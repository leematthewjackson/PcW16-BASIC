# 7. Text buffers (`TEXT`)

A TEXT buffer holds a whole document — up to 65,535 bytes — outside the
program's 16K block. You load it from a file, edit it line by line with the
`TEXT` statements, read parts of it with the `TEXT…` functions, and save it
again. The editors `examples/mdedit.pbas` to `examples/mdedit4.pbas` are
built on it. The normative text is
[LANGUAGE-SPEC.md](../../LANGUAGE-SPEC.md) §5.7.

**Evidence:** tested in XAnne (MDEDIT loaded, edited and saved a test
document byte for byte; MDEDIT II exercised ranges, the clipboard and undo).
The examples below run on the project's simulator. Not yet tested on a real
PcW16.

## 7.1 Declaring a buffer

**Syntax**

```text
DIM D AS TEXT * bytes          bytes from 1 to 65535
```

**Meaning**

- The buffer can hold up to `bytes` bytes. It lives in 16K blocks the program
  gets from Rosanne when it starts; they count towards the same 32-block
  (512K) limit as BANKED arrays and BITMAPs
  ([chapter 2](02-variables-and-types.md#27-banked-arrays)).
- A new buffer is empty: one empty line.
- A buffer is used only through the statements and functions in this
  chapter. It cannot be compared, passed as a parameter, returned, put in an
  array or record, or shown in a control.

**Requires:** a `DIM` (like every `DIM`, it is global even inside a
procedure).

**Common errors**

```pbas-error
' expect-error: declare a text buffer as DIM D AS TEXT * bytes (1 to 65535 bytes
DIM D AS TEXT * 0
END
```

```pbas-error
' expect-error: a TEXT buffer is declared with DIM at the top level, not as a parameter
DIM D AS TEXT * 10
SUB S(T AS TEXT)
END SUB
END
```

**A buffer cannot be assigned.** `D = E` is a compile error (up to M13 it
compiled and did nothing). Use `TEXT COPY` and `TEXT PASTE` to copy text
between buffers.

```pbas-error
' expect-error: D is a TEXT buffer and cannot be assigned
DIM D AS TEXT * 100
DIM E AS TEXT * 100
D = E
END
```

## 7.2 Lines, columns and bytes

- The buffer holds the document's bytes **exactly**: CR, LF, tabs, zero bytes
  and bytes over 127 included. Loading and saving an unchanged document gives
  the same file.
- A line ends at LF; a CR just before the LF belongs to the line end. The
  last line has no end, so a document that ends with a line end has an empty
  last line. `TEXTLINES(D)` is the number of LFs + 1.
- Lines count from 1. Columns are byte positions from 1; a line's length
  does not include its end. Where a statement takes a column, 1 to length + 1
  is allowed (length + 1 is just after the last character).
- A *range* `n1, c1, n2, c2` runs from line n1, column c1 up to but not
  including line n2, column c2. The start may not be after the end.

## 7.3 Statements

**Syntax**

```text
TEXT LOAD D, name$                      empty D, then read the whole file
TEXT SAVE D, name$                      write D's bytes, creating or replacing the file
TEXT CLEAR D                            empty D
TEXT INSERT D, n, col, s$               insert s$ (no CR or LF) in line n before col
TEXT DELETE D, n, col, count            delete count bytes of line n from col
TEXT SPLIT D, n, col                    end line n before col; the rest becomes line n + 1
TEXT JOIN D, n                          join line n + 1 onto line n
TEXT REMOVE D, n1, c1, n2, c2           delete a range (lines n1..n2 join)
TEXT COPY Dst, Src                      Dst becomes a copy of Src
TEXT COPY Dst, Src, n1, c1, n2, c2      Dst becomes a copy of the range (a clipboard)
TEXT PASTE Dst, n, col, Src             insert all of Src into Dst before line n, col
```

**Meaning**

- `TEXT LOAD` and `TEXT SAVE` set `IOERR` ([chapter 6](06-files.md#67-ioerr)).
  A file larger than the buffer gives `IOERR` 246 and leaves the buffer
  empty. The name is a literal or any STRING expression; an invalid name sets
  `IOERR` 247.
- `TEXT SAVE` replaces an existing file without a backup. For a document the
  user cares about, save under a temporary name and swap it in
  ([chapter 6](06-files.md#69-safe-file-handling)).
- `TEXT SPLIT` makes the new line end of the same kind as line n's own (CR LF
  or LF); for the last line, of the kind the loaded file used first.
- `TEXT COPY` and `TEXT PASTE` need two different buffers. The destination of
  a COPY also takes the source's line-end style.
- An edit that fails leaves the buffers unchanged.

**Example**

```pbas
' expect-message: 2 [ world]
' expect-message: 2 2
' expect-message: 11 11 189
' expect-message: world
' expect-message: 0 world
DIM D AS TEXT * 200
TEXT INSERT D, 1, 1, "hello world"
TEXT SPLIT D, 1, 6
MESSAGE STR$(TEXTLINES(D)) + " [" + TEXTGET$(D, 2, 1, 20) + "]"
MESSAGE STR$(TEXTFIND(D, "wor", 1, 1)) + " " + STR$(TEXTCOL(D))
TEXT JOIN D, 1
MESSAGE STR$(TEXTLEN(D, 1)) + " " + STR$(TEXTSIZE(D)) + " " + STR$(TEXTFREE(D))
TEXT DELETE D, 1, 1, 6
MESSAGE TEXTGET$(D, 1, 1, 50)
TEXT SAVE D, "PBTEXT.TXT"
TEXT CLEAR D
TEXT LOAD D, "PBTEXT.TXT"
MESSAGE STR$(IOERR) + " " + TEXTGET$(D, 1, 1, 50)
END
```

**Example: ranges, a clipboard and paste**

```pbas
' expect-message: 2 [first|second]
' expect-message: ficond  line
' expect-message: same
DIM D AS TEXT * 200
DIM Clip AS TEXT * 200
TEXT INSERT D, 1, 1, "first line"
TEXT SPLIT D, 1, 6
TEXT INSERT D, 2, 1, "second "
TEXT COPY Clip, D, 1, 1, 2, 7
MESSAGE STR$(TEXTLINES(Clip)) + " [" + TEXTGET$(Clip, 1, 1, 20) + "|" + TEXTGET$(Clip, 2, 1, 20) + "]"
TEXT REMOVE D, 1, 3, 2, 3
MESSAGE TEXTGET$(D, 1, 1, 40)
TEXT CLEAR D
TEXT PASTE D, 1, 1, Clip
IF TEXTSAME(Clip, D) THEN
    MESSAGE "same"
END IF
END
```

**Runtime errors**

- A line or column outside the allowed range:
  `Runtime error: text position out of range at line N`.
- An insertion, split, copy or paste that does not fit:
  `Runtime error: the TEXT buffer is full at line N` (check `TEXTFREE` first).
- CR or LF in `TEXT INSERT` text:
  `Runtime error: TEXT INSERT text has a line break at line N` (use
  `TEXT SPLIT` to make a new line).

```pbas
' expect-message: Runtime error: text position out of range at line 3
DIM D AS TEXT * 10
TEXT INSERT D, 2, 1, "x"
END
```

```pbas
' expect-message: Runtime error: the TEXT buffer is full at line 3
DIM D AS TEXT * 5
TEXT INSERT D, 1, 1, "abcdef"
END
```

**Common errors**

```pbas-error
' expect-error: TEXT COPY needs two different buffers
DIM D AS TEXT * 10
TEXT COPY D, D
END
```

## 7.4 Functions

| Function | Result | Meaning |
|---|---|---|
| `TEXTLINES(D)` | INTEGER | number of lines (at least 1) |
| `TEXTLEN(D, n)` | INTEGER | length of line n, without its end |
| `TEXTGET$(D, n, col, count)` | STRING | at most count bytes of line n from col; fewer at the line's end; a zero byte comes back as `?` |
| `TEXTFIND(D, s$, n, col)` | INTEGER | the line where s$ next occurs at or after line n, column col (case matters; never across a line end); 0 if not found or s$ is empty |
| `TEXTCOL(D)` | INTEGER | the column of the last `TEXTFIND` match (0 after none) |
| `TEXTCHANGED(D)` | BOOLEAN | TRUE after an edit, until the next `TEXT LOAD`, successful `TEXT SAVE` or `TEXT CLEAR` |
| `TEXTFREE(D)` | INTEGER | bytes free (at most 32767 is reported) |
| `TEXTSIZE(D)` | INTEGER | bytes used (at most 32767 is reported) |
| `TEXTSAME(D1, D2)` | BOOLEAN | TRUE if the two buffers hold the same bytes |

`TEXTGET$` returns at most 126 bytes, and at most what fits the STRING it is
assigned to; read a long line in pieces.

## 7.5 Limits

- 1 to 65,535 bytes per buffer; all buffers, BANKED arrays and BITMAPs
  together at most 512K.
- `TEXT LOAD` reads one byte per operating-system call, so loading a 5 KB
  document takes seconds (known issue KI-43, [limitations](../limitations.md)).
  Saving is faster.
- Lines are not limited in length.
- The first edit far from the previous one moves the buffer's gap, which
  takes longer for a large document. Copies between buffers move 128 bytes at
  a time; XAnne speeds are not measured.

**See also:** spec §5.7; `examples/mdedit.pbas` (the simplest editor),
`examples/mdedit2.pbas` (selection, clipboard, undo, find and replace),
`examples/mdedit4.pbas` (the current editor, with word wrap); the test
document `developer-tests/edtest.md`.
