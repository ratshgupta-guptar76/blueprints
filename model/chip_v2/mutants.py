"""Deliberately broken copies of the chip model, one small fault each.

Each entry is a mistake the RTL could plausibly contain. Replaying the recorded
traces against a mutant shows whether the scenarios, looking only at the pins,
would notice that mistake. A mutant that survives is a hole: either a scenario
is missing, or the fault cannot be seen from the pins at all and needs a test
inside the chip (those are marked `inside`).

A fault is a text substitution in chip.py or crc.py, applied to a private copy
of the module. The original must contain the old text exactly once.
"""
from __future__ import annotations

import types
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent


@dataclass(frozen=True)
class Mutant:
    name: str
    section: str            # where docs/V2_SPEC.md fixes the behaviour
    file: str               # "chip" or "crc"
    old: str
    new: str
    inside: bool = False    # known not to be visible at the pins without fault injection


M = Mutant
MUTANTS = [
    # ---- inbound frames (section 4)
    M("sync symbol is 0x5", "4", "chip", "SYNC_IN = 0xA", "SYNC_IN = 0x5"),
    M("CRC polynomial 0x07", "4", "crc", "CRC_POLY, CRC_INIT = 0x1D, 0xFF", "CRC_POLY, CRC_INIT = 0x07, 0xFF"),
    M("CRC starts at 0", "4", "crc", "CRC_POLY, CRC_INIT = 0x1D, 0xFF", "CRC_POLY, CRC_INIT = 0x1D, 0x00"),
    M("CRC takes each symbol bit 0 first", "4", "crc", "for i in (3, 2, 1, 0):", "for i in (0, 1, 2, 3):"),
    M("first header symbol left out of the CRC", "4", "chip",
      "self.rx_crc = crc8_symbol(CRC_INIT, sym)", "self.rx_crc = CRC_INIT"),
    M("received CRC nibbles swapped", "4", "chip",
      "if ((self.rx_hi << 4) | sym) == self.rx_crc:", "if ((sym << 4) | self.rx_hi) == self.rx_crc:"),
    M("frame type not checked", "4", "chip", "if self.rx_hdr >> 6:", "if False:"),
    M("payload is 64 symbols even at P = 1", "4", "chip",
      "n = 8 if self.p_reg == 1 else 64", "n = 64"),
    M("input lanes reversed", "4", "chip", "b = (sym >> k) & 1", "b = (sym >> (3 - k)) & 1"),
    M("1-bit load mode never selected", "4", "chip",
      "self._shift_lanes(sym, self.chain_p == 1)", "self._shift_lanes(sym, False)"),
    M("sequence number keeps 5 bits", "4", "chip", "self.chain_seq = self.rx_hdr & 63", "self.chain_seq = self.rx_hdr & 31"),
    M("overrun skips one symbol too few", "4", "chip",
      "self.rx, self.rx_left = SKIP, n + 1", "self.rx, self.rx_left = SKIP, n"),
    M("a frame during a weight burst is not an overrun", "4", "chip",
      "if chain_old != FREE or self.bist is not None or self.burst:", "if chain_old != FREE or self.bist is not None:"),
    M("a frame during a commanded self-test is not an overrun", "9", "chip",
      "if chain_old != FREE or self.bist is not None or self.burst:", "if chain_old != FREE or self.burst:"),
    M("chain not freed after a CRC failure", "4", "chip",
      "self.cnt_crc = min(self.cnt_crc + 1, 255)\n                self.chain = FREE", "self.cnt_crc = min(self.cnt_crc + 1, 255)"),
    M("recovery needs 71 idle symbols, not 72", "4", "chip", "N_RECOVER = 72", "N_RECOVER = 71"),
    M("recovery needs 73 idle symbols, not 72", "4", "chip", "N_RECOVER = 72", "N_RECOVER = 73"),
    M("recovery counts any symbol as idle", "4", "chip",
      "self.rx_idle = self.rx_idle + 1 if sym == 0 else 0", "self.rx_idle = self.rx_idle + 1"),
    # ---- pipeline (section 5)
    M("bit planes not weighted", "5", "chip", "wrap(a + (v << self.plane), ACC_W)", "wrap(a + v, ACC_W)"),
    M("weight sign column added, not subtracted", "5", "chip",
      "- (int(c[DW - 1]) << (DW - 1))", "+ (int(c[DW - 1]) << (DW - 1))"),
    M("accumulators not cleared at start", "5", "chip",
      "self.acc = [0] * NW             # start: clear, then P compute edges", "pass"),
    M("accumulators 20 bits wide", "5", "chip", "ACC_W = 21", "ACC_W = 20"),
    M("start waits for the capture to finish", "5", "chip",
      "(not acc_valid_old or capture)", "(not acc_valid_old)"),
    M("capture waits for a fully idle transmitter", "5", "chip", "tx_cnt_old <= 1", "tx_cnt_old == 0"),
    M("gate_off has no effect", "8", "chip", "            if not self.mode & M_GATE_OFF:", "            if True:"),
    M("tx_silence has no effect", "7", "chip", "if self.mode & M_TX_SILENCE:", "if False:"),
    M("act_spi does not stop link frames", "8", "chip", "if self.mode & M_ACT_SPI:\n                self.rx = HUNT", "if False:\n                self.rx = HUNT"),
    M("busy does not include a waiting result", "5", "chip",
      "return (self.chain != FREE or self.acc_valid or self.bist", "return (self.chain != FREE or self.bist"),
    M("busy does not include a burst in progress", "5", "chip", " or self.burst\n", "\n"),
    M("an ACT burst does not hold the chip busy", "5", "chip",
      "self.burst = self.s_ok\n", "self.burst = self.s_ok and addr == A_WEIGHTS\n"),
    M("the busy rule is not applied when a register is written", "5", "chip",
      "if self.s_n == REG_BYTES.get(addr, 1) and self._guard(addr, busy):", "if self.s_n == REG_BYTES.get(addr, 1):"),
    M("a frame starting on the same edge as a write is not seen as busy", "5", "chip",
      "busy_w = busy_old or self.rx_started", "busy_w = busy_old"),
    M("busy includes a draining transmitter", "5", "chip",
      "or self.act_cnt > 0 or self.row_rd)", "or self.act_cnt > 0 or self.row_rd or self.tx_cnt > 0)"),
    # ---- requantize (section 6)
    M("requantize without the ReLU", "6", "chip", "min(max(r + bias, 0) >> shift, 255)", "min(abs(r + bias) >> shift, 255)"),
    M("requantize wraps, does not limit", "6", "chip",
      "min(max(r + bias, 0) >> shift, 255)", "(max(r + bias, 0) >> shift) & 255"),
    M("requantize limits to 127", "6", "chip", "min(max(r + bias, 0) >> shift, 255)", "min(max(r + bias, 0) >> shift, 127)"),
    M("bias read as unsigned", "6", "chip", "self.bias[addr - 5] = wrap(v, 21)", "self.bias[addr - 5] = v & 0x1FFFFF"),
    M("bias 20 bits wide", "6", "chip", "self.bias[addr - 5] = wrap(v, 21)", "self.bias[addr - 5] = wrap(v, 20)"),
    M("shift keeps 3 bits", "6", "chip", "self.shift = v & 15", "self.shift = v & 7"),
    M("every output uses bias 0", "6", "chip", "requant(r, self.bias[j], self.shift)", "requant(r, self.bias[0], self.shift)"),
    # ---- return frames (section 7)
    M("return sync word is 1, 0, 1, 1", "7", "chip", "TX_SYNC = (0xF, 0xF, 0x0, 0xF)", "TX_SYNC = (0xF, 0x0, 0xF, 0xF)"),
    M("return header halves swapped", "7", "chip", "body = [hdr >> 4, hdr & 15]", "body = [hdr & 15, hdr >> 4]"),
    M("requantized frame marked as raw", "7", "chip", "typ, width = 1, 8", "typ, width = 0, 8"),
    M("return CRC halves swapped", "7", "chip", "+ [crc >> 4, crc & 15]", "+ [crc & 15, crc >> 4]"),
    M("return frame sequence number always 0", "7", "chip",
      "self.acc_seq, self.acc_p = self.chain_seq, self.chain_p", "self.acc_seq, self.acc_p = 0, self.chain_p"),
    # ---- SPI and registers (section 8)
    M("identity constant wrong", "8", "chip", "ID = 0xDC1A0002", "ID = 0xDC1A0003"),
    M("multi-byte registers read least significant byte first", "8", "chip",
      "[(v >> (8 * (n - 1 - i))) & 0xFF for i in range(n)]", "[(v >> (8 * i)) & 0xFF for i in range(n)]"),
    M("results not sign-extended to 24 bits", "8", "chip",
      "return self.result[addr - 0x0C] & 0xFFFFFF", "return self.result[addr - 0x0C] & 0x1FFFFF"),
    M("weight row bits in the wrong order", "8", "chip",
      "row = sum(((self.s_acc >> (31 - c)) & 1) << c for c in range(ROWS))", "row = self.s_acc"),
    M("weight rows written last row first", "8", "chip",
      "self._write_row(self.wrow, row)", "self._write_row(31 - self.wrow, row)"),
    M("chip select high does not reset the bit counter", "8", "chip",
      "if v:                               # chip select high resets the bit counter (asynchronous)\n            self.s_bit = 0",
      "if v:\n            pass"),
    M("writes while busy are carried out", "5", "chip", "if addr in GUARDED and busy:\n            self.err_busy = True\n            return False", "if False:\n            pass"),
    M("P is not protected while busy", "5", "chip", "GUARDED = {A_MODE, A_P,", "GUARDED = {A_MODE,"),
    M("START is not protected while busy", "5", "chip", "8, A_START, A_WEIGHTS,", "8, A_WEIGHTS,"),
    M("an ignored write does not set err_busy", "5", "chip",
      "if addr in GUARDED and busy:\n            self.err_busy = True", "if addr in GUARDED and busy:\n            pass"),
    M("ACT over JTAG is accepted without act_spi", "8", "chip",
      "if addr == A_ACT and not self.mode & M_ACT_SPI:\n                    self.err_busy = True                # ACT", "if False:\n                    pass  # ACT"),
    M("CLEAR bit 2 does not abandon a half-loaded vector", "8", "chip",
      "if v & 4 and self.chain == LOADING:", "if False:"),
    M("the core does not wait for the link to confirm its reset", "2", "chip",
      "if not lr_old:\n                self.lnk = L_DOWN", "if True:\n                self.lnk = L_DOWN"),
    M("the FIFO is not emptied when the link comes up", "2", "chip",
      "self.rptr = wp_seen             # follow", "self.rptr = 0                   # follow"),
    M("the link enable is not held low while the link closes", "2", "chip",
      "and self.lnk != L_CLOSING))", "))"),
    M("act_spi leaves the receiver where it was", "8", "chip",
      "self.rx = HUNT                          # link frames are ignored (section 8)", "pass"),
    M("a compute can start while a row is being written", "8.2", "chip",
      "(not acc_valid_old or capture) and wc_idle_old:", "(not acc_valid_old or capture):"),
    M("a row read does not wait for the write port", "8.2", "chip",
      "if self.wc != 0 or self.wc_pending is not None:\n                self.row_rd = True", "if False:\n                self.row_rd = True", inside=True),
    M("the write controller has no hold cycle", "8.2", "chip",
      "self.wc = 3                                 # hold: address and data stay", "self.wc = 0", inside=True),
    M("ACT is accepted without act_spi", "8", "chip",
      "if addr == A_ACT and not self.mode & M_ACT_SPI:\n                        self.s_ok, self.err_busy = False, True", "if False:\n                        pass"),
    M("STATUS.busy stuck at 0", "8.1", "chip", "return (int(self._busy()) | (self.chain == LOADED) << 1", "return (0 | (self.chain == LOADED) << 1"),
    M("STATUS.chain_loaded stuck at 0", "8.1", "chip", "(self.chain == LOADED) << 1", "0 << 1"),
    M("STATUS.acc_valid stuck at 0", "8.1", "chip", "| int(self.acc_valid) << 2", "| 0 << 2"),
    M("STATUS.tx_busy stuck at 0", "8.1", "chip", "| (self.tx_cnt > 0) << 3", "| 0 << 3"),
    M("STATUS.link_ready stuck at 0", "8.1", "chip", "| self.lr_s2 << 6", "| 0 << 6"),
    M("STATUS.selftest_done stuck at 0", "8.1", "chip", "| int(self.selftest_done) << 7", "| 0 << 7"),
    M("CLEAR bit 0 does not clear the counters", "8", "chip",
      "if v & 1:\n                self.cnt_crc", "if v & 4:\n                self.cnt_crc"),
    M("CLEAR bit 1 does not clear the sticky flags", "8", "chip",
      "if v & 2:\n                self.err_busy", "if v & 4:\n                self.err_busy"),
    M("CRC counter wraps at 256", "8", "chip", "self.cnt_crc = min(self.cnt_crc + 1, 255)", "self.cnt_crc = (self.cnt_crc + 1) & 255"),
    M("overrun counter wraps at 256", "8", "chip", "self.cnt_ovr = min(self.cnt_ovr + 1, 255)", "self.cnt_ovr = (self.cnt_ovr + 1) & 255"),
    M("bad-frame counter never counts", "8", "chip", "self.cnt_bad = min(self.cnt_bad + 1, 255)", "pass"),
    M("row read-back reads the neighbouring row", "8", "chip",
      "self.row_data = self._read_row(self.row_sel)    # one cycle", "self.row_data = self._read_row(self.row_sel ^ 1)    # one cycle"),
    M("P register keeps 2 bits", "8", "chip", "self.p_reg = (v & 7) + 1", "self.p_reg = (v & 3) + 1"),
    M("START takes P from the last frame, not the register", "8", "chip",
      "self.chain = LOADED\n            self.chain_p = self.p_reg", "self.chain = LOADED"),
    M("activations over SPI shift in most significant bit first", "8", "chip",
      "self._shift_joined((self.act_sr >> self.act_cnt) & 1, self.p_reg == 1)",
      "self._shift_joined((self.act_sr >> (7 - self.act_cnt % 8)) & 1, self.p_reg == 1)"),
    # ---- crossings (section 3) and reset (section 2)
    M("SPI word acted on one CLK edge early (X2)", "3", "chip",
      "spi_evt = self.spi_s2 != self.spi_s3", "spi_evt = self.spi_s1 != self.spi_s2"),
    M("link symbol used one CLK edge early (X1)", "3", "chip",
      "wp_seen = gray2bin(self.wp_s2)", "wp_seen = gray2bin(self.wp_s1)"),
    M("JTAG request acted on one CLK edge early (X4)", "3", "chip",
      "jt_evt = self.jt_s2 != self.jt_s3", "jt_evt = self.jt_s1 != self.jt_s2"),
    M("core leaves reset after 3 CLK edges, not 2", "2", "chip", "if self.core_rst < 2:", "if self.core_rst < 3:"),
    M("link leaves reset one LINK_CLK edge early", "2", "chip",
      "self.l_en_s2, self.l_en_s1 = self.l_en_s1, x.get(\"link_go\")", "self.l_en_s2 = self.l_en_s1 = x.get(\"link_go\")"),
    M("link FIFO write pointer not Gray coded on the way out", "3", "chip",
      "x.put(\"wptr_gray\", bin2gray(self.wptr))", "x.put(\"wptr_gray\", self.wptr)"),
    M("MISO shifts on the edge that loads it (X3)", "3", "chip",
      "if self.miso_loaded:\n            self.miso_loaded = False\n        else:", "if True:"),
    # ---- self-test (section 9)
    M("compute test reports pass and fail swapped", "9", "chip",
      "return B_PASS if sig == self.cbist_expect else B_FAIL", "return B_FAIL if sig == self.cbist_expect else B_PASS"),
    M("compute test runs 15 vectors", "9", "chip", "CBIST_VECTORS = 16", "CBIST_VECTORS = 15"),
    M("heartbeat twice as fast", "9", "chip", "self.status = (self.cyc >> 15) & 1", "self.status = (self.cyc >> 14) & 1"),
    M("no DONE pulse", "9", "chip", "self.status = int(self.done_pulse)", "self.status = 0"),
    M("STATUS low after a failed self-test", "9", "chip",
      "        else:\n            self.status = 1", "        else:\n            self.status = 0"),
    M("the write that aborts a self-test is dropped", "9", "chip",
      "self._abort_bist()\n            return True", "self._abort_bist()\n            return False"),
    M("BIST_STAT fields in the wrong place", "8", "chip",
      "return self.mb_state | (self.cb_state << 2)", "return self.mb_state | (self.cb_state << 4)"),
    M("BIST_CTRL bit 1 also runs the memory test", "8", "chip",
      "self.bist = self._run_tests(bool(v & 1), bool(v & 2))", "self.bist = self._run_tests(bool(v & 3), bool(v & 2))"),
    M("memory test uses 0x33333333 for its second pattern", "9", "chip",
      "for d in (0x00000000, 0x55555555):", "for d in (0x00000000, 0x33333333):", inside=True),
    M("memory test skips the descending passes", "9", "chip",
      "((1, d, nd), (1, nd, d), (-1, d, nd), (-1, nd, d))", "((1, d, nd), (1, nd, d))"),
    # ---- JTAG (section 10)
    M("IDCODE bit 0 not forced to 1", "10", "chip", "self.dr = ID | 1", "self.dr = ID"),
    M("MBIST and CBIST instruction codes swapped", "10", "chip",
      "= 0b001, 0b010, 0b011, 0b100, 0b111", "= 0b001, 0b010, 0b100, 0b011, 0b111"),
    M("DEBUG ready bit one place low", "10", "chip", "self.dr = (int(ready) << 39)", "self.dr = (int(ready) << 38)"),
    M("BYPASS is two bits long", "10", "chip", "DR_LEN.get(self.ir, 1)", "DR_LEN.get(self.ir, 2)"),
    M("TAP reset does not select IDCODE", "10", "chip",
      "if self.tap == TLR:\n            self.ir = IR_IDCODE", "if self.tap == TLR:\n            pass"),
    M("JTAG weight write does not step ROW_SEL", "10", "chip",
      "self.row_sel = (self.row_sel + 1) & 31", "pass"),
    M("JTAG write wins a tie with SPI", "10", "chip",
      "if spi_evt and self.s_cmd is not None and self.s_cmd >> 7:", "if False:"),
    M("JTAG answers are not one scan behind", "10", "chip",
      "ready = self.ja_s2 == self.jreq_t", "ready = True"),
    M("TDO changes on the rising edge", "10", "chip",
      "self.tap = NEXT[st][self.tms]", "self.tdo = self.dr & 1 if st == SH_DR else self.tdo\n        self.tap = NEXT[st][self.tms]"),

    # ---- the corners of the register map, the return frames and the TAP (spec gaps S8 to S21)
    M("an unreadable address does not read 0", "8", "chip",
      "        return 0\n\n    def _command", "        return 0xFFFFFFFF\n\n    def _command"),
    M("a write to a read-only register sets err_busy", "8", "chip",
      "if addr in GUARDED and busy:", "if addr in GUARDED and busy or addr in REG_BYTES and addr not in GUARDED | {A_CLEAR}:"),
    M("a write to an undefined address sets err_busy", "8", "chip",
      "if addr in GUARDED and busy:", "if addr in GUARDED and busy or addr > A_ROW_DATA:"),
    M("MODE keeps reserved bit 5", "8", "chip", "self.mode = v & 0x1F", "self.mode = v & 0x3F"),
    M("ROW_SEL ignores a write with reserved bits set", "8", "chip",
      "self.row_sel = v & 31", "self.row_sel = v & 31 if v < 32 else self.row_sel"),
    M("BIAS reads back sign-extended to 24 bits", "8", "chip",
      "return self.bias[addr - 5] & 0x1FFFFF", "return self.bias[addr - 5] & 0xFFFFFF"),
    M("START keeps 7 bits", "8", "chip", "self.chain_seq = v & 63", "self.chain_seq = v & 127"),
    M("CLEAR bit 3 also clears the counters", "8", "chip",
      "if v & 1:\n                self.cnt_crc", "if v & 9:\n                self.cnt_crc"),
    M("BIST_CTRL bit 2 runs the compute test", "8", "chip",
      "elif addr == A_BIST_CTRL and v & 3:\n            self.bist = self._run_tests(bool(v & 1), bool(v & 2))",
      "elif addr == A_BIST_CTRL and v & 7:\n            self.bist = self._run_tests(bool(v & 1), bool(v & 6))"),
    M("bytes after a register's width write it again", "8", "chip",
      "if self.s_n == REG_BYTES.get(addr, 1) and self._guard(addr, busy):",
      "if self.s_n >= REG_BYTES.get(addr, 1) and self._guard(addr, busy):"),
    M("a read past a register's width repeats its last byte", "8", "chip",
      "if self.rd_i < len(self.rd_bytes) else 0)", "if self.rd_i < len(self.rd_bytes) else self.rd_bytes[-1])"),
    M("a register write cut short is carried out with the bytes it has", "8", "chip",
      "        if self.cs_s2:                      # chip select is high: any burst is over\n"
      "            self.burst = False",
      "        if self.cs_s2:                      # chip select is high: any burst is over\n"
      "            self.burst = False\n"
      "            if self.s_cmd is not None and self.s_cmd >> 7 and 0 < self.s_n < REG_BYTES.get(self.s_cmd & 0x7F, 1):\n"
      "                self._reg_write(self.s_cmd & 0x7F, self.s_acc)\n"
      "                self.s_n = 0"),
    M("JTAG weight write stops at row 31", "10", "chip",
      "self.row_sel = (self.row_sel + 1) & 31", "self.row_sel = min(self.row_sel + 1, 31)"),
    M("tx_silence cuts a frame already going out", "7", "chip",
      "self.link_tx = 0 if self.tx_cnt == 0 else", "self.link_tx = 0 if self.tx_cnt == 0 or self.mode & M_TX_SILENCE else"),
    M("the transmitter requantizes with the SHIFT and BIAS of each cycle", "7", "chip",
      "elif tx_cnt_old > 0:\n            self.tx_cnt -= 1",
      "elif tx_cnt_old > 0:\n            if self.mode & M_REQUANT:\n                self.tx_syms = self._frame(self.result)\n"
      "            self.tx_cnt -= 1"),
    M("the IR captures 000", "10", "chip", "self.ir_sr = 0b001", "self.ir_sr = 0b000"),
    M("BYPASS captures 1", "10", "chip",
      "                self.dr = 0\n        elif st == SH_DR:", "                self.dr = 1\n        elif st == SH_DR:"),
    M("TDO returns to 0 outside shifting", "10", "chip",
      "            self.tdo = self.ir_sr & 1", "            self.tdo = self.ir_sr & 1\n        else:\n            self.tdo = 0"),

    # ---- second methods for the requirements that had only one (plan section 4)
    M("IDCODE comes through the core clock domain", "2, 10", "chip",
      "self.dr = ID | 1", "self.dr = ID | 1 if self.core_rst >= 2 else 0"),
    M("the SPI domain needs two SCLK edges to leave reset", "2", "chip",
      "self.s_first = 1\n        self.s_tgl = 0", "self.s_first = 1\n        self.s_tgl = 0\n        self.s_bit = -2"),
    M("the read-data holding register is not reset", "2, 3", "chip",
      '"spi_word", "rd_hold", "jt_req", "jt_resp"):', '"spi_word", "jt_req", "jt_resp"):'),
    M("the JTAG answer register is not reset", "2, 3", "chip",
      '"spi_word", "rd_hold", "jt_req", "jt_resp"):', '"spi_word", "rd_hold", "jt_req"):'),
    M("the SPI word register is not reset", "2, 3", "chip",
      '"spi_word", "rd_hold", "jt_req", "jt_resp"):', '"rd_hold", "jt_req", "jt_resp"):', inside=True),
    M("the JTAG request register is not reset", "2, 3", "chip",
      '"spi_word", "rd_hold", "jt_req", "jt_resp"):', '"spi_word", "rd_hold", "jt_resp"):', inside=True),
    M("the receiver is not sent to hunt when the link goes down", "2", "chip",
      "            self.rx = HUNT\n            if en and lr_old:\n                self.lnk = L_UP\n"
      "        elif self.lnk == L_CLOSING:\n            self.rx = HUNT\n            if not lr_old:\n"
      "                self.lnk = L_DOWN\n        elif not en:\n            self.lnk = L_CLOSING\n            self.rx = HUNT",
      "            if en and lr_old:\n                self.lnk = L_UP\n"
      "        elif self.lnk == L_CLOSING:\n            if not lr_old:\n"
      "                self.lnk = L_DOWN\n        elif not en:\n            self.lnk = L_CLOSING"),
    M("one idle symbol needed between frames", "4", "chip",
      "self.touched = True\n                self.rx = HUNT", "self.touched = True\n                self.rx, self.rx_left = SKIP, 1"),
    M("the transmitter takes its width from P while draining", "5", "chip",
      "elif tx_cnt_old > 0:\n            self.tx_cnt -= 1",
      "elif tx_cnt_old > 0:\n            if self.p_reg != self.acc_p and not self.mode & M_REQUANT:\n"
      "                self.acc_p = self.p_reg\n                self.tx_syms = self._frame(self.result)\n"
      "            self.tx_cnt -= 1"),
    M("raw return width is 12 + P", "7", "chip", "typ, width = 0, 13 + self.acc_p", "typ, width = 0, 12 + self.acc_p"),
    M("LINK_TX holds its last bit after a frame", "7", "chip",
      "self.link_tx = 0 if self.tx_cnt == 0 else", "self.link_tx = self.link_tx if self.tx_cnt == 0 else"),
    M("the compute test runs first", "9", "chip",
      "yield from self._run_tests(True, True)",
      "yield from self._run_tests(False, True)\n        yield from self._run_tests(True, False)"),
    M("ID reads 0 while a self-test runs", "9", "chip",
      "if addr == A_ID:\n            return ID", "if addr == A_ID:\n            return ID if self.bist is None else 0"),
    M("Pause-DR with TMS high goes to Update-DR", "10", "chip", "PAU_DR: (PAU_DR, EX2_DR)", "PAU_DR: (PAU_DR, UPD_DR)"),
    M("Exit2-IR with TMS low goes to Pause-IR", "10", "chip", "EX2_IR: (SH_IR, UPD_IR)", "EX2_IR: (PAU_IR, UPD_IR)"),
    M("Capture-IR with TMS high goes to Shift-IR", "10", "chip", "CAP_IR: (SH_IR, EX1_IR)", "CAP_IR: (SH_IR, SH_IR)"),
    M("Update-DR with TMS high goes to Run-Test/Idle", "10", "chip", "UPD_DR: (RTI, SEL_DR)", "UPD_DR: (RTI, RTI)"),
    M("bad-frame counter wraps at 256", "8", "chip",
      "self.cnt_bad = min(self.cnt_bad + 1, 255)", "self.cnt_bad = (self.cnt_bad + 1) & 255"),
    M("IR 101 selects a 32-bit register", "10", "chip",
      "DR_LEN = {IR_IDCODE: 32, IR_DEBUG: 40, IR_MBIST: 8, IR_CBIST: 35}",
      "DR_LEN = {IR_IDCODE: 32, IR_DEBUG: 40, IR_MBIST: 8, IR_CBIST: 35, 0b101: 32}"),
]


def _load(name: str, source: str, extra: dict | None = None) -> types.ModuleType:
    mod = types.ModuleType(f"model.chip_v2.{name}")
    mod.__package__ = "model.chip_v2"
    exec(compile(source, f"<{name}>", "exec"), mod.__dict__)
    if extra:
        mod.__dict__.update(extra)
    return mod


def build(m: Mutant):
    """The ChipV2 class of a copy of the model with this one fault in it."""
    src = {f: (HERE / f"{f}.py").read_text() for f in ("chip", "crc")}
    n = src[m.file].count(m.old)
    assert n == 1, f"mutant '{m.name}': the old text occurs {n} times in {m.file}.py, it must occur once"
    src[m.file] = src[m.file].replace(m.old, m.new)
    extra = None
    if m.file == "crc":
        crc = _load("crc_mutant", src["crc"])
        extra = {"crc8_symbol": crc.crc8_symbol, "CRC_INIT": crc.CRC_INIT}
    return _load("chip_mutant", src["chip"], extra).ChipV2


def check_table() -> None:
    names = [m.name for m in MUTANTS]
    assert len(set(names)) == len(names), "two mutants share a name"
    for m in MUTANTS:
        build(m)
