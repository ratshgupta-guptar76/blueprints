# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : adder_tree_tb.py
# Author    : R. Gupta
# Date      : Jul-19-2026
# --------------------------------------------------------------------------------------
# DUT       : adder_tree.sv
# Type      : Combinational
# Framework : cocotb / Verilator
# 
# DESCRIPTION
# ***********
#   Vertical reduction across the partial-product matrix. Produces one column-sum per
#   column (sum[c] = popcount of column c across all ROWS). Vertical reduction only.
# 
# SPECIFICATION
# *************
#   sum[c] = popcount( {pp[0][c], pp[1][c], ... , pp[ROWS-1][c]} ) for each c
#   pp is row-major, Inputs are active-high (pp[r][c] = w & a)
#   sum[c] width = $clog2(ROWS+1)
# 
# PARAMETERS
# **********
#   ROWS: # of partial-product bits per column (adopted from dcim_pkg::ROWS)
#   COLS: # of column trees (adopted from dcim_pkg::COLS)
# 
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/adder_tree.sv
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# Jul-26-2026 | R. Gupta      | * v1.1   | Move Golden-Ref to cocotb/golden/adder_tree
# ======================================================================================

import os
import random
import cocotb
from cocotb.triggers import Timer
from cocotb.types import LogicArray, Range

import golden.adder_tree as ref
from golden.adder_tree import golden_ref

def pack(pp: list[int], ROWS: int, COLS: int) -> int:
    v = 0
    for r in range(ROWS):
        v |= (pp[r] & ((1 << COLS) - 1)) << (r * COLS)
    return v

def unpack(sum: LogicArray, ROWS: int, COLS: int) -> list[int]:
    RW = (ROWS).bit_length()
    return [int(sum[(c+1)*RW - 1 : c*RW]) for c in range(COLS)]

@cocotb.test()
async def test_directed_tree_corners(dut) -> None:
    """Per-column reduction over generated corner matrices.

    Method :
        > Directed

    Stimulus :
        - all-zero -> every sum[c] = 0
        - all-ones -> every sum[c] = ROWS
        - single 1 at each (r,c) -> sum[c]=1, all other columns 0
        - one full column of ones -> that sum[c]=ROWS, others 0

    Catches :
        - transpose swap pp[c][r] (off-diagonal single-bit positions)
        - a bit routed to the wrong column tree
    """
    ROWS = int(dut.ROWS.value)
    COLS = int(dut.COLS.value)

    # params for golden_ref
    ref.ROWS = ROWS
    ref.COLS = COLS

    # all zero
    zeroes = [0] * ROWS
    zeroes_packed = pack(zeroes, ROWS, COLS)
    dut.pp.value = zeroes_packed
    await Timer(1, "ns")
    got = unpack(dut.sum.value, ROWS, COLS)
    exp = golden_ref(zeroes)
    assert got == exp, f"all zero: got={got}, exp={exp}"

    # all ones
    ones = [(1 << COLS) - 1] * ROWS
    ones_packed = pack(ones, ROWS, COLS)
    dut.pp.value = ones_packed
    await Timer(1, "ns")
    got = unpack(dut.sum.value, ROWS, COLS)
    exp = golden_ref(ones)
    assert got == exp, f"all ones: got={got}, exp={exp}"

    # single bit at (r,c): row r has bit c set (logic HI)
    pp = [0] * ROWS         # Initialize pp to all zeros
    for r in range(ROWS):
        for c in range(COLS):
            pp[r] = 1 << c
            dut.pp.value = pack(pp, ROWS, COLS)
            await Timer(1, "ns")
            got = unpack(dut.sum.value, ROWS, COLS)
            exp = golden_ref(pp)
            assert got == exp, f"single bit at ({r},{c}): got={got}, exp={exp}"
        pp = [0] * ROWS         # Reset pp to all zeros for next row

    # full column of ones: column c has all rows set (logic HI)
    pp = [0] * ROWS             # Initialize pp to all zeros
    for c in range(COLS):
        pp = [(1 << c)] * ROWS  # Set all bits in column c
        dut.pp.value = pack(pp, ROWS, COLS)
        await Timer(1, "ns")
        got = unpack(dut.sum.value, ROWS, COLS)
        exp = golden_ref(pp)
        assert got == exp, f"full column of ones at ({c}): got={got}, exp={exp}"

@cocotb.test()
async def test_crv_adder_tree(dut) -> None:
    """Per-column reduction over random partial-product matrices.

    Method :
        > Constrained-Random Verification (CRV)

    Stimulus :
        - uniform random ROWS x COLS bit matrix
        - dense: all columns active at once

    Catches :
        - transpose swap on diagonal cells the single-bit walk cannot reach
        - cross-column contamination under simultaneous load
    """
    ROWS = int(dut.ROWS.value)
    COLS = int(dut.COLS.value)

    # params for golden_ref
    ref.ROWS = ROWS
    ref.COLS = COLS

    N = 10000
    seed = int(os.environ.get("SEED", cocotb.RANDOM_SEED))
    rng  = random.Random(seed)
    dut._log.info(f"adder_tree_tb.test_crv_adder_tree: seed={seed}, N={N}, ROWS={ROWS}, COLS={int(dut.COLS.value)}")

    pp = [0] * ROWS         # Initialize pp to all zeros
    for _ in range(N):
        pp = [rng.getrandbits(COLS) for _ in range(ROWS)]
        dut.pp.value = pack(pp, ROWS, COLS)
        await Timer(1, "ns")
        got = unpack(dut.sum.value, ROWS, COLS)
        exp = golden_ref(pp)
        assert got == exp, f"CRV: pp={pp}: got={got}, exp={exp} @ seed={seed}"


@cocotb.test(skip=(os.environ.get("SIM") != "icarus"))
async def test_x_prop_tree(dut) -> None:
    """Unknown confinement across the column trees (Icarus only).

    Method :
        > X-Propagation

    Stimulus :
        - single X bit in one column, all other bits driven 0

    Catches :
        - X smearing into neighbouring columns' sums
        - X-masking that resolves an unknown input into a clean sum
    """
    ROWS = int(dut.ROWS.value)
    COLS = int(dut.COLS.value)

    # params for golden_ref
    ref.ROWS = ROWS
    ref.COLS = COLS

    RW = (ROWS).bit_length()        # $clog2(ROWS+1)

    # X at (r, c)
    for c in [0, COLS // 2, COLS-1]:
        r = ROWS // 2
        xIdx = r*COLS + c

        pp = ["0"] * ROWS*COLS              # Initialize pp to all zeros
        pp[ROWS*COLS - 1 - xIdx] = "x"      # set bit at (r, c) to unknown (1'bX)
        dut.pp.value = LogicArray("".join(pp))
        await Timer(1, "ns")

        sum_val = dut.sum.value
        fields = [(sum_val[(k+1)*RW - 1 : k*RW]) for k in range(COLS)]
        for cc in range(COLS):
            if cc == c:
                assert not fields[cc].is_resolvable, \
                    f"X at ({r},{c}): sum[{cc}]={fields} should be X"
            else:
                assert fields[cc].is_resolvable, \
                    f"X at ({r},{c}): sum[{cc}]={fields} should be 0"
