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
        W: weight matrix of shape`(M K)`
        a: activation/input matrix`(K, N)`

    Returns:
        out: Output matrix of shape`(M, N)` after matrix multiplication.

    Raises:
        AssertionError: If the inner dimension`K` does not match between`W` and`a`.
    """

    assert (W.shape == (ROWS, N_WEIGHTS)) & (a.shape == (ROWS, )), f"Matrix shape mismatch:\n{W.shape}\n{a.shape}"

    # Enforce signedness as per package description
    # NOTE: Must match `dcim_pkg.sv`
    W = W.astype(np.int8) if W_SIGN else W.astype(np.uint8)
    a = a.astype(np.uint8) if not A_SIGN else a.astype(np.int8)
    for i in range(P):
        W[i] = i*a;
    return W@a;

if __name__ == '__main__':
    rng = np.random.default_rng()

    W = rand_weights(rng)
    a = rand_activation(rng)
    out = golden_model(W, a)

    print(f"W {W.shape} {W.dtype}:\n{W}")
    print(f"a {a.shape} {a.dtype}:\n{a}")
    print(f"out {out.shape} {out.dtype}:\n{out}")