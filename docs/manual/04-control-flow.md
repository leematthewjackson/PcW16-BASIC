# 4. Control flow

PcW16 BASIC has block `IF`, `SELECT CASE`, `FOR … NEXT` and `WHILE … WEND`,
with `EXIT` forms to leave them early. There is no `GOTO`, `GOSUB`, `DO`
loop, `REPEAT`, `ELSEIF` or single-line `IF`
([chapter 17](17-unsupported.md)). The normative text is
[LANGUAGE-SPEC.md](../../LANGUAGE-SPEC.md) §5, §5.3 and §6.

Every condition is a BOOLEAN expression: a comparison, a BOOLEAN variable,
`TRUE`/`FALSE`, a `FUNCTION … AS BOOLEAN`, or these combined with `NOT`,
`AND`, `OR` and `XOR` ([chapter 3](03-expressions-and-functions.md#34-logical-operators-not-and-or-xor-on-booleans)).

## 4.1 `IF … THEN … ELSE … END IF`

**Syntax**

```text
IF condition THEN
    statements
[ELSE
    statements]
END IF
```

**Meaning:** runs the first group of statements when the condition is TRUE,
otherwise the `ELSE` group, if there is one. Only the block form exists:
`THEN` ends its line, and `END IF` is two words. For a chain of tests, put
another `IF` inside the `ELSE` (or use `SELECT CASE`, §4.2).

**Requires:** nothing.

**Example**

```pbas
' expect-message: two
DIM A AS INTEGER
A = 2
IF A = 1 THEN
    MESSAGE "one"
ELSE
    IF A = 2 THEN
        MESSAGE "two"
    ELSE
        MESSAGE "other"
    END IF
END IF
END
```

**Common errors**

```pbas-error
' expect-error: IF requires BOOLEAN condition, got INTEGER
DIM A AS INTEGER
IF A THEN
    A = 0
END IF
END
```

```pbas-error
' expect-error: expected NEWLINE, got A
DIM A AS INTEGER
IF A = 0 THEN A = 1
END
```

```pbas-error
' expect-error: expected NEWLINE, got IF
DIM A AS INTEGER
IF A = 1 THEN
    A = 0
ELSE IF A = 2 THEN
    A = 0
END IF
END
```

`ELSEIF` gives `expected =, got A`, `ENDIF` gives `expected =, got NEWLINE`,
and two `ELSE`s give `multiple ELSE clauses for one IF`.

**Limits:** blocks of all kinds nest at most 64 deep.

**Evidence:** tested in XAnne (`examples/branch_menu.pbas`).

**See also:** spec §6; `examples/branch_menu.pbas`.

## 4.2 `SELECT CASE`

**Syntax**

```text
SELECT CASE expression
CASE value [, value ...]          equal to any of the values
CASE low TO high                  within the range, inclusive
CASE IS op value                  op is =, <>, <, <=, > or >=
CASE ELSE                         optional, last
END SELECT
```

The three kinds of item may be mixed in one `CASE` line, separated by
commas.

**Meaning:** the expression is evaluated once. The first `CASE` that
matches runs, and only that one; there is no fall-through. `CASE ELSE` runs
if nothing matched. If nothing matches and there is no `CASE ELSE`, nothing
happens. The expression may be INTEGER, STRING or REAL; every CASE value
must have its type.

**Requires:** nothing.

**Example**

```pbas
' expect-message: fruit
' expect-message: odd
' expect-message: high
DIM S$ AS STRING
DIM A AS INTEGER
DIM X AS REAL
S$ = "pear"
SELECT CASE S$
CASE "apple", "pear"
    MESSAGE "fruit"
CASE ELSE
    MESSAGE "other"
END SELECT
A = 7
SELECT CASE A
CASE 1, 3, 5, 7, 9
    MESSAGE "odd"
CASE 7
    MESSAGE "never reached"
END SELECT
X = 2.5
SELECT CASE X
CASE 0 TO 2.4
    MESSAGE "low"
CASE IS > 2.4
    MESSAGE "high"
END SELECT
END
```

**Common errors**

```pbas-error
' expect-error: comparison = requires matching types, got INTEGER and STRING
DIM A AS INTEGER
SELECT CASE A
CASE "x"
    A = 1
END SELECT
END
```

```pbas-error
' expect-error: CASE values may not call a FUNCTION
DIM A AS INTEGER
FUNCTION F() AS INTEGER
    RETURN 1
END FUNCTION
SELECT CASE A
CASE F()
    A = 2
END SELECT
END
```

Compute such a value into a variable before the `SELECT CASE`. A `CONST` is
a fine CASE value.

**No statements before the first `CASE`.** Nothing may stand between
`SELECT CASE` and its first `CASE`. (Up to M13 the compiler accepted such
statements; since M14 they are a compile error, as the specification says.)

```pbas-error
' expect-error: a statement between SELECT CASE (line 4) and its first CASE
DIM A AS INTEGER
A = 1
SELECT CASE A
A = 2
CASE 1
    MESSAGE "one"
END SELECT
END
```

**Evidence:** tested in XAnne (used by most applications, for example
`examples/scicalc.pbas` and `examples/mdedit4.pbas`); the error before the
first CASE on the compiler.

**See also:** spec §5.3; `examples/scicalc.pbas`, `examples/gfxbench.pbas`.

## 4.3 `FOR … NEXT`

**Syntax**

```text
FOR counter = first TO last [STEP step]
    statements
NEXT [counter]
```

**Meaning**

- The counter takes the values first, first + step, … as long as it has not
  passed last. `first` and `last` are evaluated once, before the loop;
  changing a variable used in them does not change the number of passes.
- The step is 1 by default. A negative step counts down.
- If first is already past last, the body does not run at all.
- The counter **keeps the last value the loop gave it**: after
  `FOR I = 1 TO 5`, I is 5 (not 6); after a loop that did not run, I is
  first. The counter never wraps: `FOR I = 32760 TO 32767 STEP 4` runs 32760
  and 32764 and stops.
- Assigning to the counter inside the loop is allowed and changes the next
  value.
- `NEXT` may name the counter; if it does, the name is checked.

**Requires:** the counter is an INTEGER variable declared with `DIM` (a
`LOCAL` or a parameter also works inside a procedure). The step is a
non-zero INTEGER literal or `CONST`.

**Example**

```pbas
' expect-message: 1 5 9 after: 9
' expect-message: 10 8 6 4 2
' expect-message: zero passes: 1
CONST DOWN = -2
DIM I AS INTEGER
DIM T$ AS STRING
FOR I = 1 TO 10 STEP 4
    T$ = T$ + STR$(I) + " "
NEXT I
MESSAGE T$ + "after: " + STR$(I)
T$ = ""
FOR I = 10 TO 1 STEP DOWN
    T$ = T$ + " " + STR$(I)
NEXT
MESSAGE LTRIM$(T$)
FOR I = 1 TO 0
    MESSAGE "never"
NEXT I
MESSAGE "zero passes: " + STR$(I)
END
```

**Common errors**

```pbas-error
' expect-error: STEP must be a non-zero INTEGER constant (a literal or CONST)
DIM I AS INTEGER
DIM S AS INTEGER
S = 2
FOR I = 1 TO 9 STEP S
NEXT I
END
```

```pbas-error
' expect-error: FOR counter X must be INTEGER
DIM X AS REAL
FOR X = 1 TO 3
NEXT X
END
```

```pbas-error
' expect-error: FOR counter I must be declared with DIM
FOR I = 1 TO 3
NEXT I
END
```

```pbas-error
' expect-error: nested FOR reuses active counter I
DIM I AS INTEGER
FOR I = 1 TO 3
    FOR I = 1 TO 2
    NEXT I
NEXT I
END
```

Mismatched `NEXT` names give `NEXT I does not match FOR J`; a `NEXT` with no
`FOR`, `NEXT without matching FOR`.

**Limits:** INTEGER counters only; a constant step; for a REAL sequence, run
an INTEGER counter and compute the REAL from it.

**Evidence:** tested in XAnne (`examples/for_walk.pbas`; `STEP` with other
values in `examples/countdown.pbas` and later applications).

**See also:** spec §5.3, §6; `examples/for_walk.pbas`,
`examples/mixed_work.pbas`.

## 4.4 `WHILE … WEND`

**Syntax**

```text
WHILE condition
    statements
WEND
```

**Meaning:** tests the condition before every pass and stops when it is
FALSE, so the body may run zero times. If the condition calls a FUNCTION,
the call is made again before every test. Only `WEND` closes the loop.

**Requires:** a BOOLEAN condition.

**Example**

```pbas
' expect-message: 1 2 4 8 16 32 64
DIM N AS INTEGER
DIM T$ AS STRING
N = 1
WHILE N < 100
    T$ = T$ + " " + STR$(N)
    N = N * 2
WEND
MESSAGE LTRIM$(T$)
END
```

**Common errors**

```pbas-error
' expect-error: expected NEWLINE, got WHILE
DIM I AS INTEGER
WHILE I < 3
    I = I + 1
END WHILE
END
```

```pbas-error
' expect-error: WHILE requires BOOLEAN condition
WHILE 1
WEND
END
```

Use `WHILE TRUE` with `EXIT WHILE` for a loop that tests in the middle.
`DO … LOOP` and `REPEAT … UNTIL` do not exist ([chapter 17](17-unsupported.md)).

**Limits:** a WHILE loop in a window program holds up the window until it
ends: keep long work short, or spread it over `TIMER` events
([chapter 14](14-timers-and-animation.md)).

**Evidence:** tested in XAnne (`examples/while_wait.pbas`).

**See also:** spec §6; `examples/while_wait.pbas`.

## 4.5 `EXIT FOR` and `EXIT WHILE`

**Syntax**

```text
EXIT FOR
EXIT WHILE
```

**Meaning:** leaves the innermost enclosing `FOR` (or `WHILE`) loop at once
and continues after its `NEXT` (or `WEND`). The loop must be in the same
procedure. After `EXIT FOR`, the counter keeps the value it had.

**Example**

```pbas
' expect-message: 5 3
DIM I AS INTEGER
DIM N AS INTEGER
WHILE TRUE
    N = N + 1
    IF N = 5 THEN
        EXIT WHILE
    END IF
WEND
FOR I = 1 TO 10
    IF I = 3 THEN
        EXIT FOR
    END IF
NEXT I
MESSAGE STR$(N) + " " + STR$(I)
END
```

**Common errors**

```pbas-error
' expect-error: EXIT WHILE is only allowed inside a WHILE loop
DIM I AS INTEGER
FOR I = 1 TO 3
    EXIT WHILE
NEXT I
END
```

`EXIT DO` gives `expected NEWLINE, got DO`.

**Evidence:** `EXIT WHILE` tested in XAnne (`examples/records_m8.pbas`,
`examples/mdedit4.pbas`); `EXIT FOR` compiled and simulator-tested.

**See also:** spec §5.3.

## 4.6 `EXIT SUB` and `EXIT FUNCTION`

`EXIT SUB` returns from the current SUB at once, exactly as if `END SUB` had
been reached. `EXIT FUNCTION` returns from the current FUNCTION with its
default result (0, `""`, `FALSE`, 0.0, or an all-zero record); `RETURN value`
returns a value and leaves at once. Both are described with procedures in
[chapter 5](05-procedures.md#55-exit-sub-exit-function-and-return).

## 4.7 `EXIT`

**Syntax**

```text
EXIT
```

**Meaning:** ends the whole program wherever it runs: in the main line, in
a handler or in a procedure at any depth. An open window is removed and
open files are closed. In a window program, a **Quit** button's handler is
normally just `EXIT`.

**Example**

```pbas
' expect-message: before
MESSAGE "before"
EXIT
MESSAGE "never shown"
END
```

**Evidence:** tested in XAnne (every window example has a Quit handler).

**See also:** spec §5; [chapter 10](10-windows-and-controls.md).

## 4.8 Nesting

- Blocks (`IF`, `FOR`, `WHILE` and procedures) nest at most 64 deep: `blocks are nested more than 64 levels deep`.
- Every block must be closed before `END`
  (`END inside an unclosed block`) and before the file ends
  (`unclosed IF block`, `unclosed FOR block`, …).
- A closing word must match the innermost open block: `END IF without
  matching IF`, `WEND without matching WHILE`, `NEXT without matching FOR`.
- `WINDOW`, controls, `MENU`, `TYPE`, `CONST` and `SUB`/`FUNCTION`
  definitions are allowed only at the top level, not inside a block.
