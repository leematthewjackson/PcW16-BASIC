"""pcw16basic: one command for the PcW16 BASIC tools.

    pcw16basic doctor                       check Python, Pasmo and the install
    pcw16basic new NAME [--kind app|game]   a new project folder to start from
    pcw16basic check PROGRAM.pbas           every check build makes, without Pasmo
    pcw16basic build PROGRAM.pbas [options] compile to build/<name>.prg
    pcw16basic assets [MANIFEST] [OUTDIR]   PNG pictures to PBI1 files
    pcw16basic image ...                    tools/pbimage.py (import, sheet, export, info)
    pcw16basic memory PROGRAM.pbas          where the 16K resident block goes
    pcw16basic test [fast|full]             the project's own test suite

It drives the scripts in tools/ (each also usable on its own) and adds no
compiler logic. ``build`` passes its options to tools/build.py; when a
program does not fit the 16K resident block it builds again with
``--runtime-banks all`` and says so. Run it from a source checkout
(``python3 pcw16basic ...`` in this folder) or after ``pip install -e .``.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
VERSION = "1.0.0rc1"
PYTHON_MIN = (3, 10)

# SPDX-License-Identifier: MIT-0 for the template texts APP_TEMPLATE, GAME_TEMPLATE and
# ASSETS_TEMPLATE (what `new` writes into a project); this file itself is GPL-3.0-or-later.
# LICENSING.md.
APP_TEMPLATE = """' {name}: a PcW16 BASIC application (made by pcw16basic new).
' Build:  pcw16basic build {name}.pbas      Copy build/{name}.prg to the
' PcW16 as {upper}.PRG. docs/manual/README.md explains every statement and
' docs/libraries/README.md the libraries included below.
INCLUDE "lib/app.pbas"
INCLUDE "lib/geom.pbas"

DIM Clicks AS INTEGER

WINDOW Main, "{upper}", LARGE
LABEL AppStatus$
CANVAS 400, 160, PAINT Paint, MOUSE Mouse
BUTTON "Clear", ClearAll
BUTTON "Quit", Quit

MENU "File"
    ITEM "Quit", Quit, KEY "Q"
END MENU

SUB Paint
    DRAW CLEAR
    DRAW BOX 0, 0, 400, 160
    DRAW TEXT 8, 8, "Click to draw a box"
END SUB

SUB Mouse
    IF MOUSEEVENT = 1 THEN
        DRAW BOX GeomClamp(MOUSEX - 5, 0, 389), GeomClamp(MOUSEY - 5, 0, 149), 10, 10
        Clicks = Clicks + 1
        CALL AppSay(STR$(Clicks) + " boxes")
    END IF
END SUB

SUB ClearAll
    Clicks = 0
    CALL Paint
    CALL AppSay("Cleared")
END SUB

FUNCTION AppSave() AS BOOLEAN
    RETURN TRUE
END FUNCTION

SUB Quit
    EXIT
END SUB

CALL AppSay("Ready")
END
"""

GAME_TEMPLATE = """' {name}: a PcW16 BASIC game (made by pcw16basic new --kind game).
' Hold Left / Right to move the square, Space to jump; Stop quits.
' Build:  pcw16basic build {name}.pbas      Copy build/{name}.prg to the
' PcW16 as {upper}.PRG. docs/manual/13-bitmaps-and-sprites.md and
' examples/jumper.pbas show more: sprites from PNG pictures, masks, platforms.
INCLUDE "lib/geom.pbas"
INCLUDE "lib/sprite.pbas"
INCLUDE "lib/keys.pbas"
INCLUDE "lib/pace.pbas"

CONST CW = 320
CONST CH = 160
DIM Look AS BITMAP * 16, 16
DIM LookM AS BITMAP * 16, 16
DIM Back AS BITMAP * 320, 160
DIM Score$ AS STRING * 24
DIM VY AS INTEGER
DIM Ready AS BOOLEAN

WINDOW Main, "{upper}", LARGE
LABEL Score$
CANVAS 320, 160, PAINT Paint, KEYS Keys
BUTTON "Quit", Quit
TIMER Update, EVERY 2 TICKS

' The sprite is drawn here, then captured: a picture made with
' tools/pbimage.py and BITMAP LOAD works the same way.
SUB MakeSprite
    DRAW CLEAR
    DRAW FILL 0, 0, 16, 16
    DRAW INK WHITE
    DRAW FILL 4, 4, 3, 3, 8
    DRAW FILL 9, 4, 3, 3, 8
    DRAW INK BLACK
    BITMAP GET Look, 0, 0, 16, 16
    DRAW FILL 0, 0, 16, 16, 8
    BITMAP GET LookM, 0, 0, 16, 16
END SUB

SUB Paint
    IF NOT Ready THEN
        CALL MakeSprite
        DRAW CLEAR
        DRAW FILL 0, CH - 16, CW, 16, 4
        BITMAP GET Back, 0, 0, CW, CH
        Ready = TRUE
    END IF
    BITMAP PUT Back, 0, 0
    CALL SpriteShow(Look, LookM, 1)
END SUB

' Each TIMER event: the steps of 1/8 s due since the last one (lib/pace.pbas:
' Rosanne may bring fewer events than asked for), then one draw.
SUB Update
    LOCAL N AS INTEGER
    LOCAL X AS INTEGER
    LOCAL Y AS INTEGER
    IF NOT Ready THEN
        EXIT SUB
    END IF
    N = PaceSteps()
    IF N = 0 THEN
        EXIT SUB
    END IF
    X = SprX(1)
    Y = SprY(1)
    WHILE N > 0
        X = GeomClamp(X + 4 * KeyAxis(SC_LEFT, SC_RIGHT), 0, CW - 16)
        IF KEYDOWN(SC_SPACE) AND Y = CH - 32 THEN
            VY = -10
        END IF
        Y = MIN(Y + VY, CH - 32)
        VY = MIN(VY + 2, 8)
        N = N - 1
    WEND
    CALL SpriteMove(Look, LookM, Back, 1, X, Y, 0)
    Score$ = "X " + STR$(X) + "  Y " + STR$(Y)
END SUB

SUB Keys
    IF KEYCODE = KC_STOP THEN
        CALL Quit
    END IF
END SUB

SUB Quit
    TIMER OFF
    EXIT
END SUB

SprCW = CW
SprCH = CH
SprW(1) = 16
SprH(1) = 16
SprX(1) = 20
SprY(1) = CH - 32
CALL PaceStart(2, 4)
Score$ = "Left / Right, Space"
END
"""

ASSETS_TEMPLATE = """# Pictures for {name}: PNG sources here, one line each:
#   TARGET.PBI  import|sheet  SOURCE.png  [options]
# then: pcw16basic assets assets/ASSETS.txt build   (docs/graphics-assets.md)
"""


def _tool(script: str, args: list[str]) -> int:
    return subprocess.call([sys.executable, str(TOOLS / script), *args])


def cmd_doctor(_args) -> int:
    ok = True
    py = sys.version_info[:3]
    good = py >= PYTHON_MIN
    ok &= good
    print(f"{'ok  ' if good else 'FAIL'} Python {'.'.join(map(str, py))} (needs "
          f"{'.'.join(map(str, PYTHON_MIN))} or later; no other packages)")
    pasmo = shutil.which("pasmo")
    if pasmo:
        print(f"ok   Pasmo: {pasmo} (0.5.3 is the version tested)")
    else:
        ok = False
        print("FAIL Pasmo is not on PATH: install Pasmo 0.5.3 (https://pasmo.speccy.org/) to build .PRG files; "
              "'check' works without it")
    for part in ("runtime/runtime.z80.asm", "tools/build.py", "tools/pbimage.py", "examples/lib/sprite.pbas",
                 "LANGUAGE-SPEC.md"):
        there = (ROOT / part).exists()
        ok &= there
        print(f"{'ok  ' if there else 'FAIL'} {part}")
    print(f"PcW16 BASIC {VERSION} at {ROOT}")
    print("ready" if ok else "not ready: fix the FAIL lines above")
    return 0 if ok else 1


def cmd_new(args) -> int:
    name = args.name
    if not name.isidentifier() or len(name) > 8:
        print("pcw16basic new: the name is a PcW16 program name: letters, digits and _, at most 8", file=sys.stderr)
        return 2
    target = Path(args.dir or name)
    if target.exists():
        print(f"pcw16basic new: {target} already exists; choose another name (nothing was written)",
              file=sys.stderr)
        return 1
    (target / "assets").mkdir(parents=True)
    shutil.copytree(ROOT / "examples" / "lib", target / "lib")
    text = (GAME_TEMPLATE if args.kind == "game" else APP_TEMPLATE).format(
        name=name, upper=name.upper(), lower=name.lower())
    (target / f"{name}.pbas").write_text(text, encoding="utf-8")
    (target / "assets" / "ASSETS.txt").write_text(ASSETS_TEMPLATE.format(name=name), encoding="utf-8")
    print(f"{target}/{name}.pbas  (a{'' if args.kind == 'app' else ' game'} starting point)")
    print(f"{target}/lib/         (the libraries: docs/libraries/README.md)")
    print(f"{target}/assets/      (PNG pictures and ASSETS.txt)")
    # M14 (evaluation finding): name the command as it can be typed here: `pcw16basic` once it
    # is installed (on the PATH), otherwise the launcher this was started with
    launcher = "pcw16basic" if shutil.which("pcw16basic") else f"python3 {Path(sys.argv[0]).resolve()}"
    print(f"next: cd {target} && {launcher} build {name}.pbas")
    return 0


def cmd_check(args) -> int:
    return subprocess.call([sys.executable, "-m", "pbas", "check", *args.rest], cwd=None,
                           env=_env())


def _env():
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def cmd_build(args) -> int:
    rest = list(args.rest)
    out = subprocess.run([sys.executable, str(TOOLS / "build.py"), *rest], capture_output=True, text=True)
    if out.returncode != 0 and "the resident part is" in out.stderr and "--runtime-banks" not in " ".join(rest):
        print("(it does not fit the 16K block with the runtime resident: building with --runtime-banks all)")
        out = subprocess.run([sys.executable, str(TOOLS / "build.py"), *rest, "--runtime-banks", "all"],
                             capture_output=True, text=True)
    sys.stdout.write(out.stdout)
    sys.stderr.write(out.stderr)
    return out.returncode


def cmd_assets(args) -> int:
    manifest = args.manifest or ("assets/ASSETS.txt" if Path("assets/ASSETS.txt").exists()
                                 else str(ROOT / "examples" / "assets" / "ASSETS.txt"))
    return _tool("pbimage.py", ["build", manifest, args.outdir or "build"])


PASSTHROUGH = {"check": None, "build": None, "image": "pbimage.py", "memory": "memreport.py"}

#: M14 (T7): a plain (non-editable) ``pip install .`` copies only the pbas
#: package; the runtime, tools and libraries stay in the folder. Supported
#: installs: run ``python3 pcw16basic`` in the folder, or ``pip install -e .``.
NOT_A_CHECKOUT = ("pcw16basic: this copy of the pbas package has no runtime/, tools/ or examples/lib/ "
                  "beside it ({root}). PcW16 BASIC runs from its own folder: run python3 pcw16basic "
                  "there, or install it with pip install -e . (editable); a plain pip install . "
                  "is not supported (docs/install.md)")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not (ROOT / "runtime" / "runtime.z80.asm").is_file() and argv[:1] != ["--version"]:
        print(NOT_A_CHECKOUT.format(root=ROOT), file=sys.stderr)
        return 2
    # M14 (T1): these hand every argument, --help included, to the tool behind them
    # (argparse's REMAINDER did not take a leading option: "unrecognized arguments")
    if argv and argv[0] in PASSTHROUGH:
        rest = argv[1:]
        if argv[0] == "check":
            return subprocess.call([sys.executable, "-m", "pbas", "check", *rest], env=_env())
        if argv[0] == "build":
            return cmd_build(argparse.Namespace(rest=rest))
        return _tool(PASSTHROUGH[argv[0]], rest)
    parser = argparse.ArgumentParser(prog="pcw16basic", description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", action="version", version=f"PcW16 BASIC {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check Python, Pasmo and the install")
    p = sub.add_parser("new", help="a new project folder")
    p.add_argument("name")
    p.add_argument("--kind", choices=("app", "game"), default="app")
    p.add_argument("--dir", help="the folder to create (default: NAME)")
    for name, help_ in (("check", "compile-check a program"), ("build", "compile a program to a .PRG"),
                        ("image", "PNG and PBI1 pictures (tools/pbimage.py)"),
                        ("memory", "the resident block, by part (tools/memreport.py)")):
        p = sub.add_parser(name, help=help_, add_help=False)
        p.add_argument("rest", nargs=argparse.REMAINDER)
    p = sub.add_parser("assets", help="make the PBI1 files a manifest lists")
    p.add_argument("manifest", nargs="?")
    p.add_argument("outdir", nargs="?")
    p = sub.add_parser("test", help="the test suite (tools/run_tests.py)")
    p.add_argument("tier", nargs="?", default="fast", choices=("fast", "full"))
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "new":
        return cmd_new(args)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "build":
        return cmd_build(args)
    if args.command == "assets":
        return cmd_assets(args)
    if args.command == "image":
        return _tool("pbimage.py", args.rest)
    if args.command == "memory":
        return _tool("memreport.py", args.rest)
    return subprocess.call([sys.executable, str(TOOLS / "run_tests.py"), args.tier], cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
