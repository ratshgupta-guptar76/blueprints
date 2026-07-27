# Golden Model for src/shift_accum.sv

from golden.helpers import to_signed

ROWS       : int | None = None        # Default Null value for golden_tb(). 
N_WEIGHTS  : int | None = None        # Value overwritten during actual testing.
DW         : int | None = None
COLS       : int | None = None
ACC_WIDTH  : int | None = None
A_SIGN     : int | None = None
W_SIGN     : int | None = None

# ---------- Golden Reference ----------
def golden_ref(y: list[int], clr: int, en: int, bp_idx: int, col_sums: list[int]) -> list[int]:
    """Computes the golden reference output for a single Lane Shift Accumulator

    Behaviour:
       Slices the COLS column-sums into N_WEIGHTS groups of DW, then combines and accumulates
       each lane independently. y is threaded across temporal planes.

    Args:
        y (list[int])        : N_WEIGHTS signed accumulators entering this cycle
        clr (int)            : clear (zero) all accumulators - has priority over en
        en (int)             : accumulate-enable for this plane (cycle)
        bp_idx (int)         : bit-plane index 0..DW-1 (left-shift amount, LSB-first)
        col_sums (list[int]) : COLS column-sums for this lane this cycle

    Returns:
        out (list[int]) : N_WEIGHTS signed accumulator values after this clock edge. Wrapped to ACC_WIDTH

    Raises:
        RuntimeError : If ROWS, N_WEIGHTS, DW, COLS, ACC_WIDTH, A_SIGN, or W_SIGN have not been set by the testbench before use.
    """
    if (ROWS == None):
        raise RuntimeError("golden.row_decoder.ROWS not set")

    if (N_WEIGHTS == None):
        raise RuntimeError("golden.row_decoder.N_WEIGHTS not set")

    if (DW == None):
        raise RuntimeError("golden.row_decoder.DW not set")

    if (COLS == None):
        raise RuntimeError("golden.row_decoder.COLS not set")

    if (ACC_WIDTH == None):
        raise RuntimeError("golden.row_decoder.ACC_WIDTH not set")

    if (A_SIGN == None):
        raise RuntimeError("golden.row_decoder.A_SIGN not set")

    if (W_SIGN == None):
        raise RuntimeError("golden.row_decoder.W_SIGN not set")

    next_y = []
    for i in range(N_WEIGHTS):
        col = [col_sums[i*DW + b] for b in range(DW)]   # SLICE: lane i's DW columns
        # combine (independent reimplementation, not a call to lane's _combine)
        add_bin = sum(col[b] << b for b in range(DW-1))
        msb = col[DW-1] << (DW-1)
        lane_val = add_bin - msb if W_SIGN else add_bin + msb
        # accumulate
        if clr:            nxt_y_val = 0
        elif en:           nxt_y_val = (y[i] - (lane_val<<bp_idx)) if (A_SIGN and bp_idx==DW-1) else (y[i] + (lane_val<<bp_idx))
        else:              nxt_y_val = y[i]
        next_y.append(to_signed(nxt_y_val & ((1<<ACC_WIDTH)-1), ACC_WIDTH))
    return next_y

def golden_tb() -> None:
    global ROWS
    global N_WEIGHTS
    global DW
    global COLS
    global ACC_WIDTH
    global A_SIGN
    global W_SIGN
    # Simulate setting parameters from tb
    ROWS = 32
    N_WEIGHTS = 4
    DW = 8
    COLS = N_WEIGHTS*DW
    ACC_WIDTH = 22
    A_SIGN = 0
    W_SIGN = 1

    def run(weights, activations, N_WEIGHTS=N_WEIGHTS, DW=DW, COLS=COLS) -> list[int]:
        """Full matvec, single-row array. weights[i]/activations[i] per lane.
           Lane i owns columns [i*DW : i*DW+DW] = weight i's bits."""
        Wb = [[(weights[i] >> b) & 1 for b in range(DW)] for i in range(N_WEIGHTS)]
        y = [0] * N_WEIGHTS
        for p in range(DW):                              # LSB-first planes
            col_sums = [0] * COLS
            for i in range(N_WEIGHTS):
                ap = (activations[i] >> p) & 1
                for b in range(DW):
                    col_sums[i*DW + b] = Wb[i][b] & ap   # 1-row col-sum
            y = golden_ref(y, clr=0, en=1, bp_idx=p, col_sums=col_sums)
        return y

    # 1. each lane independently correct — signed matvec, hard cases per lane
    W = [to_signed(x & 0xFF, 8) for x in (0xFF, 0x7F, 0x80, 0x01)]   # -1, 127, -128, 1
    A = [1, 255, 255, 200]
    exp = [W[i] * A[i] for i in range(N_WEIGHTS)]
    got = run(W, A)
    assert got == exp, f"per-lane matvec: got {got}, expected {exp}"

    # 2. SLICE isolation: only lane 2 driven -> only y[2] nonzero
    W = [0, 0, to_signed(0x80, 8), 0]
    A = [255, 255, 255, 255]
    got = run(W, A)
    assert got[2] == -128*255 and all(got[i] == 0 for i in (0, 1, 3)), f"slice leak: {got}"

    # 3. clr zeroes all lanes
    y = [12345, -6789, 42, -1]
    assert golden_ref(y, clr=1, en=1, bp_idx=0, col_sums=[0]*COLS) == [0]*N_WEIGHTS

    print("shift_accum golden_ref self-check passed")

if __name__ == '__main__':
    golden_tb()