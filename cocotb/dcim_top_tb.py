# SPDX-FileCopyrightText: 2026 Chipathon 2026 -- Team A07 Blueprints
# SPDX-License-Identifier: Apache-2.0
"""
dcim_top_tb.py
---------------
System-level testbench for `dcim_top` directly (not the padded `chip_top`,
and not the padframe-facing `A07_dcim_top` wrapper around this same module
that config_core.yaml actually builds as DESIGN_NAME -- see src/A07_dcim_top.sv).
chip_top_tb.py tests the padded workshop-slot build instead, and its GL mode
only runs a single smoke test (y_bit has no working GL path *through the
padring's PAD cells*; see its _internal()/_y_bit() comments). dcim_top has
no padring: y_bit/done/busy are direct primary ports of the synthesized
netlist (confirmed against final/nl/dcim_top.nl.v's own module port list),
so they're readable directly in GL mode with no workaround needed, and every
test below runs in both RTL and GL mode.

Coverage, vs. chip_top_tb.py's single-fixed-seed pattern:
  - Reset/start smoke test.
  - Full-precision matvec, multiple random seeds (not one fixed draw).
  - Reduced-precision matvec, multiple seeds x multiple P values.
  - Full precision sweep P=1..DW against one seed (kept from chip_top_tb.py
    -- exercises the P=1 boundary specifically).
  - Sign/magnitude edge cases: all-zero, max-positive, max-negative
    (-128, the asymmetric two's-complement corner), alternating min/max.
  - Weight-stationary (`cont`) reuse: multiple seeds, AND varying P
    across passes within one cont run (chip_top_tb.py only ever used
    fixed P=DW-1 for its cont test -- this is new coverage).
  - Back-to-back FRESH weight loads (start->run->IDLE->start again,
    loading a DIFFERENT weight matrix the second time) with NO hard
    reset in between. This is the scenario weight_load.sv's own
    wload_cnt has no state-based reset for -- only `en`=wshift_en,
    which control_fsm.sv asserts for one cycle longer than the 1024
    (ROWS*COLS) shifts actually needed (the row_cnt==ROWS-1 && wfull
    transition-triggering cycle is still WRITE_W). That extra shift
    permanently offsets wload_cnt's phase for the *next* WRITE_W entry
    unless wload_cnt is hard-reset in between -- a real, physically
    signed-off RTL property, not a testbench artifact (traced
    cycle-by-cycle against the current weight_load.sv/control_fsm.sv
    before writing this test). Any real host loading more than one
    weight matrix per power-up needs this path to work.
"""
import os
from pathlib import Path

import numpy as np

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, ReadWrite, RisingEdge, Timer
from cocotb_tools.runner import get_runner

from golden_model import (
    ACC_WIDTH,
    DW,
    N_WEIGHTS,
    ROWS,
    golden_bit_serial,
    rand_activation,
    rand_weights,
)

sim = os.getenv("SIM", "icarus")
pdk_root = Path(os.getenv("PDK_ROOT", Path("~/.ciel").expanduser()))
pdk = os.getenv("PDK", "gf180mcuD")
scl = os.getenv("STD_CELL_LIBRARY", "gf180mcu_as_sc_mcu7t3v3")
gl = os.getenv("GL") == "1"

N_SEEDS = int(os.getenv("DCIM_TB_SEEDS", "8"))


def _drive_control(dut, *, a_bit=0, w_bit=0, start=0, cont=0, p_minus1=DW - 1):
    dut.a_bit.value = a_bit
    dut.w_bit.value = w_bit
    dut.start.value = start
    dut.cont.value = cont
    dut.P_minus1.value = p_minus1


async def _drive_and_edge(dut, **kwargs):
    """Drive control signals, wait for the clock edge that captures them, then
    settle into the ReadWrite (reactive) phase before returning.

    GL-mode hazard: a synthesized netlist replaces a handful of RTL
    always_ff blocks with one always@(posedge clk) per gate-level DFF cell.
    Driving the *next* cycle's stimulus immediately upon waking from
    RisingEdge races those blocks' evaluation of *this* edge's D input --
    unspecified relative ordering between cocotb's callback and the
    simulator's own event queue, invisible in RTL (few always_ff blocks,
    ordering happens to work out) but real in GL. Ending every edge-wait in
    ReadWrite (which fires only after all of this edge's Active/NBA updates
    have settled) guarantees any write a caller makes next lands strictly
    after the DUT's own captures for that edge are done."""
    _drive_control(dut, **kwargs)
    await RisingEdge(dut.clk)
    await ReadWrite()


async def _start_up(dut):
    _drive_control(dut)
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    dut.rst_n.value = 0
    await Timer(100, unit="ns")
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    await ReadWrite()


async def _pulse_start(dut, p_minus1):
    """IDLE -> WRITE_W is unregistered (gated only on `start`), so the very next
    edge after the start pulse already has WRITE_W's w_bit capture active."""
    await _drive_and_edge(dut, start=1, p_minus1=p_minus1)
    _drive_control(dut, p_minus1=p_minus1)


async def _load_weights(dut, W, p_minus1):
    """WRITE_W: ROWS*COLS bits (COLS = N_WEIGHTS*DW). Column c holds bit (c % DW)
    of weight (c // DW) -- weight 0 first, LSB-first within each weight (see
    dcim_array.sv's WBL wiring / weight_load.sv's shift direction)."""
    for row in range(ROWS):
        for w_idx in range(N_WEIGHTS):
            value = int(W[row, w_idx]) & ((1 << DW) - 1)
            for bit in range(DW):
                await _drive_and_edge(dut, w_bit=(value >> bit) & 1, p_minus1=p_minus1)


def _activation_bits(a):
    """The DW*ROWS activation bitstream in wire order: reversed(range(ROWS)),
    each row's DW bits LSB-first (see _load_activations)."""
    bits = []
    for row in reversed(range(ROWS)):
        value = int(a[row]) & ((1 << DW) - 1)
        for bit in range(DW):
            bits.append((value >> bit) & 1)
    return bits


async def _load_activations(dut, a, p_minus1):
    """WRITE_A: DW*ROWS bits, rows in reverse order (act_shift_chain.sv is a
    head-to-tail daisy chain; the row sent last travels least and lands in
    the head cell/row 0), each row's bits LSB-first.

    Loads the full bit stream on every pass, including cont-continuation
    passes: a_en is gated on the *current* (pre-edge) state, so the
    SHIFT_OUT->WRITE_A transition edge itself never has a_en high -- nothing
    is captured until the first cycle where state has actually settled to
    WRITE_A, one cycle later than a naive reading of the FSM diagram
    suggests. There is no bit that's already "captured" for a continuation
    pass to skip."""
    for value in _activation_bits(a):
        await _drive_and_edge(dut, a_bit=value, p_minus1=p_minus1)


async def _start_weights(dut, W, p_minus1):
    """IDLE -> WRITE_W -> WRITE_A boundary: pulse start, load ROWS*COLS weight
    bits, then cross the wfull registration bubble. Leaves the DUT ready for
    _compute_and_drain's activation load on the very next edge.

    Unlike chip_top_tb.py's caution note, this function IS exercised a
    second time without an intervening hard reset by
    test_second_fresh_weight_load_without_reset below -- that's the
    scenario under test, not something being avoided here."""
    await _pulse_start(dut, p_minus1)
    await _load_weights(dut, W, p_minus1)

    # WRITE_W -> WRITE_A is gated on `wfull`, which weight_load.sv registers one
    # cycle after the 32nd (COLS-th) weight bit -- so there is exactly one bubble
    # cycle here where a_en is still 0 and no activation bit is captured.
    await _drive_and_edge(dut, p_minus1=p_minus1)


async def _compute_and_drain(dut, a, p_minus1, cont):
    """WRITE_A -> COMPUTE -> DONE -> SHIFT_OUT for one activation vector, and
    return the N_WEIGHTS signed accumulator lanes (two's-complement, ACC_WIDTH
    bits each). Works identically for a fresh weight load or a cont-reuse
    pass -- see _load_activations for why cont passes don't skip anything."""
    await _load_activations(dut, a, p_minus1)

    await ClockCycles(dut.clk, p_minus1 + 1)
    await ReadOnly()
    assert int(dut.done.value) == 1, "expected DONE high after COMPUTE finished"

    # DONE -> SHIFT_OUT: this edge captures y into stream_out's PISO, so y_bit is
    # already valid (lane 0, bit 0) the instant we land in SHIFT_OUT.
    await RisingEdge(dut.clk)
    await ReadWrite()

    lanes = [0] * N_WEIGHTS
    for lane in range(N_WEIGHTS):
        for bit in range(ACC_WIDTH):
            _drive_control(dut, cont=cont, p_minus1=p_minus1)
            await ReadOnly()
            lanes[lane] |= int(dut.y_bit.value) << bit
            await RisingEdge(dut.clk)
            await ReadWrite()

    # SHIFT_OUT -> WRITE_A (cont) or -> IDLE: a_en is gated on the pre-edge
    # state, so nothing is captured on this edge regardless of what's driven
    # here -- the next pass's _load_activations starts clean on the cycle
    # after this one.
    await _drive_and_edge(dut, cont=cont, p_minus1=p_minus1)

    sign_bit = 1 << (ACC_WIDTH - 1)
    return [v - (1 << ACC_WIDTH) if v & sign_bit else v for v in lanes]


async def _run_matvec(dut, W, a, p_minus1):
    """One full START..SHIFT_OUT pass (fresh weight load, cont=0)."""
    await _start_weights(dut, W, p_minus1)
    return await _compute_and_drain(dut, a, p_minus1, cont=0)


async def _run_weight_stationary(dut, W, passes):
    """Load weights once, then run one _compute_and_drain per (a, p_minus1)
    pair in `passes` via the `cont` reuse path."""
    await _start_weights(dut, W, passes[0][1])

    results = []
    for i, (a, p_minus1) in enumerate(passes):
        cont = i < len(passes) - 1
        results.append(await _compute_and_drain(dut, a, p_minus1, cont=cont))
    return results


@cocotb.test()
async def test_start_sets_busy(dut):
    """Single-aspect smoke test: START pulse should drive BUSY high."""
    await _start_up(dut)
    await ReadOnly()
    assert int(dut.busy.value) == 0, "BUSY should be low after reset"
    await RisingEdge(dut.clk)
    await ReadWrite()
    await _pulse_start(dut, p_minus1=DW - 1)
    for _ in range(20):
        await ReadOnly()
        if int(dut.busy.value) == 1:
            return
        await RisingEdge(dut.clk)
        await ReadWrite()
    raise AssertionError("START did not make BUSY go high within 20 cycles")


@cocotb.test()
async def test_matvec_multi_seed(dut):
    """Full-precision matvec vs. golden model, N_SEEDS independent random
    (W, a) draws (fresh hard reset each draw) -- chip_top_tb.py's equivalent
    test used exactly one fixed seed."""
    for seed in range(N_SEEDS):
        await _start_up(dut)
        rng = np.random.default_rng(0xC0FFEE + seed)
        W = rand_weights(rng)
        a = rand_activation(rng)
        expected, _ = golden_bit_serial(W, a, DW)
        got = await _run_matvec(dut, W, a, DW - 1)
        assert got == list(expected), f"seed {seed}: matvec mismatch:\n got={got}\n exp={list(expected)}"


@cocotb.test()
async def test_matvec_reduced_precision_multi_seed(dut):
    """Reduced-precision matvec vs. golden model, sweeping both P and seed."""
    for seed, p_minus1 in enumerate([0, 1, 3, 5, 6]):
        await _start_up(dut)
        rng = np.random.default_rng(0xDECAFBAD + seed)
        W = rand_weights(rng)
        a = rand_activation(rng)
        expected, _ = golden_bit_serial(W, a, p_minus1 + 1)
        got = await _run_matvec(dut, W, a, p_minus1)
        assert got == list(expected), f"P={p_minus1 + 1}: matvec mismatch:\n got={got}\n exp={list(expected)}"


@cocotb.test()
async def test_matvec_precision_sweep(dut):
    """Every precision P=1..DW against the same W/a via the cont path,
    including the P=1 boundary (bp_cnt==P_minus1 fires on COMPUTE's very
    first cycle)."""
    await _start_up(dut)
    rng = np.random.default_rng(0x5EED)
    W = rand_weights(rng)
    a = rand_activation(rng)

    passes = [(a, p_minus1) for p_minus1 in range(DW)]
    got_all = await _run_weight_stationary(dut, W, passes)

    for p_minus1, got in zip(range(DW), got_all):
        expected, _ = golden_bit_serial(W, a, p_minus1 + 1)
        assert got == list(expected), f"P={p_minus1 + 1} matvec mismatch:\n got={got}\n exp={list(expected)}"


@cocotb.test()
async def test_matvec_edge_cases(dut):
    """Data corners most likely to trip sign-handling bugs: all-zero, max
    positive, max magnitude negative (-128 = 8'h80, the asymmetric two's-
    complement corner lane_shift_accum.sv's MSB-subtract logic targets), and
    a mixed min/max pattern."""
    cases = {
        "all_zero": (
            np.zeros((ROWS, N_WEIGHTS), dtype=np.int8),
            np.zeros((ROWS,), dtype=np.uint8),
        ),
        "max_positive": (
            np.full((ROWS, N_WEIGHTS), 127, dtype=np.int8),
            np.full((ROWS,), 255, dtype=np.uint8),
        ),
        "max_negative_weight": (
            np.full((ROWS, N_WEIGHTS), -128, dtype=np.int8),
            np.full((ROWS,), 255, dtype=np.uint8),
        ),
        "alternating_min_max": (
            np.where(
                (np.arange(ROWS * N_WEIGHTS) % 2 == 0).reshape(ROWS, N_WEIGHTS),
                np.int8(-128), np.int8(127),
            ),
            np.where(np.arange(ROWS) % 2 == 0, np.uint8(0), np.uint8(255)),
        ),
    }
    p_minus1 = DW - 1
    for name, (W, a) in cases.items():
        await _start_up(dut)
        expected, _ = golden_bit_serial(W, a, DW)
        got = await _run_matvec(dut, W, a, p_minus1)
        assert got == list(expected), f"{name}: matvec mismatch:\n got={got}\n exp={list(expected)}"


@cocotb.test()
async def test_matvec_weight_stationary_multi_seed(dut):
    """`cont` path across N_SEEDS independent weight-load sessions, each
    reusing one weight load across 3 activation vectors WITH VARYING
    PRECISION per pass (chip_top_tb.py's equivalent test held P fixed
    across the whole cont run -- this additionally covers P changing
    mid-stream while weight-stationary)."""
    for seed in range(N_SEEDS):
        await _start_up(dut)
        rng = np.random.default_rng(0xB16B00B5 + seed)
        W = rand_weights(rng)
        activations = [rand_activation(rng) for _ in range(3)]
        p_minus1s = [DW - 1, 2, DW - 1]

        expected = [
            list(golden_bit_serial(W, a, p + 1)[0]) for a, p in zip(activations, p_minus1s)
        ]
        passes = list(zip(activations, p_minus1s))
        got = await _run_weight_stationary(dut, W, passes)
        assert got == expected, f"seed {seed}: weight-stationary mismatch:\n got={got}\n exp={expected}"


@cocotb.test()
async def test_second_fresh_weight_load_without_reset(dut):
    """Two INDEPENDENT fresh weight loads (start -> WRITE_W, not the `cont`
    reuse path) back to back, with NO hard reset between them -- only the
    FSM's own natural SHIFT_OUT -> IDLE -> (host pulses start again) return.

    This specifically targets weight_load.sv's wload_cnt, which has no
    per-state reset (only hard rst_n): control_fsm.sv's wshift_en stays
    asserted for one cycle longer than the ROWS*COLS shifts actually
    needed (the row_cnt==ROWS-1 && wfull transition-triggering cycle is
    still WRITE_W), so wload_cnt picks up one uncounted extra shift every
    complete WRITE_W session. If that phase offset isn't cleared before
    the next fresh weight load, the second load's column-bit mapping is
    off by one and W2 gets corrupted -- while the FIRST load in any
    simulation always starts from a clean hard-reset wload_cnt=0, so
    every other test in this file (and in chip_top_tb.py) is structurally
    incapable of catching this regardless of how many seeds they use.

    Any real host loading more than one weight matrix per power-up cycle
    depends on this working; not exercising it is a real coverage gap in
    the existing suite, not a hypothetical one -- this test's own
    docstring in chip_top_tb.py explicitly documents calling the
    equivalent helper twice without an intervening reset as unsupported."""
    await _start_up(dut)
    rng = np.random.default_rng(0x5EC0D_BAD)
    p_minus1 = DW - 1

    W1 = rand_weights(rng)
    a1 = rand_activation(rng)
    expected1, _ = golden_bit_serial(W1, a1, DW)
    got1 = await _run_matvec(dut, W1, a1, p_minus1)
    assert got1 == list(expected1), f"first load: matvec mismatch:\n got={got1}\n exp={list(expected1)}"

    # Back in IDLE naturally (cont=0 was used above) -- no reset here.
    W2 = rand_weights(rng)
    a2 = rand_activation(rng)
    expected2, _ = golden_bit_serial(W2, a2, DW)
    got2 = await _run_matvec(dut, W2, a2, p_minus1)
    assert got2 == list(expected2), (
        f"second load (no intervening reset): matvec mismatch:\n got={got2}\n exp={list(expected2)}\n"
        "If this fails, weight_load.sv's wload_cnt phase-shift (see this test's docstring) is real: "
        "the design cannot load a second weight matrix without a hard reset in between."
    )


def dcim_top_runner():
    proj_path = Path(__file__).resolve().parent
    src_path = proj_path / "../src"

    if gl:
        sources = [
            proj_path / "../final/nl/dcim_top.nl.v",
            pdk_root / pdk / "libs.ref" / scl / "verilog" / f"{scl}.v",
            proj_path / "../ip/sram_32x8_9T/vh/sram_32x8_9T.v",
        ]
        defines = {}
    else:
        sources = [
            src_path / "dcim_pkg.sv",
            src_path / "row_decoder.sv",
            src_path / "shift_reg.sv",
            src_path / "col_adder.sv",
            src_path / "weight_load.sv",
            src_path / "stream_out.sv",
            src_path / "adder_tree.sv",
            src_path / "act_shift_chain.sv",
            src_path / "lane_shift_accum.sv",
            src_path / "shift_accum.sv",
            src_path / "dcim_array.sv",
            src_path / "control_fsm.sv",
            src_path / "dcim_top.sv",
            proj_path / "../ip/sram_32x8_9T/vh/sram_32x8_9T.v",
        ]
        defines = {}

    runner = get_runner(sim)

    if sim == "icarus":
        build_args = ["-g2012"]
    elif sim == "verilator":
        # GL mode only: Icarus has a confirmed event-scheduling bug for this
        # netlist's zero-delay, CTS-buffered flop-to-flop chains (activation
        # shift chain reads back wrong data for interior cells; Verilator,
        # a structurally different simulator, gets bit-exact correct results
        # on the identical netlist). --timing is required for the SCL's
        # primitives; -Wno-fatal since GL netlists trip lint warnings by
        # design.
        build_args = ["--timing", "-Wno-fatal"]
    else:
        build_args = []

    runner.build(
        sources=sources,
        hdl_toplevel="dcim_top",
        defines=defines,
        includes=[src_path],
        build_args=build_args,
        always=True,
        waves=True,
    )

    runner.test(
        hdl_toplevel="dcim_top",
        test_module="dcim_top_tb",
        waves=True,
    )


if __name__ == "__main__":
    dcim_top_runner()
