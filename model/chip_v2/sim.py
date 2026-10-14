"""Event kernel. Time is an integer number of picoseconds.

Everything that happens at one instant is handled in two steps, the way flops
behave: first every clock edge at that instant runs and reads only what was
visible before the instant, then the new values become visible. So two edges
at exactly the same time cannot see each other's result.
"""
from __future__ import annotations

import heapq
import random
from typing import Callable


class Sim:
    def __init__(self, seed: int = 0, meta_window: int = 0):
        self.t = 0
        self._q: list = []
        self._n = 0
        self._publish: list[Callable[[], None]] = []
        self.rng = random.Random(seed)
        self.meta_window = meta_window      # ps. Above 0: a flop that samples a signal which
                                            # changed less than this long ago gets old or new at random.

    def at(self, t: int, fn: Callable[[], None]) -> None:
        assert t >= self.t, "cannot schedule in the past"
        heapq.heappush(self._q, (t, self._n, fn))
        self._n += 1

    def on_publish(self, fn: Callable[[], None]) -> None:
        self._publish.append(fn)

    def run_until(self, t_end: int) -> None:
        while self._q and self._q[0][0] <= t_end:
            t = self._q[0][0]
            self.t = t
            while self._q and self._q[0][0] == t:
                heapq.heappop(self._q)[2]()
            for fn in self._publish:
                fn()
        self.t = max(self.t, t_end)

    def run_for(self, dt: int) -> None:
        self.run_until(self.t + dt)


class Clock:
    """A free-running clock. on_rise and on_fall are called at its edges."""

    def __init__(self, sim: Sim, period: int, phase: int = 0,
                 on_rise: Callable[[], None] | None = None,
                 on_fall: Callable[[], None] | None = None):
        assert period % 2 == 0
        self.sim, self.period, self.on_rise, self.on_fall = sim, period, on_rise, on_fall
        self.running = True
        self.edges = 0                      # rising edges so far
        sim.at(sim.t + phase, self._rise)

    def _rise(self) -> None:
        if not self.running:
            return
        self.edges += 1
        if self.on_rise:
            self.on_rise()
        self.sim.at(self.sim.t + self.period // 2, self._fall)

    def _fall(self) -> None:
        if not self.running:
            return
        if self.on_fall:
            self.on_fall()
        self.sim.at(self.sim.t + self.period // 2, self._rise)

    def stop(self) -> None:
        self.running = False


class Crossing:
    """Signals one clock domain shows to the others. A value written with put()
    becomes visible only when the kernel publishes, and get() can model a flop
    that samples it too soon after it changed."""

    def __init__(self, sim: Sim):
        self.sim = sim
        self._vis: dict[str, int] = {}
        self._prev: dict[str, int] = {}
        self._when: dict[str, int] = {}
        self._pend: dict[str, int] = {}
        self.unsafe_reads: list[tuple[int, str]] = []
        sim.on_publish(self._do_publish)

    def put(self, name: str, value: int) -> None:
        self._pend[name] = value

    def _do_publish(self) -> None:
        for name, value in self._pend.items():
            if self._vis.get(name) != value:
                self._prev[name] = self._vis.get(name, value)
                self._vis[name] = value
                self._when[name] = self.sim.t
        self._pend.clear()

    def get(self, name: str, default: int = 0) -> int:
        """Sample through a synchronizer's first flop."""
        value = self._vis.get(name, default)
        w = self.sim.meta_window
        if w and name in self._when and self.sim.t - self._when[name] < w and self.sim.rng.random() < 0.5:
            return self._prev[name]
        return value

    def held(self, name: str, default: int = 0, settle: int = 0) -> int:
        """Read a multi-bit word that the protocol says is being held still.
        If it changed less than `settle` ago, that is a crossing violation."""
        if name in self._when and self.sim.t - self._when[name] < settle:
            self.unsafe_reads.append((self.sim.t, name))
        return self._vis.get(name, default)
