"""Clean safety tests use isolated Git repositories, never checkout output."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
SCRIPT = 'compiler/build.py'
TARGETS = ("build.nosync", "tools", "gams_modules")


class SafeCleanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        destination = self.root / SCRIPT
        destination.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE / SCRIPT, destination)
        shutil.copyfile(SOURCE / "Makefile", self.root / "Makefile")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        for name in TARGETS:
            (self.root / name / "unmarked/nested").mkdir(parents=True)
            (self.root / name / "unmarked/nested/stale").write_text("recreate")
        for name in ("catalog", "models", "target", "dist", "authored"):
            (self.root / name).mkdir()
            (self.root / name / "keep").write_text("preserve")

    def clean(self):
        return subprocess.run(["make", "clean"], cwd=self.root, capture_output=True, text=True)

    def assert_preserved(self):
        for name in TARGETS:
            self.assertTrue((self.root / name / "unmarked/nested/stale").exists())

    def test_make_removes_all_unmarked_trees_and_is_repeatable(self):
        for _ in range(2):
            result = self.clean()
            self.assertEqual(result.returncode, 0, result.stderr)
        for name in TARGETS:
            self.assertFalse((self.root / name).exists())
        for name in ("catalog", "models", "target", "dist", "authored"):
            self.assertEqual((self.root / name / "keep").read_text(), "preserve")

    def test_preflight_refuses_tracked_files_in_every_tree(self):
        for name in TARGETS:
            with self.subTest(name=name):
                path = name + "/unmarked/nested/stale"
                subprocess.run(["git", "add", "-f", path], cwd=self.root, check=True)
                self.assertNotEqual(self.clean().returncode, 0)
                self.assert_preserved()
                subprocess.run(["git", "rm", "--cached", "-q", path], cwd=self.root, check=True)

    def test_preflight_refuses_nested_file_directory_and_dangling_links(self):
        for name in TARGETS:
            for target in ("authored/keep", "authored", "missing"):
                with self.subTest(name=name, target=target):
                    link = self.root / name / "link"
                    link.symlink_to(self.root / target)
                    self.assertNotEqual(self.clean().returncode, 0)
                    self.assert_preserved()
                    link.unlink()

    def test_preflight_refuses_top_level_links_and_files(self):
        for name in TARGETS:
            path = self.root / name
            saved = self.root / (name + "-saved")
            path.rename(saved)
            for target in (saved, self.root / "missing"):
                path.symlink_to(target, target_is_directory=True)
                self.assertNotEqual(self.clean().returncode, 0)
                self.assertTrue((saved / "unmarked/nested/stale").exists())
                path.unlink()
            path.write_text("not a directory")
            self.assertNotEqual(self.clean().returncode, 0)
            path.unlink()
            saved.rename(path)
            self.assert_preserved()
