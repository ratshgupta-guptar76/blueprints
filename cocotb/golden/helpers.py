# Helper functions

def to_signed(v: int, w: int) -> int:
    """Interpret the low w bits of v as a two's-complement signed integer."""
    v &= (1 << w) - 1                       # mask to w bits
    return v - (1 << w) if v & (1 << (w - 1)) else v

def _combine(col_adder: list[int], DW, W_SIGN) -> int:
    """Horizontal weight-bit combine (Full signed weight
    multiplication for each activation plane)
    
    Reduces the DW column-sums of one lane into a single signed lane value.
    bits 0...DW-2 add with weight 2^b. The MSB column (DW-1) subtracts when
    W_SIGN = 1, else adds. Weight sign is applied here.

    Args:
        col_adder (list[int]): DW column-sums (unsigned popcounts, 0...ROWS),
                               index b is weight-bit b of this lane.

    Returns:
        out (int): signed lane value
    """

    add_bin = sum(col_adder[b] << b for b in range(DW - 1))
    msb = col_adder[DW - 1] << (DW - 1)
    return add_bin - msb if W_SIGN else add_bin + msb
