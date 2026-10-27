"""M12 Stage D: lib/chart.pbas, lib/chartprt.pbas and REPORTER
(examples/reporter.pbas) on the simulator.

The chart numbers are checked against Python's exact arithmetic: the scale
top (1, 2 or 5 times a power of ten) and every bar's height, value x size /
top rounded to the nearest with halves away from zero. Bars and dots are
then measured on the simulated screen, and the printed page's bars are read
from the meta-file records. Simulator evidence only (Session 3 in XAnne).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import check_source
from pbas.layout import build_dialog
from test_m12_print import solids
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pdbcheck  # noqa: E402

PATH = ROOT / "examples" / "reporter.pbas"
SRC = PATH.read_text(encoding="utf-8")
F = "\\PCW\\FOLDER01"
SIG = "ID:I;LABEL:S12;VALUE:I"
SAMPLE = [("January", 120), ("February", 345), ("March", 78), ("April", 210), ("May", 32), ("June", 164)]
SAVE, PRINT, QUIT = ("menu", 1, 0), ("menu", 1, 1), ("menu", 1, 2)
BARS, LINES = ("menu", 2, 0), ("menu", 2, 1)
DOWN, UP = 0xE1, 0xE0


def nice_top(m: int) -> int:
    if m <= 1:
        return 1
    for p in (1, 10, 100, 1000, 10000):
        for k in (1, 2, 5):
            if p * k <= 20000 and m <= p * k:
                return p * k
    return 20000


def scale(v: int, size: int, top: int) -> int:
    q = Fraction(v * size, top)
    return int(q + Fraction(1, 2)) if q >= 0 else -int(-q + Fraction(1, 2))


def chart_program(values, go: str) -> str:
    sets = "".join(f'    ChartV({i}) = {v}\n    ChartL$({i}) = "L{i}"\n' for i, v in enumerate(values, 1))
    return (f'INCLUDE "lib/chart.pbas"\nDIM S$ AS STRING * 120\nWINDOW W, "C", LARGE\n'
            f'CANVAS 400, 200, PAINT P\nBUTTON "Go", Go\nSUB P\n    DRAW CLEAR\nEND SUB\n'
            f"SUB Go\n    ChartN = {len(values)}\n{sets}{go}    EXIT\nEND SUB\nEND\n")


def run_chart(values, go):
    src = chart_program(values, go)
    with tempfile.TemporaryDirectory(prefix="pbw16-chart-") as tmp:
        # INCLUDE reads beside the program: a copy of the library there
        (Path(tmp) / "lib").mkdir()
        shutil.copy(ROOT / "examples" / "lib" / "chart.pbas", Path(tmp) / "lib" / "chart.pbas")
        path = Path(tmp) / "chart.pbas"
        path.write_text(src, encoding="utf-8")
        prog = check_source(src, path=path)
        lay = build_dialog(prog, prog.windows[0], False)
        button = next(o.number for o in lay.objects if o.kind == "BUTTON")
        r = guarded_run(src, path=path, events=[("click", button)], max_steps=300_000_000,
                        build_options={"runtime_sections": "all"})
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    r.sx, r.sy = lay.canvas[1], lay.canvas[2]
    return r


@requires_pasmo
class ChartNumberTests(unittest.TestCase):
    def test_nice_top(self):
        maxima = [0, 1, 2, 3, 5, 6, 9, 10, 11, 19, 20, 21, 49, 50, 51, 99, 100, 101, 199, 200, 499, 500, 501,
                  999, 1000, 1001, 1999, 2001, 4999, 5001, 9999, 10000, 10001, 19999, 20000]
        go = "".join(f'    S$ = S$ + STR$(ChartNiceTop({m})) + " "\n' for m in maxima[:18])
        go += '    MESSAGE S$\n    S$ = ""\n'
        go += "".join(f'    S$ = S$ + STR$(ChartNiceTop({m})) + " "\n' for m in maxima[18:])
        go += "    MESSAGE S$\n"
        r = run_chart([1], go)
        got = " ".join(r.alerts).split()
        self.assertEqual([int(g) for g in got], [nice_top(m) for m in maxima])

    def test_scale_is_exactly_rounded(self):
        cases = [(v, s, t) for t in (5, 20, 500, 20000) for v in (0, 1, 2, t // 3, t // 2, t - 1, t)
                 for s in (1, 7, 172, 300)]
        go, lines = "", []
        for i in range(0, len(cases), 12):
            chunk = cases[i:i + 12]
            go += '    S$ = ""\n'
            for v, s, t in chunk:
                go += f'    ChartTop = {t}\n    S$ = S$ + STR$(ChartScale({v}, {s})) + " "\n'
            go += "    MESSAGE S$\n"
            lines.append(" ".join(str(scale(v, s, t)) for v, s, t in chunk) + " ")
        r = run_chart([1], go)
        self.assertEqual(r.alerts, lines)
        # the halves: 1 x 5 / 2 = 2.5 rounds up, never down
        self.assertIn(3, [scale(1, 5, 2)])


@requires_pasmo
class ChartDrawingTests(unittest.TestCase):
    X, Y, W, H = 10, 4, 380, 190

    def geometry(self, values):
        top = nice_top(max(values))
        px, py, pw, ph = self.X + 46, self.Y + 8, self.W - 50, self.H - 30
        slot = pw // len(values)
        return top, px, py, ph, slot

    def column_run(self, r, x, bottom):
        """Black pixels upwards from *bottom* in canvas column x."""
        n = 0
        while r.cpu.pixel(r.sx + x, r.sy + bottom - n) == 1:
            n += 1
        return n

    def test_bars_are_the_values(self):
        values = [120, 345, 78, 210, 32, 164, 0, 499]
        r = run_chart(values, f"    CALL ChartBars({self.X}, {self.Y}, {self.W}, {self.H})\n")
        top, px, py, ph, slot = self.geometry(values)
        self.assertEqual(top, 500)
        bw = max(slot * 2 // 3, 1)
        for i, v in enumerate(values):
            bx = px + i * slot + (slot - bw) // 2
            want = scale(v, ph, top)
            # the bar's left edge is its outline, a solid line from the base up
            self.assertEqual(self.column_run(r, bx, py + ph - 1), want, (i, v))
        # the value is printed above its bar
        texts = {t[2] for t in r.cpu.texts}
        self.assertTrue({"120", "345", "78", "0"} <= texts)
        self.assertTrue({"0", "100", "200", "300", "400", "500"} <= texts)

    def test_lines_have_a_dot_at_each_value(self):
        values = [10, 40, 25, 50, 0]
        r = run_chart(values, f"    ChartSelected = 2\n    CALL ChartLines({self.X}, {self.Y}, {self.W}, {self.H})\n")
        top, px, py, ph, slot = self.geometry(values)
        self.assertEqual(top, 50)
        for i, v in enumerate(values):
            qx, qy = px + i * slot + slot // 2, py + ph - scale(v, ph, top)
            size = 7 if i == 1 else 5
            half = size // 2
            block = r.cpu.canvas_pixels(r.sx + qx - half, r.sy + qy - half, size, size)
            self.assertEqual(block, ["#" * size] * size, (i, v))

    def test_long_labels_are_shortened_visibly(self):
        values = [1] * 12
        go = "".join(f'    ChartL$({i}) = "Wednesday"\n' for i in range(1, 13))
        r = run_chart(values, go + f"    CALL ChartBars({self.X}, {self.Y}, {self.W}, {self.H})\n")
        labels = [t[2] for t in r.cpu.texts if t[2].startswith("W")]
        self.assertEqual(len(labels), 12)
        _, _, _, _, slot = self.geometry(values)
        for text in labels:
            self.assertTrue(text.endswith("."), text)
            self.assertLessEqual(z80sim.font7_width(text.encode()), slot - 2)


def objects():
    program = check_source(SRC, path=PATH)
    main = build_dialog(program, program.windows[0], True)
    edit = build_dialog(program, program.windows[1], True)
    out = {"main:" + o.text: o.number for o in main.objects if o.kind == "BUTTON"}
    out.update({"edit:" + o.text: o.number for o in edit.objects if o.kind == "BUTTON"})
    out.update({row.var_name: row.number for row in edit.bindings})
    return out, main.canvas[1], main.canvas[2]


O, CX, CY = objects()


def edit(label=None, value=None, button="Apply"):
    ev = [("click", O["main:Edit"])]
    if label is not None:
        ev.append(("edit", O["EDLABEL$"], label))
    if value is not None:
        ev.append(("edit", O["EDVALUE"], str(value)))
    return ev + [("click", O["edit:" + button])]


def run_app(events, files=None, answers=None, **sim):
    disk = z80sim.Disk(files={(F, n): d for n, d in (files or {}).items()})
    r = guarded_run(SRC, events=events, disk=disk, path=PATH, max_steps=900_000_000,
                    alert_answers=answers, build_options={"runtime_sections": "all"}, **sim)
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r


def saved(r):
    data = r.cpu.disk.file("REPORT.PDB")
    code, info = pdbcheck.check(data, SIG)
    assert code == 0, info
    return [(row[1], row[2]) for row in pdbcheck.decode(data, SIG, 12)]


@requires_pasmo
class ReporterTests(unittest.TestCase):
    CHART_X, CHART_W, CHART_H = 202, 358, 232

    def bar_heights(self, r, values):
        top = nice_top(max(values))
        px, py, pw, ph = self.CHART_X + 46, 8, self.CHART_W - 50, self.CHART_H - 30
        slot = pw // len(values)
        bw = max(slot * 2 // 3, 1)
        out = []
        for i in range(len(values)):
            bx = px + i * slot + (slot - bw) // 2
            n = 0
            while r.cpu.pixel(CX + bx, CY + py + ph - 1 - n) == 1:
                n += 1
            out.append(n)
        return out, [scale(v, ph, top) for v in values]

    def test_sample_table_and_bars(self):
        r = run_app([QUIT])
        self.assertEqual(string_var(r, "APPSTATUS$"), "6 rows, total 949")
        got, want = self.bar_heights(r, [v for _, v in SAMPLE])
        self.assertEqual(got, want)
        texts = [t[2] for t in r.cpu.texts]
        for label, value in SAMPLE:
            self.assertIn(label, texts)
            self.assertIn(str(value), texts)
        self.assertIn("949", texts)
        self.assertTrue(r.cpu.exited)  # nothing changed: no question

    def test_a_changed_value_redraws_the_chart(self):
        r = run_app([("key", DOWN)] + edit(value=1500) + [SAVE, QUIT])
        values = [120, 1500, 78, 210, 32, 164]
        got, want = self.bar_heights(r, values)
        self.assertEqual(got, want)
        self.assertEqual(saved(r), [(label, v) for (label, _), v in zip(SAMPLE, values)])
        self.assertEqual(string_var(r, "APPSTATUS$"), "6 rows, total 2104")

    def test_save_reload_add_delete(self):
        first = run_app(edit("Jan", 5) + [SAVE, QUIT])
        self.assertEqual(saved(first)[0], ("Jan", 5))
        data = first.cpu.disk.file("REPORT.PDB")
        r = run_app(edit("July", 700, "Add") + [("key", UP)] * 6 + [("key", DOWN)] + edit(button="Delete") + [SAVE, QUIT],
                    files={"REPORT.PDB": data})
        rows = saved(r)
        self.assertEqual([label for label, _ in rows], ["Jan", "March", "April", "May", "June", "July"])
        self.assertEqual(r.cpu.disk.file("REPORT.BAK"), data)

    def test_lines_view_and_back(self):
        r = run_app([LINES, BARS, LINES, QUIT])
        # the last view is the line chart: no bar outlines at the bar columns
        got, want = self.bar_heights(r, [v for _, v in SAMPLE])
        self.assertNotEqual(got, want)

    def test_at_most_twelve(self):
        ev = []
        for i in range(7):
            ev += edit(f"R{i}", i, "Add")
        r = run_app(ev + [SAVE, QUIT])
        self.assertIn("A report has at most 12 figures", r.alerts)
        self.assertEqual(len(saved(r)), 12)

    def test_total_beyond_an_integer(self):
        ev = []
        for i in range(6):
            ev += [("key", DOWN)] * (1 if i else 0) + edit(value=20000)
        r = run_app(ev + [SAVE, QUIT])
        self.assertEqual(string_var(r, "APPSTATUS$"), "6 rows, total >32767")

    def test_value_limits_are_the_numberbox(self):
        r = run_app(edit(value=20001) + [("click", O["edit:Back"]), QUIT])
        self.assertTrue([a for a in r.alerts if "20000" in a], r.alerts)

    def test_unsaved_changes_question(self):
        self.assertFalse(run_app(edit(value=1) + [QUIT], answers=[2]).cpu.exited)  # Cancel
        self.assertTrue(run_app(edit(value=1) + [QUIT], answers=[1]).cpu.exited)  # Discard
        r = run_app(edit(value=1) + [QUIT], answers=[0])  # Save
        self.assertTrue(r.cpu.exited)
        self.assertEqual(saved(r)[0], ("January", 1))

    def test_print(self):
        r = run_app([PRINT, QUIT])
        [page] = r.cpu.printed
        recs = page["records"]
        slot = 460 // 6
        bw = slot * 2 // 3
        bars = [s for s in solids(recs) if s[2] == bw * 25]
        values = [v for _, v in SAMPLE]
        ph = 300 - 40
        self.assertEqual([b[0] // 25 for b in bars], [40 + i * slot + (slot - bw) // 2 for i in range(6)])
        self.assertEqual([b[3] // 25 for b in bars], [scale(v, ph, nice_top(max(values))) for v in values])
        base = 300 + 12 + ph
        self.assertEqual({(b[1] + b[3]) // 25 for b in bars}, {base})
        self.assertEqual(string_var(r, "APPSTATUS$"), "Printed")

    def test_damaged_file_falls_back_to_the_sample(self):
        r = run_app([QUIT], files={"REPORT.PDB": b"PDB1" + bytes(20)})
        self.assertTrue(r.alerts and r.alerts[0].startswith("REPORT.PDB: "), r.alerts)
        self.assertEqual(string_var(r, "APPSTATUS$"), "6 rows, total 949")


if __name__ == "__main__":
    unittest.main()
