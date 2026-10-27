"""Command-line checker for PcW16 BASIC programs.

Usage:
    python3 -m pbas check [--ast] [--symbols] [--string-capacity N] SOURCE.pbas

``check`` runs everything ``build`` does except the assembler: it tokenises,
parses, validates, analyses and lowers the program, lays out its windows and
generates its code, and reports the first error with its source position,
then any warnings. It needs no Pasmo and writes no file. Whether the
program fits the PcW16's 16K resident block is known only when it is
assembled: ``pcw16basic build`` (tools/build.py) does that.
(M14: until M13, check stopped after lowering, so some errors appeared
only at build.)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .errors import SourceError
from .include import expand
from .lexer import tokenize
from .parser import Parser
from .policy import (
    DEFAULT_STRING_CAPACITY,
    MAX_STRING_CAPACITY,
    MIN_STRING_CAPACITY,
)
from .program import build_program
from .semantics import analyze
from .statements import generate_parts


def _string_capacity(text: str) -> int:
    """argparse type for ``--string-capacity``: an int within policy range."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"string capacity must be an integer, got {text!r}"
        ) from None
    if not MIN_STRING_CAPACITY <= value <= MAX_STRING_CAPACITY:
        raise argparse.ArgumentTypeError(
            f"string capacity must be between {MIN_STRING_CAPACITY} "
            f"and {MAX_STRING_CAPACITY}, got {value}"
        )
    return value


def cmd_check(args: argparse.Namespace) -> int:
    """Run the Stage-1 frontend over one source file and report the result."""
    source: Path = args.source
    smap = None
    try:
        tokens, smap = expand(source.read_text(encoding="utf-8"), source, str(source))  # M10 INCLUDE
        nodes = Parser(tokens).parse()
        analysis = analyze(nodes, string_capacity=args.string_capacity)
        # Lowering must also succeed for the program to be considered valid.
        program = build_program(nodes, analysis)
        # M14 (D3): and so must the window layout and code generation, which
        # hold the checks build made that check did not (a WINDOW with no
        # BUTTON, too many buttons, a dialog that overflows, a CANVAS too
        # wide for its window, a TEXTBOX over the string limit). Only what
        # needs the assembler (the 16K fit) is left to build.
        generate_parts(program, None)
        from .lint import warnings as lint_warnings  # M14: the warnings build prints
        found = lint_warnings(program)
    except SourceError as error:
        if smap is not None:
            error = smap.translate(error)
        print(error.where(source), file=sys.stderr)
        return 1
    except OSError as error:
        print(f"{source}:{error}", file=sys.stderr)
        return 1
    for line, column, text in found:  # M14: check reports what build warns about
        print(f"{source}:{line}:{column}: warning: {text}", file=sys.stderr)
    if args.ast:
        print(json.dumps([asdict(node) for node in nodes], indent=2))
    elif args.symbols:
        print(
            json.dumps(
                {name: asdict(var) for name, var in analysis.variables.items()},
                indent=2,
            )
        )
    else:
        print(
            f"OK: {source} ({len(nodes)} statements, "
            f"{len(analysis.variables)} variables); "
            "syntax, type, layout and code checks passed. No PRG generated: "
            "whether it fits the PcW16's memory is checked by build."
        )
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    """Define the ``pbas`` CLI; ``check`` today, open to ``build`` in M2."""
    parser = argparse.ArgumentParser(
        prog="pbas",
        description=(
            "PcW16 BASIC: check a program without building it "
            "(pcw16basic build, or tools/build.py, makes the .PRG)."
        ),
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    check = commands.add_parser(
        "check",
        help="check a .pbas program: syntax, types, layout and code generation "
        "(no .PRG is written; memory fit is checked by build)",
    )
    check.add_argument(
        "source",
        type=Path,
        metavar="SOURCE.pbas",
        help="UTF-8 .pbas source file",
    )
    check.add_argument(
        "--ast",
        action="store_true",
        help="print the flat parsed AST (dataclasses.asdict) as JSON",
    )
    check.add_argument(
        "--symbols",
        action="store_true",
        help="print the analysed variable table (name -> attributes) as JSON",
    )
    check.add_argument(
        "--string-capacity",
        type=_string_capacity,
        default=DEFAULT_STRING_CAPACITY,
        metavar="N",
        help=(
            "program-wide STRING capacity in bytes including the NUL "
            "(default: %(default)s; range "
            f"{MIN_STRING_CAPACITY}..{MAX_STRING_CAPACITY})"
        ),
    )
    check.set_defaults(func=cmd_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse the command line and dispatch to the selected subcommand."""
    args = build_arg_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
