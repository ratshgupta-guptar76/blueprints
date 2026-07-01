// ==================================================================================
// lane_shift_accum.sv — one output lane (= one signed 8-bit weight)
// ==================================================================================
// Reduces one weight's DW=8 bit-columns into a single ACC_WIDTH=22 signed result.
// N_WEIGHTS=8 of these instantiated by the parent; each is independent (no cross-lane).
//
// Two reductions, two axes:
//   AXIS 1 — horizontal weight-bit combine (SIGNED_WEIGHT_ACCUM, combinational,
//            EVERY cycle): col_sums[b]·2^b for b=0..DW-2 (add) with the weight-MSB
//            column subtracted when W_SIGN (-2^(DW-1)). Produces signed lane_val.
//            Weight sign lives HERE, per-cycle — the full signed weight multiplies
//            every activation plane. NOT a last-cycle thing.
//   AXIS 2 — temporal bit-plane accumulate (SIGNED_ACT_ACCUM, registered): each
//            cycle p, y += lane_val <<< p (LSB-first, p = bp_idx). Activation sign
//            (A_SIGN) subtracts ONLY on the last plane (bp_idx==DW-1); A_SIGN=0 for
//            tapeout -> all planes add.
//
// SIGN_EXT: lane_val (LANE_W=15 signed) is sign-extended to ACC_WIDTH=22 BEFORE the
//   shift/accumulate. MUST be sign-extend (not width-cast/zero-extend) or negative
//   lane values corrupt into large positives. Correct for all {W_SIGN,A_SIGN} — a
//   positive lane_val sign-extends with 0s, identical to zero-extend.
//
// Widths: col_sums SUM_W=7 -> lane_val LANE_W=15 -> y ACC_WIDTH=22. Each reduction
//   grows width; do not collapse. LANE_W = SUM_W + DW (tight bound incl. sign).
//
// Control: clr -> y=0 (matvec start, priority over en). en -> accumulate this plane.
//   bp_idx (0..DW-1) from FSM. Inputs active-high (column inversion done upstream).
//
// TEST: combine alone vs Σ·2^b − MSB; full y vs golden_bit_serial per-cycle trace
//   (LSB-first, not just final). Cover all 4 {W_SIGN,A_SIGN}; include a negative
//   result (weight 8'hFF -> lane_val=-1). A_SIGN=1 needs matching golden + plane-7
//   activation MSB set.
// ==================================================================================

module lane_shift_accum #(
    parameter int ROWS       = dcim_pkg::ROWS,
    parameter int DW         = dcim_pkg::DW,
    parameter int ACC_WIDTH  = dcim_pkg::ACC_WIDTH,
    parameter int A_SIGN     = dcim_pkg::A_SIGN,
    parameter int W_SIGN     = dcim_pkg::W_SIGN
) (
    input logic clk,
    input logic rst_n,

    input logic                              en,
    input logic                              clr,
    input logic [$clog2(DW)-1:0]             bp_idx,
    input logic [DW-1:0][$clog2(ROWS+1)-1:0] col_adder, 

    output logic [ACC_WIDTH-1:0] y
);

    localparam int LANE_W = $clog2(ROWS+1) + DW;

    logic signed [LANE_W-1:0] add_bin, lane_val;

    always_comb begin : SIGNED_WEIGHT_ACCUM
        add_bin = '0;
        // Create add bin form 0 to DW-2 since all are added accums
        //   irrespective of the operation (+/-)
        for (int b=0; b<DW-1; b++) begin
            add_bin += $signed(LANE_W'(col_adder[b])) <<< b;
        end

        if (W_SIGN) lane_val = add_bin - $signed(LANE_W'(col_adder[DW-1]) <<< (DW-1));    // Subtract the MSB after multiplication
        else        lane_val = add_bin + $signed(LANE_W'(col_adder[DW-1]) <<< (DW-1));    // Add the MSB after multiplication
    end

    logic signed [ACC_WIDTH-1:0] lane_signed_val;
    always_comb begin : SIGN_EXT
        lane_signed_val = {{(ACC_WIDTH-LANE_W){lane_val[LANE_W-1]}}, lane_val};
    end

    always_ff @(posedge clk or negedge rst_n) begin : SIGNED_ACT_ACCUM
        if (~rst_n) begin
            y <= '0;
        end else begin
            if (clr) begin
                y <= '0;
            end else begin
                if (en) begin
                    if (A_SIGN && (bp_idx == DW-1)) y <= y - (lane_signed_val <<< bp_idx);      // Subtract MSB lane value (if A_SIGN)
                    else                            y <= y + (lane_signed_val <<< bp_idx);      // Add lane value at all other bits
                end
            end 
        end
    end


endmodule
