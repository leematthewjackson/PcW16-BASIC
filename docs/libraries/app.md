# lib/app.pbas: status line, unsaved changes and file-error texts

`lib/app.pbas` holds what every document program repeats:

- a **status line** that can never stop the program by being too long;
- an **unsaved-changes flag** and the "Unsaved changes: Save / Discard / Cancel" question before closing or opening another file;
- **file-error texts**: an `IOERR` code in a few words, and an alert that says what failed and why.

**Evidence:** *Tested in XAnne* through CONTACTS IV, STARTER, PAINT, PAINT II, DESIGNER, SPRITED, REPORTER and PRINTDEMO. Not yet tested on a real PcW16.

## Adding it

```text
INCLUDE "lib/app.pbas"
```

**Your program must define `FUNCTION AppSave() AS BOOLEAN`.** The library calls it when the user chooses Save in the unsaved-changes question. It must save the document and return TRUE if it did. Without it the build stops with `app.pbas:47:12: unknown function APPSAVE`. The function may come anywhere in the program; it does not have to be above the INCLUDE.

To show the status line, put `LABEL AppStatus$` in a window. The library needs no other library and no CANVAS.

## Procedures and functions

| Name | Kind | Parameters | Result | What it does |
|---|---|---|---|---|
| `AppSay` | SUB | `Text$ AS STRING` | | Sets the status line to the first 24 characters of `Text$`. |
| `AppChanged` | SUB | none | | Marks the document changed (`AppDirty = TRUE`). Call it after every change. |
| `AppSaved` | SUB | none | | Marks it saved (`AppDirty = FALSE`). Call it after a good save. |
| `AppMayClose` | FUNCTION | none | BOOLEAN | TRUE straight away if nothing is unsaved. Otherwise asks "Unsaved changes" with Save, Discard and Cancel: Save calls your `AppSave()` and gives TRUE if the document is then saved; Discard gives TRUE; Cancel, or a failed save, gives FALSE. Call it before closing, quitting or opening another file, and go on only when it is TRUE. |
| `AppError$` | FUNCTION | `Code AS INTEGER` | STRING | An `IOERR` code in words, for example 2 "not found", 19 "disk write-protected", 80 "the name exists", 163 "disk full", 247 "invalid name", 251 "damaged". Unknown codes give "error *n*". |
| `AppFail` | SUB | `What$ AS STRING, Code AS INTEGER` | | Shows the alert "*What*: *meaning of Code*". |

`AppError$` knows the codes 0, 2, 3, 4, 5, 19, 80, 163, 240 and 246 to 252 (files, TEXT buffers, databases and bitmaps; see [files](../manual/06-files.md)). It does not know 253, which M14 added (a `DB SAVE` or `BITMAP SAVE` refused because `NAME.NEW` or `NAME.BAK` belongs to another file): that code gives "error 253".

## Names it defines

| Name | Type | Use |
|---|---|---|
| `AppStatus$` | STRING * 24 | the status line; bind a LABEL to it |
| `AppDirty` | BOOLEAN | TRUE while there are unsaved changes |

Everything starts with `App`, and `AppSave` is the one your program provides. Do not declare other names starting with `App`.

## Memory cost

Measured in a minimal host (a window with one button) with a one-line `AppSave`:

| | bytes |
|---|---:|
| whole program, one 16K image | +2,625 |
| resident 16K block, procedures in code banks | +768 |
| of which variables and strings | +547 |

The STRING parameters and the `AppError$` result take a string cell each, and **every place your program calls `AppError$` costs another cell** (64 bytes at the default capacity). Prefer `AppFail` in many places to many separate `AppError$` calls ([memory.md](../memory.md)).

## Errors

- The status line cannot overflow: `AppSay` cuts the text to 24 characters, the most a LABEL shows.
- `AppMayClose` shows a question and waits for the answer, so call it from a BUTTON or menu handler, not from a TIMER.
- If `AppSave` returns TRUE but did not call `AppSaved`, `AppMayClose` still sees unsaved changes and returns FALSE.

## Example

```pbas
INCLUDE "lib/app.pbas"
DIM Note$ AS STRING
WINDOW "Notes"
LABEL AppStatus$
TEXTBOX Note$, "Note"
BUTTON "Stamp", Stamp
BUTTON "Save", SaveNote
BUTTON "Quit", QuitApp
SUB Stamp
    Note$ = "Checked " + STR$(SECONDS)
    CALL AppChanged
    CALL AppSay("Changed")
END SUB
SUB SaveNote
    IF AppSave() THEN
        CALL AppSay("Saved")
    END IF
END SUB
FUNCTION AppSave() AS BOOLEAN
    OPEN "NOTE.TXT" FOR OUTPUT AS #1
    PRINT #1, Note$
    CLOSE #1
    IF IOERR <> 0 THEN
        CALL AppFail("NOTE.TXT", IOERR)
        RETURN FALSE
    END IF
    CALL AppSaved
    RETURN TRUE
END FUNCTION
SUB QuitApp
    IF AppMayClose() THEN
        EXIT
    END IF
END SUB
MESSAGE AppError$(163)
CALL AppFail("Open NOTE.TXT", 2)
CALL AppSay("Ready: type a note, then Save or Quit")
END
' expect-message: disk full
' expect-message: Open NOTE.TXT: not found
```

The status line shows `Ready: type a note, then` (24 characters) when the window opens. A change to the text box itself does not call `AppChanged`: a program that must know about typing checks the text against its saved copy before closing.

## Used by

- `examples/contacts4.pbas`, `examples/starter.pbas` (with [listview](listview.md))
- `examples/paint2.pbas`, `examples/designer.pbas`, `examples/sprited.pbas`, `examples/paint.pbas`
- `examples/reporter.pbas`, `examples/printdemo.pbas`

## Limitations

- One document per program: there is one `AppDirty` flag.
- The question's wording and buttons are fixed.

See also: [library index](README.md), [lib/forms.pbas](forms.md), [lib/files.pbas](files.md), [errors and diagnostics](../manual/09-errors-and-diagnostics.md), [generated reference](../LIBRARY-REFERENCE.md).
