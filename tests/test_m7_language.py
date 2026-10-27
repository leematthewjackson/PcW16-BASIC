"""M7 — procedures with parameters, FUNCTION, LOCAL, CONST, SELECT CASE,
EXIT FOR/WHILE, constant STEP, integer bit operators and the new built-in
functions (LANGUAGE-SPEC.md §3, §5.3). Behaviour runs on the project
simulator under the memory checker: engineering evidence, not XAnne.
"""
from __future__ import annotations

import unittest

from memguard import guarded_run
from pbas import SourceError, check_source, generate
from toolchain import requires_pasmo


def run(src: str, **kw):
    r = guarded_run(src, **kw)
    assert r.violations == [], r.violations
    return r.cpu.alerts


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return caught.exception

    def test_procedure_rules(self):
        cases = {
            "SUB A(X AS INTEGER)\nEND SUB\nCALL A()\nEND\n": "A expects 1 argument, got 0",
            "SUB A(X AS INTEGER)\nEND SUB\nCALL A(1, 2)\nEND\n": "A expects 1 argument, got 2",
            'SUB A(X AS INTEGER)\nEND SUB\nCALL A("s")\nEND\n': "cannot assign STRING to INTEGER variable X (in A)",
            "SUB A(X)\nEND SUB\nEND\n": "parameter X needs a type",
            "SUB A(X AS INTEGER, X AS INTEGER)\nEND SUB\nEND\n": "duplicate parameter X",
            "FUNCTION F() AS INTEGER\nRETURN F()\nEND FUNCTION\nEND\n": "recursive CALL is not allowed",
            "FUNCTION F() AS INTEGER\nRETURN \"x\"\nEND FUNCTION\nEND\n": "cannot assign STRING to INTEGER variable the result of FUNCTION F",
            "RETURN 1\nEND\n": "RETURN is only allowed inside a FUNCTION",
            "SUB A\nRETURN 1\nEND SUB\nEND\n": "RETURN is only allowed inside a FUNCTION",
            "LOCAL X AS INTEGER\nEND\n": "LOCAL is only allowed inside a SUB or FUNCTION",
            "SUB A\nLOCAL X(3) AS INTEGER\nEND SUB\nEND\n": "LOCAL arrays are not supported",
            "SUB A(X AS INTEGER)\nLOCAL X AS INTEGER\nEND SUB\nEND\n": "already a parameter or LOCAL",
            "FUNCTION F() AS INTEGER\nEND FUNCTION\nCALL F\nEND\n": "is a FUNCTION",
            "SUB A\nEND SUB\nDIM X AS INTEGER\nX = A()\nEND\n": "is a SUB",
            # (M13: allowed when the AND/OR is plainly BOOLEAN, lowered to keep
            # short-circuit evaluation; test_m13_language. Still refused here:)
            "FUNCTION F() AS INTEGER\nRETURN 1\nEND FUNCTION\nDIM A AS INTEGER\nDIM B AS INTEGER\nA = B AND F()\nEND\n":
                "called on the right of an AND/OR that is not plainly BOOLEAN",
            'FUNCTION F$() AS INTEGER\nEND FUNCTION\nEND\n': "uses $ suffix but returns INTEGER",
            "SUB A\nEXIT FUNCTION\nEND SUB\nEND\n": "EXIT FUNCTION is only allowed inside a FUNCTION",
            "FUNCTION F() AS INTEGER\nEXIT SUB\nEND FUNCTION\nEND\n": "use EXIT FUNCTION or RETURN",
            "FUNCTION F() AS INTEGER\nEND SUB\nEND\n": "END SUB without matching SUB",
            'WINDOW "W"\nBUTTON "Go", A\nSUB A(X AS INTEGER)\nEND SUB\nEND\n': "cannot be an event handler",
            'WINDOW "W"\nBUTTON "Go", F\nFUNCTION F() AS INTEGER\nEND FUNCTION\nEND\n': "cannot be an event handler",
        }
        for src, fragment in cases.items():
            with self.subTest(src=src):
                self.assertIn(fragment, self.reject(src).message)

    def test_const_select_loop_rules(self):
        cases = {
            "CONST N = 3\nN = 4\nEND\n": "N is a CONST and cannot be changed",
            "CONST N = 3\nDIM N AS INTEGER\nEND\n": "N is already a CONST (names do not depend on upper or lower case)",
            "CONST N = 3\nCONST N = 4\nEND\n": "duplicate CONST N",
            "DIM X AS INTEGER\nCONST N = X\nEND\n": "CONST value must be a literal",
            'CONST N$ = 3\nEND\n': "uses $ suffix but its value is not a STRING",
            "SUB A\nCONST N = 1\nEND SUB\nEND\n": "CONST is only allowed at the top level",
            # (M13: a parameter or LOCAL may have a CONST's name; test_m13_language)
            "CONST N = 1\nSUB A\nN = 2\nEND SUB\nEND\n": "N is a CONST and cannot be changed",
            "CASE 1\nEND\n": "CASE without SELECT CASE",
            "END SELECT\nEND\n": "END SELECT without SELECT CASE",
            "SELECT CASE 1\nEND\n": "SELECT CASE without END SELECT",
            "SELECT CASE 1\nCASE ELSE\nCASE 2\nEND SELECT\nEND\n": "CASE after CASE ELSE",
            "FUNCTION F() AS INTEGER\nEND FUNCTION\nSELECT CASE 1\nCASE F()\nEND SELECT\nEND\n":
                "CASE values may not call a FUNCTION",
            'SELECT CASE 1\nCASE "a"\nEND SELECT\nEND\n': "comparison = requires matching types",
            "EXIT FOR\nEND\n": "EXIT FOR is only allowed inside a FOR loop",
            "DIM I AS INTEGER\nWHILE TRUE\nEXIT FOR\nWEND\nEND\n": "EXIT FOR is only allowed inside a FOR loop",
            "DIM I AS INTEGER\nFOR I = 1 TO 2\nSUB_X = 1\nNEXT I\nEND\n": "undefined variable SUB_X",
            "DIM I AS INTEGER\nDIM S AS INTEGER\nFOR I = 1 TO 4 STEP S\nNEXT I\nEND\n": "STEP must be a non-zero INTEGER constant",
            "DIM I AS INTEGER\nFOR I = 1 TO 4 STEP 0\nNEXT I\nEND\n": "STEP must be a non-zero INTEGER constant",
        }
        for src, fragment in cases.items():
            with self.subTest(src=src):
                self.assertIn(fragment, self.reject(src).message)
        # a loop exit cannot leave a SUB through the loop that called it
        self.assertIn("EXIT WHILE is only allowed", self.reject(
            "SUB A\nEXIT WHILE\nEND SUB\nWHILE TRUE\nCALL A\nWEND\nEND\n").message)
        check_source("CONST STEPS = -2\nDIM I AS INTEGER\nFOR I = 9 TO 1 STEP STEPS\nNEXT I\nEND\n")

    def test_builtin_rules(self):
        cases = {
            "DIM X AS INTEGER\nX = ABS(\"a\")\nEND\n": "ABS expects a number",
            "DIM X AS INTEGER\nX = MIN(1)\nEND\n": "MIN expects 2 arguments",
            'DIM X AS INTEGER\nX = MAX(1, "a")\nEND\n': "MAX expects two numbers, got INTEGER and STRING",
            "DIM X AS INTEGER\nX = RND(0)\nEND\n": "RND(n) needs n of at least 1",
            'DIM S$ AS STRING\nS$ = TRIM$(3)\nEND\n': "TRIM$ expects a STRING",
            'DIM S$ AS STRING\nS$ = STRING$(3, 0)\nEND\n': "STRING$ character code must be 1..255",
            'DIM S$ AS STRING\nS$ = SPACE$(-1)\nEND\n': "SPACE$ count must be at least 0",
            'DIM S$ AS STRING\nS$ = SPACE$(64)\nEND\n': "at least 64 characters",
            'RANDOMIZE "x"\nEND\n': "RANDOMIZE expects an INTEGER seed",
            'DIM T AS BOOLEAN\nT = 1 XOR TRUE\nEND\n': "XOR requires two BOOLEAN or two INTEGER operands",
            'DIM ABS(3) AS INTEGER\nEND\n': "ABS is a built-in function",
        }
        for src, fragment in cases.items():
            with self.subTest(src=src):
                self.assertIn(fragment, self.reject(src).message)

    def test_old_names_still_usable(self):
        # the new statement words are contextual: still ordinary names elsewhere
        check_source("DIM Select AS INTEGER\nDIM Case AS INTEGER\nDIM Local AS INTEGER\n"
                     "DIM Return AS INTEGER\nSelect = 1\nCase = Select + 1\nLocal = Case\n"
                     "Return = Local\nEND\n")


@requires_pasmo
class BehaviourTests(unittest.TestCase):
    PROGRAM_A = '''CONST LIMIT = 10
CONST GREETING$ = "Hi"
DIM I AS INTEGER
DIM Total AS INTEGER
DIM S$ AS STRING
FUNCTION Square(N AS INTEGER) AS INTEGER
    RETURN N * N
END FUNCTION
FUNCTION Twice$(T$) AS STRING
    LOCAL K AS INTEGER
    K = K + 1
    RETURN T$ + T$ + STR$(K)
END FUNCTION
FUNCTION Grade$(Score AS INTEGER) AS STRING
    SELECT CASE Score
    CASE IS >= 90
        RETURN "A"
    CASE 70 TO 89
        RETURN "B"
    CASE 50, 60, 65
        RETURN "C"
    CASE ELSE
        RETURN "F"
    END SELECT
END FUNCTION
SUB Show(Label$, Value AS INTEGER)
    MESSAGE Label$ + "=" + STR$(Value)
END SUB
FOR I = 1 TO LIMIT STEP 3
    Total = Total + Square(I)
NEXT I
CALL Show("squares", Total)
CALL Show("sq", Square(Square(3)) + Square(2))
MESSAGE Twice$(GREETING$) + Twice$("x")
S$ = Grade$(95) + Grade$(75) + Grade$(60) + Grade$(10) + Grade$(65)
MESSAGE S$
S$ = ""
FOR I = 10 TO -10 STEP -7
    S$ = S$ + STR$(I) + ","
NEXT I
MESSAGE S$
Total = 0
WHILE TRUE
    Total = Total + 1
    IF Total = 4 THEN
        EXIT WHILE
    END IF
WEND
FOR I = 1 TO 100
    IF I * I > 50 THEN
        EXIT FOR
    END IF
NEXT I
CALL Show("exits", Total * 100 + I)
FOR I = 32760 TO 32767 STEP 4
    Total = I
NEXT I
CALL Show("edge", Total)
END
'''
    PROGRAM_B = '''DIM A AS INTEGER
DIM I AS INTEGER
DIM S$ AS STRING
DIM Hits(6) AS INTEGER
MESSAGE STR$(ABS(-5)) + " " + STR$(ABS(7)) + " " + STR$(SGN(-9)) + STR$(SGN(0)) + STR$(SGN(4))
MESSAGE STR$(MIN(3, -2)) + " " + STR$(MAX(3, -2)) + " " + STR$(MIN(-32768, 32767))
MESSAGE STR$(12 AND 10) + " " + STR$(12 OR 10) + " " + STR$(12 XOR 10) + " " + STR$(NOT 0)
MESSAGE STR$(SHL(1, 15)) + " " + STR$(SHR(-1, 12)) + " " + STR$(SHL(5, 16)) + " " + STR$(SHR(40, 0))
S$ = "[" + TRIM$("  ab c  ") + "][" + LTRIM$("  x ") + "][" + RTRIM$(" y  ") + "][" + TRIM$("   ") + "]"
MESSAGE S$
MESSAGE "[" + SPACE$(3) + "]" + STRING$(4, 42) + STRING$(0, 65)
RANDOMIZE 7
FOR I = 1 TO 600
    A = RND(6)
    Hits(A) = Hits(A) + 1
NEXT I
S$ = ""
FOR I = 1 TO 6
    S$ = S$ + STR$(Hits(I)) + " "
NEXT I
MESSAGE S$
IF TRUE XOR FALSE THEN
    MESSAGE "xor ok"
END IF
A = RND(0 - A)
END
'''

    def test_procedures_select_and_loops(self):
        self.assertEqual(run(self.PROGRAM_A), [
            "squares=166", "sq=85", "HiHi1xx1", "ABCFC", "10,3,-4,", "exits=408", "edge=32764"])

    def test_builtins(self):
        lines = self.PROGRAM_B.splitlines()
        line = next(i for i, ln in enumerate(lines, 1) if ln.startswith("A = RND(0 - A)"))
        self.assertEqual(run(self.PROGRAM_B), [
            "5 7 -101", "-2 3 -32768", "8 14 6 -1", "-32768 15 0 40", "[ab c][x ][ y][]",
            "[   ]****", "115 73 106 93 108 105 ", "xor ok",
            f"Runtime error: number out of range at line {line}"])

    def test_random_numbers(self):
        src = ("DIM I AS INTEGER\nDIM A AS INTEGER\nDIM Lo AS INTEGER\nDIM Hi AS INTEGER\n"
               "DIM Hits(10) AS INTEGER\nDIM S$ AS STRING\n{seed}Lo = 99\n"
               "FOR I = 1 TO 3000\nA = RND(10)\nLo = MIN(Lo, A)\nHi = MAX(Hi, A)\n"
               "Hits(A) = Hits(A) + 1\nNEXT I\nFOR I = 1 TO 10\nS$ = S$ + STR$(Hits(I)) + \",\"\n"
               "NEXT I\nMESSAGE STR$(Lo) + \" \" + STR$(Hi)\nMESSAGE S$\nEND\n")
        first = run(src.format(seed=""))
        self.assertEqual(first[0], "1 10")
        counts = [int(x) for x in first[1].rstrip(",").split(",")]
        self.assertTrue(all(240 <= c <= 360 for c in counts), counts)  # each about 300
        self.assertEqual(run(src.format(seed="RANDOMIZE 0\n")), first)  # 0 = the default seed 1
        self.assertEqual(run(src.format(seed="RANDOMIZE 1\n")), first)
        self.assertNotEqual(run(src.format(seed="RANDOMIZE 1234\n")), first)

    def test_string_and_shift_errors(self):
        for expr, error in (("SHL(1, -1)", "number out of range"), ("SPACE$(0 - 1)", "substring position out of range"),
                            ("STRING$(2, 0 + 256)", "character code out of range"),
                            ("SPACE$(50 + X) + SPACE$(X)", "string too long")):
            with self.subTest(expr=expr):
                src = ("DIM S$ AS STRING\nDIM X AS INTEGER\nX = 10\n"
                       + (f"X = {expr}\n" if expr.startswith("SHL") else f"S$ = {expr}\n") + "END\n")
                self.assertEqual(run(src), [f"Runtime error: {error} at line 4"])

    def test_function_in_while_condition_is_re_evaluated(self):
        src = ("DIM N AS INTEGER\nFUNCTION Below(Limit AS INTEGER) AS BOOLEAN\n"
               "RETURN N < Limit\nEND FUNCTION\nWHILE Below(5)\nN = N + 1\nWEND\n"
               "MESSAGE STR$(N)\nEND\n")
        self.assertEqual(run(src), ["5"])

    def test_string_parameters_and_capacity(self):
        src = ("FUNCTION Wrap$(T$, L AS INTEGER) AS STRING\nRETURN LEFT$(\"<<<<\", L) + T$ + \">\"\n"
               "END FUNCTION\nDIM S$ AS STRING\nS$ = Wrap$(Wrap$(\"x\", 1), 2)\nMESSAGE S$\n"
               "S$ = Wrap$(SPACE$(62), 1)\nEND\n")
        self.assertEqual(run(src), ["<<<x>>", "Runtime error: string too long at line 2"])

    def test_handlers_call_functions(self):
        src = ('DIM Total AS INTEGER\nDIM Shown$ AS STRING\nWINDOW "W"\nLABEL Shown$\n'
               'BUTTON "Add", AddOne\nFUNCTION Bump(V AS INTEGER) AS INTEGER\nRETURN V + 2\n'
               'END FUNCTION\nSUB AddOne\nTotal = Bump(Total)\nShown$ = STR$(Total)\nEND SUB\nEND\n')
        r = guarded_run(src, events=[("click", 4), ("click", 4)])  # 2 label box, 3 label, 4 button
        self.assertEqual(r.violations, [])
        self.assertEqual(r.cpu.label_text(3, shown=True), "4")


if __name__ == "__main__":
    unittest.main()
