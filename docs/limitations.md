# Limitations and known issues

This page lists what does not work, what works only with a restriction, and what has not been checked.
It covers you whether you write PcW16 BASIC programs or only run them. It has four parts:

1. [Platform and evidence gaps](#1-platform-and-evidence-gaps): where the project has and has not been tested.
2. [Compiler limitations](#2-compiler-limitations): what the compiler still does that may surprise you,
   and the audit's defects that M14 fixed. These have no KI numbers.
3. [Open known issues and limitations](#3-open-known-issues-and-limitations), by area. They keep their
   `KI-nn` numbers, because comments in the source code cite them.
4. [Closed issues cited in the source](#4-closed-issues-cited-in-the-source).

Each entry gives the **symptom**, the **cause** where it is known, a **workaround**, and the **evidence**:

- *Tested in XAnne*: the project's owner observed it in the XAnne emulator, running Rosanne 1.12.
- *Simulator only*: shown on the project's Z80 and Rosanne model, `tests/z80sim.py`.
- *Compiler*: shown by compiling or building a program.
- *Static*: from reading Rosanne's documentation or code.

Common BASIC statements that PcW16 BASIC does not have at all (`PRINT` to the screen, `INPUT`, `GOTO`,
`DATA`, `DO … LOOP` and others) are not listed here. They are in
[manual/17-unsupported.md](manual/17-unsupported.md).

---

## 1. Platform and evidence gaps

### Nothing has been run on a real PcW16 (KI-15, KI-85)

- **Symptom:** none known. No PcW16 BASIC program has ever been run on Amstrad PcW16 hardware.
- **What this means:** every runtime result in this documentation comes from the XAnne emulator or from
  the project's simulator. Timing, memory, the floppy drive, the keyboard, printing and the exact screen
  output may all differ on real hardware.
- **Workaround:** none. If you run a program on a real PcW16, treat it as the first test.
  [real-hardware.md](real-hardware.md) describes how to transfer programs.
- **Evidence:** no hardware evidence exists.

### XAnne is an emulator

- **Symptom:** results in XAnne may not match a real PcW16.
- **Cause:** XAnne models the machine. Its RAM size is a setting (2 MB by default). A memory block number
  beyond the fitted RAM wraps round to a lower block, and free-block counts differ from a real machine
  (KI-31).
- **Workaround:** note your XAnne memory setting with any result you report.
- **Evidence:** static, from the emulator's source.

### The simulator is a model, not Rosanne

- **Symptom:** a program that passes in the simulator can still behave differently in XAnne or on a PcW16.
- **Cause:** `tests/z80sim.py` and the build checks model Rosanne's behaviour as far as it is known.
  - An operating-system call costs nothing in the simulator, so it cannot predict speed.
  - The simulator draws grey shades 0 to 3 as black and 4 to 8 as white (KI-82). Rosanne's grey patterns
    are not modelled, and no test checks a pattern's pixels.
  - Where Rosanne's behaviour was misread, the simulator repeats the misreading. This happened once with
    the cursor-key numbers, which XAnne corrected.
- **Workaround:** treat "Simulator only" as a strong check of the program's logic, not of its speed or
  appearance. [first-program.md](first-program.md) and [troubleshooting.md](troubleshooting.md) explain
  how to run a program in XAnne.
- **Evidence:** simulator source and test notes.

### Only Linux has been used for building

- **Symptom:** the build tools are untested on Windows and macOS.
- **Cause:** the compiler and tools have been run only on Linux, with Python 3.13 and Pasmo 0.5.3.
- **Workaround:** the tools are plain Python and should be portable, but any instructions for Windows or
  macOS in [install.md](install.md) are marked *untested*.
- **Evidence:** compiler, on Linux only.

### Printing has been seen only through XAnne (KI-75)

- **Symptom:** it is not known how much a page holds, how long a page takes, or what a real printer
  produces.
- **Cause:** the printed pages were XAnne's printer output, captured as PCL and converted with GhostPCL.
  The owner found the margins, wrapping and alignment correct.
- **Workaround:** none. See also KI-79 and KI-74 below.
- **Evidence:** Tested in XAnne, for text and rules only.

---

## 2. Compiler limitations

The public-readiness audit found a number of compiler defects by compiling probe programs. The M14
revision of the compiler fixed most of them; the list at the end of this part says which. What is
left is below.

### `check` does not check the memory fit

- **Symptom:** `pcw16basic check` (and `python3 -m pbas check`) can accept a program that `build` then
  rejects because its resident part is over 16K.
- **Cause:** `check` runs everything `build` runs except the assembler and the final memory fit: the
  syntax, the types, the window layout and code generation. It prints the same warnings as `build`.
  Its message says so: `syntax, type, layout and code checks passed. No PRG generated: whether it fits
  the PcW16's memory is checked by build.`
- **Workaround:** always confirm with `pcw16basic build`
  ([manual/16-building-and-commands.md](manual/16-building-and-commands.md)). `pcw16basic build` moves
  runtime code out of the resident block by itself when a program does not fit.
- **Evidence:** compiler.

### `DIM` inside a SUB declares a global variable

- **Symptom:** a variable declared with `DIM` inside a SUB or FUNCTION can be seen everywhere, and keeps
  its value after the procedure returns. The same `DIM` in two procedures is refused with `duplicate
  declaration`. The compiler warns: `warning: DIM TOTAL inside SETUP declares a variable for the whole
  program (it keeps its value between calls); use LOCAL TOTAL AS ... for one that belongs to this
  procedure`.

```pbas
' expect-message: inside 5
' expect-message: after 5
SUB Setup
    DIM Total AS INTEGER
    Total = 5
    MESSAGE "inside " + STR$(Total)
END SUB
CALL Setup
MESSAGE "after " + STR$(Total)
END
```

- **Cause:** `DIM` always declares at program level. The specification says so, and programs rely on it.
- **Workaround:** use `LOCAL` for a procedure's own variables. `LOCAL` is reset on every call and cannot
  declare an array ([manual/05-procedures.md](manual/05-procedures.md)).
- **Evidence:** compiler and simulator only.

### A name can hide a built-in function

- **Symptom:**
  - a variable, parameter or LOCAL named like a built-in that takes no arguments (`MOUSEX`, `SECONDS`,
    `KEYCODE` and others) hides the built-in where it is visible. The compiler allows it, because
    programs accepted earlier use such names, but warns: `warning: MOUSEX is also a built-in function:
    everywhere in the program, MOUSEX means this variable, not the built-in (choose another name to use
    both)`;
  - a SUB may have a built-in function's name, with no warning. The built-in then cannot be used in that
    program: `LEN("abc")` is refused with `LEN is a SUB: use CALL LEN(…) as a statement`.
- **Workaround:** do not give your own names to built-ins. The libraries in `examples/lib/` use prefixes
  such as `App`, `List` and `Sprite`, but `lib/forms.pbas` declares the unprefixed names `IsBlank`,
  `IsDigits`, `PadRight$` and `Confirm` ([libraries/README.md](libraries/README.md)). A FUNCTION, or a
  CONST named like a built-in without arguments, is refused, so neither can replace a built-in
  ([manual/05-procedures.md](manual/05-procedures.md#58-a-function-may-not-take-a-built-ins-name)).
- **Evidence:** compiler.

### Unsupported statements give generic messages

- **Symptom:** most BASIC statements that do not exist produce a parser message, not a "not supported"
  message. For example, `GOSUB 100` gives `expected =, got 100`, and `INPUT A$` gives `expected =, got A$`.
  Only `PRINT` has a message of its own.
- **Cause:** an unknown word at the start of a line is read as the name being assigned to.
- **Workaround:** if you see `expected =, got …` on a line that starts with a familiar BASIC keyword, the
  statement does not exist in PcW16 BASIC. [manual/17-unsupported.md](manual/17-unsupported.md) lists them.
- **Evidence:** compiler.

### A plain `pip install .` is not supported

- **Symptom:** after a non-editable `pip install .`, every `pcw16basic` command except `--version` stops
  with exit status 2 and the message `pcw16basic: this copy of the pbas package has no runtime/, tools/ or
  examples/lib/ beside it (…). PcW16 BASIC runs from its own folder: run python3 pcw16basic there, or
  install it with pip install -e . (editable); a plain pip install . is not supported (docs/install.md)`.
- **Cause:** the installed package does not include the runtime, the tools and the libraries.
- **Workaround:** install with `pip install -e .`, or run `python3 pcw16basic …` from the repository
  folder ([install.md](install.md)).
- **Evidence:** tools.

### Fixed in M14

These defects, found during the audit, are fixed in the M14 compiler. They are listed so that older
notes can be followed. Each was confirmed by compiling a program; the details are in the
[changelog](../CHANGELOG.md) and in [LANGUAGE-SPEC.md](../LANGUAGE-SPEC.md) §5.16.

- `KEYDOWN`, or `INCLUDE "lib/keys.pbas"`, in a program without a CANVAS failed in Pasmo
  (`Symbol 'rt_err_msg' is undefined`). It now builds.
- A SUB with a BITMAP parameter in a program with no `DIM … AS BITMAP` (for example one that includes
  `lib/sprite.pbas` or `lib/toolbar.pbas` and declares no bitmap) failed in Pasmo (`rt_bmp_put`,
  `rt_bmp_mask` or `rt_bmp_part` undefined). It now builds. `PAGEWIDTH` without any `PAGE` statement
  now builds too.
- `check` ran only the parser and the type checks. It now also catches a WINDOW with no BUTTON, seven
  buttons, a dialog that overflows, a CANVAS too wide for its window and a TEXTBOX string over 63
  characters.
- `T1 = T2` between TEXT buffers, `B1 = B2` between BITMAPs, assigning to a BITMAP parameter, and
  statements between `SELECT CASE` and the first `CASE` compiled and did nothing. They are now compile
  errors, as the specification says.
- A FUNCTION named like a built-in (`FUNCTION Len`) silently replaced the built-in. It is now a compile
  error, as is a CONST named like a built-in without arguments (`CONST PI = 3`).
- A literal index outside an array (`A(0)` or `A(11)` for `DIM A(10)`) compiled and stopped the program
  at run time. It is now a compile error.
- The TEXTBOX message blamed `--string-capacity`; it now names the variable and its `DIM`. Messages no
  longer contain internal stage names such as `M3b` or `Stage 1`.
- `pcw16basic check --help`, `build --help`, `image --help` and `memory --help` failed; they now show
  the options. `tools/libref.py --help` shows help instead of rewriting the reference, and
  `tools/build.py --help` lists every runtime section `--runtime-banks all` moves.
- `pcw16basic new` named documents that are not in this repository. Its templates now point to
  [manual/README.md](manual/README.md), [libraries/README.md](libraries/README.md),
  [manual/13-bitmaps-and-sprites.md](manual/13-bitmaps-and-sprites.md) and
  [graphics-assets.md](graphics-assets.md).

---

## 3. Open known issues and limitations

### Windows and controls

**KI-1: a NUMBERBOX spinner click can step more than once.** *Open.*
- **Symptom:** one click on a NUMBERBOX's spinner arrow sometimes changes the number by more than one
  step, for example 1, 2, 3, 5, 7, 9.
- **Cause:** not established. A probe saw one press produce three events, but it could not tell
  auto-repeat from duplication.
- **Workaround:** type the number, or check it in the handler.
- **Evidence:** Tested in XAnne (`examples/order_form.pbas`, `examples/contact_card.pbas`).

**KI-2: a SLIDER arrow click can step more than once.** *Open.*
- **Symptom and cause:** as KI-1, for a SLIDER's arrows.
- **Workaround:** drag the slider, or show the value so that the user can correct it.
- **Evidence:** Tested in XAnne (`examples/tea_timer.pbas`).

**KI-5: dragging a list's scroll bar can start off the handle.** *Open, low priority.*
- **Symptom:** the arrows and paging work, but a drag sometimes starts only near the visible handle, not
  on it.
- **Cause:** not diagnosed.
- **Workaround:** use the arrows or page by clicking the track.
- **Evidence:** Tested in XAnne.

**KI-6: some keys are untested.**
- **Symptom:** unknown.
- **What is untested:** the Stop and Help keys as `BUTTON … KEY STOP` or `KEY HELP`, which were not
  mapped in the owner's XAnne; pressing Return while a TEXTBOX is being edited; and using a LIST from the
  keyboard.
- **Workaround:** give such buttons a second way in, such as a menu item.
- **Evidence:** untested.

**KI-8: lists and drop-downs are redrawn after every handler.** *Design choice.*
- **Symptom:** a LIST or CHOICE may flicker after a button is clicked.
- **Cause:** the runtime rebuilds and redraws every LIST and CHOICE after each handler. This keeps them
  correct.
- **Workaround:** none needed.
- **Evidence:** Tested in XAnne.

**KI-9 and KI-10: label lengths.** *Limitation.*
- **Rules:**
  - A LABEL that shows a variable shows at most 24 printable ASCII characters. A longer value, or a
    character outside 32 to 126, stops the program with a runtime error. The build warns when a label's
    variable can hold more than 24 characters.
  - A fixed LABEL text may have up to 47 characters, but it is not measured, so a long text of wide
    letters can be wider than the window.
- **Workaround:** cut dynamic texts with `LEFT$(text, 24)`, or use `AppSay` from `lib/app.pbas`. Keep
  fixed texts short.
- **Evidence:** Tested in XAnne: all 95 printable characters, 24 times each, fitted the window
  (`developer-tests/m5d_labels.pbas`). The rule is kept even though `TEXTWIDTH` now measures text correctly.

**KI-25: a LIST's ACTION (double-click) never runs in XAnne.** *Limitation.*
- **Symptom:** `LIST …, ACTION Handler` compiles, but double-clicking an item never runs the handler.
- **Cause:** in XAnne a double-click on a list arrives as two single clicks, with no double-click event.
  The reason is not established.
- **Workaround:** use a BUTTON that acts on the selected item, as `examples/shopping_list.pbas` should be
  used.
- **Evidence:** Tested in XAnne, with the probe `developer-tests/evprobe.asm`.

**KI-26: a crowded second window looks cramped.** *Open, cosmetic.*
- **Symptom:** the second window of `developer-tests/m6p2_edges.pbas`, which has a 2-row list, a drop-down and
  buttons, looks cramped. No overlap of controls was found.
- **Evidence:** Tested in XAnne.

**KI-59: a handler must not draw after showing a canvas window.** *Design rule.*
- **Symptom:** a handler that runs `SHOW` for the canvas's window and then draws stops with
  `the canvas is not on screen`.
- **Cause:** the window opens only after the handler returns.
- **Workaround:** draw in the canvas's PAINT handler, which runs when the window opens.
- **Evidence:** simulator only (found by tests).

**KI-87: which control has the keyboard focus, a TEXTBOX or the canvas?** *Open.*
- **Symptom:** in a window with both a TEXTBOX and a canvas, keys typed after clicking the canvas may still
  go to the TEXTBOX. `FOCUS` cannot name a canvas.
- **Workaround:** give every key command a menu item as well, as `examples/sprited.pbas` does.
- **Evidence:** untested in XAnne.

### Keys, mouse and timers

**KI-41: only the tested canvas keys are confirmed.**
- **Symptom:** keys outside the tested set may or may not reach a canvas KEYS handler.
- **The tested set:** letters (Shift+A gives 65 with shift 1), Up 224, Down 225, Left 226, Right 227,
  Home 230, End 231, PgUp 232, PgDn 233, Return 13, Backspace 8, Delete 229, Space 32 and Tab 9. Mouse
  press, drag and release also arrive.
- **Keys that never reach KEYS:** a key that a button, a menu or a focused text field owns.
- **Evidence:** Tested in XAnne (`developer-tests/gfxprobe.pbas`).

**KI-60: menu shortcuts may also reach a KEYS handler.** *Mitigated.*
- **Symptom:** possibly, a Ctrl+letter menu shortcut also arrives at the canvas's KEYS handler, so an
  editor could type the letter as well. Whether XAnne delivers it there is not determined.
- **Workaround:** in a KEYS handler, ignore keys typed with Ctrl held (test `KEYSHIFT`), as the MDEDIT
  editors do.
- **Evidence:** Tested in XAnne: the MDEDIT guard works.

**KI-81: timer handler runs are not a count of time.** *Limitation.*
- **Symptom:** a `TIMER … EVERY 1 TICKS` (1/16 s) handler ran 142 to 154 times in 10 seconds, not 160,
  when the program was busy.
- **Cause:** a timer run that comes late is dropped, not caught up. Nothing is queued. For intervals up to
  240 ticks, the program's own event loop runs the timer from the clock.
- **Workaround:** step a game or animation by the clock, not by counting handler runs: use `CLOCKTICKS`
  or `lib/pace.pbas`, as `examples/jumper.pbas` does
  ([manual/14-timers-and-animation.md](manual/14-timers-and-animation.md)).
- **Evidence:** Tested in XAnne (`developer-tests/timeprb.pbas`: 80 of 80 clock steps).

**KI-92: a key tapped between two timer events can be missed.** *Limitation.*
- **Symptom:** `KEYDOWN` reports whether a key is down at that moment, so a key pressed and released
  between two timer events is never seen.
- **Workaround:** also take the key from the canvas KEYS handler, as `examples/jumper.pbas` does for
  Space.
- **Evidence:** Tested in XAnne.

**KI-93: CLOCKTICKS in a program's first second.** *Limitation.*
- **Symptom:** until the program has seen the seconds change once, the fraction of a second that
  `CLOCKTICKS` reports is not in step. A game started in its first second can lose up to a second of
  steps, once.
- **Cause:** XAnne's fine clock byte runs out of step with its seconds. `CLOCKTICKS` counts from the
  first change of the seconds.
- **Workaround:** none needed for most programs.
- **Evidence:** Tested in XAnne: after the first second the clock never went back, and its largest step
  was 2/16 s.

**KI-35: Rosanne's Tasks → Stop is unreliable.** *Rosanne behaviour.*
- **Symptom:** stopping a program from Rosanne's Tasks menu does not always work, and a program stopped
  that way does not run its own exit path.
- **Workaround:** quit with the program's own Quit button or menu item.
- **Evidence:** Tested in XAnne, as an owner observation.

### Drawing and text on the canvas

**KI-39 and KI-76: DRAW TEXT may stop short of the right edge.** *Limitation.*
- **Symptom:** `DRAW TEXT` draws at most (canvas width − x) ÷ 11 characters in one call, whatever the
  text's real width. A line of narrow letters can end well before the edge.
- **Cause:** 11 pixels is the widest character in the font. Measuring instead would change the bytes of
  programs that have already been tested.
- **Workaround:** draw a long line in pieces, measuring with `TEXTWIDTH`, as `examples/mdedit4.pbas`
  does.
- **Evidence:** Tested in XAnne.

**KI-65: `DRAW TEXT x, y, s$, cell` is not for text people read.** *Limitation.*
- **Symptom:** with a cell width, text is drawn on a fixed grid and looks letter-spaced, because the font
  is proportional.
- **Workaround:** use `DRAW TEXT x, y, s$` and place things with `TEXTWIDTH`.
- **Evidence:** Tested in XAnne (`developer-tests/cellprb.pbas`, `developer-tests/rendprb.pbas`).

**KI-40: overlapping DRAW SCROLL.**
- **Symptom:** unknown. `DRAW SCROLL` moved a picture correctly in XAnne, but whether Rosanne copies an
  overlapping area correctly in every direction is not known.
- **Evidence:** Tested in XAnne for up 16 and right 8.

**KI-42: PAINT runs again after an alert.** *Design choice.*
- **Symptom:** after any handler that showed an alert while a canvas was on screen, the canvas's PAINT
  handler runs again.
- **Cause:** it is not documented whether Rosanne restores the area under an alert, so the runtime
  redraws.
- **Workaround:** keep PAINT able to redraw the whole canvas.
- **Evidence:** Tested in XAnne.

**KI-45: limits of TEXT buffers.**
- **Rules:**
  - A TEXT buffer holds up to 65535 bytes, but `TEXTFREE` and `TEXTSIZE` report at most 32767.
  - Bytes over 127 are drawn as Rosanne characters, so UTF-8 shows as two characters. Bytes 0 to 31 and
    224 to 255 are drawn as `?`.
- **Evidence:** specification and simulator.

**KI-29: no string is longer than 127 bytes.** *Limitation.*
- **Symptom:** a string over 127 bytes is a compile-time or runtime "string too long" error. `STRING * n`
  can only make strings smaller.
- **Workaround:** keep long text in a TEXT buffer ([manual/07-text-buffers.md](manual/07-text-buffers.md)).
- **Evidence:** compiler and specification.

**KI-88: there is no pixel access inside a BITMAP.** *Limitation.*
- **Symptom:** no statement sets or reads one pixel of a BITMAP.
- **Workaround:** draw on the canvas and capture it with `BITMAP GET`, or `BITMAP PUT` the picture and
  read it back with `POINT`. `examples/sprited.pbas` works this way.
- **Evidence:** specification.

### Files and databases

**KI-11: FILESAVE and FILELOAD hold one short string.** *Limitation.*
- **Symptom:** a file written with `FILESAVE` holds one string of at most 127 bytes. A failed save after
  the file was opened can leave it empty, because the file is replaced, not written and then renamed.
- **Workaround:** for more data, or for safe saving, use `OPEN`, `PRINT #` and `NAME`, or the database
  statements ([manual/06-files.md](manual/06-files.md)).
- **Evidence:** Tested in XAnne.

**KI-12 and KI-21: the file system.** *Limitation.*
- **Rules:**
  - Files are on the floppy only (`--drive flash` is refused).
  - One file can be open for reading and one for writing at a time.
  - There is no random access and no appending, because Rosanne offers these only on the flash drive.
  - The folder is fixed when the program is built (`--folder`).
- **Correction:** older notes said that file names must be literals and that a CONST is refused. Both are
  out of date:
  - `OPEN`, `KILL`, `NAME`, `TEXT`, `DB` and `BITMAP` accept any STRING expression.
  - `FILESAVE` and `FILELOAD` accept a literal or a CONST.
- **Workaround:** to add to a file, copy it to a temporary file with the new lines and rename it, as
  `examples/journal.pbas` does.
- **Evidence:** Tested in XAnne; the correction was confirmed by compiling.

**KI-16: KILL or NAME on an open file.**
- **Symptom:** unknown. Deleting and renaming work, but what Rosanne does with a file that is still open
  is undocumented and untested.
- **Workaround:** `CLOSE` a file before you delete or rename it.
- **Evidence:** Tested in XAnne, for closed files.

**KI-43: loading a TEXT buffer is slow.** *Limitation.*
- **Symptom:** `TEXT LOAD` of a 5 KB document takes seconds.
- **Cause:** it reads one byte per operating-system call, because Rosanne's results after the end of a
  file are unreliable.
- **Evidence:** Tested in XAnne, but not timed.

**KI-56: DB SORT and DB SEARCH handle at most 250 records.** *Limitation.*
- **Symptom:** the index is an ordinary INTEGER array of at most 250 elements, and a BANKED index is
  refused. A database of more than 250 records cannot be sorted or searched as a whole.
- **Workaround:** sort or search a part of at most 250 records at a time
  ([manual/08-records-and-databases.md](manual/08-records-and-databases.md)).
- **Evidence:** compiler.

**KI-91: files of one name share their .NEW and .BAK.** *Limitation; changed in M14, XAnne retest pending.*
- **Symptom:** `DB SAVE` and `BITMAP SAVE` use `NAME.NEW` and `NAME.BAK`, whatever the file's extension.
  `FORM.DSN` and `FORM.PBI` therefore share `FORM.BAK`. Up to M13, saving one replaced the other's backup.
  Since M14 a save first reads the start of `NAME.NEW` and `NAME.BAK`: if either exists and is another
  kind of file (for `BITMAP SAVE`, one that does not begin `PBI1`; for `DB SAVE`, one that does not begin
  `PDB1`, or whose whole 16-byte header shows another TYPE's signature), the save does nothing and sets
  `IOERR` to 253. So the second of the two saves is refused. A companion shorter than 4 bytes counts as
  a leftover and is replaced. Two files of the same kind (`FORM.PBI` and
  `FORM.IMG`) still share their companions.
- **Workaround:** give different kinds of file different names, or write one of them through a name of its
  own and `SafeReplace` from `lib/files.pbas`, as `examples/designer.pbas` does. Otherwise the save is
  refused.
- **Evidence:** simulator only for the M14 behaviour; the owner's XAnne retest is pending. The M13
  behaviour is the tested behaviour of the examples.

**KI-13: XAnne's File Manager froze while copying.** *Not a compiler issue.*
- **Symptom:** XAnne froze once while copying a file with the PcW16's File Manager.
- **Workaround:** copy files into XAnne's folder from your computer while XAnne is not using it
  ([running-in-xanne.md](running-in-xanne.md)).
- **Evidence:** owner observation.

### Memory and program size

**KI-14: the resident 16K block.** *Limitation.*
- **Symptom:** the build stops with `the resident part is N bytes, M over …`.
- **Cause:** the main line, ordinary variables and arrays, literals, dialog definitions and the resident
  runtime must fit one 16K block. BANKED arrays, TEXT buffers and BITMAPs live outside it. SUB and
  FUNCTION code can move to code banks.
- **Workaround:**
  - Build with `--runtime-banks all`. `pcw16basic build` retries with it automatically.
  - Move work from the main line into SUBs.
  - Make large arrays BANKED.
  - See [memory.md](memory.md) and `tools/memreport.py`.
- **Evidence:** compiler; the runtime bank is Tested in XAnne.

**KI-38: a code-banked program reads its own file when it starts.** *Limitation.*
- **Symptom:** a program built with code banks fails to start if it is not one whole file in its own
  folder, or if there are not enough free 16K blocks (one per bank).
- **Workaround:** copy the whole `.PRG` into the program folder and start it from there.
- **Evidence:** Tested in XAnne.

**KI-83: every STRING FUNCTION call site costs memory.** *Limitation.*
- **Symptom:** each place a STRING-returning FUNCTION is called takes a string cell (65 bytes by default)
  in the resident block.
- **Workaround:** in a large program, pass strings back through a shared variable instead.
  `examples/designer.pbas` does this, and has 69 bytes free.
- **Evidence:** compiler (`tools/memreport.py`).

**KI-28: compiled code is not dense.** *Limitation.*
- **Symptom:** program code is the largest item in most programs.
- **Cause:** the runtime error line is recorded before each statement, and string assignments are staged
  through temporaries.
- **Workaround:** see KI-14.
- **Evidence:** compiler.

**KI-32: BANKED arrays are slow.** *Limitation.*
- **Symptom:** each BANKED element access is one operating-system copy call. Processing 3,000 records in
  `examples/records_m8.pbas` took about 60 seconds.
- **Workaround:** copy BANKED data into an ordinary array for repeated work.
- **Evidence:** Tested in XAnne.

**KI-22 and KI-84: procedures use static storage.** *Limitation.*
- **Rules:**
  - There is no recursion, direct or indirect.
  - At most 16 procedures can be active at once.
  - A CASE value may not call a FUNCTION.
  - A FUNCTION call on the right of `AND` or `OR` is allowed only when the expression is plainly BOOLEAN.
- **Workaround:** use loops instead of recursion ([manual/05-procedures.md](manual/05-procedures.md)).
- **Evidence:** compiler.

**KI-19: REAL precision.** *Limitation.*
- **Rules:**
  - REAL numbers have about 9.6 significant digits, and `STR$` shows 9.
  - `REALVAL` ignores digits after the ninth.
  - `SIN`, `COS` and `TAN` refuse values of more than 51000.
  - There are no REAL FOR counters and no REAL controls.
  - `+ - * /` are correctly rounded. Up to M13, about 1.5% of `+` and `-` results lying just under half
    a unit in the last place were rounded the wrong way, by one unit; M14 corrected this.
- **Evidence:** simulator tests; Tested in XAnne through the calculators. The M14 rounding correction is
  simulator only; the owner's XAnne retest is pending.

### Printing

**KI-79: printed bar charts.** *Corrected; retest in XAnne pending.*
- **Symptom:** in XAnne, the filled bars of a printed chart came out as merged black blocks.
- **Cause:** Rosanne's printer driver draws thick lines wider than its documentation says, so each bar was
  40 points too wide.
- **Fix:** the runtime now sends each solid rectangle so that it prints at its exact size.
- **Status:** the correction is checked against a model of the driver, but **it has not been retested in
  XAnne**. Treat `PAGE FILL` and printed charts (`lib/chartprt.pbas`, `examples/reporter.pbas`,
  `examples/printdemo.pbas`) as experimental.
- **Evidence:** simulator only, with a model checked against the owner's printed page.

**KI-74: pictures, screens and sloped lines cannot be printed.** *Limitation of Rosanne 1.12.*
- **Symptom:** there is no statement to print a BITMAP, a screen or a sloped line. Only text and
  horizontal or vertical lines and boxes can be printed, so a line chart cannot be printed.
- **Cause:** Rosanne's print format holds only characters and horizontal and vertical lines, and its
  screen-print calls are empty in version 1.12.
- **Evidence:** static.

### Programs in examples/

**KI-63: the CONTACTS III status line can overflow.** *Open.*
- **Symptom:** in `examples/contacts3.pbas`, the status line can grow past 24 characters, for example
  after sorting by number, finding a common text and deleting an entry. The program then stops with
  `string too long`, and unsaved changes are lost.
- **Workaround:** use `examples/contacts4.pbas`, which reads the same file and does not have this fault.
- **Evidence:** simulator only. It was not seen in XAnne.

**KI-104: the SCICALC overflow guard is too loose.** *Open; accepted example, unchanged.*
- **Symptom:** `examples/scicalc.pbas` and `examples/scicalc_m8.pbas` refuse a result whose logarithm
  they estimate over `CONST BIG = 88.7`, about ln(3.3E+38). REAL numbers end at about 1.7E+38
  (ln ≈ 88.03), so a result between the two passes the check. For example, 1.5E19 * 1.5E19 stops the
  program with `Runtime error: number out of range`.
- **Workaround:** avoid such results in these programs. Do not copy their guard into your own: use a
  limit of 88.03 or lower, or the tests in
  [AI-DEVELOPER-GUIDE.md](AI-DEVELOPER-GUIDE.md#214-runtime-errors).
- **Evidence:** simulator only (both programs, with x = y = 1.5E19 and `x * y`).

**KI-44: limits of the first MDEDIT.** `examples/mdedit.pbas` has no selection, clipboard, undo or word
wrap, and shows 49 characters of a line at a time. The column of a mouse click is an estimate, and find
is case-sensitive. Use `examples/mdedit4.pbas`.

**KI-55 and KI-70: editor costs.**
- Each undo step in the MDEDIT II to IV editors copies the whole text.
- Each typed character in MDEDIT II and III re-wraps the document.
- Neither has been timed in XAnne.

**KI-77: speed not timed.** The owner reported no slowness in printing or in MDEDIT IV, but neither was
timed in XAnne. Bitmap operations were timed: a GET of 120 × 80 pixels takes 7 ms and a PUT 11 ms.

**KI-78: PAINT and PAINT II keep one undo step.** The picture and its undo copy are two 16K bitmaps.
A failed Open turns undo off. A picture is at most 544 × 240 pixels.

**KI-90: a DESIGNER export can be left under a temporary name.** If the final rename of an export fails
after the old export was deleted, the new export is left in `DSGNTMP.PBI` or `DSGNTMP.BAS`. Rename it
yourself.

**KI-51: UIBENCH sorts names byte by byte.** `examples/uibench.pbas` sorts `Kestr 10` before `Kestr 2`.
This is accepted for a benchmark.

**KI-89: menu shortcuts in some tested builds.**
- **Symptom:** in earlier builds, a menu ITEM without a KEY stopped Rosanne finding the shortcuts of later
  items.
- **Status:** the compiler now gives such items a correct entry, so programs built from today's source are
  not affected.
- **What this changes:** the builds of `examples/stopwatch.pbas`, `examples/order_form.pbas`,
  `examples/contact_card.pbas`, `examples/mdedit.pbas`, `examples/paint.pbas` and `developer-tests/bankprobe.pbas`
  that were tested in XAnne had the old entry. A build from today's source therefore differs from the
  tested one in its menu table. In the old PAINT build, Ctrl+Z, Y, C, V and Q are predicted to choose a
  shade or the pencil.
- `tools/build.py --legacy-menu-hotkeys` reproduces the old builds and is not meant for new programs.
- **Evidence:** Tested in XAnne: PAINT II and DESIGNER shortcuts failed before the fix and passed after it.

### XAnne set-up

**KI-68: slow typing and drawing come from an XAnne setting.**
- **Symptom:** typing lags and screens draw slowly in XAnne.
- **Cause:** XAnne's Rosanne acceleration option was set to Graphics.
- **Workaround:** turn Graphics acceleration off. All the XAnne results in this documentation were
  obtained with it off ([running-in-xanne.md](running-in-xanne.md)).
- **Evidence:** Tested in XAnne.

---

## 4. Closed issues cited in the source

Comments in the compiler, runtime, libraries and examples mention these numbers. They are resolved, and
are listed so that you can follow the references.

| Issue | What it was | Resolution |
|---|---|---|
| KI-3 | Opening a drop-down list with no current item froze XAnne. | The runtime refuses `Sel = 0` or a count of 0 with an error alert, Tested in XAnne. Do not use the "F" variant of the probe `developer-tests/uiprobe3.asm`, which froze XAnne. |
| KI-23, KI-24 | Unused list rows showed stray text, and a deleted entry left a stale row. | Fixed, Tested in XAnne. |
| KI-34 | Rosanne's memory-copy call reports an error when a copy ends exactly at the end of a program's last block, although it copied correctly. | The runtime excuses exactly that case, Tested in XAnne (`developer-tests/banktest.pbas`). |
| KI-46 | Rosanne 1.12 refuses grey shade 8 and reports success differently from its documentation. | Shade 8 is drawn as white, and the result is read correctly, Tested in XAnne. |
| KI-49 | Rosanne 1.12 draws only horizontal and vertical lines. | The runtime draws a sloped `DRAW LINE` itself as short horizontal or vertical runs, Tested in XAnne. A long sloped line costs many calls. |
| KI-50 | GFXBENCH's trace was a row of spikes. | The example now draws a continuous trace. |
| KI-52 | A program with a TEXT buffer and no file statement did not assemble. | Fixed. |
| KI-53 | `tools/memreport.py` failed for code-banked programs. | It now measures the real build. |
| KI-57 | Doubt about database reads that end exactly at the end of a file. | Confirmed to work, Tested in XAnne (`developer-tests/dbprobe.pbas`). |
| KI-61 | A test script expected the wrong result for a damaged database file. | `DB LOAD` recovers from `.NEW`, then `.BAK`, as specified. The case with no valid backup is simulator only. |
| KI-64 | A program whose only string functions were `TRIM$`, `LTRIM$` or `RTRIM$` did not assemble. | Fixed. |
| KI-69 | Rosanne 1.12's text-width call returns the right width with an error flag. | `TEXTWIDTH` ignores the flag, Tested in XAnne. |
| KI-94, KI-95 | PAINT II's selection drag lagged; a timer of ticks stopped when there was no input. | Both fixed, Tested in XAnne. |
