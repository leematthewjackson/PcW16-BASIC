"""M14 file safety: DB SAVE, BITMAP SAVE and DB LOAD (M14-DEFECT-REGISTER.md F1 - F3).

Every test runs a program on the simulator with a model disc, injects at most
one failure (z80sim.Disk faults_at) and checks which copies remain. Each
failed on the M13-End runtime. Simulator evidence: Rosanne's own behaviour
for the calls used (open, read, delete, rename) is the one recorded since M4;
the owner's XAnne retest decides (M14-ACCEPTANCE.md).
"""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run
from test_m10_db import PERSON, PERSON_SIG, PERSON_SIZE, pdb, person
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pbicheck  # noqa: E402

F = "\\PCW\\FOLDER01"
OPEN, READ, DELETE, RENAME = 144, 147, 153, 154
OLD = pdb([person(1, "OldDesign", 1, True)], PERSON_SIZE, PERSON_SIG, 2)
PIC = pbicheck.from_rows([[1, 0] * 8] * 16)
HEAD = PERSON + "DIM P(10) AS Person BANKED\nDIM N AS INTEGER\nDIM B AS BITMAP * 16, 16\n"
DB_SAVE = HEAD + """DB LOAD P, N, "FORM.DSN"
DB NEW P, N
P(N).Name = "NewWork"
DB SAVE P, N, "FORM.DSN"
MESSAGE "db " + STR$(IOERR)
END
"""
BMP_SAVE = HEAD + """BITMAP SAVE B, "FORM.PBI"
MESSAGE "bmp " + STR$(IOERR)
END
"""
DB_LOAD = HEAD + """DB LOAD P, N, "FORM.DSN"
MESSAGE STR$(IOERR) + " " + STR$(N) + " " + STR$(DBRECOVERED)
END
"""


def run(src, disk):
    disk.calls = {}
    r = guarded_run(src, disk=disk)
    assert not r.violations, r.violations[:3]
    disk.faults_at = {}
    return r.alerts


def disk(files, **kw):
    return z80sim.Disk(files={(F, n): d for n, d in files.items()}, **kw)


def on_disc(d):
    return {n: v for (f, n), v in d.files.items() if f == F and not n.endswith(".PRG")}


def anywhere(d, data: bytes) -> bool:
    return any(data in v for v in on_disc(d).values())


@requires_pasmo
class CompanionCollision(unittest.TestCase):
    """F1 (KI-91): FORM.DSN and FORM.PBI share FORM.NEW and FORM.BAK. A save
    must not overwrite or delete the other file's companion: it refuses, 253."""

    def test_a_picture_save_keeps_a_design_left_in_form_new(self):
        d = disk({"FORM.DSN": OLD}, faults_at={RENAME: {2: 0x05}})
        self.assertEqual(run(DB_SAVE, d), ["db 5"])   # step 5 failed: new in .NEW, old in .BAK
        self.assertEqual(run(BMP_SAVE, d), ["bmp 253"])
        self.assertTrue(anywhere(d, b"NewWork") and anywhere(d, b"OldDesign"))
        self.assertEqual(run(DB_LOAD, d), ["0 2 1"])  # recovered from FORM.NEW

    def test_a_design_save_keeps_a_picture_left_in_form_new(self):
        d = disk({"FORM.DSN": OLD, "FORM.PBI": PIC}, faults_at={RENAME: {2: 0x05}})
        self.assertEqual(run(BMP_SAVE, d), ["bmp 5"])
        self.assertEqual(run(DB_SAVE, d), ["db 253"])
        self.assertEqual(d.files[(F, "FORM.BAK")], PIC)
        self.assertEqual(d.files[(F, "FORM.DSN")], OLD)

    def test_a_first_picture_save_keeps_the_designs_backup(self):
        d = disk({"FORM.DSN": OLD})
        self.assertEqual(run(DB_SAVE, d), ["db 0"])
        self.assertEqual(d.files[(F, "FORM.BAK")], OLD)
        self.assertEqual(run(BMP_SAVE, d), ["bmp 253"])
        self.assertEqual(d.files[(F, "FORM.BAK")], OLD)
        self.assertNotIn((F, "FORM.PBI"), d.files)

    def test_its_own_companions_are_replaced_as_before(self):
        d = disk({"FORM.PBI": PIC, "FORM.BAK": PIC, "FORM.NEW": PIC[:20]})
        self.assertEqual(run(BMP_SAVE, d), ["bmp 0"])
        self.assertEqual(d.files[(F, "FORM.BAK")], PIC)
        self.assertNotIn((F, "FORM.NEW"), d.files)

    def test_a_database_of_another_type_is_another_files(self):
        other = pdb([person(1, "X", 1, True)], PERSON_SIZE, "ID:I;NAME:S20;SCORE:I;FLAG:I", 2)
        d = disk({"FORM.DSN": OLD, "FORM.BAK": other})
        self.assertEqual(run(DB_SAVE, d), ["db 253"])
        self.assertEqual(d.files[(F, "FORM.BAK")], other)

    def test_a_companion_shorter_than_a_magic_is_a_leftover(self):
        d = disk({"FORM.DSN": OLD, "FORM.NEW": b"PD"})
        self.assertEqual(run(DB_SAVE, d), ["db 0"])

    def test_a_text_backup_with_the_same_name_is_kept(self):
        text = b"# Notes\r\nKept\r\n"
        d = disk({"FORM.PBI": PIC, "FORM.BAK": text})
        self.assertEqual(run(BMP_SAVE, d), ["bmp 253"])
        self.assertEqual(d.files[(F, "FORM.BAK")], text)

    def test_a_companion_that_cannot_be_read_is_reported(self):
        d = disk({"FORM.PBI": PIC, "FORM.BAK": PIC}, faults_at={READ: {1: 0x05}})
        self.assertEqual(run(BMP_SAVE, d), ["bmp 5"])
        self.assertEqual(d.files[(F, "FORM.PBI")], PIC)


@requires_pasmo
class NoFileKeepsTheBackup(unittest.TestCase):
    """F2: after a failed final rename the next session finds no file; its
    first save must not delete NAME.BAK, the only older copy."""

    S = """DIM B AS BITMAP * 16, 16
BITMAP LOAD B, "ART.PBI"
BITMAP SAVE B, "ART.PBI"
MESSAGE STR$(IOERR)
END
"""

    def test_the_old_picture_survives_the_next_session(self):
        d = disk({"ART.PBI": PIC}, faults_at={RENAME: {2: 0x05}})
        self.assertEqual(run(self.S, d), ["5"])
        self.assertEqual(sorted(on_disc(d)), ["ART.BAK", "ART.NEW"])
        self.assertEqual(run(self.S, d), ["0"])      # LOAD: not found (2); SAVE: 0
        self.assertEqual(d.files[(F, "ART.BAK")], PIC)
        self.assertEqual(sorted(on_disc(d)), ["ART.BAK", "ART.PBI"])

    def test_a_first_save_with_no_backup(self):
        d = disk({})
        self.assertEqual(run(self.S, d), ["0"])
        self.assertEqual(sorted(on_disc(d)), ["ART.PBI"])


@requires_pasmo
class LoadFallsBackOnlyOnDamage(unittest.TestCase):
    """F3: DB LOAD reads NAME.NEW / NAME.BAK only when the file is missing,
    not a database (248) or damaged (251). A whole file it cannot load here is
    reported, not silently replaced by older data."""

    OLDER = pdb([person(1, "Older", 1, True)], PERSON_SIZE, PERSON_SIG, 2)

    def load(self, files, **kw):
        return run(DB_LOAD, disk(files, **kw))

    def test_too_many_records_is_reported(self):
        big = pdb([person(i, f"P{i}", i, True) for i in range(1, 12)], PERSON_SIZE, PERSON_SIG, 12)
        self.assertEqual(self.load({"FORM.DSN": big, "FORM.BAK": self.OLDER}), ["252 0 0"])

    def test_a_read_error_is_reported(self):
        self.assertEqual(self.load({"FORM.DSN": OLD, "FORM.BAK": self.OLDER}, faults_at={READ: {1: 0x0B}}),
                         ["11 0 0"])

    def test_another_version_is_reported(self):
        v2 = pdb([person(1, "V2", 1, True)], PERSON_SIZE, PERSON_SIG, 2, version=2)
        self.assertEqual(self.load({"FORM.DSN": v2, "FORM.BAK": self.OLDER}), ["250 0 0"])

    def test_damage_still_recovers_the_backup(self):
        bad = OLD[:-1] + bytes([OLD[-1] ^ 1])
        self.assertEqual(self.load({"FORM.DSN": bad, "FORM.BAK": self.OLDER}), ["0 1 2"])

    def test_not_a_database_still_recovers_the_backup(self):
        self.assertEqual(self.load({"FORM.DSN": PIC, "FORM.BAK": self.OLDER}), ["0 1 2"])

    def test_a_missing_file_still_recovers(self):
        self.assertEqual(self.load({"FORM.NEW": OLD}), ["0 1 1"])




@requires_pasmo
class StringFieldsAreChecked(unittest.TestCase):
    """F4 (adversarial review): a PDB1 file with a correct header and check whose
    STRING field has no 0 within its capacity loaded with IOERR 0, and LEN then
    read past the field. DB LOAD now takes it as damaged (251)."""

    LOAD = PERSON + """DIM P(10) AS Person BANKED
DIM N AS INTEGER
DB LOAD P, N, "T.PDB"
MESSAGE STR$(IOERR) + " " + STR$(N) + " " + STR$(DBRECOVERED)
END
"""

    @staticmethod
    def unterminated(pid):
        return struct.pack("<h", pid) + b"X" * 21 + struct.pack("<hH", 1, 1)

    def test_a_field_without_its_0_is_damage(self):
        bad = pdb([person(1, "Ann", 1, True), self.unterminated(2)], PERSON_SIZE, PERSON_SIG, 3)
        self.assertEqual(run(self.LOAD, disk({"T.PDB": bad})), ["251 0 0"])

    def test_then_the_backup_is_loaded(self):
        bad = pdb([self.unterminated(1)], PERSON_SIZE, PERSON_SIG, 2)
        self.assertEqual(run(self.LOAD, disk({"T.PDB": bad, "T.BAK": OLD})), ["0 1 2"])

    def test_a_full_field_with_its_0_loads(self):
        full = pdb([person(1, "N" * 20, 1, True)], PERSON_SIZE, PERSON_SIG, 2)
        self.assertEqual(run(self.LOAD, disk({"T.PDB": full})), ["0 1 0"])

    def test_a_save_reads_its_own_file_back(self):
        src = PERSON + """DIM P(10) AS Person BANKED
DIM N AS INTEGER
DB NEW P, N
P(1).Name = "NNNNNNNNNNNNNNNNNNNN"
DB SAVE P, N, "T.PDB"
N = 0
DB LOAD P, N, "T.PDB"
MESSAGE STR$(IOERR) + " " + STR$(N) + " " + P(1).Name
END
"""
        self.assertEqual(run(src, disk({})), ["0 1 " + "N" * 20])


if __name__ == "__main__":
    unittest.main()
