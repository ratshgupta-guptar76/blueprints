# Golden Model for src/row_decoder.sv

DW : int | None = None      # Default Null value for golden_tb(). 
                            # Value overwritten during actual testing.

# ---------- Golden Reference ----------
def golden_ref(sr: int, en: int, c_en: int, serial_in: int) -> tuple[int, int]:
    """Computes the golden reference output for a single Shift Register

    Behaviour:
       One clock step of a DW-bit LSB shift register. Stateful; sr is passed in and 
       the post-edge state returned; thread it back each cycle.

    Args:
        sr (int) : Current Shift Register
        en (int) : Enable signal for Shift Register
        c_en (int) : Compute enable signal for Shift Register (COMPUTE mode)
        serial_in (int) : input bit into MSB

    Returns:
        tuple[int, int]
            - sr_out  : sr[0] this cycle (compute_bit = serial_out), sampled BEFORE the shift.
            - next_sr : the full DW-bit register contents AFTER the clock edge, sr shifted
                        one place toward the LSB, with the MSB filled per mode (serial_in in 
                        LOAD, 0 in COMPUTE, unchanged if en=0). Thread this back in as `sr` 
                        on the next call.

    Raises:
        RuntimeError : If DW has not been set by the testbench before use.
    """
    if DW is None:
        raise RuntimeError("golden.row_decoder.DW not set")

    # Variables
    sr_out  : int
    next_sr : int
    out     : tuple[int, int]

    if en == 0:
        next_sr = sr
    else:
        if c_en == 0:
            next_sr = (serial_in << (DW-1)) | (sr >> 1)
        else:
            next_sr = (sr >> 1)

    sr_out  = sr & 1
    next_sr &= (1 << DW) - 1    # truncate next_sr to DW, so that python code behaves like the hardware

    out = (sr_out, next_sr)
    return out

def golden_tb() -> None:
    global DW
    DW = 8       # Simulate setting the golden.row_decoder.DW from tb

    # LOAD 0b10110001 LSB-first over DW cycles, then COMPUTE it out
    sr = 0
    bits_in = [1,0,0,0,1,1,0,1]          # LSB first
    for b in bits_in:
        _, sr = golden_ref(sr, en=1, c_en=0, serial_in=b)
    assert sr == 0b10110001, f"loaded {sr:#010b}, expected 0b10110001"

    # COMPUTE drains LSB-first
    out_seq = []
    for _ in range(DW):
        o, sr = golden_ref(sr, en=1, c_en=1, serial_in=0)
        out_seq.append(o)
    assert out_seq == bits_in, f"drained {out_seq}, expected {bits_in}"
    print("shift_reg golden_ref self-check passed")

if __name__ == '__main__':
    golden_tb()
