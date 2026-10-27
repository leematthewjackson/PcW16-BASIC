# PcW16 BASIC documentation

**New to PcW16 BASIC? Read these in order:**

1. [install.md](install.md): Python, Pasmo and this repository, checked by `pcw16basic doctor`
2. [first-program.md](first-program.md): make, build and run a first program, and read its errors
3. [running-in-xanne.md](running-in-xanne.md): put programs and their pictures into the XAnne emulator
4. [TUTORIAL-1-FIRST-PROGRAM.md](TUTORIAL-1-FIRST-PROGRAM.md): a window, a field, buttons and a menu
5. [TUTORIAL-2-GRAPHICS.md](TUTORIAL-2-GRAPHICS.md): drawing, pictures from PNG files, dragging with the mouse
6. [TUTORIAL-3-GAME.md](TUTORIAL-3-GAME.md): a timer, held keys and a sprite that runs and jumps

When something goes wrong: [troubleshooting.md](troubleshooting.md).

## Reference

| document | what it covers |
|---|---|
| [manual/README.md](manual/README.md) | **the developer manual**: every statement and function, each with syntax, meaning, a working example, common errors and limits |
| [manual/17-unsupported.md](manual/17-unsupported.md) | constructs from other BASICs that PcW16 BASIC does not have, and what to use instead |
| [libraries/README.md](libraries/README.md) | the 14 BASIC libraries in `examples/lib/` and how to add them to a project |
| [LIBRARY-REFERENCE.md](LIBRARY-REFERENCE.md) | every library procedure, generated from the libraries' own comments (`tools/libref.py`) |
| [../examples/README.md](../examples/README.md) | the example programs, by category, with build commands and what each shows |
| [graphics-assets.md](graphics-assets.md) | making pictures, icons and sprite sheets from PNG files |
| [memory.md](memory.md) | the 16K resident block, banking, and keeping large programs within limits |
| [simulator.md](simulator.md) | testing a program on the PC: the PcW16 and Rosanne model, scripted clicks and typing |
| [limitations.md](limitations.md) | known issues, unverified behaviour and platform gaps |
| [real-hardware.md](real-hardware.md) | copying programs to a real PcW16 (not yet tested) |
| [AI-DEVELOPER-GUIDE.md](AI-DEVELOPER-GUIDE.md) | the whole language contract in compact form, with reliable patterns, for any developer or AI system |
| [../LANGUAGE-SPEC.md](../LANGUAGE-SPEC.md) | the normative specification: where the exact rule is settled |
| [../developer-tests/README.md](../developer-tests/README.md) | the project's XAnne probe programs (diagnostics, not examples) |
| [../programs/MANIFEST.md](../programs/MANIFEST.md) | prebuilt programs and pictures, with checksums |

About the project: [../ROADMAP.md](../ROADMAP.md) (possible future work, no commitments),
[../CHANGELOG.md](../CHANGELOG.md), [../CONTRIBUTING.md](../CONTRIBUTING.md),
[../LICENSING.md](../LICENSING.md) (GPL-3.0-or-later; the runtime, libraries and templates MIT-0),
[../THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md).

## How sure is each statement?

The documentation says how each behaviour is known:

- **Tested in XAnne**: the project owner ran it in the XAnne emulator (Rosanne 1.12).
- **Simulator only**: checked on the project's model of the PcW16 and Rosanne (`tests/z80sim.py`), not yet in XAnne.
- **Untested**: neither.

Nothing has yet been run on a real PcW16. A program that compiles has passed the compiler's
checks; only running it shows that it works.

## References in the source

The compiler, runtime, libraries, tests and the language specification were written with the
project's engineering records, and their comments cite them. Those records are not part of this
repository: they hold development history, the owner's test sessions, and research notes on
Rosanne that may not be redistributed. When a comment names one, this is where the same
information is for you:

| cited as | what it was | read instead |
|---|---|---|
| `ROSAN283`, `Supporting Docs/ROSAN283.DOC`, `OSCALLS.INC` | Amstrad's PcW16 developer documentation (Rosanne's programming interface) | not redistributable; its name and section are cited so the runtime can be checked against it by anyone who has a copy |
| `docs/M13-LIBRARIES.md` (in some tests) | the library guide | [libraries/README.md](libraries/README.md) |
| `docs/LIBRARY-REFERENCE.md` | the generated library reference | [LIBRARY-REFERENCE.md](LIBRARY-REFERENCE.md) (in this repository) |
| `docs/INSTALL.md` | installation | [install.md](install.md) |
| `docs/M13-GRAPHICS-ASSETS.md`, `docs/M12-BITMAP-FORMAT.md`, `docs/M13-SPRITES.md` | pictures, the `.PBI` format, sprites | [graphics-assets.md](graphics-assets.md), [manual/13-bitmaps-and-sprites.md](manual/13-bitmaps-and-sprites.md) |
| `docs/M12-PRINTING.md` | printing | [manual/15-printing.md](manual/15-printing.md) |
| `docs/M13-RESPONSIVENESS.md`, `docs/M11-CORRECTIVE.md` | timers, the calibrated clock, responsiveness measurements | [manual/14-timers-and-animation.md](manual/14-timers-and-animation.md) |
| `docs/M8-*.md`, `docs/M9-*.md`, `docs/M10-ARCHITECTURE.md`, `docs/M11-ARCHITECTURE.md`, `docs/M12-ARCHITECTURE.md` | memory, banking and compiler design records | [memory.md](memory.md), [manual/16-building-and-commands.md](manual/16-building-and-commands.md) |
| `docs/M13-PAINT2.md`, `docs/M13-DESIGNER.md`, `docs/M13-PLATFORMER.md`, `docs/M13-INDEPENDENT-APP.md` | design notes for the reference applications | [../examples/README.md](../examples/README.md) |
| `docs/M*-ACCEPTANCE.md`, `RUNTIME-RESULTS.md` | the owner's XAnne test scripts and results | the evidence notes in the manual and in [limitations.md](limitations.md) |
| `KNOWN-ISSUES.md`, `KI-nn` | the issue list | [limitations.md](limitations.md) (the same numbers) |
| other `docs/M*.md`, `FEATURE-STATUS.md`, `MIGRATION-PLAN.md` | audits, plans and reports from development | [manual/README.md](manual/README.md) |
| `POC/...` | the prototype compiler the project started from | nothing to read: some tests compare with it, and are left out of this repository |
| `rosanne-research/...` | research notes on Rosanne's behaviour | the behaviour itself is stated in the manual |
