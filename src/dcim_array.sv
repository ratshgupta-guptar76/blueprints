// ==================================================================================
// dcim_array.sv — weight storage + AND grid (dumb datapath, no FSM)
// ==================================================================================
// Stores the weight matrix; outputs 1-bit partial products (weight AND activation)
// for the current bit-plane. Obeys w_en; FSM drives timing.
//
//   w_mem [ROWS][COLS] : 4096 behavioral flops -> 8T SRAM macro at PnR. No reset
//                        (SRAM powers up X). Write all rows before any read.
//   write port         : row_decoder -> one-hot wl; selected row latches w_buf.
//                        wl=0 when w_en=0 (no stray writes).
//   pp (combinational) : pp[i] = w_mem[i] & {COLS{act_bp[i]}}. Transient product,
//                        not storage. ACTIVE-HIGH — no ~ here (column inverter is
//                        added at the macro swap, not in RTL).
//   col layout         : column c = bit (c%DW) of weight (c/DW). Must match
//                        weight_load + golden_model.
//
// TEST:
//   - Write a known row via row_addr/w_buf, read it back -> w_mem latches correct row only.
//   - wl is one-hot under w_en; w_en=0 -> no write (assert $onehot0(wl)).
//   - pp[i] == w_mem[i] & act_bp[i] broadcast, for a few hand-picked planes.
//   - Column mapping matches golden_model layout (one weight, check its 8 columns).
//   - pp is active-high (no inversion vs golden products).
// ==================================================================================

module dcim_array #(
    parameter int ROWS = dcim_pkg::ROWS,
    parameter int COLS = dcim_pkg::COLS
) (
    input logic clk,

    input logic                    w_en,
    input logic [$clog2(ROWS)-1:0] row_addr,
    input logic [COLS-1:0]         w_buf,
    input logic [ROWS-1:0]         act_bp,

    output logic [ROWS-1:0][COLS-1:0] pp
);

    logic [ROWS-1:0] wl;
    row_decoder #(
        .OUT_WIDTH (ROWS),
        .IN_WIDTH  ($clog2(ROWS))
    ) ROW_DECODER (
        .en   (w_en),
        .addr (row_addr),
        .wl   (wl)
    );

    logic [ROWS-1:0][COLS-1:0] w_mem;

    always_ff @(posedge clk) begin : LOAD_WEIGHTS
        if (~w_en) begin
            // Hold/IDLE state - Do nothing.
            w_mem <= w_mem;
        end else begin
            // Write Enabled for Weights
            // only rows with `wl` HI (1) will be set (emulate SRAM). `wl` must be one-hot
            for (int i = 0; i < ROWS; i++) begin
                if (wl[i] == 1'b1) w_mem[i] <= w_buf;           // Update row
                else               w_mem[i] <= w_mem[i];        // Keep state
            end
        end
    end

    always_comb begin : AND_BIT_MULT
        for (int i = 0; i < ROWS; i++)
            pp[i] = w_mem[i] & {COLS{act_bp[i]}};
    end

endmodule
