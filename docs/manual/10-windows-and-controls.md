# 10. Windows and controls

A PcW16 BASIC program can show one window at a time on the Rosanne desktop, with labels,
fields, tick boxes, option groups, number fields, lists, drop-down choices, sliders and
buttons laid out by the compiler. This chapter describes every control the compiler accepts,
the rules for laying them out, and the order in which values move between your variables and
the screen.

Evidence levels used below: *Tested in XAnne* (the owner ran a program using it in the XAnne
emulator with Rosanne 1.12), *Simulator only* (checked on the project's Z80/Rosanne model,
`tests/z80sim.py`), *Untested*. Nothing has yet been tested on a real PcW16.

Contents:
[How a windowed program runs](#how-a-windowed-program-runs) ·
[WINDOW](#window) · [Named windows and SHOW](#named-windows-and-show) ·
[Layout](#layout-rows-and-limits) · [BUTTON](#button) · [LABEL](#label) ·
[TEXTBOX](#textbox) · [CHECKBOX](#checkbox) · [RADIO](#radio) ·
[NUMBERBOX and its spinner](#numberbox-and-its-spinner) · [LIST](#list) ·
[CHOICE](#choice) · [SLIDER](#slider) · [FOCUS](#focus) ·
[MESSAGE, ASK and BEEP](#message-ask-and-beep) · [Closing a program](#closing-a-program) ·
[What is not available](#what-is-not-available)

## How a windowed program runs

1. The main line (every statement outside a `SUB` or `FUNCTION`) runs first, once, in
   order. A `MESSAGE` in the main line appears on the desktop before the window.
2. `END` ends the main line. In a program with a `WINDOW`, the program does not stop there:
   the window opens, showing every control with its variable's current value.
3. The program then waits. A click on a button (or a menu choice, a key given to a button, a
   timer event, a change in a list) runs that event's handler, a `SUB` without parameters,
   to completion. Then the program waits again.
4. The program ends when some code runs `EXIT`, or when Rosanne tells it to close. A runtime
   error also ends it, after an alert that names the line.

Values move between variables and controls **only** at these moments:

| When | Direction | What happens |
|---|---|---|
| The window opens | variable → control | every control shows its variable |
| The user types, ticks or clicks an option | none | Rosanne changes the control; no BASIC code runs; variables do not change yet |
| An event's handler is about to run | control → variable | every bound variable receives its control's value |
| The handler returns | variable → control | every control whose variable changed is redrawn |
| `EXIT`, Rosanne closes the program, runtime error | none | edits since the last handler are discarded |

So a handler always sees what was on screen when the event happened, and nothing a handler
does to a variable appears until the handler returns. A dynamic label keeps showing its old
value while the handler runs, even during a `MESSAGE` the handler shows.

`CALL` does not move values. Controls are read before the handler starts and redrawn after
it returns, whatever it calls.

Controls that bind a variable (`TEXTBOX`, `CHECKBOX`, dynamic `LABEL`, `RADIO`, `NUMBERBOX`,
`LIST`, `CHOICE`, `SLIDER`, a menu `TICK`) declare that variable if no `DIM` did. The types
must agree. In one window, a variable may be bound to only one control.

*Evidence:* tested in XAnne (examples `tally.pbas`, `details.pbas`, `prefs.pbas`,
`editor.pbas`, `visitor_counter.pbas`). Spec: [§5](../../LANGUAGE-SPEC.md#5-program-structure-and-execution-model).

## WINDOW

**Syntax**

```text
WINDOW "title"
WINDOW "title", LARGE
```

**Meaning.** Declares the program's window. Every control that follows belongs to it.
A normal window is 360 × 240 pixels at screen position 140, 110; a `LARGE` one is
600 × 400 at 20, 50 (below the menu bar). The window opens when the main line reaches `END`.

**Requires.** At least one `BUTTON`. `WINDOW` is a top-level statement (not inside a `SUB`).

**Example**

```pbas
WINDOW "Hello"
LABEL "Hello from PcW16 BASIC"
BUTTON "Quit", Quit

SUB Quit
    EXIT
END SUB
END
```

A program without `WINDOW` ends at `END`; it can still show `MESSAGE` alerts. This program
shows one alert and ends:

```pbas
' expect-message: No window: this program ends after the alert
MESSAGE "No window: this program ends after the alert"
END
```

**Common errors**

A window with no button is refused by the build (it would have no proven way to close):

```pbas-error
' expect-error: a WINDOW needs at least one BUTTON
WINDOW "Nothing to press"
LABEL "No buttons here"
END
```

```pbas-error
' expect-error: WINDOW title is 36 characters; the maximum is 35
WINDOW "A title that is far too long for Ros"
BUTTON "Quit", Quit
SUB Quit
    EXIT
END SUB
END
```

```pbas-error
' expect-error: WINDOW is only allowed at the top level
SUB Later
    WINDOW "Inside"
END SUB
BUTTON "Quit", Later
END
```

**Limits.** Title at most 35 characters. One unnamed window per program, or 2 to 8 named
ones (next section). A window's position and size are fixed: the two sizes above only.

**Note on `check`.** `pcw16basic check` reports the missing-button error above, a seventh
button, a layout overflow, a CANVAS too wide for its window and a TEXTBOX string that is too
long, as `build` does. (Up to M13 only `build` reported them.) Only `build` checks that the
program fits the PcW16's memory, so always build before you copy a program
([chapter 16](16-building-and-commands.md#pcw16basic-check)).

**See also.** `../../examples/tally.pbas`, `../../examples/greeter.pbas`;
spec [§5](../../LANGUAGE-SPEC.md#5-program-structure-and-execution-model) and
[§6](../../LANGUAGE-SPEC.md#6-statements).

## Named windows and SHOW

**Syntax**

```text
WINDOW Name, "title" [, LARGE]
SHOW Name
```

**Meaning.** A program may declare 2 to 8 named windows. Each has its own controls and its
own layout, and each needs at least one button. Only one is on screen at a time. In the main
line, `SHOW Name` chooses which window opens first (otherwise the first one declared). In a
handler, `SHOW Name` takes effect when the handler returns: the current window closes, and
`Name` opens with every control set from its variables. Showing the window that is already
open does nothing. The same variable may appear in several windows (one control per window).

**Requires.** Every control must come after a named `WINDOW`.

**Example**

```pbas
DIM Who$ AS STRING * 24

WINDOW Main, "Two windows"
LABEL Who$
BUTTON "Edit", OpenEdit, DEFAULT
BUTTON "Quit", Quit

WINDOW Edit, "Edit the name"
TEXTBOX Who$, "Your name"
BUTTON "Done", Done, DEFAULT

SUB OpenEdit
    SHOW Edit
END SUB

SUB Done
    SHOW Main
END SUB

SUB Quit
    EXIT
END SUB

Who$ = "Nobody yet"
END
```

**Common errors**

```pbas-error
' expect-error: no WINDOW MAIN is declared (SHOW needs named windows)
WINDOW "Only one"
BUTTON "Go", Go
SUB Go
    SHOW Main
END SUB
END
```

**Limits.** At most 8 windows (`too many WINDOWs: the maximum is 8`). No window opens on top
of another (no modal windows). A handler that shows the window holding the canvas must not
draw after `SHOW`: the window opens only when the handler returns, so drawing before that
stops the program with `the canvas is not on screen` (known issue KI-59,
[limitations](../limitations.md)). Let the canvas's `PAINT` handler draw instead.

*Evidence:* tested in XAnne (`contact_card.pbas`, three windows).

**See also.** `../../examples/contact_card.pbas`; spec
[§5.1](../../LANGUAGE-SPEC.md#51-m6-phase-1--native-application-interfaces).

## Layout: rows and limits

You do not give positions. The compiler stacks controls from the top of the window
(y = 48) in source order, one row each, and puts the buttons in centred rows at the bottom.
Each control keeps the same width in a `LARGE` window; `LARGE` gives more rows, not wider
controls (except a canvas).

| Control | Row height |
|---|---|
| `LABEL` | 32 px |
| `CHECKBOX` | 28 px |
| `TEXTBOX`, `NUMBERBOX`, `CHOICE` | 48 px |
| `RADIO` | 24 px per option, plus 4 |
| `LIST` | 16 px per row, plus 12 |
| `SLIDER` | 40 px |
| `CANVAS` | its height plus 8 (see [chapter 12](12-drawing.md)) |

All rows must end above the first button row: y = 180 in a normal window (132 px for
controls, for example four labels), y = 340 in a `LARGE` one (292 px). Buttons go in rows of
up to three: y = 180 and 208 (normal), 340 and 368 (`LARGE`).

The first control that does not fit is a build error that says where the row would end:

```pbas-error
' expect-error: the dialog has no room for this LABEL
WINDOW "Too many rows"
LABEL "One"
LABEL "Two"
LABEL "Three"
LABEL "Four"
LABEL "Five"
BUTTON "Quit", Quit
SUB Quit
    EXIT
END SUB
END
```

Fix it with `WINDOW "...", LARGE`, fewer rows, or a second named window.

Per window: at most 8 labels, 8 check boxes, 16 option groups and 6 buttons. At most 16
sliders in the whole program. A variable may be bound to only one control in a window
(`… is already bound to a control at line N; one control per variable`).

## BUTTON

**Syntax**

```text
BUTTON "caption", Handler
BUTTON "caption", Handler, DEFAULT
BUTTON "caption", Handler [, DEFAULT] [, KEY k] [, KEY k] [, KEY k]
```

`k` is one of `GREEN RED BLUE YELLOW STOP HELP F1 F2 F3 F4 F5 F6 F7 F8`.

**Meaning.** A push button. A click runs `Handler` once (values read before it, controls
redrawn after it). Two buttons may name the same `SUB`. `DEFAULT` gives the button the Return
key (and the keypad's Enter) and the window's first focus highlight; without a `DEFAULT`, the
first button has the highlight. `KEY k` makes the PcW16's coloured keys, Stop, Help or a
function key press the button too. A key press runs the handler exactly as a click does.

**Requires.** `SUB Handler` without parameters, defined anywhere in the program.

**Example**

```pbas
DIM Count AS INTEGER
DIM Shown$ AS STRING * 24

WINDOW "Counter"
LABEL Shown$
BUTTON "Add", AddOne, DEFAULT, KEY GREEN
BUTTON "Reset", Reset, KEY RED
BUTTON "Quit", Quit, KEY F8

SUB AddOne
    Count = Count + 1
    Shown$ = "Count " + STR$(Count)
END SUB

SUB Reset
    Count = 0
    Shown$ = "Count 0"
END SUB

SUB Quit
    EXIT
END SUB

Shown$ = "Count 0"
END
```

**Common errors**

```pbas-error
' expect-error: the dialog layout holds at most 6 BUTTONs
WINDOW "Seven"
BUTTON "1", Q
BUTTON "2", Q
BUTTON "3", Q
BUTTON "4", Q
BUTTON "5", Q
BUTTON "6", Q
BUTTON "7", Q
SUB Q
    EXIT
END SUB
END
```

```pbas-error
' expect-error: BUTTON caption is 15 characters; the maximum is 14
WINDOW "Caption"
BUTTON "Fifteen letters", Q
SUB Q
    EXIT
END SUB
END
```

```pbas-error
' expect-error: only one BUTTON may be DEFAULT
WINDOW "Two defaults"
BUTTON "Yes", Q, DEFAULT
BUTTON "No", Q, DEFAULT
SUB Q
    EXIT
END SUB
END
```

```pbas-error
' expect-error: unknown key F9
WINDOW "Keys"
BUTTON "Go", Q, KEY F9
SUB Q
    EXIT
END SUB
END
```

```pbas-error
' expect-error: QUIT cannot be an event handler
WINDOW "Handler"
BUTTON "Quit", Quit
SUB Quit(N AS INTEGER)
    EXIT
END SUB
END
```

**Limits.** 1 to 6 buttons per window (two rows of three); caption at most 14 characters; at
most one `DEFAULT`; at most three `KEY`s per button, and a key may belong to only one button in
a window. A 7th button is reported by `build`, not by `check`.

*Evidence:* clicks, two rows, `DEFAULT` and the Green, Red, Blue, Yellow and F-keys are tested
in XAnne (`visitor_counter.pbas`, `order_form.pbas`, `stopwatch.pbas`). `KEY STOP` and
`KEY HELP` are untested: those keys were not mapped in the owner's XAnne set-up (known issue
KI-6, [limitations](../limitations.md)). What Return does while a TEXTBOX is being edited is
not defined; do not rely on it.

**See also.** `../../examples/visitor_counter.pbas`, `../../examples/stopwatch.pbas`;
spec [§5](../../LANGUAGE-SPEC.md#5-program-structure-and-execution-model) and
[§5.1](../../LANGUAGE-SPEC.md#51-m6-phase-1--native-application-interfaces).

## LABEL

**Syntax**

```text
LABEL "fixed text"
LABEL Name$
```

**Meaning.** A row of text. With a literal it never changes. With a STRING variable (a
*dynamic label*) it shows the variable's value when the window opens and again after every
handler that changed it; the old text is erased first.

**Requires.** A dynamic label's variable must be a STRING. It is declared by the `LABEL` if
no `DIM` did.

**Example**

```pbas
DIM Status$ AS STRING * 24
DIM Clicks AS INTEGER

WINDOW "Labels"
LABEL "This text never changes"
LABEL Status$
BUTTON "Click", Clicked
BUTTON "Quit", Quit

SUB Clicked
    Clicks = Clicks + 1
    Status$ = "Clicked " + STR$(Clicks) + " times"
END SUB

SUB Quit
    EXIT
END SUB

Status$ = "Not clicked yet"
END
```

**The 24-character check.** A dynamic label shows **at most 24 characters**, each printable
ASCII (space to `~`). The value is checked every time the window would show it. A longer
value stops the program with `Runtime error: string too long at line N`, and a value with any
other character (a control code, or one of Rosanne's accented or typographic characters 128 to
255) with `Runtime error: label text has an unsupported character at line N`. N is the
`LABEL` line. Text is never cut for you. This program stops as its window opens:

```pbas
' expect-message: Runtime error: string too long at line 4
DIM Status$ AS STRING
WINDOW "Too long"
LABEL Status$
BUTTON "Quit", Quit
SUB Quit
    EXIT
END SUB
Status$ = "This sentence is longer than twenty-four"
END
```

Because a plain `STRING` holds 63 characters, the build warns about such a label:

```text
prog.pbas:3:1: warning: LABEL STATUS$ can hold 63 characters but a LABEL shows at most 24;
a longer value stops the program with "string too long" (cut it, e.g. LEFT$(text, 24),
or use lib/app.pbas AppSay)
```

The warning does not stop the build. To avoid both the warning and the risk, declare the
variable `AS STRING * 24`, or assign it only short literals or `LEFT$(text, 24)`. The library
`lib/app.pbas` offers `AppSay`, which shortens a status line for you
([libraries](../libraries/README.md)).

**Common errors**

```pbas-error
' expect-error: LABEL shows a STRING variable; N is INTEGER
DIM N AS INTEGER
WINDOW "Number"
LABEL N
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

```pbas-error
' expect-error: LABEL text is 48 characters; the maximum is 47
WINDOW "Static"
LABEL "This fixed label text is exactly forty-eight chr"
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

**Limits.** Static text at most 47 characters; a dynamic value at most 24 printable ASCII
characters; at most 8 labels per window; 32 px a row, so four labels alone fill a normal
window. A variable cannot be both a dynamic label and a `TEXTBOX`.

*Evidence:* tested in XAnne (`greeter.pbas`, `visitor_counter.pbas`, and the edge cases in
`../../developer-tests/m5d_labels.pbas`).

**See also.** `../../examples/visitor_counter.pbas`, `../../examples/settings_panel.pbas`;
spec [§5](../../LANGUAGE-SPEC.md#5-program-structure-and-execution-model) (dynamic labels).

## TEXTBOX

**Syntax**

```text
TEXTBOX Name$
TEXTBOX Name$, "caption"
```

**Meaning.** A single-line editable text field bound to a STRING. The caption, if any, sits
above the framed field. The field holds at most capacity − 1 characters; Rosanne refuses
more while typing.

**Requires.** The variable's string capacity must be at most 64 (63 characters). The
program-wide default capacity is 64, so a plain `STRING` is fine.

**Example**

```pbas
WINDOW "Greeting"
TEXTBOX Person$, "Your name"
BUTTON "Greet", Greet, DEFAULT
BUTTON "Clear", Clear
BUTTON "Quit", Quit

SUB Greet
    IF Person$ = "" THEN
        MESSAGE "Type a name first"
    ELSE
        MESSAGE "Hello, " + Person$
    END IF
END SUB

SUB Clear
    Person$ = ""
END SUB

SUB Quit
    EXIT
END SUB
END
```

**Common errors**

A field bound to a longer string is refused, by `check` and by `build`:

```pbas-error
' expect-error: a TEXTBOX holds at most 63 characters, but NOTE$ can hold 100
DIM Note$ AS STRING * 100
WINDOW "Too long"
TEXTBOX Note$, "Note"
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

```pbas-error
' expect-error: TEXTBOX caption is 35 characters; the maximum is 34
WINDOW "Caption"
TEXTBOX A$, "A caption of thirty-five characters"
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

**Limits.** Caption at most 34 characters. One line only; at most 63 characters. A field takes
a 48 px row. What Return does while you edit the field is not defined (known issue KI-6).

*Evidence:* tested in XAnne (`details.pbas`, `editor.pbas`, `text_tool.pbas`).

**See also.** `../../examples/details.pbas`, `../../examples/calculator.pbas`;
[chapter 7](07-text-buffers.md) for longer text; spec [§5](../../LANGUAGE-SPEC.md#5-program-structure-and-execution-model).

## CHECKBOX

**Syntax**

```text
CHECKBOX Name
CHECKBOX Name, "caption"
```

**Meaning.** A tick box bound to a BOOLEAN: ticked is `TRUE`.

**Example**

```pbas
WINDOW "Options"
CHECKBOX Sound, "Play a beep"
BUTTON "Try", Try
BUTTON "Quit", Quit

SUB Try
    IF Sound THEN
        BEEP
    ELSE
        MESSAGE "Sound is off"
    END IF
END SUB

SUB Quit
    EXIT
END SUB

Sound = TRUE
END
```

**Common errors**

```pbas-error
' expect-error: CHECKBOX caption is 35 characters; the maximum is 34
WINDOW "Caption"
CHECKBOX B, "A caption of thirty-five characters"
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

**Limits.** Caption at most 34 characters; at most 8 per window; 28 px a row.

*Evidence:* tested in XAnne (`prefs.pbas`).

**See also.** `../../examples/prefs.pbas`, `../../examples/settings_panel.pbas`.

## RADIO

**Syntax**

```text
RADIO Choice, "first", "second" [, "third" …]
```

**Meaning.** A group of 2 to 6 options, one per row, bound to an INTEGER: 0 = none chosen,
1 to n = that option. Choosing one clears the others. A handler may set the variable to choose
an option.

**Example**

```pbas
WINDOW "Size", LARGE
RADIO Size, "Small", "Medium", "Large"
BUTTON "Order", Order, DEFAULT
BUTTON "Quit", Quit

SUB Order
    IF Size = 0 THEN
        MESSAGE "Choose a size first"
    ELSE
        MESSAGE "You chose size " + STR$(Size)
    END IF
END SUB

SUB Quit
    EXIT
END SUB
END
```

**Common errors**

```pbas-error
' expect-error: RADIO needs 2 to 6 options, got 7
WINDOW "Too many", LARGE
RADIO R, "1", "2", "3", "4", "5", "6", "7"
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

A handler that sets the variable outside 0..n stops the program with
`Runtime error: option number out of range at line N` (N is the `RADIO` line).

**Limits.** 2 to 6 options; captions at most 34 characters; at most 16 groups per window;
24 px per option. The variable cannot be a `$` name.

*Evidence:* tested in XAnne (`order_form.pbas`, `contact_card.pbas`).

**See also.** `../../examples/order_form.pbas`; spec
[§5.1](../../LANGUAGE-SPEC.md#51-m6-phase-1--native-application-interfaces).

## NUMBERBOX and its spinner

**Syntax**

```text
NUMBERBOX N [, "caption"] [, MIN lo] [, MAX hi] [, SPIN]
```

**Meaning.** A field of up to 6 characters that accepts only `-` and digits, bound to an
INTEGER. `lo` and `hi` are integer literals (default −32768 and 32767). `SPIN` adds Rosanne's
spinner (up and down arrows) beside the field; each click changes the shown number by 1 within
`lo..hi`.

Before a button or menu handler runs, the field must hold a whole number from `lo` to `hi`.
If it does not, the handler does **not** run: an alert says
`caption: enter a whole number from lo to hi`, the field goes back to its last valid number and
takes the focus. Before a timer or change handler, an invalid field is left alone and the
variable keeps its value.

**Example**

```pbas
WINDOW "Quantity"
NUMBERBOX Qty, "How many (1 to 20)", MIN 1, MAX 20, SPIN
BUTTON "Order", Order, DEFAULT
BUTTON "Quit", Quit

SUB Order
    MESSAGE "Ordered " + STR$(Qty)
END SUB

SUB Quit
    EXIT
END SUB

Qty = 1
END
```

**Common errors**

```pbas-error
' expect-error: NUMBERBOX MIN 5 is greater than MAX 1
WINDOW "Range"
NUMBERBOX N, "N", MIN 5, MAX 1
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

A value outside `lo..hi` set by your own code stops the program when the field would show it
(`Runtime error: number out of range at line N`). This program stops as the window opens,
because a new INTEGER is 0 and the range starts at 1:

```pbas
' expect-message: Runtime error: number out of range at line 3
WINDOW "Range"
NUMBERBOX Qty, "How many", MIN 1, MAX 20
BUTTON "Quit", Quit
SUB Quit
    EXIT
END SUB
END
```

Set the variable in the main line before `END`, as the example above does.

**Limits.** INTEGER only; 6 characters; a 48 px row; caption at most 34 characters.
**Known defect:** one click on a spinner arrow sometimes changes the number by more than one
step (known issue KI-1, [limitations](../limitations.md)). Check the value in your handler
rather than counting clicks.

*Evidence:* tested in XAnne, with the spinner defect above (`order_form.pbas`,
`contact_card.pbas`).

**See also.** `../../examples/order_form.pbas`; spec
[§5.1](../../LANGUAGE-SPEC.md#51-m6-phase-1--native-application-interfaces).

## LIST

**Syntax**

```text
LIST Sel, Items$, Count [, ROWS r] [, CHANGE Handler] [, ACTION Handler2]
```

**Meaning.** A framed list with a scroll bar showing the first `Count` elements of the STRING
array `Items$`, `r` rows at a time (default 5). It binds the INTEGER `Sel`: 0 = nothing
selected, 1 to `Count` = that item. Clicking an item selects it. `CHANGE` runs a handler after
the user selects an item. After every handler the list is rebuilt from the array and `Count`,
so changed texts appear; if the handler changed `Sel`, the list scrolls to show it.

**Requires.** An ordinary (not `BANKED`) STRING array; `Count` an INTEGER variable or a literal.

**Memory.** The item array is an ordinary array, so all of it, every element at its full
capacity, is in the resident 16K block, together with the list's item table (3 bytes for each
element). A list of 200 names of `STRING * 24` takes about 5,600 bytes there. For many rows,
draw the list on a CANVAS with [lib/listview.pbas](../libraries/listview.md) and keep the rows
in a `BANKED` array: its `ListCell$` function reads one row at a time
([memory](../memory.md)).

**Example**

```pbas
DIM Fruit$(4) AS STRING * 20
DIM Count AS INTEGER

WINDOW "Fruit", LARGE
LIST Pick, Fruit$, Count, ROWS 4
BUTTON "Show", ShowPick, DEFAULT
BUTTON "Quit", Quit

SUB ShowPick
    IF Pick = 0 THEN
        MESSAGE "Select a fruit first"
    ELSE
        MESSAGE "You picked " + Fruit$(Pick)
    END IF
END SUB

SUB Quit
    EXIT
END SUB

Fruit$(1) = "Apple"
Fruit$(2) = "Banana"
Fruit$(3) = "Cherry"
Fruit$(4) = "Damson"
Count = 4
END
```

**Common errors**

```pbas-error
' expect-error: LIST ROWS must be 2 to 12
DIM A$(3) AS STRING
WINDOW "Rows", LARGE
LIST S, A$, 3, ROWS 13
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

```pbas-error
' expect-error: LIST cannot show the BANKED array A$
DIM A$(300) AS STRING * 20 BANKED
WINDOW "Banked", LARGE
LIST S, A$, 3
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

Runtime errors, at the `LIST` line: `list count out of range` (`Count` outside 0..array size),
`list position out of range` (`Sel` outside 0..`Count`), `string too long` (a shown item over
24 characters) and `list text has an unsupported character`.

**Limits and known defects.**
- 2 to 12 rows; a shown item at most 24 printable ASCII characters; single selection only.
- **`ACTION` never runs in XAnne:** XAnne reports a double-click on a list as two single
  clicks (known issue KI-25). Give the same action a button.
- Dragging the scroll bar's handle sometimes starts only near the handle (KI-5); the arrows and
  paging work.
- Every list is rebuilt and redrawn after every handler, which may flicker (KI-8).
- What the keyboard does on a list is not defined.

*Evidence:* tested in XAnne, with the defects above (`shopping_list.pbas`, `phone_book.pbas`).

**See also.** `../../examples/shopping_list.pbas`, `../../examples/phone_book.pbas`; for a
list drawn on a canvas, with columns and keyboard control, `lib/listview.pbas`
([libraries](../libraries/README.md)); spec
[§5.2](../../LANGUAGE-SPEC.md#52-m6-phase-2--arrays-and-data-rich-controls).

## CHOICE

**Syntax**

```text
CHOICE Sel, Items$, Count [, "caption"] [, CHANGE Handler]
```

**Meaning.** A drop-down choice: a framed readout with Rosanne's drop button. Clicking the
button opens a list of up to 6 rows; choosing an item sets `Sel` and the readout.

**Requires.** `Sel` must be 1 to `Count` (and `Count` at least 1) whenever the window shows it.
Rosanne has no "nothing chosen" state for a drop-down, so set `Sel` before the window opens.

**Example**

```pbas
DIM Tea$(3) AS STRING * 12

WINDOW "Tea"
CHOICE Kind, Tea$, 3, "Kind of tea"
BUTTON "Brew", Brew, DEFAULT
BUTTON "Quit", Quit

SUB Brew
    MESSAGE "Brewing " + Tea$(Kind)
END SUB

SUB Quit
    EXIT
END SUB

Tea$(1) = "Assam"
Tea$(2) = "Darjeeling"
Tea$(3) = "Green"
Kind = 1
END
```

**Common errors.** Forgetting to set `Sel` stops the program as the window opens:

```pbas
' expect-message: Runtime error: a CHOICE must show an item from 1 to its count at line 4
DIM Tea$(3) AS STRING * 12
WINDOW "Tea"
CHOICE Kind, Tea$, 3, "Kind of tea"
BUTTON "Quit", Quit
SUB Quit
    EXIT
END SUB
Tea$(1) = "Assam"
Tea$(2) = "Darjeeling"
Tea$(3) = "Green"
END
```

```pbas-error
' expect-error: CHOICE count must be 1 to 3
DIM Tea$(3) AS STRING * 12
WINDOW "Tea"
CHOICE Kind, Tea$, 0
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

**Limits.** A shown item at most 24 printable characters; the drop-down list (up to 6 rows)
must fit inside the window, which is a build error otherwise; a 48 px row. Not a `BANKED`
array.

*Evidence:* tested in XAnne (`tea_timer.pbas`; a 13-item choice in `scicalc.pbas`).

**See also.** `../../examples/tea_timer.pbas`, `../../examples/scicalc.pbas`; spec
[§5.2](../../LANGUAGE-SPEC.md#52-m6-phase-2--arrays-and-data-rich-controls).

## SLIDER

**Syntax**

```text
SLIDER V, MIN lo, MAX hi [, "caption"] [, CHANGE Handler]
```

**Meaning.** A horizontal slider (a 280-pixel scroll bar) bound to an INTEGER within `lo..hi`.
An arrow changes the value by 1, a click on the track by max(1, (hi − lo) / 10), and dragging
the handle sets it proportionally. `CHANGE` runs a handler after each change.

**Example**

```pbas
WINDOW "Volume"
SLIDER Level, MIN 0, MAX 10, "Level", CHANGE Moved
LABEL Shown$
BUTTON "Quit", Quit

SUB Moved
    Shown$ = "Level " + STR$(Level)
END SUB

SUB Quit
    EXIT
END SUB

Level = 5
Shown$ = "Level 5"
END
```

**Common errors**

```pbas-error
' expect-error: SLIDER MAX - MIN must be 1 to 250, got 251
WINDOW "Range"
SLIDER V, MIN 0, MAX 251
BUTTON "Quit", Q
SUB Q
    EXIT
END SUB
END
```

A value outside `lo..hi` when the slider is shown stops the program
(`Runtime error: number out of range at line N`).

**Limits and known defects.** 1 ≤ hi − lo ≤ 250; at most 16 sliders in a program; horizontal
only; a 40 px row. One arrow click sometimes moves the slider by more than one step (known
issue KI-2, [limitations](../limitations.md)).

*Evidence:* tested in XAnne, with the defect above (`tea_timer.pbas`).

**See also.** `../../examples/tea_timer.pbas`; spec
[§5.2](../../LANGUAGE-SPEC.md#52-m6-phase-2--arrays-and-data-rich-controls).

## FOCUS

**Syntax**

```text
FOCUS Name
```

**Meaning.** Moves the keyboard focus to the `TEXTBOX`, `NUMBERBOX` or `CHECKBOX` bound to
`Name`, when the handler returns or when its window next opens. `Name` may also be a named
canvas: its KEYS handler then takes the keys without a click
([chapter 12](12-drawing.md#several-canvases-draw-on)).

**Example**

```pbas
WINDOW "Focus"
TEXTBOX First$, "First name"
TEXTBOX Last$, "Last name"
BUTTON "Check", Check, DEFAULT
BUTTON "Quit", Quit

SUB Check
    IF Last$ = "" THEN
        MESSAGE "Please type the last name"
        FOCUS Last$
    END IF
END SUB

SUB Quit
    EXIT
END SUB
END
```

**Limits.** `Name` must be bound in exactly one window. A click on a canvas also takes the
keyboard from a text field in the same window (known issue KI-87).

*Evidence:* tested in XAnne (`contact_card.pbas`, `order_form.pbas`; a canvas, M15c C3–C4).

## MESSAGE, ASK and BEEP

**Syntax**

```text
MESSAGE expr
Answer = ASK(text$, "button1", "button2" [, "button3"])
BEEP
```

**Meaning.**
- `MESSAGE` shows Rosanne's alert with the text and an OK button, and waits until it is
  dismissed. The text is any STRING expression (use `STR$` for numbers).
- `ASK` shows an alert with 2 or 3 buttons and stores 1, 2 or 3 (the button chosen) in an
  INTEGER. The first button also answers to Return and the Green key, the last to Stop and the
  Red key.
- `BEEP` sounds Rosanne's beep. There is no other sound.

All three work in the main line and in handlers. A `MESSAGE` in the main line of a windowed
program appears before the window opens. In a program with a canvas, an alert shown by a handler
makes the canvas's `PAINT` handler run again when that handler returns
([chapter 12](12-drawing.md#paint-handler)).

**Example** (no input needed, so the alerts are checked on the simulator):

```pbas
' expect-message: Total: 12
' expect-message: Done
DIM A AS INTEGER
A = 7 + 5
MESSAGE "Total: " + STR$(A)
BEEP
MESSAGE "Done"
END
```

```pbas
DIM Answer AS INTEGER

WINDOW "Question"
LABEL "Quit asks first"
BUTTON "Quit", Quit

SUB Quit
    Answer = ASK("Quit the program?", "Quit", "Stay")
    IF Answer = 1 THEN
        EXIT
    END IF
END SUB
END
```

**Common errors**

```pbas-error
' expect-error: MESSAGE literal is 251 bytes; the maximum is 250
MESSAGE "..........................................................................................................................................................................................................................................................x"
END
```

```pbas-error
' expect-error: ASK may only be the whole right-hand side of an assignment to an INTEGER
DIM A AS INTEGER
A = 1 + ASK("Sure?", "Yes", "No")
END
```

**Limits.**
- `MESSAGE`: a literal at most 250 bytes. Text built at run time is budgeted against a
  160-byte alert buffer: the literal bytes, plus the capacity of every variable used, plus 6
  for every `STR$`, must fit, or the compiler refuses the statement. Declare short strings with
  `STRING * n` to fit more.
- `ASK`: text budgeted against 100 bytes; button captions are literals of 1 to 10
  characters; 2 or 3 buttons.

*Evidence:* `MESSAGE` tested in XAnne from the first programs (`hello_pcw.pbas`); `ASK` and
`BEEP` tested in XAnne (`order_form.pbas`, `stopwatch.pbas`).

**See also.** `../../examples/hello_pcw.pbas`, `../../examples/order_form.pbas`; spec
[§5.1](../../LANGUAGE-SPEC.md#51-m6-phase-1--native-application-interfaces) and
[§6](../../LANGUAGE-SPEC.md#6-statements).

## Closing a program

A window has no close box of its own. A program ends when:
- your code runs `EXIT` (in a handler, a procedure or the main line); the window is removed
  and the program returns to Rosanne;
- Rosanne tells the program to close; the window is removed the same way;
- a runtime error happens; an alert names the error and the line, then the window is removed.

That is why every window needs a button: give the user a Quit button (and, if you like, a menu
item and `KEY STOP`, which is untested). To ask first, use `ASK` as in the example above, or
`AppMayClose` in `lib/app.pbas`, which asks only when there are unsaved changes. When the
program ends, edits made since the last handler are discarded, and an open print page is
discarded.

`EXIT SUB` is different: it only returns from the current procedure, and the program goes on
waiting for events.

## What is not available

These are not part of the language; the compiler has no statement for them:
greying out a control or menu item; hiding a control; windows at other positions or sizes;
modal windows on top of the current one; multi-line text fields or fields over 63 characters;
fonts other than Rosanne's dialog font; vertical sliders; multi-selection lists; lists of
anything but STRINGs; Tab to move the focus. For text editing, use a TEXT buffer drawn on a
canvas ([chapter 7](07-text-buffers.md), `../../examples/mdedit4.pbas`). For everything
missing compared with other BASICs, see [chapter 17](17-unsupported.md).

Next: [11. Menus, keys and the mouse](11-menus-keys-mouse.md).
