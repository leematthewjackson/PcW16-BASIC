"""M7 — the REAL type: 5-byte floating point, mixed arithmetic, the maths
functions, STR$/REALVAL/ISNUM and the REAL runtime errors (LANGUAGE-SPEC.md
§2.1, §3.4, §8). Behaviour runs on the project simulator under the memory
checker and is compared with Python's exact/float maths: engineering
evidence, not XAnne.
"""
from __future__ import annotations

import math
import random
import subprocess
import sys
import unittest
from decimal import ROUND_HALF_UP, Decimal, getcontext
from fractions import Fraction
from pathlib import Path

from memguard import guarded_run
from pbas import SourceError, check_source, generate
from pbas.real import RealRangeError, pack, unpack
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]


def run(src: str):
    r = guarded_run(src)
    assert r.violations == [], r.violations
    return r


def real_values(exprs, pre=""):
    """Evaluate each REAL expression into R(i) and return the exact values."""
    src = f"DIM R({len(exprs)}) AS REAL\nDIM X AS REAL\nDIM N AS INTEGER\n{pre}"
    src += "".join(f"R({i}) = {e}\n" for i, e in enumerate(exprs, 1)) + "END\n"
    r = run(src)
    assert r.cpu.alerts == [], r.cpu.alerts
    base = r.symbols["var_r"]
    return [unpack(r.cpu.mem[base + 5 * i: base + 5 * i + 5]) for i in range(len(exprs))]


def messages(exprs, pre=""):
    src = "DIM X AS REAL\nDIM N AS INTEGER\n" + pre
    src += "".join(f"MESSAGE {e}\n" for e in exprs) + "END\n"
    return run(src).cpu.alerts


class FormatTests(unittest.TestCase):
    def test_pack_round_trip(self):
        for v in (Fraction(1), Fraction(-1, 2), Fraction(3, 4), Fraction(10) ** 13, Fraction(1, 1 << 100)):
            self.assertEqual(unpack(pack(v)), v)
        self.assertEqual(pack(0), bytes(5))
        self.assertEqual(pack(Fraction(1, 2)), bytes((0, 0, 0, 0, 0x80)))  # mantissa .1, exponent 0
        self.assertEqual(pack(-1), bytes((0, 0, 0, 0x80, 0x81)))
        self.assertEqual(unpack(pack(Fraction(1, 3))) - Fraction(1, 3), Fraction(1, 3 << 33))  # nearest
        with self.assertRaises(RealRangeError):
            pack(Fraction(10) ** 39)
        self.assertEqual(pack(Fraction(1, 10 ** 40)), bytes(5))  # underflow is zero

    def test_runtime_constant_tables_are_generated(self):
        text = (ROOT / "runtime" / "runtime.z80.asm").read_text()
        begin = text.index("; realconst.py begin")
        end = text.index("; realconst.py end") + len("; realconst.py end")
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "realconst.py")],
                             capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(text[begin:end], out)


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> str:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return caught.exception.message

    def test_type_rules(self):
        decl = "DIM X AS REAL\nDIM N AS INTEGER\nDIM S$ AS STRING\nDIM B AS BOOLEAN\n"
        cases = {
            "N = X\n": "cannot assign REAL to INTEGER variable N (convert with CINT, which rounds; "
                      "CINT(INT(x)) or CINT(FIX(x)) drops the fraction)",
            "N = 2 ^ 2\n": "cannot assign REAL to INTEGER",
            "N = INT(X)\n": "cannot assign REAL to INTEGER",
            "X = X MOD 2\n": "operator MOD requires INTEGER operands, got REAL and INTEGER",
            "X = S$ + 1.5\n": "operator + requires numbers",
            "X = SQR(S$)\n": "SQR expects a number",
            "N = CINT(S$)\n": "CINT expects a number",
            "X = REALVAL(X)\n": "REALVAL expects a STRING",
            "B = X AND 1\n": "AND requires two BOOLEAN or two INTEGER operands",
            "X = 1E39\n": "too large for a REAL",
            "S$ = STR$(B)\n": "STR$ expects a number (INTEGER or REAL)",
            "IF X = \"a\" THEN\nEND IF\n": "comparison = requires matching types",
        }
        for body, fragment in cases.items():
            with self.subTest(body=body):
                self.assertIn(fragment, self.reject(decl + body + "END\n"))

    def test_accepted_forms(self):
        src = ("DIM X AS REAL\nDIM N AS INTEGER\nDIM A(3) AS REAL\nCONST HALF = 0.5\n"
               "X = N\nX = 3\nX = N / 2\nX = HALF * PI\nA(N) = X + A(1)\nN = CINT(X)\n"
               "N = CINT(INT(X) + FIX(-X))\nIF X > N THEN\nX = -X\nEND IF\n"
               "FUNCTION Half(V AS REAL) AS REAL\nRETURN V / 2\nEND FUNCTION\nX = Half(N)\nEND\n")
        generate(check_source(src))


@requires_pasmo
class BehaviourTests(unittest.TestCase):
    def test_arithmetic_is_correctly_rounded(self):
        exprs = {"1.5 + 2.25": Fraction(15, 4), "1 - 0.75": Fraction(1, 4), "3.0 * 4.5": Fraction(27, 2),
                 "10.0 / 4": Fraction(5, 2), "-7.5 + 2": Fraction(-11, 2), "2 - 2.0": 0,
                 "-0.5 * -0.5": Fraction(1, 4), "32767 + 1.5": Fraction(65537, 2),
                 "-32768 - 0.5": Fraction(-65537, 2), "-2 ^ 2": -4, "2 ^ 10": 1024, "2 ^ -1": Fraction(1, 2),
                 "7 / 2": 3, "1.0 * (7 / 2)": 3}
        got = real_values(list(exprs))
        self.assertEqual(dict(zip(exprs, got)), {k: Fraction(v) for k, v in exprs.items()})
        # inexact results are the nearest REAL to the exact quotient/sum of the operands
        third, sum_, prod = real_values(["1.0 / 3", "0.1 + 0.2", "1E10 * 1E10"])
        self.assertEqual(third, unpack(pack(Fraction(1, 3))))
        self.assertEqual(sum_, unpack(pack(unpack(pack(Fraction(1, 10))) + unpack(pack(Fraction(2, 10))))))
        self.assertEqual(prod, unpack(pack(unpack(pack(10 ** 10)) ** 2)))

    def test_random_arithmetic_is_correctly_rounded(self):
        rng = random.Random(7)

        def operand():
            v = Fraction(rng.randint(1, 10 ** 9)) * Fraction(10) ** rng.randint(-12, 12) / 10 ** 9
            return -v if rng.random() < 0.4 else v

        cases = []
        for _ in range(80):
            a, b, op = operand(), operand(), rng.choice("+-*/")
            if rng.random() < 0.2:
                b = a * (1 + Fraction(rng.randint(-5, 5), 10 ** 8))  # cancellation
            cases.append((repr(float(a)).replace("e", "E"), op, repr(float(b)).replace("e", "E")))
        got = real_values([f"({a}) {op} ({b})" for a, op, b in cases])
        for (a, op, b), value in zip(cases, got):
            pa, pb = unpack(pack(Fraction(a))), unpack(pack(Fraction(b)))
            exact = {"+": pa + pb, "-": pa - pb, "*": pa * pb, "/": pa / pb}[op]
            self.assertEqual(value, unpack(pack(exact)), (a, op, b))

    def test_functions_match_reference_maths(self):
        cases = {
            "SQR(2.0)": math.sqrt(2), "SQR(1E10)": 1e5, "SQR(0.0)": 0.0, "SQR(1E-30)": 1e-15,
            "EXP(1.0)": math.e, "EXP(-5.0)": math.exp(-5), "EXP(80.0)": math.exp(80), "EXP(0.0)": 1.0,
            "LOG(10.0)": math.log(10), "LOG(0.001)": math.log(0.001), "LOG(2.0)": math.log(2),
            "LOG(1.0)": 0.0, "LOG(1E30)": math.log(1e30),
            "SIN(1.0)": math.sin(1), "SIN(100.0)": math.sin(100), "SIN(-0.25)": math.sin(-0.25),
            "COS(1.0)": math.cos(1), "COS(2.5)": math.cos(2.5), "COS(0.0)": 1.0,
            "TAN(0.5)": math.tan(0.5), "TAN(1.5)": math.tan(1.5), "TAN(-3.0)": math.tan(-3),
            "ATN(1.0)": math.pi / 4, "ATN(-20.0)": math.atan(-20), "ATN(0.1)": math.atan(0.1),
            "ATN(1E10)": math.pi / 2,
            "2.0 ^ 0.5": math.sqrt(2), "10 ^ 2.5": 10 ** 2.5, "(-2.0) ^ 3": -8.0, "0.0 ^ 0": 1.0,
            "1.5 ^ -3.25": 1.5 ** -3.25, "PI": math.pi, "SIN(PI / 6)": 0.5,
        }
        got = real_values(list(cases))
        for (expr, want), value in zip(cases.items(), got):
            with self.subTest(expr=expr):
                err = abs(float(value) - want)
                # about 2^-28 relative: a few units in the last place of the 32-bit mantissa
                self.assertLessEqual(err, 4e-9 * max(abs(want), 1e-30) + 1e-10 * (abs(want) < 1), (value, want))

    def test_rounding_functions(self):
        exprs = ["INT(-2.5)", "FIX(-2.5)", "INT(2.5)", "FIX(2.9)", "INT(-0.1)", "INT(1E9 + 0.5)",
                 "ABS(-1.25)", "MIN(1.5, 2)", "MAX(-1, -0.5)", "SGN(-0.1) * 1.0", "1.0 * CINT(2.5)",
                 "1.0 * CINT(-2.5)", "1.0 * CINT(-0.4)", "1.0 * CINT(32767.4)", "INT(-0.9999)", "INT(0.5)", "FIX(-0.5)"]
        want = [-3, -2, 2, 2, -1, 1000000000, Fraction(5, 4), Fraction(3, 2), Fraction(-1, 2), -1, 3, -3, 0, 32767, -1, 0, 0]
        self.assertEqual(real_values(exprs), [Fraction(w) for w in want])

    def test_str_formatting(self):
        cases = {"0.1": "0.1", "123.456": "123.456", "1E10": "1E+10", "-2.0": "-2", "0.0": "0",
                 "1.0/3": "0.333333333", "2.0/3": "0.666666667", "1E-5": "1E-05", "0.0001": "0.0001",
                 "123456789.0": "123456789", "1234567890.0": "1.23456789E+09", "PI": "3.14159265",
                 "-1E-20": "-1E-20", "1.7E38": "1.7E+38", "99999999.5": "99999999.5",
                 "999999999.6": "1E+09", "9.9999999999": "10", "12345.678901": "12345.6789",
                 "0.000123456789": "0.000123456789", "1E-38": "1E-38"}
        self.assertEqual(messages([f"STR$({e})" for e in cases]), list(cases.values()))
        self.assertEqual(messages(['"x=" + STR$(X)'], pre="X = 2.5\n"), ["x=2.5"])

    def test_str_and_realval_are_correctly_rounded(self):
        # STR$ gives the 9-digit decimal nearest to the exact stored value, and
        # REALVAL the REAL nearest to the exact decimal (both exact in rt_fbig).
        getcontext().prec = 90
        rng = random.Random(11)
        values = [unpack(pack(Fraction(rng.randint(10 ** 8, 10 ** 10)) * Fraction(10) ** (rng.randint(-38, 37) - 9)))
                  for _ in range(40)] + [unpack(pack(Fraction(61749070546875, 10 ** 6))),
                                         unpack(pack(Fraction(9999999995, 10))), unpack(pack(Fraction(1, 2 ** 128)))]
        literals = [f"{Decimal(v.numerator) / Decimal(v.denominator):.30E}" for v in values]
        got = messages([f"STR$({t})" for t in literals])
        for v, text in zip(values, got):
            d = Decimal(v.numerator) / Decimal(v.denominator)
            k = d.adjusted()
            n = d.scaleb(8 - k).quantize(Decimal(1), rounding=ROUND_HALF_UP)
            if n >= 10 ** 9:
                k += 1
                n = d.scaleb(8 - k).quantize(Decimal(1), rounding=ROUND_HALF_UP)
            self.assertEqual(Decimal(text), n.scaleb(k - 8), (float(v), text))
        texts = [f"{rng.randint(1, 999999999)}E{rng.randint(-46, 29)}" for _ in range(40)]
        texts = [t for t in texts if Fraction(2) ** -128 < Fraction(t) < Fraction(17, 10) * 10 ** 38]
        texts += ["2.94E-39", "1.70141183E38", "0.1", "16777217", "429496729", "9.99999999E-39"]
        got = real_values([f'REALVAL("{t}")' for t in texts])
        self.assertEqual(got, [unpack(pack(Fraction(t))) for t in texts])
        # digits after the ninth significant one are ignored (LANGUAGE-SPEC §3.1)
        self.assertEqual(real_values(['REALVAL("4294967295")', 'REALVAL("0.12345678999")']),
                         [4294967290, unpack(pack(Fraction("0.123456789")))])

    def test_power_edges(self):
        exprs = ["10.0 ^ -200", "2.0 ^ -127", "2.0 ^ -129", "0.5 ^ 127", "(-2.0) ^ -3", "3.0 ^ -5",
                 "10.0 ^ 38", "1.5 ^ 0", "(-1.0) ^ 32767", "1E19 ^ -1024"]
        # the last: 1E19 is in [2^63, 2^64), so (e - 128) * |n| = 64 * 1024 wraps 16 bits to 0
        want = [0, Fraction(1, 2 ** 127), 0, Fraction(1, 2 ** 127), Fraction(-1, 8), None,
                unpack(pack(Fraction(10) ** 38)), 1, -1, 0]
        got = real_values(exprs)
        for e, w, g in zip(exprs, want, got):
            if w is not None:
                self.assertEqual(g, w, e)
        self.assertLessEqual(abs(float(got[5]) - 3 ** -5), 4e-9 * 3 ** -5)
        for stmt, error in (("X = 1E-30 ^ -2", "number out of range"), ("X = 0.5 ^ -127", "number out of range"),
                            ("X = 0.0 ^ -2", "division by zero"), ("X = 10.0 ^ 39", "number out of range")):
            with self.subTest(stmt=stmt):
                r = run(f"DIM X AS REAL\n{stmt}\nEND\n")
                self.assertEqual(r.cpu.alerts, [f"Runtime error: {error} at line 2"])

    def test_realval_and_isnum(self):
        vals = {'"  3.25 "': Fraction(13, 4), '"-1.5e3"': -1500, '".5"': Fraction(1, 2), '"7abc"': 7,
                '"abc"': 0, '""': 0, '"1e"': 1, '"+2E+2"': 200, '"0.1"': unpack(pack(Fraction(1, 10)))}
        self.assertEqual(real_values([f"REALVAL({s})" for s in vals]), [Fraction(v) for v in vals.values()])
        texts = ['"12x"', '" -0.25E-2 "', '""', '"."', '"1e"', '"+7"', '"1E99"', '"5."', '"-"', '"3"']
        src = "DIM S$ AS STRING\n" + "".join(
            f"IF ISNUM({t}) THEN\nS$ = S$ + \"1\"\nELSE\nS$ = S$ + \"0\"\nEND IF\n" for t in texts)
        self.assertEqual(run(src + "MESSAGE S$\nEND\n").cpu.alerts, ["0100010101"])

    def test_comparisons(self):
        # 0.1 + 0.2 = 0.3 holds in this format: the rounded sum of the two
        # nearest REALs is the REAL nearest to 0.3 (checked with pbas.real).
        conds = ["1.5 < 2", "2.0 = 2", "-1.0 > -0.5", "-0.0 = 0.0", "1E-30 <> 0", "X >= 3 AND X <= 3.0",
                 "0.1 + 0.2 = 0.3", "-2.5 < -2", "1E30 > 1E29", "X <> 3"]
        src = "DIM X AS REAL\nDIM S$ AS STRING\nX = 3\n" + "".join(
            f"IF {c} THEN\nS$ = S$ + \"1\"\nELSE\nS$ = S$ + \"0\"\nEND IF\n" for c in conds)
        self.assertEqual(run(src + "MESSAGE S$\nEND\n").cpu.alerts, ["1101111110"])

    def test_runtime_errors(self):
        cases = {"X = 1E30 * 1E30": "number out of range", "X = 1.0 / 0": "division by zero",
                 "X = SQR(-1.0)": "function argument out of range", "X = LOG(0.0)": "function argument out of range",
                 "X = EXP(100.0)": "number out of range", "N = CINT(40000.0)": "number out of range",
                 'X = REALVAL("1E99")': "number out of range", "X = TAN(60000.0)": "number out of range",
                 "X = 0.0 ^ -1": "division by zero", "X = (-8.0) ^ 0.5": "function argument out of range"}
        for stmt, error in cases.items():
            with self.subTest(stmt=stmt):
                r = run(f"DIM X AS REAL\nDIM N AS INTEGER\n{stmt}\nMESSAGE \"not reached\"\nEND\n")
                self.assertEqual(r.cpu.alerts, [f"Runtime error: {error} at line 3"])
        self.assertEqual(real_values(["EXP(-100.0)", "1E-30 * 1E-30"]), [0, 0])  # underflow is zero

    def test_real_procedures_and_arrays(self):
        src = ("DIM A(4) AS REAL\nDIM I AS INTEGER\nDIM T AS REAL\n"
               "FUNCTION Mean(N AS INTEGER) AS REAL\nLOCAL S AS REAL\nLOCAL K AS INTEGER\n"
               "FOR K = 1 TO N\nS = S + A(K)\nNEXT K\nRETURN S / N\nEND FUNCTION\n"
               "FOR I = 1 TO 4\nA(I) = I * 1.5\nNEXT I\nT = Mean(4)\nMESSAGE STR$(T)\n"
               "MESSAGE STR$(Mean(2) * 2)\nEND\n")
        self.assertEqual(run(src).cpu.alerts, ["3.75", "4.5"])


if __name__ == "__main__":
    unittest.main()
