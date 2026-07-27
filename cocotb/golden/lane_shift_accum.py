# Golden Model for src/lane__shift_accum.sv
from golden.helpers import _combine, to_signed

ROWS      : int | None = None        # Default Null value for golden_tb(). 
DW        : int | None = None        # Value overwritten during actual testing.
ACC_WIDTH : int | None = None
A_SIGN    : int | None = None
W_SIGN    : int | None = None

def golden_ref(y: int, clr: int, en: int, bp_idx: int, col_adder: list[int]) -> int:
    """Computes the golden reference output for a single Lane Shift Accumulator

    Behaviour:
       Combines this cycle's column-sums into a signed lane value and accumulates it
       into a y, shifted by bp_idx (LSB-first). y is threaded across calls. clr 
       zeroes y and overrides en. Output (y) wraps to ACC_WIDTH.

    Args:
        y (int)               : current signed accumulator/output
        clr (int)             : clear (zero) the accumulator - has priority over en
        en (int)              : accumulate-enable for this plane
        bp_idx (int)          : bit-plane index 0..DW-1 (left-shift amount, LSB-first)
        col_adder (list[int]) : DW column-sums for this lane this cycle

    Returns:
        out (int) : signed accumulator value after this clock edge. wrapped to ACC_WIDTH

    Raises:
        RuntimeError : If DW has not been set by the testbench before use.
    """
    if ROWS is None:
        raise RuntimeError("golden.lane_shift_accum.ROWS not set")

    if DW is None:
        raise RuntimeError("golden.lane_shift_accum.DW not set")

    if ACC_WIDTH is None:
        raise RuntimeError("golden.lane_shift_accum.ACC_WIDTH not set")

    if A_SIGN is None:
        raise RuntimeError("golden.lane_shift_accum.A_SIGN not set")

    if W_SIGN is None:
        raise RuntimeError("golden.lane_shift_accum.W_SIGN  ot set")

    lane_val = _combine(col_adder, DW, W_SIGN)
    if clr:
        next_y = 0
    elif en:
        if A_SIGN and bp_idx == DW - 1:
            next_y = y - (lane_val << bp_idx)
        else:
            next_y = y + (lane_val << bp_idx)
    else:
        next_y = y
    
    return to_signed(next_y & ((1 << ACC_WIDTH) - 1), ACC_WIDTH)

def golden_tb():
    global ROWS
    global DW
    global ACC_WIDTH
    global W_SIGN
    global A_SIGN
    # Simulate setting the golden.lane_shift_accum.DW from tb
    ROWS      = 32
    DW        = 8
    ACC_WIDTH = 32
    W_SIGN    = 1
    A_SIGN    = 0

    def run(W_signed, A_unsigned, DW):
        Wb = [(W_signed >> b) & 1 for b in range(DW)]
        y = 0
        for p in range(DW):                          # LSB-first planes
            ap = (A_unsigned >> p) & 1
            col = [Wb[b] & ap for b in range(DW)]     # 1-row lane
            y = golden_ref(y, clr=0, en=1, bp_idx=p, col_adder=col)
        return y
    for W, A, exp in [(-1,1,-1), (127,255,32385), (-128,255,-32640),
                      (-128,1,-128), (-50,200,-10000), (100,100,10000)]:
        got = run(to_signed(W & 0xFF, 8), A, DW)
        assert got == exp, f"W={W} A={A}: got {got}, expected {exp}"
    print("lane_shift_accum golden_ref self-check passed")

if __name__ == '__main__':
    golden_tb()
