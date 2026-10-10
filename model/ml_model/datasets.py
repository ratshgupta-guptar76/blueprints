"""Datasets. Every dataset is 8-bit images, [n, height, width, channels].

To add a dataset: write a loader that returns a Dataset and decorate it with
@register("name"). Nothing else in the package needs to change.
"""
from __future__ import annotations

import os
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np


@dataclass
class Dataset:
    name: str
    images: np.ndarray      # uint8 [n, height, width, channels], 0 = background
    labels: np.ndarray      # int64 [n], index into classes
    classes: list[str]
    n_test: int = 360       # default number of held-out images
    live_stretch: bool = True   # stretch the contrast of live pictures (not for photographs)
    augment: bool = False       # train on mirrored and shifted copies (photographs, not digits)
    test_only: bool = False     # an independent test set: never trained on
    fixed_test: int = 0         # above 0: the last this-many images are the official test set

    @property
    def shape(self) -> tuple[int, int, int]:
        return tuple(self.images.shape[1:])

    def split(self, seed: int, n_test: int) -> tuple[np.ndarray, np.ndarray]:
        """(train indices, test indices). Same seed, same split. A dataset with
        an official test set always uses that one, whatever the seed."""
        n = len(self.labels)
        if self.fixed_test:
            return np.random.default_rng(seed).permutation(n - self.fixed_test), np.arange(n - self.fixed_test, n)
        perm = np.random.default_rng(seed).permutation(n)
        return perm[n_test:], perm[:n_test]


DATASETS: dict[str, Callable[[], Dataset]] = {}


def register(name: str):
    def deco(fn):
        DATASETS[name] = fn
        return fn
    return deco


def load(name: str, size: int | None = None) -> Dataset:
    """Load a dataset. size shrinks every image to size x size by averaging
    blocks of pixels (the original side must be a multiple of size)."""
    if name not in DATASETS:
        raise KeyError(f"unknown dataset '{name}', have: {', '.join(sorted(DATASETS))}")
    ds = DATASETS[name]()
    assert ds.images.dtype == np.uint8 and ds.images.ndim == 4
    assert len(ds.images) == len(ds.labels)
    if size is not None and size != ds.images.shape[1]:
        n, h, w, c = ds.images.shape
        if h % size or w % size:
            raise ValueError(f"size {size} does not divide {h} x {w}")
        blocks = ds.images.reshape(n, size, h // size, size, w // size, c)
        ds.images = np.round(blocks.mean(axis=(2, 4))).astype(np.uint8)
    return ds


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "dcim_model"


def fetch(url: str, filename: str) -> Path:
    """Download once into the user cache directory."""
    file = cache_dir() / filename
    if not file.exists():
        file.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {url} -> {file}", file=sys.stderr)
        part = file.with_name(file.name + ".part")     # an interrupted download leaves no half file
        urllib.request.urlretrieve(url, part)
        part.replace(file)
    return file


@register("digits")
def _digits() -> Dataset:
    """UCI optdigits test set: 1,797 handwritten digits, 8 x 8, one channel.
    The same data as scikit-learn's load_digits. Ink is stored as 0..16 and is
    rescaled here to 0..255."""
    file = fetch("https://archive.ics.uci.edu/ml/machine-learning-databases/"
                 "optdigits/optdigits.tes", "optdigits.tes")
    raw = np.loadtxt(file, delimiter=",", dtype=np.int64)
    if raw.shape != (1797, 65):
        raise RuntimeError(f"unexpected shape {raw.shape} in {file}")
    images = ((raw[:, :64] * 255 + 8) // 16).astype(np.uint8).reshape(-1, 8, 8, 1)
    return Dataset("digits", images, raw[:, 64], [str(d) for d in range(10)])


@register("cifar10")
def _cifar10() -> Dataset:
    """CIFAR-10: 60,000 colour photographs, 32 x 32, three channels (RGB), ten
    kinds of object. Read from the binary release (no pickle), parsed once and
    kept as a .npz in the cache."""
    parsed = cache_dir() / "cifar10.npz"
    if not parsed.exists():
        archive = fetch("https://www.cs.toronto.edu/~kriz/cifar-10-binary.tar.gz",
                        "cifar-10-binary.tar.gz")
        chunks, classes = [], []
        with tarfile.open(archive) as tar:
            for member in sorted(tar.getmembers(), key=lambda m: m.name):
                base = member.name.rsplit("/", 1)[-1]
                if base == "batches.meta.txt":
                    classes = tar.extractfile(member).read().decode().split()
                elif base.endswith(".bin"):     # data_batch_1..5 then test_batch
                    chunks.append(np.frombuffer(tar.extractfile(member).read(), dtype=np.uint8))
        raw = np.concatenate(chunks).reshape(-1, 1 + 3 * 32 * 32)
        if raw.shape[0] != 60000 or len(classes) != 10:
            raise RuntimeError(f"unexpected CIFAR-10 contents in {archive}")
        images = raw[:, 1:].reshape(-1, 3, 32, 32).transpose(0, 2, 3, 1)
        np.savez(parsed, images=images, labels=raw[:, 0], classes=np.array(classes))
    with np.load(parsed) as z:
        return Dataset("cifar10", np.ascontiguousarray(z["images"]), z["labels"].astype(np.int64),
                       [str(c) for c in z["classes"]], n_test=10000, live_stretch=False, augment=True)


@register("cifar10.1")
def _cifar10_1() -> Dataset:
    """CIFAR-10.1 (version 6): 2,000 photographs collected years after CIFAR-10
    by other people, for the same ten classes. An independent test set; no
    network here is ever trained on it. Recht et al., "Do CIFAR-10 Classifiers
    Generalize to CIFAR-10?"."""
    base = "https://github.com/modestyachts/CIFAR-10.1/raw/master/datasets/"
    images = np.load(fetch(base + "cifar10.1_v6_data.npy", "cifar10.1_v6_data.npy"))
    labels = np.load(fetch(base + "cifar10.1_v6_labels.npy", "cifar10.1_v6_labels.npy"))
    if images.shape != (2000, 32, 32, 3) or images.dtype != np.uint8:
        raise RuntimeError(f"unexpected CIFAR-10.1 contents: {images.shape} {images.dtype}")
    return Dataset("cifar10.1", images, labels.astype(np.int64), _cifar10().classes,
                   live_stretch=False, test_only=True)


IMAGENETTE = {"n01440764": "fish", "n02102040": "dog", "n02979186": "cassette player",
              "n03000684": "chain saw", "n03028079": "church", "n03394916": "French horn",
              "n03417042": "garbage truck", "n03425413": "gas pump", "n03445777": "golf ball",
              "n03888257": "parachute"}
IMAGENETTE_SIDE = 128


def _middle_square(data: bytes, side: int) -> np.ndarray:
    """A picture file's bytes -> the middle square of the picture, side x side, RGB."""
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    m = min(w, h)
    box = ((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m)
    return np.asarray(img.resize((side, side), Image.LANCZOS, box=box))


@register("imagenette")
def _imagenette() -> Dataset:
    """Imagenette: ten easily told apart classes taken from ImageNet, about
    13,400 full-size photographs. Stored here at 128 x 128 (the middle square of
    each photo), so training can cut varied views out of detailed images and
    shrink them afterwards. The official validation photos are the test set."""
    names, side = IMAGENETTE, IMAGENETTE_SIDE
    parsed = cache_dir() / f"imagenette_{side}.npz"
    if not parsed.exists():
        archive = fetch("https://s3.amazonaws.com/fast-ai-imageclas/imagenette2-160.tgz",
                        "archives/imagenette2-160.tgz")
        wnids = sorted(names)
        found = {"train": ([], []), "val": ([], [])}
        with tarfile.open(archive) as tar:      # read in place, nothing is unpacked to disk
            for member in tar:
                parts = member.name.split("/")
                if not (member.isfile() and len(parts) == 4 and parts[1] in found and parts[2] in names):
                    continue
                found[parts[1]][0].append(_middle_square(tar.extractfile(member).read(), side))
                found[parts[1]][1].append(wnids.index(parts[2]))
        images = np.stack(found["train"][0] + found["val"][0])
        labels = np.array(found["train"][1] + found["val"][1])
        np.savez(parsed, images=images, labels=labels, n_val=len(found["val"][1]))
    with np.load(parsed) as z:
        return Dataset("imagenette", np.ascontiguousarray(z["images"]), z["labels"].astype(np.int64),
                       [names[w] for w in sorted(names)], n_test=int(z["n_val"]),
                       live_stretch=False, augment=True, fixed_test=int(z["n_val"]))


@register("imagenetv2")
def _imagenetv2() -> Dataset:
    """ImageNetV2, cut down to the ten Imagenette classes: photographs collected
    about ten years after ImageNet by other people, following the same recipe.
    An independent test set; no network here is ever trained on it. Recht et
    al., "Do ImageNet Classifiers Generalize to ImageNet?". It was published as
    three samplings of one pool of photographs, ten per class each; they are
    merged here and a photograph that is in more than one is kept once."""
    side = IMAGENETTE_SIDE
    parsed = cache_dir() / f"imagenetv2_imagenette_{side}.npz"
    if not parsed.exists():
        # Folder names are the class numbers of the 1,000-class ImageNet list.
        number = {"0": 0, "217": 1, "482": 2, "491": 3, "497": 4, "566": 5, "569": 6, "571": 7, "574": 8, "701": 9}
        found: dict[str, tuple[np.ndarray, int]] = {}
        for variant in ("matched-frequency", "threshold0.7", "top-images"):
            name = f"imagenetv2-{variant}.tar.gz"
            archive = fetch(f"https://huggingface.co/datasets/vaishaal/ImageNetV2/resolve/main/{name}",
                            f"archives/{name}")
            with tarfile.open(archive) as tar:      # read in place, nothing is unpacked to disk
                for member in tar:
                    parts = member.name.split("/")
                    if member.isfile() and len(parts) == 3 and parts[1] in number and parts[2] not in found:
                        found[parts[2]] = (_middle_square(tar.extractfile(member).read(), side), number[parts[1]])
        keys = sorted(found)
        np.savez(parsed, images=np.stack([found[k][0] for k in keys]),
                 labels=np.array([found[k][1] for k in keys]))
    with np.load(parsed) as z:
        return Dataset("imagenetv2", np.ascontiguousarray(z["images"]), z["labels"].astype(np.int64),
                       [IMAGENETTE[w] for w in sorted(IMAGENETTE)], live_stretch=False, test_only=True)
