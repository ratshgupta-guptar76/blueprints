"""Command line for ml_model. Run from the repository root.

Training needs PyTorch, so use the system Python for train and sweep:

    /usr/bin/python3 -m model.ml_model train                          # digits, small network
    /usr/bin/python3 -m model.ml_model train --dataset cifar10 --arch small
    /usr/bin/python3 -m model.ml_model sweep --dataset cifar10 \\
        --arch "conv3:8 pool fc:32" "conv3:8 pool conv3:16 pool fc:32" --in-bits 8 2 --act-bits 8 4

The rest runs anywhere numpy does:

    python3 -m model.ml_model show                        # layers, sizes, shifts
    python3 -m model.ml_model predict --sample 7          # one held-out image
    python3 -m model.ml_model predict --image photo.jpg
    python3 -m model.ml_model test --net NET --dataset cifar10.1    # an independent test set
    python3 -m model.ml_model test --net NET --folder photos/       # photos/<class name>/*.jpg
"""
from __future__ import annotations

import argparse
import csv
import itertools
import sys
import time
from pathlib import Path

import numpy as np

from . import arch, datasets, frontend, preprocess
from .network import QNet

DEFAULT_NET = "model/build/net.npz"


def _source(args, ds):
    """The dataset at its stored size, when that is larger than the network's
    input: training then cuts varied views out of the larger photos."""
    if not args.crop_from_source or not args.size:
        return None
    full = datasets.load(args.dataset)
    return full.images if full.images.shape[1] > ds.images.shape[1] else None


def _per_image(cost: dict) -> str:
    """Attention writes some weight sets again for every image."""
    n = cost["sets_per_image"]
    return f", plus {n} weight sets written for every image" if n else ""


def _train_one(ds, n_test: int, spec_text: str, in_bits: int, act_bits: int, args, seed: int, src=None):
    """Train one network on one split. Returns (network, row of results)."""
    from .train import TrainConfig, train      # needs PyTorch
    fe = frontend.build("pixels", bits=in_bits)
    tr, te = ds.split(seed, n_test)
    a_tr, a_te = fe(ds.images[tr]), fe(ds.images[te])
    n_train = len(tr)
    epochs = args.epochs or min(300, max(30, round(431100 / n_train)))
    qat = args.qat_epochs if args.qat_epochs is not None else max(10, epochs // 3)
    cfg = TrainConfig(act_bits=act_bits, w_bits=args.w_bits, ph_bits=args.ph_bits, epochs=epochs, qat_epochs=qat, seed=seed,
                      batchnorm=args.bn, augment=ds.augment if args.augment is None else args.augment,
                      log_every=args.log_every, aug_scale=args.aug_scale, aug_color=args.aug_color,
                      crop_area=args.crop_area)
    start = time.time()
    net, rep = train(a_tr, ds.labels[tr], a_te, ds.labels[te], ds.shape, in_bits,
                     len(ds.classes), arch.parse(spec_text), cfg,
                     src_tr=None if src is None else src[tr])
    int_acc = float((net.predict(a_te) == ds.labels[te]).mean())
    net.meta = {"dataset": ds.name, "shape": list(ds.shape), "size": args.size, "classes": ds.classes,
                "arch": arch.PRESETS.get(spec_text, spec_text),
                "frontend": fe.name, "frontend_params": fe.params,
                "split_seed": seed, "test_size": n_test, "live_stretch": ds.live_stretch,
                "float_accuracy": rep["float_accuracy"], "integer_accuracy": int_acc}
    row = {"arch": net.meta["arch"], "in_bits": in_bits, "act_bits": act_bits,
           "float": rep["float_accuracy"], "integer": int_acc, **net.cost(),
           "export_agreement": rep["export_agreement"], "epochs": f"{epochs}+{qat}",
           "seconds": round(time.time() - start), "device": rep["device"]}
    return net, row


def cmd_train(args) -> int:
    ds = datasets.load(args.dataset, args.size)
    n_test = args.test_size or ds.n_test
    rows, first, src = [], None, _source(args, ds)
    for seed in range(args.splits):
        net, row = _train_one(ds, n_test, args.arch, args.in_bits, args.act_bits, args, seed, src)
        rows.append(row)
        first = first or net
        if seed:        # later runs are kept too, beside the first: name_s1.npz, name_s2.npz, ...
            net.save(Path(args.out).with_name(f"{Path(args.out).stem}_s{seed}.npz"))
        print(f"split {seed}: float {100 * row['float']:.1f}%  integer {100 * row['integer']:.1f}%  "
              f"({row['seconds']} s on {row['device']})", file=sys.stderr)
    r = rows[0]
    print(f"dataset {ds.name}: {len(ds.labels)} images of {ds.shape}, {len(ds.classes)} classes")
    print(f"network: {r['arch']}  (pixels {args.in_bits} bits, activations {args.act_bits} bits)")
    print(f"size: {r['weights']:,} weights, {r['weight_sets']} chip weight sets, "
          f"{r['chip_passes']:,} chip passes per image" + _per_image(r))
    print(f"trained {r['epochs']} epochs. Accuracy on {n_test} held-out images, "
          f"{args.splits} split(s), mean (lowest to highest):")
    for label, key in (("float", "float"), ("integer (hardware math)", "integer")):
        v = [x[key] for x in rows]
        print(f"  {label:24} {100 * np.mean(v):5.1f}% ({100 * min(v):.1f} to {100 * max(v):.1f})")
    if r["export_agreement"] < 1:
        print(f"  note: training-time integer forward and exported network agree on "
              f"{100 * r['export_agreement']:.1f}% of 256 answers (float32 rounding)")
    first.save(args.out)
    print(f"saved the split 0 network to {args.out}"
          + (f", and the others beside it as _s1 to _s{args.splits - 1}" if args.splits > 1 else ""))
    return 0


def cmd_sweep(args) -> int:
    ds = datasets.load(args.dataset, args.size)
    n_test = args.test_size or ds.n_test
    out = Path(args.csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["dataset", "arch", "in_bits", "act_bits", "float", "integer", "weights",
              "weight_sets", "chip_passes", "epochs", "seconds", "sets_per_image"]
    new = not out.exists()
    if not new and out.read_text().split("\n", 1)[0].strip() != ",".join(fields):
        print(f"{out} has other columns (an older table?). Give another --csv.", file=sys.stderr)
        return 1
    src = _source(args, ds)
    print(f"{'network':44} {'pix':>3} {'act':>3} {'float':>6} {'integer':>8} {'weights':>9} "
          f"{'sets':>5} {'passes':>8}")
    with out.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        if new:
            writer.writeheader()
        for spec, in_bits, act_bits in itertools.product(args.arch, args.in_bits, args.act_bits):
            try:
                net, row = _train_one(ds, n_test, spec, in_bits, act_bits, args, 0, src)
            except ValueError as exc:       # a shape that does not fit: report and carry on
                print(f"{spec:44} skipped: {exc}", flush=True)
                continue
            print(f"{row['arch']:44} {in_bits:>3} {act_bits:>3} {100 * row['float']:>5.1f}% "
                  f"{100 * row['integer']:>7.1f}% {row['weights']:>9,} {row['weight_sets']:>5} "
                  f"{row['chip_passes']:>8,}", flush=True)
            writer.writerow({"dataset": ds.name + (f"@{args.size}" if args.size else ""), **row})
            fh.flush()
            if args.save_dir:
                slug = "".join(ch if ch.isalnum() else "_" for ch in row["arch"])
                net.save(Path(args.save_dir) / f"{ds.name}_{slug}_p{in_bits}_a{act_bits}.npz")
    print(f"appended to {out}")
    return 0


def _load(args):
    net = QNet.load(args.net)
    fe = frontend.build(net.meta["frontend"], **net.meta["frontend_params"])
    return net, fe


def cmd_show(args) -> int:
    net, fe = _load(args)
    m = net.meta
    print(f"{args.net}: {m['dataset']}, network: {m['arch']}, pixels {fe.bits} bits")
    print(f"accuracy on held-out images: float {100 * m['float_accuracy']:.1f}%, "
          f"integer {100 * m['integer_accuracy']:.1f}%")
    print(f"{'layer':>5} {'kind':10} {'runs on':9} {'output':>12} {'inputs':>7} {'in bits':>8} "
          f"{'shift':>6} {'bias bits':>10} {'weights':>8} {'sets':>5} {'passes':>8}")
    for r in net.plan():
        shape = "x".join(map(str, r["shape"]))
        if r["kind"] == "pool":
            print(f"{r['layer']:>5} {'pool %dx%d' % (r['k'], r['k']):10} {'fpga':9} {shape:>12}")
            continue
        shift = "-" if r["shift"] is None else r["shift"]
        sets = f"{r['sets_per_image']}*" if r["sets_per_image"] else r["weight_sets"]
        print(f"{r['layer']:>5} {r['kind']:10} {r['stage']:9} {shape:>12} {r['inputs']:>7} {r['input_bits']:>8} "
              f"{shift:>6} {r['bias_bits']:>10} {r['weights']:>8,} {sets:>5} {r['chip_passes']:>8,}")
    c = net.cost()
    print(f"total: {c['weights']:,} weights, {c['weight_sets']} chip weight sets, "
          f"{c['chip_passes']:,} chip passes per image" + _per_image(c))
    if c["sets_per_image"]:
        print("* written for every image: this image's attention keys and values, used as weights")
    for layer in net.layers:
        if layer.stage == "photonic":
            print(f"\nphotonic kernels (weights {int(layer.w.min())}..{int(layer.w.max())}, rows are window positions "
                  f"then channels; one column per kernel):")
            print(layer.w)
            print(f"comparator thresholds (a kernel fires when its sum exceeds this): {(-layer.b).tolist()}")
    return 0


def cmd_predict(args) -> int:
    net, fe = _load(args)
    shape = tuple(net.meta["shape"])
    truth = None
    if args.image:
        image = preprocess.to_model_image(preprocess.read_image(args.image), shape, invert=args.invert,
                                          stretch=net.meta.get("live_stretch", True) if args.stretch is None
                                          else args.stretch)
    else:
        ds = datasets.load(net.meta["dataset"], net.meta["size"])
        _, te = ds.split(net.meta["split_seed"], net.meta["test_size"])
        image = ds.images[te[args.sample]]
        truth = ds.classes[ds.labels[te[args.sample]]]
    scores = net.scores(fe(image[None]))[0]
    print(preprocess.ascii_art(image))
    order = np.argsort(-scores)
    print("scores: " + "  ".join(f"{net.meta['classes'][i]}:{scores[i]}" for i in order[:3]) + "  ...")
    print(f"answer: {net.meta['classes'][order[0]]}" + (f"   (truth: {truth})" if truth is not None else ""))
    return 0


def cmd_test(args) -> int:
    """Accuracy on images the network has never seen in any form."""
    net, fe = _load(args)
    classes, shape = net.meta["classes"], tuple(net.meta["shape"])
    names = None
    if args.folder:
        images, labels, names = [], [], []
        for ci, cname in enumerate(classes):
            for f in sorted((Path(args.folder) / cname).glob("*")):
                images.append(preprocess.to_model_image(preprocess.read_image(f), shape, stretch=False))
                labels.append(ci)
                names.append(f"{cname}/{f.name}")
        if not images:
            print(f"no images found: expected {args.folder}/<class name>/<files>, classes: {', '.join(classes)}")
            return 1
        images, labels, source = np.stack(images), np.array(labels), args.folder
    else:
        ds = datasets.load(args.dataset, net.meta["size"])
        if ds.classes != classes:
            print(f"{args.dataset} has different classes from the network's training data")
            return 1
        images, labels, source = ds.images, ds.labels, args.dataset
        if not ds.test_only:
            _, te = ds.split(net.meta["split_seed"], net.meta["test_size"])
            images, labels, source = images[te], labels[te], f"{args.dataset} held-out"
    scores = net.scores(fe(images))
    picks = scores.argmax(axis=1)
    print(f"{args.net}: {net.meta['arch']}")
    print(f"{source}: {len(labels)} images, {100 * (picks == labels).mean():.1f}% correct "
          f"(held-out accuracy when trained: {100 * net.meta['integer_accuracy']:.1f}%)")
    print("per class: " + "  ".join(f"{c} {100 * (picks[labels == i] == i).mean():.0f}%"
                                    for i, c in enumerate(classes) if (labels == i).any()))
    if names:
        for name, pick, truth in zip(names, picks, labels):
            print(f"  {'ok   ' if pick == truth else 'WRONG'} {name:40} -> {classes[pick]}")
    return 0


def _common(p, many: bool) -> None:
    n = "+" if many else None
    p.add_argument("--dataset", default="digits", choices=sorted(datasets.DATASETS))
    p.add_argument("--size", type=int, help="shrink images to SIZE x SIZE first (default: as stored)")
    p.add_argument("--arch", nargs=n, default=["mlp"] if many else "mlp",
                   help="network shape, see model/ml_model/arch.py. Presets: " + ", ".join(arch.PRESETS))
    p.add_argument("--in-bits", type=int, nargs=n, default=[8] if many else 8, help="bits per pixel")
    p.add_argument("--act-bits", type=int, nargs=n, default=[8] if many else 8,
                   help="bits of the activations between chip layers")
    p.add_argument("--w-bits", type=int, default=8,
                   help="bits of the chip weights (experiment: the chip stores 8-bit weights)")
    p.add_argument("--ph-bits", type=int, default=8, help="resolution of photonic weights")
    p.add_argument("--test-size", type=int, help="held-out images (default: set by the dataset)")
    p.add_argument("--epochs", type=int, help="float epochs (default: scaled to the dataset size)")
    p.add_argument("--qat-epochs", type=int, help="integer fine-tune epochs (default: a third of --epochs)")
    p.add_argument("--bn", action="store_true", help="train with batch normalisation (folded away afterwards)")
    p.add_argument("--augment", action=argparse.BooleanOptionalAction,
                   help="mirror and shift training images (default: on for photographs)")
    p.add_argument("--aug-scale", type=float, default=1.0,
                   help="below 1: train on zoomed and shifted copies too (0.6 = zoom in to 60%% and out by as much)")
    p.add_argument("--aug-color", type=float, default=0.0,
                   help="above 0: vary brightness and contrast of training images by this fraction")
    p.add_argument("--crop-from-source", action="store_true",
                   help="with --size below the dataset's stored size: cut each training view out of the larger photo")
    p.add_argument("--crop-area", type=float, default=0.35,
                   help="smallest such cut, as a share of the photo's area")
    p.add_argument("--log-every", type=int, default=0, help="print progress every N epochs")


def main() -> int:
    ap = argparse.ArgumentParser(prog="python3 -m model.ml_model", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("train", help="train one network and save it")
    _common(t, many=False)
    t.add_argument("--splits", type=int, default=1, help="train/test splits to average over")
    t.add_argument("--out", default=DEFAULT_NET)
    t.set_defaults(fn=cmd_train)

    w = sub.add_parser("sweep", help="train every combination of the given choices, print a table")
    _common(w, many=True)
    w.add_argument("--csv", default="model/build/sweep.csv", help="results are appended here")
    w.add_argument("--save-dir", help="also save every trained network into this folder")
    w.set_defaults(fn=cmd_sweep)

    s = sub.add_parser("show", help="print the layers and what the hardware needs")
    s.add_argument("--net", default=DEFAULT_NET)
    s.set_defaults(fn=cmd_show)

    e = sub.add_parser("test", help="accuracy on an independent dataset or a folder of photos")
    e.add_argument("--net", default=DEFAULT_NET)
    which = e.add_mutually_exclusive_group(required=True)
    which.add_argument("--dataset", choices=sorted(datasets.DATASETS))
    which.add_argument("--folder", help="folder with one subfolder of pictures per class name")
    e.set_defaults(fn=cmd_test)

    p = sub.add_parser("predict", help="answer for one image")
    p.add_argument("--net", default=DEFAULT_NET)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="picture file (png, jpg, ...) or .npy")
    src.add_argument("--sample", type=int, help="index into the held-out images")
    p.add_argument("--invert", action="store_true", help="dark ink on a light background")
    p.add_argument("--stretch", action=argparse.BooleanOptionalAction,
                   help="stretch contrast (default: on for digits, off for photographs)")
    p.set_defaults(fn=cmd_predict)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
