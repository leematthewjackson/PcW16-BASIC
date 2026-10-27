# 1. Program structure

This chapter covers how a `.pbas` source file is laid out: lines, comments,
line numbers, letter case, the main line, `END`, `MESSAGE`, `INCLUDE` and
the names programs are given. The normative text is
[LANGUAGE-SPEC.md](../../LANGUAGE-SPEC.md) §1, §5 and §5.11.

Every program in a `pbas` block in this manual is complete and builds. A line
`' expect-message: …` in a block is an ordinary comment to the compiler; it
records the alert the program shows, and `tools/check_docs.py` checks it by
running the program on the project's simulator.

## 1.1 Source text

**Syntax**

```text
statement                      one statement per line
statement   ' comment          a trailing comment
' comment                      a whole-line comment
REM comment                    REM also starts a comment
"text with ""quotes"" inside"  "" is one quote character inside a string
```

**Meaning**

- A source file is UTF-8 text with the extension `.pbas`. Each line holds
  one statement, or nothing, or only a comment.
- `'` starts a comment that runs to the end of the line. `REM` as a whole
  word does the same, at the start of a line or after a statement. A name
  such as `REMARK` is not a comment.
- Keywords and names are case-insensitive: `Dim`, `DIM` and `dim` are the
  same word, and so are `Count` and `COUNT`. Compiler messages show names in
  capitals.
- A string literal is written in double quotes. Two quotes in a row stand
  for one quote character. A string literal cannot run past the end of its
  line.
- Blank lines and indentation have no meaning. Indent blocks for the reader.

**Requires:** nothing.

**Example**

```pbas
' expect-message: He said "hello"
REM A comment line
DIM Greeting$ AS STRING       ' a trailing comment
Greeting$ = "He said ""hello"""
message Greeting$             ' keywords are case-insensitive
END
```

**Common errors**

There is no statement separator and no line continuation:

```pbas-error
' expect-error: unexpected character ':'
DIM A AS INTEGER
A = 1 : A = 2
END
```

A `_` at the end of a line is read as a name, so it gives
`undefined variable _; declare it with DIM or a UI binding`. Write a long
expression across several statements instead, building it up in a variable.

A string must be closed on its own line:

```pbas-error
' expect-error: unterminated string
MESSAGE "no closing quote
END
```

**Limits**

- One statement per line (see [chapter 17](17-unsupported.md) for `:`).
- An expression may be nested at most 100 levels deep; blocks at most 64
  levels deep (spec §8).
- Text that reaches the screen (window captions, labels, alerts) should be
  plain ASCII; the limits for each are in the chapter for that statement.

**Evidence:** tested in XAnne (every example program uses comments and mixed
case).

**See also:** spec §1; `examples/hello_pcw.pbas`.

## 1.2 Reserved words

The words `MOD`, `AND`, `OR`, `NOT` and `XOR` are operators, and the words
below are keywords. None of them can be used as the name of a variable, an
array or a procedure:

```text
AS BOOLEAN BUTTON CALL CHECKBOX DIM ELSE END EXIT FALSE FILELOAD FILESAVE
FOR GOTO IF INTEGER LABEL MESSAGE NEXT PRINT REM STEP STRING SUB TEXTBOX
THEN TO TRUE WEND WHILE WINDOW
```

`GOTO` and `PRINT` are reserved although there is no `GOTO` statement and
`PRINT` exists only as `PRINT #` for files ([chapter 6](06-files.md)).

Other statement words (`FUNCTION`, `LOCAL`, `CONST`, `SELECT`, `CASE`,
`RETURN`, `TYPE`, `DB`, `TEXT`, `BITMAP`, `CANVAS`, `DRAW`, `MENU`, `ITEM`,
`TIMER`, `LIST`, `SHOW` and the rest) are *contextual*: they are statements
only at the start of a statement and not followed by `=`. A program may still
use them as names, but doing so makes it harder to read. Avoid it.

Do not give a procedure the name of a built-in function either: see
[§5.8](05-procedures.md#58-a-function-may-not-take-a-built-ins-name).

## 1.3 Line numbers

**Syntax**

```text
10 statement
```

**Meaning:** a line may start with a number. Line numbers are allowed for
familiarity only; they have no meaning, because there is no `GOTO` or
`GOSUB`. Numbered and unnumbered lines may be mixed. Runtime error messages
always report the *physical* line of the file (counting from 1), not a line
number you wrote.

**Example**

```pbas
' expect-message: 3
10 DIM A AS INTEGER
20 A = 1 + 2
MESSAGE STR$(A)
40 END
```

**Common errors**

```pbas-error
' expect-error: line numbers must strictly increase
20 DIM A AS INTEGER
10 A = 1
END
```

**Limits:** line numbers must strictly increase. A file brought in with
`INCLUDE` may not have line numbers at all
(`an included file may not have BASIC line numbers`).

**Evidence:** compiled and assembled; line numbers produce no code.

**See also:** spec §1; [chapter 17](17-unsupported.md) for `GOTO`.

## 1.4 The main line and `END`

**Syntax**

```text
declarations and statements          the main line, run once, top to bottom
SUB Name ... END SUB                 procedures, anywhere before END
FUNCTION Name(...) AS type ... END FUNCTION
END                                  mandatory, the last statement of the file
```

**Meaning**

- The statements outside any `SUB` or `FUNCTION` form the *main line*. They
  run once, in source order, when the program starts. Procedure definitions
  may sit between main-line statements; they do not run until they are
  called ([chapter 5](05-procedures.md)), and the main line simply continues
  past them.
- `END` must be the last statement in the file. Without a `WINDOW`, the
  program ends when the main line reaches `END`.
- With a `WINDOW` ([chapter 10](10-windows-and-controls.md)), `END` ends the
  main line only: the window then opens and the program waits for clicks,
  keys and timer events, running a handler `SUB` for each, until a handler
  executes `EXIT` (or the user quits the program from the system).
- `EXIT` ends the whole program wherever it runs
  ([chapter 4](04-control-flow.md#47-exit)).
- There is no screen text output: the main line shows results with
  `MESSAGE` alerts (§1.5) or through a window.

**Requires:** nothing.

**Example: a program without a window**

```pbas
' expect-message: start
' expect-message: in the SUB
' expect-message: end
MESSAGE "start"
CALL Middle
SUB Middle
    MESSAGE "in the SUB"
END SUB
MESSAGE "end"
END
```

**Example: a program with a window.** The `MESSAGE` runs first, on the
desktop; when the main line reaches `END`, the window opens and stays until
**Quit** is clicked.

```pbas
' expect-message: The window opens after this alert
WINDOW "Structure"
LABEL "The main line has finished."
BUTTON "Quit", Quit
SUB Quit
    EXIT
END SUB
MESSAGE "The window opens after this alert"
END
```

**Common errors**

```pbas-error
' expect-error: program requires a final END
MESSAGE "no END"
```

```pbas-error
' expect-error: statements after END are not allowed
MESSAGE "one"
END
MESSAGE "two"
```

`END inside an unclosed block` means an `IF`, `FOR`, `WHILE` or `SUB` was
not closed before `END`; `unclosed IF block` (or `FOR`, …) means the file
ended inside one.

**Evidence:** tested in XAnne (all examples; `examples/greeter.pbas` shows
the main line running before its window opens).

**See also:** spec §5; `examples/hello_pcw.pbas`, `examples/greeter.pbas`.

## 1.5 `MESSAGE`: showing a result

**Syntax**

```text
MESSAGE expression$
```

**Meaning:** shows an alert with the text and an OK button, and waits until
the user dismisses it. The program then continues. The expression is any
STRING expression; use `STR$` to show a number. `MESSAGE` works in the main
line, in procedures and in handlers.

**Requires:** nothing.

**Example**

```pbas
' expect-message: Total: 42
DIM Total AS INTEGER
Total = 6 * 7
MESSAGE "Total: " + STR$(Total)
END
```

**Common errors**

A number must be converted first:

```pbas-error
' expect-error: operator + requires numbers (or STRING + STRING)
MESSAGE "Total: " + 42
END
```

The dynamic text of an alert is budgeted at compile time against a 160-byte
buffer: the bytes of the literals, plus the capacity of every STRING variable
named, plus 6 for each `STR$` of an INTEGER (15 for a REAL). Three 64-byte
strings are too many:

```pbas-error
' expect-error: MESSAGE
DIM A$ AS STRING
DIM B$ AS STRING
DIM C$ AS STRING
MESSAGE A$ + B$ + C$
END
```

Give such strings a smaller capacity with `STRING * n`
([chapter 2](02-variables-and-types.md#23-string-and-string--n)), or show
less at once.

**Limits:** a literal alert text is at most 250 bytes
(`MESSAGE literal is 251 bytes; the maximum is 250`); dynamic text as above.
For a question with two or three buttons, use `ASK`
([chapter 10](10-windows-and-controls.md)).

**Evidence:** tested in XAnne.

**See also:** spec §6, §8; `examples/hello_pcw.pbas`, `examples/arith_demo.pbas`.

## 1.6 `INCLUDE`

**Syntax**

```text
INCLUDE "path/file.pbas"
```

**Meaning**

- The line is replaced by the text of the file, as if you had typed it there.
  A library normally holds `TYPE`s, `CONST`s, `DIM`s and `SUB`/`FUNCTION`
  definitions.
- The path is read **relative to the folder of the file that contains the
  `INCLUDE` line** — not the folder you run the compiler from. A program at
  `myapp/myapp.pbas` with `INCLUDE "lib/app.pbas"` reads `myapp/lib/app.pbas`.
  A project made by `pcw16basic new` has a copy of the libraries in its own
  `lib/` folder for this reason ([chapter 16](16-building-and-commands.md)).
- An included file may itself contain `INCLUDE` lines, resolved relative to
  its own folder. The libraries shipped in `examples/lib/` do not include one
  another, so when one library needs another you include both, the needed one
  first (for example `lib/geom.pbas` before `lib/scene.pbas`). See
  [the library guide](../libraries/README.md).
- Inclusion happens on the host when you build. Nothing about it reaches the
  PcW16.

**Requires:** the `INCLUDE` on a line of its own, outside any `SUB` or
`FUNCTION`.

**Example**

```pbas
' expect-message: 10
INCLUDE "lib/geom.pbas"
MESSAGE STR$(GeomClamp(12, 0, 10))
END
```

**Line numbers in messages**

- A compile error inside an included file names that file and its own line,
  for example `lib/forms.pbas:45:3: …`.
- At run time all files are numbered as one program. The *k*-th included
  file is numbered from B + 1000 × (k − 1) + 1, where B is the first multiple
  of 1000 above the main file's last line. In a 480-line program, line 45 of
  the first library is reported as line 1045. The build prints each file's
  range, for example `included: lib/geom.pbas: lines 1001..1999`.

**Common errors**

```pbas-error
' expect-error: no such file
INCLUDE "lib/nothere.pbas"
END
```

```pbas-error
' expect-error: that file is already part of the program
INCLUDE "lib/geom.pbas"
INCLUDE "lib/geom.pbas"
END
```

A library that needs another one not yet included fails with an ordinary
message from inside the library, for example
`scene.pbas:132:5: CALL GEOMUNITE: no SUB GEOMUNITE is defined`.

**Limits**

- An included file has fewer than 1000 lines and no line numbers.
- Each file may be included once (this also prevents cycles).
- As many files as fit below program line 32767.
- Messages that quote another line ("first declared at line …") give the
  program line, not the file's own line.

**Evidence:** compiler tests; every library-based example (for example
`examples/contacts4.pbas`, `examples/jumper.pbas`) is tested in XAnne.

**See also:** spec §5.11; [libraries](../libraries/README.md);
`examples/starter.pbas`, `examples/tutorial/t2_draw.pbas`.

## 1.7 Program names

- The `.PRG` file takes the name of the source file: `notes.pbas` builds
  `build/notes.prg`.
- On the PcW16 the program is copied as an 8.3 name in capitals, for example
  `NOTES.PRG`. Keep source names to **at most 8 letters and digits** (the
  `pcw16basic new` command also allows `_`), so the built file can be copied
  without renaming.
- A program large enough to be built with code banks reads the rest of its
  own `.PRG` when it starts. Run it under the name it was copied with, from
  the folder it is in; do not rename it while it runs (known issue KI-38,
  [limitations](../limitations.md)). See
  [chapter 16](16-building-and-commands.md) and [memory](../memory.md).
- The window title is separate from the file name: `WINDOW "My Notes"`.

**See also:** [first program](../first-program.md),
[running in XAnne](../running-in-xanne.md).
