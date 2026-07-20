// ==================================================================================
// control_fsm.sv — DCIM datapath controller (single-bank, weight-stationary)
// ==================================================================================
// One-hot FSM + 3 counters. Drives register-level datapath control; pin-level
// serialization (w_bit assembly, y_bit drain) lives in front-end modules, not here.
//
// STATES: IDLE -> WRITE_W -> WRITE_A -> COMPUTE -> DONE -> SHIFT_OUT
//   IDLE     : wait for start.
//   WRITE_W  : load 64 weight rows. row_cnt advances on wfull (one assembled row
//              from the weight front-end), NOT every cycle. Exit at row 63 & wfull.
//   WRITE_A  : stream 512 activation bits (bit-serial, zero-padded to DW). load_cnt
//              0..511 every cycle. clr pulses on the last cycle (511) -> accumulators
//              zeroed entering COMPUTE. Exit at 511.
//   COMPUTE  : run P bit-planes (P = P_minus1+1). bp_cnt 0..P_minus1. comp_en=1 each
//              plane -> accumulate. a_en=1, chain in compute mode. Exit at P_minus1.
//   DONE     : y valid, pulse y_load (capture into stream_out). 1 cycle -> SHIFT_OUT.
//   SHIFT_OUT: y_en=1, drain 176 bits serially. Exit on y_done: cont? WRITE_A : IDLE.
//              cont sampled in SHIFT_OUT (at y_done), not DONE — host holds cont
//              through drain.
//
// WEIGHT-STATIONARY: cont loops SHIFT_OUT->WRITE_A, skipping WRITE_W. Weights reload
//   only via IDLE->WRITE_W on a fresh start. Each vector re-clears via WRITE_A's clr.
//
// clr TIMING: clr = (WRITE_A && load_cnt==511) — one cycle BEFORE COMPUTE, not during.
//   MUST NOT overlap comp_en (COMPUTE) or plane 0 would clear instead of accumulate
//   (drops LSB plane). clr commits on the same edge as the WRITE_A->COMPUTE transition.
//
// COUNTERS: clear-then-override each cycle (reset when not in their state) — safe for
//   the cont loop (no IDLE pass-through). RW=6, LW=9 (holds 511), PW=3.
//
// P_minus1: precision zero-indexed (0->1bit .. 7->8bit). Terminal bp_cnt==P_minus1.
//   Never underflows (no P-1).
//
// NOTE (base-model coupling): comp_en (shift_accum .en) and the chain compute-mode
//   are both state==COMPUTE. Pipelining the adder tree SPLITS them (accumulator
//   captures later than chain mode-switch) — re-separate at STA.
//
// Interfaces: wfull from weight_load, y_done from stream_out; drives y_load/y_en to
// stream_out. Wired at chip_core.
// ==================================================================================

module control_fsm #(
    parameter int ROWS = dcim_pkg::ROWS,
    parameter int DW   = dcim_pkg::DW
) (
    input logic clk,
    input logic rst_n,

    input logic start,
    input logic cont,
    input logic [$clog2(DW)-1:0] P_minus1,     // Precision is zero-indexed, P= 1->0, P= 2->1
    input logic wfull,
    input logic y_done,

    output logic busy,
    output logic done,
    output logic w_en,
    output logic wshift_en,
    output logic [$clog2(ROWS)-1:0] row_addr,
    output logic a_en,
    output logic clr,
    output logic comp_en,
    output logic [$clog2(DW)-1:0] bp_idx,
    output logic y_load,
    output logic y_en
);

    localparam int RW = $clog2(ROWS);
    localparam int LW = $clog2(DW*ROWS);
    localparam int PW = $clog2(DW);

    // State enum
    typedef enum logic[5:0] { 
        IDLE      = 6'b000001,
        WRITE_W   = 6'b000010,
        WRITE_A   = 6'b000100,
        COMPUTE   = 6'b001000,
        DONE      = 6'b010000,
        SHIFT_OUT = 6'b100000
     } state_t;

    state_t state, next_state;

    // Counters
    logic [RW-1:0] row_cnt;
    logic [LW-1:0] load_cnt;
    logic [PW-1:0] bp_cnt;

    always_ff @(posedge clk or negedge rst_n) begin : STATE_REG
        if (~rst_n) begin
            state <= IDLE;
        end else begin
            state <= next_state;
        end
    end

    always_comb begin : STATE_LOGIC
        next_state = state;         // Default for when the next state condition is not met

        case (state)
            IDLE: begin
                if (start)
                    next_state = WRITE_W;
            end

            WRITE_W: begin
                if (row_cnt == unsigned'(RW'(ROWS-1)) && wfull)
                    next_state = WRITE_A;
            end

            WRITE_A: begin
                if (load_cnt == unsigned'(LW'(DW*ROWS-1)))
                    next_state = COMPUTE;
            end

            COMPUTE: begin
                if (bp_cnt == P_minus1) 
                    next_state = DONE;
            end

            DONE: begin
                next_state = SHIFT_OUT;
            end

            SHIFT_OUT: begin
                if (y_done)
                    next_state = cont ? WRITE_A
                                      : IDLE;
            end

            default: begin : ONE_HOT_FAILSAFE       // case for when illegal state occurs.
                next_state = IDLE;      // restart if one-hot bit error
            end
        endcase
    end

    always_ff @(posedge clk or negedge rst_n) begin : STATE_COUNTERS
        if (~rst_n) begin
            row_cnt  <= '0;
            load_cnt <= '0;
            bp_cnt   <= '0; 
        end else begin
            row_cnt  <= '0;
            load_cnt <= '0;
            bp_cnt   <= '0;

            if (state == WRITE_W)
                row_cnt <= wfull ? row_cnt + unsigned'(RW'(1))
                                 : '0;
            
            if (state == WRITE_A)
                load_cnt <= load_cnt + unsigned'(LW'(1));

            if (state == COMPUTE)
                bp_cnt <= bp_cnt + unsigned'(PW'(1));
        end
    end

    always_comb begin : STATE_OUTPUTS
        busy      = (state != IDLE);
        done      = (state == DONE);
        w_en      = (state == WRITE_W) && wfull;
        wshift_en = (state == WRITE_W);
        row_addr  = row_cnt;
        a_en      = (state == WRITE_A) || (state == COMPUTE);
        comp_en   = (state == COMPUTE);
        clr       = (state == WRITE_A) && (load_cnt == unsigned'(LW'(DW*ROWS-1)));
        bp_idx    = bp_cnt;
        y_load    = (state == DONE);
        y_en      = (state == SHIFT_OUT) || (state == DONE);
    end

endmodule
