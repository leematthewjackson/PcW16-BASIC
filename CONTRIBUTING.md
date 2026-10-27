# Contributing to PcW16 BASIC

Thank you for your interest. Please read the first section before you send
anything.

## Licence of contributions

Contributions are welcome. By sending one, you agree that it is licensed under the
licence of the part it changes ([LICENSING.md](LICENSING.md)): GPL-3.0-or-later for the
compiler, tools, simulator, tests, example applications and documentation, and MIT-0 for
the runtime (`runtime/`), the libraries (`examples/lib/`) and the project templates. Send
only work you have the right to give.

Reports of problems are just as welcome, with a minimal program (below), and so are
reports of what you observed in XAnne or, especially, on a real PcW16.

## Running the checks

Everything runs from the repository's top folder. Only Linux has been
exercised (Python 3.13, Pasmo 0.5.3); see [docs/install.md](docs/install.md).

```sh
python3 pcw16basic doctor            # Python, Pasmo and the install: prints "ready"
python3 tools/run_tests.py fast      # the quicker tier of the test suite
python3 tools/run_tests.py full      # the whole suite (much longer)
python3 tools/run_tests.py list      # the test modules
python3 tools/run_tests.py module test_m7_files  # one module
python3 tools/verify_public.py       # checksums, rebuilds of programs/ byte for byte, every example, every documented program
python3 tools/verify_public.py --tests          # ... and the full suite
python3 tools/check_docs.py          # every program shown in README.md and docs/
python3 tools/check_docs.py docs/manual/06-files.md   # just one file
```

- `tools/run_tests.py` runs the test modules in `tests/` in parallel
  (`-j JOBS` to choose how many). They use the project's simulator
  (`tests/z80sim.py`), a model of the Z80 and of Rosanne: a test that passes
  shows the program behaves as the model says, not that Rosanne agrees.
- `tools/verify_public.py` checks that every file is the one `SHA256SUMS`
  lists, that each prebuilt program in `programs/` rebuilds byte for byte from
  its source, that every example and documented program builds, that new
  projects build, and that no file is a system file, ROM, font, disk image or
  disassembly. It writes nothing into the repository.
- `tools/check_docs.py` builds every ```` ```pbas ```` block in the Markdown
  files and runs the ones with `' expect-message:` lines on the simulator.

A change is not ready until `verify_public.py --tests` passes.

## Conventions

### Code

- **The compiler must fail loudly.** A program that breaks a rule gets a
  compile error with its line and column; it must never be possible to
  produce a `.PRG` from an invalid program, and nothing may be truncated or
  wrapped silently ([LANGUAGE-SPEC.md](LANGUAGE-SPEC.md) §8).
- **Programs that do not use a feature compile to the same bytes as before.**
  The prebuilt programs in `programs/` are the owner's accepted executables;
  `verify_public.py` rebuilds them byte for byte. A change that alters them
  needs a stated reason and the owner's agreement.
- **Every change has a test**, in `tests/`, that fails without it.
- **Libraries** (`examples/lib/`): every public name starts with the
  library's prefix; the header comment points to the library's page,
  `docs/libraries/<name>.md`, and documents every SUB, FUNCTION and
  global, and `python3 tools/libref.py --check` must exit with status 0
  (`docs/LIBRARY-REFERENCE.md` in sync with the headers). That file is
  generated: do not edit it by hand, but run `python3 tools/libref.py` with
  no argument to regenerate it.
- Program and file names on the PcW16: at most 8 letters and digits, DOS 8.3
  for data files.

### Documentation

- **Every program shown in a ```` ```pbas ```` block must be complete and
  must build**; `tools/check_docs.py` builds them all. Add
  `' expect-message: text` lines, one per alert in order, when the program
  shows alerts without needing input. Show a compile error in a
  ```` ```pbas-error ```` block with an `' expect-error:` line. Put syntax
  summaries and fragments in ```` ```text ```` blocks.
- **State the evidence level** wherever behaviour matters:
  - *Tested in XAnne*: the owner ran it in the XAnne emulator (Rosanne 1.12);
  - *Simulator only*: checked on `tests/z80sim.py`, not yet in XAnne;
  - *Untested*.

  Nothing has been run on a real PcW16; say "not yet tested on a real PcW16"
  where hardware matters. Compiling is not the same as working.
- Never describe a feature that does not exist. If a conventional BASIC
  construct is missing, say so ([docs/manual/17-unsupported.md](docs/manual/17-unsupported.md)).
- Known issues are cited as "(known issue KI-nn, docs/limitations.md)".
- British spelling, plain sentences, relative links to files in the
  repository.

## Reporting a problem

Open an issue (or, before the repository is public, send it to the person who
gave you the repository) with:

1. **A minimal program**: the shortest complete `.pbas` that shows the
   problem, ideally under 20 lines, with no INCLUDEs unless a library is the
   problem. For example:

```pbas
DIM A AS INTEGER
A = -7 / 2
MESSAGE STR$(A)
' expect-message: -3
END
```

2. **The exact command** you ran (`python3 pcw16basic build PROB.pbas`, any
   options) and **its whole output**.
3. **Your versions**: `python3 pcw16basic --version`, `python3 --version`,
   the Pasmo version (`pasmo` with no arguments prints it), and your
   operating system.
4. **Where it went wrong**: at compile time, on the simulator, in XAnne (its
   version and settings; whether Rosanne's Graphics acceleration was off), or
   on a real PcW16 (which model and Rosanne version).
5. **What you expected**, with the part of [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md)
   or the manual that says so, and **what happened**: the error message or
   alert text word for word, and a description of the screen. Please do not
   attach photographs or captures of Rosanne's own screens beyond what is
   needed, and never attach system files.
6. If files are involved: the names and sizes of the files in the program's
   folder before and after. Run it on copies, never on the only copy of your
   data.

Check [docs/limitations.md](docs/limitations.md) and
[docs/troubleshooting.md](docs/troubleshooting.md) first: the problem may be
a documented limitation with a workaround.

## What can never be accepted

- **Rosanne's code or files**: the PcW16's ROM, system files, fonts, rescue or
  system disk images, or any part of them.
- **Disassembly** of Rosanne or of any Amstrad software, in any form: a code
  listing with its bytes or addresses, or code translated from one.
- **Amstrad's documentation**, or long passages of it.
- Material you do not have the right to give, or whose licence would conflict
  with the project's eventual terms.

Write what you learn about Rosanne in your own words, as behaviour ("this call
returns the width but reports an error"), not as copied code or text.
`tools/verify_public.py` refuses a repository that holds such files.
