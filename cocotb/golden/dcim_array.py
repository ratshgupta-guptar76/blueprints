# Golden Model for src/col_adder.sv

ROWS : int | None = None        # Default Null value for golden_tb(). 
COLS : int | None = None        # Value overwritten during actual testing.
DW   : int | None = None

# ---------- Golden Reference ----------
def golden_ref(w_mem: list[int], w_en: int, row_addr: int, w_buf: int,
               act_bp: int) -> tuple[list[int], list[int]]:
    """Golden reference — one clock step of dcim_array (from spec, not RTL)

    Behaviour:
       Combinational multiply on the CURRENT weight memory (pp[r] = w_mem[r] gated
       by act_bp[r], active-high), then a registered single-row write: w_en selects
       one row (row_addr) to latch w_buf, all others hold; w_en=0 writes nothing.
       w_mem threaded across calls. Observe storage only through pp (no read port).

    Args:
        w_mem (list[int]) : ROWS rows, each a COLS-bit weight row (current state)
        w_en (int)        : write enable (1 = latch selected row)
        row_addr (int)    : row to write when w_en
        w_buf (int)       : COLS-bit row value to write
        act_bp (int)      : ROWS-bit activation plane; bit r gates row r

    Returns:
        tuple[list[int], list[int]]
            - pp         : ROWS product rows THIS cycle (combinational)
            - next_w_mem : weight memory after the write edge
    """
    if ROWS is None:
        raise RuntimeError("golden.row_decoder.ROWS not set")

    if COLS is None:
        raise RuntimeError("golden.row_decoder.COLS not set")

    if DW is None:
        raise RuntimeError("golden.row_decoder.TOT not set")

    mask = (1 << COLS) - 1
    pp = [w_mem[r] & (mask if (act_bp >> r) & 1 else 0) for r in range(ROWS)]
    if w_en:
        nxt = list(w_mem)
        nxt[row_addr] = w_buf & mask
        return pp, nxt
    return pp, list(w_mem)


def golden_tb() -> None:
    global ROWS
    global COLS
    global DW
    # Simulate setting the golden.row_decoder.DW from tb
    ROWS = 32
    COLS = 32
    DW   = 8

    full = (1 << COLS) - 1

    # 1. WRITE-SELECT — writing row k changes only row k
    w_mem = [0] * ROWS
    _, w_mem = golden_ref(w_mem, 1, 5, 0xABCD, 0)
    assert w_mem[5] == (0xABCD & full) and all(w_mem[r] == 0 for r in range(ROWS) if r != 5), \
        "write hit wrong/extra row"

    # 2. NO STRAY WRITE — w_en=0 changes nothing
    before = list(w_mem)
    _, w_mem = golden_ref(w_mem, 0, 9, 0xFFFF, 0)
    assert w_mem == before, "w_en=0 must not write"

    # 3. AND-AXIS — act_bp[r]=1 -> pp[r]=w_mem[r]; =0 -> pp[r]=0
    w_mem = [((r * 13 + 1) & full) for r in range(ROWS)]
    act = 0b101 & ((1 << ROWS) - 1)
    pp, _ = golden_ref(w_mem, 0, 0, 0, act)
    for r in range(ROWS):
        assert pp[r] == (w_mem[r] if (act >> r) & 1 else 0), f"AND axis wrong at row {r}"

    # 4. AND-AXIS is per-ROW not per-column — only row 3 active, all-ones rows
    w_mem = [full] * ROWS
    pp, _ = golden_ref(w_mem, 0, 0, 0, 1 << 3)
    assert pp[3] == full and all(pp[r] == 0 for r in range(ROWS) if r != 3), \
        "broadcast axis crossed (act must gate a ROW, not a column)"

    # 5. COLUMN MAPPING — write a sub-weight, read its DW columns back via pp
    w_mem = [0] * ROWS
    w0 = 0b10110001
    _, w_mem = golden_ref(w_mem, 1, 0, w0, 0)
    pp, _ = golden_ref(w_mem, 0, 0, 0, 1 << 0)
    assert (pp[0] & ((1 << DW) - 1)) == w0, f"column mapping: got {pp[0] & 0xFF:#x}, exp {w0:#x}"

    print("dcim_array golden_ref self-check passed")

if __name__ == '__main__':
    golden_tb()