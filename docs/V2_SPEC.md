# DCIM v2 specification

**Draft 0.2, 2026-10-12.** This is the exact behaviour the v2 chip must have at its pins, cycle by cycle. `docs/V2_DESIGN_GUIDE.md` explains each feature and `docs/DESIGN_RATIONALE.md` says why it exists; this document fixes the values those two left open. Where they disagree with this document, this document is the intended behaviour and they need updating.

A pin-level, cycle-accurate model of this specification lives in `model/chip_v2/`. Every number in section 12 is measured on that model, and section 13 lists what building the model changed in this text. When the model and this text disagree, one of them is wrong and both must be brought back in line.

Status words: **Set** means fixed by this document. **Karan** means a decision that is his and is recorded here as a proposal until he confirms it.

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
| CLK | Free running. Everything that computes is in this domain. |
| LINK_CLK | Runs continuously while `MODE.link_en` is 1. Its period is never shorter than CLK's (contract 16). The FPGA changes LINK_D on the falling edge; the chip samples on the rising edge. |
| SPI_SCLK | SPI mode 0: idle low, MOSI sampled on the rising edge, MISO changes on the falling edge. Toggles only while SPI_CS_N is low. Its period is never shorter than CLK's. |
| TCK | Standard JTAG: TMS and TDI sampled on the rising edge, TDO changes on the falling edge. For DEBUG, MBIST, and CBIST its period is at least 4 CLK periods. |

**Reset.** RST_N low resets every domain asynchronously.

| Domain | Comes out of reset |
|---|---|
| Core | Two CLK rising edges after RST_N goes high (two-flop synchronizer). |
| Link | Held in reset while `MODE.link_en` is 0. Released two LINK_CLK rising edges after `link_en` is set. |
| SPI | As soon as RST_N is high. No clock is needed: SPI_SCLK does not run between transactions, so nothing here may wait for it. SPI_CS_N high resets the bit counter, so every transaction starts aligned. |
| JTAG | As soon as RST_N is high. Five TCK rising edges with TMS high also reset the TAP. |

## 3. Clock-domain crossings

There are exactly five, and nothing else may cross.

| # | From, to | Mechanism | Latency |
|---|---|---|---|
| X1 | Link to core: every sampled symbol | Asynchronous FIFO, 8 entries of 4 bits, Gray-coded pointers, two-flop synchronizers | A symbol is used by the core on the third CLK rising edge after the LINK_CLK edge that sampled it (2 to 3 CLK periods). |
| X2 | SPI to core: one whole word (a byte, or a 32-bit weight row) | The word is held in a register in the SPI domain and a toggle flips. The core synchronizes the toggle (two flops), detects the change, and reads the held word. | The core acts on the word on the third CLK rising edge after the SCLK edge that completed it. |
| X3 | Core to SPI: read data | The core places each byte to be sent in a holding register. The SPI domain loads the holding register into its output shift register on the SCLK rising edge that completes a byte, the same edge that fires X2. The core then has a whole byte time to put the next byte there. | Stable at least 4 CLK periods before it is used, at any SCLK rate. |
| X4 | JTAG to core and back: one DEBUG, MBIST, or CBIST request | Request word and toggle on Update-DR, synchronized as in X2. The core answers into a holding register and flips an acknowledge toggle, synchronized into TCK (two flops). | A response is ready 3 CLK periods plus 2 TCK periods after Update-DR. The captured word carries a ready bit. |
| X5 | SPI to core: the level of SPI_CS_N | Two-flop synchronizer. The core uses it only to know that a weight burst has ended. | 2 CLK periods. |

Rules that make these safe:

- **Only whole words cross, never a single data bit.** Synchronizers carry toggles and Gray pointers only.
- **A held word must not change while the other side may read it.** For X2 that is guaranteed by the SCLK period rule: the next byte completes at least 8 CLK periods later. The model checks every such read and reports any that happens within one CLK period of the word changing.
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
3. **Payload.** At the first payload symbol, if the activation chain is free and no weight burst is in progress, shift every payload symbol into the chain. Otherwise the frame is an **overrun**: its payload and CRC symbols are counted off and discarded, `CNT_OVERRUN` increments, and the receiver returns to hunt.
4. **CRC.** If it matches, the vector is valid and will compute. If not, `CNT_CRC` increments, the chain is marked free (its contents are junk), and the receiver goes to **recover**.
5. **Recover.** Discard everything until 72 idle symbols in a row have been seen, then hunt. A bad frame type also leads here, with `CNT_BAD` incremented.

**A known weakness of the one-symbol sync.** If the sync symbol itself is corrupted, the frame is not recognised and the receiver keeps hunting through its payload. Any payload symbol equal to `0xA` then starts a false frame. Its CRC fails 255 times in 256, which costs a recovery wait; one time in 256 it computes on garbage and returns a result whose sequence number the FPGA is not expecting and must discard.

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
| First edge after E at which the accumulators are empty, or are being captured on that same edge | **Start.** Accumulators are cleared. The chain's copy of P is the one latched at the first payload symbol. |
| The next P edges | **Compute,** one bit plane per edge, least significant first. The activation gate is open only on these edges. |
| The edge after the last compute edge | The chain is free. The accumulators are valid. STATUS pulses (DONE). |
| First edge at which the accumulators are valid and the transmitter is idle | **Capture.** The result (requantized or raw) and its header go to the transmitter, and the raw values go to `RESULT0..3`. The accumulators are empty again. |

- **Chain occupied** (first payload symbol to chain free): payload + 2 + 1 + P cycles when nothing has to wait. That is 12 at P = 1 and 75 at P = 8.
- **Busy** means any of: the chain is not free; the accumulators are valid; self-test is running; an SPI weight burst is in progress (from its command byte until SPI_CS_N is seen high); a row write is in progress; activations from SPI or JTAG are still shifting in. A draining transmitter is **not** busy. `STATUS.busy` reports this.
- **Writes while busy.** A write to P, SHIFT, BIAS, MODE, WEIGHTS, ACT, START, BIST_CTRL, or ROW_SEL while busy is ignored and sets `STATUS.err_busy`. The check is made once, on the command byte. The one exception is self-test: the write aborts it and is then carried out (section 9).
- **P travels with the vector.** One copy is taken at the first payload symbol (load mode, compute). A second is taken at capture (return width). Because P cannot be written while busy, the two always agree; the second copy exists so that a draining result keeps its width if P is written while it drains.

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

## 8. SPI and the registers

**Transaction.** While SPI_CS_N is low, bits are taken most significant first.

| Byte | Write | Read |
|---|---|---|
| 0 | `{1, addr[6:0]}` | `{0, addr[6:0]}` |
| 1 | data | dummy, ignored |
| 2 onward | more data | data |

A register wider than one byte is sent most significant byte first. Raising SPI_CS_N ends the transaction; an unfinished byte or weight row is dropped.

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
| 0x0B | ACT | 32, or 4 at P = 1 | W | | One vector through the re-joined chain, in the v1 order: row 31 first, within a row bit 0 first. Needs `act_spi` = 1; without it the write is ignored and flagged. |
| 0x0C to 0x0F | RESULT0 to RESULT3 | 3 | R | 0 | Last captured raw result, sign-extended to 24 bits |
| 0x10 | CNT_CRC | 1 | R | 0 | CRC failures, stops at 255 |
| 0x11 | CNT_OVERRUN | 1 | R | 0 | Overruns, stops at 255 |
| 0x12 | CNT_BAD | 1 | R | 0 | Bad frame types, stops at 255 |
| 0x13 | CLEAR | 1 | W | | bit 0 clears the three counters, bit 1 clears the sticky STATUS flags |
| 0x14 | BIST_CTRL | 1 | W | | bit 0 run memory test, bit 1 run compute test |
| 0x15 | BIST_STAT | 1 | R | | bits 1:0 memory test, 3:2 compute test: 0 running, 1 pass, 2 fail, 3 aborted or not run |
| 0x16 | BIST_ROW | 1 | R | | First failing row of the memory test |
| 0x17 | CBIST_SIG | 4 | R | | Compute test signature |
| 0x18 | ROW_SEL | 1 | RW | 0 | Row to read back |
| 0x19 | ROW_DATA | 4 | R | | That row's 32 stored bits, read through the compute port. Only when not busy. |

`gate_off` = 1 keeps the activation gate closed during compute (design guide 5.16). `act_spi` = 1 joins the four sub-chains into one and takes activations from ACT; link frames are then ignored.

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

One write controller owns the array's write port. A row write takes three CLK cycles: address and data set up, wordline enable high (straight from a flop), then hold. The activation gate is closed throughout. A weight set arrives one row every 32 SCLK periods, so the three cycles cost nothing.

## 9. Self-test

Out of reset, with nothing written, the chip runs the memory test and then the compute test.

**Memory test.** Row patterns `0x00000000`, `0xFFFFFFFF`, `0x55555555`, `0xAAAAAAAA`. For each of the two pairs (D, ~D): write D to every row ascending; ascending, read D then write ~D; ascending, read ~D then write D; descending, read D then write ~D; descending, read ~D then write D; read D from every row. A read is one cycle: the activation input is one-hot on that row and the 32 column sums are the row's bits. The first failing row is recorded.

**Compute test.** Weights and activations come from a 16-bit generator (x^16 + x^14 + x^13 + x^11 + 1, seed `0xACE1`), one bit per step. It writes one weight set (each row's 32 bits in column order), then runs 16 vectors at P = 8 with raw results. Each vector is 64 symbols shifted in through the four lanes as a frame's payload would be, four generator bits per symbol, lane 0's bit first. Each result is folded into a 32-bit signature register (the CRC-32 polynomial `0x04C11DB7`, seed `0xFFFFFFFF`), one 21-bit result per cycle, output 0 first. The signature must equal a constant that comes from the model, never from the RTL: `0x29E000BC`, which `model/chip_v2/chip.py` works out with ordinary arithmetic and the cycle model reproduces.

The compute test stores a single weight pattern, so it cannot see a cell stuck at the value that pattern happens to store there. Cells are the memory test's job; the compute test covers the chain, the trees, the combine, and the accumulators.

| Rule | |
|---|---|
| Timeout | 8,192 CLK cycles for each test |
| Abort | Any SPI or JTAG write, on its command byte. The test stops on the CLK edge that sees the command (3 edges after the byte completes), releases the write port and the activation input, and reports "aborted". The write that caused it is carried out. A link frame does not abort a test: `link_en` resets to 0, so none can arrive before a write, and a frame that arrives during a commanded test is an overrun. |
| Never blocks | Reads are always answered. A test that fails or times out leaves the chip fully usable. |
| After the test | The array holds test patterns. Weights must be written before use, as after any reset. |

**STATUS pin.** Low while the reset self-test runs. A square wave of CLK / 65,536 (about 381 Hz at 25 MHz) if both tests passed. High if either failed or timed out. After the first write or valid frame it becomes DONE: high for one CLK cycle each time a compute finishes.

## 10. JTAG

Instruction register: 3 bits. Reset selects IDCODE.

| IR | Instruction | Data register |
|---|---|---|
| `001` | IDCODE | 32 bits, `0xDC1A0002` with bit 0 forced to 1 as the standard requires |
| `010` | DEBUG | 40 bits |
| `011` | MBIST | 8 bits. Shifted in: bit 0 = start the memory test. Captured: `{first failing row[4:0], ready, state[1:0]}` |
| `100` | CBIST | 35 bits. Shifted in: bit 0 = start the compute test. Captured: `{ready, signature[31:0], state[1:0]}` |
| `111`, others | BYPASS | 1 bit |

**DEBUG.** Shifted in: `{write, addr[6:0], data[31:0]}`. On Update-DR the request crosses to the core (X4). A write is carried out under the same busy rule as SPI. Captured on the next scan: `{ready, 7 zeros, read data[31:0]}`.

**Every answer is one scan behind.** DEBUG, MBIST, and CBIST all capture the answer to the *previous* Update, and only if `ready` is 1; otherwise the captured word is all zeros and the scan is simply repeated. So a read is two scans (ask, collect), and so is reading a test's result (a scan with start = 0 to ask, another to collect).

**Bursts over DEBUG.** A WEIGHTS write carries one row (bit c = column c), writes it to the row in ROW_SEL, and adds 1 to ROW_SEL. An ACT write carries four activation bytes, most significant byte first.

If SPI and JTAG write in the same CLK cycle, SPI is carried out and the JTAG write is dropped, setting `err_busy`.

## 11. What the FPGA must guarantee

1. LINK_CLK continuous while the link is enabled, and no faster than CLK.
2. Frames paced so the chain is free when each payload arrives: at least 75 CLK cycles between the first payload symbols of two frames at P = 8, 69 + P at P = 2 to 7, 22 at P = 1 raw, and 16 at P = 1 requantized. An earlier frame is dropped and counted, not corrupted. No frame may be sent while a weight burst is in progress.
3. After a missing result, 72 idle symbols before the resend.
4. Weights, P, bias, shift, and mode written only when `STATUS.busy` is 0.
5. SPI_SCLK no faster than CLK. TCK at least 4 CLK periods for DEBUG.
6. Each return lane lined up by its own sync word before the CRC is checked.

## 12. Measured on the model

From `python3 -m model.chip_v2`: 78 checks, all passing, about two minutes. CLK is 25 MHz. "With metastability" means a flop that samples a signal less than 2 ns after it changed gets the old or the new value at random.

**Cycle counts.** Every one equals the design guide's estimate.

| | Measured | Estimate |
|---|---|---|
| Per vector, P = 1, raw | 22 | 22 |
| Per vector, P = 1, requantized | 16 | 16 |
| Per vector, P = 4, raw | 71 | 71 |
| Per vector, P = 8, raw or requantized | 75 | 75 |
| Per vector, P = 1, return lanes silent | 13 | not estimated: the inbound frame, 13 symbols, is the limit |
| One weight set over SPI, SCLK = CLK | 1,039 | at least 1,024 |
| Six weight sets of 64 vectors each | 35,298 | 34,944 (+1.0%) |
| One photograph, convolution network (30,899 passes, 116 weight sets) | 2,443,053 | 2,436,209 (+0.3%) |
| One photograph, attention network (35,907 passes, 207 weight set writes) | 2,917,206 | 2,904,993 (+0.4%) |
| Reset self-test | 2,772 (memory 1,277, compute 1,488) | |
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

**Not modelled.** Setup and hold times beyond the 2 ns sampling window; pad delays and drive; skew between the four input lanes of less than a cycle; clock jitter; the half-cycle stagger of the return lanes suggested in design guide 5.8; power and energy. None of the above replaces timing analysis or the RTL's own tests.

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
