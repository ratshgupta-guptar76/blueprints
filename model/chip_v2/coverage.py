"""Functional coverage (docs/V2_VERIFICATION_PLAN.md section 5), collected on the model.

    python3 -m model.chip_v2.verify coverage [N]    the scenarios and N random seeds of each kind,
                                                    with every bench watched; writes the bins missed

A collector watches one chip from outside, as trace.record does: it wraps the chip's
edge methods and a few of its internal steps, and reads only state the spec names. It
never changes what the chip does. The bins are built from the spec's values, so a bin
nobody can hit shows up as missing; IMPOSSIBLE lists the ones that are missing by
design, each with its reason.
"""
from __future__ import annotations

from . import chip as C
from .fpga import PS

STATES = ["hunt", "header 1", "header 2", "payload", "CRC 1", "CRC 2", "skip", "recover"]
GUARDED = ["P", "SHIFT", "BIAS", "MODE", "WEIGHTS", "ACT", "START", "BIST_CTRL", "ROW_SEL"]
GNAME = {C.A_P: "P", C.A_SHIFT: "SHIFT", 5: "BIAS", 6: "BIAS", 7: "BIAS", 8: "BIAS", C.A_MODE: "MODE",
         C.A_WEIGHTS: "WEIGHTS", C.A_ACT: "ACT", C.A_START: "START", C.A_BIST_CTRL: "BIST_CTRL",
         C.A_ROW_SEL: "ROW_SEL"}
CAUSES = ["none", "loading", "loaded", "computing", "result waiting", "burst", "row write", "self-test",
          "activations shifting"]
TAP = ["Test-Logic-Reset", "Run-Test/Idle", "Select-DR", "Capture-DR", "Shift-DR", "Exit1-DR", "Pause-DR",
       "Exit2-DR", "Update-DR", "Select-IR", "Capture-IR", "Shift-IR", "Exit1-IR", "Pause-IR", "Exit2-IR",
       "Update-IR"]
STATUS_MODES = ["low", "heartbeat", "high", "DONE"]


def bist_phase(chip) -> str | None:
    """Whether a running self-test is writing or reading, from where its generator stands:
    inside a row write or a row read (memory test), or before or after the compute test
    starts its vectors."""
    g, last, names = chip.bist, None, []
    while g is not None:
        names.append(g.gi_code.co_name)
        last = g
        nxt = g.gi_yieldfrom
        if nxt is None and g.gi_frame is not None:
            nxt = g.gi_frame.f_locals.get("test")     # _timed steps its test by hand
        g = nxt if hasattr(nxt, "gi_code") else None
    if "_wr" in names:
        return "write"
    if "_rd" in names:
        return "read"
    if names and names[-1] == "_cbist" and last.gi_frame is not None:
        return "read" if "sig" in last.gi_frame.f_locals else "write"
    return None


def min_period(p: int, requant: bool, silent: bool) -> int:
    """Section 11 rule 2, in CLK cycles between the first payload symbols of two frames."""
    if p == 1:
        return 13 if silent else 16 if requant else 22
    return 67 + p


def bins() -> dict[str, set]:
    b = {
        "FC-01 frame outcome": {(p, r, o) for p in range(1, 9) for r in ("raw", "requantized", "silent")
                                for o in ("accepted", "overrun", "CRC fail")},
        "FC-02 frame type": {0, 1, 2, 3},
        "FC-03 frame spacing": {(p, s) for p in range(1, 9)
                                for s in ("minimum", "minimum + 1", "one too close", "back to back")},
        "FC-04 receiver interrupted": {(s, c) for s in STATES for c in ("link off", "act_spi", "CLEAR bit 2", "reset")},
        "FC-05 guarded write": {(r, m, c) for r in GUARDED for m in ("SPI", "JTAG") for c in CAUSES},
        "FC-06 same-edge race": {(r, w) for r in ("MODE", "P", "START", "WEIGHTS") for w in ("a cycle early", "same edge",
                                                                                          "a cycle late")},
        "FC-07 every register": {(a, rw, m) for a in range(128) for rw in ("read", "write") for m in ("SPI", "JTAG")},
        "FC-08 SPI cut short": set(range(1, 17)) | {"mid-row in a burst"},
        "FC-09 clock ratio": {("LINK_CLK", r) for r in ("1.0", "just above 1", "1.1 to 2", "above 2")}
        | {("SCLK", r) for r in ("1.0", "just above 1", "1.1 to 2", "above 2")}
        | {("TCK", r) for r in ("4", "4 to 8", "above 8")},
        "FC-10 crossing alignment": {(x, e) for x in ("X1", "X2", "X4", "X5") for e in list(range(8)) + ["metastable"]},
        "FC-11 link state": {"Down to Up", "Up to Closing", "Closing to Down", "enable written during Closing",
                             "LINK_CLK stopped during Closing"},
        "FC-12 write controller": {(k, s) for k in ("request", "abort") for s in ("idle", "set up", "enable", "hold")},
        "FC-13 self-test": {(t, o) for t in ("memory", "compute")
                            for o in ("pass", "fail", "aborted in write phase", "aborted in read phase", "timed out")},
        "FC-14 STATUS pin": set(STATUS_MODES) | {("low", "heartbeat"), ("low", "high"), ("low", "DONE"),
                                                 ("heartbeat", "DONE"), ("high", "DONE")},
        "FC-15 requantize": {(t, s, bs) for t in ("negative", "zero", "in range", "above 255")
                             for s in ("0", "1 to 14", "15") for bs in ("negative bias", "bias 0 or more")},
        "FC-16 results": {(j, e, p) for j in range(4) for e in ("most positive", "most negative") for p in range(1, 9)},
        "FC-17 counters": {(n, v) for n in ("CNT_CRC", "CNT_OVERRUN", "CNT_BAD") for v in ("0", "1", "254", "255",
                                                                                        "held at 255")},
        "FC-18 TAP": {(TAP[s], m) for s in range(16) for m in (0, 1)} | {f"IR {i:03b}" for i in range(8)},
        "FC-19 JTAG and SPI tie": {"JTAG a cycle before", "JTAG on the same cycle", "JTAG a cycle after"},
    }
    return b


# Bins that cannot be hit, by design. Each reason can be checked against the spec.
IMPOSSIBLE: dict[str, dict] = {
    "FC-05 guarded write": {
        **{(r, "SPI", "burst"): "SPI cannot write during its own burst: the burst ends when chip select rises, and "
           "the next write is checked at least 8 CLK later (sections 3 and 11 rule 11)" for r in GUARDED},
        **{(r, "SPI", "self-test"): "the command byte stops the self-test 8 or more CLK before a register's data "
           "byte is checked (sections 5 and 9)" for r in ("P", "SHIFT", "BIAS", "MODE", "START", "BIST_CTRL", "ROW_SEL")},
        ("ACT", "JTAG", "loading"): "ACT over JTAG needs act_spi, and with act_spi no frame loads (section 8)",
        ("ACT", "JTAG", "self-test"): "ACT over JTAG needs act_spi, and the MODE write that sets it stops the "
                                      "self-test (sections 8 and 9)",
    },
    "FC-03 frame spacing": {
        (2, "one too close"): "at P = 2 the minimum spacing, 69, is the frame's own length: one cycle less would "
                              "overlap two frames (sections 4 and 11 rule 2)"},
    "FC-15 requantize": {
        ("above 255", "15", s): "r + bias is at most 32 x 127 x 255 + 2^20 - 1 = 2,084,895, so shifted by 15 it "
        "is at most 63 (section 6)" for s in ("negative bias", "bias 0 or more")},
    "FC-04 receiver interrupted": {
        **{(s, "CLEAR bit 2"): "CLEAR bit 2 acts only while a vector is loading, when the receiver is in "
           "payload or CRC (section 8)" for s in ("hunt", "header 1", "header 2", "skip", "recover")},
        **{(s, c): "a vector is loading, so the chip is busy and the MODE write that would do this is refused "
           "(section 5)" for s in ("payload", "CRC 1", "CRC 2") for c in ("link off", "act_spi")},
    },
}


class Coverage:
    def __init__(self):
        self.all = bins()
        self.hit: dict[str, set] = {k: set() for k in self.all}
        self.benches = 0

    def add(self, point: str, value) -> None:
        self.hit[point].add(value)

    def report(self) -> tuple[int, int, dict]:
        hit = total = 0
        missing = {}
        for k, allb in self.all.items():
            imp = IMPOSSIBLE.get(k, {})
            got = self.hit[k] & allb
            want = allb - set(imp)
            hit += len(got & want)
            total += len(want)
            miss = sorted(want - got, key=str)
            if miss:
                missing[k] = miss
        return hit, total, missing


class _Watch:
    """Everything one bench's chip does, sorted into bins."""

    def __init__(self, cov: Coverage, b: Bench):
        self.cov, self.b, self.c = cov, b, b.chip
        c = self.c
        self.master = None
        self.last_read_end = False          # the previous FIFO read finished a frame (or a skip)
        self.last_start = None              # (cycle, P, requant, silent) of the last first-payload symbol
        self.guards: list[tuple[int, str]] = []
        self.starts: list[int] = []
        self.spi_bytes: list[int] = []
        self.jtag_writes: list[int] = []
        self.status_mode = None
        self.result_obj = c.result
        self.t_prev = {}
        self.spi_bits = 0
        self.spi_first = 0
        self.snap = None
        self.aborting = False
        self.period = {}
        for name in ("clk_rise", "set_rst_n", "spi_cs", "spi_rise", "tck_rise", "link_rise", "_guard", "_spi_byte",
                     "_jtag_request", "_write_row", "_abort_bist", "_reg_write"):
            setattr(c, name, getattr(self, "w" + name)(getattr(c, name)))
        b.link.on_rise = c.link_rise        # the clock holds the method it was built with

    # ---------------------------------------------------------- helpers
    def add(self, point, value):
        self.cov.add(point, value)

    def ratio(self, which: str, t: int) -> None:
        """Classify a clock's period once two intervals in a row agree (a steady clock, not a gap)."""
        prev = self.t_prev.get(which)
        self.t_prev[which] = t
        if prev is None:
            return
        dt, last = t - prev, self.period.get(which)
        self.period[which] = dt
        if dt != last:
            return
        r = dt / self.b.T
        if which == "TCK":
            k = "4" if abs(r - 4) < 1e-9 else "4 to 8" if 4 < r <= 8 else "above 8" if r > 8 else None
        else:
            k = ("1.0" if abs(r - 1) < 1e-9 else "just above 1" if 1 < r < 1.1 else "1.1 to 2" if 1.1 <= r <= 2
                 else "above 2" if r > 2 else None)
        if k:
            self.add("FC-09 clock ratio", (which, k))

    def align(self, x: str) -> None:
        T, t = self.b.T, self.b.sim.t
        ph = t % T                          # CLK rises at whole multiples of its period
        self.add("FC-10 crossing alignment", (x, ph * 8 // T))
        if min(ph, T - ph) < 2 * PS:
            self.add("FC-10 crossing alignment", (x, "metastable"))

    def kind(self) -> str:
        m = self.c.mode
        return "silent" if m & C.M_TX_SILENCE else "requantized" if m & C.M_REQUANT else "raw"

    def causes(self, s) -> list[str]:
        out = [n for n, v in (("loading", s["chain"] == C.LOADING or self.c.rx_started),
                              ("loaded", s["chain"] == C.LOADED), ("computing", s["chain"] == C.COMPUTING),
                              ("result waiting", s["acc_valid"]), ("burst", s["burst"]),
                              ("row write", s["wc"] != 0 or s["pending"] or s["row_rd"]),
                              ("self-test", s["bist"]), ("activations shifting", s["act_cnt"] > 0)) if v]
        return out or ["none"]

    def status_of(self) -> str:
        c = self.c
        if c.touched:
            return "DONE"
        if not c.selftest_done:
            return "low"
        return "heartbeat" if c.selftest_ok else "high"

    # ---------------------------------------------------------- wrappers
    def wclk_rise(self, fn):
        def call():
            c = self.c
            if not c.rst_n or c.core_rst < 2:
                return fn()
            s = self.snap = {"rx": c.rx, "lnk": c.lnk, "mode": c.mode, "chain": c.chain, "acc_valid": c.acc_valid,
                             "bist": c.bist is not None, "burst": c.burst, "wc": c.wc,
                             "pending": c.wc_pending is not None, "act_cnt": c.act_cnt, "row_rd": c.row_rd,
                             "rptr": c.rptr, "rx_left": c.rx_left, "cnt": (c.cnt_crc, c.cnt_ovr, c.cnt_bad),
                             "mb": c.mb_state, "cb": c.cb_state, "p_reg": c.p_reg}
            fn()
            self.after_edge(s)
        return call

    def after_edge(self, s) -> None:
        c, add = self.c, self.add
        read = c.rptr != s["rptr"] and s["lnk"] == C.L_UP
        rx0 = s["rx"]
        if read:
            if rx0 == C.HDR2:
                add("FC-02 frame type", c.rx_hdr >> 6)
            first = rx0 == C.PAYLOAD and s["rx_left"] == 0
            if first:
                p = c.chain_p if c.rx_started else c.p_reg
                req, sil = bool(c.mode & C.M_REQUANT), bool(c.mode & C.M_TX_SILENCE)
                self.starts.append(c.cyc)          # accepted or dropped, the frame's first payload symbol
                if c.rx == C.SKIP:
                    add("FC-01 frame outcome", (c.p_reg, self.kind(), "overrun"))
                if self.last_start is not None:
                    d = c.cyc - self.last_start
                    mp = min_period(p, req, sil)
                    sp = {mp: "minimum", mp + 1: "minimum + 1", mp - 1: "one too close"}.get(d)
                    if sp:
                        add("FC-03 frame spacing", (p, sp))
                self.last_start = c.cyc
            if rx0 == C.CRC2:
                if c.chain == C.LOADED:
                    add("FC-01 frame outcome", (c.chain_p, self.kind(), "accepted"))
                elif c.rx == C.RECOVER:
                    add("FC-01 frame outcome", (c.chain_p, self.kind(), "CRC fail"))
            if rx0 == C.HUNT and c.rx == C.HDR1 and self.last_read_end:
                add("FC-03 frame spacing", (c.p_reg, "back to back"))
            self.last_read_end = rx0 == C.CRC2 or (rx0 == C.SKIP and c.rx == C.HUNT)
            if c.mode & C.M_ACT_SPI and not s["mode"] & C.M_ACT_SPI or c.mode & C.M_ACT_SPI and rx0 != C.HUNT:
                add("FC-04 receiver interrupted", (STATES[rx0], "act_spi"))
        if s["lnk"] == C.L_UP and c.lnk == C.L_CLOSING:
            add("FC-04 receiver interrupted", (STATES[rx0], "link off"))
            add("FC-11 link state", "Up to Closing")
        if s["lnk"] == C.L_DOWN and c.lnk == C.L_UP:
            add("FC-11 link state", "Down to Up")
        if s["lnk"] == C.L_CLOSING and c.lnk == C.L_DOWN:
            add("FC-11 link state", "Closing to Down")
        if c.lnk == C.L_CLOSING:
            if c.mode & C.M_LINK_EN and not s["mode"] & C.M_LINK_EN:
                add("FC-11 link state", "enable written during Closing")
            if not self.b.link.running:
                add("FC-11 link state", "LINK_CLK stopped during Closing")
        # counters, and a count attempted at 255
        events = [read and s["rx"] == C.CRC2 and c.rx == C.RECOVER,
                  read and s["rx"] == C.PAYLOAD and s["rx_left"] == 0 and c.rx == C.SKIP,
                  read and s["rx"] == C.HDR2 and c.rx_hdr >> 6 != 0]
        for name, v, v0, ev in zip(("CNT_CRC", "CNT_OVERRUN", "CNT_BAD"), (c.cnt_crc, c.cnt_ovr, c.cnt_bad),
                                   s["cnt"], events):
            if v in (0, 1, 254, 255):
                add("FC-17 counters", (name, str(v)))
            if ev and v0 == 255:
                add("FC-17 counters", (name, "held at 255"))
        # self-test outcomes
        for t, k0, k in (("memory", s["mb"], c.mb_state), ("compute", s["cb"], c.cb_state)):
            if k0 == C.B_RUN and k == C.B_PASS:
                add("FC-13 self-test", (t, "pass"))
            elif k0 == C.B_RUN and k == C.B_FAIL:
                add("FC-13 self-test", (t, "fail"))
            elif k0 == C.B_RUN and k == C.B_ABORT and not self.aborting:
                add("FC-13 self-test", (t, "timed out"))
        self.aborting = False
        # STATUS pin
        m = self.status_of()
        self.add("FC-14 STATUS pin", m)
        if self.status_mode is not None and m != self.status_mode:
            self.add("FC-14 STATUS pin", (self.status_mode, m))
        self.status_mode = m
        # capture: the result register is replaced by a new list
        if c.result is not self.result_obj:
            self.result_obj = c.result
            p = c.acc_p
            hi, lo = 32 * 127 * ((1 << p) - 1), -32 * 128 * ((1 << p) - 1)
            for j, r in enumerate(c.result):
                if r == hi:
                    add("FC-16 results", (j, "most positive", p))
                if r == lo:
                    add("FC-16 results", (j, "most negative", p))
                if c.mode & C.M_REQUANT and not c.mode & C.M_TX_SILENCE:
                    t = r + c.bias[j]
                    tc = ("negative" if t < 0 else "zero" if t == 0 else
                          "above 255" if t >> c.shift > 255 else "in range")
                    sc = "0" if c.shift == 0 else "15" if c.shift == 15 else "1 to 14"
                    add("FC-15 requantize", (tc, sc, "negative bias" if c.bias[j] < 0 else "bias 0 or more"))

    def wset_rst_n(self, fn):
        def call(v):
            c = self.c
            if not v and c.rst_n and c.core_rst >= 2:
                self.add("FC-04 receiver interrupted", (STATES[c.rx], "reset"))
            if not v:
                self.status_mode = None
                self.last_start = None
                self.last_read_end = False
            return fn(v)
        return call

    def wspi_cs(self, fn):
        def call(v):
            c = self.c
            if v != c.cs_n:
                self.align("X5")
            if v and not c.cs_n:
                k = self.spi_bits
                if 1 <= k <= 16:
                    self.add("FC-08 SPI cut short", k)
                if self.spi_first == 0x80 | C.A_WEIGHTS and k > 8 and (k - 8) % 32:
                    self.add("FC-08 SPI cut short", "mid-row in a burst")
            if not v:
                self.spi_bits = self.spi_first = 0
                self.t_prev.pop("SCLK", None)
                self.period.pop("SCLK", None)
            return fn(v)
        return call

    def wspi_rise(self, fn):
        def call():
            c = self.c
            live = c.rst_n and not c.cs_n
            if live:
                self.ratio("SCLK", self.b.sim.t)
                if self.spi_bits < 8:
                    self.spi_first = (self.spi_first << 1) | c.mosi
                self.spi_bits += 1
            before = c.s_bit
            fn()
            if live and before == 7:
                self.align("X2")
        return call

    def wtck_rise(self, fn):
        def call():
            c = self.c
            if c.rst_n:
                self.ratio("TCK", self.b.sim.t)
                self.add("FC-18 TAP", (TAP[c.tap], c.tms))
            fn()
            if c.rst_n and c.tap == C.UPD_IR:
                self.add("FC-18 TAP", f"IR {c.ir:03b}")
            if c.rst_n and c.tap == C.UPD_DR and c.ir in (C.IR_DEBUG, C.IR_MBIST, C.IR_CBIST):
                self.align("X4")
        return call

    def wlink_rise(self, fn):
        def call():
            if self.c.rst_n and self.c.l_en_s2:
                self.ratio("LINK_CLK", self.b.sim.t)
                self.align("X1")
            fn()
        return call

    def w_guard(self, fn):
        def call(addr, busy):
            if addr in GNAME and self.snap is not None:
                for cause in self.causes(self.snap):
                    self.add("FC-05 guarded write", (GNAME[addr], self.master, cause))
                if GNAME[addr] in ("MODE", "P", "START", "WEIGHTS"):
                    self.guards.append((self.c.cyc, GNAME[addr]))
            return fn(addr, busy)
        return call

    def w_spi_byte(self, fn):
        def call(first, byte, busy):
            c = self.c
            if first:
                self.add("FC-07 every register", (byte & 0x7F, "write" if byte >> 7 else "read", "SPI"))
            if (first and byte >> 7) or (not first and c.s_cmd is not None and c.s_cmd >> 7):
                self.spi_bytes.append(c.cyc)
            self.master = "SPI"
            return fn(first, byte, busy)
        return call

    def w_jtag_request(self, fn):
        def call(req, busy, spi_evt):
            kind, word = req >> 40, req & 0xFFFFFFFFFF
            if kind == C.J_DEBUG:
                self.add("FC-07 every register", ((word >> 32) & 0x7F, "write" if word >> 39 else "read", "JTAG"))
                if word >> 39:
                    self.jtag_writes.append(self.c.cyc)
            self.master = "JTAG"
            return fn(req, busy, spi_evt)
        return call

    def w_write_row(self, fn):
        def call(row, data):
            c = self.c
            st = ("idle", "set up", "enable", "hold")[c.wc] if c.wc_pending is None else "busy"
            if st != "busy":
                self.add("FC-12 write controller", ("request", st))
            return fn(row, data)
        return call

    def w_abort_bist(self, fn):
        def call():
            c = self.c
            self.add("FC-12 write controller", ("abort", ("idle", "set up", "enable", "hold")[c.wc]))
            t = "memory" if c.mb_state == C.B_RUN else "compute" if c.cb_state == C.B_RUN else None
            if t:
                ph = bist_phase(c)
                if ph:
                    self.add("FC-13 self-test", (t, f"aborted in {ph} phase"))
            self.aborting = True
            return fn()
        return call

    def w_reg_write(self, fn):
        def call(addr, v):
            c = self.c
            if addr == C.A_CLEAR and v & 4 and c.chain == C.LOADING:
                self.add("FC-04 receiver interrupted", (STATES[c.rx], "CLEAR bit 2"))
            return fn(addr, v)
        return call

    # ---------------------------------------------------------- at the end of the bench
    def finish(self) -> None:
        g = sorted(self.guards)
        st = set(self.starts)
        for cyc, reg in g:
            for d, name in ((1, "a cycle early"), (0, "same edge"), (-1, "a cycle late")):
                if cyc + d in st:
                    self.add("FC-06 same-edge race", (reg, name))
        sb = set(self.spi_bytes)
        for cyc in self.jtag_writes:
            for d, name in ((1, "JTAG a cycle before"), (0, "JTAG on the same cycle"), (-1, "JTAG a cycle after")):
                if cyc + d in sb:
                    self.add("FC-19 JTAG and SPI tie", name)


def forced(name: str) -> None:
    """A self-test that never finishes, by replacing one test with a generator that only waits.
    This is forcing (plan section 5), so it lives here and never in a scenario: no trace of it
    could be replayed on RTL."""
    from .fpga import Bench
    b = Bench()

    def stall():
        while True:
            yield
    setattr(b.chip, name, stall)
    b.reset()
    b.wait(lambda: b.chip.selftest_done, limit=40_000, what="the self-test to time out")
    b.run(5)


def collect(scenarios: list[str], seeds: int = 0, quiet: bool = True, force: bool = True) -> Coverage:
    """Run the scenarios, and seeds of random legal and hostile traffic, with every bench watched."""
    import contextlib
    import io

    from . import __main__ as M
    from . import fpga
    from . import random_traffic as R
    cov = Coverage()
    watches: list[_Watch] = []
    orig = fpga.Bench.__init__

    def init(self, *a, **kw):
        orig(self, *a, **kw)
        watches.append(_Watch(cov, self))
        cov.benches += 1
    fpga.Bench.__init__ = init
    try:
        with contextlib.redirect_stdout(io.StringIO()) if quiet else contextlib.nullcontext():
            for name in scenarios:
                M.SCENARIOS[name]()
            for seed in range(seeds):
                R.run_legal(seed)
                R.run_hostile(seed)
            if force:
                forced("_mbist")
                forced("_cbist")
    finally:
        fpga.Bench.__init__ = orig
    for w in watches:
        w.finish()
    return cov
