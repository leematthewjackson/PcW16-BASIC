# Roadmap

**Nothing on this page is committed.** It lists what exists, and work that
could be done next, so that the choices are visible. The project owner decides
what, if anything, is done and when. There are no dates, and no item below is
a promise that a feature will appear. Performance is not claimed anywhere
here without a measurement behind it.

Evidence levels used below: *Tested in XAnne* (the owner ran it in the XAnne
emulator with Rosanne 1.12), *Simulator only* (checked on the project's model,
`tests/z80sim.py`), *Untested*. Nothing has been run on a real PcW16.

## Existing capabilities

PcW16 BASIC is a compiler (Python) that turns `.pbas` source into a Rosanne
`.PRG` for the Amstrad PcW16, through the Pasmo assembler. Today it has:

- **The language:** INTEGER, BOOLEAN, STRING (with per-variable sizes) and
  REAL; one-dimensional arrays, BANKED arrays of up to 32,767 elements, and
  records (TYPE); block IF, SELECT CASE, FOR, WHILE; SUBs and FUNCTIONs with
  parameters and LOCAL variables; CONST; INCLUDE. See
  [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md) and the [manual](docs/manual/README.md).
- **Applications:** windows (up to 8 named ones), labels, text fields, tick
  boxes, radio buttons, number fields, lists, drop-down choices, sliders,
  menus with shortcuts, button keys, alerts and questions, one timer, and
  Rosanne's Tasks → Stop with `ON STOP` to protect unsaved work.
  *Tested in XAnne*, with the limitations in
  [docs/limitations.md](docs/limitations.md).
- **Graphics:** up to eight named drawing canvases in any windows, each with
  its own mouse and key events and keyboard focus; held keys; black and white
  drawing; Rosanne's twelve dialog fonts, with measured widths and alignment;
  scalable Swiss and Times type from 6 to 72 points, plain, bold or italic;
  bitmaps with parts and masks; PBI1 picture files made from PNGs on a PC.
  *Tested in XAnne.*
- **Data:** sequential text files, text buffers of up to 64K for editors,
  databases of records with safe saving, backup and recovery, sorting and
  searching. *Tested in XAnne.*
- **Printing:** text, lines and boxes on an A4 page. *Tested in XAnne*;
  filled boxes and printed charts await a retest (known issue KI-79,
  docs/limitations.md).
- **Large programs:** code banks and a runtime bank, so programs can be far
  larger than the 16K resident block. *Tested in XAnne.*
- **Libraries:** 14 libraries for status lines, forms, safe file names,
  lists, geometry, dragging, handles, scenes, toolbars, sprites, keys, pacing
  and charts ([docs/libraries/README.md](docs/libraries/README.md)).
- **Tools:** the `pcw16basic` command (doctor, new, check, build, image,
  memory, assets, test), the picture converter, file checkers, the simulator
  and the test suite.
- **Example applications:** a text editor, an address book, a to-do list, a
  paint program, a screen designer, a sprite editor, a report generator, a
  type specimen and a platform game, each run by the owner in XAnne, with the open items
  the catalogue notes ([examples/README.md](examples/README.md)).

## Next-phase candidates

Work that is well understood and could be done without new research. It is
listed, not scheduled.

**Release.**
- Publish release candidate 2 (1.0.0rc2) with its checksums, then collect
  reports and fix only release-blocking defects before a 1.0.

**Compiler defects found by the capability audit.** The M14 revision fixed
most of them: `KEYDOWN` without a CANVAS, `check` running only the front end,
the four assignments and statements the specification forbids, a FUNCTION
with a built-in's name, `--help` after a subcommand, and the TEXTBOX
capacity message ([CHANGELOG.md](CHANGELOG.md)). Still open:
- Conventional BASIC statements that do not exist (`INPUT`, `GOSUB`, `DO`,
  `ELSEIF` and others) get generic parser messages; a message that names the
  missing statement would help newcomers.
- A SUB may still take a built-in function's name, which makes the built-in
  unusable in that program ([docs/limitations.md](docs/limitations.md)).

**Evidence still to collect.**
- The printed-chart retest in XAnne (known issue KI-79, docs/limitations.md).
- The XAnne retest of M14's runtime corrections: `DB SAVE` and `BITMAP SAVE`
  refusing companions that belong to another file (IOERR 253, known issue
  KI-91), `DB LOAD`'s narrower fallback, and REAL `+` and `-` rounding.
  *Simulator only* so far.
- XAnne checks not yet performed: held keys in the timing probe, menu
  shortcuts while a text field has the focus, the sprite editor's keys, an
  export to a read-only disk, the Help button key, Return in a text
  field (known issue KI-6, docs/limitations.md).
- The dialog fonts' line heights, from screenshots, which would allow a
  `TEXTHEIGHT` (known issue KI-106, docs/limitations.md); the speed of
  scalable type on screen.
- `RND` and `RANDOMIZE` in XAnne (no example uses them yet).
- **A first run on a real PcW16** (known issue KI-85, docs/limitations.md).
  Everything so far is emulator evidence.

**Open interface issues:**
- a number field's spinner and a slider's arrows can step more than once a
  click (known issues KI-1 and KI-2, docs/limitations.md);
- a list's double-click action never runs in XAnne (known issue KI-25, docs/limitations.md);
- a list's scroll-bar drag can start only near the handle (known issue KI-5, docs/limitations.md);
- a status line in the older address book can exceed what a label shows
  (known issue KI-63, docs/limitations.md).

## Long-term ideas

Possible extensions that the project's records mention as limits. Each would
need design work and the owner's agreement; none is planned.

- Setting and reading single pixels inside a BITMAP (known issue KI-88, docs/limitations.md).
- Sorting and searching databases of more than 250 records (known issue KI-56, docs/limitations.md).
- `DRAW TEXT` cut by measured width in every program, not only in those that
  use `DRAW FONT` (known issue KI-76, docs/limitations.md); this would change
  accepted programs, so it needs care.
- A `TEXTHEIGHT` for the dialog fonts, once their heights are measured (known
  issue KI-106, docs/limitations.md).
- A crash-safe `FILESAVE` (write, then rename) (known issue KI-11, docs/limitations.md).
- Faster `TEXT LOAD` (known issue KI-43, docs/limitations.md).
- Denser generated code, to leave more room in the resident block (known issue KI-28, docs/limitations.md).
- Strings longer than 127 bytes (known issue KI-29, docs/limitations.md).
- Natural-number ordering in sorts (known issue KI-51, docs/limitations.md).
- Fewer redraws of lists and drop-downs after every handler (known issue KI-8, docs/limitations.md).
- Conventional constructs that the language lacks
  ([docs/manual/17-unsupported.md](docs/manual/17-unsupported.md)). Whether
  any should be added is an open question; the current design deliberately
  has no console, no GOTO and no implicit variables.

## Research-dependent possibilities

These depend on facts about Rosanne or the hardware that are not yet known.
They are possible only if the research succeeds.

- **The internal flash drive.** Files are floppy-only because the flash
  drive's naming and folder calls are not documented in the material the
  project has.
- **Appending and random access.** The system's file-pointer call works only
  on flash; on the floppy, opening a file for writing always empties it.
- **Printing pictures and sloped lines.** Rosanne 1.12's picture and stripe
  printing calls are empty (known issue KI-74, docs/limitations.md).
- **Sound beyond the beep.** Not defined.
- **Double-clicks, the right and centre mouse buttons, hover.** Not reported
  by the events the runtime receives (known issue KI-25, docs/limitations.md).
- **Timing and the clock on real hardware.** How fine the clock's sixteenths
  are, and how often a timer really runs, are measured only in XAnne.
- **What Rosanne does when an open file is deleted or renamed** (known issue KI-16, docs/limitations.md).
- **Tasks → Stop for a program without menus.** Rosanne shows such a program no menu bar, so Stop never reaches it (known issue KI-108, docs/limitations.md).
- **Overlapping scrolls** in both directions (known issue KI-40, docs/limitations.md).

The owner decides which of these, if any, are pursued.
