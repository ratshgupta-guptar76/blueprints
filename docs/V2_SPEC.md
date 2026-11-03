# DCIM v2 specification

**Draft 0.4, 2026-10-14.** This is the exact behaviour the v2 chip must have at its pins, cycle by cycle. `docs/V2_DESIGN_GUIDE.md` explains each feature and `docs/DESIGN_RATIONALE.md` says why it exists; this document fixes the values those two left open. Where they disagree with this document, this document is the intended behaviour and they need updating.

A pin-level, cycle-accurate model of this specification lives in `model/chip_v2/`. Every number in section 12 is measured on that model, and section 13 lists what building and then verifying the model changed in this text. When the model and this text disagree, one of them is wrong and both must be brought back in line.

Every value here is fixed for the purpose of writing RTL against it. The ones that are Karan's to confirm or change are collected in section 14.

---

## 1. Pins

22 pads. Unchanged from design guide 6.5.

| Pin | Dir | Pull | Clock domain | Purpose |
|---|---|---|---|---|
| VDD, VSS | supply | | | One supply, one ground |
| CLK | in | | core | Core clock, 25 MHz nominal |
| RST_N | in | | all | Reset, active low, asynchronous |
| LINK_CLK | in | down | link | Clock that travels with LINK_D |
| LINK_D[3:0] | in | down | link | Four input lanes |
| LINK_TX[3:0] | out | | core | Four return lanes |
| SPI_SCLK | in | | SPI | SPI clock |
| SPI_CS_N | in | up | SPI | SPI chip select, active low |
| SPI_MOSI | in | | SPI | SPI data in |
| SPI_MISO | out | | SPI | SPI data out |
| TCK | in | | JTAG | JTAG clock |
| TMS | in | up | JTAG | JTAG mode select |
| TDI | in | | JTAG | JTAG data in |
| TDO | out | | JTAG | JTAG data out |
| STATUS | out | | core | Self-test result, then one pulse per finished compute |

## 2. Clocks and reset

| Clock | Rule |
|---|---|
| CLK | Free running. Everything that computes is in this domain. There is no minimum frequency: the STATUS heartbeat (CLK / 65,536) and the self-test timeout (8,192 cycles) scale with it. |
| LINK_CLK | Runs continuously while `MODE.link_en` is 1. Its period is never shorter than CLK's (contract 16). The FPGA changes LINK_D on the falling edge; the chip samples on the rising edge. |
| SPI_SCLK | SPI mode 0: idle low, MOSI sampled on the rising edge, MISO changes on the falling edge. Toggles only while SPI_CS_N is low. Its period is never shorter than CLK's. |
| TCK | Standard JTAG: TMS and TDI sampled on the rising edge, TDO changes on the falling edge. For DEBUG, MBIST, and CBIST its period is at least 4 CLK periods. |

**Reset.** RST_N low resets every domain asynchronously. It is held low for at least 4 CLK periods (section 11 rule 10).

| Domain | Comes out of reset |
|---|---|
| Core | Two CLK rising edges after RST_N goes high (two-flop synchronizer). |
| Link | Held in reset while the link is off. Released two LINK_CLK rising edges after the core raises its enable. See "Switching the link on and off" below. |
| SPI | As soon as RST_N is high. No clock is needed: SPI_SCLK does not run between transactions, so nothing here may wait for it. SPI_CS_N high resets the bit counter, so every transaction starts aligned. |
| JTAG | As soon as RST_N is high. Five TCK rising edges with TMS high also reset the TAP. RST_N releases this domain with no synchronizer, so a TCK edge at that moment can leave the TAP in any state: the JTAG master clocks TMS high five times before its first scan (section 11 rule 12). |

**Reset is complete.** Every flop is reset, including the registers that hold a word for another domain (section 3). After reset the chip is indistinguishable at its pins from one that has just powered up, whatever it was doing before. The one thing reset does not touch is the weight array, whose content is unknown after power-up and is overwritten by the self-test after any reset.

**Switching the link on and off.** The two sides of the link FIFO are in different clock domains and must be reset together. The core keeps a three-state view of the link:

| State | Core | Enable sent to the link domain |
|---|---|---|
| Down | Not reading. Its read pointer follows the synchronized write pointer, so the FIFO is empty when the link comes up. Goes to Up when `link_en` is 1 and the link reports that it is out of reset. | `link_en` |
| Up | Reads the FIFO. Goes to Closing when `link_en` is written to 0. | 1 |
| Closing | Not reading. Goes to Down only when the link reports that it is in reset. | 0, whatever `link_en` now says |

So a short low pulse on `link_en` is never missed by a slow LINK_CLK, no FIFO entry is ever read twice, and switching the link off cannot raise the overflow flag. LINK_CLK must keep running until `STATUS.link_ready` reads 0. Whenever the link is not Up the receiver is in hunt.

## 3. Clock-domain crossings

There are exactly five, and nothing else may cross. Each is listed with every signal it uses.

| # | From, to | Mechanism | Latency |
|---|---|---|---|
| X1 | Link to core: every sampled symbol | Asynchronous FIFO, 8 entries of 4 bits. Gray-coded write pointer to the core and read pointer to the link, each through two flops. Three single-bit signals go with it, each through two flops: the enable level (core to link), the ready level (link to core), and an overflow toggle (link to core). | A symbol is used by the core on the third CLK rising edge after the LINK_CLK edge that sampled it (2 to 3 CLK periods). |
| X2 | SPI to core: one whole word (a byte, or a 32-bit weight row) | The word is held in a register in the SPI domain and a toggle flips. The core synchronizes the toggle (two flops), detects the change, and reads the held word. | The core acts on the word on the third CLK rising edge after the SCLK edge that completed it. |
| X3 | Core to SPI: read data | The core places each byte to be sent in a holding register. The SPI domain loads the holding register into its output shift register on the SCLK rising edge that completes a byte, the same edge that fires X2. The core then has a whole byte time to put the next byte there. | Stable at least 4 CLK periods before it is used, at any SCLK rate. |
| X4 | JTAG to core and back: one DEBUG, MBIST, or CBIST request | Request word and toggle on Update-DR, synchronized as in X2. The core answers into a holding register and flips an acknowledge toggle, synchronized into TCK (two flops). | A response is ready 3 CLK periods plus 2 TCK periods after Update-DR. The captured word carries a ready bit. |
| X5 | SPI to core: the level of SPI_CS_N | Two-flop synchronizer. The core uses it only to know that a weight burst has ended. | 2 CLK periods. |

Rules that make these safe:

- **Only whole words cross, never a single data bit.** Synchronizers carry toggles and Gray pointers only.
- **A held word must not change while the other side may read it.** For X2 that is guaranteed by the SCLK period rule: the next byte completes at least 8 CLK periods later. The model checks every such read and reports any that happens within one CLK period of the word changing.
- **Every register that holds a word for another domain is reset to 0** (the SPI word, the read-data holding register, the JTAG request and response).
- **A write has not happened when its transaction ends.** It takes effect on the third CLK edge after its last SCLK edge. The FPGA must not read a register back, or rely on a new setting, sooner than 4 CLK periods after the transaction.
- **The core reads the FIFO whenever it is not empty.** With LINK_CLK no faster than CLK the FIFO then holds at most 2 symbols (**Measured**, section 12). If it is ever written while full, the symbol is lost and `STATUS.fifo_ovf` is set.

## 4. Inbound link frames

A **symbol** is the four bits sampled on one LINK_CLK rising edge: bit k is input lane k. Idle is symbol 0.

| Field | Symbols | Content |
|---|---|---|
| Sync | 1 | `0xA` |
| Header | 2 | First `{type[1:0], seq[5:4]}`, then `seq[3:0]` |
| Payload | 8 if P = 1, else 64 | Bit k of each symbol is the next bit of sub-chain k |
| CRC | 2 | CRC-8 of header and payload, high four bits first |

- **Types.** 0 is an activation vector. 1 is reserved (weights over the link). 2 and 3 are unused. A frame of any type but 0 is a bad frame.
- **CRC-8.** Polynomial x^8 + x^4 + x^3 + x^2 + 1 (`0x1D`), initial value `0xFF`, no reflection, no final XOR. Bits are taken a symbol at a time, bit 3 first. The initial value is not zero so that a stuck-at-zero link after a stray sync does not look like a valid frame.
- **Payload order.** Sub-chain k is rows 8k to 8k + 7. Its input enters row 8k and is pushed toward row 8k + 7, as in v1. At full width each row holds 8 bits, least significant first, so lane k carries row 8k + 7 first, bit 0 first, and row 8k last. At P = 1 each row holds one bit and lane k carries row 8k + 7 first.
- **Frames may follow each other with no idle symbol between them.**

**What the receiver does,** one symbol per CLK cycle:

1. **Hunt.** Discard symbols until one equals `0xA`.
2. **Header.** Take two symbols.
3. **Payload.** At the first payload symbol, if the activation chain is free, no self-test is running, and no SPI burst is in progress, shift every payload symbol into the chain. Otherwise the frame is an **overrun**: its payload and CRC symbols are counted off and discarded, `CNT_OVERRUN` increments, and the receiver returns to hunt.
4. **CRC.** If it matches, the vector is valid and will compute. If not, `CNT_CRC` increments, the chain is marked free (its contents are junk), and the receiver goes to **recover**.
5. **Recover.** Discard everything until 72 idle symbols in a row have been seen, then hunt. Any other symbol restarts the count. A bad frame type also leads here, with `CNT_BAD` incremented.

The receiver is forced back to hunt whenever the link is not Up (section 2) or `MODE.act_spi` is 1.

**A known weakness of the one-symbol sync.** If the sync symbol itself is corrupted, the frame is not recognised and the receiver keeps hunting through its payload. Any payload symbol equal to `0xA` then starts a false frame. About three in four false frames have a type other than 0 and are counted as bad (`CNT_BAD`); the rest fail the CRC 255 times in 256. Either way the receiver waits for 72 idle symbols. The remainder compute on garbage and return a result whose sequence number the FPGA is not expecting and must discard: about one corrupted sync in 1,100 (section 12).

## 5. The pipeline

Three places hold a vector or its result.

| Place | States | Free when |
|---|---|---|
| Activation chain | free, loading, loaded, computing | Its last compute cycle has finished, or its frame failed the CRC |
| Accumulators | empty, valid | The transmitter has captured the result |
| Transmitter | idle, sending | The last bit of the return frame has been sent |

With E the CLK edge that consumes the last CRC symbol of a good frame:

| Edge | What happens |
|---|---|
| E | The vector is valid (chain: loaded). |
| First edge after E at which the accumulators are empty, or are being captured on that same edge, and the write controller is idle | **Start.** Accumulators are cleared. The chain's copy of P is the one latched at the first payload symbol. |
| The next P edges | **Compute,** one bit plane per edge, least significant first. The activation gate is open only on these edges. |
| The edge after the last compute edge | The chain is free. The accumulators are valid. STATUS pulses (DONE). |
| First edge at which the accumulators are valid and the transmitter is idle or has its last bit on the lanes | **Capture.** The result (requantized or raw) and its header go to the transmitter, and the raw values go to `RESULT0..3`. The accumulators are empty again. |

- **Chain occupied** (first payload symbol to chain free): payload + 2 + 1 + P cycles when nothing has to wait. That is 12 at P = 1 and 75 at P = 8.
- **Busy** means any of: the chain is not free; the accumulators are valid; self-test is running; an SPI WEIGHTS or ACT burst is in progress (from its command byte until SPI_CS_N is seen high); a row write is in progress or waiting; a row read is waiting for the write port; activations from SPI or JTAG are still shifting in. A draining transmitter is **not** busy. `STATUS.busy` reports this.
- **Writes while busy.** A write to P, SHIFT, BIAS, MODE, WEIGHTS, ACT, START, BIST_CTRL, or ROW_SEL while busy is ignored and sets `STATUS.err_busy`.
- **When the check is made.** On the CLK edge that carries the write out: for a register, the edge that takes its last data byte, not its command byte, because a frame can begin in the 8 or more cycles between the two. For a WEIGHTS or ACT burst, on the command byte, and the burst then holds the chip busy until SPI_CS_N is seen high. A JTAG write is checked and carried out on one edge.
- **A frame that starts on that same edge counts.** If the first payload symbol of a frame is accepted on the edge that makes the check, the chip is busy for that check. So a write and a frame that meet on one edge never both go ahead: either the write was a cycle earlier and the frame sees its effect, or the frame wins and the write is refused.
- **P travels with the vector.** One copy is taken at the first payload symbol (load mode, compute). The transmitter takes the return width at capture and keeps it until the frame has gone. P cannot be written between those two points, because the chip is busy throughout, so one P governs a vector from its first symbol to its last returned bit, and a write to P while a result drains (which is allowed) cannot change that result's width.

## 6. Requantize

Optional (`MODE.requant`). Applied at capture, to each of the four results r (21-bit signed):

1. t = r + BIASj, 22-bit signed. It cannot overflow, so there is no saturation here.
2. t = max(t, 0).
3. t = t >> SHIFT, truncating.
4. out = min(t, 255).

`BIASj` is 21-bit signed. `SHIFT` is 4 bits (0 to 15). The return payload is then 8 bits per lane.

Requantize must be off for a pass whose result is a partial sum, for a result whose sign is needed, and for final scores.

## 7. Return frames

Sent on LINK_TX, one bit per lane per CLK cycle, changing on the CLK rising edge. Idle is 0. Width is 13 + P bits raw (14 at P = 1, 21 at P = 8) and 8 bits requantized.

| Cycles | Each lane j carries |
|---|---|
| 0 to 3 | Sync word, in time order 1, 1, 0, 1 |
| 4 | Bit 4 + j of the header |
| 5 | Bit j of the header |
| 6 to 5 + width | Result j, least significant bit first |
| 6 + width | Bit 4 + j of the CRC |
| 7 + width | Bit j of the CRC |

- **Header:** `{type[1:0], seq[5:0]}`. Type 0 is a raw result, 1 a requantized one. `seq` is the sequence number of the frame that produced the result, or the value written to START.
- **CRC:** the same CRC-8, over the symbols of cycles 4 to 5 + width, where a symbol is `{lane 3, lane 2, lane 1, lane 0}` of one cycle.
- **Length:** 8 + width cycles: 22, 29, or 16.
- **The four lanes may reach the FPGA with different delays.** The FPGA finds each lane's start from that lane's own sync word, lines the lanes up, and only then forms symbols and checks the CRC.
- **`MODE.tx_silence`:** capture still happens and `RESULT0..3` are still written, but nothing is sent and the transmitter is idle again at once.
- **Return frames may follow each other with no idle cycle between them.** A result is captured on the edge that ends the previous frame (section 5), so at P = 1 raw the lanes carry one 22-cycle frame straight after another.
- **A frame that has started is not changed by any write.** Its type, width, payload and CRC are fixed at capture. A write to MODE (`requant`, `tx_silence`), SHIFT or BIAS while it goes out, which the busy rule allows, takes effect from the next capture.

## 8. SPI and the registers

**Transaction.** While SPI_CS_N is low, bits are taken most significant first.

| Byte | Write | Read |
|---|---|---|
| 0 | `{1, addr[6:0]}` | `{0, addr[6:0]}` |
| 1 | data | dummy, ignored |
| 2 onward | more data | data |

A register wider than one byte is sent most significant byte first. Bytes after a register's width are ignored on a write and read as 0. Raising SPI_CS_N ends the transaction; an unfinished byte, register, or weight row is dropped. SPI_CS_N then stays high for at least 2 CLK periods before the next transaction (section 11 rule 11).

| Addr | Name | Bytes | Access | Reset | Content |
|---|---|---|---|---|---|
| 0x00 | ID | 4 | R | `0xDC1A0002` | Identity |
| 0x01 | STATUS | 2 | R | | Section 8.1 |
| 0x02 | MODE | 1 | RW | 0 | bit 0 `link_en`, 1 `act_spi`, 2 `gate_off`, 3 `tx_silence`, 4 `requant` |
| 0x03 | P | 1 | RW | 7 | bits 2:0 = P - 1 |
| 0x04 | SHIFT | 1 | RW | 0 | bits 3:0 |
| 0x05 to 0x08 | BIAS0 to BIAS3 | 3 | RW | 0 | 21-bit signed, in the low 21 bits |
| 0x09 | START | 1 | W | | bits 5:0 = sequence number. Computes the vector now in the chain. |
| 0x0A | WEIGHTS | up to 128 | W | | A weight set: row 0 first, within a row column 0 first (weight 0 bit 0 up to weight 3 bit 7). The v1 order. Each completed 4 bytes writes one row; a burst may stop early and leaves the remaining rows as they were. |
| 0x0B | ACT | 32, or 4 at P = 1 | W | | One vector through the re-joined chain, in the v1 order: row 31 first, within a row bit 0 first. Needs `act_spi` = 1, over SPI and over JTAG; without it the write is ignored and flagged. |
| 0x0C to 0x0F | RESULT0 to RESULT3 | 3 | R | 0 | Last captured raw result, sign-extended to 24 bits |
| 0x10 | CNT_CRC | 1 | R | 0 | CRC failures, stops at 255 |
| 0x11 | CNT_OVERRUN | 1 | R | 0 | Overruns, stops at 255 |
| 0x12 | CNT_BAD | 1 | R | 0 | Bad frame types, stops at 255 |
| 0x13 | CLEAR | 1 | W | | bit 0 clears the three counters, bit 1 clears the sticky STATUS flags, bit 2 abandons a vector that is still loading from the link (the chain is freed and the receiver goes to recover). Never refused. |
| 0x14 | BIST_CTRL | 1 | W | | bit 0 run memory test, bit 1 run compute test |
| 0x15 | BIST_STAT | 1 | R | | bits 1:0 memory test, 3:2 compute test: 0 running, 1 pass, 2 fail, 3 aborted or not run |
| 0x16 | BIST_ROW | 1 | R | | First failing row of the memory test |
| 0x17 | CBIST_SIG | 4 | R | | Compute test signature |
| 0x18 | ROW_SEL | 1 | RW | 0 | Row to read back. Writing it reads the row, one cycle, as soon as the write controller is idle. |
| 0x19 | ROW_DATA | 4 | R | | That row's 32 stored bits, read through the compute port. Only when not busy. |

**Addresses and bits the table does not define.**

- Addresses 0x1A to 0x7F read 0. A write to one does nothing and is not flagged.
- A write-only register (START, WEIGHTS, ACT, CLEAR, BIST_CTRL) reads 0, and reading it does nothing.
- A write to a read-only register is ignored and not flagged.
- Reserved bits are ignored when written and read 0: MODE 7:5, P 7:3, SHIFT 7:4, ROW_SEL 7:5, BIAS 23:21, START 7:6, CLEAR 7:3, BIST_CTRL 7:2. So BIAS reads back with bits 23:21 zero, while RESULT is sign-extended.
- Each of these is still a write for section 9: its command byte stops a running self-test.

`gate_off` = 1 keeps the activation gate closed during compute (design guide 5.16), so every result is zero. `act_spi` = 1 joins the four sub-chains into one and takes activations from ACT; link frames are then ignored and the receiver stays in hunt.

**Why CLEAR bit 2 exists.** A vector that is loading keeps the chip busy until its last symbol arrives. If the link stops in the middle of a frame (LINK_CLK dies, the module is unplugged), that symbol never comes, and every guarded write, including the MODE write that would switch to SPI, is refused. Without bit 2 the only way out is RST_N, and the self-test that follows a reset overwrites the weights.

### 8.1 STATUS

| Bit | Name | Meaning |
|---|---|---|
| 0 | busy | Section 5 |
| 1 | chain_loaded | A valid vector is waiting to compute |
| 2 | acc_valid | A result is waiting for the transmitter |
| 3 | tx_busy | A return frame is being sent |
| 4 | err_busy | Sticky: a write was ignored because the chip was busy |
| 5 | fifo_ovf | Sticky: the link FIFO was written while full |
| 6 | link_ready | The link domain is out of reset |
| 7 | selftest_done | The reset self-test has finished or been aborted |

Bits 15:8 read as 0.

### 8.2 The write port

One write controller owns the array's write port. A row write takes three CLK cycles: address and data set up, wordline enable high (straight from a flop), then hold with address and data unchanged. A second row write waits for the first to finish. A weight set arrives one row every 32 SCLK periods, so the three cycles cost nothing.

**The activation gate is closed in every cycle in which the write controller is not idle.** Nothing else decides it: a compute does not start, and a row read does not happen, until the controller is idle. In normal use this never delays anything, because a write is refused while the chain is busy. It matters when a write stops a self-test that is in the middle of a row write: that row write finishes, and whatever the stopping write asked for waits for it.

## 9. Self-test

Out of reset, with nothing written, the chip runs the memory test and then the compute test.

**Memory test.** Row patterns `0x00000000`, `0xFFFFFFFF`, `0x55555555`, `0xAAAAAAAA`. For each of the two pairs (D, ~D): write D to every row ascending; ascending, read D then write ~D; ascending, read ~D then write D; descending, read D then write ~D; descending, read ~D then write D; read D from every row. A read is one cycle: the activation input is one-hot on that row and the 32 column sums are the row's bits. The first failing row is recorded.

**Compute test.** Weights and activations come from a 16-bit generator (x^16 + x^14 + x^13 + x^11 + 1, seed `0xACE1`), one bit per step. It writes one weight set (each row's 32 bits in column order), then runs 16 vectors at P = 8 with raw results. Each vector is 64 symbols shifted in through the four lanes as a frame's payload would be, four generator bits per symbol, lane 0's bit first. Each result is folded into a 32-bit signature register (the CRC-32 polynomial `0x04C11DB7`, seed `0xFFFFFFFF`), one 21-bit result per cycle, output 0 first. The signature must equal a constant that comes from the model, never from the RTL: `0x29E000BC`, which `model/chip_v2/chip.py` works out with ordinary arithmetic and the cycle model reproduces.

The compute test stores a single weight pattern, so it cannot see a cell stuck at the value that pattern happens to store there. Cells are the memory test's job; the compute test covers the chain, the trees, the combine, and the accumulators.

| Rule | |
|---|---|
| Timeout | 8,192 CLK cycles for each test |
| Abort | Any SPI or JTAG write, on its command byte. The test stops on the CLK edge that sees the command (3 edges after the byte completes) and reports "aborted". A row write already under way finishes (section 8.2); one still waiting is dropped. The write that caused the abort is then carried out under the ordinary busy rule, which it passes: over SPI its data arrives 8 or more cycles later, and over JTAG the test it stopped no longer counts. A link frame does not abort a test: `link_en` resets to 0, so none can arrive before a write, and a frame that arrives during a commanded test is an overrun. |
| Never blocks | Reads are always answered. A test that fails or times out leaves the chip fully usable. |
| After the test | The array holds test patterns. Weights must be written before use, as after any reset. |

**STATUS pin.** Low while the reset self-test runs. A square wave of CLK / 65,536 (about 381 Hz at 25 MHz) if both tests passed. High if either failed or timed out. After the first write or valid frame it becomes DONE: high for one CLK cycle each time a compute finishes.

## 10. JTAG

Instruction register: 3 bits. Reset selects IDCODE. Capture-IR loads `001`.

| IR | Instruction | Data register |
|---|---|---|
| `001` | IDCODE | 32 bits, `0xDC1A0002` with bit 0 forced to 1 as the standard requires |
| `010` | DEBUG | 40 bits |
| `011` | MBIST | 8 bits. Shifted in: bit 0 = start the memory test. Captured: `{first failing row[4:0], ready, state[1:0]}` |
| `100` | CBIST | 35 bits. Shifted in: bit 0 = start the compute test. Captured: `{ready, signature[31:0], state[1:0]}` |
| `111`, others | BYPASS | 1 bit, captures 0 |

**Not IEEE 1149.1 compliant, by design.** There is no boundary scan (a v2 non-goal), so EXTEST and SAMPLE/PRELOAD are absent and their codes select BYPASS. TDO changes only in Shift-DR and Shift-IR and otherwise holds the last bit shifted out; the standard drives it high-impedance there, but this pad is a plain output.

**DEBUG.** Shifted in: `{write, addr[6:0], data[31:0]}`. On Update-DR the request crosses to the core (X4). A write is carried out under the same busy rule as SPI. Captured on the next scan: `{ready, 7 zeros, read data[31:0]}`.

**Every answer is one scan behind.** DEBUG, MBIST, and CBIST all capture the answer to the *previous* Update, and only if `ready` is 1; otherwise the captured word is all zeros and the scan is simply repeated. So a read is two scans (ask, collect), and so is reading a test's result (a scan with start = 0 to ask, another to collect).

**Bursts over DEBUG.** A WEIGHTS write carries one row (bit c = column c), writes it to the row in ROW_SEL, and adds 1 to ROW_SEL, modulo 32 (row 31 is followed by row 0). An ACT write carries four activation bytes, most significant byte first, and like ACT over SPI needs `act_spi` = 1.

**Before any request.** After reset, a DEBUG, MBIST, or CBIST capture with no request outstanding reports ready with all-zero data.

If SPI and JTAG write in the same CLK cycle, SPI is carried out and the JTAG write is dropped, setting `err_busy`.

## 11. What the FPGA must guarantee

1. LINK_CLK continuous while the link is enabled, and no faster than CLK.
2. Frames paced so the chain is free when each payload arrives: at least 67 + P CLK cycles between the first payload symbols of two frames at P = 2 to 8 (75 at P = 8), 22 at P = 1 raw, and 16 at P = 1 requantized. An earlier frame is dropped and counted, not corrupted. No frame may be sent while a weight burst is in progress.
3. After a missing result, 72 idle symbols before the resend.
4. Weights, P, bias, shift, and mode written only when `STATUS.busy` is 0.
5. SPI_SCLK no faster than CLK. TCK at least 4 CLK periods for DEBUG.
6. Each return lane lined up by its own sync word before the CRC is checked.
7. RST_N asserted only while SPI_CS_N is high. A reset in the middle of an SPI transaction leaves the chip taking the next data byte as a command.
8. After switching the link off, LINK_CLK kept running until `STATUS.link_ready` reads 0.
9. One master at a time for a vector: the busy rule protects the chip from a write by the other master, but not from two masters each loading half of the activations.
10. RST_N held low for at least 4 CLK periods.
11. SPI_CS_N high for at least 2 CLK periods between transactions. Shorter, X5 may miss it and a weight burst never ends.
12. After RST_N rises, five TCK cycles with TMS high before the first JTAG scan.

**Getting back after link trouble,** with no reset: write CLEAR with bit 2 set; wait for `STATUS.busy` = 0; write MODE with `link_en` = 0; wait for `link_ready` = 0; clear the counters and flags; set the configuration again; send 72 idle symbols before the first frame.

## 12. Measured on the model

From `python3 -m model.chip_v2`: 155 checks, all passing, about five minutes. CLK is 25 MHz. "With metastability" means a flop that samples a signal less than 2 ns after it changed gets the old or the new value at random.

**Cycle counts.** Every one equals the design guide's estimate.

| | Measured | Estimate |
|---|---|---|
| Per vector, P = 1, raw | 22 | 22 |
| Per vector, P = 1, requantized | 16 | 16 |
| Per vector, P = 4, raw | 71 | 71 |
| Per vector, P = 8, raw or requantized | 75 | 75 |
| Per vector, P = 1, return lanes silent | 13 | not estimated: the inbound frame, 13 symbols, is the limit |
| One weight set over SPI, SCLK = CLK | 1,040 | at least 1,024 |
| Six weight sets of 64 vectors each | 35,298 | 34,944 (+1.0%) |
| One photograph, convolution network (30,899 passes, 116 weight sets) | 2,443,053 | 2,436,209 (+0.3%) |
| One photograph, attention network (35,907 passes, 207 weight set writes) | 2,917,206 | 2,904,993 (+0.4%) |
| Reset self-test | 3,030 (memory 1,535, compute 1,488) | |
| Link enable: idle symbols between the start of the MODE write and the first frame taken | 22 | |
| Self-test abort, from chip select falling | 12 (8 for the command byte, 3 to cross, 1) | |

**Correctness.**

| Check | Result |
|---|---|
| Both demo networks, one photograph each, every multiply through the pins | Scores identical to the integer network |
| Vectors at every precision 1 to 8, return lanes skewed by 0 to 3 cycles | All results, sequence numbers, and CRCs right |
| Requantize against the four steps, shifts 0 to 15, boundary values | All right |
| Chip with the link unplugged: SPI only, and JTAG only | Whole vectors run and read back correctly |
| Compute test signature | Cycle model equals plain arithmetic: `0x29E000BC` |
| Memory test with a cell stuck at 0, stuck at 1, or coupled to another | Fails and names the right row |
| `gate_off`, `act_spi`, ACT without `act_spi` (SPI and JTAG), CLEAR bits 0 and 1, counters stopping at 255 | Each as section 8 says |
| STATUS bits 0 to 3 read at 72 phases of three vectors in a row | Each seen at 0 and at 1; a loaded vector or a waiting result always reads busy |

**Crossings.**

| Check | Result |
|---|---|
| Link clock at 1.0, 1.003, and 1.5 times the core period, 8 phases each, with metastability | Every result right |
| Link FIFO, most symbols ever waiting | 2 of 8 |
| Link latency, from LINK_D changing to the core using the symbol | 2.5 to 3.5 CLK periods |
| SPI at 1.0, 1.25, and 3.7 times the core period, 8 phases each, with metastability | Every register reads back what was written |
| Held words read while changing (X2, X3, X4), in every scenario | None |
| Link clock faster than the core clock (the FPGA breaking its rule) | Caught by `fifo_ovf` |
| SPI transaction cut short mid-byte | Nothing changes; the next transaction is aligned |
| The link switched off and straight on 16 times, LINK_CLK at 40 CLK periods | Every frame right; no overflow flag; no FIFO entry read twice |
| A frame at each of 16 offsets around the link coming up | Taken from one exact symbol onward, never before |
| SPI and JTAG writing in the same CLK cycle, 8 alignments | Exactly one tie: SPI carried out, JTAG dropped and flagged |
| JTAG scan with the core clock stopped | Not ready, all zeros |

**Errors.**

| Check | Result |
|---|---|
| Every single flipped bit in a frame (52 at P = 1, 276 at P = 8) | Frame rejected; no wrong result ever returned |
| Two flipped bits, 4,000 random pairs at P = 8 | 4 pass the CRC (0.1%): pairs exactly 255 bits apart |
| Frames one cycle too close | Dropped and counted; every result that returns is right |
| Unknown frame type; a stray sync on a quiet link | Counted; no compute starts |
| Weight write while a vector loads | Ignored and flagged; the vector's result is right |
| Frame during a weight burst | Dropped; never computed on half-written weights |
| P written while a result drains | Accepted; the draining result keeps its width |
| A good frame 71, then 72, idle symbols after a bad one | Lost at 71, taken at 72; any other symbol restarts the count |
| A MODE write racing the start of a frame, 24 alignments | Taken first (10) or refused (14); the chip is idle afterwards every time |
| A weight burst racing the start of a frame, 24 alignments | The burst wins whole (18) or the frame does (6); never a mix |
| P, START, or SHIFT written while a vector loads or a result waits | Ignored and flagged |
| LINK_CLK stopped in the middle of a frame | Chip busy; CLEAR bit 2 frees it; it then runs over SPI with its weights intact |
| START over JTAG in the middle of an SPI ACT burst | Refused; the vector is then right |
| A write of any kind as the first after reset | Stops the self-test and is carried out |
| A JTAG write that stops the self-test in the middle of a row write, 12 alignments | The activation gate stays closed during the write |
| 1,500 frames with a corrupted sync, random payloads, P = 8 | 1,486 false starts: 1,140 bad types, 345 CRC failures, 1 compute on garbage; the same as a receiver written from section 4, batch by batch. Separately, 1,552 of 400,000 random type-0 bodies pass the CRC (1 in 258). So a garbage compute is about 0.991 x 0.233 / 256, one corrupted sync in 1,100. |

**How the checks were checked.** A check that passes says little unless it would have failed on a wrong chip. Four things were done about that, all before any RTL.

| What | Command | Result |
|---|---|---|
| Every scenario recorded as a pin trace (every clock edge, every input change, every output where the FPGA samples it) and replayed on a fresh copy of the model | `python3 -m model.chip_v2.verify replay` | 414 traces, 1,100,880 CLK cycles: all replay exactly |
| The same traces replayed on 106 copies of the model, each with one deliberate fault (`mutants.py`) | `python3 -m model.chip_v2.verify mutants` | 103 noticed at the pins. 3 cannot be seen from the pins and need a test inside the chip: compute starting during a row write, a row read during a row write, and the memory test's second pattern. None unnoticed. |
| Random legal traffic: random clock ratios and phases, metastability on, random precision, requantize, weight reloads, SPI and JTAG use | `python3 -m model.chip_v2.verify random N` | 300 of 300 seeds: every frame back, in order and right; no counter or flag moved |
| Random hostile traffic: frames too close, corrupted, cut short; writes while busy; both masters at once; tests started mid-traffic; the link clock stopped; then recovery without a reset, then a reset | same | 1,800 of 1,800 seeds: no result ever differed from W^T a for what the chip held at start; no crossing read while changing; the chip always came back; after reset it matched a fresh chip pin for pin |
| The traces replayed on simulated pins through cocotb, with the model behind a port-only stand-in | `cd cocotb/v2 && python3 chip_v2_tb.py` | Icarus: 411 of 411 traces, 1,091,757 cycles. Verilator: 289 of 289 (the quick set). 10 broken copies of the model behind the pins: all 10 reported. |

The first mutation run, against the 78 checks of draft 0.2, left 24 of 96 faults unnoticed. Section 13 rows 10 to 20 are what this found.

The cocotb testbench is the one the RTL will be run against. It needs the RTL to match the model edge for edge, so a difference of one cycle anywhere is reported with the pin, the time, and the two values.

**Not modelled.** Setup and hold times beyond the 2 ns sampling window; pad delays and drive; skew between the four input lanes of less than a cycle; clock jitter; the half-cycle stagger of the return lanes suggested in design guide 5.8; power and energy. Faults inside the array can only be injected in the model, so the three traces that use them are not replayed on RTL. None of the above replaces timing analysis or the RTL's own tests.

## 13. What building the model changed in this specification

Draft 0.1 was written first, then the model, then the scenarios. These are the places where the first text was wrong or silent.

| # | Found | Change |
|---|---|---|
| 1 | With a slow SPI clock, the core could move on to the next read byte before the SPI domain had taken the current one. | X3: the SPI domain loads on the SCLK edge that completes a byte, so the core always has a full byte time. |
| 2 | The busy rule was checked only on a burst's command byte, so a frame could arrive during a 1,024-bit weight burst and compute on half-written weights. | New crossing X5 (chip select level). A weight burst in progress makes the chip busy and turns arriving frames into overruns. |
| 3 | A write is not in effect when its transaction ends; a test that looked straight away saw the old value. | Section 3: the 4 CLK period rule for the FPGA. |
| 4 | Reading a test result over JTAG returned the state from before the test started. | Section 10: every JTAG answer is one scan behind, with a ready bit; MBIST and CBIST use the same crossing as DEBUG. |
| 5 | "The first valid frame aborts self-test" could not happen and was not needed. | Section 9: only writes abort. |
| 6 | The compute test passed with a stuck cell whose stuck value matched its weight pattern. | Section 9: stated as a limit; cells belong to the memory test. |
| 7 | At P = 1 a burst of about 29 frames can run at 21 cycles before one is dropped, because the accumulators hold one finished result. | None to the rule: the sustainable period is 22. The scenario now sends 96 frames. |
| 8 | With the return lanes silent at P = 1 the limit is the inbound frame length, not the chain. | Section 12 records 13. |
| 9 | A corrupted sync leaves the receiver hunting through payload data. | Section 4: stated as a known weakness, with its odds. |

Draft 0.3 came from checking the checks (section 12, "How the checks were checked"). These were found by random traffic, by the mutation run, and by putting the model behind simulated pins.

| # | Found by | Found | Change |
|---|---|---|---|
| 10 | Random hostile traffic | **A lock-up.** The busy rule was checked on a write's command byte, but the write lands 8 or more cycles later. A MODE write could pass the check while idle and then switch the receiver off in the middle of a frame, leaving the chain loading for ever. | Section 5: the check is made on the edge that carries the write out. |
| 11 | Reasoning from 10, then a directed sweep | A write and a frame's first payload symbol could meet on one CLK edge and both go ahead (a weight burst starting under a frame that had just begun). | Section 5: a frame that starts on the checking edge counts as busy. |
| 12 | Random legal traffic, 30 of 300 seeds | **A false overflow flag.** Switching the link off zeroed the core's read pointer while the link side was still writing, which looked like a full FIFO one time in 16. The same weakness could replay old FIFO entries if the link was switched off and on quickly. | Section 2: the three-state handshake. The FIFO is emptied when the link comes up. |
| 13 | The model behind simulated pins (cocotb) | **Reset was not complete.** The registers that hold a word for another domain kept their value through reset, so the first JTAG capture after a reset returned data from before it. | Sections 2 and 3: every flop is reset. The stress test now checks that a used chip, once reset, matches a fresh one pin for pin. |
| 14 | Review while fixing 10 | A link that stops mid-frame leaves the chip busy with no way out but RST_N, which costs the weights. | Section 8: CLEAR bit 2. Section 11: the recovery procedure. |
| 15 | Review while fixing 10 | An SPI ACT burst did not hold the chip busy between bytes, so START from JTAG could run a half-loaded vector. ACT over JTAG did not need `act_spi`, so it could shift the chain under an arriving frame. | Section 5 (a burst is WEIGHTS or ACT) and sections 8 and 10. |
| 16 | Review while fixing 10 | A JTAG write that stopped the self-test in the middle of a row write could open the activation gate during that write (a row read, or a compute starting two cycles later). | Section 8.2: the gate is closed whenever the write controller is not idle; reads and starts wait. The controller's hold cycle is now a state of its own. |
| 17 | Mutation run | The "second copy of P" could never differ from the first. | Section 5: reworded; the transmitter simply keeps the width it captured. |
| 18 | Random legal traffic at the tightest spacing | Section 11 said 69 + P cycles per vector for P = 2 to 7. The model, the measurements, and the design guide all say 67 + P. | Section 11 corrected. |
| 19 | Mutation run | "Exactly five crossings" left out the three single-bit signals that go with the link FIFO. | Section 3: X1 now lists them. |
| 20 | Mutation run | 24 of 96 deliberately broken copies of the model passed every one of the original 78 checks: nothing watched the exact recovery count, the STATUS bits, CLEAR, counter limits, `gate_off`, `act_spi`, the busy rule for P and START, the JTAG tie, or the link's release edge. | 35 new checks (scenarios `recover`, `linkup`, `status`, `modes`, `jtagx`, `robust`). No change to the behaviour. |
| 21 | Verification plan audit (plan section 6, gaps S5 to S23 marked "text only") | Sixteen places where the text said nothing and the model already did something sensible: undefined and write-only addresses, writes to read-only registers, reserved bits, extra and missing bytes, ROW_SEL wrapping, back-to-back return frames, writes during a return frame, TDO between scans, IR and BYPASS capture, compliance with IEEE 1149.1, the shortest reset, chip select high time, JTAG start-up, and the CLK minimum. | Draft 0.4: written into sections 2, 5, 7, 8, 10 and 11 (rules 10 to 12). Twelve new checks (scenario `regs`) and 18 new faults. No change to the behaviour. |
| 22 | The RX-12 test (scenario `sync`) | Section 4 put the odds of a garbage compute after a corrupted sync at 1 in 256. It left out the type check, which rejects about three false frames in four first. | Section 4: about 1 in 1,100, measured. |

## 14. Decisions that are Karan's

The model and the RTL need a value for each of these, so each has one. None is confirmed. Changing one means changing this document and `model/chip_v2/` together and rerunning the checks; the mutation table then says whether the change is still watched.

| # | Decision | Value used | Section | What depends on it |
|---|---|---|---|---|
| 1 | Core clock | 25 MHz nominal | 1 | Timing closure. Flow audit F3: 50 MHz is not reachable without pipelining. |
| 2 | Inbound sync | One symbol, `0xA` | 4 | The known weakness at the end of section 4. A two-symbol sync would remove most of it for one more symbol per frame. |
| 3 | CRC | CRC-8, `0x1D`, start `0xFF` | 4, 7 | Two flipped bits exactly 255 apart pass (0.1% of random pairs at P = 8). |
| 4 | Recovery wait | 72 idle symbols | 4 | The FPGA's resend rule. |
| 5 | Link FIFO depth | 8 | 3 | 2 are ever used with LINK_CLK no faster than CLK. 4 would do. |
| 6 | Return frame | Sync 1, 1, 0, 1 on every lane; header, result, CRC as in section 7 | 7 | The FPGA's receiver. |
| 7 | Requantize | 21-bit signed bias, 4-bit shift, output 0 to 255 | 6 | A signed output limit is left to the FPGA (raw results). |
| 8 | SPI | Mode 0, one dummy byte on reads, SCLK no faster than CLK | 2, 8 | The FPGA's SPI master. |
| 9 | Register map and ID | Section 8; ID `0xDC1A0002` | 8 | Host software. |
| 10 | Busy, and the busy rule | Section 5, including when the check is made | 5 | Items 10, 11 and 15 of section 13. |
| 11 | CLEAR bit 2 | Added in draft 0.3 | 8 | Recovery from a dead link without losing the weights. It is new logic, though small. |
| 12 | Link on and off | The three-state handshake | 2 | Items 12 of section 13. A few flops in the core. |
| 13 | Write port | Three cycles; gate closed whenever the controller is not idle | 8.2 | Flow audit F1 and F2. This is the "proposed, not yet accepted" write-port rule made exact. |
| 14 | Self-test | Patterns, generator, signature polynomial, 8,192-cycle timeout, abort on any write | 9 | Self-test time, and what a pass means. |
| 15 | STATUS pin | Low, then CLK / 65,536 on a pass or high on a fail, then DONE pulses | 9 | Bring-up with no SPI. |
| 16 | JTAG | 3-bit instruction register, the five codes, answers one scan behind, TCK at least 4 CLK periods | 10 | Debug host. |
| 17 | FPGA rules 7 to 9 | No reset during an SPI transaction; LINK_CLK runs until the link reports off; one master per vector | 11 | Each could be enforced in the chip instead, at a cost in logic. |
