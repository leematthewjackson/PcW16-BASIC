# Testing a program on the simulator

PcW16 BASIC comes with a model of the PcW16 and Rosanne, written in Python
(`tests/z80sim.py`). The project's own tests use it to run programs on a PC, and you can use it
too: to check your program's logic and to repeat a user's clicks and typing in seconds,
before you copy anything to XAnne.

**What it is and is not.** The simulator runs the real `.PRG` your build makes, instruction by
instruction, and models the Rosanne services the runtime calls: windows, controls, events,
files, drawing, the clock. It is a model written from Amstrad's developer documentation and the
project's XAnne sessions, not Rosanne itself. A program that works on the simulator has passed a
strong check, but only XAnne, or a PcW16, shows how it really behaves: the exact look of the
window, timing, and anything the model simplifies (for example, it draws shades 0–3 black and
4–8 white). See [limitations.md](limitations.md), "The simulator is a model".

## Programs that show alerts

For a program whose result is a `MESSAGE` alert and that needs no input, the quickest check is a
documentation-style block: `tools/check_docs.py` builds a Markdown file's ```` ```pbas ````
blocks, runs each one on the simulator, and compares its alerts with the block's
`' expect-message:` lines. See [CONTRIBUTING.md](../CONTRIBUTING.md).

## Scripting a user

A program with a window waits for the user, so the simulator needs to be told what the user
does. You give it a list of **events**. Here is the program to test, `hello.pbas`:

```pbas
DIM Name$ AS STRING * 20
DIM Greeting$ AS STRING * 24

WINDOW Main, "HELLO", LARGE
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

And a Python script beside it, `simtest.py`, that presses **Greet** with the field empty, then
types a name and presses it again:

```python
# Run hello.pbas on the PcW16 BASIC simulator with a scripted user.
#   python3 simtest.py PATH/TO/pcw16-basic
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(repo), str(repo / "tests")]
from memguard import guarded_run, string_var  # the simulator, with memory checks
from pbas import check_source
from pbas.layout import build_dialog

source_path = Path(__file__).with_name("hello.pbas")
source = source_path.read_text(encoding="utf-8")

# find the window's object numbers: buttons by caption, fields by variable
program = check_source(source, path=source_path)
layout = build_dialog(program, program.windows[0], False)
button = {o.text: o.number for o in layout.objects if o.kind == "BUTTON"}
field = {row.var_name: row.number for row in layout.bindings}

def session(events):
    run = guarded_run(source, path=source_path, events=events)
    assert run.violations == [], run.violations[:3]          # no write outside its variables
    assert not [a for a in run.alerts if a.startswith("Runtime error")], run.alerts
    return run

run = session([("click", button["Greet"])])
print(string_var(run, "GREETING$"))                          # Type your name first
run = session([("edit", field["NAME$"], "Ann"), ("click", button["Greet"])])
print(string_var(run, "GREETING$"))                          # Hello, Ann
```

```sh
python3 simtest.py ../pcw16-basic
```

It prints `Type your name first` and then `Hello, Ann`. (Checked: this exact pair of files was
run against this repository.)

How it works:

- `guarded_run(source, path=…, events=[…])` builds the program with the real compiler and
  Pasmo, with procedures in code banks when it is over 16K, and runs it until the events run
  out or the program exits. It does **not** add the runtime bank the way `pcw16basic build`
  does when the resident part does not fit: for such a program pass
  `build_options={"runtime_sections": "all"}` (the same as `--runtime-banks all`). It also
  checks every memory write: `run.violations` lists any write outside the program's own
  variables, which would be a compiler or runtime fault worth reporting. A run the model had
  to stop (for example one longer than `max_steps`, below) is also reported there, as
  `run aborted: …`.
- `run.alerts` is the text of every alert shown, in order, including any `Runtime error: …`.
- `string_var(run, "NAME$")` reads a STRING variable at the end of the run. Variable names are
  in capitals, as the compiler stores them.
- Controls are addressed by **object number**. `build_dialog` gives you the window's layout:
  `layout.objects` (each with `kind`, `text` and `number`) and `layout.bindings` (each with
  `var_name` and `number`), so you can find a button by its caption and a field by its variable.
- `program.windows[0]` is the first window; a program with several uses `windows[1]` and so on.
- The third argument of `build_dialog` says whether the program has a menu bar (it sets one
  byte of the dialog's header so the menus work while the window is open). Object numbers do
  not depend on it, so `False` is fine for finding them.
- The program is built in a new folder inside the system's temporary folder (Python's
  `tempfile`, so `TMPDIR` applies), which is deleted after the build. Nothing is written beside
  your program.

## Events

These are the event forms the project's own tests use. Each is a Python tuple.

| event | what the user does |
|---|---|
| `("click", obj)` | clicks the button with object number `obj` |
| `("pick", obj, row)` | clicks row `row` of the LIST `obj`; rows are numbered from 0, so `Sel` becomes `row + 1`. `obj` is the LIST's entry in `layout.bindings` |
| `("drop", obj, entry)` | chooses entry `entry` (from 0) of the CHOICE `obj` |
| `("edit", obj, "text")` | types `text` into the text field `obj` (replacing what was there) |
| `("menu", m, i)` | chooses entry `i` of menu `m`: the program's menus are numbered from 1 in source order (0 is Rosanne's own menu), entries from 0, and divider lines (`ITEM "-"`) are not counted |
| `("press", ascii, shift)` | presses a key while the window is shown (for example Return, 13) |
| `("key", ascii)` | a plain keyboard event |
| `("mdown", x, y)`, `("mmove", x, y)`, `("mup", x, y)` | presses, drags and releases the left mouse button at screen position x, y |
| `("hold", "RIGHT", True)` | starts holding a key (for `KEYDOWN`); `False` releases it |
| `("wait", n)` | lets n sixteenths of a second pass with nothing happening |
| `("timer", 0)` | delivers the program's TIMER event |
| `("exit",)` | Rosanne asks the program to close |

When the list runs out, the run stops as if the user had walked away, and you inspect the
result. Mouse positions are on the screen, so add the canvas's position
(`layout.canvas[1]`, `layout.canvas[2]`) to a point inside it.

## More of the model

These are the other options the project's tests use most. All are keyword arguments of
`guarded_run` unless they say otherwise.

**Questions.** `alert_answers=[…]` answers each alert that has more than one button, in order.
Buttons are numbered from 0 in the order the program gives them, so for
`Answer = ASK("Save?", "Yes", "No", "Cancel")` the answer `0` gives `Answer = 1` and `2` gives
`Answer = 3`. An alert with one button (a `MESSAGE`) takes no answer. Without an answer, the
first button is chosen.

**Reading an INTEGER variable.** There is no helper like `string_var`. Find the variable's
address in the symbol table and read two bytes, low byte first:

```python
from pbas.emit import mangle

def integer_var(run, name):                   # name in capitals, e.g. "COUNT"
    at = run.symbols["var_" + mangle(name).lower()]
    value = run.cpu.mem[at] | run.cpu.mem[at + 1] << 8
    return value - 65536 if value >= 32768 else value
```

**How the run ended.** `run.cpu.exited` is True when the program ended. When the events ran
out first, it is False and `run.cpu.idle` is True: the program was still waiting for the user.

**What a canvas showed.** `run.cpu.draw_log` lists every drawing call in order, in screen
coordinates: `("line", x1, y1, x2, y2)`, `("rect", x, y, w, h)`, `("text", x, y, text, mode)`,
`("pixel", …)`, `("bitmap", x, y, w, h)` and so on. Subtract `layout.canvas[1]` and
`layout.canvas[2]` to get canvas coordinates. A sloping line can appear as many short pieces, so
test for the texts, rectangles and positions you expect rather than for one exact list.

**Step limit.** `max_steps=N` is how many Z80 instructions a run may take (5,000,000 by
default), counted over the whole run. A run that has not ended by then (the program exited,
or the events ran out) is stopped, and `run.violations` says `run aborted: SimRunaway: …`.
Raise it for a long session.

**A model disk.** Files live on a `z80sim.Disk`. Give it the files the program should find,
keyed by folder and name in capitals, and read them back after the run:

```python
import z80sim

FOLDER = "\\PCW\\FOLDER01"                     # the default program folder
disk = z80sim.Disk(files={(FOLDER, "PEOPLE.PDB"): open("PEOPLE.PDB", "rb").read()})
run = guarded_run(source, path=source_path, events=events, disk=disk)
saved = disk.file("PEOPLE.PDB")                # bytes, or None if there is no such file
names = sorted(name for (folder, name) in disk.files if folder == FOLDER)
```

`z80sim` is in `tests/`, which the script above already puts on `sys.path`.

**Disk errors.** `z80sim.Disk(files=…, faults_at={fn: {n: code}})` makes the n-th call of
filing function `fn` fail with Rosanne error `code`; every other call works. The functions are
144 open, 145 close, 146 write, 147 read, 153 delete and 154 rename. `n` counts the calls of
that one function on this disk, from 1, including the runtime's own checks (a `DB SAVE` opens
and reads files before it writes), so count the calls of a fault-free run first: the disk
keeps them in `disk.calls`, a dict from function number to count.

**Several sessions on one disk.** To repeat a user who saves, quits and starts the program
again, run it once per session and carry the files over. Make a new `Disk` for each session
from the previous one's files:

```python
disk = z80sim.Disk(files={(FOLDER, "PEOPLE.PDB"): data})
first = guarded_run(source, path=source_path, events=session1, disk=disk)
disk = z80sim.Disk(files=dict(disk.files))     # a fresh disk with the same files
second = guarded_run(source, path=source_path, events=session2, disk=disk)
```

Do not pass the same `Disk` object to a second run. A run that stopped because its events ran
out may have left a file open on the model disk (`disk.open_read`, `disk.open_write`), and the
next run's open of a file would then fail; the call counts behind `faults_at` would also carry
on. After a run that ended with `EXIT`, `disk.open_at_exit` shows what was still open; the
project's tests check that it is `(None, None)`. A file the program was writing when the run
stopped may be incomplete, as it would be after a power cut.

For more patterns (pictures, timers, printing), the test modules in `tests/`
are working examples: [TUTORIAL-3-GAME.md](TUTORIAL-3-GAME.md)'s program, for instance, is
tested with held keys and timer events in `tests/test_m13_tutorials.py`. These Python
interfaces belong to the project's test suite, not to the BASIC language, and may change
between versions.
