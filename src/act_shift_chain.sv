// ==================================================================================
// act_shift_chain.sv — FIXED version (cycle-consistent compute + load chain)
// ==================================================================================
//
// FIXES:
// - act_bp is strictly combinational tap from each shift_reg
// - avoids timing ambiguity in compute mode
// - preserves deterministic row ordering
// - stabilizes chain behavior for cocotb cycle sampling
// ==================================================================================

module act_shift_chain #(
    parameter int ROWS = dcim_pkg::ROWS,
    parameter int DW   = dcim_pkg::DW
) (
    input  logic clk,
    input  logic rst_n,

    input  logic en,
    input  logic a_b,
    input  logic c_en,

    output logic [ROWS-1:0] act_bp,
    output logic tail_out
);

    // ------------------------------------------------------------
    // Serial chain between cells (ROW0 input → ROWS output)
    // ------------------------------------------------------------
    logic [ROWS:0] sr;

    assign sr[0]     = a_b;
    assign tail_out  = sr[ROWS];

    // ------------------------------------------------------------
    // Shift chain
    // ------------------------------------------------------------
    genvar i;
    generate
        for (i = 0; i < ROWS; i++) begin : GEN_SHIFT

            shift_reg #(
                .DW(DW)
            ) u_shift_reg (
                .clk(clk),
                .rst_n(rst_n),
                .en(en),
                .c_en(c_en),

                .serial_in(sr[i]),
                .serial_out(sr[i+1]),

                // IMPORTANT:
                // must be a COMBINATIONAL TAP inside shift_reg
                .compute_bit(act_bp[i])
            );

        end
    endgenerate

endmodule