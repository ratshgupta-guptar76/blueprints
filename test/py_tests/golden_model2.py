import math
from fxpmath import Fxp

def dot_product(vec_A, vec_B, precision=8, acc_width=24):
    """
    Calculate the bit-accurate dot product.
    
    Parameters:
    vec_A, vec_B: Input vectors (lists of integers)
    precision: Width of the input weights/activations (e.g., 8 for INT8)
    acc_width: The fixed width of the hardware accumulator register
    """

    if len(vec_A) != len(vec_B):
        raise ValueError("Vectors must be of the same length.")

    # Initialize the accumulator with the STRICT HARDWARE WIDTH
    # Assumes the RTL allows wrapping on overflow. 
    result = Fxp(0, signed=True, n_word=acc_width, n_frac=0, overflow='wrap')

    for i in range(len(vec_A)):
        # Cast inputs to exact hardware precision
        x = Fxp(vec_A[i], signed=True, n_word=precision, n_frac=0)
        y = Fxp(vec_B[i], signed=True, n_word=precision, n_frac=0)

        # Multiply (yields 2*precision bits) and accumulate into fixed-width result
        result += (x * y)

    return result


def calculate_width(precision):
    pass

if __name__ == "__main__":
    print("Testing Golden Model against 8x8 Hardware Target")
    
    # Simulating a worst-case scenario for an 8-element dot product (e.g. one column)
    # Max negative INT8 is -128. (-128 * -128 = +16,384)
    test_vec_A = [-128] * 8
    test_vec_B = [-128] * 8
    
    # Using 24 bits for the accumulator as an example
    ans = dot_product(test_vec_A, test_vec_B, precision=8, acc_width=24)
    
    print(f"Result (Decimal): {ans}")
    print(f"Result (Binary):  {ans.bin()}")
    print(f"Acc Width Used:   {ans.n_word} bits")