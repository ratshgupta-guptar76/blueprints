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