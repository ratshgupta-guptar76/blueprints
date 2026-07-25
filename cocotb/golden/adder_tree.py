# Golden Model for src/adder_tree.sv

ROWS : int | None = None        # Default Null value for golden_tb().
COLS : int | None = None        # Value overwritten during actual testing.

# ---------- Golden Reference ----------
def golden_ref(pp: list[int]) -> list[int]:
    """Golden reference output — Vertical Reduction Tree per-column vector

    Behaviour:
       Computes sum[c] as the popcount of c across all rows.

    Args:
        pp (list[int]) : packed partial-product matrix. Row-Major.

    Returns:
        out (list[int]) : sum[c] = popcount( pp[c] ), range 0..ROWS

    Raises:
        RuntimeError : If ROWS or COLS has not been set by the testbench before use.
    """
    if ROWS is None:
        raise RuntimeError("golden.adder_tree.ROWS not set")

    if COLS is None:
        raise RuntimeError("golden.adder_tree.COLS not set")

    return [sum((pp[r] >> c) & 1 for r in range(ROWS)) for c in range(COLS)]

def golden_tb() -> None:
    global ROWS
    global COLS
    # simulate setting the golden.adder_tree.ROWS and COLS from tb
    ROWS = 32
    COLS = 32

    # --- transpose / mapping: single-bit-set pins column c, not row r ---
    pp = [0]*ROWS; pp[3] = 1 << 7                      # pp[3][7] = 1
    s = golden_ref(pp)
    assert s[7] == 1 and sum(s) == 1, f"pp[3][7]=1 -> {s}, expected only sum[7]=1"

    # --- matrix corners (catch row/col swap + boundary indexing) ---
    pp = [0]*ROWS; pp[0] = 1 << 0                      # pp[0][0]
    assert golden_ref(pp)[0] == 1 and sum(golden_ref(pp)) == 1
    pp = [0]*ROWS; pp[ROWS-1] = 1 << (COLS-1)          # pp[ROWS-1][COLS-1]
    assert golden_ref(pp)[COLS-1] == 1 and sum(golden_ref(pp)) == 1

    # --- off-diagonal distinguishes a symmetric swap ---
    pp = [0]*ROWS; pp[0] = 1 << (COLS-1)               # pp[0][COLS-1]
    assert golden_ref(pp)[COLS-1] == 1 and sum(golden_ref(pp)) == 1

    # --- full column: column 5 set in every row -> sum[5] == ROWS ---
    pp = [1 << 5]*ROWS
    s = golden_ref(pp)
    assert s[5] == ROWS and sum(s) == ROWS, f"full col 5 -> {s}"

    # --- bounds ---
    assert golden_ref([0]*ROWS) == [0]*COLS
    assert golden_ref([(1 << COLS)-1]*ROWS) == [ROWS]*COLS

    print("adder_tree golden_ref self-check passed")

if __name__ == "__main__":
    golden_tb()