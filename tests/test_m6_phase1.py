"""M6 Phase 1 — native application interfaces (LANGUAGE-SPEC.md §5.1).

Named windows (LARGE, SHOW), RADIO, NUMBERBOX (+ SPIN), ASK, BEEP, FOCUS,
button KEYs, MENU/ITEM (KEY, TICK) and TIMER. Behaviour tests build with
Pasmo and run on the project simulator under the memory checker; Rosanne
behaviours the XAnne probe settles (who clears a radio group, whether a
tickable menu entry toggles itself) are run both ways. None of this is
XAnne evidence.
"""
from __future__ import annotations

import unittest

import z80sim
from memguard import guarded_run, string_var
from pbas import SourceError, check_source, generate
from pbas.layout import (
    BIND_NUMBER,
    BIND_RADIO,
    LARGE_BUTTON_ROWS,
    LARGE_RECT,
    NUMBER_LEGAL,
    build_dialog,
)
from toolchain import requires_pasmo

RADIO_ERR = "Runtime error: option number out of range at line {}"
NUMBER_ERR = "Runtime error: number out of range at line {}"
GREEN, RED, STOP, F1 = 0xFB, 0xFC, 0xFE, 0xF1


def layouts(src: str) -> list:
    program = check_source(src)
    return [build_dialog(program, w, bool(program.menus)) for w in program.windows]


def numbers(src: str, window: int = 0) -> dict:
    """Object numbers: buttons by caption, bound controls by variable,
    spinners as '<var> spin', radios as '<var> <i>'."""
    lay = layouts(src)[window]
    result = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
    for row in lay.bindings:
        result[row.var_name] = row.number
        if row.kind == BIND_NUMBER and row.spinner:
            result[row.var_name + " spin"] = row.spinner
        if row.kind == BIND_RADIO:
            for i in range(row.capacity):
                result[f"{row.var_name} {i + 1}"] = row.number + 2 * i
    return result


def run(src: str, events, **options):
    result = guarded_run(src, events=events, **options)
    return result


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return caught.exception

    def test_new_words_are_not_reserved(self):
        # Older programs may use the new statement words as names.
        src = ('WINDOW "W"\nBUTTON "Go", Show\nDIM Timer AS INTEGER\nDIM Menu$ AS STRING\n'
               'SUB Show\nTimer = Timer + 1\nMenu$ = "x"\nCALL Item\nEND SUB\n'
               'SUB Item\nEND SUB\nEND\n')
        program = check_source(src)
        self.assertEqual(program.variables["TIMER"].type, "INTEGER")
        generate(program)

    def test_windows(self):
        self.assertIn("exactly one per program", self.reject(
            'WINDOW "A"\nBUTTON "x", H\nWINDOW "B"\nBUTTON "y", H\nSUB H\nEND SUB\nEND\n').message)
        self.assertIn("not both", self.reject(
            'WINDOW "A"\nBUTTON "x", H\nWINDOW B, "B"\nBUTTON "y", H\nSUB H\nEND SUB\nEND\n').message)
        self.assertIn("duplicate WINDOW", self.reject(
            'WINDOW A, "A"\nBUTTON "x", H\nWINDOW A, "B"\nBUTTON "y", H\nSUB H\nEND SUB\nEND\n').message)
        many = "".join(f'WINDOW W{i}, "W"\nBUTTON "x", H\n' for i in range(9))
        self.assertIn("at most", self.reject(many + "SUB H\nEND SUB\nEND\n").message.replace(
            "too many WINDOWs: the maximum is", "at most"))
        err = self.reject('LABEL "early"\nWINDOW A, "A"\nBUTTON "x", H\nSUB H\nEND SUB\nEND\n')
        self.assertEqual(err.line, 1)
        self.assertIn("must follow the WINDOW", err.message)
        # a legacy single window still collects controls declared before it
        check_source('LABEL "early"\nWINDOW "A"\nBUTTON "x", H\nSUB H\nEND SUB\nEND\n')
        err = self.reject('WINDOW A, "A"\nBUTTON "x", H\nSUB H\nSHOW B\nEND SUB\nEND\n')
        self.assertIn("SHOW B", err.message)
        err = self.reject('WINDOW "A"\nBUTTON "x", H\nSUB H\nSHOW A\nEND SUB\nEND\n')
        self.assertIn("named windows", err.message)
        # WINDOW with a variable title is still the literal-title error
        err = self.reject('DIM T$ AS STRING\nWINDOW T$\nBUTTON "x", H\nSUB H\nEND SUB\nEND\n')
        self.assertEqual(err.message, "WINDOW title must be a string literal")

    def test_radio_rules(self):
        base = 'WINDOW "W"\n{}\nBUTTON "x", H\nSUB H\nEND SUB\nEND\n'
        self.assertIn("2 to 6 options", self.reject(base.format('RADIO R, "a"')).message)
        self.assertIn("2 to 6 options", self.reject(
            base.format('RADIO R, "a", "b", "c", "d", "e", "f", "g"')).message)
        self.assertIn("$ suffix", self.reject(base.format('RADIO R$, "a", "b"')).message)
        self.assertIn("caption must be a string literal", self.reject(
            base.format('DIM C$ AS STRING\nRADIO R, "a", C$')).message)
        program = check_source(base.format('RADIO R, "a", "b"'))
        self.assertEqual((program.variables["R"].type, program.variables["R"].origin), ("INTEGER", "RADIO"))

    def test_numberbox_rules(self):
        base = 'WINDOW "W"\n{}\nBUTTON "x", H\nSUB H\nEND SUB\nEND\n'
        self.assertIn("greater than MAX", self.reject(base.format("NUMBERBOX N, MIN 5, MAX 4")).message)
        self.assertIn("each at most once", self.reject(base.format("NUMBERBOX N, MIN 1, MIN 2")).message)
        self.assertIn("integer literal", self.reject(base.format("DIM K AS INTEGER\nNUMBERBOX N, MIN K")).message)
        program = check_source(base.format('NUMBERBOX N, "Count", MIN -5, MAX 5, SPIN'))
        widget = program.windows[0].widgets[0]
        self.assertEqual((widget.caption, widget.low, widget.high, widget.spin), ("Count", -5, 5, True))
        widget = check_source(base.format("NUMBERBOX N")).windows[0].widgets[0]
        self.assertEqual((widget.low, widget.high, widget.spin), (-32768, 32767, False))

    def test_ask_rules(self):
        base = 'DIM A AS INTEGER\nDIM S$ AS STRING\n{}\nEND\n'
        self.assertIn("whole right-hand side", self.reject(base.format('A = ASK("q", "y", "n") + 1')).message)
        self.assertIn("gives an INTEGER", self.reject(base.format('S$ = ASK("q", "y", "n")')).message)
        self.assertIn("got 2 arguments", self.reject(base.format('A = ASK("q", "y")')).message)
        self.assertIn("got 5 arguments", self.reject(base.format('A = ASK("q", "a", "b", "c", "d")')).message)
        self.assertIn("1 to 10", self.reject(base.format('A = ASK("q", "abcdefghijk", "n")')).message)
        self.assertIn("1 to 10", self.reject(base.format('A = ASK("q", S$, "n")')).message)
        self.assertIn("up to", self.reject(base.format('A = ASK(S$ + S$, "y", "n")')).message)
        generate(check_source(base.format('A = ASK("Size " + STR$(A) + "?", "Yes", "No", "Cancel")')))

    def test_menu_rules(self):
        base = 'WINDOW "W"\nBUTTON "x", H\n{}\nSUB H\nEND SUB\nEND\n'
        self.assertIn("only allowed inside a MENU", self.reject(base.format('ITEM "a", H')).message)
        self.assertIn("only ITEM lines", self.reject(base.format('MENU "M"\nBEEP\nEND MENU')).message)
        self.assertIn("END MENU without", self.reject(base.format("END MENU")).message)
        self.assertIn("at least one ITEM", self.reject(base.format('MENU "M"\nEND MENU')).message)
        err = self.reject('WINDOW "W"\nBUTTON "x", H\nSUB H\nEND SUB\nMENU "M"\nITEM "a", H\nEND\n')
        self.assertEqual((err.line, err.message), (7, "only ITEM lines may appear inside a MENU block"))
        self.assertIn("maximum is 12", self.reject(base.format('MENU "Thirteen char"\nITEM "a", H\nEND MENU')).message)
        self.assertIn("without |", self.reject(base.format('MENU "M"\nITEM "a|b", H\nEND MENU')).message)
        self.assertIn("divider", self.reject(base.format('MENU "M"\nITEM "-", H\nEND MENU')).message)
        self.assertIn("needs a handler", self.reject(base.format('MENU "M"\nITEM "a"\nEND MENU')).message)
        self.assertIn("already used", self.reject(
            base.format('MENU "M"\nITEM "a", H, KEY "x"\nITEM "b", H, KEY "X"\nEND MENU')).message)
        self.assertIn("one letter or digit", self.reject(base.format('MENU "M"\nITEM "a", H, KEY "xy"\nEND MENU')).message)
        self.assertIn("BOOLEAN", self.reject(
            base.format('DIM N AS INTEGER\nMENU "M"\nITEM "a", H, TICK N\nEND MENU')).message)
        self.assertIn("not defined by SUB", self.reject(base.format('MENU "M"\nITEM "a", Nope\nEND MENU')).message)
        many = "".join(f'MENU "M{i}"\nITEM "a", H\nEND MENU\n' for i in range(9))
        self.assertIn("too many MENUs", self.reject(base.format(many)).message)
        items = "".join(f'ITEM "i{i}", H\n' for i in range(21))
        self.assertIn("at most 20", self.reject(base.format(f'MENU "M"\n{items}END MENU')).message)
        err = self.reject('MENU "M"\nITEM "a", H\nEND MENU\nSUB H\nEND SUB\nEND\n')
        self.assertIn("requires a WINDOW", err.message)
        program = check_source(base.format('MENU "M"\nITEM "a", H, TICK Flag\nEND MENU'))
        self.assertEqual(program.variables["FLAG"].type, "BOOLEAN")

    def test_timer_and_focus_rules(self):
        base = 'WINDOW "W"\nTEXTBOX T$\nBUTTON "x", H\n{}\nSUB H\nEND SUB\nEND\n'
        self.assertIn("1..3599", self.reject(base.format("TIMER H, EVERY 0")).message)
        self.assertIn("1..3599", self.reject(base.format("TIMER H, EVERY 3600")).message)
        self.assertIn("only one TIMER", self.reject(base.format("TIMER H, EVERY 1\nTIMER H, EVERY 2")).message)
        self.assertIn("timer handler", self.reject(base.format("TIMER Nope, EVERY 1")).message)
        err = self.reject('WINDOW "W"\nBUTTON "x", H\nSUB H\nTIMER OFF\nEND SUB\nEND\n')
        self.assertIn("needs a TIMER", err.message)
        err = self.reject('DIM K AS INTEGER\nWINDOW "W"\nBUTTON "x", H\nSUB H\nFOCUS K\nEND SUB\nEND\n')
        self.assertIn("exactly one window", err.message)
        two = ('WINDOW A, "A"\nTEXTBOX T$\nBUTTON "x", H\nWINDOW B, "B"\nTEXTBOX T$\nBUTTON "y", H\n'
               'SUB H\nFOCUS T$\nEND SUB\nEND\n')
        self.assertIn("exactly one window", self.reject(two).message)
        generate(check_source(base.format("TIMER H, EVERY 3599")))

    def test_button_keys(self):
        base = 'WINDOW "W"\n{}\nSUB H\nEND SUB\nEND\n'
        self.assertIn("unknown key", self.reject(base.format('BUTTON "a", H, KEY PURPLE')).message)
        self.assertIn("already belongs", self.reject(
            base.format('BUTTON "a", H, KEY GREEN\nBUTTON "b", H, KEY GREEN')).message)
        self.assertIn("at most 3", self.reject(
            base.format('BUTTON "a", H, KEY F1, KEY F2, KEY F3, KEY F4')).message)
        lay = layouts(base.format('BUTTON "a", H, DEFAULT, KEY GREEN, KEY F1\nBUTTON "b", H, KEY STOP'))[0]
        buttons = [o for o in lay.objects if o.kind == "BUTTON"]
        self.assertEqual(buttons[0].definition[9:17], bytes((0x0D, 0x80, GREEN, 0x80, F1, 0x80, 0, 0)))
        self.assertEqual(buttons[1].definition[9:17], bytes((STOP, 0x80, 0, 0, 0, 0, 0, 0)))
        # the same key may be used again in another window
        check_source('WINDOW A, "A"\nBUTTON "a", H, KEY RED\nWINDOW B, "B"\nBUTTON "b", H, KEY RED\n'
                     'SUB H\nEND SUB\nEND\n')


class LayoutTests(unittest.TestCase):
    def test_radio_records(self):
        src = ('WINDOW "W"\nRADIO R, "a", "b", "c"\nRADIO S, "x", "y"\nBUTTON "x", H\n'
               'SUB H\nEND SUB\nEND\n')
        lay = layouts(src)[0]
        rows = [r for r in lay.bindings if r.kind == BIND_RADIO]
        self.assertEqual([(r.var_name, r.capacity) for r in rows], [("R", 3), ("S", 2)])
        by = {o.number: o for o in lay.objects}
        for group, row in enumerate(rows):
            for i in range(row.capacity):
                radio = by[row.number + 2 * i]
                self.assertEqual(radio.definition[0], 7)  # ob_radio
                self.assertEqual(len(radio.definition), 11)
                self.assertEqual(radio.definition[10], group)  # radio (group) number
                self.assertEqual(by[radio.number - 1].definition[9], radio.number)  # caption linked
        ys = [int.from_bytes(by[rows[0].number + 2 * i].definition[3:5], "little") for i in range(3)]
        self.assertEqual([b - a for a, b in zip(ys, ys[1:])], [24, 24])

    def test_number_field_records(self):
        src = 'WINDOW "W"\nNUMBERBOX N, "Count", SPIN\nNUMBERBOX M\nBUTTON "x", H\nSUB H\nEND SUB\nEND\n'
        lay = layouts(src)[0]
        by = {o.number: o for o in lay.objects}
        n, m = [r for r in lay.bindings if r.kind == BIND_NUMBER]
        edit = by[n.number].definition
        self.assertEqual(edit[0], 8)
        self.assertEqual(int.from_bytes(edit[9 + 28 : 9 + 30], "little"), 6)  # max length
        self.assertEqual(edit[9 + 24], len(NUMBER_LEGAL))
        self.assertEqual(edit[41:], b"      \0")
        self.assertEqual(by[n.number - 1].kind, "FIELDBOX")
        self.assertEqual(by[n.spinner].definition[:1] + by[n.spinner].definition[5:9],
                         bytes((13,)) + (17).to_bytes(2, "little") + (33).to_bytes(2, "little"))
        self.assertEqual((n.spinner, m.spinner), (n.number + 1, 0))

    def test_large_window_and_menus_flag(self):
        src = 'WINDOW "W", LARGE\nBUTTON "a", H\nBUTTON "b", H\nBUTTON "c", H\nBUTTON "d", H\nSUB H\nEND SUB\nEND\n'
        lay = layouts(src)[0]
        self.assertEqual(lay.definition[:4], bytes((1, 0, 1, 0)))
        self.assertEqual(tuple(int.from_bytes(lay.definition[5 + 2 * i : 7 + 2 * i], "little") for i in range(4)),
                         LARGE_RECT)
        ys = sorted({int.from_bytes(o.definition[3:5], "little") for o in lay.objects if o.kind == "BUTTON"})
        self.assertEqual(tuple(ys), LARGE_BUTTON_ROWS)
        first = next(o for o in lay.objects if o.kind == "BUTTON")
        self.assertEqual(int.from_bytes(first.definition[1:3], "little"), (600 - 316) // 2)
        with_menu = src.replace("SUB H", 'MENU "M"\nITEM "i", H\nEND MENU\nSUB H')
        self.assertEqual(layouts(with_menu)[0].definition[3], 1)  # ddm_enable

    def test_large_window_holds_more_rows(self):
        rows = "".join(f'CHECKBOX C{i}, "row {i}"\n' for i in range(8))
        src = f'WINDOW "W"{{}}\n{rows}BUTTON "x", H\nSUB H\nEND SUB\nEND\n'
        with self.assertRaises(SourceError):
            generate(check_source(src.format("")))
        generate(check_source(src.format(", LARGE")))


@requires_pasmo
class RadioTests(unittest.TestCase):
    SRC = ('DIM Seen AS INTEGER\nWINDOW "W"\nRADIO Size, "Small", "Medium", "Large"\n'
           'BUTTON "Read", Read\nBUTTON "Set", SetIt\nBUTTON "Bad", Bad\n'
           'SUB Read\nSeen = Size\nEND SUB\nSUB SetIt\nSize = 3\nEND SUB\n'
           'SUB Bad\nSize = 4\nEND SUB\nSize = 2\nEND\n')

    def test_selection_and_reading(self):
        n = numbers(self.SRC)
        for mode in ("set", "exclusive"):
            with self.subTest(radio_mode=mode):
                r = run(self.SRC, [("radio", n["SIZE 1"]), ("click", n["Read"])], radio_mode=mode)
                self.assertEqual(r.violations, [])
                self.assertEqual([r.cpu.control_checked(n[f"SIZE {i}"], shown=True) for i in (1, 2, 3)],
                                 [True, False, False])
                seen = r.cpu.mem[r.symbols["var_seen"]]
                self.assertEqual(seen, 1)

    def test_initial_value_and_handler_change(self):
        n = numbers(self.SRC)
        r = run(self.SRC, [("click", n["Set"])])
        self.assertEqual([r.cpu.control_checked(n[f"SIZE {i}"], shown=True) for i in (1, 2, 3)],
                         [False, False, True])
        r = run(self.SRC, [])
        self.assertEqual([r.cpu.control_checked(n[f"SIZE {i}"]) for i in (1, 2, 3)], [False, True, False])

    def test_caption_click_selects_its_option(self):
        n = numbers(self.SRC)
        r = run(self.SRC, [("objevent", n["SIZE 3"] - 1, 1), ("click", n["Read"])])
        self.assertEqual(r.cpu.mem[r.symbols["var_seen"]], 3)

    def test_out_of_range(self):
        n = numbers(self.SRC)
        r = run(self.SRC, [("click", n["Bad"])])
        self.assertEqual(r.alerts, [RADIO_ERR.format(3)])
        self.assertTrue(r.cpu.exited)


@requires_pasmo
class NumberTests(unittest.TestCase):
    SRC = ('DIM Seen AS INTEGER\nDIM Runs AS INTEGER\nWINDOW "W"\n'
           'NUMBERBOX Qty, "Qty", MIN -3, MAX 5, SPIN\n'
           'BUTTON "Read", Read\nBUTTON "Big", Big\nBUTTON "Same", Same\nTIMER Tock, EVERY 1\n'
           'SUB Read\nSeen = Qty\nRuns = Runs + 1\nEND SUB\nSUB Big\nQty = 6\nEND SUB\n'
           'SUB Same\nQty = Qty\nEND SUB\nSUB Tock\nRuns = Runs + 1\nEND SUB\nQty = 2\nEND\n')

    def word(self, r, name):
        at = r.symbols[f"var_{name}"]
        value = r.cpu.mem[at] | (r.cpu.mem[at + 1] << 8)
        return value - 0x10000 if value & 0x8000 else value

    def test_valid_entry(self):
        n = numbers(self.SRC)
        r = run(self.SRC, [("edit", n["QTY"], "-3"), ("click", n["Read"])])
        self.assertEqual(r.violations, [])
        self.assertEqual((self.word(r, "seen"), self.word(r, "runs")), (-3, 1))
        self.assertEqual(r.cpu.control_text(n["QTY"], shown=True), "-3")

    def test_invalid_entry_stops_the_handler(self):
        n = numbers(self.SRC)
        for text in ("", "-", "6", "-4", "12-3", "99999", "--1"):
            with self.subTest(text=text):
                r = run(self.SRC, [("edit", n["QTY"], text), ("click", n["Read"])])
                self.assertEqual(r.violations, [])
                self.assertEqual(r.alerts, ["Qty: enter a whole number from -3 to 5"])
                self.assertEqual(self.word(r, "runs"), 0)
                self.assertIn((73, n["QTY"]), r.cpu.os_log)
                self.assertEqual(r.cpu.control_text(n["QTY"], shown=True), "2")  # put back

    def test_after_an_invalid_entry_the_next_action_works(self):
        n = numbers(self.SRC)
        r = run(self.SRC, [("edit", n["QTY"], "9"), ("click", n["Read"]), ("click", n["Read"])])
        self.assertEqual(r.alerts, ["Qty: enter a whole number from -3 to 5"])
        self.assertEqual((self.word(r, "seen"), self.word(r, "runs")), (2, 1))

    def test_timer_leaves_an_invalid_field_alone(self):
        n = numbers(self.SRC)
        r = run(self.SRC, [("edit", n["QTY"], "-"), ("timer", 0)])
        self.assertEqual(r.alerts, [])
        self.assertEqual((self.word(r, "qty"), self.word(r, "runs")), (2, 1))
        self.assertEqual(r.cpu.control_text(n["QTY"], shown=True), "-")  # not overwritten

    def test_program_value_out_of_range(self):
        n = numbers(self.SRC)
        r = run(self.SRC, [("click", n["Big"])])
        self.assertEqual(r.alerts, [NUMBER_ERR.format(4)])

    def test_unchanged_value_is_not_redrawn(self):
        n = numbers(self.SRC)
        r = run(self.SRC, [("edit", n["QTY"], "004"), ("click", n["Same"])])
        defines = [d for f, d in r.cpu.os_log if f == 69 and d[0] == n["QTY"]]
        self.assertEqual(len(defines), 1)  # only at window opening
        self.assertEqual(r.cpu.control_text(n["QTY"], shown=True), "004")

    def test_spinner(self):
        n = numbers(self.SRC)
        spin = n["QTY spin"]
        cases = [
            ([1], "3"), ([1, 1, 1, 1, 1], "5"), ([5] * 7, "-3"), ([5, 5, 1], "1"),
        ]
        for steps, shown in cases:
            with self.subTest(steps=steps):
                events = [("spin", spin, d) for d in steps] + [("click", n["Read"])]
                r = run(self.SRC, events)
                self.assertEqual(r.violations, [])
                self.assertEqual(r.cpu.control_text(n["QTY"], shown=True), shown)
                self.assertEqual(self.word(r, "seen"), int(shown))

    def test_spinner_ignores_other_events(self):
        # Phase 1 fix: B is defined only for click / double-click; another
        # event on the spinner with a leftover B of 1 or 5 must not step.
        n = numbers(self.SRC)
        spin = n["QTY spin"]
        for evtype in (3, 4, 12, 13):
            with self.subTest(evtype=evtype):
                r = run(self.SRC, [("spinev", spin, evtype, 1), ("spinev", spin, evtype, 1),
                                   ("click", n["Read"])])
                self.assertEqual(self.word(r, "seen"), 2)
        r = run(self.SRC, [("spinev", spin, 2, 1), ("click", n["Read"])])  # double-click steps
        self.assertEqual(self.word(r, "seen"), 3)

    def test_spinner_backlog_is_flushed(self):
        # Phase 1 fix: events queued while a step redraws the field are
        # dropped (os_flush_events), so one press is one step.
        n = numbers(self.SRC)
        spin = n["QTY spin"]
        r = run(self.SRC, [("spin", spin, 1)] + [("spin", spin, 1, "queued")] * 12
                + [("click", n["Read"])])
        self.assertEqual(r.violations, [])
        self.assertEqual(self.word(r, "seen"), 3)
        self.assertIn((5, None), r.cpu.os_log)

    def test_spinner_from_text(self):
        n = numbers(self.SRC)
        spin = n["QTY spin"]
        r = run(self.SRC, [("edit", n["QTY"], "-2"), ("spin", spin, 1)])
        self.assertEqual(r.cpu.control_text(n["QTY"], shown=True), "-1")
        r = run(self.SRC, [("edit", n["QTY"], "9"), ("spin", spin, 5)])  # above MAX
        self.assertEqual(r.cpu.control_text(n["QTY"], shown=True), "5")
        r = run(self.SRC, [("edit", n["QTY"], "-"), ("spin", spin, 1)])  # from the shown value 2
        self.assertEqual(r.cpu.control_text(n["QTY"], shown=True), "3")

    def test_legal_characters_reach_the_os(self):
        n = numbers(self.SRC)
        r = run(self.SRC, [("edit", n["QTY"], "a1b"), ("click", n["Read"])])
        self.assertEqual(self.word(r, "seen"), 1)  # the model drops what the list refuses
        record = [d for f, d in r.cpu.os_log if f == 69 and d[0] == n["QTY"]][0][1]
        self.assertEqual(record[33], len(NUMBER_LEGAL))
        self.assertEqual(record[32], z80sim.FAKE_APP_BANK)


@requires_pasmo
class AskBeepTests(unittest.TestCase):
    SRC = ('DIM A AS INTEGER\nDIM N AS INTEGER\nN = 7\n'
           'A = ASK("Keep " + STR$(N) + "?", "Yes", "No", "Cancel")\n'
           'MESSAGE "Answer " + STR$(A)\nBEEP\nEND\n')

    def test_answers(self):
        for answer in (0, 1, 2):
            with self.subTest(answer=answer):
                r = run(self.SRC, [], alert_answers=[answer])
                self.assertEqual(r.violations, [])
                self.assertEqual(r.alerts, ["Keep 7?", f"Answer {answer + 1}"])
                self.assertEqual(r.cpu.alert_buttons[0], ["Yes", "No", "Cancel"])
                self.assertEqual(r.cpu.beeps, 1)

    def test_button_keys(self):
        r = run(self.SRC, [])
        at = r.symbols["ask_1"]
        block = bytes(r.cpu.mem[at : at + 1 + 3 * 8 + 4 + 3 + 7])
        self.assertEqual(block[0], 3)
        self.assertEqual(block[1:9], bytes((0x0D, 0x80, GREEN, 0x80, 0, 0, 0, 0)))  # Yes: Return, Green
        self.assertEqual(block[13:21], bytes(8))  # No: no keys
        self.assertEqual(block[24:32], bytes((STOP, 0x80, RED, 0x80, 0, 0, 0, 0)))  # Cancel: Stop, Red

    def test_long_text_is_reported(self):
        src = ('DIM A AS INTEGER\nDIM S$ AS STRING\nS$ = "' + "x" * 60 + '"\n'
               'A = ASK(S$ + S$, "Y", "N")\nEND\n')
        with self.assertRaises(SourceError):  # budget 2 x 64 > 100 at compile time
            generate(check_source(src))
        src = ('DIM A AS INTEGER\nDIM S$ AS STRING\nS$ = "' + "x" * 60 + '"\n'
               'A = ASK(S$ + "' + "y" * 30 + '", "Y", "N")\nEND\n')
        r = run(src, [], string_capacity=64)
        self.assertEqual(r.violations, [])


@requires_pasmo
class MenuTests(unittest.TestCase):
    SRC = ('DIM Hits AS INTEGER\nWINDOW "W"\nBUTTON "x", H\n'
           'MENU "File"\nITEM "Count", Count, KEY "C"\nITEM "-"\nITEM "Sound", Toggle, TICK SoundOn\nEND MENU\n'
           'MENU "Help"\nITEM "About", About\nEND MENU\n'
           'SUB H\nEND SUB\nSUB Count\nHits = Hits + 1\nEND SUB\n'
           'SUB Toggle\nSoundOn = NOT SoundOn\nEND SUB\nSUB About\nMESSAGE "About"\nEND SUB\n'
           'SoundOn = TRUE\nEND\n')

    def test_menu_bar(self):
        r = run(self.SRC, [])
        self.assertEqual(r.violations, [])
        titles = [t for t, _ in r.cpu.menu]
        self.assertEqual(titles, ["Tasks", "File", "Help"])
        self.assertTrue(r.cpu.menu_shown)
        file_menu = r.cpu.menu[1][1]
        self.assertEqual([e[2] for e in file_menu], ["Count", "_", "Sound"])
        self.assertEqual(file_menu[0][1], ord("c") | (4 << 8))  # Ctrl+C
        self.assertEqual(file_menu[2][0], 0x86)  # tickable and ticked from SoundOn
        self.assertIn((18, (1, 1, 0x86)), r.cpu.os_log)  # entry 1: the divider is not numbered
        self.assertEqual(r.cpu.dialog["ddm_enable"], 1)

    def test_items_run_their_handlers(self):
        for autotick in (False, True):
            with self.subTest(menu_autotick=autotick):
                # Rosanne numbers items only, not dividers (UIPROBE P1): Sound is 1
                r = run(self.SRC, [("menu", 1, 0), ("menu", 1, 0), ("menu", 1, 1), ("menu", 2, 0)],
                        menu_autotick=autotick)
                self.assertEqual(r.violations, [])
                self.assertEqual(r.cpu.mem[r.symbols["var_hits"]], 2)
                self.assertEqual(r.cpu.menu_entry(1, 1)[0], 0x82)  # tick follows SoundOn = FALSE
                # ticks are set by entry number, also skipping the divider
                self.assertIn((18, (1, 1, 0x82)), r.cpu.os_log)
                self.assertEqual(r.alerts, ["About"])

    def test_tasks_menu_entries_are_left_alone(self):
        r = run(self.SRC, [("menu", 0, 0)])
        self.assertEqual(r.cpu.mem[r.symbols["var_hits"]], 0)

    def test_menus_too_large_at_run_time(self):
        saved = z80sim.MODEL_TASKS_MENU
        try:
            z80sim.MODEL_TASKS_MENU = bytes((0x80, 0, 0)) + b"Tasks|" + (bytes((0x80, 0, 0)) + b"x" * 40 + b"|") * 49 + b"\0"
            r = run(self.SRC, [])
        finally:
            z80sim.MODEL_TASKS_MENU = saved
        self.assertEqual(r.alerts, ["Runtime error: the menus are too large"])
        self.assertIsNone(r.cpu.menu)


@requires_pasmo
class TimerTests(unittest.TestCase):
    SRC = ('DIM Ticks AS INTEGER\nWINDOW "W"\nBUTTON "Off", Off\nBUTTON "On", OnAgain\n'
           'TIMER Tick, EVERY 2\nSUB Tick\nTicks = Ticks + 1\nEND SUB\n'
           'SUB Off\nTIMER OFF\nEND SUB\nSUB OnAgain\nTIMER ON\nEND SUB\nEND\n')

    def test_ticks_and_switching(self):
        n = numbers(self.SRC)
        r = run(self.SRC, [("timer", 0), ("timer", 0), ("click", n["Off"]), ("click", n["On"]),
                           ("timer", 0), ("exit",)])
        self.assertEqual(r.violations, [])
        self.assertEqual(r.cpu.mem[r.symbols["var_ticks"]], 3)
        sets = [d for f, d in r.cpu.os_log if f == 8]
        self.assertEqual(sets, [(0, 1, 32), (0, 1, 32)])
        self.assertEqual([d for f, d in r.cpu.os_log if f == 9], [0, 0])  # OFF, then at exit
        self.assertEqual(r.cpu.timers, {})

    def test_stale_tick_after_off_is_ignored(self):
        n = numbers(self.SRC)
        r = run(self.SRC, [("click", n["Off"]), ("timer", 0, "stale")])
        self.assertEqual(r.cpu.timers, {})
        self.assertEqual(r.cpu.mem[r.symbols["var_ticks"]], 0)


@requires_pasmo
class WindowTests(unittest.TestCase):
    SRC = ('WINDOW Main, "Main"\nTEXTBOX Name$, "Name"\nLABEL Info$\nBUTTON "Next", GoNext\n'
           'BUTTON "Stay", Stay\n'
           'WINDOW Second, "Second", LARGE\nTEXTBOX Name$, "Name again"\nNUMBERBOX Age\n'
           'BUTTON "Back", GoBack, DEFAULT\n'
           'SUB GoNext\nSHOW Second\nFOCUS Age\nEND SUB\nSUB Stay\nSHOW Main\nInfo$ = "stay"\nEND SUB\n'
           'SUB GoBack\nInfo$ = Name$ + STR$(Age)\nSHOW Main\nEND SUB\n{main}END\n')

    def test_switching(self):
        src = self.SRC.format(main="")
        a, b = numbers(src, 0), numbers(src, 1)
        r = run(src, [("edit", a["NAME$"], "Ada"), ("click", a["Next"]),
                      ("edit", b["AGE"], "41"), ("click", b["Back"])])
        self.assertEqual(r.violations, [])
        self.assertEqual(string_var(r, "INFO$"), "Ada41")
        calls = [(f, d) for f, d in r.cpu.os_log if f in (66, 67, 68, 73)]
        self.assertEqual([f for f, _ in calls], [66, 67, 73, 68, 66, 67, 73, 73, 68, 66, 67, 73])
        self.assertIn((73, b["AGE"]), calls)
        self.assertEqual(r.cpu.dialog["title"], "Main")
        self.assertEqual(r.cpu.label_text(a["INFO$"], shown=True), "Ada41")
        # the shared variable shows in the second window when it opens
        r = run(src, [("edit", a["NAME$"], "Bo"), ("click", a["Next"])])
        self.assertEqual(r.cpu.control_text(b["NAME$"]), "Bo")

    def test_show_of_the_open_window_does_nothing(self):
        src = self.SRC.format(main="")
        a = numbers(src, 0)
        r = run(src, [("click", a["Stay"])])
        self.assertEqual([f for f, _ in r.cpu.os_log if f in (66, 68)], [66])
        self.assertEqual(r.cpu.label_text(a["INFO$"], shown=True), "stay")

    def test_show_in_the_main_line_chooses_the_first_window(self):
        src = self.SRC.format(main="SHOW Second\n")
        r = run(src, [])
        self.assertEqual(r.cpu.dialog["title"], "Second")
        self.assertEqual(r.cpu.dialog["box"], LARGE_RECT)


@requires_pasmo
class ExampleTests(unittest.TestCase):
    """The Phase 1 examples, as their XAnne scripts use them."""

    ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent

    def source(self, rel):
        return (self.ROOT / rel).read_text(encoding="utf-8")

    def test_order_form(self):
        src = self.source("examples/order_form.pbas")
        n = numbers(src)
        spin = n["QTY spin"]
        r = run(src, [("edit", n["CUSTOMER$"], "Ada"), ("radio", n["SIZE 2"]), ("spin", spin, 1),
                      ("spin", spin, 1), ("click", n["GIFT"]), ("press", GREEN, 0),
                      ("edit", n["QTY"], "25"), ("press", 0x0D, 0), ("menu", 2, 0), ("menu", 1, 0),
                      ("press", RED, 0), ("menu", 1, 2)], alert_answers=[0, 0])  # Quit: after the divider
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["Order 1 for Ada is gift wrapped.",
                                    "Quantity (1 to 20): enter a whole number from 1 to 20",
                                    "Order 2 for Ada is gift wrapped.", "Clear the form?",
                                    "Orders taken: 2. Quit now?"])
        self.assertEqual(r.cpu.beeps, 1)
        self.assertTrue(r.cpu.exited)

    def test_order_form_checks_its_fields(self):
        src = self.source("examples/order_form.pbas")
        n = numbers(src)
        r = run(src, [("press", GREEN, 0)])
        self.assertEqual(string_var(r, "STATUS$"), "Type a customer name")
        self.assertIn((73, n["CUSTOMER$"]), r.cpu.os_log)  # FOCUS Customer$
        r = run(src, [("edit", n["CUSTOMER$"], "Bo"), ("press", GREEN, 0)])
        self.assertEqual(string_var(r, "STATUS$"), "Choose a size")

    def test_stopwatch(self):
        src = self.source("examples/stopwatch.pbas")
        r = run(src, [("press", GREEN, 0)] + [("timer", 0)] * 3 + [("press", F1, 0), ("press", RED, 0)])
        self.assertEqual(r.violations, [])
        self.assertEqual(string_var(r, "SHOWN$"), "Stopped at 0:03")
        self.assertEqual(string_var(r, "LAPTEXT$"), "Lap 1 at 0:03")
        r = run(src, [("menu", 1, 1), ("press", GREEN, 0)] + [("timer", 0)] * 61)
        self.assertEqual(string_var(r, "SHOWN$"), "Running 1:01")
        self.assertEqual(r.cpu.beeps, 1)

    def test_contact_card(self):
        src = self.source("examples/contact_card.pbas")
        m, e, o = (numbers(src, i) for i in range(3))
        r = run(src, [("click", m["Edit"]), ("edit", e["PERSON$"], "Ada Lovelace"),
                      ("edit", e["PHONE$"], "0123 456"), ("spin", e["AGE spin"], 5),
                      ("radio", e["KIND 3"]), ("press", GREEN, 0), ("menu", 1, 1),
                      ("click", o["SHOWAGE"]), ("click", o["Done"]), ("click", m["Edit"]),
                      ("edit", e["PERSON$"], "Changed"), ("press", RED, 0)])
        self.assertEqual(r.violations, [])
        self.assertEqual(r.cpu.dialog["title"], "Contact card")
        shown = [r.cpu.label_text(m[v], shown=True) for v in ("LINE1$", "LINE2$", "LINE3$")]
        self.assertEqual(shown, ["Ada Lovelace", "Tel 0123 456", "Work, age 29"])

    def test_edge_program(self):
        src = self.source("developer-tests/m6_edges.pbas")
        n = numbers(src)
        r = run(src, [("press", 0x0D, 0), ("edit", n["BIG"], "-32768"), ("press", 0x0D, 0),
                      ("edit", n["BIG"], "32768"), ("press", 0x0D, 0), ("press", 0xF8, 0),
                      ("press", 0xEC, 0), ("press", 0xF9, 0), ("press", 0x0D, 0),
                      ("click", n["Break"])], alert_answers=[1])
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["Any whole number: enter a whole number from -32768 to 32767",
                                    "Two buttons: which?", RADIO_ERR.format(7)])
        self.assertIn((73, n["FLAG"]), r.cpu.os_log)


class ByteIdentityTests(unittest.TestCase):
    def test_older_programs_select_no_phase1_part(self):
        src = 'WINDOW "W"\nLABEL "x"\nBUTTON "a", H, DEFAULT\nSUB H\nEND SUB\nEND\n'
        asm = generate(check_source(src))
        for name in ("RADIO", "NUMBERS", "SPIN", "MENUS", "TIMER", "WINDOWS", "FOCUS", "ASK", "BEEP", "POST"):
            self.assertIn(f"PB_{name} equ 0", asm)
        self.assertIn("PB_BINDINGS equ 0", asm)


if __name__ == "__main__":
    unittest.main()
