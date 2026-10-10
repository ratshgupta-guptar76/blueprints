"""Network shapes, written as one line of text so they are easy to try.

    conv3:8      3 x 3 convolution on the chip, 8 feature maps, ReLU.
                 The edge is zero-padded so the image keeps its size.
    conv3:8/2    the same, moving 2 pixels at a time (halves the image).
    ph2:4        photonic first layer: 2 x 2 window, 4 kernels, weights of zero
                 or more, 1-bit output. Moves a whole window at a time unless a
                 stride is given (ph3:4/1 moves one pixel and pads the edge).
                 Only allowed as the first layer. Two options relax it, to
                 measure what each restriction costs:
                   +s    signed weights (two photodiodes per output)
                   +b4   4-bit output instead of 1 bit (a converter, not a comparator)
                 for example ph3:16/1+s+b8
    conv1:32     1 x 1 convolution: mixes the feature maps at each position.
    dw3          depthwise 3 x 3 convolution: each feature map is filtered on
                 its own (9 inputs per output), so it never needs splitting.
                 Usually followed by conv1 to mix the maps.
    pool         keep the largest of every 2 x 2 block.
    gmax         keep the largest value of each whole feature map (one number
                 per map). Replaces a fully connected layer.
    fc:32        fully connected layer on the chip, 32 units, ReLU.
    attn:16      self-attention over the positions of the feature map, with
                 16-number queries and keys (at most 32, one chip weight set
                 deep). Every position looks at every other position and adds
                 what it finds to its own values. The image keeps its size and
                 its number of feature maps. See network.py for the math.

The last layer (fully connected, one output per class) is added automatically.

    "fc:16"                              the small network used for digits
    "conv3:8 pool conv3:16 pool fc:32"   a small convolutional network
    "ph2:4 conv3:16 pool fc:32"          the same idea with an optical first layer
    "conv3:16 pool dw3 conv1:32 pool dw3 conv1:32 gmax"
                                         convolution only, every layer one chip pass
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PRESETS = {
    "mlp": "fc:16",
    "small": "conv3:8 pool conv3:16 pool fc:32",
    "photonic": "ph2:4 conv3:16 pool fc:32",
}


@dataclass(frozen=True)
class Spec:
    kind: str           # "conv", "ph", "dw", "pool", "fc", "attn"
    k: int = 1
    outputs: int = 0
    stride: int = 1
    signed: bool = False    # photonic only: weights may be negative
    out_bits: int = 1       # photonic only: width of the output


def parse(text: str) -> list[Spec]:
    text = PRESETS.get(text, text)
    specs = []
    for i, token in enumerate(text.split()):
        if token == "pool":
            specs.append(Spec("pool", 2, 0, 2))
        elif token == "gmax":
            specs.append(Spec("pool", 0, 0, 0))        # k = 0: the whole map
        elif m := re.fullmatch(r"dw(\d)(?:/(\d))?", token):
            if not i:
                raise ValueError("a depthwise layer (dw) cannot be the first layer")
            specs.append(Spec("dw", int(m[1]), 0, int(m[2]) if m[2] else 1))
        elif m := re.fullmatch(r"fc:(\d+)", token):
            specs.append(Spec("fc", 1, int(m[1])))
        elif m := re.fullmatch(r"attn:(\d+)", token):
            if not 1 <= int(m[1]) <= 32:
                raise ValueError("attn takes 1 to 32 numbers per query (one chip weight set deep)")
            specs.append(Spec("attn", 1, int(m[1])))
        elif m := re.fullmatch(r"(conv|ph)(\d):(\d+)(?:/(\d))?((?:\+(?:s|b\d))*)", token):
            kind, k, opts = m[1], int(m[2]), m[5].split("+")[1:]
            if kind == "ph" and i:
                raise ValueError("a photonic layer (ph) can only be the first layer")
            if kind == "conv" and opts:
                raise ValueError("+s and +b only apply to a photonic layer (ph)")
            bits = next((int(o[1:]) for o in opts if o[0] == "b"), 1)
            specs.append(Spec(kind, k, int(m[3]), int(m[4]) if m[4] else (k if kind == "ph" else 1),
                              signed="s" in opts, out_bits=bits))
        else:
            raise ValueError(f"cannot read '{token}'. Examples: conv3:8  conv3:8/2  conv1:32  dw3  attn:16  ph2:4  pool  gmax  fc:32")
    for a, b in zip(specs, specs[1:]):
        if a.kind == "fc" and b.kind != "fc":
            raise ValueError("after a fully connected layer only fully connected layers may follow")
    return specs
