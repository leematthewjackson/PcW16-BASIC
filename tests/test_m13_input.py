"""M13: timed updates and held keys (LANGUAGE-SPEC §5.15).

TIMER Handler, EVERY n TICKS runs Handler every n sixteenths of a second
(Rosanne's own unit, ROSAN283 os_set_timer); KEYDOWN(code) reads
bios_keystate's table: the numbers Rosanne's keyboard interrupt gives the
keys (z80sim.keystate_code: set-2 scan codes, the #E0 keys translated; the
cursor keys 99, 100, 101, 98, as the owner's SPRPROBE showed in XAnne).
The simulator's event script holds and releases keys ("hold" entries) and
fires timer ticks, so a handler that reads KEYDOWN on every tick is checked
step by step. Simulator evidence: SPRPROBE (docs/M13-ACCEPTANCE.md) measures the real
tick rate and the codes in XAnne.
"""
from __future__ import annotations

import unittest

import z80sim

from memguard import guarded_run, string_var
from pbas import SourceError, check_source, generate
from pbas.layout import build_dialog
from toolchain import requires_pasmo

LEFT, RIGHT, SPACE = "LEFT", "RIGHT", "SPACE"  # held by name: 99, 100, 41

GAME = """DIM X AS INTEGER
DIM Jumps AS INTEGER
DIM Ticks AS INTEGER
DIM S$ AS STRING
WINDOW W, "G"
LABEL S$
CANVAS 200, 60, PAINT P
BUTTON "Quit", Quit
TIMER Update, EVERY 2 TICKS
X = 100
SUB P
    DRAW CLEAR
END SUB
SUB Update
    Ticks = Ticks + 1
    IF KEYDOWN(99) THEN
        X = X - 3
    END IF
    IF KEYDOWN(100) THEN
        X = X + 3
    END IF
    IF KEYDOWN(41) THEN
        Jumps = Jumps + 1
    END IF
    S$ = STR$(X) + " " + STR$(Jumps) + " " + STR$(Ticks)
END SUB
SUB Quit
    EXIT
END SUB
END
"""


def run(src, events, banks="all"):
    r = guarded_run(src, events=events, max_steps=300_000_000,
                    build_options={"runtime_sections": banks} if banks else None)
    assert r.violations == [], r.violations[:5]
    return r


@requires_pasmo
class TimerTicksTests(unittest.TestCase):
    def test_the_interval_is_in_sixteenths(self):
        asm = generate(check_source(GAME))
        self.assertIn("gui_timer_rec:\n    dw 1\n    db 0,1\n    dw 2\n", asm)
        asm = generate(check_source(GAME.replace("EVERY 2 TICKS", "EVERY 2")))
        self.assertIn("gui_timer_rec:\n    dw 1\n    db 0,1\n    dw 32\n", asm)  # seconds as before

    def test_limits(self):
        for every, msg in (("0 TICKS", "1..32767 TICKS"),
                           ("3600", "1..3599 seconds")):
            with self.subTest(every=every):
                with self.assertRaises(SourceError) as ctx:
                    check_source(GAME.replace("EVERY 2 TICKS", f"EVERY {every}"))
                self.assertIn(msg, str(ctx.exception))
        check_source(GAME.replace("EVERY 2 TICKS", "EVERY 32767 TICKS"))

    def test_the_timer_is_set_with_the_ticks(self):
        # M13 responsiveness: the event loop runs it (no os_set_timer), every 2/16 s
        r = run(GAME, [("timer", 0)] * 3)
        self.assertEqual([fn for fn, _ in r.cpu.os_log if fn in (8, 9)], [])
        t = r.cpu.tick_times
        self.assertEqual(len(t), 3)
        self.assertTrue(all(z80sim.CLOCK_RATE // 8 - z80sim.CLOCK_RATE // 64 <= b - a <= z80sim.CLOCK_RATE // 8
                            + z80sim.CLOCK_RATE // 64 for a, b in zip(t, t[1:])), t)
        # with --legacy-timing (the corrective builds) it is Rosanne timer 0, repeating, 2/16 s
        r = guarded_run(GAME, events=[("timer", 0)], max_steps=300_000_000,
                        build_options={"runtime_sections": "all", "legacy_timing": True})
        self.assertEqual([entry for fn, entry in r.cpu.os_log if fn == 8][0], (0, 1, 2))


@requires_pasmo
class KeyDownTests(unittest.TestCase):
    def status(self, events, banks="all"):
        r = run(GAME, events, banks)
        return string_var(r, "S$"), r

    def test_held_keys_move_on_each_tick(self):
        ev = [("hold", LEFT, True), ("timer", 0), ("timer", 0), ("hold", LEFT, False), ("timer", 0),
              ("hold", RIGHT, True), ("hold", SPACE, True), ("timer", 0), ("hold", SPACE, False),
              ("timer", 0), ("hold", RIGHT, False), ("timer", 0)]
        s, r = self.status(ev)
        self.assertEqual(s, "100 1 6")  # left twice, right twice; one jump; six ticks
        self.assertEqual(r.cpu.keystate_reads.count(z80sim.keystate_code(LEFT)), 6)

    def test_two_keys_at_once(self):
        ev = [("hold", RIGHT, True), ("hold", SPACE, True), ("timer", 0), ("timer", 0)]
        self.assertEqual(self.status(ev)[0], "106 2 2")

    def test_without_the_runtime_bank(self):
        self.assertEqual(self.status([("hold", RIGHT, True), ("timer", 0)], banks=None)[0], "103 0 1")

    def test_a_code_out_of_range(self):
        src = GAME.replace("KEYDOWN(41)", "KEYDOWN(X + 100)")
        r = run(src, [("timer", 0)])
        self.assertTrue(r.alerts and r.alerts[0].startswith("Runtime error: a key code is 0 to 127 at line 22"),
                        r.alerts)
        for code, refused in (("X + 27", False), ("X + 28", True), ("X - 101", True)):  # 127, 128, -1
            with self.subTest(code=code):
                r = run(GAME.replace("KEYDOWN(41)", f"KEYDOWN({code})"), [("timer", 0)])
                self.assertEqual(bool([a for a in r.alerts if "a key code is 0 to 127" in a]), refused, r.alerts)

    def test_compile_errors(self):
        with self.assertRaises(SourceError) as ctx:
            check_source(GAME.replace("KEYDOWN(41)", 'KEYDOWN("a")'))
        self.assertIn("KEYDOWN expects an INTEGER key code", str(ctx.exception))
        with self.assertRaises(SourceError) as ctx:
            check_source(GAME.replace("KEYDOWN(41)", "KEYDOWN(1, 2)"))
        self.assertIn("KEYDOWN expects 1 arguments", str(ctx.exception))

    def test_only_programs_that_use_it_carry_it(self):
        self.assertIn("PB_KEYDOWN equ 1", generate(check_source(GAME)))
        self.assertIn("PB_KEYDOWN equ 0", generate(check_source('MESSAGE "x"\nEND\n')))


if __name__ == "__main__":
    unittest.main()
