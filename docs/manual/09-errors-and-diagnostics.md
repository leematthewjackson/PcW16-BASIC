# 9. Errors and diagnostics

This chapter shows how the compiler reports problems, how a program reports
a failure when it runs, what `check` does and does not catch, the memory
messages, and the compiler's surprises you should know about. The normative
text is [LANGUAGE-SPEC.md](../../LANGUAGE-SPEC.md) §8. For problems with
installing, building or running in XAnne, see
[troubleshooting](../troubleshooting.md).

## 9.1 Compile-time messages

A compile error stops the build. Nothing is written to the `.PRG`. The
message names the file, line and column, then the rule broken:

```text
notes.pbas:12:5: undefined variable TOTAL; declare it with DIM or a UI binding
lib/forms.pbas:45:3: ...          an error inside an included file: its own name and line
```

Both `pcw16basic check` and `pcw16basic build` print messages in this form
and exit with a non-zero status. Only the first error is reported: fix it and
build again.

**Messages you will meet often**

| Message | Usually means |
|---|---|
| `undefined variable X; declare it with DIM or a UI binding` | a missing `DIM`; a misspelt name; or a canvas function (`MOUSEX` …) in a program without a CANVAS |
| `F is a FUNCTION: call it as F() (with parentheses, even when it takes no arguments)` | a FUNCTION called without `()`, even one declared without them ([chapter 5](05-procedures.md)) |
| `expected =, got …` | the first word of the line is not a statement PcW16 BASIC knows, so it was read as an assignment: `GOSUB 100`, `INPUT A$`, `LET A = 1`, `DO`, `CLS`. See [chapter 17](17-unsupported.md) |
| `expected NEWLINE, got …` | extra words at the end of a statement: a single-line `IF`, `END WHILE`, `ELSE IF`, `EXIT DO`, several names after `DIM` |
| `unexpected character ':'` (or `;`, `&`, `\`, `%`) | a character the language does not use |
| `cannot assign REAL to INTEGER variable A (convert with CINT, which rounds; CINT(INT(x)) or CINT(FIX(x)) drops the fraction)` | a REAL needs `CINT` to become an INTEGER ([chapter 2](02-variables-and-types.md#24-real)) |
| `operator + requires numbers (or STRING + STRING), got STRING and INTEGER` | use `STR$` |
| `IF requires BOOLEAN condition, got INTEGER` | write a comparison: `IF N <> 0 THEN` |
| `cannot assign a 13-character literal to S$ with capacity 6` | a string that can never fit ([chapter 2](02-variables-and-types.md#23-string-and-string--n)) |
| `recursive CALL is not allowed: F -> F (…)` | rewrite with a loop ([chapter 5](05-procedures.md#57-recursion-and-call-depth)) |
| `X is a record of TYPE T: use one of its fields …` | records are used field by field |
| `A(11) is outside the array: its elements are A(1) to A(10)` | a literal index outside the array's bounds ([chapter 2](02-variables-and-types.md)) |

**Example**

```pbas-error
' expect-error: undefined variable GRETING$; declare it with DIM or a UI binding
DIM Greeting$ AS STRING
Greeting$ = "Hello"
MESSAGE Greting$
END
```

The compiler's own messages are mostly generic for statements that do not
exist: `GOSUB 100` gives `expected =, got 100`, not "GOSUB is not supported".
[Chapter 17](17-unsupported.md) lists each common construct with the message
it gets.

## 9.2 Warnings

A warning does not stop the build; the `.PRG` is written. Read warnings: they
point at programs that may stop when run.

- `LABEL X$ can hold 63 characters but a LABEL shows at most 24; a longer
  value stops the program with "string too long" (cut it, e.g. LEFT$(text,
  24), or use lib/app.pbas AppSay)`.
- `only N bytes left in the resident 16K block; --runtime-banks all moves
  runtime code out of it (tools/memreport.py shows where they go)`: the
  program is close to the memory limit (§9.6).
- `DIM T inside S declares a variable for the whole program (it keeps its
  value between calls); use LOCAL T AS ... for one that belongs to this
  procedure` ([chapter 5](05-procedures.md#56-dim-inside-a-procedure-declares-a-global)).
- `MOUSEX is also a built-in function: everywhere in the program, MOUSEX
  means this variable, not the built-in (choose another name to use both)`:
  a variable, parameter or LOCAL hides a built-in
  ([chapter 5](05-procedures.md#58-a-function-may-not-take-a-built-ins-name)).

`check` prints the same warnings as `build`.

## 9.3 `check` and `build`

```sh
pcw16basic check notes.pbas     everything except Pasmo and the memory fit
pcw16basic build notes.pbas     everything: front end, layout, code, Pasmo, the .PRG
```

`check` needs no Pasmo. It runs the syntax and type checks, the window layout
and code generation, and prints the same warnings as `build`. When it finds
nothing it prints `OK: notes.pbas (N statements, M variables); syntax, type,
layout and code checks passed. No PRG generated: whether it fits the PcW16's
memory is checked by build.` So it catches, for example, a WINDOW with no
BUTTON, seven BUTTONs, controls that do not fit the window, a CANVAS too wide
for its window and a TEXTBOX bound to a string of more than 63 characters.
(Up to M13 `check` ran only the front end, and these were found only by
`build`.)

| Found only by `build` | Message |
|---|---|
| a program too large for memory | `the resident part is N bytes, …` / `assembled image is N bytes, …` (§9.6) |

```pbas-error
' expect-error: a WINDOW needs at least one BUTTON
WINDOW "W"
LABEL "x"
END
```

```pbas-error
' expect-error: the dialog has no room for this LABEL
WINDOW "W"
LABEL "1"
LABEL "2"
LABEL "3"
LABEL "4"
LABEL "5"
BUTTON "Quit", Quit
SUB Quit
    EXIT
END SUB
END
```

Always finish with `build`. `pcw16basic check --help` and
`pcw16basic build --help` list the options
([chapter 16](16-building-and-commands.md)).

## 9.4 Runtime errors

When a program meets an error it cannot continue from, it shows an alert

```text
Runtime error: <what went wrong> at line N
```

and, when the user dismisses it, **ends**: an open window is removed, open
files are closed and memory blocks are given back. There is no `ON ERROR`
and no way to continue. N is the physical line of the source file, counting
every line from 1 (comments and blank lines included). For a line inside an
included file, N is the program line described in
[chapter 1](01-program-structure.md#16-include); the build lists each file's
range.

```pbas
' expect-message: Runtime error: index out of range at line 5
DIM A(3) AS INTEGER
DIM I AS INTEGER
I = 4
A(I) = 1
END
```

**Common runtime errors**

| Error | Cause | Prevent it by |
|---|---|---|
| `string too long` | a value longer than its STRING; a dynamic LABEL over 24 characters | `LEFT$`, a larger `STRING * n`, `LEN` tests |
| `substring position out of range` | a negative count, or a start below 1 in `MID$`/`INSTR` | test before you cut |
| `division by zero` | `/` or `MOD` by 0, or `0 ^` a negative | `IF B <> 0 THEN` |
| `number out of range` | `VAL` or `CINT` outside −32768..32767; a REAL over 1.7E+38; a NUMBERBOX or SLIDER value outside its range; a negative shift | `ISNUM`, range tests |
| `character code out of range` | `CHR$` outside 1..255 | |
| `function argument out of range` | `SQR` or `LOG` of a bad value | |
| `index out of range` | an array index outside 1..n, a database Count or index entry out of range | test the index |
| `label text has an unsupported character` | a dynamic LABEL value outside printable ASCII | |
| `text position out of range`, `the TEXT buffer is full`, `TEXT INSERT text has a line break` | TEXT buffers ([chapter 7](07-text-buffers.md)) | `TEXTLINES`, `TEXTLEN`, `TEXTFREE` |
| `not enough free memory for BANKED arrays` | at start-up, the PcW16 could not give the blocks | smaller BANKED arrays |
| `not enough free memory for the program's code`, `the program's code could not be read from its file` | a code-banked program at start-up ([chapter 16](16-building-and-commands.md)) | run the whole `.PRG` from its own folder under its own name |
| `the canvas is not on screen`, `drawing outside the canvas` | drawing ([chapter 12](12-drawing.md)) | draw in PAINT; keep coordinates inside |
| `list count out of range`, `list position out of range`, `a CHOICE must show an item from 1 to its count` | LIST and CHOICE ([chapter 10](10-windows-and-controls.md)) | |

File problems are **not** runtime errors: they set `IOERR`
([chapter 6](06-files.md#68-error-behaviour)).

## 9.5 Line numbers and included files

- Compile errors in an included file name that file and its own line.
- Runtime errors use program lines: the main file keeps its own; the *k*-th
  included file starts at B + 1000 × (k − 1) + 1, where B is the first
  multiple of 1000 above the main file's last line. The build prints
  `included: lib/x.pbas: lines 1001..1999` for each.
- A message that quotes another line ("first declared at line …") gives the
  program line.

## 9.6 Memory messages

A `.PRG` has one 16K block that holds the main line, every ordinary variable
and array, the window and menu definitions and the resident runtime. SUBs
and FUNCTIONs are moved to code banks automatically when the program is too
large; BANKED arrays, TEXT buffers and BITMAPs live outside the block.
[memory](../memory.md) explains the layout and how to read
`pcw16basic memory`.

| Message | What to do |
|---|---|
| `the resident part is 27616 bytes, 11232 over the 16384-byte first block even with every procedure in a code bank: …` | move main-line work into SUBs; make large arrays BANKED or give strings a smaller `STRING * n`; `pcw16basic build` already retries with `--runtime-banks all`, so this message from it means even that did not fit |
| `assembled image is 26841 bytes, over the 16384-byte .PRG image limit: …` | the same problem in a program with no procedures to move: move work into SUBs, or data to BANKED arrays |
| `procedure is N bytes of code, over the …-byte limit of one code bank` | split the procedure (one may have at most 15,866 bytes of code) |
| `BANKED arrays may use at most 32 16K blocks together (512K); this one brings the total to 233` | smaller BANKED arrays, TEXT buffers and BITMAPs |
| `this statement reads 5 BANKED array elements; at most 4 are allowed` | copy some elements into variables first |
| `only N bytes left in the resident 16K block` (warning) | as for the first row, before it becomes an error |

```pbas-error
' expect-error: the resident part is
DIM A(250) AS STRING * 63
DIM B(150) AS STRING * 63
SUB S
    MESSAGE "x"
END SUB
CALL S
END
```

`tools/memreport.py` (or `pcw16basic memory`) shows where the bytes go.

## 9.7 Compiler surprises

These behaviours are current. Each has a workaround. Known issues are listed
in [limitations](../limitations.md).

| Behaviour | What happens | Workaround |
|---|---|---|
| `check` does not check the memory fit | a program too large for the resident 16K block passes `check` and fails in `build` (§9.3) | always `build` before you copy a program |
| `DIM` inside a SUB or FUNCTION | declares a global (by the specification), with a warning | use `LOCAL` ([chapter 5](05-procedures.md#56-dim-inside-a-procedure-declares-a-global)) |
| a variable, parameter or LOCAL named like a built-in without arguments (`MOUSEX`, `SECONDS` …) | hides the built-in where it is visible, with a warning | choose another name |
| a SUB named like a built-in function | accepted, but the built-in can then not be used: `LEN is a SUB: use CALL LEN(…) as a statement` | never reuse a built-in name ([chapter 5](05-procedures.md#58-a-function-may-not-take-a-built-ins-name)) |
| a SUB named like a statement word, such as `SHOW` | must be run with `CALL`. Without it the line is read as the SHOW statement: `Show` alone gives `expected IDENT, got NEWLINE`, and `SHOW X`, where X is not a window, gives a message that ends `to call the SUB SHOW, write CALL Show` | always `CALL` it, or choose another name |
| `cannot assign REAL to INTEGER …` | `INT` and `FIX` return a REAL, so they do not help alone | `CINT(x)`, or `CINT(INT(x))` |

**Fixed in M14.** These were defects up to M13 and are now compile errors, as
the specification says: `D = E` for two TEXT buffers, `B = C` for two
BITMAPs, assigning to a BITMAP parameter, statements between `SELECT CASE`
and the first `CASE`, a FUNCTION named like a built-in, and a literal index
outside an array. `KEYDOWN` or `lib/keys.pbas` in a program without a CANVAS,
and a BITMAP parameter in a program without a `DIM … AS BITMAP`, now build
(they used to fail in Pasmo). `--help` after a `pcw16basic` command works.
The TEXTBOX and `EOF`/`IOERR` messages now name the real cause.

```pbas-error
' expect-error: B is a BITMAP and cannot be assigned
DIM B AS BITMAP * 8, 8
DIM C AS BITMAP * 8, 8
B = C
END
```

**See also:** spec §8; [troubleshooting](../troubleshooting.md),
[limitations](../limitations.md), [memory](../memory.md).
