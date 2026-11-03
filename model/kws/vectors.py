"""Chip test vectors from a real spoken word: every weight set and every activation vector the
chip is given, and the result it must return, recorded once so they can be replayed anywhere.

    /usr/bin/python3 -m model.kws.vectors [clip index] [checkpoint]

The network runs one clip from the official test set with the FPGA's schedule
(model/chip_v2/fpga.PinFpga: each product cut into weight sets of 32 inputs by 4 outputs,
output groups outside, input chunks inside, unused rows and outputs zero). For each weight set
it records the weights, every vector sent through it, and the expected raw results, worked
out by digital_dcim.chip_pass (the contracts, bit-serial) and checked against plain W^T a.

The floating-point FPGA steps decide which integers reach the chip, so another device could
record slightly different vectors. That does not matter: once written, these files are the
reference. The chip, the RTL and the silicon must return exactly these results for exactly
these inputs, wherever they run.

Writes
    model/build/kws/vectors/word<clip>_<net>.npz      the whole word (about 29 MB)
    model/chip_v2/vectors/kws_word<clip>_sample.npz    32 weight sets: the first, two middle and
                                                       last set of each kind of product in the
                                                       first block, the embedding and the head
Both carry the SHA-256 of the whole word's stream (weights, vectors, results in order), so a
full run on any target can be checked by hash.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch

from ..digital_dcim import N_OUT, ROWS, chip_pass
from . import data
from .features import LogMel
from .golden import GOLDEN
from .model import Config, Net

SAMPLE_PRODUCTS = ["embed", "0.qkv", "0.score", "0.mix", "0.proj", "0.fc1", "0.fc2", "head"]


class Recorder:
    """The FPGA's schedule, keeping every weight set, vector and result."""

    def __init__(self):
        self.weights, self.vectors, self.results, self.names = [], [], [], []
        self.current = ""

    def matvec(self, w: np.ndarray, a: np.ndarray, bits: int) -> np.ndarray:
        n_in, n_out = w.shape
        out = np.zeros((a.shape[0], n_out), dtype=np.int64)
        for g in range(0, n_out, N_OUT):
            for c in range(0, n_in, ROWS):
                blk = w[c:c + ROWS, g:g + N_OUT]
                wset = np.zeros((ROWS, N_OUT), dtype=np.int64)
                wset[:blk.shape[0], :blk.shape[1]] = blk
                aset = np.zeros((a.shape[0], ROWS), dtype=np.int64)
                aset[:, :blk.shape[0]] = a[:, c:c + ROWS]
                raw = chip_pass(wset, aset, bits)
                assert np.array_equal(raw, aset @ wset), "chip_pass differs from W^T a"
                assert bits == 8
                self.weights.append(wset)
                self.vectors.append(aset)
                self.results.append(raw)
                self.names.append(self.current)
                out[:, g:g + blk.shape[1]] += raw[:, :blk.shape[1]]
        return out

    def arrays(self, sets=None) -> dict:
        sets = range(len(self.weights)) if sets is None else sets
        return {"weights": np.stack([self.weights[s] for s in sets]).astype(np.int8),
                "vectors": np.concatenate([self.vectors[s] for s in sets]).astype(np.uint8),
                "set_of": np.concatenate([np.full(len(self.vectors[s]), k, dtype=np.int32)
                                          for k, s in enumerate(sets)]),
                "expected": np.concatenate([self.results[s] for s in sets]).astype(np.int32),
                "bits": np.full(len(sets), 8, dtype=np.int8),
                "product": np.array([self.names[s] for s in sets]),
                "index_in_word": np.array(list(sets), dtype=np.int32)}


def stream_hash(rec: Recorder) -> str:
    h = hashlib.sha256()
    for w, a, r in zip(rec.weights, rec.vectors, rec.results):
        h.update(w.astype("<i1").tobytes())
        h.update(a.astype("<u1").tobytes())
        h.update(r.astype("<i4").tobytes())
    return h.hexdigest()


def main() -> int:
    clip = int(sys.argv[1]) if len(sys.argv) > 1 else 418
    path = sys.argv[2] if len(sys.argv) > 2 else GOLDEN
    x, y = data.load()["test"]
    ck = torch.load(path, map_location="cpu", weights_only=True)
    net = Net(Config(**ck["config"]))
    net.load_state_dict(ck["state"])
    net.amax, net.mode = ck["amax"], "chip"
    net.eval()
    rec = Recorder()
    net.matvec = rec.matvec
    orig = net._mm

    def named(name, a, w, unsigned=False):
        rec.current = name
        return orig(name, a, w, unsigned)
    net._mm = named
    with torch.no_grad():
        logits = net(LogMel(torch.device("cpu"))(torch.tensor(x[clip:clip + 1])))
    answer = data.CLASSES[int(logits.argmax())]
    sha = stream_hash(rec)
    meta = {"clip": clip, "truth": data.CLASSES[int(y[clip])], "answer": answer, "network": Path(path).name,
            "network_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(), "word_stream_sha256": sha,
            "weight_sets_in_word": len(rec.weights), "vectors_in_word": int(sum(len(a) for a in rec.vectors)),
            "P": 8, "source": "Speech Commands v2 official test set, sorted file order"}
    full = Path("model/build/kws/vectors") / f"word{clip}_{Path(path).stem}.npz"
    full.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(full, meta=np.array(json.dumps(meta)), **rec.arrays())
    sets = []
    for name in SAMPLE_PRODUCTS:
        idx = [i for i, n in enumerate(rec.names) if n == name]
        sets += sorted({idx[0], idx[len(idx) // 3], idx[2 * len(idx) // 3], idx[-1]})
    sample = Path("model/chip_v2/vectors") / f"kws_word{clip}_sample.npz"
    sample.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(sample, meta=np.array(json.dumps(meta | {"sample_of": full.name})), **rec.arrays(sets))
    print(f"clip {clip} ({meta['truth']}, the network says {answer}): {meta['weight_sets_in_word']:,} weight sets, "
          f"{meta['vectors_in_word']:,} vectors, stream sha256 {sha[:16]}")
    print(f"  whole word: {full} ({full.stat().st_size / 1e6:.1f} MB)")
    print(f"  sample: {sample} ({len(sets)} sets, {sample.stat().st_size / 1e3:.0f} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
