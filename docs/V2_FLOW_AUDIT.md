# DCIM v2: ASIC Flow Audit

This document walks every step from specification to silicon bring-up, and for each one records what the v1 run actually showed, what v2 changes, what could go wrong, and what to do about it.

It uses the same tags as `docs/V2_DESIGN_GUIDE.md`:

| Tag | Meaning |
|---|---|
| **Measured** | Read from the v1 RTL, netlist, flow logs, reports, or PDK files in this repository, or simulated. |
| **Decided** | Agreed and recorded. |
| **Proposed** | A mitigation written here that Karan has not yet accepted. |
| **Open** | Not decided. |
| **Estimate** | A v2 number. No v2 number is measured. |

The v1 run referred to throughout is `librelane/runs/RUN_2026-09-02_07-05-44`, whose metrics match `reports/metrics.json` and `final/metrics.json` exactly.

---

## 1. Findings that need a decision

These are the items from this audit that change the design or need action. Everything else is in the step-by-step sections.

| # | Finding | Tag | Why it matters |
|---|---|---|---|
| F1 | **The wordlines are driven by combinational logic.** In the synthesized v1 netlist every `WL` net comes from a tree of AND gates fed by the row counter flops and the write enable. The row address and the enable change on the same clock edge, and the macro's write is level-sensitive. | Measured (structure). The effect is not analyzed. | A decoder can produce a short pulse on the wrong wordline while its inputs settle. With data on the bitlines, a pulse that is wide enough writes the wrong row. Nothing in the flow checks for this: gate-level simulation runs without timing. |
| F2 | **The macro's write behavior with the activation input high is unresolved.** The repo's own characterization script (`ip/sram_32x8_9T/lib/gen_lib.py`) records that its write testbench held `A` high and the stored bit drifted to a mid-rail value before the write pulse, and that the intended idle level of `A` was never confirmed. | Measured (the note exists). The cell behavior itself is not verified here. | In v1, `A` follows the activation chain at all times. After a run at P below 8 the chain still holds data, so a weight reload can happen with `A` high on some rows. |
| F3 | **50 MHz is not reachable without pipelining.** The worst v1 path arrives at 19.95 ns at the slow corner. It runs from a chain flop through a bitcell (`A` to `RBL`), the adder tree, and the output combine, into an accumulator flop: 59 stages. | Measured | A 20 ns clock leaves about 0.5 ns before v2 adds the activation gate and BIST multiplexer to that same path. |
| F4 | **v1's outputs are not at the lowest pad drive.** `src/A07_dcim_top.sv` sets `PDRV0 = 1, PDRV1 = 0` with a comment saying "lowest drive strength". By the PDK timing library the lowest is `PDRV0 = 0, PDRV1 = 0`; v1's setting is the second lowest. | Measured | It is the baseline for v2's supply-bounce reasoning, and the comment is wrong. |
| F5 | **`make lint` does not lint the tapeout top.** It lints `dcim_top`. The flow lints `A07_dcim_top` (the pad wrapper) and reports 109 warnings there, 102 of them `TIMESCALEMOD`. | Measured | The wrapper carries every pad setting. In v2 it grows from 59 pins to about 111. |
| F6 | **Antenna checking does not cover the macro's inputs.** The flow warns that 304 macro pins have no antenna gate information. The macro LEF's signal pins also have no `DIRECTION` or `USE`. | Measured | Nets into `A`, `WL`, and `WBL` are not really antenna-checked. v2 adds logic on exactly those nets. |
| F7 | **The macro timing library only models `A` to `RBL`.** There are 256 arcs, all of that kind, each a single number per corner. There is no arc or constraint for `WL`, `WBL`, or `WBLB`. | Measured | Static timing cannot see the write path at all. Merge gate 5 (characterized library timing) is not met. |
| F8 | **v1 routing was not comfortable.** Global routing finished with congestion (total overflow 62), and detailed routing needed 27 iterations to clear 3,159 initial violations, at 34% utilization. | Measured | v2 adds cells and adds logic at the macro pins, where the congestion is likeliest. |
| F9 | **IR drop was analyzed without source locations.** The flow warned that `VSRC_LOC_FILES` was not set. The reported worst drop of 0.14 mV is therefore not meaningful. | Measured | Low concern for the core itself: the tool's power estimate is 12.6 mW, about 3.8 mA at 3.3 V, so even a poor 5 ohm supply path would drop under 20 mV. The real supply concern is bounce from the output pads (R6), which is a different effect and which this analysis cannot see. |
| F10 | **`reports/summary.md` is from an older run.** It shows a worst setup slack of 22.30 ns; `reports/metrics.json` shows 20.52 ns. | Measured | The two committed reports disagree. `metrics.json` matches the final run. |

F1 and F2 apply to v1 as submitted, not only to v2. Section 4 says what can be checked before the December submission.

---

## 2. What the v1 flow run shows

**Measured.** This is the baseline every v2 risk is judged against.

| Item | Value |
|---|---|
| Flow | `ClassicWithPadframeBridge`, 78 steps, block-level: the hardened design is `A07_dcim_top`, not the padring |
| Die and core | 1,110 x 1,110 um die, core about 910 x 910 um (823,516 um^2) |
| Clock | one, 40 ns |
| Setup, worst corner (max_ss_125C_3v00) | +20.52 ns slack; data arrival 19.95 ns |
| Hold, worst corner (max_ff_n40C_3v60) | +0.30 ns slack |
| Clock skew | about 0.31 ns |
| Cells | 14,323 standard cells excluding fill (5,919 of them tap cells); 492 flops, all one cell type (`dfsrtp`), all asynchronously reset in the RTL |
| Hold and repair buffers | 663 delay buffers; 1,612 timing-repair buffers in all |
| Utilization | 33.8% |
| Global routing | usage 11.6%, total overflow 62, finished with congestion |
| Detailed routing | 0 violations after 27 iterations, starting from 3,159 |
| Wirelength | 513,254 um |
| DRC (Magic and KLayout), LVS, antenna, XOR | all 0 |
| Max slew, cap, fanout violations | all 0 |
| Core-level pins | 59 |
| Tool power estimate | 10.7 mW (default switching activity; not a measurement) |

Flow warnings worth knowing about:

| Warning | Meaning |
|---|---|
| "Global routing finished with congestion" | F8. `GRT_ALLOW_CONGESTION` is on, so the flow continued. |
| "sram_32x8_9T has (304) input pin(s) without antenna gate information" | F6. |
| "'VSRC_LOC_FILES' was not given a value" | F9. |
| "The die area specified in FP_DEF_TEMPLATE is different than the design die area" | The template DEF uses 200 database units per micron. Both describe 1,110 um. It passed, but it must be re-checked when the template changes. |
| "109 Lint warnings found" | F5. Apart from the 102 timescale warnings, six come from the macro blackbox being declared twice or having no body, and one is the unconnected `tail_out`. |
| "found 2 floating nets" (VDD, VSS) | Expected before the power grid exists. |

---

## 3. Step by step

Each step lists what v2 changes, what can go wrong, and the mitigation. Risk is High, Medium, or Low.

### 3.1 Specification and interface contracts

**What v2 changes.** v1 has one clock, and its other eleven signal pins are all synchronous to it. v2 has four clocks and four interfaces.

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| The FPGA and the chip disagree about an interface detail that is still open (sync patterns, CRC polynomial, SPI mode, register map). | Medium | Write one interface specification before any interface RTL, and build the cocotb bus drivers from it, not from the RTL. | Proposed |
| The chip relies on things only the FPGA can guarantee. | Medium | Section 7 lists them in one place. | Decided (each item) |
| SPI mode is not chosen. Mode 0 means MISO changes on the falling clock edge, which needs falling-edge flops. | Low | Choose mode 0, the common default. | Open |

### 3.2 RTL design rules

**What v2 changes.** New rules exist only because of the new clock domains, the write path findings, and the gating.

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| F1: a wrong-row pulse on a wordline. v2 adds two more drivers of the write port (SPI and memory BIST), so it gets more exposed. | **High** | One write controller owns the write port. The wordline enable comes straight from a flop. The row address and the bitline data are stable for the cycle before, the cycle of, and the cycle after the enable. | Proposed |
| F2: writing with `A` high. | Medium | Already covered: the activation gate holds `A` at zero outside compute, and weights are only written when idle. State it as a rule: `A` is zero during every write. Memory BIST must follow it too. | Decided (gate, idle rule); Proposed (as a stated rule) |
| The activation gate's control glitches and lets `act_bp` through. In v1 the compute enable is a comparison on the state register, which synthesis may build from several gates. | Medium | A dedicated flop drives the gate, loaded from the next-state logic so it is not a cycle late. | Decided |
| A signal crosses clock domains without a synchronizer. Simulation will not show it. | **High** | Only three crossing structures are allowed: the async FIFO, the word handoff (used by both SPI and JTAG), and the two-flop reset release. Each lives in its own module with a fixed name prefix. A script checks that no other path crosses. | Proposed |
| Combinational logic sits between a source flop and a synchronizer, and glitches get captured. | Medium | A crossing signal leaves its domain straight from a flop. The check script enforces it. | Proposed |
| Reset is released at different times in different flops. v1 feeds `rst_n` from the pad to every flop with no release synchronizer. | Medium | Core and link domains: `RST_N` asserts immediately and is released through two flops on that domain's clock. SPI domain: `SPI_CS_N` high is the reset. JTAG: TMS high for five TCK cycles, plus `RST_N`. | Decided |
| Falling-edge flops (SPI MISO, JTAG TDO, staggered return lanes) create half-cycle paths that are easy to overlook. | Low | Keep them at the pin boundary only: one flop each, directly driving the output. | Proposed |
| The stale header comments mislead whoever writes the new logic. | Low | Fix them against `dcim_pkg.sv` before starting (already planned). | Decided |

### 3.3 Lint

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| F5: the wrapper is never linted by `make lint` or CI. | Medium | Add a second lint target with `A07_dcim_top` as the top, and run both in the fast CI job. | Proposed |
| The 102 `TIMESCALEMOD` warnings hide real ones. | Low | Make the timescale consistent, or waive that one warning class by name in the flow's lint step. | Proposed |
| New multi-clock RTL introduces latches or width mismatches. | Low | Keep `-Wall`. Waive by line with a reason, as the two existing waivers do. | Decided |

### 3.4 Functional verification

**v1 state (Measured).** 11 module testbenches, 11 module golden models, mutation tables, a top-level testbench. `make func-all` passes 11 of 11 after this session's fix. The top-level cycle counts were measured by a throwaway probe; no committed test pins them.

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| Golden models drift toward the RTL. | Medium | Write each new golden model from the design guide before the RTL exists. | Decided (rule in `CLAUDE.md`) |
| Tests run with one fixed clock alignment and never exercise the crossings. | **High** | A cocotb clock driver that randomizes phase and ratio between the four clocks, used by every interface test. | Proposed |
| A crossing bug that simulation cannot show. | **High** | The structural check script from 3.2. | Proposed |
| Corner cases in framing: bad CRC, truncated frame, overrun, resend, resynchronization after a failure. | Medium | One directed test per case, listed in the design guide section 5.10, plus random frame streams with injected errors. | Decided |
| Memory BIST passes on a good model and nobody checks that it fails on a bad one. | Medium | Inject faults into the macro model (stuck cell, coupled cells) and require the right row to be reported. | Decided |
| The compute BIST signature is taken from the RTL. | Medium | Take it from the golden model. | Decided |
| The v1 cycle counts drift unnoticed. | Low | Commit a top-level test that asserts them (350 and 343). | Proposed |
| "Coverage at or above v1" cannot be checked. | Low | Record the v1 coverage numbers in `docs/v1_baseline.md`. | Open |
| Tests share state. One already did: the unwritten-memory test only passed when run first. | Low | Fixed with `stage=-1`; the rule is in `CLAUDE.md`. | Decided |

### 3.5 Synthesis

**v1 state (Measured).** Yosys with the slang front end and `--keep-hierarchy`. All 492 flops map to one cell type (`dfsrtp`). The adder trees map to 740 majority cells and 740 XOR2 cells.

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| Synthesis merges or restructures synchronizer flops. | Medium | Keep each crossing structure in its own module (hierarchy is kept) and mark its flops to be preserved. Confirm in the netlist that the two flops are still two flops. | Proposed |
| The FIFO storage is inferred as something unexpected. | Low | It is 32 bits; write it as plain flops. | Proposed |
| The new front end rejects a construct. | Low | v1 already synthesizes with it. Keep new code in the same subset: packed arrays, generate loops, `always_ff`, `always_comb`. | Decided |
| Area grows past what the slot holds. | Medium | Section 6. Run a trial synthesis as soon as the register file exists. | Proposed |

### 3.6 Timing constraints

**v1 state (Measured).** `librelane/chip_core.sdc` creates one clock from the first entry of `CLOCK_PORT`, and applies the same input and output delay to every port relative to it. `config_core.yaml` names one clock port and one clock net.

**What v2 changes.** Everything in this file. This is the step most likely to be wrong silently, because a missing constraint does not produce an error.

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| The flow times paths between unrelated clocks, then either fails or inserts buffers to "fix" them. | **High** | Four `create_clock` statements, and the four declared asynchronous to each other. | Proposed |
| Declaring the clocks asynchronous removes every check on the crossings, including the Gray-coded FIFO pointers, whose bits must not arrive more than a cycle apart. | Medium | Add a maximum-delay constraint on the crossing paths, set to one period of the faster clock. Confirm the timing tool in this flow honors it; if not, check the crossing path delays by hand in the report. | Open |
| The link inputs are constrained against the wrong clock. | Medium | `LINK_D` input delays are relative to `LINK_CLK`, with both a minimum and a maximum, so the tool balances the data against the clock tree delay. | Proposed |
| SPI and JTAG pins are constrained against the core clock. | Medium | Each interface's pins are constrained against its own clock. MISO and TDO are launched on the falling edge. | Proposed |
| Return lane output timing is over-constrained. | Low | The FPGA deskews each lane, so the constraint only needs to bound lane-to-lane skew. | Proposed |
| `SPI_CS_N` used as an asynchronous reset has no timing relationship the tool knows. | Low | The FPGA holds `SPI_CS_N` low for a stated time before the first clock edge. Put the number in the interface specification. | Proposed |
| The configuration names one clock. | Medium | `CLOCK_PORT` and `CLOCK_NET` become lists. Confirm the clock tree step builds all four. | Open |

### 3.7 Floorplan and pins

**v1 state (Measured).** Fixed die, pins placed from the organizers' template DEF (`def/A07/project_defs/A/A07_A.def`, 59 pins on Metal2). The four macros are placed by hand.

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| The pin list changes and the template does not. The template is generated by the organizers from `info.yaml`. | **High** | Declare the v2 pins in `info.yaml` early and get the new template before floorplanning. v2 has about 111 core-level pins: 7 outputs x 10 pad terminals, 13 inputs x 3, and 2 supplies. (The same formula gives v1's 59.) | Open (depends on the organizers) |
| The slot's size or pad count changes. | Medium | Section 6 and the guide's open items. | Open |
| The pad map is edited by hand. | Low | It is generated. `CLAUDE.md` forbids editing it. | Decided |
| New logic at the macro pins has nowhere to go. The macro is 44 x 181 um with `A` and `WL` pins on Metal2 and 256 `RBL` pins on Metal4. | Medium | Keep the macro halos. Place the gate and multiplexer cells for `A` near the `A` pin edge. Check after a trial placement. | Proposed |
| Four clock inputs need clean edges. | Low | Declare all four as `input_schmitt` in `info.yaml`, as v1 does for `clk`. | Proposed |

### 3.8 Power grid

**v1 state (Measured).** One supply, one ground. Core ring with vertical straps on Metal2 and horizontal on Metal3. A custom flow step (`Odb.AddPadframePowerBridge`) connects the ring to the supply pins at the die edge. Its own notes say a hardcoded target that passed one run failed the next, because the ring geometry is not deterministic, which is why it queries the geometry live.

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| The supply pin positions change with the new template and the bridge lands in the wrong place. | Medium | Re-run and inspect the bridge step first, before anything else in the new floorplan. | Proposed |
| F9: IR drop is not really analyzed. | Low | The core draws only a few milliamps, so the true figure is small. Give the flow the real supply entry points (`VSRC_LOC_FILES`) anyway, so signoff reports a number that means something. | Proposed |
| Supply bounce from seven outputs on one supply pair. The block-level flow cannot see it: the pads are outside the block. | **High** | Low pad drive, slow slew (`SL = 1`) where the rate allows, return lanes staggered by half a cycle, return lanes silenced during measurements. Ask the organizers about a second supply pad if the pad count rises. | Decided (measures); Open (how much is enough) |
| The power grid blocks routing near the macros. | Low | Unchanged from v1, which routed. | Measured |

### 3.9 Placement

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| The target density is set for v1 (35%). | Low | Raise it to match the v2 cell area once a trial synthesis gives the number. | Proposed |
| The two flops of a synchronizer are placed far apart, wasting settling time on wire delay. | Low | At 25 MHz the margin is large. Check their placement in the result; constrain it only if they are far apart. | Proposed |
| Link input flops are placed far from the link pins, adding skew between lanes. | Medium | Check after trial placement. | Proposed |

### 3.10 Clock tree

**v1 state (Measured).** One tree, 213 clock buffers, skew about 0.31 ns.

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| The flow builds a tree for only one clock. | Medium | Same as 3.6: list all four and confirm in the log that four trees were built. | Open |
| The three small domains have only a few dozen flops each and the tool over-buffers them. | Low | Inspect the result. | Proposed |
| More hold fixing. v1 already needed 663 delay buffers on its shift chains. v2 keeps the chains and adds three clocks. | Medium | Expect it. Watch the delay buffer count and the hold slack in each domain. | Proposed |
| Insertion delay on `LINK_CLK` moves the sampling point relative to the data. | Medium | The input delay constraints in 3.6 make the tool compensate. Report the final delay so the FPGA can center its data. | Proposed |

### 3.11 Routing

**v1 state (Measured).** F8.

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| v2 does not route. More cells, and new logic exactly at the macro pins. | **High** | Do a trial place and route right after the first two build steps (generate loop and activation gate), long before the interfaces exist, to see how the congestion moves. If it is tight, the levers are: move the macros apart, lower density near them, and as a last resort the adder tree sharing that the rationale deferred. | Proposed |
| The flow hides congestion because `GRT_ALLOW_CONGESTION` is on. | Medium | Read the congestion report after every run, not just the final violation count. | Proposed |

### 3.12 Antenna

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| F6: nets into the macro's inputs are not checked. | Medium | Add `DIRECTION`, `USE`, and gate area to the macro LEF pins so the checker can do its job. This is a change in `ip/`, which is Karan's. Until then, check the `A`, `WL`, and `WBL` nets by hand: keep them short and on low metal. | Proposed |
| More long nets from the register file to the write port and the result registers. | Low | The flow's repair step handled v1 with no diodes. Watch the count. | Measured |

### 3.13 Timing signoff

**v1 state (Measured).** Nine corners, all met. F3 and F7.

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| F3: the clock target. | Medium | Stay at 25 MHz. It also resolves the pad drive conflict. At 25 MHz the compute path has about 20 ns to absorb the gate and the multiplexer. | Proposed |
| F7: the write path is invisible to static timing. | **High** | The write controller rule in 3.2 makes it correct by construction. Add the missing library arcs when the write characterization is trusted. | Proposed |
| The macro timing is one number per corner, with no dependence on load or input slew. | Medium | The values come from SPICE, which is better than the earlier placeholders. A table would be better still. This is merge gate 5. | Open |
| The macro's parasitic file has no resistance. The repo's notes say extraction found none on the signal routes. | Low | Record it as a known limit of the model. | Measured |
| Crossing paths are reported as violations, or not reported at all. | Medium | 3.6. | Open |

### 3.14 Physical signoff

**v1 state (Measured).** DRC, LVS, antenna, and XOR all clean.

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| A Magic DRC error does not stop the flow (`ERROR_ON_MAGIC_DRC` is off). | Medium | Read the count after every run. It is 0 today. | Measured |
| The density deck is excluded from the main DRC run and run separately. | Low | Confirm both ran. | Measured |
| LVS for the organizers' top level uses `lvs_config.json` and the macro's LVS netlist. | Low | Unchanged in v2: the macro is the same. | Measured |

### 3.15 Gate-level simulation

**v1 state (Measured).** The gate-level harness simulates `final/nl/A07_dcim_top.nl.v` with the standard cell models and the behavioral macro. It does not use the timing files, although `final/sdf/` holds one per corner.

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| F1 cannot be seen without timing. | **High** | Run one timing-annotated gate-level simulation of a weight load. The behavioral macro treats any wordline pulse as a write, so it is a strict test. If the simulator cannot annotate timing, compare the earliest and latest arrival times on the 32 wordline nets in the timing report instead. | Proposed |
| With four clocks, unknown values spread from flops that are not reset. | Medium | Reset every flop in the crossing structures. | Proposed |
| The macro powers up unknown, so BIST must write before it reads. | Low | The march test starts with a write pass. | Decided |

### 3.16 Macro views

**Measured.** The macro itself does not change in v2. Its views have gaps that v2 depends on more than v1 did.

| View | State | Gap |
|---|---|---|
| Layout and LVS netlist | Clean in v1 | None |
| Abstract (LEF) | 338 pins, blockage on Metal1 to Metal4 | Signal pins have no direction, no use, no gate area (F6) |
| Timing library | Three corners, SPICE-derived | `A` to `RBL` only, single values (F7) |
| Parasitics | Coupling capacitance only | No resistance |
| Behavioral model | Level-sensitive write, powers up unknown | Any wordline pulse writes, which is the conservative choice |
| Read mapping to physical ports | Not verified | Merge gate 4 |

### 3.17 Pads

**v1 state (Measured).** Three outputs, all at `PDRV0 = 1, PDRV1 = 0`, fast slew. `clk` has no pull, `rst_n` and `P_minus1` have pull-ups, and the other inputs have pull-downs. The pad control pins are driven by our design.

From the PDK timing library, output pad into 15 pF:

| Setting | Typical corner: delay, rise time | Slow corner: delay, rise time |
|---|---|---|
| `PDRV0 = 0, PDRV1 = 0` (lowest) | 5.5 ns, 5.9 ns | 10.2 ns, 10.7 ns |
| `PDRV0 = 1, PDRV1 = 0` (v1's setting) | 4.1 ns, 3.0 ns | not extracted |
| `PDRV0 = 0, PDRV1 = 1` | 3.6 ns, 2.0 ns | not extracted |
| `PDRV0 = 1, PDRV1 = 1` (highest) | 3.3 ns, 1.6 ns | 6.3 ns, 2.9 ns |

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| The drive setting is chosen once at tapeout and turns out wrong for the board. | Medium | Make drive and slew for the return lanes register-controlled, with a safe default. The control pins are already ours to drive. | Proposed |
| An unconnected input floats. | Low | Pull-downs on the link inputs, pull-ups on `SPI_CS_N` and TMS. Decide the pulls for `SPI_SCLK`, `SPI_MOSI`, TCK, and TDI too: pull-down on the clocks is the safe choice. | Decided (first four); Proposed (rest) |
| MISO and TDO fight another driver. | Low | Drive them only during a transaction, through the pad's output enable. | Decided |

### 3.18 Submission and integration

**Measured.** `info.yaml` says data is pulled from the `main` branch. The organizers build the padring and the pin template from its pin list. The integration LVS reads `verilog/A07_dcim_top.pnl.v`, `gds/A07_dcim_top.gds`, and the macro's LVS netlist.

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| v2 must be on `main` to be submitted, and `main` only takes v2 after all five merge gates. | **High** | Work backward from the v2 shuttle's pull date. Gates 4 and 5 (read mapping, library timing) are analog work with no date yet. | Open |
| The v2 shuttle's rules differ from this one's. | Medium | The three organizer questions, plus area and pad count. | Open |
| The generated outputs committed to the repo drift from the source. | Low | Regenerate them from one clean run and commit them together. Fix the stale `reports/summary.md` (F10) the same way. | Proposed |

### 3.19 Bring-up and measurement

| Risk | Level | Mitigation | Tag |
|---|---|---|---|
| The chip is dead and nothing says why. | Medium | The order of checks needs no working interface at first: STATUS pin, then JTAG IDCODE (which needs no core clock), then SPI, then the link. | Decided |
| BIST fails because the read mapping is wrong, not because cells are bad. | Medium | BIST never blocks operation. Row readback through the register file shows the actual pattern. Closing merge gate 4 removes the risk. | Decided |
| Energy numbers are contaminated. | Medium | v2: return lanes silenced, compute-gate comparison. v1: every measured run starts from reset. | Decided |
| The energy comparison is made at different pad settings. | Low | Report the pad drive and slew with every energy number. v1's are fixed at the second-lowest drive, fast slew. | Proposed |

---

## 4. What can be checked on v1 before the December submission

`CLAUDE.md` allows the `v1.0` tag to move once before submission. F1 and F2 are about the design as it stands today, so they are worth a look while that is still possible. Neither is known to be a real fault.

| Check | How | What it would show |
|---|---|---|
| F1: wordline pulses | A timing-annotated gate-level simulation of the weight load, or the spread of arrival times on the 32 wordline nets from the timing report. | Whether a wrong-row pulse can occur, and how wide. |
| F2: write with `A` high | Re-run the write testbench with `A` low, then with `A` high, at the three corners. | Whether the cell writes correctly in both cases, and so whether a weight reload after a run at P below 8 is safe. |

If F2 turns out to matter, v1 has a workaround that needs no design change: reset before every weight load, which empties the activation chain and puts `A` at zero. The first load after power-up is already in that state.

v1 has no way to read weights back, so neither problem could be seen directly in silicon. They would show up only as wrong results.

---

## 5. Risk register

The main items from section 3 in one list, most serious first.

| ID | Risk | Level | Mitigation | Status |
|---|---|---|---|---|
| R1 | Wrong-row wordline pulse (F1) | High | Single write controller, enable from a flop, address and data stable around it; one timing-annotated simulation | Proposed |
| R2 | Undetected clock-domain crossing bug | High | Three allowed structures, structural check script, randomized clock phases in every interface test | Proposed |
| R3 | Wrong or missing timing constraints for four clocks | High | Rewrite `chip_core.sdc`; confirm four clock trees; decide how crossings are bounded | Open |
| R4 | v2 does not route | High | Trial place and route after build step 2; read the congestion report every run | Proposed |
| R5 | Write path invisible to timing analysis (F7) | High | Correct by construction (R1); add arcs when characterization is trusted | Proposed |
| R6 | Supply bounce with seven outputs on one supply pair | High | Low drive, slow slew, stagger, silence during measurement; register-controlled drive | Decided in part |
| R7 | Pin template and padring depend on the organizers | High | Declare v2 pins in `info.yaml` early | Open |
| R8 | v2 must pass five merge gates before `main`, and submission reads `main` | High | Schedule backward from the pull date | Open |
| R9 | Writing with `A` high (F2) | Medium | `A` is zero during every write | Decided in part |
| R10 | 50 MHz target (F3) | Medium | Stay at 25 MHz | Proposed |
| R11 | Macro input nets not antenna-checked (F6) | Medium | Complete the LEF pin properties; hand-check meanwhile | Proposed |
| R12 | Wrapper not linted (F5) | Medium | Second lint target in CI | Proposed |
| R13 | Area exceeds the slot | Medium | Trial synthesis; section 6 | Proposed |
| R14 | IR drop not analyzed (F9) | Low | Supply the source locations; the core current is only a few milliamps | Proposed |
| R15 | More hold fixing across four domains | Medium | Watch buffer count and per-domain hold slack | Proposed |
| R16 | Link input sampling point shifts with clock tree delay | Medium | Input delay constraints; report the delay to the FPGA side | Proposed |
| R17 | Pad drive fixed at tapeout | Medium | Register-controlled drive and slew | Proposed |
| R18 | BIST fails on a mapping error | Medium | BIST never blocks; close merge gate 4 | Decided |
| R19 | Second-layer activations cannot pass the photonic module | Medium | Confirm a pass-through path, or accept SPI for that layer | Open |

---

## 6. Area and flop budget

**Estimate.** This is a count by hand, to be replaced by a trial synthesis. It is here so the order of magnitude is known before the slot size is.

| Block | New flops, roughly | Made up of |
|---|---|---|
| Register file | 150 | 4 biases x 22, shift, P and its two travelling copies, mode bits, flags, two 16-bit counters |
| Link receive | 85 | 4 input flops, 8 x 4-bit FIFO, pointers and their synchronizers, frame counter, CRC, sequence |
| Compute BIST | 76 | 32-bit pattern generator, 32-bit signature, counters |
| JTAG | 65 | TAP state, instruction register, a 41-bit data register, handoff |
| SPI | 50 | 32-bit shift register, counters, handoff |
| Link transmit | 25 | frame counter, CRC, sequence copies |
| Memory BIST | 25 | row, march step, background, first failing row |
| STATUS and timeout | 38 | heartbeat divider, BIST timeout |
| Control and resets | 20 | stage valid bits, gate control, drain width counter, reset release |
| **Total** | **about 530** | |

v1 has 492 flops, so v2 has roughly twice as many: about 1,000.

In area terms: v1's flops average about 81 um^2 each (39,961 um^2 for 492), so the new flops add about 43,000 um^2. New combinational logic (four 22-bit adders and shifters for requantize, on the order of a hundred multiplexers and gates at the macro and chain, decoders, CRC) might add 15% to 25% of v1's 135,635 um^2. With buffers scaling along, v2's cells would be roughly 350,000 to 380,000 um^2 against v1's 278,000.

In v1's 823,516 um^2 core that is about 43% to 46% utilization, up from 34%. That fits on area. If the core shrank by a quarter, utilization would be about 57% to 62%. Given that v1 already showed congestion at 34%, that should be treated as not fitting until a trial run says otherwise.

---

## 7. What the FPGA must guarantee

The chip's correctness depends on these. They belong in the interface specification.

| # | Requirement | Why |
|---|---|---|
| 1 | CLK comes from the FPGA. | The return lanes rely on being the same frequency as the FPGA's own clock. |
| 2 | LINK_CLK runs continuously while the link is enabled and is never faster than CLK. | The link FIFO cannot overflow, and the framing logic always has clock edges. Contract 16. |
| 3 | SPI_SCLK is never faster than CLK. | The core must finish each word before the next arrives. |
| 4 | `SPI_CS_N` is low for a stated time before the first SPI clock edge and stays low for the whole transaction. | It is the SPI domain's reset. |
| 5 | Frames are paced at the per-vector period for the current mode: about 22 cycles at P = 1 raw, about 75 at P = 8. | Sending faster causes overruns. |
| 6 | A missing sequence number is resent. | It is the only recovery for a bad or dropped frame. |
| 7 | Each return lane is deskewed by its own sync word before the CRC is checked. | The four lanes can arrive with different delays. |
| 8 | Weights, P, bias, and shift are written only when the status register reads idle. | Writes while busy are ignored. |
| 9 | `RST_N` is held low for several cycles of the slowest running clock, and released while the interfaces are idle. | Every domain must see reset before it is released. |
| 10 | For v1 energy runs only: reset before every measured run. | Otherwise the load switches differently at P = 1 and P = 8. |
