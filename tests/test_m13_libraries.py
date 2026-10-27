"""M13 Stage B/D: the graphical libraries in examples/lib (docs/M13-LIBRARIES.md).

Each library is INCLUDEd by a small program of this test's own, as any
program would use it, and run on the simulator: geometry by its answers,
dragging and handles by the canvas after real press / drag / release
events (XOR feedback must leave the canvas exactly as it was), the toolbar
with an icon strip loaded from a PBI1 file, sprites by their pixels against
a model of the clipped, masked drawing, scenes by their stacking order.
"""
from __future__ import annotations

import shutil
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

F = "\\PCW\\FOLDER01"


def build_run(src: str, events_fn, files=None, banks="all"):
    """*events_fn*(canvas x, canvas y, button numbers) -> the event script."""
    with tempfile.TemporaryDirectory(prefix="pbw16-lib-") as tmp:
        shutil.copytree(ROOT / "examples" / "lib", Path(tmp) / "lib")
        path = Path(tmp) / "t.pbas"
        path.write_text(src, encoding="utf-8")
        prog = check_source(src, path=path)
        lay = build_dialog(prog, prog.windows[0], False)
        buttons = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
        cx, cy = lay.canvas[1], lay.canvas[2]
        disk = z80sim.Disk(files={(F, n): d for n, d in (files or {}).items()})
        r = guarded_run(src, path=path, events=events_fn(cx, cy, buttons), disk=disk, max_steps=900_000_000,
                        build_options={"runtime_sections": banks} if banks else None)
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    r.cx, r.cy = cx, cy
    r.px = lambda x, y: r.cpu.pixel(cx + x, cy + y)
    return r


def app(includes, body, mouse="", dims="", w=500, h=200):
    inc = "".join(f'INCLUDE "lib/{n}.pbas"\n' for n in includes)
    return (f"{inc}DIM Out$ AS STRING * 120\n{dims}WINDOW W, \"T\", LARGE\n"
            f"CANVAS {w}, {h}, PAINT P, MOUSE M\nBUTTON \"Go\", Go\n"
            "SUB P\n    DRAW CLEAR\nEND SUB\n"
            f"SUB M\n{mouse}END SUB\n"
            f"SUB Go\n    LOCAL I AS INTEGER\n{body}END SUB\nEND\n")


@requires_pasmo
class GeomTests(unittest.TestCase):
    def test_answers(self):
        body = """    Out$ = ""
    IF GeomIn(4, 4, 0, 0, 5, 5) THEN
        Out$ = Out$ + "a"
    END IF
    IF NOT GeomIn(5, 4, 0, 0, 5, 5) THEN
        Out$ = Out$ + "b"
    END IF
    IF GeomMeets(0, 0, 10, 10, 9, 9, 5, 5) THEN
        Out$ = Out$ + "c"
    END IF
    B1 = GeomMeets(0, 0, 10, 10, 10, 0, 5, 5)
    B2 = GeomMeets(0, 0, 0, 10, 0, 0, 5, 5)
    IF NOT B1 AND NOT B2 THEN
        Out$ = Out$ + "d"
    END IF
    B1 = GeomMeets(10, 0, 5, 5, 0, 0, 10, 10)
    B2 = GeomMeets(0, 10, 5, 5, 0, 0, 10, 10)
    IF NOT B1 AND NOT B2 AND NOT GeomMeets(0, 0, 10, 10, 0, 10, 5, 5) THEN
        Out$ = Out$ + "e"
    END IF
    Out$ = Out$ + STR$(GeomClamp(-3, 0, 9)) + STR$(GeomClamp(12, 0, 9)) + STR$(GeomClamp(4, 0, 9))
    CALL GeomSpan(7, 2, 3, 9)
    Out$ = Out$ + "|" + STR$(GeomX) + "," + STR$(GeomY) + "," + STR$(GeomW) + "," + STR$(GeomH)
    CALL GeomClip(-3, 5, 10, 10, 0, 0, 100, 8)
    Out$ = Out$ + "|" + STR$(GeomX) + "," + STR$(GeomY) + "," + STR$(GeomW) + "," + STR$(GeomH)
    Out$ = Out$ + "," + STR$(GeomDX) + "," + STR$(GeomDY)
    CALL GeomClip(200, 5, 10, 10, 0, 0, 100, 8)
    Out$ = Out$ + "|" + STR$(GeomW)
    CALL GeomUnite(0, 0, 0, 0, 5, 6, 2, 2)
    Out$ = Out$ + "|" + STR$(GeomX) + "," + STR$(GeomW)
    CALL GeomUnite(1, 1, 2, 2, 5, 6, 2, 2)
    Out$ = Out$ + "|" + STR$(GeomX) + "," + STR$(GeomY) + "," + STR$(GeomW) + "," + STR$(GeomH)
"""
        r = build_run(app(["geom"], body, dims="DIM B1 AS BOOLEAN\nDIM B2 AS BOOLEAN\n"), lambda cx, cy, b: [("click", b["Go"])])
        self.assertEqual(string_var(r, "OUT$"), "abcde094|3,2,5,8|0,5,7,3,3,0|0|5,2|1,1,6,7")


@requires_pasmo
class DragTests(unittest.TestCase):
    MOUSE = """    CALL DragMouse
    IF DragEvent = 2 THEN
        IF Mode = 1 THEN
            CALL DragShowBox
        ELSE
            CALL DragShowLine
        END IF
    END IF
    IF DragEvent = 3 THEN
        CALL DragHide
        Out$ = STR$(DragX0) + "," + STR$(DragY0) + "," + STR$(DragX) + "," + STR$(DragY) + "," + STR$(DragDX)
        IF DragMoved THEN
            Out$ = Out$ + " moved"
        END IF
        IF DragEnded THEN
            Out$ = Out$ + " ended"
        END IF
    END IF
    IF DragEvent = 2 AND DragX > 300 THEN
        CALL DragCancel
        Out$ = "cancelled"
    END IF
"""
    DIMS = "DIM Mode AS INTEGER\n"
    BODY = "    Mode = 1\n"

    def run_drag(self, path, mode=1, extra=""):
        src = app(["drag"], self.BODY.replace("1", str(mode)), self.MOUSE, self.DIMS)
        src = src.replace("SUB P\n    DRAW CLEAR\n", "SUB P\n    DRAW CLEAR\n    DragW = 500\n    DragH = 200\n"
                          "    DRAW FILL 20, 20, 200, 100, 4\n")

        def events(cx, cy, b):
            (x, y), rest = path[0], path[1:]
            ev = [("click", b["Go"]), ("mdown", cx + x, cy + y)]
            ev += [("mmove", cx + px, cy + py) for px, py in rest]
            return ev + [("mup", cx + path[-1][0], cy + path[-1][1])]
        return build_run(src, events)

    def background(self, r):
        for y in range(0, 200, 3):
            for x in range(0, 500, 3):
                inside = 20 <= x < 220 and 20 <= y < 120
                if not inside:
                    self.assertEqual(r.px(x, y), 0, (x, y))
        return r.cpu.canvas_pixels(r.cx, r.cy, 500, 200)

    def test_a_box_drag_leaves_the_canvas_as_it_was(self):
        ref = build_run(app(["drag"], self.BODY, self.MOUSE, self.DIMS).replace(
            "SUB P\n    DRAW CLEAR\n", "SUB P\n    DRAW CLEAR\n    DragW = 500\n    DragH = 200\n"
            "    DRAW FILL 20, 20, 200, 100, 4\n"), lambda cx, cy, b: [("click", b["Go"])])
        want = ref.cpu.canvas_pixels(ref.cx, ref.cy, 500, 200)
        for mode in (1, 2):
            with self.subTest(mode=mode):
                r = self.run_drag([(50, 40), (90, 60), (140, 110), (120, 30)], mode)
                self.assertEqual(r.cpu.canvas_pixels(r.cx, r.cy, 500, 200), want)
                self.assertEqual(string_var(r, "OUT$"), "50,40,120,30,70 moved ended")

    def test_a_click_is_not_a_move_and_the_pointer_is_kept_inside(self):
        r = self.run_drag([(10, 10), (11, 11)])
        self.assertEqual(string_var(r, "OUT$"), "10,10,11,11,1 ended")
        r = self.run_drag([(10, 10), (-40, 250)])
        self.assertEqual(string_var(r, "OUT$"), "10,10,0,199,-10 moved ended")

    def test_cancel_ignores_the_release(self):
        r = self.run_drag([(50, 40), (200, 60), (320, 70), (330, 80)])
        self.assertEqual(string_var(r, "OUT$"), "cancelled")


@requires_pasmo
class HandleTests(unittest.TestCase):
    def test_show_hide_at_and_resize(self):
        body = """    DRAW FILL 100, 50, 80, 40, 3
    CALL HandlesShow(100, 50, 80, 40)
    Out$ = STR$(HandleAt(100, 50, 100, 50, 80, 40)) + STR$(HandleAt(140, 51, 100, 50, 80, 40))
    Out$ = Out$ + STR$(HandleAt(181, 89, 100, 50, 80, 40)) + STR$(HandleAt(140, 70, 100, 50, 80, 40))
    Out$ = Out$ + STR$(HandleAt(98, 71, 100, 50, 80, 40))
    CALL HandleResize(5, 10, 5, 100, 50, 80, 40, 8, 8)
    Out$ = Out$ + "|" + STR$(HandX) + "," + STR$(HandY) + "," + STR$(HandW) + "," + STR$(HandH)
    CALL HandleResize(1, 100, 100, 100, 50, 80, 40, 8, 8)
    Out$ = Out$ + "|" + STR$(HandX) + "," + STR$(HandY) + "," + STR$(HandW) + "," + STR$(HandH)
    CALL HandleResize(2, 7, -10, 100, 50, 80, 40, 8, 8)
    Out$ = Out$ + "|" + STR$(HandX) + "," + STR$(HandY) + "," + STR$(HandW) + "," + STR$(HandH)
    CALL HandlesShow(0, 0, 499, 199)
    CALL HandlesHide
    CALL HandlesShow(100, 50, 80, 40)
    CALL HandlesHide
"""
        src = app(["handles"], body).replace("SUB P\n    DRAW CLEAR\n", "SUB P\n    DRAW CLEAR\n    HandleCW = 500\n"
                                             "    HandleCH = 200\n")
        r = build_run(src, lambda cx, cy, b: [("click", b["Go"])])
        self.assertEqual(string_var(r, "OUT$"), "12508|100,50,90,45|172,82,8,8|100,40,80,50")
        ref = build_run(app([], "    DRAW FILL 100, 50, 80, 40, 3\n").replace("SUB P", "SUB P"),
                        lambda cx, cy, b: [("click", b["Go"])])
        self.assertEqual(r.cpu.canvas_pixels(r.cx, r.cy, 500, 200), ref.cpu.canvas_pixels(ref.cx, ref.cy, 500, 200))


def icon_strip(n=6, s=16):
    """n icons of s x s, icon k: a frame and k + 1 diagonal steps (1 = black)."""
    rows = []
    for k in range(n):
        for y in range(s):
            rows.append([1 if x in (0, s - 1) or y in (0, s - 1) or (x == y and x <= 2 * (k + 1)) else 0
                         for x in range(s)])
    return rows


@requires_pasmo
class ToolbarTests(unittest.TestCase):
    SETUP = """    BITMAP LOAD Icons, "ICONS.PBI"
    ToolN = 6
    ToolSize = 16
    ToolX = 10
    ToolY = 10
    ToolAcross = 2
    ToolSel = 1
    ToolOff(5) = TRUE
    ToolKey(3) = 108
    SwatchN = 9
    SwatchSize = 12
    SwatchX = 100
    SwatchY = 12
    SwatchSel = 1
"""

    def run_bar(self, body):
        src = app(["toolbar"], self.SETUP + "    CALL ToolPaint(Icons)\n    CALL SwatchPaint\n" + body,
                  dims="DIM Icons AS BITMAP * 16, 96\n")
        return build_run(src, lambda cx, cy, b: [("click", b["Go"])],
                         files={"ICONS.PBI": pbicheck.from_rows(icon_strip())})

    def icon_at(self, r, k):
        col, row = (k - 1) % 2, (k - 1) // 2
        x0, y0 = 10 + col * 18, 10 + row * 18
        return [[r.px(x0 + x, y0 + y) for x in range(16)] for y in range(16)]

    def test_icons_from_the_strip_the_selection_inverted(self):
        r = self.run_bar("    Out$ = STR$(ToolAt(12, 12)) + STR$(ToolAt(30, 12)) + STR$(ToolAt(27, 12))\n"
                         "    Out$ = Out$ + STR$(ToolAt(12, 48)) + STR$(ToolAt(30, 48)) + STR$(ToolForKey(108))\n"
                         "    Out$ = Out$ + STR$(ToolForKey(0)) + STR$(SwatchAt(101, 13)) + STR$(SwatchAt(118, 13))\n")
        strip = icon_strip()
        for k in range(1, 7):
            want = strip[16 * (k - 1):16 * k]
            got = self.icon_at(r, k)
            if k == 1:
                self.assertEqual(got, [[1 - p for p in row] for row in want])  # selected: inverted
            elif k == 5:
                self.assertNotEqual(got, want)  # greyed
                self.assertTrue(all(got[y][x] <= want[y][x] for y in range(16) for x in range(16)))  # only whitened
            else:
                self.assertEqual(got, want, k)
        self.assertEqual(string_var(r, "OUT$"), "120063012")  # 18px pitch: 27 is a gap; icon 5 disabled

    def test_picking_redraws_both(self):
        r = self.run_bar("    CALL ToolPick(Icons, 4)\n    CALL ToolPick(Icons, 5)\n    CALL SwatchPick(5)\n"
                         "    Out$ = STR$(ToolSel) + STR$(SwatchSel)\n")
        strip = icon_strip()
        self.assertEqual(self.icon_at(r, 1), strip[0:16])
        self.assertEqual(self.icon_at(r, 4), [[1 - p for p in row] for row in strip[48:64]])
        self.assertEqual(string_var(r, "OUT$"), "45")  # a disabled icon is not picked
        # swatch 5 (shade 4) has a frame 2 pixels out; swatch 1 lost its frame
        x5 = 100 + 4 * 16
        self.assertEqual(r.px(x5 - 2, 10), 1)
        self.assertEqual(r.px(98, 10), 0)


def sprite_strip():
    """2 frames of 12 x 10: a filled oblong with a hole, frame 1 shifted."""
    img, mask = [], []
    for f in range(2):
        for y in range(10):
            img.append([1 if (x + y + f) % 3 else 0 for x in range(12)])
            mask.append([0 if 2 <= x < 10 and (y != 5 or x < 5) else 1 for x in range(12)])  # 0 = white = drawn
    return img, mask


@requires_pasmo
class SpriteTests(unittest.TestCase):
    """The play area is 200 x 100; the background a shade-3 pattern kept in Back."""

    SETUP = """    BITMAP LOAD Sheet, "HERO.PBI"
    BITMAP LOAD Mask, "HEROM.PBI"
    SprCW = 200
    SprCH = 100
    DRAW FILL 0, 0, 200, 100, 3
    BITMAP GET Back, 0, 0, 200, 100
"""
    DIMS = "DIM Sheet AS BITMAP * 12, 20\nDIM Mask AS BITMAP * 12, 20\nDIM Back AS BITMAP * 200, 100\nDIM B1 AS BOOLEAN\nDIM B2 AS BOOLEAN\n"

    def run_spr(self, body):
        img, mask = sprite_strip()
        src = app(["sprite"], self.SETUP + body, dims=self.DIMS)
        return build_run(src, lambda cx, cy, b: [("click", b["Go"])],
                         files={"HERO.PBI": pbicheck.from_rows(img), "HEROM.PBI": pbicheck.from_rows(mask)})

    def expect(self, r, back, sprites):
        """sprites: (x, y, frame) drawn in order over the background *back*."""
        img, mask = sprite_strip()
        want = [row[:] for row in back]
        for sx, sy, f in sprites:
            for y in range(10):
                for x in range(12):
                    X, Y = sx + x, sy + y
                    if 0 <= X < 200 and 0 <= Y < 100 and mask[f * 10 + y][x] == 0:
                        want[Y][X] = img[f * 10 + y][x]
        got = [[r.px(x, y) for x in range(200)] for y in range(100)]
        self.assertEqual(got, want)

    def background(self):
        r = self.run_spr("")
        return [[r.px(x, y) for x in range(200)] for y in range(100)]

    def test_drawn_clipped_at_every_edge(self):
        back = self.background()
        spots = [(50, 40, 0), (-5, 30, 1), (195, 10, 0), (80, -4, 1), (100, 95, 0), (-8, -6, 1), (300, 10, 0)]
        body = "".join(f"    CALL SpriteDraw(Sheet, Mask, {x}, {y}, {f}, 12, 10)\n" for x, y, f in spots)
        self.expect(self.run_spr(body), back, spots)

    def test_slots_move_and_restore_the_background(self):
        back = self.background()
        body = """    FOR I = 1 TO 2
        SprW(I) = 12
        SprH(I) = 10
    NEXT I
    SprX(1) = 20
    SprY(1) = 20
    CALL SpriteShow(Sheet, Mask, 1)
    SprX(2) = 26
    SprY(2) = 24
    SprF(2) = 1
    CALL SpriteShow(Sheet, Mask, 2)
    IF SpriteHits(1, 2) THEN
        Out$ = "hit"
    END IF
    CALL SpriteMove(Sheet, Mask, Back, 1, 150, 60, 1)
    CALL SpriteHide(Back, 2)
    CALL SpriteMove(Sheet, Mask, Back, 2, -6, 92, 0)
    B1 = SpriteHits(1, 2)
    B2 = SpriteHitsRect(1, 155, 65, 2, 2)
    IF NOT B1 AND B2 THEN
        Out$ = Out$ + " apart"
    END IF
"""
        r = self.run_spr(body)
        self.assertEqual(string_var(r, "OUT$"), "hit apart")
        self.expect(r, back, [(150, 60, 1), (-6, 92, 0)])


@requires_pasmo
class SceneTests(unittest.TestCase):
    def test_order_and_hits(self):
        body = """    CALL SceneAdd(10, 10, 50, 50)
    CALL SceneAdd(30, 30, 50, 50)
    CALL SceneAdd(100, 10, 20, 20)
    Out$ = STR$(SceneAt(40, 40)) + STR$(SceneAt(15, 15)) + STR$(SceneAt(200, 100))
    CALL SceneToFront(1)
    Out$ = Out$ + STR$(SceneAt(40, 40)) + STR$(SceneDepth(1))
    CALL SceneToBack(1)
    Out$ = Out$ + STR$(SceneAt(40, 40)) + STR$(SceneDepth(1))
    CALL SceneRemove(2)
    Out$ = Out$ + STR$(SceneN) + STR$(SceneAt(40, 40)) + STR$(SceneAt(105, 15)) + STR$(SceneRemoved)
    CALL SceneClean
    CALL SceneDirty(5, 5, 10, 10)
    CALL SceneDirty(50, 2, 4, 4)
    Out$ = Out$ + "|" + STR$(SceneDirtyX) + "," + STR$(SceneDirtyY) + "," + STR$(SceneDirtyW) + "," + STR$(SceneDirtyH)
"""
        r = build_run(app(["geom", "scene"], body), lambda cx, cy, b: [("click", b["Go"])])
        self.assertEqual(string_var(r, "OUT$"), "21013212122|5,2,49,13")


@requires_pasmo
class KeysTests(unittest.TestCase):
    def test_axis(self):
        src = app(["keys"], "    Out$ = STR$(KeyAxis(SC_LEFT, SC_RIGHT))\n")
        for held, want in (((), "0"), (("LEFT",), "-1"), (("RIGHT",), "1"), (("LEFT", "RIGHT"), "0"),
                           (("KP4",), "0")):  # the keypad's 4 is another key
            with self.subTest(held=held):
                r = build_run(src, lambda cx, cy, b, h=held: [("hold", k, True) for k in h] + [("click", b["Go"])])
                self.assertEqual(string_var(r, "OUT$"), want)


if __name__ == "__main__":
    unittest.main()
