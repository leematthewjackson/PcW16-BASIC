# 5. Procedures: SUB, FUNCTION, CALL and LOCAL

A program is divided into procedures: a `SUB` does something and is run with
`CALL`; a `FUNCTION` computes a value and is used in an expression. Both may
take typed parameters and have `LOCAL` variables. Procedures use static
storage, so **recursion is not supported**. The normative text is
[LANGUAGE-SPEC.md](../../LANGUAGE-SPEC.md) §5 and §5.3 (the older
statements in §5 and §6 that procedures have "no arguments" and "no local
variables" are out of date).

## 5.1 `SUB` and `CALL`

**Syntax**

```text
SUB Name
    statements
END SUB

SUB Name(Param AS type, Text$, ...)
    statements
END SUB

CALL Name
CALL Name()
CALL Name(argument, ...)
```

**Meaning**

- `SUB … END SUB` defines a procedure. It may be written anywhere at the top
  level before the final `END`, before or after the `CALL`s that use it.
- `CALL Name(…)` runs it and then continues with the next statement.
  Reaching `END SUB` (or `EXIT SUB`) returns.
- `CALL` is required: a SUB cannot be run by writing its name alone.
- Each parameter is `Name AS type`, where type is `INTEGER`, `BOOLEAN`,
  `REAL`, `STRING`, a TYPE name ([chapter 8](08-records-and-databases.md)) or
  `BITMAP` ([chapter 13](13-bitmaps-and-sprites.md)). A name ending in `$`
  without `AS` is a STRING.
- The arguments must match the parameters in number and type (an INTEGER
  may be given for a REAL parameter).
- A SUB used as an event handler (a `BUTTON`, `ITEM`, `TIMER`, `CHANGE`,
  `ACTION`, `PAINT`, `MOUSE` or `KEYS` handler) must have no parameters
  ([chapter 10](10-windows-and-controls.md)).

**Requires:** nothing.

**Example**

```pbas
' expect-message: Total: 5
DIM Total AS INTEGER
SUB Add(N AS INTEGER)
    Total = Total + N
END SUB
SUB Report
    MESSAGE "Total: " + STR$(Total)
END SUB
CALL Add(2)
CALL Add(3)
CALL Report
END
```

**Common errors**

```pbas-error
' expect-error: expected =, got 3
SUB Twice(N AS INTEGER)
    MESSAGE STR$(N * 2)
END SUB
Twice 3
END
```

```pbas-error
' expect-error: CALL NOPE: no SUB NOPE is defined
CALL Nope
END
```

```pbas-error
' expect-error: cannot assign STRING to INTEGER variable N (in S)
SUB S(N AS INTEGER)
END SUB
CALL S("x")
END
```

```pbas-error
' expect-error: S expects 1 argument, got 2
SUB S(N AS INTEGER)
END SUB
CALL S(1, 2)
END
```

```pbas-error
' expect-error: parameter N needs a type: N AS INTEGER
SUB S(N)
END SUB
END
```

Other messages: `CALL Twice 3` gives `expected NEWLINE, got 3`; `duplicate
subroutine TWICE` for a second definition; `S is both a SUB and a variable`;
`SUB/FUNCTION must be top-level (missing END SUB or END FUNCTION?)` for a
SUB inside another; `CALL 32768` (machine code) gives `expected IDENT, got
32768`.

**Limits:** at most 16 procedures active at once (§5.7); no recursion; no
array parameters; no `BYREF` or `BYVAL` (§5.3).

**Evidence:** tested in XAnne (`examples/grade_report.pbas`,
`examples/signup_form.pbas`; parameters in every application).

**See also:** spec §5, §5.3; `examples/grade_report.pbas`.

## 5.2 `FUNCTION`

**Syntax**

```text
FUNCTION Name(Param AS type, ...) AS type
    statements
    RETURN expression
END FUNCTION

FUNCTION Name() AS type          no parameters
FUNCTION Name AS type            the same: () may be left out here

... Name(arguments) ...          a call, inside an expression
... Name() ...                   a call without arguments: () is required
```

**Meaning**

- The result type is `INTEGER`, `BOOLEAN`, `REAL`, `STRING` or a TYPE
  name. A STRING result has the program-wide capacity.
- `RETURN expression` sets the result and leaves the function at once.
  A function that ends (or `EXIT FUNCTION`s) without `RETURN` returns 0,
  `""`, `FALSE`, 0.0 or an all-zero record.
- Calls in a statement run before the statement itself, left to right,
  innermost first. A call on the right of `AND`/`OR` is made only when
  needed ([chapter 3](03-expressions-and-functions.md#34-logical-operators-not-and-or-xor-on-booleans)).
- **A FUNCTION without parameters must be called with `()`**: `X = F()`.
  Without them, `F` is read as a variable. This is easy to miss because the
  declaration may leave the `()` out (`FUNCTION HandleOn AS BOOLEAN` in
  `lib/handles.pbas` is called as `HandleOn()`), and because built-in
  functions without arguments (`IOERR`, `SECONDS`) need no `()`.
- A FUNCTION cannot be run with `CALL`, and a SUB cannot be used in an
  expression.
- A FUNCTION that returns a record must be assigned to a record variable
  before you use a field of the result.

**Requires:** nothing.

**Example**

```pbas
' expect-message: 14 abab 0 8
FUNCTION Twice(N AS INTEGER) AS INTEGER
    RETURN N * 2
END FUNCTION
FUNCTION Double$(S$) AS STRING
    RETURN S$ + S$
END FUNCTION
FUNCTION Half(N AS INTEGER) AS INTEGER
    IF N < 0 THEN
        EXIT FUNCTION
    END IF
    RETURN N / 2
END FUNCTION
FUNCTION Seven AS INTEGER
    RETURN 7
END FUNCTION
MESSAGE STR$(Twice(Seven())) + " " + Double$("ab") + " " + STR$(Half(-1)) + " " + STR$(Half(16))
END
```

**Common errors**

```pbas-error
' expect-error: F is a FUNCTION: call it as F() (with parentheses, even when it takes no arguments)
DIM X AS INTEGER
FUNCTION F() AS INTEGER
    RETURN 1
END FUNCTION
X = F
END
```

```pbas-error
' expect-error: F is a FUNCTION: use its value in an expression
FUNCTION F() AS INTEGER
    RETURN 1
END FUNCTION
CALL F()
END
```

```pbas-error
' expect-error: S is a SUB: use CALL S
SUB S
END SUB
DIM A AS INTEGER
A = S()
END
```

```pbas-error
' expect-error: RETURN is only allowed inside a FUNCTION
SUB S
    RETURN 1
END SUB
END
```

```pbas-error
' expect-error: is not a record, so it has no field X
TYPE Pt
    X AS INTEGER
END TYPE
FUNCTION Make() AS Pt
    LOCAL T AS Pt
    RETURN T
END FUNCTION
MESSAGE STR$(Make().X)
END
```

**Limits**

- No recursion, direct or indirect (§5.7).
- `CASE` values may not call a FUNCTION.
- Every call site of a FUNCTION returning a STRING costs a string cell of the
  16K block (known issue KI-83, [limitations](../limitations.md)); in a
  large program, prefer a SUB that sets a global STRING.

**Evidence:** tested in XAnne (most applications from `examples/journal.pbas`
and `examples/scicalc.pbas` on).

**See also:** spec §5.3; `examples/scicalc.pbas`, `examples/contacts4.pbas`.

## 5.3 Parameters

**Meaning**

- Parameters are passed **by value**: the procedure gets a copy, and changing
  a parameter does not change the caller's variable. This includes records.
- The one exception is a `BITMAP` parameter, which refers to the caller's
  bitmap ([chapter 13](13-bitmaps-and-sprites.md)).
- A STRING parameter has the program-wide capacity (63 characters by
  default); a longer argument is `Runtime error: string too long` at the
  `CALL`. Each STRING parameter takes its whole capacity in the 16K block.
- A parameter with the same name as a global variable or a CONST hides it
  inside the procedure.
- To give a result back, use a FUNCTION, or set a global variable.
- There is no `BYREF` or `BYVAL` keyword and no array parameter.

**Example**

```pbas
' expect-message: inside: 2
' expect-message: outside: 1
DIM K AS INTEGER
SUB Bump(K AS INTEGER)
    K = K + 1
    MESSAGE "inside: " + STR$(K)
END SUB
K = 1
CALL Bump(K)
MESSAGE "outside: " + STR$(K)
END
```

**Common errors**

```pbas-error
' expect-error: parameter BYREF needs a type
SUB S(BYREF A AS INTEGER)
END SUB
END
```

```pbas-error
' expect-error: parameter X needs a type: X AS INTEGER
SUB S(X() AS INTEGER)
END SUB
END
```

The messages read `BYREF` and `X` as parameter names: the words do not
exist. To work on an array, make it global and pass an index.

**Evidence:** tested in XAnne (applications); copy semantics on the
simulator.

**See also:** spec §5.3, §5.8 (record parameters), §5.14 (BITMAP parameters).

## 5.4 `LOCAL`

**Syntax**

```text
LOCAL Name AS INTEGER | BOOLEAN | REAL | STRING | TypeName
```

**Meaning:** inside a SUB or FUNCTION, declares a variable visible only
there. It is reset to 0, `FALSE`, `""` or an all-zero record **every time the
procedure starts**; it does not keep its value between calls. A LOCAL hides
a global or a CONST of the same name inside the procedure.

**Requires:** a SUB or FUNCTION around it.

**Example**

```pbas
' expect-message: 1
' expect-message: 1
' expect-message: global: 5
DIM C AS INTEGER
SUB Count
    LOCAL C AS INTEGER
    C = C + 1
    MESSAGE STR$(C)
END SUB
C = 5
CALL Count
CALL Count
MESSAGE "global: " + STR$(C)
END
```

**Common errors**

```pbas-error
' expect-error: LOCAL arrays are not supported; declare the array with DIM
SUB S
    LOCAL A(3) AS INTEGER
END SUB
END
```

**Limits:** no LOCAL arrays and no `STRING * n` on a LOCAL. Locals use
static storage like parameters (one copy per procedure), which is why
recursion is not allowed.

**Evidence:** tested in XAnne (`developer-tests/m7_edges.pbas` and applications).

**See also:** spec §5.3.

## 5.5 `EXIT SUB`, `EXIT FUNCTION` and `RETURN`

**Syntax**

```text
EXIT SUB                 leave the SUB now
EXIT FUNCTION            leave the FUNCTION now, with its default result
RETURN expression        leave the FUNCTION now, with this result
```

**Meaning:** each leaves the current procedure at once and goes back to the
caller (or, for a handler, back to waiting for events). `EXIT` alone ends the
whole program ([chapter 4](04-control-flow.md#47-exit)).

**Example**

```pbas
' expect-message: checking 0
' expect-message: checking 5
' expect-message: 5 is fine
SUB Check(N AS INTEGER)
    MESSAGE "checking " + STR$(N)
    IF N <= 0 THEN
        EXIT SUB
    END IF
    MESSAGE STR$(N) + " is fine"
END SUB
CALL Check(0)
CALL Check(5)
END
```

**Common errors**

```pbas-error
' expect-error: EXIT SUB is only allowed inside a SUB
EXIT SUB
END
```

**Evidence:** `EXIT SUB` tested in XAnne (`examples/signup_form.pbas`);
`EXIT FUNCTION` compiled and simulator-tested.

## 5.6 `DIM` inside a procedure declares a global

This surprises people coming from other BASICs. A `DIM` inside a SUB or
FUNCTION declares an ordinary **global** variable: it keeps its value after
the procedure returns, it is visible everywhere, and the same `DIM` in two
procedures is a duplicate declaration. The compiler warns about each such
`DIM`: `warning: DIM T inside S declares a variable for the whole program (it
keeps its value between calls); use LOCAL T AS ... for one that belongs to
this procedure`.

```pbas
' expect-message: 5
SUB S
    DIM T AS INTEGER
    T = 5
END SUB
CALL S
MESSAGE STR$(T)
END
```

```pbas-error
' expect-error: duplicate declaration of T
SUB A
    DIM T AS INTEGER
END SUB
SUB B
    DIM T AS INTEGER
END SUB
END
```

**Workaround:** use `LOCAL` for a variable that belongs to one procedure;
keep `DIM` at the top of the program (or of a library) for globals. Arrays
must be global: declare them with `DIM` at the top level.

## 5.7 Recursion and call depth

- A procedure may not call itself, directly or through others. The compiler
  reports the cycle.
- At most 16 procedures may be active at once (counting a handler, or the
  first procedure the main line calls). The compiler checks every chain.

```pbas-error
' expect-error: recursive CALL is not allowed: S -> T -> S
SUB S
    CALL T
END SUB
SUB T
    CALL S
END SUB
END
```

```pbas-error
' expect-error: recursive CALL is not allowed: F -> F
FUNCTION F(N AS INTEGER) AS INTEGER
    IF N <= 1 THEN
        RETURN 1
    END IF
    RETURN N * F(N - 1)
END FUNCTION
MESSAGE STR$(F(5))
END
```

**Workaround:** write the algorithm with a loop, and keep any stack of
pending work in a global array:

```pbas
' expect-message: 120
FUNCTION Factorial(N AS INTEGER) AS INTEGER
    LOCAL R AS INTEGER
    LOCAL I AS INTEGER
    R = 1
    FOR I = 2 TO N
        R = R * I
    NEXT I
    RETURN R
END FUNCTION
MESSAGE STR$(Factorial(5))
END
```

A chain that is too deep gives, for example, `CALL S17 makes a chain of more
than 16 procedures active at once (from SUB S1); at most 16 are allowed`.

## 5.8 A FUNCTION may not take a built-in's name

A FUNCTION may not have the name of a built-in function (§3.7 lists them
all). Names do not depend on upper or lower case, so `Len` is `LEN`. This
holds in a library the program includes, too:

```pbas-error
' expect-error: LEN is a built-in function, so a FUNCTION cannot have that name
FUNCTION Len(S$) AS INTEGER
    RETURN 99
END FUNCTION
MESSAGE STR$(LEN("abc"))
END
```

(Up to M13 such a FUNCTION silently replaced the built-in everywhere.)

Related rules:

- A CONST may not have the name of a built-in that takes no arguments
  (`PI`, `SECONDS`, `CLOCKTICKS`, `IOERR`, `MOUSEX`, `MOUSEY`, `MOUSEEVENT`,
  `KEYCODE`, `KEYSHIFT`, `DBRECOVERED`): `PI is a built-in function, so a
  CONST cannot have that name: choose another name`.
- A variable, parameter or LOCAL with one of those names is allowed, but it
  hides the built-in where it is visible, and the compiler warns: `warning:
  SECONDS is also a built-in function: inside S, SECONDS means this parameter
  or LOCAL, not the built-in (choose another name to use both)`.
- A SUB may have a built-in function's name, with no warning, but the
  built-in can then not be used in the program: `LEN("abc")` is refused with
  `LEN is a SUB: use CALL LEN(…) as a statement`.

Give your own procedures names of their own. Give library procedures a
prefix, as the shipped libraries do (`GeomClamp`, `AppSay`, `SpriteMove`).

**Evidence:** compiler.

## 5.9 Handlers

A handler is a SUB without parameters that the program names in a `BUTTON`,
`ITEM`, `TIMER`, `LIST`/`CHOICE`/`SLIDER` (`CHANGE`, `ACTION`) or `CANVAS`
(`PAINT`, `MOUSE`, `KEYS`) declaration. It runs when that event happens; the
values of bound controls move into their variables before it runs and back to
the screen after it returns. See [chapter 10](10-windows-and-controls.md),
[chapter 11](11-menus-keys-mouse.md) and
[chapter 14](14-timers-and-animation.md).

```pbas-error
' expect-error: GO cannot be an event handler: handlers are SUBs without parameters
WINDOW "W"
BUTTON "Go", Go
SUB Go(N AS INTEGER)
END SUB
END
```

**See also:** spec §5, §5.1, §5.3.
