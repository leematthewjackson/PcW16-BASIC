# Your first program

This page takes you from an empty folder to a program running in XAnne. It assumes you have Python, Pasmo and a repository that passes `python3 pcw16basic doctor` ([install.md](install.md)). The commands below were run on Linux, and the output shown is what they printed.

## 1. Make a project

`pcw16basic new` makes a folder with a program to start from. Run it in a folder of your own, outside the repository if you like:

```sh
python3 /path/to/PcW16-BASIC/pcw16basic new hello
```

It prints:

```text
hello/hello.pbas  (a starting point)
hello/lib/         (the libraries: docs/libraries/README.md)
hello/assets/      (PNG pictures and ASSETS.txt)
next: cd hello && python3 /path/to/PcW16-BASIC/pcw16basic build hello.pbas
```

The `next:` line is the command to type next. It says `pcw16basic build hello.pbas` when the
`pcw16basic` command is on your `PATH` ([install.md](install.md#the-pcw16basic-command)), and
otherwise gives the full path of the script you ran.

Running the tools makes Python write `__pycache__/` folders inside the repository folder (not in
your project). Set `PYTHONDONTWRITEBYTECODE=1` to prevent it
([install.md](install.md#getting-pcw16-basic)).

The libraries are described in [libraries/README.md](libraries/README.md) and [LIBRARY-REFERENCE.md](LIBRARY-REFERENCE.md).

The folder holds:

| path | what it is |
|---|---|
| `hello/hello.pbas` | the program: a window with a status line, a drawing area, two buttons and a File menu. Its first lines say how to build it and to copy `build/hello.prg` to the PcW16 as `HELLO.PRG`; the build keeps the case of the source's name, so `pcw16basic new MyApp` gives `build/MyApp.prg` |
| `hello/lib/` | a copy of all 14 libraries from `examples/lib/` (`app.pbas`, `geom.pbas`, `sprite.pbas`, ...) |
| `hello/assets/ASSETS.txt` | an empty picture list, with comments only, for [graphics-assets.md](graphics-assets.md) |

`python3 pcw16basic new hop --kind game` makes the same layout with a small game instead: a black square with two eyes that runs on Left and Right and jumps on Space.

The name must be a PcW16 program name of at most 8 letters, digits and `_`. An existing folder is never touched:

```text
pcw16basic new: hello already exists; choose another name (nothing was written)
pcw16basic new: the name is a PcW16 program name: letters, digits and _, at most 8
```

## 2. Build it

```sh
cd hello
python3 /path/to/PcW16-BASIC/pcw16basic build hello.pbas
```

```text
asm: build/hello.asm (397036 bytes)
prg: build/hello.prg (9686 bytes, sha256 a97a4f732d03b7fba52c54bb40424b9385bb45b012a17f88bf488dd077dbd207)
included: lib/app.pbas: lines 1001..1999
included: lib/geom.pbas: lines 2001..2999
```

`build/hello.prg` is the PcW16 program. The game template builds to `build/hop.prg` (12,822 bytes). The `included:` lines matter when you read errors. A runtime error in an included file reports a line number in that file's range, so line 1047 is line 47 of `lib/app.pbas`.

## 3. What you should see

Copy `build/hello.prg` into XAnne as `HELLO.PRG` and start it ([running-in-xanne.md](running-in-xanne.md) gives the steps). You should see:
- a large window titled `HELLO`, with the status line `Ready` at the top;
- below it, a framed white drawing area 400 × 160 pixels across, with `Click to draw a box` written at its top left;
- **Clear** and **Quit** buttons, and a **File** menu whose **Quit** item has the shortcut Ctrl+Q.

Each click in the drawing area draws a 10 × 10 box there, and the status line counts them: `1 boxes`, `2 boxes`, and so on. **Clear** wipes the area and shows `Cleared`. **Quit**, or Ctrl+Q, ends the program.

*Evidence:* this template is built by the test suite and run on the project's simulator, where one click gives `1 boxes` and the box. No XAnne run of it is recorded, and it has not been tested on a real PcW16. The game template is in the same position.

## 4. A program of your own

Replace the contents of `hello.pbas` with this program, which needs no window:

```pbas
' HELLO: a first program. It shows three alerts, one after another.
' expect-message: Hello, PcW16
' expect-message: 1 + 2 = 3
' expect-message: Goodbye
DIM Name$ AS STRING * 20
DIM A AS INTEGER
DIM B AS INTEGER

Name$ = "PcW16"
MESSAGE "Hello, " + Name$
A = 1
B = 2
MESSAGE STR$(A) + " + " + STR$(B) + " = " + STR$(A + B)
MESSAGE "Goodbye"
END
```

Each `MESSAGE` is a Rosanne alert with an **OK** button, and the next line runs when you dismiss it. After the last alert the program ends and you are back where you started it. Every variable must be declared with `DIM` before it is used. There is no `PRINT` to the screen and no `INPUT` ([manual/17-unsupported.md](manual/17-unsupported.md)).

Build it again with the same `build` command. It prints `prg: build/hello.prg (1452 bytes, ...)`. The `' expect-message:` comments are ordinary comments. This documentation uses them to check that the program shows those alerts on the simulator.

## 5. `check` and `build`

```sh
python3 /path/to/PcW16-BASIC/pcw16basic check hello.pbas
```

`check` runs everything `build` runs except the assembler and the final memory fit: syntax, declarations and types, the window layout and code generation. It works without Pasmo and writes no file:

```text
OK: hello.pbas (10 statements, 3 variables); syntax, type, layout and code checks passed. No PRG generated: whether it fits the PcW16's memory is checked by build.
```

So `check` also catches a WINDOW with no BUTTON, more than 6 buttons, a CANVAS too wide for its window, controls that do not fit, and a TEXTBOX bound to a string longer than 63 characters:

```pbas-error
' expect-error: a WINDOW needs at least one BUTTON
DIM A AS INTEGER
WINDOW "NOBUTTON"
LABEL "hi"
END
```

```text
$ python3 pcw16basic check nobut.pbas
nobut.pbas:3:1: a WINDOW needs at least one BUTTON: a window without buttons has no tested way to be closed (add, for example, BUTTON "Quit", Quit with a SUB Quit that runs EXIT)
```

**Only `build` checks that the program fits.** A program whose resident part does not fit the PcW16's 16K block passes `check` and fails `build` ([troubleshooting.md](troubleshooting.md)).

So use `check` while you type, and always `build` before you copy a program anywhere.

## 6. Reading an error message

Misspell a variable on purpose. Make a second project with `pcw16basic new typo`, and in `typo.pbas` change the last line but one, `CALL AppSay("Ready")`, to `CALL AppSay(Mesage$)`:

```text
$ python3 pcw16basic check typo.pbas
typo.pbas:47:13: undefined variable MESAGE$; declare it with DIM or a UI binding
```

A message has the form **file:line:column: what is wrong**. Names are shown in capitals, because PcW16 BASIC does not distinguish case in names. Nothing is built when there is an error, and the exit status is 1.

Some messages for common mistakes:

```pbas-error
' expect-error: undefined variable GRETING$
DIM Greeting$ AS STRING * 24
Greting$ = "Hello"
MESSAGE Greeting$
END
```

```pbas-error
' expect-error: cannot assign a 20-character literal
DIM A$ AS STRING * 10
A$ = "this is far too long"
MESSAGE A$
END
```

```pbas-error
' expect-error: program requires a final END
MESSAGE "no END"
```

A statement that conventional BASICs have but PcW16 BASIC lacks often gives a plain parser message, not "not supported". For example, `GOSUB 100` gives `expected =, got 100`, and `INPUT A` gives `expected =, got A`. [manual/17-unsupported.md](manual/17-unsupported.md) lists them, and [manual/09-errors-and-diagnostics.md](manual/09-errors-and-diagnostics.md) explains the messages.

Errors that only the running program can find are shown as an alert, `Runtime error: ... at line N`, and the program then ends cleanly. For example, a string that grows past its capacity gives `Runtime error: string too long at line 22`. PcW16 BASIC never cuts text short without telling you.

## 7. Change, rebuild, replace

The usual cycle:
1. edit `hello.pbas`;
2. `check` it, then `build` it (the build replaces `build/hello.prg`);
3. copy `build/hello.prg` over the old `HELLO.PRG` in XAnne's folder, refresh XAnne's disc view, and start it again ([running-in-xanne.md](running-in-xanne.md#rebuilding-and-replacing-a-program)).

Copy over your own program's name only. Never copy over a file that holds data you want to keep.

## Next

- [TUTORIAL-1-FIRST-PROGRAM.md](TUTORIAL-1-FIRST-PROGRAM.md): a window, a text field, buttons and a menu, line by line.
- [TUTORIAL-2-GRAPHICS.md](TUTORIAL-2-GRAPHICS.md) and [TUTORIAL-3-GAME.md](TUTORIAL-3-GAME.md): drawing, pictures, and a sprite that runs and jumps.
- [manual/README.md](manual/README.md): the developer manual. [../LANGUAGE-SPEC.md](../LANGUAGE-SPEC.md) settles exactly what each rule says.
