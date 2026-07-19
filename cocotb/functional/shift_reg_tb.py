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
# ======================================================================================

import cocotb

DW = 8 # TODO: read from dut when tests are addded - do not hardcode.

# ---------- Golden Reference ----------
def golden_ref(sr: int, en: int, c_en: int, serial_in: int) -> tuple[int, int]:
    """Computes the golden reference output for a single Shift Register

    Behaviour:
       One clock step of a DW-bit LSB shift register. Stateful; sr is passed in and the post-edge state returned; thread it back each cycle.


    Args:
        sr (int) : Current Shift Register
        en (int) : Enable signal for Shift Register
        c_en (int) : Compute enable signal for Shift Register (COMPUTE mode)
        serial_in (int) : input bit into MSB

    Returns:
        tuple[int, int]
            - sr_out  : sr[0] this cycle (compute_bit = serial_out), sampled BEFORE the shift.
            - next_sr : the full DW-bit register contents AFTER the clock edge, sr shifted one place toward the LSB, with the MSB filled per mode (serial_in in LOAD, 0 in COMPUTE, unchanged if en=0). Thread this back in as `sr` on the next call.
    """
    
    # Variables
    sr_out  : int
    next_sr : int
    out     : tuple[int, int]

    if en == 0:
        next_sr = sr
    else:
        if c_en == 0:
            next_sr = (serial_in << (DW-1)) | (sr >> 1)
        else:
            next_sr = (sr >> 1)

    sr_out  = sr & 1
    next_sr &= (1 << DW) - 1    # truncate next_sr to DW, so that python code behaves like the hardware

    out = (sr_out, next_sr)
    return out

def golden_tb():
    # LOAD 0b10110001 LSB-first over DW cycles, then COMPUTE it out
    sr = 0
    bits_in = [1,0,0,0,1,1,0,1]          # LSB first
    for b in bits_in:
        _, sr = golden_ref(sr, en=1, c_en=0, serial_in=b)
    assert sr == 0b10110001, f"loaded {sr:#010b}, expected 0b10110001"

    # COMPUTE drains LSB-first
    out_seq = []
    for _ in range(DW):
        o, sr = golden_ref(sr, en=1, c_en=1, serial_in=0)
        out_seq.append(o)
    assert out_seq == bits_in, f"drained {out_seq}, expected {bits_in}"
    print("shift_reg golden_ref self-check passed")
    return 0

golden_tb()

