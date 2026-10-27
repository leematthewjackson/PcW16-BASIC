"""M8 selective inclusion: drop the unreachable parts of the REAL library.

The REAL library (the runtime's ``IF PB_REAL`` sections, about 4.4 KB) used
to be assembled whole into every program that used REAL at all. This pass
keeps only the code and data a program can reach.

1. Each ``IF PB_REAL`` section (no nested conditionals; checked; M14: the
   switches in INNER are first resolved to the branch the program selects) is cut into
   *chunks*. A chunk ends after an instruction control cannot fall through
   (``ret``, unconditional ``jp`` / ``jr``, ``reti``/``retn``), or at a
   data directive followed by a label. A new label therefore starts a chunk
   only where no instruction can run into it.
2. Roots are the identifiers used anywhere outside these sections: in the
   generated program and in the rest of the runtime.
3. A chunk is kept if a root or a kept chunk names one of its labels
   (textually: ``call x``, ``jp z,x``, ``ld hl,x+5``, ``dw x`` all count).

A mistake here cannot pass silently: a removed label that is still
referenced makes Pasmo fail the build. Programs without REAL are untouched:
their PB_REAL sections are not assembled anyway, so their bytes do not
change. ``equ`` lines are always kept.
"""
from __future__ import annotations

import re

SECTION_START = "    IF PB_REAL"
_LABEL = re.compile(r"^([A-Za-z_]\w*):")
_IDENT = re.compile(r"[A-Za-z_]\w*")
_FALLS_NOWHERE = re.compile(r"^(ret|reti|retn|halt)$|^(jp|jr)\s+[^,]+$", re.I)
_DATA = re.compile(r"^(db|dw|defs|defb|defw|defm|ds)\b", re.I)
#: M14: switches that choose between variants inside the REAL sections
INNER = ("RSTICKY",)


def _resolve(lines: list[str], name: str, on: bool) -> list[str]:
    """*lines* with each ``IF PB_<name>`` / ``ELSE`` / ``ENDIF`` (not nested)
    replaced by the branch *on* selects."""
    out: list[str] = []
    state = None
    for line in lines:
        if line.split(";", 1)[0].rstrip() == f"    IF PB_{name}":
            state = "if"
            continue
        if state and re.match(r"\s+ELSE\b", line):
            state = "else"
            continue
        if state and re.match(r"\s+ENDIF\b", line):
            state = None
            continue
        if (state == "if" and not on) or (state == "else" and on):
            continue
        out.append(line)
    return out


def _code(line: str) -> str:
    """The instruction part of *line*: label and comment removed."""
    line = line.split(";", 1)[0]
    m = _LABEL.match(line)
    if m:
        line = line[m.end():]
    return line.strip()


def _strip_strings(text: str) -> str:
    return re.sub(r'"[^"]*"|\'[^\']*\'', "", text)


def _first_content(lines: list[str], i: int) -> str:
    """The first instruction or directive at or after line *i*."""
    for line in lines[i:]:
        code = _code(line)
        if code:
            return code
    return ""


def _chunks(lines: list[str]) -> list[list[str]]:
    """Split at a label that no instruction can fall into. A run of data
    labels is never split: code may reach one datum from another by address
    arithmetic (rt_freduce reads "high + 5" for the low constant), which no
    textual analysis can see; only a code label after data starts a chunk."""
    chunks: list[list[str]] = [[]]
    ended, after_data = True, False  # nothing falls into the first label
    for i, line in enumerate(lines):
        label = _LABEL.match(line)
        if label and chunks[-1]:
            starts_data = bool(_DATA.match(_first_content(lines, i)))
            if (ended and not after_data) or (after_data and not starts_data):
                chunks.append([])
        chunks[-1].append(line)
        code = _code(line)
        if code:
            after_data = bool(_DATA.match(code))
            ended = bool(_FALLS_NOWHERE.match(code)) or after_data
    return chunks


def prune_real(program_asm: str, runtime_text: str) -> str:
    """*runtime_text* with the unreachable REAL chunks removed."""
    if not re.search(r"^PB_REAL equ 1\s*$", program_asm, re.M):
        return runtime_text
    lines = runtime_text.split("\n")
    for name in INNER:
        lines = _resolve(lines, name, bool(re.search(rf"^PB_{name} equ 1\s*$", program_asm, re.M)))
    sections: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if lines[i].rstrip() == SECTION_START:
            j = i + 1
            while not re.match(r"\s+ENDIF\b", lines[j]):
                if re.match(r"\s+(IF|ELSE)\b", lines[j]):
                    raise AssertionError(f"nested conditional in a PB_REAL section at runtime line {j + 1}")
                j += 1
            sections.append((i + 1, j))
            i = j
        i += 1
    chunk_lists = [_chunks(lines[a:b]) for a, b in sections]
    all_chunks = [c for cl in chunk_lists for c in cl]
    defined = [{m.group(1).lower() for ln in c if (m := _LABEL.match(ln))} for c in all_chunks]
    refs = [{t.lower() for ln in c for t in _IDENT.findall(_strip_strings(_code(ln)))} for c in all_chunks]
    keep_always = [any(re.match(r"^\w+\s+equ\b", ln, re.I) for ln in c) for c in all_chunks]
    inside = set()
    for a, b in sections:
        inside.update(range(a, b))
    outside = "\n".join(ln for k, ln in enumerate(lines) if k not in inside)
    roots = {t.lower() for t in _IDENT.findall(_strip_strings(program_asm + "\n" + outside))}
    kept = [False] * len(all_chunks)
    work = [k for k, d in enumerate(defined) if (d & roots) or keep_always[k] or not d]
    while work:
        k = work.pop()
        if kept[k]:
            continue
        kept[k] = True
        for n, d in enumerate(defined):
            if not kept[n] and d & refs[k]:
                work.append(n)
    out: list[str] = []
    pos = 0
    n = 0
    for (a, b), cl in zip(sections, chunk_lists):
        out.extend(lines[pos:a])
        for chunk in cl:
            if kept[n]:
                out.extend(chunk)
            else:
                first = next(m.group(1) for ln in chunk if (m := _LABEL.match(ln)))
                out.append(f"; (M8 selective inclusion: {first} and its chunk not reachable, left out)")
            n += 1
        pos = b
    out.extend(lines[pos:])
    return "\n".join(out)
