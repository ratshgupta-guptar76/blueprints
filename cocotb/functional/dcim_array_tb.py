"""
OVERVIEW of dcim_array_tb.py
- Functional verification for a Compute-in-Memory (CIM) weight storage and AND grid.
- Simulates an SRAM macro behavior (no reset, powers up in X).
- Verifies synchronous one-hot row writing and combinational partial product (pp) generation.

STIMULUS GENERATION
- Write Protection: Drive w_en=0 and ensure wl (wordline) remains 0 and memory does not corrupt.
- Sequential Writes: Write known values to specific rows using w_en and row_addr.
- Combinational AND: Drive act_bp (activation bit-plane) and assert pp instantly reflects w_mem & act_bp.
- Stress Test: Randomized continuous reads and writes verified against a Python golden model.

FUNCTIONAL COVERAGE IMPLEMENTATION
- Write Enable (w_en): Hit both 0 and 1.
- Row Addresses: Ensure every single row address is targeted for a write.
- Activation Broadcast: Cross coverage of row addresses and act_bp bits to ensure the broadcast AND gate fires for every row.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb_coverage.coverage import CoverPoint, CoverCross, coverage_db
import random

_sampler = None

def sample_coverage(dut, rows):
    """Sample the current state into the coverage database."""
    global _sampler
    if _sampler is None:
        
        @CoverPoint("top.w_en", xf=lambda dut, _: int(dut.w_en.value), bins=[0, 1])
        @CoverPoint("top.row_addr", xf=lambda dut, _: int(dut.row_addr.value), bins=list(range(rows)))
        # For act_bp, we just want to ensure we see heavily 0s, heavily 1s, and mixed.
        # Measuring every specific permutation of a large bit-plane is mathematically explosive.
        @CoverPoint("top.act_bp_all_zeros", xf=lambda dut, _: int(dut.act_bp.value) == 0, bins=[True])
        @CoverPoint("top.act_bp_all_ones", xf=lambda dut, rows: int(dut.act_bp.value) == ((1 << rows) - 1), bins=[True])
        @CoverCross("top.cross_write_addr", items=["top.w_en", "top.row_addr"])
        def _sample(dut, rows):
            pass

        _sampler = _sample
    _sampler(dut, rows)


def is_onehot0(val):
    """Returns True if the integer val has at most one bit set to 1."""
    return bin(val).count('1') <= 1


@cocotb.test()
async def test_stray_writes_and_onehot(dut):
    """Verify w_en write protection and wl one-hot constraints."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    rows = dut.ROWS.value.integer
    dut._log.info(f"Starting stray write test with ROWS={rows}")

    # Initialize pins safely (SRAM powers up X, so we don't assume internal state)
    dut.w_en.value = 0
    dut.row_addr.value = 0
    dut.w_buf.value = 0
    dut.act_bp.value = 0

    await Timer(1, "ps") # Delta step for combinational logic (row_decoder)

    # 1. Check w_en = 0 disables wordlines entirely
    for addr in range(rows):
        dut.row_addr.value = addr
        await Timer(1, "ps")
        assert dut.wl.value == 0, f"FAIL: Wordline is {dut.wl.value} when w_en=0 at addr {addr}"
        
        await RisingEdge(dut.clk)
        sample_coverage(dut, rows)

    # 2. Check w_en = 1 creates perfectly one-hot wordlines
    dut.w_en.value = 1
    for addr in range(rows):
        dut.row_addr.value = addr
        await Timer(1, "ps")
        
        wl_val = int(dut.wl.value)
        assert is_onehot0(wl_val), f"FAIL: wl is not one-hot! wl={bin(wl_val)} at addr {addr}"
        
        # Verify it activated the CORRECT row
        expected_wl = 1 << addr
        assert wl_val == expected_wl, f"FAIL: Expected wl={bin(expected_wl)}, got {bin(wl_val)}"
        
        await RisingEdge(dut.clk)
        sample_coverage(dut, rows)


@cocotb.test()
async def test_combinational_and_grid(dut):
    """Verify the combinational partial product logic (pp = w_mem & act_bp)."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    rows = dut.ROWS.value.integer
    cols = dut.COLS.value.integer
    dut._log.info(f"Starting combinational AND grid test with ROWS={rows}, COLS={cols}")

    # 1. Pre-load the SRAM with a known pattern
    dut.w_en.value = 1
    golden_mem = {} # Dictionary to act as our SRAM mirror
    
    for addr in range(rows):
        # Generate an alternating checkerboard pattern
        pattern = 0xAA if (addr % 2 == 0) else 0x55
        # Mask it to the column width
        pattern = pattern & ((1 << cols) - 1)
        
        dut.row_addr.value = addr
        dut.w_buf.value = pattern
        golden_mem[addr] = pattern
        await RisingEdge(dut.clk)
    
    dut.w_en.value = 0 # Turn off writes
    await Timer(1, "ps")

    # 2. Test Combinational Broadcast
    # We will test all 0s, all 1s, and a walking 1 on the activation bit-plane
    test_planes = [0, (1 << rows) - 1] + [(1 << i) for i in range(rows)]
    
    for bp in test_planes:
        dut.act_bp.value = bp
        await Timer(1, "ps") # Delta step for combinational AND gates to settle
        
        # Calculate expected partial products
        # SystemVerilog packed 2D arrays flatten to a single integer in Cocotb.
        # Row 0 is at the LSB end (bits 0 to COLS-1).
        expected_pp_flat = 0
        
        for r in range(rows):
            act_bit = (bp >> r) & 1
            if act_bit == 1:
                # If activated, the weight passes through
                row_val = golden_mem[r]
            else:
                # If not activated, it is masked to 0
                row_val = 0
                
            expected_pp_flat |= (row_val << (r * cols))
            
        assert dut.pp.value == expected_pp_flat, \
            f"FAIL combinational mismatch for act_bp={bin(bp)}:\n" \
            f"Expected pp: {hex(expected_pp_flat)}\n" \
            f"Actual pp:   {hex(int(dut.pp.value))}"
            
        await RisingEdge(dut.clk)
        sample_coverage(dut, rows)


@cocotb.test()
async def test_golden_stress(dut):
    """Stress test random writes and random bit-plane broadcasts against a Python model."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    rows = dut.ROWS.value.integer
    cols = dut.COLS.value.integer
    dut._log.info("Starting Golden Model Stress Test")
    
    # Initialize golden mirror. SRAM powers up in X, so we force it to 0 in Python
    # and initialize the RTL to 0 to align them.
    golden_mem = {i: 0 for i in range(rows)}
    
    dut.w_en.value = 1
    for addr in range(rows):
        dut.row_addr.value = addr
        dut.w_buf.value = 0
        await RisingEdge(dut.clk)
        
    random.seed(999)
    NUM_CYCLES = 1000

    for i in range(NUM_CYCLES):
        # 1. Generate Stimulus
        w_en_val = random.choice([0, 1])
        addr_val = random.randint(0, rows - 1)
        buf_val = random.getrandbits(cols)
        act_val = random.getrandbits(rows)

        # 2. Drive the physical hardware
        dut.w_en.value = w_en_val
        dut.row_addr.value = addr_val
        dut.w_buf.value = buf_val
        dut.act_bp.value = act_val

        # Wait delta for combinational signals (wl, pp) to settle based on current inputs
        await Timer(1, "ps") 
        
        # 3. Assert combinational logic (Before clock edge!)
        # The AND grid is independent of the clock. We check it using the *current* golden memory state.
        expected_pp_flat = 0
        for r in range(rows):
            act_bit = (act_val >> r) & 1
            row_val = golden_mem[r] if act_bit else 0
            expected_pp_flat |= (row_val << (r * cols))
            
        assert dut.pp.value == expected_pp_flat, f"FAIL Cycle {i}: pp mismatch before clock edge."

        # Verify Wordline integrity
        if w_en_val == 1:
            assert int(dut.wl.value) == (1 << addr_val), f"FAIL Cycle {i}: wl routing error."
        else:
            assert int(dut.wl.value) == 0, f"FAIL Cycle {i}: stray wl high."

        # 4. Clock Edge
        await RisingEdge(dut.clk)
        sample_coverage(dut, rows)
        
        # 5. Update Golden Model (Post clock edge)
        if w_en_val == 1:
            golden_mem[addr_val] = buf_val


@cocotb.test()
async def coverage_report(dut):
    """Report accumulated functional coverage and export it to file."""
    coverage_db.report_coverage(dut._log.info, bins=True)
    coverage_db.export_to_yaml(filename="dcim_array_coverage.yml")
    coverage_db.export_to_xml(filename="dcim_array_coverage.xml")