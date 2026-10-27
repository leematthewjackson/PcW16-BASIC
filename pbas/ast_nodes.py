"""Typed AST for PcW16 BASIC (Stage 1).

The parser emits a *flat* statement list: block constructs (IF/ELSE/END IF,
WHILE/WEND, FOR/NEXT, SUB/END SUB) appear as marker statements and
`pbas.parser.validate` checks their nesting. `pbas.program.build_program`
lowers the validated flat list into the structured `Program` model
(IfBlock/WhileBlock/ForBlock with nested bodies). Every node carries the
1-based source position of the token that started it.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------- expressions
@dataclass
class Expr:
    line: int
    column: int


@dataclass
class IntLiteral(Expr):
    value: int  # always within -32768..32767 (parser-enforced, spec section 2)


@dataclass
class StrLiteral(Expr):
    value: str


@dataclass
class BoolLiteral(Expr):
    value: bool


@dataclass
class RealLiteral(Expr):
    value: float  # M7: a REAL literal (decimal point or exponent)


@dataclass
class Var(Expr):
    name: str  # upper-cased (language is case-insensitive)


@dataclass
class Call(Expr):
    name: str  # upper-cased built-in name (LEN, STR$, LEFT$, RIGHT$, MID$)
    args: list = field(default_factory=list)  # list[Expr]


@dataclass
class Index(Expr):
    """M6 Phase 2: an array element, ``Name(index)`` (from a Call whose name
    is a declared array; pbas.semantics rewrites it)."""
    name: str
    index: Expr


@dataclass
class Unary(Expr):
    op: str  # '+', '-' or (M5c) 'NOT'
    operand: Expr


@dataclass
class Binary(Expr):
    op: str  # one of + - * / MOD = == <> < <= > >= AND OR
    left: Expr
    right: Expr


# ---------------------------------------------------------------- statements
@dataclass
class Stmt:
    line: int
    column: int


@dataclass
class Window(Stmt):
    title: Expr  # StrLiteral enforced by semantics
    name: str | None = None  # M6: WINDOW Name, "title" (named windows)
    large: bool = False  # M6: WINDOW ..., LARGE


@dataclass
class Label(Stmt):
    text: Expr  # StrLiteral, or (M5d) a Var: a label showing a STRING variable


@dataclass
class Message(Stmt):
    value: Expr  # alert-dialog text (budget-checked by semantics, spec section 6)


@dataclass
class Textbox(Stmt):
    name: str  # upper-cased binding target
    caption: Expr | None = None


@dataclass
class Checkbox(Stmt):
    name: str
    caption: Expr | None = None


@dataclass
class Button(Stmt):
    caption: Expr
    handler: str  # upper-cased SUB name
    default: bool = False  # M5d: BUTTON "cap", H, DEFAULT (the Return key)
    keys: list = field(default_factory=list)  # M6: KEY names, upper-cased


@dataclass
class Filesave(Stmt):
    filename: Expr  # StrLiteral enforced by semantics
    value: Expr


@dataclass
class Fileload(Stmt):
    filename: Expr
    value: Expr


@dataclass
class Dim(Stmt):
    name: str
    type_name: str  # 'INTEGER' | 'STRING' | 'BOOLEAN'
    length: int | None = None  # M6 Phase 2: DIM Name(n) AS type (an array of n)
    capacity: int | None = None  # M8: AS STRING * n holds n characters (capacity n + 1)
    banked: bool = False  # M8: DIM Name(n) AS type BANKED (elements in owned 16K blocks)
    bitmap_size: tuple | None = None  # M12: DIM Name AS BITMAP * width, height


@dataclass
class AssignIndex(Stmt):
    """M6 Phase 2: ``Name(index) = value``."""
    name: str
    index: Expr
    value: Expr


@dataclass
class For(Stmt):
    name: str  # counter variable
    start: Expr
    finish: Expr
    step: Expr  # IntLiteral, value +1 or -1 (semantics-enforced)


@dataclass
class While(Stmt):
    condition: Expr


@dataclass
class Wend(Stmt):
    pass


@dataclass
class Next(Stmt):
    name: str | None = None  # optional counter name, checked when given


@dataclass
class If(Stmt):
    condition: Expr


@dataclass
class Else(Stmt):
    pass


@dataclass
class EndIf(Stmt):
    pass


@dataclass
class EndSub(Stmt):
    pass


@dataclass
class EndProgram(Stmt):
    pass


@dataclass
class Exit(Stmt):
    sub: bool = False  # M5c: EXIT SUB (return from the current SUB)


@dataclass
class CallSub(Stmt):
    name: str  # M5c: CALL Name — upper-cased SUB name
    args: list = field(default_factory=list)  # M7: CALL Name(a, b) (lowered away)


@dataclass
class Sub(Stmt):
    name: str
    params: list = field(default_factory=list)  # M7: list[Param] (lowered away)


@dataclass
class Assign(Stmt):
    name: str
    value: Expr


@dataclass
class Print(Stmt):
    value: Expr  # parsed for a clear Stage-1 error; never survives semantics


# --- M6 Phase 1 ---------------------------------------------------------------
@dataclass
class Radio(Stmt):
    name: str  # upper-cased INTEGER binding target
    captions: list  # list[Expr], StrLiteral enforced by semantics


@dataclass
class Numberbox(Stmt):
    name: str
    caption: Expr | None = None
    low: int | None = None  # MIN literal
    high: int | None = None  # MAX literal
    spin: bool = False


@dataclass
class Beep(Stmt):
    pass


@dataclass
class Focus(Stmt):
    name: str


@dataclass
class Show(Stmt):
    name: str  # window name, upper-cased


@dataclass
class Menu(Stmt):
    title: Expr


@dataclass
class Item(Stmt):
    text: Expr
    handler: str | None = None  # None for the divider ITEM "-"
    key: str | None = None  # KEY "X": one letter or digit, upper-cased
    tick: str | None = None  # TICK Flag: BOOLEAN variable name


@dataclass
class EndMenu(Stmt):
    pass


@dataclass
class Timer(Stmt):
    handler: str  # TIMER Handler, EVERY n [TICKS]
    seconds: int  # n: seconds, or sixteenths of a second with TICKS (M13)
    ticks: bool = False


@dataclass
class TimerSwitch(Stmt):
    on: bool  # TIMER ON / TIMER OFF


# --- M6 Phase 2 ---------------------------------------------------------------
@dataclass
class ListCtl(Stmt):
    """LIST Sel, Items$, Count [, ROWS n] [, CHANGE H] [, ACTION H] and
    CHOICE Sel, Items$, Count [, "caption"] [, CHANGE H] (kind 'LIST' / 'CHOICE')."""
    kind: str
    name: str  # INTEGER selection variable
    items: str  # array name
    count: Expr  # Var or IntLiteral
    caption: Expr | None = None
    rows: int | None = None
    change: str | None = None
    action: str | None = None


@dataclass
class Slider(Stmt):
    name: str
    low: int
    high: int
    caption: Expr | None = None
    change: str | None = None



# --- M9 Stage B: drawing surface -----------------------------------------------
@dataclass
class Canvas(Stmt):
    """CANVAS width, height [, PAINT H] [, MOUSE H] [, KEYS H]."""
    width: int
    height: int
    paint: str | None = None
    mouse: str | None = None
    keys: str | None = None


@dataclass
class TextOp(Stmt):
    """M9 Stage C: TEXT op Buffer [, arguments]; op is LOAD, SAVE, CLEAR,
    INSERT, DELETE, SPLIT or JOIN."""
    op: str
    name: str  # the TEXT buffer
    values: list = field(default_factory=list)  # list[Expr]


@dataclass
class PageOp(Stmt):
    """M12: PAGE op [arguments] (printing); op is NEW, FONT, TEXT, LINE, BOX,
    FILL, PRINT or CLOSE. *bold*: PAGE FONT size, BOLD."""
    op: str
    values: list = field(default_factory=list)  # list[Expr]
    bold: bool = False


@dataclass
class BitmapOp(Stmt):
    """M12: BITMAP op Bitmap [, arguments]; op is GET, PUT, SAVE or LOAD.
    M13: PUT of a part (x, y, sx, sy, w, h) and MASK, whose ``mask`` names
    the second BITMAP (values are then x, y [, sx, sy, w, h])."""
    op: str
    name: str  # the BITMAP
    values: list = field(default_factory=list)  # list[Expr]
    mask: str | None = None  # M13: BITMAP MASK's mask


@dataclass
class Draw(Stmt):
    """DRAW op [arguments]: op is CLEAR, FILL, INVERT, BOX, LINE, PIXEL,
    TEXT, SCROLL or INK (then ``ink`` is BLACK, WHITE or XOR)."""
    op: str
    values: list = field(default_factory=list)  # list[Expr]
    ink: str | None = None


# --- M7: procedures, constants, SELECT CASE, loop exits ------------------------
# Parser output only, except ExitLoop: pbas/lower.py rewrites the rest into the
# statements above before validation and analysis.
@dataclass
class Param:
    name: str
    type_name: str  # 'INTEGER' | 'STRING' | 'BOOLEAN' | 'REAL'
    line: int = 0
    column: int = 0


@dataclass
class FunctionDef(Stmt):
    name: str
    params: list  # list[Param]
    type_name: str  # result type


@dataclass
class EndFunction(Stmt):
    pass


@dataclass
class Return(Stmt):
    value: Expr  # RETURN expr (FUNCTION only)


@dataclass
class Local(Stmt):
    name: str
    type_name: str


@dataclass
class Const(Stmt):
    name: str
    value: Expr  # a literal (optionally signed)


@dataclass
class SelectCase(Stmt):
    value: Expr


@dataclass
class CaseItem:
    kind: str  # 'EQ' | 'RANGE' | 'IS'
    value: Expr
    high: Expr | None = None  # RANGE upper bound
    op: str | None = None  # IS operator


@dataclass
class Case(Stmt):
    items: list  # list[CaseItem]; empty for CASE ELSE
    is_else: bool = False


@dataclass
class EndSelect(Stmt):
    pass


@dataclass
class ExitLoop(Stmt):
    kind: str  # 'FOR' | 'WHILE' (EXIT FOR / EXIT WHILE: kept until codegen)


@dataclass
class Randomize(Stmt):
    value: Expr | None  # RANDOMIZE [seed] (M7); None: seed from the Z80 R register


# --- M7: sequential files (LANGUAGE-SPEC §7.1) ----------------------------------
@dataclass
class OpenFile(Stmt):
    filename: Expr  # StrLiteral (8.3)
    mode: str  # 'INPUT' | 'OUTPUT'
    channel: int  # 1 or 2


@dataclass
class CloseFile(Stmt):
    channel: int | None  # None: CLOSE (every open channel)


@dataclass
class PrintFile(Stmt):
    channel: int
    value: Expr  # STRING or INTEGER (REAL) expression; one line


@dataclass
class LineInput(Stmt):
    channel: int
    name: str  # STRING variable or array
    index: Expr | None = None  # LINE INPUT #n, A$(i)


@dataclass
class Kill(Stmt):
    filename: Expr


@dataclass
class NameFile(Stmt):
    filename: Expr  # existing name
    new_name: Expr


# --------------------------------------------------------------- M10 records
@dataclass
class TypeField:
    """One field of a TYPE: ``Name AS STRING * 40``."""
    name: str
    type_name: str  # INTEGER / REAL / BOOLEAN / STRING
    capacity: int | None  # STRING: bytes including the NUL
    line: int
    column: int


@dataclass
class TypeDef(Stmt):
    """M10: ``TYPE Name`` ... ``END TYPE`` (top level)."""
    name: str
    fields: list  # list[TypeField]


@dataclass
class RecordCopy(Stmt):
    """M10 (pbas/records.py): ``A = B`` / ``A(i) = B(j)`` between records of
    one TYPE; *index* / *src_index* are None for a record variable, and a
    None *src* clears the target (a LOCAL record's fresh value)."""
    name: str
    index: Expr | None
    src: str | None
    src_index: Expr | None
    size: int = 0


@dataclass
class DbOp(Stmt):
    """M10 Stages B/C: ``DB op Array, ...`` on a BANKED array of records
    (LANGUAGE-SPEC §5.9): LOAD, SAVE, NEW, DELETE, SORT, SEARCH. *values*
    are the expressions in order; *key* names a field (SORT, SEARCH);
    *flags* holds DESC / NOCASE."""
    op: str
    name: str
    values: list = field(default_factory=list)
    key: str | None = None
    flags: list = field(default_factory=list)
