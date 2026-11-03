"""An independent test for the keyword networks: the ten words cut out of LibriSpeech.

    /usr/bin/python3 -m model.kws.librispeech model/build/kws/kwt1_s0.pt [more checkpoints]

LibriSpeech test-clean is read speech from public-domain audiobooks (LibriVox), 40 speakers,
recorded and published independently of Speech Commands, whose clips were recorded one word
at a time through a web page. The word timings come from a forced alignment (Montreal Forced
Aligner; Lugosch et al. 2019, Zenodo record 2619474). Each target word is cut at its timing, with 30 ms
either side, and placed in the middle of one second of zeros, as a Speech Commands clip has
one word in one second. "unknown" is other words cut the same way; "silence" is one second of
a pause between sentences.

This is a harder test than the official one, and on purpose: the words are spoken in running
sentences, so they are short and run into their neighbours. A drop here measures how far the
network carries outside the recording conditions it was trained on.

Before scoring, every clip is checked against every training clip, exactly (the same samples)
and by spectrogram (cosine similarity of the log-mel features), so the result can say how
close the nearest training clip is.

Archives are untrusted data: the tar is extracted with tarfile's "data" filter, and the alignment zip is
read in memory, never extracted. FLAC is decoded by ffmpeg into raw samples.
"""
from __future__ import annotations

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import numpy as np
import torch

from . import data
from .features import LogMel
from .model import Config, Net
from .train import wilson

RATE = data.RATE
PAD = int(0.03 * RATE)


def read_flac(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(RATE), "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype="<i2")


def alignments(archive: Path) -> dict[str, list[tuple[str, float, float]]]:
    """utterance id -> [(word, start s, end s)], from the words tier of each test-clean TextGrid,
    read straight out of the zip (nothing is written to disk)."""
    out = {}
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not (name.startswith("test-clean/") and name.endswith(".TextGrid")):
                continue
            seg, lo, hi, in_words = [], None, None, False
            for line in z.read(name).decode().splitlines():
                t = line.strip()
                if t.startswith("name ="):
                    in_words = t.split("=", 1)[1].strip().strip('"') == "words"
                elif in_words and t.startswith("xmin ="):
                    lo = float(t.split("=")[1])
                elif in_words and t.startswith("xmax ="):
                    hi = float(t.split("=")[1])
                elif in_words and t.startswith("text ="):
                    seg.append((t.split("=", 1)[1].strip().strip('"').lower(), lo, hi))
            out[Path(name).stem] = seg
    return out


def centered(x: np.ndarray) -> np.ndarray:
    x = x[:RATE]
    out = np.zeros(RATE, dtype=np.int16)
    s = (RATE - len(x)) // 2
    out[s:s + len(x)] = x
    return out


def build(seed: int = 0) -> dict:
    cache = data.cache() / "librispeech_test_clean_kws.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        return {k: z[k] for k in z.files}
    arch = data.cache() / "archives"
    root = data.cache() / "librispeech"
    if not (root / ".complete").exists():
        root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(arch / "test-clean.tar.gz") as t:
            t.extractall(root, filter="data")
        (root / ".complete").touch()
    al = arch / "librispeech_alignments_zenodo.zip"            # Lugosch et al. 2019, Zenodo 2619474, CC-BY 4.0
    rng = np.random.default_rng(seed)
    targets, others, quiet = [], [], []
    for utt, seg in sorted(alignments(al).items()):
        spk, chap, _ = utt.split("-")
        flac = root / "LibriSpeech" / "test-clean" / spk / chap / f"{utt}.flac"
        x = None
        for w, s, e in seg:
            other = w and w not in data.WORDS and 0.25 <= e - s <= 0.9 and rng.random() < 0.08   # a sample is enough
            if w in data.WORDS or other or (not w and e - s >= 1.2):
                x = read_flac(flac) if x is None else x
                a, b = max(0, int(s * RATE) - PAD), min(len(x), int(e * RATE) + PAD)
                if w in data.WORDS:
                    targets.append((centered(x[a:b]), data.CLASSES.index(w), spk))
                elif other:
                    others.append((centered(x[a:b]), data.CLASSES.index("unknown"), spk))
                else:
                    m = int((s + e) / 2 * RATE)
                    quiet.append((x[m - RATE // 2:m + RATE // 2].copy(), data.CLASSES.index("silence"), spk))
    per = max(1, len(targets) // len(data.WORDS))       # unknown and silence as many as an average word
    pick = [others[i] for i in rng.choice(len(others), min(per, len(others)), replace=False)]
    pickq = [quiet[i] for i in rng.choice(len(quiet), min(per, len(quiet)), replace=False)]
    items = targets + pick + pickq
    out = {"x": np.stack([it[0] for it in items]), "y": np.array([it[1] for it in items], dtype=np.int64),
           "speaker": np.array([int(it[2]) for it in items], dtype=np.int64)}
    np.savez(cache, **out)
    return out


def nearest_training(test_x: np.ndarray, mel: LogMel) -> tuple[int, np.ndarray]:
    """Exact duplicates of training audio, and each test clip's highest spectrogram cosine
    similarity to any training clip."""
    train_x = data.load()["train"][0]
    hashes = {hash(c.tobytes()) for c in train_x}
    exact = sum(hash(c.tobytes()) in hashes for c in test_x)

    def unit(x):
        out = []
        for i in range(0, len(x), 1024):
            f = mel(torch.tensor(x[i:i + 1024])).flatten(1)
            f = f - f.mean(1, keepdim=True)
            out.append(f / f.norm(dim=1, keepdim=True).clamp(min=1e-8))
        return torch.cat(out)
    tr, te = unit(train_x), unit(test_x)
    best = torch.full((len(te),), -1.0)
    for i in range(0, len(tr), 4096):
        best = torch.maximum(best, (te @ tr[i:i + 4096].T).max(1).values)
    return exact, best.numpy()


def score(path: str, feats: torch.Tensor, y: np.ndarray) -> np.ndarray:
    ck = torch.load(path, map_location="cpu", weights_only=True)
    net = Net(Config(**ck["config"]))
    net.load_state_dict(ck["state"])
    net.amax, net.mode = ck["amax"], "chip"
    net.eval()
    pred = []
    with torch.no_grad():
        for i in range(0, len(feats), 256):
            pred.append(net(feats[i:i + 256]).argmax(1).numpy())
    return np.concatenate(pred)


def main() -> int:
    torch.set_num_threads(4)
    mel = LogMel(torch.device("cpu"))
    d = build()
    x, y = d["x"], d["y"]
    counts = {c: int((y == i).sum()) for i, c in enumerate(data.CLASSES)}
    print(f"LibriSpeech test-clean: {len(y)} clips from {len(set(d['speaker']))} speakers; {counts}", flush=True)
    exact, best = nearest_training(x, mel)
    print(f"against the {len(data.load()['train'][1]):,} training clips: {exact} identical; nearest spectrogram "
          f"cosine similarity median {np.median(best):.3f}, highest {best.max():.3f} "
          f"({int((best > 0.95).sum())} above 0.95)", flush=True)
    sc = data.load()["test"]
    sc_feats = torch.cat([mel(torch.tensor(sc[0][i:i + 1024])) for i in range(0, len(sc[1]), 1024)])
    feats = torch.cat([mel(torch.tensor(x[i:i + 1024])) for i in range(0, len(y), 1024)])
    words = y < len(data.WORDS)
    for path in sys.argv[1:]:
        p_sc = score(path, sc_feats, sc[1])
        p = score(path, feats, y)
        k, n = int((p == y).sum()), len(y)
        kw, nw = int((p[words] == y[words]).sum()), int(words.sum())
        lo, hi = wilson(k, n)
        per = {c: 100 * float((p[y == i] == i).mean()) for i, c in enumerate(data.CLASSES) if (y == i).any()}
        print(f"{path}: official test (same harness) {100 * (p_sc == sc[1]).mean():.2f}%; LibriSpeech all "
              f"{100 * k / n:.2f}% (95% interval {lo:.2f} to {hi:.2f}), ten words only {100 * kw / nw:.2f}%, "
              f"mean over classes {np.mean(list(per.values())):.2f}%", flush=True)
        print("   per class: " + ", ".join(f"{c} {v:.0f}" for c, v in per.items()), flush=True)
        wrong = np.bincount(p[words & (p != y)], minlength=len(data.CLASSES))
        print("   ten-word errors went to: " + ", ".join(f"{data.CLASSES[i]} {v}" for i, v in enumerate(wrong) if v),
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
