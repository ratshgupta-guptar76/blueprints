# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : dcim_array_tb.py
# Author    : R. Gupta
# Date      : Jul-19-2026
# --------------------------------------------------------------------------------------
# DUT       : dcim_array.sv
# Type      : Sequential, no reset on w_mem
# Latency   : write registered (1 cycle); pp combinational
# Framework : cocotb / Verilator
#
# DESCRIPTION
# ***********
#   Weight storage plus the AND multiply grid. Stores the weight matrix one row at a
#   time and outputs 1-bit partial products (weight AND activation) for the current
#   bit-plane. The storage is a placeholder (behavioural, swapped for the 8T/10T SRAM
#   macro at PnR); this tb targets the ADDRESSING and MULTIPLY logic around it, not
#   the storage cell.
#
# SPECIFICATION
# *************
#   Write (registered):
#       w_en=1 => row selected by row_addr latches w_buf; all other rows unchanged.
#       w_en=0 => no row changes (no stray write).
#   Multiply (combinational, active-high):
#       pp[r][c] = w_mem[r][c] AND act_bp[r]
#       => act_bp[r] broadcasts across ALL columns of row r (per-ROW gate, not
#          per-column). No inversion (column inverter is a macro-swap step upstream).
#   Column mapping (contract shared with weight_load + golden_model):
#       column c holds weight-bit (c % DW) of sub-weight (c // DW).
#   w_mem has NO reset (SRAM powers up unknown) — all rows must be written before
#   any meaningful pp; there is no read port (observe w_mem only through pp).
#
# PARAMETERS
# **********
#   ROWS : array rows           (adopted from dcim_pkg::ROWS)
#   COLS : array columns        (adopted from dcim_pkg::COLS)
#   DW   : bits per sub-weight  (adopted from dcim_pkg::DW)
#
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/row_decoder.sv, src/dcim_array.sv
#
# LIMITATIONS:  Verifies addressing, write-select, the AND axis, and column mapping —
#               NOT the bitcell (that is SPICE: SNM/read-disturb/margins). The two meet
#               at the active-high contract. Storage correctness assumed (placeholder);
#               only the logic around it is checked here.
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-19-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# ======================================================================================

import cocotb

ROWS, COLS, DW = 32, 32, 8      # TODO: read from dut when tests are added — do not hardcode.


# ---------- Golden Reference ----------
def golden_ref(w_mem: list[int], w_en: int, row_addr: int, w_buf: int,
               act_bp: int) -> tuple[list[int], list[int]]:
    """Golden reference — one clock step of dcim_array (from spec, not RTL)

    Behaviour:
       Combinational multiply on the CURRENT weight memory (pp[r] = w_mem[r] gated
       by act_bp[r], active-high), then a registered single-row write: w_en selects
       one row (row_addr) to latch w_buf, all others hold; w_en=0 writes nothing.
       w_mem threaded across calls. Observe storage only through pp (no read port).

    Args:
        w_mem (list[int]) : ROWS rows, each a COLS-bit weight row (current state)
        w_en (int)        : write enable (1 = latch selected row)
        row_addr (int)    : row to write when w_en
        w_buf (int)       : COLS-bit row value to write
        act_bp (int)      : ROWS-bit activation plane; bit r gates row r

    Returns:
        tuple[list[int], list[int]]
            - pp         : ROWS product rows THIS cycle (combinational)
            - next_w_mem : weight memory after the write edge
    """
    mask = (1 << COLS) - 1
    pp = [w_mem[r] & (mask if (act_bp >> r) & 1 else 0) for r in range(ROWS)]
    if w_en:
        nxt = list(w_mem)
        nxt[row_addr] = w_buf & mask
        return pp, nxt
    return pp, list(w_mem)


def golden_tb():
    full = (1 << COLS) - 1

    # 1. WRITE-SELECT — writing row k changes only row k
    w_mem = [0] * ROWS
    _, w_mem = golden_ref(w_mem, 1, 5, 0xABCD, 0)
    assert w_mem[5] == (0xABCD & full) and all(w_mem[r] == 0 for r in range(ROWS) if r != 5), \
        "write hit wrong/extra row"

    # 2. NO STRAY WRITE — w_en=0 changes nothing
    before = list(w_mem)
    _, w_mem = golden_ref(w_mem, 0, 9, 0xFFFF, 0)
    assert w_mem == before, "w_en=0 must not write"

    # 3. AND-AXIS — act_bp[r]=1 -> pp[r]=w_mem[r]; =0 -> pp[r]=0
    w_mem = [((r * 13 + 1) & full) for r in range(ROWS)]
    act = 0b101 & ((1 << ROWS) - 1)
    pp, _ = golden_ref(w_mem, 0, 0, 0, act)
    for r in range(ROWS):
        assert pp[r] == (w_mem[r] if (act >> r) & 1 else 0), f"AND axis wrong at row {r}"

    # 4. AND-AXIS is per-ROW not per-column — only row 3 active, all-ones rows
    w_mem = [full] * ROWS
    pp, _ = golden_ref(w_mem, 0, 0, 0, 1 << 3)
    assert pp[3] == full and all(pp[r] == 0 for r in range(ROWS) if r != 3), \
        "broadcast axis crossed (act must gate a ROW, not a column)"

    # 5. COLUMN MAPPING — write a sub-weight, read its DW columns back via pp
    w_mem = [0] * ROWS
    w0 = 0b10110001
    _, w_mem = golden_ref(w_mem, 1, 0, w0, 0)
    pp, _ = golden_ref(w_mem, 0, 0, 0, 1 << 0)
    assert (pp[0] & ((1 << DW) - 1)) == w0, f"column mapping: got {pp[0] & 0xFF:#x}, exp {w0:#x}"

    print("dcim_array golden_ref self-check passed")


golden_tb()