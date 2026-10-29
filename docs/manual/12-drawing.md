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
[DRAW SCROLL](#draw-scroll) · [POINT](#point) · [DRAW FONT and ALIGN](#draw-font-and-align) ·
[Scalable type](#scalable-type-type-font-and-draw-type) · [Several canvases](#several-canvases-draw-on) ·
[What is not available](#what-is-not-available)

## CANVAS

**Syntax**

```text
CANVAS [Name,] width, height [, PAINT P] [, MOUSE M] [, KEYS K]
```

**Meaning.** Adds a white drawing area with a 1-pixel black frame to the current window, as a
row in the layout (its height plus 8 pixels), at x = 26 in the window. `width` and `height` are
integer literals. `P`, `M` and `K` are `SUB`s without parameters: `PAINT` draws the canvas
(below), `MOUSE` and `KEYS` receive input ([chapter 11](11-menus-keys-mouse.md)). The clauses may
come in any order.

**Requires.** A `WINDOW`. A program may have up to 8 canvases; with more than one, each needs a name
([Several canvases](#several-canvases-draw-on)).

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
' expect-error: with more than one CANVAS each needs a name
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
[chapter 10](10-windows-and-controls.md#layout-rows-and-limits)). Up to 8 canvases in a program, in
any of its windows. `CANVAS` and `DRAW` are statement words only at the start
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

**The runtime keeps no copy of what is drawn.** When PAINT runs again (after an alert, or when a
window opens again), it starts from whatever is on the screen, and a canvas's earlier drawing may
be gone. So whatever the program wants kept, strokes included, must be in its variables, and PAINT
must draw it all back. Freehand drawing that a MOUSE handler draws directly is lost unless the
handler also stores it: `examples/sketchpad.pbas` keeps its last 250 dots in arrays, and PAINT II
keeps its picture in a BITMAP. This holds for every canvas of a program with several.

*Evidence:* tested in XAnne (including M15c C5 and r2 R6: a drawing PAINT does not store is lost
after an alert; one it stores comes back).

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

**Limits.** Font 7 unless [DRAW FONT](#draw-font-and-align) chooses another; scalable sizes, bold and
italic are [DRAW TYPE](#scalable-type-type-font-and-draw-type)'s.

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

## DRAW FONT and ALIGN

**Syntax**

```text
DRAW FONT n                          n 1..12: the dialog font of later DRAW TEXT and TEXTWIDTH
DRAW TEXT x, y, text$ ALIGN LEFT     (or CENTRE, CENTER, RIGHT): text placed about x
```

**Meaning.** Rosanne has twelve dialog fonts. Font 7 is the one windows use, and the default.

`DRAW FONT n` chooses the font for the `DRAW TEXT` and `TEXTWIDTH` that follow. In a program that uses `DRAW FONT`:
- `DRAW TEXT` measures the text and cuts it at the last whole character before the right edge;
- programs without `DRAW FONT` keep the 11-pixel rule above.

There are no styles. The fonts' line heights are not yet measured, so leave room by eye; a 16-pixel line must still fit below y.

`ALIGN CENTRE` centres the text on x, and `ALIGN RIGHT` ends it at x. It is never placed left of the canvas's left edge. `ALIGN LEFT` is the ordinary `DRAW TEXT`.

**Example**

```pbas
DIM N AS INTEGER

WINDOW "Fonts", LARGE
CANVAS 400, 200, PAINT Paint
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
    FOR N = 1 TO 6
        DRAW FONT N * 2
        DRAW TEXT 200, N * 30 - 26, "Font " + STR$(N * 2) ALIGN CENTRE
    NEXT N
END SUB

SUB Quit
    EXIT
END SUB
END
```

**Common errors.** `DRAW FONT 0` or `13` stops the program: `Runtime error: a font is 1 to 12 at line N`.
`ALIGN` with a cell width is a compile error.

*Evidence:*
- tested in XAnne (M15a; M15c F1–F5; r2 R1): all twelve fonts, `TEXTWIDTH` in each, the measured cut at the right frame (fonts 11 and 12 included) and `ALIGN`;
- the fonts' line heights are not measured, so there is no `TEXTHEIGHT` (known issue KI-106); fonts 11 and 12 have unusual glyphs of Rosanne's own;
- `examples/fontbook.pbas` shows every font with its widths.

## Scalable type: TYPE FONT and DRAW TYPE

**Syntax**

```text
TYPE FONT SWISS | TIMES, size [, BOLD] [, ITALIC]   size 6, 8, 10, 11, 12, 14, 18, 24, 36 or 72
DRAW TYPE x, y, text$                               the text in that font, its top-left at x, y
TYPEWIDTH(text$)                                    INTEGER: its width in pixels
TYPEHEIGHT                                          INTEGER: the line's height in pixels
```

**Meaning.** The same scalable fonts `PAGE` prints with ([chapter 15](15-printing.md)), drawn on the canvas.
- Without `TYPE FONT`, Times 10 is used.
- `DRAW INK XOR` draws the text in XOR; otherwise it is black on white.
- The whole line (`TYPEHEIGHT`) must fit below y.
- The text is cut before the first character that would pass the right edge.
- Printing and screen type may be mixed in any order.

**Example**

```pbas
WINDOW "Type", LARGE
CANVAS 400, 120, PAINT Paint
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
    TYPE FONT SWISS, 10
    DRAW TYPE 10, 10, "Swiss at 10 points"
    TYPE FONT TIMES, 10, BOLD, ITALIC
    DRAW TYPE 10, 10 + TYPEHEIGHT + 4, "Times, bold and italic"
    DRAW LINE 10, 40, 10 + TYPEWIDTH("Times, bold and italic"), 40
END SUB

SUB Quit
    EXIT
END SUB
END
```

**Common errors.**
- A size not in the list is a compile error for a literal, and otherwise stops the program: `Runtime error: a type size is 6, 8, 10, 11, 12, 14, 18, 24, 36 or 72 at line N`.
- A line that does not fit below y is drawing outside the canvas.

*Evidence:*
- Tested in XAnne (M15a, M15c and its r2 retest): every size from 6 to 72 points, Times, bold and italic, `TYPEWIDTH` and `TYPEHEIGHT` against the drawing, the top-left placement, the right-edge cut (italic keeps a quarter of its ascender free), and printing in the same program (provisionally, printed to PDF).
- The speed of type is not measured.
- `examples/m15_specimen.pbas` shows every size.

## Several canvases: DRAW ON

**Syntax**

```text
CANVAS Name, width, height [, PAINT P] [, MOUSE M] [, KEYS K]
DRAW ON Name          later DRAW statements draw on Name
FOCUS Name            keys go to the canvas Name
```

**Meaning.** A program may have up to 8 canvases, each named, in any of its windows.
- **One canvas or several.** A program with one canvas may leave it unnamed (`CANVAS width, height, …`) and needs no `DRAW ON`: everything draws on it, exactly as before M15, with the same code. As soon as a program has two canvases, every one must be named, and the program carries a small table of its canvases.
- `DRAW ON` chooses the canvas that later drawing goes to. The first canvas is chosen at the start.
- While a canvas's own `PAINT`, `MOUSE` or `KEYS` handler runs, drawing goes to that canvas. After every handler, the `DRAW ON` choice applies again.
- Each canvas keeps its own `DRAW FONT` and `TYPE FONT`.
- When a window opens, each of its canvases' `PAINT` runs, in source order.
- A press goes to the canvas under the pointer and gives it the keyboard; the drag and the release go to the canvas pressed.
- `FOCUS Name` gives a canvas the keyboard without a click.

**Example**

```pbas
DIM Shade AS INTEGER
DIM DX(100) AS INTEGER
DIM DY(100) AS INTEGER
DIM DS(100) AS INTEGER
DIM Dots AS INTEGER
DIM N AS INTEGER

WINDOW "Two canvases", LARGE
CANVAS Strip, 400, 30, PAINT StripPaint, MOUSE StripMouse
CANVAS Board, 400, 150, PAINT BoardPaint, MOUSE BoardMouse
BUTTON "Clear", Clear
BUTTON "Quit", Quit

SUB StripPaint
    DRAW CLEAR
    DRAW FILL 0, 0, 50, 30, Shade
END SUB

SUB StripMouse
    IF MOUSEEVENT = 1 THEN
        Shade = (Shade + 1) MOD 8
        CALL StripPaint
    END IF
END SUB

SUB BoardPaint
    DRAW CLEAR
    FOR N = 1 TO Dots
        DRAW FILL DX(N), DY(N), 4, 4, DS(N)
    NEXT N
END SUB

SUB BoardMouse
    IF MOUSEX >= 0 AND MOUSEX < 396 AND MOUSEY >= 0 AND MOUSEY < 146 THEN
        DRAW FILL MOUSEX, MOUSEY, 4, 4, Shade
        IF Dots < 100 THEN
            Dots = Dots + 1
            DX(Dots) = MOUSEX
            DY(Dots) = MOUSEY
            DS(Dots) = Shade
        END IF
    END IF
END SUB

SUB Clear
    Dots = 0
    DRAW ON Board
    CALL BoardPaint
END SUB

SUB Quit
    EXIT
END SUB
END
```

```pbas-error
' expect-error: no CANVAS NOWHERE is declared
WINDOW "One"
CANVAS Board, 100, 40
BUTTON "Quit", Q
SUB Q
    DRAW ON Nowhere
END SUB
END
```

The Board stores each square it draws, so its PAINT can draw them back after an alert; `Clear`, a button's handler, uses `DRAW ON` to draw on the Board. `examples/sketchpad.pbas` is a fuller version, with keys and `FOCUS`.

**Limits.** Each canvas takes a row of its window, so a window holds only as many as its height allows.

*Evidence:* tested in XAnne (M15c C1–C7, r2 R6): presses, drags that stay with the canvas pressed, keys, `FOCUS` without a click, repaint after an alert, and a canvas in a second window.

## What is not available

There is no statement for: circles, arcs or ellipses; flood fill; polygons; patterned lines;
clipping rectangles (clip yourself, above); styles for the dialog fonts; colour; reading or setting a pixel inside a BITMAP without the canvas (known issue KI-88).
Other BASICs' `PSET`, `LINE (x1,y1)-(x2,y2)`, `CIRCLE`, `PAINT`, `SCREEN` and `COLOR` are
refused:

```pbas-error
' expect-error: expected CLEAR, FILL, INVERT, BOX, LINE, PIXEL, TEXT, SCROLL, INK, FONT, TYPE or ON after DRAW, got CIRCLE
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
