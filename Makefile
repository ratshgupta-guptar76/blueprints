MAKEFILE_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

# --- RTL sources ---------------------------------
RTL_MODULES := \
    dcim_pkg row_decoder shift_reg col_adder weight_load stream_out \
    adder_tree act_shift_chain lane_shift_accum shift_accum \
    dcim_array control_fsm dcim_top

RTL_SOURCES := $(addprefix $(MAKEFILE_DIR)/src/,$(addsuffix .sv,$(RTL_MODULES)))

# --- Project paths -------------------------------
COCOTB_DIR    := $(MAKEFILE_DIR)/cocotb
RESULTS_DIR   := $(COCOTB_DIR)/results
SIM_BUILD_DIR := $(COCOTB_DIR)/sim_build
COV_DIR       := $(COCOTB_DIR)/cov_annotated

# --- Simulation configuration --------------------
SIM                ?= verilator
VERILATOR_COVERAGE ?= 1
export SIM

ifeq ($(COCOTB_FUNC_RUN),1)

# --- Unit under test -----------------------------
FUNC      ?= row_decoder
SIM_BUILD ?= $(SIM_BUILD_DIR)/$(FUNC)
COV_FILE  := $(SIM_BUILD)/coverage.dat
export COV_FILE

# --- cocotb entry points -------------------------
TOPLEVEL_LANG       ?= verilog
TOPLEVEL            := $(FUNC)
COCOTB_TEST_MODULES := functional.$(FUNC)_tb
VERILOG_SOURCES     += $(RTL_SOURCES)

# --- cocotb environment --------------------------
WAVES               ?= 1
COCOTB_RESULTS_FILE ?= $(RESULTS_DIR)/$(FUNC).xml
export WAVES
export COCOTB_RESULTS_FILE
export PYTHONPATH := $(COCOTB_DIR):$(PYTHONPATH)

# --- Simulator arguments -------------------------
ifeq ($(SIM),verilator)
    COMPILE_ARGS += --trace-fst --trace-structs

    ifeq ($(VERILATOR_COVERAGE),1)
        COMPILE_ARGS += --coverage-line --coverage-user
        SIM_ARGS     += +verilator+coverage+file+$(COV_FILE)
        SIM_ARGS     += --trace
    endif

endif

ifeq ($(SIM),icarus)
    COMPILE_ARGS += -g2012
endif

include $(shell cocotb-config --makefiles)/Makefile.sim

else

TOP = chip_top

PDK_ROOT ?= $(MAKEFILE_DIR)/gf180mcu
PDK ?= gf180mcuD
PDK_TAG ?= 1.8.0

AVAILABLE_SLOTS = 1x1 0p5x1 1x0p5 0p5x0p5 workshop
DEFAULT_SLOT = workshop

FUNCTIONAL_TESTS := $(patsubst $(COCOTB_DIR)/functional/%_tb.py,%,\
                      $(wildcard $(COCOTB_DIR)/functional/*_tb.py))

# Slot can be any of AVAILABLE_SLOTS
SLOT ?= $(DEFAULT_SLOT)

ifeq ($(SLOT),default)
    SLOT = $(DEFAULT_SLOT)
endif

ifeq ($(filter $(SLOT),$(AVAILABLE_SLOTS)),)
    $(error $(SLOT) does not exist in AVAILABLE_SLOTS: $(AVAILABLE_SLOTS))
endif

ifneq ($(func-sim),)
.DEFAULT_GOAL := func-sim
else ifneq ($(func),)
.DEFAULT_GOAL := func
else
.DEFAULT_GOAL := help
endif

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'
.PHONY: help

all: librelane ## Build the project (runs LibreLane)
.PHONY: all

clone-pdk: ## Clone the GF180MCU PDK repository
	rm -rf $(MAKEFILE_DIR)/gf180mcu
	git clone https://github.com/wafer-space/gf180mcu.git $(MAKEFILE_DIR)/gf180mcu --depth 1 --branch ${PDK_TAG}
.PHONY: clone-pdk

librelane: ## Run LibreLane flow (synthesis, PnR, verification)
	librelane librelane/slots/slot_${SLOT}.yaml librelane/config.yaml --save-views-to $(MAKEFILE_DIR)/final --pdk ${PDK} --pdk-root ${PDK_ROOT} --manual-pdk
.PHONY: librelane

librelane-nodrc: ## Run LibreLane flow without DRC checks
	librelane librelane/slots/slot_${SLOT}.yaml librelane/config.yaml --save-views-to $(MAKEFILE_DIR)/final --pdk ${PDK} --pdk-root ${PDK_ROOT} --manual-pdk --skip KLayout.Antenna --skip KLayout.DRC --skip Magic.DRC
.PHONY: librelane-nodrc

librelane-klayoutdrc: ## Run LibreLane flow without magic DRC checks
	librelane librelane/slots/slot_${SLOT}.yaml librelane/config.yaml --save-views-to $(MAKEFILE_DIR)/final --pdk ${PDK} --pdk-root ${PDK_ROOT} --manual-pdk --skip Magic.DRC
.PHONY: librelane-klayoutdrc

librelane-magicdrc: ## Run LibreLane flow without KLayout DRC checks
	librelane librelane/slots/slot_${SLOT}.yaml librelane/config.yaml --save-views-to $(MAKEFILE_DIR)/final --pdk ${PDK} --pdk-root ${PDK_ROOT} --manual-pdk --skip KLayout.DRC
.PHONY: librelane-magicdrc

librelane-openroad: ## Open the last run in OpenROAD
	librelane librelane/slots/slot_${SLOT}.yaml librelane/config.yaml --pdk ${PDK} --pdk-root ${PDK_ROOT} --manual-pdk --last-run --flow OpenInOpenROAD
.PHONY: librelane-openroad

librelane-klayout: ## Open the last run in KLayout
	librelane librelane/slots/slot_${SLOT}.yaml librelane/config.yaml --pdk ${PDK} --pdk-root ${PDK_ROOT} --manual-pdk --last-run --flow OpenInKLayout
.PHONY: librelane-klayout

librelane-padring: ## Only create the padring
	PDK_ROOT=${PDK_ROOT} PDK=${PDK} python3 scripts/padring.py librelane/slots/slot_${SLOT}.yaml librelane/config.yaml
.PHONY: librelane-padring

lint: ## Lint RTL sources with Verilator
	verilator --lint-only -Wall --top-module dcim_top $(RTL_SOURCES)
.PHONY: lint

sim: ## Run RTL simulation with cocotb
	cd $(COCOTB_DIR) && PDK_ROOT=${PDK_ROOT} PDK=${PDK} SLOT=${SLOT} python3 chip_top_tb.py
.PHONY: sim

func: ## Run a functional cocotb test with func=<module name>
	@if [ -z "$(func)" ]; then echo "Usage: make func=<module name>"; exit 2; fi
	@mkdir -p $(RESULTS_DIR) $(SIM_BUILD_DIR)
	
	@rm -f $(COCOTB_DIR)/dump.fst
	
	$(MAKE) -C $(COCOTB_DIR) -f $(MAKEFILE_DIR)/Makefile \
		COCOTB_FUNC_RUN=1 \
		FUNC=$(func) \
		SIM_BUILD=$(SIM_BUILD_DIR)/$(func) \
		VERILATOR_COVERAGE=$(VERILATOR_COVERAGE) \
		sim
		
	@if [ -f "$(COCOTB_DIR)/dump.fst" ]; then \
		mv $(COCOTB_DIR)/dump.fst $(SIM_BUILD_DIR)/$(func)/$(func).fst; \
		echo "Waveform cleanly relocated to: $(SIM_BUILD_DIR)/$(func)/$(func).fst"; \
	fi

ifeq ($(VERILATOR_COVERAGE),1)
	@mkdir -p $(COV_DIR)/$(func)
	@if [ -f "$(SIM_BUILD_DIR)/$(func)/coverage.dat" ]; then \
		echo ; \
		echo "====================================="; \
		echo "Coverage report - $(func)"; \
		echo "====================================="; \
		verilator_coverage \
			--annotate $(COV_DIR)/$(func) \
			$(SIM_BUILD_DIR)/$(func)/coverage.dat; \
	else \
		echo "Warning: No coverage.dat found in $(SIM_BUILD_DIR)/$(func)/"; \
	fi
endif
.PHONY: func

func-sim: ## View functional cocotb waveforms in Surfer
	@if [ -z "$(func-sim)" ]; then echo "Usage: make func-sim=<module name>"; exit 2; fi
	@w=$(SIM_BUILD_DIR)/$(func-sim)/$(func-sim).fst; \
	if [ ! -f "$$w" ]; then echo "No waveform for $(func-sim). Run: make func=$(func-sim)"; exit 2; fi; \
	surfer -s $(COCOTB_DIR)/surfer/$(func-sim).surfer.ron $$w

func-all: ## Run all functional cocotb tests
	@if [ -z "$(FUNCTIONAL_TESTS)" ]; then \
		echo "ERROR: no testbenches found in $(COCOTB_DIR)/functional/"; exit 2; fi
	@failed=""; \
	for test in $(FUNCTIONAL_TESTS); do \
		echo "=== $$test ==="; \
		$(MAKE) --no-print-directory -f $(MAKEFILE_DIR)/Makefile func=$$test || failed="$$failed $$test"; \
	done; \
	echo ""; \
	if [ -n "$$failed" ]; then echo "FAILED:$$failed"; exit 1; \
	else echo "All $(words $(FUNCTIONAL_TESTS)) functional tests passed."; fi
.PHONY: func-all

sim-gl: ## Run gate-level simulation with cocotb (after copy-final)
	cd $(COCOTB_DIR) && GL=1 PDK_ROOT=${PDK_ROOT} PDK=${PDK} SLOT=${SLOT} python3 chip_top_tb.py
.PHONY: sim-gl

sim-view: ## View simulation waveforms in GTKWave
	gtkwave cocotb/sim_build/chip_top.fst
.PHONY: sim-view

render-image: ## Render an image from the final layout (after copy-final)
	mkdir -p img/
	PDK_ROOT=${PDK_ROOT} PDK=${PDK} python3 scripts/lay2img.py final/gds/${TOP}.gds img/${TOP}.png --width 2048 --oversampling 4
.PHONY: copy-final

clean: ## Remove cocotb build artefacts, results and waveforms
	rm -rf $(RESULTS_DIR) $(SIM_BUILD_DIR) $(COV_DIR)
	rm -f $(COCOTB_DIR)/dump.fst $(COCOTB_DIR)/dump.vcd $(COCOTB_DIR)/results.xml
.PHONY: clean

endif