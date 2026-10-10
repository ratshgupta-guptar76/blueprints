#!/usr/bin/env python3
"""DCIM v2 system model: FPGA -> photonic first layer -> DCIM chip.

What this is
    An arithmetic and scheduling model of the whole demo chain. It trains the
    demo network under the chip's constraints, then runs inference through a
    bit-exact model of the chip, and counts cycles and off-chip arithmetic.

    Stage 1, FPGA     : binarize the 8 x 8 image (one compare per pixel).
    Stage 2, photonic : fixed first layer. Non-overlapping patches, all-positive
                        kernels (a photodiode sums light, it cannot subtract),
                        one comparator per kernel. Output: 1-bit features.
    Stage 3, chip     : INT8 weights, bit-serial unsigned activations, 32 rows by
                        4 outputs per weight set, 21-bit accumulators. Optional
                        bias, ReLU, truncating shift, saturate (requantize).
    Stage 4, FPGA     : whatever arithmetic the chip did not do, then pick the
                        largest of the final scores.

What this is not
    It is not cycle-accurate and it does not model frames, CRC, clock domains,
    or the RTL. The chip arithmetic is derived from the architecture contracts
    in .claude/CLAUDE.md (2, 3, 6, 10, 11, 15), not from the RTL. Cycle counts
    use the estimate formulas of docs/V2_DESIGN_GUIDE.md section 6.4. The
    photonic error model (ring error, detector noise) is a placeholder with
    made-up magnitudes until the real device is measured.

Two plans are compared on the same trained weights
    fpga : the chip returns raw sums. The FPGA adds partial sums of chunked
           layers, adds bias, applies ReLU, scales to 8 bits.
    chip : the chip does bias, ReLU and scaling (requantize). Needs every layer
           to fit one pass (32 inputs or fewer). The final layer's bias is
           folded into spare rows fed with constant activations, so the FPGA
           only picks the largest score.

Usage
    python3 model/dcim_system.py                 # compare front ends
    python3 model/dcim_system.py --sweep         # add photonic error sweeps
    python3 model/dcim_system.py --frontends 2x4k4 --seeds 3 --hidden-bits 4

Needs numpy only. The digits dataset (UCI optdigits test set, 1,797 images,
the same data as scikit-learn's load_digits) is downloaded once to the user
cache directory.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Chip constants (source of truth: src/dcim_pkg.sv)
# ---------------------------------------------------------------------------
ROWS = 32
DW = 8
N_OUT = 4
CLOG2_ROWS = 5
ACC_WIDTH = DW + DW + CLOG2_ROWS    # 21
BIAS_WIDTH = 22                     # proposed width of the saturating bias add
W_MIN, W_MAX = -(1 << (DW - 1)), (1 << (DW - 1)) - 1

DATA_URL = ("https://archive.ics.uci.edu/ml/machine-learning-databases/"
            "optdigits/optdigits.tes")
N_IMAGES = 1797
N_CLASSES = 10
IMG = 8


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_digits(path: str | None) -> tuple[np.ndarray, np.ndarray]:
    """Return (images [n, 8, 8] with ink 0..16, labels [n])."""
    if path is None:
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        file = cache / "dcim_model" / "optdigits.tes"
    else:
        file = Path(path)
    if not file.exists():
        file.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {DATA_URL} -> {file}", file=sys.stderr)
        urllib.request.urlretrieve(DATA_URL, file)
    raw = np.loadtxt(file, delimiter=",", dtype=np.int64)
    if raw.shape != (N_IMAGES, IMG * IMG + 1):
        raise RuntimeError(f"unexpected dataset shape {raw.shape} in {file}")
    return raw[:, :-1].reshape(-1, IMG, IMG), raw[:, -1]


def split(n: int, seed: int, n_test: int) -> tuple[np.ndarray, np.ndarray]:
    perm = np.random.default_rng(seed).permutation(n)
    return perm[n_test:], perm[:n_test]


# ---------------------------------------------------------------------------
# Stage 2: photonic first layer
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FrontEnd:
    name: str
    ph: int             # patch height (0 = no photonic layer, raw pixels)
    pw: int             # patch width
    n_kernels: int      # kernels per patch

    @property
    def n_patches(self) -> int:
        return (IMG // self.ph) * (IMG // self.pw) if self.ph else IMG * IMG

    @property
    def n_features(self) -> int:
        return self.n_patches * self.n_kernels if self.ph else IMG * IMG


def parse_frontend(text: str) -> FrontEnd:
    if text == "pixels":
        return FrontEnd("pixels", 0, 0, 0)
    m = re.fullmatch(r"(\d)x(\d)k(\d+)", text)
    if not m:
        raise ValueError(f"front end '{text}': expected HxWkK (for example 2x2k4) or pixels")
    ph, pw, k = (int(g) for g in m.groups())
    if IMG % ph or IMG % pw:
        raise ValueError(f"front end '{text}': patch must divide {IMG}")
    return FrontEnd(text, ph, pw, k)


def extract_patches(bits: np.ndarray, fe: FrontEnd) -> np.ndarray:
    """[n, 8, 8] -> [n, patches, ph*pw]. Patches do not overlap."""
    n = bits.shape[0]
    if not fe.ph:
        return bits.reshape(n, IMG * IMG, 1)
    v = bits.reshape(n, IMG // fe.ph, fe.ph, IMG // fe.pw, fe.pw)
    return v.transpose(0, 1, 3, 2, 4).reshape(n, fe.n_patches, fe.ph * fe.pw)


@dataclass
class Kernels:
    masks: np.ndarray   # [k, pixels], designed ring transmission, 0 or 1
    thr: np.ndarray     # [k], lit pixels needed for the comparator to fire


def candidate_kernels(ph: int, pw: int) -> list[tuple[np.ndarray, int]]:
    """All-positive kernels a ring bank plus one comparator can realize here:
    every rectangle inside the patch (and the two diagonals of a square patch),
    each with every threshold from 'any pixel lit' to 'all pixels lit'."""
    masks: list[np.ndarray] = []
    for r0 in range(ph):
        for r1 in range(r0, ph):
            for c0 in range(pw):
                for c1 in range(c0, pw):
                    m = np.zeros((ph, pw), dtype=np.int64)
                    m[r0:r1 + 1, c0:c1 + 1] = 1
                    masks.append(m.reshape(-1))
    if ph == pw and ph > 1:
        masks.append(np.eye(ph, dtype=np.int64).reshape(-1))
        masks.append(np.fliplr(np.eye(ph, dtype=np.int64)).reshape(-1))
    return [(m, t) for m in masks for t in range(1, int(m.sum()) + 1)]


def photonic(patches: np.ndarray, kern: Kernels, eff: np.ndarray | None = None,
             det_sigma: float = 0.0, rng: np.random.Generator | None = None) -> np.ndarray:
    """Patches -> 1-bit features [n, patches * k], ordered patch by patch.

    eff is the fabricated transmission (defaults to the designed masks).
    det_sigma is detector noise, in units of one fully lit pixel.
    The comparator level sits half a pixel below the designed threshold.
    """
    light = patches @ (kern.masks if eff is None else eff).T.astype(np.float64)
    if det_sigma:
        light = light + rng.normal(0.0, det_sigma, light.shape)
    return (light >= kern.thr - 0.5).astype(np.int64).reshape(patches.shape[0], -1)


def fabricate(kern: Kernels, sigma: float, rng: np.random.Generator) -> np.ndarray:
    """Fabricated ring transmission: designed value plus Gaussian error on every
    ring (including the ones meant to be dark), kept within 0..1."""
    return np.clip(kern.masks + rng.normal(0.0, sigma, kern.masks.shape), 0.0, 1.0)


def _ridge_accuracy(f_tr, y_tr, f_va, y_va, lam: float = 1.0) -> float:
    a = np.hstack([f_tr, np.ones((len(f_tr), 1))])
    w = np.linalg.solve(a.T @ a + lam * np.eye(a.shape[1]), a.T @ np.eye(N_CLASSES)[y_tr])
    pred = np.hstack([f_va, np.ones((len(f_va), 1))]) @ w
    return float((pred.argmax(axis=1) == y_va).mean())


def select_kernels(patches: np.ndarray, labels: np.ndarray, fe: FrontEnd) -> Kernels:
    """Greedy choice of n_kernels from the candidates, scored by a linear
    classifier on a validation slice of the training data. Test data is never
    seen here. This stands in for 'kernels trained under physical constraints'."""
    cands = candidate_kernels(fe.ph, fe.pw)
    n_va = len(patches) // 5
    blocks, keep, seen = [], [], set()
    for i, (m, t) in enumerate(cands):
        b = (patches @ m >= t).astype(np.float64)
        key = b.tobytes()
        if b.min() == b.max() or key in seen:       # constant or duplicate
            continue
        seen.add(key)
        blocks.append(b)
        keep.append(i)
    chosen: list[int] = []
    for _ in range(fe.n_kernels):
        best, best_acc = -1, -1.0
        for j in range(len(blocks)):
            if j in chosen:
                continue
            f = np.hstack([blocks[c] for c in chosen] + [blocks[j]])
            acc = _ridge_accuracy(f[n_va:], labels[n_va:], f[:n_va], labels[:n_va])
            if acc > best_acc:
                best, best_acc = j, acc
        chosen.append(best)
    return Kernels(np.array([cands[keep[c]][0] for c in chosen]),
                   np.array([cands[keep[c]][1] for c in chosen]))


# ---------------------------------------------------------------------------
# Training (plain numpy, float first, then with the chip's integer arithmetic)
# ---------------------------------------------------------------------------
class Adam:
    def __init__(self, params: list[np.ndarray], lr: float):
        self.p, self.lr, self.t = params, lr, 0
        self.m = [np.zeros_like(x) for x in params]
        self.v = [np.zeros_like(x) for x in params]

    def step(self, grads: list[np.ndarray]) -> None:
        self.t += 1
        for p, g, m, v in zip(self.p, grads, self.m, self.v):
            m *= 0.9
            m += 0.1 * g
            v *= 0.999
            v += 0.001 * g * g
            p -= self.lr * (m / (1 - 0.9 ** self.t)) / (np.sqrt(v / (1 - 0.999 ** self.t)) + 1e-8)


def _softmax(z: np.ndarray) -> np.ndarray:
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


@dataclass
class QNet:
    """The network as the chip sees it. All integers."""
    w1: np.ndarray      # [features, hidden], INT8
    b1: np.ndarray      # [hidden]
    shift: int          # truncating right shift after bias and ReLU
    hmax: int           # hidden saturation, 2^hidden_bits - 1
    w2: np.ndarray      # [hidden, classes], INT8
    b2: np.ndarray      # [classes]


def train(f: np.ndarray, y: np.ndarray, hidden: int, hidden_bits: int,
          rng: np.random.Generator, epochs: int, qat_epochs: int) -> tuple[list[np.ndarray], QNet]:
    """Returns (float parameters before quantization, integer network)."""
    n, n_in = f.shape
    x = f.astype(np.float64)
    onehot = np.eye(N_CLASSES)[y]
    w1 = rng.normal(0, np.sqrt(2 / n_in), (n_in, hidden))
    b1 = np.zeros(hidden)
    w2 = rng.normal(0, np.sqrt(2 / hidden), (hidden, N_CLASSES))
    b2 = np.zeros(N_CLASSES)
    params = [w1, b1, w2, b2]
    batch, wd = 64, 1e-4

    # Float training.
    opt = Adam(params, 5e-3)
    for _ in range(epochs):
        for idx in np.array_split(rng.permutation(n), max(1, n // batch)):
            xb = x[idx]
            z1 = xb @ w1 + b1
            h = np.maximum(z1, 0)
            dz2 = (_softmax(h @ w2 + b2) - onehot[idx]) / len(idx)
            dz1 = (dz2 @ w2.T) * (z1 > 0)
            opt.step([xb.T @ dz1 + wd * w1, dz1.sum(0), h.T @ dz2 + wd * w2, dz2.sum(0)])
    float_params = [p.copy() for p in params]

    # Fix the scales. s1 and s2 map the largest weight to 127. The shift is the
    # smallest that keeps nearly all hidden values inside the hidden range.
    hmax = (1 << hidden_bits) - 1
    s1 = W_MAX / np.abs(w1).max()
    s2 = W_MAX / np.abs(w2).max()
    top = np.percentile(np.maximum(x @ w1 + b1, 0), 99.9) * s1
    shift = max(0, int(np.ceil(np.log2(max(top, 1.0) / hmax))))
    c = s2 * s1 / (1 << shift)          # integer logits = c * float logits

    def quantized() -> QNet:
        return QNet(np.clip(np.round(w1 * s1), W_MIN, W_MAX).astype(np.int64),
                    np.round(b1 * s1).astype(np.int64), shift, hmax,
                    np.clip(np.round(w2 * s2), W_MIN, W_MAX).astype(np.int64),
                    np.round(b2 * c).astype(np.int64))

    # Fine-tune with the integer forward pass (straight-through gradients).
    opt = Adam(params, 1e-3)
    for _ in range(qat_epochs):
        for idx in np.array_split(rng.permutation(n), max(1, n // batch)):
            q = quantized()
            xb = x[idx]
            acc1 = xb @ q.w1 + q.b1
            hq = np.clip(np.floor(acc1 / (1 << shift)), 0, hmax)
            dlog = (_softmax((hq @ q.w2 + q.b2) / c) - onehot[idx]) / len(idx)
            dacc2 = dlog / c
            live = (acc1 > 0) & (acc1 < (hmax + 1) * (1 << shift))
            dacc1 = (dacc2 @ q.w2.T) / (1 << shift) * live
            opt.step([xb.T @ dacc1 * s1, dacc1.sum(0) * s1, hq.T @ dacc2 * s2, dlog.sum(0)])
            np.clip(w1, W_MIN / s1, W_MAX / s1, out=w1)
            np.clip(w2, W_MIN / s2, W_MAX / s2, out=w2)
    return float_params, quantized()


def float_predict(params: list[np.ndarray], f: np.ndarray) -> np.ndarray:
    w1, b1, w2, b2 = params
    return (np.maximum(f @ w1 + b1, 0) @ w2 + b2).argmax(axis=1)


# ---------------------------------------------------------------------------
# Stage 3: the chip, from the architecture contracts
# ---------------------------------------------------------------------------
def _wrap(v: np.ndarray, width: int) -> np.ndarray:
    half = 1 << (width - 1)
    return ((v + half) & ((1 << width) - 1)) - half


def chip_pass(w: np.ndarray, a: np.ndarray, p_bits: int) -> np.ndarray:
    """One vector batch through one weight set. Bit-serial, as the chip does it.

    w [ROWS, N_OUT] INT8, a [n, ROWS] unsigned with p_bits bits.
    Each cycle broadcasts one activation bit-plane, LSB first (contract 6). Each
    weight bit-column is summed down the rows (contracts 2, 3). The MSB column
    is subtracted (contract 10). The lane value is added to a 21-bit signed
    accumulator, shifted by the plane index (contract 11).
    """
    assert w.shape == (ROWS, N_OUT) and a.shape[1] == ROWS
    assert w.min() >= W_MIN and w.max() <= W_MAX
    assert a.min() >= 0 and a.max() < (1 << p_bits)
    wbits = ((w[:, :, None] & 0xFF) >> np.arange(DW)) & 1          # [row, out, bit]
    acc = np.zeros((a.shape[0], N_OUT), dtype=np.int64)
    for plane_idx in range(p_bits):
        plane = (a >> plane_idx) & 1
        colsum = np.einsum("nr,rob->nob", plane, wbits)            # 0..ROWS
        lane = ((colsum[:, :, :DW - 1] << np.arange(DW - 1)).sum(axis=2)
                - (colsum[:, :, DW - 1] << (DW - 1)))
        acc = _wrap(acc + (lane << plane_idx), ACC_WIDTH)
    return acc


def raw_width(p_bits: int) -> int:
    """Raw drain width (contract 15)."""
    return DW + p_bits + CLOG2_ROWS


def bias_rows(b: np.ndarray, p_bits: int, n_spare: int) -> tuple[np.ndarray, np.ndarray] | None:
    """Express a bias as weights on spare rows fed with constant activations.

    Returns (constants [n_spare], weights [n_spare, outputs]) with
    constants @ weights == b exactly, or None if it does not fit.
    """
    amax = (1 << p_bits) - 1
    if n_spare < 2:
        return None
    consts = np.array([amax] * (n_spare - 2) + [min(16, amax), 1], dtype=np.int64)
    weights = np.zeros((n_spare, len(b)), dtype=np.int64)
    rem = b.astype(np.int64).copy()
    for i, cst in enumerate(consts[:-1]):
        weights[i] = np.clip(np.round(rem / cst), W_MIN, W_MAX)
        rem -= weights[i] * cst
    if rem.min() < W_MIN or rem.max() > W_MAX:
        return None
    weights[-1] = rem
    return consts, weights


@dataclass
class Tally:
    """What one plan costs for one image."""
    passes: list[tuple[int, bool]]      # (P, requantized drain) per pass
    weight_sets: int = 0
    fpga_adds: int = 0                  # partial sums and biases
    fpga_relu_scale: int = 0            # ReLU plus shift plus saturate, per value
    fpga_compares: int = 0              # picking the largest score
    bias_saturations: int = 0
    notes: str = ""


def _run_layer(wq: np.ndarray, a: np.ndarray, p_bits: int, tally: Tally,
               requant_drain: bool) -> tuple[np.ndarray, int]:
    """Cut a layer into 32-input chunks and 4-output groups, run every piece.
    Returns (summed raw results [n, outputs], number of chunks)."""
    n_in, n_out = wq.shape
    out = np.zeros((a.shape[0], n_out), dtype=np.int64)
    chunks = -(-n_in // ROWS)
    for g in range(0, n_out, N_OUT):
        for c in range(0, n_in, ROWS):
            wset = np.zeros((ROWS, N_OUT), dtype=np.int64)
            aset = np.zeros((a.shape[0], ROWS), dtype=np.int64)
            blk = wq[c:c + ROWS, g:g + N_OUT]
            wset[:blk.shape[0], :blk.shape[1]] = blk
            aset[:, :blk.shape[0]] = a[:, c:c + ROWS]
            raw = chip_pass(wset, aset, p_bits)
            # A raw drain sends only the low raw_width bits; they must hold the value.
            assert np.array_equal(raw, _wrap(raw, raw_width(p_bits)))
            out[:, g:g + N_OUT] += raw[:, :blk.shape[1]]
            tally.passes.append((p_bits, requant_drain))
            tally.weight_sets += 1
    return out, chunks


def infer(net: QNet, f: np.ndarray, plan: str) -> tuple[np.ndarray, Tally]:
    """Run features through the chip model. Returns (final scores, tally)."""
    hidden_bits = int(net.hmax).bit_length()
    n_hidden, n_cls = net.w2.shape
    tally = Tally(passes=[])
    on_chip = plan == "chip"
    if on_chip and f.shape[1] > ROWS:
        raise ValueError("chip plan needs a first layer of 32 inputs or fewer")

    # Layer 1, 1-bit activations.
    acc1, chunks = _run_layer(net.w1, f, 1, tally, requant_drain=on_chip)
    biased = acc1 + net.b1
    lim = 1 << (BIAS_WIDTH - 1)
    tally.bias_saturations = int(((biased < -lim) | (biased >= lim)).sum())
    h = np.minimum(np.maximum(np.clip(biased, -lim, lim - 1), 0) >> net.shift, net.hmax)
    if not on_chip:
        tally.fpga_adds += (chunks - 1) * n_hidden + n_hidden
        tally.fpga_relu_scale += n_hidden

    # Layer 2, hidden_bits activations. Final scores, never requantized.
    folded = bias_rows(net.b2, hidden_bits, ROWS - n_hidden) if on_chip else None
    if folded is not None:
        consts, wrows = folded
        w2 = np.vstack([net.w2, wrows])
        a2 = np.hstack([h, np.broadcast_to(consts, (h.shape[0], len(consts)))])
        scores, _ = _run_layer(w2, a2, hidden_bits, tally, requant_drain=False)
        tally.notes = f"final bias folded into {int((wrows != 0).any(axis=1).sum())} spare rows"
    else:
        acc2, chunks2 = _run_layer(net.w2, h, hidden_bits, tally, requant_drain=False)
        scores = acc2 + net.b2
        if on_chip:
            tally.notes = "final bias does not fit spare rows: needs a bias-only enable on chip"
        else:
            tally.fpga_adds += (chunks2 - 1) * n_cls + n_cls
    tally.fpga_compares = n_cls - 1
    return scores, tally


# ---------------------------------------------------------------------------
# Cycle estimates (docs/V2_DESIGN_GUIDE.md section 6.4; v1 figures are measured)
# ---------------------------------------------------------------------------
V1_WEIGHT_SET = 1025
V2_WEIGHT_SET = 1024        # lower bound, SPI clock at the core clock rate


def v1_period(p_bits: int) -> int:
    return ROWS * DW + p_bits + 1 + (N_OUT * ACC_WIDTH + 1)


def v2_period(p_bits: int, requantized: bool) -> int:
    load_bits = 1 if p_bits == 1 else DW                # full-width load unless P = 1 (contract 15)
    chain = (ROWS * load_bits) // 4 + 2 + 1 + p_bits    # payload, CRC, compare, compute
    drain = (DW if requantized else raw_width(p_bits)) + 8
    return max(chain, drain)


def cycles(tally: Tally) -> tuple[int, int]:
    """(v1, v2) cycles per image, weights already loaded."""
    return (sum(v1_period(p) for p, _ in tally.passes),
            sum(v2_period(p, rq) for p, rq in tally.passes))


# ---------------------------------------------------------------------------
# Self checks
# ---------------------------------------------------------------------------
def self_check() -> list[str]:
    rng = np.random.default_rng(1)
    lines = []
    for p_bits in range(1, DW + 1):
        w = rng.integers(W_MIN, W_MAX + 1, (ROWS, N_OUT))
        a = rng.integers(0, 1 << p_bits, (64, ROWS))
        assert np.array_equal(chip_pass(w, a, p_bits), a @ w)
    for wv in (W_MIN, W_MAX):
        w = np.full((ROWS, N_OUT), wv)
        a = np.full((1, ROWS), 255)
        assert np.array_equal(chip_pass(w, a, DW), a @ w)
    lines.append("bit-serial chip model equals W^T a for P = 1..8, including the extremes")

    assert (v1_period(1), v1_period(8)) == (343, 350)
    assert (v2_period(1, False), v2_period(1, True), v2_period(8, False)) == (22, 16, 75)
    lines.append("cycle formulas give 343, 350 (v1) and 22, 16, 75 (v2), as documented")

    b = rng.integers(-200000, 200000, 10)
    consts, wr = bias_rows(b, 8, 16)
    assert np.array_equal(consts @ wr, b) and wr.min() >= W_MIN and wr.max() <= W_MAX
    lines.append("bias folded into spare rows reproduces the bias exactly")

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cocotb"))
        import golden.lane_shift_accum as ref
        ref.ROWS, ref.DW, ref.ACC_WIDTH, ref.A_SIGN, ref.W_SIGN = ROWS, DW, ACC_WIDTH, 0, 1
        w = rng.integers(W_MIN, W_MAX + 1, (ROWS, N_OUT))
        a = rng.integers(0, 256, (20, ROWS))
        got = chip_pass(w, a, DW)
        for n in range(a.shape[0]):
            for o in range(N_OUT):
                y = ref.golden_ref(0, 1, 0, 0, [0] * DW)
                for p in range(DW):
                    col = [int((((a[n] >> p) & 1) * ((w[:, o] >> bit) & 1)).sum()) for bit in range(DW)]
                    y = ref.golden_ref(y, 0, 1, p, col)
                assert y == got[n, o]
        lines.append("agrees with cocotb/golden/lane_shift_accum.py on 80 random results")
    except ImportError:
        lines.append("cocotb golden model not importable: cross-check skipped")
    return lines


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------
@dataclass
class Prepared:
    """Everything fixed by one (front end, seed): split, kernels, patches."""
    fe: FrontEnd
    tr: np.ndarray
    te: np.ndarray
    patches: np.ndarray
    labels: np.ndarray
    kern: Kernels | None


def prepare(fe: FrontEnd, bits: np.ndarray, labels: np.ndarray, seed: int, n_test: int) -> Prepared:
    tr, te = split(len(bits), seed, n_test)
    patches = extract_patches(bits, fe)
    kern = select_kernels(patches[tr], labels[tr], fe) if fe.ph else None
    return Prepared(fe, tr, te, patches, labels, kern)


def features(pr: Prepared, idx: np.ndarray, eff=None, det_sigma=0.0, ber=0.0, rng=None) -> np.ndarray:
    if pr.kern is None:
        f = pr.patches[idx].reshape(len(idx), -1)
    else:
        f = photonic(pr.patches[idx], pr.kern, eff, det_sigma, rng)
    if ber:
        f = f ^ (rng.random(f.shape) < ber)
    return f.astype(np.int64)


def accuracy(net: QNet, f: np.ndarray, y: np.ndarray, plan: str = "fpga") -> float:
    scores, _ = infer(net, f, plan)
    return float((scores.argmax(axis=1) == y).mean())


def run_frontend(fe: FrontEnd, bits, labels, args) -> dict:
    res = {"frontend": fe.name, "features": fe.n_features, "float": [], "int": [], "kernels": []}
    for seed in range(args.seeds):
        pr = prepare(fe, bits, labels, seed, args.test_size)
        rng = np.random.default_rng(1000 + seed)
        f_tr, f_te = features(pr, pr.tr), features(pr, pr.te)
        fparams, net = train(f_tr, labels[pr.tr], args.hidden, args.hidden_bits, rng,
                             args.epochs, args.qat_epochs)
        y_te = labels[pr.te]
        res["float"].append(float((float_predict(fparams, f_te) == y_te).mean()))
        scores, tally = infer(net, f_te, "fpga")
        res["int"].append(float((scores.argmax(axis=1) == y_te).mean()))
        plans = {"fpga": tally}
        if fe.n_features <= ROWS:
            scores_chip, plans["chip"] = infer(net, f_te, "chip")
            assert np.array_equal(scores, scores_chip), "plans disagree"
        if pr.kern is not None:
            res["kernels"].append([(m.reshape(fe.ph, fe.pw).tolist(), int(t))
                                   for m, t in zip(pr.kern.masks, pr.kern.thr)])
        if seed == 0:
            res["plans"] = {}
            for name, t in plans.items():
                v1, v2 = cycles(t)
                res["plans"][name] = {
                    "passes": len(t.passes), "weight_sets": t.weight_sets,
                    "v1_cycles": v1, "v2_cycles": v2,
                    "fpga_adds": t.fpga_adds, "fpga_relu_scale": t.fpga_relu_scale,
                    "fpga_compares": t.fpga_compares, "notes": t.notes,
                }
            res["net"] = {
                "shift": net.shift,
                "bias1_bits": int(np.abs(net.b1).max()).bit_length() + 1,
                "bias2_bits": int(np.abs(net.b2).max()).bit_length() + 1,
                "bias_saturations": tally.bias_saturations,
            }
            res["_seed0"] = (pr, net)
    return res


def run_sweep(res: dict, bits, labels, args) -> dict:
    """Photonic error sweeps on one front end. Magnitudes are placeholders."""
    fe = parse_frontend(res["frontend"])
    out = {"fab": [], "det": [], "ber": []}
    for sigma in args.fab_sigmas:
        stale, retrained = [], []
        for seed in range(args.seeds):
            pr = prepare(fe, bits, labels, seed, args.test_size)
            rng = np.random.default_rng(2000 + seed)
            y_tr, y_te = labels[pr.tr], labels[pr.te]
            eff = fabricate(pr.kern, sigma, rng)
            _, net_ideal = train(features(pr, pr.tr), y_tr, args.hidden, args.hidden_bits,
                                 np.random.default_rng(1000 + seed), args.epochs, args.qat_epochs)
            stale.append(accuracy(net_ideal, features(pr, pr.te, eff), y_te))
            _, net_fab = train(features(pr, pr.tr, eff), y_tr, args.hidden, args.hidden_bits,
                               np.random.default_rng(1000 + seed), args.epochs, args.qat_epochs)
            retrained.append(accuracy(net_fab, features(pr, pr.te, eff), y_te))
        out["fab"].append((sigma, float(np.mean(stale)), float(np.mean(retrained))))
    pr, net = res["_seed0"]
    y_te = labels[pr.te]
    for sigma in args.det_sigmas:
        rng = np.random.default_rng(3000)
        accs = [accuracy(net, features(pr, pr.te, None, sigma, 0.0, rng), y_te) for _ in range(10)]
        out["det"].append((sigma, float(np.mean(accs))))
    for ber in args.bers:
        rng = np.random.default_rng(4000)
        accs = [accuracy(net, features(pr, pr.te, None, 0.0, ber, rng), y_te) for _ in range(10)]
        out["ber"].append((ber, float(np.mean(accs))))
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def _pct(vals: list[float]) -> str:
    return f"{100 * np.mean(vals):5.1f} ({100 * min(vals):.1f} to {100 * max(vals):.1f})"


def report(results: list[dict], sweeps: dict, args) -> None:
    b = args.test_size
    print(f"\nAccuracy on {b} held-out images, mean over {args.seeds} splits (lowest to highest)")
    print(f"{'front end':10} {'features':>8}  {'float':22} {'chip arithmetic':22}")
    for r in results:
        print(f"{r['frontend']:10} {r['features']:>8}  {_pct(r['float']):22} {_pct(r['int']):22}")

    print(f"\nCost per image (estimate). Batch column includes weight reloads at batch = {b}.")
    print(f"{'front end':10} {'plan':5} {'passes':>6} {'sets':>5} {'v1':>6} {'v2':>5} {'speedup':>8}"
          f" {'v2 batch':>9} {'FPGA adds':>10} {'ReLU+scale':>11} {'compares':>9}")
    for r in results:
        for name, p in r["plans"].items():
            v2b = p["v2_cycles"] + p["weight_sets"] * V2_WEIGHT_SET / b
            print(f"{r['frontend']:10} {name:5} {p['passes']:>6} {p['weight_sets']:>5} "
                  f"{p['v1_cycles']:>6} {p['v2_cycles']:>5} {p['v1_cycles'] / p['v2_cycles']:>7.1f}x"
                  f" {v2b:>9.0f} {p['fpga_adds']:>10} {p['fpga_relu_scale']:>11} {p['fpga_compares']:>9}")
            if p["notes"]:
                print(f"{'':16} note: {p['notes']}")

    print("\nNumbers the chip needs (split 0)")
    print(f"{'front end':10} {'shift':>5} {'bias 1 bits':>12} {'bias 2 bits':>12} {'22-bit saturations':>19}")
    for r in results:
        n = r["net"]
        print(f"{r['frontend']:10} {n['shift']:>5} {n['bias1_bits']:>12} {n['bias2_bits']:>12}"
              f" {n['bias_saturations']:>19}")

    for r in results:
        if not r["kernels"]:
            continue
        same = sum(k == r["kernels"][0] for k in r["kernels"])
        print(f"\n{r['frontend']}: kernels chosen on split 0 "
              f"(identical on {same} of {len(r['kernels'])} splits). '#' = ring on, 'n of m' = pixels needed")
        fe = parse_frontend(r["frontend"])
        for row in range(fe.ph):
            print("   " + "    ".join("".join("#" if v else "." for v in k[0][row]) + " " * (6 - fe.pw)
                                      for k in r["kernels"][0]))
        print("   " + "    ".join(f"{k[1]} of {sum(map(sum, k[0]))}".ljust(6) for k in r["kernels"][0]))

    for name, sw in sweeps.items():
        print(f"\n{name}: photonic error sweeps (placeholder magnitudes, chip arithmetic accuracy)")
        print(f"  mean over {args.seeds} splits:")
        print("  ring error sigma    trained on ideal    retrained on fabricated")
        for sigma, stale, re_ in sw["fab"]:
            print(f"  {sigma:>16.2f} {100 * stale:>19.1f} {100 * re_:>26.1f}")
        print("  split 0 only, 10 noise draws each:")
        print("  detector noise sigma (pixels)    accuracy")
        for sigma, acc in sw["det"]:
            print(f"  {sigma:>29.2f} {100 * acc:>11.1f}")
        print("  feature bit error rate           accuracy")
        for ber, acc in sw["ber"]:
            print(f"  {ber:>29.4f} {100 * acc:>11.1f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--frontends", nargs="+",
                    default=["2x2k4", "2x2k2", "2x4k4", "4x2k4", "4x4k8", "pixels"],
                    help="HxWkK (patch height x width, K kernels) or 'pixels' (no photonic layer)")
    ap.add_argument("--hidden", type=int, default=16, help="hidden units (32 or fewer)")
    ap.add_argument("--hidden-bits", type=int, default=8, help="bits of the hidden activations (P of layer 2)")
    ap.add_argument("--ink-threshold", type=int, default=8, help="a pixel is 1 when its ink (0..16) is at least this")
    ap.add_argument("--seeds", type=int, default=5, help="number of train/test splits")
    ap.add_argument("--test-size", type=int, default=360)
    ap.add_argument("--epochs", type=int, default=300)
    ap.add_argument("--qat-epochs", type=int, default=150)
    ap.add_argument("--sweep", action="store_true", help="run the photonic error sweeps")
    ap.add_argument("--fab-sigmas", type=float, nargs="+", default=[0.0, 0.05, 0.1, 0.2])
    ap.add_argument("--det-sigmas", type=float, nargs="+", default=[0.0, 0.1, 0.2, 0.3])
    ap.add_argument("--bers", type=float, nargs="+", default=[0.0, 0.001, 0.01, 0.05])
    ap.add_argument("--data", help="path to optdigits.tes (downloaded to the cache if omitted)")
    ap.add_argument("--json", help="also write the results to this file")
    args = ap.parse_args()
    if not 1 <= args.hidden <= ROWS or not 1 <= args.hidden_bits <= DW:
        ap.error("--hidden must be 1..32 and --hidden-bits 1..8")

    print("Self checks")
    for line in self_check():
        print("  ok:", line)

    images, labels = load_digits(args.data)
    bits = (images >= args.ink_threshold).astype(np.int64)
    results, sweeps = [], {}
    for text in args.frontends:
        fe = parse_frontend(text)
        print(f"running {fe.name} ...", file=sys.stderr)
        res = run_frontend(fe, bits, labels, args)
        if args.sweep and fe.ph:
            sweeps[fe.name] = run_sweep(res, bits, labels, args)
        results.append(res)
    report(results, sweeps, args)

    if args.json:
        for r in results:
            r.pop("_seed0", None)
        Path(args.json).write_text(json.dumps({"args": vars(args), "results": results, "sweeps": sweeps}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
