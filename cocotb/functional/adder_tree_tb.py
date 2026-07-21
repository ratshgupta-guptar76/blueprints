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
# DEPENDENCIES: src/dcim_pkg.sv, src/col_adder.sv, src/adder_tree.sv
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# ======================================================================================

import cocotb

ROWS, COLS = 32, 32  # TODO: read from dut when tests are addded - do not hardcode.

# ---------- Golden Reference ----------
def golden_ref(pp: list[int]) -> list[int]:
    """Golden reference output — Vertical Reduction Tree per-column vector

    Behaviour:
       Computes sum[c] as the popcount of c across all rows.

    Args:
        pp (list[int]) : packed partial-product matrix. Row-Major.

    Returns:
        out (list[int]) : sum[c] = popcount( pp[c] ), range 0..ROWS
    """

    return [sum((pp[r] >> c) & 1 for r in range(ROWS)) for c in range(COLS)]

def golden_tb():
    # --- transpose / mapping: single-bit-set pins column c, not row r ---
    pp = [0]*ROWS; pp[3] = 1 << 7                      # pp[3][7] = 1
    s = golden_ref(pp)
    assert s[7] == 1 and sum(s) == 1, f"pp[3][7]=1 -> {s}, expected only sum[7]=1"

    # --- matrix corners (catch row/col swap + boundary indexing) ---
    pp = [0]*ROWS; pp[0] = 1 << 0                      # pp[0][0]
    assert golden_ref(pp)[0] == 1 and sum(golden_ref(pp)) == 1
    pp = [0]*ROWS; pp[ROWS-1] = 1 << (COLS-1)          # pp[ROWS-1][COLS-1]
    assert golden_ref(pp)[COLS-1] == 1 and sum(golden_ref(pp)) == 1

    # --- off-diagonal distinguishes a symmetric swap ---
    pp = [0]*ROWS; pp[0] = 1 << (COLS-1)               # pp[0][COLS-1]
    assert golden_ref(pp)[COLS-1] == 1 and sum(golden_ref(pp)) == 1

    # --- full column: column 5 set in every row -> sum[5] == ROWS ---
    pp = [1 << 5]*ROWS
    s = golden_ref(pp)
    assert s[5] == ROWS and sum(s) == ROWS, f"full col 5 -> {s}"

    # --- bounds ---
    assert golden_ref([0]*ROWS) == [0]*COLS
    assert golden_ref([(1 << COLS)-1]*ROWS) == [ROWS]*COLS

    print("adder_tree golden_ref self-check passed")

golden_tb()

