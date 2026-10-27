# Libraries

PcW16 BASIC comes with 14 libraries in `examples/lib/`. Each is an ordinary `.pbas` file of SUBs, FUNCTIONs, CONSTs and DIMs that you add to a program with `INCLUDE`. They are not built into the compiler: you can read them, copy them and change your copy. Every name a library declares is listed on its page, because a library's names share one name space with your program.

This page explains how to add a library and lists all 14. Each library has a page of its own (linked in the table) with every procedure's parameters and result, the names it defines, its dependencies, its measured memory cost, its error behaviour, a complete example and its evidence level. The [generated library reference](../LIBRARY-REFERENCE.md) reproduces each library's own header comment.

## Adding a library to a project

**A new project already has them.** `pcw16basic new NAME` makes a folder `NAME/` with `NAME.pbas`, an `assets/` folder and a `lib/` folder that is a copy of `examples/lib/`:

```sh
pcw16basic new mygame --kind game
cd mygame
pcw16basic build mygame.pbas
```

**Otherwise copy the file.** Copy the library you need (and any library it needs) from `examples/lib/` into a `lib/` folder beside your program. Because the project holds its own copy, later changes to `examples/lib/` do not change your program.

**Then include it.** Put the INCLUDE on a line of its own, outside any SUB, normally near the top:

```text
INCLUDE "lib/geom.pbas"
INCLUDE "lib/scene.pbas"
```

The rules, from the [language specification](../../LANGUAGE-SPEC.md) §5.11 and [program structure](../manual/01-program-structure.md):

- **The path is relative to the file that contains the INCLUDE line**, not to the folder you build from. The tutorials in `examples/tutorial/` use `INCLUDE "../lib/geom.pbas"`.
- Inclusion is textual: the line is replaced by the file's text.
- Each file may be included only once (`... that file is already part of the program (included at line 1)`).
- A missing file stops the build: `INCLUDE "lib/x.pbas": no such file`.
- An included file has fewer than 1000 lines and no line numbers.

**Line numbers in messages.** A compile error in a library names the library and its own line (`lib/drag.pbas:49:9: ...`). A *runtime* error gives a program line: the k-th included file is numbered from the first multiple of 1000 above your program's last line, plus 1000 × (k − 1). The build prints each file's range (`included: lib/pace.pbas: lines 1001..1999`), so `Runtime error: division by zero at line 1061` means line 61 of that library.

## Order of INCLUDEs for libraries that need another

No library includes another; you include both. Two libraries depend on others:

| Library | Needs | Without it the build stops with |
|---|---|---|
| [scene](scene.md) | [geom](geom.md) | `CALL GEOMUNITE: no SUB GEOMUNITE is defined` |
| [chartprt](chartprt.md) | [chart](chart.md) | `undefined variable CHARTN` |

Include the needed library first, as the libraries' own headers ask:

```text
INCLUDE "lib/geom.pbas"
INCLUDE "lib/scene.pbas"
INCLUDE "lib/chart.pbas"
INCLUDE "lib/chartprt.pbas"
```

The compiler also accepts the reverse order, because procedures and global variables may be used before the line that defines them, but the dependency-first order is the convention used by every example.

Two libraries call procedures that **your program** must define:

| Library | Your program defines |
|---|---|
| [app](app.md) | `FUNCTION AppSave() AS BOOLEAN` |
| [listview](listview.md) | `FUNCTION ListCell$(I AS INTEGER, K AS INTEGER) AS STRING` and `SUB ListPicked` |

## Name clashes

Every library declares globals, CONSTs and procedures in the one program-wide name space, and names are not case-sensitive. A program that declares a name a library already has does not build:

- `duplicate declaration of GEOMX (first at line 1026)` for a variable;
- `duplicate subroutine CONFIRM` for a SUB or FUNCTION;
- `duplicate CONST CHARTMAX`, or `SC_UP is already a CONST`, for a CONST.

Each library uses a prefix (`App`, `Chart`, `Drag`, `Form`, `Geom`, `Handle`/`Hand`, `List`, `Pace`, `Safe`, `Scene`, `Sprite`/`Spr`, `Tool`/`Swatch`), with these exceptions to watch for:

- [forms](forms.md) defines `IsBlank`, `IsDigits`, `PadRight$` and `Confirm`;
- [keys](keys.md) defines 83 CONSTs named `SC_...` and `KC_...`;
- [sprite](sprite.md) defines the CONST `SPRITES`; [listview](listview.md) the CONST `LIST_H`; [scene](scene.md), [toolbar](toolbar.md) and [chart](chart.md) define `SCENEMAX`, `TOOLMAX` and `CHARTMAX`.

Inside a SUB or FUNCTION, a parameter or LOCAL may reuse a CONST's name. Do not name a SUB or FUNCTION of your own like a **built-in** function (`Min`, `Len`): a FUNCTION with such a name is a compile error, and a SUB with one makes the built-in unusable everywhere, including inside libraries ([manual/05-procedures.md](../manual/05-procedures.md#58-a-function-may-not-take-a-built-ins-name)).

## The libraries

Evidence levels: *Tested in XAnne* means the owner ran an application that uses the library in the XAnne emulator (Rosanne 1.12); *Experimental* means the library's key behaviour is checked only on the project's simulator. Nothing has been run on a real PcW16 yet.

### Applications

| Library | Purpose | Needs | Evidence |
|---|---|---|---|
| [app](app.md) | status line, unsaved-changes question, IOERR codes in words | your `AppSave()`; a `LABEL AppStatus$` to show the status | Tested in XAnne (CONTACTS IV, STARTER, PAINT II, DESIGNER, SPRITED, REPORTER) |
| [forms](forms.md) | checks for typed fields: required, phone, e-mail, number; first problem only | nothing | Tested in XAnne (CONTACTS III, CONTACTS IV) |
| [listview](listview.md) | a keyboard- and mouse-driven list of rows with columns on a canvas | a CANVAS; your `ListCell$` and `ListPicked` | Tested in XAnne (CONTACTS IV, STARTER) |
| [files](files.md) | a typed file name forced to your extension; replace a file only once its new version is complete | nothing | Tested in XAnne (DESIGNER) |

### Graphics and interaction

| Library | Purpose | Needs | Evidence |
|---|---|---|---|
| [geom](geom.md) | points and rectangles: inside, overlap, span, clip, union | nothing | Tested in XAnne (DESIGNER, PAINT II, SPRITED, JUMPER) |
| [drag](drag.md) | press, drag and release on a canvas, with XOR rubber bands | a CANVAS with a MOUSE handler | Tested in XAnne (DESIGNER) |
| [handles](handles.md) | eight selection handles; resizing a rectangle by a handle | a CANVAS | Tested in XAnne (DESIGNER) |
| [scene](scene.md) | up to 100 objects in a stacking order; hit test; dirty area | [geom](geom.md) | Tested in XAnne (DESIGNER) |
| [toolbar](toolbar.md) | an icon palette from one BITMAP strip, and pattern swatches | a CANVAS; a BITMAP icon strip | Tested in XAnne (PAINT II) |

### Games

| Library | Purpose | Needs | Evidence |
|---|---|---|---|
| [sprite](sprite.md) | up to 16 masked, clipped sprites with background restore | a CANVAS; sheet, mask and background BITMAPs | Tested in XAnne (JUMPER, T3HOP) |
| [keys](keys.md) | names for `KEYDOWN` scan codes and `KEYCODE` characters; `KeyAxis` | nothing (held keys are tested only with a CANVAS) | Tested in XAnne (JUMPER, T3HOP); six scan codes confirmed |
| [pace](pace.md) | fixed time steps from the clock, however often the TIMER runs | a TIMER to call it from | Tested in XAnne (JUMPER, T3HOP, timing probes) |

### Charts and printing

| Library | Purpose | Needs | Evidence |
|---|---|---|---|
| [chart](chart.md) | bar and line charts of up to 12 values on the canvas | a CANVAS | Tested in XAnne on screen (REPORTER) |
| [chartprt](chartprt.md) | the bar chart on a printed page | [chart](chart.md); an open page | **Experimental**: printed bars not yet confirmed in XAnne (known issue KI-79, [limitations](../limitations.md)) |

### Which examples use which library

| Example | Libraries |
|---|---|
| `examples/contacts3.pbas` | forms |
| `examples/contacts4.pbas` | app, forms, listview |
| `examples/starter.pbas` | app, listview |
| `examples/paint.pbas` | app |
| `examples/paint2.pbas` | app, geom, toolbar, keys |
| `examples/designer.pbas` | app, geom, scene, drag, handles, keys, files |
| `examples/sprited.pbas` | app, geom, keys |
| `examples/jumper.pbas` | geom, sprite, keys, pace |
| `examples/reporter.pbas` | app, chart, chartprt |
| `examples/printdemo.pbas` | app |
| `examples/tutorial/t2_draw.pbas` | geom, drag, toolbar |
| `examples/tutorial/t3_hop.pbas` | geom, sprite, keys, pace |

## Memory

A library costs memory twice over: its procedures' code (which goes to code banks when the program is large) and its data (globals, arrays, STRING parameters and locals), which always stays in the resident 16K block. Each library page gives figures measured by building a minimal host program with and without it. In short:

| Library | Resident bytes when procedures are banked | Of which data |
|---|---:|---:|
| keys | 92 | 8 |
| geom | 515 | 100 |
| handles | 531 | 126 |
| pace | 535 | 38 |
| app | 768 | 547 |
| drag | 848 | 56 |
| listview | 1,110 | 395 |
| scene | 1,275 | 1,114 |
| sprite | 1,493 | 328 |
| toolbar | 1,624 | 240 |
| forms | 1,988 | 1,212 |
| chart | 2,634 | 485 |
| files | 2,786 | 100 |
| chartprt | 3,765 | 104 |

The difference between the two columns is mostly runtime code the library pulls in (drawing, files, printing, the REAL library); a larger program often has much of it already, and `--runtime-banks all` moves most of it out of the resident block. For a larger measure: geom, drag, handles, scene, toolbar, sprite, keys, pace and files together, in a minimal host with a canvas and one BITMAP, build to a 28,672-byte file with one code bank and a resident block of 13,431 bytes (9,348 bytes with `--runtime-banks all`), before the program has any code of its own. See [memory.md](../memory.md) for the whole picture.

See also: [the generated reference](../LIBRARY-REFERENCE.md), [Tutorial 2](../TUTORIAL-2-GRAPHICS.md) and [Tutorial 3](../TUTORIAL-3-GAME.md) (which build programs from geom, drag, toolbar, sprite, keys and pace), and the [examples catalogue](../../examples/README.md).
