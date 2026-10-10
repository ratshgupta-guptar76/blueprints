"""The FPGA's job around the chip.

The chip does 32 inputs by 4 outputs per weight set. The FPGA:
  - cuts every layer into 32-input chunks and 4-output groups,
  - loads one weight set, sends every image's vector through it, loads the
    next (batch by weight set),
  - adds the partial sums of chunked layers,
  - adds bias, applies ReLU, scales to the next layer's width,
  - cuts images into windows for convolution layers and does the max pooling,
  - picks the largest final score.

It moves data and does this glue arithmetic. Every multiply-accumulate is the
chip's. Frames and CRC are not modelled here yet.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..digital_dcim import N_OUT, ROWS, Chip
from ..ml_model import QNet


@dataclass
class GlueOps:
    """Arithmetic the FPGA does for one image."""
    partial_sum_adds: int = 0
    bias_adds: int = 0
    relu_and_scale: int = 0
    compares: int = 0           # max pooling and picking the largest score


class Fpga:
    def __init__(self, chip: Chip):
        self.chip = chip
        self.sets: list[tuple[int, int]] = []       # per weight set: (input bits, vectors run)

    def matvec(self, w: np.ndarray, a: np.ndarray, bits: int) -> np.ndarray:
        """W^T a for a whole layer and a whole batch, using only the chip."""
        n_in, n_out = w.shape
        out = np.zeros((a.shape[0], n_out), dtype=np.int64)
        for g in range(0, n_out, N_OUT):
            for c in range(0, n_in, ROWS):
                wset = np.zeros((ROWS, N_OUT), dtype=np.int64)
                aset = np.zeros((a.shape[0], ROWS), dtype=np.int64)
                blk = w[c:c + ROWS, g:g + N_OUT]
                wset[:blk.shape[0], :blk.shape[1]] = blk       # unused rows and outputs stay zero
                aset[:, :blk.shape[0]] = a[:, c:c + ROWS]
                self.chip.load_weights(wset)
                raw = self.chip.run(aset, bits)
                out[:, g:g + N_OUT] += raw[:, :blk.shape[1]]   # partial-sum add when chunked
                self.sets.append((bits, a.shape[0]))
        return out

    def classify(self, net: QNet, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Front end output [n, features] -> (answers [n], final scores [n, classes])."""
        self.sets = []
        # One batch, so every weight set is loaded once for all images.
        scores = net.scores(features, matvec=self.matvec, batch=len(features))
        return scores.argmax(axis=1), scores

    @staticmethod
    def glue_ops(net: QNet) -> GlueOps:
        ops = GlueOps()
        for row in net.plan():
            h, w, c = row["shape"]
            if row["kind"] == "pool":
                ops.compares += (row["k"] ** 2 - 1) * h * w * c     # largest of k*k values
            elif row["stage"] == "chip":
                values = row["outputs"] * row["positions"]
                chunks = -(-row["inputs"] // ROWS)
                ops.partial_sum_adds += (chunks - 1) * values
                ops.bias_adds += values                  # for "attn mix" this is the add of the input
                if row["act"] in ("relu", "clamp"):      # clamp: scale and limit, keeping the sign
                    ops.relu_and_scale += values
                elif row["act"] == "none":
                    ops.compares += row["outputs"] - 1
        return ops
