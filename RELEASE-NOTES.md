# Release notes: PcW16 BASIC 1.0.0rc2

Release candidate 2 of PcW16 BASIC, the BASIC compiler for the Amstrad PcW16. It adds four
facilities to 1.0.0rc1, the Public Preview. Everything new was tested by the project's owner in the XAnne emulator (Rosanne 1.12). Nothing has been run on a real PcW16 yet.
The details are in [CHANGELOG.md](CHANGELOG.md).

## What you can now do

| facility | statements | what it gives your programs | read |
|---|---|---|---|
| **Several canvases** | `CANVAS Name, …` (up to 8), `DRAW ON Name`, `FOCUS Name` | a palette beside a drawing area, a preview beside a ruler, a canvas in a second window. Each canvas has its own PAINT, MOUSE and KEYS handlers | [manual 12](docs/manual/12-drawing.md#several-canvases-draw-on) |
| **Twelve dialog fonts** | `DRAW FONT n`, `TEXTWIDTH`, `DRAW TEXT … ALIGN LEFT \| CENTRE \| RIGHT` | headings, captions and labels in Rosanne's own fonts, measured, centred or right-aligned | [manual 12](docs/manual/12-drawing.md#draw-font-and-align) |
| **Scalable type** | `TYPE FONT SWISS \| TIMES, size [, BOLD] [, ITALIC]`, `DRAW TYPE`, `TYPEWIDTH`, `TYPEHEIGHT` | text from 6 to 72 points on screen, in the same fonts as printing: previews, title screens, large displays | [manual 12](docs/manual/12-drawing.md#scalable-type-type-font-and-draw-type) |
| **Tasks → Stop** | `ON STOP Handler` | Rosanne's Tasks → Stop now ends a program with menus. With `ON STOP`, it asks about unsaved work first, and can keep the program open | [manual 11](docs/manual/11-menus-keys-mouse.md#tasks--stop-and-on-stop) |

PAINT II, DESIGNER, SPRITED, MDEDIT IV and CONTACTS IV now ask before Tasks → Stop discards your work.

## New examples

- `examples/sketchpad.pbas`: two canvases in one window, with keyboard focus and a drawing that survives a repaint.
- `examples/fontbook.pbas`: the twelve dialog fonts with their widths, and alignment.
- `examples/stopguard.pbas`: the smallest safe use of `ON STOP`.
- `examples/m15_specimen.pbas` (SPECIMEN, prebuilt in `programs/`): all four facilities in one program.

## Compatibility

- Programs that use none of the new statements compile to the same bytes as in 1.0.0rc1, except that
  a program with menus gains a 4-byte table row so that Tasks → Stop ends it.
- A program with one canvas keeps the same code as before; the new runtime code goes only into the
  programs that use it.
- `--legacy-tasks-stop` rebuilds a 1.0.0rc1 executable byte for byte.

## Limitations to know

- A program without menus never receives Tasks → Stop: Rosanne shows it no menu bar (KI-108). Give it a
  Quit button.
- The runtime keeps no copy of what is drawn. PAINT must draw everything the program wants kept, on every
  canvas (KI-42, KI-107).
- The dialog fonts' line heights are not measured, so there is no `TEXTHEIGHT` (KI-106).
- The speed of scalable type is not measured.

[docs/limitations.md](docs/limitations.md) lists every known issue.
