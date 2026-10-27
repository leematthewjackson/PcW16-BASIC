"""LIST / CHOICE rows at or past the item count (owner XAnne, M7 retest,
issues L1, L2 and L5; KNOWN-ISSUES KI-23, KI-24).

Owner observations:
- Unused list rows showed OS text ("» A v1.12") in SHOPLST2, PHONES2, CONTACTS
  and P2EDGE3. The rows vanished as items filled them.
- After CONTACTS deleted an entry, a stale copy of the moved entry stayed in
  the freed row until the program was restarted.

The simulator now draws every visible row from the pointer table, as Rosanne
was seen to do (z80sim ``_list_draw``, ``slot_text``). These tests fail on
the runtime before the repair. That is engineering evidence, not XAnne.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run
from pbas import check_source
from pbas.layout import BIND_CHOICE, BIND_LIST, build_dialog
from toolchain import requires_pasmo

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
FOLDER = "\\PCW\\FOLDER01"
JUNK = z80sim.JUNK_ROW


def objects(src: str, capacity: int = 64) -> dict:
    program = check_source(src, string_capacity=capacity)
    lay = build_dialog(program, program.windows[0], bool(program.menus))
    result = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
    for row in lay.bindings:
        result[row.var_name] = row.number
        if row.kind == BIND_CHOICE:
            result[row.var_name + " label"] = row.spinner
    return result


def run(src, events, capacity=64, **kw):
    o = objects(src, capacity)
    r = guarded_run(src, events=[e(o) if callable(e) else e for e in events], string_capacity=capacity, **kw)
    assert r.violations == [], r.violations
    return r, o


@requires_pasmo
class UnusedRowTests(unittest.TestCase):
    SRC = ('DIM Items$({n}) AS STRING\nDIM Count AS INTEGER\nDIM Entry$ AS STRING\nWINDOW "W", LARGE\n'
           'LIST Pick, Items$, Count, ROWS {rows}\nTEXTBOX Entry$, "Item"\nBUTTON "Add", AddItem\n'
           'BUTTON "Drop", DropLast\nSUB AddItem\nCount = Count + 1\nItems$(Count) = Entry$\nEND SUB\n'
           'SUB DropLast\nCount = Count - 1\nEND SUB\n{start}END\n')

    def rows(self, events, n=10, rows=6, start='Items$(1) = "Bread"\nItems$(2) = "Milk"\nCount = 2\n'):
        src = self.SRC.format(n=n, rows=rows, start=start)
        r, o = run(src, events)
        return r.cpu.list_on_screen(o["PICK"])[0]

    def test_empty_slots_are_blank(self):
        self.assertEqual(self.rows([]), ["Bread", "Milk", "", "", "", ""])
        self.assertEqual(self.rows([], start=""), [""] * 6)  # an empty list

    def test_more_rows_than_elements(self):
        self.assertEqual(self.rows([], n=3, rows=5), ["Bread", "Milk", "", "", ""])

    def test_growth_fills_the_rows(self):
        add = [lambda o: ("edit", o["ENTRY$"], "Eggs"), lambda o: ("click", o["Add"])]
        self.assertEqual(self.rows(add), ["Bread", "Milk", "Eggs", "", "", ""])
        self.assertEqual(self.rows(add * 5)[-1], "Eggs")  # 7 items, 6 rows: all text

    def test_shrinkage_leaves_no_ghost(self):
        # DropLast keeps the old text in Items$(2): the freed row must be blank
        self.assertEqual(self.rows([lambda o: ("click", o["Drop"])]), ["Bread", "", "", "", "", ""])
        self.assertEqual(self.rows([lambda o: ("click", o["Drop"])] * 2), [""] * 6)

    def test_no_row_ever_shows_junk(self):
        events = [lambda o: ("click", o["Drop"]), lambda o: ("edit", o["ENTRY$"], "Tea"),
                  lambda o: ("click", o["Add"]), lambda o: ("pick", o["PICK"], 0)]
        for n, rows in ((1, 2), (2, 12), (20, 12), (120, 5)):
            with self.subTest(n=n, rows=rows):
                start = 'Items$(1) = "Bread"\nCount = 1\n'
                self.assertNotIn(JUNK, self.rows(events, n=n, rows=rows, start=start))


@requires_pasmo
class ExampleListTests(unittest.TestCase):
    def test_contacts_delete_repaints_the_freed_row(self):
        src = (EXAMPLES / "contacts.pbas").read_text()
        data = b"PBCONTACTS1\r\n2\r\nBabbage\r\n2\r\nTuring\r\n1\r\n"
        disk = z80sim.Disk(files={(FOLDER, "CONTACTS.DAT"): data})
        r, o = run(src, [lambda o: ("pick", o["WHO"], 0), lambda o: ("click", o["Delete"])],
                   capacity=32, disk=disk, alert_answers=[0])
        self.assertEqual(r.cpu.list_on_screen(o["WHO"])[0], ["Turing", "", "", "", "", ""])
        self.assertEqual(disk.files[(FOLDER, "CONTACTS.DAT")], data)  # not saved yet: unchanged

    def test_shipped_lists_show_no_junk(self):
        for name, events in (("shopping_list", []), ("phone_book", []),
                             ("shopping_list", [lambda o: ("pick", o["PICK"], 0), lambda o: ("click", o["Remove"])])):
            with self.subTest(name=name, events=len(events)):
                src = (EXAMPLES / f"{name}.pbas").read_text()
                r, o = run(src, events)
                lists = [n for n in o.values() if n in r.cpu.list_rows]
                self.assertTrue(lists)
                for number in lists:
                    self.assertNotIn(JUNK, r.cpu.list_on_screen(number)[0])

    def test_edge_program_second_window(self):
        src = (EXAMPLES.parent / "developer-tests" / "m6p2_edges.pbas").read_text()
        program = check_source(src)
        o1 = objects(src)
        lay2 = build_dialog(program, program.windows[1], bool(program.menus))
        r = guarded_run(src, events=[("click", o1["More"])])
        self.assertEqual(r.violations, [])
        for row in lay2.bindings:
            if row.kind == BIND_LIST:
                self.assertNotIn(JUNK, r.cpu.list_on_screen(row.number)[0])


@requires_pasmo
class ChoiceSlotTests(unittest.TestCase):
    def test_drop_down_slots_past_the_count_are_empty(self):
        src = ('DIM Opts$(6) AS STRING\nDIM N AS INTEGER\nWINDOW "W", LARGE\nCHOICE Opt, Opts$, N, "Pick"\n'
               'BUTTON "Go", Go\nSUB Go\nN = 1\nEND SUB\nOpts$(1) = "One"\nOpts$(2) = "Two"\nOpts$(3) = "Three"\n'
               'N = 3\nOpt = 1\nEND\n')
        for events, n in (([], 3), ([lambda o: ("click", o["Go"])], 1)):
            with self.subTest(count=n):
                r, o = run(src, events)
                drop = o["OPT"]
                self.assertEqual([r.cpu.slot_text(drop, i) for i in range(6)],
                                 ["One", "Two", "Three"][:n] + [""] * (6 - n))


if __name__ == "__main__":
    unittest.main()
