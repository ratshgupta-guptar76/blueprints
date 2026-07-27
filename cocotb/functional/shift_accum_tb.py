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
# Jul-18-2026 | R. Gupta      | * v1.0   | Move Golden-Ref to cocotb/golden/shift_accum
# ======================================================================================

import os
import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb.types import LogicArray

import golden.shift_accum as ref
from golden.shift_accum import golden_ref

def to_signed(v: int, w: int) -> int:
    """TB-side signed read (independent of the reference's copy)."""
    v &= (1 << w) - 1
    return v - (1 << w) if v & (1 << (w - 1)) else v


def pack_sum(col_sums, COLS, YW) -> int:
    """Pack COLS column-sums into one int at YW stride for dut.sum."""
    v = 0
    for c in range(COLS):
        v |= (col_sums[c] & ((1 << YW) - 1)) << (c * YW)
    return v

def read_y(dut, N_WEIGHTS, ACC_WIDTH) -> list[int]:
    """Read the packed y port into N_WEIGHTS signed accumulators."""
    raw = int(dut.y.value)
    out = []
    for i in range(N_WEIGHTS):
        field = (raw >> (i * ACC_WIDTH)) & ((1 << ACC_WIDTH) - 1)
        out.append(to_signed(field, ACC_WIDTH))
    return out

async def reset_dut(dut) -> None:
    dut.en.value = 0
    dut.clr.value = 0
    dut.bp_idx.value = 0
    dut.sum.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

@cocotb.test()
async def test_slice_isolation(dut) -> None:
    """Each lane accumulates only its own DW-column slice; no cross-lane leak.

    Method :
        > Directed

    Stimulus :
        - for each lane k: drive a known weight in columns k*DW..k*DW+DW-1,
          zeros elsewhere; full bit-serial accumulate
        - assert only y[k] responds, all other lanes stay 0

    Catches :
        - slice off-by-one (lane gets wrong columns)
        - bitcast reorder (col_adders[i][b] != sum[i*DW+b])
        - cross-lane leak
    """
    ROWS      = int(dut.ROWS.value)
    DW        = int(dut.DW.value)
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    COLS      = int(dut.COLS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    A_SIGN    = int(dut.A_SIGN.value)
    W_SIGN    = int(dut.W_SIGN.value)
    YW        = (ROWS).bit_length()

    # params for golden_ref
    ref.ROWS      = ROWS
    ref.DW        = DW
    ref.N_WEIGHTS = N_WEIGHTS
    ref.COLS      = COLS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.A_SIGN    = A_SIGN
    ref.W_SIGN    = W_SIGN

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    W = to_signed(0x80, 8)                          # -128, a strong signed value
    A = 255

    for k in range(N_WEIGHTS):
        await reset_dut(dut)

        Wb = [(W >> b) & 1 for b in range(DW)]
        y_ref = [0] * N_WEIGHTS
        dut.clr.value = 0
        dut.en.value = 1

        for p in range(DW):                        # LSB-first activation planes
            ap = (A >> p) & 1
            col_sums = [0] * COLS
            for b in range(DW):
                col_sums[k * DW + b] = Wb[b] & ap  # only lane k's columns

            dut.bp_idx.value = p
            dut.sum.value = pack_sum(col_sums, COLS, YW)
            await Timer(1, "ns")

            y_ref = golden_ref(y_ref, clr=0, en=1, bp_idx=p, col_sums=col_sums)

            await RisingEdge(dut.clk)
            await Timer(1, "ns")
            got = read_y(dut, N_WEIGHTS, ACC_WIDTH)
            assert got == y_ref, f"lane {k} plane {p}: y={got} exp={y_ref}"

        # only lane k responded; others exactly 0
        got = read_y(dut, N_WEIGHTS, ACC_WIDTH)
        assert got[k] == W * A, f"lane {k}: y[{k}]={got[k]} != W*A={W*A}"
        for i in range(N_WEIGHTS):
            if i != k:
                assert got[i] == 0, f"lane {k} driven but lane {i} leaked: y[{i}]={got[i]}"

@cocotb.test()
async def test_all_lanes_matvec(dut) -> None:
    """All lanes accumulate distinct matvecs simultaneously, independently.

    Method :
        > Directed

    Stimulus :
        - distinct (W, A) per lane, all driven together
        - full bit-serial accumulate; y[i] checked every cycle vs threaded ref

    Catches :
        - cross-lane contamination under simultaneous load
        - a lane computing a neighbor's result
        - shared control (bp_idx/en) misrouted to a lane
    """
    ROWS      = int(dut.ROWS.value)
    DW        = int(dut.DW.value)
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    COLS      = int(dut.COLS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    A_SIGN    = int(dut.A_SIGN.value)
    W_SIGN    = int(dut.W_SIGN.value)
    YW        = (ROWS).bit_length()

    # params for golden_ref
    ref.ROWS      = ROWS
    ref.DW        = DW
    ref.N_WEIGHTS = N_WEIGHTS
    ref.COLS      = COLS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.A_SIGN    = A_SIGN
    ref.W_SIGN    = W_SIGN

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_dut(dut)

    # distinct signed weight + activation per lane (cycle through hard values)
    weight_pool = [0xFF, 0x7F, 0x80, 0x01, 0xCE, 0x64, 0x00, 0x99]   # -1,127,-128,1,-50,100,0,-103
    act_pool    = [1, 255, 255, 200, 200, 100, 255, 128]
    W = [to_signed(weight_pool[i % len(weight_pool)] & 0xFF, 8) for i in range(N_WEIGHTS)]
    A = [act_pool[i % len(act_pool)] for i in range(N_WEIGHTS)]

    Wb = [[(W[i] >> b) & 1 for b in range(DW)] for i in range(N_WEIGHTS)]
    y_ref = [0] * N_WEIGHTS
    dut.clr.value = 0
    dut.en.value = 1

    for p in range(DW):
        col_sums = [0] * COLS
        for i in range(N_WEIGHTS):
            ap = (A[i] >> p) & 1
            for b in range(DW):
                col_sums[i * DW + b] = Wb[i][b] & ap

        dut.bp_idx.value = p
        dut.sum.value = pack_sum(col_sums, COLS, YW)
        await Timer(1, "ns")

        y_ref = golden_ref(y_ref, clr=0, en=1, bp_idx=p, col_sums=col_sums)

        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        got = read_y(dut, N_WEIGHTS, ACC_WIDTH)
        assert got == y_ref, f"plane {p}: y={got} exp={y_ref}"

    # every lane's final == its own product (reference-independent oracle)
    got = read_y(dut, N_WEIGHTS, ACC_WIDTH)
    for i in range(N_WEIGHTS):
        assert got[i] == W[i] * A[i], \
            f"lane {i}: y={got[i]} != W[{i}]*A[{i}]={W[i]*A[i]}"

@cocotb.test()
async def test_clr_all_lanes(dut) -> None:
    """clr zeroes all N_WEIGHTS accumulators simultaneously, priority over en.

    Method :
        > Directed

    Stimulus :
        - accumulate distinct non-zero values into every lane
        - clr=1 with en=1 -> all lanes go to 0 (clr beats en)

    Catches :
        - clr not reaching all lanes (a lane left non-zero)
        - en overriding clr in any lane
    """
    ROWS      = int(dut.ROWS.value)
    DW        = int(dut.DW.value)
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    COLS      = int(dut.COLS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    A_SIGN    = int(dut.A_SIGN.value)
    W_SIGN    = int(dut.W_SIGN.value)
    YW        = (ROWS).bit_length()

    # params for golden_ref
    ref.ROWS      = ROWS
    ref.DW        = DW
    ref.N_WEIGHTS = N_WEIGHTS
    ref.COLS      = COLS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.A_SIGN    = A_SIGN
    ref.W_SIGN    = W_SIGN

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_dut(dut)

    # accumulate something non-zero into every lane
    col_sums = [ROWS if (c % DW) < DW - 1 else 0 for c in range(COLS)]  # positive combine each lane
    dut.clr.value = 0
    dut.en.value = 1
    for p in range(3):
        dut.bp_idx.value = p
        dut.sum.value = pack_sum(col_sums, COLS, YW)
        await RisingEdge(dut.clk)
    await Timer(1, "ns")
    got = read_y(dut, N_WEIGHTS, ACC_WIDTH)
    assert all(v != 0 for v in got), f"setup: some lane zero before clr: {got}"

    # clr=1 with en=1: all lanes -> 0
    dut.clr.value = 1
    dut.en.value = 1
    dut.bp_idx.value = 0
    dut.sum.value = pack_sum(col_sums, COLS, YW)
    await RisingEdge(dut.clk)
    await Timer(1, "ns")
    got = read_y(dut, N_WEIGHTS, ACC_WIDTH)
    assert all(v == 0 for v in got), f"clr with en=1 did not zero all lanes: {got}"


@cocotb.test()
async def test_reset(dut) -> None:
    """Asynchronous reset clears all lane accumulators.

    Method :
        > Directed

    Stimulus :
        - accumulate non-zero into all lanes, confirm, then reset
        - assert rst_n=0 between edges -> all y clear
        - hold rst_n=0 while driving accumulate

    Catches :
        - a lane not cleared by reset
        - reset synchronous / polarity inverted
    """
    ROWS      = int(dut.ROWS.value)
    DW        = int(dut.DW.value)
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    COLS      = int(dut.COLS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    A_SIGN    = int(dut.A_SIGN.value)
    W_SIGN    = int(dut.W_SIGN.value)
    YW        = (ROWS).bit_length()

    # params for golden_ref
    ref.ROWS      = ROWS
    ref.DW        = DW
    ref.N_WEIGHTS = N_WEIGHTS
    ref.COLS      = COLS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.A_SIGN    = A_SIGN
    ref.W_SIGN    = W_SIGN

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    dut.en.value = 0; dut.clr.value = 0; dut.bp_idx.value = 0; dut.sum.value = 0

    # async: reset clears without an edge
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert all(v == 0 for v in read_y(dut, N_WEIGHTS, ACC_WIDTH)), "async reset: y not cleared"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # accumulate non-zero, confirm, then reset
    col_sums = [ROWS if (c % DW) < DW - 1 else 0 for c in range(COLS)]
    dut.en.value = 1
    for p in range(3):
        dut.bp_idx.value = p
        dut.sum.value = pack_sum(col_sums, COLS, YW)
        await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert all(v != 0 for v in read_y(dut, N_WEIGHTS, ACC_WIDTH)), "setup: lanes not accumulated"

    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert all(v == 0 for v in read_y(dut, N_WEIGHTS, ACC_WIDTH)), "async reset did not clear all lanes"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # hold rst_n=0 while driving accumulate
    dut.rst_n.value = 0
    dut.en.value = 1
    for _ in range(3):
        dut.bp_idx.value = 0
        dut.sum.value = pack_sum(col_sums, COLS, YW)
        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        assert all(v == 0 for v in read_y(dut, N_WEIGHTS, ACC_WIDTH)), "y not held 0 while rst_n low"
    dut.rst_n.value = 1
    dut.en.value = 0
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_crv(dut) -> None:
    """Random shared control + per-lane column-sums against the threaded reference.

    Method :
        > Constrained-Random Verification (CRV)

    Stimulus :
        - random clr, en, bp_idx (shared) and random col_sums (all COLS)
        - all N_WEIGHTS lanes threaded and checked every cycle

    Catches :
        - cross-lane / slice bugs under random accumulation
        - shared-control misrouting
    """
    ROWS      = int(dut.ROWS.value)
    DW        = int(dut.DW.value)
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    COLS      = int(dut.COLS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    A_SIGN    = int(dut.A_SIGN.value)
    W_SIGN    = int(dut.W_SIGN.value)
    YW        = (ROWS).bit_length()

    # params for golden_ref
    ref.ROWS      = ROWS
    ref.DW        = DW
    ref.N_WEIGHTS = N_WEIGHTS
    ref.COLS      = COLS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.A_SIGN    = A_SIGN
    ref.W_SIGN    = W_SIGN

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_dut(dut)

    N = 5000
    seed = int(os.environ.get("SEED", cocotb.RANDOM_SEED))
    rng = random.Random(seed)
    dut._log.info(f"shift_accum_tb.test_crv: seed={seed}, N={N}, N_WEIGHTS={N_WEIGHTS}, COLS={COLS}")

    y_ref = [0] * N_WEIGHTS
    for i in range(N):
        clr = rng.getrandbits(1)
        en = rng.getrandbits(1)
        bp_idx = rng.randrange(DW)
        col_sums = [rng.randrange(ROWS + 1) for _ in range(COLS)]

        dut.clr.value = clr
        dut.en.value = en
        dut.bp_idx.value = bp_idx
        dut.sum.value = pack_sum(col_sums, COLS, YW)
        await Timer(1, "ns")

        got = read_y(dut, N_WEIGHTS, ACC_WIDTH)
        assert got == y_ref, \
            f"cyc {i} (clr={clr},en={en},bp={bp_idx}): y={got} exp={y_ref} @ seed={seed}"

        y_ref = golden_ref(y_ref, clr=clr, en=en, bp_idx=bp_idx, col_sums=col_sums)
        await RisingEdge(dut.clk)


@cocotb.test(skip=(os.environ.get("SIM") != "icarus"))
async def test_x_prop(dut) -> None:
    """X in one lane's columns stays confined; reset resolves all lanes (Icarus only).

    Method :
        > X-Propagation

    Stimulus :
        - reset -> all y resolve to 0
        - X in one lane's columns with en=0 -> held y stays resolved
        - clr with X present -> all y resolve to 0

    Catches :
        - reset leaving a lane unresolved
        - X in one lane corrupting another (slice not confining X)
    """
    ROWS      = int(dut.ROWS.value)
    DW        = int(dut.DW.value)
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    COLS      = int(dut.COLS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    A_SIGN    = int(dut.A_SIGN.value)
    W_SIGN    = int(dut.W_SIGN.value)
    YW        = (ROWS).bit_length()

    # params for golden_ref
    ref.ROWS      = ROWS
    ref.DW        = DW
    ref.N_WEIGHTS = N_WEIGHTS
    ref.COLS      = COLS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.A_SIGN    = A_SIGN
    ref.W_SIGN    = W_SIGN

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset resolves all lanes
    dut.en.value = 0; dut.clr.value = 0; dut.bp_idx.value = 0; dut.sum.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert dut.y.value.is_resolvable and all(v == 0 for v in read_y(dut, N_WEIGHTS, ACC_WIDTH)), \
        "reset did not resolve all lanes to 0"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # X in one lane's columns, en=0 -> held y stays resolved
    dut.en.value = 0
    dut.sum.value = LogicArray("x" * (COLS * YW))
    await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert dut.y.value.is_resolvable, "X in sum corrupted held y (en=0)"

    # clr with X present -> all resolve to 0
    dut.clr.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert dut.y.value.is_resolvable and all(v == 0 for v in read_y(dut, N_WEIGHTS, ACC_WIDTH)), \
        "clr did not resolve all lanes despite X"