"""
golden_model.py
----------------
- Bit exact model for the dCiM matrix vectors
- Mirrors Hardware, bit-serial activations & bit-parallel weights
"""

# imports
import numpy as np

'''
%%%%%%%%%%%%%%
% parameters %
%%%%%%%%%%%%%%
'''
## Adopted from dcim_pkg.sv
DW          : int   =  8       # Maximum precision of weights and activations
N_WEIGHTS   : int   =  8       # Number of weights across a row/column (TBD later)
ROWS        : int   =  64      # Number of word rows 
COLS        : int   =  64      # Number of word cols
ACC_WIDTH   : int   =  22      # Out accumulator width (max[])

W_SIGN      : int   =  1       # Weight signedness
W_BITS      : int   =  8       # Weight bit-precision
A_SIGN      : int   =  0       # Activation signedness
A_MAX_BITS  : int   =  8       # Maximum Activation bit-precision


'''
%%%%%%%%%%%%%%%
% generators  %
%%%%%%%%%%%%%%%
'''
def _int_range(signed: int, bits: int) -> tuple[int, int]:
    """Inclusive [lo, hi] value range for a `bits`-wide signed/unsigned integer."""
    if signed:
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return 0, (1 << bits) - 1


def rand_weights(rng: np.random.Generator) -> np.ndarray:
    """Random weight matrix of shape `(ROWS, N_WEIGHTS)`.

    Values respect `W_SIGN`/`W_BITS` and are stored as int8/uint8 to match
    `dcim_pkg.sv`.
    """
    lo, hi = _int_range(W_SIGN, W_BITS)
    dtype = np.int8 if W_SIGN else np.uint8
    return rng.integers(lo, hi + 1, size=(ROWS, N_WEIGHTS), dtype=dtype)


def rand_activation(rng: np.random.Generator) -> np.ndarray:
    """Random activation vector of shape `(ROWS,)`.

    Values respect `A_SIGN`/`A_MAX_BITS` and are stored as int8/uint8 to match
    `dcim_pkg.sv`.
    """
    lo, hi = _int_range(A_SIGN, A_MAX_BITS)
    dtype = np.int8 if A_SIGN else np.uint8
    return rng.integers(lo, hi + 1, size=(ROWS,), dtype=dtype)

'''
%%%%%%%%%%
% models %
%%%%%%%%%%
'''
def golden_model(W: np.ndarray, a: np.ndarray) -> np.ndarray:
    r""" Simple matrix multiplication golden model.

    Args:
        W: weight matrix of shape`(M K)`
        a: activation/input matrix`(K, N)`

    Returns:
        out: Output matrix of shape`(M, N)` after matrix multiplication.

    Raises:
        AssertionError: If the inner dimension`K` does not match between`W` and`a`.
    """

    assert (W.shape == (ROWS, N_WEIGHTS)) & (a.shape == (ROWS, )), f"Matrix shape mismatch:\n{W.shape}\n{a.shape}"

    # enforce signedness as per package description
    ## NOTE: Must match `dcim_pkg.sv`
    W = W.astype(np.int8) if W_SIGN else W.astype(np.uint8)
    a = a.astype(np.uint8) if not A_SIGN else a.astype(np.int8)

    return W.astype(np.int64).T @ a.astype(np.int64)

def golden_bit_serial(W, a, P):
    r""" Bit-serial matrix-multiplication golden model.

    Args:
        W: weight matrix of shape `(M K)`
        a: activation/input matrix `(K, N)`
        P: bit-plane under test 

    Returns:
        out: Output matrix of shape `(M, N)` after matrix multiplication.
        trace[b] = accumulator after processing bit-planes 0..b.

    Raises:
        AssertionError: If the inner dimension `K` does not match between `W` and `a`.
        ValueError: If the bit-plane `P` is invalid (not in `[0, A_MAX_BITS-1]`).
    """

    assert (W.shape == (ROWS, N_WEIGHTS)) and (a.shape == (ROWS, )), f"Matrix shape mismatch:\n{W.shape}\n{a.shape}"

    # Enforce signedness as per package description
    # NOTE: Must match `dcim_pkg.sv`
    W = W.astype(np.int8) if W_SIGN else W.astype(np.uint8)
    a = a.astype(np.uint8) if not A_SIGN else a.astype(np.int8)

    # Check for invalid bit-plane
    if P < 0 or P > A_MAX_BITS:
        raise ValueError(f"Invalid bit-plane {P}. Must be in [0, {A_MAX_BITS-1}]")
    
    out = np.zeros((N_WEIGHTS,), dtype=np.int64)
    trace = []
    for bit in range(P): # LSB to MSB
        a_b = (a >> bit) & 1                                    # Bit-plane of each activation
        partial = W.astype(np.int64).T @ a_b.astype(np.int64)   # Weight Matrix-vector multiplication against the activation in bit-plane
        
        # Accumulate partial result based on signedness and bit-plane
        if A_SIGN and (bit ==  A_MAX_BITS-1):
            out -= partial << bit
        else:
            out += partial << bit

        trace.append(out.copy())
    return out, trace

if __name__ == '__main__':
    rng = np.random.default_rng()

    W = rand_weights(rng)
    a = rand_activation(rng)
    out1 = golden_model(W, a)
    out2, trace = golden_bit_serial(W, a, 8)

    print(f"W {W.shape} {W.dtype}:\n{W}")
    print(f"a {a.shape} {a.dtype}:\n{a}")
    assert np.array_equal(out1, out2), f"Mismatch between golden_model and golden_bit_serial:\n{out1}\n{out2}"
