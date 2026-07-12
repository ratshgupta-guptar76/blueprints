{
  nixConfig = {
    extra-substituters = [
      "https://nix-cache.fossi-foundation.org"
    ];
    extra-trusted-public-keys = [
      "nix-cache.fossi-foundation.org:3+K59iFwXqKsL7BNu6Guy0v+uTlwsxYQxjspXzqLYQs="
    ];
  };

  inputs = {
    librelane.url = "github:librelane/librelane/3.0.0";
  };

  outputs =
    {
      self,
      librelane,
      ...
    }:
    let
      nix-eda = librelane.inputs.nix-eda;
      devshell = librelane.inputs.devshell;
      nixpkgs = nix-eda.inputs.nixpkgs;
      lib = nixpkgs.lib;
    in
    {
      # Outputs
      legacyPackages = nix-eda.forAllSystems (
        system:
        import nixpkgs {
          inherit system;
          overlays = [
            nix-eda.overlays.default
            devshell.overlays.default
            librelane.overlays.default
          ];
        }
      );

      packages = nix-eda.forAllSystems (system: {
        inherit (self.legacyPackages.${system}.python3.pkgs) ;
      });

      devShells = nix-eda.forAllSystems (
        system:
        let
          pkgs = (self.legacyPackages.${system});
          callPackage = lib.callPackageWith pkgs;

          # cocotb-coverage isn't in nixpkgs; build it from the PyPI wheel.
          cocotb-coverage = pkgs.python3.pkgs.buildPythonPackage rec {
            pname = "cocotb-coverage";
            version = "2.0";
            format = "wheel";
            src = pkgs.fetchurl {
              url = "https://files.pythonhosted.org/packages/ae/cf/c49f7a475f2d0303007f8a5aaf9e3cbe098179c6bb956d770e881e88735a/cocotb_coverage-2.0-py3-none-any.whl";
              sha256 = "1f65a15f7431b254bcb5f5a5d1b4676c5e89919546de4faaa4dbfda86f8300cb";
            };
            propagatedBuildInputs = with pkgs.python3.pkgs; [
              cocotb
              python-constraint
              pyyaml
            ];
            doCheck = false;
          };
        in
        {
          default = pkgs.librelane-shell.override ({
            extra-packages = with pkgs; [
              # Utilities
              gnumake
              gnugrep
              gawk

              # Simulation
              iverilog
              verilator

              # Waveform viewing
              gtkwave
              surfer
            ];

            extra-python-packages =
              ps: with ps; [
                # Verification
                cocotb
                cocotb-coverage
                pytest

                # Golden model / numerics
                numpy
                matplotlib

                # For KLayout Python DRC runner
                docopt

                # For logo generation
                pillow
              ];
          });
        }
      );
    };
}