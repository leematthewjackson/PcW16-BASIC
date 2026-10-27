"""M9 Stage A — code banks: programs whose procedures do not fit one 16K block.

pbas/codebanks.py places every SUB and FUNCTION in code banks that the
program loads itself (runtime IF PB_CODEBANKS). These tests build with Pasmo
and run on tests/z80sim.py, whose M9 model maps quarter 2 (bios_setmem2 /
bios_getmem2), loads only the first 16K of a longer file and puts the file
on the model disc. Simulator evidence only: the Rosanne contracts are
CODEPROBE's (XAnne, M8) plus what BANKPROBE will show (docs/M9-ACCEPTANCE.md).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import SourceError
from pbas import codebanks
from pbas.prg import ImageTooLarge, build
from test_m6_phase1 import numbers
from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
PROBE = (ROOT / "developer-tests" / "bankprobe.pbas").read_text(encoding="utf-8")
PROBE_BUILD = dict(code_banks="always", code_bank_limit=400)
READ_ERR = "Runtime error: the program's code\ncould not be read from its file"
MEM_ERR = "Runtime error: not enough free memory\nfor the program's code"


def big_program(count: int = 110) -> tuple[str, int, str]:
    """A program of *count* distinct FUNCTIONs (integer, string and REAL
    work), called from a driver SUB; returns (source, expected total,
    expected text)."""
    lines = ["DIM Total AS INTEGER", "DIM Text$ AS STRING", "DIM R AS REAL"]
    total = 0
    for k in range(1, count + 1):
        lines += [f"FUNCTION F{k}(V AS INTEGER) AS INTEGER",
                  "    LOCAL T AS INTEGER", "    LOCAL S$ AS STRING",
                  f"    T = V * {k % 7 + 1} + {k}",
                  f'    S$ = STR$(T) + "-{k}"',
                  "    IF LEN(S$) > 5 THEN", "        T = T + 1", "    END IF",
                  "    RETURN T MOD 1000", "END FUNCTION"]
        t = k * (k % 7 + 1) + k
        if len(f"{t}-{k}") > 5:
            t += 1
        total = (total + t % 1000) % 10000
    lines += ["FUNCTION Half(X AS REAL) AS REAL", "    RETURN X / 2", "END FUNCTION",
              "SUB Driver"]
    lines += [f"    Total = (Total + F{k}({k})) MOD 10000" for k in range(1, count + 1)]
    lines += ['    R = Half(7.0)', '    Text$ = "T=" + STR$(Total) + " R=" + STR$(R)',
              "    MESSAGE Text$", "END SUB", "CALL Driver", "END"]
    return "\n".join(lines) + "\n", total, f"T={total} R=3.5"


def build_text(src: str, tmp: Path, name: str = "t", **options):
    path = tmp / f"{name}.pbas"
    path.write_text(src, encoding="utf-8")
    return build(path, tmp / f"{name}.asm", tmp / f"{name}.prg", **options)


class PackTests(unittest.TestCase):
    """Placement is a pure function of the procedure sizes (no Pasmo)."""

    def test_first_fit_decreasing_is_deterministic(self):
        sizes = [("A", 9000, 1), ("B", 7000, 2), ("C", 6000, 3), ("D", 800, 4), ("E", 800, 5)]
        banks = codebanks.pack(sizes)
        self.assertEqual([b.procedures for b in banks], [["A", "C", "D"], ["B", "E"]])
        self.assertEqual(banks, codebanks.pack(list(sizes)))
        for bank in banks:
            self.assertLessEqual(bank.used, codebanks.BANK_LIMIT)

    def test_bank_lists_its_procedures_in_source_order(self):
        banks = codebanks.pack([("Z", 10, 1), ("Y", 500, 2), ("X", 20, 3)])
        self.assertEqual(banks[0].procedures, ["Z", "Y", "X"])

    def test_exact_fit_and_one_byte_over(self):
        room = codebanks.BANK_LIMIT - codebanks.BANK_MAGIC - codebanks.ENTRY_SIZE
        self.assertEqual(len(codebanks.pack([("A", room, 1)])), 1)
        with self.assertRaises(SourceError) as caught:
            codebanks.pack([("A", room + 1, 7)])
        self.assertEqual(caught.exception.line, 7)
        self.assertIn(f"over the {room}-byte limit of one code bank", caught.exception.message)
        two = codebanks.pack([("A", room, 1), ("B", 1, 2)])
        self.assertEqual([b.procedures for b in two], [["A"], ["B"]])

    def test_limits(self):
        with self.assertRaises(SourceError):
            codebanks.pack([("A", 1, 1)], limit=codebanks.MIN_BANK_LIMIT - 1)
        with self.assertRaises(SourceError):
            codebanks.pack([("A", 1, 1)], limit=codebanks.BANK_LIMIT + 1)
        many = [(f"P{i}", 1000, i) for i in range(16 * 15 + 1)]
        with self.assertRaises(SourceError) as caught:
            codebanks.pack(many)
        self.assertIn("at most 16", caught.exception.message)

    def test_entries(self):
        self.assertEqual(codebanks.bank_entry(0), 0x8003)
        self.assertEqual(codebanks.bank_entry(5), 0x8012)

    def test_bank_text_must_be_code(self):
        with self.assertRaises(SourceError):
            codebanks.check_bank_text("X", ["sub_X:", "    ld a,1", "lbl: db 1,2"], 3)
        with self.assertRaises(SourceError):
            codebanks.check_bank_text("X", ["    defs 10"], 3)
        codebanks.check_bank_text("X", ["sub_X:", "    ld hl,lit_1 ; db in a comment", "    ret"], 3)


@requires_pasmo
class BuildTests(unittest.TestCase):
    def test_auto_leaves_fitting_programs_alone(self):
        src = (ROOT / "examples" / "journal.pbas").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            auto = build_text(src, t, "a")
            never = build_text(src, t, "n", code_banks="never")
        self.assertIsNone(auto.banked)
        self.assertEqual(auto.sha256, never.sha256)

    def test_big_program_needs_banks(self):
        src, _, _ = big_program()
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            with self.assertRaises(ImageTooLarge):
                build_text(src, t, "n", code_banks="never")
            report = build_text(src, t, "a")
            again = build_text(src, t, "b")
            image = (t / "a.prg").read_bytes()
            files = sorted(p.name for p in t.iterdir() if p.name.startswith("a.") and p.suffix != ".pbas")
            mapping = (t / "a.map").read_text()
        layout = report.banked
        self.assertIsNotNone(layout)
        self.assertEqual(report.sha256, again.sha256, "placement must be deterministic")
        self.assertGreater(sum(layout.sizes.values()), 16384, "more than 16K of procedure code")
        self.assertGreaterEqual(len(layout.banks), 2)
        self.assertEqual(len(image), 16384 + sum(len(b.image) for b in layout.banks))
        self.assertEqual(image[:256], bytes(256))
        at = 16384
        for bank in layout.banks:
            self.assertEqual(image[at:at + 3], bytes((ord("P"), ord("B"), bank.number)))
            self.assertEqual(len(bank.image) % 512, 0)
            self.assertLessEqual(len(bank.image), codebanks.BANK_LIMIT)
            at += len(bank.image)
        self.assertEqual(files, sorted(["a.asm", "a.map", "a.prg", "a.sym"]
                                       + [f"a.bank{b.number}.asm" for b in layout.banks]))
        self.assertIn("sub_F1", mapping)

    def test_always_without_procedures_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SourceError) as caught:
                build_text('MESSAGE "x"\nEND\n', Path(tmp), code_banks="always")
        self.assertIn("no SUB or FUNCTION", caught.exception.message)

    def test_too_big_procedure_is_positioned(self):
        body = "\n".join("    N = N + 1" for _ in range(2500))
        src = f"DIM N AS INTEGER\nSUB Huge\n{body}\nEND SUB\nCALL Huge\nEND\n"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SourceError) as caught:
                build_text(src, Path(tmp))
        self.assertEqual(caught.exception.line, 2)
        self.assertIn("limit of one code bank", caught.exception.message)

    def test_resident_part_too_big_is_explained(self):
        src = ('DIM A(250) AS STRING\nSUB S\nA(1) = "x"\nEND SUB\nCALL S\nEND\n')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SourceError) as caught:
                build_text(src, Path(tmp))
        self.assertIn("resident part", caught.exception.message)


@requires_pasmo
class RunTests(unittest.TestCase):
    def test_big_program_runs(self):
        src, _, text = big_program()
        r = guarded_run(src, string_capacity=64)
        self.assertEqual(r.violations, [])
        self.assertIsNotNone(r.report.banked)
        self.assertEqual(r.alerts, [text])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.blocks_at_exit, [])
        self.assertEqual(r.cpu.q2, z80sim.Q2_START_BLOCK)
        reads = [d for fn, d in r.cpu.os_log if fn == z80sim.FN_OS_READ_FILE]
        self.assertEqual(reads[:2], [0x2000, 0x2000], "the resident 16K skipped as 2 x 8K")
        self.assertLessEqual(max(reads), 0x2000, "pieces of at most 8K (CODEPROBE read size)")
        self.assertEqual(sum(reads[2:]), sum(len(b.image) for b in r.report.banked.banks))

    def test_probe_all_handlers(self):
        n = numbers(PROBE)
        r = guarded_run(PROBE, events=[("click", n["Run tests"]), ("menu", 1, 0), ("menu", 1, 0),
                                       ("timer", 0), ("timer", 0), ("timer", 0), ("click", n["Quit"])],
                        build_options=PROBE_BUILD)
        self.assertEqual(r.violations, [])
        self.assertEqual(len(r.report.banked.banks), 3)
        self.assertEqual(r.alerts, ["B1 nested: 3142 [3142]", "B2 REAL: 3.75 [3.75]",
                                    "B3 file: hello 42 IOERR=0 [hello 42 IOERR=0]"])
        self.assertEqual(string_var(r, "STATUS$"), "Tests done")
        self.assertEqual(string_var(r, "MENULINE$"), "Menu 2")
        self.assertEqual(string_var(r, "TICKLINE$"), "Ticks 3")
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.blocks_at_exit, [])
        self.assertEqual(r.cpu.disk.open_at_exit, (None, None))
        self.assertNotIn(("\\PCW\\FOLDER01", "BANKPRB.TMP"), r.cpu.disk.files)
        self.assertEqual(r.cpu.q2, z80sim.Q2_START_BLOCK)
        self.assertEqual(set(r.cpu.q2_at_wait), {z80sim.Q2_START_BLOCK},
                         "the event loop always runs with the start block at #8000")
        banks = set(r.cpu.owned) | {b for b in r.cpu.q2_maps if b != z80sim.Q2_START_BLOCK}
        self.assertEqual(len(banks), 3, "all three banks were mapped")

    def test_runtime_error_in_a_bank(self):
        n = numbers(PROBE)
        r = guarded_run(PROBE, events=[("click", n["Error"])], build_options=PROBE_BUILD)
        self.assertEqual(r.violations, [])
        line = next(i for i, t in enumerate(PROBE.splitlines(), 1) if "Small(Probe) = 1" in t)
        self.assertEqual(r.alerts, [f"Runtime error: index out of range at line {line}"])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.blocks_at_exit, [])
        self.assertEqual(r.cpu.q2, z80sim.Q2_START_BLOCK)

    def test_system_quit_while_running(self):
        r = guarded_run(PROBE, events=[("exit",)], build_options=PROBE_BUILD)
        self.assertEqual(r.violations, [])
        self.assertTrue(r.cpu.exited)
        self.assertEqual(r.cpu.blocks_at_exit, [])

    def test_other_extension(self):
        n = numbers(PROBE)
        r = guarded_run(PROBE, events=[("click", n["Quit"])], build_options=PROBE_BUILD,
                        program_ext=".APP")
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, [])
        opened = [d for fn, d in r.cpu.os_log if fn == z80sim.FN_OS_OPEN_FILE]
        self.assertEqual(opened, [("PROGRAM.APP", 0)])

    def test_name_block_without_extension(self):
        n = numbers(PROBE)
        r = guarded_run(PROBE, events=[("click", n["Quit"])], build_options=PROBE_BUILD,
                        name_block="bare")
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, [])
        self.assertTrue(r.cpu.exited)

    def _fails(self, message: str, **options):
        r = guarded_run(PROBE, events=[], build_options=PROBE_BUILD, **options)
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, [message])
        self.assertTrue(r.cpu.exited, "the program must end, not open its window")
        self.assertIsNone(r.cpu.dialog)
        self.assertEqual(r.cpu.blocks_at_exit, [])
        self.assertEqual(r.cpu.q2, z80sim.Q2_START_BLOCK)
        self.assertIsNone(r.cpu.disk.open_read)
        return r

    def test_not_enough_memory(self):
        for free in (0, 1, 2):
            with self.subTest(free=free):
                r = self._fails(MEM_ERR, free_blocks=free)
                self.assertEqual(len(r.cpu.mem_free), free, "every block given was released")

    def test_block_owned_by_someone_else(self):
        self._fails(MEM_ERR, mem_owner={0x91: 0x0155})

    def test_block_not_ram(self):
        self._fails(MEM_ERR, mem_owner={0x90: 0x0081})
        r = self._fails(MEM_ERR, mem_pool=[0x7F, 0x90, 0x91, 0x92])
        self.assertNotIn(z80sim.FN_OS_OPEN_FILE, [fn for fn, _ in r.cpu.os_log])

    def test_own_file_missing(self):
        self._fails(READ_ERR, file_image=b"")

    def _image(self) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            build_text(PROBE, Path(tmp), "p", **PROBE_BUILD)
            return (Path(tmp) / "p.prg").read_bytes()

    def test_file_too_short(self):
        image = self._image()
        for cut in (1, 512, len(image) - 16384 + 1, len(image) - 8192):
            with self.subTest(cut=cut):
                self._fails(READ_ERR, file_image=image[:-cut])

    def test_damaged_bank(self):
        image = self._image()
        for at in (16384 + 3, 16384 + 511, len(image) - 1):
            with self.subTest(at=at):
                bad = bytearray(image)
                bad[at] ^= 0x01
                self._fails(READ_ERR, file_image=bytes(bad))

    def test_read_error_in_a_bank(self):
        for n in (3, 4, 5):  # reads 1-2 skip the resident 16K, 3-5 are the three banks
            with self.subTest(read=n):
                disk = z80sim.Disk(faults_from={z80sim.FN_OS_READ_FILE: (n, 0x0A)})
                r = self._fails(READ_ERR, disk=disk)
                calls = [f for f, _ in r.cpu.os_log]
                self.assertEqual(calls.count(z80sim.FN_OS_READ_FILE), n, "stops at the failed read")
                after = calls[len(calls) - calls[::-1].index(z80sim.FN_OS_READ_FILE):]
                self.assertEqual(after[0], z80sim.FN_OS_CLOSE_FILE)

    def _same_sum(self, image: bytes, at: int, value: int) -> bytes:
        """*image* with byte *at* set to *value* and another byte of the
        same bank changed so that the bank's sum is unchanged."""
        bad = bytearray(image)
        delta = value - bad[at]
        bad[at] = value
        k = next(i for i in range(at + 3, at + 400) if 0 <= bad[i] - delta <= 255 and bad[i])
        bad[k] -= delta
        self.assertEqual(sum(bad[16384:16896]) & 0xFFFF, sum(image[16384:16896]) & 0xFFFF)
        return bytes(bad)

    def test_magic_checked_even_when_the_sum_matches(self):
        image = self._image()
        self._fails(READ_ERR, file_image=self._same_sum(image, 16384, ord("Q")))
        self._fails(READ_ERR, file_image=self._same_sum(image, 16385, ord("C")))
        self._fails(READ_ERR, file_image=self._same_sum(image, 16386, 2))

    def test_banks_swapped(self):
        image = self._image()
        swapped = image[:16384] + image[16384 + 512:16384 + 1024] + image[16384:16384 + 512] + image[16384 + 1024:]
        self._fails(READ_ERR, file_image=swapped)

    def test_read_and_open_errors(self):
        for fn, code in ((z80sim.FN_OS_READ_FILE, 0x0A), (z80sim.FN_OS_OPEN_FILE, 0x05)):
            with self.subTest(fn=fn):
                disk = z80sim.Disk(faults={fn: code})
                r = self._fails(READ_ERR, disk=disk)
                calls = [f for f, _ in r.cpu.os_log]
                if fn == z80sim.FN_OS_OPEN_FILE:
                    self.assertNotIn(z80sim.FN_OS_READ_FILE, calls, "no read after a failed open")
                    self.assertNotIn(z80sim.FN_OS_CLOSE_FILE, calls)
                else:
                    self.assertEqual(calls.count(z80sim.FN_OS_READ_FILE), 1, "stops at the first error")
                    self.assertEqual(calls.count(z80sim.FN_OS_CLOSE_FILE), 1)


@requires_pasmo
class BankedDataTests(unittest.TestCase):
    """M8 BANKED arrays in a code-banked program: the code blocks are got
    first, so the last BANKED block is still the program's last block and
    the KI-34 end-of-last-block carry is still the only one excused."""

    SRC = ("DIM A(8192) AS INTEGER BANKED\nDIM B(8192) AS INTEGER BANKED\nDIM S$ AS STRING\n"
           "SUB Fill\nA(8192) = 11\nB(8192) = 22\nB(1) = 3\nEND SUB\n"
           "FUNCTION Sum() AS INTEGER\nRETURN A(8192) + B(8192) + B(1)\nEND FUNCTION\n"
           "CALL Fill\nS$ = STR$(Sum())\nMESSAGE S$\nEND\n")

    def test_last_element_of_last_block(self):
        r = guarded_run(self.SRC, build_options=dict(code_banks="always", code_bank_limit=100))
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["36"])
        self.assertEqual(r.cpu.blocks_at_exit, [])
        code_blocks = r.report.banked and len(r.report.banked.banks)
        self.assertEqual(code_blocks, 2)
        # allocation order: the code blocks, then A's block, then B's
        firsts = [d for fn, d in r.cpu.os_log if fn == z80sim.FN_OS_GET_MEM]
        self.assertEqual(firsts, [(2, 2), (2, 2)])
        self.assertTrue(r.cpu.copy_end_errors, "the end-of-last-block carry happened and was excused")

    def test_without_code_banks_same_answer(self):
        r = guarded_run(self.SRC)
        self.assertEqual(r.violations, [])
        self.assertEqual(r.alerts, ["36"])


if __name__ == "__main__":
    unittest.main()
