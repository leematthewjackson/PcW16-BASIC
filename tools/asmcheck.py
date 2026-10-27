"""Static validation of Z80 assembly — TESTING-STRATEGY.md tier 3.

``asmcheck`` lints compiler-emitted assembly *before* Pasmo runs, so a
structural regression is caught by a readable Python check instead of an
assembler diagnostic. It is importable (``check_sources`` / ``check_source`` /
``check_files``) and runnable as a CLI::

    python3 tools/asmcheck.py FILE.asm [MORE.asm ...]

prints ``FILE: OK`` or ``FILE: N finding(s)`` per file (followed by the
findings) and exits 0 when every file is clean, 1 otherwise.

Rules implemented (TESTING-STRATEGY.md, tier-3 table):

- A1 — every label is defined exactly once; every ``jp`` (plain and
  ``z/nz/c/nc/p/m/pe/po``), ``jr`` (plain and ``z/nz/c/nc``), ``call`` and
  ``djnz`` target exists. Targets are resolved against the union of all labels
  defined in the sources passed to one call, so a program file can be checked
  together with ``runtime/runtime.z80.asm`` (or one combined build ``.asm``).
  Expression targets (``jp label+1``) are flagged as unsupported; expressions
  in *data* operands (``ld de,msgdef_3_end-msgdef_3``) are ignored.
- A2 — program files contain exactly one ``org 4000h`` and one ``defs 100h``
  (the ``.PRG`` container, ARCHITECTURE.md D7); the runtime appendix must not
  set an origin of its own — it is concatenated *after* the program text
  (ARCHITECTURE.md D2). ``runtime.z80.asm`` files are exempt from the
  exactly-one requirement.
- A4 — outside runtime content, no ``call 003Bh`` (any spelling: ``003Bh``,
  ``#003B``, ``03Bh``, ``3Bh``) and no ``ld a,<n>`` where ``<n>`` is an OS
  function number: generated code must go through the ``rt_*`` wrappers
  (ARCHITECTURE.md D2; numbers from ``OSCALLS.INC.txt``). The check is by
  numeric value, so ``ld a,76`` and its hex disguise ``ld a,4Ch`` both count.
- A5 — runtime-only lint, per routine (label-to-label span): no read of
  ``ix``/``iy`` anywhere after a ``call 003Bh`` (Rosanne corruption is
  per-call; ``os_alert`` is documented to clobber IX/IY — ARCHITECTURE.md D6,
  finding F4), and any routine that invokes ``os_get_event`` (fn 2) must test
  the Z flag (``jp z``/``jp nz``/``jr z``/``jr nz``) before the next
  ``call``/``ret`` — the F3 event-loop regression guard (R-EVT). The M2
  runtime has no event routine, so this passes vacuously; it bites in M3.
- A6 (partial) — every ``defs`` directive carries a label (on its own line or
  the same line). LIMITATION: full address-overlap checking (storage vs
  tables vs definitions) needs a symbol map; this text-only tool does not
  assemble, so only unlabelled storage is flagged. (Pasmo 0.5.3 does write a
  symbol table as its optional third argument; tests/memguard.py uses it for
  the M2.1 runtime memory-boundary checks.) The container's zero prefix
  (``defs 100h`` immediately after the ``org 4000h`` line) is exempt: it is a
  fixed part of the ``.PRG`` container (D7), not addressable storage.
- A7 — no ``$`` in label positions or mangled symbols: ``mangle()`` maps a
  trailing ``$`` to ``_S`` and doubles ``_`` (``NOTE$`` → ``NOTE_S``,
  injective since M2.1), so a raw ``$`` means
  the POC's whole-file ``re.sub`` post-pass leaked back (ARCHITECTURE.md D8).

- A8 (M11 corrective) — an ``equ`` may not name a label or symbol defined
  later in its file. Pasmo 0.5.3 gives such an ``equ`` the later symbol's
  first-pass value (0) in code assembled before the ``equ``, while its
  symbol table shows the final value: TEXTWIDTH's block once assembled as
  ``ld de,0008h`` this way (found by tests/memguard.py).

Runtime content is recognised (a) by file name (``runtime.z80.asm``) or
(b) inside a combined build ``.asm`` by a ``runtime.z80.asm`` banner comment
or the first ``rt_*`` label definition at column 0, whichever comes first;
everything from there to EOF is linted as runtime. This keeps A4 honest on
the real build artefact, whose runtime appendix legitimately contains
``call 003Bh``.

Standard library only; deliberately no Z80 emulation (TESTING-STRATEGY.md:
a simulation is not a test tier).
"""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

RUNTIME_NAME = "runtime.z80.asm"

# Rosanne OS function numbers (OSCALLS.INC.txt). Outside the runtime these
# may only ever be loaded by runtime/runtime.z80.asm itself (ARCHITECTURE.md
# D2); generated code calls rt_* wrappers instead.
OS_FUNCTIONS = frozenset(
    {2, 4, 23, 66, 67, 68, 69, 70, 72, 73, 76, 77, 82, 127, 135, 144, 145, 146, 147}
)

ORG_VALUE = 0x4000  # .PRG load address (ARCHITECTURE.md D7)
PREFIX_VALUE = 0x100  # 256-byte zero prefix (ARCHITECTURE.md D7/F8)
OS_TRAP = 0x3B  # Rosanne call gate, call #003B with fn in A (ROSAN283.DOC)
# Event functions: OSCALLS.INC.txt under CONSTOS.Z80 'RSSET 1' numbers
# os_get_event 1 and os_wait_event 2 (M3a correction: earlier versions called
# fn 2 os_get_event). Both return "Z if no matching event pending ... IX & AF
# corrupt" / "NZ ... IX = 16-bit address of 12-byte Event record"
# (ROSAN283.DOC; os_wait_event "can't be Z", tested anyway).
EVENT_FUNCTIONS = {1: "os_get_event", 2: "os_wait_event"}

# Instructions whose addressed operand is a jump/call target (A1), mapped to
# the condition codes each accepts before the target operand.
_JUMP_CONDITIONS = {
    "jp": {"z", "nz", "c", "nc", "p", "m", "pe", "po"},
    "jr": {"z", "nz", "c", "nc"},
    "call": {"z", "nz", "c", "nc", "p", "m", "pe", "po"},
    "djnz": set(),
}

_LABEL_DEF = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_EXPRESSION_TARGET = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*[-+*/]")
# ix/iy *read* (ROSAN283 per-call corruption; os_alert clobbers IX,IY).
_IX_IY_READ = re.compile(r"\b(i[xy]\b|\(i[xy]\)|i[xy]\+)", re.IGNORECASE)
# A banner comment marking where the runtime appendix begins in a combined
# build .asm, e.g. "; ---- runtime/runtime.z80.asm ----".
_RUNTIME_BANNER = re.compile(r"^\s*;[\s\-=*]*runtime\.z80\.asm[\s\-=*]*$", re.IGNORECASE)
# var_/sub_ tokens as emitted by mangle(); a '$' inside one is an A7 finding.
_MANGLED_TOKEN = re.compile(r"\b(?:var|sub)_[A-Za-z0-9_$]+")
# Anything label-like at column 0 (looser than _LABEL_DEF: also matches names
# containing '$', which _LABEL_DEF rejects but A7 must still flag).
_COLUMN0_LABELISH = re.compile(r"^([^:\s]+):")


@dataclass(frozen=True)
class Finding:
    """One asmcheck finding: the rule id, where, and a readable message."""

    rule: str
    file: str
    line: int | None
    message: str

    def __str__(self) -> str:
        where = f"{self.file}:{self.line}" if self.line is not None else self.file
        return f"[{self.rule}] {where}: {self.message}"


@dataclass
class Line:
    """One parsed assembly line (blank/comment-only lines are dropped)."""

    file: str
    number: int  # 1-based
    text: str  # comment-stripped, right-stripped
    label: str | None  # column-0 label defined here, if any
    mnemonic: str | None  # lowercased first token of the instruction part
    operand: str  # remainder of the instruction part after the mnemonic
    runtime: bool  # belongs to runtime content (appendix/runtime file)


def _strip_comment(line: str) -> str:
    """Remove a ``;`` comment, respecting double-quoted strings."""
    in_string = False
    for index, char in enumerate(line):
        if char == '"':
            in_string = not in_string
        elif char == ";" and not in_string:
            return line[:index]
    return line


def _parse_number(token: str) -> int | None:
    """Parse a Pasmo numeric literal: ``4000h``, ``#4000``, ``0x4000`` or
    plain decimal. Returns None for anything else."""
    text = token.strip().lower()
    if not text:
        return None
    if text.startswith("#"):
        text, base = text[1:], 16
    elif text.startswith("0x"):
        base = 16
    elif text.endswith("h"):
        text, base = text[:-1], 16
    else:
        base = 10
    try:
        return int(text, base)
    except ValueError:
        return None


def _parse_source(name: str, text: str) -> list[Line]:
    """Split *text* into parsed lines and mark runtime content.

    Runtime content is the whole file when *name* is ``runtime.z80.asm``;
    otherwise everything from the first runtime banner comment or ``rt_*``
    label definition (the appended runtime appendix) to EOF.
    """
    runtime_file = Path(name).name == RUNTIME_NAME
    split_at: int | None = None
    lines: list[Line] = []
    for number, raw in enumerate(text.splitlines(), 1):
        if split_at is None and not runtime_file and _RUNTIME_BANNER.match(raw):
            split_at = number
        clean = _strip_comment(raw).rstrip()
        if not clean.strip():
            continue
        label = None
        rest = clean
        if raw[0] not in " \t":
            match = _LABEL_DEF.match(clean)
            if match:
                label = match.group(1)
                rest = match.group(2).strip()
                if split_at is None and not runtime_file and label.lower().startswith("rt_"):
                    split_at = number
        mnemonic = operand = None
        if rest:
            parts = rest.split(None, 1)
            mnemonic = parts[0].lower()
            operand = parts[1].strip() if len(parts) > 1 else ""
        lines.append(Line(name, number, clean, label, mnemonic, operand, False))
    if runtime_file:
        for line in lines:
            line.runtime = True
    elif split_at is not None:
        for line in lines:
            if line.number >= split_at:
                line.runtime = True
    return lines


def _jump_target(line: Line) -> tuple[str, str]:
    """Classify the target operand of a jump/call line.

    Returns ("id", token) for a plain label reference, ("expr", token) for an
    expression target (unsupported; A1 finding) and ("none", token) for
    everything else (numeric targets, indirection like ``jp (hl)`` — outside
    A1's assigned scope; A4 covers the numeric trap call).
    """
    if not line.operand:
        return ("none", "")
    ops = [op.strip() for op in line.operand.split(",")]
    index = 0
    if line.mnemonic != "djnz" and ops[0].lower() in _JUMP_CONDITIONS[line.mnemonic]:
        index = 1
    if index >= len(ops):
        return ("none", "")
    token = ops[index]
    if _IDENTIFIER.match(token):
        return ("id", token)
    if _EXPRESSION_TARGET.match(token):
        return ("expr", token)
    return ("none", token)


def _ld_a_value(line: Line) -> int | None:
    """If *line* is ``ld a,<n>``, return the numeric value of ``<n>``."""
    if line.mnemonic != "ld":
        return None
    ops = [op.strip() for op in (line.operand or "").split(",")]
    if len(ops) == 2 and ops[0].lower() == "a":
        return _parse_number(ops[1])
    return None


def _is_os_trap_call(line: Line) -> bool:
    return line.mnemonic == "call" and _parse_number((line.operand or "").strip()) == OS_TRAP


def _check_labels(parsed: list[tuple[str, list[Line]]], findings: list[Finding],
                  imported: set[str] = frozenset()) -> None:
    """A1: unique label definitions; defined jump/call targets. *imported*
    (M9 code banks) are names a bank takes from the resident block as
    ``equ``: valid targets, not definitions."""
    defined: dict[str, tuple[str, int]] = {}
    references: list[tuple[str, int, str]] = []
    for name, lines in parsed:
        for line in lines:
            if line.label:
                if line.label in defined:
                    first_file, first_line = defined[line.label]
                    findings.append(
                        Finding(
                            "A1",
                            name,
                            line.number,
                            f"label '{line.label}' is defined more than once "
                            f"(first defined at {first_file}:{first_line})",
                        )
                    )
                else:
                    defined[line.label] = (name, line.number)
            if line.mnemonic in _JUMP_CONDITIONS:
                kind, token = _jump_target(line)
                if kind == "id":
                    references.append((name, line.number, token))
                elif kind == "expr":
                    findings.append(
                        Finding(
                            "A1",
                            name,
                            line.number,
                            f"unsupported expression jump target '{token}'; "
                            "jumps must name a plain label",
                        )
                    )
    for name, number, token in references:
        if token not in defined and token not in imported:
            findings.append(
                Finding("A1", name, number, f"jump/call target '{token}' is not defined")
            )


BANK_HEADER = "; ---- code bank "  # M9: pbas/codebanks.py writes this first


def _check_bank_container(name: str, lines: list[Line]) -> list[Finding]:
    """M9 A2 for a code bank: exactly one ``org 8000h`` (the bank runs at
    #8000), no zero prefix."""
    orgs = [line for line in lines if line.mnemonic == "org"]
    if len(orgs) != 1 or _parse_number((orgs[0].operand or "").strip()) != 0x8000:
        return [Finding("A2", name, orgs[0].number if orgs else None,
                        "a code bank has exactly one 'org 8000h' (pbas/codebanks.py)")]
    return []


def _check_container(name: str, lines: list[Line]) -> list[Finding]:
    """A2: one ``org 4000h`` + one ``defs 100h`` per program file; the
    runtime appendix carries neither."""
    findings: list[Finding] = []
    runtime_file = Path(name).name == RUNTIME_NAME
    org_count = 0
    prefix_count = 0
    for line in lines:
        if line.mnemonic == "org":
            if line.runtime:
                findings.append(
                    Finding(
                        "A2",
                        name,
                        line.number,
                        "runtime appendix must not set an origin; the single "
                        "'org 4000h' lives in the program container (ARCHITECTURE.md D2)",
                    )
                )
            elif _parse_number((line.operand or "").strip()) != ORG_VALUE:
                findings.append(
                    Finding(
                        "A2",
                        name,
                        line.number,
                        "'org' value must be 4000h (.PRG container, ARCHITECTURE.md D7)",
                    )
                )
            else:
                org_count += 1
        # The prefix is an unlabelled 'defs 100h'; a labelled 256-byte data
        # area (e.g. an M6 Phase 2 array, var_X: defs 256) is not one.
        if line.mnemonic == "defs" and line.label is None:
            value = _parse_number((line.operand or "").split(",", 1)[0].strip())
            if value == PREFIX_VALUE:
                prefix_count += 1
                if line.runtime:
                    findings.append(
                        Finding(
                            "A2",
                            name,
                            line.number,
                            "'defs 100h' zero prefix belongs to the program "
                            "container, not the runtime appendix (D7)",
                        )
                    )
    if not runtime_file:
        if org_count == 0:
            findings.append(
                Finding("A2", name, None, "missing 'org 4000h' (.PRG container, ARCHITECTURE.md D7)")
            )
        elif org_count > 1:
            findings.append(
                Finding("A2", name, None, f"expected exactly one 'org 4000h', found {org_count}")
            )
        if prefix_count == 0:
            findings.append(
                Finding(
                    "A2",
                    name,
                    None,
                    "missing 'defs 100h' zero prefix (.PRG container, ARCHITECTURE.md D7)",
                )
            )
        elif prefix_count > 1:
            findings.append(
                Finding(
                    "A2", name, None, f"expected exactly one 'defs 100h', found {prefix_count}"
                )
            )
    return findings


def _check_os_coupling(name: str, lines: list[Line]) -> list[Finding]:
    """A4: no direct OS access outside runtime content (ARCHITECTURE.md D2)."""
    findings: list[Finding] = []
    for line in lines:
        if line.runtime:
            continue
        if _is_os_trap_call(line):
            findings.append(
                Finding(
                    "A4",
                    name,
                    line.number,
                    "generated code calls 003Bh directly; call an rt_* wrapper "
                    "from runtime/runtime.z80.asm instead (ARCHITECTURE.md D2)",
                )
            )
        value = _ld_a_value(line)
        if value in OS_FUNCTIONS:
            findings.append(
                Finding(
                    "A4",
                    name,
                    line.number,
                    f"'ld a,{value}' loads OS function number {value} outside the "
                    "runtime; generated code must go through rt_* wrappers "
                    "(ARCHITECTURE.md D2, OSCALLS.INC.txt)",
                )
            )
    return findings


def _tests_z_flag(lines: Sequence[Line]) -> bool:
    """True if *lines* contain a Z-flag conditional branch (jp/jr z/nz)
    before the next call/ret boundary (A5, os_get_event contract)."""
    for line in lines:
        mnemonic = line.mnemonic or ""
        if mnemonic == "call" or mnemonic.startswith("ret"):
            return False
        if mnemonic in ("jp", "jr"):
            cond = (line.operand or "").split(",", 1)[0].strip().lower()
            if cond in ("z", "nz"):
                return True
    return False


def _check_routine(name: str, span: list[Line]) -> list[Finding]:
    """A5 lint over one routine (label-to-label span of runtime content).

    * An event call (fn 1/2) must be followed by a Z-flag test before the
      next call/ret (no-event contract; R-EVT).
    * After an OS call, IX may be read only if that most recent call was an
      event function, whose documented output IX is (the event record);
      after any other OS call IX is corrupt. IY is never documented as an
      output, so it is never read after an OS call (F4, D6).
    """
    findings: list[Finding] = []
    a_value: int | None = None
    last_call: int | None = None  # function number of the latest OS call
    for index, line in enumerate(span):
        if _is_os_trap_call(line):
            last_call = a_value if a_value is not None else -1
            # The Z test must be the very next instruction: any flag-setting
            # instruction in between (e.g. 'bit 5,h') would replace the
            # no-event Z flag with an unrelated one (M3a tightening).
            if last_call in EVENT_FUNCTIONS and not _tests_z_flag(span[index + 1 : index + 2]):
                findings.append(
                    Finding(
                        "A5",
                        name,
                        line.number,
                        f"{EVENT_FUNCTIONS[last_call]} (fn {last_call}) called "
                        "without a Z-flag test ('jp z'/'jp nz'/'jr z'/'jr nz') "
                        "as the next instruction; per ROSAN283.DOC "
                        "'os_get_event' Z means no event pending and IX is "
                        "then corrupt (R-EVT, TESTING-STRATEGY.md A5)",
                    )
                )
            continue
        match = _IX_IY_READ.search(line.text)
        if match and last_call is not None:
            reg = match.group(0).lower()
            if "iy" in reg or last_call not in EVENT_FUNCTIONS:
                findings.append(
                    Finding(
                        "A5",
                        name,
                        line.number,
                        f"read of '{match.group(0)}' after 'call 003Bh' in the same "
                        "routine; Rosanne corrupts IX/IY across OS calls, except "
                        "that an event call (fn 1/2) returns IX = event record "
                        "(ROSAN283.DOC; ARCHITECTURE.md D6)",
                    )
                )
        if line.mnemonic == "xor" and (line.operand or "").strip().lower() == "a":
            a_value = 0
        elif line.mnemonic == "ld":
            a_value = _ld_a_value(line)
    return findings


def _check_runtime_lint(name: str, lines: list[Line]) -> list[Finding]:
    """A5: split runtime content into routines and lint each one."""
    findings: list[Finding] = []
    span: list[Line] = []
    for line in lines:
        if not line.runtime:
            continue
        if line.label and span:
            findings.extend(_check_routine(name, span))
            span = []
        span.append(line)
    if span:
        findings.extend(_check_routine(name, span))
    return findings


def _check_storage(name: str, lines: list[Line]) -> list[Finding]:
    """A6 (partial): every 'defs' carries a label, except the container's
    zero prefix (org 4000h immediately followed by defs 100h — fixed .PRG
    header bytes, not addressable storage)."""
    findings: list[Finding] = []
    previous: Line | None = None
    for line in lines:
        if line.mnemonic == "defs":
            value = _parse_number((line.operand or "").split(",", 1)[0].strip())
            container_prefix = (
                value == PREFIX_VALUE
                and previous is not None
                and previous.mnemonic == "org"
                and _parse_number((previous.operand or "").strip()) == ORG_VALUE
            )
            labelled = line.label is not None or (
                previous is not None
                and previous.label is not None
                and previous.mnemonic is None
            )
            if not container_prefix and not labelled:
                findings.append(
                    Finding(
                        "A6",
                        name,
                        line.number,
                        "unlabelled 'defs' storage; give it a label so storage "
                        "can be named and checked (TESTING-STRATEGY.md A6)",
                    )
                )
        previous = line
    return findings


def _check_mangling(name: str, lines: list[Line]) -> list[Finding]:
    """A7: no '$' in label positions or var_/sub_ tokens (mangle() maps '$'
    to '_S' — a raw '$' means the POC re.sub post-pass leaked back, D8)."""
    findings: list[Finding] = []
    for line in lines:
        head = line.text
        if head and head[0] not in " \t":
            match = _COLUMN0_LABELISH.match(head)
            if match and "$" in match.group(1):
                findings.append(
                    Finding(
                        "A7",
                        name,
                        line.number,
                        f"label '{match.group(1)}' contains '$'; mangle() must map "
                        "'$' to '_S' (ARCHITECTURE.md D8)",
                    )
                )
        for match in _MANGLED_TOKEN.finditer(head):
            if "$" in match.group(0):
                findings.append(
                    Finding(
                        "A7",
                        name,
                        line.number,
                        f"mangled symbol '{match.group(0)}' contains a raw '$'; "
                        "mangle() must map '$' to '_S' (ARCHITECTURE.md D8)",
                    )
                )
    return findings


def _check_equ_order(name: str, text: str) -> list[Finding]:
    """A8: no ``equ`` refers to a symbol defined further down the file."""
    lines = text.split("\n")
    defined: dict[str, int] = {}
    for number, raw in enumerate(lines, 1):
        m = re.match(r"^(\w+):|^(\w+)\s+equ\s", raw, re.I)
        if m:
            defined.setdefault((m.group(1) or m.group(2)).lower(), number)
    findings = []
    for number, raw in enumerate(lines, 1):
        m = re.match(r"^(\w+)\s+equ\s+([^;]*)", raw, re.I)
        if not m:
            continue
        for token in re.findall(r"[A-Za-z_]\w*", m.group(2)):
            later = defined.get(token.lower())
            if later is not None and later > number:
                findings.append(Finding("A8", name, number,
                                        f"'{m.group(1)}' equ names '{token}', defined later (line {later}): "
                                        "Pasmo uses its first-pass value in code before the equ"))
    return findings


def check_sources(sources: Sequence[tuple[str, str]]) -> list[Finding]:
    """Lint every (name, text) source, returning findings for all of them.

    Label definitions and jump/call targets (A1) are pooled across *sources*,
    so a program can be checked against the runtime (or one combined build
    ``.asm`` can be checked on its own); the remaining rules are per-file.
    """
    parsed = [(name, _parse_source(name, text)) for name, text in sources]
    findings: list[Finding] = []
    banks = {name for name, text in sources if text.startswith(BANK_HEADER)}
    imported = {m.group(1) for name, text in sources if name in banks
                for m in re.finditer(r"^(\w+) equ ", text, re.M)}
    _check_labels(parsed, findings, imported)
    for name, text in sources:
        findings.extend(_check_equ_order(name, text))
    for name, lines in parsed:
        if name in banks:
            findings.extend(_check_bank_container(name, lines))
        else:
            findings.extend(_check_container(name, lines))
        findings.extend(_check_os_coupling(name, lines))
        findings.extend(_check_runtime_lint(name, lines))
        findings.extend(_check_storage(name, lines))
        findings.extend(_check_mangling(name, lines))
    order = {name: index for index, (name, _) in enumerate(parsed)}
    findings.sort(key=lambda f: (order.get(f.file, len(order)), f.line or 0, f.rule))
    return findings


def check_source(name: str, text: str) -> list[Finding]:
    """Lint a single in-memory assembly source."""
    return check_sources([(name, text)])


def check_files(paths: Sequence[str | Path]) -> list[Finding]:
    """Lint assembly files; a file named ``runtime.z80.asm`` is linted as the
    runtime appendix (A4/A5 exemptions apply to it)."""
    sources = []
    for path in paths:
        path = Path(path)
        sources.append((str(path), path.read_text(encoding="utf-8")))
    return check_sources(sources)


def main(argv: list[str] | None = None) -> int:
    """CLI: lint every FILE.asm and exit 0 (clean) or 1 (findings/errors)."""
    parser = argparse.ArgumentParser(
        prog="asmcheck.py",
        description="Static validation of PcW16 BASIC Z80 assembly "
        "(TESTING-STRATEGY.md tier 3: rules A1, A2, A4, A5, A6-partial, A7).",
    )
    parser.add_argument(
        "files",
        nargs="+",
        metavar="FILE.asm",
        help="assembly file(s) to lint: the .asm tools/build.py writes already "
        "contains the runtime, so give it alone; give runtime/runtime.z80.asm as well "
        "only for compiler output without the runtime (M14: corrected advice)",
    )
    args = parser.parse_args(argv)
    sources = []
    for file_name in args.files:
        try:
            text = Path(file_name).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"{file_name}: cannot read: {exc}", file=sys.stderr)
            return 1
        sources.append((file_name, text))
    findings = check_sources(sources)
    by_file: dict[str, list[Finding]] = {}
    for finding in findings:
        by_file.setdefault(finding.file, []).append(finding)
    for file_name in args.files:
        file_findings = by_file.get(file_name, [])
        if not file_findings:
            print(f"{file_name}: OK")
            continue
        noun = "finding" if len(file_findings) == 1 else "findings"
        print(f"{file_name}: {len(file_findings)} {noun}")
        for finding in file_findings:
            print(f"  {finding}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
