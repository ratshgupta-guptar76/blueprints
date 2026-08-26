# 9T DCIM SRAM Macro — Chipathon 2026 (Team A07 Blueprints)

A 32×32 digital compute-in-memory (DCIM) INT8 matrix-vector macro built
on a 9T SRAM bitcell, targeting the GF180MCU open PDK via the
[LibreLane](https://github.com/librelane/librelane) RTL-to-GDS flow.
The macro stores a stationary 32×32 weight matrix, streams in bit-serial
activations, and computes a 4-way INT8 dot product per row using an
AND-multiply array feeding a shift-accumulate output stage.

Built on the [wafer-space `gf180mcu-project-template`](https://github.com/wafer-space/gf180mcu-project-template)
padframe/flow infrastructure — see [Credits](#credits) below.

## Architecture

```
a_bit, w_bit, start, cont, P_minus1[2:0]      clk, rst_n
        │                                          │
        ▼                                          ▼
┌─────────────────┐  act_bp  ┌───────────────┐  busy, done
│ act_shift_chain │────────▶│               │◀───────────── control_fsm
│ weight_load     │  w_buf   │  dcim_array   │   (IDLE → WRITE_W → WRITE_A
└─────────────────┘────────▶│ (32×128 AND)  │    → COMPUTE → DONE → SHIFT_OUT)
                             └──────┬────────┘
                                    │ pp[32][128]
                                    ▼
                             ┌──────────────┐
                             │  adder_tree  │  per-column popcount
                             └──────┬───────┘
                                    ▼
                             ┌──────────────┐
                             │ shift_accum  │  4× INT8 accumulators
                             └──────┬───────┘
                                    ▼
                             ┌──────────────┐
                       y_bit │  stream_out  │  serial drain (176 bits)
                             └──────────────┘
```

- **Array**: `ROWS=32`, `COLS=N_WEIGHTS*DW=4*8=128` — a 32×32 weight
  matrix packed as 4 INT8 weight columns × 8 bit-planes each.
- **Compute**: bit-serial, weight-stationary. Weights load once
  (`WRITE_W`); each activation vector re-enters via `cont`, looping
  `SHIFT_OUT → WRITE_A` without reloading weights.
- **Precision**: activations are `P_minus1+1` bits wide (1–8b,
  configurable per-transaction via `P_minus1[2:0]`); weights are
  fixed INT8.
- **Datapath**: see [`src/dcim_pkg.sv`](src/dcim_pkg.sv) for all
  width parameters and [`src/dcim_top.sv`](src/dcim_top.sv) for the
  module wiring. FSM/dataflow diagrams live in
  [`docs/architecture/`](docs/architecture) (`ComputeFlow.png`,
  `fsm_states.png`, `SystemOverview2.png`).

`src/A07_dcim_top.sv` is the padframe-facing top: it wraps `dcim_top`
and fans its ports out to the `A07_A` padring pin set defined in
[`def/A07/project_defs/`](def/A07/project_defs) (see the file header
for the full pad-by-pad rationale).

### RTL module map

| Module | Role |
|---|---|
| `dcim_pkg.sv` | Shared width/precision parameters |
| `dcim_top.sv` | Top-level datapath wiring |
| `control_fsm.sv` | One-hot FSM: IDLE → WRITE_W → WRITE_A → COMPUTE → DONE → SHIFT_OUT |
| `weight_load.sv` | Serial weight-bit assembly into a row buffer |
| `row_decoder.sv` | One-hot row select for weight writes |
| `dcim_array.sv` | Weight storage (SRAM at hardening) + AND-multiply grid |
| `act_shift_chain.sv` | Bit-serial activation shift chain, one bit-plane per row |
| `adder_tree.sv` | Per-column popcount of partial products |
| `col_adder.sv` | Adder-tree leaf/node cell |
| `shift_accum.sv` | Shift-and-accumulate INT8 output accumulators |
| `stream_out.sv` | Serial output drain (`y_bit`) |
| `A07_dcim_top.sv` | Padframe-facing top for the `A07_A` padring slot |

## Repository layout

```
.
├── README.md                # this file
├── info.yaml                # Chipathon project metadata + pinout
├── Makefile                 # lint / sim / func / librelane / sim-gl targets
├── src/                     # SystemVerilog RTL (see module map above)
├── cocotb/                  # cocotb testbenches
│   ├── A07_dcim_top_tb.py   # top-level RTL/GL testbench
│   ├── functional/          # per-module functional testbenches
│   └── golden/              # Python golden/reference models
├── librelane/                # LibreLane flow config + padring slots
│   ├── config.yaml
│   ├── pdn_cfg.tcl
│   └── slots/                # slot_workshop.yaml, slot_0p5x0p5.yaml, ...
├── def/A07/                  # padring def templates + selected variants
├── ip/sram_32x8_9T/          # 9T SRAM bitcell macro (gds/lef/lib/mag/spice)
├── analog/                   # bitcell schematic/layout + ngspice sims (Xschem/Magic)
├── gf180mcu/                 # cloned PDK + gf180mcu_ws_ip__* macros (via clone-pdk)
├── final/                    # LibreLane signoff outputs (gds/lef/lib/sdf/spef/...)
├── verilog/, gds/, def/      # top-level post-PnR netlist / GDS / DEF snapshots
├── reports/                  # DRC, LVS, IR-drop, STA summary, metrics.csv
├── docs/
│   ├── architecture/          # diagrams (ComputeFlow, fsm_states, SystemOverview, ...)
│   ├── guides/                 # reproducing-native.md, reproducing-docker.md, workshop-slot-spec.md
│   ├── analog_sim/             # read-disturb margin plots
│   └── logs/                   # synthesis logs
├── examples/                 # rtl2gds_chipathon_padring.ipynb walkthrough
└── scripts/
    ├── flow/                   # padring.py, lay2img.py, render_full_chip.py
    ├── mutation/                # mutate.sh + tables/ (per-module mutation tables)
    ├── env/                     # run_native.sh, run_docker_iic.sh, verify_workshop_slot.sh
    └── python/                  # librelane_plugin_padframe_bridge (PYTHONPATH plugin)
```

## Quickstart

### Native build (nix-shell)

```bash
nix-shell                  # provides LibreLane 3.0.0
make clone-pdk              # clones wafer-space/gf180mcu PDK @ 1.8.0
make lint                   # Verilator lint
make sim                    # legacy padded chip_top sim (see Simulation below for A07_dcim_top)
make librelane-core          # synth + PnR for the DCIM core (no padring)
make librelane                # full flow with the A07 padring
```

Signoff artifacts land in `final/` (GDS, LEF, LIB across PVT corners,
SDF, SPEF, post-layout netlist) and `reports/` (DRC, LVS, IR-drop,
timing summary, `metrics.csv`).

### Simulation

```bash
make func=dcim_array               # functional test for one module (cocotb + golden model)
make func-all                      # run every module's functional testbench
make func-mut=dcim_array           # functional test + mutation coverage for one module
make func-mut-all                  # functional + mutation for every module with a mutation table
make sim                           # legacy padded chip_top/chip_core sim (chip_top_tb.py)
make sim-gl-core                   # gate-level sim of the DCIM core (after librelane-core)
make sim-view                      # view waveforms (GTKWave/Surfer)

# System-level RTL sim of A07_dcim_top (the actual padframe-facing DCIM top)
# is run directly rather than through a Makefile alias, and shares its
# testbench with sim-gl-core's gate-level pass:
cd cocotb && PDK_ROOT=${PDK_ROOT} PDK=${PDK} python3 A07_dcim_top_tb.py
```

### Docker (iic-osic-tools, for GDS/layout inspection)

`scripts/env/run_docker_iic.sh` launches the `hpretl/iic-osic-tools`
container with this repo mounted; inside, open `final/gds/*.gds` in
KLayout or Magic. See `docs/guides/reproducing-docker.md` and
`docs/guides/reproducing-native.md` for full walkthroughs, and
`examples/rtl2gds_chipathon_padring.ipynb` for an annotated notebook
version of the flow.

## Verification

- **Functional (RTL)**: per-module cocotb testbenches in
  `cocotb/functional/`, each checked against a Python golden model in
  `cocotb/golden/`. Run individually via `make func=<module>` or all
  at once via `make func-all`.
- **Mutation testing**: `make func-mut=<module>` / `func-mut-all`
  scores testbench quality against injected RTL mutants
  (`scripts/mutation/tables/`).
- **Top-level / gate-level**: `cocotb/A07_dcim_top_tb.py` drives the
  padframe-facing top; `make sim-gl-core` re-runs it against the
  post-PnR netlist for sign-off-equivalence checking.
- **Physical signoff**: Magic DRC, KLayout DRC, Netgen LVS
  (`lvs_config.json`), antenna, and multi-corner STA are run as part
  of `make librelane`. Latest results are in `reports/` — see
  `reports/summary.md` for the STA overview and `reports/metrics.csv`
  for the full metric dump (42 309 instances, 0 lint errors, 0 setup
  violations across all corners as of the last signed-off run).
- **Bitcell-level**: the 9T bitcell's read-disturb margin is
  characterized via ngspice in `analog/characterization/9t/` (plots in
  `docs/analog_sim/`).

## SRAM macro

The compute array bottoms out on a custom **9T SRAM bitcell**
(`ip/sram_32x8_9T/`) chosen for its decoupled read port (reduced
read-disturb vs. a 6T cell), pre-characterized as a `32x8` macro with
GDS, LEF, Liberty, SPICE, and PEX views. Bitcell schematic/layout
source and ngspice read-disturb sims live under `analog/`.

## Credits

This project builds on the [wafer-space `gf180mcu-project-template`](https://github.com/wafer-space/gf180mcu-project-template)
(Leo Moser and contributors, Apache-2.0) for the Nix flake, LibreLane
flow skeleton, and padframe conventions, and on
[Juan Moya's `padring_gf180`](https://github.com/JuanMoya/padring_gf180)
workshop padring layout (Apache-2.0) for the original workshop slot
this project's padring is derived from. See [`CREDITS.md`](CREDITS.md)
for full per-artifact attribution and [`AUTHORS.md`](AUTHORS.md) for
copyright holders.

## License

Apache-2.0, inherited from upstream. See [`LICENSE`](LICENSE) for the
full text and [`NOTICE`](NOTICE) for third-party attribution.
