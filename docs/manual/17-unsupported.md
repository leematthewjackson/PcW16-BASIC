# 17. What PcW16 BASIC does not have

PcW16 BASIC looks like a traditional BASIC, but many familiar statements and
functions do not exist. This chapter lists the common ones, with the message
the compiler gives and what to use instead. Every message below was produced
by the current compiler; `tools/check_docs.py` checks them each time the
documentation is built.

**Why the messages look odd.** Apart from `PRINT` and `GOTO`, unknown
statements are not reported as "not supported". The compiler reads an
unknown first word as the name of a variable being assigned, so `GOSUB 100`
gives `expected =, got 100`. If you see `expected =, got …` on a line that
starts with a familiar keyword, that keyword does not exist in PcW16 BASIC.
A function that does not exist gives `unknown function NAME`, and a
zero-argument "function" such as `INKEY$` gives `undefined variable INKEY$`.

Things that are **not** missing, although other documents may say so:
arrays, user FUNCTIONs, parameters, LOCAL variables, `SELECT CASE`, any
non-zero constant `STEP`, bitwise `AND`/`OR`/`XOR`/`NOT`, `RANDOMIZE`/`RND`,
line numbers (allowed, but meaningless), and STRING file names for `OPEN`.
See chapters [2](02-variables-and-types.md) to [5](05-procedures.md).

## Summary

| Construct | Message (after `file:line:col:`) | Use instead |
|---|---|---|
| `PRINT` to the screen | `PRINT to the screen does not exist in PcW16 BASIC: show text with MESSAGE, a LABEL or DRAW TEXT (PRINT #n, value writes a line to an open file)` | `MESSAGE` for an alert ([chapter 1](01-program-structure.md#15-message-showing-a-result)); a `LABEL` in a window ([chapter 10](10-windows-and-controls.md)); `DRAW TEXT` on a canvas ([chapter 12](12-drawing.md)); `PRINT #` writes to a file |
| `PRINT` lists with `;` or `,` | `unexpected character ';'` | join the text with `+` and `STR$` |
| `PRINT USING` | `unexpected character ';'` | format with `STR$`, `SPACE$`, `RIGHT$` (`examples/number_format.pbas`) |
| `INPUT` | `expected =, got A$` | a `TEXTBOX` or `NUMBERBOX` in a window; `ASK` for a choice of two or three buttons |
| `INPUT` with a prompt | `unexpected character ';'` | as above |
| `INKEY$` | `undefined variable INKEY$` | a canvas `KEYS` handler with `KEYCODE`, or `KEYDOWN` ([chapter 11](11-menus-keys-mouse.md)) |
| `CLS` | `expected =, got NEWLINE` | `DRAW CLEAR` on a canvas |
| `LOCATE` | `expected =, got 1` | `DRAW TEXT x, y, text$` |
| `SCREEN` | `expected =, got 1` | a `WINDOW`, with `LARGE` for 600 × 400 |
| `COLOR` | `expected =, got 1` | `DRAW INK BLACK`/`WHITE`/`XOR`; grey shades with `DRAW FILL` (the screen is black and white) |
| `GOTO` | `unsupported statement GOTO` | `IF`, `WHILE`, `FOR`, `SELECT CASE`, `EXIT` and procedures |
| `GOSUB` / `RETURN` | `expected =, got 100` | `SUB` and `CALL` ([chapter 5](05-procedures.md)) |
| `ON … GOTO` / `ON … GOSUB` | `expected =, got A` | `SELECT CASE` with a `CALL` in each case |
| `ON ERROR` | `expected =, got ERROR` | test `IOERR` after file statements; check values before using them (there is no error recovery) |
| `STOP` | `expected =, got NEWLINE` | `EXIT` |
| `CHAIN` | `expected =, got X.PRG` | none: one program per `.PRG`; `INCLUDE` libraries when building |
| `SHELL` | `expected =, got X` | none |
| `DATA` | `expected =, got 1` | assign array elements in the main line, or read a file with `LINE INPUT #` |
| `READ` | `expected =, got A` | as above |
| `RESTORE` | `expected =, got NEWLINE` | as above |
| two-dimensional arrays | `expected ), got ,` | one array of rows × columns, indexed `A((Row - 1) * Cols + Col)`, or an array of records |
| an array size from a variable or a CONST | `the number of elements of an array is a whole number written in the program (a literal such as 10); got N (a CONST or a variable cannot be used here)` | a literal or the largest size you need, with a count variable |
| `REDIM` | `expected =, got A` | declare the largest size once |
| `ERASE` | `expected =, got A` | a `FOR` loop that sets each element |
| `OPTION BASE` | `expected =, got BASE` | arrays always start at 1 |
| `DIM` without a type | `expected AS, got NEWLINE` | `DIM A AS INTEGER` |
| several names in one `DIM` | `expected NEWLINE, got ,` | one `DIM` per line |
| `DIM SHARED` | `expected AS, got A` | every `DIM` is already global |
| implicit variables | `undefined variable A; declare it with DIM or a UI binding` | declare every variable |
| `LET` | `expected =, got A` | `A = 1` |
| `DOUBLE`, `LONG`, `SINGLE`, `BYTE` | `unknown type DOUBLE` | `REAL` or `INTEGER` |
| type suffixes `%`, `!` | `unexpected character '%'` | names without suffix (`$` is allowed for STRINGs) |
| type suffix `#` | `expected AS, got #` | as above |
| `SWAP` | `expected =, got A` | three assignments through a spare variable |
| single-line `IF` | `expected NEWLINE, got A` | the block form `IF … THEN` / `END IF` |
| `ELSEIF` | `expected =, got A` | an `IF` inside the `ELSE`, or `SELECT CASE` |
| `ELSE IF` on one line | `expected NEWLINE, got IF` | as above |
| `ENDIF` as one word | `expected =, got NEWLINE` | `END IF` |
| numeric conditions | `IF requires BOOLEAN condition, got INTEGER` | `IF A <> 0 THEN` |
| `DO … LOOP` | `expected =, got NEWLINE` | `WHILE … WEND`; `WHILE TRUE` with `EXIT WHILE` |
| `DO WHILE` | `expected =, got WHILE` | `WHILE A < 3` … `WEND` |
| `REPEAT … UNTIL` | `expected =, got NEWLINE` | `WHILE TRUE` … `IF cond THEN` / `EXIT WHILE` / `END IF` … `WEND` |
| `END WHILE` | `expected NEWLINE, got WHILE` | `WEND` |
| `EXIT DO` | `expected NEWLINE, got DO` | `EXIT WHILE`, `EXIT FOR` |
| a REAL `FOR` counter | `FOR counter X must be INTEGER` | an INTEGER counter, and compute the REAL from it |
| a variable `STEP` | `STEP must be a non-zero INTEGER constant` | a `CONST`, or a `WHILE` loop |
| calling a SUB without `CALL` | `expected =, got 1` | `CALL S(1)` |
| `DEF FN` | `expected =, got FN` | `FUNCTION Sq(X AS INTEGER) AS INTEGER` |
| `DECLARE SUB` | `expected =, got SUB` | not needed: procedures may be used before they are defined |
| recursion | `recursive CALL is not allowed: F -> F` | a loop ([chapter 5](05-procedures.md#57-recursion-and-call-depth)) |
| `BYREF` | `parameter BYREF needs a type` | a FUNCTION result, or a global variable |
| `BYVAL` | `parameter BYVAL needs a type` | not needed: parameters are always by value |
| array parameters | `parameter X needs a type: X AS INTEGER` | a global array and an index parameter |
| `LOCAL` arrays | `LOCAL arrays are not supported` | a global `DIM` array |
| `MID$` as a statement | `expected ), got ,` | `A$ = "J" + MID$(A$, 2, LEN(A$))` |
| STRING + number | `operator + requires numbers (or STRING + STRING), got STRING and INTEGER` | `"a" + STR$(1)` |
| `HEX$` | `unknown function HEX$` | write your own with `MOD`, `/` and `MID$("0123456789ABCDEF", D + 1, 1)` |
| `&H` literals | `unexpected character '&'` | decimal (`255`) |
| `\` integer division | `unexpected character '\\'` | `/` on two INTEGERs already truncates |
| `LOG10` | `unknown function LOG10` | `LOG(X) / LOG(10)` |
| `RND` without an argument | `undefined variable RND` | `RND(n)` gives 1..n |
| `PEEK` | `unknown function PEEK` | none: programs do not touch memory directly |
| `POKE` | `expected =, got 100` | none |
| `USR` | `unknown function USR` | none |
| `CALL` of machine code | `expected IDENT, got 32768` | none |
| `SOUND` | `expected =, got 440` | `BEEP` (the only sound) |
| `PLAY` | `expected =, got C` | `BEEP` |
| `SLEEP` / `WAIT` | `expected =, got 1` | a `TIMER` handler ([chapter 14](14-timers-and-animation.md)) |
| `TIMER` as a function | `undefined variable TIMER` | `SECONDS` or `CLOCKTICKS` |
| `DATE$` / `TIME$` | `undefined variable DATE$` | `SECONDS` gives the seconds within the hour; there is no date |
| `PSET` | `expected ), got ,` | `DRAW PIXEL x, y` on a canvas |
| `LINE (x,y)-(x,y)` | `expected ), got ,` | `DRAW LINE x1, y1, x2, y2`; `DRAW BOX` for rectangles |
| `DRAW CIRCLE` and other shapes | `expected CLEAR, FILL, INVERT, BOX, LINE, PIXEL, TEXT, SCROLL or INK after DRAW, got CIRCLE` | draw with `DRAW LINE`/`DRAW PIXEL`, or `BITMAP PUT` a prepared picture |
| `INPUT #` | `expected =, got #` | `LINE INPUT #1, A$`, then take the line apart |
| `WRITE #` | `expected =, got #` | `PRINT #1, value`, one value a line |
| `OPEN … FOR APPEND` / `RANDOM` | `APPEND and RANDOM are not available on the floppy` | copy to a new file with the extra lines, then swap it in ([chapter 6](06-files.md#69-safe-file-handling)) |
| channel `#3` and above | `a file channel is #1 or #2` | one file for reading and one for writing at a time |
| a variable file name in `FILESAVE` | `this file name must be written in the program as a string, such as "NOTES.TXT", or be a CONST (…)` | a `CONST`, or `OPEN` with any STRING |

Not defined at all (no statement exists, so there is nothing to misspell):
several windows on screen at once, windows created at run time, a raw
keyboard outside a canvas, the right or middle mouse button, double-clicks,
colour, other fonts (the canvas has one text font, printing uses Times),
circles, arcs, flood fill and clipping, setting or reading one pixel inside a
BITMAP, scaling and rotation, pictures and sloped lines on printed pages,
landscape printing, folders chosen at run time, and the flash drive. See
chapters [10](10-windows-and-controls.md) to [15](15-printing.md) and
[limitations](../limitations.md).

## The messages, verified

Each block below is a complete program that the compiler refuses with the
message shown.

### Output and input

`PRINT` to the screen:

```pbas-error
' expect-error: PRINT to the screen does not exist in PcW16 BASIC
PRINT "hello"
END
```

`PRINT` lists with `;` or `,`:

```pbas-error
' expect-error: unexpected character ';'
PRINT "a"; "b"
END
```

`PRINT USING`:

```pbas-error
' expect-error: unexpected character ';'
PRINT USING "##"; 1
END
```

`INPUT`:

```pbas-error
' expect-error: expected =, got A$
DIM A$ AS STRING
INPUT A$
END
```

`INPUT` with a prompt:

```pbas-error
' expect-error: unexpected character ';'
DIM N AS INTEGER
INPUT "N"; N
END
```

`INKEY$`:

```pbas-error
' expect-error: undefined variable INKEY$
DIM K$ AS STRING
K$ = INKEY$
END
```

`CLS`:

```pbas-error
' expect-error: expected =, got NEWLINE
CLS
END
```

`LOCATE`:

```pbas-error
' expect-error: expected =, got 1
LOCATE 1, 1
END
```

`SCREEN`:

```pbas-error
' expect-error: expected =, got 1
SCREEN 1
END
```

`COLOR`:

```pbas-error
' expect-error: expected =, got 1
COLOR 1
END
```


### Jumps and line-based structure

`GOTO`:

```pbas-error
' expect-error: unsupported statement GOTO
10 GOTO 10
END
```

`GOSUB` / `RETURN`:

```pbas-error
' expect-error: expected =, got 100
GOSUB 100
END
```

`ON … GOTO` / `ON … GOSUB`:

```pbas-error
' expect-error: expected =, got A
DIM A AS INTEGER
ON A GOTO 10, 20
END
```

`ON ERROR`:

```pbas-error
' expect-error: expected =, got ERROR
ON ERROR GOTO 100
END
```

`STOP`:

```pbas-error
' expect-error: expected =, got NEWLINE
STOP
END
```

`CHAIN`:

```pbas-error
' expect-error: expected =, got X.PRG
CHAIN "X.PRG"
END
```

`SHELL`:

```pbas-error
' expect-error: expected =, got X
SHELL "X"
END
```


### Data, arrays and declarations

`DATA`:

```pbas-error
' expect-error: expected =, got 1
DATA 1, 2, 3
END
```

`READ`:

```pbas-error
' expect-error: expected =, got A
DIM A AS INTEGER
READ A
END
```

`RESTORE`:

```pbas-error
' expect-error: expected =, got NEWLINE
RESTORE
END
```

two-dimensional arrays:

```pbas-error
' expect-error: expected ), got ,
DIM A(3, 3) AS INTEGER
END
```

an array size from a variable:

```pbas-error
' expect-error: the number of elements of an array is a whole number written in the program
DIM N AS INTEGER
DIM A(N) AS INTEGER
END
```

`REDIM`:

```pbas-error
' expect-error: expected =, got A
DIM A(3) AS INTEGER
REDIM A(5) AS INTEGER
END
```

`ERASE`:

```pbas-error
' expect-error: expected =, got A
DIM A(3) AS INTEGER
ERASE A
END
```

`OPTION BASE`:

```pbas-error
' expect-error: expected =, got BASE
OPTION BASE 0
END
```

`DIM` without a type:

```pbas-error
' expect-error: expected AS, got NEWLINE
DIM A
END
```

several names in one `DIM`:

```pbas-error
' expect-error: expected NEWLINE, got ,
DIM A AS INTEGER, B AS INTEGER
END
```

`DIM SHARED`:

```pbas-error
' expect-error: expected AS, got A
DIM SHARED A AS INTEGER
END
```

implicit variables:

```pbas-error
' expect-error: undefined variable A; declare it with DIM or a UI binding
A = 1
END
```

`LET`:

```pbas-error
' expect-error: expected =, got A
DIM A AS INTEGER
LET A = 1
END
```

`DOUBLE`, `LONG`, `SINGLE`, `BYTE`:

```pbas-error
' expect-error: unknown type DOUBLE
DIM A AS DOUBLE
END
```

type suffixes `%`, `!`:

```pbas-error
' expect-error: unexpected character '%'
DIM A% AS INTEGER
END
```

type suffix `#`:

```pbas-error
' expect-error: expected AS, got #
DIM A# AS REAL
END
```

`SWAP`:

```pbas-error
' expect-error: expected =, got A
DIM A AS INTEGER
DIM B AS INTEGER
SWAP A, B
END
```


### Control flow

single-line `IF`:

```pbas-error
' expect-error: expected NEWLINE, got A
DIM A AS INTEGER
IF A = 0 THEN A = 1
END
```

`ELSEIF`:

```pbas-error
' expect-error: expected =, got A
DIM A AS INTEGER
IF A = 0 THEN
ELSEIF A = 1 THEN
END IF
END
```

`ELSE IF` on one line:

```pbas-error
' expect-error: expected NEWLINE, got IF
DIM A AS INTEGER
IF A = 0 THEN
ELSE IF A = 1 THEN
END IF
END
```

`ENDIF` as one word:

```pbas-error
' expect-error: expected =, got NEWLINE
DIM A AS INTEGER
IF A = 0 THEN
ENDIF
END
```

numeric conditions:

```pbas-error
' expect-error: IF requires BOOLEAN condition, got INTEGER
DIM A AS INTEGER
IF A THEN
END IF
END
```

`DO … LOOP`:

```pbas-error
' expect-error: expected =, got NEWLINE
DO
LOOP
END
```

`DO WHILE`:

```pbas-error
' expect-error: expected =, got WHILE
DIM A AS INTEGER
DO WHILE A < 3
END
```

`REPEAT … UNTIL`:

```pbas-error
' expect-error: expected =, got NEWLINE
REPEAT
END
```

`END WHILE`:

```pbas-error
' expect-error: expected NEWLINE, got WHILE
DIM I AS INTEGER
WHILE I < 3
I = I + 1
END WHILE
END
```

`EXIT DO`:

```pbas-error
' expect-error: expected NEWLINE, got DO
EXIT DO
END
```

a REAL `FOR` counter:

```pbas-error
' expect-error: FOR counter X must be INTEGER
DIM X AS REAL
FOR X = 1 TO 3
NEXT X
END
```

a variable `STEP`:

```pbas-error
' expect-error: STEP must be a non-zero INTEGER constant
DIM I AS INTEGER
DIM S AS INTEGER
FOR I = 1 TO 9 STEP S
NEXT I
END
```


### Procedures

calling a SUB without `CALL`:

```pbas-error
' expect-error: expected =, got 1
SUB S(N AS INTEGER)
END SUB
S 1
END
```

`DEF FN`:

```pbas-error
' expect-error: expected =, got FN
DEF FN SQ(X) = X * X
END
```

`DECLARE SUB`:

```pbas-error
' expect-error: expected =, got SUB
DECLARE SUB S
END
```

recursion:

```pbas-error
' expect-error: recursive CALL is not allowed: F -> F
FUNCTION F(N AS INTEGER) AS INTEGER
RETURN N * F(N - 1)
END FUNCTION
END
```

`BYREF`:

```pbas-error
' expect-error: parameter BYREF needs a type
SUB S(BYREF A AS INTEGER)
END SUB
END
```

`BYVAL`:

```pbas-error
' expect-error: parameter BYVAL needs a type
SUB S(BYVAL A AS INTEGER)
END SUB
END
```

array parameters:

```pbas-error
' expect-error: parameter X needs a type: X AS INTEGER
SUB S(X() AS INTEGER)
END SUB
END
```

`LOCAL` arrays:

```pbas-error
' expect-error: LOCAL arrays are not supported
SUB S
LOCAL A(3) AS INTEGER
END SUB
END
```


### Strings and numbers

`MID$` as a statement:

```pbas-error
' expect-error: expected ), got ,
DIM A$ AS STRING
MID$(A$, 1, 1) = "J"
END
```

STRING + number:

```pbas-error
' expect-error: operator + requires numbers (or STRING + STRING), got STRING and INTEGER
MESSAGE "a" + 1
END
```

`HEX$`:

```pbas-error
' expect-error: unknown function HEX$
MESSAGE HEX$(255)
END
```

`&H` literals:

```pbas-error
' expect-error: unexpected character '&'
DIM A AS INTEGER
A = &HFF
END
```

`\` integer division:

```pbas-error
' expect-error: unexpected character '\\'
DIM A AS INTEGER
A = 7 \ 2
END
```

`LOG10`:

```pbas-error
' expect-error: unknown function LOG10
DIM X AS REAL
X = LOG10(100)
END
```

`RND` without an argument:

```pbas-error
' expect-error: undefined variable RND
DIM X AS INTEGER
X = RND
END
```


### Machine access, sound and time

`PEEK`:

```pbas-error
' expect-error: unknown function PEEK
DIM A AS INTEGER
A = PEEK(100)
END
```

`POKE`:

```pbas-error
' expect-error: expected =, got 100
POKE 100, 1
END
```

`USR`:

```pbas-error
' expect-error: unknown function USR
DIM A AS INTEGER
A = USR(0)
END
```

`CALL` of machine code:

```pbas-error
' expect-error: expected IDENT, got 32768
CALL 32768
END
```

`SOUND`:

```pbas-error
' expect-error: expected =, got 440
SOUND 440, 1
END
```

`PLAY`:

```pbas-error
' expect-error: expected =, got C
PLAY "C"
END
```

`SLEEP` / `WAIT`:

```pbas-error
' expect-error: expected =, got 1
SLEEP 1
END
```

`TIMER` as a function:

```pbas-error
' expect-error: undefined variable TIMER
DIM X AS INTEGER
X = TIMER
END
```

`DATE$` / `TIME$`:

```pbas-error
' expect-error: undefined variable DATE$
DIM D$ AS STRING
D$ = DATE$
END
```


### Graphics

`PSET`:

```pbas-error
' expect-error: expected ), got ,
PSET (1, 1)
END
```

`LINE (x,y)-(x,y)`:

```pbas-error
' expect-error: expected ), got ,
LINE (1, 1)-(10, 10)
END
```

`DRAW CIRCLE` and other shapes:

```pbas-error
' expect-error: expected CLEAR, FILL, INVERT, BOX, LINE, PIXEL, TEXT, SCROLL or INK after DRAW, got CIRCLE
WINDOW "W"
CANVAS 100, 100
BUTTON "Quit", Quit
SUB Quit
EXIT
END SUB
DRAW CIRCLE 10, 10, 5
END
```


### Files

`INPUT #`:

```pbas-error
' expect-error: expected =, got #
DIM A$ AS STRING
INPUT #1, A$
END
```

`WRITE #`:

```pbas-error
' expect-error: expected =, got #
WRITE #1, "x"
END
```

`OPEN … FOR APPEND` / `RANDOM`:

```pbas-error
' expect-error: APPEND and RANDOM are not available on the floppy
OPEN "A.TXT" FOR APPEND AS #1
END
```

channel `#3` and above:

```pbas-error
' expect-error: a file channel is #1 or #2
OPEN "A.TXT" FOR INPUT AS #3
END
```

a variable file name in `FILESAVE`:

```pbas-error
' expect-error: this file name must be written in the program as a string, such as "NOTES.TXT", or be a CONST
DIM F$ AS STRING
FILESAVE F$, "x"
END
```

**See also:** [chapter 9](09-errors-and-diagnostics.md) (reading compiler
messages); [LANGUAGE-SPEC.md](../../LANGUAGE-SPEC.md) §8 and §10;
[limitations](../limitations.md).
