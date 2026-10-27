"""M8 owner probes (developer-tests/memprobe.asm, developer-tests/codeprobe.asm) on the model.

The owner runs these in XAnne; here they run on tests/z80sim.py so that a
mistake in the probe itself (a wrong register, a write outside an owned
block, a missing release) is found before the owner spends time on it.
This is engineering evidence about the PROBES, not about Rosanne.

CODEPROBE needs two things the flat simulator does not model, added here by
a subclass and kept out of z80sim.py (the compiler's model has no use for
them yet):

* the loader contract under test: only the FIRST 16K of the file is in
  memory at #4000 (os_run_program reads at most #4000 bytes: static
  analysis, docs/rosanne-research/reference/api-verification.md §4.3), and
  the name block lies over #4000;
* quarter 2 as a window: bios_setmem2 (#C2) / bios_getmem2 (#CE) map a
  block at #8000 (ROSAN283 BIOS table), and the file calls the probe makes
  (144 open, 145 close, 147 read, 156 set_ptr) on one file, the probe itself.
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
BIOS_SETMEM2, BIOS_GETMEM2 = 0x00C2, 0x00CE
OLD_Q2 = 0x8B  # whatever block the OS left at #8000


def build(name: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / f"{name}.prg"
        subprocess.run(["pasmo", "--bin", str(ROOT / "developer-tests" / f"{name}.asm"), str(out)],
                       check=True, capture_output=True)
        return out.read_bytes()


class ProbeCPU(z80sim.CPU):
    def __init__(self, file_bytes: bytes, name_block: bytes, set_ptr_works=True, open_fails=None):
        first = bytearray(file_bytes[:0x4000])
        first[: len(name_block)] = name_block  # the loader's name copy over #4000
        super().__init__(bytes(first))
        self.file = file_bytes
        self.q2 = OLD_Q2
        self.q2_junk = bytes([0x76]) * 0x4000  # halt: running unloaded code stops the run
        self.mem[0x8000:0xC000] = self.q2_junk
        self.pos = None  # read position; None = not open
        self.opened: list[tuple[str, str, int]] = []
        self.set_ptr_works = set_ptr_works
        self.open_fails = open_fails
        self.unowned_maps: list[int] = []
        self.os_from_q2: list[int] = []

    # quarter 2 window
    def _store_q2(self):
        if self.q2 in self.owned:
            self.owned[self.q2][:] = self.mem[0x8000:0xC000]

    def _map_q2(self, block: int):
        self._store_q2()
        self.q2 = block
        if block in self.owned:
            self.mem[0x8000:0xC000] = self.owned[block]
        else:
            if block != OLD_Q2:
                self.unowned_maps.append(block)
            self.mem[0x8000:0xC000] = self.q2_junk

    def _call(self, target: int) -> None:
        if target == BIOS_SETMEM2:
            self._map_q2(self.a)  # all flags and registers preserved
            return
        if target == BIOS_GETMEM2:
            self.a = self.q2
            return
        if target == z80sim.OS_DISPATCH and self.pc - 3 >= 0x8000:
            self.os_from_q2.append(self.a)
        super()._call(target)

    def _os_call(self) -> None:
        fn = self.a
        if fn == 144:
            name = self._low_string(self.hl, 33, "name")
            ext = self._low_string(self.de, 8, "ext")
            self.opened.append((name, ext, self.b))
            if self.b != 0:
                raise z80sim.SimError("CODEPROBE opened a file for write")
            if self.open_fails is not None:
                self.a, self.f = self.open_fails, z80sim.FLAG_C
                return
            self.pos, self.f = 0, 0
            return
        if fn == 145:
            self.pos, self.f = None, 0
            return
        if fn == 156:
            if not self.set_ptr_works:  # "C Error: #C8 No file open for read access"
                self.a, self.f = 0xC8, z80sim.FLAG_C
                return
            self.pos, self.f = self.b << 16 | self.de, 0
            return
        if fn == 147:
            n, block, off = self.b << 16 | self.de, self.c, self.hl & 0x3FFF
            if block not in self.owned or off + n > 0x4000:
                raise z80sim.SimError(f"os_read_file to {block:02X}:{off:04X} length {n}: not inside an owned block")
            data = self.file[self.pos:self.pos + n]
            self._store_q2()
            self.owned[block][off:off + len(data)] = data
            if self.q2 == block:
                self.mem[0x8000 + off:0x8000 + off + len(data)] = data
            self.pos += len(data)
            if len(data) < n:
                self.a, self.f = 0xA1, z80sim.FLAG_C
                left = n - len(data)
                self.b, self.d, self.e = left >> 16, (left >> 8) & 0xFF, left & 0xFF
                return
            self._poison("a")
            self.f = 0
            return
        if fn == z80sim.FN_OS_RELEASE_MEM:
            self._store_q2()
        super()._os_call()


def run_probe(cpu: ProbeCPU) -> ProbeCPU:
    try:
        while not cpu.exited:
            cpu.step()
            if cpu.steps > 2_000_000:
                raise z80sim.SimRunaway("probe runaway")
    except z80sim._SimStop:
        pass
    return cpu


@requires_pasmo
class MemProbeTests(unittest.TestCase):
    def setUp(self):
        self.prg = build("memprobe")

    def test_two_blocks_written_read_and_released(self):
        cpu = z80sim.run(self.prg)
        self.assertTrue(cpu.exited)
        # owner XAnne A1 gave W=BAD; the faithful os_copy_24bit model (PCW045
        # #5CB6: carry when a copy ends at the end of the owner's last block)
        # reproduces it: both #3FF0 copies on the second block report carry
        self.assertEqual(cpu.alerts, ["MEMPROBE F=20 A=01 G=02 90 91 O=0107 P=0107 0107 W=BAD R=20 E=20"])
        self.assertEqual([(e[0], e[1], e[2], e[3]) for e in cpu.copy_end_errors],
                         [(z80sim.FAKE_APP_BANK, cpu.copy_end_errors[0][1], 0x91, 0x3FF0),
                          (0x91, 0x3FF0, z80sim.FAKE_APP_BANK, cpu.copy_end_errors[1][3])])
        self.assertEqual(cpu.blocks_at_exit, [])

    def test_short_memory_skips_writes(self):
        for free, want in ((1, "G=01 90 00 O=0107 P=0107 FFFF W=SKIP"), (0, "G=00 00 00 O=0107 P=FFFF FFFF W=SKIP")):
            with self.subTest(free=free):
                cpu = z80sim.run(self.prg, free_blocks=free)
                self.assertIn(want, cpu.alerts[0])
                self.assertEqual(cpu.blocks_at_exit, [])

    def test_foreign_block_is_never_written(self):
        cpu = z80sim.run(self.prg, mem_owner={0x90: 0x0108})
        self.assertIn("P=0108 0107 W=SKIP", cpu.alerts[0])
        self.assertNotIn(z80sim.FN_OS_COPY_24BIT, [fn for fn, _ in cpu.os_log])


@requires_pasmo
class MemDiagTests(unittest.TestCase):
    """developer-tests/memdiag.asm: separates wrong writes, wrong reads, wrong addresses
    and the end-of-block carry (H-ROLL). Each wrong model must give a
    different alert from the faithful one."""
    FAITHFUL = "MEMDIAG G=90 91 P=N C N G4=C ok G5=N ok B=ok ok ok N=ok X=0010 Y=50 63"

    def setUp(self):
        self.prg = build("memdiag")

    def run_with(self, patch=None):
        cpu = z80sim.CPU(self.prg)
        if patch:
            patch(cpu)
        try:
            while not cpu.exited:
                cpu.step()
                if cpu.steps > 2_000_000:
                    raise z80sim.SimRunaway("memdiag")
        except z80sim._SimStop:
            pass
        self.assertEqual(cpu.blocks_at_exit, [])
        return cpu.alerts

    def test_faithful_model_gives_the_h_roll_signature(self):
        self.assertEqual(self.run_with(), [self.FAITHFUL])

    def test_other_causes_give_other_signatures(self):
        def no_end_carry(cpu):  # the old model: a copy may end at a block end
            nxt = cpu._next_block
            cpu._next_block = lambda b: nxt(b) or b
        def lost_writes(cpu):  # writes into owned blocks vanish
            w = cpu._write24
            cpu._write24 = lambda b, a, v: None if b in cpu.owned else w(b, a, v)
        def bad_reads(cpu):  # reads from owned blocks by the copy call are wrong
            r = cpu._read24
            orig = cpu._mem_call
            def mem_call(fn):
                if fn == z80sim.FN_OS_COPY_24BIT and cpu.c in cpu.owned:
                    cpu._read24 = lambda b, a: (r(b, a) ^ 0xFF) if b in cpu.owned else r(b, a)
                    try:
                        orig(fn)
                    finally:
                        cpu._read24 = r
                else:
                    orig(fn)
            cpu._mem_call = mem_call
        def shifted(cpu):  # every write lands one byte further on
            w = cpu._write24
            cpu._write24 = lambda b, a, v: w(b, (a + 1) & 0x3FFF, v) if b in cpu.owned else w(b, a, v)
        got = {name: self.run_with(p)[0] for name, p in
               (("no_end_carry", no_end_carry), ("lost_writes", lost_writes), ("bad_reads", bad_reads),
                ("shifted", shifted))}
        self.assertEqual(got["no_end_carry"], "MEMDIAG G=90 91 P=N N N G4=N ok G5=N ok B=ok ok ok N=ok X=0000 Y=50 63")
        self.assertIn("B=BAD BAD BAD", got["lost_writes"])
        self.assertIn("Y=A5 A5", got["lost_writes"])  # the model's fresh-block junk
        self.assertRegex(got["shifted"], r"Y=[0-9A-F]{2} 50$")  # "?? 50": one byte late
        self.assertIn("G5=N BAD", got["bad_reads"])
        self.assertIn("B=ok ok ok", got["bad_reads"])
        self.assertIn("N=BAD", got["shifted"])
        self.assertEqual(len(set(got.values()) | {self.FAITHFUL}), 5)

    def test_short_memory_and_foreign_blocks(self):
        for kw, want in (({"free_blocks": 1}, "MEMDIAG G=90 00 not run"), ({"free_blocks": 0}, "MEMDIAG G=00 00 not run"),
                         ({"mem_owner": {0x91: 0x0108}}, "MEMDIAG G=90 91 not run")):
            with self.subTest(kw=kw):
                cpu = z80sim.run(self.prg, **kw)
                self.assertTrue(cpu.alerts[0].startswith(want))
                self.assertEqual(cpu.blocks_at_exit, [])
                if "mem_owner" in kw:
                    self.assertNotIn(z80sim.FN_OS_COPY_24BIT, [fn for fn, _ in cpu.os_log])


@requires_pasmo
class MemProbe2Tests(unittest.TestCase):
    """developer-tests/memprobe2.asm: MEMPROBE with the KI-34 rule; excuses only the
    carry of a copy ending at #4000 of the second (last) block."""

    def setUp(self):
        self.prg = build("memprobe2")

    def test_faithful_model(self):
        cpu = z80sim.run(self.prg)
        self.assertEqual(cpu.alerts, ["MEMPROBE2 F=20 A=01 G=02 90 91 O=0107 P=0107 0107 W=OK R=20 E=20 L=02"])
        self.assertEqual(cpu.blocks_at_exit, [])

    def test_other_carries_are_bad(self):
        for pred in (lambda k: k[2] == 0x90 and k[3] == 0x3FF0,  # end of the first block (has a successor)
                     lambda k: k[2] == 0x91 and k[3] == 0x0000,  # middle of the last block
                     lambda k: k[0] == 0x91 and k[1] == 0x0000):  # a read from the last block
            with self.subTest():
                cpu = z80sim.run(self.prg, copy_carry_if=pred)
                self.assertIn("W=BAD", cpu.alerts[0])
                self.assertEqual(cpu.blocks_at_exit, [])

    def test_wrong_data_is_bad_even_with_the_excused_carry(self):
        cpu = z80sim.CPU(self.prg)
        w = cpu._write24
        cpu._write24 = lambda b, a, v: w(b, a, v ^ (1 if (b == 0x91 and a == 0x3FFF) else 0))
        try:
            while not cpu.exited:
                cpu.step()
        except z80sim._SimStop:
            pass
        self.assertIn("W=BAD", cpu.alerts[0])


@requires_pasmo
class BankTestProgramTests(unittest.TestCase):
    """developer-tests/banktest.pbas: every alert's observed part equals its [expected]."""

    def test_alerts(self):
        src = (ROOT / "developer-tests" / "banktest.pbas").read_text()
        r = guarded_run(src)
        self.assertEqual(r.violations, [])
        self.assertEqual(len(r.cpu.alerts), 4)
        for alert in r.cpu.alerts:
            seen, want = alert.split(" [", 1)
            self.assertEqual(seen.split(": ", 1)[1], want.rstrip("]"), alert)
        self.assertEqual(r.cpu.blocks_at_exit, [])
        self.assertGreater(len(r.cpu.copy_end_errors), 0)  # the harmless carries happened and were excused


@requires_pasmo
class MemLeakTests(unittest.TestCase):
    def test_one_block_kept_on_purpose(self):
        cpu = z80sim.run(build("memleak"))
        self.assertTrue(cpu.exited)
        self.assertEqual(cpu.alerts, ["MEMLEAK F=20 G=90 L=1F"])
        self.assertEqual(cpu.blocks_at_exit, [0x90])  # the model does not release at exit
        self.assertNotIn(z80sim.FN_OS_COPY_24BIT, [fn for fn, _ in cpu.os_log])

    def test_no_memory(self):
        cpu = z80sim.run(build("memleak"), free_blocks=0)
        self.assertEqual(cpu.alerts, ["MEMLEAK F=00 G=00 L=00"])


@requires_pasmo
class CodeProbeTests(unittest.TestCase):
    def setUp(self):
        self.prg = build("codeprobe")

    def probe(self, name_block=b"CODEPROBE\0.PRG\0", **kw):
        return run_probe(ProbeCPU(self.prg, name_block, **kw))

    def test_layout(self):
        self.assertGreater(len(self.prg), 0x4000)
        self.assertLess(len(self.prg), 0x4000 + 0x2000)  # the tail fits one read with slack in the block

    def test_tail_loaded_mapped_called_and_released(self):
        cpu = self.probe()
        self.assertTrue(cpu.exited)
        self.assertEqual(cpu.alerts, [
            "CODEPROBE N=CODEPROBE X=.PRG G=90 P=0107 O=00 R=00 00 00 C=OK S=00 T=00 D=OK Q=8B 8B F=20",
            "CODEPROBE 2 K=OK A=1F M=90"])
        self.assertEqual(cpu.opened, [("CODEPROBE", ".PRG", 0)] * 2)  # once per method
        self.assertIsNone(cpu.pos, "file left open")
        self.assertEqual(cpu.os_from_q2, [33])
        self.assertEqual(cpu.unowned_maps, [])
        self.assertEqual(cpu.q2, OLD_Q2)
        self.assertEqual(cpu.blocks_at_exit, [])

    def test_missing_extension_defaults_to_prg(self):
        cpu = self.probe(name_block=b"Code probe\0")
        self.assertEqual(cpu.opened, [("Code probe", ".PRG", 0)] * 2)
        self.assertTrue(cpu.alerts[0].startswith("CODEPROBE N=Code probe X=.PRGD G=90"))

    def test_longest_name_and_extension(self):
        cpu = self.probe(name_block=b"A" * 32 + b"\0.ABCDEFG\0", open_fails=0x02)
        self.assertEqual(cpu.opened, [("A" * 32, ".ABCDEFG", 0)])
        self.assertLess(len(cpu.alerts[0]), 160)

    def test_set_ptr_refused_is_reported(self):
        cpu = self.probe(set_ptr_works=False)
        self.assertIn("C=OK S=C8 T=FF D=SKIP", cpu.alerts[0])
        self.assertEqual(cpu.alerts[1], "CODEPROBE 2 K=OK A=1F M=90")  # method 1 still loads the tail
        self.assertEqual(cpu.blocks_at_exit, [])

    def test_open_failure_skips_everything(self):
        cpu = self.probe(open_fails=0x02)
        self.assertEqual(cpu.alerts, ["CODEPROBE N=CODEPROBE X=.PRG G=90 P=0107 O=02 R=FF FF FF C=SKIP S=FF T=FF D=SKIP Q=8B 8B F=20"])
        self.assertEqual(cpu.os_from_q2, [])
        self.assertEqual(cpu.blocks_at_exit, [])

    def test_no_memory(self):
        cpu = run_probe(self._no_mem())
        self.assertEqual(cpu.alerts, ["CODEPROBE N=CODEPROBE X=.PRG G=00 P=FFFF O=FF R=FF FF FF C=SKIP S=FF T=FF D=SKIP Q=8B 8B F=00"])
        self.assertEqual(cpu.opened, [])

    def test_foreign_block_is_not_used(self):
        cpu = ProbeCPU(self.prg, b"CODEPROBE\0.PRG\0")
        cpu.mem_owner = {0x90: 0x0108}
        run_probe(cpu)
        self.assertIn("G=90 P=0108 O=FF", cpu.alerts[0])
        self.assertEqual(cpu.opened, [])
        self.assertEqual(cpu.blocks_at_exit, [])

    def _no_mem(self):
        cpu = ProbeCPU(self.prg, b"CODEPROBE\0.PRG\0")
        cpu.mem_free = []
        return cpu


if __name__ == "__main__":
    unittest.main()
