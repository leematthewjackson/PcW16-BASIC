# 12. Drawing on a canvas

A `CANVAS` is a drawing area in a window. Your program draws on it with `DRAW` statements,
reads its pixels with `POINT`, and receives the mouse and keys there
([chapter 11](11-menus-keys-mouse.md)). Pictures that you prepare on a PC and draw with
`BITMAP` are in [chapter 13](13-bitmaps-and-sprites.md).

The PcW16 screen has one bit a pixel: every pixel is black or white. Greys are patterns of
black and white pixels.

Evidence levels: *Tested in XAnne* (the owner ran it in the XAnne emulator, Rosanne 1.12),
*Simulator only*, *Untested*. Nothing has yet been tested on a real PcW16. Drawing speed has
not been measured in XAnne.

Contents: [CANVAS](#canvas) · [Coordinates and no clipping](#coordinates-and-no-clipping) ·
[The PAINT handler](#paint-handler) · [DRAW CLEAR](#draw-clear) · [DRAW FILL and shades](#draw-fill-and-shades) ·
[DRAW INVERT](#draw-invert) · [DRAW BOX](#draw-box) · [DRAW LINE](#draw-line) ·
[DRAW PIXEL](#draw-pixel) · [DRAW INK](#draw-ink) · [DRAW TEXT and TEXTWIDTH](#draw-text-and-textwidth) ·
[DRAW SCROLL](#draw-scroll) · [POINT](#point) · [What is not available](#what-is-not-available)

## CANVAS

**Syntax**

```text
CANVAS width, height [, PAINT P] [, MOUSE M] [, KEYS K]
```

**Meaning.** Adds a white drawing area with a 1-pixel black frame to the current window, as a
row in the layout (its height plus 8 pixels), at x = 26 in the window. `width` and `height` are
integer literals. `P`, `M` and `K` are `SUB`s without parameters: `PAINT` draws the canvas
(below), `MOUSE` and `KEYS` receive input ([chapter 11](11-menus-keys-mouse.md)). The clauses may
come in any order.

**Requires.** A `WINDOW`. One canvas per program.

**Example**

```pbas
WINDOW "A canvas"
CANVAS 300, 100, PAINT Paint
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
    DRAW BOX 0, 0, 300, 100
    DRAW LINE 0, 0, 299, 99
    DRAW TEXT 10, 10, "Hello, canvas"
END SUB

SUB Quit
    EXIT
END SUB
END
```

**Common errors**

```pbas-error
' expect-error: CANVAS width must be 16 to 568 and height 16 to 300 pixels
WINDOW "Small"
CANVAS 10, 10
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

A normal window holds a canvas at most 330 pixels wide (`check` and `build` both report this):

```pbas-error
' expect-error: a CANVAS in this window is at most 330 pixels wide (got 400)
WINDOW "Too wide"
CANVAS 400, 100
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

The canvas's height must fit the window's rows too: in a normal window with nothing else, at
most 130 pixels; in a `LARGE` window, at most 290:

```pbas-error
' expect-error: the dialog has no room for this CANVAS
WINDOW "Too tall"
CANVAS 300, 131
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

```pbas-error
' expect-error: a program may have one CANVAS
WINDOW "Two"
CANVAS 100, 40
CANVAS 100, 40
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

```pbas-error
' expect-error: DRAW needs a CANVAS declaration
WINDOW "None"
BUTTON "Draw", D
SUB D
    DRAW CLEAR
END SUB
END
```

**Limits.** Width 16 to 568 and height 16 to 300; at most 330 wide in a normal window and 568
in a `LARGE` one; the height must fit the layout (see
[chapter 10](10-windows-and-controls.md#layout-rows-and-limits)). One canvas per program, so with
named windows only one of them has it. `CANVAS` and `DRAW` are statement words only at the start
of a statement, so you may still use them as names.

*Evidence:* tested in XAnne (`../../developer-tests/gfxprobe.pbas`, `gfxbench.pbas`, `uibench.pbas` and
the larger applications).

**See also.** `../../examples/gfxbench.pbas`, `../../examples/tutorial/t2_draw.pbas`,
[Tutorial 2](../TUTORIAL-2-GRAPHICS.md); spec
[§5.6](../../LANGUAGE-SPEC.md#56-m9--canvas-drawing-and-canvas-events).

## Coordinates and no clipping

(0, 0) is the top-left pixel inside the frame; x grows to the right up to width − 1, y grows
downwards up to height − 1. Rectangles are given as x, y, w, h: from x to x + w − 1 across and
y to y + h − 1 down. A rectangle with w or h 0 draws nothing.

**Nothing is clipped.** Every point and rectangle you draw must lie inside the canvas.
Otherwise the program stops with `Runtime error: drawing outside the canvas at line N`, and
nothing is drawn. (The one exception is text, which is cut at the right edge; see
[DRAW TEXT](#draw-text-and-textwidth).) This program stops as soon as its window opens:

```pbas
' expect-message: Runtime error: drawing outside the canvas at line 7
WINDOW "Outside"
CANVAS 100, 50, PAINT Paint
BUTTON "Quit", Quit

SUB Paint
    DRAW BOX 0, 0, 120, 10
END SUB

SUB Quit
    EXIT
END SUB
END
```

To draw something that may be partly outside, clip it yourself first. `lib/geom.pbas` has
`GeomClip(X, Y, W, H, CX, CY, CW, CH)`, which leaves the visible part in `GeomX`, `GeomY`,
`GeomW`, `GeomH` (`GeomW` = 0 when nothing is visible), and `GeomClamp(V, Lo, Hi)`:

```pbas
INCLUDE "lib/geom.pbas"

WINDOW "Clipped"
CANVAS 100, 50, PAINT Paint
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
    ' a 40 x 30 block whose corner is at 80, 35: only part of it is on the canvas
    CALL GeomClip(80, 35, 40, 30, 0, 0, 100, 50)
    IF GeomW > 0 THEN
        DRAW FILL GeomX, GeomY, GeomW, GeomH
    END IF
END SUB

SUB Quit
    EXIT
END SUB
END
```

**Every drawing statement also needs the canvas's window on screen.** The main line runs
before the window opens, so drawing there stops the program with
`Runtime error: the canvas is not on screen at line N`:

```pbas
' expect-message: Runtime error: the canvas is not on screen at line 9
WINDOW "Too early"
CANVAS 100, 50
BUTTON "Quit", Quit
SUB Quit
    EXIT
END SUB
' The window is not open yet:
DRAW CLEAR
END
```

Draw in the `PAINT` handler, or in other handlers, instead. With named windows, the same error
happens when the canvas's window is not the one on screen.

## PAINT handler

The `PAINT` handler runs:
- when the canvas's window opens (including after `SHOW` of that window);
- again after any handler during which an alert (`MESSAGE`, `ASK`, a file report) was shown,
  because Rosanne does not say whether it restores what the alert covered.

An alert shown by `PAINT` itself does not cause another `PAINT`. Draw everything the canvas
shows in `PAINT`, from your variables, and call it (`CALL Paint`) from other handlers when the
picture changes. Handlers may also draw directly, as the mouse example in
[chapter 11](11-menus-keys-mouse.md#the-mouse-mouse-mousex-mousey-mouseevent) does.

A handler that runs `SHOW` for the canvas's window must not draw after the `SHOW`: the window
opens only when the handler returns (known issue KI-59, [limitations](../limitations.md)).

*Evidence:* tested in XAnne.

## DRAW CLEAR

```text
DRAW CLEAR
```

Makes the whole canvas white. *Tested in XAnne.*

## DRAW FILL and shades

**Syntax**

```text
DRAW FILL x, y, w, h
DRAW FILL x, y, w, h, shade
```

**Meaning.** Fills the rectangle. `shade` is 0 to 8: 0 (the default) is black, 8 is white,
and 1 to 7 are Rosanne's grey patterns, from dark to light. Shades are fills only; lines, boxes
and pixels are always solid ink.

**How shades look.** In XAnne, shades 1 to 7 are distinct dotted grey patterns and 8 is a
white block (owner: "distinct grey patterns" on the charts of `../../examples/reporter.pbas`).
**The project's simulator does not model the patterns**: it draws shades 0 to 3 as black and
4 to 8 as white (known issue KI-82), so a simulator test cannot check a pattern's pixels. How
the patterns look on a real PcW16 screen is untested.

**Example**

```pbas
DIM I AS INTEGER

WINDOW "Shades"
CANVAS 300, 60, PAINT Paint
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
    FOR I = 0 TO 8
        DRAW FILL I * 32 + 4, 4, 28, 40, I
        DRAW TEXT I * 32 + 12, 44, STR$(I)
    NEXT I
END SUB

SUB Quit
    EXIT
END SUB
END
```

**Common errors.** A shade outside 0..8 is a runtime error,
`Runtime error: a shade is 0 to 8 at line N`.

*Evidence:* tested in XAnne (`../../developer-tests/gfxprobe.pbas`, nine strips; known issue KI-46 was the
Rosanne 1.12 difference behind shade 8 and is handled by the runtime).

## DRAW INVERT

```text
DRAW INVERT x, y, w, h
```

Flips every pixel of the rectangle (black becomes white and white black). Drawing the same
`INVERT` twice restores the picture, which makes it right for selections and text carets.
*Tested in XAnne.*

```pbas
WINDOW "Invert"
CANVAS 200, 40, PAINT Paint, MOUSE Mouse
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
    DRAW TEXT 10, 12, "Click to flip the middle"
END SUB

SUB Mouse
    IF MOUSEEVENT = 1 THEN
        DRAW INVERT 50, 5, 100, 30
    END IF
END SUB

SUB Quit
    EXIT
END SUB
END
```

## DRAW BOX

```text
DRAW BOX x, y, w, h
```

A 1-pixel outline of the rectangle, in the current ink. *Tested in XAnne.*

## DRAW LINE

```text
DRAW LINE x1, y1, x2, y2
```

A line between two points, both included, in the current ink. In `XOR` ink each pixel of the
line is inverted once. Rosanne 1.12 itself draws only horizontal and vertical lines; the runtime
draws sloped lines as runs of short straight pieces, so every direction works. *Tested in
XAnne.*

## DRAW PIXEL

```text
DRAW PIXEL x, y
```

One pixel, in the current ink. *Tested in XAnne.*

## DRAW INK

**Syntax**

```text
DRAW INK BLACK
DRAW INK WHITE
DRAW INK XOR
```

**Meaning.** Sets the ink for `LINE`, `PIXEL` and `BOX` (and `TEXT` in `XOR`). The ink stays
until changed; it starts as `BLACK`. `XOR` flips the pixels it draws, so drawing the same shape
twice removes it: use it for rubber-band lines and frames that move with the mouse
(`lib/drag.pbas` does this). `TEXT` is drawn black on white unless the ink is `XOR`.
`BITMAP PUT` and `MASK` ignore the ink.

**Example**

```pbas
WINDOW "Inks"
CANVAS 200, 60, PAINT Paint
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
    DRAW FILL 100, 0, 100, 60
    DRAW INK BLACK
    DRAW LINE 0, 10, 199, 10
    DRAW INK WHITE
    DRAW LINE 0, 30, 199, 30
    DRAW INK XOR
    DRAW LINE 0, 50, 199, 50
    DRAW INK BLACK
END SUB

SUB Quit
    EXIT
END SUB
END
```

The black line disappears over the black half, the white line over the white half, and the
XOR line shows on both. *Tested in XAnne.*

## DRAW TEXT and TEXTWIDTH

**Syntax**

```text
DRAW TEXT x, y, text$
DRAW TEXT x, y, text$, cell
TEXTWIDTH(text$)         INTEGER: the width in pixels DRAW TEXT gives the text
```

**Meaning.** `DRAW TEXT` draws the text in Rosanne's dialog font (font 7, proportional, 3 to
13 pixels a character), black on white (or XOR with `DRAW INK XOR`), with its top-left corner
at x, y. A line is 16 pixels high and must fit below y. Characters outside codes 32 to 223 are
shown as `?`.

`TEXTWIDTH(text$)` is the width in pixels of the text as `DRAW TEXT` draws it. Widths add up,
so the caret before character n of a line drawn at x is at `x + TEXTWIDTH(LEFT$(line$, n))`.
`TEXTWIDTH` needs no canvas.

**How much text is drawn.** One `DRAW TEXT` draws at most (canvas width − x) \ 11 characters
(11 pixels is the widest character), and cuts the rest. Ordinary text may therefore stop short
of the right edge although it would fit (known issues KI-39 and KI-76). To fill a line, draw it
in pieces and place each piece with `TEXTWIDTH`, as `../../examples/mdedit4.pbas` does.

The form with `cell` (11 to 64) draws each character on its own at x + i × cell. **It is not
recommended for text people read**: font 7 is proportional, so the result looks letter-spaced,
and the widest characters reach into the next cell. Each character is a separate system call,
so it is also slow. Use `DRAW TEXT x, y, text$` and `TEXTWIDTH` instead.

**Example** (right-aligned text):

```pbas
DIM T$ AS STRING * 24

WINDOW "Text"
CANVAS 300, 60, PAINT Paint
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
    DRAW TEXT 4, 4, "Left"
    T$ = "Right-aligned"
    DRAW TEXT 296 - TEXTWIDTH(T$), 24, T$
    DRAW TEXT 4, 40, "Underlined"
    DRAW LINE 4, 57, 3 + TEXTWIDTH("Underlined"), 57
END SUB

SUB Quit
    EXIT
END SUB
END
```

**Common errors.** A cell outside 11..64 stops the program:
`Runtime error: a text cell is 11 to 64 pixels at line N`. Text whose 16-pixel line does not fit
below y is drawing outside the canvas.

**Limits.** One font, one size; no bold or italic on screen.

*Evidence:* `DRAW TEXT` tested in XAnne (`../../developer-tests/gfxprobe.pbas`); `TEXTWIDTH` tested in
XAnne (`../../developer-tests/rendprb.pbas`: eight strings, each width matching its drawn text); the cell
form tested in XAnne (`../../developer-tests/cellprb.pbas`), with the appearance described above.

**See also.** `../../examples/mdedit4.pbas` (word wrap by width), `lib/listview.pbas`
(columns); spec [§5.6](../../LANGUAGE-SPEC.md#56-m9--canvas-drawing-and-canvas-events).

## DRAW SCROLL

**Syntax**

```text
DRAW SCROLL x, y, w, h, dx, dy
```

**Meaning.** Moves the contents of the rectangle by dx across and dy down (negative values
move left and up). What moves out of the rectangle is lost; the uncovered strip becomes white.
|dx| must be less than w and |dy| less than h. Use it for scrolling traces and lists without
redrawing everything.

**Example** (each click scrolls the picture 10 pixels to the left and draws a new bar at the
right):

```pbas
DIM H AS INTEGER

WINDOW "Scroll"
CANVAS 200, 60, PAINT Paint
BUTTON "Step", StepIt, DEFAULT
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
END SUB

SUB StepIt
    DRAW SCROLL 0, 0, 200, 60, -10, 0
    H = (H + 17) MOD 50 + 5
    DRAW FILL 190, 60 - H, 8, H
END SUB

SUB Quit
    EXIT
END SUB
END
```

*Evidence:* tested in XAnne (`../../developer-tests/gfxprobe.pbas`; `gfxbench.pbas`'s scrolling trace).

## POINT

**Syntax**

```text
POINT(x, y)          INTEGER: 1 if the canvas pixel is black, 0 if white
```

**Meaning.** Reads one pixel of the canvas. It needs a CANVAS, its window on screen, and the
point inside the canvas.

```pbas
DIM Black AS INTEGER

WINDOW "Point"
CANVAS 100, 40, PAINT Paint
BUTTON "Look", Look
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
    DRAW FILL 0, 0, 50, 40
END SUB

SUB Look
    Black = POINT(10, 10) + POINT(60, 10)
    MESSAGE STR$(Black) + " of the two pixels are black"
END SUB

SUB Quit
    EXIT
END SUB
END
```

```pbas-error
' expect-error: POINT reads the canvas: the program has no CANVAS
DIM P AS INTEGER
P = POINT(1, 1)
END
```

*Evidence:* tested in XAnne (`../../developer-tests/bmpprb.pbas`: 7,216 reads in 2 seconds).

## What is not available

There is no statement for: circles, arcs or ellipses; flood fill; polygons; patterned lines;
clipping rectangles (clip yourself, above); other fonts, sizes or styles; colour; more than one
canvas; reading or setting a pixel inside a BITMAP without the canvas (known issue KI-88).
Other BASICs' `PSET`, `LINE (x1,y1)-(x2,y2)`, `CIRCLE`, `PAINT`, `SCREEN` and `COLOR` are
refused:

```pbas-error
' expect-error: expected CLEAR, FILL, INVERT, BOX, LINE, PIXEL, TEXT, SCROLL or INK after DRAW, got CIRCLE
WINDOW "Circle"
CANVAS 100, 50
BUTTON "Quit", Q
SUB Q
    DRAW CIRCLE 50, 25, 10
END SUB
END
```

See [chapter 17](17-unsupported.md).

Next: [13. Bitmaps and sprites](13-bitmaps-and-sprites.md).
