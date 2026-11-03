"""Google Speech Commands v2, read from the two archives in the dataset cache.

The 12-class task: the ten words below, "unknown" (any of the other 25 words),
and "silence" (one-second pieces of the background noise recordings).

    train, validation   from the main archive, split by its validation_list.txt
                        and testing_list.txt. The split is by speaker, so no
                        speaker in the training set appears in either of the others.
    test                the separate official 12-class test archive (4,890 clips
                        on its own labels), the set published results are quoted on.

Archives are untrusted data: they are extracted with tarfile's "data" filter,
which refuses absolute paths, links out of the folder, and device files.
"""
from __future__ import annotations

import os
import tarfile
import wave
from pathlib import Path

import numpy as np

WORDS = ["yes", "no", "up", "down", "left", "right", "on", "off", "stop", "go"]
CLASSES = WORDS + ["unknown", "silence"]
RATE = 16000


def cache() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "dcim_model"


def _extract(archive: Path, into: Path) -> Path:
    if not (into / ".complete").exists():
        into.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as t:
            t.extractall(into, filter="data")
        (into / ".complete").touch()
    return into


def read_wav(path: Path) -> np.ndarray:
    """16-bit mono 16 kHz -> int16 [16000], padded with zeros or cut to one second."""
    with wave.open(str(path)) as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == RATE, path
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    out = np.zeros(RATE, dtype=np.int16)
    out[:min(RATE, len(x))] = x[:RATE]
    return out


def _label(word: str) -> int:
    return CLASSES.index(word) if word in WORDS else CLASSES.index("unknown")


def load(unknown_share: float = 0.1, silence_share: float = 0.1, seed: int = 0):
    """Returns a dict of (waves int16 [n, 16000], labels int64 [n]) for train,
    val and test, plus the background noise recordings for augmentation.
    Cached as one .npz after the first build."""
    parsed = cache() / f"speech_commands_v2_12_{int(unknown_share * 100)}_{int(silence_share * 100)}_{seed}.npz"
    if parsed.exists():
        z = np.load(parsed, allow_pickle=False)
        noise = [z[k] for k in sorted(k for k in z.files if k.startswith("noise_"))]
        return {s: (z[f"{s}_x"], z[f"{s}_y"]) for s in ("train", "val", "test")} | {"noise": noise}

    rng = np.random.default_rng(seed)
    root = _extract(cache() / "archives" / "speech_commands_v0.02.tar.gz", cache() / "speech_commands_v2")
    test_root = _extract(cache() / "archives" / "speech_commands_test_set_v0.02.tar.gz",
                         cache() / "speech_commands_v2_test")
    val_list = set((root / "validation_list.txt").read_text().split())
    test_list = set((root / "testing_list.txt").read_text().split())

    split = {"train": [], "val": []}
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for f in sorted(d.glob("*.wav")):
            rel = f"{d.name}/{f.name}"
            if rel in test_list:
                continue                        # the main archive's test part is not used: the official set is
            split["val" if rel in val_list else "train"].append((f, _label(d.name)))

    noise = [read_noise(f) for f in sorted((root / "_background_noise_").glob("*.wav"))]
    out = {}
    for name, items in split.items():
        known = [it for it in items if it[1] < len(WORDS)]
        unknown = [it for it in items if it[1] == CLASSES.index("unknown")]
        n_known = len(known)
        n_unk = int(round(n_known * unknown_share / (1 - unknown_share - silence_share)))
        pick = rng.choice(len(unknown), min(n_unk, len(unknown)), replace=False)
        chosen = known + [unknown[i] for i in pick]
        x = np.stack([read_wav(f) for f, _ in chosen])
        y = np.array([lab for _, lab in chosen], dtype=np.int64)
        n_sil = int(round(n_known * silence_share / (1 - unknown_share - silence_share)))
        sil = np.stack([_noise_clip(noise, rng, quiet=rng.random() < 0.5) for _ in range(n_sil)])
        x = np.concatenate([x, sil])
        y = np.concatenate([y, np.full(n_sil, CLASSES.index("silence"))])
        out[name] = (x, y)

    tx, ty = [], []
    for d in sorted(p for p in test_root.iterdir() if p.is_dir()):
        lab = CLASSES.index("silence") if d.name == "_silence_" else \
            CLASSES.index("unknown") if d.name == "_unknown_" else CLASSES.index(d.name)
        for f in sorted(d.glob("*.wav")):
            tx.append(read_wav(f))
            ty.append(lab)
    out["test"] = (np.stack(tx), np.array(ty, dtype=np.int64))
    np.savez(parsed, **{f"{s}_x": out[s][0] for s in out}, **{f"{s}_y": out[s][1] for s in out},
             **{f"noise_{i}": n for i, n in enumerate(noise)})
    return out | {"noise": noise}


def read_noise(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        assert w.getsampwidth() == 2 and w.getframerate() == RATE, path
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        if w.getnchannels() > 1:
            x = x[::w.getnchannels()]
    return x.copy()


def _noise_clip(noise: list[np.ndarray], rng, quiet: bool) -> np.ndarray:
    """One second of one background recording, at a random level; or near silence."""
    if quiet:
        return np.zeros(RATE, dtype=np.int16)
    n = noise[int(rng.integers(len(noise)))]
    s = int(rng.integers(0, len(n) - RATE))
    return (n[s:s + RATE].astype(np.float32) * rng.uniform(0, 1)).astype(np.int16)
