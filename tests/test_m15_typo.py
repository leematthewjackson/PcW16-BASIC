"""M15 W3: screen typography — TYPE FONT, DRAW TYPE, TYPEWIDTH, TYPEHEIGHT
(LANGUAGE-SPEC 5.6).

XAnne (owner, M15a T4a-T4e): os_typo_charscreen (93) draws slot 0 at 10
points, plain, bold and italic, mode 0, inside a canvas. Everything else here
is the simulator's MODEL (z80sim: widths scaled from font 7, a pixel of
25/1800", ascender and descender from the size): these tests check the
runtime's logic, guards and slot sharing with PAGE, not Rosanne's fonts.
Acceptance of the other sizes and of the y reference: M15c.
"""
from __future__ import annotations

import unittest

from memguard import guarded_run
from pbas import check_source, generate
from pbas.errors import SourceError
from toolchain import requires_pasmo
from z80sim import TYPO_FONTS, typo_width

W, H = 400, 200
SWISS, TIMES = (f[0] for f in TYPO_FONTS)


def src(paint: str, extra: str = "", dims: str = "") -> str:
    return (f"DIM N AS INTEGER\nDIM M AS INTEGER\nDIM T$ AS STRING * 120\n{dims}WINDOW Main, \"T\", LARGE\n"
            f"CANVAS {W}, {H}, PAINT Paint\nBUTTON \"Quit\", Quit\n"
            f"SUB Paint\n{paint}\nEND SUB\nSUB Quit\n    EXIT\nEND SUB\n{extra}END\n")


def run(paint, extra="", events=None, **options):
    r = guarded_run(src(paint, extra), events=events or [], build_options=options or None)
    assert r.violations == [], r.violations[:5]
    return r


def origin(r):
    at = r.symbols["cgcanvas"]
    m = r.cpu.mem
    return m[at] | m[at + 1] << 8, m[at + 2] | m[at + 3] << 8


def chars(r):
    """[(canvas x, y, char, style, mode, (font id, size))]"""
    ox, oy = origin(r)
    return [(x - ox, y - oy, c, s, m, f) for x, y, c, s, m, f in r.cpu.typo_chars]


def word(r, name):
    at = r.symbols[f"var_{name.lower()}"]
    return r.cpu.mem[at] | r.cpu.mem[at + 1] << 8


def advances(text, size, bold=False):
    """Pixel offsets of each character and the end, as the runtime rounds."""
    total, out = 0, []
    for ch in text.encode("latin-1"):
        out.append((total + 12) // 25)
        total += typo_width(ch, size, bold)
    return out, (total + 12) // 25


def height(size):
    return (size * 25 * 4 // 5 + size * 25 // 4 + 24) // 25


@requires_pasmo
class DrawTypeTests(unittest.TestCase):
    def test_a_line_at_10_points(self):
        r = run("    TYPE FONT SWISS, 10\n    DRAW TYPE 20, 30, \"Hello\"")
        xs, _ = advances("Hello", 10)
        self.assertEqual([(x, y, c) for x, y, c, *_ in chars(r)], [(20 + d, 30, c) for d, c in zip(xs, "Hello")])
        self.assertEqual({f for *_, f in chars(r)}, {(SWISS, 10)})
        self.assertEqual({(s, m) for _, _, _, s, m, _ in chars(r)}, {(0, 0)})

    def test_y_is_the_top_rosanne_gets_the_baseline(self):
        # M15c T2 (owner, XAnne): os_typo_charscreen's y is the baseline; the runtime
        # passes the line's top + the ascender, so the text hangs below y
        r = run("    TYPE FONT SWISS, 72\n    DRAW TYPE 0, 0, \"Ag\"")
        asc = (72 * 25 * 4 // 5 + 24) // 25
        _, oy = origin(r)
        (fn, (x, y, c, st, md)), = [e for e in r.cpu.os_log if e[0] == 93][:1]
        self.assertEqual(y, oy + 0 + asc)
        self.assertEqual(chars(r)[0][1], 0)  # the cell's top: the canvas's top

    def test_italic_keeps_its_lean_inside(self):
        text = "W" * 60
        r = run(f"    TYPE FONT SWISS, 24, ITALIC\n    DRAW TYPE 100, 80, \"{text}\"")
        upright = run(f"    TYPE FONT SWISS, 24\n    DRAW TYPE 100, 80, \"{text}\"")
        asc = (24 * 25 * 4 // 5 + 24) // 25
        xs, _ = advances(text, 24)
        ends = xs[1:]
        n = len(chars(r))
        self.assertLessEqual(100 + ends[n - 1], W - asc // 4)
        self.assertGreater(100 + ends[n], W - asc // 4)
        self.assertLessEqual(n, len(chars(upright)))

    def test_times_bold_italic_and_xor(self):
        r = run("    TYPE FONT TIMES, 12, BOLD, ITALIC\n    DRAW INK XOR\n    DRAW TYPE 0, 10, \"Ab\"")
        xs, _ = advances("Ab", 12, bold=True)
        self.assertEqual([(x, c, s, m, f) for x, _, c, s, m, f in chars(r)],
                         [(xs[0], "A", 3, 3, (TIMES, 12)), (xs[1], "b", 3, 3, (TIMES, 12))])

    def test_times_10_until_a_font_is_chosen(self):
        r = run("    DRAW TYPE 0, 0 + 20, \"x\"\n    N = TYPEHEIGHT")
        self.assertEqual(chars(r)[0][5], (TIMES, 10))
        self.assertEqual(word(r, "N"), height(10))

    def test_typewidth_is_the_drawn_advance(self):
        text = "Typography, at 18 points"
        r = run(f"    TYPE FONT SWISS, 18\n    N = TYPEWIDTH(\"{text}\")\n    M = TYPEHEIGHT\n"
                f"    DRAW TYPE 0, 20, \"{text}\"")
        _, end = advances(text, 18)
        self.assertEqual(word(r, "N"), end)
        self.assertEqual(word(r, "M"), height(18))
        self.assertEqual("".join(c for _, _, c, *_ in chars(r)), text)

    def test_the_cut_at_the_right_edge(self):
        text = "W" * 60
        for size in (10, 24, 72):
            with self.subTest(size=size):
                x = 100
                r = run(f"    TYPE FONT SWISS, {size}\n    DRAW TYPE {x}, 80, \"{text}\"")
                drawn = chars(r)
                xs, _ = advances(text, size)
                n = len(drawn)
                ends = xs[1:] + [advances(text, size)[1]]
                self.assertTrue(0 < n < len(text))
                self.assertLessEqual(x + ends[n - 1], W)  # the last one drawn ends inside
                self.assertGreater(x + ends[n], W)  # the next would not

    def test_the_line_must_fit_the_canvas(self):
        for paint in ("    TYPE FONT SWISS, 10\n    DRAW TYPE 0, 195, \"x\"",
                      "    TYPE FONT SWISS, 72\n    DRAW TYPE 0, 150, \"x\"",
                      "    DRAW TYPE 400, 50, \"x\"", "    DRAW TYPE -1, 50, \"x\""):
            with self.subTest(paint=paint):
                r = guarded_run(src(paint), events=[])
                self.assertTrue(any("drawing outside the canvas" in a for a in r.alerts), r.alerts)

    def test_a_bad_size_is_a_runtime_error(self):
        r = guarded_run(src("    N = 13\n    TYPE FONT SWISS, N"), events=[])
        self.assertTrue(any("a type size is 6, 8" in a for a in r.alerts), r.alerts)

    def test_every_size_draws(self):
        lines = "".join(f"    TYPE FONT SWISS, {s}\n    DRAW TYPE 0, 100, \"Ag\"\n"
                        for s in (6, 8, 10, 11, 12, 14, 18, 24, 36, 72))
        r = run(lines.rstrip("\n"))
        self.assertEqual([f[1] for *_, f in chars(r)][::2], [6, 8, 10, 11, 12, 14, 18, 24, 36, 72])

    def test_the_font_is_defined_once_while_it_stays(self):
        r = run("    TYPE FONT SWISS, 10\n    FOR N = 1 TO 5\n        DRAW TYPE 0, N * 20, \"ab\"\n    NEXT N\n"
                "    TYPE FONT SWISS, 10, BOLD\n    DRAW TYPE 0, 140, \"ab\"")
        self.assertEqual([fn for fn, _ in r.cpu.os_log].count(87), 1)  # os_typo_def
        self.assertEqual([fn for fn, _ in r.cpu.os_log].count(83), 1)  # os_typo_init

    def test_runtime_bank(self):
        r = run("    TYPE FONT TIMES, 14\n    DRAW TYPE 10, 20, \"Banked\"\n    N = TYPEWIDTH(\"Banked\")",
                runtime_sections="all")
        self.assertEqual("".join(c for _, _, c, *_ in chars(r)), "Banked")
        self.assertEqual(word(r, "N"), advances("Banked", 14)[1])


@requires_pasmo
class SharedWithPageTests(unittest.TestCase):
    PRINT = ("SUB Report\n    PAGE NEW\n    PAGE FONT 18, BOLD\n    PAGE TEXT 0, 0, \"Title\"\n"
             "    N = PAGEWIDTH(\"Title\")\n    PAGE CLOSE\nEND SUB\n")

    def test_page_and_screen_type_share_slot_0(self):
        paint = ("    TYPE FONT SWISS, 10\n    DRAW TYPE 0, 20, \"a\"\n    CALL Report\n"
                 "    DRAW TYPE 0, 40, \"b\"\n    M = TYPEWIDTH(\"WW\")")
        r = run(paint, self.PRINT)
        self.assertEqual([f for *_, f in chars(r)], [(SWISS, 10), (SWISS, 10)])
        self.assertEqual(word(r, "N"), (sum(typo_width(c, 18, True) for c in b"Title") + 24) // 25)
        self.assertEqual(word(r, "M"), advances("WW", 10)[1])
        self.assertEqual([fn for fn, _ in r.cpu.os_log].count(83), 1)  # one os_typo_init

    def test_screen_type_between_page_font_and_page_text(self):
        # the PAGE font is defined again in slot 0 before PAGE TEXT measures with it
        extra = ("SUB Report\n    PAGE NEW\n    PAGE FONT 18, BOLD\n    DRAW TYPE 0, 20, \"a\"\n"
                 "    N = PAGEWIDTH(\"Title\")\n    PAGE TEXT 0, 0, \"Title\"\n    PAGE CLOSE\nEND SUB\n")
        r = run("    TYPE FONT SWISS, 10\n    CALL Report", extra)
        self.assertEqual(word(r, "N"), (sum(typo_width(c, 18, True) for c in b"Title") + 24) // 25)
        self.assertEqual(r.cpu.typo_slot, (TIMES, 18))

    def test_page_first_then_screen_then_page(self):
        paint = "    CALL Report\n    DRAW TYPE 0, 20, \"a\"\n    CALL Report"
        r = run(paint, self.PRINT)
        self.assertEqual(word(r, "N"), (sum(typo_width(c, 18, True) for c in b"Title") + 24) // 25)
        self.assertEqual(chars(r)[0][5][1], 10)


class TypeCompileTests(unittest.TestCase):
    def test_rc1_programs_do_not_get_it(self):
        asm = generate(check_source(src("    DRAW TEXT 0, 0, \"x\"")))
        self.assertIn("PB_TYPO equ 0", asm)
        asm = generate(check_source(src("    DRAW TYPE 0, 0, \"x\"")))
        self.assertIn("PB_TYPO equ 1", asm)
        self.assertIn("PB_TYPG equ 0", asm)

    def test_a_record_type_named_font_is_still_a_record(self):
        check_source("TYPE Font\n    Size AS INTEGER\nEND TYPE\nDIM F AS Font\nF.Size = 3\nEND\n")

    def test_errors(self):
        for paint, text in (("    TYPE FONT ARIAL, 10", "SWISS or TIMES"),
                            ("    TYPE FONT SWISS, 13", "a type size is"),
                            ("    TYPE FONT SWISS, 10, ITALIC, BOLD", "BOLD, then ITALIC"),
                            ("    TYPE FONT SWISS, \"10\"", "must be INTEGER"),
                            ("    DRAW TYPE 0, 0", "takes 3 arguments"),
                            ("    DRAW TYPE 0, 0, 5", "must be STRING"),
                            ("    N = TYPEWIDTH(5)", "expects a STRING")):
            with self.subTest(paint=paint):
                with self.assertRaises(SourceError) as cm:
                    check_source(src(paint))
                self.assertIn(text, str(cm.exception))
        with self.assertRaises(SourceError) as cm:
            check_source("DIM N AS INTEGER\nN = TYPEHEIGHT\nEND\n")
        self.assertIn("no CANVAS", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
