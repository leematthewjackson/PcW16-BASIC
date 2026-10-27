"""JUMPER (examples/jumper.pbas, M13 Stage H) on the simulator.

The game is driven as a player drives it: New game, then keys held and
released between timer ticks. Its state after each script (the hero's
place, speed and frame, the beetles, coins, score, lives, the game's
state) is compared with an independent model of the rules written here:
running, jumping, gravity, landing on platforms from above only, walking
off an edge, coins, beetles, lives, winning and losing. The canvas is
checked for trails: everywhere no sprite or coin is, it must be exactly
the scenery the game started with. Simulator evidence only: the speed in
XAnne and the feel of the controls are for the owner (docs/M13-ACCEPTANCE.md,
Session D).

M13 corrective: keys are held by name and reach KEYDOWN through the key
numbers Rosanne's keyboard interrupt gives them (z80sim.keystate_code: Left
99, Right 100, Up 101, as the owner's SPRPROBE showed); the M13 build used
the keypad's numbers and did not move in XAnne. The game steps by the clock
(lib/pace.pbas), so here only "wait" events move the model clock: each tick
of a script is 1/8 s of it, then the TIMER event. tests/test_m13_corrective.py
delivers the same play with the events XAnne gave (fewer, later, merged).
"""
from __future__ import annotations

import contextlib
import io
import random
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

PATH = ROOT / "examples" / "jumper.pbas"
SRC = PATH.read_text(encoding="utf-8")
F = "\\PCW\\FOLDER01"
CW, CH = 480, 220
LEFT, RIGHT, UP, SPACE = "LEFT", "RIGHT", "UP", "SPACE"
NAMES = ("JHERO.PBI", "JHEROM.PBI", "JBUG.PBI", "JBUGM.PBI", "JCOIN.PBI", "JCOINM.PBI")


def assets() -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="pbw16-jmp-") as tmp:
        with contextlib.redirect_stdout(io.StringIO()):
            assert pbimage.main(["build", str(ROOT / "examples" / "assets" / "ASSETS.txt"), tmp]) == 0
        return {n: (Path(tmp) / n).read_bytes() for n in NAMES}


ASSETS = assets()


def layout(src=SRC):
    program = check_source(src, path=PATH)
    lay = build_dialog(program, program.windows[0], True)
    return lay.canvas[1], lay.canvas[2], {o.text: ("click", o.number) for o in lay.objects if o.kind == "BUTTON"}


SX, SY, B = layout()


# ------------------------------------------------------------------ the model
class Model:
    """The rules of JUMPER, written from its description, not its code."""

    PLATS = [(40, 164, 90), (180, 128, 100), (330, 154, 110), (80, 90, 80), (240, 60, 90),
             (400, 100, 60), (0, 204, 480)]
    COINS = [(80, 152), (226, 116), (380, 142), (116, 78), (281, 48), (426, 88), (300, 192)]

    def __init__(self, coins=None, bugs=None):
        self.coins = list(coins or self.COINS)
        self.coin_on = [True] * len(self.coins)
        self.bugs = [dict(b) for b in (bugs or [dict(lo=180, hi=264, y=116, v=2), dict(lo=160, hi=460, y=192, v=3)])]
        for b in self.bugs:
            b["x"], b["f"] = b["lo"], 0
        self.ticks, self.score, self.lives, self.left, self.state = 0, 0, 3, len(self.coins), "playing"
        self.jump_held = False
        self.respawn()

    def respawn(self):
        self.x, self.y, self.vy, self.facing, self.ground, self.safe, self.f = 12, 180, 0, 1, True, 16, 0

    def landing(self, x, y0, y1):
        tops = [py for px, py, pw in self.PLATS if x + 12 > px and x + 4 < px + pw and y0 <= py <= y1]
        return min(tops) if tops else -1

    @staticmethod
    def meets(ax, ay, aw, ah, bx, by, bw, bh):
        return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah

    def tick(self, keys):
        if self.state != "playing":
            return
        self.ticks += 1
        d = (RIGHT in keys) - (LEFT in keys)
        if d:
            self.facing = d
        self.x = max(0, min(CW - 16, self.x + 4 * d))
        up = SPACE in keys or UP in keys
        if up and self.ground and not self.jump_held:
            self.vy, self.ground = -13, False
        self.jump_held = up
        if self.ground and self.landing(self.x, self.y + 24, self.y + 24) < 0:
            self.ground, self.vy = False, 0
        if not self.ground:
            y = self.y + self.vy
            if self.vy > 0:
                top = self.landing(self.x, self.y + 24, y + 24)
                if top >= 0:
                    y, self.vy, self.ground = top - 24, 0, True
            if y < 0:
                y, self.vy = 0, 0
            self.y = y
            if not self.ground:
                self.vy = min(self.vy + 2, 10)
        f = 3 if not self.ground else (1 + self.ticks % 2 if d else 0)
        self.f = f + (4 if self.facing < 0 else 0)
        for b in self.bugs:
            x = b["x"] + b["v"]
            if x < b["lo"] or x > b["hi"]:
                b["v"] = -b["v"]
                x = b["x"] + b["v"]
            b["x"], b["f"] = x, (self.ticks // 2) % 2
        for i, (cx, cy) in enumerate(self.coins):
            if self.coin_on[i] and self.meets(self.x, self.y, 16, 24, cx, cy, 8, 8):
                self.coin_on[i] = False
                self.score += 10
                self.left -= 1
        if self.left == 0:
            self.state = "won"
            self.score += 10 * self.lives
            return
        if self.safe > 0:
            self.safe -= 1
            return
        for b in self.bugs:
            if self.meets(b["x"], b["y"], 16, 12, self.x + 3, self.y + 3, 10, 21):
                self.lives -= 1
                if self.lives == 0:
                    self.state = "over"
                else:
                    self.respawn()
                return


def script_events(script):
    """[set of keys per tick] -> the event script after New game."""
    ev, held = [B["New game"]], set()
    for keys in script:
        for k in sorted(held - keys):
            ev.append(("hold", k, False))
        for k in sorted(keys - held):
            ev.append(("hold", k, True))
        held = set(keys)
        ev += [("wait", 2), ("timer", 0)]
    return ev


def run(events, src=SRC, files=None, quit=True, legacy_timing=False, **sim):
    disk = z80sim.Disk(files={(F, n): d for n, d in (ASSETS if files is None else files).items()})
    sim.setdefault("clock_by_steps", False)  # the clock moves by "wait" events only
    r = guarded_run(src, events=events + ([B["Quit"]] if quit else []), disk=disk, path=PATH,
                    max_steps=1_500_000_000,
                    build_options={"runtime_sections": "all", "legacy_timing": legacy_timing}, **sim)
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return r


def word(r, name, index=None):
    region = next(g for g in r.regions if g.name == name)
    at = region.start + (0 if index is None else 2 * (index - 1))
    v = r.cpu.mem[at] | r.cpu.mem[at + 1] << 8
    return v - 65536 if v >= 32768 else v


STATES = {0: "title", 1: "playing", 2: "paused", 3: "won", 4: "over"}


def state_of(r):
    return dict(x=word(r, "HX"), y=word(r, "HY"), vy=word(r, "VY"), f=word(r, "SPRF", 1),
                bugs=[(word(r, "SPRX", 2), word(r, "SPRF", 2)), (word(r, "SPRX", 3), word(r, "SPRF", 3))],
                score=word(r, "SCORE"), lives=word(r, "LIVES"), left=word(r, "LEFT"),
                state=STATES[word(r, "STATE")])


def model_state(m):
    return dict(x=m.x, y=m.y, vy=m.vy, f=m.f, bugs=[(b["x"], b["f"]) for b in m.bugs], score=m.score,
                lives=m.lives, left=m.left, state=m.state)


def play(script, **model_args):
    m = Model(**model_args)
    for keys in script:
        m.tick(keys)
    return m


def page(r):
    return r.cpu.canvas_pixels(SX, SY, CW, CH)


@requires_pasmo
class ScreenTests(unittest.TestCase):
    def test_title(self):
        r = run([])
        self.assertEqual(string_var(r, "STATUS$"), "JUMPER: New game to play")
        self.assertTrue(r.cpu.exited)
        # M13 responsiveness: the TIMER of 2/16 s is the event loop's own (no
        # os_set_timer, docs/M13-RESPONSIVENESS.md); it runs every 2/16 s
        self.assertEqual([fn for fn, _ in r.cpu.os_log if fn in (8, 9)], [])
        rec = r.symbols["gui_timer_rec"]
        self.assertEqual(r.cpu.mem[rec + 4] | r.cpu.mem[rec + 5] << 8, 2)
        t = run([("wait", 2), ("timer", 0)] * 3).cpu.tick_times
        self.assertEqual([b - a for a, b in zip(t, t[1:])], [z80sim.CLOCK_RATE // 8] * 2)

    def test_a_missing_picture_is_named(self):
        files = dict(ASSETS)
        del files["JBUGM.PBI"]
        r = run([B["New game"], ("timer", 0)], files=files)
        self.assertEqual(string_var(r, "MISSING$"), "JBUGM.PBI")
        self.assertEqual(string_var(r, "STATUS$"), "JUMPER: New game to play")  # New game did nothing
        files["JBUGM.PBI"] = ASSETS["JCOIN.PBI"]  # the wrong picture: refused by its size
        self.assertEqual(string_var(run([], files=files), "MISSING$"), "JBUGM.PBI")

    def test_no_trails(self):
        start = page(run(script_events([]), quit=False))
        script = [{RIGHT}] * 12 + [{RIGHT, SPACE}] + [{RIGHT}] * 10 + [set()] * 6
        r = run(script_events(script), quit=False)
        now = page(r)
        m = play(script)
        covered = set()

        def cover(x, y, w, h):
            for j in range(max(0, y), min(CH, y + h)):
                for i in range(max(0, x), min(CW, x + w)):
                    covered.add((i, j))
        cover(12, 180, 16, 24)  # where the sprites were at the start ...
        cover(180, 116, 16, 12)
        cover(160, 192, 16, 12)
        cover(m.x, m.y, 16, 24)  # ... and are now
        for b in m.bugs:
            cover(b["x"], b["y"], 16, 12)
        for cx, cy in m.COINS:
            cover(cx, cy, 8, 8)
        diffs = [(i, j) for j in range(CH) for i in range(CW) if (i, j) not in covered and now[j][i] != start[j][i]]
        self.assertEqual(diffs[:10], [])
        # and the hero is drawn where the model says: a black pixel of his outline
        self.assertIn("#", "".join(row[m.x:m.x + 16] for row in now[m.y:m.y + 24]))


@requires_pasmo
class RulesTests(unittest.TestCase):
    def check(self, script, **kw):
        r = run(script_events(script), **kw)
        self.assertEqual(state_of(r), model_state(play(script)))
        return r

    def test_running_and_frames(self):
        for n in (1, 2, 5):
            with self.subTest(ticks=n):
                self.check([{RIGHT}] * n)
        self.check([{RIGHT}] * 3 + [{LEFT}] * 2)
        self.check([{RIGHT, LEFT}] * 3)  # both: no movement
        self.check([{LEFT}] * 6)  # held against the left edge

    def test_a_jump_rises_slows_falls_and_lands(self):
        for n in (1, 3, 7, 8, 14, 20):
            with self.subTest(ticks=n):
                self.check([{SPACE}] + [set()] * (n - 1))
        m = play([{SPACE}] + [set()] * 6)
        self.assertEqual(m.y, 180 - 13 - 11 - 9 - 7 - 5 - 3 - 1)  # the top of the jump: 49 pixels up
        self.check([{SPACE}] * 20)  # held: one jump, not another on landing
        self.check([{UP}] + [set()] * 3 + [{UP}])  # Up jumps too; not again in the air

    def test_landing_on_a_platform_and_walking_off_it(self):
        script = [{RIGHT}] * 4 + [{RIGHT, SPACE}] + [{RIGHT}] * 6 + [set()] * 6
        m = play(script)
        self.assertEqual((m.y, m.ground), (164 - 24, True))  # on the first platform
        self.check(script)
        script += [{RIGHT}] * 20 + [set()] * 8  # off its right end, down to the ground
        m = play(script)
        self.assertEqual((m.y, m.ground), (180, True))
        self.check(script)

    def test_platforms_are_passed_from_below(self):
        script = [{RIGHT}] * 6 + [{SPACE}] + [set()] * 10  # under the first platform: up through it
        m = play(script)
        self.assertEqual(m.y, 140)  # landed on it from above
        self.check(script)

    def test_coins_and_beetles(self):
        script = [{RIGHT}] * 130  # along the ground: a coin, then the beetle coming back
        m = play(script)
        self.assertLess(m.lives, 3)
        self.assertEqual(m.score, 10)
        self.check(script)

    def test_a_long_game(self):
        rng = random.Random(1613)
        script, keys = [], set()
        for _ in range(160):
            if rng.random() < 0.3:
                keys = set(rng.sample([LEFT, RIGHT, SPACE, UP], rng.randint(0, 2)))
            script.append(keys)
        self.check(script)


@requires_pasmo
class GameTests(unittest.TestCase):
    EASY = SRC
    for i, (x, y) in enumerate([(40, 196), (60, 196), (80, 196), (100, 196), (120, 196), (140, 196), (160, 196)], 1):
        EASY = EASY.replace(f"    CALL CoinAt({i}, ", f"    CALL CoinAt({i}, {x}, {y})\n    ' was CoinAt({i}, ", 1)
    EASY = EASY.replace("CALL BugAt(2, 160, 460, 192, 3)", "CALL BugAt(2, 400, 460, 192, 3)")

    def test_winning(self):
        script = [{RIGHT}] * 40
        coins = [(40, 196), (60, 196), (80, 196), (100, 196), (120, 196), (140, 196), (160, 196)]
        bugs = [dict(lo=180, hi=264, y=116, v=2), dict(lo=400, hi=460, y=192, v=3)]
        m = play(script, coins=coins, bugs=bugs)
        self.assertEqual(m.state, "won")
        r = run(script_events(script), src=self.EASY)
        self.assertEqual(state_of(r)["state"], "won")
        self.assertEqual(state_of(r)["score"], m.score)
        self.assertEqual(string_var(r, "STATUS$"), f"Score {m.score} Lives 3 Left 0")

    def test_losing(self):
        src = SRC.replace("CALL BugAt(2, 160, 460, 192, 3)", "CALL BugAt(2, 0, 100, 192, 3)")
        script = [set()] * 200  # standing still at the start, in the beetle's walk: hit three times
        m = play(script, bugs=[dict(lo=180, hi=264, y=116, v=2), dict(lo=0, hi=100, y=192, v=3)])
        self.assertEqual(m.state, "over")
        r = run(script_events(script), src=src)
        self.assertEqual(state_of(r), model_state(m))

    def test_pause(self):
        script = [{RIGHT}] * 3
        r = run(script_events(script) + [("key", ord("p"))]
                + [("hold", RIGHT, True), ("wait", 2), ("timer", 0), ("wait", 2), ("timer", 0)])
        s = state_of(r)
        self.assertEqual((s["state"], s["x"]), ("paused", 24))
        self.assertEqual(string_var(r, "STATUS$"), "Paused: P to go on")
        r = run(script_events(script) + [("key", ord("p")), ("wait", 40), ("key", ord("P")), ("hold", RIGHT, True),
                                         ("wait", 2), ("timer", 0)])
        self.assertEqual(state_of(r)["x"], 28)  # one step: the 2.5 s paused are not caught up

    def test_new_game_restarts(self):
        r = run(script_events([{RIGHT}] * 20) + [B["New game"]])
        s = state_of(r)
        self.assertEqual((s["x"], s["score"], s["lives"], s["left"], s["state"]), (12, 0, 3, 7, "playing"))

    def test_stop_quits_cleanly(self):
        r = run(script_events([{RIGHT}] * 2) + [("key", 254)], quit=False)
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.mem[r.symbols["rt_timer_run"]], 0)  # the TIMER stopped at the exit


if __name__ == "__main__":
    unittest.main()
