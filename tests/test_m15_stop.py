"""M15 W1: Rosanne's Tasks > Stop (KI-35) and ON STOP (LANGUAGE-SPEC 6.1).

XAnne (owner, M15a r4/r5, docs/M15A-PROBE.md): Tasks > Stop arrives as a menu
selection of title 0 (the Tasks menu), entry 0 (Stop), never as om_exit, and
the runtime dropped it. Since M15 a program with menus ends on it, and ON STOP
F (a FUNCTION ... AS BOOLEAN) decides: TRUE ends the program, FALSE keeps it.
Simulator evidence; the owner's M15c session is the acceptance.
"""
from __future__ import annotations

import unittest

import z80sim
from memguard import guarded_run
from pbas import check_source
from pbas.errors import SourceError
from test_m7_examples import objects
from toolchain import requires_pasmo

STOP = ("menu", 0, 0)  # Tasks (title 0), Stop (entry 0)


def allow(src):
    return ("click", objects(src, 64)["Allow"])
F = "\\PCW\\FOLDER01"


def program(on_stop=None, menus=True, body="RETURN Allowed", extra=""):
    lines = ["DIM Allowed AS BOOLEAN", "DIM Asked AS INTEGER", 'WINDOW Main, "T", LARGE',
             'BUTTON "Allow", AllowIt', 'BUTTON "Quit", Quit']
    if menus:
        lines += ['MENU "File"', '    ITEM "Quit", Quit', "END MENU"]
    if on_stop:
        lines.append(f"ON STOP {on_stop}")
    lines += ["FUNCTION MayStop() AS BOOLEAN", "    Asked = Asked + 1", f"    {body}", "END FUNCTION",
              "SUB AllowIt", "    Allowed = TRUE", "END SUB", "SUB Quit", "    EXIT", "END SUB", extra, "END"]
    return "\n".join(lines) + "\n"


def run(src, events, legacy=False, answers=None, disk=None):
    r = guarded_run(src, events=events, alert_answers=answers, disk=disk,
                    build_options={"legacy_tasks_stop": legacy})
    assert r.violations == [], r.violations[:5]
    return r


def word(r, name):
    at = r.symbols[f"var_{name.lower()}"] if f"var_{name.lower()}" in r.symbols else r.symbols[f"var_{name}"]
    return r.cpu.mem[at] | (r.cpu.mem[at + 1] << 8)


@requires_pasmo
class DefaultStopTests(unittest.TestCase):
    def test_a_program_with_menus_ends_on_stop(self):
        r = run(program(), [STOP])
        self.assertTrue(r.cpu.exited)

    def test_legacy_keeps_ignoring_it(self):
        r = run(program(), [STOP], legacy=True)
        self.assertFalse(r.cpu.exited)

    def test_other_tasks_entries_are_left_to_rosanne(self):
        r = run(program(), [("menu", 0, 1)])
        self.assertFalse(r.cpu.exited)

    def test_a_program_without_menus_or_on_stop_is_unchanged(self):
        src = program(menus=False)
        r = run(src, [("hotkey", 0, 0)])
        self.assertFalse(r.cpu.exited)


@requires_pasmo
class OnStopTests(unittest.TestCase):
    def test_false_keeps_the_program_running(self):
        r = run(program("MayStop"), [STOP])
        self.assertFalse(r.cpu.exited)
        self.assertEqual(word(r, "ASKED"), 1)  # the handler ran

    def test_true_ends_it(self):
        src = program("MayStop")
        r = run(src, [allow(src), STOP])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(word(r, "ASKED"), 1)

    def test_each_stop_asks_again(self):
        src = program("MayStop")
        r = run(src, [STOP, STOP, allow(src), STOP])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(word(r, "ASKED"), 3)

    def test_the_handler_may_ask_a_question(self):
        body = 'RETURN ASK("Unsaved changes", "Discard", "Cancel") = 1'
        src = program("MayStop", body=body).replace("RETURN ASK", "Asked = ASK").replace(
            "    Asked = Asked + 1\n", "")
        src = src.replace('    Asked = ASK("Unsaved changes", "Discard", "Cancel") = 1',
                          '    Asked = ASK("Unsaved changes", "Discard", "Cancel")\n    RETURN Asked = 1')
        r = run(src, [STOP], answers=[1])  # Cancel
        self.assertFalse(r.cpu.exited)
        self.assertIn("Unsaved changes", r.alerts)
        r = run(src, [STOP], answers=[0])  # Discard
        self.assertTrue(r.cpu.exited)

    def test_the_handler_may_save_a_file(self):
        body = 'OPEN "SAVED.TXT" FOR OUTPUT AS #1\n    PRINT #1, "kept"\n    CLOSE #1\n    RETURN TRUE'
        disk = z80sim.Disk()
        r = run(program("MayStop", body=body), [STOP], disk=disk)
        self.assertTrue(r.cpu.exited)
        self.assertEqual(disk.files[(F, "SAVED.TXT")], b"kept\r\n")

    def test_without_menus_on_stop_still_hears_stop(self):
        src = program("MayStop", menus=False)
        r = run(src, [allow(src), ("hotkey", 0, 0)])
        self.assertTrue(r.cpu.exited)
        r = run(program("MayStop", menus=False), [("hotkey", 0, 0)])
        self.assertFalse(r.cpu.exited)

    def test_on_stop_in_the_simplest_program(self):
        # one unnamed window, a label and a button: the handler call needs the
        # binding section all the same (it held rt_gui_dispatch out once)
        src = ('WINDOW "S"\nLABEL "x"\nBUTTON "Quit", Quit\nON STOP Ending\n'
               'FUNCTION Ending() AS BOOLEAN\n    RETURN TRUE\nEND FUNCTION\nSUB Quit\n    EXIT\nEND SUB\nEND\n')
        r = run(src, [("hotkey", 0, 0)])
        self.assertTrue(r.cpu.exited)

    def test_on_stop_without_menus_is_warned_about(self):
        # M15c S5 (owner, XAnne): Rosanne offers no Tasks > Stop to a program without menus
        from pbas.lint import warnings
        found = warnings(check_source(program("MayStop", menus=False)))
        self.assertTrue(any("ON STOP in a program without menus" in w for *_, w in found), found)
        self.assertFalse(any("ON STOP" in w for *_, w in warnings(check_source(program("MayStop")))))

    def test_the_program_own_menus_still_work(self):
        r = run(program("MayStop"), [("menu", 1, 0)])
        self.assertTrue(r.cpu.exited)  # File > Quit
        self.assertEqual(word(r, "ASKED"), 0)


class OnStopErrorTests(unittest.TestCase):
    def bad(self, src, text):
        with self.assertRaises(SourceError) as cm:
            check_source(src)
        self.assertIn(text, str(cm.exception))

    def test_errors(self):
        need = "ON STOP needs a FUNCTION"
        self.bad(program("Quit"), need)  # a SUB
        self.bad(program("Nothing"), need)
        self.bad(program("MayStop").replace("FUNCTION MayStop() AS BOOLEAN", "FUNCTION MayStop() AS INTEGER")
                 .replace("RETURN Allowed", "RETURN 1"), need)
        self.bad(program("MayStop").replace("FUNCTION MayStop() AS BOOLEAN", "FUNCTION MayStop(A AS INTEGER) AS BOOLEAN"),
                 need)
        self.bad(program("MayStop").replace("ON STOP MayStop", "ON STOP MayStop\nON STOP MayStop"),
                 "only one ON STOP")
        self.bad("ON STOP F\nFUNCTION F() AS BOOLEAN\n    RETURN TRUE\nEND FUNCTION\nEND\n",
                 "ON STOP requires a WINDOW")
        self.bad(program("MayStop").replace("ON STOP MayStop\n", "").replace(
            "SUB AllowIt\n", "SUB AllowIt\n    ON STOP MayStop\n"), "only allowed at the top level")

    def test_on_is_still_a_name(self):
        check_source('DIM On AS INTEGER\nOn = 1\nEND\n')


if __name__ == "__main__":
    unittest.main()
