"""PAINT II (examples/paint2.pbas, M13 Stage F) on the simulator.

Whole sessions are driven with raw mouse events on the icon palette, the
swatches and the picture, keys and menu choices. The picture is compared
pixel for pixel with what the drawing statements produce on their own (a
reference program with a canvas in the same place), so that a rubber band
left behind, a selection that moves the wrong pixels, or an undo that
restores the wrong picture shows. The palette is compared with the icon
strip made from examples/assets/paint2-icons.png by tools/pbimage.py, as
the build makes it. Saved pictures are read with tools/pbicheck.py.
Simulator evidence only: the owner's XAnne session is docs/M13-ACCEPTANCE.md,
Session B.
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
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
import pbimage  # noqa: E402

PATH = ROOT / "examples" / "paint2.pbas"
SRC = PATH.read_text(encoding="utf-8")
F = "\\PCW\\FOLDER01"
CW, CH, TOP = 544, 240, 30

NEW, OPEN, SAVE, SAVEAS, IMPORT, QUIT = (("menu", 1, i) for i in range(6))
UNDO, REDO, CUT, COPY, PASTE, DELETE, CLEAR = (("menu", 2, i) for i in range(7))
PENCIL, LINE, BOX, FILLED, ERASER, SELECT = range(1, 7)
KC_UP, KC_DOWN, KC_LEFT, KC_RIGHT, KC_DELETE, KC_STOP = 224, 225, 226, 227, 229, 254


def icon_strip() -> bytes:
    """P2ICONS.PBI as the build makes it from the PNG source (examples/assets/ASSETS.txt)."""
    with tempfile.TemporaryDirectory(prefix="pbw16-p2-") as tmp:
        with contextlib.redirect_stdout(io.StringIO()):
            assert pbimage.main(["build", str(ROOT / "examples" / "assets" / "ASSETS.txt"), tmp]) == 0
        return (Path(tmp) / "P2ICONS.PBI").read_bytes()


ICONS = icon_strip()


def layout():
    program = check_source(SRC, path=PATH)
    main = build_dialog(program, program.windows[0], True)
    files = build_dialog(program, program.windows[1], True)
    buttons = {o.text: o.number for o in files.objects if o.kind == "BUTTON"}
    buttons.update({row.var_name: row.number for row in files.bindings})
    return main.canvas[1], main.canvas[2], buttons


SX, SY, FB = layout()


def at(x, y):
    """A point of the picture on the screen."""
    return SX + x, SY + TOP + y


def tool(n):
    """A click on tool icon n (1..6)."""
    x, y = SX + 4 + (n - 1) * 26 + 12, SY + 2 + 12
    return [("mdown", x, y), ("mup", x, y)]


def shade(s):
    x, y = SX + 184 + s * 20 + 8, SY + 6 + 8
    return [("mdown", x, y), ("mup", x, y)]


def stroke(points):
    (x, y), rest = points[0], points[1:]
    ev = [("mdown",) + at(x, y)]
    ev += [("mmove",) + at(px, py) for px, py in rest]
    return ev + [("mup",) + at(*points[-1])]


def run(events, files=None, answers=None, quit=True, icons=True, banks="all"):
    disk_files = dict(files or {})
    if icons:
        disk_files.setdefault("P2ICONS.PBI", ICONS)
    disk = z80sim.Disk(files={(F, n): d for n, d in disk_files.items()})
    tail = [QUIT] if quit else []
    r = guarded_run(SRC, events=events + tail, disk=disk, path=PATH, max_steps=900_000_000,
                    alert_answers=answers, build_options={"runtime_sections": banks} if banks else None)
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r


def picture(r):
    return r.cpu.canvas_pixels(SX, SY + TOP, CW, CH)


def palette(r):
    return r.cpu.canvas_pixels(SX, SY, CW, TOP)


_REFS: dict[str, list[str]] = {}


def reference(*ops) -> list[str]:
    """The picture after *ops* on white: ("FILL", x, y, w, h[, shade]),
    ("BOX"|"LINE"|"PIXEL", ...) in picture coordinates."""
    drawing = ""
    for op, *a in ops:
        if op in ("FILL", "BOX"):
            a[1] += TOP
        elif op == "LINE":
            a[1] += TOP
            a[3] += TOP
        elif op == "PIXEL":
            a[1] += TOP
        elif op == "INK":
            drawing += f"    DRAW INK {a[0]}\n"
            continue
        drawing += f"    DRAW {op} " + ", ".join(map(str, a)) + "\n"
    if drawing not in _REFS:
        src = (f'WINDOW W, "R", LARGE\nCANVAS {CW}, {CH + TOP}, PAINT P\nBUTTON "Q", Q\n'
               f"SUB P\n    DRAW CLEAR\n{drawing}END SUB\nSUB Q\n    EXIT\nEND SUB\nEND\n")
        program = check_source(src)
        lay = build_dialog(program, program.windows[0], False)
        assert (lay.canvas[1], lay.canvas[2]) == (SX, SY), "the reference canvas must be in the same place"
        r = guarded_run(src, events=[])
        assert r.violations == [] and not r.alerts, (r.violations, r.alerts)
        _REFS[drawing] = r.cpu.canvas_pixels(SX, SY + TOP, CW, CH)
    return _REFS[drawing]


WHITE = ["." * CW] * CH


def status(r):
    return string_var(r, "APPSTATUS$")


@requires_pasmo
class PaletteTests(unittest.TestCase):
    def strip_rows(self):
        return pbicheck.pixels(ICONS)

    def test_icons_drawn_from_the_imported_strip(self):
        r = run([])
        pal = palette(r)
        strip = self.strip_rows()
        for k in range(6):
            x0 = 4 + k * 26
            got = [[1 if c == "#" else 0 for c in row[x0:x0 + 24]] for row in pal[2:26]]
            want = strip[k * 24:(k + 1) * 24]
            if k == 0:  # the pencil is chosen: inverted
                want = [[1 - p for p in row] for row in want]
            self.assertEqual(got, want, k)
        self.assertEqual(status(r), "Pencil 0 ")

    def test_clicking_icons_and_swatches(self):
        ev = tool(FILLED) + shade(3) + stroke([(10, 10), (59, 39)])
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference(("FILL", 10, 10, 50, 30, 3)))
        strip = self.strip_rows()
        pal = palette(r)
        x0 = 4 + 3 * 26
        self.assertEqual([[1 if c == "#" else 0 for c in row[x0:x0 + 24]] for row in pal[2:26]],
                         [[1 - p for p in row] for row in strip[72:96]])  # Filled is inverted now
        x0 = 4
        self.assertEqual([[1 if c == "#" else 0 for c in row[x0:x0 + 24]] for row in pal[2:26]],
                         strip[0:24])  # the pencil is not
        self.assertEqual(status(r)[:9], "Filled 3 ")
        # the chosen swatch has a double frame: its outer frame is black
        self.assertEqual(pal[4][184 + 3 * 20 - 2], "#")
        self.assertEqual(pal[4][184 + 2 * 20 - 2], ".")

    def test_without_the_icon_file_letters(self):
        r = run(tool(LINE) + stroke([(10, 10), (100, 50)]), icons=False, answers=[1])
        self.assertEqual(picture(r), reference(("LINE", 10, 10, 100, 50)))
        pal = palette(r)
        self.assertEqual(pal[2][4:28], "#" * 24)  # a frame, not the icon
        self.assertEqual(r.alerts, [a for a in r.alerts if not a.startswith("Runtime")])

    def test_keys_choose_tool_and_shade(self):
        r = run([("key", ord("f")), ("key", ord("6"))] + stroke([(0, 0), (9, 9)]), answers=[1])
        self.assertEqual(picture(r), reference(("FILL", 0, 0, 10, 10, 6)))
        self.assertEqual(status(r), "Filled 6 *")


@requires_pasmo
class DrawingTests(unittest.TestCase):
    def test_pencil_undo_redo(self):
        line = stroke([(10, 10), (30, 10), (30, 20)])
        want = reference(("LINE", 10, 10, 30, 10), ("LINE", 30, 10, 30, 20))
        self.assertEqual(picture(run(line, answers=[1])), want)
        self.assertEqual(picture(run(line + [UNDO], answers=[1])), WHITE)
        self.assertEqual(picture(run(line + [UNDO, REDO], answers=[1])), want)

    def test_white_pencil_on_black(self):
        ev = tool(FILLED) + stroke([(0, 0), (99, 49)]) + tool(PENCIL) + shade(8) + stroke([(10, 10), (40, 10)])
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference(("FILL", 0, 0, 100, 50), ("INK", "WHITE"),
                                               ("LINE", 10, 10, 40, 10), ("INK", "BLACK")))

    def test_bands_leave_nothing_behind(self):
        ev = tool(BOX) + stroke([(100, 100), (20, 20), (300, 200), (40, 30)])
        ev += tool(LINE) + stroke([(200, 10), (500, 230), (220, 40)])
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference(("BOX", 40, 30, 61, 71), ("LINE", 200, 10, 220, 40)))

    def test_a_drag_into_the_palette_stays_in_the_picture(self):
        ev = tool(LINE) + [("mdown",) + at(100, 100), ("mmove", SX + 50, SY + 5), ("mup", SX + 50, SY + 5)]
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference(("LINE", 100, 100, 50, 0)))

    def test_stop_cancels_a_band(self):
        ev = tool(BOX) + [("mdown",) + at(10, 10), ("mmove",) + at(80, 60), ("key", KC_STOP),
                          ("mup",) + at(80, 60)]
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), WHITE)

    def test_eraser(self):
        ev = tool(FILLED) + stroke([(0, 0), (99, 49)]) + tool(ERASER) + stroke([(20, 20), (20, 21)])
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference(("FILL", 0, 0, 100, 50), ("FILL", 16, 16, 8, 8, 8),
                                               ("FILL", 16, 17, 8, 8, 8)))


@requires_pasmo
class SelectionTests(unittest.TestCase):
    BOXES = [("FILL", 10, 10, 20, 10), ("BOX", 5, 5, 36, 26)]

    def setup(self):
        return tool(FILLED) + stroke([(10, 10), (29, 19)]) + tool(BOX) + stroke([(5, 5), (40, 30)])

    def moved(self, dx, dy):
        """The two boxes moved by dx, dy (as a selection 0, 0, 50, 40)."""
        return [("FILL", 10 + dx, 10 + dy, 20, 10), ("BOX", 5 + dx, 5 + dy, 36, 26)]

    def test_drag_a_selection(self):
        ev = self.setup() + tool(SELECT) + stroke([(0, 0), (49, 39)])
        ev += stroke([(20, 20), (60, 40), (220, 120)])  # inside: moves by 200, 100
        r = run(ev + stroke([(400, 200)]), answers=[1])  # a click outside puts it down
        self.assertEqual(picture(r), reference(*self.moved(200, 100)))
        # the outline is gone, and one Undo puts the boxes back
        r = run(ev + stroke([(400, 200)]) + [UNDO], answers=[1])
        self.assertEqual(picture(r), reference(*self.BOXES))

    def drag_moves(self, n):
        """The selection 0, 0, 50, 40 pressed at 20, 20 and dragged n times, 7 pixels a time."""
        return ([("mdown",) + at(20, 20)]
                + [("mmove",) + at(20 + 7 * (i + 1), 20 + i + 1) for i in range(n)])

    def test_a_dragged_selection_shows_a_ghost_and_moves_on_the_release(self):
        """M13 responsiveness: while it is dragged only an XOR outline follows
        the pointer (as in DESIGNER); the pixels move once, on the release,
        to the same place as when they followed every movement."""
        ev = self.setup() + tool(SELECT) + stroke([(0, 0), (49, 39)]) + self.drag_moves(10)
        r = run(ev, quit=False, answers=[1])
        ghost = reference(*self.BOXES, ("INK", "XOR"), ("BOX", 0, 0, 50, 40), ("BOX", 70, 10, 50, 40),
                          ("INK", "BLACK"))
        self.assertEqual(picture(r), ghost)
        r = run(ev + [("mup",) + at(90, 30)] + stroke([(400, 200)]), answers=[1])
        self.assertEqual(picture(r), reference(*self.moved(70, 10)))
        # back where it started: no ghost, the selection left as it was
        r = run(ev + [("mmove",) + at(20, 20)], quit=False, answers=[1])
        self.assertEqual(picture(r), reference(*self.BOXES, ("INK", "XOR"), ("BOX", 0, 0, 50, 40),
                                               ("INK", "BLACK")))

    def test_dragging_a_selection_draws_two_outlines_a_movement(self):
        """M13 responsiveness (owner, XAnne: PAINT II's drag lagged and
        flickered): each movement put back the picture under the selection
        and drew the selection again, 2 x its area in bitmap pixels (a
        200 x 120 selection: 48,000 pixels in 19 BIOS bitmap calls a
        movement). Now a movement erases and draws the ghost: no bitmaps."""
        base = self.setup() + tool(SELECT) + stroke([(0, 0), (49, 39)])
        before = run(base + self.drag_moves(0), quit=False, answers=[1]).cpu
        after = run(base + self.drag_moves(10), quit=False, answers=[1]).cpu
        self.assertEqual(len(after.bitmap_log), len(before.bitmap_log))
        self.assertLessEqual(len(after.draw_log) - len(before.draw_log), 2 * 10)

    def test_undo_during_a_drag_ends_it(self):
        ev = self.setup() + tool(SELECT) + stroke([(0, 0), (49, 39)]) + self.drag_moves(3)
        ev += [UNDO, ("mmove",) + at(200, 100), ("mup",) + at(200, 100)]
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference(*self.BOXES))

    def test_floating_selection_shows_its_outline_and_undo_puts_it_back(self):
        ev = self.setup() + tool(SELECT) + stroke([(0, 0), (49, 39)]) + stroke([(20, 20), (120, 70)])
        r = run(ev, answers=[1])
        pic = picture(r)
        self.assertEqual(pic[50][100:150], "#" * 50)  # the XOR outline on white, at 100, 50
        r = run(ev + [UNDO], answers=[1])
        self.assertEqual(picture(r), reference(*self.BOXES))
        r = run(ev + [UNDO, REDO], answers=[1])
        self.assertEqual(picture(r), reference(*self.moved(100, 50)))

    def test_a_selection_is_kept_inside_the_picture(self):
        ev = self.setup() + tool(SELECT) + stroke([(0, 0), (49, 39)])
        ev += stroke([(10, 10), (900 - SX, 900)])
        r = run(ev + tool(PENCIL), answers=[1])  # another tool puts it down
        self.assertEqual(picture(r), reference(*self.moved(CW - 50, CH - 40)))

    def test_nudge_with_the_cursor_keys(self):
        ev = self.setup() + tool(SELECT) + stroke([(0, 0), (49, 39)])
        ev += [("key", KC_RIGHT)] * 3 + [("key", KC_DOWN)] * 2 + [("key", KC_UP), ("key", KC_LEFT)]
        r = run(ev + tool(PENCIL), answers=[1])
        self.assertEqual(picture(r), reference(*self.moved(2, 1)))

    def test_delete(self):
        ev = self.setup() + tool(SELECT) + stroke([(0, 0), (20, 39)]) + [("key", KC_DELETE)]
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference(*self.BOXES, ("FILL", 0, 0, 21, 40, 8)))
        r = run(ev + [UNDO], answers=[1])
        self.assertEqual(picture(r), reference(*self.BOXES))

    def test_delete_a_moved_selection(self):
        ev = self.setup() + tool(SELECT) + stroke([(0, 0), (49, 39)]) + stroke([(20, 20), (220, 20)])
        r = run(ev + [DELETE], answers=[1])
        self.assertEqual(picture(r), WHITE)

    def test_cut_and_paste_floats_at_the_top_left(self):
        ev = self.setup() + tool(SELECT) + stroke([(0, 0), (49, 39)]) + [CUT]
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), WHITE)
        ev += [PASTE] + stroke([(10, 10), (310, 110)]) + stroke([(500, 200)])
        r = run(ev, answers=[1])
        self.assertEqual(picture(r), reference(*self.moved(300, 100)))

    def test_copy_paste_over_a_picture(self):
        ev = self.setup() + tool(SELECT) + stroke([(0, 0), (49, 39)]) + [COPY]
        ev += tool(FILLED) + stroke([(200, 100), (299, 199)])
        ev += [PASTE] + stroke([(5, 5), (225, 125)]) + tool(PENCIL)  # opaque: covers the black
        r = run(ev, answers=[1])
        want = reference(*self.BOXES, ("FILL", 200, 100, 100, 100), ("FILL", 220, 120, 50, 40, 8),
                         *self.moved(220, 120))
        self.assertEqual(picture(r), want)

    def test_a_click_is_no_selection(self):
        r = run(self.setup() + tool(SELECT) + stroke([(100, 100)]) + [("key", KC_DELETE)], answers=[1])
        self.assertEqual(picture(r), reference(*self.BOXES))


@requires_pasmo
class FileTests(unittest.TestCase):
    def files(self, name, button):
        return [OPEN, ("edit", FB["FILENAME$"], name), ("click", FB[button])]

    def test_save_open_and_backup(self):
        ev = stroke([(10, 10), (20, 10)]) + self.files("art", "Save as") + stroke([(10, 20), (20, 20)]) + [SAVE]
        r = run(ev)
        self.assertTrue(r.cpu.exited)
        files = {n: d for (f, n), d in r.cpu.disk.files.items() if f == F}
        self.assertEqual(pbicheck.pixels(files["ART.BAK"])[20][10:21], [0] * 11)
        self.assertEqual(pbicheck.pixels(files["ART.PBI"])[20][10:21], [1] * 11)
        self.assertEqual(pbicheck.pixels(files["ART.PBI"]),
                         [[1 if c == "#" else 0 for c in row] for row in picture(r)])

    def test_open_a_paint_picture(self):
        rows = [[(x // 4 + y // 4) % 2 for x in range(CW)] for y in range(CH)]
        r = run(self.files("pic", "Open"), files={"PIC.PBI": pbicheck.from_rows(rows)})
        self.assertEqual(picture(r), ["".join("#" if v else "." for v in row) for row in rows])
        self.assertEqual(status(r), "Pencil 0 PIC.PBI")

    def test_saving_puts_down_a_floating_selection(self):
        ev = tool(FILLED) + stroke([(10, 10), (29, 19)]) + tool(SELECT) + stroke([(0, 0), (39, 29)])
        ev += stroke([(15, 15), (115, 15)]) + [SAVE, ("edit", FB["FILENAME$"], "M"), ("click", FB["Save as"])]
        r = run(ev)
        self.assertTrue(r.cpu.exited)
        want = reference(("FILL", 110, 10, 20, 10))
        self.assertEqual(pbicheck.pixels(r.cpu.disk.file("M.PBI")), [[1 if c == "#" else 0 for c in row] for row in want])
        self.assertEqual(picture(r), want)

    def test_import_floats_a_picture(self):
        rows = [[1] * 30 for _ in range(20)]
        ev = tool(BOX) + stroke([(100, 100), (199, 149)])
        ev += self.files("STAMP", "Import") + stroke([(5, 5), (125, 115)]) + stroke([(400, 10)])
        r = run(ev, files={"STAMP.PBI": pbicheck.from_rows(rows)}, answers=[1])
        self.assertEqual(picture(r), reference(("BOX", 100, 100, 100, 50), ("FILL", 120, 110, 30, 20)))
        r = run(ev + [UNDO], files={"STAMP.PBI": pbicheck.from_rows(rows)}, answers=[1])
        self.assertEqual(picture(r), reference(("BOX", 100, 100, 100, 50)))

    def test_refused_imports(self):
        cases = {
            "WIDE.PBI": (pbicheck.from_rows([[1] * 560] * 10), "Not imported: the picture is larger than 544 x 240"),
            "DB.PBI": (b"PDB1" + bytes(40), "Not imported: not a picture"),
        }
        for name, (data, alert) in cases.items():
            with self.subTest(name):
                ev = tool(FILLED) + stroke([(10, 10), (29, 19)]) + self.files(name, "Import")
                ev += [("click", FB["Back"])]
                r = run(ev, files={name: data}, answers=[1])
                self.assertIn(alert, r.alerts)
                self.assertEqual(picture(r), reference(("FILL", 10, 10, 20, 10)))

    def test_unsaved_changes_are_asked_about(self):
        self.assertFalse(run(stroke([(10, 10)]), answers=[2]).cpu.exited)
        self.assertTrue(run(stroke([(10, 10)]), answers=[1]).cpu.exited)
        self.assertTrue(run([]).cpu.exited)


@requires_pasmo
class BuildTests(unittest.TestCase):
    def test_the_m12_paint_is_untouched(self):
        # Paint II is a new program: PAINT's source is still the accepted one
        self.assertIn("PAINT (M12 Stage B)", (ROOT / "examples" / "paint.pbas").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
