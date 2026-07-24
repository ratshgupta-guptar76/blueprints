# Golden Model for src/row_decoder.sv

ROWS : int = 32     # Default value for golden_tb(). 
                    # Value overwritten during actual testing.

# ---------- Golden Reference ----------
def golden_ref(addr: int, en: int) -> int:
    """Computes the golden reference output for the Row Decoder

    Behaviour:
        enabled: returns a signal with only the bit at the `addr` index set to `1`
        disabled: returs 0 (all wordlines de-asserted)

    Args:
        en (`int`)      : Enable signal for Row Decoder
        addr (`int`)    : Binary row address input to decode

    Returns:
        out (`int`) : The one-hot wordline (wl) decoded bit-vector representation
    
    Raises:
        AssertionError : If `addr` is less than 0 or greater than or equal to `ROWS`
    """

    if en == 0:
        return 0
    assert 0 <= addr < ROWS, f"`addr` {addr} out of range [0,{ROWS})"
    return 1 << addr

def golden_tb() -> None:
    assert golden_ref(5, 1) == 0b100000
    assert golden_ref(5, 0) == 0b000000
    assert golden_ref(0, 1) == 0b000001
    print("golden_ref self-check passed")

if __name__ == '__main__':
    golden_tb()