"""M10 Stage A: record TYPEs (LANGUAGE-SPEC §5.8, pbas/records.py).

Front-end rules and the generated Z80 code: field layout, every field type,
whole-record copies, resident and BANKED arrays of records (including the
16K block boundary), procedures, FUNCTION results, LOCAL records, index
errors, and the canonical bytes after a STRING field's NUL. Every run is
checked by the memory guard (tests/memguard.py: writes stay in the right
storage, strings stay terminated). Simulator evidence, not XAnne.
"""
from __future__ import annotations

import unittest

from memguard import guarded_run, string_var
from pbas import SourceError, check_source, generate
from pbas.real import unpack
from pbas.records import Layout
from pbas import ast_nodes as ast
from toolchain import requires_pasmo

CONTACT = """TYPE Contact
    Id AS INTEGER
    Name AS STRING * 40
    Balance AS REAL
    Active AS BOOLEAN
END TYPE
"""


def run(src: str, **kw):
    r = guarded_run(src, **kw)
    assert r.violations == [], r.violations[:5]
    assert not r.cpu.exited or r.cpu.blocks_at_exit == [], f"blocks still held: {r.cpu.blocks_at_exit}"
    return r


def record_bytes(r, name: str, size: int, element: int = 1) -> bytes:
    """A resident record's (or array element's) bytes."""
    region = next(g for g in r.regions if g.name == name)
    start = region.start + (element - 1) * size
    return bytes(r.cpu.mem[start:start + size])


class LayoutTests(unittest.TestCase):
    def layout(self, src):
        from pbas.parser import Parser
        from pbas.lexer import tokenize
        nodes = Parser(tokenize(src + "END\n")).parse()
        return Layout(next(n for n in nodes if isinstance(n, ast.TypeDef)))

    def test_offsets_and_size(self):
        lay = self.layout(CONTACT)
        self.assertEqual({k: v[2] for k, v in lay.fields.items()},
                         {"ID": 0, "NAME": 2, "BALANCE": 43, "ACTIVE": 48})
        self.assertEqual(lay.size, 50)
        self.assertEqual(lay.signature(), "ID:I;NAME:S40;BALANCE:R;ACTIVE:B")

    def test_variables(self):
        p = check_source(CONTACT + "DIM P AS Contact\nDIM L(5) AS Contact\nDIM B(300) AS Contact BANKED\nEND\n")
        v = p.variables
        self.assertEqual((v["P"].type, v["P"].capacity, v["P"].record), ("RECORD", 50, "CONTACT"))
        self.assertEqual((v["P%NAME"].type, v["P%NAME"].capacity, v["P%NAME"].alias), ("STRING", 41, ("P", 2, 50)))
        self.assertEqual((v["L%BALANCE"].length, v["L%BALANCE"].alias), (5, ("L", 43, 50)))
        self.assertTrue(v["B"].banked and v["B%ID"].banked)

    def test_programs_without_records_are_unchanged(self):
        # no TYPE, no RECORDS runtime part (the accepted executables: gate)
        asm = generate(check_source('DIM S$ AS STRING\nS$ = "x"\nEND\n'))
        self.assertIn("PB_RECORDS equ 0", asm)


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> str:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return caught.exception.message

    def test_rules(self):
        cases = {
            "DIM P AS Nothing\nEND\n": "unknown type NOTHING",
            CONTACT + "DIM P AS Contact\nP.Phone = \"1\"\nEND\n":
                "TYPE CONTACT has no field PHONE; its fields are ID, NAME, BALANCE, ACTIVE",
            CONTACT + "DIM N AS INTEGER\nN.Id = 1\nEND\n": "N is not a record, so it has no field ID",
            CONTACT + "DIM P AS Contact\nDIM N AS INTEGER\nN = P\nEND\n": "P is a record of TYPE CONTACT",
            CONTACT + "DIM P AS Contact\nMESSAGE P\nEND\n": "P is a record of TYPE CONTACT",
            CONTACT + "TYPE Other\n    Id AS INTEGER\nEND TYPE\nDIM P AS Contact\nDIM O AS Other\nP = O\nEND\n":
                "a record is copied only from the same TYPE",
            CONTACT + "DIM P AS Contact\nP = 5\nEND\n": "assign a record of the same TYPE",
            "TYPE T\n    S AS STRING\nEND TYPE\nEND\n": "a STRING field states its length",
            "TYPE T\n    S AS STRING * 127\nEND TYPE\nEND\n": "STRING * n holds 1 to 126 characters, got 127",
            "TYPE T\n    N AS INTEGER * 3\nEND TYPE\nEND\n": "* n gives a STRING field its length",
            "TYPE T\n    A AS INTEGER\n    A AS REAL\nEND TYPE\nEND\n": "duplicate field A in TYPE T",
            "TYPE T\n    A AS INTEGER\nEND TYPE\nTYPE T\n    B AS INTEGER\nEND TYPE\nEND\n": "duplicate TYPE T",
            "TYPE T\nEND TYPE\nEND\n": "TYPE T has no fields",
            "TYPE T\n    N$ AS INTEGER\nEND TYPE\nEND\n": "N$ uses $ suffix but is declared INTEGER",
            "TYPE T\n    A AS INTEGER\nEND TYPE\nTYPE U\n    X AS T\nEND TYPE\nEND\n":
                "records inside records are not supported",
            "TYPE T\n" + "".join(f"    S{i} AS STRING * 126\n" for i in range(5)) + "END TYPE\nEND\n":
                "TYPE T is 635 bytes; a record is at most 512 bytes",
            "TYPE T\n    A AS INTEGER\nEND\n": "expected END TYPE to close TYPE T",
            "TYPE T\n    A AS INTEGER\n": "TYPE T without END TYPE",
            CONTACT + "DIM L(3) AS Contact\nL.Id = 1\nEND\n": "L is an array of records: use L(index).ID",
            CONTACT + "DIM P AS Contact\nP(1).Id = 1\nEND\n": "P is a single record, not an array",
            CONTACT + "DIM L(3) AS Contact\nDIM P AS Contact\nP = L\nEND\n": "copy one element",
            CONTACT + "DIM P AS Contact\nDIM Q AS Contact\nP.Name.X = 1\nEND\n": "records inside records are not supported",
            CONTACT + "DIM P AS Contact\nFOR P.Id = 1 TO 3\nNEXT\nEND\n": "",  # parser: FOR needs a name
            CONTACT + "DIM P$ AS Contact\nEND\n": "P$ uses $ suffix but is a record of TYPE CONTACT",
            CONTACT + "DIM P AS Contact\nP.Name = \"" + "x" * 41 + "\"\nEND\n":
                "cannot assign a 41-character literal to P.NAME with capacity 41",
            CONTACT + "DIM P AS Contact\nP.Id = \"x\"\nEND\n": "cannot assign STRING to INTEGER variable P.ID",
        }
        for src, expected in cases.items():
            with self.subTest(src=src.splitlines()[-2:]):
                message = self.reject(src)
                self.assertIn(expected, message)

    def test_type_inside_a_sub(self):
        self.assertIn("TYPE", self.reject("SUB S\nTYPE T\n    A AS INTEGER\nEND TYPE\nEND SUB\nEND\n"))

    def test_banked_reads_count_the_record_copy(self):
        src = CONTACT + ("DIM B(9) AS Contact BANKED\nDIM L(9) AS INTEGER BANKED\n"
                         "B(L(1) + L(2) + L(3)) = B(L(4))\nEND\n")
        self.assertIn("reads 5 BANKED array elements", self.reject(src))

    def test_keyword_field_names(self):
        p = check_source("TYPE T\n    Label AS STRING * 9\n    Text AS INTEGER\nEND TYPE\n"
                         "DIM X AS T\nX.Label = \"a\"\nX.Text = 2\nEND\n")
        self.assertIn("X%LABEL", p.variables)


@requires_pasmo
class RunTests(unittest.TestCase):
    def test_every_field_type_and_copy(self):
        r = run(CONTACT + """DIM P AS Contact
DIM Q AS Contact
P.Id = -12345
P.Name = "Ann Example"
P.Balance = 125.5
P.Active = TRUE
Q = P
P.Name = "changed"
IF Q.Active THEN
    MESSAGE Q.Name + "|" + STR$(Q.Id) + "|" + STR$(Q.Balance) + "|on"
END IF
END
""")
        self.assertEqual(r.alerts, ["Ann Example|-12345|125.5|on"])
        q = record_bytes(r, "Q", 50)
        self.assertEqual(q[0:2], (-12345 & 0xFFFF).to_bytes(2, "little"), "INTEGER little-endian at +0")
        self.assertEqual(q[2:2 + 41], b"Ann Example".ljust(41, b"\0"), "STRING * 40 at +2, zero after the NUL")
        self.assertEqual(unpack(q[43:48]), 125.5, "REAL at +43 (M7 format)")
        self.assertEqual(q[48:50], b"\x01\x00", "BOOLEAN TRUE = 1 (16-bit cell) at +48")

    def test_copy_moves_every_byte(self):
        # the last byte of the record is non-zero, and the copies cover the
        # resident and BANKED paths in both directions
        src = """TYPE Pair
    A AS INTEGER
    B AS INTEGER
END TYPE
DIM X AS Pair
DIM Y AS Pair
DIM L(2) AS Pair
DIM K(2) AS Pair BANKED
X.A = 4660
X.B = -2
L(2) = X
K(2) = L(2)
Y = K(2)
END
"""
        r = run(src)
        want = (4660).to_bytes(2, "little") + (-2 & 0xFFFF).to_bytes(2, "little")
        self.assertEqual(record_bytes(r, "Y", 4), want)
        self.assertEqual(record_bytes(r, "L", 4, 2), want)

    def test_bytes_after_the_nul_are_zero(self):
        # a long value, then a short one: the old characters must not remain
        r = run(CONTACT + """DIM L(2) AS Contact
DIM P AS Contact
P.Name = "a long name of thirty characters"
P.Name = "short"
L(2).Name = "another long text here"
L(2).Name = "x" + "y"
END
""")
        self.assertEqual(record_bytes(r, "P", 50)[2:43], b"short".ljust(41, b"\0"))
        self.assertEqual(record_bytes(r, "L", 50, 2)[2:43], b"xy".ljust(41, b"\0"))

    def test_resident_array_of_records(self):
        r = run(CONTACT + """DIM L(4) AS Contact
DIM I AS INTEGER
DIM S$ AS STRING
FOR I = 1 TO 4
    L(I).Id = I * 100
    L(I).Name = "row" + STR$(I)
NEXT I
L(1) = L(4)
FOR I = 1 TO 4
    S$ = S$ + L(I).Name + "=" + STR$(L(I).Id) + " "
NEXT I
MESSAGE S$
END
""")
        self.assertEqual(r.alerts, ["row4=400 row2=200 row3=300 row4=400 "])

    def test_banked_records_across_a_block_boundary(self):
        # 50-byte records: 327 per 16K block, so 327 is the last of block 1
        # and 328 the first of block 2 (an element never crosses a block end)
        r = run(CONTACT + """DIM B(700) AS Contact BANKED
DIM P AS Contact
B(327).Name = "end of block 1"
B(327).Id = 327
B(328) = B(327)
B(328).Name = "start of block 2"
B(700).Balance = 2.25
P = B(328)
MESSAGE B(327).Name + "/" + P.Name + "/" + STR$(P.Id) + "/" + STR$(B(700).Balance) + "/" + STR$(B(1).Id)
END
""")
        self.assertEqual(r.alerts, ["end of block 1/start of block 2/327/2.25/0"])

    def test_procedures_functions_and_locals(self):
        r = run("""TYPE Item
    Code AS INTEGER
    Label AS STRING * 10
END TYPE
DIM A AS Item
DIM Shelf(3) AS Item BANKED
DIM Out$ AS STRING
SUB Show(X AS Item)
    Out$ = Out$ + X.Label + STR$(X.Code) + ";"
    X.Code = 0
END SUB
FUNCTION Make(C AS INTEGER) AS Item
    LOCAL T AS Item
    T.Code = C * 10
    T.Label = "n" + STR$(C)
    RETURN T
END FUNCTION
SUB Fresh
    LOCAL Z AS Item
    Out$ = Out$ + "[" + Z.Label + STR$(Z.Code) + "]"
    Z.Code = 99
    Z.Label = "dirty"
END SUB
A.Code = 7
A.Label = "seven"
CALL Show(A)
Shelf(2) = Make(4)
CALL Show(Shelf(2))
A = Make(5)
CALL Show(A)
CALL Fresh
CALL Fresh
Out$ = Out$ + STR$(A.Code)
MESSAGE Out$
END
""")
        # a record parameter is a copy: Show's X.Code = 0 does not reach A
        self.assertEqual(r.alerts, ["seven7;n440;n550;[0][0]50"])

    def test_index_errors(self):
        for decl in ("DIM L(3) AS Contact\n", "DIM L(3) AS Contact BANKED\n"):
            with self.subTest(decl=decl):
                r = guarded_run(CONTACT + decl + "DIM N AS INTEGER\nN = 4\nL(N).Id = 1\nEND\n")
                self.assertEqual(r.violations, [])
                self.assertEqual(r.alerts, ["Runtime error: index out of range at line 10"])
                r = guarded_run(CONTACT + decl + "DIM P AS Contact\nDIM N AS INTEGER\nP = L(N)\nEND\n")
                self.assertEqual(r.alerts, ["Runtime error: index out of range at line 10"])

    def test_string_field_overflow_is_an_error(self):
        r = guarded_run(CONTACT + 'DIM P AS Contact\nDIM S$ AS STRING\nS$ = "' + "z" * 30
                        + '"\nP.Name = S$ + S$\nEND\n')
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["Runtime error: string too long at line 10"])
        r = guarded_run(CONTACT + 'DIM L(2) AS Contact BANKED\nDIM S$ AS STRING\nS$ = "' + "z" * 30
                        + '"\nL(2).Name = S$ + S$\nEND\n')
        self.assertEqual(r.alerts, ["Runtime error: string too long at line 10"])


if __name__ == "__main__":
    unittest.main()
