"""docs/M12-ACCEPTANCE.md, step by step, on the simulator: every status line
and file the guide quotes is what the programs give (Sessions 1, 3 and 4;
Session 2's pages are checked in test_m12_print.DemoTests, BMPPROBE's lines
in test_m12_bitmap.ProbeTests). Simulator evidence only: the owner's XAnne
sessions decide."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from memguard import string_var
from pbas import check_source
from pbas.layout import build_dialog
from toolchain import requires_files, requires_pasmo

import test_m12_mdedit4 as tm
import test_m12_paint as tp
import test_m12_print as tpr
import test_m12_reporter as tr
from test_m10_mdedit2 import keys, SAVE

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import m12_sample_data  # noqa: E402
import pbicheck  # noqa: E402

# M14: the owner's acceptance guide is an engineering record of the private repository. Where it is
# absent (the public repository) the sessions below are still run and checked; only the check that
# the guide quotes each status text is not made, and GuideQuotes is reported as skipped for it.
GUIDE_PATH = ROOT / "docs" / "M12-ACCEPTANCE.md"
GUIDE = GUIDE_PATH.read_text(encoding="utf-8") if GUIDE_PATH.exists() else None
SAMPLE = pbicheck.from_rows(m12_sample_data.sample_rows())


def quoted(text):
    if GUIDE is not None:
        assert f"`{text}`" in GUIDE, f"the guide does not quote `{text}`"
    return text


@requires_files(GUIDE_PATH, what="the owner's M12 acceptance guide")
class GuideQuotes(unittest.TestCase):
    """M14: reports, as a skip, that the guide's quotes were not checked."""

    def test_the_guide_is_here_to_check_quotes_against(self):
        self.assertIn("`", GUIDE)


@requires_pasmo
class PaintSessionTests(unittest.TestCase):
    FB = tp.FB
    SKETCH = tp.stroke([(50, 50), (80, 60), (120, 90)]) + [tp.shade(3), tp.FILLED] + tp.stroke([(200, 40), (300, 120)])

    def status(self, events, files=None, answers=(1,)):
        r = tp.run(events, files=files, answers=list(answers), quit=False)
        return string_var(r, "APPSTATUS$"), r

    def files_step(self, button, name):
        return [tp.OPEN if button == "Open" else tp.SAVEAS, ("edit", self.FB["FILENAME$"], name), ("click", self.FB[button])]

    def test_p1_to_p8(self):
        self.assertEqual(self.status([])[0], quoted("Pencil 0 "))
        self.assertEqual(self.status(tp.stroke([(50, 50), (80, 60), (120, 90)]))[0], quoted("Pencil 0 *"))
        self.assertEqual(self.status(self.SKETCH)[0], quoted("Filled 3 *"))
        self.assertEqual(self.status(self.SKETCH + [tp.UNDO, tp.UNDO])[0], quoted("Nothing to undo"))
        s, r = self.status(self.SKETCH + [tp.PENCIL] + self.files_step("Save as", "ART"))
        self.assertEqual(s, quoted("Pencil 3 ART.PBI"))
        self.art = r.cpu.disk.file("ART.PBI")
        self.assertEqual(pbicheck.check(self.art)[0], 0)
        s, _ = self.status(self.files_step("Open", "ART"), files={"ART.PBI": self.art})
        self.assertEqual(s, quoted("Pencil 0 ART.PBI"))

    def test_p10_to_p13(self):
        s, r = self.status(self.files_step("Open", "SAMPLE.PBI"), files={"SAMPLE.PBI": SAMPLE})
        self.assertEqual(s, quoted("Pencil 0 SAMPLE.PBI"))
        self.assertEqual(tp.picture(r), ["".join("#" if v else "." for v in row) for row in m12_sample_data.sample_rows()])
        self.assertEqual(self.status([tp.SAMPLE])[0], quoted("Pencil 0 HOUSE.PBI*"))
        s, r = self.status([tp.SAMPLE] + self.files_step("Open", "EDTEST.MD") + [("click", self.FB["Back"]), tp.UNDO],
                           files={"EDTEST.MD": tm.DOC})
        self.assertIn(quoted("Not opened: not a picture"), r.alerts)
        self.assertEqual(s, "Nothing to undo")
        r = tp.run([tp.SAMPLE, tp.QUIT], answers=[2, 1], quit=False)
        self.assertFalse(r.cpu.exited)
        r = tp.run([tp.SAMPLE, tp.QUIT, tp.QUIT], answers=[2, 1], quit=False)
        self.assertTrue(r.cpu.exited)


@requires_pasmo
class ReporterSessionTests(unittest.TestCase):
    def test_c1_to_c9(self):
        st = lambda ev: string_var(tr.run_app(ev + [tr.QUIT], answers=[1]), "APPSTATUS$")
        self.assertEqual(st([]), quoted("6 rows, total 949"))
        r = tr.run_app([("key", tr.DOWN), ("click", tr.O["main:Edit"]), ("click", tr.O["edit:Back"]), tr.QUIT])
        self.assertEqual(string_var(r, "INFO$"), quoted("Figure 2 of 6"))
        c4 = [("key", tr.DOWN)] + tr.edit(value=500)
        self.assertEqual(st(c4), quoted("6 rows, total 1104 *"))
        c6 = c4 + [tr.LINES, tr.BARS] + tr.edit("July", 250, "Add")
        self.assertEqual(st(c6), quoted("7 rows, total 1354 *"))
        r = tr.run_app(c6 + [tr.SAVE, tr.QUIT])
        data = r.cpu.disk.file("REPORT.PDB")
        self.assertEqual(tr.saved(r), [("January", 120), ("February", 500), ("March", 78), ("April", 210),
                                       ("May", 32), ("June", 164), ("July", 250)])
        r = tr.run_app([tr.PRINT, tr.QUIT], files={"REPORT.PDB": data})
        self.assertEqual(string_var(r, "APPSTATUS$"), "Printed")
        texts = [line[1] for line in tpr.lines_of(r.cpu.printed[0]["records"])]
        self.assertIn("1354", texts)
        self.assertIn("Report", texts)


@requires_pasmo
class EditorSessionTests(unittest.TestCase):
    def setUp(self):
        prog = check_source(tm.SRC, path=tm.PATH)
        tools = build_dialog(prog, prog.windows[1], True)
        b = {o.text: o.number for o in tools.objects if o.kind == "BUTTON"}
        b.update({row.var_name: row.number for row in tools.bindings})
        self.open = [("menu", 1, 0), ("edit", b["FILENAME$"], "WRAPTEST.MD"), ("click", b["Open"])]
        self.files = {"EDTEST.MD": tm.DOC, "WRAPTEST.MD": tm.WRAPDOC}

    def status(self, ev):
        r = tm.run(self.open + ev, files=self.files)
        return string_var(r, "STATUS$"), r

    def test_w1_to_w5(self):
        s, r = self.status([])
        self.assertEqual((s, string_var(r, "INFO$")), (quoted("L1/32 C1"), quoted("Opened WRAPTEST.MD")))
        self.assertEqual(len([row for row in tm.screen(r) if row[0] and tm.PARA1.find(row[0][:20]) >= 0]), 5)
        d = [("key", tm.DOWN)] * 2
        self.assertEqual(self.status(d)[0], quoted("L3/32 C1"))
        self.assertEqual(self.status(d + [("key", tm.END_)])[0], quoted("L3/32 C379"))
        s, r = self.status(d + keys("Hello "))
        self.assertEqual(s, quoted("* L3/32 C7"))
        rows = tm.screen(r)
        self.assertTrue(rows[2][0].endswith("flash disc"), rows[2][0])
        self.assertTrue(rows[3][0].startswith("and a floppy drive."), rows[3][0])
        self.assertEqual(self.status(d + keys("Hello ") + [("key", tm.BS)] * 6)[0], quoted("* L3/32 C1"))
        self.assertEqual(self.status(d + [("key", tm.RIGHT)] * 10 + [("key", tm.DOWN)] * 3)[0], quoted("L3/32 C283"))

    def test_w8_and_w10(self):
        self.assertEqual(tm.line_rows(tm.LINES[6])[0][1], 78)
        r = tm.run(self.open + [("key", 230, 4)] + keys("New: ") + [SAVE, ("menu", 1, 2)], files=self.files)
        self.assertEqual(string_var(r, "INFO$"), quoted("Saved WRAPTEST.MD"))
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.disk.file("WRAPTEST.BAK"), tm.WRAPDOC)
        self.assertEqual(r.cpu.disk.file("WRAPTEST.MD").split(b"\r\n")[0], b"New: # Wrapping test")
        self.assertIsNone(r.cpu.disk.file("MDEDIT4.TMP"))


@requires_pasmo
class PrintSessionTests(unittest.TestCase):
    def test_r1_status(self):
        r = tpr.DemoTests().run_demo(["Letter", "Table", "Chart"])
        self.assertEqual(len(r.cpu.printed), 3)
        self.assertEqual(r.alerts, [])


if __name__ == "__main__":
    unittest.main()
