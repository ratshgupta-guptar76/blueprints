// SPDX-FileCopyrightText: 2026 Chipathon 2026 workshop
// SPDX-License-Identifier: Apache-2.0
//
// Minimal chip_core for the Chipathon 2026 workshop padring slot.
// The emphasis of this slot is the padring itself (60 analog + 20
// bidir + 4/4 power + clk/rst_n); the core is intentionally trivial:
// a free-running counter whose state drives the 20 bidir pads. The
// 60 analog pads are routed straight through to analog[] and stay
// unconnected at the core level (the intent is that a downstream
// design wires them to custom analog IP later).

`default_nettype none

module chip_core #(
    parameter NUM_INPUT_PADS,
    parameter NUM_BIDIR_PADS,
    parameter NUM_ANALOG_PADS
    )(
    `ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
    `endif

    input  wire clk,       // clock
    input  wire rst_n,     // reset (active low)

    input  wire [NUM_INPUT_PADS-1:0] input_in,   // Input value
    output wire [NUM_INPUT_PADS-1:0] input_pu,   // Pull-up
    output wire [NUM_INPUT_PADS-1:0] input_pd,   // Pull-down

    input  wire [NUM_BIDIR_PADS-1:0] bidir_in,   // Input value
    output wire [NUM_BIDIR_PADS-1:0] bidir_out,  // Output value
    output wire [NUM_BIDIR_PADS-1:0] bidir_oe,   // Output enable
    output wire [NUM_BIDIR_PADS-1:0] bidir_cs,   // Input type (0=CMOS, 1=Schmitt)
    output wire [NUM_BIDIR_PADS-1:0] bidir_sl,   // Slew rate (0=fast, 1=slow)
    output wire [NUM_BIDIR_PADS-1:0] bidir_ie,   // Input enable
    output wire [NUM_BIDIR_PADS-1:0] bidir_pu,   // Pull-up
    output wire [NUM_BIDIR_PADS-1:0] bidir_pd,   // Pull-down

    inout  wire [NUM_ANALOG_PADS-1:0] analog    // Analog
);

    // Define localparams and pad map
    // Inputs
    localparam int PAD_A_BIT     = 0;
    localparam int PAD_W_BIT     = 1;
    localparam int PAD_START     = 2;
    localparam int PAD_CONT      = 3;
    localparam int PAD_PMINUS1_0 = 4;
    localparam int PAD_PMINUS1_1 = 5;
    localparam int PAD_PMINUS1_2 = 6;
    // Outputs
    localparam int PAD_Y_BIT   = 7;
    localparam int PAD_DONE    = 8;
    localparam int PAD_BUSY    = 9;

    localparam logic [NUM_BIDIR_PADS-1:0] OE_MASK = 
        (NUM_BIDIR_PADS'(1) << PAD_Y_BIT)
        | (NUM_BIDIR_PADS'(1) << PAD_DONE)
        | (NUM_BIDIR_PADS'(1) << PAD_BUSY);

    localparam logic [NUM_BIDIR_PADS-1:0] IE_MASK = 
        (NUM_BIDIR_PADS'(1) << PAD_A_BIT)
        | (NUM_BIDIR_PADS'(1) << PAD_W_BIT)
        | (NUM_BIDIR_PADS'(1) << PAD_START)
        | (NUM_BIDIR_PADS'(1) << PAD_CONT)
        | (NUM_BIDIR_PADS'(1) << PAD_PMINUS1_0)
        | (NUM_BIDIR_PADS'(1) << PAD_PMINUS1_1)
        | (NUM_BIDIR_PADS'(1) << PAD_PMINUS1_2);

    // Disable pull-up and pull-down on any discrete input pads.
    assign input_pu = '0;
    assign input_pd = '0;

    // Drive the bidir pads as outputs (CMOS buffer, fast slew).
    assign bidir_oe = OE_MASK;
    assign bidir_cs = '0;
    assign bidir_sl = '0;
    assign bidir_ie = IE_MASK;
    assign bidir_pu = '0;
    assign bidir_pd = ~(OE_MASK|IE_MASK);   // Pull down unused pads

    // Keep synthesis from optimising bidir_in / input_in away.
    logic _unused_inp;
    assign _unused_inp = |input_in;

    wire a_bit, w_bit, start, cont;
    wire [2:0] P_minus1;
    wire y_bit, done, busy;

    // Drive input wires by pads
    assign a_bit    = bidir_in[PAD_A_BIT];
    assign w_bit    = bidir_in[PAD_W_BIT];
    assign start    = bidir_in[PAD_START];
    assign cont     = bidir_in[PAD_CONT];
    assign P_minus1 = {bidir_in[PAD_PMINUS1_2], bidir_in[PAD_PMINUS1_1], bidir_in[PAD_PMINUS1_0]};


    // DCIM macro - [Team A7] Blueprints
    dcim_top #(
        .ROWS     (dcim_pkg::ROWS),
        .COLS     (dcim_pkg::COLS),
        .N_WEIGHTS(dcim_pkg::N_WEIGHTS),
        .DW       (dcim_pkg::DW),
        .ACC_WIDTH(dcim_pkg::ACC_WIDTH),
        .A_SIGN   (dcim_pkg::A_SIGN),
        .W_SIGN   (dcim_pkg::W_SIGN)
     ) U_DCIM_TOP (
        .clk     (clk),
        .rst_n   (rst_n),
        .a_bit   (a_bit),
        .w_bit   (w_bit),
        .start   (start),
        .cont    (cont),
        .P_minus1(P_minus1),
        .y_bit   (y_bit),
        .done    (done),
        .busy    (busy)
    );

    logic [NUM_BIDIR_PADS-1:0] bidir_out_vec;
    always_comb begin : ASSIGN_OUT_PADS
        bidir_out_vec = '0;
        bidir_out_vec[PAD_Y_BIT] = y_bit;
        bidir_out_vec[PAD_DONE]  = done;
        bidir_out_vec[PAD_BUSY]  = busy;
    end

    assign bidir_out = bidir_out_vec;

endmodule

`default_nettype wire
