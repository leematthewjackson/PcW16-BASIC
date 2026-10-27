"""M11 Stage B: runtime code in a code bank (pbas/rtbank.py).

* The IF evaluation the bank builder relies on assembles exactly what Pasmo
  assembles: the runtime's active lines alone give the same image as the
  whole runtime, for programs that use many sections.
* The same program built with and without a runtime bank behaves the same
  on the simulator with the memory checker: alerts, drawing, texts, files
  written and STRING variables, through scripted sessions of CONTACTS III and
  MDEDIT II (sorting, searching, adding, saving, editing, undo, the clipboard).
* The runtime bank frees resident bytes; the block at #8000 at the end is the
  one there at the start.
* The builder refuses what it cannot move safely (unknown sections, code that
  would fall through between bank and resident block, the address of moved
  code used as data, conditions it cannot evaluate).
"""
from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run
from pbas import rtbank
from pbas.errors import SourceError
from pbas.prg import RUNTIME_MARKER, build
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
F = "\\PCW\\FOLDER01"


def outcome(r) -> dict:
    """What a user or a file could observe of a run."""
    c = r.cpu
    strings = {}
    for region in r.regions:
        if region.is_string and not hasattr(region, "record"):
            data = bytes(c.mem[region.start:region.start + region.size])
            strings[region.name] = data.split(b"\0", 1)[0]
    files = {k: v for k, v in c.disk.files.items() if not k[1].endswith(".PRG")}
    return dict(violations=r.violations, alerts=list(c.alerts), texts=list(c.texts),
                draw=list(c.draw_log), files=files, exited=c.exited,
                idle=getattr(c, "idle", False), strings=strings)


@requires_pasmo
class ConditionTests(unittest.TestCase):
    def test_active_lines_assemble_like_pasmo(self):
        for src in ("examples/contacts3.pbas", "examples/mdedit2.pbas", "developer-tests/m7_edges.pbas",
                    "examples/uibench.pbas", "developer-tests/dbprobe.pbas"):
            with self.subTest(program=src), tempfile.TemporaryDirectory() as tmp:
                asm, prg = Path(tmp) / "p.asm", Path(tmp) / "p.prg"
                # M14 (KI-100): CONTACTS III's resident-only build fits with its accepted code only
                build(ROOT / src, asm, prg, legacy_file_safety=src.endswith("contacts3.pbas"))
                text = asm.read_text(encoding="utf-8")
                program, runtime = text.split(RUNTIME_MARKER, 1)
                values = rtbank.switches(program)
                lines = rtbank.classify(runtime, values)
                kept = [ln.text for ln in lines if ln.active and ln.kind != "directive"]
                flat = Path(tmp) / "flat.asm"
                flat.write_text(program + RUNTIME_MARKER + "\n" + "\n".join(kept) + "\n", encoding="utf-8")
                subprocess.run(["pasmo", "--bin", str(flat), str(Path(tmp) / "flat.bin")],
                               check=True, capture_output=True)
                image = prg.read_bytes()
                self.assertEqual((Path(tmp) / "flat.bin").read_bytes(), image[:len(image)] if
                                 len(image) <= 0x4000 else self.resident(asm, tmp))

    @staticmethod
    def resident(asm, tmp):
        out = Path(tmp) / "res.bin"
        subprocess.run(["pasmo", "--bin", str(asm), str(out)], check=True, capture_output=True)
        return out.read_bytes()

    def test_conditions(self):
        values = {"PB_A": 1, "PB_B": 0, "PB_N": 3}
        self.assertEqual(rtbank.evaluate("PB_A", values), 1)
        self.assertEqual(rtbank.evaluate("PB_B + PB_A", values), 1)
        self.assertEqual(rtbank.evaluate("PB_N >= 4", values), 0)
        self.assertEqual(rtbank.evaluate("PB_N >= 3", values), 1)
        self.assertEqual(rtbank.evaluate("DEFINED PB_A", values), 1)
        self.assertEqual(rtbank.evaluate("DEFINED PB_Z", values), 0)
        for bad in ("PB_A AND PB_B", "PB_Z", "PB_A - 1", "(PB_A)"):
            with self.assertRaises(SourceError, msg=bad):
                rtbank.evaluate(bad, values)


class RefusalTests(unittest.TestCase):
    VALUES = {"PB_DB": 1, "PB_X": 1}

    def split(self, runtime):
        return rtbank.split(runtime, self.VALUES, ("DB",), "    call rt_a\n", 2)

    def test_unknown_section(self):
        with self.assertRaisesRegex(SourceError, "TEXT cannot be moved"):
            rtbank.split("", self.VALUES, ("TEXT",), "", 2)

    def test_fall_through_into_the_bank(self):
        runtime = "rt_z:\n    ld a,1\n    IF PB_DB\nrt_a:\n    ld a,2\n    ret\n    ENDIF\n"
        with self.assertRaisesRegex(SourceError, "fall through into the runtime bank"):
            self.split(runtime)

    def test_fall_through_out_of_the_bank(self):
        runtime = "    IF PB_DB\nrt_a:\n    ld a,2\n    ENDIF\nrt_z:\n    ret\n"
        with self.assertRaisesRegex(SourceError, "fall through into resident code"):
            self.split(runtime)

    def test_address_of_moved_code_as_data(self):
        runtime = "    IF PB_DB\nrt_a:\n    ld hl,rt_b\n    ret\nrt_b:\n    ret\n    ENDIF\n"
        with self.assertRaisesRegex(SourceError, "address of rt_b as data"):
            self.split(runtime)

    def test_entered_by_jump_stays_resident(self):
        # a resident loop that jumps into DB code which jumps back into the
        # loop: the DB block must stay resident (it would leave the bank mapped)
        runtime = ("rt_loop:\n    call rt_a\n    jp rt_b\nrt_next:\n    jp rt_loop\n"
                   "    IF PB_DB\nrt_a:\n    ret\nrt_b:\n    jp rt_next\n    ENDIF\n")
        s = self.split(runtime)
        self.assertEqual(s.entries, ["rt_a"])
        self.assertEqual(s.moved_labels, {"rt_a"})

    def test_tail_call_and_error_exit_may_leave(self):
        runtime = ("rt_z:\n    call rt_a\n    call rt_put\n    ret\nrt_put:\n    ret\nrt_err_msg:\n    halt\n"
                   "    IF PB_DB\nrt_a:\n    jp z,rt_err_msg\n    jp rt_put\n    ENDIF\n")
        s = self.split(runtime)
        self.assertEqual(s.moved_labels, {"rt_a"})

    def test_an_unused_routine_after_data_moves_with_its_code(self):
        # found by PBAS_TEST_RUNTIME_BANKS=all: rt_file_save follows data and
        # a program without FILESAVE never names it
        runtime = ("rt_z:\n    call rt_a\n    ret\n    IF PB_DB\nrt_t:\n    db 1\nrt_unused:\n    ld a,1\n    ret\n"
                   "rt_a:\n    ret\n    ENDIF\n")
        s = self.split(runtime)
        self.assertEqual(s.moved_labels, {"rt_unused", "rt_a"})

    def test_a_good_split(self):
        runtime = ("rt_z:\n    call rt_a\n    ret\n    IF PB_DB\nrt_a:\n    call rt_b\n    ret\n"
                   "rt_b:\n    ld hl,rt_t\n    ret\nrt_t:\n    db 1,2\nrt_t_end:\n    ENDIF\n")
        s = self.split(runtime)
        self.assertEqual(s.entries, ["rt_a"], "rt_b is only called inside the bank")
        self.assertEqual([x.strip() for x in s.bank_lines if x.strip()],
                         ["rt_a:", "call rt_b", "ret", "rt_b:", "ld hl,rt_t", "ret"])
        self.assertIn("rt_t:\n    db 1,2\nrt_t_end:", s.resident)
        self.assertIn("rt_a:\n    call rt_rbc\n    db 2\n    dw 8003h", s.resident)


RESIDENT = """\
    org 4000h
    defs 256
start:
    ld hl,0A5C3h        ; A = A5, F = C3 (S, Z, C, and bit 6)
    push hl
    ld hl,{entry}
    ld (go),hl
    pop af
    ld hl,3333h
    ld de,4444h
    ld bc,5555h
    call veneer
    ld (o_hl),hl
    ld (o_de),de
    ld (o_bc),bc
    push af
    pop hl
    ld (o_af),hl
done:
    jp done
veneer:                 ; as pbas/rtbank.py writes one, with a chosen entry
    call rt_rbc
    db 1
go:
    dw 0
hop:                    ; resident code that calls the bank again (nesting)
    call veneer2
    ret
veneer2:
    call rt_rbc
    db 1
    dw 8003h
rt_code_list:
    db 0F0h,0
o_hl: defs 2
o_de: defs 2
o_bc: defs 2
o_af: defs 2
i_hl: defs 2
i_de: defs 2
i_bc: defs 2
i_af: defs 2
i_seen: defs 1
rt_rb_hl: defs 2
rt_rb_de: defs 2
rt_rb_go: defs 2
rt_rb_a: defs 1
"""

BANK = """\
    org 8000h
    db 'P','B',1
    jp echo
    jp twice
echo:
    ld (i_hl),hl
    ld (i_de),de
    ld (i_bc),bc
    push af
    pop hl
    ld (i_af),hl
    ld a,(8002h)
    ld (i_seen),a
    ld hl,7E81h         ; A = 7E, F = 81 (S, C)
    push hl
    pop af
    ld hl,0BEEFh
    ld de,0CAFEh
    ld bc,0D00Dh
    ret
twice:
    call hop            ; resident code, which calls echo through rt_rbc again
    ret
"""


@requires_pasmo
class FarCallTests(unittest.TestCase):
    """rt_rbc itself (runtime/runtime.z80.asm, IF DEFINED PB_RTBANK), on the
    simulator: registers and flags in both directions, the block at #8000
    put back, and a nested call through resident code."""

    @staticmethod
    def block() -> str:
        runtime = (ROOT / "runtime" / "runtime.z80.asm").read_text(encoding="utf-8")
        return runtime.split("    IF DEFINED PB_RTBANK\n", 1)[1].split("\n    ENDIF\n", 1)[0]

    def test_ix_and_iy_are_not_touched(self):
        code = [ln.split(";", 1)[0].lower() for ln in self.block().splitlines()]
        self.assertFalse([c for c in code if re.search(r"\bi[xy]\b", c)])

    def run_entry(self, entry: int):
        block = self.block()
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "r.asm").write_text(RESIDENT.format(entry=entry) + block + "\n", encoding="utf-8")
            subprocess.run(["pasmo", "--bin", str(t / "r.asm"), str(t / "r.bin"), str(t / "r.sym")],
                           check=True, capture_output=True)
            from pbas.codebanks import read_symbols
            syms = read_symbols(t / "r.sym")
            (t / "b.asm").write_text(BANK + "\n".join(f"{n} equ {v:05X}h" for n, v in syms.items()
                                                       if n.startswith(("i_", "hop"))) + "\n",
                                     encoding="utf-8")
            subprocess.run(["pasmo", "--bin", str(t / "b.asm"), str(t / "b.bin")], check=True, capture_output=True)
            cpu = z80sim.CPU((t / "r.bin").read_bytes())
            cpu.owned[0xF0] = bytearray((t / "b.bin").read_bytes().ljust(0x4000, b"\0"))
            before = cpu.q2
            for _ in range(10_000):
                cpu.step()
                if cpu.pc == syms["done"]:
                    break
            else:
                self.fail("did not finish")
            word = lambda name: cpu.mem[syms[name]] | (cpu.mem[syms[name] + 1] << 8)
            return cpu, before, word

    def test_registers_and_flags_both_ways(self):
        cpu, before, word = self.run_entry(0x8003)
        self.assertEqual([word(n) for n in ("i_af", "i_hl", "i_de", "i_bc")],
                         [0xA5C3, 0x3333, 0x4444, 0x5555], "what the routine got")
        self.assertEqual([word(n) for n in ("o_af", "o_hl", "o_de", "o_bc")],
                         [0x7E81, 0xBEEF, 0xCAFE, 0xD00D], "what the caller got")
        self.assertEqual(word("i_seen") & 0xFF, 1,
                         "the routine ran with its bank at #8000")
        self.assertEqual(cpu.q2, before, "the block at #8000 is put back")
        self.assertEqual(cpu.q2_maps, [0xF0, before])
        self.assertEqual(cpu.sp, z80sim.STACK_TOP, "the stack is as before")

    def test_a_nested_call_through_resident_code(self):
        cpu, before, word = self.run_entry(0x8006)
        self.assertEqual(word("o_af"), 0x7E81)
        self.assertEqual(word("o_hl"), 0xBEEF)
        self.assertEqual(word("i_hl"), 0x3333, "registers reach the inner call unchanged")
        self.assertEqual(cpu.q2, before)
        self.assertEqual(cpu.q2_maps, [0xF0, 0xF0, 0xF0, before], "inner call: maps the bank, maps it back")
        self.assertEqual(cpu.sp, z80sim.STACK_TOP)


@requires_pasmo
class EquivalenceTests(unittest.TestCase):
    def both(self, path, **kw):
        source = path.read_text(encoding="utf-8")
        disk = kw.pop("files")
        # M14 (KI-100): CONTACTS III's resident-only build fits with its accepted file code only;
        # both builds use it, so that they compare like for like
        extra = {"legacy_file_safety": True} if path.name == "contacts3.pbas" else {}
        runs = []
        for options in (dict(extra), {"runtime_sections": "all", **extra}):
            d = z80sim.Disk(files={(F, n): v for n, v in disk.items()})
            r = guarded_run(source, path=path, disk=d, build_options=options, **kw)
            runs.append(r)
        return runs

    def test_contacts3_session(self):
        import test_m10_contacts as tc
        b = tc.b
        events = [("click", b("MAIN", "Sort")), ("click", b("MAIN", "Sort")),
                  ("click", b("MAIN", "Find...")), ("edit", b("FINDER", "FINDTEXT$"), "ann"),
                  ("click", b("FINDER", "In names")),
                  ("click", b("MAIN", "Add")), ("edit", b("EDITOR", "FNAME$"), "Zed Young"),
                  ("edit", b("EDITOR", "FPHONE$"), "01x"), ("click", b("EDITOR", "OK")),
                  ("edit", b("EDITOR", "FPHONE$"), "0161 222 3333"), ("click", b("EDITOR", "OK")),
                  tc.SAVE, tc.QUIT]
        plain, banked = self.both(ROOT / "examples" / "contacts3.pbas", files={"CONTACTS.PDB": tc.DATA},
                                  events=events, max_steps=tc.STEPS)
        self.assertEqual(plain.violations, [])
        self.assertIn("Phone: a bad character", plain.alerts)
        self.assertTrue(plain.cpu.exited)
        self.assertEqual(outcome(banked), outcome(plain))
        self.assertIsNotNone(banked.report.banked.runtime_sections)
        self.assertEqual(banked.cpu.q2, plain.cpu.q2, "the block at #8000 is put back")

    def test_contacts3_recovery_and_damage(self):
        import test_m10_contacts as tc
        damaged = (ROOT / "tests" / "fixtures" / "m10" / "DAMAGED.PDB").read_bytes()
        for files in ({"CONTACTS.PDB": damaged, "CONTACTS.BAK": tc.DATA}, {"CONTACTS.PDB": damaged},
                      {"CONTACTS.NEW": tc.DATA}):
            with self.subTest(files=sorted(files)):
                plain, banked = self.both(ROOT / "examples" / "contacts3.pbas", files=files,
                                          events=[tc.SAVE], max_steps=tc.STEPS, alert_answers=[1])
                self.assertEqual(outcome(banked), outcome(plain))

    def test_mdedit2_session(self):
        import test_m10_mdedit2 as tm
        events = ([("key", tm.RIGHT)] * 2 + tm.shift(tm.RIGHT, 6) + [tm.COPY]
                  + [("key", tm.DOWN)] * 2 + [tm.PASTE] + tm.keys("ab") + [tm.UNDO, tm.REDO]
                  + [tm.SELALL, tm.WRAP, ("key", tm.END_, 4), ("key", tm.BS), tm.WRAP, tm.SAVE, tm.QUIT])
        plain, banked = self.both(ROOT / "examples" / "mdedit2.pbas", files={"EDTEST.MD": tm.DOC},
                                  events=events, max_steps=tm.STEPS)
        self.assertEqual(plain.violations, [])
        self.assertTrue(plain.cpu.exited)
        self.assertEqual(outcome(banked), outcome(plain))

    def test_resident_bytes_freed(self):
        # measured: CONTACTS III 4,322 and MDEDIT II 2,845 bytes; the event-loop
        # helpers of CANVAS / MENUS / NUMBERS stay resident (enter by call,
        # leave by return: docs/M11-ARCHITECTURE.md §2.2 rule 7)
        for src, at_least in (("examples/contacts3.pbas", 4300), ("examples/mdedit2.pbas", 2800)):
            with self.subTest(program=src), tempfile.TemporaryDirectory() as tmp:
                t = Path(tmp)
                legacy = src.endswith("contacts3.pbas")  # M14 (KI-100): like for like, as accepted
                plain = build(ROOT / src, t / "a.asm", t / "a.prg", legacy_file_safety=legacy)
                banked = build(ROOT / src, t / "b.asm", t / "b.prg", runtime_sections="all",
                               legacy_file_safety=legacy)
                freed = plain.banked.resident_size - banked.banked.resident_size
                self.assertGreaterEqual(freed, at_least)
                self.assertTrue(re.search(r"runtime sections DB CANVAS", (t / "b.map").read_text()))


@requires_pasmo
class HeadroomTests(unittest.TestCase):
    """A program that no longer fits its resident block fits again with a
    runtime bank; the error says so (M11 Stage D4)."""

    def test_overflow_message_and_the_way_out(self):
        src = (ROOT / "examples" / "contacts3.pbas").read_text(encoding="utf-8")
        grown = src.replace("DIM ", "DIM Spare$(20) AS STRING * 100\nDIM ", 1)
        self.assertNotEqual(grown, src)
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "lib").mkdir()
            (t / "lib" / "forms.pbas").write_text(
                (ROOT / "examples" / "lib" / "forms.pbas").read_text(encoding="utf-8"), encoding="utf-8")
            (t / "grown.pbas").write_text(grown, encoding="utf-8")
            with self.assertRaises(SourceError) as caught:
                build(t / "grown.pbas", t / "a.asm", t / "a.prg")
            message = str(caught.exception)
            self.assertRegex(message, r"resident part is \d+ bytes, \d+ over the 16384-byte")
            self.assertIn("--runtime-banks all", message)
            report = build(t / "grown.pbas", t / "b.asm", t / "b.prg", runtime_sections="all")
            self.assertLess(report.banked.resident_size, 16384 - 2000)


if __name__ == "__main__":
    unittest.main()
