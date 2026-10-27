"""M14 versions of accepted example applications (M14-DEFECT-REGISTER F7, F8, F9, F15).

The accepted M13 programs are kept as they were (their sources still rebuild the accepted executables byte for
byte); each defect is corrected in an M14 copy. Every test here shows the correction and, where a run can show
it, that the accepted program still has the defect, so the test cannot pass by testing the old program.
Simulator evidence, not XAnne: the owner's session H (docs/M14-ACCEPTANCE.md) is the retest.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run
from test_m7_examples import SciCalcTests, objects
from toolchain import requires_files, requires_pasmo

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@requires_pasmo
class SciCalc14Tests(SciCalcTests):
    """F15 (KI-104): every M7 case still holds, and the results near the REAL limit are refused, not fatal."""
    SRC = (EXAMPLES / "scicalc_m14.pbas").read_text()

    # Each of these overflows a REAL; the accepted program's guard (ln 88.7) let them through.
    OVER = [("1.5E19", "x * y", "1.5E19"), ("-1.5E19", "x * y", "1.5E19"), ("1E38", "x / y", "0.5"),
            ("2", "x ^ y", "127.9"), ("0.5", "x ^ y", "-127.9"), ("1.31E19", "x * y", "1.31E19")]
    # Inside the limit: computed. The guard keeps 1% in hand (e ^ 88.02 is about 1.685E+38), so 1.3E19 * 1.3E19
    # (1.69E+38, a REAL) is refused: refused, not stopped.
    UNDER = [("1.29E19", "x * y", "1.29E19", "= 1.6641E+38"), ("8E37", "x / y", "0.5", "= 1.6E+38"),
             ("2", "x ^ y", "126", "= 8.50705917E+37")]

    def test_results_near_the_limit(self):
        for x, op, y in self.OVER:
            with self.subTest(x=x, op=op, y=y):
                self.assertEqual(self.calc(x, op, y), "result too large")
        for x, op, y, want in self.UNDER:
            with self.subTest(x=x, op=op, y=y):
                self.assertEqual(self.calc(x, op, y), want)

    def test_no_product_across_the_limit_stops_the_program(self):
        # calc() itself fails on any runtime error; each is computed or refused.
        for a in ("1.28E19", "1.295E19", "1.299E19", "1.3E19", "1.302E19", "1.304E19", "1.306E19", "1.31E19"):
            with self.subTest(a=a):
                got = self.calc(a, "x * y", a)
                self.assertTrue(got == "result too large" or got.startswith("= 1.6"), got)

    def test_the_accepted_program_stops_on_them(self):
        src = (EXAMPLES / "scicalc.pbas").read_text()
        o = objects(src, 64)
        for x, op, y in self.OVER[:4]:
            with self.subTest(x=x, op=op, y=y):
                events = [("edit", o["X$"], x), ("edit", o["Y$"], y), ("drop", o["OP"], self.OPS.index(op)),
                          ("click", o["="])]
                r = guarded_run(src, events=events)
                self.assertTrue(any(a.startswith("Runtime error") for a in r.cpu.alerts), r.cpu.alerts)

    def test_only_the_guard_changed(self):
        old = (EXAMPLES / "scicalc.pbas").read_text().splitlines()
        new = self.SRC.splitlines()
        code = lambda lines: [s for s in lines if not s.lstrip().startswith("'")]
        self.assertEqual([s for s in code(new) if s not in code(old)], ["CONST BIG = 88.02"])
        self.assertEqual([s for s in code(old) if s not in code(new)], ["CONST BIG = 88.7"])



def _sprited(path, events, files=None, answers=None):
    import test_m13_sprited as ts
    disk = z80sim.Disk(files={(ts.F, n): d for n, d in (files or {}).items()})
    r = guarded_run(path.read_text(encoding="utf-8"), events=events + [ts.QUIT], disk=disk, path=path,
                    max_steps=2_000_000_000, alert_answers=answers, build_options={"runtime_sections": "all"})
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r


@requires_pasmo
class Sprited14Tests(unittest.TestCase):
    """F7 (KI-96): sprite FOO's mask FOOM.PBI is sprite FOOM's image."""
    NEW = EXAMPLES / "sprited_m14.pbas"
    OLD = EXAMPLES / "sprited.pbas"

    def test_the_accepted_program_replaces_another_sprites_image(self):
        import test_m13_sprited as ts
        ev = ts.click(ts.IMAGE, 0, 0) + [ts.name("FOOM"), ts.SAVE] + ts.click(ts.IMAGE, 5, 5) + [ts.name("FOO"), ts.SAVE]
        r = _sprited(self.OLD, ev)
        self.assertEqual(ts.pbicheck.pixels(ts.disk_file(r, "FOOM.BAK")), ts.image([(0, 0)]))  # FOOM's image...
        self.assertNotEqual(ts.pbicheck.pixels(ts.disk_file(r, "FOOM.PBI")), ts.image([(0, 0)]))  # ...replaced

    def test_a_name_ending_in_m_is_not_saved(self):
        import test_m13_sprited as ts
        for typed in ("FOOM", "m", "hero2m.pbi"):
            with self.subTest(typed):
                r = _sprited(self.NEW, ts.click(ts.IMAGE, 0, 0) + [ts.name(typed), ts.SAVE], answers=[ts.DISCARD_ANS])
                self.assertIn("Not saved: a name ending in M could be another sprite's mask file", r.alerts)
                self.assertEqual(ts.written(r), [])
                self.assertIn("Unsaved changes", r.alerts)  # still unsaved

    def test_other_names_save_and_files_named_m_still_open(self):
        import test_m13_sprited as ts
        r = _sprited(self.NEW, ts.click(ts.IMAGE, 0, 0) + [ts.name("FOO"), ts.SAVE])
        self.assertEqual(ts.saved(r, "FOO")[0], ts.image([(0, 0)]))
        files = {"FOOM.PBI": ts.disk_file(r, "FOO.PBI"), "FOOMM.PBI": ts.disk_file(r, "FOOM.PBI")}
        r2 = _sprited(self.NEW, [ts.name("FOOM"), ts.OPEN], files=files)
        self.assertEqual(ts.thumb(r2, 0), ts.image([(0, 0)]))
        self.assertEqual(ts.status(r2), "FOOM  frame 1 of 1")

    def test_only_the_save_check_changed(self):
        code = lambda p: [s for s in p.read_text().splitlines() if not s.lstrip().startswith("'")]
        old, new = code(self.OLD), code(self.NEW)
        self.assertEqual(len(new) - len(old), 4)
        self.assertEqual([s for s in new if s not in old],
                         ['    IF RIGHT$(Base$, 1) = "M" THEN',
                          '        MESSAGE "Not saved: a name ending in M could be another sprite\'s mask file"'])



FOLDER = "\\PCW\\FOLDER01"
FN_RENAME = z80sim.FN_OS_RENAME_FILE
DOC = b"Original document line one\r\nline two\r\n"


def _mdedit(path, disk, text, answers=(1, 1, 1, 1)):
    from test_m10_mdedit2 import QUIT, SAVE, keys
    disk.calls = {}
    r = guarded_run(path.read_text(encoding="utf-8"), events=keys(text) + [SAVE, QUIT], disk=disk, path=path,
                    max_steps=2_000_000_000, build_options={"runtime_sections": "all"}, alert_answers=list(answers))
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r


def _files(disk):
    return {n: v for (f, n), v in disk.files.items() if f == FOLDER and not n.endswith(".PRG")}


@requires_pasmo
class Mdedit14Tests(unittest.TestCase):
    """F8 (KI-97): after a failed final rename, the next session lost every copy of the document."""
    NEW = EXAMPLES / "mdedit4_m14.pbas"
    OLD = EXAMPLES / "mdedit4.pbas"

    def restart(self, path, failing_rename):
        disk = z80sim.Disk(files={(FOLDER, "EDTEST.MD"): DOC}, faults_at={FN_RENAME: {failing_rename: 0x05}})
        first = _mdedit(path, disk, "A")
        self.assertTrue(any(a.startswith("Only in MDEDIT4.TMP; old in EDTEST.BAK") for a in first.alerts), first.alerts)
        self.assertNotIn("EDTEST.MD", _files(disk))
        disk.faults_at = {}
        second = _mdedit(path, disk, "B")  # the next session: a keystroke and Save
        return second, _files(disk)

    def test_the_accepted_program_loses_the_document(self):
        _, files = self.restart(self.OLD, 2)
        self.assertNotIn(b"Original", b"".join(files.values()))

    def test_the_unfinished_save_and_the_backup_are_kept(self):
        r, files = self.restart(self.NEW, 3)  # rename 1 is the check at start
        self.assertIn("An unfinished save was kept as MDEDIT4.OLD: open it to recover it", r.alerts)
        self.assertEqual(files["EDTEST.BAK"], DOC)  # the file was missing: its backup is kept
        self.assertTrue(files["MDEDIT4.OLD"].startswith(b"AOriginal"))  # the first session's text
        self.assertTrue(files["EDTEST.MD"].startswith(b"B"))
        self.assertNotIn("MDEDIT4.TMP", files)

    def test_two_unfinished_saves_turn_saving_off(self):
        start = {"EDTEST.MD": DOC, "MDEDIT4.TMP": b"one\r\n", "MDEDIT4.OLD": b"two\r\n"}
        disk = z80sim.Disk(files={(FOLDER, n): v for n, v in start.items()})
        r = _mdedit(self.NEW, disk, "C")
        self.assertIn("MDEDIT4.TMP and MDEDIT4.OLD hold unfinished saves: saving is off until one is deleted",
                      r.alerts)
        self.assertIn("Not saved: MDEDIT4.TMP and MDEDIT4.OLD hold unfinished saves", r.alerts)
        self.assertEqual(_files(disk), start)

    def test_an_ordinary_save_replaces_the_backup(self):
        disk = z80sim.Disk(files={(FOLDER, "EDTEST.MD"): DOC, (FOLDER, "EDTEST.BAK"): b"older\r\n"})
        r = _mdedit(self.NEW, disk, "D")
        self.assertEqual(r.alerts, [])
        files = _files(disk)
        self.assertEqual(sorted(files), ["EDTEST.BAK", "EDTEST.MD"])
        self.assertEqual(files["EDTEST.BAK"], DOC)
        self.assertTrue(files["EDTEST.MD"].startswith(b"DOriginal"))



def _designer(path, events):
    import test_m13_designer as dz
    disk = z80sim.Disk(files={(dz.F, "P2ICONS.PBI"): dz.ICONS})
    r = guarded_run(path.read_text(encoding="utf-8"), events=events, disk=disk, path=path,
                    max_steps=1_500_000_000, alert_answers=[1, 1, 1, 1], build_options={"runtime_sections": "all"})
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r, sorted(n for (_, n) in disk.files if n != "P2ICONS.PBI" and not n.endswith(".PRG"))


@requires_pasmo
class Designer14Tests(unittest.TestCase):
    """F9 (KI-99) and F11: DSGNTMP is DESIGNER's own temporary name."""
    NEW = EXAMPLES / "designer_m14.pbas"
    OLD = EXAMPLES / "designer.pbas"

    @staticmethod
    def files_button(typed, button):
        import test_m13_designer as dz
        menu = dz.SAVEAS if button == "Save as" else dz.EXPORT
        return [dz.SAMPLE] + dz.NOTHING + [menu, ("edit", dz.FB["FILENAME$"], typed), dz.FB[button]] + dz.NOTHING

    def test_the_accepted_program_deletes_an_export_named_dsgntmp(self):
        r, names = _designer(self.OLD, self.files_button("DSGNTMP", "Picture"))
        self.assertIn("Not exported: not found", r.alerts)
        self.assertNotIn("DSGNTMP.PBI", names)  # the picture it had just written is gone

    def test_dsgntmp_is_refused_for_every_button(self):
        for typed, button, shown in (("DSGNTMP", "Picture", "DSGNTMP.PBI"), ("dsgntmp.bas", "BASIC", "DSGNTMP.BAS"),
                                     ("DSGNTMP.PBI", "Save as", "DSGNTMP.DSN")):
            with self.subTest(button=button):
                r, names = _designer(self.NEW, self.files_button(typed, button))
                self.assertIn(shown + ": invalid name", r.alerts)
                self.assertEqual(names, [])

    def test_other_names_still_save_and_export(self):
        import test_m13_designer as dz
        ev = self.files_button("FORM", "Save as") + [dz.EXPORT, ("edit", dz.FB["FILENAME$"], "DSGNTMP2"),
                                                     dz.FB["Picture"]] + dz.NOTHING
        ev += [dz.EXPORT, ("edit", dz.FB["FILENAME$"], "FORM"), dz.FB["BASIC"]] + dz.NOTHING
        r, names = _designer(self.NEW, ev)
        self.assertEqual(names, ["DSGNTMP2.PBI", "FORM.BAS", "FORM.DSN"])

    def test_only_the_name_check_changed(self):
        code = lambda p: [s for s in p.read_text().splitlines() if not s.lstrip().startswith("'")]
        old, new = code(self.OLD), code(self.NEW)
        self.assertEqual(len(new) - len(old), 4)
        self.assertEqual([s for s in new if s not in old],
                         ['    IF LEFT$(SafeOut$, 8) = "DSGNTMP." THEN',
                          "        CALL AppFail(SafeOut$, 247)  ' DESIGNER's own temporary name"])



@requires_pasmo
class Candidate2Tests(unittest.TestCase):
    """artifacts/m14-rc2 (session H) is exactly what these sources build."""

    @requires_files(EXAMPLES.parent / "artifacts" / "m14-rc2" / "MANIFEST.md", what="the M14 candidate 2 set")
    def test_rebuild(self):
        import hashlib
        import sys
        import tempfile
        sys.path.insert(0, str(EXAMPLES.parent / "tools"))
        import package
        art = EXAMPLES.parent / "artifacts" / "m14-rc2"
        listed = (art / "MANIFEST.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            made = package.build_programs(Path(tmp), EXAMPLES.parent, programs=package.CORRECTED)
            self.assertEqual(sorted(n for n, _ in made), sorted(p.name for p in art.iterdir() if p.name != "MANIFEST.md"))
            for name, _ in made:
                data = (Path(tmp) / name).read_bytes()
                self.assertEqual(data, (art / name).read_bytes(), name)
                self.assertIn(hashlib.sha256(data).hexdigest(), listed, name)


if __name__ == "__main__":
    unittest.main()
