"""M3b tests: TEXTBOX / CHECKBOX controls and variable binding.

Layers: layout/rejection tests need no assembler; behaviour tests build with
Pasmo and run on tests/z80sim.py with scripted events under the memory
checker. The simulator keeps an OS-owned copy of the dialog with one fixed
slot per object (sized by the os_dialog_define definition), refuses an
os_object_define longer than the slot and an edit longer than the slot or
the declared max length (the v0.5.2 corruption class), applies checkbox
toggles and text edits only through os_process_event, changes what is
*shown* only at display / os_object_update, and poisons every register
ROSAN283 calls corrupt. It is an engineering aid: how Rosanne really edits,
focuses and redraws is an XAnne question (RUNTIME-RESULTS.md M3b scripts).
"""
from __future__ import annotations

import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import SourceError, check_source, generate
from pbas.layout import (
    BUTTON_Y,
    M3B_TEXTBOX_CAPACITY_MAX,
    TEXTEDIT_TEXT_OFFSET,
    build_dialog,
)
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parent.parent
FN_DEFINE_OBJ = z80sim.FN_OS_OBJECT_DEFINE
FN_UPDATE = z80sim.FN_OS_OBJECT_UPDATE
FN_DISPLAY = z80sim.FN_OS_DIALOG_DISPLAY


def numbers(source: str, capacity: int = 64) -> dict[str, int]:
    """Object numbers by bound variable name and by button caption."""
    layout = build_dialog(check_source(source, string_capacity=capacity))
    result = {row.var_name: row.number for row in layout.bindings}
    result.update({o.text: o.number for o in layout.objects if o.kind == "BUTTON"})
    return result


def decoded(source: str, capacity: int = 64) -> dict:
    layout = build_dialog(check_source(source, string_capacity=capacity))
    mem = bytearray(0x10000)
    mem[0x5000 : 0x5000 + len(layout.definition)] = layout.definition
    return z80sim.decode_dialog(mem, 0x5000)


FORM = (
    "DIM Who$ AS STRING\n"            # 1
    "DIM Where$ AS STRING\n"          # 2
    "DIM Opt AS BOOLEAN\n"            # 3
    "DIM Clicks AS INTEGER\n"         # 4
    'Where$ = "Leeds"\n'              # 5
    'WINDOW "Form"\n'                 # 6
    'TEXTBOX Who$, "Who"\n'           # 7
    "CHECKBOX Opt\n"                  # 8  (no caption)
    "TEXTBOX Where$\n"                # 9  (no caption)
    'BUTTON "Read", Read_Them\n'      # 10
    'BUTTON "Set", Set_Them\n'        # 11
    'BUTTON "Stop", Stop_It\n'        # 12
    "SUB Read_Them\n"
    "Clicks = Clicks + 1\n"
    'MESSAGE "[" + Who$ + "] [" + Where$ + "] " + STR$(Clicks)\n'
    "IF Opt THEN\n"
    'MESSAGE "opt on"\n'
    "ELSE\n"
    'MESSAGE "opt off"\n'
    "END IF\n"
    "END SUB\n"
    "SUB Set_Them\n"
    'Who$ = "set by code"\n'
    "Opt = TRUE\n"
    "END SUB\n"
    "SUB Stop_It\nEXIT\nEND SUB\n"
    "END\n"
)


# --------------------------------------------------------------------- layout
class ControlLayoutTests(unittest.TestCase):
    def test_records_decode_against_the_documented_formats(self):
        d = decoded(FORM)
        n = numbers(FORM)
        objs = {o["id"]: o for o in d["objects"]}
        who, where, opt = objs[n["WHO$"]], objs[n["WHERE$"]], objs[n["OPT"]]
        for field in (who, where):
            self.assertEqual(field["type"], z80sim.OB_TEXTEDIT)
            self.assertEqual(field["max_length"], 63)
            self.assertEqual(field["text"], " " * 63, "slot reserved with max-length spaces")
            self.assertEqual(field["length"], TEXTEDIT_TEXT_OFFSET + 64)
            self.assertEqual(field["font"], 7)
            self.assertEqual(field["rect"][2:], (292, 18))
            # M3b fix: the linked field box directly precedes every text
            # edit (NIKMACRO textentry64: box h25, params 8,0,1,0; edit
            # inset x+4, y+6, w-8, h18)
            box = objs[field["id"] - 1]
            self.assertEqual(box["type"], z80sim.OB_BOX)
            self.assertEqual((box["linked"], box["params"]), (field["id"], (8, 0, 1, 0)))
            bx, by, bw, bh = box["rect"]
            self.assertEqual(field["rect"], (bx + 4, by + 6, bw - 8, 18))
            self.assertEqual(bh, 25)
        self.assertEqual((opt["type"], opt["status"], opt["length"]), (z80sim.OB_CHECKBOX, 0, 10))
        # caption label, then field box, then TEXTBOX; no caption -> no label
        self.assertEqual(objs[n["WHO$"] - 2]["text"], "Who")
        self.assertEqual(objs[n["OPT"] - 1]["type"], z80sim.OB_TEXTEDIT)  # Who$ field

    def test_rows_stack_in_source_order(self):
        d = decoded(FORM)
        n = numbers(FORM)
        y = {o["id"]: o["rect"][1] for o in d["objects"]}
        self.assertLess(y[n["WHO$"]], y[n["OPT"]])
        self.assertLess(y[n["OPT"]], y[n["WHERE$"]])
        self.assertLessEqual(y[n["WHERE$"]] + 23, BUTTON_Y)

    def test_checkbox_caption_is_linked(self):
        src = 'WINDOW "C"\nCHECKBOX Flag, "Flag it"\nBUTTON "Go", Go\nSUB Go\nEND SUB\nEND\n'
        objs = decoded(src)["objects"]
        label, box = objs[1], objs[2]
        self.assertEqual((label["text"], label["linked"]), ("Flag it", box["id"]))
        self.assertEqual(box["type"], z80sim.OB_CHECKBOX)

    def test_capacity_boundaries(self):
        src = 'WINDOW "C"\nTEXTBOX T$\nBUTTON "Go", Go\nSUB Go\nEND SUB\nEND\n'
        field = decoded(src, capacity=2)["objects"][2]  # after BOX, field box
        self.assertEqual((field["max_length"], field["text"]), (1, " "))
        field = decoded(src, capacity=M3B_TEXTBOX_CAPACITY_MAX)["objects"][2]
        self.assertEqual(field["max_length"], M3B_TEXTBOX_CAPACITY_MAX - 1)
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src, string_capacity=M3B_TEXTBOX_CAPACITY_MAX + 1))
        self.assertEqual((caught.exception.line, caught.exception.column), (2, 1))
        self.assertIn("a TEXTBOX holds at most 63 characters", caught.exception.message)  # M14 (D12)
        self.assertIn("--string-capacity 64 or less", caught.exception.message)

    def test_mixed_controls_fit_and_overflow(self):
        fits = ('WINDOW "W"\nTEXTBOX A$\nTEXTBOX B$\nCHECKBOX C\n'
                'BUTTON "Go", Go\nSUB Go\nEND SUB\nEND\n')
        generate(check_source(fits))  # 48 + 48 + 28 = 124 px
        for extra, kind in (("TEXTBOX D$", "TEXTBOX"), ("CHECKBOX D, \"x\"", "CHECKBOX"), ('LABEL "x"', "LABEL")):
            src = fits.replace("CHECKBOX C\n", f"CHECKBOX C\n{extra}\n")
            with self.subTest(extra=extra), self.assertRaises(SourceError) as caught:
                generate(check_source(src))
            self.assertEqual(caught.exception.line, 5)
            self.assertIn(f"no room for this {kind}", caught.exception.message)

    def test_unsupported_and_invalid_bindings(self):
        cases = {
            # same variable bound twice (one control per variable)
            'WINDOW "W"\nCHECKBOX F\nCHECKBOX F\nBUTTON "Go", Go\nSUB Go\nEND SUB\nEND\n':
                (3, "already bound"),
            # frontend type rules still apply
            'DIM N AS INTEGER\nWINDOW "W"\nTEXTBOX N\nBUTTON "Go", Go\nSUB Go\nEND SUB\nEND\n':
                (3, "incompatible UI bindings"),
            'WINDOW "W"\nCHECKBOX F$\nBUTTON "Go", Go\nSUB Go\nEND SUB\nEND\n':
                (2, "$ suffix"),
            'WINDOW "W"\nTEXTBOX T$, "' + "c" * 35 + '"\nBUTTON "Go", Go\nSUB Go\nEND SUB\nEND\n':
                (2, "maximum is 34"),
            'WINDOW "W"\nBUTTON "Go", Go\nSUB Go\nTEXTBOX T$\nEND SUB\nEND\n':
                (4, "top level"),
        }
        for source, (line, needle) in cases.items():
            with self.subTest(needle=needle), self.assertRaises(SourceError) as caught:
                generate(check_source(source))
            self.assertEqual(caught.exception.line, line)
            self.assertIn(needle, caught.exception.message)

    def test_dim_plus_control_is_one_binding(self):
        src = 'DIM T$ AS STRING\nWINDOW "W"\nTEXTBOX T$\nBUTTON "Go", Go\nSUB Go\nEND SUB\nEND\n'
        self.assertEqual(len(build_dialog(check_source(src)).bindings), 1)


# ------------------------------------------------------------------ behaviour
@requires_pasmo
class BindingBehaviourTests(unittest.TestCase):
    maxDiff = None

    def run_form(self, events, source=FORM, capacity=64):
        run = guarded_run(source, string_capacity=capacity, events=events)
        self.assertEqual(run.violations, [], "memory-boundary violations")
        return run

    def defines_before_display(self, cpu):
        fns = [fn for fn, _ in cpu.os_log]
        return fns[: fns.index(FN_DISPLAY)].count(FN_DEFINE_OBJ)

    def test_initial_values_shown_without_padding(self):
        n = numbers(FORM)
        run = self.run_form([])
        cpu = run.cpu
        self.assertTrue(cpu.idle)
        # every control redefined from its variable before display, none redrawn
        self.assertEqual(self.defines_before_display(cpu), 3)
        self.assertEqual(cpu.control_text(n["WHERE$"], shown=True), "Leeds")
        self.assertEqual(cpu.control_text(n["WHO$"], shown=True), "")  # no spaces
        self.assertFalse(cpu.control_checked(n["OPT"], shown=True))
        self.assertNotIn(FN_UPDATE, [fn for fn, _ in cpu.os_log])

    def test_user_edits_reach_the_handler(self):
        n = numbers(FORM)
        run = self.run_form([
            ("edit", n["WHO$"], "Ada"),
            ("edit", n["WHERE$"], ""),           # cleared by the user
            ("click", n["OPT"]),                 # toggled on
            ("click", n["Read"]),
        ])
        self.assertEqual(run.alerts, ["[Ada] [] 1", "opt on"])
        self.assertEqual(string_var(run, "WHO$"), "Ada")
        self.assertEqual(string_var(run, "WHERE$"), "")

    def test_repeated_edits_and_clicks(self):
        n = numbers(FORM)
        run = self.run_form([
            ("edit", n["WHO$"], "one"), ("click", n["Read"]),
            ("edit", n["WHO$"], "two"), ("click", n["OPT"]), ("click", n["Read"]),
            ("click", n["OPT"]), ("click", n["Read"]),
            ("click", n["Read"]),
        ])
        self.assertEqual(
            run.alerts,
            ["[one] [Leeds] 1", "opt off", "[two] [Leeds] 2", "opt on",
             "[two] [Leeds] 3", "opt off", "[two] [Leeds] 4", "opt off"],
        )

    def test_checkbox_toggle_is_redrawn(self):
        n = numbers(FORM)
        cpu = self.run_form([("click", n["OPT"])]).cpu
        self.assertTrue(cpu.control_checked(n["OPT"]))
        self.assertTrue(cpu.control_checked(n["OPT"], shown=True), "toggle must be repainted")

    def test_handler_changes_update_only_changed_controls(self):
        n = numbers(FORM)
        cpu = self.run_form([("click", n["Set"]), ("click", n["Read"])]).cpu
        self.assertEqual(cpu.control_text(n["WHO$"], shown=True), "set by code")
        self.assertTrue(cpu.control_checked(n["OPT"], shown=True))
        self.assertEqual(cpu.control_text(n["WHERE$"], shown=True), "Leeds")
        redefined = [d[0] for fn, d in cpu.os_log if fn == FN_DEFINE_OBJ]
        # 3 at open; after Set: Who$ and Opt only; after Read: nothing changed
        self.assertEqual(redefined[3:], [n["WHO$"], n["OPT"]])
        self.assertEqual(cpu.alerts, ["[set by code] [Leeds] 1", "opt on"])

    def test_empty_and_maximum_length_text(self):
        n = numbers(FORM)
        longest = "x" * 63
        run = self.run_form([("edit", n["WHO$"], longest), ("click", n["Read"])])
        self.assertEqual(string_var(run, "WHO$"), longest)
        # a handler writing 63 characters back fits the reserved slot
        src = FORM.replace('Who$ = "set by code"', f'Who$ = "{"y" * 63}"')
        cpu = self.run_form([("click", n["Set"])], source=src).cpu
        self.assertEqual(cpu.control_text(n["WHO$"], shown=True), "y" * 63)

    def test_typing_past_max_length_is_refused_by_the_model(self):
        # The definition declares max length 63 in a 64-byte slot; the
        # model OS (like Rosanne's os_text_edit) refuses more. This pins the
        # definition, not the program: the program never sees 64 characters.
        n = numbers(FORM)
        run = guarded_run(FORM, events=[("edit", n["WHO$"], "z" * 64)])
        self.assertEqual(len(run.violations), 1)
        self.assertIn("exceeds max length 63", run.violations[0])

    def test_small_capacity_textbox(self):
        src = ('DIM K$ AS STRING\nWINDOW "Tiny"\nTEXTBOX K$\nBUTTON "Show", Show_K\n'
               'SUB Show_K\nMESSAGE "<" + K$ + ">"\nEND SUB\nEND\n')
        n = numbers(src, capacity=2)
        run = self.run_form([("click", n["Show"]), ("edit", n["K$"], "q"), ("click", n["Show"])],
                            source=src, capacity=2)
        self.assertEqual(run.alerts, ["<>", "<q>"])

    def test_unsaved_edits_on_exit(self):
        n = numbers(FORM)
        cpu = self.run_form([("edit", n["WHO$"], "lost"), ("exit",)]).cpu
        self.assertTrue(cpu.exited)
        fns = [fn for fn, _ in cpu.os_log]
        after_edit = fns[fns.index(z80sim.FN_OS_PROCESS_EVENT):]
        self.assertNotIn(z80sim.FN_OS_OBJECT_GET_DEFINE, after_edit, "no sync on om_exit")
        self.assertEqual(fns[-2:], [z80sim.FN_OS_DIALOG_REMOVE, z80sim.FN_OS_APP_EXIT])

    def test_keys_and_focus(self):
        n = numbers(FORM)
        cpu = self.run_form([("key", ord("A")), ("key", 13), ("click", n["Read"])]).cpu
        self.assertEqual(cpu.alerts, ["[] [Leeds] 1", "opt off"])  # keys changed nothing
        self.assertIn((z80sim.FN_OS_SET_FOCUS, n["Read"]), cpu.os_log)  # first button

    def test_runtime_error_in_handler_with_controls(self):
        # capacity 4: "Leeds" would not compile, so the main line uses "Lee";
        # line 23 is `Who$ = STR$(-32768)` inside Set_Them.
        src = FORM.replace('Who$ = "set by code"', 'Who$ = STR$(-32768)').replace('"Leeds"', '"Lee"')
        n = numbers(src, capacity=4)
        run = guarded_run(src, string_capacity=4, events=[("click", n["Set"])])
        self.assertEqual(run.violations, [])
        self.assertEqual(run.alerts, ["Runtime error: string too long at line 23"])
        self.assertTrue(run.cpu.exited)


# ---------------------------------------------------------- shipped examples
@requires_pasmo
class ExampleControlApplications(unittest.TestCase):
    """The three M3b examples under the sessions of the owner's XAnne
    procedure (RUNTIME-RESULTS.md, M3b scripts C1-C3)."""

    def session(self, name, script):
        source = (ROOT / "examples" / f"{name}.pbas").read_text(encoding="utf-8")
        n = numbers(source)
        run = guarded_run(source, events=script(n))
        self.assertEqual(run.violations, [])
        return run, n

    def test_details(self):
        run, n = self.session("details", lambda n: [
            ("click", n["Show"]),
            ("edit", n["FIRST$"], "Alan"),
            ("click", n["Show"]),
            ("edit", n["TOWN$"], "Shenfield"),
            ("click", n["Show"]),
            ("click", n["Clear"]),
            ("click", n["Show"]),
            ("click", n["Quit"]),
        ])
        self.assertEqual(run.alerts, [
            "Please type a first name",
            "Hello Alan from Brentwood", "Your name has 4 letters", "It starts with A",
            "Hello Alan from Shenfield", "Your name has 4 letters", "It starts with A",
            "Please type a first name",
        ])
        self.assertTrue(run.cpu.exited)

    def test_details_fields_cleared_on_screen(self):
        run, n = self.session("details", lambda n: [("edit", n["FIRST$"], "Alan"), ("click", n["Clear"])])
        self.assertEqual(run.cpu.control_text(n["FIRST$"], shown=True), "")
        self.assertEqual(run.cpu.control_text(n["TOWN$"], shown=True), "")

    def test_prefs(self):
        run, n = self.session("prefs", lambda n: [
            ("click", n["Summary"]),
            ("click", n["DARK"]), ("click", n["SOUND"]),
            ("click", n["Summary"]),
            ("click", n["All on"]),
            ("click", n["Summary"]),
            ("click", n["Quit"]),
        ])
        self.assertEqual(run.alerts, [
            "Sound on, dark screen off", "Auto save off: 1 of 3 chosen",
            "Sound off, dark screen on", "Auto save off: 1 of 3 chosen",
            "Sound on, dark screen on", "Auto save on: 3 of 3 chosen",
        ])

    def test_prefs_all_on_ticks_the_boxes(self):
        run, n = self.session("prefs", lambda n: [("click", n["All on"])])
        for var in ("SOUND", "DARK", "AUTOSAVE"):
            self.assertTrue(run.cpu.control_checked(n[var], shown=True), var)

    def test_editor(self):
        run, n = self.session("editor", lambda n: [
            ("click", n["Inspect"]),
            ("click", n["Keep 5"]),
            ("edit", n["LINE$"], "Amstrad PcW16"),
            ("click", n["FROMEND"]),
            ("click", n["Inspect"]),
            ("click", n["Keep 5"]),
            ("edit", n["LINE$"], ""),
            ("click", n["Inspect"]),
            ("click", n["Done"]),
        ])
        self.assertEqual(run.alerts, [
            "Text: PcW16 BASIC (11 letters)", "Keep 5 will keep the start",
            "Change 1: PcW16",
            "Text: Amstrad PcW16 (13 letters)", "Keep 5 will keep the end",
            "Change 2: PcW16",
            "The text is empty", "Keep 5 will keep the start",
        ])
        self.assertTrue(run.cpu.exited)

    def test_editor_keep_updates_text_and_clears_checkbox(self):
        run, n = self.session("editor", lambda n: [("click", n["FROMEND"]), ("click", n["Keep 5"])])
        self.assertEqual(run.cpu.control_text(n["LINE$"], shown=True), "BASIC")
        self.assertFalse(run.cpu.control_checked(n["FROMEND"], shown=True))



class SimulatorControlModelTests(unittest.TestCase):
    """The simulator's OS dialog copy must itself catch the v0.5.2 class,
    independently of the compiler's layout proof."""

    def cpu_with_dialog(self, text: bytes, max_len: int):
        from pbas.layout import textedit_params
        record = (bytes((z80sim.OB_TEXTEDIT,)) + bytes(8) + textedit_params(max_len) + text + b"\0")
        definition = bytes((1, 0, 1, 0, 16)) + bytes(8) + b"T\0" + record + b"\0"
        cpu = z80sim.CPU(bytes(0x200))
        cpu.mem[0x5000 : 0x5000 + len(definition)] = definition
        cpu.dialog = z80sim.decode_dialog(cpu.mem, 0x5000)
        cpu._copy_dialog(0x5000)
        return cpu, record

    def test_object_define_longer_than_slot_is_refused(self):
        cpu, record = self.cpu_with_dialog(b"ab", max_len=2)
        longer = record[:TEXTEDIT_TEXT_OFFSET] + b"abc\0"
        cpu.mem[0x6000 : 0x6000 + len(longer)] = longer
        cpu.e, cpu.c = 1, z80sim.FAKE_APP_BANK
        cpu.set_hl(0x6000)
        with self.assertRaisesRegex(z80sim.SimError, "longer than the existing"):
            cpu._object_define()

    def test_edit_longer_than_slot_is_refused(self):
        # max length claims 10 but only 3 bytes are reserved: the POC's
        # empty-field mistake, caught when the edit lands.
        cpu, _ = self.cpu_with_dialog(b"ab", max_len=10)
        cpu.pending_edit = (1, "abcdef")
        with self.assertRaisesRegex(z80sim.SimError, "overflows the 3-byte text slot"):
            cpu._apply_control_click(1)


# Independent client for the redraw regression (not an example and not the
# owner's EDITOR): two bound textboxes, each changed by a handler to a value
# that is a strict prefix of what was on screen, or empty, or longer.
REDRAW = (
    "DIM Title$ AS STRING\n"
    "DIM Note$ AS STRING\n"
    'Title$ = "Shopping for Saturday"\n'
    'Note$ = "eggs"\n'
    'WINDOW "Redraw"\n'
    'TEXTBOX Title$, "Title"\n'
    'LABEL "Each button rewrites a field"\n'
    "TEXTBOX Note$\n"
    'BUTTON "Shorten", Shorten\n'
    'BUTTON "Empty", Empty\n'
    'BUTTON "Grow", Grow\n'
    "SUB Shorten\n"
    "Title$ = LEFT$(Title$, 4)\n"
    "Note$ = LEFT$(Note$, 1)\n"
    "END SUB\n"
    "SUB Empty\n"
    'Title$ = ""\n'
    'Note$ = ""\n'
    "END SUB\n"
    "SUB Grow\n"
    'Note$ = "eggs, milk, bread"\n'
    "END SUB\n"
    "END\n"
)


@requires_pasmo
class TextboxRedrawRegressionTests(unittest.TestCase):
    """XAnne (owner, M3b): EDITOR "Keep 5" changed Line$ to "Amstr" but the
    textbox still showed "Amstrad PcW16". Root cause: no ob_box behind the
    text edit, so os_object_update drew the new glyphs over the old. These
    tests use the simulator's H-PAINT display model (tests/z80sim.py), which
    models that observation — they are not evidence of Rosanne behaviour."""

    def run_source(self, source, events):
        run = guarded_run(source, events=events)
        self.assertEqual(run.violations, [])
        return run

    def test_owner_editor_session(self):
        source = (ROOT / "examples" / "editor.pbas").read_text(encoding="utf-8")
        n = numbers(source)
        run = self.run_source(source, [
            ("edit", n["LINE$"], "Amstrad PcW16"),
            ("click", n["Keep 5"]),
            ("click", n["Inspect"]),
        ])
        self.assertEqual(run.alerts[:2], ["Change 1: Amstr", "Text: Amstr (5 letters)"])
        self.assertEqual(run.cpu.control_text(n["LINE$"]), "Amstr")
        self.assertEqual(run.cpu.control_text(n["LINE$"], shown=True), "Amstr")

    def test_every_bound_textbox_is_redrawn_cleanly(self):
        n = numbers(REDRAW)
        cases = [
            (["Shorten"], "Shop", "e"),
            (["Empty"], "", ""),
            (["Shorten", "Grow"], "Shop", "eggs, milk, bread"),
            (["Grow", "Shorten"], "Shop", "e"),
        ]
        for buttons, title, note in cases:
            with self.subTest(buttons=buttons):
                run = self.run_source(REDRAW, [("click", n[b]) for b in buttons])
                cpu = run.cpu
                self.assertEqual(cpu.control_text(n["TITLE$"], shown=True), title)
                self.assertEqual(cpu.control_text(n["NOTE$"], shown=True), note)

    def test_user_typed_text_is_replaced_on_screen(self):
        # the owner's sequence shape on an independent program: the user's
        # own longer text must not survive a shorter handler value
        n = numbers(REDRAW)
        run = self.run_source(REDRAW, [
            ("edit", n["NOTE$"], "potatoes and carrots"),
            ("click", n["Shorten"]),
        ])
        self.assertEqual(run.cpu.control_text(n["NOTE$"], shown=True), "p")

    def test_box_is_updated_between_define_and_field_update(self):
        n = numbers(REDRAW)
        run = self.run_source(REDRAW, [("click", n["Shorten"])])
        log = run.cpu.os_log
        display = [fn for fn, _ in log].index(FN_DISPLAY)
        after = [(fn, d if fn == FN_UPDATE else d[0]) for fn, d in log[display + 1:]
                 if fn in (FN_DEFINE_OBJ, FN_UPDATE)]
        for var in ("TITLE$", "NOTE$"):
            field = n[var]
            i = after.index((FN_DEFINE_OBJ, field))
            self.assertEqual(after[i + 1 : i + 3], [(FN_UPDATE, field - 1), (FN_UPDATE, field)], var)

    def test_unchanged_textbox_is_not_redrawn(self):
        n = numbers(REDRAW)
        run = self.run_source(REDRAW, [("click", n["Grow"])])  # Title$ untouched
        updates = [d for fn, d in run.cpu.os_log if fn == FN_UPDATE]
        self.assertNotIn(n["TITLE$"], updates)
        self.assertNotIn(n["TITLE$"] - 1, updates)

    def test_every_textbox_has_its_linked_field_box(self):
        for source in (FORM, REDRAW, (ROOT / "examples" / "details.pbas").read_text(encoding="utf-8")):
            layout = build_dialog(check_source(source))
            for obj in layout.objects:
                if obj.kind == "TEXTBOX":
                    box = layout.objects[obj.number - 2]
                    self.assertEqual((box.kind, box.definition[9]), ("FIELDBOX", obj.number))

    def test_unboxed_update_overlays_in_the_display_model(self):
        # The model must be able to show the fault at all: a bare text edit
        # updated to a shorter value keeps the old tail on screen.
        from pbas.layout import textedit_params
        def edit(text):
            return bytes((z80sim.OB_TEXTEDIT,)) + bytes(8) + textedit_params(20) + text
        record = edit(b" " * 20 + b"\0")
        definition = bytes((1, 0, 1, 0, 16)) + bytes(8) + b"T\0" + record + b"\0"
        cpu = z80sim.CPU(bytes(0x200))
        cpu.mem[0x5000 : 0x5000 + len(definition)] = definition
        cpu.dialog = z80sim.decode_dialog(cpu.mem, 0x5000)
        cpu._copy_dialog(0x5000)
        cpu.painted[1] = "Amstrad PcW16"
        short = edit(b"Amstr\0")
        cpu.mem[0x6000 : 0x6000 + len(short)] = short
        cpu.e, cpu.c = 1, z80sim.FAKE_APP_BANK
        cpu.set_hl(0x6000)
        cpu._object_define()
        cpu._paint_update(1)
        self.assertEqual(cpu.control_text(1), "Amstr")
        self.assertEqual(cpu.control_text(1, shown=True), "Amstrad PcW16")


if __name__ == "__main__":
    unittest.main()
