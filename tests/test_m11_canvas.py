"""M11 Stage D1: DRAW TEXT x, y, text$, cell — text on a fixed grid.

Rosanne's fonts are proportional and no width call works in XAnne (M5d), so a
program cannot know where a character of DRAW TEXT ends. With a cell width
every character is drawn on its own at x + i * cell, so a caret or a
selection can be shown exactly with DRAW INVERT over whole cells (MDEDIT III).
Simulator evidence: what Rosanne draws is for the owner (XAnne).
"""
from __future__ import annotations

import unittest

from memguard import guarded_run
from pbas import SourceError, check_source, generate
from test_m9_canvas import OUT_ERR, origin, program
from toolchain import requires_pasmo

CELL_ERR = "Runtime error: a text cell is 11 to 64 pixels at line {}"


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> str:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return caught.exception.message

    def test_arguments(self):
        self.assertIn("DRAW TEXT takes 3 or 4 arguments", self.reject(program('DRAW TEXT 1, 2, "a", 11, 3\n')))
        self.assertIn("argument 4 must be INTEGER", self.reject(program('DRAW TEXT 1, 2, "a", "11"\n')))

    def test_only_programs_that_use_it_carry_it(self):
        plain = generate(check_source(program('DRAW TEXT 1, 2, "a"\n')))
        cells = generate(check_source(program('DRAW TEXT 1, 2, "a", 11\n')))
        self.assertIn("PB_CVCELL equ 0", plain)
        self.assertIn("PB_CVCELL equ 1", cells)
        self.assertIn("call rt_draw_cells", cells)


@requires_pasmo
class DrawTests(unittest.TestCase):
    def draw(self, paint: str):
        src = program(paint)
        r = guarded_run(src, events=[])
        self.assertEqual(r.violations, [])
        sx, sy, _, _ = origin(src)
        return r, sx, sy

    def test_each_character_in_its_cell(self):
        r, sx, sy = self.draw('DRAW TEXT 5, 10, "Hi you", 11\n')
        self.assertEqual(r.alerts, [])
        self.assertEqual(r.cpu.texts, [(sx + 5, sy + 10, "H", 0), (sx + 16, sy + 10, "i", 0),
                                       (sx + 38, sy + 10, "y", 0), (sx + 49, sy + 10, "o", 0),
                                       (sx + 60, sy + 10, "u", 0)], "the space is not drawn")
        # the pointer is hidden once for the whole text
        self.assertEqual([e[0] for e in r.cpu.os_log].count(111), 1)
        self.assertEqual([e[0] for e in r.cpu.os_log].count(112), 1)

    def test_cut_at_the_right_edge_and_odd_characters(self):
        # the canvas is 100 wide: (100 - 40) / 12 = 5 cells
        r, sx, sy = self.draw('DRAW TEXT 40, 0, "ABCDEFGH", 12\nDRAW TEXT 0, 44, "x" + CHR$(9) + "y", 20\n')
        self.assertEqual([t[2] for t in r.cpu.texts], ["A", "B", "C", "D", "E", "x", "?", "y"])
        self.assertEqual([t[0] - sx for t in r.cpu.texts][:5], [40, 52, 64, 76, 88])

    def test_xor_ink(self):
        r, _, _ = self.draw('DRAW INK XOR\nDRAW TEXT 0, 0, "ab", 11\n')
        self.assertEqual([t[3] for t in r.cpu.texts], [3, 3])

    def test_errors(self):
        for paint, alert in (('DRAW TEXT 0, 0, "a", 10', CELL_ERR), ('DRAW TEXT 0, 0, "a", 65', CELL_ERR),
                             ('DRAW TEXT 0, 0, "a", -11', CELL_ERR), ('DRAW TEXT 0, 45, "a", 11', OUT_ERR),
                             ('DRAW TEXT 100, 0, "a", 11', OUT_ERR)):
            with self.subTest(paint):
                r = guarded_run(program(paint + "\n"), events=[])
                self.assertEqual(r.violations, [])
                self.assertEqual(r.alerts, [alert.format(8)])
                self.assertTrue(r.cpu.exited)
        r = guarded_run(program('DRAW TEXT 0, 0, "a", 64\nDRAW TEXT 0, 0, "", 11\n'), events=[])
        self.assertEqual(r.alerts, [], "64 is allowed; an empty text draws nothing")


@requires_pasmo
class CellProbeTests(unittest.TestCase):
    """developer-tests/cellprb.pbas on the simulator: what the owner will see."""

    def test_probe(self):
        from pathlib import Path
        from pbas.layout import build_dialog
        path = Path(__file__).resolve().parents[1] / "developer-tests" / "cellprb.pbas"
        src = path.read_text(encoding="utf-8")
        prog = check_source(src, path=path)
        lay = build_dialog(prog, prog.windows[0], False)
        buttons = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
        _, sx, sy, _, _, _ = lay.canvas
        r = guarded_run(src, path=path, build_options={"runtime_sections": "all"},
                        events=[("mdown", sx + 4 + 11 * 7 + 6, sy + 5), ("mup", sx + 100, sy + 5),
                                ("click", buttons["Page"]), ("click", buttons["Quit"])])
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["P3 start: press OK and time until P3 done", "P3 done"])
        self.assertTrue(r.cpu.exited)
        glyphs = [t for t in r.cpu.texts if t[1] == sy]
        self.assertEqual("".join(t[2] for t in glyphs[:49]), "".join(chr(c) for c in range(33, 82)),
                         "row 1 from '!' (the space is not drawn), one per 11-pixel cell")
        self.assertEqual([t[0] - sx for t in glyphs[:3]], [15, 26, 37])
        page = [t for t in r.cpu.texts if t[2] == "A" and t[0] == sx + 4]
        self.assertGreaterEqual(len(page), 13, "the page: 13 rows starting with A")


if __name__ == "__main__":
    unittest.main()
