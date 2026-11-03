"""Scenarios that check docs/V2_SPEC.md on the pin-level model and measure its
cycle counts. Run from the repository root:

    python3 -m model.chip_v2            every scenario
    python3 -m model.chip_v2 link cdc   only the named ones

Exit status is 0 only if every check passed.
"""
from __future__ import annotations

import sys
import time

import numpy as np

from . import chip as C
from .crc import CRC_INIT, crc8, crc8_symbol
from .fpga import PS, Bench, act_bytes, link_frame, reference, weight_bytes

RESULTS: list[tuple[str, bool, str]] = []
MEASURED: dict[str, object] = {}


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f": {detail}" if detail else ""), flush=True)
    return bool(ok)


def rand_w(rng):
    return rng.integers(-128, 128, (32, 4))


def send(b: Bench, frames: list[list[int]], spacing: int) -> None:
    """Queue frames so their first symbols are `spacing` link cycles apart."""
    for f in frames:
        b.stream.extend(f + [0] * max(0, spacing - len(f)))


def run_frames(b: Bench, w, vectors, p: int, spacing: int, extra: int = 400):
    """Send one frame per vector. Returns (return frames, overruns)."""
    b.rx.frames.clear()
    send(b, [link_frame(i & 63, a, p) for i, a in enumerate(vectors)], spacing)
    b.wait(lambda: not b.stream, what="the stream to go out")
    b.run(extra)
    return list(b.rx.frames), b.chip.cnt_ovr


# ------------------------------------------------------------------ scenarios
def s_selftest() -> None:
    print("self-test and the STATUS pin")
    b = Bench()
    b.trace_status = True
    b.reset()
    n = b.wait(lambda: b.chip.selftest_done, what="self-test")
    MEASURED["self-test, cycles from reset"] = n
    check("memory test passes on a good array", b.chip.mb_state == C.B_PASS)
    check("compute test signature equals the one from plain arithmetic",
          b.chip.cb_state == C.B_PASS and b.chip.cb_sig == C.cbist_signature(), hex(b.chip.cb_sig))
    check("STATUS is low for the whole self-test", not any(b.status_trace[:n]))
    b.run(70_000)
    tail = b.status_trace[n + 10:]
    edges = sum(1 for i in range(1, len(tail)) if tail[i] != tail[i - 1])
    check("STATUS toggles slowly after a pass", edges in (1, 2, 3), f"{edges} edges in 70,000 cycles")

    # The compute test stores one fixed weight pattern, so it can only see a stuck cell
    # whose stuck value differs from what the pattern stores there: (20, 31) holds 1, (9, 5) holds 0.
    for label, kind, cell in (("stuck at 0", "stuck", (20, 31, 0)), ("stuck at 1", "stuck", (9, 5, 1)),
                              ("coupled to another cell", "coupled", (3, 4, 17, 6))):
        b = Bench()
        if kind == "stuck":
            b.chip.stuck[(cell[0], cell[1])] = cell[2]
        else:
            b.chip.coupled[(cell[0], cell[1])] = (cell[2], cell[3])
        b.reset()
        b.wait(lambda: b.chip.selftest_done, what="self-test")
        row = cell[0] if kind == "stuck" else cell[2]
        check(f"memory test fails on a cell {label} and names the row",
              b.chip.mb_state == C.B_FAIL and b.chip.mb_row == row, f"row {b.chip.mb_row}")
        if kind == "stuck":
            check(f"compute test fails too with a cell {label}, where its pattern stores the other value",
                  b.chip.cb_state == C.B_FAIL)
        b.run(5)
        check(f"STATUS is high after a failure ({label})", b.chip.status == 1)

    b = Bench()
    b.reset()
    b.run(500)
    b.spi([0x80 | C.A_SHIFT], block=False)              # only the command byte so far
    gone = b.wait(lambda: b.chip.bist is None, what="the abort")
    b.run(40)
    b.wr(C.A_SHIFT, 9)
    MEASURED["self-test abort, CLK cycles from chip select falling (command byte = 8 SCLK)"] = gone
    check("the command byte of a write aborts the self-test", b.chip.mb_state == C.B_ABORT and gone <= 14,
          f"{gone} cycles after chip select fell")
    check("and the write is carried out", b.chip.shift == 9 and b.rd(C.A_BIST_STAT) == 0b1111)
    b.wr(C.A_BIST_CTRL, 1)
    n = b.wait(lambda: b.chip.bist is None, what="memory test")
    MEASURED["memory test alone, cycles"] = n
    b.wr(C.A_BIST_CTRL, 2)
    MEASURED["compute test alone, cycles"] = b.wait(lambda: b.chip.bist is None, what="compute test")
    check("tests rerun on command and pass", b.rd(C.A_BIST_STAT) == 0b0101)


def s_spi() -> None:
    print("SPI and the register file, at several clock rates and phases")
    rng = np.random.default_rng(2)
    bad = unsafe = n = 0
    for ratio in (1.0, 1.25, 3.7):
        for k in range(8):
            b = Bench(seed=k, meta=2 * PS)
            b.spi_period = int(b.T * ratio) // 2 * 2
            b.reset()
            b.run(3)
            vals = {C.A_MODE: int(rng.integers(0, 32)) & ~1, C.A_P: int(rng.integers(0, 8)),
                    C.A_SHIFT: int(rng.integers(0, 16)), C.A_ROW_SEL: int(rng.integers(0, 32))}
            vals.update({C.A_BIAS0 + j: int(rng.integers(0, 1 << 21)) for j in range(4)})
            for addr, v in vals.items():
                b.wr(addr, v, offset=k * b.T // 8)
            for addr, v in vals.items():
                n += 1
                bad += b.rd(addr, offset=(7 - k) * b.T // 8) != v
            bad += b.rd(C.A_ID) != C.ID
            unsafe += len(b.chip.x.unsafe_reads)
    check("every register reads back what was written", bad == 0, f"{n} registers, 3 SCLK rates, 8 phases")
    check("no held word was read while it was changing", unsafe == 0)

    b = Bench()
    b.reset()
    b.wr(C.A_SHIFT, 5)
    b.spi([0x80 | C.A_SHIFT, 0x0F], cut_bits=12)        # chip select raised mid-byte
    check("a transaction cut short changes nothing", b.rd(C.A_SHIFT) == 5)
    b.wr(C.A_SHIFT, 3)
    check("and the next transaction is aligned", b.rd(C.A_SHIFT) == 3)

    w = rand_w(rng)
    for ratio in (1.0, 2.5):
        b = Bench(meta=2 * PS)
        b.spi_period = int(b.T * ratio) // 2 * 2
        b.reset()
        b.wr(C.A_P, 7)
        t0 = b.chip.cyc
        b.spi([0x80 | C.A_WEIGHTS] + weight_bytes(w))
        b.wait(lambda: not b.chip._busy(), what="the weight load")
        cycles = b.chip.cyc - t0
        want = [sum((int(w[r, j]) & 0xFF) << (8 * j) for j in range(4)) for r in range(32)]
        ok = b.chip.w_mem == want and b.chip.obs["wc_collisions"] == 0
        check(f"a weight set lands in the right cells (SCLK = CLK x {ratio})", ok, f"{cycles} CLK cycles")
        if ratio == 1.0:
            MEASURED["weight set over SPI at SCLK = CLK, cycles"] = cycles
        back = []
        for r in (0, 13, 31):
            b.wr(C.A_ROW_SEL, r)
            back.append(b.rd(C.A_ROW_DATA) == want[r])
        check(f"rows read back through the compute port (SCLK = CLK x {ratio})", all(back))


def s_link() -> None:
    print("vectors over the link, every precision")
    rng = np.random.default_rng(3)
    for p in range(1, 9):
        w = rand_w(rng)
        vecs = [rng.integers(0, 1 << p, 32) for _ in range(12)]
        vecs += [np.full(32, (1 << p) - 1), np.zeros(32, dtype=int)]
        b = Bench(lane_delay=(0, 2, 1, 3))
        b.start(w, p=p)
        frames, ovr = run_frames(b, w, vecs, p, 110)
        good = (len(frames) == len(vecs) and ovr == 0 and all(f["ok"] for f in frames)
                and all(f["vals"] == reference(w, a) and f["seq"] == i for i, (f, a) in enumerate(zip(frames, vecs))))
        check(f"P = {p}: results, sequence numbers and CRC all right, lanes skewed by 0 to 3 cycles",
              good and b.chip.obs["x_reads"] == 0 and b.chip.obs["gate_leaks"] == 0, f"{len(frames)} frames")
    for wv in (-128, 127):
        w = np.full((32, 4), wv)
        b = Bench()
        b.start(w, p=8)
        frames, _ = run_frames(b, w, [np.full(32, 255)], 8, 110)
        check(f"extreme: all weights {wv}, all activations 255", frames and frames[0]["vals"] == [wv * 255 * 32] * 4,
              str(frames[0]["vals"][0]) if frames else "no frame")


def min_spacing(p: int, mode: int, lo: int, hi: int, shift: int = 4) -> int:
    rng = np.random.default_rng(4)
    w = rand_w(rng)
    # Many frames on purpose. The accumulators hold one finished result, so a burst can
    # run a cycle faster than the sustainable rate for a while before a frame is dropped
    # (about 29 frames at P = 1). 96 frames is past that.
    vecs = [rng.integers(0, 1 << p, 32) for _ in range(96)]
    for s in range(lo, hi):
        b = Bench()
        b.start(w, p=p, mode=mode, shift=shift)
        frames, ovr = run_frames(b, w, vecs, p, s)
        if mode & C.M_TX_SILENCE:
            done = ovr == 0 and b.chip.cnt_crc == 0
        else:
            done = ovr == 0 and len(frames) == len(vecs) and all(f["ok"] for f in frames)
        if done:
            return s
    return -1


def s_period() -> None:
    print("the shortest frame spacing that drops nothing")
    for label, p, mode, want, lo in (("P = 1, raw", 1, 1, 22, 13), ("P = 1, requantized", 1, 17, 16, 13),
                                     ("P = 8, raw", 8, 1, 75, 69), ("P = 8, requantized", 8, 17, 75, 69),
                                     ("P = 4, raw", 4, 1, 71, 69), ("P = 1, return lanes silent", 1, 9, 13, 13),
                                     ("P = 8, return lanes silent", 8, 9, 75, 69)):
        got = min_spacing(p, mode, lo, lo + 30)
        MEASURED[f"period, {label}"] = got
        check(f"{label}: {got} cycles per vector", got == want, f"the spec says {want}")
    # one cycle too fast must lose frames cleanly, not corrupt them
    rng = np.random.default_rng(5)
    w = rand_w(rng)
    vecs = [rng.integers(0, 256, 32) for _ in range(20)]
    b = Bench()
    b.start(w, p=8)
    frames, ovr = run_frames(b, w, vecs, 8, 74)
    right = all(f["ok"] and f["vals"] == reference(w, vecs[f["seq"]]) for f in frames)
    check("one cycle too fast: frames are dropped and counted, every result that comes back is right",
          ovr > 0 and right and len(frames) + ovr == len(vecs), f"{ovr} dropped, {len(frames)} returned")


def s_cdc() -> None:
    print("clock relationships and metastability")
    rng = np.random.default_rng(6)
    w = rand_w(rng)
    vecs = [rng.integers(0, 256, 32) for _ in range(10)]
    worst = unsafe = 0
    ok = True
    for ratio in (1.0, 1.003, 1.5):
        for k in range(8):
            b = Bench(link=int(40 * PS * ratio) // 2 * 2, link_phase=k * 5 * PS, seed=k, meta=2 * PS,
                      lane_delay=(k % 3, 0, 2, 1))
            b.start(w, p=8)
            frames, ovr = run_frames(b, w, vecs, 8, 80)
            ok &= (len(frames) == len(vecs) and ovr == 0
                   and all(f["ok"] and f["vals"] == reference(w, a) for f, a in zip(frames, vecs)))
            ok &= not b.chip.fifo_ovf
            worst = max(worst, b.chip.obs["fifo_max"])
            unsafe += len(b.chip.x.unsafe_reads)
    MEASURED["link FIFO, most symbols ever waiting"] = worst
    check("every result right at 3 link clock rates and 8 phases, with metastability modelled", ok)
    check("the FIFO never came close to full", worst <= 4, f"at most {worst} of {C.FIFO_DEPTH} entries")
    check("no held word was read while it was changing", unsafe == 0)

    b = Bench(link=int(40 * PS * 0.9) // 2 * 2)             # the FPGA breaks rule 1: link faster than core
    b.start(w, p=8)
    b.run(400)
    check("a link clock faster than the core clock is caught by the overflow flag", b.rd(C.A_STATUS) >> 5 & 1 == 1)

    lat = []
    for k in range(40):
        b = Bench(link_phase=k * PS)
        b.start(w, p=8)
        b.stream.extend([C.SYNC_IN])
        t_edge = None
        for _ in range(4000):
            if b.chip.link_d == C.SYNC_IN and t_edge is None:
                t_edge = b.sim.t
            if b.chip.rx == C.HDR1:
                break
            b.sim.run_for(PS)
        lat.append((b.sim.t - t_edge) / b.T)
    MEASURED["link crossing latency, CLK periods (from the pin changing)"] = f"{min(lat):.2f} to {max(lat):.2f}"
    check("link crossing latency is bounded", max(lat) < 4.0, MEASURED["link crossing latency, CLK periods (from the pin changing)"])


def s_errors() -> None:
    print("link errors")
    rng = np.random.default_rng(7)
    w = rand_w(rng)
    for p in (1, 8):
        a = rng.integers(0, 1 << p, 32)
        good = link_frame(9, a, p)
        b = Bench()
        b.start(w, p=p)
        wrong = lost = 0
        for i in range(len(good) * 4):
            f = list(good)
            f[i // 4] ^= 1 << (i % 4)
            b.rx.frames.clear()
            b.stream.extend(f + [0] * 80)               # 72 idle symbols let the receiver recover
            b.wait(lambda: not b.stream, what="the stream")
            b.run(60)
            if b.rx.frames:
                wrong += any(fr["vals"] != reference(w, a) or fr["seq"] != 9 for fr in b.rx.frames)
            else:
                lost += 1
        check(f"P = {p}: every single flipped bit is caught", wrong == 0 and lost == len(good) * 4,
              f"{len(good) * 4} flips, {lost} frames rejected, {wrong} wrong results")
        b.rx.frames.clear()
        b.stream.extend(good)
        b.wait(lambda: b.rx.frames, what="a good frame after the errors")
        check(f"P = {p}: a good frame works after the errors", b.rx.frames[0]["vals"] == reference(w, a))

    a = rng.integers(0, 256, 32)
    good = link_frame(1, a, 8)
    bits = len(good) * 4
    missed = 0
    trials = 4000
    for _ in range(trials):
        i, j = rng.choice(np.arange(4, bits), 2, replace=False)
        f = list(good)
        f[i // 4] ^= 1 << (i % 4)
        f[j // 4] ^= 1 << (j % 4)
        hdr_payload, crc = f[1:-2], (f[-2] << 4) | f[-1]
        from .crc import crc8
        missed += crc8(hdr_payload) == crc
    MEASURED["double bit errors that pass the CRC"] = f"{missed} of {trials}"
    check("double flipped bits are almost always caught", missed <= trials // 200, f"{missed} of {trials} random pairs pass")

    b = Bench()
    b.start(w, p=8)
    b.stream.extend(link_frame(0, a, 8, typ=2) + [0] * 80 + good)
    b.wait(lambda: b.rx.frames, what="a frame after a bad type")
    check("a frame of an unknown type is counted and skipped", b.rd(C.A_CNT_BAD) == 1 and len(b.rx.frames) == 1)

    b = Bench()
    b.start(w, p=8)
    b.stream.extend([0] * 3 + [C.SYNC_IN] + [0] * 200)      # a stray sync on a quiet link
    b.run(400)
    check("a stray sync followed by silence does not start a compute",
          not b.rx.frames and b.chip.cnt_crc == 1 and b.chip.chain == C.FREE)


def s_requant() -> None:
    print("requantize")
    rng = np.random.default_rng(8)
    w = rand_w(rng)
    ok = True
    n = 0
    for shift in (0, 3, 6, 9, 15):
        bias = [int(v) for v in rng.integers(-60000, 60000, 4)]
        vecs = [rng.integers(0, 256, 32) for _ in range(6)] + [np.zeros(32, dtype=int), np.full(32, 255)]
        b = Bench()
        b.start(w, p=8, mode=17, shift=shift, bias=bias)
        frames, _ = run_frames(b, w, vecs, 8, 90)
        for f, a in zip(frames, vecs):
            want = [C.requant(r, bias[j], shift) for j, r in enumerate(reference(w, a))]
            ok &= f["ok"] and f["type"] == 1 and f["vals"] == want
            n += 1
        ok &= len(frames) == len(vecs)
        ok &= b.results() == reference(w, vecs[-1])         # the registers still hold the raw result
    check("requantized results match bias, ReLU, shift, limit", ok, f"{n} frames, shifts 0 to 15")
    edge = [(0, 0, 0, 0), (255, 0, 0, 255), (256, 0, 0, 255), (-1, 0, 0, 0), (1023, 0, 2, 255), (1020, 0, 2, 255),
            (1019, 0, 2, 254), (-(1 << 20), (1 << 20) - 1, 0, 0), ((1 << 20) - 1, (1 << 20) - 1, 15, 63)]
    check("boundary values", all(C.requant(r, bb, s) == want for r, bb, s, want in edge))


def s_rules() -> None:
    print("the busy rule, and P travelling with the vector")
    rng = np.random.default_rng(9)
    w, w2 = rand_w(rng), rand_w(rng)
    a8, a1 = rng.integers(0, 256, 32), rng.integers(0, 2, 32)
    b = Bench()
    b.start(w, p=8)
    b.stream.extend(link_frame(1, a8, 8))
    b.wait(lambda: b.chip.tx_cnt > 0, what="the drain to begin")
    b.wr(C.A_P, 0)                                          # P = 1, written while the result drains
    check("a write while the result drains is accepted", b.chip.p_reg == 1 and not b.chip.err_busy)
    b.wait(lambda: b.rx.frames, what="the first result")
    f = b.rx.frames[0]
    check("the draining result keeps its 21-bit width", f["ok"] and f["vals"] == reference(w, a8))
    b.rx.p = 1
    b.rx.frames.clear()
    b.stream.extend(link_frame(2, a1, 1))
    b.wait(lambda: b.rx.frames, what="the second result")
    check("the next vector runs at the new precision", b.rx.frames[0]["vals"] == reference(w, a1))

    b = Bench()
    b.start(w, p=8)
    b.stream.extend(link_frame(1, a8, 8))
    b.wait(lambda: b.chip.chain == C.LOADING, what="a frame to start loading")
    b.spi([0x80 | C.A_WEIGHTS] + weight_bytes(w2))
    b.wait(lambda: b.rx.frames, what="the result")
    want = [sum((int(w[r, j]) & 0xFF) << (8 * j) for j in range(4)) for r in range(32)]
    check("a weight write while a vector is loading is ignored and flagged",
          b.chip.w_mem == want and b.rd(C.A_STATUS) >> 4 & 1 == 1 and b.rx.frames[0]["vals"] == reference(w, a8))

    b = Bench()
    b.start(w, p=8)
    b.spi([0x80 | C.A_WEIGHTS] + weight_bytes(w2), block=False)
    b.run(300)                                              # the burst is under way
    b.stream.extend(link_frame(1, a8, 8))
    b.wait(lambda: not b.stream, what="the frame")
    b.wait(lambda: not b.chip._busy(), what="the burst to end")
    b.run(200)
    check("a frame that arrives during a weight burst is dropped, not computed on half-written weights",
          not b.rx.frames and b.rd(C.A_CNT_OVR) == 1 and b.chip.obs["gate_leaks"] == 0)
    b.stream.extend(link_frame(2, a8, 8))
    b.wait(lambda: b.rx.frames, what="a frame after the burst")
    check("and the next frame uses the new weights", b.rx.frames[0]["vals"] == reference(w2, a8))


def s_nolink() -> None:
    print("the chip with the link unplugged: SPI only, then JTAG only")
    rng = np.random.default_rng(10)
    w = rand_w(rng)
    ok = True
    for p in (8, 1, 5):
        b = Bench(meta=2 * PS)
        b.start(w, p=p, mode=C.M_ACT_SPI | C.M_TX_SILENCE)
        for i in range(4):
            a = rng.integers(0, 1 << p, 32)
            ok &= b.spi_vector(a, p, i) == reference(w, a)
        ok &= b.chip.obs["act_overrun"] == 0 and b.chip.link_tx == 0
    check("vectors loaded, run and read back over SPI at P = 8, 1 and 5", ok)

    b = Bench()
    b.reset()
    b.clk.stop()                                            # the core clock is dead
    b.jtag_reset()
    b.jtag_ir(C.IR_IDCODE)
    check("IDCODE answers with the core clock stopped", b.jtag_dr(0, 32) == C.ID | 1)
    b.jtag_ir(C.IR_BYPASS)
    check("BYPASS is one bit long", b.jtag_dr(0b1011, 5) == 0b10110 & 0x1F)

    b = Bench(meta=2 * PS)
    b.reset()
    b.jtag_reset()
    check("DEBUG reads the identity register", b.jtag_read(C.A_ID) == C.ID)
    b.jtag_write(C.A_P, 7)
    b.jtag_write(C.A_MODE, C.M_ACT_SPI | C.M_TX_SILENCE)
    b.jtag_write(C.A_ROW_SEL, 0)
    for r in range(32):
        b.jtag_write(C.A_WEIGHTS, sum((int(w[r, j]) & 0xFF) << (8 * j) for j in range(4)))
    a = rng.integers(0, 256, 32)
    by = act_bytes(a, 8)
    for i in range(0, 32, 4):
        b.jtag_write(C.A_ACT, (by[i] << 24) | (by[i + 1] << 16) | (by[i + 2] << 8) | by[i + 3])
    b.jtag_write(C.A_START, 3)
    b.run(40)
    got = [C.wrap(b.jtag_read(C.A_RESULT0 + j), 24) for j in range(4)]
    check("a whole vector over JTAG alone: weights, activations, start, results", got == reference(w, a))
    check("no held word was read while it was changing", not b.chip.x.unsafe_reads)

    b.jtag_ir(C.IR_MBIST)
    b.jtag_dr(1, 8)                                         # start
    b.run(3000)
    b.jtag_dr(0, 8)                                         # ask for the state now
    state = b.jtag_dr(0, 8)                                 # collect what the previous scan asked for
    check("the MBIST instruction runs the memory test and reports a pass", state & 3 == C.B_PASS and state >> 2 & 1)
    b.jtag_ir(C.IR_CBIST)
    b.jtag_dr(1, 35)
    b.run(3000)
    b.jtag_dr(0, 35)
    state = b.jtag_dr(0, 35)
    check("the CBIST instruction runs the compute test and returns the signature",
          state & 3 == C.B_PASS and (state >> 2) & 0xFFFFFFFF == C.cbist_signature())
    b.jtag([(1, 0)] * 5)
    check("five TCK cycles with TMS high reset the TAP", b.chip.tap == C.TLR and b.chip.ir == C.IR_IDCODE)


def s_workload() -> None:
    print("a real workload: weight sets rewritten between batches, as attention needs")
    rng = np.random.default_rng(11)
    b = Bench()
    b.start(None, p=8)
    ok = True
    t0 = b.chip.cyc
    sets, per = 6, 64
    for s in range(sets):
        w = rand_w(rng)
        b.wait(lambda: not b.chip._busy(), what="idle before a weight write")
        b.load_weights(w)
        vecs = [rng.integers(0, 256, 32) for _ in range(per)]
        b.rx.frames.clear()
        send(b, [link_frame(i, a, 8) for i, a in enumerate(vecs)], 75)
        b.wait(lambda: len(b.rx.frames) == per, what="all the results of a weight set")
        frames = list(b.rx.frames)
        ok &= b.chip.cnt_ovr == 0 and all(f["ok"] and f["vals"] == reference(w, a) for f, a in zip(frames, vecs))
    cycles = b.chip.cyc - t0
    est = sets * (1024 + per * 75)
    MEASURED["6 weight sets x 64 vectors, cycles"] = f"{cycles} (estimate {est})"
    check("every result right across six weight sets of 64 vectors each", ok, f"{cycles} cycles, estimate {est}")
    check("the measured total is within 5% of the estimate", abs(cycles - est) / est < 0.05,
          f"{100 * (cycles - est) / est:+.1f}%")


def s_image() -> None:
    print("one photograph through each demo network, every multiply through the pins")
    from pathlib import Path

    from ..ml_model import QNet, datasets, frontend
    from .fpga import PinFpga
    for label, path, est in (("convolution network", "model/build/attn2/base.npz", 30899 * 75 + 116 * 1024),
                             ("attention network", "model/build/attn2/back_3.npz", 35907 * 75 + (131 + 76) * 1024)):
        if not Path(path).exists():
            print(f"  skipped: {path} is not there (trained networks are not in the repository)")
            continue
        net = QNet.load(path)
        ds = datasets.load(net.meta["dataset"], net.meta["size"])
        _, te = ds.split(net.meta["split_seed"], net.meta["test_size"])
        feats = frontend.build(net.meta["frontend"], **net.meta["frontend_params"])(ds.images[te[:1]])
        want = net.scores(feats)
        b = Bench()
        b.start(None, p=8)
        fp = PinFpga(b)
        t0, c0 = time.time(), b.chip.cyc
        got = net.scores(feats, matvec=fp.matvec, batch=1)
        cycles = b.chip.cyc - c0
        MEASURED[f"one image, {label}, cycles"] = f"{cycles:,} (estimate {est:,}, {100 * (cycles - est) / est:+.1f}%)"
        check(f"{label}: scores through the pins equal the integer network exactly",
              np.array_equal(got, want), f"{fp.passes:,} passes, {fp.sets} weight sets, {cycles:,} cycles, "
              f"{time.time() - t0:.0f} s, answer {net.meta['classes'][int(got.argmax())]}")
        check(f"{label}: nothing dropped, no crossing violation",
              b.chip.cnt_ovr == 0 and b.chip.cnt_crc == 0 and not b.chip.x.unsafe_reads
              and b.chip.obs["gate_leaks"] == 0 and b.chip.obs["x_reads"] == 0 and not b.chip.fifo_ovf)
        check(f"{label}: measured cycles within 3% of the estimate", abs(cycles - est) / est < 0.03)



def s_kws() -> None:
    print("chip test vectors of a real spoken word through the pins (model/chip_v2/vectors.py)")
    from . import vectors as V
    from pathlib import Path
    v = V.load(str(Path(__file__).parent / "vectors" / "kws_word418_sample.npz"))
    w, a = v["weights"].astype(np.int64), v["vectors"].astype(np.int64)
    exact = all(np.array_equal(a[v["set_of"] == s] @ w[s], v["expected"][v["set_of"] == s]) for s in range(len(w)))
    check("the recorded results are W^T a for the recorded weights and vectors", exact,
          f"{len(w)} sets from {len(set(v['product']))} kinds of product, word {v['meta']['clip']}")
    b = Bench()
    b.start(None, p=8)
    c0 = b.chip.cyc
    r = V.run(b, v)
    MEASURED["keyword sample: 32 weight sets through the pins, cycles"] = b.chip.cyc - c0
    check("a sample of a real spoken word (every kind of product): every result through the pins equals the recorded "
          "one", r["wrong"] == 0 and r["vectors"] == len(a) and r["sets"] == len(w),
          f"{r['sets']} sets, {r['vectors']:,} vectors, first difference {r['first_wrong']}")
    check("the keyword sample: nothing dropped, no crossing violation, no read of unwritten memory",
          b.chip.cnt_ovr == 0 and b.chip.cnt_crc == 0 and not b.chip.x.unsafe_reads and b.chip.obs["x_reads"] == 0
          and not b.chip.fifo_ovf)


# The scenarios from here to SCENARIOS exist because of the mutation run
# (python3 -m model.chip_v2.verify mutants): each closes a case where a broken
# copy of the model produced exactly the same pins as the real one.
def quiet_frame(p: int = 8) -> tuple[int, list[int]]:
    """A frame of all-zero activations whose only 0xA symbol is its sync, so a
    receiver that misses the sync cannot mistake anything later for one."""
    for seq in range(64):
        f = link_frame(seq, np.zeros(32, dtype=int), p)
        if C.SYNC_IN not in f[1:]:
            return seq, f
    raise AssertionError("no such frame")


def s_recover() -> None:
    print("recovery after a bad frame, to the symbol")
    rng = np.random.default_rng(12)
    w = rand_w(rng)
    a = rng.integers(0, 256, 32)
    good = link_frame(5, a, 8)
    bad = list(good)
    bad[10] ^= 1                                            # one payload bit: the CRC fails

    def accepted(gap: list[int]) -> bool:
        b = Bench()
        b.start(w, p=8)
        b.stream.extend(bad + gap + good)
        b.wait(lambda: not b.stream, what="the stream")
        b.run(150)
        return len(b.rx.frames) == 1 and b.rx.frames[0]["vals"] == reference(w, a) and b.rd(C.A_CNT_CRC) == 1

    check("a good frame 72 idle symbols after a bad one is accepted", accepted([0] * 72))
    check("a good frame 71 idle symbols after a bad one is not", not accepted([0] * 71))
    check("a non-idle symbol restarts the count: 40 idle, one symbol, 40 idle is not enough",
          not accepted([0] * 40 + [3] + [0] * 40))
    check("40 idle, one symbol, 72 idle is enough", accepted([0] * 40 + [3] + [0] * 72))

    # Switching the link off sends the receiver to hunt (section 2), which also ends a recovery wait.
    b = Bench()
    b.start(w, p=8)
    b.stream.extend(bad)
    b.wait(lambda: not b.stream, what="the stream")
    b.wr(C.A_MODE, 0)                                       # lands about 20 idle symbols into the wait
    b.wait(lambda: b.rd(C.A_STATUS) >> 6 & 1 == 0, limit=2000, what="the link to go down")
    b.spi([0x80 | C.A_MODE, C.M_LINK_EN], block=False)
    b.stream.extend([0] * 30 + good)                        # the frame as early as the link can take it
    b.wait(lambda: not b.stream, what="the stream")
    b.run(150)
    check("the link switched off and on during a recovery wait: the receiver is back in hunt and takes the next frame",
          len(b.rx.frames) == 1 and b.rx.frames[0]["vals"] == reference(w, a) and b.rd(C.A_CNT_CRC) == 1)


def s_linkup() -> None:
    print("the link coming out of reset")
    rng = np.random.default_rng(13)
    w = rand_w(rng)
    seq, frame = quiet_frame()
    got = []
    for k in range(14, 30):                                 # idle symbols before the frame's sync
        b = Bench()
        b.reset()
        b.wr(C.A_P, 7)
        b.load_weights(w)
        b.spi([0x80 | C.A_MODE, C.M_LINK_EN], block=False)
        b.stream.extend([0] * k + frame)
        b.wait(lambda: not b.stream, what="the stream")
        b.run(150)
        got.append(len(b.rx.frames) == 1 and b.rx.frames[0]["seq"] == seq and b.rx.frames[0]["vals"] == [0] * 4)
    first = got.index(True) if True in got else -1
    MEASURED["link enable: idle symbols needed between the MODE write starting and a frame"] = 14 + first
    check("a frame is taken from one exact symbol onward after the link is enabled, and never before",
          0 < first < len(got) - 1 and all(got[first:]) and not any(got[:first]),
          f"first accepted with {14 + first} idle symbols")


def s_status() -> None:
    print("STATUS bits and the busy rule at every phase of a vector")
    rng = np.random.default_rng(14)
    w, w2 = rand_w(rng), rand_w(rng)
    a8 = rng.integers(0, 256, 32)
    a1 = [rng.integers(0, 2, 32) for _ in range(3)]

    # P = 1: the return frame (22 cycles) outlasts the chain (12), so three frames in a row
    # leave a result waiting behind the transmitter and a loaded vector waiting behind that.
    seen = [set() for _ in range(4)]
    sane = True
    for off in range(0, 72, 1):
        b = Bench()
        b.start(w, p=1)
        send(b, [link_frame(i, v, 1) for i, v in enumerate(a1)], 13)
        b.run(off)
        st = b.rd(C.A_STATUS)
        for bit in range(4):
            seen[bit].add(st >> bit & 1)
        sane &= not (st & 0b0110 and not st & 1)            # a loaded vector or a waiting result means busy
        sane &= st >> 8 == 0 and st >> 6 & 1 == 1
    check("busy, chain_loaded, acc_valid and tx_busy are each seen at 0 and at 1", all(s == {0, 1} for s in seen))
    check("a loaded vector or a waiting result always reads as busy", sane)

    # A write that lands while only a result is waiting (chain free, transmitter still sending).
    waiting = accepted = 0
    for off in range(0, 48):
        b = Bench()
        b.start(w, p=1, shift=1)
        send(b, [link_frame(i, v, 1) for i, v in enumerate(a1[:2])], 13)
        b.run(off)
        b.spi([0x80 | C.A_SHIFT, 7], block=False)
        was = None
        for _ in range(40):
            state = (b.chip.chain, b.chip.acc_valid)
            b.run(1)
            if b.chip.err_busy and was is None:
                was = state
        b.run(60)
        got, st = b.rd(C.A_SHIFT), b.rd(C.A_STATUS)
        if was == (C.FREE, True):
            waiting += got == 1 and st >> 4 & 1
        accepted += got == 7 and not st >> 4 & 1
    check("a write while only a result is waiting is ignored and flagged", waiting > 0, f"{waiting} of 48 alignments")
    check("the same write is accepted at other times", accepted > 0, f"{accepted} of 48 alignments")

    for label, addr, value in (("P", C.A_P, 0), ("START", C.A_START, 9)):
        b = Bench()
        b.start(w, p=8)
        b.stream.extend(link_frame(1, a8, 8))
        b.wait(lambda: b.chip.chain == C.LOADING, what="a frame to start loading")
        b.wr(addr, value)
        b.wait(lambda: not b.stream, what="the stream")
        b.run(150)
        f = b.rx.frames
        check(f"a write to {label} while a vector loads is ignored and flagged",
              len(f) == 1 and f[0]["ok"] and f[0]["seq"] == 1 and f[0]["vals"] == reference(w, a8)
              and b.rd(C.A_P) == 7 and b.rd(C.A_STATUS) >> 4 & 1 == 1)

    b = Bench()
    b.start(w, p=8)
    b.jtag_reset()
    b.spi([0x80 | C.A_WEIGHTS] + weight_bytes(w2), period=4 * b.T, block=False)
    b.run(300)
    st = b.jtag_read(C.A_STATUS)
    b.jtag_write(C.A_P, 2)
    b.wait(lambda: not b.chip._busy() and b.chip.cs_n, what="the burst to end")
    b.run(20)
    check("STATUS.busy reads 1 between two rows of a weight burst, and a P write there is ignored",
          st & 1 == 1 and b.rd(C.A_P) == 7 and b.rd(C.A_STATUS) >> 4 & 1 == 1)


def s_modes() -> None:
    print("mode bits, counters and CLEAR")
    rng = np.random.default_rng(15)
    w = rand_w(rng)
    a = rng.integers(1, 256, 32)
    good = link_frame(3, a, 8)

    b = Bench()
    b.start(w, p=8, mode=C.M_LINK_EN | C.M_GATE_OFF)
    frames, _ = run_frames(b, w, [a], 8, 110)
    check("gate_off: the vector runs and every result is zero",
          len(frames) == 1 and frames[0]["ok"] and frames[0]["vals"] == [0] * 4)

    b = Bench()
    b.start(w, p=8, mode=C.M_LINK_EN | C.M_ACT_SPI)
    frames, _ = run_frames(b, w, [a], 8, 110)
    check("act_spi: link frames are ignored", not frames and b.chip.chain == C.FREE and b.rd(C.A_CNT_OVR) == 0)

    b = Bench()
    b.start(w, p=8)
    b.spi([0x80 | C.A_ACT] + act_bytes(np.full(32, 255), 8))
    flagged = b.rd(C.A_STATUS) >> 4 & 1
    frames, _ = run_frames(b, w, [a], 8, 110)
    check("ACT without act_spi is ignored and flagged, and the next frame is untouched",
          flagged == 1 and len(frames) == 1 and frames[0]["vals"] == reference(w, a))

    b = Bench()
    b.start(w, p=8)
    bad = list(good)
    bad[20] ^= 4
    b.stream.extend(bad + [0] * 80 + link_frame(0, a, 8, typ=3) + [0] * 80 + good + good + [0] * 200)
    b.wait(lambda: not b.stream, what="the stream")
    b.spi([0x80 | C.A_ACT, 0])                              # no act_spi: sets err_busy
    counts = [b.rd(x) for x in (C.A_CNT_CRC, C.A_CNT_OVR, C.A_CNT_BAD)]
    check("one CRC failure, one overrun, one bad type: each counter reads 1",
          counts == [1, 1, 1] and b.rd(C.A_STATUS) >> 4 & 1 == 1, str(counts))
    b.wr(C.A_CLEAR, 1)
    counts = [b.rd(x) for x in (C.A_CNT_CRC, C.A_CNT_OVR, C.A_CNT_BAD)]
    check("CLEAR bit 0 clears the counters and leaves the sticky flags", counts == [0, 0, 0] and b.rd(C.A_STATUS) >> 4 & 1 == 1)
    b.wr(C.A_CLEAR, 2)
    check("CLEAR bit 1 clears the sticky flags", b.rd(C.A_STATUS) >> 4 & 3 == 0)

    a1 = rng.integers(0, 2, 32)
    good1 = link_frame(1, a1, 1)
    bad1 = list(good1)
    bad1[5] ^= 1
    b = Bench()
    b.start(w, p=1)
    for _ in range(260):
        b.stream.extend(bad1 + [0] * 72)
    b.wait(lambda: not b.stream, limit=40_000, what="260 bad frames")
    b.run(20)
    check("the CRC counter stops at 255", b.chip.cnt_crc == 255 and b.rd(C.A_CNT_CRC) == 255 and not b.rx.frames)
    n = 800
    b.rx.frames.clear()
    send(b, [good1] * n, 13)
    b.wait(lambda: not b.stream, limit=40_000, what="800 crowded frames")
    b.run(100)
    lost = n - len(b.rx.frames)
    check("the overrun counter stops at 255", lost > 255 and b.rd(C.A_CNT_OVR) == 255, f"{lost} frames dropped")

    b = Bench()
    b.start(w, p=8)
    b.wr(C.A_BIST_CTRL, 1)
    b.run(50)
    b.stream.extend(good)
    b.wait(lambda: b.chip.bist is None, what="the memory test")
    b.run(200)
    check("a frame during a commanded memory test is dropped and counted; the test still passes",
          not b.rx.frames and b.rd(C.A_CNT_OVR) == 1 and b.rd(C.A_BIST_STAT) & 3 == C.B_PASS)


def s_jtagx() -> None:
    print("JTAG corners")
    b = Bench()
    b.reset()
    b.run(5)
    b.clk.stop()                                            # nothing can answer
    b.jtag_reset()
    b.jtag_ir(C.IR_DEBUG)
    b.jtag_dr(C.A_ID << 32, 40)
    check("with the core clock stopped a DEBUG scan reports not ready, all zeros", b.jtag_dr(C.A_ID << 32, 40) == 0)

    b = Bench()
    b.reset()
    b.jtag_reset()
    b.jtag_ir(C.IR_BYPASS)
    b.jtag([(1, 0)] * 5 + [(0, 0)])
    check("after a TAP reset the data register is IDCODE again, seen on TDO", b.jtag_dr(0, 32) == C.ID | 1)

    ties, others = 0, 0
    for off in range(8):                                    # SPI bytes arrive every 8 CLK cycles
        b = Bench()
        b.reset()
        b.wr(C.A_SHIFT, 5)
        b.jtag_reset()
        b.jtag_ir(C.IR_DEBUG)
        b.spi([0x80 | C.A_ID] + [0] * 60, offset=off * b.T, block=False)    # a long write that changes nothing
        b.jtag_write(C.A_SHIFT, 9)
        b.run(500)
        shift, flag = b.rd(C.A_SHIFT), b.rd(C.A_STATUS) >> 4 & 1
        ties += shift == 5 and flag == 1
        others += shift == 9 and flag == 0
    check("SPI and JTAG writing in the same CLK cycle: the JTAG write is dropped and flagged",
          ties == 1 and others == 7, f"{ties} tie and {others} clean writes in 8 alignments")


def s_robust() -> None:
    print("what the random runs found: races with a write, a dead link, the link switched off and on")
    rng = np.random.default_rng(16)
    w, w2 = rand_w(rng), rand_w(rng)
    a = rng.integers(0, 256, 32)
    frame = link_frame(4, a, 8)
    old = [sum((int(w[r, j]) & 0xFF) << (8 * j) for j in range(4)) for r in range(32)]
    new = [sum((int(w2[r, j]) & 0xFF) << (8 * j) for j in range(4)) for r in range(32)]

    # A MODE write whose command byte is taken while the chip is idle and whose data byte
    # lands as a frame begins. Every alignment, one CLK cycle apart, the same-edge one included.
    took = refused = 0
    ok = True
    for off in range(24):
        b = Bench()
        b.start(w, p=8)
        b.stream.extend([0] * off + frame)
        b.spi([0x80 | C.A_MODE, C.M_LINK_EN | C.M_ACT_SPI], block=False)
        b.wait(lambda: not b.stream, what="the stream")
        b.run(150)
        mode, flag = b.rd(C.A_MODE), b.rd(C.A_STATUS) >> 4 & 1
        if mode == C.M_LINK_EN:                             # refused: the frame must have run untouched
            refused += 1
            ok &= flag == 1 and len(b.rx.frames) == 1 and b.rx.frames[0]["vals"] == reference(w, a)
        else:                                               # taken first: the frame must have been ignored whole
            took += 1
            ok &= flag == 0 and not b.rx.frames
        ok &= b.rd(C.A_STATUS) & 1 == 0                     # and the chip is idle either way
    check("a MODE write racing the start of a frame is either taken first or refused, and never leaves the chip stuck",
          ok and took > 0 and refused > 0, f"{took} taken, {refused} refused in 24 alignments")

    took = refused = 0
    ok = True
    for off in range(24):
        b = Bench()
        b.start(w, p=8)
        b.stream.extend([0] * off + frame)
        b.spi([0x80 | C.A_WEIGHTS] + weight_bytes(w2), block=False)
        b.wait(lambda: not b.stream, what="the stream")
        b.wait(lambda: not b.chip._busy() and b.chip.cs_n and b.sim.t > b._spi_free, what="the burst to end")
        b.run(150)
        if b.rx.frames:                                     # the frame won: old weights, burst refused
            refused += 1
            ok &= b.rx.frames[0]["vals"] == reference(w, a) and b.chip.w_mem == old and b.rd(C.A_CNT_OVR) == 0
        else:                                               # the burst won: frame dropped, new weights
            took += 1
            ok &= b.chip.w_mem == new and b.rd(C.A_CNT_OVR) == 1
        ok &= b.chip.obs["gate_leaks"] == 0
    check("a weight burst racing the start of a frame: one of them wins whole, never a mix",
          ok and took > 0 and refused > 0, f"burst won {took}, frame won {refused} in 24 alignments")

    # The link dies in the middle of a frame.
    b = Bench()
    b.start(w, p=8)
    b.stream.extend(frame[:30])
    b.wait(lambda: len(b.stream) == 0, what="half a frame")
    b.run(3)
    b.link.stop()                                           # LINK_CLK stops for good
    b.run(300)
    stuck = b.rd(C.A_STATUS) & 1
    b.wr(C.A_MODE, C.M_ACT_SPI | C.M_TX_SILENCE)            # refused: the chip is busy
    refused = b.rd(C.A_MODE) == C.M_LINK_EN
    b.wr(C.A_CLEAR, 4 | 2)
    freed = b.rd(C.A_STATUS) & 0x11 == 0
    b.wr(C.A_MODE, C.M_ACT_SPI | C.M_TX_SILENCE)
    check("a link that dies mid-frame leaves the chip busy; CLEAR bit 2 frees it without a reset",
          stuck == 1 and refused and freed and b.rd(C.A_MODE) == C.M_ACT_SPI | C.M_TX_SILENCE)
    check("and the chip then runs over SPI with its weights intact", b.spi_vector(a, 8, 2) == reference(w, a))

    # An ACT burst holds the chip busy, so the other master cannot start the vector half loaded.
    b = Bench()
    b.start(w, p=8, mode=C.M_ACT_SPI | C.M_TX_SILENCE)
    b.jtag_reset()
    b.jtag_ir(C.IR_DEBUG)
    b.spi([0x80 | C.A_ACT] + act_bytes(a, 8), period=8 * b.T, block=False)
    b.run(400)
    b.jtag_write(C.A_START, 1)
    b.wait(lambda: b.chip.cs_n and b.sim.t > b._spi_free, what="the ACT burst")
    b.run(20)
    flagged = b.rd(C.A_STATUS) >> 4 & 1
    b.wr(C.A_START, 2)
    b.wait(lambda: not b.chip._busy(), what="the vector")
    check("START over JTAG in the middle of an SPI ACT burst is refused; the vector is then right",
          flagged == 1 and b.results() == reference(w, a))

    b = Bench()
    b.start(w, p=8)
    b.jtag_reset()
    b.jtag_write(C.A_ACT, 0xFFFFFFFF)
    flagged = b.rd(C.A_STATUS) >> 4 & 1
    frames, _ = run_frames(b, w, [a], 8, 110)
    check("ACT over JTAG without act_spi is refused, and the next frame is untouched",
          flagged == 1 and len(frames) == 1 and frames[0]["vals"] == reference(w, a))

    # The link switched off and straight on again. The low pulse on link_en is about 17 CLK
    # cycles; with LINK_CLK at 40 CLK periods the link domain may or may not see it.
    a1 = rng.integers(0, 2, 32)
    b = Bench(link=40 * 40 * PS)
    b.start(w, p=1)
    ok = True
    for i in range(16):
        b.rx.frames.clear()
        b.stream.extend(link_frame(i, a1, 1) + [3, 5, 7])       # the FIFO is left holding symbols that are not idle
        b.wait(lambda: b.rx.frames and not b.stream, limit=4000, what="a frame")
        ok &= b.rx.frames[0]["ok"] and b.rx.frames[0]["seq"] == i and b.rx.frames[0]["vals"] == reference(w, a1)
        b.run(i * 7)
        b.wr(C.A_MODE, 0, block=False)
        b.wr(C.A_MODE, C.M_LINK_EN)
        b.wait(lambda: b.rd(C.A_STATUS) >> 6 & 1, limit=4000, what="link ready")
        b.run(200)
    st = b.rd(C.A_STATUS)
    check("the link switched off and on 16 times with a slow link clock: every frame right, no overflow flag, "
          "no entry read twice", ok and st >> 5 & 1 == 0 and b.chip.obs["fifo_stale"] == 0
          and [b.rd(x) for x in (C.A_CNT_CRC, C.A_CNT_OVR, C.A_CNT_BAD)] == [0, 0, 0])

    # act_spi sends the receiver back to hunt, so a header cut off by it cannot swallow the next frame.
    # A stray sync, with act_spi written at every alignment around it. Where the write is taken
    # while the receiver is inside the header, the receiver must not stay there.
    ok, in_header = True, 0
    for off in range(24):
        b = Bench()
        b.start(w, p=8)
        b.stream.extend([0] * off + [C.SYNC_IN])
        b.spi([0x80 | C.A_MODE, C.M_LINK_EN | C.M_ACT_SPI], block=False)
        taken = False
        for _ in range(60):
            rx_before = b.chip.rx
            b.run(1)
            if b.chip.mode & C.M_ACT_SPI and not taken:
                taken = True
                in_header += rx_before in (C.HDR1, C.HDR2)
        if taken:
            b.wr(C.A_MODE, C.M_LINK_EN)
            frames, _ = run_frames(b, w, [a], 8, 110)
            ok &= len(frames) == 1 and frames[0]["vals"] == reference(w, a)
    check("act_spi taken in the middle of a header sends the receiver back to hunt: the next frame is not swallowed",
          ok and in_header > 0, f"{in_header} of 24 alignments land inside a header")

    # The write that stops the reset self-test is itself carried out, whatever kind it is.
    b = Bench()
    b.reset()
    b.run(40)
    b.spi([0x80 | C.A_WEIGHTS] + weight_bytes(w))
    b.wait(lambda: not b.chip._busy(), what="the weight load")
    rows = []
    for r in (0, 17, 31):
        b.wr(C.A_ROW_SEL, r)
        rows.append(b.rd(C.A_ROW_DATA) == old[r])
    check("a weight burst as the first write after reset stops the self-test and is carried out",
          all(rows) and b.rd(C.A_STATUS) >> 4 & 1 == 0 and b.rd(C.A_BIST_STAT) == 0b1111)
    b = Bench()
    b.reset()
    b.jtag_reset()
    b.jtag_write(C.A_SHIFT, 9)
    check("a JTAG write as the first write after reset stops the self-test and is carried out",
          b.rd(C.A_SHIFT) == 9 and b.rd(C.A_STATUS) >> 4 & 1 == 0)

    # Inside the chip: a write that stops the reset self-test in the middle of a row write.
    leaks = reads = 0
    got = True
    for off in range(12):
        b = Bench()
        b.reset()
        b.jtag_reset()
        b.run(off)
        b.jtag_write(C.A_ROW_SEL, 3)
        b.jtag_write(C.A_START, 0)
        b.run(60)
        leaks += b.chip.obs["gate_leaks"]
        reads += b.chip.obs["read_during_write"]
        got &= b.chip.mb_state == C.B_ABORT and not b.chip._busy()
    check("a JTAG write that stops the self-test mid row write: the activation gate stays closed during the write",
          leaks == 0 and reads == 0 and got)


def s_regs() -> None:
    print("the corners of the register map, the return frames and the TAP (spec 7, 8 and 10)")
    rng = np.random.default_rng(17)
    w = rand_w(rng)
    a, a2 = rng.integers(0, 256, 32), rng.integers(0, 256, 32)

    # A chip with something in every read-only register: a finished self-test, one CRC
    # failure, a result, and a row read back.
    b = Bench(meta=2 * PS)
    b.reset()
    b.wait(lambda: b.chip.selftest_done, what="self-test")
    b.wr(C.A_P, 7)
    b.load_weights(w)
    b.wr(C.A_MODE, C.M_LINK_EN)
    b.wait(lambda: b.chip.lr_s2, what="the link to come out of reset")
    bad = link_frame(1, a2, 8)
    bad[-1] ^= 1
    b.stream.extend(bad + [0] * 80 + link_frame(2, a, 8))
    b.wait(lambda: not b.stream, what="the stream to go out")
    b.run(200)
    b.wr(C.A_ROW_SEL, 5)
    ro = [C.A_ID, C.A_STATUS, *range(C.A_RESULT0, C.A_RESULT0 + 4), C.A_CNT_CRC, C.A_CNT_OVR, C.A_CNT_BAD,
          C.A_BIST_STAT, C.A_BIST_ROW, C.A_CBIST_SIG, C.A_ROW_DATA]
    rw = [C.A_MODE, C.A_P, C.A_SHIFT, *range(C.A_BIAS0, C.A_BIAS0 + 4), C.A_ROW_SEL]

    def snap():
        return {r: b.rd(r) for r in ro + rw}
    before = snap()
    live = (before[C.A_CNT_CRC] == 1 and before[C.A_BIST_STAT] == 0b0101
            and before[C.A_CBIST_SIG] == C.cbist_signature()
            and before[C.A_ROW_DATA] == sum((int(w[5, j]) & 0xFF) << (8 * j) for j in range(4))
            and [C.wrap(before[C.A_RESULT0 + j], 24) for j in range(4)] == reference(w, a))
    for r in ro:
        b.wr(r, (1 << 8 * C.REG_BYTES[r]) - 1)
    check("a write to a read-only register is ignored and not flagged", live and snap() == before,
          f"{len(ro)} registers, each holding a value")

    undef = range(0x1A, 0x80)
    for r in undef:
        b.spi([0x80 | r, 0xFF, 0xFF, 0xFF, 0xFF])
    reads = [b.spi([r, 0, 0, 0, 0, 0])[2:] for r in undef]
    b.jtag_reset()
    jt = [b.jtag_read(r) for r in (0x1A, 0x55, 0x7F)]
    check("addresses 0x1A to 0x7F read 0 over SPI and JTAG, and a write to one changes nothing and is not flagged",
          len(reads) == 102 and all(x == [0] * 4 for x in reads) and jt == [0] * 3 and snap() == before)

    wo = [C.A_START, C.A_WEIGHTS, C.A_ACT, C.A_CLEAR, C.A_BIST_CTRL]
    n_frames = len(b.rx.frames)
    reads = [b.spi([r, 0, 0, 0, 0, 0])[2:] for r in wo]
    jt = [b.jtag_read(r) for r in wo]
    b.run(100)
    check("write-only registers read 0 over SPI and JTAG, and reading one does nothing",
          all(x == [0] * 4 for x in reads) and jt == [0] * 5 and snap() == before and len(b.rx.frames) == n_frames)

    b.spi([0x80 | C.A_SHIFT, 0x05, 0x0A, 0x0B, 0x0C])
    b.spi([0x80 | C.A_BIAS0, 0x01, 0x23, 0x45, 0x67, 0x89])
    sh = b.spi([C.A_SHIFT, 0, 0, 0, 0, 0])[2:]
    idr = b.spi([C.A_ID, 0] + [0] * 7)[2:]
    check("bytes after a register's width are ignored when written, and read as 0",
          sh == [5, 0, 0, 0] and b.rd(C.A_BIAS0) == 0x012345 and idr == [0xDC, 0x1A, 0x00, 0x02, 0, 0, 0])

    b.wr(C.A_BIAS0 + 1, 0x0ABCDE)
    for bits in (16, 24, 29):                               # after one byte, two bytes, and mid third byte
        b.spi([0x80 | (C.A_BIAS0 + 1), 0x11, 0x22, 0x33], cut_bits=bits)
    b.wr(C.A_SHIFT, 7)
    check("a register write cut short after some of its bytes changes nothing, and the next is aligned",
          b.rd(C.A_BIAS0 + 1) == 0x0ABCDE and b.rd(C.A_SHIFT) == 7)

    rsv = {C.A_MODE: (0xE0 | C.M_LINK_EN, C.M_LINK_EN), C.A_P: (0xF9, 1), C.A_SHIFT: (0xFA, 0xA),
           C.A_ROW_SEL: (0xE9, 9), C.A_BIAS0 + 2: (0xFFFFFF, 0x1FFFFF), C.A_BIAS0 + 3: (0xE00001, 1)}
    got = {}
    for r, (v, _) in rsv.items():
        b.wr(r, v)
        got[r] = b.rd(r)
    ok = all(got[r] == m for r, (_, m) in rsv.items())
    b.wr(C.A_P, 7)
    b.spi([0x80 | C.A_ACT] + [0] * 32)                      # refused without act_spi, so err_busy is set
    b.wr(C.A_CLEAR, 0xF8)                                   # reserved bits only: clears nothing
    b.wr(C.A_BIST_CTRL, 0xFC)                               # reserved bits only: runs nothing
    st = b.rd(C.A_STATUS)
    ok &= b.rd(C.A_CNT_CRC) == 1 and st >> 4 & 1 == 1 and st & 1 == 0 and b.rd(C.A_BIST_STAT) == 0b0101
    b.wr(C.A_START, 0xFF)                                   # sequence number 63, type stays 0
    b.wait(lambda: not b.chip._busy() and b.chip.tx_cnt == 0, what="the vector")
    b.run(10)
    last = b.rx.frames[-1]
    ok &= len(b.rx.frames) == n_frames + 1 and last["seq"] == 63 and last["type"] == 0 and last["ok"]
    check("reserved bits are ignored when written and read 0 (MODE, P, SHIFT, ROW_SEL, BIAS, CLEAR, BIST_CTRL, START)",
          ok, str(got))
    b.wr(C.A_CLEAR, 3)

    b.wr(C.A_ROW_SEL, 31)
    b.jtag_write(C.A_WEIGHTS, 0x12345678)
    b.jtag_write(C.A_WEIGHTS, 0x9ABCDEF0)
    b.run(20)
    sel = b.rd(C.A_ROW_SEL)
    b.wr(C.A_ROW_SEL, 31)
    r31 = b.rd(C.A_ROW_DATA)
    b.wr(C.A_ROW_SEL, 0)
    r0 = b.rd(C.A_ROW_DATA)
    check("ROW_SEL steps modulo 32 after a JTAG weight write: row 31, then row 0",
          sel == 1 and r31 == 0x12345678 and r0 == 0x9ABCDEF0)

    # TDO between scans, and what the IR and BYPASS capture.
    b.jtag_reset()
    b.jtag_ir(C.IR_IDCODE)
    t1 = b.jtag([(1, 0), (0, 0), (0, 0)] + [(int(i == 31), 0) for i in range(32)] + [(1, 0), (0, 0)] + [(0, 0)] * 10)
    t2 = b.jtag([(1, 0), (1, 0), (0, 0), (0, 0)] + [(int(i == 2), 1) for i in range(3)] + [(1, 0), (0, 0)])
    t3 = b.jtag([(1, 0), (0, 0), (0, 0)] + [(int(i == 2), 0) for i in range(3)] + [(1, 0), (0, 0)] + [(0, 0)] * 10)
    idc = sum(t << i for i, t in enumerate(t1[3:35]))
    check("TDO holds the last bit shifted out until the next shift (1 after IDCODE, 0 after BYPASS)",
          idc == C.ID | 1 and set(t1[35:]) == {1} and set(t3[6:]) == {0})
    check("the IR captures 001 and BYPASS captures 0", t2[4:7] == [1, 0, 0] and t3[3] == 0)

    # Return frames: idle lanes, back to back, and never changed once started.
    b = Bench()
    b.start(w, p=8)
    b.rx.frames.clear()
    vecs = [rng.integers(0, 256, 32) for _ in range(3)]
    send(b, [link_frame(i, v, 8) for i, v in enumerate(vecs)], 140)
    lanes = []
    for _ in range(3 * 140 + 200):
        b.run(1)
        lanes.append(b.chip.link_tx)
    check("LINK_TX is 0 before, between and after return frames",
          len(b.rx.frames) == 3 and b.rx.sync_errors == 0 and not any(lanes[:60]) and not any(lanes[-60:])
          and sum(1 for v in lanes if v) <= 3 * 29
          and all(f["ok"] and f["vals"] == reference(w, v) for f, v in zip(b.rx.frames, vecs)))

    b = Bench()
    b.start(w, p=1)
    vecs = [rng.integers(0, 2, 32) for _ in range(6)]
    frames, ovr = run_frames(b, w, vecs, 1, 22)
    gaps = sorted({f2["cycle"] - f1["cycle"] for f1, f2 in zip(frames, frames[1:])})
    check("return frames follow each other with no idle cycle between them (P = 1 raw, 22-cycle frames)",
          ovr == 0 and len(frames) == 6 and gaps == [22]
          and all(f["ok"] and f["vals"] == reference(w, v) for f, v in zip(frames, vecs)), f"gaps {gaps}")

    b = Bench()
    b.start(w, p=8)
    b.rx.frames.clear()
    b.stream.extend(link_frame(5, a, 8))
    b.wait(lambda: b.chip.tx_cnt > 0, what="the return frame")
    b.wr(C.A_MODE, C.M_LINK_EN | C.M_REQUANT | C.M_TX_SILENCE)
    mid = b.chip.tx_cnt > 0                                 # the write took effect while the frame was going out
    b.run(60)
    f1 = list(b.rx.frames)
    b.stream.extend(link_frame(6, a2, 8))
    b.run(200)
    check("MODE written while a return frame goes out: that frame is unchanged, the next capture uses the new mode",
          mid and len(f1) == 1 and f1[0]["type"] == 0 and f1[0]["ok"] and f1[0]["vals"] == reference(w, a)
          and len(b.rx.frames) == 1 and b.results() == reference(w, a2))

    bias = (100, -200, 3000, -5)
    want = [C.requant(r, bias[j], 6) for j, r in enumerate(reference(w, a))]
    during = right = 0
    for addr, value in ((C.A_SHIFT, 1), (C.A_BIAS0, 0x0FFFFF)):
        for k in range(48, 80, 2):
            b = Bench()
            b.start(w, p=8, mode=C.M_LINK_EN | C.M_REQUANT, shift=6, bias=bias)
            b.rx.frames.clear()
            b.stream.extend(link_frame(7, a, 8))
            b.wait(lambda: b.chip.chain == C.LOADING, what="the frame")
            b.run(k)
            n = C.REG_BYTES[addr]
            b.spi([0x80 | addr] + [(value >> (8 * (n - 1 - i))) & 0xFF for i in range(n)], block=False)
            seen = (b.chip.shift, list(b.chip.bias))
            for _ in range(120):
                b.run(1)
                if (b.chip.shift, list(b.chip.bias)) != seen:
                    during += 0 < b.chip.tx_cnt < 16
                    break
            b.run(40)
            right += len(b.rx.frames) == 1 and b.rx.frames[0]["vals"] == want and b.rx.frames[0]["ok"]
    check("SHIFT and BIAS written while a requantized frame goes out do not change it",
          right == 32 and during >= 4, f"{during} of 32 writes landed mid-frame, {right} frames right")


def s_reset() -> None:
    print("reset from every kind of activity, at every phase of CLK, and the self-test that follows")
    rng = np.random.default_rng(19)
    w = rand_w(rng)
    a = rng.integers(0, 256, 32)

    def outputs(c):
        return (c.link_tx, c.miso, c.tdo, c.status)

    def dirty(b):
        """Leave the read-data and JTAG answer registers holding something."""
        b.jtag_reset()
        b.jtag_read(C.A_ID)
        b.spi([C.A_CBIST_SIG, 0])

    def after(b):
        """What a host sees first after RST_N rises: the first SPI read with its dummy byte, the
        first JTAG capture (nothing asked yet), then every register once the self-test is over."""
        first = b.spi([C.A_ID, 0, 0, 0, 0, 0])
        b.jtag_reset()
        b.jtag_ir(C.IR_DEBUG)
        cap = b.jtag_dr(0, 40)
        b.wait(lambda: b.chip.selftest_done, what="self-test")
        return first, cap, {r: b.rd(r) for r in sorted(C.REG_BYTES)}

    fresh = Bench()
    fresh.reset()
    want = after(fresh)
    fresh = Bench()                                         # a cell defect survives reset, as on silicon
    fresh.chip.stuck[(9, 5)] = 1
    fresh.reset()
    want_stuck = after(fresh)

    def hold(b, probe):
        """RST_N stays low until anything the bench had scheduled is over, then at least 4 CLK."""
        b.chip.set_rst_n(0)
        probe.append(outputs(b.chip))
        end = max(b.sim.t, b._spi_free, b._jtag_free) + 4 * b.T
        while b.sim.t < end:
            b.run(1)
            probe.append(outputs(b.chip))
        b.chip.set_rst_n(1)

    def state_frame_out(b):
        b.start(w, p=8)
        dirty(b)
        b.stream.extend(link_frame(1, a, 8))
        b.wait(lambda: b.chip.link_tx != 0, what="a return frame")

    def state_loading(b):
        b.start(w, p=8)
        dirty(b)
        b.stream.extend(link_frame(1, a, 8))
        b.wait(lambda: b.chip.chain == C.LOADING, what="a frame loading")

    def state_miso(b):
        b.reset()
        dirty(b)
        b.spi([C.A_ID, 0, 0, 0, 0, 0], block=False)
        b.wait(lambda: b.chip.miso == 1, what="MISO high")

    def state_status(b):
        b.chip.stuck[(9, 5)] = 1
        b.reset()
        b.wait(lambda: b.chip.selftest_done, what="self-test")
        dirty(b)
        b.run(5)

    def state_selftest(b):
        b.reset()
        b.run(400)

    before, probes, again = [], [], []
    for state in (state_frame_out, state_loading, state_miso, state_status, state_selftest):
        b = Bench()
        state(b)
        before.append(outputs(b.chip))
        probe = []
        hold(b, probe)
        probes.append(all(p == (0, 0, 0, 0) for p in probe))
        again.append(after(b) == (want_stuck if b.chip.stuck else want))

    # TDO: reset in the middle of an IDCODE scan, on a bit that is 1.
    b = Bench()
    b.reset()
    dirty(b)
    b.jtag_ir(C.IR_IDCODE)
    probe = []

    def watch():
        if not probe and b.chip.rst_n and b.chip.tap == C.SH_DR and b.chip.tdo == 1:
            before.append(outputs(b.chip))
            b.chip.set_rst_n(0)
            probe.append(outputs(b.chip))
    t0 = b.sim.t
    for i in range(48):
        b.sim.at(t0 + int((i + 0.8) * b.tck_period), watch)
    b.jtag_dr(0, 32)
    b.chip.set_rst_n(1)                                     # put back up to hold it properly
    hold(b, probe)
    probes.append(len(probe) > 1 and all(p == (0, 0, 0, 0) for p in probe))
    again.append(after(b) == want)
    was = [any(o[i] for o in before) for i in range(4)]
    check("RST_N low drives every output to 0 at once and holds it there, from 6 kinds of activity",
          all(probes) and all(was), f"before the reset: LINK_TX, MISO, TDO, STATUS were nonzero: {was}")
    check("after a reset from each of them the chip answers exactly as a fresh one (dummy byte, first JTAG "
          "capture, every register)", all(again), f"{sum(again)} of {len(again)}")
    first, cap, regs = want
    resets = {C.A_ID: C.ID, C.A_MODE: 0, C.A_P: 7, C.A_SHIFT: 0, C.A_BIAS0: 0, C.A_BIAS0 + 1: 0, C.A_BIAS0 + 2: 0,
              C.A_BIAS0 + 3: 0, C.A_RESULT0: 0, C.A_RESULT0 + 1: 0, C.A_RESULT0 + 2: 0, C.A_RESULT0 + 3: 0,
              C.A_CNT_CRC: 0, C.A_CNT_OVR: 0, C.A_CNT_BAD: 0, C.A_ROW_SEL: 0}
    check("every register with a reset value in the register table reads it after reset; the dummy byte is 0 and "
          "the first JTAG capture is ready with zeros",
          all(regs[r] == v for r, v in resets.items()) and first == [0, 0, 0xDC, 0x1A, 0x00, 0x02]
          and cap == 1 << 39)

    # The core leaves reset on the second CLK edge after RST_N rises, whatever the phase. STATUS
    # first goes high 32,768 core cycles later (the heartbeat after a pass), so the count is exact.
    edges = []
    for k in range(8):
        b = Bench()
        b.chip.set_rst_n(0)
        b.run(4 + (k + 0.5) / 8)
        b.chip.set_rst_n(1)
        n = 0
        while not b.chip.status:
            b.run(1)
            n += 1
        edges.append(n)
    MEASURED["CLK rising edges from RST_N rising to the first heartbeat edge on STATUS"] = edges[0]
    check("the core leaves reset on the second CLK edge after RST_N rises, at 8 phases of CLK",
          edges == [2 + (1 << 15)] * 8, str(sorted(set(edges))))

    # The self-test that follows: the memory test first, and every read answered throughout.
    b = Bench()
    b.reset()
    seen, swept, answered = [], set(), True
    stable = {C.A_ID: C.ID, C.A_MODE: 0, C.A_P: 7, C.A_SHIFT: 0, C.A_BIAS0: 0, C.A_RESULT0: 0, C.A_CNT_CRC: 0,
              C.A_ROW_SEL: 0, C.A_ROW_DATA: 0}
    while True:
        st = b.rd(C.A_BIST_STAT)
        if not seen or seen[-1] != st:
            seen.append(st)
        if st == 0b0101:
            break
        got = {r: b.rd(r) for r in stable}
        for r in (C.A_STATUS, C.A_BIST_ROW, C.A_CBIST_SIG, C.A_CNT_OVR, C.A_CNT_BAD):
            b.rd(r)
        answered &= got == stable
        swept.add(st)
    check("out of reset the memory test runs first, then the compute test", seen == [0b0000, 0b0001, 0b0101],
          str([bin(s) for s in seen]))
    check("every read is answered while each test runs", answered and swept == {0b0000, 0b0001})


def s_tap() -> None:
    print("the TAP: all 32 state transitions, seen at TDO and in what the scans do")
    b = Bench()
    b.reset()
    tms = [1] * 5 + [0]
    b.jtag_reset()                                          # ends in Run-Test/Idle
    ident = C.ID | 1

    def go(steps):
        tms.extend(t for t, _ in steps)
        return b.jtag(steps)

    def ir(code):
        return [(1, 0), (1, 0), (0, 0), (0, 0)] + [(int(i == 2), (code >> i) & 1) for i in range(3)] + [(1, 0), (0, 0)]

    def value(bits):
        return sum(t << i for i, t in enumerate(bits))

    go([(0, 0)] * 3)                                        # Run-Test/Idle held
    go(ir(C.IR_IDCODE))
    t = go([(1, 0), (0, 0), (0, 0)] + [(int(i == 9), 0) for i in range(10)] + [(0, 0), (0, 0), (1, 0), (0, 0)]
           + [(int(i == 21), 0) for i in range(22)] + [(1, 0), (0, 0)])
    check("IDCODE read with Pause-DR and Exit2-DR in the middle of the scan", value(t[3:13] + t[17:39]) == ident)

    go(ir(C.IR_DEBUG))
    req = (1 << 39) | (C.A_SHIFT << 32) | 9
    go([(1, 0), (0, 0), (0, 0)] + [(int(i == 19), (req >> i) & 1) for i in range(20)] + [(0, 0), (1, 0), (0, 0)]
       + [(int(i == 19), (req >> (20 + i)) & 1) for i in range(20)] + [(0, 0), (1, 0), (1, 0), (0, 0)])
    b.run(20)
    check("a DEBUG write that passes twice through Pause-DR and leaves by Exit2-DR to Update-DR is carried out",
          b.rd(C.A_SHIFT) == 9)

    # IDCODE (001) shifted in with a pause before its last bit: a TAP that loses that bit loads 010, DEBUG.
    go(ir(C.IR_BYPASS))
    go([(1, 0), (1, 0), (0, 0), (0, 0), (0, 1), (1, 0), (0, 0), (0, 0), (1, 0), (0, 0), (1, 0), (1, 0), (0, 0)])
    t = go([(1, 0), (0, 0), (0, 0)] + [(int(i == 31), 0) for i in range(32)] + [(1, 0), (0, 0)])
    idcode = value(t[3:35]) == ident
    go([(1, 0), (1, 0), (0, 0), (0, 0), (0, 1), (0, 1), (1, 1), (0, 0), (1, 0), (1, 0), (0, 0)])
    t = go([(1, 0), (0, 0), (0, 0)] + [(int(i == 4), (0b1011 >> i) & 1) for i in range(5)] + [(1, 0), (0, 0)])
    check("the IR loaded through Pause-IR and Exit2-IR, leaving Exit2-IR both ways (IDCODE, then BYPASS)",
          idcode and value(t[3:8]) == 0b10110)

    go(ir(C.IR_BYPASS))
    go([(1, 0), (1, 0), (1, 0), (0, 0)])
    t = go([(1, 0), (0, 0), (0, 0)] + [(int(i == 31), 0) for i in range(32)] + [(1, 0), (0, 0)])
    check("Select-IR with TMS high resets the TAP, which selects IDCODE", value(t[3:35]) == ident)

    t = go([(1, 0), (0, 0), (1, 0), (1, 0), (1, 0), (0, 0), (0, 0)] + [(int(i == 31), 0) for i in range(32)]
           + [(1, 0), (0, 0)])
    check("a scan with no shift, Update-DR straight to Select-DR, then a full scan", value(t[7:39]) == ident)

    go(ir(C.IR_BYPASS))
    t = go([(1, 0), (1, 0), (0, 0), (1, 0), (1, 0), (1, 0), (0, 0), (0, 0)] + [(int(i == 31), 0) for i in range(32)]
           + [(1, 0), (0, 0)])
    check("an IR scan with no shift loads the captured 001, which is IDCODE", value(t[8:40]) == ident)

    cover, s = set(), C.TLR
    for m in tms:
        cover.add((s, m))
        s = C.NEXT[s][m]
    check("these scans take every one of the 32 TAP transitions", len(cover) == 32, f"{len(cover)} of 32")


def column_weights(sums) -> np.ndarray:
    """Weights whose four columns add up to the given sums (each -4,096 to 4,064)."""
    w = np.zeros((32, 4), dtype=np.int64)
    for j, s in enumerate(sums):
        left = int(s)
        for r in range(32):
            w[r, j] = max(-128, min(127, left))
            left -= int(w[r, j])
        assert left == 0, s
    return w


def s_cover() -> None:
    print("sweeps for the functional coverage model (plan section 5), each with its own checks")
    from .coverage import min_period
    rng = np.random.default_rng(21)
    w = rand_w(rng)

    # Every P, every return mode: frames at the minimum spacing, one more, one too close, back to
    # back, a CRC failure, and a good frame after the recovery wait. Computes are counted on the
    # STATUS pin, so silent frames are counted too.
    wrong = []
    for p in range(1, 9):
        for kind, flags in (("raw", 0), ("requantized", C.M_REQUANT), ("silent", C.M_TX_SILENCE)):
            shift, bias = 3, (5, -7, 11, -13)
            b = Bench()
            b.start(w, p=p, mode=C.M_LINK_EN | flags, shift=shift, bias=bias)
            b.trace_status = True
            mp = min_period(p, bool(flags & C.M_REQUANT), bool(flags & C.M_TX_SILENCE))
            vecs = [rng.integers(0, 1 << p, 32) for _ in range(7)]
            fr = [link_frame(i, v, p) for i, v in enumerate(vecs)]
            n = len(fr[0])
            fr[5][3] ^= 1
            for f, gap in zip(fr, (mp, mp + 1, mp - 1, n, mp + 4, n + 92, 0)):
                b.stream.extend(f + [0] * max(0, gap - n))
            b.wait(lambda: not b.stream, what="the stream")
            b.run(200)
            computes = sum(b.status_trace)

            def want(v):
                r = reference(w, v)
                return [C.requant(x, bias[j], shift) for j, x in enumerate(r)] if flags & C.M_REQUANT else r
            ovr, crc = b.rd(C.A_CNT_OVR), b.rd(C.A_CNT_CRC)
            ok = crc == 1 and computes + ovr == 6
            if flags & C.M_TX_SILENCE:
                ok &= not b.rx.frames and b.results() == reference(w, vecs[6])
            else:
                ok &= len(b.rx.frames) == computes and b.rx.frames[-1]["seq"] == 6
                ok &= all(f["ok"] and f["vals"] == want(vecs[f["seq"]]) for f in b.rx.frames)
            b.wr(C.A_BIST_CTRL, 1)                          # a frame during a commanded test is dropped
            b.stream.extend(link_frame(7, vecs[0], p))
            b.wait(lambda: not b.stream, what="the stream")
            b.run(60)
            ok &= b.rd(C.A_CNT_OVR) == ovr + 1
            if not ok:
                wrong.append((p, kind, computes, ovr, crc))
    check("every P and return mode: frames at the minimum spacing, one more, one too close, back to back, and a "
          "CRC failure; each is computed right or dropped and counted", not wrong, str(wrong[:3]))

    # The most positive and most negative result of every lane at every P.
    ok = True
    for wv in (127, -128):
        b = Bench()
        b.start(np.full((32, 4), wv), p=8)
        for p in range(1, 9):
            b.wr(C.A_P, p - 1)
            b.rx.p = p
            b.rx.frames.clear()
            b.stream.extend(link_frame(p, np.full(32, (1 << p) - 1), p))
            b.wait(lambda: not b.stream, what="the stream")
            b.run(120)
            ok &= len(b.rx.frames) == 1 and b.rx.frames[0]["vals"] == [32 * wv * ((1 << p) - 1)] * 4
    check("the largest and the smallest result of every lane at every P come back exact", ok)

    # Requantize: r + bias negative, zero, in range and above 255, at shift 0, 7 and 15, with the bias
    # negative and not. r is 255 times a column sum, so each lane's case is set by its weights.
    cases = {0: [(-10, 100), (10, -3000), (-10, 2550), (10, -2550), (1, 0), (2, -300), (10, 0), (100, -100)],
             7: [(-10, 100), (10, -3000), (-10, 2550), (10, -2550), (10, 100), (100, -500), (200, 0), (300, -1000)],
             15: [(-10, 100), (10, -3000), (-10, 2550), (10, -2550), (10, 0), (4000, -100)]}
    ok, n = True, 0
    for shift, lanes in cases.items():
        for i in range(0, len(lanes), 4):
            group = (lanes[i:i + 4] + lanes[:4])[:4]
            sums, bias = [g[0] for g in group], [g[1] for g in group]
            b = Bench()
            b.start(column_weights(sums), p=8, mode=C.M_LINK_EN | C.M_REQUANT, shift=shift, bias=bias)
            b.stream.extend(link_frame(1, np.full(32, 255), 8))
            b.wait(lambda: not b.stream, what="the stream")
            b.run(120)
            want = [C.requant(255 * s, bias[j], shift) for j, s in enumerate(sums)]
            ok &= len(b.rx.frames) == 1 and b.rx.frames[0]["vals"] == want and b.rx.frames[0]["type"] == 1
            n += 1
    check("requantize at every corner of r + bias, shift and bias sign comes back exact", ok, f"{n} frames")

    # Every address over both masters; then chip select raised after every bit count.
    b = Bench()
    b.reset()
    b.wait(lambda: b.chip.selftest_done, what="self-test")
    b.jtag_reset()
    jt_reads = {}
    for addr in range(128):
        b.jtag_write(addr, 0)
        jt_reads[addr] = b.jtag_read(addr)
        b.spi([0x80 | addr, 0])
        b.spi([addr, 0, 0])
    plain = [a for a in range(128) if a not in C.REG_BYTES or a in (C.A_START, C.A_CLEAR, C.A_BIST_CTRL)]
    check("every address written and read over JTAG and SPI: undefined and write-only ones read 0, ID reads ID",
          all(jt_reads[a] == 0 for a in plain) and jt_reads[C.A_ID] == C.ID, f"{len(plain)} addresses read 0")

    b = Bench()
    b.reset()
    b.wr(C.A_SHIFT, 5)
    got = []
    for k in range(1, 17):
        b.spi([0x80 | C.A_SHIFT, 0x0F], cut_bits=k)
        got.append(b.rd(C.A_SHIFT))
        b.wr(C.A_SHIFT, 5)
    w2 = rand_w(rng)
    b.wr(C.A_ROW_SEL, 1)
    before = b.rd(C.A_ROW_DATA)
    b.spi([0x80 | C.A_WEIGHTS] + weight_bytes(w2), cut_bits=8 + 32 + 13)    # one row and part of the next
    b.run(10)
    rows = []
    for r in (0, 1):
        b.wr(C.A_ROW_SEL, r)
        rows.append(b.rd(C.A_ROW_DATA))
    first = sum((int(w2[0, j]) & 0xFF) << (8 * j) for j in range(4))
    check("chip select raised after each of 1 to 16 bits: only the whole write lands; a burst cut in a row keeps "
          "the row before it and leaves the rest", got == [5] * 15 + [15] and rows == [first, before])

    b = Bench(meta=2 * PS)
    b.spi_period = int(b.T * 1.05) // 2 * 2
    b.reset()
    vals = {C.A_SHIFT: 9, C.A_BIAS0: 0x12345, C.A_P: 2}
    for r, v in vals.items():
        b.wr(r, v)
    check("SCLK just slower than CLK (x 1.05): every register reads back", all(b.rd(r) == v for r, v in vals.items()))

    # STATUS: high after a failed self-test, then DONE at the first write.
    b = Bench()
    b.chip.stuck[(9, 5)] = 1
    b.reset()
    b.wait(lambda: b.chip.selftest_done, what="self-test")
    b.run(5)
    high = b.chip.status == 1
    b.trace_status = True
    b.wr(C.A_MODE, C.M_ACT_SPI | C.M_TX_SILENCE)
    b.spi_vector(np.zeros(32, dtype=int), 8)
    tr = b.status_trace
    after = tr[tr.index(0):] if 0 in tr else []
    check("STATUS high after a failed self-test turns into DONE pulses at the first write",
          high and tr[0] == 1 and sum(after) == 1)

    # The bad-frame counter up to 255, and held there.
    b = Bench()
    b.start(w, p=8)
    bad = link_frame(1, np.zeros(32, dtype=int), 8, typ=1)[:3]
    for _ in range(256):
        b.stream.extend(bad + [0] * 74)
    b.wait(lambda: not b.stream, what="the stream")
    b.run(100)
    check("the bad-frame counter stops at 255", b.rd(C.A_CNT_BAD) == 255)

    # Every IR code selects the data register the table says.
    b = Bench()
    b.reset()
    b.jtag_reset()
    lengths = {}
    for code in range(8):
        b.jtag_ir(code)
        t = b.jtag([(1, 0), (0, 0), (0, 0)] + [(0, 0)] * 64 + [(0, 1)] + [(0, 0)] * 63 + [(1, 0), (1, 0), (0, 0)])
        out = t[3 + 65:3 + 128]
        lengths[code] = out.index(1) + 1 if 1 in out else None
        b.run(50)
    check("every IR code selects its data register: 32, 40, 8 and 35 bits, and 1 bit for 000, 101, 110 and 111",
          lengths == {0: 1, 1: 32, 2: 40, 3: 8, 4: 35, 5: 1, 6: 1, 7: 1}, str(lengths))

    # The receiver stopped in each of its states: by RST_N, by CLEAR bit 2 and by switching the link off.
    ok, seq_f, frame = True, 3, None
    a = rng.integers(0, 256, 32)
    for state in (C.HDR1, C.HDR2, C.PAYLOAD, C.CRC1, C.CRC2, C.SKIP, C.RECOVER):
        b = Bench(link=40 * 40 * PS)                        # a slow link, so each state lasts 40 CLK
        b.start(w, p=8)
        f = link_frame(1, a, 8)
        if state == C.SKIP:                                 # a frame during a commanded test is skipped
            b.wr(C.A_BIST_CTRL, 1)
            b.stream.extend(f)
        elif state == C.RECOVER:
            g = list(f)
            g[5] ^= 1
            b.stream.extend(g)
        else:
            b.stream.extend(f)
        b.wait(lambda: b.chip.rx == state, limit=400_000, what="the receiver state")
        b.chip.set_rst_n(0)
        b.run(4)
        b.stream.clear()
        b2 = b
        b2.start(w, p=8)
        b2.rx.frames.clear()
        b2.rx.q = [[] for _ in range(4)]
        b2.stream.extend(f)
        b2.wait(lambda: not b2.stream, limit=400_000, what="the stream")
        b2.run(400)
        ok &= len(b2.rx.frames) == 1 and b2.rx.frames[0]["vals"] == reference(w, a)
    for state, how in ((C.CRC2, "clear"), (C.CRC1, "clear"), (C.HDR1, "off"), (C.HDR2, "off")):
        b = Bench(link=40 * 40 * PS)
        b.start(w, p=8)
        b.stream.extend(link_frame(1, a, 8))
        b.wait(lambda: b.chip.rx == state, limit=400_000, what="the receiver state")
        if how == "clear":
            b.wr(C.A_CLEAR, 4)
            b.wait(lambda: not b.stream, limit=400_000, what="the stream")
            b.stream.extend([0] * 80)
            b.wait(lambda: not b.stream, limit=400_000, what="the idle symbols")
            ok &= b.rd(C.A_STATUS) & 1 == 0
        else:
            b.wr(C.A_MODE, 0)
            b.wait(lambda: b.rd(C.A_STATUS) >> 6 & 1 == 0, limit=40_000, what="the link to go down")
            b.stream.clear()
            b.wr(C.A_MODE, C.M_LINK_EN)
            b.wait(lambda: b.rd(C.A_STATUS) >> 6 & 1, limit=40_000, what="the link to come up")
        b.rx.frames.clear()
        b.rx.q = [[] for _ in range(4)]
        b.stream.extend(link_frame(2, a, 8))
        b.wait(lambda: not b.stream, limit=400_000, what="the stream")
        b.run(400)
        ok &= len(b.rx.frames) == 1 and b.rx.frames[0]["seq"] == 2 and b.rx.frames[0]["vals"] == reference(w, a)
    check("the receiver stopped in each of its states (by RST_N, CLEAR bit 2, or the link switched off) takes the "
          "next frame whole", ok)

    # The rest of what random traffic reaches: other TCK rates and phases, the receiver in recovery or
    # skipping when act_spi or link off arrives, a row write asked for in each write-controller state,
    # and the compute test stopped while it writes and while it runs vectors.
    ok = True
    for k in range(8):
        b = Bench()
        b.tck_period = int(b.T * (4 + k / 8 + (5 if k == 7 else 0))) // 2 * 2     # up to 9.875 CLK
        b.reset()
        b.jtag_reset()
        ok &= b.jtag_read(C.A_ID) == C.ID
    for state, how in ((C.RECOVER, "act"), (C.SKIP, "act"), (C.SKIP, "off")):
        b = Bench(link=40 * 40 * PS)
        b.start(w, p=8)
        f = link_frame(1, a, 8)
        if state == C.SKIP:
            b.wr(C.A_BIST_CTRL, 1)
            b.stream.extend(f)
        else:
            g = list(f)
            g[5] ^= 1
            b.stream.extend(g)
        b.wait(lambda: b.chip.rx == state, limit=400_000, what="the receiver state")
        b.wr(C.A_MODE, C.M_LINK_EN | C.M_ACT_SPI if how == "act" else 0)
        b.wait(lambda: not b.chip._busy(), limit=40_000, what="idle")
        b.stream.clear()
        if state == C.SKIP:
            b.load_weights(w)                               # the commanded memory test wrote its patterns
        b.wr(C.A_MODE, C.M_LINK_EN)
        b.wait(lambda: b.rd(C.A_STATUS) >> 6 & 1, limit=40_000, what="the link to come up")
        b.run(200)
        b.rx.frames.clear()
        b.rx.q = [[] for _ in range(4)]
        b.stream.extend(link_frame(2, a, 8))
        b.wait(lambda: not b.stream, limit=400_000, what="the stream")
        b.run(400)
        ok &= len(b.rx.frames) == 1 and b.rx.frames[0]["vals"] == reference(w, a)
    for k in range(8):
        b = Bench()
        b.reset()
        b.run(40)
        b.jtag_reset()
        b.run(k / 2)
        b.jtag_write(C.A_WEIGHTS, 0x0F0F0F0F)
        b.run(20)
        ok &= b.chip.mb_state == C.B_ABORT and not b.chip.obs["wc_collisions"]
    for at in (1535 + 100, 1535 + 600):                     # weights being written, then vectors running
        b = Bench()
        b.reset()
        b.run(at)
        b.wr(C.A_SHIFT, 4)
        ok &= b.chip.mb_state == C.B_PASS and b.chip.cb_state == C.B_ABORT and b.rd(C.A_SHIFT) == 4
    check("JTAG at other TCK rates and phases, the receiver stopped while recovering or skipping, a row write asked "
          "for in each write-controller state, and the compute test stopped in each phase", ok)

    # A write racing a frame's first payload symbol, with a value that changes nothing, so the frame
    # goes on either way: it is taken first (no flag) or refused (flag), and the frame is right.
    outcome = {}
    for reg, value in ((C.A_MODE, C.M_LINK_EN), (C.A_P, 7)):
        seen = set()
        good = True
        for off in range(24):
            b = Bench()
            b.start(w, p=8)
            b.stream.extend([0] * off + link_frame(4, a, 8))
            b.spi([0x80 | reg, value], block=False)
            b.wait(lambda: not b.stream, what="the stream")
            b.run(150)
            flag = b.rd(C.A_STATUS) >> 4 & 1
            seen.add(flag)
            good &= len(b.rx.frames) == 1 and b.rx.frames[0]["vals"] == reference(w, a)
        outcome[reg] = good and seen == {0, 1}
    seen, good = set(), True
    for off in range(24):                                   # START: the write or the frame, never both
        b = Bench()
        b.start(w, p=8)
        b.stream.extend([0] * off + link_frame(4, a, 8))
        b.spi([0x80 | C.A_START, 9], block=False)
        b.wait(lambda: not b.stream, what="the stream")
        b.run(150)
        flag = b.rd(C.A_STATUS) >> 4 & 1
        seqs = sorted(f["seq"] for f in b.rx.frames)
        seen.add(flag)
        if flag:
            good &= seqs == [4] and b.rx.frames[0]["vals"] == reference(w, a)
        else:
            good &= 9 in seqs and (seqs == [9] and b.rd(C.A_CNT_OVR) == 1 or seqs == [4, 9])
    outcome[C.A_START] = good and seen == {0, 1}
    check("MODE, P and START racing a frame's first payload symbol: the write goes first or is refused, never both",
          all(outcome.values()), str(outcome))

    # Guarded writes from both masters while the chip is busy for each reason in turn. Where every
    # write must be refused, each one carries a value that would show if it were taken.
    ok = True
    regs = [C.A_P, C.A_SHIFT, C.A_BIAS0, C.A_MODE, C.A_START, C.A_BIST_CTRL, C.A_ROW_SEL]
    other = {C.A_P: 3, C.A_SHIFT: 9, C.A_BIAS0: 77, C.A_MODE: C.M_LINK_EN | C.M_TX_SILENCE, C.A_START: 5,
             C.A_BIST_CTRL: 1, C.A_ROW_SEL: 5}

    def unchanged(b, mode):
        return (b.rd(C.A_P) == 7 and b.rd(C.A_SHIFT) == 0 and b.rd(C.A_BIAS0) == 0 and b.rd(C.A_MODE) == mode
                and b.rd(C.A_ROW_SEL) == 0 and b.rd(C.A_STATUS) >> 4 & 1 == 1)
    # 1. A frame stream at exactly the minimum spacing at P = 8: the chain is never free, so every
    #    write from either master is refused, and every frame still comes back right.
    b = Bench()
    b.start(w, p=8)
    vecs = [rng.integers(0, 256, 32) for _ in range(200)]
    send(b, [link_frame(i & 63, v, 8) for i, v in enumerate(vecs)], 75)
    b.run(150)
    i = 0
    while len(b.stream) > 400:
        r = regs[i % len(regs)]
        if i % 3 == 2:
            b.jtag_write(r, other[r])
        elif i % 5 == 4:
            b.spi([0x80 | (C.A_WEIGHTS if i % 2 else C.A_ACT)])
        else:
            b.wr(r, other[r])
        b.run(int(rng.integers(0, 9)))
        i += 1
    b.wait(lambda: not b.stream, what="the stream")
    b.run(200)
    ok &= len(b.rx.frames) == 200 and all(f["vals"] == reference(w, vecs[k]) for k, f in enumerate(b.rx.frames))
    ok &= unchanged(b, C.M_LINK_EN) and b.rd(C.A_CNT_OVR) == 0
    # 2. P = 1, 26 frames one cycle faster than the rule (they all fit, section 13 row 7): results back
    #    up behind the transmitter, so vectors wait loaded and results wait. A write may be taken in
    #    a gap, so each writes what is already there.
    same = {C.A_P: 0, C.A_SHIFT: 0, C.A_BIAS0: 0, C.A_MODE: C.M_LINK_EN, C.A_BIST_CTRL: 0, C.A_ROW_SEL: 0}
    names = list(same) + [C.A_WEIGHTS, C.A_ACT]
    for burst in range(16):
        b = Bench()
        b.start(w, p=1)
        vecs = [rng.integers(0, 2, 32) for _ in range(26)]
        send(b, [link_frame(i & 63, v, 1) for i, v in enumerate(vecs)], 21)
        b.run(120)
        i = burst
        while len(b.stream) > 140:
            r = names[i % len(names)]
            if r in (C.A_WEIGHTS, C.A_ACT):
                b.spi([0x80 | r])
            elif burst % 2:
                b.wr(r, same[r])
            else:
                b.jtag_write(r, same[r])
            b.run(int(rng.integers(0, 5)))
            i += 1
        b.wait(lambda: not b.stream, what="the stream")
        b.run(400)
        ok &= len(b.rx.frames) == 26 and all(f["vals"] == reference(w, vecs[k]) for k, f in enumerate(b.rx.frames))
    # 2b. P = 1 frames back to back: the chain is never free in the middle of the stream (vectors wait
    #    loaded behind waiting results), so every write there is refused, and carries a value that
    #    would show; frames are dropped and counted, and every one that returns is right.
    for burst in range(24):
        b = Bench()
        b.start(w, p=1)
        rows0 = list(b.chip.w_mem)
        vecs = [rng.integers(0, 2, 32) for _ in range(40)]
        send(b, [link_frame(i, v, 1) for i, v in enumerate(vecs)], 13)
        b.run(40)
        i = burst
        while len(b.stream) > 80:
            r = (regs + [C.A_WEIGHTS, C.A_ACT])[i % 9]
            if (burst % 3 == 0 or i < burst + 2) and r != C.A_ACT:
                b.jtag_write(r, other.get(r, 0x0F0F0F0F))
            elif r in (C.A_WEIGHTS, C.A_ACT):
                b.spi([0x80 | r])
            else:
                b.wr(r, other[r])
            i += 1
        b.wait(lambda: not b.stream, what="the stream")
        b.run(400)
        back = [f for f in b.rx.frames]
        ok &= all(f["vals"] == reference(w, vecs[f["seq"]]) for f in back) and len(back) + b.rd(C.A_CNT_OVR) == 40
        ok &= b.chip.w_mem == rows0 and b.rd(C.A_P) == 0 and b.rd(C.A_SHIFT) == 0 and b.rd(C.A_MODE) == C.M_LINK_EN
        ok &= b.rd(C.A_ROW_SEL) == 0 and b.rd(C.A_STATUS) >> 4 & 1 == 1
    # 3. JTAG writes during a slow SPI weight burst, then during a slow SPI ACT burst: all refused,
    #    and each burst lands whole.
    b = Bench()
    b.start(w, p=8, mode=0)
    b.spi([0x80 | C.A_WEIGHTS] + weight_bytes(w2), period=8 * b.T, block=False)
    b.run(40)
    for r in regs + [C.A_WEIGHTS]:
        b.jtag_write(r, other.get(r, 0x0F0F0F0F))
    b.wait(lambda: not b.chip._busy() and b.chip.cs_n and b.sim.t > b._spi_free, what="the burst")
    want_rows = [sum((int(w2[r, j]) & 0xFF) << (8 * j) for j in range(4)) for r in range(32)]
    ok &= b.chip.w_mem == want_rows and unchanged(b, 0) and b.rd(C.A_BIST_STAT) == 0b1111
    b.wr(C.A_MODE, C.M_ACT_SPI | C.M_TX_SILENCE)
    b.wr(C.A_CLEAR, 2)
    a2 = rng.integers(0, 256, 32)
    b.spi([0x80 | C.A_ACT] + act_bytes(a2, 8), period=4 * b.T, block=False)
    b.run(60)
    for r in (C.A_ACT, C.A_P, C.A_START, C.A_MODE):
        b.jtag_write(r, {C.A_ACT: 0xFFFFFFFF, C.A_P: 3, C.A_START: 5, C.A_MODE: C.M_ACT_SPI}[r])
    b.wait(lambda: not b.chip._busy() and b.chip.cs_n and b.sim.t > b._spi_free, what="the ACT burst")
    b.wr(C.A_START, 1)
    b.wait(lambda: not b.chip._busy(), what="the vector")
    ok &= b.results() == reference(w2, a2) and unchanged(b, C.M_ACT_SPI | C.M_TX_SILENCE)
    # 4. Each write as the first after reset, from JTAG, while the memory test writes its rows: it
    #    stops the test and is carried out. Then SPI bursts started the same way.
    for k, r in enumerate(regs + [C.A_WEIGHTS]):
        b = Bench()
        b.reset()
        b.run(30 + 7 * k)
        b.jtag_reset()
        b.jtag_write(r, {C.A_MODE: C.M_LINK_EN}.get(r, 0))
        b.run(20)
        ok &= b.chip.mb_state == C.B_ABORT and b.rd(C.A_STATUS) >> 4 & 1 == 0
    for k, cmd in enumerate((C.A_WEIGHTS, C.A_ACT, C.A_WEIGHTS, C.A_ACT)):
        b = Bench()
        b.reset()
        b.run(25 + 9 * k)
        b.spi([0x80 | cmd])
        b.run(20)
        ok &= b.chip.mb_state == C.B_ABORT
    # 5. SPI writes landing while JTAG activations shift in, or while a JTAG row write is under way.
    for r in regs + [C.A_WEIGHTS, C.A_ACT]:
        for how, offs in (("act", range(150, 245, 3)), ("row", range(150, 215))):
            for off in offs:
                b = Bench()
                b.start(None, p=8, mode=C.M_ACT_SPI | C.M_TX_SILENCE)
                b.jtag_reset()
                if r in (C.A_WEIGHTS, C.A_ACT):
                    tx = [0x80 | r]
                else:
                    v = {C.A_MODE: C.M_ACT_SPI | C.M_TX_SILENCE, C.A_P: 7}.get(r, 0)
                    n = C.REG_BYTES[r]
                    tx = [0x80 | r] + [(v >> (8 * (n - 1 - i))) & 0xFF for i in range(n)]
                b.spi(tx, offset=off * b.T, block=False)
                b.jtag_write(C.A_ACT, 0x12345678) if how == "act" else b.jtag_write(C.A_WEIGHTS, 0x0F0F0F0F)
                b.run(80)
                ok &= not b.chip.obs["wc_collisions"] and not b.chip.obs["act_overrun"]
    # 6. JTAG writes while an SPI ACT burst at SCLK = CLK keeps activations shifting all the time.
    for r in regs + [C.A_WEIGHTS, C.A_ACT]:
        b = Bench()
        b.start(w, p=8, mode=C.M_ACT_SPI | C.M_TX_SILENCE)
        a3 = rng.integers(0, 256, 32)
        b.spi([0x80 | C.A_ACT] + act_bytes(a3, 8), block=False)
        b.jtag_reset()
        b.jtag_write(r, {C.A_MODE: C.M_ACT_SPI, C.A_P: 3, C.A_START: 5, C.A_ACT: 0xFFFFFFFF}.get(r, 0x0F0F0F0F))
        b.wait(lambda: not b.chip._busy() and b.chip.cs_n and b.sim.t > b._spi_free, what="the ACT burst")
        b.wr(C.A_START, 1)
        b.wait(lambda: not b.chip._busy(), what="the vector")
        ok &= b.results() == reference(w, a3) and b.rd(C.A_MODE) == C.M_ACT_SPI | C.M_TX_SILENCE and b.rd(C.A_P) == 7
    # 7. ACT over JTAG (it needs act_spi, so vectors come from START): landing on the edge after a
    #    START, or while a second START's result waits behind the first one's return frame, or in a
    #    row write of an SPI weight burst. Each lands somewhere in a sweep of one cycle steps.
    for x in range(150, 200):
        b = Bench()
        b.start(w, p=8, mode=C.M_ACT_SPI)
        b.jtag_reset()
        b.spi([0x80 | C.A_START, 1], offset=x * b.T, block=False)
        b.spi([0x80 | C.A_START, 2], block=False)
        b.jtag_write(C.A_ACT, 0xFFFFFFFF)
        b.run(100)
        ok &= not b.chip.obs["act_overrun"] and not b.chip.obs["wc_collisions"]
    for k in range(32):
        b = Bench()
        b.start(w, p=8, mode=C.M_ACT_SPI | C.M_TX_SILENCE)
        b.spi([0x80 | C.A_WEIGHTS] + weight_bytes(w2), block=False)
        b.run(40 + k)
        b.jtag_reset()
        b.jtag_write(C.A_ACT, 0xFFFFFFFF)
        b.wait(lambda: not b.chip._busy() and b.chip.cs_n and b.sim.t > b._spi_free, what="the burst")
        ok &= b.chip.w_mem == [sum((int(w2[r, j]) & 0xFF) << (8 * j) for j in range(4)) for r in range(32)]
        ok &= not b.chip.obs["act_overrun"] and not b.chip.obs["wc_collisions"]
    # 8. Every guarded register from each master, landed on 30 consecutive cycles in the middle of a
    #    back-to-back P = 1 stream (its pattern repeats every 22 cycles, the return frame): so each
    #    lands at least once while a vector is loading, loaded, computing, and while a result waits.
    #    The chain is never free there, so each write is refused and flagged.
    zeros = np.zeros(32, dtype=int)
    for r in regs + [C.A_WEIGHTS, C.A_ACT]:
        for master in ("SPI", "JTAG"):
            if master == "JTAG" and r == C.A_ACT:
                continue                                    # needs act_spi, which stops link frames
            for off in range(30):
                b = Bench()
                b.start(None, p=1)
                send(b, [link_frame(i, zeros, 1) for i in range(30)], 13)
                if master == "SPI":
                    if r in (C.A_WEIGHTS, C.A_ACT):
                        tx = [0x80 | r]
                    else:
                        n = C.REG_BYTES[r]
                        tx = [0x80 | r] + [(other[r] >> (8 * (n - 1 - i))) & 0xFF for i in range(n)]
                    b.spi(tx, offset=(150 + off) * b.T, block=False)
                else:
                    b.run(off)
                    b.jtag_reset()
                    b.jtag_write(r, other.get(r, 0x0F0F0F0F))
                b.wait(lambda: not b.stream, what="the stream")
                b.run(100)
                ok &= b.rd(C.A_STATUS) >> 4 & 1 == 1 and b.rd(C.A_P) == 0 and b.rd(C.A_SHIFT) == 0
    check("guarded writes from both masters while the chip is busy for each reason: refused and flagged, and nothing "
          "they meet is disturbed", ok)


def reference_rx(syms: list[int], n: int) -> dict:
    """Section 4's receiver, written from the text alone, for a stream in which every sync is false:
    hunt for 0xA; two header symbols; a type other than 0 is bad; n payload symbols and two CRC
    symbols; a CRC failure or a bad type waits for 72 idle symbols in a row."""
    out = {"starts": 0, "bad": 0, "crc": 0, "comp": 0}
    i = 0
    while i < len(syms):
        if syms[i] != C.SYNC_IN:
            i += 1
            continue
        out["starts"] += 1
        hdr = syms[i + 1:i + 3]
        i += 3
        if hdr[0] >> 2:
            out["bad"] += 1
        else:
            got = (syms[i + n] << 4) | syms[i + n + 1]
            body = hdr + syms[i:i + n]
            i += n + 2
            if crc8(body) == got:
                out["comp"] += 1
                continue
            out["crc"] += 1
        run = 0
        while i < len(syms) and run < 72:
            run = run + 1 if syms[i] == 0 else 0
            i += 1
    return out


def wilson(k: int, n: int, z: float = 3.29) -> tuple[float, float]:
    """Confidence interval for a proportion k of n (z = 3.29: 99.9%)."""
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / (1 + z * z / n)
    return c - h, c + h


def s_sync() -> None:
    print("a corrupted sync symbol (section 4's known weakness), against a reference receiver")
    rng = np.random.default_rng(20)
    w = rand_w(rng)
    b = Bench()
    b.start(w, p=8)
    trials, batch, gap = 1500, 100, 160                    # gap: a late false start, then its recovery wait
    tot = {"starts": 0, "bad": 0, "crc": 0, "comp": 0}
    exact = True
    for _ in range(trials // batch):
        syms = []
        for _ in range(batch):
            f = link_frame(int(rng.integers(0, 64)), rng.integers(0, 256, 32), 8)
            f[0] = int(rng.choice([s for s in range(16) if s != C.SYNC_IN]))
            syms += f + [0] * gap
        want = reference_rx(syms, 64)
        n0 = len(b.rx.frames)
        b.stream.extend(syms)
        b.wait(lambda: not b.stream, what="the stream")
        b.run(200)
        got = {"bad": b.rd(C.A_CNT_BAD), "crc": b.rd(C.A_CNT_CRC), "comp": len(b.rx.frames) - n0}
        exact &= got == {k: want[k] for k in got} and b.rd(C.A_CNT_OVR) == 0
        b.wr(C.A_CLEAR, 1)
        for k in tot:
            tot[k] += want[k]
    MEASURED["corrupted sync: false starts, bad type, CRC failures, garbage computes"] = (
        f"{tot['starts']}, {tot['bad']}, {tot['crc']}, {tot['comp']} of {trials} frames")
    check("a corrupted sync: the chip ends every false frame as the reference receiver does (bad type, CRC "
          "failure, or a compute), batch by batch", exact and tot["starts"] > 0.95 * trials, str(tot))

    # The rate at which a type-0 false frame passes the CRC, over many more random bodies than the
    # chip run can afford, through the same CRC (which the chip matches, scenario errors).
    table = np.array([[crc8_symbol(c, s) for s in range(16)] for c in range(256)], dtype=np.int64)
    n = 400_000
    body = rng.integers(0, 16, (n, 66))
    body[:, 0] &= 3                                         # type 0
    crc = np.full(n, CRC_INIT, dtype=np.int64)
    for i in range(66):
        crc = table[crc, body[:, i]]
    sent = rng.integers(0, 256, n)
    k = int((crc == sent).sum())
    lo, hi = wilson(k, n)
    MEASURED["random type-0 frame bodies passing the CRC"] = f"{k} of {n:,} (1 in {n / max(k, 1):.0f})"
    check("a random type-0 false frame passes the CRC 1 time in 256 (99.9% interval)", lo <= 1 / 256 <= hi,
          f"{k} of {n:,}")


SCENARIOS = {"image": s_image, "selftest": s_selftest, "spi": s_spi, "link": s_link, "period": s_period, "cdc": s_cdc,
             "errors": s_errors, "requant": s_requant, "rules": s_rules, "nolink": s_nolink,
             "workload": s_workload, "recover": s_recover, "linkup": s_linkup, "status": s_status,
             "modes": s_modes, "jtagx": s_jtagx, "robust": s_robust, "regs": s_regs,
             "reset": s_reset, "tap": s_tap, "sync": s_sync, "cover": s_cover, "kws": s_kws}


def main() -> int:
    names = sys.argv[1:] or [n for n in SCENARIOS if n != "image"] + ["image"]
    t0 = time.time()
    for name in names:
        SCENARIOS[name]()
    print("\nmeasured:")
    for k, v in MEASURED.items():
        print(f"  {k}: {v}")
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)} of {len(RESULTS)} checks passed in {time.time() - t0:.0f} s")
    for name, _, detail in failed:
        print(f"  FAILED: {name}" + (f" ({detail})" if detail else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
