"""M10 Stage E: CONTACTS III (examples/contacts3.pbas) on the simulator, with
the 160-contact test database of tools/m10_sample_data.py.

Covers loading, the page's order for each sort (against Python's own sort
of the same data), finding, adding with validation, editing, deleting
(with and without agreement), saving with the backup, recovery from
CONTACTS.NEW and from CONTACTS.BAK (acceptance C8), and the refusal to replace
an unreadable file silently.
Simulator evidence: XAnne behaviour is for the owner's run.
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
import m10_sample_data as sample  # noqa: E402
import pdbcheck  # noqa: E402

SRC = (ROOT / "examples" / "contacts3.pbas").read_text(encoding="utf-8")
F = "\\PCW\\FOLDER01"
ROWS = sample.contacts()
DATA = sample.database([sample.record(*r) for r in ROWS], len(ROWS) + 1)
DOWN, RET, DEL = 0xE1, 13, 0xE5
SAVE, QUIT = ("menu", 1, 0), ("menu", 1, 1)  # titles from 1, entries from 0
STEPS = 900_000_000


def buttons() -> dict:
    program = check_source(SRC, path=ROOT / "examples" / "contacts3.pbas")
    out = {}
    for window in program.windows:
        lay = build_dialog(program, window, True)
        for obj in lay.objects:
            if obj.kind == "BUTTON":
                out[(window.name, obj.text)] = obj.number
        for row in lay.bindings:
            out[(window.name, row.var_name)] = row.number
    return out


B = None


def b(window, name):
    global B
    if B is None:
        B = buttons()
    return B[(window, name)]


# M14 (KI-100): the M14 file-safety code does not fit CONTACTS III's resident-only build, so
# the M10 application is run as the owner accepted it; its banked M14 build is run by
# tests/test_m11_rtbank.py and test_m14_*.py cover the M14 behaviour
AS_ACCEPTED = {"legacy_file_safety": True, "legacy_tasks_stop": True}


def run(events, files=None, answers=None):
    disk = z80sim.Disk(files={(F, n): d for n, d in (files if files is not None else {"CONTACTS.PDB": DATA}).items()})
    r = guarded_run(SRC, events=events, disk=disk, max_steps=STEPS, alert_answers=answers,
                    path=ROOT / "examples" / "contacts3.pbas", build_options=AS_ACCEPTED)
    assert r.violations == [], r.violations[:5]
    return r


def page(r) -> list[str]:
    """The names on the last page drawn (canvas x = 14), top to bottom; the
    simulator records screen positions, so the canvas's origin is taken from
    the row marker ">" (canvas x = 2)."""
    marks = [t for t in r.cpu.texts if t[2] == ">"]
    if not marks:
        return []
    x = marks[-1][0] - 2 + 14
    names = [t for t in r.cpu.texts if t[0] == x]
    if not names:
        return []
    top = min(t[1] for t in names)  # the last paint starts at its top row
    start = max(i for i, t in enumerate(names) if t[1] == top)
    return [t[2] for t in names[start:start + 13]]


def by_name(rows):
    return sorted(rows, key=lambda r: r[1].upper())  # stable: element order for equal keys


def records(data: bytes):
    return pdbcheck.decode(data, sample.CONTACT_TYPE, 10_000)


@requires_pasmo
class ContactsTests(unittest.TestCase):
    def test_the_sample_database_is_valid(self):
        self.assertEqual(pdbcheck.check(DATA, sample.CONTACT_TYPE, 200)[0], 0)
        self.assertEqual(len(ROWS), 160)

    def test_loads_and_shows_by_name(self):
        r = run([])
        self.assertEqual(string_var(r, "STATUS$"), "160/160, by name")
        self.assertEqual(page(r), [row[1] for row in by_name(ROWS)[:13]])

    def test_sort_by_town_then_name_and_by_number(self):
        # a new order keeps the chosen contact (the first by name) on the page
        chosen = by_name(ROWS)[0][0]

        def expected(order):
            at = [row[0] for row in order].index(chosen) + 1
            top = max(1, at - 13 + 1)
            return [row[1] for row in order[top - 1:top - 1 + 13]]
        r = run([("click", b("MAIN", "Sort"))])
        self.assertEqual(page(r), expected(sorted(by_name(ROWS), key=lambda row: row[4].upper())))
        self.assertEqual(string_var(r, "STATUS$"), "160/160, by town")
        r = run([("click", b("MAIN", "Sort"))] * 2)
        self.assertEqual(page(r), expected(ROWS))
        self.assertEqual(string_var(r, "STATUS$"), "160/160, by number")

    def test_find_in_names_and_towns(self):
        r = run([("click", b("MAIN", "Find...")), ("edit", b("FINDER", "FINDTEXT$"), "ann"),
                 ("click", b("FINDER", "In names"))])
        found = [row for row in by_name(ROWS) if "ANN" in row[1].upper()]
        self.assertEqual(string_var(r, "STATUS$"), f"{len(found)}/160, by name found")
        self.assertEqual(page(r), [row[1] for row in found[:13]])
        r = run([("click", b("MAIN", "Find...")), ("edit", b("FINDER", "FINDTEXT$"), "LEEDS"),
                 ("click", b("FINDER", "In towns"))])
        self.assertEqual(string_var(r, "STATUS$"),
                         f"{sum(1 for row in ROWS if row[4] == 'Leeds')}/160, by name found")

    def test_add_with_validation_then_save(self):
        add = [("click", b("MAIN", "Add")), ("edit", b("EDITOR", "FNAME$"), "Zed Young"),
               ("edit", b("EDITOR", "FPHONE$"), "01x"), ("click", b("EDITOR", "OK"))]
        r = run(add)
        self.assertEqual(r.alerts, ["Phone: a bad character"])
        fix = [("edit", b("EDITOR", "FPHONE$"), "0161 222 3333"), ("edit", b("EDITOR", "FEMAIL$"), "zed@example.org"),
               ("click", b("EDITOR", "OK")), SAVE]
        r = run(add + fix)
        self.assertEqual(string_var(r, "STATUS$"), "161/161, by name")
        saved = r.cpu.disk.file("CONTACTS.PDB")
        self.assertEqual(pdbcheck.check(saved, sample.CONTACT_TYPE, 200)[0], 0)
        rows = records(saved)
        self.assertEqual(rows[-1], [161, "Zed Young", "0161 222 3333", "zed@example.org", ""])
        self.assertEqual(rows[:160], records(DATA))
        self.assertEqual(r.cpu.disk.file("CONTACTS.BAK"), DATA)
        self.assertIsNone(r.cpu.disk.file("CONTACTS.NEW"))

    def test_required_name(self):
        r = run([("click", b("MAIN", "Add")), ("click", b("EDITOR", "OK"))])
        self.assertEqual(r.alerts, ["Name is required"])

    def test_edit_the_selected_contact(self):
        first = by_name(ROWS)[1]  # the second row
        r = run([("key", DOWN), ("key", RET), ("edit", b("EDITOR", "FTOWN$"), "Zennor"),
                 ("click", b("EDITOR", "OK")), SAVE])
        rows = records(r.cpu.disk.file("CONTACTS.PDB"))
        self.assertEqual(rows[first[0] - 1], [first[0], first[1], first[2], first[3], "Zennor"])
        self.assertEqual(len(rows), 160)

    def test_delete_asks(self):
        victim = by_name(ROWS)[0]
        r = run([("key", DEL), SAVE], answers=[1])  # answers: 0-based buttons (No)
        self.assertEqual(len(records(r.cpu.disk.file("CONTACTS.PDB"))), 160, "No: nothing deleted")
        r = run([("key", DEL), SAVE], answers=[0])
        rows = records(r.cpu.disk.file("CONTACTS.PDB"))
        self.assertEqual(len(rows), 159)
        self.assertNotIn(victim[0], [row[0] for row in rows])
        self.assertEqual([row[0] for row in rows], [row[0] for row in ROWS if row[0] != victim[0]],
                         "the others keep their order")

    def test_recovery_from_an_interrupted_save(self):
        r = run([], files={"CONTACTS.NEW": DATA})
        self.assertEqual(r.alerts, ["Recovered from CONTACTS.NEW: save it"])
        self.assertEqual(string_var(r, "STATUS$"), "160/160, by name *")

    def test_an_unreadable_file_is_not_replaced_silently(self):
        damaged = bytearray(DATA)
        damaged[100] ^= 1
        files = {"CONTACTS.PDB": bytes(damaged)}
        r = run([("click", b("MAIN", "Add")), ("edit", b("EDITOR", "FNAME$"), "New One"),
                 ("click", b("EDITOR", "OK")), SAVE], files=files, answers=[1])
        self.assertEqual(r.alerts[0], "CONTACTS.PDB unreadable (251)")
        self.assertEqual(r.cpu.disk.file("CONTACTS.PDB"), bytes(damaged), "No: the file is untouched")
        r = run([SAVE], files=files, answers=[0])
        self.assertEqual(r.cpu.disk.file("CONTACTS.BAK"), bytes(damaged), "Yes: the old file is kept as .BAK")

    def test_an_unreadable_file_with_a_valid_backup(self):
        # acceptance C8 as the owner ran it: after C6 the disk holds a valid
        # CONTACTS.BAK, so DB LOAD recovers from it (LANGUAGE-SPEC §5.9 order:
        # the file, .NEW, .BAK) instead of starting empty
        damaged = (ROOT / "tests" / "fixtures" / "m10" / "DAMAGED.PDB").read_bytes()
        files = {"CONTACTS.PDB": damaged, "CONTACTS.BAK": DATA}
        r = run([], files=files)
        self.assertEqual(r.alerts, ["Unreadable: loaded CONTACTS.BAK: save it"])
        self.assertEqual(string_var(r, "STATUS$"), "160/160, by name *")
        self.assertEqual(r.cpu.disk.file("CONTACTS.PDB"), damaged, "nothing written without a save")
        self.assertEqual(r.cpu.disk.file("CONTACTS.BAK"), DATA)
        r = run([SAVE], files=files)
        self.assertEqual(r.alerts, ["Unreadable: loaded CONTACTS.BAK: save it"], "no replace question")
        self.assertEqual(r.cpu.disk.file("CONTACTS.PDB"), DATA, "the recovered data saved")
        self.assertEqual(r.cpu.disk.file("CONTACTS.BAK"), damaged, "the damaged file kept as .BAK")
        self.assertIsNone(r.cpu.disk.file("CONTACTS.NEW"))

    def test_quit_with_unsaved_changes(self):
        events = [("click", b("MAIN", "Add")), ("edit", b("EDITOR", "FNAME$"), "Q"), ("click", b("EDITOR", "OK")),
                  QUIT]
        r = run(events, answers=[2])
        self.assertFalse(r.cpu.exited, "Cancel")
        r = run(events, answers=[1])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.disk.file("CONTACTS.PDB"), DATA, "Discard: nothing written")
        r = run(events, answers=[0])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(len(records(r.cpu.disk.file("CONTACTS.PDB"))), 161)


if __name__ == "__main__":
    unittest.main()
