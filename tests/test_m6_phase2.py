"""M6 Phase 2 — arrays and data-rich interfaces (LANGUAGE-SPEC.md §5.2).

Behaviour tests build with Pasmo and run on the project simulator under the
memory checker; none of this is XAnne evidence.
"""
from __future__ import annotations

import unittest

from memguard import guarded_run, string_var
from pbas import SourceError, check_source, generate
from toolchain import requires_pasmo

INDEX_ERR = "Runtime error: index out of range at line {}"


class ArrayFrontendTests(unittest.TestCase):
    def reject(self, src: str) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return caught.exception

    def test_declarations(self):
        program = check_source("DIM A$(10) AS STRING\nDIM N(3) AS INTEGER\nDIM F(2) AS BOOLEAN\nEND\n")
        self.assertEqual([(v.type, v.length) for v in program.variables.values()],
                         [("STRING", 10), ("INTEGER", 3), ("BOOLEAN", 2)])
        self.assertIn("1 to 250", self.reject("DIM A(0) AS INTEGER\nEND\n").message)
        self.assertIn("1 to 250", self.reject("DIM A(251) AS INTEGER\nEND\n").message)
        self.assertIn("built-in", self.reject("DIM LEN(3) AS INTEGER\nEND\n").message)
        self.assertIn("$ suffix", self.reject("DIM A$(3) AS INTEGER\nEND\n").message)
        self.assertIn("is an array", self.reject("DIM A(3) AS INTEGER\nDIM A AS INTEGER\nEND\n").message)

    def test_uses(self):
        base = "DIM A(3) AS INTEGER\nDIM S$(3) AS STRING\nDIM X AS INTEGER\n{}\nEND\n"
        self.assertIn("use A(index)", self.reject(base.format("X = A")).message)
        self.assertIn("use A(index) = value", self.reject(base.format("A = 1")).message)
        self.assertIn("not an array", self.reject(base.format("X(1) = 2")).message)
        self.assertIn("must be INTEGER", self.reject(base.format('X = A("1")')).message)
        self.assertIn("must be INTEGER", self.reject(base.format('A(TRUE) = 1')).message)
        self.assertIn("cannot assign", self.reject(base.format('A(1) = "x"')).message)
        self.assertIn("plain INTEGER", self.reject(base.format('A(1) = ASK("q", "a", "b")')).message)
        self.assertIn("is an array", self.reject(base.format('WINDOW "W"\nTEXTBOX S$\nBUTTON "x", H\nSUB H\nEND SUB')).message)
        err = self.reject("DIM S$(2) AS STRING\nS$(1) = \"" + "x" * 70 + "\"\nEND\n")
        self.assertIn("capacity 64", err.message)
        generate(check_source(base.format('S$(A(1) + 1) = S$(1) + STR$(A(2))\nX = LEN(S$(3)) + A(1)')))


@requires_pasmo
class ArrayBehaviourTests(unittest.TestCase):
    SORT = '''DIM W$(6) AS STRING
DIM N(6) AS INTEGER
DIM I AS INTEGER
DIM J AS INTEGER
DIM T$ AS STRING
DIM K AS INTEGER
DIM Out$ AS STRING
W$(1) = "pear"
W$(2) = "apple"
W$(3) = "fig"
W$(4) = "kiwi"
W$(5) = "date"
W$(6) = "banana"
FOR I = 1 TO 5
FOR J = 1 TO 6 - I
IF W$(J) > W$(J + 1) THEN
T$ = W$(J)
W$(J) = W$(J + 1)
W$(J + 1) = T$
END IF
NEXT J
NEXT I
FOR I = 1 TO 6
N(I) = LEN(W$(I)) * 10 + I
Out$ = Out$ + LEFT$(W$(I), 2)
NEXT I
W$(2) = W$(2) + "!" + MID$(W$(3), 2, 2)
MESSAGE Out$ + " " + STR$(N(1) + N(6)) + " " + W$(2)
K = {k}
MESSAGE W$(K)
END
'''

    def test_sort_and_functions(self):
        r = guarded_run(self.SORT.format(k=6))
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["apbadafikipe 97 banana!at", "pear"])

    def test_bounds(self):
        for k in (0, 7, -1, -32768, 32767):
            with self.subTest(index=k):
                r = guarded_run(self.SORT.format(k=k))
                self.assertEqual(r.violations, [])
                self.assertEqual(r.alerts[-1], INDEX_ERR.format(30))
                self.assertTrue(r.cpu.exited)

    def test_writes_are_checked_before_anything_is_stored(self):
        src = ("DIM A(3) AS INTEGER\nDIM S$(2) AS STRING\nDIM I AS INTEGER\nA(3) = 7\nI = 4\n"
               "A(I) = 9\nEND\n")
        r = guarded_run(src)
        self.assertEqual(r.alerts, [INDEX_ERR.format(6)])
        self.assertEqual(r.violations, [])
        src = ('DIM S$(2) AS STRING\nDIM T$ AS STRING\nT$ = "' + "y" * 40 + '"\n'
               'S$(1) = T$ + T$\nEND\n')
        r = guarded_run(src)
        self.assertEqual(r.alerts, ["Runtime error: string too long at line 4"])
        self.assertEqual(r.violations, [])  # nothing written past the element
        self.assertEqual(string_var(r, "T$"), "y" * 40)

    def test_elements_are_independent(self):
        src = ('DIM S$(3) AS STRING\nDIM B(2) AS BOOLEAN\nS$(2) = "middle"\nS$(1) = S$(2) + "<"\n'
               'S$(3) = ">" + S$(2)\nB(2) = S$(1) = "middle<"\n'
               'IF B(2) AND NOT B(1) THEN\nMESSAGE S$(1) + S$(2) + S$(3)\nEND IF\nEND\n')
        r = guarded_run(src, string_capacity=16)
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["middle<middle>middle"])


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# LIST, CHOICE, SLIDER (LANGUAGE-SPEC §5.2): frontend, records, behaviour
# ---------------------------------------------------------------------------
from pbas.layout import (  # noqa: E402
    BIND_CHOICE,
    BIND_LIST,
    BIND_SLIDER,
    build_dialog,
)

LIST_COUNT_ERR = "Runtime error: list count out of range at line {}"
LIST_POS_ERR = "Runtime error: list position out of range at line {}"
LIST_CHAR_ERR = "Runtime error: list text has an unsupported character at line {}"
TOO_LONG_ERR = "Runtime error: string too long at line {}"
NUMBER_ERR = "Runtime error: number out of range at line {}"
CHOICE_NONE_ERR = "Runtime error: a CHOICE must show an item from 1 to its count at line {}"


def objects(src: str, window: int = 0) -> dict:
    """Object numbers: buttons by caption; LIST var -> list, '<var> bar' ->
    its scroll bar; CHOICE var -> drop button, '<var> label' -> readout;
    SLIDER var -> scroll bar; LABEL var -> label."""
    program = check_source(src)
    lay = build_dialog(program, program.windows[window], bool(program.menus))
    result = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
    for row in lay.bindings:
        result[row.var_name] = row.number
        if row.kind == BIND_LIST:
            result[row.var_name + " bar"] = row.spinner
        if row.kind == BIND_CHOICE:
            result[row.var_name + " label"] = row.spinner
    return result


def word(r, name):
    at = r.symbols[f"var_{name.lower()}"]
    return r.cpu.mem[at] | (r.cpu.mem[at + 1] << 8)


class ControlFrontendTests(unittest.TestCase):
    HEAD = 'DIM Items$(5) AS STRING\nDIM N AS INTEGER\nDIM Msg$ AS STRING\nWINDOW "W", LARGE\n'
    TAIL = '\nLABEL Msg$\nBUTTON "Go", Go\nSUB Go\nEND SUB\nSUB H\nEND SUB\nEND\n'

    def reject(self, body: str) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(self.HEAD + body + self.TAIL))
        return caught.exception

    def test_rules(self):
        self.assertIn("STRING array", self.reject("LIST P, N, 3").message)
        self.assertIn("STRING array", self.reject("LIST P, Msg$, 3").message)
        self.assertIn("count must be 0 to 5", self.reject("LIST P, Items$, 6").message)
        self.assertIn("INTEGER variable or literal", self.reject("LIST P, Items$, Msg$").message)
        self.assertIn("INTEGER variable or literal", self.reject("LIST P, Items$, N + 1").message)
        self.assertIn("ROWS must be 2 to 12", self.reject("LIST P, Items$, N, ROWS 13").message)
        self.assertIn("ROWS must be 2 to 12", self.reject("LIST P, Items$, N, ROWS 1").message)
        self.assertIn("not defined by SUB", self.reject("LIST P, Items$, N, CHANGE Nope").message)
        self.assertIn("not defined by SUB", self.reject("CHOICE C, Items$, N, CHANGE Nope").message)
        self.assertIn("expected CHANGE", self.reject("CHOICE C, Items$, N, ROWS 3").message)
        self.assertIn("MAX - MIN must be 1 to 250", self.reject("SLIDER V, MIN 0, MAX 251").message)
        self.assertIn("MAX - MIN must be 1 to 250", self.reject("SLIDER V, MIN 5, MAX 5").message)
        self.assertIn("each at most once", self.reject("LIST P, Items$, N, ACTION H, ACTION H").message)
        self.assertIn("room for this LIST", self.reject("LIST A, Items$, N, ROWS 12\nLIST B, Items$, N").message)
        low = ('DIM Big$(6) AS STRING\nWINDOW "W", LARGE\nLIST A, Big$, 1, ROWS 12\nLABEL "x"\n'
               'CHOICE C, Big$, {}\nBUTTON "Go", Go\nSUB Go\nEND SUB\nEND\n')
        generate(check_source(low.format(5).replace("Big$(6)", "Big$(5)")))  # 5 rows fit
        with self.assertRaises(SourceError) as caught:
            generate(check_source(low.format(6)))
        self.assertIn("would extend below the window", caught.exception.message)
        # LIST, CHOICE and SLIDER stay usable as names elsewhere
        check_source("DIM List AS INTEGER\nDIM Choice AS INTEGER\nDIM Slider AS INTEGER\nSlider = List + Choice\nEND\n")

    def test_records(self):
        src = (self.HEAD + "LIST P, Items$, N, ROWS 4, CHANGE H, ACTION H\nCHOICE C, Items$, 3, \"Pick\"\n"
               "SLIDER V, MIN -5, MAX 5, \"Level\", CHANGE H" + self.TAIL)
        program = check_source(src)
        lay = build_dialog(program, program.windows[0], False)
        by = {o.number: o for o in lay.objects}
        rows = {r.kind: r for r in lay.bindings}
        lst = by[rows[BIND_LIST].number].definition
        bar = by[rows[BIND_LIST].spinner].definition
        self.assertEqual((lst[0], len(lst), lst[9]), (9, 30, rows[BIND_LIST].spinner))
        self.assertEqual((lst[12], lst[22], lst[23]), (4, 7, 16))  # Nvis, font 7, 16 px rows
        self.assertEqual((bar[0], len(bar), bar[5], bar[9]), (11, 14, 17, rows[BIND_LIST].number))
        drop = by[rows[BIND_CHOICE].number].definition
        self.assertEqual((drop[0], len(drop), drop[5], drop[7]), (5, 27, 17, 17))
        self.assertEqual(drop[9], rows[BIND_CHOICE].spinner)
        self.assertEqual(by[drop[9]].kind, "CHOICELABEL")
        hs = by[rows[BIND_SLIDER].number].definition
        self.assertEqual((hs[0], len(hs), hs[7], hs[9]), (12, 14, 17, 0))
        asm = generate(program)
        for flag in ("LIST", "CHOICE", "SLIDER", "SCROLL", "CTL2", "CHANGE"):
            self.assertIn(f"PB_{flag} equ 1", asm)
        plain = generate(check_source('WINDOW "W"\nBUTTON "Go", Go\nSUB Go\nEND SUB\nEND\n'))
        for flag in ("LIST", "CHOICE", "SLIDER", "SCROLL", "CTL2", "CHANGE"):
            self.assertIn(f"PB_{flag} equ 0", plain)

    def test_slider_limit(self):
        def program(n):
            parts = []
            for w in range(3):
                parts.append(f'WINDOW W{w}, "W{w}", LARGE')
                parts += [f"SLIDER V{w}_{i}, MIN 0, MAX 9" for i in range(6) if w * 6 + i < n]
                parts.append(f'BUTTON "Go", Go')
            return "\n".join(parts) + "\nSUB Go\nEND SUB\nEND\n"
        generate(check_source(program(16)))
        with self.assertRaises(SourceError) as caught:
            generate(check_source(program(17)))
        self.assertIn("at most 16 SLIDERs", caught.exception.message)


@requires_pasmo
class ListBehaviourTests(unittest.TestCase):
    SRC = '''DIM Items$(8) AS STRING
DIM N AS INTEGER
DIM Msg$ AS STRING
DIM Calls AS INTEGER
WINDOW "Lists", LARGE
LIST Pick, Items$, N, ROWS 4{opts}
LABEL Msg$
BUTTON "Add", AddOne
BUTTON "Show", ShowIt
BUTTON "Set", SetIt
SUB Changed
    Calls = Calls + 1
    Msg$ = "change " + STR$(Pick)
END SUB
SUB Opened
    Msg$ = "open " + Items$(Pick)
END SUB
SUB AddOne
    N = N + 1
    Items$(N) = "Item " + STR$(N)
END SUB
SUB ShowIt
    Msg$ = "show " + STR$(Pick)
END SUB
SUB SetIt
    Pick = {setto}
END SUB
Items$(1) = "Apple"
Items$(2) = "Banana"
Items$(3) = "Cherry"
N = {n}
Pick = {pick}
END
'''

    def go(self, events, opts=", CHANGE Changed, ACTION Opened", n=3, pick=0, setto=8, **kw):
        src = self.SRC.format(opts=opts, n=n, pick=pick, setto=setto)
        o = objects(src)
        r = guarded_run(src, events=[e(o) if callable(e) else e for e in events], **kw)
        self.assertEqual(r.violations, [])
        return r, o

    def state(self, r, o):
        return r.cpu.list_state(o["PICK"], shown=True)

    def test_initial_display(self):
        r, o = self.go([])
        self.assertEqual(self.state(r, o), {"n": 3, "vis": 4, "first": 0, "sel": None,
                                            "items": ["Apple", "Banana", "Cherry"]})
        self.assertEqual(r.cpu.scroll_state(o["PICK bar"], shown=True), (0, 68 - 34))
        r, o = self.go([], pick=2)
        self.assertEqual(self.state(r, o)["sel"], 1)

    def test_pick_runs_change_and_binds(self):
        r, o = self.go([lambda o: ("pick", o["PICK"], 2)])
        self.assertEqual(string_var(r, "MSG$"), "change 3")
        r, o = self.go([lambda o: ("pick", o["PICK"], 0), lambda o: ("click", o["Show"])],
                       opts="")
        self.assertEqual(string_var(r, "MSG$"), "show 1")
        self.assertEqual(word(r, "Calls"), 0)

    def test_double_click_runs_action(self):
        r, o = self.go([lambda o: ("dpick", o["PICK"], 1)])
        self.assertEqual(string_var(r, "MSG$"), "open Banana")
        r, o = self.go([lambda o: ("dpick", o["PICK"], 1)], opts=", CHANGE Changed")
        self.assertEqual(string_var(r, "MSG$"), "change 2")

    def test_program_changes_items_and_selection(self):
        events = [lambda o: ("click", o["Add"])] * 5 + [lambda o: ("click", o["Set"])]
        r, o = self.go(events)
        s = self.state(r, o)
        self.assertEqual((s["n"], s["sel"], s["first"]), (8, 7, 4))  # moved to show it
        self.assertEqual(s["items"][3:], ["Item 4", "Item 5", "Item 6", "Item 7", "Item 8"])
        self.assertEqual(r.cpu.scroll_state(o["PICK bar"], shown=True), (17, 17))

    def test_scrolling(self):
        adds = [lambda o: ("click", o["Add"])] * 5  # 8 items, 4 shown: first 0..4

        def bar(b, de=0):
            return lambda o: ("scroll", o["PICK bar"], b, de)
        cases = [([bar(5)], 1), ([bar(5), bar(5), bar(1)], 1), ([bar(4)], 4), ([bar(4), bar(4)], 4),
                 ([bar(4), bar(2)], 0), ([bar(1)], 0), ([bar(3, 9)], 2), ([bar(3, 17)], 4),
                 ([bar(3, 300)], 4)]
        for extra, first in cases:
            with self.subTest(first=first, n=len(extra)):
                r, o = self.go(adds + extra)
                s = self.state(r, o)
                self.assertEqual((s["first"], s["sel"]), (first, None))
                self.assertEqual(r.cpu.scroll_state(o["PICK bar"], shown=True)[0], round(17 * first / 4))
                self.assertEqual(word(r, "Calls"), 0)  # scrolling is not a change

    def test_scroll_keeps_view_after_a_handler(self):
        r, o = self.go([lambda o: ("click", o["Add"])] * 5
                       + [lambda o: ("pick", o["PICK"], 0), lambda o: ("scroll", o["PICK bar"], 4),
                          lambda o: ("click", o["Show"])])
        s = self.state(r, o)
        self.assertEqual((s["first"], s["sel"]), (4, 0))  # selection unchanged: view kept
        self.assertEqual(string_var(r, "MSG$"), "show 1")

    def test_scroll_ignores_other_events_and_flushes(self):
        r, o = self.go([lambda o: ("click", o["Add"])] * 5
                       + [lambda o: ("scroll", o["PICK bar"], 5, 0, 12),
                          lambda o: ("scroll", o["PICK bar"], 5),
                          lambda o: ("scroll", o["PICK bar"], 5, 0, 1, "queued")])
        self.assertEqual(self.state(r, o)["first"], 1)

    def test_empty_list(self):
        r, o = self.go([lambda o: ("scroll", o["PICK bar"], 5)], n=0)
        self.assertEqual(self.state(r, o), {"n": 0, "vis": 4, "first": 0, "sel": None, "items": []})

    def test_runtime_errors(self):
        lines = self.SRC.splitlines()
        line = next(i for i, ln in enumerate(lines, 1) if ln.startswith("LIST"))
        r, o = self.go([], n=9)
        self.assertEqual(r.cpu.alerts, [LIST_COUNT_ERR.format(line)])
        r, o = self.go([], n=-1)
        self.assertEqual(r.cpu.alerts, [LIST_COUNT_ERR.format(line)])
        r, o = self.go([], pick=4)
        self.assertEqual(r.cpu.alerts, [LIST_POS_ERR.format(line)])
        r, o = self.go([], pick=-1)
        self.assertEqual(r.cpu.alerts, [LIST_POS_ERR.format(line)])
        r, o = self.go([lambda o: ("click", o["Set"])], setto=4)
        self.assertEqual(r.cpu.alerts, [LIST_POS_ERR.format(line)])
        self.assertTrue(r.cpu.exited)

    def test_item_text_rules(self):
        src = self.SRC.format(opts="", n=3, pick=0, setto=1)
        line = next(i for i, ln in enumerate(src.splitlines(), 1) if ln.startswith("LIST"))
        for text, alert in (("x" * 24, None), ("x" * 25, TOO_LONG_ERR), ('"Tab" + CHR$(9)', LIST_CHAR_ERR)):
            value = text if text.startswith('"') else f'"{text}"'
            s = src.replace('Items$(2) = "Banana"', f"Items$(2) = {value}")
            r = guarded_run(s, events=[])
            self.assertEqual(r.violations, [])
            self.assertEqual(r.cpu.alerts, [alert.format(line)] if alert else [])
        # an item beyond the count is never checked
        s = src.replace('Items$(5) = ', "").replace('N = 3', 'N = 3\nItems$(4) = "' + "y" * 30 + '"')
        self.assertEqual(guarded_run(s, events=[]).cpu.alerts, [])


@requires_pasmo
class ChoiceSliderBehaviourTests(unittest.TestCase):
    SRC = '''DIM Sizes$(5) AS STRING
DIM Msg$ AS STRING
DIM Calls AS INTEGER
WINDOW "Choices", LARGE
CHOICE Size, Sizes$, 4, "Size"{copts}
SLIDER Level, MIN {low}, MAX {high}, "Level"{sopts}
LABEL Msg$
BUTTON "Show", ShowIt
BUTTON "Set", SetIt
SUB Changed
    Calls = Calls + 1
    Msg$ = "size " + STR$(Size) + " level " + STR$(Level)
END SUB
SUB ShowIt
    Msg$ = "show " + STR$(Size) + " " + STR$(Level)
END SUB
SUB SetIt
    Size = {size2}
    Level = {level2}
    Sizes$(1) = "Tiny"
END SUB
Sizes$(1) = "Small"
Sizes$(2) = "Medium"
Sizes$(3) = "Large"
Sizes$(4) = "Huge"
Size = {size}
Level = {level}
END
'''

    def go(self, events, copts=", CHANGE Changed", sopts=", CHANGE Changed", low=0, high=20,
           size=1, level=10, size2=2, level2=3, **kw):
        src = self.SRC.format(copts=copts, sopts=sopts, low=low, high=high, size=size, level=level,
                              size2=size2, level2=level2)
        o = objects(src)
        r = guarded_run(src, events=[e(o) if callable(e) else e for e in events], **kw)
        self.assertEqual(r.violations, [])
        return r, o

    def test_choice(self):
        r, o = self.go([])
        self.assertEqual(r.cpu.list_state(o["SIZE"], shown=True),
                         {"n": 4, "vis": 4, "sel": 0, "items": ["Small", "Medium", "Large", "Huge"]})
        self.assertEqual(r.cpu.label_text(o["SIZE label"], shown=True), "Small")
        r, o = self.go([], size=3)
        self.assertEqual(r.cpu.label_text(o["SIZE label"], shown=True), "Large")
        for writes in (False, True):  # whoever writes the readout, it shows the choice
            r, o = self.go([lambda o: ("drop", o["SIZE"], 1)], drop_writes_label=writes)
            self.assertEqual(string_var(r, "MSG$"), "size 2 level 10")
            self.assertEqual(r.cpu.label_text(o["SIZE label"], shown=True), "Medium")
        r, o = self.go([lambda o: ("drop", o["SIZE"], 3), lambda o: ("click", o["Set"])])
        self.assertEqual(r.cpu.list_state(o["SIZE"], shown=True)["sel"], 1)
        self.assertEqual(r.cpu.label_text(o["SIZE label"], shown=True), "Medium")
        self.assertEqual(r.cpu.list_state(o["SIZE"])["items"][0], "Tiny")
        r, o = self.go([lambda o: ("drop", o["SIZE"], 0), lambda o: ("click", o["Show"])], copts="")
        self.assertEqual((string_var(r, "MSG$"), word(r, "Calls")), ("show 1 10", 0))
        line = next(i for i, ln in enumerate(self.SRC.splitlines(), 1) if ln.startswith("CHOICE"))
        r, o = self.go([], size=5)
        self.assertEqual(r.cpu.alerts, [LIST_POS_ERR.format(line)])

    def test_choice_never_shows_none(self):
        # Owner XAnne (UIPROBE3 F): current #FFFF ("none") froze XAnne when
        # the drop-down was opened. Sel = 0 stops the program first.
        line = next(i for i, ln in enumerate(self.SRC.splitlines(), 1) if ln.startswith("CHOICE"))
        for events, kw in (([], {"size": 0}), ([lambda o: ("click", o["Set"])], {"size2": 0})):
            with self.subTest(kw=kw):
                r, o = self.go(events, **kw)
                self.assertEqual(r.cpu.alerts, [CHOICE_NONE_ERR.format(line)])
                self.assertTrue(r.cpu.exited)
                drops = [d for fn, d in r.cpu.os_log if fn == 69 and d[0] == o["SIZE"]
                         and d[1][22:24] == b"\xff\xff"]
                self.assertEqual(drops, [])  # Rosanne was never given "none"
        src = self.SRC.format(copts="", sopts="", low=0, high=20, size=1, level=10, size2=2, level2=3)
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src.replace("CHOICE Size, Sizes$, 4", "CHOICE Size, Sizes$, 0")))
        self.assertIn("CHOICE count must be 1 to 5", caught.exception.message)
        r = guarded_run(src.replace("CHOICE Size, Sizes$, 4", "CHOICE Size, Sizes$, N")
                        .replace("DIM Msg$ AS STRING", "DIM Msg$ AS STRING\nDIM N AS INTEGER"), events=[])
        self.assertEqual(r.cpu.alerts, [CHOICE_NONE_ERR.format(line + 1)])  # N = 0: no item to show

    def test_slider(self):
        r, o = self.go([])
        self.assertEqual(r.cpu.scroll_state(o["LEVEL"], shown=True), (113, 20))

        def bar(b, de=0, *more):
            return lambda o: ("scroll", o["LEVEL"], b, de, *more)
        cases = [([bar(5)], 11), ([bar(1)], 9), ([bar(4)], 12), ([bar(2)], 8), ([bar(3, 0)], 0),
                 ([bar(3, 226)], 20), ([bar(3, 999)], 20), ([bar(3, 57)], 5), ([bar(3, 63)], 6), ([bar(4)] * 6, 20),
                 ([bar(2)] * 6, 0), ([bar(5, 0, 12)], 10), ([bar(5), bar(5, 0, 1, "queued")], 11)]
        for events, value in cases:
            with self.subTest(events=len(events), value=value):
                r, o = self.go(events)
                self.assertEqual(word(r, "Level"), value)
                self.assertEqual(r.cpu.scroll_state(o["LEVEL"], shown=True)[0], 226 * value // 20)
        r, o = self.go([bar(5), bar(5)])
        self.assertEqual((word(r, "Calls"), string_var(r, "MSG$")), (2, "size 1 level 12"))
        r, o = self.go([bar(1)], level=0)  # already at MIN: no change, no handler
        self.assertEqual(word(r, "Calls"), 0)
        r, o = self.go([lambda o: ("click", o["Show"])])  # unchanged: not redefined
        defines = [d for fn, d in r.cpu.os_log if fn == 69 and d[0] == o["LEVEL"]]
        self.assertEqual(len(defines), 1)
        r, o = self.go([lambda o: ("click", o["Set"])])
        self.assertEqual(r.cpu.scroll_state(o["LEVEL"], shown=True)[0], 226 * 3 // 20)
        r, o = self.go([bar(5)], low=-100, high=100, level=-100)
        self.assertEqual(word(r, "Level"), 0x10000 - 99)
        line = next(i for i, ln in enumerate(self.SRC.splitlines(), 1) if ln.startswith("SLIDER"))
        r, o = self.go([], level=21)
        self.assertEqual(r.cpu.alerts, [NUMBER_ERR.format(line)])
        r, o = self.go([lambda o: ("click", o["Set"])], level2=-1)
        self.assertEqual(r.cpu.alerts, [NUMBER_ERR.format(line)])


@requires_pasmo
class ChangeHandlerTests(unittest.TestCase):
    def test_change_does_not_refuse_an_unfinished_number(self):
        # A CHANGE handler runs like a timer handler: a number field holding
        # invalid text is left alone (no alert, the handler runs).
        src = ('DIM Items$(3) AS STRING\nDIM Msg$ AS STRING\nWINDOW "W", LARGE\n'
               'NUMBERBOX Qty, "Qty", MIN 1, MAX 9\nLIST Pick, Items$, 3, CHANGE Changed\n'
               'LABEL Msg$\nBUTTON "Go", Go\nSUB Changed\n    Msg$ = "picked " + STR$(Pick) + " " + STR$(Qty)\n'
               'END SUB\nSUB Go\nEND SUB\nItems$(1) = "a"\nItems$(2) = "b"\nItems$(3) = "c"\nQty = 4\nEND\n')
        o = objects(src)
        r = guarded_run(src, events=[("edit", o["QTY"], "x"), ("pick", o["PICK"], 2)])
        self.assertEqual(r.violations, [])
        self.assertEqual((r.cpu.alerts, string_var(r, "MSG$")), ([], "picked 3 4"))


@requires_pasmo
class ExampleProgramTests(unittest.TestCase):
    """The Phase 2 example programs as independent clients: scripted
    sessions under the memory checker (simulation, not XAnne)."""
    ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent

    def session(self, rel, events, window=0):
        src = (self.ROOT / rel).read_text(encoding="utf-8")
        o = [objects(src, 0), objects(src, window)][1 if window else 0]
        main = objects(src, 0)
        r = guarded_run(src, events=[e(main, o) if callable(e) else e for e in events])
        self.assertEqual(r.violations, [])
        return r, o

    def test_shopping_list(self):
        r, o = self.session("examples/shopping_list.pbas", [
            lambda m, o: ("edit", o["ENTRY$"], "Tea"), lambda m, o: ("click", o["Add"]),
            lambda m, o: ("dpick", o["PICK"], 1), lambda m, o: ("pick", o["PICK"], 0),
            lambda m, o: ("click", o["Remove"])])
        self.assertEqual(r.cpu.alerts, [])
        self.assertEqual(string_var(r, "STATUS$"), "3 items left")
        s = r.cpu.list_state(o["PICK"], shown=True)
        self.assertEqual((s["items"], s["sel"]), (["[x] Milk", "Apples", "Tea"], None))

    def test_tea_timer(self):
        r, o = self.session("examples/tea_timer.pbas", [
            lambda m, o: ("drop", o["TEA"], 0), lambda m, o: ("scroll", o["BREW"], 5),
            lambda m, o: ("click", o["Start"]), ("timer", 0), ("timer", 0)])
        self.assertEqual((r.cpu.alerts, string_var(r, "SHOWN$")), ([], "119 s to go"))
        self.assertEqual(r.cpu.label_text(o["TEA label"], shown=True), "Green")
        self.assertEqual(r.cpu.scroll_state(o["BREW"], shown=True)[0], 226 * (121 - 30) // 250)

    def test_phone_book(self):
        r, o = self.session("examples/phone_book.pbas", [
            lambda m, o: ("pick", o["WHO"], 2), lambda m, o: ("click", o["Sort"]),
            lambda m, o: ("edit", o["NAME$"], "Abel"), lambda m, o: ("edit", o["PHONE$"], "555"),
            lambda m, o: ("click", o["Add"]), lambda m, o: ("click", o["Sort"])])
        self.assertEqual((r.cpu.alerts, string_var(r, "SHOWN$")), ([], "Tel 555"))
        s = r.cpu.list_state(o["WHO"], shown=True)
        self.assertEqual((s["items"], s["sel"]), (["Abel", "Babbage", "Hopper", "Lovelace"], 0))

    def test_edges(self):
        rel = "developer-tests/m6p2_edges.pbas"
        r, o = self.session(rel, [
            lambda m, o: ("scroll", o["BIGPICK bar"], 4), lambda m, o: ("scroll", o["BIGPICK bar"], 3, 132),
            lambda m, o: ("dpick", o["BIGPICK"], 39), lambda m, o: ("click", o["None"]),
            lambda m, o: ("click", o["Last"])])
        s = r.cpu.list_state(o["BIGPICK"], shown=True)
        self.assertEqual((s["first"], s["sel"], r.cpu.scroll_state(o["BIGPICK bar"], shown=True)),
                         (28, 39, (114, 48)))
        events = [lambda m, o: ("click", m["More"]), lambda m, o: ("click", o["Fill"]),
                  lambda m, o: ("pick", o["FEWPICK"], 2), lambda m, o: ("drop", o["OPT"], 3),
                  lambda m, o: ("scroll", o["LEVEL"], 2), lambda m, o: ("click", o["Fewer"])]
        r, o = self.session(rel, events, window=1)
        self.assertEqual((r.cpu.alerts, string_var(r, "INFO2$")), ([], "Emptied"))
        self.assertEqual(r.cpu.list_state(o["FEWPICK"], shown=True)["n"], 0)
        self.assertEqual(r.cpu.label_text(o["OPT label"], shown=True), "One")
        r, o = self.session(rel, events[:1] + [lambda m, o: ("click", o["Bad text"])], window=1)
        self.assertEqual(r.cpu.alerts, [TOO_LONG_ERR.format(22)])
        r, o = self.session(rel, [lambda m, o: ("click", m["Bad pick"])])
        self.assertEqual(r.cpu.alerts, [LIST_POS_ERR.format(14)])
        r, o = self.session(rel, events[:1] + [lambda m, o: ("click", o["No choice"])], window=1)
        self.assertEqual(r.cpu.alerts, [CHOICE_NONE_ERR.format(23)])

    def test_edges_pass_asmcheck(self):
        # a 4 x 64-byte array is a labelled 'defs 256': not the container prefix (A2)
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(self.ROOT / "tools" / "build.py"),
                            str(self.ROOT / "developer-tests" / "m6p2_edges.pbas"), "--out-dir", tmp],
                           check=True, capture_output=True, cwd=self.ROOT)
            asm = Path(tmp) / "m6p2_edges.asm"
            self.assertIn("var_OPTS_S: defs 256", asm.read_text())
            check = subprocess.run([sys.executable, str(self.ROOT / "tools" / "asmcheck.py"), str(asm)],
                                   capture_output=True, text=True, cwd=self.ROOT)
            self.assertEqual(check.returncode, 0, check.stdout)


@requires_pasmo
class ListRepaintTests(unittest.TestCase):
    """M6 Phase 2 repair (owner XAnne, UIPROBE2 U6): a list redefined and
    updated after its frame box was repainted stayed blank. The simulator's
    H-LISTPAINT model (os_object_update incremental, os_object_display full)
    reproduces that; compiled lists must show their rows after every change."""
    ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent

    def test_probe_set_reproduces_the_blank_list(self):
        import subprocess
        import tempfile
        import z80sim
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            prg = Path(tmp) / "p.prg"
            subprocess.run(["pasmo", "--bin", str(self.ROOT / "developer-tests" / "uiprobe2.asm"), str(prg)],
                           check=True, capture_output=True)
            cpu = z80sim.run(prg, events=[("click", 12)])  # Set
        self.assertEqual(cpu.list_on_screen(3), (["", "", "", ""], None))

    def rows(self, events, n=3, pick=0):
        src = ListBehaviourTests.SRC.format(opts=", CHANGE Changed, ACTION Opened", n=n, pick=pick, setto=8)
        o = objects(src)
        r = guarded_run(src, events=[e(o) if callable(e) else e for e in events])
        self.assertEqual(r.violations, [])
        return r.cpu.list_on_screen(o["PICK"])

    def test_rows_after_handlers_scrolls_and_picks(self):
        self.assertEqual(self.rows([]), (["Apple", "Banana", "Cherry", ""], None))
        add = lambda o: ("click", o["Add"])  # noqa: E731
        self.assertEqual(self.rows([add]), (["Apple", "Banana", "Cherry", "Item 4"], None))
        self.assertEqual(self.rows([add] * 5 + [lambda o: ("click", o["Set"])]),
                         (["Item 5", "Item 6", "Item 7", "Item 8"], 3))
        self.assertEqual(self.rows([add] * 5 + [lambda o: ("scroll", o["PICK bar"], 5)]),
                         (["Banana", "Cherry", "Item 4", "Item 5"], None))
        self.assertEqual(self.rows([lambda o: ("pick", o["PICK"], 1)]),
                         (["Apple", "Banana", "Cherry", ""], 1))
        self.assertEqual(self.rows([lambda o: ("dpick", o["PICK"], 2)]),
                         (["Apple", "Banana", "Cherry", ""], 2))
