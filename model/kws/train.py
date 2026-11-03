"""Train and test the keyword transformer. Needs PyTorch: run with /usr/bin/python3.

    /usr/bin/python3 -m model.kws.train --out model/build/kws/kwt1_s0.pt --seed 0
    /usr/bin/python3 -m model.kws.train --test model/build/kws/kwt1_s0.pt

Training is float, then a few epochs in chip mode (quantization-aware), so the
saved network is the one the chip would run. Every result is reported on the
validation set and on the official test set, whose speakers are never in
training, with a 95% confidence interval.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from . import data
from .features import FRAMES, LogMel
from .model import Config, Net


def wilson(k: int, n: int) -> tuple[float, float]:
    """95% confidence interval for an accuracy of k in n."""
    z, p = 1.96, k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return 100 * (c - h), 100 * (c + h)


class Augment:
    """Done on the GPU, on the waveform and then the spectrogram."""

    def __init__(self, noise: list[np.ndarray], device, seed: int):
        g = np.random.default_rng(seed + 1000)
        crops = []
        for _ in range(4000):
            n = noise[int(g.integers(len(noise)))]
            s = int(g.integers(0, len(n) - data.RATE))
            crops.append(n[s:s + data.RATE])
        self.noise = torch.tensor(np.stack(crops), device=device, dtype=torch.float32)
        self.device = device

    def wave(self, x: torch.Tensor) -> torch.Tensor:
        B, n = x.shape
        x = x.float()
        shift = torch.randint(-1600, 1601, (B, 1), device=self.device)       # up to 100 ms either way
        idx = torch.arange(n, device=self.device)[None, :] - shift
        x = torch.where((idx >= 0) & (idx < n), x.gather(1, idx.clamp(0, n - 1)), torch.zeros_like(x))
        pick = torch.randint(0, len(self.noise), (B,), device=self.device)
        vol = torch.rand(B, 1, device=self.device) * 0.1 * (torch.rand(B, 1, device=self.device) < 0.8)
        return x + vol * self.noise[pick]

    def spec(self, f: torch.Tensor) -> torch.Tensor:
        B, T, M = f.shape
        f = f.clone()
        for _ in range(2):
            t0 = torch.randint(0, T, (B, 1, 1), device=self.device)
            w = torch.randint(0, 21, (B, 1, 1), device=self.device)
            t = torch.arange(T, device=self.device)[None, :, None]
            f = torch.where((t >= t0) & (t < t0 + w), torch.zeros_like(f), f)
            m0 = torch.randint(0, M, (B, 1, 1), device=self.device)
            mw = torch.randint(0, 8, (B, 1, 1), device=self.device)
            m = torch.arange(M, device=self.device)[None, None, :]
            f = torch.where((m >= m0) & (m < m0 + mw), torch.zeros_like(f), f)
        return f


def feats_of(x: torch.Tensor, mel: LogMel, net: Net, batch: int = 1024) -> torch.Tensor:
    return torch.cat([mel(x[i:i + batch]) for i in range(0, len(x), batch)])


@torch.no_grad()
def accuracy(net: Net, feats: torch.Tensor, y: torch.Tensor, batch: int = 512) -> tuple[int, int]:
    net.eval()
    hits = 0
    for i in range(0, len(y), batch):
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=net.mode == "float"):
            hits += int((net(feats[i:i + batch]).argmax(1) == y[i:i + batch]).sum())
    return hits, len(y)


def report(net: Net, sets: dict, label: str) -> dict:
    out = {}
    for name, (f, y) in sets.items():
        k, n = accuracy(net, f, y)
        lo, hi = wilson(k, n)
        out[name] = {"acc": 100 * k / n, "lo": lo, "hi": hi, "n": n}
        print(f"  {label:6} {name:5}: {100 * k / n:6.2f}%  (95% interval {lo:.2f} to {hi:.2f}, {n} clips)", flush=True)
    return out


def calibrate(net: Net, feats: torch.Tensor) -> None:
    net.mode, net.amax = "calibrate", {}
    with torch.no_grad():
        for i in range(0, min(len(feats), 2048), 256):
            net(feats[i:i + 256])
    net.mode = "chip"


def run_epochs(net, opt, sched, xs, ys, mel, aug, epochs, batch, smoothing, log_every, sets, label):
    n = len(ys)
    for ep in range(epochs):
        net.train()
        t0, total, steps = time.time(), 0.0, 0
        perm = torch.randperm(n, device=xs.device)
        for i in range(0, n - batch + 1, batch):
            idx = perm[i:i + batch]
            with torch.no_grad():
                f = aug.spec(mel(aug.wave(xs[idx])))
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=net.mode == "float"):
                loss = F.cross_entropy(net(f), ys[idx], label_smoothing=smoothing)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            sched.step()
            total, steps = total + loss.item(), steps + 1
        if (ep + 1) % log_every == 0 or ep == epochs - 1:
            k, m = accuracy(net, *sets["val"])
            print(f"  {label} epoch {ep + 1:3}/{epochs}: loss {total / steps:.3f}, val {100 * k / m:.2f}%, "
                  f"{time.time() - t0:.1f} s/epoch", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--test", type=Path)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--epochs", type=int, default=140)
    ap.add_argument("--qat-epochs", type=int, default=10)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--qat-batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--wd", type=float, default=0.1)
    ap.add_argument("--dim", type=int, default=64)
    ap.add_argument("--depth", type=int, default=12)
    ap.add_argument("--heads", type=int, default=1)
    ap.add_argument("--mlp", type=int, default=256)
    args = ap.parse_args()
    torch.manual_seed(args.seed)
    dev = torch.device("cuda")
    d = data.load()
    mel = LogMel(dev)
    xs, ys = (torch.tensor(a, device=dev) for a in d["train"])
    sets = {}
    for s in ("val", "test"):
        x, y = d[s]
        sets[s] = (feats_of(torch.tensor(x, device=dev), mel, None), torch.tensor(y, device=dev))
    print(f"train {len(ys)}, val {len(sets['val'][1])}, test {len(sets['test'][1])} clips; "
          f"classes {data.CLASSES}", flush=True)

    if args.test:
        ck = torch.load(args.test, map_location=dev, weights_only=True)
        net = Net(Config(**ck["config"])).to(dev)
        net.load_state_dict(ck["state"])
        net.amax = ck["amax"]
        net.mode = "chip"
        report(net, sets, "chip")
        return

    cfg = Config(dim=args.dim, depth=args.depth, heads=args.heads, mlp=args.mlp, frames=FRAMES)
    net = Net(cfg).to(dev)
    with torch.no_grad():
        f = feats_of(xs[:8192], mel, net)
        net.feat_mean.copy_(f.mean(dim=(0, 1)))
        net.feat_std.copy_(f.std(dim=(0, 1)))
    print(f"{sum(p.numel() for p in net.parameters()):,} parameters", flush=True)
    aug = Augment(d["noise"], dev, args.seed)

    steps = args.epochs * (len(ys) // args.batch)
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=args.wd)
    warm = 10 * (len(ys) // args.batch)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(s, steps) / steps)))
    run_epochs(net, opt, sched, xs, ys, mel, aug, args.epochs, args.batch, 0.1, 10, sets, "float")
    results = {"float": report(net, sets, "float")}
    with torch.no_grad():
        net(sets["val"][0][:1])
    results["macs_per_utterance"] = net.products

    calibrate(net, feats_of(xs[:2048], mel, net))
    results["chip_before_qat"] = report(net, sets, "chip")
    if args.qat_epochs:
        qsteps = args.qat_epochs * (len(ys) // args.qat_batch)
        opt = torch.optim.AdamW(net.parameters(), lr=args.lr / 10, weight_decay=args.wd)
        sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: 0.5 * (1 + math.cos(math.pi * min(s, qsteps) / qsteps)))
        run_epochs(net, opt, sched, xs, ys, mel, aug, args.qat_epochs, args.qat_batch, 0.1, 5, sets, "chip")
        calibrate(net, feats_of(xs[:2048], mel, net))
        results["chip"] = report(net, sets, "chip")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"config": asdict(cfg), "state": net.state_dict(), "amax": net.amax}, args.out)
    results["params"] = sum(p.numel() for p in net.parameters())
    results["args"] = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}
    args.out.with_suffix(".json").write_text(json.dumps(results, indent=1))
    print(f"saved {args.out}", flush=True)


if __name__ == "__main__":
    main()
