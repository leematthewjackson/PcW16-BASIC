"""M12 Stage A: BITMAPs (LANGUAGE-SPEC §5.12, docs/M12-BITMAP-FORMAT.md).

A BITMAP is a rectangle of screen pixels kept in a 16K block of its own:
BITMAP GET captures part of the canvas with bios_getbitmap, BITMAP PUT draws
it back with bios_plotbitmap, POINT reads one pixel with bios_getpxl, and
BITMAP SAVE / LOAD keep it in a PBI1 file with the database's safe save.

The simulator's BIOS bitmap model (z80sim._bios_bitmap) was written from
ROSAN283's register descriptions and the static reading of PCW045.SYS
(80 bytes a row, bit 7 leftmost, a set bit white): pixel exactness here is
simulator evidence, the screen layout is static evidence, and the owner's
XAnne probe (developer-tests/bmpprb.pbas) decides. Files are compared with
tools/pbicheck.py, written from the format description and not from the
compiler. Every run is checked by the memory guard.
"""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

import z80sim
from memguard import guarded_run
from pbas import SourceError, check_source, generate
from pbas.layout import build_dialog
from toolchain import requires_pasmo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pbicheck  # noqa: E402

F = "\\PCW\\FOLDER01"
BANKS = (None, "all")  # resident runtime, then every movable section in the runtime bank

# A pattern that crosses byte boundaries in every direction.
PATTERN = """    DRAW CLEAR
    DRAW FILL 3, 2, 29, 7
    DRAW LINE 0, 0, 79, 39
    DRAW LINE 79, 0, 0, 39
    DRAW BOX 41, 11, 17, 13
    DRAW PIXEL 5, 30
    DRAW PIXEL 6, 31
    DRAW FILL 60, 25, 9, 3
"""


def program(go: str, dims: str = "", paint: str = PATTERN, canvas=(400, 160)) -> str:
    return (f"{dims}DIM N AS INTEGER\nDIM I AS INTEGER\nDIM J AS INTEGER\nDIM S$ AS STRING\n"
            f'WINDOW W, "Bitmaps", LARGE\nCANVAS {canvas[0]}, {canvas[1]}, PAINT Paint\nBUTTON "Go", Go\n'
            f"SUB Paint\n{paint}END SUB\nSUB Go\n{go}    EXIT\nEND SUB\nEND\n")


def layout(src: str):
    prog = check_source(src)
    lay = build_dialog(prog, prog.windows[0], False)
    go = next(o.number for o in lay.objects if o.kind == "BUTTON" and o.text == "Go")
    return go, lay.canvas[1], lay.canvas[2]


def run(src: str, files=None, banks=None, sim=None, legacy=False, **disk_options):
    """*legacy* (M14): built with --legacy-file-safety, the save code the owner accepted."""
    go, sx, sy = layout(src)
    disk = z80sim.Disk(files={(F, n): d for n, d in (files or {}).items()}, **disk_options)
    options = {"runtime_sections": banks} if banks else {}
    if legacy:
        options["legacy_file_safety"] = True
        options["legacy_tasks_stop"] = True
    r = guarded_run(src, events=[("click", go)], disk=disk, build_options=options or None, **(sim or {}))
    assert r.violations == [], r.violations[:5]
    assert disk.open_at_exit in (None, (None, None)), disk.open_at_exit
    r.sx, r.sy = sx, sy
    return r


def grid(r, x, y, w, h) -> list[str]:
    return r.cpu.canvas_pixels(r.sx + x, r.sy + y, w, h)


def files_of(r) -> dict[str, bytes]:
    return {n: d for (f, n), d in r.cpu.disk.files.items() if f == F and not n.endswith(".PRG")}


def rows_of(lines: list[str]) -> list[list[int]]:
    return [[1 if c == "#" else 0 for c in line] for line in lines]


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> str:
        with self.assertRaises(SourceError) as ctx:
            check_source(src)
        return str(ctx.exception)

    def test_declaration(self):
        self.assertIn("1 to 568 pixels wide", self.reject("DIM B AS BITMAP * 569, 10\nEND\n"))
        self.assertIn("1 to 568 pixels wide", self.reject("DIM B AS BITMAP * 0, 10\nEND\n"))
        self.assertIn("300 high", self.reject("DIM B AS BITMAP * 10, 301\nEND\n"))
        self.assertIn("BITMAP * width, height", self.reject("DIM B AS BITMAP\nEND\n"))
        self.assertIn("BITMAP * width, height", self.reject("DIM B(3) AS BITMAP * 8, 8\nEND\n"))
        check_source("DIM B AS BITMAP * 568, 230\nEND\n")  # 71 x 230 = 16330 bytes

    def test_arguments_may_be_elements_and_event_values(self):
        # M12 fix: BITMAP arguments go through the same name rewriting as
        # DRAW's (an array element, MOUSEX, IOERR are not calls)
        src = ('DIM B AS BITMAP * 8, 8\nDIM A(3) AS INTEGER\nWINDOW W, "B", LARGE\n'
               'CANVAS 100, 50, PAINT P, MOUSE M\nBUTTON "Q", Q\nSUB P\n    BITMAP PUT B, A(1), 0\nEND SUB\n'
               'SUB M\n    BITMAP GET B, MOUSEX, MOUSEY, A(2) + 1, 4\n    BITMAP SAVE B, "B.PBI"\n'
               '    A(3) = IOERR\nEND SUB\nSUB Q\n    EXIT\nEND SUB\nEND\n')
        check_source(src)

    def test_size_limit_is_one_block(self):
        self.assertIn("16384", self.reject("DIM B AS BITMAP * 568, 231\nEND\n"))

    def test_statements(self):
        dims = "DIM B AS BITMAP * 16, 16\nDIM K AS INTEGER\n"
        self.assertIn("needs a CANVAS", self.reject(dims + "BITMAP GET B, 0, 0\nEND\n"))
        self.assertIn("has no CANVAS", self.reject(dims + "K = POINT(1, 1)\nEND\n"))
        self.assertIn("needs a BITMAP", self.reject(program("    BITMAP PUT N, 0, 0\n", dims)))
        self.assertIn("needs a BITMAP", self.reject(program("    N = BITMAPW(K)\n", dims)))
        self.assertIn("2 or 4 more arguments", self.reject(program("    BITMAP GET B, 0, 0, 4\n", dims)))
        self.assertIn("more argument", self.reject(program("    BITMAP PUT B, 0\n", dims)))
        self.assertIn("expects", self.reject(program("    BITMAP SAVE B, 3\n", dims)))
        self.assertIn(".NEW and .BAK", self.reject(program('    BITMAP SAVE B, "A.BAK"\n', dims)))
        self.assertIn(".NEW and .BAK", self.reject(program('    BITMAP LOAD B, "a.new"\n', dims)))
        check_source(program('    BITMAP GET B, 1, 2, 3, 4\n    BITMAP PUT B, 5, 6\n    BITMAP SAVE B, "A.PBI"\n'
                             '    BITMAP LOAD B, S$\n    N = BITMAPW(B) + BITMAPH(B) + POINT(1, 2)\n', dims))

    def test_only_programs_that_use_them_carry_them(self):
        plain = generate(check_source(program("    DRAW CLEAR\n")))
        shown = generate(check_source(program("    BITMAP PUT B, 0, 0\n", "DIM B AS BITMAP * 8, 8\n")))
        filed = generate(check_source(program('    BITMAP SAVE B, "B.PBI"\n', "DIM B AS BITMAP * 8, 8\n")))
        self.assertIn("PB_BITMAP equ 0", plain)
        self.assertIn("PB_BITMAP equ 1", shown)
        self.assertIn("PB_BMPFILE equ 0", shown)
        self.assertIn("PB_BMPFILE equ 1", filed)


@requires_pasmo
class ScreenTests(unittest.TestCase):
    def test_get_put_is_pixel_exact(self):
        go = ("    BITMAP GET B, 1, 1, 77, 37\n    BITMAP PUT B, 203, 97\n"
              "    MESSAGE STR$(BITMAPW(B)) + \" \" + STR$(BITMAPH(B))\n")
        for banks in BANKS:
            with self.subTest(banks=banks):
                r = run(program(go, "DIM B AS BITMAP * 80, 40\n"), banks=banks)
                self.assertEqual(r.alerts, ["77 37"])
                self.assertEqual(grid(r, 203, 97, 77, 37), grid(r, 1, 1, 77, 37))
                self.assertIn("#", "".join(grid(r, 203, 97, 77, 37)))

    def test_get_with_the_declared_size_and_many_strips(self):
        # 300 x 150: 38 bytes a row, 26 rows a 1024-byte strip, 6 strips
        go = "    BITMAP GET B, 0, 0\n    DRAW CLEAR\n    BITMAP PUT B, 100, 10\n"
        paint = PATTERN + "    DRAW LINE 0, 149, 299, 0\n    DRAW FILL 290, 140, 10, 10\n"
        for banks in BANKS:
            with self.subTest(banks=banks):
                r = run(program(go, "DIM B AS BITMAP * 300, 150\n", paint), banks=banks)
                gets = [e for e in r.cpu.bitmap_log if e[0] == "get"]
                self.assertEqual([e[4] for e in gets], [26, 26, 26, 26, 26, 20])
                self.assertEqual({e[2] for e in gets}, {r.sy + 26 * k for k in range(6)})
                # the picture as Paint drew it, now at 100, 10
                ref = run(program("", "", paint), banks=banks)
                self.assertEqual(grid(r, 100, 10, 300, 150), grid(ref, 0, 0, 300, 150))
                self.assertEqual(grid(r, 0, 0, 100, 160), ["." * 100] * 160)

    def test_put_ignores_ink_and_mode_and_restores_them(self):
        go = ("    BITMAP GET B, 0, 0, 40, 20\n    DRAW FILL 200, 100, 10, 10\n    DRAW INK WHITE\n"
              "    BITMAP PUT B, 100, 100\n    DRAW LINE 200, 105, 209, 105\n")
        r = run(program(go, "DIM B AS BITMAP * 40, 20\n"), sim={"bios_ink": 1, "bios_mode": 1})
        self.assertEqual(grid(r, 100, 100, 40, 20), grid(r, 0, 0, 40, 20))
        self.assertEqual((r.cpu.bios_ink, r.cpu.bios_mode), (1, 1))
        # the line after PUT is drawn with the program's white ink again
        self.assertEqual(grid(r, 200, 104, 10, 3), ["#" * 10, "." * 10, "#" * 10])

    def test_mouse_pointer_is_hidden_for_the_bios(self):
        go = "    BITMAP GET B, 0, 0\n    BITMAP PUT B, 50, 50\n    N = POINT(3, 3)\n"
        r = run(program(go, "DIM B AS BITMAP * 40, 20\n"))
        self.assertEqual(r.cpu.mouse_draws_visible, 0)

    def test_a_new_bitmap_is_white(self):
        go = "    DRAW FILL 0, 0, 400, 160\n    BITMAP PUT B, 7, 9\n"
        r = run(program(go, "DIM B AS BITMAP * 33, 21\n"))
        self.assertEqual(grid(r, 7, 9, 33, 21), ["." * 33] * 21)
        self.assertEqual(grid(r, 6, 9, 1, 21), ["#"] * 21)
        self.assertEqual(grid(r, 40, 30, 1, 1), ["#"])

    def test_point(self):
        points = [(0, 0), (1, 0), (3, 2), (31, 8), (32, 8), (5, 30), (6, 30), (41, 11), (42, 12), (399, 159)]
        go = "".join(f'    S$ = S$ + STR$(POINT({x}, {y}))\n' for x, y in points) + "    MESSAGE S$\n"
        for banks in BANKS:
            with self.subTest(banks=banks):
                r = run(program(go), banks=banks)
                want = "".join(str(r.cpu.pixel(r.sx + x, r.sy + y)) for x, y in points)
                self.assertEqual(r.alerts, [want])
                self.assertIn("1", want)
                self.assertIn("0", want)

    def test_rectangles_outside_the_canvas_stop_the_program(self):
        dims = "DIM B AS BITMAP * 40, 20\n"
        for go in ("    BITMAP GET B, 370, 0\n", "    BITMAP PUT B, 0, 150\n", "    N = POINT(400, 0)\n",
                   "    BITMAP GET B, -1, 0, 4, 4\n"):
            with self.subTest(go=go):
                r = run(program(go, dims))
                self.assertTrue(r.alerts and r.alerts[0].startswith("Runtime error"), r.alerts)
                self.assertEqual([e for e in r.cpu.bitmap_log if e[0] != "getpxl"], [])

    def test_a_rectangle_larger_than_the_bitmap(self):
        r = run(program("    BITMAP GET B, 0, 0, 41, 20\n", "DIM B AS BITMAP * 40, 20\n"))
        self.assertEqual(r.alerts[0][:60], "Runtime error: the rectangle is larger than the BITMAP at li")
        # the same bytes in another shape fit: 40 x 20 is 100 bytes, 16 x 50 too
        r = run(program("    BITMAP GET B, 0, 0, 16, 50\n    MESSAGE STR$(BITMAPH(B))\n",
                        "DIM B AS BITMAP * 40, 20\n"))
        self.assertEqual(r.alerts, ["50"])

    def test_two_bitmaps_have_their_own_blocks(self):
        go = ("    BITMAP GET A, 0, 0\n    BITMAP GET B, 40, 10\n    DRAW CLEAR\n"
              "    BITMAP PUT B, 0, 100\n    BITMAP PUT A, 200, 100\n")
        r = run(program(go, "DIM A AS BITMAP * 40, 20\nDIM B AS BITMAP * 40, 20\n"))
        ref = run(program(""))
        self.assertEqual(grid(r, 200, 100, 40, 20), grid(ref, 0, 0, 40, 20))
        self.assertEqual(grid(r, 0, 100, 40, 20), grid(ref, 40, 10, 40, 20))
        self.assertNotEqual(grid(ref, 0, 0, 40, 20), grid(ref, 40, 10, 40, 20))


@requires_pasmo
class FileTests(unittest.TestCase):
    SAVE = ("    BITMAP GET B, 1, 1, 77, 37\n    BITMAP SAVE B, \"ART.PBI\"\n"
            "    MESSAGE STR$(IOERR)\n")

    def test_save_writes_a_valid_file_of_the_pixels(self):
        for banks in BANKS:
            with self.subTest(banks=banks):
                r = run(program(self.SAVE, "DIM B AS BITMAP * 80, 40\n"), banks=banks)
                self.assertEqual(r.alerts, ["0"])
                data = files_of(r)["ART.PBI"]
                code, head = pbicheck.check(data)
                self.assertEqual(code, 0)
                self.assertEqual(head, {"version": 1, "width": 77, "height": 37, "row": 10, "bytes": 370})
                self.assertEqual(len(data), 16 + 370 + 4)
                self.assertEqual(pbicheck.pixels(data), rows_of(grid(r, 1, 1, 77, 37)))
                self.assertEqual(sorted(files_of(r)), ["ART.PBI"])

    def test_save_replaces_and_keeps_a_backup(self):
        old = pbicheck.from_rows([[1, 0, 1]] * 2)
        older = pbicheck.from_rows([[1]])
        # an earlier picture as ART.BAK; up to M13 any ART.BAK (here a 5-byte text) was replaced
        for legacy, bak in ((False, older), (True, older), (True, b"older")):
            with self.subTest(legacy=legacy, bak=bak[:5]):
                r = run(program(self.SAVE, "DIM B AS BITMAP * 80, 40\n"), {"ART.PBI": old, "ART.BAK": bak},
                        legacy=legacy)
                self.assertEqual(r.alerts, ["0"])
                self.assertEqual(files_of(r)["ART.BAK"], old)
                self.assertEqual(pbicheck.check(files_of(r)["ART.PBI"])[0], 0)
                self.assertNotIn("ART.NEW", files_of(r))

    def test_another_files_backup_is_kept(self):
        # M14 (KI-91): ART.BAK that is not a picture belongs to another file named ART
        old = pbicheck.from_rows([[1, 0, 1]] * 2)
        r = run(program(self.SAVE, "DIM B AS BITMAP * 80, 40\n"), {"ART.PBI": old, "ART.BAK": b"older"})
        self.assertEqual(r.alerts, ["253"])
        self.assertEqual(files_of(r), {"ART.PBI": old, "ART.BAK": b"older"})

    def test_load_round_trip(self):
        rows = [[(x * y + x // 3) % 2 for x in range(45)] for y in range(23)]
        go = ('    BITMAP LOAD B, "PIC.PBI"\n    MESSAGE STR$(IOERR) + " " + STR$(BITMAPW(B)) + " " + STR$(BITMAPH(B))\n'
              "    BITMAP PUT B, 13, 17\n")
        for banks in BANKS:
            with self.subTest(banks=banks):
                r = run(program(go, "DIM B AS BITMAP * 80, 40\n"), {"PIC.PBI": pbicheck.from_rows(rows)}, banks=banks)
                self.assertEqual(r.alerts, ["0 45 23"])
                self.assertEqual(rows_of(grid(r, 13, 17, 45, 23)), rows)

    def test_save_then_load(self):
        go = ("    BITMAP GET A, 0, 0\n    BITMAP SAVE A, \"T.PBI\"\n    BITMAP LOAD B, \"T.PBI\"\n"
              "    DRAW CLEAR\n    BITMAP PUT B, 300, 100\n    MESSAGE STR$(IOERR) + \" \" + STR$(BITMAPW(B))\n")
        r = run(program(go, "DIM A AS BITMAP * 80, 40\nDIM B AS BITMAP * 90, 50\n"))
        ref = run(program(""))
        self.assertEqual(r.alerts, ["0 80"])
        self.assertEqual(grid(r, 300, 100, 80, 40), grid(ref, 0, 0, 80, 40))

    def test_damaged_and_wrong_files(self):
        good = pbicheck.from_rows([[1, 0] * 10] * 12)
        head = bytearray(good)

        def patched(offset, value, fmt="<H"):
            data = bytearray(good)
            struct.pack_into(fmt, data, offset, value)
            body = bytes(data[:-4])
            return body + struct.pack("<HH", *pbicheck.sums(body))

        cases = {
            "not a bitmap": (b"PBI2" + good[4:], 248),
            "a database": (b"PDB1" + good[4:], 248),
            "too short for a header": (good[:9], 251),
            "empty": (b"", 251),
            "another version": (patched(4, 2, "<B"), 250),
            "flags": (patched(5, 1, "<B"), 250),
            "reserved word": (patched(14, 1), 250),
            "zero width": (patched(6, 0), 251),
            "wider than the screen": (patched(6, 641), 251),
            "row bytes wrong": (patched(10, 4), 251),
            "data bytes wrong": (patched(12, 37), 251),
            "a changed pixel byte": (bytes(head[:20]) + bytes([head[20] ^ 1]) + bytes(head[21:]), 251),
            "a changed check": (good[:-1] + bytes([good[-1] ^ 1]), 251),
            "cut in the rows": (good[:30], 251),
            "cut in the check": (good[:-2], 251),
            "a byte after the end": (good + b"\0", 251),
            "larger than the bitmap": (pbicheck.from_rows([[0] * 64] * 13), 252),  # 104 bytes; 96 fit
        }
        go = ('    BITMAP LOAD B, "X.PBI"\n'
              '    MESSAGE STR$(IOERR) + " " + STR$(BITMAPW(B)) + " " + STR$(BITMAPH(B))\n')
        for what, (data, code) in cases.items():
            with self.subTest(what):
                r = run(program(go, "DIM B AS BITMAP * 32, 24\n"), {"X.PBI": data})
                self.assertEqual(r.alerts, [f"{code} 32 24"])
                self.assertEqual(files_of(r), {"X.PBI": data})
                if code != 252:
                    self.assertEqual(pbicheck.check(data)[0], code)

    def test_no_file(self):
        r = run(program('    BITMAP LOAD B, "NONE.PBI"\n    MESSAGE STR$(IOERR)\n', "DIM B AS BITMAP * 8, 8\n"))
        self.assertNotEqual(r.alerts, ["0"])
        self.assertEqual(files_of(r), {})

    def test_reserved_extensions_at_run_time(self):
        go = ('    S$ = "ART.BAK"\n    BITMAP SAVE B, S$\n    N = IOERR\n'
              '    S$ = "art.new"\n    BITMAP LOAD B, S$\n    MESSAGE STR$(N) + " " + STR$(IOERR)\n')
        r = run(program(go, "DIM B AS BITMAP * 8, 8\n"), {"ART.BAK": b"keep", "ART.NEW": b"keep"})
        self.assertEqual(r.alerts, ["247 247"])
        self.assertEqual(files_of(r), {"ART.BAK": b"keep", "ART.NEW": b"keep"})

    def test_each_failing_save_step_keeps_a_readable_picture(self):
        old = pbicheck.from_rows([[1, 1, 0]] * 3)
        src = program(self.SAVE, "DIM B AS BITMAP * 80, 40\n")
        cases = [
            ({144: {1: 0xA3}}, "163", {"ART.PBI": old}),  # open NAME.NEW
            ({146: {1: 0xA3}}, "163", {"ART.PBI": old}),  # the header's write
            ({146: {2: 0xA3}}, "163", {"ART.PBI": old}),  # a piece of the rows
            ({145: {1: 0x07}}, "7", {"ART.PBI": old}),  # the close
            ({144: {2: 0xA3}}, "163", {"ART.PBI": old}),  # opening it to read it back
            ({147: {3: 0x07}}, "7", {"ART.PBI": old}),  # reading it back
            ({153: {1: 0x05}}, "5", {"ART.PBI": old}),  # deleting the old backup
            ({154: {1: 0x05}}, "5", {"ART.PBI": old}),  # the file to ART.BAK
            ({154: {2: 0x05}}, "5", None),  # ART.NEW to the file: both copies remain
        ]
        for faults, code, after in cases:
            with self.subTest(faults=faults):
                r = run(src, {"ART.PBI": old}, faults_at=faults)
                self.assertEqual(r.alerts, [code])
                left = files_of(r)
                if after is not None:
                    self.assertEqual(left, after)
                else:
                    self.assertEqual(left["ART.BAK"], old)
                    self.assertEqual(pbicheck.check(left["ART.NEW"])[0], 0)
                    self.assertNotIn("ART.PBI", left)

    def test_read_back_catches_a_stale_new_file(self):
        # a longer ART.NEW left by an earlier save of this picture (it starts "PBI1"); on
        # a Rosanne that did not truncate on open its tail would follow the new data
        old = pbicheck.from_rows([[1]])
        stale = old[:16] + b"\xff" * 2000
        for legacy, new in ((False, stale), (True, stale), (True, b"\xff" * 2000)):
            with self.subTest(legacy=legacy, new=new[:4]):
                r = run(program(self.SAVE, "DIM B AS BITMAP * 80, 40\n"),
                        {"ART.PBI": old, "ART.NEW": new}, truncate_on_open=False, legacy=legacy)
                self.assertEqual(r.alerts, ["251"])
                self.assertEqual(files_of(r), {"ART.PBI": old})
        # M14: an ART.NEW that is not a picture is another file's, and is kept
        r = run(program(self.SAVE, "DIM B AS BITMAP * 80, 40\n"),
                {"ART.PBI": old, "ART.NEW": b"\xff" * 2000}, truncate_on_open=False)
        self.assertEqual(r.alerts, ["253"])
        self.assertEqual(files_of(r), {"ART.PBI": old, "ART.NEW": b"\xff" * 2000})


PROBE = Path(__file__).resolve().parents[1] / "developer-tests" / "bmpprb.pbas"


@requires_pasmo
class ProbeTests(unittest.TestCase):
    """developer-tests/bmpprb.pbas as the owner will run it (the times are XAnne's to
    give: the simulator charges nothing for a BIOS call)."""

    def run_probe(self, names, banks="all", **sim):
        src = PROBE.read_text(encoding="utf-8")
        prog = check_source(src, path=PROBE)
        lay = build_dialog(prog, prog.windows[0], False)
        b = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
        r = guarded_run(src, path=PROBE, events=[("click", b[n]) for n in names + ["Quit"]],
                        build_options={"runtime_sections": banks} if banks else None,
                        max_steps=400_000_000, **sim)
        self.assertEqual(r.violations, [])
        self.assertFalse([a for a in r.alerts if a.startswith("Runtime error")], r.alerts)
        self.assertTrue(r.cpu.exited)
        r.sx, r.sy = lay.canvas[1], lay.canvas[2]
        r.lines = [t[2] for t in r.cpu.texts if t[0] == r.sx + 4]
        return r

    def test_copy_points_and_file(self):
        for banks in ("all", None):
            with self.subTest(banks=banks):
                r = self.run_probe(["Copy", "Points", "File"], banks)
                self.assertEqual(grid(r, 320, 0, 120, 80), grid(r, 0, 0, 120, 80))
                self.assertIn("C2: BITMAPW 120, BITMAPH 80 (want 120, 80)", r.lines)
                self.assertIn("P3: want 1 0 1 0 / 1 0 1 1;  differences: 0", r.lines)
                self.assertIn("F1: SAVE IOERR 0, LOAD IOERR 0 (want 0, 0)", r.lines)
                self.assertIn("F2: loaded 120 x 80 (want 120 x 80)", r.lines)
                data = r.cpu.disk.file("BMPPROBE.PBI")
                self.assertEqual(pbicheck.check(data)[0], 0)
                self.assertEqual(pbicheck.pixels(data), rows_of(grid(r, 0, 0, 120, 80)))

    def test_copy_is_drawn_after_copy(self):
        r = self.run_probe(["Copy"])
        self.assertEqual(grid(r, 160, 0, 120, 80), grid(r, 0, 0, 120, 80))
        self.assertIn("#", "".join(grid(r, 160, 0, 120, 80)))

    def test_speed_finishes_and_reports(self):
        with mock.patch.object(z80sim, "CLOCK_RATE", 300_000):
            r = self.run_probe(["Speed"])
        for label in ("S1 GET 120 x 80: ", "S3 GET 560 x 200: ", "S5 POINT: "):
            self.assertTrue([t for t in r.lines if t.startswith(label) and " ms (" in t], (label, r.lines))


class HostCheckerTests(unittest.TestCase):
    def test_round_trip_and_pbm(self):
        rows = [[(x + y) % 3 == 0 for x in range(13)] for y in range(5)]
        rows = [[int(v) for v in r] for r in rows]
        data = pbicheck.from_rows(rows)
        self.assertEqual(pbicheck.check(data)[0], 0)
        self.assertEqual(pbicheck.pixels(data), rows)
        pbm = pbicheck.to_pbm(data)
        self.assertTrue(pbm.startswith(b"P4\n13 5\n"))
        self.assertEqual(len(pbm), len(b"P4\n13 5\n") + 2 * 5)
        # the unused bits of a row's last byte are white
        self.assertEqual(data[16 + 1] & 0x07, 0x07)


if __name__ == "__main__":
    unittest.main()
