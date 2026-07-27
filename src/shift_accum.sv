// ==================================================================================
// shift_accum.sv — 8-lane parent (horizontal combine + temporal accumulate)
// ==================================================================================
// Takes the 64 column-sums from sum, slices into N_WEIGHTS=8 lanes (one per
// weight, DW=8 contiguous columns each), instantiates one lane_shift_accum per lane.
// All lane math (weight-bit combine, MSB-subtract, temporal accumulate) lives in the
// unit — this module only reshapes and replicates.
//
// SLICE: col_adders[i] = sum[i*DW +: DW] via packed-array reshape (MSB-aligned
//   bit-flatten equality). Contiguous per lane (unlike sum's row/col transpose)
//   -> lower bug risk. Verify: col_adders[i][0] = weight i's LSB column = sum
//   [i*DW]; col_adders[i][DW-1] = weight i's MSB column = sum[i*DW+DW-1].
//
// Ports: sum[COLS][SUM_W] in -> y[N_WEIGHTS][ACC_WIDTH] out. bp_idx/en/clr
//   FSM-driven, shared across all 8 lanes (same plane, same cycle, independent accs).
//
// TEST: each lane's y independently matches golden_bit_serial's per-weight trace;
//   confirm slice boundaries (lane 0 = sum[7:0], lane 7 = sum[63:56]).
// ==================================================================================

module shift_accum #(
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

    input logic                                en,
    input logic                                clr,
    input logic [$clog2(DW)-1:0]               bp_idx,
    input logic [COLS-1:0][$clog2(ROWS+1)-1:0] sum,

    output logic [N_WEIGHTS-1:0][ACC_WIDTH-1:0] y
);

    logic [N_WEIGHTS-1:0][DW-1:0][$clog2(ROWS+1)-1:0] col_adders;
    typedef logic [N_WEIGHTS-1:0][DW-1:0][$clog2(ROWS+1)-1:0] col_adders_t;

    assign col_adders = col_adders_t'(sum);

    genvar i;
    generate
        for (i=0; i<N_WEIGHTS; i++) begin : GENERATE_LANES
            lane_shift_accum #(
                .A_SIGN(A_SIGN),
                .ACC_WIDTH(ACC_WIDTH),
                .DW(DW),
                .ROWS(ROWS),
                .W_SIGN(W_SIGN)
            ) LANE_SHIFT_ACCUM (
                .clk(clk),
                .rst_n(rst_n),
                .en(en),
                .clr(clr),
                .bp_idx(bp_idx),
                .col_adder(col_adders[i]),
                .y(y[i])
            );
        end
    endgenerate

endmodule
