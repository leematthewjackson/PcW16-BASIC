"""M5c — logic and procedures (LANGUAGE-SPEC.md §1, §3, §5, §8).

``AND`` / ``OR`` / ``NOT`` on BOOLEAN with short-circuit evaluation,
``CALL Name`` (no recursion, at most 16 procedures active at once),
``EXIT SUB``, and ``UCASE$`` / ``LCASE$``. Behaviour tests build with Pasmo
and run on the project simulator under the M2.1 memory checker; none of
this is XAnne evidence.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import z80sim
from memguard import _symbols, guarded_run
from pbas import SourceError, check_source, generate, parse, tokenize
from pbas import ast_nodes as ast
from pbas.policy import MAX_CALL_DEPTH
from pbas.prg import build
from test_controls import numbers
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parent.parent
DIV_ERR = "Runtime error: division by zero at line {}"
VAL_ERR = "Runtime error: number out of range at line {}"
LONG_ERR = "Runtime error: string too long at line {}"


def gen(src: str) -> str:
    return generate(check_source(src))


def chain(levels: int, main_calls: bool = True) -> str:
    """A program whose SUBs L1..Ln call each other in a line."""
    subs = "".join(
        f"SUB L{i}\n    D = D + 1\n" + (f"    CALL L{i + 1}\n" if i < levels else "    M = D\n")
        + "END SUB\n"
        for i in range(1, levels + 1)
    )
    main = "CALL L1\nMESSAGE STR$(M)\n" if main_calls else ""
    return f"DIM D AS INTEGER\nDIM M AS INTEGER\n{main}{subs}END\n"


# ------------------------------------------------------------- frontend
class M5cFrontendTests(unittest.TestCase):
    def reject(self, src: str) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            check_source(src)
        return caught.exception

    def expr(self, text: str):
        nodes = parse(f"DIM T AS BOOLEAN\nT = {text}\nEND\n")
        return nodes[1].value

    def shape(self, node) -> str:
        if isinstance(node, ast.Binary):
            return f"({self.shape(node.left)} {node.op} {self.shape(node.right)})"
        if isinstance(node, ast.Unary):
            return f"({node.op} {self.shape(node.operand)})"
        if isinstance(node, ast.Var):
            return node.name
        if isinstance(node, ast.BoolLiteral):
            return "T" if node.value else "F"
        if isinstance(node, ast.IntLiteral):
            return str(node.value)
        raise AssertionError(node)

    def test_logical_words_are_operator_tokens_in_any_case(self):
        ops = [t.value for t in tokenize("T = not A and B Or C\n") if t.kind == "OP"]
        self.assertEqual(ops, ["=", "NOT", "AND", "OR"])
        self.assertEqual(tokenize("CALL X\n")[0].kind, "CALL")

    def test_new_words_are_reserved(self):
        for word in ("AND", "Or", "not", "CALL"):
            with self.subTest(word=word):
                self.reject(f"DIM {word} AS INTEGER\nEND\n")
        self.reject("SUB And\nEND SUB\nEND\n")
        # still fine inside strings and as parts of longer names
        check_source('DIM Order AS INTEGER\nDIM Notes$ AS STRING\nDIM Andy AS BOOLEAN\n'
                     'Notes$ = "and or not call"\nEND\n')

    def test_precedence_and_grouping(self):
        cases = {
            "NOT A = B": "(NOT (A = B))",
            "A OR B AND C": "(A OR (B AND C))",
            "A AND B OR C": "((A AND B) OR C)",
            "NOT A AND B": "((NOT A) AND B)",
            "NOT A OR B": "((NOT A) OR B)",
            "NOT NOT A": "(NOT (NOT A))",
            "A OR B OR C": "((A OR B) OR C)",
            "A AND B AND C": "((A AND B) AND C)",
            "X < 1 AND Y + 2 * 3 > 4 OR A": "(((X < 1) AND ((Y + (2 * 3)) > 4)) OR A)",
            "NOT (A OR B)": "(NOT (A OR B))",
            "NOT X MOD 2 = 0": "(NOT ((X MOD 2) = 0))",
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.shape(self.expr(text)), want)

    def test_operands_must_be_boolean(self):
        head = "DIM T AS BOOLEAN\nDIM X AS INTEGER\nDIM S$ AS STRING\n"
        cases = {
            "T = X AND T": "AND requires two BOOLEAN or two INTEGER operands, got INTEGER and BOOLEAN",
            "T = T OR 1": "OR requires two BOOLEAN or two INTEGER operands, got BOOLEAN and INTEGER",
            "T = NOT X": "cannot assign INTEGER to BOOLEAN",  # M7: NOT of an INTEGER is bitwise
            "T = NOT S$": "NOT requires a BOOLEAN or INTEGER operand, got STRING",
            "X = T AND T": "cannot assign BOOLEAN to INTEGER",
            "T = -T": "unary - requires INTEGER",
            'T = S$ AND "x"': "AND requires two BOOLEAN or two INTEGER operands, got STRING and STRING",
        }
        for stmt, fragment in cases.items():
            with self.subTest(stmt=stmt):
                self.assertIn(fragment, self.reject(f"{head}{stmt}\nEND\n").message)

    def test_logic_in_conditions(self):
        check_source("DIM A AS INTEGER\nDIM T AS BOOLEAN\n"
                     "IF A > 0 AND NOT T OR A = 5 THEN\nEND IF\n"
                     "WHILE NOT T AND A < 10\nA = A + 1\nT = A = 7 OR A > 8\nWEND\nEND\n")
        # M7: A AND 1 is a bitwise INTEGER, not a condition
        err = self.reject("DIM A AS INTEGER\nIF A AND 1 THEN\nEND IF\nEND\n")
        self.assertEqual((err.line, err.message), (2, "IF requires BOOLEAN condition, got INTEGER"))

    def test_infix_not_is_an_error(self):
        err = self.reject("DIM T AS BOOLEAN\nT = T NOT T\nEND\n")
        self.assertEqual(err.line, 2)

    def test_case_functions_type(self):
        check_source('DIM S$ AS STRING\nS$ = UCASE$(S$) + LCASE$("X" + S$)\nEND\n')
        for src, fragment in (
            ("DIM S$ AS STRING\nS$ = UCASE$(5)\nEND\n", "UCASE$ expects a STRING"),
            ('DIM S$ AS STRING\nS$ = LCASE$("a", "b")\nEND\n', "LCASE$ expects 1 arguments"),
            ('DIM X AS INTEGER\nX = UCASE$("a")\nEND\n', "cannot assign STRING to INTEGER"),
        ):
            with self.subTest(src=src):
                self.assertIn(fragment, self.reject(src).message)

    def test_case_functions_keep_length_bounds(self):
        # A 70-character literal never fits a 64-byte variable, cased or not.
        long = "a" * 70
        err = self.reject(f'DIM S$ AS STRING\nS$ = UCASE$("{long}")\nEND\n')
        self.assertIn("at least 70 characters", err.message)
        check_source('DIM S$ AS STRING\nS$ = UCASE$("' + "a" * 63 + '")\nEND\n')

    def test_call_targets(self):
        check_source("CALL Later\nSUB Later\nEND SUB\nEND\n")  # defined after use
        err = self.reject("DIM X AS INTEGER\nCALL Nothing\nEND\n")
        self.assertEqual((err.line, err.column, err.message),
                         (2, 1, "CALL NOTHING: no SUB NOTHING is defined"))
        err = self.reject("DIM X AS INTEGER\nCALL X\nEND\n")
        self.assertIn("no SUB X is defined", err.message)
        self.reject("CALL\nEND\n")
        check_source("SUB A\nEND SUB\nCALL A()\nEND\n")  # M7: an empty argument list
        self.reject('SUB A\nEND SUB\nCALL "A"\nEND\n')

    def test_recursion_is_rejected_with_the_cycle(self):
        err = self.reject("SUB A\n    CALL A\nEND SUB\nEND\n")
        self.assertEqual((err.line, err.column), (2, 5))
        self.assertIn("recursive CALL is not allowed: A -> A", err.message)
        err = self.reject("SUB A\nCALL B\nEND SUB\nSUB B\nCALL C\nEND SUB\nSUB C\nIF TRUE THEN\nCALL A\nEND IF\n"
                          "END SUB\nEND\n")
        self.assertEqual(err.line, 9)
        self.assertIn("A -> B -> C -> A", err.message)
        # a diamond is not recursion
        check_source("SUB A\nCALL B\nCALL C\nEND SUB\nSUB B\nCALL D\nEND SUB\nSUB C\nCALL D\nEND SUB\n"
                     "SUB D\nEND SUB\nCALL A\nCALL D\nEND\n")

    def test_call_depth_limit(self):
        self.assertEqual(MAX_CALL_DEPTH, 16)
        check_source(chain(16))
        err = self.reject(chain(17))
        self.assertIn("at most 16", err.message)
        self.assertEqual(err.line, 67)  # CALL L17 inside SUB L16: the 17th
        self.assertIn("from SUB L1", err.message)
        # the limit applies to SUBs nobody calls yet (they may be handlers)
        self.reject(chain(17, main_calls=False))
        # a very long chain is reported, not a Python RecursionError
        self.assertIn("at most 16", self.reject(chain(400)).message)

    def test_exit_sub(self):
        nodes = parse("SUB A\nEXIT SUB\nEND SUB\nEND\n")
        self.assertTrue(nodes[1].sub)
        self.assertFalse(parse("EXIT\nEND\n")[0].sub)
        err = self.reject("DIM X AS INTEGER\nEXIT SUB\nEND\n")
        self.assertEqual((err.line, err.message), (2, "EXIT SUB is only allowed inside a SUB"))
        self.reject("IF TRUE THEN\nEXIT SUB\nEND IF\nEND\n")
        check_source("SUB A\nWHILE TRUE\nIF TRUE THEN\nEXIT SUB\nEND IF\nWEND\nEND SUB\nEND\n")


# ------------------------------------------------------------- codegen
class M5cCodegenTests(unittest.TestCase):
    def test_case_section_only_when_used(self):
        self.assertIn("PB_CASE equ 0", gen("DIM T AS BOOLEAN\nT = NOT T AND T\nEND\n"))
        self.assertIn("PB_CASE equ 1", gen('DIM S$ AS STRING\nIF LCASE$(S$) = "a" THEN\nEND IF\nEND\n'))

    def test_call_exit_sub_and_exit(self):
        asm = gen("CALL DoIt\nSUB DoIt\nEXIT SUB\nEXIT\nEND SUB\nEND\n")
        self.assertRegex(asm, r"call sub_DOIT\b")
        body = asm.split("sub_DOIT:")[1]
        self.assertLess(body.index("    ret\n"), body.index("    jp rt_exit"))

    def test_no_os_calls_in_generated_code(self):
        asm = gen('DIM S$ AS STRING\nDIM T AS BOOLEAN\nT = NOT T OR UCASE$(S$) = "A" AND T\n'
                  "CALL P\nSUB P\nEXIT SUB\nEND SUB\nEND\n")
        self.assertNotRegex(asm, r"call\s+003Bh")


# ------------------------------------------------------------- behaviour
@requires_pasmo
class M5cBehaviourTests(unittest.TestCase):
    maxDiff = None

    def run_ok(self, src: str, **kw):
        run = guarded_run(src, **kw)
        self.assertEqual(run.violations, [], "memory-boundary violations")
        return run

    def bools(self, setup: str, exprs: list[str]) -> str:
        body = "".join(f"T = {e}\nIF T THEN\nR$ = R$ + \"1\"\nELSE\nR$ = R$ + \"0\"\nEND IF\n"
                       for e in exprs)
        run = self.run_ok("DIM T AS BOOLEAN\nDIM P AS BOOLEAN\nDIM Q AS BOOLEAN\nDIM A AS INTEGER\n"
                          f"DIM B AS INTEGER\nDIM S$ AS STRING\nDIM R$ AS STRING\n{setup}{body}MESSAGE R$\nEND\n")
        self.assertTrue(run.cpu.exited, run.alerts)
        return run.alerts[0]

    def test_truth_tables(self):
        want, exprs = "", []
        for p in (False, True):
            for q in (False, True):
                lp, lq = ("TRUE" if p else "FALSE"), ("TRUE" if q else "FALSE")
                exprs += [f"{lp} AND {lq}", f"{lp} OR {lq}", f"NOT {lp}"]
                want += f"{int(p and q)}{int(p or q)}{int(not p)}"
        self.assertEqual(self.bools("", exprs), want)
        # the same through variables and comparisons
        out = ""
        for p in (0, 1):
            for q in (0, 1):
                out += self.bools(f"A = {p}\nB = {q}\nP = A = 1\nQ = B = 1\n",
                                  ["P AND Q", "P OR Q", "NOT P", "NOT (P AND Q) = (NOT P OR NOT Q)",
                                   "A = 1 AND B = 1", "A = 1 OR B = 1"])
        want = ""
        for p in (False, True):
            for q in (False, True):
                want += "".join(str(int(v)) for v in (p and q, p or q, not p, True, p and q, p or q))
        self.assertEqual(out, want)

    def test_precedence_values(self):
        self.assertEqual(
            self.bools("A = 1\nB = 2\n", [
                "NOT A = B", "TRUE OR FALSE AND FALSE", "NOT TRUE OR TRUE", "NOT NOT TRUE",
                "FALSE AND TRUE OR TRUE AND NOT FALSE", "A < B AND B < A", "(TRUE OR FALSE) AND FALSE",
                "NOT (TRUE OR TRUE)",
            ]),
            "11111000",
        )

    def test_short_circuit_skips_the_right_operand(self):
        # each right operand would stop the program with a runtime error
        self.assertEqual(self.bools("A = 0\n", [
            "A <> 0 AND 10 / A > 1", "A = 0 OR 10 / A > 1", "FALSE AND VAL(\"99999\") = 1",
            "TRUE OR CHR$(A) = \"x\"", "LEN(S$) > 0 AND ASC(S$) = 65",
            "A <> 0 AND (A <> 0 AND 1 / A = 1)",
        ]), "010100")

    def test_right_operand_runs_when_needed(self):
        run = self.run_ok("DIM A AS INTEGER\nDIM T AS BOOLEAN\nA = 0\nT = A = 0 AND 10 / A > 1\nEND\n")
        self.assertEqual(run.alerts, [DIV_ERR.format(4)])
        run = self.run_ok("DIM A AS INTEGER\nDIM T AS BOOLEAN\nA = 0\nIF A <> 0 OR 10 / A > 1 THEN\n"
                          "END IF\nEND\n")
        self.assertEqual(run.alerts, [DIV_ERR.format(4)])

    def test_logic_with_strings_and_scratch(self):
        self.assertEqual(self.bools('S$ = "abc"\n', [
            'LEFT$(S$, 1) = "a" AND RIGHT$(S$ + "!", 2) = "c!"',
            'UCASE$(S$) = "ABC" OR S$ + S$ = ""',
            'NOT (MID$(S$, 2, 1) + "x" = "bx") OR LEN(S$ + S$) = 6',
        ]), "111")

    def test_loops_and_ifs_with_logic(self):
        run = self.run_ok("DIM I AS INTEGER\nDIM N AS INTEGER\nDIM Done AS BOOLEAN\n"
                          "WHILE NOT Done AND I < 100\nI = I + 1\n"
                          "IF I MOD 3 = 0 OR I MOD 5 = 0 THEN\nN = N + I\nEND IF\n"
                          "Done = I >= 20 AND NOT N < 50\nWEND\n"
                          "MESSAGE STR$(I) + \" \" + STR$(N)\nEND\n")
        n = i = 0
        done = False
        while not done and i < 100:
            i += 1
            if i % 3 == 0 or i % 5 == 0:
                n += i
            done = i >= 20 and not n < 50
        self.assertEqual(run.alerts, [f"{i} {n}"])

    def test_case_conversion_of_every_byte(self):
        run = self.run_ok("DIM N AS INTEGER\nDIM S$ AS STRING\nFOR N = 1 TO 255\n"
                          "S$ = UCASE$(CHR$(N)) + LCASE$(CHR$(N))\n"
                          "MESSAGE STR$(ASC(S$)) + \",\" + STR$(ASC(MID$(S$, 2, 1)))\nNEXT N\nEND\n")
        want = []
        for code in range(1, 256):
            up = code - 32 if 97 <= code <= 122 else code
            low = code + 32 if 65 <= code <= 90 else code
            want.append(f"{up},{low}")
        self.assertEqual(run.alerts, want)

    def test_case_conversion_in_expressions(self):
        run = self.run_ok('DIM S$ AS STRING\nDIM T$ AS STRING\nS$ = "Hello, World 16!"\n'
                          'MESSAGE UCASE$(S$)\nMESSAGE LCASE$(S$)\n'
                          'MESSAGE "[" + UCASE$(LEFT$(S$, 5) + "x") + "]" + LCASE$("ABC") + STR$(LEN(UCASE$(S$)))\n'
                          'MESSAGE UCASE$("")\n'
                          'T$ = "mixed"\nT$ = UCASE$(T$)\nMESSAGE T$\n'
                          'T$ = "<" + LCASE$(T$) + ">"\nMESSAGE T$\n'
                          'T$ = UCASE$(MID$(T$, 2, 1)) + LCASE$(T$)\nMESSAGE T$\n'
                          'IF UCASE$("yes") = "YES" AND LCASE$("NO") <> "NO" THEN\nMESSAGE "ok"\nEND IF\nEND\n')
        self.assertEqual(run.alerts, ["HELLO, WORLD 16!", "hello, world 16!", "[HELLOX]abc16", "",
                                      "MIXED", "<mixed>", "M<mixed>", "ok"])

    def test_case_conversion_overflow_is_reported(self):
        run = self.run_ok('DIM S$ AS STRING\nDIM T$ AS STRING\nS$ = "abcdef"\nT$ = UCASE$(S$)\nMESSAGE T$\n'
                          "T$ = UCASE$(S$ + S$)\nMESSAGE \"no\"\nEND\n", string_capacity=8)
        self.assertEqual(run.alerts, ["ABCDEF", LONG_ERR.format(6)])

    def test_call_runs_procedures_in_order_with_globals(self):
        run = self.run_ok(
            "DIM S$ AS STRING\nDIM I AS INTEGER\nS$ = \"m\"\nCALL A\nS$ = S$ + \"m\"\nCALL B\n"
            "FOR I = 1 TO 3\nCALL C\nNEXT I\nMESSAGE S$ + STR$(I)\n"
            "SUB A\nS$ = S$ + \"a\"\nCALL B\nS$ = S$ + \"a\"\nEND SUB\n"
            "SUB B\nS$ = S$ + \"b\"\nEND SUB\n"
            "SUB C\nDIM J AS INTEGER\nFOR J = 1 TO 2\nS$ = S$ + STR$(J)\nNEXT J\nEND SUB\nEND\n")
        self.assertEqual(run.alerts, ["mabamb1212123"])

    def test_exit_sub_returns_early_at_any_nesting(self):
        run = self.run_ok(
            "DIM S$ AS STRING\nDIM I AS INTEGER\nCALL A\nS$ = S$ + \"|\"\nCALL A\nMESSAGE S$ + STR$(I)\n"
            "SUB A\nS$ = S$ + \"<\"\nWHILE TRUE\nFOR I = 1 TO 10\nIF I = 3 AND LEN(S$) > 0 THEN\n"
            "S$ = S$ + \">\"\nEXIT SUB\nEND IF\nNEXT I\nWEND\nEND SUB\nEND\n")
        self.assertEqual(run.alerts, ["<>|<>3"])

    def test_exit_ends_the_program_from_any_depth(self):
        run = self.run_ok("CALL A\nMESSAGE \"no\"\nSUB A\nCALL B\nMESSAGE \"no A\"\nEND SUB\n"
                          "SUB B\nMESSAGE \"in B\"\nEXIT\nEND SUB\nEND\n")
        self.assertEqual(run.alerts, ["in B"])
        self.assertTrue(run.cpu.exited)

    def test_runtime_error_in_a_called_procedure_reports_its_line(self):
        run = self.run_ok("DIM A AS INTEGER\nCALL P\nSUB P\nA = 1 / A\nEND SUB\nEND\n")
        self.assertEqual(run.alerts, [DIV_ERR.format(4)])

    def test_deepest_chain_and_stack_use(self):
        """16 active procedures run; each level costs exactly 2 stack bytes.

        SP is sampled when the innermost SUB stores M (``M = D``), so the
        figure is the CALL chain alone: the main line's return address
        frame plus one return address per active procedure.
        """
        sps = {}
        for levels in (1, 2, 16):
            with tempfile.TemporaryDirectory() as tmp_name:
                tmp = Path(tmp_name)
                src, asm, prg = tmp / "t.pbas", tmp / "t.asm", tmp / "t.prg"
                src.write_text(chain(levels), encoding="utf-8")
                build(src, asm, prg)
                var_m = _symbols(asm, tmp)["var_m"]
                seen = []
                cpu = z80sim.run(prg, on_write=lambda c, addr, _v: seen.append(c.sp)
                                 if addr == var_m else None)
            self.assertEqual(cpu.alerts, [str(levels)])
            self.assertTrue(cpu.exited)
            sps[levels] = min(seen)
        self.assertEqual(sps[1], z80sim.STACK_TOP - 2)  # one return address
        self.assertEqual(sps[1] - sps[2], 2)
        self.assertEqual(sps[1] - sps[16], 2 * 15)
        self.assertEqual(z80sim.STACK_TOP - sps[16], 32)  # 16 levels, 32 bytes

    def test_handler_called_and_exit_sub_with_bindings(self):
        src = ('DIM Name$ AS STRING\nDIM Count AS INTEGER\nName$ = "a"\nWINDOW "W"\nTEXTBOX Name$, "N"\n'
               'BUTTON "Go", Go\nBUTTON "Twice", Twice\n'
               'SUB Go\nCount = Count + 1\nName$ = Name$ + "b"\nIF Count > 1 THEN\nEXIT SUB\nEND IF\n'
               'Name$ = UCASE$(Name$)\nEND SUB\n'
               'SUB Twice\nCALL Go\nCALL Go\nMESSAGE Name$ + STR$(Count)\nEND SUB\nEND\n')
        n = numbers(src)
        run = self.run_ok(src, events=[("click", n["Go"]), ("click", n["Twice"])])
        self.assertEqual(run.alerts, ["ABbb3"])
        self.assertEqual(run.cpu.control_text(n["NAME$"], shown=True), "ABbb")


@requires_pasmo
class M5cExampleTests(unittest.TestCase):
    def run_file(self, path: Path, **kw):
        run = guarded_run(path.read_text(encoding="utf-8"), **kw)
        self.assertEqual(run.violations, [])
        return run

    def test_signup_form(self):
        path = ROOT / "examples" / "signup_form.pbas"
        n = numbers(path.read_text(encoding="utf-8"))
        run = self.run_file(path, events=[
            ("click", n["Check"]), ("click", n["AGREE"]), ("click", n["Check"]),
            ("edit", n["NAME$"], ""), ("edit", n["AGE$"], "1000"), ("click", n["Check"]),
            ("edit", n["NAME$"], "9lives"), ("edit", n["AGE$"], "abc"), ("click", n["Check"]),
            ("edit", n["NAME$"], "bOB sMITH"), ("click", n["Tidy"]),
            # 99999 would stop VAL with a runtime error: the length test runs first
            ("edit", n["AGE$"], "99999"), ("click", n["Check"]),
            ("edit", n["AGE$"], "120"), ("click", n["Check"]), ("click", n["Quit"]),
        ])
        self.assertEqual(run.alerts, [
            "Please fix: Tick the box.", "Welcome, Ada!",
            "Please fix: Name is empty. Age: 1 to 3 digits.",
            "Please fix: Name: start with a letter. Age: 13 to 120.",
            "Please fix: Age: 1 to 3 digits.", "Welcome, Bob smith!",
        ])
        self.assertEqual(run.cpu.control_text(n["NAME$"], shown=True), "Bob smith")
        self.assertTrue(run.cpu.exited)

    def test_grade_report(self):
        run = self.run_file(ROOT / "examples" / "grade_report.pbas")
        self.assertEqual(run.alerts, ["Ada lovelace: A (top, no bonus needed)", "Charles babbage: B",
                                      "Grace: F (resit)", "2 of 3 passed"])
        self.assertTrue(run.cpu.exited)

    def test_xanne_edge_program(self):
        run = self.run_file(ROOT / "developer-tests" / "m5c_edges.pbas")
        self.assertEqual(run.alerts, [
            "1 TTTTTF", "2 FTF", "3 PCW16 ABC-XYZ/pcw16 abc-xyz 200", "4 AZaz 96 123 64 91",
            "5 16 16", "6 about to EXIT from 2 procedures deep",
        ])
        self.assertTrue(run.cpu.exited)


if __name__ == "__main__":
    unittest.main()
