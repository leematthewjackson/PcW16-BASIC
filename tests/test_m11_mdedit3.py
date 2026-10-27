"""MDEDIT III (examples/mdedit3.pbas, M11 Stage E1; proportional text: M11
corrective): MDEDIT II with the caret as a thin bar and the selection
highlighted (inverted) instead of marked with [ and ]. Each row is one DRAW
TEXT, normally spaced; every position on it is measured with TEXTWIDTH.

The page is rebuilt from the simulator's ordered drawing log (white row
fills clear a row; one text per row; inversions toggle pixels; a 2-pixel
inversion is the caret). Inverted pixels and carets are then read back as
character columns, using the simulator's font-7 model: a character counts as
selected only if every pixel of it is inverted, and any inverted pixel that
is not a whole character (or the EOLW block after a line's end) fails the
test, so a highlight one pixel out is caught. That is compared with an
independent Python model of what each row must show. Edits must give exactly
the files MDEDIT II gives for the same keys (the editing code is MDEDIT II's).
The program is built with its runtime sections in a code bank (M11 Stage B):
without it, it does not fit its resident 16K block. Simulator evidence only:
how it looks and how fast it draws in XAnne is for the owner.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import check_source
from pbas.errors import SourceError
from pbas.layout import build_dialog
from pbas.prg import build
from test_m10_mdedit2 import (COPY, CUT, DOC, MARK, PASTE, QUIT, REDO, SAVE, SELALL, UNDO, WRAP, keys, shift)
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "examples" / "mdedit3.pbas"
SRC = PATH.read_text(encoding="utf-8")
F = "\\PCW\\FOLDER01"
ROWS, COLS, LINEH, EOLW, TEXTW = 13, 50, 16, 6, 552
UP, DOWN, LEFT, RIGHT, HOME, END_ = 0xE0, 0xE1, 0xE2, 0xE3, 0xE6, 0xE7
BS, F1 = 8, 241
LINES = DOC.decode("latin-1").split("\r\n")
STEPS = 900_000_000


def run(events, files=None, source=SRC, path=PATH, banks="all"):
    disk = z80sim.Disk(files={(F, n): d for n, d in (files if files is not None else {"EDTEST.MD": DOC}).items()})
    r = guarded_run(source, events=events, disk=disk, max_steps=STEPS, path=path,
                    build_options={"runtime_sections": banks} if banks else None)
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r


def canvas():
    program = check_source(SRC, path=PATH)
    for window in program.windows:
        lay = build_dialog(program, window, True)
        if lay.canvas:
            return lay.canvas[1], lay.canvas[2]
    raise AssertionError("no canvas")


CX, CY = canvas()


def fw(text: str) -> int:
    return z80sim.font7_width(text.encode("latin-1"))


def edges(text: str) -> list[int]:
    """The pixel x (from the row's left, text at 4) before each character and
    after the last, as DrawSeg measures them (capped at the right edge)."""
    return [4 + min(TEXTW, fw(text[:k])) for k in range(len(text) + 1)]


def screen(r):
    """Each row as (text, inverted columns, caret columns), replayed from the
    log and read back through the font model."""
    rows = [["", set(), set()] for _ in range(ROWS)]
    for entry in r.cpu.draw_log:
        if entry[0] == "direct":
            _, op, x, y, w, h, _ = entry
            covered = [row for row in range(ROWS) if y <= CY + row * LINEH and CY + (row + 1) * LINEH <= y + h]
            for row in covered:
                if op == 1 and w >= 500:  # a row cleared white
                    rows[row] = ["", set(), set()]
                elif op == 4 and w == 2:  # the caret bar, 1 pixel before its edge
                    rows[row][2] ^= {x - CX + 1}
                elif op == 4:
                    rows[row][1] ^= set(range(x - CX, x - CX + w))
        elif entry[0] == "text":
            _, x, y, text, _ = entry
            assert x == CX + 4 and (y - CY) % LINEH == 0, entry
            rows[(y - CY) // LINEH][0] = text
    out = []
    for text, pixels, carets in rows:
        e = edges(text)
        inv = [k for k in range(len(text)) if set(range(e[k], e[k + 1])) <= pixels and e[k + 1] > e[k]]
        covered = set()
        for k in inv:
            covered |= set(range(e[k], e[k + 1]))
        tail = set(range(e[-1], min(4 + TEXTW, e[-1] + EOLW)))
        if tail and tail <= pixels:
            inv.append(len(text))
            covered |= tail
        assert pixels == covered, f"inverted pixels that are not whole characters: {sorted(pixels - covered)[:8]}"
        cols = []
        for x in carets:
            assert x in e, f"a caret at {x}, not at a character edge of {text!r}"
            cols.append(e.index(x) if e.count(x) == 1 else max(k for k, v in enumerate(e) if v == x))
        out.append((text.rstrip(" "), sorted(inv), sorted(cols)))
    return out


def expected_rows(lines, top, caret, anchor=None):
    """The page by the rules in examples/mdedit3.pbas (wrap on, 50 columns)."""
    sel = anchor is not None and anchor != caret
    start, end = (min(anchor, caret), max(anchor, caret)) if sel else (None, None)
    out = []
    line = top
    while len(out) < ROWS and line <= len(lines):
        text = lines[line - 1]
        for s in range(len(text) // COLS + 1):
            rcol = s * COLS + 1
            seg = text[rcol - 1:rcol - 1 + COLS]
            last = rcol + COLS - 1 if rcol + COLS <= len(text) + 1 else rcol + len(seg)
            inv = []
            if sel and start[0] <= line <= end[0]:
                a = max(start[1], rcol) if line == start[0] else rcol
                b = rcol + len(seg)
                if line == end[0]:
                    b = min(end[1], b)
                elif b == len(text) + 1 and len(seg) < COLS:
                    b += 1
                inv = list(range(a - rcol, b - rcol))
            carets = [caret[1] - rcol] if line == caret[0] and rcol <= caret[1] <= last else []
            out.append((seg.rstrip(" "), inv, carets))
            if len(out) == ROWS:
                break
        line += 1
    return out + [("", [], [])] * (ROWS - len(out))


def x_of(col, text=None):
    """The screen x of the edge before column col of a row (col 1 = the
    row's first character), on line 1 unless text is given."""
    text = LINES[0] if text is None else text
    return CX + edges(text)[col - 1]


def nearest(text, mx):
    """Independent rule for a press at text pixel mx (from the text's left):
    the column whose edge is nearest; halfway goes right."""
    e = [fw(text[:k]) for k in range(len(text) + 1)]
    return min(range(len(e)), key=lambda k: (abs(2 * mx - 2 * e[k]), -k)) + 1


@requires_pasmo
class BuildTests(unittest.TestCase):
    def test_needs_and_gets_a_runtime_bank(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            with self.assertRaisesRegex(SourceError, "over the 16384-byte"):
                build(PATH, t / "a.asm", t / "a.prg")
            report = build(PATH, t / "b.asm", t / "b.prg", runtime_sections="all")
            self.assertLess(report.banked.resident_size, 13800)
            asm = (t / "b.asm").read_text(encoding="utf-8")
            self.assertIn("PB_CVCELL equ 0", asm, "no cell drawing any more")
            self.assertIn("PB_TEXTW equ 1", asm)


@requires_pasmo
class PageTests(unittest.TestCase):
    def test_opening_page(self):
        r = run([])
        self.assertEqual(screen(r), expected_rows(LINES, 1, (1, 1)))
        self.assertEqual(string_var(r, "STATUS$"), "L1/114 C1")
        self.assertEqual(string_var(r, "INFO$"), "Opened EDTEST.MD")
        self.assertFalse([t for t in r.cpu.texts if t[2] in "[]|" and t[2] not in DOC.decode("latin-1")])

    def test_text_never_moves_with_the_caret(self):
        r = run([("key", DOWN), ("key", DOWN), ("key", END_), ("key", LEFT), ("key", LEFT)])
        self.assertGreater(len(LINES[2]), COLS)
        self.assertEqual(screen(r), expected_rows(LINES, 1, (3, len(LINES[2]) - 1)))
        opening = [row[0] for row in screen(run([]))]
        self.assertEqual([row[0] for row in screen(r)], opening, "only the caret moved")

    def test_select_all_highlights_every_line(self):
        r = run([SELALL])
        end = (len(LINES), len(LINES[-1]) + 1)
        self.assertEqual(screen(r), expected_rows(LINES, 1, (1, 1), end))
        self.assertEqual(string_var(r, "STATUS$"), "L1/114 C1 sel")
        self.assertTrue(all(row[1] for row in screen(r) if row[0]), "every shown line is highlighted")

    def test_shift_selection_across_a_wrapped_row(self):
        ev = [("key", DOWN), ("key", DOWN)] + [("key", RIGHT)] * 45 + shift(RIGHT, 10)
        r = run(ev)
        self.assertEqual(screen(r), expected_rows(LINES, 1, (3, 56), (3, 46)))
        rows = screen(r)
        self.assertEqual(rows[2][1], list(range(45, 50)), "the end of the first row of line 3")
        self.assertEqual(rows[3][1], list(range(0, 5)), "and the start of its second row")

    def test_a_selection_over_line_ends(self):
        r = run([("key", DOWN)] + shift(DOWN, 2))
        self.assertEqual(screen(r), expected_rows(LINES, 1, (4, 1), (2, 1)))


@requires_pasmo
class SelectionTests(unittest.TestCase):
    def test_mouse_drag_selects_exact_columns(self):
        y = CY + 4
        ev = [("mdown", x_of(3), y), ("mmove", x_of(6), y), ("mup", x_of(9), y), COPY,
              ("key", DOWN), ("key", DOWN), ("key", HOME), PASTE, SAVE, QUIT]
        r = run(ev[:4])
        self.assertEqual(string_var(r, "STATUS$"), "L1/114 C9 sel")
        self.assertEqual(screen(r)[0][1], list(range(2, 8)))
        r = run(ev)
        self.assertTrue(r.cpu.disk.file("EDTEST.MD").split(b"\r\n")[2].startswith(b"MDEDIT"))

    def test_the_nearest_character_edge(self):
        y = CY + 4
        line = LINES[0]
        for dx in range(-7, 8):
            col = nearest(line, x_of(3) + dx - CX - 4)
            with self.subTest(dx=dx, col=col):
                r = run([("mdown", x_of(3) + dx, y), ("mup", x_of(3) + dx, y)])
                self.assertEqual(string_var(r, "STATUS$"), f"L1/114 C{col}")
        # the widths differ, so the boundaries are not every 11 pixels
        self.assertNotEqual(x_of(4) - x_of(3), x_of(3) - x_of(2))

    def test_clicks_along_a_whole_row(self):
        y = CY + 2 * LINEH + 4
        line = LINES[2][:COLS]
        self.assertGreater(len(LINES[2]), COLS, "a row that continues on the next")
        for px in range(0, fw(line) + 12, 23):
            # the edge after a continuing row's last character is the next
            # row's first: on this row the last column is COLS
            col = min(COLS, nearest(line, px))
            with self.subTest(px=px, col=col):
                r = run([("mdown", CX + 4 + px, y), ("mup", CX + 4 + px, y)])
                self.assertEqual(string_var(r, "STATUS$"), f"L3/114 C{col}")

    def test_mark_by_f1_and_menu(self):
        for start in ([("key", F1)], [MARK]):
            with self.subTest(start=start):
                r = run(start + [("key", RIGHT)] * 4)
                self.assertEqual(screen(r)[0][1], [0, 1, 2, 3])
                self.assertEqual(string_var(r, "STATUS$"), "L1/114 C5 mark")

    def test_ctrl_keys_never_type(self):
        r = run([("key", ord("k"), 4), ("key", ord("c"), 4), ("key", 11, 4), SAVE, QUIT])
        self.assertEqual(r.cpu.disk.file("EDTEST.MD"), DOC, "unchanged, so Save wrote nothing new")

    def test_cut_clears_the_highlight(self):
        r = run(shift(RIGHT, 7) + [CUT])
        lines = list(LINES)
        lines[0] = lines[0][7:]
        self.assertEqual(screen(r), expected_rows(lines, 1, (1, 1)))
        self.assertTrue(all(not row[1] for row in screen(r)))


@requires_pasmo
class WideRowTests(unittest.TestCase):
    """A row of characters wider than the page (Rosanne's #B2-#B9 are 13
    pixels: docs/M11-CORRECTIVE.md §2) is cut at a whole character before
    the right edge; the document itself is not changed by drawing it. The
    simulator's font model is widened for these codes for this test only."""

    base_model = staticmethod(z80sim.font7_width)

    @classmethod
    def wide_model(cls, text: bytes) -> int:
        return sum(13 if 0xB2 <= c <= 0xB9 else cls.base_model(bytes([c])) for c in text)

    def test_cut_at_the_edge_and_document_unchanged(self):
        from unittest import mock
        doc = bytes([0xB5]) * 60 + b"\r\nabc\r\n"
        with mock.patch.object(z80sim, "font7_width", self.wide_model):
            r = run([("key", END_), SELALL, SAVE, QUIT], files={"EDTEST.MD": doc})
        texts = [t for t in r.cpu.texts if t[1] == CY]
        self.assertEqual(texts[-1][2], "\xb5" * 42, "42 x 13 = 546 <= 552 pixels; 43 would pass the edge")
        inverted = [e for e in r.cpu.draw_log if e[0] == "direct" and e[1] == 4 and e[3] == CY and e[4] > 2]
        self.assertTrue(inverted)
        self.assertLessEqual(max(e[2] + e[4] for e in inverted) - CX, 4 + TEXTW, "nothing past the edge")
        self.assertEqual(r.cpu.disk.file("EDTEST.MD"), doc, "drawing changed nothing")

    def test_extended_and_odd_characters_drawn_and_measured_alike(self):
        doc = bytes([0x80, 0x9C, 0xC5, ord("a"), 0xE5, ord("b")]) + b"\r\n"
        r = run([("key", RIGHT), ("key", RIGHT)] + shift(RIGHT, 2), files={"EDTEST.MD": doc})
        self.assertEqual(string_var(r, "STATUS$"), "L1/2 C5 sel")
        rows = screen(r)
        self.assertEqual(rows[0][0], "\x80\x9c\xc5a?b", "codes from #E0 drawn as ?")
        self.assertEqual(rows[0][1], [2, 3])
        self.assertEqual(rows[0][2], [4])


@requires_pasmo
class SameEditsAsMdedit2Tests(unittest.TestCase):
    """The editing code is MDEDIT II's: the same keys must give the same file."""

    def test_same_files(self):
        import test_m10_mdedit2 as tm
        ev = ([("key", RIGHT)] * 2 + shift(RIGHT, 6) + [COPY] + [("key", DOWN)] * 2 + [PASTE]
              + keys("Hello") + [("key", 13), ("key", BS), UNDO, REDO, SELALL, ("key", DOWN)]
              + [MARK] + [("key", DOWN)] * 3 + [CUT, ("key", END_, 4), PASTE, WRAP, ("key", DOWN)]
              + keys("xyz") + [SAVE, QUIT])
        two = tm.run(ev)
        three = run(ev)
        self.assertTrue(two.cpu.exited and three.cpu.exited)
        self.assertEqual(three.cpu.disk.file("EDTEST.MD"), two.cpu.disk.file("EDTEST.MD"))
        self.assertEqual(three.cpu.disk.file("EDTEST.BAK"), DOC)
        self.assertIsNone(three.cpu.disk.file("MDEDIT3.TMP"))
        self.assertNotEqual(three.cpu.disk.file("EDTEST.MD"), DOC)


@requires_pasmo
class CostTests(unittest.TestCase):
    """Drawing each character on its own costs more than one DRAW TEXT per
    row; a key still redraws only its lines (measured, simulator)."""

    def test_per_key_cost(self):
        def steps(ev):
            return run(ev).cpu.steps
        base = steps([("key", RIGHT)] * 2 + shift(RIGHT, 6))
        more = steps([("key", RIGHT)] * 2 + shift(RIGHT, 7))
        plain = steps([("key", RIGHT)] * 3) - steps([("key", RIGHT)] * 2)
        self.assertLess(more - base, 250_000)
        self.assertLess(plain, 200_000)
        self.costs = (more - base, plain)


if __name__ == "__main__":
    unittest.main()
