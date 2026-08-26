# SPDX-FileCopyrightText: 2026 Chipathon 2026 -- Team A07 Blueprints
# SPDX-License-Identifier: Apache-2.0
"""
A07_dcim_top_tb.py
-------------------
System-level testbench for `A07_dcim_top`, the padframe-facing wrapper that
config_core.yaml builds as DESIGN_NAME (see src/A07_dcim_top.sv) around the
pure `dcim_top` macro -- not the padded `chip_top` (chip_top_tb.py tests that
build instead, and its GL mode only runs a single smoke test: y_bit has no
working GL path *through the padring's PAD cells*; see its
_internal()/_y_bit() comments).

A07_dcim_top's P_minus1 is a packed 3-bit vector and
y_bit/done/busy are split into _OUT variants plus unused pad-config pins
(PU/PD/CS/SL/IE/OE/PDRV0/PDRV1, tied off in RTL -- see src/A07_dcim_top.sv)
and unused _IN receiver pins (also tied off there, driven 0 here for
cleanliness). Both RTL and GL mode build/target A07_dcim_top directly -- GL
reads config_core.yaml's actual synthesized output,
final/nl/A07_dcim_top.nl.v, whose top module is A07_dcim_top itself (Yosys
flattens the wrapper + dcim_top's internal hierarchy into one module), so no
port-adapter shim is needed either way, and every test below runs in both
RTL and GL mode.

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
  - Blackbox top-level interface check against A07_A.def.
  - Constrained-random regression over randomized operation sequences.
"""
import os
from pathlib import Path

import numpy as np

import cocotb
from cocotb.triggers import ReadOnly, ReadWrite, RisingEdge
from cocotb_tools.runner import get_runner

from a07_dcim_top_helpers import (
    _pulse_start,
    _run_matvec,
    _run_weight_stationary,
    _start_up,
)
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


_EXPECTED_SCALAR_PINS = [
    "clk_PU", "clk_PD", "clk",
    "rst_n_PU", "rst_n_PD", "rst_n",
    "a_bit_PU", "a_bit_PD", "a_bit",
    "w_bit_PU", "w_bit_PD", "w_bit",
    "start_PU", "start_PD", "start",
    "cont_PU", "cont_PD", "cont",
    "y_bit_CS", "y_bit_SL", "y_bit_IE", "y_bit_OE", "y_bit_PU", "y_bit_PD",
    "y_bit_OUT", "y_bit_PDRV0", "y_bit_PDRV1", "y_bit_IN",
    "done_CS", "done_SL", "done_IE", "done_OE", "done_PU", "done_PD",
    "done_OUT", "done_PDRV0", "done_PDRV1", "done_IN",
    "busy_CS", "busy_SL", "busy_IE", "busy_OE", "busy_PU", "busy_PD",
    "busy_OUT", "busy_PDRV0", "busy_PDRV1", "busy_IN",
]
_EXPECTED_VECTOR_PINS = [("P_minus1", 3), ("P_minus1_PU", 3), ("P_minus1_PD", 3)]


@cocotb.test()
async def test_top_level_pins_match_padframe_spec(dut):
    """Blackbox interface check against A07_A.def."""
    missing = []
    wrong_width = []

    for name in _EXPECTED_SCALAR_PINS:
        if getattr(dut, name, None) is None:
            missing.append(name)

    for name, width in _EXPECTED_VECTOR_PINS:
        handle = getattr(dut, name, None)
        if handle is None:
            missing.append(name)
            continue
        if len(handle) != width:
            wrong_width.append((name, len(handle), width))

    assert not missing, f"DUT is missing pin(s) required by A07_A.def: {missing}"
    assert not wrong_width, (
        f"DUT pin(s) have the wrong width vs A07_A.def (name, got, want): {wrong_width}"
    )


@cocotb.test()
async def test_start_sets_busy(dut):
    """Single-aspect smoke test: START pulse should drive BUSY high."""
    await _start_up(dut)
    await ReadOnly()
    assert int(dut.busy_OUT.value) == 0, "BUSY should be low after reset"
    await RisingEdge(dut.clk)
    await ReadWrite()
    await _pulse_start(dut, p_minus1=DW - 1)
    for _ in range(20):
        await ReadOnly()
        if int(dut.busy_OUT.value) == 1:
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


@cocotb.test()
async def test_matvec_constrained_random_regression(dut):
    """Constrained-random regression over randomized operation sequences."""
    rng = np.random.default_rng(int(os.getenv("DCIM_TB_CRV_SEED", "3735928559")))
    n_iters = int(os.getenv("DCIM_TB_CRV_ITERS", "20"))

    await _start_up(dut)

    for trial in range(n_iters):
        W = rand_weights(rng)
        n_passes = int(rng.integers(1, 5))
        passes = [
            (rand_activation(rng), int(rng.integers(0, DW)))
            for _ in range(n_passes)
        ]

        got_all = await _run_weight_stationary(dut, W, passes)

        for i, ((a, p_minus1), got) in enumerate(zip(passes, got_all)):
            expected, _ = golden_bit_serial(W, a, p_minus1 + 1)
            assert got == list(expected), (
                f"trial {trial} pass {i}/{n_passes} (P={p_minus1 + 1}): "
                f"matvec mismatch:\n got={got}\n exp={list(expected)}"
            )

        if rng.random() < 0.3:
            await _start_up(dut)


def a07_dcim_top_runner():
    proj_path = Path(__file__).resolve().parent
    src_path = proj_path / "../src"

    if gl:
        sources = [
            proj_path / "../final/nl/A07_dcim_top.nl.v",
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
            src_path / "A07_dcim_top.sv",
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
        hdl_toplevel="A07_dcim_top",
        defines=defines,
        includes=[src_path],
        build_args=build_args,
        always=True,
        waves=True,
    )

    runner.test(
        hdl_toplevel="A07_dcim_top",
        test_module="A07_dcim_top_tb",
        waves=True,
    )


if __name__ == "__main__":
    a07_dcim_top_runner()
