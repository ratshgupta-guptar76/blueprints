"""Front ends: whatever turns an 8-bit image into the chip's first input vector.

A front end is an object with
    name    registry name
    bits    width of each value it produces (this is P of the first layer)
    params  dict that rebuilds it (stored with the trained network)
    __call__(images uint8 [n, h, w, c]) -> integers [n, features], values 0..2^bits - 1

To add one (for example the photonic first layer): write the class and decorate
it with @register("name"). The network trains on whatever the front end emits.
"""
from __future__ import annotations

import numpy as np

FRONTENDS: dict[str, type] = {}


def register(name: str):
    def deco(cls):
        cls.name = name
        FRONTENDS[name] = cls
        return cls
    return deco


def build(name: str, **params):
    if name not in FRONTENDS:
        raise KeyError(f"unknown front end '{name}', have: {', '.join(sorted(FRONTENDS))}")
    return FRONTENDS[name](**params)


@register("pixels")
class Pixels:
    """No first-layer hardware: the pixels themselves, row by row, keeping the
    top `bits` bits of each. bits = 8 sends the full pixel, bits = 1 is a plain
    black and white threshold at half scale."""

    def __init__(self, bits: int = 8):
        if not 1 <= bits <= 8:
            raise ValueError("bits must be 1..8")
        self.bits = bits
        self.params = {"bits": bits}

    def __call__(self, images: np.ndarray) -> np.ndarray:
        return (images.reshape(len(images), -1) >> (8 - self.bits)).astype(np.int16)
