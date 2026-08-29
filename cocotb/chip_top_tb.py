# SPDX-FileCopyrightText: 2026 Chipathon 2026 workshop
# SPDX-License-Identifier: Apache-2.0
"""
chip_top_tb.py
---------------
System-level testbench for `chip_top`, the full padframe-wrapped chip (built
by config.yaml's default flow / the `sim`/`sim-gl` Makefile targets) -- not
the padframe-free core wrapper A07_dcim_top (A07_dcim_top_tb.py tests that
build instead, via `sim-gl-core`).

Coverage mirrors A07_dcim_top_tb.py wherever chip_top's GL mode can support
it: pin-interface check, multi-seed matvec/reduced-precision/weight-
stationary variants, the back-to-back-fresh-weight-load regression, and a
constrained-random regression. The one gap that can't be closed: GL mode here
only runs test_start_sets_busy and test_top_level_pins_match_padframe_spec --
every other test needs y_bit, which has no working path through the real
padring's switch-level PAD cells in GL (optimized/renamed away in synthesis;
see _y_bit in chip_top_helpers.py). A07_dcim_top_tb.py's GL mode has no such
gap because it targets the unpadded core wrapper directly.
"""

import os
from pathlib import Path

import numpy as np

import cocotb
from cocotb.triggers import RisingEdge
from cocotb_tools.runner import get_runner

from chip_top_helpers import _busy, _pulse_start, _run_matvec, _run_weight_stationary, _start_up
from golden_model import (
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
slot = os.getenv("SLOT", "workshop")
scl = os.getenv("STD_CELL_LIBRARY", "gf180mcu_as_sc_mcu7t3v3")
gl = os.getenv("GL") == "1"

N_SEEDS = int(os.getenv("DCIM_TB_SEEDS", "8"))

# (NUM_INPUT_PADS, NUM_BIDIR_PADS, NUM_ANALOG_PADS) per SLOT -- mirrors the
# `ifdef SLOT_* blocks in src/slot_defines.svh (clk_PAD/rst_n_PAD are fixed
# scalars in every slot, so they aren't listed here).
_SLOT_PAD_WIDTHS = {
    "1x1": (12, 40, 2),
    "0p5x1": (4, 44, 6),
    "1x0p5": (4, 46, 4),
    "0p5x0p5": (4, 38, 4),
    "workshop": (1, 20, 60),
}


@cocotb.test()
async def test_top_level_pins_match_padframe_spec(dut):
    """Blackbox interface check against src/slot_defines.svh for the active SLOT
    -- chip_top's inout ports (clk_PAD, rst_n_PAD, input_PAD, bidir_PAD,
    analog_PAD) are fixed; only their widths vary per slot. Runs in both RTL
    and GL mode (these are chip_top's own top-level ports, unaffected by the
    y_bit-through-padring GL limitation -- see _y_bit). Mirrors
    A07_dcim_top_tb.py's test_top_level_pins_match_padframe_spec."""
    n_input, n_bidir, n_analog = _SLOT_PAD_WIDTHS[slot]

    missing = [
        name
        for name in ("clk_PAD", "rst_n_PAD", "input_PAD", "bidir_PAD", "analog_PAD")
        if getattr(dut, name, None) is None
    ]
    assert not missing, f"DUT is missing pin(s) required by SLOT={slot}: {missing}"

    wrong_width = [
        (name, len(getattr(dut, name)), width)
        for name, width in (
            ("input_PAD", n_input),
            ("bidir_PAD", n_bidir),
            ("analog_PAD", n_analog),
        )
        if len(getattr(dut, name)) != width
    ]
    assert not wrong_width, (
        f"DUT pin(s) have the wrong width vs SLOT={slot} (name, got, want): {wrong_width}"
    )


@cocotb.test()
async def test_start_sets_busy(dut):
    """Single-aspect smoke test: START pulse should drive BUSY high."""
    await _start_up(dut)

    assert _busy(dut) == 0, "BUSY should be low after reset"

    await _pulse_start(dut, p_minus1=DW - 1)

    for _ in range(20):
        if _busy(dut) == 1:
            return
        await RisingEdge(dut.clk_PAD)

    raise AssertionError("START did not make BUSY go high within 20 cycles")


@cocotb.test(skip=gl)  # needs y_bit, no working GL path -- see _y_bit
async def test_matvec_matches_golden_model(dut):
    """Full-precision (P=DW) matrix-vector multiply vs. golden_bit_serial."""
    await _start_up(dut)

    np_rng = np.random.default_rng(0xC0FFEE)
    W = rand_weights(np_rng)
    a = rand_activation(np_rng)

    p_minus1 = DW - 1
    expected, _trace = golden_bit_serial(W, a, DW)

    got = await _run_matvec(dut, W, a, p_minus1)

    assert got == list(expected), (
        f"matvec mismatch:\n got={got}\n exp={list(expected)}"
    )


@cocotb.test(skip=gl)  # needs y_bit, no working GL path -- see _y_bit
async def test_matvec_reduced_precision(dut):
    """Same as above but with P < DW, to exercise variable-precision COMPUTE
    (P = p_minus1 + 1 bit-planes instead of the full DW)."""
    await _start_up(dut)

    np_rng = np.random.default_rng(0xDECAFBAD)
    W = rand_weights(np_rng)
    a = rand_activation(np_rng)

    p_minus1 = 3  # P = 4 bit-planes
    expected, _trace = golden_bit_serial(W, a, p_minus1 + 1)

    got = await _run_matvec(dut, W, a, p_minus1)

    assert got == list(expected), (
        f"matvec mismatch:\n got={got}\n exp={list(expected)}"
    )


@cocotb.test(skip=gl)  # needs y_bit, no working GL path -- see _y_bit
async def test_matvec_precision_sweep(dut):
    """Every precision P=1..DW against the same W/a, including the P=1 boundary
    (bp_cnt==P_minus1 fires on COMPUTE's very first cycle). Uses the `cont`
    weight-stationary path (one weight load, 8 activation-only passes) rather
    than a fresh reset per P -- both because it's faster and because it's
    extra exercise of the cont datapath (see test_matvec_weight_stationary)."""
    await _start_up(dut)

    np_rng = np.random.default_rng(0x5EED)
    W = rand_weights(np_rng)
    a = rand_activation(np_rng)

    passes = [(a, p_minus1) for p_minus1 in range(DW)]
    got_all = await _run_weight_stationary(dut, W, passes)

    for p_minus1, got in zip(range(DW), got_all):
        expected, _trace = golden_bit_serial(W, a, p_minus1 + 1)
        assert got == list(expected), (
            f"P={p_minus1 + 1} matvec mismatch:\n got={got}\n exp={list(expected)}"
        )


@cocotb.test(skip=gl)  # needs y_bit, no working GL path -- see _y_bit
async def test_matvec_edge_cases(dut):
    """Data corners most likely to trip sign-handling bugs: all-zero, max
    positive, max magnitude negative (-128 = 8'h80, the asymmetric two's-
    complement corner lane_shift_accum.sv's MSB-subtract logic targets), and a
    mixed min/max pattern. Each case gets its own weight matrix, so each needs
    a fresh _start_up (hard reset) rather than re-entering WRITE_W directly --
    see _start_weights's caution note."""
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
                np.int8(-128),
                np.int8(127),
            ),
            np.where(np.arange(ROWS) % 2 == 0, np.uint8(0), np.uint8(255)),
        ),
    }

    p_minus1 = DW - 1
    for name, (W, a) in cases.items():
        await _start_up(dut)
        expected, _trace = golden_bit_serial(W, a, DW)
        got = await _run_matvec(dut, W, a, p_minus1)
        assert got == list(expected), (
            f"{name} matvec mismatch:\n got={got}\n exp={list(expected)}"
        )


@cocotb.test(skip=gl)  # needs y_bit, no working GL path -- see _y_bit
async def test_matvec_weight_stationary(dut):
    """`cont` path: load weights once, then run 3 different activation vectors
    back to back via SHIFT_OUT->WRITE_A (skipping WRITE_W after the first).

    This used to fail on the 2nd/3rd pass with wrong (not just late) results.
    Root cause, found via a waveform dump (FST -> VCD, then diffing the actual
    a_bit sequence against the intended one bit-for-bit): the SHIFT_OUT-exit
    edge that transitions into the next WRITE_A phase is *already* a real
    a_en-active capture edge, not a free bubble -- so driving a default a_bit
    there (as _compute_and_drain used to) silently captured a stray 0 as the
    next pass's first bit, shifting its entire 256-bit stream by one position
    and dropping the true last bit. This is a testbench bug, not an RTL bug --
    the RTL's cont/weight-stationary datapath is correct. Fixed by driving the
    next pass's real first bit on that edge and telling _load_activations to
    send only the remaining 255 bits (see _compute_and_drain's
    skip_first_bit/next_a handling)."""
    await _start_up(dut)

    np_rng = np.random.default_rng(0xB16B00B5)
    W = rand_weights(np_rng)
    activations = [rand_activation(np_rng) for _ in range(3)]

    p_minus1 = DW - 1
    expected = [
        list(golden_bit_serial(W, a, DW)[0]) for a in activations
    ]

    passes = [(a, p_minus1) for a in activations]
    got = await _run_weight_stationary(dut, W, passes)

    assert got == expected, f"weight-stationary mismatch:\n got={got}\n exp={expected}"


@cocotb.test(skip=gl)  # needs y_bit, no working GL path -- see _y_bit
async def test_matvec_multi_seed(dut):
    """Full-precision matvec vs. golden model, N_SEEDS independent random (W, a)
    draws (fresh hard reset each draw) -- extends
    test_matvec_matches_golden_model's single fixed seed. Mirrors
    A07_dcim_top_tb.py's equivalent test."""
    for seed in range(N_SEEDS):
        await _start_up(dut)
        np_rng = np.random.default_rng(0xC0FFEE + seed)
        W = rand_weights(np_rng)
        a = rand_activation(np_rng)
        expected, _trace = golden_bit_serial(W, a, DW)
        got = await _run_matvec(dut, W, a, DW - 1)
        assert got == list(expected), (
            f"seed {seed}: matvec mismatch:\n got={got}\n exp={list(expected)}"
        )


@cocotb.test(skip=gl)  # needs y_bit, no working GL path -- see _y_bit
async def test_matvec_reduced_precision_multi_seed(dut):
    """Reduced-precision matvec vs. golden model, sweeping both P and seed --
    extends test_matvec_reduced_precision's single (P, seed) pair. Mirrors
    A07_dcim_top_tb.py's equivalent test."""
    for seed, p_minus1 in enumerate([0, 1, 3, 5, 6]):
        await _start_up(dut)
        np_rng = np.random.default_rng(0xDECAFBAD + seed)
        W = rand_weights(np_rng)
        a = rand_activation(np_rng)
        expected, _trace = golden_bit_serial(W, a, p_minus1 + 1)
        got = await _run_matvec(dut, W, a, p_minus1)
        assert got == list(expected), (
            f"P={p_minus1 + 1}: matvec mismatch:\n got={got}\n exp={list(expected)}"
        )


@cocotb.test(skip=gl)  # needs y_bit, no working GL path -- see _y_bit
async def test_matvec_weight_stationary_multi_seed(dut):
    """`cont` path across N_SEEDS independent weight-load sessions, each reusing
    one weight load across 3 activation vectors WITH VARYING PRECISION per pass
    -- test_matvec_weight_stationary above holds P fixed across the whole cont
    run; this additionally covers P changing mid-stream while weight-stationary.
    Mirrors A07_dcim_top_tb.py's equivalent test."""
    for seed in range(N_SEEDS):
        await _start_up(dut)
        np_rng = np.random.default_rng(0xB16B00B5 + seed)
        W = rand_weights(np_rng)
        activations = [rand_activation(np_rng) for _ in range(3)]
        p_minus1s = [DW - 1, 2, DW - 1]

        expected = [
            list(golden_bit_serial(W, a, p + 1)[0]) for a, p in zip(activations, p_minus1s)
        ]
        passes = list(zip(activations, p_minus1s))
        got = await _run_weight_stationary(dut, W, passes)
        assert got == expected, (
            f"seed {seed}: weight-stationary mismatch:\n got={got}\n exp={expected}"
        )


@cocotb.test(skip=gl)  # needs y_bit, no working GL path -- see _y_bit
async def test_second_fresh_weight_load_without_reset(dut):
    """Two INDEPENDENT fresh weight loads (start -> WRITE_W, not the `cont`
    reuse path) back to back, with NO hard reset between them -- only the FSM's
    own natural SHIFT_OUT -> IDLE -> (host pulses start again) return.

    This specifically targets weight_load.sv's wload_cnt, which has no
    per-state reset (only hard rst_n): control_fsm.sv's wshift_en stays
    asserted for one cycle longer than the ROWS*COLS shifts actually needed
    (the row_cnt==ROWS-1 && wfull transition-triggering cycle is still
    WRITE_W), so wload_cnt picks up one uncounted extra shift every complete
    WRITE_W session. If that phase offset isn't cleared before the next fresh
    weight load, the second load's column-bit mapping is off by one and W2
    gets corrupted -- while the FIRST load in any simulation always starts
    from a clean hard-reset wload_cnt=0, so every other test in this file is
    structurally incapable of catching this regardless of how many seeds they
    use. Any real host loading more than one weight matrix per power-up cycle
    depends on this working. Mirrors A07_dcim_top_tb.py's equivalent test."""
    np_rng = np.random.default_rng(0x5EC0D_BAD)
    p_minus1 = DW - 1
    await _start_up(dut)

    W1 = rand_weights(np_rng)
    a1 = rand_activation(np_rng)
    expected1, _trace = golden_bit_serial(W1, a1, DW)
    got1 = await _run_matvec(dut, W1, a1, p_minus1)
    assert got1 == list(expected1), (
        f"first load: matvec mismatch:\n got={got1}\n exp={list(expected1)}"
    )

    # Back in IDLE naturally (cont=0 was used above) -- no reset here.
    W2 = rand_weights(np_rng)
    a2 = rand_activation(np_rng)
    expected2, _trace = golden_bit_serial(W2, a2, DW)
    got2 = await _run_matvec(dut, W2, a2, p_minus1)
    assert got2 == list(expected2), (
        f"second load (no intervening reset): matvec mismatch:\n got={got2}\n exp={list(expected2)}\n"
        "If this fails, weight_load.sv's wload_cnt phase-shift (see this test's docstring) is real: "
        "the design cannot load a second weight matrix without a hard reset in between."
    )


@cocotb.test(skip=gl)  # needs y_bit, no working GL path -- see _y_bit
async def test_matvec_constrained_random_regression(dut):
    """Constrained-random regression over randomized operation sequences.
    Mirrors A07_dcim_top_tb.py's equivalent test."""
    np_rng = np.random.default_rng(int(os.getenv("DCIM_TB_CRV_SEED", "3735928559")))
    n_iters = int(os.getenv("DCIM_TB_CRV_ITERS", "20"))

    await _start_up(dut)

    for trial in range(n_iters):
        W = rand_weights(np_rng)
        n_passes = int(np_rng.integers(1, 5))
        passes = [
            (rand_activation(np_rng), int(np_rng.integers(0, DW)))
            for _ in range(n_passes)
        ]

        got_all = await _run_weight_stationary(dut, W, passes)

        for i, ((a, p_minus1), got) in enumerate(zip(passes, got_all)):
            expected, _trace = golden_bit_serial(W, a, p_minus1 + 1)
            assert got == list(expected), (
                f"trial {trial} pass {i}/{n_passes} (P={p_minus1 + 1}): "
                f"matvec mismatch:\n got={got}\n exp={list(expected)}"
            )

        if np_rng.random() < 0.3:
            await _start_up(dut)


def chip_top_smoke_runner():
    proj_path = Path(__file__).resolve().parent
    src_path = proj_path / "../src"

    if gl:
        # Post-synthesis netlist + gate-level cell models instead of RTL.
        # GL only runs test_start_sets_busy (see the skip=gl test decorators):
        # y_bit has no working GL path (optimized/renamed away in synthesis),
        # and bit-banging ~1300+ cycles through a full-design gate-level
        # netlist in iverilog would be far too slow for the matvec tests.
        sources = [
            proj_path / "../final/nl/chip_top.nl.v",
            pdk_root
            / pdk
            / "libs.ref"
            / scl
            / "verilog"
            / f"{scl}.v",
            proj_path / "../ip/sram_32x8_9T/vh/sram_32x8_9T.v",
            pdk_root / pdk / "libs.ref" / "gf180mcu_fd_io" / "verilog" / "gf180mcu_fd_io.v",
            pdk_root / pdk / "libs.ref" / "gf180mcu_fd_io" / "verilog" / "gf180mcu_ws_io.v",
            proj_path / "../ip/gf180mcu_ws_ip__id/vh/gf180mcu_ws_ip__id.v",
            proj_path / "../ip/gf180mcu_ws_ip__logo/vh/gf180mcu_ws_ip__logo.v",
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
            src_path / "chip_core.sv",
            src_path / "chip_top.sv",
            proj_path / "../ip/sram_32x8_9T/vh/sram_32x8_9T.v",
            pdk_root / pdk / "libs.ref" / "gf180mcu_fd_io" / "verilog" / "gf180mcu_fd_io.v",
            pdk_root / pdk / "libs.ref" / "gf180mcu_fd_io" / "verilog" / "gf180mcu_ws_io.v",
            proj_path / "../ip/gf180mcu_ws_ip__id/vh/gf180mcu_ws_ip__id.v",
            proj_path / "../ip/gf180mcu_ws_ip__logo/vh/gf180mcu_ws_ip__logo.v",
        ]
        defines = {f"SLOT_{slot.upper()}": True}

    runner = get_runner(sim)

    runner.build(
        sources=sources,
        hdl_toplevel="chip_top",
        defines=defines,
        includes=[src_path],
        build_args=["-g2012"] if sim == "icarus" else [],
        always=True,
        waves=True,
    )

    runner.test(
        hdl_toplevel="chip_top",
        test_module="chip_top_tb",
        waves=True,
    )


if __name__ == "__main__":
    chip_top_smoke_runner()
