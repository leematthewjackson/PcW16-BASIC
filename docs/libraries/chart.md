# lib/chart.pbas: bar and line charts on the canvas

`lib/chart.pbas` draws a bar chart or a line chart of up to 12 values inside a rectangle of the canvas: a scale on the left from 0 to a round number, the bars or the joined points, the value above each bar, and a label under each slot.

**Evidence:** *Tested in XAnne* on screen through REPORTER (the owner: separate bars, distinct grey patterns, readable values, correct scaling). Printing the chart is a separate library, [lib/chartprt.pbas](chartprt.md), and is **not** yet confirmed in XAnne. Not yet tested on a real PcW16.

## Adding it

```text
INCLUDE "lib/chart.pbas"
```

The program must have a CANVAS (without one, the build stops with `chart.pbas:73:5: DRAW needs a CANVAS declaration`). It needs no other library. The library uses REAL arithmetic for exact scaling, so it brings part of the REAL library into the program.

## Data

Set `ChartN` (0..12), the values `ChartV(1..ChartN)` (0 to 20000) and the labels `ChartL$(1..ChartN)` (up to 12 characters), then call `ChartBars` or `ChartLines`. `ChartSelected` (0 for none) is the slot drawn darker (a bar in shade 1 instead of 4, a larger dot).

## Procedures and functions

All parameters are INTEGER.

| Name | Kind | Parameters | Result | What it does |
|---|---|---|---|---|
| `ChartBars` | SUB | `X, Y, W, H` | | Clears the rectangle and draws a bar chart in it, with the value above each bar when there is room. |
| `ChartLines` | SUB | `X, Y, W, H` | | Clears the rectangle and draws the values joined by lines, with a dot at each. |
| `ChartNiceTop` | FUNCTION | `Max` | INTEGER | The top of the scale for a largest value `Max`: 1, 2 or 5 times a power of ten, at least `Max`, at most 20000. |
| `ChartScale` | FUNCTION | `V, Size` | INTEGER | V as a length of `Size` pixels on the current scale (`ChartTop`), rounded to the nearest. |

`ChartFrame` and `ChartLabel` are internal.

The rectangle should be at least 120 pixels wide and 80 high. Inside it, the plot area starts 46 pixels from the left (the scale's numbers go there) and leaves 22 pixels at the bottom for the labels. A label too wide for its slot is shortened and ends in `.`; show the full label elsewhere, for example in a table.

## Names it defines

| Name | Type | Use |
|---|---|---|
| `CHARTMAX` | CONST = 12 | |
| `ChartV(12)` | INTEGER array | the values |
| `ChartL$(12)` | STRING * 12 array | the labels |
| `ChartN`, `ChartSelected` | INTEGER | set by your program |
| `ChartTop`, `ChartDiv` | INTEGER | the scale of the last chart drawn |
| `ChartPX`, `ChartPY`, `ChartPW`, `ChartPH`, `ChartSlot` | INTEGER | the plot area and slot width of the last chart drawn (use them to find which bar was clicked) |

Every name starts with `Chart` (or is `CHARTMAX`); do not declare your own.

## Memory cost

Measured in a minimal host with a canvas:

| | bytes |
|---|---:|
| whole program, one 16K image | +5,429 |
| resident 16K block, procedures in code banks | +2,634 |
| of which variables and arrays | +485 |
| of which the REAL library | +907 |

The REAL library stays in the resident block even with `--runtime-banks all`; in a large program that is the biggest cost of this library ([memory.md](../memory.md)).

## Errors

- `ChartN` above 12 stops the program with `Runtime error: index out of range`.
- Values above 20000 or below 0 are not supported: the scale stops at 20000, and a taller bar is drawn outside the rectangle, which can stop the program with `drawing outside the canvas`.
- `ChartScale` divides by `ChartTop`, which is 0 until a chart has been drawn; called then, it stops the program with `Runtime error: division by zero` (checked on the simulator). Call it only after `ChartBars` or `ChartLines`, or set `ChartTop = ChartNiceTop(...)` yourself first.
- The rectangle must lie inside the canvas, and drawing needs the canvas on screen (call it from PAINT or another handler).

## Example

```pbas
INCLUDE "lib/chart.pbas"
WINDOW "Chart", LARGE
CANVAS 320, 180, PAINT Paint
BUTTON "Quit", Quit
SUB Paint
    CALL ChartBars(0, 0, 320, 180)
END SUB
SUB Quit
    EXIT
END SUB
ChartN = 4
ChartV(1) = 12
ChartL$(1) = "Jan"
ChartV(2) = 30
ChartL$(2) = "Feb"
ChartV(3) = 22
ChartL$(3) = "Mar"
ChartV(4) = 37
ChartL$(4) = "Apr"
ChartSelected = 4
MESSAGE "scale to " + STR$(ChartNiceTop(37))
END
' expect-message: scale to 50
```

Change `ChartBars` to `ChartLines` for a line chart of the same data.

## Used by

- `examples/reporter.pbas` (a table with a bar or line chart of its figures)

## Limitations

- At most 12 values, all 0..20000, INTEGER only.
- One series per chart; no legend, no negative values, no stacked bars.
- The scale is always from 0.

See also: [library index](README.md), [lib/chartprt.pbas](chartprt.md), [drawing](../manual/12-drawing.md), [generated reference](../LIBRARY-REFERENCE.md).
