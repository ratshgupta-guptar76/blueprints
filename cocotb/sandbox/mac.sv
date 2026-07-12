`timescale 1ns/1ps

module mac (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        valid_in,
    input  logic signed [7:0] a,
    input  logic signed [7:0] b,
    output logic signed [18:0] acc
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            acc <= '0;
        end else if (valid_in) begin
            acc <= acc + (a * b);
        end
    end

endmodule