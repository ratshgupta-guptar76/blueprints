// =============================================================================
// row_decoder.sv — binary-to-one-hot wordline decoder (weight write port)
// =============================================================================
// Combinational. Selects ONE array row for a weight write by driving a single
// one-hot wordline. Used ONLY for weight loads — activations do not use a
// decoder (they self-route through the shift chain).
//
//   en=1: wl = one-hot(addr)   exactly one wordline high (row = addr)
//   en=0: wl = 0               ALL wordlines low
//
// The en=0 → all-low behavior is REQUIRED: it guarantees no row is written
// during COMPUTE or IDLE. en is driven by we from control_fsm. Never let wl
// float high outside an active write.
//
// Params: OUT_WIDTH = ROWS = 64 (one-hot width); IN_WIDTH = $clog2(OUT_WIDTH) = 6
// (derived — declare OUT_WIDTH first so IN_WIDTH can reference it).
// OUT_WIDTH'(1) << addr is width-sized so the shift literal can't truncate.
// =============================================================================

module row_decoder #(
    parameter int OUT_WIDTH = 64,
    parameter int IN_WIDTH  = $clog2(OUT_WIDTH)
) (
    input logic en,         // Enable decoder

    input logic [IN_WIDTH-1:0] addr,        // Binary Input bits

    output logic [OUT_WIDTH-1:0] wl         // One-Hot outupt bits (decoded)
);

    always_comb begin : DECODER
        wl = '0;
        if (en) begin
            wl[addr] = 1'b1;
        end
    end

endmodule
