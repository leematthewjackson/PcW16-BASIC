# PcW16 BASIC

**A BASIC compiler for the Amstrad PcW16.** You write a program on a PC, compile it there,
and run the resulting `.PRG` file in the XAnne emulator, or (untested so far) on a real
PcW16, as a native Rosanne application with its own windows, buttons, pictures and files.
No assembly language is needed.

| | |
|---|---|
| **What you can build** | desktop-style applications (windows, buttons, text fields, lists, menus), drawing programs, editors, record databases, printed reports, and sprite games with timers and held keys. See [what has been built with it](#what-has-been-built-with-it). |
| **What you need** | **Python 3.10 or later** (standard library only) and the **Pasmo** Z80 assembler (0.5.3). To run programs: the **XAnne** emulator with your own copy of the PcW16 system, or a PcW16. |
| **Status** | **PcW16 BASIC Public Preview** (version 1.0.0rc1); free software (GPL-3.0-or-later, with the runtime, libraries and templates under MIT-0: [LICENSING.md](LICENSING.md)). Programs have been tested in XAnne; nothing has been run on a real PcW16 yet. Only Linux has been exercised as the PC side. |

## Start here

1. **Install** Python and Pasmo: [docs/install.md](docs/install.md).
2. **Write your first program**: [docs/first-program.md](docs/first-program.md), or the short version below.
3. **Try the ready-to-run applications** (PAINT II, DESIGNER, JUMPER, SPRITED, MDEDIT IV, the scientific
   calculator and the tutorials) without compiling anything: [programs/](programs/MANIFEST.md).

[developer-tests/](developer-tests/README.md) holds advanced diagnostics used to develop the compiler in
the emulator, not beginner examples: some stop with an error on purpose, and some change test files.

## Compile your first program

In this folder ([docs/install.md](docs/install.md) has the installation of Python and Pasmo):

```sh
python3 pcw16basic doctor               # checks Python, Pasmo and this copy
python3 pcw16basic new hello            # creates hello/hello.pbas, hello/lib/, hello/assets/
cd hello
python3 ../pcw16basic build hello.pbas  # writes build/hello.prg
```

Copy `build/hello.prg` into XAnne as `HELLO.PRG` and run it from the File Manager
([docs/running-in-xanne.md](docs/running-in-xanne.md)). The step-by-step version, with what you
should see and what to do when something goes wrong, is **[docs/first-program.md](docs/first-program.md)**.

A complete program looks like this. The main line sets the greeting and `END` hands the window
to the user; each button runs its SUB. (It builds as shown: `tools/check_docs.py` builds every
program in the documentation.)

```pbas
' A window with a greeting, a text field and two buttons.
DIM Name$ AS STRING * 20
DIM Greeting$ AS STRING * 24

WINDOW Main, "HELLO", LARGE
LABEL Greeting$
TEXTBOX Name$, "Your name"
BUTTON "Greet", Greet, DEFAULT
BUTTON "Quit", Quit

SUB Greet
    IF LEN(Name$) = 0 THEN
        Greeting$ = "Type your name first"
    ELSE
        Greeting$ = LEFT$("Hello, " + Name$, 24)
    END IF
END SUB

SUB Quit
    EXIT
END SUB

Greeting$ = "Hello!"
END
```

## Where to learn more

| start here | for |
|---|---|
| **[docs/README.md](docs/README.md)** | the map of all the documentation: **the one place to start** |
| [docs/first-program.md](docs/first-program.md), then the tutorials [1](docs/TUTORIAL-1-FIRST-PROGRAM.md), [2](docs/TUTORIAL-2-GRAPHICS.md), [3](docs/TUTORIAL-3-GAME.md) | learning step by step |
| [docs/manual/README.md](docs/manual/README.md) | the developer manual: every statement, with examples |
| [docs/libraries/README.md](docs/libraries/README.md) | the BASIC libraries in `examples/lib/` |
| [examples/README.md](examples/README.md) | the catalogue of example programs |
| [docs/limitations.md](docs/limitations.md) | what does not work, or has not been verified |
| [docs/AI-DEVELOPER-GUIDE.md](docs/AI-DEVELOPER-GUIDE.md) | a compact, complete contract for writing programs (for people and AI systems) |
| [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md) | the normative specification, for settling exactly what a rule says |

## What has been built with it

Each of these is in `examples/`, builds from this repository, and has passed the project
owner's sessions in XAnne except where noted ([examples/README.md](examples/README.md)).

| program | source | what it shows |
|---|---|---|
| PAINT II | `examples/paint2.pbas` | an icon palette loaded from pictures, pattern fills, a floating selection, undo, files |
| DESIGNER | `examples/designer_m14.pbas` | a screen designer: select, drag, resize, restack; a validated file; export as a picture or as BASIC |
| JUMPER | `examples/jumper.pbas` | a platform game: masked, animated sprites, held keys, gravity, collisions, lives |
| SPRITED | `examples/sprited_m14.pbas` | a sprite editor with frames and animation |
| MDEDIT IV | `examples/mdedit4_m14.pbas` | a word-wrapping text editor with files, undo and the clipboard |
| CONTACTS IV | `examples/contacts4.pbas` | typed records, sorting, searching, safe saving with recovery |
| REPORTER | `examples/reporter.pbas` | printed pages, tables and bar charts (the printed bar chart's correction has not yet been retested in XAnne) |

Prebuilt copies of the main programs, byte-identical to what a build here produces, are in
[programs/](programs/MANIFEST.md).

## How it works

The compiler (`pbas/`, Python) checks the program and generates Z80 assembly with a runtime
(`runtime/runtime.z80.asm`) that calls Rosanne's own windowing, drawing and file services.
Pasmo assembles that into a `.PRG`. The project's Z80 and Rosanne model (`tests/z80sim.py`)
runs programs on the PC for the test suite; it is a model, so XAnne (or a PcW16) is the final
judge of how a program behaves.

## Checking this copy

```sh
python3 tools/verify_public.py           # checksums, rebuilds, examples, docs, new projects, no private material
python3 tools/verify_public.py --tests   # ... and the test suite
```

## Acknowledgements

PcW16 BASIC owes much to the people who have preserved the Amstrad PcW16 and its software over the years.

Special thanks to John Elliott for the ANNE emulator and his invaluable technical documentation, and to Rob Buckley, whose earlier PcW16 BASIC compiler helped inspire this project.

I'm also grateful to everyone who preserved the original software, development materials and knowledge that made this work possible.

Read the full [Credits and Acknowledgements](CREDITS.md).

## Licence and notices

Copyright © 2026 Lee Matthew Jackson. The compiler, tools, simulator, tests, example applications
and documentation are licensed under the GNU General Public License, version 3 or later
([LICENSE](LICENSE)). The embedded Z80 runtime, the reusable BASIC libraries and the templates
`pcw16basic new` makes are licensed under MIT-0 ([LICENSE-MIT-0](LICENSE-MIT-0)), so programs you
compile with PcW16 BASIC are yours to distribute under any licence you choose, subject to the rights
in any other material you include. [LICENSING.md](LICENSING.md) says which licence covers each part.

PcW16 BASIC is an independent, community-developed project for the Amstrad PcW16. It is not
affiliated with or endorsed by Amstrad or its successors. It contains no Rosanne software, ROM,
fonts or Amstrad documents: see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Changes are listed in
[CHANGELOG.md](CHANGELOG.md); possible future work, with no commitment, in [ROADMAP.md](ROADMAP.md).
