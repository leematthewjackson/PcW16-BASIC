# 3. Expressions and built-in functions

This chapter covers operators, their precedence, integer and REAL
arithmetic, comparisons, the logical and bitwise operators, and every
built-in function. The normative text is
[LANGUAGE-SPEC.md](../../LANGUAGE-SPEC.md) §3, §3.1 and §5.3. Where the
older parts of the spec disagree with later sections (for example §3 says
there are no bitwise operators), the later sections and this chapter
describe what the compiler does.

## 3.1 Operators and precedence

**Syntax**

```text
^                        power (always REAL)
+x  -x                   sign
*  /  MOD                multiply, divide, remainder
+  -                     add, subtract; + also joins two STRINGs
=  ==  <>  <  <=  >  >=  comparisons (== is the same as =)
NOT                      logical or bitwise not
AND                      logical or bitwise and
OR                       logical or bitwise or
XOR                      logical or bitwise exclusive or
```

**Meaning:** the list runs from the tightest-binding operator to the
loosest. Operators of equal precedence group from left to right, including
`^` (`2 ^ 3 ^ 2` is `(2 ^ 3) ^ 2` = 64). Parentheses override everything.

Points that differ from other BASICs:

- `^` binds tighter than a sign: `-2 ^ 2` is −4.
- `NOT` takes in a whole comparison: `NOT A = B` means `NOT (A = B)`. Its
  operand stops at `AND`, `OR` and `XOR`, so `NOT A = B AND C` means
  `(NOT (A = B)) AND C`.
- `AND` binds tighter than `OR`, and `XOR` is the loosest of all:
  `A OR B AND C` is `A OR (B AND C)`.
- `MOD`, `AND`, `OR`, `NOT` and `XOR` are words; put spaces around them.
- There is no `\` integer-division operator: `/` on two INTEGERs already
  gives a whole number.

**Example**

```pbas
' expect-message: 11 -6 20 64 -4
DIM A AS INTEGER
A = 2 + 3 * 4 - 10 / 3
MESSAGE STR$(A) + " " + STR$(-2 * 3) + " " + STR$((2 + 3) * 4) + " " + STR$(2 ^ 3 ^ 2) + " " + STR$(-2 ^ 2)
END
```

`10 / 3` is 3, so A is 2 + 12 − 3 = 11.

**Common errors**

```pbas-error
' expect-error: unexpected character '\\'
DIM A AS INTEGER
A = 7 \ 2
END
```

**Limits:** an expression may be nested at most 100 levels deep (operators,
parentheses and calls), or `expression is nested more than 100 levels deep`.

**Evidence:** tested in XAnne (`examples/arith_demo.pbas`,
`examples/grade_report.pbas`); the precedence cases on the simulator.

**See also:** spec §3, §3.1, §5.3.

## 3.2 Integer arithmetic

**Meaning**

- `+ - *` on INTEGERs give an INTEGER and wrap silently past ±32767
  ([chapter 2](02-variables-and-types.md#22-integer-and-boolean)).
- `/` on two INTEGERs divides and **truncates toward zero**: `-7 / 2` is −3.
- `MOD` is the remainder, with the sign of the left operand: `-7 MOD 2` is
  −1 and `7 MOD -2` is 1. `A = (A / B) * B + A MOD B` always holds. `MOD`
  works on INTEGERs only.
- Division or `MOD` by a constant 0 is a compile error; by a value that turns
  out to be 0 when the program runs, `Runtime error: division by zero at line N`.
- If either operand of `+ - * /` is a REAL, the INTEGER is converted and the
  result is a REAL (§3.6).

**Example**

```pbas
' expect-message: -3 -1 1 -32768
DIM N AS INTEGER
N = 32767
MESSAGE STR$(-7 / 2) + " " + STR$(-7 MOD 2) + " " + STR$(7 MOD -2) + " " + STR$(N + 1)
END
```

**Common errors**

```pbas-error
' expect-error: division by zero
DIM A AS INTEGER
A = 5 / 0
END
```

```pbas
' expect-message: Runtime error: division by zero at line 4
DIM A AS INTEGER
DIM B AS INTEGER
A = 5 / B
END
```

Guard a division with a test (`IF B <> 0 THEN`), or with a short-circuit
`AND` (§3.4).

**Evidence:** tested in XAnne (`examples/calculator.pbas`,
`examples/char_codes.pbas`).

**See also:** spec §3.

## 3.3 Comparisons

**Meaning**

- `=` (or `==`), `<>`, `<`, `<=`, `>`, `>=` give a BOOLEAN.
- Both operands must have the same type, except that INTEGER and REAL may be
  mixed.
- STRINGs compare byte by byte in character-code order: capitals sort before
  lower case (`"Zebra" < "apple"`) and a string sorts before a longer one
  that starts with it (`"abc" < "abcd"`). For a comparison that ignores case,
  compare `UCASE$` of both sides.
- BOOLEANs may be compared with `=` and `<>` only.
- REALs compare exact values. Compare computed REALs with a tolerance:
  `ABS(A - B) < 1E-6`.

**Example**

```pbas
' expect-message: ascii order
' expect-message: same word
DIM A$ AS STRING
A$ = "Yes"
IF "Zebra" < "apple" AND "abc" < "abcd" THEN
    MESSAGE "ascii order"
END IF
IF UCASE$(A$) = "YES" THEN
    MESSAGE "same word"
END IF
END
```

**Common errors**

```pbas-error
' expect-error: comparison = requires matching types, got INTEGER and STRING
DIM A AS INTEGER
IF A = "1" THEN
    A = 0
END IF
END
```

```pbas-error
' expect-error: ordering comparisons (<, <=, >, >=) require
DIM B AS BOOLEAN
IF B < TRUE THEN
    B = FALSE
END IF
END
```

**Limits:** a computed STRING operand (a `STR$`, substring or
concatenation) may be at most 127 bytes in the worst case. Literals and
variables are compared in place, at any length.

**Evidence:** tested in XAnne (`examples/arith_demo.pbas`,
`examples/word_sort.pbas`).

**See also:** spec §3.

## 3.4 Logical operators: `NOT`, `AND`, `OR`, `XOR` on BOOLEANs

**Meaning**

- With BOOLEAN operands, `NOT`, `AND`, `OR` and `XOR` are logical and give a
  BOOLEAN.
- `AND` and `OR` **short-circuit**: in `a AND b`, `b` is not evaluated when
  `a` is FALSE; in `a OR b`, `b` is not evaluated when `a` is TRUE. So
  `IF B <> 0 AND A / B > 2 THEN` never divides by zero. (Many classic BASICs
  evaluate both sides; PcW16 BASIC does not.) `XOR` always evaluates both.
- There is no numeric truthiness: `IF N THEN` is an error; write
  `IF N <> 0 THEN`.

**Example**

```pbas
' expect-message: safe
DIM A AS INTEGER
DIM B AS INTEGER
A = 10
IF B = 0 OR A / B > 2 THEN
    MESSAGE "safe"
END IF
END
```

**A user FUNCTION on the right of `AND` or `OR`.** It is allowed, and runs
only when needed, when the `AND`/`OR` is plainly BOOLEAN: one side is a
comparison, `NOT`, `TRUE`/`FALSE` or a `FUNCTION … AS BOOLEAN`.

```pbas
' expect-message: checked
' expect-message: yes
DIM B AS BOOLEAN
FUNCTION Positive(N AS INTEGER) AS BOOLEAN
    MESSAGE "checked"
    RETURN N > 0
END FUNCTION
B = 1 > 0 AND Positive(3)
IF B THEN
    MESSAGE "yes"
END IF
B = 1 > 2 AND Positive(3)
END
```

The second `Positive(3)` is never called, so there is only one "checked".

**Common errors**

```pbas-error
' expect-error: AND requires two BOOLEAN or two INTEGER operands, got INTEGER and BOOLEAN
DIM N AS INTEGER
N = 3 AND TRUE
END
```

```pbas-error
' expect-error: is called on the right of an AND/OR that is not plainly BOOLEAN
DIM A AS INTEGER
FUNCTION F() AS INTEGER
    RETURN 1
END FUNCTION
A = 3 AND F()
END
```

Call such a FUNCTION in a separate statement first.

**Evidence:** tested in XAnne (`examples/grade_report.pbas`,
`examples/signup_form.pbas`); the FUNCTION-on-the-right rule on the
simulator.

**See also:** spec §3, §5.3.

## 3.5 Bitwise operators and shifts

**Meaning**

- With two INTEGER operands, `AND`, `OR`, `XOR` and `NOT` work on the 16 bits
  of the two's-complement value, and both operands are always evaluated:
  `12 AND 10` = 8, `12 OR 3` = 15, `12 XOR 10` = 6, `NOT 0` = −1.
- Mixing a BOOLEAN and an INTEGER is an error.
- `SHL(x, n)` and `SHR(x, n)` are *functions*, not operators: logical shifts
  left and right by n bits. n of 16 or more gives 0; a negative n stops the
  program with `Runtime error: number out of range`. `SHR` brings in zeros, so
  `SHR(-1, 1)` is 32767.

**Example**

```pbas
' expect-message: 8 15 6 -1 16 32767
MESSAGE STR$(12 AND 10) + " " + STR$(12 OR 3) + " " + STR$(12 XOR 10) + " " + STR$(NOT 0) + " " + STR$(SHL(1, 4)) + " " + STR$(SHR(-1, 1))
END
```

**Limits:** INTEGER only (no REAL operands).

**Evidence:** simulator-tested; used by programs tested in XAnne
(`examples/paint2.pbas`, `examples/sprited.pbas`, `lib/drag.pbas`).

**See also:** spec §5.3.

## 3.6 REAL arithmetic

**Meaning**

- When one operand of `+ - * /` or of a comparison is REAL and the other
  INTEGER, the INTEGER is converted to REAL first. `INTEGER / INTEGER` is
  still integer division: write `N / 2.0` for a REAL quotient.
- `^` always gives a REAL. `0 ^ 0` is 1; a negative number needs a whole
  power; `0 ^` a negative power is a division by zero.
- `+ - * /` are correctly rounded: the exact result is rounded to the
  nearest REAL, halves away from zero. (Up to M13, about 1.5% of `+` and `-`
  results lying just under half a unit in the last place were rounded the
  wrong way, by one unit. M14 corrected this; the correction is simulator
  tested and awaits the owner's XAnne retest.) A result beyond about 1.7E+38
  stops the program with `Runtime error: number out of range`; one smaller
  than about 2.9E−39 becomes 0.

**Example**

```pbas
' expect-message: 0.333333333 3.5 1E+10
DIM N AS INTEGER
N = 7
MESSAGE STR$(1 / 3.0) + " " + STR$(N / 2.0) + " " + STR$(1E5 * 1E5)
END
```

**Evidence:** tested in XAnne (`examples/scicalc.pbas`).

**See also:** spec §3.1; [chapter 2](02-variables-and-types.md#24-real).

## 3.7 Built-in functions

Arguments are checked for type when the program is built. `s` stands for a
STRING expression, `n`, `start`, `code` for INTEGER expressions, and `x`
for an INTEGER or REAL expression (an INTEGER is converted).

A built-in function without arguments may be written with or without `()`
(`IOERR` or `IOERR()`), except `PI`, which has no parentheses. This differs
from your own FUNCTIONs, which must always be called with `()`
([chapter 5](05-procedures.md#52-function)).

### Text functions

| Function | Result | Meaning |
|---|---|---|
| `LEN(s)` | INTEGER | length in bytes |
| `STR$(x)` | STRING | the decimal text of an INTEGER (no leading space) or of a REAL (9 significant digits) |
| `LEFT$(s, n)` | STRING | the first n characters (all of s if it is shorter) |
| `RIGHT$(s, n)` | STRING | the last n characters |
| `MID$(s, start, n)` | STRING | n characters from position start (1-based); a start past the end gives `""` |
| `INSTR(a, b)`, `INSTR(start, a, b)` | INTEGER | position of the first b in a at or after start (default 1), or 0; case-sensitive; an empty b is found at start |
| `VAL(s)` | INTEGER | skips leading spaces, reads an optional sign and decimal digits, stops at anything else; no digits gives 0 (`VAL("12abc")` = 12) |
| `REALVAL(s)` | REAL | like `VAL`, with a decimal point and exponent (`"1.5E3"`); uses only the first 9 significant digits (later ones are ignored, not rounded) |
| `ISNUM(s)` | BOOLEAN | TRUE if the whole of s (spaces around it allowed) is one number that `REALVAL` can read and that is in range |
| `ASC(s)` | INTEGER | code (1..255) of the first character; `ASC("")` is −1 |
| `CHR$(code)` | STRING | one character, code 1..255 |
| `UCASE$(s)`, `LCASE$(s)` | STRING | ASCII letters changed to capitals / lower case; every other byte unchanged |
| `TRIM$(s)`, `LTRIM$(s)`, `RTRIM$(s)` | STRING | s without spaces (code 32 only) at both ends / the left / the right |
| `SPACE$(n)` | STRING | n spaces |
| `STRING$(n, code)` | STRING | n copies of the character with that code (1..255) |

**Example**

```pbas
' expect-message: [] [hi] 3 1 -7 12
' expect-message: [x]***  | ABCdef ell
' expect-message: 1500 TRUE 65 A
DIM Ok$ AS STRING
MESSAGE "[" + MID$("hello", 9, 2) + "] [" + LEFT$("hi", 5) + "] " + STR$(INSTR(3, "hello", "l")) + " " + STR$(INSTR("abc", "")) + " " + STR$(VAL(" -7")) + " " + STR$(VAL("12abc"))
MESSAGE "[" + TRIM$("  x  ") + "]" + STRING$(3, 42) + SPACE$(2) + "| " + UCASE$("abc") + LCASE$("DEF") + " " + MID$("hello", 2, 3)
Ok$ = "FALSE"
IF ISNUM(" 1.5E3 ") THEN
    Ok$ = "TRUE"
END IF
MESSAGE STR$(REALVAL("1.5E3")) + " " + Ok$ + " " + STR$(ASC("A")) + " " + CHR$(65)
END
```

**Common errors and runtime errors**

- A constant count below 0, or a constant `MID$`/`INSTR` start below 1, is a
  compile error. A computed one stops the program with
  `Runtime error: substring position out of range at line N`.
- `VAL` of a number outside −32768..32767 stops the program with
  `Runtime error: number out of range at line N`; it never wraps.
- `CHR$(0)` is a compile error (a STRING cannot contain a zero byte); a
  computed code outside 1..255 is
  `Runtime error: character code out of range at line N`.
- There is no `MID$` statement: `MID$(A$, 1, 1) = "J"` gives
  `expected ), got ,`. Build the new string with `LEFT$`, `MID$` and `+`.
- There is no `HEX$` (`unknown function HEX$`), and `VAL("&HFF")` is 0.

```pbas
' expect-message: Runtime error: substring position out of range at line 4
DIM N AS INTEGER
N = -1
MESSAGE LEFT$("abc", N)
END
```

```pbas-error
' expect-error: CHR$ character code must be 1..255, got 0
MESSAGE CHR$(0)
END
```

```pbas-error
' expect-error: computed strings used by LEN are limited to 127
MESSAGE STR$(LEN(STRING$(127, 65) + "x"))
END
```

**Limits:** a computed STRING argument (not a literal or a variable) of
`LEN`, `VAL`, `ASC`, `INSTR`, `REALVAL`, `ISNUM` and the substring functions
may be at most 127 bytes; `SPACE$` and `STRING$` produce at most 127
characters. Computed strings nested inside one another use a pool of six
scratch strings; an expression needing more is a compile error ("nested too
deeply"): split it into statements.

**Evidence:** tested in XAnne (`examples/word_tools.pbas`,
`examples/number_format.pbas`, `examples/char_codes.pbas`,
`examples/text_tool.pbas`).

### Number functions

| Function | Result | Meaning |
|---|---|---|
| `ABS(x)` | type of x | absolute value; `ABS(-32768)` stays −32768 |
| `SGN(x)` | INTEGER | −1, 0 or 1 |
| `MIN(a, b)`, `MAX(a, b)` | INTEGER, or REAL if either is REAL | the smaller / larger |
| `SHL(n, k)`, `SHR(n, k)` | INTEGER | logical shift (§3.5) |
| `RND(n)` | INTEGER | a pseudo-random number from 1 to n (n ≥ 1) |
| `CINT(x)` | INTEGER | nearest whole number, halves away from zero (`CINT(-2.5)` = −3); outside −32768..32767 is `number out of range` |

`RND` uses a 16-bit generator: a program gets the same sequence every time it
runs, until it calls `RANDOMIZE`.

```text
RANDOMIZE            seed from the processor's refresh register (varies, not secure)
RANDOMIZE seed       a fixed seed (0 means 1): a repeatable sequence
```

**Example**

```pbas
' expect-message: -32768 -1 0 9 -2 -3
' expect-message: in range
DIM N AS INTEGER
MESSAGE STR$(ABS(-32768)) + " " + STR$(SGN(-5)) + " " + STR$(SGN(0)) + " " + STR$(MAX(3, 9)) + " " + STR$(MIN(-2, 4)) + " " + STR$(CINT(-2.5))
RANDOMIZE
N = RND(6)
IF N >= 1 AND N <= 6 THEN
    MESSAGE "in range"
END IF
END
```

**Common errors**

```pbas-error
' expect-error: RND(n) needs n of at least 1
MESSAGE STR$(RND(0))
END
```

`RND` without an argument is read as a variable
(`undefined variable RND; …`): write `RND(n)`.

**Evidence:** `ABS`, `SGN`, `MIN`, `MAX`, `CINT` tested in XAnne. `RND` and
`RANDOMIZE` are simulator-tested only: no example or XAnne probe uses them.

### REAL functions

The argument may be INTEGER or REAL; the result is REAL.

| Function | Meaning |
|---|---|
| `SQR(x)` | square root, x ≥ 0 |
| `EXP(x)` | e to the power x (x up to about 88) |
| `LOG(x)` | natural logarithm, x > 0 (there is no `LOG10`: use `LOG(x) / LOG(10)`) |
| `SIN(x)`, `COS(x)`, `TAN(x)` | in radians, \|x\| ≤ 51000 |
| `ATN(x)` | arctangent, −π/2..π/2 |
| `INT(x)` | the largest whole number ≤ x (`INT(-2.5)` = −3), as a REAL |
| `FIX(x)` | x with its fraction removed (`FIX(-2.5)` = −2), as a REAL |
| `REAL(n)` | n as a REAL (rarely needed: conversion is automatic) |
| `PI` | π (no parentheses) |

**Example**

```pbas
' expect-message: 3.14159265 1 2.71828183 2 -3 -2
MESSAGE STR$(ATN(1) * 4) + " " + STR$(SIN(PI / 2)) + " " + STR$(EXP(1)) + " " + STR$(LOG(EXP(2))) + " " + STR$(INT(-2.5)) + " " + STR$(FIX(-2.5))
END
```

**Runtime errors:** `SQR` of a negative number, `LOG` of 0 or a negative
number, and a negative number to a fractional power stop the program with
`Runtime error: function argument out of range at line N`; `SIN`, `COS`,
`TAN` beyond 51000 and `EXP` above about 88 with `number out of range`.

```pbas
' expect-message: Runtime error: function argument out of range at line 3
DIM X AS REAL
X = SQR(-1)
END
```

```pbas-error
' expect-error: unknown function LOG10
DIM X AS REAL
X = LOG10(100)
END
```

**Limits:** accuracy within a few units of the last binary place (relative
error at most about 4E−9 in the project's tests).

**Evidence:** tested in XAnne (`examples/scicalc.pbas`, `developer-tests/m7_edges.pbas`).

### Functions documented in other chapters

| Function | Result | Chapter |
|---|---|---|
| `EOF(channel)` | BOOLEAN | [6](06-files.md) |
| `IOERR` | INTEGER | [6](06-files.md) |
| `TEXTLINES(D)`, `TEXTLEN(D, n)`, `TEXTGET$(D, n, col, count)`, `TEXTFIND(D, s, n, col)`, `TEXTCOL(D)`, `TEXTCHANGED(D)`, `TEXTFREE(D)`, `TEXTSIZE(D)`, `TEXTSAME(D1, D2)` | see chapter | [7](07-text-buffers.md) |
| `DBFIND(A, Count, id)`, `DBNEXTID(A)`, `DBRECOVERED` | INTEGER | [8](08-records-and-databases.md) |
| `ASK(text, "b1", "b2" [, "b3"])` | INTEGER | [10](10-windows-and-controls.md) |
| `MOUSEX`, `MOUSEY`, `MOUSEEVENT`, `KEYCODE`, `KEYSHIFT` | INTEGER | [11](11-menus-keys-mouse.md) |
| `KEYDOWN(code)` | BOOLEAN | [11](11-menus-keys-mouse.md) |
| `TEXTWIDTH(s)` | INTEGER | [12](12-drawing.md) |
| `POINT(x, y)`, `BITMAPW(B)`, `BITMAPH(B)` | INTEGER | [13](13-bitmaps-and-sprites.md) |
| `SECONDS`, `CLOCKTICKS` | INTEGER | [14](14-timers-and-animation.md) |
| `PAGEWIDTH(s)` | INTEGER | [15](15-printing.md) |

There is no `PEEK`, `USR`, `INKEY$`, `DATE$`, `TIME$`, `TIMER` function,
`HEX$` or `LOG10`; see [chapter 17](17-unsupported.md).

**See also:** spec §3, §3.1, §5.3; `examples/scicalc.pbas`.
