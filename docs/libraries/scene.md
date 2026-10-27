# lib/scene.pbas: objects in a stacking order

`lib/scene.pbas` keeps a list of up to 100 objects, each with a bounding rectangle, in a back-to-front stacking order. It finds the topmost object under a point, brings objects to the front or sends them to the back, removes them, and collects a *dirty area*: the rectangle that has to be redrawn after something changed. It does not draw: what an object looks like is up to your program.

**Evidence:** *Tested in XAnne* through DESIGNER (selecting, dragging, resizing, layering, deleting and duplicating objects). Not yet tested on a real PcW16.

## Adding it

```text
INCLUDE "lib/geom.pbas"
INCLUDE "lib/scene.pbas"
```

**scene needs [lib/geom.pbas](geom.md)**: `SceneDirty` calls `GeomUnite`. Without geom the build stops with `CALL GEOMUNITE: no SUB GEOMUNITE is defined`. Include geom first, as the library's header asks; the compiler also accepts the other order, because procedures and globals may be used before the line that defines them.

## The model

An object is a number 1..`SceneN`. Its rectangle is `SceneX(I)`, `SceneY(I)`, `SceneW(I)`, `SceneH(I)`: where it can be clicked and what it may cover. Everything else about an object (its kind, text, shade) lives in your own arrays, indexed by the same number.

`SceneOrder(1..SceneN)` is the stacking order, back to front. The object at `SceneOrder(SceneN)` is drawn last and is on top. To redraw, loop over `SceneOrder` from 1 to `SceneN`.

## Procedures and functions

All parameters are INTEGER.

| Name | Kind | Parameters | Result | What it does |
|---|---|---|---|---|
| `SceneAdd` | SUB | `X, Y, W, H` | `SceneNew` | Adds an object on top. `SceneNew` is its number, or 0 when the scene already holds 100. |
| `SceneRemove` | SUB | `I` | `SceneRemoved` | Removes object I. Objects with higher numbers move down one number; move your own arrays the same way. `SceneRemoved` is set to I. Does nothing when I is outside 1..SceneN. |
| `SceneAt` | FUNCTION | `X, Y` | INTEGER | The topmost object whose rectangle holds the pixel X, Y, or 0. |
| `SceneToFront` | SUB | `I` | | Moves object I to the top of the order. |
| `SceneToBack` | SUB | `I` | | Moves object I to the back. |
| `SceneDepth` | FUNCTION | `I` | INTEGER | Where object I is in the order (1 = back), or 0 if there is no such object. |
| `SceneDirty` | SUB | `X, Y, W, H` | `SceneDirtyX/Y/W/H` | Adds a rectangle to the dirty area. |
| `SceneClean` | SUB | | | Empties the dirty area (`SceneDirtyW` becomes 0). |

To redraw after a change: add the object's old and new rectangles with `SceneDirty`, redraw your background inside the dirty area, then draw every object, back to front, whose rectangle meets it (`GeomMeets`), and call `SceneClean`.

## Names it defines

| Name | Type |
|---|---|
| `SCENEMAX` | CONST = 100 |
| `SceneN`, `SceneNew`, `SceneRemoved` | INTEGER |
| `SceneX(100)`, `SceneY(100)`, `SceneW(100)`, `SceneH(100)`, `SceneOrder(100)` | INTEGER arrays |
| `SceneDirtyX`, `SceneDirtyY`, `SceneDirtyW`, `SceneDirtyH` | INTEGER |

Every name starts with `Scene` (or is `SCENEMAX`). Your program must not declare any of them.

## Memory cost

Measured on top of a host that already includes geom:

| | bytes |
|---|---:|
| whole program, one 16K image | +2,921 |
| resident 16K block, procedures in code banks | +1,275 |
| of which the five arrays | +1,030 |

The five 100-element arrays are ordinary arrays, so they always live in the resident 16K block: 1,000 bytes that no build option can move. This is a large part of why DESIGNER has so little room left ([memory.md](../memory.md)).

## Errors

- `SceneAdd` on a full scene does not fail: it sets `SceneNew` to 0. Check it.
- Indexing the arrays yourself with a number outside 1..100 stops the program with `Runtime error: index out of range`.
- `SceneAt` uses the rectangle only, so a round or irregular object is found anywhere in its bounding box.

## Example

```pbas
' Three overlapping boxes; the dark one is brought to the front.
INCLUDE "lib/geom.pbas"
INCLUDE "lib/scene.pbas"
DIM Shade(100) AS INTEGER
CALL SceneAdd(20, 20, 80, 50)
Shade(SceneNew) = 6
CALL SceneAdd(60, 40, 80, 50)
Shade(SceneNew) = 4
CALL SceneAdd(100, 10, 60, 60)
Shade(SceneNew) = 1
MESSAGE "top at 70,45: " + STR$(SceneAt(70, 45))
CALL SceneToFront(1)
MESSAGE "after ToFront: " + STR$(SceneAt(70, 45))
MESSAGE "depth of 1: " + STR$(SceneDepth(1))
WINDOW "Scene"
CANVAS 200, 100, PAINT Paint
BUTTON "Quit", Quit
SUB Paint
    LOCAL K AS INTEGER
    LOCAL I AS INTEGER
    DRAW CLEAR
    FOR K = 1 TO SceneN
        I = SceneOrder(K)
        DRAW FILL SceneX(I), SceneY(I), SceneW(I), SceneH(I), Shade(I)
        DRAW BOX SceneX(I), SceneY(I), SceneW(I), SceneH(I)
    NEXT K
END SUB
SUB Quit
    EXIT
END SUB
END
' expect-message: top at 70,45: 2
' expect-message: after ToFront: 1
' expect-message: depth of 1: 3
```

## Used by

- `examples/designer.pbas`

## Limitations

- At most 100 objects (`SCENEMAX`). The limit is fixed in the library's source; raising it costs 10 bytes of the resident block per object.
- Hit testing is by bounding rectangle only.
- `SceneRemove` renumbers objects; your program must shift its own arrays to match, using `SceneRemoved`.

See also: [library index](README.md), [lib/geom.pbas](geom.md), [lib/drag.pbas](drag.md), [lib/handles.pbas](handles.md), [generated reference](../LIBRARY-REFERENCE.md).
