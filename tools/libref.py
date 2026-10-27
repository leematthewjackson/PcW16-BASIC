"""The library reference, docs/LIBRARY-REFERENCE.md, from the libraries'
own header comments (M13 Stage J).

    python3 tools/libref.py            write docs/LIBRARY-REFERENCE.md
    python3 tools/libref.py --check    exit 1 if the file is out of date

Each library in examples/lib begins with a comment that is its reference:
what it is for, what to INCLUDE first, what the program sets, every SUB and
FUNCTION, and the prefix of its names. This tool copies those comments,
in the order below, with a table of the SUBs and FUNCTIONs each defines
(read from the code, so a procedure the comment forgets still shows), so
the reference cannot drift from the libraries.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "examples" / "lib"
OUT = ROOT / "docs" / "LIBRARY-REFERENCE.md"
ORDER = [  # (file, group)
    ("app", "Applications"), ("forms", "Applications"), ("listview", "Applications"), ("files", "Applications"),
    ("geom", "Graphics and interaction"), ("drag", "Graphics and interaction"),
    ("handles", "Graphics and interaction"), ("scene", "Graphics and interaction"),
    ("toolbar", "Graphics and interaction"),
    ("sprite", "Games"), ("keys", "Games"), ("pace", "Games"),
    ("chart", "Charts and printing"), ("chartprt", "Charts and printing"),
]
PROC = re.compile(r"^(SUB|FUNCTION)\s+(\w+\$?)\s*(\([^)]*\))?\s*(AS\s+\w+)?", re.M | re.I)


def header(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if not line.startswith("'"):
            break
        lines.append(line[1:][1:] if line.startswith("' ") else line[1:])
    return "\n".join(lines).rstrip()


def render() -> str:
    names = {p.stem for p in LIB.glob("*.pbas")}
    listed = {n for n, _ in ORDER}
    missing = sorted(names - listed)
    if missing:
        raise SystemExit(f"libref.py: add {', '.join(missing)} to ORDER")
    out = ["# PcW16 BASIC library reference", "",
           "The libraries in `examples/lib/` are ordinary PcW16 BASIC: `INCLUDE \"lib/NAME.pbas\"` near the top "
           "of a program (each library once; one that needs another says so). Every name a library declares "
           "starts with its prefix, and a program's own CONSTs never clash with a library's parameters "
           "(LANGUAGE-SPEC §5.1). This page is made from each library's own opening comment by "
           "`tools/libref.py`; the code is the authority. docs/libraries/README.md shows how the graphical ones "
           "fit together; tests/test_m11_*, test_m12_* and test_m13_libraries.py test them.", ""]
    group = None
    for name, g in ORDER:
        if g != group:
            out += [f"## {g}", ""]
            group = g
        text = (LIB / f"{name}.pbas").read_text(encoding="utf-8")
        out += [f"### lib/{name}.pbas", "", "```text", header(text), "```", ""]
        procs = PROC.findall(text)
        if procs:
            out += ["Defines (with its internal helpers; the comment above says which are for programs):", ""]
            for kind, pname, params, result in procs:
                out.append(f"- `{kind.upper()} {pname}{params or ''}{' ' + result if result else ''}`")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def main(argv=None) -> int:
    import argparse  # M14 (T3): any argument used to rewrite the file, --help included
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="change nothing; exit 1 if docs/LIBRARY-REFERENCE.md is out of date")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    text = render()
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT} is out of date: run python3 tools/libref.py", file=sys.stderr)
            return 1
        print(f"{OUT}: up to date ({len(ORDER)} libraries)")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"{OUT}: {len(ORDER)} libraries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
