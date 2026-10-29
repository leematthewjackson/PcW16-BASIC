"""M15 public examples: fontbook, sketchpad and stopguard, each driven through a
session in the simulator (the M15 features are XAnne-accepted: LANGUAGE-SPEC
§5.17; these programs themselves have not been run in XAnne)."""
from __future__ import annotations

import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import check_source
from pbas.layout import build_dialog
from toolchain import requires_pasmo
from z80sim import dialog_font_width

ROOT = Path(__file__).resolve().parents[1]
F = "\\PCW\\FOLDER01"
STOP = ("menu", 0, 0)


def run(name, events, answers=None, disk=None):
    path = ROOT / "examples" / name
    r = guarded_run(path.read_text(encoding="utf-8"), path=path, events=events, alert_answers=answers, disk=disk)
    assert r.violations == [], r.violations[:5]
    return r


def canvases(name):
    p = check_source((ROOT / "examples" / name).read_text(encoding="utf-8"), path=ROOT / "examples" / name)
    lay = build_dialog(p, p.windows[0], bool(p.menus))
    return {(w.canvas_name or "CANVAS"): (n, x, y, cw, ch) for n, x, y, cw, ch, w in lay.canvases}


def buttons(name):
    """Buttons by caption, bound controls by variable (INCLUDEs read beside the program)."""
    path = ROOT / "examples" / name
    p = check_source(path.read_text(encoding="utf-8"), path=path)
    lay = build_dialog(p, p.windows[0], bool(p.menus))
    out = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
    out.update({row.var_name: row.number for row in lay.bindings})
    return out


@requires_pasmo
class FontbookTests(unittest.TestCase):
    def test_pages(self):
        n = buttons("fontbook.pbas")
        r = run("fontbook.pbas", [("click", n["Fonts 7-12"]), ("click", n["Align"])])
        self.assertEqual(r.alerts, [])
        self.assertEqual(sorted(set(r.cpu.text_fonts)), list(range(1, 13)))
        texts = [t for _, _, t, _ in r.cpu.texts]
        w = dialog_font_width(b"Font 9: Pack my box", 9)
        self.assertIn(f"{w} px", texts)


@requires_pasmo
class SketchpadTests(unittest.TestCase):
    def test_drawing_survives_a_repaint_and_keys_follow_focus(self):
        cv = canvases("sketchpad.pbas")
        n = buttons("sketchpad.pbas")
        _, px, py, _, _ = cv["PALETTE"]
        _, dx, dy, _, _ = cv["PAD"]
        events = [("mdown", px + 2 * 70 + 10, py + 5), ("mup", px + 2 * 70 + 10, py + 5),
                  ("mdown", dx + 40, dy + 40), ("mmove", dx + 50, dy + 40), ("mup", dx + 50, dy + 40),
                  ("click", n["Keys: Palette"]), ("key", 227), ("click", n["Help"])]
        r = run("sketchpad.pbas", events)
        dots = [(x, y) for kind, op, x, y, w, h, *_ in (e for e in r.cpu.draw_log if e[0] == "direct")
                if op in (2, 3) and (w, h) == (4, 4)]
        first = [(dx + 40, dy + 40), (dx + 50, dy + 40), (dx + 50, dy + 40)]
        self.assertEqual(dots, first * 2)  # drawn, then drawn again by PAINT
        self.assertEqual(r.cpu.mem[r.symbols["var_shade"]], 3)  # 2, then Right on the Palette
        self.assertEqual(r.alerts[0][:13], "Drag on the p")

    def test_clear_draws_on_the_pad_from_a_button(self):
        n = buttons("sketchpad.pbas")
        r = run("sketchpad.pbas", [("click", n["Clear"])])
        self.assertEqual(r.alerts, [])


@requires_pasmo
class StopguardTests(unittest.TestCase):
    def setUp(self):
        self.n = buttons("stopguard.pbas")

    def changed(self):
        return [("edit", self.n["NOTE$"], "Milk"), ("click", self.n["Keep"])]

    def test_unsaved_note_cancel_keeps_it_open(self):
        r = run("stopguard.pbas", self.changed() + [STOP], answers=[2])  # Cancel
        self.assertFalse(r.cpu.exited)
        self.assertIn("Unsaved changes", r.alerts)

    def test_discard_ends(self):
        r = run("stopguard.pbas", self.changed() + [STOP], answers=[1])  # Discard
        self.assertTrue(r.cpu.exited)

    def test_save_from_the_question_then_end(self):
        disk = z80sim.Disk()
        r = run("stopguard.pbas", self.changed() + [STOP], answers=[0], disk=disk)  # Save
        self.assertTrue(r.cpu.exited)
        self.assertEqual(disk.files[(F, "STOPNOTE.TXT")], b"Milk\r\n")

    def test_nothing_changed_ends_at_once(self):
        r = run("stopguard.pbas", [STOP])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.alerts, [])


if __name__ == "__main__":
    unittest.main()
