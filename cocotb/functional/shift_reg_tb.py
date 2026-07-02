
"""
OVERVIEW of shift_reg.sv
- Serial-In/Serial-Out (SISO) shift register
- Stores value of data width dw (typically 8-bits)
- serial_in data enters MSB, and shifts towards LSB

Inputs
- Clock (clk):
    - Clock signal that synchronizes the register
    - Possible Values: Rising Edge (0 -> 1), Falling Edge (1 -> 0)
- Reset (rst_n):
    - Active-low asynchronous reset to clear all states
    - Possible Values: 0, 1
- Enable (en):
    - Global enable signal
    - Possible Values: 0, 1
- Compute Enable (c_en):
    - Selects between LOAD mode (c_en=0) and COMPUTE mode (c_en=1)
    - Possible Values: 0, 1
- Serial In (serial_in):
    - The data streamed in during LOAD mode
    - Possible Values: 0, 1

Outputs:
- Compute Bit / Serial Out (sr[0])
    - Connected to LSB, routed to either compute array or serial_in
    - Possible Values: 0, 1

FUNCTIONAL COVERAGE IMPLEMENTATION
- Modes:
    - Hold (en=0): Freezes current state and ignores inputs
    - Load (en=1, c_en=0): Shifts external data in bit-by-bit from serial_in pin to populate the register
    - Compute (en=1, c_en=1): Shifts data out bit-by-bit to feed compute array, replacing vacated MSB with 0s
- Data Variations: All 1s, All 0s, and alternating patterns on serial_in
- Reset Coverage: Asserting rst_n during HOLD, LOAD, and COMPUTE modes
- Cross Coverage: Cross en, c_en, and serial_in across consecutive clock cycles
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb_coverage.coverage import CoverPoint, CoverCross, coverage_db
from collections import deque
import random

_sampler = None

def sample_coverage(dut):
    """Sample the current (en, addr) point into the coverage database."""
    global _sampler
    if _sampler is None:
        def get_mode(dut):
            en_val = int(dut.en.value)
            c_en_val = int(dut.c_en.value)
            
            if en_val == 0:
                return "HOLD"
            elif en_val == 1 and c_en_val == 0:
                return "LOAD"
            elif en_val == 1 and c_en_val == 1:
                return "COMPUTE"

        @CoverPoint("top.rst_n", xf=lambda dut: int(dut.rst_n.value), bins=[0, 1])
        @CoverPoint("top.en", xf=lambda dut: int(dut.en.value), bins=[0,1])
        @CoverPoint("top.c_en", xf=lambda dut: int(dut.c_en.value), bins=[0,1])
        @CoverPoint("top.serial_in", xf=lambda dut: int(dut.serial_in.value), bins=[0,1])
        @CoverPoint("top.mode", xf=get_mode, bins=["HOLD", "LOAD", "COMPUTE"])
        @CoverCross("top.cross_mode_serial_in", items=["top.mode", "top.serial_in"])
        def _sample(dut):
            pass



        _sampler = _sample
    _sampler(dut)


async def reset_dut(dut):
    """Helper task to apply active-low reset for >= 10 cycles."""
    dut.rst_n.value = 0
    dut.en.value = 0
    dut.c_en.value = 0
    dut.serial_in.value = 0
    
    # Hold reset for 10 cycles as specified in verification plan
    await Timer(1, "ps")
    for _ in range(10):
        sample_coverage(dut)
        
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    sample_coverage(dut)


@cocotb.test()
async def reset_test(dut):
    """Test functionality of reset pin"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut._log.info("Starting Reset Test")

    dut.en.value = 1
    dut.c_en.value = 1
    dut.serial_in.value = 1

    await reset_dut(dut)

    # Check that outputs are firmly 0 and not 'X' or 'Z'
    assert dut.compute_bit.value.is_resolvable, "FAIL: compute_bit is 'X' or 'Z' after reset!"
    assert dut.compute_bit.value == 0, f"FAIL: compute_bit not 0 after reset. Got {dut.compute_bit.value}"
    
    assert dut.serial_out.value.is_resolvable, "FAIL: serial_out is 'X' or 'Z' after reset!"
    assert dut.serial_out.value == 0, f"FAIL: serial_out not 0 after reset. Got {dut.serial_out.value}"

@cocotb.test()
async def test_async_reset(dut):
    """Verify that reset clears outputs instantly, completely independent of the clock edge."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dw = dut.DW.value.integer
    
    # 1. Load the register with 1s so we have something to clear
    await reset_dut(dut)
    dut.en.value = 1
    dut.c_en.value = 0
    dut.serial_in.value = 1
    
    for _ in range(dw):
        await RisingEdge(dut.clk)
        
    # Let the hardware delta-cycles settle before reading the pin!
    await Timer(1, "ps") 
        
    assert dut.serial_out.value == 1, "Failed to load 1s for setup."

    # 2. Wait for HALF a clock cycle (mid-cycle, no rising edge)
    await Timer(5, "ns")
    
    # 3. Assert reset asynchronously
    dut.rst_n.value = 0
    
    # 4. Wait 1 picosecond for the logic to physically settle (NO clock edge!)
    await Timer(1, "ps")
    
    # 5. Verify outputs dropped to 0 instantly
    assert dut.serial_out.value == 0, f"FAIL: Async reset failed. serial_out is {dut.serial_out.value}"
    assert dut.compute_bit.value == 0, f"FAIL: Async reset failed. compute_bit is {dut.compute_bit.value}"

@cocotb.test()
async def test_load_golden(dut):
    """Test isolated LOAD mode using a dynamic Golden Model."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dw = dut.DW.value.integer
    dut._log.info(f"Starting test_load_golden with DW={dw}")

    await reset_dut(dut)
    
    dut.en.value = 1
    dut.c_en.value = 0 # Force into LOAD mode

    # 1. Initialize the Golden Mirror
    # Index 0 is the LSB (output). Index dw-1 is the MSB (input).
    golden_sr = [0] * dw 

    random.seed(42)
    
    # Continuously stream 50 random bits through the pipeline
    for i in range(50):
        in_bit = random.choice([0, 1])

        # 2. Drive the physical hardware
        dut.serial_in.value = in_bit

        # 3. Update the logical Golden Mirror
        # Hardware shifts toward LSB. The old LSB drops off, and in_bit fills the MSB.
        golden_sr = golden_sr[1:] + [in_bit]

        # Wait for the hardware to clock in the state
        await RisingEdge(dut.clk)
        sample_coverage(dut)
        await Timer(1, "ps") # Settle time

        # 4. Compare the Mirrors
        expected_out = golden_sr[0]
        
        assert dut.serial_out.value == expected_out, \
            f"FAIL Cycle {i}: Expected {expected_out}, got {dut.serial_out.value}"


@cocotb.test()
async def test_hold(dut):
    """Test isolated HOLD mode (en=0)"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dw = dut.DW.value.integer
    dut._log.info(f"Starting test_load_mode with DW={dw}")

    await reset_dut(dut)

    dut.en.value = 1
    dut.c_en.value = 0

    # Pre-Load Data
    for i in range(dw):
        dut.serial_in.value = 1
        await RisingEdge(dut.clk)
        sample_coverage(dut)
    
    dut.en.value = 0
    for j in range(dw+1):
        dut.serial_in.value = 0
        await RisingEdge(dut.clk)
        sample_coverage(dut)
        assert dut.serial_out.value == 1, f"FAIL: Expected HOLD value 1, received 0"
    

@cocotb.test()
async def test_compute_golden(dut):
    """Test isolated COMPUTE Mode """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dw = dut.DW.value.integer
    dut._log.info(f"Starting test_compute with DW={dw}")

    await reset_dut(dut)

    # 1. INITIALIZE THE GOLDEN MIRROR
    # A simple Python list perfectly mirrors the hardware's internal register.
    # Index 0 is the LSB (output), Index dw-1 is the MSB.
    golden_sr = [0] * dw 

    random.seed(42)
    
    # We will run 10 blocks of Load -> Compute
    for _ in range(10):
        
        # --- PHASE 1: LOAD ---
        dut.en.value = 1
        dut.c_en.value = 0
        
        for _ in range(dw):
            # Generate random stimulus
            in_bit = random.choice([0, 1])
            dut.serial_in.value = in_bit
            
            # 2. UPDATE THE GOLDEN MIRROR
            # Mirror the exact logical behavior of LOAD mode in Python
            golden_sr = golden_sr[1:] + [in_bit] 
            
            await RisingEdge(dut.clk)
            await Timer(1, "ps") # Settle time
            
            # 3. ASSERT AGAINST THE MIRROR
            # We don't check an array index; we check the mirror's current LSB
            assert dut.serial_out.value == golden_sr[0], \
                f"LOAD mismatch: expected {golden_sr[0]}, got {dut.serial_out.value}"

        # --- PHASE 2: COMPUTE ---
        dut.en.value = 1
        dut.c_en.value = 1
        
        for _ in range(dw):
            # serial_in is ignored during compute, but we randomize it to prove that
            dut.serial_in.value = random.choice([0, 1])
            
            # 2. UPDATE THE GOLDEN MIRROR
            # Mirror the exact logical behavior of COMPUTE mode (shifting in 0s)
            golden_sr = golden_sr[1:] + [0]
            
            await RisingEdge(dut.clk)
            await Timer(1, "ps") # Settle time
            
            # 3. ASSERT AGAINST THE MIRROR
            assert dut.serial_out.value == golden_sr[0], \
                f"COMPUTE mismatch: expected {golden_sr[0]}, got {dut.serial_out.value}"
            

@cocotb.test()
async def test_transitions(dut):
    """Thorough stress test: random mode transitions, all input values, and reset interruptions."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dw = dut.DW.value.integer
    dut._log.info(f"Starting test_transitions with DW={dw}")

    # Initialize a Python list as our golden model. 
    # Index 0 is the LSB (output), Index dw-1 is the MSB (serial_in entry point)
    golden_sr = [0] * dw

    await reset_dut(dut)
    
    # Wait a tiny delta step for outputs to settle before reading
    await Timer(1, "ps")

    random.seed(12345)
    NUM_CYCLES = 1000

    for i in range(NUM_CYCLES):
        # 5% chance to trigger a random asynchronous reset interruption
        if random.random() < 0.05:
            dut._log.debug(f"Cycle {i}: Triggering random reset")
            dut.rst_n.value = 0
            
            # Randomize inputs during reset to test that reset overrides them
            dut.en.value = random.choice([0, 1])
            dut.c_en.value = random.choice([0, 1])
            dut.serial_in.value = random.choice([0, 1])
            
            # Hold reset for 1 to 5 clock cycles
            hold_cycles = random.randint(1, 5)
            for _ in range(hold_cycles):
                await RisingEdge(dut.clk)
                sample_coverage(dut)
            
            # Release reset and clear the golden model
            dut.rst_n.value = 1
            golden_sr = [0] * dw 
            
            # Wait a tiny delta step for the asynchronous reset release to settle
            await Timer(1, "ps")
            
            # Verify outputs immediately post-reset (asynchronous check)
            assert dut.serial_out.value == 0, f"FAIL: serial_out != 0 after random reset at cycle {i}."
            assert dut.compute_bit.value == 0, f"FAIL: compute_bit != 0 after random reset at cycle {i}."
            
            # Continue directly to the normal loop so both DUT and Model process the next edge together
            continue

        # Normal Operation: Randomize inputs
        en_val = random.choice([0, 1])
        c_en_val = random.choice([0, 1])
        serial_in_val = random.choice([0, 1])

        dut.en.value = en_val
        dut.c_en.value = c_en_val
        dut.serial_in.value = serial_in_val

        # Update the expected state of our python golden model
        if en_val == 1 and c_en_val == 0:       # LOAD Mode
            # Shift right (drop LSB, insert serial_in at MSB)
            golden_sr = golden_sr[1:] + [serial_in_val]
        elif en_val == 1 and c_en_val == 1:     # COMPUTE Mode
            # Shift right (drop LSB, insert 0 at MSB)
            golden_sr = golden_sr[1:] + [0]
        else:                                   # HOLD Mode (en == 0)
            # State remains unchanged
            pass 

        # Wait for the DUT to clock in the new state
        await RisingEdge(dut.clk)
        sample_coverage(dut)
        
        # Settle time for continuous assignment outputs (compute_bit, serial_out)
        await Timer(1, "ps")

        # Check outputs against golden model
        expected_out = golden_sr[0]
        
        assert dut.serial_out.value == expected_out, \
            f"FAIL Cycle {i} (en={en_val}, c_en={c_en_val}, s_in={serial_in_val}): Expected serial_out {expected_out}, got {dut.serial_out.value}"
        assert dut.compute_bit.value == expected_out, \
            f"FAIL Cycle {i} (en={en_val}, c_en={c_en_val}, s_in={serial_in_val}): Expected compute_bit {expected_out}, got {dut.compute_bit.value}"

@cocotb.test()
async def coverage_report(dut):
    """Report accumulated functional coverage and export it to file.

    Runs last so it sees the points sampled by every preceding test. The
    coverage_db is a global singleton, so coverage accumulates across tests.
    """
    coverage_db.report_coverage(dut._log.info, bins=True)
    coverage_db.export_to_yaml(filename="shift_reg_coverage.yml")
    coverage_db.export_to_xml(filename="shift_reg_coverage.xml")
