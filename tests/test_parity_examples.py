"""Parity harness (R-EX): every POC example must pass the production frontend.

The POC examples in ``POC/examples/`` are the behavioural parity baseline
(MIGRATION-PLAN section 5): every one of them except ``hello.pbas`` must
pass the Stage-1 frontend, ``logic.pbas`` is now fully valid under the
unified execution model (main-line statements plus a dialog), and
``hello.pbas`` must fail with the Stage-1 ``PRINT`` error. The harness also
pins the two documented POC frontend bugs as fixed end-to-end: a whole-line
``REM`` comment and a lone numbered (blank) line both parse.

The examples directory is read-only; these tests never write there.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pbas.ast_nodes import Fileload, Filesave
from pbas.errors import SourceError
from pbas.lexer import tokenize
from pbas.parser import Parser
from pbas.policy import DEFAULT_STRING_CAPACITY
from pbas.program import build_program
from pbas.semantics import analyze

try:  # Prefer the package-level helper when the orchestrator publishes it.
    from pbas import check_source as _package_check_source
except ImportError:
    _package_check_source = None

from toolchain import requires_files  # noqa: E402  (M14)

EXAMPLES = Path(__file__).resolve().parents[2] / "POC" / "examples"

EXPECTED_EXAMPLES = {
    "buttons_native.pbas",
    "hello.pbas",
    "hello_name.pbas",
    "logic.pbas",
    "logic_native.pbas",
    "loop_lab.pbas",
    "loop_lab_46.pbas",
    "note_saver.pbas",
    "notes_v051.pbas",
    "state_native.pbas",
    "text_analyser.pbas",
    "text_toolkit.pbas",
    "window.pbas",
}


def check_source(text: str, *, string_capacity: int = DEFAULT_STRING_CAPACITY):
    """Compile one source text through the whole M1 frontend; return Program."""
    if _package_check_source is not None:
        return _package_check_source(text, string_capacity=string_capacity)
    tokens = tokenize(text)
    nodes = Parser(tokens).parse()
    analysis = analyze(nodes, string_capacity=string_capacity)
    return build_program(nodes, analysis)


def _walk(statements):
    """Yield every statement in a body, recursing into nested blocks."""
    for node in statements:
        yield node
        then_body = getattr(node, "then_body", None)
        if then_body is not None:
            yield from _walk(then_body)
            yield from _walk(node.else_body)
        else:
            body = getattr(node, "body", None)
            if body is not None:
                yield from _walk(body)


def _read(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


@requires_files(EXAMPLES, what="the prototype's example programs")  # M14: parity is a private check
class TestExamplesPresent(unittest.TestCase):
    def test_all_thirteen_examples_present(self):
        found = {path.name for path in EXAMPLES.glob("*.pbas")}
        self.assertEqual(found, EXPECTED_EXAMPLES)


@requires_files(EXAMPLES, what="the prototype's example programs")  # M14
class TestParity(unittest.TestCase):
    def test_every_example_except_hello_checks(self):
        for name in sorted(EXPECTED_EXAMPLES - {"hello.pbas"}):
            with self.subTest(example=name):
                program = check_source(_read(name))
                self.assertIsNotNone(program)

    def test_hello_rejected_with_print_error(self):
        with self.assertRaises(SourceError) as caught:
            check_source(_read("hello.pbas"))
        self.assertIn("PRINT", str(caught.exception))

    def test_logic_main_line_and_window(self):
        program = check_source(_read("logic.pbas"))
        # The source literal is "Counter"; a WINDOW title is display text and
        # is preserved verbatim (POC parity: only identifiers and file names
        # are case-normalised, never string content).
        self.assertEqual(program.dialog_title, "Counter")
        self.assertTrue(program.main)

    def test_notes_v051_binding_and_file_ops(self):
        program = check_source(_read("notes_v051.pbas"))
        self.assertEqual(len(program.bindings), 1)
        binding = program.bindings[0]
        self.assertEqual(binding.widget, "TEXTBOX")
        self.assertEqual(binding.var_name, "NOTE$")
        file_ops = {}
        for proc in program.procedures:
            for node in _walk(proc.body):
                if isinstance(node, (Filesave, Fileload)):
                    file_ops[proc.name] = type(node).__name__
        self.assertEqual(
            file_ops, {"LOADNOTE": "Fileload", "SAVENOTE": "Filesave"}
        )

    def test_text_toolkit_handlers_map_to_subs(self):
        program = check_source(_read("text_toolkit.pbas"))
        self.assertEqual(
            [handler.sub for handler in program.handlers],
            ["FIRSTFIVE", "LASTFIVE", "MIDDLETEXT"],
        )
        for handler in program.handlers:
            widget = program.widgets[handler.button_index]
            self.assertEqual(widget.kind, "BUTTON")
            self.assertEqual(widget.handler, handler.sub)
        self.assertEqual(
            {proc.name for proc in program.procedures},
            {"FIRSTFIVE", "LASTFIVE", "MIDDLETEXT"},
        )

    def test_poc_frontend_bugs_fixed_end_to_end(self):
        source = (
            "REM full-line comment\n"
            "10\n"
            "20 DIM Total AS INTEGER\n"
            "30 Total = 1 REM trailing comment\n"
            "40 END\n"
        )
        nodes = Parser(tokenize(source)).parse()
        # REM lines and the lone numbered blank line emit no statements.
        self.assertEqual(len(nodes), 3)
        program = check_source(source)
        self.assertTrue(program.main)


# M14: the command's own tests use small fixtures of their own (tests/fixtures/cli),
# not the prototype's programs, so they run in the public repository too
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cli"


class TestCli(unittest.TestCase):
    def run_cli(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "pbas", *argv],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def test_ok_line(self):
        source = FIXTURES / "count.pbas"
        result = self.run_cli("check", str(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            f"OK: {source} (8 statements, 1 variables); "
            "syntax, type, layout and code checks passed. No PRG generated: "  # M14 (D3)
            "whether it fits the PcW16's memory is checked by build.",
        )

    def test_hello_print_error_on_stderr_exit_1(self):
        result = self.run_cli("check", str(FIXTURES / "print.pbas"))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("PRINT", result.stderr)

    def test_missing_source_is_an_error(self):
        source = FIXTURES / "does_not_exist.pbas"
        result = self.run_cli("check", str(source))
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(source), result.stderr)

    def test_ast_flag_prints_flat_ast_json(self):
        result = self.run_cli(
            "check", "--ast", str(FIXTURES / "count.pbas")
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data[0]["name"], "COUNT")
        self.assertEqual(data[0]["type_name"], "INTEGER")

    def test_symbols_flag_prints_variable_table_json(self):
        result = self.run_cli(
            "check", "--symbols", str(FIXTURES / "count.pbas")
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        table = json.loads(result.stdout)
        self.assertEqual(set(table), {"COUNT"})
        self.assertEqual(table["COUNT"]["type"], "INTEGER")
        self.assertIsNone(table["COUNT"]["capacity"])

    def test_string_capacity_flows_to_variable_table(self):
        result = self.run_cli(
            "check",
            "--symbols",
            "--string-capacity",
            "32",
            str(FIXTURES / "note.pbas"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        table = json.loads(result.stdout)
        self.assertEqual(table["NOTE$"]["capacity"], 32)

    def test_string_capacity_out_of_range_rejected(self):
        result = self.run_cli(
            "check", "--string-capacity", "1", str(FIXTURES / "count.pbas")
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("string capacity", result.stderr)

    def test_string_capacity_not_an_integer_rejected(self):
        result = self.run_cli(
            "check",
            "--string-capacity",
            "abc",
            str(FIXTURES / "count.pbas"),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("string capacity", result.stderr)


if __name__ == "__main__":
    unittest.main()
