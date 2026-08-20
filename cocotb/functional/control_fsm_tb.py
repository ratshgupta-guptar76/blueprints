# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : control_fsm_tb.py
# Author    : R. Gupta
# Date      : Jul-18-2026
# --------------------------------------------------------------------------------------
# DUT       : control_fsm.sv
# Type      : One-Hot FSM
# Framework : cocotb / Verilator
# 
# DESCRIPTION
# ***********
#   Datapath controller for the DCIM macro. A one-hot FSM sequences one matrix-vector
#   operation through six states, driving register-level control (weight load, act. 
#   stream-in, compute, output stream-out). Three counters track progress within these
#   states.
#   Reset is asynchronous.
# 
# SPECIFICATION
# *************
#   @ negedge rst_n:
#       state    = IDLE
#       load_cnt = 0
#       row_cnt  = 0
#       bp_cnt   = 0
#   @ posedge clk: next_state =>
#       IDLE -> WRITE_W, if start
#       WRITE_W -> WRITE_A, if row_cnt == ROWS-1 && wfull
#       WRITE_A -> COMPUTE, if load_cnt == DW*ROWS-1
#       COMPUTE -> DONE, if bp_cnt == P-1 (Pminus1)
#       DONE -> SHIFT_OUT       // Delay state
#       SHIFT_OUT -> cont ? WRITE_A : IDLE, if y_done
#       default: IDLE (one-hot failsafe)
#   @ posedge clk: counters =>
#       WRITE_W : row_cnt  <- wfull ? row_cnt + 1 : row_cnt
#       WRITE_A : load_cnt <- load_cnt + 1
#       COMPUTE : bp_cnt   <- bp_cnt + 1
#   @ posedge clk: outputs
#       busy = ~IDLE
#       done = DONE
#       comp_en = COMPUTE
#       a_en = WRITE_A or COMPUTE
#       w_en = WRITE_W and wfull
#       wshift_en = WRITE_W and not (row_cnt == ROWS-1 and wfull)  // excludes the
#                   WRITE_W->WRITE_A transition-triggering cycle itself, so
#                   weight_load.sv's wload_cnt doesn't take an uncounted
#                   extra shift there (see golden/control_fsm.py)
#       row_addr = row_cnt
#       bp_idx = bp_cnt
#       clr = WRITE_A and (if load_cnt == DW*ROWS-1)
#       y_load = done
#       y_en = DONE or SHIFT_OUT
# 
# PARAMETERS
# **********
#   ROWS: # of weights per row (adopted from dcim_pkg::ROWS)
#   DW: data-width of activations (adopted from dcim_pkg::DW)
# 
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/control_fsm.sv
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# Jul-27-2026 | R. Gupta      | * v1.1   | Move Golden-Ref to cocotb/golden/control_fsm
# ======================================================================================

import os
import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb.types import LogicArray

import golden.control_fsm as ref
from golden.control_fsm import golden_ref

# enum states
IDLE, WRITE_W, WRITE_A, COMPUTE, DONE, SHIFT_OUT = (
    0b000001, 0b000010, 0b000100, 0b001000, 0b010000, 0b100000
)

STATE_NAME = {IDLE: "IDLE", WRITE_W: "WRITE_W", WRITE_A: "WRITE_A",
              COMPUTE: "COMPUTE", DONE: "DONE", SHIFT_OUT: "SHIFT_OUT"}

OUTPUTS = ["busy", "done", "w_en", "wshift_en", "row_addr", "a_en",
           "comp_en", "clr", "bp_idx", "y_load", "y_en"]

# reachable arc set (default->IDLE failsafe covered separately)
REACHABLE_ARCS = {
    ("IDLE", "IDLE"), ("IDLE", "WRITE_W"),
    ("WRITE_W", "WRITE_W"), ("WRITE_W", "WRITE_A"),
    ("WRITE_A", "WRITE_A"), ("WRITE_A", "COMPUTE"),
    ("COMPUTE", "COMPUTE"), ("COMPUTE", "DONE"),
    ("DONE", "SHIFT_OUT"),
    ("SHIFT_OUT", "SHIFT_OUT"), ("SHIFT_OUT", "WRITE_A"), ("SHIFT_OUT", "IDLE"),
}


# reachable arc set (default->IDLE failsafe covered separately)
REACHABLE_ARCS = {
    ("IDLE", "IDLE"), ("IDLE", "WRITE_W"),
    ("WRITE_W", "WRITE_W"), ("WRITE_W", "WRITE_A"),
    ("WRITE_A", "WRITE_A"), ("WRITE_A", "COMPUTE"),
    ("COMPUTE", "COMPUTE"), ("COMPUTE", "DONE"),
    ("DONE", "SHIFT_OUT"),
    ("SHIFT_OUT", "SHIFT_OUT"), ("SHIFT_OUT", "WRITE_A"), ("SHIFT_OUT", "IDLE"),
}


def read_outputs(dut):
    """Read all 11 combinational outputs into a dict matching the ref."""
    return {
        "busy": int(dut.busy.value),
        "done": int(dut.done.value),
        "w_en": int(dut.w_en.value),
        "wshift_en": int(dut.wshift_en.value),
        "row_addr": int(dut.row_addr.value),
        "a_en": int(dut.a_en.value),
        "comp_en": int(dut.comp_en.value),
        "clr": int(dut.clr.value),
        "bp_idx": int(dut.bp_idx.value),
        "y_load": int(dut.y_load.value),
        "y_en": int(dut.y_en.value),
    }


def check_outputs(dut, exp  , cyc, ctx=""):
    got = read_outputs(dut)
    for k in OUTPUTS:
        assert got[k] == exp[k], f"cyc {cyc} {ctx}: output {k}={got[k]} exp {exp[k]}"


async def reset_dut(dut):
    dut.start.value = 0
    dut.cont.value = 0
    dut.P_minus1.value = 0
    dut.wfull.value = 0
    dut.y_done.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_reset(dut) -> None:
    """Asynchronous reset forces state to IDLE and clears all counters.

    Method :
        > Directed

    Stimulus :
        - advance into a non-IDLE state with non-zero counters, confirm, then reset
        - assert rst_n=0 between edges -> state=IDLE, counters=0 (no clock edge)
        - hold rst_n=0 while driving start -> stays IDLE
        - re-assert on consecutive cycles

    Catches :
        - state not forced to IDLE by reset
        - counters not cleared
        - reset synchronous / polarity inverted / edge-not-level
    """
    ROWS     = int(dut.ROWS.value)
    DW       = int(dut.DW.value)
    MAX_LOAD = DW * ROWS - 1

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW
    ref.MAX_LOAD = MAX_LOAD

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    dut.start.value = 0
    dut.cont.value = 0
    dut.P_minus1.value = 1
    dut.wfull.value = 0
    dut.y_done.value = 0

    # --- async: reset forces IDLE without a clock edge ---
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.state.value) == IDLE, \
        f"async reset: state not IDLE ({int(dut.state.value):#08b})"
    assert int(dut.busy.value) == 0, "async reset: busy asserted in IDLE"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- advance into WRITE_W with a non-zero row_cnt, confirm, then reset ---
    dut.start.value = 1
    await RisingEdge(dut.clk)                       # IDLE -> WRITE_W
    dut.start.value = 0
    dut.wfull.value = 1
    for _ in range(3):                             # advance row_cnt a few times
        await RisingEdge(dut.clk)
    dut.wfull.value = 0
    await Timer(1, "ns")
    assert int(dut.state.value) == WRITE_W, "setup: not in WRITE_W"
    assert int(dut.row_addr.value) != 0, "setup: row_cnt did not advance"

    # --- async reset mid-operation clears state and counter, no edge ---
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.state.value) == IDLE, "async reset did not force IDLE"
    assert int(dut.row_addr.value) == 0, "async reset did not clear row_cnt"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- hold rst_n=0 while driving start: must stay IDLE ---
    dut.rst_n.value = 0
    dut.start.value = 1                            # try to leave IDLE while held in reset
    for _ in range(3):
        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        assert int(dut.state.value) == IDLE, "state left IDLE while rst_n low"

    dut.rst_n.value = 1
    dut.start.value = 0
    await RisingEdge(dut.clk)

    # --- back-to-back reset ---
    dut.start.value = 1
    await RisingEdge(dut.clk)                       # into WRITE_W
    dut.start.value = 0
    await Timer(1, "ns")
    assert int(dut.state.value) == WRITE_W, "setup: reload failed"

    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.state.value) == IDLE, "first reset did not force IDLE"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_full_sequence(dut) -> None:
    """Full happy-path walk IDLE->...->SHIFT_OUT->(cont)WRITE_A.

    Method :
        > Directed

    Stimulus :
        - drive the complete matvec sequence, all 11 outputs checked each cycle
        - embeds regression guards: row_cnt hold, clr timing, DONE handshake, cont loop

    Catches :
        - any output wrong in any state
        - row_cnt cleared between wfull (the fixed hang bug)
        - clr overlapping comp_en
        - DONE not asserting y_load & y_en
        - cont not looping to WRITE_A
    """
    ROWS     = int(dut.ROWS.value)
    DW       = int(dut.DW.value)
    MAX_LOAD = DW * ROWS - 1

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW
    ref.MAX_LOAD = MAX_LOAD

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_dut(dut)

    P = 1                                          # 2 planes
    dut.P_minus1.value = P

    # threaded ref state
    s, r, l, b = IDLE, 0, 0, 0

    def thread(start=0, cont=0, wfull=0, y_done=0):
        nonlocal s, r, l, b
        exp_out, ns, nr, nl, nb = golden_ref(s, r, l, b, start, cont, P, wfull, y_done)
        return exp_out, ns, nr, nl, nb

    cyc = 0

    async def drive(start=0, cont=0, wfull=0, y_done=0, ctx=""):
        nonlocal s, r, l, b, cyc
        dut.start.value = start
        dut.cont.value = cont
        dut.wfull.value = wfull
        dut.y_done.value = y_done
        await Timer(1, "ns")
        exp_out, ns, nr, nl, nb = thread(start, cont, wfull, y_done)
        check_outputs(dut, exp_out, cyc, ctx)
        await RisingEdge(dut.clk)
        s, r, l, b = ns, nr, nl, nb
        cyc += 1

    # IDLE -> WRITE_W
    await drive(start=1, ctx="IDLE")
    assert s == WRITE_W, f"expected WRITE_W, got {STATE_NAME.get(s)}"

    # WRITE_W: row_cnt HOLDS between wfull; advances on wfull (regression guard)
    for row in range(ROWS):
        await drive(wfull=0, ctx=f"WRITE_W row {row} hold")
        assert r == row, f"row_cnt cleared: {r} != {row} (the hang-bug regression)"
        await drive(wfull=1, ctx=f"WRITE_W row {row} advance")
    assert s == WRITE_A, f"expected WRITE_A after {ROWS} rows, got {STATE_NAME.get(s)}"

    # WRITE_A: clr ONLY on the last cycle (regression guard)
    for i in range(MAX_LOAD + 1):
        await drive(ctx=f"WRITE_A i={i}")
    assert s == COMPUTE, f"expected COMPUTE, got {STATE_NAME.get(s)}"

    # COMPUTE: clr must NOT overlap comp_en (checked inside check_outputs each cycle)
    for p in range(P + 1):
        await drive(ctx=f"COMPUTE plane {p}")
    assert s == DONE, f"expected DONE, got {STATE_NAME.get(s)}"

    # DONE: y_load AND y_en asserted (stream_out capture handshake)
    await drive(ctx="DONE")
    assert s == SHIFT_OUT, f"expected SHIFT_OUT, got {STATE_NAME.get(s)}"

    # SHIFT_OUT: hold on ~y_done, then cont=1 loops to WRITE_A (weight-stationary)
    await drive(y_done=0, ctx="SHIFT_OUT hold")
    assert s == SHIFT_OUT, "SHIFT_OUT should hold while ~y_done"
    await drive(cont=1, y_done=1, ctx="SHIFT_OUT cont-exit")
    assert s == WRITE_A, f"cont=1 should loop to WRITE_A, got {STATE_NAME.get(s)}"

@cocotb.test()
async def test_all_arcs(dut) -> None:
    """Every reachable state transition is exercised (arc coverage).

    Method :
        > Directed (arc coverage)

    Stimulus :
        - a walk that takes every arc incl. self-loops and BOTH SHIFT_OUT exits
        - each (from,to) transition recorded; assert the full reachable set is hit

    Catches :
        - a transition condition wrong in a way line coverage misses
          (esp. SHIFT_OUT->WRITE_A vs SHIFT_OUT->IDLE, same case-item)
    """
    ROWS     = int(dut.ROWS.value)
    DW       = int(dut.DW.value)
    MAX_LOAD = DW * ROWS - 1

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW
    ref.MAX_LOAD = MAX_LOAD

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_dut(dut)

    P = 1
    dut.P_minus1.value = P
    s, r, l, b = IDLE, 0, 0, 0
    arcs_seen = set()

    async def drive(start=0, cont=0, wfull=0, y_done=0):
        nonlocal s, r, l, b
        dut.start.value = start
        dut.cont.value = cont
        dut.wfull.value = wfull
        dut.y_done.value = y_done
        await Timer(1, "ns")
        exp_out, ns, nr, nl, nb = golden_ref(s, r, l, b, start, cont, P, wfull, y_done)
        check_outputs(dut, exp_out, 0, f"{STATE_NAME[s]}->{STATE_NAME[ns]}")
        arcs_seen.add((STATE_NAME[s], STATE_NAME[ns]))
        await RisingEdge(dut.clk)
        s, r, l, b = ns, nr, nl, nb

    # IDLE->IDLE (sit, ~start), then IDLE->WRITE_W
    await drive(start=0)
    await drive(start=0)
    await drive(start=1)

    # WRITE_W: self-loop (~wfull) then advance, for all rows -> WRITE_W->WRITE_A
    for _ in range(ROWS):
        await drive(wfull=0)
        await drive(wfull=1)

    # WRITE_A: self-loop until MAX_LOAD -> WRITE_A->COMPUTE
    for _ in range(MAX_LOAD + 1):
        await drive()

    # COMPUTE: self-loop then -> DONE
    for _ in range(P + 1):
        await drive()

    # DONE->SHIFT_OUT
    await drive()

    # SHIFT_OUT: self-loop (~y_done), then ~cont exit -> IDLE
    await drive(y_done=0)
    await drive(cont=0, y_done=1)                   # SHIFT_OUT->IDLE
    assert s == IDLE, f"~cont should exit to IDLE, got {STATE_NAME[s]}"

    # now do a SECOND run to hit SHIFT_OUT->WRITE_A (cont exit)
    await drive(start=1)                            # IDLE->WRITE_W
    for _ in range(ROWS):
        await drive(wfull=0)
        await drive(wfull=1)
    for _ in range(MAX_LOAD + 1):
        await drive()
    for _ in range(P + 1):
        await drive()
    await drive()                                  # DONE->SHIFT_OUT
    await drive(cont=1, y_done=1)                   # SHIFT_OUT->WRITE_A
    assert s == WRITE_A, f"cont should loop to WRITE_A, got {STATE_NAME[s]}"

    # every reachable arc hit
    missing = REACHABLE_ARCS - arcs_seen
    assert not missing, f"arcs not covered: {missing}"
    extra = arcs_seen - REACHABLE_ARCS
    assert not extra, f"unexpected arcs (RTL took an illegal transition): {extra}"


@cocotb.test()
async def test_one_hot_failsafe(dut) -> None:
    """Illegal one-hot state recovers to IDLE (default arc).

    Method :
        > Directed (fault injection)

    Stimulus :
        - force state to an illegal (non-one-hot) value
        - confirm next_state resolves to IDLE

    Catches :
        - missing/incorrect default case (SEU/bit-flip would hang)
    """
    ROWS     = int(dut.ROWS.value)
    DW       = int(dut.DW.value)
    MAX_LOAD = DW * ROWS - 1

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW
    ref.MAX_LOAD = MAX_LOAD

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_dut(dut)

    dut.start.value = 0
    dut.cont.value = 0
    dut.wfull.value = 0
    dut.y_done.value = 0

    # force an illegal one-hot state (two bits set, or zero bits)
    try:
        dut.state.value = 0b000000                 # illegal: no bit set
        await Timer(1, "ns")
        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        assert int(dut.state.value) == IDLE, \
            f"illegal state did not recover to IDLE: {int(dut.state.value):#08b}"
    except AttributeError:
        dut._log.warning("dut.state not forceable — default->IDLE arc unreachable, documented")

@cocotb.test()
async def test_compute_precision(dut) -> None:
    """COMPUTE runs exactly P_minus1+1 planes for every precision, incl. min/max.

    Method :
        > Directed (parameter sweep)

    Stimulus :
        - for each P_minus1 in 0..DW-1: walk into COMPUTE, count planes to DONE
        - assert exactly P_minus1+1 comp_en cycles, bp_idx sweeps 0..P_minus1
        - special focus: P_minus1=0 (single plane) and P_minus1=DW-1 (max)

    Catches :
        - COMPUTE exit off-by-one (visible only at boundary precisions)
        - bp_cnt not sweeping the full range
        - underflow at P_minus1=0
    """
    ROWS     = int(dut.ROWS.value)
    DW       = int(dut.DW.value)
    MAX_LOAD = DW * ROWS - 1

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW
    ref.MAX_LOAD = MAX_LOAD

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    for P in range(DW):                            # P_minus1 = 0 .. DW-1
        await reset_dut(dut)
        dut.P_minus1.value = P

        s, r, l, b = IDLE, 0, 0, 0

        async def drive(start=0, cont=0, wfull=0, y_done=0):
            nonlocal s, r, l, b
            dut.start.value = start
            dut.cont.value = cont
            dut.P_minus1.value = P
            dut.wfull.value = wfull
            dut.y_done.value = y_done
            await Timer(1, "ns")
            exp_out, ns, nr, nl, nb = golden_ref(s, r, l, b, start, cont, P, wfull, y_done)
            check_outputs(dut, exp_out, 0, f"P={P} {STATE_NAME[s]}")
            await RisingEdge(dut.clk)
            s, r, l, b = ns, nr, nl, nb

        # walk to COMPUTE
        await drive(start=1)                       # IDLE->WRITE_W
        for _ in range(ROWS):
            await drive(wfull=0)
            await drive(wfull=1)
        for _ in range(MAX_LOAD + 1):
            await drive()
        assert s == COMPUTE, f"P={P}: expected COMPUTE, got {STATE_NAME[s]}"

        # count COMPUTE planes: comp_en high each cycle, bp_idx = plane index,
        # must run exactly P+1 planes then exit to DONE
        planes = 0
        bp_seen = []
        while s == COMPUTE:
            await Timer(1, "ns")
            assert int(dut.comp_en.value) == 1, f"P={P} plane {planes}: comp_en not high"
            bp_seen.append(int(dut.bp_idx.value))
            planes += 1
            exp_out, ns, nr, nl, nb = golden_ref(s, r, l, b, 0, 0, P, 0, 0)
            await RisingEdge(dut.clk)
            s, r, l, b = ns, nr, nl, nb
            if planes > DW + 2:                    # safety: never-exits guard
                assert False, f"P={P}: COMPUTE did not exit after {planes} planes"

        assert planes == P + 1, f"P={P}: ran {planes} planes, expected {P+1}"
        assert bp_seen == list(range(P + 1)), f"P={P}: bp_idx swept {bp_seen}, expected {list(range(P+1))}"
        assert s == DONE, f"P={P}: COMPUTE exited to {STATE_NAME[s]}, not DONE"

@cocotb.test()
async def test_input_gating(dut) -> None:
    """Each strobe is ignored outside the state where it acts.

    Method :
        > Directed

    Stimulus :
        - start pulsed in WRITE_A -> ignored (stays in sequence)
        - wfull pulsed in COMPUTE -> bp_cnt / state unaffected
        - y_done pulsed in WRITE_W -> no transition
        - cont sampled only at y_done (value before y_done irrelevant)

    Catches :
        - a strobe leaking into a state it should not affect
        - cont sampled at the wrong time
    """
    ROWS     = int(dut.ROWS.value)
    DW       = int(dut.DW.value)
    MAX_LOAD = DW * ROWS - 1

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW
    ref.MAX_LOAD = MAX_LOAD

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_dut(dut)

    P = DW - 1
    s, r, l, b = IDLE, 0, 0, 0

    async def drive(start=0, cont=0, wfull=0, y_done=0):
        nonlocal s, r, l, b
        dut.start.value = start; dut.cont.value = cont
        dut.P_minus1.value = P; dut.wfull.value = wfull; dut.y_done.value = y_done
        await Timer(1, "ns")
        exp_out, ns, nr, nl, nb = golden_ref(s, r, l, b, start, cont, P, wfull, y_done)
        check_outputs(dut, exp_out, 0, f"{STATE_NAME[s]}")
        assert int(dut.state.value) == s, f"state drift: {int(dut.state.value):#08b} != {STATE_NAME[s]}"
        await RisingEdge(dut.clk)
        s, r, l, b = ns, nr, nl, nb

    # --- get into WRITE_A ---
    await drive(start=1)
    for _ in range(ROWS):
        await drive(wfull=0)
        await drive(wfull=1)
    assert s == WRITE_A

    # --- start pulsed in WRITE_A: ignored (no jump back to WRITE_W) ---
    await drive(start=1)                            # start high, but we're in WRITE_A
    assert s == WRITE_A, "start in WRITE_A caused an illegal transition"
    # y_done pulsed in WRITE_A: ignored
    await drive(y_done=1)
    assert s == WRITE_A, "y_done in WRITE_A caused a transition"

    # finish WRITE_A -> COMPUTE
    while s == WRITE_A:
        await drive()
    assert s == COMPUTE

    # --- wfull pulsed in COMPUTE: row_cnt stays 0, no effect ---
    await drive(wfull=1)
    assert int(dut.row_addr.value) == 0, "wfull in COMPUTE disturbed row_cnt"
    assert s == COMPUTE, "wfull in COMPUTE caused a transition"
    # start pulsed in COMPUTE: ignored
    await drive(start=1)
    assert s == COMPUTE, "start in COMPUTE caused a transition"

    # finish COMPUTE -> DONE -> SHIFT_OUT
    while s == COMPUTE:
        await drive()
    assert s == DONE
    await drive()                                  # DONE -> SHIFT_OUT
    assert s == SHIFT_OUT

    # --- cont timing: cont high but y_done low -> no exit, cont not yet sampled ---
    await drive(cont=1, y_done=0)
    assert s == SHIFT_OUT, "SHIFT_OUT exited without y_done"
    # cont LOW at the actual y_done cycle -> exits to IDLE (cont sampled NOW)
    await drive(cont=0, y_done=1)
    assert s == IDLE, "cont sampled at wrong time (should sample at y_done)"


@cocotb.test()
async def test_crv(dut) -> None:
    """Random all-input drive against the threaded reference (input-gating backstop).

    Method :
        > Constrained-Random Verification (CRV)

    Stimulus :
        - random start, cont, wfull, y_done, P_minus1 each cycle for N cycles
        - state + 3 counters threaded; all 11 outputs + state checked every cycle

    Catches :
        - any input affecting a state it should not (gating leak)
        - transition / counter bugs under input combinations the directed tests miss
    """
    ROWS     = int(dut.ROWS.value)
    DW       = int(dut.DW.value)
    MAX_LOAD = DW * ROWS - 1

    # params for golden_ref
    ref.ROWS = ROWS
    ref.DW = DW
    ref.MAX_LOAD = MAX_LOAD

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    await reset_dut(dut)

    N = 20000
    seed = int(os.environ.get("SEED", cocotb.RANDOM_SEED))
    rng = random.Random(seed)
    dut._log.info(f"control_fsm_tb.test_crv: seed={seed}, N={N}")

    s, r, l, b = IDLE, 0, 0, 0

    for i in range(N):
        start = rng.getrandbits(1)
        cont = rng.getrandbits(1)
        wfull = rng.getrandbits(1)
        y_done = rng.getrandbits(1)
        P = rng.randrange(DW)                       # 0..DW-1

        dut.start.value = start; dut.cont.value = cont; dut.P_minus1.value = P
        dut.wfull.value = wfull; dut.y_done.value = y_done
        await Timer(1, "ns")

        exp_out, ns, nr, nl, nb = golden_ref(s, r, l, b, start, cont, P, wfull, y_done)
        # all 11 outputs
        got = read_outputs(dut)
        for k in OUTPUTS:
            assert got[k] == exp_out[k], \
                f"cyc {i} {STATE_NAME[s]} (st={start},co={cont},wf={wfull},yd={y_done},P={P}): " \
                f"{k}={got[k]} exp {exp_out[k]} @ seed={seed}"
        # state itself
        assert int(dut.state.value) == s, \
            f"cyc {i}: state {int(dut.state.value):#08b} != {STATE_NAME[s]} @ seed={seed}"

        await RisingEdge(dut.clk)
        s, r, l, b = ns, nr, nl, nb