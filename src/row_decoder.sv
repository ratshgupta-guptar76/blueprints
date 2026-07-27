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
// Params: ROWS = dcim_pkg::ROWS (one-hot width); RW = $clog2(ROWS) (address
// width, derived — declare ROWS first so RW can reference it).
// en is driven by w_en from control_fsm. Never let wl assert outside a write.
// =============================================================================

module row_decoder #(
    parameter int ROWS = dcim_pkg::ROWS,
    parameter int RW  = $clog2(ROWS)
) (
    input logic en,         // Enable decoder

    input logic [RW-1:0] addr,        // Binary Input bits

    output logic [ROWS-1:0] wl         // One-Hot outupt bits (decoded)
);

    always_comb begin : DECODER
        wl = '0;
        if (en) begin
            wl[addr] = 1'b1;
        end
    end

endmodule
