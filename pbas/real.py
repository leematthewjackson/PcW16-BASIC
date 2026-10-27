"""M7 REAL numbers: the 5-byte floating-point format (LANGUAGE-SPEC.md §2).

The Amstrad/Locomotive BASIC lineage (CPCWiki firmware guide): a 32-bit
mantissa with an implicit leading 1 whose top bit holds the sign, and an
exponent byte biased by #80. In memory, low byte first::

    +0 m0  +1 m1  +2 m2  +3 m3 (bit 7 = sign)  +4 exponent (0 = the value 0)

value = (-1)^sign * (0.1 m3' m2 m1 m0 in binary) * 2^(exponent - 128),
where m3' is m3 with bit 7 replaced by the implicit 1, so the mantissa
fraction lies in [0.5, 1). Range about 2.9E-39 .. 1.7E+38 (exponent 1..255),
about 9.6 significant decimal digits.

``pack`` rounds exactly (to nearest, ties away from zero, as the runtime's
rounding does) from a Fraction, so literals are the representable value
nearest to their decimal text. ``unpack`` is exact. Both are used by the code
generator (literals, constant tables) and by the tests.
"""
from __future__ import annotations

from fractions import Fraction

EXP_BIAS = 128
MANTISSA_BITS = 32
MAX_EXPONENT = 255


class RealRangeError(ValueError):
    """A value too large for the format."""


def pack(value) -> bytes:
    """The 5 bytes of the representable value nearest to *value*."""
    q = Fraction(value)
    if q == 0:
        return bytes(5)
    sign = 0x80 if q < 0 else 0
    q = abs(q)
    # find e with q = f * 2^(e-128), f in [1/2, 1)
    e = q.numerator.bit_length() - q.denominator.bit_length() + EXP_BIAS
    while q / Fraction(2) ** (e - EXP_BIAS) >= 1:
        e += 1
    while q / Fraction(2) ** (e - EXP_BIAS) < Fraction(1, 2):
        e -= 1
    f = q / Fraction(2) ** (e - EXP_BIAS)
    scaled = f * (1 << MANTISSA_BITS)
    m = int(scaled)
    if scaled - m >= Fraction(1, 2):  # nearest, ties away from zero
        m += 1
    if m == 1 << MANTISSA_BITS:  # rounded up to the next power of two
        m >>= 1
        e += 1
    if e > MAX_EXPONENT:
        raise RealRangeError(f'{float(value):g} is too large for a REAL (about 1.7E+38 at most)')
    if e < 1:
        return bytes(5)  # underflow: zero
    m &= 0x7FFFFFFF
    return bytes((m & 0xFF, (m >> 8) & 0xFF, (m >> 16) & 0xFF, ((m >> 24) & 0x7F) | sign, e))


def unpack(data: bytes) -> Fraction:
    """The exact value of 5 packed bytes."""
    b = bytes(data)
    if b[4] == 0:
        return Fraction(0)
    m = b[0] | (b[1] << 8) | (b[2] << 16) | (((b[3] & 0x7F) | 0x80) << 24)
    value = Fraction(m, 1 << MANTISSA_BITS) * Fraction(2) ** (b[4] - EXP_BIAS)
    return -value if b[3] & 0x80 else value


def db_line(value) -> str:
    """An assembler `db` operand list for *value*."""
    return ",".join(str(x) for x in pack(value))
