"""Tier-4 toolchain gate (R-EX): every shipped M2 example must build cleanly.

Each ``examples/*.pbas`` program is assembled with Pasmo via ``tools/build.py``
into a temp directory (never into the repo, never over POC artefacts), the
emitted ASM passes ``tools/asmcheck.py``, and the resulting ``.prg`` satisfies
the container guards (D7/F8: 256 zero prefix bytes, non-trivial size, <= 16K first bank, M2.1;
M9: a banked example's banks follow the 16K block and pass asmcheck too).
The behavioural content of the alerts is covered by ``test_behaviour.py``
(engineering aid, not runtime evidence); XAnne runs are owner-executed and
recorded in ``RUNTIME-RESULTS.md``.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _example_sources() -> list[Path]:
    return sorted(EXAMPLES.glob("*.pbas"))


def _declared_options(source: Path) -> list[str]:
    """Build options an example names in a header comment (M7), e.g.
    ``' Build with --string-capacity 32 (...)``."""
    match = re.search(r"^' Build with ((?:--string-capacity \d+|--runtime-banks \S+)"
                      r"(?: (?:--string-capacity \d+|--runtime-banks \S+))*)",
                      source.read_text(encoding="utf-8"), re.M)  # M11: --runtime-banks
    return match.group(1).split() if match else []


@requires_pasmo
class ExampleBuildTests(unittest.TestCase):
    def test_all_examples_build_and_pass_asmcheck(self):
        sources = _example_sources()
        self.assertGreaterEqual(len(sources), 6, "expected the six M2 examples")
        for source in sources:
            with self.subTest(example=source.name), tempfile.TemporaryDirectory() as tmp:
                build = subprocess.run(
                    [sys.executable, str(ROOT / "tools" / "build.py"),
                     str(source), "--out-dir", tmp, *_declared_options(source)],
                    capture_output=True, text=True, cwd=ROOT,
                )
                self.assertEqual(build.returncode, 0, build.stderr)
                prg = Path(tmp) / (source.stem + ".prg")
                asm = Path(tmp) / (source.stem + ".asm")
                self.assertTrue(prg.exists(), build.stdout)
                self.assertTrue(asm.exists(), build.stdout)
                data = prg.read_bytes()
                self.assertEqual(data[:256], b"\0" * 256, "256-byte zero prefix")
                self.assertGreater(len(data), 256, "image must exceed the prefix")
                banks = sorted(Path(tmp).glob(source.stem + ".bank*.asm"))
                if banks:
                    # M9 code banks (LANGUAGE-SPEC §5.5): the loader reads the
                    # padded 16K resident block; each bank follows it, padded
                    # to a multiple of 512 and at most 15872 bytes.
                    rest = len(data) - 16384
                    self.assertGreater(rest, 0, "banks follow the 16K resident block")
                    self.assertEqual(rest % 512, 0, "banks padded to 512")
                    self.assertLessEqual(rest, 15872 * len(banks))
                else:
                    self.assertLessEqual(len(data), 16384, "16K first-bank image limit")
                # Each bank is its own assembly (it defines its procedures'
                # sub_ labels; the resident block defines their stubs).
                for unit in (asm, *banks):
                    check = subprocess.run(
                        [sys.executable, str(ROOT / "tools" / "asmcheck.py"), str(unit)],
                        capture_output=True, text=True, cwd=ROOT,
                    )
                    self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
                # Reproducibility: a second build is byte-identical.
                again = subprocess.run(
                    [sys.executable, str(ROOT / "tools" / "build.py"),
                     str(source), "--out-dir", tmp, *_declared_options(source)],
                    capture_output=True, text=True, cwd=ROOT,
                )
                self.assertEqual(again.returncode, 0, again.stderr)
                self.assertEqual(prg.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
