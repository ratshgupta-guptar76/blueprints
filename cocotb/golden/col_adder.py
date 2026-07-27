# Golden Model for src/col_adder.sv

ROWS: int | None = None

# ---------- Golden Reference ----------
def golden_ref(pp_col: int) -> int:
    """Golden reference output — Single Column Vertical Reduction Tree

    Behaviour:
       Counts the set bits of one bit-column's partial products. Inputs are
       active-high and the sum is a plain pop-count

    Args:
        pp_col (int) : ROWS-bit column of active-high partial-product bits

    Returns:
        out (int) : sum = popcount(pp_col), range 0..ROWS

    Raise:
        RuntimeError : If ROWS has not been set by the testbench before use.
    """
    if (ROWS == None):
        raise RuntimeError("golden.row_decoder.ROWS not set")

    return bin(pp_col & ((1 << ROWS) - 1)).count("1")

def golden_tb() -> None:
    global ROWS
    ROWS = 32       # Simulate setting the golden.row_decoder.ROWS from tb
    assert golden_ref(0) == 0
    assert golden_ref((1 << ROWS) - 1) == ROWS
    assert golden_ref(0b1011) == 3
    print("col_adder golden_ref self-check passed")

if __name__ == '__main__':
    golden_tb()