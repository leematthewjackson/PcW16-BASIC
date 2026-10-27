# Troubleshooting

Problems are listed by what you see. Every message quoted here was produced with the current compiler, and file names and numbers are from those runs. A few help texts name engineering documents that are not in this repository (such as `docs/M13-GRAPHICS-ASSETS.md`); [README.md](README.md#references-in-the-source) maps them to the public pages.

For the language's limits and known defects, see [limitations.md](limitations.md). [manual/09-errors-and-diagnostics.md](manual/09-errors-and-diagnostics.md) explains the message types.

## Installing

### `doctor` prints `FAIL Pasmo is not on PATH`

```text
FAIL Pasmo is not on PATH: install Pasmo 0.5.3 (https://pasmo.speccy.org/) to build .PRG files; 'check' works without it
```

Install Pasmo ([install.md](install.md)) and open a new terminal. `pasmo` with no arguments should print `Pasmo v. 0.5.3`. A build without Pasmo stops with `pasmo assembler not found on PATH`. `check` still works without it.

### `doctor` prints `FAIL` for `examples/lib/sprite.pbas` or `LANGUAGE-SPEC.md`

`doctor` looks for these files beside the `pbas` package it runs from. They are missing in two cases:
- the command was installed with a plain `pip install .`, which copies the package away from the repository. Such a copy is not supported: `pcw16basic` then stops at once with exit status 2 and the message `pcw16basic: this copy of the pbas package has no runtime/, tools/ or examples/lib/ beside it (…)`. Uninstall it and use `python3 -m pip install -e .` instead (editable), or run `python3 pcw16basic ...` from the repository folder;
- the repository copy is incomplete. `python3 tools/verify_public.py` shows which files are missing or changed.

### `doctor` prints `FAIL Python ...`

PcW16 BASIC needs Python 3.10 or later. Install a newer Python. Very old versions may fail before `doctor` can print anything.

### `pip install` says the environment is externally managed

Some Linux distributions forbid `pip install` outside a virtual environment. Make one with `python3 -m venv ~/pcw16-venv`, then install with `~/pcw16-venv/bin/python -m pip install -e .` ([install.md](install.md)).

## Building

### `check` says OK, but `build` fails

`check` runs everything `build` runs except the assembler and the final memory fit. Window layout, button counts, canvas sizes and TEXTBOX capacity are reported by both. What only `build` finds is a program whose resident part does not fit the 16K block:

```text
$ python3 pcw16basic check jumper.pbas
OK: jumper.pbas (1216 statements, 256 variables); syntax, type, layout and code checks passed. No PRG generated: whether it fits the PcW16's memory is checked by build.
$ python3 tools/build.py jumper.pbas
jumper.pbas:1:1: the resident part is 17364 bytes, 980 over the 16384-byte first block even with every procedure in a code bank: ...
```

(`pcw16basic build` then retries by itself; see the next entry.) Always `build` before you copy a program.

### `the resident part is N bytes, ... over the 16384-byte first block`

The main line, all variables and data, the window and menu definitions and the resident runtime must fit the PcW16's first 16K block. Procedures move to code banks automatically, but those parts cannot.

`pcw16basic build` handles the commonest case by itself. When the first build fails this way, it builds again with the runtime's movable sections in a code bank, and says so:

```text
$ python3 pcw16basic build jumper.pbas
(it does not fit the 16K block with the runtime resident: building with --runtime-banks all)
asm: build/jumper.asm (218491 bytes)
prg: build/jumper.prg (36352 bytes, sha256 e1739f94...)
```

`tools/build.py` on its own does not retry, and it reports the failure:

```text
jumper.pbas:1:1: the resident part is 17364 bytes, 980 over the 16384-byte first block even with every procedure in a code bank: ... (tools/build.py --runtime-banks all; pcw16basic build does this by itself)); tools/memreport.py shows where the bytes go
```

Add `--runtime-banks all` yourself in that case. If the program still does not fit, see where the bytes go with `python3 pcw16basic memory PROGRAM.pbas`. Then move work from the main line into SUBs, make large arrays `BANKED`, or lower the string capacity. [memory.md](memory.md) explains each of these.

### String capacity errors

Every STRING has a capacity, fixed when it is declared: `DIM A$ AS STRING * 10`, or the program-wide default of 63 characters. Messages you may meet:

| message | when | what to do |
|---|---|---|
| `cannot assign a 20-character literal to A$ with capacity 11` | `check` or `build`: a literal is longer than the variable (the capacity counts the terminating byte) | declare the variable longer |
| `string capacity must be between 2 and 127` | `build --string-capacity 128` | the default capacity can be 2 to 127 bytes |
| `a TEXTBOX holds at most 63 characters, but NOTE$ can hold 100 (declare it as DIM NOTE$ AS STRING * 63 or shorter)` | `check` or `build`: a TEXTBOX bound to `STRING * 100` | keep a TEXTBOX's string at 63 characters or fewer |
| `Runtime error: string too long at line 4` | while running: a computed string did not fit its variable | make the variable longer, or cut the value with `LEFT$` |

A dynamic `LABEL` shows at most 24 characters. A longer value also stops the program with `string too long`, so keep label variables at `STRING * 24` or less.

### A message such as `expected =, got 100`

Many statements that other BASICs have do not exist in PcW16 BASIC. The parser reads an unknown word as the start of an assignment, so it reports a plain parser error instead of "not supported":

```text
gs.pbas:2:7: expected =, got 100            (GOSUB 100)
in.pbas:2:7: expected =, got A              (INPUT A)
sif.pbas:3:15: expected NEWLINE, got MESSAGE (a one-line IF ... THEN statement)
d2.pbas:1:8: expected ), got ,              (DIM A(3, 3): two-dimensional arrays)
gt.pbas:2:4: unsupported statement GOTO
pr.pbas:1:1: PRINT to the screen does not exist in PcW16 BASIC: show text with MESSAGE, a LABEL or DRAW TEXT (PRINT #n, value writes a line to an open file)
```

[manual/17-unsupported.md](manual/17-unsupported.md) lists each missing construct, what to use instead, and its exact message.

### `undefined variable X; declare it with DIM or a UI binding`

Every variable must be declared before use, with `DIM`, `LOCAL`, or a control that declares its own variable (TEXTBOX, CHECKBOX, LABEL, RADIO, NUMBERBOX, LIST, SLIDER). Look for a spelling mistake first. The message gives the name in capitals. A FUNCTION called without brackets gives its own message, `F is a FUNCTION: call it as F() (with parentheses, even when it takes no arguments)`: write `F()`, not `F`, even when the FUNCTION was declared without brackets.

## Running

### The program starts and ends at once, or shows nothing

- A program with neither a `WINDOW` nor a `MESSAGE` runs its main line and ends straight away. Nothing appears on screen. This is correct.
- Drawing in the main line is an error, because the window opens only after the main line's `END`:
  ```text
  Runtime error: the canvas is not on screen at line 7
  ```
  Put drawing in the canvas's `PAINT` handler, or in a handler of a button, menu, timer, mouse or key event. PAINT runs when the window opens, and again after a handler that showed an alert ([manual/12-drawing.md](manual/12-drawing.md)).
- Nothing is clipped. A point outside the canvas stops the program with `Runtime error: drawing outside the canvas at line 5`.
- If the program is not in XAnne's File Manager at all, refresh the disc view with Ctrl+L ([running-in-xanne.md](running-in-xanne.md)).

### A picture is not found

`BITMAP LOAD` does not stop the program when a file is missing. It sets `IOERR` to a non-zero code, and the bitmap is not loaded. Check `IOERR` straight after each load, as Tutorial 2 does, and the program can say what is missing. If a picture does not appear:
- the `.PBI` must be in the program's folder, `\PCW\FOLDER01` unless the program was built with `--folder`;
- the name must match exactly, as an 8.3 name (`T3HEROM.PBI`, not `t3hero-mask.pbi`);
- the file must be a PBI1 picture made by `pcw16basic image` or `pcw16basic assets`. `python3 tools/pbicheck.py FILE.PBI` checks one;
- after copying, refresh XAnne with Ctrl+L.

### `DB SAVE` or `BITMAP SAVE` sets `IOERR` 253

Since M14 a save first looks at the two companion files it uses, `NAME.NEW` and `NAME.BAK` (the name with its extension replaced). If either exists and is another kind of file, the save does nothing and sets `IOERR` to 253. This happens when two files share a name and differ only in extension, such as a database `FORM.DSN` and a picture `FORM.PBI`, or when a text file `FORM.BAK` is in the folder. Give each kind of file a name of its own, or write one of them through a temporary name and `SafeReplace` from `lib/files.pbas` ([libraries/files.md](libraries/files.md), known issue KI-91 in [limitations.md](limitations.md)). This behaviour is simulator-tested and awaits the owner's XAnne retest.

### Movement is uneven, or a timer runs fewer times than asked

The handler of `TIMER ... EVERY n TICKS` runs when the clock reaches its due time. If it is late by more than an interval, because of a long handler, an alert or the system's own work, the missed runs are dropped, not queued. In XAnne a `TIMER ... EVERY 1 TICKS` ran its handler 142 to 154 times in 10 seconds instead of 160 while the program was busy (Tested in XAnne; known issue KI-81, docs/limitations.md).

So never count handler runs as time. Read the clock instead, and do as many steps as the time passed covers. `lib/pace.pbas` does this: `PaceStart(2, 4)` once, then `N = PaceSteps()` in each handler run. Programs built this way did 80 steps in 80 for 10 seconds in XAnne, idle and loaded. [TUTORIAL-3-GAME.md](TUTORIAL-3-GAME.md) and [manual/14-timers-and-animation.md](manual/14-timers-and-animation.md) show how.

Two smaller effects remain:
- a key pressed and released between two timer runs may never be seen by `KEYDOWN`. A game that must not miss a tap also takes it from the canvas's `KEYS` handler, as `examples/jumper.pbas` does;
- in a program's first second the clock's fraction can be wrong, so a game started then can lose up to a second of steps once.

### Typing lags, or drawing is slow or wrong in XAnne

Check XAnne's Rosanne acceleration setting. With **Graphics** acceleration selected, typing lagged and drawing was slow and wrong in places. All the recorded results used Graphics acceleration off ([running-in-xanne.md](running-in-xanne.md)).

### A large program fails to start, or fails after it was renamed

A program larger than 16K reads its code banks from its own `.PRG` file. Copy the file whole, run it from the folder you copied it to under the name you gave it, and do not rename it while it runs.

### Still stuck

Run `python3 tools/verify_public.py`. It shows whether your Python and Pasmo reproduce the tested programs exactly. Then compare your program with the nearest example in [../examples/README.md](../examples/README.md).
