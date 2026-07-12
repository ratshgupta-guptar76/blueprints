// ==================================================================================
// act_shift_chain.sv — 64-cell activation shift chain (single bank)
// ==================================================================================
// ROWS shift_reg cells cascaded into one (ROWS*DW)=512-bit chain, one cell per
// array row. Drives the broadcast bit-plane to the DCIM array. Two modes (c_en):
//
//   LOAD    (en=1, c_en=0): cells form one 512-bit shift register. Activations
//                           stream in serially on a_b through cell 0, propagate
//                           cell-to-cell via sr_connect_wire. Stream LSB-first per
//                           byte so each byte's bit0 lands in its cell's sr[0].
//
//   COMPUTE (en=1, c_en=1): each cell shifts toward LSB, zero-filling MSB. act_bp
//                           [i] = cell i's sr[0]. The full act_bp[ROWS-1:0] is one
//                           broadcast bit-plane, LSB-first over 8 cycles. MUST match
//                           golden_model trace order.
//
// Wiring:
//   sr_connect_wire[ROWS:0] — ROWS+1 nets. [0]=a_b (head), [i+1]=cell i serial_out,
//                             cell i serial_in=[i]. The +1 width gives clean head/
//                             tail with no [-1] or overrun.
//   tail_out = [ROWS]       — last cell's departing bit (load-time chain end).
//   act_bp[i] ← compute_bit — parallel plane tap, 1:1 row mapping, NO permutation
//                             (must match array row order + golden model).
//
// FSM CONSTRAINT: during the 8 compute cycles c_en MUST stay 1. A stray en&~c_en
// mid-compute injects a chain bit into a cell MSB instead of 0 -> corrupt plane.
//
// Single bank only. Ping-pong (2 banks + output mux, FSM swap select) wraps this
// later — not in this module.
// ==================================================================================


module act_shift_chain #(
    parameter int ROWS = dcim_pkg::ROWS,
    parameter int DW   = dcim_pkg::DW
) (
    input logic clk,
    input logic rst_n,

    input logic en,
    input logic a_b,
    input logic c_en,

    output logic [ROWS-1:0] act_bp,         // Activation bit-plane accessed to compute mat-vec mult
    output logic tail_out                   // Last serial out bit of the activation chain
);

    logic [ROWS:0] sr_connect_wire;

    assign sr_connect_wire[0] = a_b;
    assign tail_out           = sr_connect_wire[ROWS];

    genvar i;
    generate
        for (i = 0; i < ROWS; i++) begin : ACT_SHIFT_CHAIN
            shift_reg #(
                .DW(DW)
            ) ACT_SHIFT_REG (
                .clk(clk),
                .rst_n(rst_n),
                .en(en),
                .serial_in(sr_connect_wire[i]),
                .c_en(c_en),
                .compute_bit(act_bp[i]),
                .serial_out(sr_connect_wire[i+1])
            );
        end
    endgenerate

endmodule
