"""M10 Stage D: TEXT REMOVE / COPY / PASTE / TEXTSAME (LANGUAGE-SPEC §5.7,
M10 additions) and INCLUDE (§5.11).

Random sequences of range operations on two buffers, compiled as BASIC,
must leave exactly the bytes a Python model predicts (test_m9_text's
TextModel plus ranges), across 16K block boundaries; position and room
errors are positioned runtime errors. INCLUDE: nested files, line numbers,
error mapping, and the rules. Simulator evidence only.
"""
from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run
from pbas import SourceError, check_source, generate
from pbas.prg import build
from test_m9_text import F, TextModel
from toolchain import requires_pasmo

POS_ERR = "Runtime error: text position out of range at line {}"
FULL_ERR = "Runtime error: the TEXT buffer is full at line {}"


def pos(m: TextModel, n: int, c: int) -> int:
    start, length, _ = m._line(n)
    assert 1 <= c <= length + 1
    return start + c - 1


def run(src, files):
    disk = z80sim.Disk(files={(F, k): v for k, v in files.items()})
    r = guarded_run(src, disk=disk, max_steps=600_000_000)
    assert r.violations == [], r.violations[:5]
    return r


def saved(r, name):
    return r.cpu.disk.files.get((F, name))


class FrontendTests(unittest.TestCase):
    def reject(self, src):
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return str(caught.exception)

    def test_rules(self):
        base = "DIM D AS TEXT * 100\nDIM C AS TEXT * 100\nDIM N AS INTEGER\n"
        cases = {
            "TEXT COPY D, D\nEND\n": "TEXT COPY needs two different buffers",
            "TEXT PASTE D, 1, 1, D\nEND\n": "needs two different buffers",
            "TEXT COPY D, N\nEND\n": "TEXT COPY needs a TEXT buffer",
            "TEXT COPY D, C, 1, 1\nEND\n": "TEXT COPY takes the buffer and 1 or 5 more arguments, got 3",
            "TEXT REMOVE D, 1, 1, 1\nEND\n": "TEXT REMOVE takes the buffer and 4 more arguments, got 3",
            "TEXT REMOVE D, 1, 1, 1, \"x\"\nEND\n": "TEXT REMOVE expects INTEGER here, got STRING",
            "TEXT PASTE D, 1, 1, \"x\"\nEND\n": "TEXT PASTE needs a TEXT buffer",
            "IF TEXTSAME(D, N) THEN\nEND IF\nEND\n": "TEXTSAME needs a TEXT buffer",
            "TEXT FOLD D\nEND\n": "COPY or PASTE after TEXT, got FOLD",
        }
        for body, message in cases.items():
            with self.subTest(body=body):
                self.assertIn(message, self.reject(base + body))

    def test_programs_without_ranges_keep_their_runtime(self):
        asm = generate(check_source("DIM D AS TEXT * 100\nTEXT INSERT D, 1, 1, \"a\"\nEND\n"))
        self.assertIn("PB_TXRANGE equ 0", asm)


@requires_pasmo
class RangeModelTests(unittest.TestCase):
    def random_text(self, rnd, size):
        out = bytearray()
        while len(out) < size:
            out += bytes(rnd.choice(b"abcxyz 0129") for _ in range(rnd.randint(0, 70)))
            out += rnd.choice([b"\r\n", b"\n", b"\r\n"])
        return bytes(out[:size])

    def random_range(self, rnd, m):
        lines = m.lines()
        n1 = rnd.randint(1, lines)
        n2 = rnd.randint(n1, min(lines, n1 + rnd.choice([0, 1, 3, 40])))
        c1 = rnd.randint(1, m.length(n1) + 1)
        c2 = rnd.randint(c1 if n2 == n1 else 1, m.length(n2) + 1)
        return n1, c1, n2, c2

    def check(self, seed, size, steps):
        rnd = random.Random(seed)
        d = TextModel(self.random_text(rnd, size))
        c = TextModel(b"")
        ops, lines_seen = [], []
        for _ in range(steps):
            kind = rnd.choice(["remove", "copy", "paste", "paste", "whole", "split"])
            if kind == "remove":
                n1, c1, n2, c2 = self.random_range(rnd, d)
                del d.b[pos(d, n1, c1):pos(d, n2, c2)]
                ops.append(f"TEXT REMOVE D, {n1}, {c1}, {n2}, {c2}")
            elif kind == "copy":
                n1, c1, n2, c2 = self.random_range(rnd, d)
                part = bytes(d.b[pos(d, n1, c1):pos(d, n2, c2)])
                if len(part) > 30000:
                    continue
                c = TextModel(part)
                c.style_crlf = d.style_crlf
                ops.append(f"TEXT COPY C, D, {n1}, {c1}, {n2}, {c2}")
            elif kind == "paste":
                if len(d.b) + len(c.b) > 40000:
                    continue
                n = rnd.randint(1, d.lines())
                col = rnd.randint(1, d.length(n) + 1)
                at = pos(d, n, col)
                d.b[at:at] = c.b
                ops.append(f"TEXT PASTE D, {n}, {col}, C")
            elif kind == "whole":
                if len(d.b) > 30000:
                    continue
                c = TextModel(bytes(d.b))
                c.style_crlf = d.style_crlf
                ops.append("TEXT COPY C, D")
            else:  # a line end in C: of its line's kind, or of the style it was copied with
                if len(c.b) + 2 > 30000:
                    continue
                n = rnd.randint(1, c.lines())
                col = rnd.randint(1, c.length(n) + 1)
                c.split(n, col)
                ops.append(f"TEXT SPLIT C, {n}, {col}")
            ops.append(f"MESSAGE STR$(TEXTLINES(D)) + \" \" + STR$(TEXTLINES(C))")
            lines_seen.append(f"{d.lines()} {c.lines()}")
        src = ("DIM D AS TEXT * 40000\nDIM C AS TEXT * 30000\nTEXT LOAD D, \"IN.TXT\"\n"
               + "\n".join(o for o in ops if o) + "\nTEXT SAVE D, \"D.TXT\"\nTEXT SAVE C, \"C.TXT\"\n"
               "IF TEXTSAME(D, C) THEN\n    MESSAGE \"same\"\nELSE\n    MESSAGE \"differ\"\nEND IF\nEND\n")
        r = run(src, {"IN.TXT": bytes(TextModel(self.random_text(random.Random(seed), size)).b)})
        self.assertEqual(r.alerts, lines_seen + ["same" if d.b == c.b else "differ"])
        self.assertEqual(saved(r, "D.TXT"), bytes(d.b))
        self.assertEqual(saved(r, "C.TXT"), bytes(c.b))

    def test_small(self):
        for seed in range(4):
            with self.subTest(seed=seed):
                self.check(seed, 600, 12)

    def test_across_blocks(self):
        self.check(99, 21000, 10)  # positions on both sides of the 16K block end

    def test_split_after_copy_uses_the_source_style(self):
        src = ('DIM D AS TEXT * 100\nDIM C AS TEXT * 100\nTEXT LOAD D, "IN.TXT"\n'
               'TEXT COPY C, D, 1, 2, 1, 3\nTEXT SPLIT C, 1, 2\nTEXT SAVE C, "C.TXT"\nEND\n')
        for data, end in ((b"abc\nd", b"\n"), (b"abc\r\nd", b"\r\n")):
            with self.subTest(data=data):
                r = run(src, {"IN.TXT": data})
                self.assertEqual(saved(r, "C.TXT"), b"b" + end)

    def test_same_compares_bytes_only(self):
        src = ('DIM D AS TEXT * 100\nDIM C AS TEXT * 50\nTEXT LOAD D, "A.TXT"\nTEXT LOAD C, "B.TXT"\n'
               'IF TEXTSAME(D, C) THEN\n    MESSAGE "same"\nELSE\n    MESSAGE "differ"\nEND IF\nEND\n')
        for a, b, want in ((b"", b"", "same"), (b"ab\r\n", b"ab\r\n", "same"), (b"ab\r\n", b"ab\n", "differ"),
                           (b"ab", b"abc", "differ"), (b"abd", b"abc", "differ")):
            with self.subTest(a=a, b=b):
                self.assertEqual(run(src, {"A.TXT": a, "B.TXT": b}).alerts, [want])

    def test_errors(self):
        base = 'DIM D AS TEXT * 100\nDIM C AS TEXT * 8\nTEXT LOAD D, "IN.TXT"\n'
        data = b"abcd\r\nefgh\r\nij"
        cases = [
            ("TEXT REMOVE D, 2, 1, 1, 3", POS_ERR),  # end before start
            ("TEXT REMOVE D, 1, 6, 2, 1", POS_ERR),  # column past the line
            ("TEXT REMOVE D, 1, 1, 4, 1", POS_ERR),  # no line 4
            ("TEXT COPY C, D", FULL_ERR),             # 14 bytes into 8
            ("TEXT COPY C, D, 1, 1, 3, 3", FULL_ERR),
            ("TEXT COPY C, D, 2, 3, 2, 2", POS_ERR),
            ("TEXT PASTE D, 3, 4, C", POS_ERR),
        ]
        for stmt, err in cases:
            with self.subTest(stmt=stmt):
                r = run(base + stmt + "\nEND\n", {"IN.TXT": data})
                self.assertEqual(r.alerts, [err.format(4)])
        # a paste that does not fit; the destination is unchanged
        src = ('DIM D AS TEXT * 20\nDIM C AS TEXT * 20\nTEXT LOAD D, "IN.TXT"\nTEXT COPY C, D\n'
               'TEXT PASTE D, 1, 1, C\nEND\n')
        self.assertEqual(run(src, {"IN.TXT": data}).alerts, [FULL_ERR.format(5)])

    def test_buffers_without_files_build(self):
        # KI-52: before M10 a TEXT program without LOAD / SAVE did not assemble
        src = ('DIM D AS TEXT * 100\nDIM C AS TEXT * 100\nTEXT INSERT D, 1, 1, "abc"\nTEXT SPLIT D, 1, 2\n'
               'TEXT COPY C, D\nMESSAGE STR$(TEXTLINES(C)) + TEXTGET$(C, 2, 1, 5)\nEND\n')
        self.assertEqual(run(src, {}).alerts, ["2bc"])

    def test_empty_ranges_change_nothing(self):
        src = ('DIM D AS TEXT * 100\nDIM C AS TEXT * 20\nTEXT LOAD D, "IN.TXT"\n'
               'TEXT REMOVE D, 2, 3, 2, 3\nTEXT PASTE D, 1, 1, C\nIF TEXTCHANGED(D) THEN\n    MESSAGE "changed"\n'
               'END IF\nTEXT COPY C, D, 1, 2, 1, 2\nMESSAGE STR$(TEXTSIZE(C)) + STR$(TEXTLINES(C))\nEND\n')
        self.assertEqual(run(src, {"IN.TXT": b"ab\ncd"}).alerts, ["01"])


@requires_pasmo
class IncludeTests(unittest.TestCase):
    def build(self, files: dict[str, str], main="MAIN.PBAS"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text, encoding="utf-8")
        return root, lambda: build(root / main, root / "m.asm", root / "m.prg")

    def test_nested_libraries_and_line_numbers(self):
        root, go = self.build({
            "MAIN.PBAS": 'INCLUDE "lib/a.pbas"\nCALL Two(1)\nCALL Two(0)\nEND\n',
            "lib/a.pbas": "' a\nINCLUDE \"b.pbas\"\nSUB Two(N AS INTEGER)\n    MESSAGE Name$() + STR$(6 / N)\nEND SUB\n",
            "lib/b.pbas": 'FUNCTION Name$() AS STRING\n    RETURN "b"\nEND FUNCTION\n',
        })
        report = go()
        self.assertEqual(report.includes, ("lib/a.pbas: lines 1001..1999", "lib/b.pbas: lines 2001..2999"))
        r = z80sim.run(root / "m.prg")
        self.assertEqual(r.alerts, ["b6", "Runtime error: division by zero at line 1004"])

    def test_without_include_nothing_changes(self):
        # the include pass hands the parser the lexer's own tokens
        from pbas.include import expand
        from pbas.lexer import tokenize
        src = (Path(__file__).resolve().parents[1] / "examples" / "mdedit.pbas").read_text(encoding="utf-8")
        tokens, smap = expand(src, None)
        self.assertEqual(tokens, tokenize(src))
        self.assertEqual(smap.parts, [])

    def test_errors_name_the_file_and_its_line(self):
        root, go = self.build({"MAIN.PBAS": 'INCLUDE "LIB.PBAS"\nEND\n',
                               "LIB.PBAS": "SUB S\n    MESSAGE 1 + 2\nEND SUB\n"})
        with self.assertRaises(SourceError) as caught:
            go()
        self.assertEqual(caught.exception.where("MAIN.PBAS"), "LIB.PBAS:2:5: MESSAGE expects STRING, got INTEGER")

    def test_rules(self):
        cases = {
            "missing": ({"MAIN.PBAS": 'INCLUDE "NONE.PBAS"\nEND\n'}, 'MAIN.PBAS:1:1: INCLUDE "NONE.PBAS": no such file'),
            "twice": ({"MAIN.PBAS": 'INCLUDE "L.PBAS"\nINCLUDE "L.PBAS"\nEND\n', "L.PBAS": "' x\n"},
                      'MAIN.PBAS:2:1: INCLUDE "L.PBAS": that file is already part of the program (included at line 1)'),
            "cycle": ({"MAIN.PBAS": 'INCLUDE "L.PBAS"\nEND\n', "L.PBAS": 'INCLUDE "MAIN.PBAS"\n'},
                      'L.PBAS:1:1: INCLUDE "MAIN.PBAS": that file is already part of the program (it is the program itself)'),
            "line numbers": ({"MAIN.PBAS": 'INCLUDE "L.PBAS"\nEND\n', "L.PBAS": '10 X = 1\n'},
                             "L.PBAS:1:1: an included file may not have BASIC line numbers"),
            "too long": ({"MAIN.PBAS": 'INCLUDE "L.PBAS"\nEND\n', "L.PBAS": "' x\n" * 1000},
                         'MAIN.PBAS:1:1: INCLUDE "L.PBAS": an included file has fewer than 1000 lines (it has 1000)'),
        }
        for what, (files, message) in cases.items():
            with self.subTest(what):
                _, go = self.build(files)
                with self.assertRaises(SourceError) as caught:
                    go()
                self.assertEqual(caught.exception.where("MAIN.PBAS"), message)


if __name__ == "__main__":
    unittest.main()
