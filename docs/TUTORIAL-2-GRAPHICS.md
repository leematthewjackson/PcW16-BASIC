# Tutorial 2: drawing, pictures and an icon palette

This tutorial makes a small drawing program. You drag to draw a box, and an icon palette chooses between an outline and a filled box. The icons are a PNG picture converted for the PcW16. The program uses three libraries:
- `lib/geom.pbas` for rectangles;
- `lib/drag.pbas` for dragging, with an outline that follows the pointer;
- `lib/toolbar.pbas` for the palette.

*Evidence:* this program builds, and the project's simulator runs it in the test suite (`tests/test_m13_tutorials.py`). A drag draws a 41 × 41 outline with no rubber band left behind, and after the second icon is picked the same drag fills the box. **No XAnne run of this program is recorded**, and it has not been tested on a real PcW16. The simulator does not draw Rosanne's grey patterns, so it cannot show how the fill looks.

## The picture

The two icons are one PNG, `examples/assets/tutorial-icons.png`: 48 × 24 pixels, holding two 24 × 24 icons side by side. Any paint program can edit it. The PcW16 screen has one bit per pixel, and a program loads PBI1 pictures, so convert it:

```sh
python3 pcw16basic image sheet examples/assets/tutorial-icons.png T2ICONS.PBI --frame 24,24
```

```text
T2ICONS.PBI: 2 frames of 24 x 24, a 24 x 48 strip; frame k is the part 0, k * 24, 24, 24
```

This writes `T2ICONS.PBI` with the icons one under the other, a 24 × 48 strip, which is what the toolbar library draws from. `python3 pcw16basic assets` makes every picture that `examples/assets/ASSETS.txt` lists, in one go. [graphics-assets.md](graphics-assets.md) describes the options: thresholds, dithering and masks. `programs/T2ICONS.PBI` is the same file, prebuilt.

## The program

The program is `examples/tutorial/t2_draw.pbas`:

<!-- file: examples/tutorial/t2_draw.pbas -->
```basic
' Tutorial 2: a canvas you draw boxes on by dragging, with an icon palette.
INCLUDE "../lib/geom.pbas"
INCLUDE "../lib/drag.pbas"
INCLUDE "../lib/toolbar.pbas"

DIM Icons AS BITMAP * 24, 48
DIM Status$ AS STRING * 24

WINDOW Main, "DRAW", LARGE
LABEL Status$
CANVAS 400, 200, PAINT Paint, MOUSE Mouse
BUTTON "Clear", ClearAll
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
    CALL ToolPaint(Icons)
    DRAW LINE 0, 30, 399, 30
END SUB

SUB Mouse
    LOCAL T AS INTEGER
    CALL DragMouse
    IF DragEvent = 1 AND DragY < 30 THEN
        T = ToolAt(DragX, DragY)
        IF T > 0 THEN
            CALL ToolPick(Icons, T)
        END IF
        CALL DragCancel
        EXIT SUB
    END IF
    SELECT CASE DragEvent
    CASE 2
        CALL DragShowBox
    CASE 3
        CALL DragHide
        CALL GeomSpan(DragX0, MAX(DragY0, 31), DragX, MAX(DragY, 31))
        IF ToolSel = 1 THEN
            DRAW BOX GeomX, GeomY, GeomW, GeomH
        ELSE
            DRAW FILL GeomX, GeomY, GeomW, GeomH, 2
        END IF
        Status$ = STR$(GeomW) + " x " + STR$(GeomH)
    END SELECT
END SUB

SUB ClearAll
    CALL Paint
    Status$ = "Cleared"
END SUB

SUB Quit
    EXIT
END SUB

DragW = 400
DragH = 200
ToolN = 2
ToolSize = 24
ToolX = 4
ToolY = 3
ToolSel = 1
BITMAP LOAD Icons, "T2ICONS.PBI"
IF IOERR <> 0 THEN
    Status$ = "T2ICONS.PBI is missing"
ELSE
    Status$ = "Drag to draw"
END IF
END
```

Build it:

```sh
python3 pcw16basic build examples/tutorial/t2_draw.pbas
```

It is larger than 16K, so the build puts some of its procedures in a code bank (`code banks: 1` in the build's output). Copy `build/t2_draw.prg` as `T2DRAW.PRG`, together with `T2ICONS.PBI`, into the same folder ([running-in-xanne.md](running-in-xanne.md)). Copy the `.PRG` whole: a code-banked program reads its banks from its own file. The program writes no files.

The `INCLUDE` lines say `"../lib/geom.pbas"` because the program sits in `examples/tutorial/`, and an INCLUDE path is relative to the file that contains it. In a project made by `pcw16basic new`, the libraries are in the project's own `lib/` folder, so you write `INCLUDE "lib/geom.pbas"`.

## What you should see

A large window titled `DRAW`, with the status line `Drag to draw`. If the picture was not found, the line says `T2ICONS.PBI is missing`. Below it is a 400 × 200 drawing area: the two icons at its top left, then a line across the area under them. **Clear** and **Quit** buttons are below the area.

## How it works

- **INCLUDE** reads a library into the program. The libraries are ordinary BASIC in `examples/lib/`, and [LIBRARY-REFERENCE.md](LIBRARY-REFERENCE.md) lists what each one provides. These three libraries start each of their names with a prefix (`Geom`, `Drag`, `Tool`), so their names do not clash with yours. Not every library does this: `lib/forms.pbas`, for one, also declares `IsBlank`, `IsDigits`, `PadRight$` and `Confirm` ([libraries/README.md](libraries/README.md)). Do not give a procedure of your own the name of a built-in function: a FUNCTION with such a name is refused, and a SUB with one makes the built-in unusable ([manual/05-procedures.md](manual/05-procedures.md#58-a-function-may-not-take-a-built-ins-name)).
- **CANVAS 400, 200, PAINT Paint, MOUSE Mouse** is a drawing area. The runtime runs `Paint` when the window opens, and again after any handler that showed an alert, so `Paint` must draw everything the area shows. `Mouse` runs for a press (`DragEvent` 1), for each movement while the button is held (2), and for the release (3).
- **DragMouse** keeps the press point and the pointer's position. `DragShowBox` draws the rubber band in XOR ink, so drawing it again rubs it out and nothing is left behind. `DragCancel` ignores the rest of a press that chose an icon.
- **ToolPaint(Icons)** draws the palette from the BITMAP the program loaded, and **ToolPick** marks the chosen icon. A BITMAP can be passed to a SUB: `SUB ToolPaint(Icons AS BITMAP)` ([manual/13-bitmaps-and-sprites.md](manual/13-bitmaps-and-sprites.md)).
- **GeomSpan** turns the two corners of the drag into a rectangle, `GeomX`, `GeomY`, `GeomW` and `GeomH`. `MAX(..., 31)` keeps it below the palette's line.
- **BITMAP LOAD** reads the PBI1 file and sets `IOERR`, and the program checks it. A missing picture does not stop the program, so a program that needs one should always check, as this one does.
- **Shade 2** in `DRAW FILL ..., 2` is one of Rosanne's grey patterns: 0 is black, 8 is white, and the values between are greys ([manual/12-drawing.md](manual/12-drawing.md)).

## Try

1. Draw a third icon in the PNG, so that it is 72 × 24. Convert it again, and set `ToolN = 3` and `DIM Icons AS BITMAP * 24, 72`.
2. Use `DragShowLine` and `DRAW LINE` for a line tool.
3. Look at `examples/paint2.pbas`. It is a complete drawing program built the same way, with six imported icons, pattern swatches, undo and a selection that moves (Tested in XAnne).

Next: [Tutorial 3](TUTORIAL-3-GAME.md) makes a sprite run and jump.
