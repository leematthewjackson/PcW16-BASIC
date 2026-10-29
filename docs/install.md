# Installing PcW16 BASIC

PcW16 BASIC runs on the computer you write programs on. It turns `.pbas` source into a `.PRG` file for the Amstrad PcW16. You need two things:

| | version | why |
|---|---|---|
| Python | 3.10 or later | runs the compiler and the tools; no other Python packages are used |
| Pasmo | 0.5.3 (the tested version) | assembles the compiler's Z80 output into a `.PRG` |

**Which platforms have been tried.** Only Linux has been exercised: Ubuntu 24.04 with Python 3.13 (the fast test tier also with 3.11 and 3.12) and the distribution's Pasmo 0.5.3 package. The Windows and macOS sections below are **untested**. They describe the most likely route, not one anyone has followed for this project.

To run the programs you build, you also need the XAnne emulator with your own copy of the PcW16 system software ([running-in-xanne.md](running-in-xanne.md)), or a real PcW16 ([real-hardware.md](real-hardware.md); not yet tested on a real PcW16).

## Linux (tested on Ubuntu 24.04)

1. **Python.** Most distributions already have Python 3. Check the version:
   ```sh
   python3 --version
   ```
   If it is older than 3.10, install a newer `python3` from your distribution's packages.
2. **Pasmo.** On Debian and Ubuntu it is a package:
   ```sh
   sudo apt install pasmo
   ```
   This is the tested route: the Ubuntu package is version `0.5.3-7`, and the executable is `/usr/bin/pasmo`. Pasmo has no `--version` option. Running `pasmo` with no arguments prints its banner (`Pasmo v. 0.5.3 ...`) and then its usage.

   On other distributions, look for a `pasmo` package first. If there is none, build Pasmo from source (see [Building Pasmo from source](#building-pasmo-from-source)).

## Windows (untested)

1. **Python.** Install Python 3.10 or later from python.org, or from the Microsoft Store. The Python launcher is `py`, so wherever these documents say `python3`, type `py -3`:
   ```sh
   py -3 --version
   py -3 pcw16basic doctor
   ```
2. **Pasmo.** Pasmo is Julián Albo's Z80 cross-assembler. Its home page is `https://pasmo.speccy.org/`, the address `pcw16basic doctor` prints. Look there for a Windows executable of version 0.5.3, or build it from the source. Put the folder that holds `pasmo.exe` on your `PATH`, so that `pasmo` runs from a new Command Prompt.

Nothing in PcW16 BASIC depends on Linux. Its tools are Python scripts that start Pasmo by name. Even so, nobody has run them on Windows.

## macOS (untested)

1. **Python.** Install Python 3.10 or later from python.org or with a package manager such as Homebrew. Check the version with `python3 --version`.
2. **Pasmo.** Check whether your package manager has a `pasmo` package. If it has none, build Pasmo from source (below) with Apple's command-line developer tools, which give you a C++ compiler and `make`. Put `pasmo` somewhere on your `PATH`.

## Building Pasmo from source

This route is **untested**. Pasmo is a small C++ program. Its source is on the Pasmo home page named above. Unpack the source archive of version 0.5.3, and follow its own instructions. For a conventional source package that means `./configure`, `make` and then installing the result. Then check that `pasmo` with no arguments prints `Pasmo v. 0.5.3`.

Other versions of Pasmo may work, but only 0.5.3 has been tested. `tools/verify_public.py` (below) tells you whether your Pasmo produces exactly the accepted programs.

## Getting PcW16 BASIC

Clone the repository, or download and unpack it, anywhere you like. Everything lives inside that one folder. The tools write only to the folders you name, and to `build/` under the folder you run them from, with one exception: Python itself saves compiled copies of the tools' modules in `__pycache__/` folders inside the repository (for example `pbas/__pycache__/`) the first time they run.

`tools/verify_public.py` ignores these folders. To keep the repository folder exactly as it was, for example a read-only or shared copy, set `PYTHONDONTWRITEBYTECODE=1` in the environment:
```sh
export PYTHONDONTWRITEBYTECODE=1        # for this shell
PYTHONDONTWRITEBYTECODE=1 python3 pcw16basic build hello.pbas   # for one command
```
`python3 -B` alone is not enough: `pcw16basic build` and `check` start further Python processes, which do not inherit the option, so `pbas/__pycache__/` is still written. The environment variable is inherited. Without these folders the tools only start slightly more slowly.

Work from the repository's top folder, the one that holds `pcw16basic`, `pbas/` and `LANGUAGE-SPEC.md`.

## The `pcw16basic` command

`pcw16basic` is a Python script at the top of the repository. You can use it in two ways.

**From the repository folder.** No installation is needed:
```sh
python3 pcw16basic --version          # PcW16 BASIC 1.0.0rc2
python3 pcw16basic doctor
```
From another folder, give the path to the script, for example `python3 ../pcw16basic build hello.pbas`.

**As a command on your `PATH`.** Install the folder in *editable* mode:
```sh
python3 -m pip install -e .
pcw16basic doctor
```
- Use `-e`. The command finds the runtime, the tools and the libraries inside the repository folder. A plain (non-editable) `pip install .` is not supported: it copies only the `pbas` package, and every `pcw16basic` command except `--version` then stops with exit status 2 and a message saying that PcW16 BASIC must be run from its own folder (`python3 pcw16basic`) or installed with `pip install -e .`.
- Some Linux distributions (Ubuntu 24.04 among them) refuse `pip install` outside a virtual environment. Make one first:
  ```sh
  python3 -m venv ~/pcw16-venv
  ~/pcw16-venv/bin/python -m pip install -e .
  ~/pcw16-venv/bin/pcw16basic doctor
  ```
- An editable install writes a `pcw16basic.egg-info` folder into the repository. `tools/verify_public.py` lists those files as a `note`, not as a failure.

The rest of these documents write `python3 pcw16basic ...`. If you installed the command, type `pcw16basic ...` instead.

## Checking the install: `doctor`

```sh
python3 pcw16basic doctor
```

On the tested Linux set-up, it prints:

```text
ok   Python 3.13.16 (needs 3.10 or later; no other packages)
ok   Pasmo: /usr/bin/pasmo (0.5.3 is the version tested)
ok   runtime/runtime.z80.asm
ok   tools/build.py
ok   tools/pbimage.py
ok   examples/lib/sprite.pbas
ok   LANGUAGE-SPEC.md
PcW16 BASIC 1.0.0rc2 at /path/to/PcW16-BASIC
ready
```

Every line should start `ok`, and the last line should say `ready`. The exit status is then 0. A line starting `FAIL` names what is missing, and the last line becomes `not ready: fix the FAIL lines above`. For example, without Pasmo it prints:

```text
FAIL Pasmo is not on PATH: install Pasmo 0.5.3 (https://pasmo.speccy.org/) to build .PRG files; 'check' works without it
```

`doctor` checks only that a `pasmo` is on the `PATH`. It does not check that `pasmo` is version 0.5.3. [troubleshooting.md](troubleshooting.md) covers each `FAIL` line.

## The full self-check: `tools/verify_public.py`

```sh
python3 tools/verify_public.py            # everything except the test suite
python3 tools/verify_public.py --tests    # also the whole test suite (much longer)
```

This script checks the copy end to end, and it writes nothing into the folder: all its builds go to a temporary folder. It does the following:
1. it compares every file with `SHA256SUMS`;
2. it checks Python and Pasmo, as `doctor` does;
3. it rebuilds each prebuilt program in [`programs/`](../programs/MANIFEST.md) and each picture, and checks that they come out byte for byte the same;
4. it builds every example, tutorial and probe in the catalogue;
5. it builds every program shown in the documentation (`tools/check_docs.py`);
6. it makes and builds an application and a game with `pcw16basic new`;
7. it checks that no file names a path outside the repository, and that none is a system, ROM, font or disk-image file.

Each line starts `ok`, `FAIL` or `note`. The last line is `verify_public: every check passed`, with exit status 0, or `verify_public: N check(s) failed`. A byte-for-byte match in step 3 means that your Python and Pasmo produce exactly the programs that were tested in XAnne.

## Removing it

Delete the folder. If you installed the command, run `python3 -m pip uninstall pcw16basic` first, or delete the virtual environment.

Next: [first-program.md](first-program.md).
