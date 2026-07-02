import random

import cocotb
from cocotb.triggers import Timer
from cocotb_coverage.coverage import CoverPoint, coverage_db


# ==========================================================
# Design Constants
# ==========================================================

# Number of input bits in the column adder (64-bit column)
ROWS = 64

# Target functional coverage points for popcount values
POPCOUNT_BINS = [0, 1, 2, 4, 8, 16, 32, 48, 64]

# Internal handle used for lazy coverage model initialization
_sampler = None


# ==========================================================
# Reference Model
# ==========================================================

def popcount(value):
    """
    Golden reference model.

    Computes the number of 1 bits in an integer.

    This represents the expected output of the DUT column adder,
    which sums all bits in a 64-bit input column.
    """
    return bin(value).count("1")


# ==========================================================
# Coverage Model Creation
# ==========================================================

def initialize_coverage():
    """
    Creates the functional coverage model.

    This function defines the coverage point only once
    (lazy initialization pattern).

    Coverage tracked:
        top.popcount -> number of active bits in pp_col
    """

    global _sampler

    # Prevent redefining coverage multiple times
    if _sampler is not None:
        return

    # Define a coverage point on DUT input column
    @CoverPoint(
        "top.popcount",

        # Extract popcount from DUT signal safely
        xf=lambda dut: (
            popcount(dut.pp_col.value.to_unsigned())
            if dut.pp_col.value.is_resolvable
            else -1
        ),

        # Coverage bins we want to hit
        bins=POPCOUNT_BINS
    )
    def _sample(dut):
        pass

    # Store sampler function for later reuse
    _sampler = _sample


# ==========================================================
# Coverage Sampling
# ==========================================================

def sample_coverage(dut):
    """
    Samples functional coverage for the current DUT state.

    Ensures:
        - Coverage model is initialized
        - DUT signal is valid (no X/Z values)
    """

    if _sampler is None:
        initialize_coverage()

    # Only sample when signal is fully resolved
    if dut.pp_col.value.is_resolvable:
        _sampler(dut)


# ==========================================================
# Missing Coverage Analysis
# ==========================================================

def missing_popcount_bins():
    """
    Returns a list of coverage bins that have NOT yet been hit.

    Used by the coverage-driven test to determine
    what stimulus to generate next.
    """

    try:
        cp = coverage_db["top.popcount"]
    except KeyError:
        # Coverage not created yet → all bins are missing
        return POPCOUNT_BINS.copy()

    # Find bins that have zero hits
    return [
        b
        for b, hit in cp.detailed_coverage.items()
        if hit == 0
    ]


# ==========================================================
# Stimulus Generation
# ==========================================================

def generate_vector_with_popcount(count):
    """
    Generates a random 64-bit vector with exactly
    'count' number of bits set to 1.

    This allows deterministic control of DUT input
    for coverage closure.
    """

    if count == 0:
        return 0

    # Randomly choose bit positions to set
    positions = random.sample(range(ROWS), count)

    value = 0

    # Build bit-vector with selected bits set
    for p in positions:
        value |= (1 << p)

    return value


# ==========================================================
# Driver / Checker
# ==========================================================

async def apply_and_check(dut, stimulus, expected):
    """
    Applies input stimulus to DUT and verifies correctness.

    Steps:
        1. Drive input vector (pp_col)
        2. Wait for combinational logic to settle
        3. Sample functional coverage
        4. Check output validity (no X/Z)
        5. Compare DUT output with reference model
    """

    # Apply stimulus
    dut.pp_col.value = stimulus

    # Wait for combinational propagation
    await Timer(1, units="ns")

    # Sample coverage after DUT settles
    sample_coverage(dut)

    # Ensure output is valid
    assert dut.sum.value.is_resolvable, (
        "sum contains X/Z values"
    )

    # Read DUT result
    actual = dut.sum.value.to_unsigned()

    # Compare against expected result
    assert actual == expected, (
        f"\nMismatch"
        f"\nInput    : {stimulus:064b}"
        f"\nExpected : {expected}"
        f"\nActual   : {actual}"
    )


# ==========================================================
# Smoke Tests
# ==========================================================

async def run_smoke_tests(dut):
    """
    Basic sanity tests to verify DUT correctness
    before running full coverage closure.

    Tests:
        - All zeros input
        - All ones input
    """

    dut._log.info("Running smoke tests...")

    # Test: no bits set
    await apply_and_check(dut, 0, 0)

    # Test: all bits set
    await apply_and_check(
        dut,
        (1 << ROWS) - 1,
        ROWS
    )

    dut._log.info("Smoke tests passed.")


# ==========================================================
# Coverage Closure Engine
# ==========================================================

async def run_coverage_closure(dut):
    """
    Coverage-driven stimulus generator.

    Goal:
        Hit all defined popcount bins.

    Algorithm:
        1. Query missing coverage bins
        2. Select one missing bin
        3. Generate matching stimulus
        4. Apply and verify DUT
        5. Repeat until coverage complete
    """

    dut._log.info("Running coverage closure...")

    max_iterations = 100

    for _ in range(max_iterations):

        missing = missing_popcount_bins()

        # Stop when full coverage is reached
        if not missing:
            dut._log.info("Coverage closure complete.")
            return

        # Pick one uncovered bin
        target = random.choice(missing)

        # Generate stimulus that guarantees that popcount
        stimulus = generate_vector_with_popcount(target)

        await apply_and_check(dut, stimulus, target)

    raise AssertionError(
        f"Coverage not closed.\n"
        f"Missing bins: {missing_popcount_bins()}"
    )


# ==========================================================
# Coverage Reporting
# ==========================================================

def generate_coverage_report(dut):
    """
    Generates and exports coverage reports.

    Outputs:
        - Console coverage summary
        - YAML report
        - XML report
    """

    coverage_db.report_coverage(
        dut._log.info,
        bins=True
    )

    coverage_db.export_to_yaml(
        "col_adder_coverage.yml"
    )

    coverage_db.export_to_xml(
        "col_adder_coverage.xml"
    )


# ==========================================================
# Top-Level Cocotb Test
# ==========================================================

@cocotb.test()
async def test_col_adder(dut):
    """
    Full verification flow for the column adder DUT.

    Execution order:
        1. Initialize coverage model
        2. Run smoke tests
        3. Perform coverage-driven testing
        4. Generate coverage report

    Everything runs in one simulation to preserve
    coverage state across all phases.
    """

    initialize_coverage()

    await run_smoke_tests(dut)

    await run_coverage_closure(dut)

    generate_coverage_report(dut)