# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : shift_accum_tb.py
# Author    : R. Gupta
# Date      : Jul-18-2026
# --------------------------------------------------------------------------------------
# DUT       : shift_accum.sv
# Type      : Sequential, async reset
# Latency   : 1 Clk Cycle
# Framework : cocotb / Verilator
# 
# DESCRIPTION
# ***********
#   All output lanes, reduces a every signed weight's DW bit-columns into N_WEIGHTS -
#   ACC_WIDTH signed results. Two reductions done on two different axes:
#   Combinational Horizontal Axis, Temporal Accumulate Axis. Horizontal Axis 
#   combines the DW column-sums into signed lanes (signedness applied here). Temporal 
#   Axis registers the accumulator of that lane value across bit-planes (LSB-first). 
#   The reset is asynchronous.
# 
# SPECIFICATION
# *************
#   SLICE (the module's only logic):
#       col_adders[i][b] = sum[i*DW + b]      for lane i in 0..N_WEIGHTS-1,
#                                                 bit  b in 0..DW-1
#       => lane i holds weight i's DW column-sums, LSB-aligned:
#          col_adders[i][0]    = sum[i*DW]        (weight i LSB column)
#          col_adders[i][DW-1] = sum[i*DW + DW-1] (weight i MSB column)
#   Per-lane behaviour: identical to lane_shift_accum (see that spec).
#   Shared: en, clr, bp_idx broadcast to all lanes; y[i] each ACC_WIDTH signed.
# 
# 
# PARAMETERS
# **********
#   ROWS: # of rows summed per column-sum (adopted from dcim_pkg::ROWS)
#   N_WEIGHTS: # of weights a.k.a. total outputs (adopted from dcim_pkg::N_WEIGHTS)
#   DW: data-width of activations (adopted from dcim_pkg::DW)
#   ACC_WIDTH: data-width of accumulator/output (adopted from dcim_pkg::ACC_WIDTH)
#   A_SIGN: activation signedness (adopted from dcim_pkg::A_SIGN)
#   W_SIGN: weight signedness (adopted from dcim_pkg::W_SIGN)
# 
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/lane_shift_accum.sv src/shift_accum.sv
# 
# LIMITATIONS:  Lane arithmetic is verified in lane_shift_accum_tb; this tb targets
#               the slice/mapping (which columns feed which lane) and lane
#               independence. ACC_WIDTH read from DUT, not set here.
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# ======================================================================================

import cocotb

ROWS, N_WEIGHTS, DW, ACC_WIDTH, A_SIGN, W_SIGN = 32, 4, 8, 22, 0, 1 # TODO: read from dut when tests are addded - do not hardcode.
COLS = N_WEIGHTS*DW
# Helper function
# TODO: Add to different file
def to_signed(v: int, w: int) -> int:
    """Interpret the low w bits of v as a two's-complement signed integer."""
    v &= (1 << w) - 1                       # mask to w bits
    return v - (1 << w) if v & (1 << (w - 1)) else v

# ---------- Golden Reference ----------
def golden_ref(y: list[int], clr: int, en: int, bp_idx: int, col_sums: list[int]) -> list[int]:
    """Computes the golden reference output for a single Lane Shift Accumulator

    Behaviour:
       Slices the COLS column-sums into N_WEIGHTS groups of DW, then combines and accumulates
       each lane independently. y is threaded across temporal planes.

    Args:
        y (list[int])        : N_WEIGHTS signed accumulators entering this cycle
        clr (int)            : clear (zero) all accumulators - has priority over en
        en (int)             : accumulate-enable for this plane (cycle)
        bp_idx (int)         : bit-plane index 0..DW-1 (left-shift amount, LSB-first)
        col_sums (list[int]) : COLS column-sums for this lane this cycle

    Returns:
        out (list[int]) : N_WEIGHTS signed accumulator values after this clock edge. Wrapped to ACC_WIDTH
    """

    next_y = []
    for i in range(N_WEIGHTS):
        col = [col_sums[i*DW + b] for b in range(DW)]   # SLICE: lane i's DW columns
        # combine (independent reimplementation, not a call to lane's _combine)
        add_bin = sum(col[b] << b for b in range(DW-1))
        msb = col[DW-1] << (DW-1)
        lane_val = add_bin - msb if W_SIGN else add_bin + msb
        # accumulate
        if clr:            nxt_y_val = 0
        elif en:           nxt_y_val = (y[i] - (lane_val<<bp_idx)) if (A_SIGN and bp_idx==DW-1) else (y[i] + (lane_val<<bp_idx))
        else:              nxt_y_val = y[i]
        next_y.append(to_signed(nxt_y_val & ((1<<ACC_WIDTH)-1), ACC_WIDTH))
    return next_y

def golden_tb():
    def run(weights, activations):
        """Full matvec, single-row array. weights[i]/activations[i] per lane.
           Lane i owns columns [i*DW : i*DW+DW] = weight i's bits."""
        Wb = [[(weights[i] >> b) & 1 for b in range(DW)] for i in range(N_WEIGHTS)]
        y = [0] * N_WEIGHTS
        for p in range(DW):                              # LSB-first planes
            col_sums = [0] * COLS
            for i in range(N_WEIGHTS):
                ap = (activations[i] >> p) & 1
                for b in range(DW):
                    col_sums[i*DW + b] = Wb[i][b] & ap   # 1-row col-sum
            y = golden_ref(y, clr=0, en=1, bp_idx=p, col_sums=col_sums)
        return y

    # 1. each lane independently correct — signed matvec, hard cases per lane
    W = [to_signed(x & 0xFF, 8) for x in (0xFF, 0x7F, 0x80, 0x01)]   # -1, 127, -128, 1
    A = [1, 255, 255, 200]
    exp = [W[i] * A[i] for i in range(N_WEIGHTS)]
    got = run(W, A)
    assert got == exp, f"per-lane matvec: got {got}, expected {exp}"

    # 2. SLICE isolation: only lane 2 driven -> only y[2] nonzero
    W = [0, 0, to_signed(0x80, 8), 0]
    A = [255, 255, 255, 255]
    got = run(W, A)
    assert got[2] == -128*255 and all(got[i] == 0 for i in (0, 1, 3)), f"slice leak: {got}"

    # 3. clr zeroes all lanes
    y = [12345, -6789, 42, -1]
    assert golden_ref(y, clr=1, en=1, bp_idx=0, col_sums=[0]*COLS) == [0]*N_WEIGHTS

    print("shift_accum golden_ref self-check passed")

golden_tb()
