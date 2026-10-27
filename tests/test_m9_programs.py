"""M9 probe and benchmark programs on the simulator: GFXPROBE
(developer-tests/gfxprobe.pbas), GFXBENCH and UIBENCH (examples/). Each is driven by
scripted events; the checks are on what the program shows (status lines,
drawing calls) and on the M2.1 memory rules. Simulator evidence only.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from memguard import guarded_run, string_var
from pbas import check_source
from pbas.layout import build_dialog
from toolchain import requires_files, requires_pasmo

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def objects(src: str) -> dict:
    program = check_source(src)
    lay = build_dialog(program, program.windows[0], bool(program.menus))
    result = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
    result["canvas"] = lay.canvas
    return result


@requires_pasmo
class GfxProbeTests(unittest.TestCase):
    SRC = source("developer-tests/gfxprobe.pbas")

    def test_every_step(self):
        o = objects(self.SRC)
        _, sx, sy, w, h, _ = o["canvas"]
        events = [("click", o["Shapes"]), ("click", o["Scroll"]), ("click", o["Alert"]),
                  ("key", 65, 1), ("key", 0xE0), ("objevent", o["Quit"], 9),
                  ("mdown", sx + 10, sy + 10), ("mmove", sx + 20, sy + 15), ("mup", sx + 21, sy + 16),
                  ("click", o["Speed"]), ("click", o["Quit"])]
        r = guarded_run(self.SRC, events=events, max_steps=50_000_000)
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["G3: after OK the picture must be complete",
                                    "G6: 100 lines and 50 texts drawn"])
        self.assertEqual(string_var(r, "KEYLINE$"), "K233.0 #3")
        self.assertEqual(string_var(r, "MOUSELINE$"), "M3 21,16")
        self.assertTrue(r.cpu.exited)
        kinds = {e[0] for e in r.cpu.draw_log}
        self.assertEqual(kinds, {"direct", "rect", "line", "pixel", "text"})
        self.assertEqual(r.cpu.bios_sloped_lines, 0, "KI-49: sloped lines drawn as runs")
        # XAnne M9: Rosanne refused grey 8 at line 44. Nine strips, the
        # ninth white (dg_blk_white), inside the frame; grey 8 never sent.
        self.assertFalse([e for e in r.cpu.draw_log if e[0] == "direct" and e[1] in (3, 4)
                          and e[6][0] >= 8])
        strips = [e for e in r.cpu.draw_log if e[0] == "direct" and e[3] == sy + 160 and e[5] == 36]
        self.assertEqual([e[1] for e in strips[:9]], [3] * 8 + [1])
        self.assertEqual([e[2] - sx for e in strips[:9]], [4 + 12 * i for i in range(9)])
        clipped = [t for t in r.cpu.texts if t[2].startswith("ABC")]
        self.assertEqual(clipped[0][2], "ABCDEFGHIJKLMNOPQRSTUV", "(400 - 150) / 11 = 22 characters")
        self.assertEqual(len(clipped[0][2]), (400 - 150) // 11)


@requires_pasmo
class BenchmarkTests(unittest.TestCase):
    def test_gfxbench(self):
        src = source("examples/gfxbench.pbas")
        o = objects(src)
        _, sx, sy, w, h, _ = o["canvas"]
        x3 = sx + 30 + 2 * 36 + 5  # inside bar 3
        events = [("mdown", x3, sy + 100), ("mup", x3, sy + 100), ("key", 0xE0), ("key", 0xE3),
                  ("click", o["Run"]), ("timer", 0), ("timer", 0), ("click", o["Stop"]), ("timer", 0),
                  ("click", o["Redraw"]), ("click", o["Quit"])]
        r = guarded_run(src, events=events, max_steps=50_000_000)
        self.assertEqual(r.violations, [])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(string_var(r, "STATUS$"), f"Apr = {20 + (4 * 37) % 90}")
        self.assertEqual(r.cpu.bios_sloped_lines, 0, "KI-49: the trace's sloped segments drawn as runs")
        copies = [e for e in r.cpu.draw_log if e[0] == "direct" and e[1] == 10]
        self.assertEqual(len(copies), 2, "the trace scrolled once per tick while running")

    def test_gfxbench_trace_is_continuous(self):
        # KI-50 (owner XAnne recording): the Run trace was a row of spikes,
        # each segment drawn from the centre line. Each segment now starts
        # where the last ended: after 8 ticks the trace (x 413..477 of the
        # strip, y 199..231) is one 8-connected line spanning every column.
        src = source("examples/gfxbench.pbas")
        o = objects(src)
        _, sx, sy, w, h, _ = o["canvas"]
        r = guarded_run(src, events=[("click", o["Run"])] + [("timer", 0)] * 8, max_steps=80_000_000)
        self.assertEqual(r.violations, [])
        pts = {(x, y) for x in range(413, 478) for y in range(199, 232) if r.cpu.pixel(sx + x, sy + y)}
        self.assertEqual({x for x, _ in pts}, set(range(413, 478)), "a pixel in every column")
        seen, todo = set(), [min(pts)]
        while todo:
            x, y = todo.pop()
            if (x, y) in seen:
                continue
            seen.add((x, y))
            todo += [(x + i, y + j) for i in (-1, 0, 1) for j in (-1, 0, 1) if (x + i, y + j) in pts]
        self.assertEqual(seen, pts, "one connected line")

    def test_uibench(self):
        src = source("examples/uibench.pbas")
        o = objects(src)
        _, sx, sy, w, h, _ = o["canvas"]
        events = [("key", 0xE1), ("key", 0xE1), ("key", 0xE9), ("key", 0xE7), ("key", 0xE6),
                  ("mdown", sx + 10, sy + 18 * 5 + 3), ("click", o["Page down"]), ("menu", 1, 1),
                  ("key", 13), ("click", o["Quit"])]
        r = guarded_run(src, events=events, max_steps=80_000_000)
        self.assertEqual(r.violations, [])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(len(r.alerts), 1)
        self.assertEqual(string_var(r, "STATUS$"), "Row 18 of 60, page 2")


@requires_pasmo
class TextboxProbeTests(unittest.TestCase):
    """TBPROBE (MDEDIT E9 follow-up): what the simulator expects XAnne to
    show; a different value in XAnne locates the defect (TB1-TB4)."""

    def test_every_step(self):
        from pbas.layout import build_dialog
        src = source("developer-tests/tbprobe.pbas")
        program = check_source(src)
        b = {}
        for window in program.windows:
            for o in build_dialog(program, window, False).objects:
                if o.kind == "BUTTON":
                    b[(window.name, o.text)] = o.number
        events = [("click", b[("FIRST", "Check here")]), ("click", b[("FIRST", "Second window")]),
                  ("click", b[("SECOND", "Check")]), ("click", b[("SECOND", "Back")]),
                  ("click", b[("FIRST", "Check here")]), ("click", b[("FIRST", "Quit")])]
        r = guarded_run(src, events=events)
        self.assertEqual(r.violations, [])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.alerts, ["TB1 M[EDTEST.MD]9", "TB2 S[EDTEST.MD]9 L[EDTEST.MD]9", "TB1 M[EDTEST.MD]9",
                                    "TB4 M[EDTEST.MD] S[EDTEST.MD] L[EDTEST.MD]"])


@requires_pasmo
class ArtifactTests(unittest.TestCase):
    """artifacts/m9 is what the owner runs: each executable rebuilds from
    its source, byte for byte, with the options in its MANIFEST (and, for
    the two with a menu item without KEY, the hotkey words they were built
    with: legacy_menu_hotkeys, KI-89)."""

    BUILDS = (("developer-tests/bankprobe.pbas", "bankprobe", dict(code_banks="always", code_bank_limit=400,
                                                         legacy_menu_hotkeys=True)),
              ("developer-tests/gfxprobe.pbas", "gfxprobe", {}), ("examples/gfxbench.pbas", "gfxbench", {}),
              ("examples/uibench.pbas", "uibench", {}), ("examples/mdedit.pbas", "mdedit", dict(legacy_menu_hotkeys=True)),
              ("developer-tests/tbprobe.pbas", "tbprobe", {}))

    @requires_files(ROOT / "artifacts" / "m9" / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14

    def test_rebuild(self):
        import hashlib
        import tempfile
        from pbas.prg import build
        manifest = (ROOT / "artifacts" / "m9" / "MANIFEST.md").read_text(encoding="utf-8")
        for src, name, options in self.BUILDS:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                t = Path(tmp)
                build(ROOT / src, t / f"{name}.asm", t / f"{name}.prg", **options)
                image = (t / f"{name}.prg").read_bytes()
                self.assertEqual(image, (ROOT / "artifacts" / "m9" / f"{name}.prg").read_bytes())
                self.assertIn(hashlib.sha256(image).hexdigest(), manifest)
        self.assertEqual((ROOT / "artifacts" / "m9" / "edtest.md").read_bytes(),
                         (ROOT / "developer-tests" / "edtest.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
