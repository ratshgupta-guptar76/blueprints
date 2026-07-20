# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : weight_load_tb.py
# Author    : R. Gupta
# Date      : Jul-19-2026
# --------------------------------------------------------------------------------------
# DUT       : weight_load.sv
# Type      : Sequential, SIPO, async reset
# Latency   : wfull asserts 1 cycle after w_buf is full (final w_bit is registered) 
# Framework : cocotb / Verilator
# 
# DESCRIPTION
# ***********
#   Serial-in Parallel-out shift register and weight-row assembler. Shifts COLS serial
#   w_bit(s) into a parallel w_buf - buffer register. w_bit enters the MSB, shifting
#   towards the LSB. It pulses w_full for exactly one cycle when a full row is
#   assembled. wfull is registered and asserts the cycle AFTER the final bit lands,
#   coincident with a fully-valid w_buf. Forced low whenever en is low.
#   Reset is asynchronous.
# 
# SPECIFICATION
# *************
#   @ negedge rst_n
#       w_buf = '0
#   @ posedge clk && en == 1:
#       w_buf     <- {w_bit, w_buf[COLS-1:1]}                   (MSB fill, LSB shift)
#       wload_cnt <- (wload_cnt == COLS-1) ? 0 : wload_cnt + 1
#       wfull     <- (wload_cnt == COLS-1) ? 1 : 0              (registered)
#   @ posedge clk && en == 0:
#       w_buf     <- w_buf
#       wload_cnt <- wload_cnt
#       wfull     <- 0
#   Output (comb.)  => w_buf outputs are connected parallely
#   Ordering: w_bit shifts into MSB and towards the LSB.
# 
# PARAMETERS
# **********
#   COLS: # of weight-bits a.k.a. depth of weight_load (adopted from dcim_pkg::COLS)
# 
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/weight_load.sv
# 
# LIMITATIONS:  en held high for full row (FSM: wshift_en = WRITE_W).
#               Mid-row de-assertion unreachable; not exercised.
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# ======================================================================================

import cocotb

COLS = 32  # TODO: read from dut when tests are addded - do not hardcode.

# ---------- Golden Reference ----------
def golden_ref(w_buf: int, en: int, wload_cnt: int, w_bit: int) -> tuple[int, int, int, int]:
    """Golden reference output — Weight Load Register

    Behaviour:
       w_buf and wload_cnt are registers; wfull is also a registered flag so
       it is returned as a next-state (current status visible the next cycle)

    Args:
        w_buf (int)     : Current Weight Load Buffer Register
        en (int)        : Enable signal for Weight Load buffer
        wload_cnt (int) : Current wload_cnt (0...COLS-1)
        w_bit (int)     : input weight bit into MSB of w_buf

    Returns:
        tuple[int, int, int, int]
            - w_buf_out      : w_buf THIS cycle (comb. parallel output)
            - next_wfull     : next state of wfull flag, since wfull is registered.
            - next_wload_cnt : next state of the wload_cnt register after this clk edge
            - next_w_buf     : next state of the w_buf shift-register after w_bit is shifted into the MSB
    """

    # Variables
    next_wfull     : int
    next_wload_cnt : int
    next_w_buf     : int
    out : tuple[int, int, int, int]

    w_buf_out = w_buf

    if en == 1:
        next_w_buf     = ((w_bit << (COLS-1)) | (w_buf >> 1))
        next_wload_cnt = 0 if wload_cnt == COLS-1 else wload_cnt + 1
        next_wfull     = 1 if wload_cnt == COLS-1 else 0
    else:
        next_w_buf     = w_buf
        next_wload_cnt = wload_cnt
        next_wfull     = 0

    next_w_buf &= (1 << COLS) - 1
    out = (w_buf_out, next_wfull, next_wload_cnt, next_w_buf)
    return out

def golden_tb():
    C = 4                          # tiny COLS for a hand-checkable trace
    global COLS; COLS = 4
    w_buf = cnt = 0
    wfull_seen = []
    for i in range(C + 1):         # one extra cycle to see the registered pulse
        _, nf, ncnt, nbuf = golden_ref(w_buf, 1, cnt, 1)
        wfull_seen.append(nf)
        w_buf, cnt = nbuf, ncnt
    # cnt hits COLS-1 on cycle C-1 -> wfull_next high that call -> visible cycle C
    expected = [0, 0, 0, 1, 0]
    assert wfull_seen == expected, (
        f"wfull timing mismatch:\n"
        f"  got      {wfull_seen}\n"
        f"  expected {expected}"
    )
    COLS = 32
    print("weight_load golden_ref self-check passed")

golden_tb()

