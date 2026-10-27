"""docs/M11-ACCEPTANCE.md as the owner will run it, on the simulator: every
expected status, alert and file in the sessions comes from these scripts.
"""
from __future__ import annotations

import difflib
import unittest

from memguard import string_var
from toolchain import requires_pasmo
import test_m11_contacts4 as t4
import test_m11_mdedit3 as t3
import test_m11_starter as ts
from test_m10_mdedit2 import COPY, CUT, MARK, PASTE, QUIT, REDO, SAVE, SELALL, UNDO, WRAP, keys, shift

R, L, U, D, H, E, PGDN = 0xE3, 0xE2, 0xE0, 0xE1, 0xE6, 0xE7, 0xE9
CTRL_HOME = ("key", H, 4)


@requires_pasmo
class Session1MdeditTests(unittest.TestCase):
    """M1-M11."""

    def test_session(self):
        x, y = t3.x_of, t3.CY + 4
        script = [
            ("M1", [], "L1/114 C1", "Opened EDTEST.MD"),
            ("M2", [("key", D), ("key", D), ("key", E), ("key", L), ("key", R), ("key", U), ("key", D),
                    ("key", H), ("key", E)], "L3/114 C81", ""),
            ("M3", [CTRL_HOME, ("mdown", x(3), y), ("mmove", x(6), y), ("mup", x(9), y)], "L1/114 C9 sel", ""),
            ("M4", [COPY, ("key", D), ("key", D), ("key", H), PASTE], "* L3/114 C7", "Pasted"),
            ("M5", [CTRL_HOME, MARK] + [("key", R)] * 6 + [COPY] + [("key", D)] * 3 + [("key", H), PASTE],
             "* L4/114 C7", "Pasted"),
            ("M6", [CTRL_HOME] + shift(R, 3) + shift(L, 1) + shift(D, 1), "* L2/114 C1 sel", ""),
            ("M7", [SELALL], "* L1/114 C1 sel", ""),
            ("M7b", [("key", R)], "* L1/114 C2", ""),
            ("M8", [UNDO, UNDO, REDO], "* L4/114 C1", "Redone"),
            ("M9", [WRAP], "* L4/114 C1 nowrap", "Redone"),
            ("M9b", [WRAP], "* L4/114 C1", "Redone"),
            ("M10", [CTRL_HOME, ("mdown", x(3), y), ("mup", x(9), y), CUT], "* L1/114 C3", "Cut"),
            ("M10b", [UNDO], "* L1/114 C9", "Undone"),
            ("M11", [CTRL_HOME] + keys("!") + [SAVE], "L1/114 C2", "Saved EDTEST.MD"),
        ]
        events = []
        for step, more, status, info in script:
            events += more
            r = t3.run(events)
            with self.subTest(step=step):
                self.assertEqual(string_var(r, "STATUS$"), status)
                self.assertEqual(string_var(r, "INFO$"), info)
                rows = t3.screen(r)
                if step == "M3":
                    self.assertEqual(rows[0][1], [2, 3, 4, 5, 6, 7], "MDEDIT highlighted")
                if step == "M6":
                    self.assertEqual(rows[0][1], list(range(29)), "line 1 and its end")
                if step == "M7":
                    self.assertTrue(all(row[1] for row in rows if row[0]))
                if step in ("M7b", "M11"):
                    self.assertFalse(any(row[1] for row in rows))
        r = t3.run(events + [QUIT])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.disk.file("EDTEST.BAK"), t3.DOC)
        self.assertIsNone(r.cpu.disk.file("MDEDIT3.TMP"))
        diff = [ln for ln in difflib.unified_diff(t3.DOC.decode().split("\r\n"),
                                                  r.cpu.disk.file("EDTEST.MD").decode().split("\r\n"),
                                                  lineterm="", n=0) if ln[:1] in "+-" and ln[:3] not in ("---", "+++")]
        self.assertEqual(diff, ["-# MDEDIT acceptance document", "+!# MDEDIT acceptance document",
                                "-" + t3.LINES[2], "+MDEDIT" + t3.LINES[2]])


@requires_pasmo
class Session2ContactsTests(unittest.TestCase):
    """C1-C10."""

    def test_session(self):
        script = [
            ("C1", [], [], "160/160 name", "Loaded", None),
            ("C2", [("key", D), ("key", D), ("key", PGDN), ("key", E), ("key", H),
                    ("mdown", t4.CX + 50, t4.CY + 5 * 16 + 3)], [], "160/160 name", "", None),
            ("C3a", [("click", "MAIN", "Sort")], [], "160/160 town", "", None),
            ("C3b", [("click", "MAIN", "Sort")], [], "160/160 number", "", None),
            ("C3c", [("click", "MAIN", "Sort")], [], "160/160 name", "", None),
            ("C4", [("click", "MAIN", "Find..."), ("edit", "FINDER", "FINDTEXT$", "ann"),
                    ("click", "FINDER", "In names")], [], "6/160 name found", "6 found", None),
            ("C4b", [("click", "MAIN", "Find..."), ("click", "FINDER", "Show all")], [], "160/160 name", "", None),
            ("C5", [("click", "MAIN", "Add"), ("edit", "EDITOR", "FNAME$", "Zed Young"),
                    ("edit", "EDITOR", "FPHONE$", "01x"), ("click", "EDITOR", "OK")], [],
             "160/160 name", "", "Phone: a bad character"),
            ("C5b", [("edit", "EDITOR", "FPHONE$", "0161 222 3333"), ("click", "EDITOR", "OK")], [],
             "* 161/161 name", "Changed", None),
            ("C6", [("click", "MAIN", "Delete")], [1], "* 161/161 name", "Changed", "Delete Zed Young?"),
            ("C6b", [("click", "MAIN", "Delete")], [0], "* 160/160 name", "Deleted", "Delete Zed Young?"),
            ("C7", [("click", "MAIN", "Sort"), ("click", "MAIN", "Sort"), ("click", "MAIN", "Find..."),
                    ("edit", "FINDER", "FINDTEXT$", "a"), ("click", "FINDER", "In names"),
                    ("click", "MAIN", "Delete")], [0], "* 114/159 number found", "Deleted", "Delete Nia Grant?"),
            ("C8", [t4.SAVE], [], "114/159 number found", "Saved", None),
        ]
        events, answers = [], []
        for step, more, ans, status, info, alert in script:
            events += more
            answers += ans
            r = t4.run(t4.PATH4, events, answers=answers)
            with self.subTest(step=step):
                self.assertEqual(string_var(r, "APPSTATUS$"), status)
                self.assertEqual(string_var(r, "INFO$"), info)
                self.assertFalse([a for a in r.alerts if a.startswith("Runtime error")])
                if alert:
                    self.assertEqual(r.alerts[-1], alert)
                if step == "C2":
                    self.assertEqual([inv for _, inv in t4.page(r)], [i == 5 for i in range(13)])
        r = t4.run(t4.PATH4, events + [t4.QUIT], answers=answers)
        self.assertTrue(r.cpu.exited)
        saved, bak = r.cpu.disk.file("CONTACTS.PDB"), r.cpu.disk.file("CONTACTS.BAK")
        self.assertEqual(bak, t4.DATA)
        self.assertIsNone(r.cpu.disk.file("CONTACTS.NEW"))
        files = {"CONTACTS.PDB": saved, "CONTACTS.BAK": bak}
        self.assertEqual(string_var(t4.run(t4.PATH4, [], files=files), "APPSTATUS$"), "159/159 name")   # C9
        self.assertEqual(string_var(t4.run(t4.PATH3, [], files=files), "STATUS$"), "159/159, by name")
        damaged = (t4.ROOT / "tests" / "fixtures" / "m11" / "DAMAGED.PDB").read_bytes()
        r = t4.run(t4.PATH4, [], files={"CONTACTS.PDB": damaged, "CONTACTS.BAK": bak})          # C10
        self.assertEqual(r.alerts, ["Unreadable: loaded CONTACTS.BAK: save it"])
        self.assertEqual(string_var(r, "APPSTATUS$"), "* 160/160 name")
        self.assertEqual(r.cpu.disk.file("CONTACTS.PDB"), damaged)


@requires_pasmo
class Session3StarterTests(unittest.TestCase):
    """T1-T8."""

    def test_session(self):
        o = ts.O
        script = [
            ("T1", [], "0 tasks", []),
            ("T2", ts.add("Buy milk") + ts.add("Post letter") + ts.add("Ring Ann"), "* 3 tasks", []),
            ("T3", [("key", U), ("key", 32)], "* 3 tasks", [("Post letter", True)]),
            ("T4", [("key", D), ("click", o["Done"])], "* 3 tasks", [("Ring Ann", True)]),
            ("T5", [("key", H), ("key", 0xE5)], "* 2 tasks", []),
            ("T6", [ts.SAVE], "2 tasks", []),
        ]
        events = []
        for step, more, status, _ in script:
            events += more
            r = ts.run(events)
            with self.subTest(step=step):
                self.assertEqual(string_var(r, "APPSTATUS$"), status)
        r = ts.run(events + [ts.QUIT])
        self.assertTrue(r.cpu.exited)
        saved = r.cpu.disk.file("TODO.PDB")
        self.assertEqual(ts.tasks(saved), [("Post letter", True), ("Ring Ann", True)])
        self.assertIsNone(r.cpu.disk.file("TODO.BAK"), "the first save has no previous file")
        r = ts.run([], files={"TODO.PDB": saved})                                   # T7
        self.assertEqual(string_var(r, "APPSTATUS$"), "2 tasks")
        r = ts.run(ts.add("Unsaved") + [ts.QUIT], files={"TODO.PDB": saved}, answers=[2])   # T8 Cancel
        self.assertFalse(r.cpu.exited)
        self.assertEqual(r.alerts, ["Unsaved changes"])
        r = ts.run(ts.add("Unsaved") + [ts.QUIT], files={"TODO.PDB": saved}, answers=[1])   # Discard
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.disk.file("TODO.PDB"), saved)


@requires_pasmo
class RetestR1MdeditTests(unittest.TestCase):
    """docs/M11-ACCEPTANCE.md R1 (the proportional-text retest)."""

    def test_r1(self):
        y = t3.CY + 4
        m_left = t3.x_of(3) + 2                    # on the left half of the M
        t_right = t3.x_of(9) - 2                   # on the right half of the T
        script = [
            ("R1.1", [], "L1/114 C1", "Opened EDTEST.MD"),
            ("R1.2", [("key", D), ("key", D), ("key", E)], "L3/114 C81", ""),
            ("R1.3", [CTRL_HOME, ("mdown", m_left, y), ("mmove", t3.x_of(6), y), ("mup", t_right, y)],
             "L1/114 C9 sel", ""),
            ("R1.4", [COPY, ("key", D), ("key", D), ("key", H), PASTE], "* L3/114 C7", "Pasted"),
            ("R1.5a", [CTRL_HOME] + shift(R, 3), "* L1/114 C4 sel", ""),
            ("R1.5b", shift(D, 1), "* L2/114 C1 sel", ""),
            ("R1.6a", [SELALL], "* L1/114 C1 sel", ""),
            ("R1.6b", [("key", R)], "* L1/114 C2", ""),
            ("R1.8", [("key", PGDN), ("key", PGDN), ("key", 0xE8), WRAP, WRAP], None, None),
            ("R1.9", [CTRL_HOME] + keys("Hello") + [SAVE], "L1/114 C6", "Saved EDTEST.MD"),
        ]
        events = []
        for step, more, status, info in script:
            events += more
            r = t3.run(events)
            rows = t3.screen(r)
            with self.subTest(step=step):
                if status is not None:
                    self.assertEqual(string_var(r, "STATUS$"), status)
                    self.assertEqual(string_var(r, "INFO$"), info)
                if step == "R1.1":
                    self.assertEqual(rows[0], ("# MDEDIT acceptance document", [], [0]))
                if step == "R1.3":
                    self.assertEqual(rows[0][1], [2, 3, 4, 5, 6, 7], "exactly MDEDIT")
                if step == "R1.5a":
                    self.assertEqual(rows[0][1], [0, 1, 2])
                if step == "R1.5b":
                    self.assertEqual(rows[0][1], list(range(29)), "line 1 and the block after its end")
                if step == "R1.6a":
                    self.assertTrue(all(row[1] for row in rows if row[0]))
                if step == "R1.6b":
                    self.assertFalse(any(row[1] for row in rows))
                if step == "R1.9":
                    self.assertEqual(rows[0][0], "Hello# MDEDIT acceptance document")
        r = t3.run(events + [QUIT])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.disk.file("EDTEST.BAK"), t3.DOC)
        self.assertIsNone(r.cpu.disk.file("MDEDIT3.TMP"))
        saved = r.cpu.disk.file("EDTEST.MD")
        diff = [ln for ln in difflib.unified_diff(t3.DOC.decode().split("\r\n"), saved.decode().split("\r\n"),
                                                  lineterm="", n=0) if ln[:1] in "+-" and ln[:3] not in ("---", "+++")]
        self.assertEqual(diff, ["-# MDEDIT acceptance document", "+Hello# MDEDIT acceptance document",
                                "-" + t3.LINES[2], "+MDEDIT" + t3.LINES[2]])
        r = t3.run([], files={"EDTEST.MD": saved})                                         # R1.10
        self.assertEqual(string_var(r, "STATUS$"), "L1/114 C1")
        self.assertEqual(t3.screen(r)[0][0], "Hello# MDEDIT acceptance document")


@requires_pasmo
class RetestR2ContactsTests(unittest.TestCase):
    """docs/M11-ACCEPTANCE.md R2."""

    def test_r2(self):
        wide = "W" * 30
        script = [
            ("R2.1", [], [], "160/160 name", "Loaded"),
            ("R2.2", [("key", D), ("key", D), ("mdown", t4.CX + 50, t4.CY + 5 * 16 + 3)], [], "160/160 name", ""),
            ("R2.3", [("click", "MAIN", "Sort")] * 3, [], "160/160 name", ""),
            ("R2.4", [("click", "MAIN", "Find..."), ("edit", "FINDER", "FINDTEXT$", "ann"),
                      ("click", "FINDER", "In names"), ("click", "MAIN", "Find..."),
                      ("click", "FINDER", "Show all")], [], "160/160 name", ""),
            ("R2.5", [("click", "MAIN", "Add"), ("edit", "EDITOR", "FNAME$", wide),
                      ("edit", "EDITOR", "FPHONE$", "0161 222 3333"), ("click", "EDITOR", "OK")], [],
             "* 161/161 name", "Changed"),
            ("R2.6", [("click", "MAIN", "Delete"), t4.SAVE], [0], "160/160 name", "Saved"),
        ]
        events, answers = [], []
        for step, more, ans, status, info in script:
            events += more
            answers += ans
            r = t4.run(t4.PATH4, events, answers=answers)
            with self.subTest(step=step):
                self.assertEqual(string_var(r, "APPSTATUS$"), status)
                self.assertEqual(string_var(r, "INFO$"), info)
                page = t4.page(r)
                self.assertEqual(sum(inv for _, inv in page), 1, "one row inverted")
                if step == "R2.2":
                    self.assertEqual([inv for _, inv in page], [i == 5 for i in range(13)])
                if step == "R2.5":
                    chosen = [cells for cells, inv in page if inv][0]
                    self.assertEqual(chosen[:2], ("W" * 21, "0161 222 3333"), "cut before the phone column")
        r = t4.run(t4.PATH4, events + [t4.QUIT], answers=answers)
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.disk.file("CONTACTS.BAK"), t4.DATA, "Save used once")
        saved = r.cpu.disk.file("CONTACTS.PDB")
        self.assertEqual(saved[8:12], bytes([160, 0, 162, 0]), "160 records, next identifier 162")
        self.assertEqual(t4.pdbcheck.check(saved, t4.sample.CONTACT_TYPE, 200)[0], 0)
        three = t4.run(t4.PATH3, [], files={"CONTACTS.PDB": saved})                       # R2.7
        self.assertEqual(string_var(three, "STATUS$"), "160/160, by name")


@requires_pasmo
class RetestR3StarterTests(unittest.TestCase):
    """docs/M11-ACCEPTANCE.md R3."""

    def test_r3(self):
        r = ts.run([])
        self.assertEqual(string_var(r, "APPSTATUS$"), "0 tasks")                         # R3.1
        ev = ts.add("Buy milk") + ts.add("Post letter")
        self.assertEqual(string_var(ts.run(ev), "APPSTATUS$"), "* 2 tasks")             # R3.2
        ev += [("key", U), ("key", 32), ts.SAVE]                                          # R3.3, R3.4
        r = ts.run(ev + [ts.QUIT])
        self.assertTrue(r.cpu.exited)
        saved = r.cpu.disk.file("TODO.PDB")
        self.assertEqual(ts.tasks(saved), [("Buy milk", True), ("Post letter", False)])
        self.assertEqual(string_var(ts.run([], files={"TODO.PDB": saved}), "APPSTATUS$"), "2 tasks")


if __name__ == "__main__":
    unittest.main()
