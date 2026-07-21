# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : lane_shift_accum_tb.py
# Author    : R. Gupta
# Date      : Jul-18-2026
# --------------------------------------------------------------------------------------
# DUT       : lane_shift_accum.sv
# Type      : Sequential, async reset
# Latency   : 1 Clk Cycle
# Framework : cocotb / Verilator
# 
# DESCRIPTION
# ***********
#   One output lane, reduces a single signed weight's DW bit-columns into one ACC_WIDTH
#   signed result. Two reductions done on two different axes: Combinational Horizontal
#   Axis, Temporal Accumulate Axis. Horizontal Axis combines the DW column-sums into a
#   signed lane (signedness applied here). Temporal Axis registers the accumulator of 
#   that lane value across bit-planes (LSB-first). The reset is asynchronous.
# 
# SPECIFICATION
# *************
#   [Horizontal Axis (1)] ->
#   lane_val  =  ∑_{b=0}^{DW−2} (col_adder[b]    · 2^b)
#                              ± col_adder[DW−1] · 2^(DW−1)
#   (Subtract the MSB column if W_SIGN, else add)
# 
#   [Temporal Axis (2)] ->
#   @ negedge rst_n:
#       y = 0
#   @ posedge clk, clr:         // Takes priority over `en`
#       y = 0
#   @ posedge clk, en:
#       if A_SIGN && bp_idx=DW-1;
#           y = y - (lane_val <<< bp_idx)
#       else
#           y = y + (lane_val <<< bp_idx)
# 
# PARAMETERS
# **********
#   ROWS: # of rows summed per column-sum (adopted from dcim_pkg::ROWS)
#   DW: data-width of activations a.k.a. depth of lane_shift_accum (adopted from dcim_pkg::DW)
#   ACC_WIDTH: data-width of accumulator/output (adopted from dcim_pkg::ACC_WIDTH)
#   A_SIGN: activation signedness (adopted from dcim_pkg::A_SIGN)
#   W_SIGN: weight signedness (adopted from dcim_pkg::W_SIGN)
# 
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/lane_shift_accum.sv
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# ======================================================================================

import cocotb

ROWS, DW, ACC_WIDTH, A_SIGN, W_SIGN = 32, 8, 22, 0, 1 # TODO: read from dut when tests are addded - do not hardcode.

# Helper function
# TODO: Add to different file
def to_signed(v: int, w: int) -> int:
    """Interpret the low w bits of v as a two's-complement signed integer."""
    v &= (1 << w) - 1                       # mask to w bits
    return v - (1 << w) if v & (1 << (w - 1)) else v

# ---------- Golden Reference ----------
def _combine(col_adder: list[int]) -> int:
    """Horizontal weight-bit combine (Full signed weight
    multiplication for each activation plane)
    
    Reduces the DW column-sums of one lane into a single signed lane value.
    bits 0...DW-2 add with weight 2^b. The MSB column (DW-1) subtracts when
    W_SIGN = 1, else adds. Weight sign is applied here.

    Args:
        col_adder (list[int]): DW column-sums (unsigned popcounts, 0...ROWS),
                               index b is weight-bit b of this lane.

    Returns:
        out (int): signed lane value
    """

    add_bin = sum(col_adder[b] << b for b in range(DW - 1))
    msb = col_adder[DW - 1] << (DW - 1)
    return add_bin - msb if W_SIGN else add_bin + msb


def golden_ref(y: int, clr: int, en: int, bp_idx: int, col_adder: list[int]) -> int:
    """Computes the golden reference output for a single Lane Shift Accumulator

    Behaviour:
       Combines this cycle's column-sums into a signed lane value and accumulates it
       into a y, shifted by bp_idx (LSB-first). y is threaded across calls. clr 
       zeroes y and overrides en. Output (y) wraps to ACC_WIDTH.

    Args:
        y (int)               : current signed accumulator/output
        clr (int)             : clear (zero) the accumulator - has priority over en
        en (int)              : accumulate-enable for this plane
        bp_idx (int)          : bit-plane index 0..DW-1 (left-shift amount, LSB-first)
        col_adder (list[int]) : DW column-sums for this lane this cycle

    Returns:
        out (int) : signed accumulator value after this clock edge. wrapped to ACC_WIDTH
    """

    lane_val = _combine(col_adder)
    if clr:
        next_y = 0
    elif en:
        if A_SIGN and bp_idx == DW - 1:
            next_y = y - (lane_val << bp_idx)
        else:
            next_y = y + (lane_val << bp_idx)
    else:
        next_y = y
    
    return to_signed(next_y & ((1 << ACC_WIDTH) - 1), ACC_WIDTH)

def golden_tb():
    def run(W_signed, A_unsigned):
        Wb = [(W_signed >> b) & 1 for b in range(DW)]
        y = 0
        for p in range(DW):                          # LSB-first planes
            ap = (A_unsigned >> p) & 1
            col = [Wb[b] & ap for b in range(DW)]     # 1-row lane
            y = golden_ref(y, clr=0, en=1, bp_idx=p, col_adder=col)
        return y
    for W, A, exp in [(-1,1,-1), (127,255,32385), (-128,255,-32640),
                      (-128,1,-128), (-50,200,-10000), (100,100,10000)]:
        got = run(to_signed(W & 0xFF, 8), A)
        assert got == exp, f"W={W} A={A}: got {got}, expected {exp}"
    print("lane_shift_accum golden_ref self-check passed")

golden_tb()
