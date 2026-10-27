"""M13 corrective (the owner's first XAnne sessions of 618d80a): the defects
the owner found, each reproduced on the program the owner ran and shown
corrected on the program built from this source.

- P0 DESIGNER: Picture export wrote a PBI over FORM.DSN (the name in the
  Files box kept its .DSN); BASIC export could do the same; and even a
  correctly named export shared FORM.NEW / FORM.BAK with the design.
- P1 Ctrl shortcuts: an ITEM without KEY got the hotkey word #0000, which
  Rosanne's hotkey search takes for the end of its title (z80sim.ddm_hotkey):
  PAINT II Ctrl+Z/Y/C/V/Q and DESIGNER Ctrl+D/F did nothing, Ctrl+S worked.
- P1 KEYDOWN codes: lib/keys.pbas gave the cursor keys the keypad's numbers;
  Rosanne gives them 99, 100, 101, 98 (z80sim.keystate_code; owner SPRPROBE).
- P1 timers: Rosanne merges ticks it could not deliver (one "due" flag per
  timer) and in XAnne a 1/16 s TIMER came about 3.5 times a second; JUMPER
  moved one step per event and so crawled. It now steps by the clock
  (CLOCKTICKS, lib/pace.pbas), catches up at most four steps, keeps a short
  press of Space, and draws only what moved.

"The program the owner ran" is artifacts/m13/*.PRG from 618d80a, run
unchanged. Simulator evidence, labelled so: what XAnne does with the
corrected builds is the owner's retest, docs/M13-ACCEPTANCE.md RT1-RT5.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import check_source
from pbas.prg import build
from toolchain import need_file, requires_pasmo

import test_m13_designer as dz
import test_m13_jumper as jz
import test_m13_paint2 as pz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pbicheck  # noqa: E402
import pdbcheck  # noqa: E402

ORIG = ROOT / "artifacts" / "m13"  # what the owner ran (618d80a)
F = "\\PCW\\FOLDER01"
CTRL = 4


def original(name, events, files, answers=None, **sim):
    """artifacts/m13/<name> run on the simulator, as the owner ran it."""
    need_file(ORIG / "MANIFEST.md", "the builds the owner ran in XAnne at M13")  # M14
    disk = z80sim.Disk(files={(F, n): d for n, d in files.items()})
    return z80sim.run((ORIG / name).read_bytes(), events=events, disk=disk, alert_answers=answers,
                      max_steps=1_500_000_000, **sim)


def ctrl(letter):
    return ("type", ord(letter.lower()), CTRL)


# ------------------------------------------------------------------ P0 DESIGNER
SAVE_FORM = [dz.SAMPLE] + dz.NOTHING + [dz.SAVEAS, ("edit", dz.FB["FILENAME$"], "FORM"), dz.FB["Save as"]]
# the owner's export: the Files window as it opens (the name it shows), then Picture
PICTURE = [dz.EXPORT, dz.FB["Picture"]] + dz.NOTHING
BASIC = [dz.EXPORT, dz.FB["BASIC"]] + dz.NOTHING
UNRELATED = {"OTHER.PBI": b"not mine 1", "FORM.TXT": b"not mine 2", "NOTES.BAK": b"not mine 3",
             "PLAN.DSN": b"not mine 4"}


def dsn_count(data):
    code, info = pdbcheck.check(data, dz.SIG)
    return info["count"] if code == 0 else None


def new_designer(events, files=None, answers=(1, 1, 1, 1)):
    d = dict(UNRELATED)
    d.update(files or {})
    return dz.run(events, disk_files=d, answers=list(answers), quit=False).cpu


def old_designer(events, files=None):
    d = {"P2ICONS.PBI": dz.ICONS}
    d.update(UNRELATED)
    d.update(files or {})
    return original("DESIGNER.PRG", events, d, answers=[1, 1, 1, 1])


@requires_pasmo
class DesignerFileSafetyTests(unittest.TestCase):
    """The owner's twelve checks (assignment §3), on real file bytes."""

    @classmethod
    def setUpClass(cls):
        cls.saved = new_designer(SAVE_FORM).disk.file("FORM.DSN")  # FORM.DSN as Save as wrote it

    def check_untouched(self, disk):
        for name, data in UNRELATED.items():  # 12
            self.assertEqual(disk.file(name), data, name)
        self.assertEqual([n for (_, n) in disk.files if n.startswith("DSGNTMP")], [])

    def test_the_owners_session_on_the_original_build_overwrote_the_design(self):
        cpu = old_designer(SAVE_FORM + PICTURE)
        data = cpu.disk.file("FORM.DSN")
        self.assertEqual(pbicheck.check(data)[0], 0)  # FORM.DSN became a picture ...
        self.assertIsNone(dsn_count(data))  # ... no longer a design
        self.assertIsNone(cpu.disk.file("FORM.PBI"))  # and FORM.PBI was not written
        self.assertEqual(dsn_count(cpu.disk.file("FORM.BAK")), 10)  # the design survived as FORM.BAK only

    def test_the_original_build_also_replaced_the_designs_backup(self):
        # a second save makes FORM.BAK the first one; then a correctly named picture
        cpu = old_designer(SAVE_FORM + [dz.SAVE, dz.EXPORT, ("edit", dz.FB["FILENAME$"], "FORM"), dz.FB["Picture"]])
        self.assertEqual(pbicheck.check(cpu.disk.file("FORM.PBI"))[0], 0)
        self.assertIsNone(cpu.disk.file("FORM.BAK"))  # BITMAP SAVE's step 3 deleted the design's backup

    def test_save_export_picture_and_basic(self):
        cpu = new_designer(SAVE_FORM + [dz.SAVE] + PICTURE + BASIC)
        disk = cpu.disk
        for name in ("FORM.DSN", "FORM.PBI", "FORM.BAS", "FORM.BAK"):  # 4
            self.assertIsNotNone(disk.file(name), name)
        self.assertEqual(disk.file("FORM.DSN"), self.saved)  # 5: the design, byte for byte
        self.assertEqual(dsn_count(disk.file("FORM.DSN")), 10)
        self.assertEqual(disk.file("FORM.BAK"), self.saved)  # the second save's backup: the first
        self.assertIsNone(disk.file("FORM.NEW"))
        code, info = pbicheck.check(disk.file("FORM.PBI"))  # 6
        self.assertEqual((code, info["width"], info["height"]), (0, 544, 240))
        text = disk.file("FORM.BAS").decode("latin-1")  # 7
        self.assertTrue(text.startswith("' FORM.BAS: drawn by DESIGNER, 9 objects"))
        self.assertIn("SUB DrawDesign\r\n", text)
        self.assertTrue(text.endswith("END SUB\r\n"))
        check_source('DIM Icons AS BITMAP * 24, 144\nWINDOW W, "R", LARGE\nCANVAS 544, 240, PAINT P\n'
                     + text.replace("\r\n", "\n") + "SUB P\n    CALL DrawDesign\nEND SUB\nEND\n")
        self.check_untouched(disk)

    def test_the_design_reopens_after_the_exports(self):
        ev = SAVE_FORM + PICTURE + BASIC + [dz.NEW, dz.OPEN, ("edit", dz.FB["FILENAME$"], "FORM"), dz.FB["Open"]]
        r = dz.run(ev, disk_files=dict(UNRELATED), answers=[1, 1, 1, 1], quit=False)  # 8
        self.assertEqual(string_var(r, "APPSTATUS$"), "9 objects FORM.DSN")
        self.assertEqual(r.cpu.disk.file("FORM.DSN"), self.saved)
        self.assertEqual(dz.page(r), dz.page(dz.run([dz.SAMPLE] + dz.NOTHING, answers=[1], quit=False)))

    def test_exporting_again_replaces_only_the_export(self):
        ev = SAVE_FORM + PICTURE + [dz.B["Box"]] + dz.NOTHING + PICTURE  # 9: a box added, exported again
        cpu = new_designer(ev)
        first = new_designer(SAVE_FORM + PICTURE).disk.file("FORM.PBI")
        again = cpu.disk.file("FORM.PBI")
        self.assertEqual(pbicheck.check(again)[0], 0)
        self.assertNotEqual(again, first)
        self.assertEqual(cpu.disk.file("FORM.DSN"), self.saved)  # the unsaved box is not in the design
        self.assertIsNone(cpu.disk.file("FORM.BAK"))  # one save: no backup, and the exports made none
        self.check_untouched(cpu.disk)

    def test_names_typed_get_the_exports_own_extension(self):
        for typed, button, made in (("form.bas", "Picture", "FORM.PBI"), ("FORM.DSN", "BASIC", "FORM.BAS"),
                                    ("ABCDEFGH", "Picture", "ABCDEFGH.PBI"), ("form.pbi", "BASIC", "FORM.BAS")):
            with self.subTest(typed=typed, button=button):  # 11
                cpu = new_designer(SAVE_FORM + [dz.EXPORT, ("edit", dz.FB["FILENAME$"], typed), dz.FB[button]]
                                   + dz.NOTHING)
                self.assertIsNotNone(cpu.disk.file(made))
                self.assertEqual(cpu.disk.file("FORM.DSN"), self.saved)
                self.check_untouched(cpu.disk)
        r = dz.run(SAVE_FORM + [dz.EXPORT, ("edit", dz.FB["FILENAME$"], "ABCDEFGHI"), dz.FB["Picture"]],
                   disk_files=dict(UNRELATED), answers=[1, 1], quit=False)
        self.assertIn("A name has at most 8 characters before the dot", r.alerts)
        self.assertEqual(sorted(n for (_, n) in r.cpu.disk.files if n.startswith("ABCDEFGH")), [])

    def test_a_failed_export_leaves_everything_as_it_was(self):
        # 10: an existing export, then a new one that fails while being written
        base = new_designer(SAVE_FORM + PICTURE + BASIC).disk
        files = {n: d for (_, n), d in base.files.items()}
        for button, fn in (("Picture", z80sim.FN_OS_WRITE_FILE), ("BASIC", z80sim.FN_OS_WRITE_FILE),
                           ("Picture", z80sim.FN_OS_RENAME_FILE), ("BASIC", z80sim.FN_OS_RENAME_FILE)):
            with self.subTest(button=button, failing=fn):
                d = dict(files)
                d["P2ICONS.PBI"] = dz.ICONS
                disk = z80sim.Disk(files={(F, n): v for n, v in d.items()}, faults_from={fn: (1, 0xA3)})
                r = guarded_run(dz.SRC, events=[dz.OPEN, ("edit", dz.FB["FILENAME$"], "FORM"), dz.FB["Open"],
                                                dz.B["Box"]] + dz.NOTHING
                                + [dz.EXPORT, dz.FB[button]],
                                disk=disk, path=dz.PATH, max_steps=1_500_000_000, alert_answers=[1, 1, 1],
                                build_options={"runtime_sections": "all"})
                self.assertEqual(r.violations, [])
                self.assertTrue([a for a in r.alerts if a.startswith("Not exported: ")], r.alerts)
                for name in ("FORM.DSN", "FORM.BAK", "FORM.NEW"):  # the design, untouched
                    self.assertEqual(disk.file(name), files.get(name), name)
                own = "FORM.PBI" if button == "Picture" else "FORM.BAS"
                if fn == z80sim.FN_OS_WRITE_FILE or button == "Picture":
                    # failed while writing (BITMAP SAVE renames too): the old export kept
                    self.assertEqual(disk.file(own), files[own], own)
                else:  # the old export deleted, the rename refused: the new one kept in DSGNTMP
                    self.assertIn(b"SUB DrawDesign", disk.file("DSGNTMP.BAS"))
                for name, data in UNRELATED.items():
                    self.assertEqual(disk.file(name), data, name)

    def test_the_files_window_offers_the_designs_name_without_its_extension(self):
        r = dz.run(SAVE_FORM + [dz.EXPORT], disk_files=dict(UNRELATED), answers=[1], quit=False)
        self.assertEqual(string_var(r, "FILENAME$"), "FORM")


# ------------------------------------------------------------- P1 Ctrl shortcuts
MENU_SRC = """DIM Got$ AS STRING * 24
WINDOW W, "M", LARGE
LABEL Got$
CANVAS 200, 100, PAINT P, KEYS K
BUTTON "Quit", Q
MENU "File"
    ITEM "New", A1, KEY "N"
    ITEM "Save as...", A2
    ITEM "-"
    ITEM "Quit", Q, KEY "Q"
END MENU
MENU "Edit"
    ITEM "Undo", A3, KEY "Z"
    ITEM "Clear", A4
    ITEM "Copy", A5, KEY "C"
END MENU
SUB P
END SUB
SUB K
    Got$ = "key " + STR$(KEYCODE) + " " + STR$(KEYSHIFT)
END SUB
SUB A1
    Got$ = "New"
END SUB
SUB A2
    Got$ = "Save as"
END SUB
SUB A3
    Got$ = "Undo"
END SUB
SUB A4
    Got$ = "Clear"
END SUB
SUB A5
    Got$ = "Copy"
END SUB
SUB Q
    Got$ = "Quit"
END SUB
END
"""


def menu_run(events, **build_options):
    return guarded_run(MENU_SRC, events=events, build_options=build_options or None)


def paint2_state(cpu):
    return (cpu.canvas_pixels(pz.SX, pz.SY, pz.CW, pz.CH + pz.TOP), sorted(cpu.disk.files.items()))


def designer_state(cpu):
    return (cpu.canvas_pixels(dz.SX, dz.SY, dz.CW, dz.CH), sorted(cpu.disk.files.items()))


@requires_pasmo
class ShortcutTests(unittest.TestCase):
    """A shortcut does exactly what choosing its menu item does."""

    def test_every_key_reaches_its_item_wherever_items_without_key_are(self):
        for letter, got in (("n", "New"), ("q", "Quit"), ("z", "Undo"), ("c", "Copy")):
            with self.subTest(letter=letter):
                self.assertEqual(string_var(menu_run([ctrl(letter)]), "GOT$"), got)

    def test_the_hotkey_word_0_made_rosanne_miss_them(self):
        # the M13 encoding, kept for accepted executables: the keys before the
        # first item without KEY are found; after it the search counts the
        # rest of File as Edit, so Ctrl+Q chooses Edit's first item, and runs
        # out of titles before it reaches Edit's own keys, which reach KEYS
        for letter, got in (("n", "New"), ("q", "Undo"), ("z", f"key {ord('z')} 4"),
                            ("c", f"key {ord('c')} 4")):
            with self.subTest(letter=letter):
                r = menu_run([ctrl(letter)], legacy_menu_hotkeys=True)
                self.assertEqual(string_var(r, "GOT$"), got)

    def test_the_search_model(self):
        # z80sim.ddm_hotkey on the two encodings of one definition: the
        # (title, entry) it reports, as Rosanne's #7446 counts them
        r = menu_run([])
        self.assertEqual(r.cpu.ddm_hotkey(ord("z"), CTRL), (2, 0))
        self.assertEqual(r.cpu.ddm_hotkey(ord("q"), CTRL), (1, 2))
        self.assertIsNone(r.cpu.ddm_hotkey(ord("z"), 0))  # the shift state must match
        r = menu_run([], legacy_menu_hotkeys=True)
        self.assertEqual(r.cpu.ddm_hotkey(ord("n"), CTRL), (1, 0))
        self.assertEqual(r.cpu.ddm_hotkey(ord("q"), CTRL), (2, 0))  # Quit counted as Edit's first item
        self.assertIsNone(r.cpu.ddm_hotkey(ord("z"), CTRL))  # the walk ran out of titles first

    def test_other_keys_still_reach_the_canvas(self):
        self.assertEqual(string_var(menu_run([("type", ord("k"), CTRL)]), "GOT$"), "key 107 4")
        self.assertEqual(string_var(menu_run([("type", ord("z"), 0)]), "GOT$"), "key 122 0")

    LINE = pz.tool(pz.LINE) + pz.stroke([(10, 10), (60, 40)])
    SEL = pz.tool(pz.SELECT) + pz.stroke([(5, 5), (70, 50)])
    SAVED = [pz.SAVEAS, ("edit", pz.FB["FILENAME$"], "ART"), ("click", pz.FB["Save as"])]
    PAINT_CASES = (  # (before, keys, the menu items they stand for)
        (LINE, "z", [pz.UNDO]), (LINE + [pz.UNDO], "y", [pz.REDO]), (LINE + SEL, "c", [pz.COPY]),
        (LINE + SEL + [pz.COPY], "v", [pz.PASTE]), (LINE + SEL, "x", [pz.CUT]),
        (LINE + SAVED + LINE, "s", [pz.SAVE]), (LINE, "n", [pz.NEW]), (LINE, "q", [pz.QUIT]))

    def test_paint2_shortcuts(self):
        for before, letter, menu in self.PAINT_CASES:
            with self.subTest(letter=letter):
                by_key, by_menu, nothing = (pz.run(ev, answers=[2, 2], quit=False) for ev in
                                            (before + [ctrl(letter)], before + menu, before))
                full = [paint2_state(r.cpu) + (string_var(r, "APPSTATUS$"), r.alerts)
                        for r in (by_key, by_menu, nothing)]
                self.assertEqual(full[0], full[1])
                self.assertNotEqual(full[0], full[2])

    def test_paint2_as_the_owner_ran_it(self):
        files = {"P2ICONS.PBI": pz.ICONS}
        for before, letter, menu in self.PAINT_CASES:
            with self.subTest(letter=letter):
                by_key = original("PAINT2.PRG", before + [ctrl(letter)], files, answers=[2, 2])
                nothing = original("PAINT2.PRG", before, files, answers=[2, 2])
                by_menu = original("PAINT2.PRG", before + menu, files, answers=[2, 2])
                if letter in "ns":  # before the first item without KEY: found (owner: Ctrl+S works)
                    self.assertEqual(paint2_state(by_key), paint2_state(by_menu))
                    self.assertEqual(len(by_key.hotkey_log), 1)
                else:  # owner: Ctrl+Z, Y, C, V, Q did nothing (X was not tried)
                    self.assertEqual(paint2_state(by_key), paint2_state(nothing))
                    self.assertEqual(by_key.hotkey_log, [])

    DESIGN_CASES = (("d", [dz.DUPLICATE]), ("f", [dz.FRONT]), ("b", [dz.BACK]), ("p", [dz.PROPS]),
                    ("s", [dz.SAVE]), ("n", [dz.NEW]))

    def test_designer_shortcuts(self):
        before = [dz.B["Panel"], dz.B["Box"]] + dz.click(20, 20)
        for letter, menu in self.DESIGN_CASES:
            with self.subTest(letter=letter):
                by_key = dz.run(before + [ctrl(letter)], answers=[1, 1], quit=False)
                by_menu = dz.run(before + menu, answers=[1, 1], quit=False)
                self.assertEqual(designer_state(by_key.cpu), designer_state(by_menu.cpu))
                self.assertEqual(string_var(by_key, "APPSTATUS$"), string_var(by_menu, "APPSTATUS$"))
        files = {"P2ICONS.PBI": dz.ICONS}
        for letter, menu in self.DESIGN_CASES[:4]:  # the owner's build: Edit's keys were never found
            with self.subTest(original=letter):
                cpu = original("DESIGNER.PRG", before + [ctrl(letter)], files, answers=[1, 1])
                self.assertEqual(cpu.hotkey_log, [])
                self.assertEqual(designer_state(cpu), designer_state(original("DESIGNER.PRG", before, files,
                                                                              answers=[1, 1])))

    def test_a_shortcut_while_a_text_field_has_been_typed_in(self):
        # the Files window, its name field just typed into: Ctrl+S saves the picture
        # (simulator: Rosanne's search does not look at the focus; XAnne RT1.7)
        before = self.LINE + self.SAVED + self.LINE + [pz.SAVEAS, ("edit", pz.FB["FILENAME$"], "ZZZ")]
        by_key = pz.run(before + [ctrl("s")], answers=[1])
        self.assertIsNotNone(by_key.cpu.disk.file("ART.BAK"))
        self.assertIsNone(by_key.cpu.disk.file("ZZZ.PBI"))


# ------------------------------------------------------------------ P1 KEYDOWN
def jumper_page(cpu):
    return cpu.canvas_pixels(jz.SX, jz.SY, jz.CW, jz.CH)


@requires_pasmo
class KeyCodeTests(unittest.TestCase):
    def test_lib_keys_has_rosannes_numbers(self):
        text = (ROOT / "examples" / "lib" / "keys.pbas").read_text(encoding="utf-8")
        consts = {}
        for line in text.splitlines():
            if line.startswith("CONST SC_"):
                name, value = line[6:].split(" = ")
                consts[name[3:]] = int(value)
        self.assertEqual((consts["LEFT"], consts["RIGHT"], consts["UP"], consts["DOWN"]), (99, 100, 101, 98))
        self.assertEqual((consts["SPACE"], consts["A"]), (41, 28))  # as the owner saw them
        for name, value in consts.items():
            with self.subTest(name):
                self.assertEqual(z80sim.keystate_code(name), value)
        self.assertEqual(len(set(consts.values())), len(consts))  # no two keys share a number

    def test_jumper_runs_on_the_cursor_keys(self):
        for key in ("RIGHT", "LEFT"):
            with self.subTest(key):
                moved = jz.run(jz.script_events([{key}] * 10))
                self.assertEqual(jz.state_of(moved), jz.model_state(jz.play([{key}] * 10)))
        self.assertEqual(jz.state_of(jz.run(jz.script_events([{"RIGHT"}] * 10)))["x"], 12 + 40)

    def test_jumper_as_the_owner_ran_it_did_not_run(self):
        # held Right (100) for ten steps: the owner's build drew what standing still draws
        held = original("JUMPER.PRG", jz.script_events([{"RIGHT"}] * 10), jz.ASSETS, clock_by_steps=False)
        still = jz.run(jz.script_events([set()] * 10), quit=False)
        self.assertEqual(jumper_page(held), jz.page(still))
        self.assertNotEqual(jz.page(jz.run(jz.script_events([{"RIGHT"}] * 10), quit=False)), jz.page(still))


# ------------------------------------------------------------- P1 timers, JUMPER
def xanne_waits(seconds, per_second=3.5):
    """The waits (in 1/16 s) before each event of a TIMER that comes
    per_second times a second: the owner's SPRPROBE T1 had 35 in 10 s."""
    out, last, n = [], 0, 0
    while True:
        n += 1
        at = min(round(n * 16 / per_second), seconds * 16)
        out.append(at - last)
        last = at
        if at == seconds * 16:
            return out


def delivered(keys, waits):
    """New game, keys held throughout, a TIMER event after each wait."""
    ev = [jz.B["New game"]] + [("hold", k, True) for k in sorted(keys)]
    for w in waits:
        ev += [("wait", w), ("timer", 0)]
    return ev


PACE_SRC = ('INCLUDE "lib/pace.pbas"\nDIM S$ AS STRING * 24\nWINDOW W, "P", LARGE\nLABEL S$\n'
            'BUTTON "Go", Go\nTIMER T, EVERY 2 TICKS\nSUB Go\n    CALL PaceStart(2, 4)\nEND SUB\n'
            'SUB T\n    S$ = S$ + STR$(PaceSteps()) + ","\nEND SUB\nEND\n')


@requires_pasmo
class PacingTests(unittest.TestCase):
    def test_clockticks(self):
        src = 'DIM T AS INTEGER\nT = CLOCKTICKS\nMESSAGE STR$(T)\nEND\n'
        self.assertEqual(guarded_run(src, events=[], clock_by_steps=False).alerts, ["896"])  # 12:34:56.000
        r = guarded_run(src, events=[], clock_by_steps=False, clock_tick_step=1)
        self.assertEqual(r.alerts, ["896"])

    def pace(self, waits):
        program = check_source(PACE_SRC, path=jz.PATH)
        from pbas.layout import build_dialog
        go = ("click", next(o.number for o in build_dialog(program, program.windows[0], False).objects
                            if o.kind == "BUTTON"))
        ev = [go]
        for w in waits:
            ev += [("wait", w), ("timer", 0)]
        # a Rosanne timer (as the corrective builds): one handler run per
        # script entry, whatever the clock did (M13 responsiveness)
        r = guarded_run(PACE_SRC, events=ev, path=jz.PATH, clock_by_steps=False,
                        build_options={"legacy_timing": True})
        self.assertEqual(r.violations, [])
        return string_var(r, "S$")

    def test_pace_steps_by_the_clock(self):
        # carried remainders; 16 sixteenths capped at 4 steps; a clock gone back counts nothing
        self.assertEqual(self.pace([2, 3, 1, 4, 16, -8, 2]), "1,1,1,2,4,0,1,")
        self.assertEqual(self.pace([16] * 6), "4,4,4,4,4,4,")  # over the minute (the clock starts at :56)
        self.assertEqual(self.pace([1, 1, 1, 1]), "0,1,0,1,")

    def test_jumper_keeps_its_speed_however_the_timer_comes(self):
        xanne = xanne_waits(5)  # 5 s as XAnne delivered: 18 events
        self.assertEqual((len(xanne), sum(xanne)), (18, 80))
        want = jz.model_state(jz.play([{"RIGHT"}] * 40))
        for name, waits, sim in (("as asked", [2] * 40, {}), ("XAnne", xanne, {}),
                                 ("XAnne, a clock in quarter seconds", xanne, {"clock_tick_step": 64})):
            with self.subTest(name):
                got = jz.state_of(jz.run(delivered({"RIGHT"}, waits), **sim))
                self.assertEqual(got, want)
        # one event a second (the corrective build, a Rosanne timer): four steps each at most
        # (a stall slows the game, it never leaps)
        self.assertEqual(jz.state_of(jz.run(delivered({"RIGHT"}, [16] * 5), legacy_timing=True))["x"],
                         12 + 4 * 4 * 5)
        # M13 RT6: the loop's own TIMER runs every 2/16 s while those seconds pass: full speed
        self.assertEqual(jz.state_of(jz.run(delivered({"RIGHT"}, [16] * 5)))["x"], 12 + 4 * 40)

    def test_the_owners_build_moved_a_step_an_event(self):
        xanne = xanne_waits(5)
        old = original("JUMPER.PRG", delivered(set(), xanne), jz.ASSETS, clock_by_steps=False)
        steps_18 = jz.run(delivered(set(), [2] * 18), quit=False)
        steps_40 = jz.run(delivered(set(), xanne), quit=False)
        self.assertEqual(jumper_page(old), jz.page(steps_18))  # 18 steps in 5 s, not 40
        self.assertEqual(jz.page(steps_40), jz.page(jz.run(delivered(set(), [2] * 40), quit=False)))

    def test_a_short_press_of_space_jumps(self):
        ev = [jz.B["New game"], ("wait", 2), ("timer", 0), ("key", 32), ("wait", 2), ("timer", 0)]
        s = jz.state_of(jz.run(ev))
        self.assertEqual((s["y"], s["vy"]), (180 - 13, -11))  # in the air
        old = original("JUMPER.PRG", ev, jz.ASSETS, clock_by_steps=False)
        still = jz.run([jz.B["New game"], ("wait", 2), ("timer", 0), ("wait", 2), ("timer", 0)], quit=False)
        self.assertEqual(jumper_page(old), jz.page(still))  # the owner's build missed it

    def test_holding_space_with_its_key_repeats_jumps_once(self):
        ev = [jz.B["New game"], ("hold", "SPACE", True)]
        for _ in range(30):
            ev += [("key", 32), ("wait", 2), ("timer", 0)]
        self.assertEqual(jz.state_of(jz.run(ev)), jz.model_state(jz.play([{"SPACE"}] * 30)))

    def test_only_what_moved_is_drawn(self):
        ev = [jz.B["New game"], ("wait", 2), ("timer", 0)]
        step = [("hold", "RIGHT", True), ("wait", 2), ("timer", 0)]
        new = len(jz.run(ev + step).cpu.bitmap_log) - len(jz.run(ev).cpu.bitmap_log)
        old = (len(original("JUMPER.PRG", ev + step, jz.ASSETS, clock_by_steps=False).bitmap_log)
               - len(original("JUMPER.PRG", ev, jz.ASSETS, clock_by_steps=False).bitmap_log))
        # the hero and both beetles moved: three put back, three drawn. The
        # owner's build drew every sprite and every coin again each step
        self.assertLess(new, old)
        self.assertLessEqual(new, 6 * 2)
        # a step with the hero standing still: only the two beetles are drawn again
        log = jz.run(ev).cpu.bitmap_log
        after = jz.run(ev + [("wait", 2), ("timer", 0)]).cpu.bitmap_log
        self.assertEqual([e[0] for e in after[len(log):]].count("masked"), 2)



# --------------------------------------------------------------- the probes
TIMEPRB = ROOT / "developer-tests" / "timeprb.pbas"


def timeprb(events, legacy_timing=False, **sim):
    src = TIMEPRB.read_text(encoding="utf-8")
    from pbas.layout import build_dialog
    program = check_source(src, path=TIMEPRB)
    b = {o.text: ("click", o.number) for o in build_dialog(program, program.windows[0], False).objects
         if o.kind == "BUTTON"}
    r = guarded_run(src, events=[e if isinstance(e, tuple) else b[e] for e in events], path=TIMEPRB,
                    max_steps=1_500_000_000,
                    build_options={"runtime_sections": "all", "legacy_timing": legacy_timing}, **sim)
    assert r.violations == [], r.violations[:5]
    return [bytes(r.cpu.mem[a:a + 61]).split(b"\0")[0].decode() for a in
            (next(g.start for g in r.regions if g.name == "R$") + 61 * i for i in range(6))]


@requires_pasmo
class ProbeTests(unittest.TestCase):
    def test_c1_shows_how_fine_the_clock_is(self):
        self.assertEqual(timeprb(["Clock"])[0], "C1 clock in 2 s: 32 changes (32 wanted)")
        self.assertEqual(timeprb(["Clock"], clock_tick_step=64)[0], "C1 clock in 2 s: 8 changes (32 wanted)")

    def test_p1_counts_events_and_steps_apart(self):
        # the corrective build (a Rosanne timer), its events as XAnne delivered them
        # (tests/test_m13_responsive.py: the loop's own TIMER, as built now)
        ev = ["Idle"]
        for w in xanne_waits(11):
            ev += [("wait", w), ("timer", 0)]
        rows = timeprb(ev, legacy_timing=True)
        self.assertRegex(rows[0], r"^P1 idle 10 s: 3[3-6] events \(160 wanted\), clock 1(59|6[0-4])/16 s$")
        self.assertRegex(rows[1], r"^steps of 2/16 s: (79|8[0-2]) \(80 wanted\), frames 3[3-6], dropped 0$")


if __name__ == "__main__":
    unittest.main()
