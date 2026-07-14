module dcim_top #(
    parameter int ROWS      = dcim_pkg::ROWS,
    parameter int COLS      = dcim_pkg::COLS,
    parameter int N_WEIGHTS = dcim_pkg::N_WEIGHTS,
    parameter int DW        = dcim_pkg::DW,
    parameter int ACC_WIDTH = dcim_pkg::ACC_WIDTH,
    parameter bit A_SIGN    = dcim_pkg::A_SIGN,
    parameter bit W_SIGN    = dcim_pkg::W_SIGN
) (
    input logic clk,
    input logic rst_n,

    input logic                  a_bit,
    input logic                  w_bit,
    input logic                  start,
    input logic                  cont,
    input logic [$clog2(DW)-1:0] P_minus1,
    
    output logic y_bit,
    output logic done,
    output logic busy
);
// Control signals - FSM
logic a_en;
logic comp_en;
logic w_en;
logic wshift_en;
logic clr;
logic y_en;
logic y_load;
logic wfull;
logic y_done;

// Registers
logic [$clog2(ROWS)-1:0] row_addr;
logic [$clog2(DW)-1:0]   bp_idx;
logic [ROWS-1:0]         act_bp;
logic [COLS-1:0]         w_buf;

// AND-Mult Matrix
logic [ROWS-1:0][COLS-1:0]           pp;

// Adder Tree Output
logic [COLS-1:0][$clog2(ROWS+1)-1:0] sum;

// Output Vector
logic [N_WEIGHTS-1:0][ACC_WIDTH-1:0] y;

// #######################
//  MODULE INSTANTIATIONS
// #######################

// act_shift_chain.sv
act_shift_chain #(
    .ROWS(ROWS),
    .DW  (DW)
) ACTIVATION_SHIFT_CHAIN (
    .clk(clk),
    .rst_n(rst_n),
    .en(a_en),
    .a_b(a_bit),
    .c_en(comp_en),

    .act_bp(act_bp),
    .tail_out()     // Modify Code to remove this signal safely.
);

// adder_tree.sv
adder_tree #(
    .ROWS(ROWS),
    .COLS(COLS)
) ADDER_TREE (
    .pp(pp),

    .sum(sum)
);

// control_fsm.sv
control_fsm #(
    .ROWS(ROWS),
    .DW  (DW)
) CONTROL_FSM (
    .clk       (clk),
    .rst_n     (rst_n),
// Input Signals
    .start     (start),
    .cont      (cont),
    .P_minus1  (P_minus1),
    .wfull     (wfull),
    .y_done    (y_done),
// Output signals
    .busy      (busy),
    .done      (done),
    .w_en      (w_en),
    .wshift_en (wshift_en),
    .row_addr  (row_addr),
    .a_en      (a_en),
    .clr       (clr),
    .comp_en   (comp_en),
    .bp_idx    (bp_idx),
    .y_load    (y_load),
    .y_en      (y_en)
);

// dcim_array
dcim_array #(
    .ROWS(ROWS),
    .COLS(COLS)
) DCIM_ARRAY (
    .clk(clk),
// Input Signals
    .w_en(w_en),
    .row_addr(row_addr),
    .w_buf(w_buf),
    .act_bp(act_bp),
// Output Signals
    .pp(pp)
);

// shift_accum.sv
shift_accum #(
    .ROWS(ROWS),
    .COLS(COLS),
    .N_WEIGHTS(N_WEIGHTS),
    .DW(DW),
    .ACC_WIDTH(ACC_WIDTH),
    .A_SIGN(A_SIGN),
    .W_SIGN(W_SIGN)
) SHIFT_ACCUMULATOR (
    .clk(clk),
    .rst_n(rst_n),
    .en(comp_en),
    .clr(clr),
    .bp_idx(bp_idx),
    .sum(sum),

    .y(y)
);

// stream_out.sv
stream_out #(
    .N_WEIGHTS(N_WEIGHTS),
    .ACC_WIDTH(ACC_WIDTH)
) SERIAL_STREAM_OUTPUT (
    .clk(clk),
    .rst_n(rst_n),
    .en(y_en),
    .load(y_load),
    .acc(y),

    .done(y_done),
    .y_bit(y_bit)
);

// weight_load.sv
weight_load #(
    .COLS(COLS)
) SERIAL_WEIGHT_LOAD_TO_BUF (
    .clk(clk),
    .rst_n(rst_n),
    .en(wshift_en),
    .w_bit(w_bit),
    
    .wfull(wfull),
    .w_buf(w_buf)
);

endmodule
