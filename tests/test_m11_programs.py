"""artifacts/m11-r2 is what the owner retests: each executable and data file
rebuilds from its source, byte for byte, with the hashes of its MANIFEST.
artifacts/m11 is the record of what the owner ran in the M11 sessions: its
files keep their MANIFEST hashes, and CELLPRB (unchanged since) still
rebuilds to the same bytes."""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pbas.prg import build
from toolchain import requires_files, requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "m11-r2"
OLD = ROOT / "artifacts" / "m11"


@requires_pasmo
class ArtifactTests(unittest.TestCase):
    BUILDS = (("examples/mdedit3.pbas", "mdedit3"), ("examples/contacts4.pbas", "contacts4"),
              ("examples/starter.pbas", "starter"))

    @requires_files(ART / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14

    def test_rebuild(self):
        manifest = (ART / "MANIFEST.md").read_text(encoding="utf-8")
        for src, name in self.BUILDS:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                t = Path(tmp)
                build(ROOT / src, t / f"{name}.asm", t / f"{name}.prg", runtime_sections="all",
                      legacy_file_safety=True, legacy_real_rounding=True, legacy_tasks_stop=True)  # M14: as accepted
                image = (t / f"{name}.prg").read_bytes()
                self.assertEqual(image, (ART / f"{name}.prg").read_bytes())
                self.assertIn(hashlib.sha256(image).hexdigest(), manifest)
                self.assertIn("--runtime-banks all", manifest)

    @requires_files(ART / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14

    def test_data(self):
        manifest = (ART / "MANIFEST.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(ROOT / "tools" / "m10_sample_data.py"), tmp], check=True,
                           capture_output=True)
            for name in ("CONTACTS.PDB", "DAMAGED.PDB"):
                data = (Path(tmp) / name).read_bytes()
                self.assertEqual(data, (ART / name).read_bytes())
                self.assertEqual(data, (ROOT / "artifacts" / "m10" / name).read_bytes())
                self.assertIn(hashlib.sha256(data).hexdigest(), manifest)
        self.assertEqual((ART / "EDTEST.MD").read_bytes(), (ROOT / "developer-tests" / "edtest.md").read_bytes())


@requires_pasmo
class OwnerTestedRecordTests(unittest.TestCase):
    @requires_files(OLD / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14
    def test_the_programs_the_owner_ran_are_kept(self):
        manifest = (OLD / "MANIFEST.md").read_text(encoding="utf-8")
        rows = re.findall(r"^\| (\S+) \| \d+ \| `([0-9a-f]{64})`", manifest, re.M)
        self.assertEqual(len(rows), 7)
        for name, digest in rows:
            with self.subTest(name):
                self.assertEqual(hashlib.sha256((OLD / name).read_bytes()).hexdigest(), digest)

    @requires_files(OLD / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14

    def test_cellprb_still_rebuilds(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            build(ROOT / "developer-tests" / "cellprb.pbas", t / "c.asm", t / "c.prg", runtime_sections="all")
            self.assertEqual((t / "c.prg").read_bytes(), (OLD / "cellprb.prg").read_bytes())


if __name__ == "__main__":
    unittest.main()
