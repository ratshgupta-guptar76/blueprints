// ==================================================================================
// weight_load.sv — serial-to-parallel weight row assembler (WRITE_W front-end)
// ==================================================================================
// Collects COLS=64 serial w_bit into one parallel row, pulses wfull when complete.
// FSM turns wfull -> w_en to commit the row into dcim_array (parallel write port).
// Hides the serial pin reality from the array (which assumes parallel row-write).
//
//   en=1: shift w_bit into w_buf (toward LSB, w_bit enters MSB). Counter 0..63.
//   wfull: 1-cycle pulse, cycle AFTER the 64th bit -> w_buf fully valid that cycle.
//          Registered (not combinational) so it aligns with complete w_buf, not the
//          63-bit-in state. Forced low when ~en (no stale pulse into non-WRITE_W).
//
// CONTRACT (FSM depends on this): wfull pulses EXACTLY one cycle per assembled row,
//   coincident with valid w_buf. Multi-cycle hold -> double row_cnt increment.
//
// VERIFY (O1-equivalent, cocotb): stream-order of w_bit -> column mapping. Column c
//   must hold bit (c%DW) of weight (c/DW), matching dcim_array + golden_model layout.
//   Shift direction here ({w_bit, w_buf[COLS-1:1]}) sets that mapping — confirm, don't
//   assume.
// ==================================================================================

module weight_load #(
    parameter int COLS = dcim_pkg::COLS
) (
    input logic clk,
    input logic rst_n,
    
    input logic en,
    input logic w_bit,

    output logic wfull,
    output logic [COLS-1:0] w_buf
);

localparam int CW = $clog2(COLS);

// Counter
logic [CW-1:0] wload_cnt;

always_ff @(posedge clk or negedge rst_n) begin : WEIGHT_BUFFER
    if (~rst_n) begin
        w_buf <= '0;
    end else begin
        if (en) w_buf <= {w_bit, w_buf[COLS-1:1]};
    end
end

always_ff @(posedge clk or negedge rst_n) begin : LOAD_COUNTER
    if (~rst_n) begin
        wload_cnt <= '0;
    end else begin
        if (en) wload_cnt <= (wload_cnt == COLS-1) ? '0 : wload_cnt + CW'(1);
    end
end

always_ff @(posedge clk or negedge rst_n) begin : LOAD_DONE
    if (~rst_n) begin
        wfull <= '0;
    end else begin
        if (en) wfull <= (wload_cnt == COLS - 1) ? 1'b1 : 1'b0;
        else    wfull <= 1'b0;
    end
end

endmodule