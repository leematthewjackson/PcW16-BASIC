"""M10 Stage C: DB SORT and DB SEARCH (LANGUAGE-SPEC §5.10).

Random databases (written as PDB1 files by the independent encoder of
test_m10_db) are loaded by compiled programs that sort and search them by
every field kind and flag; the index each program builds must be exactly
the one a Python model of the contract builds (stable sort; DESC keeps equal
keys in element order; NOCASE folds a-z only; STRING order is unsigned
bytes with a prefix first; search = substring, in element order). Every run
is checked by the memory guard. Simulator evidence only.
"""
from __future__ import annotations

import random
import struct
import unittest
from fractions import Fraction

from memguard import guarded_run
from pbas import SourceError, check_source, generate
from pbas.real import pack, unpack
from test_m10_db import F, crc16, pdb, files_of
from toolchain import requires_pasmo
import z80sim

ITEM = """TYPE Item
    Id AS INTEGER
    Name AS STRING * 12
    Qty AS INTEGER
    Price AS REAL
END TYPE
"""
ITEM_SIG = "ID:I;NAME:S12;QTY:I;PRICE:R"
ITEM_SIZE = 2 + 13 + 2 + 5


def item(pid: int, name: bytes, qty: int, price) -> bytes:
    return struct.pack("<h", pid) + name.ljust(13, b"\0") + struct.pack("<h", qty) + pack(price)


def fold(b: bytes) -> bytes:
    return bytes(c - 32 if 97 <= c <= 122 else c for c in b)


def model_sort(rows, key, desc=False, nocase=False):
    keyed = []
    for i, row in enumerate(rows, 1):
        k = row[key]
        if nocase:
            k = fold(k)
        keyed.append((k, i))
    if desc:
        # stable descending: equal keys keep element order
        return [i for _, i in sorted(keyed, key=lambda t: (_neg(t[0]), t[1]))]
    return [i for _, i in sorted(keyed, key=lambda t: (t[0], t[1]))]


class _Desc:
    def __init__(self, v):
        self.v = v

    def __lt__(self, other):
        return self.v > other.v

    def __eq__(self, other):
        return self.v == other.v


def _neg(v):
    return _Desc(v)


def model_search(rows, text: bytes, nocase=False):
    if nocase:
        text = fold(text)
    return [i for i, row in enumerate(rows, 1) if text in (fold(row["name"]) if nocase else row["name"])]


def random_rows(rnd, n):
    alphabet = b"abcABC xyz-Z09{`@["  # the neighbours of a-z / A-Z must not fold
    rows = []
    for i in range(n):
        name = bytes(rnd.choice(alphabet) for _ in range(rnd.randint(0, 12)))
        if rows and rnd.random() < 0.2:
            name = rnd.choice(rows)["name"]  # duplicates test stability
        qty = rnd.choice([rnd.randint(-40, 40), rnd.randint(-32768, 32767)])
        price = Fraction(rnd.randint(-5000, 5000), rnd.choice([1, 4, 100]))
        if rnd.random() < 0.15:
            price = rnd.choice([0, 1, -1, Fraction(1, 2), Fraction(-1, 2)])  # zero, signs, near ties
        rows.append({"id": i + 1, "name": name, "qty": qty, "price": unpack(pack(price))})
    return rows


def database(rows) -> bytes:
    return pdb([item(r["id"], r["name"], r["qty"], r["price"]) for r in rows], ITEM_SIZE, ITEM_SIG,
               len(rows) + 1)


def print_index(var: str, count: str) -> str:
    """MESSAGE the index's entries count at a time, 12 per line."""
    return f"""S$ = ""
J = 0
FOR I = 1 TO {count}
    S$ = S$ + STR$({var}(I)) + " "
    J = J + 1
    IF J = 12 THEN
        MESSAGE S$
        S$ = ""
        J = 0
    END IF
NEXT I
MESSAGE S$ + "."
"""


def parse_index(alerts) -> list[int]:
    text = " ".join(alerts)
    assert text.endswith("."), text
    return [int(x) for x in text[:-1].split()]


def run(src, files, legacy=False):
    disk = z80sim.Disk(files={(F, k): v for k, v in files.items()})
    r = guarded_run(src, disk=disk, max_steps=400_000_000,
                    build_options={"legacy_file_safety": True} if legacy else None)
    assert r.violations == [], r.violations[:5]
    return r


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> str:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return str(caught.exception)

    def test_rules(self):
        base = ITEM + "DIM T(9) AS Item BANKED\nDIM O(9) AS INTEGER\nDIM N AS INTEGER\nDIM F AS INTEGER\n"
        cases = {
            "DB SORT T, N, O, Colour\nEND\n": "TYPE ITEM has no field COLOUR; its fields are ID, NAME, QTY, PRICE",
            "DB SORT T, N, N, Name\nEND\n": "fills an index: give an INTEGER array",
            "DIM B(9) AS INTEGER BANKED\nDB SORT T, N, B, Name\nEND\n": "a BANKED index is not supported",
            "DB SORT T, N, O, Qty, NOCASE\nEND\n": "NOCASE applies to a STRING field",
            "DB SORT T, N, O, Name, DESC, DESC\nEND\n": "DB SORT takes DESC, NOCASE or KEEP here, got DESC",
            "DB SEARCH T, N, O, F, Qty, \"1\"\nEND\n": "a text search needs a STRING field",
            "DB SEARCH T, N, O, F, Name, 5\nEND\n": "the text to find is a STRING",
            "DB SEARCH T, N, O, 3, Name, \"a\"\nEND\n": "give a plain INTEGER variable",
            "DB SEARCH T, N, O, F, Name, \"a\", DESC\nEND\n": "DB SEARCH takes NOCASE here",
        }
        for body, message in cases.items():
            with self.subTest(body=body):
                self.assertIn(message, self.reject(base + body))


@requires_pasmo
class ModelTests(unittest.TestCase):
    SORTS = [("Name", "name", ""), ("Name", "name", ", DESC"), ("Name", "name", ", NOCASE"),
             ("Name", "name", ", DESC, NOCASE"), ("Qty", "qty", ""), ("Qty", "qty", ", DESC"),
             ("Price", "price", ""), ("Price", "price", ", DESC"), ("Id", "id", ", DESC")]

    def program(self, cap: int, statements: str) -> str:
        return ITEM + f"""DIM T({cap}) AS Item BANKED
DIM O({cap}) AS INTEGER
DIM N AS INTEGER
DIM F AS INTEGER
DIM I AS INTEGER
DIM J AS INTEGER
DIM S$ AS STRING
DB LOAD T, N, "ITEMS.PDB"
""" + statements + "END\n"

    def test_sorts_against_the_model(self):
        rnd = random.Random(1010)
        for n in (0, 1, 2, 7, 40):
            rows = random_rows(rnd, n)
            body = ""
            for field, _, flags in self.SORTS:
                body += f"DB SORT T, N, O, {field}{flags}\n" + print_index("O", "N")
            r = run(self.program(max(n, 1), body), {"ITEMS.PDB": database(rows)})
            chunks, current = [], []
            for alert in r.alerts:
                current.append(alert)
                if alert.endswith("."):
                    chunks.append(parse_index(current))
                    current = []
            self.assertEqual(len(chunks), len(self.SORTS))
            for (field, key, flags), got in zip(self.SORTS, chunks):
                with self.subTest(n=n, field=field, flags=flags):
                    want = model_sort(rows, key, "DESC" in flags, "NOCASE" in flags)
                    self.assertEqual(got, want)

    def test_searches_against_the_model(self):
        rnd = random.Random(77)
        rows = random_rows(rnd, 40)
        texts = [b"", b"a", b"A", b"ab", b"z09", b"x", b"abcABCxyz-Z09q", b" "]
        body = ""
        cases = []
        for text in texts:
            for nocase in (False, True):
                lit = '"' + text.decode() + '"'
                body += f"DB SEARCH T, N, O, F, Name, {lit}{', NOCASE' if nocase else ''}\n"
                body += "MESSAGE STR$(F)\n" + print_index("O", "F")
                cases.append((text, nocase))
        r = run(self.program(40, body), {"ITEMS.PDB": database(rows)})
        alerts = list(r.alerts)
        for text, nocase in cases:
            with self.subTest(text=text, nocase=nocase):
                found = int(alerts.pop(0))
                current = []
                while True:
                    a = alerts.pop(0)
                    current.append(a)
                    if a.endswith("."):
                        break
                want = model_search(rows, text, nocase)
                self.assertEqual(found, len(want))
                self.assertEqual(parse_index(current), want)

    def test_search_text_from_an_expression(self):
        rows = random_rows(random.Random(5), 20)
        body = ('S$ = "AB"\nDB SEARCH T, N, O, F, Name, LCASE$(LEFT$(S$, 1)), NOCASE\nMESSAGE STR$(F)\n'
                'DB SEARCH T, N, O, F, Name, T(3).Name\nMESSAGE STR$(F)\n')
        r = run(self.program(20, body), {"ITEMS.PDB": database(rows)})
        self.assertEqual(r.alerts, [str(len(model_search(rows, b"a", True))),
                                    str(len(model_search(rows, rows[2]["name"])))])

    def test_the_index_must_hold_the_count(self):
        rows = random_rows(random.Random(9), 6)
        src = ITEM + """DIM T(6) AS Item BANKED
DIM O(5) AS INTEGER
DIM N AS INTEGER
DIM F AS INTEGER
DB LOAD T, N, "ITEMS.PDB"
N = 5
DB SORT T, N, O, Qty
MESSAGE "five"
N = 6
DB SEARCH T, N, O, F, Name, "q"
END
"""
        r = run(src, {"ITEMS.PDB": database(rows)})
        self.assertEqual(r.alerts, ["five", "Runtime error: index out of range at line 16"])

    def test_sort_leaves_records_and_entries_after_count(self):
        rows = random_rows(random.Random(3), 8)
        data = database(rows)
        src = ITEM + """DIM T(8) AS Item BANKED
DIM O(10) AS INTEGER
DIM N AS INTEGER
DB LOAD T, N, "ITEMS.PDB"
O(9) = 99
O(10) = -4
DB SORT T, N, O, Name, DESC
DB SAVE T, N, "ITEMS.PDB"
MESSAGE STR$(O(9)) + STR$(O(10)) + STR$(IOERR)
END
"""
        r = run(src, {"ITEMS.PDB": data})
        self.assertEqual(r.alerts, ["99-40"])
        self.assertEqual(files_of(r)["ITEMS.PDB"], data)

    def test_keep_sorts_the_entries_already_there(self):
        rnd = random.Random(42)
        rows = random_rows(rnd, 30)
        for r in rows:  # few distinct names, so the second key decides often
            r["name"] = rnd.choice([b"b", b"A", b"a", b"bb"])
        body = ("DB SORT T, N, O, Qty\nDB SORT T, N, O, Name, KEEP\n" + print_index("O", "N")
                + 'DB SEARCH T, N, O, F, Name, "b"\nDB SORT T, F, O, Price, DESC, KEEP\n'
                + print_index("O", "F"))
        r = run(self.program(30, body), {"ITEMS.PDB": database(rows)})
        text = " ".join(r.alerts)
        first, second = text.split(".", 1)
        by_qty = model_sort(rows, "qty")
        two_key = sorted(by_qty, key=lambda i: rows[i - 1]["name"])  # stable: qty within name
        self.assertEqual([int(x) for x in first.split()], two_key)
        found = model_search(rows, b"b")
        want = sorted(found, key=lambda i: _neg(rows[i - 1]["price"]))
        self.assertEqual([int(x) for x in second.rstrip(".").split()], want)

    def test_keep_checks_the_entries(self):
        rows = random_rows(random.Random(8), 4)
        for n, bad in (("1", "0"), ("1", "5"), ("3", "7")):
            with self.subTest(n=n, bad=bad):
                body = f"O(1) = 2\nO(2) = 1\nO(3) = 3\nO({n}) = {bad}\nN = {n}\nDB SORT T, N, O, Qty, KEEP\nMESSAGE \"ok\"\n"
                r = run(self.program(4, body), {"ITEMS.PDB": database(rows)})
                self.assertEqual(r.alerts, ["Runtime error: index out of range at line 20"])

    def test_a_string_field_without_its_nul(self):
        # A file written elsewhere may fill a STRING field with no NUL: the
        # key is the field's bytes only (the next field is not read as text).
        rows = [{"id": 1, "name": b"b" * 13, "qty": 0x4141, "price": 0},
                {"id": 2, "name": b"b" * 13, "qty": 0x2020, "price": 0},
                {"id": 3, "name": b"b" * 12, "qty": 0, "price": 0}]
        data = pdb([struct.pack("<h", r["id"]) + r["name"].ljust(13, b"\0") + struct.pack("<h", r["qty"])
                    + pack(r["price"]) for r in rows], ITEM_SIZE, ITEM_SIG, 4)
        body = ("DB SORT T, N, O, Name\nMESSAGE STR$(O(1)) + STR$(O(2)) + STR$(O(3))\n"
                "DB SORT T, N, O, Name, DESC\nMESSAGE STR$(O(1)) + STR$(O(2)) + STR$(O(3))\n")
        # first a longer field of another database, so the key buffer holds
        # text past 13 bytes
        other = ("TYPE Long\n    Id AS INTEGER\n    Text AS STRING * 60\nEND TYPE\n"
                 "DIM L(2) AS Long BANKED\nDIM LN AS INTEGER\nDB NEW L, LN\nDB NEW L, LN\n"
                 'L(1).Text = STRING$(60, 99)\nL(2).Text = STRING$(60, 99)\nDB SORT L, LN, O, Text\n')
        body += 'DB SEARCH T, N, O, F, Name, "bc"\nMESSAGE STR$(F)\n'
        # the code the owner accepted loads such a file; M14's DB LOAD refuses it (251,
        # M14-DEFECT-REGISTER F4), so the sort's own guard is checked with the accepted code
        r = run(self.program(3, other + body), {"ITEMS.PDB": data}, legacy=True)
        self.assertEqual(r.alerts, ["312", "123", "0"])
        r = run(self.program(3, 'MESSAGE STR$(IOERR) + " " + STR$(N)\n'), {"ITEMS.PDB": data})
        self.assertEqual(r.alerts, ["251 0"])

    def test_measure_250_records(self):
        """The largest index: 250 records (the resident array limit)."""
        rnd = random.Random(250)
        rows = random_rows(rnd, 250)
        body = 'DB SORT T, N, O, Name, NOCASE\nMESSAGE STR$(O(1)) + " " + STR$(O(250))\n'
        r = run(self.program(250, body), {"ITEMS.PDB": database(rows)})
        want = model_sort(rows, "name", nocase=True)
        self.assertEqual(r.alerts, [f"{want[0]} {want[-1]}"])
        copies = sum(1 for entry in r.cpu.os_log if entry[0] == 41)
        # one field read per comparison: 250 + the binary search's (at most
        # sum of ceil(log2 i) for i = 2..250, about 1700)
        self.assertGreater(copies, 250)
        self.assertLess(copies, 250 * 3 + 250 + 1800)


if __name__ == "__main__":
    unittest.main()
