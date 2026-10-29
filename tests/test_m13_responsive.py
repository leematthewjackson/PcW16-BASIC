"""M13 corrective, responsiveness (docs/M13-RESPONSIVENESS.md): the owner's
retest of the corrective builds (artifacts/m13-corrective) found JUMPER
pausing about once a second and TIMEPRB / TIMEPR4 getting 89-90 of 160 and
27-28 of 40 events, with CLOCKTICKS stepping back twice in 2 s.

Cause: XAnne's 1/256 s byte (#F9) is not in step with its seconds register.
CLOCKTICKS (seconds * 16 + #F9 \\ 16) stepped back where #F9 wrapped and
jumped where the seconds changed; Rosanne's timer deadlines (seconds + #F9,
PCW045.SYS block 6 #6958) past the wrap waited for the seconds register, so
the timer stopped for up to a second, once a second.

The simulator models that clock (rtc_phase) and Rosanne's timer service on
it (rosanne_timers); free_run lets a program run on with no script. The
owner's builds are rebuilt byte for byte with legacy_timing, so the figures
below are those of the executables the owner ran.
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run
from pbas import check_source
from pbas.layout import build_dialog
from pbas.prg import build
from toolchain import requires_files, requires_pasmo

import test_m13_jumper as jz

ROOT = Path(__file__).resolve().parents[1]
CORRECTIVE = ROOT / "artifacts" / "m13-corrective"  # what the owner retested
XANNE = 115  # a phase of #F9 (1/256 s) at which the owner's TIMEPRB figures come out
RATE = z80sim.CLOCK_RATE


def probe(name, button, legacy=False, phase=XANNE, seconds=13, **sim):
    """developer-tests/<name>.pbas: press button, run on for *seconds* of model time
    with Rosanne's timers on a clock of that phase; (rows of R$, cpu)."""
    path = ROOT / "developer-tests" / f"{name}.pbas"
    src = path.read_text(encoding="utf-8")
    program = check_source(src, path=path)
    buttons = {o.text: ("click", o.number) for o in build_dialog(program, program.windows[0], False).objects
               if o.kind == "BUTTON"}
    r = guarded_run(src, events=[buttons[button]], path=path, max_steps=3_000_000_000,
                    build_options={"runtime_sections": "all", "legacy_timing": legacy},
                    rtc_phase=phase, rosanne_timers=True, free_run=seconds, **sim)
    assert r.violations == [], r.violations[:5]
    at = next(g.start for g in r.regions if g.name == "R$")
    return [bytes(r.cpu.mem[at + 61 * i:at + 61 * i + 61]).split(b"\0")[0].decode() for i in range(6)], r.cpu


def gaps(cpu, skip=1.0):
    """The times between TIMER handler runs (s), after the first *skip* s of them."""
    t = [x for x in cpu.tick_times if x > cpu.tick_times[0] + skip * RATE]
    return [(b - a) / RATE for a, b in zip(t, t[1:])]


def p1(rows):
    """(events, clock, steps, frames, dropped) from P1's two report lines."""
    m = re.match(r"P1 idle 10 s: (\d+) events \(\d+ wanted\), clock (\d+)/16 s$", rows[0])
    n = re.match(r"steps of 2/16 s: (\d+) \(80 wanted\), frames (\d+), dropped (\d+)$", rows[1])
    assert m and n, rows
    return tuple(int(g) for g in m.groups() + n.groups())


@requires_pasmo
class LegacyTimingTests(unittest.TestCase):
    @requires_files(CORRECTIVE / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14
    def test_legacy_timing_rebuilds_the_corrective_builds_byte_for_byte(self):
        cases = [("examples/jumper.pbas", "JUMPER", "all"), ("examples/sprited.pbas", "SPRITED", "all"),
                 ("developer-tests/sprprb.pbas", "SPRPRB", "all"), ("developer-tests/sprprb.pbas", "SPRPRN", ()),
                 ("examples/tutorial/t3_hop.pbas", "T3HOP", ())]
        with tempfile.TemporaryDirectory() as tmp:
            for src, name, banks in cases:
                with self.subTest(name):
                    prg = Path(tmp) / f"{name}.PRG"
                    build(ROOT / src, Path(tmp) / f"{name}.asm", prg, runtime_sections=banks, legacy_timing=True,
                          legacy_file_safety=True, legacy_real_rounding=True, legacy_tasks_stop=True)  # M14: as accepted
                    self.assertEqual(prg.read_bytes(), (CORRECTIVE / name).with_suffix(".PRG").read_bytes())
                    build(ROOT / src, Path(tmp) / f"{name}.asm", prg, runtime_sections=banks)
                    self.assertNotEqual(prg.read_bytes(), (CORRECTIVE / name).with_suffix(".PRG").read_bytes())

    def test_only_ticks_timers_poll(self):
        def asm(timer):
            src = f'WINDOW W, "T", LARGE\nBUTTON "Q", Q\nTIMER T, {timer}\nSUB T\nEND SUB\nSUB Q\n    EXIT\nEND SUB\nEND\n'
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "t.pbas"
                path.write_text(src)
                build(path, Path(tmp) / "t.asm", Path(tmp) / "t.prg")
                text = (Path(tmp) / "t.asm").read_text()
            return {k: re.search(rf"^PB_{k} equ (\d)$", text, re.M).group(1) for k in ("TICKPOLL", "CKCAL")}
        self.assertEqual(asm("EVERY 2 TICKS"), {"TICKPOLL": "1", "CKCAL": "1"})
        self.assertEqual(asm("EVERY 240 TICKS"), {"TICKPOLL": "1", "CKCAL": "1"})
        self.assertEqual(asm("EVERY 241 TICKS"), {"TICKPOLL": "0", "CKCAL": "0"})  # os_set_timer
        self.assertEqual(asm("EVERY 2"), {"TICKPOLL": "0", "CKCAL": "0"})  # seconds: as accepted


@requires_pasmo
class ClockTests(unittest.TestCase):
    def test_c1_the_owners_clock_stepped_back(self):
        rows, _ = probe("timeprb", "Clock", legacy=True, seconds=None)
        self.assertRegex(rows[0], r"^C1 clock in 2 s: (2[89]|3[0-2]) changes")
        self.assertRegex(rows[1], r"^largest step 1[67]/16 s, went back 2 times$")  # as in XAnne

    def test_c1_clockticks_counts_from_the_seconds_change(self):
        for phase in (0, XANNE, 200):
            with self.subTest(phase=phase):
                rows, _ = probe("timeprb", "Clock", phase=phase, seconds=None)
                self.assertEqual(rows[:2], ["C1 clock in 2 s: 32 changes (32 wanted)",
                                            "largest step 1/16 s, went back 0 times"])


@requires_pasmo
class TimerTests(unittest.TestCase):
    def test_p1_the_owners_builds_on_xannes_clock(self):
        rows, cpu = probe("timeprb", "Idle", legacy=True)
        self.assertEqual(p1(rows), (91, 160, 80, 50, 0))  # owner: 89-90 events, 80 steps, 50 frames
        self.assertGreater(max(gaps(cpu)), 0.45)
        rows, cpu = probe("timepr4", "Idle", legacy=True)
        self.assertEqual(p1(rows), (31, 160, 80, 30, 0))  # owner: 27-28, 70-74, 25-27 (phase about 1/2)
        rows, _ = probe("timepr4", "Idle", legacy=True, phase=140)
        self.assertEqual(p1(rows), (21, 160, 60, 20, 20))  # past 1/2: steps dropped at the cap
        rows, _ = probe("timeprb", "Idle", legacy=True, phase=0)
        self.assertEqual(p1(rows), (161, 160, 80, 80, 0))  # a clock in step: as asked

    def test_p1_the_loop_runs_ticks_on_any_clock(self):
        for name, events, frames, gap in (("timeprb", 160, 80, 1), ("timepr4", 40, 40, 4)):
            for phase in (0, XANNE, 200):
                with self.subTest(name=name, phase=phase):
                    rows, cpu = probe(name, "Idle", phase=phase)
                    e, clock, steps, f, dropped = p1(rows)
                    self.assertIn(e, (events, events + 1))
                    self.assertIn(clock, (160, 161))
                    self.assertEqual((steps, f, dropped), (80, frames, 0))
                    self.assertEqual(rows[2], f"longest gap between events {gap}/16 s ({gap} wanted)")
                    self.assertLess(max(gaps(cpu)), gap / 16 + 0.01)

    def test_p2_load_keeps_the_steps(self):
        rows, _ = probe("timeprb", "Load")
        self.assertRegex(rows[0], r"^P2 load 10 s: 16[01] events")
        self.assertEqual(rows[1], "steps of 2/16 s: 80 (80 wanted), frames 80, dropped 0")

    def test_r1_timer_off_and_on(self):
        rows, _ = probe("timeprb", "Restart", seconds=8)
        m = re.match(r"R1 5 s: (\d+) events after (\d+) restarts$", rows[1])
        self.assertTrue(m, rows)
        self.assertIn(int(m.group(2)), (4, 5))
        self.assertGreaterEqual(int(m.group(1)), 76)  # 80 sixteenths, less a tick at each restart

    def test_timer_script_entries_on_a_polled_timer(self):
        # ("timer", 0) runs the handler once more; one a "wait" already caused
        # counts; while a wait passes the loop polls and the handler runs at
        # each interval (2, 4 and 6 sixteenths)
        src = ('DIM N AS INTEGER\nWINDOW W, "T", LARGE\nBUTTON "Q", Q\nTIMER T, EVERY 2 TICKS\n'
               'SUB T\n    N = N + 1\nEND SUB\nSUB Q\n    MESSAGE STR$(N)\n    EXIT\nEND SUB\nEND\n')
        program = check_source(src)
        q = ("click", next(o.number for o in build_dialog(program, program.windows[0], False).objects
                           if o.kind == "BUTTON"))
        for events, want in (([("timer", 0)] * 5, "5"), ([("wait", 2), ("timer", 0)] * 5, "5"),
                             ([("wait", 6), ("timer", 0)], "3"), ([("timer", 0, "stale")], "0")):
            with self.subTest(events=events):
                r = guarded_run(src, events=events + [q], clock_by_steps=False)
                self.assertEqual(r.alerts, [want])

    def test_callbacks_collapse_under_load_but_the_steps_do_not(self):
        # The contract of EVERY n TICKS (owner RT7: TIMEPRB 142-154 callbacks
        # of 160, longest gap 2/16 s, yet 80 of 80 steps): a run that ends
        # past the next interval loses that callback (no catch-up), and
        # lib/pace.pbas still does every step the clock says. Here the
        # handler's work is made to take nearly an interval (a machine 25
        # times slower than the model's usual).
        from unittest import mock
        with mock.patch.object(z80sim, "CLOCK_RATE", 80_000):
            rows, _ = probe("timeprb", "Load")
            pace = [int(x) for x in re.findall(r"\d+", rows[1])]
            gap = int(re.search(r"gap between events (\d+)/16", rows[2]).group(1))
        events = int(re.search(r"(\d+) events", rows[0]).group(1))
        self.assertLess(events, 150)  # callbacks collapsed
        self.assertEqual(gap, 2)  # by one interval at a time, never more
        self.assertGreaterEqual(pace[2], 79)  # steps: what the clock says (80 in 10 s)
        self.assertEqual(pace[-1], 0)  # none dropped at the cap

    def test_a_handler_that_falls_behind_is_not_caught_up(self):
        # the first run takes 6/16 s (it waits on the clock); the run that
        # fell due meanwhile comes once, at its end, and the next 2/16 s
        # after that: not three runs at once to catch up
        src = ('DIM N AS INTEGER\nDIM C AS INTEGER\nWINDOW W, "T", LARGE\nBUTTON "Q", Q\nTIMER T, EVERY 2 TICKS\n'
               'SUB T\n    N = N + 1\n    IF N = 1 THEN\n        C = CLOCKTICKS\n'
               '        WHILE (CLOCKTICKS - C + 960) MOD 960 < 6\n        WEND\n    END IF\nEND SUB\n'
               'SUB Q\n    MESSAGE STR$(N)\n    EXIT\nEND SUB\nEND\n')
        program = check_source(src)
        q = ("click", next(o.number for o in build_dialog(program, program.windows[0], False).objects
                           if o.kind == "BUTTON"))
        r = guarded_run(src, events=[("timer", 0), ("wait", 5), q], clock_by_steps=True)
        self.assertEqual(r.alerts, ["4"])  # the long run, the overdue one, then 2/16 and 4/16 s on


@requires_pasmo
class JumperTests(unittest.TestCase):
    def run_right(self, legacy, phase, seconds=10):
        disk = z80sim.Disk(files={(jz.F, n): d for n, d in jz.ASSETS.items()})
        r = guarded_run(jz.SRC, events=[jz.B["New game"], ("hold", jz.RIGHT, True)], disk=disk, path=jz.PATH,
                        max_steps=3_000_000_000, build_options={"runtime_sections": "all", "legacy_timing": legacy},
                        rtc_phase=phase, rosanne_timers=True, free_run=seconds)
        self.assertEqual(r.violations, [])
        return r

    def test_the_owners_jumper_paused_once_a_second(self):
        r = self.run_right(True, XANNE)
        g = gaps(r.cpu)
        self.assertGreaterEqual(sum(x > 0.4 for x in g), 7)
        self.assertLess(len(r.cpu.tick_times), 60)

    def test_jumper_runs_without_pauses(self):
        for phase in (0, XANNE, 200):
            with self.subTest(phase=phase):
                r = self.run_right(False, phase)
                g = gaps(r.cpu)
                self.assertLess(max(g), 0.2)
                self.assertGreaterEqual(len(g) / 8, 7.5)  # 8 frames a second asked for
                # the hero ran as the rules model says for the steps done
                steps = jz.word(r, "PACETOTAL")
                self.assertEqual(jz.word(r, "HX"), jz.play([{"RIGHT"}] * steps).x)


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------- M13 RT6: no input at all (owner)
RT6 = ROOT / "artifacts" / "m13-responsive"  # what the owner ran in RT6 (070a09d)


def jumper(events, phase=XANNE, seconds=None, **sim):
    """JUMPER (built from this source) on XAnne's clock with Rosanne's
    timers; with *seconds*, it runs on with no input until that time."""
    disk = z80sim.Disk(files={(jz.F, n): d for n, d in jz.ASSETS.items()})
    r = guarded_run(jz.SRC, events=events, disk=disk, path=jz.PATH, max_steps=3_000_000_000,
                    build_options={"runtime_sections": "all"}, rtc_phase=phase, rosanne_timers=True,
                    free_run=seconds, **sim)
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r


TITLE = [("wait", 24)]  # 1.5 s on the title screen first, as a player takes


@requires_pasmo
class IdleTests(unittest.TestCase):
    """The owner's RT6 (070a09d): the event loop compared the clock before
    waiting, but waited with os_wait_event, which does not return without
    an event; with no input the TIMER never ran."""

    @requires_files(RT6 / "MANIFEST.md", what="the builds the owner ran in XAnne at earlier milestones")  # M14

    def test_1_ten_seconds_with_no_input(self):
        path = ROOT / "developer-tests" / "timeprb.pbas"
        program = check_source(path.read_text(encoding="utf-8"), path=path)
        idle = next(("click", o.number) for o in build_dialog(program, program.windows[0], False).objects
                    if o.text == "Idle")
        for phase in (0, XANNE):
            with self.subTest(phase=phase):
                # the RT6 executable: the handler ran once, then the loop waited for ever
                old = z80sim.run((RT6 / "TIMEPRB.PRG").read_bytes(), events=[idle], max_steps=3_000_000_000,
                                 rtc_phase=phase, rosanne_timers=True, free_run=13)
                self.assertLessEqual(len(old.tick_times), 1)
                self.assertTrue(any(fn == 2 for fn, _ in old.os_log))
                rows, cpu = probe("timeprb", "Idle", phase=phase)
                self.assertEqual(p1(rows)[2:], (80, 80, 0))
                self.assertGreaterEqual(len(cpu.tick_times), 160)
                self.assertEqual([fn for fn, _ in cpu.os_log if fn == 2], [])  # never os_wait_event

    def test_2_a_tap_of_space_then_nothing(self):
        r = jumper(TITLE + [jz.B["New game"], ("key", 32)], seconds=5)
        steps = jz.word(r, "PACETOTAL")
        self.assertGreaterEqual(steps, 26)
        s = jz.state_of(r)
        # the jump went up, came down and landed, with no input after the tap
        self.assertEqual(s, jz.model_state(jz.play([{jz.SPACE}] + [set()] * (steps - 1))))
        self.assertEqual((s["y"], s["vy"]), (180, 0))
        jumped = [t for t in r.cpu.tick_times]
        self.assertLess(max((b - a) / RATE for a, b in zip(jumped[8:], jumped[9:])), 0.2)

    def test_3_standing_still_the_beetles_and_coins_go_on(self):
        r = jumper(TITLE + [jz.B["New game"]], seconds=6)
        steps = jz.word(r, "PACETOTAL")
        s = jz.state_of(r)
        self.assertGreaterEqual(steps, 30)
        self.assertEqual(s, jz.model_state(jz.play([set()] * steps)))
        self.assertEqual(s["x"], 12)  # the hero where he started
        start = jz.state_of(jumper(TITLE + [jz.B["New game"]]))
        self.assertNotEqual(s["bugs"], start["bugs"])  # the beetles walked, the coins turned
        self.assertNotEqual(jz.word(r, "TICKS") // 4, jz.word(jumper(TITLE + [jz.B["New game"]]), "TICKS") // 4)

    def test_4_the_minute_and_the_hour_turn_while_idle(self):
        # the model clock starts 2 s before 13:00:00: the seconds, the minute
        # and the hour all turn in the first counted second
        rows, cpu = probe("timeprb", "Idle", clock_start=12 * 3600 + 59 * 60 + 58)
        self.assertEqual(p1(rows)[1:], (160, 80, 80, 0))
        self.assertEqual(rows[2], "longest gap between events 1/16 s (1 wanted)")

    def test_5_timer_off_on_and_pause_resume_with_no_input(self):
        rows, _ = probe("timeprb", "Restart", seconds=8)
        self.assertRegex(rows[1], r"^R1 5 s: (7[6-9]|8[01]) events after [45] restarts$")
        p = ("key", ord("p"))
        r = jumper(TITLE + [jz.B["New game"], ("wait", 16), p, ("wait", 32), p], seconds=7)
        s = jz.state_of(r)
        self.assertEqual(s["state"], "playing")
        # steps since the resume (PaceStart) only: at most 7 - 4.5 s of them (the repaints
        # of pausing and resuming take model time too); the 2 s paused are not caught up
        steps = jz.word(r, "PACETOTAL")
        self.assertTrue(8 <= steps <= 21, steps)
        t = [x / RATE for x in r.cpu.tick_times]
        self.assertLess(max(b - a for a, b in zip(t[-12:], t[-11:])), 0.2)  # running on after the resume

    def test_6_timer_with_drawing_and_a_stream_of_keys(self):
        # Right held and its key repeating (KEYS events) all the time: the
        # handler (which draws) still runs every 1/8 s
        ev = TITLE + [jz.B["New game"], ("hold", jz.RIGHT, True)]
        for _ in range(60):
            ev += [("key", 227), ("wait", 1)]
        r = jumper(ev, clock_by_steps=True)
        t = [x / RATE for x in r.cpu.tick_times]
        t = [x for x in t if x > t[0] + 2]
        self.assertGreaterEqual(len(t), 20)
        self.assertLess(max(b - a for a, b in zip(t, t[1:])), 0.2)
        self.assertEqual(jz.word(r, "HX"), jz.play([{jz.RIGHT}] * jz.word(r, "PACETOTAL")).x)


class EventCallTests(unittest.TestCase):
    """7: the simulator's event calls against ROSAN283 and the static reading."""

    def cpu(self, events, **opts):
        c = z80sim.CPU(bytes(16))
        c.events = list(events)
        c.h = c.l = 0xFF
        for k, v in opts.items():
            setattr(c, k, v)
        return c

    def test_os_wait_event_never_returns_z_for_time_or_keys(self):
        c = self.cpu([("wait", 8), ("hold", "RIGHT", True), ("key", 32)], clock_by_steps=0)
        c._wait_event(blocking=True)
        self.assertFalse(c.f & z80sim.FLAG_Z)  # the key, after the half second and the hold
        self.assertEqual(c.clock_waited, z80sim.CLOCK_RATE // 2)
        self.assertEqual(c.ix, z80sim.EVENT_RECORD)

    def test_os_wait_event_with_nothing_to_come_does_not_return(self):
        c = self.cpu([("wait", 4)], clock_by_steps=0)
        with self.assertRaises(z80sim._SimIdle):
            c._wait_event(blocking=True)

    def test_os_wait_event_wakes_for_a_rosanne_timer(self):
        c = self.cpu([("wait", 32)], clock_by_steps=0, rosanne_timers=True)
        c.timers[0] = (1, 2)
        c._rosanne_arm(0, 2)
        c._wait_event(blocking=True)
        self.assertFalse(c.f & z80sim.FLAG_Z)
        self.assertEqual(c.mem[z80sim.EVENT_RECORD] & 1, 1)  # a timer event
        # within its 2/16 s (the model waits 1/256 s at a time: 7,812 of its 2,000,000 a second)
        self.assertLessEqual(c.clock_waited, z80sim.CLOCK_RATE * 2 // 16 + z80sim.CLOCK_RATE // 256)

    def test_os_get_event_returns_z_while_time_passes(self):
        c = self.cpu([("wait", 1), ("key", 32)], clock_by_steps=0)
        zs = 0
        while True:
            c._wait_event(blocking=False)
            if not c.f & z80sim.FLAG_Z:
                break
            zs += 1
        self.assertIn(zs, (16, 17))  # 1/16 s, 1/256 s (7,812 model cycles) a call
        self.assertEqual(c.clock_waited, z80sim.CLOCK_RATE // 16)


class SimModelTests(unittest.TestCase):
    def test_rosanne_rearm_is_the_static_reading(self):
        # #6958: deadline ticks = (ticks now + interval * 16) AND #F0, the carry into the seconds
        cpu = z80sim.CPU(bytes(16))
        cpu.clock_by_steps = 0
        for phase, ticks_now, interval, want in ((0x37, 0x37, 1, (0, 0x40)), (0xF5, 0xF5, 1, (1, 0x00)),
                                                 (0x80, 0x80, 4, (0, 0xC0)), (0xE9, 0xE9, 4, (1, 0x20))):
            with self.subTest(phase=phase, interval=interval):
                cpu.rtc_phase = phase
                secs, ticks = cpu.rtc()
                self.assertEqual(ticks, ticks_now)
                cpu.timers[0] = (1, interval)
                cpu._rosanne_arm(0, interval)
                self.assertEqual(cpu.timer_deadline[0], (secs + want[0], want[1]))
