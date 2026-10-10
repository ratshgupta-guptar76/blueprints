"""End to end: image -> front end -> (photonic layer) -> FPGA -> chip -> answer.

Runs a trained network through every stage and checks the chip's answer
against the plain integer math in ml_model. Run from the repository root,
after `python3 -m model.ml_model train`:

    python3 -m model.emulation                          # all held-out images
    python3 -m model.emulation --sample 7               # one held-out image
    python3 -m model.emulation --image photo.png --invert
    python3 -m model.emulation --net other.npz --limit 500
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from .digital_dcim import Chip, v1_period, v2_period
from .fpga import Fpga
from .ml_model import QNet, datasets, frontend, preprocess


def main() -> int:
    ap = argparse.ArgumentParser(prog="python3 -m model.emulation", description=__doc__.split("\n\n")[0])
    ap.add_argument("--net", default="model/build/net.npz")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--image", help="picture file (png, jpg, ...) or .npy")
    src.add_argument("--sample", type=int, help="index into the held-out images")
    ap.add_argument("--limit", type=int, help="use only the first LIMIT held-out images")
    ap.add_argument("--invert", action="store_true", help="dark ink on a light background")
    ap.add_argument("--stretch", action=argparse.BooleanOptionalAction,
                    help="stretch contrast (default: on for digits, off for photographs)")
    args = ap.parse_args()

    net = QNet.load(args.net)
    meta = net.meta
    fe = frontend.build(meta["frontend"], **meta["frontend_params"])
    shape = tuple(meta["shape"])

    # Stage 1: the images.
    labels = None
    if args.image:
        images = preprocess.to_model_image(preprocess.read_image(args.image), shape,
                                           invert=args.invert,
                                           stretch=meta.get("live_stretch", True) if args.stretch is None
                                           else args.stretch)[None]
        source = args.image
    else:
        ds = datasets.load(meta["dataset"], meta["size"])
        _, te = ds.split(meta["split_seed"], meta["test_size"])
        te = te[[args.sample]] if args.sample is not None else te[:args.limit]
        images, labels = ds.images[te], ds.labels[te]
        source = f"{ds.name} held-out"
    n = len(images)

    # Stage 2: front end. Stage 3 and 4: FPGA driving the chip.
    features = fe(images)
    chip = Chip()
    fpga = Fpga(chip)
    answers, scores = fpga.classify(net, features)
    reference = net.scores(features)
    same = np.array_equal(scores, reference)

    by_bits = {b: sum(v for p, v in fpga.sets if p == b) // n for b in sorted({p for p, _ in fpga.sets})}
    optical = [layer for layer in net.layers if layer.stage == "photonic"]
    ops = fpga.glue_ops(net)
    cyc = chip.cycles()

    if n == 1:
        print(preprocess.ascii_art(images[0]))
        order = np.argsort(-scores[0])
        print("scores: " + "  ".join(f"{meta['classes'][i]}:{scores[0][i]}" for i in order[:3]) + "  ...")
        truth = f"   (truth: {meta['classes'][labels[0]]})" if labels is not None else ""
        print(f"answer: {meta['classes'][answers[0]]}{truth}\n")

    print(f"Stage 1  images     {n} from {source}, {shape[0]} x {shape[1]} x {shape[2]}, 8-bit")
    print(f"Stage 2  front end  {fe.name} {fe.params}: {features.shape[1]} values of {fe.bits} bits per image")
    if optical:
        print(f"         photonic   first layer computed as ideal optics: {optical[0].w.shape[1]} kernels, "
              f"{optical[0].k} x {optical[0].k} window, {optical[0].out_bits}-bit output")
    cost = net.cost()
    assert chip.weight_loads == cost["weight_sets"] + n * cost["sets_per_image"]
    per_image = f" loaded once and {cost['sets_per_image']} more written for every image" \
        if cost["sets_per_image"] else ""
    print(f"Stage 3  chip       network {meta['arch']}: {cost['weight_sets']} weight sets{per_image}, "
          f"{sum(by_bits.values()):,} passes per image ("
          + ", ".join(f"{k:,} at P = {b}" for b, k in by_bits.items()) + ")")
    print(f"Stage 4  FPGA math  per image: {ops.partial_sum_adds:,} partial-sum adds, {ops.bias_adds:,} bias adds, "
          f"{ops.relu_and_scale:,} ReLU and scale, {ops.compares:,} compares")
    print(f"\nChip scores identical to the reference integer math on all {scores.size} values: "
          f"{'yes' if same else 'NO'}")
    if labels is not None and n > 1:
        print(f"Accuracy through the chip: {100 * (answers == labels).mean():.1f}% of {n} images")

    v1_img = sum(k * v1_period(b) for b, k in by_bits.items())
    v2_img = sum(k * v2_period(b) for b, k in by_bits.items())
    print(f"\nCycles (estimate for v2, measured basis for v1), batch of {n}:")
    print(f"{'':6} {'per image':>10} {'weight reloads':>15} {'total':>12} {'per image with reloads':>23}")
    for name, per in (("v1", v1_img), ("v2", v2_img)):
        print(f"{name:6} {per:>10,} {cyc[name + '_reload']:>15,} {cyc[name]:>12,} {cyc[name] / n:>23,.0f}")
    print(f"v2 is {cyc['v1'] / cyc['v2']:.1f}x faster at this batch size "
          f"({v1_img / v2_img:.1f}x with weights already loaded)")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
