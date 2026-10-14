"""The link CRC and the self-test generators, as plain functions."""
from __future__ import annotations

CRC_POLY, CRC_INIT = 0x1D, 0xFF


def crc8_symbol(crc: int, symbol: int) -> int:
    """Take one 4-bit symbol into the CRC, bit 3 first."""
    for i in (3, 2, 1, 0):
        top = ((crc >> 7) ^ (symbol >> i)) & 1
        crc = ((crc << 1) & 0xFF) ^ (CRC_POLY if top else 0)
    return crc


def crc8(symbols) -> int:
    crc = CRC_INIT
    for s in symbols:
        crc = crc8_symbol(crc, s)
    return crc


class Lfsr16:
    """x^16 + x^14 + x^13 + x^11 + 1, seed 0xACE1. One bit per step."""

    def __init__(self, seed: int = 0xACE1):
        self.s = seed

    def bit(self) -> int:
        b = self.s & 1
        fb = (self.s ^ (self.s >> 2) ^ (self.s >> 3) ^ (self.s >> 5)) & 1
        self.s = (self.s >> 1) | (fb << 15)
        return b


MISR_POLY, MISR_SEED = 0x04C11DB7, 0xFFFFFFFF


def misr_step(sig: int, value: int) -> int:
    """Fold one value (up to 32 bits) into the signature."""
    sig = ((sig << 1) & 0xFFFFFFFF) ^ (MISR_POLY if sig >> 31 else 0)
    return sig ^ (value & 0xFFFFFFFF)
