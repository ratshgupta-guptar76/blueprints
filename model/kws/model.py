"""The keyword transformer, and how its multiplies would run on the chip.

The network is the Keyword Transformer layout (Berg et al., 2021): each of the
98 spectrogram frames is a token, a class token is prepended, then pre-norm
transformer blocks, then a linear classifier on the class token.

Every product of two tensors goes through Net._mm, by name. In float mode it is
an ordinary matrix product. In chip mode it is what the chip and the FPGA do:

    weights      8-bit signed, one scale per output (the FPGA applies the scale)
    activations  8-bit. The chip takes 0 to 255; a signed tensor is sent as
                 value + 128 and the FPGA removes 128 x (sum of that output's
                 weights) from the result, which is exact. Probabilities after
                 the softmax are unsigned already.
    keys, values written into the weight array for each utterance: their scale
                 is worked out per utterance from the values themselves
    the product  exact integers (computed in float32, exact below 2^24, asserted)

Layer norm, softmax, GELU, the residual adds, the biases and every scale are
the FPGA's, in float. Training in chip mode passes gradients straight through
the rounding (quantization-aware training).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class Config:
    dim: int = 64
    depth: int = 12
    heads: int = 1
    mlp: int = 256
    classes: int = 12
    n_mels: int = 40
    frames: int = 98
    dropout: float = 0.0


def _round_ste(x: torch.Tensor) -> torch.Tensor:
    return x + (torch.round(x) - x).detach()


class Net(nn.Module):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = c = cfg
        self.mode = "float"                         # float | calibrate | chip
        self.amax: dict[str, float] = {}            # calibrated activation range per product
        self.register_buffer("feat_mean", torch.zeros(c.n_mels))
        self.register_buffer("feat_std", torch.ones(c.n_mels))
        self.embed = nn.Linear(c.n_mels, c.dim)
        self.cls = nn.Parameter(torch.zeros(1, 1, c.dim))
        self.pos = nn.Parameter(torch.randn(1, c.frames + 1, c.dim) * 0.02)
        self.blocks = nn.ModuleList()
        for _ in range(c.depth):
            self.blocks.append(nn.ModuleDict({
                "ln1": nn.LayerNorm(c.dim), "qkv": nn.Linear(c.dim, 3 * c.dim), "proj": nn.Linear(c.dim, c.dim),
                "ln2": nn.LayerNorm(c.dim), "fc1": nn.Linear(c.dim, c.mlp), "fc2": nn.Linear(c.mlp, c.dim)}))
        self.ln = nn.LayerNorm(c.dim)
        self.head = nn.Linear(c.dim, c.classes)
        self.drop = nn.Dropout(c.dropout)
        self.products = 0                           # multiply-accumulates in the last forward pass, per utterance
        self.matvec = None                          # chip mode: send the integer products here (the pin model)
        self.chip = None                            # chip mode: or here, whole tensors at once (model/kws/golden.py)

    # ------------------------------------------------------------------ products
    def _act(self, name: str, a: torch.Tensor, unsigned: bool) -> tuple[torch.Tensor, torch.Tensor]:
        """8-bit activation codes and their scale."""
        if self.mode == "calibrate":
            m = float(a.detach().abs().flatten().float().quantile(0.9999)) if a.numel() < 16_000_000 else \
                float(a.detach().abs().max())
            self.amax[name] = max(self.amax.get(name, 0.0), m)
        s = torch.tensor(max(self.amax[name], 1e-8) / (255.0 if unsigned else 127.0), device=a.device)
        lo, hi = (0, 255) if unsigned else (-127, 127)
        return torch.clamp(_round_ste(a / s), lo, hi), s

    @staticmethod
    def _weights(w: torch.Tensor, dim: int) -> tuple[torch.Tensor, torch.Tensor]:
        """8-bit weight codes, one scale per output (reduce over `dim`, the input axis)."""
        s = w.detach().abs().amax(dim=dim, keepdim=True).clamp(min=1e-8) / 127.0
        return torch.clamp(_round_ste(w / s), -127, 127), s

    def _mm(self, name: str, a: torch.Tensor, w: torch.Tensor, unsigned: bool = False) -> torch.Tensor:
        """a [..., K] @ w [K, N] (or batched w [B, ..., K, N]), as the chip would do it."""
        self.products += a.shape[-1] * w.shape[-1] * (a.numel() // a.shape[-1]) // a.shape[0]
        if self.mode == "float":
            return a @ w
        with torch.autocast(device_type=a.device.type, enabled=False):
            a, w = a.float(), w.float()
            if self.mode == "calibrate":
                self._act(name, a, unsigned)
                return a @ w
            aq, sa = self._act(name, a, unsigned)
            wq, sw = self._weights(w, dim=-2)
            assert 255 * 127 * a.shape[-1] < 2 ** 24
            if self.chip is not None:
                out = self._chip(aq, wq, unsigned)
            else:
                out = aq @ wq if self.matvec is None else self._through(aq, wq, unsigned)  # exact integers
            return out * sa * sw

    def _through(self, aq: torch.Tensor, wq: torch.Tensor, unsigned: bool) -> torch.Tensor:
        """The integer product by way of self.matvec(w [K, N], a [n, K] in 0..255, bits) -> [n, N].
        A signed activation goes in as code + 128; 128 x (sum of each output's weights) is taken
        off afterwards, as the FPGA would."""
        import numpy as np
        a = aq.detach().cpu().numpy().astype(np.int64)
        w = wq.detach().cpu().numpy().astype(np.int64)
        lead = a.shape[:-2] if w.ndim > 2 else ()
        a2 = a.reshape(-1, *a.shape[-2:]) if lead else a.reshape(1, -1, a.shape[-1])
        w2 = w.reshape(-1, *w.shape[-2:]) if lead else w[None]
        out = []
        for i in range(len(a2)):
            wi = w2[i if len(w2) > 1 else 0]
            ai = a2[i] if unsigned else a2[i] + 128
            r = self.matvec(wi, ai, 8)
            if not unsigned:
                r = r - 128 * wi.sum(axis=0)[None, :]
            out.append(r)
        res = np.stack(out).reshape(*a.shape[:-1], w.shape[-1])
        return torch.tensor(res, dtype=torch.float32, device=aq.device)

    def _chip(self, aq: torch.Tensor, wq: torch.Tensor, unsigned: bool) -> torch.Tensor:
        """The integer product by way of self.chip(a [..., M, K] in 0..255, w [..., K, N]) -> [..., M, N],
        with the same +128 offset and correction as _through."""
        a = aq.detach().long() if unsigned else aq.detach().long() + 128
        w = wq.detach().long()
        r = self.chip(a, w)
        if not unsigned:
            r = r - 128 * w.sum(dim=-2, keepdim=True)
        return r.float()

    def _linear(self, name: str, lin: nn.Linear, a: torch.Tensor) -> torch.Tensor:
        return self._mm(name, a, lin.weight.t()) + lin.bias

    # ------------------------------------------------------------------ network
    def forward(self, feats: torch.Tensor) -> torch.Tensor:
        """feats [B, 98, 40] log-mel -> logits [B, classes]."""
        c = self.cfg
        self.products = 0
        x = (feats - self.feat_mean) / self.feat_std
        x = self._linear("embed", self.embed, x)
        x = torch.cat([self.cls.expand(len(x), -1, -1), x], dim=1) + self.pos
        for i, b in enumerate(self.blocks):
            h = b["ln1"](x)
            q, k, v = self._linear(f"{i}.qkv", b["qkv"], h).chunk(3, dim=-1)
            B, T, _ = q.shape
            dh = c.dim // c.heads
            q, k, v = (t.reshape(B, T, c.heads, dh).transpose(1, 2) for t in (q, k, v))
            att = self._mm(f"{i}.score", q, k.transpose(-1, -2)) / math.sqrt(dh)    # keys written as weights
            p = torch.softmax(att.float(), dim=-1).to(q.dtype)
            o = self._mm(f"{i}.mix", p, v, unsigned=True)                           # values written as weights
            o = o.transpose(1, 2).reshape(B, T, c.dim)
            x = x + self.drop(self._linear(f"{i}.proj", b["proj"], o))
            h = b["ln2"](x)
            h = F.gelu(self._linear(f"{i}.fc1", b["fc1"], h))
            x = x + self.drop(self._linear(f"{i}.fc2", b["fc2"], h))
        return self._linear("head", self.head, self.ln(x[:, 0]))
