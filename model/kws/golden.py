"""The keyword network's acceptance test: the official Speech Commands test set (4,890 clips,
none of their speakers in training), with every multiply done the way the chip does it.

    /usr/bin/python3 -m model.kws.golden [checkpoint ...] [--limit N]

The chip arithmetic here is written from the architecture contracts in .claude/CLAUDE.md, as
model/digital_dcim is, never from the RTL, and it is checked against digital_dcim.chip_pass
before it is used. The FPGA cuts every product into weight sets of 32 inputs by 4 outputs
(unused rows and outputs zero). In each set the activations go in one bit plane at a time,
least significant first (contract 6); each plane meets the weights' bit columns, the most
significant column subtracted (contracts 3, 10); the lane value is shifted by the plane and
added into a 21-bit accumulator (contract 11); the result leaves as 13 + P bits (contract 15).
The FPGA adds the sets' partial sums. Signed activations go in as value + 128 and the FPGA
takes off 128 x (the sum of each output's weights), as model/kws/model.py describes.

Every product is compared with plain integer arithmetic (a @ w); one difference fails the run.
The answers and logits for every clip are written to model/build/kws/golden_<checkpoint>.npz,
with the checkpoint's SHA-256: the reference that the RTL, the FPGA code and the silicon are
later compared with, clip by clip.

The golden network is kwt1_s1, chosen by validation accuracy (97.56%, against 97.34% and
97.54%) before its test score was looked at for this purpose. The other two can be run too.
"""
from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from ..digital_dcim import chip_pass
from . import data
from .features import LogMel
from .model import Config, Net
from .train import wilson

ROWS, N_OUT, DW, ACC_WIDTH, CLOG2_ROWS = 32, 4, 8, 21, 5
GOLDEN = "model/build/kws/kwt1_s1.pt"


def wrap(v: torch.Tensor, width: int) -> torch.Tensor:
    half = 1 << (width - 1)
    return ((v + half) & ((1 << width) - 1)) - half


class ChipArith:
    """W^T a for whole tensors, bit for bit as the chip and the FPGA do it, and a check of
    every product against a @ w."""

    def __init__(self, bits: int = 8):
        self.bits = bits
        self.products = self.values = self.wrong = 0
        self.sets = self.passes = 0                 # per clip, counted on the first batch
        self.counting = True

    def __call__(self, a: torch.Tensor, w: torch.Tensor) -> torch.Tensor:
        """a [..., M, K] in 0..2^bits - 1, w [..., K, N] in -128..127 -> [..., M, N]."""
        assert int(a.min()) >= 0 and int(a.max()) < 1 << self.bits
        assert int(w.min()) >= -128 and int(w.max()) <= 127
        K, N = w.shape[-2:]
        Kp, Np = -(-K // ROWS) * ROWS, -(-N // N_OUT) * N_OUT
        a = F.pad(a, (0, Kp - K))
        wp = F.pad(w, (0, Np - N, 0, Kp - K))
        cols = (((wp & 0xFF).unsqueeze(-1) >> torch.arange(DW, device=w.device)) & 1).float()
        cols = cols.reshape(*wp.shape[:-2], Kp, Np * DW)            # [..., row, output x bit column]
        weight_of = torch.arange(DW - 1, device=w.device)
        out = 0
        for c in range(Kp // ROWS):                                 # one weight set per 32 inputs (x 4 outputs)
            wc = cols[..., c * ROWS:(c + 1) * ROWS, :]
            acc = torch.zeros((), dtype=torch.long, device=w.device)
            for p in range(self.bits):                              # bit planes, least significant first
                plane = ((a[..., c * ROWS:(c + 1) * ROWS] >> p) & 1).float()
                colsum = torch.matmul(plane, wc).round().long()     # 0..32: exact in float32
                colsum = colsum.reshape(*colsum.shape[:-1], Np, DW)
                lane = (colsum[..., :DW - 1] << weight_of).sum(-1) - (colsum[..., DW - 1] << (DW - 1))
                acc = wrap(acc + (lane << p), ACC_WIDTH)
            out = out + wrap(acc, DW + self.bits + CLOG2_ROWS)     # the return lane; partial sums add on the FPGA
        out = out[..., :N]
        ref = torch.matmul(a[..., :K].float(), w.float()).round().long()
        self.products += 1
        self.values += out.numel()
        self.wrong += int((out != ref).sum())
        if self.counting:
            per_clip_w = int(np.prod(wp.shape[1:-2])) if wp.dim() > 2 else 1      # keys, values: one per clip
            sets = (Kp // ROWS) * (Np // N_OUT) * per_clip_w
            self.sets += sets
            self.passes += sets * (a.shape[-2] if a.dim() > 2 else 1)   # one vector per token per clip; the head, one
        return out


def self_check() -> None:
    """ChipArith against digital_dcim.chip_pass: random weight sets at every P, extremes included."""
    rng = np.random.default_rng(5)
    for bits in range(1, 9):
        for trial in range(20):
            w = rng.integers(-128, 128, (ROWS, N_OUT))
            if trial == 0:
                w[:] = -128
            a = rng.integers(0, 1 << bits, (16, ROWS))
            if trial == 0:
                a[:] = (1 << bits) - 1
            got = ChipArith(bits)(torch.tensor(a), torch.tensor(w)).numpy()
            assert np.array_equal(got, chip_pass(w, a, bits)), f"ChipArith differs from digital_dcim at P = {bits}"


def main() -> int:
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    args = [x for x in args if not (limit is not None and x == str(limit))] or [GOLDEN]
    torch.set_num_threads(4)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    self_check()
    print("chip arithmetic agrees with model/digital_dcim at every P", flush=True)
    x, y = data.load()["test"]
    x, y = x[:limit], y[:limit]
    mel = LogMel(dev)
    feats = torch.cat([mel(torch.tensor(x[i:i + 512], device=dev)) for i in range(0, len(y), 512)])
    bad = 0
    for path in args:
        t0 = time.time()
        ck = torch.load(path, map_location=dev, weights_only=True)
        net = Net(Config(**ck["config"])).to(dev)
        net.load_state_dict(ck["state"])
        net.amax, net.mode = ck["amax"], "chip"
        net.eval()
        net.chip = arith = ChipArith()
        logits = []
        with torch.no_grad():
            for i in range(0, len(y), 64):
                arith.counting = i == 0                     # the schedule is the same for every clip
                logits.append(net(feats[i:i + 64]).cpu())
        logits = torch.cat(logits).numpy()
        pred = logits.argmax(1)
        k, n = int((pred == y).sum()), len(y)
        lo, hi = wilson(k, n)
        sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        out = Path(path).with_name(f"golden_{Path(path).stem}{'' if limit is None else f'_first{limit}'}.npz")
        np.savez(out, labels=y, answers=pred.astype(np.int8), logits=logits.astype(np.float32),
                 checkpoint_sha256=np.array(sha))
        per = ", ".join(f"{c} {100 * (pred[y == i] == i).mean():.1f}" for i, c in enumerate(data.CLASSES) if (y == i).any())
        print(f"{path} (sha256 {sha[:12]}): {n} clips, {arith.products:,} products, {arith.values:,} values, "
              f"{arith.wrong} different from plain integer arithmetic", flush=True)
        print(f"   accuracy through the chip arithmetic: {100 * k / n:.2f}% (95% interval {lo:.2f} to {hi:.2f}); "
              f"per class: {per}", flush=True)
        print(f"   per clip: {arith.sets:,} weight sets, {arith.passes:,} passes; written {out} "
              f"({time.time() - t0:.0f} s on {dev})", flush=True)
        bad += arith.wrong != 0
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
