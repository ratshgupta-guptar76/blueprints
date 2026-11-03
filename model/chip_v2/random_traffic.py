"""Random traffic on the pin-level model, to find holes in docs/V2_SPEC.md
before any RTL is written. Two kinds of run, each from a seed:

legal     The FPGA keeps every rule of section 11, at random clock ratios and
          phases, with the metastability model on. Everything it sends must
          come back, in order and exactly right, and no error flag or counter
          may move.

hostile   The FPGA breaks the rules at random: frames too close, corrupted or
          cut short, writes while busy, transactions abandoned, both masters
          at once, tests started in the middle of traffic, resets. Nothing is
          expected of the results then, but three things must still hold:

            1. A result is always W^T a for the weights and activations the
               chip held when that vector started. Nothing may change either
               underneath a running vector.
            2. No crossing is read while it changes, the write port never sees
               two writes at once or an open activation gate, and the link
               FIFO never hands out an entry twice.
            3. When the abuse stops the chip comes back by itself: it goes
               idle, takes a clean configuration, and then runs legal traffic
               exactly right. No reset is needed.

          Then it is reset and must be indistinguishable, pin for pin, from a
          chip that has just powered up.

    python3 -m model.chip_v2.verify random 200
"""
from __future__ import annotations

import time

import numpy as np

from . import chip as C
from . import trace as T
from .fpga import PS, Bench, act_bytes, link_frame, reference, weight_bytes


def min_period(p: int, requant: bool, silent: bool) -> int:
    """Section 11 rule 2, in CLK cycles between the first payload symbols of two frames."""
    if p == 1:
        return 13 if silent else 16 if requant else 22
    return 67 + p


class Watched(Bench):
    """A bench that checks, on every CLK edge, what only the model can see."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.problems: list[str] = []
        self._run = None            # (activations, weights, P, gate_off) of the vector now computing
        self._was = C.FREE
        self.vectors = 0

    def _clk_rise(self) -> None:
        super()._clk_rise()
        c = self.chip
        if not c.rst_n:
            self._run, self._was = None, C.FREE
            return
        if c.chain == C.COMPUTING and self._was != C.COMPUTING:
            self._run = (list(c.rows), c.wbits.copy(), c.chain_p, bool(c.mode & C.M_GATE_OFF))
        elif self._run is not None and c.chain == C.COMPUTING and not np.array_equal(c.wbits, self._run[1]):
            self.problems.append(f"cycle {c.cyc}: the weights changed under a running vector")
            self._run = None
        elif self._run is not None and self._was == C.COMPUTING and c.chain != C.COMPUTING:
            rows, wbits, p, gate_off = self._run
            self._run = None
            if c.acc_valid:                             # it finished (not cut off by a self-test abort)
                a = np.array([r & ((1 << p) - 1) for r in rows], dtype=np.int64)
                w = np.zeros((C.ROWS, C.NW), dtype=np.int64)
                for j in range(C.NW):
                    col = wbits[:, j * 8:j * 8 + 8]
                    w[:, j] = col[:, :7] @ (1 << np.arange(7)) - (col[:, 7] << 7)
                want = [0] * C.NW if gate_off else [int(v) for v in a @ w]
                self.vectors += 1
                if list(c.acc) != want:
                    self.problems.append(f"cycle {c.cyc}: a result is not W^T a for what the chip held at start "
                                         f"(P = {p}): {list(c.acc)} against {want}")
        self._was = c.chain

    def structural(self, where: str) -> None:
        c = self.chip
        for name in ("wc_collisions", "gate_leaks", "act_overrun", "fifo_stale", "read_during_write"):
            if c.obs[name]:
                self.problems.append(f"{where}: {name} = {c.obs[name]}")
        if c.x.unsafe_reads:
            self.problems.append(f"{where}: {len(c.x.unsafe_reads)} held words read while changing, "
                                 f"first {c.x.unsafe_reads[0]}")


def make_bench(rng, seed: int) -> Watched:
    ratio = float(rng.choice([1.0, 1.0, 1.001, 1.13, 1.5, 2.0]))
    b = Watched(link=int(40 * PS * ratio) // 2 * 2, link_phase=int(rng.integers(0, 40)) * PS, seed=seed,
                meta=2 * PS, lane_delay=tuple(int(v) for v in rng.integers(0, 4, 4)))
    b.spi_period = int(b.T * float(rng.choice([1.0, 1.0, 1.3, 2.0, 3.7]))) // 2 * 2
    b.tck_period = int(b.T * float(rng.choice([4.0, 4.0, 5.5, 9.0]))) // 2 * 2
    return b


def wait_idle(b: Bench, limit: int = 40_000) -> bool:
    """Poll STATUS over SPI, as the FPGA would, until busy and tx_busy are both 0."""
    start = b.chip.cyc
    while b.chip.cyc - start < limit:
        if b.rd(C.A_STATUS) & 0b1001 == 0:
            return True
        b.run(int(b.sim.rng.random() * 40))
    return False


def expected(w, a, st) -> list[int]:
    raw = reference(w, a)
    return [C.requant(r, st["bias"][j], st["shift"]) for j, r in enumerate(raw)] if st["requant"] else raw


def send_frames(b: Bench, rng, st, n: int, tight: bool) -> list[str]:
    """n legal frames at the current settings. Returns what went wrong."""
    p, w = st["p"], st["w"]
    vecs = [rng.integers(0, 1 << p, 32) for _ in range(n)]
    period = min_period(p, st["requant"], False)
    b.rx.frames.clear()
    b.rx.p = p
    for i, a in enumerate(vecs):
        f = link_frame((st["seq"] + i) & 63, a, p)
        gap = period if tight else period + int(rng.choice([0, 0, 1, 7, 40]))
        b.stream.extend(f + [0] * max(0, gap - len(f)))
    budget = (n * (period + 45) + 400) * max(1, b.link.period // b.T + 1)
    for _ in range(budget):
        if len(b.rx.frames) >= n and not b.stream:
            break
        if rng.random() < 0.002:                        # reads never disturb anything
            if b.rd(C.A_ID) != C.ID:
                return ["ID read wrong during traffic"]
        b.run(1)
    out = []
    if len(b.rx.frames) != n:
        out.append(f"{len(b.rx.frames)} of {n} frames came back (P = {p}, requant {st['requant']})")
    for i, (f, a) in enumerate(zip(b.rx.frames, vecs)):
        if not f["ok"] or f["seq"] != (st["seq"] + i) & 63 or f["vals"] != expected(w, a, st) \
                or f["type"] != int(st["requant"]):
            out.append(f"frame {i} of {n} wrong (P = {p}, requant {st['requant']}): {f}")
            break
    st["seq"] += n
    return out


def configure(b: Bench, rng, st) -> None:
    st["p"] = int(rng.integers(1, 9))
    st["requant"] = bool(rng.random() < 0.4)
    st["shift"] = int(rng.integers(0, 16))
    st["bias"] = [int(v) for v in rng.integers(-(1 << 17), 1 << 17, 4)]
    b.wr(C.A_P, st["p"] - 1)
    b.wr(C.A_SHIFT, st["shift"])
    for j in range(4):
        b.wr(C.A_BIAS0 + j, st["bias"][j] & 0x1FFFFF)
    b.wr(C.A_MODE, C.M_LINK_EN | (C.M_REQUANT if st["requant"] else 0))


def load(b: Bench, rng, st, check_rows: int = 2) -> list[str]:
    st["w"] = rng.integers(-128, 128, (32, 4))
    b.load_weights(st["w"])
    if not wait_idle(b):
        return ["never idle after a weight load"]
    out = []
    for r in rng.choice(32, check_rows, replace=False):
        b.wr(C.A_ROW_SEL, int(r))
        want = sum((int(st["w"][r, j]) & 0xFF) << (8 * j) for j in range(4))
        if b.rd(C.A_ROW_DATA) != want:
            out.append(f"row {r} reads back wrong after a weight load")
    return out


def flags_clean(b: Bench) -> list[str]:
    out = []
    counts = [b.rd(x) for x in (C.A_CNT_CRC, C.A_CNT_OVR, C.A_CNT_BAD)]
    if counts != [0, 0, 0]:
        out.append(f"error counters moved: CRC, overrun, bad type = {counts}")
    st = b.rd(C.A_STATUS)
    if st >> 4 & 3:
        out.append(f"sticky flags set: err_busy {st >> 4 & 1}, fifo_ovf {st >> 5 & 1}")
    return out


def run_legal(seed: int, steps: int = 14) -> list[str]:
    rng = np.random.default_rng(seed)
    b = make_bench(rng, seed)
    st = {"seq": 0, "w": None}
    b.reset()
    if rng.random() < 0.3:
        b.wait(lambda: b.chip.selftest_done, what="self-test")
    configure(b, rng, st)
    out = load(b, rng, st)
    b.wait(lambda: b.rd(C.A_STATUS) >> 6 & 1, limit=400, what="link ready")
    for _ in range(steps):
        if out:
            break
        act = rng.choice(["frames", "frames", "frames", "tight", "weights", "config", "spi", "jtag"])
        if act in ("frames", "tight"):
            out += send_frames(b, rng, st, int(rng.integers(1, 14)), act == "tight")
        elif act == "weights":
            if not wait_idle(b):
                out.append("never idle before a weight load")
            out += load(b, rng, st)
        elif act == "config":
            if not wait_idle(b):
                out.append("never idle before a configuration change")
            configure(b, rng, st)
            b.run(4)
        elif act == "spi":                              # one vector with the link out of use
            if not wait_idle(b):
                out.append("never idle before an SPI vector")
            b.wr(C.A_MODE, C.M_ACT_SPI | C.M_TX_SILENCE)
            a = rng.integers(0, 1 << st["p"], 32)
            if b.spi_vector(a, st["p"], 5) != reference(st["w"], a):
                out.append(f"SPI vector wrong at P = {st['p']}")
            b.wr(C.A_MODE, C.M_LINK_EN | (C.M_REQUANT if st["requant"] else 0))
            b.wait(lambda: b.rd(C.A_STATUS) >> 6 & 1, limit=400, what="link ready")
        else:
            b.jtag_reset()
            if b.jtag_read(C.A_ID) != C.ID:
                out.append("JTAG read of ID wrong")
    out += flags_clean(b)
    b.structural("legal run")
    if b.chip.obs["x_reads"]:
        out.append(f"{b.chip.obs['x_reads']} reads of memory that was never written")
    return out + b.problems


# ---------------------------------------------------------------- hostile runs
WRITABLE = [C.A_MODE, C.A_P, C.A_SHIFT, C.A_BIAS0, C.A_BIAS0 + 3, C.A_START, C.A_CLEAR, C.A_BIST_CTRL, C.A_ROW_SEL]


def abuse(b: Bench, rng, st) -> str:
    c = b.chip
    act = rng.choice(["close", "corrupt", "junk", "cut", "spi_write", "spi_write", "weights", "act", "spi_cut",
                      "jtag_write", "jtag_write", "jtag_test", "both", "both", "mode", "idle", "good", "dead"])
    p = c.p_reg
    if act == "close":
        f = link_frame(int(rng.integers(0, 64)), rng.integers(0, 1 << p, 32), p)
        for _ in range(int(rng.integers(2, 8))):
            b.stream.extend(f + [0] * int(rng.integers(0, 30)))
    elif act == "corrupt":
        f = link_frame(int(rng.integers(0, 64)), rng.integers(0, 1 << p, 32), p, typ=int(rng.choice([0, 0, 0, 1, 2, 3])))
        for _ in range(int(rng.integers(1, 4))):
            f[int(rng.integers(0, len(f)))] ^= 1 << int(rng.integers(0, 4))
        b.stream.extend(f + [0] * int(rng.integers(0, 100)))
    elif act == "junk":
        b.stream.extend(int(v) for v in rng.integers(0, 16, int(rng.integers(1, 120))))
    elif act == "cut":
        f = link_frame(1, rng.integers(0, 1 << p, 32), p)
        b.stream.extend(f[:int(rng.integers(1, len(f)))] + [0] * int(rng.integers(0, 90)))
    elif act == "dead":                                 # the link clock stops, perhaps in the middle of a frame
        if b.link.running and rng.random() < 0.3:
            f = link_frame(2, rng.integers(0, 1 << p, 32), p)
            b.stream.extend(f)
            b.run(int(rng.integers(1, len(f) + 4)) * b.link.period // b.T)
            b.link.stop()
    elif act == "good":
        f = link_frame(int(rng.integers(0, 64)), rng.integers(0, 1 << p, 32), p)
        b.stream.extend(f + [0] * 80)
    elif act == "spi_write":
        addr = int(rng.choice(WRITABLE))
        b.wr(addr, int(rng.integers(0, 1 << 8 * C.REG_BYTES[addr])), block=bool(rng.random() < 0.5))
    elif act == "mode":                                 # the link switched off and on again at once
        b.wr(C.A_MODE, int(rng.integers(0, 32)) & ~C.M_LINK_EN, block=False)
        b.wr(C.A_MODE, int(rng.integers(0, 32)) | C.M_LINK_EN, block=bool(rng.random() < 0.5))
    elif act == "weights":
        n = int(rng.choice([128, 128, 4, 9, 60, 127]))
        b.spi([0x80 | C.A_WEIGHTS] + weight_bytes(rng.integers(-128, 128, (32, 4)))[:n],
              block=bool(rng.random() < 0.5))
    elif act == "act":
        b.spi([0x80 | C.A_ACT] + act_bytes(rng.integers(0, 256, 32), 8)[:int(rng.integers(1, 33))],
              block=bool(rng.random() < 0.5))
    elif act == "spi_cut":
        addr = int(rng.choice(WRITABLE + [C.A_WEIGHTS, C.A_ACT]))
        b.spi([0x80 | addr] + [int(v) for v in rng.integers(0, 256, 6)], cut_bits=int(rng.integers(1, 56)), block=False)
    elif act == "jtag_write":
        addr = int(rng.choice(WRITABLE + [C.A_WEIGHTS, C.A_ACT]))
        if rng.random() < 0.2:
            b.jtag_reset()
        b.jtag_write(addr, int(rng.integers(0, 1 << 32)))
    elif act == "jtag_test":
        ir = int(rng.choice([C.IR_MBIST, C.IR_CBIST]))
        b.jtag_ir(ir)
        b.jtag_dr(int(rng.integers(0, 2)), C.DR_LEN[ir])
    elif act == "both":                                 # the two masters at the same moment
        addr = int(rng.choice(WRITABLE + [C.A_WEIGHTS, C.A_ACT]))
        if addr == C.A_WEIGHTS:
            tx = [0x80 | addr] + weight_bytes(rng.integers(-128, 128, (32, 4)))
        elif addr == C.A_ACT:
            tx = [0x80 | addr] + act_bytes(rng.integers(0, 256, 32), 8)
        else:
            tx = [0x80 | addr] + [int(v) for v in rng.integers(0, 256, C.REG_BYTES[addr])]
        b.spi(tx, offset=int(rng.integers(0, 16)) * b.T // 8, block=False)
        for _ in range(int(rng.integers(1, 5))):
            b.jtag_write(int(rng.choice(WRITABLE + [C.A_WEIGHTS, C.A_ACT])), int(rng.integers(0, 1 << 32)))
    b.run(int(rng.choice([0, 1, 5, 30, 200])))
    return str(act)


def recover(b: Watched, rng, st) -> list[str]:
    """The abuse has stopped. The chip must come back without a reset."""
    dead = not b.link.running
    if not dead:
        b.wait(lambda: not b.stream, limit=60_000, what="the stream to drain")
    b.stream.clear()
    b.run(2 * 16 * b.spi_period // b.T + 100)           # any abandoned transaction is over; 72 idle symbols pass
    b.wr(C.A_CLEAR, 4)                                  # abandon a vector the link never finished
    if not wait_idle(b, 40_000):                        # two self-tests at their timeout is 16,384 cycles
        c = b.chip
        return [f"never idle after the abuse stopped: chain {c.chain}, acc_valid {c.acc_valid}, "
                f"self-test {'running' if c.bist is not None else 'off'}, burst {c.burst}, wc {c.wc}, "
                f"act_cnt {c.act_cnt}, tx_cnt {c.tx_cnt}"]
    b.wr(C.A_MODE, 0)                                   # link off first, while nothing can arrive
    if dead:                                            # then the link clock comes back
        b.link.running = True
        b.sim.at(b.sim.t + int(rng.integers(1, 40)) * PS, b.link._rise)
    b.wait(lambda: b.rd(C.A_STATUS) >> 6 & 1 == 0, limit=2000, what="the link to report that it is off")
    b.wr(C.A_CLEAR, 3)
    configure(b, rng, st)
    b.wait(lambda: b.rd(C.A_STATUS) >> 6 & 1, limit=400, what="link ready")
    b.run(80 * b.link.period // b.T + 10)
    b.rx.q = [[] for _ in range(4)]                     # the FPGA's receiver starts clean too
    out = []
    if b.rd(C.A_P) != st["p"] - 1 or b.rd(C.A_SHIFT) != st["shift"]:
        out.append("a clean configuration did not take after the abuse")
    if not wait_idle(b):
        out.append("not idle after reconfiguring")
    out += load(b, rng, st, check_rows=4)
    st["seq"] = 0
    out += send_frames(b, rng, st, 6, False)
    out += flags_clean(b)
    return [f"after the abuse: {o}" for o in out]


def run_hostile(seed: int, steps: int = 40) -> list[str]:
    rng = np.random.default_rng(seed)
    b = make_bench(rng, seed)
    st = {"seq": 0, "w": None}
    b.reset()
    configure(b, rng, st)
    out = load(b, rng, st)
    did = []
    for _ in range(steps):
        did.append(abuse(b, rng, st))
        if b.problems:
            break
    b.structural("hostile run")
    out += b.problems
    if not out:
        out += recover(b, rng, st)
        b.structural("after the abuse")
        out += b.problems
    if not out:                                         # reset must make it a fresh chip again
        ref = Bench()
        tr = T.record(ref)
        ref.start(rng.integers(-128, 128, (32, 4)), p=8)
        ref.stream.extend(link_frame(7, rng.integers(0, 256, 32), 8))
        ref.wait(lambda: ref.rx.frames, what="the reference frame")
        ref.jtag_reset()
        ref.jtag_read(C.A_STATUS)
        b.wait(lambda: b.sim.t > b._spi_free and b.chip.cs_n, what="chip select high")   # section 11: no reset mid-transaction
        m = replay_on(b, tr)
        if m:
            out.append(f"after a reset the chip is not a fresh chip: {m}")
    return [f"{o}   [actions: {' '.join(did[-12:])}]" for o in out] if out else []


def replay_on(b: Bench, tr: T.Trace):
    """Replay a trace recorded on a fresh chip on this used one, starting with its reset."""
    chip, sim = b.chip, b.sim
    b.clk.stop()
    b.link.stop()
    sim.run_for(4 * b.T)
    t0 = sim.t + 8 * b.T
    chip.link_d, chip.mosi, chip.tms, chip.tdi = 0, 0, 1, 0
    chip.sim.meta_window = 0
    for i, (t, kind, val, exp) in enumerate(tr.rows()):
        if t0 + t != sim.t:
            sim.advance(t0 + t)
        if kind == T.CLK_R:
            got = chip.link_tx | chip.status << 4
            if got != exp:
                return f"event {i}: LINK_TX and STATUS are {got:#x}, a fresh chip has {exp:#x}"
            chip.clk_rise()
        elif kind == T.LINK_R:
            chip.link_rise()
        elif kind == T.LINK_D:
            chip.link_d = val
        elif kind == T.SCLK_R:
            if chip.miso != exp:
                return f"event {i}: SPI_MISO is {chip.miso}, a fresh chip has {exp}"
            chip.spi_rise()
        elif kind == T.SCLK_F:
            chip.spi_fall()
        elif kind == T.MOSI:
            chip.mosi = val
        elif kind == T.CS:
            chip.spi_cs(val)
        elif kind == T.TCK_R:
            if chip.tdo != exp:
                return f"event {i}: TDO is {chip.tdo}, a fresh chip has {exp}"
            chip.tck_rise()
        elif kind == T.TCK_F:
            chip.tck_fall()
        elif kind == T.TMS:
            chip.tms = val
        elif kind == T.TDI:
            chip.tdi = val
        elif kind == T.RST:
            chip.set_rst_n(val)
    return None


def main(argv: list[str]) -> int:
    n = int(argv[0]) if argv else 50
    first = int(argv[1]) if len(argv) > 1 else 0
    kinds = argv[2].split(",") if len(argv) > 2 else ["legal", "hostile"]
    t0 = time.time()
    bad = 0
    for kind in kinds:
        fn = {"legal": run_legal, "hostile": run_hostile}[kind]
        failed = []
        for seed in range(first, first + n):
            try:
                out = fn(seed)
            except Exception as e:
                out = [f"{type(e).__name__}: {e}"]
            if out:
                failed.append(seed)
                print(f"  {kind} seed {seed}: {out[0]}" + (f"  (+{len(out) - 1} more)" if len(out) > 1 else ""), flush=True)
        bad += len(failed)
        print(f"{kind}: {n - len(failed)} of {n} seeds clean" + (f"; failing seeds {failed[:20]}" if failed else ""), flush=True)
    print(f"{time.time() - t0:.0f} s")
    return 1 if bad else 0
