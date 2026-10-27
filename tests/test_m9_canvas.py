"""M9 Stage B — CANVAS, DRAW and canvas events (LANGUAGE-SPEC §5.5).

Built with Pasmo and run on tests/z80sim.py, whose M9 screen model keeps a
640 x 480 bitmap: BIOS line / rectangle / pixel and os_scr_direct blocks are
drawn into it, os_dialog_string draws each character as an 11 x 16 black
cell (a model, not Rosanne's font). What Rosanne really draws, and which
events it really sends a program, is for GFXPROBE in XAnne.
"""
from __future__ import annotations

import unittest

import z80sim
from memguard import guarded_run, string_var
from pbas import SourceError, check_source, generate
from pbas.layout import build_dialog
from test_m6_phase1 import numbers
from toolchain import requires_pasmo

OUT_ERR = "Runtime error: drawing outside the canvas at line {}"
OFF_ERR = "Runtime error: the canvas is not on screen at line {}"
SHADE_ERR = "Runtime error: a shade is 0 to 8 at line {}"


def program(paint: str = "", extra: str = "", options: str = ", PAINT P, MOUSE M, KEYS K",
            size: str = "100, 60", before: str = "") -> str:
    return (f'DIM Log$ AS STRING\nDIM N AS INTEGER\n{before}WINDOW "C", LARGE\nLABEL Log$\n'
            f'CANVAS {size}{options}\nBUTTON "Quit", Q\n'
            f"SUB P\n{paint}END SUB\n"
            'SUB M\nLog$ = "M" + STR$(MOUSEEVENT) + " " + STR$(MOUSEX) + "," + STR$(MOUSEY)\nEND SUB\n'
            'SUB K\nN = N + 1\nLog$ = "K" + STR$(KEYCODE) + "." + STR$(KEYSHIFT) + "#" + STR$(N)\nEND SUB\n'
            f"SUB Q\nEXIT\nEND SUB\n{extra}END\n")


def origin(src: str) -> tuple[int, int, int, int]:
    p = check_source(src)
    lay = build_dialog(p, p.windows[0], False)
    return lay.canvas[1:5]


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return caught.exception

    def test_canvas_declaration(self):
        self.assertIn("requires a WINDOW", self.reject("CANVAS 10, 10\nEND\n").message)
        self.assertIn("16 to 568", self.reject(program(size="15, 50")).message)
        self.assertIn("16 to 568", self.reject(program(size="100, 301")).message)
        self.assertIn("one CANVAS", self.reject(program().replace(
            'BUTTON "Quit"', 'CANVAS 20, 20\nBUTTON "Quit"')).message)
        self.assertIn("expected PAINT, MOUSE or KEYS", self.reject(program(options=", PAINT P, PAINT P")).message)
        self.assertIn("not defined by SUB", self.reject(program(options=", PAINT Nothing")).message)
        self.assertIn("handlers are SUBs without parameters", self.reject(
            program(options=", PAINT F") .replace("SUB Q", "FUNCTION F() AS INTEGER\nRETURN 1\nEND FUNCTION\nSUB Q")).message)
        self.assertIn("at most 330 pixels wide", self.reject(
            program(size="400, 50").replace(', LARGE', '')).message)
        self.assertIn("no room", self.reject(program(size="500, 300")).message)

    def test_draw_statements(self):
        self.assertIn("DRAW needs a CANVAS", self.reject('DRAW CLEAR\nEND\n').message)
        self.assertIn("DRAW LINE takes 4 arguments", self.reject(program("DRAW LINE 1, 2, 3\n")).message)
        self.assertIn("DRAW FILL takes 4 or 5", self.reject(program("DRAW FILL 1, 2, 3\n")).message)
        self.assertIn("must be INTEGER", self.reject(program('DRAW BOX 1, "2", 3, 4\n')).message)
        self.assertIn("must be STRING", self.reject(program("DRAW TEXT 1, 2, 3\n")).message)
        self.assertIn("BLACK, WHITE or XOR", self.reject(program("DRAW INK RED\n")).message)
        self.assertIn("expected CLEAR, FILL", self.reject(program("DRAW CIRCLE 1, 2\n")).message)
        self.assertIn("no CANVAS", self.reject('DIM N AS INTEGER\nN = KEYCODE()\nEND\n').message)

    def test_words_stay_free_without_a_canvas(self):
        # Programs without a CANVAS may use these names as variables.
        check_source("DIM Draw AS INTEGER\nDIM Canvas AS INTEGER\nDIM KeyCode AS INTEGER\n"
                     "DIM MouseX AS INTEGER\nDraw = 1\nCanvas = Draw + KeyCode + MouseX\nEND\n")

    def test_layout(self):
        sx, sy, w, h = origin(program())
        self.assertEqual((w, h), (100, 60))
        self.assertEqual((sx, sy), (20 + 26 + 1, 50 + 48 + 32 + 1), "frame at x=26 below the label row")
        p = check_source(program())
        lay = build_dialog(p, p.windows[0], False)
        frame = next(o for o in lay.objects if o.kind == "CANVAS")
        self.assertEqual(frame.definition[0], 1, "an ob_box")
        self.assertEqual(frame.number, lay.canvas[0])


@requires_pasmo
class DrawTests(unittest.TestCase):
    def draw(self, paint: str, **options):
        src = program(paint)
        r = guarded_run(src, events=[], **options)
        self.assertEqual(r.violations, [])
        sx, sy, w, h = origin(src)
        return r, sx, sy, w, h

    def test_clear_box_line_pixel(self):
        r, sx, sy, w, h = self.draw("DRAW CLEAR\nDRAW BOX 0, 0, 100, 60\nDRAW LINE 10, 10, 20, 10\nDRAW PIXEL 50, 30\n")
        cpu = r.cpu
        for x, y in ((0, 0), (99, 0), (0, 59), (99, 59), (50, 0), (0, 30)):
            self.assertEqual(cpu.pixel(sx + x, sy + y), 1, (x, y))
        self.assertEqual(cpu.pixel(sx + 1, sy + 1), 0)
        self.assertEqual([cpu.pixel(sx + x, sy + 10) for x in range(9, 22)], [0] + [1] * 11 + [0])
        self.assertEqual(cpu.pixel(sx + 50, sy + 30), 1)
        self.assertEqual(cpu.pixel(sx + 100, sy), 0, "nothing beyond the canvas")
        self.assertEqual(cpu.mouse_draws_visible, 0, "the pointer is hidden around BIOS drawing")
        self.assertEqual(cpu.mouse_hidden, 0)
        self.assertEqual((cpu.bios_ink, cpu.bios_mode), (0, 0), "ink and mode put back")
        r, sx, sy, w, h = self.draw("DRAW LINE 0, 0, 5, 5\nDRAW INK XOR\nDRAW BOX 1, 1, 4, 4\n",
                                    bios_ink=1, bios_mode=1)
        self.assertEqual(r.cpu.pixel(sx, sy), 1, "drawn in the program's black ink")
        self.assertEqual((r.cpu.bios_ink, r.cpu.bios_mode), (1, 1), "the BIOS's own ink and mode put back")

    def test_fill_invert_ink(self):
        r, sx, sy, w, h = self.draw("DRAW FILL 0, 0, 10, 10\nDRAW FILL 10, 0, 10, 10, 8\n"
                                    "DRAW INVERT 5, 0, 10, 1\nDRAW INK WHITE\nDRAW PIXEL 0, 5\n"
                                    "DRAW INK XOR\nDRAW PIXEL 15, 5\nDRAW PIXEL 15, 5\nDRAW PIXEL 16, 5\n")
        cpu = r.cpu
        row = [cpu.pixel(sx + x, sy) for x in range(20)]
        self.assertEqual(row, [1] * 5 + [0] * 5 + [1] * 5 + [0] * 5)
        self.assertEqual(cpu.pixel(sx, sy + 5), 0, "white ink")
        self.assertEqual(cpu.pixel(sx + 15, sy + 5), 0, "XOR twice")
        self.assertEqual(cpu.pixel(sx + 16, sy + 5), 1, "XOR on white")
        greys = [e for e in cpu.draw_log if e[0] == "direct" and e[1] == 3]
        self.assertEqual([g[6][0] for g in greys], [0], "shade = dg_blk_grey value")
        whites = [e for e in cpu.draw_log if e[0] == "direct" and e[1] == 1]
        self.assertEqual([w[2:6] for w in whites], [(sx + 10, sy, 10, 10)], "shade 8 is dg_blk_white")

    def test_lines_in_every_direction(self):
        # XAnne M9 (KI-49): the GFXPROBE diagonal was missing. Rosanne 1.12's
        # bios_line draws only horizontal and vertical lines (the simulator
        # ignores a sloped call, as 1.12 does), so the runtime draws a sloped
        # line as runs along its major axis: both ends, one pixel per step of
        # the major axis, 8-connected, and no sloped call reaches the BIOS.
        cases = [(10, 10, 20, 10), (10, 10, 10, 30), (0, 0, 5, 5), (0, 0, 9, 3), (9, 3, 0, 0), (0, 0, 3, 9),
                 (3, 9, 0, 0), (0, 59, 99, 0), (99, 0, 0, 59), (5, 5, 6, 40), (0, 0, 99, 59), (50, 10, 10, 11)]
        for c in cases:
            with self.subTest(line=c):
                r, sx, sy, w, h = self.draw("DRAW CLEAR\nDRAW LINE %d, %d, %d, %d\n" % c)
                self.assertEqual(r.alerts, [])
                self.assertEqual(r.cpu.bios_sloped_lines, 0, "no sloped bios_line")
                got = {(x, y) for y in range(h) for x in range(w) if r.cpu.pixel(sx + x, sy + y)}
                self.assertIn(c[:2], got)
                self.assertIn(c[2:], got)
                major = max(abs(c[2] - c[0]), abs(c[3] - c[1]))
                self.assertEqual(len(got), major + 1)
                for x, y in got - {c[2:]}:  # each pixel has a neighbour nearer the end
                    self.assertTrue(any((x + i, y + j) in got and max(abs(x + i - c[2]), abs(y + j - c[3]))
                                        < max(abs(x - c[2]), abs(y - c[3]))
                                        for i in (-1, 0, 1) for j in (-1, 0, 1)), (x, y))
                self.assertEqual(r.cpu.mouse_draws_visible, 0, "the pointer is hidden throughout")
        r, sx, sy, w, h = self.draw("DRAW CLEAR\nDRAW INK XOR\nDRAW LINE 0, 0, 99, 37\nDRAW LINE 0, 0, 99, 37\n")
        self.assertEqual(r.cpu.canvas_pixels(sx, sy, w, h), ["." * w] * h, "XOR twice: each pixel set once")

    def test_every_shade(self):
        # XAnne M9: Rosanne 1.12 refused dg_blk_grey with grey 8 (GFXPROBE
        # line 44, MDEDIT line 79). Shades 0..7 go to dg_blk_grey, 8 to
        # dg_blk_white; the simulator refuses grey 8 as Rosanne does.
        src = program("FOR I = 0 TO 8\nDRAW FILL I * 10, 0, 10, 36, I\nNEXT I\n",
                      before="DIM I AS INTEGER\n")
        r = guarded_run(src, events=[])
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, [])
        sx, sy, w, h = origin(src)
        direct = [e for e in r.cpu.draw_log if e[0] == "direct"]
        self.assertEqual([(e[1], e[6][0]) if e[1] == 3 else (e[1],) for e in direct],
                         [(3, i) for i in range(8)] + [(1,)])
        self.assertEqual(r.cpu.pixel(sx + 8 * 10, sy), 0, "shade 8 white")
        self.assertEqual(r.cpu.pixel(sx, sy), 1, "shade 0 black")

    def test_rosanne_refusal_is_reported(self):
        # Whatever Rosanne refuses stops the program with the line number.
        src = program("N = 1\nDRAW FILL 0, 0, 10, 10\n")
        r = guarded_run(src, events=[], scr_direct_refuse=True)
        line = src.splitlines().index("DRAW FILL 0, 0, 10, 10") + 1
        self.assertEqual(r.alerts[-1], f"Runtime error: Rosanne refused a drawing at line {line}")

    def test_scroll(self):
        paint = ("DRAW CLEAR\nDRAW PIXEL 5, 10\nDRAW PIXEL 6, 59\nDRAW SCROLL 0, 0, 100, 60, 0, -4\n")
        r, sx, sy, w, h = self.draw(paint)
        cpu = r.cpu
        self.assertEqual(cpu.pixel(sx + 5, sy + 6), 1)
        self.assertEqual(cpu.pixel(sx + 5, sy + 10), 0)
        self.assertEqual(cpu.pixel(sx + 6, sy + 55), 1)
        self.assertEqual([cpu.pixel(sx + x, sy + y) for y in range(56, 60) for x in range(100)], [0] * 400,
                         "the uncovered strip is white")
        r, sx, sy, w, h = self.draw("DRAW CLEAR\nDRAW PIXEL 0, 0\nDRAW SCROLL 0, 0, 20, 20, 3, 2\n")
        self.assertEqual(r.cpu.pixel(sx + 3, sy + 2), 1)
        self.assertEqual(r.cpu.pixel(sx, sy), 0)
        r, sx, sy, w, h = self.draw("DRAW CLEAR\nDRAW PIXEL 19, 19\nDRAW SCROLL 0, 0, 20, 20, -3, 0\n")
        self.assertEqual(r.cpu.pixel(sx + 16, sy + 19), 1)
        self.assertEqual([r.cpu.pixel(sx + x, sy + 19) for x in range(17, 20)], [0, 0, 0])

    def test_text(self):
        r, sx, sy, w, h = self.draw('DRAW TEXT 5, 10, "Hello"\nDRAW TEXT 40, 0, "ABCDEFGHIJ"\n'
                                    'DRAW TEXT 0, 44, "x" + CHR$(9) + "y" + CHR$(230)\n')
        self.assertEqual(r.cpu.texts, [(sx + 5, sy + 10, "Hello", 0),
                                       (sx + 40, sy, "ABCDE", 0),
                                       (sx, sy + 44, "x?y?", 0)])

    def test_bounds(self):
        cases = ["DRAW FILL -1, 0, 5, 5", "DRAW FILL 0, 0, 101, 5", "DRAW FILL 96, 0, 5, 5",
                 "DRAW FILL 0, 55, 5, 6", "DRAW BOX 0, 0, -1, 5", "DRAW LINE 0, 0, 100, 0",
                 "DRAW LINE 0, 60, 1, 1", "DRAW PIXEL 100, 0", "DRAW PIXEL 0, -1",
                 "DRAW TEXT 0, 45, \"x\"", "DRAW TEXT 100, 0, \"x\"", "DRAW INVERT 0, 0, 0, 61",
                 "DRAW SCROLL 0, 0, 10, 10, 10, 0", "DRAW SCROLL 0, 0, 10, 10, 0, -10"]
        for paint in cases:
            with self.subTest(paint):
                src = program(paint + "\n")
                r = guarded_run(src, events=[])
                self.assertEqual(r.violations, [])
                self.assertEqual(r.alerts, [OUT_ERR.format(8)])
                self.assertTrue(r.cpu.exited)
        r = guarded_run(program("DRAW FILL 0, 0, 5, 5, 9\n"), events=[])
        self.assertEqual(r.alerts, [SHADE_ERR.format(8)])
        r = guarded_run(program("DRAW FILL 0, 0, 0, 0\nDRAW BOX 0, 0, 100, 60\nDRAW FILL 0, 0, 100, 60\n"),
                        events=[])
        self.assertEqual(r.alerts, [], "the whole canvas, and an empty rectangle, are fine")

    def test_not_on_screen(self):
        r = guarded_run(program(extra="DRAW CLEAR\n"), events=[])
        self.assertEqual(r.alerts, [OFF_ERR.format(19)])


@requires_pasmo
class EventTests(unittest.TestCase):
    def run_events(self, events, paint="DRAW CLEAR\n", extra=""):
        src = program(paint, extra)
        n = numbers(src)
        sx, sy, w, h = origin(src)
        script = [e(n, sx, sy) if callable(e) else e for e in events]
        r = guarded_run(src, events=script)
        self.assertEqual(r.violations, [])
        return r, n

    def test_keys(self):
        r, _ = self.run_events([("key", 65, 1)])
        self.assertEqual(string_var(r, "LOG$"), "K65.1#1")
        r, _ = self.run_events([("key", 0xE5, 4), ("key", 8, 0)])
        self.assertEqual(string_var(r, "LOG$"), "K8.0#2")

    def test_cursor_keys_on_a_focused_object(self):
        for evtype, code in ((4, 224), (5, 225), (6, 230), (7, 231), (8, 232), (9, 233), (12, 32)):
            with self.subTest(evtype=evtype):
                r, n = self.run_events([lambda n, sx, sy, t=evtype: ("objevent", n["Quit"], t)])
                self.assertEqual(string_var(r, "LOG$"), f"K{code}.0#1")
        r, n = self.run_events([lambda n, sx, sy: ("objevent", n["Quit"], 10)])
        self.assertEqual(string_var(r, "LOG$"), "", "focus moves are not keys")

    def test_text_field_keeps_its_keys(self):
        src = program().replace('BUTTON "Quit"', 'TEXTBOX Name$\nBUTTON "Quit"')
        n = numbers(src)
        r = guarded_run(src, events=[("objevent", n["NAME$"], 4), ("objevent", n["Quit"], 4)])
        self.assertEqual(r.violations, [])
        self.assertEqual(string_var(r, "LOG$"), "K224.0#1", "only the button's Up reached KEYS")

    def test_mouse_press_drag_release(self):
        r, _ = self.run_events([lambda n, sx, sy: ("mdown", sx + 10, sy + 20),
                                lambda n, sx, sy: ("mmove", sx + 12, sy + 25)])
        self.assertEqual(string_var(r, "LOG$"), "M2 12,25")
        r, _ = self.run_events([lambda n, sx, sy: ("mdown", sx + 10, sy + 20),
                                lambda n, sx, sy: ("mmove", sx + 200, sy - 5),
                                lambda n, sx, sy: ("mup", sx + 201, sy - 6)])
        self.assertEqual(string_var(r, "LOG$"), "M3 201,-6", "a drag may leave the canvas")
        r, _ = self.run_events([lambda n, sx, sy: ("mdown", sx - 1, sy + 20),
                                lambda n, sx, sy: ("mmove", sx + 5, sy + 5),
                                lambda n, sx, sy: ("mup", sx + 5, sy + 5)])
        self.assertEqual(string_var(r, "LOG$"), "", "a press outside starts nothing")
        r, _ = self.run_events([lambda n, sx, sy: ("mdown", sx + 1, sy + 1),
                                lambda n, sx, sy: ("mmove", sx + 2, sy + 2, 0)])
        self.assertEqual(string_var(r, "LOG$"), "M3 2,2", "button up while moving = release")

    def test_click_on_the_canvas_object(self):
        src = program()
        p = check_source(src)
        frame = build_dialog(p, p.windows[0], False).canvas[0]
        r, _ = self.run_events([lambda n, sx, sy: ("clickat", frame, sx + 7, sy + 9)])
        self.assertEqual(string_var(r, "LOG$"), "M1 7,9")
        r, _ = self.run_events([lambda n, sx, sy: ("clickat", frame, sx - 1, sy + 9)])
        self.assertEqual(string_var(r, "LOG$"), "", "on the frame line itself")

    def test_paint_runs_at_open_and_after_an_alert(self):
        paint = 'N = N + 1\nDRAW CLEAR\n'
        extra = ""
        src = program(paint).replace('SUB Q\nEXIT', 'SUB Q\nMESSAGE "hi"\nIF N > 5 THEN\nEXIT\nEND IF')
        n = numbers(src)
        r = guarded_run(src, events=[("click", n["Quit"])])
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["hi"])
        self.assertEqual(sum(1 for e in r.cpu.draw_log if e[0] == "direct" and e[1] == 1), 2,
                         "PAINT at open, then once more after the alert")

    def test_alert_inside_paint_does_not_loop(self):
        src = program('MESSAGE "painting"\nDRAW CLEAR\n')
        n = numbers(src)
        r = guarded_run(src, events=[("key", 65), ("click", n["Quit"])])
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["painting"])
        self.assertTrue(r.cpu.exited)

    def test_canvas_in_a_second_window(self):
        src = ('DIM Log$ AS STRING\nWINDOW A, "First"\nBUTTON "Go", Go\nWINDOW B, "Second", LARGE\n'
               'CANVAS 50, 50, PAINT P, KEYS K\nBUTTON "Back", Back\n'
               'SUB P\nDRAW CLEAR\nDRAW PIXEL 1, 1\nEND SUB\nSUB K\nLog$ = STR$(KEYCODE)\nEND SUB\n'
               'SUB Go\nSHOW B\nEND SUB\nSUB Back\nSHOW A\nEND SUB\nEND\n')
        layouts = [build_dialog(check_source(src), w, False) for w in check_source(src).windows]
        go = next(o.number for o in layouts[0].objects if o.text == "Go")
        back = next(o.number for o in layouts[1].objects if o.text == "Back")
        r = guarded_run(src, events=[("key", 65), ("click", go), ("key", 66), ("click", back), ("key", 67)])
        self.assertEqual(r.violations, [])
        self.assertEqual(string_var(r, "LOG$"), "66", "keys reach KEYS only while its window is open")
        self.assertEqual(sum(1 for e in r.cpu.draw_log if e[0] == "pixel"), 1)


if __name__ == "__main__":
    unittest.main()
