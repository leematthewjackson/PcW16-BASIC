"""M10 Stage D1: MDEDIT II (examples/mdedit2.pbas) on the simulator.

Scripted key, menu and window events; the saved file is compared byte for
byte with the same edits applied to test_m9_text.TextModel (plus ranges).
Covers the selection (Shift + cursor keys and Mark), cut / copy / paste,
undo / redo and their 4-step bound, typing over a selection, replace all,
display-only wrap, and the checked save with its backup. Simulator evidence:
which shifted keys XAnne passes, and how the page looks, is for the owner.
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
SRC = (ROOT / "examples" / "mdedit2.pbas").read_text(encoding="utf-8")
DOC = (ROOT / "developer-tests" / "edtest.md").read_bytes()
F = "\\PCW\\FOLDER01"
UP, DOWN, LEFT, RIGHT, HOME, END_ = 0xE0, 0xE1, 0xE2, 0xE3, 0xE6, 0xE7
BS, DEL, RET = 8, 0xE5, 13
# menu titles count from 1, entries from 0 (dividers are not numbered)
SAVE, QUIT = ("menu", 1, 1), ("menu", 1, 2)
UNDO, REDO, CUT, COPY, PASTE, SELALL, MARK = (("menu", 2, k) for k in range(7))
FINDER = ("menu", 2, 7)
WRAP = ("menu", 3, 0)
STEPS = 900_000_000


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


def shift(code, n=1):
    return [("key", code, 1)] * n


def run(events, files=None, **disk_options):
    disk = z80sim.Disk(files={(F, n): d for n, d in (files if files is not None else {"EDTEST.MD": DOC}).items()},
                       **disk_options)
    r = guarded_run(SRC, events=events, disk=disk, max_steps=STEPS)
    assert r.violations == [], r.violations[:5]
    # a runtime error ends the program: never expected in these scripts
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r


def pos(m: TextModel, n: int, c: int) -> int:
    return m._line(n)[0] + c - 1


@requires_pasmo
class EditorTests(unittest.TestCase):
    def saved_after(self, events, **kw):
        r = run(events + [SAVE, QUIT], **kw)
        self.assertTrue(r.cpu.exited, r.alerts)
        return r, r.cpu.disk.file("EDTEST.MD")

    def test_builds_with_a_code_bank_and_opens(self):
        r = run([])
        self.assertIsNotNone(r.report.banked)
        self.assertEqual(string_var(r, "INFO$"), "Opened EDTEST.MD")
        self.assertEqual(r.cpu.texts[0][2], "|# MDEDIT acceptance document")

    def test_copy_paste_with_shift_selection(self):
        m = TextModel(DOC)
        # line 1 "# MDEDIT acceptance document": select "MDEDIT" (columns 3..8)
        ev = [("key", RIGHT)] * 2 + shift(RIGHT, 6) + [COPY]
        clip = bytes(m.b[pos(m, 1, 3):pos(m, 1, 9)])
        self.assertEqual(clip, b"MDEDIT")
        ev += [("key", DOWN)] * 2 + [("key", HOME), PASTE] + keys("!")
        at = pos(m, 3, 1)
        m.b[at:at] = clip + b"!"
        r, saved = self.saved_after(ev)
        self.assertEqual(saved, bytes(m.b))
        self.assertEqual(r.cpu.disk.file("EDTEST.BAK"), DOC, "the previous version is kept")
        self.assertIsNone(r.cpu.disk.file("MDEDIT2.TMP"))

    def test_cut_across_lines_then_undo_and_redo(self):
        m = TextModel(DOC)
        # from line 2 column 1, shift-down twice: lines 2 and 3 with their ends
        ev = [("key", DOWN)] + shift(DOWN, 2) + [CUT]
        cut = bytes(m.b[pos(m, 2, 1):pos(m, 4, 1)])
        r, saved = self.saved_after(ev)
        after_cut = bytearray(m.b)
        del after_cut[pos(m, 2, 1):pos(m, 4, 1)]
        self.assertEqual(saved, bytes(after_cut))
        _, saved = self.saved_after(ev + [UNDO])
        self.assertEqual(saved, DOC)
        _, saved = self.saved_after(ev + [UNDO, REDO])
        self.assertEqual(saved, bytes(after_cut))
        # paste it back at the end of the document
        _, saved = self.saved_after(ev + [("key", END_, 4), PASTE])
        self.assertEqual(saved, bytes(after_cut) + cut)

    def test_typing_replaces_the_selection_and_is_one_step(self):
        m = TextModel(DOC)
        ev = shift(RIGHT, 7) + keys("Hello")  # "# MDEDI" -> "Hello"
        del m.b[0:7]
        m.b[0:0] = b"Hello"
        _, saved = self.saved_after(ev)
        self.assertEqual(saved, bytes(m.b))
        _, saved = self.saved_after(ev + [UNDO])
        self.assertEqual(saved, DOC, "the selection removal and the typing undo together")

    def test_undo_keeps_four_steps(self):
        ev = []
        for k in range(5):  # five steps on five different lines
            ev += [("key", DOWN), ("key", HOME)] + keys(str(k))
        m = TextModel(DOC)
        for k in range(5):
            m.insert(k + 2, 1, str(k).encode())
        _, saved = self.saved_after(ev)
        self.assertEqual(saved, bytes(m.b))
        r, saved = self.saved_after(ev + [UNDO] * 5)
        first = TextModel(DOC)
        first.insert(2, 1, b"0")
        self.assertEqual(saved, bytes(first.b), "four steps undone; the first stays")
        r = run(ev + [UNDO] * 5)
        self.assertEqual(string_var(r, "INFO$"), "Nothing to undo")
        _, saved = self.saved_after(ev + [UNDO] * 4 + [REDO] * 4)
        self.assertEqual(saved, bytes(m.b))

    def test_mark_select_all_and_delete(self):
        _, saved = self.saved_after([SELALL, ("key", DEL)] + keys("x"))
        self.assertEqual(saved, b"x")
        m = TextModel(DOC)
        ev = [MARK] + [("key", RIGHT)] * 4 + [MARK, ("key", BS)]
        del m.b[0:4]
        _, saved = self.saved_after(ev)
        self.assertEqual(saved, bytes(m.b))

    def test_replace_all(self):
        b = buttons()
        ev = [FINDER, ("edit", b[("FINDER", "FINDTEXT$")], "Section"),
              ("edit", b[("FINDER", "REPLTEXT$")], "Part"), ("click", b[("FINDER", "Replace all")])]
        r, saved = self.saved_after(ev)
        self.assertEqual(saved, DOC.replace(b"Section", b"Part"))
        self.assertIn(b"Section", DOC)
        _, saved = self.saved_after(ev + [UNDO])
        self.assertEqual(saved, DOC, "replace all is one undo step")

    def test_wrap_is_on_and_can_be_turned_off(self):
        long = b"0123456789" * 11 + b"\r\nnext"
        digits = "0123456789" * 11
        r = run([], files={"EDTEST.MD": long})
        texts = [t[2] for t in r.cpu.texts]
        self.assertEqual(texts[:4], ["|" + digits[:47], digits[47:94], digits[94:], "next"])
        self.assertEqual(string_var(r, "STATUS$"), "L1/2 C1")
        r = run([WRAP], files={"EDTEST.MD": long})
        self.assertEqual([t[2] for t in r.cpu.texts][-2:], ["|" + digits[:47], "next"])
        self.assertEqual(string_var(r, "STATUS$"), "L1/2 C1 nowrap")
        _, saved = self.saved_after([WRAP], files={"EDTEST.MD": long})
        self.assertEqual(saved, long, "wrap changes only the display")

    def test_a_failed_save_keeps_the_file(self):
        for faults in ({146: {1: 0xA3}}, {154: {1: 0x05}}):
            with self.subTest(faults=faults):
                r = run(keys("abc") + [SAVE], faults_at=faults)
                self.assertEqual(r.cpu.disk.file("EDTEST.MD"), DOC)
                self.assertTrue(r.alerts)
                self.assertIn("*", string_var(r, "STATUS$"), "still unsaved")

    def test_a_save_that_does_not_read_back_is_refused(self):
        opening = sum(1 for e in run([]).cpu.os_log if e[0] == z80sim.FN_OS_READ_FILE)
        r = run(keys("abc") + [SAVE], faults_at={147: {opening + 1: 0x07}})  # the read-back's first read
        self.assertEqual(r.alerts, ["Not saved: check failed (7)"])
        self.assertEqual(r.cpu.disk.file("EDTEST.MD"), DOC)
        self.assertIsNone(r.cpu.disk.file("MDEDIT2.TMP"))


if __name__ == "__main__":
    unittest.main()
