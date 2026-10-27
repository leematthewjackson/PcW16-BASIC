"""SPRITED (examples/sprited.pbas), the sprite and icon editor, on the simulator.

Sessions are driven with raw mouse events on the zoomed grids and the frame
strips, canvas keys, menu choices, a typed file name and timer ticks. What
the program shows is read from the canvas pixel for pixel: the zoomed
cells, the actual-size frames in the strips, the masked frame preview and
the animated preview. What it saves is read back with tools/pbicheck.py
and compared with the pixels the session set, so a click that lands on the
wrong image pixel, a mask stored the wrong way round, an edit that goes to
the wrong frame or a strip saved in the wrong order shows. Files it opens
are made here with pbicheck.from_rows, independently of the program.
Simulator evidence only (the simulator draws Rosanne's grey patterns as
solid black or white, so the program's grey shading of hidden cells is not
checked here; nothing here has run in XAnne).
"""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import check_source
from pbas.layout import build_dialog
from toolchain import requires_pasmo

import memguard

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pbicheck  # noqa: E402

# Every guarded_run builds the program again (about 3.5 s here); the
# sessions below all run the same source, so the first build's .asm and
# .prg are kept and copied for the others. Only this module is affected.
_BUILDS: dict = {}
_real_build = memguard.build


def _cached_build(src, asm, prg, **options):
    key = (Path(src).read_text(encoding="utf-8"), repr(sorted(options.items())))
    if key not in _BUILDS:
        report = _real_build(src, asm, prg, **options)
        _BUILDS[key] = (Path(asm).read_bytes(), Path(prg).read_bytes(), report)
    asm_bytes, prg_bytes, report = _BUILDS[key]
    Path(asm).write_bytes(asm_bytes)
    Path(prg).write_bytes(prg_bytes)
    return report


memguard.build = _cached_build

PATH = ROOT / "examples" / "sprited.pbas"
SRC = PATH.read_text(encoding="utf-8")
F = "\\PCW\\FOLDER01"

# the program's layout (its CONSTs), in canvas coordinates
GY, IGX, MGX, ZOOM = 24, 8, 152, 8
STX, SMX, STY = 308, 332, 24
PVX, ANX, PVY = 384, 448, 24

NEW, OPEN, SAVE, QUIT = (("menu", 1, i) for i in range(4))  # dividers are not numbered
NEXT, PREV, ADD, DELETE, CLEAR, ANIMATE = (("menu", 2, i) for i in range(6))
MASK_FROM_IMAGE, MASK_FILL, INVERT = (("menu", 3, i) for i in range(3))
SAVE_ANS, DISCARD_ANS, CANCEL_ANS = 0, 1, 2  # "Unsaved changes": Save / Discard / Cancel
KC_LEFT, KC_RIGHT = 226, 227
IMAGE, MASK = 0, 1


def layout():
    program = check_source(SRC, path=PATH)
    main = build_dialog(program, program.windows[0], True)
    binds = {row.var_name: row.number for row in main.bindings}
    return main.canvas[1], main.canvas[2], binds["NAME$"]


CX0, CY0, NAME_FIELD = layout()


def cell(layer, x, y):
    """The screen point at the middle of a zoomed cell."""
    gx = IGX if layer == IMAGE else MGX
    return CX0 + gx + x * ZOOM + 4, CY0 + GY + y * ZOOM + 4


def click(layer, x, y):
    return [("mdown",) + cell(layer, x, y), ("mup",) + cell(layer, x, y)]


def drag(layer, cells):
    first, rest = cells[0], cells[1:]
    ev = [("mdown",) + cell(layer, *first)]
    ev += [("mmove",) + cell(layer, *c) for c in rest]
    return ev + [("mup",) + cell(layer, *cells[-1])]


def key(ch):
    return ("key", ord(ch) if isinstance(ch, str) else ch)


def name(text):
    return ("edit", NAME_FIELD, text)


def run(events, files=None, answers=None, quit=True, **sim):
    disk = z80sim.Disk(files={(F, n): d for n, d in (files or {}).items()})
    tail = [QUIT] if quit else []
    r = guarded_run(SRC, events=events + tail, disk=disk, path=PATH, max_steps=2_000_000_000,
                    alert_answers=answers, build_options={"runtime_sections": "all"}, **sim)
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r


def canvas(r, x, y, w, h):
    """Canvas pixels as rows of 1 (black) / 0 (white)."""
    return [[1 if c == "#" else 0 for c in row] for row in r.cpu.canvas_pixels(CX0 + x, CY0 + y, w, h)]


def thumb(r, f):
    """Frame f's image in the strip on screen (1 = black)."""
    return canvas(r, STX, STY + f * 16, 16, 16)


def thumb_mask(r, f):
    """Frame f's mask in the strip on screen (1 = drawn, i.e. white)."""
    return [[1 - p for p in row] for row in canvas(r, SMX, STY + f * 16, 16, 16)]


def grid(r, layer):
    """The colour in the middle of each zoomed cell (1 = black)."""
    gx = IGX if layer == IMAGE else MGX
    rows = canvas(r, gx, GY, 128, 128)
    return [[rows[y * 8 + 4][x * 8 + 4] for x in range(16)] for y in range(16)]


def image(points, w=16, h=16):
    rows = [[0] * w for _ in range(h)]
    for x, y in points:
        rows[y][x] = 1
    return rows


def disk_file(r, name):
    return r.cpu.disk.files.get((F, name))


def written(r):
    """The files on the disk other than the program itself (it reads its code banks from it)."""
    return sorted(n for (_, n) in r.cpu.disk.files if n != "PROGRAM.PRG")


def saved(r, base):
    """(image rows 1 = black, mask rows 1 = drawn) of a saved sprite, checked as PBI1."""
    img, msk = disk_file(r, base + ".PBI"), disk_file(r, base + "M.PBI")
    assert img is not None and msk is not None, written(r)
    assert pbicheck.check(img)[0] == 0 and pbicheck.check(msk)[0] == 0
    return pbicheck.pixels(img), [[1 - p for p in row] for row in pbicheck.pixels(msk)]


def checker(x0):
    """The preview box's backdrop: 8 x 8 squares, white at the top left."""
    return [[((x // 8) + (y // 8)) % 2 for x in range(32)] for y in range(32)]


def preview(img, msk):
    """A frame drawn through its mask at 8, 8 over the backdrop."""
    box = checker(0)
    for y in range(16):
        for x in range(16):
            if msk[y][x]:
                box[8 + y][8 + x] = img[y][x]
    return box


def status(r):
    return string_var(r, "APPSTATUS$")


def rows_from(rows, f):
    return rows[f * 16:(f + 1) * 16]


EMPTY = image([])
FULL = [[1] * 16 for _ in range(16)]


@requires_pasmo
class DrawingTests(unittest.TestCase):
    def test_clicks_set_the_right_image_pixels(self):
        points = [(0, 0), (15, 0), (3, 7), (0, 15), (15, 15), (9, 4)]
        ev = [e for p in points for e in click(IMAGE, *p)] + [name("hero"), SAVE]
        r = run(ev)
        want = image(points)
        self.assertEqual(thumb(r, 0), want)
        self.assertEqual(grid(r, IMAGE), want)
        img, msk = saved(r, "HERO")
        self.assertEqual(img, want)
        self.assertEqual(msk, EMPTY)  # a new sprite's mask is all transparent
        self.assertTrue(r.cpu.exited)  # saved: Quit does not ask

    def test_a_click_on_a_grid_line_or_a_cell_edge(self):
        # the cell's first column (on the grid line) and its last pixel both belong to it
        x, y = CX0 + IGX + 5 * ZOOM, CY0 + GY + 2 * ZOOM + 7
        ev = [("mdown", x, y), ("mup", x, y)]
        x2, y2 = CX0 + IGX + 16 * ZOOM - 1, CY0 + GY + 16 * ZOOM - 1  # the last pixel of the grid
        ev += [("mdown", x2, y2), ("mup", x2, y2)]
        x3 = CX0 + IGX + 16 * ZOOM  # just right of the grid: nothing
        ev += [("mdown", x3, y2), ("mup", x3, y2)]
        r = run(ev, answers=[DISCARD_ANS])
        self.assertEqual(thumb(r, 0), image([(5, 2), (15, 15)]))

    def test_drag_paints_every_cell_on_the_way(self):
        ev = drag(IMAGE, [(2, 3), (9, 3)])  # one move event 7 cells away
        ev += drag(IMAGE, [(0, 8), (5, 13)])  # diagonal
        ev += drag(IMAGE, [(12, 0), (12, 2), (14, 2)])
        r = run(ev, answers=[DISCARD_ANS])
        want = image([(x, 3) for x in range(2, 10)] + [(i, 8 + i) for i in range(6)]
                     + [(12, 0), (12, 1), (12, 2), (13, 2), (14, 2)])
        self.assertEqual(thumb(r, 0), want)
        self.assertEqual(grid(r, IMAGE), want)

    def test_a_press_on_black_clears(self):
        ev = drag(IMAGE, [(0, 5), (15, 5)])
        ev += drag(IMAGE, [(4, 5), (7, 5)])  # starts on black: clears 4..7
        ev += drag(IMAGE, [(4, 6), (4, 5)])  # starts on white: sets, and (4, 5) again
        r = run(ev, answers=[DISCARD_ANS])
        want = image([(x, 5) for x in range(16) if x not in (5, 6, 7)] + [(4, 6)])
        self.assertEqual(thumb(r, 0), want)

    def test_a_drag_off_the_grid_paints_nothing_there(self):
        x_out = CX0 + IGX + 16 * ZOOM + 3  # between the two grids
        ev = [("mdown",) + cell(IMAGE, 13, 1), ("mmove", x_out, cell(IMAGE, 0, 1)[1]),
              ("mmove",) + cell(MASK, 2, 1),  # into the other grid: it stays the image's pen
              ("mmove",) + cell(IMAGE, 15, 3), ("mup",) + cell(IMAGE, 15, 3)]
        r = run(ev, answers=[DISCARD_ANS])
        self.assertEqual(thumb(r, 0), image([(13, 1), (15, 3)]))
        self.assertEqual(thumb_mask(r, 0), EMPTY)

    def test_invert(self):
        r = run(click(IMAGE, 1, 1) + [INVERT], answers=[DISCARD_ANS])
        want = [[1] * 16 for _ in range(16)]
        want[1][1] = 0
        self.assertEqual(thumb(r, 0), want)

    def test_status_line(self):
        r = run([], quit=False)
        self.assertEqual(status(r), "untitled  frame 1 of 1")
        r = run(click(IMAGE, 1, 1), quit=False)
        self.assertEqual(status(r), "untitled*  frame 1 of 1")


@requires_pasmo
class MaskTests(unittest.TestCase):
    def test_mask_cells_are_edited_separately(self):
        img_pts = [(1, 1), (2, 2)]
        msk_pts = [(1, 1), (10, 12), (15, 0)]
        ev = [e for p in img_pts for e in click(IMAGE, *p)]
        ev += [e for p in msk_pts for e in click(MASK, *p)]
        ev += drag(MASK, [(0, 15), (3, 15)])
        ev += [name("M1"), SAVE]
        r = run(ev)
        want_m = image(msk_pts + [(x, 15) for x in range(4)])
        self.assertEqual(thumb_mask(r, 0), want_m)
        self.assertEqual(thumb(r, 0), image(img_pts))
        # the mask grid shows the mask as BITMAP MASK reads it: white = drawn
        self.assertEqual(grid(r, MASK), [[1 - p for p in row] for row in want_m])
        img, msk = saved(r, "M1")
        self.assertEqual(img, image(img_pts))
        self.assertEqual(msk, want_m)

    def test_mask_from_image_and_fill(self):
        pts = [(3, 3), (4, 3), (5, 9)]
        ev = [e for p in pts for e in click(IMAGE, *p)] + [key("m"), name("A"), SAVE]
        r = run(ev)
        self.assertEqual(saved(r, "A")[1], image(pts))
        r = run([e for p in pts for e in click(IMAGE, *p)] + [MASK_FILL, name("B"), SAVE])
        self.assertEqual(saved(r, "B")[1], FULL)
        r = run(click(MASK, 0, 0) + [key("f"), click(MASK, 0, 0)[0], click(MASK, 0, 0)[1],
                                     name("C"), SAVE])
        want = [[1] * 16 for _ in range(16)]
        want[0][0] = 0  # filled, then the click on a drawn cell clears it
        self.assertEqual(saved(r, "C")[1], want)

    def test_the_frame_preview_draws_through_the_mask(self):
        img_pts = [(x, 2) for x in range(16)] + [(5, 5)]
        msk_pts = [(x, 2) for x in range(8)] + [(x, 9) for x in range(16)]
        ev = [e for p in img_pts for e in click(IMAGE, *p)]
        ev += [e for p in msk_pts for e in click(MASK, *p)]
        r = run(ev, answers=[DISCARD_ANS])
        box = canvas(r, PVX, PVY, 32, 32)
        self.assertEqual(box, preview(image(img_pts), image(msk_pts)))
        # opaque white pixels hide the black squares, opaque black ones the white
        self.assertEqual(box[8 + 9][8:24], [0] * 16)
        self.assertEqual(box[8 + 2][8:16], [1] * 8)


@requires_pasmo
class FrameTests(unittest.TestCase):
    def test_add_copies_the_frame_and_edits_go_to_the_current_one(self):
        ev = click(IMAGE, 0, 0) + click(MASK, 0, 0)
        ev += [key("a")] + click(IMAGE, 1, 1)  # frame 2: a copy, then (1, 1)
        ev += [ADD] + click(IMAGE, 2, 2) + click(MASK, 2, 2)  # frame 3
        ev += [key("1")] + click(IMAGE, 15, 15)  # back to frame 1
        ev += [name("STRIP"), SAVE]
        r = run(ev)
        img, msk = saved(r, "STRIP")
        self.assertEqual(len(img), 48)
        self.assertEqual(rows_from(img, 0), image([(0, 0), (15, 15)]))
        self.assertEqual(rows_from(img, 1), image([(0, 0), (1, 1)]))
        self.assertEqual(rows_from(img, 2), image([(0, 0), (1, 1), (2, 2)]))
        self.assertEqual(rows_from(msk, 0), image([(0, 0)]))
        self.assertEqual(rows_from(msk, 1), image([(0, 0)]))
        self.assertEqual(rows_from(msk, 2), image([(0, 0), (2, 2)]))
        for f in range(3):
            self.assertEqual(thumb(r, f), rows_from(img, f))
        self.assertEqual(status(r), "STRIP  frame 1 of 3")

    def test_clicking_a_frame_in_the_strip_selects_it(self):
        ev = click(IMAGE, 0, 0) + [key("a"), key("a")] + click(IMAGE, 3, 3)  # frame 3
        sx, sy = CX0 + STX + 4, CY0 + STY + 1 * 16 + 8  # frame 2 in the strip
        ev += [("mdown", sx, sy), ("mup", sx, sy)] + click(IMAGE, 7, 7)
        r = run(ev, answers=[DISCARD_ANS])
        self.assertEqual(thumb(r, 1), image([(0, 0), (7, 7)]))
        self.assertEqual(thumb(r, 2), image([(0, 0), (3, 3)]))
        self.assertEqual(grid(r, IMAGE), image([(0, 0), (7, 7)]))
        # the marker beside the strip is at frame 2
        marker = canvas(r, STX - 7, STY, 1, 64)
        self.assertEqual([marker[f * 16 + 8][0] for f in range(4)], [0, 1, 0, 0])

    def test_left_right_and_next_previous_wrap(self):
        ev = [key("a"), key("a")]  # 3 frames, on frame 3
        ev += [key(KC_RIGHT)] + click(IMAGE, 1, 0)  # wraps to frame 1
        ev += [key(KC_LEFT)] + click(IMAGE, 3, 0)  # back to frame 3
        ev += [PREV] + click(IMAGE, 2, 0) + [NEXT, NEXT] + click(IMAGE, 4, 0)  # frame 2, then 1
        r = run(ev, answers=[DISCARD_ANS])
        self.assertEqual(thumb(r, 0), image([(1, 0), (4, 0)]))
        self.assertEqual(thumb(r, 1), image([(2, 0)]))
        self.assertEqual(thumb(r, 2), image([(3, 0)]))

    def test_four_frames_at_most_and_frame_keys_beyond_them(self):
        ev = [key("a")] * 5 + [key("1")] + click(IMAGE, 0, 0)
        r = run(ev + [name("FOUR"), SAVE])
        img, _ = saved(r, "FOUR")
        self.assertEqual(len(img), 64)
        self.assertEqual(status(r), "FOUR  frame 1 of 4")
        ev = [key("a"), key("4")] + click(IMAGE, 9, 9)  # 2 frames: "4" does nothing
        r = run(ev, answers=[DISCARD_ANS])
        self.assertEqual(thumb(r, 1), image([(9, 9)]))

    def test_delete_and_clear(self):
        ev = click(IMAGE, 0, 0) + [key("a")] + click(IMAGE, 1, 0) + [key("a")] + click(IMAGE, 2, 0)
        ev += [key("2"), DELETE]  # frames 1 and 3 remain; frame 3 is now frame 2
        r = run(ev + [name("DEL"), SAVE])
        img, _ = saved(r, "DEL")
        self.assertEqual(len(img), 32)
        self.assertEqual(rows_from(img, 0), image([(0, 0)]))
        self.assertEqual(rows_from(img, 1), image([(0, 0), (1, 0), (2, 0)]))
        self.assertEqual(status(r), "DEL  frame 2 of 2")
        r = run(click(IMAGE, 0, 0) + click(MASK, 0, 0) + [DELETE, CLEAR, name("CLR"), SAVE])
        img, msk = saved(r, "CLR")
        self.assertEqual((img, msk), (EMPTY, EMPTY))  # the last frame is kept, then cleared


@requires_pasmo
class AnimationTests(unittest.TestCase):
    FRAMES = [[(x, 0) for x in range(16)], [(0, y) for y in range(16)], [(i, i) for i in range(16)]]
    # M13 responsiveness: the TIMER is the event loop's own and runs as the
    # clock says; here the clock moves only by the script, so the animation
    # moves on only at its "timer" entries (each one: the handler once more)
    TIME = {"clock_by_steps": False}

    def three_frames(self):
        ev = []
        for k, pts in enumerate(self.FRAMES):
            if k:
                ev += [key("a"), CLEAR]
            ev += [e for p in pts for e in click(IMAGE, *p)] + [MASK_FILL]
        return ev

    def anim(self, r):
        return canvas(r, ANX, PVY, 32, 32)

    def test_each_tick_shows_the_next_frame(self):
        base = self.three_frames()
        r = run(base, answers=[DISCARD_ANS], **self.TIME)
        start = self.anim(r)
        for ticks in range(1, 5):
            with self.subTest(ticks=ticks):
                r = run(base + [("timer", 0)] * ticks, answers=[DISCARD_ANS], **self.TIME)
                self.assertEqual(self.anim(r), preview(image(self.FRAMES[ticks % 3]), FULL))
        # it began on frame 1 (the timer had not run yet)
        self.assertEqual(start, preview(image(self.FRAMES[0]), FULL))

    def test_paused_animation_stays(self):
        base = self.three_frames() + [("timer", 0)]  # frame 2
        r = run(base + [key("p")] + [("timer", 0)] * 3, answers=[DISCARD_ANS], **self.TIME)
        self.assertEqual(self.anim(r), preview(image(self.FRAMES[1]), FULL))
        r = run(base + [key("p"), ("timer", 0), ANIMATE, ("timer", 0)], answers=[DISCARD_ANS], **self.TIME)
        self.assertEqual(self.anim(r), preview(image(self.FRAMES[2]), FULL))

    def test_the_animation_shows_edits_and_the_mask(self):
        ev = click(IMAGE, 5, 5) + click(MASK, 5, 5) + click(MASK, 6, 6) + [("timer", 0)]
        r = run(ev, answers=[DISCARD_ANS], **self.TIME)
        self.assertEqual(self.anim(r), preview(image([(5, 5)]), image([(5, 5), (6, 6)])))


@requires_pasmo
class FileTests(unittest.TestCase):
    def random_sprite(self, frames, seed):
        rnd = random.Random(seed)
        img = [[rnd.randint(0, 1) for _ in range(16)] for _ in range(16 * frames)]
        msk = [[rnd.randint(0, 1) for _ in range(16)] for _ in range(16 * frames)]
        return img, msk

    def files_for(self, base, img, msk):
        return {base + ".PBI": pbicheck.from_rows(img),
                base + "M.PBI": pbicheck.from_rows([[1 - p for p in row] for row in msk])}

    def test_open_a_strip(self):
        img, msk = self.random_sprite(3, 1)
        r = run([name("rnd"), OPEN], files=self.files_for("RND", img, msk))
        self.assertNotIn("Not opened", " ".join(r.alerts))
        for f in range(3):
            self.assertEqual(thumb(r, f), rows_from(img, f))
            self.assertEqual(thumb_mask(r, f), rows_from(msk, f))
        self.assertEqual(grid(r, MASK), [[1 - p for p in row] for row in rows_from(msk, 0)])
        self.assertEqual(status(r), "RND  frame 1 of 3")
        self.assertTrue(r.cpu.exited)  # just opened: no question

    def test_round_trip(self):
        img, msk = self.random_sprite(4, 2)
        files = self.files_for("IN", img, msk)
        ev = [name("in.pbi"), OPEN, key("2")] + click(IMAGE, 0, 0) + click(MASK, 15, 15)
        ev += [name("OUT"), SAVE]
        r = run(ev, files=files)
        out_img, out_msk = saved(r, "OUT")
        img[16][0] ^= 1
        msk[31][15] ^= 1
        self.assertEqual(out_img, img)
        self.assertEqual(out_msk, msk)
        self.assertEqual(disk_file(r, "IN.PBI"), files["IN.PBI"])  # the opened files are untouched
        # what it saved opens again, the same
        r2 = run([name("OUT"), OPEN, name("AGAIN"), SAVE],
                 files={n: disk_file(r, n) for n in ("OUT.PBI", "OUTM.PBI")})
        self.assertEqual(saved(r2, "AGAIN"), (img, msk))

    def test_saving_again_keeps_a_backup(self):
        ev = click(IMAGE, 0, 0) + [name("BK"), SAVE] + click(IMAGE, 1, 0) + [SAVE]
        r = run(ev)
        self.assertEqual(saved(r, "BK")[0], image([(0, 0), (1, 0)]))
        self.assertEqual(pbicheck.pixels(disk_file(r, "BK.BAK")), image([(0, 0)]))
        self.assertIsNotNone(disk_file(r, "BKM.BAK"))  # M14: the mask's backup too (M14-ACCEPTANCE G8)

    def test_bad_files_are_refused_and_the_sprite_kept(self):
        good_img, good_msk = self.random_sprite(1, 3)
        m16 = pbicheck.from_rows([[1] * 16] * 16)
        damaged = bytearray(pbicheck.from_rows([[0] * 16] * 16))
        damaged[20] ^= 0xFF
        cases = {
            "not a picture": ({"X.PBI": b"PDB1" + bytes(40), "XM.PBI": m16},
                              "Not opened: X.PBI: not a PBI1 picture"),
            "damaged": ({"X.PBI": bytes(damaged), "XM.PBI": m16}, "Not opened: X.PBI: damaged"),
            "missing": ({}, "Not opened: X.PBI: not found"),
            "too wide": ({"X.PBI": pbicheck.from_rows([[0] * 32] * 32), "XM.PBI": m16},
                         "Not opened: X.PBI is 32 x 32, not 16 wide with 1 to 4 frames of 16"),
            "not whole frames": ({"X.PBI": pbicheck.from_rows([[0] * 16] * 20), "XM.PBI": m16},
                                 "Not opened: X.PBI is 16 x 20, not 16 wide with 1 to 4 frames of 16"),
            "too large": ({"X.PBI": pbicheck.from_rows([[0] * 16] * 80), "XM.PBI": m16},
                          "Not opened: X.PBI: too large"),
            "no mask": ({"X.PBI": pbicheck.from_rows([[0] * 16] * 32)},
                        "Not opened: its mask XM.PBI: not found"),
            "mask of another size": ({"X.PBI": pbicheck.from_rows([[0] * 16] * 32), "XM.PBI": m16},
                                     "Not opened: the mask XM.PBI is not the same size as the image"),
        }
        for label, (files, alert) in cases.items():
            with self.subTest(label):
                files = dict(files, **self.files_for("GOOD", good_img, good_msk))
                r = run([name("GOOD"), OPEN, name("X"), OPEN], files=files)
                self.assertIn(alert, r.alerts)
                self.assertEqual(thumb(r, 0), good_img)
                self.assertEqual(thumb_mask(r, 0), good_msk)
                self.assertEqual(status(r), "GOOD  frame 1 of 1")
                self.assertTrue(r.cpu.exited)  # nothing changed: no question at Quit

    def test_names(self):
        cases = {
            "": "Type a name in the Name field first",
            "TOOLONG8": "A name has at most 7 characters (the mask adds M)",
            "A.TXT": "A name has only letters, digits and _",
            "A B": "A name has only letters, digits and _",
        }
        for typed, alert in cases.items():
            with self.subTest(typed):
                r = run(click(IMAGE, 0, 0) + [name(typed), SAVE], answers=[DISCARD_ANS])
                self.assertIn(alert, r.alerts)
                self.assertEqual(written(r), [])
        r = run(click(IMAGE, 0, 0) + [name(" my_7.pbi "), SAVE])
        self.assertEqual(saved(r, "MY_7")[0], image([(0, 0)]))

    def test_a_failed_save_says_so(self):
        disk_full = {z80sim.FN_OS_WRITE_FILE: 163}  # os_write_file is refused: "disk full"
        disk = z80sim.Disk(faults_from={fn: (1, code) for fn, code in disk_full.items()})
        r = guarded_run(SRC, events=click(IMAGE, 0, 0) + [name("FULL"), SAVE, QUIT], disk=disk,
                        path=PATH, max_steps=2_000_000_000, alert_answers=[DISCARD_ANS],
                        build_options={"runtime_sections": "all"})
        self.assertEqual(r.violations, [])
        self.assertTrue(any(a.startswith("Not saved: FULL.PBI:") for a in r.alerts), r.alerts)
        self.assertIn("Unsaved changes", r.alerts)  # still unsaved
        self.assertTrue(r.cpu.exited)


@requires_pasmo
class UnsavedChangesTests(unittest.TestCase):
    def test_quit_asks(self):
        self.assertTrue(run([]).cpu.exited)  # nothing changed: no question
        r = run(click(IMAGE, 0, 0), answers=[CANCEL_ANS])
        self.assertIn("Unsaved changes", r.alerts)
        self.assertFalse(r.cpu.exited)
        r = run(click(IMAGE, 0, 0), answers=[DISCARD_ANS])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(written(r), [])

    def test_save_from_the_question(self):
        r = run(click(IMAGE, 4, 4) + [name("ASKED")], answers=[SAVE_ANS])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(saved(r, "ASKED")[0], image([(4, 4)]))
        r = run(click(IMAGE, 4, 4), answers=[SAVE_ANS])  # no name: not saved, not closed
        self.assertIn("Type a name in the Name field first", r.alerts)
        self.assertFalse(r.cpu.exited)

    def test_new_and_open_ask(self):
        r = run(click(IMAGE, 4, 4) + [NEW], answers=[CANCEL_ANS, DISCARD_ANS])
        self.assertEqual(thumb(r, 0), image([(4, 4)]))  # Cancel: kept
        r = run(click(IMAGE, 4, 4) + [key("a"), NEW], quit=False, answers=[DISCARD_ANS])
        self.assertEqual(thumb(r, 0), EMPTY)
        self.assertEqual(status(r), "untitled  frame 1 of 1")
        files = {"O.PBI": pbicheck.from_rows(image([(1, 1)])), "OM.PBI": pbicheck.from_rows(FULL)}
        r = run(click(IMAGE, 4, 4) + [name("O"), OPEN], files=files, answers=[CANCEL_ANS, DISCARD_ANS])
        self.assertEqual(thumb(r, 0), image([(4, 4)]))
        r = run(click(IMAGE, 4, 4) + [name("O"), OPEN], files=files, answers=[DISCARD_ANS])
        self.assertEqual(thumb(r, 0), image([(1, 1)]))
        self.assertTrue(r.cpu.exited)


if __name__ == "__main__":
    unittest.main()
