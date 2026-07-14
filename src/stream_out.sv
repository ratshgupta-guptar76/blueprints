// ==================================================================================
// stream_out.sv — parallel-to-serial result drain (SHIFT_OUT front-end)
// ==================================================================================
// Serializes y (N_WEIGHTS*ACC_WIDTH = 176 bits) out one y_bit pin. Mirror of
// weight_load (PISO vs SIPO). Order: lane 0 first, LSB-first per lane (packed acc's
// low bits = lane 0, shift toward LSB taps bit 0 first).
//
//   load: capture acc into piso, reset counter. (DONE-entry pulse.)
//   en:   shift toward LSB, y_bit = piso[0]. Counter 0..TOT-1.
//   done: registered, pulses cycle AFTER bit 175 (drain complete). FSM SHIFT_OUT
//         exit gates on this.
//   else: hold.
//
// TOT = N_WEIGHTS*ACC_WIDTH = 176. Counter YW = $clog2(TOT) = 8-bit.
// ==================================================================================

module stream_out #(
    parameter int N_WEIGHTS = dcim_pkg::N_WEIGHTS,
    parameter int ACC_WIDTH = dcim_pkg::ACC_WIDTH
) (
    input logic clk,
    input logic rst_n,

    input logic                                en,
    input logic                                load,
    input logic [N_WEIGHTS-1:0][ACC_WIDTH-1:0] acc,

    output logic done,
    output logic y_bit
);

localparam int TOT = N_WEIGHTS*ACC_WIDTH;
localparam int YW = $clog2(N_WEIGHTS*ACC_WIDTH);

// Counters
logic [TOT-1:0] piso;
logic [YW-1:0]  counter;


    always_ff @(posedge clk or negedge rst_n) begin
        if (~rst_n) begin
            piso    <= '0;
            counter <= '0;
            done    <= 1'b0;
        end else begin
            if (load) begin
                piso    <= TOT'(acc);
                counter <= '0;
                done    <= '0;
            end else if (en) begin
                piso    <= {1'b0, piso[TOT-1:1]};
                counter <= counter + unsigned'(YW'(1));
                done    <= (counter == unsigned'(YW'(TOT-1)));
            end
        end
    end

    assign y_bit = piso[0];

endmodule
