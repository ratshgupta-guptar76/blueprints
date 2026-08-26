# SPDX-FileCopyrightText: 2026 Chipathon 2026 workshop
# SPDX-License-Identifier: Apache-2.0

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
