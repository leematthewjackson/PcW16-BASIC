"""Static semantic analysis for PcW16 BASIC (Stage 1).

Ported from the proven POC frontend (``POC/pbas/semantics.py``,
ARCHITECTURE.md D8) and extended with the Stage-1 contract of
LANGUAGE-SPEC.md: program-wide fixed string capacities, collection of the
dialog description (widgets, bindings, handlers), literal/ASCII/length
constraints on Rosanne-facing text, MESSAGE budgeting against the alert
buffer, the concatenation position restriction, the substring
integer-literal rule and DOS 8.3 file-name validation. ``analyze`` returns
an :class:`Analysis`; there is deliberately no code generation in M1.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import ast_nodes as ast
from .errors import SourceError
from .files import RESERVED_NAMES
from .policy import (
    ALERT_BUFFER_SIZE,
    BUTTON_CAPTION_MAX,
    CAPTION_MAX,
    DEFAULT_STRING_CAPACITY,
    DYNAMIC_LABEL_MAX,
    FILE_TEXT_MAX,
    FILENAME_PATTERN_TEXT,
    FILENAME_RE,
    LABEL_TEXT_MAX,
    MAX_BUTTONS,
    MAX_CHECKBOXES,
    MAX_LABELS,
    MAX_STRING_CAPACITY,
    MESSAGE_LITERAL_MAX,
    MIN_STRING_CAPACITY,
    SCRATCH_STRING_MAX,
    STRS_BUDGET,
    TEXTBOX_CAPACITY_MAX,
    WINDOW_TITLE_MAX,
    ASK_BUTTONS_MAX,
    ASK_BUTTONS_MIN,
    ASK_CAPTION_MAX,
    ASK_TEXT_MAX,
    MAX_BUTTON_KEYS,
    MAX_MENUS,
    MAX_RADIO_GROUPS,
    MAX_WINDOWS,
    MENU_ITEM_MAX,
    MENU_ITEMS_MAX,
    MENU_TITLE_MAX,
    RADIO_OPTIONS_MAX,
    RADIO_OPTIONS_MIN,
    TIMER_SECONDS_MAX,
    TIMER_TICKS_MAX,
    ARRAY_LENGTH_MAX,
    BANKED_BLOCKS_MAX,
    BANKED_LENGTH_MAX,
    BANKED_READS_MAX,
    BLOCK_SIZE,
    SLIDER_RANGE_MAX,
)
from .lower import display_name
from .records import expand as expand_records
from .program import Binding, Handler, MenuDecl, MenuItem, TimerDecl, Widget, WindowDecl


@dataclass
class Variable:
    """A global variable: type, fixed capacity and declaration origin."""

    name: str
    type: str  # 'INTEGER' | 'STRING' | 'BOOLEAN'
    capacity: int | None  # bytes incl. NUL; STRING only
    origin: str  # 'DIM' | 'TEXTBOX' | 'CHECKBOX' | 'LABEL'
    line: int
    column: int
    length: int | None = None  # M6 Phase 2: number of elements of an array
    banked: bool = False  # M8: elements in owned 16K blocks (LANGUAGE-SPEC §5.4)
    text_bytes: int = 0  # M9: a TEXT buffer's capacity in bytes
    record: str | None = None  # M10: a record's TYPE name (type 'RECORD', capacity = its size)
    alias: tuple | None = None  # M10: a field: (record name, offset, record size)


@dataclass
class Analysis:
    """Everything later milestones need from semantic analysis."""

    variables: dict[str, Variable]  # insertion-ordered by first declaration
    string_capacity: int
    dialog_title: str | None
    widgets: list[Widget]  # source order
    bindings: list[Binding]  # source order
    handlers: list[Handler]  # source order
    dialog_position: tuple[int, int] | None = None  # WINDOW (line, column)
    windows: list = None  # list[WindowDecl] (M6)
    menus: list = None  # list[MenuDecl] (M6)
    timer: TimerDecl | None = None  # M6
    on_stop: str | None = None  # M15: ON STOP's FUNCTION
    on_stop_line: int = 0


NUMERIC = ('INTEGER', 'REAL')  # M7
REAL_FUNCTIONS = ('SQR', 'SIN', 'COS', 'TAN', 'ATN', 'LOG', 'EXP', 'INT', 'FIX', 'REAL')
STR_REAL_BUDGET = 15  # M7: the longest STR$ of a REAL, "-1.23456789E-38"
PI_TEXT = '3.14159265358979323846'

# Built-in function names: never array names (M6 Phase 2).
_BUILTINS = {'LEN', 'STR$', 'LEFT$', 'RIGHT$', 'MID$', 'VAL', 'ASC', 'CHR$', 'INSTR',
             'UCASE$', 'LCASE$', 'ASK',
             # M7
             'ABS', 'SGN', 'MIN', 'MAX', 'RND', 'SHL', 'SHR', 'TRIM$', 'LTRIM$', 'RTRIM$',
             'SPACE$', 'STRING$', 'EOF', 'IOERR',
             'SQR', 'SIN', 'COS', 'TAN', 'ATN', 'LOG', 'EXP', 'INT', 'FIX', 'REAL', 'CINT',
             'REALVAL', 'ISNUM', 'PI',
             # M9 canvas events
             'MOUSEX', 'MOUSEY', 'MOUSEEVENT', 'KEYCODE', 'KEYSHIFT',
             # M9 Stage C text buffers
             'TEXTLINES', 'TEXTLEN', 'TEXTGET$', 'TEXTFIND', 'TEXTCOL', 'TEXTCHANGED',
             'TEXTFREE', 'TEXTSIZE', 'TEXTSAME',
             # M10 databases
             'DBFIND', 'DBNEXTID', 'DBRECOVERED',
             # M11 corrective: text measurement and the clock
             'TEXTWIDTH', 'SECONDS',
             # M12 bitmaps and the screen
             'BITMAPW', 'BITMAPH', 'POINT',
             'PAGEWIDTH',  # M12 printing
             'KEYDOWN',  # M13 held keys
             'CLOCKTICKS',  # M13 corrective: the clock in 1/16 s
             'TYPEWIDTH', 'TYPEHEIGHT'}  # M15 screen typography
DB_FUNCTIONS = ('DBFIND', 'DBNEXTID', 'DBRECOVERED')  # M10 (LANGUAGE-SPEC §5.9)
# M9 Stage C: TEXT functions -> (argument types after the buffer, result type)
TEXT_FUNCTIONS = {'TEXTLINES': ((), 'INTEGER'), 'TEXTLEN': (('INTEGER',), 'INTEGER'),
                  'TEXTGET$': (('INTEGER', 'INTEGER', 'INTEGER'), 'STRING'),
                  'TEXTFIND': (('STRING', 'INTEGER', 'INTEGER'), 'INTEGER'),
                  'TEXTCOL': ((), 'INTEGER'), 'TEXTCHANGED': ((), 'BOOLEAN'),
                  'TEXTFREE': ((), 'INTEGER'), 'TEXTSIZE': ((), 'INTEGER'),
                  'TEXTSAME': (('TEXT',), 'BOOLEAN')}  # M10
TEXT_BYTES_MAX = 65535  # M9: a TEXT buffer's capacity (16-bit positions)
TEXT_GET_MAX = 126  # M9: TEXTGET$ returns at most this many bytes
CANVAS_EVENT_NAMES = ('MOUSEX', 'MOUSEY', 'MOUSEEVENT', 'KEYCODE', 'KEYSHIFT')  # M9
CANVAS_MIN = 16  # M9: smallest CANVAS side (pixels)
CANVAS_MAX_W = 568  # M9: widest drawing area that fits a LARGE window's box (pbas/layout.py)
CANVAS_MAX_H = 300
CANVAS_MAX_N = 8  # M15: canvases in one program
PAGE_SIZES = (6, 8, 10, 11, 12, 14, 18, 24, 36, 72)  # M12: os_typo_def / os_meta_font point sizes
_TRIMS = ('TRIM$', 'LTRIM$', 'RTRIM$')


def dynamic_message_budget(expr, variables) -> int:
    """Worst-case byte size of a dynamic MESSAGE expression (spec section 6).

    Total bytes of all StrLiteral parts + the capacity of every referenced
    STRING variable (each occurrence counted) + ``STRS_BUDGET`` per STR$
    call. Only text counts (M5a): a substring counts its source, not its
    integer arguments; STR$ counts its 6 digits, not its argument; LEN and
    other INTEGER pieces contribute nothing.
    """
    if isinstance(expr, ast.StrLiteral):
        return len(expr.value.encode('utf-8'))
    if isinstance(expr, (ast.Var, ast.Index)):
        var = variables.get(expr.name)
        return var.capacity if var is not None and var.type == 'STRING' else 0
    if isinstance(expr, ast.Call):
        if expr.name == 'STR$':
            return STR_REAL_BUDGET if getattr(expr.args[0], 'typ', None) == 'REAL' else STRS_BUDGET
        if expr.name == 'CHR$':
            return 1
        if expr.name in ('LEFT$', 'RIGHT$', 'MID$', 'UCASE$', 'LCASE$') + _TRIMS:
            return dynamic_message_budget(expr.args[0], variables)
        if expr.name in ('SPACE$', 'STRING$', 'TEXTGET$'):  # M7, M9
            return string_length_bounds(expr, variables)[1]
        return 0  # LEN: an INTEGER, no text
    if isinstance(expr, ast.Unary):
        return dynamic_message_budget(expr.operand, variables)
    if isinstance(expr, ast.Binary):
        return dynamic_message_budget(expr.left, variables) + dynamic_message_budget(
            expr.right, variables
        )
    return 0  # IntLiteral/BoolLiteral contribute nothing to a STRING expression


def string_length_bounds(expr, variables) -> tuple[int, int]:
    """Static (minimum, maximum) byte length of a STRING expression (M2.1).

    Exact for literals and substrings of literals; a STRING variable holds
    0..capacity-1 bytes; STR$ yields 1..6 ("0".."-32768"); substrings are
    clipped by their literal counts; concatenation adds. Used to reject
    overflow that is certain at compile time (LANGUAGE-SPEC.md section 4) and
    to bound computed operands that need runtime scratch storage.
    """
    if isinstance(expr, ast.StrLiteral):
        n = len(expr.value.encode('utf-8'))
        return n, n
    if isinstance(expr, (ast.Var, ast.Index)):
        return 0, variables[expr.name].capacity - 1
    if isinstance(expr, ast.Binary):  # '+' concatenation
        left = string_length_bounds(expr.left, variables)
        right = string_length_bounds(expr.right, variables)
        return left[0] + right[0], left[1] + right[1]
    if isinstance(expr, ast.Call):
        if expr.name == 'STR$':
            if getattr(expr.args[0], 'typ', None) == 'REAL':  # M7
                return 1, STR_REAL_BUDGET
            return 1, STRS_BUDGET
        if expr.name == 'CHR$':  # M5b: exactly one character
            return 1, 1
        if expr.name in ('UCASE$', 'LCASE$'):  # M5c: same length as the argument
            return string_length_bounds(expr.args[0], variables)
        if expr.name in _TRIMS:  # M7: up to the argument's length
            return 0, string_length_bounds(expr.args[0], variables)[1]
        if expr.name == 'TEXTGET$':  # M9: up to its count (at most TEXT_GET_MAX)
            n = constant_int(expr.args[3])
            return 0, min(n, TEXT_GET_MAX) if n is not None and n >= 0 else TEXT_GET_MAX
        if expr.name in ('SPACE$', 'STRING$'):  # M7: exactly n (computed n: up to 127)
            n = constant_int(expr.args[0])
            return (n, n) if n is not None else (0, SCRATCH_STRING_MAX)
        lo, hi = string_length_bounds(expr.args[0], variables)
        if expr.name == 'MID$':
            start = constant_int(expr.args[1])
            if start is None:  # M5a: run-time start, anything from 1 up
                lo = 0
            else:
                lo, hi = max(lo - (start - 1), 0), max(hi - (start - 1), 0)
        count = constant_int(expr.args[-1])
        if count is None:  # M5a: run-time count, 0 up to the whole source
            return 0, hi
        return min(lo, count), min(hi, count)
    raise AssertionError(f'not a STRING expression: {type(expr).__name__}')


def constant_int(expr):
    """The value of an INTEGER constant (a literal, optionally with unary
    sign), or None for anything computed at run time (M5a)."""
    if isinstance(expr, ast.IntLiteral):
        return expr.value
    if isinstance(expr, ast.Unary) and isinstance(expr.operand, ast.IntLiteral):
        return -expr.operand.value if expr.op == '-' else expr.operand.value
    return None


def _literal_parts(expr):
    """Yield every StrLiteral in a (dynamic) MESSAGE expression, in order."""
    if isinstance(expr, ast.StrLiteral):
        yield expr
    elif isinstance(expr, ast.Binary):
        yield from _literal_parts(expr.left)
        yield from _literal_parts(expr.right)
    elif isinstance(expr, ast.Call):
        for arg in expr.args:
            yield from _literal_parts(arg)
    elif isinstance(expr, ast.Unary):
        yield from _literal_parts(expr.operand)


def _require_textbox_capacity(name: str, capacity: int, line: int, column: int) -> None:
    """A TEXTBOX binding must fit the documented textedit maximum (F10)."""
    if capacity > TEXTBOX_CAPACITY_MAX:
        raise SourceError(
            line,
            column,
            f'TEXTBOX-bound string {name} has capacity {capacity}, '
            f'exceeding the textedit maximum of {TEXTBOX_CAPACITY_MAX}',
        )


def analyze(nodes, *, string_capacity: int = DEFAULT_STRING_CAPACITY) -> Analysis:
    """Check declarations, types and limits; collect the dialog description.

    *nodes* is the validated flat statement list from ``pbas.parser``.
    Declaration processing is a source-order pass (DIM and widget bindings
    may appear in any order as long as types agree); statement checks are a
    second pass over the same list. All names are case-insensitive and
    stored upper-cased.
    """
    if not isinstance(string_capacity, int) or not (
        MIN_STRING_CAPACITY <= string_capacity <= MAX_STRING_CAPACITY
    ):
        raise SourceError(
            1,
            1,
            f'string capacity must be between {MIN_STRING_CAPACITY} '
            f'and {MAX_STRING_CAPACITY}',
        )

    expand_records(nodes)  # M10: TYPEs, fields, whole-record copies (pbas/records.py)
    variables: dict[str, Variable] = {}
    subs: dict[str, ast.Sub] = {}
    widgets: list[Widget] = []
    bindings: list[Binding] = []
    handlers: list[Handler] = []
    counts = {'LABEL': 0, 'CHECKBOX': 0, 'BUTTON': 0}
    dialog_title: str | None = None
    dialog_position: tuple[int, int] | None = None
    has_window = any(isinstance(node, ast.Window) for node in nodes)
    has_files = any(isinstance(node, (ast.OpenFile, ast.Kill, ast.NameFile, ast.DbOp))  # M10: DB
                    for node in nodes) or any(
        isinstance(node, (ast.TextOp, ast.BitmapOp)) and node.op in ('LOAD', 'SAVE') for node in nodes  # M9; M12
    ) or any(isinstance(node, ast.PageOp) for node in nodes)  # M12: PAGE sets IOERR
    has_canvas = any(isinstance(node, ast.Canvas) for node in nodes)  # M9
    canvases: list = []  # M9: one CANVAS per program; M15: up to CANVAS_MAX_N, named

    # ------------------------------------------------------------- expressions
    def expression(expr) -> str:
        """Type an expression node (M7: and record it as ``expr.typ`` for the
        code generator); raise SourceError at the innermost position."""
        typ = expression_type(expr)
        expr.typ = typ
        return typ

    def expression_type(expr) -> str:
        if isinstance(expr, ast.IntLiteral):
            return 'INTEGER'
        if isinstance(expr, ast.StrLiteral):
            return 'STRING'
        if isinstance(expr, ast.BoolLiteral):
            return 'BOOLEAN'
        if isinstance(expr, ast.RealLiteral):  # M7
            return 'REAL'
        if isinstance(expr, ast.Var):
            var = variables.get(expr.name)
            if var is None:
                if expr.name + '..R' in variables:  # M14 (D7): a FUNCTION used without ()
                    raise SourceError(expr.line, expr.column,
                                      f'{expr.name} is a FUNCTION: call it as {expr.name}() '
                                      '(with parentheses, even when it takes no arguments)')
                raise SourceError(
                    expr.line,
                    expr.column,
                    f'undefined variable {expr.name}; '
                    'declare it with DIM or a UI binding',
                )
            if var.length is not None:
                raise SourceError(
                    expr.line, expr.column,
                    f'{expr.name} is an array: use {expr.name}(index)',
                )
            return var.type
        if isinstance(expr, ast.Index):  # M6 Phase 2
            var = variables[expr.name]
            if expression(expr.index) != 'INTEGER':
                raise SourceError(
                    expr.index.line, expr.index.column, 'an array index must be INTEGER'
                )
            literal_index(expr.name, expr.index, var)
            return var.type
        if isinstance(expr, ast.Call):
            return call(expr)
        if isinstance(expr, ast.Unary):
            operand_type = expression(expr.operand)
            if expr.op == 'NOT':  # M5c: BOOLEAN; M7: INTEGER gives the bitwise complement
                if operand_type not in ('BOOLEAN', 'INTEGER'):
                    raise SourceError(
                        expr.line,
                        expr.column,
                        f'NOT requires a BOOLEAN or INTEGER operand, got {operand_type}',
                    )
                return operand_type
            if operand_type not in NUMERIC:
                raise SourceError(
                    expr.line,
                    expr.column,
                    f'unary {expr.op} requires INTEGER or REAL, got {operand_type}',
                )
            return operand_type
        if isinstance(expr, ast.Binary):
            return binary(expr)
        raise AssertionError(f'unknown expression node: {type(expr).__name__}')

    def binary(expr) -> str:
        op = expr.op
        left_type = expression(expr.left)
        right_type = expression(expr.right)
        both_numeric = left_type in NUMERIC and right_type in NUMERIC
        real = both_numeric and 'REAL' in (left_type, right_type)
        # M7: an INTEGER operand next to a REAL one is widened to REAL (exact)
        if op == '^':
            if not both_numeric:
                raise SourceError(expr.line, expr.column,
                                  f'operator ^ requires numbers, got {left_type} and {right_type}')
            return 'REAL'
        if real and op in ('+', '-', '*', '/'):
            return 'REAL'
        if real and op in ('=', '==', '<>', '<', '<=', '>', '>='):
            return 'BOOLEAN'
        if op == '+':
            if left_type == right_type == 'STRING':
                return 'STRING'  # M5a: concatenation anywhere a STRING is expected
            if left_type == right_type == 'INTEGER':
                return 'INTEGER'
            raise SourceError(
                expr.line,
                expr.column,
                f'operator + requires numbers (or STRING + STRING), '
                f'got {left_type} and {right_type}',
            )
        if op in ('AND', 'OR', 'XOR'):
            # M5c: BOOLEAN, short-circuit (AND/OR). M7: two INTEGERs give the
            # bitwise result (both evaluated); XOR never short-circuits.
            if left_type == right_type and left_type in ('BOOLEAN', 'INTEGER'):
                return left_type
            raise SourceError(
                expr.line,
                expr.column,
                f'{op} requires two BOOLEAN or two INTEGER operands, got {left_type} and {right_type}',
            )
        if op in ('/', 'MOD'):  # M5b: integer division, truncating toward zero
            if left_type != 'INTEGER' or right_type != 'INTEGER':
                raise SourceError(
                    expr.line,
                    expr.column,
                    f'operator {op} requires INTEGER operands, got {left_type} and {right_type}'
                    if op == 'MOD' else
                    f'operator {op} requires numbers, got {left_type} and {right_type}',
                )
            if constant_int(expr.right) == 0:
                raise SourceError(
                    expr.right.line, expr.right.column, f'division by zero ({op} 0)'
                )
            return 'INTEGER'
        if op in ('-', '*'):
            if left_type != 'INTEGER' or right_type != 'INTEGER':
                raise SourceError(
                    expr.line,
                    expr.column,
                    f'operator {op} requires numbers, got {left_type} and {right_type}',
                )
            return 'INTEGER'
        if op in ('=', '==', '<>'):
            if left_type != right_type:
                raise SourceError(
                    expr.line,
                    expr.column,
                    f'comparison {op} requires matching types, '
                    f'got {left_type} and {right_type}',
                )
            if left_type == 'STRING':
                require_scratch_fit(expr.left, 'string comparison')
                require_scratch_fit(expr.right, 'string comparison')
            return 'BOOLEAN'
        if op in ('<', '<=', '>', '>='):
            # M5b: STRING ordering is byte order (rt_str_compare).
            if left_type != right_type or left_type == 'BOOLEAN':
                raise SourceError(
                    expr.line,
                    expr.column,
                    'ordering comparisons (<, <=, >, >=) require two INTEGER '
                    f'or two STRING operands, got {left_type} and {right_type}',
                )
            if left_type == 'STRING':
                require_scratch_fit(expr.left, 'string comparison')
                require_scratch_fit(expr.right, 'string comparison')
            return 'BOOLEAN'
        raise AssertionError(f'unknown operator {op!r}')

    def bitmap_var(arg, what: str) -> None:
        """M12: *arg* names a BITMAP."""
        var = variables.get(arg.name) if isinstance(arg, ast.Var) else None
        if var is None or var.type not in ('BITMAP', 'BITMAPREF'):  # M13: or a BITMAP parameter
            raise SourceError(arg.line, arg.column, f'{what} needs a BITMAP (DIM Name AS BITMAP * width, height)')
        arg.typ = 'BITMAP'

    def text_buffer(arg, what: str) -> None:
        """M9: *arg* names a TEXT buffer."""
        var = variables.get(arg.name) if isinstance(arg, ast.Var) else None
        if var is None or var.type != 'TEXT':
            raise SourceError(arg.line, arg.column, f'{what} needs a TEXT buffer (DIM Name AS TEXT * bytes)')
        arg.typ = 'TEXT'

    def database(arg, what: str):
        """M10: *arg* names a database: a BANKED array of records (§5.9)."""
        name = arg.name if isinstance(arg, ast.Var) else arg
        var = variables.get(name)
        at = arg if isinstance(arg, ast.Expr) else None
        if var is None or var.type != 'RECORD' or var.length is None or not var.banked:
            raise SourceError(at.line if at else 0, at.column if at else 0,
                              f'{what} needs a database: a BANKED array of records '
                              f'(DIM {display_name(name)}(n) AS TypeName BANKED)')
        if at is not None:
            at.typ = 'RECORD'
        return var

    def first_field_id(var, line, column, what):
        """M10: DB NEW / DBFIND / DBNEXTID keep identifiers in the TYPE's
        first field, which must be INTEGER."""
        first = next(f for f in variables.values()
                     if f.alias is not None and f.alias[0] == var.name and f.alias[1] == 0)
        if first.type != 'INTEGER':
            raise SourceError(line, column,
                              f'{what} keeps the record identifier in the first field of TYPE '
                              f'{var.record}, which must be INTEGER ({display_name(first.name)} is {first.type})')

    def call(expr) -> str:
        """Type a built-in function call (arity, argument types, literal rule)."""
        name, args = expr.name, expr.args

        def arity(expected: int) -> None:
            if len(args) != expected:
                raise SourceError(
                    expr.line,
                    expr.column,
                    f'{name} expects {expected} arguments, got {len(args)}',
                )

        if name == 'ASK':  # M6: only as `v = ASK(...)`, checked by check_assign
            raise SourceError(
                expr.line, expr.column,
                'ASK may only be the whole right-hand side of an assignment to an INTEGER',
            )
        if name == 'LEN':
            arity(1)
            if expression(args[0]) != 'STRING':
                raise SourceError(args[0].line, args[0].column, 'LEN expects a STRING')
            require_scratch_fit(args[0], 'LEN')
            return 'INTEGER'
        if name == 'STR$':
            arity(1)
            if expression(args[0]) not in NUMERIC:
                raise SourceError(
                    args[0].line, args[0].column, 'STR$ expects a number (INTEGER or REAL)'
                )
            return 'STRING'
        if name in ('LEFT$', 'RIGHT$'):
            arity(2)
            if expression(args[0]) != 'STRING' or expression(args[1]) != 'INTEGER':
                raise SourceError(
                    expr.line, expr.column, f'{name} expects (STRING, INTEGER)'
                )
            require_count(name, args[1])
            require_scratch_fit(args[0], f'{name} source')
            return 'STRING'
        if name == 'MID$':
            arity(3)
            if [expression(arg) for arg in args] != ['STRING', 'INTEGER', 'INTEGER']:
                raise SourceError(
                    expr.line, expr.column, 'MID$ expects (STRING, INTEGER, INTEGER)'
                )
            require_mid_start(args[1])
            require_count('MID$', args[2])
            require_scratch_fit(args[0], 'MID$ source')
            return 'STRING'
        if name in ('UCASE$', 'LCASE$'):  # M5c
            arity(1)
            if expression(args[0]) != 'STRING':
                raise SourceError(args[0].line, args[0].column, f'{name} expects a STRING')
            return 'STRING'
        if name == 'TEXTWIDTH':  # M11 corrective: font-7 width in pixels (os_dialog_string_width)
            arity(1)
            if expression(args[0]) != 'STRING':
                raise SourceError(args[0].line, args[0].column, 'TEXTWIDTH expects a STRING')
            require_scratch_fit(args[0], name)
            return 'INTEGER'
        if name in ('BITMAPW', 'BITMAPH'):  # M12: a bitmap's current width / height
            arity(1)
            bitmap_var(args[0], name)
            return 'INTEGER'
        if name in ('TYPEWIDTH', 'TYPEHEIGHT'):  # M15: screen typography, in pixels
            if not has_canvas:
                raise SourceError(expr.line, expr.column, f'{name} measures for DRAW TYPE: the program has no CANVAS')
            arity(1 if name == 'TYPEWIDTH' else 0)
            if args and expression(args[0]) != 'STRING':
                raise SourceError(args[0].line, args[0].column, 'TYPEWIDTH expects a STRING')
            if args:
                require_scratch_fit(args[0], name)
            return 'INTEGER'
        if name == 'PAGEWIDTH':  # M12: printed width in points (os_typo_charwidth)
            arity(1)
            if expression(args[0]) != 'STRING':
                raise SourceError(args[0].line, args[0].column, 'PAGEWIDTH expects a STRING')
            require_scratch_fit(args[0], name)
            return 'INTEGER'
        if name == 'POINT':  # M12: a canvas pixel, 1 black / 0 white (bios_getpxl)
            if not has_canvas:
                raise SourceError(expr.line, expr.column, 'POINT reads the canvas: the program has no CANVAS')
            arity(2)
            for arg in args:
                if expression(arg) != 'INTEGER':
                    raise SourceError(arg.line, arg.column, 'POINT expects INTEGER x, y')
            return 'INTEGER'
        if name == 'SECONDS':  # M11 corrective: seconds past the hour (bios_gettime)
            arity(0)
            return 'INTEGER'
        if name == 'CLOCKTICKS':  # M13 corrective: 1/16 s within the minute (bios_gettime)
            arity(0)
            return 'INTEGER'
        if name == 'KEYDOWN':  # M13: a key held down now (bios_keystate, a set-2 scan code)
            arity(1)
            if expression(args[0]) != 'INTEGER':
                raise SourceError(args[0].line, args[0].column, 'KEYDOWN expects an INTEGER key code')
            return 'BOOLEAN'
        if name in ('VAL', 'ASC'):  # M5b
            arity(1)
            if expression(args[0]) != 'STRING':
                raise SourceError(args[0].line, args[0].column, f'{name} expects a STRING')
            require_scratch_fit(args[0], name)
            return 'INTEGER'
        if name == 'CHR$':  # M5b
            arity(1)
            if expression(args[0]) != 'INTEGER':
                raise SourceError(args[0].line, args[0].column, 'CHR$ expects an INTEGER')
            code = constant_int(args[0])
            if code is not None and not 1 <= code <= 255:
                raise SourceError(
                    args[0].line, args[0].column,
                    f'CHR$ character code must be 1..255, got {code} '
                    '(0 cannot be part of a STRING)',
                )
            return 'STRING'
        if name == 'INSTR':  # M5b: INSTR(a$, b$) or INSTR(start, a$, b$)
            if len(args) not in (2, 3):
                raise SourceError(
                    expr.line, expr.column, f'INSTR expects 2 or 3 arguments, got {len(args)}'
                )
            want = ['STRING', 'STRING'] if len(args) == 2 else ['INTEGER', 'STRING', 'STRING']
            if [expression(arg) for arg in args] != want:
                raise SourceError(
                    expr.line, expr.column,
                    'INSTR expects (STRING, STRING) or (INTEGER, STRING, STRING)',
                )
            if len(args) == 3:
                start = constant_int(args[0])
                if start is not None and start < 1:
                    raise SourceError(
                        args[0].line, args[0].column,
                        'INSTR start position must be at least 1 (positions are 1-based)',
                    )
            for arg in args[-2:]:
                require_scratch_fit(arg, 'INSTR')
            return 'INTEGER'
        if name in ('ABS', 'SGN'):  # M7 (REAL as well, once REAL exists)
            arity(1)
            got = expression(args[0])
            if got not in NUMERIC:
                raise SourceError(args[0].line, args[0].column, f'{name} expects a number')
            return got if name == 'ABS' else 'INTEGER'
        if name in ('MIN', 'MAX'):  # M7
            arity(2)
            a, b = expression(args[0]), expression(args[1])
            if a not in NUMERIC or b not in NUMERIC:
                raise SourceError(expr.line, expr.column,
                                  f'{name} expects two numbers, got {a} and {b}')
            return 'REAL' if 'REAL' in (a, b) else 'INTEGER'
        if name in REAL_FUNCTIONS or name == 'CINT':  # M7
            arity(1)
            if expression(args[0]) not in NUMERIC:
                raise SourceError(args[0].line, args[0].column, f'{name} expects a number')
            return 'INTEGER' if name == 'CINT' else 'REAL'
        if name in ('REALVAL', 'ISNUM'):  # M7
            arity(1)
            if expression(args[0]) != 'STRING':
                raise SourceError(args[0].line, args[0].column, f'{name} expects a STRING')
            require_scratch_fit(args[0], name)
            return 'REAL' if name == 'REALVAL' else 'BOOLEAN'
        if name in ('SHL', 'SHR', 'RND'):  # M7
            arity(2 if name != 'RND' else 1)
            if any(expression(a) != 'INTEGER' for a in args):
                raise SourceError(expr.line, expr.column, f'{name} expects INTEGER arguments')
            if name == 'RND' and constant_int(args[0]) is not None and constant_int(args[0]) < 1:
                raise SourceError(args[0].line, args[0].column, 'RND(n) needs n of at least 1')
            return 'INTEGER'
        if name in _TRIMS:  # M7
            arity(1)
            if expression(args[0]) != 'STRING':
                raise SourceError(args[0].line, args[0].column, f'{name} expects a STRING')
            return 'STRING'
        if name in DB_FUNCTIONS:  # M10
            if name == 'DBRECOVERED':
                arity(0)
                if not any(isinstance(n, ast.DbOp) and n.op == 'LOAD' for n in nodes):
                    raise SourceError(expr.line, expr.column, 'DBRECOVERED reports on DB LOAD: the program has none')
                return 'INTEGER'
            arity(3 if name == 'DBFIND' else 1)
            var = database(args[0], name)
            first_field_id(var, expr.line, expr.column, name)
            for arg in args[1:]:
                if expression(arg) != 'INTEGER':
                    raise SourceError(arg.line, arg.column, f'{name} expects INTEGER arguments after the database')
            return 'INTEGER'
        if name in TEXT_FUNCTIONS:  # M9 Stage C
            kinds, result = TEXT_FUNCTIONS[name]
            arity(1 + len(kinds))
            text_buffer(args[0], name)
            for arg, want in zip(args[1:], kinds):
                if want == 'TEXT':  # M10 TEXTSAME: a second buffer
                    text_buffer(arg, name)
                    continue
                got = expression(arg)
                if got != want:
                    raise SourceError(arg.line, arg.column, f'{name} expects {want} here, got {got}')
            return result
        if name in CANVAS_EVENT_NAMES:  # M9: the last canvas mouse / key event
            if not has_canvas:
                raise SourceError(expr.line, expr.column,
                                  f'{name} reports canvas events: the program has no CANVAS')
            arity(0)
            return 'INTEGER'
        if name in ('EOF', 'IOERR'):  # M7 files
            if not has_files:
                raise SourceError(expr.line, expr.column,
                                  f'{name} reports on file operations, and the program has none (OPEN, KILL, NAME, '
                                  'TEXT LOAD or SAVE, DB, BITMAP LOAD or SAVE, PAGE)')  # M14 (D12): the full list
            if name == 'IOERR':
                arity(0)
                return 'INTEGER'
            arity(1)
            if not isinstance(args[0], ast.IntLiteral) or args[0].value not in (1, 2):
                raise SourceError(args[0].line, args[0].column, 'EOF expects a channel number, 1 or 2')
            return 'BOOLEAN'
        if name in ('SPACE$', 'STRING$'):  # M7: SPACE$(n), STRING$(n, code)
            arity(1 if name == 'SPACE$' else 2)
            if any(expression(a) != 'INTEGER' for a in args):
                raise SourceError(expr.line, expr.column,
                                  f'{name} expects INTEGER arguments' +
                                  (' (n, character code)' if name == 'STRING$' else ''))
            require_count(name, args[0])
            if name == 'STRING$':
                code = constant_int(args[1])
                if code is not None and not 1 <= code <= 255:
                    raise SourceError(args[1].line, args[1].column,
                                      f'STRING$ character code must be 1..255, got {code}')
            return 'STRING'
        raise SourceError(expr.line, expr.column, f'unknown function {name}')

    def require_count(name: str, arg) -> None:
        """A substring count is any INTEGER expression (M5a); a constant one
        is checked here, a computed one at run time (spec section 3)."""
        value = constant_int(arg)
        if value is not None and value < 0:
            raise SourceError(
                arg.line,
                arg.column,
                f'{name} count must be at least 0 (counts are non-negative)',
            )

    def require_mid_start(arg) -> None:
        """MID$ start is 1-based: a constant start must be at least 1; a
        computed one is checked at run time (M5a)."""
        value = constant_int(arg)
        if value is not None and value < 1:
            raise SourceError(
                arg.line,
                arg.column,
                'MID$ start position must be at least 1 (positions are 1-based)',
            )

    def require_scratch_fit(operand, context: str) -> None:
        """A computed operand (STR$, substring, concatenation) is built in a
        runtime scratch buffer; its worst-case length must fit
        (SCRATCH_STRING_MAX)."""
        if isinstance(operand, (ast.StrLiteral, ast.Var)):
            return  # used in place, no copy
        _, hi = string_length_bounds(operand, variables)
        if hi > SCRATCH_STRING_MAX:
            raise SourceError(
                operand.line,
                operand.column,
                f'{context} operand may be up to {hi} characters; computed '
                f'strings used by {context} are limited to {SCRATCH_STRING_MAX}',
            )

    def literal_index(name: str, index, var) -> None:
        """M14 (D8): a literal index outside 1..n is certain to fail: a compile error, not
        the runtime error "index out of range" (a computed index is checked when it runs)."""
        if var is None or var.length is None:
            return
        value = None
        if isinstance(index, ast.IntLiteral):
            value = index.value
        elif (isinstance(index, ast.Unary) and index.op == '-'
              and isinstance(index.operand, ast.IntLiteral)):
            value = -index.operand.value
        if value is not None and not 1 <= value <= var.length:
            raise SourceError(index.line, index.column,
                              f'{display_name(name)}({value}) is outside the array: its elements '
                              f'are {display_name(name)}(1) to {display_name(name)}({var.length})')

    # ------------------------------------------------------------ declarations
    def declare(name: str, typ: str, line: int, column: int, origin: str,
                length: int | None = None, capacity: int | None = None, banked: bool = False) -> None:
        """Declare a variable; DIM is unique, widget bindings may agree."""
        old = variables.get(name)
        if old is not None and (old.length is not None or length is not None):
            what = name + (' is an array' if old.length is not None else ' is not an array')
            raise SourceError(
                line, column,
                f'{what} (first declared at line {old.line}); '
                'an array is declared once, with DIM, and bound only to a LIST or CHOICE',
            )
        if old is not None:
            if capacity is not None and capacity != old.capacity:
                raise SourceError(
                    line, column,
                    f'DIM {name} AS STRING * {capacity - 1} must come before the {old.origin} '
                    f'at line {old.line}, which already gave {name} the capacity {old.capacity}',
                )
            if origin == 'DIM' and old.origin == 'DIM':
                raise SourceError(
                    line,
                    column,
                    f'duplicate declaration of {name} (first at line {old.line})',
                )
            if old.type != typ:
                raise SourceError(
                    line,
                    column,
                    f'{name} has incompatible UI bindings ({old.type} and {typ})',
                )
            return  # compatible: DIM + widget of the same type, or a repeat
        if name.endswith('$') and typ != 'STRING':
            raise SourceError(
                line,
                column,
                f'{name} uses $ suffix but is declared {typ}; expected STRING',
            )
        variables[name] = Variable(
            name=name,
            type=typ,
            capacity=(capacity or string_capacity) if typ == 'STRING' else (
                capacity if typ == 'RECORD' else None),
            origin=origin,
            line=line,
            column=column,
            length=length,
            banked=banked,
        )

    def require_window(node, kind: str) -> None:
        if not has_window:
            raise SourceError(
                node.line, node.column, f'{kind} requires a WINDOW declaration'
            )

    def literal_ui_text(node, kind: str, field: str, expr, max_len: int, prefix: str) -> str:
        """Validate a Rosanne-facing text position: STRING, literal, ASCII, length."""
        if not isinstance(expr, ast.StrLiteral):
            got = expression(expr)
            if got != 'STRING':
                where = 'caption expects' if field == 'caption' else 'expects'
                raise SourceError(
                    node.line, node.column, f'{kind} {where} STRING, got {got}'
                )
            if kind == 'LABEL':
                raise SourceError(
                    node.line,
                    node.column,
                    'LABEL text must be a string literal or a STRING variable',
                )
            raise SourceError(
                node.line, node.column, f'{kind} {field} must be a string literal'
            )
        value = expr.value
        if not value.isascii():
            raise SourceError(
                node.line,
                node.column,
                f'{kind} {field} must be ASCII for Rosanne display',
            )
        size = len(value.encode('utf-8'))
        if size > max_len:
            raise SourceError(
                node.line,
                node.column,
                f'{prefix} is {size} characters; the maximum is {max_len}',
            )
        return value

    def caption(node, kind: str, max_len: int) -> str | None:
        if node.caption is None:
            return None
        return literal_ui_text(node, kind, 'caption', node.caption, max_len, f'{kind} caption')

    pending_lists: list[Widget] = []  # M6 Phase 2: arrays are checked once all are declared
    windows: list[WindowDecl] = []
    window_counts: list[dict] = []
    pending: list[Widget] = []  # controls before any WINDOW (legacy single window)
    pending_counts = {'LABEL': 0, 'CHECKBOX': 0, 'BUTTON': 0, 'RADIO': 0, 'keys': set()}
    menus: list[MenuDecl] = []
    menu_keys: dict[str, int] = {}
    timer: TimerDecl | None = None
    on_stop = None  # M15: (FUNCTION, line) of ON STOP

    def current():
        """The widget list and caps of the WINDOW controls attach to."""
        if windows:
            return windows[-1].widgets, window_counts[-1]
        return pending, pending_counts

    def bump(node, kind: str, cap: int, counts) -> None:
        counts[kind] += 1
        if counts[kind] > cap:
            raise SourceError(
                node.line,
                node.column,
                f'too many {kind}s: {counts[kind]} declared, the maximum is {cap}',
            )

    def menu_text(node, expr, max_len: int, what: str) -> str:
        if not isinstance(expr, ast.StrLiteral):
            raise SourceError(node.line, node.column, f'{what} must be a string literal')
        value = expr.value
        if not value or any(not (0x20 <= ord(c) <= 0x7E) or c == '|' for c in value):
            raise SourceError(
                node.line, node.column,
                f'{what} must be 1..{max_len} printable ASCII characters without |',
            )
        if len(value) > max_len:
            raise SourceError(
                node.line, node.column,
                f'{what} is {len(value)} characters; the maximum is {max_len}',
            )
        return value

    banked_blocks = [0]  # M8: 16K blocks of all BANKED arrays so far
    inferred: list = []  # M7: SELECT CASE selector temporaries, typed below
    for node in nodes:
        if isinstance(node, ast.Dim) and node.type_name == '?':
            inferred.append(node.name)
        elif isinstance(node, ast.Dim):
            if node.banked:  # M8
                if node.length is None:
                    raise SourceError(node.line, node.column,
                                      f'only an array can be BANKED: DIM {node.name}(n) AS {node.type_name} BANKED')
                if not 1 <= node.length <= BANKED_LENGTH_MAX:
                    raise SourceError(node.line, node.column,
                                      f'a BANKED array has 1 to {BANKED_LENGTH_MAX} elements, got {node.length}')
            elif node.length is not None and not 1 <= node.length <= ARRAY_LENGTH_MAX:
                raise SourceError(
                    node.line, node.column,
                    f'an array has 1 to {ARRAY_LENGTH_MAX} elements, got {node.length}'
                    + (' (a larger array can be BANKED)' if node.length <= BANKED_LENGTH_MAX else ''),
                )
            if node.type_name == 'BITMAPREF':  # M13: a BITMAP parameter (pbas/lower.py)
                declare(node.name, 'BITMAPREF', node.line, node.column, 'DIM', None, None, False)
                continue
            if node.type_name == 'BITMAP':  # M12
                if '.' in node.name or node.length is not None or node.banked or node.bitmap_size is None:
                    raise SourceError(node.line, node.column,
                                      f'declare a bitmap as DIM {node.name} AS BITMAP * width, height '
                                      '(at the top level; it is always in banked memory)')
                bw, bh = node.bitmap_size
                if not (1 <= bw <= CANVAS_MAX_W and 1 <= bh <= CANVAS_MAX_H) or (bw + 7) // 8 * bh > BLOCK_SIZE:
                    raise SourceError(node.line, node.column,
                                      f'a BITMAP is 1 to {CANVAS_MAX_W} pixels wide and 1 to {CANVAS_MAX_H} high, '
                                      f'and (width + 7) \\ 8 * height at most {BLOCK_SIZE} bytes '
                                      f'(one 16K block); got {bw} x {bh}')
                declare(node.name, 'BITMAP', node.line, node.column, 'DIM', None, None, False)
                variables[node.name].bitmap_size = (bw, bh)
                banked_blocks[0] += 1
                if banked_blocks[0] > BANKED_BLOCKS_MAX:
                    raise SourceError(node.line, node.column,
                                      f'BANKED arrays, TEXT buffers and BITMAPs may use at most {BANKED_BLOCKS_MAX} '
                                      f'16K blocks together; this one brings the total to {banked_blocks[0]}')
                continue
            if node.type_name == 'TEXT':  # M9 Stage C
                if '.' in node.name:
                    raise SourceError(node.line, node.column,
                                      'a TEXT buffer is declared with DIM at the top level, '
                                      'not as a parameter, LOCAL or FUNCTION result')
                if node.length is not None or node.banked or node.capacity is None \
                        or not 1 <= node.capacity <= TEXT_BYTES_MAX:
                    raise SourceError(node.line, node.column,
                                      f'declare a text buffer as DIM {node.name} AS TEXT * bytes '
                                      f'(1 to {TEXT_BYTES_MAX} bytes; it is always in banked memory)')
                declare(node.name, 'TEXT', node.line, node.column, 'DIM', None, node.capacity, False)
                variables[node.name].text_bytes = node.capacity
                banked_blocks[0] += -(-node.capacity // BLOCK_SIZE)
                if banked_blocks[0] > BANKED_BLOCKS_MAX:
                    raise SourceError(node.line, node.column,
                                      f'BANKED arrays and TEXT buffers may use at most {BANKED_BLOCKS_MAX} '
                                      f'16K blocks together; this one brings the total to {banked_blocks[0]}')
                continue
            if node.capacity is not None and not 2 <= node.capacity <= 127:
                raise SourceError(node.line, node.column,
                                  f'STRING * n holds 1 to 126 characters, got {node.capacity - 1}')
            if node.length is not None and node.name in _BUILTINS:
                raise SourceError(node.line, node.column, f'{node.name} is a built-in function')
            layout = getattr(node, 'record', None)
            if layout is not None:  # M10: a record (variable or array)
                declare(node.name, 'RECORD', node.line, node.column, 'DIM', node.length,
                        layout.size, node.banked)
                variables[node.name].record = layout.name
            else:
                declare(node.name, node.type_name, node.line, node.column, 'DIM', node.length,
                        node.capacity, node.banked)
            if getattr(node, 'alias', None) is not None:  # M10: a field shares its record's storage
                variables[node.name].alias = node.alias
                continue
            if node.banked:
                var = variables[node.name]
                banked_blocks[0] += banked_layout(var)[2]
                if banked_blocks[0] > BANKED_BLOCKS_MAX:
                    raise SourceError(node.line, node.column,
                                      f'BANKED arrays may use at most {BANKED_BLOCKS_MAX} 16K blocks together '
                                      f'({BANKED_BLOCKS_MAX * 16}K); this one brings the total to {banked_blocks[0]}')
        elif isinstance(node, ast.Sub):
            subs[node.name] = node
        elif isinstance(node, ast.Window):
            if windows and windows[0].name is None and node.name is None:
                raise SourceError(
                    node.line,
                    node.column,
                    'multiple WINDOW declarations are not allowed '
                    '(exactly one per program)',
                )
            if windows and (windows[0].name is None or node.name is None):
                raise SourceError(
                    node.line,
                    node.column,
                    'a program has one unnamed WINDOW or up to '
                    f'{MAX_WINDOWS} named ones (WINDOW Name, "title"), not both',
                )
            if any(w.name == node.name for w in windows):
                raise SourceError(node.line, node.column, f'duplicate WINDOW {node.name}')
            if len(windows) == MAX_WINDOWS:
                raise SourceError(
                    node.line, node.column, f'too many WINDOWs: the maximum is {MAX_WINDOWS}'
                )
            title = literal_ui_text(
                node, 'WINDOW', 'title', node.title, WINDOW_TITLE_MAX, 'WINDOW title'
            )
            windows.append(WindowDecl(node.name, title, node.large, [], node.line, node.column))
            window_counts.append({'LABEL': 0, 'CHECKBOX': 0, 'BUTTON': 0, 'RADIO': 0, 'keys': set()})
            if dialog_title is None:
                dialog_title = title
                dialog_position = (node.line, node.column)
        elif isinstance(node, ast.Label):
            require_window(node, 'LABEL')
            target, counts = current()
            bump(node, 'LABEL', MAX_LABELS, counts)
            if isinstance(node.text, ast.Var):
                # M5d: a label showing a STRING variable (one-way binding)
                name = node.text.name
                old = variables.get(name)
                if old is not None and old.type != 'STRING':
                    raise SourceError(
                        node.text.line,
                        node.text.column,
                        f'LABEL shows a STRING variable; {name} is {old.type} '
                        '(use a STRING and STR$)',
                    )
                declare(name, 'STRING', node.line, node.column, 'LABEL')
                widget = Widget('LABEL', None, name, None, node.line, node.column)
                bindings.append(Binding(name, 'LABEL', DYNAMIC_LABEL_MAX + 1, node.line))
            else:
                text = literal_ui_text(
                    node, 'LABEL', 'text', node.text, LABEL_TEXT_MAX, 'LABEL text'
                )
                widget = Widget('LABEL', text, None, None, node.line, node.column)
            target.append(widget)
            widgets.append(widget)
        elif isinstance(node, ast.Textbox):
            require_window(node, 'TEXTBOX')
            target, _ = current()
            cap = caption(node, 'TEXTBOX', CAPTION_MAX)
            declare(node.name, 'STRING', node.line, node.column, 'TEXTBOX')
            # M8: the box holds what its variable holds (STRING * n, or the
            # program-wide capacity); never more, or typing would overrun it
            box_capacity = variables[node.name].capacity
            _require_textbox_capacity(node.name, box_capacity, node.line, node.column)
            widget = Widget('TEXTBOX', cap, node.name, None, node.line, node.column)
            target.append(widget)
            widgets.append(widget)
            bindings.append(Binding(node.name, 'TEXTBOX', box_capacity, node.line))
        elif isinstance(node, ast.Checkbox):
            require_window(node, 'CHECKBOX')
            target, counts = current()
            bump(node, 'CHECKBOX', MAX_CHECKBOXES, counts)
            cap = caption(node, 'CHECKBOX', CAPTION_MAX)
            declare(node.name, 'BOOLEAN', node.line, node.column, 'CHECKBOX')
            widget = Widget('CHECKBOX', cap, node.name, None, node.line, node.column)
            target.append(widget)
            widgets.append(widget)
            bindings.append(Binding(node.name, 'CHECKBOX', None, node.line))
        elif isinstance(node, ast.Radio):  # M6
            require_window(node, 'RADIO')
            target, counts = current()
            bump(node, 'RADIO', MAX_RADIO_GROUPS, counts)
            if not RADIO_OPTIONS_MIN <= len(node.captions) <= RADIO_OPTIONS_MAX:
                raise SourceError(
                    node.line, node.column,
                    f'RADIO needs {RADIO_OPTIONS_MIN} to {RADIO_OPTIONS_MAX} options, '
                    f'got {len(node.captions)}',
                )
            options = tuple(
                literal_ui_text(node, 'RADIO', 'caption', c, CAPTION_MAX, 'RADIO caption')
                for c in node.captions
            )
            declare(node.name, 'INTEGER', node.line, node.column, 'RADIO')
            widget = Widget('RADIO', None, node.name, None, node.line, node.column, options=options)
            target.append(widget)
            widgets.append(widget)
            bindings.append(Binding(node.name, 'RADIO', None, node.line))
        elif isinstance(node, ast.Numberbox):  # M6
            require_window(node, 'NUMBERBOX')
            target, _ = current()
            cap = caption(node, 'NUMBERBOX', CAPTION_MAX)
            low = -32768 if node.low is None else node.low
            high = 32767 if node.high is None else node.high
            if low > high:
                raise SourceError(
                    node.line, node.column, f'NUMBERBOX MIN {low} is greater than MAX {high}'
                )
            declare(node.name, 'INTEGER', node.line, node.column, 'NUMBERBOX')
            widget = Widget('NUMBERBOX', cap, node.name, None, node.line, node.column,
                            low=low, high=high, spin=node.spin)
            target.append(widget)
            widgets.append(widget)
            bindings.append(Binding(node.name, 'NUMBERBOX', None, node.line))
        elif isinstance(node, ast.ListCtl):  # M6 Phase 2: LIST / CHOICE
            require_window(node, node.kind)
            target, _ = current()
            cap = caption(node, node.kind, CAPTION_MAX)
            rows = 5 if node.rows is None else node.rows
            if node.kind == 'LIST' and not 2 <= rows <= 12:
                raise SourceError(node.line, node.column, 'LIST ROWS must be 2 to 12')
            declare(node.name, 'INTEGER', node.line, node.column, node.kind)
            widget = Widget(node.kind, cap, node.name, None, node.line, node.column,
                            items=node.items, count=node.count, rows=rows,
                            change=node.change, action=node.action)
            target.append(widget)
            widgets.append(widget)
            bindings.append(Binding(node.name, node.kind, None, node.line))
            pending_lists.append(widget)
        elif isinstance(node, ast.Canvas):  # M9
            require_window(node, 'CANVAS')
            unnamed = next((c for c in canvases if c.canvas_name is None), None)
            if canvases and (node.name is None or unnamed is not None):  # M15: several, each named
                at = node if node.name is None else unnamed
                raise SourceError(at.line, at.column,
                                  'with more than one CANVAS each needs a name: CANVAS Name, width, height '
                                  f'(the other is at line {canvases[0].line if at is node else node.line})')
            if len(canvases) == CANVAS_MAX_N:
                raise SourceError(node.line, node.column, f'a program may have at most {CANVAS_MAX_N} canvases')
            if node.name is not None:
                twin = next((c for c in canvases if c.canvas_name == node.name), None)
                if twin is not None:
                    raise SourceError(node.line, node.column,
                                      f'CANVAS {node.name} is already declared at line {twin.line}')
            if not CANVAS_MIN <= node.width <= CANVAS_MAX_W or not CANVAS_MIN <= node.height <= CANVAS_MAX_H:
                raise SourceError(node.line, node.column,
                                  f'CANVAS width must be {CANVAS_MIN} to {CANVAS_MAX_W} and height '
                                  f'{CANVAS_MIN} to {CANVAS_MAX_H} pixels, got {node.width} x {node.height}')
            target, _ = current()
            widget = Widget('CANVAS', None, None, None, node.line, node.column,
                            width=node.width, height=node.height, paint=node.paint,
                            mouse=node.mouse, keys_handler=node.keys, canvas_name=node.name)
            canvases.append(widget)
            target.append(widget)
            widgets.append(widget)
        elif isinstance(node, ast.Slider):  # M6 Phase 2
            require_window(node, 'SLIDER')
            target, _ = current()
            cap = caption(node, 'SLIDER', CAPTION_MAX)
            if not 1 <= node.high - node.low <= SLIDER_RANGE_MAX:
                raise SourceError(
                    node.line, node.column,
                    f'SLIDER MAX - MIN must be 1 to {SLIDER_RANGE_MAX}, got {node.high - node.low}',
                )
            declare(node.name, 'INTEGER', node.line, node.column, 'SLIDER')
            widget = Widget('SLIDER', cap, node.name, None, node.line, node.column,
                            low=node.low, high=node.high, change=node.change)
            target.append(widget)
            widgets.append(widget)
            bindings.append(Binding(node.name, 'SLIDER', None, node.line))
        elif isinstance(node, ast.Button):
            require_window(node, 'BUTTON')
            target, counts = current()
            bump(node, 'BUTTON', MAX_BUTTONS, counts)
            cap = caption(node, 'BUTTON', BUTTON_CAPTION_MAX)
            if node.default:
                first = next((w for w in target if w.kind == 'BUTTON' and w.default), None)
                if first is not None:
                    raise SourceError(
                        node.line,
                        node.column,
                        f'only one BUTTON may be DEFAULT (the first is at line {first.line})',
                    )
            if len(node.keys) > MAX_BUTTON_KEYS:
                raise SourceError(
                    node.line, node.column,
                    f'a BUTTON may have at most {MAX_BUTTON_KEYS} KEYs',
                )
            for key in node.keys:
                if key in counts['keys']:
                    raise SourceError(
                        node.line, node.column,
                        f'KEY {key} already belongs to another BUTTON of this window',
                    )
                counts['keys'].add(key)
            index = len(widgets)
            widget = Widget('BUTTON', cap, None, node.handler, node.line, node.column,
                            node.default, keys=tuple(node.keys))
            target.append(widget)
            widgets.append(widget)
            handlers.append(Handler(index, node.handler, node.line))
        elif isinstance(node, ast.Menu):  # M6
            require_window(node, 'MENU')
            if len(menus) == MAX_MENUS:
                raise SourceError(
                    node.line, node.column, f'too many MENUs: the maximum is {MAX_MENUS}'
                )
            title = menu_text(node, node.title, MENU_TITLE_MAX, 'MENU title')
            menus.append(MenuDecl(title, [], node.line, node.column))
        elif isinstance(node, ast.Item):  # M6 (pbas.parser puts it inside a MENU)
            menu = menus[-1]
            if len(menu.items) == MENU_ITEMS_MAX:
                raise SourceError(
                    node.line, node.column,
                    f'a MENU has at most {MENU_ITEMS_MAX} ITEMs (dividers included)',
                )
            if isinstance(node.text, ast.StrLiteral) and node.text.value == '-':
                if node.handler is not None:
                    raise SourceError(node.line, node.column, 'a divider ITEM "-" has no handler')
                menu.items.append(MenuItem('-', None, None, None, node.line, node.column))
                continue
            text = menu_text(node, node.text, MENU_ITEM_MAX, 'ITEM text')
            if node.handler is None:
                raise SourceError(
                    node.line, node.column, 'ITEM needs a handler: ITEM "text", SubName'
                )
            if node.key is not None:
                if node.key in menu_keys:
                    raise SourceError(
                        node.line, node.column,
                        f'menu KEY "{node.key}" is already used at line {menu_keys[node.key]}',
                    )
                menu_keys[node.key] = node.line
            if node.tick is not None:
                old = variables.get(node.tick)
                if old is not None and old.type != 'BOOLEAN':
                    raise SourceError(
                        node.line, node.column,
                        f'TICK shows a BOOLEAN; {node.tick} is {old.type}',
                    )
                declare(node.tick, 'BOOLEAN', node.line, node.column, 'TICK')
            menu.items.append(
                MenuItem(text, node.handler, node.key, node.tick, node.line, node.column)
            )
        elif isinstance(node, ast.EndMenu):
            if not menus[-1].items:
                raise SourceError(node.line, node.column, 'a MENU needs at least one ITEM')
        elif isinstance(node, ast.OnStop):  # M15
            require_window(node, 'ON STOP')
            if on_stop is not None:
                raise SourceError(node.line, node.column,
                                  f'only one ON STOP is allowed (the first is at line {on_stop[1]})')
            on_stop = (node.handler, node.line)
        elif isinstance(node, ast.Timer):  # M6
            require_window(node, 'TIMER')
            if timer is not None:
                raise SourceError(
                    node.line, node.column,
                    f'only one TIMER is allowed (the first is at line {timer.line})',
                )
            if node.ticks and not 1 <= node.seconds <= TIMER_TICKS_MAX:  # M13
                raise SourceError(
                    node.line, node.column,
                    f'TIMER interval must be 1..{TIMER_TICKS_MAX} TICKS (sixteenths of a second)',
                )
            if not node.ticks and not 1 <= node.seconds <= TIMER_SECONDS_MAX:
                raise SourceError(
                    node.line, node.column,
                    f'TIMER interval must be 1..{TIMER_SECONDS_MAX} seconds',
                )
            timer = TimerDecl(node.handler, node.seconds, node.line, node.column, node.ticks)

    for widget in pending_lists:  # M6 Phase 2
        array = variables.get(widget.items)
        if array is None or array.length is None or array.type != 'STRING':
            raise SourceError(
                widget.line, widget.column,
                f'{widget.kind} shows a STRING array: {widget.items} must be declared '
                f'with DIM {widget.items}(n) AS STRING',
            )
        if array.banked:  # M8: Rosanne would draw items from the program's bank
            raise SourceError(widget.line, widget.column,
                              f'{widget.kind} cannot show the BANKED array {widget.items}: '
                              'copy the items into an ordinary array')
        widget.length = array.length
        count = widget.count
        if isinstance(count, ast.IntLiteral):
            low = 1 if widget.kind == 'CHOICE' else 0  # a CHOICE always shows an item (XAnne)
            if not low <= count.value <= array.length:
                raise SourceError(
                    widget.line, widget.column,
                    f'{widget.kind} count must be {low} to {array.length} (the length of {widget.items})',
                )
        elif isinstance(count, ast.Var):
            var = variables.get(count.name)
            if var is None or var.type != 'INTEGER' or var.length is not None:
                raise SourceError(
                    widget.line, widget.column,
                    f'{widget.kind} count must be an INTEGER variable or literal',
                )
        else:
            raise SourceError(
                widget.line, widget.column,
                f'{widget.kind} count must be an INTEGER variable or literal',
            )

    if pending and windows:
        if windows[0].name is not None:
            first = pending[0]
            raise SourceError(
                first.line, first.column,
                f'{first.kind} must follow the WINDOW it belongs to (named windows)',
            )
        windows[0].widgets[:0] = pending

    for node in nodes:  # M14 (D6): remember which globals a procedure's DIM declared (pbas/lint.py)
        if isinstance(node, ast.Dim) and getattr(node, 'in_proc', None) and node.name in variables:
            variables[node.name].dim_in = node.in_proc

    for name, sub in subs.items():
        if name in variables:
            raise SourceError(
                sub.line, sub.column, f'{name} is both a SUB and a variable'
            )

    # ------------------------------------------------- arrays (M6 Phase 2)
    arrays = {name for name, var in variables.items() if var.length is not None}

    def rewrite(expr):
        """Name(index) of a declared array is an element, not a call."""
        if isinstance(expr, ast.Var) and expr.name in ('IOERR', 'DBRECOVERED') and expr.name not in variables:
            return ast.Call(expr.line, expr.column, expr.name, [])  # M7: a status function; M10
        if (isinstance(expr, ast.Var) and expr.name in ('SECONDS', 'CLOCKTICKS', 'TYPEHEIGHT')
                and expr.name not in variables):
            return ast.Call(expr.line, expr.column, expr.name, [])  # M11: the clock; M13 corrective
        if (isinstance(expr, ast.Var) and expr.name in CANVAS_EVENT_NAMES and has_canvas
                and expr.name not in variables):
            return ast.Call(expr.line, expr.column, expr.name, [])  # M9: an event value
        if isinstance(expr, ast.Var) and expr.name == 'PI' and 'PI' not in variables:
            literal = ast.RealLiteral(expr.line, expr.column, float(PI_TEXT))  # M7
            literal.text = PI_TEXT
            return literal
        if isinstance(expr, ast.Call):
            args = [rewrite(a) for a in expr.args]
            if expr.name in arrays:
                if len(args) != 1:
                    raise SourceError(
                        expr.line, expr.column, f'{expr.name} is an array: use {expr.name}(index)'
                    )
                return ast.Index(expr.line, expr.column, expr.name, args[0])
            expr.args = args
            return expr
        if isinstance(expr, ast.Unary):
            expr.operand = rewrite(expr.operand)
        elif isinstance(expr, ast.Binary):
            expr.left, expr.right = rewrite(expr.left), rewrite(expr.right)
        return expr

    for node in nodes:
        for name in ('value', 'condition', 'start', 'finish', 'step', 'filename', 'index', 'title', 'text',
                     'new_name', 'src_index'):
            if isinstance(getattr(node, name, None), ast.Expr):
                setattr(node, name, rewrite(getattr(node, name)))
        if isinstance(node, (ast.Draw, ast.TextOp, ast.DbOp, ast.BitmapOp, ast.PageOp)):  # M9; M10; M12
            node.values = [rewrite(v) for v in node.values]

    # M7: a SELECT CASE temporary has its selector's type (pbas/lower.py)
    for name in inferred:
        source = next(n for n in nodes if isinstance(n, ast.Assign) and n.name == name)
        typ = expression(source.value)
        variables[name] = Variable(name=name, type=typ,
                                   capacity=string_capacity if typ == 'STRING' else None,
                                   origin='DIM', line=source.line, column=source.column)

    # -------------------------------------------------------------- statements
    def check_filename(expr) -> None:
        if not isinstance(expr, ast.StrLiteral):
            raise SourceError(
                expr.line, expr.column,
                'this file name must be written in the program as a string, such as "NOTES.TXT", or be '
                'a CONST (OPEN, KILL, NAME, TEXT, DB and BITMAP statements also accept a STRING variable)'
            )
        if FILENAME_RE.fullmatch(expr.value) is None:
            raise SourceError(
                expr.line,
                expr.column,
                f'file name {expr.value!r} is not a valid DOS 8.3 name '
                f'({FILENAME_PATTERN_TEXT})',
            )
        stem = expr.value.split('.')[0].upper()
        if stem in RESERVED_NAMES:
            raise SourceError(
                expr.line,
                expr.column,
                f'file name {expr.value!r} uses the DOS device name {stem}; '
                'choose another name',
            )

    def check_db(node: ast.DbOp) -> None:
        """M10: DB LOAD / SAVE / NEW / DELETE / SORT / SEARCH (§5.9, §5.10)."""
        what = f'DB {node.op}'
        var = database(ast.Var(node.line, node.column, node.name), what)
        if node.op in ('NEW',):
            first_field_id(var, node.line, node.column, what)

        def count_var(value, writes):
            if writes and not (isinstance(value, ast.Var) and variables.get(value.name) is not None
                               and variables[value.name].type == 'INTEGER'
                               and variables[value.name].length is None):
                raise SourceError(value.line, value.column,
                                  f'{what} sets the record count: give a plain INTEGER variable')
            if expression(value) != 'INTEGER':
                raise SourceError(value.line, value.column, f'{what}: the record count is an INTEGER')

        def index_array(value):
            v = variables.get(value.name) if isinstance(value, ast.Var) else None
            if v is None or v.type != 'INTEGER' or v.length is None or v.alias is not None:
                raise SourceError(value.line, value.column,
                                  f'{what} fills an index: give an INTEGER array (DIM Order(n) AS INTEGER)')
            if v.banked:
                raise SourceError(value.line, value.column,
                                  f'{what}: the index is a resident INTEGER array (at most 250 entries); '
                                  'a BANKED index is not supported')
            value.typ = 'INTEGER'

        values = node.values
        if node.op in ('LOAD', 'SAVE'):
            count_var(values[0], node.op == 'LOAD')
            if isinstance(values[1], ast.StrLiteral):
                check_filename(values[1])
                if values[1].value.upper().rsplit('.', 1)[-1] in ('NEW', 'BAK') and '.' in values[1].value:
                    raise SourceError(values[1].line, values[1].column,
                                      f'{what}: .NEW and .BAK are the database\'s own temporary and '
                                      'backup files; give the file another extension')
            if expression(values[1]) != 'STRING':
                raise SourceError(values[1].line, values[1].column, f'{what}: the file name is a STRING')
        elif node.op == 'NEW':
            count_var(values[0], True)
        elif node.op == 'DELETE':
            count_var(values[0], True)
            if expression(values[1]) != 'INTEGER':
                raise SourceError(values[1].line, values[1].column, f'{what}: the record number is an INTEGER')
        else:  # SORT, SEARCH
            count_var(values[0], False)
            index_array(values[1])
            if node.op == 'SEARCH':
                count_var(values[2], True)
            field = variables.get(f'{node.name}%{node.key}')
            if field is None or field.alias is None:
                fields = [display_name(f.name).split('.')[-1] for f in variables.values()
                          if f.alias is not None and f.alias[0] == node.name]
                raise SourceError(node.line, node.column,
                                  f'TYPE {var.record} has no field {node.key}; its fields are '
                                  + ', '.join(fields))
            if field.type not in ('INTEGER', 'STRING', 'REAL') or \
                    (node.op == 'SEARCH' and field.type != 'STRING'):
                raise SourceError(node.line, node.column,
                                  f'{what} BY {node.key}: '
                                  + ('a text search needs a STRING field' if node.op == 'SEARCH'
                                     else 'sort by an INTEGER, REAL or STRING field'))
            if 'NOCASE' in node.flags and field.type != 'STRING':
                raise SourceError(node.line, node.column, f'{what}: NOCASE applies to a STRING field')
            if node.op == 'SEARCH' and expression(values[3]) != 'STRING':
                raise SourceError(values[3].line, values[3].column, f'{what}: the text to find is a STRING')

    def check_message(node: ast.Message) -> None:
        got = expression(node.value)
        if got != 'STRING':
            raise SourceError(
                node.line, node.column, f'MESSAGE expects STRING, got {got}'
            )
        # MESSAGE text enters a Rosanne alert (spec section 1: ASCII is
        # enforced where text enters Rosanne objects/alerts). Literal parts
        # are checked here; variable content is runtime data and cannot be.
        for part in _literal_parts(node.value):
            if not part.value.isascii():
                raise SourceError(
                    part.line,
                    part.column,
                    'MESSAGE text must be ASCII for Rosanne display',
                )
        if isinstance(node.value, ast.StrLiteral):
            size = len(node.value.value.encode('utf-8'))
            if size > MESSAGE_LITERAL_MAX:
                raise SourceError(
                    node.line,
                    node.column,
                    f'MESSAGE literal is {size} bytes; '
                    f'the maximum is {MESSAGE_LITERAL_MAX}',
                )
            return
        budget = dynamic_message_budget(node.value, variables)
        if budget > ALERT_BUFFER_SIZE:
            raise SourceError(
                node.line,
                node.column,
                f'MESSAGE may need up to {budget} bytes (literal text + string '
                f'capacities + 6 per STR$) but the alert buffer is '
                f'{ALERT_BUFFER_SIZE} bytes',
            )

    def check_for(node: ast.For) -> None:
        var = variables.get(node.name)
        if var is None:
            raise SourceError(
                node.line,
                node.column,
                f'FOR counter {node.name} must be declared with DIM',
            )
        if var.type != 'INTEGER':
            raise SourceError(
                node.line,
                node.column,
                f'FOR counter {node.name} must be INTEGER',
            )
        if expression(node.start) != 'INTEGER' or expression(node.finish) != 'INTEGER':
            raise SourceError(node.line, node.column, 'FOR bounds must be INTEGER')
        step = constant_int(node.step)  # M7: any non-zero INTEGER constant
        if step is None or step == 0:
            raise SourceError(
                node.step.line,
                node.step.column,
                'STEP must be a non-zero INTEGER constant (a literal or CONST)',
            )

    def check_ask(node: ast.Assign, var) -> None:
        """M6: `v = ASK(text, "b1", "b2" [, "b3"])` (LANGUAGE-SPEC §5.1)."""
        args = node.value.args
        if var.type != 'INTEGER':
            raise SourceError(
                node.line, node.column, f'ASK gives an INTEGER; {node.name} is {var.type}'
            )
        if not ASK_BUTTONS_MIN + 1 <= len(args) <= ASK_BUTTONS_MAX + 1:
            raise SourceError(
                node.value.line, node.value.column,
                f'ASK expects a question and {ASK_BUTTONS_MIN} or {ASK_BUTTONS_MAX} '
                f'button captions, got {len(args)} arguments',
            )
        if expression(args[0]) != 'STRING':
            raise SourceError(node.value.line, node.value.column, 'ASK question must be a STRING')
        for part in _literal_parts(args[0]):
            if not part.value.isascii():
                raise SourceError(part.line, part.column, 'ASK text must be ASCII')
        budget = dynamic_message_budget(args[0], variables)
        if budget > ASK_TEXT_MAX:
            raise SourceError(
                node.value.line, node.value.column,
                f'ASK question may need up to {budget} bytes; the maximum is {ASK_TEXT_MAX}',
            )
        for arg in args[1:]:
            if not isinstance(arg, ast.StrLiteral) or not arg.value.isascii() \
                    or not 1 <= len(arg.value) <= ASK_CAPTION_MAX:
                raise SourceError(
                    arg.line, arg.column,
                    f'ASK button captions are ASCII literals of 1 to {ASK_CAPTION_MAX} characters',
                )

    def check_assign(node: ast.Assign) -> None:
        var = variables.get(node.name)
        if var is None:
            raise SourceError(
                node.line,
                node.column,
                f'undefined variable {node.name}; '
                'declare it with DIM or a UI binding',
            )
        if isinstance(node.value, ast.Call) and node.value.name == 'ASK':
            check_ask(node, var)
            return
        if var.type in ('TEXT', 'BITMAP'):
            # M14 (D4): LANGUAGE-SPEC §5.7 and §5.12: a TEXT buffer or a BITMAP cannot be
            # assigned. `T = U` compiled and did nothing (nothing is copied).
            what, how = (('a TEXT buffer', 'TEXT COPY and TEXT PASTE copy text between buffers')
                         if var.type == 'TEXT' else
                         ('a BITMAP', 'BITMAP GET and PUT copy pictures'))
            raise SourceError(node.line, node.column,
                              f'{display_name(node.name)} is {what} and cannot be assigned ({how})')
        if var.type == 'BITMAPREF':  # M13: a BITMAP argument (the call's parameter assignment)
            arg = variables.get(node.value.name) if isinstance(node.value, ast.Var) else None
            if arg is None or arg.type not in ('BITMAP', 'BITMAPREF'):
                raise SourceError(node.value.line, node.value.column,
                                  f'{display_name(node.name)} is a BITMAP parameter: pass it a BITMAP\'s name')
            node.value.typ = 'BITMAP'
            return
        got = expression(node.value)
        if got != var.type and not (var.type == 'REAL' and got == 'INTEGER'):  # M7: widening
            # M14 (D12): INT and FIX return a REAL too; CINT is the conversion
            hint = (' (convert with CINT, which rounds; CINT(INT(x)) or CINT(FIX(x)) drops the fraction)'
                    if (got, var.type) == ('REAL', 'INTEGER') else '')
            raise SourceError(
                node.line,
                node.column,
                f'cannot assign {got} to {var.type} variable {display_name(node.name)}{hint}',
            )
        if var.type == 'STRING' and isinstance(node.value, ast.StrLiteral):
            size = len(node.value.value.encode('utf-8'))
            if size + 1 > var.capacity:
                raise SourceError(
                    node.line,
                    node.column,
                    f'cannot assign a {size}-character literal to {display_name(node.name)} '
                    f'with capacity {var.capacity}',
                )
        elif var.type == 'STRING':
            # Overflow certain at compile time is an error (spec section 4);
            # a value that only *may* overflow is checked at run time.
            shortest, _ = string_length_bounds(node.value, variables)
            if shortest > var.capacity - 1:
                raise SourceError(
                    node.line,
                    node.column,
                    f'cannot assign a value of at least {shortest} characters '
                    f'to {display_name(node.name)} with capacity {var.capacity} (room for '
                    f'{var.capacity - 1} characters)',
                )

    for node in nodes:
        if isinstance(
            node,
            (
                ast.Dim,
                ast.Window,
                ast.Label,
                ast.Textbox,
                ast.Checkbox,
                ast.Button,
                ast.Radio,
                ast.Numberbox,
                ast.ListCtl,
                ast.Slider,
                ast.Canvas,
                ast.Menu,
                ast.Item,
                ast.EndMenu,
                ast.Timer,
                ast.OnStop,
                ast.Sub,
                ast.EndSub,
                ast.Else,
                ast.EndIf,
                ast.Wend,
                ast.Next,
                ast.EndProgram,
            ),
        ):
            continue
        if isinstance(node, ast.Print):
            raise SourceError(
                node.line,
                node.column,
                'PRINT to the screen does not exist in PcW16 BASIC: show text with MESSAGE, a LABEL '
                'or DRAW TEXT (PRINT #n, value writes a line to an open file)',
            )
        if isinstance(node, ast.Message):
            check_message(node)
        elif isinstance(node, ast.Filesave):
            check_filename(node.filename)
            got = expression(node.value)
            if got != 'STRING':
                raise SourceError(
                    node.line, node.column, f'FILESAVE expects STRING, got {got}'
                )
            _, longest = string_length_bounds(node.value, variables)
            if longest > FILE_TEXT_MAX:
                raise SourceError(
                    node.line,
                    node.column,
                    f'FILESAVE value may be up to {longest} bytes; a file '
                    f'written by FILESAVE holds at most {FILE_TEXT_MAX}',
                )
        elif isinstance(node, ast.Fileload):
            check_filename(node.filename)
            expression(node.value)
            target = variables.get(node.value.name) if isinstance(node.value, ast.Var) else None
            if target is None or target.type != 'STRING':
                raise SourceError(
                    node.line,
                    node.column,
                    'FILELOAD destination must be a string variable',
                )
        elif isinstance(node, ast.While):
            if expression(node.condition) != 'BOOLEAN':
                raise SourceError(node.line, node.column, 'WHILE requires BOOLEAN condition')
        elif isinstance(node, ast.For):
            check_for(node)
        elif isinstance(node, ast.If):
            got = expression(node.condition)
            if got != 'BOOLEAN':
                raise SourceError(
                    node.line,
                    node.column,
                    f'IF requires BOOLEAN condition, got {got}',
                )
        elif isinstance(node, ast.Assign):
            if node.name in arrays:
                raise SourceError(node.line, node.column, f'{node.name} is an array: use {node.name}(index) = value')
            check_assign(node)
        elif isinstance(node, ast.AssignIndex):  # M6 Phase 2
            if node.name not in arrays:
                raise SourceError(node.line, node.column, f'{node.name} is not an array (declare it with DIM {node.name}(n) AS ...)')
            if expression(node.index) != 'INTEGER':
                raise SourceError(node.index.line, node.index.column, 'an array index must be INTEGER')
            literal_index(node.name, node.index, variables[node.name])
            if isinstance(node.value, ast.Call) and node.value.name == 'ASK':
                raise SourceError(node.line, node.column,
                                  'ASK may only be assigned to a plain INTEGER variable')
            check_assign(node)
        elif isinstance(node, ast.RecordCopy):  # M10 (pbas/records.py checked the names)
            for index in (node.index, node.src_index):
                if index is not None and expression(index) != 'INTEGER':
                    raise SourceError(index.line, index.column, 'an array index must be INTEGER')
        elif isinstance(node, (ast.OpenFile, ast.Kill, ast.NameFile)):  # M7; M9 (OPEN M13): or a STRING expression
            for name in ('filename', 'new_name'):
                value = getattr(node, name, None)
                if value is None:
                    continue
                if isinstance(value, ast.StrLiteral):
                    check_filename(value)
                elif expression(value) != 'STRING':
                    raise SourceError(value.line, value.column, 'a file name is a STRING')
        elif isinstance(node, ast.CloseFile):
            pass
        elif isinstance(node, ast.PrintFile):
            got = expression(node.value)
            if got not in ('STRING',) + NUMERIC:
                raise SourceError(node.line, node.column, f'PRINT # writes a STRING or a number, got {got}')
            if got == 'STRING':
                _, longest = string_length_bounds(node.value, variables)
                if longest > FILE_TEXT_MAX:
                    raise SourceError(node.line, node.column,
                                      f'PRINT # value may be up to {longest} characters; a line holds at '
                                      f'most {FILE_TEXT_MAX}')
        elif isinstance(node, ast.LineInput):
            target = variables.get(node.name)
            if target is None or target.type != 'STRING':
                raise SourceError(node.line, node.column,
                                  f'LINE INPUT needs a STRING variable, got {display_name(node.name)}')
            if (target.length is None) != (node.index is None):
                raise SourceError(node.line, node.column,
                                  f'{node.name} is an array: use {node.name}(index)' if target.length
                                  else f'{node.name} is not an array')
            if node.index is not None and expression(node.index) != 'INTEGER':
                raise SourceError(node.index.line, node.index.column, 'an array index must be INTEGER')
        elif isinstance(node, ast.Randomize):  # M7
            if node.value is not None and expression(node.value) != 'INTEGER':
                raise SourceError(node.line, node.column, 'RANDOMIZE expects an INTEGER seed')
        elif isinstance(node, (ast.Exit, ast.CallSub, ast.Beep, ast.ExitLoop)):
            continue  # targets, recursion and depth: pbas.parser.validate
        elif isinstance(node, ast.Show):  # M6
            if not any(w.name == node.name for w in windows if w.name is not None):
                # M14 (D10): a SUB named Show is called with CALL; without it the line is SHOW
                hint = ('; to call the SUB SHOW, write CALL Show' if 'SHOW' in subs else '')
                raise SourceError(
                    node.line, node.column,
                    f'SHOW {node.name}: no WINDOW {node.name} is declared '
                    f'(SHOW needs named windows){hint}',
                )
        elif isinstance(node, ast.Focus) and node.name in {c.canvas_name for c in canvases}:
            if node.name in variables:  # M15: FOCUS Name gives a canvas the keyboard
                raise SourceError(node.line, node.column,
                                  f'FOCUS {node.name}: {node.name} names both a CANVAS and a variable')
            continue
        elif isinstance(node, ast.Focus):  # M6
            homes = [
                w for w in windows
                if any(x.var_name == node.name and x.kind in ('TEXTBOX', 'NUMBERBOX', 'CHECKBOX')
                       for x in w.widgets)
            ]
            if len(homes) != 1:
                raise SourceError(
                    node.line, node.column,
                    f'FOCUS {node.name}: the variable must be bound to a TEXTBOX, '
                    'NUMBERBOX or CHECKBOX in exactly one window',
                )
        elif isinstance(node, ast.DbOp):  # M10 Stages B / C
            check_db(node)
        elif isinstance(node, ast.BitmapOp):  # M12
            bitmap_var(ast.Var(node.line, node.column, node.name), f'BITMAP {node.op}')
            if node.mask is not None:  # M13
                bitmap_var(ast.Var(node.line, node.column, node.mask), 'BITMAP MASK\'s mask')
            if node.op in ('GET', 'PUT', 'MASK') and not has_canvas:
                raise SourceError(node.line, node.column, f'BITMAP {node.op} needs a CANVAS declaration')
            for value in node.values:
                want = 'STRING' if node.op in ('SAVE', 'LOAD') else 'INTEGER'
                if want == 'STRING' and isinstance(value, ast.StrLiteral):
                    check_filename(value)
                    if '.' in value.value and value.value.upper().rsplit('.', 1)[-1] in ('NEW', 'BAK'):
                        raise SourceError(value.line, value.column,
                                          f'BITMAP {node.op}: .NEW and .BAK are the save\'s own temporary '
                                          'and backup files; give the file another extension')
                got = expression(value)
                if got != want:
                    raise SourceError(value.line, value.column,
                                      f'BITMAP {node.op} expects {want} here, got {got}')
        elif isinstance(node, ast.PageOp):  # M12 printing
            for i, value in enumerate(node.values):
                want = 'STRING' if node.op == 'TEXT' and i == 2 else 'INTEGER'
                got = expression(value)
                if got != want:
                    raise SourceError(value.line, value.column,
                                      f'PAGE {node.op} argument {i + 1} must be {want}, got {got}')
            if node.op == 'FONT' and isinstance(node.values[0], ast.IntLiteral) \
                    and node.values[0].value not in PAGE_SIZES:
                raise SourceError(node.values[0].line, node.values[0].column,
                                  'a print size is ' + ', '.join(map(str, PAGE_SIZES[:-1])) + f' or {PAGE_SIZES[-1]}')
        elif isinstance(node, ast.TextOp):  # M9 Stage C
            text_buffer(ast.Var(node.line, node.column, node.name), f'TEXT {node.op}')
            kinds = {'LOAD': ('STRING',), 'SAVE': ('STRING',), 'CLEAR': (),
                     'INSERT': ('INTEGER', 'INTEGER', 'STRING'), 'DELETE': ('INTEGER',) * 3,
                     'SPLIT': ('INTEGER',) * 2, 'JOIN': ('INTEGER',),
                     'REMOVE': ('INTEGER',) * 4, 'COPY': ('TEXT',) + ('INTEGER',) * 4,
                     'PASTE': ('INTEGER', 'INTEGER', 'TEXT')}[node.op]  # M10
            for value, want in zip(node.values, kinds):
                if want == 'TEXT':  # M10: the other buffer, never the same one
                    text_buffer(value, f'TEXT {node.op}')
                    if value.name == node.name:
                        raise SourceError(value.line, value.column,
                                          f'TEXT {node.op} needs two different buffers')
                    continue
                if node.op in ('LOAD', 'SAVE') and isinstance(value, ast.StrLiteral):
                    check_filename(value)
                got = expression(value)
                if got != want:
                    raise SourceError(value.line, value.column,
                                      f'TEXT {node.op} expects {want} here, got {got}')
        elif isinstance(node, ast.Draw):  # M9
            if not has_canvas:
                raise SourceError(node.line, node.column, 'DRAW needs a CANVAS declaration')
            if node.op == 'ON' and node.target not in {c.canvas_name for c in canvases}:  # M15
                named = ', '.join(c.canvas_name for c in canvases if c.canvas_name) or 'none is named'
                raise SourceError(node.line, node.column,
                                  f'DRAW ON {node.target}: no CANVAS {node.target} is declared ({named})')
            for i, value in enumerate(node.values):
                want = 'STRING' if node.op in ('TEXT', 'TYPE') and i == 2 else 'INTEGER'
                got = expression(value)
                if got != want:
                    raise SourceError(value.line, value.column,
                                      f'DRAW {node.op} argument {i + 1} must be {want}, got {got}')
        elif isinstance(node, ast.TypeFont):  # M15 screen typography
            if not has_canvas:
                raise SourceError(node.line, node.column, 'TYPE FONT is for DRAW TYPE: it needs a CANVAS declaration')
            got = expression(node.value)
            if got != 'INTEGER':
                raise SourceError(node.value.line, node.value.column, f'TYPE FONT size must be INTEGER, got {got}')
            if isinstance(node.value, ast.IntLiteral) and node.value.value not in PAGE_SIZES:
                raise SourceError(node.value.line, node.value.column,
                                  'a type size is ' + ', '.join(map(str, PAGE_SIZES[:-1])) + f' or {PAGE_SIZES[-1]}')
        elif isinstance(node, ast.TimerSwitch):  # M6
            if timer is None:
                raise SourceError(
                    node.line, node.column, 'TIMER ON/OFF needs a TIMER declaration'
                )
        else:
            raise AssertionError(f'unexpected statement node: {type(node).__name__}')

    for node in nodes:  # M8: each statement reads at most four BANKED elements
        reads = _banked_reads(node, variables)
        if reads > BANKED_READS_MAX:
            raise SourceError(node.line, node.column,
                              f'this statement reads {reads} BANKED array elements; at most '
                              f'{BANKED_READS_MAX} are allowed (copy some into variables first)')

    return Analysis(
        variables=variables,
        string_capacity=string_capacity,
        dialog_title=dialog_title,
        widgets=widgets,
        bindings=bindings,
        handlers=handlers,
        dialog_position=dialog_position,
        windows=windows,
        menus=menus,
        timer=timer,
        on_stop=on_stop[0] if on_stop else None,
        on_stop_line=on_stop[1] if on_stop else 0,
    )


def banked_layout(var) -> tuple[int, int, int]:
    """M8: (element size, elements per 16K block, blocks) of a BANKED array.
    An element never crosses a block end."""
    size = var.capacity if var.type in ('STRING', 'RECORD') else 5 if var.type == 'REAL' else 2
    per_block = BLOCK_SIZE // size
    return size, per_block, -(-var.length // per_block)


def _banked_reads(node, variables) -> int:
    """BANKED elements read by *node* (its expressions, not its target)."""
    count = 0

    def walk(value):
        nonlocal count
        if isinstance(value, ast.Index):
            var = variables.get(value.name)
            if var is not None and var.banked:
                count += 1
            walk(value.index)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, ast.Expr):
            for field in vars(value).values():
                walk(field)

    for name, field in vars(node).items():
        if name not in ('line', 'column'):
            walk(field)
    if isinstance(node, ast.RecordCopy) and node.src is not None and variables[node.src].banked:
        count += 1  # M10: the source record's read window
    return count
