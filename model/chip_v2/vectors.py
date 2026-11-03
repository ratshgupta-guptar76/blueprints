"""Recorded chip test vectors through the pins of the v2 model.

    python3 -m model.chip_v2.vectors FILE [--sets A:B]

A vector file (written by model/kws/vectors.py) holds weight sets, the activation vectors sent
through each, and the raw results the chip must return. Each set is written over SPI once the
chip is idle, its vectors go out as link frames at the per-vector period, and every return
frame is compared with the recorded result, exactly. The scenario `kws` runs the committed
sample this way, so its pin trace is replayed edge for edge on RTL by cocotb/v2.
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np

from .chip import A_P
from .fpga import Bench, link_frame


def load(path: str) -> dict:
    z = np.load(path, allow_pickle=False)
    v = {k: z[k] for k in z.files}
    v["meta"] = json.loads(str(v["meta"]))
    return v


def run(b: Bench, v: dict, sets=None, spacing: int = 75) -> dict:
    """Send the recorded sets through a started bench. Returns what was compared."""
    sets = range(len(v["weights"])) if sets is None else sets
    out = {"sets": 0, "vectors": 0, "wrong": 0, "first_wrong": None}
    p = None
    for s in sets:
        idx = np.flatnonzero(v["set_of"] == s)
        bits = int(v["bits"][s])
        b.wait(lambda: not b.chip._busy() and not b.chip.tx_cnt, what="idle before a weight write")
        if bits != p:
            b.wr(A_P, bits - 1)
            p = b.rx.p = bits
        b.load_weights(v["weights"][s].astype(np.int64))
        b.rx.frames.clear()
        gap = spacing if bits != 1 else 22
        for k, i in enumerate(idx):
            f = link_frame(k & 63, v["vectors"][i].astype(np.int64), bits)
            b.stream.extend(f + [0] * (gap - len(f)))
        b.wait(lambda: len(b.rx.frames) >= len(idx), limit=len(idx) * gap + 2000, what="every result of a set")
        for k, (i, f) in enumerate(zip(idx, b.rx.frames)):
            good = f["ok"] and f["seq"] == k & 63 and f["vals"] == [int(r) for r in v["expected"][i]]
            if not good:
                out["wrong"] += 1
                if out["first_wrong"] is None:
                    out["first_wrong"] = (int(s), int(i), f["vals"], [int(r) for r in v["expected"][i]])
        out["sets"] += 1
        out["vectors"] += len(idx)
    return out


def main() -> int:
    path = sys.argv[1]
    v = load(path)
    sets = None
    if "--sets" in sys.argv:
        a, c = sys.argv[sys.argv.index("--sets") + 1].split(":")
        sets = range(int(a or 0), int(c) if c else len(v["weights"]))
    b = Bench()
    b.start(None, p=8)
    t0, c0 = time.time(), b.chip.cyc
    r = run(b, v, sets)
    m = v["meta"]
    print(f"{path}: word {m['clip']} ({m['truth']}), {r['sets']:,} weight sets, {r['vectors']:,} vectors through the "
          f"pins, {r['wrong']} results different from the recorded ones; {b.chip.cyc - c0:,} cycles, "
          f"{time.time() - t0:.0f} s")
    if r["first_wrong"]:
        print(f"  first difference: set {r['first_wrong'][0]}, vector {r['first_wrong'][1]}: got {r['first_wrong'][2]}, "
              f"recorded {r['first_wrong'][3]}")
    clean = b.chip.cnt_ovr == 0 and b.chip.cnt_crc == 0 and not b.chip.x.unsafe_reads and b.chip.obs["x_reads"] == 0
    return 0 if r["wrong"] == 0 and clean else 1


if __name__ == "__main__":
    sys.exit(main())
