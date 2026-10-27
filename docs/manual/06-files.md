# 6. Files

PcW16 BASIC reads and writes files on the PcW16's floppy disk, in one folder
chosen when the program is built. There are two levels:

- `FILESAVE` and `FILELOAD` save or load one short string in one statement,
  with a ready-made alert telling the user what happened;
- `OPEN`, `PRINT #`, `LINE INPUT #`, `EOF`, `CLOSE`, `KILL` and `NAME` work
  line by line and report through `IOERR`, so the program decides what to
  tell the user.

Whole documents, databases and pictures have their own statements:
`TEXT LOAD`/`TEXT SAVE` ([chapter 7](07-text-buffers.md)), `DB LOAD`/`DB SAVE`
([chapter 8](08-records-and-databases.md)) and `BITMAP LOAD`/`BITMAP SAVE`
([chapter 13](13-bitmaps-and-sprites.md)). The normative text is
[LANGUAGE-SPEC.md](../../LANGUAGE-SPEC.md) §7 and §7.1. (Where §7 and §7.1
say file names are always literals, that is out of date: see §6.1 below.)

**Evidence:** the file statements are tested in XAnne (`examples/file_roundtrip.pbas`,
`examples/missing_file.pbas`, `examples/file_limits.pbas`,
`examples/journal.pbas`, `developer-tests/m7_edges.pbas`; `KILL` and `NAME` through the
applications). They are **not yet tested on a real PcW16** or a real floppy
drive. The examples in this chapter run on the project's simulator, which
has a disk of its own in memory.

## 6.1 File names and the folder

- **The folder is fixed when the program is built**, by the build option
  `--folder` (default `\PCW\FOLDER01`) on the floppy drive
  ([chapter 16](16-building-and-commands.md)). A program cannot choose
  another folder or drive at run time, and never creates a folder: it must
  already exist on the disk. `--drive flash` is refused; only the floppy is
  supported.
- **A file name is a DOS 8.3 name**: 1 to 8 letters, digits or `_`, a dot,
  and 1 to 3 letters or digits (`NOTES.TXT`, `DATA_1.DAT`). Lower case is
  turned into capitals. The device names `CON`, `PRN`, `AUX`, `NUL`, `CLOCK$`,
  `COM1`–`COM9` and `LPT1`–`LPT9` are refused.
- `FILESAVE` and `FILELOAD` need the name as a **string literal or a CONST**,
  checked when the program is built.
- `OPEN`, `KILL`, `NAME`, `TEXT`, `DB` and `BITMAP` accept **any STRING
  expression** as a name, checked when the statement runs: an invalid name
  does nothing and sets `IOERR` to 247.

```pbas-error
' expect-error: file name 'CON.TXT' uses the DOS device name CON
FILESAVE "CON.TXT", "x"
END
```

```pbas-error
' expect-error: is not a valid DOS 8.3 name
FILESAVE "TOOLONGNAME.TXT", "x"
END
```

```pbas-error
' expect-error: this file name must be written in the program as a string, such as "NOTES.TXT", or be a CONST
DIM F$ AS STRING
F$ = "A.TXT"
FILESAVE F$, "x"
END
```

## 6.2 `FILESAVE` and `FILELOAD`

**Syntax**

```text
FILESAVE "NAME.EXT", text$
FILELOAD "NAME.EXT", variable$
```

**Meaning**

- `FILESAVE` creates the file, or **replaces an existing file of that name
  without asking**, and writes exactly the bytes of the text: no line ending,
  no terminator. An empty string makes an empty file.
- `FILELOAD` replaces the STRING variable with the whole contents of the
  file. The file must hold at most capacity − 1 bytes and no zero byte.
- Each statement shows **one alert** and then the program continues; a file
  failure is never a runtime error. The alerts are:

| Outcome | Alert |
|---|---|
| saved / loaded | `File saved: NAME.EXT` / `File loaded: NAME.EXT` |
| failure | `File not saved: NAME.EXT (reason)` / `File not loaded: NAME.EXT (reason)` |

  The reason is `folder not found`, `not found`, `longer than N characters`,
  `not text` (a zero byte), `drive error`, or `error #XX` with Rosanne's code
  in hexadecimal (`#13` write-protected, `#A3` disk full, `#05` access
  denied). In XAnne a missing folder has also shown as `error #05`.
- A failed load never changes the variable or any file.
- In a window program, a `TEXTBOX` bound to the loaded variable shows the new
  text when the handler returns, after the alert.

**Requires:** a literal or CONST file name.

**Example**

```pbas
' expect-message: File saved: PBNOTE.TXT
' expect-message: File loaded: PBNOTE.TXT
' expect-message: hello
' expect-message: File not loaded: PBNONE.TXT (not found)
' expect-message: hello
CONST NOTE = "PBNOTE.TXT"
DIM S$ AS STRING
FILESAVE NOTE, "hello"
FILELOAD NOTE, S$
MESSAGE S$
FILELOAD "PBNONE.TXT", S$
MESSAGE S$
END
```

**Common errors**

```pbas-error
' expect-error: a file written by FILESAVE holds at most 127
DIM S$ AS STRING * 126
FILESAVE "A.TXT", S$ + S$
END
```

**Limits and hazards**

- At most 127 bytes per file (checked when the program is built, from the
  longest value the expression could have).
- `FILESAVE` is **not crash-safe**: if writing fails after the file was
  opened, the old contents may already be gone and the file may be empty or
  partial (known issue KI-11, [limitations](../limitations.md)). For data
  that matters, use the safe replacement of §6.9.
- While an `OPEN` channel of the same direction is open, `FILESAVE`/`FILELOAD`
  cannot open their file and report `error #04` in their alert.

**See also:** spec §7; `examples/file_roundtrip.pbas`,
`examples/missing_file.pbas`, `examples/file_limits.pbas`,
`examples/mini_notes.pbas`, `examples/settings_panel.pbas`.

## 6.3 `OPEN` and `CLOSE`

**Syntax**

```text
OPEN name$ FOR INPUT AS #1      (or #2)
OPEN name$ FOR OUTPUT AS #2     (or #1)
CLOSE #channel
CLOSE                           every open channel
```

**Meaning**

- `FOR INPUT` opens an existing file for reading. `FOR OUTPUT` creates the
  file, or **replaces** an existing one (it is emptied when opened).
- The channel is `#1` or `#2`. At most **one file open for reading and one
  for writing** at a time (Rosanne's rule): opening a second file in the same
  direction sets `IOERR` 4.
- `name$` is a literal or any STRING expression.
- Close every file you open. Ending the program (`END`, `EXIT`, a runtime
  error) also closes open files.

**Requires:** nothing. Any program with `OPEN`, `KILL` or `NAME` may use
`IOERR` and `EOF`.

**Common errors**

```pbas-error
' expect-error: expected INPUT or OUTPUT (APPEND and RANDOM are not available on the floppy)
OPEN "A.TXT" FOR APPEND AS #1
END
```

```pbas-error
' expect-error: a file channel is #1 or #2
OPEN "A.TXT" FOR INPUT AS #3
END
```

There is no `APPEND`: to add a line, copy the file to a new one with the new
line, then replace the old one (§6.9; `examples/journal.pbas` does this).
There is no random access or seek.

## 6.4 `PRINT #`

**Syntax**

```text
PRINT #channel, value
```

**Meaning:** writes one line: the text of a STRING, or a number as `STR$`
would show it, followed by CR LF. One value per statement: there are no `;`
or `,` lists. `PRINT` without `#` does not exist.

**Common errors**

```pbas-error
' expect-error: unexpected character ';'
OPEN "A.TXT" FOR OUTPUT AS #2
PRINT #2, "a"; "b"
CLOSE #2
END
```

**Limits:** a STRING written is at most 127 characters.

## 6.5 `LINE INPUT #` and `EOF`

**Syntax**

```text
LINE INPUT #channel, variable$
LINE INPUT #channel, array$(index)
EOF(channel)
```

**Meaning**

- `LINE INPUT #` reads the next line, up to LF, into a STRING variable or
  array element. A CR before the LF is dropped.
- A line longer than the variable can hold is **not cut**: the variable is
  left unchanged, the rest of the line is skipped, and `IOERR` is 243. A line
  with a zero byte is skipped with `IOERR` 244. Reading past the end gives
  `IOERR` 245.
- `EOF(c)` is TRUE unless channel c is open for reading and has something
  left to read. The channel is the literal 1 or 2. `EOF` does not change
  `IOERR`.
- There is no `INPUT #` and no `WRITE #`: read whole lines and take them
  apart with `INSTR`, `MID$` and `VAL`.

**Example**

```pbas
' expect-message: one/42/2.5/
' expect-message: 2
OPEN "PBLINES.TXT" FOR OUTPUT AS #2
PRINT #2, "one"
PRINT #2, 42
PRINT #2, 2.5
CLOSE #2
DIM L$ AS STRING
DIM T$ AS STRING
OPEN "PBLINES.TXT" FOR INPUT AS #1
WHILE NOT EOF(1)
    LINE INPUT #1, L$
    T$ = T$ + L$ + "/"
WEND
CLOSE #1
MESSAGE T$
KILL "PBLINES.TXT"
OPEN "PBLINES.TXT" FOR INPUT AS #1
MESSAGE STR$(IOERR)
END
```

The last `OPEN` fails with `IOERR` 2 (file not found) because the file was
deleted.

**Example: a line that does not fit**

```pbas
' expect-message: 243 []
' expect-message: 0 [ok]
' expect-message: 245
DIM S$ AS STRING * 3
OPEN "PBLONG.TXT" FOR OUTPUT AS #2
PRINT #2, "abcdef"
PRINT #2, "ok"
CLOSE #2
OPEN "PBLONG.TXT" FOR INPUT AS #1
LINE INPUT #1, S$
MESSAGE STR$(IOERR) + " [" + S$ + "]"
LINE INPUT #1, S$
MESSAGE STR$(IOERR) + " [" + S$ + "]"
LINE INPUT #1, S$
MESSAGE STR$(IOERR)
CLOSE #1
END
```

**Common errors**

```pbas-error
' expect-error: EOF reports on file operations, and the program has none
DIM B AS BOOLEAN
B = EOF(1)
END
```

```pbas-error
' expect-error: expected =, got #
DIM A$ AS STRING
INPUT #1, A$
END
```

## 6.6 `KILL` and `NAME`

**Syntax**

```text
KILL name$
NAME old$ AS new$
```

**Meaning:** `KILL` deletes a file. `NAME` renames one; the new name must not
exist already (`IOERR` 80). Both set `IOERR`. Close a file before deleting or
renaming it.

**Example**

```pbas
' expect-message: 80
' expect-message: 0
OPEN "PBA.TXT" FOR OUTPUT AS #2
PRINT #2, "a"
CLOSE #2
OPEN "PBB.TXT" FOR OUTPUT AS #2
CLOSE #2
NAME "PBA.TXT" AS "PBB.TXT"
MESSAGE STR$(IOERR)
KILL "PBB.TXT"
NAME "PBA.TXT" AS "PBB.TXT"
MESSAGE STR$(IOERR)
END
```

## 6.7 `IOERR`

`IOERR` is an INTEGER: the outcome of the last `OPEN`, `CLOSE`, `PRINT #`,
`LINE INPUT #`, `KILL` or `NAME` (and of the TEXT, DB, BITMAP and PAGE
statements in their chapters). **File errors never stop the program**: check
`IOERR` after every statement whose failure matters.

| IOERR | Meaning |
|---|---|
| 0 | success |
| 2 | file not found |
| 3 | folder not found |
| 4 | too many open files: one for reading and one for writing at most |
| 5 | access denied (a read-only file) |
| 19 | disk write-protected (Rosanne `#13`) |
| 80 | the new name already exists (`#50`) |
| 163 | disk full (`#A3`) |
| 240 | drive error |
| 241 | channel already open |
| 242 | channel not open, or not open in that direction |
| 243 | the line is longer than the variable: the rest of the line is skipped |
| 244 | the line contains a zero byte: skipped |
| 245 | nothing left to read |
| 246 | (TEXT LOAD) the file is larger than the buffer |
| 247 | invalid file name |
| 248–253 | database and picture file errors: [chapter 8](08-records-and-databases.md), [chapter 13](13-bitmaps-and-sprites.md) |
| any other | a Rosanne error code |

`IOERR` and `EOF` are compile errors in a program that has no file statement
at all: `IOERR reports on file operations, and the program has none (OPEN, KILL,
NAME, TEXT LOAD or SAVE, DB, BITMAP LOAD or SAVE, PAGE)`.

## 6.8 Error behaviour

- A file problem is never a runtime error: the statement does nothing (or as
  much as it could), sets `IOERR`, and the program goes on. `FILESAVE` and
  `FILELOAD` show their alert instead.
- Nothing read is ever cut short to fit: a line or file that does not fit is
  refused and the variable keeps its old value.
- `ON ERROR` does not exist; test `IOERR` instead.
- `lib/app.pbas` has `AppError$(Code)`, a short text for each IOERR code, and
  `AppFail(What$, Code)` to report one ([libraries](../libraries/README.md)).

## 6.9 Safe file handling

Opening a file for output empties it at once, so a program that writes
straight over its only copy loses the data if anything goes wrong half way.
Write the new version under a temporary name, check it, then swap it in:

1. Write `NAME.TMP`, checking `IOERR` after every `PRINT #` and after
   `CLOSE`.
2. `KILL` the old file (`IOERR` 2 is fine: there was none).
3. `NAME` the temporary file to the real name.
4. At start-up, if the real file is missing but `NAME.TMP` exists, the
   program stopped between steps 2 and 3: rename the temporary file and tell
   the user (as `examples/contacts.pbas` does).

```pbas
' expect-message: saved
' expect-message: 3 lines
DIM I AS INTEGER
DIM Bad AS BOOLEAN
DIM L$ AS STRING
DIM N AS INTEGER
SUB SaveAll
    Bad = FALSE
    OPEN "PBDATA.TMP" FOR OUTPUT AS #2
    IF IOERR <> 0 THEN
        Bad = TRUE
        EXIT SUB
    END IF
    FOR I = 1 TO 3
        PRINT #2, "line " + STR$(I)
        IF IOERR <> 0 THEN
            Bad = TRUE
        END IF
    NEXT I
    CLOSE #2
    IF Bad OR IOERR <> 0 THEN
        Bad = TRUE
        KILL "PBDATA.TMP"
        EXIT SUB
    END IF
    KILL "PBDATA.TXT"
    IF IOERR <> 0 AND IOERR <> 2 THEN
        Bad = TRUE
        EXIT SUB
    END IF
    NAME "PBDATA.TMP" AS "PBDATA.TXT"
    Bad = IOERR <> 0
END SUB
CALL SaveAll
IF Bad THEN
    MESSAGE "not saved: " + STR$(IOERR)
ELSE
    MESSAGE "saved"
END IF
OPEN "PBDATA.TXT" FOR INPUT AS #1
WHILE NOT EOF(1)
    LINE INPUT #1, L$
    N = N + 1
WEND
CLOSE #1
MESSAGE STR$(N) + " lines"
END
```

**`lib/files.pbas`** packages steps 2 and 3 as `SafeReplace()` and forces a
typed name to the right extension with `SafeName(Ext$)`; see
[libraries](../libraries/README.md).

**Statements that do this for you.** `DB SAVE` and `BITMAP SAVE` already use a
safe replacement, keeping the previous version as `NAME.BAK` and writing
through `NAME.NEW` ([chapter 8](08-records-and-databases.md#86-safe-replacement-and-recovery)).
`TEXT SAVE`, `FILESAVE` and `OPEN … FOR OUTPUT` do not.

**Two files with one name.** The `.BAK` and `.NEW` companions are named by
replacing the extension, so `FORM.DSN` and `FORM.PBI` share `FORM.BAK` and
`FORM.NEW`. Up to M13, saving one replaced the other's backup. Since M14
`DB SAVE` and `BITMAP SAVE` first check `NAME.NEW` and `NAME.BAK`: if either
belongs to another kind of file, the save does nothing and sets `IOERR` to
253 (known issue KI-91, [limitations](../limitations.md); simulator only,
awaiting the owner's XAnne retest). Give each kind of file a name of its own,
or write the others through a temporary name and `SafeReplace`, as
`examples/designer.pbas` does; otherwise the second save is refused.

**Other habits**

- Use names that are clearly your program's own; `FILESAVE` and
  `OPEN … FOR OUTPUT` replace any file of that name without asking.
- Ask before replacing a user's document (`ASK`,
  [chapter 10](10-windows-and-controls.md)).
- Copy important disks on the host before testing a program that writes
  files.

**See also:** spec §7.1; `examples/journal.pbas`, `examples/word_sort.pbas`,
`examples/contacts.pbas`, `examples/records_m8.pbas`, `lib/files.pbas`.
