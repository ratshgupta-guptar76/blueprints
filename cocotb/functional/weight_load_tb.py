# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : weight_load_tb.py
# Author    : R. Gupta
# Date      : Jul-19-2026
# --------------------------------------------------------------------------------------
# DUT       : weight_load.sv
# Type      : Sequential, SIPO, async reset
# Latency   : wfull asserts 1 cycle after w_buf is full (final w_bit is registered) 
# Framework : cocotb / Verilator
# 
# DESCRIPTION
# ***********
#   Serial-in Parallel-out shift register and weight-row assembler. Shifts COLS serial
#   w_bit(s) into a parallel w_buf - buffer register. w_bit enters the MSB, shifting
#   towards the LSB. It pulses w_full for exactly one cycle when a full row is
#   assembled. wfull is registered and asserts the cycle AFTER the final bit lands,
#   coincident with a fully-valid w_buf. Forced low whenever en is low.
#   Reset is asynchronous.
# 
# SPECIFICATION
# *************
#   @ negedge rst_n
#       w_buf     = '0
#       wload_cnt = '0
#       wfull     =  0
#   @ posedge clk && en == 1:
#       w_buf     <- {w_bit, w_buf[COLS-1:1]}                   (MSB fill, LSB shift)
#       wload_cnt <- (wload_cnt == COLS-1) ? 0 : wload_cnt + 1
#       wfull     <- (wload_cnt == COLS-1) ? 1 : 0              (registered)
#   @ posedge clk && en == 0:
#       w_buf     <- w_buf
#       wload_cnt <- wload_cnt
#       wfull     <- 0
#   Output (comb.)  => w_buf outputs are connected parallely
#   Ordering: w_bit shifts into MSB and towards the LSB.
# 
# PARAMETERS
# **********
#   COLS: # of weight-bits a.k.a. depth of weight_load (adopted from dcim_pkg::COLS)
# 
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/weight_load.sv
# 
# LIMITATIONS:  en held high for full row (FSM: wshift_en = WRITE_W).
#               Mid-row de-assertion unreachable; not exercised.
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# Jul-18-2026 | R. Gupta      | * v1.0   | Move Golden-Ref to cocotb/golden/weight_load
# ======================================================================================

import os
import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb.types import LogicArray

import golden.weight_load as ref
from golden.weight_load import golden_ref

@cocotb.test()
async def weight_load_tb(dut):
    """Asynchronous reset clears all three registers to zero.

    Method :
        > Directed

    Stimulus :
        - load a non-zero partial row, confirm state, then reset
        - assert rst_n=0 between clock edges -> w_buf, wload_cnt, wfull clear
        - drop rst_n mid-load
        - hold rst_n=0 across several cycles
        - re-assert rst_n on consecutive cycles (back-to-back reset)

    Catches :
        - any of the three registers not cleared by reset
        - reset made synchronous (would require a clock edge)
        - reset polarity inverted
        - reset edge-triggered instead of level
    """
    COLS = int(dut.COLS.value)

    # params for golden_ref
    ref.COLS = COLS

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # idle
    dut.en.value = 0
    dut.w_bit.value = 0

    # --- async: rst_n=0 clears outputs WITHOUT a clock edge ---
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.w_buf.value) == 0, "async reset: w_buf not cleared"
    assert int(dut.wfull.value) == 0, "async reset: wfull not cleared"
    assert int(dut.wload_cnt.value) == 0, "async reset: wload_cnt not cleared"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- load a KNOWN non-zero partial row, confirm, THEN reset ---
    dut.en.value = 1
    dut.w_bit.value = 1
    for _ in range(3):                             # 3 of COLS bits -> partial, non-zero
        await RisingEdge(dut.clk)
    dut.en.value = 0
    await Timer(1, "ns")
    assert int(dut.w_buf.value) != 0, "setup: partial load left w_buf empty"
    assert int(dut.wload_cnt.value) != 0, "setup: counter did not advance"

    # --- async reset clears the loaded state, no edge ---
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.w_buf.value) == 0, "async reset did not clear w_buf"
    assert int(dut.wload_cnt.value) == 0, "async reset did not clear wload_cnt"
    assert int(dut.wfull.value) == 0, "async reset did not clear wfull"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- mid-load: reset while a row is partially assembled ---
    dut.en.value = 1
    dut.w_bit.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert int(dut.w_buf.value) != 0, "setup: mid-load empty"

    dut.rst_n.value = 0
    await Timer(1, "ns")                           # no edge, mid-operation
    assert int(dut.w_buf.value) == 0, "async reset mid-load did not clear w_buf"
    assert int(dut.wload_cnt.value) == 0, "async reset mid-load did not clear counter"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- hold rst_n=0 across several cycles while driving load ---
    dut.rst_n.value = 0
    dut.en.value = 1
    dut.w_bit.value = 1                            # try to load while held in reset
    for _ in range(3):
        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        assert int(dut.w_buf.value) == 0, "w_buf not held 0 while rst_n low"
        assert int(dut.wload_cnt.value) == 0, "counter not held 0 while rst_n low"
        assert int(dut.wfull.value) == 0, "wfull not held 0 while rst_n low"

    dut.rst_n.value = 1
    dut.en.value = 0
    await RisingEdge(dut.clk)

    # --- back-to-back reset: re-assert on consecutive cycles ---
    dut.en.value = 1
    dut.w_bit.value = 1
    for _ in range(3):                            # reload non-zero
        await RisingEdge(dut.clk)
    dut.en.value = 0
    await Timer(1, "ns")
    assert int(dut.w_buf.value) != 0, "setup: reload failed"

    dut.rst_n.value = 0                           # first assertion
    await Timer(1, "ns")
    assert int(dut.w_buf.value) == 0, "first reset did not clear"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    dut.en.value = 1
    for _ in range(3):                            # reload between resets
        await RisingEdge(dut.clk)
    dut.en.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 0                           # second, back-to-back
    await Timer(1, "ns")
    assert int(dut.w_buf.value) == 0, "re-asserted reset did not clear"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

@cocotb.test()
async def test_load_full_row(dut) -> None:
    """Assemble a full weight row; wfull pulses once, coincident with complete w_buf.

    Method :
        > Directed

    Stimulus :
        - stream COLS w_bit with en=1 (one full row)
        - one extra cycle to observe the registered wfull pulse
        - check w_buf, wfull (registered, one-cycle lag), and their coincidence

    Catches :
        - wfull mistimed vs complete w_buf (one cycle early/late)
        - wrong shift direction / column mapping
        - w_buf assembled incorrectly
    """
    COLS = int(dut.COLS.value)

    # params for golden_ref
    ref.COLS = COLS

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset
    dut.en.value = 0
    dut.w_bit.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # deterministic row pattern (asymmetric so direction matters)
    row_bits = [(i * 3 + 1) & 1 for i in range(COLS)]

    w_buf = 0
    cnt = 0
    prev_next_wfull = 0                             # DUT.wfull after reset = 0
    wfull_count = 0

    dut.en.value = 1

    # stream COLS bits, then ONE extra cycle to see wfull pulse
    for i in range(COLS + 1):
        b = row_bits[i] if i < COLS else 0          # extra cycle: w_bit don't-care
        dut.w_bit.value = b

        await Timer(1, "ns")                        # settle

        # DUT.w_buf this cycle == ref's w_buf_out (current buffer)
        assert int(dut.w_buf.value) == w_buf, \
            f"cyc {i}: w_buf {int(dut.w_buf.value):#0{COLS+2}b} exp {w_buf:#0{COLS+2}b}"
        # DUT.wfull this cycle == PREVIOUS call's next_wfull (registered lag)
        assert int(dut.wfull.value) == prev_next_wfull, \
            f"cyc {i}: wfull {int(dut.wfull.value)} exp {prev_next_wfull}"

        # coincidence: when wfull high, w_buf must be the complete row
        if int(dut.wfull.value) == 1:
            wfull_count += 1
            expect_full = 0
            for bit in row_bits:
                expect_full = (bit << (COLS - 1)) | (expect_full >> 1)
            expect_full &= (1 << COLS) - 1
            assert int(dut.w_buf.value) == expect_full, \
                f"cyc {i}: wfull high but w_buf incomplete: {int(dut.w_buf.value):#0{COLS+2}b} exp {expect_full:#0{COLS+2}b}"

        w_buf_out, next_wfull, next_cnt, next_wbuf = golden_ref(w_buf, en=1, wload_cnt=cnt, w_bit=b)
        await RisingEdge(dut.clk)
        prev_next_wfull = next_wfull
        w_buf, cnt = next_wbuf, next_cnt

        assert wfull_count <= 1, f"wfull asserted more than once: {wfull_count} times"

@cocotb.test()
async def test_wfull_single_pulse(dut) -> None:
    """wfull pulses exactly one cycle per row across back-to-back rows.

    Method :
        > Directed

    Stimulus :
        - stream ROWS_N full rows continuously (en=1, no gaps)
        - track wfull every cycle

    Catches :
        - wfull held multiple cycles (FSM double-counts row_cnt)
        - wfull skips a row (row committed without a pulse)
        - wfull mistimed against row completion across boundaries
    """
    COLS = int(dut.COLS.value)

    # params for golden_ref
    ref.COLS = COLS

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset
    dut.en.value = 0
    dut.w_bit.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    ROWS_N = 3
    total_cycles = ROWS_N * COLS + 1               # +1 to catch the final pulse

    w_buf = 0
    cnt = 0
    prev_next_wfull = 0
    dut.en.value = 1

    wfull_high_cycles = []                          # cycle indices where wfull==1
    prev_wfull = 0

    for i in range(total_cycles):
        b = (i * 3 + 1) & 1                         # arbitrary continuous stream
        dut.w_bit.value = b
        await Timer(1, "ns")

        cur_wfull = int(dut.wfull.value)
        assert cur_wfull == prev_next_wfull, f"cyc {i}: wfull {cur_wfull} exp {prev_next_wfull}"

        # no two consecutive highs -> never held
        assert not (cur_wfull == 1 and prev_wfull == 1), \
            f"cyc {i}: wfull held two consecutive cycles (FSM would double-count)"

        if cur_wfull == 1:
            wfull_high_cycles.append(i)

        _, next_wfull, next_cnt, next_wbuf = golden_ref(w_buf, en=1, wload_cnt=cnt, w_bit=b)
        await RisingEdge(dut.clk)
        prev_wfull = cur_wfull
        prev_next_wfull = next_wfull
        w_buf, cnt = next_wbuf, next_cnt

    # exactly ROWS_N pulses, evenly spaced COLS apart
    assert len(wfull_high_cycles) == ROWS_N, \
        f"expected {ROWS_N} pulses, got {len(wfull_high_cycles)} at {wfull_high_cycles}"
    gaps = [wfull_high_cycles[k+1] - wfull_high_cycles[k] for k in range(len(wfull_high_cycles)-1)]
    assert all(g == COLS for g in gaps), f"pulses not COLS apart: {wfull_high_cycles}"

@cocotb.test()
async def test_en_gates_wfull(dut) -> None:
    """en=0 suppresses wfull even when the counter is at the trigger value.

    Method :
        > Directed

    Stimulus :
        - stream COLS-1 bits (counter sits at COLS-1, primed to pulse)
        - drop en=0 on the cycle wfull would fire -> must stay low
        - hold en=0 several cycles -> wfull stays low, counter frozen
        - re-enable -> the primed pulse now fires

    Catches :
        - missing '~en -> wfull<=0' guard (stale pulse into non-WRITE_W state)
        - counter advancing while disabled
    """
    COLS = int(dut.COLS.value)

    # params for golden_ref
    ref.COLS = COLS

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset
    dut.en.value = 0
    dut.w_bit.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- prime the counter to COLS-1 by streaming COLS-1 bits ---
    dut.en.value = 1
    dut.w_bit.value = 1
    for _ in range(COLS - 1):
        await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert int(dut.wload_cnt.value) == COLS - 1, \
        f"setup: counter at {int(dut.wload_cnt.value)}, expected {COLS-1}"
    assert int(dut.wfull.value) == 0, "setup: wfull already high before trigger cycle"

    # --- drop en on the cycle wfull WOULD pulse; guard must hold it low ---
    dut.en.value = 0
    for c in range(3):                              # hold disabled several cycles
        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        assert int(dut.wfull.value) == 0, \
            f"en=0 cyc {c}: wfull pulsed while disabled (missing ~en guard)"
        assert int(dut.wload_cnt.value) == COLS - 1, \
            f"en=0 cyc {c}: counter advanced while disabled ({int(dut.wload_cnt.value)})"

    # --- re-enable: the primed pulse must now fire (proves priming was real) ---
    dut.en.value = 1
    dut.w_bit.value = 1
    await Timer(1, "ns")
    # this cycle: en=1, cnt still COLS-1 -> next_wfull=1 -> wfull high NEXT cycle
    await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert int(dut.wfull.value) == 1, \
        "re-enabled: primed pulse did not fire (counter was not genuinely at COLS-1)"

@cocotb.test()
async def test_interrupt(dut) -> None:
    """Enable-gap freezes the assembler; the row completes with one delayed pulse.

    Method :
        > Directed

    Stimulus :
        - stream a partial row -> en=0 several cycles -> resume -> complete
        - during the gap: w_buf, counter frozen; wfull stays low
        - after resume: exactly one wfull pulse, coincident with complete w_buf

    Catches :
        - en ignored (state advances during the gap)
        - wfull spuriously pulsing while disabled
        - row corrupted or pulse lost across the interruption
    """
    COLS = int(dut.COLS.value)

    # params for golden_ref
    ref.COLS = COLS

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset
    dut.en.value = 0
    dut.w_bit.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    row_bits = [(i * 3 + 1) & 1 for i in range(COLS)]
    half = COLS // 2
    GAP = 3

    # build a per-cycle schedule: (en, w_bit)
    schedule = [(1, row_bits[i]) for i in range(half)]        # load first half
    schedule += [(0, 0)] * GAP                                # en=0 gap
    schedule += [(1, row_bits[i]) for i in range(half, COLS)] # resume rest
    schedule += [(1, 0)]                                      # extra cycle to see pulse

    w_buf = 0
    cnt = 0
    prev_next_wfull = 0
    wfull_count = 0
    frozen_buf = None
    frozen_cnt = None

    for i, (en, b) in enumerate(schedule):
        dut.en.value = en
        dut.w_bit.value = b
        await Timer(1, "ns")

        cur_wfull = int(dut.wfull.value)
        assert cur_wfull == prev_next_wfull, f"cyc {i}: wfull {cur_wfull} exp {prev_next_wfull}"
        assert int(dut.w_buf.value) == w_buf, \
            f"cyc {i}: w_buf {int(dut.w_buf.value):#0{COLS+2}b} exp {w_buf:#0{COLS+2}b}"

        if en == 0:
            # freeze check: capture on first gap cycle, assert unchanged after
            if frozen_buf is None:
                frozen_buf = int(dut.w_buf.value)
                frozen_cnt = int(dut.wload_cnt.value)
            assert int(dut.w_buf.value) == frozen_buf, f"cyc {i}: w_buf moved during gap"
            assert int(dut.wload_cnt.value) == frozen_cnt, f"cyc {i}: counter moved during gap"
            assert cur_wfull == 0, f"cyc {i}: wfull pulsed during gap"

        if cur_wfull == 1:
            wfull_count += 1

        _, next_wfull, next_cnt, next_wbuf = golden_ref(w_buf, en=en, wload_cnt=cnt, w_bit=b)
        await RisingEdge(dut.clk)
        prev_next_wfull = next_wfull
        w_buf, cnt = next_wbuf, next_cnt

    assert wfull_count == 1, f"expected exactly 1 pulse after interrupt, got {wfull_count}"

@cocotb.test()
async def test_crv(dut) -> None:
    """Random per-cycle (en, w_bit) against the threaded reference.

    Method :
        > Constrained-Random Verification (CRV)

    Stimulus :
        - random (en, w_bit) each cycle for N cycles
        - w_buf, wload_cnt threaded; wfull compared with one-cycle registered lag

    Catches :
        - registered-flag mistiming across random en gaps and counter wraps
        - counter wrap / hold bugs the directed sequences miss
    """
    COLS = int(dut.COLS.value)

    # params for golden_ref
    ref.COLS = COLS

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset
    dut.en.value = 0
    dut.w_bit.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    N = 10000
    seed = int(os.environ.get("SEED", cocotb.RANDOM_SEED))
    rng = random.Random(seed)
    dut._log.info(f"weight_load_tb.test_crv: seed={seed}, N={N}, COLS={COLS}")

    w_buf = 0
    cnt = 0
    prev_next_wfull = 0                             # DUT.wfull after reset = 0

    for i in range(N):
        en = rng.getrandbits(1)
        wb = rng.getrandbits(1)
        dut.en.value = en
        dut.w_bit.value = wb
        await Timer(1, "ns")

        # w_buf: current buffer (vs ref w_buf_out)
        assert int(dut.w_buf.value) == w_buf, \
            f"cyc {i} (en={en},wb={wb}): w_buf {int(dut.w_buf.value):#0{COLS+2}b} exp {w_buf:#0{COLS+2}b} @ seed={seed}"
        # wfull: registered, one-cycle lag (vs PREVIOUS next_wfull)
        assert int(dut.wfull.value) == prev_next_wfull, \
            f"cyc {i} (en={en},wb={wb}): wfull {int(dut.wfull.value)} exp {prev_next_wfull} @ seed={seed}"
        # counter: threaded state (vs ref cnt)
        assert int(dut.wload_cnt.value) == cnt, \
            f"cyc {i} (en={en},wb={wb}): wload_cnt {int(dut.wload_cnt.value)} exp {cnt} @ seed={seed}"

        _, next_wfull, next_cnt, next_wbuf = golden_ref(w_buf, en=en, wload_cnt=cnt, w_bit=wb)
        await RisingEdge(dut.clk)
        prev_next_wfull = next_wfull
        w_buf, cnt = next_wbuf, next_cnt

@cocotb.test(skip=(os.environ.get("SIM") != "icarus"))
async def test_x_prop(dut) -> None:
    """Reset resolves to known state; a data-path X stays confined (Icarus only).

    Method :
        > X-Propagation

    Stimulus :
        - assert rst_n=0 -> w_buf, wfull, wload_cnt all resolve to 0
        - load a single X at the MSB (w_bit=X, one cycle), rest 0
        - shift it through; X occupies one moving w_buf bit and drains
        - counter and wfull stay resolved throughout (control not corrupted)

    Catches :
        - reset leaving X in any register
        - X smearing beyond its one w_buf bit
        - data-path X corrupting the counter or wfull (control path)
        - X failing to drain
    """
    COLS = int(dut.COLS.value)

    # params for golden_ref
    ref.COLS = COLS

    def is_x(v) -> bool:
        return str(v).lower() in ("x", "z")

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # --- reset resolves everything to 0 (clears prior-test state) ---
    dut.en.value = 0
    dut.w_bit.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert dut.w_buf.value.is_resolvable, "reset left X in w_buf"
    assert int(dut.w_buf.value) == 0, "reset did not clear w_buf"
    assert not is_x(dut.wfull.value) and int(dut.wfull.value) == 0, "reset did not clear wfull"
    assert dut.wload_cnt.value.is_resolvable and int(dut.wload_cnt.value) == 0, \
        "reset did not clear wload_cnt"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- load ONE X at the MSB, rest clean 0 ---
    dut.en.value = 1
    dut.w_bit.value = LogicArray("x")              # single X into MSB
    await RisingEdge(dut.clk)
    dut.w_bit.value = 0                            # remaining loads clean

    # continue clean loads; counter/wfull must stay resolved despite X in w_buf
    for _ in range(COLS - 1):
        await Timer(1, "ns")
        assert dut.wload_cnt.value.is_resolvable, "data-path X corrupted the counter"
        assert not is_x(dut.wfull.value), "data-path X corrupted wfull"
        await RisingEdge(dut.clk)

    # after COLS loads the X has walked to bit 0; w_buf still holds exactly one X
    await Timer(1, "ns")
    assert not dut.w_buf.value.is_resolvable, "single X vanished during load (masked)"

    # --- drain: shift the X out; register must fully resolve to 0 ---
    # keep loading 0s (en=1) to shift the X off the LSB end
    for _ in range(COLS):
        dut.w_bit.value = 0
        await RisingEdge(dut.clk)

    await Timer(1, "ns")
    assert dut.w_buf.value.is_resolvable, "X stuck in w_buf — did not drain"
    assert int(dut.w_buf.value) == 0, "w_buf not zero after draining the X"
    assert dut.wload_cnt.value.is_resolvable, "counter went X"