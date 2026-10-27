# lib/handles.pbas: selection handles and resizing

`lib/handles.pbas` draws the eight small squares that mark a selected rectangle, tells you which handle is under the pointer, and works out the new rectangle when a handle is dragged. Together with [lib/drag.pbas](drag.md) and [lib/scene.pbas](scene.md) it gives you the select-move-resize behaviour of a drawing or design program.

**Evidence:** *Tested in XAnne* through DESIGNER (selecting and resizing objects). Not yet tested on a real PcW16.

## Adding it

```text
INCLUDE "lib/handles.pbas"
```

The program must have a CANVAS (the handles are drawn with `DRAW INVERT`). It needs no other library.

## The handles

Handles are numbered clockwise from the top-left corner:

```text
1 --- 2 --- 3
8           4
7 --- 6 --- 5
```

Each is a square of `HandleSize` pixels (default 5) centred on a corner or on the middle of a side. Handles are drawn inverted, so drawing them twice erases them, and they are clipped to the canvas.

Set `HandleCW` and `HandleCH` to the canvas's width and height once, before showing any handles.

## Procedures and functions

All parameters are INTEGER.

| Name | Kind | Parameters | Result | What it does |
|---|---|---|---|---|
| `HandlesShow` | SUB | `X, Y, W, H` | | Erases the handles shown before (if any) and shows those of X, Y, W, H. |
| `HandlesHide` | SUB | | | Erases the handles shown. |
| `HandleOn` | FUNCTION | none | BOOLEAN | TRUE while handles are shown. **Call it as `HandleOn()`**: the library declares it without brackets, but a call needs them (`IF HandleOn THEN` stops the build with `HANDLEON is a FUNCTION: call it as HANDLEON() …`). |
| `HandleAt` | FUNCTION | `MX, MY, X, Y, W, H` | INTEGER | The handle of X, Y, W, H under the pixel MX, MY: 1..8, or 0. A pixel inside the rectangle but on no handle gives 0. |
| `HandleResize` | SUB | `K, DX, DY, X, Y, W, H, MinW, MinH` | `HandX`, `HandY`, `HandW`, `HandH` | The rectangle X, Y, W, H after handle K has moved by DX, DY. The sides handle K does not touch stay where they are, and the result is never smaller than MinW × MinH. |

`HandlePos`, `HandleFlip` and `HandlesFlipAll` are internal.

A typical resize: on a press, `K = HandleAt(DragX, DragY, ...)`; while dragging, `CALL HandleResize(K, DragDX, DragDY, ...)` and show the result with `DragShowFrame(HandX, HandY, HandW, HandH)`; on the release, store HandX..HandH as the object's new rectangle.

Because the handles are inverted pixels, hide them (`HandlesHide`) before you redraw the area under them, and show them again afterwards.

## Names it defines

| Name | Type | Use |
|---|---|---|
| `HandleSize` | INTEGER | handle size in pixels (0 means 5) |
| `HandleCW`, `HandleCH` | INTEGER | the canvas size; your program sets them |
| `HandX`, `HandY`, `HandW`, `HandH` | INTEGER | results of `HandleResize` |
| `HandleShown`, `HandleSX`, `HandleSY`, `HandleSW`, `HandleSH`, `HandlePX`, `HandlePY` | | internal |

Names start with `Handle` or `Hand`. Do not declare your own with these prefixes.

## Memory cost

Measured in a minimal host with a 200 × 100 canvas:

| | bytes |
|---|---:|
| whole program, one 16K image | +2,905 |
| resident 16K block, procedures in code banks | +531 |
| of which variables | +126 |

## Errors

- If `HandleCW` and `HandleCH` are left at 0, every handle is clipped away and nothing is drawn. Nothing stops.
- `HandleOn` without brackets is refused:

```pbas-error
INCLUDE "lib/handles.pbas"
WINDOW "Handles"
CANVAS 200, 100
BUTTON "Quit", Quit
SUB Quit
    IF HandleOn THEN
        CALL HandlesHide
    END IF
    EXIT
END SUB
END
' expect-error: HANDLEON is a FUNCTION: call it as HANDLEON()
```

- Handles drawn over something your program later redraws are left inverted: the next `HandlesShow` or `HandlesHide` then inverts the wrong pixels. Always hide before redrawing.

## Example

```pbas
INCLUDE "lib/handles.pbas"
MESSAGE "handle at 10,10: " + STR$(HandleAt(10, 10, 10, 10, 50, 30))
MESSAGE "handle at 35,25: " + STR$(HandleAt(35, 25, 10, 10, 50, 30))
CALL HandleResize(5, 20, 10, 10, 10, 50, 30, 8, 8)
MESSAGE "after dragging 5: " + STR$(HandW) + " x " + STR$(HandH)
CALL HandleResize(1, 100, 0, 10, 10, 50, 30, 8, 8)
MESSAGE "never below 8: x " + STR$(HandX) + ", w " + STR$(HandW)
WINDOW "Handles"
CANVAS 200, 100, PAINT Paint
BUTTON "Quit", Quit
SUB Paint
    DRAW CLEAR
    DRAW FILL 40, 30, 80, 40, 6
    DRAW BOX 40, 30, 80, 40
    CALL HandlesShow(40, 30, 80, 40)
END SUB
SUB Quit
    EXIT
END SUB
HandleCW = 200
HandleCH = 100
END
' expect-message: handle at 10,10: 1
' expect-message: handle at 35,25: 0
' expect-message: after dragging 5: 70 x 40
' expect-message: never below 8: x 52, w 8
```

## Used by

- `examples/designer.pbas`

## Limitations

- One rectangle's handles at a time.
- Handles are axis-aligned squares; there is no rotation handle.

See also: [library index](README.md), [lib/drag.pbas](drag.md), [lib/scene.pbas](scene.md), [generated reference](../LIBRARY-REFERENCE.md).
