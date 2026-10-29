# PcW16 BASIC manual

This manual describes the PcW16 BASIC language as the compiler in this
repository accepts it: every statement, function and option, with its limits,
the errors you will see, and a complete example program. It is written for
someone who knows some programming; if you are new, start with
[your first program](../first-program.md) and the tutorials listed in the
[documentation index](../README.md), then come back here.

The normative definition is [LANGUAGE-SPEC.md](../../LANGUAGE-SPEC.md). Where
an older section of the specification disagrees with a later one, the manual
describes what the compiler actually does and says so.

## Chapters

**The language**

1. [Program structure](01-program-structure.md) — source text, comments,
   line numbers, case, the main line, `END`, `MESSAGE`, `INCLUDE`, program
   names.
2. [Variables and types](02-variables-and-types.md) — `DIM`, `INTEGER`,
   `BOOLEAN`, `REAL`, `STRING`, `STRING * n`, `CONST`, arrays, `BANKED`
   arrays, string capacity and `--string-capacity`.
3. [Expressions and built-in functions](03-expressions-and-functions.md) —
   operators and precedence, integer and REAL arithmetic, comparisons,
   logical and bitwise operators, every built-in function.
4. [Control flow](04-control-flow.md) — `IF`, `SELECT CASE`, `FOR … NEXT`,
   `WHILE … WEND`, the `EXIT` forms.
5. [Procedures](05-procedures.md) — `SUB`, `FUNCTION`, `CALL`, parameters,
   `LOCAL`, `RETURN`, recursion and depth rules.

**Data**

6. [Files](06-files.md) — `FILESAVE`, `FILELOAD`, `OPEN`, `PRINT #`,
   `LINE INPUT #`, `EOF`, `CLOSE`, `KILL`, `NAME`, `IOERR`, safe file
   handling.
7. [Text buffers](07-text-buffers.md) — `TEXT` documents of up to 64K.
8. [Records and databases](08-records-and-databases.md) — `TYPE`, record
   arrays, `DB` load, save, sort and search, the PDB1 format,
   `tools/pdbcheck.py`.
9. [Errors and diagnostics](09-errors-and-diagnostics.md) — compiler
   messages, warnings, `check` versus `build`, runtime errors, memory
   messages, the compiler's remaining surprises.

**The PcW16 interface**

10. [Windows and controls](10-windows-and-controls.md) — `WINDOW`, `LABEL`,
    `TEXTBOX`, `CHECKBOX`, `BUTTON`, `RADIO`, `NUMBERBOX`, `LIST`, `CHOICE`,
    `SLIDER`, `SHOW`, `FOCUS`, `ASK`, `BEEP`.
11. [Menus, keys and mouse](11-menus-keys-mouse.md) — `MENU`, `ITEM`,
    Tasks → Stop and `ON STOP`, keyboard and mouse handlers on a canvas, `KEYDOWN`.
12. [Drawing](12-drawing.md) — `CANVAS` and `DRAW`, the twelve dialog fonts
    (`DRAW FONT`, `ALIGN`), scalable type (`TYPE FONT`, `DRAW TYPE`), and
    several canvases (`DRAW ON`).
13. [Bitmaps and sprites](13-bitmaps-and-sprites.md) — `BITMAP`, masks,
    `POINT`, picture files.
14. [Timers and animation](14-timers-and-animation.md) — `TIMER`, ticks,
    `SECONDS`, `CLOCKTICKS`.
15. [Printing](15-printing.md) — `PAGE`.

**Tools and gaps**

16. [Building and commands](16-building-and-commands.md) — `pcw16basic` and
    the build options.
17. [What PcW16 BASIC does not have](17-unsupported.md) — common BASIC
    constructs that are absent, the messages they give, and what to use
    instead.

**Elsewhere**

- [Libraries](../libraries/README.md) — the 14 libraries in `examples/lib/`
  and [the generated reference](../LIBRARY-REFERENCE.md).
- [Example programs](../../examples/README.md) — the catalogue of programs in
  `examples/`, each referred to from the chapters by its path.
- [Limitations](../limitations.md) — known issues (`KI-nn`) and what has not
  been tested.
- [Memory](../memory.md) — the 16K block, code banks and BANKED data.
- [The language specification](../../LANGUAGE-SPEC.md).

## How to read a chapter

Each feature is described under the same headings:

- **Syntax** — the forms the compiler accepts, in a `text` block.
  `[ ]` marks an optional part, `|` separates alternatives and `...` means
  "more of the same". Words in capitals are typed as shown (in any case);
  other words stand for your own names and expressions.
- **Meaning** — what the statement does.
- **Requires** — declarations, `INCLUDE`s or other statements it depends on.
- **Example** — a complete program in a `pbas` block. Every such block
  builds: `tools/check_docs.py` compiles and assembles each one. A line
  `' expect-message: text` (an ordinary comment) records an alert the program
  shows, and the checker runs the program on the project's simulator and
  compares. Programs that need a window or input are only built.
- **Common errors** — real compiler messages. A `pbas-error` block is a
  program the compiler refuses, with `' expect-error:` giving words from the
  message; the checker confirms it.
- **Limits** — sizes, counts and restrictions.
- **See also** — example programs in `examples/` and the specification
  section.

**Evidence.** Compiling is not the same as working on the machine. The
manual says which applies:

- *tested in XAnne* — the owner ran a program using the feature in the XAnne
  emulator (Rosanne 1.12);
- *simulator* — checked only on the project's model of the PcW16
  (`tests/z80sim.py`);
- *untested* — neither.

**Nothing has been run on a real PcW16 yet.** See
[real hardware](../real-hardware.md).

## Language at a glance

Every statement and keyword the compiler recognises, and the chapter that
documents it. The list is taken from the compiler's lexer and parser
(`pbas/lexer.py`, `pbas/parser.py`); anything not in it does not exist
([chapter 17](17-unsupported.md)).

### Statements

| Statement | Purpose | Chapter |
|---|---|---|
| `' …`, `REM …` | comment | [1](01-program-structure.md) |
| `INCLUDE "file"` | insert a library's text | [1](01-program-structure.md) |
| `MESSAGE text$` | show an alert | [1](01-program-structure.md) |
| `END` | end of the program (and of the main line) | [1](01-program-structure.md) |
| `DIM … AS …` | declare a variable or array (`STRING * n`, `BANKED`, `TEXT * n`, `BITMAP * w, h`) | [2](02-variables-and-types.md) |
| `CONST Name = literal` | name a constant | [2](02-variables-and-types.md) |
| `Name = expression` | assignment (there is no `LET`) | [2](02-variables-and-types.md) |
| `RANDOMIZE [seed]` | seed `RND` | [3](03-expressions-and-functions.md) |
| `IF … THEN` / `ELSE` / `END IF` | choice | [4](04-control-flow.md) |
| `SELECT CASE` / `CASE` / `CASE IS` / `CASE … TO …` / `CASE ELSE` / `END SELECT` | choice by value | [4](04-control-flow.md) |
| `FOR … = … TO … [STEP …]` / `NEXT [counter]` | counted loop | [4](04-control-flow.md) |
| `WHILE …` / `WEND` | conditional loop | [4](04-control-flow.md) |
| `EXIT FOR`, `EXIT WHILE` | leave a loop | [4](04-control-flow.md) |
| `EXIT` | end the program | [4](04-control-flow.md) |
| `SUB` / `END SUB` | define a procedure | [5](05-procedures.md) |
| `FUNCTION … AS type` / `END FUNCTION` | define a function | [5](05-procedures.md) |
| `CALL Name[(…)]` | run a SUB | [5](05-procedures.md) |
| `RETURN value` | return from a FUNCTION | [5](05-procedures.md) |
| `LOCAL Name AS type` | a procedure's own variable | [5](05-procedures.md) |
| `EXIT SUB`, `EXIT FUNCTION` | leave a procedure | [5](05-procedures.md) |
| `FILESAVE`, `FILELOAD` | save / load one string | [6](06-files.md) |
| `OPEN … FOR INPUT\|OUTPUT AS #n`, `CLOSE [#n]` | open and close a file | [6](06-files.md) |
| `PRINT #n, value` | write a line | [6](06-files.md) |
| `LINE INPUT #n, var$` | read a line | [6](06-files.md) |
| `KILL name$`, `NAME old$ AS new$` | delete, rename a file | [6](06-files.md) |
| `TEXT LOAD\|SAVE\|CLEAR\|INSERT\|DELETE\|SPLIT\|JOIN\|REMOVE\|COPY\|PASTE` | edit a text buffer | [7](07-text-buffers.md) |
| `TYPE` / `END TYPE` | define a record | [8](08-records-and-databases.md) |
| `DB LOAD\|SAVE\|NEW\|DELETE\|SORT\|SEARCH` | databases | [8](08-records-and-databases.md) |
| `WINDOW [Name,] "title" [, LARGE]` | declare a window | [10](10-windows-and-controls.md) |
| `LABEL`, `TEXTBOX`, `CHECKBOX`, `BUTTON`, `RADIO`, `NUMBERBOX`, `LIST`, `CHOICE`, `SLIDER` | controls | [10](10-windows-and-controls.md) |
| `SHOW Name`, `FOCUS var` or `FOCUS Canvas` | switch window, move the focus | [10](10-windows-and-controls.md) |
| `var = ASK(…)`, `BEEP` | question alert, beep | [10](10-windows-and-controls.md) |
| `MENU "title"` / `ITEM …` / `END MENU` | menus | [11](11-menus-keys-mouse.md) |
| `ON STOP Handler` | run a FUNCTION when Rosanne's Tasks → Stop is chosen | [11](11-menus-keys-mouse.md#tasks--stop-and-on-stop) |
| `CANVAS [Name,] w, h [, PAINT …] [, MOUSE …] [, KEYS …]` | a drawing area and its handlers (up to 8, named) | [12](12-drawing.md) |
| `DRAW CLEAR\|FILL\|INVERT\|BOX\|LINE\|PIXEL\|TEXT\|SCROLL\|INK` | draw on the canvas | [12](12-drawing.md) |
| `DRAW FONT n`, `DRAW TEXT … ALIGN …` | dialog fonts 1–12, aligned text | [12](12-drawing.md#draw-font-and-align) |
| `TYPE FONT SWISS\|TIMES, size …`, `DRAW TYPE x, y, s$` | scalable type, 6 to 72 points | [12](12-drawing.md#scalable-type-type-font-and-draw-type) |
| `DRAW ON Name` | choose the canvas later drawing goes to | [12](12-drawing.md#several-canvases-draw-on) |
| `BITMAP GET\|PUT\|MASK\|SAVE\|LOAD` | pictures | [13](13-bitmaps-and-sprites.md) |
| `TIMER Handler, EVERY n [TICKS]`, `TIMER ON`, `TIMER OFF` | timer events | [14](14-timers-and-animation.md) |
| `PAGE NEW\|FONT\|TEXT\|LINE\|BOX\|FILL\|PRINT\|CLOSE` | printing | [15](15-printing.md) |
| `PRINT` (to the screen), `GOTO` | reserved words with no statement | [17](17-unsupported.md) |

### Words used inside statements

| Word | Where | Chapter |
|---|---|---|
| `AS` | `DIM`, `LOCAL`, parameters, `FUNCTION`, `OPEN`, `NAME` | [2](02-variables-and-types.md), [5](05-procedures.md), [6](06-files.md) |
| `INTEGER`, `BOOLEAN`, `REAL`, `STRING` | types | [2](02-variables-and-types.md) |
| `TRUE`, `FALSE` | BOOLEAN literals | [2](02-variables-and-types.md) |
| `BANKED` | `DIM A(n) AS … BANKED` | [2](02-variables-and-types.md) |
| `THEN`, `ELSE` | `IF`; `CASE ELSE` | [4](04-control-flow.md) |
| `TO`, `STEP` | `FOR`; `CASE low TO high` | [4](04-control-flow.md) |
| `IS` | `CASE IS > value` | [4](04-control-flow.md) |
| `INPUT`, `OUTPUT` | `OPEN … FOR …` | [6](06-files.md) |
| `DESC`, `NOCASE`, `KEEP` | `DB SORT`, `DB SEARCH` | [8](08-records-and-databases.md) |
| `LARGE` | `WINDOW` | [10](10-windows-and-controls.md) |
| `DEFAULT`, `KEY` | `BUTTON` (`KEY GREEN`, `RED`, `BLUE`, `YELLOW`, `STOP`, `HELP`, `F1`…`F8`) | [10](10-windows-and-controls.md) |
| `MIN`, `MAX`, `SPIN` | `NUMBERBOX`, `SLIDER` | [10](10-windows-and-controls.md) |
| `ROWS`, `CHANGE`, `ACTION` | `LIST`, `CHOICE`, `SLIDER` | [10](10-windows-and-controls.md) |
| `KEY "X"`, `TICK` | `ITEM` | [11](11-menus-keys-mouse.md) |
| `PAINT`, `MOUSE`, `KEYS` | `CANVAS` handlers | [11](11-menus-keys-mouse.md), [12](12-drawing.md) |
| `BLACK`, `WHITE`, `XOR` | `DRAW INK` | [12](12-drawing.md) |
| `EVERY`, `TICKS`, `ON`, `OFF` | `TIMER` | [14](14-timers-and-animation.md) |
| `LEFT`, `CENTRE`, `RIGHT` | `DRAW TEXT … ALIGN` | [12](12-drawing.md#draw-font-and-align) |
| `SWISS`, `TIMES`, `BOLD`, `ITALIC` | `TYPE FONT` | [12](12-drawing.md#scalable-type-type-font-and-draw-type) |
| `BOLD` | `PAGE FONT` | [15](15-printing.md) |

### Operators

| Operator | Chapter |
|---|---|
| `^`, `*`, `/`, `MOD`, `+`, `-` | [3](03-expressions-and-functions.md) |
| `=`, `==`, `<>`, `<`, `<=`, `>`, `>=` | [3](03-expressions-and-functions.md) |
| `NOT`, `AND`, `OR`, `XOR` (logical on BOOLEANs, bitwise on INTEGERs) | [3](03-expressions-and-functions.md) |
| `+` on STRINGs (joining) | [3](03-expressions-and-functions.md) |
| `.` (record field), `( )` (array index, call), `#` (file channel) | [8](08-records-and-databases.md), [2](02-variables-and-types.md), [6](06-files.md) |

### Built-in functions

| Functions | Chapter |
|---|---|
| `LEN`, `STR$`, `LEFT$`, `RIGHT$`, `MID$`, `INSTR`, `VAL`, `REALVAL`, `ISNUM`, `ASC`, `CHR$`, `UCASE$`, `LCASE$`, `TRIM$`, `LTRIM$`, `RTRIM$`, `SPACE$`, `STRING$` | [3](03-expressions-and-functions.md#text-functions) |
| `ABS`, `SGN`, `MIN`, `MAX`, `SHL`, `SHR`, `RND`, `CINT` | [3](03-expressions-and-functions.md#number-functions) |
| `SQR`, `EXP`, `LOG`, `SIN`, `COS`, `TAN`, `ATN`, `INT`, `FIX`, `REAL`, `PI` | [3](03-expressions-and-functions.md#real-functions) |
| `EOF`, `IOERR` | [6](06-files.md) |
| `TEXTLINES`, `TEXTLEN`, `TEXTGET$`, `TEXTFIND`, `TEXTCOL`, `TEXTCHANGED`, `TEXTFREE`, `TEXTSIZE`, `TEXTSAME` | [7](07-text-buffers.md) |
| `DBFIND`, `DBNEXTID`, `DBRECOVERED` | [8](08-records-and-databases.md) |
| `ASK` | [10](10-windows-and-controls.md) |
| `MOUSEX`, `MOUSEY`, `MOUSEEVENT`, `KEYCODE`, `KEYSHIFT`, `KEYDOWN` | [11](11-menus-keys-mouse.md) |
| `TEXTWIDTH`, `TYPEWIDTH`, `TYPEHEIGHT` | [12](12-drawing.md) |
| `POINT` | [12](12-drawing.md#point) |
| `BITMAPW`, `BITMAPH` | [13](13-bitmaps-and-sprites.md#bitmapw-and-bitmaph) |
| `SECONDS`, `CLOCKTICKS` | [14](14-timers-and-animation.md) |
| `PAGEWIDTH` | [15](15-printing.md) |

### Reserved words

`MOD AND OR NOT XOR` and `AS BOOLEAN BUTTON CALL CHECKBOX DIM ELSE END EXIT
FALSE FILELOAD FILESAVE FOR GOTO IF INTEGER LABEL MESSAGE NEXT PRINT REM STEP
STRING SUB TEXTBOX THEN TO TRUE WEND WHILE WINDOW` can never be names. The
other statement words are recognised by position and can still be used as
names, though it is clearer not to ([chapter 1](01-program-structure.md#12-reserved-words)).
Do not name your own procedures after built-in functions
([chapter 5](05-procedures.md#58-a-function-may-not-take-a-built-ins-name)).

## A first complete program

```pbas
' expect-message: Hello from PcW16 BASIC
' expect-message: 2 + 2 = 4
DIM Sum AS INTEGER
Sum = 2 + 2
MESSAGE "Hello from PcW16 BASIC"
MESSAGE "2 + 2 = " + STR$(Sum)
END
```

Build it with `pcw16basic build hello.pbas` and copy `build/hello.prg` to the
PcW16 (or XAnne) as `HELLO.PRG`; see [first program](../first-program.md) and
[chapter 16](16-building-and-commands.md).
