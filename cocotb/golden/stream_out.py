# Golden Model for src/stream_out.sv

ACC_WIDTH : int | None = None       # Default Null value for golden_tb(). 
N_WEIGHTS : int | None = None       # Value overwritten during actual testing.
TOT       : int | None = None

# ---------- Golden Reference ----------
def golden_ref(piso: int, counter: int, done: int, en: int, load: int, acc: int) -> tuple[int, int, int, int]:
    """Computes the golden reference output for Stream Out Register

    Behaviour:
       piso, counter, and done are registered. done is a registered flag, so it is returned
       as next-state. en is the master enable.. with en low, all states hold.

    Args:
        piso (int)    : Current PISO stream-out Register
        counter (int) : current stream-out counter
        done (int)    : current done flag
        en (int)      : Enable signal for Stream Out buffer
        load (int)    : Capture enable flag
        acc (int)     : packed accumulator vector

    Returns:
        tuple[int, int, int, int]
            - y_bit        : piso[0] in THIS cycle (comb. output)
            - next_done    : done latching this clk edge (high one cycle after when counter == TOT-1)
            - next_piso    : PISO contents after the clk
            - next_counter : stream-out counter after the clk edge

    Raises:
        RuntimeError : If ACC_WIDTH, N_WEIGHTS or N_WEIGHTS has not been set by the testbench before use.
    """
    if ACC_WIDTH is None:
        raise RuntimeError("golden.row_decoder.ACC_WIDTH not set")

    if N_WEIGHTS is None:
        raise RuntimeError("golden.row_decoder.N_WEIGHTS not set")

    if TOT is None:
        raise RuntimeError("golden.row_decoder.TOT not set")

    # Variables
    y_bit        : int
    next_done    : int
    next_piso    : int
    next_counter : int
    out : tuple[int, int, int, int]

    y_bit = piso & 1
    if en == 1:
        if load == 1:
            next_piso    = acc
            next_counter = 0
            next_done    = 0
        else:
            next_piso    = piso >> 1
            next_counter = counter + 1
            next_done    = 1 if counter == TOT-1 else 0
    else:
        next_piso    = piso
        next_counter = counter
        next_done    = done

    next_piso &= (1 << TOT) - 1
    out = (y_bit, next_done, next_counter, next_piso)
    return out

def golden_tb() -> None:
    global ACC_WIDTH
    global N_WEIGHTS
    global TOT
    # tiny ACC_WIDTH, N_WEIGHTS, TOT for a hand-checkable trace
    ACC_WIDTH = 3
    N_WEIGHTS = 2
    TOT = ACC_WIDTH * N_WEIGHTS     # 2 lanes x 3 bits, hand-checkable
    acc = 0b101_011                 # lane1=101, lane0=011 (low bits = lane0)
    expected_bits = [1, 1, 0, 1, 0, 1]   # lane0 LSB-first, then lane1

    piso = counter = done = 0
    # capture requires en & load (master-enable gating)
    _, done, counter, piso = golden_ref(piso, counter, done, en=1, load=1, acc=acc)

    drained, done_seen = [], []
    for _ in range(TOT + 1):      # +1 to see registered done
        y, ndone, ncounter, npiso = golden_ref(piso, counter, done, en=1, load=0, acc=0)
        drained.append(y)
        done_seen.append(ndone)
        piso, counter, done = npiso, ncounter, ndone

    assert drained[:TOT] == expected_bits, (
        f"drain order:\n  got      {drained[:TOT]}\n  expected {expected_bits}")
    expected_done = [0, 0, 0, 0, 0, 1, 0]
    assert done_seen == expected_done, (
        f"done timing:\n  got      {done_seen}\n  expected {expected_done}")

    print("stream_out golden_ref self-check passed")

if __name__ == '__main__':
    golden_tb()
