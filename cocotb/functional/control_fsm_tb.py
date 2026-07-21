# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : control_fsm_tb.py
# Author    : R. Gupta
# Date      : Jul-18-2026
# --------------------------------------------------------------------------------------
# DUT       : control_fsm.sv
# Type      : One-Hot FSM
# Framework : cocotb / Verilator
# 
# DESCRIPTION
# ***********
#   Datapath controller for the DCIM macro. A one-hot FSM sequences one matrix-vector
#   operation through six states, driving register-level control (weight load, act. 
#   stream-in, compute, output stream-out). Three counters track progress within these
#   states.
#   Reset is asynchronous.
# 
# SPECIFICATION
# *************
#   @ negedge rst_n:
#       state    = IDLE
#       load_cnt = 0
#       row_cnt  = 0
#       bp_cnt   = 0
#   @ posedge clk: next_state =>
#       IDLE -> WRITE_W, if start
#       WRITE_W -> WRITE_A, if row_cnt == ROWS-1 && wfull
#       WRITE_A -> COMPUTE, if load_cnt == DW*ROWS-1
#       COMPUTE -> DONE, if bp_cnt == P-1 (Pminus1)
#       DONE -> SHIFT_OUT       // Delay state
#       SHIFT_OUT -> cont ? WRITE_A : IDLE, if y_done
#       default: IDLE (one-hot failsafe)
#   @ posedge clk: counters =>
#       WRITE_W : row_cnt  <- wfull ? row_cnt + 1 : row_cnt
#       WRITE_A : load_cnt <- load_cnt + 1
#       COMPUTE : bp_cnt   <- bp_cnt + 1
#   @ posedge clk: outputs
#       busy = ~IDLE
#       done = DONE
#       comp_en = COMPUTE
#       a_en = WRITE_A or COMPUTE
#       w_en = WRITE_W and wfull
#       wshift_en = WRITE_W
#       row_addr = row_cnt
#       bp_idx = bp_cnt
#       clr = WRITE_A and (if load_cnt == DW*ROWS-1)
#       y_load = done
#       y_en = DONE or SHIFT_OUT
# 
# PARAMETERS
# **********
#   ROWS: # of weights per row (adopted from dcim_pkg::ROWS)
#   DW: data-width of activations (adopted from dcim_pkg::DW)
# 
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/control_fsm.sv
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# ======================================================================================

import cocotb

ROWS, DW = 32, 8 # TODO: read from dut when tests are addded - do not hardcode.
MAX_LOAD = DW*ROWS-1

# ---- enums ----
IDLE, WRITE_W, WRITE_A, COMPUTE, DONE, SHIFT_OUT = (
    0b000001, 0b000010, 0b000100, 0b001000, 0b010000, 0b100000
)

# ---------- Golden Reference ----------
def golden_ref(state: int,
               row_cnt: int, 
               load_cnt: int, 
               bp_cnt: int,
               start,
               cont,
               P_minus1,
               wfull,
               y_done
) -> tuple[dict[str, int], int, int, int, int]:
    """Computes the golden reference output for a one-hot FSM

    Behaviour:
        Outputs are combinationally driven by the CURRENT state and the counters. The state
        and counters are however registered and the outputs of the current state is referenced
        to as next_state. At reset all states and counters revert to 0.

    Args:
        state (int)    : current one-hot state
        row_cnt (int)  : weight-row counter (WRITE_W)
        load_cnt (int) : activation-bit counter (WRITE_A)
        bp_cnt (int)   : bit-plane counter (COMPUTE)
        start (int)    : IDLE -> WRITE_W trigger
        cont (int)     : SHIFT_OUT exit select (WRITE_A if 1 else IDLE)
        P_minus1 (int) : precision(P)-1; COMPUTE runs P_minus1+1 planes
        wfull (int)    : weight-row-assembled strobe (from weight_load)
        y_done (int)   : drain-complete strobe (from stream_out)

    Returns:
        tuple[dict[str, int], int, int, int, int]
            - comb_outputs  : dict of all 11 combinational outputs THIS cycle
            - next_state    : one-hot state after clk posedge
            - next_row_cnt  : row_cnt after clk posedge
            - next_load_cnt : load_cnt after clk posedge
            - next_bp_cnt   : bp_cnt after clk posedge
    """

    # Variables
    comb_outputs  : dict[str, int]
    next_state    : int
    next_row_cnt  : int
    next_load_cnt : int
    next_bp_cnt   : int
    out : tuple[dict, int, int, int, int]

    comb_outputs = {
        "busy"      : int(state != IDLE),
        "done"      : int(state == DONE),
        "w_en"      : int(state == WRITE_W and wfull),
        "wshift_en" : int(state == WRITE_W),
        "row_addr"  : row_cnt,
        "a_en"      : int(state in (WRITE_A, COMPUTE)),
        "comp_en"   : int(state == COMPUTE),
        "clr"       : int(state == WRITE_A and load_cnt == MAX_LOAD),
        "bp_idx"    : bp_cnt,
        "y_load"    : int(state == DONE),
        "y_en"      : int(state in (DONE, SHIFT_OUT))
    }

    if   state == IDLE      : next_state = WRITE_W if start else IDLE
    elif state == WRITE_W   : next_state = WRITE_A if (row_cnt == ROWS-1 and wfull) else WRITE_W
    elif state == WRITE_A   : next_state = COMPUTE if (load_cnt == MAX_LOAD) else WRITE_A
    elif state == COMPUTE   : next_state = DONE if (bp_cnt == P_minus1) else COMPUTE
    elif state == DONE      : next_state = SHIFT_OUT
    elif state == SHIFT_OUT : next_state = (WRITE_A if cont else IDLE) if y_done else SHIFT_OUT
    else: next_state = IDLE # default state (one-hot failsafe)

    # Next Counters
    next_row_cnt = (row_cnt + 1) if (state == WRITE_W and wfull) \
                                 else row_cnt if state == WRITE_W \
                                 else 0

    next_load_cnt = (load_cnt + 1) if state == WRITE_A \
                                   else 0

    next_bp_cnt  = (bp_cnt + 1) if state == COMPUTE \
                                else 0


    out = (comb_outputs, next_state, next_row_cnt, next_load_cnt, next_bp_cnt)
    return out

def golden_tb():
    s, r, l, b = IDLE, 0, 0, 0
    P = 1                                   # 2 planes

    def step(start=0, cont=0, wfull=0, y_done=0):
        nonlocal s, r, l, b
        out, ns, nr, nl, nb = golden_ref(s, r, l, b, start, cont, P, wfull, y_done)
        s, r, l, b = ns, nr, nl, nb
        return out

    # IDLE -> WRITE_W
    step(start=1); assert s == WRITE_W

    # WRITE_W: row_cnt must HOLD between wfull pulses (regression guard)
    for row in range(ROWS):
        step(wfull=0); assert s == WRITE_W
        step(wfull=0); assert r == row, f"row_cnt cleared: {r} != {row}"
        step(wfull=1)
    assert s == WRITE_A

    # WRITE_A: clr on the last cycle only
    for i in range(MAX_LOAD + 1):
        o = step()
        assert o["clr"] == (1 if i == MAX_LOAD else 0), f"clr wrong at i={i}"
    assert s == COMPUTE

    # COMPUTE: clr must NOT overlap comp_en
    for p in range(P + 1):
        o = step(); assert o["clr"] == 0 and o["comp_en"] == 1
    assert s == DONE

    # DONE: y_load AND y_en (stream_out capture)
    o = step(); assert o["y_load"] == 1 and o["y_en"] == 1
    assert s == SHIFT_OUT

    # SHIFT_OUT: cont=1 loops to WRITE_A (weight-stationary)
    step(y_done=0)
    step(cont=1, y_done=1)
    assert s == WRITE_A, f"cont=1 should loop to WRITE_A, got {s:#08b}"

    print("control_fsm golden_ref self-check passed")

golden_tb()

