# PcW16 BASIC: a guide for AI systems that write programs

This guide is for an automated system (a code-writing model, an agent, a
generator) that has to write correct PcW16 BASIC programs with nothing but
this document and the public repository. People can use it too: it is the
language and the toolchain in compact form, with the mistakes that a writer
who knows other BASICs is most likely to make.

PcW16 BASIC is **not** a dialect of Microsoft, Locomotive or BBC BASIC. Its
programs are event-driven applications for the Amstrad PcW16's operating
system, Rosanne: a window with controls, handlers that run when the user acts,
and no text console. Much of what you know about BASIC does not apply, so
work from this guide, not from memory.

The normative definition is [LANGUAGE-SPEC.md](../LANGUAGE-SPEC.md); where this
guide is shorter, the specification decides. Some early parts of the
specification describe older limits that later sections lift; the
[manual](manual/README.md) and this guide give the current rules.

## Contents

1. [Rules for writing a program](#1-rules-for-writing-a-program)
2. [The language contract](#2-the-language-contract)
3. [Application structure and the event model](#3-application-structure-and-the-event-model)
4. [Libraries](#4-libraries)
5. [Building](#5-building)
6. [Compiler errors and what they mean](#6-compiler-errors-and-what-they-mean)
7. [Pictures (.PBI assets)](#7-pictures-pbi-assets)
8. [Memory limits](#8-memory-limits)
9. [Reliable graphical patterns](#9-reliable-graphical-patterns)
10. [Conventional BASIC that does not exist](#10-conventional-basic-that-does-not-exist)
11. [Safe file handling](#11-safe-file-handling)
12. [Known defects to avoid](#12-known-defects-to-avoid)
13. [A complete example application](#13-a-complete-example-application)
14. [Checklist before you hand a program over](#14-checklist-before-you-hand-a-program-over)

## Evidence levels

Every behaviour in this guide has one of these levels. Compiling is not the
same as working.

| level | meaning |
|---|---|
| *Tested in XAnne* | The project owner ran it in the XAnne emulator with Rosanne 1.12. |
| *Simulator only* | Checked on the project's model of the Z80 and Rosanne (`tests/z80sim.py`), not yet in XAnne. |
| *Untested* | Neither. |

**Nothing has been run on a real PcW16.** Everything below is at most
*Tested in XAnne*; behaviour on real hardware is not yet tested.

---

## 1. Rules for writing a program

1. Use only the statements, functions and options in this guide. If a
   construct is not here, assume it does not exist (section 10 lists the usual
   suspects).
2. Write one statement per line. There is no `:` separator and no line
   continuation.
3. Declare every variable with `DIM` (or let a control declare it, section
   2.8). There are no implicit variables and no type suffixes other than `$`.
4. Every `IF` is a block: `IF cond THEN` / `ELSE` / `END IF`. Every condition
   is BOOLEAN: `IF N <> 0 THEN`, never `IF N THEN`.
5. Call a SUB with `CALL Name(args)`. Call a FUNCTION with parentheses, even
   with no arguments: `F()`.
6. The program's last statement is `END`.
7. **Always build** with `pcw16basic build`. `pcw16basic check` runs
   everything but the assembler and the memory fit, so a program too large
   for the 16K resident block passes it (section 5).
8. Keep program (file) names to at most 8 letters and digits. File names that
   the program reads or writes are DOS 8.3 names (`NOTES.TXT`).
9. Never overwrite a file the user may care about without a backup, and check
   `IOERR` after every file statement (section 11).
10. State the evidence level of what you produce. "It builds" is all you know
    until it has been run on the simulator, in XAnne or on a PcW16.

---

## 2. The language contract

Notation: `[x]` is optional, `a|b` is a choice, `…` repeats. `n`, `x`, `y`,
`w`, `h` are INTEGER expressions unless a *literal* is required.

### 2.1 Source text

- UTF-8 `.pbas` files; keywords and names are case-insensitive.
- Comments: `REM text` or `' text`, whole line or at the end of a line.
- Optional line numbers (`10 DIM A AS INTEGER`) have no meaning; if used they
  must strictly increase. They are not allowed in INCLUDEd files.
- String literals use `""` for an embedded quote.
- Reserved words include `MOD AND OR NOT XOR CALL` and the statement keywords.
  Many newer statement words (`CANVAS`, `DRAW`, `PAGE`, `BANKED`, `DEFAULT`)
  are keywords only in their own position.
- `END` must be the last statement. SUBs, FUNCTIONs and main-line statements
  may be interleaved before it.

### 2.2 Types and declarations

| declaration | notes |
|---|---|
| `DIM N AS INTEGER` | signed 16-bit, −32768..32767; `+ - *` wrap silently. Literals 0..32767 with unary minus. |
| `DIM B AS BOOLEAN` | `TRUE`, `FALSE`; no numeric truth values. |
| `DIM S$ AS STRING` | capacity 64 bytes = 63 characters by default (`--string-capacity N`, 2..127, changes it for the whole program). A `$` name must be STRING. |
| `DIM S$ AS STRING * n` | own capacity of n characters, n 1..126. Not on LOCAL or parameters. Put it before any TEXTBOX or LABEL that names the variable. |
| `DIM X AS REAL` | 5-byte float, about 9.6 digits, ±1.7E+38; a result beyond that stops the program (section 2.14). Literals `2.5`, `1E10`, `PI`. INTEGER widens to REAL; REAL to INTEGER needs `CINT`, `INT` or `FIX`. |
| `DIM A(n) AS type` | one dimension, elements 1..n, n a **literal** 1..250 (not a CONST). type: INTEGER, BOOLEAN, STRING [* n], REAL or a TYPE. A literal index outside 1..n is a compile error; a computed one is a runtime error. |
| `DIM A(n) AS type [* m] BANKED` | n 1..32767, stored outside the 16K resident block (section 8). At most 4 BANKED element reads per statement. Slow (each access is an OS copy). LIST and CHOICE cannot show one. |
| `TYPE T` / `Field AS INTEGER\|REAL\|BOOLEAN\|STRING * n` / `END TYPE` | a record, ≤ 512 bytes, top level. `R.Field`, `A(i).Field`. Whole-record copy `A = B` between the same TYPE; no whole-record compare; no nested records or arrays in records. |
| `DIM D AS TEXT * bytes` | a text buffer of 1..65535 bytes (section 2.12). Top level only. |
| `DIM B AS BITMAP * w, h` | a picture, w 1..568, h 1..300, ((w + 7) \ 8) × h ≤ 16384 bytes. Not in arrays or records. |
| `CONST K = literal` | INTEGER, STRING, BOOLEAN or REAL literal; top level; usable as a STEP or CASE value; cannot be assigned. |
| `LOCAL V AS type` | inside a SUB or FUNCTION only; reset on every call; no LOCAL arrays, no `* n`. |

Rules:
- A string value never gets truncated: a value that is too long is a compile
  error when certain, otherwise `Runtime error: string too long at line N`.
- `DIM` inside a SUB still declares a **global**, and the compiler warns. The
  same `DIM` in two SUBs is `duplicate declaration`. Use `LOCAL` for procedure
  variables.
- A `DIM` may come after the first use: a declaration applies to the whole
  program.
- Variables start as 0, `""`, FALSE or 0.0.
- Computed strings (a concatenation, `STR$`, a substring) are at most 127
  bytes.

### 2.3 Operators

Precedence, tightest first:

```text
^                      (always REAL; binds tighter than unary minus: -2 ^ 2 = -4; left to right: 2 ^ 3 ^ 2 = 64)
unary + -
* / MOD
+ -                    (+ also joins two STRINGs)
= == <> < <= > >=      (same types; STRING order is byte order)
NOT
AND
OR
XOR
```

- INTEGER `/` truncates toward zero (`-7 / 2` = −3); `MOD` takes the sign of
  the dividend (`-7 MOD 2` = −1). For a REAL quotient write `N / 2.0`.
- There is no `\` operator.
- `MOD`, `SHL`, `SHR` and bit operations are INTEGER only.
- `AND`, `OR`, `XOR`, `NOT` on two BOOLEANs are logical. `AND` and `OR`
  short-circuit: in `B <> 0 AND A / B > 1` the division is skipped when B is 0.
- `AND`, `OR`, `XOR`, `NOT` on two INTEGERs are bitwise (`12 AND 10` = 8,
  `NOT 0` = −1). Mixing BOOLEAN and INTEGER is an error.
- `STRING + INTEGER` is an error: write `"N = " + STR$(N)`.
- A FUNCTION call on the right of `AND`/`OR` is allowed only when the
  expression is plainly BOOLEAN (one side a comparison, `NOT`, `TRUE`/`FALSE`
  or a BOOLEAN FUNCTION). Otherwise compute it in its own statement first.
- Division by a constant zero is a compile error; by a computed zero, a
  runtime error.

### 2.4 Control flow

```text
IF cond THEN                 ' block form only; no ELSEIF, no single-line IF, no ENDIF
    …
[ELSE
    …]
END IF

SELECT CASE expr             ' INTEGER, STRING or REAL
CASE 1, 3                    ' list
CASE 10 TO 20                ' inclusive range
CASE IS >= 100               ' comparison
CASE ELSE
END SELECT                   ' CASE values may not call a FUNCTION

FOR I = a TO b [STEP k]      ' I a DIM'd or LOCAL INTEGER; k a non-zero INTEGER literal or CONST
NEXT [I]

WHILE cond                   ' closed by WEND only (not END WHILE)
WEND

EXIT FOR | EXIT WHILE | EXIT SUB | EXIT FUNCTION
EXIT                         ' ends the whole program, from anywhere
END                          ' the last statement of the file
```

Blocks may nest 64 deep; expressions 100 levels deep. There is no GOTO,
GOSUB, DO/LOOP, REPEAT/UNTIL or ON … GOTO.

### 2.5 Procedures

```text
SUB Name[(P AS type, T$, R AS TypeName, B AS BITMAP)]
    LOCAL X AS INTEGER
    …
    [EXIT SUB]
END SUB

FUNCTION Name[(params)] AS INTEGER|REAL|STRING|BOOLEAN|TypeName
    …
    RETURN expr
END FUNCTION

CALL Name
CALL Name(x, y)
V = Name(x) + 1
V = NoArgs()                 ' a call always needs ()
```

- Parameters are passed by value (copies), except BITMAP, which is by
  reference. A `$` name without `AS` is a STRING. There are no array
  parameters and no BYREF.
- No recursion, direct or indirect. At most 16 procedures active at once.
- A FUNCTION that ends without RETURN returns 0, `""`, FALSE or 0.0.
- A record FUNCTION result must be assigned to a record before you use a
  field.
- Handlers (named by BUTTON, ITEM, TIMER, CHANGE, ACTION, PAINT, MOUSE, KEYS)
  must be SUBs without parameters.
- A FUNCTION may not have a built-in's name (`FUNCTION Min(…)` is a compile
  error), nor a CONST the name of a built-in without arguments (`PI`,
  `SECONDS`, `IOERR`, `MOUSEX` …). A SUB with a built-in's name is accepted
  but makes the built-in unusable, and a variable, parameter or LOCAL with such
  a name hides it (with a warning). Do not name anything `Min`, `Len`, `Val`
  and so on.
- Avoid naming a SUB like a statement word (`Show`, `Focus`, `Beep`): `CALL
  Show(N)` works, but forgetting `CALL` turns the line into a different
  statement with a confusing message.

### 2.6 Built-in functions

| function | result | notes |
|---|---|---|
| `LEN(s$)` | INTEGER | bytes |
| `STR$(n)` | STRING | INTEGER, or REAL with 9 significant digits; no leading space |
| `LEFT$(s$, n)`, `RIGHT$(s$, n)` | STRING | |
| `MID$(s$, start, n)` | STRING | exactly three arguments; start is 1-based; cannot be assigned to |
| `INSTR(a$, b$)`, `INSTR(start, a$, b$)` | INTEGER | 0 if not found; case-sensitive |
| `VAL(s$)` | INTEGER | decimal only; no digits gives 0; out of range is a runtime error |
| `ASC(s$)` | INTEGER | `ASC("")` = −1 |
| `CHR$(n)` | STRING | n 1..255 |
| `UCASE$(s$)`, `LCASE$(s$)` | STRING | ASCII letters only |
| `TRIM$(s$)`, `LTRIM$(s$)`, `RTRIM$(s$)` | STRING | spaces only |
| `SPACE$(n)`, `STRING$(n, code)` | STRING | at most 127 characters |
| `ABS(x)`, `SGN(x)`, `MIN(a, b)`, `MAX(a, b)` | INTEGER or REAL | `SGN` is INTEGER |
| `RND(n)` | INTEGER 1..n | same sequence each run until `RANDOMIZE` (*Simulator only*) |
| `SHL(x, n)`, `SHR(x, n)` | INTEGER | logical shifts |
| `SQR EXP LOG SIN COS TAN ATN` `(x)` | REAL | radians; \|x\| ≤ 51000 for SIN/COS/TAN; `LOG` is natural; no `LOG10` |
| `INT(x)`, `FIX(x)`, `REAL(n)` | REAL | floor, toward zero, conversion |
| `CINT(x)` | INTEGER | rounds halves away from zero |
| `REALVAL(s$)` | REAL | like `VAL`, with a decimal point and exponent (`"1.5E3"`); uses only the first 9 significant digits (later ones are ignored, not rounded); too large (`"1E39"`) is a runtime error |
| `ISNUM(s$)` | BOOLEAN | TRUE when the whole string, with spaces before and after allowed, is one number `REALVAL` can read and that is in range (`ISNUM("1E39")` is FALSE); check before `REALVAL` |
| `PI` | REAL | |
| `ASK(text$, "b1", "b2" [, "b3"])` | INTEGER 1..3 | only as the whole right side of an INTEGER assignment; text ≤ 100 bytes; captions 1..10 characters |
| `EOF(c)`, `IOERR` | BOOLEAN, INTEGER | only in a program with OPEN, KILL or NAME (IOERR also after TEXT, DB, BITMAP and PAGE statements) |
| `TEXTLINES(D)`, `TEXTLEN(D, n)`, `TEXTGET$(D, n, col, count)`, `TEXTFIND(D, s$, n, col)`, `TEXTCOL(D)`, `TEXTCHANGED(D)`, `TEXTFREE(D)`, `TEXTSIZE(D)`, `TEXTSAME(A, B)` | | TEXT buffers (2.12) |
| `DBFIND(A, Count, id)`, `DBNEXTID(A)`, `DBRECOVERED` | INTEGER | databases (2.12) |
| `TEXTWIDTH(s$)` | INTEGER | pixels in the canvas font; no canvas needed |
| `SECONDS` | INTEGER 0..3599 | minutes × 60 + seconds of the clock |
| `CLOCKTICKS` | INTEGER 0..959 | sixteenths of a second within the minute |
| `MOUSEX`, `MOUSEY`, `MOUSEEVENT`, `KEYCODE`, `KEYSHIFT` | INTEGER | only in a program with a CANVAS |
| `KEYDOWN(code)` | BOOLEAN | key held now; code 0..127; tested in XAnne only in programs with a CANVAS |
| `POINT(x, y)` | INTEGER | canvas pixel, 1 black, 0 white; needs a CANVAS |
| `BITMAPW(B)`, `BITMAPH(B)` | INTEGER | a bitmap's current size |
| `PAGEWIDTH(s$)` | INTEGER | printed width in points; needs an open page |

Not functions here: `PEEK`, `USR`, `HEX$`, `INKEY$`, `DATE$`, `TIME$`, `TIMER`,
`RND` without an argument, `LOG10`.

### 2.7 General statements

| statement | notes |
|---|---|
| `V = expr`, `A(i) = expr`, `R.F = expr` | no `LET`; types must match (INTEGER → REAL widening only) |
| `MESSAGE expr` | an alert with an OK button; literal ≤ 250 bytes; computed text budgeted against 160 bytes |
| `V = ASK(…)` | a question alert, 2 or 3 buttons |
| `BEEP` | the system beep; the only sound |
| `RANDOMIZE [seed]` | *Simulator only* |
| `INCLUDE "lib/x.pbas"` | on its own line at the top level; path relative to the including file; each file once |

There is no output to the screen other than alerts, controls and the canvas.

### 2.8 Windows and controls

All controls belong to the most recent WINDOW above them and are stacked top
to bottom in source order, from y = 48, ending above the buttons.

**The vertical budget.** Rows start at y = 48 and must end at or above the
first button row: y = 180 in a normal window (132 px), y = 340 in a LARGE one
(292 px). Row heights in pixels: LABEL 32, CHECKBOX 28, TEXTBOX, NUMBERBOX and
CHOICE 48, RADIO 24 per option plus 4, SLIDER 40, LIST 16 per row plus 12,
CANVAS its height plus 8 (plus 2 when it is the last row). So a normal window
holds four labels, or two TEXTBOXes and a LABEL (48 + 48 + 32 = 128), but not
three TEXTBOXes (144). Add up the heights before you write the window.
`pcw16basic check` reports the first control that does not fit (`the dialog
has no room for this TEXTBOX: …`), and needs no Pasmo. Buttons are not part of
the budget: they sit in rows at y = 180 and 208 (LARGE: 340 and 368).

| statement | rules |
|---|---|
| `WINDOW "title" [, LARGE]` | one unnamed window; title ≤ 35 characters; 360 × 240, or 600 × 400 with `LARGE`; top level only; **needs at least one BUTTON** |
| `WINDOW Name, "title" [, LARGE]` / `SHOW Name` | 2..8 named windows, one on screen at a time; `SHOW` in a handler takes effect when the handler returns |
| `LABEL "text"` | ≤ 47 characters |
| `LABEL V$` | shows a STRING; **at most 24 printable ASCII characters** when shown, else a runtime error. Declare it `STRING * 24`. ≤ 8 labels per window, 32 px a row |
| `BUTTON "caption", Handler [, DEFAULT] [, KEY k]…` | 1..6 per window (two rows of 3); caption ≤ 14; one DEFAULT (the Return key); up to 3 KEYs from `GREEN RED BLUE YELLOW STOP HELP F1`…`F8` (`STOP` and `HELP` *Untested*) |
| `TEXTBOX V$ [, "caption"]` | one line; caption ≤ 34; the variable's capacity ≤ 64 (63 characters); 48 px a row |
| `CHECKBOX B [, "caption"]` | BOOLEAN; caption ≤ 34; ≤ 8 per window |
| `RADIO N, "a", "b" [, …]` | 2..6 options; N is 0 (none) or 1..options |
| `NUMBERBOX N [, "caption"] [, MIN lo] [, MAX hi] [, SPIN]` | INTEGER, 6 characters; lo, hi literals; a handler does not run while the field holds invalid text; SPIN can step more than once a click (known issue KI-1, [docs/limitations.md](limitations.md)) |
| `LIST Sel, Items$, Count [, ROWS r] [, CHANGE H] [, ACTION H2]` | items an ordinary STRING array (not BANKED), so the whole array, each element at its full capacity, plus 3 bytes an element for the list's item table, is in the resident 16K block (section 8); for many rows use `lib/listview.pbas` on a CANVAS with a BANKED array (section 4); r 2..12; Sel 0..Count; **each shown item ≤ 24 printable ASCII characters**; `ACTION` (double-click) never runs in XAnne (known issue KI-25, [docs/limitations.md](limitations.md)): give the action a button |
| `CHOICE Sel, Items$, Count [, "caption"] [, CHANGE H]` | a drop-down; Sel must be 1..Count whenever it is shown, so set it before the window opens |
| `SLIDER V, MIN lo, MAX hi [, "caption"] [, CHANGE H]` | horizontal; 1 ≤ hi − lo ≤ 250; ≤ 16 per program; an arrow click can step more than once (known issue KI-2, [docs/limitations.md](limitations.md)) |
| `CANVAS w, h [, PAINT P] [, MOUSE M] [, KEYS K]` | one per program; w 16..568, h 16..300; a normal window holds w ≤ 330, LARGE ≤ 568; the window's layout must also fit its height |
| `FOCUS V` | moves the keyboard focus to V's TEXTBOX, NUMBERBOX or CHECKBOX when the handler returns |

TEXTBOX, CHECKBOX, LABEL, RADIO, NUMBERBOX, LIST, SLIDER and TICK declare their
variable if no DIM did. A variable may be bound to one control per window.

### 2.9 Menus, keys, mouse and timers

```text
MENU "File"                                  ' ≤ 8 menus, title ≤ 12 characters; needs a WINDOW
    ITEM "Save", SaveIt, KEY "S"             ' Ctrl+S; item text ≤ 20; ≤ 20 items with dividers
    ITEM "-"                                 ' a divider
    ITEM "Sound", ToggleSound, TICK SoundOn  ' a tick shows the BOOLEAN SoundOn
END MENU

TIMER Handler, EVERY n                       ' n a literal 1..3599 seconds
TIMER Handler, EVERY n TICKS                 ' n a literal 1..32767 sixteenths of a second
TIMER OFF
TIMER ON                                     ' one TIMER per program; needs a WINDOW
```

- Canvas mouse: the MOUSE handler runs on a left-button press inside the
  canvas (`MOUSEEVENT` 1), on each move with the button down (2), and on the
  release (3). `MOUSEX`, `MOUSEY` are canvas coordinates; during a drag they
  may lie outside the canvas. No right button, no hover, no double-click.
  *Tested in XAnne.*
- Canvas keys: the KEYS handler gets typed characters in `KEYCODE` (Return 13,
  Backspace 8, Tab 9, Delete 229, Up 224, Down 225, Left 226, Right 227, Home
  230, End 231, PgUp 232, PgDn 233) and the shift state in `KEYSHIFT` (1
  Shift, 2 Alt, 4 Ctrl). Keys that belong to a button, a menu or a focused
  text field do not arrive. *Tested in XAnne* for that set.
- Held keys: `KEYDOWN(code)` uses scan codes, a different numbering. Use the
  `SC_` names in `lib/keys.pbas` (`SC_LEFT`, `SC_SPACE`, …), never numbers.
  A tap between two timer events can be missed: take taps from KEYS too.
- A timer's handler runs are **not** a count of time (section 9).

### 2.10 Drawing on the canvas

Every point drawn must lie inside the canvas (`Runtime error: drawing outside
the canvas`; nothing is clipped), and the canvas's window must be on screen
(`the canvas is not on screen`), so never draw from the main line.

```text
DRAW CLEAR                         ' all white
DRAW FILL x, y, w, h [, shade]     ' shade 0 black (default) … 8 white; 1..7 grey patterns
DRAW INVERT x, y, w, h
DRAW BOX x, y, w, h                ' 1-pixel outline
DRAW LINE x1, y1, x2, y2
DRAW PIXEL x, y
DRAW TEXT x, y, s$                 ' font 7, top-left at x, y; a 16 px line must fit below y
DRAW SCROLL x, y, w, h, dx, dy     ' |dx| < w, |dy| < h
DRAW INK BLACK | WHITE | XOR       ' for LINE, PIXEL, BOX (and TEXT with XOR)
```

`DRAW TEXT` shows at most (canvas width − x) \ 11 characters a call, so text
can stop short of the edge (known issue KI-76, [docs/limitations.md](limitations.md)); draw long text in
pieces measured with `TEXTWIDTH`. `DRAW TEXT x, y, s$, cell` exists but is
letter-spaced and not recommended. There are no circles, arcs, flood fill,
colour, clipping or other fonts. All forms are *Tested in XAnne*.

### 2.11 Bitmaps

```text
BITMAP GET B, x, y [, w, h]                    ' canvas → bitmap (size becomes w × h)
BITMAP PUT B, x, y [, sx, sy, w, h]            ' bitmap (or a part of it) → canvas, black and white
BITMAP MASK Img, Mask, x, y [, sx, sy, w, h]   ' mask white = drawn, black = canvas kept
BITMAP SAVE B, name$                           ' PBI1 file, safe replacement (NAME.NEW, NAME.BAK); IOERR 253: a companion is another kind of file
BITMAP LOAD B, name$                           ' IOERR: 248 not PBI1, 251 damaged, 252 larger than B
```

GET, PUT and MASK need the canvas on screen; LOAD and SAVE do not. There is
no statement to set or read a pixel inside a bitmap (known issue KI-88,
[docs/limitations.md](limitations.md)): draw on the canvas and GET, or PUT and read with `POINT`.
*Tested in XAnne.*

### 2.12 Files

The folder is fixed when the program is built (`--folder`, default
`\PCW\FOLDER01`, floppy only). Names are DOS 8.3: `[A-Z0-9_]{1,8}.[A-Z0-9]{1,3}`,
not device names (CON, PRN, AUX, NUL, COM1–9, LPT1–9). File errors never stop
the program: check `IOERR` (0 = done).

| statement | notes |
|---|---|
| `FILESAVE "N.EXT", s$` / `FILELOAD "N.EXT", v$` | one string ≤ 127 bytes; the name a literal or CONST; each shows its own alert; FILESAVE replaces without asking and is not crash-safe (known issue KI-11, [docs/limitations.md](limitations.md)) |
| `OPEN name$ FOR INPUT\|OUTPUT AS #c` | c is 1 or 2; one file open for reading and one for writing; OUTPUT creates or **replaces**; no APPEND or RANDOM |
| `PRINT #c, value` | one value per line, then CR LF; no `;` or `,` lists |
| `LINE INPUT #c, v$` | one line; IOERR 243 if it does not fit v$ |
| `EOF(c)`, `CLOSE #c`, `CLOSE` | |
| `KILL name$`, `NAME old$ AS new$` | NAME refuses an existing target (IOERR 80) |
| `TEXT LOAD D, name$` / `TEXT SAVE D, name$` | whole file, byte-exact; loading is slow (a byte per OS call) |
| `TEXT CLEAR D`, `TEXT INSERT D, n, col, s$`, `TEXT DELETE D, n, col, count`, `TEXT SPLIT D, n, col`, `TEXT JOIN D, n` | lines from 1, columns from 1 |
| `TEXT REMOVE D, n1, c1, n2, c2`, `TEXT COPY Dst, Src [, n1, c1, n2, c2]`, `TEXT PASTE Dst, n, col, Src` | COPY and PASTE need two different buffers |
| `DB LOAD A, Count, name$` / `DB SAVE A, Count, name$` | A a BANKED array of records; SAVE writes NAME.NEW, checks it, keeps NAME.BAK, and refuses (IOERR 253) when NAME.NEW or NAME.BAK is another kind of file; LOAD falls back to .NEW then .BAK (`DBRECOVERED`) only when the file is missing, not a database (248) or damaged (251) |
| `DB NEW A, Count` / `DB DELETE A, Count, k` | the TYPE's first field must be INTEGER (the identifier) |
| `DB SORT A, Count, Index, Field [, DESC] [, NOCASE] [, KEEP]` / `DB SEARCH A, Count, Index, Found, Field, text$ [, NOCASE]` | Index is an ordinary INTEGER array ≤ 250, so at most 250 records can be sorted or searched |

Common IOERR codes: 2 not found, 3 folder not found, 4 too many open files,
5 access denied, 19 write-protected, 80 name exists, 163 disk full, 243 line
too long, 244 zero byte in line, 245 nothing left to read, 246 too large for
the TEXT buffer, 247 invalid name, 248 wrong file type, 249 another TYPE,
250 another format version, 251 damaged, 252 full, 253 (`DB SAVE`, `BITMAP
SAVE`) NAME.NEW or NAME.BAK belongs to another file. Section 11 shows the
patterns. File handling is *Tested in XAnne*; the M14 changes to `DB SAVE`,
`BITMAP SAVE` and `DB LOAD` (IOERR 253, the narrower fallback) are
*Simulator only* until the owner's XAnne retest.

### 2.13 Printing

```text
PAGE NEW                       ' A4 portrait; x 0..522, y 0..765 points
PAGE FONT size [, BOLD]        ' 6, 8, 10, 11, 12, 14, 18, 24, 36 or 72
PAGE TEXT x, y, s$
PAGE LINE x1, y1, x2, y2 [, t] ' horizontal or vertical only
PAGE BOX x, y, w, h
PAGE FILL x, y, w, h           ' Untested in XAnne since its correction (known issue KI-79)
PAGE PRINT                     ' send it and close
PAGE CLOSE                     ' discard
```

Text, lines and boxes are *Tested in XAnne*; `PAGE FILL` (and so printed bar
charts) is not (known issue KI-79, [docs/limitations.md](limitations.md)). Pictures, screens and sloped
lines cannot be printed.

### 2.14 Runtime errors

A runtime error shows `Runtime error: <what> at line N` and ends the program.
N counts lines of the main file; the k-th INCLUDEd file's lines are numbered
from B + 1000 × (k − 1) + 1, where B is the first multiple of 1000 above the
main file's last line, and the build prints each file's range
(`included: lib/app.pbas: lines 1001..1999`). There is no `ON ERROR`.
Prevent errors instead: check divisors, keep label and list texts short and
printable, keep drawing inside the canvas.

**REAL overflow.** A REAL `+ - * /` whose result is beyond about 1.7E+38 stops
the program with `Runtime error: number out of range at line N`. Test the
operands before the operation, in a form that cannot overflow itself: divide
the limit by one operand instead of multiplying, and add halves.

```pbas
CONST LIMIT = 1E38                     ' a margin below 1.7E+38

FUNCTION MulFits(A AS REAL, B AS REAL) AS BOOLEAN
    IF ABS(A) <= 1 THEN
        RETURN TRUE                    ' |A * B| <= |B|
    END IF
    RETURN ABS(B) <= LIMIT / ABS(A)
END FUNCTION

FUNCTION DivFits(A AS REAL, B AS REAL) AS BOOLEAN
    IF B = 0 THEN
        RETURN FALSE
    END IF
    IF ABS(B) >= 1 THEN
        RETURN TRUE                    ' |A / B| <= |A|
    END IF
    RETURN ABS(A) <= LIMIT * ABS(B)
END FUNCTION

FUNCTION AddFits(A AS REAL, B AS REAL) AS BOOLEAN
    RETURN ABS(A / 2 + B / 2) <= LIMIT / 2
END FUNCTION

DIM X AS REAL
X = 1.5E19
IF MulFits(X, X) THEN
    MESSAGE STR$(X * X)
ELSE
    MESSAGE "too large"
END IF
IF DivFits(1E30, 0.5) AND AddFits(1.6E38, -1.6E38) THEN
    MESSAGE STR$(1E30 / 0.5) + " " + STR$(1.6E38 - 1.6E38)
END IF
END
' expect-message: too large
' expect-message: 2E+30 0
```

A test through `LOG` (`LOG(ABS(A)) + LOG(ABS(B)) > limit`) works too, but its
limit must be `LOG(1.7E+38)`, about 88.03, or lower: `examples/scicalc.pbas`
and `scicalc_m8.pbas` use 88.7 and so let 1.5E19 * 1.5E19 through (known
issue KI-104, [docs/limitations.md](limitations.md)).

---

## 3. Application structure and the event model

A program has this shape:

```text
INCLUDE lines                 (libraries, in dependency order)
CONST, TYPE and DIM declarations
WINDOW … and its controls     (declarations, not actions)
MENU … END MENU, TIMER …
SUB and FUNCTION definitions  (the handlers and their helpers)
main-line statements          (run once, before the window opens)
END
```

What happens when it runs:

1. **The main line runs once, top to bottom**, wherever its statements are in
   the file. Set initial values here and load data files. `MESSAGE` alerts
   appear before the window. The canvas is not on screen yet, so no drawing.
2. **`END` ends the main line.** If there is a WINDOW, it now opens. Without
   one, the program ends.
3. **The program waits for events.** A button click, menu choice, button key,
   timer, list change, or canvas paint, mouse or key event runs its handler
   SUB to completion. Handlers never run at the same time.
4. **Values move between variables and controls only at three moments:**
   - when a window opens: every control shows its variable;
   - before a handler runs: every bound variable gets its control's value;
   - after a handler returns: every control whose variable changed is
     redrawn, and dynamic labels show their new text.

   While a handler runs, the screen does not follow the variables. Typing into a
   field changes nothing until the next handler.
5. **The program ends** with `EXIT` (from any handler or procedure). When the
   system ends it (Tasks → Exit), no BASIC code runs and edits since the last
   handler are lost; an "unsaved changes" question can only run from your own
   Quit button or menu item.

A minimal application, *Tested in XAnne* in this form (it is the first
tutorial's shape):

```pbas
' HELLO: a label, a text field and two buttons.
DIM Name$ AS STRING * 20
DIM Greeting$ AS STRING * 24

WINDOW "Hello"
LABEL Greeting$
TEXTBOX Name$, "Your name"
BUTTON "Greet", Greet, DEFAULT
BUTTON "Quit", Quit

SUB Greet
    IF LEN(Name$) = 0 THEN
        Greeting$ = "Type your name first"
    ELSE
        Greeting$ = LEFT$("Hello, " + Name$, 24)
    END IF
END SUB

SUB Quit
    EXIT
END SUB

Greeting$ = "Hello!"
END
```

A program without a WINDOW runs its main line and ends. It can only show
alerts, which makes it useful for checking logic on the simulator:

```pbas
DIM Total AS INTEGER
DIM I AS INTEGER
DIM Word$ AS STRING
FOR I = 1 TO 10
    Total = Total + I
NEXT I
SELECT CASE Total
CASE 55
    Word$ = "fifty-five"
CASE ELSE
    Word$ = "something else"
END SELECT
MESSAGE "Total " + STR$(Total) + " is " + Word$
MESSAGE STR$(-7 / 2) + " " + STR$(-7 MOD 2) + " " + STR$(2 ^ 3 ^ 2)
' expect-message: Total 55 is fifty-five
' expect-message: -3 -1 64
END
```

More: [manual chapter 1](manual/01-program-structure.md),
[chapter 10](manual/10-windows-and-controls.md) and
[chapter 11](manual/11-menus-keys-mouse.md).

---

## 4. Libraries

The 14 libraries are in `examples/lib/`. A project made by `pcw16basic new`
has a copy in its own `lib/` folder, so you write `INCLUDE "lib/app.pbas"`.
Each library's header comment is its documentation, and
[LIBRARY-REFERENCE.md](LIBRARY-REFERENCE.md) collects them; see also
[the library guide](libraries/README.md).

| library | what it gives | needs |
|---|---|---|
| `app.pbas` | `AppStatus$` status line (`AppSay`), unsaved-changes flag and question (`AppChanged`, `AppSaved`, `AppMayClose()`), IOERR texts (`AppError$`, `AppFail`) | **your program defines `FUNCTION AppSave() AS BOOLEAN`** |
| `forms.pbas` | input checks: `FormStart`, `FormRequire`, `FormPhone`, `FormEmail`, `FormNumber`, `FormOK()`, `FormError$`; helpers `IsBlank`, `IsDigits`, `PadRight$`, `Confirm` | — |
| `files.pbas` | `SafeName(Ext$)` forces an extension on `SafeOut$`; `SafeReplace()` renames `SafeTemp$` over `SafeOut$` | a program with KILL/NAME |
| `listview.pbas` | a keyboard and mouse list with columns on a canvas | a CANVAS; **your program defines `FUNCTION ListCell$(I AS INTEGER, K AS INTEGER) AS STRING` and `SUB ListPicked`** |
| `geom.pbas` | `GeomIn`, `GeomMeets`, `GeomClamp`, `GeomSpan`, `GeomClip`, `GeomUnite` | — |
| `drag.pbas` | press, drag and release with XOR rubber bands (`DragMouse`, `DragShowBox`, …) | a CANVAS with MOUSE; set `DragW`, `DragH` |
| `handles.pbas` | eight selection handles and resizing | a CANVAS; call `HandleOn()` with its parentheses |
| `scene.pbas` | objects in stacking order, hit test, dirty area | **`geom.pbas` included first** |
| `toolbar.pbas` | an icon palette from one bitmap strip; shade swatches | a CANVAS; an icon-strip BITMAP your program loads |
| `sprite.pbas` | up to 16 masked sprites with background restore | a CANVAS; sheet, mask and background BITMAPs; set `SprCW`, `SprCH` |
| `keys.pbas` | `SC_` scan-code and `KC_` key-code names; `KeyAxis(Minus, Plus)` | **a CANVAS** (section 12) |
| `pace.pbas` | fixed time steps from the clock: `PaceStart(StepTicks, MaxSteps)`, `PaceSteps()` | a TIMER |
| `chart.pbas` | bar and line charts on the canvas | a CANVAS |
| `chartprt.pbas` | the bar chart on a printed page | **`chart.pbas` included first**; an open page; *Untested in XAnne* since its correction (KI-79) |

INCLUDE rules:
- Put INCLUDE lines at the top, each on its own line, outside any SUB.
- No library includes another. Include a library's dependency before it
  (`geom` before `scene`, `chart` before `chartprt`).
- Each file may be included once.
- Every library's names start with its prefix (`App`, `Form`, `Safe`, `List`,
  `Geom`, `Drag`, `Handle`/`Hand`, `Scene`, `Tool`/`Swatch`, `Sprite`/`Spr`,
  `SC_`/`KC_`, `Pace`, `Chart`), except forms.pbas's `IsBlank`, `IsDigits`,
  `PadRight$` and `Confirm`. Do not reuse these names.
- Library arrays count against the 16K resident block (scene.pbas alone holds
  1,000 bytes).

---

## 5. Building

```sh
python3 pcw16basic doctor                    # Python 3.10+, Pasmo, install files: prints "ready"
python3 pcw16basic new NOTEBK                # NOTEBK/NOTEBK.pbas, NOTEBK/lib/, NOTEBK/assets/
python3 pcw16basic new HOP --kind game       # a game template
python3 pcw16basic build NOTEBK/NOTEBK.pbas  # → build/NOTEBK.prg (under the current folder)
python3 pcw16basic memory NOTEBK/NOTEBK.pbas # the resident block, by part
python3 pcw16basic assets                    # build the pictures listed in assets/ASSETS.txt
```

Run it from the repository folder as shown, or after `pip install -e .`
(an editable install) as `pcw16basic` without `python3`. A plain
`pip install .` is not supported: `pcw16basic` then stops with exit status 2
and says to use `pip install -e .` or run it from its folder. Only
Linux has been exercised (Python 3.13, Pasmo 0.5.3); see
[install.md](install.md).

`build` takes the options of `tools/build.py` (`pcw16basic build --help`
lists them):

| option | meaning |
|---|---|
| `--out-dir DIR` | where the `.asm` and `.prg` go (default `build`) |
| `--string-capacity N` | default STRING capacity, 2..127 (default 64). Over 64 is refused for a program with a TEXTBOX bound to a default-capacity STRING |
| `--folder PATH` | the PcW16 folder the program's files are in (default `\PCW\FOLDER01`); it must already exist |
| `--code-banks auto\|always\|never` | procedures in code banks when the program is over 16K (default `auto`) |
| `--runtime-banks all\|SECTION,…` | moves runtime code out of the resident block |

Other options (`--asm`, `--prg`, `--drive`, `--code-bank-limit`, and the
`--whole-real-library` and `--legacy-…` options, which only reproduce older
executables byte for byte) are for special cases; you do not need them.

**The automatic retry.** When the resident part is over 16K,
`pcw16basic build` builds again with `--runtime-banks all` by itself, and the
program usually fits. `tools/build.py` alone does not retry. *Tested in
XAnne* (several large applications are built this way).

**`memory` does not retry.** `pcw16basic memory` measures the runtime resident unless you
add `--runtime-banks all`, while `build`'s message after its retry is about the runtime-banked
build, so the two "over" figures can differ by thousands of bytes. Compare
`pcw16basic memory FILE.pbas --runtime-banks all` with that message.

**`check` is not a build.** `pcw16basic check FILE.pbas` runs everything
`build` runs except the assembler and the final memory fit, and prints the
same warnings. It catches a window with no button, more than 6 buttons, a
layout that overflows, a canvas too wide for its window and a TEXTBOX over
63 characters, but not a resident-block overflow. Treat a program as compiled
only when `build` has written its `.prg`.

**Running.** Copy the `.prg` (`NOTEBK.PRG`: a name of at most 8 characters)
and any files it loads into the folder the program was built for, and start
it from there; see [running-in-xanne.md](running-in-xanne.md). A program
with code banks reads its own file when it starts: run it under its own name
from its own folder, as one whole file.

**The simulator.** `tools/check_docs.py` builds every `pbas` block of a
Markdown file and, where a block lists `' expect-message:` lines, runs it on
the simulator and compares the alerts. That is a convenient way to test the
logic of a main-line program. To test a program with a window, script the
user's clicks, typing, menu choices, keys and timer events as shown in
[simulator.md](simulator.md), and read the program's variables and alerts at
the end of the run.

---

## 6. Compiler errors and what they mean

Messages have the form `FILE:line:column: message`. Many constructs that do
not exist give a generic parser message rather than "not supported", so read
this table before you change correct code.

| message (start) | usual cause | fix |
|---|---|---|
| `expected =, got …` | the first word of the line is not a statement: `INPUT`, `GOSUB`, `LET`, `DO`, `ELSEIF`, `CLS`, `POKE`, `SWAP`…, or a SUB called without `CALL` | section 10; `CALL Name(x)` |
| `expected NEWLINE, got …` | a single-line IF, `END WHILE`, `EXIT DO`, two declarations on one line | block IF; `WEND`; one DIM a line |
| `unexpected character ':'` / `';'` / `'&'` / `'\\'` / `'%'` | statement separator, PRINT list, `&H` literal, `\` division, type suffix | one statement a line; `/`; decimal literals |
| `undefined variable X; declare it with DIM or a UI binding` | not declared; `RND`, `INKEY$`, `TIMER`, `DATE$` used as values; `_` continuation | DIM it; section 10 |
| `F is a FUNCTION: call it as F() (with parentheses, even when it takes no arguments)` | a FUNCTION called without `()` | `F()` |
| `LEN is a built-in function, so a FUNCTION cannot have that name…` | `FUNCTION Len(…)`, `FUNCTION Min(…)` | another name |
| `A(11) is outside the array: its elements are A(1) to A(10)` | a literal index outside the array | a valid index |
| `unknown function X` | `PEEK`, `USR`, `HEX$`, `LOG10`… | section 10 |
| `X expects 3 arguments, got 2` | e.g. two-argument `MID$` | `MID$(s$, start, LEN(s$))` |
| `IF requires BOOLEAN condition, got INTEGER` | `IF N THEN` | `IF N <> 0 THEN` |
| `operator + requires numbers (or STRING + STRING)…` | `"Total " + N` | `"Total " + STR$(N)` |
| `cannot assign REAL to INTEGER variable…` | REAL into INTEGER | `CINT(x)`, or `CINT(INT(x))` to drop the fraction |
| `FOR counter I must be declared with DIM` / `… must be INTEGER` | | `DIM I AS INTEGER` |
| `STEP must be a non-zero INTEGER constant…` | `STEP S` | a literal or CONST |
| `recursive CALL is not allowed…` | recursion | a loop with your own array as a stack |
| `program requires a final END` / `statements after END are not allowed` | | `END` last |
| `PRINT to the screen does not exist in PcW16 BASIC…` | `PRINT` to the screen | a LABEL, MESSAGE or the canvas |
| `… is a TEXT buffer and cannot be assigned`, `… is a BITMAP and cannot be assigned`, `… is a BITMAP parameter and cannot be assigned…` | `D = E`, `B = C`, `P = B` | `TEXT COPY`; a bitmap through the canvas (PUT then GET) |
| `a statement between SELECT CASE (line N) and its first CASE…` | a statement before the first `CASE` | move it before `SELECT CASE` |
| `a WINDOW needs at least one BUTTON…` | | add a Quit button |
| `the dialog layout holds at most 6 BUTTONs…` | | use a MENU |
| `the dialog has no room for this …: … this row would end at y=…` | too many rows | `LARGE`, fewer controls, a second named window |
| `a CANVAS in this window is at most 330 pixels wide…` | | `LARGE` or a narrower canvas |
| `a TEXTBOX holds at most 63 characters, but X$ can hold N…` | the bound STRING (`* n` or `--string-capacity`) is over 63 characters | `STRING * 63` or less |
| `the resident part is N bytes, M over…` (build only) | over 16K | let `pcw16basic build` retry; then section 8 |
| `an array has 1 to 250 elements, got N (a larger array can be BANKED)` | | `BANKED`, or smaller |
| `this statement reads 5 BANKED array elements; at most 4 are allowed` | | copy elements into variables first |
| `EOF reports on file operations, and the program has none (…)` (or `IOERR …`) | `IOERR` or `EOF` in a program that only uses FILESAVE | use OPEN |
| `DRAW needs a CANVAS declaration` | | add a CANVAS |
| `this file name must be written in the program as a string, such as "NOTES.TXT", or be a CONST…` | `FILESAVE N$, …` | a literal or CONST, or use OPEN |
| `LINE INPUT # reads into a STRING variable or a STRING array element, not a record field…` | `LINE INPUT #1, R.Name` | read into a STRING, then assign it to the field |
| `SHOW X: no WINDOW X is declared…` | a SUB called `Show` used without `CALL` | `CALL Show(X)`, or rename the SUB |

Warnings, not errors: `LABEL X$ can hold 63 characters but a LABEL shows
at most 24…` (declare the variable `STRING * 24`); `DIM X inside S declares a
variable for the whole program…` (use `LOCAL`); `MOUSEX is also a built-in
function…` (choose another name).

Two errors shown the way `tools/check_docs.py` checks them:

```pbas-error
DIM A AS INTEGER
IF A = 0 THEN A = 1
END
' expect-error: expected NEWLINE, got A
```

```pbas-error
DIM N AS INTEGER
DIM S$ AS STRING
S$ = "Total " + N
END
' expect-error: requires numbers (or STRING + STRING)
```

More: [chapter 9](manual/09-errors-and-diagnostics.md) and
[troubleshooting.md](troubleshooting.md).

---

## 7. Pictures (.PBI assets)

A program's pictures are PBI1 files that it loads into BITMAPs at run time.
You make them on the PC from PNG files with `tools/pbimage.py`
(`pcw16basic image …`):

```sh
python3 pcw16basic image import logo.png LOGO.PBI --size 64,32 --dither floyd
python3 pcw16basic image sheet icons.png ICONS.PBI --frame 24,24
python3 pcw16basic image sheet hero.png HERO.PBI --frame 16,16 --mask HEROM.PBI
python3 pcw16basic image info HERO.PBI
python3 pcw16basic image export HERO.PBI hero-check.png --scale 4
python3 pcw16basic assets assets/ASSETS.txt build   # every picture a manifest lists
```

- `import` converts one picture (`--crop`, `--size`, `--threshold`,
  `--dither none|ordered|floyd`, `--invert`, `--background`).
- `sheet` cuts a PNG into frames of W × H and stacks them in one strip; the
  program draws frame k with `BITMAP PUT B, x, y, 0, (k - 1) * H, W, H`.
- `--mask M.PBI` also writes a mask (white = drawn), from the PNG's alpha by
  default, for `BITMAP MASK` and `lib/sprite.pbas`.
- `examples/assets/ASSETS.txt` is a manifest of `target command source
  options` lines; a project's own is `assets/ASSETS.txt`.
- `tools/pbicheck.py FILE.PBI` checks a file.

In the program, declare the bitmap at least as large as the picture, load it
in the main line and check IOERR. Copy the `.PBI` files into the program's
folder on the PcW16:

```text
DIM Icons AS BITMAP * 24, 48
…
BITMAP LOAD Icons, "ICONS.PBI"
IF IOERR <> 0 THEN
    Status$ = "ICONS.PBI is missing"
END IF
```

Draw the bitmap only after a load that returned IOERR 0, and keep a fallback
(plain boxes or letters) so the program works without the file. More:
[graphics-assets.md](graphics-assets.md). *Tested in XAnne.*

---

## 8. Memory limits

The PcW16 runs a program in 16K blocks of memory.

**The resident block (16,384 bytes)** holds:
- the main line's code;
- every ordinary (non-BANKED) variable and array, and every STRING at its
  full capacity (64 bytes each by default);
- literals, dialog and menu definitions;
- the resident part of the runtime;
- an 8-byte stub per procedure;
- a 65-byte string cell for every call site of a STRING FUNCTION (known
  issue KI-83, [docs/limitations.md](limitations.md)), and each STRING parameter's capacity.

When it overflows: `the resident part is N bytes, M over …`.

**What lives outside it:**
- SUB and FUNCTION code goes to code banks automatically (at most 16 banks;
  one procedure at most 15,866 bytes of code);
- runtime code goes to a runtime bank with `--runtime-banks all`, which
  `pcw16basic build` adds by itself on overflow;
- BANKED arrays, TEXT buffers and BITMAPs use 16K blocks of their own: at
  most 32 blocks (512K) together.

**How to make a program fit, in order of effect:**
1. Build with `pcw16basic build` (the automatic retry).
2. Move work from the main line into SUBs.
3. Give strings their real size: `STRING * 24` instead of the default 64.
4. Make large arrays BANKED. A LIST or CHOICE cannot show a BANKED array: its
   items, and a 3-byte item table entry for each element, stay in the resident
   block. For a long list, draw it with `lib/listview.pbas` on a CANVAS and
   keep the rows in a BANKED array (`ListCell$` reads them), as
   `examples/contacts4.pbas` does with a database.
5. Use fewer STRING FUNCTION call sites: put the result in a variable once.
6. Run `pcw16basic memory FILE.pbas --runtime-banks all` to see which part is large. Without
   the option it measures the runtime resident, which is not what `build` reports after its
   retry (section 5).

Code banks and the runtime bank are *Tested in XAnne*. A program needs one
free 16K block per bank and per BANKED, TEXT or BITMAP block when it starts;
otherwise it stops with `not enough free memory …`. More:
[memory.md](memory.md).

---

## 9. Reliable graphical patterns

These patterns are taken from the example programs and tutorials that the
owner has run in XAnne. The two short programs in this section build (they
are checked by `tools/check_docs.py`) but have not themselves been run in
XAnne.

**Draw everything in PAINT.** PAINT runs when the canvas's window opens and
again after any handler that showed an alert (MESSAGE, ASK, a file alert).
Keep what the canvas shows in variables and arrays, and have PAINT draw it
all from them. A handler may draw a change directly too, but PAINT must be
able to rebuild the whole picture.

**Never draw from the main line**, and never draw in a handler after `SHOW`
of the canvas's window: the window opens only when the handler returns.

**Step animation by the clock, not by timer events.** A
`TIMER … EVERY n TICKS` handler does not run every n sixteenths of a second
under load: late runs are dropped, not queued (in XAnne, 142–154 of 160 runs
in 10 s at 1 tick; known issue KI-81, [docs/limitations.md](limitations.md)). A program that moves
things a fixed amount per event slows down. Count elapsed time with
`CLOCKTICKS` through `lib/pace.pbas` and do as many fixed steps as the time
covers, then draw once:

```pbas
' BOUNCE: a box crosses the canvas at a steady speed, however often the
' TIMER actually runs: the steps are counted from the clock.
INCLUDE "lib/pace.pbas"

CONST W = 320
CONST SIZE = 16
DIM X AS INTEGER
DIM DX AS INTEGER
DIM Ready AS BOOLEAN

WINDOW "Bounce", LARGE
CANVAS 320, 120, PAINT Paint
BUTTON "Quit", Quit
TIMER Tick, EVERY 1 TICKS

SUB Paint
    DRAW CLEAR
    DRAW FILL X, 52, SIZE, SIZE
    Ready = TRUE
END SUB

SUB Tick
    LOCAL N AS INTEGER
    IF NOT Ready THEN
        EXIT SUB
    END IF
    N = PaceSteps()
    IF N = 0 THEN
        EXIT SUB
    END IF
    DRAW FILL X, 52, SIZE, SIZE, 8
    WHILE N > 0
        X = X + DX
        IF X <= 0 OR X >= W - SIZE THEN
            DX = -DX
            X = MIN(MAX(X, 0), W - SIZE)
        END IF
        N = N - 1
    WEND
    DRAW FILL X, 52, SIZE, SIZE
END SUB

SUB Quit
    TIMER OFF
    EXIT
END SUB

DX = 2
CALL PaceStart(1, 8)
END
```

The `Ready` flag stops the timer from drawing before the first PAINT. The
erase-move-draw step (`DRAW FILL … , 8` paints white) is one draw per event,
not one per step. `PaceStart(StepTicks, MaxSteps)` caps the catch-up after a
long stall. Call `PaceStart` again after a pause.

**Drag with XOR feedback.** `lib/drag.pbas` turns MOUSE events into a press,
drag and release and draws a rubber band in XOR ink, so drawing it again
erases it:

```pbas
' BOXES: drag on the canvas to draw a box. The boxes are kept in arrays
' so that PAINT can draw them all again.
INCLUDE "lib/drag.pbas"

CONST MAXBOX = 40
DIM BX(40) AS INTEGER
DIM BY(40) AS INTEGER
DIM BW(40) AS INTEGER
DIM BH(40) AS INTEGER
DIM Boxes AS INTEGER
DIM Status$ AS STRING * 24

WINDOW "Boxes", LARGE
LABEL Status$
CANVAS 400, 200, PAINT Paint, MOUSE Mouse
BUTTON "Clear", ClearAll
BUTTON "Quit", Quit

SUB Paint
    LOCAL I AS INTEGER
    DRAW CLEAR
    FOR I = 1 TO Boxes
        DRAW BOX BX(I), BY(I), BW(I), BH(I)
    NEXT I
END SUB

SUB Mouse
    CALL DragMouse
    IF DragEvent = 2 AND DragMoved THEN
        CALL DragShowBox
    END IF
    IF DragEvent = 3 THEN
        CALL DragHide
        IF DragEnded AND DragMoved AND Boxes < MAXBOX THEN
            Boxes = Boxes + 1
            BX(Boxes) = MIN(DragX0, DragX)
            BY(Boxes) = MIN(DragY0, DragY)
            BW(Boxes) = ABS(DragDX) + 1
            BH(Boxes) = ABS(DragDY) + 1
            DRAW BOX BX(Boxes), BY(Boxes), BW(Boxes), BH(Boxes)
            Status$ = STR$(Boxes) + " boxes"
        END IF
    END IF
END SUB

SUB ClearAll
    Boxes = 0
    DRAW CLEAR
    Status$ = "Cleared"
END SUB

SUB Quit
    EXIT
END SUB

DragW = 400
DragH = 200
Status$ = "Drag to draw a box"
END
```

Keep the feedback cheap: an outline, not the object redrawn at every move.
Moving a whole selection on every mouse movement lagged in XAnne until it was
changed to an XOR outline.

**More rules that hold:**
- Clamp every coordinate before drawing (`MIN`, `MAX`, `GeomClamp`): drawing
  outside the canvas stops the program.
- Restore a background with a BITMAP: GET the empty scene once, then PUT the
  part under a moving object (`lib/sprite.pbas` does this for you; see the
  third tutorial, *Tested in XAnne*).
- Held keys: read `KEYDOWN` with the `SC_` names in the TIMER handler; take a
  single tap (a jump) from KEYS as well.
- Measure text with `TEXTWIDTH` to place carets, columns and right-aligned
  text.
- Keep the timer's handler short and stop the timer (`TIMER OFF`) before
  `EXIT`.

More: [chapters 12–14](manual/12-drawing.md),
[TUTORIAL-2-GRAPHICS.md](TUTORIAL-2-GRAPHICS.md) and
[TUTORIAL-3-GAME.md](TUTORIAL-3-GAME.md).

---

## 10. Conventional BASIC that does not exist

These are the constructs most often written by mistake. Each is refused by
the compiler (the message is given where it is not obvious). The full list
is [manual chapter 17](manual/17-unsupported.md).

| you might write | it does not exist; write instead |
|---|---|
| `PRINT "Hello"` | no console. A dynamic `LABEL`, `MESSAGE`, or `DRAW TEXT` on a canvas. (`PRINT #c, …` writes to a file.) |
| `PRINT A; B` / `PRINT USING` | build the text: `STR$`, `+`, `SPACE$`, `RIGHT$` for alignment |
| `INPUT A$` / `INPUT "Name"; N` | a `TEXTBOX` or `NUMBERBOX`, read in a button handler; `ASK` for a choice |
| `INKEY$` / `GET` | a canvas `KEYS` handler (`KEYCODE`) or `KEYDOWN` |
| `GOTO 100`, line-number jumps | `IF`, `WHILE`, `FOR`, `SELECT CASE`, `EXIT …`, SUBs |
| `GOSUB 100` / `RETURN` | `SUB` and `CALL` |
| `ON X GOTO …` | `SELECT CASE` |
| `ON ERROR GOTO` | check `IOERR` and values before using them |
| `DO … LOOP`, `DO WHILE`, `LOOP UNTIL`, `REPEAT … UNTIL` | `WHILE cond` … `WEND` (for "until", `WHILE NOT cond`, or a BOOLEAN flag set at the end) |
| `END WHILE` | `WEND` |
| `EXIT DO` | `EXIT WHILE` |
| `ELSEIF` / `ELSE IF` on one line | `SELECT CASE`, or `ELSE` followed by a nested `IF … END IF` |
| `ENDIF` | `END IF` |
| `IF A = 0 THEN B = 1` | the block form on three lines |
| `A = 1 : B = 2` | one statement a line |
| `LET A = 1` | `A = 1` |
| `A = 1` without DIM | `DIM A AS INTEGER` first |
| `A% = 1`, `X! = 1.5`, `DOUBLE`, `LONG` | `INTEGER`, `REAL` |
| `&HFF`, `&O17`, `HEX$` | decimal literals; build hex text yourself |
| `7 \ 2` | `7 / 2` (INTEGER division already truncates) |
| `DIM A(3, 3)` | a one-dimensional array indexed `(R - 1) * COLS + C`, or a TYPE |
| `DIM A(N)` | a literal size (a CONST is not accepted either); the largest you need |
| `REDIM`, `ERASE`, `OPTION BASE` | fixed sizes; arrays are 1-based |
| `DATA` / `READ` / `RESTORE` | assignments in the main line, or a data file read with `LINE INPUT #` |
| `DEF FN` | `FUNCTION` |
| `Name 1, 2` (calling a SUB) | `CALL Name(1, 2)` |
| `F` (calling a FUNCTION without arguments) | `F()` |
| recursion | a loop |
| `BYREF`, array parameters | globals, or a BITMAP parameter (the only by-reference type) |
| `MID$(A$, 2, 1) = "x"` | `A$ = LEFT$(A$, 1) + "x" + MID$(A$, 3, LEN(A$))` |
| `CLS`, `LOCATE`, `COLOR`, `SCREEN`, `WIDTH` | a canvas: `DRAW CLEAR`, `DRAW TEXT x, y, s$`; the screen is black and white |
| `PSET`, `LINE (x,y)-(x,y)`, `CIRCLE`, `PAINT` (fill) | `DRAW PIXEL`, `DRAW LINE`, `DRAW BOX`, `DRAW FILL`; no circles |
| `PEEK`, `POKE`, `CALL &H…`, `USR` | not available |
| `SLEEP`, `WAIT`, `FOR` delay loops | a `TIMER`, and `SECONDS` / `CLOCKTICKS` |
| `TIMER` (as a value), `TIME$`, `DATE$` | `SECONDS`, `CLOCKTICKS` |
| `RND` without an argument | `RND(n)`, 1..n |
| `SOUND`, `PLAY` | `BEEP` |
| `SWAP A, B` | three assignments through a spare variable |
| `OPEN … FOR APPEND` / `RANDOM`, `SEEK`, `INPUT #`, `WRITE #` | read the old file and write a new one (section 11); `LINE INPUT #`, `PRINT #` |
| `STOP`, `CHAIN`, `SHELL` | `EXIT` |
| `DECLARE SUB`, `DIM SHARED` | not needed: procedures may be defined after use, DIM is always global |
| `LOG10(x)` | `LOG(x) / LOG(10)` |
| `IF A THEN` (A an INTEGER) | `IF A <> 0 THEN` |
| `"Total " + N` | `"Total " + STR$(N)` |
| `FOR X = 0.5 TO 2` (X REAL), `STEP S` (S a variable) | INTEGER counters, constant steps; compute the REAL inside the loop |

A complete program using one of these does not build. For example:

```pbas-error
DIM N AS INTEGER
INPUT N
END
' expect-error: expected =, got N
```

---

## 11. Safe file handling

The language never asks before replacing a file: `OPEN … FOR OUTPUT`,
`FILESAVE` and `TEXT SAVE` replace at once. Protect the user's data yourself.

**Rules.**
1. Use names of your program's own (`NOTES.TXT`, not `DATA.TXT`), in the
   folder the program was built for. Never write a file the program did not
   create.
2. Never write over the only copy. Write a temporary file, check it, keep
   the previous version as a backup, then rename the temporary file into place:
   1. `OPEN "NOTES.TMP" FOR OUTPUT AS #2`; check `IOERR` after the OPEN,
      after every `PRINT #2`, and after `CLOSE #2`;
   2. on any failure: `KILL "NOTES.TMP"`, leave the real file alone, and tell
      the user;
   3. `KILL "NOTES.BAK"` (IOERR 2, "not found", is fine);
   4. `NAME "NOTES.TXT" AS "NOTES.BAK"` (IOERR 2 is fine on the first save);
   5. `NAME "NOTES.TMP" AS "NOTES.TXT"`; if this fails, the new data is still
      in NOTES.TMP, so say so.
3. When loading, read into spare variables or arrays and copy them over the
   program's data only when the whole file has been read. A failed load must
   leave the program's data as it was.
4. At start-up, if the file is missing but the temporary file or the backup
   exists, offer the data from it and mark it unsaved (the example in section
   13 does this).
5. Check every line you load before you show it: a LIST row or dynamic LABEL
   must be at most 24 printable ASCII characters, or the program stops.
6. Keep an unsaved-changes flag and ask before Quit or Reload
   (`lib/app.pbas` `AppMayClose()`).
7. `DB SAVE` and `BITMAP SAVE` already write NAME.NEW, check it and keep
   NAME.BAK. Files that share a name (FORM.DSN and FORM.PBI) share
   FORM.BAK and FORM.NEW, so the second of their saves is refused with
   IOERR 253 (known issue KI-91, [docs/limitations.md](limitations.md);
   *Simulator only* until the owner's XAnne retest). Give each kind of file
   its own name, or use `lib/files.pbas` for the others.
8. `FILESAVE` is for small, disposable settings: it is not crash-safe and
   shows its own alert every time.
9. Close a file before KILL or NAME. Only one file may be open for reading
   and one for writing.
10. There is no append: to add a line, copy the old file to a new one with the
    line added, then rename (`examples/journal.pbas` does this).

**Error paths.** Turn IOERR into words (`AppError$(IOERR)`, or your own
SELECT CASE) and show them in the status line or an alert. Do not stop the
program on a file error; leave the data as it was and let the user try
again. More: [manual chapter 6](manual/06-files.md) and
[chapter 8](manual/08-records-and-databases.md).

---

## 12. Known defects to avoid

These are faults of the current compiler and tools, with the way round each.
[limitations.md](limitations.md) has the full list of limitations.

| defect | what happens | avoid it by |
|---|---|---|
| `check` does not check the memory fit | `pcw16basic check` passes a program whose resident part is over 16K; only `build` finds it | always `build` |
| a SUB named like a built-in | accepted, but the built-in cannot then be used (`LEN is a SUB: use CALL LEN(…) as a statement`) | never reuse a built-in's name |
| a variable, parameter or LOCAL named like a built-in without arguments | hides the built-in where it is visible (a warning) | another name |
| `DIM` in a SUB | declares a global (a warning); two SUBs with the same DIM fail with `duplicate declaration` | `LOCAL` |
| `FUNCTION Name AS BOOLEAN` without `()` | declaring it without parentheses is allowed, but a call needs them (`lib/handles.pbas`'s `HandleOn`) | always call `Name()` |
| LIST `ACTION` | never runs in XAnne: a double-click arrives as two clicks (known issue KI-25, [docs/limitations.md](limitations.md)) | a button for the action |
| NUMBERBOX `SPIN`, SLIDER arrows | one click can step more than once (known issues KI-1 and KI-2, [docs/limitations.md](limitations.md)) | do not rely on exact single steps |
| `PAGE FILL`, printed charts | corrected but not retested in XAnne (known issue KI-79, [docs/limitations.md](limitations.md)) | say so if your program prints filled boxes |
| `DRAW TEXT` length | cut at (width − x) \ 11 characters (known issue KI-76, [docs/limitations.md](limitations.md)) | draw long text in pieces |
| Return in a TEXTBOX, `KEY STOP`, `KEY HELP` | not tested (known issue KI-6, [docs/limitations.md](limitations.md)) | do not depend on them; give every action a click |
| keyboard focus between a TEXTBOX and a canvas | not established; single-letter canvas keys may go into a text field (known issue KI-87, [docs/limitations.md](limitations.md)) | avoid letter keys on a canvas in a window with a TEXTBOX, or use Ctrl shortcuts in a menu |
| `RND`, `RANDOMIZE` | *Simulator only* | test games in XAnne |
| M14 runtime corrections | `DB SAVE`/`BITMAP SAVE` refusing another file's companions (IOERR 253), `DB LOAD`'s narrower fallback, REAL `+`/`-` rounding: *Simulator only* | say so if your program depends on them |

Fixed in M14, and no longer to be avoided: `KEYDOWN` or `lib/keys.pbas`
without a CANVAS (it used to fail in Pasmo); `check` running only the front
end; `D = E`, `B = C` and statements before the first `CASE` compiling
silently (now errors); a FUNCTION replacing a built-in (now an error);
`--help` after a subcommand; the TEXTBOX message blaming `--string-capacity`.

If you find a new defect, report it with a minimal program
([CONTRIBUTING.md](../CONTRIBUTING.md)).

---

## 13. A complete example application

NOTEBK keeps up to 20 short notes in `NOTES.TXT`. It has a text field, a
list, a status line, five buttons and a File menu, and it shows every rule of
section 11: a checked write to a temporary file, a backup, a rename, loading
into spare storage, recovery at start-up, input that a list can show, and an
unsaved-changes question on Quit and Reload.

Evidence: it builds (`tools/check_docs.py`), and on the simulator its
start-up, save, failed-rename and quit paths behave as described. It has not
been run in XAnne. The status line is `lib/app.pbas`'s `AppStatus$`.

```pbas
' NOTEBK: a list of short notes kept in NOTES.TXT, one note a line.
' Saving writes NOTES.TMP, checks every step, keeps the previous file as
' NOTES.BAK and only then renames NOTES.TMP to NOTES.TXT. Loading never
' changes the list unless the whole file was read.
INCLUDE "lib/app.pbas"

CONST MAXNOTES = 20
DIM Notes$(20) AS STRING * 24
DIM Spare$(20) AS STRING * 24
DIM Count AS INTEGER
DIM SpareN AS INTEGER
DIM Sel AS INTEGER
DIM Entry$ AS STRING * 24
DIM Line$ AS STRING * 24
DIM Answer AS INTEGER

WINDOW "Notebook", LARGE
TEXTBOX Entry$, "New note (up to 24 characters)"
LIST Sel, Notes$, Count, ROWS 8
LABEL AppStatus$
BUTTON "Add", AddNote, DEFAULT
BUTTON "Delete", DeleteNote
BUTTON "Save", SaveNotes
BUTTON "Reload", ReloadNotes
BUTTON "Quit", QuitApp, KEY STOP

MENU "File"
    ITEM "Save", SaveNotes, KEY "S"
    ITEM "Reload", ReloadNotes, KEY "R"
    ITEM "-"
    ITEM "Quit", QuitApp, KEY "Q"
END MENU

' TRUE if every character of S$ is printable ASCII (a LIST row needs it).
FUNCTION Printable(S$ AS STRING) AS BOOLEAN
    LOCAL I AS INTEGER
    LOCAL C AS INTEGER
    FOR I = 1 TO LEN(S$)
        C = ASC(MID$(S$, I, 1))
        IF C < 32 OR C > 126 THEN
            RETURN FALSE
        END IF
    NEXT I
    RETURN TRUE
END FUNCTION

' A file problem in a few words (codes 243 and 244 are line problems).
FUNCTION Problem$(Code AS INTEGER) AS STRING
    IF Code = 243 OR Code = 244 THEN
        RETURN "unreadable line"
    END IF
    RETURN AppError$(Code)
END FUNCTION

' Read the file Name$ into Spare$(1..SpareN). 0, or the first IOERR.
FUNCTION ReadNotes(Name$ AS STRING) AS INTEGER
    LOCAL Code AS INTEGER
    SpareN = 0
    OPEN Name$ FOR INPUT AS #1
    Code = IOERR
    IF Code <> 0 THEN
        RETURN Code
    END IF
    WHILE Code = 0 AND NOT EOF(1)
        LINE INPUT #1, Line$
        Code = IOERR
        IF Code = 0 THEN
            IF SpareN = MAXNOTES THEN
                Code = 252
            ELSE
                IF Printable(Line$) THEN
                    SpareN = SpareN + 1
                    Spare$(SpareN) = Line$
                ELSE
                    Code = 244
                END IF
            END IF
        END IF
    WEND
    CLOSE #1
    RETURN Code
END FUNCTION

' Copy Spare$ into the list shown.
SUB TakeSpare
    LOCAL I AS INTEGER
    FOR I = 1 TO SpareN
        Notes$(I) = Spare$(I)
    NEXT I
    Count = SpareN
    Sel = 0
    CALL AppSaved
END SUB

' At start: NOTES.TXT, else NOTES.TMP (a save stopped before its last
' rename), else NOTES.BAK. Tell the user when a spare copy was used.
SUB LoadAtStart
    LOCAL Code AS INTEGER
    Code = ReadNotes("NOTES.TXT")
    IF Code = 0 THEN
        CALL TakeSpare
        CALL AppSay(STR$(Count) + " notes")
        EXIT SUB
    END IF
    IF Code <> 2 THEN
        MESSAGE "NOTES.TXT: " + Problem$(Code)
    END IF
    IF ReadNotes("NOTES.TMP") = 0 THEN
        CALL TakeSpare
        CALL AppChanged
        MESSAGE "Recovered NOTES.TMP: save to keep it"
        CALL AppSay("Recovered: please save")
        EXIT SUB
    END IF
    IF ReadNotes("NOTES.BAK") = 0 THEN
        CALL TakeSpare
        CALL AppChanged
        MESSAGE "Recovered NOTES.BAK: save to keep it"
        CALL AppSay("Recovered: please save")
        EXIT SUB
    END IF
    CALL AppSay("New notebook")
END SUB

' Write the list to NOTES.TMP, then make it NOTES.TXT, keeping NOTES.BAK.
' lib/app.pbas calls this from AppMayClose when the user chooses Save.
FUNCTION AppSave() AS BOOLEAN
    LOCAL I AS INTEGER
    LOCAL Code AS INTEGER
    OPEN "NOTES.TMP" FOR OUTPUT AS #2
    Code = IOERR
    I = 1
    WHILE Code = 0 AND I <= Count
        PRINT #2, Notes$(I)
        Code = IOERR
        I = I + 1
    WEND
    CLOSE #2
    IF Code = 0 THEN
        Code = IOERR
    END IF
    IF Code <> 0 THEN
        KILL "NOTES.TMP"
        MESSAGE "Not saved: " + Problem$(Code)
        RETURN FALSE
    END IF
    KILL "NOTES.BAK"
    IF IOERR <> 0 AND IOERR <> 2 THEN
        MESSAGE "Not saved: " + Problem$(IOERR)
        RETURN FALSE
    END IF
    NAME "NOTES.TXT" AS "NOTES.BAK"
    IF IOERR <> 0 AND IOERR <> 2 THEN
        MESSAGE "Not saved: " + Problem$(IOERR)
        RETURN FALSE
    END IF
    NAME "NOTES.TMP" AS "NOTES.TXT"
    IF IOERR <> 0 THEN
        MESSAGE "Saved as NOTES.TMP only: " + AppError$(IOERR)
        RETURN FALSE
    END IF
    CALL AppSaved
    CALL AppSay("Saved " + STR$(Count) + " notes")
    RETURN TRUE
END FUNCTION

SUB AddNote
    IF LEN(TRIM$(Entry$)) = 0 THEN
        CALL AppSay("Type a note first")
        EXIT SUB
    END IF
    IF NOT Printable(Entry$) THEN
        CALL AppSay("Plain letters only")
        EXIT SUB
    END IF
    IF Count = MAXNOTES THEN
        CALL AppSay("The notebook is full")
        EXIT SUB
    END IF
    Count = Count + 1
    Notes$(Count) = Entry$
    Sel = Count
    Entry$ = ""
    CALL AppChanged
    CALL AppSay("Added note " + STR$(Count))
END SUB

SUB DeleteNote
    LOCAL I AS INTEGER
    IF Sel = 0 THEN
        CALL AppSay("Choose a note first")
        EXIT SUB
    END IF
    Answer = ASK("Delete this note?", "Delete", "Keep")
    IF Answer <> 1 THEN
        EXIT SUB
    END IF
    FOR I = Sel TO Count - 1
        Notes$(I) = Notes$(I + 1)
    NEXT I
    Notes$(Count) = ""
    Count = Count - 1
    Sel = 0
    CALL AppChanged
    CALL AppSay("Deleted")
END SUB

SUB SaveNotes
    IF AppSave() THEN
        Sel = 0
    END IF
END SUB

SUB ReloadNotes
    LOCAL Code AS INTEGER
    IF NOT AppMayClose() THEN
        EXIT SUB
    END IF
    Code = ReadNotes("NOTES.TXT")
    IF Code <> 0 THEN
        MESSAGE "Not reloaded: " + Problem$(Code)
        EXIT SUB
    END IF
    CALL TakeSpare
    CALL AppSay("Loaded " + STR$(Count) + " notes")
END SUB

SUB QuitApp
    IF AppMayClose() THEN
        EXIT
    END IF
END SUB

CALL LoadAtStart
END
```

Points to notice:
- Every string a LIST or LABEL shows is `STRING * 24`, and typed or loaded
  text is checked with `Printable` before it reaches the list.
- `ReadNotes` reads into `Spare$`; the list changes only in `TakeSpare`,
  after a complete read.
- `AppSave` deletes its temporary file on a failed write and never touches
  `NOTES.TXT` until the new file is complete. If the last rename fails, it
  says where the data is, and the next start recovers it.
- The FUNCTION calls on the right of `AND` in the WHILE conditions are
  built-ins (`EOF`), not the program's own FUNCTIONs.
- Five buttons fit in a LARGE window in two rows; the menu gives Ctrl+S,
  Ctrl+R and Ctrl+Q.
- When the system closes the program (Tasks → Exit), unsaved notes are lost:
  the question runs only from Quit.

---

## 14. Checklist before you hand a program over

- [ ] Every variable is declared; every `$` name is STRING.
- [ ] No construct from section 10; one statement a line; block IFs; `WEND`.
- [ ] Every SUB call has `CALL`; every FUNCTION call has `()`.
- [ ] No procedure is named like a built-in.
- [ ] Every window has a button that ends the program with `EXIT`.
- [ ] Every dynamic LABEL and LIST string is `STRING * 24` or shorter, and
      only printable ASCII can reach it.
- [ ] Nothing is drawn from the main line; PAINT can redraw everything;
      every coordinate is kept inside the canvas.
- [ ] Animation is stepped by `CLOCKTICKS` (`lib/pace.pbas`), not by counting
      timer events.
- [ ] Library dependencies are included first; your program defines what a
      library needs (`AppSave`, `ListCell$`, `ListPicked`).
- [ ] Every file statement is followed by an IOERR check; saves go through a
      temporary file and a backup; loads go through spare storage.
- [ ] `pcw16basic build` wrote the `.prg` (not only `check`).
- [ ] You have said which evidence level applies: built; run on the
      simulator; run in XAnne. Not yet tested on a real PcW16.
