# v2 requirements matrix

**Generated** by `python3 -m model.chip_v2.verify matrix` from `model/chip_v2/requirements.py`. Do not edit by hand. The plan that explains it is `docs/V2_VERIFICATION_PLAN.md`.

115 requirements: 100 covered, 6 flow, 5 needs L1, 4 one method.

Status: **covered** = at least two of (directed check, random invariant, fault caught at the pins); **one method** = only one of them; **needs L1** = not visible at the pins, needs a test inside the chip; **flow** = checked by the physical flow; **GAP** = nothing yet.

| ID | Spec | Requirement | Kind | Checks | Random | Faults | Planned | Status |
|---|---|---|---|---|---|---|---|---|
| PIN-01 | 1 | 22 pads with the names and directions of the pin table | phys | 0 | 0 | 0 | 2 | flow |
| PIN-02 | 1 | Pulls: down on LINK_CLK and LINK_D, up on SPI_CS_N and TMS | phys | 0 | 0 | 0 | 2 | flow |
| CLK-01 | 2 | LINK_D is sampled on the LINK_CLK rising edge | func | 9 | 1 | 1 | 0 | covered |
| CLK-02 | 2 | SPI mode 0: MOSI sampled on the rising edge, MISO changes on the falling edge | func | 2 | 0 | 1 | 0 | covered |
| CLK-03 | 2 | JTAG: TMS and TDI sampled on the rising edge of TCK, TDO changes on the falling edge | func | 2 | 0 | 1 | 0 | covered |
| CLK-04 | 2 | Correct at any LINK_CLK period not shorter than CLK's, at any phase | func | 2 | 1 | 0 | 0 | covered |
| CLK-05 | 2 | Correct at any SCLK period not shorter than CLK's, at any phase | func | 4 | 1 | 0 | 0 | covered |
| CLK-06 | 2 | DEBUG, MBIST and CBIST correct at any TCK period of at least 4 CLK periods | func | 2 | 2 | 0 | 0 | covered |
| CLK-07 | 2, 10 | IDCODE and BYPASS work with CLK stopped | func | 2 | 0 | 1 | 0 | covered |
| RST-01 | 2 | RST_N low resets every domain asynchronously; the outputs are 0 in reset | func | 1 | 1 | 0 | 1 | covered |
| RST-02 | 2 | The core leaves reset on the second CLK rising edge after RST_N rises | func | 1 | 0 | 1 | 1 | covered |
| RST-03 | 2 | The SPI and JTAG domains need no clock to leave reset | func | 2 | 0 | 1 | 0 | covered |
| RST-04 | 2, 3 | Reset is complete: every flop, the held words included; after reset the chip equals a fresh one | func | 2 | 1 | 4 | 2 | covered |
| RST-05 | 2 | Reset does not touch the weight array; the self-test overwrites it | inside | 0 | 0 | 0 | 1 | needs L1 |
| LNK-01 | 2 | The link leaves reset two LINK_CLK rising edges after the core raises its enable | func | 1 | 0 | 1 | 0 | covered |
| LNK-02 | 2 | Three-state link handshake: no short pulse missed, no entry read twice, no false overflow | func | 1 | 2 | 3 | 0 | covered |
| LNK-03 | 2 | The receiver is in hunt whenever the link is not Up | func | 3 | 0 | 1 | 1 | covered |
| LNK-04 | 2, 8.1 | STATUS.link_ready reports that the link domain is out of reset | func | 0 | 2 | 1 | 0 | covered |
| CDC-01 | 3 | Exactly five crossings; nothing else crosses a clock domain | inside | 0 | 0 | 0 | 2 | needs L1 |
| CDC-02 | 3 | X1: a symbol is used on the third CLK edge after the LINK_CLK edge that sampled it | func | 1 | 0 | 1 | 0 | covered |
| CDC-03 | 3 | X1: FIFO pointers cross Gray coded through two flops | func | 1 | 0 | 1 | 1 | covered |
| CDC-04 | 3 | X2: the core acts on an SPI word on the third CLK edge after the SCLK edge that completed it | func | 1 | 0 | 1 | 0 | covered |
| CDC-05 | 3 | X3: read data is loaded on the byte-completing SCLK edge and is stable 4 CLK periods before | func | 2 | 0 | 1 | 0 | covered |
| CDC-06 | 3 | X4: JTAG request and answer; the answer is ready 3 CLK plus 2 TCK periods after Update-DR | func | 2 | 0 | 2 | 0 | covered |
| CDC-07 | 3 | X5: a burst ends when the core sees SPI_CS_N high | func | 3 | 0 | 1 | 0 | covered |
| CDC-08 | 3 | A held word is never read while it changes | func | 3 | 1 | 0 | 0 | covered |
| CDC-09 | 3 | A write takes effect on the third CLK edge after its last SCLK edge | func | 1 | 0 | 1 | 0 | covered |
| CDC-10 | 3 | The FIFO holds at most 2 symbols; a write while full loses the symbol and sets fifo_ovf | func | 2 | 1 | 0 | 0 | covered |
| RX-01 | 4 | Frame: sync 0xA, two header symbols, 8 or 64 payload symbols, two CRC symbols | func | 8 | 1 | 2 | 0 | covered |
| RX-02 | 4 | CRC-8: 0x1D, start 0xFF, a symbol at a time, bit 3 first, over header and payload | func | 3 | 0 | 5 | 0 | covered |
| RX-03 | 4 | A frame of type 1, 2 or 3 is bad: CNT_BAD counts, the receiver recovers | func | 2 | 0 | 2 | 0 | covered |
| RX-04 | 4 | Payload order: lane k feeds rows 8k to 8k + 7, row 8k + 7 first, bit 0 first; 1 bit per row at P = 1 | func | 10 | 0 | 2 | 0 | covered |
| RX-05 | 4 | Frames may follow each other with no idle symbol | func | 1 | 0 | 1 | 0 | covered |
| RX-06 | 4 | Overrun: a frame that finds the chain busy, a self-test, or a burst is skipped whole and counted | func | 4 | 0 | 3 | 0 | covered |
| RX-07 | 4 | CRC failure: CNT_CRC counts, the chain is freed, the receiver recovers | func | 5 | 0 | 1 | 0 | covered |
| RX-08 | 4 | Recover: 72 idle symbols in a row, any other symbol restarts the count | func | 4 | 0 | 3 | 0 | covered |
| RX-09 | 4, 8 | act_spi sends the receiver to hunt and link frames are ignored | func | 2 | 0 | 2 | 0 | covered |
| RX-10 | 4 | A stray sync followed by idle never computes (non-zero CRC start) | func | 1 | 0 | 1 | 0 | covered |
| RX-11 | 4, 7 | The 6-bit sequence number goes from the frame to its result | func | 9 | 1 | 2 | 0 | covered |
| RX-12 | 4 | A corrupted sync: each false frame ends as section 4 says; about 1 in 1,100 computes on garbage | perf | 2 | 0 | 1 | 0 | covered |
| PIPE-01 | 5 | Start: accumulators empty or captured on the same edge, and the write controller idle | func | 2 | 0 | 2 | 0 | covered |
| PIPE-02 | 5 | Compute: P edges, one bit plane each, least significant first, weight MSB column subtracted | func | 12 | 2 | 4 | 0 | covered |
| PIPE-03 | 5, 9 | After the last compute edge: chain free, accumulators valid, one DONE pulse on STATUS | func | 0 | 1 | 1 | 1 | covered |
| PIPE-04 | 5 | Capture: when the accumulators are valid and the transmitter is idle or on its last bit; RESULT0 to 3 take the raw values | func | 1 | 0 | 2 | 0 | covered |
| PIPE-05 | 5, 11 | Per-vector period: 22 at P = 1 raw, 16 requantized, 67 + P at P = 2 to 8, 13 silent at P = 1 | func | 7 | 1 | 0 | 0 | covered |
| PIPE-06 | 5 | Busy is exactly: chain not free, result waiting, self-test, burst, row write, row read waiting, activations shifting; a draining transmitter is not busy | func | 5 | 0 | 5 | 0 | covered |
| PIPE-07 | 5 | A write to P, SHIFT, BIAS, MODE, WEIGHTS, ACT, START, BIST_CTRL or ROW_SEL while busy is ignored and sets err_busy | func | 6 | 0 | 4 | 1 | covered |
| PIPE-08 | 5 | The busy check is made when the write is carried out (bursts: on the command byte) | func | 1 | 1 | 1 | 0 | covered |
| PIPE-09 | 5 | A frame that starts on the checking edge counts as busy | func | 3 | 0 | 1 | 0 | covered |
| PIPE-10 | 5 | P travels with the vector; P written while a result drains does not change it | func | 3 | 0 | 1 | 0 | covered |
| RQ-01 | 6 | Requantize: 22-bit add of a 21-bit signed bias, ReLU, truncating shift, limit 255 | func | 3 | 1 | 7 | 0 | covered |
| RQ-02 | 6, 7 | A requantized result is type 1 with an 8-bit payload; RESULT0 to 3 stay raw | func | 1 | 0 | 1 | 0 | covered |
| TX-01 | 7 | Return frame: sync 1, 1, 0, 1 per lane, header bits 4 + j then j, result LSB first, CRC as header | func | 8 | 1 | 3 | 0 | covered |
| TX-02 | 7 | Width 13 + P raw, 8 requantized; frame length 8 + width | func | 10 | 1 | 1 | 0 | covered |
| TX-03 | 7 | The return header carries the sequence number of the frame, or the value written to START | func | 8 | 0 | 1 | 1 | covered |
| TX-04 | 7 | tx_silence: capture and RESULT still happen, nothing is sent | func | 2 | 0 | 1 | 0 | covered |
| TX-05 | 7 | LINK_TX changes on the CLK rising edge and is 0 when idle | func | 1 | 1 | 1 | 1 | covered |
| TX-06 | 5, 7 | Return frames may follow each other with no idle cycle | func | 2 | 0 | 1 | 0 | covered |
| TX-07 | 7 | A frame that has started is not changed by any write (MODE, SHIFT, BIAS) | func | 2 | 0 | 2 | 0 | covered |
| SPI-01 | 8 | Transaction: command byte, one dummy byte on reads, MSB first, wide registers MSB byte first | func | 1 | 0 | 1 | 0 | covered |
| SPI-02 | 8 | SPI_CS_N high ends a transaction; an unfinished byte, row or register is dropped; the next is aligned | func | 4 | 1 | 2 | 0 | covered |
| SPI-03 | 8 | Every register: address, width, access, and reset value as the register table | func | 2 | 0 | 2 | 1 | covered |
| SPI-04 | 8 | WEIGHTS: row 0 first, column 0 first; each 4 bytes write a row; an early stop keeps the rest | func | 5 | 0 | 2 | 1 | covered |
| SPI-05 | 8, 10 | ACT: row 31 first, bit 0 first; needs act_spi over SPI and over JTAG | func | 3 | 0 | 3 | 0 | covered |
| SPI-06 | 8 | START computes the vector in the chain with P from the register and its sequence number | func | 2 | 0 | 1 | 0 | covered |
| SPI-07 | 8 | RESULT0 to 3: last captured raw result, sign-extended to 24 bits | func | 2 | 0 | 1 | 0 | covered |
| SPI-08 | 8 | CNT_CRC, CNT_OVERRUN, CNT_BAD count and stop at 255 | func | 4 | 0 | 4 | 1 | covered |
| SPI-09 | 8 | CLEAR: bit 0 counters, bit 1 sticky flags, bit 2 abandons a vector still loading; never refused | func | 4 | 0 | 3 | 0 | covered |
| SPI-10 | 8 | BIST_CTRL, BIST_STAT encoding, BIST_ROW, CBIST_SIG | func | 2 | 0 | 2 | 0 | covered |
| SPI-11 | 8, 8.2 | ROW_SEL reads the row through the compute port once the write port is idle; ROW_DATA returns it | func | 2 | 2 | 2 | 0 | covered |
| SPI-12 | 8 | gate_off makes every result zero | func | 1 | 0 | 1 | 0 | covered |
| SPI-13 | 8.1 | STATUS bits 0 to 7 as section 8.1; bits 15:8 read 0 | func | 3 | 0 | 6 | 0 | covered |
| SPI-14 | 8 | Addresses 0x1A to 0x7F read 0; a write to one does nothing and is not flagged | func | 2 | 0 | 2 | 0 | covered |
| SPI-15 | 8 | A write-only register reads 0, and reading it does nothing | func | 2 | 0 | 1 | 0 | covered |
| SPI-16 | 8 | A write to a read-only register is ignored and not flagged | func | 1 | 0 | 1 | 0 | covered |
| SPI-17 | 8 | Reserved bits are ignored when written and read 0; BIAS reads back with bits 23:21 zero | func | 1 | 0 | 6 | 0 | covered |
| SPI-18 | 8 | Bytes after a register's width are ignored on a write and read as 0 | func | 1 | 0 | 2 | 0 | covered |
| WP-01 | 8.2 | A row write is three cycles: set up, enable from a flop, hold; a second write waits | inside | 0 | 1 | 1 | 2 | needs L1 |
| WP-02 | 8.2 | The activation gate is closed whenever the write controller is not idle | inside | 1 | 1 | 2 | 2 | needs L1 |
| BIST-01 | 9 | Out of reset the memory test runs, then the compute test | func | 3 | 0 | 1 | 0 | covered |
| BIST-02 | 9 | Memory test: the march of section 9; finds a stuck or coupled cell and names its row | func | 3 | 0 | 2 | 1 | covered |
| BIST-03 | 9 | Compute test: the generator, 16 vectors at P = 8, signature 0x29E000BC from plain arithmetic | func | 4 | 0 | 2 | 0 | covered |
| BIST-04 | 9 | Timeout: 8,192 cycles per test, then reported, and STATUS high | inside | 0 | 0 | 0 | 1 | needs L1 |
| BIST-05 | 9 | Any write's command byte aborts a running test; a row write under way finishes; the write is carried out | func | 5 | 0 | 1 | 0 | covered |
| BIST-06 | 9 | A frame during a commanded test is an overrun | func | 1 | 0 | 1 | 0 | covered |
| BIST-07 | 9 | Reads are always answered, during a test too | func | 2 | 0 | 1 | 1 | covered |
| BIST-08 | 9 | STATUS pin: low during the reset self-test, CLK / 65,536 after a pass, high after a fail, then DONE pulses | func | 6 | 0 | 3 | 0 | covered |
| JT-01 | 10 | 3-bit IR; reset (RST_N or five TMS-high edges) selects IDCODE | func | 2 | 0 | 1 | 0 | covered |
| JT-02 | 10 | IDCODE is 0xDC1A0002 with bit 0 forced to 1 | func | 1 | 0 | 2 | 0 | covered |
| JT-03 | 10 | BYPASS is one bit, for 111 and every unused code (no EXTEST or SAMPLE/PRELOAD, by design) | func | 2 | 0 | 2 | 1 | covered |
| JT-04 | 10 | DEBUG: {write, addr, data}; answers one scan behind with a ready bit | func | 4 | 0 | 2 | 0 | covered |
| JT-05 | 10 | MBIST and CBIST instructions start a test and report it | func | 2 | 0 | 1 | 0 | covered |
| JT-06 | 10 | DEBUG WEIGHTS writes the row in ROW_SEL and steps ROW_SEL modulo 32; DEBUG ACT carries four bytes | func | 2 | 0 | 2 | 0 | covered |
| JT-07 | 10 | SPI and JTAG writing on one CLK edge: SPI wins, JTAG is dropped and flagged | func | 1 | 0 | 1 | 0 | covered |
| JT-08 | 10 | The TAP follows the standard 16-state machine on every transition | func | 8 | 0 | 4 | 1 | covered |
| JT-09 | 10 | Capture-IR loads 001; BYPASS captures 0 | func | 2 | 0 | 2 | 0 | covered |
| JT-10 | 10 | TDO holds the last bit shifted out outside Shift-DR and Shift-IR (a stated difference from IEEE 1149.1) | func | 1 | 0 | 1 | 0 | covered |
| ENV-01 | 11 | Rule 1, LINK_CLK continuous and no faster than CLK; broken: fifo_ovf | env | 1 | 1 | 0 | 0 | covered |
| ENV-02 | 11 | Rule 2, frame pacing; broken: dropped and counted, never corrupted | env | 2 | 2 | 0 | 0 | covered |
| ENV-03 | 11 | Rule 3, 72 idle symbols before a resend | env | 1 | 0 | 2 | 0 | covered |
| ENV-04 | 11 | Rule 4, settings written only when not busy; broken: refused and flagged | env | 1 | 2 | 0 | 0 | covered |
| ENV-05 | 11 | Rule 5, SCLK no faster than CLK, TCK at least 4 CLK | env | 1 | 1 | 0 | 0 | covered |
| ENV-06 | 11 | Rule 6, each return lane lined up by its own sync word | env | 8 | 1 | 0 | 0 | covered |
| ENV-07 | 11 | Rules 7 to 9 and the recovery procedure | env | 2 | 1 | 0 | 0 | covered |
| ENV-08 | 2, 11 | Rule 10, RST_N low for at least 4 CLK periods | env | 1 | 1 | 0 | 0 | covered |
| ENV-09 | 8, 11 | Rule 11, SPI_CS_N high for at least 2 CLK periods between transactions | env | 1 | 1 | 0 | 0 | covered |
| ENV-10 | 2, 11 | Rule 12, five TCK cycles with TMS high before the first JTAG scan | env | 2 | 1 | 0 | 0 | covered |
| PERF-01 | 12 | One weight set over SPI at SCLK = CLK: 1,040 cycles | perf | 1 | 0 | 0 | 0 | one method |
| PERF-02 | 12 | A workload of weight sets and vectors within 5% of the estimate | perf | 2 | 0 | 0 | 0 | one method |
| PERF-03 | 12 | Both demo photographs: scores exact through the pins, cycles within 3% of the estimate | perf | 3 | 0 | 0 | 0 | one method |
| PERF-04 | 12 | Chip test vectors of a real spoken word (model/chip_v2/vectors): every result exact at the pins | perf | 3 | 0 | 0 | 0 | one method |
| PHY-01 | 1 | Timing closes at 25 MHz at every corner, with the I/O timing of section 2 | phys | 0 | 0 | 0 | 2 | flow |
| PHY-02 | - | DRC, LVS, antenna clean | phys | 0 | 0 | 0 | 1 | flow |
| PHY-03 | - | The read-bitline mapping matches the macro's physical ports | phys | 0 | 0 | 0 | 2 | flow |
| PHY-04 | - | The macro timing library is characterized, write arcs included | phys | 0 | 0 | 0 | 1 | flow |

## Planned tests

- **PIN-01** L4: script compares info.yaml and the top-level ports with the pin table
- **PIN-01** L3: gate-level replay through the pad ring
- **PIN-02** L4: script reads the pad configuration in the top level
- **PIN-02** L3: replay with the inputs left floating
- **RST-01** L2: assert reset at random instants in every state, outputs checked during reset
- **RST-02** L2: directed test, release at 8 phases of CLK, first STATUS change counted
- **RST-04** L1: every module's reset values against its golden model
- **RST-04** L2: the cocotb replay runs every trace on one chip back to back
- **RST-05** L1: array content survives RST_N with the self-test held off
- **LNK-03** L2: frame cut by switching the link off, then a frame right after it comes up
- **CDC-01** L4: script on the synthesized netlist lists every flop-to-flop path between domains and matches it to X1 to X5
- **CDC-01** L4: every synchronizer is two flops with no logic between
- **CDC-03** L4: formal proof on the FIFO: one pointer bit changes per write, never full plus one
- **PIPE-03** L2: DONE pulses counted against vectors completed, every P
- **PIPE-07** L2: every guarded register written while busy, from SPI and from JTAG (9 x 2 cases)
- **TX-03** L2: START sequence numbers 0 to 63 checked in the return header
- **TX-05** L2: every trace replays edge for edge (cocotb/v2)
- **SPI-03** L2: read every address after reset, compare with the reset column
- **SPI-04** L2: bursts of 4, 9, 60 and 127 bytes, untouched rows read back
- **SPI-08** L2: CNT_BAD stops at 255
- **WP-01** L1: write controller test with an assertion on every cycle of every write
- **WP-01** L4: formal proof: enable from a flop, address and data stable around it
- **WP-02** L1 and L2: assertion on the gate and the controller state, every cycle
- **WP-02** L4: formal proof of the same
- **BIST-02** L1: march sequence compared step by step with the golden model
- **BIST-04** L1: force the test's state machine to stall (cocotb force), check the timeout and the report
- **BIST-07** L2: read every readable register while each test runs
- **JT-03** L1: every IR code 000 to 111, data register length measured
- **JT-08** L1: all 32 state transitions of the TAP, including both pause states
- **PHY-01** L4: STA across corners (merge gate 3)
- **PHY-01** L3: timing-annotated replay of the quick traces at the slow and fast corners
- **PHY-02** L4: LibreLane signoff (merge gate 3)
- **PHY-03** L4: Karan's layout check (merge gate 4)
- **PHY-03** L6: memory test and ROW_DATA on silicon
- **PHY-04** L4: Karan's characterization (merge gate 5)

## Audit

- Checks not traced to any requirement: 0
- Faults not traced to any requirement: 0
- Broken references: 0
- The photographs were not run for this matrix.
