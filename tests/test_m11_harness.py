"""M11 Stage A: the test harness's own checks.

The memory checker (tests/memguard.py) finds the region of every write with a
table built once (``region_table``) instead of searching every region. These
tests show that the table gives the same region as the search at every
address, for real programs, and that the write observer still reports each
kind of violation (R1 outside storage, R1 in the #8000 window, R2 into a
string object that is not the active destination).

The simulator's ``step`` chooses each opcode's handler from a table
(tests/z80sim.py ``_build_dispatch``) instead of an if-chain. LockstepTests
run real programs on it and on the if-chain kept in tests/z80ref.py, and
compare a hash of every register after every instruction and the whole final
state (memory, owned blocks, files, alerts, drawing, OS calls).
"""
from __future__ import annotations

import copy
import random
import unittest
from pathlib import Path

import z80sim
from memguard import GuardedRun, Region, guarded_run, region_table, write_observer
from z80ref import ReferenceCPU
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]

STRINGS = """\
DIM A$ AS STRING * 10
DIM B$ AS STRING * 20
DIM N(5) AS INTEGER
A$ = "abc"
B$ = A$ + "def"
N(3) = LEN(B$)
END
"""

RECORDS = """\
TYPE Person
    Id AS INTEGER
    Name AS STRING * 12
    Town AS STRING * 8
END TYPE
DIM P(3) AS Person
DIM Q AS Person
P(2).Name = "Ann"
P(2).Town = "Bolton"
Q = P(2)
END
"""


class FakeCPU:
    def __init__(self):
        self.mem = bytearray(0x10000)
        self.q2 = 0
        self.owned = set()


@requires_pasmo
class RegionTableTests(unittest.TestCase):
    def check_same_as_search(self, run):
        table = region_table(run.regions)
        for addr in range(0x10000):
            self.assertIs(table[addr], next((r for r in run.regions if addr in r), None), hex(addr))

    def test_a_small_program(self):
        run = guarded_run(STRINGS)
        self.assertEqual(run.violations, [])
        self.check_same_as_search(run)

    def test_records_with_fields_inside_them(self):
        run = guarded_run(RECORDS)
        self.assertEqual(run.violations, [])
        # STRING fields lie inside their record's region and come first
        self.assertTrue(any(hasattr(r, "record") for r in run.regions))
        self.check_same_as_search(run)

    def test_contacts3(self):
        path = ROOT / "examples" / "contacts3.pbas"
        run = guarded_run(path.read_text(encoding="utf-8"), events=[], path=path, disk=z80sim.Disk(),
                          build_options={"legacy_file_safety": True})  # M14 (KI-100): as accepted
        self.assertEqual(run.violations, [])
        self.check_same_as_search(run)


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.run = GuardedRun(cpu=None, symbols={"rt_dst_end": 0x6000}, regions=[
            Region("S$", 0x5000, 4, True), Region("N", 0x5010, 2, False)])
        self.cpu = FakeCPU()
        self.write = write_observer(self.run)

    def set_dst_end(self, value):
        self.cpu.mem[0x6000], self.cpu.mem[0x6001] = value & 0xFF, value >> 8

    def test_allowed_writes(self):
        self.write(self.cpu, 0x5011, 1)
        self.set_dst_end(0x5003)
        self.write(self.cpu, 0x5000, 0x41)
        self.cpu.q2, self.cpu.owned = 0x90, {0x90}
        self.write(self.cpu, 0x8123, 0)
        self.assertEqual(self.run.violations, [])

    def test_outside_storage(self):
        self.write(self.cpu, 0x5012, 7)
        self.assertEqual(self.run.violations, ["R1: write 07h to 5012h outside allocated storage"])

    def test_string_object_not_the_destination(self):
        self.set_dst_end(0x5011)
        self.write(self.cpu, 0x5002, 0x42)
        self.assertEqual(len(self.run.violations), 1)
        self.assertTrue(self.run.violations[0].startswith("R2: write 42h to 5002h in S$"))

    def test_window_without_an_owned_block(self):
        self.cpu.q2 = 0x91
        self.write(self.cpu, 0x8000, 3)
        self.assertEqual(self.run.violations,
                         ["R1: write 03h to 8000h in the #8000 window (block 91h mapped)"])


class Traced:
    """Records each executed opcode (with its prefix) and a running hash of the
    registers after every instruction."""

    def __init__(self, *args, **kwargs):
        self.trace = 0
        self.seen = set()
        super().__init__(*args, **kwargs)

    def step(self):
        pc = self.pc
        op = self.mem[pc]
        self.seen.add((op, self.mem[(pc + 1) & 0xFFFF]) if op in (0xCB, 0xDD, 0xED, 0xFD) else op)
        super().step()
        self.trace = hash((self.trace, self.pc, self.a, self.f, self.b, self.c, self.d, self.e,
                           self.h, self.l, self.sp, self.ix, self.iy))


NewCPU = type("NewCPU", (Traced, z80sim.CPU), {})
RefCPU = type("RefCPU", (Traced, ReferenceCPU), {})


def traced_run(cls, source, **kw):
    saved = z80sim.CPU
    z80sim.CPU = cls  # z80sim.run builds its CPU from the module name
    try:
        r = guarded_run(source, **kw)
    finally:
        z80sim.CPU = saved
    c = r.cpu
    state = dict(violations=list(r.violations))
    if c is not None:
        state.update(trace=c.trace, steps=c.steps, mem=bytes(c.mem), alerts=list(c.alerts),
                     texts=list(c.texts), draw=list(c.draw_log), os_log=list(c.os_log),
                     exited=c.exited, idle=getattr(c, "idle", False), q2=c.q2,
                     files=dict(c.disk.files), owned={k: bytes(v) for k, v in c.owned.items()})
    return state, (c.seen if c is not None else set())


def lockstep_cases():
    import test_m10_contacts as tc
    import test_m10_mdedit2 as tm
    import test_m9_programs as tp
    import test_m14_probe as probe
    import test_m14_real as real
    import m14_sample_data
    gfx = tp.source("developer-tests/gfxprobe.pbas")
    o = tp.objects(gfx)
    _, sx, sy, _, _, _ = o["canvas"]
    contacts = ROOT / "examples" / "contacts3.pbas"
    mdedit2 = ROOT / "examples" / "mdedit2.pbas"
    F = "\\PCW\\FOLDER01"
    return {
        "dbprobe": dict(source=(ROOT / "developer-tests" / "dbprobe.pbas").read_text(encoding="utf-8"),
                        events=[], disk=z80sim.Disk()),
        "m7_edges": dict(source=(ROOT / "developer-tests" / "m7_edges.pbas").read_text(encoding="utf-8"),
                         events=[], disk=z80sim.Disk()),
        "bankprobe": dict(source=(ROOT / "developer-tests" / "bankprobe.pbas").read_text(encoding="utf-8"),
                          events=[], disk=z80sim.Disk(),
                          build_options=dict(code_banks="always", code_bank_limit=400)),
        "gfxprobe": dict(source=gfx, max_steps=50_000_000, events=[
            ("click", o["Shapes"]), ("click", o["Scroll"]), ("click", o["Alert"]),
            ("key", 65, 1), ("key", 0xE0), ("objevent", o["Quit"], 9),
            ("mdown", sx + 10, sy + 10), ("mmove", sx + 20, sy + 15), ("mup", sx + 21, sy + 16),
            ("click", o["Speed"]), ("click", o["Quit"])]),
        "contacts3": dict(source=contacts.read_text(encoding="utf-8"), path=contacts,
                          disk=z80sim.Disk(files={(F, "CONTACTS.PDB"): tc.DATA}), max_steps=tc.STEPS,
                          build_options={"legacy_file_safety": True},  # M14 (KI-100): as accepted
                          events=[("click", tc.b("MAIN", "Sort")), ("click", tc.b("MAIN", "Find...")),
                                  ("edit", tc.b("FINDER", "FINDTEXT$"), "ann"),
                                  ("click", tc.b("FINDER", "In names")), tc.SAVE, tc.QUIT]),
        # M14: the corrected file-safety and REAL code (M14-DEFECT-REGISTER F1-F5) on both cores
        "m14prb": dict(source=probe.SRC, path=probe.PATH, events=probe.EVENTS,
                       disk=z80sim.Disk(files={(F, "M14S.PDB"): m14_sample_data.unterminated()}),
                       build_options={"runtime_sections": "all"}),
        "m14real": dict(source=real.source("-", real.near_ties("-", 16)[:40]), disk=z80sim.Disk()),
        "mdedit2": dict(source=tm.SRC, path=mdedit2, max_steps=tm.STEPS,
                        disk=z80sim.Disk(files={(F, "EDTEST.MD"): tm.DOC}),
                        events=[("key", tm.RIGHT)] * 2 + tm.shift(tm.RIGHT, 6) + [tm.COPY]
                        + [("key", tm.DOWN)] * 2 + [tm.PASTE] + tm.keys("ab") + [tm.UNDO, tm.WRAP,
                           ("key", tm.END_), ("key", tm.BS), tm.SAVE, tm.QUIT]),
    }


@requires_pasmo
class LockstepTests(unittest.TestCase):
    def test_programs_run_identically_on_the_if_chain(self):
        seen = set()
        for name, kw in lockstep_cases().items():
            with self.subTest(program=name):
                kw = dict(kw)
                source = kw.pop("source")
                disk = kw.pop("disk", None)
                new, seen_new = traced_run(NewCPU, source, disk=copy.deepcopy(disk), **kw)
                ref, seen_ref = traced_run(RefCPU, source, disk=copy.deepcopy(disk), **kw)
                self.assertEqual(new["violations"], [], name)
                self.assertIn("trace", new, name)
                for key in ref:
                    self.assertEqual(new.get(key), ref[key], f"{name}: {key} differs")
                self.assertEqual(seen_new, seen_ref)
                seen |= seen_new
        # what real programs never execute is covered by RandomOpcodeTests
        names = z80sim.CPU.dispatch_names()
        used = {names[op if isinstance(op, int) else op[0]] for op in seen}
        self.assertLessEqual(set(names) - used, {"_x_halt", "_x_unsupported", "_x_ccf", "_x_nop",
                                                 "_x_ld_a_bc", "_x_ld_bc_a", "_x_jr", "_x_fd"})

    def test_the_table_follows_the_if_chain(self):
        # every opcode the chain rejected is still rejected, with its message
        cpu = z80sim.CPU(bytes(0x200))
        names = z80sim.CPU.dispatch_names()
        for op in range(256):
            if names[op] == "_x_unsupported":
                cpu.mem[0x4000] = op
                cpu.pc = 0x4000
                with self.assertRaisesRegex(z80sim.SimError, f"unsupported opcode {op:02X}h at PC=4000h"):
                    cpu.step()
                ref = ReferenceCPU(bytes(0x200))
                ref.mem[0x4000] = op
                ref.pc = 0x4000
                with self.assertRaisesRegex(z80sim.SimError, f"unsupported opcode {op:02X}h at PC=4000h"):
                    ref.step()


class RandomOpcodeTests(unittest.TestCase):
    """Every opcode 0..255 (and, through the prefixes, their second bytes) from
    random registers and memory: one instruction on the table and on the
    if-chain must leave the same registers, memory and outcome."""

    REGS = ("a", "f", "b", "c", "d", "e", "h", "l", "sp", "ix", "iy", "pc", "steps")

    def one(self, cls, mem, regs):
        cpu = cls(bytes(0x10))
        cpu.mem[:] = mem
        for name, value in regs.items():
            setattr(cpu, name, value)
        try:
            cpu.step()
            outcome = None
        except Exception as exc:  # noqa: BLE001 - the outcome is compared
            outcome = (type(exc).__name__, str(exc))
        return outcome, {n: getattr(cpu, n) for n in self.REGS}, bytes(cpu.mem), list(cpu.alerts)

    def test_each_opcode(self):
        rng = random.Random(1611)
        for op in range(256):
            for trial in range(12):
                mem = bytearray(rng.randbytes(0x10000))
                pc = 0xFFFF if trial < 2 else rng.randrange(0x4000, 0x7F00)  # 2 at the wrap
                mem[pc] = op
                regs = {n: rng.randrange(256) for n in ("a", "f", "b", "c", "d", "e", "h", "l")}
                regs.update(sp=rng.randrange(0x3000, 0x3F00), ix=rng.randrange(0x10000),
                            iy=rng.randrange(0x10000), pc=pc, steps=0)
                new = self.one(z80sim.CPU, mem, regs)
                ref = self.one(ReferenceCPU, mem, regs)
                self.assertEqual(new, ref, f"opcode {op:02X}h, registers {regs}")


if __name__ == "__main__":
    unittest.main()
