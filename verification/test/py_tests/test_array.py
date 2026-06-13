import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ReadOnly
import random
import numpy as np

MAX_SIZE = 64

async def reset_dut(dut):
    """Reset the hardware."""
    dut.rst_n.value = 0
    dut.valid_in.value = 0
    dut.a.value = 0
    dut.b.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

# "Identity matrix test"
@cocotb.test()
async def matrixTest(dut):

    # "-- Start Set Up --"
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    # "-- End Set Up"

    # "Generating identity matrix"
    array = [2, 4, 8, 64]

    # "Generates each zeros matrix 2x2, 4x4, 8x8, 64x64"
    for i in array:
        matrix = np.zeros(i, i)
        # "Inserts the 1's into the matrix"
        for j in range(i):
            matrix[j][j] = 1
        # "matrix variable gets inserted as the input"
        



    dut._log.info("SUCCESS")