"""M5b — numbers and text (LANGUAGE-SPEC.md §3, §8).

Integer ``/`` and ``MOD``, ``VAL``, ``ASC``, ``CHR$``, ``INSTR`` and STRING
ordering. Behaviour tests build with Pasmo and run on the project simulator
under the M2.1 memory checker; none of this is XAnne evidence.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run
from pbas import SourceError, check_source, generate, tokenize
from test_controls import numbers
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parent.parent
DIV_ERR = "Runtime error: division by zero at line {}"
VAL_ERR = "Runtime error: number out of range at line {}"
CHR_ERR = "Runtime error: character code out of range at line {}"
SUB_ERR = "Runtime error: substring position out of range at line {}"


def gen(src: str) -> str:
    return generate(check_source(src))


# ------------------------------------------------------------- frontend
class M5bFrontendTests(unittest.TestCase):
    def reject(self, src: str) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            check_source(src)
        return caught.exception

    def test_mod_is_an_operator_token_in_any_case(self):
        kinds = [(t.kind, t.value) for t in tokenize("X = A mod B\n") if t.kind == "OP"]
        self.assertIn(("OP", "MOD"), kinds)

    def test_mod_is_reserved(self):
        err = self.reject("DIM Mod AS INTEGER\nEND\n")
        self.assertEqual(err.line, 1)

    def test_precedence(self):
        # MOD and / bind like *: 2 + 7 MOD 4 * 3 = 2 + ((7 MOD 4) * 3)
        check_source("DIM X AS INTEGER\nX = 2 + 7 MOD 4 * 3 - 8 / 2\nEND\n")

    def test_types(self):
        cases = {
            'DIM S$ AS STRING\nDIM X AS INTEGER\nX = S$ / 2\nEND\n': "operator / requires numbers",
            'DIM X AS INTEGER\nX = VAL(5)\nEND\n': "VAL expects a STRING",
            'DIM X AS INTEGER\nX = ASC(5)\nEND\n': "ASC expects a STRING",
            'DIM S$ AS STRING\nS$ = CHR$("A")\nEND\n': "CHR$ expects an INTEGER",
            'DIM X AS INTEGER\nX = INSTR("a")\nEND\n': "INSTR expects 2 or 3 arguments",
            'DIM X AS INTEGER\nX = INSTR(1, 2, "a")\nEND\n': "INSTR expects (STRING, STRING) or",
            'DIM S$ AS STRING\nS$ = VAL("1")\nEND\n': "cannot assign INTEGER to STRING",
        }
        for src, fragment in cases.items():
            with self.subTest(src=src):
                self.assertIn(fragment, self.reject(src).message)

    def test_constant_arguments_checked_at_compile_time(self):
        for src, fragment, pos in (
            ("DIM X AS INTEGER\nX = X / 0\nEND\n", "division by zero (/ 0)", (2, 9)),
            ("DIM X AS INTEGER\nX = X MOD 0\nEND\n", "division by zero (MOD 0)", (2, 11)),
            ('DIM S$ AS STRING\nS$ = CHR$(0)\nEND\n', "must be 1..255, got 0", (2, 11)),
            ('DIM S$ AS STRING\nS$ = CHR$(256)\nEND\n', "must be 1..255, got 256", (2, 11)),
            ('DIM X AS INTEGER\nX = INSTR(0, "a", "b")\nEND\n', "INSTR start position must be at least 1", (2, 11)),
        ):
            with self.subTest(src=src):
                err = self.reject(src)
                self.assertIn(fragment, err.message)
                self.assertEqual((err.line, err.column), pos)

    def test_string_ordering_needs_matching_types(self):
        check_source('DIM A$ AS STRING\nIF A$ + "x" >= "b" THEN\nEND IF\nEND\n')
        self.assertIn("two INTEGER or two STRING",
                      self.reject('DIM A$ AS STRING\nIF A$ < 1 THEN\nEND IF\nEND\n').message)


class M5bCodegenTests(unittest.TestCase):
    def test_sections_only_when_used(self):
        plain = gen('DIM X AS INTEGER\nX = 1 + 2\nEND\n')
        for name in ("DIV", "VAL", "ASC", "CHR", "INSTR"):
            self.assertIn(f"PB_{name} equ 0", plain)
        used = gen('DIM X AS INTEGER\nDIM S$ AS STRING\nX = X / 3 + VAL(S$) + ASC(S$) + INSTR(S$, "a")\n'
                   'S$ = CHR$(65)\nEND\n')
        for name in ("DIV", "VAL", "ASC", "CHR", "INSTR"):
            self.assertIn(f"PB_{name} equ 1", used)

    def test_runtime_error_statements_record_their_line(self):
        asm = gen('DIM X AS INTEGER\nDIM Y AS INTEGER\nX = 7\nY = X MOD X\nEND\n')
        self.assertIn("ld hl,4\n    ld (rt_err_line),hl", asm)
        self.assertNotIn("ld hl,3\n    ld (rt_err_line),hl", asm)

    def test_no_os_calls_in_generated_code(self):
        asm = gen('DIM S$ AS STRING\nDIM X AS INTEGER\nX = INSTR(2, S$ + "x", CHR$(65)) / VAL(S$)\nEND\n')
        self.assertNotRegex(asm, r"call\s+003Bh")


# ------------------------------------------------------------- behaviour
@requires_pasmo
class M5bBehaviourTests(unittest.TestCase):
    maxDiff = None

    def run_ok(self, src: str, **kw):
        run = guarded_run(src, **kw)
        self.assertEqual(run.violations, [], "memory-boundary violations")
        return run

    def ints(self, setup: str, exprs: list[str]) -> list[int]:
        body = "".join(f"N = {e}\nMESSAGE STR$(N)\n" for e in exprs)
        run = self.run_ok(f"DIM N AS INTEGER\nDIM A AS INTEGER\nDIM B AS INTEGER\nDIM S$ AS STRING\n{setup}{body}END\n")
        self.assertTrue(run.cpu.exited, run.alerts)
        return [int(a) for a in run.alerts]

    def test_division_matches_truncation_toward_zero(self):
        pairs = [(7, 2), (-7, 2), (7, -2), (-7, -2), (0, 5), (5, 7), (-32768, 1), (-32768, -1),
                 (-32768, 7), (32767, -1), (32767, 32767), (-32768, -32768), (1, -32768), (100, 10)]
        exprs, want = [], []
        for a, b in pairs:
            q = abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)
            q = (q + 32768) % 65536 - 32768  # -32768 / -1 wraps (spec §2)
            r = a - (abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)) * b
            exprs += [f"({a}) / ({b})", f"({a}) MOD ({b})"]
            want += [q, r]
        self.assertEqual(self.ints("", exprs), want)

    def test_div_and_mod_through_variables(self):
        self.assertEqual(self.ints("A = -45\nB = 4\n", ["A / B", "A MOD B", "A / B * B + A MOD B"]),
                         [-11, -1, -45])

    def test_val(self):
        cases = {
            '""': 0, '"abc"': 0, '"-"': 0, '"+"': 0, '"   "': 0, '"0"': 0, '"-0"': 0,
            '"42"': 42, '"  42"': 42, '"42 "': 42, '"12abc"': 12, '"+7"': 7, '"-7"': -7,
            '"007"': 7, '"32767"': 32767, '"-32768"': -32768, '"3276"': 3276,
            '"000000000032767"': 32767, '"1 2"': 1, '" -5x9"': -5, '"--5"': 0,
            'S$ + "9"': 19, 'STR$(-1234)': -1234,
        }
        got = self.ints('S$ = "1"\n', [f"VAL({e})" for e in cases])
        self.assertEqual(dict(zip(cases, got)), cases)

    def test_val_out_of_range_is_a_runtime_error(self):
        # "65537" / "655370" / "131072" / "-65546" would wrap to small values
        # in 16 bits: the per-digit check must catch them, not the final one.
        for text in ("32768", "-32769", "99999", "327670", "-40000", "65537", "655370",
                     "131072", "-65546", "32768000"):
            with self.subTest(text=text):
                run = self.run_ok(f'DIM N AS INTEGER\nN = 5\nN = VAL("{text}")\nMESSAGE "no"\nEND\n')
                self.assertEqual(run.alerts, [VAL_ERR.format(3)])
                self.assertTrue(run.cpu.exited)

    def test_asc_and_chr(self):
        self.assertEqual(self.ints('S$ = "Zz"\n', ['ASC(S$)', 'ASC("a")', 'ASC("")', 'ASC(MID$(S$, 2, 1))',
                                                   'ASC(CHR$(200))', 'ASC(CHR$(1))', 'ASC(CHR$(255))']),
                         [90, 97, -1, 122, 200, 1, 255])
        run = self.run_ok('DIM N AS INTEGER\nDIM S$ AS STRING\nN = 66\nS$ = CHR$(N - 1) + CHR$(N) + CHR$(N + 1)\n'
                          'MESSAGE S$ + STR$(LEN(S$))\nEND\n')
        self.assertEqual(run.alerts, ["ABC3"])

    def test_chr_out_of_range_is_a_runtime_error(self):
        for n in ("0", "256", "-1", "-32768", "1000"):
            with self.subTest(n=n):
                run = self.run_ok(f'DIM N AS INTEGER\nDIM S$ AS STRING\nN = {n}\nS$ = "a" + CHR$(N)\nEND\n')
                self.assertEqual(run.alerts, [CHR_ERR.format(4)])

    def test_instr(self):
        cases = {
            'INSTR(S$, "an")': 2, 'INSTR(S$, "ana")': 2, 'INSTR(S$, "nana")': 3, 'INSTR(S$, "banana")': 1,
            'INSTR(S$, "bananas")': 0, 'INSTR(S$, "x")': 0, 'INSTR(S$, "a")': 2, 'INSTR(S$, "")': 1,
            'INSTR(1, S$, "an")': 2, 'INSTR(3, S$, "an")': 4, 'INSTR(5, S$, "an")': 0,
            'INSTR(6, S$, "a")': 6, 'INSTR(7, S$, "a")': 0, 'INSTR(7, S$, "")': 7, 'INSTR(8, S$, "")': 0,
            'INSTR(30000, S$, "")': 0, 'INSTR("", "")': 1, 'INSTR("", "a")': 0,
            'INSTR(S$ + "!", "a!")': 6, 'INSTR(A, S$, CHR$(110))': 3, 'INSTR("aAa", "A")': 2,
        }
        got = self.ints('S$ = "banana"\nA = 2\n', list(cases))
        self.assertEqual(dict(zip(cases, got)), cases)

    def test_instr_computed_start_below_one_is_the_substring_error(self):
        run = self.run_ok('DIM N AS INTEGER\nDIM A AS INTEGER\nA = 0\nN = INSTR(A, "abc", "b")\nEND\n')
        self.assertEqual(run.alerts, [SUB_ERR.format(4)])

    def test_division_by_zero_is_a_runtime_error(self):
        for stmt in ("N = 5 / A", "N = 5 MOD A", "MESSAGE STR$(10 / A)", "IF 1 / A = 0 THEN\nEND IF"):
            with self.subTest(stmt=stmt):
                run = self.run_ok(f"DIM N AS INTEGER\nDIM A AS INTEGER\nA = 0\n{stmt}\nMESSAGE \"no\"\nEND\n")
                self.assertEqual(run.alerts, [DIV_ERR.format(4)])
                self.assertTrue(run.cpu.exited)

    def test_string_ordering(self):
        pairs = [("apple", "banana"), ("abc", "abcd"), ("", "a"), ("Zebra", "apple"), ("b", "a"),
                 ("same", "same"), ("a", ""), ("A1", "A2"), ("~", "a")]
        ops = ["<", "<=", ">", ">="]
        body, want = "", []
        for a, b in pairs:
            for op in ops:
                body += f'IF "{a}" {op} "{b}" THEN\nMESSAGE "T"\nELSE\nMESSAGE "F"\nEND IF\n'
                want.append("T" if eval(f"{a!r}.encode() {op} {b!r}.encode()") else "F")
        run = self.run_ok(body + "END\n")
        self.assertEqual(run.alerts, want)

    def test_ordering_of_computed_and_variable_operands(self):
        run = self.run_ok('DIM A$ AS STRING\nDIM B$ AS STRING\nA$ = "ab"\nB$ = "ab"\n'
                          'IF A$ + "c" > B$ THEN\nMESSAGE "1"\nEND IF\n'
                          'IF LEFT$(A$, 1) < B$ THEN\nMESSAGE "2"\nEND IF\n'
                          'IF A$ >= B$ THEN\nMESSAGE "3"\nEND IF\n'
                          'IF CHR$(200) > "z" THEN\nMESSAGE "4 unsigned"\nEND IF\nEND\n')
        self.assertEqual(run.alerts, ["1", "2", "3", "4 unsigned"])

    def test_values_in_a_bound_textbox(self):
        src = (ROOT / "examples" / "calculator.pbas").read_text(encoding="utf-8")
        n = numbers(src)
        run = self.run_ok(src, events=[("edit", n["FIRST$"], "-45"), ("edit", n["SECOND$"], "4"),
                                       ("click", n["Divide"])])
        self.assertEqual(run.alerts, ["-45 / 4 = -11 remainder -1"])
        self.assertEqual(run.cpu.control_text(n["FIRST$"], shown=True), "-11")


@requires_pasmo
class M5bExampleTests(unittest.TestCase):
    def run_file(self, path: Path, **kw):
        run = guarded_run(path.read_text(encoding="utf-8"), **kw)
        self.assertEqual(run.violations, [])
        return run

    def test_calculator(self):
        path = ROOT / "examples" / "calculator.pbas"
        n = numbers(path.read_text(encoding="utf-8"))
        run = self.run_file(path, events=[
            ("click", n["Divide"]), ("click", n["Swap"]), ("edit", n["SECOND$"], "0"),
            ("click", n["Divide"]), ("click", n["Quit"]),
        ])
        self.assertEqual(run.alerts, ["100 / 7 = 14 remainder 2", "Cannot divide 7 by zero"])
        self.assertEqual(run.cpu.control_text(n["FIRST$"], shown=True), "7")
        self.assertEqual(run.cpu.control_text(n["SECOND$"], shown=True), "0")
        self.assertTrue(run.cpu.exited)
        run = self.run_file(path, events=[("edit", n["FIRST$"], "40000"), ("click", n["Divide"])])
        self.assertEqual(run.alerts, [VAL_ERR.format(18)])

    def test_char_codes(self):
        run = self.run_file(ROOT / "examples" / "char_codes.pbas")
        self.assertEqual(run.alerts, ["Coded: KHOOR SFZ16", "Decoded: HELLO PCW16",
                                      "Code of H is 72, empty gives -1"])

    def test_word_sort(self):
        disk = z80sim.Disk()
        run = self.run_file(ROOT / "examples" / "word_sort.pbas", disk=disk)
        self.assertEqual(run.alerts, [
            "Commas at 5 and 11", "Fields: pear apple", "and fig",
            "File saved: PBSORT.TXT", "File loaded: PBSORT.TXT",
            "Sorted: apple,fig,pear", "No grape in 14 characters",
        ])
        self.assertEqual(disk.file("PBSORT.TXT"), b"apple,fig,pear")

    def test_xanne_edge_program(self):
        run = self.run_file(ROOT / "developer-tests" / "m5b_edges.pbas")
        self.assertEqual(run.alerts, [
            "1 -3 -1 -3 1", "2 -32768 0 -4681", "3 -12 0 32767 -32768", "4 97 -1 PcW",
            "5 2 4 0 7 0", "6 capitals sort first", "7 about to divide by 0", DIV_ERR.format(21),
        ])
        self.assertTrue(run.cpu.exited)


if __name__ == "__main__":
    unittest.main()
