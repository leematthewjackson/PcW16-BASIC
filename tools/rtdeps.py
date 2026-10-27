"""Runtime dependency check: can a runtime section use a symbol that is not assembled? (M14)

    python3 tools/rtdeps.py [--verbose]

The runtime (runtime/runtime.z80.asm) is cut into conditional sections by
``IF PB_x`` ... ``ENDIF`` (with ``ELSE``, sums meaning "any of", ``DEFINED``
and ``PB_STR_TEMPS >= n``). A symbol defined inside a section exists only
when that section's condition holds. For every reference to a runtime symbol,
this tool asks: is there a choice of the compiler's switches for which the
referencing line is assembled but the definition is not? If so, a program
that sets those switches fails in Pasmo with "Symbol ... is undefined" (the
M14 defects D1 and D2 were two such cases).

The switches are not independent: the compiler sets some together
(``IMPLIES`` below, each with the line of pbas/ that does it). A finding is a
real defect only if the compiler can produce the combination; the regression
test (tests/test_m14_rtdeps.py) requires no findings.

Exit status 0 only if there are no findings.
"""
from __future__ import annotations

import argparse
import itertools
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime" / "runtime.z80.asm"

#: switch -> switches the compiler always sets with it. Each line is a fact of
#: pbas/statements.py (or of a rule the front end enforces before it):
IMPLIES = {
    "IMATH": {"DIV"},                                   # compile(): rt_rnd uses rt_mod16
    "TEXT": {"FIO", "FILES", "BANK", "ARRAYS"},         # compile(); uses_files; a TEXT variable is banked
    "TXRANGE": {"TEXT"},                                # text_statement()
    "TICKPOLL": {"CLOCKTICKS", "CKCAL", "TIMER"},       # compile(): set only with a TIMER and without --legacy-timing
    "CKCAL": {"CLOCKTICKS"},                            # compile()
    "RSTICKY": {"REAL"},                                # M14 compile(): set only with REAL
    "FSAFE": {"DB", "BANK", "ARRAYS", "FIO", "RECORDS", "FILES"},  # M14 compile(): set only with DB
    "STRFN": {"CHR", "SLICE"},                          # TRIM$ / SPACE$ / STRING$ (KI-64)
    "BITMAP": {"BANK", "ARRAYS"},                       # a BITMAP variable is banked; M14: bitmap_statement()
    "BANK": {"ARRAYS"},                                 # every place that sets BANK sets ARRAYS
    "BMPPART": {"BITMAP"},                              # M14: bitmap_statement()
    "BMPFILE": {"DB", "BANK", "ARRAYS", "FIO", "RECORDS", "BITMAP", "FILES"},  # BITMAP LOAD / SAVE
    "DB": {"BANK", "ARRAYS", "FIO", "RECORDS", "FILES"},  # DB statements; a DB function needs one (front end)
    "PAGE": {"FIO", "FILES"},                           # PAGE statements and (M14) PAGEWIDTH: uses_files
    "FIO": {"FILES"},                                   # IOERR / EOF need a file statement (front end)
    "FNAME": {"FIO", "FILES"},                          # a STRING file name in a file statement
    "LABELS": {"DIALOG", "BINDINGS"},                   # a dynamic LABEL is a bound row
    "KEYS": {"DIALOG"},                                 # a BUTTON's keys
    "CANVAS": {"DIALOG", "BINDINGS"},                   # bindings_on
    "CVLINE": {"CANVAS"}, "CVCELL": {"CANVAS"}, "POINT": {"CANVAS"},  # need a CANVAS (front end)
    "RADIO": {"DIALOG", "BINDINGS"}, "NUMBERS": {"DIALOG", "BINDINGS"},  # widgets; bindings_on
    "SPIN": {"NUMBERS"},
    "MENUS": {"DIALOG", "BINDINGS", "POST"}, "TIMER": {"DIALOG", "BINDINGS"},  # need a WINDOW; bindings_on
    "WINDOWS": {"DIALOG", "POST"}, "FOCUS": {"DIALOG", "POST"}, "POST": {"BINDINGS", "DIALOG"},
    "LIST": {"CTL2", "SCROLL"}, "SLIDER": {"CTL2", "SCROLL"}, "CHOICE": {"CTL2"},
    "SCROLL": {"CTL2"}, "CHANGE": {"CTL2"}, "CTL2": {"DIALOG", "BINDINGS"},
}

COND = re.compile(r"^\s*(IF|ELSE|ENDIF)\b\s*(.*?)\s*(;.*)?$")
LABEL = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):")
EQU = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s+equ\b", re.I)
WORD = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


def parse_cond(text: str) -> list[str]:
    """A condition as an OR of atoms."""
    text = text.strip()
    m = re.fullmatch(r"DEFINED\s+PB_(\w+)", text)
    if m:
        return [f"DEFINED_{m.group(1)}"]
    m = re.fullmatch(r"PB_STR_TEMPS\s*>=\s*(\d+)", text)
    if m:
        return [f"STR_TEMPS_{m.group(1)}"]
    atoms = [a.strip() for a in text.split("+")]
    out = []
    for a in atoms:
        m = re.fullmatch(r"PB_(\w+)", a)
        if not m:
            raise ValueError(f"unsupported condition {text!r}")
        out.append(m.group(1))
    return out


def scan(lines):
    """(definitions, references): symbol -> guard; [(symbol, guard, line)].

    A guard is a tuple of (atoms, positive) clauses, all of which must hold."""
    stack: list[tuple[tuple[str, ...], bool]] = []
    defs: dict[str, list] = {}  # a symbol may be defined in several sections (rt_tw_buf)
    refs: list[tuple[str, tuple, int]] = []
    for n, raw in enumerate(lines, 1):
        m = COND.match(raw)
        if m:
            kind, rest = m.group(1), m.group(2)
            if kind == "IF":
                stack.append((tuple(parse_cond(rest)), True))
            elif kind == "ELSE":
                atoms, pos = stack.pop()
                stack.append((atoms, not pos))
            else:
                stack.pop()
            continue
        code = raw.split(";", 1)[0]
        if not code.strip():
            continue
        guard = tuple(stack)
        lm = LABEL.match(code) or EQU.match(code)
        if lm:
            defs.setdefault(lm.group(1), []).append(guard)
            code = code[lm.end():]
        parts = code.split(None, 1)
        if len(parts) == 2 and not re.fullmatch(r"(?i)(db|dw|defb|defw|defs|defm|ds|equ|org|include)", parts[0]):
            operands = re.sub(r"'[^']*'|\"[^\"]*\"", "", parts[1])
            for w in WORD.findall(operands):
                refs.append((w, guard, n))
        elif len(parts) == 2:
            operands = re.sub(r"'[^']*'|\"[^\"]*\"", "", parts[1])
            for w in WORD.findall(operands):
                refs.append((w, guard, n))
    return defs, refs


def holds(guard, true: set[str]) -> bool:
    for atoms, pos in guard:
        any_on = any(a in true for a in atoms)
        if any_on != pos:
            return False
    return True


def closure(true: set[str]) -> set[str]:
    out = set(true)
    changed = True
    while changed:
        changed = False
        for a in list(out):
            for b in IMPLIES.get(a, ()):
                if b not in out:
                    out.add(b)
                    changed = True
    return out


def counterexample(ref_guard, def_guards):
    """A switch set under which the reference is assembled but none of the definitions."""
    names = sorted({a for g in (ref_guard, *def_guards) for atoms, _ in g for a in atoms})
    if len(names) > 22:
        raise ValueError(f"too many switches to search: {names}")
    for bits in itertools.product((False, True), repeat=len(names)):
        chosen = {n for n, b in zip(names, bits) if b}
        world = closure(chosen)
        if holds(ref_guard, world) and not any(holds(g, world) for g in def_guards):
            return sorted(chosen)
    return None


def findings():
    lines = RUNTIME.read_text(encoding="utf-8").splitlines()
    defs, refs = scan(lines)
    seen = {}
    for sym, guard, n in refs:
        if sym not in defs or any(not g for g in defs[sym]):
            continue  # not a runtime symbol, or always assembled
        key = (sym, guard)
        if key in seen:
            continue
        ce = counterexample(guard, defs[sym])
        seen[key] = ce
        if ce is not None:
            yield sym, n, ce, defs[sym]


def show(guards):
    return " or ".join(_show(g) for g in guards)


def _show(guard):
    return " and ".join(("" if pos else "not ") + "(" + " or ".join(atoms) + ")" for atoms, pos in guard) or "always"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)
    found = list(findings())
    for sym, n, ce, dg in found:
        print(f"runtime line {n}: {sym} is defined only when {show(dg)}; "
              f"assembled without it when the program sets {', '.join('PB_' + c for c in ce) or 'nothing'}")
    print(f"rtdeps: {len(found)} finding(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
