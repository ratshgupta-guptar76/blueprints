"""fpga: scheduling and glue arithmetic around the chip.

    host.py   cut layers into weight sets, run the batch, do the leftover math
"""
from .host import Fpga, GlueOps

__all__ = ["Fpga", "GlueOps"]
