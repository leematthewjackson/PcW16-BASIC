"""M15 acceptance programs and the integrated demo, driven through whole
sessions in the simulator before the M15c XAnne session
(docs/M15C-ACCEPTANCE.md). These check that each program runs its steps
without a memory violation or an unexpected runtime error and that its
figures are those the guide asks the owner to compare; they do not show
what Rosanne does (fonts, type sizes, the y reference, Stop's delivery).
"""
from __future__ import annotations

import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import check_source
from pbas.layout import build_dialog
from test_m6_phase1 import numbers
from toolchain import requires_files, requires_pasmo
from z80sim import dialog_font_width

ROOT = Path(__file__).resolve().parents[1]
M15C = ROOT / "developer-tests" / "m15c"
F = "\\PCW\\FOLDER01"
STOP = ("menu", 0, 0)  # Tasks > Stop (M15a r5)


def source(name):
    path = (ROOT / "examples" / name) if name.startswith("m15_") else M15C / name
    return path, path.read_text(encoding="utf-8")


def session(name, events, answers=None, disk=None, window=0):
    path, src = source(name)
    r = guarded_run(src, path=path, events=events, alert_answers=answers, disk=disk)
    assert r.violations == [], r.violations[:5]
    return r


def canvases(name):
    _, src = source(name)
    p = check_source(src)
    out = {}
    for window in p.windows:
        for number, sx, sy, w, h, widget in build_dialog(p, window, bool(p.menus)).canvases:
            out[widget.canvas_name or "CANVAS"] = (number, sx, sy, w, h)
    return out


def buttons(name, window=0):
    return numbers(source(name)[1], window)


@requires_pasmo
class StopProgramTests(unittest.TestCase):
    def test_m15stop_each_choice(self):
        n = buttons("m15stop.pbas")
        r = session("m15stop.pbas", [STOP])
        self.assertTrue(r.cpu.exited)
        r = session("m15stop.pbas", [("radio", n["MODE 2"]), STOP, STOP])
        self.assertFalse(r.cpu.exited)
        self.assertEqual(string_var(r, "SEEN$"), "Stop requests: 2")
        r = session("m15stop.pbas", [("radio", n["MODE 3"]), STOP, STOP], answers=[1, 0])
        self.assertTrue(r.cpu.exited)
        disk = z80sim.Disk()
        r = session("m15stop.pbas", [("radio", n["MODE 4"]), STOP], disk=disk)
        self.assertTrue(r.cpu.exited)
        self.assertEqual(disk.files[(F, "M15STOP.TXT")], b"M15STOP ended by Tasks > Stop, request 1\r\n")

    def test_m15stnm(self):
        disk = z80sim.Disk()
        r = session("m15stnm.pbas", [("hotkey", 0, 0)], disk=disk)
        self.assertTrue(r.cpu.exited)
        self.assertIn((F, "M15STNM.TXT"), disk.files)


@requires_pasmo
class FontProgramTests(unittest.TestCase):
    def test_pages_and_widths(self):
        n = buttons("m15font.pbas")
        r = session("m15font.pbas", [("click", n["Fonts 7-12"])])
        info = string_var(r, "INFO$")
        want = " ".join(f"{k}={dialog_font_width(f'Font {k}: The quick brown fox 0123'.encode(), k)}"
                        for k in range(7, 13))
        self.assertEqual(info, "Widths: " + want)
        r = session("m15font.pbas", [("click", n["Cut 1-6"]), ("click", n["Cut 7-12"]), ("click", n["Align"])])
        self.assertEqual(r.alerts, [])
        self.assertTrue(string_var(r, "INFO$").startswith("Align"))
        ox = canvases("m15font.pbas")["CANVAS"][1]
        cut = [(x - ox, t, f) for (x, _, t, _), f in zip(r.cpu.texts, r.cpu.text_fonts) if x - ox == 300]
        self.assertEqual([f for *_, f in cut], list(range(1, 13)))
        for x, t, f in cut:  # M15c F3: each ends inside, fonts other than 7 with the margin
            margin = 0 if f == 7 else dialog_font_width(b"W", f) // 2 + 1
            self.assertLessEqual(x + dialog_font_width(t.encode(), f), 560 - margin, f)

    def test_bad_font_and_default_stop(self):
        n = buttons("m15font.pbas")
        r = session("m15font.pbas", [("menu", 1, 0)])  # File > Bad font
        self.assertTrue(any("a font is 1 to 12" in a for a in r.alerts), r.alerts)
        r = session("m15font.pbas", [STOP])  # menus, no ON STOP: Stop ends it (M15 default)
        self.assertTrue(r.cpu.exited)


@requires_pasmo
class TypeProgramTests(unittest.TestCase):
    def test_every_size_and_style(self):
        n = buttons("m15type.pbas")
        events = [("click", n["Larger"])] * 7 + [("menu", 2, 1), ("menu", 2, 2), ("menu", 2, 0)]
        events += [("click", n["Smaller"])] * 9
        r = session("m15type.pbas", events)
        self.assertEqual(r.alerts, [])
        self.assertTrue(string_var(r, "INFO$").startswith("Times 6 bold italic: TYPEWIDTH"))
        self.assertEqual(sorted({size for *_, (_, size) in r.cpu.typo_chars}),
                         [6, 8, 10, 11, 12, 14, 18, 24, 36, 72])

    def test_speed_and_print(self):
        n = buttons("m15type.pbas")
        r = session("m15type.pbas", [("click", n["Speed"]), ("click", n["Print"])])
        self.assertEqual(r.alerts, [])
        self.assertTrue(string_var(r, "INFO$").startswith("Print: IOERR 0"), string_var(r, "INFO$"))


@requires_pasmo
class CanvasProgramTests(unittest.TestCase):
    def test_session(self):
        cv = canvases("m15canv.pbas")
        n = buttons("m15canv.pbas")
        n2 = buttons("m15canv.pbas", 1)
        _, px, py, _, _ = cv["PALETTE"]
        _, bx, by, _, _ = cv["BOARD"]
        events = [("mdown", px + 3 * 70 + 10, py + 5), ("mup", px + 3 * 70 + 10, py + 5),
                  ("key", 227),  # the Palette has the keyboard after the press
                  ("mdown", bx + 100, by + 50), ("mmove", bx + 110, by + 60), ("mup", bx + 110, by + 60),
                  ("key", 225),  # now the Board's
                  ("click", n["Keys: Palette"]), ("key", 226),
                  ("click", n["Mark both"]), ("click", n["Alert"]), ("menu", 1, 0),
                  ("click", n["Window 2"]), ("click", n2["Back"])]
        r = session("m15canv.pbas", events)
        self.assertEqual(r.alerts, ["After this alert both canvases are drawn again."])
        self.assertEqual(string_var(r, "INFO$"), "Board cleared")
        at = r.symbols["var_shade"]
        self.assertEqual(r.cpu.mem[at], 3)  # 3, Right to 4, Left back to 3
        fonts = set(r.cpu.text_fonts)
        self.assertEqual(fonts, {2, 4, 12})

    def test_the_board_keeps_its_drawing_through_a_repaint(self):
        # M15c C5: the strokes vanished after the alert. The runtime repaints (PAINT
        # runs again); r2's Board stores its squares and its PAINT draws them again
        cv = canvases("m15canv.pbas")
        n = buttons("m15canv.pbas")
        _, bx, by, _, _ = cv["BOARD"]
        drag = [("mdown", bx + 100, by + 50), ("mmove", bx + 110, by + 60), ("mup", bx + 110, by + 60)]
        r = session("m15canv.pbas", drag + [("click", n["Alert"])])
        squares = [(x, y) for kind, op, x, y, w, h, *_ in (e for e in r.cpu.draw_log if e[0] == "direct")
                   if op in (2, 3) and (w, h) == (4, 4)]
        first = [(bx + 100, by + 50), (bx + 110, by + 60), (bx + 110, by + 60)]
        self.assertEqual(squares[:3], first)  # as dragged
        self.assertEqual(squares[3:], first)  # and again by PAINT after the alert

    def test_runtime_bank(self):
        path, src = source("m15canv.pbas")
        n = buttons("m15canv.pbas")
        r = guarded_run(src, path=path, events=[("click", n["Mark both"])],
                        build_options={"runtime_sections": "all"})
        self.assertEqual(r.violations, [])
        self.assertEqual(string_var(r, "INFO$"), "Marked both")


@requires_pasmo
class SpecimenTests(unittest.TestCase):
    def test_session(self):
        cv = canvases("m15_specimen.pbas")
        n = buttons("m15_specimen.pbas")
        _, sx, sy, _, _ = cv["SIZESTRIP"]
        events = [("edit", n["SAMPLE$"], "Quick type"), ("click", n["Show"]),
                  ("mdown", sx + 7 * 56 + 5, sy + 5), ("mup", sx + 7 * 56 + 5, sy + 5),
                  ("menu", 2, 3), ("key", 227), ("menu", 2, 1), ("click", n["Print"]),
                  STOP, STOP]
        r = session("m15_specimen.pbas", events, answers=[1, 0])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.alerts, ["End the type specimen?"] * 2)  # Stay, then End
        self.assertIn(36, {size for *_, (_, size) in r.cpu.typo_chars})  # size 8 of the strip, then Right
        self.assertIn("Quick type", "".join(c for _, _, c, *_ in r.cpu.typo_chars))


    def test_type_stays_inside_the_preview(self):
        # M15c SPECIMEN: at 72 pt the text overlapped the size strip, and old text and
        # control graphics stayed on screen. Cause: Rosanne's y is the baseline (T2),
        # so type drawn "at y = 8" stood above the Preview canvas, where DRAW CLEAR
        # never reaches. Every character's cell must now lie in the Preview canvas
        cv = canvases("m15_specimen.pbas")
        n = buttons("m15_specimen.pbas")
        _, sx, sy, _, _ = cv["SIZESTRIP"]
        _, px, py, pw, ph = cv["PREVIEW"]
        events = []
        for k in range(10):  # every size, then bold italic Times at each again
            events += [("mdown", sx + k * 56 + 5, sy + 5), ("mup", sx + k * 56 + 5, sy + 5)]
        events += [("menu", 2, 0), ("menu", 2, 1), ("menu", 2, 2)]
        for k in range(9, -1, -1):
            events += [("mdown", sx + k * 56 + 5, sy + 5), ("mup", sx + k * 56 + 5, sy + 5)]
        r = session("m15_specimen.pbas", events)
        self.assertEqual(r.alerts, [])
        sizes = set()
        for x, y, c, st, md, (_, size) in r.cpu.typo_chars:
            sizes.add(size)
            h = (size * 25 * 4 // 5 + size * 25 // 4 + 24) // 25
            self.assertTrue(px <= x < px + pw and py <= y and y + h <= py + ph, (x, y, size))
        self.assertEqual(sorted(sizes), [6, 8, 10, 11, 12, 14, 18, 24, 36, 72])


@requires_pasmo
class ArtefactTests(unittest.TestCase):
    """artifacts/m15c-r2 (the focused retest after M15c) is exactly what these sources
    build. artifacts/m15c keeps the files of the M15c session itself (their sources
    have since been corrected: docs/M15C-RETEST.md)."""

    @requires_files(ROOT / "artifacts" / "m15c-r2" / "MANIFEST.md", what="the builds the owner ran in XAnne for M15")
    def test_rebuild(self):
        import hashlib
        import sys
        import tempfile
        sys.path.insert(0, str(ROOT / "tools"))
        import package
        art = ROOT / "artifacts" / "m15c-r2"
        listed = (art / "MANIFEST.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            made = package.build_programs(Path(tmp), ROOT, programs=package.M15C_R2)
            for name, _ in made:
                data = (Path(tmp) / name).read_bytes()
                self.assertEqual(data, (art / name).read_bytes(), name)
                self.assertIn(hashlib.sha256(data).hexdigest(), listed, name)


if __name__ == "__main__":
    unittest.main()
