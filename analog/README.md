# Analog Workspace

Full-custom design and characterization of the 9T compute-in-memory
bitcell behind the [`ip/sram_32x8_9T/`](../ip/sram_32x8_9T) macro — the
*development* side of the SRAM cell, as opposed to `ip/`, which holds only
the signed-off views the LibreLane flow actually places. ngspice and the
GF180 PDK only exist inside the IIC-OSIC-TOOLS container, not in the
repo-root Nix shell (that shell is the *digital* LibreLane environment).
Launch the container with
[`scripts/env/run_docker_iic.sh`](../scripts/env/run_docker_iic.sh); it
bind-mounts the whole repo at `/workspace`, so `/workspace/analog` stays in
sync with the host with nothing to copy in.

## Layout

```
cells/                 # bitcell DUT: schematic + extracted SPICE
  9T_03v3.sch/.spice

testbench/               # reusable testbench subcircuits, .include'd by characterization/9t/ decks
  9T_tb.spice             # closed-loop wrapper
  9T_open_tb.spice         # open-loop wrapper

characterization/
  pvt.spice, pvt_ff_n40C_3v60.spice,   # PVT corner definitions (tt/ff/ss), shared across
    pvt_ss_125C_3v00.spice,             # every deck below
    pvt_tt_025C_3v30.spice
  9t/                                    # runnable ngspice test decks, one file per metric
    read_run, write_run, read_delay, write_delay, write_margin, hold_snm,
    hold_power, access_energy, compute_disturb_{hi,lo}, mult_w*a*_test,
    monte_carlo_{hold,wm}, ...
    results/                             # ngspice raw output -- gitignored, safe to delete/regenerate

layout/9T/               # 9T physical layout
  mag/       # Magic layout (.mag) -- tileable cell, tap column, the hardened sram_32x8_9T tile
  gds/       # streamed-out GDS
  scripts/   # to_sram.sh/to_std.sh (SRAMDEF marker toggle), check.sh (DRC), add_sramdef.py
```

**No sweep automation exists yet for 9T.** This directory used to also
hold an 8T bitcell variant (an earlier, ultimately-not-chosen topology) and
all of its sizing/PVT/Monte-Carlo sweep tooling (`sizing_sweep.py`,
`m1m2_sweep.py`, `pvt_sweep.ipynb`, `mc.ipynb`); that material was removed
once 9T became the only variant this repo develops, and every one of those
sweep tools was written specifically against the 8T decks (`sim/8t/`), not
9T. It's still recoverable from git history if a 9T-targeted version needs
to be built from it. Until then, characterizing 9T means running the decks
in `characterization/9t/` directly.

## Tool flow

| Step | Tool | Output |
|------|------|--------|
| Schematic | `xschem` | `cells/9T_03v3.sch`, `testbench/*.spice` |
| Characterize | `ngspice` | `characterization/9t/*.spice` decks → `characterization/9t/results/` |
| Layout | `magic` | `layout/9T/mag/*.mag` |
| DRC | `magic` / `klayout` (`layout/9T/scripts/check.sh`) | clean layout |
| Extract + LVS | `magic` (PEX) + `netgen` | schematic-vs-layout match |

## Handoff to the digital flow

The hardened views the LibreLane flow consumes live in
[`ip/sram_32x8_9T/`](../ip/sram_32x8_9T) (`gds/`, `lef/`, `lib/`, `nl/`,
`spef/`, `vh/`), declared in `librelane/config.yaml` /
`librelane/config_core.yaml`'s `MACROS.sram_32x8_9T`. Keep this `analog/`
folder for the *sources* (schematic/layout/SPICE/characterization); keep
`ip/sram_32x8_9T/` for the *built views* that actually get placed in the
core.
