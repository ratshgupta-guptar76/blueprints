# CLAUDE.md

Guidance for Claude Code working in this repository. Read this fully before making any change. Also read `docs/DESIGN_RATIONALE.md` (why each decision was made) `docs/V2_DESIGN_GUIDE.md` (how each change works, with every item tagged Measured, Decided, Proposed, Open, or Estimate), and `docs/V2_FLOW_AUDIT.md` (what can go wrong at each flow step, and the risk register) before proposing any architectural change. `docs/HANDOFF.md` is being regenerated and is not in the repo yet; the earlier handoff is superseded, so where it disagrees with this file or the rationale, it is wrong.

## Project

Digital compute-in-memory (DCIM) INT8 matrix-vector macro, y = W^T * a, on GF180MCU (gf180mcuD) with the LibreLane flow. v1 was submitted for fabrication through the SSCS PICO Chipathon 2026 (Team A07 "Blueprints"). Say "submitted for fabrication", not "fabricated", until silicon returns. v2 is in development on this repo.

Custom 9T SRAM bitcell (6T storage + compute port), packaged as the `sram_32x8_9T` macro in `ip/sram_32x8_9T/`. Four macros form the 32x32 bit array.

## Authorship rules (important)

- Karan writes all RTL in `src/` and all SPICE/analog in `ip/` and `analog/`. Do not create or modify these files unless explicitly asked in the current request. When asked, keep diffs minimal and explain every changed line.
- You may freely write and edit: cocotb testbenches (`cocotb/functional/`), bus drivers (`cocotb/bfm/`), helper scripts (`scripts/`), the system model (`model/`), CI config, Makefile targets, and docs.
- Golden models (`cocotb/golden/`) must stay independent of the RTL. Derive them from the architecture contracts below, never by reading or mirroring the RTL implementation.
- Never hand-edit generated outputs: `verilog/*.pnl.v`, `gds/`, `def/`, `reports/`, anything produced by LibreLane.

## Branch and tag rules

- `v1.0` is the v1 design as submitted for fabrication (December shuttle). It may move once, before the December submission, and only if a later commit is what gets submitted. After submission, never move, delete, or rebase over it.
- `main` stays at v1 until v2 passes all merge gates. Never commit or push directly to `main`.
- v2 integration branch: `v2-dev`. Do work on `feat/<name>` branches cut from `v2-dev`.
- Never force-push. Never rewrite published history.

## Current parameters (source of truth: `src/dcim_pkg.sv`)

| Param | v1 value |
|---|---|
| ROWS | 32 |
| DW | 8 |
| N_WEIGHTS | 4 |
| COLS | N_WEIGHTS * DW = 32 |
| W_SIGN / A_SIGN | 1 / 0 |
| ACC_WIDTH | DW + A_MAX_BITS + clog2(ROWS) = 21 |

Warning: many module header comments describe an older 64x64, 8-lane configuration (512-bit load, 176-bit drain, 7-bit column sums). Trust `dcim_pkg`, not the comments. Fixing that drift is a v2 task.

## Architecture contracts

The numbers are stable: tests and docs refer to them, so do not renumber.

### Invariants (do not violate, in v1 or v2)

1. Weight-stationary. Weights persist until an explicit weight write. Running a vector never reloads or disturbs them.
2. Weights are bit-parallel INT8. Only activations are bit-serial. Never decompose weights into bit-planes; this breaks the golden model.
3. Column mapping: column c holds bit (c % DW) of weight (c / DW). `weight_load`, `dcim_array`, and the golden model must all agree.
4. Macro read mapping: `pp[r][w*8 + c] = rbl[w][r*8 + c]`. The RBL index mapping has not yet been verified against the physical ports; treat it as an open item.
5. Partial products are active-high in RTL. Column inversion belongs to the macro boundary, not the RTL.
6. Activations stream LSB-first. `act_bp` is one broadcast bit-plane per COMPUTE cycle, rows mapped 1:1 with no permutation.
10. Weight sign: the MSB column is subtracted (W_SIGN=1) in the per-cycle lane combine. Activation sign (A_SIGN) subtracts only on the last plane.
11. Sign-extend `lane_val` to ACC_WIDTH before shift-accumulate. Zero-extension corrupts negative values.
12. Each result drains LSB-first. In v1 the four results share one pin, output 0 first. In v2 return lane j carries output j, so all four drain at once.
13. Activation precision control stays (1 to 8 bits). In v1 it is the `P_minus1` pins (0 = 1 bit, 7 = 8 bits). In v2 it is a register and the pins are removed.
14. (v2) The return lanes are clocked from core CLK, which originates at the FPGA, never from LINK_CLK or a chip-local source. Return data is plain NRZ with a sync word on each lane; the FPGA aligns phase on the sync word. There is no clock recovery.
15. (v2) Load mode and raw drain width are derived from P, never set by separate mode bits. P = 1 selects the 1-bit load, anything else loads full width. Raw result width is DW + P + clog2(ROWS) (14 bits at P = 1, 21 at P = 8).
16. (v2) LINK_CLK runs continuously while the link is enabled and is never faster than core CLK. The link clock domain only samples the input lanes and writes the async FIFO; all frame parsing is in the core domain.

### v1 timing details (true of the v1 RTL; v2 is allowed to change them)

When a v2 change alters one of these, update this list in the same change.

1a. `cont` loops SHIFT_OUT -> WRITE_A without reloading weights. (v2 removes `cont`: a valid frame or a register write starts each vector.)
7. During COMPUTE, `c_en` must stay high for the whole phase. A stray `en && !c_en` injects a chain bit into a cell MSB and corrupts the plane.
8. `clr` pulses on the last WRITE_A cycle, one cycle before COMPUTE. It must never overlap `comp_en`, or plane 0 is dropped.
9. `wfull` pulses exactly one cycle per assembled row. A multi-cycle pulse double-increments `row_cnt`.

## Known bug patterns (check for these in every change)

- Copy-paste-and-rename bugs in replicated logic. Use `generate` loops instead of hand-duplicated instances or literal slices. If logic must be duplicated for a second instance (for example A-matrix logic reused for B), find-and-replace every identifier first, then review indexing separately.
- Exhaustive tests that are not exhaustive: a past bug used `range(RW)` instead of `range(ROWS)` and tested 5 of 32 addresses while claiming full coverage. Assert the iteration count in any "exhaustive" test.
- Parameter drift between `dcim_pkg` and the golden models. Use the module-global sync pattern with a None guard:
  ```python
  import golden.row_decoder as ref
  ref.ROWS = int(dut.ROWS.value)
  ```

## Verification flow

- cocotb 2.0.1, Icarus by default (`SIM=icarus`), Verilator 5.044 for coverage (`SIM=verilator`).
- Environment: `nix-shell` (see `shell.nix` / `flake.nix`).

| Task | Command |
|---|---|
| Lint RTL | `make lint` |
| One module | `make func func=<module>` |
| All modules | `make func-all` |
| Module + mutation | `make func-mut func-mut=<module>` |
| All + mutation | `make func-mut-all` |
| Top-level RTL sim | `make sim` |
| Gate-level sim | `make sim-gl` / `make sim-gl-core` |
| Full flow | `make librelane` |

- `make lint` lints `dcim_top` only. The tapeout top is `A07_dcim_top` (the pad wrapper), and it is linted only inside the LibreLane flow, where the last v1 run reported 109 warnings (102 of them `TIMESCALEMOD`).
- Gate-level simulation runs without timing. It cannot show a glitch or a clock-domain crossing fault.
- After changing any Verilator flag: `rm -rf cocotb/sim_build/<module>` (stale cache otherwise).
- Waveforms are in `cocotb/sim_build/<module>/`; Karan views them in Surfer.
- Each module test should cover: exhaustive or targeted directed cases, random cases, edge values (all-0, all-1, single-1), and X-propagation. Mutation tables live in `scripts/mutation/tables/`.
- Deliberately deferred, do not add: `cocotb/golden/__init__.py`, multi-parameter test sweeps.
- `make func-all` runs every `cocotb/functional/*_tb.py` and is the per-push fast CI check. The top-level cycle test (`dcim_top_tb.py`) is not in the repo yet. The earlier handoff says it takes about 90 s per test on Icarus and should stay out of the fast job; that timing is unmeasured here (a 9-vector top-level probe ran in about 6 s on Icarus 13), so measure it when the file lands and decide then.
- A test that needs unwritten memory (X-propagation) must run before any test that writes it: the macro model has no reset. Use `@cocotb.test(stage=-1)`.

## System model (`model/`)

A Python model of the demo chain, separate from the RTL and the cocotb tests. One package per stage: `ml_model` (datasets, training, the network as integers), `fpga` (scheduling and glue arithmetic), `digital_dcim` (bit-exact chip arithmetic and cycle estimates), `photonics` (empty so far), and `emulation.py` (runs images through all of them).

- `model/ml_model/network.py` defines the integer math the hardware must do. Like the golden models, it is derived from the contracts above, never from the RTL.
- Training needs PyTorch, which the nix shell does not have. Use `/usr/bin/python3 -m model.ml_model train ...` (or `sweep`). Everything else runs in the nix shell.
- `python3 -m model.digital_dcim` runs the chip model's self checks, including agreement with `cocotb/golden/lane_shift_accum.py`. `python3 -m model.emulation --net <file>` checks a trained network against the chip model and exits non-zero on any mismatch. Run both after changing `network.py`, `digital_dcim/`, or `fpga/`.
- `model/build/` holds trained networks, sweep tables, and downloaded test photos. It is ignored by git. Datasets are cached under `~/.cache/dcim_model/`.
- `model/dcim_system.py` is the earlier single-file version. It is the only place on-chip requantize and the photonic error sweeps are modelled until they are moved into the packages.
- Accuracy numbers are from single training runs unless stated (`--splits 3` gives three). Three runs of one network spanned 0.7 points and a rerun once moved 1.4, so do not treat single-run differences under about 1.5 points as real. State the dataset with every figure (Imagenette validation, ImageNetV2, CIFAR-10 held-out, CIFAR-10.1, or web photos). `python3 -m model.test_imagenette <web folder> <networks>` scores Imagenette networks on all three kinds.
- Network shapes are one line of text (`model/ml_model/arch.py`). `attn:16` is a self-attention layer. Running self-attention is a goal for this chip (Karan, 2026-10-09). It runs on the chip unchanged by writing each image's keys and values into the weight array, so the chip is weight-stationary within an image and those sets are rewritten per image. Measured: it matches convolution's accuracy and does not beat it, for about 20% more cycles; no chip change is needed for it (design guide 7.7).

## v2 merge gates (all required before v2-dev -> main)

1. All golden-model tests pass, coverage at or above v1. The v1 baseline (tests, line coverage, mutation results) is recorded in `docs/v1_baseline.md`, with what this gate asks of v2 in its last section.
2. Functional verification with the real macro model, not flip-flop placeholders.
3. Signoff clean: DRC, LVS, antenna, timing across PVT corners.
4. RBL mapping verified against physical ports.
5. Characterized LIB timing, not placeholder values.

## v2 scope

Same compute array as v1 (4 macros, 32 x 4). v1 is I/O-bound (256 load + 8 compute + 1 done + 85 drain = 350 cycles per vector at INT8, measured), so v2 rebalances the I/O. The reasoning for every item is in `docs/DESIGN_RATIONALE.md`.

Demo (decided 2026-10-09): photograph recognition, trained on Imagenette (ten ImageNet classes, photographs shrunk to 64 x 64 colour), run two ways on the same chip. Headline: the attention network (one-pass front end, then 3 attention blocks; 13,248 weights, 131 weight sets loaded once and 76 rewritten per image, 35,907 chip passes, 82.0% on the validation photographs and 70.8% on independent ones, mean of three runs). Reference: the "one-pass" convolution network (7,968 weights, 116 weight sets, 30,899 passes, 81.2% and 71.7%, no layer chunked). The chip is identical for both; only the weights and the FPGA schedule differ. Every pass is 8-bit, so the estimated gain over v1 is about 4.4x to 4.5x per image, not the 9.5x of the earlier 8 x 8 digits network, which is kept as a bring-up test. Wider and full-resolution networks were measured and not chosen. CIFAR-10 was the earlier demo dataset; its results remain where nothing newer exists and are labelled. See design guide section 7.

Priorities:
1. I/O:
   - Four parallel activation lanes (four sub-chains of eight rows). Contiguous mapping: input lane k feeds rows 8k to 8k + 7. Which row holds which feature is a software convention shared by the FPGA and the training script.
   - Activation gating: the macros' A input is held at zero outside compute, merged with the BIST multiplexer and driven straight from a flop so it cannot glitch.
   - Two load modes derived from P: 1-bit at P = 1, full width otherwise (one mux per row on the LSB flop).
   - Drain overlapped with the next load, with drain backpressure. A frame that arrives while the chain still holds an uncomputed vector is dropped and counted (overrun); the resend rule recovers it.
   - Precision-aware drain: raw result width DW + P + clog2(ROWS).
   - Optional on-chip bias + ReLU + requantize: 22-bit saturating bias add, truncating shift, saturate 0..255, single-pass layers only.
   - P is a register and travels with the vector: one copy latched when the load begins (load mode and compute), a second taken when the result is captured (drain width). `start` and `cont` pins are removed: a register write or a valid link frame starts a vector.
2. Interfaces and test:
   - Link RX (data path): source-synchronous, 4 lanes, async FIFO. Frame: sync, 8-bit header (2-bit type, 6-bit sequence), payload, CRC-8. The CRC is computed over symbols in arrival order. A valid frame starts compute; the CRC gates start, not load. Pull-downs on LINK_CLK and LINK_D. See contract 16.
   - Link TX: four NRZ return lanes, return lane j carries output j, sequence number echoed, see contract 14. The FPGA deskews each lane by its own sync word before checking the CRC.
   - SPI slave (control and functional fallback), clocked by SPI_SCLK in its own clock domain (not sampled by core CLK). Proposed crossing rules, not yet accepted: whole words cross, SCLK never faster than core CLK, SPI_CS_N high resets the bit counter, one dummy byte on reads. Pull-up on SPI_CS_N. Weights load as one burst; activations load through the four sub-chains re-joined into one. Writes to weights, P, bias, or shift while busy are ignored and flagged.
   - JTAG TAP on its own TCK: BYPASS, IDCODE, MBIST, CBIST, DEBUG with register file read and write. Pull-up on TMS.
   - Four clock domains: core, link receive, JTAG, SPI.
   - Write port (proposed, not yet accepted): one write controller owns it; the wordline enable comes straight from a flop; row address and bitline data are stable the cycle before, of, and after the enable; the activation input is zero during every write.
   - Memory BIST through the compute port (one-hot activation, read via column sums), compute BIST with MISR signature. Both auto-run out of reset, never gate normal operation, and abort on the first write, first valid link frame, or a timeout. Four-state status: running, pass, fail, aborted.
   - STATUS pin: BIST heartbeat until the first write or valid link frame, then DONE (one pulse per completed compute).
   - Config bits: activation source mux, compute-gate, return-lane silence.
3. Cleanup: generate-loop the macro array in `dcim_array.sv`, fix stale header comments.

Stretch goals only (do not start without being asked): ping-pong activation banks, scan of the core domain, weight loading over the link (a frame type is reserved for it; kept out because the photonic module may not pass raw weight bits through unchanged, so weights load over SPI).

Non-goals for v2: changing the bitcell or array size, analog blocks, a separate macro or pad supply, boundary scan, adder tree sharing (only revisit if area becomes tight after synthesis).

Pin budget: 22 pads total including power, one supply net (VDD) and one ground net (VSS).

| VDD | VSS | Inputs | Outputs | Return lanes |
|---|---|---|---|---|
| 1 | 1 | 13 | 7 | 4 |

The return lanes stay at four. If the v2 slot offers more than 22 pads, the first extra pads go to a second VDD, then a second VSS. The slot's area may also shrink; recheck the area budget before assuming there is room for new logic.

Pins are declared in `info.yaml`; the pad map under `def/` is generated by the shuttle tooling and must not be edited by hand. Whether two pads may share a supply net is an open question with the organizers.

Energy is measured differentially on total chip current, on the VDD side, with the return lanes silenced during measurement loops. On v1, every measured run starts from reset, not from a `cont` loop (see the rationale). Report throughput and energy with the interface, P, drain mode, and batch size stated.

## Working style

- Make small, single-purpose changes on a feature branch. Run the relevant tests before reporting a change as done, and report the actual command output.
- Show diffs for review. Flag any change to index arithmetic, widths, or sign handling explicitly.
- Be concise and direct. Push back when a request conflicts with the contracts above.
- Do not use em dashes or en dashes anywhere: code comments, docs, commit messages, or chat. Use commas, colons, parentheses, or "to" for ranges.

