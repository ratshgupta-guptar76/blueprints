# Default to Icarus Verilog
SIM ?= icarus
TOPLEVEL_LANG ?= verilog

# Your SystemVerilog source files
VERILOG_SOURCES += $(PWD)/../src/row_decoder.sv

# The name of the top-level SystemVerilog module
TOPLEVEL = row_decoder

# The name of your Python test file (without the .py extension)
MODULE = row_decoder_test

# Include cocotb's standard makefile rules
include $(shell cocotb-config --makefiles)/Makefile.sim