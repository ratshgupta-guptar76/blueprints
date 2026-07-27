# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : stream_out_tb.py
# Author    : R. Gupta
# Date      : Jul-19-2026
# --------------------------------------------------------------------------------------
# DUT       : stream_out.sv
# Type      : Sequential, PISO, async reset
# Latency   : done asserts 1 cycle after the final output bit drains (registered)
# Framework : cocotb / Verilator
# 
# DESCRIPTION
# ***********
#   Parallel-in Serial-out shift register and output-bit streamer. Captures the packed
#   accumulator vector and shifts it out one bit per cycle on y_bit. The done signal is
#   asserted once the entire output drain is completed.
#   Reset is asynchronous.
# 
# SPECIFICATION
# *************
#   @ negedge rst_n
#       piso    = '0
#       counter = '0
#       done    =  0
#   @ posedge clk && en == 1, load == 0:
#       piso    = {1'b0, piso[TOT-1:1]}
#       counter = counter + 1
#       done    = (counter == TOT-1) ? 1 : 0
#   @ posedge clk && en == 1, load == 1:
#       piso    = acc
#       counter = '0
#       done    =  0
#   @ posedge clk && en == 0:
#       piso    = piso
#       counter = counter
#       done    = done
#   Output (comb.)  => y_bit = piso[0]
#   Ordering: y_bit shifts out LSB first and then MSB.
# 
# PARAMETERS
# **********
#   N_WEIGHTS: # of weights in each row (adopted from dcim_pkg::N_WEIGHTS)
#   ACC_WIDTH: bit-width of one accumulator (adopted from dcim_pkg::ACC_WIDTH)
# 
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/stream_out.sv
# 
# LIMITATIONS:  en is the master enable. Nothing moves unless en is asserted. Stream
#               requires en & load.
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# Jul-18-2026 | R. Gupta      | * v1.0   | Move Golden-Ref to cocotb/golden/stream_out
# ======================================================================================

import os
import random
import cocotb
from cocotb.triggers import RisingEdge, Timer
from cocotb.clock import Clock
from cocotb.types import LogicArray

import golden.stream_out as ref
from golden.stream_out import golden_ref

@cocotb.test()
async def test_reset(dut) -> None:
    """Asynchronous reset clears piso, counter, and done to zero.

    Method :
        > Directed

    Stimulus :
        - capture a non-zero acc, confirm piso loaded, then reset
        - assert rst_n=0 between edges -> piso, counter, done clear
        - drop rst_n mid-drain
        - hold rst_n=0 across several cycles
        - re-assert on consecutive cycles

    Catches :
        - any of the three registers not cleared
        - reset made synchronous / polarity inverted / edge-not-level
    """
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    TOT = N_WEIGHTS * ACC_WIDTH

    # params for golden_ref
    ref.N_WEIGHTS = N_WEIGHTS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.TOT = TOT

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # idle
    dut.en.value = 0
    dut.load.value = 0
    dut.acc.value = 0

    # --- async: rst_n=0 clears WITHOUT an edge ---
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.y_bit.value) == 0, "async reset: y_bit not cleared"
    assert int(dut.done.value) == 0, "async reset: done not cleared"
    assert int(dut.piso.value) == 0, "async reset: piso not cleared"
    assert int(dut.counter.value) == 0, "async reset: counter not cleared"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- capture a KNOWN non-zero acc, confirm, THEN reset ---
    acc_val = (1 << TOT) - 1                        # all-ones acc
    dut.en.value = 1
    dut.load.value = 1
    dut.acc.value = acc_val
    await RisingEdge(dut.clk)                       # capture edge
    dut.load.value = 0
    await Timer(1, "ns")
    assert int(dut.piso.value) == acc_val, "setup: acc not captured into piso"

    # --- async reset clears the loaded piso, no edge ---
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.piso.value) == 0, "async reset did not clear piso"
    assert int(dut.counter.value) == 0, "async reset did not clear counter"
    assert int(dut.done.value) == 0, "async reset did not clear done"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- mid-drain: reset while draining ---
    dut.en.value = 1
    dut.load.value = 1
    dut.acc.value = acc_val
    await RisingEdge(dut.clk)                       # capture
    dut.load.value = 0
    for _ in range(TOT // 2):                       # drain halfway
        await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert int(dut.counter.value) != 0, "setup: mid-drain counter not advanced"

    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.piso.value) == 0, "async reset mid-drain did not clear piso"
    assert int(dut.counter.value) == 0, "async reset mid-drain did not clear counter"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- hold rst_n=0 across several cycles while driving capture ---
    dut.rst_n.value = 0
    dut.en.value = 1
    dut.load.value = 1
    dut.acc.value = acc_val                         # try to capture while held in reset
    for _ in range(3):
        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        assert int(dut.piso.value) == 0, "piso not held 0 while rst_n low"
        assert int(dut.counter.value) == 0, "counter not held 0 while rst_n low"
        assert int(dut.done.value) == 0, "done not held 0 while rst_n low"

    dut.rst_n.value = 1
    dut.en.value = 0
    dut.load.value = 0
    await RisingEdge(dut.clk)

    # --- back-to-back reset ---
    dut.en.value = 1
    dut.load.value = 1
    dut.acc.value = acc_val
    await RisingEdge(dut.clk)
    dut.load.value = 0
    await Timer(1, "ns")
    assert int(dut.piso.value) == acc_val, "setup: recapture failed"

    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.piso.value) == 0, "first reset did not clear"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    dut.en.value = 1
    dut.load.value = 1
    dut.acc.value = acc_val
    await RisingEdge(dut.clk)
    dut.load.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.piso.value) == 0, "re-asserted reset did not clear"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

@cocotb.test()
async def test_capture_and_drain(dut) -> None:
    """Capture acc, drain LSB-first; done pulses once at drain completion.

    Method :
        > Directed

    Stimulus :
        - capture a known acc on (en & load)
        - drain TOT cycles (en=1, load=0), one extra to observe registered done
        - check y_bit each cycle, done (registered, one-cycle lag), and bit order

    Catches :
        - wrong drain order / shift direction
        - done mistimed vs drain completion (one cycle early/late)
        - done pulsing more than once, or not at all
    """
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    TOT = N_WEIGHTS * ACC_WIDTH

    # params for golden_ref
    ref.N_WEIGHTS = N_WEIGHTS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.TOT = TOT

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset
    dut.en.value = 0
    dut.load.value = 0
    dut.acc.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # deterministic acc (asymmetric so drain direction matters)
    acc_val = 0
    for k in range(TOT):
        acc_val |= ((k * 5 + 3) & 1) << k

    # --- capture on (en & load) ---
    dut.en.value = 1
    dut.load.value = 1
    dut.acc.value = acc_val
    await RisingEdge(dut.clk)                       # capture edge
    dut.load.value = 0

    # thread the ref: after capture, piso=acc, counter=0, done=0
    piso = acc_val
    cnt = 0
    prev_next_done = 0

    drained = []
    done_count = 0

    # drain TOT bits + 1 extra to see the registered done pulse
    for i in range(TOT + 1):
        await Timer(1, "ns")

        # y_bit this cycle == current piso[0]
        assert int(dut.y_bit.value) == (piso & 1), \
            f"cyc {i}: y_bit {int(dut.y_bit.value)} exp {piso & 1}"
        # done this cycle == PREVIOUS call's next_done (registered lag)
        assert int(dut.done.value) == prev_next_done, \
            f"cyc {i}: done {int(dut.done.value)} exp {prev_next_done}"

        if i < TOT:
            drained.append(int(dut.y_bit.value))
        if int(dut.done.value) == 1:
            done_count += 1

        y, next_done, next_cnt, next_piso = golden_ref(piso, cnt, int(dut.done.value),
                                                        en=1, load=0, acc=0)
        await RisingEdge(dut.clk)
        prev_next_done = next_done
        piso, cnt = next_piso, next_cnt

    # drain order: LSB-first, bit k of acc at position k
    expect = [(acc_val >> k) & 1 for k in range(TOT)]
    assert drained == expect, f"drain order: got {drained} exp {expect}"

    # done pulsed exactly once
    assert done_count == 1, f"done pulsed {done_count} times, expected exactly 1"

@cocotb.test()
async def test_capture_gating(dut) -> None:
    """en gates load: capture requires en=1 AND load=1.

    Method :
        > Directed

    Stimulus :
        - capture pattern A, confirm loaded
        - drive en=0, load=1, acc=B for several cycles -> piso must HOLD A
        - drive en=0, load=0 -> piso holds A
        - drive en=1, load=1, acc=B -> piso now captures B

    Catches :
        - capture on load alone (ignoring en) -> stray load corrupts the stream
        - en not gating the load path
    """
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    TOT = N_WEIGHTS * ACC_WIDTH

    # params for golden_ref
    ref.N_WEIGHTS = N_WEIGHTS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.TOT = TOT

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset
    dut.en.value = 0
    dut.load.value = 0
    dut.acc.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    A = 0
    B = 0
    for k in range(TOT):
        A |= ((k * 5 + 3) & 1) << k
    B = A ^ ((1 << TOT) - 1)          # bitwise NOT of A within TOT bits — differs in every bit
    assert A != B, "test setup: A and B must differ"

    # --- capture A ---
    dut.en.value = 1
    dut.load.value = 1
    dut.acc.value = A
    await RisingEdge(dut.clk)
    dut.load.value = 0
    await Timer(1, "ns")
    assert int(dut.piso.value) == A, f"setup: A not captured, piso={int(dut.piso.value):#x}"

    # --- en=0, load=1, acc=B: en gates load -> must HOLD A ---
    dut.en.value = 0
    dut.load.value = 1
    dut.acc.value = B                              # different pattern; a capture bug shows as B
    for c in range(3):
        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        assert int(dut.piso.value) == A, \
            f"en=0/load=1 cyc {c}: piso captured B while disabled (en not gating load): {int(dut.piso.value):#x}"

    # --- en=0, load=0: hold A ---
    dut.load.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert int(dut.piso.value) == A, "en=0/load=0: piso did not hold A"

    # --- en=1, load=1, acc=B: NOW captures B (gate works both ways) ---
    dut.en.value = 1
    dut.load.value = 1
    dut.acc.value = B
    await RisingEdge(dut.clk)
    dut.load.value = 0
    await Timer(1, "ns")
    assert int(dut.piso.value) == B, \
        f"en=1/load=1: B not captured, piso={int(dut.piso.value):#x}"

@cocotb.test()
async def test_done_single_pulse(dut) -> None:
    """done pulses exactly once per drain across back-to-back drains.

    Method :
        > Directed

    Stimulus :
        - capture -> drain TOT -> recapture -> drain, repeated N_DRAINS times
        - track done every cycle

    Catches :
        - done held multiple cycles (FSM mis-transitions out of SHIFT_OUT)
        - done skips a drain (FSM hangs in SHIFT_OUT)
        - done mistimed across drain boundaries
    """
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    TOT = N_WEIGHTS * ACC_WIDTH

    # params for golden_ref
    ref.N_WEIGHTS = N_WEIGHTS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.TOT = TOT

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset
    dut.en.value = 0
    dut.load.value = 0
    dut.acc.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    acc_val = 0
    for k in range(TOT):
        acc_val |= ((k * 5 + 3) & 1) << k

    N_DRAINS = 3

    # build schedule: (load, acc) per cycle — capture then TOT drains, repeated
    schedule = []
    for _ in range(N_DRAINS):
        schedule.append((1, acc_val))            # capture
        schedule += [(0, 0)] * TOT               # drain
    schedule.append((0, 0))                      # extra to observe last done

    dut.en.value = 1

    done_cycles = []
    prev_done = 0

    for i, (load, a) in enumerate(schedule):
        dut.load.value = load
        dut.acc.value = a
        await Timer(1, "ns")

        cur_done = int(dut.done.value)
        # no two consecutive highs -> never held
        assert not (cur_done == 1 and prev_done == 1), \
            f"cyc {i}: done held two consecutive cycles (FSM would mis-transition)"
        if cur_done == 1:
            done_cycles.append(i)

        await RisingEdge(dut.clk)
        prev_done = cur_done

    # exactly N_DRAINS pulses, evenly spaced (TOT drain + 1 recapture)
    assert len(done_cycles) == N_DRAINS, \
        f"expected {N_DRAINS} done pulses, got {len(done_cycles)} at {done_cycles}"
    gaps = [done_cycles[k+1] - done_cycles[k] for k in range(len(done_cycles)-1)]
    assert all(g == TOT + 1 for g in gaps), f"pulses not TOT+1 apart: {done_cycles}"

@cocotb.test()
async def test_recapture(dut) -> None:
    """A load mid-drain aborts the current drain and restarts with the new acc.

    Method :
        > Directed

    Stimulus :
        - capture A, drain partway
        - recapture B mid-drain (en & load) -> counter resets, piso reloads
        - drain B fully -> B's bits, done at completion

    Catches :
        - load not resetting the counter (stale count -> wrong done timing)
        - recapture not overwriting piso (A residue in the B drain)
        - drain not restarting cleanly after mid-stream reload
    """
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    TOT = N_WEIGHTS * ACC_WIDTH

    # params for golden_ref
    ref.N_WEIGHTS = N_WEIGHTS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.TOT = TOT

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset
    dut.en.value = 0
    dut.load.value = 0
    dut.acc.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    A = 0
    for k in range(TOT):
        A |= ((k * 5 + 3) & 1) << k
    B = A ^ ((1 << TOT) - 1)                       # every bit differs
    assert A != B

    # --- capture A, drain partway ---
    dut.en.value = 1
    dut.load.value = 1
    dut.acc.value = A
    await RisingEdge(dut.clk)                       # capture A
    dut.load.value = 0
    for _ in range(TOT // 2):                       # drain partway
        await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert int(dut.counter.value) != 0, "setup: mid-drain counter not advanced"

    # --- recapture B mid-drain: counter resets, piso reloads ---
    dut.load.value = 1
    dut.acc.value = B
    await RisingEdge(dut.clk)                       # recapture
    dut.load.value = 0
    await Timer(1, "ns")
    assert int(dut.piso.value) == B, \
        f"recapture: piso={int(dut.piso.value):#x} not B ({B:#x}) — A residue or no reload"
    assert int(dut.counter.value) == 0, \
        f"recapture: counter={int(dut.counter.value)} not reset"
    assert int(dut.done.value) == 0, "recapture: done not cleared"

    # --- drain B fully; thread ref, confirm B's bits and one done pulse ---
    piso = B
    cnt = 0
    prev_next_done = 0
    drained = []
    done_count = 0

    for i in range(TOT + 1):
        await Timer(1, "ns")
        assert int(dut.y_bit.value) == (piso & 1), \
            f"cyc {i}: y_bit {int(dut.y_bit.value)} exp {piso & 1}"
        assert int(dut.done.value) == prev_next_done, \
            f"cyc {i}: done {int(dut.done.value)} exp {prev_next_done}"
        if i < TOT:
            drained.append(int(dut.y_bit.value))
        if int(dut.done.value) == 1:
            done_count += 1

        _, next_done, next_cnt, next_piso = golden_ref(piso, cnt, int(dut.done.value),
                                                        en=1, load=0, acc=0)
        await RisingEdge(dut.clk)
        prev_next_done = next_done
        piso, cnt = next_piso, next_cnt

    expect = [(B >> k) & 1 for k in range(TOT)]
    assert drained == expect, f"B drain: got {drained} exp {expect}"
    assert done_count == 1, f"done pulsed {done_count} times after recapture, expected 1"

@cocotb.test()
async def test_interrupt(dut) -> None:
    """Enable-gap freezes the drain; it resumes with one delayed done pulse.

    Method :
        > Directed

    Stimulus :
        - capture, drain partway -> en=0 several cycles -> resume -> complete
        - during the gap: piso, counter frozen; done stays low
        - after resume: exactly one done pulse, coincident with completion

    Catches :
        - en ignored (drain advances during the gap)
        - done spuriously pulsing while disabled
        - drain corrupted or done lost across the interruption
    """
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    TOT = N_WEIGHTS * ACC_WIDTH

    # params for golden_ref
    ref.N_WEIGHTS = N_WEIGHTS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.TOT = TOT

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset
    dut.en.value = 0
    dut.load.value = 0
    dut.acc.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    acc_val = 0
    for k in range(TOT):
        acc_val |= ((k * 5 + 3) & 1) << k

    # capture
    dut.en.value = 1
    dut.load.value = 1
    dut.acc.value = acc_val
    await RisingEdge(dut.clk)
    dut.load.value = 0

    piso = acc_val
    cnt = 0
    prev_next_done = 0
    done_count = 0
    frozen_piso = None
    frozen_cnt = None

    half = TOT // 2
    GAP = 3
    # schedule: en per cycle. drain half, gap, drain rest, +1 extra
    ens = [1] * half + [0] * GAP + [1] * (TOT - half) + [1]

    for i, en in enumerate(ens):
        dut.en.value = en
        await Timer(1, "ns")

        cur_done = int(dut.done.value)
        assert cur_done == prev_next_done, f"cyc {i}: done {cur_done} exp {prev_next_done}"
        assert int(dut.y_bit.value) == (piso & 1), \
            f"cyc {i}: y_bit {int(dut.y_bit.value)} exp {piso & 1}"

        if en == 0:
            if frozen_piso is None:
                frozen_piso = int(dut.piso.value)
                frozen_cnt = int(dut.counter.value)
            assert int(dut.piso.value) == frozen_piso, f"cyc {i}: piso moved during gap"
            assert int(dut.counter.value) == frozen_cnt, f"cyc {i}: counter moved during gap"
            assert cur_done == 0, f"cyc {i}: done pulsed during gap"

        if cur_done == 1:
            done_count += 1

        _, next_done, next_cnt, next_piso = golden_ref(piso, cnt, cur_done, en=en, load=0, acc=0)
        await RisingEdge(dut.clk)
        prev_next_done = next_done
        piso, cnt = next_piso, next_cnt

    assert done_count == 1, f"expected exactly 1 done pulse, got {done_count}"

@cocotb.test()
async def test_crv(dut) -> None:
    """Random per-cycle (en, load) against the threaded reference.

    Method :
        > Constrained-Random Verification (CRV)

    Stimulus :
        - random (en, load) each cycle for N cycles, random acc on load
        - piso, counter threaded; done compared with one-cycle registered lag

    Catches :
        - capture/drain/hold transition bugs the directed sequences miss
        - registered-done mistiming across random gaps and recaptures
    """
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    TOT = N_WEIGHTS * ACC_WIDTH

    # params for golden_ref
    ref.N_WEIGHTS = N_WEIGHTS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.TOT = TOT

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset
    dut.en.value = 0
    dut.load.value = 0
    dut.acc.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    N = 10000
    seed = int(os.environ.get("SEED", cocotb.RANDOM_SEED))
    rng = random.Random(seed)
    dut._log.info(f"stream_out_tb.test_crv: seed={seed}, N={N}, TOT={TOT}")

    piso = 0
    cnt = 0
    done = 0
    prev_next_done = 0

    for i in range(N):
        en = rng.getrandbits(1)
        load = rng.getrandbits(1)
        acc = rng.getrandbits(TOT)
        dut.en.value = en
        dut.load.value = load
        dut.acc.value = acc
        await Timer(1, "ns")

        assert int(dut.y_bit.value) == (piso & 1), \
            f"cyc {i} (en={en},load={load}): y_bit {int(dut.y_bit.value)} exp {piso & 1} @ seed={seed}"
        assert int(dut.done.value) == prev_next_done, \
            f"cyc {i} (en={en},load={load}): done {int(dut.done.value)} exp {prev_next_done} @ seed={seed}"
        assert int(dut.piso.value) == piso, \
            f"cyc {i} (en={en},load={load}): piso {int(dut.piso.value):#x} exp {piso:#x} @ seed={seed}"
        assert int(dut.counter.value) == cnt, \
            f"cyc {i} (en={en},load={load}): counter {int(dut.counter.value)} exp {cnt} @ seed={seed}"

        y, next_done, next_cnt, next_piso = golden_ref(piso, cnt, done, en=en, load=load, acc=acc)
        await RisingEdge(dut.clk)
        prev_next_done = next_done
        piso, cnt, done = next_piso, next_cnt, next_done

@cocotb.test(skip=(os.environ.get("SIM") != "icarus"))
async def test_x_prop(dut) -> None:
    """Reset resolves; a data-path X stays confined and drains (Icarus only).

    Method :
        > X-Propagation

    Stimulus :
        - assert rst_n=0 -> piso, counter, done all resolve to 0
        - capture an acc with a single X bit, rest clean
        - drain; the X reaches y_bit at its bit position, then drains out
        - counter and done stay resolved throughout (control not corrupted)

    Catches :
        - reset leaving X in any register
        - X smearing beyond its one piso bit
        - data-path X corrupting the counter or done (control path)
        - X failing to drain
    """
    N_WEIGHTS = int(dut.N_WEIGHTS.value)
    ACC_WIDTH = int(dut.ACC_WIDTH.value)
    TOT = N_WEIGHTS * ACC_WIDTH

    # params for golden_ref
    ref.N_WEIGHTS = N_WEIGHTS
    ref.ACC_WIDTH = ACC_WIDTH
    ref.TOT = TOT

    def is_x(v) -> bool:
        return str(v).lower() in ("x", "z")

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # --- reset resolves everything to 0 (clears prior-test state) ---
    dut.en.value = 0
    dut.load.value = 0
    dut.acc.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert not is_x(dut.y_bit.value) and int(dut.y_bit.value) == 0, "reset did not clear y_bit"
    assert not is_x(dut.done.value) and int(dut.done.value) == 0, "reset did not clear done"
    assert dut.piso.value.is_resolvable and int(dut.piso.value) == 0, "reset did not clear piso"
    assert dut.counter.value.is_resolvable and int(dut.counter.value) == 0, "reset did not clear counter"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- capture acc with ONE X bit at a known position, rest clean 0 ---
    XPOS = TOT // 2
    bits = ["0"] * TOT
    bits[TOT - 1 - XPOS] = "x"                     # LogicArray string: index 0 = MSB
    dut.en.value = 1
    dut.load.value = 1
    dut.acc.value = LogicArray("".join(bits))
    await RisingEdge(dut.clk)                       # capture
    dut.load.value = 0

    # piso now holds one X at bit XPOS; control must be clean
    await Timer(1, "ns")
    assert not dut.piso.value.is_resolvable, "captured X vanished (masked)"
    assert dut.counter.value.is_resolvable, "data-path X corrupted the counter"
    assert not is_x(dut.done.value), "data-path X corrupted done"

    # --- drain: X reaches y_bit at cycle XPOS, exactly once; control stays clean ---
    x_seen = 0
    for i in range(TOT):
        await Timer(1, "ns")
        if is_x(dut.y_bit.value):
            x_seen += 1
        assert dut.counter.value.is_resolvable, f"cyc {i}: counter went X"
        assert not is_x(dut.done.value), f"cyc {i}: done went X"
        await RisingEdge(dut.clk)

    assert x_seen == 1, f"X should reach y_bit exactly once (one bit), saw {x_seen}"

    # --- X has drained; piso fully resolved 0 ---
    await Timer(1, "ns")
    assert dut.piso.value.is_resolvable, "X stuck in piso — did not drain"
    assert int(dut.piso.value) == 0, "piso not zero after draining the X"