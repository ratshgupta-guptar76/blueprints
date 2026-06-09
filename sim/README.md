# sim/

Purpose: simulation testbenches, regression scripts, and waveform artifacts.

Layout:
- `sim/rtl/`   — RTL testbenches and test vectors that exercise `src/rtl`.
- `sim/analog/` — Analog SPICE testbenches and netlists that exercise `src/analog`.
- `sim/mix/`   — Mixed-signal testbenches combining analog and RTL components.

How to run:
- Use `scripts/eda.sh` helper scripts or the top-level `Makefile` to run simulations. See each subfolder README for per-test instructions.

Notes:
- Organize regression by target name and add a short README per test when it is non-trivial.
