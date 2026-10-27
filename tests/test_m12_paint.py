"""PAINT (examples/paint.pbas, M12 Stage B) on the simulator.

Whole sessions are driven with raw mouse events, keys and menu choices,
and the canvas is compared pixel for pixel with what the drawing
statements produce on their own (a reference program), so that a rubber
band left behind, an undo that restores the wrong picture or a paste in
the wrong place shows. Saved pictures are read with tools/pbicheck.py.
Simulator evidence only: Rosanne's drawing and the BIOS bitmap calls are
for the owner's XAnne session (docs/M12-ACCEPTANCE.md, Session 1).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import check_source
from pbas.layout import build_dialog
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pbicheck  # noqa: E402

PATH = ROOT / "examples" / "paint.pbas"
SRC = PATH.read_text(encoding="utf-8")
F = "\\PCW\\FOLDER01"
CW, CH = 544, 240

# menus (dividers are not numbered)
NEW, OPEN, SAVE, SAVEAS, SAMPLE, QUIT = (("menu", 1, i) for i in range(6))
UNDO, REDO, COPY, PASTE, CLEAR = (("menu", 2, i) for i in range(5))
PENCIL, LINE, BOX, FILLED, ERASER, SELECT = (("menu", 3, i) for i in range(6))


def shade(n):
    return ("menu", 4, n)


def layout():
    program = check_source(SRC, path=PATH)
    main = build_dialog(program, program.windows[0], True)
    files = build_dialog(program, program.windows[1], True)
    buttons = {o.text: o.number for o in files.objects if o.kind == "BUTTON"}
    buttons.update({row.var_name: row.number for row in files.bindings})
    return main.canvas[1], main.canvas[2], buttons


SX, SY, FB = layout()


def at(x, y):
    return SX + x, SY + y


def stroke(points):
    """Press at the first point, drag through the others, release at the last."""
    (x, y), rest = points[0], points[1:]
    ev = [("mdown",) + at(x, y)]
    ev += [("mmove",) + at(px, py) for px, py in rest]
    return ev + [("mup",) + at(*points[-1])]


def run(events, files=None, answers=None, quit=True, banks="all"):
    """*answers*: the button chosen (0-based) for each question."""
    disk = z80sim.Disk(files={(F, n): d for n, d in (files or {}).items()})
    tail = [QUIT] if quit else []
    r = guarded_run(SRC, events=events + tail, disk=disk, path=PATH, max_steps=600_000_000,
                    alert_answers=answers, build_options={"runtime_sections": banks} if banks else None)
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r


def picture(r):
    return r.cpu.canvas_pixels(SX, SY, CW, CH)


_REFS: dict[str, list[str]] = {}


def reference(drawing: str) -> list[str]:
    """The canvas after *drawing* (DRAW statements) on a clean canvas."""
    if drawing not in _REFS:
        src = (f'WINDOW W, "R", LARGE\nCANVAS {CW}, {CH}, PAINT P\nBUTTON "Q", Q\n'
               f"SUB P\n    DRAW CLEAR\n{drawing}END SUB\nSUB Q\n    EXIT\nEND SUB\nEND\n")
        program = check_source(src)
        lay = build_dialog(program, program.windows[0], False)
        r = guarded_run(src, events=[])
        assert r.violations == [] and not r.alerts, (r.violations, r.alerts)
        _REFS[drawing] = r.cpu.canvas_pixels(lay.canvas[1], lay.canvas[2], CW, CH)
    return _REFS[drawing]


WHITE = ["." * CW] * CH


def files_of(r):
    return {n: d for (f, n), d in r.cpu.disk.files.items() if f == F and n != "PROGRAM.PRG"}


@requires_pasmo
class DrawingTests(unittest.TestCase):
    def test_pencil_undo_redo(self):
        line = stroke([(10, 10), (30, 10), (30, 20)])
        r = run(line)
        self.assertEqual(picture(r), reference("    DRAW LINE 10, 10, 30, 10\n    DRAW LINE 30, 10, 30, 20\n"))
        self.assertEqual(r.cpu.exited, False)  # unsaved: Quit asked, and Save without a name opened Files
        r = run(line + [UNDO], answers=[1])
        self.assertEqual(picture(r), WHITE)
        self.assertTrue(r.cpu.exited)
        r = run(line + [UNDO, REDO], answers=[1])
        self.assertEqual(picture(r), reference("    DRAW LINE 10, 10, 30, 10\n    DRAW LINE 30, 10, 30, 20\n"))

    def test_line_leaves_no_rubber_band(self):
        r = run([LINE] + stroke([(10, 10), (200, 150), (90, 40), (300, 20), (60, 30)]), answers=[1])
        self.assertEqual(picture(r), reference("    DRAW LINE 10, 10, 60, 30\n"))

    def test_box_and_filled_box_in_a_shade(self):
        ev = [BOX] + stroke([(100, 100), (20, 20), (40, 30)])
        ev += [FILLED, shade(3)] + stroke([(200, 50), (260, 180), (250, 120)])
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference("    DRAW BOX 40, 30, 61, 71\n    DRAW FILL 200, 50, 51, 71, 3\n"))

    def test_eraser(self):
        ev = [FILLED] + stroke([(0, 0), (99, 49)]) + [ERASER] + stroke([(20, 20), (20, 21)])
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference("    DRAW FILL 0, 0, 100, 50\n    DRAW FILL 16, 16, 8, 8, 8\n"
                                               "    DRAW FILL 16, 17, 8, 8, 8\n"))

    def test_eraser_stays_inside_at_the_edge(self):
        ev = [FILLED] + stroke([(0, 0), (CW - 1, CH - 1)]) + [ERASER] + stroke([(CW - 1, CH - 1)])
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference(f"    DRAW FILL 0, 0, {CW}, {CH}\n"
                                               f"    DRAW FILL {CW - 8}, {CH - 8}, 8, 8, 8\n"))

    def test_drag_outside_the_canvas_is_kept_at_the_edge(self):
        ev = [LINE, ("mdown",) + at(500, 200), ("mmove", SX + 700, SY + 300), ("mup", SX + 700, SY + 300)]
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference(f"    DRAW LINE 500, 200, {CW - 1}, {CH - 1}\n"))

    def test_copy_and_paste(self):
        ev = [FILLED] + stroke([(10, 10), (29, 19)]) + [BOX] + stroke([(5, 5), (40, 30)])
        ev += [SELECT] + stroke([(0, 0), (49, 39)]) + [COPY, PASTE] + stroke([(300, 100)])
        ev += stroke([(530, 230)])  # kept inside: placed at 494, 200
        r = run(ev, answers=[1])
        drawing = "    DRAW FILL 10, 10, 20, 10\n    DRAW BOX 5, 5, 36, 26\n"
        ref = reference(drawing)
        pic = picture(r)
        self.assertEqual(pic[:40], [row[:50] + "." * (CW - 50) for row in ref[:40]])
        self.assertEqual([row[300:350] for row in pic[100:140]], [row[:50] for row in ref[:40]])
        self.assertEqual([row[494:544] for row in pic[200:240]], [row[:50] for row in ref[:40]])
        self.assertEqual(string_var(r, "APPSTATUS$")[:5], "Paste")

    def test_selection_outline_is_not_saved_and_goes_on_undo(self):
        ev = [FILLED] + stroke([(10, 10), (29, 19)]) + [SELECT] + stroke([(0, 0), (49, 39)])
        ev += [SAVEAS, ("edit", FB["FILENAME$"], "SEL"), ("click", FB["Save as"])]
        r = run(ev, answers=[1])
        data = r.cpu.disk.file("SEL.PBI")
        self.assertEqual(pbicheck.check(data)[0], 0)
        ref = reference("    DRAW FILL 10, 10, 20, 10\n")
        self.assertEqual(pbicheck.pixels(data), [[1 if c == "#" else 0 for c in row] for row in ref])
        # the outline is back on the canvas after the Files window
        self.assertEqual(picture(r)[0][:50], "#" * 50)

    def test_clear_and_undo(self):
        ev = [FILLED] + stroke([(10, 10), (29, 19)]) + [CLEAR]
        self.assertEqual(picture(run(ev, answers=[1])), WHITE)
        self.assertEqual(picture(run(ev + [UNDO], answers=[1])), reference("    DRAW FILL 10, 10, 20, 10\n"))

    def test_undo_is_one_step(self):
        ev = stroke([(10, 10), (20, 10)]) + stroke([(10, 20), (20, 20)]) + [UNDO, UNDO]
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference("    DRAW LINE 10, 10, 20, 10\n"))
        self.assertEqual(string_var(r, "APPSTATUS$"), "Nothing to undo")

    def test_keys_choose_tool_and_shade(self):
        r = run([("key", ord("f")), ("key", ord("6"))] + stroke([(0, 0), (9, 9)]), answers=[1])
        self.assertEqual(picture(r), reference("    DRAW FILL 0, 0, 10, 10, 6\n"))
        self.assertEqual(string_var(r, "APPSTATUS$"), "Filled 6 *")

    def test_sample(self):
        r = run([SAMPLE, SAVE])
        self.assertEqual(string_var(r, "APPSTATUS$"), "Pencil 0 HOUSE.PBI")
        data = r.cpu.disk.file("HOUSE.PBI")
        self.assertEqual(pbicheck.check(data)[0], 0)
        self.assertEqual(pbicheck.pixels(data), [[1 if c == "#" else 0 for c in row] for row in picture(r)])
        self.assertTrue(r.cpu.exited)
        # it uses every shade
        self.assertGreater(sum(row.count("#") for row in picture(r)), 5000)


@requires_pasmo
class FileTests(unittest.TestCase):
    def save_as(self, name):
        return [SAVEAS, ("edit", FB["FILENAME$"], name), ("click", FB["Save as"])]

    def open(self, name):
        return [OPEN, ("edit", FB["FILENAME$"], name), ("click", FB["Open"])]

    def test_save_as_then_save_keeps_a_backup(self):
        ev = stroke([(10, 10), (20, 10)]) + self.save_as("art") + stroke([(10, 20), (20, 20)]) + [SAVE]
        r = run(ev)
        files = files_of(r)
        self.assertEqual(sorted(files), ["ART.BAK", "ART.PBI"])
        self.assertEqual(pbicheck.pixels(files["ART.BAK"])[10][10:21], [1] * 11)
        self.assertEqual(pbicheck.pixels(files["ART.BAK"])[20][10:21], [0] * 11)
        self.assertEqual(pbicheck.pixels(files["ART.PBI"])[20][10:21], [1] * 11)
        self.assertTrue(r.cpu.exited)  # saved: Quit asks nothing

    def test_open_a_picture(self):
        rows = [[(x // 4 + y // 4) % 2 for x in range(CW)] for y in range(CH)]
        r = run(stroke([(10, 10), (20, 10)]) + self.open("pic"), files={"PIC.PBI": pbicheck.from_rows(rows)},
                answers=[1])
        self.assertEqual(picture(r), ["".join("#" if v else "." for v in row) for row in rows])
        self.assertEqual(string_var(r, "APPSTATUS$"), "Pencil 0 PIC.PBI")
        self.assertTrue(r.cpu.exited)

    def test_open_a_smaller_picture(self):
        rows = [[1] * 30 for _ in range(20)]
        r = run([FILLED] + stroke([(0, 0), (CW - 1, CH - 1)]) + self.open("SMALL.PBI"),
                files={"SMALL.PBI": pbicheck.from_rows(rows)}, answers=[1])
        self.assertEqual(picture(r), reference("    DRAW FILL 0, 0, 30, 20\n"))
        # drawing on it and saving gives a whole-canvas picture
        r = run(self.open("SMALL.PBI") + stroke([(100, 100)]) + [SAVE], files={"SMALL.PBI": pbicheck.from_rows(rows)})
        code, head = pbicheck.check(r.cpu.disk.file("SMALL.PBI"))
        self.assertEqual((code, head["width"], head["height"]), (0, CW, CH))

    def test_refused_files_leave_the_picture(self):
        good = reference("    DRAW FILL 10, 10, 20, 10\n")
        cases = {
            "BIG.PBI": (pbicheck.from_rows([[1] * 640] * 20), "Not opened: the picture is larger than 544 x 240"),
            "BAD.PBI": (pbicheck.from_rows([[1] * 8] * 8)[:-1], "Not opened: damaged"),
            "DB.PBI": (b"PDB1" + bytes(40), "Not opened: not a picture"),
            "HUGE.PBI": (pbicheck.from_rows([[1] * 600] * 300), "Not opened: too large"),
        }
        for name, (data, alert) in cases.items():
            with self.subTest(name):
                ev = [FILLED] + stroke([(10, 10), (29, 19)]) + self.open(name) + [("click", FB["Back"]), UNDO]
                r = run(ev, files={name: data}, answers=[1])
                self.assertIn(alert, r.alerts)
                self.assertEqual(picture(r), good)
                self.assertEqual(string_var(r, "APPSTATUS$"), "Nothing to undo")

    def test_missing_file(self):
        r = run(self.open("NONE"), answers=[1])
        self.assertIn("Not opened: not found", r.alerts)

    def test_save_failure_is_reported_and_keeps_the_old_file(self):
        old = pbicheck.from_rows([[1, 0]] * 4)
        disk_files = {"ART.PBI": old}
        ev = self.open("ART") + stroke([(10, 10)]) + [SAVE]
        disk = z80sim.Disk(files={(F, n): d for n, d in disk_files.items()}, faults_at={146: {2: 0xA3}})
        r = guarded_run(SRC, events=ev + [QUIT], disk=disk, path=PATH, max_steps=600_000_000,
                        alert_answers=[1], build_options={"runtime_sections": "all"})
        self.assertEqual(r.violations, [])
        self.assertIn("Not saved: disk full", r.alerts)
        self.assertEqual(r.cpu.disk.file("ART.PBI"), old)


@requires_pasmo
class UnsavedChangesTests(unittest.TestCase):
    def test_quit_asks(self):
        ev = stroke([(10, 10)])
        self.assertFalse(run(ev, answers=[2]).cpu.exited)  # Cancel (answers are 0-based)
        self.assertTrue(run(ev, answers=[1]).cpu.exited)  # Discard
        self.assertTrue(run([], answers=[]).cpu.exited)  # nothing changed: no question

    def test_save_from_the_question_without_a_name_opens_files(self):
        r = run(stroke([(10, 10)]), answers=[0])  # Save
        self.assertFalse(r.cpu.exited)
        self.assertEqual(files_of(r), {})

    def test_save_from_the_question_with_a_name(self):
        ev = stroke([(10, 10)]) + [SAVEAS, ("edit", FB["FILENAME$"], "A"), ("click", FB["Save as"])]
        ev += stroke([(20, 20)])
        r = run(ev, answers=[0])  # Save
        self.assertTrue(r.cpu.exited)
        self.assertEqual(pbicheck.pixels(r.cpu.disk.file("A.PBI"))[20][20], 1)

    def test_new_asks_and_clears(self):
        r = run(stroke([(10, 10)]) + [NEW], answers=[1, 1])
        self.assertEqual(picture(r), WHITE)

    def test_drawing_menus_in_the_files_window_go_back(self):
        # Clear, Copy and Sample draw: chosen in the Files window they only go
        # back to the picture; Undo needs no canvas and is shown on return
        ev = stroke([(10, 10)]) + [OPEN, CLEAR, OPEN, COPY, OPEN, SAMPLE]
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference("    DRAW PIXEL 10, 10\n"))
        r = run(stroke([(10, 10)]) + [OPEN, UNDO, ("click", FB["Back"])], answers=[1])
        self.assertEqual(picture(r), WHITE)


@requires_pasmo
class BuildTests(unittest.TestCase):
    def test_spans_code_banks(self):
        # M12: PAINT's code is in its resident block, a procedure bank and
        # the runtime bank (docs/M12-ARCHITECTURE.md, memory report)
        import tempfile
        from pbas.prg import build
        with tempfile.TemporaryDirectory() as tmp:
            report = build(PATH, Path(tmp) / "p.asm", Path(tmp) / "p.prg", runtime_sections="all")
        layout = report.banked
        self.assertIsNotNone(layout)
        self.assertGreaterEqual(len([b for b in layout.banks if b.procedures]), 1)
        self.assertIn("BITMAP", layout.runtime_sections)
        self.assertLessEqual(layout.resident_size, 16384)


if __name__ == "__main__":
    unittest.main()
