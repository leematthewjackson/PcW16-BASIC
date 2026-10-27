"""M3a GUI tests: WINDOW / LABEL / BUTTON, event dispatch, lifecycle.

Layers (TESTING-STRATEGY.md):
* layout and rejection tests are tiers 2-3 (no assembler);
* behaviour tests build with Pasmo and run on tests/z80sim.py with scripted
  events under tests/memguard.py's write checks. The simulator models the
  documented OS contract (ROSAN283 os_wait_event, os_process_event,
  os_dialog_define/display/remove, os_set_focus) and poisons every register
  the documentation calls corrupt. It is an engineering aid, never XAnne or
  hardware evidence: it cannot show how Rosanne draws the dialog or which
  events a real mouse produces.

All programs are written for this file (identifiers, titles and handler
names deliberately differ from the shipped examples), except the classes
that exercise the shipped examples and the POC parity programs.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run
from pbas import SourceError, check_source, generate
from pbas.layout import (
    BUTTON_TEXT_DOC_MAX,
    DIALOG_RECT,
    M3A_MAX_BUTTONS,
    MAX_LAYOUT_BUTTONS,
    M3A_MAX_LABELS,
    build_dialog,
)
from toolchain import requires_files, requires_pasmo

ROOT = Path(__file__).resolve().parent.parent

FN_ALERT, FN_EXIT = z80sim.FN_OS_ALERT, z80sim.FN_OS_APP_EXIT
FN_WAIT, FN_PROCESS = z80sim.FN_OS_WAIT_EVENT, z80sim.FN_OS_PROCESS_EVENT
FN_DEFINE, FN_DISPLAY = z80sim.FN_OS_DIALOG_DEFINE, z80sim.FN_OS_DIALOG_DISPLAY
FN_REMOVE, FN_FOCUS = z80sim.FN_OS_DIALOG_REMOVE, z80sim.FN_OS_SET_FOCUS


def program(n_labels: int, n_buttons: int, title: str = "Matrix") -> str:
    lines = [f'WINDOW "{title}"']
    lines += [f'LABEL "Row {i} text"' for i in range(n_labels)]
    lines += [f'BUTTON "B{i}", Act_{i}' for i in range(n_buttons)]
    for i in range(n_buttons):
        lines += [f"SUB Act_{i}", f'MESSAGE "act {i}"', "END SUB"]
    return "\n".join(lines) + "\nEND\n"


def decoded(source: str) -> tuple[dict, list]:
    """Build the layout and decode its bytes with the simulator's decoder."""
    layout = build_dialog(check_source(source))
    mem = bytearray(0x10000)
    mem[0x5000 : 0x5000 + len(layout.definition)] = layout.definition
    return z80sim.decode_dialog(mem, 0x5000), layout.handler_rows


# --------------------------------------------------------------------- layout
class DialogLayoutTests(unittest.TestCase):
    def test_definition_decodes_against_the_documented_format(self):
        dialog, rows = decoded(
            'WINDOW "Plant Log"\n'
            'BUTTON "Water", Water_It\n'  # buttons and labels interleaved
            'LABEL "Tap a button"\n'
            'BUTTON "Done", Finish\n'
            'LABEL "Second line"\n'
            "SUB Water_It\nEND SUB\nSUB Finish\nEXIT\nEND SUB\nEND\n"
        )
        self.assertEqual(dialog["title"], "Plant Log")
        self.assertEqual(
            (dialog["focus"], dialog["exit_by_click"], dialog["screen_store"], dialog["ddm_enable"]),
            (1, 0, 1, 0),
        )
        self.assertEqual((dialog["box_type"], dialog["box"]), (z80sim.DG_DIALOG_BOX, DIALOG_RECT))
        kinds = [(o["id"], o["type"], o.get("text")) for o in dialog["objects"]]
        self.assertEqual(
            kinds,
            [
                (1, z80sim.OB_BOX, None),
                (2, z80sim.OB_LABEL, "Tap a button"),
                (3, z80sim.OB_LABEL, "Second line"),
                (4, z80sim.OB_TEXTBUTTON, "Water"),
                (5, z80sim.OB_TEXTBUTTON, "Done"),
            ],
        )
        self.assertEqual(rows, [(4, "WATER_IT"), (5, "FINISH")])
        for button in dialog["objects"][3:]:
            self.assertEqual((button["keys"], button["repeat"]), ((0, 0, 0, 0), 0))

    def test_label_and_button_count_matrix(self):
        for n_labels in range(M3A_MAX_LABELS + 1):
            for n_buttons in range(1, M3A_MAX_BUTTONS + 1):
                with self.subTest(labels=n_labels, buttons=n_buttons):
                    dialog, rows = decoded(program(n_labels, n_buttons))
                    objects = dialog["objects"]
                    self.assertEqual(len(objects), 1 + n_labels + n_buttons)
                    self.assertEqual([o["id"] for o in objects], list(range(1, len(objects) + 1)))
                    first_button = 2 + n_labels
                    self.assertEqual([r[0] for r in rows], list(range(first_button, first_button + n_buttons)))
                    self.assertEqual([r[1] for r in rows], [f"ACT_{i}" for i in range(n_buttons)])
                    layout = build_dialog(check_source(program(n_labels, n_buttons)))
                    self.assertEqual(dialog["length"], len(layout.definition))
                    self.assertEqual(layout.focus_object, first_button)
                    for obj in objects:
                        x, y, w, h = obj["rect"]
                        self.assertLessEqual(x + w, DIALOG_RECT[2])
                        self.assertLessEqual(y + h, DIALOG_RECT[3])
                    xs = [o["rect"][0] for o in objects if o["type"] == z80sim.OB_TEXTBUTTON]
                    for left, right in zip(xs, xs[1:]):
                        self.assertGreaterEqual(right - left, 96, "buttons must not overlap")

    def test_one_handler_for_two_buttons(self):
        _, rows = decoded(
            'WINDOW "Shared"\nBUTTON "One", Same\nBUTTON "Two", Same\n'
            "SUB Same\nEND SUB\nEND\n"
        )
        self.assertEqual(rows, [(2, "SAME"), (3, "SAME")])

    def test_maximum_policy_texts_fit_documented_limits(self):
        title, label, caption = "T" * 35, "L" * 47, "C" * 14
        dialog, _ = decoded(
            f'WINDOW "{title}"\nLABEL "{label}"\nBUTTON "{caption}", Go\nSUB Go\nEND SUB\nEND\n'
        )
        self.assertEqual(dialog["title"], title)
        self.assertEqual(dialog["objects"][1]["text"], label)
        self.assertEqual(dialog["objects"][2]["text"], caption)
        self.assertLessEqual(len(caption), BUTTON_TEXT_DOC_MAX)


class GuiRejectionTests(unittest.TestCase):
    """Unsupported GUI combinations: positioned errors, never a .PRG."""

    def reject(self, source: str) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(source))
        return caught.exception

    def test_too_many_labels_points_at_the_first_extra(self):
        err = self.reject(program(M3A_MAX_LABELS + 1, 1))
        self.assertEqual((err.line, err.column), (2 + M3A_MAX_LABELS, 1))
        self.assertIn(f"at most {M3A_MAX_LABELS} LABELs", err.message)

    def test_too_many_buttons_points_at_the_first_extra(self):
        # M5d lifted the M3a cap of 3 to two rows of 3 (LANGUAGE-SPEC §5).
        err = self.reject(program(0, MAX_LAYOUT_BUTTONS + 1))
        self.assertEqual((err.line, err.column), (2 + MAX_LAYOUT_BUTTONS, 1))
        self.assertIn(f"at most {MAX_LAYOUT_BUTTONS} BUTTONs", err.message)

    def test_window_without_buttons(self):
        err = self.reject('DIM X AS INTEGER\nX = 1\nWINDOW "Bare"\nLABEL "x"\nEND\n')
        self.assertEqual((err.line, err.column), (3, 1))
        self.assertIn("a WINDOW needs at least one BUTTON", err.message)  # M14 (D13): no risk code
        self.assertIn("SUB Quit that runs EXIT", err.message)

    def test_one_control_per_variable(self):
        err = self.reject(
            'WINDOW "W"\nTEXTBOX Entry$\nBUTTON "Go", Go\nTEXTBOX Entry$\nSUB Go\nEND SUB\nEND\n'
        )
        self.assertEqual((err.line, err.column), (4, 1))
        self.assertIn("already bound to a control at line 2", err.message)

    def test_file_io_in_a_handler_compiles(self):
        # M4: file statements are ordinary statements in handlers too.
        asm = generate(check_source(
            'DIM S$ AS STRING\nWINDOW "W"\nBUTTON "Save", Keep\n'
            'SUB Keep\nFILESAVE "A.TXT", S$\nFILELOAD "A.TXT", S$\nEND SUB\nEND\n'
        ))
        self.assertIn("call rt_file_save", asm)
        self.assertIn("call rt_file_load", asm)

    def test_frontend_rules_still_apply(self):
        cases = {
            'WINDOW "W"\nBUTTON "Go", Missing\nEND\n': "not defined by SUB",
            'WINDOW "A"\nWINDOW "B"\nEND\n': "multiple WINDOW",
            'BUTTON "Go", Go\nSUB Go\nEND SUB\nEND\n': "requires a WINDOW",
            'WINDOW "W"\nSUB Go\nBUTTON "x", Go\nEND SUB\nEND\n': "top level",
            f'WINDOW "W"\nBUTTON "{"x" * 15}", Go\nSUB Go\nEND SUB\nEND\n': "maximum is 14",
        }
        for source, needle in cases.items():
            with self.subTest(needle=needle):
                with self.assertRaises(SourceError) as caught:
                    generate(check_source(source))
                self.assertIn(needle, caught.exception.message)


class GuiEmissionTests(unittest.TestCase):
    def test_program_ending_and_tables(self):
        asm = generate(check_source(program(1, 2, "Shape")))
        self.assertTrue(asm.startswith("PB_DIALOG equ 1\n"))
        self.assertIn("    ld hl,gui_dialog\n    ld de,gui_handlers\n    jp rt_gui_run", asm)
        self.assertNotIn("    jp rt_exit\n\nsub_", asm)
        self.assertIn("gui_handlers:\n    db 3,2\n    db 3\n    dw sub_ACT__0\n    db 4\n    dw sub_ACT__1", asm)
        self.assertNotIn("003B", asm)

    def test_non_gui_program_has_no_dialog_section(self):
        asm = generate(check_source("DIM X AS INTEGER\nX = 1\nEND\n"))
        self.assertTrue(asm.startswith("PB_DIALOG equ 0\n"))
        self.assertNotIn("gui_", asm)
        self.assertIn("    jp rt_exit", asm)


# ------------------------------------------------------------------ behaviour
@requires_pasmo
class GuiBehaviourTests(unittest.TestCase):
    maxDiff = None

    def run_gui(self, source, events, **kw):
        run = guarded_run(source, events=events, **kw)
        self.assertEqual(run.violations, [], "memory-boundary violations")
        return run.cpu

    def fns(self, cpu):
        return [fn for fn, _ in cpu.os_log]

    PANEL = (
        "DIM Hits AS INTEGER\n"            # 1
        "DIM Misses AS INTEGER\n"          # 2
        "Hits = 0\n"                       # 3
        'MESSAGE "panel starting"\n'       # 4
        'WINDOW "Panel"\n'                 # 5
        'LABEL "Hit or miss"\n'            # 6  object 2
        'BUTTON "Hit", Score_Hit\n'        # 7  object 3
        'BUTTON "Miss", Score_Miss\n'      # 8  object 4
        'BUTTON "Leave", Leave_Panel\n'    # 9  object 5
        "SUB Score_Hit\n"
        "Hits = Hits + 1\n"
        'MESSAGE "hits " + STR$(Hits)\n'
        "END SUB\n"
        "SUB Score_Miss\n"
        "Misses = Misses + 1\n"
        "IF Misses > 1 THEN\n"
        'MESSAGE "misses " + STR$(Misses) + " total " + STR$(Hits + Misses)\n'
        "END IF\n"
        "END SUB\n"
        "SUB Leave_Panel\n"
        "EXIT\n"
        "END SUB\n"
        "END\n"
    )

    def test_startup_sequence_and_focus(self):
        cpu = self.run_gui(self.PANEL, [])
        self.assertTrue(cpu.idle, "the program must be waiting for events")
        self.assertFalse(cpu.exited)
        self.assertEqual(cpu.alerts, ["panel starting"])  # main line ran first
        self.assertEqual(self.fns(cpu), [FN_ALERT, FN_DEFINE, FN_DISPLAY, FN_FOCUS, FN_WAIT])
        self.assertEqual(cpu.os_log[3], (FN_FOCUS, 3))  # first button
        self.assertTrue(cpu.dialog_shown)
        self.assertEqual(cpu.dialog["title"], "Panel")

    def test_multiple_handlers_repeated_clicks_and_state(self):
        cpu = self.run_gui(
            self.PANEL,
            [("click", 3), ("click", 3), ("click", 4), ("click", 3), ("click", 4), ("click", 5)],
        )
        self.assertTrue(cpu.exited)
        self.assertEqual(
            cpu.alerts, ["panel starting", "hits 1", "hits 2", "hits 3", "misses 2 total 5"]
        )
        # every object event went through os_process_event before dispatch
        self.assertEqual(self.fns(cpu).count(FN_PROCESS), 6)
        # EXIT: dialog removed, then os_app_exit, nothing after
        self.assertEqual(self.fns(cpu)[-2:], [FN_REMOVE, FN_EXIT])

    def test_events_that_must_not_dispatch(self):
        cpu = self.run_gui(
            self.PANEL,
            [
                ("noevent",),             # Z: IX corrupt, must be ignored
                ("key", ord("H")),        # keyboard: no action in M3a
                ("click", 2),             # the label
                ("click", 1),             # the background box
                ("click", 99),            # no such object
                ("objevent", 3, z80sim.OBEV_DCLICK),  # not a click
                ("message", z80sim.OM_TOPBAR, 0),
                ("click", 3),             # finally a real click
            ],
        )
        self.assertTrue(cpu.idle)
        self.assertEqual(cpu.alerts, ["panel starting", "hits 1"])
        processed = [d for fn, d in cpu.os_log if fn == FN_PROCESS]
        self.assertEqual(len(processed), 6)  # all OS messages, never key/no-event

    def test_om_exit_removes_dialog_and_exits(self):
        cpu = self.run_gui(self.PANEL, [("click", 3), ("exit",), ("click", 3)])
        self.assertTrue(cpu.exited)
        self.assertEqual(cpu.alerts, ["panel starting", "hits 1"])
        self.assertEqual(self.fns(cpu)[-3:], [FN_WAIT, FN_REMOVE, FN_EXIT])
        self.assertEqual(cpu.events, [("click", 3)], "nothing after om_exit is consumed")

    def test_exit_in_main_line_never_opens_the_dialog(self):
        cpu = self.run_gui(
            'MESSAGE "before"\nEXIT\nWINDOW "Never"\nBUTTON "X", Nope\nSUB Nope\nEND SUB\nEND\n',
            [("click", 2)],
        )
        self.assertTrue(cpu.exited)
        self.assertEqual(self.fns(cpu), [FN_ALERT, FN_EXIT])  # no define, no remove

    def test_dialog_failure_is_reported_then_exits(self):
        cpu = self.run_gui(self.PANEL, [("click", 3)], fail_dialog_define=True)
        self.assertTrue(cpu.exited)
        self.assertEqual(
            cpu.alerts, ["panel starting", "Runtime error: the window could not be opened"]
        )
        self.assertNotIn(FN_REMOVE, self.fns(cpu))

    def test_runtime_string_error_in_handler_closes_dialog(self):
        source = (
            "DIM T$ AS STRING\n"
            'WINDOW "Overflow"\n'
            'BUTTON "Fill", Fill_It\n'
            "SUB Fill_It\n"
            "T$ = STR$(-32768)\n"   # line 5: capacity 4 holds 3 characters
            'MESSAGE "unreachable"\n'
            "END SUB\n"
            "END\n"
        )
        run = guarded_run(source, string_capacity=4, events=[("click", 2), ("click", 2)])
        self.assertEqual(run.violations, [])
        cpu = run.cpu
        self.assertTrue(cpu.exited)
        self.assertEqual(cpu.alerts, ["Runtime error: string too long at line 5"])
        self.assertEqual(self.fns(cpu)[-3:], [FN_ALERT, FN_REMOVE, FN_EXIT])

    def test_handlers_use_the_whole_statement_language(self):
        source = (
            "DIM I AS INTEGER\nDIM Acc AS INTEGER\nDIM W$ AS STRING\n"
            'W$ = "pcw sixteen"\n'
            'WINDOW "Work"\n'
            'BUTTON "Run", Do_Work\n'
            'BUTTON "End", Stop_All\n'
            "SUB Do_Work\n"
            "Acc = 0\n"
            "FOR I = 1 TO 4\n"
            "IF I <> 3 THEN\n"
            "Acc = Acc + I * I\n"
            "END IF\n"
            "NEXT I\n"
            "WHILE Acc > 15\n"
            "Acc = Acc - 7\n"
            "WEND\n"
            'IF MID$(W$, 5, 3) = "six" THEN\n'
            'MESSAGE RIGHT$(W$, 7) + " " + STR$(Acc) + " " + STR$(LEN(W$))\n'
            "END IF\n"
            "END SUB\n"
            "SUB Stop_All\nEXIT\nEND SUB\nEND\n"
        )
        cpu = self.run_gui(source, [("click", 2), ("click", 2), ("click", 3)])
        # 1+4+16 = 21 -> 14; repeated, the same result
        self.assertEqual(cpu.alerts, ["sixteen 14 11", "sixteen 14 11"])
        self.assertTrue(cpu.exited)


# ---------------------------------------------------------- shipped programs
@requires_pasmo
class ExampleGuiApplications(unittest.TestCase):
    """The three M3a examples under scripted sessions — the same sessions the
    owner's XAnne procedure describes (RUNTIME-RESULTS.md, M3a scripts)."""

    def session(self, name, events, alerts, exited=True):
        source = (ROOT / "examples" / f"{name}.pbas").read_text(encoding="utf-8")
        run = guarded_run(source, events=events)
        self.assertEqual(run.violations, [])
        self.assertEqual(run.alerts, alerts)
        self.assertEqual(run.cpu.exited, exited)
        if exited:
            self.assertEqual([fn for fn, _ in run.cpu.os_log][-2:], [FN_REMOVE, FN_EXIT])
        return run

    def test_tally(self):
        run = self.session(
            "tally",
            # objects: 1 box, 2-3 labels, 4 Add, 5 Score, 6 Quit
            [("click", 5), ("click", 4), ("click", 4), ("click", 4), ("click", 5),
             ("click", 4), ("click", 5), ("click", 6)],
            ["Score 100 after 0 clicks: ahead",
             "Click 1: score 98", "Click 2: score 96", "Click 3: bonus, score 111",
             "Score 111 after 3 clicks: ahead",
             "Click 4: score 109", "Score 109 after 4 clicks: ahead",
             "Goodbye from Tally"],
        )
        self.assertEqual(
            [o.get("text") for o in run.cpu.dialog["objects"]],
            [None, "Add counts a click; Score reports", "Every third click earns a bonus",
             "Add", "Score", "Quit"],
        )

    def test_tally_falls_behind(self):
        self.session(
            "tally",
            [("click", 4), ("click", 4), ("click", 5)],
            ["Click 1: score 98", "Click 2: score 96", "Score 96 after 2 clicks: behind"],
            exited=False,
        )

    def test_greeter(self):
        run = self.session(
            "greeter",
            [("click", 6), ("click", 6), ("click", 7)],
            ["Preparing greetings for PcW16 owner",
             "Hello, PcW16 owner (greeting 1)",
             "Hello, PcW16 owner (greeting 2)", "Twice now: PcW16!"],
        )
        self.assertEqual(len([o for o in run.cpu.dialog["objects"] if o["type"] == z80sim.OB_LABEL]), 4)

    def test_countdown(self):
        self.session(
            "countdown",
            [("click", 4), ("click", 5), ("click", 4), ("click", 5), ("click", 5),
             ("click", 4), ("click", 6)],
            ["Counted down from 3, sum 6", "Start is now 4", "Counted down from 4, sum 10",
             "Start is now 5", "Start is now 6", "Counted down from 6, sum 21", "Stopped"],
        )


@requires_pasmo
@requires_files(ROOT.parent / "POC" / "examples", what="the prototype's example programs")  # M14
class PocDialogParity(unittest.TestCase):
    """POC dialog examples that need only M3a constructs now build and
    behave as their POC READMEs describe (read-only inputs)."""

    def poc(self, name):
        return (ROOT.parent / "POC" / "examples" / f"{name}.pbas").read_text(encoding="utf-8")

    def test_buttons_native(self):
        run = guarded_run(self.poc("buttons_native"), events=[("click", 4), ("click", 5)])
        self.assertEqual(run.violations, [])
        self.assertEqual(run.alerts, ["Count is above ten", "Written in PcW16 BASIC"])

    def test_loop_lab(self):
        run = guarded_run(self.poc("loop_lab"), events=[("click", 4), ("click", 5), ("click", 6)])
        self.assertEqual(run.violations, [])
        self.assertEqual(run.alerts, ["Total: 15", "Iterations: 0"])
        self.assertTrue(run.cpu.exited)

    def test_loop_lab_46(self):
        run = guarded_run(self.poc("loop_lab_46"), events=[("click", 3), ("click", 4), ("click", 5)])
        self.assertEqual(run.violations, [])
        self.assertEqual(run.alerts, ["Count: 5", "Descending sum: 15"])
        self.assertTrue(run.cpu.exited)

    def test_logic_zero_buttons_is_a_positioned_m3a_error(self):
        with self.assertRaises(SourceError) as caught:
            generate(check_source(self.poc("logic")))
        self.assertEqual((caught.exception.line, caught.exception.column), (2, 1))


if __name__ == "__main__":
    unittest.main()
