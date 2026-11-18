{
  description = "Pinned toolchain for the GAMS browser compiler artifacts";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/d233902339c02a9c334e7e593de68855ad26c4cb";
    rust-overlay.url = "github:oxalica/rust-overlay/2ff7d39b901d79ee26d26f9fa32f90511eecaa0e";
    rust-overlay.inputs.nixpkgs.follows = "nixpkgs";
  };
  outputs = {
    nixpkgs,
    rust-overlay,
    ...
  }: let
    systems = ["x86_64-linux" "aarch64-darwin" "x86_64-darwin"];
  in {
    devShells = nixpkgs.lib.genAttrs systems (system: let
      pkgs = import nixpkgs {
        inherit system;
        overlays = [rust-overlay.overlays.default];
      };
      rust = pkgs.rust-bin.stable."1.94.1".default.override {targets = ["wasm32-wasip1"];};
    in {
      default = pkgs.mkShell {
        packages = [rust pkgs.nodejs_24 pkgs.python3 pkgs.gnumake pkgs.esbuild pkgs.typescript pkgs.wasm-tools pkgs.cacert pkgs.git];
      };
    });
  };
}
