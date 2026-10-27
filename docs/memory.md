# Memory

This page explains where a PcW16 BASIC program's bytes go, why a program can stop building although the PcW16 has plenty of RAM, how to read `pcw16basic memory`, and what to do when a program is full. The figures were measured with the project's own tools on the current examples. Memory sizes are a property of the build, so they are the same in XAnne and on a real PcW16; running out of free RAM at start-up has been exercised only in XAnne and the simulator, not yet on a real PcW16.

## The model in one picture

```text
Z80 addresses      what is there while the program runs
#0000-#3FFF        Rosanne's own block: the stack, and a small runtime
                     work area (file names, menu and drawing workspace)
#4000-#7FFF        the RESIDENT 16K BLOCK, always mapped:
                     prefix (256 bytes)
                     main-line code, one 8-byte stub per procedure
                     ALL ordinary variables and arrays, string cells, literal text
                     window, menu and control definitions
                     the resident part of the runtime and its workspace
#8000-#BFFF        a window: a CODE BANK while banked code runs (your SUBs
                     and FUNCTIONs, or the RUNTIME BANK), a TEXT buffer's
                     block while a TEXT routine runs
#C000-#FFFF        Rosanne's; its copy and drawing routines map blocks here
other 16K blocks   owned by the program: code banks, BANKED arrays, TEXT
                     buffers and BITMAPs, reached by mapping or by
                     Rosanne's copy calls, never directly by your program
```

The PcW16's RAM is handed out by Rosanne in 16K blocks. A program's `.PRG` file is loaded into one block, mapped at #4000. Everything that must be reachable at any moment lives there, so **the resident 16K block is the limit you meet first**: 16,384 bytes for the prefix, main line, data, dialogs and the resident runtime together. More code and more data go into further 16K blocks, which the program asks Rosanne for when it starts. Code is mapped at #8000 while it runs; a BANKED array element is copied in and out by a Rosanne call on every access.

## Code banks: procedures outside the resident block

When a program does not fit in one 16K image, the build puts every SUB and FUNCTION into **code banks** of up to 15,872 bytes each, at most 16 banks. Only an 8-byte stub per procedure stays resident. You change nothing in the source; the default `--code-banks auto` does it when needed (see [building and commands](manual/16-building-and-commands.md) and the [specification](../LANGUAGE-SPEC.md) §5.5).

- One procedure must fit one bank: at most 15,866 bytes of code. Split a larger one.
- The main line stays resident. Move work from the main line into SUBs to free resident bytes.
- At start, the program asks for one 16K block per bank and reads the banks from its own `.PRG` file. So a code-banked program must be run under its own file name, from its own folder, as one whole file (known issue KI-38, [limitations](limitations.md)). If the blocks cannot be had, it stops before its first line with `Runtime error: not enough free memory for the program's code`.
- A call into another bank costs two BIOS calls more than an ordinary call; banks are read once, at start.

Code banks are *Tested in XAnne* (a bank probe, MDEDIT and every large example).

## The runtime bank: runtime code outside the resident block

The runtime (the Z80 code that draws, reads files, runs dialogs, sorts databases and so on) is normally resident. Only the routines a program uses are included. With **`--runtime-banks all`** the build moves the code of the movable runtime sections into one more code bank, the **runtime bank**. Their data stays resident, and each routine called from outside keeps a 6-byte resident entry.

The sections that move are DB, CANVAS, CVLINE, CVCELL, FILES, FIO, FNAME, NUMBERS, MENUS, LIST, CHOICE, SLIDER, BITMAP, BMPFILE, POINT, PAGE and BMPPART (only those the program uses are present). **The REAL library and the common core (string handling, arithmetic, dialogs, the event loop) always stay resident.** `python3 tools/build.py --help` lists fewer section names than actually move.

**The automatic retry.** `pcw16basic build` first builds normally. If the resident part is over 16K, it says

```text
(it does not fit the 16K block with the runtime resident: building with --runtime-banks all)
```

and builds again with `--runtime-banks all`. Calling `tools/build.py` directly does **not** retry: it stops with `the resident part is N bytes, M over the 16384-byte first block even with every procedure in a code bank ...`. The large examples say so in their header (`' Build with --runtime-banks all`).

The runtime bank is *Tested in XAnne* (MDEDIT III, CONTACTS IV, STARTER and all the large graphics programs). A call into it costs three BIOS calls more than a resident call; no difference in speed was measurable in XAnne.

## Data blocks: BANKED arrays, TEXT buffers and BITMAPs

Three kinds of data live outside the resident block, in 16K blocks of their own:

| Declaration | Blocks |
|---|---|
| `DIM A(k) AS type BANKED` | as many as its elements need; an element never crosses a block end |
| `DIM D AS TEXT * bytes` | bytes ÷ 16,384, rounded up (a 30,000-byte buffer takes 2) |
| `DIM B AS BITMAP * w, h` | exactly 1, whatever its size |

Together they may use **at most 32 blocks (512K)**, checked at compile time (`... at most 32 16K blocks together (512K); this one brings the total to 33`). At start the program asks Rosanne for all of them at once. If it cannot have them, it gives back what it got and stops before its first line with `Runtime error: not enough free memory for BANKED arrays` (the wording names arrays, but bitmaps and TEXT buffers count too). How much RAM a particular PcW16 has free beside its documents is reported at start, never assumed.

BANKED arrays are slow: every element access is a Rosanne copy call. LIST and CHOICE cannot show them, and one statement may read at most four BANKED elements. See [variables and types](manual/02-variables-and-types.md).

## String capacity

Every STRING without `* n` has the **program-wide capacity**, 64 bytes by default (63 characters plus the end byte). Set it with `--string-capacity N` (2..127). Measured:

| What | Resident bytes at the default capacity |
|---|---:|
| `DIM S$ AS STRING` | 64 |
| `DIM S$ AS STRING * 10` | 11 |
| a STRING parameter of a SUB or FUNCTION | 64 |
| a STRING `LOCAL` | 64 |
| a STRING FUNCTION: its result | 64 |
| each place in the source that calls a STRING FUNCTION | 64 more |

Parameters and LOCALs are not on a stack: every procedure's parameters and locals have static storage in the resident block, even while the procedure is not running. The last row is known issue KI-83 ([limitations](limitations.md)): temporaries are not shared between call sites, so a STRING FUNCTION called from twenty places costs twenty cells, 1,280 bytes. This is the main cost a large program meets.

So:

- give long-lived strings an explicit `STRING * n` of the size they need;
- pass strings to procedures through a shared global instead of a parameter, as [lib/files.pbas](libraries/files.md) does with `SafeOut$`;
- call a STRING FUNCTION from one place (a SUB that stores its result) rather than from many.

A smaller `--string-capacity` shrinks every cell at once, but it also shortens every string in the program; the build refuses it where a value is known not to fit (DESIGNER does not build with 32: `cannot assign a value of at least 37 characters to the result of FUNCTION INVALID$ with capacity 32`). CONTACTS IV builds with `--string-capacity 48` and then has 416 bytes more resident room; whether a program still behaves correctly with shorter strings is for you to test. A TEXTBOX's string must have a capacity of at most 64 in any case.

## Reading `pcw16basic memory`

`pcw16basic memory FILE.pbas` runs `tools/memreport.py`, which builds the program exactly as `tools/build.py` does and attributes every byte of the resident block. It does not retry with the runtime bank: pass `--runtime-banks all` yourself for a program that needs it. (`pcw16basic memory --help` does not work; use `python3 tools/memreport.py --help`.)

```sh
pcw16basic memory examples/jumper.pbas --runtime-banks all
```

prints:

```text
jumper: resident block 10917 bytes
     256  prefix
    1539  program code
     352  code-bank stubs
     108  runtime-bank veneers
     768  variables
     470  arrays
     228  GUI definitions and tables
     301  static strings and constants
      81  file descriptors
    3407  runtime: common
       0  runtime: REAL library
     111  runtime: files
    1229  runtime: GUI
    2067  runtime workspace and buffers
    5467  free (to the 16K limit)
  code bank 1: 12394 bytes, 44 procedure(s)
  code bank 2: 6692 bytes, 0 procedure(s)
```

| Line | Meaning | What reduces it |
|---|---|---|
| prefix | Rosanne's program header, always 256 | nothing |
| program code | the main line (and every procedure, when the program is not banked) | move main-line work into SUBs |
| code-bank stubs | 8 bytes per SUB and FUNCTION in a code bank | fewer, larger procedures |
| runtime-bank veneers | 6 bytes per runtime routine called in the runtime bank | nothing practical |
| variables | every global, parameter and LOCAL, strings at their capacity | `STRING * n`, shared globals, fewer STRING parameters |
| arrays | ordinary (not BANKED) arrays | `BANKED` for large arrays |
| GUI definitions and tables | windows, controls, menus | fewer windows, controls and menu items |
| static strings and constants | literal text: captions, messages | shorter messages |
| file descriptors | the runtime's records for the files the program names | nothing practical |
| runtime: common / REAL library / files / GUI | the resident runtime code the program uses | `--runtime-banks all` moves the movable part |
| runtime workspace and buffers | the runtime's own buffers | nothing |
| free (to the 16K limit) | what is left | |

The `code bank` lines are the banks in order. **The last one, with 0 procedures, is the runtime bank** when the program is built with `--runtime-banks`. Each holds at most 16,384 bytes.

A program over the limit is still reported, with the line `** N bytes over the 16384-byte limit: it does not build **`. `--sections` adds the resident runtime by section, which shows what the runtime bank would move. `--markdown` prints a table for several programs at once.

`tools/build.py` also warns when fewer than 512 bytes are left: `warning: only 69 bytes left in the resident 16K block`.

## Measured figures for the large examples

All built with `--runtime-banks all`, as they must be: without it each is over the limit (DESIGNER by 7,899 bytes, SPRITED 2,255, PAINT II 1,765, CONTACTS IV 1,124, JUMPER 980, MDEDIT IV 614). Command:

```sh
python3 tools/memreport.py --markdown --runtime-banks all examples/designer.pbas examples/paint2.pbas examples/jumper.pbas examples/sprited.pbas examples/mdedit4.pbas examples/contacts4.pbas
```

| bytes | designer | paint2 | jumper | sprited | mdedit4 | contacts4 |
|---|---:|---:|---:|---:|---:|---:|
| **resident block** | **16,315** | **11,425** | **10,917** | **11,868** | **14,159** | **13,192** |
| program code | 550 | 588 | 1,539 | 440 | 343 | 691 |
| code-bank stubs | 776 | 640 | 352 | 472 | 552 | 384 |
| runtime-bank veneers | 228 | 120 | 108 | 126 | 102 | 102 |
| variables | 1,882 | 1,416 | 768 | 1,270 | 1,077 | 2,078 |
| arrays | 1,030 | 132 | 470 | 306 | 284 | 428 |
| GUI definitions and tables | 2,294 | 700 | 228 | 655 | 1,629 | 1,546 |
| static strings and constants | 1,440 | 729 | 301 | 904 | 553 | 649 |
| file descriptors | 27 | 27 | 81 | 14 | 27 | 28 |
| runtime: common | 3,931 | 3,466 | 3,407 | 3,744 | 5,673 | 3,598 |
| runtime: files | 111 | 111 | 111 | 111 | 111 | 111 |
| runtime: GUI | 1,609 | 1,136 | 1,229 | 1,461 | 1,604 | 1,313 |
| runtime workspace and buffers | 2,181 | 2,104 | 2,067 | 2,109 | 1,948 | 2,008 |
| **free in the resident block** | **69** | **4,959** | **5,467** | **4,516** | **2,225** | **3,192** |
| code banks (bytes used) | 15,871 + 12,580 + 8,393 | 15,872 + 1,449 + 6,987 | 12,394 + 6,692 | 15,871 + 248 + 7,043 | 15,871 + 5,929 + 3,075 | 11,416 + 4,552 |
| `.PRG` file | 53,760 | 40,960 | 36,352 | 39,936 | 41,984 | 32,768 |

The prefix (256) and the REAL library (0 in all six) are left out of the table. In the code-bank row the last figure is the runtime bank.

Data blocks taken at start, outside the resident block:

| Program | Blocks |
|---|---|
| DESIGNER | 4: two BITMAPs (icons, a 544 × 240 picture) and two BANKED record arrays |
| PAINT II | 5 BITMAPs: two pictures, the floating selection, the board and the icons |
| JUMPER | 7 BITMAPs: three sprite sheets, their three masks, and the background |
| MDEDIT IV | 14: seven 30,000-byte TEXT buffers (the document, the clipboard, four undo copies and a swap), 2 blocks each |

What these show:

- **DESIGNER is full: 69 bytes free.** Its resident data is the scene library's five 100-element arrays (1,000 bytes), three windows and two menus (2,294 bytes of GUI tables) and its strings. It fits only because its scene holds 100 objects, not more, and because it passes strings in one shared variable instead of STRING parameters. Adding a feature to DESIGNER means first taking bytes out of the resident block.
- **MDEDIT IV** has 2,225 bytes free; its first code bank is full and new procedures go to the next bank automatically.
- **PAINT II, SPRITED and JUMPER** have 4.5K to 5.5K free; **CONTACTS IV** about 3K.
- The runtime is the largest single part: its resident code and workspace take 6.8K to 9.3K of each of these programs' resident blocks even after the runtime bank has taken what can move.

For comparison, the first tutorial program (`examples/tutorial/t1_hello.pbas`) is a single 3,447-byte image with 12,937 bytes free, and needs no code bank at all.

## Staying within the limits

In order of effect, for a program that is full or nearly full:

1. **Build with `--runtime-banks all`.** `pcw16basic build` does it for you when it must; nothing in the source changes.
2. **Make large arrays BANKED.** An ordinary array is always resident: 250 INTEGERs are 500 bytes, 100 strings at the default capacity are 6,400 bytes. A BANKED array costs almost nothing resident. Copy the rows you show into a small ordinary array for a `LIST`.
3. **Cut string cells.** Use `STRING * n` for every string that does not need 63 characters, especially arrays of strings. Replace STRING parameters with a shared global. Call each STRING FUNCTION from as few places as possible (KI-83).
4. **Move main-line work into SUBs.** The main line is resident; procedures are banked.
5. **Spend GUI bytes carefully.** Every window, control and menu item costs table bytes in the resident block. A canvas drawn with a library such as [listview](libraries/listview.md) can replace several controls.
6. **Shorten literal text.** Long MESSAGE texts and captions are resident.
7. **Check with `pcw16basic memory`** after each change, and keep a margin: the build warns below 512 bytes.

Some costs cannot be moved: the 256-byte prefix, the REAL library (about 0.9K to 1.2K when a program uses REAL, including through [lib/chart.pbas](libraries/chart.md)), the common runtime core, the runtime's workspace, and all ordinary variables and arrays. Each library's page gives its own measured cost; the [library index](libraries/README.md) compares them.

## What happens at start-up

Before the first line of the program runs, it asks Rosanne for, in this order, one block per code bank (including the runtime bank) and then every data block. Each block is checked to be RAM belonging to the program. If any request fails, the program gives back every block it got and ends with one of:

- `Runtime error: not enough free memory for the program's code`
- `Runtime error: the program's code could not be read from its file` (the file is missing, renamed, damaged or shorter than built)
- `Runtime error: not enough free memory for BANKED arrays`

All blocks are given back however the program ends: `END`, `EXIT`, a runtime error, or Rosanne's Quit. Getting, using and giving back the blocks is *Tested in XAnne* (the BANKED-array benchmarks and every large example, JUMPER with seven bitmaps, MDEDIT IV with fourteen TEXT blocks). The not-enough-memory stop is checked on the simulator only, and the amount of free RAM on a real PcW16 with documents open is not known, so a program that needs many blocks should be tried on the machine it is meant for.

See also: [building and commands](manual/16-building-and-commands.md), [variables and types](manual/02-variables-and-types.md), [bitmaps and sprites](manual/13-bitmaps-and-sprites.md), [limitations](limitations.md), [libraries](libraries/README.md), and the [specification](../LANGUAGE-SPEC.md) §5.4–§5.5.
