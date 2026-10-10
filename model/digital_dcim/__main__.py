"""Self checks for the chip model. Run from the repository root:

    python3 -m model.digital_dcim
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from .chip import (ACC_WIDTH, DW, N_OUT, ROWS, W_MAX, W_MIN, Chip, chip_pass,
                   v1_period, v2_period)


def main() -> int:
    rng = np.random.default_rng(1)

    for bits in range(1, DW + 1):
        w = rng.integers(W_MIN, W_MAX + 1, (ROWS, N_OUT))
        a = rng.integers(0, 1 << bits, (64, ROWS))
        assert np.array_equal(chip_pass(w, a, bits), a @ w)
    for wv in (W_MIN, W_MAX):
        w = np.full((ROWS, N_OUT), wv)
        a = np.full((1, ROWS), 255)
        assert np.array_equal(chip_pass(w, a, DW), a @ w)
    print("ok: bit-serial result equals W^T a for P = 1..8, including the extremes")

    assert (v1_period(1), v1_period(8)) == (343, 350)
    assert (v2_period(1), v2_period(8)) == (22, 75)
    assert (v2_period(2), v2_period(4)) == (69, 71)      # full-width load unless P = 1
    print("ok: cycle formulas give 343, 350 (v1) and 22, 75 (v2), as documented")

    chip = Chip()
    w = rng.integers(W_MIN, W_MAX + 1, (ROWS, N_OUT))
    chip.load_weights(w)
    a = rng.integers(0, 256, (20, ROWS))
    first, second = chip.run(a, DW), chip.run(a, DW)
    assert np.array_equal(first, second) and chip.weight_loads == 1
    print("ok: weights persist across vectors (contract 1)")

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cocotb"))
        import golden.lane_shift_accum as ref
        ref.ROWS, ref.DW, ref.ACC_WIDTH, ref.A_SIGN, ref.W_SIGN = ROWS, DW, ACC_WIDTH, 0, 1
        for n in range(a.shape[0]):
            for o in range(N_OUT):
                y = ref.golden_ref(0, 1, 0, 0, [0] * DW)
                for p in range(DW):
                    col = [int((((a[n] >> p) & 1) * ((w[:, o] >> bit) & 1)).sum()) for bit in range(DW)]
                    y = ref.golden_ref(y, 0, 1, p, col)
                assert y == first[n, o]
        print("ok: agrees with cocotb/golden/lane_shift_accum.py on 80 random results")
    except ImportError:
        print("skipped: cocotb golden model not importable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
