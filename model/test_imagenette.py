"""Accuracy of saved Imagenette networks on every kind of data we have:
the official validation photos, the independent ImageNetV2 photos, and a folder
of web photos (one subfolder per class). Run from the repository root:

    python3 -m model.test_imagenette <web folder> <network.npz> ...

Files named name.npz, name_s1.npz, name_s2.npz are training runs of one
network: they are shown as one row, mean (lowest to highest). The last columns
are the chip cost per image: passes, weight sets written for every image, and
estimated v2 cycles (each pass at the width of its input, plus those writes,
without the weight sets that are loaded once). A photonic first layer costs
the chip nothing.
"""
import re
import sys
from pathlib import Path

import numpy as np

from .digital_dcim.chip import V2_WEIGHT_SET, v2_period
from .ml_model import QNet, datasets, frontend, preprocess

folder, files = Path(sys.argv[1]), sys.argv[2:]
groups: dict[str, list[str]] = {}
for path in files:
    groups.setdefault(re.sub(r"_s\d+$", "", Path(path).stem), []).append(path)

first = QNet.load(files[0])
size, shape, classes = first.meta["size"], tuple(first.meta["shape"]), first.meta["classes"]
val = datasets.load("imagenette", size)
_, te = val.split(0, val.n_test)
v2 = datasets.load("imagenetv2", size)
assert v2.classes == classes and v2.test_only
web_x, web_y = [], []
for ci, cname in enumerate(classes):
    for f in sorted((folder / cname).glob("*.jpg")):
        web_x.append(preprocess.to_model_image(preprocess.read_image(f), shape, stretch=False))
        web_y.append(ci)
sets = [("validation", val.images[te], val.labels[te]), ("ImageNetV2", v2.images, v2.labels),
        ("web", np.stack(web_x), np.array(web_y))]
print("images: " + ", ".join(f"{name} {len(y)}" for name, _, y in sets))
print(f"{'network':14} {'runs':>4}  {'validation':>20}  {'ImageNetV2':>20}  {'web':>20}  {'both independent':>20}"
      f"  {'passes':>7} {'writes':>6} {'cycles':>10}")
for name, paths in groups.items():
    rows = []
    for path in paths:
        net = QNet.load(path)
        assert net.meta["size"] == size and net.meta["classes"] == classes
        fe = frontend.build(net.meta["frontend"], **net.meta["frontend_params"])
        hits = [net.predict(fe(x)) == y for _, x, y in sets]
        rows.append([100 * h.mean() for h in hits] + [100 * np.concatenate(hits[1:]).mean()])
    rows = np.array(rows)
    cells = [f"{rows[:, j].mean():5.1f}% ({rows[:, j].min():.1f} to {rows[:, j].max():.1f})" for j in range(4)]
    cost = net.cost()
    cycles = sum(r["chip_passes"] * v2_period(r["input_bits"]) for r in net.plan() if "weights" in r) \
        + cost["sets_per_image"] * V2_WEIGHT_SET
    print(f"{name:14} {len(paths):>4}  " + "  ".join(f"{c:>20}" for c in cells)
          + f"  {cost['chip_passes']:>7,} {cost['sets_per_image']:>6} {cycles:>10,}", flush=True)
