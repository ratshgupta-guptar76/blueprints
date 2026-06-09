import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ReadOnly
import random
import os

# Import the golden model you built
from golden_model import GoldenModel

async def reset_dut(dut):
    """Reset the hardware."""
    dut.rst_n.value = 0
    dut.valid_in.value = 0
    dut.a.value = 0
    dut.b.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

@cocotb.test()
async def test_mac_random_math(dut):
    """Test MAC with parameterized, bit-accurate golden model integration."""
    
    # 1. Pull configuration from the environment variables (set by scheduler)
    # Defaulting to 50 cycles, INT8, and seed 42 if run manually without the scheduler
    num_cycles = int(os.environ.get('NUM_CYCLES', 50))
    precision = int(os.environ.get('PRECISION', 8))
    seed = int(os.environ.get('RANDOM_SEED', 42))

    # Lock in the randomness for reproducibility
    random.seed(seed)
    
    dut._log.info(f"Starting randomized MAC test: {num_cycles} cycles | INT{precision} | Seed: {seed}")

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # 2. Initialize Golden Model and calculate accumulator width
    gm = GoldenModel(overflow_type='wrap')
    
    # Assuming length=1 for a basic single MAC operation. 
    # If this was an 8x8 array, length would be 8.
    acc_width = gm.calculate_width(length=1, precision=precision) 
    
    # Initialize expected sum perfectly wrapped to hardware width
    expected_acc = gm.fxp_wrap(0, acc_width)

    # Determine min/max values based on precision (e.g., INT8 -> -128 to 127)
    max_val = (1 << (precision - 1)) - 1
    min_val = -(1 << (precision - 1))

    for i in range(num_cycles):
        await FallingEdge(dut.clk)

        # Drive hardware pins with precision-aware random values
        val_a = random.randint(min_val, max_val)
        val_b = random.randint(min_val, max_val)
        dut.a.value = val_a
        dut.b.value = val_b
        dut.valid_in.value = 1

        await RisingEdge(dut.clk)
        await ReadOnly()

        # 3. Update golden model with strict width enforcement
        x = gm.fxp_wrap(val_a, precision)
        y = gm.fxp_wrap(val_b, precision)
        
        # Calculate raw math, then immediately force wrap to accumulator width
        raw_sum = expected_acc + (x * y)
        expected_acc = gm.fxp_wrap(raw_sum, acc_width)

        # Read hardware output
        actual_acc = dut.acc.value.to_signed()

        # 4. Compare (cast the Fxp object back to a standard int for the assertion)
        assert actual_acc == int(expected_acc), f"FAIL on cycle {i}: Expected {int(expected_acc)}, got {actual_acc}"
        
    dut._log.info(f"SUCCESS: All {num_cycles} MAC cycles perfectly matched the Golden Model!")


@cocotb.test()
async def test_mac_smoke(dut):
    """Barebones smoke test."""
    # (Leaving this largely identical to your original, just showing it stays here)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    
    await FallingEdge(dut.clk)
    dut.a.value = 2
    dut.b.value = 3
    dut.valid_in.value = 1
    
    await RisingEdge(dut.clk)
    await ReadOnly()
    
    actual_acc = dut.acc.value.to_signed()
    assert actual_acc == 6, f"FAIL: Expected 6, got {actual_acc}"
    dut._log.info("SUCCESS: Basic 2x3 math smoke test passed!")