# ======================================================================================
# Project   : DCIM INT8 Matrix-Vector Macro (Chipathon 2026, Team A7 - Blueprints)
# File      : row_decoder_tb.py
# Author    : R. Gupta
# Date      : Jul-18-2026
# --------------------------------------------------------------------------------------
# DUT       : row_decoder.sv
# Type      : Combinational
# Framework : cocotb / Verilator
# 
# DESCRIPTION
# ***********
#   Binary to one-hot wordline decoder for the DCIM weight-write path. A `ROWS`-wide 
#   one-hot wl selects the row driven during a weight write; the enable gates the 
#   entire decode so that no wordline asserts when WRITE is inactive.
# 
# SPECIFICATION
# *************
#   en == 1 => wl[addr] = 1, the rest are 0
#   en == 0 => wl[*]    = 0, all bits are 0
# 
# PARAMETERS
# **********
#   ROWS: number of wordlines (adopted from dcim_pkg::ROWS - must match)
# 
# --------------------------------------------------------------------------------------
# DEPENDENCIES: src/dcim_pkg.sv, src/row_decoder.sv
# --------------------------------------------------------------------------------------
# Revision History:
# Date        | Engineer      | Version  | Description
# ------------+---------------+----------+----------------------------------------------
# Jul-18-2026 | R. Gupta      | * v1.0   | Initial Testbench Environment Setup
# ======================================================================================


