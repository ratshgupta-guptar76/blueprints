"""The chip, bit for bit, from the architecture contracts in .claude/CLAUDE.md.

Not derived from the RTL. It models the arithmetic (contracts 2, 3, 6, 10, 11,
15) and counts what was asked of it. It does not model frames, CRC, clock
domains, or timing inside a cycle. Cycle totals use the estimate formulas of
docs/V2_DESIGN_GUIDE.md section 6.4; the v1 figures are measured.
"""
from __future__ import annotations

from collections import Counter

import numpy as np

# Source of truth: src/dcim_pkg.sv
ROWS = 32
DW = 8
N_OUT = 4
CLOG2_ROWS = 5
ACC_WIDTH = DW + DW + CLOG2_ROWS        # 21
W_MIN, W_MAX = -(1 << (DW - 1)), (1 << (DW - 1)) - 1

V1_WEIGHT_SET = 1025        # measured
V2_WEIGHT_SET = 1024        # estimate, lower bound: SPI clock at the core clock rate


def wrap(v: np.ndarray, width: int) -> np.ndarray:
    """Keep the low `width` bits and read them as a signed number."""
    half = 1 << (width - 1)
    return ((v + half) & ((1 << width) - 1)) - half


def raw_width(bits: int) -> int:
    """Width of a raw result on the return lane (contract 15)."""
    return DW + bits + CLOG2_ROWS


def chip_pass(w: np.ndarray, a: np.ndarray, bits: int) -> np.ndarray:
    """One batch of vectors through one weight set, bit-serial.

    w [ROWS, N_OUT] INT8. a [n, ROWS] unsigned, `bits` bits each.
    Each cycle broadcasts one activation bit-plane, LSB first (contract 6).
    Each weight bit-column is summed down the rows (contracts 2, 3). The MSB
    column is subtracted (contract 10). The lane value goes into a 21-bit
    signed accumulator, shifted by the plane index (contract 11). The result
    leaves as raw_width(bits) bits (contract 15).
    """
    assert w.shape == (ROWS, N_OUT) and a.shape[1] == ROWS
    assert w.min() >= W_MIN and w.max() <= W_MAX
    assert a.min() >= 0 and a.max() < (1 << bits)
    wbits = ((w[:, :, None] & 0xFF) >> np.arange(DW)) & 1          # [row, out, bit]
    acc = np.zeros((a.shape[0], N_OUT), dtype=np.int64)
    for plane_idx in range(bits):
        plane = (a >> plane_idx) & 1
        colsum = np.einsum("nr,rob->nob", plane, wbits)            # 0..ROWS
        lane = ((colsum[:, :, :DW - 1] << np.arange(DW - 1)).sum(axis=2)
                - (colsum[:, :, DW - 1] << (DW - 1)))
        acc = wrap(acc + (lane << plane_idx), ACC_WIDTH)
    return wrap(acc, raw_width(bits))


def v1_period(bits: int) -> int:
    """v1 cycles per vector: load, compute, done, drain."""
    return ROWS * DW + bits + 1 + (N_OUT * ACC_WIDTH + 1)


def v2_period(bits: int) -> int:
    """v2 cycles per vector with a raw drain: the slower of the activation
    chain (payload, CRC, compare, compute) and the return lane. The load is
    1 bit per row at P = 1 and the full DW bits per row at every other P
    (contract 15), so P = 2..7 saves compute cycles only."""
    load_bits = 1 if bits == 1 else DW
    chain = (ROWS * load_bits) // 4 + 2 + 1 + bits
    drain = raw_width(bits) + 8
    return max(chain, drain)


class Chip:
    """Weight-stationary chip: load a weight set, then run vectors through it."""

    def __init__(self):
        self._w: np.ndarray | None = None
        self.weight_loads = 0
        self.vectors: Counter[int] = Counter()      # vectors run, by precision

    def load_weights(self, w: np.ndarray) -> None:
        w = np.asarray(w, dtype=np.int64)
        assert w.shape == (ROWS, N_OUT) and w.min() >= W_MIN and w.max() <= W_MAX
        self._w = w.copy()
        self.weight_loads += 1

    def run(self, a: np.ndarray, bits: int) -> np.ndarray:
        """a [n, ROWS] -> raw results [n, N_OUT]. Weights are not disturbed."""
        assert self._w is not None, "no weights loaded"
        a = np.asarray(a, dtype=np.int64)
        self.vectors[bits] += a.shape[0]
        return chip_pass(self._w, a, bits)

    def cycles(self) -> dict[str, int]:
        """Total cycles for everything run so far, as v1 and as v2 (estimate)."""
        return {
            "v1": self.weight_loads * V1_WEIGHT_SET
                  + sum(n * v1_period(b) for b, n in self.vectors.items()),
            "v2": self.weight_loads * V2_WEIGHT_SET
                  + sum(n * v2_period(b) for b, n in self.vectors.items()),
            "v1_reload": self.weight_loads * V1_WEIGHT_SET,
            "v2_reload": self.weight_loads * V2_WEIGHT_SET,
        }
