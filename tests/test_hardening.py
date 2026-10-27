"""M2.1 hardening: regression tests for independent-review defects D1-D7.

Each defect has a minimal reproducer written against the M2.1 string policy
(LANGUAGE-SPEC.md section 4):

* overflow provable at compile time  -> positioned compile error;
* overflow only knowable at run time -> the program shows the alert
  "Runtime error: string too long at line N" and exits via os_app_exit;
* never silent truncation, never a write outside the destination.

Behavioural checks run on tests/z80sim.py under tests/memguard.py's write
observer (rules R1-R3). That is an engineering aid, never runtime/XAnne
evidence, and passing it shows only that these programs wrote nothing outside
their destinations on the CPU model.

All programs are independent clients written for this file; none is derived
from the shipped examples.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memguard import guarded_run, string_var
from pbas import SourceError, check_source, generate
from pbas.emit import mangle
from pbas.policy import MAX_EXPRESSION_DEPTH, MAX_BLOCK_DEPTH, SCRATCH_STRING_MAX
from pbas.prg import PRG_IMAGE_MAX, build
from toolchain import requires_files, requires_pasmo


def overflow_alert(line: int) -> str:
    return f"Runtime error: string too long at line {line}"


def compile_error(testcase, source: str, string_capacity: int = 64) -> SourceError:
    """Assert the full frontend+codegen rejects *source*; return the error."""
    with testcase.assertRaises(SourceError) as caught:
        generate(check_source(source, string_capacity=string_capacity))
    return caught.exception


@requires_pasmo
class GuardedTestCase(unittest.TestCase):
    maxDiff = None

    def run_clean(self, source: str, expected_alerts, string_capacity: int = 64):
        run = guarded_run(source, string_capacity=string_capacity)
        self.assertEqual(run.violations, [], "memory-boundary violations")
        self.assertTrue(run.cpu.exited, "program did not stop via os_app_exit")
        self.assertEqual(run.alerts, expected_alerts)
        return run


# ----------------------------------------------------------------------- D1
class D1StrDestinationCapacity(GuardedTestCase):
    """STR$ assignment must respect the destination capacity."""

    SOURCE = (
        "DIM A$ AS STRING\n"
        "DIM B$ AS STRING\n"
        'B$ = "XY"\n'
        "A$ = STR$({value})\n"
        'MESSAGE "A=" + A$ + " B=" + B$\n'
        "END\n"
    )

    def test_value_that_fits_is_assigned(self):
        run = self.run_clean(self.SOURCE.format(value=-12), ["A=-12 B=XY"], string_capacity=4)
        self.assertEqual(string_var(run, "B$"), "XY")

    def test_value_too_long_is_a_reported_runtime_error(self):
        # capacity 4 holds 3 characters; "-32768" needs 6.
        run = self.run_clean(self.SOURCE.format(value=-32768), [overflow_alert(4)], string_capacity=4)
        self.assertEqual(string_var(run, "B$"), "XY", "neighbour must be untouched")

    def test_exact_fit_at_capacity_seven(self):
        self.run_clean(self.SOURCE.format(value=-32768), ["A=-32768 B=XY"], string_capacity=7)

    def test_one_short_at_capacity_six(self):
        self.run_clean(self.SOURCE.format(value=-32768), [overflow_alert(4)], string_capacity=6)


# ----------------------------------------------------------------------- D2
class D2SubstringDestinationCapacity(GuardedTestCase):
    """Substring assignment is bounded by the destination, not the source."""

    LONG = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 4  # 104 characters

    def test_literal_source_overflow_is_a_compile_error(self):
        for call in (
            f'LEFT$("{self.LONG}", 100)',
            f'RIGHT$("{self.LONG}", 100)',
            f'MID$("{self.LONG}", 2, 100)',
        ):
            with self.subTest(call=call):
                err = compile_error(self, f"DIM T$ AS STRING\nT$ = {call}\nEND\n")
                self.assertEqual((err.line, err.column), (2, 1))
                self.assertIn("T$", err.message)
                self.assertIn("capacity 64", err.message)

    def test_literal_source_boundary(self):
        fits = "x" * 63
        self.run_clean(
            f'DIM T$ AS STRING\nT$ = LEFT$("{fits}Z", 63)\nMESSAGE T$\nEND\n', [fits]
        )
        compile_error(self, f'DIM T$ AS STRING\nT$ = LEFT$("{fits}Z", 64)\nEND\n')

    def test_mid_and_right_compute_exact_lengths(self):
        # MID$ starting near the end and RIGHT$ of a long literal yield short
        # strings: these must be accepted, not rejected on the source length.
        self.run_clean(
            "DIM T$ AS STRING\n"
            f'T$ = MID$("{self.LONG}", 101, 50)\n'
            "MESSAGE T$\n"
            f'T$ = RIGHT$("{self.LONG}", 3)\n'
            "MESSAGE T$\n"
            "END\n",
            ["WXYZ", "XYZ"],
            string_capacity=8,
        )

    def test_variable_source_never_overflows(self):
        run = self.run_clean(
            "DIM S$ AS STRING\nDIM T$ AS STRING\nDIM U$ AS STRING\n"
            'U$ = "guard"\n'
            'S$ = "abcdefghijklmno"\n'
            "T$ = LEFT$(S$, 200)\n"
            "MESSAGE T$\n"
            "T$ = MID$(S$, 3, 32767)\n"
            "MESSAGE T$\n"
            "T$ = RIGHT$(S$, 32767)\n"
            "MESSAGE T$ + U$\n"
            "END\n",
            ["abcdefghijklmno", "cdefghijklmno", "abcdefghijklmnoguard"],
            string_capacity=16,
        )
        self.assertEqual(string_var(run, "U$"), "guard")


# ----------------------------------------------------------------------- D3
class D3ComparisonOperands(GuardedTestCase):
    """String comparison never overflows its scratch buffers."""

    def test_long_identical_literals_compare_equal(self):
        lit = "Y" * 200
        self.run_clean(
            f'IF "{lit}" = "{lit}" THEN\nMESSAGE "equal"\nELSE\nMESSAGE "different"\nEND IF\nEND\n',
            ["equal"],
        )

    def test_variable_against_long_literal(self):
        self.run_clean(
            "DIM S$ AS STRING\n"
            'S$ = "abc"\n'
            f'IF S$ <> "{"Z" * 140}" THEN\nMESSAGE "different"\nEND IF\n'
            'IF S$ = "abc" THEN\nMESSAGE "same"\nEND IF\n'
            "END\n",
            ["different", "same"],
        )

    def test_computed_operand_within_scratch_limit(self):
        lit = "q" * SCRATCH_STRING_MAX
        self.run_clean(
            "DIM I AS INTEGER\n"
            "I = -7\n"
            f'IF LEFT$("{lit}x", {SCRATCH_STRING_MAX}) = "{lit}" THEN\nMESSAGE "ok"\nEND IF\n'
            'IF STR$(I) = "-7" THEN\nMESSAGE "str"\nEND IF\n'
            "END\n",
            ["ok", "str"],
        )

    def test_computed_operand_over_scratch_limit_is_a_compile_error(self):
        lit = "q" * 200
        err = compile_error(
            self,
            f'DIM S$ AS STRING\nIF LEFT$("{lit}", 150) = S$ THEN\nMESSAGE "x"\nEND IF\nEND\n',
        )
        self.assertEqual(err.line, 2)
        self.assertIn(str(SCRATCH_STRING_MAX), err.message)


# ----------------------------------------------------------------------- D4
class D4LenOfComputedString(GuardedTestCase):
    def test_len_of_long_slice_within_limit(self):
        self.run_clean(
            "DIM N AS INTEGER\n"
            f'N = LEN(MID$("{"Q" * 300}", 1, 100))\n'
            'MESSAGE "len " + STR$(N)\n'
            "END\n",
            ["len 100"],
        )

    def test_len_of_slice_over_scratch_limit_is_a_compile_error(self):
        err = compile_error(
            self, f'DIM N AS INTEGER\nN = LEN(MID$("{"Q" * 300}", 1, 300))\nEND\n'
        )
        self.assertEqual(err.line, 2)
        self.assertIn(str(SCRATCH_STRING_MAX), err.message)

    def test_len_inside_str_inside_message_keeps_message_destination(self):
        # LEN of a computed string uses scratch storage while a MESSAGE is
        # being built: the MESSAGE destination must survive the nesting.
        self.run_clean(
            "DIM S$ AS STRING\n"
            'S$ = "hello"\n'
            'MESSAGE "n=" + STR$(LEN(LEFT$(S$, 3))) + " " + S$\n'
            'IF STR$(LEN(STR$(-32768))) = "6" THEN\nMESSAGE "six"\nEND IF\n'
            "END\n",
            ["n=3 hello", "six"],
        )


# ----------------------------------------------------------------------- D5
class D5IdentifierEncoding(GuardedTestCase):
    TRICKY = ["A$", "A_STR", "A_S", "A__S", "A_", "A__", "A_S$", "A__STR$"]

    def test_mangle_is_injective_over_tricky_names(self):
        encoded = [mangle(name) for name in self.TRICKY]
        self.assertEqual(len(set(encoded)), len(encoded), dict(zip(self.TRICKY, encoded)))
        for symbol in encoded:
            self.assertRegex(symbol, r"^[A-Z0-9_]+$")

    def test_colliding_names_are_independent_variables(self):
        decls = "".join(
            f"DIM {n} AS {'STRING' if n.endswith('$') else 'INTEGER'}\n" for n in self.TRICKY
        )
        assigns = "".join(
            (f'{n} = "s{i}"\n' if n.endswith("$") else f"{n} = {i}\n")
            for i, n in enumerate(self.TRICKY)
        )
        report = " + ".join(
            (n if n.endswith("$") else f"STR$({n})") for n in self.TRICKY
        )
        self.run_clean(
            decls + assigns + f"MESSAGE {report}\nEND\n",
            ["s012345s6s7"],
            string_capacity=8,
        )


# ----------------------------------------------------------------------- D6
@requires_pasmo
class D6ImageLimit(unittest.TestCase):
    def test_limit_is_first_bank(self):
        # ROSAN283 'Memory Layout' / 'Addressing': only the #4000-#7FFF
        # quarter is known to hold the image; os_alert pointers carry that
        # quarter's block number.
        self.assertEqual(PRG_IMAGE_MAX, 0x4000)

    def test_oversized_image_is_rejected(self):
        lines = ["DIM N AS INTEGER"]
        lines += [f'MESSAGE "Message number {i} padded to make the image grow quickly"' for i in range(300)]
        lines.append("END")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "big.pbas"
            src.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(SourceError) as caught:
                build(src, Path(tmp) / "big.asm", Path(tmp) / "big.prg")
        self.assertIn("16384", caught.exception.message)


# ----------------------------------------------------------------------- D7
class D7ExpressionAndBlockDepth(unittest.TestCase):
    def test_deep_parentheses(self):
        src = "DIM X AS INTEGER\nX = " + "(" * 2000 + "1" + ")" * 2000 + "\nEND\n"
        err = compile_error(self, src)
        self.assertEqual(err.line, 2)
        self.assertIn(str(MAX_EXPRESSION_DEPTH), err.message)

    def test_long_operator_chain(self):
        src = "DIM X AS INTEGER\nX = " + " + ".join(["1"] * 5000) + "\nEND\n"
        err = compile_error(self, src)
        self.assertEqual(err.line, 2)
        self.assertIn(str(MAX_EXPRESSION_DEPTH), err.message)

    def test_deep_unary_and_calls(self):
        src = "DIM X AS INTEGER\nX = " + "-" * 3000 + "X\nEND\n"
        self.assertEqual(compile_error(self, src).line, 2)
        src = 'DIM X AS INTEGER\nX = ' + "LEN(STR$(" * 1500 + "1" + "))" * 1500 + "\nEND\n"
        self.assertEqual(compile_error(self, src).line, 2)

    def test_depth_at_limit_is_accepted(self):
        # A chain of MAX_EXPRESSION_DEPTH operands is a tree of that depth.
        src = "DIM X AS INTEGER\nX = " + " + ".join(["1"] * MAX_EXPRESSION_DEPTH) + "\nEND\n"
        generate(check_source(src))
        src = "DIM X AS INTEGER\nX = " + " + ".join(["1"] * (MAX_EXPRESSION_DEPTH + 1)) + "\nEND\n"
        compile_error(self, src)

    def test_deep_block_nesting(self):
        n = 1000
        src = "DIM X AS INTEGER\n" + "IF TRUE THEN\n" * n + "X = 1\n" + "END IF\n" * n + "END\n"
        err = compile_error(self, src)
        self.assertEqual(err.line, 2 + MAX_BLOCK_DEPTH)
        self.assertIn(str(MAX_BLOCK_DEPTH), err.message)

    def test_block_depth_at_limit_is_accepted(self):
        n = MAX_BLOCK_DEPTH
        src = "DIM X AS INTEGER\n" + "WHILE FALSE\n" * n + "X = 1\n" + "WEND\n" * n + "END\n"
        generate(check_source(src))


# ------------------------------------------------- capacity / operation matrix
class CapacityMatrix(GuardedTestCase):
    """Every string-writing operation at several capacities, under R1-R3."""

    CAPACITIES = (2, 3, 6, 7, 16, 64, 127)

    def program(self, cap: int) -> tuple[str, list[str]]:
        room = cap - 1
        fit = "abcdefghijklmnopqrstuvwxyz0123456789" * 4
        lit = fit[:room]
        lines = [
            "DIM S$ AS STRING",
            "DIM T$ AS STRING",
            "DIM G$ AS STRING",
            "DIM N AS INTEGER",
            'G$ = "#"',
            f'S$ = "{lit}"',
            "T$ = S$",
            "MESSAGE T$",
            f"T$ = LEFT$(S$, {cap + 5})",
            "MESSAGE T$",
            "T$ = MID$(S$, 2, 32767)",
            "MESSAGE T$",
            "T$ = RIGHT$(S$, 1)",
            "MESSAGE T$",
            "N = LEN(S$) + LEN(LEFT$(S$, 2))",
            "MESSAGE STR$(N)",
            'IF S$ = T$ THEN\nMESSAGE "eq"\nELSE\nMESSAGE "ne"\nEND IF',
            "S$ = STR$(7)",
            "MESSAGE S$",
            "MESSAGE G$",
        ]
        expected = [lit, lit, lit[1:], lit[-1:], str(len(lit) + min(2, len(lit)))]
        expected.append("eq" if lit == lit[-1:] else "ne")
        expected += ["7", "#"]
        return "\n".join(lines) + "\nEND\n", expected

    def test_matrix(self):
        for cap in self.CAPACITIES:
            with self.subTest(capacity=cap):
                source, expected = self.program(cap)
                run = self.run_clean(source, expected, string_capacity=cap)
                self.assertEqual(string_var(run, "G$"), "#")

    def test_str_overflow_reported_at_every_small_capacity(self):
        for cap in range(2, 7):
            with self.subTest(capacity=cap):
                self.run_clean(
                    "DIM S$ AS STRING\nDIM G$ AS STRING\n"
                    'G$ = "#"\n'
                    "S$ = STR$(-32768)\n"
                    'MESSAGE "unreachable"\nEND\n',
                    [overflow_alert(4)],
                    string_capacity=cap,
                )


if __name__ == "__main__":
    unittest.main()


# ------------------------------------------- the seven M2 acceptance programs
class AcceptanceProgramsUnderMemguard(GuardedTestCase):
    """The seven owner-validated M2 programs, rebuilt by the M2.1 compiler,
    must produce exactly the alert text recorded in RUNTIME-RESULTS.md and
    write nothing outside allocated storage (rules R1-R3)."""

    ROOT = Path(__file__).resolve().parent.parent
    EXPECTED = {
        "examples/hello_pcw.pbas": ["Hello from PcW16 BASIC", "Built on the PcW16", "Dice roll: 4"],
        "examples/arith_demo.pbas": [
            "-21 < 9: yes", "9 <= 30: yes", "30 > 9: yes",
            "9 >= -9: yes", "21 = 21: yes", "270 <> 30: yes",
        ],
        "examples/branch_menu.pbas": ["Tier: SILVER (77)"],
        "examples/for_walk.pbas": ["Up: 30", "Down: 15", "Empty: 99"],
        "examples/while_wait.pbas": ["Doubled to 64 in 6 rises", "Shrunk to 1"],
        "examples/mixed_work.pbas": [
            "Leg 1 patch RAC at 7 mi", "Leg 2 patch RAC at 21 mi",
            "Leg 3 patch RAC at 42 mi", "Head TRA tail ING len 8",
        ],
    }
    # M14: the prototype's program is in the private repository only (tests its own way below)
    PROTOTYPE = {"../POC/examples/logic_native.pbas": ["Count is above ten"]}

    def test_acceptance_programs(self):
        for rel, alerts in self.EXPECTED.items():
            with self.subTest(program=rel):
                source = (self.ROOT / rel).read_text(encoding="utf-8")
                run = self.run_clean(source, alerts)
                self.assertEqual(run.cpu.sp, 0x3FFE, "stack must be balanced at exit")

    @requires_files(Path(__file__).resolve().parents[2] / "POC" / "examples" / "logic_native.pbas",
                    what="the prototype's example programs")
    def test_prototype_acceptance_program(self):
        for rel, alerts in self.PROTOTYPE.items():
            with self.subTest(program=rel):
                source = (self.ROOT / rel).read_text(encoding="utf-8")
                run = self.run_clean(source, alerts)
                self.assertEqual(run.cpu.sp, 0x3FFE, "stack must be balanced at exit")


# ------------------------------------------------- M2.1 owner XAnne programs
class OwnerRegressionPrograms(GuardedTestCase):
    """The new programs of the M2.1 XAnne procedure (RUNTIME-RESULTS.md,
    scripts R2/R3) produce exactly the alerts the owner is told to expect,
    within the memory rules. Neither reproduces a memory-corruption defect."""

    XANNE = Path(__file__).resolve().parent.parent / "developer-tests"

    def test_r2_overflow_report(self):
        source = (self.XANNE / "overflow_report.pbas").read_text(encoding="utf-8")
        self.run_clean(
            source,
            ["Step 1: overflow check starts", overflow_alert(7)],
            string_capacity=4,
        )

    def test_r3_large_image(self):
        source = (self.XANNE / "large_image.pbas").read_text(encoding="utf-8")
        run = self.run_clean(
            source,
            [
                "Step 1: large image loaded",
                "Step 2: alert text read near the top of the bank, 16K",
            ],
        )
        image_end = 0x4000 + 16384
        self.assertGreater(run.symbols["rt_alert_buf"], image_end - 0x400)
