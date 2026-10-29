# 16. Building and commands

This chapter describes every command of the toolchain: the `pcw16basic` command, the build
script `tools/build.py` and its options, the checker `python3 -m pbas check`, and the
helper tools for pictures, databases, memory and assembly. The outputs shown were produced by
running the commands (Linux, Python 3.13, Pasmo 0.5.3); paths are shortened to `~/PcW16-BASIC`.

Only Linux has been exercised. The commands are plain Python and should work the same on
Windows and macOS, but that is *untested*.

Installation is in [install](../install.md); copying the result to XAnne is in
[Running in XAnne](../running-in-xanne.md).

Contents: [Running the commands](#running-the-commands) · [doctor](#pcw16basic-doctor) ·
[new](#pcw16basic-new) · [check](#pcw16basic-check) · [build](#pcw16basic-build) ·
[tools/build.py options](#toolsbuildpy-options) · [What a build writes](#what-a-build-writes) ·
[assets and image](#pcw16basic-assets-and-pcw16basic-image) · [memory](#pcw16basic-memory) ·
[test](#pcw16basic-test) · [python3 -m pbas check](#python3--m-pbas-check) ·
[pbicheck.py](#toolspbicheckpy) · [pdbcheck.py](#toolspdbcheckpy) · [asmcheck.py](#toolsasmcheckpy) ·
[Remaining quirks of the commands](#remaining-quirks-of-the-commands)

## Running the commands

In the repository folder, run `python3 pcw16basic COMMAND …`. After
`python3 -m pip install -e .` in that folder, the command `pcw16basic` works from anywhere
(it runs the files where they are). Every `pcw16basic` command drives a script in `tools/`,
which you can also run directly.

Python writes compiled copies of the modules it runs into `__pycache__/` folders inside the
repository. Set `PYTHONDONTWRITEBYTECODE=1` in the environment to prevent it, for example for a
read-only copy; `python3 -B` is not enough, because `build` and `check` start further Python
processes ([install](../install.md#getting-pcw16-basic)).

```sh
pcw16basic --help
pcw16basic --version
```

```text
usage: pcw16basic [-h] [--version]
                  {doctor,new,check,build,image,memory,assets,test} ...

positional arguments:
  {doctor,new,check,build,image,memory,assets,test}
    doctor              check Python, Pasmo and the install
    new                 a new project folder
    check               compile-check a program
    build               compile a program to a .PRG
    image               PNG and PBI1 pictures (tools/pbimage.py)
    memory              the resident block, by part (tools/memreport.py)
    assets              make the PBI1 files a manifest lists
    test                the test suite (tools/run_tests.py)
...
PcW16 BASIC 1.0.0rc2
```

`--help` after a subcommand shows that command's options: `pcw16basic check --help`,
`pcw16basic build --help` (the options of `tools/build.py`), `pcw16basic image --help` and
`pcw16basic memory --help`. (Up to M13 these failed with `unrecognized arguments: --help`.)

A copy installed with a plain (non-editable) `pip install .` is not supported: every
`pcw16basic` command except `--version` then stops with exit status 2 and a message that it
must be run from its own folder or installed with `pip install -e .` ([install](../install.md)).

## pcw16basic doctor

```sh
pcw16basic doctor
```

Checks Python (3.10 or later), that Pasmo is on the PATH, and that the install's main files are
present. Exit status 0 when ready.

```text
ok   Python 3.13.16 (needs 3.10 or later; no other packages)
ok   Pasmo: /usr/bin/pasmo (0.5.3 is the version tested)
ok   runtime/runtime.z80.asm
ok   tools/build.py
ok   tools/pbimage.py
ok   examples/lib/sprite.pbas
ok   LANGUAGE-SPEC.md
PcW16 BASIC 1.0.0rc2 at ~/PcW16-BASIC
ready
```

A `FAIL` line says what to fix. Without Pasmo you can still `check`, but not `build`.

## pcw16basic new

```sh
pcw16basic new NAME [--kind app|game] [--dir FOLDER]
```

Makes a project folder `NAME` (or `FOLDER`) holding `NAME.pbas`, a copy of the libraries in
`lib/`, and `assets/ASSETS.txt` (an empty picture manifest). `--kind app` (the default) writes a
window with a status line, a canvas you click on, two buttons and a menu. `--kind game` writes
a sprite that runs with Left and Right and jumps with Space, paced by the clock. Both build as
they are.

```text
$ pcw16basic new myapp
myapp/myapp.pbas  (a starting point)
myapp/lib/         (the libraries: docs/libraries/README.md)
myapp/assets/      (PNG pictures and ASSETS.txt)
next: cd myapp && pcw16basic build myapp.pbas
```

The `next:` line says `pcw16basic build` when the `pcw16basic` command is on the `PATH`
(an editable install, above). Otherwise it gives the script you ran with its full path, for
example `next: cd myapp && python3 /path/to/PcW16-BASIC/pcw16basic build myapp.pbas`.

The first lines of `NAME.pbas` say how to build it and to copy `build/NAME.prg` to the PcW16 as
`NAME.PRG` in capitals. `NAME` keeps the case you typed, because the build names its output after
the source file: `pcw16basic new MyApp` writes `MyApp/MyApp.pbas`, whose header says to copy
`build/MyApp.prg` to the PcW16 as `MYAPP.PRG`.

The comments at the top of the templates point to the [manual](README.md), the
[libraries](../libraries/README.md), [chapter 13](13-bitmaps-and-sprites.md) (sprites, in the
game template) and [Making pictures](../graphics-assets.md).

Errors (nothing is written):

```text
$ pcw16basic new myapp
pcw16basic new: myapp already exists; choose another name (nothing was written)
$ pcw16basic new toolongname
pcw16basic new: the name is a PcW16 program name: letters, digits and _, at most 8
```

## pcw16basic check

```sh
pcw16basic check PROGRAM.pbas [--string-capacity N] [--ast] [--symbols]
```

Runs everything `build` runs except the assembler and the final memory fit: syntax,
declarations and types, the window layout and code generation. It does not need Pasmo and
writes no file. It prints the same warnings as `build`.

```text
$ pcw16basic check myapp.pbas
OK: myapp.pbas (313 statements, 67 variables); syntax, type, layout and code checks passed. No PRG generated: whether it fits the PcW16's memory is checked by build.
$ pcw16basic check typo.pbas
typo.pbas:3:9: undefined variable GRETING$; declare it with DIM or a UI binding
$ pcw16basic check nobtn.pbas
nobtn.pbas:1:1: a WINDOW needs at least one BUTTON: a window without buttons has no tested way to be closed (add, for example, BUTTON "Quit", Quit with a SUB Quit that runs EXIT)
```

Every message starts `file:line:column:`. Exit status 0 when the program passes.

So `check` reports a WINDOW with no BUTTON or more than 6 buttons, a window whose controls do
not fit its layout, a CANVAS too wide for its window, and a TEXTBOX bound to a string of more
than 63 characters. (Up to M13 it ran only the front end, and these were reported only by
`build`.) **What only `build` finds** is a program whose resident part does not fit the 16K
block (`the resident part is N bytes, …`), because that needs the assembler.

Use `check` while you type; always `build` before you call a program correct.

## pcw16basic build

```sh
pcw16basic build PROGRAM.pbas [tools/build.py options]
```

Compiles the program to Z80 assembly, assembles it with Pasmo, and writes `build/NAME.prg`
(the folder `build` is made beside where you run it unless you give `--out-dir`). It passes
its options to `tools/build.py` (next section).

```text
$ pcw16basic build myapp.pbas
asm: build/myapp.asm (392385 bytes)
prg: build/myapp.prg (9686 bytes, sha256 27a1d21feccf63c8d3f0e2873e4f5b777120a35c37530cb449b8521543400d06)
included: lib/app.pbas: lines 1001..1999
included: lib/geom.pbas: lines 2001..2999
```

The `included:` lines tell you how to read a runtime error's line number: an error "at line
1042" is line 42 of `lib/app.pbas` (the k-th included file starts at 1000 × k + 1).

**Automatic retry with `--runtime-banks all`.** When the program's resident part (its main
line, variables, dialogs and the runtime) does not fit the first 16K, `pcw16basic build` builds
again with `--runtime-banks all` and says so. `tools/build.py` alone stops with the error:

```text
$ python3 tools/build.py jumper.pbas
jumper.pbas:1:1: the resident part is 17364 bytes, 980 over the 16384-byte first block even
with every procedure in a code bank: ... (move work into SUBs, or large arrays to BANKED; or
move runtime code to a code bank of its own (tools/build.py --runtime-banks all));
tools/memreport.py shows where the bytes go
$ pcw16basic build jumper.pbas
(it does not fit the 16K block with the runtime resident: building with --runtime-banks all)
asm: build/jumper.asm (218491 bytes)
prg: build/jumper.prg (36352 bytes, sha256 e1739f94...)
included: lib/geom.pbas: lines 1001..1999
included: lib/sprite.pbas: lines 2001..2999
included: lib/keys.pbas: lines 3001..3999
included: lib/pace.pbas: lines 4001..4999
code banks: 2 (resident 10917 bytes; map build/jumper.map)
runtime bank: 2 (DB CANVAS CVLINE CVCELL FILES FIO FNAME NUMBERS MENUS LIST CHOICE SLIDER BITMAP BMPFILE POINT PAGE BMPPART; 18 entries)
```

Warnings (lines with `warning:`) do not stop the build; read them. The common one is about a
dynamic LABEL that can hold more than 24 characters
([chapter 10](10-windows-and-controls.md#label)).

**Copy the `.prg` to the PcW16 as `NAME.PRG`**, in the folder the program was built for, with
any files it loads ([Running in XAnne](../running-in-xanne.md),
[real hardware](../real-hardware.md)). A program with code banks reads the rest of its own file
when it starts, so it must be run under its own file name from its own folder, and copied whole
(known issue KI-38, [limitations](../limitations.md)).

## tools/build.py options

```sh
python3 tools/build.py SOURCE.pbas [options]
```

| Option | Meaning |
|---|---|
| `--out-dir DIR` | where to write the results (default `build`; made if missing) |
| `--asm PATH` | the assembly file (default `DIR/NAME.asm`) |
| `--prg PATH` | the executable (default `DIR/NAME.prg`), e.g. `--prg out/HELLO.PRG` for an upper-case name |
| `--string-capacity N` | the program-wide STRING capacity in bytes including the end byte: 2 to 127, default 64 (63 characters). A smaller value saves resident memory; `STRING * n` sets one variable's size instead |
| `--drive DRIVE` | the drive for the program's files: only `floppy` (the default) is accepted |
| `--folder PATH` | the folder, on that drive, where the program reads and writes **all** its files (data, pictures, databases): default `\PCW\FOLDER01`, the folder the PcW16's File Manager uses. The program never creates it |
| `--code-banks auto\|always\|never` | `auto` (default): put SUBs and FUNCTIONs in 16K code banks only when the program does not fit one 16K image; `always`: bank every procedure; `never`: fail if it does not fit |
| `--code-bank-limit BYTES` | at most BYTES per code bank (64 to 15872, the default and maximum); spreads a small program over several banks (for testing) |
| `--runtime-banks all\|SECTION,…` | move the code of runtime sections to a bank of their own, freeing resident memory. `all` moves every movable one present: DB, CANVAS, CVLINE, CVCELL, FILES, FIO, FNAME, NUMBERS, MENUS, LIST, CHOICE, SLIDER, BITMAP, BMPFILE, POINT, PAGE, BMPPART. Implies code banks |
| `--whole-real-library` | assemble the whole REAL arithmetic library instead of only the parts used. Only for rebuilding old executables byte for byte |
| `--legacy-menu-hotkeys` | give menu items without `KEY` the old hotkey word that stopped later shortcuts working. Only for rebuilding old executables |
| `--legacy-timing` | make `EVERY n TICKS` a Rosanne timer and `CLOCKTICKS` the raw clock byte, as in older builds whose timers paused in XAnne. Only for rebuilding old executables |
| `--legacy-file-safety` | build `DB SAVE`, `BITMAP SAVE` and `DB LOAD` as before M14: no check of `NAME.NEW` and `NAME.BAK` (no IOERR 253), a backup deleted on a first save, and any load failure falling back to an older copy. **Only to reproduce older accepted executables byte for byte**; it brings back the defects M14 corrected |
| `--legacy-real-rounding` | build REAL `+` and `-` as before M14, when a result just under half a unit in the last place could round the wrong way. **Only to reproduce older accepted executables byte for byte** |

Do not use the last five for new programs. A program that uses `DB LOAD`, `DB SAVE`,
`BITMAP SAVE` or REAL arithmetic compiles to different bytes from an M13 build unless the
matching legacy option is given.

Examples and errors:

```text
$ python3 tools/build.py myapp.pbas --folder '\PCW\GAMES' --out-dir out2 --prg out2/APP.PRG
asm: out2/myapp.asm (392385 bytes)
prg: out2/APP.PRG (9686 bytes, sha256 27a1d21f...)
$ python3 tools/build.py myapp.pbas --string-capacity 128
myapp.pbas:1:1: string capacity must be between 2 and 127
$ python3 tools/build.py myapp.pbas --drive flash
build.py: --drive=flash is not supported: Rosanne's flash folders are numbered and their file
naming is not documented in the material the project has; use --drive=floppy (the default)
$ python3 tools/build.py myapp.pbas --code-banks always --code-bank-limit 10
myapp.pbas:1:1: code bank limit must be 64..15872 bytes
$ python3 tools/build.py jumper.pbas --runtime-banks FOO
jumper.pbas:1:1: runtime section(s) FOO cannot be moved to a code bank; movable: DB, CANVAS, ...
```

The same source always gives the same bytes, and the sha256 printed lets you check a copy.

## What a build writes

| File | When |
|---|---|
| `NAME.asm` | always: the program and the parts of the runtime it uses |
| `NAME.prg` | always, when assembly succeeds: the Rosanne executable |
| `NAME.bank1.asm`, `NAME.bank2.asm`, … | with code banks: each bank's assembly |
| `NAME.map` | with code banks only: the resident size and every bank's procedures and sizes |
| `NAME.sym` | with code banks: the assembler's symbols |

A `.map` begins like this (`jumper.pbas` with `--runtime-banks CANVAS,BITMAP`):

```text
; PcW16 BASIC code-bank map (generated; pbas/codebanks.py)
resident 15821 of 16384 bytes (padded to 16384)
bank 1: 12394 bytes used, 12800 in the file, 44 procedure(s)
    entry  0 at 8003h  sub_GEOMIN  184 bytes
    ...
```

Memory and banks are explained in [memory](../memory.md).

## pcw16basic assets and pcw16basic image

```sh
pcw16basic assets [MANIFEST] [OUTDIR]
pcw16basic image import|sheet|export|info|build ...
```

`assets` makes every `.PBI` picture a manifest lists (`tools/pbimage.py build`). With no
arguments it uses `assets/ASSETS.txt` if the current folder has one, otherwise the examples'
`examples/assets/ASSETS.txt`, and writes to `build`:

```text
$ pcw16basic assets
build/P2ICONS.PBI: 6 frames of 24 x 24, a 24 x 144 strip; frame k is the part 0, k * 24, 24, 24
build/JHERO.PBI: 8 frames of 16 x 24, a 16 x 192 strip; frame k is the part 0, k * 24, 16, 24
build/JHEROM.PBI: the mask strip
...
build/T3HEROM.PBI: the mask strip
```

`image` passes everything to `tools/pbimage.py`. Both are described in full, with every option,
in [Making pictures](../graphics-assets.md).

## pcw16basic memory

```sh
pcw16basic memory PROGRAM.pbas [--runtime-banks all|SECTION,...] [--string-capacity N]
                               [--sections] [--markdown] [--whole-real-library]
```

Runs `tools/memreport.py`: where the resident 16K block goes, by part. Use it when a build says
the resident part is too large.

```text
$ pcw16basic memory jumper.pbas
jumper: image 17364 bytes
  ** 980 bytes over the 16384-byte limit: it does not build **
     256  prefix
    1887  program code
       0  code-bank stubs
       0  runtime-bank veneers
     768  variables
     470  arrays
     228  GUI definitions and tables
     301  static strings and constants
      81  file descriptors
    8739  runtime: common
       0  runtime: REAL library
    1345  runtime: files
    1229  runtime: GUI
    2060  runtime workspace and buffers
    -980  free (to the 16K limit)
$ pcw16basic memory jumper.pbas --runtime-banks all
jumper: resident block 10917 bytes
...
    5467  free (to the 16K limit)
  code bank 1: 12394 bytes, 44 procedure(s)
  code bank 2: 6692 bytes, 0 procedure(s)
```

**Its figures and `build`'s.** `memory` measures the build you ask for and does not retry:
without `--runtime-banks` the runtime stays resident. `pcw16basic build` retries by itself with
`--runtime-banks all`, so when even that build does not fit, its message (`… N over … even with
every procedure in a code bank`) is about the runtime-banked build and can be much smaller than
`memory`'s plain figure. Run `pcw16basic memory PROGRAM.pbas --runtime-banks all` to see the
same figure as that message. For a program that does not fit, `memory` prints `image` even when
its procedures are in code banks, and counts their 8-byte stubs as program code.

`--sections` adds the resident runtime's bytes by section, the names `--runtime-banks` takes;
`--markdown` prints a table. `tools/memreport.py` accepts several sources at once.

## pcw16basic test

```sh
pcw16basic test [fast|full]
python3 tools/run_tests.py fast|full|module NAME...|list [-j JOBS]
```

Runs the project's own test suite (the compiler, the runtime on the simulator, the examples and
the tools), each module in its own process. `fast` (the default) leaves out the slow modules;
`full` runs every module. `list` shows the modules and their tier; `module NAME` runs chosen
ones. Each module prints a line, and a summary ends the run:

```text
ok        65 tests      0.4 s  test_parser
ok        63 tests      0.1 s  test_semantics
...
fast: N modules, N tests, N failed, N s wall clock with 4 job(s) ...
```

On the machine used for this manual `fast` took about nine minutes with four jobs. The tests
check the compiler and the simulator's model of the PcW16; passing them does not show how a
program behaves in XAnne or on a PcW16 ([CONTRIBUTING](../../CONTRIBUTING.md)).

## python3 -m pbas check

```sh
python3 -m pbas check [--ast] [--symbols] [--string-capacity N] SOURCE.pbas
```

The checker that `pcw16basic check` runs. Run it from the repository folder (or with
that folder on `PYTHONPATH`, or after `pip install -e .`). `--symbols` prints the analysed
variable table as JSON; `--ast` prints the parsed program as JSON. They are for tools and for
investigating how the compiler reads a program.

With `--symbols` or `--ast` it prints the JSON instead of the `OK:` line:

```text
$ python3 -m pbas check --symbols tiny.pbas
{
  "N": {
    "name": "N",
    "type": "INTEGER",
    "capacity": null,
    "origin": "DIM",
    "line": 1,
    "column": 1,
    ...
  }
}
```

## tools/pbicheck.py

```sh
python3 tools/pbicheck.py PICTURE.PBI [--pbm picture.pbm]
python3 tools/pbicheck.py --from-pbm picture.pbm PICTURE.PBI
```

Checks a PBI1 picture file on the PC (for example one a program saved with `BITMAP SAVE`), and
converts it to or from a PBM image. It never changes the file it checks. Exit status 0 valid,
1 not valid (it gives the `IOERR` that `BITMAP LOAD` would), 2 usage.

```text
$ python3 tools/pbicheck.py HERO.PBI --pbm hero.pbm
version: 1
width: 16
height: 192
row: 2
bytes: 384
result: valid
wrote hero.pbm
$ python3 tools/pbicheck.py hero.pbm
result: NOT valid (248: not a PBI1 file)
```

## tools/pdbcheck.py

```sh
python3 tools/pdbcheck.py FILE.PDB [--type SIGNATURE] [--capacity N] [--rows N]
```

Checks a PDB1 database file (written by `DB SAVE`, [chapter 8](08-records-and-databases.md)) on
the PC. Read-only. `--type` gives the record's field list (for example `"ID:I;NAME:S40"`) to
check it against and to decode records with `--rows`; `--capacity` is the program's array
length.

```text
$ python3 tools/pdbcheck.py CONTACTS.PDB
file: CONTACTS.PDB (17300 bytes)
sha256: 3116ca9f...
version: 1
flags: 0
record size: 108
count: 160
next identifier: 161
signature: 0FD1h
result: valid
```

A damaged file ends `result: NOT VALID — DB LOAD would give 251 (damaged)` with exit status 1.

## tools/asmcheck.py

```sh
python3 tools/asmcheck.py build/NAME.asm
```

A static check of generated Z80 assembly against the project's own rules (for contributors
changing the code generator).

```text
$ python3 tools/asmcheck.py myapp/build/myapp.asm
myapp/build/myapp.asm: OK
```

Give a build's `.asm` alone: it already contains the runtime. Add `runtime/runtime.z80.asm`
only for compiler output without the runtime (its `--help` says the same).

## Remaining quirks of the commands

- `pcw16basic check` does not check the memory fit; only `build` does (above).
- `pcw16basic memory` on a program over 16K that has no SUB or FUNCTION stops with a Python
  traceback ending in `assembled image is N bytes, over the 16384-byte .PRG image limit`,
  instead of a report. `build` gives the same figure as a plain message.
- A plain (non-editable) `pip install .` is not supported: `pcw16basic` then stops with exit
  status 2 and says to run it from its folder or install it with `pip install -e .`.
- Some help texts still name engineering documents that are not part of this repository, for
  example `pcw16basic image --help` (`docs/M13-GRAPHICS-ASSETS.md`); the
  [documentation index](../README.md#references-in-the-source) maps them to the public pages.

Fixed in M14: `--help` after a subcommand; `check` running only the front end; the TEXTBOX
capacity message blaming `--string-capacity`; `tools/libref.py` now has `--help` and
`--check`, and rewrites the reference only when run without arguments; `pbimage.py info` on a
missing file gives a one-line message; `tools/pbicheck.py` refuses an extra argument;
`tools/build.py --help` lists every runtime section; messages no longer contain internal stage
names such as `M4`.

**See also.** [install](../install.md), [troubleshooting](../troubleshooting.md),
[memory](../memory.md); spec [§5.5](../../LANGUAGE-SPEC.md#55-m9--code-banks-programs-larger-than-16k)
(code banks and the runtime bank).
