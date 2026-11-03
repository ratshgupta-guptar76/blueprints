# DCIM v2 verification plan

**Draft 0.2, 2026-10-14.** How v2 is shown to meet `docs/V2_SPEC.md`, what "100% coverage" means here, how far it has got, and what is left. The submission deadline is 2026-12-14.

The plan comes before the RTL on purpose: building the traceability below is what finds the places the spec is silent (section 6). The spec is not final until those are closed.

| Document | What it is |
|---|---|
| `docs/V2_SPEC.md` | What the chip must do at its pins, cycle by cycle |
| `model/chip_v2/` | The pin-level model of the spec: the reference every test compares against |
| `model/chip_v2/requirements.py` | Every requirement, with the checks that test it |
| `docs/V2_REQUIREMENTS_MATRIX.md` | Generated from the line above: which requirements are covered, by what |
| This document | The method, the coverage targets, the test list, and the gaps |

---

## 1. What "100% coverage" means

No single number captures "verified", so there are six kinds of coverage. Each has a target of 100%. Each also has a rule for what may be excluded, and an exclusion needs a written reason that someone else can check.

| # | Kind | Measured by | Target | Exclusions allowed |
|---|---|---|---|---|
| C1 | **Requirement coverage.** Every requirement has at least two kinds of evidence: a directed check, a random invariant, a fault caught at the pins, or (inside the chip) a module test, assertion, or proof. | `verify matrix` | 100% of requirements | Physical requirements, which the flow checks (section 9) |
| C2 | **Functional coverage.** Every bin of the coverage model in section 5 is hit at least once. | Collectors on the model, then on the RTL | 100% of bins | A bin that is impossible, with the proof |
| C3 | **Code coverage** of the v2 RTL: line, toggle, and every state and transition of every state machine. | Verilator coverage | 100% | Code that cannot be reached by design (a `default` of a fully decoded `case`), each one listed |
| C4 | **Fault coverage.** Every fault in the model's fault list, and every RTL mutation in each module's table, is caught. | `verify mutants`, `make func-mut-all` | 100% caught | None. A fault that cannot be caught at the pins must be caught inside (C1). |
| C5 | **Crossing coverage.** Every path between clock domains in the netlist is one of X1 to X5, through a proper synchronizer. | A netlist script (section 8) | 100% of paths | None |
| C6 | **Assertion coverage.** Every assertion in the RTL has fired its cover at least once and never failed. | Simulation | 100% | None |

Two things 100% here does **not** promise. It does not prove the spec is what the demo needs: that is the job of the photograph runs (PERF-03). And it does not cover the analog macro itself: the bitcell, read margins and write margins are Karan's SPICE work, and in simulation the macro is a behavioural model. Merge gates 4 and 5 and the silicon bring-up (section 11) are where those are checked.

## 2. Where the answers come from

Every expected value in every test comes from one of two places, and never from the RTL:

1. **The model,** `model/chip_v2/`, written from the spec. Tests at the pins compare the chip with it edge for edge.
2. **Plain arithmetic** written separately from the model, for the numbers that matter most: W^T a (`fpga.reference`), requantize (`chip.requant`), the self-test signature (`chip.cbist_signature`), and for module tests the golden models in `cocotb/golden/`, written from the spec before each module's RTL.

**The authorship risk.** Claude is writing both the RTL and most of the tests. A misreading of the spec could go into both and agree with itself. Four things work against that:

- The model and its checks (155 now) existed before any v2 RTL.
- The fault list shows that the checks fail when the behaviour is wrong (C4).
- The random traffic was not written with any implementation in mind.
- Karan reviews every requirement in `requirements.py` against the spec. That review is the step no tool replaces.

## 3. Levels

| Level | What is tested | Tool | State today |
|---|---|---|---|
| **L0** | The spec itself, through the model | Python: scenarios, pin traces, fault list, random traffic, traceability | Built. Results in section 4. |
| **L1** | Each RTL module against its golden model | cocotb, Icarus and Verilator, mutation tables | v1 modules only. v2 modules come with their RTL. |
| **L2** | The whole chip at its pins against the model | cocotb: replay of every model trace, random co-simulation, directed tests | Testbench built and proved on a stand-in (`cocotb/v2/`). Waits for the v2 top level. |
| **L3** | The synthesized and laid-out netlists | The L2 replay, without and then with timing | v1 flow only |
| **L4** | Things simulation cannot show | Lint, crossing check, formal proofs, timing at every corner, DRC, LVS, antenna | v1 flow only. Crossing script and proofs to be written. |
| **L5** | The RTL at full speed against the real FPGA host code | The core on the Nexys A7, the macro as a behavioural model | **Proposed.** It tests the FPGA software before silicon exists. |
| **L6** | The silicon | Bench, with the FPGA | April to June 2027 |

### L0, the spec through the model (built)

| Command | What it shows | Result |
|---|---|---|
| `python3 -m model.chip_v2` | 155 directed checks, both demo photographs through the pins | 155 of 155 |
| `python3 -m model.chip_v2.verify replay` | Every scenario as a pin trace; a fresh model reproduces it | 2,140 traces, 3,456,232 cycles, all exact |
| `python3 -m model.chip_v2.verify mutants` | 143 faults; each must change the pins somewhere in the traces | 139 caught; 4 are invisible at the pins (WP-02's row read, BIST-02, two of RST-04), none missed |
| `python3 -m model.chip_v2.verify random N` | Random legal and hostile traffic, seven invariants (section 4) | 300 legal and 1,800 hostile seeds, all clean |
| `python3 -m model.chip_v2.verify matrix` | Every requirement traced to its evidence; no check or fault left untraced | Section 4 |
| `python3 -m model.chip_v2.verify coverage` | The functional coverage model of section 5 | 1,036 of 1,036 reachable bins; 32 impossible, with reasons |

### L1, modules (with the RTL)

For each v2 module, before its RTL is written:

1. **A golden model** in `cocotb/golden/`, from the spec.
2. **A testbench** in `cocotb/functional/`. It needs directed cases, edge values, random cases, and an X-propagation test that runs first. Any test that claims to be exhaustive asserts its iteration count.
3. **A mutation table** in `scripts/mutation/tables/`.
4. **Assertions** in the RTL for the module's invariants (section 7), each with a cover.

| Module (planned) | Tests that matter most |
|---|---|
| Link receive domain and the FIFO | Gray pointers, full and empty at every pointer value, the three-state handshake, overflow |
| Frame receiver | Every state, every transition, every way out of each state (link off, act_spi, CLEAR bit 2, reset) |
| CRC-8 (receive and send) | Every symbol value from every CRC value: 16 x 256 = 4,096 cases, exhaustive |
| Activation chain, four lanes | Both load modes, every row, the joined chain for SPI and JTAG |
| Datapath (v1 modules, P from the vector) | Already covered in v1; add P from the vector and the plane count |
| Requantize | Exhaustive over the shift, boundary values of r + bias, random |
| Transmitter | Frame layout at every width, back-to-back frames, tx_silence |
| Register file and busy rule | Every register: reset value, width, access, reserved bits; every guarded write against every busy cause |
| SPI slave | Every bit count at which chip select can rise; reads of every width |
| Write controller | Three cycles, the gate, a request while busy, an abort in each state |
| Self-test (memory and compute) | The march step by step against the golden model, faults injected by force, timeouts by force |
| JTAG TAP and the X4 crossing | All 32 state transitions, every IR code, ready bit timing |
| Link handshake (core side) | All transitions, enable written during Closing |

### L2, the chip at its pins

- **Replay.** `cocotb/v2/chip_v2_tb.py` replays every model trace and requires the same output on every pin at every sampling edge. It is proved today: on Icarus, 411 traces match with the model behind a stand-in, and 10 broken stand-ins are all reported. Pointing it at the RTL takes `CHIP_V2_TOP` and `CHIP_V2_SOURCES`.
- **Random co-simulation.** The same random traffic as L0 driven into the RTL, with the model running alongside as the reference. The stand-in's `StandIn` class is already a model that follows the pins. The new part is a cocotb version of the traffic generator.
- **Directed tests** for what the replay cannot carry: injected cell faults through `force`, X-propagation from an unwritten array, and the planned items in the matrix.
- **Coverage:** Verilator line and toggle coverage of the whole chip, and the functional coverage collectors (section 5) on the RTL.

### L3, netlists

1. The L2 replay on the synthesized netlist, zero delay. This checks synthesis did not change behaviour.
2. The quick trace set on the laid-out netlist with timing at the slow and fast corners. This is the one place a glitch or a crossing timing fault can show in simulation.

v1's gate-level simulation ran without timing. v2's must not stop there.

### L4, static and formal

See sections 8 and 9.

## 4. Where it stands (measured today)

From `verify matrix` (full table: `docs/V2_REQUIREMENTS_MATRIX.md`):

| Status | Count | Meaning |
|---|---|---|
| Covered | 100 | At least two kinds of evidence, all passing |
| One method | 3 | Only one kind of evidence: PERF-01 to 03, measurements, accepted as one method |
| Needs L1 | 5 | Cannot be seen at the pins: needs module tests, assertions, or proofs |
| Flow | 6 | Checked by the physical flow and pad scripts |
| Gap | 0 | |
| **Total** | **114** | |

Draft 0.1 of this plan had 102 requirements: 72 covered, 18 with one method and RX-12 with nothing. Work list items 2 and 3 (section 13) added 12 requirements for the gaps written into the spec, and closed the 18 and RX-12 as the table below says.

The audit also found, and fixed, 5 checks and 1 fault that no requirement listed. Now no check or fault is untraced and no reference is broken.

The seven random invariants:

| Invariant | Holds in |
|---|---|
| Every frame back, in order, exactly right | legal runs |
| No counter or sticky flag moves | legal runs |
| Every result is W^T a for what the chip held when the vector started | hostile runs |
| Weights never change under a running vector | hostile runs |
| No crossing read while changing, no write collision, gate closed during writes, no FIFO entry read twice | hostile runs |
| After the abuse the chip comes back without a reset | hostile runs |
| After a reset, a used chip matches a fresh one pin for pin | hostile runs |

### The 18 that had one method, and what closed each (done 2026-10-14)

| ID | What was missing | What closed it |
|---|---|---|
| CLK-07 | Directed checks only | Fault: IDCODE comes through the core clock domain |
| RST-01 | Random only | Directed (`reset`): RST_N asserted with each output high (LINK_TX, MISO, TDO, STATUS) and in 2 more states; every output 0 at once and throughout. The L2 random version stays planned. |
| RST-02 | A fault only | Directed (`reset`): release at 8 phases of CLK; STATUS first goes high on edge 2 + 32,768 every time |
| RST-03 | Directed only | Fault: the SPI domain needs two SCLK edges to leave reset |
| RST-04 | Random only | Directed (`reset`): after a reset from 6 states the chip answers as a fresh one (dummy byte, first JTAG capture, every register). Faults: the read-data and JTAG answer registers not reset. The SPI word and JTAG request registers not reset are invisible at the pins (overwritten before use) and marked inside. |
| LNK-03 | One directed check | Directed (`recover`): the link switched off and on during a recovery wait; the next frame is taken. Fault: the receiver not sent to hunt when the link goes down. |
| RX-05 | One directed check | Fault: one idle symbol needed between frames. (Random legal runs never send frames with no gap, because the shortest period is longer than a frame except with the lanes silent.) |
| PIPE-10 | Directed only | Fault: the transmitter takes its width from P while draining |
| TX-02 | Directed only | Random legal listed; fault: raw width 12 + P |
| TX-05 | Random only | Directed (`regs`): LINK_TX 0 before, between and after frames. Fault: LINK_TX holds its last bit. |
| BIST-01 | Directed only | Directed (`reset`): BIST_STAT read throughout the reset self-test goes 0000, 0001, 0101. Fault: the compute test first. |
| BIST-07 | One directed check | Directed (`reset`): every readable register read while each test runs. Fault: ID reads 0 during a test. |
| JT-08 | One directed check | Directed (`tap`): scans that take all 32 transitions, each judged at TDO or by what the scan does. Faults: four wrong transitions. The L1 test stays planned. |
| ENV-03 | One directed check | Faults listed: recovery at 71 and at 73 (the 72 check catches both). Note: the hostile recovery does not exercise rule 3, because switching the link off also ends the wait. |
| ENV-06 | Directed only | Random legal listed (lane delays 0 to 3 cycles) |
| PERF-01, 02, 03 | Directed only | Accepted as one method: they are measurements. The L2 RTL run of the same scenarios is the second. |
| RX-12 | Nothing | Scenario `sync`: 1,500 corrupted syncs, every false frame ends as a receiver written from section 4 says; 400,000 random bodies through the CRC. Fault: frame type not checked. It corrected the spec (section 13 row 22). |

## 5. Functional coverage model (C2)

The checks above say a behaviour is right where it was tested. The coverage model says it was tested in every situation that matters. It is collected on the model during L0 runs and on the RTL during L2 runs. Every bin must be hit.

| Point | Bins | Count |
|---|---|---|
| FC-01 frame outcome | P (1 to 8) x return (raw, requantized, silent) x outcome (accepted, overrun, CRC fail) | 72 |
| FC-02 frame type | type 0, 1, 2, 3 | 4 |
| FC-03 frame spacing | for each P: at the minimum, minimum + 1, one too close, back to back | 32 |
| FC-04 receiver interrupted | receiver state (hunt, header 1, header 2, payload, CRC 1, CRC 2, skip, recover) x cause (link off, act_spi, CLEAR bit 2, reset) | 32 |
| FC-05 guarded write | register (9 guarded) x master (SPI, JTAG) x what makes the chip busy (none, loading, loaded, computing, result waiting, burst, row write, self-test, activations shifting) | 162 |
| FC-06 same-edge race | write check and first payload symbol: write a cycle early, same edge, a cycle late, for MODE, P, START and WEIGHTS | 12 |
| FC-07 every register | every address 0x00 to 0x7F x read or write x master | 512 |
| FC-08 SPI cut short | chip select rising after each bit count 1 to 16 of the first two bytes, and mid-row in a burst | 17 |
| FC-09 clock ratio | LINK_CLK / CLK in (1.0, just above 1, 1.1 to 2, above 2); SCLK / CLK the same; TCK / CLK (4, 4 to 8, above 8) | 11 |
| FC-10 crossing alignment | for X1, X2, X4 and X5: the event lands in each eighth of the CLK period, and inside the metastability window | 36 |
| FC-11 link state | Down to Up, Up to Closing, Closing to Down, enable written again during Closing, LINK_CLK stopped during Closing | 5 |
| FC-12 write controller | a request in each of its four states; an abort in each state | 8 |
| FC-13 self-test | memory and compute x (pass, fail, aborted in write phase, aborted in read phase, timed out) | 10 |
| FC-14 STATUS pin | low, heartbeat, high, DONE; and each change between them that can happen (low to heartbeat, to high, to DONE; heartbeat to DONE; high to DONE) | 9 |
| FC-15 requantize | r + bias negative, zero, in range, above 255 x shift (0, 1 to 14, 15) x bias sign | 24 |
| FC-16 results | each lane at its most positive and most negative raw value for each P | 64 |
| FC-17 counters | 0, 1, 254, 255 and held at 255, for each of the three | 15 |
| FC-18 TAP | all 32 state transitions; every IR code | 40 |
| FC-19 JTAG and SPI tie | a JTAG write one cycle before, on, and one cycle after an SPI byte | 3 |
| **Total** | | **1,068** |

Some bins can only be hit in the hostile runs (FC-04, FC-06, FC-19) and some only by forcing (FC-13 timeouts). A bin no test can hit is either impossible, and gets a proof, or a gap in the stimulus, which gets a test.

**Measured (2026-10-14).** `python3 -m model.chip_v2.verify coverage` collects these bins on the model (`model/chip_v2/coverage.py`, which watches each bench from outside and changes nothing) and writes `docs/V2_FUNCTIONAL_COVERAGE.md` (generated). The first run, on the scenarios that existed then and 40 random seeds of each kind, hit 609 bins. Scenario `cover` was then written to close the rest, with checks of its own (13). Now:

- **1,036 of 1,036 reachable bins hit (100%)**, by the directed scenarios alone; random traffic adds repetitions, not bins.
- **32 bins are impossible by design**, each with its reason in the generated report: CLEAR bit 2 acts only while a vector loads; a loading vector makes the MODE write that would switch the link off or set `act_spi` a refused write; SPI cannot write during its own burst; an SPI register write is checked 8 or more cycles after its command byte stopped the self-test; ACT over JTAG needs `act_spi`; at P = 2 one cycle under the minimum spacing would overlap two frames; and r + bias shifted by 15 cannot exceed 63.
- **Two forced bins**, the self-test timeouts, are hit by replacing a test with one that never ends, in the coverage run only: no trace of it could be replayed on RTL. On RTL they are BIST-04's L1 test.
- **Sweeps, not luck.** Where a bin is a timing window of one cycle (a write landing while a vector is loaded, or computing), the sweep lands the write on every cycle of a window longer than the pattern's period, so the bin cannot be missed by a change of seed.

## 6. Gaps in the spec found by this audit

Writing a requirement for every sentence showed where the spec does not say what happens. Where the model already does something sensible, the fix is to write it down. Where it does not, the decision is yours. The "text only" items are written into spec draft 0.4, each with a requirement (SPI-14 to 18, TX-06, TX-07, JT-09, JT-10, ENV-08 to 10, and additions to SPI-02, JT-03 and JT-06), a check in scenario `regs`, and a fault; S23 is a statement with no behaviour to test. The "Yes" items wait for you.

| # | Section | The spec does not say | Model today | Proposed | Yours? |
|---|---|---|---|---|---|
| S1 | 1 | Whether RST_N has a pull. Floating at power-up, the chip could start out of reset with the FPGA unplugged | None | Pull-down: held in reset until driven | **Yes** |
| S2 | 1 | Pulls on TDI and TCK. IEEE 1149.1 asks for a pull-up on TDI | None | TDI pull-up. TCK pull-down. | **Yes** |
| S3 | 1 | Output drive strength and slew (flow audit F4, risk R17) | Not modelled | Lowest drive that meets section 2's timing, set in the pad wrapper, stated here | **Yes** |
| S4 | 2 | The I/O timing STA needs: input setup and hold to each clock, MISO and TDO valid after their edge, LINK_TX after CLK | Not modelled | A timing table: inputs change half a period before their edge; outputs valid within a stated time. The numbers come from the first timing run. | **Yes** |
| S5 | 2 | The shortest RST_N pulse | Bench uses 4 CLK | At least 4 CLK periods | text only: **done**, draft 0.4 |
| S6 | 2 | RST_N released while TCK runs. The JTAG domain leaves reset with no synchronizer, so a TCK edge then can leave the TAP in any state. | Not modelled | Rule: the JTAG master clocks TMS high 5 times before use. This is standard; the bench already does it. | text only: **done**, draft 0.4 |
| S7 | 3, 8 | How long SPI_CS_N must stay high between transactions. Under 2 CLK periods, X5 may miss it and a burst never ends. | Bench leaves 2 SCLK periods | At least 2 CLK periods (FPGA rule 11) | text only: **done**, draft 0.4 |
| S8 | 8 | Undefined addresses 0x1A to 0x7F | Read 0; write ignored, not flagged, but still aborts the self-test | Write that down | text only: **done**, draft 0.4 |
| S9 | 8 | Reading a write-only register (START, WEIGHTS, ACT, CLEAR, BIST_CTRL) | Reads 0 | Write that down | text only: **done**, draft 0.4 |
| S10 | 8 | Writing a read-only register | Ignored, not flagged | Write that down | text only: **done**, draft 0.4 |
| S11 | 8 | Reserved bits (MODE 7:5, P 7:3, SHIFT 7:4, ROW_SEL 7:5, BIAS 23:21, START 7:6, CLEAR 7:3, BIST_CTRL 7:2) | Ignored when written; read 0. BIAS reads back zero-extended, RESULT sign-extended. | Write that down | text only: **done**, draft 0.4 |
| S12 | 8 | Extra bytes after a register's width, and a read longer than the register | Ignored; read as 0 | Write that down | text only: **done**, draft 0.4 |
| S13 | 8 | A register write cut short after some of its bytes. The spec says "an unfinished byte or weight row is dropped". | Dropped | Say "byte, register, or weight row" | text only: **done**, draft 0.4 |
| S14 | 8 | WEIGHTS beyond 128 bytes; ACT beyond its length | Extra WEIGHTS ignored; extra ACT bytes keep shifting | Write that down; or ignore ACT bytes beyond the vector | **Yes** (ACT) |
| S15 | 10 | ROW_SEL stepping past row 31 after a JTAG WEIGHTS write | Wraps to 0 | Write "modulo 32" | text only: **done**, draft 0.4 |
| S16 | 9 | What a timeout reports in BIST_STAT | 3, "aborted" | Give it its own code? 2 bits are all used; keep 3 and say so | **Yes** |
| S17 | 9 | BIST_ROW when nothing failed; CBIST_SIG after an abort | 0 after reset, but a passing run after a failing one leaves the old row there; CBIST_SIG keeps the last finished signature | Clear BIST_ROW when a memory test starts, so it always describes the last run | **Yes** (small) |
| S18 | 7 | Whether return frames may follow each other with no gap | They do (capture on the last bit) | Write it, as section 4 does for inbound frames | text only: **done**, draft 0.4 |
| S19 | 7 | tx_silence or requant written while a frame is going out | Applies from the next capture | Write "a frame that has started is not changed by any write" | text only: **done**, draft 0.4 |
| S20 | 10 | TDO when not shifting. The standard drives it high-impedance; this pad is a plain output. | Holds its last value | State it as a known difference from IEEE 1149.1, with "no boundary scan" | text only: **done**, draft 0.4 |
| S21 | 10 | The value captured into the IR, and into BYPASS | 001 and 0 | Write that down | text only: **done**, draft 0.4 |
| S22 | 10 | Which instructions IEEE 1149.1 requires that this TAP lacks (EXTEST, SAMPLE/PRELOAD) | Not there | State: not compliant, no boundary scan, by design (v2 non-goal) | text only: **done**, draft 0.4 |
| S23 | 2 | A minimum CLK frequency. Is there one? The STATUS heartbeat and self-test timeout scale with it. | None | None; state it | text only: **done**, draft 0.4 |
| S24 | 12 | The corners and margin STA must close at | Not stated | The corners in the flow, 25 MHz plus a margin you choose | **Yes** |
| S25 | 4 | RX-12 has odds but no test | None | L0 statistical scenario | test only: **done**, scenario `sync` |

## 7. Assertions (C6)

These are the model's invariants rewritten as assertions in the RTL. Each one checks something on every cycle that a pin test only samples now and then. Each has a cover so that it is known to have fired.

| # | Assertion | Where |
|---|---|---|
| A1 | The wordline enable comes from a flop and is one-hot or zero | Write controller |
| A2 | Address and data are unchanged in the cycles before, during, and after the enable | Write controller |
| A3 | The activation gate is closed whenever the write controller is not idle | Gate |
| A4 | The macro's activation input is zero outside compute and outside a row read | Gate |
| A5 | No new write request arrives while one is pending (no collision) | Write controller |
| A6 | Each Gray pointer changes by at most one bit per clock of its domain | FIFO |
| A7 | The FIFO is never written while full in legal operation (a cover, not a failure, under the hostile tests) | FIFO |
| A8 | A held word does not change between its toggle and the other side's read | X2, X3, X4 |
| A9 | Busy is high from a frame's first payload symbol until its result is captured | Pipeline |
| A10 | The weights do not change while the chain is loaded or computing | Array |
| A11 | Every synchronizer flop's input comes straight from the other domain | Crossings (also C5) |
| A12 | The link FSM never reads the FIFO except in Up | Link handshake |
| A13 | The counters never wrap | Registers |

## 8. Crossings and resets, statically (C5)

Simulation finds a crossing bug only if the timing happens to line up. Two scripts on the synthesized netlist, written once and run on every synthesis:

1. **Crossing list.** For every flop, find its clock. List every flop-to-flop path whose two ends are in different domains. Every one must belong to X1 to X5 and end in a two-flop synchronizer with no logic between the two flops, or be a held word read only under its toggle. Anything else fails the build.
2. **Reset list.** Every flop has a reset, as section 2 requires. Each domain's reset release must be synchronized, except the SPI and JTAG domains, which are covered by rules S6 and section 11 rule 7.

Both can be done with Yosys on the netlist the flow already makes. No commercial CDC tool is needed.

## 9. Formal proofs and the physical flow

**Formal** (SymbiYosys, if the toolchain has it, else bounded checks in simulation). These are small blocks where a proof is cheaper than any number of tests:

- **FIFO:** never overflows with the read side able to keep up; empty and full are exact; the pointers stay Gray.
- **Write controller:** A1, A2, A3 hold for all inputs.
- **Busy rule:** a guarded write and a frame start never both succeed on one edge.
- **CRC:** equal to the reference function for every input (also exhaustive in L1).
- **TAP:** follows the standard table.

**Physical**, which simulation cannot check (merge gates 3 to 5):

| ID | Check | How |
|---|---|---|
| PHY-01 | Timing at every corner, with the I/O timing of S4 | STA in the flow; L3 timing simulation of the quick traces |
| PHY-02 | DRC, LVS, antenna | Flow signoff |
| PHY-03 | Read-bitline mapping against the macro layout | Karan, merge gate 4 |
| PHY-04 | Macro timing library, write arcs included | Karan, merge gate 5 |
| PIN-01, 02 | Pin names, directions, pulls | Script comparing `info.yaml` and the pad wrapper with section 1 |

## 10. Regression and when each part runs

| Tier | When | Contents | Time |
|---|---|---|---|
| Fast | Every push (CI `fast` job) | Lint; `make func-all`; L0 scenarios without the photographs; `verify matrix` | About 5 minutes (estimate) |
| Full | Before Karan merges to `v2-dev`, and nightly when the laptop is idle | All of L0 (random 300 + 300, mutants, photographs); L1 with mutation; L2 replay on Icarus and Verilator with coverage | About 1 hour (estimate) |
| Signoff | Before the go/no-go on 2026-12-07 | Everything above; L3 on both netlists; L4 crossing and reset scripts, proofs, STA; coverage reports at 100% or with every exclusion listed | Half a day |

Heavy runs are single-threaded on the E-cores, one at a time, as now.

## 11. Exit criteria

| Milestone | Date | Criteria |
|---|---|---|
| Spec frozen | 2026-10-19 | Section 6 items marked "Yes" decided; spec, model and `requirements.py` updated; matrix at 0 gaps and 0 "one method" except PERF |
| Each module done | With its RTL | L1 tests pass on Icarus and Verilator; its mutation table 100%; line and toggle 100% with exclusions listed; its assertions in place |
| RTL frozen | 2026-11-23 | L2 replay matches every trace; random co-simulation clean; C1 to C4 and C6 at 100% |
| Go or no-go | 2026-12-07 | L3 and L4 clean; C5 at 100%; merge gates 1 to 5 met |
| Silicon | 2027 | Bring-up plan below |

**Silicon bring-up (L6), in order.** The order is chosen so that each step needs only what the previous steps proved.

1. Current at power-up with RST_N low.
2. The STATUS pin: heartbeat or high, with no FPGA logic needed.
3. JTAG IDCODE.
4. SPI: ID, then every register.
5. The memory test through BIST_STAT and ROW_DATA. This is also the first check of the read mapping (PHY-03) on real silicon.
6. One vector over SPI only.
7. The link at slow LINK_CLK, then at CLK.
8. The return lanes.
9. Both demo networks.
10. Energy with the lanes silenced.

Every step has a pass criterion from the spec and a fallback interface if it fails.

## 12. How this plan was audited

- **Every section of the spec was read sentence by sentence.** Each normative statement became a requirement in `requirements.py` (102), or a gap in section 6 where the sentence was missing.
- **The tool checks every trace both ways.** Every requirement's checks and faults must exist and pass. Every check in every scenario and every fault in the fault list must belong to some requirement. On the first run, 5 checks and 1 fault belonged to none; they were traced and the count is now zero.
- **The fault list was run against the checks.** Its first run, against draft 0.2, found 24 faults no check noticed. They led to 35 new checks and two real spec bugs (spec section 13).

**What this audit cannot see:**
- Requirements that should exist but appear nowhere in the spec. That needs a second reader: Karan, and anyone who has to build the FPGA side.
- Whether the behavioural macro model matches the real macro.

## 13. Work list, in order

1. **Karan:** decide the "Yes" items in section 6 and the open values in spec section 14.
2. ~~Write the "text only" items of section 6 into the spec, with requirements and checks for each.~~ Done 2026-10-14 (spec draft 0.4).
3. ~~Close the 18 "one method" requirements and RX-12 (section 4 table).~~ Done 2026-10-14. RX-12 corrected the spec.
4. ~~Add the functional coverage collectors (section 5) to the model; run random traffic until every bin is hit, or each missing bin is shown impossible.~~ Done 2026-10-14: 100% of reachable bins, 32 impossible with reasons (section 5).
5. Write the crossing and reset scripts (section 8) and try them on the v1 netlist.
6. Then, module by module: golden model, testbench, mutation table, assertions, RTL, L1 to 100%.
7. Point `cocotb/v2` at the v2 top level; L2 to 100%.
8. L3, L4, signoff.
