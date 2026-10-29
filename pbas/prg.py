""".PRG container assembly and the top-level build pipeline (ARCHITECTURE.md D7).

``assemble`` concatenates the emitted program portion with the hand-written
``runtime/runtime.z80.asm`` (D2: that file is the only place Rosanne is
called), invokes ``pasmo --bin`` and guards the XAnne-proven container shape:
``org 4000h`` with a 256-byte zero prefix (execution starts at #4100,
ROSAN283.DOC 'Memory Layout'; F8), image size within the first 16K bank
(M2.1, see PRG_IMAGE_MAX). ``build`` composes the M1 frontend, the M2 generator and assembly.
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import SourceError
from .files import FileLocation
from .lexer import tokenize
from .parser import Parser
from .policy import DEFAULT_STRING_CAPACITY
from .program import build_program
from .semantics import analyze
from .prune import prune_real
from .statements import generate_parts
from . import codebanks
from . import include

#: Default runtime source, appended after every emitted program (D2).
DEFAULT_RUNTIME_PATH = Path(__file__).resolve().parent.parent / "runtime" / "runtime.z80.asm"

#: .PRG container facts (D7, F8, F10).
PREFIX_SIZE = 256  # zero prefix; start: lands at #4100
# The whole image (code, data, runtime buffers) must lie in #4000-#7FFF.
# ROSAN283 'Memory Layout': the app's starting block is switched into the 2nd
# quarter and "Switching in further blocks of your app is up to you"; nothing
# in Supporting Docs/ says a disk-loaded .PRG gets #8000-#FFFF mapped. And
# ROSAN283 'Addressing': a 24-bit pointer is a bank number plus a 14-bit
# address ("The top two bits ... are ignored"), while rt_alert passes the
# #4000-quarter block (bios_getmem1) — data above #7FFF would be read from
# the wrong memory. The M2 limit of 48K rested on an undocumented assumption
# (independent review, D6); 16K is the documented, conservative bound.
PRG_IMAGE_MAX = 0x4000
RUNTIME_MARKER = "; ---- runtime (runtime/runtime.z80.asm) ----"


@dataclass
class BuildReport:
    """Result of one container build: paths, image size and content hash."""

    asm_path: Path
    prg_path: Path
    prg_size: int
    sha256: str
    banked: "codebanks.BankedLayout | None" = None  # M9: set for a code-banked build
    includes: tuple = ()  # M10: "FILE: lines a..b" for each INCLUDEd file


class ImageTooLarge(SourceError):
    """The single-block image is over 16K (M9: ``--code-banks auto`` then
    builds the program with code banks instead)."""


def assemble(
    program_asm: str, runtime_path: Path, asm_path: Path, prg_path: Path, *, prune: bool = True
) -> BuildReport:
    """Concatenate program + runtime, run ``pasmo --bin``, guard the container.

    *prune* (M8, default) leaves the unreachable parts of the REAL library
    out (pbas/prune.py); ``prune=False`` assembles it whole, as M7 did, so
    an M7 executable can be rebuilt byte for byte.

    Raises SourceError (position 1:1 — failures here carry no source node)
    when pasmo fails, the image misses its zero prefix, or it exceeds the
    16K first-bank limit. OSError from unreadable inputs propagates to the CLI.
    """
    runtime_path = Path(runtime_path)
    asm_path = Path(asm_path)
    prg_path = Path(prg_path)
    runtime_text = runtime_path.read_text(encoding="utf-8")
    if prune:
        runtime_text = prune_real(program_asm, runtime_text)  # M8
    # M9: the runtime's code-bank section (IF PB_CODEBANKS) is not assembled.
    asm_path.write_text(program_asm + "PB_CODEBANKS equ 0\n" + "\n" + RUNTIME_MARKER + "\n"
                        + runtime_text, encoding="utf-8")
    proc = subprocess.run(
        ["pasmo", "--bin", str(asm_path), str(prg_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-3:]) or "(no stderr)"
        raise SourceError(1, 1, f"pasmo failed (exit {proc.returncode}): {tail}")
    if not prg_path.is_file():
        raise SourceError(1, 1, f"pasmo produced no output file: {prg_path}")
    image = prg_path.read_bytes()
    if len(image) > PRG_IMAGE_MAX:
        raise ImageTooLarge(
            1,
            1,
            f"assembled image is {len(image)} bytes, over the "
            f"{PRG_IMAGE_MAX}-byte .PRG image limit: the program must fit the "
            "first 16K bank #4000-#7FFF (ROSAN283 'Memory Layout'/'Addressing')",
        )
    if image[:PREFIX_SIZE] != bytes(PREFIX_SIZE):
        raise SourceError(
            1,
            1,
            f"assembled image lacks the {PREFIX_SIZE}-byte zero prefix of the "
            ".PRG container (ARCHITECTURE.md D7/F8)",
        )
    return BuildReport(
        asm_path=asm_path,
        prg_path=prg_path,
        prg_size=len(image),
        sha256=hashlib.sha256(image).hexdigest(),
    )


def build(
    source_path,
    asm_path,
    prg_path,
    *,
    string_capacity: int = DEFAULT_STRING_CAPACITY,
    runtime_path: Path | None = None,
    location: FileLocation | None = None,
    prune: bool = True,
    code_banks: str = "auto",
    code_bank_limit: int = codebanks.BANK_LIMIT,
    runtime_sections=(),
    legacy_menu_hotkeys: bool = False,
    legacy_timing: bool = False,
    legacy_file_safety: bool = False,
    legacy_real_rounding: bool = False,
    legacy_tasks_stop: bool = False,
) -> BuildReport:
    """Compile one ``.pbas`` file end to end: frontend -> generate -> assemble.

    *string_capacity* is the program-wide STRING capacity (spec section 4);
    *runtime_path* overrides the default ``runtime/runtime.z80.asm`` (tests
    pass a stub; production tools pass the shipped runtime). *location* is
    the FILESAVE/FILELOAD drive and folder (``pbas.files.make_location``;
    default floppy ``\\PCW\\FOLDER01``). *prune*: see ``assemble``.
    *code_banks* (M9): ``"never"`` builds one 16K image (an error if it does
    not fit); ``"always"`` puts every SUB and FUNCTION in code banks
    (pbas/codebanks.py); ``"auto"`` (default) builds one image when it fits
    and code banks only when it does not, so every program that fitted
    before builds to exactly the same bytes. *code_bank_limit* caps the
    bytes per bank (pbas.codebanks.pack).

    *runtime_sections* (M11, pbas/rtbank.py): runtime sections whose code
    goes to a code bank of its own, behind resident veneers. A tuple of
    section names (``rtbank.MOVABLE``), ``"all"`` for every movable one, or
    empty (the default: the runtime stays resident, as up to M10). It
    implies code banks.

    *legacy_menu_hotkeys* (M13 corrective): menu items without KEY get the
    hotkey word #0000 they had before, which breaks Rosanne's hotkey search
    (pbas/statements.py NO_HOTKEY). Only to rebuild accepted executables.

    *legacy_timing* (M13 responsiveness): TIMER ... EVERY n TICKS a Rosanne
    timer and CLOCKTICKS the raw ticks byte, as in the M13 corrective builds
    (pbas/statements.py generate_parts). Only to rebuild those byte for byte
    and to reproduce their pauses.

    *legacy_file_safety* (M14): DB SAVE, BITMAP SAVE and DB LOAD as up to
    M13, without the M14 companion check, backup rule and narrower fallback
    (pbas/statements.py generate_parts). Only to rebuild accepted executables.
    *legacy_real_rounding* (M14): REAL + and - rounded as up to M13 (the same).
    *legacy_tasks_stop* (M15): a program with menus and no ON STOP ignores
    Tasks > Stop, as up to RC1. Only to rebuild accepted executables.
    """
    if code_banks not in codebanks.MODES:
        raise ValueError(f"code_banks must be one of {codebanks.MODES}, got {code_banks!r}")
    source_path = Path(source_path)
    tokens, smap = include.expand(source_path.read_text(encoding="utf-8"), source_path,
                                  source_path.name)
    try:
        nodes = Parser(tokens).parse()
        analysis = analyze(nodes, string_capacity=string_capacity)
        program = build_program(nodes, analysis)
        parts = generate_parts(program, location, legacy_menu_hotkeys=legacy_menu_hotkeys,
                               legacy_timing=legacy_timing, legacy_file_safety=legacy_file_safety,
                               legacy_real_rounding=legacy_real_rounding,
                               legacy_tasks_stop=legacy_tasks_stop)
    except SourceError as exc:
        raise smap.translate(exc) from None
    runtime = DEFAULT_RUNTIME_PATH if runtime_path is None else Path(runtime_path)
    if runtime_sections == "all":
        from .rtbank import MOVABLE
        runtime_sections = MOVABLE
    runtime_sections = tuple(runtime_sections or ())
    if runtime_sections and code_banks == "never":
        raise ValueError("runtime_sections needs code banks")
    report = None
    if code_banks != "always" and not runtime_sections:
        try:
            report = assemble(parts.text, runtime, Path(asm_path), Path(prg_path), prune=prune)
        except ImageTooLarge:
            if code_banks == "never" or not parts.spans:
                raise
    if report is None:
        report = assemble_banked(parts, runtime, Path(asm_path), Path(prg_path), prune=prune,
                                 limit=code_bank_limit, runtime_sections=runtime_sections)
    report.includes = tuple(smap.describe())
    return report


def assemble_banked(parts, runtime_path: Path, asm_path: Path, prg_path: Path, *,
                    prune: bool = True, limit: int = codebanks.BANK_LIMIT,
                    runtime_sections: tuple = ()) -> BuildReport:
    """M9: assemble a program with its procedures in code banks."""
    runtime_text = Path(runtime_path).read_text(encoding="utf-8")
    if prune:
        runtime_text = prune_real(parts.text, runtime_text)
    layout = codebanks.build_banked(parts, runtime_text, RUNTIME_MARKER, Path(asm_path),
                                    Path(prg_path), limit, runtime_sections)
    image = Path(prg_path).read_bytes()
    if image[:PREFIX_SIZE] != bytes(PREFIX_SIZE):
        raise SourceError(1, 1, f"assembled image lacks the {PREFIX_SIZE}-byte zero prefix")
    return BuildReport(
        asm_path=Path(asm_path),
        prg_path=Path(prg_path),
        prg_size=len(image),
        sha256=hashlib.sha256(image).hexdigest(),
        banked=layout,
    )
