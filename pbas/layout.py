"""Dialog layout, object definitions and binding rows (ARCHITECTURE.md D3/D4).

The one place that turns a program's dialog description (WINDOW, LABEL,
CHECKBOX, TEXTBOX, BUTTON) into the byte definition passed to
``os_dialog_define``, the handler table the runtime dispatches clicks from,
and (M3b) the binding table the runtime synchronises variables from. Every
field is written from ROSAN283.DOC 'os_dialog_define' / 'os_text_edit';
numeric codes are from CONSTOS.Z80 (``RSSET #01`` enumerations):

Global definition (4 bytes)   focus, exit-by-click, screen-store, ddm_enable
Box & Title                   type (dg_dialog_box = 16), x,y,w,h words,
                              ASCII title, #00
Object N                      type byte, x,y,w,h words (relative to the box
                              origin), then by type:
  ob_box (1)                  +9 linked object, +10..13 dg_multi_box params
  ob_label (2)                +9 linked object, +10 font, +11 alignment,
                              +12 ASCII text #00 ("max 128 chars")
  ob_textbutton (3)           +9..16 four keycode words, +17 repeat flag,
                              +18 ASCII text #00 ("max 33 bytes incl 0")
  ob_checkbox (6)             +9 status #00 / #FF = un- / checked
  ob_textedit (8)             +9..40 the 32-byte os_text_edit parameter
                              block (we set font +16, legal chars +21/+24,
                              max length +28 "max 128"; +0..15, +25, +30/31
                              "set by OS"), +41 ASCII current text #00
Terminator                    #00
Whole definition              "max length 16k"

Object numbers are 1-based in definition order (ARCHITECTURE F10:
XAnne-empirical, POC-proven; ROSAN283 does not state the rule).

Geometry. A 360x240 box at 140,110 with one background ob_box, then the
non-button widgets stacked top-down in **source order** from y=48: a LABEL
row is 32 px (the M3a/POC pitch, so label-only dialogs are exactly the
XAnne-proven M3a layout), a CHECKBOX row 28 px (POC: 19x19 box at x=26, its
caption label at x=52 linked to it), a TEXTBOX row 48 px (caption label at
the row top, then a field box and its text field, below). The rows
must end at or above the button row at y=180; the first widget that does
not fit is a positioned error. Buttons: one centred row of 96x24, 110 apart
(POC), at most 3.

TEXTBOX slot reservation (M3b; the v0.5.2 failure class). Rosanne edits a
textbox in place in its own copy of the definition: os_text_edit's
destination (+25, "set by OS") is the record's text and "+28 Maximum bytes
available at destination" bounds the edit. That copy's slot is as long as the
record given to os_dialog_define, and a later os_object_define "Must not be
longer than existing definition". So the initial definition carries
capacity-1 spaces (+ NUL) — reserving the whole slot, as the XAnne-proven
POC v0.5.1 did with 32 spaces — and max length = capacity-1. The runtime
then immediately redefines each textbox from its variable *before* the
dialog is displayed, so the spaces are never seen, and every later
redefinition is no longer than the slot. Capacity is limited to 64 (63
characters) in M3b: conservative, half the documented 128.

TEXTBOX field box (M3b fix, XAnne-observed redraw fault). Every textbox is
two objects: an ob_box (white fill, 1-line black outline) linked to the
ob_textedit that follows it, the edit inset 4 px inside the box. This is the
Amstrad pattern — NIKMACRO.Z80 ``textentry64`` (box x,y,w,25 params 8,0,1,0;
edit x+4,y+6,w-8,18) and the ``ob_box ;OBLIGATORY!!!!!!`` comments in
NIKMACRO.Z80 / MACROS.Z80. The text edit draws only its glyphs; the box
paints the background. Without it, os_object_update after a handler changed
the text drew the new glyphs over the old ones (EDITOR "Keep 5" left
"Amstrad PcW16" visible). The runtime redraws a changed textbox as: define
the edit, os_object_update the box (number - 1, clears the area), then
os_object_update the edit. validate_layout proves the box is always the
edit's number - 1 and links to it.

Dynamic labels (M5d). ``LABEL Name$`` is a label row whose text the runtime
sets from the variable, through the binding table (kind 3, one direction:
variable -> label). Like a textbox it is two objects: an ob_box with white
fill and no outline (dg_multi_box params 8,0,0,0: "fill colour (0-8 =
black-white)", no outline bits — the background box's own parameters)
covering the text area, then the ob_label, whose initial text reserves the
whole slot with DYNAMIC_LABEL_MAX (24) spaces (os_object_define "Must not be longer
than existing definition"). The runtime redraws a changed label box-first,
exactly as a textbox, so no glyph of a longer old text can remain. The box
is LABEL_BOX: 2 px around the label's x, from 2 px above its y to 18 px
below — inside the 32-px row and clear of every neighbouring row's objects.

Buttons (M5d). Up to 3 buttons: one centred row at y=180, exactly as before.
4 to 6: the first three keep that row; the rest form a second centred row
at y=208 (pitch 28), inside the background box (which ends at y=238). A
DEFAULT button carries the Return key in its first keycode pair (#0D, shift
#80 = ignore: CONSTBIO kc_return = kc_enter = #0D; NIKMACRO ok_can_help) and
receives the initial focus.

Deliberate difference from the POC bytes: exit-by-click is 0. ROSAN283:
"non-0 = exit on click outside dialog"; a stray click must not dismiss the
program's only window.
"""
from __future__ import annotations

from dataclasses import dataclass

from .errors import SourceError
from .policy import DYNAMIC_LABEL_MAX, NUMBERBOX_CHARS
from .program import WindowDecl

# --- ROSAN283 / CONSTOS.Z80 codes ------------------------------------------
DG_DIALOG_BOX = 16
OB_BOX = 1
OB_LABEL = 2
OB_TEXTBUTTON = 3
OB_CHECKBOX = 6
OB_RADIO = 7  # M6 Phase 1
OB_TEXTEDIT = 8
OB_SPINNER = 13  # M6 Phase 1

# --- Global definition (ROSAN283 'os_dialog_define' +0..+3) ----------------
GLOBAL_FOCUS = 1  # focus exists (the first button receives it)
GLOBAL_EXIT_BY_CLICK = 0  # never dismiss on a click outside (see above)
GLOBAL_SCREEN_STORE = 1  # OS stores/restores the screen under the dialog
GLOBAL_DDM_ENABLE = 0  # no drop-down menus during the dialog

# --- Documented size limits -------------------------------------------------
DIALOG_DEFINITION_MAX = 16 * 1024  # "max length 16k"
LABEL_TEXT_DOC_MAX = 128  # ob_label "max 128 chars"
BUTTON_TEXT_DOC_MAX = 32  # ob_textbutton "max 33 bytes incl 0"
TEXTEDIT_LENGTH_DOC_MAX = 128  # ob_textedit +28 "max length (max 128)"
OBJECT_NUMBER_MAX = 255  # object numbers are bytes (E register, IX+3)

# --- Record layout constants --------------------------------------------------
TEXTEDIT_TEXT_OFFSET = 41  # +9 params (32 bytes) then the text
TEXTEDIT_TEMPLATE_LEN = TEXTEDIT_TEXT_OFFSET  # type..params, rebuilt by the runtime
CHECKBOX_RECORD_LEN = 10
CHECKBOX_TEMPLATE_LEN = 9  # type + x,y,w,h; the runtime appends the status
CHECKED, UNCHECKED = 0xFF, 0x00

# --- Geometry (POC-proven sizes; M3b row stacking) --------------------------
DIALOG_RECT = (140, 110, 360, 240)  # x, y, w, h on screen
BOX_RECT = (2, 26, 356, 212)  # background ob_box inside the dialog
BOX_TAIL = bytes((0, 8, 0, 0, 0))  # linked object 0; dg_multi_box params
CONTENT_TOP = 48
LABEL_X, LABEL_PITCH, LABEL_W, LABEL_H = 24, 32, 305, 1
LABEL_FONT, LABEL_ALIGN_LEFT = 7, 0
CHECK_PITCH, CHECK_BOX = 28, (26, 7, 19, 19)  # x, dy, w, h
CHECK_CAPTION = (52, 9, 280, 1)  # x, dy, w, h
TEXT_PITCH = 48
TEXT_CAPTION = (26, 0, 300, 1)  # x, dy, w, h
TEXT_FIELD_BOX = (26, 15, 300, 25)  # x, dy, w, h (NIKMACRO textentry64: h 25)
TEXT_FIELD_INSET = (4, 6, 8, 18)  # edit at box x+4, y+6, w-8, h 18 (textentry64)
FIELD_BOX_PARAMS = bytes((8, 0, 1, 0))  # white fill, 1 black outline (textentry64)
TEXT_FONT = 7
BUTTON_Y, BUTTON_W, BUTTON_H, BUTTON_PITCH = 180, 96, 24, 110
BUTTON_ROWS = (180, 208)  # M5d: second row below the first, inside BOX_RECT
BUTTONS_PER_ROW = 3
RETURN_KEYS = bytes((0x0D, 0x80)) + bytes(6)  # M5d DEFAULT: kc_return, shift ignored
LABEL_BOX = (-2, -2, 4, 20)  # M5d dynamic label box: dx, dy, extra w, h
LABEL_BOX_PARAMS = bytes((8, 0, 0, 0))  # white fill, no outline (dg_multi_box)
# Height the dialog font's glyphs may occupy below a label's y (assumed from
# the XAnne-proven layouts: a TEXTBOX caption at y sits above its field box
# at y+15; a CHECKBOX caption at y+9 beside a 19-px box at y+7). The label
# box covers 18 px below y. XAnne question L1 checks it.
LABEL_GLYPH_H = 16

# --- Caps -------------------------------------------------------------------
M3A_MAX_LABELS = (BUTTON_Y - CONTENT_TOP) // LABEL_PITCH  # 4, as in M3a
M3A_MAX_BUTTONS = 3
MAX_LAYOUT_BUTTONS = len(BUTTON_ROWS) * BUTTONS_PER_ROW  # M5d: 6
LABEL_SHOW_MAX = DYNAMIC_LABEL_MAX  # M5d recovery: 24 printable characters (LANGUAGE-SPEC §5)
M3B_TEXTBOX_CAPACITY_MAX = 64  # conservative: 63 characters (doc allows 128)

BIND_TEXTBOX, BIND_CHECKBOX, BIND_LABEL = 1, 2, 3  # binding-table kind codes (runtime)
LABEL_TEMPLATE_LEN = 12  # type, x,y,w,h, linked, font, alignment

# --- M6 Phase 1 (LANGUAGE-SPEC §5.1) -----------------------------------------
BIND_RADIO, BIND_NUMBER = 4, 5  # binding-table kind codes (runtime)
BIND_LIST, BIND_CHOICE, BIND_SLIDER = 6, 7, 8  # M6 Phase 2
OB_DROPBUTTON, OB_LIST, OB_VSCROLL, OB_HSCROLL = 5, 9, 11, 12  # CONSTOS.Z80 RSSET #01
# LIST: a frame ob_box, the ob_list inset by 1 px, its ob_vscroll (width 17,
# ROSAN283 "width must be 17") to the right (NIKMACRO n_list_box pattern).
# Font 7, 16 px per row: the font G1 measured, so 24 printable characters
# fit the 305-px text width as they do in a label.
LIST_X, LIST_W, LIST_ROW_H, LIST_FONT = 26, 305, 16, 7
LIST_ROWS_DEFAULT, LIST_ROWS_MIN, LIST_ROWS_MAX = 5, 2, 12
LIST_RECORD_LEN = 30  # type, x,y,w,h, +9 link, +10..21 six words, +22 font, +23 h, +25 Wd24, +28 tab
SCROLL_RECORD_LEN = 14  # type, x,y,w,h, +9 link/reserved, +10 handle position, +12 handle size
SCROLL_ARROW = 17  # assumed arrow-button length at each end of a scroll bar (UIPROBE2 checks)
# CHOICE: optional caption, a framed readout (white box + label showing the
# chosen item), the 17x17 ob_dropbutton linked to the label (MACROS.Z80
# bb_droplist), its droplist below the readout, 13 px per row (bb_droplist).
CHOICE_BOX = (26, 15, 307, 22)
CHOICE_LABEL = (30, 19, 288, 1)
CHOICE_BUTTON = (335, 17, 17, 17)
CHOICE_DROP_ROW, CHOICE_DROP_ROWS = 13, 6
DROP_RECORD_LEN = 27  # type, x,y,w,h, +9 link, +10..17 droplist x,y,w,h, +18 Ntot, +20 Nvis, +22 current, +24 Wd24
# SLIDER: optional caption, an ob_hscroll (ROSAN283 "height must be 17").
SLIDER_BAR = (26, 15, 280, 17)
SLIDER_HANDLE = 20
SLIDER_PITCH = 40
# M9 CANVAS: a white ob_box with a 1-pixel black outline (FIELD_BOX_PARAMS)
# at x=26; the drawing area is the box's inside, 1 pixel in from each edge.
# The row is the box plus CANVAS_GAP below it.
CANVAS_X = 26
CANVAS_GAP = 6
LARGE_RECT = (20, 50, 600, 400)  # WINDOW ..., LARGE: below the menu bar (y 2..19)
LARGE_BOX_RECT = (2, 26, 596, 372)
LARGE_BUTTON_ROWS = (340, 368)
RADIO_PITCH = 24  # one option per row: 19x19 radio at y+3, caption label at y+5
RADIO_BOX = (26, 3, 19, 19)  # x, dy, w, h (the CHECKBOX box, MACROS.Z80 `radio` size)
RADIO_CAPTION = (52, 5, 280, 1)
RADIO_RECORD_LEN = 11  # type, x,y,w,h, status, radio (group) number
NUMBER_FIELD_BOX = (26, 15, 100, 25)  # framed like a TEXTBOX, 6 characters wide
NUMBER_SPINNER = (132, 11, 17, 33)  # x, dy, w, h (NIKMACRO bb_spinedit: 17 x 33)
SPINNER_RECORD_LEN = 10  # type, x,y,w,h, reserved
NUMBER_LEGAL = b"-0123456789"  # explicit legal-character list (os_text_edit +21/+24)
NUMBER_CAPACITY = NUMBERBOX_CHARS + 1
LEGAL_ADDR_OFFSET = 9 + 21  # record offset of the Wd24 legal-character address
# CONSTBIO.Z80 key codes for BUTTON ... KEY k (shift state #80 = ignored)
KEY_CODES = {
    'GREEN': 0xFB, 'RED': 0xFC, 'BLUE': 0xF9, 'YELLOW': 0xFA, 'STOP': 0xFE, 'HELP': 0xEC,
    'F1': 0xF1, 'F2': 0xF2, 'F3': 0xF3, 'F4': 0xF4, 'F5': 0xF5, 'F6': 0xF6, 'F7': 0xF7, 'F8': 0xF8,
}


@dataclass(frozen=True)
class Geometry:
    """Where a window sits and where its rows and buttons go."""

    dialog: tuple[int, int, int, int]
    box: tuple[int, int, int, int]
    button_rows: tuple[int, int]


NORMAL = Geometry(DIALOG_RECT, BOX_RECT, BUTTON_ROWS)
LARGE = Geometry(LARGE_RECT, LARGE_BOX_RECT, LARGE_BUTTON_ROWS)


@dataclass
class DialogObject:
    """One emitted object: its number, kind, bytes and source position."""

    number: int
    kind: str  # 'BOX' | 'LABEL' | 'BUTTON' | 'CHECKBOX' | 'FIELDBOX' | 'TEXTBOX'
    #            | (M5d) 'LABELBOX' | 'DLABEL' (a dynamic label)
    #            | (M6) 'RADIO' | 'NUMBER' (a number field's edit) | 'SPINNER'
    text: str | None
    definition: bytes
    line: int
    column: int


@dataclass
class BindingRow:
    """One TEXTBOX/CHECKBOX binding (runtime binding-table row, D3)."""

    number: int  # object number of the textedit / checkbox
    kind: int  # BIND_TEXTBOX | BIND_CHECKBOX | BIND_LABEL
    var_name: str
    capacity: int  # bytes incl. NUL for TEXTBOX / shown text of a LABEL; 0 for CHECKBOX
    template: bytes  # record prefix the runtime rebuilds the object from
    line: int
    widget: object = None  # M6: the source Widget (NUMBERBOX bounds, RADIO options)
    spinner: int = 0  # M6: NUMBERBOX spinner object number (0 = none)


@dataclass
class DialogLayout:
    """Everything codegen emits for the dialog."""

    definition: bytes  # complete os_dialog_define data
    objects: list[DialogObject]
    handler_rows: list[tuple[int, str]]  # (object number, SUB name), source order
    focus_object: int  # 0 = none
    bindings: list[BindingRow]
    geometry: Geometry = NORMAL  # M6
    # M9: (frame object number, drawing area screen x, y, width, height,
    # widget) of the window's CANVAS, or None
    canvas: tuple | None = None
    canvases: tuple = ()  # M15: every CANVAS of the window, as above, in source order


def _word(value: int) -> bytes:
    assert 0 <= value <= 0xFFFF
    return bytes((value & 0xFF, value >> 8))


def _rect(x: int, y: int, w: int, h: int) -> bytes:
    return _word(x) + _word(y) + _word(w) + _word(h)


def _ascii_z(text: str) -> bytes:
    return text.encode("ascii") + b"\0"


def _label(x: int, y: int, w: int, text: str, linked: int = 0) -> bytes:
    return bytes((OB_LABEL,)) + _rect(x, y, w, LABEL_H) + bytes((linked, LABEL_FONT, LABEL_ALIGN_LEFT)) + _ascii_z(text)


def textedit_params(max_length: int) -> bytes:
    """The 32-byte os_text_edit block of an ob_textedit (ROSAN283).

    +0 mode / +1 highlight are "set by OS" but given as 0,1 — the POC's
    XAnne-proven bytes; +16 dialog font; +21 legal-chars Wd24 with bank 0
    ("all"), +24 length 0; +28 maximum bytes at the destination.
    """
    params = bytearray(32)
    params[1] = 1
    params[16:18] = _word(TEXT_FONT)
    params[28:30] = _word(max_length)
    return bytes(params)


def _fit_error(widget, top: int, height: int, limit: int = BUTTON_Y) -> SourceError:
    return SourceError(
        widget.line,
        widget.column,
        f"the dialog has no room for this {widget.kind}: rows are stacked from "
        f"y={CONTENT_TOP} and must end by the button row at y={limit} "
        f"(LABEL {LABEL_PITCH} px — at most {M3A_MAX_LABELS} LABELs alone —, "
        f"CHECKBOX {CHECK_PITCH} px, TEXTBOX {TEXT_PITCH} px, NUMBERBOX {TEXT_PITCH} px, "
        f"RADIO {RADIO_PITCH} px per option + 4); this row would end at y={top + height}",
    )


def number_template(field_x: int, field_y: int) -> bytes:
    """The 41-byte record prefix of a NUMBERBOX edit (M6).

    As a TEXTBOX edit, with max length NUMBERBOX_CHARS and the explicit
    legal-character list NUMBER_LEGAL (+21 Wd24 address, +24 length). The
    address and bank are left 0 here: codegen writes the runtime list's
    address into the template, and the runtime patches the app bank in
    before each os_object_define (pbas/statements.py, runtime rt_num_*).
    """
    params = bytearray(textedit_params(NUMBERBOX_CHARS))
    params[24] = len(NUMBER_LEGAL)
    ix, idy, iw, ih = TEXT_FIELD_INSET
    bw = NUMBER_FIELD_BOX[2]
    return bytes((OB_TEXTEDIT,)) + _rect(field_x + ix, field_y + idy, bw - iw, ih) + bytes(params)


def _window_of(program, window) -> WindowDecl:
    if window is not None:
        return window
    if getattr(program, "windows", None):
        return program.windows[0]
    line, column = program.dialog_position or (1, 1)
    return WindowDecl(None, program.dialog_title, False, program.widgets, line, column)


def build_dialog(program, window: WindowDecl | None = None, menus: bool = False) -> DialogLayout:
    """Lay out one window's dialog; raise SourceError for what cannot be built.

    *window* defaults to the program's first (or only) window. *menus*
    (M6) sets the global ddm_enable byte so the program's menu bar works
    while the window is open.
    """
    window = _window_of(program, window)
    line, column = window.line, window.column
    geometry = LARGE if window.large else NORMAL
    button_rows = geometry.button_rows
    limit = button_rows[0]
    buttons = [w for w in window.widgets if w.kind == "BUTTON"]
    rows = [w for w in window.widgets if w.kind != "BUTTON"]
    if len(buttons) > MAX_LAYOUT_BUTTONS:
        extra = buttons[MAX_LAYOUT_BUTTONS]
        raise SourceError(
            extra.line,
            extra.column,
            f"the dialog layout holds at most {MAX_LAYOUT_BUTTONS} BUTTONs "
            f"(two rows of {BUTTONS_PER_ROW})",
        )
    if not buttons:
        raise SourceError(
            line,
            column,
            "a WINDOW needs at least one BUTTON: a window without buttons "
            "has no tested way to be closed (add, for example, BUTTON \"Quit\", Quit "
            "with a SUB Quit that runs EXIT)",
        )

    objects: list[DialogObject] = [
        DialogObject(1, "BOX", None, bytes((OB_BOX,)) + _rect(*geometry.box) + BOX_TAIL, line, column)
    ]
    bindings: list[BindingRow] = []
    bound: dict[str, int] = {}
    radio_group = 0

    def add(kind, text, definition, widget):
        objects.append(DialogObject(len(objects) + 1, kind, text, definition, widget.line, widget.column))
        return objects[-1].number

    y = CONTENT_TOP
    canvas = None
    canvases = []  # M15
    for widget in rows:
        if widget.var_name is not None:  # TEXTBOX, CHECKBOX, dynamic LABEL, RADIO, NUMBERBOX
            if widget.var_name in bound:
                raise SourceError(
                    widget.line,
                    widget.column,
                    f"{widget.var_name} is already bound to a control at line "
                    f"{bound[widget.var_name]}; one control per variable",
                )
            bound[widget.var_name] = widget.line
        if widget.kind == "LABEL" and widget.var_name is not None:
            if y + LABEL_PITCH > limit:
                raise _fit_error(widget, y, LABEL_PITCH, limit)
            dx, dy, dw, h = LABEL_BOX
            add("LABELBOX", None,
                bytes((OB_BOX,)) + _rect(LABEL_X + dx, y + dy, LABEL_W + dw, h) + bytes((0,)) + LABEL_BOX_PARAMS,
                widget)
            record = _label(LABEL_X, y, LABEL_W, " " * LABEL_SHOW_MAX)  # slot reservation
            number = add("DLABEL", None, record, widget)
            bindings.append(BindingRow(number, BIND_LABEL, widget.var_name, LABEL_SHOW_MAX + 1,
                                       record[:LABEL_TEMPLATE_LEN], widget.line))
            y += LABEL_PITCH
        elif widget.kind == "LABEL":
            if y + LABEL_PITCH > limit:
                raise _fit_error(widget, y, LABEL_PITCH, limit)
            add("LABEL", widget.caption, _label(LABEL_X, y, LABEL_W, widget.caption), widget)
            y += LABEL_PITCH
        elif widget.kind == "CHECKBOX":
            if y + CHECK_PITCH > limit:
                raise _fit_error(widget, y, CHECK_PITCH, limit)
            box_x, box_dy, box_w, box_h = CHECK_BOX
            if widget.caption is not None:
                cap_x, cap_dy, cap_w, _ = CHECK_CAPTION
                # the caption label precedes and links to the checkbox (POC)
                add("LABEL", widget.caption,
                    _label(cap_x, y + cap_dy, cap_w, widget.caption, linked=len(objects) + 2), widget)
            template = bytes((OB_CHECKBOX,)) + _rect(box_x, y + box_dy, box_w, box_h)
            number = add("CHECKBOX", None, template + bytes((UNCHECKED,)), widget)
            bindings.append(BindingRow(number, BIND_CHECKBOX, widget.var_name, 0, template, widget.line))
            y += CHECK_PITCH
        elif widget.kind == "TEXTBOX":
            if y + TEXT_PITCH > limit:
                raise _fit_error(widget, y, TEXT_PITCH, limit)
            # M8: the variable's own capacity (STRING * n), else the program's
            capacity = program.variables[widget.var_name].capacity
            if capacity > M3B_TEXTBOX_CAPACITY_MAX:
                raise SourceError(
                    widget.line,
                    widget.column,
                    f"a TEXTBOX holds at most {M3B_TEXTBOX_CAPACITY_MAX - 1} characters, but "
                    f"{widget.var_name} can hold {capacity - 1} "
                    + (f"(declare it as DIM {widget.var_name} AS STRING * {M3B_TEXTBOX_CAPACITY_MAX - 1} "
                       "or shorter)"
                       if capacity != program.string_capacity else
                       f"(the program's string capacity: build with --string-capacity "
                       f"{M3B_TEXTBOX_CAPACITY_MAX} or less, or DIM {widget.var_name} AS STRING * "
                       f"{M3B_TEXTBOX_CAPACITY_MAX - 1})"),
                )
            if widget.caption is not None:
                cap_x, cap_dy, cap_w, _ = TEXT_CAPTION
                add("LABEL", widget.caption, _label(cap_x, y + cap_dy, cap_w, widget.caption), widget)
            bx, bdy, bw, bh = TEXT_FIELD_BOX
            ix, idy, iw, ih = TEXT_FIELD_INSET
            # the field box precedes and links to the text edit (Amstrad
            # "OBLIGATORY" ob_box); it paints the background the edit lacks
            add("FIELDBOX", None,
                bytes((OB_BOX,)) + _rect(bx, y + bdy, bw, bh) + bytes((len(objects) + 2,)) + FIELD_BOX_PARAMS,
                widget)
            template = bytes((OB_TEXTEDIT,)) + _rect(bx + ix, y + bdy + idy, bw - iw, ih) + textedit_params(capacity - 1)
            reserve = b" " * (capacity - 1) + b"\0"  # slot reservation, never displayed
            number = add("TEXTBOX", None, template + reserve, widget)
            bindings.append(BindingRow(number, BIND_TEXTBOX, widget.var_name, capacity, template, widget.line))
            y += TEXT_PITCH
        elif widget.kind == "RADIO":  # M6: one group of options
            height = RADIO_PITCH * len(widget.options) + 4
            if y + height > limit:
                raise _fit_error(widget, y, height, limit)
            box_x, box_dy, box_w, box_h = RADIO_BOX
            cap_x, cap_dy, cap_w, _ = RADIO_CAPTION
            records = b""
            first = 0
            for i, option in enumerate(widget.options):
                top = y + RADIO_PITCH * i
                # caption label linked to its radio (the MACROS.Z80 `radio` pattern)
                add("LABEL", option, _label(cap_x, top + cap_dy, cap_w, option, linked=len(objects) + 2), widget)
                record = bytes((OB_RADIO,)) + _rect(box_x, top + box_dy, box_w, box_h) + bytes((UNCHECKED, radio_group))
                number = add("RADIO", None, record, widget)
                first = first or number
                records += record
            bindings.append(BindingRow(first, BIND_RADIO, widget.var_name, len(widget.options),
                                       records, widget.line, widget))
            radio_group += 1
            y += height
        elif widget.kind == "NUMBERBOX":  # M6: whole-number field (+ spinner)
            if y + TEXT_PITCH > limit:
                raise _fit_error(widget, y, TEXT_PITCH, limit)
            if widget.caption is not None:
                cap_x, cap_dy, cap_w, _ = TEXT_CAPTION
                add("LABEL", widget.caption, _label(cap_x, y + cap_dy, cap_w, widget.caption), widget)
            bx, bdy, bw, bh = NUMBER_FIELD_BOX
            add("FIELDBOX", None,
                bytes((OB_BOX,)) + _rect(bx, y + bdy, bw, bh) + bytes((len(objects) + 2,)) + FIELD_BOX_PARAMS,
                widget)
            template = number_template(bx, y + bdy)
            reserve = b" " * NUMBERBOX_CHARS + b"\0"
            number = add("NUMBER", None, template + reserve, widget)
            spinner = 0
            if widget.spin:
                sx, sdy, sw, sh = NUMBER_SPINNER
                spinner = add("SPINNER", None, bytes((OB_SPINNER,)) + _rect(sx, y + sdy, sw, sh) + b"\0", widget)
            bindings.append(BindingRow(number, BIND_NUMBER, widget.var_name, NUMBER_CAPACITY,
                                       template, widget.line, widget, spinner))
            y += TEXT_PITCH
        elif widget.kind == "LIST":  # M6 Phase 2
            rows_shown = widget.rows
            height = rows_shown * LIST_ROW_H + 4
            if y + height + 8 > limit:
                raise _fit_error(widget, y, height + 8, limit)
            add("LISTBOX", None,
                bytes((OB_BOX,)) + _rect(LIST_X, y, LIST_W + 2, height) + bytes((0,)) + FIELD_BOX_PARAMS,
                widget)
            list_no = len(objects) + 1
            record = (bytes((OB_LIST,)) + _rect(LIST_X + 1, y + 1, LIST_W, height - 2)
                      + bytes((list_no + 1,)) + _word(0) + _word(rows_shown) + bytes(8)
                      + bytes((LIST_FONT,)) + _word(LIST_ROW_H) + bytes(3) + _word(0))
            add("LIST", None, record, widget)
            bar = (bytes((OB_VSCROLL,)) + _rect(LIST_X + LIST_W + 4, y, 17, height)
                   + bytes((list_no,)) + _word(0) + _word(max(height - 2 * SCROLL_ARROW, 1)))
            add("VSCROLL", None, bar, widget)
            bindings.append(BindingRow(list_no, BIND_LIST, widget.var_name, rows_shown,
                                       record + bar, widget.line, widget, list_no + 1))
            y += height + 8
        elif widget.kind == "CHOICE":  # M6 Phase 2
            if y + TEXT_PITCH > limit:
                raise _fit_error(widget, y, TEXT_PITCH, limit)
            if widget.caption is not None:
                cap_x, cap_dy, cap_w, _ = TEXT_CAPTION
                add("LABEL", widget.caption, _label(cap_x, y + cap_dy, cap_w, widget.caption), widget)
            bx, bdy, bw, bh = CHOICE_BOX
            add("FIELDBOX", None,
                bytes((OB_BOX,)) + _rect(bx, y + bdy, bw, bh) + bytes((len(objects) + 3,)) + FIELD_BOX_PARAMS,
                widget)
            lx, ldy, lw, _ = CHOICE_LABEL
            label = (bytes((OB_LABEL,)) + _rect(lx, y + ldy, lw, LABEL_H)
                     + bytes((len(objects) + 2, LABEL_FONT, LABEL_ALIGN_LEFT)))
            label_no = add("CHOICELABEL", None, label + b" " * LABEL_SHOW_MAX + b"\0", widget)
            rows_drop = min(CHOICE_DROP_ROWS, widget.length)
            drop_y = y + bdy + bh + 1
            drop_h = 2 + rows_drop * CHOICE_DROP_ROW
            if drop_y + drop_h > geometry.dialog[3] - 2:
                raise SourceError(widget.line, widget.column,
                                  "the CHOICE's drop-down list would extend below the window; "
                                  "place the CHOICE higher or use a LARGE window")
            ux, udy, uw, uh = CHOICE_BUTTON
            drop = (bytes((OB_DROPBUTTON,)) + _rect(ux, y + udy, uw, uh) + bytes((label_no,))
                    + _rect(bx, drop_y, bw, drop_h) + _word(0) + _word(rows_drop) + _word(0) + bytes(3))
            number = add("DROPBUTTON", None, drop, widget)
            bindings.append(BindingRow(number, BIND_CHOICE, widget.var_name, rows_drop,
                                       drop + label, widget.line, widget, label_no))
            y += TEXT_PITCH
        elif widget.kind == "CANVAS":  # M9
            pitch = widget.height + 2 + CANVAS_GAP
            if y + pitch - CANVAS_GAP > limit:
                raise _fit_error(widget, y, pitch - CANVAS_GAP, limit)
            box_x, _, box_w, _ = geometry.box
            if CANVAS_X + widget.width + 2 > box_x + box_w:
                raise SourceError(widget.line, widget.column,
                                  f"a CANVAS in this window is at most {box_x + box_w - CANVAS_X - 2} "
                                  f"pixels wide (got {widget.width}); a LARGE window holds a wider one")
            frame = (bytes((OB_BOX,)) + _rect(CANVAS_X, y, widget.width + 2, widget.height + 2)
                     + bytes((0,)) + FIELD_BOX_PARAMS)
            number = add("CANVAS", None, frame, widget)
            dx, dy = geometry.dialog[0], geometry.dialog[1]
            canvases.append((number, dx + CANVAS_X + 1, dy + y + 1, widget.width, widget.height, widget))
            canvas = canvas or canvases[-1]
            y += pitch
        elif widget.kind == "SLIDER":  # M6 Phase 2
            if y + SLIDER_PITCH > limit:
                raise _fit_error(widget, y, SLIDER_PITCH, limit)
            if widget.caption is not None:
                cap_x, cap_dy, cap_w, _ = TEXT_CAPTION
                add("LABEL", widget.caption, _label(cap_x, y + cap_dy, cap_w, widget.caption), widget)
            sx, sdy, sw, sh = SLIDER_BAR
            bar = (bytes((OB_HSCROLL,)) + _rect(sx, y + sdy, sw, sh) + bytes((0,))
                   + _word(0) + _word(SLIDER_HANDLE))
            number = add("HSCROLL", None, bar, widget)
            bindings.append(BindingRow(number, BIND_SLIDER, widget.var_name, 0, bar, widget.line, widget))
            y += SLIDER_PITCH
        else:
            raise AssertionError(f"unexpected widget {widget.kind}")

    handler_rows: list[tuple[int, str]] = []
    focus = 0
    width = geometry.dialog[2]
    for row, top in enumerate(button_rows):
        in_row = buttons[row * BUTTONS_PER_ROW : (row + 1) * BUTTONS_PER_ROW]
        total = len(in_row) * BUTTON_PITCH - (BUTTON_PITCH - BUTTON_W)
        left = (width - total) // 2
        for i, button in enumerate(in_row):
            rect = (left + i * BUTTON_PITCH, top, BUTTON_W, BUTTON_H)
            keys = button_keys(button)
            body = bytes((OB_TEXTBUTTON,)) + _rect(*rect) + keys + bytes((0,))
            number = add("BUTTON", button.caption, body + _ascii_z(button.caption), button)
            handler_rows.append((number, button.handler))
            if button.default:
                focus = number

    header = bytes((GLOBAL_FOCUS, GLOBAL_EXIT_BY_CLICK, GLOBAL_SCREEN_STORE, 1 if menus else GLOBAL_DDM_ENABLE))
    box = bytes((DG_DIALOG_BOX,)) + _rect(*geometry.dialog) + _ascii_z(window.title)
    definition = header + box + b"".join(o.definition for o in objects) + b"\0"
    layout = DialogLayout(definition, objects, handler_rows, focus or handler_rows[0][0], bindings, geometry,
                          canvas, tuple(canvases))
    validate_layout(layout, line, column)
    return layout


def button_keys(button) -> bytes:
    """The 8 keycode bytes of a text button: Return first for DEFAULT (M5d),
    then each KEY (M6), shift state #80 = ignored; unused pairs zero."""
    keys = RETURN_KEYS[:2] if button.default else b""
    for name in getattr(button, "keys", ()):
        keys += bytes((KEY_CODES[name], 0x80))
    return keys + bytes(8 - len(keys))


def _rect_of(obj: DialogObject) -> tuple[int, int, int, int]:
    return tuple(int.from_bytes(obj.definition[1 + 2 * i : 3 + 2 * i], "little") for i in range(4))


def validate_layout(layout: DialogLayout, line: int, column: int) -> None:
    """Check the built definition against the documented limits.

    Compile-time proofs, before any assembly: each record has its documented
    size, texts fit their documented maxima, numbers are sequential bytes,
    every object lies inside the dialog box, textbox slots reserve exactly
    max-length + 1 bytes, binding templates are prefixes of their records,
    and the whole definition is within the 16K os_dialog_define limit.
    """
    fixed = {"BOX": 14, "FIELDBOX": 14, "LABELBOX": 14, "CANVAS": 14, "LABEL": 12, "BUTTON": 18,
             "CHECKBOX": CHECKBOX_RECORD_LEN, "RADIO": RADIO_RECORD_LEN,
             "SPINNER": SPINNER_RECORD_LEN, "LISTBOX": 14, "LIST": LIST_RECORD_LEN,
             "VSCROLL": SCROLL_RECORD_LEN, "HSCROLL": SCROLL_RECORD_LEN,
             "DROPBUTTON": DROP_RECORD_LEN}
    doc_max = {"LABEL": LABEL_TEXT_DOC_MAX, "BUTTON": BUTTON_TEXT_DOC_MAX}
    by_number = {}
    for expected, obj in enumerate(layout.objects, start=1):
        by_number[obj.number] = obj
        if obj.number != expected or obj.number > OBJECT_NUMBER_MAX:
            raise SourceError(obj.line, obj.column, f"dialog object number {obj.number} is invalid")
        if obj.kind in ("TEXTBOX", "NUMBER"):
            max_len = int.from_bytes(obj.definition[9 + 28 : 9 + 30], "little")
            slot_text = obj.definition[TEXTEDIT_TEXT_OFFSET:]
            if max_len > TEXTEDIT_LENGTH_DOC_MAX or slot_text != b" " * max_len + b"\0":
                raise AssertionError(f"textbox {obj.number} slot does not reserve max length + 1")
            # the runtime clears a changed textbox by updating object number-1
            box = layout.objects[obj.number - 2] if obj.number >= 2 else None
            if box is None or box.kind != "FIELDBOX" or box.definition[9] != obj.number:
                raise AssertionError(f"textbox {obj.number} is not preceded by its linked field box")
        elif obj.kind == "CHOICELABEL":  # M6 Phase 2: slot for the 24-character readout
            if obj.definition[LABEL_TEMPLATE_LEN:] != b" " * LABEL_SHOW_MAX + b"\0":
                raise AssertionError(f"choice label {obj.number} slot does not reserve {LABEL_SHOW_MAX}")
        elif obj.kind == "DLABEL":
            # M5d: the slot reserves LABEL_SHOW_MAX characters; the runtime
            # clears the label by updating object number-1, its LABELBOX.
            if obj.definition[LABEL_TEMPLATE_LEN:] != b" " * LABEL_SHOW_MAX + b"\0":
                raise AssertionError(f"dynamic label {obj.number} slot does not reserve {LABEL_SHOW_MAX}")
            box = layout.objects[obj.number - 2] if obj.number >= 2 else None
            if box is None or box.kind != "LABELBOX":
                raise AssertionError(f"dynamic label {obj.number} is not preceded by its box")
            bx, by, bw, bh = _rect_of(box)
            lx, ly, lw, _ = _rect_of(obj)
            if not (bx <= lx and by <= ly and lx + lw <= bx + bw and ly + LABEL_GLYPH_H <= by + bh):
                raise AssertionError(f"dynamic label {obj.number} lies outside its box")
            # the box is painted over whatever it covers: nothing else may be there
            for other in layout.objects[1:]:
                if other is box or other is obj:
                    continue
                ox, oy, ow, oh = _rect_of(other)
                if ox < bx + bw and bx < ox + ow and oy < by + bh and by < oy + oh:
                    raise AssertionError(
                        f"dynamic label box {box.number} overlaps object {other.number}"
                    )
        else:
            text_len = 0 if obj.text is None else len(obj.text.encode("ascii")) + 1
            if len(obj.definition) != fixed[obj.kind] + text_len:
                raise AssertionError(f"object {obj.number} definition has the wrong size")
            if obj.kind in doc_max and text_len - 1 > doc_max[obj.kind]:
                raise SourceError(
                    obj.line, obj.column,
                    f"{obj.kind} text exceeds the documented maximum of {doc_max[obj.kind]}",
                )
        x, y, w, h = (int.from_bytes(obj.definition[1 + 2 * i : 3 + 2 * i], "little") for i in range(4))
        if x + w > layout.geometry.dialog[2] or y + h > layout.geometry.dialog[3]:
            raise SourceError(obj.line, obj.column, f"{obj.kind} lies outside the dialog box")
    for row in layout.bindings:
        record = by_number[row.number].definition
        if row.kind in (BIND_LIST, BIND_CHOICE, BIND_SLIDER):  # M6 Phase 2
            if row.kind == BIND_LIST:
                assert row.template == record + by_number[row.number + 1].definition
                assert by_number[row.number - 1].kind == "LISTBOX"
            elif row.kind == BIND_CHOICE:
                assert row.template == record + by_number[row.spinner].definition[:LABEL_TEMPLATE_LEN]
                assert row.spinner == row.number - 1 and record[9] == row.spinner
            else:
                assert row.template == record
            continue
        if row.kind == BIND_RADIO:  # M6: n consecutive 11-byte records, radios 2 apart
            n = row.capacity
            assert len(row.template) == RADIO_RECORD_LEN * n
            for i in range(n):
                obj = by_number[row.number + 2 * i]
                assert obj.kind == "RADIO" and obj.definition == row.template[11 * i : 11 * (i + 1)]
                caption = by_number[row.number + 2 * i - 1]
                assert caption.kind == "LABEL" and caption.definition[9] == obj.number
            continue
        assert record.startswith(row.template), "binding template must prefix its record"
        assert len(row.template) == {
            BIND_TEXTBOX: TEXTEDIT_TEMPLATE_LEN,
            BIND_CHECKBOX: CHECKBOX_TEMPLATE_LEN,
            BIND_LABEL: LABEL_TEMPLATE_LEN,
            BIND_NUMBER: TEXTEDIT_TEMPLATE_LEN,
        }[row.kind]
        if row.kind == BIND_NUMBER:  # M6: field box before, spinner (if any) after
            box = by_number[row.number - 1]
            assert box.kind == "FIELDBOX" and box.definition[9] == row.number
            assert row.spinner in (0, row.number + 1)
    if len(layout.definition) > DIALOG_DEFINITION_MAX:
        raise SourceError(
            line, column,
            f"dialog definition is {len(layout.definition)} bytes; "
            f"os_dialog_define accepts at most {DIALOG_DEFINITION_MAX}",
        )
    buttons = {o.number for o in layout.objects if o.kind == "BUTTON"}
    # M5d: buttons in two rows must never overlap one another
    rects = [(o, _rect_of(o)) for o in layout.objects if o.kind == "BUTTON"]
    for i, (a, (ax, ay, aw, ah)) in enumerate(rects):
        for b, (bx, by, bw, bh) in rects[i + 1:]:
            if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                raise AssertionError(f"buttons {a.number} and {b.number} overlap")
    for number, _ in layout.handler_rows:
        assert number in buttons, "handler row for a non-button object"
