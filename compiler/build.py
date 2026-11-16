"""Build the patched wasm-tools API into the pinned upstream browser package."""
import base64
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build.nosync'


def remove(path):
    path = Path(path)
    path.relative_to(BUILD)
    for parent in [path, *path.parents]:
        if parent == ROOT:
            break
        if parent.is_symlink():
            raise RuntimeError(f'Refusing directory symlink: {parent}')
    if subprocess.check_output(['git', 'ls-files', '-z', '--', str(path.relative_to(ROOT))], cwd=ROOT):
        raise RuntimeError(f'Refusing tracked files: {path}')
    if path.is_dir():
        # SDK/archive directories can retain read-only modes; never chmod through links.
        for directory, _, _ in os.walk(path, followlinks=False):
            directory = Path(directory)
            if not directory.is_symlink():
                directory.chmod(directory.stat().st_mode | 0o700)
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def inputs():
    (BUILD / 'downloads').mkdir(parents=True, exist_ok=True)
    for item in json.loads((ROOT / 'compiler/inputs.json').read_text()):
        name = 'types-node' if item['name'] == '@types/node' else item['name'].split('/')[-1]
        archive = BUILD / 'downloads' / f"{name}-{item['version']}.tgz"
        if not archive.exists():
            with urllib.request.urlopen(item['url']) as response:
                archive.write_bytes(response.read())
        data = archive.read_bytes()
        if 'sha512-' + base64.b64encode(hashlib.sha512(data).digest()).decode() != item['integrity']:
            raise RuntimeError(f'Integrity mismatch: {archive}')
        destination = BUILD / 'deps' / name
        remove(destination)
        destination.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
            bundle.extractall(destination, filter='data')
        if name == 'types-node':
            roots = list(destination.iterdir())
            if len(roots) != 1 or not roots[0].is_dir():
                raise RuntimeError('Unexpected Node type SDK layout')
            target = BUILD / 'deps/types/node'
            remove(target)
            target.parent.mkdir(exist_ok=True)
            shutil.move(roots[0], target)


def environment():
    BUILD.mkdir(exist_ok=True)
    for name in ['cargo-home', 'cargo-target', 'tmp']:
        (BUILD / name).mkdir(exist_ok=True)
    return {**os.environ, 'CARGO_HOME': str(BUILD / 'cargo-home'),
            'CARGO_TARGET_DIR': str(BUILD / 'cargo-target'), 'TMPDIR': str(BUILD / 'tmp')}


def licenses(receipts, package):
    notices = package / 'vendor/licenses/patched-wasm-tools'
    manifests = {Path(item['manifest_path']) for item in receipts if item.get('reason') == 'compiler-artifact'}
    for manifest in manifests:
        if manifest.is_relative_to(ROOT / 'crates'):
            continue
        metadata = tomllib.loads(manifest.read_text())['package']
        selected = [path for path in manifest.parent.iterdir()
                    if path.is_file() and path.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'COPYRIGHT'))]
        if metadata.get('license-file'):
            selected.append(manifest.parent / metadata['license-file'])
        if not selected:
            supplied = ROOT / 'compiler/licenses' / f"{metadata['name']}-{metadata['version']}"
            if not supplied.is_dir():
                raise RuntimeError(f'Missing license text for {manifest}')
            selected = list(supplied.iterdir())
        destination = notices / f"{metadata['name']}-{metadata['version']}"
        destination.mkdir(parents=True, exist_ok=True)
        for source in selected:
            shutil.copy2(source, destination / source.name)
    rust = Path(subprocess.check_output(['rustc', '--print', 'sysroot'], text=True).strip()) / 'share/doc/rust'
    shutil.copytree(rust / 'licenses', notices / 'rust-std/licenses')
    shutil.copy2(rust / 'COPYRIGHT-library.html', notices / 'rust-std/COPYRIGHT-library.html')
    shutil.copy2(ROOT / 'LICENSE', notices / 'LICENSE')
    for path in notices.rglob('*'):
        path.chmod(0o755 if path.is_dir() else 0o644)


def package():
    env = environment()
    inputs()
    for name in ['package', 'work']:
        remove(BUILD / name)
    package = BUILD / 'package'
    shutil.copytree(BUILD / 'deps/jco-transpile/package', package)
    # Only wasm-tools is rebuilt; the pinned upstream bindgen component is retained.
    command = ['cargo', 'build', '--locked', '-p', 'wasm-tools-js', '--release',
               '--target', 'wasm32-wasip1', '--message-format=json-render-diagnostics']
    result = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, text=True, check=True)
    (BUILD / 'cargo-receipts.jsonl').write_text(result.stdout)
    receipts = [json.loads(line) for line in result.stdout.splitlines()]
    core = BUILD / 'cargo-target/wasm32-wasip1/release/wasm_tools_js.wasm'
    component = BUILD / 'wasm-tools.component.wasm'
    subprocess.run(['wasm-tools', 'component', 'new', str(core), '--adapt',
                    'wasi_snapshot_preview1=' + str(ROOT / 'packages/jco/lib/wasi_snapshot_preview1.reactor.wasm'),
                    '-o', str(component)], check=True)
    subprocess.run(['wasm-tools', 'validate', str(component)], check=True)
    # Remove every old wasm-tools binding/type/core file before regeneration.
    for path in (package / 'vendor').glob('wasm-tools*'):
        path.unlink()
    subprocess.run(['node', 'compiler/generate.mjs'], cwd=ROOT, env=env, check=True)
    work = BUILD / 'work'
    (work / 'src').mkdir(parents=True)
    shutil.copytree(package / 'vendor', work / 'vendor', ignore=shutil.ignore_patterns('*.wasm', '*.js'))
    for name in ['wasm-tools.ts', 'wasm-tools-component.ts', 'tool-imports.ts']:
        shutil.copy2(ROOT / 'packages/jco-transpile/src' / name, work / 'src' / name)
    config = {'compilerOptions': {'target': 'ES2022', 'module': 'ESNext', 'moduleResolution': 'Bundler',
              'strict': True, 'skipLibCheck': True, 'declaration': True, 'sourceMap': True,
              'rootDir': str(work / 'src'), 'outDir': str(package / 'dist'),
              'typeRoots': [str(BUILD / 'deps/types')], 'types': ['node'],
              'paths': {'@bytecodealliance/preview2-shim/instantiation': [str(BUILD / 'deps/preview2-shim/package/dist/common/instantiation.d.ts')],
                        '@bytecodealliance/preview2-shim': [str(BUILD / 'deps/preview2-shim/package/dist/browser/index.d.ts')]}},
              'files': [str(path) for path in sorted((work / 'src').glob('*.ts'))]}
    (work / 'tsconfig.json').write_text(json.dumps(config))
    subprocess.run(['tsc', '--project', str(work / 'tsconfig.json')], check=True)
    # Preserve the package's other exports while adding the new root re-export.
    with (package / 'dist/index.js').open('a') as output:
        output.write("\nexport { componentWitJson } from './wasm-tools.js';\n")
    with (package / 'dist/index.d.ts').open('a') as output:
        output.write("\nexport { componentWitJson } from './wasm-tools.js';\n")
    licenses(receipts, package)
    identity = {'source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'upstream': '0cd19e847994a4adffe6d723cb10a733ff9b2f2c',
                'tag': os.environ.get('GITHUB_REF_NAME', 'development'),
                'componentSha256': hashlib.sha256(component.read_bytes()).hexdigest()}
    (package / 'gams-compiler.json').write_text(json.dumps(identity, indent=2) + '\n')
    archive = BUILD / 'jco-transpile.tgz'
    with archive.open('wb') as target, gzip.GzipFile(fileobj=target, mode='wb', mtime=0, filename='') as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as bundle:
            for path in sorted(package.rglob('*')):
                info = bundle.gettarinfo(str(path), str(path.relative_to(BUILD)))
                info.uid = info.gid = info.mtime = 0
                info.mode = 0o755 if path.is_dir() else 0o644
                info.uname = info.gname = ''
                if path.is_file():
                    with path.open('rb') as data:
                        bundle.addfile(info, data)
                else:
                    bundle.addfile(info)


def clean():
    if any((BUILD / 'cargo-home' / name).exists() for name in ['credentials', 'credentials.toml']):
        raise RuntimeError('Refusing to remove a Cargo home containing credentials')
    for name in ['package', 'work', 'deps', 'downloads', 'cargo-home', 'cargo-target', 'tmp', 'pycache',
                 'wasm-tools.component.wasm', 'cargo-receipts.jsonl', 'jco-transpile.tgz', 'SHA256SUMS']:
        remove(BUILD / name)


if __name__ == '__main__':
    {'package': package, 'clean': clean}[sys.argv[1]]()
