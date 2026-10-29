# 11. Menus, keys and the mouse

This chapter covers the menu bar, keyboard shortcuts, the keys a canvas receives, keys held
down (`KEYDOWN`), the `lib/keys.pbas` names for key numbers, and mouse events on a canvas.
Buttons' own keys (`KEY GREEN`, `DEFAULT` for Return) are in
[chapter 10](10-windows-and-controls.md#button).

Evidence levels: *Tested in XAnne* (the owner ran it in the XAnne emulator, Rosanne 1.12),
*Simulator only*, *Untested*. Nothing has yet been tested on a real PcW16.

Contents: [MENU and ITEM](#menu-and-item) · [Tasks → Stop and ON STOP](#tasks--stop-and-on-stop) ·
[Which input goes where](#which-input-goes-where) ·
[Canvas keys: KEYS, KEYCODE, KEYSHIFT](#canvas-keys-keys-keycode-keyshift) ·
[Held keys: KEYDOWN](#held-keys-keydown) · [lib/keys.pbas](#libkeyspbas-names-for-keys) ·
[The mouse: MOUSE, MOUSEX, MOUSEY, MOUSEEVENT](#the-mouse-mouse-mousex-mousey-mouseevent) ·
[What is not available](#what-is-not-available)

## MENU and ITEM

**Syntax**

```text
MENU "Title"
    ITEM "text", Handler
    ITEM "text", Handler, KEY "X"
    ITEM "text", Handler, TICK Flag
    ITEM "text", Handler, KEY "X", TICK Flag
    ITEM "-"
END MENU
```

**Meaning.** Each `MENU … END MENU` block adds a title to the menu bar, after Rosanne's own
Tasks menu, in source order. Choosing an item runs its `SUB` exactly like a button click:
controls are read before it and redrawn after it. `ITEM "-"` is a divider line.
`KEY "X"` (one letter or digit) makes Ctrl+X choose the item. `TICK Flag` shows the BOOLEAN
`Flag` as a tick beside the item; the runtime sets the tick from `Flag` when the first window
opens and after every handler. Choosing the item does not change `Flag`: your handler decides
(usually `Flag = NOT Flag`). `TICK` declares `Flag` if no `DIM` did.

The menu bar is available in every window of the program while it is open.

**Requires.** A `WINDOW` in the program; handlers are `SUB`s without parameters.

**Example**

```pbas
DIM Count AS INTEGER
DIM Shown$ AS STRING * 24

WINDOW "Menus"
LABEL Shown$
BUTTON "Quit", Quit

MENU "File"
    ITEM "Add one", AddOne, KEY "A"
    ITEM "Reset", Reset
    ITEM "-"
    ITEM "Quit", Quit, KEY "Q"
END MENU

MENU "Options"
    ITEM "Beep on add", ToggleBeep, TICK BeepOn
END MENU

SUB AddOne
    Count = Count + 1
    Shown$ = "Count " + STR$(Count)
    IF BeepOn THEN
        BEEP
    END IF
END SUB

SUB Reset
    Count = 0
    Shown$ = "Count 0"
END SUB

SUB ToggleBeep
    BeepOn = NOT BeepOn
END SUB

SUB Quit
    EXIT
END SUB

Shown$ = "Count 0"
END
```

**Common errors**

```pbas-error
' expect-error: MENU requires a WINDOW declaration
MENU "File"
    ITEM "Quit", Quit
END MENU
SUB Quit
    EXIT
END SUB
END
```

```pbas-error
' expect-error: MENU title is 13 characters; the maximum is 12
WINDOW "Menus"
BUTTON "Quit", Quit
MENU "Thirteen char"
    ITEM "Quit", Quit
END MENU
SUB Quit
    EXIT
END SUB
END
```

```pbas-error
' expect-error: a menu KEY is one letter or digit
WINDOW "Menus"
BUTTON "Quit", Quit
MENU "File"
    ITEM "Quit", Quit, KEY "F1"
END MENU
SUB Quit
    EXIT
END SUB
END
```

**Limits.**
- At most 8 menus (`too many MENUs: the maximum is 8`).
- At most 20 items per menu, dividers included (`a MENU has at most 20 ITEMs (dividers included)`).
- Title at most 12 characters, item text at most 20; printable ASCII without `|`.
- Rosanne's Tasks menu and all your menus must fit a 2048-byte area. This is checked when the
  window opens: `Runtime error: the menus are too large`. The text is never cut.
- You cannot grey out or hide an item.

*Evidence:* menus, ticks and Ctrl shortcuts tested in XAnne (`order_form.pbas`,
`stopwatch.pbas`, `paint2.pbas`, `designer.pbas`). Shortcuts placed after an item without
`KEY` used to be lost; that is corrected in the current compiler and was retested in XAnne
(known issue KI-89, [limitations](../limitations.md)). The build option
`--legacy-menu-hotkeys` brings the old behaviour back only to rebuild old executables byte for
byte; do not use it.

**See also.** `../../examples/order_form.pbas`, `../../examples/stopwatch.pbas`,
`../../examples/paint2.pbas`; spec
[§5.1](../../LANGUAGE-SPEC.md#51-m6-phase-1--native-application-interfaces) (Menus) and
[§5.15](../../LANGUAGE-SPEC.md#515-m13--ticks-the-clock-in-sixteenths-and-held-keys) (Menu shortcuts).

## Tasks → Stop and ON STOP

**Syntax**

```text
ON STOP Handler        Handler: FUNCTION Handler() AS BOOLEAN, without parameters
```

**Meaning.** Rosanne's Tasks menu, the first menu on the bar, has Stop as its first entry.
- A program with menus **ends** when Stop is chosen, as on `EXIT`: the window is removed, files are closed and memory is given back.
- With `ON STOP Handler`, Stop runs the handler first, like a menu item's handler. **TRUE ends the program, FALSE keeps it running.** The handler may ask a question or save a file.
- `lib/app.pbas` has one ready: `ON STOP AppMayClose` asks about unsaved changes (Save / Discard / Cancel).
- One `ON STOP` per program, at the top level.

**Example**

```pbas
DIM Edited AS BOOLEAN
DIM A AS INTEGER

WINDOW "Stop asks"
CHECKBOX Edited, "Pretend there are changes"
BUTTON "Quit", Quit
MENU "File"
    ITEM "Quit", Quit
END MENU
ON STOP MayStop

FUNCTION MayStop() AS BOOLEAN
    IF NOT Edited THEN
        RETURN TRUE
    END IF
    A = ASK("Discard the changes?", "Discard", "Cancel")
    RETURN A = 1
END FUNCTION

SUB Quit
    EXIT
END SUB
END
```

```pbas-error
' expect-error: ON STOP needs a FUNCTION QUIT() AS BOOLEAN
WINDOW "Wrong"
BUTTON "Quit", Quit
ON STOP Quit
SUB Quit
    EXIT
END SUB
END
```

**Limits.**
- A program without menus shows no menu bar, so Stop never reaches it (known issue KI-108). The compiler warns about `ON STOP` there; give such a program a Quit button, or a menu.
- The other Tasks entries are Rosanne's.
- The build option `--legacy-tasks-stop` brings back the old behaviour (Stop ignored) only to rebuild old executables byte for byte; do not use it.
- `examples/stopguard.pbas` is a small complete program that saves its note, or asks, before Stop ends it.

*Evidence:*
- XAnne (M15a): Stop arrives as Tasks entry 0, and a program that ends on it does so cleanly after its own code has run.
- `ON STOP`, tested in XAnne (M15c S1–S4, S6, S7): ending at once, staying open, asking first, saving then ending, and the unsaved-work questions of PAINT II, DESIGNER, SPRITED, MDEDIT IV and CONTACTS IV.

## Which input goes where

| Input | Goes to | Available |
|---|---|---|
| Click on a button; its `DEFAULT` (Return) or `KEY` keys | that button's handler | any window |
| Menu choice; Ctrl+letter of an item's `KEY` | that item's handler | any program with a WINDOW |
| Typing in a focused TEXTBOX or NUMBERBOX | Rosanne edits the field; no BASIC code runs | any window |
| Any other key, while the canvas's window is open | the canvas's `KEYS` handler (`KEYCODE`, `KEYSHIFT`) | programs with a CANVAS |
| Whether a key is held down *now* | `KEYDOWN(code)`, from any code | any program (tested in XAnne only with a CANVAS) |
| Left mouse button on the canvas: press, drag, release | the canvas's `MOUSE` handler | programs with a CANVAS |

A key owned by a button, a menu or a focused text field never reaches `KEYS`.

## Canvas keys: KEYS, KEYCODE, KEYSHIFT

**Syntax**

```text
CANVAS width, height, KEYS Handler [, PAINT P] [, MOUSE M]
KEYCODE          the key's character code (INTEGER)
KEYSHIFT         the shift state: 1 Shift, 2 Alt, 4 Ctrl, 16 keypad (added together)
```

(The `PAINT`, `MOUSE` and `KEYS` clauses may come in any order after the size.)

**Meaning.** While the canvas's window is open, every key Rosanne passes to the program runs
the `KEYS` handler. `KEYCODE` is the character the key gives: printable characters as
themselves (`a` is 97, Shift+A is 65), and for other keys:

| Key | KEYCODE | | Key | KEYCODE |
|---|---|---|---|---|
| Return | 13 | | Up | 224 |
| Backspace | 8 | | Down | 225 |
| Tab | 9 | | Left | 226 |
| Delete | 229 | | Right | 227 |
| Home | 230 | | PgUp | 232 |
| End | 231 | | PgDn | 233 |
| Stop | 254 | | f1 to f8 | 241 to 248 |

A key held down repeats at the keyboard's rate, so `KEYS` is right for typing and commands,
not for smooth movement (use `KEYDOWN` with a timer for that). `KEYCODE`, `KEYSHIFT` and the
mouse values keep the last event's values and can be read in any expression of a program with
a canvas.

**Example**

```pbas
INCLUDE "lib/keys.pbas"

DIM X AS INTEGER

WINDOW "Arrow keys"
CANVAS 200, 60, PAINT Paint, KEYS Keys
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
    DRAW FILL X, 20, 20, 20
END SUB

SUB Keys
    IF KEYCODE = KC_LEFT AND X >= 10 THEN
        X = X - 10
    END IF
    IF KEYCODE = KC_RIGHT AND X <= 170 THEN
        X = X + 10
    END IF
    IF KEYCODE = KC_STOP THEN
        EXIT
    END IF
    CALL Paint
END SUB

SUB Quit
    EXIT
END SUB

X = 90
END
```

**Common errors**

```pbas-error
' expect-error: undefined variable KEYCODE
WINDOW "No canvas"
BUTTON "Quit", Quit
SUB Quit
    IF KEYCODE = 13 THEN
        EXIT
    END IF
END SUB
END
```

**Limits.** Only keys Rosanne passes while the canvas's window is open. Tab reaches `KEYS`; it
does not move the focus.

*Evidence:* tested in XAnne for the keys in the table, plus letters with and without Shift
(`../../developer-tests/gfxprobe.pbas`, known issue KI-41). Other keys are untested.

**See also.** `../../examples/uibench.pbas`, `../../examples/mdedit4.pbas`; spec
[§5.6](../../LANGUAGE-SPEC.md#56-m9--canvas-drawing-and-canvas-events) (KEYS).

## Held keys: KEYDOWN

**Syntax**

```text
KEYDOWN(code)        BOOLEAN: TRUE while that key is held down now
```

**Meaning.** `KEYDOWN` reads the keyboard's state at that moment; no event is needed. Several
keys can be down at once. It is meant for games: a timer handler moves something for as long as
a key is held ([chapter 14](14-timers-and-animation.md)).

`code` is 0 to 127, the number Rosanne's keyboard handler keeps the key's state under. This is
**not** the same numbering as `KEYCODE`: Left is 99 for `KEYDOWN` but 226 for `KEYCODE`. Use
the `SC_` names in `lib/keys.pbas`, never the numbers.

**Requires.** Nothing. A program without a CANVAS may use `KEYDOWN`, and may include
`lib/keys.pbas`. (Up to M13 such a program failed in the assembler with `Symbol 'rt_err_msg'
is undefined`; M14 fixed this.) `KEYDOWN` has been tested in XAnne only in programs with a
canvas, which is where held keys are useful.

```pbas
DIM Held AS BOOLEAN
WINDOW "Keys"
LABEL "Hold Space, then click Look"
BUTTON "Look", Look
BUTTON "Quit", Quit
SUB Look
    Held = KEYDOWN(41)
END SUB
SUB Quit
    EXIT
END SUB
END
```

A program with a canvas:

```pbas
INCLUDE "lib/keys.pbas"

DIM X AS INTEGER

WINDOW "Hold a key"
CANVAS 200, 40, PAINT Paint
BUTTON "Look", Look, DEFAULT
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
    DRAW FILL X, 10, 20, 20
END SUB

SUB Look
    ' Hold Left or Right while pressing Return
    X = X + 20 * KeyAxis(SC_LEFT, SC_RIGHT)
    X = MAX(0, MIN(X, 180))
    CALL Paint
END SUB

SUB Quit
    EXIT
END SUB

X = 90
END
```

**Common errors.** A code outside 0..127 stops the program:
`Runtime error: a key code is 0 to 127 at line N`.

**Limits.**
- A key pressed and released between two looks is never seen held (known issue KI-92). A game
  that must not miss a tap (a jump, say) also takes it from `KEYS`, as
  `../../examples/jumper.pbas` does for Space.
- The key numbers were read from Rosanne 1.12's keyboard handler and checked in XAnne for
  Left, Right, Up, Down, Space and A. The others come from the same table but were not each
  pressed in XAnne. Not yet tested on a real PcW16 keyboard.

*Evidence:* tested in XAnne (`../../developer-tests/sprprb.pbas`, `../../examples/jumper.pbas`, the
tutorial game `../../examples/tutorial/t3_hop.pbas`).

**See also.** spec
[§5.15](../../LANGUAGE-SPEC.md#515-m13--ticks-the-clock-in-sixteenths-and-held-keys) (Held keys).

## lib/keys.pbas: names for keys

`INCLUDE "lib/keys.pbas"` near the top of the program gives:

- 70 `SC_` constants for `KEYDOWN`: `SC_UP` 101, `SC_DOWN` 98, `SC_LEFT` 99, `SC_RIGHT` 100,
  `SC_HOME`, `SC_END`, `SC_PGUP`, `SC_PGDN`, `SC_INSERT`, `SC_DELETE`, `SC_SPACE` 41,
  `SC_RETURN`, `SC_ESC`, `SC_TAB`, `SC_BACKSPACE`, `SC_LSHIFT`, `SC_RSHIFT`, `SC_CTRL`,
  `SC_RCTRL`, `SC_ALT`, `SC_RALT`, `SC_KPENTER`, `SC_KPDIVIDE`, `SC_PRINTSCREEN`,
  `SC_KP0` to `SC_KP9` (the keypad), `SC_A` to `SC_Z` and `SC_0` to `SC_9`.
  The cursor keys and the keypad's 8, 2, 4, 6 are different keys with different `SC_` codes.
- 13 `KC_` constants for `KEYCODE`: `KC_RETURN` 13, `KC_BACKSPACE` 8, `KC_TAB` 9,
  `KC_DELETE` 229, `KC_UP` 224, `KC_DOWN` 225, `KC_LEFT` 226, `KC_RIGHT` 227, `KC_HOME` 230,
  `KC_END` 231, `KC_PGUP` 232, `KC_PGDN` 233, `KC_STOP` 254. (For letters, compare `KEYCODE`
  with `ASC("a")` and so on.)
- `FUNCTION KeyAxis(Minus AS INTEGER, Plus AS INTEGER) AS INTEGER`: −1 while only the `Minus`
  key is down, 1 while only `Plus` is, otherwise 0. `KeyAxis(SC_LEFT, SC_RIGHT)` is a
  horizontal direction.

Full reference: [libraries](../libraries/README.md) and
[LIBRARY-REFERENCE](../LIBRARY-REFERENCE.md).

## The mouse: MOUSE, MOUSEX, MOUSEY, MOUSEEVENT

**Syntax**

```text
CANVAS width, height, MOUSE Handler [, PAINT P] [, KEYS K]
MOUSEEVENT       1 press, 2 drag (moved with the button down), 3 release
MOUSEX, MOUSEY   the position in canvas coordinates
```

**Meaning.** The `MOUSE` handler runs when the left button is pressed inside the canvas
(`MOUSEEVENT` = 1), on each movement while it stays down after such a press (2), and when it is
released (3). During a drag the position may be outside the canvas, so check it before you
draw there. Clicks elsewhere in the window go to the buttons and controls as usual.

**Example**

```pbas
WINDOW "Click to draw"
CANVAS 300, 100, PAINT Paint, MOUSE Mouse
BUTTON "Clear", Paint
BUTTON "Quit", Quit

SUB Paint
    DRAW CLEAR
END SUB

SUB Mouse
    IF MOUSEX < 0 OR MOUSEY < 0 OR MOUSEX > 299 OR MOUSEY > 99 THEN
        EXIT SUB
    END IF
    IF MOUSEEVENT = 1 OR MOUSEEVENT = 2 THEN
        DRAW PIXEL MOUSEX, MOUSEY
    END IF
END SUB

SUB Quit
    EXIT
END SUB
END
```

**Common errors**

```pbas-error
' expect-error: undefined variable MOUSEX
WINDOW "No canvas"
BUTTON "Quit", Quit
SUB Quit
    MESSAGE STR$(MOUSEX)
END SUB
END
```

**Limits.** Left button only. No double-click (a double-click arrives as two presses), no
hover or movement without the button down, no right or centre button. The mouse is read only on
the canvas.

For dragging shapes, rubber-band rectangles and selection handles, use `lib/drag.pbas` and
`lib/handles.pbas` ([libraries](../libraries/README.md)), as
`../../examples/paint2.pbas` and `../../examples/designer.pbas` do.

*Evidence:* press, drag and release tested in XAnne (`../../developer-tests/gfxprobe.pbas`;
`paint2.pbas`, `designer.pbas`).

**See also.** `../../examples/tutorial/t2_draw.pbas` and
[Tutorial 2](../TUTORIAL-2-GRAPHICS.md); spec
[§5.6](../../LANGUAGE-SPEC.md#56-m9--canvas-drawing-and-canvas-events) (MOUSE).

## What is not available

- Keyboard events outside a canvas: without a CANVAS, only buttons' keys, menu shortcuts and
  text fields respond to keys. There is no `INKEY$` or `INPUT`.
- Greying menu items, menus that change at run time, pop-up menus.
- Right and centre mouse buttons, double-clicks, mouse movement without a button down.
- Tab or the cursor keys to move between controls.

See [chapter 17](17-unsupported.md) for the statements other BASICs have.

Next: [12. Drawing](12-drawing.md).
