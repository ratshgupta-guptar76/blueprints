import cocotb
import random
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb_coverage.coverage import CoverPoint, coverage_db
from cocotb.triggers import Timer


# =========================================================
# Helpers
# =========================================================

def get_params(dut):
    return dut.ROWS.value.to_unsigned(), dut.DW.value.to_unsigned()


def get_act_bp(dut):
    """Packed vector safe read (NO indexing of dut.act_bp[i])"""
    return dut.act_bp.value.to_unsigned()


def get_bit(vec, idx):
    return (vec >> idx) & 1


async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.en.value = 0
    dut.c_en.value = 0
    dut.a_b.value = 0

    for _ in range(3):
        await RisingEdge(dut.clk)

    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

async def tick(dut):
    dut.clk.value = 0
    await Timer(1, "ns")
    dut.clk.value = 1
    await Timer(1, "ns")

# =========================================================
# GOLDEN MODEL
# =========================================================

def load_step(chain, bit_in, rows):
    carry = bit_in
    for i in range(rows):
        new_carry = chain[i][0]
        chain[i] = chain[i][1:] + [carry]
        carry = new_carry
    return carry


def compute_step(chain, rows):
    act_bp = []
    for i in range(rows):
        act_bp.append(chain[i][0])
        chain[i] = chain[i][1:] + [0]
    return act_bp


# =========================================================
# COVERAGE
# =========================================================

_sampler = None

def sample_coverage(dut):
    global _sampler

    if _sampler is None:

        @CoverPoint("top.en", xf=lambda d: int(d.en.value), bins=[0, 1])
        @CoverPoint("top.c_en", xf=lambda d: int(d.c_en.value), bins=[0, 1])
        @CoverPoint("top.a_b", xf=lambda d: int(d.a_b.value), bins=[0, 1])
        @CoverPoint("top.tail", xf=lambda d: int(d.tail_out.value), bins=[0, 1])
        def _sample(dut):
            pass

        _sampler = _sample

    _sampler(dut)


# =========================================================
# TESTS
# =========================================================

@cocotb.test()
async def test_load_mode(dut):
    """LOAD mode correctness"""

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    rows, dw = get_params(dut)
    await reset_dut(dut)

    dut.en.value = 1
    dut.c_en.value = 0

    chain = [[0] * dw for _ in range(rows)]

    for _ in range(rows * dw * 2):

        bit = random.randint(0, 1)
        dut.a_b.value = bit

        await RisingEdge(dut.clk)

        expected_tail = load_step(chain, bit, rows)

        sample_coverage(dut)

        assert int(dut.tail_out.value) == expected_tail


# =========================================================
@cocotb.test()
async def test_compute_mode(dut):
    """Verify compute mode bit-plane correctness (FIXED timing)"""

    rows = dut.ROWS.value.to_unsigned()
    dw = dut.DW.value.to_unsigned()

    # preload chain
    chain = [[random.randint(0, 1) for _ in range(dw)] for _ in range(rows)]

    dut.en.value = 1
    dut.c_en.value = 0

    # warm-up load phase
    for _ in range(10):
        dut.a_b.value = random.randint(0, 1)

        carry = dut.a_b.value
        for i in range(rows):
            new_carry = chain[i][0]
            chain[i] = chain[i][1:] + [carry]
            carry = new_carry

        await tick(dut)

# switch to compute
    dut.c_en.value = 1

    for cycle in range(dw):
        # 1. SAMPLE THE CURRENT STATE BEFORE THE CLOCK EDGE
        current_bp = dut.act_bp.value

        for i in range(rows):
            expected = chain[i][0]
            
            # Keep original straightforward indexing order
            got = int(current_bp[i])
            
            assert got == expected, f"cycle {cycle}, row {i}: expected {expected}, got {got}"

        # 2. UPDATE THE PYTHON MODEL FOR THE NEXT CYCLE
        for i in range(rows):
            chain[i] = chain[i][1:] + [0]

        # 3. ADVANCE CLOCK
        await tick(dut)

        # 1. SAMPLE AND ASSERT BEFORE THE CLOCK EDGE (Since act_bp is combinational)
        for i in range(rows):
            expected = chain[i][0]
            # Indexing the handle directly avoids string/endian reversal issues
            got = dut.act_bp[i].value.integer 
            assert got == expected, f"cycle {cycle}, row {i}: expected {expected}, got {got}"

        # 2. UPDATE THE PYTHON MODEL FOR THE NEXT CYCLE
        for i in range(rows):
            chain[i] = chain[i][1:] + [0]

        # 3. ADVANCE CLOCK
        await tick(dut)
# =========================================================

@cocotb.test()
async def test_random_stress(dut):
    """FULL stress test (fixed packed handling + timing)"""

    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())

    rows, dw = get_params(dut)
    await reset_dut(dut)

    chain = [[0] * dw for _ in range(rows)]

    for cycle in range(300):

        dut.en.value = 1
        dut.c_en.value = random.randint(0, 1)
        dut.a_b.value = random.randint(0, 1)

        await RisingEdge(dut.clk)

        if dut.c_en.value == 0:
            expected_tail = load_step(chain, int(dut.a_b.value), rows)
        else:
            expected_bp = compute_step(chain, rows)
            expected_tail = chain[-1][0]

            actual = get_act_bp(dut)

            for i in range(rows):
                assert get_bit(actual, i) == expected_bp[i], \
                    f"cycle {cycle}, row {i}"

        assert int(dut.tail_out.value) == expected_tail

        sample_coverage(dut)

# =========================================================

@cocotb.test()
async def coverage_report(dut):
    coverage_db.report_coverage(dut._log.info, bins=True)
    coverage_db.export_to_yaml(filename="act_shift_chain_coverage.yml")
    coverage_db.export_to_xml(filename="act_shift_chain_coverage.xml")