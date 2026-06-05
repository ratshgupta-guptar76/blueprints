import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ReadOnly
import random

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
    """Test MAC with random 8-bit integers."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    await reset_dut(dut)
    
    expected_acc = 0

    dut._log.info("Starting randomized MAC test...")

    for i in range(50):
        # 1. Advance time to the falling edge to unlock the simulator
        await FallingEdge(dut.clk)

        # 2. Drive hardware pins (data is now safely stable before the rising edge)
        val_a = random.randint(-128, 127)
        val_b = random.randint(-128, 127)
        dut.a.value = val_a
        dut.b.value = val_b
        dut.valid_in.value = 1

        # 3. Trigger the active rising clock edge where math happens
        await RisingEdge(dut.clk)
        
        # 4. Wait for the hardware registers to settle into a readable state
        await ReadOnly()

        # Update golden model
        expected_acc += (val_a * val_b)

        # Read hardware output
        actual_acc = dut.acc.value.to_signed()

        # Compare
        assert actual_acc == expected_acc, f"FAIL on cycle {i}: Expected {expected_acc}, got {actual_acc}"
        
    dut._log.info("SUCCESS: All 50 MAC cycles matched the Python golden model!")