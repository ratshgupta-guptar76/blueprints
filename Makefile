MAKEFILE_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

ifeq ($(COCOTB_FUNC_RUN),1)

SIM ?= icarus
TOPLEVEL_LANG ?= verilog

FUNC ?= row_decoder
SIM_BUILD ?= sim_build/$(FUNC)

VERILOG_SOURCES += $(MAKEFILE_DIR)/src/$(FUNC).sv
TOPLEVEL = $(FUNC)
COCOTB_TEST_MODULES = functional.$(FUNC)_tb

include $(shell cocotb-config --makefiles)/Makefile.sim

else

RUN_TAG = $(shell ls librelane/runs/ | tail -n 1)
TOP = chip_top

PDK_ROOT ?= $(MAKEFILE_DIR)/gf180mcu
PDK ?= gf180mcuD
PDK_TAG ?= 1.8.0

AVAILABLE_SLOTS = 1x1 0p5x1 1x0p5 0p5x0p5 workshop
DEFAULT_SLOT = 1x1

# ADDED FOR FUNCTIONAL TESTS
FUNCTIONAL_TESTS := $(patsubst cocotb/functional/%_tb.py,%,$(wildcard cocotb/functional/*_tb.py))

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
	cd $(MAKEFILE_DIR)/src && verilator --lint-only -Wall -f files.f
.PHONY: lint

sim: ## Run RTL simulation with cocotb
	cd cocotb; PDK_ROOT=${PDK_ROOT} PDK=${PDK} SLOT=${SLOT} python3 chip_top_tb.py
.PHONY: sim

func: ## Run a functional cocotb test with func=<module name>
	@if [ -z "$(func)" ]; then echo "Usage: make func=<module name>"; exit 2; fi
	$(MAKE) -C cocotb -f $(MAKEFILE_DIR)/Makefile COCOTB_FUNC_RUN=1 FUNC=$(func) sim
.PHONY: func

func-sim: ## View functional cocotb waveforms in GTKWave with func-sim=<module name>
	@if [ -z "$(func-sim)" ]; then echo "Usage: make func-sim=<module name>"; exit 2; fi
	gtkwave cocotb/sim_build/$(func-sim)/$(func-sim).fst
.PHONY: func-sim

func-all: ## Run all functional cocotb tests
	@for test in $(FUNCTIONAL_TESTS); do \
		echo "Running functional test: $$test"; \
		$(MAKE) -C cocotb -f $(MAKEFILE_DIR)/Makefile COCOTB_FUNC_RUN=1 FUNC=$$test sim || exit $$?; \
	done
.PHONY: func-all

sim-gl: ## Run gate-level simulation with cocotb (after copy-final)
	cd cocotb; GL=1 PDK_ROOT=${PDK_ROOT} PDK=${PDK} SLOT=${SLOT} python3 chip_top_tb.py
.PHONY: sim-gl

sim-view: ## View simulation waveforms in GTKWave
	gtkwave cocotb/sim_build/chip_top.fst
.PHONY: sim-view

render-image: ## Render an image from the final layout (after copy-final)
	mkdir -p img/
	PDK_ROOT=${PDK_ROOT} PDK=${PDK} python3 scripts/lay2img.py final/gds/${TOP}.gds img/${TOP}.png --width 2048 --oversampling 4
.PHONY: copy-final

endif
