"""M8 selective inclusion of the REAL library (pbas/prune.py).

Each REAL feature is compiled ALONE, so that a dependency the pruner missed
cannot be hidden by another feature that happens to keep the same code. The
result is compared with Python's maths. Engineering evidence, not XAnne.
"""
from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from fractions import Fraction

from memguard import guarded_run
from pbas import check_source, generate
from pbas.prg import DEFAULT_RUNTIME_PATH, build
from pbas.prune import prune_real
from pbas.real import pack, unpack
from toolchain import requires_files, requires_pasmo

RUNTIME = DEFAULT_RUNTIME_PATH.read_text(encoding="utf-8")


def alone(expr: str):
    """The REAL value of *expr*, compiled in a program that uses nothing else."""
    r = guarded_run(f"DIM X AS REAL\nX = {expr}\nEND\n")
    assert r.violations == [] and r.cpu.alerts == [], (r.violations, r.cpu.alerts)
    at = r.symbols["var_x"]
    return float(unpack(r.cpu.mem[at:at + 5]))


class PruneTextTests(unittest.TestCase):
    def test_programs_without_real_are_untouched(self):
        program = generate(check_source("DIM N AS INTEGER\nN = 2\nEND\n"))
        self.assertEqual(prune_real(program, RUNTIME), RUNTIME)

    def test_only_real_sections_change(self):
        program = generate(check_source("DIM X AS REAL\nX = 1.5\nEND\n"))
        pruned = prune_real(program, RUNTIME)
        self.assertLess(len(pruned), len(RUNTIME))
        kept = [ln for ln in pruned.split("\n") if not ln.startswith("; (M8 selective inclusion")]
        self.assertTrue(set(kept) <= set(RUNTIME.split("\n")))  # only removals
        # outside the PB_REAL sections nothing differs
        def outside(text):
            out, depth = [], 0  # M14: a REAL section may hold its own IF (PB_RSTICKY)
            for ln in text.split("\n"):
                if ln.rstrip() == "    IF PB_REAL" or (depth and ln.strip().startswith("IF ")):
                    depth += 1
                elif depth and ln.strip() == "ENDIF":
                    depth -= 1
                elif not depth:
                    out.append(ln)
            return out
        self.assertEqual(outside(pruned), outside(RUNTIME))

    def test_data_runs_are_kept_whole(self):
        # rt_freduce reaches the low constant as high + 5: both must stay
        program = generate(check_source("DIM X AS REAL\nX = SIN(1.0)\nEND\n"))
        pruned = prune_real(program, RUNTIME)
        self.assertIn("rt_fc_pio2_lo:", pruned)
        self.assertIn("rt_fc_ln2_lo:", pruned)


@requires_pasmo
class IsolatedFeatureTests(unittest.TestCase):
    def test_each_function_alone(self):
        cases = {"SQR(2.0)": math.sqrt(2), "EXP(1.0)": math.e, "LOG(10.0)": math.log(10), "SIN(1.0)": math.sin(1),
                 "COS(1.0)": math.cos(1), "TAN(0.5)": math.tan(0.5), "ATN(1.0)": math.atan(1),
                 "2.0 ^ 0.5": math.sqrt(2), "2.0 ^ 10": 1024.0, "10.0 ^ -200": 0.0, "INT(-2.5)": -3.0,
                 "FIX(-2.5)": -2.0, "1.0 * CINT(2.5)": 3.0, "ABS(-1.25)": 1.25, "MIN(1.5, 2)": 1.5,
                 "MAX(1.5, 2)": 2.0, "1.0 / 3": 1 / 3, "1.5 - 0.25": 1.25, "PI * 2": 2 * math.pi,
                 'REALVAL("1.5E3")': 1500.0, "1.0 * SGN(-0.5)": -1.0}
        for expr, want in cases.items():
            with self.subTest(expr=expr):
                self.assertLessEqual(abs(alone(expr) - want), 4e-9 * max(abs(want), 1e-30) + 1e-12, expr)

    def test_text_conversions_alone(self):
        for src, want in (('MESSAGE STR$(1.0 / 3)\nEND\n', ["0.333333333"]),
                          ('IF ISNUM("1e5") THEN\nMESSAGE "y"\nEND IF\nEND\n', ["y"]),
                          ('DIM X AS REAL\nX = 2.5\nIF X > 2 THEN\nMESSAGE "gt"\nEND IF\nEND\n', ["gt"]),
                          ('DIM X AS REAL\nX = SQR(-1.0)\nEND\n',
                           ["Runtime error: function argument out of range at line 2"])):
            with self.subTest(src=src):
                r = guarded_run(src)
                self.assertEqual((r.violations, r.cpu.alerts), ([], want))

    def test_exact_values_alone(self):
        self.assertEqual(Fraction(alone("1.0 / 3")), unpack(pack(Fraction(1, 3))))


@requires_pasmo
class WholeLibraryTests(unittest.TestCase):
    """prune=False (build.py --whole-real-library) rebuilds the XAnne-accepted
    M7 REAL programs byte for byte; the default build is smaller."""
    ROOT = Path(__file__).resolve().parents[1]

    @requires_files(ROOT / "artifacts" / "m7-fix" / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14

    def test_accepted_m7_real_programs(self):
        for src, art in (("examples/scicalc.pbas", "m7-fix/scicalc.prg"), ("examples/journal.pbas", "m7/journal.prg"),
                         ("developer-tests/m7_edges.pbas", "m7/m7_edges.prg")):
            with self.subTest(src=src), tempfile.TemporaryDirectory() as tmp:
                whole = build(self.ROOT / src, Path(tmp) / "w.asm", Path(tmp) / "w.prg", prune=False,
                              legacy_real_rounding=True, legacy_tasks_stop=True)  # M14, M15: as accepted
                self.assertEqual((Path(tmp) / "w.prg").read_bytes(), (self.ROOT / "artifacts" / art).read_bytes())
                pruned = build(self.ROOT / src, Path(tmp) / "p.asm", Path(tmp) / "p.prg")
                self.assertLess(pruned.prg_size, whole.prg_size)


if __name__ == "__main__":
    unittest.main()
