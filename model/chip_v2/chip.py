"""The v2 chip at its pins, one clock edge at a time. Written from
docs/V2_SPEC.md; section numbers in comments refer to it.

Four clock domains, each with its own edge function:

    clk_rise()             core: parser, chain, compute, transmitter, registers, self-test
    link_rise()            link: sample the four lanes, write the FIFO
    spi_rise(), spi_fall() SPI: an 8-bit shift register and a toggle
    tck_rise(), tck_fall() JTAG: the TAP

Nothing passes between domains except through `self.x` (a Crossing), so every
crossing is visible in one place and can be checked.
"""
from __future__ import annotations

import numpy as np

from .crc import CRC_INIT, MISR_SEED, Lfsr16, crc8_symbol, misr_step
from .sim import Crossing, Sim

ROWS, DW, NW = 32, 8, 4
ACC_W = 21
ID = 0xDC1A0002
SYNC_IN = 0xA
TX_SYNC = (0xF, 0xF, 0x0, 0xF)          # every lane sends 1, 1, 0, 1
N_RECOVER = 72
FIFO_DEPTH = 8
BIST_TIMEOUT = 8192
CBIST_VECTORS = 16

# Register addresses (section 8)
(A_ID, A_STATUS, A_MODE, A_P, A_SHIFT, A_BIAS0, A_START, A_WEIGHTS, A_ACT, A_RESULT0, A_CNT_CRC,
 A_CNT_OVR, A_CNT_BAD, A_CLEAR, A_BIST_CTRL, A_BIST_STAT, A_BIST_ROW, A_CBIST_SIG, A_ROW_SEL,
 A_ROW_DATA) = (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x09, 0x0A, 0x0B, 0x0C, 0x10,
                0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19)
REG_BYTES = {A_ID: 4, A_STATUS: 2, A_MODE: 1, A_P: 1, A_SHIFT: 1, 5: 3, 6: 3, 7: 3, 8: 3, A_START: 1,
             0x0C: 3, 0x0D: 3, 0x0E: 3, 0x0F: 3, A_CNT_CRC: 1, A_CNT_OVR: 1, A_CNT_BAD: 1, A_CLEAR: 1,
             A_BIST_CTRL: 1, A_BIST_STAT: 1, A_BIST_ROW: 1, A_CBIST_SIG: 4, A_ROW_SEL: 1, A_ROW_DATA: 4}
GUARDED = {A_MODE, A_P, A_SHIFT, 5, 6, 7, 8, A_START, A_WEIGHTS, A_ACT, A_BIST_CTRL, A_ROW_SEL}

M_LINK_EN, M_ACT_SPI, M_GATE_OFF, M_TX_SILENCE, M_REQUANT = 1, 2, 4, 8, 16

FREE, LOADING, LOADED, COMPUTING = range(4)                             # activation chain
HUNT, HDR1, HDR2, PAYLOAD, CRC1, CRC2, SKIP, RECOVER = range(8)         # link receiver
B_RUN, B_PASS, B_FAIL, B_ABORT = range(4)                               # self-test result

# JTAG TAP states and the standard transition table: NEXT[state][tms]
(TLR, RTI, SEL_DR, CAP_DR, SH_DR, EX1_DR, PAU_DR, EX2_DR, UPD_DR,
 SEL_IR, CAP_IR, SH_IR, EX1_IR, PAU_IR, EX2_IR, UPD_IR) = range(16)
NEXT = {TLR: (RTI, TLR), RTI: (RTI, SEL_DR), SEL_DR: (CAP_DR, SEL_IR), CAP_DR: (SH_DR, EX1_DR),
        SH_DR: (SH_DR, EX1_DR), EX1_DR: (PAU_DR, UPD_DR), PAU_DR: (PAU_DR, EX2_DR),
        EX2_DR: (SH_DR, UPD_DR), UPD_DR: (RTI, SEL_DR), SEL_IR: (CAP_IR, TLR), CAP_IR: (SH_IR, EX1_IR),
        SH_IR: (SH_IR, EX1_IR), EX1_IR: (PAU_IR, UPD_IR), PAU_IR: (PAU_IR, EX2_IR),
        EX2_IR: (SH_IR, UPD_IR), UPD_IR: (RTI, SEL_DR)}
IR_IDCODE, IR_DEBUG, IR_MBIST, IR_CBIST, IR_BYPASS = 0b001, 0b010, 0b011, 0b100, 0b111
DR_LEN = {IR_IDCODE: 32, IR_DEBUG: 40, IR_MBIST: 8, IR_CBIST: 35}
J_DEBUG, J_MBIST, J_CBIST = range(3)


def bin2gray(v: int) -> int:
    return v ^ (v >> 1)


def gray2bin(g: int) -> int:
    v = 0
    while g:
        v ^= g
        g >>= 1
    return v


def wrap(v: int, width: int) -> int:
    """Keep the low `width` bits and read them as signed."""
    half = 1 << (width - 1)
    return ((v + half) & ((1 << width) - 1)) - half


def requant(r: int, bias: int, shift: int) -> int:
    """Section 6."""
    return min(max(r + bias, 0) >> shift, 255)


def cbist_patterns():
    """The compute self-test's weights [32 rows of 32 bits] and its 16 vectors
    as link symbols, from the generator. Shared by the chip model and by the
    independent calculation of the expected signature."""
    g = Lfsr16()
    rows = []
    for _ in range(ROWS):
        row = 0
        for c in range(ROWS):
            row |= g.bit() << c
        rows.append(row)
    vectors = [[sum(g.bit() << k for k in range(4)) for _ in range(64)] for _ in range(CBIST_VECTORS)]
    return rows, vectors


class ChipV2:
    def __init__(self, sim: Sim, clk_period: int):
        self.sim, self.x, self.clk_period = sim, Crossing(sim), clk_period
        # pins
        self.rst_n = 0
        self.link_d = 0
        self.link_tx = 0
        self.mosi, self.miso, self.cs_n = 0, 0, 1
        self.tms, self.tdi, self.tdo = 1, 0, 0
        self.status = 0
        # model-only: injected cell faults and what the simulation observed
        self.stuck: dict[tuple[int, int], int] = {}             # (row, column) -> stuck value
        self.coupled: dict[tuple[int, int], tuple[int, int]] = {}   # writing a 1 here also sets that cell
        self.obs = {"fifo_max": 0, "wc_collisions": 0, "x_reads": 0, "gate_leaks": 0, "act_overrun": 0}
        self.cbist_expect = cbist_signature()
        self._reset()

    # ------------------------------------------------------------------ reset
    def _reset(self) -> None:
        """Everything RST_N low forces, in every domain."""
        self.cyc = 0
        self.core_rst = 0                   # CLK edges seen since RST_N rose
        # link domain
        self.wptr = 0
        self.fifo = [0] * FIFO_DEPTH
        self.l_en_s1 = self.l_en_s2 = 0
        self.rp_s1 = self.rp_s2 = 0
        self.ovf_t = 0
        # core: synchronizers
        self.wp_s1 = self.wp_s2 = 0
        self.spi_s1 = self.spi_s2 = self.spi_s3 = 0
        self.jt_s1 = self.jt_s2 = self.jt_s3 = 0
        self.ovf_s1 = self.ovf_s2 = self.ovf_s3 = 0
        self.lr_s1 = self.lr_s2 = 0
        self.cs_s1 = self.cs_s2 = 1
        self.wload = False                  # an SPI weight burst is in progress
        self.rptr = 0
        # core: receiver
        self.rx = HUNT
        self.rx_hdr = self.rx_crc = self.rx_left = self.rx_idle = self.rx_hi = 0
        # core: chain, datapath, pipeline
        self.rows = [0] * ROWS              # activation cells, 8 bits each
        self.chain = FREE
        self.chain_p = 8
        self.chain_seq = 0
        self.plane = 0
        self.comp_left = 0
        self.w_mem = [0] * ROWS             # 32-bit rows, bit c = column c
        self.w_valid = [False] * ROWS       # written since power-up (power-up content is unknown)
        self.wbits = np.zeros((ROWS, ROWS), dtype=np.int64)
        self.acc = [0] * NW
        self.acc_valid = False
        self.acc_seq = 0
        self.acc_p = 8
        # core: transmitter
        self.tx_syms: list[int] = []
        self.tx_cnt = 0
        self.result = [0] * NW
        # core: registers
        self.mode = 0
        self.p_reg = 8
        self.shift = 0
        self.bias = [0] * NW
        self.cnt_crc = self.cnt_ovr = self.cnt_bad = 0
        self.err_busy = self.fifo_ovf = False
        self.row_sel = 0
        self.row_data = 0
        # core: SPI and JTAG decoders
        self.s_cmd = None
        self.s_n = self.s_acc = 0
        self.s_ok = False
        self.rd_bytes: list[int] = []
        self.rd_i = 0
        self.wrow = 0
        self.act_sr = self.act_cnt = 0
        self.jt_ack = 0
        # core: write controller
        self.wc = 0
        self.wc_row = self.wc_data = 0
        self.wc_pending = None
        # core: self-test
        self.mb_state = self.cb_state = B_RUN
        self.mb_row = 0
        self.cb_sig = 0
        self.bist = self._selftest()
        self.bist_owns_acc = False
        self.selftest_done = False
        self.selftest_ok = False
        self.touched = False                # a write or a valid frame has been seen
        self.done_pulse = False
        # SPI domain
        self.s_sr = self.s_bit = 0
        self.s_first = 1
        self.s_tgl = 0
        self.miso_sr = 0
        self.miso_loaded = False
        # JTAG domain
        self.tap = TLR
        self.ir = IR_IDCODE
        self.ir_sr = 0
        self.dr = 0
        self.jreq_t = 0
        self.ja_s1 = self.ja_s2 = 0
        self.link_tx = self.status = self.miso = self.tdo = 0
        for name in ("wptr_gray", "rptr_gray", "spi_tgl", "jt_tgl", "jt_ack", "ovf_tgl", "link_en", "link_rdy"):
            self.x.put(name, 0)
        self.x.put("cs_n", 1)

    def set_rst_n(self, v: int) -> None:
        self.rst_n = v
        if not v:
            self._reset()

    # ============================================================ link domain
    def link_rise(self) -> None:
        if not self.rst_n:
            return
        x = self.x
        released = self.l_en_s2
        self.l_en_s2, self.l_en_s1 = self.l_en_s1, x.get("link_en")
        if not released:                    # held in reset while the link is disabled (section 2)
            self.wptr = 0
            x.put("wptr_gray", 0)
            x.put("link_rdy", 0)
            return
        x.put("link_rdy", 1)
        rp = gray2bin(self.rp_s2)
        self.rp_s2, self.rp_s1 = self.rp_s1, x.get("rptr_gray")
        if (self.wptr - rp) & 15 == FIFO_DEPTH:         # full: the symbol is lost
            self.ovf_t ^= 1
            x.put("ovf_tgl", self.ovf_t)
            return
        self.fifo[self.wptr & 7] = self.link_d
        self.wptr = (self.wptr + 1) & 15
        x.put("wptr_gray", bin2gray(self.wptr))

    # ============================================================= SPI domain
    def spi_cs(self, v: int) -> None:
        self.cs_n = v
        self.x.put("cs_n", v)               # crossing X5: the level, through two flops in the core
        if v:                               # chip select high resets the bit counter (asynchronous)
            self.s_bit = 0
            self.s_first = 1
            self.miso_sr = 0
            self.miso = 0

    def spi_rise(self) -> None:
        if not self.rst_n or self.cs_n:
            return
        self.s_sr = ((self.s_sr << 1) | self.mosi) & 0xFF
        self.s_bit += 1
        if self.s_bit == 8:                 # a whole byte: hold it, flip the toggle (crossing X2)
            self.s_bit = 0
            self.x.put("spi_word", (self.s_first << 8) | self.s_sr)
            self.s_tgl ^= 1
            self.x.put("spi_tgl", self.s_tgl)
            self.s_first = 0
            # Crossing X3: the next byte to send is loaded on this same edge, so it
            # never races the core, whatever the SCLK rate.
            self.miso_sr = self.x.held("rd_hold", settle=self.clk_period)
            self.miso_loaded = True

    def spi_fall(self) -> None:
        if not self.rst_n or self.cs_n:
            return
        if self.miso_loaded:
            self.miso_loaded = False
        else:
            self.miso_sr = (self.miso_sr << 1) & 0xFF
        self.miso = self.miso_sr >> 7

    # ============================================================ JTAG domain
    def tck_rise(self) -> None:
        if not self.rst_n:
            return
        x, st = self.x, self.tap
        ready = self.ja_s2 == self.jreq_t
        self.ja_s2, self.ja_s1 = self.ja_s1, x.get("jt_ack")
        if st == CAP_DR:
            resp = x.held("jt_resp", settle=self.clk_period) if ready else 0
            if self.ir == IR_IDCODE:
                self.dr = ID | 1
            elif self.ir == IR_DEBUG:
                self.dr = (int(ready) << 39) | (resp & 0xFFFFFFFF)
            elif self.ir == IR_MBIST:
                self.dr = (resp & 0xFB) | (int(ready) << 2)
            elif self.ir == IR_CBIST:
                self.dr = (int(ready) << 34) | (resp & 0x3FFFFFFFF)
            else:
                self.dr = 0
        elif st == SH_DR:
            self.dr = (self.dr >> 1) | (self.tdi << (DR_LEN.get(self.ir, 1) - 1))
        elif st == CAP_IR:
            self.ir_sr = 0b001
        elif st == SH_IR:
            self.ir_sr = (self.ir_sr >> 1) | (self.tdi << 2)
        self.tap = NEXT[st][self.tms]
        if self.tap == TLR:
            self.ir = IR_IDCODE
        elif self.tap == UPD_IR:
            self.ir = self.ir_sr
        elif self.tap == UPD_DR and self.ir in (IR_DEBUG, IR_MBIST, IR_CBIST):
            kind = {IR_DEBUG: J_DEBUG, IR_MBIST: J_MBIST, IR_CBIST: J_CBIST}[self.ir]
            x.put("jt_req", (kind << 40) | (self.dr & 0xFFFFFFFFFF))    # crossing X4
            self.jreq_t ^= 1
            x.put("jt_tgl", self.jreq_t)

    def tck_fall(self) -> None:
        if not self.rst_n:
            return
        if self.tap == SH_DR:
            self.tdo = self.dr & 1
        elif self.tap == SH_IR:
            self.tdo = self.ir_sr & 1

    # ============================================================ core domain
    def _busy(self) -> bool:
        return (self.chain != FREE or self.acc_valid or self.bist is not None or self.wload
                or self.wc != 0 or self.wc_pending is not None or self.act_cnt > 0)

    def _lanes(self, plane: list[int]) -> list[int]:
        """Column sums of one bit plane, combined per weight (contracts 3, 10)."""
        colsum = np.asarray(plane, dtype=np.int64) @ self.wbits
        out = []
        for j in range(NW):
            c = colsum[j * DW:(j + 1) * DW]
            out.append(int(sum(int(c[b]) << b for b in range(DW - 1)) - (int(c[DW - 1]) << (DW - 1))))
        return out

    def _store(self, row: int, data: int) -> None:
        """What a wordline pulse leaves in the cells, with any injected faults."""
        for (r, c), (r2, c2) in self.coupled.items():
            if r == row and (data >> c) & 1:
                self.w_mem[r2] |= 1 << c2
                self._refresh(r2)
        self.w_mem[row] = data
        self.w_valid[row] = True
        self._refresh(row)

    def _refresh(self, row: int) -> None:
        bits = self.w_mem[row]
        for (r, c), v in self.stuck.items():
            if r == row:
                bits = (bits & ~(1 << c)) | (v << c)
        self.wbits[row] = [(bits >> c) & 1 for c in range(ROWS)]

    def _read_row(self, row: int) -> int:
        """One-hot activation: the 32 column sums are that row's bits (design guide 5.13)."""
        if not self.w_valid[row]:
            self.obs["x_reads"] += 1
        return sum(int(b) << c for c, b in enumerate(self.wbits[row]))

    def _shift_lanes(self, sym: int, one_bit: bool) -> None:
        """One payload symbol into the four sub-chains (section 4)."""
        old = self.rows
        new = list(old)
        for k in range(4):
            b = (sym >> k) & 1
            for i in range(8 * k, 8 * k + 8):
                src = b if i == 8 * k else old[i - 1] & 1
                new[i] = (old[i] & 0xFE) | src if one_bit else (src << 7) | (old[i] >> 1)
        self.rows = new

    def _shift_joined(self, b: int, one_bit: bool) -> None:
        """One bit into the single re-joined chain (SPI and JTAG activations)."""
        old = self.rows
        new = list(old)
        for i in range(ROWS):
            src = b if i == 0 else old[i - 1] & 1
            new[i] = (old[i] & 0xFE) | src if one_bit else (src << 7) | (old[i] >> 1)
        self.rows = new

    def clk_rise(self) -> None:
        if not self.rst_n:
            return
        if self.core_rst < 2:               # two-flop reset synchronizer
            self.core_rst += 1
            return
        self.cyc += 1
        x = self.x

        # ---- what this edge sees: everything as it was before the edge
        chain_old, acc_valid_old, tx_cnt_old = self.chain, self.acc_valid, self.tx_cnt
        acc_old = list(self.acc)
        busy_old = self._busy()
        wc_old = self.wc
        self.done_pulse = False

        # ---- synchronizers
        wp_seen = gray2bin(self.wp_s2)
        self.wp_s2, self.wp_s1 = self.wp_s1, x.get("wptr_gray")
        spi_evt = self.spi_s2 != self.spi_s3
        self.spi_s3, self.spi_s2, self.spi_s1 = self.spi_s2, self.spi_s1, x.get("spi_tgl")
        jt_evt = self.jt_s2 != self.jt_s3
        self.jt_s3, self.jt_s2, self.jt_s1 = self.jt_s2, self.jt_s1, x.get("jt_tgl")
        if self.ovf_s2 != self.ovf_s3:
            self.fifo_ovf = True
        self.ovf_s3, self.ovf_s2, self.ovf_s1 = self.ovf_s2, self.ovf_s1, x.get("ovf_tgl")
        self.lr_s2, self.lr_s1 = self.lr_s1, x.get("link_rdy")
        if self.cs_s2:                      # chip select is high: any weight burst is over
            self.wload = False
        self.cs_s2, self.cs_s1 = self.cs_s1, x.get("cs_n", 1)

        # ---- link FIFO read (crossing X1) and the receiver (section 4)
        if not self.mode & M_LINK_EN:
            self.rptr = 0
            x.put("rptr_gray", 0)
            self.rx = HUNT
        elif self.rptr != wp_seen:
            self.obs["fifo_max"] = max(self.obs["fifo_max"], (wp_seen - self.rptr) & 15)
            sym = self.fifo[self.rptr & 7]
            self.rptr = (self.rptr + 1) & 15
            x.put("rptr_gray", bin2gray(self.rptr))
            if not self.mode & M_ACT_SPI:
                self._receive(sym, chain_old)

        # ---- pipeline (section 5)
        capture = acc_valid_old and tx_cnt_old <= 1 and not self.bist_owns_acc
        if chain_old == COMPUTING:
            plane = [r & 1 for r in self.rows]
            if not self.mode & M_GATE_OFF:
                if any(p and not v for p, v in zip(plane, self.w_valid)):
                    self.obs["x_reads"] += 1
                lanes = self._lanes(plane)
                self.acc = [wrap(a + (v << self.plane), ACC_W) for a, v in zip(self.acc, lanes)]
            if self.chain_p != 1:
                self.rows = [r >> 1 for r in self.rows]
            self.plane += 1
            self.comp_left -= 1
            if self.comp_left == 0:
                self.chain = FREE
                self.acc_valid = True
                self.acc_seq, self.acc_p = self.chain_seq, self.chain_p
                self.done_pulse = True
        elif chain_old == LOADED and self.chain == LOADED and (not acc_valid_old or capture):
            self.acc = [0] * NW             # start: clear, then P compute edges
            self.chain = COMPUTING
            self.plane = 0
            self.comp_left = self.chain_p

        # ---- transmitter (section 7)
        if capture:
            self.result = acc_old
            self.acc_valid = False
            if self.mode & M_TX_SILENCE:
                self.tx_cnt = 0
                self.link_tx = 0
            else:
                self.tx_syms = self._frame(acc_old)
                self.tx_cnt = len(self.tx_syms)
                self.link_tx = self.tx_syms[0]
        elif tx_cnt_old > 0:
            self.tx_cnt -= 1
            self.link_tx = 0 if self.tx_cnt == 0 else self.tx_syms[len(self.tx_syms) - self.tx_cnt]

        # ---- write controller (section 8.2): set up, enable, hold
        if wc_old == 1:
            self._store(self.wc_row, self.wc_data)      # wordline enable is high for this cycle
            self.wc = 2
        elif wc_old == 2:
            self.wc = 0
        if self.wc == 0 and self.wc_pending is not None:
            self.wc_row, self.wc_data = self.wc_pending
            self.wc_pending = None
            self.wc = 1
        if self.wc != 0 and chain_old == COMPUTING and not self.mode & M_GATE_OFF:
            self.obs["gate_leaks"] += 1                 # a write while the activation gate is open

        # ---- activations arriving by SPI or JTAG: one bit per cycle into the joined chain
        if self.act_cnt:
            self.act_cnt -= 1
            self._shift_joined((self.act_sr >> self.act_cnt) & 1, self.p_reg == 1)

        # ---- SPI bytes (X2), then JTAG requests (X4). SPI wins a tie (section 10).
        if spi_evt:
            word = x.held("spi_word", settle=self.clk_period)
            self._spi_byte(word >> 8, word & 0xFF, busy_old)
        if jt_evt:
            self._jtag_request(x.held("jt_req", settle=self.clk_period), busy_old, spi_evt)

        # ---- self-test
        if self.bist is not None:
            try:
                next(self.bist)
            except StopIteration:
                self.bist = None

        # ---- STATUS pin (section 9)
        if self.touched:
            self.status = int(self.done_pulse)
        elif not self.selftest_done:
            self.status = 0
        elif self.selftest_ok:
            self.status = (self.cyc >> 15) & 1
        else:
            self.status = 1
        x.put("link_en", self.mode & M_LINK_EN)

    # ------------------------------------------------------------ receiver
    def _receive(self, sym: int, chain_old: int) -> None:
        st = self.rx
        if st == HUNT:
            if sym == SYNC_IN:
                self.rx = HDR1
        elif st == HDR1:
            self.rx_hi = sym
            self.rx_crc = crc8_symbol(CRC_INIT, sym)
            self.rx = HDR2
        elif st == HDR2:
            self.rx_hdr = (self.rx_hi << 4) | sym
            self.rx_crc = crc8_symbol(self.rx_crc, sym)
            if self.rx_hdr >> 6:                        # only type 0 exists
                self.cnt_bad = min(self.cnt_bad + 1, 255)
                self.rx, self.rx_idle = RECOVER, 0
            else:
                self.rx, self.rx_left = PAYLOAD, 0
        elif st == PAYLOAD:
            if self.rx_left == 0:                       # first payload symbol: is the chain free?
                n = 8 if self.p_reg == 1 else 64
                if chain_old != FREE or self.bist is not None or self.wload:
                    self.cnt_ovr = min(self.cnt_ovr + 1, 255)
                    self.rx, self.rx_left = SKIP, n + 1     # the rest of the payload, then the CRC
                    return
                self.chain = LOADING
                self.chain_p = self.p_reg               # P travels with the vector
                self.rx_left = n
            self._shift_lanes(sym, self.chain_p == 1)
            self.rx_crc = crc8_symbol(self.rx_crc, sym)
            self.rx_left -= 1
            if self.rx_left == 0:
                self.rx = CRC1
        elif st == CRC1:
            self.rx_hi = sym
            self.rx = CRC2
        elif st == CRC2:
            if ((self.rx_hi << 4) | sym) == self.rx_crc:
                self.chain = LOADED
                self.chain_seq = self.rx_hdr & 63
                self.touched = True
                self.rx = HUNT
            else:
                self.cnt_crc = min(self.cnt_crc + 1, 255)
                self.chain = FREE
                self.rx, self.rx_idle = RECOVER, 0
        elif st == SKIP:
            self.rx_left -= 1
            if self.rx_left == 0:
                self.rx = HUNT
        elif st == RECOVER:
            self.rx_idle = self.rx_idle + 1 if sym == 0 else 0
            if self.rx_idle >= N_RECOVER:
                self.rx = HUNT

    # ---------------------------------------------------------- transmitter
    def _frame(self, raw: list[int]) -> list[int]:
        """The return frame as one 4-bit symbol per cycle, bit j = lane j."""
        if self.mode & M_REQUANT:
            typ, width = 1, 8
            vals = [requant(r, self.bias[j], self.shift) for j, r in enumerate(raw)]
        else:
            typ, width = 0, 13 + self.acc_p
            vals = [r & ((1 << width) - 1) for r in raw]
        hdr = (typ << 6) | self.acc_seq
        body = [hdr >> 4, hdr & 15] + [sum(((vals[j] >> i) & 1) << j for j in range(NW)) for i in range(width)]
        crc = CRC_INIT
        for s in body:
            crc = crc8_symbol(crc, s)
        return list(TX_SYNC) + body + [crc >> 4, crc & 15]

    # ------------------------------------------------------------ registers
    def _reg_read(self, addr: int) -> int:
        if addr == A_ID:
            return ID
        if addr == A_STATUS:
            return (int(self._busy()) | (self.chain == LOADED) << 1 | int(self.acc_valid) << 2
                    | (self.tx_cnt > 0) << 3 | int(self.err_busy) << 4 | int(self.fifo_ovf) << 5
                    | self.lr_s2 << 6 | int(self.selftest_done) << 7)
        if addr == A_MODE:
            return self.mode
        if addr == A_P:
            return self.p_reg - 1
        if addr == A_SHIFT:
            return self.shift
        if 5 <= addr <= 8:
            return self.bias[addr - 5] & 0x1FFFFF
        if 0x0C <= addr <= 0x0F:
            return self.result[addr - 0x0C] & 0xFFFFFF
        if addr == A_CNT_CRC:
            return self.cnt_crc
        if addr == A_CNT_OVR:
            return self.cnt_ovr
        if addr == A_CNT_BAD:
            return self.cnt_bad
        if addr == A_BIST_STAT:
            return self.mb_state | (self.cb_state << 2)
        if addr == A_BIST_ROW:
            return self.mb_row
        if addr == A_CBIST_SIG:
            return self.cb_sig
        if addr == A_ROW_SEL:
            return self.row_sel
        if addr == A_ROW_DATA:
            return self.row_data
        return 0

    def _allowed(self, addr: int, busy: bool) -> bool:
        """The busy rule of section 5. A write during self-test aborts it and goes ahead."""
        self.touched = True
        if self.bist is not None:
            self._abort_bist()
            return True
        if addr in GUARDED and busy:
            self.err_busy = True
            return False
        return True

    def _reg_write(self, addr: int, v: int) -> None:
        if addr == A_MODE:
            self.mode = v & 0x1F
        elif addr == A_P:
            self.p_reg = (v & 7) + 1
        elif addr == A_SHIFT:
            self.shift = v & 15
        elif 5 <= addr <= 8:
            self.bias[addr - 5] = wrap(v, 21)
        elif addr == A_START:                           # compute the vector now in the chain
            self.chain = LOADED
            self.chain_p = self.p_reg
            self.chain_seq = v & 63
        elif addr == A_CLEAR:
            if v & 1:
                self.cnt_crc = self.cnt_ovr = self.cnt_bad = 0
            if v & 2:
                self.err_busy = self.fifo_ovf = False
        elif addr == A_BIST_CTRL and v & 3:
            self.bist = self._run_tests(bool(v & 1), bool(v & 2))
        elif addr == A_ROW_SEL:
            self.row_sel = v & 31
            self.row_data = self._read_row(self.row_sel)    # one cycle through the compute port

    def _spi_byte(self, first: int, byte: int, busy: bool) -> None:
        if first:
            self.s_cmd, self.s_n, self.s_acc = byte, 0, 0
            addr = byte & 0x7F
            if byte >> 7:
                self.s_ok = self._allowed(addr, busy)
                if addr == A_ACT and not self.mode & M_ACT_SPI:
                    self.s_ok, self.err_busy = False, True      # ACT needs act_spi (section 8)
                self.wrow = 0
                self.wload = self.s_ok and addr == A_WEIGHTS
            else:                                       # a read: snapshot the whole register now
                n = REG_BYTES.get(addr, 1)
                v = self._reg_read(addr)
                self.rd_bytes = [(v >> (8 * (n - 1 - i))) & 0xFF for i in range(n)]
                self.rd_i = 0
                self.x.put("rd_hold", self.rd_bytes[0])
            return
        if self.s_cmd is None:
            return
        addr = self.s_cmd & 0x7F
        if not self.s_cmd >> 7:                         # a read: line up the next byte
            self.rd_i += 1
            self.x.put("rd_hold", self.rd_bytes[self.rd_i] if self.rd_i < len(self.rd_bytes) else 0)
            return
        if not self.s_ok:
            return
        if addr == A_WEIGHTS:                           # four bytes are one row, column 0 first on the wire
            self.s_acc = (self.s_acc << 8) | byte
            self.s_n += 1
            if self.s_n == 4 and self.wrow < ROWS:
                row = sum(((self.s_acc >> (31 - c)) & 1) << c for c in range(ROWS))
                self._write_row(self.wrow, row)
                self.wrow += 1
                self.s_n = self.s_acc = 0
        elif addr == A_ACT:
            if self.act_cnt:
                self.obs["act_overrun"] += 1            # SCLK faster than CLK: section 11 rule 5 broken
            self.act_sr, self.act_cnt = byte, 8
        else:
            self.s_acc = (self.s_acc << 8) | byte
            self.s_n += 1
            if self.s_n == REG_BYTES.get(addr, 1):
                self._reg_write(addr, self.s_acc)

    def _write_row(self, row: int, data: int) -> None:
        if self.wc_pending is not None:
            self.obs["wc_collisions"] += 1
        self.wc_pending = (row, data)

    def _jtag_request(self, req: int, busy: bool, spi_evt: bool) -> None:
        kind, word = req >> 40, req & 0xFFFFFFFFFF
        write, addr, data = word >> 39, (word >> 32) & 0x7F, word & 0xFFFFFFFF
        resp = 0
        if kind == J_DEBUG and not write:
            resp = self._reg_read(addr)
        elif kind == J_DEBUG:
            if spi_evt and self.s_cmd is not None and self.s_cmd >> 7:
                self.err_busy = True                    # SPI is writing in this same cycle
            elif self._allowed(addr, busy):
                if addr == A_WEIGHTS:
                    self._write_row(self.row_sel, data)
                    self.row_sel = (self.row_sel + 1) & 31
                elif addr == A_ACT:
                    self.act_sr, self.act_cnt = data, 32
                else:
                    self._reg_write(addr, data)
        elif kind == J_MBIST:
            resp = (self.mb_row << 3) | self.mb_state
            if data & 1 and self._allowed(A_BIST_CTRL, busy):
                self._reg_write(A_BIST_CTRL, 1)
        elif kind == J_CBIST:
            resp = (self.cb_sig << 2) | self.cb_state
            if data & 1 and self._allowed(A_BIST_CTRL, busy):
                self._reg_write(A_BIST_CTRL, 2)
        self.x.put("jt_resp", resp)
        self.jt_ack ^= 1
        self.x.put("jt_ack", self.jt_ack)

    # -------------------------------------------------------------- self-test
    def _abort_bist(self) -> None:
        self.bist = None
        self.bist_owns_acc = False
        if self.mb_state == B_RUN:
            self.mb_state = B_ABORT
        if self.cb_state == B_RUN:
            self.cb_state = B_ABORT
        self.chain, self.acc_valid = FREE, False
        self.wc_pending = None
        self.selftest_done = True

    def _selftest(self):
        """Out of reset: the memory test, then the compute test."""
        yield from self._run_tests(True, True)
        self.selftest_done = True
        self.selftest_ok = self.mb_state == B_PASS and self.cb_state == B_PASS

    def _run_tests(self, memory: bool, compute: bool):
        if memory:
            self.mb_state = B_RUN
        if compute:
            self.cb_state = B_RUN
        if memory:
            self.mb_state = yield from self._timed(self._mbist())
        if compute:
            self.bist_owns_acc = True
            self.cb_state = yield from self._timed(self._cbist())
            self.bist_owns_acc = False
            self.chain, self.acc_valid = FREE, False

    def _timed(self, test):
        """Run a test one cycle at a time, with the timeout of section 9."""
        for _ in range(BIST_TIMEOUT):
            try:
                next(test)
            except StopIteration as done:
                return done.value
            yield
        return B_ABORT

    def _wr(self, row: int, data: int):
        """A row write through the write controller: three cycles."""
        self._write_row(row, data)
        yield
        yield
        yield

    def _mbist(self):
        result = B_PASS
        for d in (0x00000000, 0x55555555):
            nd = d ^ 0xFFFFFFFF
            for r in range(ROWS):
                yield from self._wr(r, d)
            for order, rd, wr in ((1, d, nd), (1, nd, d), (-1, d, nd), (-1, nd, d)):
                for r in (range(ROWS) if order > 0 else range(ROWS - 1, -1, -1)):
                    if self._read_row(r) != rd and result == B_PASS:
                        result, self.mb_row = B_FAIL, r
                    yield
                    yield from self._wr(r, wr)
            for r in range(ROWS):
                if self._read_row(r) != d and result == B_PASS:
                    result, self.mb_row = B_FAIL, r
                yield
        return result

    def _cbist(self):
        g = Lfsr16()
        for r in range(ROWS):               # weights: 4 generator bits per cycle, 8 cycles per row
            row = 0
            for i in range(8):
                for k in range(4):
                    row |= g.bit() << (4 * i + k)
                yield
            self._write_row(r, row)
        yield
        yield
        yield
        sig = MISR_SEED
        for v in range(CBIST_VECTORS):
            for _ in range(64):             # activations: through the four lanes, as a frame would
                self._shift_lanes(sum(g.bit() << k for k in range(4)), False)
                yield
            self.chain, self.chain_p, self.chain_seq = LOADED, 8, v
            yield
            while not self.acc_valid:
                yield
            for j in range(NW):
                sig = misr_step(sig, self.acc[j] & 0x1FFFFF)
                yield
            self.acc_valid = False
        self.cb_sig = sig
        return B_PASS if sig == self.cbist_expect else B_FAIL


def cbist_signature() -> int:
    """The compute self-test's expected signature, worked out from the patterns
    with ordinary arithmetic (W^T a), not by running the cycle model."""
    rows, vectors = cbist_patterns()
    w = np.zeros((ROWS, NW), dtype=np.int64)
    for r in range(ROWS):
        for j in range(NW):
            w[r, j] = wrap((rows[r] >> (DW * j)) & 0xFF, 8)
    sig = MISR_SEED
    for syms in vectors:
        a = np.zeros(ROWS, dtype=np.int64)
        for k in range(4):                  # lane k: row 8k + 7 first, each row bit 0 first
            bits = [(s >> k) & 1 for s in syms]
            for n in range(8):
                a[8 * k + 7 - n] = sum(bits[8 * n + b] << b for b in range(8))
        for y in a @ w:
            sig = misr_step(sig, int(y) & 0x1FFFFF)
    return sig
