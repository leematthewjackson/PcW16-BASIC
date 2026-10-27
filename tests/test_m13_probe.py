"""M13: SPRPROBE (developer-tests/sprprb.pbas) on the simulator.

The probe checks its masked and part drawing itself, pixel by pixel with
POINT; here those checks must find nothing wrong, with and without the
runtime bank, so that a "wrong" in XAnne is XAnne's evidence, not the
probe's mistake. Its key monitor must show the codes of the keys the
event script holds. The tick count needs real seconds and is for XAnne
only (docs/M13-ACCEPTANCE.md, Session A).
"""
from __future__ import annotations

import unittest
from pathlib import Path

from memguard import guarded_run
from pbas import check_source
from pbas.layout import build_dialog
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "developer-tests" / "sprprb.pbas"


def results(r, prog):
    """R$(1..6) as strings."""
    region = next(g for g in r.regions if g.name == "R$")
    cap = prog.variables["R$"].capacity
    out = []
    for at in range(region.start, region.start + region.size, cap):
        out.append(bytes(r.cpu.mem[at:at + cap]).split(b"\0", 1)[0].decode("latin-1"))
    return out


def run(events_for, banks):
    src = PROBE.read_text(encoding="utf-8")
    prog = check_source(src, path=PROBE)
    lay = build_dialog(prog, prog.windows[0], False)
    b = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
    r = guarded_run(src, path=PROBE, events=events_for(b), max_steps=900_000_000,
                    build_options={"runtime_sections": banks} if banks else None)
    assert r.violations == [], r.violations[:5]
    assert not [a for a in r.alerts if a.startswith("Runtime error")], r.alerts
    return results(r, prog)


@requires_pasmo
class SprProbeTests(unittest.TestCase):
    def test_mask_checks_pass(self):
        for banks in ("all", None):
            with self.subTest(banks=banks):
                res = run(lambda b: [("click", b["Mask"])], banks)
                self.assertTrue(res[0].startswith("M1 ") and res[0].endswith(": 0 wrong"), res)
                self.assertTrue(res[1].startswith("M2 ") and res[1].endswith(": 0 wrong"), res)
                self.assertTrue(res[2].startswith("M3 ") and res[2].endswith(": 0 wrong"), res)

    def test_a_wrong_mask_rule_is_caught(self):
        # The probe's own check is not vacuous: the same comparison with the
        # mask's meaning reversed must report differences.
        src = PROBE.read_text(encoding="utf-8").replace(
            "IF POINT(MX + I, MY + J) = 1 THEN", "IF POINT(MX + I, MY + J) = 0 THEN")
        tmp = PROBE.with_name("sprprb_mut.pbas")
        tmp.write_text(src, encoding="utf-8")
        try:
            prog = check_source(src, path=tmp)
            lay = build_dialog(prog, prog.windows[0], False)
            b = {o.text: o.number for o in lay.objects if o.kind == "BUTTON"}
            r = guarded_run(src, path=tmp, events=[("click", b["Mask"])], max_steps=900_000_000,
                            build_options={"runtime_sections": "all"})
            res = results(r, prog)
            self.assertFalse([a for a in r.alerts if a.startswith("Runtime error")], r.alerts)
        finally:
            tmp.unlink()
        self.assertRegex(res[0], r": [1-9][0-9]* wrong, first at ")
        self.assertTrue(res[1].endswith(": 0 wrong"), res)  # M2 has no mask
        self.assertRegex(res[2], r": [1-9][0-9]* wrong, first at ")

    def test_keys_show_the_held_codes(self):
        res = run(lambda b: [("click", b["Keys"]), ("hold", "LEFT", True), ("hold", "SPACE", True),
                             ("timer", 0), ("timer", 0)], "all")
        self.assertEqual(res[2], "down: 41 99")  # as the owner's XAnne run showed
        res = run(lambda b: [("click", b["Keys"]), ("timer", 0)], "all")
        self.assertEqual(res[2], "down:")

    def test_ticks_and_speed_run_cleanly(self):
        # Their figures are XAnne's; here they must run without an error and
        # say what they measure.
        res = run(lambda b: [("click", b["Ticks"])] + [("timer", 0)] * 6, "all")
        self.assertTrue(res[0].startswith("T1 counting ticks"), res)
        res = run(lambda b: [("click", b["Speed"])], "all")
        for k, line in enumerate(res[:4], 1):
            self.assertRegex(line, rf"^S{k} .*: [0-9]+ ms \([0-9]+ in 3 s\)$")


if __name__ == "__main__":
    unittest.main()
