"""M5a — general STRING expressions and assignment (LANGUAGE-SPEC.md §3/§4).

Concatenation anywhere a STRING is expected, substrings of computed strings,
INTEGER-expression positions and counts (checked at run time), and
assignment that stays correct when the destination is also read
(``S$ = "x" + S$``). Behaviour tests build with Pasmo and run on the project
simulator under the M2.1 memory checker; none of this is XAnne evidence.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import SourceError, check_source, generate
from pbas.policy import SCRATCH_STRING_MAX
from test_controls import numbers
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parent.parent
SUB_ERR = "Runtime error: substring position out of range at line {}"
LONG_ERR = "Runtime error: string too long at line {}"


def gen(src: str, capacity: int = 64) -> str:
    return generate(check_source(src, string_capacity=capacity))


def nested_left(depth: int) -> str:
    """LEFT$(LEFT$(...(A$ + "x")...), 1) — *depth* computed sources."""
    expr = 'A$ + "x"'
    for _ in range(depth):
        expr = f'LEFT$({expr} + "y", 1)'
    return expr


# ------------------------------------------------------------- frontend
class M5aSemanticsTests(unittest.TestCase):
    def reject(self, src: str, capacity: int = 64) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            check_source(src, string_capacity=capacity)
        return caught.exception

    def test_concatenation_is_a_string_expression_everywhere(self):
        check_source(
            'DIM A$ AS STRING\nDIM B$ AS STRING\nDIM N AS INTEGER\n'
            'A$ = B$ + "-" + STR$(N)\n'
            'IF A$ + B$ = "x" + B$ THEN\nN = LEN(A$ + B$)\nEND IF\n'
            'B$ = LEFT$(A$ + B$, 3)\nMESSAGE MID$(A$ + "!", 2, 1)\nEND\n'
        )

    def test_certain_overflow_of_a_concatenation_is_a_compile_error(self):
        err = self.reject('DIM S$ AS STRING\nS$ = "abcdef" + "ghij"\nEND\n', capacity=8)
        self.assertEqual((err.line, err.column), (2, 1))
        self.assertIn("at least 10 characters", err.message)

    def test_possible_overflow_is_left_to_run_time(self):
        check_source('DIM S$ AS STRING\nDIM T$ AS STRING\nS$ = S$ + T$\nEND\n', string_capacity=8)

    def test_constant_arguments_are_still_checked(self):
        self.assertIn("count must be at least 0",
                      self.reject('DIM T$ AS STRING\nMESSAGE RIGHT$(T$, -1)\nEND\n').message)
        self.assertIn("start position must be at least 1",
                      self.reject('DIM T$ AS STRING\nMESSAGE MID$(T$, 0, 1)\nEND\n').message)

    def test_computed_sources_and_operands_are_bounded(self):
        three = 'DIM A$ AS STRING\nDIM B$ AS STRING\nDIM C$ AS STRING\n'
        for stmt, context in (
            ('MESSAGE LEFT$(A$ + B$ + C$, 2)', 'LEFT$ source'),
            ('DIM N AS INTEGER\nN = LEN(A$ + B$ + C$)', 'LEN'),
        ):
            with self.subTest(stmt=stmt):
                err = self.reject(three + stmt + '\nEND\n')
                self.assertIn(f"limited to {SCRATCH_STRING_MAX}", err.message)
                self.assertIn(context, err.message)

    def test_message_budget_counts_text_only(self):
        # LEN / integer arguments add no text: this MESSAGE fits now (M5a).
        check_source(
            'DIM A$ AS STRING\nDIM B$ AS STRING\nDIM C$ AS STRING\n'
            'MESSAGE LEFT$(A$, LEN(B$)) + MID$(B$, LEN(C$), LEN(A$))\nEND\n'
        )


# ------------------------------------------------------------- code shape
class M5aCodegenTests(unittest.TestCase):
    def test_in_place_when_the_destination_is_only_read_first(self):
        asm = gen('DIM S$ AS STRING\nS$ = S$ + "!"\nEND\n')
        self.assertIn("ld hl,var_S_S+63\n    ld (rt_dst_end),hl\n    ld de,var_S_S", asm)
        self.assertNotIn("rt_cmp_buf1", asm)

    def test_through_scratch_when_a_later_part_reads_the_destination(self):
        for rhs in ('"x" + S$', 'S$ + S$', '"n" + STR$(LEN(S$))', '"a" + MID$("abc", LEN(S$), 1)'):
            with self.subTest(rhs=rhs):
                asm = gen(f'DIM S$ AS STRING\nS$ = {rhs}\nEND\n')
                self.assertIn("ld de,rt_cmp_buf1", asm)
                self.assertIn("ld hl,rt_cmp_buf1\n    ld bc,128\n    call rt_str_copy", asm)

    def test_other_variables_do_not_alias(self):
        asm = gen('DIM S$ AS STRING\nDIM S2$ AS STRING\nS$ = "x" + S2$\nEND\n')
        self.assertNotIn("rt_cmp_buf1", asm)

    def test_pool_sections_are_assembled_only_when_needed(self):
        self.assertIn("PB_STR_TEMPS equ 0", gen('DIM A$ AS STRING\nA$ = A$ + "x"\nEND\n'))
        self.assertIn("PB_STR_TEMPS equ 2",
                      gen(f'DIM A$ AS STRING\nDIM B$ AS STRING\nB$ = {nested_left(4)}\nEND\n'))

    def test_too_deep_nesting_is_a_positioned_compile_error(self):
        with self.assertRaises(SourceError) as caught:
            gen(f'DIM A$ AS STRING\nDIM B$ AS STRING\nIF {nested_left(6)} = "y" THEN\nEND IF\nEND\n')
        self.assertEqual(caught.exception.line, 3)
        self.assertIn("nested too deeply", caught.exception.message)

    def test_no_os_calls_in_generated_code(self):
        asm = gen('DIM A$ AS STRING\nDIM N AS INTEGER\nA$ = MID$(A$ + "x", N, N) + A$\nEND\n')
        self.assertNotRegex(asm, r"call\s+003Bh")


# ------------------------------------------------------------- behaviour
@requires_pasmo
class M5aBehaviourTests(unittest.TestCase):
    maxDiff = None

    def run_ok(self, src: str, capacity: int = 64, events=None):
        run = guarded_run(src, string_capacity=capacity, events=events)
        self.assertEqual(run.violations, [], "memory-boundary violations")
        return run

    def values(self, decls: str, setup: str, exprs: list[str], capacity: int = 64) -> list[str]:
        body = "".join(f"R$ = {e}\nMESSAGE \"[\" + R$ + \"]\"\n" for e in exprs)
        run = self.run_ok(f"DIM R$ AS STRING\n{decls}{setup}{body}END\n", capacity)
        self.assertTrue(run.cpu.exited, run.alerts)
        return [a[1:-1] for a in run.alerts]

    def test_expression_values(self):
        decls = "DIM A$ AS STRING\nDIM B$ AS STRING\nDIM E$ AS STRING\nDIM N AS INTEGER\nDIM M AS INTEGER\n"
        setup = 'A$ = "Hello"\nB$ = "World"\nN = 2\nM = 4\n'
        cases = {
            'A$ + ", " + B$': "Hello, World",
            'A$ + E$ + B$': "HelloWorld",
            'E$ + E$': "",
            'LEFT$(A$, N)': "He",
            'RIGHT$(A$, N + 1)': "llo",
            'MID$(A$, N, M - 1)': "ell",
            'LEFT$(A$ + B$, 7)': "HelloWo",
            'RIGHT$(A$ + B$, M + 4)': "lloWorld",
            'MID$(A$ + "-" + B$, 5, 3)': "o-W",
            'MID$(STR$(-12345), 2, 3)': "123",
            'LEFT$(STR$(N * 1000), LEN(A$) - 3)': "20",
            'LEFT$(A$, 0)': "",
            'LEFT$(A$, M * 100)': "Hello",
            'RIGHT$(A$, M - 4)': "",
            'RIGHT$(A$, 32767)': "Hello",
            'MID$(A$, M * 10, 3)': "",
            'MID$(A$, LEN(A$), 99)': "o",
            'MID$(E$, N, M)': "",
            'LEFT$(MID$(RIGHT$(A$ + B$, 8), 2, 6), 3)': "loW",
            'STR$(LEN(A$ + B$)) + "/" + STR$(LEN(E$ + E$))': "10/0",
        }
        got = self.values(decls, setup, list(cases))
        self.assertEqual(dict(zip(cases, got)), cases)

    def test_assignment_reading_its_own_destination(self):
        decls = "DIM S$ AS STRING\n"
        steps = [
            ('S$ = "abc"', "abc"),
            ('S$ = "<" + S$ + ">"', "<abc>"),
            ('S$ = S$ + S$', "<abc><abc>"),
            ('S$ = RIGHT$(S$, 4) + LEFT$(S$, 4)', "abc><abc"),
            ('S$ = MID$(S$, 2, LEN(S$) - 2) + "!"', "bc><ab!"),
            ('S$ = STR$(LEN(S$)) + ":" + S$', "7:bc><ab!"),
            ('S$ = LEFT$(S$, LEN(S$) - 1)', "7:bc><ab"),
            ('S$ = MID$(S$ + S$, 3, 4)', "bc><"),
        ]
        body = "".join(f"{stmt}\nMESSAGE S$\n" for stmt, _ in steps)
        run = self.run_ok(f"{decls}{body}END\n")
        self.assertEqual(run.alerts, [want for _, want in steps])

    def test_concatenation_in_comparisons(self):
        run = self.run_ok(
            'DIM A$ AS STRING\nDIM B$ AS STRING\nA$ = "ab"\nB$ = "cd"\n'
            'IF A$ + B$ = "abcd" THEN\nMESSAGE "1 yes"\nEND IF\n'
            'IF A$ + B$ <> B$ + A$ THEN\nMESSAGE "2 yes"\nEND IF\n'
            'IF LEFT$(B$ + A$, 3) = "cd" + LEFT$(A$, 1) THEN\nMESSAGE "3 yes"\nEND IF\n'
            'IF A$ + "" = A$ THEN\nMESSAGE "4 yes"\nEND IF\n'
            'END\n'
        )
        self.assertEqual(run.alerts, ["1 yes", "2 yes", "3 yes", "4 yes"])

    def test_deep_nesting_uses_the_pool_safely(self):
        run = self.run_ok(
            f'DIM A$ AS STRING\nDIM B$ AS STRING\nA$ = "Q"\nB$ = {nested_left(4)} + A$\n'
            f'IF {nested_left(4)} = "Q" THEN\nMESSAGE B$\nEND IF\nEND\n'
        )
        self.assertEqual(run.alerts, ["QQ"])

    def test_runtime_substring_errors(self):
        cases = [
            ("N = -1\nMESSAGE LEFT$(A$, N)", 5),
            ("N = -5\nMESSAGE RIGHT$(A$, N)", 5),
            ("N = 0\nMESSAGE MID$(A$, N, 1)", 5),
            ("N = -32768\nMESSAGE MID$(A$, 1, N)", 5),
            ("N = 1\nMESSAGE MID$(A$ + \"x\", N - 1, 2)", 5),
        ]
        for stmts, line in cases:
            with self.subTest(stmts=stmts):
                run = self.run_ok(f'DIM A$ AS STRING\nDIM N AS INTEGER\nA$ = "abc"\n{stmts}\nMESSAGE "not reached"\nEND\n')
                self.assertEqual(run.alerts, [SUB_ERR.format(line)])
                self.assertTrue(run.cpu.exited)

    def test_error_before_any_write_leaves_the_destination(self):
        run = self.run_ok('DIM S$ AS STRING\nDIM N AS INTEGER\nS$ = "keep"\nN = -1\n'
                          'S$ = "x" + LEFT$(S$, N)\nEND\n')
        self.assertEqual(run.alerts, [SUB_ERR.format(5)])
        self.assertEqual(string_var(run, "S$"), "keep")

    def test_overflow_is_the_reported_error_never_an_overrun(self):
        # capacity 8: 7 characters fit. As for any assignment (spec §4), the
        # characters that fitted may already be in the destination when the
        # error stops the program; R1-R3 prove nothing went outside it and
        # it stays NUL-terminated — through scratch (aliasing) or in place.
        run = self.run_ok('DIM S$ AS STRING\nS$ = "abcd"\nS$ = S$ + "-" + S$\nEND\n', capacity=8)
        self.assertEqual(run.alerts, [LONG_ERR.format(3)])
        self.assertTrue("abcd-abcd".startswith(string_var(run, "S$")))
        run = self.run_ok('DIM S$ AS STRING\nDIM T$ AS STRING\nT$ = "abcd"\nS$ = T$ + T$\nEND\n', capacity=8)
        self.assertEqual(run.alerts, [LONG_ERR.format(4)])
        run = self.run_ok('DIM S$ AS STRING\nS$ = "abcdefg"\nMESSAGE S$\nEND\n', capacity=8)
        self.assertEqual(run.alerts, ["abcdefg"])

    def test_capacity_extremes(self):
        run = self.run_ok('DIM S$ AS STRING\nDIM N AS INTEGER\nN = 1\nS$ = "z"\n'
                          'S$ = LEFT$(S$ + S$, N)\nMESSAGE S$\nEND\n', capacity=2)
        self.assertEqual(run.alerts, ["z"])
        run = self.run_ok('DIM S$ AS STRING\nDIM T$ AS STRING\nT$ = "' + "x" * 63 + '"\n'
                          'S$ = T$ + T$\nMESSAGE STR$(LEN(S$))\nS$ = S$ + "!"\nEND\n', capacity=127)
        self.assertEqual(run.alerts, ["126", LONG_ERR.format(6)])  # 126 is the most a capacity-127 STRING holds

    def test_bound_textbox_updated_by_a_concatenation(self):
        src = ('DIM Name$ AS STRING\nWINDOW "T"\nTEXTBOX Name$, "Name"\n'
               'BUTTON "Wrap", Wrap\nSUB Wrap\nName$ = "[" + Name$ + "]"\nEND SUB\nEND\n')
        n = numbers(src)
        run = self.run_ok(src, events=[("edit", n["NAME$"], "Ann"), ("click", n["Wrap"]),
                                       ("click", n["Wrap"])])
        self.assertEqual(run.cpu.control_text(n["NAME$"], shown=True), "[[Ann]]")

    def test_filesave_of_computed_substrings(self):
        disk = z80sim.Disk()
        run = guarded_run('DIM A$ AS STRING\nDIM N AS INTEGER\nA$ = "PcW16 BASIC"\nN = 6\n'
                          'FILESAVE "PBM5A.TXT", RIGHT$(A$, N - 1) + "/" + LEFT$(A$, N - 1)\n'
                          'FILELOAD "PBM5A.TXT", A$\nMESSAGE A$\nEND\n', disk=disk)
        self.assertEqual(run.violations, [])
        self.assertEqual(disk.file("PBM5A.TXT"), b"BASIC/PcW16")
        self.assertEqual(run.alerts[-1], "BASIC/PcW16")


@requires_pasmo
class M5aExampleTests(unittest.TestCase):
    """The M5a example programs, as described in examples/README.md."""

    def run_example(self, name, events=None):
        src = (ROOT / "examples" / f"{name}.pbas").read_text(encoding="utf-8")
        run = guarded_run(src, events=events)
        self.assertEqual(run.violations, [])
        return run, src

    def test_word_tools(self):
        run, _ = self.run_example("word_tools")
        self.assertEqual(run.alerts, [
            "Backwards: 61WcP dartsmA", "Letters a/A: 2",
            "Built from the front: 61WcP dartsmA", "[Amstrad PcW16] has 15 characters",
        ])

    def test_number_format(self):
        run, _ = self.run_example("number_format")
        self.assertEqual(run.alerts, [
            "Row 1:    111|", "Row 2:    444|", "Row 3:    999|", "Padded: 00042",
            "Bar: ########## (10)", "Fifth from the end: #",
        ])

    def test_xanne_edge_program(self):
        src = (ROOT / "developer-tests" / "m5a_edges.pbas").read_text(encoding="utf-8")
        run = guarded_run(src)
        self.assertEqual(run.violations, [])
        self.assertEqual(run.alerts, [
            "1 <abc>", "2 <abc><abc>", "3 abc><abc", "4 [][]", "5 []", "6 abc><abc 0",
            "7 about to fail: MID$ start 0", SUB_ERR.format(20),
        ])
        self.assertTrue(run.cpu.exited)

    def test_text_tool(self):
        src = (ROOT / "examples" / "text_tool.pbas").read_text(encoding="utf-8")
        n = numbers(src)
        run, _ = self.run_example("text_tool", [("click", n["Reverse"]), ("click", n["Reverse"]),
                                                ("click", n["Initials"]), ("click", n["Quit"])])
        self.assertEqual(run.alerts, ["Initials: PBc (3 words)"])
        self.assertEqual(run.cpu.control_text(n["TEXT$"], shown=True), "PBc = PcW16 BASIC compiler")
        self.assertTrue(run.cpu.exited)
        # 63 typed characters cannot grow by " = " plus initials: the
        # reported runtime error, never an overrun.
        run, _ = self.run_example("text_tool", [("edit", n["TEXT$"], "w " * 31 + "z"),
                                                ("click", n["Initials"])])
        self.assertEqual(run.alerts, ["Initials: wwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwz (32 words)",
                                      LONG_ERR.format(31)])


if __name__ == "__main__":
    unittest.main()
