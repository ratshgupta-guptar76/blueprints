# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : shift_reg_tb.py
# Author    : R. Gupta
# Date      : Jul-18-2026
# --------------------------------------------------------------------------------------
# DUT       : shift_reg.sv
# Type      : Sequential, SISO, async reset
# Latency   : 1 Clk Cycle
# Framework : cocotb / Verilator
# 
# DESCRIPTION
# ***********
#   Single DW-bit activation shift register. Always shift toward the LSB every enabled
#   cycle. `compute_bit` and `serial_out` signals both tap sr[0]. Two modes, LOAD and 
#   COMPUTE, register fills in LOAD where as shifts out in COMPUTE. Both modes only 
#   differ only in the bit that fills MSB. The reset is asynchronous
# 
# SPECIFICATION
# *************
#   Reset (@ negedge rst_n) => sr = '0
#   Output (combinational)  => compute_bit = serial_out = sr[0]
#   @ posedge clk:
#       en=1, c_en=1 (COMPUTE) => sr <- {1'b0, sr[DW-1:1]}
#       en=1, c_en=0 (LOAD)    => sr <- {serial_in, sr[DW-1:1]}
#       en=0                   => sr <- sr(hold)
#   Ordering: LSB-first, MSB-last
# 
# PARAMETERS
# **********
#   DW: data-width of activations a.k.a. depth of shift_reg (adopted from dcim_pkg::DW)
# 
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/shift_reg.sv
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# Jul-27-2026 | R. Gupta      | * v1.1   | Move Golden-Ref to cocotb/golden/shift_reg
# ======================================================================================

import os
import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb.types import LogicArray

import golden.shift_reg as ref
from golden.shift_reg import golden_ref

async def load_ones(dut, DW: int) -> None:
    """Load all-ones into the shift register."""
    dut.en.value   = 1
    dut.c_en.value = 0
    for _ in range(DW):
        dut.serial_in.value = 1
        await RisingEdge(dut.clk)

@cocotb.test()
async def test_async_reset(dut) -> None:
    """Asynchronous reset to known-zero state.

    Method :
        > Directed

    Stimulus :
        - assert rst_n=0 between clock edges -> sr clears without an edge
        - drop rst_n mid-shift on a partially-loaded register
        - hold rst_n=0 across several cycles
        - re-assert rst_n on consecutive cycles (back-to-back reset)

    Catches :
        - reset made synchronous (would require a clock edge)
        - reset polarity inverted
        - reset edge-triggered instead of level (misses re-assertion)
    """
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.DW = DW

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # idle
    dut.en.value = 0
    dut.c_en.value = 0
    dut.serial_in.value = 0

    # --- async: rst_n=0 clears output WITHOUT a clock edge ---
    dut.rst_n.value = 0
    await Timer(1, "ns")
    assert int(dut.compute_bit.value) == 0, f"async reset: compute_bit not cleared = {dut.compute_bit.value}"
    assert int(dut.serial_out.value) == 0, f"async reset: serial_out not cleared = {dut.serial_out.value}"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- reset a KNOWN-nonzero, fully-loaded register (no edge) ---
    await load_ones(dut, DW)                       # DW cycles of LOAD serial_in=1
    await Timer(1, "ns")
    assert int(dut.compute_bit.value) == 1, "setup: register not loaded all-ones"
    assert int(dut.sr.value) == (1 << DW) - 1, "setup: full register not all-ones"

    dut.rst_n.value = 0
    await Timer(1, "ns")                           # no clock edge
    assert int(dut.sr.value) == 0, "async reset did not clear a loaded register"
    assert int(dut.compute_bit.value) == 0, "async reset: output not cleared"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- mid-shift: reset while the register is PARTIALLY loaded ---
    dut.en.value = 1
    dut.c_en.value = 0                             # LOAD
    for b in [1, 0, 1]:                            # 3 of DW cycles -> partial
        dut.serial_in.value = b
        await RisingEdge(dut.clk)
    dut.en.value = 0
    await Timer(1, "ns")
    assert int(dut.sr.value) != 0, "setup: partial load left register empty"   # sr[0] may be 0 — check whole reg

    dut.rst_n.value = 0
    await Timer(1, "ns")                           # no edge, mid-operation
    assert int(dut.sr.value) == 0, "async reset mid-shift did not clear"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- hold rst_n=0 across several cycles: level-sensitive, stays 0 ---
    await load_ones(dut, DW)                       # reload non-zero
    await Timer(1, "ns")
    assert int(dut.sr.value) == (1 << DW) - 1, "setup: reload failed"

    dut.rst_n.value = 0                            # hold low
    dut.en.value = 1
    dut.c_en.value = 0
    dut.serial_in.value = 1                        # try to load while held in reset
    for _ in range(3):
        await RisingEdge(dut.clk)                  # edges occur, but reset dominates
        await Timer(1, "ns")
        assert int(dut.sr.value) == 0, "register not held 0 while rst_n low"

    dut.rst_n.value = 1
    dut.en.value = 0
    await RisingEdge(dut.clk)

    # --- back-to-back reset: re-assert on consecutive cycles ---
    await load_ones(dut, DW)                       # non-zero so each reset has something to clear
    await Timer(1, "ns")
    assert int(dut.sr.value) == (1 << DW) - 1, "setup: reload failed"

    dut.rst_n.value = 0                            # first assertion
    await Timer(1, "ns")
    assert int(dut.sr.value) == 0, "first reset did not clear"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    await load_ones(dut, DW)                       # reload between resets
    await Timer(1, "ns")
    dut.rst_n.value = 0                            # second, back-to-back assertion
    await Timer(1, "ns")
    assert int(dut.sr.value) == 0, "re-asserted reset did not clear (edge-triggered bug?)"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

@cocotb.test()
async def test_load_then_compute(dut) -> None:
    """Load a pattern LSB-first, then compute-drain it.

    Method :
        > Directed

    Stimulus :
        - LOAD a known DW-bit pattern over DW cycles (c_en=0)
        - COMPUTE-drain DW cycles (c_en=1)
        - read compute_bit and serial_out every cycle

    Catches :
        - shift toward MSB instead of LSB
        - LOAD fails to fill MSB with serial_in
        - output tapped from the wrong bit
        - compute_bit and serial_out diverging
    """
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.DW = DW

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset to known 0
    dut.en.value = 0
    dut.c_en.value = 0
    dut.serial_in.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    sr = 0                                          # threaded reference state

    # LSB-first pattern (bit i loaded on cycle i)
    pattern = [(i * 5 + 3) & 1 for i in range(DW)]  # deterministic mix; or a fixed literal

    # --- LOAD phase ---
    dut.en.value = 1
    dut.c_en.value = 0                              # LOAD
    for b in pattern:
        dut.serial_in.value = b
        await Timer(1, "ns")                        # combinational output settles
        exp_out, sr = golden_ref(sr, en=1, c_en=0, serial_in=b)
        cb = int(dut.compute_bit.value)
        so = int(dut.serial_out.value)
        assert cb == exp_out, f"LOAD out: got {cb} exp {exp_out}"
        assert cb == so, f"compute_bit={cb} != serial_out={so}"
        await RisingEdge(dut.clk)                   # shift happens

    # register now holds the pattern; verify full state
    await Timer(1, "ns")
    assert int(dut.sr.value) == sr, f"loaded sr={int(dut.sr.value):#0{DW+2}b} exp {sr:#0{DW+2}b}"

    # --- COMPUTE phase: drain, output should reproduce pattern LSB-first ---
    dut.c_en.value = 1                              # COMPUTE
    dut.serial_in.value = 0
    drained = []
    for _ in range(DW):
        await Timer(1, "ns")
        exp_out, sr = golden_ref(sr, en=1, c_en=1, serial_in=0)
        cb = int(dut.compute_bit.value)
        so = int(dut.serial_out.value)
        assert cb == exp_out, f"COMPUTE out: got {cb} exp {exp_out}"
        assert cb == so, f"compute_bit={cb} != serial_out={so}"
        drained.append(cb)
        await RisingEdge(dut.clk)

    assert drained == pattern, f"drained {drained} != loaded {pattern}"

@cocotb.test()
async def test_interrupt(dut) -> None:
    """Enable-gap suspends and resumes an in-progress operation.

    Method :
        > Directed

    Stimulus :
        - LOAD partial -> en=0 several cycles -> resume LOAD -> drain
        - LOAD full -> COMPUTE partial -> en=0 several cycles -> resume drain
        - output holds sr[0] throughout the gap

    Catches :
        - en ignored (register shifts during the hold)
        - state corrupted across a hold
        - resume misaligned (drained sequence wrong after the gap)
    """
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.DW = DW

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    async def reset() -> None:
        dut.en.value = 0; dut.c_en.value = 0; dut.serial_in.value = 0
        dut.rst_n.value = 0
        await Timer(1, "ns")
        dut.rst_n.value = 1
        await RisingEdge(dut.clk)

    async def step(sr, en, c_en, si) -> int:
        """One cycle: drive, check output pre-edge, clock, return threaded sr."""
        dut.en.value = en; dut.c_en.value = c_en; dut.serial_in.value = si
        await Timer(1, "ns")
        exp_out, nxt = golden_ref(sr, en=en, c_en=c_en, serial_in=si)
        cb = int(dut.compute_bit.value)
        assert cb == exp_out, f"out: got {cb} exp {exp_out} (en={en},c_en={c_en})"
        assert cb == int(dut.serial_out.value), "compute_bit != serial_out"
        await RisingEdge(dut.clk)
        return nxt

    pattern = [1, 0, 1, 1, 0, 0, 1, 0]

    # ================= LOAD interrupt =================
    await reset()
    sr = 0

    # load first 3
    for b in pattern[:3]:
        sr = await step(sr, 1, 0, b)

    # hold: en=0 for several cycles — sr frozen, output constant
    await Timer(1, "ns")
    sr_frozen = int(dut.sr.value)
    for _ in range(3):
        sr = await step(sr, 0, 0, 0)                # en=0 hold
        await Timer(1, "ns")
        assert int(dut.sr.value) == sr_frozen, "register shifted during hold (en ignored)"

    # resume load
    for b in pattern[3:]:
        sr = await step(sr, 1, 0, b)

    await Timer(1, "ns")
    assert int(dut.sr.value) == sr, "load state wrong after interrupt"

    # drain — must reproduce the full pattern despite the gap
    drained = []
    for _ in range(DW):
        dut.en.value = 1; dut.c_en.value = 1; dut.serial_in.value = 0
        await Timer(1, "ns")
        drained.append(int(dut.compute_bit.value))
        _, sr = golden_ref(sr, en=1, c_en=1, serial_in=0)
        await RisingEdge(dut.clk)
    assert drained == pattern, f"LOAD-interrupt drain {drained} != {pattern}"

    # ================= COMPUTE interrupt =================
    await reset()
    sr = 0

    # full load
    for b in pattern:
        sr = await step(sr, 1, 0, b)

    # drain 3
    drained = []
    for _ in range(3):
        dut.en.value = 1; dut.c_en.value = 1; dut.serial_in.value = 0
        await Timer(1, "ns")
        drained.append(int(dut.compute_bit.value))
        _, sr = golden_ref(sr, en=1, c_en=1, serial_in=0)
        await RisingEdge(dut.clk)

    # hold mid-drain: en=0, sr frozen, output constant
    await Timer(1, "ns")
    sr_frozen = int(dut.sr.value)
    held_out = int(dut.compute_bit.value)
    for _ in range(3):
        sr = await step(sr, 0, 0, 0)
        await Timer(1, "ns")
        assert int(dut.sr.value) == sr_frozen, "register shifted during compute-hold"
        assert int(dut.compute_bit.value) == held_out, "output changed during hold"

    # resume drain — remaining bits
    for _ in range(DW - 3):
        dut.en.value = 1; dut.c_en.value = 1; dut.serial_in.value = 0
        await Timer(1, "ns")
        drained.append(int(dut.compute_bit.value))
        _, sr = golden_ref(sr, en=1, c_en=1, serial_in=0)
        await RisingEdge(dut.clk)

    assert drained == pattern, f"COMPUTE-interrupt drain {drained} != {pattern}"

@cocotb.test()
async def test_back_to_back(dut) -> None:
    """No-gap mode switches and reload without reset.

    Method :
        > Directed

    Stimulus :
        - LOAD and COMPUTE alternating on consecutive edges (en held high)
        - LOAD pattern A fully, then LOAD pattern B immediately (no reset)

    Catches :
        - mode switch artifact on consecutive edges
        - register fails to fully flush -> pattern A residue leaks into B
    """
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.DW = DW

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    DW = int(dut.DW.value)
    ref.DW = DW

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    async def reset() -> None:
        dut.en.value = 0; dut.c_en.value = 0; dut.serial_in.value = 0
        dut.rst_n.value = 0
        await Timer(1, "ns")
        dut.rst_n.value = 1
        await RisingEdge(dut.clk)

    async def step(sr, en, c_en, si) -> int:
        dut.en.value = en; dut.c_en.value = c_en; dut.serial_in.value = si
        await Timer(1, "ns")
        exp_out, nxt = golden_ref(sr, en=en, c_en=c_en, serial_in=si)
        assert int(dut.compute_bit.value) == exp_out, \
            f"out got {int(dut.compute_bit.value)} exp {exp_out} (en={en},c_en={c_en},si={si})"
        await RisingEdge(dut.clk)
        return nxt

    # ===== reload without reset: A fully replaced by B =====
    await reset()
    sr = 0
    A = [1, 1, 1, 1, 1, 1, 1, 1]                    # all-ones
    B = [0, 0, 0, 0, 0, 0, 0, 0]                    # all-zeros

    for b in A:
        sr = await step(sr, 1, 0, b)
    await Timer(1, "ns")
    assert int(dut.sr.value) == sr, "pattern A not loaded"

    # immediately load B, no reset between
    for b in B:
        sr = await step(sr, 1, 0, b)
    await Timer(1, "ns")
    assert int(dut.sr.value) == sr, "pattern A residue leaked into B"
    assert int(dut.sr.value) == 0, "reload did not fully flush A"

    # ===== alternating LOAD/COMPUTE on consecutive edges, en high =====
    await reset()
    sr = 0
    modes = [(0, 1), (1, 0), (0, 1), (1, 0), (0, 0), (1, 1), (0, 1), (1, 0)]  # (c_en, si) churn
    for c_en, si in modes:
        sr = await step(sr, 1, c_en, si)           # en always 1, mode flips each edge
    await Timer(1, "ns")
    assert int(dut.sr.value) == sr, "mode-switch artifact on consecutive edges"

@cocotb.test()
async def test_compute_ignores_serial_in(dut) -> None:
    """COMPUTE fills MSB with 0, not serial_in.

    Method :
        > Directed

    Stimulus :
        - LOAD a pattern
        - COMPUTE-drain while holding serial_in=1

    Catches :
        - serial_in leaking into the MSB during COMPUTE
          (a bug that uses serial_in in both modes)
    """
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.DW = DW

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset
    dut.en.value = 0; dut.c_en.value = 0; dut.serial_in.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    sr = 0
    pattern = [1, 0, 1, 1, 0, 0, 1, 0]

    # --- LOAD the pattern ---
    dut.en.value = 1; dut.c_en.value = 0
    for b in pattern:
        dut.serial_in.value = b
        await Timer(1, "ns")
        _, sr = golden_ref(sr, en=1, c_en=0, serial_in=b)
        await RisingEdge(dut.clk)

    # --- COMPUTE-drain with serial_in held HIGH (must be ignored) ---
    dut.c_en.value = 1
    dut.serial_in.value = 1                         # the adversarial input
    drained = []
    for _ in range(DW):
        await Timer(1, "ns")
        cb = int(dut.compute_bit.value)
        exp_out, sr = golden_ref(sr, en=1, c_en=1, serial_in=1)   # ref also ignores it
        assert cb == exp_out, f"drain out: got {cb} exp {exp_out}"
        drained.append(cb)
        await RisingEdge(dut.clk)

    assert drained == pattern, f"serial_in leaked: drained {drained} != {pattern}"

    # register fully drained to 0 — proves MSB filled 0s, not serial_in=1
    await Timer(1, "ns")
    assert int(dut.sr.value) == 0, "serial_in leaked into MSB (register not all-zero after drain)"

@cocotb.test()
async def test_crv(dut) -> None:
    """Random per-cycle mode against the threaded reference.

    Method :
        > Constrained-Random Verification (CRV)

    Stimulus :
        - random (en, c_en, serial_in) each cycle for N cycles
        - reference state (next_sr) threaded in lockstep with the DUT

    Catches :
        - mode-transition and timing bugs the directed sequences miss
        - ragged LOAD/COMPUTE/hold adjacencies
    """
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.DW = DW

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # reset
    dut.en.value = 0; dut.c_en.value = 0; dut.serial_in.value = 0
    dut.rst_n.value = 0
    await Timer(1, "ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    N = 10000
    seed = int(os.environ.get("SEED", cocotb.RANDOM_SEED))
    rng = random.Random(seed)
    dut._log.info(f"shift_reg_tb.test_crv: seed={seed}, N={N}, DW={DW}")

    sr = 0                                          # threaded reference state
    for i in range(N):
        en = rng.getrandbits(1)
        c_en = rng.getrandbits(1)
        si = rng.getrandbits(1)

        dut.en.value = en; dut.c_en.value = c_en; dut.serial_in.value = si
        await Timer(1, "ns")

        # output is combinational sr[0], pre-edge
        exp_out, next_sr = golden_ref(sr, en=en, c_en=c_en, serial_in=si)
        cb = int(dut.compute_bit.value)
        so = int(dut.serial_out.value)
        assert cb == exp_out, f"cycle {i} (en={en},c_en={c_en},si={si}): out {cb} exp {exp_out} @ seed={seed}"
        assert cb == so, f"cycle {i}: compute_bit={cb} != serial_out={so} @ seed={seed}"

        await RisingEdge(dut.clk)
        sr = next_sr

        # full-register check every cycle (peek proven working)
        await Timer(1, "ns")
        assert int(dut.sr.value) == sr, \
            f"cycle {i} (en={en},c_en={c_en},si={si}): sr={int(dut.sr.value):#0{DW+2}b} exp {sr:#0{DW+2}b} @ seed={seed}"

@cocotb.test(skip=(os.environ.get("SIM") != "icarus"))
async def test_x_prop(dut) -> None:
    """Powerup-unknown resolves to a known state on reset (Icarus only).

    Method :
        > X-Propagation

    Stimulus :
        - powerup with no reset -> outputs read X
        - assert rst_n=0 -> outputs must resolve to 0
        - load a single X at the MSB (serial_in=X, one LOAD cycle), rest 0
        - shift it down the register and drain over DW cycles

    Catches :
        - reset that does not fully clear the register (X survives)
        - outputs resolving without a real reset (masked X)
        - X smearing beyond its one bit position as it shifts
        - X failing to drain (stuck unknown after DW shifts)
    """
    DW = int(dut.DW.value)

    # params for golden_ref
    ref.DW = DW

    def is_x(v) -> bool:
        """Single-bit signal (Logic) unknown check."""
        return str(v).lower() in ("x", "z")

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    # --- reset resolves output AND full register to 0 ---
    dut.rst_n.value = 0
    await Timer(1, "ns")                             # async, no edge
    assert not is_x(dut.compute_bit.value) and int(dut.compute_bit.value) == 0, \
        "reset did not resolve output to 0"
    assert dut.sr.value.is_resolvable, "reset left X in the register"
    assert int(dut.sr.value) == 0, "reset did not clear the register"

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # --- load ONE X at the MSB, rest 0; the X must occupy exactly one moving bit ---
    dut.en.value = 1
    dut.c_en.value = 0                               # LOAD
    dut.serial_in.value = LogicArray("x")            # single X into MSB
    await RisingEdge(dut.clk)

    dut.serial_in.value = 0                          # remaining loads are clean 0
    for _ in range(DW - 1):
        await RisingEdge(dut.clk)

    # register now holds exactly one X (walked to bit 0), rest resolved 0
    await Timer(1, "ns")
    assert not dut.sr.value.is_resolvable, "single X vanished during load (masked)"

    # --- drain: X appears at output exactly once, then register fully resolves ---
    dut.c_en.value = 1                               # COMPUTE
    dut.serial_in.value = 0
    x_seen = 0
    for _ in range(DW):
        await Timer(1, "ns")
        if is_x(dut.compute_bit.value):
            x_seen += 1
        await RisingEdge(dut.clk)

    assert x_seen == 1, f"X should reach output exactly once (one bit), saw {x_seen}"

    await Timer(1, "ns")
    assert dut.sr.value.is_resolvable, "X stuck in register — did not drain"
    assert int(dut.sr.value) == 0, "register not zero after draining the X"
