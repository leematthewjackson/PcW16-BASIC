"""M13 Stage J: language consistency (LANGUAGE-SPEC §5.1, §7).

- A parameter or LOCAL may have the name of a CONST, as it may have the
  name of a global variable: inside its procedure the name is the
  parameter. So a library's parameter names (W, H, CW, CH, ...) cannot
  clash with a program's constants. Outside the procedure, and inside a
  procedure that does not declare the name, the CONST is unchanged and
  still cannot be assigned.
- OPEN takes a STRING file name, as KILL, NAME, TEXT, DB and BITMAP do,
  checked when it runs (IOERR 247 for an invalid name: nothing opened). A
  literal name compiles exactly as before.
- A FUNCTION may be called on the right of a BOOLEAN AND / OR (one side a
  comparison, NOT, TRUE/FALSE or a FUNCTION AS BOOLEAN). It is lowered to
  T = left : IF T THEN (the call) : T = right, so the call runs only when
  its value is needed: short-circuit evaluation holds, and a call with a
  side effect shows it. Programs that compiled before are unchanged (this
  was a compile error).
Simulator evidence.
"""
from __future__ import annotations

import unittest

from memguard import guarded_run
from pbas import SourceError, check_source, generate
from toolchain import requires_pasmo

SHADOW = """CONST W = 100
CONST H = 7
DIM R AS INTEGER
FUNCTION Area(W AS INTEGER, X AS INTEGER) AS INTEGER
    LOCAL H AS INTEGER
    H = X
    W = W + 1
    RETURN W * H
END FUNCTION
SUB Count
    LOCAL W AS INTEGER
    FOR W = 1 TO 3
        R = R + W
    NEXT W
    R = R + H
END SUB
R = Area(4, 5)
MESSAGE STR$(R) + " " + STR$(W) + " " + STR$(H)
R = 0
CALL Count
MESSAGE STR$(R)
END
"""


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> str:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return caught.exception.message

    def test_a_const_is_still_constant_where_it_is_not_shadowed(self):
        self.assertIn("W is a CONST and cannot be changed",
                      self.reject("CONST W = 1\nSUB A(X AS INTEGER)\nW = X\nEND SUB\nEND\n"))
        self.assertIn("W is a CONST and cannot be changed",
                      self.reject("CONST W = 1\nSUB A(W AS INTEGER)\nEND SUB\nW = 2\nEND\n"))
        self.assertIn("W is already a CONST (names do not depend on upper or lower case): DIM another name",
                      self.reject("CONST W = 1\nSUB A\nEND SUB\nDIM w AS INTEGER\nEND\n"))

    def test_shadowing_compiles(self):
        generate(check_source(SHADOW))


@requires_pasmo
class BehaviourTests(unittest.TestCase):
    def test_the_parameter_or_local_wins_inside_only(self):
        r = guarded_run(SHADOW)
        self.assertEqual(r.violations, [])
        # Area: (4 + 1) * 5; outside, W and H are the CONSTs; Count: 1+2+3 + H (the CONST)
        self.assertEqual(r.cpu.alerts, ["25 100 7", "13"])


OPENS = """DIM N$ AS STRING
DIM L$ AS STRING
DIM E AS INTEGER
N$ = "out" + ".txt"
OPEN N$ FOR OUTPUT AS #1
E = IOERR
PRINT #1, "first"
CLOSE #1
OPEN N$ FOR INPUT AS #2
LINE INPUT #2, L$
CLOSE #2
MESSAGE STR$(E) + " " + L$
N$ = "BAD NAME.TXT"
OPEN N$ FOR OUTPUT AS #1
E = IOERR
PRINT #1, "x"
MESSAGE STR$(E) + " " + STR$(IOERR)
END
"""


@requires_pasmo
class OpenTests(unittest.TestCase):
    def test_open_takes_a_string_name(self):
        import z80sim
        r = guarded_run(OPENS, disk=z80sim.Disk())
        self.assertEqual(r.violations, [])
        self.assertEqual(r.cpu.alerts[0], "0 first")
        e, after = r.cpu.alerts[1].split()
        self.assertEqual(e, "247")  # the name is refused: nothing is opened ...
        self.assertNotEqual(after, "0")  # ... so the PRINT # fails too
        self.assertEqual(r.cpu.disk.file("OUT.TXT"), b"first\r\n")

    def test_a_literal_open_compiles_as_before(self):
        src = 'OPEN "A.TXT" FOR OUTPUT AS #1\nCLOSE #1\nEND\n'
        self.assertNotIn("call rt_fname", generate(check_source(src)))  # no run-time name check
        self.assertIn("call rt_fname", generate(check_source(src.replace('"A.TXT"', 'LCASE$("A.TXT")'))))

    def test_open_of_a_number_is_refused(self):
        with self.assertRaises(SourceError) as caught:
            generate(check_source("DIM N AS INTEGER\nOPEN N FOR OUTPUT AS #1\nEND\n"))
        self.assertIn("a file name is a STRING", caught.exception.message)


SHORT = """DIM Calls AS INTEGER
DIM I AS INTEGER
DIM N AS INTEGER
DIM B AS BOOLEAN
FUNCTION Big(X AS INTEGER) AS BOOLEAN
    Calls = Calls + 1
    RETURN X > 10
END FUNCTION
FUNCTION Twice(X AS INTEGER) AS INTEGER
    Calls = Calls + 100
    RETURN 2 * X
END FUNCTION
IF 1 > 2 AND Big(50) THEN
    MESSAGE "wrong"
END IF
MESSAGE "a" + STR$(Calls)
IF 3 > 2 AND Big(50) THEN
    MESSAGE "b" + STR$(Calls)
END IF
B = 3 > 2 OR Big(50)
MESSAGE "c" + STR$(Calls)
B = NOT Big(1) AND NOT Big(2)
MESSAGE "d" + STR$(Calls)
B = Big(1) OR Twice(3) > 5 AND Big(20)
MESSAGE "e" + STR$(Calls)
WHILE N < 3 AND Twice(N) < 100
    N = N + 1
WEND
MESSAGE "f" + STR$(Calls) + " " + STR$(N)
FOR I = 1 TO 4
    IF I MOD 2 = 0 AND Big(I * 10) THEN
        MESSAGE "g" + STR$(I)
    END IF
NEXT I
MESSAGE "h" + STR$(Calls)
END
"""


@requires_pasmo
class ShortCircuitTests(unittest.TestCase):
    def test_a_function_on_the_right_runs_only_when_needed(self):
        r = guarded_run(SHORT)
        self.assertEqual(r.violations, [])
        self.assertEqual(r.cpu.alerts, [
            "a0",       # FALSE AND Big(): not called
            "b1",       # TRUE AND Big(50): called, TRUE
            "c1",       # TRUE OR Big(): not called
            "d3",       # NOT Big(1) is TRUE, so NOT Big(2) is called too
            "e105",     # Big(1) FALSE, so Twice(3) > 5 AND Big(20): both called
            "f405 3",   # Twice runs for N = 0, 1, 2; at N = 3 the left side is FALSE: not called
            "g2", "g4",  # I = 2, 4: Big(20), Big(40)
            "h407",     # Big ran only for the even I
        ])

    def test_still_refused_where_the_type_is_not_plain(self):
        src = ("FUNCTION F() AS INTEGER\nRETURN 1\nEND FUNCTION\nDIM A AS INTEGER\nDIM B AS INTEGER\n"
               "A = B AND F()\nEND\n")
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        self.assertIn("not plainly BOOLEAN", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
