"""M11 regressions found while writing the M11 examples.

KI-64: a program whose only string function was TRIM$, LTRIM$ or RTRIM$ did
not assemble ("rt_err_substring is undefined"): the runtime's STRFN section
also holds rt_repeat (SPACE$ / STRING$), which reports errors through the
SLICE and CHR sections, and only SPACE$ / STRING$ switched those on. Every
built-in function is now built alone in a program, so a missing section
dependency shows as a failed build here rather than in a user's program.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memguard import guarded_run
from pbas.prg import build
from toolchain import requires_pasmo

HEAD = 'DIM A$ AS STRING\nDIM B$ AS STRING\nDIM N AS INTEGER\nDIM M AS INTEGER\nA$ = " ab c "\nN = 2\nM = 3\n'
CASES = {
    "STR$": "B$ = STR$(N)", "LEFT$ literal": "B$ = LEFT$(A$, 2)", "LEFT$": "B$ = LEFT$(A$, N)",
    "RIGHT$": "B$ = RIGHT$(A$, N)", "MID$": "B$ = MID$(A$, N, M)", "MID$ literal": 'B$ = MID$(A$, 2, 1)',
    "CHR$": "B$ = CHR$(65)", "CHR$ computed": "B$ = CHR$(N + 63)", "UCASE$": "B$ = UCASE$(A$)",
    "LCASE$": "B$ = LCASE$(A$)", "TRIM$": "B$ = TRIM$(A$)", "LTRIM$": "B$ = LTRIM$(A$)",
    "RTRIM$": "B$ = RTRIM$(A$)", "SPACE$": "B$ = SPACE$(N)", "STRING$": "B$ = STRING$(N, 65)",
    "LEN": "N = LEN(A$)", "ASC": "N = ASC(A$)", "VAL": 'N = VAL("12")', "INSTR": 'N = INSTR(A$, "b")',
    "ABS": "N = ABS(N - 5)", "MIN": "N = MIN(N, M)", "MAX": "N = MAX(N, M)", "RND": "N = RND(6)",
    "SHL": "N = SHL(N, 1)", "SHR": "N = SHR(M, 1)", "divide": "N = M / N", "MOD": "N = M MOD N",
    "multiply": "N = M * N", "compare": "IF A$ < B$ THEN\nN = 1\nEND IF",
    "SELECT": "SELECT CASE N\nCASE 1\nM = 0\nCASE ELSE\nM = 1\nEND SELECT",
}


@requires_pasmo
class EachBuiltinAloneTests(unittest.TestCase):
    def test_each_builds(self):
        for name, stmt in CASES.items():
            with self.subTest(builtin=name), tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / "p.pbas"
                src.write_text(HEAD + stmt + "\nEND\n", encoding="utf-8")
                build(src, Path(tmp) / "p.asm", Path(tmp) / "p.prg")

    def test_ki64_trim_alone_runs(self):
        for fn, want in (("TRIM$", "[x]"), ("LTRIM$", "[x  ]"), ("RTRIM$", "[  x]")):
            with self.subTest(fn=fn):
                r = guarded_run(f'DIM A$ AS STRING\nA$ = "[" + {fn}("  x  ") + "]"\nMESSAGE A$\nEND\n')
                self.assertEqual(r.violations, [])
                self.assertEqual(r.alerts, [want])


class LabelLintTests(unittest.TestCase):
    """pbas/lint.py (M11 Stage D4): a dynamic LABEL that may get more than
    the 24 characters a LABEL shows (KI-63)."""

    @staticmethod
    def found(src, path=None):
        from pbas import check_source
        from pbas.lint import warnings
        return [w[2].split(" can hold")[0] for w in warnings(check_source(src, path=path))]

    def program(self, body):
        return ('DIM S$ AS STRING * 40\nDIM T$ AS STRING * 24\nWINDOW "W"\nLABEL S$\nLABEL T$\n'
                'BUTTON "Go", Go\nSUB Go\n' + body + "END SUB\nEND\n")

    def test_findings(self):
        self.assertEqual(self.found(self.program('S$ = "short"\n')), [])
        self.assertEqual(self.found(self.program('S$ = LEFT$(T$ + T$, 24)\n')), [])
        self.assertEqual(self.found(self.program('S$ = LEFT$(T$ + T$, 25)\n')), ["LABEL S$"])
        self.assertEqual(self.found(self.program('S$ = T$ + "!"\n')), ["LABEL S$"])
        self.assertEqual(self.found(self.program('T$ = T$ + "!"\n')), [], "24 characters fit")

    def test_examples(self):
        root = Path(__file__).resolve().parents[1] / "examples"
        for name, want in (("contacts3.pbas", ["LABEL STATUS$", "LABEL INFO$"]), ("mdedit2.pbas", []),
                           ("contacts4.pbas", []), ("mdedit3.pbas", []), ("starter.pbas", [])):
            with self.subTest(program=name):
                path = root / name
                self.assertEqual(self.found(path.read_text(encoding="utf-8"), path), want)


if __name__ == "__main__":
    unittest.main()
