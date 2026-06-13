# Default to Icarus Verilog
SIM ?= icarus
TOPLEVEL_LANG ?= verilog

# Your SystemVerilog source files
VERILOG_SOURCES += $(PWD)/mac.sv

# The name of the top-level SystemVerilog module
TOPLEVEL = mac

# The name of your Python test file (without the .py extension)
MODULE = test_test_array

# Include cocotb's standard makefile rules
include $(shell cocotb-config --makefiles)/Makefile.sim