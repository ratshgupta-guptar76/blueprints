// ==================================================================================
// col_adder.sv — single column reduction (vertical sum, combinational)
// ==================================================================================
// Sums the ROWS=64 partial-product bits of ONE bit-column -> one column-sum.
// 64 instances (one per column) live in the parent. Plain unsigned addition:
// NO weight-bit weighting (x2^bit), NO bit-plane shift, NO sign — those are
// shift_accum. Stateless: no clk/en (downstream accumulate is FSM-gated).
// Synthesis builds/balances the ~6-level tree from the += loop.
//   sum width = $clog2(ROWS+1) = 7  (max 64 one-bit inputs)
// TEST: sum == popcount(pp_col) for random vectors + all-0 + all-1 (=64).
// ==================================================================================

module col_adder_behavioural #(
    parameter int ROWS = dcim_pkg::ROWS
) (
    input logic [ROWS-1:0] pp_col,      // AND-multiply bits

    output logic [$clog2(ROWS):0] sum
);

    always_comb begin : COL_ADDER_TREE
        sum = '0;
        for (int i = 0; i < ROWS; i++) begin
            sum += pp_col[i];
        end
    end

endmodule
