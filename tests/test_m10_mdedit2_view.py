"""MDEDIT II page, selection and keys: regression tests for the owner's
XAnne Session 2 failures (docs/M10-ACCEPTANCE.md, RUNTIME-RESULTS "M10
owner XAnne, Session 2"):

1. moving the caret shifted the visible text sideways;
2. Select All left a clipped, garbled page (the view scrolled to column 10);
3. selections could not be copied ("Nothing selected") after Mark, keyboard
   or mouse attempts;
4. every key repainted the whole page while a selection was shown.

The page is checked against an independent Python model of what each row
must show (expected_rows), rebuilt from the simulator's ordered drawing log
(fills and texts), so incremental redraws are checked too. Keys that a menu
owns are also sent as KEYS events (with Ctrl), as XAnne may deliver them:
the simulator's rule that menu keys never reach KEYS is not XAnne-verified
(KI-60). Simulator evidence only.
"""
from __future__ import annotations

import unittest

from memguard import string_var
from pbas import check_source
from pbas.layout import build_dialog
from test_m10_mdedit2 import (COPY, CUT, DOC, MARK, PASTE, QUIT, SAVE, SELALL, SRC, keys, run, shift)
from toolchain import requires_pasmo

ROWS, COLS, LINEH = 13, 47, 16
UP, DOWN, LEFT, RIGHT, HOME, END_, PGDN = 0xE0, 0xE1, 0xE2, 0xE3, 0xE6, 0xE7, 0xE9
F1 = 241
LINES = DOC.decode("latin-1").split("\r\n")


def canvas():
    program = check_source(SRC)
    for window in program.windows:
        lay = build_dialog(program, window, True)
        if lay.canvas:
            return lay.canvas[1], lay.canvas[2]
    raise AssertionError("no canvas")


CX, CY = canvas()


def expected_rows(lines, top, caret, anchor=None):
    """The 13 rows of the page (wrap on, 47 columns): each row a segment of
    a line, "|" before the caret's column, "[" / "]" at the selection's
    start / end ("[|" or "|]" where the caret is). A mark sits on the row
    that shows its column; the column after a line's last character is on
    the line's last row."""
    sel = anchor is not None and anchor != caret
    start, end = (min(anchor, caret), max(anchor, caret)) if sel else (None, None)
    out = []
    line = top
    while len(out) < ROWS and line <= len(lines):
        text = lines[line - 1]
        spans = len(text) // COLS + 1
        for s in range(spans):
            rcol = s * COLS + 1
            seg = text[rcol - 1:rcol - 1 + COLS]
            last = rcol + COLS - 1 if rcol + COLS <= len(text) + 1 else rcol + len(seg)
            marks = []
            if sel:
                if line == end[0] and rcol <= end[1] <= last:
                    marks.append((end[1], "|]" if caret == end else "]"))
                if line == start[0] and rcol <= start[1] <= last:
                    marks.append((start[1], "[|" if caret == start else "["))
            elif line == caret[0] and rcol <= caret[1] <= last:
                marks.append((caret[1], "|"))
            for col, m in sorted(marks, reverse=True):
                p = col - rcol
                seg = seg[:p] + m + seg[p:]
            out.append(seg)
            if len(out) == ROWS:
                break
        line += 1
    return out + [""] * (ROWS - len(out))


def screen(r) -> list[str]:
    """What each canvas row shows after the run: replayed from the drawing
    log (a full-width white fill clears a row, a text sets it)."""
    rows = [""] * ROWS
    for entry in r.cpu.draw_log:
        if entry[0] == "direct":
            _, op, x, y, w, h, _ = entry
            if w >= 500:
                for row in range(ROWS):
                    top = CY + row * LINEH
                    if y <= top and top + LINEH <= y + h:
                        rows[row] = ""
        elif entry[0] == "text":
            _, x, y, text, _ = entry
            if x == CX + 4 and (y - CY) % LINEH == 0:
                rows[(y - CY) // LINEH] = text
    return rows


def steps(events) -> int:
    return run(events).cpu.steps


@requires_pasmo
class PageTests(unittest.TestCase):
    def test_opening_page(self):
        r = run([])
        self.assertEqual(screen(r), expected_rows(LINES, 1, (1, 1)))
        self.assertEqual(string_var(r, "STATUS$"), "L1/114 C1")

    def test_navigation_keeps_rows_in_place(self):
        # line 3 is longer than one row: End puts the caret on its last
        # row; nothing is drawn shifted sideways (no horizontal scrolling)
        self.assertGreater(len(LINES[2]), COLS)
        ev = [("key", DOWN), ("key", DOWN), ("key", END_), ("key", LEFT), ("key", LEFT)]
        r = run(ev)
        self.assertEqual(screen(r), expected_rows(LINES, 1, (3, len(LINES[2]) - 1)))
        self.assertTrue(all(len(t[2]) <= 50 for t in r.cpu.texts), "every row fits DRAW TEXT (50)")

    def test_select_all_shows_the_page(self):
        r = run([SELALL])
        end = (len(LINES), len(LINES[-1]) + 1)
        self.assertEqual(screen(r), expected_rows(LINES, 1, (1, 1), end))
        self.assertEqual(string_var(r, "STATUS$"), "L1/114 C1 sel")
        self.assertEqual(screen(r)[0][:2], "[|")

    def test_shift_selection_on_a_long_row(self):
        # line 3, columns 40..55: the selection crosses the row boundary at 48
        ev = [("key", DOWN), ("key", DOWN)] + [("key", RIGHT)] * 39 + shift(RIGHT, 16)
        r = run(ev)
        self.assertEqual(screen(r), expected_rows(LINES, 1, (3, 56), (3, 40)))
        self.assertEqual(string_var(r, "STATUS$"), "L3/114 C56 sel")


@requires_pasmo
class SelectionTests(unittest.TestCase):
    def saved(self, events):
        r = run(events + [SAVE, QUIT])
        self.assertTrue(r.cpu.exited, r.alerts)
        return r, r.cpu.disk.file("EDTEST.MD")

    def paste_at_line3(self):
        return [("key", DOWN), ("key", DOWN), ("key", HOME), PASTE]

    def with_line3(self, text: str) -> bytes:
        lines = list(LINES)
        lines[2] = text + lines[2]
        return "\r\n".join(lines).encode("latin-1")

    def test_shift_arrows_copy(self):
        r, saved = self.saved([("key", RIGHT)] * 2 + shift(RIGHT, 6) + [COPY] + self.paste_at_line3())
        self.assertEqual(saved, self.with_line3("MDEDIT"))

    def test_mouse_drag_copies(self):
        # press before column 3 of line 1, drag to column 9, release
        x3, x9 = CX + 4 + 2 * 7, CX + 4 + 8 * 7
        ev = [("mdown", x3, CY + 4), ("mmove", x9, CY + 4), ("mup", x9, CY + 4), COPY]
        r = run(ev)
        self.assertEqual(string_var(r, "STATUS$"), "L1/114 C9 sel")
        self.assertEqual(string_var(r, "INFO$"), "Copied")
        r, saved = self.saved(ev + self.paste_at_line3())
        self.assertEqual(saved, self.with_line3("MDEDIT"))

    def test_a_click_alone_selects_nothing(self):
        r = run([("mdown", CX + 30, CY + 20), ("mup", CX + 30, CY + 20), COPY])
        self.assertEqual(string_var(r, "INFO$"), "Nothing selected")

    def test_mark_by_menu_f1_or_ctrl_k(self):
        for start in ([MARK], [("key", F1)]):
            with self.subTest(start=start):
                r, saved = self.saved([("key", RIGHT)] * 2 + start + [("key", RIGHT)] * 6 + [COPY]
                                      + self.paste_at_line3())
                self.assertEqual(saved, self.with_line3("MDEDIT"))

    def test_menu_shortcuts_that_also_reach_keys(self):
        # XAnne may pass a menu's Ctrl+letter to KEYS too (as the letter or
        # as its control code, with Ctrl in KEYSHIFT): it must not type,
        # split the line or end the selection
        for form in (lambda c: ord(c), lambda c: ord(c.upper()) - 64):
            with self.subTest(code=form("c")):
                ev = ([("key", RIGHT)] * 2 + [MARK, ("key", form("k"), 4)] + [("key", RIGHT)] * 6
                      + [COPY, ("key", form("c"), 4)] + [("key", DOWN), ("key", DOWN), ("key", HOME)]
                      + [PASTE, ("key", form("v"), 4)])
                r, saved = self.saved(ev)
                self.assertEqual(saved, self.with_line3("MDEDIT"))

    def test_cut_then_undo_from_a_drag(self):
        x1, x9 = CX + 4, CX + 4 + 8 * 7
        ev = [("mdown", x1, CY + 4), ("mmove", x9, CY + 4), ("mup", x9, CY + 4), CUT]
        r, saved = self.saved(ev)
        self.assertEqual(saved, DOC[8:])
        r, saved = self.saved(ev + [("menu", 2, 0)])
        self.assertEqual(saved, DOC)


@requires_pasmo
class RetestScriptTests(unittest.TestCase):
    """docs/M10-ACCEPTANCE.md Session 2R, S1-S12, as the owner will run it."""

    def test_session_2r(self):
        x1, x9 = CX + 4 + 2 * 7, CX + 4 + 8 * 7
        ctrl_home = ("key", HOME, 4)
        ev = [("key", DOWN), ("key", DOWN), ("key", END_), ("key", LEFT), ("key", RIGHT), ("key", UP),
              ("key", DOWN), ("key", HOME), ("key", END_)]                                     # S2
        ev += [ctrl_home, ("mdown", x1, CY + 4), ("mmove", x9, CY + 4), ("mup", x9, CY + 4)]  # S3
        ev += [COPY, ("key", DOWN), ("key", DOWN), ("key", HOME), PASTE]                      # S4
        ev += [ctrl_home, MARK] + [("key", RIGHT)] * 6 + [COPY] + [("key", DOWN)] * 3 + [("key", HOME), PASTE]  # S5
        ev += [ctrl_home, MARK, ("key", ord("k"), 4)] + [("key", RIGHT)] * 3 + [COPY, ("key", ord("c"), 4)]  # S6
        ev += [ctrl_home] + shift(RIGHT, 3)                                                    # S7
        ev += [SELALL]                                                                         # S8
        r = run(ev)
        end = (len(LINES), len(LINES[-1]) + 1)
        lines = list(LINES)
        lines[2] = "MDEDIT" + lines[2]
        lines[3] = "# MDED" + lines[3]
        self.assertEqual(screen(r), expected_rows(lines, 1, (1, 1), end))
        self.assertEqual(string_var(r, "STATUS$"), "* L1/114 C1 sel")
        ev += [("key", RIGHT), ("menu", 2, 0), ("menu", 2, 0), ("menu", 2, 1)]                 # S8, S9
        ev += [("menu", 3, 0), ("menu", 3, 0)]                                                # S10
        ev += [ctrl_home] + keys("!") + [SAVE, QUIT]                                          # S12
        r = run(ev)
        self.assertTrue(r.cpu.exited, r.alerts)
        want = list(LINES)
        want[0] = "!" + want[0]
        want[2] = "MDEDIT" + want[2]
        self.assertEqual(r.cpu.disk.file("EDTEST.MD"), "\r\n".join(want).encode("latin-1"))
        self.assertEqual(r.cpu.disk.file("EDTEST.BAK"), DOC)
        self.assertIsNone(r.cpu.disk.file("MDEDIT2.TMP"))


@requires_pasmo
class StatusTests(unittest.TestCase):
    """A LABEL shows at most 24 characters (M5d): the status must never be
    longer, or the program stops with "string too long" (found by the
    Session 2R script: "L1/114 C2 sel mark wrap *" was 25)."""

    def test_longest_status_fits(self):
        ev = [("key", DOWN)] * 2 + keys("x") + [MARK, ("key", RIGHT), ("menu", 3, 0)]
        r = run(ev)
        self.assertEqual(string_var(r, "STATUS$"), "* L3/114 C3 mark nowrap")
        self.assertLessEqual(len(string_var(r, "STATUS$")), 24)


@requires_pasmo
class CostTests(unittest.TestCase):
    """A key must not repaint the whole page while a selection is shown
    (before the fix: 799,000 instructions per Shift+Right, 13 rows)."""

    def test_keys_redraw_only_their_lines(self):
        base = steps([("key", RIGHT)] * 2 + shift(RIGHT, 6))
        more = steps([("key", RIGHT)] * 2 + shift(RIGHT, 7))
        self.assertLess(more - base, 120_000)
        plain = steps([("key", RIGHT)] * 3) - steps([("key", RIGHT)] * 2)
        self.assertLess(plain, 80_000)
        r = run([("key", RIGHT)] * 2 + shift(RIGHT, 7))
        before = len(run([("key", RIGHT)] * 2 + shift(RIGHT, 6)).cpu.texts)
        self.assertLessEqual(len(r.cpu.texts) - before, 2)


if __name__ == "__main__":
    unittest.main()
