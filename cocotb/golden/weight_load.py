# Golden Model for src/weight_load.sv

COLS: int | None = None     # Default Null value for golden_tb(). 
                            # Value overwritten during actual testing.

# ---------- Golden Reference ----------
def golden_ref(w_buf: int, en: int, wload_cnt: int, w_bit: int) -> tuple[int, int, int, int]:
    """Computes the golden reference output for the Weight Load Register

    Behaviour:
       w_buf and wload_cnt are registers; wfull is also a registered flag so
       it is returned as a next-state (current status visible the next cycle)

    Args:
        w_buf (int)     : Current Weight Load Buffer Register
        en (int)        : Enable signal for Weight Load buffer
        wload_cnt (int) : Current wload_cnt (0...COLS-1)
        w_bit (int)     : input weight bit into MSB of w_buf

    Returns:
        tuple[int, int, int, int]
            - w_buf_out      : w_buf THIS cycle (comb. parallel output)
            - next_wfull     : next state of wfull flag, since wfull is registered.
            - next_wload_cnt : next state of the wload_cnt register after this clk edge
            - next_w_buf     : next state of the w_buf shift-register after w_bit is shifted into the MSB
    
    Raises:
        RuntimeError : If ROWS has not been set by the testbench before use.
    """
    if COLS is None:
        raise RuntimeError("golden.row_decoder.COLS not set")

    # Variables
    next_wfull     : int
    next_wload_cnt : int
    next_w_buf     : int
    out : tuple[int, int, int, int]

    w_buf_out = w_buf

    if en == 1:
        next_w_buf     = ((w_bit << (COLS-1)) | (w_buf >> 1))
        next_wload_cnt = 0 if wload_cnt == COLS-1 else wload_cnt + 1
        next_wfull     = 1 if wload_cnt == COLS-1 else 0
    else:
        next_w_buf     = w_buf
        next_wload_cnt = wload_cnt
        next_wfull     = 0

    next_w_buf &= (1 << COLS) - 1
    out = (w_buf_out, next_wfull, next_wload_cnt, next_w_buf)
    return out

def golden_tb() -> None:
    global COLS
    COLS = 4         # tiny COLS for a hand-checkable trace
    w_buf = cnt = 0
    wfull_seen = []
    for i in range(COLS + 1):         # one extra cycle to see the registered pulse
        _, nf, ncnt, nbuf = golden_ref(w_buf, 1, cnt, 1)
        wfull_seen.append(nf)
        w_buf, cnt = nbuf, ncnt
    # cnt hits COLS-1 on cycle COLS-1 -> wfull_next high that call -> visible cycle C
    expected = [0, 0, 0, 1, 0]
    assert wfull_seen == expected, (
        f"wfull timing mismatch:\n"
        f"  got      {wfull_seen}\n"
        f"  expected {expected}"
    )
    print("weight_load golden_ref self-check passed")

if __name__ == '__main__':
    golden_tb()
