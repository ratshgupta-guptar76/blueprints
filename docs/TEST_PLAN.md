# Post-silicon test plan: DCIM INT8 matrix-vector chip

Team A07 (Blueprints), SSCS PICO Chipathon 2026. Process: GF180MCU (gf180mcuD).
Prepared by R. Gupta. Revision 0.1, 2026-11-02.

**Status of this plan.** It is written before the design is submitted for fabrication (submission 2026-12-14; chips are expected back 4 to 6 months later). Every expected value below comes from the chip specification or from the cycle-accurate reference model of the chip, and its source is stated. Values that only silicon can give (supply current, maximum clock frequency, voltage margins, energy) are marked **to be measured**; no guess is given for them. If the specification changes before submission, this plan will be updated to match.

---

## 1. Scope and goals

This plan covers testing fabricated chips on a dedicated test board. Simulation and other checks done before fabrication are outside its scope; their outputs are used here only as expected values.

The tests answer these questions, in this order:

1. Is the die alive: pins connected, no shorts, sane current, clock and reset working?
2. Do the built-in self-tests pass?
3. Do the control interfaces (SPI and JTAG) work?
4. Does the weight memory store and return every bit correctly, at every address?
5. Is every matrix-vector result bit-exact, at every activation precision, through every interface?
6. Does the chip handle errors exactly as specified (bad frames, overruns, writes while busy, link loss, reset)?
7. How fast does it run, and at what supply voltages (characterization)?
8. How much energy does a matrix-vector operation take (characterization)?
9. Do real workloads (keyword spotting, photograph classification) give exactly the reference results?

Questions 1 to 6 have pass or fail answers. Questions 7 and 8 are measurements, reported with their conditions. Question 9 is answered bit-exactly, result by result.

## 2. The chip in brief

### 2.1 Function

The chip computes y = W^T a, a matrix-vector product, in a digital compute-in-memory array.

| Item | Value |
|---|---|
| Weights W | 32 rows x 4 outputs, signed 8-bit (-128 to 127), 1,024 bits in total |
| Weight storage | Custom 9T SRAM bitcells (6T storage plus a compute read port), four 32 x 8 macros. Weights stay until rewritten; computing never disturbs them. |
| Activations a | 32 unsigned values of P bits each, P = 1 to 8, set by a register |
| Compute | One activation bit plane per clock cycle, least significant first: P cycles per vector |
| Raw result | Four signed sums y_j, j = 0 to 3, each 13 + P bits wide (14 bits at P = 1, 21 at P = 8) |
| Optional on-chip post-processing ("requantize") | Per output: add a 21-bit signed bias, clamp below at 0, shift right by 0 to 15, clamp above at 255. The result is then 8 bits. |

The table below gives the extreme results, which are used as directed test cases (section 7.5). Every weight is -128, or every weight is 127, and every activation is at its maximum, 2^P - 1.

| P | Max activation | All weights -128 | All weights 127 | Raw width (bits) |
|---|---|---|---|---|
| 1 | 1 | -4,096 | 4,064 | 14 |
| 2 | 3 | -12,288 | 12,192 | 15 |
| 3 | 7 | -28,672 | 28,448 | 16 |
| 4 | 15 | -61,440 | 60,960 | 17 |
| 5 | 31 | -126,976 | 125,984 | 18 |
| 6 | 63 | -258,048 | 256,032 | 19 |
| 7 | 127 | -520,192 | 516,128 | 20 |
| 8 | 255 | -1,044,480 | 1,036,320 | 21 |

Every value fits its raw width, so no result can overflow.

### 2.2 Interfaces

| Interface | Pins | What it does | Role in testing |
|---|---|---|---|
| Link input | LINK_CLK, LINK_D[3:0] | Activation frames: sync symbol, header (type, 6-bit sequence number), payload, CRC-8. A valid frame starts a compute. | Main data path; error handling |
| Return lanes | LINK_TX[3:0] | Lane j carries result j, with its own sync word, header (sequence number echoed) and CRC-8. Clocked from CLK. | Main result path |
| SPI (mode 0) | SPI_SCLK, SPI_CS_N, SPI_MOSI, SPI_MISO | Register file, weight loading, and a complete fallback: activations through the ACT register, results through RESULT0 to RESULT3 | Weight loading; first vectors; fallback |
| JTAG | TCK, TMS, TDI, TDO | IDCODE, BYPASS, register access (DEBUG), memory and compute self-test control. No boundary scan. | Bring-up; second, independent access path |
| STATUS pin | STATUS | After reset: self-test result (low while running, a square wave of CLK / 65,536 on pass, high on fail). After the first write or valid frame: one CLK-cycle pulse per finished compute. | Bring-up with no interface working; compute counting |

### 2.3 Pins

22 pads: one supply (VDD), one ground (VSS), 13 inputs, 7 outputs. Pad positions come from the shuttle's pad map.

| Pin | Direction | Internal pull | Clock domain |
|---|---|---|---|
| VDD, VSS | supply | | |
| CLK | in | | core |
| RST_N | in (active low, asynchronous) | | all |
| LINK_CLK | in | pull-down | link |
| LINK_D[3:0] | in | pull-down | link |
| LINK_TX[3:0] | out | | core |
| SPI_SCLK | in | | SPI |
| SPI_CS_N | in | pull-up | SPI |
| SPI_MOSI | in | | SPI |
| SPI_MISO | out | | SPI |
| TCK | in | | JTAG |
| TMS | in | pull-up | JTAG |
| TDI | in | | JTAG |
| TDO | out | | JTAG |
| STATUS | out | | core |

### 2.4 Operating rules the test bench must follow

These rules come from the chip specification. A test that breaks one has not found a chip failure; several tests below break one deliberately and check that the chip reacts as specified.

1. LINK_CLK runs continuously while the link is enabled and is never faster than CLK. SPI_SCLK is never faster than CLK. TCK is at least 4 CLK periods for DEBUG, MBIST and CBIST scans.
2. RST_N is held low for at least 4 CLK periods, and asserted only while SPI_CS_N is high.
3. After RST_N rises, TMS is held high for five TCK cycles before the first JTAG scan.
4. SPI_CS_N stays high for at least 2 CLK periods between transactions.
5. A register write takes effect 3 CLK edges after its last SCLK edge; nothing reads it back or relies on it sooner than 4 CLK periods after the transaction.
6. Weights, P, bias, shift and mode are written only while `STATUS.busy` is 0.
7. Frames are paced so the chip is free when each payload arrives: at least 67 + P CLK cycles between the first payload symbols of two frames for P = 2 to 8 (75 at P = 8), 22 at P = 1 raw, 16 at P = 1 requantized. No frame is sent during a weight burst.
8. After a frame fails, at least 72 idle symbols are sent before the next frame.
9. Each return lane is aligned by its own sync word before its CRC is checked.
10. After switching the link off, LINK_CLK keeps running until `STATUS.link_ready` reads 0.

### 2.5 Self-test at reset

Out of reset, with nothing written, the chip runs a memory test (march test, patterns 0x00000000, 0xFFFFFFFF, 0x55555555 and 0xAAAAAAAA, reading through the compute port) and then a compute test (16 vectors at P = 8 from a 16-bit pseudo-random generator, folded into a 32-bit signature). Each test has an 8,192-cycle timeout. Any SPI or JTAG write aborts a running test. Together they take about 3,030 CLK cycles in the reference model (about 121 microseconds at 25 MHz). The expected compute signature is `0x29E000BC`, computed by ordinary arithmetic in the reference model.

After the self-test the weight array holds test patterns, so after every reset the weights must be written before the chip is used.

## 3. Equipment

The bench uses only common, low-cost equipment. No source-measure unit, temperature chamber or stand-alone logic analyzer is needed.

| Item | Need | Minimum specification | Used in |
|---|---|---|---|
| Test board | Required | Section 4 | All |
| FPGA board | Required | At least 20 general I/O at 3.3 V (13 to drive the chip's inputs, 7 to read its outputs), a clock generator able to make CLK from about 1 MHz to well above 25 MHz in fine steps, and enough memory for test vectors (about 30 MB for the largest file, section 5). For example the Digilent Nexys A7-100T (four 8-signal Pmod ports at 3.3 V, 128 MB DDR2). | All functional tests |
| Host PC | Required | Runs the reference model (Python) to produce expected values, drives the FPGA, stores logs | All |
| Bench power supply | Required | One adjustable channel, 0 to 3.6 V, with a current limit and a current readout. One channel is enough: the level translators take their chip-side supply from the same output (section 4). | Power-up, voltage sweeps |
| Digital multimeters | Required, two | One in series with VDD as the current meter: a microamp range for static current, a milliamp range for running current, and averaging or a steady reading over about 1 second. Its range is set from the first measurement (section 7.1). The other for voltage at the chip pins, diode test and high-impedance readings. | Current and energy, pin continuity, pull-up and pull-down checks, VDD at the pins |
| Oscilloscope | Required | Single-shot capture; 4 channels preferred, 2 workable. At least 100 MHz bandwidth is preferred for edge timing at 25 MHz; with less, LNK-06 is run at a lower CLK. | Clock and pin timing, STATUS, return-lane timing, first power-up |
| Signal generator | Required | Square wave at 3.3 V into a high-impedance input. Any frequency up to 25 MHz that it can reach is enough for section 7.2. | Self-test check with no FPGA (section 7.2) |
| Logic analyzer | Not needed | The FPGA's embedded logic analyzer covers this | Debugging the bench |
| ESD protection | Required | Grounded mat and wrist strap | Handling every die |
| Thermometer | Recommended | An inexpensive digital room thermometer. Without one, the room's thermostat reading is logged instead. | Ambient temperature, logged with every measurement |

**Expected current, for setting ranges only.** No power analysis of this chip exists yet. The layout tools' estimate for an earlier layout of the same compute core, with default switching activity, was 10.7 to 12.6 mW, about 3 to 4 mA at 3.3 V. That is not a measurement and does not include the load on the output pads. Static current is not estimated.

## 4. Test board requirements

This section is a design checklist for the test board.

**Chip mounting.** The board follows the package (or chip-on-board bonding) that the shuttle delivers, and the shuttle's pad map. If a socket is available for that package, use one, so that several dies can be tested on one board.

**Supply and current measurement.**
- [ ] The chip's VDD is a rail of its own, fed only from the bench supply, so that the measured current is the chip's alone.
- [ ] A jumper or 0-ohm link in series with VDD, so the current meter can be inserted.
- [ ] A test point at the chip's VDD and VSS pins, so the voltage at the chip can be measured, not only at the supply. The current meter drops a little voltage, so the supply is set by this reading.
- [ ] Decoupling capacitors close to the VDD pin.
- [ ] Nothing else on the board draws from the chip's VDD rail.

**Signal levels.**
- [ ] Level translators between the FPGA and the chip on every signal. Their chip-side supply is taken from the same bench output as the chip's VDD, but before the current-meter jumper, so it always follows the chip's VDD and its current is not counted as the chip's. This keeps the inputs from being driven above the chip's VDD during voltage sweeps and power-up, which would forward-bias the pads' protection diodes, power the chip through its inputs and spoil the current measurement. The meter's voltage drop puts the translators slightly above the chip's VDD; keep it well below 0.3 V by checking the meter's burden voltage on the range in use. The translators must also keep their outputs off while unpowered.
- [ ] Translators fast enough for the highest CLK under test (at least 100 Mbit/s per channel), with matched delay across channels.
- [ ] A jumper on each chip pin to disconnect it from its translator (for continuity and pull checks).

**Clock and reset.**
- [ ] CLK selectable between the FPGA and a coaxial input for a signal generator.
- [ ] CLK routed as a short, controlled line with a series termination footprint near the driver.
- [ ] RST_N driven by the FPGA and also by a push button. It defaults low (board pull-down) so the chip is held in reset until something releases it.

**Standalone operation (no FPGA).**
- [ ] With only VDD, CLK and the reset button, the chip must run its self-test. Inputs without an internal pull (SPI_SCLK, SPI_MOSI, TCK, TDI) get weak board pull-downs that can be removed with a jumper.
- [ ] STATUS drives an LED through a buffer, as well as going to the FPGA. With CLK at 65,536 Hz the self-test pass signal is a 1 Hz blink.

**Probing.**
- [ ] A test point and a ground point next to every signal, for the oscilloscope.
- [ ] A ground pin for every few signals on each FPGA connector.
- [ ] A standard JTAG header in parallel with the FPGA's JTAG lines, isolated by jumpers, so an external JTAG adapter can be used if the FPGA path fails.

**Identification.**
- [ ] A label area for the die or package serial number. Every log entry records it.

## 5. Test infrastructure to build before chips return

| Item | What it is | Status |
|---|---|---|
| Chip specification | Exact pin-level behaviour, cycle by cycle | Exists (draft) |
| Reference model | A cycle-accurate model of the chip with all four clocks, written from the specification. It produces every expected result, frame, counter value and cycle count in this plan. | Exists |
| Pin traces | Every scenario of the reference model recorded as pin activity: each clock edge, each input change, each output where the bench samples it | Exist |
| Recorded workload vectors | A spoken word from the Speech Commands v2 test set, as the chip sees it: 6,014 weight sets, 594,766 activation vectors and the raw results the chip must return, with a SHA-256 of the whole stream. A 32-set sample covering every kind of product is in the repository. | Exist (keyword spotting). Photograph vectors to record the same way. |
| Test board | Section 4 | To design once the package is known |
| FPGA bench firmware | SPI master, JTAG master, 4-lane link transmitter with CRC, 4-lane return receiver that aligns each lane on its sync word and checks the CRC, cycle counters on CLK, STATUS pulse counter, vector memory | To write. The reference model's bench side defines what it must do. |
| Host software | Loads tests and expected values into the FPGA, runs the sequence in section 7, compares every result, writes the log | To write |
| Bench rehearsal | The chip's design running on an FPGA (memory as flip-flops), driven by the bench exactly as the chip will be, so that bench faults are found before silicon | Planned |

## 6. Test conditions and records

**Nominal conditions.** VDD = 3.3 V at the chip pins, CLK = 25 MHz, LINK_CLK = CLK, SPI_SCLK at most CLK, TCK at least 4 CLK periods, room temperature (recorded). The design's timing is analysed at the process's 3.3 V corners: 3.0 V (slow, 125 degrees C), 3.3 V (typical, 25 degrees C) and 3.6 V (fast, -40 degrees C). **Never apply more than 3.6 V** unless the process's absolute maximum rating has been checked first.

**Handling.** ESD precautions for every die. Power off before inserting or removing a die.

**What is logged with every run.** Date and time; die serial number; board serial number; VDD at the chip; CLK, LINK_CLK, SCLK and TCK frequencies; ambient temperature; test ID; FPGA firmware version; reference model version (repository commit); pass or fail; every mismatch with the expected value (address, expected, received); raw measurement files.

**Repeatability.** The chip is digital and deterministic: the same inputs must give the same results, cycle counts and counters on every run, every die and every board. Any run-to-run difference in a digital result is a failure. Analog measurements (current, energy) are repeated at least 10 times and reported as mean and standard deviation.

**Pass rule for every functional test.** Every result, frame, sequence number, CRC, counter and cycle count equals the reference model's value exactly. There is no tolerance.

## 7. Test sequence

The order is chosen so that each step needs only what earlier steps proved. If a step fails, follow the diagnosis in section 9 before going on. Tests marked **(screen)** make up the short screening run that every die receives; the rest are run on a characterization subset (section 8).

| Phase | Tests | Needs |
|---|---|---|
| 7.1 Power and pins | PWR-01 to PWR-04 | Board, supply, multimeter |
| 7.2 Self-test with no interface | ST-01 to ST-03 | Plus clock and scope |
| 7.3 Control interfaces | JT-01 to JT-04, SPI-01 to SPI-05 | Plus FPGA |
| 7.4 Memory | MEM-01 to MEM-06 | SPI |
| 7.5 Arithmetic over SPI | ARI-01 to ARI-09 | SPI, memory passing (ARI-09 also needs the return lanes) |
| 7.6 Link and return lanes | LNK-01 to LNK-06 | Arithmetic passing over SPI |
| 7.7 Throughput and cycle counts | PERF-01 to PERF-04 | Link |
| 7.8 Error handling and recovery | ERR-01 to ERR-12 | Link |
| 7.9 Workloads | APP-01 to APP-03 | Link |
| 7.10 Characterization | CHR-01 to CHR-04 | All functional tests passing |
| 7.11 Energy | NRG-01 to NRG-05 | Link, current meter |

### 7.1 Power and pins

**PWR-01 Visual inspection** (screen). Inspect the package or bonds under magnification. Record anything unusual. Pass: no visible damage.

**PWR-02 Pin continuity, unpowered** (screen). Disconnect every pin from its translator. With the multimeter in diode mode, measure from VSS to each signal pin, then from each signal pin to VDD; then measure the resistance from VDD to VSS. Pass: every signal pin shows a protection-diode forward drop, similar on every pin and every die; no pin open or shorted; VDD to VSS not a short. A pin that differs from the same pin on other dies points to a bond or pad fault.

**PWR-03 First power-up, in reset** (screen). Setup: RST_N low, CLK stopped, all inputs low, current limit 20 mA (several times the estimate in section 3). Raise VDD slowly from 0 to 3.3 V while watching the current. Record the current at 3.3 V. Then start CLK at 25 MHz and record the current again. Pass: no current limit reached; the current is steady; every output is low, as the specification requires in reset. The first dies set the range against which later dies are compared; a die far outside the others is investigated.

**PWR-04 Internal pulls.** Setup: VDD at 3.3 V, RST_N low, the pin under test disconnected (jumper open). Measure with a high-impedance voltmeter on LINK_CLK, LINK_D[3:0] (expected near VSS: pull-down), SPI_CS_N and TMS (expected near VDD: pull-up). Pass: each pin is at the expected rail.

### 7.2 Self-test with no interface

These need only power, a clock and reset, so they show whether the core runs before any interface is trusted.

**ST-01 Self-test result on the STATUS pin** (screen). Setup: CLK at 25 MHz from the signal generator or the FPGA, every other input at its default. Release RST_N. Scope on STATUS, triggered on RST_N rising.
- Expected: STATUS low while the self-test runs (about 3,030 CLK cycles, about 121 microseconds; the exact count comes from the reference model trace), then a square wave of CLK / 65,536 = 381.47 Hz.
- Pass: the square wave appears, at exactly CLK / 65,536.
- STATUS high after the self-test means a test failed or timed out (read the cause in SPI-03). STATUS stuck low means the core is not running (section 9).

**ST-02 Self-test across clock frequency.** Repeat ST-01 at CLK = 65,536 Hz (expected: the LED blinks at 1 Hz), 1 MHz, 10 MHz and 25 MHz, or the highest frequency the signal generator reaches. Pass: square wave at CLK / 65,536 every time. The self-test has no minimum clock frequency; its timeout and the heartbeat both scale with CLK.

**ST-03 Reset repeatability.** Press reset 100 times at random moments (with SPI_CS_N high, as rule 2 of section 2.4 requires). Pass: every time, STATUS goes low and the square wave returns.

### 7.3 Control interfaces

**JT-01 TAP reset and IDCODE** (screen). After reset, five TCK cycles with TMS high, then read the data register. Expected: `0xDC1A0003` (the identity `0xDC1A0002` with bit 0 forced to 1, as the JTAG standard requires of an IDCODE). Pass: exact value, 100 reads in a row.

**JT-02 Instruction register and BYPASS.** When an instruction is shifted in, the value captured in the instruction register is `001`. Select BYPASS (`111`): a 1-bit register that captures 0, so a pattern shifted through TDI appears on TDO one TCK later. Codes `000`, `101` and `110` also select BYPASS. Pass: all as stated.

**JT-03 Register access through DEBUG.** Read ID and STATUS through DEBUG, remembering that every answer is one scan behind: a scan with the request, then a scan that collects it, whose ready bit must be 1. Write and read back MODE, P and SHIFT. Pass: values identical to the same registers read over SPI.

**JT-04 Self-test control through JTAG.** Start the memory test through MBIST, collect `{first failing row, ready, state}`; start the compute test through CBIST, collect `{ready, signature, state}`. Expected: state "pass" (1) for both, signature `0x29E000BC`. Pass: as expected.

**SPI-01 Identity** (screen). Read register 0x00. Expected `0xDC1A0002`. Pass: exact, 100 reads in a row, at SCLK = 1 MHz, then at SCLK = CLK.

**SPI-02 Reset values** (screen). Before any write, read every register. Expected: MODE 0, P 7 (that is, P = 8), SHIFT 0, BIAS0 to BIAS3 0, RESULT0 to RESULT3 0, CNT_CRC, CNT_OVERRUN and CNT_BAD 0, ROW_SEL 0; addresses 0x1A to 0x7F and every write-only register read 0. Pass: all exact.

**SPI-03 Self-test results** (screen). Before any write: STATUS bit 7 (`selftest_done`) is 1 and bit 0 (`busy`) is 0; BIST_STAT reads `0x05` (memory pass, compute pass); CBIST_SIG reads `0x29E000BC`. Pass: all exact. On a memory failure BIST_ROW gives the first failing row.

**SPI-04 Register write and read-back.** For every read-write register (MODE, P, SHIFT, BIAS0 to BIAS3, ROW_SEL): write all-0, all-1, `0x55` and `0xAA` patterns (byte-wise across the register width) and read back after at least 4 CLK periods. Reserved bits read 0. Writes to read-only and undefined addresses change nothing. Pass: every read-back equals the expected value.

**SPI-05 Transaction edge cases.** A transaction cut short in the middle of a byte changes nothing, and the next transaction is aligned. Extra data bytes after a register's width are ignored on writes and read as 0. Pass: as stated.

### 7.4 Memory

The weight memory is a custom SRAM macro, so its function and margins are measured here for the first time. The memory is read through the compute port: an activation that is 1 on one row and 0 on all others makes the 32 column sums equal that row's 32 stored bits. ROW_SEL and ROW_DATA do exactly that from SPI or JTAG. This is also the first check on silicon of the mapping from the macro's read outputs to weight columns.

**MEM-01 Built-in memory test** (screen). Check the reset self-test result (SPI-03), then command a rerun through BIST_CTRL bit 0 and read BIST_STAT. Pass: "pass" both times.

**MEM-02 Write and read-back patterns** (screen). Write a full weight set over SPI, then read every row through ROW_SEL and ROW_DATA. Patterns:
1. All 0, then all 1.
2. `0x55555555` and `0xAAAAAAAA` in every row, then alternated row by row (checkerboard).
3. A different value in every row (for example the row number repeated in each byte, and its complement), to catch address faults that uniform patterns cannot.
4. Walking 1 and walking 0: one bit set (or cleared) per row, moving across all 32 columns.

Pass: every bit of every row equals what was written. Assert in the test that all 32 rows and all 32 columns were checked.

**MEM-03 Partial writes.** A weight burst that stops after k rows (k = 1, 16, 31) changes only the first k rows; the rest keep their values. Pass: as stated.

**MEM-04 Compute does not disturb weights.** Write a pattern from MEM-02, run 10 million random vectors over the link at P = 8, then read every row back. Pass: unchanged.

**MEM-05 Retention with the clock running and stopped.** Write the row-unique pattern. Read back after 1 minute, 10 minutes and 1 hour with CLK running and nothing written, then repeat with CLK stopped. Pass: unchanged.

**MEM-06 Data retention voltage** (characterization). Write the row-unique pattern at 3.3 V. Stop CLK. Lower VDD to a hold voltage for 10 seconds, raise it back to 3.3 V, restart CLK, read every row. Step the hold voltage down by 0.1 V until bits are lost. Also read back MODE, P and SHIFT (written beforehand to non-reset values): if those changed too, the control logic lost its state first and the result measures the logic, not the memory; record both. Report the lowest hold voltage with no loss, per die.

### 7.5 Arithmetic over SPI

Activations are written through ACT (`MODE.act_spi` = 1), the compute is started with START, and the results are read from RESULT0 to RESULT3. This path needs no link, so it isolates the arithmetic from the link and return lanes. Every expected value is computed by the reference model. Each case runs at every P from 1 to 8.

**ARI-01 First vector** (screen). One weight of 1 at row 0, output 0; activation 1 on row 0. Expected: result 0 = 1, the others 0. Repeat for each output.

**ARI-02 Zeros** (screen). All-zero weights with random activations, and random weights with all-zero activations. Expected: every result 0.

**ARI-03 Extremes** (screen). All weights -128, then all weights 127, with every activation at 2^P - 1. Expected: the values in section 2.1 (for example -1,044,480 and 1,036,320 at P = 8). These drive the accumulators to the ends of their range and check the weight sign handling.

**ARI-04 Weight bit walk.** For each row, each output and each of the 8 weight bits: that single bit set, every other weight bit 0, every activation at 2^P - 1. Expected: the output equals 2^b x (2^P - 1) for bits 0 to 6 and -128 x (2^P - 1) for bit 7 (the sign bit); every other output 0. This checks the column position and sign of each of the 1,024 cells through the arithmetic, independently of MEM-02. Assert that 32 x 4 x 8 = 1,024 cases ran.

**ARI-05 Activation bit walk.** Every weight 1. For each row and each activation bit k below P, set only that row's activation to 2^k and all others to 0. Expected: every output equals 2^k. This checks each bit plane and its weight in the sum.

**ARI-06 Mixed signs.** Half the rows 127, half -128, activations at their maximum; and alternating signs across outputs. Expected: the reference values (large partial sums that cancel).

**ARI-07 Random** (screen at P = 1 and 8). 100 random weight sets with 16 random vectors each, at every P. Expected: the reference values.

**ARI-08 Compute gate.** `MODE.gate_off` = 1 with non-zero weights and activations. Expected: every result 0. Then `gate_off` = 0: results return to the reference values.

**ARI-09 Requantize.** `MODE.requant` = 1. For each output: out = min(max(r + BIAS, 0) >> SHIFT, 255). Cases: SHIFT 0 to 15; biases that put r + BIAS at -1, 0, 1, and at the thresholds where the clamp at 255 begins for each shift; random. Requantized results appear only on the return lanes, so this test runs once the link works (LNK-04); RESULT0 to RESULT3 always hold the raw values. Expected: the reference values.

### 7.6 Link and return lanes

**LNK-01 Link enable.** Write `MODE.link_en` = 1 with LINK_CLK running; `STATUS.link_ready` goes to 1. Expected: the first frame is taken 22 idle symbols after the start of the MODE write, as in the reference model.

**LNK-02 First frames.** One frame at P = 8 with the ARI-01 case, then ARI-02 and ARI-03, at LINK_CLK = CLK. The FPGA aligns each return lane on its sync word (1, 1, 0, 1), then checks the header and the CRC. Expected: result, sequence number and CRC exactly as in the reference.

**LNK-03 Arithmetic through the link** (screen). ARI-03 to ARI-07 again, now through frames and return lanes, at every P. Expected: identical to the SPI results.

**LNK-04 Requantized frames.** ARI-09 through the link. Expected: 8-bit results in type-1 return frames of 16 cycles.

**LNK-05 Link clock ratios.** LINK_CLK equal to CLK at several phase offsets; LINK_CLK at 2/3 and 1/2 of the CLK frequency; and LINK_CLK from an independent source slightly slower than CLK. Random traffic at each. Expected: every result correct; `STATUS.fifo_ovf` stays 0.

**LNK-06 Return-lane timing.** Scope on CLK and each LINK_TX lane at the board. Measure each lane's delay from the CLK edge and the skew between lanes, at 25 MHz and at the highest passing CLK of CHR-01. Record the FPGA's chosen alignment per lane. Pass: the FPGA's sampling margin is positive on every lane; report the measured values.

### 7.7 Throughput and cycle counts

The FPGA counts CLK cycles. Every count must equal the reference model's exactly: the chip is synchronous, so its cycle counts do not vary.

**PERF-01 Minimum frame spacing** (screen at P = 1 and 8). 1,000 frames back to back at the minimum spacing for each P: 22 cycles at P = 1 raw, 16 at P = 1 requantized, 67 + P for P = 2 to 8 (69 to 75). Expected: every result returned, in order, CNT_OVERRUN 0, one STATUS pulse per compute. With the return lanes silenced (`MODE.tx_silence` = 1) at P = 1 the limit is the 13-symbol inbound frame: 13 cycles.

**PERF-02 One cycle too close.** The same, with frames one cycle closer than the minimum. Expected: frames that arrive while the chip is busy are dropped and counted in CNT_OVERRUN, never corrupted; every result that does return is correct.

**PERF-03 Weight load time.** One full weight set over SPI at SCLK = CLK, from the start of the burst until the chip reports not busy. Expected: 1,040 CLK cycles, measured as the reference model measures it.

**PERF-04 Latency.** From the last CRC symbol of a frame to the STATUS pulse and to the first bit of the return frame, at every P. Expected: the reference model's counts.

### 7.8 Error handling and recovery

Each test breaks a rule from section 2.4 or injects a fault, and checks the chip's specified reaction. Expected values come from the reference model.

| ID | Action | Expected |
|---|---|---|
| ERR-01 | Flip one bit of a frame (every position, at P = 1 and 8) | Frame rejected, CNT_CRC + 1, no result returned; the next good frame, sent after 72 idle symbols, is correct |
| ERR-02 | Send a good frame 71 idle symbols after a bad one, then 72 | Lost at 71, taken at 72 |
| ERR-03 | Frame with a type other than 0 | CNT_BAD + 1, no compute |
| ERR-04 | Write weights, P, SHIFT or START while a vector loads or a result waits | Write ignored, `STATUS.err_busy` set, the vector's result correct |
| ERR-05 | Send a frame during a weight burst | Frame dropped (overrun), never computed on half-written weights |
| ERR-06 | Stop LINK_CLK in the middle of a frame | Chip busy; CLEAR bit 2 frees it; it then runs over SPI with its weights intact |
| ERR-07 | Full recovery from link trouble without reset: CLEAR bit 2, wait for not busy, `link_en` = 0, wait for `link_ready` = 0, clear counters and flags, configure, 72 idle symbols | Every following frame correct |
| ERR-08 | Switch the link off and on 16 times with traffic | Every frame correct, no overflow flag |
| ERR-09 | Run past 255 errors of each counter; then CLEAR bits 0 and 1 | Counters stop at 255; CLEAR resets them and the sticky flags |
| ERR-10 | Reset at random moments during traffic (SPI_CS_N high) | Afterwards the chip behaves exactly like one just powered up: reset values (SPI-02), self-test passes (SPI-03), STATUS heartbeat |

**ERR-11 SPI-only and JTAG-only operation.** With the link inputs disconnected (left at their internal pull-downs): a whole vector through SPI (ACT, START, RESULT), then through JTAG DEBUG. Expected: correct results. This proves each fallback path on its own.

**ERR-12 Self-test abort.** Make an SPI write during the reset self-test (within its first 3,000 cycles). Expected: BIST_STAT reports "aborted" (3) for the running test, the write is carried out, and STATUS switches to DONE pulses.

### 7.9 Workloads

**APP-01 Recorded keyword-spotting vectors** (screen: the 32-set sample). Load each recorded weight set over SPI, send its vectors as frames at the minimum spacing, and compare every return frame with the recorded result. First the 32-set sample, then the whole word: 6,014 weight sets and 594,766 vectors, 51,120,635 CLK cycles in the reference model (about 2 seconds at 25 MHz). Also compute the SHA-256 of the returned stream. Pass: zero differences; hash equal to the recorded one.

Real data does not reach the extreme accumulator values (its largest result needs 19 bits), so APP-01 complements ARI-03 and does not replace it.

**APP-02 Photograph vectors.** As APP-01, with vectors recorded from the photograph classification networks once those vectors exist. Pass: zero differences.

**APP-03 Full application runs** (optional, needs the application running on the FPGA and host). Keyword spotting on the official Speech Commands v2 test set (4,890 clips) and photograph classification, with every product computed by the chip. Pass: every chip result equals the reference model's. The answers are also compared with the reference answers. The reference keyword network scores 97.26% on that test set with every product computed in the chip's arithmetic. The steps done outside the chip (normalization, softmax, scaling) are in floating point, so a clip's answer can differ between computers; any differing answer is traced to those steps, never accepted as a chip result.

### 7.10 Characterization

Run on the characterization subset of dies. Results are reported as measured; there is no pass or fail.

**CHR-01 Clock frequency against supply voltage (shmoo).** VDD from 3.6 V down in 0.1 V steps until the chip fails at 1 MHz. At each VDD, CLK from 1 MHz upward (1, 5, 10, 15, 20, 25 MHz, then 1 MHz steps) until a failure. At each point run: MEM-01, MEM-02 (row-unique pattern), ARI-03, ARI-07 at P = 1 and 8, LNK-03 at P = 8 with LINK_CLK = CLK, and SPI-01 at SCLK = CLK. Report the pass and fail map and the first failing test at each boundary point. If the bench's own limit (FPGA or translators) is reached before the chip fails, report "at least" that frequency.

**CHR-02 Memory margins.** MEM-02 alone across the CHR-01 grid. The memory macro is custom, so its boundary may differ from the logic's; report it separately.

**CHR-03 Static current against VDD.** CLK stopped, out of reset, idle. VDD from 3.0 V to 3.6 V in 0.1 V steps.

**CHR-04 Die-to-die spread.** CHR-01's boundary, CHR-03's current, and MEM-06's retention voltage, across all characterization dies.


### 7.11 Energy

The chip has a single supply, so the measured current includes the I/O pads. Energy is therefore measured differentially: two runs that differ only in the thing being measured, on the VDD side, with everything else identical. The return lanes are silenced (`MODE.tx_silence` = 1) in every compute loop, so their pad current does not swamp the compute current. Each figure is reported with VDD, CLK, P, interface, requantize on or off, data used, and temperature.

**NRG-01 Idle.** CLK running, link enabled with idle symbols, no frames. This is the baseline.

**NRG-02 Energy per vector.** Back-to-back frames at the minimum spacing for 10 seconds; vector energy = (I_loop - I_idle) x VDD / vector rate. At 25 MHz and P = 8 that is 333,333 vectors per second, each vector being 128 multiply-accumulates (32 x 4) at 8 x 8 bits. Run at every P, with random data and with the recorded keyword-spotting vectors.

**NRG-03 Compute share.** NRG-02 again with `MODE.gate_off` = 1 (activation gate closed: the array and adder trees do not switch, the link and control do). The difference from NRG-02 is the energy of the compute array itself.

**NRG-04 Weight load energy.** Compare a loop of weight bursts over SPI with an idle SPI bus (CS_N high).

**NRG-05 Supply dependence.** NRG-02 at P = 8 and NRG-03 at VDD from the lowest passing voltage of CHR-01 to 3.6 V, at 25 MHz or the highest passing frequency if lower.

Every measurement is repeated 10 times and reported as mean and standard deviation.

## 8. Dies, screening and classification

Every die received runs the screen (the tests marked "screen"). A subset of at least three dies (all of them if fewer arrive) runs every test, including characterization and energy. The number of dies is set by what the shuttle delivers.

| Class | Meaning |
|---|---|
| A: fully functional | Every screen test passes at nominal conditions |
| B: functional through SPI only | Arithmetic correct over SPI; link or return lanes faulty |
| C: memory fault | Memory tests fail on identified rows or columns; the rest works |
| D: control interfaces only | SPI or JTAG respond, arithmetic wrong |
| E: not functional | No interface responds, or PWR tests fail |

Characterization and energy figures come from class A dies only.

## 9. Failure diagnosis

| Symptom | Likely area | Next step |
|---|---|---|
| Short between VDD and VSS, or current limit reached | Assembly, package or die damage | Inspect; compare dies; do not raise the current limit |
| One pin open or different in PWR-02 | Bond or pad | Re-check on another die; if consistent across dies, check the board |
| STATUS stuck low after reset | Core not running: clock, reset or supply | Scope CLK and RST_N at the chip pins; check VDD at the pins; try a lower CLK |
| STATUS high after reset | A self-test failed or timed out | Read BIST_STAT, BIST_ROW and CBIST_SIG over SPI or JTAG |
| SPI does not respond, JTAG does | SPI pads or SPI domain | Use JTAG DEBUG for everything else; check SCLK at the pin |
| JTAG does not respond, SPI does | JTAG pads or TAP | Use SPI; check TMS and TCK at the pins, and the five-cycle TMS reset |
| Neither responds, STATUS heartbeat present | Both interfaces, or the bench | Check levels and translators; scope the pins |
| Memory test fails on one or a few rows | Bitcells or wordline of those rows | Map the failing bits with MEM-02; repeat at higher VDD (CHR-02) |
| Memory bits wrong in the same columns on every row, in a fixed pattern | Mapping from the macro's read outputs to columns, or read polarity | Record the exact permutation or inversion. A fixed permutation or inversion can be compensated by loading weights in the corrected order; confirm with ARI-04 and ARI-07 before relying on it. |
| Memory passes, arithmetic fails | Adder trees, sign handling, accumulators | ARI-04 and ARI-05 locate the column, bit plane or sign; ARI-03 checks the accumulator range |
| Arithmetic right over SPI, wrong over the link | Link receiver, frame timing | Lower LINK_CLK; check CNT_CRC, CNT_BAD, CNT_OVERRUN; scope LINK_D against LINK_CLK |
| RESULT registers right, return frames wrong | Transmitter or output pads | LNK-06 timing; check each lane's sync word alone |
| Failures only at high CLK | Timing path | Shmoo (CHR-01) to map it; run at the passing frequency |
| Failures only at low VDD | Margin, possibly the memory | Compare CHR-01 with CHR-02 |
| Results differ between runs | Marginal timing or supply noise | Lower CLK, raise VDD within limits, check decoupling and VDD at the pins |

## 10. Limits of this plan

- **Internal behaviour that cannot be seen from the pins.** A few of the chip's internal timing rules (for example, that a compute never starts while a memory row is being written) have no effect at the pins in normal use. They are covered only by verification before fabrication.
- **No scan chain or boundary scan.** A fault inside the logic is located only through the registers, the self-tests and the directed tests above, not to a single flip-flop.
- **Single supply.** Core and pad current cannot be separated by measurement; only the differential method of section 7.11 isolates the compute energy.
- **Expected current, maximum frequency and margins are not predicted here.** They are measured.
- **Temperature.** There is no temperature testing: every result is at room temperature, which is logged.
- **The test bench itself** (board, translators, FPGA) can limit the highest frequency that can be tested. Results at that limit are reported as "at least".

## 11. Schedule

| When | What |
|---|---|
| By submission (2026-12-14) | This plan matches the submitted design |
| After submission | Board design (once the package is known); FPGA bench firmware and host software; bench rehearsal against the design on an FPGA; photograph workload vectors recorded |
| Before chips return (expected 4 to 6 months after submission) | Board assembled and checked without a chip; full sequence rehearsed |
| Chips returned | Sections 7.1 to 7.9 on every die (screen), then the characterization subset |

## 12. References in this repository

| Document | Path |
|---|---|
| Chip specification (pins, frames, registers, self-test, JTAG, operating rules, measured model values) | `docs/V2_SPEC.md` |
| Reference model of the chip, and its scenarios and pin traces | `model/chip_v2/` |
| Recorded keyword-spotting sample vectors | `model/chip_v2/vectors/kws_word418_sample.npz` |
| Replaying a vector file through the reference model's pins | `python3 -m model.chip_v2.vectors FILE` |
| Recording a whole word's vectors | `python3 -m model.kws.vectors` |
