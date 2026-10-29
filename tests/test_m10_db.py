"""M10 Stage B: databases (LANGUAGE-SPEC §5.9; runtime "M10 databases").

A database is a BANKED array of records plus an INTEGER count, saved whole
as a PDB1 file. These tests compare the compiled runtime with an
independent Python encoder of the file format (pdb() below, written from
the specification, not from the compiler), and drive the save's safe
replacement and DB LOAD's recovery through injected Rosanne errors at every
step (z80sim.Disk faults_at: exactly the n-th call of a filing function
fails). Every run is checked by the memory guard. Simulator evidence only:
Rosanne's behaviour is what the owner observes in XAnne.
"""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run
from pbas import SourceError, check_source, generate
from toolchain import requires_pasmo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pdbcheck  # noqa: E402  (the host checker: another reading of the format)

F = "\\PCW\\FOLDER01"
INDEX_ERR = "Runtime error: index out of range at line {}"

PERSON = """TYPE Person
    Id AS INTEGER
    Name AS STRING * 20
    Score AS INTEGER
    Flag AS BOOLEAN
END TYPE
"""
PERSON_SIG = "ID:I;NAME:S20;SCORE:I;FLAG:B"
PERSON_SIZE = 2 + 21 + 2 + 2


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE, table-driven (the compiler's is bitwise)."""
    table = []
    for i in range(256):
        c = i << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
        table.append(c)
    crc = 0xFFFF
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ table[((crc >> 8) ^ b) & 0xFF]
    return crc


def person(pid: int, name: str, score: int, flag: bool) -> bytes:
    return (struct.pack("<h", pid) + name.encode("ascii").ljust(21, b"\0")
            + struct.pack("<hH", score, 1 if flag else 0))


def pdb(records: list[bytes], size: int, sig: str, next_id: int, *, magic=b"PDB1", version=1,
        flags=0, count=None, reserved=0) -> bytes:
    """A PDB1 file (LANGUAGE-SPEC §5.9) from the specification."""
    head = (magic + bytes((version, flags)) + struct.pack("<HhhHH", size,
            len(records) if count is None else count, next_id, crc16(sig.encode()), reserved))
    body = head + b"".join(records)
    s1 = s2 = 0
    for b in body:
        s1 = (s1 + b) & 0xFFFF
        s2 = (s2 + s1) & 0xFFFF
    return body + struct.pack("<HH", s1, s2)


PEOPLE = [person(1, "Ann", 31, True), person(2, "Bob", 42, False), person(5, "Cy", -7, True)]
GOOD = pdb(PEOPLE, PERSON_SIZE, PERSON_SIG, 6)
OLD = pdb(PEOPLE[:1], PERSON_SIZE, PERSON_SIG, 2)


def run(src: str, files=None, legacy=False, **disk_options):
    """*legacy* (M14): built with --legacy-file-safety, the save and load code the owner accepted."""
    disk = z80sim.Disk(files={(F, name): data for name, data in (files or {}).items()},
                       **disk_options)
    r = guarded_run(src, disk=disk, build_options={"legacy_file_safety": True, "legacy_tasks_stop": True} if legacy else None)
    assert r.violations == [], r.violations[:5]
    assert disk.open_at_exit in (None, (None, None)), disk.open_at_exit
    return r


def files_of(r) -> dict[str, bytes]:
    return {name: data for (folder, name), data in r.cpu.disk.files.items() if folder == F}


def load_program(name: str = '"PEOPLE.PDB"', cap: int = 10, typ: str = PERSON) -> str:
    return typ + f"""DIM P({cap}) AS Person BANKED
DIM N AS INTEGER
DIM I AS INTEGER
DIM S$ AS STRING
N = 99
DB LOAD P, N, {name}
S$ = STR$(IOERR) + " " + STR$(N) + " " + STR$(DBRECOVERED) + " " + STR$(DBNEXTID(P))
MESSAGE S$
I = 1
WHILE I <= N
    S$ = STR$(P(I).Id) + "," + P(I).Name + "," + STR$(P(I).Score)
    IF P(I).Flag THEN
        S$ = S$ + ",T"
    END IF
    MESSAGE S$
    I = I + 1
WEND
END
"""


PEOPLE_LINES = ["1,Ann,31,T", "2,Bob,42", "5,Cy,-7,T"]

SAVE_PROGRAM = PERSON + """DIM P(10) AS Person BANKED
DIM N AS INTEGER
DIM S$ AS STRING
DB LOAD P, N, "PEOPLE.PDB"
DB NEW P, N
P(N).Name = "Dee"
P(N).Score = 8
DB SAVE P, N, "PEOPLE.PDB"
S$ = STR$(IOERR) + " " + STR$(N)
MESSAGE S$
END
"""
SAVED = pdb(PEOPLE + [person(6, "Dee", 8, False)], PERSON_SIZE, PERSON_SIG, 7)


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> str:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return str(caught.exception)

    def test_rules(self):
        base = PERSON + "DIM N AS INTEGER\nDIM A(5) AS INTEGER\n"
        cases = {
            "DIM P(5) AS Person\nDB NEW P, N\nEND\n": "needs a database: a BANKED array of records",
            "DIM P AS Person\nDB NEW P, N\nEND\n": "needs a database",
            "DIM P(5) AS Person BANKED\nDB NEW P, 3\nEND\n": "give a plain INTEGER variable",
            "DIM P(5) AS Person BANKED\nDB LOAD P, A(1), \"X.PDB\"\nEND\n": "plain INTEGER variable",
            "DIM P(5) AS Person BANKED\nDB SAVE P, N, 5\nEND\n": "the file name is a STRING",
            "DIM P(5) AS Person BANKED\nDB DELETE P, N, \"x\"\nEND\n": "the record number is an INTEGER",
            "DIM P(5) AS Person BANKED\nDB FLY P, N\nEND\n": "expected LOAD, SAVE, NEW, DELETE, SORT or SEARCH",
            "DIM P(5) AS Person BANKED\nDB SAVE P, N, \"X.PDB\", NOCASE\nEND\n": "DB SAVE takes nothing here",
            "DIM P(5) AS Person BANKED\nN = DBFIND(A, N, 1)\nEND\n": "needs a database",
            "DIM P(5) AS Person BANKED\nDB SAVE P, N, \"X.BAK\"\nEND\n": ".NEW and .BAK are the database's own",
            "DIM P(5) AS Person BANKED\nDB LOAD P, N, \"x.new\"\nEND\n": ".NEW and .BAK are the database's own",
        }
        for body, message in cases.items():
            with self.subTest(body=body):
                self.assertIn(message, self.reject(base + body))

    def test_identifier_field_must_be_integer(self):
        src = ("TYPE Tag\n    Label AS STRING * 8\n    Id AS INTEGER\nEND TYPE\n"
               "DIM T(5) AS Tag BANKED\nDIM N AS INTEGER\nDB NEW T, N\nEND\n")
        self.assertIn("first field of TYPE TAG, which must be INTEGER", self.reject(src))
        # LOAD / SAVE / DELETE do not use identifiers
        generate(check_source(src.replace("DB NEW T, N", 'DB SAVE T, N, "T.PDB"\nDB DELETE T, N, 1')))

    def test_signature_is_the_field_list(self):
        asm = generate(check_source(load_program()))
        self.assertIn(f"cgdb_P: dw cgbank_P,{crc16(PERSON_SIG.encode())},cgdbid_P", asm)


@requires_pasmo
class FormatTests(unittest.TestCase):
    """The saved bytes are exactly the specification's."""

    def test_first_save(self):
        r = run(SAVE_PROGRAM.replace('DB LOAD P, N, "PEOPLE.PDB"\n', ""))
        self.assertEqual(r.alerts, ["0 1"])
        self.assertEqual(files_of(r), {"PEOPLE.PDB": pdb([person(1, "Dee", 8, False)], PERSON_SIZE,
                                                         PERSON_SIG, 2)})

    def test_save_replaces_and_keeps_a_backup(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                r = run(SAVE_PROGRAM, {"PEOPLE.PDB": GOOD, "PEOPLE.BAK": OLD}, legacy=legacy)
                self.assertEqual(r.alerts, ["0 4"])
                self.assertEqual(files_of(r), {"PEOPLE.PDB": SAVED, "PEOPLE.BAK": GOOD})
                self.assertEqual(pdbcheck.check(SAVED, PERSON_SIG, 10)[0], 0)
                self.assertEqual(pdbcheck.decode(SAVED, PERSON_SIG, 9)[3], [6, "Dee", 8, False])
                log = [entry for entry in r.cpu.os_log if entry[0] in (144, 153, 154)]
                m14 = [] if legacy else [
                    (144, ("PEOPLE.NEW", 0)),             # 0 (M14) is NAME.NEW another file's? (not there)
                    (144, ("PEOPLE.BAK", 0)),             # 0 (M14) is NAME.BAK? (this TYPE's: yes)
                ]
                there = [] if legacy else [(144, ("PEOPLE.PDB", 0))]  # (M14) is the file there?
                self.assertEqual(log, [
                    (144, ("PEOPLE.PDB", 0)),             # DB LOAD
                    *m14,
                    (144, ("PEOPLE.NEW", 1)),             # 1 write the new file
                    (144, ("PEOPLE.NEW", 0)),             # 2 read it back
                    *there,
                    (153, "PEOPLE.BAK"),                  # 3 the old backup goes
                    (154, ("PEOPLE.PDB", "PEOPLE.BAK")),  # 4 the file becomes the backup
                    (154, ("PEOPLE.NEW", "PEOPLE.PDB")),  # 5 the new file takes its name
                ])

    def test_empty_database(self):
        src = PERSON + 'DIM P(3) AS Person BANKED\nDIM N AS INTEGER\nDB SAVE P, N, "E.PDB"\nMESSAGE STR$(IOERR)\nEND\n'
        r = run(src)
        self.assertEqual(files_of(r), {"E.PDB": pdb([], PERSON_SIZE, PERSON_SIG, 0)})
        r = run(load_program('"E.PDB"'), files_of(r))
        self.assertEqual(r.alerts, ["0 0 0 1"])

    def test_large_records_across_blocks(self):
        # 383-byte records: three reads of 128 / 128 / 127 bytes each; 42 to
        # a 16K block, so 60 records use two blocks.
        typ = ("TYPE Note\n    Id AS INTEGER\n    A AS STRING * 126\n    B AS STRING * 126\n"
               "    C AS STRING * 126\nEND TYPE\n")
        sig = "ID:I;A:S126;B:S126;C:S126"
        src = typ + """DIM T(60) AS Note BANKED
DIM N AS INTEGER
DIM I AS INTEGER
FOR I = 1 TO 60
    DB NEW T, N
    T(N).A = "a" + STR$(I)
    T(N).B = STRING$(126, 64 + I MOD 26)
    T(N).C = STR$(I * 3)
NEXT I
DB SAVE T, N, "NOTES.DAT"
MESSAGE STR$(IOERR)
END
"""
        r = run(src)
        self.assertEqual(r.alerts, ["0"])

        def note(i):
            return (struct.pack("<h", i) + f"a{i}".encode().ljust(127, b"\0")
                    + bytes([64 + i % 26]) * 126 + b"\0" + str(i * 3).encode().ljust(127, b"\0"))
        expected = pdb([note(i) for i in range(1, 61)], 383, sig, 61)
        self.assertEqual(files_of(r)["NOTES.DAT"], expected)
        check = typ + """DIM T(60) AS Note BANKED
DIM N AS INTEGER
DIM S$ AS STRING
DB LOAD T, N, "NOTES.DAT"
S$ = STR$(IOERR) + " " + STR$(N) + " " + T(43).A + " " + LEFT$(T(60).B, 3)
S$ = S$ + " " + T(42).C
MESSAGE S$
END
"""
        r = run(check, {"NOTES.DAT": expected})
        self.assertEqual(r.alerts, ["0 60 a43 HHH 126"])
        # every read is at most 128 bytes into the 640-byte rt_file_buf (a
        # read may fill to the end of the 512-byte disc block, M4)
        reads = [entry[1] for entry in r.cpu.os_log if entry[0] == z80sim.FN_OS_READ_FILE]
        self.assertEqual(max(reads), 128)
        self.assertEqual(len(reads), 1 + 3 * 60 + 1 + 1)

    def test_real_fields_round_trip(self):
        typ = "TYPE M\n    Id AS INTEGER\n    V AS REAL\nEND TYPE\n"
        src = typ + """DIM T(4) AS M BANKED
DIM N AS INTEGER
DIM K AS INTEGER
DB NEW T, N
T(N).V = 3.25
DB NEW T, N
T(N).V = -0.001
DB SAVE T, N, "M.PDB"
T(1).V = 0
T(2).V = 0
DB LOAD T, K, "M.PDB"
MESSAGE STR$(IOERR) + " " + STR$(K) + " " + STR$(T(1).V) + " " + STR$(T(2).V)
END
"""
        r = run(src)
        self.assertEqual(r.alerts, ["0 2 3.25 -0.001"])


@requires_pasmo
class LoadTests(unittest.TestCase):
    def test_good_file(self):
        r = run(load_program(), {"PEOPLE.PDB": GOOD})
        self.assertEqual(r.alerts, ["0 3 0 6"] + PEOPLE_LINES)

    def test_string_name(self):
        src = load_program("F$").replace("N = 99\n", 'DIM F$ AS STRING\nF$ = "people.pdb"\nN = 99\n')
        r = run(src, {"PEOPLE.PDB": GOOD})
        self.assertEqual(r.alerts, ["0 3 0 6"] + PEOPLE_LINES)

    def test_no_file(self):
        r = run(load_program(), {})
        self.assertEqual(r.alerts, ["2 0 0 1"])

    def test_a_failed_load_resets_the_database(self):
        src = PERSON + """DIM P(5) AS Person BANKED
DIM N AS INTEGER
DB LOAD P, N, "PEOPLE.PDB"
MESSAGE STR$(N) + " " + STR$(DBNEXTID(P)) + " " + STR$(DBRECOVERED)
DB LOAD P, N, "OTHER.PDB"
MESSAGE STR$(IOERR) + " " + STR$(N) + " " + STR$(DBNEXTID(P)) + " " + STR$(DBRECOVERED)
END
"""
        r = run(src, {"PEOPLE.NEW": GOOD})
        self.assertEqual(r.alerts, ["3 6 1", "2 0 1 0"])

    def test_recovery_order(self):
        newer = pdb(PEOPLE[:2], PERSON_SIZE, PERSON_SIG, 3)
        damaged = GOOD[:-1] + bytes([GOOD[-1] ^ 1])
        cases = [
            ({"PEOPLE.NEW": newer, "PEOPLE.BAK": OLD}, ["0 2 1 3"] + PEOPLE_LINES[:2]),
            ({"PEOPLE.PDB": damaged, "PEOPLE.BAK": OLD}, ["0 1 2 2"] + PEOPLE_LINES[:1]),
            ({"PEOPLE.PDB": damaged, "PEOPLE.NEW": damaged, "PEOPLE.BAK": OLD},
             ["0 1 2 2"] + PEOPLE_LINES[:1]),
            ({"PEOPLE.PDB": GOOD, "PEOPLE.NEW": newer, "PEOPLE.BAK": OLD}, ["0 3 0 6"] + PEOPLE_LINES),
            ({"PEOPLE.PDB": damaged}, ["251 0 0 1"]),
            ({"PEOPLE.NEW": b"junk" * 8, "PEOPLE.BAK": damaged}, ["248 0 0 1"]),
            ({"PEOPLE.NEW": b"junk", "PEOPLE.BAK": damaged}, ["251 0 0 1"]),
        ]
        for files, alerts in cases:
            with self.subTest(files=sorted(files)):
                self.assertEqual(run(load_program(), files).alerts, alerts)

    def test_damage_is_detected(self):
        other_sig = pdb(PEOPLE, PERSON_SIZE, "ID:I;NAME:S20;SCORE:I;FLOG:B", 6)
        cases = {
            "not a database": (b"PDB2" + GOOD[4:], 248),
            "too short for a header": (GOOD[:10], 251),
            "empty": (b"", 251),
            "another version": (pdb(PEOPLE, PERSON_SIZE, PERSON_SIG, 6, version=2), 250),
            "flags": (pdb(PEOPLE, PERSON_SIZE, PERSON_SIG, 6, flags=1), 250),
            "reserved bytes": (pdb(PEOPLE, PERSON_SIZE, PERSON_SIG, 6, reserved=1), 250),
            "another record size": (pdb([p + b"\0" for p in PEOPLE], PERSON_SIZE + 1, PERSON_SIG, 6), 249),
            "another TYPE": (other_sig, 249),
            "a changed byte": (GOOD[:30] + bytes([GOOD[30] ^ 0x20]) + GOOD[31:], 251),
            "a changed check": (GOOD[:-3] + bytes([GOOD[-3] ^ 1]) + GOOD[-2:], 251),
            "cut in a record": (GOOD[:16 + PERSON_SIZE + 5], 251),
            "cut in the check": (GOOD[:-2], 251),
            "a byte after the end": (GOOD + b"\0", 251),
            "count above the array": (pdb(PEOPLE * 4, PERSON_SIZE, PERSON_SIG, 6), 252),
            "negative count": (pdb(PEOPLE, PERSON_SIZE, PERSON_SIG, 6, count=-3), 251),
            "count says more than there is": (pdb(PEOPLE, PERSON_SIZE, PERSON_SIG, 6, count=4), 251),
        }
        for what, (data, code) in cases.items():
            with self.subTest(what):
                self.assertEqual(run(load_program(), {"PEOPLE.PDB": data}).alerts, [f"{code} 0 0 1"])
                self.assertEqual(pdbcheck.check(data, PERSON_SIG, 10)[0], code)

    def test_exactly_full_array(self):
        r = run(load_program(cap=3), {"PEOPLE.PDB": GOOD})
        self.assertEqual(r.alerts, ["0 3 0 6"] + PEOPLE_LINES)
        r = run(load_program(cap=2), {"PEOPLE.PDB": GOOD})
        self.assertEqual(r.alerts, ["252 0 0 1"])

    def test_reserved_extensions_are_refused(self):
        # a STRING name at run time (a literal is refused by the compiler)
        for name in ('"PEOPLE.NEW"', '"people.bak"'):
            with self.subTest(name=name):
                src = load_program("F$").replace("N = 99\n", f"DIM F$ AS STRING\nF$ = {name}\nN = 99\n")
                r = run(src, {"PEOPLE.NEW": GOOD, "PEOPLE.BAK": GOOD})
                self.assertEqual(r.alerts, ["247 0 0 1"])
        src = SAVE_PROGRAM.replace('DB SAVE P, N, "PEOPLE.PDB"', 'F$ = "PEOPLE.BAK"\nDB SAVE P, N, F$')
        src = src.replace("DIM S$ AS STRING", "DIM S$ AS STRING\nDIM F$ AS STRING")
        r = run(src, {"PEOPLE.PDB": GOOD})
        self.assertEqual(r.alerts, ["247 4"])
        self.assertEqual(files_of(r), {"PEOPLE.PDB": GOOD})

    def test_missing_folder(self):
        r = guarded_run(load_program(), disk=z80sim.Disk(folders=("\\", "\\PCW")))
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["3 0 0 1"])


@requires_pasmo
class SaveFailureTests(unittest.TestCase):
    """Every failing step leaves a file DB LOAD reads (LANGUAGE-SPEC §5.9)."""

    def after(self, files_before, alerts, files_after, **disk_options):
        r = run(SAVE_PROGRAM, files_before, **disk_options)
        self.assertEqual(r.alerts, alerts)
        self.assertEqual(files_of(r), files_after)
        return files_of(r)

    def test_each_step(self):
        # M14: the call numbers of the M14 sequence (two companion checks and the
        # file check come first); test_each_step_as_accepted keeps the M10 numbers
        self.each_step({144: 4, 145: 3, 147: 11}, legacy=False)
        before = {"PEOPLE.PDB": GOOD, "PEOPLE.BAK": OLD}
        unchanged = dict(before)
        # 0 (M14): a companion check that fails changes nothing
        self.after(before, ["5 4"], unchanged, faults_at={144: {3: 0x05}})
        self.after(before, ["11 4"], unchanged, faults_at={147: {7: 0x0B}})

    def test_each_step_as_accepted(self):
        self.each_step({144: 2, 145: 2, 147: 9}, legacy=True)

    def each_step(self, n, legacy):
        before = {"PEOPLE.PDB": GOOD, "PEOPLE.BAK": OLD}
        unchanged = dict(before)
        cases = [
            # 1: the new file's open, a record's write, the close
            ({144: {n[144]: 0xA3}}, ["163 4"], unchanged),
            ({146: {1: 0xA3}}, ["163 4"], unchanged),
            ({146: {3: 0xA3}}, ["163 4"], unchanged),
            ({145: {n[145]: 0x07}}, ["7 4"], unchanged),
            # 2: reading it back
            ({147: {n[147]: 0x07}}, ["7 4"], unchanged),
            # 3: deleting the old backup (a failure other than "not found")
            ({153: {1: 0x05}}, ["5 4"], unchanged),
            # 4: renaming the file to the backup: the file is unchanged, the
            # old backup is already gone
            ({154: {1: 0x05}}, ["5 4"], {"PEOPLE.PDB": GOOD}),
            # 5: renaming the new file: both copies remain, DB LOAD finds the new one
            ({154: {2: 0x05}}, ["5 4"], {"PEOPLE.NEW": SAVED, "PEOPLE.BAK": GOOD}),
        ]
        for faults, alerts, after in cases:
            with self.subTest(faults=faults, legacy=legacy):
                left = self.after(before, alerts, after, faults_at=faults, legacy=legacy)
                r = run(load_program(), left, legacy=legacy)
                if "PEOPLE.NEW" in left:
                    self.assertEqual(r.alerts[0], "0 4 1 7")
                else:
                    self.assertEqual(r.alerts, ["0 3 0 6"] + PEOPLE_LINES)

    def test_read_back_catches_a_bad_new_file(self):
        # A Rosanne that did not truncate on open (the alternative to
        # hypothesis H-TRUNC) would leave a longer stale NAME.NEW's tail:
        # the read-back sees bytes after the check and the save stops.
        stale = GOOD * 3
        before = {"PEOPLE.PDB": GOOD, "PEOPLE.NEW": stale}
        r = run(SAVE_PROGRAM, before, truncate_on_open=False)
        self.assertEqual(r.alerts, ["251 4"])
        self.assertEqual(files_of(r), {"PEOPLE.PDB": GOOD})

    def test_first_save_steps_tolerate_missing_files(self):
        src = SAVE_PROGRAM.replace('DB LOAD P, N, "PEOPLE.PDB"\n', "")
        # M10: delete .BAK and rename the file, both "not found", then the rename of .NEW;
        # M14: with no file, steps 3 and 4 are skipped (a .BAK there would be kept)
        for legacy, calls in ((True, 3), (False, 1)):
            with self.subTest(legacy=legacy):
                r = run(src, {}, legacy=legacy)
                self.assertEqual(r.alerts, ["0 1"])
                results = [entry for entry in r.cpu.os_log if entry[0] in (153, 154)]
                self.assertEqual(len(results), calls)
                self.assertEqual(sorted(files_of(r)), ["PEOPLE.PDB"])

    def test_save_count_outside_the_array(self):
        for count in ("11", "-1"):
            with self.subTest(count=count):
                src = PERSON + (f"DIM P(10) AS Person BANKED\nDIM N AS INTEGER\nN = {count}\n"
                                'DB SAVE P, N, "PEOPLE.PDB"\nEND\n')
                r = run(src, {"PEOPLE.PDB": GOOD})
                self.assertEqual(r.alerts, [INDEX_ERR.format(10)])
                self.assertEqual(files_of(r), {"PEOPLE.PDB": GOOD})


@requires_pasmo
class RecordOpTests(unittest.TestCase):
    def test_new_until_full(self):
        src = PERSON + """DIM P(3) AS Person BANKED
DIM N AS INTEGER
DIM I AS INTEGER
FOR I = 1 TO 4
    DB NEW P, N
    MESSAGE STR$(IOERR) + " " + STR$(N) + " " + STR$(P(N).Id) + " " + STR$(DBNEXTID(P))
NEXT I
END
"""
        r = run(src)
        self.assertEqual(r.alerts, ["0 1 1 2", "0 2 2 3", "0 3 3 4", "252 3 3 4"])

    def test_new_clears_the_element_and_continues_the_file_ids(self):
        src = PERSON + """DIM P(5) AS Person BANKED
DIM N AS INTEGER
P(4).Name = "old"
P(4).Score = 9
P(4).Flag = TRUE
DB LOAD P, N, "PEOPLE.PDB"
DB NEW P, N
MESSAGE STR$(N) + " " + STR$(P(N).Id) + "[" + P(N).Name + "]" + STR$(P(N).Score)
IF P(N).Flag THEN
    MESSAGE "flag"
END IF
END
"""
        r = run(src, {"PEOPLE.PDB": GOOD})
        self.assertEqual(r.alerts, ["4 6[]0"])

    def test_identifiers_run_out(self):
        last = pdb(PEOPLE, PERSON_SIZE, PERSON_SIG, 32767)
        src = PERSON + """DIM P(9) AS Person BANKED
DIM N AS INTEGER
DB LOAD P, N, "PEOPLE.PDB"
DB NEW P, N
MESSAGE STR$(IOERR) + " " + STR$(N) + " " + STR$(P(N).Id)
DB NEW P, N
MESSAGE STR$(IOERR) + " " + STR$(N)
END
"""
        r = run(src, {"PEOPLE.PDB": last})
        self.assertEqual(r.alerts, ["0 4 32767", "252 4"])

    def test_delete_keeps_order(self):
        src = PERSON + """DIM P(5) AS Person BANKED
DIM N AS INTEGER
DIM I AS INTEGER
DIM S$ AS STRING
DB LOAD P, N, "PEOPLE.PDB"
DB DELETE P, N, 2
S$ = STR$(N)
FOR I = 1 TO 3
    S$ = S$ + " " + STR$(P(I).Id) + P(I).Name
NEXT I
MESSAGE S$
DB DELETE P, N, 2
DB DELETE P, N, 1
MESSAGE STR$(N) + " " + STR$(P(1).Id) + "[" + P(1).Name + "]"
END
"""
        r = run(src, {"PEOPLE.PDB": GOOD})
        self.assertEqual(r.alerts, ["2 1Ann 5Cy 0", "0 0[]"])

    def test_delete_outside_the_count(self):
        for k in ("0", "4", "-1"):
            with self.subTest(k=k):
                src = PERSON + (f"DIM P(5) AS Person BANKED\nDIM N AS INTEGER\n"
                                f'DB LOAD P, N, "PEOPLE.PDB"\nDB DELETE P, N, {k}\nEND\n')
                r = run(src, {"PEOPLE.PDB": GOOD})
                self.assertEqual(r.alerts, [INDEX_ERR.format(10)])

    def test_find(self):
        dup = pdb(PEOPLE + [person(2, "Two", 0, False)], PERSON_SIZE, PERSON_SIG, 6)
        src = PERSON + """DIM P(5) AS Person BANKED
DIM N AS INTEGER
DB LOAD P, N, "PEOPLE.PDB"
MESSAGE STR$(DBFIND(P, N, 1)) + STR$(DBFIND(P, N, 2)) + STR$(DBFIND(P, N, 5)) + STR$(DBFIND(P, N, 3)) + STR$(DBFIND(P, N - 2, 5))
END
"""
        r = run(src, {"PEOPLE.PDB": dup})
        self.assertEqual(r.alerts, ["12300"])

    def test_edit_save_reload(self):
        src = PERSON + """DIM P(5) AS Person BANKED
DIM N AS INTEGER
DIM K AS INTEGER
DB LOAD P, N, "PEOPLE.PDB"
K = DBFIND(P, N, 2)
P(K).Name = "Robert"
P(K).Flag = TRUE
DB DELETE P, N, 1
DB SAVE P, N, "PEOPLE.PDB"
MESSAGE STR$(IOERR)
END
"""
        r = run(src, {"PEOPLE.PDB": GOOD})
        self.assertEqual(r.alerts, ["0"])
        expected = pdb([person(2, "Robert", 42, True), PEOPLE[2]], PERSON_SIZE, PERSON_SIG, 6)
        self.assertEqual(files_of(r), {"PEOPLE.PDB": expected, "PEOPLE.BAK": GOOD})
        r = run(load_program(), files_of(r))
        self.assertEqual(r.alerts, ["0 2 0 6", "2,Robert,42,T", "5,Cy,-7,T"])


if __name__ == "__main__":
    unittest.main()
