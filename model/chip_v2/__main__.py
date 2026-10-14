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


SCENARIOS = {"image": s_image, "selftest": s_selftest, "spi": s_spi, "link": s_link, "period": s_period, "cdc": s_cdc,
             "errors": s_errors, "requant": s_requant, "rules": s_rules, "nolink": s_nolink,
             "workload": s_workload}


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
