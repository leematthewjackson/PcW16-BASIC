"""M12 Stage C: printing (LANGUAGE-SPEC §5.13, docs/M12-PRINTING.md).

PAGE statements build one page in Rosanne's print meta-file and PAGE PRINT
sends it to the printer. The simulator models the documented typo font and
meta-file calls (ROSAN283 83..105; z80sim._print_call) and keeps every page
it was asked to print as records, so these tests check exactly what would
reach the printer: the font, each character's position, every line. The
fonts' widths are a model (z80sim.typo_width). Rosanne's printer driver
does not draw a line between its documented ends (M12 corrective,
docs/M12-PRINTING.md §6): each solid rectangle is sent so that it prints
exactly, and solids() reads the records back as those rectangles;
test_m12_printgeom puts them on paper through tests/printmodel.py.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import z80sim
from memguard import guarded_run
from pbas import SourceError, check_source, generate
from pbas.layout import build_dialog
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "printdemo.pbas"
TIMES = 0x0101
U = 25  # 1/1800" per point


def run(src: str, banks=None, **sim):
    r = guarded_run(src, build_options={"runtime_sections": banks} if banks else None, **sim)
    assert r.violations == [], r.violations[:5]
    return r


def printed(r) -> list[list[tuple]]:
    return [page["records"] for page in r.cpu.printed]


def solids(records) -> list[tuple[int, int, int, int]]:
    """The rectangles (x, y, w, h in 1/1800") the lines print as (rt_pg_solid):
    an hline prints from left to right + its thickness; an hline square
    (right = left) followed by a vline at its x, as thick, is one rectangle
    from the square's top to the vline's bottom; a vline alone is a box's
    side, read as from its top."""
    out, i = [], 0
    while i < len(records):
        rec = records[i]
        nxt = records[i + 1] if i + 1 < len(records) else None
        if rec[0] == "hline" and rec[1] == rec[2] and nxt and nxt[0] == "vline" and nxt[1:3] == (rec[1], rec[3]) \
                and nxt[4] == rec[4]:
            out.append((rec[1], rec[3], rec[4], nxt[3] - rec[3]))
            i += 2
            continue
        if rec[0] == "hline":
            out.append((rec[1], rec[3], rec[2] - rec[1] + rec[4], rec[4]))
        elif rec[0] == "vline":
            out.append((rec[1], rec[2], rec[4], rec[3] - rec[2]))
        i += 1
    return out


def lines_of(records) -> list[tuple[int, str, int, int]]:
    """(top, text, first x, end x) of each printed line, in 1/1800"."""
    out, size, bold, top = [], 10, False, None
    for rec in records:
        if rec[0] == "font":
            size = rec[2]
        elif rec[0] == "style":
            bold = bool(rec[1] & 1)
        elif rec[0] == "y":
            top = rec[2]
            out.append([top, "", None, None])
        elif rec[0] == "char":
            line = out[-1]
            line[1] += chr(rec[1])
            line[2] = rec[3] if line[2] is None else line[2]
            line[3] = rec[3] + z80sim.typo_width(rec[1], size, bold)
    return [tuple(x) for x in out]


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> str:
        with self.assertRaises(SourceError) as ctx:
            check_source(src)
        return str(ctx.exception)

    def test_statements(self):
        self.assertIn("PAGE TEXT takes 3 arguments", self.reject("PAGE TEXT 1, 2\nEND\n"))
        self.assertIn("PAGE LINE takes 4 or 5 arguments", self.reject("PAGE LINE 1, 2, 3\nEND\n"))
        self.assertIn("PAGE NEW takes 0 arguments", self.reject("PAGE NEW 1\nEND\n"))
        self.assertIn("argument 3 must be STRING", self.reject("PAGE TEXT 1, 2, 3\nEND\n"))
        self.assertIn("argument 1 must be INTEGER", self.reject('PAGE FILL "a", 1, 2, 3\nEND\n'))
        self.assertIn("a print size is 6, 8, 10", self.reject("PAGE FONT 9\nEND\n"))
        self.assertIn("PAGEWIDTH expects a STRING", self.reject("DIM N AS INTEGER\nN = PAGEWIDTH(3)\nEND\n"))
        check_source("DIM S AS INTEGER\nS = 12\nPAGE NEW\nPAGE FONT S, BOLD\nPAGE FONT 72\nPAGE TEXT 0, 0, \"x\"\n"
                     "PAGE LINE 0, 0, 9, 0\nPAGE LINE 0, 0, 0, 9, 3\nPAGE BOX 0, 0, 9, 9\nPAGE FILL 0, 0, 9, 9\n"
                     "PAGE PRINT\nPAGE CLOSE\nMESSAGE STR$(IOERR + PAGEWIDTH(\"x\"))\nEND\n")

    def test_page_is_still_a_name(self):
        # accepted programs use PAGE as a constant (contacts_m8, uibench)
        check_source("CONST PAGE = 6\nDIM N AS INTEGER\nN = PAGE * 2\nEND\n")
        check_source("DIM Page AS INTEGER\nPage = 3\nPage = Page + 1\nEND\n")

    def test_only_programs_that_print_carry_it(self):
        self.assertIn("PB_PAGE equ 0", generate(check_source('MESSAGE "x"\nEND\n')))
        self.assertIn("PB_PAGE equ 1", generate(check_source("PAGE NEW\nPAGE PRINT\nEND\n")))


SAMPLE = """DIM W AS INTEGER
PAGE NEW
PAGE FONT 12, BOLD
PAGE TEXT 0, 0, "Hello, PcW16"
W = PAGEWIDTH("Hello")
PAGE LINE 0, 20, 200, 20
PAGE LINE 10, 30, 10, 90, 2
PAGE BOX 20, 30, 100, 60
PAGE FILL 130, 30, 40, 60
PAGE PRINT
MESSAGE STR$(IOERR) + " " + STR$(W)
END
"""


@requires_pasmo
class PageTests(unittest.TestCase):
    def test_a_page_exactly(self):
        for banks in (None, "all"):
            with self.subTest(banks=banks):
                src = SAMPLE if banks is None else "SUB Go\n" + SAMPLE.replace("END\n", "END SUB\nCALL Go\nEND\n")
                r = run(src, banks)
                width = sum(z80sim.typo_width(ord(c), 12, True) for c in "Hello")
                self.assertEqual(r.alerts, [f"0 {-(-width // U)}"])
                [page] = r.cpu.printed
                # A4, half-inch margins, as Rosanne's Shopping List
                self.assertEqual(page["block"][:9], bytes([0]) + (14850).to_bytes(2, "little")
                                 + (20925).to_bytes(2, "little") + (900).to_bytes(2, "little") * 2)
                recs = page["records"]
                self.assertEqual(recs[:4], [("font", TIMES, 10), ("style", 0), ("font", TIMES, 12), ("style", 1)])
                asc, desc = 12 * U * 4 // 5, 12 * U // 4
                self.assertEqual(recs[4], ("y", asc, 0, asc + desc))
                [(top, text, x0, _)] = lines_of(recs)
                self.assertEqual((top, text, x0), (0, "Hello, PcW16", 0))
                xs = [rec[3] for rec in recs if rec[0] == "char"]
                self.assertEqual(xs[1] - xs[0], z80sim.typo_width(ord("H"), 12, True))
                # Rosanne prints an hline on past its right end by its
                # thickness, and a vline from its thickness below its top
                self.assertEqual([rec for rec in recs if rec[0] in ("hline", "vline")], [
                    ("hline", 0, 199 * U, 20 * U, U),
                    ("hline", 10 * U, 10 * U, 30 * U, 2 * U),  # the vertical line: its top square,
                    ("vline", 10 * U, 30 * U, 90 * U, 2 * U),  # then the rest
                    ("hline", 20 * U, 119 * U, 30 * U, U),  # the box: top, bottom, left, right
                    ("hline", 20 * U, 119 * U, 89 * U, U),
                    ("vline", 20 * U, 30 * U, 90 * U, U),
                    ("vline", 119 * U, 30 * U, 90 * U, U),
                    ("hline", 130 * U, 130 * U, 30 * U, 40 * U),  # the fill (taller than wide)
                    ("vline", 130 * U, 30 * U, 90 * U, 40 * U),
                ])
                self.assertEqual([s for s in solids(recs) if s[2] != U or s[3] != 60 * U], [
                    (0, 20 * U, 200 * U, U), (10 * U, 30 * U, 2 * U, 60 * U),
                    (20 * U, 30 * U, 100 * U, U), (20 * U, 89 * U, 100 * U, U), (130 * U, 30 * U, 40 * U, 60 * U)])
                self.assertIsNone(r.cpu.meta)

    def test_lines_both_ways_round(self):
        r = run("PAGE NEW\nPAGE LINE 50, 10, 20, 10\nPAGE LINE 5, 40, 5, 30, 4\nPAGE LINE 7, 7, 7, 7\nPAGE PRINT\nEND\n")
        recs = [rec for rec in printed(r)[0] if rec[0] in ("hline", "vline")]
        self.assertEqual(recs, [("hline", 20 * U, 49 * U, 10 * U, U),
                                ("hline", 5 * U, 5 * U, 30 * U, 4 * U), ("vline", 5 * U, 30 * U, 40 * U, 4 * U)])
        self.assertEqual(solids(recs), [(20 * U, 10 * U, 30 * U, U), (5 * U, 30 * U, 4 * U, 10 * U)])

    def test_the_font_is_times_else_the_first(self):
        r = run(SAMPLE)
        self.assertEqual({rec[1] for rec in printed(r)[0] if rec[0] == "font"}, {TIMES})
        with mock.patch.object(z80sim, "TYPO_FONTS", ((0x0301, 0x0F, 2, "Swiss"), (0x0302, 0x0F, 0, "Other"))):
            r = run(SAMPLE)
        self.assertEqual({rec[1] for rec in printed(r)[0] if rec[0] == "font"}, {0x0301})
        with mock.patch.object(z80sim, "TYPO_FONTS", ()):
            r = run("PAGE NEW\nMESSAGE STR$(IOERR)\nEND\n")
        self.assertEqual(r.alerts, ["2"])
        self.assertIsNone(r.cpu.meta)

    def test_rosanne_refusals_set_ioerr(self):
        r = run("PAGE NEW\nMESSAGE STR$(IOERR)\nPAGE PRINT\nEND\n", meta_open_result=7)
        self.assertEqual(r.alerts[0], "7")
        self.assertEqual(r.alerts[1][:47], "Runtime error: no page is open (PAGE NEW) at li")
        r = run("PAGE NEW\nPAGE TEXT 0, 0, \"x\"\nPAGE PRINT\nMESSAGE STR$(IOERR)\nPAGE CLOSE\nEND\n", print_result=6)
        self.assertEqual(r.alerts, ["6"])
        self.assertIsNone(r.cpu.meta)
        self.assertEqual(r.cpu.printed, [])
        with mock.patch.object(z80sim, "TYPO_SIZES", (10, 12)):
            r = run("PAGE NEW\nPAGE FONT 72\nMESSAGE STR$(IOERR)\nEND\n")
        self.assertEqual(r.alerts, ["2"])

    def test_print_closes_the_page(self):
        r = run('PAGE NEW\nPAGE TEXT 0, 0, "a"\nPAGE PRINT\nPAGE TEXT 0, 0, "b"\nEND\n')
        self.assertEqual(len(r.cpu.printed), 1)
        self.assertEqual(r.alerts[0][:47], "Runtime error: no page is open (PAGE NEW) at li")

    def test_a_new_page_discards_the_open_one_and_the_end_closes(self):
        r = run("PAGE NEW\nPAGE TEXT 0, 0, \"one\"\nPAGE NEW\nPAGE TEXT 0, 0, \"two\"\nPAGE PRINT\n"
                "PAGE NEW\nPAGE TEXT 0, 0, \"three\"\nEND\n")
        self.assertEqual([lines_of(p)[0][1] for p in printed(r)], ["two"])
        self.assertIsNone(r.cpu.meta)  # closed at the program's end
        self.assertEqual([f for f, _ in r.cpu.os_log].count(105), 3)

    def test_errors_stop_the_program(self):
        cases = {
            "PAGE TEXT 0, 0, \"x\"\n": "no page is open (PAGE NEW)",
            "PAGE NEW\nPAGE TEXT 523, 0, \"x\"\n": "printing outside the page",
            "PAGE NEW\nPAGE TEXT 0, 760, \"x\"\n": "printing outside the page",
            "PAGE NEW\nPAGE TEXT -1, 0, \"x\"\n": "printing outside the page",
            "PAGE NEW\nPAGE TEXT 500, 0, \"WWWWWWWW\"\n": "printing outside the page",
            "PAGE NEW\nPAGE FILL 500, 0, 23, 5\n": "printing outside the page",
            "PAGE NEW\nPAGE FILL 10, 10, -2, 5\n": "printing outside the page",
            "PAGE NEW\nPAGE BOX 0, 700, 10, 66\n": "printing outside the page",
            "PAGE NEW\nPAGE LINE 0, 0, 10, 10\n": "a printed line is horizontal or vertical",
            "PAGE NEW\nPAGE LINE 0, 0, 10, 0, 0\n": "1 to 72 points thick",
            "PAGE NEW\nPAGE LINE 0, 0, 10, 0, 73\n": "1 to 72 points thick",
            "DIM S AS INTEGER\nS = 9\nPAGE NEW\nPAGE FONT S\n": "a print size is 6, 8, 10",
            "DIM N AS INTEGER\nN = PAGEWIDTH(\"x\")\n": "no page is open (PAGE NEW)",
        }
        for body, error in cases.items():
            with self.subTest(body=body):
                r = run(body + "PAGE PRINT\nEND\n")
                self.assertTrue(r.alerts and error in r.alerts[0], r.alerts)
                self.assertEqual(r.cpu.printed, [])

    def test_edges_fit(self):
        r = run("PAGE NEW\nPAGE FILL 0, 0, 522, 765\nPAGE LINE 521, 0, 521, 765\nPAGE FILL 5, 5, 0, 9\nPAGE PRINT\n"
                "MESSAGE STR$(IOERR)\nEND\n")
        self.assertEqual(r.alerts, ["0"])
        recs = [rec for rec in printed(r)[0] if rec[0] in ("hline", "vline")]
        self.assertEqual(solids(recs), [(0, 0, 522 * U, 765 * U), (521 * U, 0, U, 765 * U)])  # w = 0: nothing
        self.assertEqual(len(recs), 4)

    def test_pagewidth_rounds_up_and_follows_the_font(self):
        texts = ["i", "Hello", "WWW", "", "0123456789"]
        src = "DIM S$ AS STRING\nPAGE NEW\n"
        for size, bold in ((10, False), (24, True)):
            src += f"PAGE FONT {size}{', BOLD' if bold else ''}\n"
            src += "".join(f'S$ = S$ + STR$(PAGEWIDTH("{t}")) + " "\n' for t in texts)
        r = run(src + "MESSAGE S$\nEND\n")
        want = ""
        for size, bold in ((10, False), (24, True)):
            for t in texts:
                want += str(-(-sum(z80sim.typo_width(ord(c), size, bold) for c in t) // U)) + " "
        self.assertEqual(r.alerts, [want])

    def test_odd_characters_print_as_question_marks(self):
        r = run('PAGE NEW\nPAGE TEXT 0, 0, "a" + CHR$(7) + CHR$(200)\nPAGE PRINT\nEND\n')
        self.assertEqual(lines_of(printed(r)[0])[0][1], "a?" + chr(200))


def demo_buttons():
    program = check_source(DEMO.read_text(encoding="utf-8"), path=DEMO)
    lay = build_dialog(program, program.windows[0], True)
    out = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
    out.update({row.var_name: row.number for row in lay.bindings})
    return out


@requires_pasmo
class DemoTests(unittest.TestCase):
    """examples/printdemo.pbas, as the owner will run it (Session 2)."""

    B = demo_buttons()
    MARGIN, WIDTH = 36, 450

    def run_demo(self, names, **sim):
        src = DEMO.read_text(encoding="utf-8")
        events = [("edit", self.B["WHO$"], "Ann")] + [("click", self.B[n]) for n in names] + [("click", self.B["Quit"])]
        r = guarded_run(src, path=DEMO, events=events, max_steps=400_000_000,
                        build_options={"runtime_sections": "all"}, **sim)
        self.assertEqual(r.violations, [])
        self.assertFalse([a for a in r.alerts if a.startswith("Runtime error")], r.alerts)
        self.assertTrue(r.cpu.exited)
        return r

    def test_letter_is_wrapped_to_the_width(self):
        r = self.run_demo(["Letter"])
        [page] = printed(r)
        lines = lines_of(page)
        self.assertEqual(lines[0][1], "Printed from PcW16 BASIC")
        body = [line for line in lines[1:-1]]
        self.assertGreater(len(body), 4)
        self.assertIn("Ann.", " ".join(line[1] for line in body))
        for top, text, x0, x1 in body:
            self.assertEqual(x0, self.MARGIN * U)
            self.assertLessEqual(x1, (self.MARGIN + self.WIDTH) * U, text)
        # each line is as full as it can be: in a paragraph (lines 14 points
        # apart) the next line's first word would not have fitted
        for (top, text, _, x1), (ntop, ntext, _, _) in zip(body, body[1:]):
            if ntop - top == 14 * U:
                extra = sum(z80sim.typo_width(ord(c), 10) for c in " " + ntext.split()[0])
                # (PAGEWIDTH rounds each part up: within 2 points)
                self.assertGreater(x1 + extra, (self.MARGIN + self.WIDTH - 2) * U, (text, ntext))
        # the signature ends at the right margin (PAGEWIDTH rounds up)
        sig = lines[-1]
        self.assertEqual(sig[1], "PcW16 BASIC, M12")
        self.assertLessEqual(sig[3], (self.MARGIN + self.WIDTH) * U)
        self.assertGreater(sig[3], (self.MARGIN + self.WIDTH - 1) * U)
        self.assertEqual(r.alerts, [])

    def test_table_numbers_are_right_aligned(self):
        r = self.run_demo(["Table"])
        lines = lines_of(printed(r)[0])
        numbers = [line for line in lines if line[1].isdigit()]
        self.assertEqual([n[1] for n in numbers], ["120", "345", "78", "210", "32", "164", "949"])
        for _, text, _, x1 in numbers:
            self.assertGreater(x1, 299 * U)
            self.assertLessEqual(x1, 300 * U)

    def test_chart_bars_are_the_figures(self):
        r = self.run_demo(["Chart"])
        bars = [s for s in solids(printed(r)[0]) if s[2] == 40 * U]
        self.assertEqual([s[0] // U for s in bars], [76 + 64 * i for i in range(6)])  # 24 points apart
        self.assertEqual([s[3] // U for s in bars], [60, 172, 39, 105, 16, 82])  # amounts / 2
        self.assertEqual({s[1] + s[3] for s in bars}, {300 * U})  # all stand on the base line

    def test_no_printer(self):
        r = self.run_demo(["Letter"], print_result=6)
        self.assertEqual(r.alerts, ["Not printed: No valid printer set up (code 6)"])


if __name__ == "__main__":
    unittest.main()
