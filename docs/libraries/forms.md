# lib/forms.pbas: checks for data-entry forms

`lib/forms.pbas` checks what someone typed into a form (required fields, telephone numbers, e-mail addresses, whole numbers in a range) and keeps the **first** problem found as a message you can show. It also has four small helpers: `IsBlank`, `IsDigits`, `PadRight$` and `Confirm`.

**Evidence:** *Tested in XAnne* through CONTACTS III and CONTACTS IV. Not yet tested on a real PcW16.

## Adding it

```text
INCLUDE "lib/forms.pbas"
```

It needs no other library and no CANVAS.

## How a check works

```text
CALL FormStart
CALL FormRequire(Name$, "Name")
CALL FormPhone(Phone$, "Phone")
CALL FormEmail(Mail$, "E-mail")
IF NOT FormOK() THEN
    MESSAGE FormError$
END IF
```

`FormStart` clears the problem. Each check records its problem only if none is recorded yet, so `FormError$` names the first field that failed, in the order you checked them.

## Procedures and functions

| Name | Kind | Parameters | Result | What it does |
|---|---|---|---|---|
| `FormStart` | SUB | none | | Clears `FormError$`. |
| `FormOK` | FUNCTION | none | BOOLEAN | TRUE when no problem is recorded. |
| `FormFail` | SUB | `Why$ AS STRING` | | Records `Why$` as the problem, unless one is already recorded. Use it for checks of your own. |
| `FormRequire` | SUB | `V$ AS STRING, Label$ AS STRING` | | Fails with "*Label* is required" when V$ is empty or only spaces. |
| `FormPhone` | SUB | `V$ AS STRING, Label$ AS STRING` | | Accepts an empty value, or digits with optional spaces and `+ ( ) -`, at least 3 digits. Fails with "*Label*: a bad character" or "*Label*: too short". |
| `FormEmail` | SUB | `V$ AS STRING, Label$ AS STRING` | | Accepts an empty value, or exactly one `@` with text before it, and after it a dot with text on both sides; no spaces. Fails with "*Label* is not valid". |
| `FormNumber` | SUB | `V$ AS STRING, Label$ AS STRING, Low AS INTEGER, High AS INTEGER` | | Requires digits with an optional leading `-` (spaces around are ignored), between Low and High. Empty is refused. Fails with "*Label* is not valid" or "*Label* must be *Low* to *High*". |
| `IsBlank` | FUNCTION | `S$ AS STRING` | BOOLEAN | S$ is empty or only spaces. |
| `IsDigits` | FUNCTION | `S$ AS STRING` | BOOLEAN | S$ is one or more digits 0–9. |
| `PadRight$` | FUNCTION | `S$ AS STRING, N AS INTEGER` | STRING | S$ cut or padded with spaces to exactly N characters. |
| `Confirm` | FUNCTION | `Q$ AS STRING` | BOOLEAN | Asks Q$ with Yes and No buttons; TRUE for Yes. |

`FormRequire` only checks for presence. `FormPhone` and `FormEmail` accept an empty value, so combine them with `FormRequire` when the field is compulsory.

## Names it defines

| Name | Type |
|---|---|
| `FormError$` | STRING * 60: the first problem, "" when none |

Plus the procedure names above. **Four of them do not start with `Form`: `IsBlank`, `IsDigits`, `PadRight$` and `Confirm`.** A program that includes this library cannot define its own procedure with one of these names: the build stops with `duplicate subroutine CONFIRM`.

## Memory cost

| | bytes |
|---|---:|
| whole program, one 16K image | +4,480 |
| resident 16K block, procedures in code banks | +1,988 |
| of which variables | +1,212 |

The variables are mostly STRING parameters and locals. Each one is a full string of the program's string capacity (64 bytes by default) in the resident block, and this library has fifteen of them. Building with a smaller `--string-capacity` reduces the cost; each call site of `PadRight$` costs another string cell ([memory.md](../memory.md)).

## Errors

- `FormError$` holds 60 characters. A label so long that the message would not fit stops the program with a "string too long" runtime error; keep labels short.
- `FormNumber` never stops the program on a large number: more than five digits is "not valid", and five digits above 32767 is "must be *Low* to *High*".
- `Confirm` shows an alert and waits for the answer; do not call it from a TIMER handler.

## Example

```pbas
INCLUDE "lib/forms.pbas"
DIM Name$ AS STRING
DIM Phone$ AS STRING
DIM Mail$ AS STRING
DIM Age$ AS STRING
Name$ = "Ann"
Phone$ = "01632 960 123"
Mail$ = "ann@example"
Age$ = "42"
CALL FormStart
CALL FormRequire(Name$, "Name")
CALL FormPhone(Phone$, "Phone")
CALL FormEmail(Mail$, "E-mail")
CALL FormNumber(Age$, "Age", 0, 120)
IF NOT FormOK() THEN
    MESSAGE FormError$
END IF
Mail$ = "ann@example.org"
Age$ = "130"
CALL FormStart
CALL FormEmail(Mail$, "E-mail")
CALL FormNumber(Age$, "Age", 0, 120)
MESSAGE FormError$
MESSAGE "[" + PadRight$("Ann", 6) + "]"
END
' expect-message: E-mail is not valid
' expect-message: Age must be 0 to 120
' expect-message: [Ann   ]
```

## Used by

- `examples/contacts4.pbas`, `examples/contacts3.pbas`

## Limitations

- Only the first problem is reported.
- The e-mail and telephone rules are deliberately simple; they catch typing mistakes, not every invalid address.
- `FormNumber` checks INTEGERs only; there is no REAL check (use `ISNUM` and `REALVAL`, see [expressions and functions](../manual/03-expressions-and-functions.md)).

See also: [library index](README.md), [lib/app.pbas](app.md), [windows and controls](../manual/10-windows-and-controls.md), [generated reference](../LIBRARY-REFERENCE.md).
