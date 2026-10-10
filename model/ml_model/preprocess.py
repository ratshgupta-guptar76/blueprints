"""Live input: turn any picture into the small 8-bit image the network expects.

The network only ever sees images shaped like its training data (for the digits
dataset: 8 x 8, one channel, bright ink on a dark background, the digit filling
the frame). A photo of dark ink on white paper therefore needs invert=True.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def read_image(path: str | Path) -> np.ndarray:
    """Read an image file as uint8 [height, width] or [height, width, 3]."""
    path = Path(path)
    if path.suffix == ".npy":
        return np.load(path).astype(np.uint8)
    from PIL import Image       # only needed for picture files
    img = Image.open(path)
    return np.asarray(img.convert("L" if img.mode in ("L", "1", "I", "F") else "RGB"), dtype=np.uint8)


def _area_resize(img: np.ndarray, height: int, width: int) -> np.ndarray:
    """Average the source pixels that fall in each target cell. [H, W, C] float."""
    src_h, src_w = img.shape[:2]
    out = np.empty((height, width, img.shape[2]))
    for r in range(height):
        r0, r1 = (r * src_h) // height, max(((r + 1) * src_h + height - 1) // height, (r * src_h) // height + 1)
        for c in range(width):
            c0, c1 = (c * src_w) // width, max(((c + 1) * src_w + width - 1) // width, (c * src_w) // width + 1)
            out[r, c] = img[r0:r1, c0:c1].mean(axis=(0, 1))
    return out


def to_model_image(img: np.ndarray, shape: tuple[int, int, int],
                   invert: bool = False, stretch: bool = True) -> np.ndarray:
    """Picture -> uint8 [height, width, channels] in the training data's format.

    shape   (height, width, channels) of the training images
    The middle of the picture is kept if its proportions differ.
    invert  flip dark and bright (use for dark ink on a light background)
    stretch scale so the darkest pixel is 0 and the brightest is 255
    """
    height, width, channels = shape
    img = np.asarray(img, dtype=np.float64)
    if img.ndim == 2:
        img = img[:, :, None]
    img = img[:, :, :3]
    if channels == 1 and img.shape[2] == 3:
        img = (img @ np.array([0.299, 0.587, 0.114]))[:, :, None]
    elif channels == 3 and img.shape[2] == 1:
        img = np.repeat(img, 3, axis=2)
    # Cut the middle out so the picture has the training images' proportions.
    src_h, src_w = img.shape[:2]
    crop_h, crop_w = min(src_h, src_w * height // width), min(src_w, src_h * width // height)
    top, left = (src_h - crop_h) // 2, (src_w - crop_w) // 2
    img = img[top:top + crop_h, left:left + crop_w]
    out = _area_resize(img, height, width)
    if invert:
        out = 255.0 - out
    if stretch and out.max() > out.min():
        out = (out - out.min()) * (255.0 / (out.max() - out.min()))
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def ascii_art(image: np.ndarray) -> str:
    """What the network sees, for a quick look in the terminal."""
    ramp = " .:-=+*#%@"
    gray = image.astype(np.float64).mean(axis=2)
    return "\n".join("".join(ramp[int(v * (len(ramp) - 1) / 255)] * 2 for v in row) for row in gray)
