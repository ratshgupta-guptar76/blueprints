# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : stream_out_tb.py
# Author    : R. Gupta
# Date      : Jul-19-2026
# --------------------------------------------------------------------------------------
# DUT       : stream_out.sv
# Type      : Sequential, PISO, async reset
# Latency   : done asserts 1 cycle after the final output bit drains (registered)
# Framework : cocotb / Verilator
# 
# DESCRIPTION
# ***********
#   Parallel-in Serial-out shift register and output-bit streamer. Captures the packed
#   accumulator vector and shifts it out one bit per cycle on y_bit. The done signal is
#   asserted once the entire output drain is completed.
#   Reset is asynchronous.
# 
# SPECIFICATION
# *************
#   @ negedge rst_n
#       piso    = '0
#       counter = '0
#       done    =  0
#   @ posedge clk && en == 1, load == 0:
#       piso    = {1'b0, piso[TOT-1:1]}
#       counter = counter + 1
#       done    = (counter == TOT-1) ? 1 : 0
#   @ posedge clk && en == 1, load == 1:
#       piso    = acc
#       counter = '0
#       done    =  0
#   @ posedge clk && en == 0:
#       piso    = piso
#       counter = counter
#       done    = done
#   Output (comb.)  => y_bit = piso[0]
#   Ordering: y_bit shifts out LSB first and then MSB.
# 
# PARAMETERS
# **********
#   N_WEIGHTS: # of weights in each row (adopted from dcim_pkg::N_WEIGHTS)
#   ACC_WIDTH: bit-width of one accumulator (adopted from dcim_pkg::ACC_WIDTH)
# 
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/stream_out.sv
# 
# LIMITATIONS:  en is the master enable. Nothing moves unless en is asserted. Stream
#               requires en & load.
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# ======================================================================================

import cocotb

N_WEIGHTS, ACC_WIDTH = 4, 21  # TODO: read from dut when tests are addded - do not hardcode.
TOT = N_WEIGHTS*ACC_WIDTH

# ---------- Golden Reference ----------
def golden_ref(piso: int, counter: int, done: int, en: int, load: int, acc: int) -> tuple[int, int, int, int]:
    """Golden reference output — Stream Out Register

    Behaviour:
       piso, counter, and done are registered. done is a registered flag, so it is returned
       as next-state. en is the master enable.. with en low, all states hold.

    Args:
        piso (int)    : Current PISO stream-out Register
        counter (int) : current stream-out counter
        done (int)    : current done flag
        en (int)      : Enable signal for Stream Out buffer
        load (int)    : Capture enable flag
        acc (int)     : packed accumulator vector

    Returns:
        tuple[int, int, int, int]
            - y_bit        : piso[0] in THIS cycle (comb. output)
            - next_done    : done latching this clk edge (high one cycle after when counter == TOT-1)
            - next_piso    : PISO contents after the clk
            - next_counter : stream-out counter after the clk edge
    """

    # Variables
    y_bit        : int
    next_done    : int
    next_piso    : int
    next_counter : int
    out : tuple[int, int, int, int]

    y_bit = piso & 1
    if en == 1:
        if load == 1:
            next_piso    = acc
            next_counter = 0
            next_done    = 0
        else:
            next_piso    = piso >> 1
            next_counter = counter + 1
            next_done    = 1 if counter == TOT-1 else 0
    else:
        next_piso    = piso
        next_counter = counter
        next_done    = done

    next_piso &= (1 << TOT) - 1
    out = (y_bit, next_done, next_counter, next_piso)
    return out

def golden_tb() -> None:
    global TOT
    TOT = 6                       # 2 lanes x 3 bits, hand-checkable
    acc = 0b101_011               # lane1=101, lane0=011 (low bits = lane0)
    expected_bits = [1, 1, 0, 1, 0, 1]   # lane0 LSB-first, then lane1

    piso = counter = done = 0
    # capture requires en & load (master-enable gating)
    _, done, counter, piso = golden_ref(piso, counter, done, en=1, load=1, acc=acc)

    drained, done_seen = [], []
    for _ in range(TOT + 1):      # +1 to see registered done
        y, ndone, ncounter, npiso = golden_ref(piso, counter, done, en=1, load=0, acc=0)
        drained.append(y)
        done_seen.append(ndone)
        piso, counter, done = npiso, ncounter, ndone

    assert drained[:TOT] == expected_bits, (
        f"drain order:\n  got      {drained[:TOT]}\n  expected {expected_bits}")
    expected_done = [0, 0, 0, 0, 0, 1, 0]
    assert done_seen == expected_done, (
        f"done timing:\n  got      {done_seen}\n  expected {expected_done}")

    TOT = N_WEIGHTS * ACC_WIDTH
    print("stream_out golden_ref self-check passed")

golden_tb()

