"""STARTER (examples/starter.pbas, M11 Stage E3): the small to-do list built
on lib/app.pbas and lib/listview.pbas. Adding, ticking, deleting, saving
(TODO.PDB with TODO.BAK), reopening, recovery and the unsaved-changes
question, on the simulator; the saved file is read with tools/pdbcheck.py.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import check_source
from pbas.layout import build_dialog
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pdbcheck  # noqa: E402

PATH = ROOT / "examples" / "starter.pbas"
SRC = PATH.read_text(encoding="utf-8")
F = "\\PCW\\FOLDER01"
SIG = "ID:I;TEXT:S40;DONE:B"
SAVE, QUIT = ("menu", 1, 0), ("menu", 1, 1)
UP, DOWN, DEL = 0xE0, 0xE1, 0xE5


def objects():
    program = check_source(SRC, path=PATH)
    lay = build_dialog(program, program.windows[0], True)
    out = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
    out.update({row.var_name: row.number for row in lay.bindings})
    return out


O = objects()


def add(text):
    return [("edit", O["NEWTEXT$"], text), ("click", O["Add"])]


def run(events, files=None, answers=None):
    disk = z80sim.Disk(files={(F, n): d for n, d in (files or {}).items()})
    r = guarded_run(SRC, events=events, disk=disk, path=PATH, max_steps=300_000_000,
                    alert_answers=answers, build_options={"runtime_sections": "all"})
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r


def tasks(data: bytes):
    code, info = pdbcheck.check(data, SIG)
    assert code == 0, info
    return [(row[1], bool(row[2])) for row in pdbcheck.decode(data, SIG, 100)]


@requires_pasmo
class StarterTests(unittest.TestCase):
    def test_add_tick_delete_save(self):
        ev = add("Buy milk") + add("Post letter") + add("Ring Ann") + [("key", UP), ("key", 32), ("key", UP),
                                                                     ("key", DEL), SAVE]
        r = run(ev)
        self.assertEqual(tasks(r.cpu.disk.file("TODO.PDB")), [("Post letter", True), ("Ring Ann", False)])
        self.assertEqual(string_var(r, "APPSTATUS$"), "2 tasks")
        self.assertEqual(string_var(r, "NEWTEXT$"), "")

    def test_reopen_and_backup(self):
        first = run(add("One") + add("Two") + [SAVE, QUIT]).cpu.disk.file("TODO.PDB")
        r = run(add("Three") + [SAVE], files={"TODO.PDB": first})
        self.assertEqual(tasks(r.cpu.disk.file("TODO.PDB")), [("One", False), ("Two", False), ("Three", False)])
        self.assertEqual(r.cpu.disk.file("TODO.BAK"), first)
        self.assertIsNone(r.cpu.disk.file("TODO.NEW"))

    def test_recovered_copy_is_reported(self):
        saved = run(add("Kept") + [SAVE]).cpu.disk.file("TODO.PDB")
        r = run([], files={"TODO.NEW": saved})
        self.assertEqual(r.alerts, ["TODO.PDB was recovered from a copy: save it"])
        self.assertEqual(string_var(r, "APPSTATUS$"), "* 1 tasks")

    def test_unsaved_changes_question(self):
        ev = add("Unsaved") + [QUIT]
        self.assertFalse(run(ev, answers=[2]).cpu.exited, "Cancel")
        r = run(ev, answers=[1])
        self.assertTrue(r.cpu.exited)
        self.assertIsNone(r.cpu.disk.file("TODO.PDB"), "Discard: nothing written")
        r = run(ev, answers=[0])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(tasks(r.cpu.disk.file("TODO.PDB")), [("Unsaved", False)])

    def test_rows_are_two_aligned_columns_and_the_chosen_one_inverted(self):
        program = check_source(SRC, path=PATH)
        lay = build_dialog(program, program.windows[0], True)
        cx, cy = lay.canvas[1], lay.canvas[2]
        r = run(add("Buy milk") + add("Post letter") + [("key", UP), ("key", 32)])
        rows = {}
        inverted = set()
        for entry in r.cpu.draw_log:
            if entry[0] == "text":
                _, x, y, text, _ = entry
                rows.setdefault((y - cy) // 16, {})[x - cx] = text
            elif entry[0] == "direct" and entry[1] == 1 and entry[4] == 560:
                rows[(entry[3] - cy) // 16] = {}
                inverted.discard((entry[3] - cy) // 16)
            elif entry[0] == "direct" and entry[1] == 4 and entry[4] == 560:
                inverted ^= {(entry[3] - cy) // 16}
        # Up chose "Buy milk"; Space ticked it
        self.assertEqual(rows[0], {2: "[x]", 30: "Buy milk"})
        self.assertEqual(rows[1], {2: "[ ]", 30: "Post letter"}, "the text starts at 30 whatever the box shows")
        self.assertEqual(inverted, {0})

    def test_empty_text_adds_nothing(self):
        r = run(add("   ") + [SAVE])
        self.assertEqual(tasks(r.cpu.disk.file("TODO.PDB")), [])


if __name__ == "__main__":
    unittest.main()
