# lib/sprite.pbas: masked sprites with background restore

`lib/sprite.pbas` draws up to 16 sprites on a CANVAS. Each sprite's frames come from one BITMAP strip, are drawn through a mask (so the background shows around the shape), are clipped at the edges of the play area, and are removed by putting back the background from a saved picture. It also tests sprites for overlap.

**Evidence:** *Tested in XAnne* through JUMPER (the owner: "completely playable", no lasting sprite trails) and the third tutorial game (T3HOP). The masking itself was confirmed by the SPRPROBE masks test (`developer-tests/sprprb.pbas`, 0 wrong pixels). Not yet tested on a real PcW16.

## Adding it

```text
INCLUDE "lib/sprite.pbas"
```

The program needs:

- a CANVAS;
- a sheet BITMAP and a mask BITMAP for each kind of sprite, and a background BITMAP of the play area.

(Up to M13 a program that included this library but declared no BITMAP failed in the assembler; M14 fixed this.)

It needs no other library. JUMPER and T3HOP also use [geom](geom.md), [keys](keys.md) and [pace](pace.md).

## Assets

A sprite's frames are one BITMAP: frames of W × H pixels one under another, frame 0 at the top. Frame F is the part at 0, F × H. The mask BITMAP has the same shape: **white where the sprite is drawn, black where it is transparent**. `pcw16basic image sheet` makes both from a PNG (its `--mask` option); see [graphics assets](../graphics-assets.md). You can also build them at run time with `BITMAP GET`, as the example below does.

The *play area* is the rectangle 0, 0, `SprCW`, `SprCH` of the canvas; set both, normally to the canvas size. The background BITMAP is a picture of the whole play area as drawn at 0, 0. Take it with `BITMAP GET Back, 0, 0, w, h` after drawing the scenery.

## Slots

Slot I (1..16) describes one sprite. Your program fills `SprX(I)`, `SprY(I)` (top-left corner), `SprW(I)`, `SprH(I)` (frame size) and `SprF(I)` (frame number). `SprOn(I)` is TRUE while it is drawn.

## Procedures and functions

Parameters not marked BITMAP are INTEGER.

| Name | Kind | Parameters | Result | What it does |
|---|---|---|---|---|
| `SpriteShow` | SUB | `Sheet AS BITMAP, Mask AS BITMAP, I` | | Draws slot I as it is now; `SprOn(I)` becomes TRUE. |
| `SpriteHide` | SUB | `Back AS BITMAP, I` | | Puts back the background where slot I was drawn; `SprOn(I)` becomes FALSE. Does nothing if it was not shown. |
| `SpriteMove` | SUB | `Sheet AS BITMAP, Mask AS BITMAP, Back AS BITMAP, I, X, Y, F` | | Hides slot I, moves it to X, Y with frame F, and shows it. |
| `SpriteHits` | FUNCTION | `I, J` | BOOLEAN | Slots I and J overlap (by rectangle). |
| `SpriteHitsRect` | FUNCTION | `I, X, Y, W, H` | BOOLEAN | Slot I overlaps the rectangle. |
| `SpriteDraw` | SUB | `Sheet AS BITMAP, Mask AS BITMAP, X, Y, F, W, H` | | Draws frame F at X, Y through the mask, without a slot. |
| `SpriteDrawOpaque` | SUB | `Sheet AS BITMAP, X, Y, F, W, H` | | The same without a mask: the whole frame rectangle is drawn. |
| `SpriteBack` | SUB | `Back AS BITMAP, X, Y, W, H` | | Puts back that part of the background. |
| `SpriteClip` | SUB | `X, Y, W, H` | `SprVX/VY/VW/VH` | The visible part of a rectangle (`SprVW` 0: none); used by the others. |

BITMAP parameters are passed by reference, so passing a large bitmap costs nothing.

**Overlapping sprites:** hide every sprite that moves, then show them all again, back to front. Hiding one sprite restores the background, not the sprites under it.

## Names it defines

| Name | Type |
|---|---|
| `SPRITES` | CONST = 16 |
| `SprX(16)`, `SprY(16)`, `SprW(16)`, `SprH(16)`, `SprF(16)` | INTEGER arrays |
| `SprOn(16)` | BOOLEAN array |
| `SprCW`, `SprCH` | INTEGER, the play area; your program sets them |
| `SprVX`, `SprVY`, `SprVW`, `SprVH` | INTEGER, results of `SpriteClip` |

Names start with `Sprite` or `Spr`, and the CONST is `SPRITES`, so a variable of your own called `Sprites` clashes with it.

## Memory cost

Measured in a minimal host with a canvas and one small BITMAP:

| | bytes |
|---|---:|
| whole program, one 16K image | +2,976 |
| resident 16K block, procedures in code banks | +1,493 |
| of which the slot arrays | +228 |

Each BITMAP the program declares takes a 16K block of its own outside the resident block, whatever its size (see [memory.md](../memory.md)); JUMPER uses seven.

## Errors

- A slot number outside 1..16 stops the program with `Runtime error: index out of range`.
- A frame number past the end of the sheet asks for a part outside the bitmap, and the program stops with a runtime error. Keep F below the sheet's height ÷ H.
- With `SprCW` and `SprCH` left at 0, nothing is drawn.
- Drawing needs the canvas's window on screen; draw from PAINT, TIMER, MOUSE or KEYS handlers, not from the main line before the window opens.

## Example

Builds a two-frame sprite and its mask at run time, then moves it across a patterned background.

```pbas
INCLUDE "lib/sprite.pbas"
DIM Sheet AS BITMAP * 16, 32
DIM Mask AS BITMAP * 16, 32
DIM Back AS BITMAP * 160, 80
DIM Ready AS BOOLEAN
WINDOW "Sprite"
CANVAS 160, 80, PAINT Paint
BUTTON "Quit", Quit
TIMER Tick, EVERY 2 TICKS
SUB Paint
    IF NOT Ready THEN
        DRAW CLEAR
        DRAW FILL 2, 2, 12, 12, 0
        DRAW FILL 5, 5, 6, 6, 8
        DRAW FILL 2, 18, 12, 12, 0
        BITMAP GET Sheet, 0, 0, 16, 32
        DRAW FILL 0, 0, 16, 32, 0
        DRAW FILL 2, 2, 12, 12, 8
        DRAW FILL 2, 18, 12, 12, 8
        BITMAP GET Mask, 0, 0, 16, 32
        DRAW FILL 0, 0, 160, 80, 6
        BITMAP GET Back, 0, 0, 160, 80
        Ready = TRUE
    END IF
    BITMAP PUT Back, 0, 0
    CALL SpriteShow(Sheet, Mask, 1)
END SUB
SUB Tick
    LOCAL X AS INTEGER
    IF NOT Ready THEN
        EXIT SUB
    END IF
    X = SprX(1) + 2
    IF X >= 160 THEN
        X = -16
    END IF
    CALL SpriteMove(Sheet, Mask, Back, 1, X, 32, ((X + 16) / 8) MOD 2)
END SUB
SUB Quit
    EXIT
END SUB
SprCW = 160
SprCH = 80
SprW(1) = 16
SprH(1) = 16
SprX(1) = 0
SprY(1) = 32
SprW(2) = 16
SprH(2) = 16
SprX(2) = 10
SprY(2) = 40
IF SpriteHits(1, 2) THEN
    MESSAGE "slots 1 and 2 overlap"
END IF
END
' expect-message: slots 1 and 2 overlap
```

The sprite enters partly off the left edge (X = −16 .. −1); clipping draws only the visible part. A real game paces the movement with [lib/pace.pbas](pace.md) instead of moving a fixed step per event.

## Used by

- `examples/jumper.pbas`
- `examples/tutorial/t3_hop.pbas` ([Tutorial 3](../TUTORIAL-3-GAME.md))

## Limitations

- At most 16 slots; collision tests use rectangles, not pixels.
- No scaling, rotation or flipping: draw every frame you need into the sheet.
- Every sprite move redraws through the BIOS blitter. In XAnne a sprite move took about 3 ms (SPRPROBE); many large sprites per frame slow a game down.

See also: [library index](README.md), [bitmaps and sprites](../manual/13-bitmaps-and-sprites.md), [graphics assets](../graphics-assets.md), [generated reference](../LIBRARY-REFERENCE.md).
