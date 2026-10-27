"""M11 corrective (docs/M11-CORRECTIVE.md): TEXTWIDTH and SECONDS, and the
XAnne probe developer-tests/rendprb.pbas that decides how MDEDIT III, CONTACTS IV and
STARTER are redrawn.

TEXTWIDTH(s$) is os_dialog_string_width (fn 82) on the text DRAW TEXT would
draw; the runtime reads HL and not the carry, which Rosanne 1.12 sets on
every call (M5d WIDTHDG). The simulator models that observation: carry set,
A = #07, HL = its font-7 model (z80sim.font7_width), so a runtime that
tested the carry would fail here. SECONDS is bios_gettime's minutes * 60 +
seconds; the simulator's clock runs at z80sim.CLOCK_RATE instructions a
second from z80sim.CLOCK_START.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import z80sim
from memguard import guarded_run
from pbas import SourceError, check_source, generate
from pbas.layout import build_dialog
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "developer-tests" / "rendprb.pbas"


def alerts_of(src: str, **options) -> list[str]:
    r = guarded_run(src, **options)
    assert r.violations == [], r.violations[:5]
    return r.alerts


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> str:
        with self.assertRaises(SourceError) as ctx:
            check_source(src)
        return str(ctx.exception)

    def test_types_and_arity(self):
        self.assertIn("TEXTWIDTH expects a STRING", self.reject("DIM N AS INTEGER\nN = TEXTWIDTH(3)\nEND\n"))
        self.assertIn("TEXTWIDTH expects 1 arguments",
                      self.reject('DIM N AS INTEGER\nN = TEXTWIDTH("a", "b")\nEND\n'))
        self.assertIn("SECONDS expects 0 arguments", self.reject("DIM N AS INTEGER\nN = SECONDS(1)\nEND\n"))
        self.assertIn("cannot assign", self.reject('DIM S$ AS STRING\nS$ = TEXTWIDTH("a")\nEND\n'))

    def test_a_variable_named_seconds_is_still_a_variable(self):
        # examples/stopwatch.pbas (accepted M6) declares Seconds
        check_source("DIM Seconds AS INTEGER\nSeconds = Seconds + 1\nEND\n")

    def test_only_programs_that_use_them_carry_them(self):
        plain = generate(check_source('MESSAGE "x"\nEND\n'))
        used = generate(check_source('DIM N AS INTEGER\nN = TEXTWIDTH("a") + SECONDS\nEND\n'))
        self.assertIn("PB_TEXTW equ 0", plain)
        self.assertIn("PB_CLOCK equ 0", plain)
        self.assertIn("PB_TEXTW equ 1", used)
        self.assertIn("PB_CLOCK equ 1", used)


@requires_pasmo
class TextWidthTests(unittest.TestCase):
    def test_widths_are_rosannes_hl(self):
        src = ('DIM A$ AS STRING\nA$ = "WWWWWWWWWW"\n'
               'MESSAGE STR$(TEXTWIDTH(A$))\n'
               'MESSAGE STR$(TEXTWIDTH("Label tests: long, short, empty"))\n'
               'MESSAGE STR$(TEXTWIDTH(""))\n'
               'MESSAGE STR$(TEXTWIDTH(LEFT$(A$, 3) + "il"))\n'
               'MESSAGE STR$(TEXTWIDTH(CHR$(7) + "a" + CHR$(230)))\nEND\n')
        want = [z80sim.font7_width(t) for t in (b"W" * 10, b"Label tests: long, short, empty", b"",
                                                 b"WWWil", b"?a?")]
        self.assertEqual(alerts_of(src), [str(n) for n in want])
        self.assertEqual(want[0], 110, "the WIDTHDG reading for ten W's")

    def test_the_block_is_dialog_font_7_in_the_programs_block(self):
        r = guarded_run('DIM N AS INTEGER\nN = TEXTWIDTH("ab")\nN = TEXTWIDTH(CHR$(7) + "b" + CHR$(230))\nEND\n')
        self.assertEqual(r.violations, [])
        # what DRAW TEXT would draw: outside 32..223 as '?'
        self.assertEqual([d for f, d in r.cpu.os_log if f == 82], [b"ab", b"?b?"])

    def test_in_a_runtime_banked_program(self):
        src = ('SUB Show\n    MESSAGE STR$(TEXTWIDTH("MW"))\nEND SUB\nCALL Show\nEND\n')
        self.assertEqual(alerts_of(src, build_options={"runtime_sections": "all"}),
                         [str(z80sim.font7_width(b"MW"))])


@requires_pasmo
class SecondsTests(unittest.TestCase):
    def test_minutes_and_seconds_of_the_clock(self):
        start = z80sim.CLOCK_START
        self.assertEqual(alerts_of("MESSAGE STR$(SECONDS)\nEND\n"), [str(start % 3600)])

    def test_the_hour_rolls_over(self):
        with mock.patch.object(z80sim, "CLOCK_START", 13 * 3600 + 59 * 60 + 59):
            got = alerts_of("DIM A AS INTEGER\nDIM B AS INTEGER\nA = SECONDS\nB = SECONDS\n"
                            "WHILE B = A\n    B = SECONDS\nWEND\nMESSAGE STR$(A) + \" \" + STR$(B)\nEND\n")
        self.assertEqual(got, ["3599 0"])

    def test_time_passes_with_work(self):
        with mock.patch.object(z80sim, "CLOCK_RATE", 50_000):
            got = alerts_of("DIM A AS INTEGER\nDIM I AS INTEGER\nDIM N AS INTEGER\nA = SECONDS\n"
                            "FOR I = 1 TO 20000\n    N = N + 1\nNEXT I\n"
                            "MESSAGE STR$((SECONDS - A + 3600) MOD 3600)\nEND\n")
        self.assertGreater(int(got[0]), 0)


class EquOrderTests(unittest.TestCase):
    """tools/asmcheck.py A8: Pasmo 0.5.3 assembles code that uses an equ
    whose value names a later label with that label's first-pass value (0),
    though the symbol table shows the final one. TEXTWIDTH's shared block
    was once assembled as ld de,0008h this way (caught by memguard)."""

    def test_a8(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import asmcheck
        bad = "    ld de,rt_tw_buf+8\nrt_tw_buf equ rt_ds_buf\nrt_ds_buf:\n    defs 136\n"
        good = "    ld de,rt_tw_buf+8\nrt_ds_buf:\n    defs 136\nrt_tw_buf equ rt_ds_buf\n"
        self.assertEqual([f.rule for f in asmcheck.check_source("runtime.z80.asm", bad)], ["A8"])
        self.assertEqual([f.rule for f in asmcheck.check_source("runtime.z80.asm", good)], [])
        self.assertEqual(asmcheck.check_files([ROOT / "runtime" / "runtime.z80.asm"]), [])

    @requires_pasmo
    def test_the_shared_block_is_assembled_at_rt_ds_buf(self):
        r = guarded_run('DIM N AS INTEGER\nWINDOW W, "W"\nCANVAS 100, 50, PAINT P\nBUTTON "Q", Q\n'
                        'SUB Q\n    EXIT\nEND SUB\nSUB P\n    N = TEXTWIDTH("ab")\n    DRAW TEXT 2, 2, STR$(N)\nEND SUB\nEND\n')
        self.assertEqual(r.violations, [])
        self.assertEqual(r.symbols["rt_tw_buf"], r.symbols["rt_ds_buf"])
        self.assertEqual([t[2] for t in r.cpu.texts][-1], str(z80sim.font7_width(b"ab")))


def probe_objects():
    program = check_source(PROBE.read_text(encoding="utf-8"), path=PROBE)
    lay = build_dialog(program, program.windows[0], False)
    buttons = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
    buttons.update({row.var_name: row.number for row in lay.bindings})
    return buttons, lay.canvas[1], lay.canvas[2]


@requires_pasmo
class ProbeTests(unittest.TestCase):
    """developer-tests/rendprb.pbas as the owner will run it (the times are XAnne's to
    give: the simulator charges nothing for an OS call)."""

    B, SX, SY = probe_objects()

    def run_probe(self, events, banks="all", **options):
        r = guarded_run(PROBE.read_text(encoding="utf-8"), path=PROBE, events=events,
                        build_options={"runtime_sections": banks} if banks else None,
                        max_steps=400_000_000, **options)
        self.assertEqual(r.violations, [])
        self.assertFalse([a for a in r.alerts if a.startswith("Runtime error")], r.alerts)
        return r

    def test_widths(self):
        for banks in ("all", None):
            with self.subTest(banks=banks):
                r = self.run_probe([("click", self.B["Widths"]), ("click", self.B["Quit"])], banks)
                drawn = {t[2]: t for t in r.cpu.texts if t[0] - self.SX == 6}
                numbers = [t[2] for t in r.cpu.texts if t[0] - self.SX == 450]
                for sample, number in zip(list(drawn)[-8:], numbers[-8:]):
                    self.assertEqual(number, str(z80sim.font7_width(sample.encode("latin-1"))), sample)
                self.assertEqual(numbers[-8], "110")

    def test_look_inverts_exactly_the_selected_characters(self):
        r = self.run_probe([("click", self.B["Look"]), ("click", self.B["Quit"])])
        inverts = [d for f, d in r.cpu.os_log if f == 117 and d[0] == 4]
        line1 = "# MDEDIT acceptance document"
        x0 = self.SX + 4
        # characters 3..8 ("MDEDIT") of line 1, from TEXTWIDTH of what precedes them
        self.assertIn((4, x0 + z80sim.font7_width(b"# "), self.SY, z80sim.font7_width(b"MDEDIT"), 16), inverts)
        # the caret before character 6 of line 3, one pixel wide
        line3 = b"This file is EDTEST.MD, the M9 editor's acceptance"
        self.assertIn((4, x0 + z80sim.font7_width(line3[:5]), self.SY + 16, 1, 16), inverts)
        self.assertIn((self.SX + 4, self.SY, line1), [t[:3] for t in r.cpu.texts])

    def test_keys_counts_handler_calls(self):
        r = self.run_probe([("key", 97), ("key", 98), ("edit", self.B["TYPED$"], "ab"),
                            ("click", self.B["Keys"]), ("click", self.B["Quit"])])
        self.assertEqual(r.alerts, ["KEYS ran 2 times; the box holds 2 characters"])

    def test_speed_and_pages_finish_and_report(self):
        with mock.patch.object(z80sim, "CLOCK_RATE", 300_000):
            r = self.run_probe([("click", self.B["Speed"]), ("click", self.B["Pages"]),
                                ("click", self.B["Quit"])])
        self.assertTrue(r.cpu.exited)
        report = [t[2] for t in r.cpu.texts if t[0] - self.SX == 4]
        for label in ("T1 DRAW TEXT, 1 character", "T7 TEXTWIDTH, 40 characters",
                      "P1 editor page, cells", "P4 list page, proportional"):
            self.assertIn(label, report)


if __name__ == "__main__":
    unittest.main()
