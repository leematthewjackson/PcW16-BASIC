"""Tier-3/4 tests for the build pipeline tools (``tools/asmcheck.py``,
``tools/build.py``).

The asmcheck tests are pure-Python: inline fixture assembly strings, one rule
family each (TESTING-STRATEGY.md rules A1, A2, A4, A5, A6-partial, A7). The
build.py tests run the CLI end to end in a subprocess from a temporary
directory outside the repository (proving the sys.path bootstrap works from
any cwd): they need Pasmo (tests/toolchain.py: missing Pasmo is an error
unless PBAS_ALLOW_MISSING_PASMO=1 is set).
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from toolchain import requires_pasmo

REPO_ROOT = Path(__file__).resolve().parent.parent
ASMCHECK_PY = REPO_ROOT / "tools" / "asmcheck.py"
BUILD_PY = REPO_ROOT / "tools" / "build.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolves the module via sys.modules
    spec.loader.exec_module(module)
    return module


asmcheck = _load_module("asmcheck", ASMCHECK_PY)


# The M2 code-generation modules and runtime have landed; their absence is a
# broken checkout, and a missing Pasmo is an error unless explicitly allowed
# (tests/toolchain.py) — never a silent skip.
REQUIRE_TOOLCHAIN = requires_pasmo


def rules_of(findings):
    return sorted({finding.rule for finding in findings})


def messages_of(findings, rule):
    return [finding.message for finding in findings if finding.rule == rule]


# --- fixtures ----------------------------------------------------------------

# The frozen container shape (ARCHITECTURE.md D7, POC/NOTES.asm): org, zero
# prefix, start:, 4-space-indented instructions, column-0 labels. Includes a
# data expression ('ld de,msg_end-msg') which A1 must tolerate and a jump in
# every condition family the rule covers.
GOOD_PROGRAM = (
    "    org 4000h\n"
    "    defs 100h\n"
    "start:\n"
    "    call rt_mul16\n"
    "    jp z,start\n"
    "    jp pe,rt_mul16\n"
    "    jr nc,start\n"
    "    djnz start\n"
    "    ld hl,msg\n"
    "    ld de,msg_end-msg\n"
    "    call sub_do\n"
    "    ret\n"
    "sub_do:\n"
    "    ld a,1\n"
    "    ret\n"
    "rt_mul16:\n"
    "    ret\n"
    "msg:\n"
    "    db 72,105,0\n"
    "msg_end:\n"
)

DUPLICATE_LABEL = (
    "    org 4000h\n"
    "    defs 100h\n"
    "start:\n"
    "    jp start\n"
    "start:\n"
    "    ret\n"
)

MISSING_JP_TARGET = (
    "    org 4000h\n"
    "    defs 100h\n"
    "start:\n"
    "    jp nowhere\n"
)

EXPRESSION_TARGET = (
    "    org 4000h\n"
    "    defs 100h\n"
    "start:\n"
    "    jp start+1\n"
    "    ret\n"
)

SECOND_ORG = (
    "    org 4000h\n"
    "    defs 100h\n"
    "start:\n"
    "    ret\n"
    "    org 4000h\n"
)

MISSING_DEFS = (
    "    org 4000h\n"
    "start:\n"
    "    ret\n"
)

SECOND_PREFIX = (
    "    org 4000h\n"
    "    defs 100h\n"
    "start:\n"
    "    ret\n"
    "    defs 100h\n"
)

UNLABELLED_DEFS = (
    "    org 4000h\n"
    "    defs 100h\n"
    "start:\n"
    "    ret\n"
    "    defs 10\n"
)

LABELLED_DEFS_OK = (
    "    org 4000h\n"
    "    defs 100h\n"
    "start:\n"
    "    ret\n"
    "var_X:\n"
    "    defs 10\n"
)

DOLLAR_LABEL = (
    "    org 4000h\n"
    "    defs 100h\n"
    "var_A$:\n"
    "    ret\n"
)

DOLLAR_TOKEN = (
    "    org 4000h\n"
    "    defs 100h\n"
    "start:\n"
    "    ld hl,var_A$\n"
    "    ret\n"
)

# Program portion referencing rt_* labels that only exist in the runtime.
PROGRAM_NEEDS_RUNTIME = (
    "    org 4000h\n"
    "    defs 100h\n"
    "start:\n"
    "    call rt_mul16\n"
    "    ret\n"
)

CLEAN_RUNTIME = (
    "rt_mul16:\n"
    "    ld bc,0\n"
    "    ld a,16\n"
    "rt_mul_loop:\n"
    "    bit 0,l\n"
    "    jp z,rt_mul_skip\n"
    "    ret\n"
    "rt_mul_skip:\n"
    "    ret\n"
    "rt_alert:\n"
    "    ld a,76\n"
    "    call 003Bh\n"
    "    ret\n"
    # An ix read *before* the OS call is fine (only reads *after* are linted).
    "rt_probe:\n"
    "    ld a,(ix+2)\n"
    "    call 003Bh\n"
    "    ret\n"
)

RUNTIME_IY_READ = (
    "rt_alert:\n"
    "    ld a,76\n"
    "    call 003Bh\n"
    "    ld a,(iy+0)\n"
    "    ret\n"
)

RUNTIME_GETEVENT_NO_Z = (
    "rt_get_event:\n"
    "    ld hl,0ffffh\n"
    "    ld a,1\n"
    "    call 003Bh\n"
    "    ld b,a\n"
    "    ret\n"
)

RUNTIME_WAITEVENT_NO_Z = RUNTIME_GETEVENT_NO_Z.replace("ld a,1", "ld a,2")

# M3a: IX is the documented output of an event call (fn 1/2) — readable until
# the next OS call, after a Z-flag test.
RUNTIME_EVENT_IX_OK = (
    "rt_loop:\n"
    "    ld hl,0ffffh\n"
    "    ld a,2\n"
    "    call 003Bh\n"
    "    jp z,rt_loop\n"
    "    ld a,(ix+2)\n"
    "    ld (rt_cell),a\n"
    "    ld a,4\n"
    "    call 003Bh\n"
    "    ret\n"
    "rt_cell:\n"
    "    defs 1\n"
)

RUNTIME_IX_AFTER_PROCESS = (
    "rt_loop:\n"
    "    ld hl,0ffffh\n"
    "    ld a,2\n"
    "    call 003Bh\n"
    "    jp z,rt_loop\n"
    "    ld a,4\n"
    "    call 003Bh\n"
    "    ld a,(ix+3)\n"
    "    ret\n"
)

RUNTIME_WITH_ORG = (
    "    org 4000h\n"
    "rt_mul16:\n"
    "    ret\n"
)

# One combined build .asm: program container + appended runtime portion.
COMBINED_BUILD = (
    "    org 4000h\n"
    "    defs 100h\n"
    "start:\n"
    "    call rt_alert\n"
    "    ret\n"
    "; ---- runtime/runtime.z80.asm ----\n"
    "rt_alert:\n"
    "    ld a,76\n"
    "    call 003Bh\n"
    "    ret\n"
)

COMBINED_WITH_TRAP_IN_PROGRAM = (
    "    org 4000h\n"
    "    defs 100h\n"
    "start:\n"
    "    call 003Bh\n"
    "    ret\n"
    "; ---- runtime/runtime.z80.asm ----\n"
    "rt_alert:\n"
    "    ld a,76\n"
    "    call 003Bh\n"
    "    ret\n"
)


class AsmcheckRules(unittest.TestCase):
    """Unit tests for tools/asmcheck.py over inline fixture assembly."""

    def test_good_program_is_clean(self):
        self.assertEqual(asmcheck.check_source("mini.asm", GOOD_PROGRAM), [])

    def test_duplicate_label(self):
        findings = asmcheck.check_source("mini.asm", DUPLICATE_LABEL)
        self.assertEqual(rules_of(findings), ["A1"])
        self.assertIn("defined more than once", messages_of(findings, "A1")[0])

    def test_missing_jp_target(self):
        findings = asmcheck.check_source("mini.asm", MISSING_JP_TARGET)
        self.assertEqual(rules_of(findings), ["A1"])
        self.assertIn("'nowhere'", messages_of(findings, "A1")[0])

    def test_expression_jump_target_flagged(self):
        findings = asmcheck.check_source("mini.asm", EXPRESSION_TARGET)
        self.assertEqual(rules_of(findings), ["A1"])
        self.assertIn("unsupported expression jump target", messages_of(findings, "A1")[0])

    def test_second_org(self):
        findings = asmcheck.check_source("mini.asm", SECOND_ORG)
        self.assertEqual(rules_of(findings), ["A2"])
        self.assertIn("exactly one 'org 4000h'", messages_of(findings, "A2")[0])

    def test_code_bank_file(self):
        # M9: a bank (pbas/codebanks.py) runs at #8000 and takes resident
        # names as equ; neither is a finding, but an undefined target is.
        bank = ("; ---- code bank 1\n"
                "rt_farcall equ 4321h\n"
                "    org 8000h\n"
                "    db 'P','B',1\n"
                "    jp sub_a\n"
                "sub_a:\n"
                "    call rt_farcall\n"
                "    ret\n")
        self.assertEqual(asmcheck.check_source("p.bank1.asm", bank), [])
        findings = asmcheck.check_source(
            "p.bank1.asm", bank.replace("org 8000h", "org 4000h"))
        self.assertIn("org 8000h", messages_of(findings, "A2")[0])
        findings = asmcheck.check_source(
            "p.bank1.asm", bank.replace("call rt_farcall", "call nowhere"))
        self.assertEqual(rules_of(findings), ["A1"])

    def test_missing_defs_100h(self):
        findings = asmcheck.check_source("mini.asm", MISSING_DEFS)
        self.assertEqual(rules_of(findings), ["A2"])
        self.assertIn("defs 100h", messages_of(findings, "A2")[0])

    def test_second_defs_100h_is_a2_and_unlabelled_a6(self):
        findings = asmcheck.check_source("mini.asm", SECOND_PREFIX)
        self.assertEqual(rules_of(findings), ["A2", "A6"])

    def test_call_003b_outside_runtime_all_spellings(self):
        for spelling in ("003Bh", "#003B", "03Bh", "3Bh"):
            with self.subTest(spelling=spelling):
                text = (
                    "    org 4000h\n"
                    "    defs 100h\n"
                    "start:\n"
                    f"    call {spelling}\n"
                    "    ret\n"
                )
                findings = asmcheck.check_source("mini.asm", text)
                self.assertEqual(rules_of(findings), ["A4"])

    def test_ld_a_os_function_outside_runtime(self):
        for operand in ("76", "4Ch"):  # decimal and hex disguise, same value
            with self.subTest(operand=operand):
                text = (
                    "    org 4000h\n"
                    "    defs 100h\n"
                    "start:\n"
                    f"    ld a,{operand}\n"
                    "    ret\n"
                )
                findings = asmcheck.check_source("mini.asm", text)
                self.assertEqual(rules_of(findings), ["A4"])
                self.assertIn("function number 76", messages_of(findings, "A4")[0])

    def test_ld_a_non_os_value_is_clean(self):
        text = (
            "    org 4000h\n"
            "    defs 100h\n"
            "start:\n"
            "    ld a,42\n"
            "    ret\n"
        )
        self.assertEqual(asmcheck.check_source("mini.asm", text), [])

    def test_unlabelled_defs(self):
        findings = asmcheck.check_source("mini.asm", UNLABELLED_DEFS)
        self.assertEqual(rules_of(findings), ["A6"])

    def test_labelled_defs_is_clean(self):
        self.assertEqual(asmcheck.check_source("mini.asm", LABELLED_DEFS_OK), [])

    def test_dollar_in_label_definition(self):
        findings = asmcheck.check_source("mini.asm", DOLLAR_LABEL)
        self.assertEqual(rules_of(findings), ["A7"])

    def test_dollar_in_var_token(self):
        findings = asmcheck.check_source("mini.asm", DOLLAR_TOKEN)
        self.assertEqual(rules_of(findings), ["A7"])
        self.assertIn("var_A$", messages_of(findings, "A7")[0])

    def test_clean_runtime_is_ok(self):
        self.assertEqual(asmcheck.check_source("runtime.z80.asm", CLEAN_RUNTIME), [])

    def test_runtime_iy_read_after_call_is_a5(self):
        findings = asmcheck.check_source("runtime.z80.asm", RUNTIME_IY_READ)
        self.assertEqual(rules_of(findings), ["A5"])
        self.assertIn("'iy'", messages_of(findings, "A5")[0])

    def test_runtime_get_event_without_z_test_is_a5(self):
        findings = asmcheck.check_source("runtime.z80.asm", RUNTIME_GETEVENT_NO_Z)
        self.assertEqual(rules_of(findings), ["A5"])
        self.assertIn("Z-flag", messages_of(findings, "A5")[0])
        self.assertIn("os_get_event (fn 1)", messages_of(findings, "A5")[0])

    def test_runtime_wait_event_without_z_test_is_a5(self):
        findings = asmcheck.check_source("runtime.z80.asm", RUNTIME_WAITEVENT_NO_Z)
        self.assertEqual(rules_of(findings), ["A5"])
        self.assertIn("os_wait_event (fn 2)", messages_of(findings, "A5")[0])

    def test_runtime_event_z_test_must_come_first(self):
        # A flag-setting instruction between the call and the jump replaces
        # the no-event Z flag: 'bit 5,h' then 'jp z' is not a Z test.
        late = RUNTIME_EVENT_IX_OK.replace(
            "    call 003Bh\n    jp z,rt_loop\n",
            "    call 003Bh\n    bit 5,h\n    jp z,rt_loop\n",
            1,
        )
        findings = asmcheck.check_source("runtime.z80.asm", late)
        self.assertEqual(rules_of(findings), ["A5"])
        self.assertIn("as the next instruction", messages_of(findings, "A5")[0])

    def test_runtime_ix_after_event_call_is_ok(self):
        self.assertEqual(asmcheck.check_source("runtime.z80.asm", RUNTIME_EVENT_IX_OK), [])

    def test_runtime_ix_after_other_call_is_a5(self):
        findings = asmcheck.check_source("runtime.z80.asm", RUNTIME_IX_AFTER_PROCESS)
        self.assertEqual(rules_of(findings), ["A5"])
        self.assertIn("'ix'", messages_of(findings, "A5")[0])

    def test_runtime_must_not_set_org(self):
        findings = asmcheck.check_source("runtime.z80.asm", RUNTIME_WITH_ORG)
        self.assertEqual(rules_of(findings), ["A2"])

    def test_combined_build_splits_runtime_appendix(self):
        # The runtime's own call 003Bh is exempt; the program's would not be.
        self.assertEqual(asmcheck.check_source("mini.asm", COMBINED_BUILD), [])
        findings = asmcheck.check_source("mini.asm", COMBINED_WITH_TRAP_IN_PROGRAM)
        self.assertEqual(rules_of(findings), ["A4"])
        self.assertEqual(len(findings), 1)

    def test_rt_call_targets_resolve_across_sources(self):
        alone = asmcheck.check_sources([("mini.asm", PROGRAM_NEEDS_RUNTIME)])
        self.assertEqual(rules_of(alone), ["A1"])  # rt_mul16 undefined here
        together = asmcheck.check_sources(
            [("mini.asm", PROGRAM_NEEDS_RUNTIME), ("runtime.z80.asm", CLEAN_RUNTIME)]
        )
        self.assertEqual(rules_of(together), [])

    def test_duplicate_label_across_sources(self):
        findings = asmcheck.check_sources(
            [("mini.asm", GOOD_PROGRAM), ("runtime.z80.asm", CLEAN_RUNTIME)]
        )
        # GOOD_PROGRAM defines rt_mul16; CLEAN_RUNTIME defines it again.
        self.assertIn("A1", rules_of(findings))
        self.assertIn("defined more than once", messages_of(findings, "A1")[0])


class AsmcheckCli(unittest.TestCase):
    """The asmcheck command-line interface itself."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def _run(self, *files: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ASMCHECK_PY), *(str(f) for f in files)],
            capture_output=True,
            text=True,
        )

    def test_cli_ok(self):
        good = self.dir / "good.asm"
        good.write_text(GOOD_PROGRAM, encoding="utf-8")
        result = self._run(good)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)

    def test_cli_reports_findings_and_exits_1(self):
        bad = self.dir / "bad.asm"
        bad.write_text(DUPLICATE_LABEL, encoding="utf-8")
        result = self._run(bad)
        self.assertEqual(result.returncode, 1)
        self.assertIn("1 finding", result.stdout)
        self.assertIn("[A1]", result.stdout)

    def test_cli_missing_file(self):
        result = self._run(self.dir / "absent.asm")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read", result.stderr)


MINI_PROGRAM = (
    "DIM X AS INTEGER\n"
    "X = 2 + 3\n"
    "MESSAGE STR$(X)\n"
    "END\n"
)

WINDOW_PROGRAM = 'WINDOW "Hi"\nEND\n'


@REQUIRE_TOOLCHAIN
class BuildEndToEnd(unittest.TestCase):
    """Tier-4 toolchain gate: build.py drives pbas.prg.build + Pasmo."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.src = self.dir / "mini.pbas"
        self.src.write_text(MINI_PROGRAM, encoding="utf-8")
        self.out = self.dir / "build"

    def _run_build(self, *extra: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        # Run from the temp dir (outside the repo) on purpose: tools/build.py
        # must bootstrap sys.path so 'import pbas' works from any cwd.
        return subprocess.run(
            [sys.executable, str(BUILD_PY), str(self.src), *map(str, extra)],
            cwd=cwd or self.dir,
            capture_output=True,
            text=True,
        )

    def test_builds_asm_and_prg_with_container_shape(self):
        result = self._run_build("--out-dir", self.out)
        self.assertEqual(result.returncode, 0, result.stderr)
        asm_path = self.out / "mini.asm"
        prg_path = self.out / "mini.prg"
        self.assertTrue(asm_path.is_file())
        self.assertGreater(asm_path.stat().st_size, 0)
        data = prg_path.read_bytes()
        # .PRG container (ARCHITECTURE.md D7, POC NOTES.PRG shape): 256-byte
        # zero prefix, first code byte at 0x100, <= 16K image (M2.1).
        self.assertEqual(data[:256], bytes(256))
        self.assertNotEqual(data[256], 0)
        self.assertLessEqual(len(data), 16384)
        self.assertRegex(result.stdout, r"(?m)^asm: .+ \(\d+ bytes\)$")
        self.assertRegex(result.stdout, r"(?m)^prg: .+ \(\d+ bytes, sha256 [0-9a-f]{64}\)$")
        digest = re.search(r"sha256 ([0-9a-f]{64})", result.stdout).group(1)
        self.assertEqual(digest, hashlib.sha256(data).hexdigest())

    def test_build_is_reproducible(self):
        first = self._run_build("--out-dir", self.out)
        prg_path = self.out / "mini.prg"
        first_bytes = prg_path.read_bytes()
        second = self._run_build("--out-dir", self.out)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(prg_path.read_bytes(), first_bytes)
        self.assertEqual(second.stdout, first.stdout)

    def test_asm_and_prg_override_paths(self):
        asm_path = self.dir / "custom.asm"
        prg_path = self.dir / "nested" / "custom.prg"
        result = self._run_build("--asm", asm_path, "--prg", prg_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(asm_path.is_file())
        self.assertTrue(prg_path.is_file())
        self.assertIn(f"asm: {asm_path}", result.stdout)
        self.assertIn(f"prg: {prg_path}", result.stdout)

    def test_buttonless_window_program_fails(self):
        self.src.write_text(WINDOW_PROGRAM, encoding="utf-8")
        result = self._run_build("--out-dir", self.out)
        self.assertEqual(result.returncode, 1)
        self.assertIn("at least one BUTTON", result.stderr)
        self.assertIn(str(self.src), result.stderr)

    def test_out_of_range_string_capacity_fails(self):
        result = self._run_build("--out-dir", self.out, "--string-capacity", "1")
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(self.src), result.stderr)


class BuildCliWithoutToolchain(unittest.TestCase):
    """Failure modes of build.py that do not need Pasmo or codegen."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_missing_source_fails(self):
        missing = self.dir / "absent.pbas"
        result = subprocess.run(
            [sys.executable, str(BUILD_PY), str(missing)],
            cwd=self.dir,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(missing), result.stderr)


if __name__ == "__main__":
    unittest.main()


@requires_pasmo
class MemreportOverLimit(unittest.TestCase):
    """M13: the build error for a resident part over 16K points to
    tools/memreport.py, so memreport must report such a program (where the
    bytes go, and by how much it is over) instead of failing on it."""

    def test_an_oversized_program_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "big.pbas"
            src.write_text('DIM A(200) AS STRING * 90\nSUB S\n    A(1) = "x"\nEND SUB\nCALL S\nEND\n',
                           encoding="utf-8")
            out = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "tools" / "memreport.py"),
                                  str(src)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("bytes over the 16384-byte limit: it does not build", out.stdout)
        arrays = int(re.search(r"^\s+(\d+)\s+arrays$", out.stdout, re.M).group(1))
        self.assertGreaterEqual(arrays, 200 * 91)
        self.assertRegex(out.stdout, r"\s-\d+\s+free \(to the 16K limit\)")


class LibraryReference(unittest.TestCase):
    """M13: docs/LIBRARY-REFERENCE.md is made from the libraries' own
    comments by tools/libref.py and must be current."""

    def test_the_reference_is_current(self):
        out = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "tools" / "libref.py"),
                              "--check"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
