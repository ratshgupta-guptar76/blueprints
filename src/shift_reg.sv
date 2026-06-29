// ==================================================================================
// shift_reg.sv — single 8-bit activation cell (one per array row) - (2 if ping-pong)
// ==================================================================================
// One DW-bit register. 64 of these chain together in activation_shiftchain.sv,
// one per array row. Two modes, selected by c_en (en must be high for either):
//
//   LOAD    (en=1, c_en=0): shift toward MSB. serial_in enters at sr[0];
//                           sr[DW-1] exits via serial_out into the next cell's
//                           serial_in. The 64 cells act as one 512-bit chain to
//                           stream activations in. (Mode mux: c_en picks mode;
//                           never derive one mode from the other.)
//
//   COMPUTE (en=1, c_en=1): shift toward LSB, zero-fill MSB. Each cycle exposes
//                           the next activation bit on compute_bit (= sr[0]),
//                           LSB-FIRST. The 64 compute_bit outputs across all rows
//                           form one broadcast bit-plane to the array.
//                           LSB-first order MUST match golden_model trace.
//
//   en=0:  hold/IDLE
//
// Taps are combinational wires, not flops (no added latency):
//   compute_bit = sr[0]      bit-plane output for this row (compute mode)
//   serial_out  = sr[DW-1]   chain output to next cell (load mode)
//
// NOTE: load and compute shift OPPOSITE directions (slices [DW-2:0] vs [DW-1:1]).
// That asymmetry is intentional — same slice on both lines = one mode is wrong.
// ==================================================================================

module shift_reg #(
    parameter int DW   = dcim_pkg::DW
) (
    input logic clk,
    input logic rst_n,

    input logic en,
    input logic serial_in,
    input logic c_en,           // Compute Enable/~Write Enable

    output logic compute_bit,   // LSB of shift-reg, used for compute
    output logic serial_out     // Serial-Out bit, used for shifting data across shift-regs
);

    logic [DW-1:0] sr;      // Shift Register

    always_ff @(posedge clk or negedge rst_n) begin : SISO_SHIFT
        if (~rst_n) begin
            sr <= '0;
        end else begin
            if (en & c_en) begin
                sr <= {1'b0, sr[DW-1:1]};       // Computes, so shift 
            end else if (en & ~c_en) begin
                sr <= {serial_in, sr[DW-2:0]};
            end else begin
                sr <= sr;
            end
        end
    end

    assign compute_bit = sr[0];

    assign serial_out  = sr[DW-1];

endmodule
