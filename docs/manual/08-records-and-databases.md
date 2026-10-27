# 8. Records and databases

A `TYPE` groups fields into a record. An array of records kept `BANKED` is a
*database*: `DB` statements load and save it whole, with a safe replacement
and automatic recovery, add and delete records, and sort or search it
through an index. The normative text is
[LANGUAGE-SPEC.md](../../LANGUAGE-SPEC.md) §5.8, §5.9 and §5.10.

**Evidence:** tested in XAnne (the database probe `developer-tests/dbprobe.pbas`, which
covers saving, the backup rotation and recovery from both companion files,
and a sort and search of 200 records; `examples/contacts3.pbas` and
`examples/contacts4.pbas`, including recovery from a damaged file). The "no
valid copy at all" path is simulator-tested only. The M14 changes to
`DB SAVE` and `DB LOAD` (§8.6, IOERR 253) are simulator-tested and await the
owner's XAnne retest. Times on a real PcW16 are not measured; nothing here is
yet tested on real hardware.

## 8.1 `TYPE`

**Syntax**

```text
TYPE Name
    Field AS INTEGER
    Field AS REAL
    Field AS BOOLEAN
    Field AS STRING * n
END TYPE
```

**Meaning**

- Declares a record type at the top level, one field per line. A TYPE may be
  used before or after its declaration.
- Field types are INTEGER, REAL, BOOLEAN and `STRING * n` (1 ≤ n ≤ 126). A
  STRING field must state its length.
- A field name may be a keyword (`Label`, `Text`), because it is always
  written after a dot. A field name ending in `$` must be a STRING.
- The layout is fixed, in declaration order with no padding: INTEGER and
  BOOLEAN 2 bytes, REAL 5 bytes, `STRING * n` n + 1 bytes. Bytes after a
  string's end are always zero, so a record's bytes depend only on its
  values. Database files depend on this layout.

**Requires:** nothing.

**Common errors**

```pbas-error
' expect-error: a STRING field states its length
TYPE T
    Name AS STRING
END TYPE
END
```

```pbas-error
' expect-error: records inside records are not supported
TYPE A
    X AS INTEGER
END TYPE
TYPE B
    Inner AS A
END TYPE
DIM V AS B
V.Inner.X = 1
END
```

```pbas-error
' expect-error: a record is at most 512 bytes
TYPE T
    A AS STRING * 126
    B AS STRING * 126
    C AS STRING * 126
    D AS STRING * 126
    E AS STRING * 126
END TYPE
DIM R AS T
END
```

`TYPE T has no fields` for an empty TYPE; `TYPE T without END TYPE` when the
file ends inside one.

**Limits:** at most 512 bytes per record; no nested records; no arrays
inside a record; no BITMAP or TEXT fields.

## 8.2 Record variables

**Syntax**

```text
DIM R AS TypeName
DIM A(n) AS TypeName [BANKED]
LOCAL R AS TypeName
R.Field          A(i).Field
R = Other        A(i) = R        R = A(j)        whole-record copies
```

**Meaning**

- `R.Field` and `A(i).Field` are variables of the field's type, usable
  anywhere such a variable is.
- A new record is all zero: 0, `FALSE`, `""`.
- A whole record may be used in two places only: a copy from another record
  of the **same TYPE**, and as a parameter or FUNCTION result
  ([chapter 5](05-procedures.md)). A record parameter is a copy; changing it
  does not change the argument.
- Records are not compared whole: compare fields.

**Example**

```pbas
' expect-message: Ada 7 2.5 0
TYPE Contact
    Id AS INTEGER
    Name AS STRING * 20
    Balance AS REAL
    Active AS BOOLEAN
END TYPE
DIM P AS Contact
DIM Shelf(3) AS Contact
P.Name = "Ada"
P.Balance = 2.5
P.Active = TRUE
Shelf(2) = P
Shelf(2).Id = 7
MESSAGE Shelf(2).Name + " " + STR$(Shelf(2).Id) + " " + STR$(Shelf(2).Balance) + " " + STR$(P.Id)
END
```

**Example: records and procedures**

```pbas
' expect-message: 3,4
' expect-message: 3
TYPE Pt
    X AS INTEGER
    Y AS INTEGER
END TYPE
DIM P AS Pt
FUNCTION Make(X AS INTEGER, Y AS INTEGER) AS Pt
    LOCAL T AS Pt
    T.X = X
    T.Y = Y
    RETURN T
END FUNCTION
SUB Show(Q AS Pt)
    MESSAGE STR$(Q.X) + "," + STR$(Q.Y)
    Q.X = 0
END SUB
P = Make(3, 4)
CALL Show(P)
MESSAGE STR$(P.X)
END
```

**Common errors**

```pbas-error
' expect-error: A is a record of TYPE T: use one of its fields
TYPE T
    X AS INTEGER
END TYPE
DIM A AS T
MESSAGE A
END
```

```pbas-error
' expect-error: a record is copied only from the same TYPE
TYPE T
    X AS INTEGER
END TYPE
TYPE U
    X AS INTEGER
END TYPE
DIM A AS T
DIM B AS U
A = B
END
```

**Limits:** an ordinary array of records has at most 250 elements and counts
against the 16K block. A BANKED array of records may have up to 32767; each
field read from a BANKED record counts as one of the four BANKED reads a
statement may make ([chapter 2](02-variables-and-types.md#27-banked-arrays)).
A program with a BANKED array of records keeps five record-sized buffers in
the 16K block.

## 8.3 What a database is

A **database** is a BANKED array of records together with an INTEGER
variable that holds its record count. The records in use are elements
1..Count. A database file is read and written whole: there is no record-by-
record file access.

- `DB NEW` and `DBFIND` use the TYPE's **first field** as the record's
  identifier, and it must be INTEGER.
- `DB NEW` gives each new record the next identifier (1, 2, 3, …). The next
  identifier is saved in the file, so an identifier is never reused after a
  delete. After 32767, `DB NEW` reports `IOERR` 252.
- For `LOAD`, `NEW` and `DELETE`, Count must be a plain INTEGER variable,
  because the statement sets it. A Count outside 0..the array's length stops
  the program with `index out of range`.

## 8.4 `DB` statements and functions

**Syntax**

```text
DB LOAD A, Count, name$             read the file; set Count, IOERR, DBRECOVERED
DB SAVE A, Count, name$             write elements 1..Count safely; set IOERR
DB NEW A, Count                     add a cleared record with the next identifier
DB DELETE A, Count, k               remove element k, keeping the order
DBFIND(A, Count, id)                the first element whose first field is id, else 0
DBNEXTID(A)                         the identifier the next DB NEW will give
DBRECOVERED                         which file the last DB LOAD read: 0, 1 (.NEW) or 2 (.BAK)
```

**Meaning**

- `DB NEW`: if Count is below the array's length, element Count + 1 is
  cleared, its first field gets the next identifier, Count increases and
  `IOERR` is 0. Otherwise `IOERR` is 252 and nothing changes.
- `DB DELETE`: element k (1..Count) is removed; later elements move down one;
  the old last element is cleared and Count decreases. `IOERR` is not
  changed.
- `DB LOAD` and `DB SAVE`: see §8.6.
- The file name is a literal or a STRING (§6.1 of [chapter 6](06-files.md)).

**Requires:** `DIM A(n) AS TypeName BANKED` and `DIM Count AS INTEGER`.

**Example**

```pbas
' expect-message: Ann 3
' expect-message: 0
' expect-message: 2 0 2
' expect-message: 1
TYPE Pet
    Id AS INTEGER
    Name AS STRING * 20
    Age AS INTEGER
END TYPE
DIM Pets(100) AS Pet BANKED
DIM Count AS INTEGER
DIM ByName(100) AS INTEGER
DIM Found AS INTEGER
DB NEW Pets, Count
Pets(Count).Name = "Rex"
DB NEW Pets, Count
Pets(Count).Name = "Ann"
DB SORT Pets, Count, ByName, Name
MESSAGE Pets(ByName(1)).Name + " " + STR$(DBNEXTID(Pets))
DB SAVE Pets, Count, "PBPETS.PDB"
MESSAGE STR$(IOERR)
Count = 0
DB LOAD Pets, Count, "PBPETS.PDB"
MESSAGE STR$(Count) + " " + STR$(DBRECOVERED) + " " + STR$(DBFIND(Pets, Count, 2))
DB SEARCH Pets, Count, ByName, Found, Name, "e"
MESSAGE STR$(Found)
END
```

**Example: a full array, a delete, and a missing file**

```pbas
' expect-message: 3 252
' expect-message: 2 2 4
' expect-message: 0 2
TYPE T
    Id AS INTEGER
    Name AS STRING * 10
END TYPE
DIM A(3) AS T BANKED
DIM N AS INTEGER
DB NEW A, N
DB NEW A, N
DB NEW A, N
DB NEW A, N
MESSAGE STR$(N) + " " + STR$(IOERR)
DB DELETE A, N, 1
MESSAGE STR$(N) + " " + STR$(A(1).Id) + " " + STR$(DBNEXTID(A))
DB LOAD A, N, "PBNONE.PDB"
MESSAGE STR$(N) + " " + STR$(IOERR)
END
```

**Common errors**

```pbas-error
' expect-error: DB SAVE needs a database: a BANKED array of records
TYPE T
    Id AS INTEGER
END TYPE
DIM A(10) AS T
DIM N AS INTEGER
DB SAVE A, N, "PBX.PDB"
END
```

```pbas-error
' expect-error: which must be INTEGER
TYPE T
    Name AS STRING * 10
    Id AS INTEGER
END TYPE
DIM A(10) AS T BANKED
DIM N AS INTEGER
DB NEW A, N
END
```

```pbas-error
' expect-error: .NEW and .BAK are the database's own temporary and backup files
TYPE T
    Id AS INTEGER
END TYPE
DIM A(10) AS T BANKED
DIM N AS INTEGER
DB SAVE A, N, "PBX.BAK"
END
```

`DBRECOVERED reports on DB LOAD: the program has none` if the program never
loads a database.

## 8.5 `IOERR` codes for databases

| Code | Meaning |
|---|---|
| 0 | success (also after a recovery: check `DBRECOVERED`) |
| 2 | no file, no `.NEW` and no `.BAK` |
| 247 | invalid name, or a `.NEW` / `.BAK` extension given as a STRING |
| 248 | not a database |
| 249 | another TYPE: the field list or record size differs |
| 250 | another format version |
| 251 | damaged: the check bytes differ, the file is short, bytes follow the end, or (M14) a STRING field has no terminating 0 within the field |
| 252 | more records than the array holds (`LOAD`), or the array or the identifiers are full (`NEW`) |
| 253 | `SAVE`: `NAME.NEW` or `NAME.BAK` belongs to another file of the same name (M14, known issue KI-91); nothing was changed |
| others | the file codes of [chapter 6](06-files.md#67-ioerr) |

## 8.6 Safe replacement and recovery

`DB SAVE` never writes over the only copy of a database. It uses two
companion files, named by replacing the extension: **`NAME.NEW`** (the new
version being written) and **`NAME.BAK`** (the previous version).

| Step | `DB SAVE` does |
|---|---|
| 0 | (M14) check that `NAME.NEW` and `NAME.BAK`, where they exist, belong to this database (below) |
| 1 | write `NAME.NEW` |
| 2 | read `NAME.NEW` back and check it completely |
| 3 | delete `NAME.BAK` |
| 4 | rename the file to `NAME.BAK` |
| 5 | rename `NAME.NEW` to the file |

- Step 0 reads the start of each companion that exists:
  - shorter than 4 bytes: a leftover, replaced;
  - beginning `PDB1`: this database's own, unless it holds a whole 16-byte
    header whose TYPE signature is another TYPE's (a `PDB1` file shorter than
    the header counts as this database's; the format version is not checked);
  - anything else (for example `FORM.BAK` is the backup of a picture
    `FORM.PBI`, or a text file): another file's. The save does nothing and
    sets `IOERR` to 253.

  If a companion cannot be opened or read, the save stops with Rosanne's code
  and changes nothing.
- When the file itself does not exist (a first save, or step 5 failed last
  time), steps 3 and 4 are skipped, so `NAME.BAK` is kept. (Up to M13 a first
  save deleted it.)
- A failure in steps 1–4 deletes `NAME.NEW` and leaves the file as it was
  (if step 4 fails, the old `.BAK` is already gone).
- A failure in step 5 leaves the new data in `NAME.NEW` and the previous
  version in `NAME.BAK`.
- **A save that did not finish counts as not done.** If a save is
  interrupted (the PcW16 is switched off, or the program stops) after step 2
  but before step 5, while the file itself still exists, the disk holds the
  file (the old data) and a whole `NAME.NEW` (the new data). `DB LOAD` then
  loads the file itself, with `DBRECOVERED` 0, and the next `DB SAVE` writes
  over `NAME.NEW`: the result is as if the interrupted save had never
  started. A program that wants to offer the newer copy must first rename it
  to a name of its own, for example `NAME "PEOPLE.NEW" AS "PEOPLENW.PDB"`,
  and load that. `DB LOAD` does not take a `.NEW` name: a literal one is a
  compile error, and one in a STRING variable gives `IOERR` 247.
- `DB LOAD` reads the file. Only if the file is missing, is not a database
  (248) or is damaged (251) does it try `NAME.NEW`, then `NAME.BAK`, and use
  the first that reads back whole and valid. `DBRECOVERED` says which (0, 1
  or 2), and `IOERR` is 0: **recovery is not an error**. When `DBRECOVERED`
  is not 0, tell the user and save again.
- A file that is whole but cannot be loaded here (another TYPE, 249; another
  version, 250; more records than the array holds, 252; or a read error) is
  reported with that code, Count is 0, and no older copy is loaded over it.
  (Up to M13 any failure fell back to an older copy with `IOERR` 0, and a
  program that then saved replaced the newer file.)
- If none is valid, Count is 0, the next identifier is 1, `DBRECOVERED` is 0
  and `IOERR` is the error of the first file that exists (2 if none does).
  Elements after Count may hold bytes of a failed file.
- *Evidence:* the M14 changes (step 0, the kept `.BAK`, when `DB LOAD` falls
  back, the STRING-field check) are simulator only, awaiting the owner's XAnne
  retest. The rest is tested in XAnne.
- There is no "flush to disk" call on the PcW16: data counts as safe once it
  has been closed and read back.

**Hazards**

- `DB SAVE` replaces `NAME.BAK` and creates and deletes `NAME.NEW`. Do not
  give a database the name of another document of yours.
- Files that differ only in extension share these companions: `FORM.DSN` and
  `FORM.PBI` both use `FORM.BAK`, so the second of their saves is refused with
  `IOERR` 253 (known issue KI-91, [limitations](../limitations.md)); see
  [chapter 6](06-files.md#69-safe-file-handling).
- Changing a TYPE makes its old files unreadable (`IOERR` 249). There is no
  automatic conversion.

## 8.7 `DB SORT` and `DB SEARCH`

**Syntax**

```text
DB SORT A, Count, Index, Field [, DESC] [, NOCASE] [, KEEP]
DB SEARCH A, Count, Index, Found, Field, text$ [, NOCASE]
```

**Meaning**

- The records never move. An **index** — an ordinary INTEGER array — receives
  element numbers instead; then `A(Index(i)).Field` visits the records in
  order.
- `DB SORT` sets `Index(1..Count)` to 1..Count ordered by the field:
  ascending, or descending with `DESC`. The sort is stable (equal keys stay
  in element order). INTEGERs sort as signed numbers, REALs numerically,
  STRINGs in byte order; `NOCASE` makes `a`..`z` compare as `A`..`Z`.
- `KEEP` sorts the entries already in `Index(1..Count)` instead of starting
  from 1..Count. Use it for a two-key order (sort by the second key, then by
  the first with `KEEP`) and to sort search results.
- `DB SEARCH` puts into `Index(1..Found)`, in element order, the elements whose
  STRING field contains text$, and sets Found. An empty text$ matches every
  record. Then `DB SORT A, Found, Index, Field, KEEP` sorts the matches.

**Requires:** a database (§8.3) and `DIM Index(n) AS INTEGER` with n at
least Count.

**Common errors**

```pbas-error
' expect-error: sort by an INTEGER, REAL or STRING field
TYPE T
    Id AS INTEGER
    F AS BOOLEAN
END TYPE
DIM A(10) AS T BANKED
DIM N AS INTEGER
DIM I(10) AS INTEGER
DB SORT A, N, I, F
END
```

```pbas-error
' expect-error: a BANKED index is not supported
TYPE T
    Id AS INTEGER
    Name AS STRING * 10
END TYPE
DIM A(10) AS T BANKED
DIM N AS INTEGER
DIM I(10) AS INTEGER BANKED
DB SORT A, N, I, Name
END
```

**Limits**

- The index is an ordinary array, so it has at most 250 entries: **a database
  of more than 250 records cannot be sorted or searched as a whole** (known
  issue KI-56, [limitations](../limitations.md)). An index shorter than Count
  stops the program with `index out of range`.
- `DB SEARCH` text is at most 127 characters.
- A sort reads one field per comparison through an operating-system copy, about
  n·log2(n) reads (under 2,800 for 250 records on the simulator).

## 8.8 The PDB1 file format

You do not need the format to use databases. It is fixed and documented so
that a database can be checked or produced on a PC. All numbers are
little-endian.

| Offset | Size | Content |
|---|---|---|
| 0 | 4 | `PDB1` |
| 4 | 1 | version, 1 |
| 5 | 1 | flags, 0 |
| 6 | 2 | record size |
| 8 | 2 | count |
| 10 | 2 | next identifier |
| 12 | 2 | TYPE signature |
| 14 | 2 | 0 |
| 16 | count × size | the records, in the layout of §8.1 |
| end | 4 | check: s1, s2 |

- The **TYPE signature** is the CRC-16/CCITT-FALSE of the field list written
  as `NAME:I;NAME:S40;NAME:R;NAME:B`, in field order, names in capitals
  (`S40` is `STRING * 40`).
- The **check** runs over every byte of the header and the records, both
  sums starting at 0: s1 = s1 + byte, s2 = s2 + s1, modulo 65536.

**`tools/pdbcheck.py`** checks a database file on the host without changing
it. Give `--type` the field list to check the signature, and `--rows` to
decode records; `--capacity` checks the count against the program's array
length. The exit status is 0 for a valid file and 1 for an invalid one.

```sh
python3 tools/pdbcheck.py PBPETS.PDB --type "ID:I;NAME:S20;AGE:I" --rows 2
```

For the database the first example above saves, it prints the size and
SHA-256 of the file, then `version: 1`, `flags: 0`, `record size: 25`,
`count: 2`, `next identifier: 3`, the signature and the expected signature,
`result: valid`, and the two records (`1 | Rex | 0`, `2 | Ann | 0`).

**See also:** spec §5.8–§5.10; `examples/contacts4.pbas` (the current
address book, on `lib/app.pbas`, `lib/forms.pbas` and `lib/listview.pbas`),
`examples/contacts3.pbas`, `examples/starter.pbas` (a to-do list),
`examples/reporter.pbas`, `examples/designer.pbas`, `developer-tests/dbprobe.pbas`.
