"""PcW16 BASIC Stage-1 parser: flat typed AST plus structural validation.

Port of the proven POC Pratt parser and statement dispatcher (ARCHITECTURE.md
D8), emitting the typed dataclasses from ``pbas.ast_nodes``. The statement
list is *flat*: block constructs are marker statements (If/Else/EndIf,
While/Wend, For/Next, Sub/EndSub) whose nesting ``validate`` checks after the
parse, exactly as in the POC.

Differences from the POC, per LANGUAGE-SPEC.md:

- a unary ``+``/``-`` applied directly to an integer literal folds into one
  signed IntLiteral, so ``-32768`` is a single literal (spec section 2);
  out-of-range magnitudes are parser errors. ``-X`` stays ``Unary`` and the
  outer sign of ``--5`` never re-folds;
- declarations (WINDOW/LABEL/TEXTBOX/CHECKBOX/BUTTON) inside any open block
  are rejected: they are only allowed at the top level;
- diagnostic columns always come from the offending node or token;
- expressions deeper than ``MAX_EXPRESSION_DEPTH`` and blocks nested deeper
  than ``MAX_BLOCK_DEPTH`` are positioned errors (M2.1, D7) instead of a
  Python RecursionError later in the pipeline.
"""
from __future__ import annotations

from .ast_nodes import (
    Assign,
    AssignIndex,
    Beep,
    Binary,
    BoolLiteral,
    Button,
    Call,
    CallSub,
    Checkbox,
    Dim,
    Else,
    EndIf,
    EndMenu,
    EndProgram,
    EndSub,
    Exit,
    Expr,
    Filesave,
    Fileload,
    Focus,
    For,
    If,
    IntLiteral,
    RealLiteral,
    Item,
    Label,
    ListCtl,
    Local,
    Menu,
    Message,
    Next,
    Numberbox,
    Print,
    Radio,
    Show,
    Slider,
    Stmt,
    Canvas,
    Draw,
    TextOp,
    BitmapOp,
    PageOp,
    Case,
    CaseItem,
    Const,
    EndFunction,
    EndSelect,
    ExitLoop,
    FunctionDef,
    Param,
    Randomize,
    Return,
    OpenFile,
    CloseFile,
    PrintFile,
    LineInput,
    Kill,
    NameFile,
    SelectCase,
    StrLiteral,
    Sub,
    Textbox,
    DbOp,
    TypeDef,
    TypeField,
    Timer,
    TimerSwitch,
    Unary,
    Var,
    Wend,
    While,
    Window,
)
from .errors import SourceError
from .lower import lower
from .lexer import CONTEXT_WORDS, Token, tokenize
from .policy import MAX_BLOCK_DEPTH, MAX_CALL_DEPTH, MAX_EXPRESSION_DEPTH

# M5c: OR 4 < AND 6 < NOT (prefix, operand parsed at _NOT_OPERAND) < comparisons.
_PRECEDENCE = {
    'XOR': 3, 'OR': 4, 'AND': 6,  # M7: XOR binds loosest (QBasic order)
    '=': 10, '==': 10, '<>': 10, '<': 10, '>': 10, '<=': 10, '>=': 10,
    '+': 20, '-': 20, '*': 30, '/': 30, 'MOD': 30,
    '^': 35,  # M7: power, tighter than * and /, looser than unary minus
}
# NOT's operand includes comparisons but stops at AND/OR: NOT A = B AND C
# is (NOT (A = B)) AND C (LANGUAGE-SPEC section 3).
_NOT_OPERAND = 8

_DECLARATIONS = {
    Window: 'WINDOW',
    Label: 'LABEL',
    Textbox: 'TEXTBOX',
    Checkbox: 'CHECKBOX',
    Button: 'BUTTON',
    Radio: 'RADIO',  # M6 Phase 1
    Numberbox: 'NUMBERBOX',
    Menu: 'MENU',
    Timer: 'TIMER',
    ListCtl: 'LIST/CHOICE',  # M6 Phase 2
    Slider: 'SLIDER',
    Canvas: 'CANVAS',  # M9
    TypeDef: 'TYPE',  # M10
}
# M9: DRAW operations and how many arguments each takes.
DRAW_ARITY = {'CLEAR': (0,), 'FILL': (4, 5), 'INVERT': (4,), 'BOX': (4,), 'LINE': (4,),
              'PIXEL': (2,), 'TEXT': (3, 4), 'SCROLL': (6,), 'INK': (0,)}  # M11: TEXT ..., cell
DRAW_INKS = ('BLACK', 'WHITE', 'XOR')
# M9 Stage C: TEXT operations and how many arguments follow the buffer.
TEXT_ARITY = {'LOAD': 1, 'SAVE': 1, 'CLEAR': 0, 'INSERT': 3, 'DELETE': 3, 'SPLIT': 2, 'JOIN': 1,
              'REMOVE': 4, 'COPY': (1, 5), 'PASTE': 3}  # M10: ranges and two buffers
# M10: DB operations -> (expressions before the field, takes a field, expressions after it)
DB_SHAPES = {'LOAD': (2, False, 0), 'SAVE': (2, False, 0), 'NEW': (1, False, 0), 'DELETE': (2, False, 0),
             'SORT': (2, True, 0), 'SEARCH': (3, True, 1)}
DB_FLAGS = {'SORT': ('DESC', 'NOCASE', 'KEEP'), 'SEARCH': ('NOCASE',)}
# M6: KEY names a BUTTON may take (CONSTBIO.Z80 key codes).
BUTTON_KEYS = ('GREEN', 'RED', 'BLUE', 'YELLOW', 'STOP', 'HELP',
               'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8')


# M12 printing: PAGE operations and their argument counts
PAGE_ARITY = {'NEW': (0,), 'FONT': (1,), 'TEXT': (3,), 'LINE': (4, 5), 'BOX': (4,), 'FILL': (4,),
              'PRINT': (0,), 'CLOSE': (0,)}


class Parser:
    """Statement and expression parser over a ``tokenize``d source."""

    def __init__(self, tokens: list[Token]):
        self.ts = tokens
        self.i = 0
        self._nesting = 0  # active expression() recursion levels

    def cur(self) -> Token:
        return self.ts[self.i]

    def pop(self) -> Token:
        token = self.ts[self.i]
        self.i += 1
        return token

    def accept(self, kind: str, value: str | None = None) -> Token | None:
        token = self.cur()
        if token.kind == kind and (value is None or token.value.upper() == value):
            return self.pop()
        return None

    def expect(self, kind: str, value: str | None = None) -> Token:
        token = self.accept(kind, value)
        if token is None:
            got = self.cur()
            raise SourceError(
                got.line,
                got.column,
                f'expected {value or kind}, got {got.value or got.kind}',
            )
        return token

    def _size(self, what: str) -> Token:
        """M14 (D11): a size in a declaration is a whole-number literal; say so (it said
        "expected NUMBER, got N" for a CONST or a variable)."""
        if self.cur().kind != 'NUMBER':
            got = self.cur()
            raise SourceError(got.line, got.column,
                              f'{what} is a whole number written in the program (a literal such as 10); '
                              f'got {got.value or got.kind} (a CONST or a variable cannot be used here)')
        return self.expect('NUMBER')

    def expression(self, minprec: int = 0) -> Expr:
        """Pratt expression parser; comparisons 10, additive 20, mul 30."""
        return self._expression(minprec)[0]

    def _too_deep(self, token: Token) -> SourceError:
        return SourceError(
            token.line,
            token.column,
            f'expression is nested more than {MAX_EXPRESSION_DEPTH} levels deep '
            '(operators, parentheses or calls); split it across statements',
        )

    def _expression(self, minprec: int) -> tuple[Expr, int]:
        """Parse one expression; return it with its tree depth.

        Depth counts the nodes on the longest root-to-leaf path. Both the
        parser's own recursion (parentheses, unary chains, call arguments)
        and the resulting tree depth (which later passes recurse over) are
        bounded by MAX_EXPRESSION_DEPTH.
        """
        if self._nesting >= MAX_EXPRESSION_DEPTH:
            raise self._too_deep(self.cur())
        self._nesting += 1
        try:
            return self._expression_body(minprec)
        finally:
            self._nesting -= 1

    def _expression_body(self, minprec: int) -> tuple[Expr, int]:
        token = self.pop()
        depth = 1
        if token.kind == 'STRING':
            left: Expr = StrLiteral(token.line, token.column, token.value)
        elif token.kind == 'NUMBER':
            value = int(token.value)
            if value > 32767:
                raise SourceError(
                    token.line,
                    token.column,
                    f'integer literal {value} is outside the range 0..32767',
                )
            left = IntLiteral(token.line, token.column, value)
        elif token.kind == 'REALNUM':  # M7
            left = _real_literal(token, token.value)
        elif token.kind in ('TRUE', 'FALSE'):
            left = BoolLiteral(token.line, token.column, token.kind == 'TRUE')
        elif token.kind == 'IDENT':
            if self.accept('OP', '('):
                args: list[Expr] = []
                if not self.accept('OP', ')'):
                    arg, arg_depth = self._expression(0)
                    args.append(arg)
                    depth = max(depth, arg_depth + 1)
                    while self.accept('OP', ','):
                        arg, arg_depth = self._expression(0)
                        args.append(arg)
                        depth = max(depth, arg_depth + 1)
                    self.expect('OP', ')')
                left = Call(token.line, token.column, self._field_name(token.value.upper()), args)
            else:
                left = Var(token.line, token.column, self._field_name(token.value.upper()))
        elif token.kind == 'OP' and token.value in ('+', '-'):
            left, depth = self._unary(token)
        elif token.kind == 'OP' and token.value == 'NOT':
            operand, depth = self._expression(_NOT_OPERAND)
            left = Unary(token.line, token.column, 'NOT', operand)
            depth += 1
        elif token.kind == 'OP' and token.value == '(':
            left, depth = self._expression(0)
            self.expect('OP', ')')
        else:
            raise SourceError(token.line, token.column, 'expected expression')
        if depth > MAX_EXPRESSION_DEPTH:
            raise self._too_deep(token)
        while (
            self.cur().kind == 'OP'
            and self.cur().value in _PRECEDENCE
            and _PRECEDENCE[self.cur().value] >= minprec
        ):
            op = self.pop()
            right, right_depth = self._expression(_PRECEDENCE[op.value] + 1)
            left = Binary(op.line, op.column, op.value, left, right)
            depth = max(depth, right_depth) + 1
            if depth > MAX_EXPRESSION_DEPTH:
                raise self._too_deep(op)
        return left, depth

    def _unary(self, token: Token) -> tuple[Expr, int]:
        """Unary +/-; a directly following literal folds into a signed one.

        Only a NUMBER token immediately after the sign folds, so ``--5`` is
        Unary('-', IntLiteral(-5)) — the inner sign folds, the outer does not
        re-fold (LANGUAGE-SPEC.md section 2).
        """
        following = self.cur()
        # M7: -2^2 is -(2^2), as in QBasic: a literal followed by ^ is not
        # folded, and the operand of a sign may contain ^ (precedence 35).
        power_next = (self.i + 1 < len(self.ts)
                      and self.ts[self.i + 1].kind == 'OP' and self.ts[self.i + 1].value == '^')
        if following.kind == 'REALNUM' and not power_next:  # M7: a signed REAL literal
            self.pop()
            return _real_literal(token, ('-' if token.value == '-' else '') + following.value), 1
        if following.kind != 'NUMBER' or power_next:
            operand, depth = self._expression(35)
            return Unary(token.line, token.column, token.value, operand), depth + 1
        self.pop()
        magnitude = int(following.value)
        if token.value == '-':
            if magnitude > 32768:
                raise SourceError(
                    following.line,
                    following.column,
                    f'integer literal -{magnitude} is outside the range '
                    '-32768..32767',
                )
            return IntLiteral(token.line, token.column, -magnitude), 1
        if magnitude > 32767:
            raise SourceError(
                following.line,
                following.column,
                f'integer literal {magnitude} is outside the range 0..32767',
            )
        return IntLiteral(token.line, token.column, magnitude), 1

    def _page(self, token) -> Stmt:
        """M12 PAGE op [arguments] (LANGUAGE-SPEC §5.13)."""
        word = self.pop()
        op = word.value.upper()
        node = PageOp(token.line, token.column, op)
        if self.cur().kind != 'NEWLINE':
            node.values.append(self.expression())
            while self.accept('OP', ','):
                if op == 'FONT' and self.cur().kind == 'IDENT' and self.cur().value.upper() == 'BOLD':
                    self.pop()
                    node.bold = True
                    break
                node.values.append(self.expression())
        if len(node.values) not in PAGE_ARITY[op]:
            want = ' or '.join(str(n) for n in PAGE_ARITY[op])
            raise SourceError(token.line, token.column,
                              f'PAGE {op} takes {want} argument{"" if want == "1" else "s"}, got {len(node.values)}')
        self.expect('NEWLINE')
        return node

    def statement(self) -> Stmt:
        """Parse one statement; the terminating NEWLINE is consumed."""
        token = self.pop()
        kind = token.kind
        if (kind == 'IDENT' and token.value.upper() == 'PAGE'
                and self.cur().value.upper() in PAGE_ARITY):
            return self._page(token)  # M12: PAGE is a statement word only before its operations
        if (kind == 'IDENT' and token.value.upper() in CONTEXT_WORDS
                and not (self.cur().kind == 'OP' and self.cur().value in ('=', '.'))):
            kind = token.value.upper()  # M6 contextual statement word
        elif kind == 'IDENT' and self._file_statement(token.value.upper()):
            kind = 'M7FILE:' + token.value.upper()  # M7 file statement word
        if kind == 'WINDOW':
            name = None
            following = self.ts[self.i + 1] if self.i + 1 < len(self.ts) else None
            if (self.cur().kind == 'IDENT' and following is not None
                    and following.kind == 'OP' and following.value == ','):
                name = self.pop().value.upper()  # M6: WINDOW Name, "title"
                self.expect('OP', ',')
            value = self.expression()
            large = False
            if self.accept('OP', ','):
                self._word('LARGE')
                large = True
            node: Stmt = Window(token.line, token.column, value, name, large)
        elif kind in ('LABEL', 'MESSAGE', 'PRINT') and not (
                kind == 'PRINT' and self.cur().kind == 'OP' and self.cur().value == '#'):
            value = self.expression()
            if kind == 'LABEL':
                node = Label(token.line, token.column, value)
            elif kind == 'MESSAGE':
                node = Message(token.line, token.column, value)
            else:
                node = Print(token.line, token.column, value)
        elif kind in ('TEXTBOX', 'CHECKBOX'):
            name = self.expect('IDENT')
            caption = self.expression() if self.accept('OP', ',') else None
            cls = Textbox if kind == 'TEXTBOX' else Checkbox
            node = cls(token.line, token.column, name.value.upper(), caption)
        elif kind == 'BUTTON':
            caption = self.expression()
            self.expect('OP', ',')
            handler = self.expect('IDENT')
            default = False
            keys: list[str] = []
            while self.accept('OP', ','):  # M5d: DEFAULT; M6: KEY k
                word = self.expect('IDENT')
                upper = word.value.upper()
                if upper == 'DEFAULT' and not default and not keys:
                    default = True
                elif upper == 'KEY':
                    key = self.expect('IDENT')
                    if key.value.upper() not in BUTTON_KEYS:
                        raise SourceError(
                            key.line, key.column,
                            f'unknown key {key.value}; a BUTTON KEY is one of '
                            + ', '.join(BUTTON_KEYS),
                        )
                    keys.append(key.value.upper())
                else:
                    raise SourceError(
                        word.line, word.column,
                        f'expected DEFAULT or KEY, got {word.value}',
                    )
            node = Button(
                token.line, token.column, caption, handler.value.upper(), default, keys
            )
        elif kind == 'RADIO':  # M6
            name = self.expect('IDENT')
            captions = []
            while self.accept('OP', ','):
                captions.append(self.expression())
            node = Radio(token.line, token.column, name.value.upper(), captions)
        elif kind == 'NUMBERBOX':  # M6
            name = self.expect('IDENT')
            box = Numberbox(token.line, token.column, name.value.upper())
            first = True
            while self.accept('OP', ','):
                if first and self.cur().kind == 'STRING':
                    box.caption = self.expression()
                    first = False
                    continue
                first = False
                word = self.expect('IDENT')
                upper = word.value.upper()
                if upper in ('MIN', 'MAX') and getattr(box, 'low' if upper == 'MIN' else 'high') is None:
                    value = self._int_literal()
                    if upper == 'MIN':
                        box.low = value
                    else:
                        box.high = value
                elif upper == 'SPIN' and not box.spin:
                    box.spin = True
                else:
                    raise SourceError(
                        word.line, word.column,
                        f'expected MIN, MAX or SPIN (each at most once), got {word.value}',
                    )
            node = box
        elif kind in ('LIST', 'CHOICE'):  # M6 Phase 2
            name = self.expect('IDENT').value.upper()
            self.expect('OP', ',')
            items = self.expect('IDENT').value.upper()
            self.expect('OP', ',')
            count = self.expression()
            node = ListCtl(token.line, token.column, kind, name, items, count)
            seen: set[str] = set()
            while self.accept('OP', ','):
                if kind == 'CHOICE' and self.cur().kind == 'STRING' and 'caption' not in seen:
                    node.caption = self.expression()
                    seen.add('caption')
                    continue
                word = self.expect('IDENT')
                upper = word.value.upper()
                allowed = ('ROWS', 'CHANGE', 'ACTION') if kind == 'LIST' else ('CHANGE',)
                if upper not in allowed or upper in seen:
                    raise SourceError(word.line, word.column,
                                      f'expected {" or ".join(allowed)} (each at most once), got {word.value}')
                seen.add(upper)
                if upper == 'ROWS':
                    node.rows = self._int_literal()
                elif upper == 'CHANGE':
                    node.change = self.expect('IDENT').value.upper()
                else:
                    node.action = self.expect('IDENT').value.upper()
        elif kind == 'SLIDER':  # M6 Phase 2
            name = self.expect('IDENT').value.upper()
            self.expect('OP', ',')
            self._word('MIN')
            low = self._int_literal()
            self.expect('OP', ',')
            self._word('MAX')
            high = self._int_literal()
            node = Slider(token.line, token.column, name, low, high)
            seen = set()
            while self.accept('OP', ','):
                if self.cur().kind == 'STRING' and 'caption' not in seen:
                    node.caption = self.expression()
                    seen.add('caption')
                    continue
                word = self.expect('IDENT')
                if word.value.upper() != 'CHANGE' or 'CHANGE' in seen:
                    raise SourceError(word.line, word.column, f'expected CHANGE, got {word.value}')
                seen.add('CHANGE')
                node.change = self.expect('IDENT').value.upper()
        elif kind == 'CANVAS':  # M9
            width = self._int_literal()
            self.expect('OP', ',')
            height = self._int_literal()
            node = Canvas(token.line, token.column, width, height)
            while self.accept('OP', ','):
                word = self.expect('IDENT')
                upper = word.value.upper()
                if upper not in ('PAINT', 'MOUSE', 'KEYS') or getattr(node, upper.lower()) is not None:
                    raise SourceError(word.line, word.column,
                                      f'expected PAINT, MOUSE or KEYS (each at most once), got {word.value}')
                setattr(node, upper.lower(), self.expect('IDENT').value.upper())
        elif kind == 'DRAW':  # M9
            word = self.expect('IDENT')
            op = word.value.upper()
            if op not in DRAW_ARITY:
                raise SourceError(word.line, word.column,
                                  'expected CLEAR, FILL, INVERT, BOX, LINE, PIXEL, TEXT, SCROLL '
                                  f'or INK after DRAW, got {word.value}')
            node = Draw(token.line, token.column, op)
            if op == 'INK':
                ink = self.pop()  # XOR is an operator token (M7), BLACK / WHITE identifiers
                if ink.kind not in ('IDENT', 'OP') or ink.value.upper() not in DRAW_INKS:
                    raise SourceError(ink.line, ink.column,
                                      f'DRAW INK is BLACK, WHITE or XOR, got {ink.value}')
                node.ink = ink.value.upper()
            elif self.cur().kind != 'NEWLINE':
                node.values.append(self.expression())
                while self.accept('OP', ','):
                    node.values.append(self.expression())
            if len(node.values) not in DRAW_ARITY[op]:
                want = ' or '.join(str(n) for n in DRAW_ARITY[op])
                raise SourceError(token.line, token.column,
                                  f'DRAW {op} takes {want} argument{"" if want == "1" else "s"}, '
                                  f'got {len(node.values)}')
        elif kind == 'TEXT':  # M9 Stage C
            word = self.expect('IDENT')
            op = word.value.upper()
            if op not in TEXT_ARITY:
                raise SourceError(word.line, word.column,
                                  'expected LOAD, SAVE, CLEAR, INSERT, DELETE, SPLIT, JOIN, REMOVE, '
                                  f'COPY or PASTE after TEXT, got {word.value}')
            name = self.expect('IDENT').value.upper()
            node = TextOp(token.line, token.column, op, name)
            while self.accept('OP', ','):
                node.values.append(self.expression())
            allowed = TEXT_ARITY[op] if isinstance(TEXT_ARITY[op], tuple) else (TEXT_ARITY[op],)
            if len(node.values) not in allowed:
                n = ' or '.join(str(k) for k in allowed)
                raise SourceError(token.line, token.column,
                                  f'TEXT {op} takes the buffer and {n} more argument'
                                  f'{"" if n == "1" else "s"}, got {len(node.values)}')
        elif kind == 'BITMAP':  # M12
            word = self.expect('IDENT')
            op = word.value.upper()
            arity = {'GET': (2, 4), 'PUT': (2, 6), 'SAVE': (1,), 'LOAD': (1,), 'MASK': (2, 6)}  # M13: part, MASK
            if op not in arity:
                raise SourceError(word.line, word.column,
                                  f'expected GET, PUT, MASK, SAVE or LOAD after BITMAP, got {word.value}')
            name = self.expect('IDENT').value.upper()
            node = BitmapOp(token.line, token.column, op, name)
            if op == 'MASK':  # M13: BITMAP MASK Image, Mask, x, y [, sx, sy, w, h]
                self.expect('OP', ',')
                node.mask = self.expect('IDENT').value.upper()
            while self.accept('OP', ','):
                node.values.append(self.expression())
            if len(node.values) not in arity[op]:
                n = ' or '.join(str(k) for k in arity[op])
                what = 'the image, the mask' if op == 'MASK' else 'the bitmap'
                raise SourceError(token.line, token.column,
                                  f'BITMAP {op} takes {what} and {n} more argument{"" if n == "1" else "s"}, '
                                  f'got {len(node.values)}')
        elif kind == 'BEEP':  # M6
            node = Beep(token.line, token.column)
        elif kind in ('FOCUS', 'SHOW'):  # M6
            name = self.expect('IDENT').value.upper()
            node = (Focus if kind == 'FOCUS' else Show)(token.line, token.column, name)
        elif kind == 'MENU':  # M6
            node = Menu(token.line, token.column, self.expression())
        elif kind == 'ITEM':  # M6
            text = self.expression()
            item = Item(token.line, token.column, text)
            if self.accept('OP', ','):
                item.handler = self.expect('IDENT').value.upper()
                while self.accept('OP', ','):
                    word = self.expect('IDENT')
                    upper = word.value.upper()
                    if upper == 'KEY' and item.key is None:
                        key = self.expect('STRING')
                        if len(key.value) != 1 or not key.value.isascii() or not key.value.isalnum():
                            raise SourceError(
                                key.line, key.column,
                                'a menu KEY is one letter or digit, e.g. KEY "N" for Ctrl+N',
                            )
                        item.key = key.value.upper()
                    elif upper == 'TICK' and item.tick is None:
                        item.tick = self.expect('IDENT').value.upper()
                    else:
                        raise SourceError(
                            word.line, word.column,
                            f'expected KEY or TICK (each at most once), got {word.value}',
                        )
            node = item
        elif kind == 'TIMER':  # M6
            word = self.expect('IDENT')
            upper = word.value.upper()
            if upper in ('ON', 'OFF') and self.cur().kind == 'NEWLINE':
                node = TimerSwitch(token.line, token.column, upper == 'ON')
            else:
                self.expect('OP', ',')
                self._word('EVERY')
                seconds = self._int_literal()
                node = Timer(token.line, token.column, upper, seconds)
                if self.cur().kind == 'IDENT' and self.cur().value.upper() == 'TICKS':  # M13: 1/16 s
                    self.expect('IDENT')
                    node.ticks = True
        elif kind in ('FILESAVE', 'FILELOAD'):
            filename = self.expression()
            self.expect('OP', ',')
            value = self.expression()
            cls = Filesave if kind == 'FILESAVE' else Fileload
            node = cls(token.line, token.column, filename, value)
        elif kind == 'DIM':
            name = self.expect('IDENT')
            length = None
            if self.accept('OP', '('):  # M6 Phase 2: DIM Name(n) AS type
                size = self._size('the number of elements of an array')
                length = int(size.value)
                self.expect('OP', ')')
            self.expect('AS')
            type_name = self._type_name()
            capacity = None
            bitmap_size = None
            if self.accept('OP', '*'):  # M8: STRING * n; M9: TEXT * bytes; M12: BITMAP * w, h
                chars = self._size({'TEXT': "a TEXT buffer's size in bytes",
                                    'BITMAP': "a BITMAP's width"}.get(type_name, "a STRING's length"))
                capacity = int(chars.value) + (0 if type_name in ('TEXT', 'BITMAP') else 1)
                if type_name == 'BITMAP':
                    self.expect('OP', ',')
                    bitmap_size = (int(chars.value), int(self._size("a BITMAP's height").value))
                    capacity = None
                elif type_name not in ('STRING', 'TEXT'):
                    raise SourceError(chars.line, chars.column, '* n gives a STRING its length; '
                                      f'{name.value} is {type_name}')
            banked = False
            word = self.cur()
            if word.kind == 'IDENT' and word.value.upper() == 'BANKED':  # M8
                self.pop()
                banked = True
            node = Dim(token.line, token.column, name.value.upper(), type_name, length, capacity, banked,
                       bitmap_size)
        elif kind == 'FOR':
            name = self.expect('IDENT')
            self.expect('OP', '=')
            start = self.expression()
            self.expect('TO')
            finish = self.expression()
            if self.accept('STEP'):
                step = self.expression()
            else:
                step = IntLiteral(token.line, token.column, 1)
            node = For(token.line, token.column, name.value.upper(), start, finish, step)
        elif kind == 'WHILE':
            node = While(token.line, token.column, self.expression())
        elif kind == 'WEND':
            node = Wend(token.line, token.column)
        elif kind == 'NEXT':
            name = self.accept('IDENT')
            node = Next(token.line, token.column, name.value.upper() if name else None)
        elif kind == 'IF':
            condition = self.expression()
            self.expect('THEN')
            node = If(token.line, token.column, condition)
        elif kind == 'ELSE':
            node = Else(token.line, token.column)
        elif kind == 'EXIT':
            if self.accept('FOR'):  # M7
                node = ExitLoop(token.line, token.column, 'FOR')
            elif self.accept('WHILE'):  # M7
                node = ExitLoop(token.line, token.column, 'WHILE')
            elif self.cur().kind == 'IDENT' and self.cur().value.upper() == 'FUNCTION':  # M7
                self.pop()
                node = Exit(token.line, token.column, sub=True)
                node.function = True
            else:
                node = Exit(token.line, token.column, sub=self.accept('SUB') is not None)
        elif kind == 'CALL':
            name = self.expect('IDENT').value.upper()
            node = CallSub(token.line, token.column, name, self._call_args())
        elif kind == 'SUB':
            name = self.expect('IDENT').value.upper()
            node = Sub(token.line, token.column, name, self._params())
        elif kind == 'FUNCTION':  # M7
            name = self.expect('IDENT')
            params = self._params()
            self.expect('AS')
            node = FunctionDef(token.line, token.column, name.value.upper(), params,
                               self._type_name())
        elif kind.startswith('M7FILE:'):
            node = self._file_node(token, kind[7:])
        elif kind == 'PRINT' and self.cur().kind == 'OP' and self.cur().value == '#':  # M7
            channel = self._channel()
            self.expect('OP', ',')
            node = PrintFile(token.line, token.column, channel, self.expression())
        elif kind == 'RANDOMIZE':  # M7: RANDOMIZE [seed]
            seed = None if self.cur().kind == 'NEWLINE' else self.expression()
            node = Randomize(token.line, token.column, seed)
        elif kind == 'RETURN':  # M7
            node = Return(token.line, token.column, self.expression())
        elif kind == 'LOCAL':  # M7
            name = self.expect('IDENT')
            if self.cur().kind == 'OP' and self.cur().value == '(':
                raise SourceError(name.line, name.column,
                                  'LOCAL arrays are not supported; declare the array with DIM')
            self.expect('AS')
            node = Local(token.line, token.column, name.value.upper(), self._type_name())
        elif kind == 'CONST':  # M7
            name = self.expect('IDENT')
            self.expect('OP', '=')
            node = Const(token.line, token.column, name.value.upper(), self.expression())
        elif kind == 'SELECT':  # M7
            word = self.expect('IDENT')
            if word.value.upper() != 'CASE':
                raise SourceError(word.line, word.column, 'expected CASE after SELECT')
            node = SelectCase(token.line, token.column, self.expression())
        elif kind == 'CASE':  # M7
            if self.accept('ELSE'):
                node = Case(token.line, token.column, [], True)
            else:
                items = [self._case_item()]
                while self.accept('OP', ','):
                    items.append(self._case_item())
                node = Case(token.line, token.column, items)
        elif kind == 'END':
            if self.accept('IF'):
                node = EndIf(token.line, token.column)
            elif self.cur().kind == 'IDENT' and self.cur().value.upper() == 'FUNCTION':  # M7
                self.pop()
                node = EndFunction(token.line, token.column)
            elif self.cur().kind == 'IDENT' and self.cur().value.upper() == 'SELECT':  # M7
                self.pop()
                node = EndSelect(token.line, token.column)
            elif self.cur().kind == 'IDENT' and self.cur().value.upper() == 'MENU':  # M6
                self.pop()
                node = EndMenu(token.line, token.column)
            elif self.accept('SUB'):
                node = EndSub(token.line, token.column)
            else:
                node = EndProgram(token.line, token.column)
        elif kind == 'TYPE':  # M10: TYPE Name / fields / END TYPE
            node = self._type_def(token)
        elif kind == 'DB':  # M10: DB op Array, ...
            node = self._db_statement(token)
        elif kind == 'IDENT':
            if self.accept('OP', '('):  # M6 Phase 2: Name(index) = value
                index = self.expression()
                self.expect('OP', ')')
                name = self._field_name(token.value.upper())  # M10: Name(index).Field = value
                self.expect('OP', '=')
                node = AssignIndex(token.line, token.column, name, index, self.expression())
            else:
                name = self._field_name(token.value.upper())  # M10: Name.Field = value
                self.expect('OP', '=')
                node = Assign(token.line, token.column, name, self.expression())
        else:
            raise SourceError(
                token.line, token.column, f'unsupported statement {token.value or kind}'
            )
        self.expect('NEWLINE')
        return node

    # ------------------------------------------------------------ M10 records
    def _field_name(self, name: str) -> str:
        """After a name (and its index), an optional `.Field`: the field is
        named NAME%FIELD, which pbas/records.py declares (LANGUAGE-SPEC §5.8)."""
        if not (self.cur().kind == 'OP' and self.cur().value == '.'):
            return name
        self.pop()
        field = self._field_word()
        if self.cur().kind == 'OP' and self.cur().value == '.':
            dot = self.cur()
            raise SourceError(dot.line, dot.column,
                              'a field of a field: records inside records are not supported')
        if '%' in name:
            raise SourceError(field.line, field.column, 'a field of a field is not supported')
        return f'{name}%{field.value.upper()}'

    def _field_word(self) -> Token:
        """A field name: an identifier, or a keyword (LABEL, TEXT, …) — a
        field is always written after a record and a dot, so it cannot be
        confused with the statement or operator the keyword names."""
        token = self.pop()
        if token.kind == 'IDENT' or (token.kind not in ('OP', 'NUMBER', 'REALNUM', 'STRING', 'NEWLINE',
                                                         'EOF', 'LINENO') and token.value[:1].isalpha()):
            return token
        raise SourceError(token.line, token.column, f'expected a field name, got {token.value or token.kind}')

    def _db_statement(self, token) -> DbOp:
        word = self.expect('IDENT')
        op = word.value.upper()
        if op not in DB_SHAPES:
            raise SourceError(word.line, word.column,
                              f'expected LOAD, SAVE, NEW, DELETE, SORT or SEARCH after DB, got {word.value}')
        before, takes_field, after = DB_SHAPES[op]
        node = DbOp(token.line, token.column, op, self.expect('IDENT').value.upper())
        for _ in range(before):
            self.expect('OP', ',')
            node.values.append(self.expression())
        if takes_field:
            self.expect('OP', ',')
            node.key = self._field_word().value.upper()
        for _ in range(after):
            self.expect('OP', ',')
            node.values.append(self.expression())
        while self.accept('OP', ','):
            flag = self._field_word()
            if flag.value.upper() not in DB_FLAGS.get(op, ()) or flag.value.upper() in node.flags:
                words = DB_FLAGS.get(op, ())
                allowed = (', '.join(words[:-1]) + ' or ' + words[-1]) if len(words) > 1 else (
                    words[0] if words else 'nothing')
                raise SourceError(flag.line, flag.column, f'DB {op} takes {allowed} here, got {flag.value}')
            node.flags.append(flag.value.upper())
        return node

    def _type_def(self, token) -> TypeDef:
        """`TYPE Name`, then one `Field AS type [* n]` per line, then
        `END TYPE`. The END TYPE line's NEWLINE is left for statement()."""
        name = self.expect('IDENT')
        self.expect('NEWLINE')
        fields: list = []
        while True:
            while self.accept('NEWLINE'):
                pass
            cur = self.cur()
            if cur.kind == 'EOF':
                raise SourceError(token.line, token.column, f'TYPE {name.value} without END TYPE')
            if cur.kind == 'END':
                self.pop()
                word = self.cur()
                if word.kind == 'IDENT' and word.value.upper() == 'TYPE':
                    self.pop()
                    return TypeDef(token.line, token.column, name.value.upper(), fields)
                raise SourceError(cur.line, cur.column, f'expected END TYPE to close TYPE {name.value}')
            field = self._field_word()
            self.expect('AS')
            type_name = self._type_name()
            capacity = None
            if self.accept('OP', '*'):
                chars = self.expect('NUMBER')
                capacity = int(chars.value) + 1
                if type_name != 'STRING':
                    raise SourceError(chars.line, chars.column,
                                      f'* n gives a STRING field its length; {field.value} is {type_name}')
            fields.append(TypeField(field.value.upper(), type_name, capacity, field.line, field.column))
            self.expect('NEWLINE')

    # --------------------------------------------------------------- M7 parts
    def _type_name(self) -> str:
        token = self.pop()
        if token.kind in ('INTEGER', 'STRING', 'BOOLEAN'):
            return token.kind
        if token.kind == 'IDENT' and token.value.upper() == 'REAL':
            return 'REAL'
        if token.kind == 'IDENT' and token.value.upper() == 'TEXT':  # M9 (DIM only: semantics)
            return 'TEXT'
        if token.kind == 'IDENT':  # M10: a record TYPE (pbas/records.py checks it exists)
            return token.value.upper()
        raise SourceError(token.line, token.column, 'expected INTEGER, REAL, STRING or BOOLEAN')

    def _params(self) -> list:
        """Optional `(name [AS type], ...)`; a $ name without AS is STRING."""
        params: list = []
        if not self.accept('OP', '('):
            return params
        if self.accept('OP', ')'):
            return params
        while True:
            name = self.expect('IDENT')
            upper = name.value.upper()
            if self.accept('AS'):
                type_name = self._type_name()
            elif upper.endswith('$'):
                type_name = 'STRING'
            else:
                raise SourceError(name.line, name.column,
                                  f'parameter {name.value} needs a type: {name.value} AS INTEGER')
            params.append(Param(upper, type_name, name.line, name.column))
            if self.accept('OP', ')'):
                return params
            self.expect('OP', ',')

    def _call_args(self) -> list:
        args: list = []
        if not self.accept('OP', '('):
            return args
        if self.accept('OP', ')'):
            return args
        args.append(self.expression())
        while self.accept('OP', ','):
            args.append(self.expression())
        self.expect('OP', ')')
        return args

    def _file_statement(self, word: str) -> bool:
        """M7 file words are statements only in their own shapes, so OPEN,
        CLOSE, KILL, NAME and LINE stay usable as variable or array names."""
        nxt = self.cur()
        if word in ('OPEN', 'KILL', 'NAME'):  # M9: also a STRING variable or expression (OPEN: M13)
            return nxt.kind == 'STRING' or (nxt.kind == 'IDENT' and not (
                self.i + 1 < len(self.ts) and self.ts[self.i + 1].kind == 'OP'
                and self.ts[self.i + 1].value == '='))
        if word == 'CLOSE':
            return nxt.kind == 'NEWLINE' or (nxt.kind == 'OP' and nxt.value == '#')
        if word == 'LINE':
            return nxt.kind == 'IDENT' and nxt.value.upper() == 'INPUT'
        return False

    def _channel(self) -> int:
        self.expect('OP', '#')
        number = self.expect('NUMBER')
        if number.value not in ('1', '2'):
            raise SourceError(number.line, number.column,
                              'a file channel is #1 or #2 (Rosanne allows one read and one write file)')
        return int(number.value)

    def _file_node(self, token, word: str):
        line, column = token.line, token.column
        if word == 'OPEN':
            name = self.expression()
            self.expect('FOR')
            mode = self.expect('IDENT')
            if mode.value.upper() not in ('INPUT', 'OUTPUT'):
                raise SourceError(mode.line, mode.column,
                                  'expected INPUT or OUTPUT (APPEND and RANDOM are not available on the floppy)')
            self.expect('AS')
            return OpenFile(line, column, name, mode.value.upper(), self._channel())
        if word == 'CLOSE':
            if self.cur().kind == 'NEWLINE':
                return CloseFile(line, column, None)
            return CloseFile(line, column, self._channel())
        if word == 'KILL':
            return Kill(line, column, self.expression())
        if word == 'NAME':
            old = self.expression()
            self.expect('AS')
            return NameFile(line, column, old, self.expression())
        self.pop()  # LINE INPUT #n, var$  /  LINE INPUT #n, A$(i)
        channel = self._channel()
        self.expect('OP', ',')
        name = self.expect('IDENT').value.upper()
        index = None
        if self.accept('OP', '('):
            index = self.expression()
            self.expect('OP', ')')
        tok = self.cur()
        if tok.kind == 'OP' and tok.value == '.':  # M14: a record field (adversarial review)
            raise SourceError(tok.line, tok.column, 'LINE INPUT # reads into a STRING variable or a '
                              'STRING array element, not a record field: read the line into a STRING, '
                              'then assign it to the field')
        return LineInput(line, column, channel, name, index)

    def _case_item(self) -> CaseItem:
        token = self.cur()
        if token.kind == 'IDENT' and token.value.upper() == 'IS':
            self.pop()
            op = self.pop()
            if op.kind != 'OP' or op.value not in ('=', '<>', '<', '<=', '>', '>='):
                raise SourceError(op.line, op.column, 'expected a comparison after CASE IS')
            return CaseItem('IS', self.expression(), None, op.value)
        low = self.expression()
        if self.accept('TO'):
            return CaseItem('RANGE', low, self.expression())
        return CaseItem('EQ', low)

    def _word(self, expected: str) -> Token:
        """An identifier that is a fixed word in this position (M6)."""
        word = self.expect('IDENT')
        if word.value.upper() != expected:
            raise SourceError(word.line, word.column, f'expected {expected}, got {word.value}')
        return word

    def _int_literal(self) -> int:
        """A signed integer literal (M6 NUMBERBOX bounds, TIMER seconds)."""
        token = self.cur()
        value = self.expression()
        if not isinstance(value, IntLiteral):
            raise SourceError(token.line, token.column, 'expected an integer literal')
        return value.value

    def parse(self) -> list[Stmt]:
        """Parse the whole stream and return the validated flat AST."""
        nodes: list[Stmt] = []
        prevnum = 0
        while self.cur().kind != 'EOF':
            if self.accept('NEWLINE'):
                continue
            num = self.accept('LINENO')
            if num is not None:
                value = int(num.value)
                if value <= prevnum:
                    raise SourceError(
                        num.line, num.column, 'line numbers must strictly increase'
                    )
                prevnum = value
            if self.cur().kind == 'NEWLINE':
                self.pop()
                continue
            nodes.append(self.statement())
        nodes = lower(nodes)  # M7: procedures, CONST, SELECT CASE (pbas/lower.py)
        validate(nodes)
        return nodes


def _real_literal(token, text: str):
    """M7: a REAL literal; its value is kept exactly (pbas/real.py rounds)."""
    from fractions import Fraction
    from .real import RealRangeError, pack
    try:
        pack(Fraction(text))
    except RealRangeError as exc:
        raise SourceError(token.line, token.column, str(exc)) from None
    node = RealLiteral(token.line, token.column, float(text))
    node.text = text
    return node


def validate(nodes: list[Stmt]) -> None:
    """Check marker-statement nesting, handler definitions and declaration
    placement; raise SourceError at the offending node's position.

    Rules are the POC's, plus: WINDOW/LABEL/TEXTBOX/CHECKBOX/BUTTON found
    while any block is open (inside IF/WHILE/FOR/SUB) are rejected.
    DIM is not restricted; it declares a global and may appear anywhere.
    """
    stack: list[tuple[str, str | None]] = []  # ('IF', 'ELSE-seen') marks an IF
    defined: set[str] = set()
    handlers: list[Button] = []
    calls: list[tuple[str | None, CallSub]] = []  # (calling SUB or None, CALL)
    main_ended = False
    for node in nodes:
        if len(stack) >= MAX_BLOCK_DEPTH and isinstance(node, (Sub, If, While, For)):
            raise SourceError(
                node.line,
                node.column,
                f'blocks are nested more than {MAX_BLOCK_DEPTH} levels deep',
            )
        if main_ended:
            raise SourceError(
                node.line, node.column, 'statements after END are not allowed'
            )
        in_menu = bool(stack) and stack[-1][0] == 'MENU'
        if in_menu and not isinstance(node, (Item, EndMenu)):
            raise SourceError(
                node.line, node.column, 'only ITEM lines may appear inside a MENU block'
            )
        if isinstance(node, Item) and not in_menu:
            raise SourceError(node.line, node.column, 'ITEM is only allowed inside a MENU block')
        decl_kind = _DECLARATIONS.get(type(node))
        if decl_kind is not None and stack:
            raise SourceError(
                node.line,
                node.column,
                f'{decl_kind} is only allowed at the top level',
            )
        if isinstance(node, Sub):
            if stack:
                raise SourceError(node.line, node.column, 'SUB must be top-level')
            if node.name in defined:
                raise SourceError(
                    node.line, node.column, f'duplicate subroutine {node.name}'
                )
            defined.add(node.name)
            stack.append(('SUB', node.name))
        elif isinstance(node, Menu):
            stack.append(('MENU', None))
        elif isinstance(node, EndMenu):
            if not in_menu:
                raise SourceError(node.line, node.column, 'END MENU without matching MENU')
            stack.pop()
        elif isinstance(node, If):
            stack.append(('IF', None))
        elif isinstance(node, While):
            stack.append(('WHILE', None))
        elif isinstance(node, Wend):
            if not stack or stack[-1][0] != 'WHILE':
                raise SourceError(node.line, node.column, 'WEND without matching WHILE')
            stack.pop()
        elif isinstance(node, For):
            if any(item[0] == 'FOR' and item[1] == node.name for item in stack):
                raise SourceError(
                    node.line,
                    node.column,
                    f'nested FOR reuses active counter {node.name}',
                )
            stack.append(('FOR', node.name))
        elif isinstance(node, Next):
            if not stack or stack[-1][0] != 'FOR':
                raise SourceError(node.line, node.column, 'NEXT without matching FOR')
            if node.name is not None and node.name != stack[-1][1]:
                raise SourceError(
                    node.line,
                    node.column,
                    f'NEXT {node.name} does not match FOR {stack[-1][1]}',
                )
            stack.pop()
        elif isinstance(node, Else):
            if not stack or stack[-1][0] != 'IF':
                raise SourceError(node.line, node.column, 'ELSE without matching IF')
            if stack[-1][1] is not None:
                raise SourceError(
                    node.line, node.column, 'multiple ELSE clauses for one IF'
                )
            stack[-1] = ('IF', 'ELSE')
        elif isinstance(node, EndProgram):
            if stack:
                raise SourceError(
                    node.line, node.column, 'END inside an unclosed block'
                )
            main_ended = True
        elif isinstance(node, (EndIf, EndSub)):
            target = 'IF' if isinstance(node, EndIf) else 'SUB'
            if not stack or stack[-1][0] != target:
                raise SourceError(
                    node.line,
                    node.column,
                    f'END {target} without matching {target}',
                )
            stack.pop()
        if isinstance(node, (Button, Timer)) or (isinstance(node, Item) and node.handler):
            handlers.append(node)
        elif isinstance(node, (ListCtl, Slider, Canvas)):  # M6 Phase 2 CHANGE / ACTION; M9 CANVAS
            for handler in (getattr(node, 'change', None), getattr(node, 'action', None),
                            getattr(node, 'paint', None), getattr(node, 'mouse', None),
                            getattr(node, 'keys', None)):
                if handler is not None and handler not in [s.name for s in nodes if isinstance(s, Sub)]:
                    raise SourceError(node.line, node.column,
                                      f'handler {handler} is not defined by SUB')
        elif isinstance(node, CallSub):
            caller = next((name for kind, name in reversed(stack) if kind == 'SUB'), None)
            calls.append((caller, node))
        elif isinstance(node, ExitLoop):  # M7: innermost enclosing loop of that kind, same SUB
            loops = []
            for kind, _ in reversed(stack):
                if kind == 'SUB':
                    break
                loops.append(kind)
            if node.kind not in loops:
                raise SourceError(node.line, node.column,
                                  f'EXIT {node.kind} is only allowed inside a {node.kind} loop')
        elif isinstance(node, Exit) and node.sub and not any(
            kind == 'SUB' for kind, _ in stack
        ):
            raise SourceError(
                node.line, node.column, 'EXIT SUB is only allowed inside a SUB'
            )
    if stack:
        last = nodes[-1] if nodes else None
        raise SourceError(
            last.line if last else 1,
            last.column if last else 1,
            f'unclosed {stack[-1][0]} block',
        )
    if not main_ended:
        last = nodes[-1] if nodes else None
        raise SourceError(
            last.line if last else 1,
            last.column if last else 1,
            'program requires a final END',
        )
    for button in handlers:
        if button.handler not in defined:
            what = {Button: 'button', Item: 'menu item', Timer: 'timer'}[type(button)]
            raise SourceError(
                button.line,
                button.column,
                f'{what} handler {button.handler} is not defined by SUB',
            )
    _validate_calls(calls, defined)


def _validate_calls(calls, defined) -> None:
    """M5c CALL rules (LANGUAGE-SPEC section 5): every target is a SUB; no
    procedure calls itself directly or indirectly; at most MAX_CALL_DEPTH
    procedures are active at once.

    The call graph has an edge for every CALL inside a SUB. A depth-first
    search in source order reports the first CALL that closes a cycle; with
    the graph acyclic, depth(S) = 1 + the deepest SUB that S calls, and a
    SUB deeper than the limit is reported at its CALL of the deepest callee.
    """
    edges: dict[str, list[CallSub]] = {}
    for caller, node in calls:
        if node.name not in defined:
            raise SourceError(
                node.line, node.column, f'CALL {node.name}: no SUB {node.name} is defined'
            )
        if caller is not None:
            edges.setdefault(caller, []).append(node)
    state: dict[str, int] = {}  # 1 = on the current path, 2 = finished
    depth: dict[str, int] = {}
    path: list[str] = []

    def visit(name: str) -> None:
        state[name] = 1
        path.append(name)
        best = 0
        deepest = None
        for node in edges.get(name, []):
            if state.get(node.name) == 1:
                cycle = path[path.index(node.name):] + [node.name]
                raise SourceError(
                    node.line,
                    node.column,
                    'recursive CALL is not allowed: ' + ' -> '.join(cycle)
                    + ' (procedures use static storage, so recursion is not supported)',
                )
            if node.name not in state:
                if len(path) >= MAX_CALL_DEPTH:  # bounds this recursion too
                    raise SourceError(
                        node.line,
                        node.column,
                        f'CALL {node.name} makes a chain of more than {MAX_CALL_DEPTH} '
                        f'procedures active at once (from SUB {path[0]}); '
                        f'at most {MAX_CALL_DEPTH} are allowed',
                    )
                visit(node.name)
            if depth[node.name] > best:
                best, deepest = depth[node.name], node
        depth[name] = best + 1
        if depth[name] > MAX_CALL_DEPTH:
            raise SourceError(
                deepest.line,
                deepest.column,
                f'CALL {deepest.name} makes a chain of {depth[name]} procedures '
                f'active at once (from SUB {name}); at most {MAX_CALL_DEPTH} are allowed',
            )
        path.pop()
        state[name] = 2

    for caller, _ in calls:
        if caller is not None and caller not in state:
            visit(caller)


def parse(source: str) -> list[Stmt]:
    """Tokenize and parse *source*, returning the validated flat AST."""
    return Parser(tokenize(source)).parse()
