"""Record everything that happens at the chip's pins during a bench run, and
replay it against another chip.

A trace is the list of pin events of one bench, in order: every clock edge,
every change of an input pin, and at each edge where the outside world samples
an output, the value the model had there. Replaying a trace drives a chip with
exactly those inputs and compares its outputs at exactly those points:

    LINK_TX[3:0], STATUS    just before every CLK rising edge
    SPI_MISO                just before every SPI_SCLK rising edge
    TDO                     just before every TCK rising edge

These are the instants the FPGA samples them. The chip being replayed can be a
second copy of the model (the trace must then match exactly), a deliberately
broken copy (it must not), or the RTL through cocotb (cocotb/v2/).

Nothing in fpga.py or chip.py knows about recording: record() wraps a bench
that has not run yet.
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass

from .chip import ChipV2
from .fpga import Bench
from .sim import Sim

(RST, CS, CLK_R, CLK_F, LINK_R, LINK_F, SCLK_R, SCLK_F, TCK_R, TCK_F,
 LINK_D, MOSI, TMS, TDI) = range(14)
KIND = ("RST_N", "SPI_CS_N", "CLK rise", "CLK fall", "LINK_CLK rise", "LINK_CLK fall",
        "SPI_SCLK rise", "SPI_SCLK fall", "TCK rise", "TCK fall", "LINK_D", "SPI_MOSI", "TMS", "TDI")
CLOCK_EDGES = frozenset((CLK_R, CLK_F, LINK_R, LINK_F, SCLK_R, SCLK_F, TCK_R, TCK_F))
INITIAL = {RST: 0, CS: 1, LINK_D: 0, MOSI: 0, TMS: 1, TDI: 0}      # pin levels before the first event


class Trace:
    def __init__(self, clk_period: int, label: str = ""):
        self.clk_period, self.label = clk_period, label
        self.t = array("q")
        self.kind, self.val, self.exp = bytearray(), bytearray(), bytearray()
        self.chip = None                    # the recorded chip, for what only the model can tell

    def add(self, t: int, kind: int, val: int = 0, exp: int = 0) -> None:
        self.t.append(t)
        self.kind.append(kind)
        self.val.append(val)
        self.exp.append(exp)

    def __len__(self) -> int:
        return len(self.t)

    def rows(self):
        return zip(self.t, self.kind, self.val, self.exp)

    @property
    def cycles(self) -> int:
        return self.kind.count(CLK_R)

    @property
    def has_faults(self) -> bool:
        """Cell faults were injected into the model. The RTL has no such hook."""
        return bool(self.chip is not None and (self.chip.stuck or self.chip.coupled))


def record(b: Bench, label: str = "") -> Trace:
    """Start recording a bench. Call it before the bench has run."""
    chip, sim = b.chip, b.sim
    assert sim.t == 0 and chip.cyc == 0, "attach before the bench runs"
    tr = Trace(b.T, label)
    tr.chip = chip
    pins = [chip.link_d, chip.mosi, chip.tms, chip.tdi]

    def sync() -> None:                     # log any input pin that has changed
        now = (chip.link_d, chip.mosi, chip.tms, chip.tdi)
        for i, kind in enumerate((LINK_D, MOSI, TMS, TDI)):
            if now[i] != pins[i]:
                pins[i] = now[i]
                tr.add(sim.t, kind, now[i])

    def logged(kind, fn, exp=None):
        def call(*a):
            sync()
            tr.add(sim.t, kind, a[0] if a else 0, exp() if exp else 0)
            return fn(*a)
        return call

    chip.set_rst_n = logged(RST, chip.set_rst_n)
    chip.spi_cs = logged(CS, chip.spi_cs)
    chip.clk_rise = logged(CLK_R, chip.clk_rise, lambda: chip.link_tx | chip.status << 4)
    chip.link_rise = logged(LINK_R, chip.link_rise)
    chip.spi_rise = logged(SCLK_R, chip.spi_rise, lambda: chip.miso)
    chip.spi_fall = logged(SCLK_F, chip.spi_fall)
    chip.tck_rise = logged(TCK_R, chip.tck_rise, lambda: chip.tdo)
    chip.tck_fall = logged(TCK_F, chip.tck_fall)
    b.clk.on_fall = logged(CLK_F, lambda: None)
    b.link.on_rise = chip.link_rise         # the clock holds the method it was built with
    b.link.on_fall = logged(LINK_F, b.link.on_fall)

    at = sim.at

    def at_then_sync(t, fn):                # an input pin changed by any scheduled call is logged
        def run():
            fn()
            sync()
        at(t, run)
    sim.at = at_then_sync
    return tr


@dataclass
class Mismatch:
    index: int
    t: int
    pin: str
    want: int
    got: int

    def __str__(self) -> str:
        return f"event {self.index} at {self.t / 1000:.3f} ns: {self.pin} is {self.got:#x}, the model had {self.want:#x}"


def replay(tr: Trace, chip_cls=ChipV2, stop_after: int = 1) -> list[Mismatch]:
    """Drive a fresh chip of class chip_cls with the trace's inputs and compare
    its outputs with the recorded ones. Returns the first stop_after mismatches."""
    sim = Sim()
    chip = chip_cls(sim, tr.clk_period)
    if tr.has_faults:                       # the same injected cell faults (model chips only)
        chip.stuck, chip.coupled = dict(tr.chip.stuck), dict(tr.chip.coupled)
    bad: list[Mismatch] = []
    for i, (t, kind, val, exp) in enumerate(tr.rows()):
        if t != sim.t:
            sim.advance(t)
        if kind == CLK_R:
            got = chip.link_tx | chip.status << 4
            if got != exp:
                if got & 15 != exp & 15:
                    bad.append(Mismatch(i, t, "LINK_TX", exp & 15, got & 15))
                if got >> 4 != exp >> 4:
                    bad.append(Mismatch(i, t, "STATUS", exp >> 4, got >> 4))
            chip.clk_rise()
        elif kind == LINK_R:
            chip.link_rise()
        elif kind == LINK_D:
            chip.link_d = val
        elif kind == SCLK_R:
            if chip.miso != exp:
                bad.append(Mismatch(i, t, "SPI_MISO", exp, chip.miso))
            chip.spi_rise()
        elif kind == SCLK_F:
            chip.spi_fall()
        elif kind == MOSI:
            chip.mosi = val
        elif kind == CS:
            chip.spi_cs(val)
        elif kind == TCK_R:
            if chip.tdo != exp:
                bad.append(Mismatch(i, t, "TDO", exp, chip.tdo))
            chip.tck_rise()
        elif kind == TCK_F:
            chip.tck_fall()
        elif kind == TMS:
            chip.tms = val
        elif kind == TDI:
            chip.tdi = val
        elif kind == RST:
            chip.set_rst_n(val)
        if len(bad) >= stop_after:
            break
    return bad


def record_scenarios(names: list[str], meta: bool = False, quiet: bool = True):
    """Run scenarios from __main__ with every bench they build recorded.
    Returns (traces, checks) where checks is the scenario's own (name, ok, detail) list.

    meta = False switches the metastability model off, which an RTL simulation
    does not have either; the trace is then what the RTL must reproduce."""
    import contextlib
    import io

    from . import __main__ as M
    traces: list[Trace] = []
    current = [""]

    class RecordedBench(Bench):
        def __init__(self, *a, **kw):
            if not meta:
                kw["meta"] = 0
            super().__init__(*a, **kw)
            n = sum(1 for x in traces if x.label.startswith(current[0] + " "))
            traces.append(record(self, f"{current[0]} {n}"))

    saved, M.Bench = M.Bench, RecordedBench
    first = len(M.RESULTS)
    try:
        for name in names:
            current[0] = name
            with contextlib.redirect_stdout(io.StringIO() if quiet else None) if quiet else contextlib.nullcontext():
                M.SCENARIOS[name]()
    finally:
        M.Bench = saved
    return traces, M.RESULTS[first:]
