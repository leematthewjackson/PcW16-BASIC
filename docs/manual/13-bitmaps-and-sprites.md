# 13. Bitmaps and sprites

A `BITMAP` is a rectangle of black and white pixels kept in memory. You capture it from the
canvas or load it from a `.PBI` picture file, and draw it on the canvas whole, in part, or
through a mask. With a strip of frames and a mask, a bitmap becomes a sprite sheet.

Pictures are prepared on a PC as PNG files and converted with `tools/pbimage.py`: see
[Making pictures](../graphics-assets.md). Drawing statements are in
[chapter 12](12-drawing.md).

Evidence levels: *Tested in XAnne* (the owner ran it in the XAnne emulator, Rosanne 1.12),
*Simulator only*, *Untested*. Nothing has yet been tested on a real PcW16.

Contents: [DIM … AS BITMAP](#dim--as-bitmap) · [BITMAP GET](#bitmap-get) ·
[BITMAP PUT](#bitmap-put) · [Parts of a bitmap](#parts-of-a-bitmap) ·
[BITMAP MASK](#bitmap-mask) · [BITMAP LOAD and SAVE](#bitmap-load-and-save) ·
[BITMAPW and BITMAPH](#bitmapw-and-bitmaph) · [BITMAP parameters](#bitmap-parameters) ·
[A bitmap cannot be assigned](#a-bitmap-cannot-be-assigned) ·
[Clipping](#clipping) · [Sprite sheets and lib/sprite.pbas](#sprite-sheets-and-libspritepbas) ·
[What is not available](#what-is-not-available)

## DIM … AS BITMAP

**Syntax**

```text
DIM Name AS BITMAP * width, height
```

**Meaning.** Declares a bitmap of that size, white at the start. It is kept in a 16K memory
block of its own, outside the program's resident 16K, so it costs little resident memory.
`width` is 1 to 568 and `height` 1 to 300, and its bytes, (width + 7) \ 8 × height, must fit
16384. `DIM B AS BITMAP * 568, 230` is the largest full-width bitmap.

**Requires.** Nothing to declare it; `GET`, `PUT` and `MASK` need a CANVAS and its window on
screen.

**Common errors**

```pbas-error
' expect-error: declare a bitmap as DIM B AS BITMAP * width, height
DIM B(3) AS BITMAP * 8, 8
END
```

```pbas-error
' expect-error: at most 16384 bytes (one 16K block); got 568 x 231
DIM B AS BITMAP * 568, 231
END
```

**Limits.** Not in arrays or records. Every BITMAP, TEXT buffer and BANKED array together may
use at most 32 blocks of 16K (512K), and the PcW16 must have that memory free when the program
starts ([memory](../memory.md)).

*Evidence:* tested in XAnne (`../../developer-tests/bmpprb.pbas`).

## BITMAP GET

**Syntax**

```text
BITMAP GET Name, x, y
BITMAP GET Name, x, y, w, h
```

**Meaning.** Copies a rectangle of the canvas into the bitmap. The short form copies a
rectangle of the bitmap's current size. The long form copies w × h pixels; its bytes,
(w + 7) \ 8 × h, must fit the bitmap's declared bytes (so another shape of the same size fits
too), and the bitmap's size becomes w × h.

**Example** (draw once, capture, then stamp copies):

```pbas
DIM Star AS BITMAP * 16, 16
DIM Ready AS BOOLEAN

WINDOW "Stamps"
CANVAS 300, 100, PAINT Paint, MOUSE Mouse
BUTTON "Quit", Quit

SUB Paint
    IF NOT Ready THEN
        DRAW CLEAR
        DRAW BOX 0, 0, 16, 16
        DRAW LINE 0, 0, 15, 15
        DRAW LINE 15, 0, 0, 15
        BITMAP GET Star, 0, 0
        Ready = TRUE
    END IF
    DRAW CLEAR
END SUB

SUB Mouse
    IF MOUSEEVENT = 1 AND MOUSEX <= 284 AND MOUSEY <= 84 THEN
        BITMAP PUT Star, MOUSEX, MOUSEY
    END IF
END SUB

SUB Quit
    EXIT
END SUB
END
```

**Common errors.** A rectangle outside the canvas stops the program
(`drawing outside the canvas`). A rectangle larger than the bitmap stops it too:

```pbas
' expect-message: Runtime error: the rectangle is larger than the BITMAP at line 7
DIM Pic AS BITMAP * 16, 16
WINDOW "Too big"
CANVAS 100, 40, PAINT Paint
BUTTON "Quit", Paint
SUB Paint
    BITMAP GET Pic, 0, 0, 40, 40
END SUB
END
```

*Evidence:* tested in XAnne (`../../developer-tests/bmpprb.pbas`: a 120 × 80 GET in 7 ms).

## BITMAP PUT

**Syntax**

```text
BITMAP PUT Name, x, y
```

**Meaning.** Draws the whole bitmap (its current size) with its top-left corner at x, y on the
canvas. **There is one mode only: opaque.** Every pixel is drawn black or white exactly as it
was captured, whatever `DRAW INK` says; the ink is left as it was. For transparency use
[`BITMAP MASK`](#bitmap-mask); there is no XOR or OR put.

Putting back a captured background is how a program erases a moving object (below).

*Evidence:* tested in XAnne (a 120 × 80 PUT in 11 ms).

## Parts of a bitmap

**Syntax**

```text
BITMAP PUT Name, x, y, sx, sy, w, h
```

**Meaning.** Draws only the w × h rectangle of the bitmap whose top-left corner is sx, sy in
the bitmap, with that corner at x, y on the canvas. This is how one bitmap holds many images:
icons, or the frames of an animation.

**Example** (four frames side by side in one bitmap, drawn one at a time):

```pbas
DIM Frames AS BITMAP * 64, 16
DIM F AS INTEGER
DIM Ready AS BOOLEAN

WINDOW "Frames"
CANVAS 200, 40, PAINT Paint
BUTTON "Next", NextFrame, DEFAULT
BUTTON "Quit", Quit

SUB Paint
    IF NOT Ready THEN
        DRAW CLEAR
        DRAW FILL 0, 0, 4, 16
        DRAW FILL 16, 0, 8, 16
        DRAW FILL 32, 0, 12, 16
        DRAW FILL 48, 0, 16, 16
        BITMAP GET Frames, 0, 0
        Ready = TRUE
    END IF
    DRAW CLEAR
    BITMAP PUT Frames, 90, 12, F * 16, 0, 16, 16
END SUB

SUB NextFrame
    F = (F + 1) MOD 4
    BITMAP PUT Frames, 90, 12, F * 16, 0, 16, 16
END SUB

SUB Quit
    EXIT
END SUB
END
```

**Common errors.** The part must lie inside the bitmap's current size:

```pbas
' expect-message: Runtime error: the part is outside the BITMAP at line 7
DIM Pic AS BITMAP * 16, 16
WINDOW "Part"
CANVAS 100, 40, PAINT Paint
BUTTON "Quit", Paint
SUB Paint
    BITMAP PUT Pic, 0, 0, 8, 8, 16, 16
END SUB
END
```

**Speed.** A part that starts at the bitmap's left edge and is as wide as the bitmap is drawn
straight from the bitmap; any other part is copied and shifted first, which is slower. That is
why `pbimage.py sheet` stacks frames **one under another** (frame k is the part
`0, k * H, W, H`), unlike the side-by-side example above.

*Evidence:* tested in XAnne (`../../developer-tests/sprprb.pbas`).

## BITMAP MASK

**Syntax**

```text
BITMAP MASK Image, Mask, x, y
BITMAP MASK Image, Mask, x, y, sx, sy, w, h
```

**Meaning.** Draws `Image` through `Mask`, an ordinary bitmap of at least the image's size,
matched pixel for pixel from the top left. Where the mask is **white**, the image's pixel is
drawn (black or white); where the mask is **black**, the canvas keeps its own pixel. The long
form does the same for a part, which must lie inside both bitmaps. `pbimage.py --mask` writes
masks in this convention (white = drawn).

**Example** (a ring drawn over a grey background; the middle stays transparent):

```pbas
DIM Ring AS BITMAP * 16, 16
DIM RingM AS BITMAP * 16, 16
DIM Ready AS BOOLEAN

WINDOW "Mask"
CANVAS 200, 60, PAINT Paint
BUTTON "Quit", Quit

SUB Paint
    IF NOT Ready THEN
        DRAW CLEAR
        DRAW FILL 0, 0, 16, 16
        BITMAP GET Ring, 0, 0
        DRAW FILL 0, 0, 16, 16, 8
        DRAW FILL 4, 4, 8, 8
        BITMAP GET RingM, 0, 0
        Ready = TRUE
    END IF
    DRAW CLEAR
    DRAW FILL 0, 0, 200, 60, 4
    BITMAP MASK Ring, RingM, 92, 22
END SUB

SUB Quit
    EXIT
END SUB
END
```

Here the image is solid black and the mask is white except for an 8 × 8 black square in the
middle, so the background shows through the hole. In practice you make both from a PNG with
transparency: see [Making pictures](../graphics-assets.md).

`PUT` and `MASK` hide the mouse pointer while they draw.

*Evidence:* tested in XAnne (`../../developer-tests/sprprb.pbas`: "0 wrong" in every mask test, with
and without code banks).

## BITMAP LOAD and SAVE

**Syntax**

```text
BITMAP LOAD Name, file$
BITMAP SAVE Name, file$
```

**Meaning.** `LOAD` reads a PBI1 picture file into the bitmap; the bitmap's size becomes the
file's. `SAVE` writes the bitmap (its current size) as a PBI1 file, safely: it writes
`NAME.NEW`, reads it back, renames the old file to `NAME.BAK`, then renames `NAME.NEW` to the
name. `file$` is a STRING expression holding a DOS 8.3 name.

Since M14, `SAVE` first reads the start of `NAME.NEW` and `NAME.BAK`, where they exist. One
shorter than 4 bytes is a leftover and is replaced. One that begins `PBI1` is a picture's and is
replaced (nothing after those 4 bytes is checked). Anything else (for example `FORM.BAK` is the
backup of a database `FORM.DSN`, or a text file) belongs to another file: the save does nothing
and sets `IOERR` to 253. When the file itself does not exist yet, `SAVE` keeps `NAME.BAK` (up to M13 it
deleted it).

Neither ever stops the program. Both set `IOERR`: 0 means done. Otherwise:

| IOERR | Meaning |
|---|---|
| a Rosanne code | the file could not be found, read or written |
| 247 | the name ends in `.NEW` or `.BAK` (refused at compile time for a literal) |
| 248 | not a PBI1 file |
| 250 | another version of the format |
| 251 | damaged (its check, its length, or bytes after the end) |
| 252 | larger than the bitmap |
| 253 | `SAVE` only: `NAME.NEW` or `NAME.BAK` belongs to another kind of file; nothing was changed (M14) |

A failed `LOAD` leaves the size unchanged but may have replaced some pixels: draw the bitmap
only after `IOERR = 0`. `LOAD` does not look for `NAME.NEW` or `NAME.BAK`.

**Where the files are.** Files are read and written in the folder the program was built for:
`\PCW\FOLDER01` on the floppy unless you built with `--folder`
([chapter 16](16-building-and-commands.md#toolsbuildpy-options)). Copy every `.PBI` file a
program loads into that folder, next to its `.PRG` ([Making pictures](../graphics-assets.md#copying-pictures-with-the-program)).

**Example** (load a picture at start; report a missing file):

```pbas
DIM Icons AS BITMAP * 24, 48
DIM Loaded AS BOOLEAN

WINDOW "Icons"
CANVAS 100, 60, PAINT Paint
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
    IF Loaded THEN
        BITMAP PUT Icons, 10, 5, 0, 0, 24, 24
        BITMAP PUT Icons, 50, 5, 0, 24, 24, 24
    ELSE
        DRAW TEXT 4, 20, "No T2ICONS.PBI"
    END IF
END SUB

SUB Quit
    EXIT
END SUB

BITMAP LOAD Icons, "T2ICONS.PBI"
Loaded = IOERR = 0
IF NOT Loaded THEN
    MESSAGE "T2ICONS.PBI could not be loaded (code " + STR$(IOERR) + ")"
END IF
END
```

(`T2ICONS.PBI` is built from `examples/assets/tutorial-icons.png` by
`pcw16basic assets`; it is a 24 × 48 strip of two icons.)

**Common errors**

```pbas-error
' expect-error: .NEW and .BAK are the save's own temporary and backup files
DIM B AS BITMAP * 8, 8
BITMAP SAVE B, "PIC.NEW"
END
```

**Limits.** One name, several files: `FORM.PBI` and another file `FORM.DSN` share
`FORM.BAK`. Since M14 the second of the two saves is refused with `IOERR` 253 instead of
replacing the other's backup (known issue KI-91, [limitations](../limitations.md)). Use
different names, or `lib/files.pbas` `SafeReplace`. Two pictures, `FORM.PBI` and `FORM.IMG`,
still share their companions.

*Evidence:* tested in XAnne (`../../developer-tests/bmpprb.pbas`, `paint.pbas` saving and reopening
pictures; the owner's own `TEST.PBI` checked on a PC with `tools/pbicheck.py`). The M14 checks
of `NAME.NEW` and `NAME.BAK` (IOERR 253) are simulator only, awaiting the owner's XAnne retest.

## BITMAPW and BITMAPH

```text
BITMAPW(Name)        INTEGER: the bitmap's current width
BITMAPH(Name)        INTEGER: its current height
```

The current size changes with `GET … w, h` and `LOAD`. This program shows its alert as its
window opens and then ends, so the alert is checked on the simulator:

```pbas
' expect-message: 32 x 8
DIM Pic AS BITMAP * 16, 16
WINDOW "Size"
CANVAS 100, 40, PAINT Paint
BUTTON "Quit", Quit
SUB Paint
    ' 32 x 8 has the same bytes as 16 x 16, so it fits
    BITMAP GET Pic, 0, 0, 32, 8
    MESSAGE STR$(BITMAPW(Pic)) + " x " + STR$(BITMAPH(Pic))
    EXIT
END SUB
SUB Quit
    EXIT
END SUB
END
```

## BITMAP parameters

**Syntax**

```text
SUB Name(Pic AS BITMAP, X AS INTEGER, …)
CALL Name(SomeBitmap, 10, …)
```

**Meaning.** A `SUB` or `FUNCTION` may take a bitmap. The argument must be a bitmap's name
(a DIM'd bitmap or the caller's own BITMAP parameter). Unlike every other parameter, it is
passed **by reference**: a `GET` or `LOAD` through `Pic` changes the caller's bitmap. This is
how `lib/sprite.pbas` and `lib/toolbar.pbas` draw your images.

**Example**

```pbas
DIM Logo AS BITMAP * 16, 16
DIM Ready AS BOOLEAN

WINDOW "Parameter"
CANVAS 200, 40, PAINT Paint
BUTTON "Quit", Quit

SUB ShowTwice(Pic AS BITMAP, X AS INTEGER)
    BITMAP PUT Pic, X, 4
    BITMAP PUT Pic, X + 20, 4
END SUB

SUB Paint
    IF NOT Ready THEN
        DRAW CLEAR
        DRAW BOX 0, 0, 16, 16
        DRAW FILL 4, 4, 8, 8
        BITMAP GET Logo, 0, 0
        Ready = TRUE
    END IF
    DRAW CLEAR
    CALL ShowTwice(Logo, 50)
END SUB

SUB Quit
    EXIT
END SUB
END
```

**Common errors.** An argument that is not a bitmap's name is refused:

```pbas-error
' expect-error: is a BITMAP parameter: pass it a BITMAP's name
DIM N AS INTEGER
SUB S(P AS BITMAP)
END SUB
CALL S(N)
END
```

**A BITMAP parameter cannot be assigned**: `P = B` is a compile error
([below](#a-bitmap-cannot-be-assigned)).

*Evidence:* tested in XAnne through the programs that use the libraries (`jumper.pbas`,
`paint2.pbas`, `sprited.pbas`).

## A bitmap cannot be assigned

`B = C` for two bitmaps, and assigning anything to a BITMAP parameter (`Pic = Other`), are
compile errors, as the specification says. (Up to M13 the compiler accepted them, and they did
nothing.)

```pbas-error
' expect-error: B is a BITMAP and cannot be assigned
DIM B AS BITMAP * 8, 8
DIM C AS BITMAP * 32, 16
B = C
END
```

```pbas-error
' expect-error: P is a BITMAP parameter and cannot be assigned
DIM C AS BITMAP * 8, 8
SUB Copy(P AS BITMAP)
    P = C
END SUB
END
```

To copy one bitmap to another, draw it on the canvas and capture it:
`BITMAP PUT C, 0, 0` then `BITMAP GET B, 0, 0, BITMAPW(C), BITMAPH(C)`. (TEXT buffers cannot
be assigned either; see [chapter 7](07-text-buffers.md).)

*Evidence:* compiler.

## Clipping

Nothing is clipped. A `PUT`, `MASK` or `GET` whose rectangle is not wholly inside the canvas
stops the program with `drawing outside the canvas`. To draw an image that is partly off the
canvas, draw only its visible part: `GeomClip` in `lib/geom.pbas` gives the visible rectangle
and how far its corner moved (`GeomDX`, `GeomDY`), which is the `sx, sy` of the part to draw.
`lib/sprite.pbas` does this for you.

```pbas
INCLUDE "lib/geom.pbas"

DIM Pic AS BITMAP * 32, 32
DIM Ready AS BOOLEAN

WINDOW "Clipped picture"
CANVAS 100, 50, PAINT Paint
BUTTON "Quit", Quit

' Draw Pic with its corner at X, Y, even if part of it is off the canvas.
SUB PutClipped(X AS INTEGER, Y AS INTEGER)
    CALL GeomClip(X, Y, 32, 32, 0, 0, 100, 50)
    IF GeomW > 0 THEN
        BITMAP PUT Pic, GeomX, GeomY, GeomDX, GeomDY, GeomW, GeomH
    END IF
END SUB

SUB Paint
    IF NOT Ready THEN
        DRAW CLEAR
        DRAW FILL 0, 0, 32, 32
        DRAW FILL 8, 8, 16, 16, 8
        BITMAP GET Pic, 0, 0
        Ready = TRUE
    END IF
    DRAW CLEAR
    CALL PutClipped(80, 30)
    CALL PutClipped(-10, -10)
END SUB

SUB Quit
    EXIT
END SUB
END
```

## Sprite sheets and lib/sprite.pbas

A *sprite sheet* is one bitmap holding a sprite's frames, W × H each, **one under another**,
with a mask bitmap of the same shape. `tools/pbimage.py sheet` makes both from one PNG with
transparency; frame k is the part `0, k * H, W, H` ([Making pictures](../graphics-assets.md)).

`lib/sprite.pbas` (with `lib/geom.pbas`) manages up to 16 masked sprites on a canvas:
it draws a frame through its mask, clips it at the edges of the play area, and puts the
background back behind it when it moves. You keep a picture of the whole play area in a
background bitmap.

- Set `SprCW`, `SprCH` (the play area, normally the canvas size) and, for each slot I (1..16),
  `SprW(I)`, `SprH(I)` (the frame size), `SprX(I)`, `SprY(I)`.
- `SpriteShow(Sheet, Mask, I)` draws slot I; `SpriteHide(Back, I)` puts the background back;
  `SpriteMove(Sheet, Mask, Back, I, X, Y, F)` hides, moves to X, Y with frame F, and shows.
- `SpriteHits(I, J)` and `SpriteHitsRect(I, X, Y, W, H)` test overlaps.

**Example** (the sprite is drawn and captured in the program; a sheet loaded with `BITMAP LOAD`
works the same way):

```pbas
INCLUDE "lib/geom.pbas"
INCLUDE "lib/sprite.pbas"

DIM Look AS BITMAP * 16, 16
DIM LookM AS BITMAP * 16, 16
DIM Back AS BITMAP * 300, 100
DIM Ready AS BOOLEAN

WINDOW "Sprite"
CANVAS 300, 100, PAINT Paint
BUTTON "Left", GoLeft
BUTTON "Right", GoRight, DEFAULT
BUTTON "Quit", Quit

SUB Paint
    IF NOT Ready THEN
        ' the sprite: a black square with two white eyes, mask all white
        DRAW CLEAR
        DRAW FILL 0, 0, 16, 16
        DRAW FILL 4, 4, 3, 3, 8
        DRAW FILL 9, 4, 3, 3, 8
        BITMAP GET Look, 0, 0
        DRAW FILL 0, 0, 16, 16, 8
        BITMAP GET LookM, 0, 0
        ' the background: grey ground
        DRAW CLEAR
        DRAW FILL 0, 84, 300, 16, 4
        BITMAP GET Back, 0, 0
        Ready = TRUE
    END IF
    BITMAP PUT Back, 0, 0
    CALL SpriteShow(Look, LookM, 1)
END SUB

SUB GoLeft
    CALL SpriteMove(Look, LookM, Back, 1, SprX(1) - 8, SprY(1), 0)
END SUB

SUB GoRight
    CALL SpriteMove(Look, LookM, Back, 1, SprX(1) + 8, SprY(1), 0)
END SUB

SUB Quit
    EXIT
END SUB

SprCW = 300
SprCH = 100
SprW(1) = 16
SprH(1) = 16
SprX(1) = 20
SprY(1) = 68
END
```

The sprite may walk off either edge; only its visible part is drawn. For movement driven by a
timer and held keys, see [chapter 14](14-timers-and-animation.md) and
[Tutorial 3](../TUTORIAL-3-GAME.md).

**Limits.** At most 16 sprites per program. Overlapping sprites: hide every sprite that moves,
then show them all again, back to front. Each library's arrays use resident memory
([memory](../memory.md)).

*Evidence:* tested in XAnne (`jumper.pbas`, "completely playable"; `../../examples/tutorial/t3_hop.pbas`).

**See also.** `../../examples/jumper.pbas`, `../../examples/sprited.pbas` (an editor for
16 × 16 sprites with masks), `../../examples/paint2.pbas`; [libraries](../libraries/README.md);
spec [§5.12](../../LANGUAGE-SPEC.md#512-m12--bitmaps-and-point) and
[§5.14](../../LANGUAGE-SPEC.md#514-m13--parts-of-bitmaps-masks-and-bitmap-parameters).

## What is not available

No statement sets or reads one pixel *inside* a bitmap (draw on the canvas and `GET`, or `PUT`
and read back with `POINT`; known issue KI-88). There is no scaling, rotation, flipping,
transparent `PUT` without a mask, XOR `PUT`, bitmap arrays, bitmaps in records, colour, or file
format other than PBI1 (convert PNG on a PC with `tools/pbimage.py`; PBM with
`tools/pbicheck.py`). Screens and bitmaps cannot be printed ([chapter 15](15-printing.md)).

Next: [14. Timers and animation](14-timers-and-animation.md).
