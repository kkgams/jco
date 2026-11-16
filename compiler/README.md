# GAMS compiler artifacts

This fork publishes the browser compiler package consumed by GAMS. The `gams`
branch starts from `jco-transpile-v0.24.0`
(`0cd19e847994a4adffe6d723cb10a733ff9b2f2c`) and adds
`componentWitJson(bytes): Promise<string>` to the existing wasm-tools API.
Its JSON contains the selected `world` index and the full `resolve` graph,
including resource ownership and aliases. The format follows the bundled
wit-parser version; consumers must pin the artifact and integrity hash.

Upstream history, package layout, licenses and normal upstream commands remain
intact. This is a compiler-tool fork, not a GAMS Project Unit. It does not bundle
GAMS, change plugin ABIs or publish packages to npm.

## Build

```sh
nix develop --command make test
nix develop --command make package
```

| Ref | Output / behavior |
| --- | --- |
| B1 | `build.nosync/jco-transpile.tgz` contains the pinned upstream package with regenerated wasm-tools WASM, JS bindings and TypeScript declarations. The original bindgen compiler is retained byte-for-byte. |
| B2 | `build.nosync/SHA256SUMS` covers that exact archive. `package` is incremental; a repeat invocation does no work. |
| B3 | The pinned flake supplies Rust 1.94.1 with the WASIp1 target, Node 24, TypeScript, Python and wasm-tools. No SDK or package-manager installer runs from Make. |
| B4 | `compiler/inputs.json` pins and verifies the bootstrap compiler, browser shim and Node type SDK archives. The bootstrap uses an isolated in-memory filesystem; it needs no Node filesystem addon or installed dependency tree. |
| B5 | Packaging checks the actual generated schema API, owned/borrowed distinctions and declared errors. Original package notices are retained; copied license texts for rebuilt Rust dependencies and the Rust standard library accompany the archive. |

All downloaded/intermediate files and Cargo caches are under `build.nosync/`.
`make clean` removes only the declared output/cache locations, refuses tracked
files/directory symlinks and refuses a Cargo home containing credentials. Other
files in `build.nosync/` are preserved. Do not put authored inputs or credentials
in generated-output locations.

## Publish and consume

Pushes to `gams` run native tests and build the package. A `gams-v*` tag builds
once and publishes the archive plus checksum using GitHub Releases and the
automatic workflow token; an existing release is not overwritten. The tag selects
the compiler build, not an npm publication or a new upstream package version.

For example, tag a reviewed commit as `gams-v0.24.0-1` and push that tag. Consumers
use the explicit release URL:

```text
https://github.com/kkgams/jco/releases/download/gams-v0.24.0-1/jco-transpile.tgz
```

GAMS downloads this archive and verifies its declared integrity. It never builds
this fork or depends on a sibling checkout. Update its compiler/cache identity
when selecting a different fork build. Publishing this package does not implement
the generic Runtime converter or callbacks/linking.

For an upstream refresh, select the intended source revision, reconcile the
small API change, regenerate the lockfile deliberately, and run native/package
and real-browser metadata checks before publishing a new immutable tag. Retain
original notices. If upstream provides equivalent metadata, drop the local API
patch after verifying parity.
