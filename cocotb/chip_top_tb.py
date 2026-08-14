# SPDX-FileCopyrightText: 2026 Chipathon 2026 workshop
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer
from cocotb_tools.runner import get_runner


sim = os.getenv("SIM", "icarus")
pdk_root = Path(os.getenv("PDK_ROOT", Path("~/.ciel").expanduser()))
pdk = os.getenv("PDK", "gf180mcuD")
slot = os.getenv("SLOT", "workshop")


def _drive_inputs(dut, start=0, p_minus1=7):
    """Drive only the DCIM input pads and keep the rest high-Z."""
    width = len(dut.bidir_PAD)
    bus = ["z"] * width

    def set_bit(bit, value):
        bus[width - 1 - bit] = "1" if value else "0"

    # bit 0: a_bit, bit 1: w_bit (held low)
    set_bit(0, 0)
    set_bit(1, 0)

    # bit 2: start
    set_bit(2, start)

    # bit 3: cont (held low)
    set_bit(3, 0)

    # bits 4..6: P_minus1
    set_bit(4, (p_minus1 >> 0) & 1)
    set_bit(5, (p_minus1 >> 1) & 1)
    set_bit(6, (p_minus1 >> 2) & 1)

    dut.bidir_PAD.value = "".join(bus)


async def _start_up(dut):
    dut.input_PAD.value = 0
    _drive_inputs(dut, start=0, p_minus1=7)

    cocotb.start_soon(Clock(dut.clk_PAD, 20, unit="ns").start())

    dut.rst_n_PAD.value = 0
    await Timer(100, unit="ns")
    dut.rst_n_PAD.value = 1
    await ClockCycles(dut.clk_PAD, 2)


@cocotb.test()
async def test_start_sets_busy(dut):
    """Single-aspect smoke test: START pulse should drive BUSY high."""
    await _start_up(dut)

    assert int(dut.i_chip_core.busy.value) == 0, "BUSY should be low after reset"

    _drive_inputs(dut, start=1, p_minus1=7)
    await RisingEdge(dut.clk_PAD)
    _drive_inputs(dut, start=0, p_minus1=7)

    for _ in range(20):
        await RisingEdge(dut.clk_PAD)
        if int(dut.i_chip_core.busy.value) == 1:
            return

    raise AssertionError("START did not make BUSY go high within 20 cycles")


def chip_top_smoke_runner():
    proj_path = Path(__file__).resolve().parent
    src_path = proj_path / "../src"

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

    runner = get_runner(sim)

    runner.build(
        sources=sources,
        hdl_toplevel="chip_top",
        defines={f"SLOT_{slot.upper()}": True},
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
