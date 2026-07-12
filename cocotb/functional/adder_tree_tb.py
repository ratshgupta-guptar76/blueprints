import cocotb
import random
from cocotb.triggers import Timer
from cocotb_coverage.coverage import CoverPoint, CoverCross, coverage_db

# =========================================================
# Helpers
# =========================================================

def get_rows_cols(dut):
    rows = dut.ROWS.value.to_unsigned()
    cols = dut.COLS.value.to_unsigned()
    return rows, cols


def flatten_pp(pp, rows, cols):
    """Convert 2D matrix -> flat integer bitvector"""
    flat = 0
    for r in range(rows):
        for c in range(cols):
            flat |= (pp[r][c] & 1) << (r * cols + c)
    return flat


def drive_pp(dut, pp, rows, cols):
    """Drive DUT input safely (NO indexing into DUT signals)"""
    dut.pp.value = flatten_pp(pp, rows, cols)


def popcount_columns(pp, rows, cols):
    """Golden model: column-wise popcount"""
    out = [0] * cols
    for c in range(cols):
        out[c] = sum(pp[r][c] for r in range(rows))
    return out


def read_sum_flat(dut, rows, cols):
    """
    Extract sum[] safely from packed DUT output.
    Assumes:
        sum[c] is contiguous block of bits per column
    """
    raw = dut.sum.value.integer

    # width per column = clog2(ROWS+1)
    bits_per_col = (rows + 1).bit_length()

    out = []
    mask = (1 << bits_per_col) - 1

    for c in range(cols):
        out.append((raw >> (c * bits_per_col)) & mask)

    return out


# =========================================================
# Coverage
# =========================================================

_sampler = None

def sample_coverage(dut):
    global _sampler

    if _sampler is None:

        @CoverPoint("top.pp_random", xf=lambda dut: int(dut.pp.value.integer & 1), bins=[0, 1])
        @CoverPoint("top.sum0", xf=lambda dut: int(dut.sum.value.integer & 0x7F), bins=list(range(0, 65)))
        @CoverCross("top.cross", items=["top.pp_random", "top.sum0"])
        def _sample(dut):
            pass

        _sampler = _sample

    _sampler(dut)


# =========================================================
# TESTS
# =========================================================

@cocotb.test()
async def test_zero_and_all_ones(dut):
    """Extreme cases: all 0s and all 1s"""

    rows, cols = get_rows_cols(dut)

    # -------------------
    # ALL ZEROS
    # -------------------
    pp = [[0 for _ in range(cols)] for _ in range(rows)]
    drive_pp(dut, pp, rows, cols)

    await Timer(1, "ps")
    sample_coverage(dut)

    sums = read_sum_flat(dut, rows, cols)
    assert all(s == 0 for s in sums), f"Zero test failed: {sums}"

    # -------------------
    # ALL ONES
    # -------------------
    pp = [[1 for _ in range(cols)] for _ in range(rows)]
    drive_pp(dut, pp, rows, cols)

    await Timer(1, "ps")
    sample_coverage(dut)

    sums = read_sum_flat(dut, rows, cols)
    assert all(s == rows for s in sums), f"All-ones failed: {sums}"


@cocotb.test()
async def test_random_data(dut):
    """Random correctness test vs golden popcount model"""

    rows, cols = get_rows_cols(dut)

    for _ in range(50):
        pp = [
            [random.randint(0, 1) for _ in range(cols)]
            for _ in range(rows)
        ]

        drive_pp(dut, pp, rows, cols)

        await Timer(1, "ps")
        sample_coverage(dut)

        expected = popcount_columns(pp, rows, cols)
        actual = read_sum_flat(dut, rows, cols)

        assert actual == expected, f"Mismatch:\nexp={expected}\nact={actual}"


@cocotb.test()
async def test_single_bit_per_column(dut):
    """Each column gets exactly one '1'"""

    rows, cols = get_rows_cols(dut)

    for c in range(cols):
        pp = [[0 for _ in range(cols)] for _ in range(rows)]
        r = random.randrange(rows)
        pp[r][c] = 1

        drive_pp(dut, pp, rows, cols)

        await Timer(1, "ps")
        sample_coverage(dut)

        sums = read_sum_flat(dut, rows, cols)

        for cc in range(cols):
            expected = 1 if cc == c else 0
            assert sums[cc] == expected, f"Col {cc} failed: {sums}"
            

@cocotb.test()
async def coverage_report(dut):
    """Export coverage after all tests"""
    coverage_db.report_coverage(dut._log.info, bins=True)
    coverage_db.export_to_yaml(filename="adder_tree_coverage.yml")
    coverage_db.export_to_xml(filename="adder_tree_coverage.xml")