"""M13 Stage J: the pcw16basic command (pbas/cli.py) and its project templates.

A new project is made in a temporary folder, as a developer would make
it, built with the command, and run on the simulator: the application
template draws a box where it is clicked, the game template moves its
sprite while a key is held. The command refuses to overwrite a folder.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from memguard import guarded_run, string_var
from pbas import check_source
from pbas.layout import build_dialog
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
CMD = [sys.executable, str(ROOT / "pcw16basic")]


def cli(*args, cwd=None):
    return subprocess.run([*CMD, *args], capture_output=True, text=True, cwd=cwd)


class CommandTests(unittest.TestCase):
    def test_help_and_version(self):
        out = cli("--help")
        self.assertEqual(out.returncode, 0)
        for word in ("doctor", "new", "check", "build", "assets", "image", "memory", "test"):
            self.assertIn(word, out.stdout)
        self.assertIn("1.0.0rc2", cli("--version").stdout)

    def test_new_refuses_an_existing_folder_and_a_bad_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cli("new", "demo", cwd=tmp).returncode, 0)
            again = cli("new", "demo", cwd=tmp)
            self.assertEqual(again.returncode, 1)
            self.assertIn("already exists", again.stderr)
            self.assertEqual(cli("new", "toolongname", cwd=tmp).returncode, 2)
            self.assertTrue((Path(tmp) / "demo" / "lib" / "sprite.pbas").exists())

    def test_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.pbas"
            bad.write_text("X = \nEND\n", encoding="utf-8")
            out = cli("check", str(bad))
            self.assertEqual(out.returncode, 1)
            self.assertIn("bad.pbas:1:", out.stderr)


@requires_pasmo
class TemplateTests(unittest.TestCase):
    def make(self, tmp, kind):
        out = cli("new", "demo", "--kind", kind, cwd=tmp)
        self.assertEqual(out.returncode, 0, out.stderr)
        project = Path(tmp) / "demo"
        built = cli("build", "demo.pbas", cwd=project)
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertTrue((project / "build" / "demo.prg").exists())
        self.assertEqual(cli("doctor").returncode, 0)
        return project / "demo.pbas"

    def test_the_app_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, "app")
            src = path.read_text(encoding="utf-8")
            lay = build_dialog(check_source(src, path=path), check_source(src, path=path).windows[0], False)
            cx, cy = lay.canvas[1], lay.canvas[2]
            r = guarded_run(src, path=path, events=[("mdown", cx + 100, cy + 50), ("mup", cx + 100, cy + 50)])
            self.assertEqual(r.violations, [])
            self.assertEqual(string_var(r, "APPSTATUS$"), "1 boxes")
            self.assertEqual(r.cpu.canvas_pixels(cx, cy, 400, 160)[45][95:105], "#" * 10)

    def test_the_game_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make(tmp, "game")
            src = path.read_text(encoding="utf-8")
            r = guarded_run(src, path=path, events=[("hold", "RIGHT", True)] + [("wait", 2), ("timer", 0)] * 5,
                            build_options={"runtime_sections": "all"}, clock_by_steps=False)
            self.assertEqual(r.violations, [])
            self.assertFalse([a for a in r.alerts if a.startswith("Runtime error")], r.alerts)
            self.assertEqual(string_var(r, "SCORE$"), "X 40  Y 128")


if __name__ == "__main__":
    unittest.main()
