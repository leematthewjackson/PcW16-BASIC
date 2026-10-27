"""M8 benchmark programs as independent clients (examples/contacts_m8.pbas,
examples/scicalc_m8.pbas, examples/records_m8.pbas). Each is built with the
options its header names and driven through the simulator (in-memory disk,
scripted GUI events, model 16K blocks) under the memory checker.
Engineering evidence, not XAnne.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from memguard import guarded_run
import test_m7_examples as m7
from test_m7_examples import FOLDER, objects, word
import z80sim
from toolchain import requires_pasmo

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
BOOK = 1  # menu title 1 ("Book"; title 0 is Rosanne's Tasks menu); Save 0, Quit 1


def book_file(*entries, magic="PBCONTBOOK1", count=None) -> bytes:
    lines = [magic, str(len(entries) if count is None else count)]
    for entry in entries:
        lines += list(entry)
    return "".join(f"{x}\r\n" for x in lines).encode()


def person(i: int) -> tuple[str, str, str]:
    return (f"Person {i:03}", f"01632 {i:06}", f"person.{i:03}@example.org")


@requires_pasmo
class ContactsBookTests(unittest.TestCase):
    SRC = (EXAMPLES / "contacts_m8.pbas").read_text()
    CAP = 41

    def go(self, files, events, answers=None, **kw):
        o = objects(self.SRC, self.CAP)
        disk = z80sim.Disk(files={(FOLDER, k): v for k, v in files.items()})
        evs = [e(o) if callable(e) else e for e in events]
        r = guarded_run(self.SRC, string_capacity=self.CAP, disk=disk, events=evs,
                        alert_answers=answers, **kw)
        self.assertEqual(r.violations, [])
        return r, o, {k[1]: v for k, v in disk.files.items()}

    def status(self, r, o):
        return r.cpu.label_text(o["STATUS$"], shown=True)

    def rows(self, r, o):
        return r.cpu.list_state(o["WHO"], shown=True)["items"]

    def field(self, r, o, name):
        return r.cpu.control_text(o[name], shown=True)

    def test_header_and_size(self):
        self.assertIn("' Build with --string-capacity 41", self.SRC)
        self.assertIn("DIM Emails$(200) AS STRING * 40 BANKED", self.SRC)

    def test_a_book_of_150_loads_pages_and_finds(self):
        start = book_file(*[person(i) for i in range(1, 151)])
        r, o, files = self.go({"CONTBOOK.DAT": start}, [
            lambda o: ("click", o["Next"]),
            lambda o: ("edit", o["NAME$"], "person 140"), lambda o: ("click", o["Find"]),
        ])
        self.assertEqual(self.rows(r, o), [person(i)[0] for i in range(139, 145)])  # page 24: 139..144
        self.assertEqual(word(r, "WHO"), 2)
        self.assertEqual(word(r, "SEL"), 140)
        self.assertEqual(self.field(r, o, "EMAIL$"), "person.140@example.org")
        self.assertEqual(self.field(r, o, "PHONE$"), "01632 000140")
        self.assertEqual(self.status(r, o), "Found 140 of 150")
        self.assertEqual(files, {"CONTBOOK.DAT": start})  # nothing written
        self.assertEqual(len(r.cpu.owned), 3)  # one block per BANKED array

    def test_paging_limits(self):
        start = book_file(*[person(i) for i in range(1, 8)])
        r, o, _ = self.go({"CONTBOOK.DAT": start}, [lambda o: ("click", o["Prev"])])
        self.assertEqual(self.status(r, o), "First page")
        r, o, _ = self.go({"CONTBOOK.DAT": start}, [lambda o: ("click", o["Next"])])
        self.assertEqual(self.rows(r, o), [person(7)[0]])
        self.assertEqual(self.status(r, o), "Page 2")
        r, o, _ = self.go({"CONTBOOK.DAT": start}, [lambda o: ("click", o["Next"]), lambda o: ("click", o["Next"])])
        self.assertEqual(self.status(r, o), "Last page")

    def test_add_places_in_order_and_save_round_trips(self):
        start = book_file(*[person(i) for i in range(1, 41)])
        r, o, files = self.go({"CONTBOOK.DAT": start}, [
            lambda o: ("edit", o["NAME$"], "person 020a"), lambda o: ("edit", o["PHONE$"], "5"),
            lambda o: ("edit", o["EMAIL$"], "x" * 40), lambda o: ("click", o["Add"]),
            lambda o: ("edit", o["NAME$"], "Aardvark"), lambda o: ("edit", o["PHONE$"], ""),
            lambda o: ("edit", o["EMAIL$"], ""), lambda o: ("click", o["Add"]),
            lambda o: ("menu", BOOK, 0),
        ])
        want = [("Aardvark", "", "")] + [person(i) for i in range(1, 21)] + [("person 020a", "5", "x" * 40)] \
            + [person(i) for i in range(21, 41)]
        self.assertEqual(files, {"CONTBOOK.DAT": book_file(*want)})
        self.assertEqual(self.status(r, o), "Saved 42 contacts")

    def test_update_moves_down_and_delete(self):
        start = book_file(("Ann", "1", "a@x"), ("Bob", "2", "b@x"), ("Cat", "3", "c@x"), ("Dan", "4", "d@x"))
        r, o, files = self.go({"CONTBOOK.DAT": start}, [
            lambda o: ("pick", o["WHO"], 0), lambda o: ("edit", o["NAME$"], "Coe"), lambda o: ("click", o["Update"]),
            lambda o: ("pick", o["WHO"], 1), lambda o: ("click", o["Delete"]),
            lambda o: ("menu", BOOK, 0),
        ], answers=[0])
        self.assertEqual(files["CONTBOOK.DAT"], book_file(("Bob", "2", "b@x"), ("Coe", "1", "a@x"), ("Dan", "4", "d@x")))

    def test_full_book_and_field_checks(self):
        full = book_file(*[person(i) for i in range(1, 201)])
        r, o, _ = self.go({"CONTBOOK.DAT": full}, [
            lambda o: ("edit", o["NAME$"], "X"), lambda o: ("click", o["Add"])])
        self.assertEqual(self.status(r, o), "The book is full (200)")
        r, o, _ = self.go({}, [lambda o: ("edit", o["NAME$"], "X"), lambda o: ("edit", o["PHONE$"], "1" * 21),
                               lambda o: ("click", o["Add"])])
        self.assertEqual(self.status(r, o), "Phone: up to 20 chars")  # the E-mail box itself stops at 40
        r, o, _ = self.go({"CONTBOOK.DAT": book_file(count=201)}, [])
        self.assertEqual(self.status(r, o), "Not a contacts file")
        r, o, _ = self.go({"CONTBOOK.DAT": book_file(("A" * 25, "1", "e"))}, [])
        self.assertEqual(self.status(r, o), "Entry 1: error 243")  # too long for STRING * 24

    def test_not_enough_memory_stops_at_start(self):
        r, o, files = self.go({}, [], free_blocks=2)
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.alerts, ["Runtime error: not enough free memory for BANKED arrays at line 21"])
        self.assertEqual(r.cpu.blocks_at_exit, [])

    def test_quit_releases_the_blocks(self):
        r, o, files = self.go({}, [lambda o: ("menu", BOOK, 1)])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.blocks_at_exit, [])
        self.assertEqual(files, {})


@requires_pasmo
class SciCalcStatsTests(m7.SciCalcTests):
    """The M8 calculator: every M7 calculator case (inherited) plus statistics."""
    SRC = (EXAMPLES / "scicalc_m8.pbas").read_text()
    CAP = 24
    OPS = m7.SciCalcTests.OPS + ["add x to data", "count of data", "mean of data", "std dev of data",
                                 "clear data"]

    def go(self, events):
        o = objects(self.SRC, self.CAP)
        r = guarded_run(self.SRC, string_capacity=self.CAP, events=[e(o) if callable(e) else e for e in events])
        self.assertEqual(r.violations, [])
        self.assertEqual(r.cpu.alerts, [])  # never a runtime error
        return r, o

    def calc(self, x, op, y="", degrees=False, before=()):
        o = objects(self.SRC, self.CAP)
        events = list(before) + [("edit", o["X$"], x), ("edit", o["Y$"], y), ("drop", o["OP"], self.OPS.index(op))]
        if degrees:
            events.append(("click", o["DEGREES"]))
        r, o = self.go(events + [("click", o["="])])
        return r.cpu.label_text(o["RESULT$"], shown=True)

    def adds(self, *values):
        o = objects(self.SRC, self.CAP)
        out = []
        for v in values:
            out += [("edit", o["X$"], v), ("drop", o["OP"], self.OPS.index("add x to data")), ("click", o["="])]
        return out

    def test_header(self):
        self.assertIn("' Build with --string-capacity 24", self.SRC)

    def test_statistics(self):
        data = self.adds("2", "4", "4", "4", "5", "5", "7", "9")
        self.assertEqual(self.calc("", "count of data", before=data), "n = 8")
        self.assertEqual(self.calc("", "mean of data", before=data), "= 5")
        self.assertEqual(self.calc("", "std dev of data", before=data), "= 2.13808994")  # sqrt(32 / 7)
        self.assertEqual(self.calc("", "std dev of data", before=self.adds("1E15", "-1E15")), "= 1.41421356E+15")
        self.assertEqual(self.calc("1E16", "add x to data"), "too large for data")
        self.assertEqual(self.calc("", "mean of data"), "no data")
        self.assertEqual(self.calc("", "std dev of data", before=self.adds("3")), "needs 2 values")
        self.assertEqual(self.calc("", "clear data", before=data), "data cleared")
        self.assertEqual(self.calc("", "count of data", before=data + [lambda o: ("drop", o["OP"], self.OPS.index("clear data")),
                                      lambda o: ("click", o["="])]), "no data")
        self.assertEqual(self.calc("x", "add x to data"), "x is not a number")


REGIONS = ["North", "South", "East", "West", "Central", "Islands", "Harbour"]


def sales(n: int):
    """n sales with distinct amounts (no ties for the sort to order freely)."""
    out = []
    for i in range(1, n + 1):
        region = REGIONS[i * 3 % len(REGIONS)]
        qty = i % 13 + 1
        price = (i * 37 % 1000) / 4 + i / 8192  # exact in binary; distinct amounts
        out.append((region, qty, price))
    return out


def sales_file(rows, magic="PBSALES1") -> bytes:
    def num(x):
        return f"{x:.9g}" if x != int(x) else str(int(x))
    return "".join(f"{x}\r\n" for x in [magic] + [f"{r};{q};{num(p)}" for r, q, p in rows]).encode()


@requires_pasmo
class RecordsTests(unittest.TestCase):
    SRC = (EXAMPLES / "records_m8.pbas").read_text()

    def go(self, files, **kw):
        disk = z80sim.Disk(files={(FOLDER, k): v for k, v in files.items()})
        r = guarded_run(self.SRC, disk=disk, max_steps=400_000_000, **kw)
        self.assertEqual(r.violations, [])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.blocks_at_exit, [])
        return r, {k[1]: v for k, v in disk.files.items()}

    def test_report_of_600_sales(self):
        rows = sales(600)
        r, files = self.go({"SALES.DAT": sales_file(rows)})
        self.assertEqual(r.cpu.alerts, [f"Report written: 600 sales, {len(REGIONS)} regions"])
        lines = files["REPORT.TXT"].decode().split("\r\n")
        self.assertEqual(lines[0], f"Sales report: 600 sales in {len(REGIONS)} regions")
        order = []
        for reg, _, _ in rows:
            if reg not in order:
                order.append(reg)
        for k, reg in enumerate(order, 1):
            mine = [(q, p) for g, q, p in rows if g == reg]
            head = f"{reg}: {len(mine)} sales, {sum(q for q, _ in mine)} items, "
            self.assertTrue(lines[k].startswith(head), (lines[k], head))
            total = float(lines[k][len(head):])
            self.assertAlmostEqual(total, sum(q * p for q, p in mine), delta=abs(total) * 1e-7)
        top = sorted(rows, key=lambda t: -t[1] * t[2])[:10]
        for k, (reg, q, p) in enumerate(top, 1):
            line = lines[len(order) + 1 + k]
            self.assertTrue(line.startswith(f"{k}. {reg} {q} for "), line)
            self.assertAlmostEqual(float(line.rsplit(" ", 1)[1]), q * p, delta=q * p * 1e-7)
        self.assertEqual(files["SALES.DAT"], sales_file(rows))  # input untouched
        self.assertEqual(len(r.cpu.owned), 0)

    def test_bad_lines_write_no_report(self):
        good = sales(5)
        cases = [(b"hello\r\n", "SALES.DAT line 1: not a sales file"),
                 (sales_file(good)[:-2] + b"\r\nNorth;-1;3\r\n", "SALES.DAT line 7: bad quantity"),
                 (sales_file(good) + b"North;1.5;3\r\n", "SALES.DAT line 7: bad quantity"),
                 (sales_file(good) + b"North;40000;3\r\n", "SALES.DAT line 7: bad quantity"),
                 (sales_file(good) + b"North;2;x\r\n", "SALES.DAT line 7: bad price"),
                 (sales_file(good) + b"North;2;2E9\r\n", "SALES.DAT line 7: bad price"),
                 (sales_file(good) + b";2;3\r\n", "SALES.DAT line 7: region must be 1 to 12 chars"),
                 (sales_file(good) + b"ThirteenChars;2;3\r\n", "SALES.DAT line 7: region must be 1 to 12 chars"),
                 (sales_file(good) + b"North 2 3\r\n", "SALES.DAT line 7: region must be 1 to 12 chars"),
                 (sales_file(good) + b"North;2\r\n", "SALES.DAT line 7: needs region;quantity;price"),
                 (sales_file([(f"R{i}", 1, 1) for i in range(21)]), "SALES.DAT line 22: more than 20 regions")]
        for data, want in cases:
            with self.subTest(want=want):
                r, files = self.go({"SALES.DAT": data})
                self.assertEqual(r.cpu.alerts, [want])
                self.assertNotIn("REPORT.TXT", files)
        r, files = self.go({})
        self.assertEqual(r.cpu.alerts, ["SALES.DAT line 0: cannot open: error 2"])

    def test_not_enough_memory(self):
        r, files = self.go({"SALES.DAT": sales_file(sales(3))}, free_blocks=5)
        self.assertEqual(r.cpu.alerts, ["Runtime error: not enough free memory for BANKED arrays at line 19"])
        self.assertEqual(files, {"SALES.DAT": sales_file(sales(3))})


if __name__ == "__main__":
    unittest.main()
