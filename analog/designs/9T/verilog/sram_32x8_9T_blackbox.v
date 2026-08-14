/*
 * 9T DCIM SRAM macro : 32 rows x 8 columns
 * Synthesis blackbox (no power pins)
 */
(* blackbox *)
module sram_32x8_9T (
    WL,
    A,
    WBL,
    WBLB,
    RBL
);
input  [31:0]  WL;    // wordline, one-hot, active high
input  [31:0]  A;     // activation, one per row
input  [7:0]   WBL;   // write bitline, one per column
input  [7:0]   WBLB;  // write bitline complement
output [255:0] RBL;   // per-cell product output, RBL[r*8+c]
endmodule