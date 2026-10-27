"""MDEDIT IV (examples/mdedit4.pbas, M12 Stage E): MDEDIT III with word
wrapping by pixel width.

The page is replayed from the simulator's drawing log (test_m11_mdedit3's
screen(): the text of each row, its inverted characters and its caret) and
compared with an independent model of the wrapping rule, written from its
definition rather than from the program: a row ends just after the last
space whose preceding text (from the row's start) fits the page's width;
without such a space the row is the longest prefix that fits; the rest of
a line ends its last row when it fits; a row holds at most 120 characters.
Widths are the simulator's font-7 model (the program measures with
TEXTWIDTH, which the simulator answers from the same model). Edits are
checked after typing and deleting anywhere in wrapped paragraphs, so a row
the incremental re-measuring missed shows as a difference. Simulator
evidence only (Session 4 in XAnne).
"""
from __future__ import annotations

import random
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import check_source
from pbas.layout import build_dialog
from test_m10_mdedit2 import COPY, CUT, DOC, PASTE, QUIT, REDO, SAVE, SELALL, UNDO, WRAP, keys, shift
from test_m11_mdedit3 import CX, CY, edges, fw
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "examples" / "mdedit4.pbas"
SRC = PATH.read_text(encoding="utf-8")
F = "\\PCW\\FOLDER01"
ROWS, LINEH, EOLW, TEXTW, ROWMAX = 13, 16, 6, 552, 120
UP, DOWN, LEFT, RIGHT, HOME, END_, PGDN = 0xE0, 0xE1, 0xE2, 0xE3, 0xE6, 0xE7, 0xE9
BS, DEL = 8, 229
STEPS = 2_000_000_000
# The test document: paragraphs that wrap, widths that differ, a word longer
# than a row, and enough lines to scroll (EDTEST.MD's lines all fit a row).
PARA1 = ("The PcW16 was Amstrad's last word processor, a small grey machine with a flash disc and a floppy drive. "
         "Its software, Rosanne, draws every character in proportion, so a row of narrow letters holds many more "
         "characters than a row of wide ones, and an editor that wraps by counting characters leaves ragged gaps "
         "or runs off the edge. MDEDIT IV measures each row in pixels instead.")
PARA2 = ("Wide WWW MMM mmm and narrow iii lll ttt letters mixed: WWWW iiii MMMM llll mmmm tttt WWWW iiii MMMM llll "
         "mmmm tttt WWWW iiii MMMM llll mmmm tttt WWWW iiii.")
LINES = ["# Wrapping test", "", PARA1, "", PARA2, "Short line.", "x" * 150 + " tail", ""] + [
    f"Line {k}: the quick brown fox jumps over the lazy dog, again and again, until the row is quite full."
    for k in range(1, 25)]
WRAPDOC = "\r\n".join(LINES).encode("latin-1")  # no final line end: exactly LINES


def screen(r):
    """Each row as (text, inverted columns, caret columns), replayed from the
    log and read back through the font model (test_m11_mdedit3.screen, with
    a row drawn in pieces: each piece must start where the last one ended)."""
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
            assert (y - CY) % LINEH == 0, entry
            row = rows[(y - CY) // LINEH]
            if x == CX + 4:
                row[0] = text
            else:
                assert x == CX + edges(row[0])[-1], (entry, row[0])
                row[0] += text
            assert len(text) <= (560 - (x - CX)) // 11, "a piece DRAW TEXT would cut"
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


def run(events, files=None):
    disk = z80sim.Disk(files={(F, n): d for n, d in (files if files is not None else {"EDTEST.MD": WRAPDOC}).items()})
    r = guarded_run(SRC, events=events, disk=disk, max_steps=STEPS, path=PATH,
                    build_options={"runtime_sections": "all"})
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r


def text_fits(text: str) -> bool:
    return fw(text) <= TEXTW


def line_rows(text: str) -> list[tuple[int, int, bool]]:
    """(start, end, last) of each row of a line (0-based, end exclusive)."""
    out, s = [], 0
    while True:
        rest = text[s:]
        if len(rest) <= ROWMAX and text_fits(rest):
            out.append((s, len(text), True))
            return out
        window = rest[:ROWMAX]
        spaces = [p for p in range(1, len(window) + 1) if window[p - 1] == " " and text_fits(window[:p - 1])]
        if spaces:
            e = s + max(spaces)
        else:
            longest = max(k for k in range(len(window) + 1) if text_fits(window[:k]))
            e = s + max(longest, 1)
        if e >= len(text):
            out.append((s, len(text), True))
            return out
        out.append((s, e, False))
        s = e


def all_rows(lines):
    """Every row of the document: (line number, start, end, last)."""
    return [(n, s, e, last) for n, text in enumerate(lines, 1) for s, e, last in line_rows(text)]


def expected(lines, first, caret, anchor=None):
    """The page from the document's row index *first* (0-based), with the
    caret and selection as MDEDIT III's rules draw them."""
    sel = anchor is not None and anchor != caret
    start, end = (min(anchor, caret), max(anchor, caret)) if sel else (None, None)
    out = []
    for n, s, e, last in all_rows(lines)[first:first + ROWS]:
        text = lines[n - 1]
        seg, rcol = text[s:e], s + 1
        inv = []
        if sel and start[0] <= n <= end[0]:
            a = max(start[1], rcol) if n == start[0] else rcol
            b = rcol + len(seg)
            if n == end[0]:
                b = min(end[1], b)
            elif last and b == len(text) + 1:
                b += 1
            inv = list(range(a - rcol, b - rcol))
        hi = rcol + len(seg) if last else e
        carets = [caret[1] - rcol] if n == caret[0] and rcol <= caret[1] <= hi else []
        out.append((seg.rstrip(" "), inv, carets))
    return out + [("", [], [])] * (ROWS - len(out))


def page_start(r, lines):
    """The document row index the page shows first (it must be a window of
    the document's rows)."""
    shown = [row[0] for row in screen(r)]
    texts = [lines[n - 1][s:e].rstrip(" ") for n, s, e, _ in all_rows(lines)]
    for k in range(len(texts)):
        window = (texts[k:k + ROWS] + [""] * ROWS)[:ROWS]
        if window == shown:
            return k
    raise AssertionError(f"the page is not a window of the document's rows: {shown}")


def status_pos(r):
    s = string_var(r, "STATUS$").lstrip("* ")
    line, col = s.split()[0], s.split()[1]
    return int(line[1:].split("/")[0]), int(col[1:])


def edited(lines, line, col, typed="", deleted=0):
    out = list(lines)
    text = out[line - 1]
    out[line - 1] = text[:col - 1] + typed + text[col - 1 + deleted:]
    return out


class ModelTests(unittest.TestCase):
    """The model itself, on texts whose breaks are known."""

    def test_the_xanne_document_is_this_one(self):
        # Session 4 opens developer-tests/wraptest.md (artifacts/m12/WRAPTEST.MD)
        self.assertEqual((ROOT / "developer-tests" / "wraptest.md").read_bytes(), WRAPDOC)

    def test_rows(self):
        self.assertEqual(line_rows(""), [(0, 0, True)])
        self.assertEqual(line_rows("short"), [(0, 5, True)])
        long = "word " * 40
        rows = line_rows(long)
        self.assertGreater(len(rows), 1)
        for s, e, last in rows[:-1]:
            self.assertEqual(long[e - 1], " ")
            self.assertTrue(text_fits(long[s:e - 1]))
            self.assertFalse(text_fits(long[s:e + 4]), "the next word would not have fitted")
        self.assertEqual("".join(long[s:e] for s, e, _ in rows), long)
        self.assertEqual(line_rows("W" * 300)[0][1], max(k for k in range(121) if text_fits("W" * k)))
        self.assertEqual(line_rows("i" * 300)[0][1], ROWMAX)


@requires_pasmo
class PageTests(unittest.TestCase):
    def test_opening_page(self):
        r = run([])
        self.assertEqual(screen(r), expected(LINES, 0, (1, 1)))
        self.assertEqual(string_var(r, "STATUS$"), f"L1/{len(LINES)} C1")
        long = [n for n, text in enumerate(LINES[:8], 1) if len(line_rows(text)) > 1]
        self.assertTrue(long, "the opening page has wrapped lines")

    def test_rows_end_between_words(self):
        r = run([])
        for (text, _, _), (n, s, e, last) in zip(screen(r), all_rows(LINES)):
            if not last and " " in LINES[n - 1][s:e]:  # (a word longer than a row is broken)
                self.assertEqual(LINES[n - 1][e - 1], " ", text)

    def test_select_all_and_a_selection_across_rows(self):
        r = run([SELALL])
        end = (len(LINES), len(LINES[-1]) + 1)
        self.assertEqual(screen(r), expected(LINES, 0, (1, 1), end))
        n = next(n for n, text in enumerate(LINES, 1) if len(line_rows(text)) > 1)
        first_end = line_rows(LINES[n - 1])[0][1]
        # to line n, then to the end of its first row and over the break
        ev = [("key", DOWN)] * sum(len(line_rows(t)) for t in LINES[:n - 1])
        ev += [("key", RIGHT)] * (first_end - 3) + shift(RIGHT, 6)
        r = run(ev)
        self.assertEqual(screen(r), expected(LINES, 0, (n, first_end + 4), (n, first_end - 2)))

    def test_wrap_off_and_on(self):
        r = run([WRAP])
        self.assertTrue(string_var(r, "STATUS$").endswith("nowrap"))
        self.assertEqual([row[0] for row in screen(r)][:3], [t[:50].rstrip(" ") for t in LINES[:3]])
        r = run([WRAP, WRAP])
        self.assertEqual(screen(r), expected(LINES, 0, (1, 1)))


@requires_pasmo
class EditTests(unittest.TestCase):
    """Typing and deleting in wrapped lines: the page must equal the model
    of the edited text after every kind of change."""

    def long_line(self):
        n = max(range(1, 9), key=lambda k: len(line_rows(LINES[k - 1])))
        rows_above = sum(len(line_rows(t)) for t in LINES[:n - 1])
        return n, rows_above

    def caret_to(self, n, rows_above, col):
        return [("key", DOWN)] * rows_above + [("key", HOME)] + [("key", RIGHT)] * (col - 1)

    def check(self, ev, lines, caret):
        r = run(ev)
        self.assertEqual(screen(r), expected(lines, 0, caret))
        self.assertEqual(status_pos(r), caret)
        return r

    def test_typing_moves_words_to_the_next_row(self):
        n, above = self.long_line()
        s, e, _ = line_rows(LINES[n - 1])[0]
        col = e - 8  # inside the first row's last word
        ev = self.caret_to(n, above, col) + keys("WWWW")
        self.check(ev, edited(LINES, n, col, "WWWW"), (n, col + 4))

    def test_deleting_pulls_words_back(self):
        n, above = self.long_line()
        _, e, _ = line_rows(LINES[n - 1])[0]
        col = 6
        ev = self.caret_to(n, above, col) + [("key", DEL)] * 12
        self.check(ev, edited(LINES, n, col, deleted=12), (n, col))
        ev = self.caret_to(n, above, e + 3) + [("key", BS)] * 7
        self.check(ev, edited(LINES, n, e + 3 - 7, deleted=7), (n, e + 3 - 7))

    def test_a_line_that_gains_and_loses_rows(self):
        n, above = self.long_line()
        ev = self.caret_to(n, above, 4) + keys("abcdefghij " * 12)
        lines = edited(LINES, n, 4, "abcdefghij " * 12)
        self.assertGreater(len(line_rows(lines[n - 1])), len(line_rows(LINES[n - 1])))
        r = self.check(ev, lines, (n, 4 + 132))
        ev += [("key", BS)] * 132
        self.check(ev, LINES, (n, 4))
        self.assertIsNotNone(r)

    def test_a_word_longer_than_a_row(self):
        ev = keys("x" * 130) + [("key", HOME)] + [("key", RIGHT)] * 3 + keys(" ")
        lines = edited(LINES, 1, 1, "x" * 130)
        lines = edited(lines, 1, 4, " ")
        self.check(ev, lines, (1, 5))

    def test_a_space_past_the_edge_ends_the_line(self):
        # A line that just fits, then a space that does not: the space hangs
        # at the end of the line's only row; there is no empty row after it.
        n = 6
        text = LINES[n - 1]
        while fw(text + " the quick brown fox") <= TEXTW:
            text += " the quick brown fox"
        for ch in "mtli":
            while fw(text + ch) <= TEXTW and fw(text + " ") <= TEXTW:
                text += ch
        self.assertTrue(fw(text) <= TEXTW < fw(text + " "))
        typed = text[len(LINES[n - 1]):] + " "
        lines = edited(LINES, n, len(LINES[n - 1]) + 1, typed)
        self.assertEqual(line_rows(lines[n - 1]), [(0, len(text) + 1, True)])
        rows_above = sum(len(line_rows(t)) for t in LINES[:n - 1])
        ev = [("key", DOWN)] * rows_above + [("key", END_)] + keys(typed)
        r = run(ev)
        want = expected(lines, 0, (n, len(text) + 2))
        # The space is past the right edge, so nothing of it is drawn; the
        # caret after it is at the edge, i.e. after the row's last drawn
        # character (the same pixel, read back as that column).
        self.assertEqual(edges(text)[-1], 4 + TEXTW)
        self.assertEqual(want[rows_above][2], [len(text) + 1])
        want[rows_above] = (want[rows_above][0], [], [len(text)])
        self.assertEqual(screen(r), want)
        self.assertEqual(status_pos(r), (n, len(text) + 2))

    def test_deleting_a_rows_last_space_shows_the_caret_on_the_next(self):
        # A row ending in two spaces: deleting the second leaves the rows
        # below as they were, only shifted, so only the first row is measured
        # again, but the caret, now at the next row's start, is drawn there.
        n, above = self.long_line()
        para = LINES[n - 1]
        e = line_rows(para)[0][1]
        self.assertEqual(para[e - 1], " ")
        text = para[:e] + " " + para[e:]
        rows = line_rows(text)
        self.assertEqual(rows[0][1], e + 1)
        self.assertEqual([(s - 1, t - 1, z) for s, t, z in rows[1:]], line_rows(para)[1:])
        doc = list(LINES)
        doc[n - 1] = text
        ev = self.caret_to(n, above, e + 1) + [("key", DEL)]
        r = run(ev, files={"EDTEST.MD": "\r\n".join(doc).encode("latin-1")})
        want = expected(LINES, 0, (n, e + 1))
        self.assertEqual(want[above + 1][2], [0])
        self.assertEqual(screen(r), want)
        self.assertEqual(status_pos(r), (n, e + 1))

    def test_random_edits_in_paragraphs(self):
        rng = random.Random(1212)
        for trial in range(4):
            with self.subTest(trial=trial):
                lines = list(LINES)
                n, above = self.long_line()
                col = rng.randrange(1, len(lines[n - 1]) + 1)
                ev = self.caret_to(n, above, col)
                for _ in range(24):
                    kind = rng.choice(["type", "type", "bs", "del", "left", "right", "space"])
                    text = lines[n - 1]
                    if kind == "type":
                        word = rng.choice(["a", "be", "PcW16", "Mm", "lilt", "WWW"])
                        ev += keys(word)
                        lines = edited(lines, n, col, word)
                        col += len(word)
                    elif kind == "space":
                        ev += keys(" ")
                        lines = edited(lines, n, col, " ")
                        col += 1
                    elif kind == "bs" and col > 1:
                        ev.append(("key", BS))
                        col -= 1
                        lines = edited(lines, n, col, deleted=1)
                    elif kind == "del" and col <= len(text):
                        ev.append(("key", DEL))
                        lines = edited(lines, n, col, deleted=1)
                    elif kind == "left" and col > 1:
                        ev.append(("key", LEFT))
                        col -= 1
                    elif kind == "right" and col <= len(text):
                        ev.append(("key", RIGHT))
                        col += 1
                r = run(ev)
                start = page_start(r, lines)
                self.assertEqual(screen(r), expected(lines, start, (n, col)))

    def test_same_files_as_mdedit3_for_the_same_keys(self):
        import test_m11_mdedit3 as t3
        ev = ([("key", RIGHT)] * 2 + shift(RIGHT, 6) + [COPY, ("key", END_), PASTE]
              + keys("Hello") + [("key", 13), ("key", BS), UNDO, REDO, SELALL, ("key", RIGHT)]
              + [CUT, ("key", END_, 4), PASTE, WRAP] + keys("xyz") + [SAVE, QUIT])
        three = t3.run(ev)
        four = run(ev, files={"EDTEST.MD": DOC})
        self.assertTrue(three.cpu.exited and four.cpu.exited)
        self.assertEqual(four.cpu.disk.file("EDTEST.MD"), three.cpu.disk.file("EDTEST.MD"))
        self.assertEqual(four.cpu.disk.file("EDTEST.BAK"), DOC)
        self.assertIsNone(four.cpu.disk.file("MDEDIT4.TMP"))


@requires_pasmo
class MovementTests(unittest.TestCase):
    def test_down_moves_by_rows_keeping_x(self):
        rows = all_rows(LINES)
        r = run([("key", RIGHT)] * 9 + [("key", DOWN)] * 4)
        x = edges(LINES[0][rows[0][1]:rows[0][2]])[9]
        n, s, e, last = rows[4]
        seg = LINES[n - 1][s:e]
        # ColAt: the first character whose middle the x has not passed
        k = 0
        w = 0
        while k < len(seg):
            a = fw(seg[k])
            if 2 * (x - 4) < 2 * w + a:
                break
            w += a
            k += 1
        col = s + 1 + k
        if not last:
            col = min(col, e)
        self.assertEqual(status_pos(r), (n, min(col, len(LINES[n - 1]) + 1)))

    def test_scrolling_down_and_up_by_rows(self):
        total = len(all_rows(LINES))
        r = run([("key", DOWN)] * (ROWS + 2))
        self.assertEqual(page_start(r, LINES), 3, "scrolled row by row: the caret on the last row")
        caret_row = [k for k, row in enumerate(screen(r)) if row[2]]
        self.assertEqual(caret_row, [ROWS - 1])
        r = run([("key", DOWN)] * (ROWS + 2) + [("key", UP)] * (ROWS + 1))
        self.assertEqual(page_start(r, LINES), 1)
        self.assertGreater(total, ROWS)

    def test_pgdn_and_ctrl_end(self):
        r = run([("key", END_, 4)])
        lines_n = len(LINES)
        self.assertEqual(status_pos(r), (lines_n, len(LINES[-1]) + 1))
        start = page_start(r, LINES)
        self.assertEqual(screen(r), expected(LINES, start, (lines_n, len(LINES[-1]) + 1)))
        r = run([("key", PGDN)])
        start = page_start(r, LINES)
        self.assertEqual(screen(r), expected(LINES, start, status_pos(r)))

    def test_click_on_a_wrapped_row(self):
        rows = all_rows(LINES)
        k = next(i for i, row in enumerate(rows[:ROWS]) if not row[3] and i > 0)
        n, s, e, _ = rows[k + 1]
        seg = LINES[n - 1][s:e]
        y = CY + (k + 1) * LINEH + 4
        for px in (0, 37, fw(seg) // 2, min(fw(seg) + 30, 548)):
            with self.subTest(px=px):
                r = run([("mdown", CX + 4 + px, y), ("mup", CX + 4 + px, y)])
                kk, w = 0, 0
                while kk < len(seg):
                    a = fw(seg[kk])
                    if 2 * px < 2 * w + a:
                        break
                    w += a
                    kk += 1
                col = s + 1 + kk
                if not rows[k + 1][3]:
                    col = min(col, e)
                self.assertEqual(status_pos(r), (n, col))


@requires_pasmo
class CostTests(unittest.TestCase):
    def test_typing_measures_few_rows(self):
        n = max(range(1, 9), key=lambda k: len(line_rows(LINES[k - 1])))
        above = sum(len(line_rows(t)) for t in LINES[:n - 1])
        ev = [("key", DOWN)] * above + [("key", HOME)] + [("key", RIGHT)] * 5
        r1 = run(ev)
        r2 = run(ev + keys("a"))
        calls = sum(1 for f, _ in r2.cpu.os_log if f == 82) - sum(1 for f, _ in r1.cpu.os_log if f == 82)
        # 17 in the simulator: re-measuring two rows, then drawing them and the caret's row
        self.assertLess(calls, 25, "one typed character re-measures a row or two, not the page")
        self.calls = calls

    def test_code_spans_banks(self):
        import tempfile
        from pbas.prg import build
        with tempfile.TemporaryDirectory() as tmp:
            report = build(PATH, Path(tmp) / "m.asm", Path(tmp) / "m.prg", runtime_sections="all")
        self.assertGreaterEqual(len([b for b in report.banked.banks if b.procedures]), 2)
        self.assertLessEqual(report.banked.resident_size, 16384)


if __name__ == "__main__":
    unittest.main()
