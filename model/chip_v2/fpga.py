"""What sits on the other side of the pins: the clocks, the link driver, the
return-lane receiver, an SPI master, and a JTAG master. Together with the chip
this is a bench that scenarios drive.

Everything here talks to the chip only through its pins and its clock edges.
"""
from __future__ import annotations

from collections import deque

import numpy as np

from .chip import (A_ACT, A_BIAS0, A_MODE, A_P, A_RESULT0, A_SHIFT, A_START, A_STATUS, A_WEIGHTS,
                   DR_LEN, IR_DEBUG, NW, REG_BYTES, ROWS, SYNC_IN, ChipV2, wrap)
from .crc import crc8
from .sim import Clock, Sim

PS = 1000       # one nanosecond


# ------------------------------------------------------------------ encodings
def weight_bytes(w: np.ndarray) -> list[int]:
    """W [32 rows, 4 weights] INT8 -> the 128 bytes of a WEIGHTS burst. On the
    wire each row goes column 0 first, so each byte is a weight bit-reversed."""
    out = []
    for r in range(ROWS):
        for j in range(NW):
            v = int(w[r, j]) & 0xFF
            out.append(sum(((v >> b) & 1) << (7 - b) for b in range(8)))
    return out


def link_payload(a, p: int) -> list[int]:
    """Activations [32] -> payload symbols. Lane k carries row 8k + 7 first,
    each row bit 0 first (one bit per row at P = 1)."""
    per_row = 1 if p == 1 else 8
    lanes = [[(int(a[8 * k + 7 - n]) >> b) & 1 for n in range(8) for b in range(per_row)] for k in range(4)]
    return [sum(lanes[k][s] << k for k in range(4)) for s in range(8 * per_row)]


def link_frame(seq: int, a, p: int, typ: int = 0) -> list[int]:
    """Sync, header, payload, CRC (section 4)."""
    hdr = (typ << 6) | (seq & 63)
    body = [hdr >> 4, hdr & 15] + link_payload(a, p)
    crc = crc8(body)
    return [SYNC_IN] + body + [crc >> 4, crc & 15]


def act_bytes(a, p: int) -> list[int]:
    """Activations [32] -> the bytes of an ACT burst: row 31 first, bit 0 first."""
    per_row = 1 if p == 1 else 8
    bits = [(int(a[r]) >> b) & 1 for r in range(ROWS - 1, -1, -1) for b in range(per_row)]
    return [sum(bits[i + n] << (7 - n) for n in range(8)) for i in range(0, len(bits), 8)]


# ---------------------------------------------------------------- return lanes
class ReturnRx:
    """The FPGA's receiver for the four return lanes. Each lane is lined up by
    its own sync word before symbols are formed and the CRC is checked."""

    def __init__(self, lane_delay=(0, 0, 0, 0)):
        self.delay = [deque([0] * d) for d in lane_delay]
        self.q: list[list[int]] = [[] for _ in range(NW)]
        self.frames: list[dict] = []
        self.sync_errors = 0
        self.p = 8                  # the FPGA knows the precision it configured
        self.cycle = 0

    def sample(self, pins: int) -> None:
        self.cycle += 1
        for j in range(NW):
            self.delay[j].append((pins >> j) & 1)
            self.q[j].append(self.delay[j].popleft())
        self._assemble()

    def _assemble(self) -> None:
        q = self.q
        while True:
            for j in range(NW):
                n = 0
                while n < len(q[j]) and q[j][n] == 0:
                    n += 1
                del q[j][:n]                            # idle
            if min(len(x) for x in q) < 6:
                return
            bad = [j for j in range(NW) if q[j][:4] != [1, 1, 0, 1]]
            if bad:
                self.sync_errors += 1
                for j in bad:
                    del q[j][:1]
                continue
            hdr = sum(q[j][4] << (4 + j) for j in range(NW)) | sum(q[j][5] << j for j in range(NW))
            width = 8 if hdr >> 6 == 1 else 13 + self.p
            if min(len(x) for x in q) < 8 + width:
                return
            body = [sum(q[j][i] << j for j in range(NW)) for i in range(4, 6 + width)]
            crc = (sum(q[j][6 + width] << (4 + j) for j in range(NW))
                   | sum(q[j][7 + width] << j for j in range(NW)))
            vals = [sum(q[j][6 + i] << i for i in range(width)) for j in range(NW)]
            if hdr >> 6 == 0:
                vals = [wrap(v, width) for v in vals]
            for j in range(NW):
                del q[j][:8 + width]
            self.frames.append({"seq": hdr & 63, "type": hdr >> 6, "vals": vals,
                                "ok": crc8(body) == crc, "cycle": self.cycle})


# ----------------------------------------------------------------------- bench
class Bench:
    def __init__(self, clk: int = 40 * PS, link: int | None = None, link_phase: int = 7 * PS,
                 seed: int = 0, meta: int = 0, lane_delay=(0, 0, 0, 0)):
        self.sim = Sim(seed, meta)
        self.T = clk
        self.chip = ChipV2(self.sim, clk)
        self.rx = ReturnRx(lane_delay)
        self.stream: deque[int] = deque()       # symbols waiting to go out on LINK_D
        self.lcyc = 0
        self.status_trace: list[int] = []
        self.trace_status = False
        self.clk = Clock(self.sim, clk, clk, on_rise=self._clk_rise)
        self.link = Clock(self.sim, link or clk, clk + link_phase, on_rise=self.chip.link_rise,
                          on_fall=self._link_fall)
        self._spi_free = 0
        self._jtag_free = 0
        self.spi_period = clk
        self.tck_period = 4 * clk

    # -- clocks
    def _clk_rise(self) -> None:
        self.rx.sample(self.chip.link_tx)       # the FPGA sees what was driven before this edge
        if self.trace_status:
            self.status_trace.append(self.chip.status)
        self.chip.clk_rise()

    def _link_fall(self) -> None:
        self.lcyc += 1
        self.chip.link_d = self.stream.popleft() if self.stream else 0

    def run(self, cycles: float) -> None:
        self.sim.run_for(int(cycles * self.T))

    def reset(self, cycles: int = 4) -> None:
        self.chip.set_rst_n(0)
        self.run(cycles)
        self.chip.set_rst_n(1)

    def wait(self, cond, limit: int = 200_000, what: str = "condition") -> int:
        """Run until cond() is true. Returns the CLK cycles it took."""
        start = self.chip.cyc
        for _ in range(limit):
            if cond():
                return self.chip.cyc - start
            self.run(1)
        raise TimeoutError(f"timed out waiting for {what}")

    # -- SPI master, mode 0
    def spi(self, tx: list[int], period: int | None = None, offset: int = 0, cut_bits: int | None = None,
            block: bool = True) -> list[int]:
        """One transaction. Returns the bytes read on MISO. cut_bits raises
        chip select early, after that many bits."""
        T = period or self.spi_period
        sim, chip = self.sim, self.chip
        bits = [(b >> (7 - i)) & 1 for b in tx for i in range(8)]
        if cut_bits is not None:
            bits = bits[:cut_bits]
        got: list[int] = []
        t0 = max(sim.t, self._spi_free) + T + offset
        sim.at(t0, lambda: chip.spi_cs(0))
        for i, b in enumerate(bits):
            t = t0 + T // 2 + i * T
            sim.at(t, lambda b=b: setattr(chip, "mosi", b))
            sim.at(t + T // 2, lambda: (got.append(chip.miso), chip.spi_rise()))
            sim.at(t + T, chip.spi_fall)
        t_end = t0 + T // 2 + len(bits) * T + T // 2
        sim.at(t_end, lambda: chip.spi_cs(1))
        self._spi_free = t_end + T
        if block:
            # A byte is acted on by the core on the third CLK edge after the SCLK edge
            # that completed it (crossing X2), so allow for that before returning.
            sim.run_until(self._spi_free + 4 * self.T)
        return_bytes = lambda: [sum(got[8 * k + i] << (7 - i) for i in range(8)) for k in range(len(got) // 8)]
        return return_bytes() if block else return_bytes

    def wr(self, addr: int, value: int, **kw) -> None:
        n = REG_BYTES[addr]
        self.spi([0x80 | addr] + [(value >> (8 * (n - 1 - i))) & 0xFF for i in range(n)], **kw)

    def rd(self, addr: int, **kw) -> int:
        n = REG_BYTES[addr]
        data = self.spi([addr, 0] + [0] * n, **kw)[2:]
        return sum(b << (8 * (n - 1 - i)) for i, b in enumerate(data))

    def load_weights(self, w: np.ndarray, **kw) -> None:
        self.spi([0x80 | A_WEIGHTS] + weight_bytes(w), **kw)
        self.run(8)                             # the last row: three write cycles after it crosses

    def results(self) -> list[int]:
        return [wrap(self.rd(A_RESULT0 + j), 24) for j in range(NW)]

    def spi_vector(self, a, p: int, seq: int = 0) -> list[int]:
        """One vector with no link: ACT, START, then read RESULT0..3."""
        self.spi([0x80 | A_ACT] + act_bytes(a, p))
        self.wr(A_START, seq)
        self.wait(lambda: not self.chip._busy(), what="the vector to finish")
        return self.results()

    # -- JTAG master
    def jtag(self, steps: list[tuple[int, int]], period: int | None = None, clk_running: bool = True) -> list[int]:
        """Clock (tms, tdi) pairs. Returns TDO as sampled at each rising edge."""
        T = period or self.tck_period
        sim, chip = self.sim, self.chip
        got: list[int] = []
        t0 = max(sim.t, self._jtag_free) + T
        for i, (tms, tdi) in enumerate(steps):
            t = t0 + i * T

            def setup(tms=tms, tdi=tdi):
                chip.tms, chip.tdi = tms, tdi
            sim.at(t, setup)
            sim.at(t + T // 2, lambda: (got.append(chip.tdo), chip.tck_rise()))
            sim.at(t + T, chip.tck_fall)
        self._jtag_free = t0 + len(steps) * T
        sim.run_until(self._jtag_free)
        return got

    def jtag_reset(self) -> None:
        self.jtag([(1, 0)] * 5 + [(0, 0)])

    def jtag_ir(self, ir: int) -> None:
        self.jtag([(1, 0), (1, 0), (0, 0), (0, 0)] + [(int(i == 2), (ir >> i) & 1) for i in range(3)]
                  + [(1, 0), (0, 0)])

    def jtag_dr(self, value: int, n: int) -> int:
        got = self.jtag([(1, 0), (0, 0), (0, 0)] + [(int(i == n - 1), (value >> i) & 1) for i in range(n)]
                        + [(1, 0), (0, 0)])
        return sum(b << i for i, b in enumerate(got[3:3 + n]))

    def jtag_read(self, addr: int) -> int:
        """Ask, then collect. The collecting scan repeats the same read, so it can
        simply be retried until its ready bit is set."""
        self.jtag_ir(IR_DEBUG)
        n = DR_LEN[IR_DEBUG]
        req = addr << 32
        self.jtag_dr(req, n)
        for _ in range(20):
            got = self.jtag_dr(req, n)
            if got >> 39:
                return got & 0xFFFFFFFF
        raise TimeoutError("JTAG DEBUG never reported ready")

    def jtag_write(self, addr: int, data: int) -> None:
        self.jtag_ir(IR_DEBUG)
        self.jtag_dr((1 << 39) | (addr << 32) | (data & 0xFFFFFFFF), DR_LEN[IR_DEBUG])

    # -- common set-up
    def start(self, w: np.ndarray | None = None, p: int = 8, mode: int = 1, shift: int = 0,
              bias=(0, 0, 0, 0), skip_selftest: bool = True) -> None:
        """Reset, optionally cut the self-test short with the first write, configure."""
        self.reset()
        if not skip_selftest:
            self.wait(lambda: self.chip.selftest_done, what="self-test")
        self.wr(A_P, p - 1)
        self.wr(A_SHIFT, shift)
        for j in range(NW):
            self.wr(A_BIAS0 + j, int(bias[j]) & 0x1FFFFF)
        if w is not None:
            self.load_weights(w)
        self.wr(A_MODE, mode)
        self.rx.p = p
        if mode & 1:
            self.wait(lambda: self.chip.lr_s2, what="the link to come out of reset")


def reference(w: np.ndarray, a) -> list[int]:
    """W^T a."""
    return [int(v) for v in np.asarray(a, dtype=np.int64) @ np.asarray(w, dtype=np.int64)]


class PinFpga:
    """The FPGA's schedule on top of the bench, so a whole network can run with
    every multiply-accumulate going through the chip's pins. matvec() has the
    signature network.py expects: W^T a for one layer and a batch of vectors.

    Per weight set: wait for idle, write the set over SPI, send one frame per
    vector at the per-vector period, collect the return frames."""

    def __init__(self, bench: Bench, spacing: int = 75):
        self.b, self.spacing = bench, spacing
        self.p = 8
        self.sets = self.passes = 0

    def matvec(self, w: np.ndarray, a: np.ndarray, bits: int) -> np.ndarray:
        b = self.b
        if bits != self.p:
            b.wait(lambda: not b.chip._busy() and not b.chip.tx_cnt, what="idle before changing P")
            b.wr(A_P, bits - 1)
            self.p = b.rx.p = bits
        n_in, n_out = w.shape
        out = np.zeros((a.shape[0], n_out), dtype=np.int64)
        for g in range(0, n_out, NW):
            for c in range(0, n_in, ROWS):
                blk = w[c:c + ROWS, g:g + NW]
                wset = np.zeros((ROWS, NW), dtype=np.int64)
                wset[:blk.shape[0], :blk.shape[1]] = blk        # unused rows and outputs stay zero
                aset = np.zeros((a.shape[0], ROWS), dtype=np.int64)
                aset[:, :blk.shape[0]] = a[:, c:c + ROWS]
                b.wait(lambda: not b.chip._busy(), what="idle before a weight write")
                b.load_weights(wset)
                out[:, g:g + blk.shape[1]] += self._run(aset)[:, :blk.shape[1]]   # partial sums add here
                self.sets += 1
        return out

    def _run(self, aset: np.ndarray) -> np.ndarray:
        b, n = self.b, len(aset)
        b.rx.frames.clear()
        spacing = self.spacing if self.p != 1 else 22
        for i in range(n):
            f = link_frame(i & 63, aset[i], self.p)
            b.stream.extend(f + [0] * (spacing - len(f)))
        b.wait(lambda: len(b.rx.frames) >= n, limit=n * spacing + 2000, what="every result of a weight set")
        frames = b.rx.frames[:n]
        assert all(f["ok"] and f["seq"] == i & 63 for i, f in enumerate(frames)), "a return frame was bad or out of order"
        assert b.chip.cnt_ovr == 0 and b.chip.cnt_crc == 0
        self.passes += n
        return np.array([f["vals"] for f in frames], dtype=np.int64)

