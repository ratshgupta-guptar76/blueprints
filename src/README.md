# src/

Purpose: project source files (RTL and analog designs).

Layout:
- `src/rtl/`  — SystemVerilog RTL sources; `include/` holds shared headers such as `params.svh`.
- `src/analog/` — analog circuit schematics and SPICE sources (if any).

How to use:
- Build and simulation flows are driven from the top-level `Makefile` and `scripts/` utilities.
- Include/search paths: add `src/rtl/include` to simulator/synthesis include paths when running tools.

Notes:
- Keep implementation code here; testbenches and regression scripts belong in `sim/` or `verification/`.
