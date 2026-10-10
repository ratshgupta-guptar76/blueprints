"""digital_dcim: the bit-exact chip.

    chip.py       the arithmetic, the Chip object, the cycle estimates
    __main__.py   self checks: python3 -m model.digital_dcim
"""
from .chip import (ACC_WIDTH, DW, N_OUT, ROWS, Chip, chip_pass, raw_width,
                   v1_period, v2_period, wrap)

__all__ = ["ACC_WIDTH", "DW", "N_OUT", "ROWS", "Chip", "chip_pass", "raw_width",
           "v1_period", "v2_period", "wrap"]
