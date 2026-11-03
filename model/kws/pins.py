"""Spoken words through the v2 chip's pins: every multiply-accumulate of the
keyword transformer goes through the pin-level model (model/chip_v2) by way of
the FPGA schedule, and every result is compared with plain integer arithmetic.

    /usr/bin/python3 -m model.kws.pins model/build/kws/kwt1_s0.pt [n clips]

Slow on purpose: the pin model runs about 57,000 chip cycles a second.
"""
from __future__ import annotations

import sys
import time

import numpy as np
import torch

from ..chip_v2.fpga import Bench, PinFpga
from . import data
from .features import LogMel
from .model import Config, Net


def main() -> int:
    path, n = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1
    dev = torch.device("cpu")
    ck = torch.load(path, map_location=dev, weights_only=True)
    net = Net(Config(**ck["config"]))
    net.load_state_dict(ck["state"])
    net.amax, net.mode = ck["amax"], "chip"
    net.eval()
    x, y = data.load()["test"]
    pick = np.random.default_rng(3).choice(len(y), n, replace=False)
    mel = LogMel(dev)
    bad = 0
    for i in pick:
        feats = mel(torch.tensor(x[i:i + 1]))
        with torch.no_grad():
            want = net(feats)                               # integer products in torch
        b = Bench()
        b.start(None, p=8)
        fp = PinFpga(b)
        calls = {"n": 0, "wrong": 0}

        def matvec(w, a, bits):
            r = fp.matvec(w, a, bits)
            calls["n"] += 1
            calls["wrong"] += int(not np.array_equal(r, a.astype(np.int64) @ w.astype(np.int64)))
            return r
        net.matvec = matvec
        t0, c0 = time.time(), b.chip.cyc
        with torch.no_grad():
            got = net(feats)
        net.matvec = None
        cycles = b.chip.cyc - c0
        same = torch.equal(got, want) and calls["wrong"] == 0
        clean = b.chip.cnt_ovr == 0 and b.chip.cnt_crc == 0 and not b.chip.x.unsafe_reads and not b.chip.fifo_ovf
        bad += not (same and clean)
        print(f"clip {i}: truth {data.CLASSES[y[i]]:8} chip says {data.CLASSES[int(got.argmax())]:8} "
              f"products {calls['n']} calls, {calls['wrong']} wrong; logits identical {torch.equal(got, want)}; "
              f"{fp.passes:,} passes, {fp.sets:,} weight sets, {cycles:,} cycles ({cycles / 25e6:.2f} s at 25 MHz); "
              f"{time.time() - t0:.0f} s", flush=True)
    print("all identical" if not bad else f"{bad} clips differ")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
