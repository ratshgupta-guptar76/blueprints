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

import cocotb

ROWS = 32 # TODO: read from dut when tests are addded - do not hardcode.

# ---------- Golden Reference ----------
def golden_ref(addr: int, en: int) -> int:
    """Computes the golden reference output for the Row Decoder

    Behaviour:
        enabled: returns a signal with only the bit at the `addr` index set to `1`
        disabled: returs 0 (all wordlines de-asserted)

    Args:
        en (`int`) : Enable signal for Row Decoder
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

golden_tb()

