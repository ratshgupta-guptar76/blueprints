

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

    always_comb begin : SIGNED_MULT
        add_bin = '0;
        // Create add bin form 0 to DW-2 since all are added accums
        //   irrespective of the operation (+/-)
        for (int b=0; b<DW-1; b++) begin
            add_bin += $signed(LANE_W'(col_adder[b])) <<< b;
        end

        if (W_SIGN) lane_val = add_bin - $signed(LANE_W'(col_adder[DW-1]) <<< (DW-1));    // Subtract the MSB after multiplication
        else        lane_val = add_bin + $signed(LANE_W'(col_adder[DW-1]) <<< (DW-1));    // Add the MSB after multiplication
    end

    always_ff @(posedge clk or negedge rst_n) begin : LANE_SHIFT_ACCUM
        if (~rst_n) begin
            y <= '0;
        end else begin
            if (clr) begin
                y <= '0;
            end else begin
                if (en) begin
                    y += col_adder << bp_idx;
                end
            end
        end
    end

endmodule
