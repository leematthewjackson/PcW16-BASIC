# lib/keys.pbas: names for keys

`lib/keys.pbas` gives names to the two kinds of key number a program meets:

- **`SC_` constants** are the codes `KEYDOWN(code)` takes. `KEYDOWN` tells whether a key is held down *now*, which is how a game moves something steadily while a key is held. Several keys can be down at once.
- **`KC_` constants** are the character codes `KEYCODE` gives inside a canvas's KEYS handler. A KEYS event comes once per key press and then repeats at the keyboard's own rate, so it suits typing and commands, not steady movement.

It also has one function, `KeyAxis`, that turns a pair of held keys into −1, 0 or 1.

**Evidence:** *Tested in XAnne* through JUMPER and the third tutorial game (T3HOP), which move with `SC_LEFT`/`SC_RIGHT` and jump with `SC_SPACE`, and through PAINT II, DESIGNER and SPRITED, which use the `KC_` names in their KEYS handlers. Only six scan codes were observed in XAnne: Left 99, Right 100, Up 101, Down 98, Space 41 and A 28. The other `SC_` values come from reading Rosanne's keyboard table and have not been checked key by key. Not yet tested on a real PcW16.

## Adding it

```text
INCLUDE "lib/keys.pbas"
```

It needs no other library and no CANVAS. (Up to M13 a program that included it without a CANVAS failed when Pasmo assembled it; M14 fixed this.) Held keys are tested in XAnne only in programs with a CANVAS.

```pbas
' No CANVAS: this builds since M14.
INCLUDE "lib/keys.pbas"
WINDOW "No canvas"
BUTTON "Quit", Quit
SUB Quit
    EXIT
END SUB
END
```

## The function

| Name | Kind | Parameters | Result | What it does |
|---|---|---|---|---|
| `KeyAxis` | FUNCTION | `Minus AS INTEGER, Plus AS INTEGER` (scan codes) | INTEGER | −1 while only the Minus key is down, 1 while only the Plus key is down, otherwise 0. |

`X = X + 4 * KeyAxis(SC_LEFT, SC_RIGHT)` moves X four pixels per step while Left or Right is held.

## Constants: scan codes for KEYDOWN

| Group | Names (value) |
|---|---|
| Cursor keys | `SC_UP` 101, `SC_DOWN` 98, `SC_LEFT` 99, `SC_RIGHT` 100 |
| Editing keys | `SC_HOME` 110, `SC_END` 106, `SC_PGUP` 94, `SC_PGDN` 95, `SC_INSERT` 80, `SC_DELETE` 81, `SC_BACKSPACE` 102, `SC_TAB` 13, `SC_RETURN` 90, `SC_ESC` 118, `SC_SPACE` 41 |
| Modifiers | `SC_LSHIFT` 18, `SC_RSHIFT` 89, `SC_CTRL` 20, `SC_ALT` 17, `SC_RCTRL` 19, `SC_RALT` 16 |
| Keypad | `SC_KP0` 112, `SC_KP1` 105, `SC_KP2` 114, `SC_KP3` 122, `SC_KP4` 107, `SC_KP5` 115, `SC_KP6` 116, `SC_KP7` 108, `SC_KP8` 117, `SC_KP9` 125, `SC_KPENTER` 92, `SC_KPDIVIDE` 109 |
| Other | `SC_PRINTSCREEN` 57 |
| Letters | `SC_A` 28, `SC_B` 50, `SC_C` 33, `SC_D` 35, `SC_E` 36, `SC_F` 43, `SC_G` 52, `SC_H` 51, `SC_I` 67, `SC_J` 59, `SC_K` 66, `SC_L` 75, `SC_M` 58, `SC_N` 49, `SC_O` 68, `SC_P` 77, `SC_Q` 21, `SC_R` 45, `SC_S` 27, `SC_T` 44, `SC_U` 60, `SC_V` 42, `SC_W` 29, `SC_X` 34, `SC_Y` 53, `SC_Z` 26 |
| Digits | `SC_0` 69, `SC_1` 22, `SC_2` 30, `SC_3` 38, `SC_4` 37, `SC_5` 46, `SC_6` 54, `SC_7` 61, `SC_8` 62, `SC_9` 70 |

The cursor keys and the keypad's 8, 2, 4 and 6 have different scan codes (`SC_UP` and `SC_KP8`, and so on).

## Constants: characters for KEYCODE

| Name | Value | Name | Value |
|---|---:|---|---:|
| `KC_RETURN` | 13 | `KC_UP` | 224 |
| `KC_BACKSPACE` | 8 | `KC_DOWN` | 225 |
| `KC_TAB` | 9 | `KC_LEFT` | 226 |
| `KC_DELETE` | 229 | `KC_RIGHT` | 227 |
| `KC_HOME` | 230 | `KC_END` | 231 |
| `KC_PGUP` | 232 | `KC_PGDN` | 233 |
| `KC_STOP` | 254 | | |

The cursor keys and the keypad's arrows give the same `KC_` character. Other keys give the character they type.

## Names it defines

83 CONSTs (70 `SC_` and 13 `KC_`) and the FUNCTION `KeyAxis`. A program cannot declare a CONST or variable of its own with any of these names (`duplicate CONST SC_UP`, or `SC_UP is already a CONST`). Inside a SUB, a parameter or LOCAL may reuse a CONST's name.

## Memory cost

| | bytes |
|---|---:|
| whole program, one 16K image | +163 |
| resident 16K block, procedures in code banks | +92 |

CONSTs take no memory; the cost is `KeyAxis` and the runtime's KEYDOWN routine.

## Errors and timing

- `KEYDOWN` reads the key's state at that moment. A key pressed and released between two timer events is never seen held (known issue KI-92, [limitations](../limitations.md)). JUMPER also takes its jump key from the KEYS handler so that a short tap is not lost.
- Keys that a BUTTON, menu shortcut or focused text field owns are not passed to the canvas's KEYS handler.

## Example

Hold Left or Right to move the block. Read the keys from a TIMER and step by the clock with [lib/pace.pbas](pace.md) in a real game; this example moves a fixed step per event to stay short.

```pbas
INCLUDE "lib/keys.pbas"
DIM X AS INTEGER
WINDOW "Keys"
CANVAS 200, 60, PAINT Paint, KEYS Keys
BUTTON "Quit", Quit
TIMER Tick, EVERY 2 TICKS
SUB Paint
    DRAW CLEAR
    DRAW FILL X, 20, 16, 16, 0
END SUB
SUB Tick
    LOCAL D AS INTEGER
    D = KeyAxis(SC_LEFT, SC_RIGHT)
    IF D <> 0 THEN
        DRAW FILL X, 20, 16, 16, 8
        X = MIN(MAX(X + 4 * D, 0), 200 - 16)
        DRAW FILL X, 20, 16, 16, 0
    END IF
END SUB
SUB Keys
    IF KEYCODE = KC_HOME THEN
        DRAW FILL X, 20, 16, 16, 8
        X = 0
        DRAW FILL X, 20, 16, 16, 0
    END IF
END SUB
SUB Quit
    EXIT
END SUB
X = 92
END
```

## Used by

- `examples/jumper.pbas`, `examples/tutorial/t3_hop.pbas` (KEYDOWN through `SC_` and `KeyAxis`)
- `examples/paint2.pbas`, `examples/designer.pbas`, `examples/sprited.pbas` (`KC_` names in KEYS handlers)
- `developer-tests/timeprb.pbas`, `developer-tests/timepr4.pbas` (timing probes, through `developer-tests/timecore.pbas`)

## Limitations

- The F1 to F8, Stop and Help keys can be given to BUTTONs (`KEY F1`), but this library has no scan codes for them.
- The scan-code values are those of the keyboard Rosanne reports; only the six listed above are confirmed in XAnne.

See also: [library index](README.md), [menus, keys and mouse](../manual/11-menus-keys-mouse.md), [timers and animation](../manual/14-timers-and-animation.md), [generated reference](../LIBRARY-REFERENCE.md).
