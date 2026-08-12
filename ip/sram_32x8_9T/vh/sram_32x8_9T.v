/*
 * 9T DCIM SRAM macro — 32 rows x 8 columns
 * Behavioural simulation model
 *
 * Write:   level-sensitive on WL[r]; WBL drives the row while asserted.
 *          WBLB is the complement and is not modelled (real cell is
 *          differential; a mismatch would be a driver bug, not a cell bug).
 * Compute: RBL[r*8+c] = mem[r][c] & A[r]   (AND of stored bit and activation)
 *
 * Memory powers up X, matching real SRAM. Write all rows before any read.
 */
`timescale 1ns / 1ps

module sram_32x8_9T (
    input  wire [31:0]  WL,
    input  wire [31:0]  A,
    input  wire [7:0]   WBL,
    input  wire [7:0]   WBLB,
    output wire [255:0] RBL
);

    reg [7:0] mem [31:0];

    integer r;
    always @(*) begin
        for (r = 0; r < 32; r = r + 1)
            if (WL[r] === 1'b1) mem[r] = WBL;
    end

    genvar gr, gc;
    generate
        for (gr = 0; gr < 32; gr = gr + 1) begin : ROW
            for (gc = 0; gc < 8; gc = gc + 1) begin : COL
                assign RBL[gr*8 + gc] = mem[gr][gc] & A[gr];
            end
        end
    endgenerate

`ifdef SRAM_CHECK_WL
    // one-hot check: more than one wordline asserted is a driver bug
    always @(WL)
        if (WL !== 32'b0 && (WL & (WL - 1)) !== 32'b0)
            $display("WARNING %0t: %m WL not one-hot: %b", $time, WL);
`endif

endmodule