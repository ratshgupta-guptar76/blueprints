"""
OVERVIEW
row_decoder.sv: responsible for selecting 1/64 rows in 8T array during "WRITE" mode

Two primary axes to test:
- Enable pin (en): Controls whether decoder is active
- Address bus (addr): 6-bit input that selects active row

STIMULUS GENERATION
- Full Sweep: en=1, iterate through addr
- Deactivated: en=0, iterate through addr
- Transition 1: Toggle between en=0 and en=1, hold addr constant
- Transition 2: Toggle between en=0 and en=1, changing addr same time

FUNCTIONAL COVERAGE IMPLEMENTATION
- Address Bus: 0 to 63
- Enable Pin: 0 and 1
- Cross Coverage: All addr and en combinations

CHECKING MECHANISM
- When en==1, wl should be 1<<addr
- When en==0, wl should be 0

"""


import cocotb
from cocotb.triggers import Timer
from cocotb_coverage.coverage import CoverPoint, CoverCross, coverage_db
import random

# Functional coverage model (see docstring above): addr, en, and their cross.
#
# The decorators run at import time, before any `dut` exists, so the addr bins
# can't reference the DUT there. Build the model lazily on the first sample and
# size the addr bins from dut.OUT_WIDTH -- the same parameter the tests loop
# over -- so the bins can never drift out of sync with the stimulus.
_sampler = None

def sample_coverage(dut):
    """Sample the current (en, addr) point into the coverage database."""
    global _sampler
    if _sampler is None:
        out_width = dut.OUT_WIDTH.value.integer

        @CoverPoint("top.en", xf=lambda dut: int(dut.en.value), bins=[0, 1])
        @CoverPoint("top.addr", xf=lambda dut: int(dut.addr.value), bins=list(range(out_width)))
        @CoverCross("top.en_x_addr", items=["top.en", "top.addr"])
        def _sample(dut):
            pass

        _sampler = _sample
    _sampler(dut)


@cocotb.test()
async def full_sweep(dut):
    """en=1, iterate through address bus"""
    out_width = dut.OUT_WIDTH.value.integer
    # by default this should be 64
    dut._log.info(f"Starting Full Sweep row_decoder test with OUT_WIDTH={out_width}")
    
    dut.en.value = 1 # manually set enable pin to 1 (activated)

    for addr in range(out_width):
        dut.addr.value = addr
        await Timer(1, unit="ns")
        sample_coverage(dut)

        # Check output should be 0
        assert dut.wl.value == 1<<addr, f"FAIL: Wordline is not {1<<addr} when en=1 for address {addr}. Got {dut.wl.value}"


@cocotb.test()
async def deactivated(dut):
    """en=0, iterate through address bus"""
    out_width = dut.OUT_WIDTH.value.integer
    # by default this should be 64

    dut._log.info(f"Starting Deactivated row_decoder test with OUT_WIDTH={out_width}")
    
    dut.en.value = 0 # manually set enable pin to 0

    for addr in range(out_width):
        dut.addr.value = addr
        await Timer(1, unit="ns")
        sample_coverage(dut)

        # Check output should be 0
        assert dut.wl.value == 0, f"FAIL: Wordline is not 0 when en=0 for address {addr}. Got {dut.wl.value}"

@cocotb.test()
async def transition1(dut):
    """Toggling High/Low en transitions with constant addr"""
    out_width = dut.OUT_WIDTH.value.integer
    # by default this should be 64

    dut._log.info(f"Starting Transition 1 row_decoder test with OUT_WIDTH={out_width}")
 
    for addr in range(out_width):
        dut.addr.value = addr
        await Timer(1, unit="ns")
        for en in range(3): # to test both high and low transitions
            en_val = en % 2
            dut.en.value = en_val
            await Timer(1, unit="ns")
            sample_coverage(dut)

            if en_val == 0:
                assert dut.wl.value == 0, f"FAIL: Wordline is not 0 when en=0 for address {addr}. Got {dut.wl.value}"
            elif en_val == 1:
                assert dut.wl.value == 1<<addr, f"FAIL: Wordline is not {1<<addr} when en=1 for address {addr}. Got {dut.wl.value}"

@cocotb.test()
async def transition2(dut):
    """Toggling High/Low en transitions with changing addr"""
    out_width = dut.OUT_WIDTH.value.integer
    # by default this should be 64

    dut._log.info(f"Starting Transition 2 row_decoder test with OUT_WIDTH={out_width}")

    for en in range(3):
        en_val = en % 2
        dut.en.value = en_val
        await Timer(1, unit="ns")

        for addr in range(out_width):
            dut.addr.value = addr
            await Timer(1, unit="ns")
            sample_coverage(dut)

            if en_val == 0:
                assert dut.wl.value == 0, f"FAIL: Wordline is not 0 when en=0 for address {addr}. Got {dut.wl.value}"
            elif en_val == 1:
                assert dut.wl.value == 1<<addr, f"FAIL: Wordline is not {1<<addr} when en=1 for address {addr}. Got {dut.wl.value}"


@cocotb.test()
async def coverage_report(dut):
    """Report accumulated functional coverage and export it to file.

    Runs last so it sees the points sampled by every preceding test. The
    coverage_db is a global singleton, so coverage accumulates across tests.
    """
    coverage_db.report_coverage(dut._log.info, bins=True)
    coverage_db.export_to_yaml(filename="row_decoder_coverage.yml")
    coverage_db.export_to_xml(filename="row_decoder_coverage.xml")
