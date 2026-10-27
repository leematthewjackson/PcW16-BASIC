"""Memory report: where a program's .PRG image goes (M8).

    python3 tools/memreport.py [--string-capacity N] PROGRAM.pbas [...]
    python3 tools/memreport.py --markdown ...      (a table for the docs)
    python3 tools/memreport.py --whole-real-library ...   (as M7 built it)

Every byte of the assembled image is attributed to the label that starts
it (Pasmo symbol table, all labels sorted by address). Program labels are
classified by the code generator's naming conventions. Runtime labels are
classified by the innermost `IF PB_x` section they are defined in, and a
runtime `label:` followed by `defs N` counts as workspace. The 256-byte
prefix and the space left below #8000 are reported separately. This is an
engineering measurement tool: it changes nothing in the build.

M11: the report is made from the real build (``pbas.prg.build``, the same
files ``tools/build.py`` writes), so a code-banked program (M9) is measured
as it is built: its resident block (with one far-call stub per procedure)
is attributed as above, and each code bank is listed with its bytes. Up to
M10 the tool assembled its own single image, which failed for every program
once the runtime needed the code-bank symbols (KI-53).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pbas.codebanks import read_symbols  # noqa: E402
from pbas.errors import SourceError  # noqa: E402
from pbas.prg import RUNTIME_MARKER, build  # noqa: E402

IMAGE_LIMIT = 16384
PREFIX = 256

REAL_SECTIONS = {"REAL"}
FILE_SECTIONS = {"FILES", "FIO", "FILE_DEVICE"}
GUI_SECTIONS = {"DIALOG", "BINDINGS", "LIST", "CHOICE", "SLIDER", "LABELS", "RADIO", "NUMBERS", "SPIN",
                "SCROLL", "CHANGE", "KEYS", "WINDOWS", "POST", "FOCUS", "MENUS", "TIMER", "ASK", "BEEP",
                "CONTROLS"}

ORDER = ["prefix", "program code", "code-bank stubs", "runtime-bank veneers", "variables", "arrays", "GUI definitions and tables", "static strings and constants",
         "file descriptors", "runtime: common", "runtime: REAL library", "runtime: files", "runtime: GUI",
         "runtime workspace and buffers", "free (to the 16K limit)"]


def runtime_sections(text: str) -> tuple[dict[str, str], set[str]]:
    """label -> innermost PB_ feature section; and the set of defs cells."""
    stack: list[str] = []
    where: dict[str, str] = {}
    cells: set[str] = set()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"\s+IF\s+(.*)", line)
        if m:
            names = re.findall(r"PB_(\w+)", m.group(1))
            stack.append(names[0] if len(names) == 1 else "+".join(names) or "?")
            continue
        if re.match(r"\s+ENDIF\b", line):
            stack.pop()
            continue
        m = re.match(r"^(\w+):", line)
        if m:
            where[m.group(1).lower()] = stack[-1] if stack else ""
            nxt = line[m.end():].strip() or (lines[i + 1].strip() if i + 1 < len(lines) else "")
            if nxt.startswith("defs"):
                cells.add(m.group(1).lower())
    return where, cells


def runtime_category(section: str) -> str:
    if "+" in section:  # a guard shared by several features
        return "runtime: common"
    parts = {section} if section else set()
    if parts == REAL_SECTIONS:
        return "runtime: REAL library"
    if parts & FILE_SECTIONS:
        return "runtime: files"
    if parts & GUI_SECTIONS:
        return "runtime: GUI"
    return "runtime: common"


def program_category(label: str, arrays: set[str]) -> str:
    if label.startswith("var_"):
        return "arrays" if label[4:] in arrays else "variables"
    if label.startswith(("cgarr_",)):
        return "arrays"
    if label.startswith(("cgforlimit_", "cgsel", "cgtmp")):
        return "variables"
    if label.startswith(("lit_", "msgdef_", "cgreal_", "str_")):
        return "static strings and constants"
    if label.startswith(("gui_", "ask_", "menu_")) or "ltab_" in label or "lcnt_" in label or "tpl_" in label:
        return "GUI definitions and tables"
    if label.startswith("pb_file"):
        return "file descriptors"
    return "program code"


def report(source: Path, capacity: int, prune: bool = True,
           code_banks: str = "auto", sections: Counter | None = None, rt_banks=()
           ) -> tuple[Counter, int, list[tuple[int, int, int]]]:
    """(bytes per category of the resident 16K block, resident image size,
    [(bank number, bytes used, procedures)] for a code-banked build).
    *sections*, if given, receives the runtime's bytes by innermost ``IF PB_x``
    section (workspace cells included; "-" outside any section)."""
    with tempfile.TemporaryDirectory() as tmp:
        asm, prg = Path(tmp) / "p.asm", Path(tmp) / "p.prg"
        over = None
        try:
            built = build(source, asm, prg, string_capacity=capacity, prune=prune, code_banks=code_banks,
                          runtime_sections=rt_banks)
        except SourceError as exc:  # M13: still show where the bytes go when it does not fit
            # M14: also a single image over 16K (a program without SUBs or FUNCTIONs)
            fits_not = "the resident part is" in exc.message or "assembled image is" in exc.message
            if not fits_not or not prg.exists():
                raise
            over, built = prg.stat().st_size, None
        text = asm.read_text(encoding="utf-8")
        sym = asm.with_suffix(".sym")
        if (built is None or built.banked is None) and not sym.exists():  # a single image writes none
            subprocess.run(["pasmo", "--bin", str(asm), str(Path(tmp) / "s.bin"), str(sym)],
                           check=True, capture_output=True)
        symbols = {name.lower(): addr for name, addr in read_symbols(sym).items()}
    program, runtime = text.split(RUNTIME_MARKER, 1)
    where, cells = runtime_sections(runtime)
    prog_labels = {m.group(1).lower() for m in re.finditer(r"^([A-Za-z_][\w.]*):", program, re.M)}
    arrays = {m.group(1).lower() for m in re.finditer(r"^cgarr_(\w+):", program, re.M)}
    banks = []
    stubs: set[str] = set()
    veneers: set[str] = set()
    if over is not None:  # the resident block alone, as far as the build got (code-bank stubs count as code)
        size = over
    elif built.banked is not None:
        size = built.banked.resident_size
        banks = [(b.number, b.used, len(b.procedures)) for b in built.banked.banks]
        stubs = {f"sub_{s}".lower() for b in built.banked.banks for s in b.procedures}
        veneers = {name.lower() for name in built.banked.runtime_entries}  # M11
    else:
        size = built.prg_size
    labels = sorted((addr, name) for name, addr in symbols.items()
                    if 0x4100 <= addr < 0x4000 + size and (name in prog_labels or name in where))
    out = Counter({"prefix": PREFIX})
    bounds = [a for a, _ in labels] + [0x4000 + size]
    if labels and labels[0][0] > 0x4100:
        out["program code"] += labels[0][0] - 0x4100
    for (addr, name), end in zip(labels, bounds[1:]):
        span = end - addr
        if name in stubs:
            out["code-bank stubs"] += span
        elif name in veneers:
            out["runtime-bank veneers"] += span
        elif name in prog_labels:
            out[program_category(name, arrays)] += span
        elif name in cells:
            out["runtime workspace and buffers"] += span
        else:
            out[runtime_category(where[name])] += span
        if sections is not None and name not in prog_labels:
            sections[where[name] or "-"] += span
    out["free (to the 16K limit)"] = IMAGE_LIMIT - size
    return out, size, banks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sources", nargs="+", type=Path)
    ap.add_argument("--string-capacity", type=int, default=64)
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--whole-real-library", action="store_true", help="measure the build with the whole REAL library")
    ap.add_argument("--runtime-banks", default="", metavar="all|SECTION,...",
                    help="measure the build with runtime sections in a code bank")
    ap.add_argument("--sections", action="store_true",
                    help="also list the resident runtime's bytes by IF PB_x section")
    args = ap.parse_args()
    rows = []
    failed = False
    for src in args.sources:
        cap = args.string_capacity
        m = re.search(r"^' Build with --string-capacity (\d+)", src.read_text(encoding="utf-8"), re.M)
        if m:
            cap = int(m.group(1))
        sections = Counter()
        rt = (args.runtime_banks if args.runtime_banks in ("", "all")
              else tuple(s.strip().upper() for s in args.runtime_banks.split(",")))
        try:
            counts, size, banks = report(src, cap, prune=not args.whole_real_library, sections=sections,
                                         rt_banks=rt)
        except SourceError as exc:  # M14: a program that does not compile: its message, not a traceback
            print(f"{src}:{exc.line}:{exc.column}: {exc.message}", file=sys.stderr)
            failed = True
            continue
        assert sum(counts.values()) == IMAGE_LIMIT, (src, sum(counts.values()))
        rows.append((src.stem, size, counts, banks))
        if args.sections:
            print(f"{src.stem}: resident runtime by section")
            for name, n in sorted(sections.items(), key=lambda kv: -kv[1]):
                print(f"  {n:6}  {name}")
    if args.markdown:
        print("| bytes | " + " | ".join(r[0] for r in rows) + " |")
        print("|---|" + "---:|" * len(rows))
        print("| **image** | " + " | ".join(f"**{r[1]}**" for r in rows) + " |")
        for key in ORDER:
            print(f"| {key} | " + " | ".join(str(r[2].get(key, 0)) for r in rows) + " |")
        print("| code banks (bytes used) | " + " | ".join(
            " + ".join(str(used) for _, used, _ in r[3]) or "–" for r in rows) + " |")
    else:
        for stem, size, counts, banks in rows:
            print(f"{stem}: {'resident block' if banks else 'image'} {size} bytes")
            if size > IMAGE_LIMIT:
                print(f"  ** {size - IMAGE_LIMIT} bytes over the {IMAGE_LIMIT}-byte limit: it does not build **")
            for key in ORDER:
                print(f"  {counts.get(key, 0):6}  {key}")
            for number, used, procs in banks:
                print(f"  code bank {number}: {used} bytes, {procs} procedure(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
