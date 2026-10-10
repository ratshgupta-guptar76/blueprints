"""System model of the DCIM demo chain. One package per stage:

    ml_model      the network: data, training, the integer math the chip must do
    fpga          (to come) scheduling, glue arithmetic, framing
    photonics     (to come) the fixed optical first layer
    digital_dcim  (to come) the bit-exact chip
    emulation.py  (to come) wires the stages together

Run the tools from the repository root, for example:
    python3 -m model.ml_model train
"""
