# lib/files.pbas: safe file names and safe replacement

`lib/files.pbas` solves two problems of programs that keep several files under one name (for example a design `FORM.DSN`, its picture `FORM.PBI` and a listing `FORM.BAS`):

- **The right extension.** `SafeName` turns whatever name the user typed into the name with the extension *your program* needs, so that exporting a picture can never overwrite the design because the user typed `FORM.DSN`.
- **Replacing a file only when its new version is complete.** `SafeReplace` deletes the old file and renames a finished temporary file to its name. If anything fails, the new version is still in the temporary file.

Why the second matters: `DB SAVE` and `BITMAP SAVE` keep the previous version as `NAME.BAK` and use `NAME.NEW` while writing, with the extension replaced. `FORM.DSN` and `FORM.PBI` therefore share `FORM.BAK`. Up to M13, saving the picture with `BITMAP SAVE` to `FORM.PBI` replaced the design's backup. Since M14 the save is refused instead: it does nothing and sets `IOERR` to 253, because `FORM.BAK` is not a picture (known issue KI-91, [limitations](../limitations.md); simulator only, awaiting the owner's XAnne retest). Either way, write the picture to a temporary name of its own and move it into place with `SafeReplace`.

**Evidence:** *Tested in XAnne* through DESIGNER, whose picture and listing exports use it (the owner's retest confirmed separate export names and a backup identical to the saved design). Not yet tested on a real PcW16.

## Adding it

```text
INCLUDE "lib/files.pbas"
```

It needs no other library and no CANVAS. It uses `KILL` and `NAME`, so `IOERR` and `EOF` are available in any program that includes it.

## Procedures and functions

The names go in and out through two global variables, not parameters: a STRING parameter would cost the resident block a whole string cell.

| Name | Kind | Parameters | Result | What it does |
|---|---|---|---|---|
| `SafeName` | FUNCTION | `Ext$ AS STRING` | INTEGER | Takes `SafeOut$` (set it to the name typed first), puts it in capitals, removes any extension typed and adds `Ext$` (for example `".PBI"`, or `""` for none). Returns 0 done, 1 no name, 2 more than 8 characters before the dot. |
| `SafeReplace` | FUNCTION | none | INTEGER | Deletes the file `SafeOut$` if it exists, then renames `SafeTemp$` to `SafeOut$`. Returns the `IOERR` of that, 0 when done. |

Use them in this order:

1. `SafeOut$ = typed name`, then `SafeName(".EXT")`; refuse the save if it is not 0.
2. Set `SafeTemp$` to a temporary name **of its own**, for example `"DSGNTMP.PBI"`, so that its `.NEW` and `.BAK` are its own too.
3. Write the complete new version to `SafeTemp$` (with `OPEN`/`PRINT #`/`CLOSE`, `BITMAP SAVE`, `TEXT SAVE` or `DB SAVE`) and check `IOERR`.
4. Only then call `SafeReplace()`.

## Names it defines

| Name | Type |
|---|---|
| `SafeOut$` | STRING * 13: the target name |
| `SafeTemp$` | STRING * 13: the temporary name |

Every name starts with `Safe`; do not declare your own.

## Memory cost

| | bytes |
|---|---:|
| whole program, one 16K image | +3,195 |
| resident 16K block, procedures in code banks | +2,786 |
| of which variables | +100 |

Most of this is the runtime's file code (delete, rename and file-name checks) and its workspace. A program that already uses files has much of it; with `--runtime-banks all` the file code moves to the runtime bank ([memory.md](../memory.md)).

## Errors

- `SafeName` does not check the characters: a name with a space or a DOS device name (`CON`) is accepted here and refused when the file is opened (`IOERR` 247, invalid name). Check `IOERR` after the write.
- `SafeReplace` treats "not found" (2) when deleting as success: there was no old file.
- If the rename fails, `SafeOut$` may already have been deleted; the new version is safe in `SafeTemp$`. Tell the user its name.
- `IOERR` codes are listed in [files](../manual/06-files.md); [lib/app.pbas](app.md)'s `AppError$` turns them into words.

## Example

```pbas
INCLUDE "lib/files.pbas"
DIM R AS INTEGER
DIM Line$ AS STRING
SafeOut$ = "notes.txt"
R = SafeName(".LOG")
MESSAGE "SafeName " + STR$(R) + ": " + SafeOut$
SafeTemp$ = "NOTESTMP.LOG"
OPEN SafeTemp$ FOR OUTPUT AS #1
PRINT #1, "first line"
CLOSE #1
IF IOERR = 0 THEN
    R = SafeReplace()
    MESSAGE "SafeReplace " + STR$(R)
END IF
OPEN SafeOut$ FOR INPUT AS #1
LINE INPUT #1, Line$
CLOSE #1
MESSAGE "read back: " + Line$
SafeOut$ = "averylongname"
MESSAGE "too long: " + STR$(SafeName(".LOG"))
END
' expect-message: SafeName 0: NOTES.LOG
' expect-message: SafeReplace 0
' expect-message: read back: first line
' expect-message: too long: 2
```

The messages above are from the project's simulator; on a PcW16 the files go to the folder the program was built for (`\PCW\FOLDER01` by default).

## Used by

- `examples/designer.pbas` (exporting a design as a picture and as a BASIC listing)

## Limitations

- Names are DOS 8.3 names in the program's one folder; there are no paths.
- Not atomic: between the delete and the rename there is a moment with no file of that name. A power cut then leaves the new version in `SafeTemp$`.

See also: [library index](README.md), [files](../manual/06-files.md), [records and databases](../manual/08-records-and-databases.md), [generated reference](../LIBRARY-REFERENCE.md).
