// SPDX-FileCopyrightText: 2026 Chipathon 2026 workshop
// SPDX-License-Identifier: Apache-2.0
//
// Padframe-facing top for the A07_A padring variant (def/A07/project_defs/A/).
// Wraps dcim_top and exposes exactly the pin set + names required by
// FP_DEF_TEMPLATE (def/A07/project_defs/A/A07_A.def, generated from
// A07_A_interface.yaml / A07_A_pad_map.yaml). Each pin_map entry maps 1:1
// onto a dcim_top port:
//   input_cmos/input_schmitt pads (W14-W22): clk, rst_n, a_bit, w_bit,
//     start, cont, P_minus1_0/1/2 -- plain data pin plus PU/PD pull config,
//     pulls disabled since these are actively driven off-chip.
//   bidirectional pads (N01-N03): y_bit, done, busy -- these are pure
//     outputs from dcim_top, so OE is tied permanently high and the
//     _IN (pad->core) path is left disabled (IE=0) and unconnected.
// PDRV0/PDRV1 (drive-strength select) don't affect gf180mcu_fd_io__bi_t's
// logical function (see gf180mcu_fd_io.v specify block). Tied to 8mA
// (PDRV0=1, PDRV1=0): the 4mA floor is already enough for these
// low-frequency status signals, but the off-chip load is unknown, so
// one step of margin is used. Not maxed out: full drive strength would
// add needless simultaneous-switching noise on the shared multi-project
// die and risks overshoot/ringing on an uncontrolled-impedance test
// trace, for no benefit at this signaling speed.

`default_nettype none

module A07_dcim_top (
    input  logic clk,
    output logic clk_PU,
    output logic clk_PD,

    input  logic rst_n,
    output logic rst_n_PU,
    output logic rst_n_PD,

    input  logic a_bit,
    output logic a_bit_PU,
    output logic a_bit_PD,

    input  logic w_bit,
    output logic w_bit_PU,
    output logic w_bit_PD,

    input  logic start,
    output logic start_PU,
    output logic start_PD,

    input  logic cont,
    output logic cont_PU,
    output logic cont_PD,

    input  logic P_minus1[2:0],
    output logic P_minus1_PU[2:0],
    output logic P_minus1_PD[2:0],

    input  logic y_bit_IN,
    output logic y_bit_OUT,
    output logic y_bit_OE,
    output logic y_bit_CS,
    output logic y_bit_SL,
    output logic y_bit_IE,
    output logic y_bit_PU,
    output logic y_bit_PD,
    output logic y_bit_PDRV0,
    output logic y_bit_PDRV1,

    input  logic done_IN,
    output logic done_OUT,
    output logic done_OE,
    output logic done_CS,
    output logic done_SL,
    output logic done_IE,
    output logic done_PU,
    output logic done_PD,
    output logic done_PDRV0,
    output logic done_PDRV1,

    input  logic busy_IN,
    output logic busy_OUT,
    output logic busy_OE,
    output logic busy_CS,
    output logic busy_SL,
    output logic busy_IE,
    output logic busy_PU,
    output logic busy_PD,
    output logic busy_PDRV0,
    output logic busy_PDRV1
);

    // Input pads: pulls disabled, driven externally.
    assign clk_PU          = 1'b0;
    assign clk_PD          = 1'b0;
    assign rst_n_PU        = 1'b0;
    assign rst_n_PD        = 1'b0;
    assign a_bit_PU        = 1'b0;
    assign a_bit_PD        = 1'b0;
    assign w_bit_PU        = 1'b0;
    assign w_bit_PD        = 1'b0;
    assign start_PU        = 1'b0;
    assign start_PD        = 1'b0;
    assign cont_PU         = 1'b0;
    assign cont_PD         = 1'b0;
    assign P_minus1_PU[0]  = 1'b0;
    assign P_minus1_PD[0]  = 1'b0;
    assign P_minus1_PU[1]  = 1'b0;
    assign P_minus1_PD[1]  = 1'b0;
    assign P_minus1_PU[2]  = 1'b0;
    assign P_minus1_PD[2]  = 1'b0;

    // Bidir pads used as fixed outputs: OE permanently on, receiver
    // (IE) off, CMOS/fast/no-pull config, lowest drive strength.
    assign y_bit_OE     = 1'b1;
    assign y_bit_CS     = 1'b0;
    assign y_bit_SL     = 1'b0;
    assign y_bit_IE     = 1'b0;
    assign y_bit_PU     = 1'b0;
    assign y_bit_PD     = 1'b0;
    assign y_bit_PDRV0  = 1'b1;
    assign y_bit_PDRV1  = 1'b0;

    assign done_OE       = 1'b1;
    assign done_CS       = 1'b0;
    assign done_SL       = 1'b0;
    assign done_IE       = 1'b0;
    assign done_PU       = 1'b0;
    assign done_PD       = 1'b0;
    assign done_PDRV0    = 1'b1;
    assign done_PDRV1    = 1'b0;

    assign busy_OE       = 1'b1;
    assign busy_CS       = 1'b0;
    assign busy_SL       = 1'b0;
    assign busy_IE       = 1'b0;
    assign busy_PU       = 1'b0;
    assign busy_PD       = 1'b0;
    assign busy_PDRV0    = 1'b1;
    assign busy_PDRV1    = 1'b0;

    // Receiver paths are disabled (IE=0) and unused.
    logic _unused_in;
    assign _unused_in = y_bit_IN ^ done_IN ^ busy_IN;

    dcim_top U_DCIM_TOP (
        .clk     (clk),
        .rst_n   (rst_n),
        .a_bit   (a_bit),
        .w_bit   (w_bit),
        .start   (start),
        .cont    (cont),
        .P_minus1(P_minus1),
        .y_bit   (y_bit_OUT),
        .done    (done_OUT),
        .busy    (busy_OUT)
    );

endmodule

`default_nettype wire
