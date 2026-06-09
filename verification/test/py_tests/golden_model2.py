import math
from fxpmath import Fxp

class GoldenModel:
    """
    Python Golden Model for bit-accurate dot product calculations.
    """

    def __init__(self, overflow_type='wrap'):
        self.overflow_type = overflow_type

    def dot_product(self, vec_A, vec_B, precision=8, acc_width=24):
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
        result = self.fxp_wrap(0, acc_width)

        for i in range(len(vec_A)):
            # Cast inputs to exact hardware precision
            x = self.fxp_wrap(vec_A[i], precision)
            y = self.fxp_wrap(vec_B[i], precision)

            # Multiply (yields 2*precision bits) and accumulate into fixed-width result
            result += (x * y)

        return result

    def fxp_wrap(self, value, precision):
        """Simulate hardware values"""
        return Fxp(value, signed=True, n_word=precision, n_frac=0, overflow=self.overflow_type)

    def calculate_width(self, length, precision): 
        # Multiplying 2 M-bit numbers yields up to 2M bits
        # Summing N products can add log2(N) bits to the width
        return (2 * precision) + math.ceil(math.log2(length))


if __name__ == "__main__":
    print("Testing Golden Model against 8x8 Hardware Target")
    golden_model = GoldenModel()

    # Simulating a worst-case scenario for an 8-element dot product (e.g. one column)
    # Max negative INT8 is -128. (-128 * -128 = +16,384)
    test_vec_A = [1, 2]
    test_vec_B = [3, 4]
    
    # Using calculated width for the accumulator
    acc_width = golden_model.calculate_width(length=8, precision=8)
    ans = golden_model.dot_product(test_vec_A, test_vec_B, precision=8, acc_width=acc_width)
    
    print(f"Result (Decimal): {ans}")
    print(f"Result (Binary):  {ans.bin()}")
    print(f"Acc Width Used:   {ans.n_word} bits")