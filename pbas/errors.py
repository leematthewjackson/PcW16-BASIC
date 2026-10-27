"""Source-positioned compiler diagnostics.

Every lexer, parser, semantic and (in later milestones) codegen failure is a
SourceError carrying 1-based line/column and a message stating the rule
violated (LANGUAGE-SPEC.md section 8).
"""
from __future__ import annotations


class SourceError(ValueError):
    # M10 INCLUDE: the included file the position is in (None: the program's
    # own file); set by pbas.include.SourceMap.translate.
    file: str | None = None

    def __init__(self, line: int, column: int, message: str):
        super().__init__(f"{line}:{column}: {message}")
        self.line = line
        self.column = column
        self.message = message

    def where(self, source) -> str:
        """``source:line:column: message`` (the included file's name if any)."""
        return f"{self.file or source}:{self.line}:{self.column}: {self.message}"
