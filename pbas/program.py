"""Lowered program model for PcW16 BASIC (Stage 1).

`pbas.parser` produces a flat, validated statement list; ``build_program``
lowers it into the structured model below: nested control-flow blocks, the
main line vs procedure bodies, and the dialog description taken from the
``Analysis`` produced by ``pbas.semantics`` (ARCHITECTURE.md section 3).
Plain data only — the model has no behaviour beyond the lowering itself.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import ast_nodes as ast


@dataclass
class Widget:
    """One dialog widget declaration, in source order."""

    kind: str  # 'LABEL' | 'TEXTBOX' | 'CHECKBOX' | 'BUTTON' | (M6) 'RADIO' | 'NUMBERBOX'
    caption: str | None  # None for a dynamic LABEL (M5d)
    var_name: str | None  # TEXTBOX/CHECKBOX binding target; dynamic LABEL variable
    handler: str | None  # BUTTON handler SUB name
    line: int
    column: int
    default: bool = False  # M5d: the BUTTON marked DEFAULT (Return key)
    keys: tuple = ()  # M6: BUTTON KEY names
    options: tuple = ()  # M6: RADIO captions
    low: int = -32768  # M6: NUMBERBOX MIN
    high: int = 32767  # M6: NUMBERBOX MAX
    spin: bool = False  # M6: NUMBERBOX SPIN
    items: str | None = None  # M6 Phase 2: LIST / CHOICE array
    count: object = None  # M6 Phase 2: LIST / CHOICE count (Var or IntLiteral)
    rows: int = 0  # M6 Phase 2: LIST visible rows
    length: int = 0  # M6 Phase 2: the array's length
    change: str | None = None  # M6 Phase 2: CHANGE handler
    action: str | None = None  # M6 Phase 2: LIST ACTION (double-click) handler
    width: int = 0  # M9: CANVAS drawing area width (pixels)
    height: int = 0  # M9: CANVAS drawing area height (pixels)
    paint: str | None = None  # M9: CANVAS PAINT handler
    mouse: str | None = None  # M9: CANVAS MOUSE handler
    keys_handler: str | None = None  # M9: CANVAS KEYS handler
    canvas_name: str | None = None  # M15: CANVAS Name


@dataclass
class WindowDecl:
    """One WINDOW and the controls declared under it (M6: several)."""

    name: str | None  # None for the single unnamed window
    title: str
    large: bool
    widgets: list[Widget]
    line: int
    column: int


@dataclass
class MenuItem:
    text: str  # "-" for a divider
    handler: str | None
    key: str | None  # Ctrl+key: one upper-case letter or digit
    tick: str | None  # BOOLEAN variable shown as the tick
    line: int
    column: int


@dataclass
class MenuDecl:
    title: str
    items: list[MenuItem]
    line: int
    column: int


@dataclass
class TimerDecl:
    handler: str
    seconds: int
    line: int
    column: int
    ticks: bool = False  # M13: seconds counts sixteenths of a second


@dataclass
class Binding:
    """A TEXTBOX/CHECKBOX-to-variable binding (codegen table row, D3)."""

    var_name: str
    widget: str  # 'TEXTBOX' | 'CHECKBOX' | (M5d) 'LABEL'
    capacity: int | None  # bytes incl. NUL for TEXTBOX/LABEL; None for CHECKBOX
    line: int


@dataclass
class Handler:
    """A BUTTON-to-SUB handler registration (codegen table row, D3)."""

    button_index: int  # index of the BUTTON in Program.widgets (source order)
    sub: str
    line: int


@dataclass
class IfBlock:
    condition: ast.Expr
    then_body: list[BodyItem]
    else_body: list[BodyItem]  # empty when the IF has no ELSE
    line: int
    column: int


@dataclass
class WhileBlock:
    condition: ast.Expr
    body: list[BodyItem]
    line: int
    column: int


@dataclass
class ForBlock:
    name: str
    start: ast.Expr
    finish: ast.Expr
    step: ast.Expr  # IntLiteral valued +1 or -1 (semantics-enforced)
    body: list[BodyItem]
    line: int
    column: int


@dataclass
class Procedure:
    name: str
    body: list[BodyItem]
    line: int
    column: int


SimpleStatement = (
    ast.Assign | ast.CallSub | ast.Exit | ast.Filesave | ast.Fileload | ast.Message
    | ast.Beep | ast.Focus | ast.Show | ast.TimerSwitch | ast.AssignIndex | ast.ExitLoop
    | ast.Randomize | ast.OpenFile | ast.CloseFile | ast.PrintFile | ast.LineInput | ast.Kill
    | ast.NameFile | ast.Draw | ast.TextOp | ast.RecordCopy | ast.DbOp | ast.BitmapOp | ast.PageOp
    | ast.TypeFont
)
_SIMPLE = (ast.Assign, ast.CallSub, ast.Exit, ast.Filesave, ast.Fileload, ast.Message,
           ast.Beep, ast.Focus, ast.Show, ast.TimerSwitch, ast.AssignIndex, ast.ExitLoop,
           ast.Randomize, ast.OpenFile, ast.CloseFile, ast.PrintFile, ast.LineInput, ast.Kill,
           ast.NameFile, ast.Draw, ast.TextOp, ast.RecordCopy, ast.DbOp, ast.BitmapOp, ast.PageOp,
           ast.TypeFont)
BodyItem = SimpleStatement | IfBlock | WhileBlock | ForBlock

_DECLARATIONS = (ast.Dim, ast.Window, ast.Label, ast.Textbox, ast.Checkbox, ast.Button,
                 ast.Radio, ast.Numberbox, ast.Menu, ast.Item, ast.EndMenu, ast.Timer,
                 ast.ListCtl, ast.Slider, ast.Canvas, ast.OnStop)
_MARKERS = (
    ast.Sub,
    ast.EndSub,
    ast.If,
    ast.Else,
    ast.EndIf,
    ast.While,
    ast.Wend,
    ast.For,
    ast.Next,
)


@dataclass
class Program:
    """A fully analysed Stage-1 program: main line, procedures, dialog."""

    main: list[BodyItem]
    procedures: list[Procedure]
    dialog_title: str | None
    widgets: list[Widget]
    variables: dict  # name -> semantics.Variable (insertion-ordered)
    bindings: list[Binding]
    handlers: list[Handler]
    string_capacity: int
    dialog_position: tuple[int, int] | None = None  # WINDOW (line, column)
    windows: list = None  # list[WindowDecl] (M6); one entry for a legacy program
    menus: list = None  # list[MenuDecl] (M6)
    timer: TimerDecl | None = None  # M6
    on_stop: str | None = None  # M15: ON STOP's FUNCTION
    on_stop_line: int = 0


def build_program(nodes, analysis) -> Program:
    """Lower a validated flat statement list into the structured Program model.

    Declarations never reach bodies — their data comes from *analysis*
    (dialog title, widgets, bindings, handlers, variables). Simple statements
    keep their parser node classes; control-flow markers become nested
    IfBlock/WhileBlock/ForBlock instances. Nesting invariants are guaranteed
    by ``pbas.parser.validate``, so a violated invariant here is an
    AssertionError, never a silently wrong tree.
    """
    main: list[BodyItem] = []
    procedures: list[Procedure] = []
    blocks: list[tuple[IfBlock | WhileBlock | ForBlock, list]] = []
    ifs: list[IfBlock] = []  # open IfBlocks, for ELSE body switching
    current: list = main
    proc: Procedure | None = None

    for node in nodes:
        if isinstance(node, _DECLARATIONS):
            continue
        if isinstance(node, ast.Sub):
            assert proc is None, 'SUB inside SUB reached build_program'
            proc = Procedure(node.name, [], node.line, node.column)
            procedures.append(proc)
            current = proc.body
        elif isinstance(node, ast.EndSub):
            assert proc is not None, 'END SUB outside SUB reached build_program'
            proc = None
            current = main
        elif isinstance(node, ast.If):
            block = IfBlock(node.condition, [], [], node.line, node.column)
            current.append(block)
            blocks.append((block, current))
            ifs.append(block)
            current = block.then_body
        elif isinstance(node, ast.Else):
            assert (
                ifs
                and blocks
                and blocks[-1][0] is ifs[-1]
                and current is ifs[-1].then_body
            ), 'ELSE without open IF reached build_program'
            current = ifs[-1].else_body
        elif isinstance(node, ast.EndIf):
            assert ifs and blocks and blocks[-1][0] is ifs[-1], (
                'END IF without open IF reached build_program'
            )
            ifs.pop()
            _, current = blocks.pop()
        elif isinstance(node, ast.While):
            block = WhileBlock(node.condition, [], node.line, node.column)
            current.append(block)
            blocks.append((block, current))
            current = block.body
        elif isinstance(node, ast.Wend):
            assert blocks and isinstance(blocks[-1][0], WhileBlock), (
                'WEND without open WHILE reached build_program'
            )
            _, current = blocks.pop()
        elif isinstance(node, ast.For):
            block = ForBlock(
                node.name, node.start, node.finish, node.step, [], node.line, node.column
            )
            current.append(block)
            blocks.append((block, current))
            current = block.body
        elif isinstance(node, ast.Next):
            assert blocks and isinstance(blocks[-1][0], ForBlock), (
                'NEXT without open FOR reached build_program'
            )
            _, current = blocks.pop()
        elif isinstance(node, ast.EndProgram):
            assert proc is None and not blocks, (
                'END inside an unclosed block reached build_program'
            )
            break  # validate() guarantees END is the final statement
        elif isinstance(node, _MARKERS):
            raise AssertionError(f'unexpected marker node: {type(node).__name__}')
        elif isinstance(node, _SIMPLE):
            current.append(node)
        else:
            raise AssertionError(f'unexpected node in validated program: {type(node).__name__}')

    return Program(
        main=main,
        procedures=procedures,
        dialog_title=analysis.dialog_title,
        widgets=analysis.widgets,
        variables=analysis.variables,
        bindings=analysis.bindings,
        handlers=analysis.handlers,
        string_capacity=analysis.string_capacity,
        dialog_position=getattr(analysis, 'dialog_position', None),
        windows=getattr(analysis, 'windows', None) or [],
        menus=getattr(analysis, 'menus', None) or [],
        timer=getattr(analysis, 'timer', None),
        on_stop=getattr(analysis, 'on_stop', None),
        on_stop_line=getattr(analysis, 'on_stop_line', 0),
    )
