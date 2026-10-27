"""M12 corrective: what printed lines, boxes and bars look like on paper.

The owner's XAnne Session 2 (Rosanne 1.12, a 300 dpi page captured and
converted with GhostPCL) printed PRINTDEMO's and REPORTER's bar charts as
merged black blocks. Each PAGE FILL came out h points too wide: Rosanne's
printer driver draws an os_meta_hline on past its right end by its own
thickness, and starts an os_meta_vline its thickness (less a dot) below its
top (tests/printmodel.py; docs/M12-PRINTING.md §6). The runtime now sends
records that allow for both (rt_pg_solid).

These tests put the records the simulator collects through that model and
check the paper: every rectangle within a dot of where the program placed
it, at three printer resolutions and several page offsets; the charts' bars
apart, as tall as their values, clear of their labels. OwnerPageTests checks
the model itself against the owner's page.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import printmodel as pm
import test_m12_print as tp
import test_m12_reporter as tr
from memguard import guarded_run
from pbas import check_source
from pbas.layout import build_dialog
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
U = 25  # 1/1800" per point
# (units a dot, x offset, y offset): 360, 300 and 180 dpi; the owner's page
# (300 dpi) has x = 1350, y = 1116 (OwnerPageTests)
PRINTERS = ((5, 0, 0), (6, 1350, 1116), (6, 7, 3), (10, 900, 450))


def boxes(records) -> list[tuple[str, int, int, int, int]]:
    """(text, x0, x1, top, bottom) of each printed text, in 1/1800"."""
    out = []
    for text, x0, x1, top in [(t, a, b, top) for top, t, a, b in tp.lines_of(records)]:
        out.append((text, x0, x1, top))
    ys = [rec for rec in records if rec[0] == "y"]
    return [(t, x0, x1, y[2], y[3]) for (t, x0, x1, _), y in zip(out, ys)]


class PaperMixin:
    def near(self, got: float, want: float, what: str):
        self.assertLessEqual(abs(got - want), 1, f"{what}: {got} dots, want {want:.2f}")

    def assert_rect(self, rs, rect, d, ox, oy, what=""):
        """rs print exactly the rectangle (x, y, w, h) in points: solid, each
        edge within a dot."""
        x, y, w, h = (v * U for v in rect)
        ext = pm.extent(rs)
        self.near(ext[0], (x + ox) / d, f"{what} left")
        self.near(ext[2] + 1, (x + w + ox) / d, f"{what} right")
        self.near(ext[1], (y + oy) / d, f"{what} top")
        self.near(ext[3] + 1, (y + h + oy) / d, f"{what} bottom")
        self.assertTrue(pm.solid(rs, ext), f"{what}: not solid")


@requires_pasmo
class ShapeTests(PaperMixin, unittest.TestCase):
    """Each shape on a page of its own, read back through the model."""

    def pages(self, statements):
        src = "".join(f"PAGE NEW\n{s}\nPAGE PRINT\n" for s in statements) + "END\n"
        r = tp.run(src)
        self.assertEqual(len(r.cpu.printed), len(statements))
        return [page["records"] for page in r.cpu.printed]

    def test_fills_are_their_rectangles(self):
        shapes = [(10, 20, 40, 172), (100, 20, 200, 30), (320, 20, 50, 50), (0, 300, 1, 400), (0, 250, 522, 1),
                  (400, 400, 100, 365), (0, 0, 522, 765), (5, 5, 3, 700), (60, 600, 41, 40), (60, 600, 40, 41)]
        for shape, recs in zip(shapes, self.pages([f"PAGE FILL {x}, {y}, {w}, {h}" for x, y, w, h in shapes])):
            self.assertLessEqual(len(recs), 4)  # at most two lines a rectangle
            for d, ox, oy in PRINTERS:
                with self.subTest(shape=shape, d=d, ox=ox, oy=oy):
                    self.assert_rect(pm.rects(recs, d, ox, oy), shape, d, ox, oy, "fill")

    def test_lines_are_their_rectangles(self):
        lines = [((10, 50, 300, 50, 1), (10, 50, 290, 1)), ((10, 50, 300, 50, 10), (10, 50, 290, 10)),
                 ((300, 80, 10, 80, 72), (10, 80, 290, 72)), ((40, 100, 40, 400, 1), (40, 100, 1, 300)),
                 ((40, 400, 40, 100, 2), (40, 100, 2, 300)), ((200, 100, 200, 130, 72), (200, 100, 72, 30))]
        stmts = [f"PAGE LINE {a}, {b}, {c}, {e}, {t}" for (a, b, c, e, t), _ in lines]
        for (_, rect), recs in zip(lines, self.pages(stmts)):
            for d, ox, oy in PRINTERS:
                with self.subTest(rect=rect, d=d):
                    self.assert_rect(pm.rects(recs, d, ox, oy), rect, d, ox, oy, "line")

    def test_a_box_is_its_outline(self):
        [recs] = self.pages(["PAGE BOX 36, 54, 270, 148"])
        for d, ox, oy in PRINTERS:
            with self.subTest(d=d):
                rs = pm.rects(recs, d, ox, oy)
                ext = pm.extent(rs)
                self.near(ext[0], (36 * U + ox) / d, "left")
                self.near(ext[2] + 1, (306 * U + ox) / d, "right")
                self.near(ext[1], (54 * U + oy) / d, "top")
                self.near(ext[3] + 1, (202 * U + oy) / d, "bottom")
                one = pm.ceil_div(U, d) + 1  # a 1-point side, a dot either way
                mid_row = pm.row(rs, (128 * U + oy) // d)
                self.assertEqual(len(mid_row), 2)
                self.assertTrue(all(b - a + 1 <= one for a, b in mid_row), mid_row)
                mid_col = pm.column(rs, (171 * U + ox) // d)
                self.assertEqual(len(mid_col), 2)
                self.assertTrue(all(b - a + 1 <= one for a, b in mid_col), mid_col)
                # the corners are closed: the top line reaches the right side
                self.assertEqual(pm.row(rs, (54 * U + oy) // d), [(ext[0], ext[2])])


@requires_pasmo
class OwnerPageTests(unittest.TestCase):
    """The model against the owner's page: PRINTDEMO's chart as the M12
    candidate (1c8a7a4) printed it, captured in XAnne and converted with
    GhostPCL; the dots measured with pdftoppm -r 300 -mono. The records are
    those that build sent (each bar an hline from x to x + 40 points)."""

    RECORDS = [("hline", 1650, 11400, y, 25) for y in (7500, 6250, 5000, 3750, 2500)] + [
        ("vline", 1650, 2500, 7500, 50),
        ("hline", 1900, 2900, 6000, 1500), ("hline", 3500, 4500, 3200, 4300), ("hline", 5100, 6100, 6525, 975),
        ("hline", 6700, 7700, 4875, 2625), ("hline", 8300, 9300, 7100, 400), ("hline", 9900, 10900, 5450, 2050)]
    # measured on the owner's page: black runs (first, last dot) of rows
    ROWS = {908: [(500, 508), (808, 1691)], 1008: [(500, 508), (808, 1945)], 1108: [(500, 508), (808, 2382)],
            1208: [(500, 508), (541, 2382)], 1300: [(500, 508), (541, 2382)],
            602: [(500, 2129)], 811: [(500, 2129)], 1019: [(500, 2129)]}

    def test_the_model_draws_the_owners_page(self):
        rs = pm.rects(self.RECORDS, 6, 1350, 1116)
        for y, runs in self.ROWS.items():
            with self.subTest(row=y):
                self.assertEqual(pm.row(rs, y), runs)
        # the grid lines are rows 602-606 (1 point = 5 dots); the 2-point axis
        # is 9 dots wide and starts 8 dots below its top, at row 610
        self.assertEqual(pm.column(rs, 2100)[:3], [(602, 606), (811, 815), (1019, 1023)])
        self.assertEqual(pm.column(rs, 504)[:2], [(602, 606), (610, 1440)])
        # Coffee's top (128 points) is row 719, as on the page
        self.assertEqual(pm.column(rs, 892)[1][0], 719)

    def test_the_fault_was_the_width(self):
        # the defective page's Coffee bar was 40 + 172 points wide
        rs = pm.rects([("hline", 3500, 4500, 3200, 4300)], 6)
        x0, _, x1, _ = rs[0]
        self.assertEqual((x1 + 1 - x0) * 6 // U, 212)


def chart_page(values, labels=None, font=8):
    """lib/chartprt's ChartPrintBars(0, 300, 500, 300) for values on a page."""
    labels = labels or [f"L{i}" for i in range(1, len(values) + 1)]
    sets = "".join(f'    ChartV({i}) = {v}\n    ChartL$({i}) = "{lab}"\n'
                   for i, (v, lab) in enumerate(zip(values, labels), 1))
    src = (f'INCLUDE "lib/chart.pbas"\nINCLUDE "lib/chartprt.pbas"\nWINDOW W, "C", LARGE\n'
           f'CANVAS 400, 200, PAINT P\nBUTTON "Go", Go\nSUB P\n    DRAW CLEAR\nEND SUB\n'
           f"SUB Go\n    ChartN = {len(values)}\n{sets}    PAGE NEW\n    PAGE FONT {font}\n"
           f"    CALL ChartPrintBars(0, 300, 500, 300)\n    PAGE PRINT\n    EXIT\nEND SUB\nEND\n")
    with tempfile.TemporaryDirectory(prefix="pbw16-chartprt-") as tmp:
        (Path(tmp) / "lib").mkdir()
        for name in ("chart.pbas", "chartprt.pbas"):
            shutil.copy(ROOT / "examples" / "lib" / name, Path(tmp) / "lib" / name)
        path = Path(tmp) / "chartprt.pbas"
        path.write_text(src, encoding="utf-8")
        prog = check_source(src, path=path)
        lay = build_dialog(prog, prog.windows[0], False)
        button = next(o.number for o in lay.objects if o.kind == "BUTTON")
        r = guarded_run(src, path=path, events=[("click", button)], max_steps=600_000_000,
                        build_options={"runtime_sections": "all"})
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    [page] = r.cpu.printed
    return page["records"]


class ChartMixin(PaperMixin):
    def check_bars(self, recs, bars, area_right, what=""):
        """bars: (x, top, w, h) in points, all standing on one base; each
        printed as its rectangle, apart from the next, left of area_right,
        and no text printed over any of them."""
        base = bars[0][1] + bars[0][3]
        for d, ox, oy in PRINTERS:
            with self.subTest(what=what, d=d, ox=ox, oy=oy):
                rs = pm.rects(recs, d, ox, oy)
                # a row just above the base: the axis, then one run a bar
                runs = pm.row(rs, ((base - 1) * U + oy) // d)
                standing = [b for b in bars if b[3] >= 2]
                self.assertEqual(len(runs), 1 + len(standing), runs)
                for (a, b), (x, _, w, _) in zip(runs[1:], standing):
                    self.near(a, (x * U + ox) / d, f"bar at {x} left")
                    self.near(b + 1, ((x + w) * U + ox) / d, f"bar at {x} right")
                    self.assertLess(b, ((area_right * U) + ox) / d)
                for (_, b), (a, _) in zip(runs[1:], runs[2:]):
                    self.assertGreater(a - b, 3, "bars touch")
                # each bar as tall as its value: its column from the base up
                for x, top, w, h in standing:
                    col = pm.column(rs, ((x + w // 2) * U + ox) // d)
                    [run] = [r for r in col if r[0] <= ((base - 1) * U + oy) // d <= r[1]]
                    self.near(run[0], (top * U + oy) / d, f"bar at {x} top")
                # no text over a bar
                solid_rs = [q for q in rs if (q[2] - q[0] + 1) * d >= 3 * U and (q[3] - q[1] + 1) * d >= 2 * U]
                for text, x0, x1, top, bottom in boxes(recs):
                    tb = ((x0 + ox) // d, (top + oy) // d, (x1 + ox) // d, (bottom + oy) // d)
                    for q in solid_rs:
                        self.assertFalse(tb[0] <= q[2] and q[0] <= tb[2] and tb[1] <= q[3] and q[1] <= tb[3],
                                         f"{text!r} printed over a bar")


@requires_pasmo
class DemoChartTests(ChartMixin, unittest.TestCase):
    """RP1: PRINTDEMO's chart (examples/printdemo.pbas PrintChart)."""

    def test_six_separate_bars(self):
        r = tp.DemoTests("test_no_printer").run_demo(["Chart"])
        [recs] = tp.printed(r)
        amounts = [120, 345, 78, 210, 32, 164]
        bars = [(76 + 64 * i, 300 - a // 2, 40, a // 2) for i, a in enumerate(amounts)]
        self.check_bars(recs, bars, 456, "PRINTDEMO")
        texts = [b[0] for b in boxes(recs)]
        for word in ["Tea", "Coffee", "Biscuits", "Milk", "Sugar", "Fruit"] + [str(a) for a in amounts]:
            self.assertIn(word, texts)
        scale = ["0", "100", "200", "300", "400"]
        self.assertTrue(any(texts[k:k + 5] == scale for k in range(len(texts))), texts)


@requires_pasmo
class LibraryChartTests(ChartMixin, unittest.TestCase):
    """lib/chartprt.pbas ChartPrintBars(0, 300, 500, 300): plot from x 40 to
    500, base at 300 + 12 + 260."""

    def bars(self, values):
        top = tr.nice_top(max(values))
        slot = 460 // len(values)
        bw = max(slot * 2 // 3, 1)
        out = []
        for i, v in enumerate(values):
            h = tr.scale(v, 260, top)
            out.append((40 + i * slot + (slot - bw) // 2, 572 - h, bw, h))
        return out, slot

    def test_seven_bars_of_the_owners_report(self):
        values = [120, 500, 78, 210, 32, 164, 250]
        recs = chart_page(values)
        bars, _ = self.bars(values)
        self.check_bars(recs, bars, 500, "seven")

    def test_twelve_bars_with_long_labels(self):
        values = [k * 1000 for k in range(1, 13)]
        labels = ["Septembers" + str(k) for k in range(1, 13)]
        recs = chart_page(values, labels)
        bars, slot = self.bars(values)
        self.check_bars(recs, bars, 500, "twelve")
        shown = [b for b in boxes(recs) if b[0].startswith("Sep")]
        self.assertEqual(len(shown), 12)
        for i, (text, x0, x1, _, _) in enumerate(shown):
            self.assertTrue(text.endswith("."), text)  # shortened, visibly
            self.assertGreaterEqual(x0, (40 + i * slot) * U)
            self.assertLessEqual(x1, (40 + (i + 1) * slot) * U)

    def test_a_zero_bar_and_a_bar_at_the_top(self):
        values = [0, 50, 100]
        recs = chart_page(values)
        bars, _ = self.bars(values)
        self.check_bars(recs, bars, 500, "zero")
        self.assertIn("0", [b[0] for b in boxes(recs)])  # its value is still printed
        for d, ox, oy in PRINTERS:
            rs = pm.rects(recs, d, ox, oy)
            x = (bars[0][0] + bars[0][2] // 2) * U
            # nothing in the zero bar's column but the grid lines (1 point)
            self.assertTrue(all((b - a + 1) * d <= U + d for a, b in pm.column(rs, (x + ox) // d)))
            # the full bar reaches the scale's top line (at 312)
            x = (bars[2][0] + bars[2][2] // 2) * U
            col = pm.column(rs, (x + ox) // d)
            self.near(col[0][0], (312 * U + oy) / d, "top bar")

    def test_one_bar(self):
        recs = chart_page([7])
        bars, _ = self.bars([7])
        self.check_bars(recs, bars, 500, "one")


@requires_pasmo
class ReporterPrintTests(ChartMixin, unittest.TestCase):
    """RP2 and RP4: REPORTER printing the owner's seven-record REPORT.PDB."""

    ROWS = [("January", 120), ("February", 500), ("March", 78), ("April", 210), ("May", 32), ("June", 164),
            ("July", 250)]

    @classmethod
    def setUpClass(cls):
        first = tr.run_app([("key", tr.DOWN)] + tr.edit(value=500) + tr.edit("July", 250, "Add") + [tr.SAVE, tr.QUIT])
        assert tr.saved(first) == cls.ROWS
        cls.pdb = first.cpu.disk.file("REPORT.PDB")

    def test_seven_separate_bars_and_the_table(self):
        files = {"REPORT.PDB": self.pdb, "NOTES.TXT": b"the owner's own file\r\n"}
        r = tr.run_app([tr.PRINT, tr.PRINT, tr.QUIT], files=files)
        self.assertEqual(tr.string_var(r, "APPSTATUS$"), "Printed")
        first, second = (page["records"] for page in r.cpu.printed)
        self.assertEqual(first, second)  # a second print is the same page
        values = [v for _, v in self.ROWS]
        slot = 460 // 7
        bw = slot * 2 // 3
        bars = [(40 + i * slot + (slot - bw) // 2, 572 - tr.scale(v, 260, 500), bw, tr.scale(v, 260, 500))
                for i, v in enumerate(values)]
        self.check_bars(first, bars, 500, "REPORTER")
        texts = [b[0] for b in boxes(first)]
        for label, value in self.ROWS:
            self.assertIn(label, texts)
            self.assertIn(str(value), texts)
        self.assertIn("1354", texts)
        scale = ["0", "100", "200", "300", "400", "500"]  # printed one after another
        self.assertTrue(any(texts[k:k + 6] == scale for k in range(len(texts))), texts)
        # printing changed no file (RP4)
        data = {name: v for (_, name), v in r.cpu.disk.files.items() if not name.endswith(".PRG")}
        self.assertEqual(data, files)  # the same files, the same bytes: no .BAK, .NEW or other file


if __name__ == "__main__":
    unittest.main()
