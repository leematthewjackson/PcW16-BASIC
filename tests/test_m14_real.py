"""M14 (M14-DEFECT-REGISTER.md F5): REAL + and - correctly rounded.

LANGUAGE-SPEC §3.1 says + - * / give the REAL nearest the exact result. Up to
M13, rt_fadd dropped the bits it shifted below the guard byte, so a
difference just under half a unit in the last place could round up (about
1.5% of the + and - cases built to lie near a half; found by the M14
adversarial review). The sticky bit (PB_RSTICKY) keeps them.
--legacy-real-rounding rebuilds the old code, to show the defect and to
reproduce accepted executables.
"""
from __future__ import annotations

import random
import unittest
from fractions import Fraction

from memguard import guarded_run
from pbas.real import pack, unpack
from toolchain import requires_pasmo

CASES = 120


def literal(v: Fraction) -> str:
    """A decimal literal that packs to exactly *v* (a representable REAL)."""
    digits = 30
    while True:
        text = f"{float(v):.{digits}E}" if v else "0"
        if unpack(pack(Fraction(text.replace('E', 'e')))) == v:
            return text
        digits += 5


def half_ulp_distance(x: Fraction) -> Fraction:
    """How far *x* is from a halfway point between REALs, in units in the last place."""
    x = abs(x)
    e = x.numerator.bit_length() - x.denominator.bit_length()
    while x >= Fraction(2) ** e:
        e += 1
    while x < Fraction(2) ** (e - 1):
        e -= 1
    scaled = x * Fraction(2) ** (32 - e)
    return abs(scaled - int(scaled) - Fraction(1, 2))


def near_ties(op: str, seed: int):
    rng = random.Random(seed)
    out = []
    while len(out) < CASES:
        a = Fraction(rng.randint(1 << 31, (1 << 32) - 1), 1 << 32) * Fraction(2) ** rng.randint(-20, 20)
        b = Fraction(rng.randint(1 << 31, (1 << 32) - 1), 1 << 32) * Fraction(2) ** rng.randint(-20, 20)
        b = -b if rng.random() < 0.5 else b
        b = unpack(pack(b * Fraction(2) ** rng.randint(-40, 0)))
        exact = a + b if op == "+" else a - b
        if exact and half_ulp_distance(exact) < Fraction(1, 100):
            out.append((a, b, exact))
    return out


def source(op: str, cases) -> str:
    src = ["DIM A AS REAL", "DIM B AS REAL", f"DIM X({len(cases)}) AS REAL"]
    for i, (a, b, _) in enumerate(cases, 1):
        src += [f"A = {literal(a)}", f"B = {literal(b)}", f"X({i}) = A {op} B"]
    return "\n".join(src + ["END"]) + "\n"


def results(op: str, cases, **build):
    r = guarded_run(source(op, cases), build_options=build)
    assert not r.violations and r.cpu.exited, r.violations[:2]
    base = r.symbols["var_x"]
    return [unpack(bytes(r.cpu.mem[base + 5 * i:base + 5 * i + 5])) for i in range(len(cases))]


@requires_pasmo
class NearHalfRounding(unittest.TestCase):
    def check(self, op, seed):
        cases = near_ties(op, seed)
        got = results(op, cases)
        wrong = [(literal(a), op, literal(b)) for (a, b, exact), g in zip(cases, got) if g != unpack(pack(exact))]
        self.assertEqual(wrong, [])
        return cases

    def test_addition(self):
        self.check("+", 14)

    def test_subtraction(self):
        self.check("-", 15)

    def test_the_old_rounding_was_wrong_here(self):
        a, b = Fraction(240), unpack(pack(Fraction("-2.8759247157950085238553584E-5")))
        exact = unpack(pack(a + b))
        self.assertEqual(results("+", [(a, b, a + b)]), [exact])
        self.assertNotEqual(results("+", [(a, b, a + b)], legacy_real_rounding=True), [exact])

    def test_the_pruned_and_whole_libraries_agree(self):
        cases = near_ties("-", 16)[:20]
        self.assertEqual(results("-", cases), results("-", cases, prune=False))


if __name__ == "__main__":
    unittest.main()
