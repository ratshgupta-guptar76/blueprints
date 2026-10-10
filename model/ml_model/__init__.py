"""ml_model: the network the hardware has to run.

    datasets.py    8-bit image datasets (add one with @register)
    frontend.py    image -> input values (pixel precision)
    arch.py        network shapes as one line of text
    network.py     the integer network: the exact math the hardware must do
    train.py       PyTorch training, float then integer fine-tune (needs PyTorch)
    preprocess.py  live picture -> image in the training data's format
    __main__.py    command line: train, sweep, show, predict

Typical use from another stage:

    from model.ml_model import QNet, frontend
    net = QNet.load("model/build/net.npz")
    fe = frontend.build(net.meta["frontend"], **net.meta["frontend_params"])
    answer = net.predict(fe(images), matvec=my_chip_matvec)
"""
from . import arch, datasets, frontend, preprocess
from .network import Layer, QNet, reference_matvec

__all__ = ["arch", "datasets", "frontend", "preprocess", "Layer", "QNet", "reference_matvec"]
