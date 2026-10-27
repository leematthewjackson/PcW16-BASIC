"""M10 Stage D3: INCLUDE "file" (LANGUAGE-SPEC §5.11).

``INCLUDE "LIB.PBAS"`` on a line of its own is replaced by the tokens of that
file, read relative to the folder of the file that includes it. Inclusion is
textual (the included text is compiled as if it were written there), so the
language rules decide what a library may hold; a library is normally TYPEs,
CONSTs, DIMs and SUB / FUNCTION definitions.

Line numbers: the main file keeps its own; included file k (in the order
the INCLUDE lines are reached) is numbered from 1000 * (b + k) + 1, where
1000 * b is the first multiple of 1000 above the main file's last line. So
line 45 of the first library of a 480-line program is program line 1045 in
compile errors that the build has not mapped back, in runtime error
reports ("at line 1045") and in the generated assembly's comments. Compile
errors are mapped back to the file and its own line (SourceError.file).

Rules (compile errors): the file must exist and be UTF-8 text with fewer
than 1000 lines; the same file may be included only once (also prevents
cycles); an included file may not have BASIC line numbers; at most the
included files whose numbers stay below 32768.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .errors import SourceError
from .lexer import Token, tokenize

BLOCK = 1000
LINE_MAX = 32767


@dataclass
class SourceMap:
    """The files of one program and where their lines are numbered."""
    main: str
    main_lines: int
    parts: list[tuple[int, str]] = field(default_factory=list)  # (base, display name)

    def locate(self, line: int) -> tuple[str, int]:
        for base, name in reversed(self.parts):
            if line > base:
                return name, line - base
        return self.main, line

    def describe(self) -> list[str]:
        return [f"{name}: lines {base + 1}..{base + BLOCK - 1}" for base, name in self.parts]

    def translate(self, exc: SourceError) -> SourceError:
        """*exc* with its line mapped to its own file (``exc.file``)."""
        name, line = self.locate(exc.line)
        if name == self.main and getattr(exc, "file", None) is None:
            return exc
        out = SourceError(line, exc.column, exc.message)
        out.file = name
        return out


def _include_target(tokens: list[Token], i: int) -> Token | None:
    """The STRING token if tokens[i:] start an ``INCLUDE "file"`` line."""
    first = tokens[i]
    if first.kind != "IDENT" or first.value.upper() != "INCLUDE":
        return None
    if i > 0 and tokens[i - 1].kind not in ("NEWLINE", "LINENO"):
        return None
    if i + 1 >= len(tokens) or tokens[i + 1].kind != "STRING":
        return None
    if i + 2 < len(tokens) and tokens[i + 2].kind not in ("NEWLINE", "EOF"):
        return None
    return tokens[i + 1]


def expand(text: str, path: Path | None, name: str = "<source>") -> tuple[list[Token], SourceMap]:
    """Tokenize *text* (the program, from *path* if it has one) with every
    INCLUDE line replaced by its file's tokens."""
    lines = len(text.splitlines())
    smap = SourceMap(name, lines)
    if "INCLUDE" not in text.upper():
        return tokenize(text), smap
    folder = path.resolve().parent if path is not None else Path.cwd()
    seen: dict[Path, tuple[str, int]] = {}
    if path is not None:
        seen[path.resolve()] = (name, 0)
    next_base = [-(-(lines + 1) // BLOCK) * BLOCK]

    def splice(tokens: list[Token], here: Path, base: int, who: str) -> list[Token]:
        out: list[Token] = []
        i = 0
        while i < len(tokens):
            target = _include_target(tokens, i)
            if target is None:
                out.append(tokens[i])
                i += 1
                continue
            at = tokens[i]
            if not target.value:
                raise SourceError(at.line, at.column, "INCLUDE needs a file name")
            file = (here / target.value).resolve()
            if file in seen:
                first_name, first_line = seen[file]
                raise SourceError(at.line, at.column,
                                  f'INCLUDE "{target.value}": that file is already part of the program'
                                  + (f" (included at line {first_line})" if first_line else " (it is the program itself)"))
            try:
                data = file.read_text(encoding="utf-8")
            except FileNotFoundError:
                raise SourceError(at.line, at.column, f'INCLUDE "{target.value}": no such file') from None
            except (OSError, UnicodeError) as exc:
                raise SourceError(at.line, at.column, f'INCLUDE "{target.value}": {exc}') from None
            count = len(data.splitlines())
            if count >= BLOCK:
                raise SourceError(at.line, at.column,
                                  f'INCLUDE "{target.value}": an included file has fewer than {BLOCK} lines '
                                  f"(it has {count})")
            sub_base = next_base[0]
            if sub_base + BLOCK - 1 > LINE_MAX:
                raise SourceError(at.line, at.column,
                                  f'INCLUDE "{target.value}": too many included files (program lines '
                                  f"stop at {LINE_MAX})")
            next_base[0] += BLOCK
            try:  # shown relative to the program's own folder
                display = file.relative_to(folder).as_posix()
            except ValueError:
                display = str(file)
            seen[file] = (display, at.line)
            smap.parts.append((sub_base, display))
            sub = tokenize(data)
            for t in sub:
                if t.kind == "LINENO":
                    raise SourceError(sub_base + t.line, t.column,
                                      "an included file may not have BASIC line numbers")
                t.line += sub_base
            sub = [t for t in sub if t.kind != "EOF"]
            if sub and sub[-1].kind != "NEWLINE":
                last = sub[-1]
                sub.append(Token("NEWLINE", "\n", last.line, last.column + len(last.value)))
            out.extend(splice(sub, file.parent, sub_base, display))
            i += 2
            if i < len(tokens) and tokens[i].kind == "NEWLINE":
                i += 1  # the INCLUDE line's own end (the file brought its own)
        return out

    try:
        return splice(tokenize(text), folder, 0, name), smap
    except SourceError as exc:  # a problem inside an included file: its own name and line
        raise smap.translate(exc) from None
