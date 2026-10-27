"""PcW16 BASIC production compiler — milestones M1 (frontend) + M2 (codegen).

Tokenise, parse, structurally validate, analyse and lower ``.pbas`` source
into a typed, source-positioned AST and the structured ``Program`` model
(M1), then emit Z80 assembly and assemble a Rosanne ``.prg`` image via Pasmo
(M2). Generated code calls the hand-written runtime (``runtime/runtime.z80.asm``)
through ``rt_*`` entry points; it never touches the OS directly
(ARCHITECTURE.md D2).

Typical use::

    from pbas import check_source, build, SourceError
    program = check_source(text)          # frontend gate, raises SourceError
    report = build("game.pbas", "game.asm", "game.prg")   # full toolchain
"""
from __future__ import annotations

from .errors import SourceError
from .lexer import Token, tokenize
from .parser import Parser, parse, validate
from .policy import DEFAULT_STRING_CAPACITY
from .prg import PREFIX_SIZE, PRG_IMAGE_MAX, BuildReport, assemble, build
from .program import (
    Binding,
    BodyItem,
    ForBlock,
    Handler,
    IfBlock,
    Procedure,
    Program,
    SimpleStatement,
    WhileBlock,
    Widget,
    build_program,
)
from .semantics import Analysis, Variable, analyze, dynamic_message_budget
from .statements import generate

__version__ = "1.0.0-m2"

__all__ = [
    "Analysis",
    "Binding",
    "BodyItem",
    "BuildReport",
    "DEFAULT_STRING_CAPACITY",
    "ForBlock",
    "Handler",
    "IfBlock",
    "PRG_IMAGE_MAX",
    "PREFIX_SIZE",
    "Parser",
    "Procedure",
    "Program",
    "SimpleStatement",
    "SourceError",
    "Token",
    "Variable",
    "WhileBlock",
    "Widget",
    "analyze",
    "assemble",
    "build",
    "build_program",
    "check_source",
    "dynamic_message_budget",
    "generate",
    "parse",
    "tokenize",
    "validate",
]


def check_source(text: str, *, string_capacity: int = DEFAULT_STRING_CAPACITY,
                 path=None) -> Program:
    """Run the full Stage-1 frontend over *text* and return the lowered Program.

    Raises SourceError (with 1-based line/column) on the first lexical,
    syntactic or semantic problem. This is the single entry point the tests
    and the ``pbas check`` CLI use; M2 adds codegen on top of the same model.
    M10: INCLUDE files are read relative to *path*'s folder (the current
    folder if *path* is None); an error in one has ``file`` set.
    """
    from pathlib import Path
    from .include import expand
    tokens, smap = expand(text, None if path is None else Path(path),
                          "<source>" if path is None else Path(path).name)
    try:
        nodes = Parser(tokens).parse()
        analysis = analyze(nodes, string_capacity=string_capacity)
        return build_program(nodes, analysis)
    except SourceError as exc:
        raise smap.translate(exc) from None
