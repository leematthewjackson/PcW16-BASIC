"""PcW16 BASIC Stage-1 lexer (LANGUAGE-SPEC.md section 1).

Port of the proven POC tokenizer with the spec-mandated fixes:

- a whole-word ``REM`` discards the rest of the line *without* emitting a
  token, so full-line and trailing REM comments both work (the POC emitted a
  REM token the parser then rejected); ``REMARK``/``REMAIN$`` are ordinary
  identifiers;
- a non-ASCII letter that the identifier regex cannot match raises
  ``unexpected character`` at that column instead of the POC's AttributeError
  crash;
- a line number may end the line (``10`` alone is a numbered blank line) via
  ``(?:\\s+|$)`` instead of the POC's mandatory trailing whitespace.

Keywords become token kinds, upper-cased; identifier/keyword tokens keep the
original source spelling as their value. Every token carries 1-based line and
column; each source line ends with a NEWLINE token and the stream ends with
an EOF token.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .errors import SourceError

KEYWORDS = {
    'WINDOW', 'LABEL', 'TEXTBOX', 'CHECKBOX', 'BUTTON', 'SUB', 'END', 'DIM',
    'AS', 'INTEGER', 'STRING', 'BOOLEAN', 'IF', 'THEN', 'ELSE', 'PRINT',
    'MESSAGE', 'REM', 'TRUE', 'FALSE', 'GOTO', 'EXIT', 'FOR', 'TO', 'NEXT',
    'STEP', 'WHILE', 'WEND', 'FILESAVE', 'FILELOAD',
    'CALL',  # M5c
}
# M6 Phase 1 statement words are *contextual*, not reserved: pbas.parser
# treats an identifier from this set as a statement only at the start of a
# statement and not followed by '=', so older programs that use these names
# for variables or SUBs (e.g. SUB Show) compile unchanged.
CONTEXT_WORDS = {'RADIO', 'NUMBERBOX', 'BEEP', 'FOCUS', 'SHOW', 'MENU', 'ITEM', 'TIMER',
                 'LIST', 'CHOICE', 'SLIDER',  # M6 Phase 2
                 'FUNCTION', 'RETURN', 'LOCAL', 'CONST', 'SELECT', 'CASE', 'RANDOMIZE',  # M7
                 'CANVAS', 'DRAW', 'TEXT',  # M9
                 'TYPE', 'DB',  # M10
                 'BITMAP'}  # M12
# M5b: MOD; M5c: AND, OR, NOT. Reserved; tokenised as operators.
WORD_OPERATORS = {'MOD', 'AND', 'OR', 'NOT', 'XOR'}  # XOR: M7
TWO_CHAR = {'<=', '>=', '<>', '=='}
SINGLE = set('+-*/=(),<>#^')  # '#': M7 file channels, '^': M7 power

_IDENT_RE = re.compile(r'[A-Za-z_][A-Za-z_0-9]*\$?')
_LINENO_RE = re.compile(r'\s*(\d+)(?:\s+|$)')
_NUMBER_RE = re.compile(r'\d+')
# M7 REAL literals: a decimal point and/or an exponent (1.5, .5, 2., 1E-3)
_REAL_RE = re.compile(r'(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+')


@dataclass
class Token:
    kind: str
    value: str
    line: int
    column: int


def tokenize(text: str) -> list[Token]:
    """Split *text* into tokens, raising SourceError on the first bad character.

    Positions are 1-based. A line number at the start of a line becomes a
    LINENO token (metadata only; the parser enforces strictly increasing
    numbers). ``'`` and whole-word ``REM`` comments emit no tokens. M14: a
    UTF-8 byte-order mark at the very start (some editors write one) is ignored.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    tokens: list[Token] = []
    lines = text.splitlines()
    for ln, raw in enumerate(lines, 1):
        i = 0
        lineno = _LINENO_RE.match(raw)
        if lineno:
            tokens.append(Token('LINENO', lineno.group(1), ln, lineno.start(1) + 1))
            i = lineno.end()
        while i < len(raw):
            ch = raw[i]
            if ch.isspace():
                i += 1
                continue
            if ch == "'":
                break
            if ch == '"':
                start = i
                value, i = _read_string(raw, i, ln)
                tokens.append(Token('STRING', value, ln, start + 1))
                continue
            if ch == '.' and i + 1 < len(raw) and (raw[i + 1].isalpha() or raw[i + 1] == '_'):
                # M10: a record field, `Person.Name` (a '.' before a digit is a REAL)
                tokens.append(Token('OP', '.', ln, i + 1))
                i += 1
                continue
            real = _REAL_RE.match(raw, i) if (ch.isdigit() or ch == '.') else None
            if real is not None:
                tokens.append(Token('REALNUM', real.group(), ln, i + 1))
                i = real.end()
                continue
            if ch.isdigit():
                number = _NUMBER_RE.match(raw, i)
                tokens.append(Token('NUMBER', number.group(), ln, i + 1))
                i = number.end()
                continue
            if ch.isalpha() or ch == '_':
                ident = _IDENT_RE.match(raw, i)
                if ident is None:
                    raise SourceError(ln, i + 1, f'unexpected character {ch!r}')
                word = ident.group()
                if word.upper() == 'REM':
                    break
                if word.upper() in WORD_OPERATORS:
                    # M5b/M5c: MOD, AND, OR, NOT are operators (OP tokens), not names.
                    tokens.append(Token('OP', word.upper(), ln, i + 1))
                else:
                    kind = word.upper() if word.upper() in KEYWORDS else 'IDENT'
                    tokens.append(Token(kind, word, ln, i + 1))
                i = ident.end()
                continue
            if raw[i:i + 2] in TWO_CHAR:
                tokens.append(Token('OP', raw[i:i + 2], ln, i + 1))
                i += 2
                continue
            if ch in SINGLE:
                tokens.append(Token('OP', ch, ln, i + 1))
                i += 1
                continue
            raise SourceError(ln, i + 1, f'unexpected character {ch!r}')
        tokens.append(Token('NEWLINE', '', ln, len(raw) + 1))
    tokens.append(Token('EOF', '', len(lines) + 1, 1))
    return tokens


def _read_string(raw: str, start: int, ln: int) -> tuple[str, int]:
    """Read a "..." string at *start*; return (value, index past closing quote).

    ``""`` escapes one literal quote. A line ending before the closing quote
    is an ``unterminated string`` error at the opening quote's position.
    """
    out: list[str] = []
    i = start + 1
    while i < len(raw):
        if raw[i] == '"':
            if i + 1 < len(raw) and raw[i + 1] == '"':
                out.append('"')
                i += 2
                continue
            return ''.join(out), i + 1
        out.append(raw[i])
        i += 1
    raise SourceError(ln, start + 1, 'unterminated string')
