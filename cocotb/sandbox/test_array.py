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
async def identity_matrix_test(dut):

    # DESCRIPTION: Generates an identity matrix for easy validation.

    # "-- Start Set Up --"
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    # "-- End Set Up"

    # "Generating identity matrix"
    
    array = [2, 4, 8, 64]

    # "Generates each zeros matrix 2x2, 4x4, 8x8, 64x64"
    for i in array:
        matrix = [[0 for _ in range(i)] for _ in range(i)]
        for j in range(0, i): # Inserts 1's across the diagonal
            matrix[j][j] = 1
            # "matrix variable gets inserted as the input"

@cocotb.test()
async def single_nonzero_test():

    # DESCRIPTION: Changes one value at a time, checking to see if each memory address works.

    # "-- Start Set Up --"
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    # "-- End Set Up"

    # "Generating identity matrix"
    
    array = [2, 4]
    #Generates the identity matrix
    for i in array:
        matrix = [[0 for _ in range(i)] for _ in range(i)]
        for j in range(0, i):
            for k in range(0, i):
                matrix[j][k] = 1
                # Take this matrix value as the input since it changes back to zero after.
                matrix[j][k] = 0

@cocotb.test()
async def corner_case_test():

    # "-- Start Set Up --"
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    # "-- End Set Up"

@cocotb.test()
async def random_vector_size_test():

    # "-- Start Set Up --"
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    # "-- End Set Up"