# v2 functional coverage

**Generated** by `python3 -m model.chip_v2.verify coverage` from `model/chip_v2/coverage.py`. Do not edit by hand. The coverage model is `docs/V2_VERIFICATION_PLAN.md` section 5.

Collected on 2292 benches: every scenario but the photographs, 50 legal and 50 hostile random seeds, and two forced self-test timeouts. 1036 of 1036 reachable bins hit (100.0%); 32 bins are impossible by design.

| Point | Bins | Impossible | Hit | Missing |
|---|---|---|---|---|
| FC-01 frame outcome | 72 | 0 | 72 | 0 |
| FC-02 frame type | 4 | 0 | 4 | 0 |
| FC-03 frame spacing | 32 | 1 | 31 | 0 |
| FC-04 receiver interrupted | 32 | 11 | 21 | 0 |
| FC-05 guarded write | 162 | 18 | 144 | 0 |
| FC-06 same-edge race | 12 | 0 | 12 | 0 |
| FC-07 every register | 512 | 0 | 512 | 0 |
| FC-08 SPI cut short | 17 | 0 | 17 | 0 |
| FC-09 clock ratio | 11 | 0 | 11 | 0 |
| FC-10 crossing alignment | 36 | 0 | 36 | 0 |
| FC-11 link state | 5 | 0 | 5 | 0 |
| FC-12 write controller | 8 | 0 | 8 | 0 |
| FC-13 self-test | 10 | 0 | 10 | 0 |
| FC-14 STATUS pin | 9 | 0 | 9 | 0 |
| FC-15 requantize | 24 | 2 | 22 | 0 |
| FC-16 results | 64 | 0 | 64 | 0 |
| FC-17 counters | 15 | 0 | 15 | 0 |
| FC-18 TAP | 40 | 0 | 40 | 0 |
| FC-19 JTAG and SPI tie | 3 | 0 | 3 | 0 |

## Missing bins


## Impossible bins, and why

- **FC-05 guarded write** ('P', 'SPI', 'burst'): SPI cannot write during its own burst: the burst ends when chip select rises, and the next write is checked at least 8 CLK later (sections 3 and 11 rule 11)
- **FC-05 guarded write** ('SHIFT', 'SPI', 'burst'): SPI cannot write during its own burst: the burst ends when chip select rises, and the next write is checked at least 8 CLK later (sections 3 and 11 rule 11)
- **FC-05 guarded write** ('BIAS', 'SPI', 'burst'): SPI cannot write during its own burst: the burst ends when chip select rises, and the next write is checked at least 8 CLK later (sections 3 and 11 rule 11)
- **FC-05 guarded write** ('MODE', 'SPI', 'burst'): SPI cannot write during its own burst: the burst ends when chip select rises, and the next write is checked at least 8 CLK later (sections 3 and 11 rule 11)
- **FC-05 guarded write** ('WEIGHTS', 'SPI', 'burst'): SPI cannot write during its own burst: the burst ends when chip select rises, and the next write is checked at least 8 CLK later (sections 3 and 11 rule 11)
- **FC-05 guarded write** ('ACT', 'SPI', 'burst'): SPI cannot write during its own burst: the burst ends when chip select rises, and the next write is checked at least 8 CLK later (sections 3 and 11 rule 11)
- **FC-05 guarded write** ('START', 'SPI', 'burst'): SPI cannot write during its own burst: the burst ends when chip select rises, and the next write is checked at least 8 CLK later (sections 3 and 11 rule 11)
- **FC-05 guarded write** ('BIST_CTRL', 'SPI', 'burst'): SPI cannot write during its own burst: the burst ends when chip select rises, and the next write is checked at least 8 CLK later (sections 3 and 11 rule 11)
- **FC-05 guarded write** ('ROW_SEL', 'SPI', 'burst'): SPI cannot write during its own burst: the burst ends when chip select rises, and the next write is checked at least 8 CLK later (sections 3 and 11 rule 11)
- **FC-05 guarded write** ('P', 'SPI', 'self-test'): the command byte stops the self-test 8 or more CLK before a register's data byte is checked (sections 5 and 9)
- **FC-05 guarded write** ('SHIFT', 'SPI', 'self-test'): the command byte stops the self-test 8 or more CLK before a register's data byte is checked (sections 5 and 9)
- **FC-05 guarded write** ('BIAS', 'SPI', 'self-test'): the command byte stops the self-test 8 or more CLK before a register's data byte is checked (sections 5 and 9)
- **FC-05 guarded write** ('MODE', 'SPI', 'self-test'): the command byte stops the self-test 8 or more CLK before a register's data byte is checked (sections 5 and 9)
- **FC-05 guarded write** ('START', 'SPI', 'self-test'): the command byte stops the self-test 8 or more CLK before a register's data byte is checked (sections 5 and 9)
- **FC-05 guarded write** ('BIST_CTRL', 'SPI', 'self-test'): the command byte stops the self-test 8 or more CLK before a register's data byte is checked (sections 5 and 9)
- **FC-05 guarded write** ('ROW_SEL', 'SPI', 'self-test'): the command byte stops the self-test 8 or more CLK before a register's data byte is checked (sections 5 and 9)
- **FC-05 guarded write** ('ACT', 'JTAG', 'loading'): ACT over JTAG needs act_spi, and with act_spi no frame loads (section 8)
- **FC-05 guarded write** ('ACT', 'JTAG', 'self-test'): ACT over JTAG needs act_spi, and the MODE write that sets it stops the self-test (sections 8 and 9)
- **FC-03 frame spacing** (2, 'one too close'): at P = 2 the minimum spacing, 69, is the frame's own length: one cycle less would overlap two frames (sections 4 and 11 rule 2)
- **FC-15 requantize** ('above 255', '15', 'negative bias'): r + bias is at most 32 x 127 x 255 + 2^20 - 1 = 2,084,895, so shifted by 15 it is at most 63 (section 6)
- **FC-15 requantize** ('above 255', '15', 'bias 0 or more'): r + bias is at most 32 x 127 x 255 + 2^20 - 1 = 2,084,895, so shifted by 15 it is at most 63 (section 6)
- **FC-04 receiver interrupted** ('hunt', 'CLEAR bit 2'): CLEAR bit 2 acts only while a vector is loading, when the receiver is in payload or CRC (section 8)
- **FC-04 receiver interrupted** ('header 1', 'CLEAR bit 2'): CLEAR bit 2 acts only while a vector is loading, when the receiver is in payload or CRC (section 8)
- **FC-04 receiver interrupted** ('header 2', 'CLEAR bit 2'): CLEAR bit 2 acts only while a vector is loading, when the receiver is in payload or CRC (section 8)
- **FC-04 receiver interrupted** ('skip', 'CLEAR bit 2'): CLEAR bit 2 acts only while a vector is loading, when the receiver is in payload or CRC (section 8)
- **FC-04 receiver interrupted** ('recover', 'CLEAR bit 2'): CLEAR bit 2 acts only while a vector is loading, when the receiver is in payload or CRC (section 8)
- **FC-04 receiver interrupted** ('payload', 'link off'): a vector is loading, so the chip is busy and the MODE write that would do this is refused (section 5)
- **FC-04 receiver interrupted** ('payload', 'act_spi'): a vector is loading, so the chip is busy and the MODE write that would do this is refused (section 5)
- **FC-04 receiver interrupted** ('CRC 1', 'link off'): a vector is loading, so the chip is busy and the MODE write that would do this is refused (section 5)
- **FC-04 receiver interrupted** ('CRC 1', 'act_spi'): a vector is loading, so the chip is busy and the MODE write that would do this is refused (section 5)
- **FC-04 receiver interrupted** ('CRC 2', 'link off'): a vector is loading, so the chip is busy and the MODE write that would do this is refused (section 5)
- **FC-04 receiver interrupted** ('CRC 2', 'act_spi'): a vector is loading, so the chip is busy and the MODE write that would do this is refused (section 5)
