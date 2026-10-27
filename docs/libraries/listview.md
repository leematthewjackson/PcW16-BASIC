# lib/listview.pbas: a list of rows on a canvas

`lib/listview.pbas` draws a scrolling list of rows with up to 8 columns on a CANVAS, and lets the user choose a row with the cursor keys or the mouse. The chosen row is shown inverted. Your program supplies the text of each cell through a function, so the rows can come from anywhere: an ordinary array, a BANKED array or a database.

Use it instead of the `LIST` control when you need columns, more than 12 visible rows, keyboard movement, rows from a BANKED array, or a list that is not rebuilt after every handler.

**Evidence:** *Tested in XAnne* through CONTACTS IV and STARTER. Not yet tested on a real PcW16.

## Adding it

```text
INCLUDE "lib/listview.pbas"
```

The program must have a CANVAS (the library uses `KEYCODE`, `MOUSEY`, `DRAW` and `TEXTWIDTH`; without one the build stops with `undefined variable KEYCODE`), and **must define two procedures that the library calls**:

| Your procedure | Called | Must |
|---|---|---|
| `FUNCTION ListCell$(I AS INTEGER, K AS INTEGER) AS STRING` | for every cell drawn | return the text of row I (1..ListCount), column K (1..ListCols) |
| `SUB ListPicked` | after the chosen row changed | react (show details, update a label); it may do nothing |

Without them the build stops with `unknown function LISTCELL$` or `CALL LISTPICKED: no SUB LISTPICKED is defined`. They may come anywhere in the program.

The library needs no other library.

## Settings (your program sets them)

| Name | Type | Meaning |
|---|---|---|
| `ListCount` | INTEGER | rows in the list, 0 or more |
| `ListRows` | INTEGER | rows shown; each row is 16 pixels (`LIST_H`), so the canvas should be `16 × ListRows` high |
| `ListWidth` | INTEGER | the canvas width |
| `ListCols` | INTEGER | columns, 1..8 (0 means 1) |
| `ListX(1..8)` | INTEGER | x where each column starts; `ListX(1)` is 2 when left at 0 |
| `ListSel` | INTEGER | the chosen row (0 only when the list is empty) |
| `ListTop` | INTEGER | the first row shown |

Column K runs from `ListX(K)` to 4 pixels before `ListX(K + 1)`; the last column runs to 2 pixels before the edge. Text too long for its column is cut at a whole character (measured with `TEXTWIDTH`), so it never runs into the next column. Rows are drawn in the dialog font with normal spacing.

Set these before the canvas is first painted (in the main line), and again whenever the rows change, then call `ListPaint`.

## Procedures and functions

| Name | Kind | Parameters | Result | What it does |
|---|---|---|---|---|
| `ListPaint` | SUB | none | | Draws the visible rows. Call it from the canvas's PAINT handler and after changing the rows. |
| `ListKey` | FUNCTION | none | BOOLEAN | Call it from the KEYS handler. Up, Down, PgUp, PgDn, Home and End move the choice; it returns TRUE when it used the key and FALSE for any other key, which is then yours to handle. |
| `ListMouse` | SUB | none | | Call it from the MOUSE handler. A press or a drag over a row chooses it. |
| `ListMoveTo` | SUB | `I AS INTEGER` | | Chooses row I (kept within the list), redraws what changed and calls `ListPicked` if the choice changed. |
| `ListFit$` | FUNCTION | `S$ AS STRING, W AS INTEGER` | STRING | S$ cut at a whole character to at most W pixels wide. |
| `ListClamp` | SUB | none | | Puts `ListSel` back within 1..`ListCount` (0 when the list is empty) and moves `ListTop` so the chosen row is on the page and the last page is full where it can be. Call it after you change `ListCount`, `ListSel` or `ListTop` yourself, for example after deleting or filtering rows. It does not redraw and does not call `ListPicked`: call `ListPaint` afterwards (or let PAINT run). `examples/contacts4.pbas` calls it after rebuilding its view. |

`ListDrawRow` is internal. A key or a click redraws only the two rows that change, unless the list scrolls.

## Names it defines

`LIST_H` (CONST = 16), `ListCount`, `ListRows`, `ListWidth`, `ListSel`, `ListTop`, `ListCols`, `ListX(8)`, and the procedures above. Every name starts with `List`; `ListCell$` and `ListPicked` are the two you provide. Do not declare other names starting with `List`.

## Memory cost

Measured in a minimal host with a canvas and empty `ListCell$` and `ListPicked`:

| | bytes |
|---|---:|
| whole program, one 16K image | +3,356 |
| resident 16K block, procedures in code banks | +1,110 |
| of which variables and arrays | +395 |

`ListCell$` and `ListFit$` are STRING functions, so their results and their call sites take string cells; keep `ListCell$` short and let it read from your own arrays ([memory.md](../memory.md)).

## Errors

- `ListCols` above 8 is treated as 8; a `ListX` value past the canvas edge leaves that column empty.
- A canvas shorter than `16 × ListRows` makes `ListPaint` draw outside it, and the program stops with `drawing outside the canvas`.
- `ListSel` is 0 when the list is empty. If your list can become empty, check `ListSel > 0` in `ListPicked` before indexing your arrays with it, or the program stops with `index out of range`.
- `ListCell$` must return a string that fits the program's string capacity; a "string too long" there stops the program.

## Example

```pbas
INCLUDE "lib/listview.pbas"
DIM Names$(5) AS STRING * 20
DIM Phones$(5) AS STRING * 16
DIM Picked$ AS STRING * 24
WINDOW "Phone list"
LABEL Picked$
CANVAS 300, 96, PAINT Paint, KEYS Keys, MOUSE Mouse
BUTTON "Quit", Quit
FUNCTION ListCell$(I AS INTEGER, K AS INTEGER) AS STRING
    IF K = 1 THEN
        RETURN Names$(I)
    END IF
    RETURN Phones$(I)
END FUNCTION
SUB ListPicked
    Picked$ = Names$(ListSel)
END SUB
SUB Paint
    CALL ListPaint
END SUB
SUB Keys
    IF NOT ListKey() THEN
        BEEP
    END IF
END SUB
SUB Mouse
    CALL ListMouse
END SUB
SUB Quit
    EXIT
END SUB
Names$(1) = "Ann Archer"
Phones$(1) = "01632 960001"
Names$(2) = "Bob Baker"
Phones$(2) = "01632 960002"
Names$(3) = "Cath Carter"
Phones$(3) = "01632 960003"
Names$(4) = "Dev Dyer"
Phones$(4) = "01632 960004"
Names$(5) = "Eve Evans"
Phones$(5) = "01632 960005"
ListCount = 5
ListRows = 6
ListWidth = 300
ListCols = 2
ListX(1) = 2
ListX(2) = 170
ListSel = 1
Picked$ = Names$(1)
MESSAGE "[" + ListFit$("Cath Carter, Leeds", 80) + "]"
END
' expect-message: [Cath Carter, ]
```

The alert shows how much of the text fits 80 pixels. The result above is from the simulator's model of the dialog font; the exact cut on a PcW16 depends on Rosanne's real character widths.

## Used by

- `examples/contacts4.pbas` (the contact list, with [app](app.md) and [forms](forms.md))
- `examples/starter.pbas` (a to-do list, with [app](app.md))

## Limitations

- One list per program: the library's state is global, and a program has one CANVAS.
- Single selection only; there is no multiple selection and no double-click (the mouse reports no double-clicks).
- No scroll bar: the list scrolls only with the keys (Up, Down, PgUp, PgDn, Home, End) or when your program calls `ListMoveTo`. The mouse chooses among the rows shown.

See also: [library index](README.md), [windows and controls](../manual/10-windows-and-controls.md) (the `LIST` control), [menus, keys and mouse](../manual/11-menus-keys-mouse.md), [generated reference](../LIBRARY-REFERENCE.md).
