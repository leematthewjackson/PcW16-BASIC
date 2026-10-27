"""M5d — GUI usability (LANGUAGE-SPEC.md §5, §6).

Dynamic labels (``LABEL Name$``), up to six buttons in two rows, and the
Return key for a ``DEFAULT`` button. Behaviour tests build with Pasmo and
run on the project simulator under the M2.1 memory checker, with the
H-PAINT display model extended to labels; none of this is XAnne evidence.
"""
from __future__ import annotations

import tempfile
import re
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run
from pbas import SourceError, check_source, generate, parse
from pbas.layout import (
    BIND_LABEL,
    BUTTON_ROWS,
    DIALOG_RECT,
    LABEL_SHOW_MAX,
    MAX_LAYOUT_BUTTONS,
    build_dialog,
)
from pbas.prg import build
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime" / "runtime.z80.asm"
LONG_ERR = "Runtime error: string too long at line {}"
CHAR_ERR = "Runtime error: label text has an unsupported character at line {}"
WIDEST = "W" * 24  # the widest 24-character text: 264 px (font-7 W = 11 px, XAnne)
SENTENCE = "the quick brown fox jump"  # 24 ordinary characters
RETURN = 0x0D


def gen(src: str) -> str:
    return generate(check_source(src))


def window(body: str, buttons: int = 1, default: int | None = None, subs: str = "") -> str:
    """A WINDOW program: *body* rows, then *buttons* buttons B1..Bn, each
    with its own handler that records its number in Who$."""
    lines = ['DIM Who$ AS STRING', 'WINDOW "W"', body.rstrip("\n")]
    for i in range(1, buttons + 1):
        mark = ", DEFAULT" if default == i else ""
        lines.append(f'BUTTON "B{i}", H{i}{mark}')
    for i in range(1, buttons + 1):
        lines.append(f'SUB H{i}\nWho$ = "{i}"\nEND SUB')
    return "\n".join(line for line in lines if line) + "\n" + subs + "END\n"


def numbers(src: str) -> dict:
    """Object numbers: buttons by caption, dynamic labels by variable."""
    layout = build_dialog(check_source(src))
    result = {o.text: o.number for o in layout.objects if o.kind == "BUTTON"}
    result.update({r.var_name: r.number for r in layout.bindings})
    return result


# ------------------------------------------------------------- frontend
class M5dFrontendTests(unittest.TestCase):
    def reject(self, src: str) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            check_source(src)
        return caught.exception

    def test_label_with_a_string_variable(self):
        program = check_source(window("DIM S$ AS STRING\nLABEL S$\nLABEL Undeclared$"))
        self.assertEqual(program.variables["UNDECLARED$"].type, "STRING")
        self.assertEqual(program.variables["UNDECLARED$"].origin, "LABEL")
        labels = [w for w in program.widgets if w.kind == "LABEL"]
        self.assertEqual([(w.caption, w.var_name) for w in labels], [(None, "S$"), (None, "UNDECLARED$")])
        self.assertEqual([(b.var_name, b.widget, b.capacity) for b in program.bindings],
                         [("S$", "LABEL", 25), ("UNDECLARED$", "LABEL", 25)])
        check_source(window("LABEL Plain\nDIM Plain AS STRING"))  # no $ needed

    def test_label_variable_must_be_string(self):
        err = self.reject(window("DIM N AS INTEGER\nLABEL N"))
        self.assertEqual((err.line, err.column), (4, 7))
        self.assertIn("LABEL shows a STRING variable; N is INTEGER (use a STRING and STR$)", err.message)
        err = self.reject(window("LABEL T\nDIM T AS BOOLEAN"))
        self.assertIn("incompatible UI bindings", err.message)
        self.assertIn("string literal or a STRING variable", self.reject(window('LABEL "a" + "b"')).message)
        self.assertIn("string literal or a STRING variable",
                      self.reject(window('DIM S$ AS STRING\nLABEL LEFT$(S$, 2)')).message)

    def test_one_control_per_variable(self):
        # checked where the controls are laid out (pbas.layout), as in M3b
        for body in ("LABEL S$\nTEXTBOX S$", "LABEL S$\nLABEL S$", "TEXTBOX S$\nLABEL S$"):
            with self.subTest(body=body), self.assertRaises(SourceError) as caught:
                build_dialog(check_source(window(body)))
            self.assertIn("already bound to a control at line 3", caught.exception.message)
            self.assertEqual(caught.exception.line, 4)

    def test_default_button_syntax(self):
        nodes = parse(window("", buttons=2, default=2))
        buttons = [n for n in nodes if type(n).__name__ == "Button"]
        self.assertEqual([b.default for b in buttons], [False, True])
        check_source(window("DIM Default AS INTEGER\nDefault = 1", buttons=1, default=1))  # not reserved
        err = self.reject('WINDOW "W"\nBUTTON "A", H, OTHER\nSUB H\nEND SUB\nEND\n')
        self.assertEqual((err.line, err.message), (2, "expected DEFAULT or KEY, got OTHER"))
        self.reject('WINDOW "W"\nBUTTON "A", H, "DEFAULT"\nSUB H\nEND SUB\nEND\n')
        self.reject('WINDOW "W"\nBUTTON "A", H, DEFAULT, DEFAULT\nSUB H\nEND SUB\nEND\n')

    def test_one_default_per_window(self):
        src = 'WINDOW "W"\nBUTTON "A", H, DEFAULT\nBUTTON "B", H, DEFAULT\nSUB H\nEND SUB\nEND\n'
        err = self.reject(src)
        self.assertEqual((err.line, err.column), (3, 1))
        self.assertIn("only one BUTTON may be DEFAULT (the first is at line 2)", err.message)


# ------------------------------------------------------------- layout
class M5dLayoutTests(unittest.TestCase):
    def rects(self, layout, kind):
        out = []
        for o in layout.objects:
            if o.kind == kind:
                out.append(tuple(int.from_bytes(o.definition[1 + 2 * i : 3 + 2 * i], "little")
                                 for i in range(4)))
        return out

    def test_button_rows_for_every_count(self):
        self.assertEqual(MAX_LAYOUT_BUTTONS, 6)
        width = DIALOG_RECT[2]
        for count in range(1, 7):
            with self.subTest(count=count):
                layout = build_dialog(check_source(window("", buttons=count)))
                rects = self.rects(layout, "BUTTON")
                self.assertEqual(len(rects), count)
                rows = [rects[:3], rects[3:]] if count > 3 else [rects]
                self.assertEqual(BUTTON_ROWS, (180, 208))  # spec: rows at y=180 and y=208
                for row, top in zip(rows, (180, 208)):
                    self.assertTrue(all(r[1] == top and r[2:] == (96, 24) for r in row))
                    xs = [r[0] for r in row]
                    self.assertEqual([b - a for a, b in zip(xs, xs[1:])], [110] * (len(xs) - 1))
                    left, right = xs[0], width - (xs[-1] + 96)
                    self.assertLessEqual(abs(left - right), 1)  # centred
                # every button is inside the background box (2,26,356,212)
                for x, y, w, h in rects:
                    self.assertTrue(2 <= x and x + w <= 358 and 26 <= y and y + h <= 238)
                # handlers dispatch by object number, in source order
                self.assertEqual([sub for _, sub in layout.handler_rows],
                                 [f"H{i}" for i in range(1, count + 1)])

    def test_three_buttons_or_fewer_keep_the_m3a_bytes(self):
        # No DEFAULT, <= 3 buttons: the exact POC/M3a button records.
        layout = build_dialog(check_source(window('LABEL "x"', buttons=3)))
        buttons = [o.definition for o in layout.objects if o.kind == "BUTTON"]
        self.assertEqual([b[1:3] for b in buttons], [bytes((22, 0)), bytes((132, 0)), bytes((242, 0))])
        self.assertTrue(all(b[9:17] == bytes(8) for b in buttons))
        self.assertEqual(layout.focus_object, layout.handler_rows[0][0])

    def test_seventh_button_is_rejected(self):
        with self.assertRaises(SourceError) as caught:
            build_dialog(check_source(window("", buttons=7)))
        self.assertEqual(caught.exception.line, 3 + 6)
        self.assertIn("at most 6 BUTTONs (two rows of 3)", caught.exception.message)

    def test_default_button_keys_and_focus(self):
        for count, default in ((1, 1), (3, 2), (6, 6), (5, 4)):
            with self.subTest(count=count, default=default):
                layout = build_dialog(check_source(window("", buttons=count, default=default)))
                buttons = [o for o in layout.objects if o.kind == "BUTTON"]
                for i, b in enumerate(buttons, 1):
                    want = bytes((RETURN, 0x80)) + bytes(6) if i == default else bytes(8)
                    self.assertEqual(b.definition[9:17], want)
                self.assertEqual(layout.focus_object, buttons[default - 1].number)

    def test_dynamic_label_objects(self):
        layout = build_dialog(check_source(window('LABEL "Title"\nLABEL S$\nCHECKBOX B, "tick"\nLABEL T$')))
        kinds = [o.kind for o in layout.objects]
        self.assertEqual(kinds, ["BOX", "LABEL", "LABELBOX", "DLABEL", "LABEL", "CHECKBOX",
                                 "LABELBOX", "DLABEL", "BUTTON"])
        for row in layout.bindings:
            if row.kind != BIND_LABEL:
                continue
            label = layout.objects[row.number - 1]
            box = layout.objects[row.number - 2]
            self.assertEqual(label.definition[12:], b" " * LABEL_SHOW_MAX + b"\0")
            self.assertEqual(row.template, label.definition[:12])
            self.assertEqual(row.capacity, LABEL_SHOW_MAX + 1)
            self.assertEqual(box.definition[9:], bytes((0, 8, 0, 0, 0)))  # unlinked, white, no outline
            lx, ly = (int.from_bytes(label.definition[1 + 2 * i : 3 + 2 * i], "little") for i in range(2))
            bx, by, bw, bh = (int.from_bytes(box.definition[1 + 2 * i : 3 + 2 * i], "little") for i in range(4))
            self.assertEqual((bx, by, bw, bh), (lx - 2, ly - 2, 309, 20))

    def test_dynamic_labels_use_label_rows(self):
        build_dialog(check_source(window("LABEL A$\nLABEL B$\nLABEL C$\nLABEL D$")))  # 4 x 32 px
        with self.assertRaises(SourceError) as caught:
            build_dialog(check_source(window("LABEL A$\nLABEL B$\nLABEL C$\nLABEL D$\nLABEL E$")))
        self.assertEqual(caught.exception.line, 7)
        build_dialog(check_source(window('TEXTBOX T$, "t"\nCHECKBOX C, "c"\nLABEL S$', buttons=6)))


# ------------------------------------------------------------- codegen
class M5dCodegenTests(unittest.TestCase):
    def test_switches_only_when_used(self):
        plain = gen(window('TEXTBOX T$\nLABEL "x"', buttons=3))
        self.assertIn("PB_LABELS equ 0", plain)
        self.assertIn("PB_KEYS equ 0", plain)
        self.assertNotIn("PB_LABELS equ 1", gen('DIM X AS INTEGER\nEND\n'))
        used = gen(window("LABEL S$", buttons=2, default=2))
        self.assertIn("PB_LABELS equ 1", used)
        self.assertIn("PB_KEYS equ 1", used)
        self.assertIn("; LABEL S$ (object", used)

    def test_no_os_calls_in_generated_code(self):
        self.assertNotRegex(gen(window("LABEL S$", buttons=6, default=1)), r"call\s+003Bh")


# ------------------------------------------------------------- behaviour
@requires_pasmo
class M5dBehaviourTests(unittest.TestCase):
    maxDiff = None

    def run_ok(self, src: str, **kw):
        run = guarded_run(src, **kw)
        self.assertEqual(run.violations, [], "memory-boundary violations")
        return run

    def test_every_button_runs_its_own_handler(self):
        for count in range(1, 7):
            with self.subTest(count=count):
                src = window("LABEL Who$", buttons=count)
                n = numbers(src)
                events = [("click", n[f"B{i}"]) for i in range(count, 0, -1)]
                run = self.run_ok(src, events=events)
                updates = [d for f, d in run.cpu.os_log if f == z80sim.FN_OS_OBJECT_DEFINE]
                shown = [d[1][12:-1].decode() for d in updates if d[0] == n["WHO$"]]
                self.assertEqual(shown, [""] + [str(i) for i in range(count, 0, -1)])
                self.assertEqual(run.cpu.label_text(n["WHO$"], shown=True), "1")

    def test_label_shows_its_value_when_the_window_opens(self):
        src = 'S$ = "Hello"\n' + window("LABEL S$\nLABEL E$")
        n = numbers(src)
        run = self.run_ok(src, events=[])
        self.assertEqual(run.cpu.label_text(n["S$"], shown=True), "Hello")
        self.assertEqual(run.cpu.label_text(n["E$"], shown=True), "")

    def test_long_to_short_leaves_no_stale_text(self):
        long = WIDEST  # M5d repair: 47 W's never fitted (XAnne D3)
        src = window("LABEL S$", buttons=3).replace('SUB H1\nWho$ = "1"', f'SUB H1\nS$ = "{long}"') \
                              .replace('SUB H2\nWho$ = "2"', 'SUB H2\nS$ = "ok"') \
                              .replace('SUB H3\nWho$ = "3"', 'SUB H3\nS$ = ""')
        n = numbers(src)
        seq, want = [], []
        for _ in range(3):
            for button, text in (("B1", long), ("B2", "ok"), ("B1", long), ("B3", ""), ("B2", "ok")):
                seq.append(("click", n[button]))
                want.append(text)
        run = self.run_ok(src, events=seq)
        self.assertEqual(run.cpu.label_text(n["S$"], shown=True), "ok")
        self.assertEqual(run.cpu.label_text(n["S$"]), "ok")
        # every change redrew the box (object number - 1) before the label
        log = [(f, d) for f, d in run.cpu.os_log if f == z80sim.FN_OS_OBJECT_UPDATE]
        label = n["S$"]
        pairs = [log[i][1] for i in range(len(log)) if log[i][1] in (label - 1, label)]
        self.assertEqual(pairs, [label - 1, label] * len(want))

    def test_unchanged_label_is_not_redrawn(self):
        src = 'S$ = "same"\n' + window("LABEL S$", buttons=1)
        n = numbers(src)
        run = self.run_ok(src, events=[("click", n["B1"]), ("click", n["B1"])])
        defines = [d[0] for f, d in run.cpu.os_log if f == z80sim.FN_OS_OBJECT_DEFINE]
        self.assertEqual(defines, [n["S$"]])  # only when the window opened

    def test_label_keeps_its_old_value_while_a_handler_runs(self):
        src = ('DIM N AS INTEGER\nS$ = "before"\nWINDOW "W"\nLABEL S$\nBUTTON "Go", Go\n'
               'SUB Go\nS$ = "after"\nCALL Tell\nEND SUB\nSUB Tell\nMESSAGE "now " + S$\nEND SUB\nEND\n')
        n = numbers(src)
        run = self.run_ok(src, events=[("click", n["Go"])])
        self.assertEqual(run.alerts, ["now after"])
        log = [f for f, d in run.cpu.os_log if f in (z80sim.FN_OS_ALERT, z80sim.FN_OS_OBJECT_UPDATE)]
        self.assertEqual(log, [z80sim.FN_OS_ALERT, z80sim.FN_OS_OBJECT_UPDATE, z80sim.FN_OS_OBJECT_UPDATE])
        self.assertEqual(run.cpu.label_text(n["S$"], shown=True), "after")

    def test_label_set_by_a_called_procedure(self):
        src = ('DIM N AS INTEGER\nWINDOW "W"\nLABEL S$\nBUTTON "Go", Go\n'
               'SUB Go\nN = N + 1\nCALL Show\nEND SUB\nSUB Show\nS$ = "N=" + STR$(N)\nEND SUB\nEND\n')
        n = numbers(src)
        run = self.run_ok(src, events=[("click", n["Go"])] * 3)
        self.assertEqual(run.cpu.label_text(n["S$"], shown=True), "N=3")

    def test_dynamic_label_contract(self):
        """M5d recovery: at most 24 printable ASCII characters (#20-#7E),
        checked before anything is defined or drawn; never cut."""
        cases = [
            (SENTENCE, None), (WIDEST, None), ("i" * 24, None), ("~" * 24, None), (" " * 24, None),
            ("x" * 25, LONG_ERR), ("W" * 47, LONG_ERR), ("y" * 63, LONG_ERR),
        ]
        for text, err in cases:
            with self.subTest(text=text):
                src = window("LABEL S$", buttons=1).replace('Who$ = "1"', f'S$ = "{text}"')
                n = numbers(src)
                run = self.run_ok(src, events=[("click", n["B1"]), ("click", n["B1"])])
                if err is None:
                    self.assertEqual(run.cpu.label_text(n["S$"], shown=True), text)
                    self.assertEqual(run.alerts, [])
                else:
                    self.assertEqual(run.alerts, [err.format(3)])
                    self.assertTrue(run.cpu.exited)
                    self.assertEqual(run.cpu.label_text(n["S$"], shown=True), "")  # never drawn

    def test_unsupported_characters_are_refused(self):
        for code in (1, 9, 13, 31, 127, 128, 200, 255):
            with self.subTest(code=code):
                src = window("LABEL S$", buttons=1).replace('Who$ = "1"', f'S$ = "ok" + CHR$({code})')
                n = numbers(src)
                run = self.run_ok(src, events=[("click", n["B1"])])
                self.assertEqual(run.alerts, [CHAR_ERR.format(3)])
                self.assertEqual(run.cpu.label_text(n["S$"], shown=True), "")
                defines = [d for f, d in run.cpu.os_log if f == z80sim.FN_OS_OBJECT_DEFINE]
                self.assertTrue(all(b"ok" not in d[1] for d in defines))  # nothing defined

    def test_every_printable_character_fits_the_label(self):
        """Model check (font-7 table; the evidence is XAnne script G1): 24
        copies of every printable character stay within the 305-px label."""
        for code in range(32, 127):
            self.assertLessEqual(z80sim.font7_width(bytes([code]) * 24), 305, chr(code))
        self.assertEqual(z80sim.font7_width(b"W"), 11)  # measured in XAnne (D3 screenshots)

    def test_size_checks_at_window_opening(self):
        for text, err in (("y" * 25, LONG_ERR), ("ok\t", CHAR_ERR)):
            with self.subTest(text=text):
                value = f'"{text}"' if "\t" not in text else '"ok" + CHR$(9)'
                run = self.run_ok(f"S$ = {value}\n" + window("LABEL S$"))
                self.assertEqual(run.alerts, [err.format(4)])
                self.assertNotIn(z80sim.FN_OS_DIALOG_DISPLAY, [f for f, _ in run.cpu.os_log])

    def test_the_width_call_is_never_used(self):
        """WIDTHDG (owner, XAnne): os_dialog_string_width returned carry in
        every test, so the labels never call it. M11 corrective: the one
        call is TEXTWIDTH's (rt_text_width, IF PB_TEXTW), which reads HL and
        not the carry (docs/M11-CORRECTIVE.md); no label code uses it."""
        text = RUNTIME.read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"ld a,82\b", text)), 1)
        width = text[text.index("\nrt_text_width:"):]
        self.assertIn("ld a,82", width[:width.index("\n    ret\n")])
        src = window("LABEL S$", buttons=1).replace('Who$ = "1"', f'S$ = "{WIDEST}"')
        n = numbers(src)
        run = self.run_ok(src, events=[("click", n["B1"])])
        self.assertNotIn(z80sim.FN_OS_DIALOG_STRING_WIDTH, [f for f, _ in run.cpu.os_log])

    def test_repeated_transitions_never_draw_outside_a_label(self):
        """Long, short, empty, longest ... many times: no label wider than its
        object (memguard rule L) and no glyph of an earlier text remains."""
        texts = {"B1": WIDEST, "B2": "ok", "B3": "", "B4": SENTENCE}
        src = window("LABEL S$", buttons=4)
        for i, text in enumerate(texts.values(), 1):
            src = src.replace(f'Who$ = "{i}"', f'S$ = "{text}"')
        n = numbers(src)
        order = ["B1", "B2", "B3", "B1", "B4", "B2", "B4", "B3", "B1", "B1", "B4", "B1"] * 4
        run = self.run_ok(src, events=[("click", n[b]) for b in order])
        self.assertEqual(run.cpu.label_text(n["S$"], shown=True), WIDEST)
        updates = [d for f, d in run.cpu.os_log if f == z80sim.FN_OS_OBJECT_UPDATE]
        label = n["S$"]
        changes = sum(1 for a, b in zip([""] + order, order) if texts.get(a, "") != texts[b])
        self.assertEqual(updates, [label - 1, label] * changes)

    def test_the_simulator_flags_text_wider_than_its_label(self):
        """Structural check: a *literal* label is not limited to 24
        characters (no compile-time metrics; risk R-LABELW), so a too-wide
        literal is still drawn, and memguard's rule L reports it."""
        run = guarded_run(window('LABEL "' + "W" * 40 + '"'))
        self.assertTrue(any(v.startswith("L: label") for v in run.violations), run.violations)

    def test_return_runs_the_default_button(self):
        src = window("LABEL Who$", buttons=6, default=5)
        n = numbers(src)
        for shift in (0, 1, 4, 0x10):  # shift, ctrl, keypad Enter: shift state ignored
            with self.subTest(shift=shift):
                run = self.run_ok(src, events=[("press", RETURN, shift)])
                self.assertEqual(run.cpu.label_text(n["WHO$"], shown=True), "5")
        run = self.run_ok(src, events=[("press", ord("a"), 0), ("press", 32, 0), ("press", 27, 0)])
        self.assertEqual(run.cpu.label_text(n["WHO$"], shown=True), "")  # other keys: nothing
        self.assertIn((z80sim.FN_OS_SET_FOCUS, n["B5"]), run.cpu.os_log)

    def test_return_does_nothing_without_a_default_button(self):
        src = window("LABEL Who$", buttons=3)
        n = numbers(src)
        run = self.run_ok(src, events=[("press", RETURN, 0), ("click", n["B2"]), ("press", RETURN, 0)])
        self.assertEqual(run.cpu.label_text(n["WHO$"], shown=True), "2")
        self.assertIn((z80sim.FN_OS_SET_FOCUS, n["B1"]), run.cpu.os_log)

    def test_return_reads_controls_like_a_click(self):
        src = ('WINDOW "W"\nTEXTBOX T$, "t"\nCHECKBOX C, "c"\nLABEL S$\nBUTTON "Show", Show, DEFAULT\n'
               'SUB Show\nIF C THEN\nS$ = UCASE$(T$)\nELSE\nS$ = T$\nEND IF\nT$ = ""\nEND SUB\nEND\n')
        layout = build_dialog(check_source(src))
        n = {r.var_name: r.number for r in layout.bindings}
        run = self.run_ok(src, events=[("edit", n["T$"], "hello"), ("press", RETURN, 0),
                                       ("edit", n["T$"], "again"), ("click", n["C"]),
                                       ("press", RETURN, 0)])
        self.assertEqual(run.cpu.label_text(n["S$"], shown=True), "AGAIN")
        self.assertEqual(run.cpu.control_text(n["T$"], shown=True), "")


@requires_pasmo
class M5dExampleTests(unittest.TestCase):
    def run_file(self, path: Path, **kw):
        run = guarded_run(path.read_text(encoding="utf-8"), **kw)
        self.assertEqual(run.violations, [])
        return run

    def test_visitor_counter(self):
        path = ROOT / "examples" / "visitor_counter.pbas"
        n = numbers(path.read_text(encoding="utf-8"))
        status, counts, note = n["STATUS$"], n["COUNTS$"], n["NOTE$"]
        run = self.run_file(path, events=[])
        self.assertEqual([run.cpu.label_text(x, shown=True) for x in (status, counts, note)],
                         ["Inside: 0 of 5", "Today 0, peak 0", ""])
        run = self.run_file(path, events=[("press", RETURN, 0)] * 5 + [("click", n["In"])])
        self.assertEqual([run.cpu.label_text(x, shown=True) for x in (status, counts, note)],
                         ["Inside: 5 of 5 (full)", "Today 5, peak 5", "Full - wait for someone"])
        run = self.run_file(path, events=[("click", n["In"])] * 3 + [("click", n["Out"])] * 4
                            + [("click", n["Reset"]), ("click", n["Quit"])])
        self.assertEqual([run.cpu.label_text(x, shown=True) for x in (status, counts, note)],
                         ["Inside: 0 of 5", "Today 0, peak 0", ""])
        self.assertTrue(run.cpu.exited)

    def test_settings_panel(self):
        path = ROOT / "examples" / "settings_panel.pbas"
        src = path.read_text(encoding="utf-8")
        layout = build_dialog(check_source(src))
        n = {r.var_name: r.number for r in layout.bindings}
        n.update({o.text: o.number for o in layout.objects if o.kind == "BUTTON"})
        disk = z80sim.Disk()
        run = self.run_file(path, disk=disk, events=[
            ("click", n["Load"]),
            ("edit", n["OWNER$"], "Ada"), ("click", n["SOUND"]), ("press", RETURN, 0),
            ("click", n["Defaults"]), ("click", n["Check"]),
            ("click", n["Load"]),
            ("edit", n["OWNER$"], "W" * 30), ("click", n["Save"]),
            ("edit", n["OWNER$"], "a|b"), ("click", n["Save"]),
            ("click", n["Quit"]),
        ])
        self.assertEqual(run.alerts, ["File not loaded: PBSETUP.TXT (not found)", "File saved: PBSETUP.TXT",
                                      "File loaded: PBSETUP.TXT", "File saved: PBSETUP.TXT"])
        self.assertEqual(disk.file("PBSETUP.TXT"), b"W" * 30 + b"|0")
        self.assertEqual(run.cpu.label_text(n["STATUS$"], shown=True), "Name empty or has |")
        self.assertTrue(run.cpu.exited)
        run = self.run_file(path, disk=disk, events=[("click", n["Load"])])
        self.assertEqual(run.cpu.label_text(n["STATUS$"], shown=True), "Loaded for " + "W" * 13)
        run = self.run_file(path, disk=disk, events=[("click", n["Load"]), ("click", n["Check"])])
        self.assertFalse(run.cpu.control_checked(n["SOUND"], shown=True))
        self.assertEqual(run.cpu.label_text(n["STATUS$"], shown=True), "Sound off, name 30 chars")

    def test_xanne_label_check_program(self):
        """G1: the M5d recovery validation program."""
        path = ROOT / "developer-tests" / "m5d_labels.pbas"
        n = numbers(path.read_text(encoding="utf-8"))
        shown, last = n["SHOWN$"], n["LAST$"]
        run = self.run_file(path, events=[])
        self.assertEqual([run.cpu.label_text(x, shown=True) for x in (shown, last)], ["Ready", "Press 1 or Return"])
        # every printable character, 24 times, by Return (DEFAULT) and by click
        run = self.run_file(path, events=[("press", RETURN, 0)] * 95)
        self.assertEqual(run.alerts, [])
        self.assertEqual([run.cpu.label_text(x, shown=True) for x in (shown, last)], ["~" * 24, "Char 126 x 24"])
        run = self.run_file(path, events=[("click", n["1 Next char"])] * 96)  # wraps to space
        self.assertEqual([run.cpu.label_text(x, shown=True) for x in (shown, last)], [" " * 24, "Char 32 x 24"])
        cycle = ["2 Widest", "3 Short", "4 Empty", "2 Widest", "1 Next char", "3 Short", "4 Empty"]
        run = self.run_file(path, events=[("click", n[b]) for b in cycle * 5])
        self.assertEqual(run.alerts, [])
        self.assertEqual([run.cpu.label_text(x, shown=True) for x in (shown, last)], ["", "Empty line above"])
        run = self.run_file(path, events=[("click", n["2 Widest"]), ("click", n["5 Too long"]), ("click", n["3 Short"])])
        self.assertEqual(run.alerts, [LONG_ERR.format(17)])
        self.assertEqual(run.cpu.label_text(shown, shown=True), WIDEST)
        run = self.run_file(path, events=[("click", n["3 Short"]), ("click", n["6 Bad char"])])
        self.assertEqual(run.alerts, [CHAR_ERR.format(17)])
        self.assertEqual(run.cpu.label_text(shown, shown=True), "ok")
        self.assertTrue(run.cpu.exited)

    def test_d3_program_meets_the_defined_errors(self):
        """The unchanged D3 program (47 W's, 33-character status texts) is
        refused cleanly under the 24-character contract."""
        path = ROOT / "developer-tests" / "m5d_edges.pbas"
        n = numbers(path.read_text(encoding="utf-8"))
        run = self.run_file(path, events=[("click", n["2 Short"]), ("click", n["1 Long"])])
        self.assertEqual(run.alerts, [LONG_ERR.format(13)])
        run = self.run_file(path, events=[("click", n["2 Short"]), ("click", n["3 Empty"])])
        self.assertEqual(run.alerts, [LONG_ERR.format(14)])


if __name__ == "__main__":
    unittest.main()
