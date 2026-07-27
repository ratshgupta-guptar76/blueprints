# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : col_adder_tb.py
# Author    : R. Gupta
# Date      : Jul-19-2026
# --------------------------------------------------------------------------------------
# DUT       : col_adder.sv
# Type      : Combinational
# Framework : cocotb / Verilator
# 
# DESCRIPTION
# ***********
#   Single column vertical reduction. Sums the ROWS partial-product bits of one bit-
#   column into an unsigned column-sum (a popcount). Plain addition only. No weight-
#   bit weighting, no bit-plane shift, no sign (those belong in shift_accum).
# 
# SPECIFICATION
# *************
#   sum = popcount(pp_col)
#   Inputs are active-high (pp[i] = w & a)
#   sum width = $clog2(ROWS+1)
# 
# PARAMETERS
# **********
#   ROWS: # of partial-product bits per column (adopted from dcim_pkg::ROWS)
# 
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/col_adder.sv
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# Jul-24-2026 | R. Gupta      | * v1.1   | Move Golden-Ref to cocotb/golden/col_adder
# ======================================================================================

import os
import random
import cocotb
from cocotb.triggers import Timer
from cocotb.types import LogicArray

import golden.col_adder as ref
from golden.col_adder import golden_ref

@cocotb.test()
async def test_directed_corners(dut) -> None:
    """Column popcount over generated corner vectors.

    Method :
        > Directed

    Stimulus :
        - zero
        - all-ones
        - walking single bit
        - alternating

    Catches :
        - all-ones maxes width -> narrow output
        - walking bit -> unwired line.
    """
    ROWS = int(dut.ROWS.value)

    # params for golden_ref
    ref.ROWS = ROWS

    # corner vectors
    corners = [
        0,                                      # zero
        (1 << ROWS) - 1,                        # all-ones -> ROWS
        *(1 << i for i in range(ROWS)),         # walking single bit
        int("01" * (ROWS // 2), 2),             # alternating 0101...
        int("10" * (ROWS // 2), 2),             # alternating 1010...
    ]

    for vec in corners:
        dut.pp_col.value = vec
        await Timer(1, "ns")            # combinational settle
        got = int(dut.sum.value)
        exp = golden_ref(vec)
        assert got == exp, f"pp_col={vec:#0{ROWS//4+2}x}: actual={got}, expected={exp}"


@cocotb.test()
async def test_crv_adder(dut) -> None:
    """Column adder over random vectors.
    
    Method :
        > Constrained-Random Verification (CRV)

    Stimulus :
        - uniform random vectors of ROWS bits
        - binomial distribution of 0s and 1s, to stress the adder

    Catches :
        - mid-range range arithmetic errors corners never reach
    """
    ROWS = int(dut.ROWS.value)

    # params for golden_ref
    ref.ROWS = ROWS

    N    = 10000        # Number of random vectors to tests
    seed = int(os.environ.get("SEED", cocotb.RANDOM_SEED))
    rng  = random.Random(seed)
    dut._log.info(f"col_adder_tb.test_crv_adder: seed={seed}, N={N}, ROWS={ROWS}")

    for _ in range(N):
        vec = rng.getrandbits(ROWS)
        dut.pp_col.value = vec
        await Timer(1, "ns")
        got = int(dut.sum.value)
        exp = golden_ref(vec)
        assert 0 <= got <= ROWS, \
            f"pp_col={vec:#0{ROWS//4+2}x}: actual={got} out of range [0, {ROWS}] @ seed={seed}"
        assert got == exp, \
            f"pp_col={vec:#0{ROWS//4+2}x}: actual={got}, expected={exp} @ seed={seed}"


@cocotb.test(skip=(os.environ.get("SIM") != "icarus"))
async def test_x_prop(dut) -> None:
    """Unknown propagation through reduction tree.

    Method :
        > X-Propagation

    Stimulus :
        - single unknown bit (1'bX) at MSB all others driven 0
        - single unknown bit (1'bX) at LSB all others driven 0
        - single unknown bit (1'bX) at mid all others driven 0


    Catches :
        - X-masking arithmetic that resolves an unknown input into a
        - Undercount or Overcount at X-prop
    """
    ROWS = int(dut.ROWS.value)

    # params for golden_ref
    ref.ROWS = ROWS

    position = [
        0,          # LSB
        ROWS // 2,  # mid
        ROWS - 1    # MSB
    ]

    for pos in position:
        bits = ["0"] * ROWS
        bits[ROWS-1 - pos] = "x"
        dut.pp_col.value = LogicArray("".join(bits))
        await Timer(1, "ns")

        sum_val = dut.sum.value
        assert not sum_val.is_resolvable, \
            f"X at bit {pos} produced resolved sum={sum_val}. X was masked"
