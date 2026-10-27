"""M7 — sequential files (LANGUAGE-SPEC.md §7.1): OPEN, CLOSE, PRINT #,
LINE INPUT #, EOF, KILL, NAME and IOERR. Runs on the simulator's in-memory
disk (never on host files) under the memory checker: engineering evidence,
not XAnne. The Rosanne contracts used are ROSAN283's; delete and rename have
not been seen in XAnne.
"""
from __future__ import annotations

import unittest

import z80sim
from memguard import guarded_run
from pbas import SourceError, check_source, generate
from pbas.files import FileLocation
from toolchain import requires_pasmo

FOLDER = "\\PCW\\FOLDER01"


def run(src: str, files=None, **disk_kw):
    location = disk_kw.pop("location", None)
    disk = z80sim.Disk(files={(FOLDER, k): v for k, v in (files or {}).items()}, **disk_kw)
    r = guarded_run(src, disk=disk, location=location)
    assert r.violations == [], r.violations
    assert disk.open_at_exit in (None, (None, None)) or r.cpu.alerts, disk.open_at_exit
    return r.cpu.alerts, {k[1]: v for k, v in disk.files.items()}


READER = '''DIM L$ AS STRING
DIM N AS INTEGER
OPEN "IN.TXT" FOR INPUT AS #1
MESSAGE "open " + STR$(IOERR)
WHILE NOT EOF(1)
    L$ = "?"
    LINE INPUT #1, L$
    N = N + 1
    MESSAGE STR$(N) + " " + STR$(IOERR) + " [" + L$ + "]"
WEND
LINE INPUT #1, L$
MESSAGE "after " + STR$(IOERR) + " [" + L$ + "]"
CLOSE #1
MESSAGE "close " + STR$(IOERR)
END
'''


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return caught.exception

    def test_rules(self):
        cases = {
            'OPEN "A.TXT" FOR INPUT AS #3\nEND\n': "a file channel is #1 or #2",
            'OPEN "A.TXT" FOR APPEND AS #1\nEND\n': "expected INPUT or OUTPUT",
            'OPEN "TOOLONGNAME.TXT" FOR INPUT AS #1\nEND\n': "not a valid DOS 8.3 name",
            'OPEN "CON.TXT" FOR INPUT AS #1\nEND\n': "DOS device name",
            'DIM X AS INTEGER\nX = IOERR\nEND\n': "the program has none (OPEN, KILL, NAME",
            'KILL "A.TXT"\nIF EOF(3) THEN\nEND IF\nEND\n': "EOF expects a channel number",
            'DIM X AS INTEGER\nOPEN "A.TXT" FOR INPUT AS #1\nLINE INPUT #1, X\nEND\n': "LINE INPUT needs a STRING variable",
            'DIM A$(3) AS STRING\nOPEN "A.TXT" FOR INPUT AS #1\nLINE INPUT #1, A$\nEND\n': "is an array",
            'OPEN "A.TXT" FOR OUTPUT AS #1\nPRINT #1, TRUE\nEND\n': "PRINT # writes a STRING or a number",
            'DIM S$ AS STRING\nOPEN "A.TXT" FOR OUTPUT AS #1\nPRINT #1, S$ + S$ + S$\nEND\n': "a line holds at most 127",
            'NAME "A.TXT" AS "B"\nEND\n': "not a valid DOS 8.3 name",
            'PRINT "x"\nEND\n': "PRINT to the screen does not exist",  # M14
        }
        for src, fragment in cases.items():
            with self.subTest(src=src):
                self.assertIn(fragment, self.reject(src).message)

    def test_words_stay_usable_as_names(self):
        check_source("DIM Open AS INTEGER\nDIM Name AS INTEGER\nDIM Line AS INTEGER\nDIM Kill(3) AS INTEGER\n"
                     "DIM Close AS INTEGER\nOpen = 1\nName = Open\nLine = Name\nKill(1) = Line\n"
                     "Close = Kill(1)\nEND\n")


@requires_pasmo
class BehaviourTests(unittest.TestCase):
    def test_round_trip_kill_and_rename(self):
        src = '''DIM Names$(5) AS STRING
DIM I AS INTEGER
DIM N AS INTEGER
DIM L$ AS STRING
OPEN "PBREC.TMP" FOR OUTPUT AS #2
FOR I = 1 TO 3
    PRINT #2, "Record " + STR$(I)
NEXT I
PRINT #2, 12345
PRINT #2, ""
CLOSE #2
MESSAGE "write " + STR$(IOERR)
KILL "PBREC.DAT"
MESSAGE "kill missing " + STR$(IOERR)
NAME "PBREC.TMP" AS "PBREC.DAT"
MESSAGE "rename " + STR$(IOERR)
OPEN "PBREC.DAT" FOR INPUT AS #1
WHILE NOT EOF(1)
    N = N + 1
    LINE INPUT #1, Names$(N)
WEND
CLOSE
FOR I = 1 TO N
    MESSAGE "[" + Names$(I) + "]"
NEXT I
LINE INPUT #1, L$
MESSAGE "closed " + STR$(IOERR)
OPEN "NOFILE.DAT" FOR INPUT AS #1
MESSAGE "missing " + STR$(IOERR)
IF EOF(1) THEN
    MESSAGE "eof true"
END IF
END
'''
        alerts, files = run(src)
        self.assertEqual(alerts, ["write 0", "kill missing 2", "rename 0", "[Record 1]", "[Record 2]",
                                  "[Record 3]", "[12345]", "[]", "closed 242", "missing 2", "eof true"])
        self.assertEqual(files, {"PBREC.DAT": b"Record 1\r\nRecord 2\r\nRecord 3\r\n12345\r\n\r\n"})

    def test_line_endings_and_odd_content(self):
        cases = {
            b"one\ntwo": ["1 0 [one]", "2 0 [two]"],                    # LF only, no final newline
            b"a\r\nb\r\n": ["1 0 [a]", "2 0 [b]"],
            b"x\ry\r\n": ["1 0 [xy]"],                                    # CR is dropped
            b"\r\n\r\n": ["1 0 []", "2 0 []"],
            b"": [],                                                      # empty file: EOF at once
            b"ok\n" + b"z" * 70 + b"\nnext\n": ["1 0 [ok]", "2 243 [?]", "3 0 [next]"],  # too long
            b"a\x00b\nc\n": ["1 244 [?]", "2 0 [c]"],                     # a zero byte
            b"y" * 63 + b"\n": ["1 0 [" + "y" * 63 + "]"],                # exactly the capacity
        }
        for content, lines in cases.items():
            with self.subTest(content=content[:20]):
                alerts, _ = run(READER, files={"IN.TXT": content})
                last = lines[-1].split("[", 1)[1][:-1] if lines else ""
                self.assertEqual(alerts, ["open 0"] + lines + [f"after 245 [{last}]", "close 0"])
                self.assertTrue(alerts[-2].startswith("after 245"))

    def test_failures_are_recoverable(self):
        src = '''DIM S$ AS STRING
S$ = "keep"
OPEN "IN.TXT" FOR INPUT AS #1
MESSAGE "a " + STR$(IOERR)
OPEN "IN.TXT" FOR INPUT AS #1
MESSAGE "b " + STR$(IOERR)
OPEN "IN.TXT" FOR INPUT AS #2
MESSAGE "c " + STR$(IOERR)
PRINT #1, "x"
MESSAGE "d " + STR$(IOERR)
PRINT #2, "x"
MESSAGE "e " + STR$(IOERR)
LINE INPUT #2, S$
MESSAGE "f " + STR$(IOERR) + " " + S$
CLOSE #2
MESSAGE "g " + STR$(IOERR)
OPEN "OUT.TXT" FOR OUTPUT AS #2
PRINT #2, "first"
MESSAGE "h " + STR$(IOERR)
KILL "IN.TXT"
MESSAGE "i " + STR$(IOERR)
NAME "IN.TXT" AS "OUT.TXT"
MESSAGE "j " + STR$(IOERR)
CLOSE
MESSAGE "k " + STR$(IOERR)
NAME "IN.TXT" AS "OUT.TXT"
MESSAGE "l " + STR$(IOERR)
END
'''
        alerts, files = run(src, files={"IN.TXT": b"line\n"})
        self.assertEqual(alerts, ["a 0", "b 241", "c 4", "d 242", "e 242", "f 242 keep", "g 242",
                                  "h 0", "i 5", "j 5", "k 0", "l 80"])
        self.assertEqual(files, {"IN.TXT": b"line\n", "OUT.TXT": b"first\r\n"})

    def test_os_errors_reach_ioerr(self):
        write = '''OPEN "OUT.TXT" FOR OUTPUT AS #1
MESSAGE "open " + STR$(IOERR)
PRINT #1, "x"
MESSAGE "print " + STR$(IOERR)
CLOSE #1
MESSAGE "close " + STR$(IOERR)
END
'''
        self.assertEqual(run(write, faults={146: 0xA3})[0], ["open 0", "print 163", "close 0"])
        self.assertEqual(run(write, faults={144: 0x13})[0], ["open 19", "print 242", "close 242"])
        self.assertEqual(run(write, faults={127: 1})[0], ["open 240", "print 242", "close 242"])
        self.assertEqual(run(write, location=FileLocation(folder="\\PCW\\NOSUCH"))[0],
                         ["open 3", "print 242", "close 242"])
        read = READER.replace('OPEN "IN.TXT"', 'OPEN "IN.TXT"')
        alerts, _ = run(read, files={"IN.TXT": b"abc\n"}, faults={147: 0xD1})
        self.assertEqual(alerts, ["open 0", "after 209 []", "close 0"])

    def test_line_input_into_an_array_and_index_error(self):
        src = '''DIM A$(2) AS STRING
DIM I AS INTEGER
OPEN "IN.TXT" FOR INPUT AS #1
WHILE NOT EOF(1)
    I = I + 1
    LINE INPUT #1, A$(I)
WEND
MESSAGE A$(1) + "/" + A$(2)
END
'''
        alerts, _ = run(src, files={"IN.TXT": b"p\nq\n"})
        self.assertEqual(alerts, ["p/q"])
        alerts, _ = run(src, files={"IN.TXT": b"p\nq\nr\n"})
        self.assertEqual(alerts, ["Runtime error: index out of range at line 6"])

    def test_many_records(self):
        src = '''DIM I AS INTEGER
DIM L$ AS STRING
DIM Sum AS INTEGER
OPEN "BIG.DAT" FOR OUTPUT AS #2
FOR I = 1 TO 300
    PRINT #2, "Entry number " + STR$(I) + " with some text"
NEXT I
CLOSE #2
OPEN "BIG.DAT" FOR INPUT AS #1
WHILE NOT EOF(1)
    LINE INPUT #1, L$
    Sum = Sum + VAL(MID$(L$, 14, 3))
WEND
CLOSE
MESSAGE STR$(Sum) + " " + STR$(IOERR)
END
'''
        alerts, files = run(src)
        total = sum(range(1, 301))  # 45150, which wraps in 16 bits (LANGUAGE-SPEC §2)
        self.assertEqual(alerts, [f"{(total + 32768) % 65536 - 32768} 0"])
        self.assertEqual(len(files["BIG.DAT"]), sum(len(f"Entry number {i} with some text") + 2
                                                    for i in range(1, 301)))
