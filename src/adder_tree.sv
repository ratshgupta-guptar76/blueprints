// ==================================================================================
// adder_tree.sv — vertical reduction (64 column-trees, combinational)
// ==================================================================================
// Sums pp down the rows, per column: sum[c] = popcount(pp[*][c]). COLS=64 trees,
// each a col_adder over ROWS=64 bits -> 7-bit column-sum. Vertical reduction ONLY:
// no weight-bit weighting, no plane shift, no sign (-> shift_accum). Stateless.
//
//   GATHER: col[r] = pp[r][c] transposes a COLUMN out of row-major pp. The whole
//           point of the module — pp[c][r] here would sum the wrong axis (bug).
//   col_adder swap point: replace col_adder_behavioural with a CSA/pipelined
//           variant at STA without touching this parent (ports fixed).
//
// TEST: sum[c] == popcount of column c, for random pp + a single-1 + all-1 columns.
// ==================================================================================

module adder_tree #(
    parameter int ROWS      = dcim_pkg::ROWS,
    parameter int COLS      = dcim_pkg::COLS
) (
    input logic [ROWS-1:0][COLS-1:0] pp,

    output logic [COLS-1:0][$clog2(ROWS+1)-1:0] sum
);

    genvar r;
    genvar c;
    generate
        for (c=0; c<COLS; c++) begin : ADDER_TREES
            logic [ROWS-1:0] col;
            for (r=0; r<ROWS; r++) begin : ROW_GATHER
                assign col[r] = pp[r][c];
            end
            
            col_adder_behavioural #(
                .ROWS(ROWS)
            ) COL_ADDER (
                .pp_col (col),
                .sum    (sum[c])
            );
        end
    endgenerate

endmodule