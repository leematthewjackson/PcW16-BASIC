# lib/geom.pbas: points and rectangles

`lib/geom.pbas` answers the small geometric questions every graphical program asks: is this pixel inside that rectangle, do two rectangles overlap, what is the rectangle between two corners, which part of a rectangle lies inside another. It draws nothing, so it works with or without a CANVAS.

**Evidence:** *Tested in XAnne* through DESIGNER, PAINT II, SPRITED, JUMPER and the third tutorial game (T3HOP). Not yet tested on a real PcW16.

## Adding it

```text
INCLUDE "lib/geom.pbas"
```

Put the line near the top of the program, on a line of its own, outside any SUB. It needs no other library. [lib/scene.pbas](scene.md) needs this one.

## Rectangles

A rectangle is four INTEGERs X, Y, W, H in pixels. It covers the columns X to X + W − 1 and the rows Y to Y + H − 1. A rectangle whose W or H is 0 or less is *empty*: it holds no pixel and meets nothing.

## Procedures and functions

All parameters are INTEGER.

| Name | Kind | Parameters | Result | What it does |
|---|---|---|---|---|
| `GeomIn` | FUNCTION | `X, Y, RX, RY, RW, RH` | BOOLEAN | TRUE when the pixel X, Y is inside the rectangle RX, RY, RW, RH. |
| `GeomMeets` | FUNCTION | `AX, AY, AW, AH, BX, BY, BW, BH` | BOOLEAN | TRUE when the two rectangles share at least one pixel. An empty rectangle meets nothing. |
| `GeomClamp` | FUNCTION | `V, Lo, Hi` | INTEGER | V kept within Lo..Hi. |
| `GeomSpan` | SUB | `X1, Y1, X2, Y2` | GeomX, GeomY, GeomW, GeomH | The rectangle whose opposite corners are the two pixels, both included, in any order. This is the rectangle of a rubber band. |
| `GeomClip` | SUB | `X, Y, W, H, CX, CY, CW, CH` | GeomX, GeomY, GeomW, GeomH, GeomDX, GeomDY | The part of X, Y, W, H inside CX, CY, CW, CH. GeomW and GeomH are 0 when there is none. GeomDX, GeomDY say how far the top-left corner moved (GeomX − X, GeomY − Y). |
| `GeomUnite` | SUB | `AX, AY, AW, AH, BX, BY, BW, BH` | GeomX, GeomY, GeomW, GeomH | The smallest rectangle that holds both. An empty rectangle is ignored. |

The SUBs return their rectangle in global variables, because a SUB has no result and a FUNCTION returns one value. Read the results straight after the CALL: the next call to any Geom SUB replaces them.

`GeomClip` is how you draw the visible part of a bitmap that is partly off the canvas: clip the bitmap's rectangle to the canvas, then draw the part GeomDX, GeomDY, GeomW, GeomH of the bitmap at GeomX, GeomY.

## Names it defines

| Name | Type | Use |
|---|---|---|
| `GeomX`, `GeomY`, `GeomW`, `GeomH` | INTEGER | results of the SUBs |
| `GeomDX`, `GeomDY` | INTEGER | results of `GeomClip` |

Every name starts with `Geom`. Do not declare a variable, CONST, SUB or FUNCTION of your own with one of these names: the build stops with `duplicate declaration of GEOMX` or `duplicate subroutine GEOMSPAN`.

## Memory cost

Measured by building a minimal host program (a window with one button) with and without the library:

| | bytes |
|---|---:|
| whole program, when everything fits in one 16K image | +1,902 |
| resident 16K block, when the procedures are in code banks | +515 |
| of which variables (globals, parameters and locals) | +100 |

The resident figure includes about 360 bytes of runtime routines (MIN, MAX and comparisons) that most programs already have. See [memory.md](../memory.md) for how to read these figures.

## Errors

The library has no error cases of its own. It never draws, so it cannot cause `drawing outside the canvas`. INTEGER arithmetic wraps above 32767, so rectangles near that size give wrong answers; screen coordinates never come close.

## Example

```pbas
' Geometry checks, shown as alerts.
INCLUDE "lib/geom.pbas"
IF GeomIn(5, 5, 0, 0, 10, 10) THEN
    MESSAGE "5,5 is inside"
END IF
IF NOT GeomMeets(0, 0, 10, 10, 10, 0, 5, 5) THEN
    MESSAGE "side by side: no overlap"
END IF
CALL GeomSpan(30, 20, 10, 5)
MESSAGE "span " + STR$(GeomX) + "," + STR$(GeomY) + " " + STR$(GeomW) + "x" + STR$(GeomH)
CALL GeomClip(-4, 2, 10, 10, 0, 0, 100, 100)
MESSAGE "clip " + STR$(GeomX) + "," + STR$(GeomY) + " " + STR$(GeomW) + "x" + STR$(GeomH) + " from " + STR$(GeomDX)
MESSAGE "clamp " + STR$(GeomClamp(120, 0, 99))
END
' expect-message: 5,5 is inside
' expect-message: side by side: no overlap
' expect-message: span 10,5 21x16
' expect-message: clip 0,2 6x10 from 4
' expect-message: clamp 99
```

## Used by

- `examples/designer.pbas`, `examples/paint2.pbas`, `examples/sprited.pbas`, `examples/jumper.pbas`
- `examples/tutorial/t2_draw.pbas`, `examples/tutorial/t3_hop.pbas` ([Tutorial 2](../TUTORIAL-2-GRAPHICS.md), [Tutorial 3](../TUTORIAL-3-GAME.md))

## Limitations

- Rectangles only: there are no circles, lines or polygons.
- Results come back in shared globals, so a SUB that calls a Geom SUB and then another procedure that also uses Geom must copy the results first.

See also: [library index](README.md), [generated reference](../LIBRARY-REFERENCE.md), [drawing](../manual/12-drawing.md).
