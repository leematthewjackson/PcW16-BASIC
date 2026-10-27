# 2. Variables and types

PcW16 BASIC is statically typed: every variable is declared with a type, and
the compiler checks every assignment and expression against it. There is no
implicit declaration and no implicit conversion between text and numbers.
The normative text is [LANGUAGE-SPEC.md](../../LANGUAGE-SPEC.md) §2, §3.1,
§4, §5.2, §5.3 (CONST) and §5.4.

| Type | Holds | Size | Starts as |
|---|---|---|---|
| `INTEGER` | whole numbers −32768..32767 | 2 bytes | 0 |
| `BOOLEAN` | `TRUE` or `FALSE` | 2 bytes | `FALSE` |
| `REAL` | floating point, about 9.6 significant digits, up to about ±1.7E+38 | 5 bytes | 0 |
| `STRING` | text of fixed capacity (63 characters by default) | capacity bytes | `""` |
| `STRING * n` | text of at most n characters (1..126) | n + 1 bytes | `""` |
| a `TYPE` name | a record | sum of its fields | all fields zero / empty: [chapter 8](08-records-and-databases.md) |
| `TEXT * bytes` | a text document buffer | outside the 16K block | empty: [chapter 7](07-text-buffers.md) |
| `BITMAP * w, h` | a black-and-white picture | outside the 16K block | white: [chapter 13](13-bitmaps-and-sprites.md) |

There is no `DOUBLE`, `LONG`, `SINGLE` or `BYTE` type and no `%`, `!` or `#`
type suffix ([chapter 17](17-unsupported.md)).

## 2.1 `DIM`

**Syntax**

```text
DIM Name AS INTEGER | BOOLEAN | REAL | STRING
DIM Name$ AS STRING * n
DIM Name(n) AS type [* n] [BANKED]
```

**Meaning**

- `DIM` declares one variable per line. Every `DIM` declares a **global**
  variable, visible everywhere in the program — even a `DIM` written inside a
  `SUB` or `FUNCTION` ([chapter 5](05-procedures.md#56-dim-inside-a-procedure-declares-a-global)).
  The compiler warns about a `DIM` inside a procedure. Use `LOCAL` for a
  variable that belongs to one procedure.
- The compiler collects declarations from the whole program, so a `DIM` does
  not have to come before the first use: a declaration applies to the whole
  program, wherever it is written. Put declarations at the top anyway;
  it is easier to read, and some declarations (`STRING * n` before a
  `TEXTBOX`) must come first.
- A name ending in `$` must be a STRING. A STRING may also have a name
  without `$`.
- A `TEXTBOX`, `LABEL`, `CHECKBOX`, `RADIO`, `NUMBERBOX`, `LIST`, `CHOICE`,
  `SLIDER` or menu `TICK` declares the variable it is bound to if no `DIM`
  did ([chapter 10](10-windows-and-controls.md)). Nothing else declares a
  variable.

**Requires:** nothing.

**Example**

```pbas
' expect-message: 0 FALSE "" 0
DIM Count AS INTEGER
DIM Done AS BOOLEAN
DIM Name$ AS STRING
DIM Price AS REAL
DIM Shown$ AS STRING
Shown$ = "FALSE"
IF Done THEN
    Shown$ = "TRUE"
END IF
MESSAGE STR$(Count) + " " + Shown$ + " """ + Name$ + """ " + STR$(Price)
END
```

**Common errors**

```pbas-error
' expect-error: undefined variable TOTAL; declare it with DIM or a UI binding
Total = 1
END
```

```pbas-error
' expect-error: duplicate declaration of A
DIM A AS INTEGER
DIM A AS INTEGER
END
```

```pbas-error
' expect-error: N$ uses $ suffix but is declared INTEGER; expected STRING
DIM N$ AS INTEGER
END
```

A `DIM` without a type (`DIM A`) gives `expected AS, got NEWLINE`; several
names on one line (`DIM A AS INTEGER, B AS INTEGER`) give
`expected NEWLINE, got ,`.

**Evidence:** tested in XAnne (every example).

**See also:** spec §4; `examples/mixed_work.pbas`.

## 2.2 `INTEGER` and `BOOLEAN`

**Meaning**

- An `INTEGER` is a signed 16-bit whole number, −32768..32767. `+`, `-` and
  `*` **wrap** without an error: `32767 + 1` is −32768. Division and `MOD` are
  described in [chapter 3](03-expressions-and-functions.md).
- An integer literal is written in decimal, 0..32767, with a leading `-` for
  a negative value (so `-32768` can be written). There are no hexadecimal or
  octal literals.
- A `BOOLEAN` is `TRUE` or `FALSE`. A comparison gives a BOOLEAN, and you can
  store it: `Big = N > 100`. A BOOLEAN is not a number: `IF N THEN` is an
  error, and `STR$` does not accept a BOOLEAN.

**Example**

```pbas
' expect-message: -32768
' expect-message: big
DIM N AS INTEGER
DIM Big AS BOOLEAN
N = 32767
N = N + 1
MESSAGE STR$(N)
Big = N < 0
IF Big THEN
    MESSAGE "big"
END IF
END
```

**Common errors**

```pbas-error
' expect-error: integer literal 32768 is outside the range 0..32767
DIM N AS INTEGER
N = 32768
END
```

```pbas-error
' expect-error: IF requires BOOLEAN condition, got INTEGER
DIM N AS INTEGER
IF N THEN
    N = 0
END IF
END
```

```pbas-error
' expect-error: STR$ expects a number (INTEGER or REAL)
DIM B AS BOOLEAN
MESSAGE STR$(B)
END
```

**Limits:** no overflow trap on `+ - *`; use REAL for larger values.

**Evidence:** tested in XAnne (`examples/arith_demo.pbas`); the wrap was
checked on the simulator.

**See also:** spec §2; [chapter 3](03-expressions-and-functions.md).

## 2.3 `STRING` and `STRING * n`

**Syntax**

```text
DIM S$ AS STRING              program-wide capacity (64 bytes: 63 characters)
DIM S$ AS STRING * n          its own capacity: n characters, 1..126
DIM A$(k) AS STRING * n       every element n characters
```

**Meaning**

- A STRING has a fixed **capacity**, decided when the program is built. A
  string of capacity C bytes holds at most C − 1 characters (one byte ends
  the text).
- The program-wide capacity is 64 bytes (63 characters). Change it for the
  whole program with the build option `--string-capacity N`, N from 2 to 127
  bytes ([chapter 16](16-building-and-commands.md)). Every STRING without
  `* n` — including parameters, locals and FUNCTION results — has this
  capacity.
- `STRING * n` gives one variable or array its own capacity of n
  characters. Use it to save memory (a 24-character name costs 25 bytes
  instead of 64) and to allow up to 126 characters.
- **Nothing is ever cut short.** A value that certainly does not fit is a
  compile error; one that only might not fit is checked when the program runs
  and stops it with `Runtime error: string too long at line N`
  ([chapter 9](09-errors-and-diagnostics.md)).
- Assigning to a string from an expression that reads the same string is
  safe: `S$ = "<" + S$ + ">"` works as if the right side were worked out
  first.
- Text is bytes. A literal in the source is UTF-8; keep text that reaches
  the screen to plain ASCII.

**Requires:** nothing. A `* n` must be on the `DIM`, and that `DIM` must
come before any `TEXTBOX` or `LABEL` that names the variable.

**Example**

```pbas
' expect-message: [Ada] 3
DIM Name$ AS STRING * 10
Name$ = "Ada"
Name$ = "[" + Name$ + "]"
MESSAGE Name$ + " " + STR$(LEN(Name$) - 2)
END
```

**Example: a runtime overflow**

```pbas
' expect-message: Runtime error: string too long at line 5
DIM S$ AS STRING * 3
DIM N AS INTEGER
N = 12345
S$ = STR$(N)
END
```

**Common errors**

```pbas-error
' expect-error: cannot assign a 13-character literal to S$ with capacity 6
DIM S$ AS STRING * 5
S$ = "too long text"
END
```

```pbas-error
' expect-error: STRING * n holds 1 to 126 characters, got 127
DIM S$ AS STRING * 127
END
```

`--string-capacity 128` is refused with `string capacity must be between 2
and 127`. `LOCAL` variables and parameters have no `* n` form.

**Limits**

- A computed string (a `STR$`, a substring, a concatenation) used as an
  operand of a comparison, `LEN`, `INSTR` or another function may be at most
  127 bytes in the worst case.
- A `TEXTBOX` needs a variable of capacity at most 64 (63 characters); a
  dynamic `LABEL` shows at most 24 characters
  ([chapter 10](10-windows-and-controls.md)).

**Evidence:** tested in XAnne (`STRING * n` in `examples/contacts_m8.pbas`
and later applications); the overflow rules on the simulator and in XAnne.

**See also:** spec §4, §5.4; `examples/word_tools.pbas`,
`examples/number_format.pbas`.

## 2.4 `REAL`

**Syntax**

```text
DIM X AS REAL
2.5   .5   3.   1E10   6.02E+23   1.5e-3   PI
```

**Meaning**

- A REAL is a 5-byte binary floating-point number: about 9.6 significant
  decimal digits, from about ±2.9E−39 to ±1.7E+38, and 0. A literal with a
  decimal point or an exponent is a REAL. `PI` is the REAL nearest to π.
- An INTEGER is converted to REAL automatically where a REAL is needed
  (assignment, mixed arithmetic, comparisons).
- A REAL is **never** converted to an INTEGER silently. Use `CINT(x)` to
  round to the nearest INTEGER. `INT(x)` and `FIX(x)` round down or toward
  zero but their result is still a REAL, so `N = CINT(INT(X))` takes the
  whole part into an INTEGER.
- A result beyond about 1.7E+38 stops the program with
  `Runtime error: number out of range`; a result too small becomes 0.
- `STR$(x)` gives 9 significant digits without trailing zeros: `0.1`,
  `0.333333333`, `1E+10`.

**Requires:** nothing. The first use of REAL adds the parts of the REAL
library the program reaches to the program (up to about 4.5 KB of the 16K
block, see [memory](../memory.md)).

**Example**

```pbas
' expect-message: 3.5 3 3.5
' expect-message: 4
DIM X AS REAL
DIM N AS INTEGER
N = 7
X = N
X = X / 2
MESSAGE STR$(X) + " " + STR$(N / 2) + " " + STR$(N / 2.0)
N = CINT(X)
MESSAGE STR$(N)
END
```

`N / 2` with two INTEGERs is integer division (3); write `N / 2.0` for a
REAL quotient.

**Common errors**

```pbas-error
' expect-error: cannot assign REAL to INTEGER variable A (convert with CINT, which rounds; CINT(INT(x)) or CINT(FIX(x)) drops the fraction)
DIM A AS INTEGER
DIM X AS REAL
X = 2.7
A = X
END
```

The message suggests `INT` and `FIX`, but they return a REAL too, so
`A = INT(X)` gives the same error. Use `CINT`, or `CINT(INT(X))`.

```pbas-error
' expect-error: is too large for a REAL
DIM X AS REAL
X = 1E39
END
```

**Limits:** no REAL `FOR` counters, no REAL `MOD` or bit operators, no REAL
`NUMBERBOX`, `TEXTBOX` or `LABEL` binding (bind a STRING and convert with
`STR$` and `REALVAL`), no double precision, no formatted output.

**Evidence:** tested in XAnne (`examples/scicalc.pbas`, the REAL edge-case
probe `developer-tests/m7_edges.pbas`).

**See also:** spec §3.1; [chapter 3](03-expressions-and-functions.md#real-functions);
`examples/scicalc.pbas`, `examples/scicalc_m8.pbas`.

## 2.5 `CONST`

**Syntax**

```text
CONST Name = literal
```

**Meaning:** gives a name to a value. Every use of the name is replaced by
the literal, so a CONST may be used where only a constant is allowed: as a
`FOR … STEP`, as a `CASE` value, and as a `FILESAVE`/`FILELOAD` file name.
The literal may be an INTEGER (optionally signed), a REAL, a STRING, `TRUE`
or `FALSE`.

**Requires:** the `CONST` at the top level (outside any procedure).

**Example**

```pbas
' expect-message: Hi 1.5 -3
CONST GREETING = "Hi"
CONST RATE = 1.5
CONST LOW = -3
MESSAGE GREETING + " " + STR$(RATE) + " " + STR$(LOW)
END
```

**Common errors**

```pbas-error
' expect-error: K is a CONST and cannot be changed
CONST K = 5
K = 6
END
```

```pbas-error
' expect-error: CONST value must be a literal
DIM N AS INTEGER
CONST K = N
END
```

```pbas-error
' expect-error: CONST is only allowed at the top level
SUB S
    CONST K = 1
END SUB
END
```

**Limits:** a literal only (no expressions such as `CONST B = A * 2`). A
parameter or `LOCAL` may have the same name as a CONST: inside that
procedure the name means the parameter or LOCAL.

**Evidence:** compiled and simulator-tested; used by most applications
tested in XAnne.

**See also:** spec §5.3; `examples/gfxbench.pbas`.

## 2.6 Arrays

**Syntax**

```text
DIM Name(n) AS INTEGER | BOOLEAN | REAL | STRING [* chars] | TypeName
Name(index)
```

**Meaning**

- An array has **one dimension**, elements numbered **from 1** to n. n is an
  integer literal from 1 to 250.
- `Name(i)` is used like a variable of the element type, in expressions and
  as an assignment target. The index is any INTEGER expression.
- A literal index outside 1..n (`A(0)`, or `A(11)` for `DIM A(10)`) is a
  compile error: `A(0) is outside the array: its elements are A(1) to A(10)`.
  A computed index outside 1..n stops the program with
  `Runtime error: index out of range at line N`.
- Every element starts as 0, `FALSE` or `""`.
- There are no whole-array operations: an array cannot be assigned, compared,
  passed as a parameter or shown without an index. A STRING array can be the
  items of a `LIST` or `CHOICE` ([chapter 10](10-windows-and-controls.md)).

**Requires:** nothing.

**Example**

```pbas
' expect-message: 1 4 9 16 25
' expect-message: Runtime error: index out of range at line 11
DIM Sq(5) AS INTEGER
DIM I AS INTEGER
DIM T$ AS STRING
FOR I = 1 TO 5
    Sq(I) = I * I
    T$ = T$ + " " + STR$(Sq(I))
NEXT I
MESSAGE LTRIM$(T$)
Sq(I + 1) = 0
END
```

The last assignment fails because `I` is 5 after the loop (a `FOR` counter
keeps its last value, [chapter 4](04-control-flow.md#43-for--next)), so
`I + 1` is 6. The line number counts every line of the file, comments
included.

**Common errors**

```pbas-error
' expect-error: an array has 1 to 250 elements, got 251 (a larger array can be BANKED)
DIM A(251) AS INTEGER
END
```

```pbas-error
' expect-error: A is an array: use A(index)
DIM A(3) AS INTEGER
MESSAGE STR$(A)
END
```

```pbas-error
' expect-error: A(0) is outside the array: its elements are A(1) to A(3)
DIM A(3) AS INTEGER
A(0) = 1
END
```

Two dimensions (`DIM A(3, 3)`) give `expected ), got ,`. The size must be a
literal: a size from a variable or a CONST (`DIM A(N)`) gives `the number of
elements of an array is a whole number written in the program (a literal such
as 10); got N (a CONST or a variable cannot be used here)`. An array may not have
the name of a built-in function.

**Limits:** 250 elements; ordinary arrays live in the 16K block, so large
STRING arrays fill it quickly ([memory](../memory.md)). Use `BANKED` for
more.

**Evidence:** tested in XAnne (`examples/phone_book.pbas`,
`examples/shopping_list.pbas`).

**See also:** spec §5.2; `examples/word_sort.pbas`.

## 2.7 `BANKED` arrays

**Syntax**

```text
DIM Name(k) AS INTEGER | BOOLEAN | REAL | STRING [* n] | TypeName BANKED
```

**Meaning**

- A BANKED array lives outside the program's 16K block, in 16K blocks of RAM
  the program asks Rosanne for when it starts. k may be 1..32767.
- Elements are used exactly like ordinary elements: in expressions, as
  assignment targets, with `LINE INPUT #` and `PRINT #`, in procedures and
  handlers.
- Every element starts as 0 or `""`. If the PcW16 cannot give the blocks, the
  program stops at once with
  `Runtime error: not enough free memory for BANKED arrays at line N`.
- Each element access is an operating-system copy call, so a loop over
  thousands of elements is slow: `examples/records_m8.pbas` reads 3,000
  records in about 60 seconds in XAnne.
- A BANKED array of records is a *database* ([chapter 8](08-records-and-databases.md)).

**Requires:** an array (only an array can be BANKED).

**Example**

```pbas
' expect-message: 2000 1999000
DIM Big(2000) AS INTEGER BANKED
DIM I AS INTEGER
DIM Sum AS REAL
FOR I = 1 TO 2000
    Big(I) = I - 1
NEXT I
FOR I = 1 TO 2000
    Sum = Sum + Big(I)
NEXT I
MESSAGE STR$(I) + " " + STR$(Sum)
END
```

**Common errors**

```pbas-error
' expect-error: only an array can be BANKED
DIM A AS INTEGER BANKED
END
```

```pbas-error
' expect-error: BANKED arrays may use at most 32 16K blocks together (512K)
DIM A(30000) AS STRING * 126 BANKED
END
```

A statement may read at most four BANKED elements
(`this statement reads 5 BANKED array elements; at most 4 are allowed`):
copy some into variables first. A `LIST` or `CHOICE` cannot show a BANKED
array (`LIST cannot show the BANKED array A$`): copy the rows to show into an
ordinary array.

**Limits**

- All BANKED arrays, TEXT buffers and BITMAPs together use at most 32 blocks
  of 16K (512K). An element never crosses a block end, so a block holds
  16384 div (element size) elements.
- At most 4 BANKED reads in one statement.
- Not shown by `LIST` or `CHOICE`; not a parameter.

**Evidence:** tested in XAnne (`examples/contacts_m8.pbas`,
`examples/records_m8.pbas`, the probe `developer-tests/banktest.pbas`). Not yet tested
on a real PcW16, where free memory may differ.

**See also:** spec §5.4; [memory](../memory.md); `examples/records_m8.pbas`.

## 2.8 Assignment and conversion

**Syntax**

```text
Name = expression
Name(index) = expression
Record.Field = expression          (chapter 8)
```

**Meaning**

- The value must have the variable's type. The only automatic conversion is
  INTEGER to REAL.
- Text and numbers never convert by themselves: use `STR$` (number to text),
  `VAL` (text to INTEGER), `REALVAL` (text to REAL) and `ISNUM` (is the text
  a number?) — [chapter 3](03-expressions-and-functions.md).
- There is no `LET`.

**Example**

```pbas
' expect-message: 42 42 TRUE
DIM N AS INTEGER
DIM T$ AS STRING
DIM Ok$ AS STRING
T$ = "42"
N = VAL(T$)
Ok$ = "FALSE"
IF ISNUM(T$) THEN
    Ok$ = "TRUE"
END IF
MESSAGE STR$(N) + " " + T$ + " " + Ok$
END
```

**Common errors**

```pbas-error
' expect-error: cannot assign STRING to INTEGER variable N
DIM N AS INTEGER
N = "42"
END
```

`LET A = 1` gives `expected =, got A` ([chapter 17](17-unsupported.md)).

**See also:** spec §4.
