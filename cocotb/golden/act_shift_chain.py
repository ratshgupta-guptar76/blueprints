# Golden Model for src/act_shift_chain.sv

ROWS : int | None = None       # Default Null value for golden_tb(). 
DW   : int | None = None       # Value overwritten during actual testing.

# ---------- Golden Reference ----------
def golden_ref(cells: list[int], en: int, c_en: int, a_b: int) -> tuple[list[int], int, list[int]]:
    """Computes the golden reference output for One clock step of act_shift_chain

    Behaviour:
       Models ROWS cascaded DW-bit shift cells. LOAD cascades a_b through cell 0
       toward the LSB, cell i's LSB feeding cell i+1's MSB. COMPUTE zero-fills and
       shifts each cell, exposing act_bp[i]=cell i sr[0]. en=0 holds. act_bp is
       sampled BEFORE the shift (combinational tap). cells threaded across calls.
       Chain reverses row order: cell i ends holding the (ROWS-1-i)-th streamed byte.

    Args:
        cells (list[int]) : ROWS cells, each a DW-bit shift register (current state)
        en (int)          : master enable (0 holds)
        c_en (int)        : 1 COMPUTE (zero-fill), 0 LOAD (cascade a_b)
        a_b (int)         : serial activation bit into cell 0 (LOAD only)

    Returns:
        tuple[list[int], int, list[int]]
            - act_bp    : ROWS bits, act_bp[i] = cell i sr[0] THIS cycle
            - tail_out  : bit leaving the last cell (LOAD); 0 in COMPUTE
            - next_cells: cells after the edge
    
    Raises:
        RuntimeError : If ROWS or DW has not been set by the testbench before use.
    """
    if ROWS is None:
        raise RuntimeError("golden.act_shift_chain.ROWS not set")

    if DW is None:
        raise RuntimeError("golden.act_shift_chain.DW not set")

    act_bp = [cells[i] & 1 for i in range(ROWS)]          # comb tap, before shift
    if not en:
        return act_bp, cells[ROWS-1] & 1, list(cells)
    nxt = list(cells)
    if c_en:                                              # COMPUTE
        nxt = [(cells[i] >> 1) & ((1 << DW) - 1) for i in range(ROWS)]
        tail = 0
    else:                                                 # LOAD: cascade
        carry = a_b
        for i in range(ROWS):
            out_bit = nxt[i] & 1
            nxt[i] = ((carry << (DW - 1)) | (nxt[i] >> 1)) & ((1 << DW) - 1)
            carry = out_bit
        tail = carry
    return act_bp, tail, nxt

def golden_tb() -> None:
    global ROWS
    global DW
    # simulate setting the golden.act_shift_chain.ROWS and DW from tb
    ROWS = 32
    DW   = 8
    
    acts = [(r * 7 + 3) & 0xFF for r in range(ROWS)]      # distinct per row
    cells = [0] * ROWS

    # LOAD row 0 first ... row ROWS-1 last, each byte LSB-first
    for r in range(ROWS):
        for b in range(DW):
            _, _, cells = golden_ref(cells, en=1, c_en=0, a_b=(acts[r] >> b) & 1)

    # COMPUTE: drain DW planes, reconstruct each cell's byte LSB-first
    rec = [0] * ROWS
    for p in range(DW):
        act_bp, _, cells = golden_ref(cells, en=1, c_en=1, a_b=0)
        for i in range(ROWS):
            rec[i] |= act_bp[i] << p

    # documented reversal: cell i holds row (ROWS-1-i)'s activation
    assert all(rec[i] == acts[ROWS-1-i] for i in range(ROWS)), \
        f"chain mapping wrong: {rec}"

    # en=0 holds
    _, _, held = golden_ref(cells, en=0, c_en=1, a_b=1)
    assert held == cells, "en=0 must hold"

    print("act_shift_chain golden_ref self-check passed")


golden_tb()
