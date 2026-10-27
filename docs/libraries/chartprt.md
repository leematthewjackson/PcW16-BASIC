# lib/chartprt.pbas: the bar chart on a printed page

`lib/chartprt.pbas` prints the bar chart of [lib/chart.pbas](chart.md) on the open page: the scale, the bars, their values and the labels, laid out as `ChartBars` draws them on screen, in points instead of pixels.

**Evidence: experimental.** In XAnne the printed bars first came out merged into black blocks. The runtime's printed rectangles were corrected and the correction is checked on the project's model of Rosanne's printer driver, but **the owner's XAnne retest of printed charts is not yet recorded** (known issue KI-79, [limitations](../limitations.md)). Printed text and rules (`PAGE TEXT`, `PAGE LINE`) are tested in XAnne; this library's bars use `PAGE FILL`, which is not. Not yet tested on a real PcW16 or a real printer.

## Adding it

```text
INCLUDE "lib/chart.pbas"
INCLUDE "lib/chartprt.pbas"
```

**chartprt needs [lib/chart.pbas](chart.md)**: it prints chart's data (`ChartN`, `ChartV`, `ChartL$`) and uses `ChartNiceTop` and `ChartScale`. Without chart the build stops with `chartprt.pbas:25:18: undefined variable CHARTN`. Include chart first, as the header asks; the compiler also accepts the other order. Because chart draws on the canvas, the program also needs a CANVAS, even if it only prints.

## The procedure

| Name | Kind | Parameters | What it does |
|---|---|---|---|
| `ChartPrintBars` | SUB | `X, Y, W, H AS INTEGER` (points) | Prints the bar chart of the current chart data in the rectangle X, Y, W, H of the open page. |

Call it between `PAGE NEW` and `PAGE PRINT` (see [printing](../manual/15-printing.md)). The values and labels are printed in the page's current font; 8 or 10 points suit a chart. Labels too wide for their slot are shortened and end in `.`. The bars are solid black (`PAGE FILL`); the selected bar is not marked.

There is no printed line chart: a printed line is horizontal or vertical only, so the joined points of `ChartLines` cannot be printed.

## Names it defines

None of its own besides `ChartPrintBars`. It sets chart's `ChartTop` and `ChartDiv` as `ChartBars` does.

## Memory cost

Measured on top of a host that already includes chart:

| | bytes |
|---|---:|
| whole program, one 16K image | +5,191 |
| resident 16K block, procedures in code banks | +3,765 |
| of which variables | +104 |

Most of this is the runtime's printing code and its page workspace, which any program that prints needs. With `--runtime-banks all` the printing code (the PAGE section) moves to the runtime bank ([memory.md](../memory.md)).

## Errors

- Everything printed must lie inside the printable area (x 0..522, y 0..765 points); otherwise the program stops with `Runtime error: printing outside the page`. The scale's numbers go 6 points or more to the left of X + 40, and the values above the tallest bar need about 12 points above Y + 12, so leave a margin.
- Without an open page the program stops with `Runtime error: no page is open (PAGE NEW)`.
- `PAGE PRINT` reports problems (no printer set up, stopped by the user) in `IOERR` and does not stop the program.

## Example

```pbas
INCLUDE "lib/chart.pbas"
INCLUDE "lib/chartprt.pbas"
WINDOW "Sales", LARGE
CANVAS 320, 180, PAINT Paint
BUTTON "Print", PrintIt
BUTTON "Quit", Quit
SUB Paint
    CALL ChartBars(0, 0, 320, 180)
END SUB
SUB PrintIt
    PAGE NEW
    PAGE FONT 14, BOLD
    PAGE TEXT 0, 0, "Sales"
    PAGE FONT 8
    CALL ChartPrintBars(0, 40, 400, 240)
    PAGE PRINT
    IF IOERR <> 0 THEN
        MESSAGE "Not printed (" + STR$(IOERR) + ")"
    END IF
END SUB
SUB Quit
    EXIT
END SUB
ChartN = 4
ChartV(1) = 12
ChartL$(1) = "January"
ChartV(2) = 30
ChartL$(2) = "February"
ChartV(3) = 22
ChartL$(3) = "March"
ChartV(4) = 37
ChartL$(4) = "April"
END
```

## Used by

- `examples/reporter.pbas` (its printed report: a table and the bar chart)

## Limitations

- Bars only; no printed line chart.
- Experimental until printed bars are confirmed in XAnne (KI-79).
- One page at a time, A4 portrait, as for all printing.

See also: [library index](README.md), [lib/chart.pbas](chart.md), [printing](../manual/15-printing.md), [generated reference](../LIBRARY-REFERENCE.md).
