import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('compiler_build', Path(__file__).with_name('build.py'))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class CleanTests(unittest.TestCase):
    def setUp(self):
        temporary = Path(__file__).resolve().parents[1] / 'build.nosync/tmp'
        temporary.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temporary)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.original = build.ROOT, build.BUILD
        self.addCleanup(self.restore)
        build.ROOT, build.BUILD = self.root, self.root / 'build.nosync'
        build.BUILD.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)

    def restore(self):
        build.ROOT, build.BUILD = self.original

    def test_clean_removes_entire_disposable_tree(self):
        (build.BUILD / 'work').mkdir()
        (build.BUILD / 'work/generated').write_text('generated')
        (build.BUILD / 'stale').write_text('recreate')
        build.clean()
        self.assertFalse((build.BUILD / 'work').exists())
        self.assertFalse(build.BUILD.exists())

    def test_clean_refuses_tracked_edits_and_credentials(self):
        target = build.BUILD / 'work'
        target.mkdir()
        (target / 'input').write_text('original')
        subprocess.run(['git', '-C', str(self.root), 'add', '-f', 'build.nosync/work/input'], check=True)
        (target / 'input').write_text('edited')
        with self.assertRaisesRegex(RuntimeError, 'tracked'):
            build.remove(target)
        self.assertEqual((target / 'input').read_text(), 'edited')
        credentials = build.BUILD / 'cargo-home'
        credentials.mkdir()
        (credentials / 'credentials.toml').write_text('fixture only')
        with self.assertRaisesRegex(RuntimeError, 'credentials'):
            build.clean()
        self.assertTrue((credentials / 'credentials.toml').exists())

    def test_clean_removes_readonly_generated_directories(self):
        target = build.BUILD / 'work' / 'licenses'
        target.mkdir(parents=True)
        (target / 'LICENSE').write_text('fixture')
        target.chmod(0o555)
        build.clean()
        self.assertFalse((build.BUILD / 'work').exists())

    def test_clean_refuses_directory_symlinks(self):
        outside = self.root / 'authored'
        outside.mkdir()
        (outside / 'input').write_text('keep')
        (build.BUILD / 'work').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'symlink'):
            build.clean()
        self.assertEqual((outside / 'input').read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
