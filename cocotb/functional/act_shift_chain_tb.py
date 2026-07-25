# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : act_shift_chain_tb.py
# Author    : R. Gupta
# Date      : Jul-19-2026
# --------------------------------------------------------------------------------------
# DUT       : act_shift_chain.sv
# Type      : Sequential, async reset
# Latency   : 1 clk cycle
# Framework : cocotb / Verilator
#
# DESCRIPTION
# ***********
#   ROWS shift_reg cells cascaded into one (ROWS*DW)-bit chain, one cell per array
#   row, driving the broadcast activation bit-plane. LOAD streams activations in
#   serially on a_b through cell 0; COMPUTE emits each cell's sr[0] as act_bp[i],
#   LSB-first over DW planes. Asynchronous reset.
#
# SPECIFICATION
# *************
#   @ negedge rst_n:
#       all states to 0
#   @ posedge clk:
#   LOAD    (en=1, c_en=0): a_b enters cell 0's MSB; the whole chain shifts toward
#                           the LSB; cell i's LSB feeds cell i+1's MSB. tail_out is
#                           the bit leaving the last cell.
#   COMPUTE (en=1, c_en=1): each cell zero-fills its MSB and shifts toward LSB.
#                           act_bp[i] = cell i's sr[0], 1:1 row map, no permutation.
#   en=0                  : hold.
#
# PARAMETERS
# **********
#   ROWS : chain cells / array rows   (adopted from dcim_pkg::ROWS)
#   DW   : bits per cell; planes       (adopted from dcim_pkg::DW)
#
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/shift_reg.sv, src/act_shift_chain.sv
#
# LIMITATIONS:  Per-cell shift verified in shift_reg_tb; this tb targets the chain
#               wiring and the load->cell reversal. c_en must stay high through the
#               DW compute cycles (FSM-guaranteed); a stray en&~c_en mid-compute
#               injects a chain bit into a cell MSB — not exercised here.
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-19-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# ======================================================================================

import cocotb

ROWS, DW = 32, 8      # TODO: read from dut when tests are added — do not hardcode.
CHAIN = ROWS * DW


# ---------- Golden Reference ----------
def golden_ref(cells: list[int], en: int, c_en: int, a_b: int) -> tuple[list[int], int, list[int]]:
    """Golden reference — one clock step of act_shift_chain

    Behaviour:
       Models ROWS cascaded DW-bit shift cells. LOAD cascades a_b through cell 0
       toward the LSB, cell i's LSB feeding cell i+1's MSB. COMPUTE zero-fills and
       shifts each cell, exposing act_bp[i]=cell i sr[0]. en=0 holds. act_bp is
       sampled BEFORE the shift (combinational tap). cells threaded across calls.
       Chain reverses row order: cell i ends holding the (ROWS-1-i)-th streamed byte.

    Args:
        cells (list[int]) : ROWS cells, each a DW-bit shift register (current state)
        en (int)          : master enable (0 holds)
        c_en (int)        : 1 COMPUTE (zero-fill), 0 LOAD (cascade a_b)
        a_b (int)         : serial activation bit into cell 0 (LOAD only)

    Returns:
        tuple[list[int], int, list[int]]
            - act_bp    : ROWS bits, act_bp[i] = cell i sr[0] THIS cycle
            - tail_out  : bit leaving the last cell (LOAD); 0 in COMPUTE
            - next_cells: cells after the edge
    """
    act_bp = [cells[i] & 1 for i in range(ROWS)]          # comb tap, before shift
    if not en:
        return act_bp, cells[ROWS-1] & 1, list(cells)
    nxt = list(cells)
    if c_en:                                              # COMPUTE
        nxt = [(cells[i] >> 1) & ((1 << DW) - 1) for i in range(ROWS)]
        tail = 0
    else:                                                 # LOAD: cascade
        carry = a_b
        for i in range(ROWS):
            out_bit = nxt[i] & 1
            nxt[i] = ((carry << (DW - 1)) | (nxt[i] >> 1)) & ((1 << DW) - 1)
            carry = out_bit
        tail = carry
    return act_bp, tail, nxt


def golden_tb():
    acts = [(r * 7 + 3) & 0xFF for r in range(ROWS)]      # distinct per row
    cells = [0] * ROWS

    # LOAD row 0 first ... row ROWS-1 last, each byte LSB-first
    for r in range(ROWS):
        for b in range(DW):
            _, _, cells = golden_ref(cells, en=1, c_en=0, a_b=(acts[r] >> b) & 1)

    # COMPUTE: drain DW planes, reconstruct each cell's byte LSB-first
    rec = [0] * ROWS
    for p in range(DW):
        act_bp, _, cells = golden_ref(cells, en=1, c_en=1, a_b=0)
        for i in range(ROWS):
            rec[i] |= act_bp[i] << p

    # documented reversal: cell i holds row (ROWS-1-i)'s activation
    assert all(rec[i] == acts[ROWS-1-i] for i in range(ROWS)), \
        f"chain mapping wrong: {rec}"

    # en=0 holds
    _, _, held = golden_ref(cells, en=0, c_en=1, a_b=1)
    assert held == cells, "en=0 must hold"

    print("act_shift_chain golden_ref self-check passed")


golden_tb()
