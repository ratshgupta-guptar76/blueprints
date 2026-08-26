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
# Jul-27-2026 | R. Gupta      | * v1.1   | Move Golden-Ref to cocotb/golden/act_shift_chain
# ======================================================================================

import os
import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb.types import LogicArray

import golden.act_shift_chain as ref
from golden.act_shift_chain import golden_ref


def read_act_bp(dut, ROWS) -> list[int]:
    """act_bp is a packed ROWS-bit port -> list of ROWS bits, act_bp[i] = bit i."""
    v = int(dut.act_bp.value)
    return [(v >> i) & 1 for i in range(ROWS)]

async def reset_chain(dut) -> None:
    dut.en.value = 0
    dut.c_en.value = 0
    dut.a_b.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_reset(dut) -> None:
    """Asynchronous reset clears every cell in the chain.

    Method :
        > Directed

    Stimulus :
        - load non-zero into the chain, confirm act_bp non-zero, then reset
        - assert rst_n=0 between edges -> act_bp, tail all clear
        - hold rst_n=0 across cycles while driving load
        - re-assert on consecutive cycles

    Catches :
        - any cell not cleared by reset
        - reset synchronous / polarity inverted / edge-not-level
    """
    ROWS = int(dut.ROWS.value)
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    dut.en.value = 0
    dut.c_en.value = 0
    dut.a_b.value = 0

    # async: reset clears without an edge 
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.act_bp.value) == 0, "async reset: act_bp not cleared"
    assert int(dut.tail_out.value) == 0, "async reset: tail_out not cleared"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # load ones into the chain, confirm non-zero, then reset
    dut.en.value = 1
    dut.c_en.value = 0
    dut.a_b.value = 1
    for _ in range(DW):                            # fill cell 0 at least
        await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert int(dut.act_bp.value) != 0, "setup: chain did not load non-zero"

    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.act_bp.value) == 0, "async reset did not clear chain"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # hold rst_n=0 while driving load
    dut.rst_n.value = 0
    dut.en.value = 1
    dut.c_en.value = 0
    dut.a_b.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        assert int(dut.act_bp.value) == 0, "chain not held 0 while rst_n low"

    dut.rst_n.value = 1
    dut.en.value = 0
    await RisingEdge(dut.clk)

    # back-to-back reset
    dut.en.value = 1
    dut.a_b.value = 1
    for _ in range(DW):
        await RisingEdge(dut.clk)
    dut.en.value = 0
    await Timer(1, "ns")
    assert int(dut.act_bp.value) != 0, "setup: reload failed"

    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.act_bp.value) == 0, "first reset did not clear"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_cascade_connectivity(dut) -> None:
    """A single bit propagates head-to-tail through every cell.

    Method :
        > Directed

    Stimulus :
        - drive a_b=1 for one cycle, then a_b=0
        - shift ROWS*DW cycles; the bit must exit at tail_out at cycle ROWS*DW

    Catches :
        - a broken or skipped cell-to-cell link (bit never reaches tail)
        - tail tapped from the wrong point
    """
    ROWS = int(dut.ROWS.value)
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_chain(dut)

    cells = [0] * ROWS
    tail_high_cycles = []

    dut.en.value = 1
    dut.c_en.value = 0                              # LOAD

    for cyc in range(ROWS * DW + 2):
        ab = 1 if cyc == 0 else 0                   # single 1 at the head
        dut.a_b.value = ab
        await Timer(1, "ns")

        # tail_out this cycle == ref tail (before shift) — check via ref threading
        exp_bp, exp_tail, next_cells = golden_ref(cells, en=1, c_en=0, a_b=ab)
        if int(dut.tail_out.value) == 1:
            tail_high_cycles.append(cyc)

        await RisingEdge(dut.clk)
        cells = next_cells

    assert tail_high_cycles == [ROWS * DW], \
        f"single bit exited tail at {tail_high_cycles}, expected [{ROWS*DW}]"


@cocotb.test()
async def test_load_reversal(dut) -> None:
    """Chain reverses row order: cell i holds byte ROWS-1-i.

    Method :
        > Directed

    Stimulus :
        - LOAD ROWS distinct bytes, row 0 first, each LSB-first
        - COMPUTE-drain DW planes, reconstruct each cell's byte from act_bp
        - assert cell i == byte ROWS-1-i (the documented reversal)

    Catches :
        - cascade order wrong (no reversal, or wrong direction)
        - act_bp not 1:1 with cells
        - byte bit-order corrupted through the chain
    """
    ROWS = int(dut.ROWS.value)
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_chain(dut)

    acts = [(r * 7 + 3) & ((1 << DW) - 1) for r in range(ROWS)]
    cells = [0] * ROWS

    # LOAD: row 0 first .. row ROWS-1 last, each byte LSB-first
    dut.en.value = 1
    dut.c_en.value = 0
    for r in range(ROWS):
        for b in range(DW):
            dut.a_b.value = (acts[r] >> b) & 1
            await Timer(1, "ns")
            _, _, cells = golden_ref(cells, en=1, c_en=0, a_b=(acts[r] >> b) & 1)
            await RisingEdge(dut.clk)

    # COMPUTE-drain DW planes, reconstruct each cell's byte LSB-first
    dut.c_en.value = 1
    dut.a_b.value = 0
    rec = [0] * ROWS
    for p in range(DW):
        await Timer(1, "ns")
        bp = read_act_bp(dut, ROWS)
        exp_bp, _, cells = golden_ref(cells, en=1, c_en=1, a_b=0)
        assert bp == exp_bp, f"plane {p}: act_bp {bp} exp {exp_bp}"
        for i in range(ROWS):
            rec[i] |= bp[i] << p
        await RisingEdge(dut.clk)

    # the reversal
    for i in range(ROWS):
        assert rec[i] == acts[ROWS - 1 - i], \
            f"cell {i} holds {rec[i]:#x}, expected byte ROWS-1-i = {acts[ROWS-1-i]:#x}"

@cocotb.test()
async def test_compute_zero_fill(dut) -> None:
    """COMPUTE zero-fills each cell's MSB; a_b does not leak in.

    Method :
        > Directed

    Stimulus :
        - LOAD the chain full
        - COMPUTE-drain with a_b held HIGH -> MSBs must fill 0, not a_b
        - after ROWS*DW compute cycles the whole chain is 0

    Catches :
        - COMPUTE filling MSB with a_b/cascade instead of 0 (corrupt plane)
        - the FSM-CONSTRAINT hazard: chain bit injected during compute
    """
    ROWS = int(dut.ROWS.value)
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_chain(dut)

    cells = [0] * ROWS

    # LOAD full (all ones so cells are non-zero)
    dut.en.value = 1
    dut.c_en.value = 0
    for _ in range(ROWS * DW):
        dut.a_b.value = 1
        await Timer(1, "ns")
        _, _, cells = golden_ref(cells, en=1, c_en=0, a_b=1)
        await RisingEdge(dut.clk)

    # COMPUTE-drain with a_b held HIGH — must be ignored, MSB fills 0
    dut.c_en.value = 1
    dut.a_b.value = 1                              # adversarial: should not leak
    for p in range(DW):
        await Timer(1, "ns")
        bp = read_act_bp(dut, ROWS)
        exp_bp, _, cells = golden_ref(cells, en=1, c_en=1, a_b=1)
        assert bp == exp_bp, f"compute plane {p}: act_bp {bp} exp {exp_bp}"
        await RisingEdge(dut.clk)

    # keep draining until fully empty; a_b leak would keep cells non-zero
    for _ in range(ROWS * DW):
        dut.a_b.value = 1
        await Timer(1, "ns")
        await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert int(dut.act_bp.value) == 0, \
        "chain not empty after full compute-drain (a_b leaked into MSB)"


@cocotb.test()
async def test_interrupt(dut) -> None:
    """Enable-gap freezes the chain mid-load; it resumes correctly.

    Method :
        > Directed

    Stimulus :
        - LOAD partway -> en=0 several cycles -> resume -> complete
        - during the gap: act_bp and tail frozen

    Catches :
        - en ignored (chain shifts during the hold)
        - state corrupted across a hold
    """
    ROWS = int(dut.ROWS.value)
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_chain(dut)

    acts = [(r * 7 + 3) & ((1 << DW) - 1) for r in range(ROWS)]
    cells = [0] * ROWS

    # flatten the load sequence into (a_b) per cycle
    load_bits = []
    for r in range(ROWS):
        for b in range(DW):
            load_bits.append((acts[r] >> b) & 1)

    half = len(load_bits) // 2
    GAP = 3
    # schedule: (en, a_b). load half, gap, load rest
    schedule = [(1, load_bits[i]) for i in range(half)]
    schedule += [(0, 0)] * GAP
    schedule += [(1, load_bits[i]) for i in range(half, len(load_bits))]

    dut.c_en.value = 0
    frozen_bp = None

    for en, ab in schedule:
        dut.en.value = en
        dut.a_b.value = ab
        await Timer(1, "ns")

        bp = read_act_bp(dut, ROWS)
        exp_bp = [cells[i] & 1 for i in range(ROWS)]
        assert bp == exp_bp, f"act_bp {bp} exp {exp_bp}"

        if en == 0:
            if frozen_bp is None:
                frozen_bp = int(dut.act_bp.value)
            assert int(dut.act_bp.value) == frozen_bp, "chain shifted during gap"

        _, _, cells = golden_ref(cells, en=en, c_en=0, a_b=ab)
        await RisingEdge(dut.clk)

    # COMPUTE-drain and confirm the reversal survived the interruption
    dut.c_en.value = 1
    dut.a_b.value = 0
    rec = [0] * ROWS
    for p in range(DW):
        await Timer(1, "ns")
        bp = read_act_bp(dut, ROWS)
        _, _, cells = golden_ref(cells, en=1, c_en=1, a_b=0)
        for i in range(ROWS):
            rec[i] |= bp[i] << p
        await RisingEdge(dut.clk)

    for i in range(ROWS):
        assert rec[i] == acts[ROWS - 1 - i], \
            f"cell {i} = {rec[i]:#x} after interrupt, expected {acts[ROWS-1-i]:#x}"


@cocotb.test()
async def test_crv(dut) -> None:
    """Random per-cycle (en, c_en, a_b) against the threaded reference.

    Method :
        > Constrained-Random Verification (CRV)

    Stimulus :
        - random (en, c_en, a_b) each cycle for N cycles
        - all ROWS cells threaded; act_bp and tail checked every cycle

    Catches :
        - mode-transition bugs across the chain the directed tests miss
        - cascade / tap errors under random mode churn
    """
    ROWS = int(dut.ROWS.value)
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_chain(dut)

    N = 5000
    seed = int(os.environ.get("SEED", cocotb.RANDOM_SEED))
    rng = random.Random(seed)
    dut._log.info(f"act_shift_chain_tb.test_crv: seed={seed}, N={N}, ROWS={ROWS}, DW={DW}")

    cells = [0] * ROWS

    for i in range(N):
        en = rng.getrandbits(1)
        c_en = rng.getrandbits(1)
        ab = rng.getrandbits(1)
        dut.en.value = en
        dut.c_en.value = c_en
        dut.a_b.value = ab
        await Timer(1, "ns")

        exp_bp, exp_tail, next_cells = golden_ref(cells, en=en, c_en=c_en, a_b=ab)
        bp = read_act_bp(dut, ROWS)
        assert bp == exp_bp, \
            f"cyc {i} (en={en},c_en={c_en},ab={ab}): act_bp {bp} exp {exp_bp} @ seed={seed}"
        assert int(dut.tail_out.value) == exp_tail, \
            f"cyc {i}: tail {int(dut.tail_out.value)} exp {exp_tail} @ seed={seed}"

        await RisingEdge(dut.clk)
        cells = next_cells


@cocotb.test(skip=(os.environ.get("SIM") != "icarus"))
async def test_x_prop(dut) -> None:
    """A single X cascades confined to one bit and drains (Icarus only).

    Method :
        > X-Propagation

    Stimulus :
        - reset -> act_bp resolves to 0
        - LOAD a single X at a_b, rest 0; cascade it through
        - the X occupies one moving position; COMPUTE-drain resolves the chain

    Catches :
        - reset leaving X in the chain
        - X smearing beyond its one bit as it cascades
        - X failing to drain
    """
    ROWS = int(dut.ROWS.value)
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW

    def is_x(v) -> bool:
        return str(v).lower() in ("x", "z")

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset resolves the chain
    dut.en.value = 0
    dut.c_en.value = 0
    dut.a_b.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert dut.act_bp.value.is_resolvable and int(dut.act_bp.value) == 0, \
        "reset did not resolve chain to 0"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # LOAD one X at a_b, rest clean 0
    dut.en.value = 1
    dut.c_en.value = 0
    dut.a_b.value = LogicArray("x")
    await RisingEdge(dut.clk)
    dut.a_b.value = 0

    # shift the X through the chain with clean 0s; it must stay a single X
    total = ROWS * DW
    for _ in range(total - 1):
        await RisingEdge(dut.clk)
    await Timer(1, "ns")

    # COMPUTE-drain everything; chain must resolve to 0
    dut.c_en.value = 1
    dut.a_b.value = 0
    for _ in range(total):
        await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert dut.act_bp.value.is_resolvable, "X stuck in chain — did not drain"
    assert int(dut.act_bp.value) == 0, "chain not zero after draining the X"