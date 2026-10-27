"""M9 Stage C — TEXT buffers (LANGUAGE-SPEC §5.6) on the simulator.

A TEXT buffer keeps a document's bytes exactly (CR, LF, NUL, bytes over
127), in owned 16K blocks mapped at #8000 by the runtime. The tests compare
the compiled runtime with a small Python reference model of the same
contract (TextModel below): random edit sequences, compiled as BASIC, must
leave exactly the bytes the model predicts. Simulator evidence only.
"""
from __future__ import annotations

import random
import unittest

import z80sim
from memguard import guarded_run
from pbas import SourceError, check_source, generate
from toolchain import requires_pasmo

F = "\\PCW\\FOLDER01"
POS_ERR = "Runtime error: text position out of range at line {}"
FULL_ERR = "Runtime error: the TEXT buffer is full at line {}"
BRK_ERR = "Runtime error: TEXT INSERT text has a line break at line {}"


class TextModel:
    """The TEXT contract in Python: a line ends at LF; a CR right before
    the LF belongs to the end; the last line has no end."""

    def __init__(self, data: bytes = b""):
        self.b = bytearray(data)
        i = data.find(b"\n")
        self.style_crlf = i < 0 or (i > 0 and data[i - 1] == 13)

    def lines(self) -> int:
        return self.b.count(10) + 1

    def _line(self, n: int) -> tuple[int, int, int]:
        """(start, length, end length) of line n."""
        start = 0
        for _ in range(n - 1):
            start = self.b.index(10, start) + 1
        lf = self.b.find(10, start)
        if lf < 0:
            return start, len(self.b) - start, 0
        if lf > start and self.b[lf - 1] == 13:
            return start, lf - 1 - start, 2
        return start, lf - start, 1

    def length(self, n: int) -> int:
        return self._line(n)[1]

    def get(self, n: int, col: int, count: int) -> bytes:
        start, length, _ = self._line(n)
        data = bytes(self.b[start + col - 1 : start + min(length, col - 1 + count)])
        return data.replace(b"\0", b"?")

    def insert(self, n: int, col: int, s: bytes) -> None:
        start, _, _ = self._line(n)
        self.b[start + col - 1 : start + col - 1] = s

    def delete(self, n: int, col: int, count: int) -> None:
        start, _, _ = self._line(n)
        del self.b[start + col - 1 : start + col - 1 + count]

    def split(self, n: int, col: int) -> None:
        start, _, end = self._line(n)
        if end == 0:
            end = 2 if self.style_crlf else 1
        self.b[start + col - 1 : start + col - 1] = b"\r\n" if end == 2 else b"\n"

    def join(self, n: int) -> None:
        start, length, end = self._line(n)
        del self.b[start + length : start + length + end]

    def find(self, s: bytes, n: int, col: int) -> tuple[int, int]:
        start, _, _ = self._line(n)
        at = self.b.find(s, start + col - 1) if s else -1
        while at >= 0 and 10 in self.b[at : at + len(s)]:
            at = self.b.find(s, at + 1)
        if at < 0:
            return 0, 0
        line = self.b.count(10, 0, at) + 1
        line_start = self.b.rfind(10, 0, at) + 1
        return line, at - line_start + 1


def basic_string(data: bytes) -> str:
    return '"' + data.decode("ascii") + '"'


def run(src: str, files=None, **options):
    disk = z80sim.Disk(files={(F, name): data for name, data in (files or {}).items()},
                       faults=options.pop("faults", None))
    return guarded_run(src, disk=disk, **options)


# MESSAGE IOERR and whether the buffer is changed ("0" / "1": STR$ takes no BOOLEAN)
IO_AND_CHANGED = ('S$ = STR$(IOERR)\nIF TEXTCHANGED(D) THEN\nS$ = S$ + "1"\nELSE\n'
                  'S$ = S$ + "0"\nEND IF\nMESSAGE S$\n')


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return caught.exception

    def test_declarations(self):
        self.assertIn("AS TEXT * bytes", self.reject("DIM D AS TEXT\nEND\n").message)
        self.assertIn("AS TEXT * bytes", self.reject("DIM D AS TEXT * 0\nEND\n").message)
        self.assertIn("AS TEXT * bytes", self.reject("DIM D AS TEXT * 65536\nEND\n").message)
        self.assertIn("AS TEXT * bytes", self.reject("DIM D(3) AS TEXT * 100\nEND\n").message)
        self.assertIn("top level", self.reject(
            "SUB S\nLOCAL D AS TEXT\nEND SUB\nEND\n").message)
        program = check_source("DIM D AS TEXT * 65535\nEND\n")
        self.assertEqual(program.variables["D"].text_bytes, 65535)

    def test_statements_and_functions(self):
        base = "DIM D AS TEXT * 100\nDIM N AS INTEGER\nDIM S$ AS STRING\n"
        self.assertIn("needs a TEXT buffer", self.reject(base + "TEXT CLEAR N\nEND\n").message)
        self.assertIn("needs a TEXT buffer", self.reject(base + "N = TEXTLINES(S$)\nEND\n").message)
        self.assertIn("takes the buffer and 3 more", self.reject(base + "TEXT INSERT D, 1, 1\nEND\n").message)
        self.assertIn("expects STRING", self.reject(base + "TEXT INSERT D, 1, 1, 5\nEND\n").message)
        self.assertIn("expected LOAD, SAVE", self.reject(base + "TEXT SHOW D\nEND\n").message)
        self.assertIn("not a valid DOS 8.3", self.reject(base + 'TEXT LOAD D, "TOOLONGNAME.TXT"\nEND\n').message)
        self.assertIn("cannot assign", self.reject(base + "N = D\nEND\n").message)
        # older programs may use TEXT as a variable
        check_source("DIM Text AS INTEGER\nText = 3\nEND\n")

    def test_textget_budget(self):
        program = check_source("DIM D AS TEXT * 100\nDIM S$ AS STRING * 10\nS$ = TEXTGET$(D, 1, 1, 9)\nEND\n")
        self.assertIsNotNone(program)


@requires_pasmo
class RoundTripTests(unittest.TestCase):
    PROGRAM = ('DIM D AS TEXT * {cap}\nDIM S$ AS STRING\nTEXT LOAD D, "IN.MD"\n'
               'MESSAGE STR$(IOERR) + " " + STR$(TEXTLINES(D)) + " " + STR$(TEXTSIZE(D))\n'
               'TEXT SAVE D, "OUT.MD"\n' + IO_AND_CHANGED + 'END\n')

    def roundtrip(self, data: bytes, cap: int = 40000):
        r = run(self.PROGRAM.format(cap=cap), {"IN.MD": data})
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, [f"0 {data.count(10) + 1} {min(len(data), 32767)}", "00"])
        self.assertEqual(r.cpu.disk.file("OUT.MD"), data)
        self.assertEqual(r.cpu.blocks_at_exit, [])
        self.assertEqual(r.cpu.q2, z80sim.Q2_START_BLOCK)

    def test_kinds_of_text(self):
        cases = {
            "crlf": b"# Title\r\n\r\nA line.\r\nLast line\r\n",
            "lf": b"# Title\n\nA line.\nLast line\n",
            "no final end": b"one\r\ntwo",
            "empty": b"",
            "one LF": b"\n",
            "lone CR": b"a\rb\r\nc",
            "bytes": bytes(range(256)) * 3,
            "long line": b"x" * 700 + b"\r\n" + b"y" * 300,
        }
        for name, data in cases.items():
            with self.subTest(name):
                self.roundtrip(data)

    def test_more_than_one_block(self):
        rnd = random.Random(9)
        data = b"".join(b"line %d %s\r\n" % (i, bytes(rnd.choice(b"abcdef ") for _ in range(30)))
                        for i in range(800))
        self.assertGreater(len(data), 16384 + 8000)
        self.roundtrip(data)

    def test_exactly_full_and_too_big(self):
        self.roundtrip(b"z" * 100, cap=100)
        r = run(self.PROGRAM.format(cap=100), {"IN.MD": b"z" * 101})
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts[0], "246 1 0", "too big: IOERR 246, the buffer left empty")
        self.assertEqual(r.cpu.disk.open_at_exit, (None, None))

    def test_missing_file(self):
        r = run(self.PROGRAM.format(cap=100), {})
        self.assertEqual(r.alerts[0], "2 1 0")

    def test_disk_full_on_save(self):
        r = run(self.PROGRAM.format(cap=100), {"IN.MD": b"abc"}, faults={z80sim.FN_OS_WRITE_FILE: 0xA3})
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts[1], "1630")
        self.assertEqual(r.cpu.disk.open_at_exit, (None, None))


@requires_pasmo
class EditTests(unittest.TestCase):
    """Random edits, compiled as BASIC, against TextModel."""

    def check_sequence(self, data: bytes, ops, cap: int = 40000, seed_note: str = "", steps=None):
        model = TextModel(data)
        lines = [f"DIM D AS TEXT * {cap}", "DIM S$ AS STRING", 'TEXT LOAD D, "IN.MD"']
        expect = []
        for op in ops:
            kind = op[0]
            if kind == "insert":
                lines.append(f"TEXT INSERT D, {op[1]}, {op[2]}, {basic_string(op[3])}")
                model.insert(*op[1:])
            elif kind == "delete":
                lines.append(f"TEXT DELETE D, {op[1]}, {op[2]}, {op[3]}")
                model.delete(*op[1:])
            elif kind == "split":
                lines.append(f"TEXT SPLIT D, {op[1]}, {op[2]}")
                model.split(*op[1:])
            elif kind == "join":
                lines.append(f"TEXT JOIN D, {op[1]}")
                model.join(op[1])
            elif kind == "probe":
                n = op[1]
                lines.append(f'S$ = STR$(TEXTLINES(D)) + ":" + STR$(TEXTLEN(D, {n})) + ":" + TEXTGET$(D, {n}, 1, 20)')
                lines.append("MESSAGE S$")
                expect.append(f"{model.lines()}:{model.length(n)}:" + model.get(n, 1, 20).decode("latin-1"))
        lines += ['TEXT SAVE D, "OUT.MD"', IO_AND_CHANGED + "END"]
        expect.append("00")
        r = run("\n".join(lines) + "\n", {"IN.MD": data}, **({"max_steps": steps} if steps else {}))
        self.assertEqual(r.violations, [], seed_note)
        self.assertEqual(r.alerts, expect, seed_note)
        self.assertEqual(r.cpu.disk.file("OUT.MD"), bytes(model.b), seed_note)
        self.assertEqual(r.cpu.blocks_at_exit, [])

    def random_ops(self, rnd, model: TextModel, count: int):
        ops = []
        for _ in range(count):
            n = rnd.randint(1, model.lines())
            length = model.length(n)
            kind = rnd.choice(("insert", "insert", "delete", "split", "join", "probe"))
            if kind == "insert":
                text = bytes(rnd.choice(b"abcXYZ 019#*-") for _ in range(rnd.randint(1, 12)))
                op = ("insert", n, rnd.randint(1, length + 1), text)
                model.insert(*op[1:])
            elif kind == "delete" and length:
                col = rnd.randint(1, length)
                op = ("delete", n, col, rnd.randint(0, length - col + 1))
                model.delete(*op[1:])
            elif kind == "split":
                op = ("split", n, rnd.randint(1, length + 1))
                model.split(*op[1:])
            elif kind == "join" and n < model.lines():
                op = ("join", n)
                model.join(n)
            else:
                op = ("probe", n)
            ops.append(op)
        return ops

    def test_random_sequences(self):
        bases = [b"", b"one\r\ntwo\r\nthree", b"alpha\nbeta\n\ngamma\n", b"x" * 200 + b"\r\n" + b"y" * 50]
        for seed in range(12):
            rnd = random.Random(seed)
            data = bases[seed % len(bases)]
            ops = self.random_ops(rnd, TextModel(data), 40)
            with self.subTest(seed=seed):
                self.check_sequence(data, ops, seed_note=f"seed {seed}")

    def test_gap_moves_across_blocks(self):
        data = b"".join(b"%05d abcdefghij\r\n" % i for i in range(1500))  # about 25K
        model = TextModel(data)
        last = model.lines()
        ops = [("insert", last, 1, b"END"), ("insert", 1, 1, b"START"), ("probe", 1),
               ("insert", 900, 3, b"MID"), ("probe", 900), ("split", 1000, 4), ("join", 1),
               ("delete", 2, 1, 5), ("probe", last)]
        self.check_sequence(data, ops, steps=400_000_000)

    def test_split_uses_the_line_end_kind(self):
        self.check_sequence(b"a\nb\r\nc", [("split", 1, 2), ("split", 3, 1), ("split", 4, 2), ("probe", 4)])
        self.check_sequence(b"lf only\n", [("split", 2, 1), ("split", 1, 3)])
        self.check_sequence(b"", [("split", 1, 1), ("insert", 1, 1, b"x")])


@requires_pasmo
class FindTests(unittest.TestCase):
    def test_find(self):
        data = b"alpha beta\r\ngamma beta\r\n\r\ndelta"
        model = TextModel(data)
        cases = [(b"beta", 1, 1), (b"beta", 1, 8), (b"beta", 2, 7), (b"delta", 1, 1), (b"zeta", 1, 1),
                 (b"a\r", 1, 1), (b"a", 4, 5), (b"a", 4, 6)]
        lines = ["DIM D AS TEXT * 1000", 'TEXT LOAD D, "IN.MD"']
        for s, n, col in cases:
            lines.append(f'MESSAGE STR$(TEXTFIND(D, {basic_string(s) if 13 not in s else chr(34) + "a" + chr(34) + " + CHR$(13)"}, {n}, {col})) + "," + STR$(TEXTCOL(D))')
        r = run("\n".join(lines) + "\nEND\n", {"IN.MD": data})
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["%d,%d" % model.find(s, n, col) for s, n, col in cases])


@requires_pasmo
class ErrorTests(unittest.TestCase):
    BASE = 'DIM D AS TEXT * 50\nDIM S$ AS STRING\nTEXT LOAD D, "IN.MD"\n'

    def error(self, statement: str, message: str, data: bytes = b"ab\r\ncd"):
        r = run(self.BASE + statement + "\nEND\n", {"IN.MD": data})
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, [message.format(4)])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.blocks_at_exit, [])
        self.assertEqual(r.cpu.q2, z80sim.Q2_START_BLOCK, "the block at #8000 is put back before the report")

    def test_positions(self):
        for statement in ("TEXT INSERT D, 0, 1, \"x\"", "TEXT INSERT D, 3, 1, \"x\"",
                          "TEXT INSERT D, 1, 0, \"x\"", "TEXT INSERT D, 1, 4, \"x\"",
                          "TEXT DELETE D, 1, 3, 1", "TEXT DELETE D, 1, 2, 2", "TEXT DELETE D, 1, 1, -1",
                          "TEXT SPLIT D, 2, 4", "TEXT JOIN D, 2", "S$ = TEXTGET$(D, 1, 4, 1)",
                          "S$ = TEXTGET$(D, 1, 1, -1)", "S$ = STR$(TEXTLEN(D, 3))",
                          "S$ = STR$(TEXTFIND(D, \"a\", 0, 1))", "TEXT DELETE D, 1, 4, 0"):
            with self.subTest(statement):
                self.error(statement, POS_ERR)

    def test_full_and_line_breaks(self):
        self.error('TEXT INSERT D, 1, 1, "' + "x" * 45 + '"', FULL_ERR)
        self.error("TEXT INSERT D, 1, 1, \"a\" + CHR$(10)", BRK_ERR)
        self.error("TEXT INSERT D, 1, 1, CHR$(13)", BRK_ERR)
        self.error("TEXT SPLIT D, 1, 1", FULL_ERR, b"x" * 49)

    def test_zero_byte_reads_as_question_mark(self):
        r = run(self.BASE + 'S$ = TEXTGET$(D, 1, 1, 9)\nMESSAGE S$ + STR$(LEN(S$))\nEND\n',
                {"IN.MD": b"a\0b\r\n"})
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["a?b3"])

    def test_free_and_size(self):
        r = run(self.BASE + 'MESSAGE STR$(TEXTFREE(D)) + " " + STR$(TEXTSIZE(D))\nEND\n', {"IN.MD": b"ab\r\ncd"})
        self.assertEqual(r.alerts, ["44 6"])

    def test_string_file_names(self):
        names = {"ok.md": 0, "OK.MD": 0, "CON.TXT": 247, "LPT1.X": 247, "COM10.X": 2, "A.TOOLONG": 247,
                 "NODOT": 247, ".MD": 247, "TOOLONGNAME.MD": 247, "A_B.M_D": 247, "A B.MD": 247,
                 "LPT.X": 2, "NULL.X": 2}
        lines = ["DIM D AS TEXT * 50", "DIM N$ AS STRING"]
        for name in names:
            lines += [f'N$ = "{name}"', "TEXT LOAD D, N$", "MESSAGE STR$(IOERR)"]
        r = run("\n".join(lines) + "\nEND\n", {"OK.MD": b"x"})
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, [str(v) for v in names.values()])

    def test_kill_and_name_with_strings(self):
        src = ('DIM A$ AS STRING\nDIM B$ AS STRING\nA$ = "old.tmp"\nB$ = "NEW.TMP"\n'
               'NAME A$ AS B$\nMESSAGE STR$(IOERR)\nKILL B$\nMESSAGE STR$(IOERR)\n'
               'A$ = "BAD"\nKILL A$\nMESSAGE STR$(IOERR)\nEND\n')
        r = run(src, {"OLD.TMP": b"data"})
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["0", "0", "247"])
        self.assertIsNone(r.cpu.disk.file("NEW.TMP"))
        self.assertIsNone(r.cpu.disk.file("OLD.TMP"))


@requires_pasmo
class BankedCodeTests(unittest.TestCase):
    """TEXT routines map their blocks at #8000 — where a code bank runs. A
    TEXT call from banked code must find its bank mapped again afterwards."""

    def test_text_from_code_banks(self):
        src = ('DIM D AS TEXT * 30000\nDIM S$ AS STRING\n'
               'SUB Edit\nTEXT INSERT D, 1, 1, "hello"\nTEXT SPLIT D, 1, 3\nCALL Show\nEND SUB\n'
               'SUB Show\nS$ = TEXTGET$(D, 2, 1, 10) + STR$(TEXTLINES(D))\nMESSAGE S$\nEND SUB\n'
               'TEXT LOAD D, "IN.MD"\nCALL Edit\nTEXT SAVE D, "OUT.MD"\nEND\n')
        r = run(src, {"IN.MD": b"world\r\n"}, build_options=dict(code_banks="always", code_bank_limit=120))
        self.assertEqual(r.violations, [])
        self.assertGreaterEqual(len(r.report.banked.banks), 2)
        self.assertEqual(r.alerts, ["lloworld3"])
        self.assertEqual(r.cpu.disk.file("OUT.MD"), b"he\r\nlloworld\r\n")
        self.assertEqual(r.cpu.blocks_at_exit, [])
        self.assertEqual(r.cpu.q2, z80sim.Q2_START_BLOCK)


if __name__ == "__main__":
    unittest.main()
