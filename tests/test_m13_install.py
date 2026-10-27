"""M13 Stage J/K: a clean install, from exactly what a release contains.

The release folder is made with tools/package.py (the project's own files,
no prototype, no Amstrad material, the M13 programs built from that copy,
checksums). Then, using only that copy, as a new developer would:
pcw16basic doctor; a new application and a new game, each built; the
checksums verified; the release's own programs equal to builds from the
source tree; and some of the test suite run from the copy. A planted
Rosanne file must make the release be refused.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from toolchain import requires_files, requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
# M14: tools/package.py stages the private repository's release folder; it is not in the
# public repository (tools/verify_public.py checks a public copy instead)
PACKAGE = ROOT / "tools" / "package.py"
if PACKAGE.exists():
    import package  # noqa: E402


@requires_pasmo
@requires_files(PACKAGE, what="the private release packager")
class CleanInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pbw16-rel-")
        cls.release = package.stage(Path(cls.tmp.name))
        cls.cmd = [sys.executable, str(cls.release / "pcw16basic")]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def env(self):
        return dict(os.environ, PYTHONPATH="", PYTHONDONTWRITEBYTECODE="1")

    def test_what_it_holds(self):
        self.assertEqual(package.check(self.release), [])
        for need in ("LICENSE", "THIRD-PARTY-NOTICES.md", "docs/INSTALL.md", "LANGUAGE-SPEC.md",
                     "docs/LIBRARY-REFERENCE.md", "examples/lib/sprite.pbas", "programs/JUMPER.PRG"):
            self.assertTrue((self.release / need).is_file(), need)
        for never in ("POC", "Supporting Docs", "build", "docs/rosanne-research"):
            self.assertFalse((self.release / never).exists(), never)

    def test_the_checksums(self):
        lines = (self.release / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(lines), 300)
        for line in lines:
            digest, name = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((self.release / name).read_bytes()).hexdigest(), digest, name)

    def test_doctor_new_and_build_from_the_copy(self):
        self.assertEqual(subprocess.run([*self.cmd, "doctor"], capture_output=True, env=self.env()).returncode, 0)
        with tempfile.TemporaryDirectory() as work:
            for kind in ("app", "game"):
                out = subprocess.run([*self.cmd, "new", f"my{kind}", "--kind", kind], cwd=work,
                                     capture_output=True, text=True, env=self.env())
                self.assertEqual(out.returncode, 0, out.stderr)
                out = subprocess.run([*self.cmd, "build", f"my{kind}.pbas"], cwd=Path(work) / f"my{kind}",
                                     capture_output=True, text=True, env=self.env())
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertTrue((Path(work) / f"my{kind}" / "build" / f"my{kind}.prg").exists())

    def test_its_programs_equal_builds_from_the_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            made = package.build_programs(Path(tmp) / "p", ROOT)
            for name, _ in made:
                self.assertEqual((Path(tmp) / "p" / name).read_bytes(),
                                 (self.release / "programs" / name).read_bytes(), name)

    def test_the_committed_artefacts_are_these_builds(self):
        # artifacts/m13-rt7 (the owner's RT7 files) are exactly what the source builds with the
        # M13 file-safety code (M14: --legacy-file-safety)
        art = ROOT / "artifacts" / "m13-rt7"
        with tempfile.TemporaryDirectory() as tmp:
            package.build_programs(Path(tmp) / "p", ROOT, legacy=True)
            for name, *_ in package.PROGRAMS:
                self.assertEqual((art / name).read_bytes(), (Path(tmp) / "p" / name).read_bytes(), name)
        listed = (art / "MANIFEST.md").read_text(encoding="utf-8")
        for p in art.iterdir():
            if p.name != "MANIFEST.md":
                self.assertIn(hashlib.sha256(p.read_bytes()).hexdigest(), listed, p.name)

    def test_the_rt6_files_are_kept(self):
        # artifacts/m13-responsive: what the owner ran in RT6 (070a09d), kept as it was
        # (tests/test_m13_responsive.py runs its TIMEPRB to show the loop blocking)
        art = ROOT / "artifacts" / "m13-responsive"
        listed = (art / "MANIFEST.md").read_text(encoding="utf-8")
        for p in art.iterdir():
            if p.name != "MANIFEST.md":
                self.assertIn(hashlib.sha256(p.read_bytes()).hexdigest(), listed, p.name)

    def test_the_corrective_retest_files_are_kept(self):
        # artifacts/m13-corrective: what the owner retested (RT1-RT5), kept as it was
        # (tests/test_m13_responsive.py rebuilds its timer programs byte for byte)
        art = ROOT / "artifacts" / "m13-corrective"
        listed = (art / "MANIFEST.md").read_text(encoding="utf-8")
        for p in art.iterdir():
            if p.name != "MANIFEST.md":
                self.assertIn(hashlib.sha256(p.read_bytes()).hexdigest(), listed, p.name)
        self.assertIn("4c7e552", listed)

    def test_the_first_session_files_are_kept(self):
        # artifacts/m13: the 618d80a files the owner ran first, kept as they were
        # (tests/test_m13_corrective.py runs them to show each defect)
        listed = (ROOT / "artifacts" / "m13" / "MANIFEST.md").read_text(encoding="utf-8")
        for p in (ROOT / "artifacts" / "m13").iterdir():
            if p.name != "MANIFEST.md":
                self.assertIn(hashlib.sha256(p.read_bytes()).hexdigest(), listed, p.name)
        self.assertIn("618d80a", listed)

    def test_tests_run_from_the_copy(self):
        out = subprocess.run([sys.executable, "-m", "unittest", "test_m13_language", "test_m13_pbimage",
                              "test_m13_tutorials"], cwd=self.release, capture_output=True, text=True,
                             env=dict(self.env(), PYTHONPATH=f".{os.pathsep}tests"))
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        self.assertIn("OK", out.stderr)

    def test_the_accepted_executables_rebuild_from_the_copy(self):
        # The accepted .PRG files, rebuilt from the release's own sources: all
        # 49 but the three the gate builds from the prototype in ../POC, which
        # a release never holds (in the repository the gate checks all 49)
        with tempfile.TemporaryDirectory() as out:
            run = subprocess.run(["bash", "tools/accepted-gate.sh", out], cwd=self.release, capture_output=True,
                                 text=True, env=self.env())
        lines = run.stdout.splitlines()
        self.assertEqual(lines.count("ok"), 46, run.stdout[-2000:] + run.stderr[-2000:])
        self.assertEqual(sorted(line for line in lines if line != "ok"),
                         sorted(f"{kind} {name}" for kind in ("FAIL build", "DIFF")
                                for name in ("m3a/loop_lab", "m3a/logic_native", "m4-fix/notes_v051_pbtest")))

    def test_a_rosanne_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "r"
            shutil.copytree(self.release / "docs", copy / "docs")
            for f in ("LICENSE", "THIRD-PARTY-NOTICES.md", "README.md", "SHA256SUMS"):
                shutil.copyfile(self.release / f, copy / f)
            (copy / "programs").mkdir()
            (copy / "programs" / "PCW045.SYS").write_bytes(b"x")
            (copy / "ROSAN283.DOC").write_bytes(b"x")
            problems = package.check(copy)
            self.assertEqual(len(problems), 2, problems)
            (copy / "LICENSE").unlink()
            self.assertIn("LICENSE is missing", package.check(copy))

    def test_a_disassembly_is_refused_under_any_name(self):
        # RC1 preparation: docs/rosanne-research/reference/rom0.asm (a disassembly of
        # Rosanne's boot block, bytes and file offsets) was in the release; the pack is
        # now left out, and a listing like it is refused wherever it is
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "r"
            copy.mkdir()
            for f in ("LICENSE", "THIRD-PARTY-NOTICES.md", "README.md", "SHA256SUMS"):
                shutil.copyfile(self.release / f, copy / f)
            self.assertEqual(package.check(copy), [])
            rows = "".join(f"                 ld a,b     ; ${0x4000 + i:04X} f+{i:04X}  78\n" for i in range(60))
            (copy / "notes.md").write_text("# notes\n" + rows)
            hex_rows = "".join(f"{0x5584 + 3 * i:04X}  cd eb 1b fd\n" for i in range(60))
            (copy / "trace.txt").write_text(hex_rows)
            problems = package.check(copy)
            self.assertEqual(len(problems), 2, problems)
            self.assertTrue(all("disassembly may not be released" in x for x in problems), problems)
            # the project's own sources and the few addresses its documents cite pass
            for own in ("runtime/runtime.z80.asm", "docs/M13-RESPONSIVENESS.md", "RUNTIME-RESULTS.md"):
                (copy / Path(own).name).write_bytes((ROOT / own).read_bytes())
            self.assertEqual(len(package.check(copy)), 2)


if __name__ == "__main__":
    unittest.main()
