"""M15 W2: DRAW FONT n (dialog fonts 1..12), TEXTWIDTH in that font, the
measured right-edge cut and DRAW TEXT ... ALIGN (LANGUAGE-SPEC 5.6).

XAnne (owner, M15a T1/T2): all twelve dialog fonts draw on a canvas with
os_dialog_string (81) and each has its own widths (82). The simulator's widths
for fonts other than 7 are a MODEL (z80sim.dialog_font_width); these tests
check the runtime's logic, not Rosanne's fonts. Acceptance: M15c.
"""
from __future__ import annotations

import unittest

from memguard import guarded_run
from pbas import check_source, generate
from pbas.errors import SourceError
from toolchain import requires_pasmo
from z80sim import dialog_font_width

W, H = 400, 160


def src(paint: str, extra: str = "") -> str:
    return (f"DIM N AS INTEGER\nDIM T$ AS STRING * 120\nWINDOW Main, \"F\", LARGE\n"
            f"CANVAS {W}, {H}, PAINT Paint\nBUTTON \"Quit\", Quit\n"
            f"SUB Paint\n{paint}\nEND SUB\nSUB Quit\n    EXIT\nEND SUB\n{extra}END\n")


def run(paint, extra=""):
    r = guarded_run(src(paint, extra), events=[])
    assert r.violations == [], r.violations[:5]
    return r


def origin(r):
    at = r.symbols["cgcanvas"]
    m = r.cpu.mem
    return m[at] | m[at + 1] << 8, m[at + 2] | m[at + 3] << 8


def drawn(r):
    """[(canvas x, y, text, font)] of every DRAW TEXT."""
    ox, oy = origin(r)
    return [(x - ox, y - oy, t, f) for (x, y, t, _), f in zip(r.cpu.texts, r.cpu.text_fonts)]


def word(r, name):
    at = r.symbols[f"var_{name.lower()}"]
    return r.cpu.mem[at] | r.cpu.mem[at + 1] << 8


@requires_pasmo
class DrawFontTests(unittest.TestCase):
    def test_each_font_is_used(self):
        r = run("    FOR N = 1 TO 12\n        DRAW FONT N\n        DRAW TEXT 0, 0, \"F\"\n    NEXT N")
        self.assertEqual([f for *_, f in drawn(r)], list(range(1, 13)))

    def test_font_7_until_one_is_chosen(self):
        r = run("    DRAW TEXT 0, 0, \"a\"\n    DRAW FONT 3\n    DRAW TEXT 0, 20, \"b\"")
        self.assertEqual([f for *_, f in drawn(r)], [7, 3])

    def test_textwidth_measures_the_current_font(self):
        r = run("    DRAW FONT 12\n    N = TEXTWIDTH(\"Hello WM\")")
        self.assertEqual(word(r, "N"), dialog_font_width(b"Hello WM", 12))

    def test_the_cut_is_measured(self):
        long = "The quick brown fox jumps over the lazy dog " * 2
        for font in (1, 7, 12):
            with self.subTest(font=font):
                x = 260
                r = run(f"    DRAW FONT {font}\n    DRAW TEXT {x}, 0, \"{long}\"")
                (_, _, text, _), = drawn(r)
                room = W - x
                if font != 7:  # M15c F3: half a W + 1 px kept free (font 7's widths are exact)
                    room -= dialog_font_width(b"W", font) // 2 + 1
                self.assertTrue(long.startswith(text))
                self.assertLessEqual(dialog_font_width(text.encode(), font), room)
                self.assertGreater(dialog_font_width(long[:len(text) + 1].encode(), font), room)

    def test_narrow_text_is_no_longer_cut_at_11_px_a_character(self):
        narrow = "i" * 60  # 60 x 3 px = 180 px: fits 200 px, but 200 / 11 = 18 characters
        r = run(f"    DRAW FONT 7\n    DRAW TEXT 200, 0, \"{narrow}\"")
        self.assertEqual(drawn(r)[0][2], narrow)
        r = run(f"    DRAW TEXT 200, 0, \"{narrow}\"")  # no DRAW FONT: the RC1 rule
        self.assertEqual(drawn(r)[0][2], narrow[:18])

    def test_align(self):
        width = dialog_font_width(b"Centre me", 7)
        r = run("    DRAW TEXT 200, 0, \"Centre me\" ALIGN CENTRE\n"
                "    DRAW TEXT 200, 20, \"Centre me\" ALIGN RIGHT\n"
                "    DRAW TEXT 200, 40, \"Centre me\" ALIGN LEFT\n"
                "    DRAW TEXT 10, 60, \"Centre me\" ALIGN RIGHT\n"
                "    DRAW TEXT 200, 80, \"Centre me\"")
        xs = [x for x, *_ in drawn(r)]
        self.assertEqual(xs, [200 - width // 2, 200 - width, 200, 0, 200])

    def test_a_bad_font_is_a_runtime_error(self):
        for n in (0, 13, -1):
            with self.subTest(n=n):
                r = guarded_run(src(f"    DRAW FONT {n}"), events=[])
                self.assertTrue(any("a font is 1 to 12" in a for a in r.alerts), r.alerts)

    def test_a_refused_drawing_is_still_reported(self):
        # the font routines sit after rt_cv_refused, not between rt_cv_dg's
        # "ret nc" and the refusal it falls into
        r = guarded_run(src("    DRAW FONT 2\n    DRAW FILL 0, 0, 10, 10"), events=[], scr_direct_refuse=True)
        self.assertTrue(any("refused a drawing" in a for a in r.alerts), r.alerts)


class DrawFontCompileTests(unittest.TestCase):
    def test_rc1_programs_do_not_get_it(self):
        asm = generate(check_source(src("    DRAW TEXT 0, 0, \"x\"")))
        self.assertIn("PB_DWFONT equ 0", asm)
        asm = generate(check_source(src("    DRAW FONT 2")))
        self.assertIn("PB_DWFONT equ 1", asm)
        self.assertIn("PB_DWALIGN equ 0", asm)

    def test_errors(self):
        for paint, text in (("    DRAW TEXT 0, 0, \"x\", 12 ALIGN RIGHT", "ALIGN takes"),
                            ("    DRAW TEXT 0, 0, \"x\" ALIGN MIDDLE", "ALIGN takes"),
                            ("    DRAW FONT \"7\"", "must be INTEGER"),
                            ("    DRAW FONT", "takes 1 argument")):
            with self.subTest(paint=paint):
                with self.assertRaises(SourceError) as cm:
                    check_source(src(paint))
                self.assertIn(text, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
