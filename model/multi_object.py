"""Pictures with several objects: does attention help when the answer depends
on more than one part of the image?

Every picture is four photographs side by side (two by two), each 32 x 32, so
the picture is 64 x 64 like the single-photograph demo. Two tasks:

    contents   which of the ten kinds of object are in the picture (a yes or no
               for each kind; several can be right)
    odd        three photographs show one kind of object and one shows
               another: which corner holds the odd one (4 answers)

Training pictures are built from the Imagenette training photographs, each cut
and mirrored at random. Test pictures are built three ways, from photographs
the network never trained on: the Imagenette validation photographs, the
ImageNetV2 photographs, and a folder of web photographs. Accuracy is integer
(hardware math), mean (lowest to highest) over the training runs.

Run from the repository root (needs PyTorch):

    /usr/bin/python3 -m model.multi_object <web folder> <task> <runs> name="shape" ...
"""
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from .digital_dcim import Chip
from .digital_dcim.chip import V2_WEIGHT_SET, v2_period
from .fpga import Fpga
from .ml_model import arch, datasets, frontend, preprocess
from .ml_model.train import TrainConfig, train

folder, task, runs = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
nets = dict(a.split("=", 1) for a in sys.argv[4:])
assert task in ("contents", "odd")
TILE, N_TRAIN, N_VAL, N_OTHER = 32, 60000, 4000, 1000
EPOCHS, QAT = 40, 8
if os.environ.get("MULTI_QUICK"):        # a short trial of the script itself
    N_TRAIN, N_VAL, N_OTHER, EPOCHS, QAT = 3000, 300, 200, 2, 1


def pictures(images, labels, n, rng, cut):
    """n pictures of four tiles. images: the photographs to draw from (any
    size when cut, else TILE x TILE). Returns (pictures, answers)."""
    by_class = [np.flatnonzero(labels == c) for c in range(10)]
    out = np.empty((n, 2 * TILE, 2 * TILE, 3), dtype=np.uint8)
    if task == "contents":
        kinds = rng.integers(0, 10, (n, 4))
        answers = np.zeros((n, 10), dtype=np.float32)
        np.put_along_axis(answers, kinds, 1.0, axis=1)
    else:
        usual, answers = rng.integers(0, 10, n), rng.integers(0, 4, n)
        kinds = np.repeat(usual[:, None], 4, axis=1)
        kinds[np.arange(n), answers] = (usual + rng.integers(1, 10, n)) % 10
    for i in range(n):
        used = set()
        for t in range(4):
            pool = by_class[kinds[i, t]]
            pick = int(rng.choice(pool))
            while pick in used and len(pool) > 4:       # four different photographs
                pick = int(rng.choice(pool))
            used.add(pick)
            img = images[pick]
            if cut:     # a random part of the photograph (35% to 100% of it), shrunk, maybe mirrored
                side = img.shape[0]
                s = int(side * np.sqrt(rng.uniform(0.35, 1)))
                x0, y0 = rng.integers(0, side - s + 1, 2)
                img = np.asarray(Image.fromarray(img).resize((TILE, TILE), Image.BOX, box=(x0, y0, x0 + s, y0 + s)))
                if rng.random() < 0.5:
                    img = img[:, ::-1]
            r, c = divmod(t, 2)
            out[i, r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE] = img
    return out, answers


full, small, v2 = datasets.load("imagenette"), datasets.load("imagenette", TILE), datasets.load("imagenetv2", TILE)
tr, te = full.split(0, full.n_test)
web_x, web_y = [], []
for ci, cname in enumerate(full.classes):
    for f in sorted((folder / cname).glob("*.jpg")):
        web_x.append(preprocess.to_model_image(preprocess.read_image(f), (TILE, TILE, 3), stretch=False))
        web_y.append(ci)
rng = np.random.default_rng(0)
x_tr, y_tr = pictures(full.images[tr], full.labels[tr], N_TRAIN, rng, cut=True)
tests = {"validation": pictures(small.images[te], small.labels[te], N_VAL, rng, cut=False),
         "ImageNetV2": pictures(v2.images, v2.labels, N_OTHER, rng, cut=False),
         "web": pictures(np.stack(web_x), np.array(web_y), N_OTHER, rng, cut=False)}
fe = frontend.build("pixels", bits=8)
shape = x_tr.shape[1:]
Image.fromarray(np.concatenate(list(tests["validation"][0][:8]), axis=1)).save(f"model/build/multi_{task}_examples.png")


def score(net, x, y):
    """(share of answers right, share of pictures with every answer right)."""
    s = net.scores(fe(x))
    if task == "contents":
        right = (s > 0) == (y > 0.5)
        return right.mean(), right.all(axis=1).mean()
    right = s.argmax(axis=1) == y
    return right.mean(), right.mean()


print(f"task: {task}. {N_TRAIN} training pictures, tests: "
      + ", ".join(f"{k} {len(v[1])}" for k, v in tests.items())
      + (". Figures: share of pictures with all ten yes/no answers right." if task == "contents"
         else ". Figures: share of pictures answered right (guessing gives 25%)."))
print(f"{'network':12} {'runs':>4}  {'validation':>20}  {'ImageNetV2':>20}  {'web':>20}  {'passes':>7} {'writes':>6} {'cycles':>10}")
for name, text in nets.items():
    rows = []
    for seed in range(runs):
        cfg = TrainConfig(epochs=EPOCHS, qat_epochs=QAT, seed=seed, batchnorm=True, augment=False)
        net, rep = train(fe(x_tr), y_tr, fe(tests["validation"][0]), tests["validation"][1], shape, 8,
                         10 if task == "contents" else 4, arch.parse(text), cfg)
        net.meta = {"task": task, "arch": text, "frontend": fe.name, "frontend_params": fe.params}
        net.save(f"model/build/multi/{task}_{name}{f'_s{seed}' if seed else ''}.npz")
        if not seed:        # the chip model must give the same integers
            probe = fe(tests["validation"][0][:2])
            assert np.array_equal(Fpga(Chip()).classify(net, probe)[1], net.scores(probe))
        rows.append([100 * score(net, *tests[k])[1] for k in tests])
    rows = np.array(rows)
    cost = net.cost()
    cycles = sum(r["chip_passes"] * v2_period(r["input_bits"]) for r in net.plan() if "weights" in r) \
        + cost["sets_per_image"] * V2_WEIGHT_SET
    print(f"{name:12} {runs:>4}  " + "  ".join(
        f"{rows[:, j].mean():5.1f}% ({rows[:, j].min():.1f} to {rows[:, j].max():.1f})".rjust(20) for j in range(3))
        + f"  {cost['chip_passes']:>7,} {cost['sets_per_image']:>6} {cycles:>10,}", flush=True)
