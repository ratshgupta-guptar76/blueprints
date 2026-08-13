# ======================================================================================
# Golden reference for src/dcim_array.sv  (4x sram_32x8_9T macro version)
#
# Written from the SPEC, not the RTL.
#
# CONTRACT
#   Write (LEVEL-SENSITIVE, transparent — no clock on this module):
#       w_en=1 -> mem[row_addr] tracks w_buf continuously while asserted
#       w_en=0 -> no row changes
#   Read (combinational, ACTIVE-HIGH):
#       pp[r][c] = mem[r][c] AND act_bp[r]      (act_bp gates a ROW, not a column)
#   Column layout:
#       column c holds bit (c % DW) of weight (c // DW); weight w is stored by
#       macro w, which takes w_buf[w*DW +: DW].
#   Storage powers up X. All rows must be written before any read.
#
# NOTE on ordering: pp is computed on the POST-write memory. The macro write is
# a transparent latch, not a flop, so there is no clock edge separating the write
# from the read — a row written and activated in the same delta reads the NEW
# value. Modelling this as a registered write (pp on pre-write memory) would be
# wrong and would silently disagree with the DUT.
# ======================================================================================

ROWS: int | None = None
COLS: int | None = None
DW:   int | None = None
N_W:  int | None = None
MASK: int | None = None


def golden_ref(mem: list[int], w_en: int, row_addr: int, w_buf: int,
               act_bp: int) -> tuple[list[int], list[int]]:
    """Golden reference — one evaluation of dcim_array (level-sensitive write).

    Behaviour:
        Applies the transparent write first (w_en selects one row, which latches
        w_buf), then computes the combinational AND read on the resulting memory.
        mem is threaded across calls by the caller.

    Args:
        mem (list[int])  : ROWS rows, each a COLS-bit weight row (current state)
        w_en (int)       : write enable — level, not edge
        row_addr (int)   : row selected while w_en is high
        w_buf (int)      : COLS-bit value driven onto the write bitlines
        act_bp (int)     : ROWS-bit activation plane; bit r gates row r

    Returns:
        tuple[list[int], list[int]]
            - pp        : ROWS product rows for this input state
            - next_mem  : memory after the (transparent) write

    Raises:
        RuntimeError: If ROWS/COLS/DW have not been set by the testbench.
    """
    if ROWS is None or COLS is None or MASK is None:
        raise RuntimeError("golden.dcim_array params not set — tb must sync from the DUT")

    nxt = list(mem)
    if w_en:
        nxt[row_addr] = w_buf & MASK

    return [nxt[r] & (MASK if (act_bp >> r) & 1 else 0) for r in range(ROWS)], nxt


def golden_tb() -> None:
    global ROWS, COLS, DW, N_W, MASK
    ROWS, COLS, DW = 32, 32, 8
    N_W = COLS // DW
    MASK = (1 << COLS) - 1

    # write-select: only the addressed row changes
    mem = [0] * ROWS
    _, mem = golden_ref(mem, 1, 5, 0xABCD1234, 0)
    assert mem[5] == 0xABCD1234 and all(mem[r] == 0 for r in range(ROWS) if r != 5)

    # no stray write
    before = list(mem)
    _, mem = golden_ref(mem, 0, 9, 0xFFFFFFFF, 0)
    assert mem == before

    # AND axis is per-ROW, not per-column
    mem = [MASK] * ROWS
    pp, _ = golden_ref(mem, 0, 0, 0, 1 << 3)
    assert pp[3] == MASK and all(pp[r] == 0 for r in range(ROWS) if r != 3)

    # column mapping: four distinct weights, one per DW-column group
    mem = [0] * ROWS
    ws = [0b10110001, 0b01001110, 0b11110000, 0b00001111]
    word = sum(ws[w] << (w * DW) for w in range(N_W))
    _, mem = golden_ref(mem, 1, 0, word, 0)
    pp, _ = golden_ref(mem, 0, 0, 0, 1 << 0)
    for w in range(N_W):
        assert (pp[0] >> (w * DW)) & ((1 << DW) - 1) == ws[w]

    # transparent latch: a row written and activated together reads the NEW value
    mem = [0] * ROWS
    pp, _ = golden_ref(mem, 1, 7, 0xFF, 1 << 7)
    assert pp[7] == 0xFF, "transparent write must be visible in the same evaluation"

    print("dcim_array golden_ref self-check passed")

golden_tb()