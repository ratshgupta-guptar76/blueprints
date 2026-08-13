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
# Jul-27-2026 | R. Gupta      | * v1.1   | Move Golden-Ref to cocotb/golden/dcim_array
# ======================================================================================

# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : dcim_array_tb.py
# Author    : R. Gupta
# Date      : Aug-13-2026
# --------------------------------------------------------------------------------------
# DUT       : dcim_array.sv  (4x sram_32x8_9T macro instances)
# Type      : Combinational boundary — level-sensitive write, combinational read
# Framework : cocotb / Verilator (Icarus for X-prop)
#
# DESCRIPTION
# ***********
#   Weight storage plus the AND multiply grid, now built from four sram_32x8_9T
#   macro instances (one per DW-wide weight) rather than behavioural flops. This
#   tb targets the ADDRESSING, the 4-macro SPLIT/REMAP, and the AND axis — not the
#   bitcell (that is SPICE: SNM / read-disturb / write margin).
#
# SPECIFICATION
# *************
#   Write (LEVEL-SENSITIVE / transparent latch — NOT edge-triggered):
#       w_en=1 => wl = one-hot(row_addr); macro writes mem[row_addr] <= w_buf
#                 CONTINUOUSLY while wl is asserted. w_buf changes propagate
#                 immediately. There is no clk on this module.
#       w_en=0 => wl = 0, no row written.
#   Read (combinational, ACTIVE-HIGH):
#       pp[r][c] = mem[r][c] AND act_bp[r]
#       act_bp[r] gates ALL columns of row r (per-ROW broadcast, not per-column).
#   Macro split / remap:
#       macro w takes WBL = w_buf[w*DW +: DW]; its RBL[r*DW + c] is remapped to
#       pp[r][w*DW + c]. So column c of pp holds bit (c%DW) of weight (c/DW),
#       the contract shared with weight_load + golden_model.
#   Storage powers up X (no reset). All rows must be written before any read.
#
# PARAMETERS
# **********
#   ROWS : array rows    (dcim_pkg::ROWS)
#   COLS : array columns (dcim_pkg::COLS)
#   DW   : bits per weight; columns per macro (dcim_pkg::DW)
#
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/row_decoder.sv, src/sram_32x8_9T.v, src/dcim_array.sv
#
# LIMITATIONS:
#   - Verifies addressing, macro split/remap, AND axis and column mapping. Does NOT
#     verify the bitcell (SPICE owns SNM / read-disturb / write margin). The two meet
#     at the ACTIVE-HIGH AND contract asserted here.
#   - WBLB is not modelled by the behavioural macro (differential drive is a SPICE
#     concern); a WBL/WBLB mismatch would be a driver bug and is not observable here.
#   - Write is transparent while wl is high: holding w_en with a changing w_buf
#     corrupts the row. The FSM owns that timing contract; test_write_through
#     documents the behaviour rather than forbidding it.
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Aug-13-2026 | R. Gupta      | * v2.0   | Rewritten for SRAM macro (was behavioural flops)
# ======================================================================================
 
import os
import random
 
import cocotb
from cocotb.triggers import Timer
 
import golden.dcim_array as ref
 
SETTLE = (1, "ns")
 
 
def _params(dut) -> tuple[int, int, int]:
    """Read params from the DUT and sync the golden reference."""
    rows = int(dut.ROWS.value)
    cols = int(dut.COLS.value)
    dw = cols // 4                      # 4 macros, DW columns each
    ref.ROWS, ref.COLS, ref.DW = rows, cols, dw
    ref.N_W = cols // dw
    ref.MASK = (1 << cols) - 1
    return rows, cols, dw
 
 
async def drive(dut, w_en, row_addr, w_buf, act_bp) -> list[int]:
    """Apply inputs, settle, return pp as a list of per-row ints."""
    dut.w_en.value = w_en
    dut.row_addr.value = row_addr
    dut.w_buf.value = w_buf
    dut.act_bp.value = act_bp
    await Timer(*SETTLE)
    raw = int(dut.pp.value)
    cols = int(dut.COLS.value)
    rows = int(dut.ROWS.value)
    mask = (1 << cols) - 1
    return [(raw >> (r * cols)) & mask for r in range(rows)]
 
 
async def write_row(dut, row, word) -> None:
    """Write one row, then drop w_en (transparent latch — must deassert)."""
    await drive(dut, 1, row, word, 0)
    await drive(dut, 0, 0, 0, 0)
 
 
async def write_all(dut, rows, word_fn) -> None:
    """Write every row. REQUIRED before any read: storage powers up X."""
    for r in range(rows):
        await write_row(dut, r, word_fn(r))
 
 
@cocotb.test()
async def test_write_select(dut) -> None:
    """Writing row k changes ONLY row k — catches decoder/macro address errors."""
    rows, cols, dw = _params(dut)
    mask = (1 << cols) - 1
 
    await write_all(dut, rows, lambda r: 0)          # initialise out of X
    for row in (0, 1, 5, rows // 2, rows - 1):
        await write_row(dut, row, mask)
        pp = await drive(dut, 0, 0, 0, (1 << rows) - 1)   # activate all rows
        assert pp[row] == mask, f"row {row} not written: {pp[row]:#x}"
        for r in range(rows):
            if r != row:
                assert pp[r] == 0, f"write to {row} leaked into row {r}: {pp[r]:#x}"
        await write_row(dut, row, 0)                 # restore
 
 
@cocotb.test()
async def test_no_stray_write(dut) -> None:
    """w_en=0 must write nothing, whatever row_addr/w_buf do."""
    rows, cols, dw = _params(dut)
    mask = (1 << cols) - 1
 
    await write_all(dut, rows, lambda r: 0)
    for row in range(rows):
        await drive(dut, 0, row, mask, 0)            # w_en LOW, w_buf all ones
    pp = await drive(dut, 0, 0, 0, (1 << rows) - 1)
    for r in range(rows):
        assert pp[r] == 0, f"stray write to row {r} with w_en=0: {pp[r]:#x}"
 
 
@cocotb.test()
async def test_and_axis_is_per_row(dut) -> None:
    """act_bp[r] gates ALL columns of row r — catches a transposed broadcast.
 
    All rows all-ones, activate exactly one row: only that pp row may be set.
    If the AND were column-gated this fails immediately.
    """
    rows, cols, dw = _params(dut)
    mask = (1 << cols) - 1
 
    await write_all(dut, rows, lambda r: mask)
    for row in (0, 3, rows // 2, rows - 1):
        pp = await drive(dut, 0, 0, 0, 1 << row)
        assert pp[row] == mask, f"row {row} active but pp={pp[row]:#x}"
        for r in range(rows):
            if r != row:
                assert pp[r] == 0, f"row {r} set while only {row} activated"
 
 
@cocotb.test()
async def test_and_axis_values(dut) -> None:
    """pp[r] == mem[r] & act_bp[r] for distinct per-row data and mixed planes."""
    rows, cols, dw = _params(dut)
    mask = (1 << cols) - 1
    data = [((r * 0x9E3779B1) & mask) for r in range(rows)]
 
    await write_all(dut, rows, lambda r: data[r])
    for act in (0, 1, (1 << rows) - 1, 0xA5A5A5A5 & ((1 << rows) - 1)):
        pp = await drive(dut, 0, 0, 0, act)
        for r in range(rows):
            exp = data[r] if (act >> r) & 1 else 0
            assert pp[r] == exp, \
                f"act={act:#x} row={r}: got {pp[r]:#x}, expected {exp:#x}"
 
 
@cocotb.test()
async def test_column_mapping(dut) -> None:
    """Each weight lands in its own DW-column group across the 4 macros.
 
    This is the macro-split test: a copy-paste error in the sram instantiations
    (macro 2 fed w_buf[23:16] but wired to rbl[1], etc.) shows up here and
    nowhere else. Four DISTINCT weights so a swap cannot alias.
    """
    rows, cols, dw = _params(dut)
    n_w = cols // dw
    weights = [0b10110001, 0b01001110, 0b11110000, 0b00001111][:n_w]
    word = sum(weights[w] << (w * dw) for w in range(n_w))
 
    await write_all(dut, rows, lambda r: 0)
    await write_row(dut, 0, word)
    pp = await drive(dut, 0, 0, 0, 1 << 0)
 
    for w in range(n_w):
        got = (pp[0] >> (w * dw)) & ((1 << dw) - 1)
        assert got == weights[w], \
            f"weight {w} in wrong column group: got {got:#010b}, expected {weights[w]:#010b}"
 
 
@cocotb.test()
async def test_active_high(dut) -> None:
    """pp is ACTIVE-HIGH: stored 1 AND active 1 -> 1. No inversion in RTL.
 
    The column inverter is added at the macro swap in layout, not here. If this
    ever fails, the RTL and the SPICE convention have diverged.
    """
    rows, cols, dw = _params(dut)
    mask = (1 << cols) - 1
 
    await write_all(dut, rows, lambda r: 0)
    pp = await drive(dut, 0, 0, 0, (1 << rows) - 1)
    assert all(p == 0 for p in pp), "stored 0 with act=1 must give pp=0 (inverted?)"
 
    await write_all(dut, rows, lambda r: mask)
    pp = await drive(dut, 0, 0, 0, (1 << rows) - 1)
    assert all(p == mask for p in pp), "stored 1 with act=1 must give pp=1"
 
 
@cocotb.test()
async def test_write_through(dut) -> None:
    """Transparent-latch behaviour: pp sees the value BEING written, same delta.
 
    The macro write is level-sensitive, so with w_en high and that row activated,
    pp reflects w_buf immediately — there is no clock edge separating write from
    read. This documents the behaviour the FSM must respect: w_buf has to be
    stable for the whole wl assertion or the row is corrupted.
    """
    rows, cols, dw = _params(dut)
    mask = (1 << cols) - 1
 
    await write_all(dut, rows, lambda r: 0)
    pp = await drive(dut, 1, 7, mask, 1 << 7)        # write and read row 7 together
    assert pp[7] == mask, f"transparent write not visible: {pp[7]:#x}"
 
    # and it tracks: change w_buf while wl is still asserted
    pp = await drive(dut, 1, 7, 0x0F0F0F0F & mask, 1 << 7)
    assert pp[7] == (0x0F0F0F0F & mask), \
        f"latch did not track changing w_buf: {pp[7]:#x}"
    await drive(dut, 0, 0, 0, 0)
 
 
@cocotb.test()
async def test_random(dut) -> None:
    """Random writes and activation planes vs the golden reference."""
    rows, cols, dw = _params(dut)
    mask = (1 << cols) - 1
    rng = random.Random(0xDC1A)
 
    mem = [0] * rows
    await write_all(dut, rows, lambda r: 0)
 
    for _ in range(200):
        row = rng.randrange(rows)
        word = rng.getrandbits(cols)
        act = rng.getrandbits(rows)
 
        await write_row(dut, row, word)
        mem[row] = word
 
        pp = await drive(dut, 0, 0, 0, act)
        exp, _ = ref.golden_ref(mem, 0, 0, 0, act)
        assert pp == exp, f"mismatch act={act:#x} after writing row {row}"
 
 
@cocotb.test(skip=(os.environ.get("SIM") != "icarus"))
async def test_x_prop_unwritten(dut) -> None:
    """4-state only: an unwritten row must NOT read as a clean 0.
 
    Verilator is 2-state and initialises memory to 0, which masks exactly the
    bug this catches: reading a row before it was written. Real SRAM powers up
    unpredictably, so a design that depends on unwritten content works on one
    die and fails on another.
    """
    rows = int(dut.ROWS.value)
 
    dut.w_en.value = 0
    dut.row_addr.value = 0
    dut.w_buf.value = 0
    dut.act_bp.value = (1 << rows) - 1              # activate everything
    await Timer(*SETTLE)
 
    assert not dut.pp.value.is_resolvable, \
        "unwritten storage resolved to a definite value — X was masked, " \
        "so a read-before-write bug would not be detectable"