# Example programs

This folder holds 67 example programs (`examples/*.pbas`), the three tutorial programs
(`examples/tutorial/*.pbas`), the shared libraries they use (`examples/lib/`, described in
[docs/libraries/README.md](../docs/libraries/README.md)) and the PNG sources of their pictures
(`examples/assets/`). Every program listed here builds with the command given for it.

Each entry gives:

- **Source**: the file, relative to the repository root.
- **Build**: the exact command, run from the repository root.
- **Pictures and files**: anything the program loads or writes.
- **What you see**: the expected behaviour, in words. There are no screenshots.
- **Evidence**: how far the behaviour has been checked.
  - *Tested in XAnne* means the project's owner ran the program in the XAnne emulator (Rosanne 1.12).
  - *Simulator only* means it was checked on the project's Z80 and Rosanne model (`tests/z80sim.py`) but not in XAnne.
  - **Nothing here has been run on a real PcW16.** XAnne is an emulator, so a pass there is not hardware evidence.

Known issues are cited as "known issue KI-nn" and are described in
[docs/limitations.md](../docs/limitations.md).

## Contents

- [Building and running an example](#building-and-running-an-example)
- [Prebuilt programs](#prebuilt-programs-in-programs)
- [First steps](#first-steps)
- [General programming](#general-programming)
- [Windows and controls](#windows-and-controls)
- [Drawing and graphics](#drawing-and-graphics): PAINT II, DESIGNER
- [Data and files](#data-and-files)
- [Productivity](#productivity): document editing, database and records, a calculator, reporting and printing
- [Sprites and animation](#sprites-and-animation): SPRITED
- [Games](#games): JUMPER
- [Advanced](#advanced): benchmarks
- [Tutorials](#tutorials)
- [M15: several canvases, fonts, type and Tasks → Stop](#m15-several-canvases-fonts-type-and-tasks--stop): SKETCHPAD, FONTBOOK, STOPGUARD, the type specimen, and the applications that ask before Stop
- [M14 versions](#m14-versions): SPRITED, MDEDIT IV, DESIGNER and the scientific calculator, corrected
- [Earlier versions](#earlier-versions)

## Building and running an example

From the repository root:

```sh
python3 tools/build.py examples/tally.pbas
```

This writes `build/tally.asm` and `build/tally.prg`. The `.prg` is named after the source file.
`python3 pcw16basic build examples/tally.pbas` does the same. If the program is too big for the
resident 16K block, it also retries by itself with `--runtime-banks all`. Pass options such as
`--string-capacity` to either command in the same way. See
[docs/manual/16-building-and-commands.md](../docs/manual/16-building-and-commands.md) for every option.

Some builds print warnings, and most warnings are harmless:

- A warning that a LABEL variable "can hold 63 characters but a LABEL shows at most 24" means the
  program must keep that text short. The examples do.
- A warning that "only N bytes left in the resident 16K block" means the program fits, but with
  little room to spare.

To run a program, copy the `.prg` file into the XAnne PcW16's program folder (`\PCW\FOLDER01` unless
you built with `--folder`). Copy it under a name of at most 8 letters or digits, with the extension
`.PRG`, for example `build/visitor_counter.prg` as `VISITORS.PRG`. Copy any pictures or data files the
program needs into the same folder. Then start it from the PcW16's File Manager.
[docs/running-in-xanne.md](../docs/running-in-xanne.md) gives the steps and the recommended XAnne
settings. With XAnne's Rosanne acceleration set to Graphics, typing and drawing are slow (known issue
KI-68, docs/limitations.md), so turn that setting off.

Programs that save files write them in the build folder. Most write only names of their own, given
below. Run them on a disk where those names hold nothing of value.

### Pictures

Programs that draw icons or sprites load `.PBI` picture files (the PcW16 BASIC bitmap format,
[docs/graphics-assets.md](../docs/graphics-assets.md)). The pictures come from two places:

- **Prebuilt:** [`programs/`](../programs/MANIFEST.md) holds every `.PBI` file the examples load.
- **Built from the PNG sources:** `examples/assets/ASSETS.txt` lists how each `.PBI` is made. Either of
  these commands builds all ten files into `build/`:

  ```sh
  python3 pcw16basic assets
  python3 tools/pbimage.py build examples/assets/ASSETS.txt build
  ```

  (`pcw16basic assets` uses `assets/ASSETS.txt` if your current folder has one, and otherwise
  `examples/assets/ASSETS.txt`.)

| Picture files | Made from | Used by |
|---|---|---|
| `P2ICONS.PBI` | `examples/assets/paint2-icons.png`, six 24 × 24 icons | PAINT II, DESIGNER (both work without it) |
| `JHERO.PBI`, `JHEROM.PBI` | `jumper-hero.png`, eight 16 × 24 frames and their mask | JUMPER |
| `JBUG.PBI`, `JBUGM.PBI` | `jumper-beetle.png`, two 16 × 12 frames and mask | JUMPER |
| `JCOIN.PBI`, `JCOINM.PBI` | `jumper-coin.png`, two 8 × 8 frames and mask | JUMPER |
| `T2ICONS.PBI` | `tutorial-icons.png`, two 24 × 24 icons | Tutorial 2 |
| `T3HERO.PBI`, `T3HEROM.PBI` | `tutorial-hero.png`, three 16 × 16 frames and mask | Tutorial 3 |

No other example loads a picture, except as a file you choose yourself in PAINT II, DESIGNER or SPRITED.

## Prebuilt programs in `programs/`

[`programs/MANIFEST.md`](../programs/MANIFEST.md) lists the ready-built PcW16 programs and pictures. It
gives each file's source, build options, XAnne result and SHA-256 checksum. Copy a program together with
the pictures it loads.

| Program file | Built from | In XAnne |
|---|---|---|
| `PAINT2.PRG` | `examples/paint2_m15.pbas --runtime-banks all` | Tested in XAnne (M15) |
| `DESIGNER.PRG` | `examples/designer_m15.pbas --runtime-banks all` | Tested in XAnne (M15) |
| `SPRITED.PRG` | `examples/sprited_m15.pbas --runtime-banks all` | Tested in XAnne (M15) |
| `MDEDIT4.PRG` | `examples/mdedit4_m15.pbas --runtime-banks all` | Tested in XAnne (M15) |
| `SPECIMEN.PRG` | `examples/m15_specimen.pbas --runtime-banks all` | Tested in XAnne (M15) |
| `SCICALC.PRG` | `examples/scicalc_m14.pbas` | Tested in XAnne |
| `JUMPER.PRG` | `examples/jumper.pbas --runtime-banks all` | Tested in XAnne |
| `T1HELLO.PRG` | `examples/tutorial/t1_hello.pbas --legacy-tasks-stop` | no XAnne run recorded |
| `T2DRAW.PRG` | `examples/tutorial/t2_draw.pbas` | no XAnne run recorded |
| `T3HOP.PRG` | `examples/tutorial/t3_hop.pbas` | Tested in XAnne |

`T1HELLO.PRG` is the 1.0.0rc1 build, kept byte for byte, so it ignores Tasks → Stop; a build of
`t1_hello.pbas` without the option ends on Stop. The folder also holds the ten `.PBI` pictures listed above. With Python 3.13 and Pasmo 0.5.3 on Linux,
building these sources with the options shown reproduces every prebuilt file byte for byte (compare
with `sha256sum`). The other examples are provided as source only.

---

## First steps

These programs have only a main line. Each runs its statements once and shows its results as
alerts. Dismiss each alert (Return, or click OK) to see the next. At `END` the program returns to
the File Manager. None of them reads or writes a file.

| Program | Build | What you see | Evidence |
|---|---|---|---|
| **Hello**: the smallest check that your tool chain works. Source `examples/hello_pcw.pbas`. Copy as `HELLOPCW.PRG`. | `python3 tools/build.py examples/hello_pcw.pbas` | `Hello from PcW16 BASIC`, `Built on the PcW16`, `Dice roll: 4` (computed as 2 + 2, not random) | Tested in XAnne |
| **Arithmetic and comparisons**: signed 16-bit `+ - *`, unary minus and all six comparisons. Source `examples/arith_demo.pbas`. | `python3 tools/build.py examples/arith_demo.pbas` | six alerts: `-21 < 9: yes`, `9 <= 30: yes`, `30 > 9: yes`, `9 >= -9: yes`, `21 = 21: yes`, `270 <> 30: yes` | Tested in XAnne |
| **Nested IF**: three levels of `IF`/`ELSE` choose one of four results. Source `examples/branch_menu.pbas`. | `python3 tools/build.py examples/branch_menu.pbas` | one alert: `Tier: SILVER (77)` | Tested in XAnne |
| **FOR loops**: up, down with `STEP -1`, and a loop that runs zero times. Source `examples/for_walk.pbas`. | `python3 tools/build.py examples/for_walk.pbas` | `Up: 30`, `Down: 15`, `Empty: 99` | Tested in XAnne |
| **WHILE loops**: conditions that change inside the loop. Source `examples/while_wait.pbas`. | `python3 tools/build.py examples/while_wait.pbas` | `Doubled to 64 in 6 rises`, `Shrunk to 1` | Tested in XAnne |
| **Numbers and strings together**: a FOR loop that builds a report with `STR$`, `MID$`, `LEFT$`, `RIGHT$` and `LEN`. Source `examples/mixed_work.pbas`. | `python3 tools/build.py examples/mixed_work.pbas` | `Leg 1 patch RAC at 7 mi`, `Leg 2 patch RAC at 21 mi`, `Leg 3 patch RAC at 42 mi`, `Head TRA tail ING len 8` | Tested in XAnne |

## General programming

String expressions, character codes and procedures, still with alerts only and no files.

| Program | Build | What you see | Evidence |
|---|---|---|---|
| **Word Tools**: reverses and counts letters with computed `MID$` positions, and has assignments that read their own destination. Source `examples/word_tools.pbas`. | `python3 tools/build.py examples/word_tools.pbas` | `Backwards: 61WcP dartsmA`, `Letters a/A: 2`, `Built from the front: 61WcP dartsmA`, `[Amstrad PcW16] has 15 characters` | Tested in XAnne |
| **Number Format**: right-aligned columns, zero padding and a bar of `#`. Source `examples/number_format.pbas`. | `python3 tools/build.py examples/number_format.pbas` | `Row 1:    111\|` and two more rows, `Padded: 00042`, `Bar: ########## (10)`, `Fifth from the end: #` | Tested in XAnne |
| **Char Codes**: a Caesar cipher with `ASC`, `CHR$`, `MOD` and string comparison. Source `examples/char_codes.pbas`. | `python3 tools/build.py examples/char_codes.pbas` | `Coded: KHOOR SFZ16`, `Decoded: HELLO PCW16`, `Code of H is 72, empty gives -1` | Tested in XAnne |
| **Grade report**: SUBs called with `CALL`, and `AND` binding tighter than `OR`. Source `examples/grade_report.pbas`. | `python3 tools/build.py examples/grade_report.pbas` | `Ada lovelace: A (top, no bonus needed)`, `Charles babbage: B`, `Grace: F (resit)`, `2 of 3 passed` | Tested in XAnne |

See [docs/manual/03-expressions-and-functions.md](../docs/manual/03-expressions-and-functions.md) and
[docs/manual/05-procedures.md](../docs/manual/05-procedures.md).

## Windows and controls

Each program runs its main line, then opens a Rosanne window and waits for you. A value you type or
tick reaches the program only when a button or menu item runs a handler. A handler that changes a
bound variable updates the window when it returns
([docs/manual/10-windows-and-controls.md](../docs/manual/10-windows-and-controls.md)). Unless stated
otherwise, these programs read and write no files.

| Program | Build | What you see and do | Evidence and limits |
|---|---|---|---|
| **Tally counter**. Source `examples/tally.pbas`. | `python3 tools/build.py examples/tally.pbas` | Window "Tally Counter" with two labels and the buttons Add, Score and Quit. Each Add shows the click and score, and every third click earns a bonus. Score says "ahead" or "behind" 100. Quit says `Goodbye from Tally`. | Tested in XAnne |
| **Greeter**: a main line that runs before the window. Source `examples/greeter.pbas`. | `python3 tools/build.py examples/greeter.pbas` | First the alert `Preparing greetings for …`, then the "Greeter" window with four labels. Hello greets and counts, and Close ends the program. | Tested in XAnne |
| **Countdown**: loops inside handlers. Source `examples/countdown.pbas`. Copy as `COUNTDWN.PRG`. | `python3 tools/build.py examples/countdown.pbas` | Count adds up a countdown from Start, Longer adds one to Start, and Stop says `Stopped`. | Tested in XAnne |
| **Personal Details**: two TEXTBOXes. Source `examples/details.pbas`. | `python3 tools/build.py examples/details.pbas` | Fields "First name" and "Home town", with the town filled in. Show checks for an empty name and reports, and Clear empties both fields. | Tested in XAnne |
| **Preferences**: CHECKBOXes bound to BOOLEANs. Source `examples/prefs.pbas`. | `python3 tools/build.py examples/prefs.pbas` | Three tick boxes, with Sound already ticked. Summary lists your choices, and All on ticks every box. | Tested in XAnne |
| **Interactive Editor**: a TEXTBOX and a CHECKBOX together. Source `examples/editor.pbas`. | `python3 tools/build.py examples/editor.pbas` | Inspect reports both controls. Keep 5 keeps the first five letters, or the last five if the box is ticked, and writes them back. | Tested in XAnne |
| **Text Tool**: buttons that rewrite a TEXTBOX. Source `examples/text_tool.pbas`. Copy as `TEXTTOOL.PRG`. | `python3 tools/build.py examples/text_tool.pbas` | Reverse reverses the field. Initials shows `Initials: PBc (3 words)` for the starting text and puts the initials in front of it. | Tested in XAnne |
| **Calculator**: whole-number division with `VAL`, `/` and `MOD`. Source `examples/calculator.pbas`. | `python3 tools/build.py examples/calculator.pbas` | Two fields. Divide reports `100 / 7 = 14 remainder 2` for the starting values, puts 14 back in the first field and refuses division by zero. Swap exchanges the fields. It uses INTEGERs only: for decimals, see `examples/scicalc.pbas` (REAL numbers, [Calculator](#calculator)). | Tested in XAnne |
| **Sign-up form**: checks with `AND`/`OR`/`NOT`, `CALL` and `EXIT SUB`. Source `examples/signup_form.pbas`. | `python3 tools/build.py examples/signup_form.pbas` | The first Check reports `Please fix: Tick the box.` and capitalises the name to `Ada`. Tidy is both a button and a procedure. | Tested in XAnne |
| **Visitor counter**: dynamic labels, four buttons in two rows, and a DEFAULT button. Source `examples/visitor_counter.pbas`. Copy as `VISITORS.PRG`. | `python3 tools/build.py examples/visitor_counter.pbas` | Opens with `Inside now: 0 of 5` and `Visitors today: 0, busiest: 0`. In (also Return), Out, Reset and Quit. | Tested in XAnne |
| **Settings panel**: a field, a tick box, a status line and five buttons. Source `examples/settings_panel.pbas`. Copy as `SETTINGS.PRG`. | `python3 tools/build.py examples/settings_panel.pbas` | Opens with `PcW16 user`, the box ticked and `Not saved yet`. Save (Return) writes, Load reads back, Defaults resets and Check reports. **Writes `PBSETUP.TXT`.** | Tested in XAnne |
| **Order form**: RADIO, a NUMBERBOX with a spinner, an `ASK` question, a menu with a tick, keys on buttons and `BEEP`. Source `examples/order_form.pbas`. Copy as `ORDERS.PRG`. | `python3 tools/build.py examples/order_form.pbas` | A large window. Add order (Return or the Green key) asks a question and reports the order, Clear (Red) empties the form, and Options > Beep on add ticks on and off. | Tested in XAnne. One spinner click can step more than once (known issue KI-1, docs/limitations.md). The Stop key on Quit is untested (KI-6). The XAnne-tested build used the old menu-shortcut table (KI-89). |
| **Stopwatch**: a one-second TIMER, TIMER ON/OFF, keys on buttons and a ticked menu item. Source `examples/stopwatch.pbas`. Copy as `WATCH.PRG`. | `python3 tools/build.py examples/stopwatch.pbas` | Start (Green) counts seconds, Stop (Red) stops, Lap (F1) records a lap, and Watch > Reset (Ctrl+R) resets. "Beep each minute" can be ticked. | Tested in XAnne (KI-6 and KI-89 apply as for Order form) |
| **Contact card**: three named windows shown one at a time, `SHOW` and `FOCUS`. Source `examples/contact_card.pbas`. Copy as `CARD.PRG`. | `python3 tools/build.py examples/contact_card.pbas` | The main window summarises a card. Edit opens a large window where Cancel restores the saved values. Options chooses what the summary shows. The Card menu works in every window. | Tested in XAnne (KI-1, KI-6 and KI-89 apply) |
| **Shopping list**: a LIST over a STRING array. Source `examples/shopping_list.pbas`. Copy as `SHOPLIST.PRG`. | `python3 tools/build.py examples/shopping_list.pbas` | Opens with Bread, Milk and Apples and `Pick or add an item`. Type an item and press Add, pick an item to see it, and Remove closes the gap. | Tested in XAnne. **Double-clicking an item should tick it, but in XAnne the double-click (the LIST's ACTION) never runs** (known issue KI-25, docs/limitations.md). Dragging the scroll bar can start off the handle (KI-5). |
| **Tea timer**: a CHOICE drop-down, a SLIDER and a TIMER. Source `examples/tea_timer.pbas`. Copy as `TEATIME.PRG`. | `python3 tools/build.py examples/tea_timer.pbas` | Choose a tea and the slider shows its brewing time (30 to 280 seconds). Start counts down and beeps when the tea is ready. | Tested in XAnne. One slider arrow click can step more than once (KI-2). |
| **Phone book**: parallel arrays and a sorted LIST. Source `examples/phone_book.pbas`. Copy as `PHONES.PRG`. | `python3 tools/build.py examples/phone_book.pbas` | Lovelace, Babbage and Hopper. Pick a name to see the number. Sort orders the names and keeps your selection on its entry. | Tested in XAnne |

Menus, keys and timers are described in
[docs/manual/11-menus-keys-mouse.md](../docs/manual/11-menus-keys-mouse.md) and
[docs/manual/14-timers-and-animation.md](../docs/manual/14-timers-and-animation.md).

## Drawing and graphics

The flagship drawing programs. Both use a CANVAS, the mouse and BITMAPs
([docs/manual/12-drawing.md](../docs/manual/12-drawing.md),
[docs/manual/13-bitmaps-and-sprites.md](../docs/manual/13-bitmaps-and-sprites.md)). The earlier PAINT is
under [Earlier versions](#earlier-versions), and the graphics benchmark is under [Advanced](#advanced).

### PAINT II: a black-and-white drawing program

- **Source:** `examples/paint2.pbas`.
- **Build:** `python3 tools/build.py examples/paint2.pbas --runtime-banks all`. The option is needed. A
  prebuilt `PAINT2.PRG` is in `programs/`.
- **Pictures and files:**
  - It loads `P2ICONS.PBI` for its tool icons, from `programs/` or `python3 pcw16basic assets`. Without
    the file the tools show as letters and everything still works.
  - It opens and saves pictures that you name, as `.PBI` files of up to 544 × 240 pixels. It keeps
    `NAME.BAK` and uses `NAME.NEW` while saving. It writes nothing else.
  - `python3 tools/pbimage.py` converts between PNG and PBI ([docs/graphics-assets.md](../docs/graphics-assets.md)).
- **What you see and do:**
  - A large window. Along the top of the canvas is a palette: six tool icons (Pencil, Line, Box, Filled
    box, Eraser, Select), then nine pattern swatches from black (0) through grey to white (8). The status
    line at the top right shows the tool, the shade, the file name, and `*` when there are unsaved changes.
  - Click a tool or swatch, or press its key on the canvas: P, L, B, F, E, S, and 0 to 8 for the shades.
  - Draw by pressing and dragging. Select drags out a rectangle. You can then drag inside it: an outline
    follows the pointer and the selection moves when you let go. You can also nudge it one pixel at a
    time with the cursor keys, or rub it out with Delete.
  - Edit gives Undo (Ctrl+Z) and Redo (Ctrl+Y), one step each; Cut, Copy and Paste (a pasted copy floats
    at the top left); and Clear.
  - File gives New, Open, Save (Ctrl+S), Save as, Import (brings in a picture as a floating selection)
    and Quit (Ctrl+Q). New, Open and Quit ask about unsaved changes.
- **Evidence:** Tested in XAnne. This covers drawing, patterned fills, selection, moving and nudging,
  the Ctrl shortcuts, and saving and reopening, which gave a valid PBI file. Dragging a selection is
  smooth. The first press on a selection that is not yet floating captures the picture, which takes
  about 0.4 s (an estimate).
- **Limitations:** only one step of undo. Pictures larger than 544 × 240 are refused. One name with two
  extensions shares its `.BAK` file (known issue KI-91, docs/limitations.md). Built with the M14
  compiler, the second save is refused with IOERR 253 instead of replacing the other's backup
  (simulator only); the prebuilt `programs/PAINT2.PRG` is the older build.

### DESIGNER: a visual screen designer

- **Source:** `examples/designer.pbas`.
- **Build:** `python3 tools/build.py examples/designer.pbas --runtime-banks all`. The option is needed.
  The build warns that only 69 bytes are left in the resident block, which is expected. A prebuilt
  `DESIGNER.PRG` is in `programs/`.
- **Pictures and files:**
  - It loads `P2ICONS.PBI` (shared with PAINT II) for its icon objects. Without the file, icons are drawn
    as framed question marks.
  - Designs are saved as `.DSN` files. A `.DSN` file is a PcW16 BASIC database, saved safely with
    `NAME.NEW` and `NAME.BAK` ([docs/manual/08-records-and-databases.md](../docs/manual/08-records-and-databases.md)).
  - Export picture writes a `.PBI`. Export BASIC writes a `.BAS` text file holding `SUB DrawDesign`,
    which another program can INCLUDE.
  - Each export is written to `DSGNTMP.PBI` or `DSGNTMP.BAS` first and then renamed into place. Each
    command forces its own extension, so an export never overwrites the design.
- **What you see and do:**
  - A large window with a 544 × 240 page.
  - The buttons Box, Panel, Label, Button and Icon each add an object at the top left, selected.
  - Click an object to select it: eight handles appear around it. Drag to move it (an outline follows
    the pointer), drag a handle to resize it, or nudge it with the cursor keys.
  - Props (Ctrl+P) edits the caption, place, size and shade. Delete removes the object.
  - Edit gives To front, To back, Duplicate (Ctrl+D) and Snap to grid (steps of 4).
  - File gives New, Open, Save, Save as, Sample, the two exports, Print and Quit.
  - File > Sample draws a mock-up of a dialog box: a light panel with a dark title bar, an icon, a framed
    group, labels, and Print and Cancel buttons. The status reads `9 objects SAMPLE.DSN*`.
- **Evidence:** Tested in XAnne. This covers the sample; selecting, dragging and resizing; properties;
  layering, deleting and duplicating; the shortcuts; saving and reopening, which gave a valid database;
  and the separate export names. **No XAnne result is recorded for File > Print.**
- **Limitations:**
  - If the final rename of an export fails after the old export was deleted, the new export is left in
    `DSGNTMP.*` (KI-90).
  - The program is at its memory limit, with 69 resident bytes free (KI-83).

## Data and files

The PcW16 BASIC file statements are described in [docs/manual/06-files.md](../docs/manual/06-files.md).
The folder a program uses is fixed when you build it (`\PCW\FOLDER01` by default, floppy only). Each of
these programs uses only its own file names, given below.

| Program | Build | What you see and do | Evidence |
|---|---|---|---|
| **File Round Trip**: `FILESAVE` and `FILELOAD`. Source `examples/file_roundtrip.pbas`. Copy as `ROUNDTRP.PRG`. | `python3 tools/build.py examples/file_roundtrip.pbas` | It saves a string, loads it back and compares, then saves a shorter string over it. Alerts: `File saved: PBRTRIP.TXT`, `File loaded: PBRTRIP.TXT`, `Trip 1 OK: PcW16 round trip 42 (19 letters)`, the two file alerts again, then `Trip 2 OK: Short (5 letters)`. **Writes `PBRTRIP.TXT`.** | Tested in XAnne |
| **Missing File**: loading a file that does not exist. Source `examples/missing_file.pbas`. Copy as `MISSING.PRG`. | `python3 tools/build.py examples/missing_file.pbas` | `File not loaded: PBNOFILE.TXT (not found)`, `Still running; Got$ is unchanged`, the same failure again, then `Second try done; Got$ is unchanged`. `PBNOFILE.TXT` must not exist. If you build it with `--folder '\PCW\PBNOFLDR'` (a folder that does not exist), the alerts say `(folder not found)`. Reads only. | Tested in XAnne |
| **File Limits**: files that do and do not fit a STRING. Source `examples/file_limits.pbas`. Copy as `LIMITS.PRG`. | `python3 tools/build.py examples/file_limits.pbas` | You must first make three files (see below). Then: `File loaded: PBEXACT.TXT`, `PBEXACT gives 63 letters`, `File not loaded: PBLONG.TXT (longer than 63 characters)`, `After PBLONG: start`, `File not loaded: PBZERO.TXT (not text)`, `After PBZERO: start`. Reads only. | Tested in XAnne |
| **Mini Notes**: one memo kept in a file. Source `examples/mini_notes.pbas`. Copy as `MININOTE.PRG`. | `python3 tools/build.py examples/mini_notes.pbas` | A text field with Save, Load and Quit. Each click shows `File saved: PBMEMO.TXT` or `File loaded: PBMEMO.TXT` (`(not found)` before the first save). The memo survives quitting and starting again. **Writes `PBMEMO.TXT`.** | Tested in XAnne |
| **Word Sort**: splitting with `INSTR`, sorting, then saving and reloading. Source `examples/word_sort.pbas`. Copy as `WORDSORT.PRG`. | `python3 tools/build.py examples/word_sort.pbas` | `Commas at 5 and 11`, `Fields: pear apple`, `and fig`, the file alerts, `Sorted: apple,fig,pear`, `No grape in 14 characters`. **Writes `PBSORT.TXT`.** | Tested in XAnne |
| **Journal**: a diary of one-line entries, using sequential files (`OPEN`, `PRINT #`, `LINE INPUT #`, `KILL`, `NAME`). Source `examples/journal.pbas`. | `python3 tools/build.py examples/journal.pbas` | On the first run it shows `0 entries` and `New journal`. Add and Delete copy the file through `JOURNAL.TMP`, because a floppy file cannot be appended to. Prev, Next and Find read the file. A read or write problem leaves the journal as it was. Entries hold at most 63 characters. **Reads and replaces `JOURNAL.TXT` and `JOURNAL.TMP`.** | Tested in XAnne |

To prepare the three input files for File Limits, run this on your computer and copy the files into the
PcW16 folder:

```sh
python3 -c "open('PBEXACT.TXT','wb').write(b'E'*63); open('PBLONG.TXT','wb').write(b'L'*64); open('PBZERO.TXT','wb').write(b'ab\0cd')"
```

## Productivity

Complete applications for text, records and reports. They use the libraries in `examples/lib/`
([docs/libraries/README.md](../docs/libraries/README.md)).

### Document editing: MDEDIT IV

- **Source:** `examples/mdedit4.pbas`.
- **Build:** `python3 tools/build.py examples/mdedit4.pbas --runtime-banks all`. The option is needed.
- **Files:**
  - At start it opens `EDTEST.MD` from its folder. Copy `developer-tests/edtest.md` there as `EDTEST.MD`.
    `developer-tests/wraptest.md` is a second test document, with long paragraphs of wide and narrow letters.
  - Saving writes `MDEDIT4.TMP`, reads it back and compares it, keeps the previous file as `NAME.BAK`,
    and then renames the temporary file into place. If any step fails, the old file is kept.
- **What you see and do:**
  - A plain-text and Markdown editor. The page shows 13 rows in Rosanne's proportional font. The caret is
    a thin bar and a selection is shown inverted.
  - With word wrap on (the default), a long line continues on the next rows and breaks between words,
    measured in pixels. Ctrl+W turns wrapping off, and the page then scrolls sideways.
  - Typing, Return, Backspace and Delete edit the text. The cursor keys, Home, End, PgUp and PgDn move;
    with Shift held they extend the selection. Mouse press and drag selects.
  - Menu shortcuts: Ctrl+X, C and V (cut, copy, paste); Ctrl+A (select all); Ctrl+K or f1 (mark);
    Ctrl+Z and Ctrl+Y (undo and redo, 4 steps); Ctrl+S (save); Ctrl+O (open); Ctrl+F (find and replace);
    Ctrl+G (find next); Ctrl+L (go to line); Ctrl+Q (quit, which asks about unsaved changes).
- **Evidence:** Tested in XAnne. This covers wrapping, editing, saving and reopening. The saved file
  differed from the original by exactly the edit made, and no temporary file was left.
- **Limitations:**
  - Up to 30,000 bytes of text, including the clipboard. A row holds at most 120 characters.
  - Each undo step copies the whole text (KI-55).
  - Typing re-measures the rows an edit can change (KI-70).
  - Loading a document reads one byte per operating-system call, so it takes seconds (KI-43).
  - The editing speed has not been timed in XAnne (KI-77).

### Database and records

**CONTACTS IV: an address book.**

- **Source:** `examples/contacts4.pbas`.
- **Build:** `python3 tools/build.py examples/contacts4.pbas --runtime-banks all`. The option is needed.
- **Files:** it reads and replaces `CONTACTS.PDB`, using `CONTACTS.NEW` and `CONTACTS.BAK` while
  saving. This is the same file format as CONTACTS III, below.
- **What you see and do:**
  - A list of name, phone and town in columns. Up, Down, PgUp, PgDn, Home, End or a click choose a row.
    Return edits the row. Delete deletes it after asking.
  - The buttons and menus give Add, Edit, Delete, Find (in names or towns, ignoring case), Show all, Sort
    (by name; by town, then name; by number), Save (Ctrl+S) and Quit (Ctrl+Q, which asks about unsaved
    changes).
  - The status line shows `*` when there are unsaved changes, the count shown out of the total, the
    order, and `found` after a find.
  - A save that stopped halfway is recovered the next time the program starts.
- **Evidence:** Tested in XAnne.
- **Limitations:**
  - Up to 200 contacts. Fields hold up to 30 (name), 20 (phone), 32 (e-mail) and 20 (town) characters.
  - The list shows the first 22, 15 and 12 characters of name, phone and town.

**STARTER: a to-do list to copy and grow.** It is about 130 lines and is the smallest complete
application here.

- **Source:** `examples/starter.pbas`.
- **Build:** `python3 tools/build.py examples/starter.pbas --runtime-banks all`. It also builds without
  the option.
- **Files:** it writes `TODO.PDB`, `TODO.NEW` and `TODO.BAK` and nothing else.
- **What you see and do:**
  - Type a task and press Add. Up, Down or a click choose a task. Done (or Space) ticks or unticks it, and
    Delete removes it.
  - Save is Ctrl+S. Quit (Ctrl+Q) asks about unsaved changes.
- **Evidence:** Tested in XAnne.

**Sales records: data processing on 3,000 records in BANKED arrays.** BANKED arrays live in memory blocks
outside the program.

- **Source:** `examples/records_m8.pbas`. Copy as `RECORDS.PRG`.
- **Build:** `python3 tools/build.py examples/records_m8.pbas`.
- **Files:**
  - It reads `SALES.DAT` and never changes it. It writes `REPORT.TXT`, with one line per region, the
    grand total and the ten largest sales.
  - `SALES.DAT` is a text file with CR LF line ends. The first line is `PBSALES1`. Each later line is one
    sale: `region;quantity;price`, for example `North;12;3.75`. A region has 1 to 12 characters, the
    quantity is 0 to 32767, and the price is 0 to 1E9. There can be at most 20 regions and 3,000 sales.
    `tools/m8_sample_data.py` makes a test file of 3,000 sales in 7 regions (and prints the
    summary line the program should show):

    ```sh
    python3 tools/m8_sample_data.py sample
    ```

    It writes `sample/SALES.DAT` (and `sample/CONTBOOK.DAT`, 150 contacts for
    `examples/contacts_m8.pbas`).
- **What you see:**
  - There is no window. After the program has worked through the file, one alert appears:
    `Report written: 3000 sales, 7 regions`.
  - A bad line is reported by its line number, and then no report is written.
  - It needs 6 free 16K memory blocks.
- **Evidence:** Tested in XAnne. It took about 60 seconds for 3,000 records, because every BANKED element
  access is an operating-system copy call (KI-32).

See [docs/manual/08-records-and-databases.md](../docs/manual/08-records-and-databases.md) and
[docs/memory.md](../docs/memory.md). The earlier address books are under [Earlier versions](#earlier-versions).

### Calculator

**Scientific calculator with statistics.**

- **Source:** `examples/scicalc_m8.pbas`. Copy as `SCISTATS.PRG`.
- **Build:** `python3 tools/build.py examples/scicalc_m8.pbas --string-capacity 24`. The option comes
  from the program's header and gives a number of up to 23 characters. A plain build also succeeds, but
  it is a different, untested program image.
- **Files:** none.
- **What you see and do:**
  - Type x (and y for the two-number operations), choose an operation from the drop-down and click `=`.
    The operations are `+ - * / ^`, square root, exponential, logarithms, trigonometry, and degrees or
    radians.
  - Every entry is checked, and domain or range problems are reported in the window instead of stopping
    the program, with one gap: see the limitations below.
  - Use, Swap, Store and Recall work with the result and the memory. "add x to data" collects numbers
    for a running count, mean and sample standard deviation. "clear data" starts the statistics again.
  - With 2 and 0.5 entered and `x ^ y` chosen, `=` shows `= 1.41421356`.
- **Evidence:** Tested in XAnne.
- **Limitations:** REAL numbers have about 9.6 significant digits (KI-19). `LOG10` is the program's own
  operation, not a built-in function.
- **Overflow guard (known issue KI-104):** the program refuses a result whose logarithm is over
  `CONST BIG = 88.7`, which is about ln(3.3E+38). REAL numbers end at about 1.7E+38 (ln ≈ 88.03), so a
  result between the two passes the check. For example x = 1.5E19, y = 1.5E19 and `x * y` stops the program
  with `Runtime error: number out of range`. `examples/scicalc.pbas` has the same guard. Both programs
  are accepted and unchanged; do not copy the guard (a safe one is in
  [docs/AI-DEVELOPER-GUIDE.md](../docs/AI-DEVELOPER-GUIDE.md#214-runtime-errors)).

### Reporting and printing

**REPORTER: a table, a chart and a printed report.**

- **Source:** `examples/reporter.pbas`.
- **Build:** `python3 tools/build.py examples/reporter.pbas --runtime-banks all`. The option is needed.
- **Files:** it keeps up to 12 named figures in `REPORT.PDB` (with `REPORT.NEW` and `REPORT.BAK`).
  Without that file it starts with sample figures.
- **What you see and do:**
  - The figures as a table beside a bar chart. Up, Down or a click choose a row, and its bar is drawn
    darker.
  - Edit (or Return) opens the row's label and value, and Apply puts them back. Add makes a new row and
    Delete removes the chosen one.
  - Bars and Lines (Ctrl+B, Ctrl+L) switch the chart. Save is Ctrl+S. Print (Ctrl+P) prints the table and
    the bar chart on one A4 page. Quit (Ctrl+Q) asks about unsaved changes.
  - Values are whole numbers from 0 to 20000.
- **Evidence:** Tested in XAnne for the table, the charts, editing and saving.
- **Limitations:**
  - **The printed bar chart failed in XAnne:** the bars printed as merged black blocks. The runtime has
    been corrected, but the correction has not yet been retested in XAnne (known issue KI-79,
    docs/limitations.md).
  - A line chart cannot be printed (KI-74).

**PRINTDEMO: printing a letter, a table and a bar chart.**

- **Source:** `examples/printdemo.pbas`. Copy as `PRINTDMO.PRG`.
- **Build:** `python3 tools/build.py examples/printdemo.pbas`. The comment in the file suggests
  `--runtime-banks all`, but it builds either way.
- **Files:** it writes no files.
- **What you see and do:**
  - Three buttons, each printing one A4 page through Rosanne's print system:
    - Letter: a heading, your name and a paragraph wrapped to the page, signed at the right margin.
    - Table: a ruled table with right-aligned figures and a total.
    - Chart: a bar chart of the same figures.
  - After each page, an alert reports what Rosanne answered.
  - To see the page on a PC, set XAnne's printer to a PCL printer that prints to a file, and convert the
    file with GhostPCL ([docs/manual/15-printing.md](../docs/manual/15-printing.md)).
- **Evidence:**
  - Letter and Table: Tested in XAnne, with margins, wrapping and alignment correct.
  - **Chart: failed in XAnne, and the correction is not yet retested** (KI-79).
  - No real printer has been used (KI-75).

## Sprites and animation

### SPRITED: a sprite and icon editor

- **Source:** `examples/sprited.pbas`.
- **Build:** `python3 tools/build.py examples/sprited.pbas --runtime-banks all`. With
  `python3 pcw16basic build` the option is chosen automatically. A prebuilt `SPRITED.PRG` is in
  `programs/`.
- **Pictures and files:**
  - Type a name of up to 7 letters or digits in the Name field, then use File > Save (Ctrl+S) or
    File > Open (Ctrl+O).
  - `NAME.PBI` holds the frames one below another, and `NAMEM.PBI` holds the masks. They load straight
    into `lib/sprite.pbas`.
  - Saving keeps `NAME.BAK` and `NAMEM.BAK`. Open refuses a file that is not a 16-pixel-wide strip of
    1 to 4 frames with a matching mask.
- **What you see and do:**
  - The canvas shows several parts, from left to right:
    - the current 16 × 16 frame, enlarged 8 times. Click or drag to set or clear cells. Cells the mask
      hides are shown grey.
    - its mask (white is drawn, black is transparent).
    - every frame at actual size.
    - the current frame drawn through its mask over grey.
    - an animation of the frames at four a second.
  - Keys on the canvas: 1–4 choose a frame; Left and Right step between frames; A adds a frame (a copy);
    M makes the mask from the image; F fills the mask; I inverts the image; P pauses the animation; Stop
    quits. The menus have the same commands.
  - New, Open and Quit ask about unsaved changes.
- **Evidence:** Tested in XAnne. This covers drawing, the preview, and saving, which gave valid PBI
  files with backups. The animation runs by itself and pauses with P.
- **Limitations:**
  - After you type in the Name field, single-letter keys may go into the field instead of the canvas.
    This has not been tried in XAnne (known issue KI-87). Every key command is also a menu item, so use
    the menus.
  - There is no statement to set a pixel inside a BITMAP, so the editor draws and captures instead
    (KI-88).

See also Tutorial 3 below, and [docs/manual/13-bitmaps-and-sprites.md](../docs/manual/13-bitmaps-and-sprites.md).

## Games

### JUMPER: a single-screen platform game

- **Source:** `examples/jumper.pbas`.
- **Build:** `python3 tools/build.py examples/jumper.pbas --runtime-banks all`. The option is needed.
  A prebuilt `JUMPER.PRG` is in `programs/`.
- **Pictures:** `JHERO.PBI`, `JHEROM.PBI`, `JBUG.PBI`, `JBUGM.PBI`, `JCOIN.PBI` and `JCOINM.PBI`, from
  `programs/` or `python3 pcw16basic assets`. Copy all six with the program. If one is missing, the game
  says which.
- **What you see and do:**
  - A starry sky, platforms, the ground, the hero, seven coins, two beetles and the title.
  - Hold Left or Right to run. Press Space (or Up) to jump: the jump rises, slows, falls and lands on the
    platform below.
  - Collect every coin and avoid the beetles. Touching a beetle costs one of three lives. When the lives
    are gone, the game is over.
  - P pauses and resumes, and Stop quits.
  - The game moves in steps of 1/8 s of the clock, however often its timer runs (`lib/pace.pbas`). The
    keys held down are read with `KEYDOWN`.
- **Evidence:** Tested in XAnne and completely playable. This covers movement, short presses of Space,
  coins, lives, game over and pause. The game runs without the mouse being moved and leaves no sprite
  trails.
- **Limitations:**
  - A key tapped and released between two timer events is not seen as held. The game catches Space and
    Up taps through its KEYS handler (KI-92).
  - A game started in its first second can lose up to a second of steps once (KI-93).

The guide to writing a game like this is [docs/TUTORIAL-3-GAME.md](../docs/TUTORIAL-3-GAME.md).

## Advanced

Benchmarks: programs that draw a lot, for judging speed in XAnne. They need no files.

| Program | Build | What you see and do | Evidence |
|---|---|---|---|
| **GFXBENCH**: an interactive bar chart. Source `examples/gfxbench.pbas`. | `python3 tools/build.py examples/gfxbench.pbas` | A bar chart of 12 monthly values with axes, labels and a title. Click a bar, or use Left and Right, to select it: it is shown inverted and its value appears in the status line. Up and Down change the value by 5 and redraw only that bar. Run starts a timer that scrolls a continuous zigzag trace along the bottom strip. The trace is a made-up waveform, not the bar values. Stop stops it, and Redraw draws everything again and counts the redraws. | Tested in XAnne |
| **UIBENCH**: a keyboard and mouse list drawn on a canvas. Source `examples/uibench.pbas`. | `python3 tools/build.py examples/uibench.pbas` | 60 records as rows. Up and Down move the inverted selection. PgUp, PgDn and the Page buttons page through the list, Home and End jump, and a click selects a row. The List menu sorts by name (Ctrl+N), by score (Ctrl+S) or reverses (Ctrl+R). Return shows the record in an alert. | Tested in XAnne. Sorting by name compares byte by byte, so `Kestr 10` comes before `Kestr 2` (KI-51). |

## Tutorials

The programs that the three step-by-step tutorials build. Each tutorial's code matches its file exactly.

| Program | Build | Pictures | What you see | Evidence |
|---|---|---|---|---|
| **Tutorial 1**: a window with a label, a text field, buttons and a menu. Source `examples/tutorial/t1_hello.pbas`. Guide [docs/TUTORIAL-1-FIRST-PROGRAM.md](../docs/TUTORIAL-1-FIRST-PROGRAM.md). | `python3 tools/build.py examples/tutorial/t1_hello.pbas` | none | A large window "HELLO". Type your name and press Greet (Return, or File > Greet, Ctrl+G) to see a greeting in the label. Quit is Ctrl+Q. | Simulator only (no XAnne run recorded). Prebuilt as `T1HELLO.PRG`. |
| **Tutorial 2**: a canvas you draw boxes on by dragging, with an icon palette. Source `examples/tutorial/t2_draw.pbas`. Guide [docs/TUTORIAL-2-GRAPHICS.md](../docs/TUTORIAL-2-GRAPHICS.md). | `python3 tools/build.py examples/tutorial/t2_draw.pbas` | `T2ICONS.PBI` | A large window "DRAW" with a canvas and two tool icons. Drag to draw. Clear empties the canvas. Without the picture, the status reads `T2ICONS.PBI is missing`. | Simulator only. Prebuilt as `T2DRAW.PRG`. |
| **Tutorial 3**: a sprite that runs while a key is held, and jumps. Source `examples/tutorial/t3_hop.pbas`. Guide [docs/TUTORIAL-3-GAME.md](../docs/TUTORIAL-3-GAME.md). | `python3 tools/build.py examples/tutorial/t3_hop.pbas` | `T3HERO.PBI`, `T3HEROM.PBI` | A large window "HOP". The status reads `Left / Right, Space`. The hero runs while Left or Right is held, and jumps and lands with Space. | Tested in XAnne. Prebuilt as `T3HOP.PRG`. |

## M15: several canvases, fonts, type and Tasks → Stop

Programs that use what 1.0.0rc2 adds ([manual, chapter 12](../docs/manual/12-drawing.md) and
[chapter 11](../docs/manual/11-menus-keys-mouse.md#tasks--stop-and-on-stop)). None loads a picture or
needs a private file. Each builds with `python3 tools/build.py SOURCE`, plus the option shown.

| Program | Build | What you see | Evidence |
|---|---|---|---|
| **SKETCHPAD**. Source `examples/sketchpad.pbas`. | no option | Two canvases in one window. Click a shade on the Palette (or Left/Right once it has the keyboard); drag on the Pad to draw. **Keys: Palette** and **Keys: Pad** give a canvas the keyboard with `FOCUS`; the arrows move a pen marker on the Pad. **Clear** uses `DRAW ON` from a button. After **Help**'s alert both canvases are painted again and the drawing comes back, because the Pad stores its last 250 dots | Simulator only (`tests/test_m15_examples.py`); every statement it uses is tested in XAnne (M15c) |
| **FONTBOOK**. Source `examples/fontbook.pbas`. | no option | Three pages, from the buttons **Fonts 1-6**, **Fonts 7-12** and **Align**: each font line with a tick at its measured end (`TEXTWIDTH`) and its width in pixels, and an Align page (LEFT, CENTRE, RIGHT about a line) | Simulator only (`tests/test_m15_examples.py`); the fonts, widths and `ALIGN` are tested in XAnne (M15c) |
| **STOPGUARD**. Source `examples/stopguard.pbas`. | no option | A note field with **Keep**, **Save** and **Quit**. Type a note and press **Keep** (Return): the status line says it is not saved. Then choose Rosanne's Tasks → Stop: it asks Save / Discard / Cancel (`ON STOP AppMayClose`, `lib/app.pbas`); Save writes `STOPNOTE.TXT` and ends, Cancel keeps the program. With nothing unsaved, Stop ends at once. Quit asks the same question | Simulator only (`tests/test_m15_examples.py`); `ON STOP AppMayClose` is tested in XAnne in the applications below |
| **SPECIMEN** (the type specimen). Source `examples/m15_specimen.pbas`. | `--runtime-banks all` | Type a sample and **Show**: a Preview canvas draws it in Swiss or Times, bold or italic, at the size clicked on a strip canvas (6 to 72 points); a caption in dialog font 3 gives `TYPEWIDTH` and `TYPEHEIGHT`, right-aligned. Type → "Sizes take keys" lets Left/Right choose sizes. **Print** prints the sample. Tasks → Stop asks `End the type specimen?` | Tested in XAnne (M15c, r2 R5) |

**Applications that ask before Tasks → Stop.** Each `_m15` copy adds one line, `ON STOP AppMayClose`
(or its own question), to its M14 version, and is otherwise the same program. Build each as its original,
naming the `_m15` source. `programs/` holds the PAINT II, DESIGNER, SPRITED and MDEDIT IV builds.

| Source | Copy of | Evidence |
|---|---|---|
| `examples/paint2_m15.pbas` | `examples/paint2.pbas` | Tested in XAnne (M15c S7) |
| `examples/designer_m15.pbas` | `examples/designer_m14.pbas` | Tested in XAnne (M15c S7) |
| `examples/sprited_m15.pbas` | `examples/sprited_m14.pbas` | Tested in XAnne (M15c S7) |
| `examples/mdedit4_m15.pbas` | `examples/mdedit4_m14.pbas` | Tested in XAnne (M15c S7) |
| `examples/contacts4_m15.pbas` | `examples/contacts4.pbas` | Tested in XAnne (M15c S7); uses `CONTACTS.PDB`, as `contacts4.pbas` does |

## M14 versions

Corrected copies of four programs above. Each corrects one known issue and is otherwise the same program;
the program it corrects is kept as it was tested. Build each one as its original, naming the `_m14` source.
Tested on the simulator (`tests/test_m14_apps.py`) and in XAnne; `programs/` holds these builds.

| Source | Corrects | What changed |
|---|---|---|
| `examples/sprited_m14.pbas` | `examples/sprited.pbas`, KI-96 | Save refuses a name ending in M: sprite FOO's mask `FOOM.PBI` would be sprite FOOM's image. Open still takes such a name |
| `examples/mdedit4_m14.pbas` | `examples/mdedit4.pbas`, KI-97 | An `MDEDIT4.TMP` left by an unfinished save is kept as `MDEDIT4.OLD` at start (an alert says so), and a save keeps `NAME.BAK` when `NAME` itself is missing. With both `.TMP` and `.OLD` present saving is off until one is deleted |
| `examples/designer_m14.pbas` | `examples/designer.pbas`, KI-99 | The Files window refuses the name `DSGNTMP`, DESIGNER's own temporary file (`DSGNTMP.PBI: invalid name`) |
| `examples/scicalc_m14.pbas` | `examples/scicalc.pbas`, KI-104 | The overflow guard is ln 88.02 instead of 88.7, so 1.5E19 * 1.5E19 is refused instead of stopping the program. Results within 1% of the REAL limit are refused too |

## Earlier versions

These are superseded programs, kept because the test suite builds and runs them and because they are
simpler to read. Each one was tested in XAnne in its own right. For new work, start from the program
named in the second column.

| Program | Superseded by | Build | What it is | Evidence and limits |
|---|---|---|---|---|
| **Contacts** (text file). Source `examples/contacts.pbas`. | `examples/contacts4.pbas` | `python3 tools/build.py examples/contacts.pbas --string-capacity 32` | An address book of up to 30 names and phones in a LIST, kept in `CONTACTS.DAT` (text lines). Add, update, delete and find. Save writes `CONTACTS.TMP` and then replaces the file, and a lone `.TMP` file is recovered at start. Quit asks before losing changes. **Reads and replaces `CONTACTS.DAT` and `CONTACTS.TMP`.** The option comes from its header, and each field then holds 31 characters. | Tested in XAnne, built with that option. A plain build also succeeds but is a different program image. |
| **Contacts with e-mail** (BANKED arrays). Source `examples/contacts_m8.pbas`. Copy as `CONTBOOK.PRG`. | `examples/contacts4.pbas` | `python3 tools/build.py examples/contacts_m8.pbas --string-capacity 41` | Up to 200 entries of name, phone and e-mail in BANKED arrays. The LIST shows one page of 6 names, and Prev and Next turn the page. Save and Quit are in the Book menu. **Reads and replaces `CONTBOOK.DAT` and `CONTBOOK.TMP`.** Needs 3 free 16K blocks. The option comes from its header and gives a 40-character e-mail field. | Tested in XAnne |
| **CONTACTS III** (database file). Source `examples/contacts3.pbas`. Copy as `CONTACT3.PRG`. | `examples/contacts4.pbas` (same `CONTACTS.PDB` format) | `python3 tools/build.py examples/contacts3.pbas --runtime-banks all` (since M14; `pcw16basic build` does this by itself) | The same commands as CONTACTS IV, with the list drawn by the program itself. **Reads and replaces `CONTACTS.PDB`, `.NEW` and `.BAK`.** | Tested in XAnne. **The status line can grow past 24 characters** (for example after sorting by number, finding and deleting), and the program then stops with "string too long" and unsaved changes are lost (known issue KI-63, docs/limitations.md). CONTACTS IV does not have this fault. |
| **MDEDIT** (the first editor). Source `examples/mdedit.pbas`. | `examples/mdedit4.pbas` | `python3 tools/build.py examples/mdedit.pbas` | A TEXT-buffer editor on a canvas. The caret is a `\|`, and 49 characters of a line are shown, with the page scrolling sideways. Ctrl+S, O, F, G, L and Q. Opens `EDTEST.MD` and saves through `MDEDIT.TMP`. | Tested in XAnne. It has no selection, clipboard, undo or wrap, and the column of a mouse click is an estimate (KI-44). The tested build used the old menu-shortcut table (KI-89). |
| **MDEDIT II** (selection, clipboard, undo, find and replace). Source `examples/mdedit2.pbas`. | `examples/mdedit4.pbas` | `python3 tools/build.py examples/mdedit2.pbas` | A selection shown with `[` and `]` and a grey bar, wrap by 47 characters, and a checked save with `NAME.BAK`. Opens `EDTEST.MD` and saves through `MDEDIT2.TMP`. | Tested in XAnne (KI-55 and KI-70 apply) |
| **MDEDIT III** (proportional text). Source `examples/mdedit3.pbas`. | `examples/mdedit4.pbas` | `python3 tools/build.py examples/mdedit3.pbas --runtime-banks all` | MDEDIT II with the selection shown inverted and a bar caret placed by measuring the text. It wraps after 50 characters, not by width. Saves through `MDEDIT3.TMP`. | Tested in XAnne |
| **PAINT** (the first drawing program). Source `examples/paint.pbas`. | `examples/paint2.pbas` | `python3 tools/build.py examples/paint.pbas --runtime-banks all` | Tools on buttons, a Tool menu or keys (P, L, B, F, E, S), shades 0–8, select, copy and paste, one step of undo, and File > Sample (a picture named `HOUSE.PBI`). It loads no icon file and opens and saves the `.PBI` files you name. | Tested in XAnne. The tested build used the old menu-shortcut table, in which Ctrl+Z, Y, C, V and Q are predicted to choose a shade or the pencil. A build from today's source has the corrected table (KI-89). Undo and memory limits: KI-78. |
| **Scientific calculator** (REAL numbers). Source `examples/scicalc.pbas`. | `examples/scicalc_m8.pbas` | `python3 tools/build.py examples/scicalc.pbas` | The same calculator without the statistics. It is still the simplest example of REAL arithmetic, `ISNUM` and `REALVAL`. Its overflow guard lets some products through, for example 1.5E19 * 1.5E19, which then stops the program with "number out of range" (known issue KI-104, docs/limitations.md). | Tested in XAnne |
