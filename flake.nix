{
  description = "pytest-sentry-capture development and package checks";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    flake-parts.inputs.nixpkgs-lib.follows = "nixpkgs";
    nix-tooling.url = "github:adamcik/nix-tooling";
    nix-tooling.inputs.nixpkgs.follows = "nixpkgs";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{
      flake-parts,
      nix-tooling,
      uv2nix,
      pyproject-nix,
      pyproject-build-systems,
      ...
    }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [ "x86_64-linux" ];
      imports = [
        nix-tooling.flakeModules.formatting.common
        nix-tooling.flakeModules.formatting.python
      ];
      perSystem =
        { pkgs, ... }:
        let
          inherit (pkgs) lib;
          project = "pytest-sentry-capture";
          workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
          overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };
          python = pkgs.python312;
          baseSet = pkgs.callPackage pyproject-nix.build.packages { inherit python; };
          pythonSet = baseSet.overrideScope (
            lib.composeManyExtensions [
              pyproject-build-systems.overlays.default
              overlay
            ]
          );
          devVenv = pythonSet.mkVirtualEnv "${project}-checks" { ${project} = [ "dev" ]; };
          editableSet = pythonSet.overrideScope (
            workspace.mkEditablePyprojectOverlay { root = "$REPO_ROOT"; }
          );
          editableVenv = editableSet.mkVirtualEnv "${project}-dev" { ${project} = [ "dev" ]; };
          mkCheck =
            name: body:
            pkgs.runCommand "${project}-${name}"
              {
                src = ./.;
                nativeBuildInputs = [
                  devVenv
                  pkgs.uv
                ];
              }
              ''
                cp -r "$src" source
                chmod -R u+w source
                cd source
                export HOME="$TMPDIR"
                export UV_PYTHON="${devVenv}/bin/python"
                export UV_PYTHON_DOWNLOADS=never
                ${body}
                touch "$out"
              '';
        in
        {
          packages.default = pythonSet.${project};
          checks = {
            package = pythonSet.${project};
            lock = mkCheck "lock" "uv lock --check --offline";
            tests = mkCheck "tests" ''pytest -q -n 2 -o cache_dir="$TMPDIR/pytest-cache"'';
            typing = mkCheck "typing" "basedpyright";
            distributions =
              pkgs.runCommand "${project}-distributions"
                {
                  src = ./.;
                  nativeBuildInputs = [ devVenv ];
                }
                ''
                  cp -r "$src" source
                  chmod -R u+w source
                  cd source
                  export HOME="$TMPDIR"
                  python -m build --no-isolation --outdir "$out"
                  twine check "$out"/*
                '';
          };
          devShells.default = pkgs.mkShell {
            packages = [
              editableVenv
              pkgs.uv
            ];
            env = {
              UV_NO_SYNC = "1";
              UV_NO_MANAGED_PYTHON = "1";
              UV_PYTHON = python.interpreter;
              UV_PYTHON_DOWNLOADS = "never";
            };
            shellHook = ''
              unset PYTHONPATH
              export REPO_ROOT=$(git rev-parse --show-toplevel)
            '';
          };
        };
    };
}
