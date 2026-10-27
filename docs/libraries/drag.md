# lib/drag.pbas: pressing, dragging and releasing on a canvas

`lib/drag.pbas` turns the raw mouse events of a CANVAS into a drag: where the button went down, where the pointer is now, how far it has moved, whether the gesture was a click or a real drag, and when it ended. It also draws rubber-band feedback (a box, a line or any outline) in XOR ink, so that drawing it a second time erases it.

**Evidence:** *Tested in XAnne* through DESIGNER (selecting, dragging and resizing objects; the owner found its outline drag smooth). The second tutorial (T2DRAW) uses it too, but has no recorded XAnne result. Not yet tested on a real PcW16.

## Adding it

```text
INCLUDE "lib/drag.pbas"
```

The program must have a CANVAS with a MOUSE handler. Without a CANVAS the build stops with `drag.pbas:49:9: undefined variable MOUSEEVENT`. It needs no other library.

## How to use it

1. Set `DragW` and `DragH` to the canvas's width and height, once, before the first mouse event (in the main line).
2. Call `DragMouse` first thing in the canvas's MOUSE handler.
3. Then read the state below and react to `DragEvent`.

| Variable | Type | Meaning after `DragMouse` |
|---|---|---|
| `DragEvent` | INTEGER | 1 a press, 2 a move with the button down, 3 the release; 0 after `DragCancel` until the next press |
| `DragOn` | BOOLEAN | TRUE from a press until its release |
| `DragX0`, `DragY0` | INTEGER | where the button went down |
| `DragX`, `DragY` | INTEGER | where the pointer is now, kept inside 0..DragW − 1, 0..DragH − 1 |
| `DragDX`, `DragDY` | INTEGER | `DragX − DragX0`, `DragY − DragY0` |
| `DragMoved` | BOOLEAN | TRUE once the pointer has gone `DragSlop` pixels or more from the press. A click is a press and release without it |
| `DragEnded` | BOOLEAN | TRUE on the release that ends a drag (not after `DragCancel`) |
| `DragSlop` | INTEGER | the click tolerance in pixels; 0 or less means the default, 2 |

## Procedures

| Name | Kind | Parameters | What it does |
|---|---|---|---|
| `DragMouse` | SUB | none | Reads `MOUSEEVENT`, `MOUSEX`, `MOUSEY` and updates the variables above. |
| `DragShowBox` | SUB | none | Shows the rectangle from the press to the pointer, erasing what was shown before. |
| `DragShowLine` | SUB | none | Shows a line from the press to the pointer. |
| `DragShowFrame` | SUB | `X, Y, W, H AS INTEGER` | Shows any outline, for example an object at the place it is being moved to. It is clipped to the canvas. |
| `DragHide` | SUB | none | Erases whatever is shown. |
| `DragCancel` | SUB | none | Erases the feedback and forgets the drag (for the Stop key or a tool change). The release that follows is ignored. |

The feedback procedures draw with `DRAW INK XOR` and leave the ink set to `BLACK`. `DragFbDraw` is internal.

Because the feedback is XOR, your program must not redraw the canvas under it while it is shown: call `DragHide` before drawing, then show it again.

## Names it defines

`DragW`, `DragH`, `DragEvent`, `DragOn`, `DragX0`, `DragY0`, `DragX`, `DragY`, `DragDX`, `DragDY`, `DragMoved`, `DragEnded`, `DragSlop`, and the internal `DragIgnore`, `DragFbKind`, `DragFbX`, `DragFbY`, `DragFbW`, `DragFbH`. Every name starts with `Drag`; do not declare your own.

## Memory cost

Measured in a minimal host with a 200 × 100 canvas:

| | bytes |
|---|---:|
| whole program, one 16K image | +1,757 |
| resident 16K block, procedures in code banks | +848 |
| of which variables | +56 |

About 700 bytes of the resident figure are runtime drawing and mouse routines that a canvas program normally has anyway ([memory.md](../memory.md)).

## Errors

- **Set `DragW` and `DragH`.** If they are left at 0, `DragX` and `DragY` become −1, and `DragShowLine` then stops the program with `Runtime error: drawing outside the canvas`. (`DragShowBox` and `DragShowFrame` clip, so they draw nothing instead.)
- Only the left mouse button exists; there is no double-click and no hover (see [menus, keys and mouse](../manual/11-menus-keys-mouse.md)).

## Example

Drag on the canvas to draw a box; a click without moving draws a dot.

```pbas
INCLUDE "lib/drag.pbas"
DIM Info$ AS STRING * 24
WINDOW "Rubber band", LARGE
LABEL Info$
CANVAS 400, 200, PAINT Paint, MOUSE Mouse
BUTTON "Quit", Quit
SUB Paint
    DRAW CLEAR
    DRAW BOX 0, 0, 400, 200
END SUB
SUB Mouse
    CALL DragMouse
    IF DragEvent = 2 AND DragMoved THEN
        CALL DragShowBox
    END IF
    IF DragEvent = 3 THEN
        CALL DragHide
        IF DragMoved THEN
            DRAW BOX MIN(DragX0, DragX), MIN(DragY0, DragY), ABS(DragDX) + 1, ABS(DragDY) + 1
            Info$ = "Box " + STR$(ABS(DragDX) + 1) + " x " + STR$(ABS(DragDY) + 1)
        ELSE
            DRAW FILL DragX, DragY, 1, 1, 0
            Info$ = "Click"
        END IF
    END IF
END SUB
SUB Quit
    EXIT
END SUB
DragW = 400
DragH = 200
Info$ = "Drag to draw a box"
END
```

## Used by

- `examples/designer.pbas` (moving objects with `DragShowFrame`, rubber-band selection)
- `examples/tutorial/t2_draw.pbas` ([Tutorial 2](../TUTORIAL-2-GRAPHICS.md))

## Limitations

- One drag at a time, from the left button.
- The feedback is a 1-pixel XOR outline; filled or patterned feedback is up to your program.
- Mouse events arrive only while the pointer is over the canvas and the window is on screen.

See also: [library index](README.md), [lib/handles.pbas](handles.md), [lib/scene.pbas](scene.md), [generated reference](../LIBRARY-REFERENCE.md).
