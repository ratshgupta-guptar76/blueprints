/*
 * 9T DCIM SRAM macro : 32 rows x 8 columns
 * Synthesis blackbox with power pins
 */
(* blackbox *)
module sram_32x8_9T (
    WL,
    A,
    WBL,
    WBLB,
    RBL,
    VDD,
    VSS
);
input  [31:0]  WL;
input  [31:0]  A;
input  [7:0]   WBL;
input  [7:0]   WBLB;
output [255:0] RBL;
endmodule