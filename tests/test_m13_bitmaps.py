"""M13: BITMAP PUT of a part and BITMAP MASK (LANGUAGE-SPEC §5.14).

A pattern is drawn on the canvas and captured (BITMAP GET, pixel-exact
since M12); parts of it are then drawn elsewhere, and every pixel of each is
compared with the pattern still on the canvas. Masks are captured the same
way: a white mask pixel draws the image's pixel, a black one leaves the
canvas as it was, which is checked against an untouched copy of the
background. Simulator evidence (ROSAN283 bios_plotmaskedbitmap; the mask's
polarity is a static reading of PCW045.SYS, for SPRPROBE in XAnne).
"""
from __future__ import annotations

import random
import unittest

from memguard import guarded_run
from pbas import SourceError, check_source, generate
from pbas.layout import build_dialog
from toolchain import requires_pasmo


def program(body: str, dims: str = "") -> str:
    return (f"{dims}WINDOW W, \"T\", LARGE\nCANVAS 560, 290, PAINT P\nBUTTON \"Go\", Go\n"
            "SUB P\n    DRAW CLEAR\nEND SUB\n"
            f"SUB Go\n    LOCAL I AS INTEGER\n{body}END SUB\nEND\n")


def run(src: str, banks="all"):
    prog = check_source(src)
    lay = build_dialog(prog, prog.windows[0], False)
    btn = next(o.number for o in lay.objects if o.kind == "BUTTON")
    r = guarded_run(src, events=[("click", btn)], max_steps=900_000_000,
                    build_options={"runtime_sections": banks} if banks else None)
    assert r.violations == [], r.violations[:5]
    cx, cy = lay.canvas[1], lay.canvas[2]
    r.px = lambda x, y: r.cpu.pixel(cx + x, cy + y)
    return r


# a pattern no part can match by accident: diagonals, a box, a stripe
PATTERN = ("    FOR I = 0 TO {w} - 1 STEP 3\n        DRAW LINE I, 0, {w} - 1 - I, {h} - 1\n    NEXT I\n"
           "    DRAW BOX 2, 2, 7, 5\n    DRAW FILL 11, 1, 3, {h} - 2\n    DRAW PIXEL {w} - 1, 0\n")


@requires_pasmo
class DrawingStateTests(unittest.TestCase):
    def test_ink_and_mode_are_put_back(self):
        # a line in XOR ink drawn twice leaves nothing; the PUT and MASK
        # between the two draw opaque, then put the XOR ink and mode back
        body = ("    BITMAP GET M, 0, 0, 20, 20\n    DRAW FILL 0, 0, 40, 20, 0\n    BITMAP GET A, 0, 0\n"
                "    DRAW CLEAR\n    DRAW INK XOR\n    DRAW LINE 0, 100, 300, 100\n"
                "    BITMAP PUT A, 50, 30, 0, 0, 30, 10\n    BITMAP MASK A, M, 100, 30, 0, 0, 10, 10\n"
                "    DRAW LINE 0, 100, 300, 100\n    DRAW INK BLACK\n")
        r = run(program(body, "DIM A AS BITMAP * 40, 20\nDIM M AS BITMAP * 20, 20\n"))
        self.assertEqual([r.px(x, 100) for x in range(0, 301, 10)], [0] * 31)
        self.assertEqual(r.px(60, 35), 1)  # and the parts were drawn black, opaque
        self.assertEqual(r.px(105, 35), 1)

    def test_rosannes_mode_and_ink_are_left_as_they_were(self):
        # whatever Rosanne's own drawing state was, a PUT or MASK leaves it so
        src = program("    BITMAP GET A, 0, 0\n    BITMAP GET M, 0, 0, 20, 20\n"
                      "    BITMAP PUT A, 50, 30, 3, 0, 30, 10\n    BITMAP MASK A, M, 100, 30, 0, 0, 10, 10\n",
                      "DIM A AS BITMAP * 40, 20\nDIM M AS BITMAP * 20, 20\n")
        prog = check_source(src)
        btn = next(o.number for o in build_dialog(prog, prog.windows[0], False).objects if o.kind == "BUTTON")
        for mode in (1, 2, 3):
            with self.subTest(mode=mode):
                r = guarded_run(src, events=[("click", btn)], bios_mode=mode, build_options={"runtime_sections": "all"})
                self.assertEqual(r.violations, [])
                self.assertEqual((r.cpu.bios_mode, r.cpu.bios_ink), (mode, 0))


@requires_pasmo
class PartTests(unittest.TestCase):
    def check_parts(self, w, h, parts, banks="all"):
        body = PATTERN.format(w=w, h=h) + "    BITMAP GET A, 0, 0\n"
        for (x, y, sx, sy, pw, ph) in parts:
            body += f"    BITMAP PUT A, {x}, {y}, {sx}, {sy}, {pw}, {ph}\n"
        r = run(program(body, f"DIM A AS BITMAP * {w}, {h}\n"), banks)
        for (x, y, sx, sy, pw, ph) in parts:
            for j in range(ph):
                for i in range(pw):
                    self.assertEqual(r.px(x + i, y + j), r.px(sx + i, sy + j), (x, y, sx, sy, pw, ph, i, j))
        return r

    def test_parts_at_every_shift(self):
        # sx = 0..9 (every bit offset, and past a byte), widths across bytes
        parts = [(60 + 40 * (k % 12), 40 + 30 * (k // 12), k, k % 5, 17 + k % 6, 9) for k in range(24)]
        r = self.check_parts(48, 20, parts)
        self.assertTrue(any(e[0] == "plot" for e in r.cpu.bitmap_log))

    def test_random_parts(self):
        rng = random.Random(1313)
        parts = []
        for k in range(16):
            pw, ph = rng.randint(1, 40), rng.randint(1, 20)
            sx, sy = rng.randint(0, 64 - pw), rng.randint(0, 24 - ph)
            parts.append((80 + 60 * (k % 8), 60 + 50 * (k // 8), sx, sy, pw, ph))
        self.check_parts(64, 24, parts)

    def test_whole_rows_are_drawn_from_the_block(self):
        # a part as wide as the bitmap, from x 0: one plot straight from its block
        r = self.check_parts(40, 20, [(100, 50, 0, 3, 40, 12)])
        [plot] = [e for e in r.cpu.bitmap_log if e[0] == "plot"]
        self.assertEqual(plot[3:], (40, 12))

    def test_many_strips(self):
        # 400 pixels a row (50 bytes): 640 \ 50 = 12 source rows fit the strip,
        # but the 300-pixel part's rows (38 bytes) only 192 \ 38 = 5: 8 strips
        r = self.check_parts(400, 40, [(30, 120, 5, 0, 300, 40)])
        self.assertEqual(len([e for e in r.cpu.bitmap_log if e[0] == "plot"]), 8)

    def test_without_the_runtime_bank(self):
        self.check_parts(40, 20, [(60, 40, 3, 1, 21, 13)], banks=None)

    def test_the_old_put_is_unchanged(self):
        src = program("    BITMAP GET A, 0, 0\n    BITMAP PUT A, 50, 50\n", "DIM A AS BITMAP * 40, 20\n")
        self.assertIn("PB_BMPPART equ 0", generate(check_source(src)))
        src = program("    BITMAP PUT A, 50, 50, 0, 0, 4, 4\n", "DIM A AS BITMAP * 40, 20\n")
        self.assertIn("PB_BMPPART equ 1", generate(check_source(src)))


@requires_pasmo
class MaskTests(unittest.TestCase):
    """Image: the pattern at (0, 0); mask: a shape captured at (0, 30); the
    background: shade 4 at two places, the second masked over."""

    MASK = ("    DRAW FILL 4, 33, 20, 12\n    DRAW LINE 0, 30, 39, 49\n    DRAW FILL 30, 31, 6, 3\n"
            "    DRAW INVERT 0, 30, 40, 20\n")  # black outside the shape: white = drawn

    def check_masked(self, calls, banks="all"):
        body = PATTERN.format(w=40, h=20) + self.MASK + \
            "    BITMAP GET A, 0, 0\n    BITMAP GET M, 0, 30\n" \
            "    DRAW FILL 0, 100, 560, 80, 4\n    DRAW FILL 0, 190, 560, 80, 4\n"
        for x, sx, sy, pw, ph in calls:
            if (sx, sy, pw, ph) == (0, 0, 40, 20):
                body += f"    BITMAP MASK A, M, {x}, 190\n"
            else:
                body += f"    BITMAP MASK A, M, {x}, 190, {sx}, {sy}, {pw}, {ph}\n"
        r = run(program(body, "DIM A AS BITMAP * 40, 20\nDIM M AS BITMAP * 40, 20\n"), banks)
        drawn = 0
        for x, sx, sy, pw, ph in calls:
            for j in range(ph):
                for i in range(pw):
                    white_mask = r.px(sx + i, 30 + sy + j) == 0
                    want = r.px(sx + i, sy + j) if white_mask else r.px(x + i, 100 + j)
                    drawn += white_mask
                    self.assertEqual(r.px(x + i, 190 + j), want, (x, sx, sy, i, j, white_mask))
        self.assertGreater(drawn, 0)
        return r

    def test_the_whole_image_through_its_mask(self):
        r = self.check_masked([(40, 0, 0, 40, 20)])
        self.assertEqual([e[0] for e in r.cpu.bitmap_log].count("masked"), 1)

    def test_parts_through_the_mask(self):
        self.check_masked([(100 + 50 * k, k, k % 4, 20 + k % 7, 13) for k in range(9)])

    def test_without_the_runtime_bank(self):
        self.check_masked([(100, 3, 2, 30, 15)], banks=None)


@requires_pasmo
class ErrorTests(unittest.TestCase):
    def alerts(self, body, dims="DIM A AS BITMAP * 40, 20\nDIM M AS BITMAP * 20, 20\n"):
        prog = check_source(program(body, dims))
        lay = build_dialog(prog, prog.windows[0], False)
        btn = next(o.number for o in lay.objects if o.kind == "BUTTON")
        r = guarded_run(program(body, dims), events=[("click", btn)], max_steps=200_000_000)
        self.assertEqual(r.violations, [])
        return r.alerts

    def test_a_part_outside_the_bitmap(self):
        for args in ("0, 0, 30, 0, 11, 5", "0, 0, 0, 15, 5, 6", "0, 0, -1, 0, 5, 5", "0, 0, 0, 0, -3, 5"):
            with self.subTest(args=args):
                [msg] = self.alerts(f"    BITMAP PUT A, {args}\n")
                self.assertTrue(msg.startswith("Runtime error: the part is outside the BITMAP at line"), msg)

    def test_a_part_outside_the_canvas(self):
        [msg] = self.alerts("    BITMAP PUT A, 550, 0, 0, 0, 20, 5\n")
        self.assertTrue(msg.startswith("Runtime error: drawing outside the canvas"), msg)

    def test_a_mask_smaller_than_the_part(self):
        [msg] = self.alerts("    BITMAP MASK A, M, 0, 0\n")  # M is 20 wide, the image 40
        self.assertTrue(msg.startswith("Runtime error: the part is outside the BITMAP"), msg)

    def test_nothing_drawn_for_an_empty_part(self):
        self.assertEqual(self.alerts("    BITMAP PUT A, 0, 0, 0, 0, 0, 5\n    BITMAP MASK A, M, 0, 0, 0, 0, 5, 0\n"),
                         [])

    def test_compile_errors(self):
        cases = {
            "    BITMAP MASK A, Q, 0, 0\n": "BITMAP MASK's mask needs a BITMAP",
            "    BITMAP MASK A, M, 0\n": "BITMAP MASK takes the image, the mask and 2 or 6 more arguments",
            "    BITMAP PUT A, 0, 0, 1\n": "BITMAP PUT takes the bitmap and 2 or 6 more arguments",
            "    BITMAP PUT A, 0, 0, 0, 0, \"x\", 1\n": "expects INTEGER",
        }
        dims = "DIM A AS BITMAP * 40, 20\nDIM M AS BITMAP * 20, 20\nDIM Q AS INTEGER\n"
        for body, msg in cases.items():
            with self.subTest(body=body):
                with self.assertRaises(SourceError) as ctx:
                    check_source(program(body, dims))
                self.assertIn(msg, str(ctx.exception))
        with self.assertRaises(SourceError) as ctx:
            check_source("DIM A AS BITMAP * 8, 8\nDIM M AS BITMAP * 8, 8\nBITMAP MASK A, M, 0, 0\nEND\n")
        self.assertIn("needs a CANVAS", str(ctx.exception))


@requires_pasmo
class ContractTests(unittest.TestCase):
    def test_ink_and_mode_come_back_and_the_pointer_is_hidden(self):
        body = (PATTERN.format(w=40, h=20) + "    BITMAP GET A, 0, 0\n    BITMAP GET M, 0, 0\n"
                "    DRAW INK XOR\n    BITMAP PUT A, 100, 50, 3, 3, 20, 10\n    BITMAP MASK A, M, 200, 50, 1, 1, 30, 9\n"
                "    DRAW FILL 300, 50, 10, 10\n    DRAW PIXEL 300, 50\n")
        r = run(program(body, "DIM A AS BITMAP * 40, 20\nDIM M AS BITMAP * 40, 20\n"))
        self.assertEqual(r.px(300, 50), 0)  # XOR ink still: the black pixel flipped white
        self.assertEqual(r.px(301, 50), 1)
        self.assertEqual(r.cpu.mouse_draws_visible, 0)


if __name__ == "__main__":
    unittest.main()


LIBRARY = """SUB Stamp(Img AS BITMAP, Msk AS BITMAP, X AS INTEGER, Y AS INTEGER, F AS INTEGER)
    ' frame F of a strip of square frames, through its mask
    LOCAL S AS INTEGER
    S = BITMAPW(Img)
    BITMAP MASK Img, Msk, X, Y, 0, F * S, S, S
END SUB
SUB Copy(Img AS BITMAP, X AS INTEGER, Y AS INTEGER)
    BITMAP PUT Img, X, Y
    CALL Twice(Img, X + 40, Y)
END SUB
SUB Twice(B AS BITMAP, X AS INTEGER, Y AS INTEGER)
    BITMAP PUT B, X, Y, 0, 0, BITMAPW(B), BITMAPH(B) / 2
END SUB
SUB Grab(B AS BITMAP)
    BITMAP GET B, 0, 0
END SUB
"""


@requires_pasmo
class ParameterTests(unittest.TestCase):
    """M13: a BITMAP parameter refers to the caller's bitmap."""

    def test_a_library_draws_the_callers_bitmaps(self):
        body = (PATTERN.format(w=16, h=48) + "    CALL Grab(Sheet)\n    CALL Grab(Mask)\n"
                "    DRAW FILL 0, 100, 560, 60, 4\n    DRAW FILL 0, 200, 560, 60, 4\n"
                "    FOR I = 0 TO 2\n        CALL Stamp(Sheet, Mask, 100 + 30 * I, 200, I)\n    NEXT I\n"
                "    CALL Copy(Sheet, 300, 200)\n")
        src = "DIM Sheet AS BITMAP * 16, 48\nDIM Mask AS BITMAP * 16, 48\n" + LIBRARY.replace("SUB Stamp", "SUB Stamp", 1)
        src = program(body, src)
        r = run(src)
        for i in range(3):  # Sheet = Mask, so a white mask pixel draws white: frames of white
            for j in range(16):
                for k in range(16):
                    white = r.px(k, 16 * i + j) == 0
                    want = 0 if white else r.px(100 + 30 * i + k, 100 + j)
                    self.assertEqual(r.px(100 + 30 * i + k, 200 + j), want, (i, j, k))
        for j in range(48):  # Copy: the whole bitmap, then its top half 40 to the right
            for k in range(16):
                self.assertEqual(r.px(300 + k, 200 + j), r.px(k, j))
                if j < 24:
                    self.assertEqual(r.px(340 + k, 200 + j), r.px(k, j))

    def test_errors(self):
        dims = "DIM Sheet AS BITMAP * 16, 48\nDIM N AS INTEGER\n"
        cases = {
            "    CALL Grab(N)\n": "B (in GRAB) is a BITMAP parameter: pass it a BITMAP's name",
            "    CALL Grab(3)\n": "is a BITMAP parameter: pass it a BITMAP's name",
        }
        for body, msg in cases.items():
            with self.subTest(body=body):
                with self.assertRaises(SourceError) as ctx:
                    check_source(program(body, dims + "SUB Grab(B AS BITMAP)\n    BITMAP GET B, 0, 0\nEND SUB\n"))
                self.assertIn(msg, str(ctx.exception))
        with self.assertRaises(SourceError) as ctx:
            check_source(program("", dims + "SUB Bad\n    LOCAL B AS BITMAP\nEND SUB\n"))
        self.assertIn("declare a bitmap as DIM", str(ctx.exception))
        with self.assertRaises(SourceError) as ctx:
            check_source(program("    N = Sheet\n", dims))
        self.assertIn("cannot assign BITMAP", str(ctx.exception))
