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
# ======================================================================================

import cocotb

ROWS = 32  # TODO: read from dut when tests are addded - do not hardcode.

# ---------- Golden Reference ----------
def golden_ref(pp_col: int) -> int:
    """Golden reference output — Single Column Vertical Reduction Tree

    Behaviour:
       Counts the set bits of one bit-column's partial products. Inputs are
       active-high and the sum is a plain pop-count

    Args:
        pp_col (int) : ROWS-bit column of active-high partial-product bits

    Returns:
        out (int) : sum = popcount(pp_col), range 0..ROWS
    """

    return bin(pp_col & ((1 << ROWS) - 1)).count("1")

def golden_tb():
    assert golden_ref(0) == 0
    assert golden_ref((1 << ROWS) - 1) == ROWS
    assert golden_ref(0b1011) == 3
    print("col_adder golden_ref self-check passed")

golden_tb()

