"""artifacts/m12 is what the owner tests in XAnne (docs/M12-ACCEPTANCE.md):
each executable rebuilds from its source, byte for byte, with the hashes of
its MANIFEST, and each data file comes again from tools/m12_sample_data.py.
No file there is a third-party binary or personal data."""
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
ART = ROOT / "artifacts" / "m12"
sys.path.insert(0, str(ROOT / "tools"))
import pbicheck  # noqa: E402

BUILDS = (("examples/paint.pbas", "paint"), ("examples/printdemo.pbas", "printdemo"),
          ("examples/reporter.pbas", "reporter"), ("examples/mdedit4.pbas", "mdedit4"),
          ("developer-tests/bmpprb.pbas", "bmpprb"))


@requires_pasmo
class ArtifactTests(unittest.TestCase):
    @requires_files(ART / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14
    def test_rebuild(self):
        manifest = (ART / "MANIFEST.md").read_text(encoding="utf-8")
        self.assertIn("--runtime-banks all", manifest)
        for src, name in BUILDS:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                t = Path(tmp)
                # PAINT has menu items without KEY: built with the hotkey
                # words it was accepted with (KI-89)
                build(ROOT / src, t / f"{name}.asm", t / f"{name}.prg", runtime_sections="all",
                      legacy_menu_hotkeys=name == "paint",  # M14: as accepted
                      legacy_file_safety=True, legacy_real_rounding=True, legacy_tasks_stop=True)
                image = (t / f"{name}.prg").read_bytes()
                self.assertEqual(image, (ART / f"{name}.prg").read_bytes())
                self.assertIn(hashlib.sha256(image).hexdigest(), manifest)

    @requires_files(ART / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14

    def test_probe_without_the_runtime_bank(self):
        manifest = (ART / "MANIFEST.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            build(ROOT / "developer-tests" / "bmpprb.pbas", t / "n.asm", t / "n.prg",
                  legacy_file_safety=True, legacy_real_rounding=True, legacy_tasks_stop=True)
            image = (t / "n.prg").read_bytes()
            self.assertEqual(image, (ART / "bmpprn.prg").read_bytes())
            self.assertIn(hashlib.sha256(image).hexdigest(), manifest)

    @requires_files(ART / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14

    def test_data(self):
        manifest = (ART / "MANIFEST.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(ROOT / "tools" / "m12_sample_data.py"), tmp], check=True,
                           capture_output=True)
            for name in ("SAMPLE.PBI", "WRAPTEST.MD", "EDTEST.MD"):
                data = (Path(tmp) / name).read_bytes()
                self.assertEqual(data, (ART / name).read_bytes(), name)
                self.assertIn(hashlib.sha256(data).hexdigest(), manifest)
        self.assertEqual(pbicheck.check((ART / "SAMPLE.PBI").read_bytes())[0], 0)

    @requires_files(ART / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14

    def test_nothing_else_is_shipped(self):
        allowed = {f"{n}{ext}" for _, n in BUILDS for ext in (".prg", ".asm", ".map", ".sym")}
        allowed |= {f"{n}.bank{k}.asm" for _, n in BUILDS for k in (1, 2, 3)}
        allowed |= {"bmpprn.prg", "bmpprn.asm", "bmpprn.map", "bmpprn.sym", "bmpprn.bank1.asm",
                    "SAMPLE.PBI", "WRAPTEST.MD", "EDTEST.MD", "MANIFEST.md"}
        extra = {p.name for p in ART.iterdir()} - allowed
        self.assertEqual(extra, set())


if __name__ == "__main__":
    unittest.main()
