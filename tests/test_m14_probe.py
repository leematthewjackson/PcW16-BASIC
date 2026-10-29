"""developer-tests/m14prb.pbas, M14PRB: the owner's XAnne probe of the M14 runtime
corrections (docs/M14-ACCEPTANCE.md, session F), on the simulator. Each
button shows the result the guide expects, twice in one session (each
scenario removes its own files first), and every line differs when the
program is built with the M13 code (--legacy-file-safety,
--legacy-real-rounding): the probe tells the two apart."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run
from pbas import check_source
from pbas.layout import build_dialog
from toolchain import requires_files, requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import m14_sample_data  # noqa: E402

PATH = ROOT / "developer-tests" / "m14prb.pbas"
SRC = PATH.read_text(encoding="utf-8")
F = "\\PCW\\FOLDER01"
EXPECTED = [
    "1 design 0, again 0, picture 253 (want 0, 0, 253); from BAK 0 1 2 (want 0 1 2)",
    "2 saves 0, after KILL 0, BAK kept 0 (want 0, 0, 0)",
    "3 saves 0 0, load 249 0 0 (want 0 0, 249 0 0)",
    "4 load 251 0 (want 251 0)",
    "5 correctly rounded",
]


def events():
    """Buttons 1 to 5 twice, then Quit (session F)."""
    prog = check_source(SRC)
    lay = build_dialog(prog, prog.windows[0], False)
    b = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
    names = ["1 Companion", "2 Backup", "3 Type", "4 Field", "5 Round"]
    return [("click", b[n]) for n in names] * 2 + [("click", b["Quit"])]


EVENTS = events()


def session(legacy=False):
    disk = z80sim.Disk(files={(F, "M14S.PDB"): m14_sample_data.unterminated()})
    r = guarded_run(SRC, disk=disk, path=PATH, events=EVENTS,
                    build_options={"runtime_sections": "all", "legacy_file_safety": legacy,
                                   "legacy_real_rounding": legacy})
    assert not r.violations, r.violations[:2]
    return r


@requires_pasmo
class ProbeTests(unittest.TestCase):
    def test_every_line_is_what_the_guide_expects(self):
        r = session()
        self.assertEqual(r.alerts, EXPECTED * 2)
        self.assertTrue(r.cpu.exited)

    def test_the_m13_code_fails_every_line(self):
        got = session(legacy=True).alerts
        self.assertEqual(len(got), 10)
        for line in got:
            self.assertNotIn(line, EXPECTED)

    def test_the_data_file(self):
        data = m14_sample_data.unterminated()
        self.assertEqual(data[:4], b"PDB1")
        self.assertNotIn(b"\0", data[18:29])  # the field: 11 bytes, no 0
        art = ROOT / "artifacts" / "m14" / "M14S.PDB"
        if art.exists():
            self.assertEqual(art.read_bytes(), data)



@requires_pasmo
class ApplicationTests(unittest.TestCase):
    """Session G2-G5: DESIGNER's design and backup survive a PAINT II picture of the same name."""

    def test_g2_to_g5(self):
        import test_m13_designer as td
        import test_m13_paint2 as tp
        from memguard import string_var

        def disc(r):
            return {n: v for (f, n), v in r.cpu.disk.files.items() if f == F and not n.endswith(".PRG")}
        r = td.run([td.SAMPLE] + td.NOTHING + td.files("FORM", "Save as") + [td.SAVE], answers=[1])
        self.assertEqual(string_var(r, "APPSTATUS$"), "9 objects FORM.DSN")
        files = disc(r)
        self.assertIn("FORM.BAK", files)
        r = td.run([td.EXPORT, ("edit", td.FB["FILENAME$"], "FORM"), td.FB["Picture"]] + td.NOTHING
                   + [td.OPEN, ("edit", td.FB["FILENAME$"], "FORM"), td.FB["Open"]], disk_files=files, answers=[1])
        self.assertEqual(string_var(r, "APPSTATUS$"), "9 objects FORM.DSN")
        files = disc(r)
        self.assertIn("FORM.PBI", files)
        ev = tp.stroke([(10, 10), (20, 10)]) + [tp.OPEN, ("edit", tp.FB["FILENAME$"], "FORM"), ("click", tp.FB["Save as"])]
        r = tp.run(ev, files=files, answers=[2])
        self.assertEqual(r.alerts, ["Not saved: error 253", "Unsaved changes"])
        after = disc(r)
        for name in ("FORM.DSN", "FORM.BAK", "FORM.PBI"):
            self.assertEqual(after[name], files[name], name)
        r = td.run([td.OPEN, ("edit", td.FB["FILENAME$"], "FORM"), td.FB["Open"]], disk_files=after, answers=[1])
        self.assertEqual(string_var(r, "APPSTATUS$"), "9 objects FORM.DSN")



@requires_pasmo
class ArtefactTests(unittest.TestCase):
    """artifacts/m14 (the owner's retest set) is exactly what this source builds, and only
    the programs whose code M14 changed differ from the accepted artifacts/m13-rt7."""

    @requires_files(ROOT / "artifacts" / "m14" / "MANIFEST.md", what="the owner's M14 retest set")
    def test_rebuild(self):
        import hashlib
        import tempfile
        import package
        art = ROOT / "artifacts" / "m14"
        listed = (art / "MANIFEST.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            made = package.build_programs(Path(tmp), ROOT, programs=package.PROGRAMS + package.RETEST,
                                          legacy_stop=True)  # M15: as built for the M14 retest
            for name, _ in made:
                data = (Path(tmp) / name).read_bytes()
                self.assertEqual(data, (art / name).read_bytes(), name)
                self.assertIn(hashlib.sha256(data).hexdigest(), listed, name)
        changed = sorted(p.name for p in art.glob("*.PRG") if (ROOT / "artifacts" / "m13-rt7" / p.name).exists()
                         and p.read_bytes() != (ROOT / "artifacts" / "m13-rt7" / p.name).read_bytes())
        self.assertEqual(changed, ["DESIGNER.PRG", "PAINT2.PRG", "SPRITED.PRG"])


if __name__ == "__main__":
    unittest.main()
