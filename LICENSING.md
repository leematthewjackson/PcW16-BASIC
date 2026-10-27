# Licensing

Copyright © 2026 Lee Matthew Jackson.

PcW16 BASIC is free software. It uses two licences: a copyleft one for the tools you run on
your PC, and a permissive one for everything that ends up inside, or is copied into, your own
programs.

| part | where | licence (SPDX) | licence file |
|---|---|---|---|
| the compiler | `pbas/`, `pcw16basic` | `GPL-3.0-or-later` | [LICENSE](LICENSE) |
| the command-line and development tools | `tools/`, `pyproject.toml` | `GPL-3.0-or-later` | [LICENSE](LICENSE) |
| the simulator and tests | `tests/`, `developer-tests/` | `GPL-3.0-or-later` | [LICENSE](LICENSE) |
| the complete example applications and tutorials | `examples/` (except `examples/lib/`), with their pictures in `examples/assets/` | `GPL-3.0-or-later` | [LICENSE](LICENSE) |
| the documentation | `docs/`, `*.md` | `GPL-3.0-or-later` | [LICENSE](LICENSE) |
| the prebuilt programs | `programs/` | `GPL-3.0-or-later`, with the runtime inside them under `MIT-0` | [LICENSE](LICENSE) |
| **the embedded Z80 runtime** | `runtime/` | `MIT-0` | [runtime/LICENSE](runtime/LICENSE) |
| **the reusable BASIC libraries** | `examples/lib/` | `MIT-0` | [examples/lib/LICENSE](examples/lib/LICENSE) |
| **the generated project templates** | the text `pcw16basic new` writes (`APP_TEMPLATE`, `GAME_TEMPLATE` and `ASSETS_TEMPLATE` in `pbas/cli.py`) | `MIT-0` | [LICENSE-MIT-0](LICENSE-MIT-0) |

`LICENSE` is the unmodified GNU General Public License, version 3. "Or later" means you may
also use any later version published by the Free Software Foundation. The MIT-0 files are the
unmodified MIT No Attribution licence, with the copyright line above.

For the GPL-3.0-or-later parts:

> This program is free software: you can redistribute it and/or modify it under the terms of
> the GNU General Public License as published by the Free Software Foundation, either version 3
> of the License, or (at your option) any later version.
>
> This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
> without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
> the GNU General Public License for more details.

## Your own programs

Programs you write and compile with PcW16 BASIC are yours. You may distribute them under any
licence you choose:
- every compiled `.PRG` contains a copy of the runtime, which is MIT-0 and asks nothing of you;
- the libraries you `INCLUDE` and the project files `pcw16basic new` makes are MIT-0 too;
- the compiler's GPL covers the compiler, not the programs it compiles.

Your choice is subject only to the rights in anything else you add. If you start from one of the
complete example applications (GPL-3.0-or-later) or use its pictures, that material keeps its
licence. Pictures, text or code from other people keep theirs.

## What is not covered, because it is not here

- **Rosanne** (the PcW16's operating system), its fonts and ROM, rescue disks, and Amstrad's
  developer documentation are not part of this repository and are never redistributed with it.
  You use your own PcW16, or your own copy of its system for the emulator.
- **Pasmo** (the Z80 assembler, GNU GPL) and **Python** are installed separately. Pasmo runs as a
  separate program, and its licence does not cover what it assembles.
- **XAnne / JOYCE** (the emulator) is installed separately.

See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

PcW16 BASIC is an independent, community-developed project for the Amstrad PcW16. It is not
affiliated with or endorsed by Amstrad or its successors.
