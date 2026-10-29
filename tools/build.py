"""Build driver: PcW16 BASIC source (.pbas) -> assembly (.asm) -> .PRG.

Thin, scriptable CLI over ``pbas.prg.build`` (ARCHITECTURE.md D2/D7): the
compiler frontend checks the program, the emitter writes program assembly, the
runtime appendix (``runtime/runtime.z80.asm``) is concatenated, Pasmo
assembles the result with ``--bin``, and the 16K image limit is enforced.
This script owns no compiler logic — it resolves output paths, creates output
directories, reports one line per artefact, and maps failures to exit codes.

Usage::

    python3 tools/build.py SOURCE.pbas [--out-dir DIR] [--asm PATH] [--prg PATH]
                           [--string-capacity N] [--code-banks auto|always|never]

Defaults write ``<stem>.asm`` / ``<stem>.prg`` under ``--out-dir build``
(created if missing); ``--asm`` / ``--prg`` override each artefact path
individually. Output (stdout)::

    asm: <path> (<n> bytes)
    prg: <path> (<n> bytes, sha256 <hex>)

Exit status: 0 on success; 1 for any compiler error (reported on stderr as
``<source>:<line>:<column>: <message>``, per LANGUAGE-SPEC.md section 8), for
a missing source file, or when the Pasmo assembler is not on PATH.

The script is runnable from any working directory: the directory containing
the ``pbas`` package (…/PcW16-BASIC) is inserted at ``sys.path[0]`` relative
to this file. ``tools/asmcheck.py`` is the companion static validator and is
kept deliberately separate: this script builds, it does not lint.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow 'import pbas' when invoked as 'python3 tools/build.py' from any cwd:
# put the directory containing the pbas package (…/PcW16-BASIC) at sys.path[0].
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from pbas.errors import SourceError  # noqa: E402
from pbas.rtbank import MOVABLE  # noqa: E402
from pbas.files import (  # noqa: E402
    DEFAULT_DRIVE,
    DEFAULT_FOLDER,
    FileLocationError,
    make_location,
)
from pbas.policy import (  # noqa: E402
    DEFAULT_STRING_CAPACITY,
    MAX_STRING_CAPACITY,
    MIN_STRING_CAPACITY,
)

try:
    from pbas import prg
except ImportError:  # M2 code-generation modules not landed yet (parallel work)
    prg = None


def build_arg_parser() -> argparse.ArgumentParser:
    """Define the build.py command line."""
    parser = argparse.ArgumentParser(
        prog="build.py",
        description="Compile a PcW16 BASIC program to Z80 assembly and a "
        "Rosanne .PRG executable (via pasmo --bin).",
    )
    parser.add_argument(
        "source",
        type=Path,
        metavar="SOURCE.pbas",
        help="UTF-8 .pbas source file",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("build"),
        metavar="DIR",
        help="artefact directory, created if missing (default: %(default)s)",
    )
    parser.add_argument(
        "--asm",
        type=Path,
        default=None,
        metavar="PATH",
        help="assembly output path (default: <out-dir>/<stem>.asm)",
    )
    parser.add_argument(
        "--prg",
        type=Path,
        default=None,
        metavar="PATH",
        help=".PRG output path (default: <out-dir>/<stem>.prg)",
    )
    parser.add_argument(
        "--string-capacity",
        type=int,
        default=DEFAULT_STRING_CAPACITY,
        metavar="N",
        help=(
            "program-wide STRING capacity in bytes including the NUL "
            "(default: %(default)s; range "
            f"{MIN_STRING_CAPACITY}..{MAX_STRING_CAPACITY})"
        ),
    )
    parser.add_argument(
        "--drive",
        default=DEFAULT_DRIVE,
        metavar="DRIVE",
        help="drive for the program's files: floppy (the default; flash is "
        "not supported)",
    )
    parser.add_argument(
        "--folder",
        default=DEFAULT_FOLDER,
        metavar="PATH",
        help="existing folder for FILESAVE/FILELOAD files, e.g. \\PCW\\FOLDER01 "
        "(default: %(default)s); the program never creates it",
    )
    parser.add_argument(
        "--whole-real-library",
        action="store_true",
        help="assemble the REAL library whole instead of only the parts the "
        "program reaches (the default leaves the rest out); only to reproduce "
        "older accepted executables byte for byte",
    )
    parser.add_argument(
        "--legacy-menu-hotkeys",
        action="store_true",
        help="give menu items without KEY the hotkey word 0 older builds had, "
        "which stops Rosanne finding later shortcuts; only to reproduce older "
        "accepted executables byte for byte",
    )
    parser.add_argument(
        "--legacy-timing",
        action="store_true",
        help="TIMER ... EVERY n TICKS a Rosanne timer and CLOCKTICKS the raw "
        "ticks byte, as in older builds (whose timers paused in XAnne); only to "
        "reproduce those executables",
    )
    parser.add_argument(
        "--legacy-file-safety",
        action="store_true",
        help="DB SAVE, BITMAP SAVE and DB LOAD as before M14 (no check of "
        "NAME.NEW / NAME.BAK, a backup deleted on a first save, any failure "
        "falling back to an older copy); only to reproduce older accepted executables",
    )
    parser.add_argument(
        "--legacy-real-rounding",
        action="store_true",
        help="REAL + and - rounded as before M14 (a result just under half a unit "
        "in the last place could round up); only to reproduce older accepted executables",
    )
    parser.add_argument(
        "--legacy-tasks-stop",
        action="store_true",
        help="a program with menus and no ON STOP ignores Rosanne's Tasks > Stop, as "
        "before M15; only to reproduce older accepted executables",
    )
    parser.add_argument(
        "--code-banks",
        choices=("auto", "always", "never"),
        default="auto",
        help="put SUBs and FUNCTIONs in code banks loaded by the program "
        "itself: 'auto' (default) only when the program does not fit one 16K "
        "image, 'always', or 'never' (fail if it does not fit)",
    )
    parser.add_argument(
        "--code-bank-limit",
        type=int,
        default=None,
        metavar="BYTES",
        help="at most BYTES per code bank (default and maximum 15872); a "
        "smaller value spreads a small program over several banks (probes)",
    )
    parser.add_argument(
        "--runtime-banks",
        default="",
        metavar="all|SECTION,...",
        help="move the code of these runtime sections (or 'all' movable ones: "
        + ", ".join(MOVABLE) + ") to a code bank of their own, freeing room in "
        "the resident 16K block; implies code banks (pcw16basic build does this "
        "by itself when a program does not fit)",
    )
    return parser


LOW_HEADROOM = 512  # M11: warn when less of the resident block is left


def build_warnings(source: Path) -> list:
    """M11 Stage D4: pbas.lint findings (never fatal; empty on any problem)."""
    try:
        from pbas import check_source
        from pbas.lint import warnings
        return warnings(check_source(source.read_text(encoding="utf-8"), path=source))
    except Exception:  # noqa: BLE001 - the build itself reports real errors
        return []


def cmd_build(args: argparse.Namespace) -> int:
    """Compile *args.source* to assembly and a .PRG; report artefacts."""
    source: Path = args.source
    if not source.is_file():
        print(f"{source}: no such file", file=sys.stderr)
        return 1
    if prg is None:
        print(
            "build.py: the M2 code-generation modules (pbas.prg) are not "
            "available in this checkout",
            file=sys.stderr,
        )
        return 1
    asm_path = args.asm if args.asm is not None else args.out_dir / f"{source.stem}.asm"
    prg_path = args.prg if args.prg is not None else args.out_dir / f"{source.stem}.prg"
    try:
        location = make_location(args.drive, args.folder)
    except FileLocationError as exc:
        print(f"build.py: {exc}", file=sys.stderr)
        return 1
    for target in {asm_path, prg_path}:
        target.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = prg.build(
            source,
            asm_path,
            prg_path,
            string_capacity=args.string_capacity,
            location=location,
            prune=not args.whole_real_library,
            legacy_menu_hotkeys=args.legacy_menu_hotkeys,
            legacy_timing=args.legacy_timing,
            legacy_file_safety=args.legacy_file_safety,
            legacy_real_rounding=args.legacy_real_rounding,
            legacy_tasks_stop=args.legacy_tasks_stop,
            code_banks=args.code_banks,
            runtime_sections=(args.runtime_banks if args.runtime_banks in ("", "all")
                              else tuple(s.strip().upper() for s in args.runtime_banks.split(","))),
            **({} if args.code_bank_limit is None else {"code_bank_limit": args.code_bank_limit}),
        )
    except SourceError as exc:
        print(exc.where(source), file=sys.stderr)  # M10: an INCLUDEd file's own name and line
        return 1
    except FileNotFoundError:
        # pbas.prg runs pasmo as a subprocess; a missing executable surfaces
        # as FileNotFoundError (per the pbas.prg contract, which wraps all
        # frontend/size/pasmo *failures* in SourceError instead).
        print("pasmo assembler not found on PATH", file=sys.stderr)
        return 1
    except UnicodeError as exc:
        print(f"{source}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"{source}: {exc}", file=sys.stderr)
        return 1
    for line, column, text in build_warnings(source):  # M11 Stage D4
        print(f"{source}:{line}:{column}: warning: {text}", file=sys.stderr)
    print(f"asm: {asm_path} ({asm_path.stat().st_size} bytes)")
    print(f"prg: {prg_path} ({report.prg_size} bytes, sha256 {report.sha256})")
    for part in report.includes:  # M10: runtime error lines of included files
        print(f"included: {part}")
    if report.banked is not None:
        layout = report.banked
        print(f"code banks: {len(layout.banks)} (resident {layout.resident_size} bytes; "
              f"map {asm_path.with_suffix('.map')})")
        if layout.runtime_sections:  # M11
            print(f"runtime bank: {len(layout.banks)} ({' '.join(layout.runtime_sections)}; "
                  f"{len(layout.runtime_entries)} entries)")
    resident = report.banked.resident_size if report.banked is not None else report.prg_size
    if 16384 - resident < LOW_HEADROOM:  # M11 Stage D4
        hint = "" if report.banked is not None and report.banked.runtime_sections else \
            "; --runtime-banks all moves runtime code out of it"
        print(f"{source}: warning: only {16384 - resident} bytes left in the resident 16K "
              f"block{hint} (tools/memreport.py shows where they go)", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the command line and build the requested program."""
    args = build_arg_parser().parse_args(argv)
    return cmd_build(args)


if __name__ == "__main__":
    sys.exit(main())
