"""M10 Stage D2: the forms library (examples/lib/forms.pbas), INCLUDEd by a
test program and run on the simulator against a Python statement of its
documented rules. Simulator evidence only.
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

import z80sim
from pbas.prg import build
from toolchain import requires_pasmo

LIB = Path(__file__).resolve().parents[1] / "examples" / "lib" / "forms.pbas"


def phone_ok(v: str) -> bool:
    return v == "" or (all(c.isdigit() or c in " +()-" for c in v) and sum(c.isdigit() for c in v) >= 3)


def email_ok(v: str) -> bool:
    if v == "":
        return True
    if " " in v or v.count("@") != 1:
        return False
    name, rest = v.split("@")
    return len(name) >= 1 and "." in rest and rest.index(".") >= 1 and not rest.endswith(".")


def number_ok(v: str, low: int, high: int) -> bool:
    t = v.strip()
    return bool(re.fullmatch(r"-?[0-9]{1,5}", t)) and low <= int(t) <= high


def run(body: str):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "T.PBAS").write_text(f'INCLUDE "{LIB.as_posix()}"\nDIM V$ AS STRING\n' + body + "END\n",
                                     encoding="utf-8")
        build(root / "T.PBAS", root / "t.asm", root / "t.prg")
        return z80sim.run(root / "t.prg", max_steps=200_000_000)


@requires_pasmo
class FormsTests(unittest.TestCase):
    def check(self, sub: str, values, rule, extra=""):
        body = ""
        for v in values:
            body += f'V$ = "{v}"\nCALL FormStart\nCALL {sub}(V$, "F"{extra})\nIF FormOK() THEN\n    MESSAGE "ok"\nELSE\n    MESSAGE FormError$\nEND IF\n'
        alerts = run(body).alerts
        self.assertEqual(len(alerts), len(values))
        for v, a in zip(values, alerts):
            with self.subTest(sub=sub, value=v):
                self.assertEqual(a == "ok", rule(v), a)

    def test_phone(self):
        self.check("FormPhone", ["", "0161 555 0100", "+44 (0)161-555", "12", "1 2", "12a3", "123", "   "],
                   phone_ok)

    def test_email(self):
        self.check("FormEmail", ["", "a@b.c", "ann@example.org", "@b.c", "a@.c", "a@b.", "a@b", "a b@c.d",
                                 "a@b@c.d", "a@bc", "x.y@b.co"], email_ok)

    def test_number(self):
        self.check("FormNumber", ["", "5", "-5", " 42 ", "100", "101", "32767", "40000", "99999", "4x", "-",
                                  "000100"],
                   lambda v: number_ok(v, -10, 100), ", -10, 100")

    def test_required_and_first_error_wins(self):
        r = run('CALL FormStart\nCALL FormRequire("  ", "Name")\nCALL FormPhone("ab", "Phone")\n'
                'MESSAGE FormError$\nCALL FormStart\nCALL FormRequire("x", "Name")\nIF FormOK() THEN\n'
                '    MESSAGE "ok"\nEND IF\n')
        self.assertEqual(r.alerts, ["Name is required", "ok"])

    def test_helpers(self):
        r = run('MESSAGE "[" + PadRight$("abc", 5) + "][" + PadRight$("abcdef", 4) + "]"\n'
                'IF IsDigits("0123") THEN\n    MESSAGE "a"\nEND IF\nIF IsDigits("") THEN\n    MESSAGE "b"\nEND IF\n'
                'IF IsDigits("1 2") THEN\n    MESSAGE "c"\nEND IF\n')
        self.assertEqual(r.alerts, ["[abc  ][abcd]", "a"])


if __name__ == "__main__":
    unittest.main()
