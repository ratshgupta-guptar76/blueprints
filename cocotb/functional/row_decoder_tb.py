# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : row_decoder_tb.py
# Author    : R. Gupta
# Date      : Jul-18-2026
# --------------------------------------------------------------------------------------
# DUT       : row_decoder.sv
# Type      : Combinational
# Framework : cocotb / Verilator
# 
# DESCRIPTION
# ***********
#   Binary to one-hot wordline decoder for the DCIM weight-write path. A `ROWS`-wide 
#   one-hot wl selects the row driven during a weight write; the enable gates the 
#   entire decode so that no wordline asserts when WRITE is inactive.
# 
# SPECIFICATION
# *************
#   en == 1 => wl[addr] = 1, the rest are 0
#   en == 0 => wl[*]    = 0, all bits are 0
# 
# PARAMETERS
# **********
#   ROWS: number of wordlines (adopted from dcim_pkg::ROWS - must match)
# 
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/row_decoder.sv
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# ======================================================================================

import os
import cocotb
from cocotb.triggers import Timer
from cocotb.types import LogicArray

ROWS : int = 32     # Default value for golden_tb(). 
                    # Value overwritten during actual testing.

# ---------- Golden Reference ----------
def golden_ref(addr: int, en: int) -> int:
    """Computes the golden reference output for the Row Decoder

    Behaviour:
        enabled: returns a signal with only the bit at the `addr` index set to `1`
        disabled: returs 0 (all wordlines de-asserted)

    Args:
        en (`int`)      : Enable signal for Row Decoder
        addr (`int`)    : Binary row address input to decode

    Returns:
        out (`int`) : The one-hot wordline (wl) decoded bit-vector representation
    
    Raises:
        AssertionError : If `addr` is less than 0 or greater than or equal to `ROWS`
    """

    if en == 0:
        return 0
    assert 0 <= addr < ROWS, f"`addr` {addr} out of range [0,{ROWS})"
    return 1 << addr

def golden_tb():
    assert golden_ref(5, 1) == 0b100000
    assert golden_ref(5, 0) == 0b000000
    assert golden_ref(0, 1) == 0b000001
    print("golden_ref self-check passed")
    return 0

@cocotb.test()
async def test_exhaustive(dut) -> None:
    """All ROWS addresses x {en=0,1} — full input space, proof-equivalent."""
    for en in (0, 1):
        for addr in range(ROWS):
            dut.en.value = en
            dut.addr.value = addr
            await Timer(1, "ns")                    # combinational settle

            wl = int(dut.wl.value)
            exp = golden_ref(addr, en)

            # property: one-hot when enabled, zero-hot when not
            n = bin(wl).count("1")
            assert n == (1 if en else 0), \
                f"en={en} addr={addr}: wl={wl:#x} has {n} bits set"
            assert wl == exp, \
                f"en={en} addr={addr}: got {wl:#x}, expected {exp:#x}"

@cocotb.test()
async def test_en_low_no_write(dut) -> None:
    """Safety: en=0 silences wl for every addr — no stray SRAM write."""
    ROWS = int(dut.ROWS.value)
    for addr in range(ROWS):
        dut.en.value = 0
        dut.addr.value = addr
        await Timer(1, "ns")
        assert int(dut.wl.value) == 0, \
            f"en=0 addr={addr}: wl={int(dut.wl.value):#x} — stray wordline"

@cocotb.test()
async def test_no_latch(dut):
    """wl must fully re-evaluate each time — no held bits from prior addresses.

    Without the `wl = '0` default in the RTL, wl[addr]=1'b1 infers a latch and
    old bits persist. Walk consecutive addresses and confirm only the current
    one is set.
    """
    prev = None
    for addr in (5, 7, 5, 0, ROWS - 1, 12):
        dut.en.value = 1
        dut.addr.value = addr
        await Timer(1, "ns")

        wl = int(dut.wl.value)
        assert wl == (1 << addr), \
            f"addr={addr} (prev={prev}): got {wl:#x}, expected {1 << addr:#x} — stale bits held?"
        prev = addr

    # en 1->0 must clear immediately, not hold the last decode
    dut.en.value = 0
    await Timer(1, "ns")
    assert int(dut.wl.value) == 0, \
        f"en 1->0 did not clear wl: {int(dut.wl.value):#x}"

@cocotb.test(skip=(os.environ.get("SIM") != "icarus"))
async def test_x_prop(dut):
    """4-state only: X on addr/en must not silently produce a plausible wl."""
    ROWS = int(dut.ROWS.value)
    RW = (ROWS-1).bit_length()
    dut.en.value = 1
    dut.addr.value = LogicArray("x" * RW)
    await Timer(1, "ns")
    wl = dut.wl.value
    assert not wl.is_resolvable or int(wl) == 0, \
        f"X addr produced a resolved wordline {wl} — X was masked"
