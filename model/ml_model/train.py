"""Training (PyTorch). Only this file needs PyTorch; what it returns is a QNet
of plain integers, and the reported integer accuracy always comes from the
numpy math in network.py, never from PyTorch.

Two phases:
  1. Float training, already inside the hardware's structural rules: ReLU
     everywhere, photonic weights kept at zero or more with a 1-bit output.
     Batch normalisation may be used here; it is folded into the weights and
     biases afterwards (exact), so the hardware never sees it.
  2. Fine-tuning with the forward pass done in integer arithmetic (INT8
     weights, truncating shift, saturation). Gradients pass straight through
     the rounding.

Between the phases the scales are fixed: each layer's largest weight maps to
the top of its range, and each shift is the smallest that keeps nearly all
activations in range.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np

try:
    import torch
    import torch.nn.functional as F
except ImportError as exc:      # the rest of the package works without it
    raise ImportError("training needs PyTorch. The nix shell's python does not have it; "
                      "run with /usr/bin/python3 -m model.ml_model ...") from exc

from .arch import Spec
from .network import Attention, Layer, QNet


@dataclass
class TrainConfig:
    act_bits: int = 8               # bits of the activations between chip layers
    w_bits: int = 8                 # bits of the chip weights (the chip stores 8; fewer is an experiment)
    ph_bits: int = 8                # resolution of the photonic weights
    epochs: int = 30                # float phase
    qat_epochs: int = 10            # integer fine-tune phase
    lr: float = 2e-3
    qat_lr: float = 2e-4
    batch: int = 128
    weight_decay: float = 1e-4
    calib_percentile: float = 99.9  # share of activations that must not saturate
    seed: int = 0
    batchnorm: bool = False         # batch norm on chip layers during the float phase
    augment: bool = False           # random mirror and shift of the training images
    aug_scale: float = 1.0          # below 1: also zoom in to this fraction and out by as much
    aug_color: float = 0.0          # above 0: also vary brightness and contrast by this fraction
    crop_area: float = 0.35         # with source images: smallest crop, as a share of the photo
    log_every: int = 0              # print progress every this many epochs (0 = never)
    float_only: bool = False        # stop after the float phase: no integer network is made
    attn_textbook: bool = False     # attention as in a textbook transformer (softmax, 4 heads,
                                    # layer norm, signed queries). The chip cannot run it, so it
                                    # implies float_only. For comparison with the chip's version.


def _round_ste(x):
    return x + (torch.round(x) - x).detach()


def _step_ste(z, tau):
    """Forward: 1 if z > 0 else 0. Backward: slope of a ramp of half-width tau."""
    ramp = torch.clamp(z / (2 * tau) + 0.5, 0, 1)
    return ramp + ((z > 0).float() - ramp).detach()


def _floor_ste(y, lo: float, hi: float):
    """Forward: floor, then limit to lo..hi. Backward: slope 1 inside the limits."""
    soft = torch.clamp(y, lo, hi)
    return soft + (torch.clamp(torch.floor(y), lo, hi) - soft).detach()


class _Net(torch.nn.Module):
    def __init__(self, specs: list[Spec], in_shape, n_classes: int, in_bits: int, cfg: TrainConfig):
        super().__init__()
        self.cfg, self.g0 = cfg, float((1 << in_bits) - 1)
        h, w, c = in_shape
        self.ops, self.weights, self.biases = [], torch.nn.ParameterList(), torch.nn.ParameterList()
        self.bns = torch.nn.ModuleList()
        self.pos, self.thr = torch.nn.ParameterList(), torch.nn.ParameterList()     # attention only
        self.textbook = torch.nn.ModuleList()       # per attention: layer norm, output projection
        full = list(specs) + [Spec("fc", 1, n_classes)]
        flat, bits = False, in_bits
        for i, sp in enumerate(full):
            last = i == len(full) - 1
            if sp.kind == "attn":
                if flat or bits != cfg.act_bits or not any(o["kind"] == "conv" for o in self.ops):
                    raise ValueError("attn must come after a convolution on the chip, before any fc layer")
                op = {"kind": "attn", "bits": bits, "pi": len(self.pos), "shift_a": 0, "shift_o": 0, "g_s": 1.0,
                      "cs": sp.outputs ** -0.5, "co": 1.0 / (h * w)}    # keep scores and sums near 1 in float
                for name, outs in (("q", sp.outputs), ("k", sp.outputs), ("v", c)):
                    part = {"kind": "conv", "pi": len(self.weights), "stage": "chip", "signed": True,
                            "stride": 1, "groups": 1, "s": 1.0, "g_in": 1.0, "shift": 0, "bn": None}
                    wt = torch.empty(outs, c, 1, 1)
                    torch.nn.init.kaiming_normal_(wt, nonlinearity="relu" if name == "q" else "linear")
                    if cfg.batchnorm:
                        part["bn"] = len(self.bns)
                        self.bns.append(torch.nn.BatchNorm2d(outs))
                    if name == "v":         # the block starts as "change nothing"
                        torch.nn.init.zeros_(self.bns[-1].weight if cfg.batchnorm else wt)
                    self.weights.append(torch.nn.Parameter(wt))
                    self.biases.append(torch.nn.Parameter(torch.zeros(outs)))
                    op[name] = part
                self.pos.append(torch.nn.Parameter(torch.zeros(2, sp.outputs, h, w)))   # queries, keys
                if cfg.attn_textbook:
                    out = torch.nn.Linear(c, c)
                    torch.nn.init.zeros_(out.weight)        # the block starts as "change nothing"
                    self.textbook.append(torch.nn.ModuleList([torch.nn.LayerNorm(c), out]))
                self.thr.append(torch.nn.Parameter(torch.zeros(1)))
                self.ops.append(op)
                continue
            if sp.kind == "pool":
                k = sp.k or h                               # k = 0: the whole map
                if h % k or w % k or flat:
                    raise ValueError(f"pool {k} x {k} does not fit a {h} x {w} image")
                h, w = h // k, w // k
                self.ops.append({"kind": "pool", "k": k})
                continue
            op = {"kind": "dense" if sp.kind == "fc" else "conv", "pi": len(self.weights),
                  "stage": "photonic" if sp.kind == "ph" else "chip",
                  "act": "none" if last else ("step" if sp.kind == "ph" and sp.out_bits == 1 else "relu"),
                  "signed": sp.signed, "bits": sp.out_bits if sp.kind == "ph" else cfg.act_bits,
                  "k": sp.k, "stride": sp.stride, "pad": 0, "center": False, "groups": 1,
                  "s": 1.0, "g_in": 1.0, "shift": 0, "tau": 1.0}
            if op["kind"] == "conv":
                op["pad"] = 0 if sp.kind == "ph" and sp.stride == sp.k else (sp.k - 1) // 2
                if sp.kind == "dw":                         # one filter per feature map
                    sp = Spec("dw", sp.k, c, sp.stride)
                    op["groups"] = c
                wt = torch.empty(sp.outputs, c // op["groups"], sp.k, sp.k)
                h = (h + 2 * op["pad"] - sp.k) // sp.stride + 1
                w = (w + 2 * op["pad"] - sp.k) // sp.stride + 1
                if h < 1 or w < 1:
                    raise ValueError("the image is too small for these layers")
                c = sp.outputs
            else:
                if not flat:
                    h, w, c, flat = 1, 1, h * w * c, True
                wt = torch.empty(sp.outputs, c)
                c = sp.outputs
            torch.nn.init.kaiming_normal_(wt, nonlinearity="relu")
            if op["stage"] == "photonic" and not op["signed"]:
                wt = wt.abs()
            op["bn"] = None
            if cfg.batchnorm and op["act"] == "relu" and op["stage"] == "chip":
                op["bn"] = len(self.bns)
                self.bns.append(torch.nn.BatchNorm2d(sp.outputs) if op["kind"] == "conv"
                                else torch.nn.BatchNorm1d(sp.outputs))
            self.weights.append(torch.nn.Parameter(wt))
            self.biases.append(torch.nn.Parameter(torch.zeros(sp.outputs)))
            self.ops.append(op)
            bits = 1 if op["act"] == "step" else op["bits"]
        # Only a chip layer that sees the raw pixels trains on mean-removed input.
        first = next(op for op in self.ops if op["kind"] != "pool")
        first["center"] = first["stage"] == "chip"
        self.mean = None

    def linear_ops(self):
        """Every op that owns a weight tensor, the three inside attention included."""
        for op in self.ops:
            if op["kind"] == "attn":
                yield from (op["q"], op["k"], op["v"])
            elif op["kind"] != "pool":
                yield op

    def _attention(self, op, x, mode: str, taps: list | None):
        """The Attention layer of network.py. x [n, c, h, w] -> the same shape."""
        n, c, h, w = x.shape
        if self.cfg.attn_textbook:
            assert mode == "float", "textbook attention has no integer form"
            norm, out = self.textbook[op["pi"]]
            tokens = x.flatten(2).transpose(1, 2)                       # [n, token, c]
            t = norm(tokens).transpose(1, 2).reshape(n, c, h, w)
            heads = 4
            q, k, v = (F.conv2d(t, self.weights[op[name]["pi"]], self.biases[op[name]["pi"]])
                       for name in "qkv")
            q, k = q + self.pos[op["pi"]][0], k + self.pos[op["pi"]][1]
            q, k, v = (z.flatten(2).reshape(n, heads, -1, h * w).transpose(2, 3) for z in (q, k, v))
            a = torch.softmax(q @ k.transpose(2, 3) / q.shape[-1] ** 0.5, dim=-1)   # [n, head, token, token]
            o = (a @ v).transpose(1, 2).reshape(n, h * w, c)
            return F.relu(tokens + out(o)).transpose(1, 2).reshape(n, c, h, w)
        pos, thr = self.pos[op["pi"]], self.thr[op["pi"]]
        top = float((1 << op["bits"]) - 1)
        lo, hi = self.weight_range(op["k"])         # keys and values are stored as chip weights
        z = {}
        for i, name in enumerate("qkv"):
            part = op[name]
            wt, b = self.weights[part["pi"]], self.biases[part["pi"]]
            if mode == "float":
                t = F.conv2d(x, wt, b)
                if part["bn"] is not None:
                    t = self.bns[part["bn"]](t)
                if name != "v":
                    t = t + pos[i]
            else:
                scale = part["g_in"] * part["s"]
                t = F.conv2d(x, torch.clamp(_round_ste(wt * part["s"]), lo, hi), _round_ste(b * scale))
                if name != "v":
                    t = t + _round_ste(pos[i] * scale)
                t = t / (1 << part["shift"])
            z[name] = t.flatten(2).transpose(1, 2)          # [n, token, numbers]
        tokens = x.flatten(2).transpose(1, 2)
        if mode == "float":
            s = F.relu(z["q"]) @ z["k"].transpose(1, 2) * op["cs"] + thr
            if taps is not None:
                taps.append((op, tuple(_sample(t) for t in (z["q"], z["k"], z["v"], s))))
            y = F.relu(tokens + F.relu(s) @ z["v"] * op["co"])
        else:
            q, k, v = _floor_ste(z["q"], 0, top), _floor_ste(z["k"], lo, hi), _floor_ste(z["v"], lo, hi)
            s = q @ k.transpose(1, 2) + _round_ste(thr * op["g_s"])
            a = _floor_ste(s / (1 << op["shift_a"]), 0, top)
            y = _floor_ste((a @ v) / (1 << op["shift_o"]) + tokens, 0, top)
        return y.transpose(1, 2).reshape(n, c, h, w)

    def _linear(self, op, x, w, b):
        if op["kind"] == "conv":
            return F.conv2d(x, w, b, stride=op["stride"], groups=op["groups"])
        return x @ w.T + b

    def forward(self, a, mode: str, taps: list | None = None):
        """a: integer-valued float tensor [n, c, h, w]. mode: "float" or "int"."""
        cfg = self.cfg
        x = a / self.g0 if mode == "float" else a
        for op in self.ops:
            if op["kind"] == "pool":
                x = F.max_pool2d(x, op["k"])
                continue
            if op["kind"] == "attn":
                x = self._attention(op, x, mode, taps)
                continue
            w, b = self.weights[op["pi"]], self.biases[op["pi"]]
            if op["kind"] == "conv":
                x = F.pad(x, (op["pad"],) * 4)
            elif x.dim() == 4:
                x = x.permute(0, 2, 3, 1).flatten(1)        # height, width, channel order
            if mode == "float":
                if op["center"]:
                    x = x - self.mean
                z = self._linear(op, x, w, b)
                if op["bn"] is not None:
                    z = self.bns[op["bn"]](z)
            else:
                scale = op["g_in"] * op["s"]                # integer acc = scale * float z
                lo, hi = self.weight_range(op)
                acc = self._linear(op, x, torch.clamp(_round_ste(w * op["s"]), lo, hi), _round_ste(b * scale))
                z = acc / scale
            if taps is not None:
                taps.append((op, _sample(z if mode == "float" else acc)))
            if op["act"] == "none":
                return z
            if op["act"] == "step":
                x = _step_ste(z, op["tau"])
            elif mode == "float":
                x = F.relu(z)
            else:
                y = acc / (1 << op["shift"])
                amax = float((1 << op["bits"]) - 1)
                soft = torch.clamp(y, 0, amax)
                x = soft + (torch.clamp(torch.floor(y), 0, amax) - soft).detach()
        raise AssertionError("no final layer")

    def weight_range(self, op) -> tuple[float, float]:
        """Integer range of a layer's weights."""
        if op["stage"] == "chip":
            half = 1 << (self.cfg.w_bits - 1)
            return float(-half), float(half - 1)
        top = float((1 << self.cfg.ph_bits) - 1)
        return (-top if op["signed"] else 0.0), top

    def fold_batchnorm(self) -> None:
        """z = k (W^T x + b - mu) + beta, with k = gamma / sigma, becomes
        (k W)^T x + (k (b - mu) + beta). Exact for the stored statistics."""
        with torch.no_grad():
            for op in self.linear_ops():
                if op["bn"] is None:
                    continue
                bn, w, b = self.bns[op["bn"]], self.weights[op["pi"]], self.biases[op["pi"]]
                k = bn.weight / torch.sqrt(bn.running_var + bn.eps)
                w.mul_(k.view(-1, *([1] * (w.dim() - 1))))
                b.copy_(k * (b - bn.running_mean) + bn.bias)
                op["bn"] = None

    def project(self, mode: str) -> None:
        """Keep the weights inside what the hardware can hold."""
        with torch.no_grad():
            for op in self.linear_ops():
                w = self.weights[op["pi"]]
                lo, hi = self.weight_range(op)
                if mode == "int":
                    w.clamp_(lo / op["s"], hi / op["s"])
                elif lo == 0:
                    w.clamp_(min=0)


def _sample(t):
    """At most a million of the values, picked at random. Enough to set a scale,
    and it keeps the scale-fixing step from holding every layer's output."""
    t = t.detach().flatten()
    if t.numel() > 1_000_000:
        t = t[torch.randint(0, t.numel(), (1_000_000,), device=t.device)]
    return t


def _quantile(t, pct: float) -> float:
    return float(torch.quantile(_sample(t).float(), pct / 100))


def train(a_tr: np.ndarray, y_tr: np.ndarray, a_te: np.ndarray, y_te: np.ndarray,
          in_shape: tuple[int, int, int], in_bits: int, n_classes: int,
          specs: list[Spec], cfg: TrainConfig, src_tr: np.ndarray | None = None,
          extra: dict[str, tuple[np.ndarray, np.ndarray]] | None = None) -> tuple[QNet | None, dict]:
    """a_*: front end output, integers of in_bits bits, any shape that reshapes
    to [n, height, width, channels]. Returns (integer network, report).

    y_*: one class index per image, or (float32, one column per class, 0 or 1)
    a yes/no per class when several classes can be in one image.

    src_tr, if given, holds the training photos at a larger size, uint8
    [n, S, S, channels]. Every training batch is then cut fresh from them: a
    random part of each photo, shrunk to the network's input size. This is the
    same crop-then-shrink a live photo goes through.

    extra: more test sets, name -> (inputs like a_te, labels). Their float
    accuracy is added to the report. With cfg.float_only the function stops
    after the float phase and returns (None, report)."""
    torch.manual_seed(cfg.seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    def to_dev(a):
        return torch.from_numpy(np.ascontiguousarray(a.reshape(-1, *in_shape))).to(dev).permute(0, 3, 1, 2)

    xtr, xte = to_dev(a_tr), to_dev(a_te)
    ytr, yte = torch.from_numpy(y_tr).to(dev), torch.from_numpy(y_te).to(dev)
    net = _Net(specs, in_shape, n_classes, in_bits, cfg).to(dev)
    n = len(ytr)
    calib = xtr[torch.randperm(n, device=dev)[:2000]].float()
    xsrc = None if src_tr is None else torch.from_numpy(np.ascontiguousarray(src_tr)).to(dev).permute(0, 3, 1, 2)

    def cropped(idx):
        """Random part of each source photo (area, proportions, position, mirror),
        shrunk to the input size and cut to in_bits bits like the front end does."""
        m, (h, w, c) = len(idx), in_shape
        area = torch.empty(m, device=dev).uniform_(cfg.crop_area, 1)
        ratio = torch.exp(torch.empty(m, device=dev).uniform_(np.log(3 / 4), np.log(4 / 3)))
        sw, sh = torch.sqrt(area * ratio).clamp(max=1), torch.sqrt(area / ratio).clamp(max=1)
        theta = torch.zeros(m, 2, 3, device=dev)
        theta[:, 0, 0] = sw * (torch.randint(0, 2, (m,), device=dev) * 2 - 1)
        theta[:, 1, 1] = sh
        theta[:, 0, 2] = (torch.rand(m, device=dev) * 2 - 1) * (1 - sw)
        theta[:, 1, 2] = (torch.rand(m, device=dev) * 2 - 1) * (1 - sh)
        x = F.grid_sample(xsrc[idx].float(), F.affine_grid(theta, [m, c, h, w], align_corners=False),
                          mode="bilinear", padding_mode="border", align_corners=False)
        if cfg.aug_color > 0:
            k = cfg.aug_color
            mean = x.mean(dim=(1, 2, 3), keepdim=True)
            x = (x - mean) * torch.empty(m, 1, 1, 1, device=dev).uniform_(1 - k, 1 + k) + mean
            x = x * torch.empty(m, 1, 1, 1, device=dev).uniform_(1 - k, 1 + k)
        return torch.floor(torch.clamp(torch.round(x), 0, 255) / (1 << (8 - in_bits)))

    # Data-dependent start: input mean for a chip first layer; for a photonic
    # first layer, thresholds at the median so about half the outputs fire.
    first = next(op for op in net.ops if op["kind"] != "pool")
    with torch.no_grad():
        x0 = calib / net.g0
        if first["center"]:
            net.mean = x0.mean(dim=(0, 2, 3), keepdim=True) if first["kind"] == "conv" \
                else x0.permute(0, 2, 3, 1).flatten(1).mean(dim=0)
        if first["act"] == "step":
            z = F.conv2d(F.pad(x0, (first["pad"],) * 4), net.weights[0], None, stride=first["stride"])
            net.biases[0].copy_(-z.transpose(0, 1).flatten(1).median(dim=1).values)
            first["tau"] = float(z.std())

    def accuracy(mode: str, x=None, y=None) -> float:
        x, y = (xte, yte) if x is None else (x, y)
        net.eval()
        hits = 0
        with torch.no_grad():
            for i in range(0, len(y), 1000):
                out = net(x[i:i + 1000].float(), mode)
                # Labels with one column per class: several classes may be right
                # at once, a class is "present" when its score is above zero, and
                # the figure is the share of yes/no answers that are right.
                hits += int(((out > 0) == (y[i:i + 1000] > 0.5)).sum() if y.dim() == 2
                            else (out.argmax(1) == y[i:i + 1000]).sum())
        return hits / y.numel()

    def augmented(x):
        """Mirror half the images and shift each by up to 4 pixels, filling with
        zeros. Integers stay integers, so this works in both phases."""
        m, _, h, w = x.shape
        x = torch.where(torch.rand(m, 1, 1, 1, device=dev) < 0.5, x.flip(3), x)
        if cfg.aug_scale < 1 or cfg.aug_color > 0:
            # Varied framing: the object may be larger, smaller or off centre,
            # brighter or flatter. Resampled values are rounded back to integers.
            s = torch.empty(m, device=dev).uniform_(cfg.aug_scale, 1 / cfg.aug_scale)
            reach = (1 - s).abs() + 0.15
            theta = torch.zeros(m, 2, 3, device=dev)
            theta[:, 0, 0] = theta[:, 1, 1] = s
            theta[:, :, 2] = (torch.rand(m, 2, device=dev) * 2 - 1) * reach[:, None]
            x = F.grid_sample(x, F.affine_grid(theta, list(x.shape), align_corners=False),
                              mode="bilinear", padding_mode="zeros", align_corners=False)
            if cfg.aug_color > 0:
                c = cfg.aug_color
                mean = x.mean(dim=(1, 2, 3), keepdim=True)
                x = (x - mean) * torch.empty(m, 1, 1, 1, device=dev).uniform_(1 - c, 1 + c) + mean
                x = x * torch.empty(m, 1, 1, 1, device=dev).uniform_(1 - c, 1 + c)
            return torch.clamp(torch.round(x), 0, net.g0)
        x = F.pad(x, (4, 4, 4, 4))
        oy, ox = torch.randint(0, 9, (m,), device=dev), torch.randint(0, 9, (m,), device=dev)
        rows = (oy[:, None] + torch.arange(h, device=dev))[:, :, None]
        cols = (ox[:, None] + torch.arange(w, device=dev))[:, None, :]
        return x[torch.arange(m, device=dev)[:, None, None], :, rows, cols].permute(0, 3, 1, 2)

    def run(mode: str, epochs: int, lr: float) -> None:
        if not epochs:
            return
        # With batch norm the float phase uses SGD with momentum, the usual
        # recipe for convolutional networks. Otherwise Adam.
        if mode == "float" and cfg.batchnorm:
            opt = torch.optim.SGD(net.parameters(), lr=0.05, momentum=0.9, nesterov=True, weight_decay=5e-4)
        else:
            opt = torch.optim.Adam(net.parameters(), lr=lr, weight_decay=cfg.weight_decay)
        steps = epochs * -(-n // cfg.batch)
        sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=opt.param_groups[0]["lr"], total_steps=steps,
                                                    pct_start=0.15 if mode == "float" else 0.05)
        for epoch in range(epochs):
            net.train()
            perm = torch.randperm(n, device=dev)
            for i in range(0, n, cfg.batch):
                idx = perm[i:i + cfg.batch]
                if xsrc is not None:
                    xb = cropped(idx)
                else:
                    xb = xtr[idx].float()
                    if cfg.augment:
                        xb = augmented(xb)
                loss = (F.binary_cross_entropy_with_logits if ytr.dim() == 2 else F.cross_entropy)(
                    net(xb, mode), ytr[idx])
                opt.zero_grad(set_to_none=True)
                loss.backward()
                opt.step()
                sched.step()
                net.project(mode)
            if cfg.log_every and ((epoch + 1) % cfg.log_every == 0 or epoch + 1 == epochs):
                print(f"  {mode} epoch {epoch + 1}/{epochs}: loss {loss.item():.3f}, "
                      f"held-out {100 * accuracy(mode):.1f}%", file=sys.stderr, flush=True)

    # Phase 1: float.
    run("float", cfg.epochs, cfg.lr)
    float_acc = accuracy("float")
    float_extra = {name: accuracy("float", to_dev(a), torch.from_numpy(y).to(dev))
                   for name, (a, y) in (extra or {}).items()}
    if cfg.float_only or cfg.attn_textbook:
        return None, {"float_accuracy": float_acc, "float_extra": float_extra, "device": dev}
    net.eval()
    net.fold_batchnorm()

    # Fold the input mean into the first bias: W^T (x - m) + b = W^T x + (b - W^T m).
    # Exact at the image edge too, because the mean is removed after padding.
    with torch.no_grad():
        if first["center"]:
            w = net.weights[first["pi"]]
            net.biases[first["pi"]] -= (w * net.mean).sum(dim=(1, 2, 3)) if first["kind"] == "conv" else w @ net.mean
            first["center"] = False

    # Fix the scales. s maps a layer's largest weight to the top of its range.
    # g is the scale of the integers flowing between layers (integer = g * float).
    with torch.no_grad():
        taps: list = []
        net.eval()
        net(calib, "float", taps)
        g = net.g0

        def weight_scale(op) -> float:
            """Integer weight = this times the float weight."""
            w = net.weights[op["pi"]]
            # With few weight levels one stray large weight would waste them, so the
            # scale is set from the bulk of the weights (three standard deviations).
            top_w = float(w.abs().max())
            if op["stage"] == "chip" and cfg.w_bits < 8:
                top_w = min(top_w, 3 * float(w.std()))
            return net.weight_range(op)[1] / max(top_w, 1e-12)

        def fit(values, scale: float, limit: float) -> int:
            """Smallest right shift that keeps nearly all of scale * values within limit."""
            top = _quantile(values, cfg.calib_percentile) * scale
            return max(0, int(np.ceil(np.log2(max(top, 1.0) / limit))))

        for op, z in taps:
            if op["kind"] == "attn":
                zq, zk, zv, zs = z
                top, hi = float((1 << op["bits"]) - 1), net.weight_range(op["k"])[1]
                for part, values, limit in ((op["q"], F.relu(zq), top), (op["k"], zk.abs(), hi)):
                    part["s"], part["g_in"] = weight_scale(part), g
                    part["shift"] = fit(values, g * part["s"], limit)
                gq, gk = (g * op[name]["s"] / (1 << op[name]["shift"]) for name in "qk")
                op["g_s"] = gq * gk / op["cs"]
                op["shift_a"] = fit(F.relu(zs), op["g_s"], top)
                ga = op["g_s"] / (1 << op["shift_a"])
                # The output is added to the input, so both must be on the same
                # scale. That fixes the value weights' scale up to a power of
                # two: the largest that still fits the weight range is used.
                part = op["v"]
                m = int(np.floor(np.log2(weight_scale(part) * ga / op["co"])))
                part["s"], part["g_in"] = op["co"] * 2.0 ** m / ga, g
                part["shift"] = min(fit(zv.abs(), g * part["s"], hi), m)
                op["shift_o"] = m - part["shift"]
                if m < 0:
                    raise ValueError("attention output is too large for the scale of its input")
                continue
            op["s"], op["g_in"] = weight_scale(op), g
            if op["act"] == "relu":
                op["shift"] = fit(F.relu(z), g * op["s"], (1 << op["bits"]) - 1)
                g = g * op["s"] / (1 << op["shift"])
            elif op["act"] == "step":
                g = 1.0

    # Phase 2: integer forward.
    net.project("int")
    run("int", cfg.qat_epochs, cfg.qat_lr)

    # Export plain integers.
    layers, bits = [], in_bits
    with torch.no_grad():
        for op in net.ops:
            if op["kind"] == "pool":
                layers.append(Layer("pool", k=op["k"], stride=op["k"], out_bits=bits))
                continue
            if op["kind"] == "attn":
                found = {"ba": int(torch.round(net.thr[op["pi"]] * op["g_s"]))}
                for i, name in enumerate("qkv"):
                    part = op[name]
                    scale = part["g_in"] * part["s"]
                    wq = torch.clamp(torch.round(net.weights[part["pi"]] * part["s"]), *net.weight_range(part))
                    bq = torch.round(net.biases[part["pi"]] * scale)
                    if name != "v":     # position terms: one bias per token
                        bq = bq + torch.round(net.pos[op["pi"]][i] * scale).permute(1, 2, 0).flatten(0, 1)
                    found["w" + name] = wq[:, :, 0, 0].T.cpu().numpy().astype(np.int64)
                    found["b" + name] = bq.cpu().numpy().astype(np.int64)
                    found["shift_" + name] = part["shift"]
                layers.append(Attention(shift_a=op["shift_a"], shift_o=op["shift_o"], out_bits=op["bits"],
                                        w_bits=cfg.w_bits, **found))
                continue
            w, b = net.weights[op["pi"]], net.biases[op["pi"]]
            wq = torch.clamp(torch.round(w * op["s"]), *net.weight_range(op))
            wq = wq.permute(2, 3, 1, 0).reshape(-1, wq.shape[0]) if op["kind"] == "conv" else wq.T
            bq = torch.round(b * op["g_in"] * op["s"])
            bits = {"relu": op["bits"], "step": 1, "none": bits}[op["act"]]
            layers.append(Layer(op["kind"], wq.cpu().numpy().astype(np.int64), bq.cpu().numpy().astype(np.int64),
                                shift=op["shift"], act=op["act"], out_bits=bits, k=op["k"],
                                stride=op["stride"], pad=op["pad"], stage=op["stage"], groups=op["groups"]))
    qnet = QNet(tuple(in_shape), in_bits, layers)

    # The training-time integer forward and the exported network should agree.
    with torch.no_grad():
        net.eval()
        probe = slice(0, min(256, len(y_te)))
        out = net(xte[probe].float(), "int")
        torch_pick = ((out > 0) if yte.dim() == 2 else out.argmax(1)).cpu().numpy()
    numpy_pick = qnet.scores(a_te[probe]) > 0 if yte.dim() == 2 else qnet.predict(a_te[probe])
    agree = float((torch_pick == numpy_pick).mean())
    return qnet, {"float_accuracy": float_acc, "float_extra": float_extra, "torch_int_accuracy": accuracy("int"),
                  "export_agreement": agree, "device": dev}
