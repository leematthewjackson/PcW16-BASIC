"""M15 W4: several named canvases, DRAW ON, FOCUS Canvas (LANGUAGE-SPEC 5.6).

A canvas is the runtime's own construct (a box of the dialog drawn on
directly), so nothing new is asked of Rosanne; event delivery to the right
canvas is the runtime's logic and is checked here in the simulator. One
canvas keeps the RC1 code (PB_CVMULTI 0): tests/test_m9_canvas.py and the
M15 diffbuild cover it. Acceptance: M15c.
"""
from __future__ import annotations

import unittest

from memguard import guarded_run, string_var
from pbas import SourceError, check_source, generate
from pbas.layout import build_dialog
from toolchain import requires_pasmo

HANDLERS = (
    'SUB PalPaint\n    DRAW FILL 0, 0, 4, 4\nEND SUB\n'
    'SUB BoardPaint\n    DRAW FILL 0, 0, 6, 6\nEND SUB\n'
    'SUB PalMouse\n    Log$ = Log$ + "p" + STR$(MOUSEEVENT) + ":" + STR$(MOUSEX) + "," + STR$(MOUSEY) + " "\n'
    '    DRAW FILL MOUSEX, MOUSEY, 1, 1\nEND SUB\n'
    'SUB BoardMouse\n    Log$ = Log$ + "b" + STR$(MOUSEEVENT) + ":" + STR$(MOUSEX) + "," + STR$(MOUSEY) + " "\nEND SUB\n'
    'SUB PalKeys\n    Log$ = Log$ + "pk" + STR$(KEYCODE) + " "\nEND SUB\n'
    'SUB BoardKeys\n    Log$ = Log$ + "bk" + STR$(KEYCODE) + " "\nEND SUB\n'
    'SUB Quit\n    EXIT\nEND SUB\n')


def one_window(extra="", buttons=""):
    return ('DIM Log$ AS STRING * 120\nDIM N AS INTEGER\nWINDOW Main, "Two", LARGE\n'
            'CANVAS Pal, 100, 60, PAINT PalPaint, MOUSE PalMouse, KEYS PalKeys\n'
            'CANVAS Board, 200, 100, PAINT BoardPaint, MOUSE BoardMouse, KEYS BoardKeys\n'
            f'{buttons}BUTTON "Quit", Quit\n' + HANDLERS + extra + 'END\n')


def canvases(src):
    """{name: (frame object, screen x, y, w, h)} and button numbers by caption."""
    p = check_source(src)
    out, buttons = {}, {}
    for window in p.windows:
        lay = build_dialog(p, window, False)
        for number, sx, sy, w, h, widget in lay.canvases:
            out[widget.canvas_name.capitalize()] = (number, sx, sy, w, h)
        buttons.update({(window.name, o.text): o.number for o in lay.objects if o.kind == "BUTTON"})
    return out, buttons


def run(src, events, **options):
    r = guarded_run(src, events=events, build_options=options or None)
    assert r.violations == [], r.violations[:5]
    return r


def fills(r):
    """Screen rectangles of every DRAW FILL (os_scr_direct grey)."""
    return [(x, y, w, h) for kind, op, x, y, w, h, *_ in (e for e in r.cpu.draw_log if e[0] == "direct")
            if op in (2, 3)]


@requires_pasmo
class TwoCanvasTests(unittest.TestCase):
    def setUp(self):
        self.src = one_window('SUB ToBoard\n    DRAW ON Board\n    DRAW FILL 10, 10, 2, 2\nEND SUB\n'
                              'SUB Plain\n    DRAW FILL 20, 20, 3, 3\nEND SUB\n'
                              'SUB KeysBoard\n    FOCUS Board\nEND SUB\n'
                              'SUB Tell\n    MESSAGE "x"\nEND SUB\n',
                              'BUTTON "Go", ToBoard\nBUTTON "Plain", Plain\nBUTTON "Kb", KeysBoard\n'
                              'BUTTON "Tell", Tell\n')
        self.cv, self.b = canvases(self.src)
        self.btn = {cap: n for (_, cap), n in self.b.items()}

    def at(self, name, x, y):
        _, sx, sy, _, _ = self.cv[name]
        return sx + x, sy + y

    def test_each_paint_draws_on_its_own_canvas(self):
        r = run(self.src, [])
        self.assertEqual(fills(r)[:2], [(*self.at("Pal", 0, 0), 4, 4), (*self.at("Board", 0, 0), 6, 6)])

    def test_a_press_goes_to_the_canvas_under_it_and_a_drag_stays_there(self):
        x, y = self.at("Board", 50, 40)
        px, py = self.at("Pal", 5, 5)
        r = run(self.src, [("mdown", x, y), ("mmove", px, py), ("mup", px, py),
                           ("mdown", px, py), ("mup", px, py)])
        self.assertEqual(string_var(r, "LOG$"),
                         f"b1:50,40 b2:{px - self.cv['Board'][1]},{py - self.cv['Board'][2]} "
                         f"b3:{px - self.cv['Board'][1]},{py - self.cv['Board'][2]} p1:5,5 p3:5,5 ")

    def test_a_canvas_handler_draws_on_its_canvas(self):
        px, py = self.at("Pal", 7, 8)
        r = run(self.src, [("click", self.btn["Go"]), ("mdown", px, py), ("click", self.btn["Plain"])])
        drawn = fills(r)[2:]
        self.assertEqual(drawn[0], (*self.at("Board", 10, 10), 2, 2))  # DRAW ON Board
        self.assertEqual(drawn[1], (px, py, 1, 1))  # PalMouse: on Pal
        self.assertEqual(drawn[2], (*self.at("Board", 20, 20), 3, 3))  # the target again: Board

    def test_keys_go_to_the_first_canvas_then_the_one_pressed_or_focused(self):
        bx, by = self.at("Board", 1, 1)
        r = run(self.src, [("key", 65), ("mdown", bx, by), ("mup", bx, by), ("key", 66)])
        self.assertTrue(string_var(r, "LOG$").startswith("pk65 b1:1,1 b3:1,1 bk66"))
        r = run(self.src, [("click", self.btn["Kb"]), ("key", 67)])
        self.assertEqual(string_var(r, "LOG$"), "bk67 ")

    def test_a_click_on_a_frame(self):
        frame = self.cv["Board"][0]
        x, y = self.at("Board", 3, 4)
        r = run(self.src, [("clickat", frame, x, y)])
        self.assertEqual(string_var(r, "LOG$"), "b1:3,4 ")

    def test_an_alert_repaints_both(self):
        r = run(self.src, [("click", self.btn["Tell"])])
        self.assertEqual(fills(r), [(*self.at("Pal", 0, 0), 4, 4), (*self.at("Board", 0, 0), 6, 6)] * 2)

    def test_runtime_bank(self):
        x, y = self.at("Board", 50, 40)
        r = run(self.src, [("mdown", x, y), ("click", self.btn["Go"])], runtime_sections="all")
        self.assertEqual(string_var(r, "LOG$"), "b1:50,40 ")
        self.assertEqual(fills(r)[-1], (*self.at("Board", 10, 10), 2, 2))


@requires_pasmo
class FontsPerCanvasTests(unittest.TestCase):
    def test_draw_font_and_type_font_are_kept_per_canvas(self):
        src = ('DIM Log$ AS STRING\nWINDOW Main, "F", LARGE\n'
               'CANVAS A, 200, 60, PAINT PA\nCANVAS B, 200, 60, PAINT PB\nBUTTON "Again", Again\n'
               'SUB PA\n    DRAW FONT 3\n    TYPE FONT SWISS, 12\n    DRAW TEXT 0, 0, "a"\n    DRAW TYPE 0, 20, "a"\nEND SUB\n'
               'SUB PB\n    DRAW TEXT 0, 0, "b"\n    DRAW TYPE 0, 20, "b"\nEND SUB\n'
               'SUB Again\n    DRAW ON A\n    DRAW TEXT 0, 40, "c"\n    DRAW TYPE 100, 20, "c"\n'
               '    DRAW ON B\n    DRAW TEXT 0, 40, "d"\nEND SUB\n'
               'END\n')
        _, b = canvases(src)
        r = run(src, [("click", b[("MAIN", "Again")])])
        self.assertEqual(r.cpu.text_fonts, [3, 7, 3, 7])
        self.assertEqual([size for *_, (_, size) in r.cpu.typo_chars], [12, 10, 12])


@requires_pasmo
class TwoWindowTests(unittest.TestCase):
    SRC = ('DIM Log$ AS STRING\nWINDOW Main, "One", LARGE\nCANVAS A, 100, 50, PAINT PA\n'
           'BUTTON "Next", GoB\nBUTTON "DrawB", DrawB\n'
           'WINDOW Second, "Two", LARGE\nCANVAS B, 120, 40, PAINT PB\nBUTTON "Back", GoA\nBUTTON "DrawA", DrawA\n'
           'SUB PA\n    DRAW FILL 0, 0, 2, 2\nEND SUB\nSUB PB\n    DRAW FILL 0, 0, 3, 3\nEND SUB\n'
           'SUB GoB\n    SHOW Second\nEND SUB\nSUB GoA\n    SHOW Main\nEND SUB\n'
           'SUB DrawB\n    DRAW ON B\n    DRAW FILL 1, 1, 1, 1\nEND SUB\n'
           'SUB DrawA\n    DRAW ON A\n    DRAW FILL 1, 1, 1, 1\nEND SUB\nEND\n')

    def test_each_window_paints_its_canvas(self):
        cv, b = canvases(self.SRC)
        r = run(self.SRC, [("click", b[("MAIN", "Next")]), ("click", b[("SECOND", "Back")])])
        self.assertEqual([(w, h) for *_, w, h in fills(r)], [(2, 2), (3, 3), (2, 2)])

    def test_a_canvas_in_a_window_not_shown_is_not_on_screen(self):
        cv, b = canvases(self.SRC)
        r = guarded_run(self.SRC, events=[("click", b[("MAIN", "DrawB")])])
        self.assertTrue(any("not on screen" in a for a in r.alerts), r.alerts)
        r = guarded_run(self.SRC, events=[("click", b[("MAIN", "Next")]), ("click", b[("SECOND", "DrawA")])])
        self.assertTrue(any("not on screen" in a for a in r.alerts), r.alerts)
        r = run(self.SRC.replace('BUTTON "DrawA", DrawA', 'BUTTON "DrawA", DrawB'),
                [("click", b[("MAIN", "Next")]), ("click", b[("SECOND", "DrawA")])])
        self.assertEqual(r.alerts, [])  # B, in the window on screen
        self.assertEqual(fills(r)[-1], (cv["B"][1] + 1, cv["B"][2] + 1, 1, 1))


class CompileTests(unittest.TestCase):
    def test_one_canvas_keeps_the_rc1_code(self):
        named = ('WINDOW "C"\nCANVAS Board, 100, 60, PAINT P\nBUTTON "Q", Q\n'
                 'SUB P\n    DRAW ON Board\n    DRAW CLEAR\nEND SUB\nSUB Q\n    EXIT\nEND SUB\nEND\n')
        plain = named.replace("CANVAS Board,", "CANVAS").replace("    DRAW ON Board\n", "    REM\n")
        a, b = generate(check_source(named)), generate(check_source(plain))
        self.assertIn("PB_CVMULTI equ 0", a)
        strip = lambda t: [ln for ln in t.splitlines() if not ln.lstrip().startswith(";")]
        self.assertEqual(strip(a), strip(b))
        self.assertIn("PB_CVMULTI equ 1", generate(check_source(one_window())))

    def test_errors(self):
        two_unnamed = one_window().replace("CANVAS Pal,", "CANVAS").replace("CANVAS Board,", "CANVAS")
        cases = ((two_unnamed, "each needs a name"),
                 (one_window().replace("CANVAS Board,", "CANVAS Pal,"), "already declared"),
                 (one_window("SUB X\n    DRAW ON Nowhere\nEND SUB\n"), "no CANVAS NOWHERE"),
                 (one_window().replace("DIM N AS INTEGER", "DIM Pal AS INTEGER")
                  + "", None))
        for src, text in cases[:3]:
            with self.subTest(text=text):
                with self.assertRaises(SourceError) as cm:
                    generate(check_source(src))
                self.assertIn(text, str(cm.exception))
        many = ('WINDOW W1, "a", LARGE\n' + "".join(f"CANVAS C{i}, 20, 16\n" for i in range(5))
                + 'WINDOW W2, "b", LARGE\n' + "".join(f"CANVAS D{i}, 20, 16\n" for i in range(4)) + "END\n")
        with self.assertRaises(SourceError) as cm:
            check_source(many)
        self.assertIn("at most 8 canvases", str(cm.exception))
        clash = one_window("SUB X\n    FOCUS Pal\nEND SUB\n").replace("DIM N AS INTEGER", "DIM Pal AS INTEGER")
        with self.assertRaises(SourceError) as cm:
            check_source(clash)
        self.assertIn("both a CANVAS and a variable", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
