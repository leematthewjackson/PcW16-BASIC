# 15. Printing

A program prints one A4 page at a time: it opens a page with `PAGE NEW`, places text, lines,
boxes and filled rectangles on it in points, and sends it with `PAGE PRINT`. The page goes to
the printer chosen in the PcW16's Setup, through Rosanne's own print system, at that printer's
resolution.

Evidence levels: *Tested in XAnne* (the owner printed from XAnne, Rosanne 1.12, capturing the
printer output on a PC), *Simulator only* (the project's model of Rosanne's print calls),
*Untested*. **Nothing has been printed on a real PcW16 and printer.**

| Statement | Status |
|---|---|
| `PAGE NEW`, `PAGE FONT`, `PAGE TEXT`, `PAGEWIDTH`, `PAGE PRINT`, `PAGE CLOSE` | tested in XAnne (`printdemo.pbas` Letter) |
| `PAGE LINE`, `PAGE BOX` | tested in XAnne (`printdemo.pbas` Table rules and borders) |
| `PAGE FILL` (and so printed bar charts) | **experimental**: printed bars merged into one black area in XAnne; the runtime was corrected, and the correction is checked on the simulator, but **it has not yet been retested in XAnne** (known issue KI-79, [limitations](../limitations.md)) |

Contents: [PAGE NEW and PAGE CLOSE](#page-new-and-page-close) · [Coordinates](#coordinates) ·
[PAGE FONT](#page-font) · [PAGE TEXT and PAGEWIDTH](#page-text-and-pagewidth) ·
[PAGE LINE](#page-line) · [PAGE BOX](#page-box) · [PAGE FILL](#page-fill-experimental) ·
[PAGE PRINT and IOERR](#page-print-and-ioerr) · [Printed charts](#printed-charts) ·
[What cannot be printed](#what-cannot-be-printed)

## PAGE NEW and PAGE CLOSE

```text
PAGE NEW
PAGE CLOSE
```

`PAGE NEW` starts an empty A4 portrait page with half-inch margins, in 10-point plain text. A
page still open is discarded first. `PAGE CLOSE` discards the page without printing (nothing
happens if no page is open). A page still open when the program ends is discarded.

Every other `PAGE` statement, and `PAGEWIDTH`, needs an open page:

```pbas
' expect-message: Runtime error: no page is open (PAGE NEW) at line 3
' PAGE NEW was forgotten:
PAGE TEXT 0, 0, "Hello"
END
```

`PAGE` is a statement word only when one of these operations follows it, so you may still use
`Page` as a variable name.

## Coordinates

Positions are whole points (1/72 inch) from the top-left corner of the printable area: x from 0
to 522, y from 0 to 765. Everything printed must lie inside that area, a line of text with its
whole height and width; nothing is clipped or cut. Otherwise the program stops:

```pbas
' expect-message: Runtime error: printing outside the page at line 3
PAGE NEW
PAGE TEXT 500, 0, "Too far right"
END
```

## PAGE FONT

**Syntax**

```text
PAGE FONT size
PAGE FONT size, BOLD
```

**Meaning.** The text that follows prints in Rosanne's Times typeface (or the first typeface
there is, if there is no Times) at `size` points, plain or bold. The sizes are 6, 8, 10, 11, 12,
14, 18, 24, 36 and 72.

**Common errors.** A literal size outside the list is refused when you build; a size held in a
variable is checked when the statement runs:

```pbas-error
' expect-error: a print size is 6, 8, 10, 11, 12, 14, 18, 24, 36 or 72
PAGE NEW
PAGE FONT 9
END
```

```pbas
' expect-message: Runtime error: a print size is 6, 8, 10, 11, 12, 14, 18, 24, 36 or 72 at line 6
DIM S AS INTEGER
S = 9
PAGE NEW
' a variable size is checked here:
PAGE FONT S
END
```

**Limits.** One typeface; no italic; no other sizes.

## PAGE TEXT and PAGEWIDTH

**Syntax**

```text
PAGE TEXT x, y, text$
PAGEWIDTH(text$)         INTEGER: the printed width in points in the current font, rounded up
```

**Meaning.** `PAGE TEXT` prints the text with the top of its line at x, y. Characters outside
codes 32 to 255 print as `?`. `PAGEWIDTH` measures text in the current font, for wrapping,
centring and right-aligning; widths of parts add up to within a point a part.

**Example** (this prints a page, so it needs no window; on the simulator the page is modelled,
and the two alerts report the width and Rosanne's answer):

```pbas
' expect-message: Title is 43 points wide
' expect-message: Printed, IOERR 0
CONST RIGHT = 522

DIM W AS INTEGER

PAGE NEW
PAGE FONT 18, BOLD
PAGE TEXT 0, 0, "Title"
W = PAGEWIDTH("Title")
MESSAGE "Title is " + STR$(W) + " points wide"
PAGE LINE 0, 26, RIGHT, 26, 2
PAGE FONT 10
PAGE TEXT 0, 40, "Left"
PAGE TEXT RIGHT - PAGEWIDTH("Right"), 40, "Right"
PAGE BOX 0, 60, 200, 40
PAGE PRINT
IF IOERR = 0 THEN
    MESSAGE "Printed, IOERR 0"
ELSE
    MESSAGE "Not printed, IOERR " + STR$(IOERR)
END IF
END
```

The width the simulator reports comes from its own model of the font; Rosanne's real Times
font gives its own value.

```pbas-error
' expect-error: PAGEWIDTH expects a STRING
DIM A AS INTEGER
PAGE NEW
A = PAGEWIDTH(3)
END
```

*Evidence:* tested in XAnne (`printdemo.pbas` Letter: heading, wrapped paragraphs and a
right-aligned sign-off, all placed correctly).

## PAGE LINE

**Syntax**

```text
PAGE LINE x1, y1, x2, y2
PAGE LINE x1, y1, x2, y2, thickness
```

**Meaning.** A horizontal or vertical line, `thickness` points thick (1 by default, 1 to 72),
drawn below or to the right of the two points. A line of no length prints nothing. Sloped lines
cannot be printed:

```pbas
' expect-message: Runtime error: a printed line is horizontal or vertical at line 3
PAGE NEW
PAGE LINE 0, 0, 100, 100
END
```

Each line prints as exactly its rectangle, to within one printer dot. (Rosanne 1.12's printer
driver lengthens horizontal lines and shortens vertical ones; the runtime allows for both.)

*Evidence:* tested in XAnne (`printdemo.pbas` Table: "clean borders").

## PAGE BOX

```text
PAGE BOX x, y, w, h
```

The outline of a rectangle, one point thick, inside the rectangle. *Tested in XAnne.*

## PAGE FILL (experimental)

```text
PAGE FILL x, y, w, h
```

A solid black rectangle; w or h 0 prints nothing. There are no grey fills on paper.

**Status: experimental.** In the owner's XAnne print test, printed bar charts came out as one
merged black area: each fill was printed `h` points too wide. The runtime has been corrected,
and the simulator's model of the printer shows the corrected geometry, but **the owner has not
yet retested printing in XAnne** (known issue KI-79). Do not rely on `PAGE FILL`, or on printed
bar charts, until that retest is recorded. Text, lines and boxes are not affected.

## PAGE PRINT and IOERR

```text
PAGE PRINT
```

Sends the page to the printer and closes it. `PAGE NEW`, `FONT`, `TEXT`, `LINE`, `BOX`, `FILL`
and `PRINT` set `IOERR` to Rosanne's answer (0 = done) and never stop the program for it:

| Statement | IOERR |
|---|---|
| `PAGE NEW` | 7 not enough memory; 2 no typeface |
| `PAGE FONT` | 1 typeface missing; 2 size refused; 7 not enough memory |
| `PAGE PRINT` | 1 not enough memory to print; 2 font not found; 3 too many fonts; 4 stopped by the user; 5 printer in use; 6 no valid printer set up |

Check `IOERR` after `PAGE PRINT` and tell the user, as the example above does.
`../../examples/printdemo.pbas` turns every code into a sentence.

**Printing in XAnne.** XAnne's printer output can be captured on the PC and converted to PDF;
that is how the owner checked the pages. See [Running in XAnne](../running-in-xanne.md).

## Printed charts

`lib/chartprt.pbas` prints the bar chart of `lib/chart.pbas` on an open page
(`ChartPrintBars(X, Y, W, H)`, in points). Its bars are `PAGE FILL`, so it is **experimental**
for the reason above. Line charts cannot be printed (sloped lines). See
[libraries](../libraries/README.md).

*Evidence:* the screen charts of `reporter.pbas` are tested in XAnne; its printed chart, and
`printdemo.pbas`'s Chart page, failed before the correction and are not yet retested.

## What cannot be printed

Rosanne 1.12's print system has characters and horizontal and vertical lines only, and its
print-screen and picture calls do nothing. So there is **no print screen**, and no printing of
the canvas, BITMAPs, sloped lines or pictures (known issue KI-74). Also not available: other
paper sizes, landscape, typefaces by name, italic, several pages open at once, and a preview on
screen. Print a document of several pages one `PAGE NEW … PAGE PRINT` at a time.

**See also.** `../../examples/printdemo.pbas` (letter, table and chart),
`../../examples/reporter.pbas`, `../../examples/designer.pbas` (prints a design's text, boxes and
fills); spec [§5.13](../../LANGUAGE-SPEC.md#513-m12--printing-page).

Next: [16. Building and commands](16-building-and-commands.md).
