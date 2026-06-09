# Minimal Makefile with example targets for builds and CI

SIM=scripts/eda.sh

.PHONY: help all build sim-rtl sim-analog sim-mix test ci-smoke clean

help:
	@echo "Usage: make <target>"
	@echo "Targets: all build sim-rtl sim-analog sim-mix test ci-smoke clean"

all: build

build:
	@echo "No global build defined; run specific targets like 'make sim-rtl'"

sim-rtl:
	@echo "Running RTL simulation..."
	$(SIM) sim rtl

sim-analog:
	@echo "Running analog simulation..."
	$(SIM) sim analog

sim-mix:
	@echo "Running mixed-signal simulation..."
	$(SIM) sim mix

test: sim-rtl sim-analog

ci-smoke:
	@echo "CI smoke: verify layout and list key files"
	@echo "src files:" && ls -1 src || true
	@echo "sim folders:" && ls -1 sim || true

clean:
	@echo "No clean actions defined. Add tool-specific cleans as needed."
