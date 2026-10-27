"""M9 flagship: MDEDIT (examples/mdedit.pbas) through the owner's acceptance
steps (docs/M9-ACCEPTANCE.md, E1-E11) on the simulator.

The edits are scripted as key events; the saved file is compared byte for
byte with the same edits applied by test_m9_text.TextModel. Simulator
evidence: what XAnne sends for each key, and how the page looks, is for the
owner's run.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import check_source
from pbas.layout import build_dialog
from test_m9_text import TextModel
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "examples" / "mdedit.pbas").read_text(encoding="utf-8")
DOC = (ROOT / "developer-tests" / "edtest.md").read_bytes()
F = "\\PCW\\FOLDER01"
UP, DOWN, LEFT, RIGHT, HOME, END_, PGUP, PGDN = 0xE0, 0xE1, 0xE2, 0xE3, 0xE6, 0xE7, 0xE8, 0xE9
BS, DEL, RET, STOP = 8, 0xE5, 13, 0xFE
SAVE, QUIT = ("menu", 1, 1), ("menu", 1, 3)  # dividers are not numbered (UIPROBE P1)
STEPS = 300_000_000


def buttons() -> dict:
    program = check_source(SRC)
    result = {}
    for window in program.windows:
        lay = build_dialog(program, window, True)
        for obj in lay.objects:
            if obj.kind == "BUTTON":
                result[(window.name, obj.text)] = obj.number
        for row in lay.bindings:
            result[(window.name, row.var_name)] = row.number
    return result


def keys(text: str):
    return [("key", ord(c)) for c in text]


def run(events, files=None, **options):
    disk = z80sim.Disk(files={(F, n): d for n, d in (files if files is not None else {"EDTEST.MD": DOC}).items()},
                       faults=options.pop("faults", None), faults_from=options.pop("faults_from", None))
    return guarded_run(SRC, events=events, disk=disk, max_steps=STEPS, **options)


@requires_pasmo
class EditorTests(unittest.TestCase):
    def check(self, r):
        self.assertEqual(r.violations, [])
        self.assertIsNotNone(r.report.banked, "MDEDIT is larger than 16K: built with a code bank")

    def test_e1_open_and_e2_scroll(self):
        r = run([("key", PGDN)] * 10)
        self.check(r)
        self.assertEqual(string_var(r, "STATUS$"), "L114/114 C1")
        self.assertEqual(string_var(r, "INFO$"), "")
        r = run([("key", PGDN)] * 10 + [("key", PGUP)] * 10)
        self.assertEqual(string_var(r, "STATUS$"), "L1/114 C1")
        r = run([])
        self.assertEqual(string_var(r, "INFO$"), "Opened EDTEST.MD")
        texts = [t[2] for t in r.cpu.texts]
        self.assertEqual(texts[0], "|# MDEDIT acceptance document", "the caret before the first character")
        empty = sum(1 for t in DOC.split(b"\r\n")[:13] if not t)
        self.assertEqual(len(texts), 13 - empty, "13 rows; empty lines draw no text")

    def test_e3_to_e9_edit_save_quit_and_e10_reopen(self):
        model = TextModel(DOC)
        events = []
        # E3 move: down 5 lines (line 6 = "## Section 1"), right 3
        events += [("key", DOWN)] * 5 + [("key", RIGHT)] * 3
        # E4 insert
        events += keys("NEW ")
        model.insert(6, 4, b"NEW ")
        # E5 delete: Backspace twice, then Delete once
        events += [("key", BS)] * 2 + [("key", DEL)]
        model.delete(6, 6, 2)
        model.delete(6, 6, 1)
        # E6 split at the caret (line 6, column 6)
        events += [("key", RET)]
        model.split(6, 6)
        # E7 join: Backspace at the start of the new line joins it again,
        # then End + Delete joins line 8 to line 9
        events += [("key", BS)]
        model.join(6)
        events += [("key", DOWN), ("key", DOWN), ("key", END_), ("key", DEL)]
        model.join(8)
        # E8 search: the Tools window, "FINDME", Find
        b = buttons()
        events += [("click", b[("MAIN", "Files...")]), ("edit", b[("TOOLS", "FINDTEXT$")], "FINDME"),
                   ("click", b[("TOOLS", "Find")])]
        # type at the found place
        events += keys("*")
        line, col = model.find(b"FINDME", 1, 1)
        model.insert(line, col, b"*")
        # E9 save and quit
        events += [SAVE, QUIT]
        r = run(events)
        self.check(r)
        self.assertEqual(r.alerts, [])
        self.assertTrue(r.cpu.exited)
        saved = r.cpu.disk.file("EDTEST.MD")
        self.assertEqual(saved, bytes(model.b))
        self.assertEqual(saved, (ROOT / "tests" / "fixtures" / "m9" / "edtest_expected.md").read_bytes(),
                         "the owner's E10 comparison file")
        self.assertIsNone(r.cpu.disk.file("MDEDIT.TMP"), "the temporary file was renamed")
        self.assertEqual(r.cpu.blocks_at_exit, [])
        # E10 reopen: what was saved is what is loaded and saved again
        r2 = run([SAVE, QUIT], files={"EDTEST.MD": saved})
        self.check(r2)
        self.assertEqual(r2.cpu.disk.file("EDTEST.MD"), saved)
        self.assertEqual(string_var(r2, "INFO$"), "Saved EDTEST.MD")

    def e3_to_e8(self, name_box=None):
        """Owner steps E3-E8 (as above); *name_box* is typed into the Tools
        window's File name box before Find, if given."""
        b = buttons()
        events = [("key", DOWN)] * 5 + [("key", RIGHT)] * 3 + keys("NEW ") + [("key", BS)] * 2 + [("key", DEL)]
        events += [("key", RET), ("key", BS), ("key", DOWN), ("key", DOWN), ("key", END_), ("key", DEL)]
        events += [("click", b[("MAIN", "Files...")])]
        if name_box is not None:
            events += [("edit", b[("TOOLS", "FILENAME$")], name_box)]
        events += [("edit", b[("TOOLS", "FINDTEXT$")], "FINDME"), ("click", b[("TOOLS", "Find")])] + keys("*")
        return events

    def test_e9_save_does_not_take_the_tools_name_box(self):
        # Owner XAnne (M9): E1-E8 passed; at E9 Ctrl+S gave "Saved as MDEDIT.TMP
        # only:  could not be replaced (247)": the name was empty. The File
        # name box had come back empty from the Tools window (E8's Find reads
        # every box), and Save used that box. Save now uses the document's
        # own name; the box is only for Open and Save as.
        expected = (ROOT / "tests" / "fixtures" / "m9" / "edtest_expected.md").read_bytes()
        for box in ("", "OTHER.MD"):
            with self.subTest(name_box=box):
                r = run(self.e3_to_e8(box) + [SAVE, QUIT])
                self.check(r)
                self.assertEqual(r.alerts, [])
                self.assertTrue(r.cpu.exited, "saved, so Quit does not ask")
                self.assertEqual(r.cpu.disk.file("EDTEST.MD"), expected)
                self.assertIsNone(r.cpu.disk.file("MDEDIT.TMP"))
                self.assertIsNone(r.cpu.disk.file("OTHER.MD"), "nothing written under the box's name")

    def test_failed_replacement_keeps_the_text_and_the_mark(self):
        # The original cannot be deleted (Rosanne error 4, say): the text is in
        # MDEDIT.TMP, EDTEST.MD is untouched, and the document is still
        # unsaved: the status keeps "*" and Quit asks (Cancel keeps it open).
        r = run(keys("x") + [SAVE, QUIT], faults={z80sim.FN_OS_DELETE_FILE: 4}, alert_answers=[0, 2])
        self.check(r)
        self.assertEqual(r.alerts[0], "Saved as MDEDIT.TMP only: [EDTEST.MD] could not be replaced (4)")
        self.assertEqual(r.alerts[1], "There are unsaved changes.")
        self.assertFalse(r.cpu.exited)
        self.assertEqual(r.cpu.disk.file("EDTEST.MD"), DOC)
        self.assertEqual(r.cpu.disk.file("MDEDIT.TMP"), b"x" + DOC)
        self.assertEqual(string_var(r, "STATUS$"), "L1/114 C2 *")
        # the rename fails instead: the same, with its own message
        r = run(keys("x") + [SAVE], faults={z80sim.FN_OS_RENAME_FILE: 4})
        self.assertEqual(r.alerts, ["Saved as MDEDIT.TMP only: rename to [EDTEST.MD] failed (4)"])
        self.assertEqual(r.cpu.disk.file("MDEDIT.TMP"), b"x" + DOC)
        self.assertEqual(string_var(r, "STATUS$"), "L1/114 C2 *")

    def test_open_and_save_as_need_a_name(self):
        b = buttons()
        for button in ("Open", "Save as"):
            with self.subTest(button=button):
                r = run(keys("x") + [("click", b[("MAIN", "Files...")]), ("edit", b[("TOOLS", "FILENAME$")], ""),
                                     ("click", b[("TOOLS", button)])])
                self.check(r)
                self.assertEqual(r.alerts, ["Type a file name first."])
                self.assertEqual(r.cpu.disk.file("EDTEST.MD"), DOC)
                self.assertIsNone(r.cpu.disk.file("MDEDIT.TMP"))

    def test_quit_asks_about_changes(self):
        r = run(keys("x") + [QUIT], alert_answers=[1])  # Discard (buttons count from 0 here)
        self.check(r)
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.disk.file("EDTEST.MD"), DOC, "Discard keeps the file")
        r = run(keys("x") + [QUIT], alert_answers=[0])  # Save
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.disk.file("EDTEST.MD"), b"x" + DOC)
        r = run(keys("x") + [QUIT, ("key", STOP)], alert_answers=[2, 2])  # Cancel, then Stop -> Cancel
        self.assertFalse(r.cpu.exited)
        self.assertEqual(string_var(r, "STATUS$"), "L1/114 C2 *")

    def test_e11_errors(self):
        # disk full while saving: the message, the original kept, no temporary file left
        r = run(keys("x") + [SAVE], faults_from={z80sim.FN_OS_WRITE_FILE: (1, 0xA3)})
        self.check(r)
        self.assertEqual(r.alerts, ["Not saved: error 163. EDTEST.MD is unchanged."])
        self.assertEqual(r.cpu.disk.file("EDTEST.MD"), DOC)
        self.assertIsNone(r.cpu.disk.file("MDEDIT.TMP"))
        self.assertEqual(string_var(r, "STATUS$"), "L1/114 C2 *", "still marked as changed")
        # no file yet: a new, empty document
        r = run([], files={})
        self.assertEqual(string_var(r, "INFO$"), "New file EDTEST.MD")
        self.assertEqual(string_var(r, "STATUS$"), "L1/1 C1")
        # a file too large for the buffer
        r = run([], files={"EDTEST.MD": b"x" * 60001})
        self.assertEqual(r.alerts, ["EDTEST.MD is larger than 60000 bytes; nothing was loaded."])
        # an invalid name typed into the Tools window
        b = buttons()
        r = run([("click", b[("MAIN", "Files...")]), ("edit", b[("TOOLS", "FILENAME$")], "BAD NAME"),
                 ("click", b[("TOOLS", "Open")])])
        self.check(r)
        self.assertEqual(r.alerts, ["Not a file name: [BAD NAME]"])

    def test_cursor_keys_as_dialog_messages(self):
        # Rosanne may report cursor keys on the focused button (obev_curdn ...)
        b = buttons()
        save = b[("MAIN", "Save")]
        r = run([("objevent", save, 5)] * 3 + [("objevent", save, 7)])
        self.check(r)
        length = len(DOC.split(b"\r\n")[3])
        self.assertEqual(string_var(r, "STATUS$"), f"L4/114 C{length + 1}")

    def test_long_line_scrolls_sideways(self):
        line = next(i for i, t in enumerate(DOC.split(b"\r\n"), 1) if t.startswith(b"A long line"))
        r = run([("key", DOWN)] * (line - 1) + [("key", END_)])
        self.check(r)
        length = len(DOC.split(b"\r\n")[line - 1])
        self.assertEqual(string_var(r, "STATUS$"), f"L{line}/114 C{length + 1}")
        shown = [t[2] for t in r.cpu.texts if t[2].endswith("|")]
        self.assertTrue(shown, "the caret's line is drawn ending with the caret")
        self.assertLessEqual(len(shown[-1]), 49)


if __name__ == "__main__":
    unittest.main()
