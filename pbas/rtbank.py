"""M11 Stage B: runtime code in a code bank ("runtime bank").

Up to M10 every runtime routine stayed in the program's resident 16K block
(#4000-#7FFF), and only SUB/FUNCTION code went to code banks (M9,
pbas/codebanks.py). With ``runtime_sections`` the code of chosen runtime
sections (``IF PB_x`` blocks of runtime/runtime.z80.asm) is moved to one more
code bank, loaded and checked by the M9 loader like any other bank. Its data
(``db``/``dw``/``defs`` and ``equ``) stays resident, because the OS and the
rest of the runtime read it by address.

A resident routine, a procedure bank or the generated program reaches a
moved routine through a resident veneer with the routine's own name::

    rt_x:  call rt_rbc      ; runtime/runtime.z80.asm, IF DEFINED PB_RTBANK
           db k             ; the runtime bank's number
           dw 8003h+3*i     ; its entry in the bank's jump table

``rt_rbc`` maps the runtime bank at #8000 and jumps to the entry with AF, BC,
DE, HL, IX and IY exactly as the caller left them; when the routine returns,
it maps back the block that was at #8000 and returns with the routine's
registers and flags (ROSAN283 BIOS #16 bios_setmem2 and #1A bios_getmem2:
"all flags & regs preserved" / "all flags & other regs preserved"). Calls
inside the bank are plain calls.

Why this is safe, and what this module checks before it moves anything:

* Every runtime routine that maps another block at #8000 (TEXT, the code-bank
  far call) maps back what was there before it returns, so code in a bank may
  call it; this is what banked procedures have done since M9 (XAnne: MDEDIT,
  MDEDIT II). A section is movable only if none of its code runs while a
  data block is mapped and none of its routines is handed a pointer into the
  #8000 window: ``MOVABLE`` lists the sections audited for that
  (docs/M11-ARCHITECTURE.md §2).
* The ``IF`` conditions are evaluated here (they use only PB_ switches,
  numbers, ``+``, ``>=`` and ``DEFINED``; anything else is refused), so the
  moved and kept lines are exactly those Pasmo would assemble.
* No code may fall through between the bank and the resident block: the last
  moved instruction before resident code (and the reverse) must be an
  unconditional jump or return.
* Moved code may not use the address of moved code as data (``ld hl,label``),
  since that address is only valid while the bank is mapped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import SourceError

#: Sections audited as movable (M11 architecture §2). Their code never runs
#: with a TEXT or other data block mapped at #8000 and receives no pointer
#: into the #8000 window.
MOVABLE = ("DB", "CANVAS", "CVLINE", "CVCELL", "FILES", "FIO", "FNAME", "NUMBERS", "MENUS",
           "LIST", "CHOICE", "SLIDER",
           # M12: the BIOS blitter maps a bitmap's block at #8000 / #C000 and
           # maps back what was there before it returns [static: PCW045.SYS
           # #1C03 / #1C1E], like an OS call (docs/M12-ARCHITECTURE.md)
           "BITMAP", "BMPFILE", "POINT",
           # M12 printing: OS calls with addresses in the resident block
           "PAGE",
           # M13: parts and masks: the blitter (as BITMAP) and os_copy_24bit
           # into the bottom quarter
           "BMPPART")
#: The default set for ``runtime_sections="auto"``.
DEFAULT = MOVABLE
#: M14: switches that only select a variant of code inside a section: their
#: lines belong to (and move with) that section.
PART_OF = {"FSAFE": "DB"}

_IF = re.compile(r"^\s+IF\s+(.*?)\s*(;.*)?$")
_ELSE = re.compile(r"^\s+ELSE\b")
_ENDIF = re.compile(r"^\s+ENDIF\b")
_LABEL = re.compile(r"^([A-Za-z_]\w*):(.*)$")
_EQU = re.compile(r"^([A-Za-z_]\w*)\s+equ\b", re.I)
_DATA = re.compile(r"^\s*(db|dw|defs|defb|defw|defm|ds|incbin)\b", re.I)
_DIRECTIVE = re.compile(r"^\s*(org|end|macro|endm|include|if|else|endif)\b", re.I)
_UNCONDITIONAL = re.compile(r"^\s*(ret|reti|retn|jp\s+[^,]+|jr\s+[^,]+|halt)\s*$", re.I)
_WORD = re.compile(r"\b([A-Za-z_]\w*)\b")
_BRANCH = re.compile(r"^\s*(call|jp|jr|djnz)\b", re.I)
_JUMP = re.compile(r"^\s*(call|jp|jr|djnz)\s+(?:\w+\s*,\s*)?([A-Za-z_]\w*)\s*$", re.I)
#: Resident routines that never return (an error report, the program's end):
#: moved code may jump to them.
NORETURN = frozenset({"rt_err_msg", "rt_exit", "rt_err_string_overflow"})


def previous_of(content: list, ln) -> "Line | None":
    """The content line just before *ln* (labels included)."""
    i = content.index(ln)
    return content[i - 1] if i else None


def switches(text: str) -> dict[str, int]:
    """``PB_x equ n`` lines of *text* (the generated program part)."""
    return {m.group(1): int(m.group(2)) for m in re.finditer(r"^(PB_\w+)\s+equ\s+(\d+)\s*$", text, re.M)}


def evaluate(expr: str, values: dict[str, int]) -> int:
    """An IF condition of the runtime: PB_ names, numbers, ``+``, ``>=``
    and ``DEFINED name``; anything else is an internal error."""
    tokens = re.findall(r"DEFINED\s+\w+|PB_\w+|\d+|>=|\+|\S", expr.strip())

    def term(tok: str) -> int:
        if tok.upper().startswith("DEFINED"):
            return 1 if tok.split()[1] in values else 0
        if tok.isdigit():
            return int(tok)
        if tok in values:
            return values[tok]
        raise SourceError(1, 1, f"internal: runtime condition {expr!r} names {tok!r}, "
                          "which the runtime bank builder does not know")

    if not tokens:
        raise SourceError(1, 1, "internal: empty runtime condition")
    total, i = term(tokens[0]), 1
    while i < len(tokens) and tokens[i] == "+":
        total += term(tokens[i + 1])
        i += 2
    if i < len(tokens) and tokens[i] == ">=":
        total = 1 if total >= term(tokens[i + 1]) else 0
        i += 2
    if i != len(tokens):
        raise SourceError(1, 1, f"internal: runtime condition {expr!r} is not supported here")
    return total


@dataclass
class Line:
    index: int
    text: str
    active: bool
    section: str  # innermost IF's single PB_ name, or "" (outside / compound)
    kind: str = ""  # code / data / equ / label / directive / blank
    enclosing: tuple = ()  # the names of every enclosing IF
    owner: str = ""  # the section of the label this line falls under
    label: str | None = None
    body: str = ""


def classify(runtime: str, values: dict[str, int]) -> list[Line]:
    """Each runtime line with whether Pasmo assembles it and its section."""
    out: list[Line] = []
    stack: list[tuple[bool, bool, str]] = []  # (this branch active, parent active, section)
    owner = ""
    for i, text in enumerate(runtime.split("\n")):
        active = all(s[0] for s in stack)
        section = stack[-1][2] if stack else ""
        enclosing = tuple(s[2] for s in stack if s[2])
        m = _IF.match(text)
        if m:
            names = re.findall(r"PB_(\w+)", m.group(1))
            name = names[0] if len(names) == 1 and "+" not in m.group(1) and "DEFINED" not in m.group(1) else ""
            name = PART_OF.get(name, name)
            cond = bool(evaluate(m.group(1), values)) if active else False
            out.append(Line(i, text, active, section, "directive"))
            stack.append((cond, active, name))
            continue
        if _ELSE.match(text):
            cond, parent, name = stack.pop()
            stack.append((not cond if parent else False, parent, name))
            out.append(Line(i, text, all(s[1] for s in stack[-1:]), section, "directive"))
            continue
        if _ENDIF.match(text):
            stack.pop()
            out.append(Line(i, text, active, section, "directive"))
            continue
        line = Line(i, text, active, section, enclosing=enclosing)
        code = text.split(";", 1)[0].rstrip()
        m = _LABEL.match(code)
        if m:
            line.label = m.group(1)
            code = m.group(2)
            if active:
                owner = section
        line.owner = owner
        line.body = code.strip()
        if not line.body:
            line.kind = "label" if line.label else "blank"
        elif _EQU.match(text.split(";", 1)[0].strip()):
            line.kind = "equ"
        elif _DATA.match(code):
            line.kind = "data"
        elif _DIRECTIVE.match(code):
            line.kind = "directive"
        else:
            line.kind = "code"
        out.append(line)
    if stack:
        raise SourceError(1, 1, "internal: unbalanced IF in the runtime")
    return out


@dataclass
class Split:
    resident: str  # the runtime text without the moved code, plus the veneers
    bank_lines: list[str]  # the moved code, in order
    entries: list[str]  # labels with a veneer, in jump-table order
    moved_bytes_hint: int = 0
    moved_labels: set[str] = field(default_factory=set)


def split(runtime: str, values: dict[str, int], sections, other_text: str, bank: int) -> Split:
    """Move the code of *sections* out of *runtime* (see the module notes).
    *other_text* is everything else that is assembled (the program part and
    every procedure bank), searched for references that need a veneer."""
    sections = tuple(sections)
    unknown = [s for s in sections if s not in MOVABLE]
    if unknown:
        raise SourceError(1, 1, f"runtime section(s) {', '.join(unknown)} cannot be moved to a "
                          f"code bank; movable: {', '.join(MOVABLE)}")
    lines = classify(runtime, values)
    content = [ln for ln in lines if ln.active and ln.kind in ("code", "data", "label")]
    moving = set(sections)

    # where each active label and line goes
    def placed(ln: Line) -> str:
        # a code line moves with its routine: the label it falls under was
        # defined in a moved section, and the line is inside that section
        moved = ln.kind == "code" and ln.owner in moving and ln.owner in ln.enclosing
        return "bank" if moved else "resident"

    # labels used as code: branch targets, and jump-table words
    targets: set[str] = set()
    for ln in lines:
        if ln.active and ln.body and (_BRANCH.match(ln.body) or re.match(r"(?i)dw\b", ln.body)):
            targets.update(_WORD.findall(ln.body))
    targets.update(_WORD.findall(other_text))  # the program calls runtime routines
    referenced: set[str] = set(_WORD.findall(other_text))
    for ln in lines:
        if ln.active and ln.body:
            referenced.update(_WORD.findall(ln.body))

    where: dict[int, str] = {}
    pending: list[Line] = []
    last: Line | None = None  # the previous code or data line
    for ln in content:
        if ln.kind == "label":
            pending.append(ln)
            continue
        dest = placed(ln)
        for lab in pending:
            # a label right after data that nothing branches to marks the
            # data's end (``x_end: ... ld bc,x_end-x``): it stays with it
            # (a label nothing uses goes with the code after it)
            after_data = last is not None and last.kind == "data"
            data_end = after_data and lab.label not in targets and lab.label in referenced
            where[lab.index] = "resident" if data_end else dest
        if dest == "bank" and (last is None or where[last.index] != "bank"):
            if not any(where[lab.index] == "bank" for lab in pending):
                raise SourceError(1, 1, f"internal: moved runtime code at line {ln.index + 1} "
                                  "has no label of its own to be entered by")
        pending = []
        where[ln.index] = dest
        last = ln
    for lab in pending:
        where[lab.index] = "resident"

    # Enter by call, leave by return (M11: the independent core found code
    # that a resident loop reached by jp and that jumped back into the loop,
    # leaving the bank mapped and rt_rbc's frame on the stack). A run of
    # moved code ("block") stays resident if a label in it is the target of
    # a jump from outside the bank, or if it jumps to resident code other
    # than a routine that is called elsewhere (a tail call, which returns
    # through rt_rbc) or one that never returns. Repeated until stable.
    calls: set[str] = set()
    jumps_in: dict[str, set[int]] = {}
    for ln in lines:
        if ln.active and ln.kind == "code":
            m = _JUMP.match(ln.body)
            if m and m.group(1).lower() == "call":
                calls.add(m.group(2))
    calls.update(re.findall(r"(?im)^\s*call\s+(?:\w+\s*,\s*)?(\w+)", other_text))
    program_jumps = set(re.findall(r"(?im)^\s*j[pr]\s+(?:\w+\s*,\s*)?(\w+)", other_text))
    while True:
        # a block ends where control cannot fall through: after a return or
        # an unconditional jump (so a block is about one routine)
        blocks: list[list[Line]] = []
        for ln in content:
            if where[ln.index] == "bank":
                before = previous_of(content, ln)
                if (not blocks or blocks[-1][-1] is not before
                        or (before.kind == "code" and _UNCONDITIONAL.match(before.body))):
                    blocks.append([])
                blocks[-1].append(ln)
        moved_now = {ln.label for blk in blocks for ln in blk if ln.label}
        targets_out: set[str] = set(program_jumps)
        for ln in content:
            if ln.kind == "code" and where[ln.index] != "bank":
                m = _JUMP.match(ln.body)
                if m and m.group(1).lower() != "call":
                    targets_out.add(m.group(2))
        pinned = []
        for blk in blocks:
            labels = {ln.label for ln in blk if ln.label}
            bad = bool(labels & targets_out)
            for ln in blk:
                m = _JUMP.match(ln.body) if ln.kind == "code" else None
                if m and m.group(1).lower() != "call" and m.group(2) not in moved_now:
                    if m.group(2) not in calls and m.group(2) not in NORETURN:
                        bad = True
            if bad:
                pinned.append(blk)
        if not pinned:
            break
        for blk in pinned:
            for ln in blk:
                where[ln.index] = "resident"

    # fall-through across the boundary
    previous: Line | None = None
    for ln in content:
        if ln.kind == "label":
            continue
        if previous is not None and where[previous.index] != where[ln.index] and previous.kind == "code":
            if not _UNCONDITIONAL.match(previous.body):
                raise SourceError(1, 1, f"internal: runtime line {previous.index + 1} "
                                  f"({previous.text.strip()!r}) would fall through into "
                                  f"{'the runtime bank' if where[ln.index] == 'bank' else 'resident code'}")
        previous = ln

    moved_labels = {ln.label for ln in content if ln.label and where[ln.index] == "bank"}
    bank_lines: list[str] = []
    resident_lines: list[str] = []
    moved_index = {ln.index for ln in content if where[ln.index] == "bank"}
    for ln in lines:
        if ln.index in moved_index:
            bank_lines.append(ln.text)
            if ln.kind == "code":
                for word in _WORD.findall(ln.body):
                    if word in moved_labels and not _BRANCH.match(ln.body):
                        raise SourceError(1, 1, f"internal: runtime line {ln.index + 1} uses the "
                                          f"address of {word} as data; it cannot be moved")
            resident_lines.append("")  # keep the line count; nothing assembled here
        elif not ln.active and ln.kind not in ("directive", "blank"):
            # not assembled for this program (a false IF): left out, so that
            # tools/asmcheck.py sees no reference to a label now in the bank
            resident_lines.append("")
        else:
            resident_lines.append(ln.text)

    # which moved labels are referenced from outside the bank
    outside = other_text + "\n" + "\n".join(
        ln.text.split(";", 1)[0] for ln in lines if ln.active and ln.index not in moved_index)
    used = set(_WORD.findall(outside))
    entries = [ln.label for ln in content if ln.label in moved_labels and ln.label in used]
    veneers = ["; ---- M11 runtime-bank veneers (pbas/rtbank.py) ----"]
    for i, name in enumerate(entries):
        veneers += [f"{name}:", "    call rt_rbc", f"    db {bank}", f"    dw {0x8003 + 3 * i:04X}h"]
    return Split("\n".join(resident_lines) + "\n" + "\n".join(veneers) + "\n",
                 bank_lines, entries, moved_labels=moved_labels)


def bank_text(result: Split, bank: int, symbols: dict[str, int]) -> str:
    """The runtime bank's assembly: magic, jump table, the moved code, then
    the resident symbols it uses (all but its own labels)."""
    out = [f"; ---- code bank {bank}: runtime sections (pbas/rtbank.py) ----", "    org 8000h",
           f"    db 'P','B',{bank}"]
    out += [f"    jp {name}" for name in result.entries]
    out += result.bank_lines
    out.append("; ---- resident symbols ----")
    own = {name.lower() for name in result.moved_labels}
    out += [f"{name} equ {value:05X}h" for name, value in sorted(symbols.items())
            if name.lower() not in own]
    return "\n".join(out) + "\n"
