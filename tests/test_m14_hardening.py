"""M14 hardening: one regression test for each corrected defect (M14-DEFECT-REGISTER.md).

The defect numbers (D1, D2, ...) are those of the register. Each test fails on
the M13-End compiler and passes now; tests/m14_mutants.json reverts each fix
and checks that a test here catches it.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pasmo_corpus
from pbas import check_source
from pbas.errors import SourceError
from pbas.lint import warnings
from pbas.prg import build
from pbas.statements import generate_parts
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import rtdeps  # noqa: E402


def check(src: str):
    """Everything `pcw16basic check` runs: the front end, layout and code generation."""
    program = check_source(src)
    generate_parts(program, None)
    return program


class AssemblerFailures(unittest.TestCase):
    """D1, D2, D14: BASIC the front end accepts must never stop Pasmo."""

    def test_runtime_dependencies_are_closed(self):
        self.assertEqual(list(rtdeps.findings()), [])

    def test_the_dependency_check_sees_a_missing_switch(self):
        # the D1 fault put back in a copy: rt_err_msg without PB_KEYDOWN
        text = rtdeps.RUNTIME.read_text(encoding="utf-8")
        self.assertIn(" + PB_KEYDOWN", text)
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "runtime.z80.asm"
            copy.write_text(text.replace(" + PB_KEYDOWN", ""), encoding="utf-8")
            saved, rtdeps.RUNTIME = rtdeps.RUNTIME, copy
            try:
                found = list(rtdeps.findings())
            finally:
                rtdeps.RUNTIME = saved
        self.assertEqual([f[0] for f in found], ["rt_err_msg"])

    @requires_pasmo
    def test_no_accepted_program_fails_in_pasmo(self):
        def one(item):
            name, src = item
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                shutil.copytree(ROOT / "examples" / "lib", tmp / "lib")
                path = tmp / "p.pbas"
                path.write_text(src, encoding="utf-8")
                try:
                    check_source(src, path=path)
                except SourceError:
                    return None  # refused by the front end: a positioned error is right
                for opts in ({}, {"runtime_sections": "all"}):
                    try:
                        build(path, tmp / "p.asm", tmp / "p.prg", **opts)
                        return None
                    except SourceError as exc:
                        if "pasmo failed" in str(exc):
                            return f"{name}: {exc}"
                        if "resident part" in str(exc) and not opts:
                            continue
                        return None
            return None

        with ThreadPoolExecutor(8) as pool:
            failures = [r for r in pool.map(one, list(pasmo_corpus.programs())) if r]
        self.assertEqual(failures, [])

    @requires_pasmo
    def test_the_three_reported_cases_build(self):
        cases = {
            "D1 KEYDOWN, no canvas": "DIM B AS BOOLEAN\nB = KEYDOWN(41)\nEND\n",
            "D2 BITMAP parameter, no BITMAP": dict(pasmo_corpus.WHOLE)["bmpparam"],
            "D14 PAGEWIDTH, no PAGE": "DIM I AS INTEGER\nI = PAGEWIDTH(\"abc\")\nEND\n",
        }
        for what, src in cases.items():
            with self.subTest(what), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "p.pbas"
                path.write_text(src, encoding="utf-8")
                build(path, Path(tmp) / "p.asm", Path(tmp) / "p.prg")


class CheckMatchesBuild(unittest.TestCase):
    """D3: what build refuses for a reason in the program, check refuses too."""

    CASES = {
        "no button": ('WINDOW "W"\nLABEL "x"\nEND\n', "a WINDOW needs at least one BUTTON"),
        "seven buttons": ('WINDOW "W"\n' + "".join(f'BUTTON "{i}", A\n' for i in range(7))
                          + "SUB A\nEND SUB\nEND\n", "at most 6 BUTTONs"),
        "canvas too wide": ('WINDOW "W"\nCANVAS 400, 50\nBUTTON "Q", A\nSUB A\nEND SUB\nEND\n',
                            "at most 330 pixels wide"),
        "textbox too long": ('DIM S AS STRING * 100\nWINDOW "W"\nTEXTBOX S, "x"\nBUTTON "Q", A\n'
                             'SUB A\nEND SUB\nEND\n', "a TEXTBOX holds at most 63 characters"),
        "dialog overflow": ('WINDOW "W"\n' + "".join(f'LABEL "l{i}"\n' for i in range(5))
                            + 'BUTTON "Q", A\nSUB A\nEND SUB\nEND\n', "no room for this LABEL"),
    }

    def test_check_refuses_what_build_refused(self):
        for what, (src, words) in self.CASES.items():
            with self.subTest(what):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "p.pbas"
                    path.write_text(src, encoding="utf-8")
                    r = subprocess.run([sys.executable, "-m", "pbas", "check", str(path)], cwd=ROOT,
                                       capture_output=True, text=True)
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn(words, r.stderr)

    def test_check_prints_build_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.pbas"
            path.write_text("SUB P\n    DIM N AS INTEGER\nEND SUB\nCALL P\nEND\n", encoding="utf-8")
            r = subprocess.run([sys.executable, "-m", "pbas", "check", str(path)], cwd=ROOT,
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("warning: DIM N inside P declares a variable for the whole program", r.stderr)


class Names(unittest.TestCase):
    """D5, D10: names and the built-in functions."""

    def refused(self, src: str) -> str:
        with self.assertRaises(SourceError) as caught:
            check(src)
        return caught.exception.message

    def test_a_function_cannot_take_a_builtins_name(self):
        for name in ("Min", "LEN", "abs", "Pi", "Seconds", "Str$"):
            with self.subTest(name):
                typ = "STRING" if name.endswith("$") else "INTEGER"
                ret = '""' if name.endswith("$") else "0"
                msg = self.refused(f"FUNCTION {name}() AS {typ}\n    RETURN {ret}\nEND FUNCTION\nEND\n")
                self.assertIn(f"{name.upper()} is a built-in function, so a FUNCTION cannot have that name", msg)

    def test_a_const_cannot_hide_a_builtin(self):
        self.assertIn("a CONST cannot have that name", self.refused("CONST PI = 3\nEND\n"))

    def test_names_that_stay_usable(self):
        # accepted programs use these (STOPWATCH's Seconds, lib/chart's Max, PAINT's SUB Show)
        check("DIM Seconds AS INTEGER\nSeconds = 3\nEND\n")
        check("SUB P(Max AS INTEGER)\n    MESSAGE STR$(MAX(1, Max))\nEND SUB\nCALL P(4)\nEND\n")
        check("SUB Show\nEND SUB\nCALL Show\nEND\n")
        check("CONST Min = 2\nDIM I AS INTEGER\nI = MIN(5, Min)\nEND\n")

    def test_a_hidden_builtin_is_reported(self):
        found = warnings(check("DIM Seconds AS INTEGER\nSeconds = 3\nEND\n"))
        self.assertEqual(len(found), 1)
        self.assertIn("SECONDS is also a built-in function", found[0][2])
        self.assertEqual(warnings(check("DIM Max AS INTEGER\nMax = 3\nEND\n")), [])

    def test_a_sub_named_show_gets_a_hint(self):
        msg = self.refused("DIM N AS INTEGER\nSUB Show(K AS INTEGER)\nEND SUB\nShow N\nEND\n")
        self.assertIn("to call the SUB SHOW, write CALL Show", msg)


class SpecifiedErrors(unittest.TestCase):
    """D4, D7, D8, D11, D12, D15: the specification's errors, and messages that help."""

    def refused(self, src: str) -> str:
        with self.assertRaises(SourceError) as caught:
            check(src)
        return caught.exception.message

    def test_four_constructs_the_specification_forbids(self):
        cases = {
            "DIM T AS TEXT * 10\nDIM U AS TEXT * 10\nT = U\nEND\n": "is a TEXT buffer and cannot be assigned",
            "DIM B AS BITMAP * 8, 8\nDIM C AS BITMAP * 8, 8\nB = C\nEND\n": "is a BITMAP and cannot be assigned",
            ("DIM B AS BITMAP * 8, 8\nSUB P(X AS BITMAP, Y AS BITMAP)\n    X = Y\nEND SUB\n"
             "CALL P(B, B)\nEND\n"): "is a BITMAP parameter and cannot be assigned",
            ("DIM I AS INTEGER\nSELECT CASE I\nI = 2\nCASE 1\nI = 3\nEND SELECT\nEND\n"):
                "a statement between SELECT CASE (line 2) and its first CASE",
        }
        for src, words in cases.items():
            with self.subTest(words):
                self.assertIn(words, self.refused(src))

    def test_what_stays_valid(self):
        check("DIM B AS BITMAP * 8, 8\nSUB P(X AS BITMAP)\n    MESSAGE \"x\"\nEND SUB\nCALL P(B)\nEND\n")
        check("DIM I AS INTEGER\nSELECT CASE I\n' a comment\nCASE 1\nI = 3\nEND SELECT\nEND\n")

    def test_a_function_used_without_parentheses(self):
        msg = self.refused("FUNCTION Ready AS BOOLEAN\n    RETURN TRUE\nEND FUNCTION\nDIM B AS BOOLEAN\n"
                           "B = Ready\nEND\n")
        self.assertIn("READY is a FUNCTION: call it as READY()", msg)

    def test_a_literal_index_outside_the_array(self):
        for index in ("0", "6", "-1"):
            with self.subTest(index):
                msg = self.refused(f"DIM A(5) AS INTEGER\nA({index}) = 1\nEND\n")
                self.assertIn(f"A({index}) is outside the array", msg)
        check("DIM A(5) AS INTEGER\nDIM I AS INTEGER\nA(1) = 1\nA(5) = 5\nI = 9\nA(I) = 2\nEND\n")

    def test_sizes_must_be_literals(self):
        msg = self.refused("CONST N = 5\nDIM A(N) AS INTEGER\nEND\n")
        self.assertIn("a CONST or a variable cannot be used here", msg)

    def test_line_input_into_a_field(self):
        # D15 (adversarial review): the message names the rule, not the next token
        msg = self.refused('TYPE T\n    N AS STRING * 10\nEND TYPE\nDIM X AS T\nOPEN "A.TXT" FOR INPUT AS #1\n'
                           'LINE INPUT #1, X.N\nCLOSE #1\nEND\n')
        self.assertIn("not a record field: read the line into a STRING", msg)
        check('DIM S$ AS STRING\nOPEN "A.TXT" FOR INPUT AS #1\nLINE INPUT #1, S$\nCLOSE #1\nEND\n')

    def test_a_byte_order_mark_is_ignored(self):
        # D16 (adversarial review): editors that save "UTF-8 with BOM" made every program fail
        check('\ufeffMESSAGE "x"\nEND\n')
        self.assertIn("unexpected character", self.refused('MESSAGE "x"\n\ufeffEND\n'))

    def test_messages_name_the_cure(self):
        self.assertIn("convert with CINT", self.refused("DIM R AS REAL\nDIM N AS INTEGER\nN = R\nEND\n"))
        self.assertIn("PRINT to the screen does not exist", self.refused('PRINT "x"\nEND\n'))
        msg = self.refused("DIM I AS INTEGER\nI = IOERR\nEND\n")
        self.assertIn("TEXT LOAD or SAVE, DB, BITMAP LOAD or SAVE, PAGE", msg)


class Tools(unittest.TestCase):
    """T1-T7: the command line and the tools."""

    def run_(self, *args, cwd=ROOT):
        return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True)

    def test_subcommand_help_reaches_the_tool(self):
        for cmd, words in (("check", "usage: pbas check"), ("build", "usage: build.py"),
                           ("image", "usage: pbimage.py"), ("memory", "usage: memreport.py")):
            with self.subTest(cmd):
                r = self.run_(str(ROOT / "pcw16basic"), cmd, "--help")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn(words, r.stdout)

    def test_new_names_only_public_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kind in ("app", "game"):
                r = self.run_(str(ROOT / "pcw16basic"), "new", f"p{kind}", "--kind", kind, cwd=tmp)
                self.assertEqual(r.returncode, 0, r.stderr)
                text = r.stdout + (Path(tmp) / f"p{kind}" / f"p{kind}.pbas").read_text(encoding="utf-8")
                text += (Path(tmp) / f"p{kind}" / "assets" / "ASSETS.txt").read_text(encoding="utf-8")
                self.assertNotRegex(text, r"docs/M\d")
                self.assertRegex(text, r"docs/(libraries|manual|graphics-assets)")

    def test_libref_help_changes_nothing(self):
        out = ROOT / "docs" / "LIBRARY-REFERENCE.md"
        before = out.read_bytes() if out.exists() else None
        r = self.run_(str(ROOT / "tools" / "libref.py"), "--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--check", r.stdout)
        self.assertEqual(out.read_bytes() if out.exists() else None, before)

    def test_pbimage_reports_a_missing_file_in_one_line(self):
        r = self.run_(str(ROOT / "tools" / "pbimage.py"), "info", "/no/such/picture.png")
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("No such file or directory", r.stderr)

    def test_pbicheck_has_no_unused_argument(self):
        r = self.run_(str(ROOT / "tools" / "pbicheck.py"), "a.pbi", "b")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unrecognized arguments: b", r.stderr)

    def test_memory_report_on_programs_that_do_not_build(self):
        # T8 (M14 evaluation): a single image over 16K (no SUB or FUNCTION) and a program
        # that does not compile each gave a Python traceback
        with tempfile.TemporaryDirectory() as tmp:
            big, bad = Path(tmp) / "big.pbas", Path(tmp) / "bad.pbas"
            big.write_text('DIM A(200) AS STRING * 60\nDIM B(200) AS STRING * 60\nA(1) = "x"\nEND\n')
            bad.write_text("DIM A(9000) AS INTEGER\nEND\n")
            tool = [sys.executable, str(ROOT / "tools" / "memreport.py")]
            out = subprocess.run(tool + [str(big)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("bytes over the 16384-byte limit: it does not build", out.stdout)
            self.assertIn("arrays", out.stdout)
            out = subprocess.run(tool + [str(bad)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 1)
            self.assertNotIn("Traceback", out.stderr)
            self.assertIn("bad.pbas:1:1: an array has 1 to 250 elements", out.stderr)

    def test_an_install_without_the_folder_says_so(self):
        import pbas.cli as cli
        with tempfile.TemporaryDirectory() as tmp:
            saved, cli.ROOT = cli.ROOT, Path(tmp)
            try:
                import contextlib
                import io
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    code = cli.main(["doctor"])
            finally:
                cli.ROOT = saved
        self.assertEqual(code, 2)
        self.assertIn("pip install -e .", err.getvalue())


if __name__ == "__main__":
    unittest.main()
