"""Check this copy of PcW16 BASIC from end to end.

    python3 tools/verify_public.py            everything below except the test suite
    python3 tools/verify_public.py --tests    ... and the test suite (tools/run_tests.py full)

1. Every file is the one SHA256SUMS lists, and nothing is missing.
2. Python 3.10 or later and Pasmo are present (as `pcw16basic doctor` checks).
3. Every prebuilt program in programs/ is rebuilt from its source with the
   options programs/MANIFEST.md gives, and must come out byte for byte the
   same; so must the pictures, rebuilt from examples/assets.
4. Every example, tutorial and probe in the catalogue builds.
5. Every program shown in the documentation builds (tools/check_docs.py).
6. A new project made by `pcw16basic new` builds, for an application and
   for a game.
7. No file names a path outside this folder, and no file is a system file,
   ROM, font or disk image or a disassembly listing.

It writes nothing into this folder: builds go to a temporary folder.
Exit status 0 only if every check passed.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_NAME = re.compile(r"(?i)(\.sys$|\.rom$|\.fnt$|\.fon$|rosan\w*\.doc$|\.dsk$|\.img$|\.cfi$)")
DUMP_LINE = re.compile(r"(f\+[0-9A-Fa-f]{4}\b)|(^\s*\$?[0-9A-Fa-f]{4}:?\s+(?:[0-9A-Fa-f]{2}\s){3,})", re.M)
PRIVATE = re.compile(r"/home/\w|/tmp/claude|PcW16-BASIC-Development-Private|scratchpad|C:\\Users", re.I)
# names of material that is deliberately not in this repository; source comments cite them
# (the accepted compiler is kept byte for byte), so they are counted, not refused
ELSEWHERE = re.compile(r"Supporting Docs/|rosanne-research|\bPOC/|RUNTIME-RESULTS\.md|docs/M\d+[A-Z]?-[A-Z0-9-]+\.md")
TEXT = (".py", ".md", ".txt", ".pbas", ".asm", ".toml", ".json", ".csv", "")


class Report:
    def __init__(self):
        self.failed = 0

    def check(self, ok: bool, what: str, detail: str = ""):
        print(("ok    " if ok else "FAIL  ") + what + (f"\n      {detail}" if detail and not ok else ""))
        self.failed += 0 if ok else 1


def build(src: Path, out: Path, *opts: str) -> tuple[bool, str, Path]:
    cmd = [sys.executable, str(ROOT / "tools" / "build.py"), str(src), "--out-dir", str(out), *opts]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, (r.stderr + r.stdout).strip(), out / (src.stem + ".prg")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tests", action="store_true", help="also run the test suite")
    args = ap.parse_args(argv)
    rep = Report()

    # 1. checksums
    sums = {}
    for line in (ROOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        sha, rel = line.split("  ", 1)
        sums[rel] = sha
    bad = [r for r, s in sums.items() if not (ROOT / r).is_file()
           or hashlib.sha256((ROOT / r).read_bytes()).hexdigest() != s]
    extra = [str(p.relative_to(ROOT)).replace("\\", "/") for p in ROOT.rglob("*") if p.is_file()
             and "__pycache__" not in p.parts and ".git" not in p.parts and p.name != "SHA256SUMS"
             and not any(part.endswith(".egg-info") for part in p.parts)  # made by pip install -e .
             and str(p.relative_to(ROOT)).replace("\\", "/") not in sums]
    rep.check(not bad, f"SHA256SUMS: {len(sums)} files as listed", f"changed or missing: {bad[:10]}")
    if extra:
        print(f"note  {len(extra)} files not in SHA256SUMS (your own additions?): {extra[:5]}")

    # 2. tools
    rep.check(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]} (3.10 or later)")
    rep.check(shutil.which("pasmo") is not None, "Pasmo on the PATH", "install Pasmo: docs/install.md")
    if shutil.which("pasmo") is None:
        return 1

    with tempfile.TemporaryDirectory(prefix="pcw16-verify-") as tmp:
        tmp = Path(tmp)
        # 3. prebuilt programs and pictures
        manifest = (ROOT / "programs" / "MANIFEST.md").read_text(encoding="utf-8")
        pics = tmp / "pics"
        subprocess.run([sys.executable, str(ROOT / "tools" / "pbimage.py"), "build",
                        str(ROOT / "examples" / "assets" / "ASSETS.txt"), str(pics)],
                       capture_output=True, check=False)
        for m in re.finditer(r"^\| (\S+) \| (.+?) \| .+? \| `([0-9a-f]{64})` \|$", manifest, re.M):
            name, what, sha = m.groups()
            have = (ROOT / "programs" / name).read_bytes()
            if name.upper().endswith(".PBI"):
                made = pics / name
                same = made.is_file() and made.read_bytes() == have
                rep.check(same and hashlib.sha256(have).hexdigest() == sha,
                          f"programs/{name}: rebuilt from examples/assets, identical")
                continue
            src, *opts = what.split()
            ok, msg, prg = build(ROOT / src, tmp / "prg" / name, *opts)
            same = ok and prg.read_bytes() == have
            rep.check(same and hashlib.sha256(have).hexdigest() == sha,
                      f"programs/{name}: rebuilt from {what}, identical", msg[-400:])

        # 4. every catalogued program builds
        cat_file = ROOT / "examples" / "README.md"
        catalogue = cat_file.read_text(encoding="utf-8") if cat_file.is_file() else ""
        listed = sorted(set(re.findall(r"`((?:examples|developer-tests)/[\w/]+\.pbas)`", catalogue)))
        rep.check(bool(listed), f"examples/README.md lists {len(listed)} programs")
        for rel in listed:
            src = ROOT / rel
            if not src.is_file():
                rep.check(False, f"{rel}: listed in the catalogue but missing")
                continue
            ok, msg, _ = build(src, tmp / "ex" / src.stem)
            if not ok and "the resident part is" in msg:
                ok, msg, _ = build(src, tmp / "ex" / src.stem, "--runtime-banks", "all")
            rep.check(ok, f"{rel} builds", msg[-400:])

        # 5. the documentation's programs
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_docs.py")], capture_output=True, text=True)
        rep.check(r.returncode == 0, "documentation: " + (r.stdout.strip().splitlines() or ["?"])[-1],
                  r.stdout[-1500:])

        # 6. new projects
        for kind in ("app", "game"):
            work = tmp / f"new-{kind}"
            work.mkdir()
            a = subprocess.run([sys.executable, str(ROOT / "pcw16basic"), "new", f"my{kind}", "--kind", kind],
                               cwd=work, capture_output=True, text=True)
            b = subprocess.run([sys.executable, str(ROOT / "pcw16basic"), "build", f"my{kind}.pbas"],
                               cwd=work / f"my{kind}", capture_output=True, text=True)
            prg = work / f"my{kind}" / "build" / f"my{kind}.prg"
            rep.check(a.returncode == 0 and b.returncode == 0 and prg.is_file(),
                      f"pcw16basic new my{kind} --kind {kind}, then build", (a.stderr + b.stderr)[-400:])

    # 7. nothing private, nothing proprietary
    leaks, forbidden, dumps, elsewhere = [], [], [], []
    for p in sorted(ROOT.rglob("*")):
        if (not p.is_file() or "__pycache__" in p.parts or ".git" in p.parts
                or any(part.endswith(".egg-info") for part in p.parts)):
            continue
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if FORBIDDEN_NAME.search(p.name):
            forbidden.append(rel)
        if p.suffix.lower() in TEXT and rel not in ("tools/verify_public.py",):
            text = p.read_text(encoding="latin-1")
            if PRIVATE.search(text):
                leaks.append(f"{rel}: {PRIVATE.search(text).group(0)}")
            if len(DUMP_LINE.findall(text)) >= 40:
                dumps.append(rel)
            if ELSEWHERE.search(text):
                elsewhere.append(rel)
    rep.check(not leaks, "no file names a private path", "; ".join(leaks[:8]))
    rep.check(not forbidden, "no system, ROM, font or disk-image file", ", ".join(forbidden))
    rep.check(not dumps, "no disassembly listing", ", ".join(dumps))
    if elsewhere:
        print(f"note  {len(elsewhere)} files cite material that is not in this repository "
              "(the project's engineering records, its prototype, Amstrad's documents): "
              "docs/README.md, \"References in the source\"")

    if args.tests:
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "run_tests.py"), "full"], cwd=ROOT,
                           capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip()
        summary = [ln for ln in r.stdout.splitlines() if ln.startswith("full:")] or out.splitlines()[-1:] or ["?"]
        rep.check(r.returncode == 0, "test suite: " + summary[-1], out[-3000:])

    print(f"verify_public: {rep.failed} check(s) failed" if rep.failed else "verify_public: every check passed")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
