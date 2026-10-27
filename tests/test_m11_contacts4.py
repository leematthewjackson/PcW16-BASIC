"""CONTACTS IV (examples/contacts4.pbas, M11 Stage E2): CONTACTS III rebuilt
on lib/app.pbas, lib/forms.pbas and lib/listview.pbas, with its runtime
sections in a code bank.

* For the same events it writes exactly the files CONTACTS III writes (the
  same TYPE and database statements), including recovery and the refusal to
  replace an unreadable file.
* The list shows aligned columns on the fixed text grid, in the order of a
  Python sort of the same data, with the chosen row inverted; keys and the
  mouse choose rows and redraw only what changed.
* KI-63: CONTACTS III stops with "string too long" when its status passes
  the 24 characters a LABEL shows; CONTACTS IV's status never does.
Simulator evidence only.
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

PATH4 = ROOT / "examples" / "contacts4.pbas"
PATH3 = ROOT / "examples" / "contacts3.pbas"
F = "\\PCW\\FOLDER01"
ROWS = sample.contacts()
DATA = sample.database([sample.record(*r) for r in ROWS], len(ROWS) + 1)
SAVE, QUIT = ("menu", 1, 0), ("menu", 1, 1)
UP, DOWN, PGDN, END_, RET, DEL = 0xE0, 0xE1, 0xE9, 0xE7, 13, 0xE5
STEPS = 900_000_000


def objects(path: Path) -> tuple[dict, tuple]:
    program = check_source(path.read_text(encoding="utf-8"), path=path)
    out, canvas = {}, None
    for window in program.windows:
        lay = build_dialog(program, window, True)
        for obj in lay.objects:
            if obj.kind == "BUTTON":
                out[(window.name, obj.text)] = obj.number
        for row in lay.bindings:
            out[(window.name, row.var_name)] = row.number
        if lay.canvas:
            canvas = lay.canvas
    return out, canvas


B4, CANVAS4 = objects(PATH4)
B3, _ = objects(PATH3)
CX, CY = CANVAS4[1], CANVAS4[2]


def events_for(script, table):
    """Script steps ("click", window, button) / ("edit", window, var, text) -> events."""
    out = []
    for step in script:
        if step[0] == "click":
            out.append(("click", table[(step[1], step[2])]))
        elif step[0] == "edit":
            out.append(("edit", table[(step[1], step[2])], step[3]))
        else:
            out.append(step)
    return out


def run(path, script, files=None, answers=None, banks="all"):
    table = B4 if path == PATH4 else B3
    disk = z80sim.Disk(files={(F, n): d for n, d in (files if files is not None else {"CONTACTS.PDB": DATA}).items()})
    r = guarded_run(path.read_text(encoding="utf-8"), events=events_for(script, table), disk=disk,
                    max_steps=STEPS, alert_answers=answers, path=path,
                    build_options={"runtime_sections": banks} if path == PATH4
                    else {"legacy_file_safety": True})  # M14 (KI-100): CONTACTS III as accepted
    assert r.violations == [], r.violations[:5]
    return r


COLUMNS = ((2, 238), (244, 156), (404, 154))  # (x, room): ListX(K) .. ListX(K + 1) - 4, the last to 558


def fit(text: str, room: int) -> str:
    """lib/listview.pbas ListFit$, independently: the longest start of text
    that is at most room pixels wide (simulator font-7 model)."""
    n = len(text)
    while n > 0 and z80sim.font7_width(text[:n].encode("latin-1")) > room:
        n -= 1
    return text[:n]


def page(r) -> list[tuple[tuple[str, ...], bool]]:
    """The 13 rows (the texts drawn, left to right, and inverted), replayed
    from the drawing log. Each text must start at one of the columns."""
    rows = [({}, False) for _ in range(13)]
    for entry in r.cpu.draw_log:
        if entry[0] == "direct":
            _, op, x, y, w, h, _ = entry
            if (y - CY) % 16 or h != 16:
                continue
            row = (y - CY) // 16
            if op == 1 and w == 560:
                rows[row] = ({}, False)
            elif op == 4 and w == 560:
                rows[row] = (rows[row][0], not rows[row][1])
        elif entry[0] == "text":
            _, x, y, text, _ = entry
            assert x - CX in [c[0] for c in COLUMNS], entry
            rows[(y - CY) // 16][0][x - CX] = text
    return [(tuple(t for _, t in sorted(ch.items())), inv) for ch, inv in rows]


def row_text(name, phone, town):
    return tuple(fit(t, room) for t, (_, room) in zip((name, phone, town), COLUMNS))


@requires_pasmo
class SameFilesTests(unittest.TestCase):
    """The same events must write the same files as CONTACTS III."""

    def same(self, script, files=None, answers=None):
        three = run(PATH3, script, files, answers)
        four = run(PATH4, script, files, answers)
        names = sorted({k for k in three.cpu.disk.files} | {k for k in four.cpu.disk.files})
        for key in names:
            if not key[1].endswith(".PRG"):
                self.assertEqual(four.cpu.disk.files.get(key), three.cpu.disk.files.get(key), key)
        self.assertEqual(four.cpu.exited, three.cpu.exited)
        return three, four

    def test_add_edit_delete_save(self):
        script = [("click", "MAIN", "Add"), ("edit", "EDITOR", "FNAME$", "Zed Young"),
                  ("edit", "EDITOR", "FPHONE$", "01x"), ("click", "EDITOR", "OK"),
                  ("edit", "EDITOR", "FPHONE$", "0161 222 3333"), ("click", "EDITOR", "OK"),
                  ("key", DOWN), ("key", DOWN), ("key", RET), ("edit", "EDITOR", "FTOWN$", "Leeds"),
                  ("click", "EDITOR", "OK"), ("key", DOWN), ("click", "MAIN", "Delete"), SAVE, QUIT]
        three, four = self.same(script, answers=[0])
        self.assertIn("Phone: a bad character", four.alerts)
        self.assertTrue(four.cpu.exited)
        self.assertEqual(four.cpu.disk.file("CONTACTS.BAK"), DATA)

    def test_recovery_and_refusal(self):
        damaged = (ROOT / "tests" / "fixtures" / "m10" / "DAMAGED.PDB").read_bytes()
        for files, answers in (({"CONTACTS.NEW": DATA}, None), ({"CONTACTS.PDB": damaged, "CONTACTS.BAK": DATA}, None),
                               ({"CONTACTS.PDB": damaged}, [1]), ({"CONTACTS.PDB": damaged}, [0])):
            with self.subTest(files=sorted(files), answers=answers):
                three, four = self.same([SAVE], files, answers)
                if "CONTACTS.BAK" not in files and "CONTACTS.NEW" not in files:
                    self.assertEqual(four.alerts[0], "CONTACTS.PDB: damaged")
                    self.assertEqual(four.alerts[1], "Replace unreadable file?")

    def test_quit_with_unsaved_changes(self):
        add = [("click", "MAIN", "Add"), ("edit", "EDITOR", "FNAME$", "Q"), ("click", "EDITOR", "OK"), QUIT]
        for answer in (0, 1, 2):
            with self.subTest(answer=answer):
                three, four = self.same(add, answers=[answer])
                self.assertEqual(four.cpu.exited, answer != 2)


@requires_pasmo
class BackupGenerationTests(unittest.TestCase):
    """The owner's C8 check (XAnne): CONTACTS.BAK differed from the 160-contact
    fixture at byte 9 (offset 8, the record count's low byte). DB SAVE
    always leaves CONTACTS.BAK = the file that was there before that save
    (runtime rt_db_save, steps 3-5). One save in the session gives the
    fixture back byte for byte; a second save makes the first save's file
    the backup, which differs from the fixture first at exactly byte 9."""

    C1_C7 = [("click", "MAIN", "Sort"), ("click", "MAIN", "Sort"), ("click", "MAIN", "Find..."),
             ("edit", "FINDER", "FINDTEXT$", "a"), ("click", "FINDER", "In names"),
             ("click", "MAIN", "Delete")]

    @staticmethod
    def first_difference(a: bytes, b: bytes) -> int:
        """cmp's report: the 1-based number of the first differing byte."""
        return next(i for i, (x, y) in enumerate(zip(a, b)) if x != y) + 1

    def test_one_save_keeps_the_fixture(self):
        r = run(PATH4, self.C1_C7 + [SAVE, QUIT], answers=[0])
        self.assertEqual(r.cpu.disk.file("CONTACTS.BAK"), DATA)

    def test_a_second_save_moves_the_backup_on_one_generation(self):
        r = run(PATH4, self.C1_C7 + [SAVE, SAVE, QUIT], answers=[0])
        bak, pdb = r.cpu.disk.file("CONTACTS.BAK"), r.cpu.disk.file("CONTACTS.PDB")
        self.assertEqual(self.first_difference(bak, DATA), 9, "as the owner's cmp reported")
        self.assertEqual(bak[8:12], bytes([159, 0, 161, 0]), "159 records, next identifier 161")
        self.assertEqual(bak, pdb, "the two saves wrote the same data")
        self.assertEqual(pdbcheck.check(bak, sample.CONTACT_TYPE, 200)[0], 0, "a valid database")
        self.assertIsNone(r.cpu.disk.file("CONTACTS.NEW"))


@requires_pasmo
class PageTests(unittest.TestCase):
    def test_columns_in_name_order(self):
        r = run(PATH4, [])
        order = sorted(ROWS, key=lambda c: c[1].upper())
        self.assertEqual(page(r), [(row_text(c[1], c[2], c[4]), i == 0) for i, c in enumerate(order[:13])])
        self.assertEqual(string_var(r, "APPSTATUS$"), "160/160 name")

    def test_keys_and_mouse_choose_rows(self):
        r = run(PATH4, [("key", DOWN), ("key", DOWN), ("mdown", CX + 50, CY + 5 * 16 + 3)])
        rows = page(r)
        self.assertEqual([inv for _, inv in rows], [i == 5 for i in range(13)])
        before = len(run(PATH4, [("key", DOWN)]).cpu.texts)
        after = len(run(PATH4, [("key", DOWN), ("key", DOWN)]).cpu.texts)
        self.assertEqual(after - before, 2 * 3, "one key: two rows redrawn, three columns each")

    def test_a_name_too_wide_for_its_column_is_cut_on_screen_only(self):
        wide = "W" * 30
        r = run(PATH4, [("click", "MAIN", "Add"), ("edit", "EDITOR", "FNAME$", wide),
                        ("edit", "EDITOR", "FPHONE$", "0161 222 3333"), ("click", "EDITOR", "OK"), SAVE, QUIT])
        chosen = [row for row, inv in page(r) if inv]
        self.assertEqual(chosen[0][0], "W" * 21, "21 x 11 = 231 <= 238 pixels; 22 would reach the phone column")
        self.assertEqual(chosen[0][1], "0161 222 3333")
        saved = pdbcheck.decode(r.cpu.disk.file("CONTACTS.PDB"), sample.CONTACT_TYPE, 999)
        self.assertIn(wide, [row[1] for row in saved], "the record keeps all 30 characters")

    def test_page_down_and_end_scroll(self):
        r = run(PATH4, [("key", PGDN), ("key", END_)])
        order = sorted(ROWS, key=lambda c: c[1].upper())
        self.assertEqual(page(r)[-1], (row_text(order[-1][1], order[-1][2], order[-1][4]), True))


@requires_pasmo
class StatusTests(unittest.TestCase):
    SCRIPT = [("click", "MAIN", "Sort"), ("click", "MAIN", "Sort"), ("click", "MAIN", "Find..."),
              ("edit", "FINDER", "FINDTEXT$", "a"), ("click", "FINDER", "In names"), ("click", "MAIN", "Delete")]

    def test_ki63_contacts3_stops(self):
        r = run(PATH3, self.SCRIPT, answers=[0])
        self.assertEqual(r.alerts[-1], "Runtime error: string too long at line 54")
        self.assertTrue(r.cpu.exited, "CONTACTS III ends; the unsaved deletion is lost (KI-63)")

    def test_contacts4_status_fits(self):
        r = run(PATH4, self.SCRIPT, answers=[0])
        self.assertFalse([a for a in r.alerts if a.startswith("Runtime error")])
        self.assertFalse(r.cpu.exited)
        self.assertEqual(string_var(r, "APPSTATUS$"), "* 114/159 number found")


if __name__ == "__main__":
    unittest.main()
