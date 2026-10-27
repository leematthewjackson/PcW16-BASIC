"""M13 Stage J: the tutorials (docs/TUTORIAL-*.md) and their programs.

Each tutorial quotes its whole program; the quote must be exactly the file
in examples/tutorial, and the file must build and do what the tutorial
says, on the simulator, with the pictures made from examples/assets the
way the tutorial makes them.
"""
from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import check_source
from pbas.layout import build_dialog
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pbimage  # noqa: E402

F = "\\PCW\\FOLDER01"
DOCS = sorted((ROOT / "docs").glob("TUTORIAL-*.md"))


def pictures() -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="pbw16-tut-") as tmp:
        with contextlib.redirect_stdout(io.StringIO()):
            assert pbimage.main(["build", str(ROOT / "examples" / "assets" / "ASSETS.txt"), tmp]) == 0
        return {p.name: p.read_bytes() for p in Path(tmp).iterdir()}


PICS = pictures()


def program(name):
    path = ROOT / "examples" / "tutorial" / name
    src = path.read_text(encoding="utf-8")
    lay = build_dialog(check_source(src, path=path), check_source(src, path=path).windows[0], False)
    return path, src, lay


def run(name, events):
    path, src, lay = program(name)
    disk = z80sim.Disk(files={(F, n): d for n, d in PICS.items()})
    r = guarded_run(src, path=path, events=events, disk=disk, build_options={"runtime_sections": "all"},
                    max_steps=600_000_000, clock_by_steps=False)  # the clock moves by "wait" events only
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r, lay


class QuoteTests(unittest.TestCase):
    def test_three_tutorials(self):
        self.assertEqual([p.name for p in DOCS], ["TUTORIAL-1-FIRST-PROGRAM.md", "TUTORIAL-2-GRAPHICS.md",
                                                  "TUTORIAL-3-GAME.md"])

    def test_every_quoted_program_is_its_file(self):
        for doc in DOCS:
            text = doc.read_text(encoding="utf-8")
            quotes = re.findall(r"<!-- file: (\S+) -->\n```basic\n(.*?)```", text, re.S)
            self.assertEqual(len(quotes), 1, doc.name)
            for name, code in quotes:
                with self.subTest(doc=doc.name):
                    self.assertEqual(code, (ROOT / name).read_text(encoding="utf-8"))


@requires_pasmo
class ProgramTests(unittest.TestCase):
    def test_1_hello(self):
        path, src, lay = program("t1_hello.pbas")
        b = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
        field = {row.var_name: row.number for row in lay.bindings}["NAME$"]
        r, _ = run("t1_hello.pbas", [("click", b["Greet"])])
        self.assertEqual(string_var(r, "GREETING$"), "Type your name first")
        r, _ = run("t1_hello.pbas", [("edit", field, "Ann"), ("click", b["Greet"])])
        self.assertEqual(string_var(r, "GREETING$"), "Hello, Ann")

    def test_2_draw(self):
        path, src, lay = program("t2_draw.pbas")
        cx, cy = lay.canvas[1], lay.canvas[2]
        drag = [("mdown", cx + 50, cy + 60), ("mmove", cx + 150, cy + 120), ("mup", cx + 90, cy + 100)]
        r, _ = run("t2_draw.pbas", drag)
        self.assertEqual(string_var(r, "STATUS$"), "41 x 41")
        pic = r.cpu.canvas_pixels(cx, cy, 400, 200)
        self.assertEqual(pic[60][50:91], "#" * 41)  # the outline, and no band left behind
        self.assertEqual(pic[80][51:90], "." * 39)
        self.assertEqual(pic[120][100:150], "." * 50)
        pick = [("mdown", cx + 4 + 26 + 12, cy + 15), ("mup", cx + 4 + 26 + 12, cy + 15)]
        r, _ = run("t2_draw.pbas", pick + drag)
        # filled in shade 2 (the simulator draws shades 0-3 black and 4-8 white;
        # Rosanne's grey patterns are for XAnne, KI-46)
        self.assertEqual(r.cpu.canvas_pixels(cx, cy, 400, 200)[80][50:91], "#" * 41)

    def test_3_hop(self):
        tick = [("wait", 2), ("timer", 0)]  # 1/8 s of the clock, then the event
        r, lay = run("t3_hop.pbas", [("hold", "RIGHT", True)] + tick * 5)
        self.assertEqual(string_var(r, "STATUS$"), "X 40  Y 128")
        r, lay = run("t3_hop.pbas", [("hold", "SPACE", True)] + tick * 3)
        self.assertEqual(string_var(r, "STATUS$"), "X 20  Y 98")  # 128 - 12 - 10 - 8
        # the same three steps when Rosanne brings one event for all of them (KI-81)
        r, lay = run("t3_hop.pbas", [("hold", "SPACE", True), ("wait", 6), ("timer", 0)])
        self.assertEqual(string_var(r, "STATUS$"), "X 20  Y 98")


if __name__ == "__main__":
    unittest.main()
