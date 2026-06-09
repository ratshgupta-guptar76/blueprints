# blueprints
Repository for the SSCS PICO Chip-a-thon 2026 - [Track A7] dCIM Module

## Project Layout

```
.
├── src/               # Implementation sources
│   ├── rtl/           # SystemVerilog RTL (top.sv, include/params.svh)
│   └── analog/        # Analog circuit designs
├── sim/               # Simulation testbenches and flows
│   ├── rtl/           # RTL simulations
│   ├── analog/        # Analog simulations
│   └── mix/           # Mixed-signal simulations
├── verification/      # Verification plans and orchestration
├── pdk/               # Process design kit files and documentation
├── config/            # Configuration files (tool settings, pin orders, etc.)
├── liberlane/         # Project-local library (libercell library)
├── docs/              # Documentation and technical references
├── scripts/           # Helper scripts (eda.sh, etc.)
├── Makefile           # Build and test automation
├── LICENSE            # License information
└── README.md          # This file
```

## Quick Start

List available targets:
```bash
make help
```

Run RTL simulation:
```bash
make sim-rtl
```

Run all simulations:
```bash
make test
```

Run CI smoke test (verify repo layout):
```bash
make ci-smoke
```

## Documentation

- [src/README.md](src/README.md) — Source code structure and include paths
- [sim/README.md](sim/README.md) — Simulation layout and how to run tests
- [verification/README.md](verification/README.md) — Verification methodology
- [pdk/README.md](pdk/README.md) — PDK setup and version information

## CI/CD

Automated checks run on pull requests and merges (see `.github/workflows/ci.yml`).
