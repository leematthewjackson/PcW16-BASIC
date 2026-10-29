# Changelog

## 1.0.0rc2 — release candidate 2

Release candidate 2 adds the M15 facilities below to 1.0.0rc1. They are tested in XAnne (Rosanne 1.12) by the project's owner: the M15c session and its
focused retest. Nothing is tested on a real PcW16. A short summary is in
[RELEASE-NOTES.md](RELEASE-NOTES.md).

**Compatibility.** Programs that use none of the new statements compile to the same bytes as in
1.0.0rc1, with one exception: a program with menus gains a 4-byte menu-table row so that Tasks → Stop
ends it. A program with one canvas keeps its 1.0.0rc1 code. The new runtime code is assembled only
into programs that use it, and goes to the runtime bank where there is one. `--legacy-tasks-stop`
rebuilds 1.0.0rc1 executables byte for byte.

**Rosanne's Tasks → Stop now works** (KI-35).
- Up to 1.0.0rc1 the runtime ignored it. Now a program with menus ends on Stop, as on `EXIT`.
- `ON STOP Handler` runs a `FUNCTION Handler() AS BOOLEAN` first: TRUE ends the program, FALSE keeps it. The handler may ask a question or save a file.
- `ON STOP AppMayClose` (lib/app.pbas) asks Save / Discard / Cancel when there are unsaved changes.
- The M15 versions of MDEDIT IV, PAINT II, DESIGNER, SPRITED and CONTACTS IV ask before Stop ends them.
- Rosanne shows a program without menus no menu bar, so Stop never reaches it (KI-108). `ON STOP` there gives a warning.
- *Tested in XAnne* (M15c S1–S7).

**Rosanne's twelve dialog fonts.**
- `DRAW FONT n` (1 to 12) chooses the font of later `DRAW TEXT` and `TEXTWIDTH` on that canvas.
- With `DRAW FONT`, text is measured and cut at the last whole character before the right edge. Fonts other than 7 keep half a W + 1 px free there (KI-109).
- `DRAW TEXT x, y, text$ ALIGN LEFT | CENTRE | RIGHT` places measured text about x.
- *Tested in XAnne* (M15c F1–F5, retest R1). The fonts' line heights are not measured, so there is no `TEXTHEIGHT` (KI-106).

**Scalable type on the screen.**
- `TYPE FONT SWISS | TIMES, size [, BOLD] [, ITALIC]` (6, 8, 10, 11, 12, 14, 18, 24, 36 or 72 points) and `DRAW TYPE x, y, text$`: the fonts `PAGE` prints with, drawn on a canvas with the line's top-left at x, y.
- `TYPEWIDTH(text$)` and `TYPEHEIGHT` measure it.
- Screen type and printing can be mixed in one program.
- *Tested in XAnne* (M15c T1–T5, retest R2–R5; printing alongside, T7, provisionally, to PDF). The speed is not measured (T6).

**Several canvases.**
- `CANVAS Name, width, height, …`: up to 8 named canvases, in any of a program's windows.
- Each canvas has its own PAINT, MOUSE and KEYS handlers, and draws on itself while they run. A press gives that canvas the keyboard.
- `DRAW ON Name` chooses where other code draws. `FOCUS Name` gives a canvas the keyboard without a click (KI-87).
- Each canvas keeps its own `DRAW FONT` and `TYPE FONT`.
- The runtime keeps no copy of a drawing: PAINT must draw back what the program keeps (KI-107).
- *Tested in XAnne* (M15c C1–C7, retest R6).

**Examples.** `examples/sketchpad.pbas` (two canvases, `DRAW ON`, `FOCUS`, a drawing PAINT restores),
`examples/fontbook.pbas` (the twelve fonts, their widths, ALIGN), `examples/stopguard.pbas` (Tasks → Stop
without losing work) and `examples/m15_specimen.pbas` (all of it, *tested in XAnne*); the `_m15` copies of
the applications. `programs/` holds the M15 builds of PAINT II, DESIGNER, SPRITED and MDEDIT IV, and SPECIMEN.

**Messages changed.**
- Two `CANVAS` statements without names: `with more than one CANVAS each needs a name …` (was `a program may have one CANVAS …`).
- An unknown `DRAW` word lists `… SCROLL, INK, FONT, TYPE or ON …`.

**Corrections made during M15 acceptance (XAnne).**
- `DRAW TYPE` places the line's top-left at x, y. Rosanne takes y as the baseline, so the text first stood above y, and large sizes drew over the controls above the canvas (KI-105).
- Dialog fonts other than 7, and italic type, keep a small margin at the right edge (KI-109).

**Build option.** `--legacy-tasks-stop` keeps Stop ignored, only to rebuild old executables byte for byte.

## 1.0.0rc1 — release candidate 1 (the Public Preview)

1.0.0rc1 was published by the project's owner as the PcW16 BASIC Public Preview. It is the M13 candidate
described in the next section with the M14 corrections below. The text of both sections is as it was
written before that publication.

### M14 corrections

Corrections to the compiler, the tools and the runtime. The compiler changes
were checked by compiling programs; the runtime changes are tested on the
project's simulator and await the owner's retest in XAnne. Nothing is tested on
a real PcW16. Programs that use none of the changed features compile to the
same bytes as before.

**Compiler: programs that failed to build now build.**
- `KEYDOWN`, or `INCLUDE "lib/keys.pbas"`, in a program without a CANVAS (it
  failed in Pasmo with `Symbol 'rt_err_msg' is undefined`).
- A SUB with a BITMAP parameter in a program with no `DIM … AS BITMAP`, for
  example one that includes `lib/sprite.pbas` or `lib/toolbar.pbas` (`rt_bmp_put`,
  `rt_bmp_mask` or `rt_bmp_part` undefined).
- `PAGEWIDTH` in a program without `PAGE` statements.

**Compiler: `check` runs layout and code generation.** `pcw16basic check` now
runs everything `build` runs except the assembler and the final 16K memory fit,
and prints the same warnings. It now reports a WINDOW with no BUTTON, seven
buttons, a dialog that overflows, a CANVAS too wide for its window and a TEXTBOX
string over 63 characters. A resident block over 16K is still found only by
`build`.

**Compiler: errors the specification asked for.**
- `T1 = T2` between TEXT buffers, `B1 = B2` between BITMAPs, assigning to a
  BITMAP parameter, and any statement between `SELECT CASE` and the first `CASE`
  are compile errors (they compiled and did nothing).
- A FUNCTION may not have a built-in function's name (`FUNCTION Len(…)`; it
  silently replaced the built-in). A CONST may not have the name of a built-in
  without arguments (`PI`, `SECONDS`, `CLOCKTICKS`, `IOERR`, `MOUSEX`, `MOUSEY`,
  `MOUSEEVENT`, `KEYCODE`, `KEYSHIFT`, `DBRECOVERED`). A variable, parameter or
  LOCAL with such a name is still allowed but gives a warning.
- A literal index outside an array (`A(0)`, `A(11)` for `DIM A(10)`) is a
  compile error.
- A `DIM` inside a SUB or FUNCTION still declares a global, and now gives a
  warning. A `DIM` after the first use is accepted.

**Compiler: clearer messages.** A FUNCTION called without `()` says to add them;
`SHOW X`, where X is not a window but the program has a SUB named Show, says to
write `CALL Show`; `LINE INPUT #` into a
record field, a variable file name in `FILESAVE`, `EOF` or `IOERR` without file
statements, a TEXTBOX string that is too long, an array size that is not a
literal, and `PRINT` each have a message that names the rule. Messages no
longer contain internal stage names.

**Tools.**
- `pcw16basic check|build|image|memory --help` shows the options.
- `pcw16basic new` templates point to the public documentation.
- A non-editable `pip install .` is still not supported: `pcw16basic` now stops
  with exit status 2 and says to use `pip install -e .` or to run
  `python3 pcw16basic` from the folder.
- `tools/libref.py` has `--help` and `--check`; `pbimage.py info` on a missing
  file gives a one-line error; `tools/asmcheck.py --help` gives the right advice;
  `tools/pbicheck.py` refuses an extra argument.
- The library header comments point to `docs/libraries/<name>.md`;
  `docs/LIBRARY-REFERENCE.md` is generated from them.

**Runtime** (simulator-tested; awaiting the owner's XAnne retest).
- `DB SAVE` and `BITMAP SAVE` first check `NAME.NEW` and `NAME.BAK`. If either
  belongs to another kind of file (for example `FORM.BAK` of a database
  `FORM.DSN` when a picture `FORM.PBI` is saved), the save does nothing and sets
  the new `IOERR` 253 (known issue KI-91). A companion shorter than 4 bytes is
  replaced. When the file itself does not exist, a save keeps `NAME.BAK`.
- `DB LOAD` falls back to `NAME.NEW` or `NAME.BAK` only when the file is
  missing, not a database (248) or damaged (251). Another TYPE (249), another
  version (250), too many records (252) or a read error is reported with that
  code, and no older copy is loaded. A STRING field without its terminating 0
  counts as damage (251).
- REAL `+` and `-` are correctly rounded in every case (about 1.5% of results
  just under half a unit in the last place were one unit out).
- `tools/build.py --legacy-file-safety` and `--legacy-real-rounding` rebuild the
  old code, only to reproduce older accepted executables byte for byte.

## The M13 candidate (written as "1.0.0rc1 — release candidate 1 (not released)")

The first version prepared for the public. It has not been released, tagged for the public
or licensed for redistribution ([LICENSING.md](LICENSING.md)). Everything below is in this
repository; how far each part has been tested is stated in [docs/limitations.md](docs/limitations.md)
and, per feature, in the [developer manual](docs/manual/README.md).

**Language.** INTEGER, REAL (32-bit floating point), BOOLEAN, STRING and fixed-length
`STRING * n`; `CONST`; one-dimensional arrays, including `BANKED` arrays kept outside the
16K resident block; `TYPE` records and arrays of records; `IF`, `SELECT CASE`, `FOR`/`NEXT`
with `STEP`, `WHILE`/`WEND` and the `EXIT` forms; `SUB` and `FUNCTION` with parameters,
locals and return values; string, numeric and REAL maths functions; `INCLUDE`.
What is deliberately not in the language is listed in
[docs/manual/17-unsupported.md](docs/manual/17-unsupported.md).

**Applications.** Rosanne windows (several per program, one on screen at a time) with labels,
buttons, text and number fields, tick boxes, radio buttons, choices, sliders and lists;
menus with Ctrl keys; alerts and questions; a drawing canvas with the mouse; held-key
state (`KEYDOWN`); timers paced by a calibrated clock.

**Graphics.** Lines, boxes, shaded fills, inversion, scrolling and text on a canvas;
`BITMAP` pictures captured from the canvas or loaded from `.PBI` files, drawn whole, in part
(sprite sheets) or through a mask (transparent sprites); tools to turn PNG files into `.PBI`
pictures and sprite sheets.

**Data.** Whole-file text save and load, sequential files, text buffers for editors, a
record database file with safe replacement and recovery, sorting and searching. Printing
of text in several sizes and ruled tables on A4 pages (printed filled bars, used by charts,
are corrected but not yet retested in XAnne).

**Tools.** `pcw16basic` (`doctor`, `new`, `check`, `build`, `assets`, `image`, `memory`,
`test`), the memory report, code and runtime banking, the picture and database checkers,
the project's Z80 and Rosanne simulator and its test suite, `tools/check_docs.py` (builds
every program in the documentation) and `tools/verify_public.py` (checks this copy end to end).

**Programs.** 54 examples, three tutorials, 14 libraries, and prebuilt copies of the main
programs in `programs/`.

### Before this version

PcW16 BASIC was developed privately in stages, each one tested by the project owner in the
XAnne emulator before the next began. That history is kept in the project's private
records; this public history starts at 1.0.0rc1.
