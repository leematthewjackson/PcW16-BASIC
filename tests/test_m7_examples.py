"""M7 example programs as independent clients: examples/contacts.pbas,
examples/scicalc.pbas, examples/journal.pbas. Each is built with the options
its header names and driven through the simulator (in-memory disk, scripted
GUI events) under the memory checker. Engineering evidence, not XAnne.
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


def objects(src: str, capacity: int) -> dict:
    program = check_source(src, string_capacity=capacity)
    lay = build_dialog(program, program.windows[0], bool(program.menus))
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


def contacts_file(*entries, magic="PBCONTACTS1", count=None) -> bytes:
    lines = [magic, str(len(entries) if count is None else count)]
    for name, phone in entries:
        lines += [name, phone]
    return "".join(f"{x}\r\n" for x in lines).encode()


@requires_pasmo
class ContactsTests(unittest.TestCase):
    SRC = (EXAMPLES / "contacts.pbas").read_text()
    CAP = 32

    def go(self, files, events, answers=None):
        o = objects(self.SRC, self.CAP)
        disk = z80sim.Disk(files={(FOLDER, k): v for k, v in files.items()})
        evs = [e(o) if callable(e) else e for e in events]
        r = guarded_run(self.SRC, string_capacity=self.CAP, disk=disk, events=evs,
                        alert_answers=answers)
        self.assertEqual(r.violations, [])
        return r, o, {k[1]: v for k, v in disk.files.items()}

    def status(self, r, o):
        return r.cpu.label_text(o["STATUS$"], shown=True)

    def names(self, r, o):
        return r.cpu.list_state(o["WHO"], shown=True)["items"]

    def test_new_book_add_sort_save(self):
        r, o, files = self.go({}, [
            lambda o: ("edit", o["NAME$"], "Turing"), lambda o: ("edit", o["PHONE$"], "01632 960010"),
            lambda o: ("click", o["Add"]),
            lambda o: ("edit", o["NAME$"], "babbage"), lambda o: ("edit", o["PHONE$"], "01632 960002"),
            lambda o: ("click", o["Add"]),
            lambda o: ("edit", o["NAME$"], "Hopper"), lambda o: ("edit", o["PHONE$"], ""),
            lambda o: ("click", o["Add"]),
            lambda o: ("click", o["Save"]),
        ])
        self.assertEqual(self.names(r, o), ["babbage", "Hopper", "Turing"])  # sorted ignoring case
        self.assertEqual(self.status(r, o), "Saved 3 contacts")
        self.assertEqual(files, {"CONTACTS.DAT": contacts_file(("babbage", "01632 960002"), ("Hopper", ""),
                                                               ("Turing", "01632 960010"))})

    def test_load_find_update_delete(self):
        start = contacts_file(("Ada Lovelace", "1"), ("Charles Babbage", "2"), ("Grace Hopper", "3"))
        r, o, files = self.go({"CONTACTS.DAT": start}, [
            lambda o: ("edit", o["NAME$"], "hop"), lambda o: ("click", o["Find"]),
            lambda o: ("edit", o["PHONE$"], "99"), lambda o: ("click", o["Update"]),
            lambda o: ("pick", o["WHO"], 0), lambda o: ("click", o["Delete"]),  # pick counts from 0
            lambda o: ("click", o["Save"]),
        ], answers=[0])  # Delete? -> Delete (answers count from 0)
        self.assertEqual(self.names(r, o), ["Charles Babbage", "Grace Hopper"])
        self.assertEqual(files["CONTACTS.DAT"], contacts_file(("Charles Babbage", "2"), ("Grace Hopper", "99")))
        self.assertNotIn("CONTACTS.TMP", files)

    def test_find_wraps_and_reports_misses(self):
        start = contacts_file(("Ann", "1"), ("Bob", "2"), ("Dan", "3"))
        r, o, _ = self.go({"CONTACTS.DAT": start}, [
            lambda o: ("edit", o["NAME$"], "N"), lambda o: ("click", o["Find"]),  # Ann
            lambda o: ("edit", o["NAME$"], "N"), lambda o: ("click", o["Find"]),  # Dan
            lambda o: ("edit", o["NAME$"], "N"), lambda o: ("click", o["Find"]),  # wraps to Ann
        ])
        self.assertEqual(word(r, "WHO"), 1)
        self.assertEqual(self.status(r, o), "Found 1 of 3")
        r, o, _ = self.go({"CONTACTS.DAT": start}, [
            lambda o: ("edit", o["NAME$"], "zed"), lambda o: ("click", o["Find"])])
        self.assertEqual(self.status(r, o), "Not found")

    def test_recovers_an_interrupted_save(self):
        tmp = contacts_file(("Recovered", "7"))
        r, o, files = self.go({"CONTACTS.TMP": tmp}, [])
        self.assertEqual(self.names(r, o), ["Recovered"])
        self.assertEqual(self.status(r, o), "Recovered unsaved copy")
        self.assertEqual(files, {"CONTACTS.DAT": tmp})

    def test_a_stale_temporary_file_is_ignored_and_replaced(self):
        good = contacts_file(("Kept", "1"))
        r, o, files = self.go({"CONTACTS.DAT": good, "CONTACTS.TMP": b"junk\r\n"},
                              [lambda o: ("click", o["Save"])])
        self.assertEqual(self.names(r, o), ["Kept"])
        self.assertEqual(files, {"CONTACTS.DAT": good})

    def test_damaged_files_are_never_overwritten(self):
        for data, message in ((b"hello\r\n3\r\n", "Not a contacts file"),
                              (contacts_file(count=31), "Not a contacts file"),
                              (contacts_file(("A", "1"), count=2), "Entry 2: file too short"),
                              (contacts_file(("A" * 40, "1")), "Entry 1: bad line"),
                              (contacts_file(("A" * 25, "1")), "Entry 1: name too long")):
            with self.subTest(message=message):
                r, o, files = self.go({"CONTACTS.DAT": data}, [lambda o: ("click", o["Save"])])
                self.assertEqual(self.status(r, o), "Damaged file: not saved")
                self.assertEqual(files, {"CONTACTS.DAT": data})
                r, o, _ = self.go({"CONTACTS.DAT": data}, [])
                self.assertEqual(self.status(r, o), message)

    def test_full_book_and_field_checks(self):
        full = contacts_file(*[(f"P{i:02}", "") for i in range(30)])
        r, o, _ = self.go({"CONTACTS.DAT": full}, [
            lambda o: ("edit", o["NAME$"], "One more"), lambda o: ("click", o["Add"])])
        self.assertEqual(self.status(r, o), "The book is full (30)")
        r, o, _ = self.go({}, [lambda o: ("click", o["Add"])])
        self.assertEqual(self.status(r, o), "Name: 1 to 24 characters")
        r, o, _ = self.go({}, [lambda o: ("click", o["Update"])])
        self.assertEqual(self.status(r, o), "Pick a contact first")

    def test_disk_errors_keep_the_old_file(self):
        good = contacts_file(("Kept", "1"))
        o = objects(self.SRC, self.CAP)
        disk = z80sim.Disk(files={(FOLDER, "CONTACTS.DAT"): good}, faults={146: 0xA3})  # writes: disk full
        r = guarded_run(self.SRC, string_capacity=self.CAP, disk=disk, events=[
            ("edit", o["NAME$"], "New"), ("click", o["Add"]), ("click", o["Save"])])
        self.assertEqual(r.violations, [])
        self.assertEqual(r.cpu.label_text(o["STATUS$"], shown=True), "Save: disk full")
        self.assertEqual(disk.files, {(FOLDER, "CONTACTS.DAT"): good})

    def test_quit_asks_about_unsaved_changes(self):
        add = [lambda o: ("edit", o["NAME$"], "X"), lambda o: ("click", o["Add"]),
               lambda o: ("click", o["Quit"])]
        r, o, files = self.go({}, add, answers=[2])  # Cancel: still running, nothing written
        self.assertFalse(r.cpu.exited)
        self.assertEqual(files, {})
        r, o, files = self.go({}, add, answers=[1])  # Discard
        self.assertTrue(r.cpu.exited)
        self.assertEqual(files, {})
        r, o, files = self.go({}, add, answers=[0])  # Save
        self.assertTrue(r.cpu.exited)
        self.assertEqual(files, {"CONTACTS.DAT": contacts_file(("X", ""))})


@requires_pasmo
class SciCalcTests(unittest.TestCase):
    SRC = (EXAMPLES / "scicalc.pbas").read_text()
    OPS = ["x + y", "x - y", "x * y", "x / y", "x ^ y", "SQR x", "EXP x", "LOG x (natural)", "LOG10 x",
           "SIN x", "COS x", "TAN x", "ATN x"]

    def go(self, events):
        o = objects(self.SRC, 64)
        r = guarded_run(self.SRC, events=[e(o) if callable(e) else e for e in events])
        self.assertEqual(r.violations, [])
        self.assertEqual(r.cpu.alerts, [])  # never a runtime error
        return r, o

    def calc(self, x, op, y="", degrees=False):
        o = objects(self.SRC, 64)
        events = [("edit", o["X$"], x), ("edit", o["Y$"], y), ("drop", o["OP"], self.OPS.index(op))]
        if degrees:
            events.append(("click", o["DEGREES"]))
        r, o = self.go(events + [("click", o["="])])
        return r.cpu.label_text(o["RESULT$"], shown=True)

    def test_results(self):
        cases = [("2", "x + y", "3.5", "= 5.5"), ("1E38", "x + y", "1E38", "result too large"),
                 ("-1.5E38", "x - y", "1E38", "result too large"), ("1E38", "x - y", "1E38", "= 0"),
                 ("7", "x * y", "-6", "= -42"), ("1E20", "x * y", "1E20", "result too large"),
                 ("1", "x / y", "3", "= 0.333333333"), ("1", "x / y", "0", "division by zero"),
                 ("1E30", "x / y", "1E-30", "result too large"), ("2", "x ^ y", "10", "= 1024"),
                 ("2", "x ^ y", "0.5", "= 1.41421356"), ("-8", "x ^ y", "3", "= -512"),
                 ("-8", "x ^ y", "0.5", "negative ^ fraction"), ("0", "x ^ y", "-1", "0 ^ negative"),
                 ("0", "x ^ y", "0", "= 1"), ("10", "x ^ y", "200", "result too large"),
                 ("10", "x ^ y", "-200", "= 0"), ("0.5", "x ^ y", "-200", "result too large"),
                 ("2", "SQR x", "", "= 1.41421356"), ("-4", "SQR x", "", "SQR of a negative"),
                 ("1", "EXP x", "", "= 2.71828183"), ("89", "EXP x", "", "result too large"),
                 ("-200", "EXP x", "", "= 0"), ("10", "LOG x (natural)", "", "= 2.30258509"),
                 ("0", "LOG x (natural)", "", "LOG needs x > 0"), ("1000", "LOG10 x", "", "= 3"),
                 ("0.5", "SIN x", "", "= 0.479425539"), ("1E6", "SIN x", "", "angle too large"),
                 ("1", "ATN x", "", "= 0.785398163"), (" 12x", "SQR x", "", "x is not a number"),
                 ("1", "x + y", "", "y is not a number"), ("1E99", "SQR x", "", "x is not a number")]
        for x, op, y, want in cases:
            with self.subTest(x=x, op=op, y=y):
                self.assertEqual(self.calc(x, op, y), want)

    def test_degrees(self):
        self.assertEqual(self.calc("30", "SIN x", degrees=True), "= 0.5")
        self.assertEqual(self.calc("60", "COS x", degrees=True), "= 0.5")
        self.assertEqual(self.calc("45", "TAN x", degrees=True), "= 1")
        self.assertEqual(self.calc("1", "ATN x", degrees=True), "= 45")
        self.assertEqual(self.calc("90", "TAN x", degrees=True)[:2], "= ")  # finite, no runtime error

    def test_use_swap_store_recall(self):
        o = objects(self.SRC, 64)
        r, o = self.go([("edit", o["X$"], "6"), ("edit", o["Y$"], "7"), ("drop", o["OP"], 2),
                        ("click", o["="]), ("click", o["Store"]), ("click", o["Use"]), ("click", o["Swap"]),
                        ("click", o["Recall"])])
        self.assertEqual(r.cpu.label_text(o["MEM$"], shown=True), "M = 42")
        self.assertEqual(r.cpu.control_text(o["X$"], shown=True), "42")
        self.assertEqual(r.cpu.control_text(o["Y$"], shown=True), "42")
        self.assertEqual(r.cpu.label_text(o["OP label"], shown=True), "x * y")


def lines(*texts) -> bytes:
    return "".join(f"{t}\r\n" for t in texts).encode()


@requires_pasmo
class JournalTests(unittest.TestCase):
    SRC = (EXAMPLES / "journal.pbas").read_text()

    def go(self, files, events, answers=None, max_steps=z80sim.DEFAULT_MAX_STEPS, **disk_kw):
        o = objects(self.SRC, 64)
        disk = z80sim.Disk(files={(FOLDER, k): v for k, v in files.items()}, **disk_kw)
        r = guarded_run(self.SRC, disk=disk, events=[e(o) if callable(e) else e for e in events],
                        alert_answers=answers, max_steps=max_steps)
        self.assertEqual(r.violations, [])
        self.assertEqual([a for a in r.cpu.alerts if a.startswith("Runtime error")], [])
        shown = (r.cpu.label_text(o["WHERE$"], shown=True), r.cpu.label_text(o["STATUS$"], shown=True),
                 r.cpu.control_text(o["TEXT$"], shown=True))
        return shown, {k[1]: v for k, v in disk.files.items()}

    @staticmethod
    def add(text):
        return [lambda o: ("edit", o["TEXT$"], text), lambda o: ("click", o["Add"])]

    def test_new_journal_and_adding(self):
        shown, files = self.go({}, [])
        self.assertEqual(shown, ("0 entries", "New journal", ""))
        shown, files = self.go({}, self.add("Planted the beans") + self.add("  Rain  all day ") + self.add("x"))
        self.assertEqual(shown, ("3 entries", "Added entry 3", ""))
        self.assertEqual(files, {"JOURNAL.TXT": lines("Planted the beans", "  Rain  all day ", "x")})

    def test_browse_find_and_delete(self):
        start = lines("Monday: beans", "Tuesday: rain", "Wednesday: more BEANS", "Thursday: sun")
        shown, _ = self.go({"JOURNAL.TXT": start}, [])
        self.assertEqual(shown, ("4 entries", "9 words in all", ""))  # Survey at start
        nxt = lambda o: ("click", o["Next"])
        prev = lambda o: ("click", o["Prev"])
        self.assertEqual(self.go({"JOURNAL.TXT": start}, [nxt, nxt])[0], ("Entry 2 of 4", "2 words", "Tuesday: rain"))
        self.assertEqual(self.go({"JOURNAL.TXT": start}, [prev])[0][::2], ("Entry 4 of 4", "Thursday: sun"))
        find = [lambda o: ("edit", o["FIND$"], "beans"), lambda o: ("click", o["Find"])]
        self.assertEqual(self.go({"JOURNAL.TXT": start}, find + find)[0],
                         ("Entry 3 of 4", "Found in entry 3", "Wednesday: more BEANS"))
        self.assertEqual(self.go({"JOURNAL.TXT": start}, find * 3)[0][:2], ("4 entries", "No more matches"))
        shown, files = self.go({"JOURNAL.TXT": start}, [nxt, nxt, lambda o: ("click", o["Delete"])], answers=[0])
        self.assertEqual(shown, ("3 entries", "7 words in all", ""))
        self.assertEqual(files, {"JOURNAL.TXT": lines("Monday: beans", "Wednesday: more BEANS", "Thursday: sun")})
        _, files = self.go({"JOURNAL.TXT": start}, [nxt, lambda o: ("click", o["Delete"])], answers=[1])  # Keep
        self.assertEqual(files, {"JOURNAL.TXT": start})

    def test_problems_leave_the_journal_unchanged(self):
        long_line = lines("ok", "y" * 70, "after")
        shown, files = self.go({"JOURNAL.TXT": long_line}, self.add("new"))
        self.assertEqual(shown[1], "Unchanged: line too long")
        self.assertEqual(files, {"JOURNAL.TXT": long_line})
        self.assertEqual(self.go({"JOURNAL.TXT": long_line}, [])[0][:2], ("1 entries", "line too long at 2"))
        start = lines("one")
        shown, files = self.go({"JOURNAL.TXT": start}, self.add("two"), faults={146: 0xA3})
        self.assertEqual(shown[1], "Unchanged: disk full")
        self.assertEqual(files, {"JOURNAL.TXT": start})
        shown, files = self.go({"JOURNAL.TXT": start, "JOURNAL.TMP": b"stale"}, self.add("two"))
        self.assertEqual(files, {"JOURNAL.TXT": lines("one", "two")})
        self.assertEqual(self.go({}, [lambda o: ("click", o["Delete"])])[0][1], "Show an entry first")
        self.assertEqual(self.go({}, [lambda o: ("click", o["Next"])])[0][1], "The journal is empty")

    def test_many_entries_stream_through_the_file(self):
        start = lines(*[f"entry {i} of the long journal" for i in range(1, 401)])
        shown, files = self.go({"JOURNAL.TXT": start}, self.add("the 401st"), max_steps=60_000_000)
        self.assertEqual(shown[:2], ("401 entries", "Added entry 401"))
        self.assertEqual(files["JOURNAL.TXT"], start + lines("the 401st"))


@requires_pasmo
class EdgeProgramTests(unittest.TestCase):
    """developer-tests/m7_edges.pbas: every alert's observed part equals its [expected] part."""

    def test_alerts(self):
        src = (EXAMPLES.parent / "developer-tests" / "m7_edges.pbas").read_text()
        for old in ({}, {"M7EDGE.TMP": b"old", "M7EDGE2.TMP": b"old"}):
            with self.subTest(old_files=bool(old)):
                disk = z80sim.Disk(files={(FOLDER, k): v for k, v in old.items()})
                r = guarded_run(src, disk=disk)
                self.assertEqual(r.violations, [])
                alerts = r.cpu.alerts
                self.assertEqual(len(alerts), 9)
                for alert in alerts[:8]:
                    got, want = alert[4:-1].split(" [")
                    if alert.startswith("E5"):
                        self.assertEqual(got, ("22" if not old else "00") + " / 00000")
                    else:
                        self.assertEqual(got, want)
                line = src.splitlines().index("X = SQR(X)") + 1
                self.assertEqual(alerts[8], f"Runtime error: function argument out of range at line {line}")
                self.assertEqual(disk.files, {})  # every test file removed
                self.assertTrue(r.cpu.exited)


if __name__ == "__main__":
    unittest.main()
