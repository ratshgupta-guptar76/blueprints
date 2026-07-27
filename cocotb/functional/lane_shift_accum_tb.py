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
#   DW: data-width of activations (adopted from dcim_pkg::DW)
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

import os
import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb.types import LogicArray

import golden.lane_shift_accum as ref
from golden.lane_shift_accum import golden_ref


def to_signed(v: int, w: int) -> int:
    """TB-side: interpret raw w-bit DUT value as two's-complement signed.
    Deliberately independent of the reference's to_signed (both sides of the wall)."""
    v &= (1 << w) - 1
    return v - (1 << w) if v & (1 << (w - 1)) else v



def pack_col(cols: list[int], DW: int, YW: int) -> int:
    """Pack DW column-sums into one int at YW-bit stride for dut.col_adder."""
    v = 0
    for b in range(DW):
        v |= (cols[b] & ((1 << YW) - 1)) << (b * YW)
    return v


async def reset_dut(dut) -> None:
    dut.en.value = 0
    dut.clr.value = 0
    dut.bp_idx.value = 0
    dut.col_adder.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_combine(dut) -> None:
    """AXIS-1 signed weight combine: one accumulate reflects _combine(col_adder).

    Method :
        > Directed

    Stimulus :
        - clr, then one accumulate at bp_idx=0 for various col_adder patterns
        - includes weight 0xFF (all col_sums=1) -> lane_val = -1 (MSB-subtract)

    Catches :
        - MSB column not subtracted when W_SIGN (lane_val sign wrong)
        - wrong per-bit weighting (2^b)
        - signed result read/compared incorrectly
    """
    ROWS      = int(dut.ROWS.value)
    DW        = int(dut.DW.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    A_SIGN    = int(dut.A_SIGN.value)
    W_SIGN    = int(dut.W_SIGN.value)
    YW        = (ROWS).bit_length()

    # params for golden_ref
    ref.ROWS      = ROWS
    ref.DW        = DW
    ref.ACC_WIDTH = ACC_WIDTH
    ref.A_SIGN    = A_SIGN
    ref.W_SIGN    = W_SIGN

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # column-sum patterns to test the combine (each entry is DW col_sums, 0..ROWS)
    patterns = [
        [0] * DW,                                  # all zero -> 0
        [1] * DW,                                  # all ones -> W_SIGN: -1 (127-128)
        [ROWS] + [0] * (DW - 1),                   # only LSB col = ROWS
        [0] * (DW - 1) + [ROWS],                   # only MSB col = ROWS -> -ROWS*2^7 (W_SIGN)
        [ROWS] * (DW - 1) + [0],                   # max positive combine
        [ROWS] * DW,                               # all max -> depends on W_SIGN
        [(b * 7 + 3) % (ROWS + 1) for b in range(DW)],  # arbitrary mix
    ]

    for cols in patterns:
        await reset_dut(dut)

        # one accumulate at bp_idx=0: y should become _combine(cols) (sign-extended)
        dut.clr.value = 0
        dut.en.value = 1
        dut.bp_idx.value = 0
        dut.col_adder.value = pack_col(cols, DW, YW)
        await Timer(1, "ns")

        # thread the ref (y starts at 0 after reset)
        exp = golden_ref(0, clr=0, en=1, bp_idx=0, col_adder=cols)

        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        got = to_signed(int(dut.y.value), ACC_WIDTH)
        assert got == exp, f"cols={cols}: y={got} exp={exp} (W_SIGN={W_SIGN})"

@cocotb.test()
async def test_full_accumulate(dut) -> None:
    """Full bit-serial accumulate: y matches the per-cycle signed trace.

    Method :
        > Directed

    Stimulus :
        - clr, then DW planes (bp_idx 0..DW-1, LSB-first) of W x A
        - signed vectors incl. negative results (W=-128,A=255 -> -32640)
        - y checked EVERY cycle, not just final

    Catches :
        - wrong bit-plane shift (2^p weighting)
        - accumulate sign errors across planes
        - final-only correctness masking a mid-trace divergence
    """
    ROWS      = int(dut.ROWS.value)
    DW        = int(dut.DW.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    A_SIGN    = int(dut.A_SIGN.value)
    W_SIGN    = int(dut.W_SIGN.value)
    YW        = (ROWS).bit_length()

    # params for golden_ref
    ref.ROWS      = ROWS
    ref.DW        = DW
    ref.ACC_WIDTH = ACC_WIDTH
    ref.A_SIGN    = A_SIGN
    ref.W_SIGN    = W_SIGN

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # (W, A) vectors — W as signed 8-bit, A unsigned. Expected computed via ref.
    vectors = [(-1, 1), (127, 255), (-128, 255), (-128, 1), (-50, 200), (100, 100),
               (0, 255), (1, 1), (-1, 255)]

    for W, A in vectors:
        await reset_dut(dut)
        dut.clr.value = 0

        Wb = [(W >> b) & 1 for b in range(DW)]     # weight bits (two's-comp low DW bits)
        y_ref = 0

        for p in range(DW):                        # LSB-first activation planes
            ap = (A >> p) & 1
            cols = [Wb[b] & ap for b in range(DW)]  # 1-row lane: col_sum b = Wbit b AND act plane p

            dut.en.value = 1
            dut.bp_idx.value = p
            dut.col_adder.value = pack_col(cols, DW, YW)
            await Timer(1, "ns")

            y_ref = golden_ref(y_ref, clr=0, en=1, bp_idx=p, col_adder=cols)

            await RisingEdge(dut.clk)
            await Timer(1, "ns")
            got = to_signed(int(dut.y.value), ACC_WIDTH)
            assert got == y_ref, \
                f"W={W} A={A} plane {p}: y={got} exp={y_ref}"

        # final matches the known product (sanity against ref-independent truth)
        expected_product = to_signed(W & 0xFF, 8) * A
        assert to_signed(int(dut.y.value), ACC_WIDTH) == expected_product, \
            f"W={W} A={A}: final y={to_signed(int(dut.y.value), ACC_WIDTH)} != W*A={expected_product}"

@cocotb.test()
async def test_clr_priority(dut) -> None:
    """clr zeroes y and takes priority over en.

    Method :
        > Directed

    Stimulus :
        - accumulate to a known non-zero y
        - assert clr=1 with en=1 -> y goes to 0 (clr beats en)
        - continue with clr=1 held -> y stays 0 despite en/col_adder driven

    Catches :
        - clr not clearing y
        - en overriding clr (accumulate happening when it should reset)
    """
    ROWS      = int(dut.ROWS.value)
    DW        = int(dut.DW.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    A_SIGN    = int(dut.A_SIGN.value)
    W_SIGN    = int(dut.W_SIGN.value)
    YW        = (ROWS).bit_length()

    # params for golden_ref
    ref.ROWS      = ROWS
    ref.DW        = DW
    ref.ACC_WIDTH = ACC_WIDTH
    ref.A_SIGN    = A_SIGN
    ref.W_SIGN    = W_SIGN

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_dut(dut)

    # --- accumulate to a known non-zero y ---
    cols = [ROWS] * (DW - 1) + [0]                 # max-positive combine, non-zero
    dut.clr.value = 0
    dut.en.value = 1
    for p in range(3):
        dut.bp_idx.value = p
        dut.col_adder.value = pack_col(cols, DW, YW)
        await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert to_signed(int(dut.y.value), ACC_WIDTH) != 0, "setup: y did not accumulate non-zero"

    # --- clr=1 WITH en=1: clr must win, y -> 0 ---
    dut.clr.value = 1
    dut.en.value = 1                               # both high: clr has priority
    dut.bp_idx.value = 0
    dut.col_adder.value = pack_col(cols, DW, YW)
    await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert to_signed(int(dut.y.value), ACC_WIDTH) == 0, \
        "clr with en=1 did not zero y (en overrode clr)"

    # --- hold clr=1 while driving en/col_adder: y stays 0 ---
    for _ in range(3):
        dut.bp_idx.value = 1
        dut.col_adder.value = pack_col(cols, DW, YW)
        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        assert to_signed(int(dut.y.value), ACC_WIDTH) == 0, \
            "y not held 0 while clr asserted (en accumulating through clr)"

@cocotb.test()
async def test_reset(dut) -> None:
    """Asynchronous reset clears y to zero.

    Method :
        > Directed

    Stimulus :
        - accumulate non-zero y, confirm, then reset
        - assert rst_n=0 between edges -> y clears without an edge
        - hold rst_n=0 while driving accumulate
        - re-assert on consecutive cycles

    Catches :
        - y not cleared by reset
        - reset synchronous / polarity inverted / edge-not-level
    """
    ROWS      = int(dut.ROWS.value)
    DW        = int(dut.DW.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    A_SIGN    = int(dut.A_SIGN.value)
    W_SIGN    = int(dut.W_SIGN.value)
    YW        = (ROWS).bit_length()

    # params for golden_ref
    ref.ROWS      = ROWS
    ref.DW        = DW
    ref.ACC_WIDTH = ACC_WIDTH
    ref.A_SIGN    = A_SIGN
    ref.W_SIGN    = W_SIGN

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    dut.en.value = 0; dut.clr.value = 0; dut.bp_idx.value = 0; dut.col_adder.value = 0

    # async: reset clears without an edge
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert to_signed(int(dut.y.value), ACC_WIDTH) == 0, "async reset: y not cleared"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # accumulate non-zero, confirm, then reset
    cols = [ROWS] * (DW - 1) + [0]
    dut.en.value = 1
    for p in range(3):
        dut.bp_idx.value = p
        dut.col_adder.value = pack_col(cols, DW, YW)
        await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert to_signed(int(dut.y.value), ACC_WIDTH) != 0, "setup: y not accumulated"

    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert to_signed(int(dut.y.value), ACC_WIDTH) == 0, "async reset did not clear y"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # hold rst_n=0 while driving accumulate
    dut.rst_n.value = 0
    dut.en.value = 1
    for _ in range(3):
        dut.bp_idx.value = 0
        dut.col_adder.value = pack_col(cols, DW, YW)
        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        assert to_signed(int(dut.y.value), ACC_WIDTH) == 0, "y not held 0 while rst_n low"

    dut.rst_n.value = 1
    dut.en.value = 0
    await RisingEdge(dut.clk)

    # back-to-back reset
    dut.en.value = 1
    for p in range(3):
        dut.bp_idx.value = p
        dut.col_adder.value = pack_col(cols, DW, YW)
        await RisingEdge(dut.clk)
    dut.en.value = 0
    await Timer(1, "ns")
    assert to_signed(int(dut.y.value), ACC_WIDTH) != 0, "setup: reload failed"

    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert to_signed(int(dut.y.value), ACC_WIDTH) == 0, "first reset did not clear"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_interrupt(dut) -> None:
    """Enable-gap holds the accumulator; it resumes correctly.

    Method :
        > Directed

    Stimulus :
        - accumulate partway -> en=0 several cycles -> resume -> complete
        - during the gap: y frozen

    Catches :
        - en ignored (y accumulates during the hold)
        - state corrupted across a hold
    """
    ROWS      = int(dut.ROWS.value)
    DW        = int(dut.DW.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    A_SIGN    = int(dut.A_SIGN.value)
    W_SIGN    = int(dut.W_SIGN.value)
    YW        = (ROWS).bit_length()

    # params for golden_ref
    ref.ROWS      = ROWS
    ref.DW        = DW
    ref.ACC_WIDTH = ACC_WIDTH
    ref.A_SIGN    = A_SIGN
    ref.W_SIGN    = W_SIGN

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_dut(dut)

    W, A = -50, 200
    Wb = [(W >> b) & 1 for b in range(DW)]
    y_ref = 0
    dut.clr.value = 0

    half = DW // 2
    # schedule: (en, plane) — accumulate half, gap, resume
    steps = [(1, p) for p in range(half)] + [(0, 0)] * 3 + [(1, p) for p in range(half, DW)]
    frozen_y = None

    for en, p in steps:
        ap = (A >> p) & 1
        cols = [Wb[b] & ap for b in range(DW)]
        dut.en.value = en
        dut.bp_idx.value = p
        dut.col_adder.value = pack_col(cols, DW, YW)
        await Timer(1, "ns")

        assert to_signed(int(dut.y.value), ACC_WIDTH) == y_ref, \
            f"y {to_signed(int(dut.y.value), ACC_WIDTH)} exp {y_ref}"

        if en == 0:
            if frozen_y is None:
                frozen_y = to_signed(int(dut.y.value), ACC_WIDTH)
            assert to_signed(int(dut.y.value), ACC_WIDTH) == frozen_y, "y moved during gap"

        y_ref = golden_ref(y_ref, clr=0, en=en, bp_idx=p, col_adder=cols)
        await RisingEdge(dut.clk)

    await Timer(1, "ns")
    assert to_signed(int(dut.y.value), ACC_WIDTH) == to_signed(W & 0xFF, 8) * A, \
        f"final y wrong after interrupt: {to_signed(int(dut.y.value), ACC_WIDTH)} != {to_signed(W&0xFF,8)*A}"


@cocotb.test()
async def test_crv(dut) -> None:
    """Random per-cycle (clr, en, bp_idx, col_adder) against the threaded reference.

    Method :
        > Constrained-Random Verification (CRV)

    Stimulus :
        - random clr, en, bp_idx, and col_adder each cycle for N cycles
        - y threaded and checked every cycle (signed)

    Catches :
        - accumulate / clr / hold transition bugs the directed tests miss
        - signed overflow / wrap errors under random accumulation
    """
    ROWS      = int(dut.ROWS.value)
    DW        = int(dut.DW.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    A_SIGN    = int(dut.A_SIGN.value)
    W_SIGN    = int(dut.W_SIGN.value)
    YW        = (ROWS).bit_length()

    # params for golden_ref
    ref.ROWS      = ROWS
    ref.DW        = DW
    ref.ACC_WIDTH = ACC_WIDTH
    ref.A_SIGN    = A_SIGN
    ref.W_SIGN    = W_SIGN

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_dut(dut)

    N = 10000
    seed = int(os.environ.get("SEED", cocotb.RANDOM_SEED))
    rng = random.Random(seed)
    dut._log.info(f"lane_shift_accum_tb.test_crv: seed={seed}, N={N}, ACC_WIDTH={ACC_WIDTH}")

    y_ref = 0
    for i in range(N):
        clr = rng.getrandbits(1)
        en = rng.getrandbits(1)
        bp_idx = rng.randrange(DW)
        cols = [rng.randrange(ROWS + 1) for _ in range(DW)]   # full range 0..ROWS

        dut.clr.value = clr
        dut.en.value = en
        dut.bp_idx.value = bp_idx
        dut.col_adder.value = pack_col(cols, DW, YW)
        await Timer(1, "ns")

        assert to_signed(int(dut.y.value), ACC_WIDTH) == y_ref, \
            f"cyc {i} (clr={clr},en={en},bp={bp_idx}): y={to_signed(int(dut.y.value), ACC_WIDTH)} exp={y_ref} @ seed={seed}"

        y_ref = golden_ref(y_ref, clr=clr, en=en, bp_idx=bp_idx, col_adder=cols)
        await RisingEdge(dut.clk)


@cocotb.test(skip=(os.environ.get("SIM") != "icarus"))
async def test_x_prop(dut) -> None:
    """Reset resolves y; X in col_adder does not corrupt a cleared accumulator (Icarus only).

    Method :
        > X-Propagation

    Stimulus :
        - reset -> y resolves to 0
        - drive X in col_adder with en=0 -> y (held) stays resolved
        - clr with X in col_adder -> y resolves to 0 (clr dominates X input)

    Catches :
        - reset leaving y unresolved
        - X in the data input corrupting a held or cleared accumulator
    """
    ROWS      = int(dut.ROWS.value)
    DW        = int(dut.DW.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    A_SIGN    = int(dut.A_SIGN.value)
    W_SIGN    = int(dut.W_SIGN.value)
    YW        = (ROWS).bit_length()

    # params for golden_ref
    ref.ROWS      = ROWS
    ref.DW        = DW
    ref.ACC_WIDTH = ACC_WIDTH
    ref.A_SIGN    = A_SIGN
    ref.W_SIGN    = W_SIGN

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset resolves y
    dut.en.value = 0; dut.clr.value = 0; dut.bp_idx.value = 0; dut.col_adder.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert dut.y.value.is_resolvable and to_signed(int(dut.y.value), ACC_WIDTH) == 0, \
        "reset did not resolve y to 0"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # X in col_adder with en=0: y held, must stay resolved (X input ignored)
    dut.en.value = 0
    dut.col_adder.value = LogicArray("x" * (DW * YW))
    await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert dut.y.value.is_resolvable, "X in col_adder corrupted a held y (en=0)"

    # clr with X in col_adder: clr dominates, y -> 0 resolved
    dut.clr.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert dut.y.value.is_resolvable and to_signed(int(dut.y.value), ACC_WIDTH) == 0, \
        "clr did not resolve y to 0 despite X input"
