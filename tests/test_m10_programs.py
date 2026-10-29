"""artifacts/m10 is what the owner runs: each executable and data file
rebuilds from its source, byte for byte, with the hashes of its MANIFEST."""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pbas.prg import build
from toolchain import requires_files, requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "m10"


@requires_pasmo
class ArtifactTests(unittest.TestCase):
    BUILDS = (("developer-tests/dbprobe.pbas", "dbprobe"), ("examples/mdedit2.pbas", "mdedit2"),
              ("examples/contacts3.pbas", "contacts3"))

    @requires_files(ART / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14

    def test_rebuild(self):
        manifest = (ART / "MANIFEST.md").read_text(encoding="utf-8")
        for src, name in self.BUILDS:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                t = Path(tmp)
                build(ROOT / src, t / f"{name}.asm", t / f"{name}.prg",  # M14: as accepted
                      legacy_file_safety=True, legacy_real_rounding=True, legacy_tasks_stop=True)
                image = (t / f"{name}.prg").read_bytes()
                self.assertEqual(image, (ART / f"{name}.prg").read_bytes())
                self.assertIn(hashlib.sha256(image).hexdigest(), manifest)

    @requires_files(ART / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14

    def test_data(self):
        manifest = (ART / "MANIFEST.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(ROOT / "tools" / "m10_sample_data.py"), tmp], check=True,
                           capture_output=True)
            for name in ("CONTACTS.PDB", "DAMAGED.PDB"):
                data = (Path(tmp) / name).read_bytes()
                self.assertEqual(data, (ART / name).read_bytes())
                self.assertIn(hashlib.sha256(data).hexdigest(), manifest)
        self.assertEqual((ART / "EDTEST.MD").read_bytes(), (ROOT / "developer-tests" / "edtest.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
