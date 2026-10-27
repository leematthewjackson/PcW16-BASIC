# lib/toolbar.pbas: icon palette and pattern swatches

`lib/toolbar.pbas` draws two kinds of palette on a CANVAS and tells you which entry the pointer is on:

- an **icon palette** of up to 24 square icons taken from one BITMAP strip, with a selected icon (drawn inverted), disabled icons (greyed) and a key for each icon;
- a **pattern palette** of up to 9 swatches filled with the `DRAW FILL` shades, the chosen one marked with a double frame.

**Evidence:** *Tested in XAnne* through PAINT II (the owner: the six imported icons and nine swatches work). The second tutorial (T2DRAW) uses it too, without a recorded XAnne result. Not yet tested on a real PcW16.

## Adding it

```text
INCLUDE "lib/toolbar.pbas"
```

The program needs:

- a CANVAS;
- for the icon palette, a BITMAP holding the icon strip, loaded or drawn before the canvas is first painted.

(Up to M13 a program that included this library but declared no BITMAP failed in the assembler; M14 fixed this.)

It needs no other library.

## The icon strip

Square icons of `ToolSize` pixels, one under another: a BITMAP `ToolSize` wide and `ToolN × ToolSize` high. `pcw16basic image sheet` makes one from a PNG; PAINT II loads `P2ICONS.PBI` with `BITMAP LOAD` ([graphics assets](../graphics-assets.md)). A program should still work when the file is missing: PAINT II shows letters instead of icons.

## Settings (your program sets them)

| Name | Meaning |
|---|---|
| `ToolN` | number of icons, 1..24 |
| `ToolSize` | icon size in pixels |
| `ToolX`, `ToolY` | top-left corner of the palette on the canvas |
| `ToolAcross` | icons per row; 0 means `ToolN` (one row); 1 makes a column |
| `ToolGap` | pixels between icons; 0 means 2 |
| `ToolSel` | the selected icon, 1..ToolN, or 0 |
| `ToolOff(I)` | TRUE: icon I is disabled (greyed, cannot be chosen) |
| `ToolKey(I)` | a KEYCODE that chooses icon I, or 0 |
| `SwatchN` | number of swatches, 1..9 |
| `SwatchSize` | swatch size in pixels |
| `SwatchX`, `SwatchY` | top-left corner of the swatches |
| `SwatchAcross` | swatches per row; 0 means `SwatchN` |
| `SwatchSel` | the chosen swatch |
| `SwatchShade(I)` | the shade of swatch I; by default I − 1 (0 black .. 8 white) |

Swatches are spaced 4 pixels apart. The default shades are set by the first swatch drawn; set `SwatchShade` and `SwatchSet = TRUE` yourself to use other shades.

## Procedures and functions

Parameters not marked BITMAP are INTEGER.

| Name | Kind | Parameters | Result | What it does |
|---|---|---|---|---|
| `ToolPaint` | SUB | `Icons AS BITMAP` | | Draws every icon: the selected one inverted, disabled ones greyed. |
| `ToolAt` | FUNCTION | `X, Y` | INTEGER | The icon under X, Y; 0 for none or for a disabled icon. |
| `ToolPick` | SUB | `Icons AS BITMAP, I` | | Selects icon I and redraws the old and new icon. Ignored for a disabled icon or a number out of range. |
| `ToolForKey` | FUNCTION | `K` | INTEGER | The enabled icon whose `ToolKey` is K, or 0. |
| `SwatchDefaults` | SUB | | | Sets the default shades once (called for you). |
| `SwatchPaint` | SUB | | | Draws every swatch. |
| `SwatchAt` | FUNCTION | `X, Y` | INTEGER | The swatch under X, Y, or 0. |
| `SwatchPick` | SUB | `I` | | Chooses swatch I and redraws the old and new one. |

`ToolCell`, `ToolDraw`, `SwatchCell` and `SwatchDraw` are internal.

## Names it defines

`TOOLMAX` (CONST = 24); `ToolN`, `ToolSize`, `ToolX`, `ToolY`, `ToolAcross`, `ToolGap`, `ToolSel`, `ToolOff(24)`, `ToolKey(24)`, `ToolCX`, `ToolCY`; `SwatchN`, `SwatchSize`, `SwatchX`, `SwatchY`, `SwatchAcross`, `SwatchSel`, `SwatchShade(9)`, `SwatchSet`. Names start with `Tool` or `Swatch`; do not declare your own.

## Memory cost

Measured in a minimal host with a canvas and one small BITMAP:

| | bytes |
|---|---:|
| whole program, one 16K image | +4,155 |
| resident 16K block, procedures in code banks | +1,624 |
| of which variables and arrays | +240 |

The icon strip is a BITMAP, so it takes a 16K block of its own outside the resident block ([memory.md](../memory.md)).

## Errors

- `ToolN` above 24 or `SwatchN` above 9 stops the program with `Runtime error: index out of range` when the palette is drawn.
- An icon strip shorter than `ToolN × ToolSize` makes `ToolPaint` ask for a part outside the bitmap, and the program stops with a runtime error.
- A palette that does not fit the canvas stops the program with `drawing outside the canvas`.

## Example

Three icons drawn at run time, and the nine swatches. Click an icon or a swatch to choose it; the L key chooses the second icon.

```pbas
INCLUDE "lib/toolbar.pbas"
DIM Icons AS BITMAP * 16, 48
DIM Ready AS BOOLEAN
WINDOW "Toolbar"
CANVAS 200, 80, PAINT Paint, MOUSE Mouse, KEYS Keys
BUTTON "Quit", Quit
SUB Paint
    IF NOT Ready THEN
        DRAW CLEAR
        DRAW BOX 3, 3, 10, 10
        DRAW LINE 3, 28, 12, 19
        DRAW FILL 3, 35, 10, 10, 0
        BITMAP GET Icons, 0, 0, 16, 48
        Ready = TRUE
    END IF
    DRAW CLEAR
    CALL ToolPaint(Icons)
    CALL SwatchPaint
END SUB
SUB Mouse
    LOCAL I AS INTEGER
    IF MOUSEEVENT <> 1 THEN
        EXIT SUB
    END IF
    I = ToolAt(MOUSEX, MOUSEY)
    IF I > 0 THEN
        CALL ToolPick(Icons, I)
    END IF
    I = SwatchAt(MOUSEX, MOUSEY)
    IF I > 0 THEN
        CALL SwatchPick(I)
    END IF
END SUB
SUB Keys
    LOCAL I AS INTEGER
    I = ToolForKey(KEYCODE)
    IF I > 0 THEN
        CALL ToolPick(Icons, I)
    END IF
END SUB
SUB Quit
    EXIT
END SUB
ToolN = 3
ToolSize = 16
ToolX = 4
ToolY = 4
ToolSel = 1
ToolKey(2) = ASC("l")
SwatchN = 9
SwatchSize = 12
SwatchX = 6
SwatchY = 40
SwatchSel = 1
MESSAGE "icon at 25,10: " + STR$(ToolAt(25, 10))
MESSAGE "icon for l: " + STR$(ToolForKey(ASC("l")))
END
' expect-message: icon at 25,10: 2
' expect-message: icon for l: 2
```

## Used by

- `examples/paint2.pbas`
- `examples/tutorial/t2_draw.pbas` ([Tutorial 2](../TUTORIAL-2-GRAPHICS.md))

## Limitations

- At most 24 icons and 9 swatches; icons are square and all the same size.
- Disabled icons are greyed with white diagonal lines, so a mostly white icon looks almost the same disabled.

See also: [library index](README.md), [bitmaps and sprites](../manual/13-bitmaps-and-sprites.md), [generated reference](../LIBRARY-REFERENCE.md).
