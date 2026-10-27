# Developer tests: XAnne probes and edge-case programs

> **Advanced material, not beginner examples.** These are development and emulator tests. Some of them
> **stop on purpose with a runtime error**, and some **write, rename and delete test files** in their
> folder. To learn PcW16 BASIC, start with [the examples](../examples/README.md) and
> [docs/first-program.md](../docs/first-program.md); ready-to-run applications are in
> [programs/](../programs/MANIFEST.md).

The programs in this folder are **diagnostics, not examples**. The project uses them to check how the
compiled runtime behaves under Rosanne 1.12 in the XAnne emulator. Each one was written to settle a
particular question: a limit at its edge, a deliberate runtime error, an operating-system call that is
documented but unproven, or a timing that the simulator cannot measure. The project's owner ran them in
XAnne, and the results decided how the compiler and runtime work today.

Use them when you want to:

- see a limit or an error message for yourself;
- re-check behaviour in another XAnne set-up, or later on a real PcW16 (where none has been run yet);
- read short, focused programs about one feature each.

To learn the language, use [the examples](../examples/README.md) instead. Several of these programs
**end on purpose with a runtime error**, and several **write, rename and delete files** in their folder.
Read the comment at the top of a file before you run it.

## Building and running

From the repository root:

```sh
python3 tools/build.py developer-tests/m7_edges.pbas
```

This writes `build/m7_edges.prg`. Some programs need options, which are given in the tables below and in
the comment at the top of each file. Copy the `.prg` into the XAnne PcW16's program folder
(`\PCW\FOLDER01` unless you built with `--folder`), under a name of at most 8 letters or digits such as
`M7EDGES.PRG`, and start it from the File Manager ([docs/running-in-xanne.md](../docs/running-in-xanne.md)).
Most probes show their results in alerts or in a window. Each result is shown with the expected value in
square brackets, so you can compare them yourself.

The file timecore.pbas in this folder is not a program. It is the shared body that `developer-tests/timeprb.pbas` and
`developer-tests/timepr4.pbas` INCLUDE, and it does not build on its own.

## Evidence

The results column says what the owner's XAnne runs recorded, using the evidence words of
[the examples catalogue](../examples/README.md). Where a run used an older compiler, a build from today's
source can differ in bytes but not in what the probe checks. **None of these programs has been run on a
real PcW16.**

## Language and runtime edge cases

| Program | What it checks | Build | Result in XAnne |
|---|---|---|---|
| `developer-tests/overflow_report.pbas` | The runtime's "string too long" report. With a string capacity of 4, `STR$(-32768)` cannot fit. Alerts: `Step 1: overflow check starts`, then `Runtime error: string too long at line 7`, and the program ends. The "NOT EXPECTED" alert must never appear. | `python3 tools/build.py developer-tests/overflow_report.pbas --string-capacity 4` (the option is the point of the test) | Tested in XAnne: pass |
| `developer-tests/large_image.pbas` | A program image close to the 16K limit of the first block (about 16,260 bytes). Never-taken `IF FALSE` blocks fill it. Alerts: `Step 1: large image loaded`, then a second alert whose text lies near the top of the block. | `python3 tools/build.py developer-tests/large_image.pbas` | Tested in XAnne: pass |
| `developer-tests/m5a_edges.pbas` | String assignments that read their own destination, empty and out-of-range counts. Ends on purpose with `Runtime error: substring position out of range at line 20`. | `python3 tools/build.py developer-tests/m5a_edges.pbas` | Tested in XAnne: pass |
| `developer-tests/m5b_edges.pbas` | Signed division, the limits of `VAL`, `ASC` and `CHR$`, the edges of `INSTR`, and string ordering. Seven alerts, then on purpose `Runtime error: division by zero at line 21`. | `python3 tools/build.py developer-tests/m5b_edges.pbas` | Tested in XAnne: pass |
| `developer-tests/m5c_edges.pbas` | Operator precedence, short-circuit `AND` and `OR`, case conversion, `EXIT SUB`, and the deepest allowed chain of 16 active procedures. Six alerts, then on purpose `EXIT` from two procedures deep. | `python3 tools/build.py developer-tests/m5c_edges.pbas` | Tested in XAnne: pass |
| `developer-tests/m7_edges.pbas` | Procedures with parameters, REAL output and functions, and every sequential-file statement, including `KILL` and `NAME`. Nine alerts, each with its expected value in brackets, then on purpose a REAL runtime error (`function argument out of range`). **Creates, renames and deletes `M7EDGE.TMP` and `M7EDGE2.TMP`.** | `python3 tools/build.py developer-tests/m7_edges.pbas` | Tested in XAnne: 9 of 9 |
| `developer-tests/banktest.pbas` | BANKED array elements that end exactly at the end of a 16K block, including the last block, where Rosanne's copy call reports a harmless carry. Four alerts. In each, the part before `[` must equal the part inside the brackets. Needs 3 free 16K blocks. | `python3 tools/build.py developer-tests/banktest.pbas` | Tested in XAnne: 4 of 4 |
| `developer-tests/bankprobe.pbas` | Whether a program whose SUBs and FUNCTIONs are spread over several code banks behaves like a single-block one. Run tests shows three alerts. Probe > Count counts menu selections. A timer in a bank counts seconds. Error ends with `Runtime error: index out of range at line N`. **Writes, reads and deletes `BANKPRB.TMP`.** | `python3 tools/build.py developer-tests/bankprobe.pbas --code-banks always --code-bank-limit 400` (the options force the procedures into several banks) | Tested in XAnne: pass, with no memory block lost. The tested build used the old menu-shortcut table (known issue KI-89, [docs/limitations.md](../docs/limitations.md)). |

## Windows and controls

| Program | What it checks | Build | Result in XAnne |
|---|---|---|---|
| `developer-tests/m5d_labels.pbas` | That a changing LABEL shows up to 24 printable characters inside its window. "1 Next char" (also Return) shows each printable character 24 times. "2 Widest" shows 24 W's. "3 Short" and "4 Empty" can be repeated in any order. "5 Too long" (25 characters) and "6 Bad char" (character 200) each end the program with an error. | `python3 tools/build.py developer-tests/m5d_labels.pbas` | Tested in XAnne: pass. This settled the 24-character rule for dynamic labels. |
| `developer-tests/m5d_edges.pbas` | Six buttons in both rows, a DEFAULT button that is not the first, a label that keeps its old value while a handler's alert is showing, and long, short and empty label texts. "1 Long" sets a 47-character text. Under the 24-character rule it now ends the program with a runtime error, as does "6 Too long". | `python3 tools/build.py developer-tests/m5d_edges.pbas` | Tested in XAnne. The first run failed: a long label was drawn outside the window. That failure led to the 24-character rule. The later runs checked the error paths. |
| `developer-tests/m6_edges.pbas` | Every window-control limit at its edge: a NUMBERBOX, a 6-option RADIO, a CHECKBOX, ASK, FOCUS, and buttons on the F8, Help, Blue and Yellow keys. "Break" stops the program on purpose with `Runtime error: option number out of range at line 7`. | `python3 tools/build.py developer-tests/m6_edges.pbas` | Tested in XAnne: pass for the behaviours tested. The Help key was not mapped in that set-up (KI-6). |
| `developer-tests/m6p2_edges.pbas` | Two windows: a 40-item list in 12 rows, an empty 2-row list filled later, a drop-down whose item count changes, a slider from −100 to 100, and a 24-character item. "Bad pick", "Bad text" and "No choice" each end the program with a deliberate runtime error. | `python3 tools/build.py developer-tests/m6p2_edges.pbas` | Tested in XAnne: pass. The second window looks cramped, though no overlap was found (KI-26). "No choice" gives its error alert and does not freeze (KI-3). |
| `developer-tests/tbprobe.pbas` | Whether a TEXTBOX keeps its variable's value: `STRING * 13` boxes in a first and a second window, and a full-length box. Without typing, each Check must show `[EDTEST.MD] 9` everywhere. | `python3 tools/build.py developer-tests/tbprobe.pbas` | Tested in XAnne: pass |

## Canvas, text and graphics

| Program | What it checks | Build | Result in XAnne |
|---|---|---|---|
| `developer-tests/gfxprobe.pbas` | Every DRAW statement at a known place: a box on the canvas edge, a diagonal line, nine grey strips from black to white, an inverted band, corner pixels and clipped text. Then DRAW SCROLL (up 16, right 8), an alert over the canvas (after which the picture must be complete again), the key codes the KEYS handler receives, and mouse press, drag and release. | `python3 tools/build.py developer-tests/gfxprobe.pbas` | Tested in XAnne: pass. Only the keys tried there are confirmed (KI-41). |
| `developer-tests/cellprb.pbas` | `DRAW TEXT x, y, s$, cell`, which draws text on a fixed grid of 11-pixel cells. It checks that every printable character fits its cell, which column a click finds, and how long a page of 13 rows takes. | `python3 tools/build.py developer-tests/cellprb.pbas --runtime-banks all` | Tested in XAnne: pass, judged by eye |
| `developer-tests/rendprb.pbas` | `TEXTWIDTH` against the drawn text (each sample is boxed at its measured width). It also compares proportional text with the cell grid, times each drawing operation and whole pages, and counts KEYS calls while you type. | `python3 tools/build.py developer-tests/rendprb.pbas --runtime-banks all`. For the version without the runtime bank, use `python3 tools/build.py developer-tests/rendprb.pbas --prg build/rendprn.prg` | Tested in XAnne: all eight widths matched their text. The banked and unbanked builds took the same time per call. |
| `developer-tests/bmpprb.pbas` | BITMAPs. Copy: GET a test card and PUT it beside itself, which must be identical. Points: POINT on eight pixels of known colour. File: BITMAP SAVE and LOAD of `BMPPROBE.PBI`. Speed: GET and PUT timed by the PcW16 clock. **Writes `BMPPROBE.PBI`, and `BMPPROBE.BAK` the second time.** Check the saved file on your computer with `python3 tools/pbicheck.py BMPPROBE.PBI`. | `python3 tools/build.py developer-tests/bmpprb.pbas --runtime-banks all`, and `python3 tools/build.py developer-tests/bmpprb.pbas --prg build/bmpprn.prg` for the unbanked build | Tested in XAnne: pass. GET of 120 × 80 took 7 ms and PUT 11 ms. |
| `developer-tests/sprprb.pbas` | Masks, parts, held keys, timer ticks and speed. Mask: BITMAP MASK and parts at odd x, each compared pixel by pixel ("0 wrong"). Keys: the KEYDOWN codes of the keys held now. Ticks: timer events counted over 10 seconds, at rest and under load. Speed: one draw of each kind. | `python3 tools/build.py developer-tests/sprprb.pbas --runtime-banks all`, or plain `python3 tools/build.py developer-tests/sprprb.pbas` | Tested in XAnne. Masks: 0 wrong in both builds. The key numbers it showed (Left 99, Right 100, Up 101, Down 98, Space 41, A 28) are the ones the keys library `lib/keys.pbas` uses. Its tick count predates the current timer and is replaced by TIMEPRB. |

## Timers and the clock

| Program | What it checks | Build | Result in XAnne |
|---|---|---|---|
| `developer-tests/timeprb.pbas` | A `TIMER … EVERY 1 TICKS` (1/16 s), using the body in timecore.pbas. Clock: how often `CLOCKTICKS` changes in 2 s, its largest step, and whether it goes back. Idle and Load: events, clock sixteenths, `lib/pace.pbas` steps and the longest gap over 10 s, at rest and while drawing. Keys: events while keys are held. Restart: TIMER OFF and ON every second. Writes no files. | `python3 tools/build.py developer-tests/timeprb.pbas --runtime-banks all`. It also builds without the option. | Tested in XAnne: pass. The clock never went back and its largest step was 2/16 s. Idle gave 154 events for 160 wanted, with 80 of 80 steps. Under load it gave 142 to 148 events, still with 80 of 80 steps (KI-81). The Keys test was not reported. |
| `developer-tests/timepr4.pbas` | The same as TIMEPRB for `EVERY 4 TICKS` (1/4 s). | `python3 tools/build.py developer-tests/timepr4.pbas --runtime-banks all`. It also builds without the option. | Tested in XAnne: pass. Idle gave 41 events for 40 wanted, with 80 of 80 steps. |

## Databases

| Program | What it checks | Build | Result in XAnne |
|---|---|---|---|
| `developer-tests/dbprobe.pbas` | The database statements step by step. Each step shows one alert: clean-up; 40 records saved and loaded back; a second save keeping `.BAK`; recovery from `.BAK` and from `.NEW` (`DBRECOVERED` 2 and 1); a file that is not a database (`IOERR 248`); sorting and searching 200 records (time it with a watch); clean-up. **Writes, renames and deletes `DBPROBE.PDB`, `.NEW`, `.BAK` and `.TXT`.** | `python3 tools/build.py developer-tests/dbprobe.pbas` | Tested in XAnne: pass |

## Test documents

- `developer-tests/edtest.md` is the document the editors open at start. Copy it to the PcW16 folder as `EDTEST.MD`
  and keep the original elsewhere.
- `developer-tests/wraptest.md` is a document of long paragraphs mixing wide and narrow letters, for checking
  MDEDIT IV's word wrap.

## Assembly-language probes

The `.asm` files are not PcW16 BASIC. Each is a small hand-written Z80 program that makes exactly the
operating-system calls the runtime depends on and shows the raw results. They were used to establish
Rosanne's behaviour before the runtime relied on it. Each one assembles with Pasmo, for example:

```sh
pasmo --bin developer-tests/readdiag.asm build/readdiag.prg
```

| File | What it examined |
|---|---|
| `developer-tests/readdiag.asm` | the results of the read-file call at the end of a file |
| `developer-tests/widthdiag.asm` | the text-width call, which in Rosanne 1.12 returns the right width with an error flag set |
| `developer-tests/uiprobe.asm`, `developer-tests/uiprobe2.asm`, `developer-tests/uiprobe3.asm` | the dialog, list, drop-down and slider definitions the runtime uses, and how a redefined list must be redrawn. **Do not use the "F" variant of `uiprobe3.asm`: it froze XAnne** (KI-3). |
| `developer-tests/evprobe.asm` | which events a double-click on a list produces: two single clicks, which is why a LIST's ACTION never runs (KI-25) |
| `developer-tests/memprobe.asm`, `developer-tests/memprobe2.asm`, `developer-tests/memdiag.asm`, `developer-tests/memleak.asm` | getting, copying into and releasing 16K memory blocks, as BANKED arrays do, and whether Rosanne takes the blocks back when a program exits |
| `developer-tests/codeprobe.asm` | whether a program can load and run code beyond its first 16K, which led to code banks |

These probes read and write memory and system state directly, so run them only in a disposable XAnne
set-up.
