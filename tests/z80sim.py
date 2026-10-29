"""Z80 behavioural simulator for M2 codegen tests — an engineering aid, not an evidence tier.

PURPOSE: executes the machine code the M2 compiler generates (the .PRG image,
program portion plus appended ``runtime/runtime.z80.asm`` text) on a small CPU
model, so that ``tests/test_behaviour.py`` can observe the text of every
MESSAGE alert and the os_app_exit stop without Rosanne or an emulator.

Per ``PcW16-BASIC/TESTING-STRATEGY.md`` this simulator is explicitly NOT a test
tier and must never be cited as runtime, emulator or XAnne evidence; XAnne
remains the only runtime evidence (tier 5). A green behavioural test here only
means "the generated code does what this test expects on this CPU model".

The model is deliberately bounded. ``CPU.step`` dispatches exactly the opcode
inventory the M2 emitter and runtime are contracted to use and raises loudly
— with the offending opcode in hex — on anything else, never a silent skip.
The only platform interface is intercepted at the two documented boundaries:

- ``call 003Bh`` (Rosanne OS dispatch; ROSAN283.DOC "Calling the OS",
  OSCALLS.INC.txt): A=23 ``os_app_exit`` stops the run as success; A=76
  ``os_alert`` decodes the alert definition addressed by HL (DE bytes) and
  appends its text to ``cpu.alerts`` (ROSAN283.DOC "os_alert" definition
  format: NUL-terminated ASCII lines, an extra NUL, then the button block);
  any other A raises SimError — the invariant that M2 programs only exit and
  alert through the runtime.
- ``call 000CBh`` (``bios_getmem1``; ROSAN283.DOC): returns a fake app bank
  number in A, preserving everything else.

M3a adds the dialog/event subset (function numbers counted from
OSCALLS.INC.txt under CONSTOS.Z80's ``RSSET 1``): 2 ``os_wait_event`` (pops
the next entry of a scripted event list; when the script is exhausted the
run stops as *idle*), 4 ``os_process_event`` (checks IX addresses the event
record it handed out), 66 ``os_dialog_define`` (decodes the definition with
``decode_dialog``, written independently from ROSAN283 'os_dialog_define'),
67 ``os_dialog_display``, 68 ``os_dialog_remove``, 73 ``os_set_focus``.

Register poisoning: after every OS call the registers ROSAN283 documents as
corrupted are overwritten with junk (``POISON``), so generated code that
keeps a value live across a call fails here rather than passing by luck
(the POC's F4 class of bug).

Reset state follows ARCHITECTURE.md D7/F10: the image loads at #4000, PC
starts at #4100 (ROSAN283.DOC "Memory Layout"), SP at #3FFE, all registers
zero. Memory is a flat 64K with no interrupts; EI/DI are treated as NOP. If
the program runs off into the zero padding, the resulting nop-slide exhausts
the step budget and raises SimRunaway — a test failure, by design.
"""
from __future__ import annotations

from pathlib import Path

APP_IMAGE_ORIGIN = 0x4000  # ARCHITECTURE D7: .PRG container org
APP_ENTRY_POINT = 0x4100  # ROSAN283.DOC 'Memory Layout': execution starts at #4100
STACK_TOP = 0x3FFE  # ARCHITECTURE F10: stack descends from #3FFE
OS_DISPATCH = 0x003B  # ROSAN283.DOC: call #003B with the function number in A
BIOS_GETMEM1 = 0x00CB  # ROSAN283.DOC: bios_getmem1, app bank number returned in A
# M9 code banks: ROSAN283 BIOS table, call #80 + 3 x n: bios_setmem2 (#16)
# "set memory block for #8000...#BFFF ... all flags & regs preserved",
# bios_getmem2 (#1A) "out: A = block number ... all flags & other regs
# preserved".
BIOS_SETMEM2 = 0x00C2
BIOS_GETMEM2 = 0x00CE
# M9 CANVAS: the screen and the BIOS graphics entries (ROSAN283 BIOS table,
# #80 + 3 x n) and OS functions (OSCALLS.INC.txt) the runtime draws with.
SCREEN_W, SCREEN_H = 640, 480
BIOS_SETINK, BIOS_GETINK, BIOS_SETMODE, BIOS_GETMODE = 0xE0, 0xE3, 0xE6, 0xE9
BIOS_PIXEL, BIOS_LINE, BIOS_RECTANG = 0xF2, 0xF8, 0xFB
BIOS_GRAPHICS = (BIOS_SETINK, BIOS_GETINK, BIOS_SETMODE, BIOS_GETMODE, BIOS_PIXEL, BIOS_LINE,
                 BIOS_RECTANG)
# M12 bitmaps (ROSAN283 BIOS #27, #2E, #31). [static: PCW045.SYS] the screen
# is 80 bytes a row, bit 7 leftmost, a set bit white; the model's bitmaps use
# that layout ((w + 7) // 8 bytes a row) and insists on the runtime's own
# contract: parameters and capture buffer in the bottom quarter, plotting in
# black ink and opaque mode, the pointer hidden.
BIOS_GETPXL, BIOS_PLOTBITMAP, BIOS_GETBITMAP = 0xF5, 0x10A, 0x113
# M13: ROSAN283 bios_plotmaskedbitmap #2F (call #80 + 3 x #2F)
BIOS_PLOTMASKED = 0x10D
# M13: ROSAN283 bios_keystate #03 (call #80 + 3 x 3)
BIOS_KEYSTATE = 0x89
FN_OS_DIALOG_STRING = 81
FN_OS_MOUSE_OFF, FN_OS_MOUSE_ON, FN_OS_GET_MOUSE_XY = 111, 112, 114
FN_OS_SCR_DIRECT = 117
CANVAS_FNS = (FN_OS_DIALOG_STRING, FN_OS_MOUSE_OFF, FN_OS_MOUSE_ON, FN_OS_GET_MOUSE_XY,
              FN_OS_SCR_DIRECT)
EV_LEFT_CLICK, EV_LEFT_RELEASE, EV_MOVE = 1 << 8, 1 << 10, 1 << 11
TEXT_CELL_W, TEXT_CELL_H = 11, 16  # the model draws a text character as an 11 x 16 cell
Q2_START_BLOCK = 0x83  # model: the (OS) block at #8000 when the program starts
LOADER_LIMIT = 0x4000  # os_run_program reads at most #4000 bytes (M8 research §3)
FN_OS_APP_EXIT = 23  # OSCALLS.INC.txt: os_app_exit
FN_OS_ALERT = 76  # OSCALLS.INC.txt: os_alert
FN_OS_GET_EVENT = 1  # OSCALLS.INC.txt line 1 under RSSET 1 (M13 RT6: TICKS loops poll)
FN_OS_WAIT_EVENT = 2  # OSCALLS.INC.txt line 2 under RSSET 1 (os_get_event is 1)
FN_OS_PROCESS_EVENT = 4
FN_OS_DIALOG_DEFINE = 66
FN_OS_DIALOG_DISPLAY = 67
FN_OS_DIALOG_REMOVE = 68
FN_OS_SET_FOCUS = 73
EVENT_RECORD = 0x2E00  # where the model's OS keeps the 12-byte event record
POISON = 0xA5  # junk byte for documented-corrupt registers
# Event codes / message ids (ROSAN283 'os_get_event'; CONSTOS.Z80 RSSET 1).
EV_OS_MESSAGE = 1 << 13
EV_KEYBOARD = 1 << 14
OM_TOPBAR = 1
OM_OBJEVENT = 4
OM_EXIT = 5
OBEV_CLICK = 1
OBEV_DCLICK = 2
OBEV_KEY = 3  # CONSTOS.Z80 RSSET #01: click 1, dclick 2, key 3 (M5d)
# Object types (CONSTOS.Z80 RSSET #01) and the dialog box code.
OB_BOX, OB_LABEL, OB_TEXTBUTTON = 1, 2, 3
OB_CHECKBOX, OB_TEXTEDIT = 6, 8
OB_RADIO, OB_SPINNER = 7, 13  # M6 Phase 1
OB_DROPBUTTON, OB_LIST, OB_VSCROLL, OB_HSCROLL = 5, 9, 11, 12  # M6 Phase 2 (CONSTOS.Z80)
# record lengths (ROSAN283 os_dialog_define object tails)
FIXED_RECORD_LEN = {OB_CHECKBOX: 10, OB_RADIO: 11, OB_SPINNER: 10,
                    OB_DROPBUTTON: 27, OB_LIST: 30, OB_VSCROLL: 14, OB_HSCROLL: 14}
LIST_ITEM_MODEL_MAX = 128  # model: an item text longer than this is a runaway pointer
DG_DIALOG_BOX = 16
# M6 Phase 1: more OS functions (OSCALLS.INC.txt, counted from 1).
FN_OS_SET_TIMER = 8
FN_OS_KILL_TIMER = 9
FN_OS_DDM_DEFINE = 12
FN_OS_DDM_DISPLAY = 13
FN_OS_DDM_GET_TASKS = 14
FN_OS_DDM_GET_ENTRY_STATUS = 17
FN_OS_DDM_PUT_ENTRY_STATUS = 18
FN_OS_BEEP = 50
FN_OS_FLUSH_EVENTS = 5
EV_TIMER = 1 << 0  # ROSAN283 os_get_event event code bits
EV_DDM = 1 << 1
OBEV_FOCFIRE = 12
LOW_BANK = 0x80  # block #80, the bottom quarter (ROSAN283 'Memory Layout')
# The model's Tasks menu (os_ddm_get_tasks output). Its real size is what
# UIPROBE reports; this one is a plausible stand-in in the documented format.
# M13 corrective: its entries' hotkey words are not #0000. Rosanne's hotkey
# search (ddm_hotkey) stops a title at #0000, so a #0000 in the real Tasks
# menu would have put every program's shortcuts in the wrong title; MDEDIT
# III / IV's shortcuts all worked in XAnne (owner, M11 and M12).
MODEL_TASKS_MENU = (bytes((0x80, 0, 0)) + b"Tasks|"
                    + bytes((0x80, 0, 0xFF)) + b"Desktop|"
                    + bytes((0x80, 0, 0xFF)) + b"Exit" + b"\0")
# M3b: banked access and object (re)definition.
FN_OS_GET_BYTE_24BIT = 42
FN_OS_ADD_24BIT = 48
FN_OS_OBJECT_DEFINE = 69
FN_OS_OBJECT_GET_DEFINE = 70
FN_OS_OBJECT_UPDATE = 72
FN_OS_OBJECT_DISPLAY = 71  # OSCALLS.INC.txt line 71 (M6 Phase 2 repair)
FN_OS_DIALOG_STRING_WIDTH = 82  # OSCALLS.INC.txt line 82 (TEXTWIDTH, M11 corrective; WIDTHDG)
# M13 corrective: the numbers bios_keystate keeps a key's state under, by
# key, as Rosanne's keyboard interrupt makes them [static: PCW045.SYS block
# 6 #69A0..#6A6B]: a key's PS/2 set-2 scan code, except that a key sent with
# the #E0 prefix is translated by the table at #6A31 (pairs, ended by #00:
# 11 10, 14 13, 4A 6D, 5A 5C, 69 6A, 6B 63, 6C 6E, 70 50, 71 51, 72 62,
# 74 64, 75 65, 7A 5F, 7C 39, 7D 5E). The owner's SPRPROBE in XAnne showed
# Left 99, Right 100, Up 101, Down 98, Space 41, A 28 (M13, banked and not).
# Before this correction the model gave the cursor keys their keypad codes
# (107, 116, 117, 114), as the M13 audit had misread the table.
SET2 = {"A": 0x1C, "B": 0x32, "C": 0x21, "D": 0x23, "E": 0x24, "F": 0x2B, "G": 0x34, "H": 0x33,
        "I": 0x43, "J": 0x3B, "K": 0x42, "L": 0x4B, "M": 0x3A, "N": 0x31, "O": 0x44, "P": 0x4D,
        "Q": 0x15, "R": 0x2D, "S": 0x1B, "T": 0x2C, "U": 0x3C, "V": 0x2A, "W": 0x1D, "X": 0x22,
        "Y": 0x35, "Z": 0x1A, "0": 0x45, "1": 0x16, "2": 0x1E, "3": 0x26, "4": 0x25, "5": 0x2E,
        "6": 0x36, "7": 0x3D, "8": 0x3E, "9": 0x46, "SPACE": 0x29, "RETURN": 0x5A, "ESC": 0x76,
        "TAB": 0x0D, "BACKSPACE": 0x66, "LSHIFT": 0x12, "RSHIFT": 0x59, "CTRL": 0x14, "ALT": 0x11,
        "KP0": 0x70, "KP1": 0x69, "KP2": 0x72, "KP3": 0x7A, "KP4": 0x6B, "KP5": 0x73, "KP6": 0x74,
        "KP7": 0x6C, "KP8": 0x75, "KP9": 0x7D}
E0_KEYS = {"RALT": 0x11, "RCTRL": 0x14, "KPDIVIDE": 0x4A, "KPENTER": 0x5A, "END": 0x69,
           "LEFT": 0x6B, "HOME": 0x6C, "INSERT": 0x70, "DELETE": 0x71, "DOWN": 0x72,
           "RIGHT": 0x74, "UP": 0x75, "PGDN": 0x7A, "PRINTSCREEN": 0x7C, "PGUP": 0x7D}
E0_TABLE = bytes.fromhex("11 10 14 13 4a 6d 5a 5c 69 6a 6b 63 6c 6e 70 50 71 51 72 62 74 64 75 65 7a 5f 7c 39 7d 5e 00")


def keystate_code(key) -> int:
    """The bios_keystate number of *key*: a name of SET2 or E0_KEYS, or a number as it is."""
    if isinstance(key, int):
        return key
    if key in E0_KEYS:
        pairs = dict(zip(E0_TABLE[0:-1:2], E0_TABLE[1::2]))
        return pairs[E0_KEYS[key]]
    return SET2[key]


# M11 corrective: bios_gettime (ROSAN283 BIOS #10, call #B0): E ticks, D
# seconds, C minutes, B hours. The model clock runs from CLOCK_START at
# CLOCK_RATE instructions per second (a model of time, not of the PcW16).
BIOS_GETTIME = 0x00B0
CLOCK_RATE = 2_000_000
CLOCK_START = 12 * 3600 + 34 * 60 + 56


def dialog_font_width(text: bytes, font: int) -> int:
    """M15: a MODEL of dialog font *font*'s advances (1..12): font 7 as
    font7_width, the others scaled from it by (font + 4) / 11. Not Rosanne's
    fonts (XAnne, M15a T1/T2: every font draws, each with its own widths;
    their figures were not recorded); only for exercising the runtime's
    measuring (DRAW FONT, TEXTWIDTH, the right-edge cut, ALIGN)."""
    width = font7_width(text)
    return width if font == 7 else (width * (font + 4) + 5) // 11


def font7_width(text: bytes) -> int:
    """Model of dialog font 7 advances in pixels (M5d repair).

    Measured in XAnne (owner screenshot docs/xanne-evidence/m5d-d3/
    d3-long-clipped.png, 1:1 scale): a capital W advances 11 px;
    "Label tests: long, short, empty" is 170 px and "Last: 1 (47
    characters)" 131 px. The table below is an estimate that is never
    narrower than those measurements (176 and 134 px) and matches W exactly;
    codes >= 128 count as 11. It is a model for exercising the runtime's
    use of os_dialog_string_width, not Rosanne's font: the real limit is
    Rosanne's own measurement at run time.
    """
    total = 0
    for code in text:
        c = chr(code)
        if code >= 128 or c in "WMmw":
            total += 11
        elif c == " " or c in "il.,:;'!|":
            total += 3
        elif c in "jtfr()":
            total += 5
        elif c.isupper():
            total += 8
        else:
            total += 7
    return total
OS_BANK = 0x81  # the model OS keeps its dialog copy in this RAM block
OS_COPY_BASE = 0x1000  # 14-bit offset of the copy inside OS_BANK
TEXTEDIT_TEXT = 41  # ob_textedit: +9 32-byte params, +41 text
LABEL_TEXT = 12  # ob_label: +9 linked, +10 font, +11 alignment, +12 text (M5d)
TEXTEDIT_MAXLEN = 9 + 28  # params +28 Word: maximum bytes available
FAKE_APP_BANK = 0x42  # plausible bank number; nothing in the model depends on it
# M4: filing functions (OSCALLS.INC.txt; ROSAN283 "THE FILING FUNCTIONS").
FN_OS_SET_DEVICE = 127
FN_OS_SET_CWD = 135
FN_OS_OPEN_FILE = 144
FN_OS_CLOSE_FILE = 145
FN_OS_WRITE_FILE = 146
FN_OS_READ_FILE = 147
# M8 memory management (OSCALLS.INC positions; ROSAN283 "os_ask_mem" ..
# "os_copy_24bit"). The model hands out blocks from a pool, fills them with
# MEM_JUNK (unspecified contents), refuses any access to a block the program
# does not own and any copy across a 16K block end, and does NOT release a
# program's blocks at os_app_exit: the runtime must give them back itself
# (ROSAN283 "You must also remember to release RAM"), which tests check.
FN_OS_ASK_MEM = 33
FN_OS_GET_MEM = 34
FN_OS_RELEASE_MEM = 35
FN_OS_GET_MEM_OWNERID = 38
FN_OS_COPY_24BIT = 41
MEM_FNS = (FN_OS_ASK_MEM, FN_OS_GET_MEM, FN_OS_RELEASE_MEM, FN_OS_GET_MEM_OWNERID, FN_OS_COPY_24BIT)
MEM_POOL = tuple(range(0x90, 0xB0))  # model: 32 free RAM blocks
# M12 printing (ROSAN283 83..105): the model's typo fonts, as os_typo_getlist
# lists them (+0 ID, +2 styles, +3 RTF family, +4 name), in their own block;
# os_typo_info's 8 bytes in the OS part of the bottom quarter. Widths: the
# font-7 model scaled to the point size (a model, not Rosanne's fonts).
FN_TYPO = range(83, 92)
FN_META = range(95, 106)
TYPO_BANK = 0x84
TYPO_INFO_AT = 0x1E00
TYPO_FONTS = ((0x0201, 0x0F, 2, "Swiss"), (0x0101, 0x0F, 1, "Times"))
TYPO_SIZES = (6, 8, 10, 11, 12, 14, 18, 24, 36, 72)
# M15: os_typo_charscreen (93) draws one character of slot 0 on the screen.
# XAnne (M15a T4): slot 0 at 10 points draws; the model's pixel is 25/1800"
# (a reading of the T4d screenshot) and its cell is the advance wide and
# ascender + descender high. Rosanne's y is the BASELINE (owner, XAnne, M15c
# T2: text drawn at y = 40 stood above a rule at 40): the cell runs from y -
# ascender to y + descender. typo_chars records the cell's top.
FN_OS_TYPO_CHARSCREEN = 93


def typo_width(char: int, size: int, bold: bool = False) -> int:
    """The model's width of *char* in 1/1800" at *size* points."""
    base = font7_width(bytes([char if 32 <= char < 224 else 63]))
    return (base * size * 25 * (11 if bold else 10)) // 120
MEM_JUNK = 0xA5
MEM_LIST_AT = 0x0E00  # where the model OS returns os_get_mem's block list (bottom quarter)
MODEL_APP_ID = 0x0107  # os_run_program's appid_ex (docs/rosanne-research api-verification §4.3)
FN_OS_DELETE_FILE = 153  # M7
FN_OS_RENAME_FILE = 154  # M7
FILE_FNS = (FN_OS_SET_DEVICE, FN_OS_SET_CWD, FN_OS_OPEN_FILE, FN_OS_CLOSE_FILE,
            FN_OS_WRITE_FILE, FN_OS_READ_FILE, FN_OS_DELETE_FILE, FN_OS_RENAME_FILE)
BLOCK_FILL = 0xE5  # what the model's os_read_file leaves after EOF in a block
DEFAULT_MAX_STEPS = 5_000_000
JUNK_ROW = "\u00bb junk"  # a list row drawn from a slot outside the program (owner XAnne: "» A v1.12")

# Flag bits in F, in bit order S Z Y H X PV N C.
FLAG_S = 0x80
FLAG_Z = 0x40
FLAG_Y = 0x20
FLAG_H = 0x10
FLAG_X = 0x08
FLAG_PV = 0x04
FLAG_N = 0x02
FLAG_C = 0x01


class SimError(Exception):
    """An unsupported opcode or an OS function outside the M2 contract."""


class SimRunaway(Exception):
    """The program stopped without os_app_exit (HALT, or the step limit was hit)."""


class _SimIdle(Exception):
    """Internal: os_wait_event with the event script exhausted."""


def decode_dialog(mem, addr: int) -> dict:
    """Decode an os_dialog_define definition (ROSAN283 'os_dialog_define').

    Global definition (4 bytes), Box&Title (type, x,y,w,h words, NUL-ended
    title), then objects (type byte, x,y,w,h words, type-specific tail) up to
    a #00 terminator. Objects are numbered from 1 in definition order. Only
    the object types the M3a compiler may emit are accepted; anything else is
    a SimError, as is a text field over its documented maximum.
    """
    def word(at):
        return mem[at] | (mem[at + 1] << 8)

    def text(at, limit):
        end = at
        while mem[end] != 0:
            end += 1
            if end - at > limit:
                raise SimError(f"dialog text at {at:04X}h exceeds {limit} bytes")
        return bytes(mem[at:end]).decode("ascii"), end + 1

    start = addr
    focus, exit_by_click, screen_store, ddm = (mem[addr + i] for i in range(4))
    addr += 4
    box_type = mem[addr]
    box = tuple(word(addr + 1 + 2 * i) for i in range(4))
    title, addr = text(addr + 9, 255)
    objects = []
    while mem[addr] != 0:
        kind = mem[addr]
        rect = tuple(word(addr + 1 + 2 * i) for i in range(4))
        obj = {"id": len(objects) + 1, "type": kind, "rect": rect, "offset": addr - start}
        if kind == OB_BOX:
            obj["linked"] = mem[addr + 9]
            obj["params"] = tuple(mem[addr + 10 : addr + 14])
            addr += 14
        elif kind == OB_LABEL:
            obj["linked"], obj["font"], obj["align"] = mem[addr + 9], mem[addr + 10], mem[addr + 11]
            obj["text"], addr = text(addr + 12, 128)
        elif kind == OB_TEXTBUTTON:
            obj["keys"] = tuple(word(addr + 9 + 2 * i) for i in range(4))
            obj["repeat"] = mem[addr + 17]
            obj["text"], addr = text(addr + 18, 32)
        elif kind == OB_CHECKBOX:
            obj["status"] = mem[addr + 9]
            addr += 10
        elif kind == OB_RADIO:  # M6: +9 status, +10 radio (group) number 0..15
            obj["status"], obj["group"] = mem[addr + 9], mem[addr + 10]
            if obj["group"] > 15:
                raise SimError("ob_radio group number exceeds the documented 0..15")
            addr += 11
        elif kind == OB_SPINNER:  # M6: +9 reserved
            addr += 10
        elif kind == OB_LIST:  # M6 Phase 2 (ROSAN283 ob_list)
            obj["linked"] = mem[addr + 9]
            obj["ntot"], obj["nvis"], obj["first"] = word(addr + 10), word(addr + 12), word(addr + 14)
            obj["sel"], obj["font"], obj["row_h"] = word(addr + 18), mem[addr + 22], word(addr + 23)
            obj["table"] = (mem[addr + 27], word(addr + 25))
            addr += 30
        elif kind in (OB_VSCROLL, OB_HSCROLL):  # "width / height must be 17"
            if rect[2 if kind == OB_VSCROLL else 3] != 17:
                raise SimError("a scroll bar's width (vertical) or height (horizontal) must be 17")
            obj["linked"], obj["pos"], obj["size"] = mem[addr + 9], word(addr + 10), word(addr + 12)
            if kind == OB_HSCROLL and obj["linked"] != 0:
                raise SimError("ob_hscroll +9 is reserved and must be 0")
            addr += 14
        elif kind == OB_DROPBUTTON:  # "width and height must be 17"
            if rect[2:] != (17, 17):
                raise SimError("an ob_dropbutton must be 17 x 17")
            obj["linked"] = mem[addr + 9]
            obj["drop"] = tuple(word(addr + 10 + 2 * i) for i in range(4))
            obj["ntot"], obj["nvis"], obj["sel"] = word(addr + 18), word(addr + 20), word(addr + 22)
            obj["table"] = (mem[addr + 26], word(addr + 24))
            addr += 27
        elif kind == OB_TEXTEDIT:
            params = bytes(mem[addr + 9 : addr + 41])
            obj["params"] = params
            obj["font"] = params[16] | (params[17] << 8)
            obj["max_length"] = params[28] | (params[29] << 8)
            if obj["max_length"] > 128:
                raise SimError("ob_textedit max length exceeds the documented 128")
            # +21 Wd24 legal characters (address, bank), +24 length; banks
            # 0..3 select a built-in set (ROSAN283 os_text_edit)
            obj["legal_addr"] = params[21] | (params[22] << 8)
            obj["legal_bank"] = params[23]
            obj["legal_len"] = params[24]
            obj["text"], addr = text(addr + 41, 128)
        else:
            raise SimError(f"object type {kind} at {addr:04X}h is outside the M3a model")
        obj["length"] = addr - start - obj["offset"]
        objects.append(obj)
    return {
        "focus": focus,
        "exit_by_click": exit_by_click,
        "screen_store": screen_store,
        "ddm_enable": ddm,
        "box_type": box_type,
        "box": box,
        "title": title,
        "objects": objects,
        "length": addr + 1 - start,
    }


def decode_menu(mem, addr: int) -> list:
    """Decode an os_ddm_define definition (ROSAN283 'os_ddm_define').

    Per title: status (bit 7 = 1), a word, ASCII text ended by '|'. Then the
    entries: status (bit 7 = 1), hotkey word, text ended by '|', the last
    by #00; a divider is #80,'_','|' (or '_',#00 if last); a title without
    entries has a single #00. A final #00 ends the definition. Limits: 10
    titles, 20 entries per title, 2048 bytes of entry data.
    """
    start = addr
    titles = []
    while mem[addr] != 0:
        status = mem[addr]
        if not status & 0x80:
            raise SimError(f"DDM title status at {addr:04X}h lacks bit 7")
        addr += 3
        end = addr
        while mem[end] != ord("|"):
            if mem[end] == 0 or end - addr > 40:
                raise SimError(f"DDM title at {addr:04X}h is not '|'-terminated")
            end += 1
        title = bytes(mem[addr:end]).decode("ascii")
        addr = end + 1
        entries = []
        if mem[addr] == 0:
            addr += 1
        else:
            while True:
                status = mem[addr]
                if not status & 0x80:
                    raise SimError(f"DDM entry status at {addr:04X}h lacks bit 7")
                if mem[addr + 1] == ord("_") and mem[addr + 2] in (ord("|"), 0):
                    entries.append((status, 0, "_"))
                    last = mem[addr + 2] == 0
                    addr += 3
                else:
                    key = mem[addr + 1] | (mem[addr + 2] << 8)
                    addr += 3
                    end = addr
                    while mem[end] not in (ord("|"), 0):
                        if end - addr > 40:
                            raise SimError(f"DDM entry text at {addr:04X}h is too long")
                        end += 1
                    entries.append((status, key, bytes(mem[addr:end]).decode("ascii")))
                    last = mem[end] == 0
                    addr = end + 1
                if last:
                    break
        if len(entries) > 20:
            raise SimError("a DDM title has more than 20 entries")
        titles.append((title, entries))
    if len(titles) > 10:
        raise SimError("a DDM definition has more than 10 titles")
    if addr - start > 2048:
        raise SimError("a DDM definition exceeds 2048 bytes")
    return titles


class _SimStop(Exception):
    """Internal: the os_app_exit intercept; run() turns this into a normal return."""


class CPU:
    """A flat 64K Z80 model: AF BC DE HL, SP, PC, flags, memory, collected alerts."""

    def __init__(self, image: bytes, origin: int = APP_IMAGE_ORIGIN):
        self.mem = bytearray(0x10000)
        # M9: the loader maps only the first 16K of a longer file; the rest
        # is the program's to read itself (code banks).
        self.file_image = bytes(image)
        if origin == APP_IMAGE_ORIGIN and len(image) > LOADER_LIMIT:
            image = image[:LOADER_LIMIT]
        self.mem[origin : origin + len(image)] = image
        self.image_end = (origin + len(image)) & 0xFFFF
        # M9 quarter-2 model: the block mapped at #8000 and the contents of
        # every block that is not mapped there (owned blocks live in owned).
        self.q2 = Q2_START_BLOCK
        self.q2_other: dict[int, bytearray] = {Q2_START_BLOCK: bytearray(0x4000)}
        self.q2_maps: list[int] = []  # every bios_setmem2, in order
        self.q2_at_wait: list[int] = []  # the block at #8000 at every os_wait_event
        # M9 screen model: 0 white, 1 black, per pixel; every drawing call is
        # logged; texts are kept as (x, y, text, mode) and their cells drawn
        # black (a model, not Rosanne's renderer).
        self.screen = bytearray(SCREEN_W * SCREEN_H)
        self.draw_log: list[tuple] = []
        self.texts: list[tuple] = []
        self.bios_ink = 0
        self.bios_mode = 0
        self.scr_direct_refuse = False
        self.bios_sloped_lines = 0  # bios_line calls Rosanne 1.12 ignores (KI-49)
        self.scr_direct_a = POISON  # A after a successful os_scr_direct other than grey (unspecified)
        self.mouse_hidden = 0
        self.mouse_xy = (0, 0)
        self.mouse_draws_visible = 0  # BIOS drawing while the pointer was shown
        self.a = 0
        self.f = 0
        self.b = 0
        self.c = 0
        self.d = 0
        self.e = 0
        self.h = 0
        self.l = 0
        self.sp = STACK_TOP
        self.pc = APP_ENTRY_POINT
        self.steps = 0
        self.alerts: list[str] = []
        self.exited = False  # set only by the os_app_exit intercept
        self.ix = 0
        self.text_fonts: list = []  # M15: the font of each os_dialog_string, as texts
        self.iy = 0  # M7: set only by ld iy,nn
        self.mem_free: list[int] = list(MEM_POOL)  # M8: blocks os_get_mem can hand out
        self.owned: dict[int, bytearray] = {}  # M8: the program's blocks
        self.blocks_at_exit: list[int] | None = None
        self.mem_owner: dict[int, int] = {}  # M8 test hook: os_get_mem_ownerid answers
        self.mem_copy_fails = False  # M8 test hook: os_copy_24bit reports an error
        # M8 A1: True = Rosanne's os_copy_24bit as read in PCW045.SYS (carry
        # when a copy ends at the end of the owner's last block); False = the
        # earlier model, kept only for tests of logic the carry would mask
        # (KNOWN-ISSUES KI-34)
        self.copy_end_carry = True
        self.copy_carry_if = None  # M8 test hook: predicate on (C, HL, B, DE, IX) forcing a carry
        self.copy_end_errors: list[tuple] = []  # M8: copies that hit the end of the owner's last block
        self.copy_rollovers: list[tuple] = []  # M8: copies that continued into the next owned block
        # M3a dialog/event model.
        self.events: list[tuple] = []  # scripted input, consumed by os_wait_event
        self.idle = False  # os_wait_event found the script exhausted
        self.os_log: list[tuple] = []  # (fn, detail) for every OS call
        self.clock_reads: list[int] = []  # M11: bios_gettime results (seconds of the day)
        self.clock_waited = 0  # M13 corrective: model time passed by ("wait", sixteenths) events
        self.clock_tick_step = 1  # M13 corrective: the ticks byte's step (see BIOS_GETTIME)
        self.clock_by_steps = 1  # M13 corrective: 0 = only "wait" events move the clock
        # M13 responsiveness. rtc_phase (1/256 s): how far the ticks byte is
        # ahead of the seconds, as XAnne's (see BIOS_GETTIME). rosanne_timers:
        # os_set_timer timers fire by themselves, on a model of Rosanne's
        # timer service (_rosanne_timer_due). free_run_until: model time up to
        # which an exhausted script gives no-events instead of stopping.
        self.rtc_phase = 0
        self.clock_start = CLOCK_START  # M13 RT6: seconds of the day at the start (run() sets it)
        self.rosanne_timers = False
        self.timer_deadline: dict[int, tuple[int, int]] = {}  # timer -> (seconds, ticks)
        self.free_run_until: int | None = None
        # The program's TIMER handler, found from its event loop's code
        # (_find_timer_entry): its address, the model times it was entered,
        # and how many of those entries "timer" script entries have claimed.
        self.timer_entry: int | None = None
        self.timer_polled = False  # the loop runs the TIMER itself (PB_TICKPOLL)
        self.tick_times: list[int] = []
        self.ticks_claimed = 0
        self.bitmap_log: list[tuple] = []  # M12: bios_getpxl / getbitmap / plotbitmap calls
        # M12 printing: typo system, its slot 0, the open meta-page, and
        # every page sent to the printer (block, records); print_result is
        # what os_meta_print answers (0 printed; 6 "printer type not valid")
        self.typo_ready = False
        self.typo_mem = bytearray(0x4000)
        self.typo_slot: tuple | None = None
        self.typo_selected = 0
        self.typo_chars: list = []  # M15: (x, y, char, style, mode, (id, size)) of each os_typo_charscreen
        self.meta: dict | None = None
        self.printed: list[dict] = []
        self.print_result = 0
        self.meta_open_result = 0
        self.dialog: dict | None = None  # decoded os_dialog_define definition
        self.dialog_shown = False
        self.fail_dialog_define = False
        self.event_pending = False  # an event record is live at EVENT_RECORD
        # M3b: the OS-owned copy of the dialog. Each object has a fixed slot
        # sized by the definition passed to os_dialog_define; os_object_define
        # may not exceed it ("N.B. Must not be longer than existing
        # definition"). shown[obj] is what is on screen: it changes at
        # os_dialog_display and os_object_update only.
        self.os_mem = bytearray(0x4000)
        self.slots: dict[int, tuple[int, int, int]] = {}  # obj -> (addr, length, type)
        self.shown: dict[int, bytes] = {}
        # Display model for text edits (hypothesis H-PAINT, M3b fix): the
        # glyphs on screen per ob_textedit. ROSAN283 does not say whether a
        # text edit paints its own background; the Amstrad macros put an
        # "OBLIGATORY" ob_box behind every one (NIKMACRO.Z80 textentry64),
        # and XAnne showed os_object_update of a bare edit leaving the old
        # text visible. So: os_object_update(textedit) draws the new glyphs
        # over the old (new + old[len(new):]); os_object_update(box) clears
        # every text edit lying inside it; os_dialog_display and the OS's
        # own editing draw the true text. A model of an observation, not of
        # Rosanne's renderer — XAnne remains the evidence.
        self.painted: dict[int, str] = {}
        # M5d repair: labels drawn wider than their object (see
        # _check_label_width): (object, text, model width, object width).
        self.label_overflows: list[tuple[int, str, int, int]] = []
        self.pending_edit: tuple[int, str] | None = None
        self.pending_spin: int | None = None
        self.stale_b: int | None = None
        # M4: the filing functions act on an in-memory Disk (never on host
        # files, so a test cannot touch real data).
        self.disk = Disk()
        # M6 Phase 1 models. Rosanne behaviours UIPROBE settles are options:
        # radio_mode "exclusive" (the OS clears the other radios of the group)
        # or "set" (it only sets the clicked one); menu_autotick: the OS
        # toggles a tickable entry's tick when it is selected.
        self.radio_mode = "set"
        self.menu_autotick = False
        self.timers: dict[int, tuple[int, int]] = {}  # timer -> (repeat, interval)
        # M13: keys held down (PS/2 set-2 scan codes, bios_keystate's table),
        # changed by ("hold", code, True / False) entries of the event script
        self.keys_down: set[int] = set()
        self.keystate_reads: list[int] = []
        self.menu: list | None = None  # [(title, [(status, hotkey, text)])]
        self.menu_shown = False
        self.hotkey_log: list = []  # M13 corrective: ("type") keys the hotkey search took
        self.beeps = 0
        self.alert_answers: list[int] = []  # button chosen for each multi-button alert
        self.alert_buttons: list[list[str]] = []  # captions of every alert, in order
        self.last_b = None  # B returned by os_process_event (spinner)
        # M6 Phase 2: the scripted list / drop-down / scroll-bar action that
        # os_process_event applies; drop_writes_label: whether the OS writes
        # a drop-down's readout label itself (UIPROBE2 settles it).
        self.pending_phase2 = None
        self.drop_writes_label = False
        self.list_rows: dict[int, tuple[list[str], int | None]] = {}
        # Optional write observer (M2.1 memory-boundary checks,
        # tests/memguard.py): called as on_write(cpu, addr, value) before
        # every memory write, with the old contents still in place.
        self.on_write = None
        self._build_dispatch()  # M11: step()'s opcode table

    # ------------------------------------------------------- register pairs
    @property
    def bc(self) -> int:
        return (self.b << 8) | self.c

    def set_bc(self, value: int) -> None:
        self.b, self.c = (value >> 8) & 0xFF, value & 0xFF

    @property
    def de(self) -> int:
        return (self.d << 8) | self.e

    def set_de(self, value: int) -> None:
        self.d, self.e = (value >> 8) & 0xFF, value & 0xFF

    @property
    def hl(self) -> int:
        return (self.h << 8) | self.l

    def set_hl(self, value: int) -> None:
        self.h, self.l = (value >> 8) & 0xFF, value & 0xFF

    # ------------------------------------------------------------- memory
    def _rb(self, addr: int) -> int:
        return self.mem[addr & 0xFFFF]

    def _rw(self, addr: int) -> int:
        return self._rb(addr) | (self._rb(addr + 1) << 8)

    def _wb(self, addr: int, value: int) -> None:
        if self.on_write is not None:
            self.on_write(self, addr & 0xFFFF, value & 0xFF)
        self.mem[addr & 0xFFFF] = value & 0xFF

    def _wb_block(self, addr: int, data: bytes) -> None:
        """M11: _wb for each byte of *data* at addr, addr + 1, ... in order
        (the observer sees each write before it, as with _wb)."""
        mem, observe = self.mem, self.on_write
        for i, value in enumerate(data):
            at = (addr + i) & 0xFFFF
            if observe is not None:
                observe(self, at, value)
            mem[at] = value

    def _ww(self, addr: int, value: int) -> None:
        self._wb(addr, value)
        self._wb(addr + 1, value >> 8)

    def _fetch8(self) -> int:
        value = self._rb(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def _fetch16(self) -> int:
        return self._fetch8() | (self._fetch8() << 8)

    def _fetch_rel(self) -> int:
        value = self._fetch8()
        return value - 0x100 if value & 0x80 else value

    def _push16(self, value: int) -> None:
        self.sp = (self.sp - 2) & 0xFFFF
        self._ww(self.sp, value)

    def _pop16(self) -> int:
        value = self._rw(self.sp)
        self.sp = (self.sp + 2) & 0xFFFF
        return value

    # ------------------------------------------------- 8-bit register file
    # Index order is B C D E H L (HL) A; index 6 accesses memory at HL.
    def _get_r(self, idx: int) -> int:
        if idx == 6:
            return self._rb(self.hl)
        return (self.b, self.c, self.d, self.e, self.h, self.l, 0, self.a)[idx]

    def _set_r(self, idx: int, value: int) -> None:
        value &= 0xFF
        if idx == 6:
            self._wb(self.hl, value)
        elif idx == 7:
            self.a = value
        elif idx == 0:
            self.b = value
        elif idx == 1:
            self.c = value
        elif idx == 2:
            self.d = value
        elif idx == 3:
            self.e = value
        elif idx == 4:
            self.h = value
        else:
            self.l = value

    # ------------------------------------------------------- 16-bit pairs
    # Index order is BC DE HL SP.
    def _get_rr(self, idx: int) -> int:
        return (self.bc, self.de, self.hl, self.sp)[idx]

    def _set_rr(self, idx: int, value: int) -> None:
        value &= 0xFFFF
        if idx == 0:
            self.set_bc(value)
        elif idx == 1:
            self.set_de(value)
        elif idx == 2:
            self.set_hl(value)
        else:
            self.sp = value

    def _get_rr_stack(self, idx: int) -> int:
        # PUSH/POP use pair 3 as AF, not SP.
        return (self.a << 8) | self.f if idx == 3 else self._get_rr(idx)

    def _set_rr_stack(self, idx: int, value: int) -> None:
        if idx == 3:
            self.a, self.f = (value >> 8) & 0xFF, value & 0xFF
        else:
            self._set_rr(idx, value)

    # -------------------------------------------------------------- flags
    @staticmethod
    def _parity(value: int) -> int:
        """Even parity flag value: PV set when the byte has an even bit count."""
        return FLAG_PV if bin(value & 0xFF).count("1") % 2 == 0 else 0

    def _flags_add(self, a: int, b: int, result: int, total: int) -> None:
        self.f = (
            (FLAG_C if total > 0xFF else 0)
            | (FLAG_H if (a ^ b ^ result) & 0x10 else 0)
            | (FLAG_PV if ((a ^ result) & (b ^ result)) & 0x80 else 0)
            | (FLAG_S if result & 0x80 else 0)
            | (FLAG_Z if result == 0 else 0)
            | (result & (FLAG_Y | FLAG_X))
        )

    def _flags_sub(self, a: int, b: int, result: int, total: int) -> None:
        self.f = (
            FLAG_N
            | (FLAG_C if total < 0 else 0)
            | (FLAG_H if (a ^ b ^ result) & 0x10 else 0)
            | (FLAG_PV if ((a ^ b) & (a ^ result)) & 0x80 else 0)
            | (FLAG_S if result & 0x80 else 0)
            | (FLAG_Z if result == 0 else 0)
            | (result & (FLAG_Y | FLAG_X))
        )

    def _flags_logic(self, result: int, half: int) -> None:
        self.f = (
            (FLAG_H if half else 0)
            | (FLAG_S if result & 0x80 else 0)
            | (FLAG_Z if result == 0 else 0)
            | (result & (FLAG_Y | FLAG_X))
            | self._parity(result)
        )

    def _inc8(self, value: int) -> int:
        result = (value + 1) & 0xFF
        self.f = (
            (self.f & FLAG_C)
            | (FLAG_S if result & 0x80 else 0)
            | (FLAG_Z if result == 0 else 0)
            | (FLAG_H if result & 0x0F == 0 else 0)
            | (FLAG_PV if value == 0x7F else 0)
            | (result & (FLAG_Y | FLAG_X))
        )
        return result

    def _dec8(self, value: int) -> int:
        result = (value - 1) & 0xFF
        self.f = (
            (self.f & FLAG_C)
            | FLAG_N
            | (FLAG_S if result & 0x80 else 0)
            | (FLAG_Z if result == 0 else 0)
            | (FLAG_H if result & 0x0F == 0x0F else 0)
            | (FLAG_PV if value == 0x80 else 0)
            | (result & (FLAG_Y | FLAG_X))
        )
        return result

    def _cond(self, cc: int) -> bool:
        """Test a condition code 0..7 in the order NZ Z NC C PO PE P M."""
        if cc == 0:
            return not (self.f & FLAG_Z)
        if cc == 1:
            return bool(self.f & FLAG_Z)
        if cc == 2:
            return not (self.f & FLAG_C)
        if cc == 3:
            return bool(self.f & FLAG_C)
        if cc == 4:
            return not (self.f & FLAG_PV)
        if cc == 5:
            return bool(self.f & FLAG_PV)
        if cc == 6:
            return not (self.f & FLAG_S)
        return bool(self.f & FLAG_S)

    # ---------------------------------------------------------------- alu
    def _alu(self, group: int, operand: int) -> None:
        """ADD ADC SUB SBC AND XOR OR CP; group is (opcode >> 3) & 7."""
        a = self.a
        carry = 1 if self.f & FLAG_C else 0
        if group == 0:  # add
            result = (a + operand) & 0xFF
            self._flags_add(a, operand, result, a + operand)
            self.a = result
        elif group == 1:  # adc
            result = (a + operand + carry) & 0xFF
            self._flags_add(a, operand, result, a + operand + carry)
            self.a = result
        elif group == 2:  # sub
            result = (a - operand) & 0xFF
            self._flags_sub(a, operand, result, a - operand)
            self.a = result
        elif group == 3:  # sbc
            result = (a - operand - carry) & 0xFF
            self._flags_sub(a, operand, result, a - operand - carry)
            self.a = result
        elif group == 4:  # and
            self.a = a & operand
            self._flags_logic(self.a, 1)
        elif group == 5:  # xor
            self.a = a ^ operand
            self._flags_logic(self.a, 0)
        elif group == 6:  # or
            self.a = a | operand
            self._flags_logic(self.a, 0)
        else:  # cp: flags from the subtraction, A unchanged
            result = (a - operand) & 0xFF
            self._flags_sub(a, operand, result, a - operand)

    # ------------------------------------------------------------ control
    def _call(self, target: int) -> None:
        if target == OS_DISPATCH:
            self._os_call()  # raises _SimStop or emulates the ret in place
            return
        if target == BIOS_GETMEM1:
            self.a = FAKE_APP_BANK  # flags preserved; the ret leaves PC alone
            return
        if target in BIOS_GRAPHICS:  # M9
            self._bios_graphics(target)
            return
        if target in (BIOS_GETPXL, BIOS_PLOTBITMAP, BIOS_GETBITMAP, BIOS_PLOTMASKED):  # M12; M13
            self._bios_bitmap(target)
            return
        if target == BIOS_KEYSTATE:  # M13 [static: PCW045.SYS #0D97]
            code = self.a
            self.keystate_reads.append(code)
            if code < 128:  # a byte of the key table: 0 up, non-0 down
                self.a = 0xFF if code in self.keys_down else 0
            self.f = POISON
            return
        if target == BIOS_GETTIME:  # M11 corrective
            # M13 corrective: plus the time ("wait") events let pass with no
            # instructions run; clock_tick_step > 1 makes the ticks byte
            # coarse (it moves in steps of that many 1/256 s), a model of a
            # clock whose sub-second part is not a fine counter
            secs, self.e = self.rtc()
            self.d = secs % 60
            self.c = secs // 60 % 60
            self.b = secs // 3600
            self.f = POISON
            self.clock_reads.append(secs)
            return
        if target == BIOS_GETMEM2:  # M9
            self.a = self.q2
            return
        if target == BIOS_SETMEM2:  # M9
            self._map_q2(self.a)
            return
        self._push16(self.pc)
        self.pc = target

    def _poison(self, *regs: str) -> None:
        """Overwrite documented-corrupt registers with junk."""
        for reg in regs:
            if reg == "ix":
                self.ix = (POISON << 8) | POISON
            else:
                setattr(self, reg, POISON)

    def _os_call(self) -> None:
        """Dispatch call 003Bh over the modelled OS subset."""
        fn = self.a
        if fn == FN_OS_APP_EXIT:
            self.os_log.append((fn, None))
            self.exited = True
            # "os_app_exit automatically closes any opened read and/or write
            # files": record what was still open so tests can insist on none.
            self.disk.open_at_exit = (self.disk.open_read, self.disk.open_write)
            self.blocks_at_exit = sorted(self.owned)  # M8: still held at exit
            raise _SimStop()
        if fn in FILE_FNS:
            self._file_call(fn)
            return
        if fn in MEM_FNS:
            self._mem_call(fn)
            return
        if fn in CANVAS_FNS:  # M9
            self._canvas_call(fn)
            return
        if fn in FN_TYPO or fn in FN_META:  # M12 printing
            self._print_call(fn)
            return
        if fn == FN_OS_TYPO_CHARSCREEN:  # M15 screen typography
            self._typo_screen()
            return
        if fn == FN_OS_ALERT:
            # out: NC, A = button; "BC, DE, HL, IX, IY corrupt"
            self.os_log.append((fn, None))
            self.alerts.append(self._alert_text())
            buttons = self._alert_buttons()
            self.alert_buttons.append(buttons)
            answer = 0
            if len(buttons) > 1 and self.alert_answers:
                answer = self.alert_answers.pop(0)
                if not 0 <= answer < len(buttons):
                    raise SimError(f"scripted alert answer {answer} for {len(buttons)} buttons")
            self._poison("b", "c", "d", "e", "h", "l", "ix")
            self.a = answer
            self.f &= ~FLAG_C  # NC: alert acknowledged, as the POC runtime expects
            return
        if fn == FN_OS_DIALOG_DEFINE:
            # in: C,HL = 24-bit address; out: C error / NC OK;
            # "AF, BC, DE, HL, IX, IY corrupt"
            if self.c != FAKE_APP_BANK or not 0x4000 <= self.hl < 0x8000:
                raise SimError(
                    f"os_dialog_define with C={self.c:02X}h HL={self.hl:04X}h: "
                    "the definition must be addressed in the app bank #4000-#7FFF"
                )
            self.dialog = decode_dialog(self.mem, self.hl)
            self._copy_dialog(self.hl)
            self.os_log.append((fn, self.hl))
            failed = self.fail_dialog_define
            self._poison("a", "b", "c", "d", "e", "h", "l", "ix")
            self.f = FLAG_C if failed else 0
            if failed:
                self.dialog = None
            return
        if fn == FN_OS_DIALOG_DISPLAY:
            ok = self.dialog is not None and not self.dialog_shown
            self.dialog_shown = self.dialog_shown or ok
            if ok:
                self.shown = {n: self._slot_bytes(n) for n in self.slots}
                for n, (_, _, t) in self.slots.items():
                    if t == OB_LIST:
                        self._list_draw(n, full=True)
                    elif t == OB_DROPBUTTON:
                        self._drop_readout(n)
                self.painted = {
                    n: self._slot_text(n)
                    for n, (_, _, t) in self.slots.items()
                    if t in (OB_TEXTEDIT, OB_LABEL)
                }
                for n, (_, _, t) in self.slots.items():
                    if t == OB_LABEL:
                        self._check_label_width(n)
            self.os_log.append((fn, None))
            self._poison("a", "b", "c", "d", "e", "h", "l", "ix")
            self.f = 0 if ok else FLAG_C
            return
        if fn == FN_OS_DIALOG_REMOVE:
            ok = self.dialog_shown
            self.dialog_shown = False
            self.os_log.append((fn, None))
            self._poison("a", "b", "c", "d", "e", "h", "l", "ix")
            self.f = 0 if ok else FLAG_C
            return
        if fn == FN_OS_SET_FOCUS:
            self.os_log.append((fn, self.e))
            self._poison("a", "b", "c", "d", "e", "h", "l", "ix")
            self.f = 0
            return
        if fn == FN_OS_WAIT_EVENT:
            self._wait_event()
            return
        if fn == FN_OS_GET_EVENT:  # M13 RT6: the polling call
            self._wait_event(blocking=False)
            return
        if fn == FN_OS_PROCESS_EVENT:
            if not self.event_pending or self.ix != EVENT_RECORD:
                raise SimError(
                    f"os_process_event with IX={self.ix:04X}h: IX must be the event "
                    "record just returned by os_wait_event (ROSAN283 'N.B.!')"
                )
            record = bytes(self.mem[EVENT_RECORD : EVENT_RECORD + 12])
            self.os_log.append((fn, record))
            spin = None
            if record[2] == OM_OBJEVENT and record[5] in (OBEV_CLICK, OBEV_FOCFIRE) \
                    and self.stale_b is None:
                spin = self._apply_control_click(record[3])
            scroll = self._apply_phase2_event(record[3]) if record[2] == OM_OBJEVENT else None
            self._poison("a", "b", "c", "d", "e", "h", "l", "ix")
            if scroll is not None:
                self.b = scroll[0]  # scroll bars: B = 1..5, DE = new handle position
                self.set_de(scroll[1])
            elif spin is not None:
                self.b = spin  # ob_spinner: B = 1 up / 5 down (ROSAN283)
            elif self.stale_b is not None:
                self.b = self.stale_b
            self.stale_b = None
            self.f = 0
            return
        if fn == FN_OS_OBJECT_DEFINE:
            self._object_define()
            return
        if fn == FN_OS_OBJECT_GET_DEFINE:
            # out: C error / NC CHL = definition; "AF, B, DE, IX, IY corrupt"
            number = self.e
            self.os_log.append((fn, number))
            self._poison("a", "b", "d", "e", "ix")
            if number not in self.slots:
                self.f = FLAG_C
                return
            self.c = OS_BANK
            self.set_hl(self.slots[number][0])
            self.f = 0
            return
        if fn in (FN_OS_OBJECT_UPDATE, FN_OS_OBJECT_DISPLAY):
            number = self.e
            self.os_log.append((fn, number))
            ok = number in self.slots
            if ok:
                self.shown[number] = self._slot_bytes(number)
                if self.slots[number][2] == OB_LIST:
                    self._list_draw(number, full=fn == FN_OS_OBJECT_DISPLAY)
                elif self.slots[number][2] == OB_DROPBUTTON:
                    self._drop_readout(number)
                else:
                    self._paint_update(number)
            self._poison("a", "b", "c", "d", "e", "h", "l", "ix")
            self.f = 0 if ok else FLAG_C
            return
        if fn == FN_OS_DIALOG_STRING_WIDTH:
            # XAnne evidence (owner, WIDTHDG.PRG): carry set with A=#07 in
            # every test (block in the app image or at #2200, with or
            # without a dialog), and HL = the width (110 for ten W's, 172 for
            # "Label tests: long, short, empty", exactly Rosanne's font-7
            # advances: docs/M11-CORRECTIVE.md). The model returns that: HL =
            # font7_width of the block's text, carry set, A = #07.
            text = bytearray()
            addr = self.hl
            while len(text) < 256:
                byte = self._read24(self.c, (addr + 8 + len(text)) & 0xFFFF)
                if byte == 0:
                    break
                text.append(byte)
            font = self._read24(self.c, addr)
            if not 1 <= font <= 12:
                raise SimError(f"os_dialog_string_width: font {font} is not 1..12")
            self.os_log.append((fn, bytes(text)))
            self.set_hl(dialog_font_width(bytes(text), font))
            self.a = 0x07
            self.f = FLAG_C
            return
        if fn == FN_OS_GET_BYTE_24BIT:
            # in: C,HL, B wind-on flag; out: E byte, C,HL wound on; A corrupt
            # (B, D unspecified -> treated as corrupt).
            self.e = self._read24(self.c, self.hl)
            if self.b == 1:
                self.set_hl(self.hl + 1)
            elif self.b != 0:
                raise SimError("os_get_byte_24bit wind-on flag must be 0 or 1")
            self.os_log.append((fn, None))
            self._poison("a", "b", "d")
            return
        if fn == FN_OS_ADD_24BIT:
            # in: C,HL + BDE; out: NC/C, C,HL updated; A corrupt.
            total = (self.hl & 0x3FFF) + ((self.b << 16) | self.de)
            self.os_log.append((fn, None))
            if total > 0x3FFF:
                raise SimError("os_add_24bit crossing a block: outside the model")
            self.set_hl((self.hl & 0xC000) | total)
            self._poison("a", "b", "d", "e")
            self.f = 0
            return
        if fn in (FN_OS_SET_TIMER, FN_OS_KILL_TIMER, FN_OS_DDM_DEFINE, FN_OS_DDM_DISPLAY,
                  FN_OS_DDM_GET_TASKS, FN_OS_DDM_GET_ENTRY_STATUS, FN_OS_DDM_PUT_ENTRY_STATUS,
                  FN_OS_BEEP, FN_OS_FLUSH_EVENTS):
            self._phase1_call(fn)
            return
        raise SimError(f"call 003Bh with A={fn}: not in the simulated OS subset")

    # ----------------------------------------------- M6 Phase 1 OS functions
    def _phase1_call(self, fn: int) -> None:
        if fn == FN_OS_FLUSH_EVENTS:
            # "flush all pending events from the OS event pipe; out: AF, HL
            # corrupt". Scripted events marked "queued" model input that
            # arrived while the program was busy: they are in the pipe.
            while self.events and self.events[0][-1] == "queued":
                self.events.pop(0)
            self.os_log.append((fn, None))
            self._poison("a", "h", "l")
            return
        if fn == FN_OS_BEEP:  # "in: none; out: none; AF corrupt"
            self.beeps += 1
            self.os_log.append((fn, None))
            self._poison("a")
            return
        if fn == FN_OS_SET_TIMER:
            # in: C,HL = Timer Record (bytes 2..5: timer 0..3, repeat 0/1,
            # interval in 1/16 s 0..57599); out: NC/C
            rec = [self._read24(self.c, self.hl + i) for i in range(6)]
            timer, repeat = rec[2], rec[3]
            interval = rec[4] | (rec[5] << 8)
            self.os_log.append((fn, (timer, repeat, interval)))
            ok = timer <= 3 and repeat in (0, 1) and interval <= 57599
            if ok:
                self.timers[timer] = (repeat, interval)
                if self.rosanne_timers:
                    self._rosanne_arm(timer, interval)
            self._poison("a")
            self.f = 0 if ok else FLAG_C
            return
        if fn == FN_OS_KILL_TIMER:  # in: E = timer 0..3; out: NC/C
            self.os_log.append((fn, self.e))
            ok = self.e <= 3
            self.timers.pop(self.e, None)
            self.timer_deadline.pop(self.e, None)
            self._poison("a")
            self.f = 0 if ok else FLAG_C
            return
        if fn == FN_OS_DDM_GET_TASKS:
            # in: C,HL = buffer; out: HL = next byte after the Tasks list
            if self.c != LOW_BANK or not 0x2000 <= self.hl < 0x3000:
                raise SimError("os_ddm_get_tasks: the runtime keeps menus in the #2000-#2FFF workspace")
            start = self.hl
            for i, byte in enumerate(MODEL_TASKS_MENU):
                if self.on_write is not None:
                    self.on_write(self, start + i, byte)
                self.mem[start + i] = byte
            self.os_log.append((fn, start))
            self._poison("a", "b", "d", "e")
            self.set_hl(start + len(MODEL_TASKS_MENU))
            return
        if fn == FN_OS_DDM_DEFINE:
            if self.c != LOW_BANK or not 0x2000 <= self.hl < 0x3000:
                raise SimError("os_ddm_define: the runtime keeps menus in the #2000-#2FFF workspace")
            self.menu = decode_menu(self.mem, self.hl)
            self.os_log.append((fn, self.b))
            self._poison("a", "b", "c", "d", "e", "h", "l", "ix")
            return
        if fn == FN_OS_DDM_DISPLAY:
            if self.menu is None:
                raise SimError("os_ddm_display before os_ddm_define")
            self.menu_shown = True
            self.os_log.append((fn, None))
            self._poison("a", "b", "c", "d", "e", "h", "l", "ix")
            return
        if fn in (FN_OS_DDM_GET_ENTRY_STATUS, FN_OS_DDM_PUT_ENTRY_STATUS):
            title, entry = self.c, self.b
            ok = self.menu is not None and title < len(self.menu) and entry < self._menu_count(title)
            self.os_log.append((fn, (title, entry, self.e)))  # Rosanne's numbering
            if ok:
                entry = self._menu_index(title, entry)
            if ok and fn == FN_OS_DDM_PUT_ENTRY_STATUS:
                if not self.e & 0x80:
                    raise SimError("DDM entry status bit 7 must always be 1")
                st, key, text = self.menu[title][1][entry]
                self.menu[title][1][entry] = (self.e, key, text)
            elif ok:
                self.a = self.menu[title][1][entry][0]
            self._poison("b", "c")
            self.f = 0 if ok else FLAG_C
            return
        raise AssertionError(fn)

    def _menu_count(self, title: int) -> int:
        return sum(1 for e in self.menu[title][1] if e[2] != "_")

    def _menu_index(self, title: int, number: int) -> int:
        """Position in the decoded list of entry *number*: Rosanne does not
        number divider lines (owner XAnne, UIPROBE P1)."""
        seen = -1
        for i, e in enumerate(self.menu[title][1]):
            if e[2] != "_":
                seen += 1
                if seen == number:
                    return i
        raise SimError(f"menu {title} has no entry {number}")

    def menu_entry(self, title: int, entry: int) -> tuple[int, int, str]:
        """(status, hotkey word, text) of entry *entry* (dividers unnumbered)."""
        return self.menu[title][1][self._menu_index(title, entry)]

    def _alert_buttons(self) -> list[str]:
        """Captions of the os_alert definition at HL (ROSAN283 'os_alert')."""
        data = bytes(self.mem[self.hl : min(self.hl + self.de, 0x10000)])
        end = data.find(b"\x00\x00")
        if end == -1:
            raise SimError("os_alert definition has no end of text")
        at = end + 2
        count = data[at]
        at += 1
        captions = []
        for _ in range(count):
            at += 8  # 4 keycode words
            stop = data.index(0, at)
            captions.append(data[at:stop].decode("ascii"))
            at = stop + 1
        if at != len(data):
            raise SimError(f"os_alert length {len(data)} does not match its content ({at})")
        return captions

    # --------------------------------------------------- M4 filing functions
    def _low_string(self, addr: int, limit: int, what: str) -> str:
        """A 0-terminated argument that ROSAN283 requires "in bottom quarter
        of memory"."""
        if not 0 <= addr < 0x4000:
            raise SimError(f"{what} at {addr:04X}h is not in the bottom quarter (ROSAN283)")
        end = addr
        while self.mem[end] != 0:
            end += 1
            if end - addr > limit:
                raise SimError(f"{what} at {addr:04X}h has no NUL within {limit} bytes")
        return bytes(self.mem[addr:end]).decode("latin-1")

    def _app_range(self, length: int, what: str) -> int:
        """Check a 24-bit CHL buffer of *length* bytes lies in the app bank."""
        if self.c != FAKE_APP_BANK or not 0x4000 <= self.hl < 0x8000:
            raise SimError(f"{what} at C={self.c:02X}h HL={self.hl:04X}h is not in the app bank")
        if self.hl + length > 0x8000:
            raise SimError(f"{what} of {length} bytes crosses the end of the 16K block")
        return self.hl

    def _file_fail(self, code: int) -> None:
        self._poison("b", "c", "d", "e", "h", "l", "ix")
        self.a = code
        self.f = FLAG_C

    def _file_ok(self, *keep: str) -> None:
        self._poison(*[r for r in ("a", "b", "c", "d", "e", "h", "l", "ix") if r not in keep])
        self.f = 0

    def _file_call(self, fn: int) -> None:
        """The filing functions (ROSAN283 "THE FILING FUNCTIONS"); "all
        registers which are not specified on exit are assumed corrupted"."""
        disk = self.disk
        fault = disk.faults.get(fn)
        disk.calls[fn] = disk.calls.get(fn, 0) + 1  # M9: faults_from counts calls
        if fn in disk.faults_from and disk.calls[fn] >= disk.faults_from[fn][0]:
            fault = disk.faults_from[fn][1]
        if disk.calls[fn] in disk.faults_at.get(fn, {}):  # M10: exactly the n-th call fails
            fault = disk.faults_at[fn][disk.calls[fn]]
        if fn == FN_OS_SET_DEVICE:
            self.os_log.append((fn, self.b))
            if self.b not in (1, 2) or fault is not None:
                self._file_fail(POISON)  # "C ... Invalid device number"; A unspecified
                return
            disk.device = self.b
            self._file_ok()
            return
        if fn == FN_OS_SET_CWD:
            hl = self.hl
            path = self._low_string(hl, 128, "os_set_cwd path")
            self.os_log.append((fn, path))
            if disk.device != 1:
                raise SimError("os_set_cwd is 'DOS-compatible floppy only': set device 1 first")
            if not path.startswith("\\"):
                raise SimError(f"relative os_set_cwd path {path!r} is outside the model")
            norm = path.upper()
            code = fault
            if code is None and len(norm) > 64:
                code = 0xBA
            elif code is None and norm not in disk.folders:
                code = 0x03
            if code is not None:
                self._file_fail(code)
                self.set_hl(hl)  # "HL still points to buffer with original input path"
                return
            disk.cwd = norm
            for i, ch in enumerate(norm.encode("latin-1") + b"\0"):  # the OS writes the new path back
                self._wb(hl + i, ch)
            self._file_ok("h", "l")
            self.set_hl(hl)
            return
        if fn == FN_OS_OPEN_FILE:
            stem = self._low_string(self.hl, 8, "os_open_file name")
            ext = "" if self.de == 0 else self._low_string(self.de, 4, "os_open_file extension")
            mode = self.b
            key = (disk.cwd, (stem + ext).upper())
            self.os_log.append((fn, (key[1], mode)))
            if disk.device is None:
                raise SimError("os_open_file before os_set_device")
            if mode not in (0, 1):
                raise SimError(f"os_open_file access mode {mode}")
            if fault is not None:
                self._file_fail(fault)
                return
            if mode == 0:
                if disk.open_read is not None:
                    self._file_fail(0x04)
                elif key not in disk.files:
                    self._file_fail(0x02)
                else:
                    disk.open_read = [key, 0]
                    self._file_ok()
                return
            if disk.open_write is not None:
                self._file_fail(0x04)
                return
            # Hypothesis H-TRUNC (not stated by ROSAN283): opening for write
            # creates the file or truncates an existing one. truncate_on_open
            # = False models the alternative (overwrite in place).
            if disk.truncate_on_open or key not in disk.files:
                disk.files[key] = b""
            disk.open_write = [key, 0]
            self._file_ok()
            return
        if fn == FN_OS_CLOSE_FILE:
            mode = self.b
            self.os_log.append((fn, mode))
            slot = "open_read" if mode == 0 else "open_write"
            if mode not in (0, 1):
                raise SimError(f"os_close_file access mode {mode}")
            if getattr(disk, slot) is None:
                self._file_fail(0x02)
                return
            setattr(disk, slot, None)
            if fault is not None:
                self._file_fail(fault)
                return
            self._file_ok()
            return
        if fn == FN_OS_WRITE_FILE:
            length = (self.b << 16) | self.de
            self.os_log.append((fn, length))
            if self.c in self.owned:  # M9: TEXT SAVE writes from the program's blocks
                if self.hl + length > 0x4000:
                    raise SimError(f"os_write_file of {length} bytes from {self.c:02X}:{self.hl:04X}h "
                                   "crosses the end of the block")
                data = bytes(self._read24(self.c, self.hl + i) for i in range(length))
            else:
                src = self._app_range(length, "os_write_file source")
                data = bytes(self.mem[src : src + length])
            if disk.open_write is None:
                self._file_fail(0x02)
                return
            if fault is not None:
                self._file_fail(fault)  # e.g. #A3 Disk Full: "no data has been written"
                return
            key, pos = disk.open_write
            old = disk.files[key]
            disk.files[key] = old[:pos] + data + old[pos + length:]
            disk.open_write[1] = pos + length
            self._file_ok()
            return
        if fn == FN_OS_READ_FILE:
            length = (self.b << 16) | self.de
            self.os_log.append((fn, length))
            if disk.open_read is None:
                self._file_fail(0x02)
                return
            key, pos = disk.open_read
            content = disk.files[key]
            n = max(0, min(length, len(content) - pos))
            # "there must be enough space at CHL to allow RAM to be filled up
            # with the remainder of the last 512-/510-byte block read": the
            # model fills with junk after the data, to the larger of the two
            # readings — the end of the file's 512-byte block, or 512-byte
            # rounding of the request itself (worst case; M4 repair).
            by_position = (-(-(pos + n) // 512) * 512 - pos) if n else 0
            by_request = -(-max(n, 1) // 512) * 512
            span = max(by_position, by_request)
            data = content[pos:pos + span]
            data += bytes([BLOCK_FILL]) * (span - len(data))
            if self.c in self.owned:  # M9: straight into one of the program's blocks
                if self.hl + max(span, length) > 0x4000:
                    raise SimError(f"os_read_file of {length} bytes to {self.c:02X}h:{self.hl:04X}h "
                                   "would fill past the end of the 16K block")
                if fault is not None:
                    self._file_fail(fault)
                    return
                base, blk = self.hl, self.c
                for i, v in enumerate(data):
                    self._write24(blk, base + i, v)
            else:
                dst = self._app_range(max(span, length), "os_read_file destination")
                if fault is not None:
                    self._file_fail(fault)
                    return
                self._wb_block(dst, data)
            disk.open_read[1] = pos + n
            if n == length:
                self._file_ok()
                return
            self._poison("b", "c", "d", "e", "h", "l", "ix")
            self.a = 0xA1  # Premature EoF
            if disk.eof_registers == "documented":
                # ROSAN283: "BDE = amount NOT loaded, CHL = filesize"
                missing, size = length - n, len(content)
                self.b, self.d, self.e = (missing >> 16) & 0xFF, (missing >> 8) & 0xFF, missing & 0xFF
                self.c, self.h, self.l = (size >> 16) & 0xFF, (size >> 8) & 0xFF, size & 0xFF
            self.f = FLAG_C
            return
        if fn in (FN_OS_DELETE_FILE, FN_OS_RENAME_FILE):
            # M7 (ROSAN283): delete: HL name, DE extension; rename: also IX
            # new name, IY new extension, B = #00 file. Model rules, not
            # XAnne-verified: an open file cannot be deleted or renamed
            # (#05), a rename onto an existing name is #50.
            stem = self._low_string(self.hl, 8, "file name")
            ext = "" if self.de == 0 else self._low_string(self.de, 4, "file extension")
            key = (disk.cwd, (stem + ext).upper())
            if fn == FN_OS_RENAME_FILE:
                if self.b != 0:
                    raise SimError("os_rename_file B must be #00 (rename a file)")
                new = (disk.cwd, (self._low_string(self.ix, 8, "new name")
                                  + self._low_string(self.iy, 4, "new extension")).upper())
            self.os_log.append((fn, (key[1], new[1]) if fn == FN_OS_RENAME_FILE else key[1]))
            open_keys = {slot[0] for slot in (disk.open_read, disk.open_write) if slot}
            if fault is not None:
                self._file_fail(fault)
            elif key not in disk.files:
                self._file_fail(0x02)
            elif key in open_keys:
                self._file_fail(0x05)
            elif fn == FN_OS_DELETE_FILE:
                del disk.files[key]
                self._file_ok()
            elif new in disk.files:
                self._file_fail(0x50)
            else:
                disk.files[new] = disk.files.pop(key)
                self._file_ok()
            return
        raise AssertionError(fn)

    # --------------------------------------------------- M3b OS dialog copy
    def _copy_dialog(self, addr: int) -> None:
        self.os_mem = bytearray(0x4000)
        length = self.dialog["length"]
        self.os_mem[OS_COPY_BASE : OS_COPY_BASE + length] = self.mem[addr : addr + length]
        self.slots = {
            o["id"]: (OS_COPY_BASE + o["offset"], o["length"], o["type"])
            for o in self.dialog["objects"]
        }
        self.shown = {}
        self.painted = {}

    def _slot_text(self, number: int) -> str:
        offset = LABEL_TEXT if self.slots[number][2] == OB_LABEL else TEXTEDIT_TEXT
        body = self._slot_bytes(number)[offset:]
        return body[: body.index(0)].decode("latin-1")

    def _slot_rect(self, number: int) -> tuple[int, int, int, int]:
        addr = self.slots[number][0]
        return tuple(self.os_mem[addr + 1 + 2 * i] | (self.os_mem[addr + 2 + 2 * i] << 8) for i in range(4))

    def _paint_update(self, number: int) -> None:
        """H-PAINT effect of os_object_update(number) on text glyphs.

        M5d extends the text-edit rule to labels: ROSAN283 does not say
        whether an ob_label paints its background either, so the model
        assumes the same overdraw (new + old[len(new):]) and the same
        clearing by a box that contains it. Encodes a risk, not Rosanne.
        """
        kind = self.slots[number][2]
        if kind == OB_LABEL:
            self._check_label_width(number)
        if kind in (OB_TEXTEDIT, OB_LABEL):
            new, old = self._slot_text(number), self.painted.get(number, "")
            self.painted[number] = new + old[len(new):]
        elif kind == OB_BOX:
            bx, by, bw, bh = self._slot_rect(number)
            for n, (_, _, t) in self.slots.items():
                if t in (OB_TEXTEDIT, OB_LABEL, OB_LIST):
                    x, y, w, h = self._slot_rect(n)
                    if bx <= x and by <= y and x + w <= bx + bw and y + h <= by + bh:
                        if t == OB_LIST:
                            rows, _ = self.list_rows.get(n, ([], None))
                            self.list_rows[n] = ([""] * len(rows), None)
                        else:
                            self.painted[n] = ""

    def _check_label_width(self, number: int) -> None:
        """M5d repair: XAnne showed Rosanne drawing a label wider than its
        object outside the window, unclipped and beyond any repaint. Every
        label drawn wider than its rectangle (font-7 model) is recorded."""
        text = self._slot_text(number).encode("latin-1")
        width = font7_width(text)
        w = self._slot_rect(number)[2]
        if width > w:
            self.label_overflows.append((number, text.decode("latin-1"), width, w))

    def _slot_bytes(self, number: int) -> bytes:
        addr, length, _ = self.slots[number]
        return bytes(self.os_mem[addr : addr + length])

    # ------------------------------------------------------- M9 graphics
    def _plot(self, x: int, y: int, how: str = "ink") -> None:
        if not (0 <= x < SCREEN_W and 0 <= y < SCREEN_H):
            raise SimError(f"drawing at {x},{y}, off the {SCREEN_W}x{SCREEN_H} screen")
        i = y * SCREEN_W + x
        if how == "xor":
            self.screen[i] ^= 1
        elif how == "white":
            self.screen[i] = 0
        elif how == "black":
            self.screen[i] = 1
        elif self.bios_mode == 3:
            self.screen[i] ^= 1 if self.bios_ink == 0 else 0
        else:
            self.screen[i] = 1 if self.bios_ink == 0 else 0

    def _block(self, x, y, w, h, how) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self._plot(xx, yy, how)

    def pixel(self, x: int, y: int) -> int:
        return self.screen[y * SCREEN_W + x]

    def _bios_bitmap(self, target: int) -> None:
        """M12: bios_getpxl, bios_plotbitmap, bios_getbitmap."""
        if target == BIOS_GETPXL:
            x, y = self.de, self.hl
            if not (0 <= x < SCREEN_W and 0 <= y < SCREEN_H):
                raise SimError(f"bios_getpxl off screen {x},{y}")
            self.a = 0 if self.screen[y * SCREEN_W + x] else 1
            self.f = POISON
            self._poison("h", "l")
            self.bitmap_log.append(("getpxl", x, y))
            return
        at = self.hl
        if at >= 0x4000 or at + (14 if target == BIOS_PLOTMASKED else 11) > 0x4000:
            raise SimError(f"BIOS bitmap parameters at {at:04X}h, not in the bottom quarter")
        x, y, w, h = (self._rw(at + 2 * i) for i in range(4))
        if not (w and h and x + w <= SCREEN_W and y + h <= SCREEN_H):
            raise SimError(f"BIOS bitmap rectangle {x},{y},{w},{h} off screen")
        if not self.mouse_hidden:
            self.mouse_draws_visible += 1
        row = (w + 7) // 8
        if target == BIOS_GETBITMAP:
            buf = self.de
            # [static: PCW045.SYS #1359] the blitter writes the rows to the
            # 24-bit address at +8..+10, ROSAN283 says to DE: the runtime's
            # contract is that both name the same buffer (block #80 is the
            # bottom quarter)
            if (self._rw(at + 8), self.mem[at + 10]) != (buf, 0x80):
                raise SimError("bios_getbitmap: +8..+10 is not the DE buffer in block #80")
            if buf + row * h > 0x4000:
                raise SimError(f"bios_getbitmap buffer {buf:04X}h + {row * h} not in the bottom quarter")
            for j in range(h):
                for i in range(row):
                    byte = 0
                    for b in range(8):
                        px = x + 8 * i + b
                        white = px >= x + w or not self.screen[(y + j) * SCREEN_W + px]
                        byte |= (0x80 >> b) if white else 0
                    self.mem[buf + j * row + i] = byte
            self.bitmap_log.append(("get", x, y, w, h))
        else:
            if self.bios_mode != 0 or self.bios_ink != 0:
                raise SimError("bios_plotbitmap outside black ink / opaque mode (the runtime's contract)")
            data, offset = self._bitmap_source(at + 8, row * h)
            mask = None
            if target == BIOS_PLOTMASKED:
                # M13 [doc: "+11 24-bit address of mask data (0=transp)"; static:
                # PCW045.SYS #1478 ANDs data with mask, the screen kept where a
                # mask bit is 0]: a set (white) mask bit draws the data's pixel
                mask, moffset = self._bitmap_source(at + 11, row * h)
            for j in range(h):
                for i in range(w):
                    bit = 0x80 >> (i % 8)
                    if mask is not None and not mask[moffset + j * row + i // 8] & bit:
                        continue
                    white = data[offset + j * row + i // 8] & bit
                    self.screen[(y + j) * SCREEN_W + x + i] = 0 if white else 1
            kind = "masked" if mask is not None else "plot"
            self.draw_log.append(("bitmap", x, y, w, h))
            self.bitmap_log.append((kind, x, y, w, h))
        self._poison("a", "b", "c", "d", "e", "h", "l")

    def _bitmap_source(self, at: int, size: int):
        """The bytes a BIOS bitmap call reads at the 24-bit address at *at*:
        (the 16K block's bytes, the offset). M13: block #80 is the bottom
        quarter (the runtime's repacking buffers)."""
        offset, block = self._rw(at) & 0x3FFF, self.mem[at + 2]
        if block == 0x80:
            data = self.mem[0:0x4000]
            if not 0x2C00 <= offset or offset + size > 0x3000:
                raise SimError(f"BIOS bitmap data {offset:04X}h+{size} outside the bottom-quarter strip")
        else:
            if block not in self.owned:
                raise SimError(f"bios_plotbitmap from block {block:02X}h, which the program does not own")
            data = self.mem[0x8000:0xC000] if block == self.q2 else self.owned.get(block)
        if offset + size > 0x4000:
            raise SimError("bios_plotbitmap data past its block")
        return data, offset

    def _bios_graphics(self, target: int) -> None:
        """BIOS graphics (ROSAN283): registers as documented; the 16-bit
        parameter block must be in the bottom quarter (the BIOS may map
        quarter 1 away: bios_printstring "HL must NOT be in range
        #4000-7FFF" — the model insists, as the runtime does)."""
        if target == BIOS_SETINK:
            if self.a not in (0, 1):
                raise SimError(f"bios_setink A={self.a}")
            self.bios_ink = self.a
            self._poison("c")
            return
        if target == BIOS_SETMODE:
            if self.a not in (0, 1, 2, 3):
                raise SimError(f"bios_setmode A={self.a}")
            self.bios_mode = self.a
            self._poison("c")
            return
        if target == BIOS_GETINK:
            self.a = self.bios_ink
            return
        if target == BIOS_GETMODE:
            self.a = self.bios_mode
            return
        if not self.mouse_hidden:
            self.mouse_draws_visible += 1
        if target == BIOS_PIXEL:
            self.draw_log.append(("pixel", self.de, self.hl))
            self._plot(self.de, self.hl)
            self._poison("a", "c")
            return
        at = self.hl
        if at >= 0x4000:
            raise SimError(f"BIOS graphics parameters at {at:04X}h, not in the bottom quarter")
        words = [self._rw(at + 2 * i) for i in range(4)]
        if target == BIOS_LINE:
            x1, y1, x2, y2 = words
            self.draw_log.append(("line", x1, y1, x2, y2))
            if x1 != x2 and y1 != y2:
                # Rosanne 1.12 bios_line (#0FB5) draws only horizontal and
                # vertical lines; a sloped one returns without drawing
                # [static: PCW045.SYS; XAnne: GFXPROBE diagonal missing, KI-49]
                self.bios_sloped_lines += 1
                self._poison("a", "b", "c", "h", "l")
                return
            dx, dy = abs(x2 - x1), -abs(y2 - y1)
            sx, sy = (1 if x1 < x2 else -1), (1 if y1 < y2 else -1)
            err, x, y = dx + dy, x1, y1
            while True:
                self._plot(x, y)
                if x == x2 and y == y2:
                    break
                e2 = 2 * err
                if e2 >= dy:
                    err += dy
                    x += sx
                if e2 <= dx:
                    err += dx
                    y += sy
        else:  # bios_rectang: the outline of x, y, w, h
            x, y, w, h = words
            self.draw_log.append(("rect", x, y, w, h))
            for xx in range(x, x + w):
                self._plot(xx, y)
                if h > 1:
                    self._plot(xx, y + h - 1)
            for yy in range(y + 1, y + h - 1):
                self._plot(x, yy)
                if w > 1:
                    self._plot(x + w - 1, yy)
        self._poison("a", "b", "c", "h", "l")

    def _canvas_call(self, fn: int) -> None:
        if fn == FN_OS_MOUSE_OFF:
            self.mouse_hidden += 1
            self.os_log.append((fn, None))
            return
        if fn == FN_OS_MOUSE_ON:
            if not self.mouse_hidden:
                raise SimError("os_mouse_on without os_mouse_off")
            self.mouse_hidden -= 1
            self.os_log.append((fn, None))
            return
        if fn == FN_OS_GET_MOUSE_XY:
            self.os_log.append((fn, self.mouse_xy))
            self.set_de(self.mouse_xy[0])
            self.set_hl(self.mouse_xy[1])
            return
        if self.c != FAKE_APP_BANK or not 0x4000 <= self.hl < 0x8000:
            raise SimError(f"OS drawing data at C={self.c:02X}h HL={self.hl:04X}h, not in the app bank")
        at = self.hl
        if fn == FN_OS_DIALOG_STRING:
            font, align, style, mode = self.mem[at : at + 4]
            x, y = self._rw(at + 4), self._rw(at + 6)
            end = self.mem.index(0, at + 8)
            text = bytes(self.mem[at + 8 : end]).decode("latin-1")
            if not 1 <= font <= 12 or align > 2 or style != 0 or mode > 3:
                self.f |= FLAG_C
                self._poison("a")
                return
            self.os_log.append((fn, (x, y, text)))
            self.draw_log.append(("text", x, y, text, mode))
            self.texts.append((x, y, text, mode))
            self.text_fonts.append(font)  # M15: DRAW FONT
            width = TEXT_CELL_W * len(text)
            if x + width > SCREEN_W:  # M15: measured text may end nearer the edge
                width = dialog_font_width(text.encode("latin-1"), font)
            self._block(x, y, width, TEXT_CELL_H, "black")
            self._poison("a")
            self.f &= ~FLAG_C
            return
        # os_scr_direct
        op = self.mem[at]
        x, y, w, h = (self._rw(at + 1 + 2 * i) for i in range(4))
        self.os_log.append((fn, (op, x, y, w, h)))
        self.draw_log.append(("direct", op, x, y, w, h, bytes(self.mem[at + 9 : at + 13])))
        # Rosanne 1.12's own checks [static: PCW045.SYS, os_scr_direct in OS
        # block 6], stricter than ROSAN283: both corners of the rectangle on
        # the 640 x 480 screen (so w, h >= 1); for dg_blk_grey and
        # dg_blk_grey_xor a grey value of 0..7 (the manual says 0..8; XAnne
        # refused 8: MDEDIT, M9); for dg_blk_copy the destination's top-left
        # on screen.
        # The result is the CARRY flag, not A (KI-46): the handlers return
        # with carry set on an error and "and a / ret" on success, and the
        # r1call return path hands back the handler's AF unchanged. On
        # success A is whatever the handler left: dg_blk_grey(_xor) leave the
        # grey value (the routine pops the AF it pushed on entry); for the
        # others the model leaves junk (XAnne: GFXPROBE stopped at grey 1
        # while the runtime still tested A).
        def on_screen(px, py):
            return 0 <= px < SCREEN_W and 0 <= py < SCREEN_H
        refused = (w == 0 or h == 0 or not on_screen(x, y)
                   or not on_screen(x + w - 1, y + h - 1)
                   or (op in (3, 4) and self.mem[at + 9] >= 8)
                   or (op == 10 and not on_screen(self._rw(at + 9), self._rw(at + 11))))
        if (refused or self.scr_direct_refuse) and op in (1, 2, 3, 4, 10):
            self.a = 1
            self.f |= FLAG_C
            return
        self.f &= ~FLAG_C
        self.a = self.mem[at + 9] if op in (3, 4) else self.scr_direct_a
        if op == 1:
            self._block(x, y, w, h, "white")
        elif op == 2:
            self._block(x, y, w, h, "black")
        elif op == 3:
            grey = self.mem[at + 9]
            self._block(x, y, w, h, "black" if grey < 4 else "white")
        elif op == 4:
            if self.mem[at + 9] != 0:
                raise SimError("dg_blk_grey_xor: the model knows grey value 0 (invert) only")
            self._block(x, y, w, h, "xor")
        elif op == 10:  # dg_blk_copy to x2, y2 (the model copies as if from a snapshot)
            x2, y2 = self._rw(at + 9), self._rw(at + 11)
            old = bytes(self.screen)
            for yy in range(h):
                for xx in range(w):
                    self._plot(x2 + xx, y2 + yy, "black" if old[(y + yy) * SCREEN_W + x + xx] else "white")
        else:
            raise SimError(f"os_scr_direct function {op} is outside the model")

    def canvas_pixels(self, sx: int, sy: int, w: int, h: int) -> list[str]:
        """The canvas area as rows of '.' (white) and '#' (black)."""
        return ["".join("#" if self.screen[(sy + y) * SCREEN_W + sx + x] else "." for x in range(w))
                for y in range(h)]

    def _map_q2(self, block: int) -> None:
        """bios_setmem2: map *block* at #8000-#BFFF (M9). Only the program's
        own blocks and the block found there at start may be mapped."""
        self.q2_maps.append(block)
        if block == self.q2:
            return
        if block not in self.owned and block not in self.q2_other:
            raise SimError(f"bios_setmem2 of block {block:02X}h, which the program does not own")
        window = self.mem[0x8000:0xC000]
        if self.q2 in self.owned:
            self.owned[self.q2][:] = window
        else:
            self.q2_other[self.q2] = bytearray(window)
        source = self.owned[block] if block in self.owned else self.q2_other[block]
        self.mem[0x8000:0xC000] = source
        self.q2 = block

    def _typo_screen(self) -> None:
        """M15: os_typo_charscreen: C char, B accent, DE x, HL y (pixels),
        IX low style, high mode; A = 0 / 4 no font in slot / 5 out of range.
        A character not wholly on the screen is a model error (Rosanne would
        clip to its window or answer 6 / 9; the runtime must not ask)."""
        if not self.typo_ready or self.typo_selected != 0:
            raise SimError("os_typo_charscreen before os_typo_init / select")
        if not self.mouse_hidden:
            raise SimError("os_typo_charscreen with the mouse pointer shown")
        style, mode = self.ix & 0xFF, self.ix >> 8
        self.os_log.append((FN_OS_TYPO_CHARSCREEN, (self.de, self.hl, self.c, style, mode)))
        if self.typo_slot is None:
            self.a = 4
        elif self.b != 0 or self.c < 32:
            self.a = 5
        else:
            size = self.typo_slot[1]
            w = (typo_width(self.c, size, bool(style & 1)) + 24) // 25
            h = (size * 25 * 4 // 5 + size * 25 // 4 + 24) // 25
            x, y = self.de, self.hl - (size * 25 * 4 // 5 + 24) // 25  # the baseline less the ascender
            if x + w > SCREEN_W or y + h > SCREEN_H or y < 0:
                raise SimError(f"typo character at {x},{y} ({w}x{h}) off the {SCREEN_W}x{SCREEN_H} screen")
            if mode not in (0, 3) or style & ~3:
                raise SimError(f"os_typo_charscreen style {style} mode {mode}: outside what the runtime uses")
            self.typo_chars.append((x, y, chr(self.c), style, mode, self.typo_slot))
            self.draw_log.append(("typo", x, y, chr(self.c), style, mode))
            self._block(x, y, w, h, "black")
            self.a = 0
        self._poison("b", "c", "d", "e", "h", "l", "ix")

    def _print_call(self, fn: int) -> None:
        """M12: the typo font (83..91) and print meta-file (95..105) calls
        as ROSAN283 documents them; every register not documented as a
        result is corrupted, so the runtime may rely on none."""
        if fn not in (83, 84, 85, 87, 88, 90, 91, 95, 96, 97, 98, 99, 101, 102, 103, 105):
            raise SimError(f"OS function A={fn} is outside the model (printing)")
        self.os_log.append((fn, None))
        if fn == 83:  # os_typo_init: NC OK / C no memory; "AF corrupt, all other regs preserved"
            self.typo_ready, self.typo_slot = True, None
            self.f = 0
            return
        if fn != 84 and fn in FN_TYPO and not self.typo_ready:
            raise SimError(f"typo function {fn} before os_typo_init")
        if fn == 84:  # os_typo_getlist: B entries of 37 bytes at CHL
            if not self.typo_ready:
                raise SimError("os_typo_getlist before os_typo_init")
            for i, (ident, styles, family, name) in enumerate(TYPO_FONTS):
                entry = bytes([ident & 0xFF, ident >> 8, styles, family]) + name.encode().ljust(33, b"\0")
                self.typo_mem[37 * i: 37 * i + 37] = entry
            self.b, self.c = len(TYPO_FONTS), TYPO_BANK
            self.set_hl(0)
            self._poison("a", "d", "e", "ix")
            return
        if fn == 85:  # os_typo_select: E = slot (the model has slot 0)
            self.a = 0 if self.e == 0 else 3
            self.typo_selected = self.e
            self._poison("b", "c", "d", "e", "h", "l", "ix")
            return
        if fn in (87, 88, 90, 91) and self.typo_selected != 0:
            raise SimError("typo slot not selected")
        if fn == 87:  # os_typo_def: HL ID, D styles, B size; "F corrupt, all other regs preserved"
            ids = [f[0] for f in TYPO_FONTS]
            if self.typo_slot is not None:
                self.a = 8
            elif not self.d & 1:
                self.a = 10
            elif self.hl not in ids:
                self.a = 1
            elif self.b not in TYPO_SIZES:
                self.a = 2
            else:
                self.typo_slot = (self.hl, self.b)
                self.a = 0
            return
        if fn == 88:  # os_typo_clr
            self.a = 0 if self.typo_slot else 4
            self.typo_slot = None
            return
        if fn == 90:  # os_typo_info: HL -> pitch, ascender, descender, widest
            if self.typo_slot is None:
                self.a = 4
            else:
                size = self.typo_slot[1]
                words = (size * 25 * 6 // 5, size * 25 * 4 // 5, size * 25 // 4, size * 25)
                for i, value in enumerate(words):
                    self.mem[TYPO_INFO_AT + 2 * i] = value & 0xFF
                    self.mem[TYPO_INFO_AT + 2 * i + 1] = value >> 8
                self.set_hl(TYPO_INFO_AT)
                self.a = 0
            self._poison("b", "c", "d", "e", "ix")
            return
        if fn == 91:  # os_typo_charwidth: C char, B accent, D style; DE width; HL, BC corrupt
            if self.typo_slot is None:
                self.a = 4
            elif self.b != 0 or self.c < 32:
                self.a = 5
            else:
                self.set_de(typo_width(self.c, self.typo_slot[1], bool(self.d & 1)))
                self.a = 0
            self._poison("b", "c", "h", "l", "ix")
            return
        if fn in FN_TYPO:
            raise SimError(f"typo function {fn} is outside the model")
        # ---------------------------------------------------------- meta-file
        if fn == 95:  # os_meta_open: CHL -> 13 bytes
            if self.meta is not None:
                raise SimError("os_meta_open with a meta-page open (the runtime closes it first)")
            block = bytes(self._read24(self.c, (self.hl + i) & 0xFFFF) for i in range(13))
            self.a = self.meta_open_result
            if self.a == 0:
                self.meta = {"block": block, "records": []}
            self._poison("b", "c", "d", "e", "h", "l", "ix")
            return
        if self.meta is None:
            self.a = 255
            self._poison("b", "c", "d", "e", "h", "l", "ix")
            return
        records = self.meta["records"]
        if fn == 96:  # os_meta_font: HL ID, B size
            if self.hl not in [f[0] for f in TYPO_FONTS] or self.b not in TYPO_SIZES:
                raise SimError(f"os_meta_font {self.hl:04X}h size {self.b}: not a typo font")
            records.append(("font", self.hl, self.b))
        elif fn == 97:
            records.append(("style", self.d))
        elif fn == 98:  # HL baseline, DE top, BC bottom
            if not self.de <= self.hl <= self.bc:
                raise SimError("os_meta_y: top <= baseline <= bottom")
            records.append(("y", self.hl, self.de, self.bc))
        elif fn == 99:  # C char, B accent, DE x
            records.append(("char", self.c, self.b, self.de))
        elif fn == 101:  # DE left, BC right, HL top, IX thickness
            if self.bc < self.de:
                raise SimError("os_meta_hline: right < left")
            records.append(("hline", self.de, self.bc, self.hl, self.ix))
        elif fn == 102:  # DE x, HL top, BC bottom, IX thickness
            if self.bc < self.hl:
                raise SimError("os_meta_vline: bottom < top")
            records.append(("vline", self.de, self.hl, self.bc, self.ix))
        elif fn == 103:  # os_meta_print: B = 0 / 1
            if self.b not in (0, 1):
                raise SimError("os_meta_print B is 0 or 1")
            self.a = self.print_result
            if self.a == 0:
                self.printed.append({"block": self.meta["block"], "records": list(records)})
            self._poison("b", "c", "d", "e", "h", "l", "ix")
            return
        elif fn == 105:
            self.meta = None
        else:
            raise SimError(f"meta-file function {fn} is outside the model")
        self.a = 0
        self._poison("b", "c", "d", "e", "h", "l", "ix")

    def _read24(self, bank: int, addr: int) -> int:
        if bank == self.q2 and bank in self.owned:  # M9: mapped at #8000
            return self.mem[0x8000 + (addr & 0x3FFF)]
        if bank == OS_BANK:
            return self.os_mem[addr & 0x3FFF]
        if bank == FAKE_APP_BANK:
            return self.mem[0x4000 + (addr & 0x3FFF)]
        if bank == TYPO_BANK:  # M12: the model's typo font list
            return self.typo_mem[addr & 0x3FFF]
        if bank == 0x80:  # M12: the bottom quarter (ROSAN283: block #80)
            return self.mem[addr & 0x3FFF]
        if bank in self.owned:  # M8
            return self.owned[bank][addr & 0x3FFF]
        raise SimError(f"24-bit read from unmodelled bank {bank:02X}h")

    def _next_block(self, bank: int) -> int | None:
        """os_get_next_mem (fn 40) for a block of this program: the next one
        in allocation order (PCW045.SYS block 8 #B921), or None. The
        program's own block (allocated by the loader first) is followed by
        the first block os_get_mem gave."""
        order = list(self.owned)
        if bank == FAKE_APP_BANK:
            return order[0] if order else None
        if bank in self.owned:
            i = order.index(bank)
            return order[i + 1] if i + 1 < len(order) else None
        raise SimError(f"os_copy_24bit roll-over from block {bank:02X}h, which the program does not own")

    def _write24(self, bank: int, addr: int, value: int) -> None:
        """M8: an OS write into the program's bank (seen by on_write) or an
        owned block; anything else is a model error."""
        if bank == FAKE_APP_BANK:
            target = 0x4000 + (addr & 0x3FFF)
            if self.on_write is not None:
                self.on_write(self, target, value)
            self.mem[target] = value
        elif bank == 0x80:  # M13: into the bottom quarter (a repacking strip), seen by on_write
            target = addr & 0x3FFF
            if self.on_write is not None:
                self.on_write(self, target, value)
            self.mem[target] = value
        elif bank == self.q2 and bank in self.owned:  # M9: mapped at #8000
            self.mem[0x8000 + (addr & 0x3FFF)] = value
        elif bank in self.owned:
            self.owned[bank][addr & 0x3FFF] = value
        else:
            raise SimError(f"OS write into block {bank:02X}h, which the program does not own")

    # ------------------------------------------------ M8 memory management
    def _mem_call(self, fn: int) -> None:
        if fn == FN_OS_ASK_MEM:
            # out: A = 16ks free, B = owned by applications, C = by folders; F corrupt
            self.os_log.append((fn, None))
            self.a, self.b, self.c = len(self.mem_free), 1 + len(self.owned), 0
            self.f = 0
            return
        if fn == FN_OS_GET_MEM:
            # in: B = 16ks, E = owner #00; out NC: B = allocated (may be fewer),
            # HL = 16-bit address of the 0-terminated list; AF, C corrupt
            if self.e != 0:
                raise SimError("os_get_mem for a folder (E <> 0) is outside the model")
            given = self.mem_free[: self.b]
            del self.mem_free[: len(given)]
            for block in given:
                self.owned[block] = bytearray([MEM_JUNK]) * 0x4000
            self.mem[MEM_LIST_AT : MEM_LIST_AT + len(given) + 1] = bytes(given) + b"\0"
            self.os_log.append((fn, (self.b, len(given))))
            self.b = len(given)
            self.set_hl(MEM_LIST_AT)
            self._poison("a", "c")
            self.f = 0
            return
        if fn == FN_OS_RELEASE_MEM:
            # in: C,HL = 24-bit address of the 0-terminated list, E = #00
            if self.e != 0:
                raise SimError("os_release_mem for a folder (E <> 0) is outside the model")
            blocks, at = [], self.hl
            while (block := self._read24(self.c, at)) != 0:
                if block not in self.owned:
                    raise SimError(f"os_release_mem of block {block:02X}h, which the program does not own")
                blocks.append(block)
                at += 1
            for block in blocks:
                if block == self.q2:  # M9: the runtime maps its own block back first
                    raise SimError(f"os_release_mem of block {block:02X}h while it is mapped at #8000")
                del self.owned[block]
                self.mem_free.append(block)
            self.os_log.append((fn, tuple(blocks)))
            self.a, self.b, self.c = len(self.mem_free), 1 + len(self.owned), 0
            self._poison("d", "e", "h", "l", "ix")
            self.f = 0
            return
        if fn == FN_OS_GET_MEM_OWNERID:
            # in: E = block #80..#FF; out C: illegal; NC: DE = owner
            # (#0000 free, #01xx application); AF, HL corrupt. The model's
            # program bank is the loader's block, owned by the program.
            block = self.e
            self.os_log.append((fn, block))
            if block in self.mem_owner:  # test hook: a block reported as someone else's
                owner = self.mem_owner[block]
            elif block == FAKE_APP_BANK or block in self.owned:
                owner = MODEL_APP_ID
            elif block < 0x80:
                self.f = FLAG_C
                return
            elif block in self.mem_free:
                owner = 0
            else:
                owner = 0x0081  # model: everything else belongs to the OS
            self.d, self.e = owner >> 8, owner & 0xFF
            self._poison("a", "h", "l")
            self.f = 0
            return
        if fn == FN_OS_COPY_24BIT:
            # in: C,HL = source, B,DE = destination, IX = length; out NC/C,
            # CHL / BDE advanced, IX = 0 when OK; A corrupt (ROSAN283).
            # Model of the routine in PCW045.SYS (block 6 #5CB6; M8 A1
            # follow-up): bytes are copied one at a time and, after EVERY
            # byte (the last one included), a pointer that has reached the
            # block end moves to the owner's next block (os_get_next_mem: the
            # allocation order); if there is none the call returns carry,
            # after the bytes were copied. So a copy ending exactly at the end
            # of the owner's last block reports an error (owner XAnne A1,
            # MEMPROBE W=BAD). On that error IX is left as it was.
            length = self.ix
            if self.mem_copy_fails:  # test hook: "C = Error"
                self.os_log.append((fn, "fail"))
                self._poison("a")
                self.f = FLAG_C
                return
            sb, so, db, do = self.c, self.hl & 0x3FFF, self.b, self.de & 0x3FFF
            self.os_log.append((fn, (sb, so, db, do, length)))
            failed = False
            for k in range(length):
                self._write24(db, do, self._read24(sb, so))
                so, do = so + 1, do + 1
                if not self.copy_end_carry:  # the pre-A1 model (KI-34): no roll-over at all
                    if (so == 0x4000 or do == 0x4000) and k + 1 < length:
                        raise SimError("os_copy_24bit across a 16K block end: roll-over is outside the model")
                    continue
                if so == 0x4000:
                    sb, so = self._next_block(sb), 0
                if do == 0x4000:
                    db, do = self._next_block(db), 0
                if sb is None or db is None:
                    failed = True
                    break
            if not failed and self.copy_carry_if is not None and self.copy_carry_if(
                    (self.c, self.hl & 0x3FFF, self.b, self.de & 0x3FFF, length)):
                failed = True  # test hook: a carry Rosanne would not give here (bytes copied)
            if failed:
                self.copy_end_errors.append((self.c, self.hl & 0x3FFF, self.b, self.de & 0x3FFF, length))
                self._poison("a")
                self.f = FLAG_C
                return
            if not self.copy_end_carry:
                sb, db, so, do = self.c, self.b, (self.hl + length) & 0x3FFF, (self.de + length) & 0x3FFF
            if (sb, db) != (self.c, self.b):
                self.copy_rollovers.append((self.c, self.hl & 0x3FFF, self.b, self.de & 0x3FFF, length))
            self.c, self.b = sb, db
            self.set_hl(so)
            self.set_de(do)
            self.ix = 0
            self._poison("a")
            self.f = 0
            return
        raise AssertionError(fn)

    def _object_define(self) -> None:
        number = self.e
        if self.c != FAKE_APP_BANK or not 0x4000 <= self.hl < 0x8000:
            raise SimError("os_object_define definition must be in the app bank #4000-#7FFF")
        if number not in self.slots:
            raise SimError(f"os_object_define for unknown object {number}")
        addr, slot_len, kind = self.slots[number]
        new = self._record_at(self.hl)
        if new[0] != kind:
            raise SimError(f"os_object_define changes object {number}'s type")
        if len(new) > slot_len:
            raise SimError(
                f"os_object_define object {number}: {len(new)} bytes is longer than the "
                f"existing {slot_len}-byte definition (v0.5.2 corruption class)"
            )
        self.os_mem[addr : addr + len(new)] = new
        if kind in (OB_LIST, OB_DROPBUTTON):
            self.items_of(number)  # Rosanne reads the item texts it draws
        if kind == OB_DROPBUTTON:
            ntot, cur = new[18] | (new[19] << 8), new[22] | (new[23] << 8)
            if cur >= ntot:
                raise SimError(
                    f"drop button {number} defined with current {cur:04X}h outside its {ntot} "
                    "items: opening it froze XAnne (owner, UIPROBE3 F)"
                )
        self.os_log.append((FN_OS_OBJECT_DEFINE, (number, bytes(new))))
        self._poison("a", "b", "c", "d", "e", "h", "l", "ix")
        self.f = 0

    def _record_at(self, addr: int) -> bytes:
        """One object record at *addr* in app memory, by its documented length."""
        kind = self.mem[addr]
        if kind in FIXED_RECORD_LEN:
            return bytes(self.mem[addr : addr + FIXED_RECORD_LEN[kind]])
        if kind == OB_LABEL:  # M5d dynamic labels: +12 text, "max 128 chars"
            end = addr + LABEL_TEXT
            while self.mem[end] != 0:
                end += 1
                if end - addr - LABEL_TEXT > 128:
                    raise SimError("ob_label text exceeds 128 bytes")
            return bytes(self.mem[addr : end + 1])
        if kind == OB_TEXTEDIT:
            end = addr + TEXTEDIT_TEXT
            while self.mem[end] != 0:
                end += 1
                if end - addr - TEXTEDIT_TEXT > 128:
                    raise SimError("ob_textedit text exceeds 128 bytes")
            return bytes(self.mem[addr : end + 1])
        raise SimError(f"os_object_define for object type {kind} is outside the M3b model")

    def _apply_control_click(self, number: int) -> None:
        """os_process_event on obev_click: record the value change in the
        OS copy (ROSAN283) — checkbox toggles; textedit runs the edit."""
        if number not in self.slots:
            return None
        addr, slot_len, kind = self.slots[number]
        if kind == OB_CHECKBOX:
            self.os_mem[addr + 9] = 0x00 if self.os_mem[addr + 9] else 0xFF
        elif kind == OB_RADIO:
            group = self.os_mem[addr + 10]
            if self.radio_mode == "exclusive":
                for n, (a2, _, k2) in self.slots.items():
                    if k2 == OB_RADIO and self.os_mem[a2 + 10] == group:
                        self.os_mem[a2 + 9] = 0
            self.os_mem[addr + 9] = 0xFF
        elif kind == OB_SPINNER:
            spin = self.pending_spin
            self.pending_spin = None
            if spin not in (1, 5):
                raise SimError("a spinner click needs a scripted direction (1 up / 5 down)")
            return spin
        elif kind == OB_TEXTEDIT and self.pending_edit and self.pending_edit[0] == number:
            text = self.pending_edit[1].encode("latin-1")
            legal_len = self.os_mem[addr + 9 + 24]
            legal_bank = self.os_mem[addr + 9 + 23]
            if legal_bank > 3 and legal_len:
                legal_addr = self.os_mem[addr + 9 + 21] | (self.os_mem[addr + 9 + 22] << 8)
                legal = {self._read24(legal_bank, legal_addr + i) for i in range(legal_len)}
                text = bytes(b for b in text if b in legal)  # Rosanne refuses other keys
            max_len = self.os_mem[addr + TEXTEDIT_MAXLEN] | (self.os_mem[addr + TEXTEDIT_MAXLEN + 1] << 8)
            room = slot_len - TEXTEDIT_TEXT  # bytes incl. NUL reserved by the definition
            if len(text) > max_len:
                raise SimError(f"edit of {len(text)} bytes exceeds max length {max_len}")
            if len(text) + 1 > room:
                raise SimError(
                    f"edit of {len(text)} bytes overflows the {room}-byte text slot "
                    "of object {number} (v0.5.2 corruption class)"
                )
            self.os_mem[addr + TEXTEDIT_TEXT : addr + TEXTEDIT_TEXT + len(text) + 1] = text + b"\0"
            self.painted[number] = self._slot_text(number)  # the OS editor drew it
        self.pending_edit = None
        return None

    # ------------------------------------------------- M6 Phase 2 controls
    def _apply_phase2_event(self, number: int):
        """os_process_event for a list, drop-down or scroll bar (M6 Phase 2).
        ROSAN283: the OS "records the value changes in the dialog data" —
        a list's selection (model: the list is also scrolled to show a
        picked item) and a drop-down's current entry — "except scroll-bars /
        spinners", whose B (1..5) and DE (new handle position) are returned
        instead."""
        pending, self.pending_phase2 = self.pending_phase2, None
        if pending is None:
            return None
        if pending[0] != number or number not in self.slots:
            raise SimError("scripted Phase 2 event lost its object")
        addr, _, kind = self.slots[number]
        os = self.os_mem
        if pending[1] == "pick":
            index = pending[2]
            ntot = os[addr + 10] | (os[addr + 11] << 8)
            nvis = os[addr + 12] | (os[addr + 13] << 8)
            first = os[addr + 14] | (os[addr + 15] << 8)
            if kind != OB_LIST or not 0 <= index < ntot:
                raise SimError(f"pick of item {index} in a list of {ntot}")
            if not first <= index < first + nvis:
                first = min(index, max(ntot - nvis, 0))
                os[addr + 14], os[addr + 15] = first & 0xFF, first >> 8
            os[addr + 18], os[addr + 19] = index & 0xFF, index >> 8
            self.shown[number] = self._slot_bytes(number)  # the OS redraws its list
            return None
        if pending[1] == "drop":
            index = pending[2]
            ntot = os[addr + 18] | (os[addr + 19] << 8)
            if kind != OB_DROPBUTTON or not 0 <= index < ntot:
                raise SimError(f"drop-down choice {index} of {ntot}")
            os[addr + 22], os[addr + 23] = index & 0xFF, index >> 8
            if self.drop_writes_label:
                label = os[addr + 9]
                laddr, llen, _ = self.slots[label]
                text = self.items_of(number)[index].encode("latin-1")[: llen - LABEL_TEXT - 1]
                os[laddr + LABEL_TEXT : laddr + LABEL_TEXT + len(text) + 1] = text + b"\0"
            self.shown[number] = self._slot_bytes(number)
            return None
        if kind not in (OB_VSCROLL, OB_HSCROLL):
            raise SimError("a scripted scroll event must name a scroll bar")
        return pending[2], pending[3]

    def _list_draw(self, number: int, full: bool) -> None:
        """Display model H-LISTPAINT (owner XAnne, UIPROBE2 U6: a list
        redefined and updated after its frame box was repainted stayed
        blank). os_dialog_display and os_object_display (fn 71) draw every
        visible row. os_object_update (fn 72) is modelled as incremental, by
        ROSAN283's "+16 Reserved - previous first visible / +20 previous
        list selection": all rows only if first <> previous first, else only
        the rows whose highlight changes, else nothing. After drawing, the OS
        copy's previous fields equal the current ones. A model of an
        observation, not of Rosanne's renderer."""
        addr = self.slots[number][0]
        os = self.os_mem

        def word(at):
            return os[addr + at] | (os[addr + at + 1] << 8)

        n, nvis, first, prev_first = word(10), word(12), word(14), word(16)
        sel, prev_sel = word(18), word(20)
        items = self.items_of(number)
        # Owner XAnne (M7 retest, L1/L2): Rosanne also draws the visible rows
        # at or past Ntot from the pointer table: zero slots showed OS text
        # ("» A v1.12") and a slot left from a longer list a ghost item.
        row_text = [items[first + i] if first + i < n else self.slot_text(number, first + i)
                    for i in range(nvis)]
        lit = sel - first if first <= sel < first + nvis and sel < n else None
        rows, _ = self.list_rows.get(number, ([""] * nvis, None))
        rows = (rows + [""] * nvis)[:nvis]
        if full or first != prev_first:
            rows = row_text
        elif sel != prev_sel:
            for s in (sel, prev_sel):
                if first <= s < first + nvis:
                    rows[s - first] = row_text[s - first]
        else:
            lit = self.list_rows.get(number, (None, None))[1]
        self.list_rows[number] = (rows, lit)
        os[addr + 16 : addr + 18] = os[addr + 14 : addr + 16]
        os[addr + 20 : addr + 22] = os[addr + 18 : addr + 20]

    def _drop_readout(self, number: int) -> None:
        """Owner XAnne (UIPROBE2 U1, U6): Rosanne writes a drop button's
        current item into its linked label when the dialog is displayed and
        when the button is updated. A current entry outside the list (#FFFF,
        "none") is unverified (UIPROBE3 F): the label is left as it is."""
        addr = self.slots[number][0]
        os = self.os_mem
        ntot = os[addr + 18] | (os[addr + 19] << 8)
        cur = os[addr + 22] | (os[addr + 23] << 8)
        label = os[addr + 9]
        if cur >= ntot or label not in self.slots:
            return
        laddr, llen, _ = self.slots[label]
        text = self.items_of(number)[cur].encode("latin-1")
        if len(text) + 1 > llen - LABEL_TEXT:
            raise SimError(f"drop button {number}: readout {text!r} overflows label {label}")
        os[laddr + LABEL_TEXT : laddr + LABEL_TEXT + len(text) + 1] = text + b"\0"
        self.shown[label] = self._slot_bytes(label)
        self.painted[label] = text.decode("latin-1")

    def list_on_screen(self, number: int) -> tuple[list[str], int | None]:
        """(row texts as drawn, highlighted row) under H-LISTPAINT."""
        return self.list_rows[number]

    def slot_text(self, number: int, index: int) -> str:
        """What Rosanne draws for pointer-table slot *index* of a list or
        drop-down (also past its count): the text the slot points at, or
        JUNK_ROW when it points outside the program (a zero slot reads OS
        memory) or at bytes that are not a short printable text."""
        addr, _, kind = self.slots[number]
        os = self.os_mem
        at = 25 if kind == OB_LIST else 24
        table = os[addr + at] | (os[addr + at + 1] << 8)
        bank = os[addr + at + 2]
        p = table + 3 * index
        ptr = self._read24(bank, p) | (self._read24(bank, p + 1) << 8)
        pbank = self._read24(bank, p + 2)
        if pbank != FAKE_APP_BANK or not 0x4000 <= ptr < 0x8000:
            return JUNK_ROW
        text = bytearray()
        while (b := self._read24(pbank, ptr + len(text))) != 0:
            if not 0x20 <= b < 0x7F or len(text) >= LIST_ITEM_MODEL_MAX:
                return JUNK_ROW
            text.append(b)
        return text.decode("latin-1")

    def items_of(self, number: int) -> list[str]:
        """The item texts of a list or drop-down, through its table of 24-bit
        pointers (ROSAN283 "+25 / +24 Wd24 24-bit address of string-list =
        list of 24-bit addresses"), as Rosanne would read them to draw."""
        addr, _, kind = self.slots[number]
        os = self.os_mem
        at = 25 if kind == OB_LIST else 24
        n_at = 10 if kind == OB_LIST else 18
        ntot = os[addr + n_at] | (os[addr + n_at + 1] << 8)
        table = os[addr + at] | (os[addr + at + 1] << 8)
        bank = os[addr + at + 2]
        items = []
        for i in range(ntot):
            p = table + 3 * i
            ptr = self._read24(bank, p) | (self._read24(bank, p + 1) << 8)
            pbank = self._read24(bank, p + 2)
            text = bytearray()
            while (b := self._read24(pbank, ptr + len(text))) != 0:
                text.append(b)
                if len(text) > LIST_ITEM_MODEL_MAX:
                    raise SimError(f"object {number} item {i}: text without an end")
            items.append(text.decode("latin-1"))
        return items

    def list_state(self, number: int, shown: bool = False) -> dict:
        """A list's or drop-down's record fields (OS copy, or as last drawn)."""
        data = self.shown[number] if shown else self._slot_bytes(number)

        def word(at):
            return data[at] | (data[at + 1] << 8)

        if data[0] == OB_LIST:
            sel = word(18)
            return {"n": word(10), "vis": word(12), "first": word(14),
                    "sel": None if sel >= word(10) else sel, "items": self.items_of(number)}
        sel = word(22)
        return {"n": word(18), "vis": word(20), "sel": None if sel >= word(18) else sel,
                "items": self.items_of(number)}

    def scroll_state(self, number: int, shown: bool = False) -> tuple[int, int]:
        """A scroll bar's (handle position, handle size)."""
        data = self.shown[number] if shown else self._slot_bytes(number)
        return data[10] | (data[11] << 8), data[12] | (data[13] << 8)

    # inspection helpers for tests
    def control_text(self, number: int, shown: bool = False) -> str:
        """The edit's text in the OS copy, or (shown=True) the glyphs on
        screen under the H-PAINT display model."""
        if shown:
            return self.painted[number]
        return self._slot_text(number)

    def control_checked(self, number: int, shown: bool = False) -> bool:
        data = self.shown[number] if shown else self._slot_bytes(number)
        return data[9] != 0

    def now(self) -> int:
        """Model time, in 1/CLOCK_RATE s (M13 corrective / responsiveness)."""
        return self.clock_start * CLOCK_RATE + self.steps * self.clock_by_steps + self.clock_waited

    def rtc(self) -> tuple[int, int]:
        """(seconds of the day, ticks byte) that bios_gettime reads now.

        M13 responsiveness: with rtc_phase the ticks byte runs that many
        1/256 s ahead of the seconds and wraps where they do not change, a
        model of XAnne's (JOYCE's Anne: #F9 from the host's millisecond
        counter, the seconds from its calendar clock; owner probe: steps of
        16-17/16 s and two steps back in two seconds)."""
        secs, part = divmod(self.now(), CLOCK_RATE)
        ticks = (part * 256 // CLOCK_RATE + self.rtc_phase) % 256
        return secs % 86400, ticks // self.clock_tick_step * self.clock_tick_step

    def _rosanne_arm(self, timer: int, interval: int) -> None:
        """Rosanne's re-arm (PCW045.SYS block 6 #6958, static): the deadline is
        the ticks byte now plus the interval's 1/256 s, carried into the
        seconds, and #F0."""
        secs, ticks = self.rtc()
        total = ticks + interval * 16
        self.timer_deadline[timer] = (secs + total // 256, total % 256 & 0xF0)

    def _rosanne_timer_due(self) -> int | None:
        """A timer whose deadline the clock has reached (block 6 #6830 compares
        hours, minutes, seconds, ticks in turn), re-armed or killed."""
        now = self.rtc()
        for timer, deadline in sorted(self.timer_deadline.items()):
            if now >= deadline:
                repeat, interval = self.timers[timer]
                if repeat:
                    self._rosanne_arm(timer, interval)
                else:
                    del self.timer_deadline[timer]
                return timer
        return None

    def _no_event(self) -> None:
        """Z: no event ("IX & AF corrupt, all other registers preserved")."""
        self.event_pending = False
        self._poison("a", "ix")
        self.f = FLAG_Z

    def _find_timer_entry(self) -> None:
        """The runtime's rt_gui_timer, read from the event loop that called
        os_get_event: the call returns to `jp z,rt_gui_loop`; a loop that
        polls its clock starts `call rt_tick_poll / jp nz,rt_gui_timer`
        (PB_TICKPOLL), one that takes Rosanne's timer events goes on
        `bit 0,l / jp nz,rt_gui_timer`. Entries there are recorded
        (tick_times) by a check on that one opcode."""
        ret = self.pc  # the OS call is emulated at its call site: PC is past it
        mem = self.mem
        if mem[ret] != 0xCA:
            return
        loop = mem[ret + 1] | mem[ret + 2] << 8
        if mem[loop] == 0xCD and mem[loop + 3] == 0xC2:
            entry = mem[loop + 4] | mem[loop + 5] << 8
            self.timer_polled = True
        elif mem[ret + 3] == 0xCB and mem[ret + 4] == 0x45 and mem[ret + 5] == 0xC2:
            entry = mem[ret + 6] | mem[ret + 7] << 8
        else:
            return
        self.timer_entry = entry
        op = mem[entry]
        plain = self._dispatch[op]

        def watched(op, op_addr, plain=plain):
            if op_addr == entry and self.mem[self.mem[entry + 1] | self.mem[entry + 2] << 8]:
                self.tick_times.append(self.now())  # rt_timer_run is set: the handler runs
            plain(op, op_addr)
        self._dispatch[op] = watched

    def _wait_event(self, blocking: bool = True) -> None:
        """os_wait_event (fn 2, blocking) and os_get_event (fn 1, M13 RT6):
        HL = mask in; NZ, HL = code, IX = record out; os_get_event Z when
        nothing is pending ("IX & AF corrupt").

        ROSAN283: os_wait_event "can't be Z for no event": it does not return
        until an event comes [static: block 6 #558E loops over the retrieval
        #55A8 while Z]. So while it waits, time passes and the program runs
        nothing: a ("wait", n) entry passes n sixteenths without returning,
        a ("hold", ...) entry changes a key without returning, and a
        Rosanne timer (rosanne_timers) or the next entry ends the wait. Up to
        M13 RT6 both returned Z for "wait" and "hold", as if the program were
        polling, which hid a loop that blocked with nothing to wake it
        (owner: TIMEPRB Idle stopped until the mouse moved). os_get_event
        returns Z at once when nothing is pending: under it a ("wait", n)
        passes 1/256 s a call, returning Z each time, until n sixteenths
        have passed.

        Script entries: ("click", obj), ("objevent", obj, evtype),
        ("exit",), ("message", msg_id, data), ("key", ascii), ("noevent",)
        and (M5d) ("press", ascii, shift): a key pressed while the dialog is
        shown. Per ROSAN283 (ob_textbutton "+9,11,13,15 Words Keycodes (4
        pairs of Ascii, Shift[#80=ignore])"; obev_key "object key pressed
        (txt/bmpbutton only)") it becomes om_objevent/obev_key on the first
        button whose keycode pair matches, else a plain keyboard event.
        ("noevent",) returns Z with IX corrupt even from os_wait_event, which
        the documentation says cannot happen; it exercises defensive code.
        """
        fn = FN_OS_WAIT_EVENT if blocking else FN_OS_GET_EVENT
        if self.hl != 0xFFFF:
            raise SimError(f"os event call fn {fn} mask HL={self.hl:04X}h: ROSAN283 requires #FFFF")
        self.q2_at_wait.append(self.q2)  # M9
        if self.timer_entry is None:  # M13 responsiveness
            self._find_timer_entry()
        tick = CLOCK_RATE // 256
        entry = None
        while entry is None:
            due = self._rosanne_timer_due() if self.rosanne_timers and self.timer_deadline else None
            if due is not None:
                entry = ("timer", due)
                break
            if not self.events:
                if self.free_run_until is not None and self.now() < self.free_run_until:
                    self.clock_waited += tick  # time passes with nothing to do
                    if blocking:
                        continue
                    return self._no_event()
                self.os_log.append((fn, None))
                raise _SimIdle()
            head = self.events[0]
            kind = head[0]
            if kind == "wait":  # M13 corrective: ("wait", sixteenths): time passes, no event
                left = head[1] * CLOCK_RATE // 16 if len(head) < 3 else head[2]
                step = min(tick, max(left, 0)) if blocking or left > 0 else 0
                if left <= 0 or step >= left:
                    self.clock_waited += left  # (a negative wait: the clock set back)
                    self.os_log.append((fn, self.events.pop(0)))
                else:
                    self.clock_waited += step
                    self.events[0] = ("wait", head[1], left - step)
                if blocking:
                    continue
                return self._no_event()
            if kind == "hold":  # M13: ("hold", code, down): a key goes down / up; no OS event
                self.os_log.append((fn, self.events.pop(0)))
                (self.keys_down.add if head[2] else self.keys_down.discard)(keystate_code(head[1]))
                continue
            if kind == "timer" and head[1] not in self.timers and self.timer_polled:
                # M13 responsiveness: a "timer" entry for a TIMER the event loop
                # runs itself: the handler runs once more (the time it needs to
                # be due passes, 1/256 s a poll; one it already ran counts)
                if blocking:
                    raise SimError("a TIMER the event loop runs itself, but the loop waits in "
                                   "os_wait_event, which does not return without an event")
                if len(head) > 2:  # "stale": nothing for such a loop
                    self.os_log.append((fn, self.events.pop(0)))
                elif len(self.tick_times) > self.ticks_claimed:
                    self.ticks_claimed += 1
                    self.os_log.append((fn, self.events.pop(0)))
                else:
                    if self.clock_waited > 3600 * CLOCK_RATE:
                        raise SimError("a timer script entry, but the TIMER never ran (TIMER OFF?)")
                    self.clock_waited += tick
                return self._no_event()
            entry = self.events.pop(0)
        self.os_log.append((fn, entry))
        kind = entry[0]
        if kind == "noevent":
            return self._no_event()
        record = bytearray(12)
        if kind == "type":  # M13 corrective: ("type", ascii, shift): a key typed
            # at the keyboard. Rosanne's DDM hotkey search turns a menu
            # shortcut into a menu selection (ddm_hotkey); any other key is
            # a "press" (a button's key, else a raw key event).
            found = self.ddm_hotkey(entry[1], entry[2])
            if found is not None:
                self.hotkey_log.append((entry[1], entry[2], found))
                kind, entry = "hotkey", ("hotkey",) + found
            else:
                kind, entry = "press", ("press", entry[1], entry[2])
        if kind == "press":
            target = self._key_button(entry[1], entry[2])
            if target is None:  # M13 corrective: with its shift state (it was dropped)
                kind, entry = "key", ("key", entry[1], entry[2])
            else:
                kind, entry = "objevent", ("objevent", target, OBEV_KEY)
        if kind == "key":
            code = EV_KEYBOARD
            record[2] = entry[1]
            if len(entry) > 2:  # M9: ("key", ascii, shift)
                record[3] = record[11] = entry[2]
        elif kind in ("mdown", "mmove", "mup"):  # M9: raw left button events
            # ("mdown", x, y), ("mmove", x, y [, buttons]), ("mup", x, y)
            code = {"mdown": EV_LEFT_CLICK, "mmove": EV_MOVE, "mup": EV_LEFT_RELEASE}[kind]
            x, y = entry[1], entry[2]
            buttons = entry[3] if len(entry) > 3 else (4 if kind != "mup" else 0)
            record[6], record[7], record[8], record[9] = x & 0xFF, x >> 8, y & 0xFF, y >> 8
            record[10] = buttons
            self.mouse_xy = (x, y)
        elif kind == "timer":  # M6: ("timer", n): only a running timer fires;
            # ("timer", n, "stale"): a tick already queued when it was killed
            stale = len(entry) > 2 and entry[2] == "stale"
            if entry[1] not in self.timers and not stale:
                raise SimError(f"timer {entry[1]} fired but is not set")
            code = EV_TIMER
            record[2] = entry[1]
            repeat, interval = self.timers.get(entry[1], (1, 0))
            record[3], record[4], record[5] = repeat, interval & 0xFF, interval >> 8
            if not repeat and not stale:
                del self.timers[entry[1]]
        elif kind == "hotkey":  # from "type": ("hotkey", title, entry) as the search found it
            title, number = entry[1], entry[2]
            status = 0x80
            if self.menu and title < len(self.menu):  # M15: a program without menus
                keyed = [i for i, e in enumerate(self.menu[title][1]) if e[2] != "_"]
                if number < len(keyed):
                    st, key, text = self.menu[title][1][keyed[number]]
                    if st & 0x02:  # #74AC: a tickable entry's tick is toggled
                        st ^= 0x04
                        self.menu[title][1][keyed[number]] = (st, key, text)
                    status = st
            code = EV_DDM
            record[2], record[3], record[4] = title, number, status
        elif kind == "menu":  # M6: ("menu", title, entry) selected
            title, number = entry[1], entry[2]
            if not self.menu_shown or title >= len(self.menu) or number >= self._menu_count(title):
                raise SimError(f"menu selection {title},{number} is not on the menu bar")
            if self.dialog_shown and not self.dialog["ddm_enable"]:
                raise SimError("menu selected while a dialog without ddm_enable is open")
            number = self._menu_index(title, number)
            status, key, text = self.menu[title][1][number]
            if status & 0x08 or text == "_":
                raise SimError(f"menu entry {title},{number} is greyed or a divider")
            if self.menu_autotick and status & 0x02:
                status ^= 0x04
                self.menu[title][1][number] = (status, key, text)
            code = EV_DDM
            record[2], record[3], record[4] = title, entry[2], status
        else:
            code = EV_OS_MESSAGE
            if kind == "click":
                record[2:6] = bytes((OM_OBJEVENT, entry[1], OB_TEXTBUTTON, OBEV_CLICK))
            elif kind == "clickat":  # M9: ("clickat", obj, x, y): an object click there
                record[2:6] = bytes((OM_OBJEVENT, entry[1], 1, OBEV_CLICK))
                self.mouse_xy = (entry[2], entry[3])
            elif kind == "edit":  # click on a textedit; os_process_event applies the text
                record[2:6] = bytes((OM_OBJEVENT, entry[1], OB_TEXTEDIT, OBEV_CLICK))
                self.pending_edit = (entry[1], entry[2])
            elif kind == "objevent":
                record[2:6] = bytes((OM_OBJEVENT, entry[1], 0, entry[2]))
            elif kind == "radio":  # M6: a click on a radio button
                record[2:6] = bytes((OM_OBJEVENT, entry[1], OB_RADIO, OBEV_CLICK))
            elif kind == "spin":  # M6: ("spin", obj, 1 up / 5 down [, "queued"])
                record[2:6] = bytes((OM_OBJEVENT, entry[1], OB_SPINNER, OBEV_CLICK))
                self.pending_spin = entry[2]
            elif kind == "spinev":  # ("spinev", obj, evtype, B): another event on a
                # spinner, with B left at a value ROSAN283 does not define
                record[2:6] = bytes((OM_OBJEVENT, entry[1], OB_SPINNER, entry[2]))
                self.stale_b = entry[3]
            elif kind in ("pick", "dpick"):  # M6 Phase 2: ("pick", list, index); "dpick" is
                # ROSAN283's obev_dclick, which XAnne never reported for a list (EVPROBE R4, KI-25)
                ev = OBEV_CLICK if kind == "pick" else OBEV_DCLICK
                record[2:6] = bytes((OM_OBJEVENT, entry[1], OB_LIST, ev))
                self.pending_phase2 = (entry[1], "pick", entry[2])
            elif kind == "drop":  # ("drop", dropbutton, index chosen from its list)
                record[2:6] = bytes((OM_OBJEVENT, entry[1], OB_DROPBUTTON, OBEV_CLICK))
                self.pending_phase2 = (entry[1], "drop", entry[2])
            elif kind == "scroll":  # ("scroll", bar, B [, DE [, evtype]]): B 1..5
                ev = entry[4] if len(entry) > 4 else OBEV_CLICK
                record[2:6] = bytes((OM_OBJEVENT, entry[1], 0, ev))
                self.pending_phase2 = (entry[1], "scroll", entry[2], entry[3] if len(entry) > 3 else 0)
            elif kind == "exit":
                record[2] = OM_EXIT
            elif kind == "message":
                record[2], record[3] = entry[1], entry[2]
            else:
                raise SimError(f"unknown scripted event {entry!r}")
        record[0], record[1] = code & 0xFF, code >> 8
        self.mem[EVENT_RECORD : EVENT_RECORD + 12] = record
        self.event_pending = True
        self._poison("a", "b", "c", "d", "e")  # "AF, BC, DE corrupt"
        self.set_hl(code)
        self.ix = EVENT_RECORD
        self.f = 0  # NZ

    def ddm_hotkey(self, ascii: int, shift: int):
        """(title, entry) of the DDM selection Rosanne makes of a typed key,
        or None. A model of PCW045.SYS block 6 #7446..#74C7 (static):
        IY walks the hotkey words copied from the definition (#05CB: one per
        entry, dividers excluded, #0000 after each title's last entry) for
        as many titles as there are (#0575); within a title it counts entries
        up to a #0000, which ends that title, and compares each word with
        (ASCII, shift) exactly. So a #0000 in the middle of a title ends it
        early, and the words after it are counted as the next title's: the
        selection reported is then (title, entry) as counted, whatever entry
        it really was. Greyed titles (skipped there) and greyed entries are
        not modelled: no program greys them."""
        if not self.menu_shown or (self.dialog_shown and not self.dialog["ddm_enable"]):
            return None
        words = []
        for _, entries in self.menu:
            words += [key for status, key, text in entries if text != "_"] + [0]
        want = ascii | (shift << 8)
        i = 0
        for title in range(len(self.menu)):
            number = 0
            while i < len(words):
                word = words[i]
                i += 1
                if word == 0:
                    break
                if word == want:
                    return title, number
                number += 1
        return None

    def _key_button(self, ascii: int, shift: int) -> int | None:
        """The first displayed text button whose keycodes match (M5d)."""
        if not self.dialog_shown:
            return None
        for number, (addr, _, kind) in sorted(self.slots.items()):
            if kind != OB_TEXTBUTTON:
                continue
            for i in range(4):
                code, want = self.os_mem[addr + 9 + 2 * i], self.os_mem[addr + 10 + 2 * i]
                if code and code == ascii and (want == 0x80 or want == shift):
                    return number
        return None

    def label_text(self, number: int, shown: bool = False) -> str:
        """A label's text in the OS copy, or (shown=True) its glyphs on
        screen under the H-PAINT display model (M5d)."""
        if self.slots[number][2] != OB_LABEL:
            raise SimError(f"object {number} is not a label")
        return self.painted[number] if shown else self._slot_text(number)

    def _alert_text(self) -> str:
        """Decode the os_alert definition at HL, DE bytes long.

        Definition format (ROSAN283.DOC 'os_alert', POC/NOTES.asm msg_N):
        ASCII lines each NUL-terminated, an extra NUL, then the button block.
        The alert text is everything before the double NUL; the (single) NULs
        of a multi-line definition are preserved as newlines.
        """
        start = self.hl
        length = self.de
        data = bytes(self.mem[start : min(start + length, 0x10000)])
        end = data.find(b"\x00\x00")
        text = data[:end] if end != -1 else data
        return text.replace(b"\x00", b"\n").decode("ascii", errors="replace")

    # ------------------------------------------------------------ CB group
    def _cb(self, op: int) -> None:
        group = op >> 6  # 0 rotate/shift, 1 BIT, 2 RES, 3 SET
        y = (op >> 3) & 7
        idx = op & 7
        if group == 1:  # bit b,r: H=1, N=0, Z=PV=bit clear, S tests bit 7
            value = self._get_r(idx)
            bit_set = (value >> y) & 1
            self.f = (
                (self.f & FLAG_C)
                | FLAG_H
                | (0 if bit_set else FLAG_Z | FLAG_PV)
                | (FLAG_S if y == 7 and bit_set else 0)
                | (value & (FLAG_Y | FLAG_X))
            )
            return
        if group == 2:  # res b,r: no flags
            self._set_r(idx, self._get_r(idx) & ~(1 << y) & 0xFF)
            return
        if group == 3:  # set b,r: no flags
            self._set_r(idx, self._get_r(idx) | (1 << y))
            return
        if y in (2, 3, 4, 5, 7):  # rl, rr, sla, sra, srl
            value = self._get_r(idx)
            if y == 2:  # rl
                result = ((value << 1) | (1 if self.f & FLAG_C else 0)) & 0xFF
                carry = bool(value & 0x80)
            elif y == 3:  # rr
                result = ((value >> 1) | (0x80 if self.f & FLAG_C else 0)) & 0xFF
                carry = bool(value & 0x01)
            elif y == 4:  # sla
                result = (value << 1) & 0xFF
                carry = bool(value & 0x80)
            elif y == 5:  # sra
                result = ((value >> 1) | (value & 0x80)) & 0xFF
                carry = bool(value & 0x01)
            else:  # srl
                result = value >> 1
                carry = bool(value & 0x01)
            self.f = (
                (FLAG_C if carry else 0)
                | (FLAG_S if result & 0x80 else 0)
                | (FLAG_Z if result == 0 else 0)
                | (result & (FLAG_Y | FLAG_X))
                | self._parity(result)
            )
            self._set_r(idx, result)
            return
        raise SimError(f"unsupported CB opcode CB {op:02X}h near PC={self.pc:04X}h")

    # ------------------------------------------------------------ ED group
    def _ed(self, op: int) -> None:
        if op in (0x42, 0x52, 0x62, 0x72, 0x4A, 0x5A, 0x6A, 0x7A):
            self._adc_sbc_hl(bool(op & 0x08), (op >> 4) & 3)
            return
        if op in (0x4B, 0x5B, 0x6B, 0x7B):  # ld bc/de/hl/sp,(nn)
            addr = self._fetch16()
            value = self.mem[addr] | (self.mem[(addr + 1) & 0xFFFF] << 8)
            self._set_rr((op >> 4) & 3, value)
            return
        if op in (0x43, 0x53, 0x63, 0x73):  # ld (nn),bc/de/hl/sp
            self._ww(self._fetch16(), self._get_rr((op >> 4) & 3))
            return
        if op == 0xA0:  # ldi
            self._ldi()
            return
        if op == 0x44:  # neg (M7)
            a = self.a
            result = (-a) & 0xFF
            self._flags_sub(0, a, result, -a)
            self.a = result
            return
        if op == 0x5F:  # ld a,r (M7: RANDOMIZE without a seed); R modelled as the step count
            self.a = self.steps & 0x7F
            self.f = (self.f & FLAG_C) | (FLAG_S if self.a & 0x80 else 0) | (FLAG_Z if self.a == 0 else 0)
            return
        if op in (0xA8, 0xB8):  # ldd / lddr (M7)
            while True:
                count = self.bc or 0x10000
                self._wb(self.de, self._rb(self.hl))
                self.set_hl((self.hl - 1) & 0xFFFF)
                self.set_de((self.de - 1) & 0xFFFF)
                count -= 1
                self.set_bc(count & 0xFFFF)
                self.f = (self.f & (FLAG_S | FLAG_Z | FLAG_C)) | (FLAG_PV if count else 0)
                if op == 0xA8 or not count:
                    return
        if op == 0xB0:  # ldir
            self._ldi()
            while self.f & FLAG_PV:
                self._ldi()
            return
        raise SimError(f"unsupported ED opcode ED {op:02X}h near PC={self.pc:04X}h")

    def _dd(self, op: int) -> None:
        """IX group: only ld r,(ix+d) and ld ix,nn (M3a event record reads)."""
        if op == 0x21:  # ld ix,nn
            self.ix = self._fetch16()
            return
        if op == 0xE1:  # pop ix (M8: os_copy_24bit's length)
            self.ix = self._pop16()
            return
        if op == 0xE5:  # push ix
            self._push16(self.ix)
            return
        if op == 0x22:  # ld (nn),ix (M8: MEMDIAG records IX after a copy)
            self._ww(self._fetch16(), self.ix)
            return
        if op & 0xC7 == 0x46 and op != 0x76:  # ld r,(ix+d)
            addr = (self.ix + self._fetch_rel()) & 0xFFFF
            self._set_r((op >> 3) & 7, self._rb(addr))
            return
        raise SimError(f"unsupported DD opcode DD {op:02X}h near PC={self.pc:04X}h")

    def _adc_sbc_hl(self, is_adc: bool, idx: int) -> None:
        hl = self.hl
        rr = self._get_rr(idx)
        carry = 1 if self.f & FLAG_C else 0
        if is_adc:
            total = hl + rr + carry
            result = total & 0xFFFF
            half = (hl & 0x0FFF) + (rr & 0x0FFF) + carry > 0x0FFF
            overflow = ((hl ^ result) & (rr ^ result)) & 0x8000
            carry_out = total > 0xFFFF
            sub = 0
        else:
            total = hl - rr - carry
            result = total & 0xFFFF
            half = bool((hl ^ rr ^ result) & 0x1000)
            overflow = ((hl ^ rr) & (hl ^ result)) & 0x8000
            carry_out = total < 0
            sub = FLAG_N
        self.f = (
            (FLAG_S if result & 0x8000 else 0)
            | (FLAG_Z if result == 0 else 0)
            | (FLAG_H if half else 0)
            | (FLAG_PV if overflow else 0)
            | sub
            | (FLAG_C if carry_out else 0)
            | ((result >> 8) & (FLAG_Y | FLAG_X))
        )
        self.set_hl(result)

    def _ldi(self) -> None:
        # Z80 semantics: BC=0 means 65536 transfers; here a single step.
        count = self.bc or 0x10000
        self._wb(self.de, self._rb(self.hl))
        self.set_hl((self.hl + 1) & 0xFFFF)
        self.set_de((self.de + 1) & 0xFFFF)
        count -= 1
        self.set_bc(count & 0xFFFF)
        # Z80-spec-loose per the M2 contract: H=0, N=0, PV = BC != 0.
        self.f = (self.f & (FLAG_S | FLAG_Z | FLAG_C)) | (FLAG_PV if count else 0)

    # ---------------------------------------------------------------- step
    def step(self) -> None:
        """Execute exactly one instruction; intercept OS calls at call sites.

        M11: the opcode selects its handler from a 256-entry table built from
        the same tests, in the same order, as the if-chain it replaces
        (``_build_dispatch``); tests/test_m11_harness.py runs programs in
        lockstep with that chain (tests/z80ref.py)."""
        op_addr = self.pc
        op = self.mem[op_addr]
        self.pc = (op_addr + 1) & 0xFFFF
        self.steps += 1
        self._dispatch[op](op, op_addr)

    # ---------------------------------------------------- opcode handlers
    def _x_nop(self, op, op_addr):
        return

    def _x_halt(self, op, op_addr):
        raise SimRunaway(
            f"HALT at PC={op_addr:04X}h: program stopped without os_app_exit"
        )

    def _x_cb(self, op, op_addr):
        self._cb(self._fetch8())

    def _x_ed(self, op, op_addr):
        self._ed(self._fetch8())

    def _x_dd(self, op, op_addr):
        self._dd(self._fetch8())

    def _x_fd(self, op, op_addr):  # M7: only ld iy,nn (os_rename_file's new extension)
        sub = self._fetch8()
        if sub != 0x21:
            raise SimError(f"unsupported FD opcode FD {sub:02X}h near PC={self.pc:04X}h")
        self.iy = self._fetch16()

    def _x_rot_a(self, op, op_addr):  # rlca, rrca, rla, rra (M7): S, Z, PV kept
        a, carry = self.a, 1 if self.f & FLAG_C else 0
        if op == 0x07:
            out, a = a >> 7, ((a << 1) | (a >> 7)) & 0xFF
        elif op == 0x0F:
            out, a = a & 1, ((a >> 1) | ((a & 1) << 7)) & 0xFF
        elif op == 0x17:
            out, a = a >> 7, ((a << 1) | carry) & 0xFF
        else:
            out, a = a & 1, ((a >> 1) | (carry << 7)) & 0xFF
        self.a = a
        self.f = (self.f & (FLAG_S | FLAG_Z | FLAG_PV)) | (FLAG_C if out else 0) | (a & (FLAG_Y | FLAG_X))

    def _x_jp_hl(self, op, op_addr):
        self.pc = self.hl

    def _x_ld_rr_nn(self, op, op_addr):
        self._set_rr((op >> 4) & 3, self._fetch16())

    def _x_ld_bc_a(self, op, op_addr):
        self._wb(self.bc, self.a)

    def _x_ld_de_a(self, op, op_addr):
        self._wb(self.de, self.a)

    def _x_ld_nn_hl(self, op, op_addr):
        self._ww(self._fetch16(), self.hl)

    def _x_ld_nn_a(self, op, op_addr):
        self._wb(self._fetch16(), self.a)

    def _x_ld_a_bc(self, op, op_addr):
        self.a = self._rb(self.bc)

    def _x_ld_a_de(self, op, op_addr):
        self.a = self._rb(self.de)

    def _x_ld_hl_nn(self, op, op_addr):
        self.set_hl(self._rw(self._fetch16()))

    def _x_ld_a_nn(self, op, op_addr):
        self.a = self._rb(self._fetch16())

    def _x_ld_mhl_n(self, op, op_addr):
        self._wb(self.hl, self._fetch8())

    def _x_ld_r_n(self, op, op_addr):  # ld r,n: 06 0E 16 1E 26 2E 3E (36 handled above)
        self._set_r((op >> 3) & 7, self._fetch8())

    def _x_ld_r_r(self, op, op_addr):  # ld r,r' — includes 70-75/77 ld (hl),r
        self._set_r((op >> 3) & 7, self._get_r(op & 7))

    def _x_inc_r(self, op, op_addr):
        idx = (op >> 3) & 7
        self._set_r(idx, self._inc8(self._get_r(idx)))

    def _x_dec_r(self, op, op_addr):
        idx = (op >> 3) & 7
        self._set_r(idx, self._dec8(self._get_r(idx)))

    def _x_inc_rr(self, op, op_addr):
        idx = (op >> 4) & 3
        self._set_rr(idx, (self._get_rr(idx) + 1) & 0xFFFF)

    def _x_dec_rr(self, op, op_addr):
        idx = (op >> 4) & 3
        self._set_rr(idx, (self._get_rr(idx) - 1) & 0xFFFF)

    def _x_add_hl_rr(self, op, op_addr):
        rr = self._get_rr((op >> 4) & 3)
        hl = self.hl
        total = hl + rr
        # ADD HL,rr touches only H, N, C (and the undocumented X/Y);
        # S, Z, PV are preserved.
        self.f = (
            (self.f & (FLAG_S | FLAG_Z | FLAG_PV))
            | (FLAG_H if (hl & 0x0FFF) + (rr & 0x0FFF) > 0x0FFF else 0)
            | (FLAG_C if total > 0xFFFF else 0)
            | ((total >> 8) & (FLAG_Y | FLAG_X))
        )
        self.set_hl(total & 0xFFFF)

    def _x_alu_r(self, op, op_addr):  # alu a,r
        self._alu((op >> 3) & 7, self._get_r(op & 7))

    def _x_alu_n(self, op, op_addr):  # alu a,n: C6 CE D6 DE E6 EE F6 FE
        self._alu((op >> 3) & 7, self._fetch8())

    def _x_djnz(self, op, op_addr):
        offset = self._fetch_rel()
        self.b = (self.b - 1) & 0xFF
        if self.b:
            self.pc = (self.pc + offset) & 0xFFFF

    def _x_jr(self, op, op_addr):  # jr and jr cc
        offset = self._fetch_rel()
        if op == 0x18 or self._cond((op >> 3) & 3):
            self.pc = (self.pc + offset) & 0xFFFF

    def _x_jp(self, op, op_addr):  # jp and jp cc
        target = self._fetch16()
        if op == 0xC3 or self._cond((op >> 3) & 7):
            self.pc = target

    def _x_call(self, op, op_addr):  # call and call cc
        target = self._fetch16()
        if op == 0xCD or self._cond((op >> 3) & 7):
            self._call(target)

    def _x_ret(self, op, op_addr):  # ret and ret cc
        if op == 0xC9 or self._cond((op >> 3) & 7):
            self.pc = self._pop16()

    def _x_push(self, op, op_addr):
        self._push16(self._get_rr_stack((op >> 4) & 3))

    def _x_pop(self, op, op_addr):
        idx = (op >> 4) & 3
        self._set_rr_stack(idx, self._pop16())

    def _x_cpl(self, op, op_addr):
        self.a = (~self.a) & 0xFF
        self.f = (
            (self.f & (FLAG_S | FLAG_Z | FLAG_PV | FLAG_C))
            | FLAG_H
            | FLAG_N
            | (self.a & (FLAG_Y | FLAG_X))
        )

    def _x_scf(self, op, op_addr):
        self.f = (
            (self.f & (FLAG_S | FLAG_Z | FLAG_PV))
            | FLAG_C
            | (self.a & (FLAG_Y | FLAG_X))
        )

    def _x_ccf(self, op, op_addr):
        carry = self.f & FLAG_C
        self.f = (
            (self.f & (FLAG_S | FLAG_Z | FLAG_PV))
            | (FLAG_H if carry else 0)
            | (0 if carry else FLAG_C)
            | (self.a & (FLAG_Y | FLAG_X))
        )

    def _x_ex_de_hl(self, op, op_addr):
        self.d, self.h = self.h, self.d
        self.e, self.l = self.l, self.e

    def _x_unsupported(self, op, op_addr):
        raise SimError(f"unsupported opcode {op:02X}h at PC={op_addr:04X}h")

    # The if-chain of step() up to M10, as (test, handler) in its order: the
    # first test that holds for an opcode chooses its handler.
    _CHAIN = (
        (lambda op: op == 0x00, "_x_nop"),
        (lambda op: op == 0x76, "_x_halt"),
        (lambda op: op == 0xCB, "_x_cb"),
        (lambda op: op == 0xED, "_x_ed"),
        (lambda op: op == 0xDD, "_x_dd"),
        (lambda op: op == 0xFD, "_x_fd"),
        (lambda op: op in (0x07, 0x0F, 0x17, 0x1F), "_x_rot_a"),
        (lambda op: op == 0xE9, "_x_jp_hl"),
        (lambda op: op in (0x01, 0x11, 0x21, 0x31), "_x_ld_rr_nn"),
        (lambda op: op == 0x02, "_x_ld_bc_a"),
        (lambda op: op == 0x12, "_x_ld_de_a"),
        (lambda op: op == 0x22, "_x_ld_nn_hl"),
        (lambda op: op == 0x32, "_x_ld_nn_a"),
        (lambda op: op == 0x0A, "_x_ld_a_bc"),
        (lambda op: op == 0x1A, "_x_ld_a_de"),
        (lambda op: op == 0x2A, "_x_ld_hl_nn"),
        (lambda op: op == 0x3A, "_x_ld_a_nn"),
        (lambda op: op == 0x36, "_x_ld_mhl_n"),
        (lambda op: op & 0xC7 == 0x06, "_x_ld_r_n"),
        (lambda op: 0x40 <= op <= 0x7F, "_x_ld_r_r"),
        (lambda op: op & 0xC7 == 0x04, "_x_inc_r"),
        (lambda op: op & 0xC7 == 0x05, "_x_dec_r"),
        (lambda op: op & 0xCF == 0x03, "_x_inc_rr"),
        (lambda op: op & 0xCF == 0x0B, "_x_dec_rr"),
        (lambda op: op & 0xCF == 0x09, "_x_add_hl_rr"),
        (lambda op: 0x80 <= op <= 0xBF, "_x_alu_r"),
        (lambda op: op & 0xC7 == 0xC6, "_x_alu_n"),
        (lambda op: op == 0x10, "_x_djnz"),
        (lambda op: op in (0x18, 0x20, 0x28, 0x30, 0x38), "_x_jr"),
        (lambda op: op == 0xC3 or (op & 0xC7 == 0xC2), "_x_jp"),
        (lambda op: op == 0xCD or (op & 0xC7 == 0xC4), "_x_call"),
        (lambda op: op == 0xC9 or (op & 0xC7 == 0xC0), "_x_ret"),
        (lambda op: op & 0xCF == 0xC5, "_x_push"),
        (lambda op: op & 0xCF == 0xC1, "_x_pop"),
        (lambda op: op == 0x2F, "_x_cpl"),
        (lambda op: op == 0x37, "_x_scf"),
        (lambda op: op == 0x3F, "_x_ccf"),
        (lambda op: op == 0xEB, "_x_ex_de_hl"),
        (lambda op: op in (0xF3, 0xFB), "_x_nop"),  # di / ei: the model has no interrupts
    )

    @classmethod
    def dispatch_names(cls) -> list[str]:
        """The handler name for each opcode 0..255 (the first test in _CHAIN that holds)."""
        return [next((name for test, name in cls._CHAIN if test(op)), "_x_unsupported")
                for op in range(256)]

    def _build_dispatch(self) -> None:
        self._dispatch = [getattr(self, name) for name in self.dispatch_names()]


class Disk:
    """In-memory model of the floppy for the filing functions (M4).

    *files* maps (folder, "NAME.EXT") to bytes; *folders* holds the existing
    absolute folder paths (upper case). *faults* maps a filing function
    number to an error code it should return (for os_set_device any value
    makes it fail); *eof_registers* chooses what os_read_file's #A1 result
    leaves in BDE/CHL: "documented" = ROSAN283's wording (BDE = amount not
    loaded, CHL = file size), "unspecified" (default) = junk — the owner's
    XAnne ROUNDTRP run showed #A1 with values that did not fit the wording,
    so the runtime must not depend on them (M4 repair); *truncate_on_open*
    = False models the alternative to hypothesis H-TRUNC. Engineering aid only: Rosanne's real behaviour is what
    the owner observes in XAnne.
    """

    def __init__(self, files=None, folders=("\\", "\\PCW", "\\PCW\\FOLDER01"),
                 faults=None, truncate_on_open: bool = True,
                 eof_registers: str = "unspecified", faults_from=None, faults_at=None):
        self.files: dict[tuple[str, str], bytes] = dict(files or {})
        self.folders = set(folders)
        self.faults: dict[int, int] = dict(faults or {})
        # M9: {fn: (n, code)}: the n-th and every later call of fn fails with code
        self.faults_from: dict[int, tuple[int, int]] = dict(faults_from or {})
        # M10: {fn: {n: code}}: only the n-th call of fn fails, with code
        self.faults_at: dict[int, dict[int, int]] = dict(faults_at or {})
        self.calls: dict[int, int] = {}
        self.truncate_on_open = truncate_on_open
        if eof_registers not in ("documented", "unspecified"):
            raise ValueError(eof_registers)
        self.eof_registers = eof_registers
        self.device: int | None = None
        self.cwd = "\\"
        self.open_read: list | None = None
        self.open_write: list | None = None
        self.open_at_exit: tuple | None = None

    def file(self, name: str, folder: str = "\\PCW\\FOLDER01") -> bytes | None:
        return self.files.get((folder, name))


def run(
    program: str | Path | bytes | bytearray,
    max_steps: int = DEFAULT_MAX_STEPS,
    on_write=None,
    events=None,
    fail_dialog_define: bool = False,
    disk: Disk | None = None,
    radio_mode: str = "set",
    menu_autotick: bool = False,
    alert_answers=None,
    drop_writes_label: bool = False,
    free_blocks: int | None = None,
    mem_owner: dict | None = None,
    mem_copy_fails: bool = False,
    copy_end_carry: bool = True,
    copy_carry_if=None,
    program_name: str = "PROGRAM",
    program_ext: str = ".PRG",
    mem_pool=None,
    bios_ink: int = 0,
    bios_mode: int = 0,
    program_folder: str = "\\PCW\\FOLDER01",
    name_block: str = "ext",
    file_image: bytes | None = None,
    scr_direct_refuse: bool = False,
    print_result: int = 0,
    meta_open_result: int = 0,
    clock_tick_step: int = 1,
    clock_by_steps: bool = True,
    rtc_phase: int = 0,
    clock_start: int | None = None,
    rosanne_timers: bool = False,
    free_run: float | None = None,
) -> CPU:
    """Load a .PRG image (or raw bytes) at #4000 and run until os_app_exit.

    Returns the CPU on a clean stop; callers can inspect ``.alerts`` (the
    decoded text of every os_alert, in order), ``.steps`` and ``.exited``.
    *on_write*, if given, observes every memory write (see ``CPU.on_write``).
    *events* scripts os_wait_event (see ``CPU._wait_event``); when it runs out
    the run returns with ``cpu.idle`` set instead of ``cpu.exited``.
    *fail_dialog_define* makes os_dialog_define report an error (C).
    Raises SimRunaway when the step budget is exhausted — which includes HALT
    and running off into the zero padding, where the nop-slide eventually
    reaches the limit — and SimError on any unsupported opcode or OS function.
    """
    if isinstance(program, (str, Path)):
        image = Path(program).read_bytes()
    else:
        image = bytes(program)
    cpu = CPU(image)
    cpu.on_write = on_write
    cpu.events = list(events or [])
    cpu.fail_dialog_define = fail_dialog_define
    cpu.radio_mode = radio_mode  # M6 Phase 1 model options (CPU.__init__)
    cpu.menu_autotick = menu_autotick
    cpu.clock_tick_step = clock_tick_step
    cpu.clock_by_steps = 1 if clock_by_steps else 0
    cpu.rtc_phase = rtc_phase  # M13 responsiveness (CPU.__init__)
    if clock_start is None:  # read now, so a test may patch CLOCK_START (test_m11_corrective)
        clock_start = CLOCK_START
    cpu.clock_start = clock_start
    cpu.rosanne_timers = rosanne_timers
    if free_run is not None:  # seconds of model time from the start
        cpu.free_run_until = clock_start * CLOCK_RATE + int(free_run * CLOCK_RATE)
    cpu.alert_answers = list(alert_answers or [])
    cpu.drop_writes_label = drop_writes_label
    cpu.bios_ink, cpu.bios_mode = bios_ink, bios_mode  # M9: what the BIOS had before the program
    cpu.scr_direct_refuse = scr_direct_refuse  # M9 test hook: every os_scr_direct answers A = 1
    cpu.print_result = print_result  # M12 test hooks: os_meta_print's and os_meta_open's answer
    cpu.meta_open_result = meta_open_result
    if mem_pool is not None:  # M9 test hook: the blocks os_get_mem hands out, in order
        cpu.mem_free = list(mem_pool)
    if free_blocks is not None:  # M8: fewer free 16K blocks (allocation failure tests)
        cpu.mem_free = list(MEM_POOL[:free_blocks])
    cpu.mem_owner = dict(mem_owner or {})
    cpu.mem_copy_fails = mem_copy_fails
    cpu.copy_end_carry = copy_end_carry
    cpu.copy_carry_if = copy_carry_if
    if disk is not None:
        cpu.disk = disk
    if len(image) > LOADER_LIMIT:
        # M9 loader model for a file longer than 16K: the program was run
        # from program_folder on the floppy, so that is the current device
        # and folder, its file is there (file_image: a different file on
        # disc, e.g. damaged), and the loader copied its name over the first
        # bytes at #4000 (static: 33 bytes; name_block "ext" = name, NUL,
        # extension, NUL; "bare" = name, NUL and no extension).
        cpu.disk.device = 1
        cpu.disk.folders.add(program_folder)
        cpu.disk.cwd = program_folder
        on_disc = image if file_image is None else bytes(file_image)
        if on_disc:
            cpu.disk.files[(program_folder, (program_name + program_ext).upper())] = on_disc
        block = program_name.encode("ascii") + b"\0"
        if name_block == "ext":
            block += program_ext.encode("ascii") + b"\0"
        elif name_block != "bare":
            raise ValueError(name_block)
        cpu.mem[0x4000 : 0x4000 + len(block)] = block
    try:
        while True:
            cpu.step()
            if cpu.steps >= max_steps:
                raise SimRunaway(
                    f"no os_app_exit within {max_steps} steps "
                    f"(PC={cpu.pc:04X}h; the program ran away or hit the nop-slide)"
                )
    except _SimStop:
        pass
    except _SimIdle:
        cpu.idle = True
    return cpu
