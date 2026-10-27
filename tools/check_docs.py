"""Build every program shown in the documentation, and check what it says.

    python3 tools/check_docs.py                 all Markdown files under docs/, and README.md
    python3 tools/check_docs.py FILE.md ...     just these
    python3 tools/check_docs.py --list          the blocks found, without building

A fenced block marked ``pbas`` is a complete program. It is built exactly as
``pcw16basic build`` would build it (tools/build.py, Pasmo included, and with
``--runtime-banks all`` if it does not fit with the runtime resident), in an
empty folder holding a copy of ``examples/lib``, so ``INCLUDE "lib/..."``
works as it does in a project made by ``pcw16basic new``. Lines in the block
of the form

    ' expect-message: text

say what the program's MESSAGE alerts must be, in order, when it runs on the
PcW16 BASIC simulator (tests/z80sim.py) with no input. A block marked
``pbas-error`` must NOT compile, and its line

    ' expect-error: words

gives words the compiler's message must contain. Blocks marked anything else
(``text``, ``sh``, ...) are not checked.

Exit status 0 only if every block did what it says. The simulator is a model
of Rosanne, not Rosanne: a block that passes here has been compiled,
assembled and (with expect-message) run on the model; only XAnne or a PcW16
shows how it really behaves.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FENCE = re.compile(r"^( *)```([A-Za-z0-9_-]*)\s*$")  # also inside list items (indented)


def blocks(md: Path):
    """(kind, first line number, text) of each fenced block in *md*."""
    lines = md.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if m:
            indent, kind, start, body = len(m.group(1)), m.group(2), i + 1, []
            i += 1
            while i < len(lines) and not lines[i].lstrip(" ").startswith("```"):
                line = lines[i]
                body.append(line[indent:] if line[:indent].strip() == "" else line)
                i += 1
            yield kind, start + 1, "\n".join(body) + "\n"
        i += 1


def build(root: Path, src: str, name: str, work: Path):
    """Build *src* as work/<name>.pbas: (ok, message, .prg path)."""
    folder = work / name
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    shutil.copytree(root / "examples" / "lib", folder / "lib")
    path = folder / f"{name}.pbas"
    path.write_text(src, encoding="utf-8")
    cmd = [sys.executable, str(root / "tools" / "build.py"), str(path), "--out-dir", str(folder / "build")]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0 and "the resident part is" in out.stderr:
        out = subprocess.run(cmd + ["--runtime-banks", "all"], capture_output=True, text=True)
    prg = folder / "build" / f"{name}.prg"
    return out.returncode == 0 and prg.is_file(), (out.stderr + out.stdout).strip(), prg


def run_messages(root: Path, prg: Path) -> list[str]:
    sys.path.insert(0, str(root / "tests"))
    import z80sim  # the project's model of the PcW16 and Rosanne
    cpu = z80sim.run(prg.read_bytes(), events=[], max_steps=200_000_000)
    return list(cpu.alerts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--root", type=Path, default=ROOT, help="the PcW16 BASIC folder (pbas/, tools/, examples/lib)")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    files = args.files or sorted([root / "README.md"] + list((root / "docs").rglob("*.md")))
    failures, counts = [], {"pbas": 0, "pbas-error": 0, "messages": 0}
    with tempfile.TemporaryDirectory(prefix="pcw16-docs-") as tmp:
        work = Path(tmp)
        for md in files:
            md = Path(md)
            for n, (kind, line, text) in enumerate(blocks(md)):
                if kind not in ("pbas", "pbas-error"):
                    continue
                where = f"{md}:{line}"
                if args.list:
                    print(f"{kind:10} {where}")
                    continue
                counts[kind] += 1
                name = f"doc{len(failures) + sum(counts.values())}"
                ok, msg, prg = build(root, text, name, work)
                if kind == "pbas":
                    if not ok:
                        failures.append(f"{where}: does not build:\n    " + msg.replace("\n", "\n    "))
                        continue
                    want = [m.group(1) for m in re.finditer(r"^\s*' expect-message: (.*?)\s*$", text, re.M)]
                    if want:
                        counts["messages"] += 1
                        got = run_messages(root, prg)
                        if got != want:
                            failures.append(f"{where}: messages {got!r}, the text says {want!r}")
                else:
                    want = re.search(r"^\s*' expect-error: (.*?)\s*$", text, re.M)
                    if ok:
                        failures.append(f"{where}: was meant not to compile, but it built")
                    elif want and want.group(1).lower() not in msg.lower():
                        failures.append(f"{where}: the error is {msg!r}, the text says it contains {want.group(1)!r}")
    if args.list:
        return 0
    for f in failures:
        print("FAIL", f)
    print(f"check_docs: {counts['pbas']} programs built ({counts['messages']} run on the simulator), "
          f"{counts['pbas-error']} error examples, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
