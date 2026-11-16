SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := package
BUILD := build.nosync
SOURCES := $(shell find compiler crates/wasm-tools-component -type f) Cargo.toml Cargo.lock flake.nix flake.lock Makefile LICENSE packages/jco/lib/wasi_snapshot_preview1.reactor.wasm packages/jco-transpile/src/wasm-tools.ts packages/jco-transpile/src/wasm-tools-component.ts packages/jco-transpile/src/tool-imports.ts

.PHONY: package test clean
package: $(BUILD)/jco-transpile.tgz $(BUILD)/SHA256SUMS

$(BUILD)/jco-transpile.tgz: $(SOURCES)
	python3 compiler/build.py package

$(BUILD)/SHA256SUMS: $(BUILD)/jco-transpile.tgz
	python3 -c 'from pathlib import Path; import hashlib; p=Path("$<"); Path("$@").write_text(hashlib.sha256(p.read_bytes()).hexdigest()+"  "+p.name+"\n")'

test:
	PYTHONPYCACHEPREFIX="$(abspath $(BUILD))/pycache" python3 -m unittest discover -s compiler -p 'test_*.py'
	mkdir -p $(BUILD)/cargo-home $(BUILD)/cargo-target $(BUILD)/tmp
	CARGO_HOME="$(abspath $(BUILD))/cargo-home" CARGO_TARGET_DIR="$(abspath $(BUILD))/cargo-target" TMPDIR="$(abspath $(BUILD))/tmp" cargo test --locked -p wasm-tools-js --lib

clean:
	python3 compiler/build.py clean
