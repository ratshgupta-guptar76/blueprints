"""Is the chip's attention holding the network back? A float-only comparison.

Trains the same networks three ways and reports float accuracy on validation,
ImageNetV2 and web photos:

    chip       the attention the chip can run (ReLU, one head, batch norm,
               unsigned queries), before it is turned into integers
    textbook   attention as in a transformer (softmax, 4 heads, layer norm,
               signed queries). The chip cannot run this one.

Run from the repository root (needs PyTorch):

    /usr/bin/python3 -m model.attention_control <web folder> <runs> name="shape" ...
"""
import sys
from pathlib import Path

import numpy as np

from .ml_model import arch, datasets, frontend, preprocess
from .ml_model.train import TrainConfig, train

folder, runs, nets = Path(sys.argv[1]), int(sys.argv[2]), dict(a.split("=", 1) for a in sys.argv[3:])
size = 64
ds, full = datasets.load("imagenette", size), datasets.load("imagenette")
fe = frontend.build("pixels", bits=8)
tr, te = ds.split(0, ds.n_test)
v2 = datasets.load("imagenetv2", size)
web_x, web_y = [], []
for ci, cname in enumerate(ds.classes):
    for f in sorted((folder / cname).glob("*.jpg")):
        web_x.append(preprocess.to_model_image(preprocess.read_image(f), ds.shape, stretch=False))
        web_y.append(ci)
web_x, web_y = np.stack(web_x), np.array(web_y)
extra = {"ImageNetV2": (fe(v2.images), v2.labels), "web": (fe(web_x), web_y)}
n_v2, n_web = len(v2.labels), len(web_y)

print(f"float accuracy, {runs} runs each: mean (lowest to highest). "
      f"validation {len(te)}, ImageNetV2 {n_v2}, web {n_web}")
print(f"{'network':12} {'attention':9}  {'validation':>20}  {'ImageNetV2':>20}  {'web':>20}  {'both independent':>20}")
for name, shape in nets.items():
    styles = ("chip", "textbook") if "attn" in shape else ("none",)
    for style in styles:
        rows = []
        for seed in range(runs):
            cfg = TrainConfig(epochs=200, qat_epochs=0, seed=seed, batchnorm=True, augment=True,
                              float_only=True, attn_textbook=style == "textbook")
            _, rep = train(fe(ds.images[tr]), ds.labels[tr], fe(ds.images[te]), ds.labels[te], ds.shape, 8,
                           len(ds.classes), arch.parse(shape), cfg, src_tr=full.images[tr], extra=extra)
            a, b = rep["float_extra"]["ImageNetV2"], rep["float_extra"]["web"]
            rows.append([rep["float_accuracy"], a, b, (a * n_v2 + b * n_web) / (n_v2 + n_web)])
        rows = 100 * np.array(rows)
        print(f"{name:12} {style:9}  " + "  ".join(
            f"{rows[:, j].mean():5.1f}% ({rows[:, j].min():.1f} to {rows[:, j].max():.1f})".rjust(20)
            for j in range(4)), flush=True)
