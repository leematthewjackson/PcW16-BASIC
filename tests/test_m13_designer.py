"""DESIGNER (examples/designer.pbas, M13 Stage G) on the simulator.

Sessions are driven with the window's buttons, mouse presses, drags and
releases on the page, keys, menus and the Properties and Files windows.
The page is compared pixel for pixel with what the drawing statements
produce on their own; saved designs are decoded with tools/pdbcheck.py
(the PDB1 format, LANGUAGE-SPEC §5.9); a damaged or foreign design must be
refused naming what is wrong. The BASIC export is compiled into a program
of its own and run: it must draw exactly the page the designer showed.
Simulator evidence only: the owner's XAnne session is docs/M13-ACCEPTANCE.md,
Session C.
"""
from __future__ import annotations

import contextlib
import io
import struct
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
import pbicheck  # noqa: E402
import pdbcheck  # noqa: E402
import pbimage  # noqa: E402

PATH = ROOT / "examples" / "designer.pbas"
SRC = PATH.read_text(encoding="utf-8")
F = "\\PCW\\FOLDER01"
CW, CH = 544, 240
SIG = "KIND:I;X:I;Y:I;W:I;H:I;SHADE:I;CAPTION:S30"

NEW, OPEN, SAVE, SAVEAS, EXPORT, PRINT, SAMPLE, QUIT = (("menu", 1, i) for i in range(8))
PROPS, DUPLICATE, DELETE, FRONT, BACK, SNAP = (("menu", 2, i) for i in range(6))
KC_UP, KC_DOWN, KC_LEFT, KC_RIGHT, KC_DELETE = 224, 225, 226, 227, 229


def icons() -> bytes:
    with tempfile.TemporaryDirectory(prefix="pbw16-dsn-") as tmp:
        with contextlib.redirect_stdout(io.StringIO()):
            assert pbimage.main(["build", str(ROOT / "examples" / "assets" / "ASSETS.txt"), tmp]) == 0
        return (Path(tmp) / "P2ICONS.PBI").read_bytes()


ICONS = icons()


def layout():
    program = check_source(SRC, path=PATH)
    main, props, files = (build_dialog(program, w, True) for w in program.windows)
    b = {o.text: ("click", o.number) for o in main.objects if o.kind == "BUTTON"}
    pb = {o.text: ("click", o.number) for o in props.objects if o.kind == "BUTTON"}
    pf = {row.var_name: row.number for row in props.bindings}
    fb = {o.text: ("click", o.number) for o in files.objects if o.kind == "BUTTON"}
    fb.update({row.var_name: row.number for row in files.bindings})
    return main.canvas[1], main.canvas[2], b, pb, pf, fb


SX, SY, B, PB, PF, FB = layout()


def at(x, y):
    return SX + x, SY + y


def click(x, y):
    return [("mdown",) + at(x, y), ("mup",) + at(x, y)]


def drag(points):
    (x, y), rest = points[0], points[1:]
    return [("mdown",) + at(x, y)] + [("mmove",) + at(px, py) for px, py in rest] + [("mup",) + at(*points[-1])]


def props(**values):
    ev = [PROPS]
    for name, value in values.items():
        key = name.upper()
        ev.append(("edit", PF.get(key, PF.get(key + "$")), str(value)))
    return ev + [PB["Apply"]]


def files(name, button):
    return [SAVEAS, ("edit", FB["FILENAME$"], name), FB[button]]


NOTHING = click(540, 236)  # an empty corner: nothing selected, no handles


def run(events, disk_files=None, answers=None, quit=True, icons=True):
    d = dict(disk_files or {})
    if icons:
        d.setdefault("P2ICONS.PBI", ICONS)
    disk = z80sim.Disk(files={(F, n): v for n, v in d.items()})
    r = guarded_run(SRC, events=events + ([QUIT] if quit else []), disk=disk, path=PATH,
                    max_steps=1_500_000_000, alert_answers=answers,
                    build_options={"runtime_sections": "all"})
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r


def page(r):
    return r.cpu.canvas_pixels(SX, SY, CW, CH)


_REFS: dict[str, list[str]] = {}


def reference(drawing: str, with_icons=False) -> list[str]:
    key = drawing + str(with_icons)
    if key not in _REFS:
        head = 'DIM Icons AS BITMAP * 24, 144\nBITMAP LOAD Icons, "P2ICONS.PBI"\n' if with_icons else ""
        src = (f'{head}WINDOW W, "R", LARGE\nLABEL S$\nCANVAS {CW}, {CH}, PAINT P\nBUTTON "Q", Q\n'
               f"SUB P\n    DRAW CLEAR\n{drawing}END SUB\nSUB Q\n    EXIT\nEND SUB\nEND\n")
        program = check_source(src)
        lay = build_dialog(program, program.windows[0], False)
        assert (lay.canvas[1], lay.canvas[2]) == (SX, SY)
        disk = z80sim.Disk(files={(F, "P2ICONS.PBI"): ICONS})
        r = guarded_run(src, events=[], disk=disk)
        assert r.violations == [] and not r.alerts, (r.violations, r.alerts)
        _REFS[key] = r.cpu.canvas_pixels(SX, SY, CW, CH)
    return _REFS[key]


def design(r, name):
    data = r.cpu.disk.file(name)
    code, info = pdbcheck.check(data, SIG)
    assert code == 0, (code, info)
    return pdbcheck.decode(data, SIG, info["count"])


def pdb(records) -> bytes:
    """A PDB1 file of DesignRec records (LANGUAGE-SPEC §5.9), built here."""
    body = b""
    for kind, x, y, w, h, shade, cap in records:
        body += struct.pack("<6h", kind, x, y, w, h, shade) + cap.encode("latin-1").ljust(31, b"\0")
    head = b"PDB1" + bytes([1, 0]) + struct.pack("<HHHHH", 43, len(records), 1, pdbcheck.crc16(SIG.encode()), 0)
    s1 = s2 = 0
    for byte in head + body:
        s1 = (s1 + byte) % 65536
        s2 = (s2 + s1) % 65536
    return head + body + struct.pack("<HH", s1, s2)


HEADER = (0, 1, 0, CW, CH, 0, "PCW16 DESIGN")


@requires_pasmo
class EditingTests(unittest.TestCase):
    def test_add_select_and_handles(self):
        r = run([B["Box"]], answers=[1])
        pic = page(r)
        ref = reference("    DRAW BOX 8, 8, 80, 48\n")
        # the handles are inverted 5 x 5 squares on the corners and sides
        self.assertEqual(pic[8][6:11], "".join("#" if c == "." else "." for c in ref[8][6:11]))
        self.assertEqual(string_var(r, "APPSTATUS$"), "Box 8,8 80x48*")
        r = run([B["Box"]] + NOTHING, answers=[1])
        self.assertEqual(page(r), ref)
        self.assertEqual(string_var(r, "APPSTATUS$"), "1 objects *")

    def test_drag_moves_and_leaves_nothing_behind(self):
        ev = [B["Box"]] + drag([(30, 30), (200, 100), (60, 40), (130, 80)]) + NOTHING
        r = run(ev, answers=[1])
        self.assertEqual(page(r), reference("    DRAW BOX 108, 58, 80, 48\n"))

    def test_a_drag_is_kept_on_the_page(self):
        ev = [B["Box"]] + drag([(30, 30), (900 - SX, 900 - SY)]) + click(5, 230)
        r = run(ev, answers=[1])
        self.assertEqual(page(r), reference(f"    DRAW BOX {CW - 80}, {CH - 48}, 80, 48\n"))

    def test_resize_by_a_handle(self):
        # handle 5 is the bottom-right corner, 87, 55
        ev = [B["Box"]] + drag([(87, 55), (150, 90), (127, 75)]) + NOTHING
        r = run(ev, answers=[1])
        self.assertEqual(page(r), reference("    DRAW BOX 8, 8, 120, 68\n"))
        # handle 1, the top left, past the opposite corner: never smaller than 8 x 8
        ev = [B["Box"]] + drag([(8, 8), (300, 200)]) + NOTHING
        self.assertEqual(page(run(ev, answers=[1])), reference("    DRAW BOX 80, 48, 8, 8\n"))

    def test_overlap_topmost_is_picked_and_restacked(self):
        # a black panel under a white button: clicking where they overlap picks the button
        ev = [B["Panel"]] + props(pshade=0) + [B["Button"]] + drag([(20, 20), (60, 40)])
        ev += NOTHING + click(55, 35)  # the button now at 48, 28
        r = run(ev + [BACK] + NOTHING + files("Z", "Save as"), answers=[1])
        recs = design(r, "Z.DSN")
        self.assertEqual([rec[0] for rec in recs], [0, 4, 2])  # the button went to the back
        drawn = reference("    DRAW FILL 48, 28, 72, 24, 8\n    DRAW BOX 48, 28, 72, 24\n"
                          "    DRAW BOX 50, 30, 68, 20\n    DRAW TEXT 48 + (72 - TEXTWIDTH(\"OK\")) / 2, 32, \"OK\"\n"
                          "    DRAW FILL 8, 8, 96, 56, 0\n    DRAW BOX 8, 8, 96, 56\n")
        self.assertEqual(page(r), drawn)
        r = run(ev + [BACK, FRONT] + NOTHING, answers=[1])
        self.assertEqual(page(r)[40][100:110], reference(
            "    DRAW FILL 8, 8, 96, 56, 0\n    DRAW BOX 8, 8, 96, 56\n    DRAW FILL 48, 28, 72, 24, 8\n"
            "    DRAW BOX 48, 28, 72, 24\n    DRAW BOX 50, 30, 68, 20\n    DRAW TEXT 48 + (72 - TEXTWIDTH(\"OK\")) / 2, 32, \"OK\"\n")[40][100:110])

    def test_redrawing_a_part_keeps_what_lies_above(self):
        # back to front: a panel, a box on it, a label on the panel. Moving
        # the label away redraws the panel, so the box on it must be redrawn
        # over it, although the label never touched the box
        ev = [B["Panel"], B["Box"]] + props(px=60, py=40) + [B["Label"]]
        ev += drag([(20, 12), (20, 16)]) + NOTHING  # a small move: only the label's area is dirty
        r = run(ev, answers=[1])
        self.assertEqual(page(r), reference(
            "    DRAW FILL 8, 8, 96, 56, 6\n    DRAW BOX 8, 8, 96, 56\n    DRAW BOX 60, 40, 80, 48\n"
            '    DRAW TEXT 11, 12, "Label"\n'))

    def test_redrawing_follows_overlaps_in_any_order(self):
        # back to front: a panel P, a box T on it, a box Q over P's corner, a
        # label R touching only Q. Moving R redraws Q, and so P (under Q),
        # and so T (on P): P is reached only after Q in the stacking order
        ev = [B["Panel"], B["Box"]] + props(px=20, py=20, pw=30, ph=20) + [B["Box"]] + props(px=60, py=40)
        ev += [B["Label"]] + props(px=120, py=80) + drag([(130, 85), (130, 90)]) + NOTHING
        r = run(ev, answers=[1])
        self.assertEqual(page(r), reference(
            "    DRAW FILL 8, 8, 96, 56, 6\n    DRAW BOX 8, 8, 96, 56\n    DRAW BOX 20, 20, 30, 20\n"
            '    DRAW BOX 60, 40, 80, 48\n    DRAW TEXT 123, 85, "Label"\n'))

    def test_keys_nudge_and_delete(self):
        ev = [B["Box"], ("key", KC_RIGHT), ("key", KC_RIGHT), ("key", KC_DOWN)] + NOTHING
        self.assertEqual(page(run(ev, answers=[1])), reference("    DRAW BOX 10, 9, 80, 48\n"))
        ev = [B["Box"], B["Panel"], ("key", KC_DELETE)] + NOTHING
        self.assertEqual(page(run(ev, answers=[1])), reference("    DRAW BOX 8, 8, 80, 48\n"))

    def test_snap_to_grid(self):
        ev = [SNAP, B["Box"]] + drag([(30, 30), (37, 31)]) + NOTHING
        self.assertEqual(page(run(ev, answers=[1])), reference("    DRAW BOX 16, 8, 80, 48\n"))

    def test_properties(self):
        ev = [B["Label"]] + props(pcaption="Name:", px=100, py=60, pw=120, ph=20) + NOTHING
        r = run(ev, answers=[1])
        self.assertEqual(page(r), reference('    DRAW TEXT 103, 62, "Name:"\n'))
        ev = [B["Box"]] + props(px=500, pw=80)
        r = run(ev + [PB["Cancel"]] + NOTHING, answers=[1])
        self.assertIn("It must fit the page: X + width at most 544, Y + height at most 240", r.alerts)
        self.assertEqual(page(r), reference("    DRAW BOX 8, 8, 80, 48\n"))

    def test_a_long_caption_shows_its_beginning(self):
        # drawn as far as it fits inside the frame (never past the object, never
        # an error); the caption itself is kept whole in the design
        ev = [B["Button"]] + props(pcaption="Print everything now") + NOTHING
        r = run(ev + files("L", "Save as"))
        self.assertEqual(page(r), reference(
            '    LOCAL T$ AS STRING\n    T$ = "Print everything now"\n'
            "    WHILE TEXTWIDTH(T$) > 66\n        T$ = LEFT$(T$, LEN(T$) - 1)\n    WEND\n"
            "    DRAW FILL 8, 8, 72, 24, 8\n    DRAW BOX 8, 8, 72, 24\n    DRAW BOX 10, 10, 68, 20\n"
            "    DRAW TEXT 8 + (72 - TEXTWIDTH(T$)) / 2, 12, T$\n"))
        self.assertEqual(design(r, "L.DSN")[1][6], "Print everything now")

    def test_icons(self):
        ev = [B["Icon"]] + props(pshade=3) + NOTHING
        r = run(ev, answers=[1])
        self.assertEqual(page(r), reference("    BITMAP PUT Icons, 8, 8, 0, 48, 24, 24\n", with_icons=True))
        r = run([B["Icon"]] + props(pshade=7) + [PB["Cancel"]], answers=[1])
        self.assertIn("An icon is number 1 to 6", r.alerts)


@requires_pasmo
class FileTests(unittest.TestCase):
    def test_save_writes_a_versioned_design(self):
        ev = [B["Box"], B["Label"]] + props(px=40, py=100, pcaption="Hello") + files("FORM", "Save as")
        r = run(ev)
        self.assertTrue(r.cpu.exited)  # saved: Quit asks nothing
        recs = design(r, "FORM.DSN")
        self.assertEqual(recs[0], list(HEADER))
        self.assertEqual(recs[1], [1, 8, 8, 80, 48, 0, ""])
        self.assertEqual(recs[2], [3, 40, 100, 80, 16, 0, "Hello"])

    def test_open_round_trip_and_backup(self):
        data = pdb([HEADER, (2, 10, 10, 100, 50, 3, ""), (4, 20, 20, 60, 24, 0, "Go")])
        r = run([OPEN, ("edit", FB["FILENAME$"], "form"), FB["Open"]] + NOTHING, disk_files={"FORM.DSN": data})
        self.assertEqual(page(r), reference("    DRAW FILL 10, 10, 100, 50, 3\n    DRAW BOX 10, 10, 100, 50\n"
                                            "    DRAW FILL 20, 20, 60, 24, 8\n    DRAW BOX 20, 20, 60, 24\n"
                                            "    DRAW BOX 22, 22, 56, 20\n    DRAW TEXT 20 + (60 - TEXTWIDTH(\"Go\")) / 2, 24, \"Go\"\n"))
        r = run([OPEN, ("edit", FB["FILENAME$"], "form"), FB["Open"], B["Box"], SAVE], disk_files={"FORM.DSN": data})
        self.assertEqual(r.cpu.disk.file("FORM.BAK"), data)
        self.assertEqual(len(design(r, "FORM.DSN")), 4)

    def test_damaged_and_foreign_files_are_refused(self):
        good = [HEADER, (1, 10, 10, 50, 50, 0, "")]
        cases = {
            "not a design": pdb([(0, 1, 0, CW, CH, 0, "SOMETHING ELSE")]),
            "scene version 2, this program reads 1": pdb([(0, 2, 0, CW, CH, 0, "PCW16 DESIGN")]),
            "another page size": pdb([(0, 1, 0, 320, 200, 0, "PCW16 DESIGN")]),
            "object 1 is an unknown kind 9": pdb([HEADER, (9, 10, 10, 50, 50, 0, "")]),
            "object 2 is off the page": pdb(good + [(1, 500, 10, 50, 50, 0, "")]),
            "object 1 is too small": pdb([HEADER, (3, 10, 10, 50, 8, 0, "x")]),
            "object 1 is a shade outside 0 to 8": pdb([HEADER, (2, 10, 10, 50, 50, 9, "")]),
            "object 1 is not an icon 1 to 6 of 24 x 24": pdb([HEADER, (5, 10, 10, 24, 24, 0, "")]),
            "object 1 is a double quote in its caption": pdb([HEADER, (3, 10, 10, 50, 16, 0, 'a"b')]),
            "damaged": pdb(good)[:-1],
            "not found": None,
        }
        for why, data in cases.items():
            with self.subTest(why):
                d = {"BAD.DSN": data} if data is not None else {}
                ev = [B["Box"], OPEN, ("edit", FB["FILENAME$"], "BAD"), FB["Open"], FB["Back"]] + NOTHING
                r = run(ev, disk_files=d, answers=[1, 1])
                self.assertIn("Not opened: " + why, r.alerts)
                self.assertEqual(page(r), reference("    DRAW BOX 8, 8, 80, 48\n"))  # the design is kept

    def test_unsaved_changes_are_asked_about(self):
        self.assertFalse(run([B["Box"]], answers=[2]).cpu.exited)
        self.assertTrue(run([B["Box"]], answers=[1]).cpu.exited)
        self.assertTrue(run([]).cpu.exited)


@requires_pasmo
class ExportTests(unittest.TestCase):
    SESSION = [SAMPLE] + NOTHING

    def test_sample(self):
        r = run(self.SESSION, answers=[1])
        self.assertGreater(sum(row.count("#") for row in page(r)), 3000)
        self.assertEqual(string_var(r, "APPSTATUS$"), "9 objects SAMPLE.DSN*")

    def test_export_picture(self):
        r = run(self.SESSION + [EXPORT, ("edit", FB["FILENAME$"], "shot"), FB["Picture"]] + NOTHING, answers=[1])
        data = r.cpu.disk.file("SHOT.PBI")
        self.assertEqual(pbicheck.check(data)[0], 0)
        self.assertEqual(pbicheck.pixels(data), [[1 if c == "#" else 0 for c in row] for row in page(r)])

    def test_export_basic_draws_the_same_page(self):
        r = run(self.SESSION + [EXPORT, ("edit", FB["FILENAME$"], "form"), FB["BASIC"]] + NOTHING, answers=[1])
        text = r.cpu.disk.file("FORM.BAS").decode("latin-1")
        self.assertIn("SUB DrawDesign", text)
        self.assertTrue(text.endswith("END SUB\r\n"))
        body = text.replace("\r\n", "\n")
        src = ('DIM Icons AS BITMAP * 24, 144\nBITMAP LOAD Icons, "P2ICONS.PBI"\n'
               f'WINDOW W, "R", LARGE\nLABEL S$\nCANVAS {CW}, {CH}, PAINT P\nBUTTON "Q", Q\n'
               f"{body}SUB P\n    DRAW CLEAR\n    CALL DrawDesign\nEND SUB\nSUB Q\n    EXIT\nEND SUB\nEND\n")
        program = check_source(src)
        lay = build_dialog(program, program.windows[0], False)
        self.assertEqual((lay.canvas[1], lay.canvas[2]), (SX, SY))
        out = guarded_run(src, events=[], disk=z80sim.Disk(files={(F, "P2ICONS.PBI"): ICONS}))
        self.assertEqual(out.violations, [])
        self.assertEqual(out.cpu.canvas_pixels(SX, SY, CW, CH), page(r))

    def test_print(self):
        r = run(self.SESSION + [PRINT], answers=[1])
        self.assertEqual(string_var(r, "APPSTATUS$"), "Printed")


if __name__ == "__main__":
    unittest.main()
