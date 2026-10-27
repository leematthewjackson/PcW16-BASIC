# Third-party notices

This repository contains only PcW16 BASIC's own work:
- the compiler (`pbas/`);
- the runtime (`runtime/`);
- the tools and the simulator;
- the libraries, examples and documentation;
- the pixel art in `examples/assets/`, drawn for this project.

None of the items below is included. Each is something PcW16 BASIC uses, needs, or refers to.

| | what it is | how PcW16 BASIC uses it | included? |
|---|---|---|---|
| **Python** (Python Software Foundation licence) | the language the compiler and tools are written in | needed on your PC; only its standard library is used | no: install it yourself |
| **Pasmo** by Julián Albo (GNU GPL) | a Z80 assembler | run by the build as a separate program, to assemble the compiler's output; its licence does not cover that output | no: install it yourself |
| **Rosanne**, the PcW16's operating system, with its fonts and ROM, © Amstrad plc and its successors | the system PcW16 programs run on | programs call it while they run, as Amstrad's developer documentation describes | no, and never redistributed: use your own PcW16 or your own copy of its system |
| **Amstrad's PcW16 developer documentation** (ROSAN283 and its include files) | the reference for Rosanne's programming interface | read to write the runtime; cited by name and section in source comments | no |
| **XAnne / JOYCE** by John Elliott | a PcW16 emulator | the place to run and test programs on a PC | no: install it yourself |

The PcW16 BASIC simulator (`tests/z80sim.py`), the project's PNG reader and writer
(`tools/pbimage.py`) and all other code here are PcW16 BASIC's own. None of them
copies a third-party implementation.

Source comments sometimes describe how Rosanne behaves at a given address ("static"
evidence). These descriptions were made for interoperability. They are written in
prose, and no Rosanne code, fonts or data are reproduced.

Amstrad, PcW16 and Rosanne are named only to say what this software runs on.
PcW16 BASIC is an independent, community-developed project for the Amstrad PcW16. It is not
affiliated with or endorsed by Amstrad or its successors.

PcW16 BASIC itself is Copyright © 2026 Lee Matthew Jackson, licensed under GPL-3.0-or-later and,
for the runtime, libraries and templates, MIT-0: see [LICENSING.md](LICENSING.md).
