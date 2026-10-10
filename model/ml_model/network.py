"""The network as integers: this file is the math the hardware has to do.

A network is a list of layers. Four kinds:

  conv   slide a k x k window over the image. For every window position:
             acc = W^T a + b       W [k*k*channels, outputs], a = the window
         A depthwise conv filters each channel on its own: W is [k*k, channels]
         and output c uses only channel c of the window.
  dense  the same with one window that covers everything.
  pool   keep the largest value of every k x k block (compares only).
  attn   self-attention: every position of the feature map looks at every
         other position (see Attention below).

After conv and dense comes one of three activations:

  relu   a = min(max(acc, 0) >> shift, 2^out_bits - 1)   ReLU, scale, saturate
  step   a = 1 if acc > 0 else 0                         one comparator
  none   the final scores; the answer is the index of the largest

A layer runs on the chip (signed INT8 weights) or in the photonic first layer
(normally weights of zero or more and a step activation; negative weights mean
two photodiodes per output). Images are zero-padded at the edge.

The only multiply-accumulates are `W^T a`. They go through the `matvec`
(chip) and `optical` (photonic) arguments, so the same network runs on plain
numpy (the reference below), on the chip model, or on hardware, and must give
identical integers everywhere.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, ClassVar

import numpy as np

W_MIN, W_MAX = -128, 127
CHIP_ROWS, CHIP_OUTPUTS = 32, 4     # one weight set (src/dcim_pkg.sv)

# matvec(w [n_in, n_out], a [n, n_in], bits of a) -> [n, n_out]
Matvec = Callable[[np.ndarray, np.ndarray, int], np.ndarray]


def reference_matvec(w: np.ndarray, a: np.ndarray, bits: int) -> np.ndarray:
    """W^T a. Done in float64 because that is far faster than integer matmul,
    and it is exact: every product and partial sum is an integer below 2^53."""
    assert a.shape[1] * 255 * (int(np.abs(w).max()) + 1) < 2 ** 53
    return np.rint(a.astype(np.float64) @ w.astype(np.float64)).astype(np.int64)


@dataclass
class Layer:
    kind: str                       # "conv", "dense" or "pool"
    w: np.ndarray | None = None     # int64 [inputs per window, outputs]
    b: np.ndarray | None = None     # int64 [outputs]
    shift: int = 0                  # right shift of the relu activation
    act: str = "relu"               # "relu", "step" or "none"
    out_bits: int = 8               # width of this layer's output values
    k: int = 1                      # window side (conv), block side (pool)
    stride: int = 1
    pad: int = 0                    # zero padding on every edge (conv)
    stage: str = "chip"             # "chip" or "photonic"
    groups: int = 1                 # more than 1: depthwise conv (one group per channel)
    ARRAYS: ClassVar[tuple[str, ...]] = ("w", "b")


@dataclass
class Attention:
    """Self-attention over the positions ("tokens") of a feature map, built
    only from what the chip already does. x is [tokens, channels], unsigned.

        q = min(max(Wq^T x + bq, 0) >> shift_q, top)        query, unsigned
        k = clamp((Wk^T x + bk) >> shift_k)                 key, signed, weight range
        v = clamp((Wv^T x + bv) >> shift_v)                 value, signed, weight range
        s[i, j] = q[i] . k[j]                               how much i attends to j
        a = min(max(s + ba, 0) >> shift_a, top)             ReLU instead of softmax
        o[i] = sum over j of a[i, j] * v[j]
        y = min(max((o >> shift_o) + x, 0), top)            added to the input

    Three of the five products use fixed weights (Wq, Wk, Wv). The other two
    multiply data by data. The chip does those by taking one operand as
    weights: this image's keys, then this image's values, are written into
    the weight array (which is why they are signed and limited to the weight
    range), and the queries, then the attention rows, are sent as unsigned
    activations. So these weight sets are written again for every image.

    Differences from a textbook transformer block, all so that it fits the
    chip unchanged: ReLU and a power-of-two scale in place of softmax, one
    head, no layer normalisation, and position information as a per-position
    bias on queries and keys (bq and bk are [tokens, numbers])."""
    kind: str = "attn"
    wq: np.ndarray | None = None    # int64 [channels, numbers per query]
    bq: np.ndarray | None = None    # int64 [tokens, numbers per query]
    wk: np.ndarray | None = None
    bk: np.ndarray | None = None
    wv: np.ndarray | None = None    # int64 [channels, channels]
    bv: np.ndarray | None = None    # int64 [channels]
    ba: int = 0                     # added to every score before the ReLU
    shift_q: int = 0
    shift_k: int = 0
    shift_v: int = 0
    shift_a: int = 0
    shift_o: int = 0
    out_bits: int = 8               # width of q, a and the output
    w_bits: int = 8                 # width of k and v (they are stored as weights)
    stage: str = "chip"
    ARRAYS: ClassVar[tuple[str, ...]] = ("wq", "bq", "wk", "bk", "wv", "bv")


def _attention(layer: Attention, x: np.ndarray, bits: int, run: Matvec) -> np.ndarray:
    """x [n, h, w, c] -> the same shape."""
    n, h, w, c = x.shape
    assert bits == layer.out_bits, "attention input and output widths differ"
    top = (1 << layer.out_bits) - 1
    lo, hi = -(1 << (layer.w_bits - 1)), (1 << (layer.w_bits - 1)) - 1
    flat = x.reshape(n * h * w, c)
    tokens = x.reshape(n, h * w, c)
    q = run(layer.wq, flat, bits).reshape(n, h * w, -1) + layer.bq
    q = np.minimum(np.maximum(q, 0) >> layer.shift_q, top)
    k = np.clip((run(layer.wk, flat, bits).reshape(n, h * w, -1) + layer.bk) >> layer.shift_k, lo, hi)
    v = np.clip((run(layer.wv, flat, bits).reshape(n, h * w, -1) + layer.bv) >> layer.shift_v, lo, hi)
    y = np.empty_like(tokens)
    for i in range(n):          # keys and values belong to one image: written to the chip per image
        s = run(k[i].T, q[i], layer.out_bits) + layer.ba        # [token, token]
        a = np.minimum(np.maximum(s, 0) >> layer.shift_a, top)
        o = run(v[i], a, layer.out_bits)                        # [token, channel]
        y[i] = np.minimum(np.maximum((o >> layer.shift_o) + tokens[i], 0), top)
    return y.reshape(n, h, w, c)


def depthwise_pack(k: int) -> int:
    """Channels of a depthwise conv that fit one chip weight set: each needs
    k*k rows and one output."""
    return max(1, min(CHIP_OUTPUTS, CHIP_ROWS // (k * k)))


def _depthwise(run: Matvec, w: np.ndarray, cols: np.ndarray, k: int, bits: int) -> np.ndarray:
    """cols [m, k*k*c] -> [m, c]. Channels are packed side by side into weight
    sets the way the chip would take them: channel j of a set uses its own
    k*k rows and output j, with zero weights everywhere else."""
    kk, c = w.shape
    cols = cols.reshape(len(cols), kk, c)
    out = np.empty((len(cols), c), dtype=np.int64)
    per = depthwise_pack(k)
    for c0 in range(0, c, per):
        chans = range(c0, min(c0 + per, c))
        wset = np.zeros((len(chans) * kk, len(chans)), dtype=np.int64)
        for j, ch in enumerate(chans):
            wset[j * kk:(j + 1) * kk, j] = w[:, ch]
        aset = np.concatenate([cols[:, :, ch] for ch in chans], axis=1)
        out[:, c0:c0 + len(chans)] = run(wset, aset, bits)
    return out


def windows(x: np.ndarray, k: int, stride: int, pad: int) -> tuple[np.ndarray, int, int]:
    """[n, h, w, c] -> ([n * oh * ow, k * k * c], oh, ow). A window is flattened
    row by row, and within a pixel channel by channel."""
    if pad:
        x = np.pad(x, ((0, 0), (pad, pad), (pad, pad), (0, 0)))
    v = np.lib.stride_tricks.sliding_window_view(x, (k, k), axis=(1, 2))[:, ::stride, ::stride]
    n, oh, ow = v.shape[:3]                                   # v: [n, oh, ow, c, k, k]
    return v.transpose(0, 1, 2, 4, 5, 3).reshape(n * oh * ow, -1), oh, ow


@dataclass
class QNet:
    in_shape: tuple[int, int, int]      # height, width, channels of the input image
    in_bits: int                        # width of each input value
    layers: list[Layer]
    meta: dict = field(default_factory=dict)

    def scores(self, a: np.ndarray, matvec: Matvec = reference_matvec,
               optical: Matvec = reference_matvec, batch: int = 128) -> np.ndarray:
        """Front end output [n, features] -> final integer scores [n, classes]."""
        a = np.asarray(a)
        assert a.min() >= 0 and a.max() < (1 << self.in_bits), "input out of range"
        out = []
        for start in range(0, len(a), batch):
            x = a[start:start + batch].reshape(-1, *self.in_shape).astype(np.int64)
            bits = self.in_bits
            for layer in self.layers:
                if layer.kind == "pool":
                    n, h, w, c = x.shape
                    x = x.reshape(n, h // layer.k, layer.k, w // layer.k, layer.k, c).max(axis=(2, 4))
                    continue
                if layer.kind == "attn":
                    x = _attention(layer, x, bits, matvec)
                    continue
                run = optical if layer.stage == "photonic" else matvec
                if layer.kind == "conv":
                    cols, oh, ow = windows(x, layer.k, layer.stride, layer.pad)
                    acc = _depthwise(run, layer.w, cols, layer.k, bits) if layer.groups > 1 \
                        else run(layer.w, cols, bits)
                    acc = (acc + layer.b).reshape(len(x), oh, ow, -1)
                else:
                    acc = run(layer.w, x.reshape(len(x), -1), bits) + layer.b
                if layer.act == "none":
                    out.append(acc.reshape(len(x), -1))
                    break
                if layer.act == "step":
                    x = (acc > 0).astype(np.int64)
                else:
                    x = np.minimum(np.maximum(acc, 0) >> layer.shift, (1 << layer.out_bits) - 1)
                bits = layer.out_bits
        return np.concatenate(out)

    def predict(self, a: np.ndarray, **kw) -> np.ndarray:
        return self.scores(a, **kw).argmax(axis=1)

    def plan(self) -> list[dict]:
        """One row per layer: what it is and how much work it is per image.
        weight_sets are loaded once and serve every image. sets_per_image are
        written again for each image (attention keys and values)."""
        rows, (h, w, c), bits = [], self.in_shape, self.in_bits

        def chip_sets(n_in: int, n_out: int) -> int:
            return -(-n_in // CHIP_ROWS) * -(-n_out // CHIP_OUTPUTS)

        for i, layer in enumerate(self.layers):
            if layer.kind == "attn":
                n, d = h * w, layer.wq.shape[1]
                for kind, n_in, n_out, in_bits, fixed, act, shift, bias in (
                        ("attn query", c, d, bits, True, "relu", layer.shift_q, layer.bq),
                        ("attn key", c, d, bits, True, "clamp", layer.shift_k, layer.bk),
                        ("attn value", c, c, bits, True, "clamp", layer.shift_v, layer.bv),
                        ("attn score", d, n, layer.out_bits, False, "relu", layer.shift_a, np.array([layer.ba])),
                        ("attn mix", n, c, layer.out_bits, False, "relu", layer.shift_o, np.array([0]))):
                    sets = chip_sets(n_in, n_out)
                    rows.append({
                        "layer": i + 1, "kind": kind, "stage": "chip", "shape": (h, w, n_out),
                        "inputs": n_in, "outputs": n_out, "input_bits": in_bits, "positions": n,
                        "weights": n_in * n_out if fixed else 0,
                        "weight_sets": sets if fixed else 0, "sets_per_image": 0 if fixed else sets,
                        "chip_passes": sets * n, "act": act, "shift": shift,
                        "bias_bits": int(np.abs(bias).max()).bit_length() + 1,
                    })
                continue
            if layer.kind == "pool":
                h, w = h // layer.k, w // layer.k
                rows.append({"layer": i + 1, "kind": "pool", "stage": "fpga", "shape": (h, w, c), "k": layer.k})
                continue
            if layer.kind == "conv":
                h = (h + 2 * layer.pad - layer.k) // layer.stride + 1
                w = (w + 2 * layer.pad - layer.k) // layer.stride + 1
                positions = h * w
            else:
                h, w, positions = 1, 1, 1
            n_in, c = layer.w.shape
            on_chip = layer.stage == "chip"
            if layer.groups > 1:
                sets = -(-c // depthwise_pack(layer.k))
            else:
                sets = chip_sets(n_in, c) if on_chip else 0
            name = {"conv": f"{'dw' if layer.groups > 1 else 'conv'} {layer.k}x{layer.k}", "dense": "dense"}[layer.kind]
            rows.append({
                "layer": i + 1, "kind": name,
                "stage": layer.stage, "shape": (h, w, c), "inputs": n_in, "outputs": c,
                "input_bits": bits, "positions": positions, "weights": n_in * c,
                "weight_sets": sets, "sets_per_image": 0, "chip_passes": sets * positions,
                "act": layer.act, "shift": layer.shift if layer.act == "relu" else None,
                "bias_bits": int(np.abs(layer.b).max()).bit_length() + 1,
            })
            bits = layer.out_bits
        return rows

    def cost(self) -> dict:
        """Size of the network, for comparing designs."""
        rows = [r for r in self.plan() if "weights" in r]
        return {"weights": sum(r["weights"] for r in rows),
                "weight_sets": sum(r["weight_sets"] for r in rows),
                "sets_per_image": sum(r["sets_per_image"] for r in rows),
                "chip_passes": sum(r["chip_passes"] for r in rows)}

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays, specs = {}, []
        for i, layer in enumerate(self.layers):
            spec = asdict(layer)
            for key in layer.ARRAYS:
                if spec.pop(key) is not None:
                    arrays[f"{key}{i}"] = getattr(layer, key)
            specs.append(spec)
        header = {"in_shape": list(self.in_shape), "in_bits": self.in_bits,
                  "layers": specs, "meta": self.meta}
        np.savez(path, header=json.dumps(header), **arrays)

    @staticmethod
    def load(path: str | Path) -> "QNet":
        with np.load(path) as z:
            header = json.loads(str(z["header"]))
            layers = []
            for i, spec in enumerate(header["layers"]):
                cls = Attention if spec["kind"] == "attn" else Layer
                found = {key: z[f"{key}{i}"].astype(np.int64) for key in cls.ARRAYS if f"{key}{i}" in z}
                layers.append(cls(**found, **spec))
        for layer in layers:
            for key in ("w", "wq", "wk", "wv"):
                w = getattr(layer, key, None)
                if layer.stage == "chip" and w is not None:
                    assert w.min() >= W_MIN and w.max() <= W_MAX
        return QNet(tuple(header["in_shape"]), header["in_bits"], layers, header["meta"])
