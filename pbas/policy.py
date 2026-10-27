"""Stage-1 language and layout policy constants — single source of truth.

Basis of each constant (LANGUAGE-SPEC.md section 6 and ARCHITECTURE.md D4/D5):
- "doc":    derived from Supporting Docs/ROSAN283.DOC
- "POC":    carried over from audited prototype behaviour
- "policy": conservative choice pending XAnne measurement / owner review

Semantics (M1) checks these; codegen/layout (M3) consumes the same constants.
They are policy, not architecture: each is a named constant a later milestone
may lift or re-derive with an XAnne script (MIGRATION-PLAN M3/M5 gates).
"""
from __future__ import annotations

import re

# --- STRING capacity (spec section 4, ARCHITECTURE D5) -----------------------
DEFAULT_STRING_CAPACITY = 64  # bytes including the NUL terminator
MIN_STRING_CAPACITY = 2  # spec section 4: compiler option range
MAX_STRING_CAPACITY = 127  # spec section 4: compiler option range
TEXTBOX_CAPACITY_MAX = 128  # doc: textedit maximum length field

# --- Single-dialog widget caps (policy; POC caps retained pending auto-layout)
MAX_LABELS = 8
MAX_CHECKBOXES = 8
MAX_BUTTONS = 8
# TEXTBOX has no M1 count cap; bounded by the 16K dialog definition size (doc),
# asserted at build time in M3 (ARCHITECTURE D4).

# --- Text length limits (policy unless noted) --------------------------------
WINDOW_TITLE_MAX = 35  # POC-measured
LABEL_TEXT_MAX = 47  # policy, pending auto-layout
# M5d recovery: a *dynamic* label shows at most 24 printable ASCII characters
# (#20-#7E). Basis: 24 x 12 px = 288 px <= the 305-px label (font-7 W = 11 px,
# measured in XAnne; every printable character checked by XAnne script G1).
# Rosanne does not reliably clip a label and its width call is unusable
# (WIDTHDG), so the content itself bounds the drawn width.
DYNAMIC_LABEL_MAX = 24
CAPTION_MAX = 34  # TEXTBOX / CHECKBOX caption
BUTTON_CAPTION_MAX = 14

# --- Comparison / LEN scratch (M2.1) -----------------------------------------
# A *computed* STRING operand of = / == / <> or of LEN (STR$, a substring) is
# materialised in a 128-byte runtime scratch buffer (rt_cmp_buf1/2). Its
# worst-case length is known at compile time and must not exceed this.
SCRATCH_STRING_MAX = 127

# --- Nesting limits (M2.1, policy; D7) ---------------------------------------
# Deeper programs used to crash the compiler with a Python RecursionError.
# Expression depth also bounds generated stack use (one word per level,
# against the documented ~2K stack, ROSAN283 'Memory Layout').
MAX_EXPRESSION_DEPTH = 100  # longest operator/operand path in one expression
MAX_BLOCK_DEPTH = 64  # nested IF/WHILE/FOR/SUB blocks
# M5c: procedures active at once through CALL (a button handler or the first
# SUB the main line calls counts as one). 2 stack bytes each (return address;
# nothing else is on the stack at statement level): 32 of the ~2K stack.
MAX_CALL_DEPTH = 16

# --- MESSAGE alert budget (spec section 6; buffer size POC-proven) -----------
MESSAGE_LITERAL_MAX = 250  # policy cap on a pure-literal MESSAGE
ALERT_BUFFER_SIZE = 160  # POC dyn_message buffer
STRS_BUDGET = 6  # worst-case STR$ output "-32768"

# --- DOS 8.3 file names (spec section 7) -------------------------------------
# Case-insensitive acceptance (DOS file names are case-insensitive); the
# pattern is the spec's [A-Z0-9_]{1,8}.[A-Z0-9]{1,3}.
FILENAME_RE = re.compile(r"[A-Za-z0-9_]{1,8}\.[A-Za-z0-9]{1,3}")
FILENAME_PATTERN_TEXT = "[A-Z0-9_]{1,8}.[A-Z0-9]{1,3}"

# --- File contents (M4, spec section 7) --------------------------------------
# FILESAVE builds its value in the runtime file buffer: at most 127 bytes
# (the largest STRING a program can hold, MAX_STRING_CAPACITY - 1). FILELOAD
# reads at most capacity - 1 bytes; a longer file is refused, never cut.
FILE_TEXT_MAX = MAX_STRING_CAPACITY  # 127 bytes (a STRING holds at most 126)
FILE_BUFFER_SIZE = 640  # byte <= 126 read at +i, plus a block fill of <= 511 (runtime 'Files')

# --- M6 Phase 1: native application interfaces (LANGUAGE-SPEC §5.1) ----------
MAX_WINDOWS = 8  # policy: named windows per program, one on screen at a time
RADIO_OPTIONS_MIN, RADIO_OPTIONS_MAX = 2, 6  # policy (24-px rows)
MAX_RADIO_GROUPS = 16  # doc: ob_radio "Radio Number 0...15"
NUMBERBOX_CHARS = 6  # "-32768"; legal characters "-0123456789"
ASK_TEXT_MAX = 100  # policy: alert text; the button block follows in rt_alert_buf
ASK_CAPTION_MAX = 10  # policy, unmeasured alert button font
ASK_BUTTONS_MIN, ASK_BUTTONS_MAX = 2, 3
MAX_BUTTON_KEYS = 3  # doc: 4 keycode pairs per ob_textbutton, one kept for DEFAULT
MAX_MENUS = 8  # doc max 10 titles; the Tasks menu is one; margin kept
MENU_ITEMS_MAX = 20  # doc: "Max entries per title = 20" (dividers count)
MENU_TITLE_MAX = 12  # policy, unmeasured menu font
MENU_ITEM_MAX = 20  # policy, unmeasured menu font
MENU_AREA = 2048  # doc: "Max total length of all entry data = 2048 bytes"
TIMER_SECONDS_MAX = 3599  # doc: interval in 1/16 s, at most 57599
TIMER_TICKS_MAX = 32767  # M13: TIMER ... EVERY n TICKS, n sixteenths of a second (an INTEGER literal; doc 57599)

# --- M6 Phase 2: arrays and data-rich controls (LANGUAGE-SPEC §5.2) -----------
ARRAY_LENGTH_MAX = 250  # policy: elements per array (list pointer tables are 3 x n)
BANKED_LENGTH_MAX = 32767  # M8: elements of a BANKED array (an INTEGER index)
BANKED_BLOCKS_MAX = 32  # M8 policy: 16K blocks for all BANKED arrays together (512K)
BANKED_READS_MAX = 4  # M8: BANKED elements one statement may read (the runtime's read windows)
BLOCK_SIZE = 16384  # ROSAN283 "RAM can be got from the OS in 16k lumps"
SLIDER_RANGE_MAX = 250  # policy: MAX - MIN of a SLIDER (handle arithmetic stays within 16 bits)
