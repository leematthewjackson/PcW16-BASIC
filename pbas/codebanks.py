"""M9 Stage A: programs whose code does not fit one 16K block (code banks).

A Rosanne loader gives a program exactly one 16K block, mapped at
#4000-#7FFF ("os_run_program" reads at most #4000 bytes; M8 research §3).
Code beyond it has to be loaded by the program itself into RAM it asks the
OS for, and mapped at #8000-#BFFF when it runs (ROSAN283 'Memory Layout':
"Switching in further blocks of your app is up to you (you can do what you
want with the 2nd, 3rd and 4th quarters of memory)"; "RAM can be got from
the OS in 16k lumps"). The two contracts this rests on, self-loaded code at
#8000 running and an OS call from it returning, passed in XAnne with the
hand-written CODEPROBE (RUNTIME-RESULTS "M8 final acceptance").

The file this module builds::

    +0       the resident block, padded to exactly 16384 bytes: the zero
             prefix, start:, the main line, one 8-byte stub per procedure,
             all data, the runtime (with its loader and far call)
    +16384   code bank 1, padded to a multiple of 512 bytes
    ...      code bank 2 ... n, the same way

Each code bank is assembled on its own at ``org 8000h``::

    8000h    'P','B',k          magic and the bank's number (checked at load)
    8003h    jp sub_A           one jump per procedure in the bank, in
    8006h    jp sub_B           source order
    ...      the procedures' code, exactly as the generator emitted it

and imports every resident symbol as an ``equ`` from Pasmo's symbol file.
A call to a procedure in the same bank is a plain ``call``; any other call
(from the main line, from the runtime's event dispatch, from another bank)
reaches the resident stub ``sub_X: ld c,k / ld hl,8000h+3+3i / jp
rt_farcall``, which maps bank k, calls the entry, and maps back the block
that was there before. Parameters, locals and results are static variables
in the resident block (M7), so nothing passes in registers.

Placement is deterministic: every procedure goes to a bank; banks are
filled first-fit in decreasing order of code size (ties in source order),
then each bank lists its procedures in source order. Nothing the OS or the
runtime reads through a pointer is ever placed in a bank: the bank text is
checked to contain instructions only (no ``db``/``dw``/``defs``).

The programmer never sees a block number: the loader asks for the blocks
with os_get_mem and keeps their numbers in ``rt_code_list``.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .errors import SourceError

#: Where a code bank runs: quarter 2 (bios_setmem2, ROSAN283 BIOS #16).
BANK_ORIGIN = 0x8000
BANK_BLOCK = 0x4000
#: os_read_file may fill to the end of a 512-byte disc block (CODEPROBE's
#: precaution, M8 research §6); a bank's padded length stays at least 512
#: bytes short of the block end, so no read can run past its block.
FILE_ALIGN = 512
BANK_LIMIT = BANK_BLOCK - FILE_ALIGN  # 15872 bytes of padded bank
BANK_MAGIC = 3  # 'P', 'B', bank number
ENTRY_SIZE = 3  # jp nn
STUB_SIZE = 8  # ld c,n / ld hl,nn / jp nn
#: rt_code_list holds at most this many blocks (runtime IF PB_CODEBANKS).
MAX_CODE_BANKS = 16
MIN_BANK_LIMIT = 64
RESIDENT_SIZE = 0x4000
MODES = ("auto", "always", "never")

_DATA = re.compile(r"^\s*(?:[A-Za-z_]\w*:)?\s*(db|dw|defs|defb|defw|defm|ds|org|incbin)\b", re.I)
_SYM = re.compile(r"^(\S+)\s+EQU\s+0?([0-9A-Fa-f]+)H\s*$")


@dataclass
class CodeBank:
    """One code bank: its number (1..n), procedures and padded image."""

    number: int
    procedures: list[str] = field(default_factory=list)  # symbols, source order
    code_size: int = 0  # bytes of procedure code (without magic/table)
    image: bytes = b""  # padded to FILE_ALIGN

    @property
    def used(self) -> int:
        return BANK_MAGIC + ENTRY_SIZE * len(self.procedures) + self.code_size


@dataclass
class BankedLayout:
    """What the code-bank build produced (also written as the .map file)."""

    resident_size: int  # bytes before padding to 16384
    banks: list[CodeBank]
    sizes: dict[str, int]  # procedure symbol -> code bytes
    total_size: int  # the whole .PRG file
    runtime_sections: tuple = ()  # M11: runtime sections moved to the last bank
    runtime_entries: tuple = ()  # M11: their veneered labels, in jump-table order

    def map_text(self) -> str:
        lines = ["; PcW16 BASIC code-bank map (generated; pbas/codebanks.py)",
                 f"resident {self.resident_size} of {RESIDENT_SIZE} bytes "
                 f"(padded to {RESIDENT_SIZE})"]
        for bank in self.banks:
            if not bank.procedures and self.runtime_sections:
                lines.append(f"bank {bank.number}: {bank.used} bytes used, {len(bank.image)} in the "
                             f"file, runtime sections {' '.join(self.runtime_sections)}, "
                             f"{len(self.runtime_entries)} entries")
                continue
            lines.append(f"bank {bank.number}: {bank.used} bytes used, "
                         f"{len(bank.image)} in the file, {len(bank.procedures)} procedure(s)")
            for i, sym in enumerate(bank.procedures):
                lines.append(f"    entry {i:2d} at {BANK_ORIGIN + BANK_MAGIC + ENTRY_SIZE * i:04X}h  "
                             f"sub_{sym}  {self.sizes[sym]} bytes")
        lines.append(f"file {self.total_size} bytes")
        return "\n".join(lines) + "\n"


def bank_entry(slot: int) -> int:
    """Address of the jump-table entry *slot* (0-based) in any bank."""
    return BANK_ORIGIN + BANK_MAGIC + ENTRY_SIZE * slot


def _pasmo(asm_path: Path, out_path: Path, sym_path: Path | None = None) -> None:
    args = ["pasmo", "--bin", str(asm_path), str(out_path)]
    if sym_path is not None:
        args.append(str(sym_path))
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-3:]) or "(no stderr)"
        raise SourceError(1, 1, f"pasmo failed on {asm_path.name} (exit {proc.returncode}): {tail}")


def read_symbols(sym_path: Path) -> dict[str, int]:
    """Pasmo's symbol file (``name EQU 0nnnnH`` lines) as a dict."""
    table: dict[str, int] = {}
    for line in Path(sym_path).read_text(encoding="utf-8").splitlines():
        m = _SYM.match(line.strip())
        if m:
            table[m.group(1)] = int(m.group(2), 16)
    return table


def _imports(symbols: dict[str, int], exclude: set[str]) -> list[str]:
    return [f"{name} equ {value:05X}h" for name, value in sorted(symbols.items())
            if name not in exclude]


def check_bank_text(symbol: str, lines: list[str], line_no: int) -> None:
    """A procedure moved to a bank must hold instructions only."""
    for text in lines:
        code = text.split(";", 1)[0]
        if _DATA.match(code):
            raise SourceError(line_no, 1,
                              f"internal: procedure sub_{symbol} contains data "
                              f"({text.strip()!r}); it cannot be placed in a code bank")


def pack(sizes: list[tuple[str, int, int]], limit: int = BANK_LIMIT) -> list[CodeBank]:
    """First-fit decreasing over (symbol, size, source line), deterministic.

    *limit* is the most a bank may use (default and maximum BANK_LIMIT; a
    smaller value spreads a small program over several banks, for tests and
    probes of cross-bank calls). A procedure too big for one bank is a
    positioned compile error.
    """
    if not MIN_BANK_LIMIT <= limit <= BANK_LIMIT:
        raise SourceError(1, 1, f"code bank limit must be {MIN_BANK_LIMIT}..{BANK_LIMIT} bytes")
    room = limit - BANK_MAGIC
    order = sorted(enumerate(sizes), key=lambda item: (-item[1][1], item[0]))
    banks: list[CodeBank] = []
    placed: dict[str, int] = {}
    for _, (sym, size, line) in order:
        need = size + ENTRY_SIZE
        if need > room:
            raise SourceError(line, 1,
                              f"procedure is {size} bytes of code, over the "
                              f"{room - ENTRY_SIZE}-byte limit of one code bank; "
                              "split it into smaller SUBs or FUNCTIONs")
        for bank in banks:
            if bank.used + need <= limit:
                break
        else:
            bank = CodeBank(len(banks) + 1)
            banks.append(bank)
        bank.procedures.append(sym)
        bank.code_size += size
        placed[sym] = bank.number
    if len(banks) > MAX_CODE_BANKS:
        raise SourceError(1, 1, f"the program needs {len(banks)} code banks; at most "
                          f"{MAX_CODE_BANKS} are supported")
    source_rank = {sym: i for i, (sym, _, _) in enumerate(sizes)}
    for bank in banks:
        bank.procedures.sort(key=source_rank.__getitem__)
    return banks


def _resident_text(parts, stub_targets: dict[str, tuple[int, int]],
                   table: list[tuple[int, int]], runtime_text: str, marker: str,
                   rt_bank: int | None = None) -> str:
    lines = parts.lines
    spans = parts.spans
    head = lines[:spans[0][1]]
    data = lines[spans[-1][2]:]
    out: list[str] = ["PB_CODEBANKS equ 1", f"PB_CODE_N equ {len(table)}"]
    if rt_bank is not None:  # M11: runtime code in bank rt_bank (pbas/rtbank.py)
        out += ["PB_RTBANK equ 1"]
    seen_start = False
    for text in head:
        out.append(text)
        if text == "start:" and not seen_start:
            seen_start = True
            # The loader runs first: before the BANKED data blocks are
            # allocated (rt_bank_init), so code blocks always precede them.
            out.append("    call rt_code_load")
    if not seen_start:
        raise SourceError(1, 1, "internal: no start: label in the program text")
    out.append("; ---- M9 code-bank stubs: one far call per procedure ----")
    for sym, _, _, _ in spans:
        bank, slot = stub_targets[sym]
        # C, not A, carries the bank: generated text never loads a constant
        # into A (asmcheck A4: no OS function numbers outside the runtime)
        out += [f"sub_{sym}:", f"    ld c,{bank}", f"    ld hl,{bank_entry(slot):04X}h",
                "    jp rt_farcall"]
    out += data
    text = "\n".join(out) + "\n" + parts.tail
    words = ",".join(f"{length},{total}" for length, total in table)
    text += f"rt_code_tab: dw {words}\n"
    return text + "\n" + marker + "\n" + runtime_text


def _bank_text(bank: CodeBank, parts, symbols: dict[str, int]) -> str:
    bodies = {sym: (first, end) for sym, first, end, _ in parts.spans}
    out = [f"; ---- code bank {bank.number} (pbas/codebanks.py) ----",
           f"    org {BANK_ORIGIN:04X}h", f"    db 'P','B',{bank.number}"]
    out += [f"    jp sub_{sym}" for sym in bank.procedures]
    for sym in bank.procedures:
        first, end = bodies[sym]
        out += parts.lines[first:end]
    own = {f"sub_{sym}" for sym in bank.procedures}
    out.append("; ---- resident symbols ----")
    out += _imports(symbols, own)
    return "\n".join(out) + "\n"


def _rt_bank_equ(split, number) -> str:
    """M11: the runtime bank's number for the veneers' ``db PB_RT_BANK``."""
    return "" if split is None else f"PB_RT_BANK equ {number}\n"


def _checksum(data: bytes) -> int:
    return sum(data) & 0xFFFF


def build_banked(parts, runtime_text: str, marker: str, asm_path: Path,
                 prg_path: Path, limit: int = BANK_LIMIT,
                 runtime_sections: tuple = ()) -> BankedLayout:
    """Assemble *parts* (pbas.statements.GeneratedProgram) as a code-banked
    program and write the .PRG. Intermediate files go next to *asm_path*:
    ``<stem>.bankN.asm`` for every bank, ``<stem>.measure.asm`` and
    ``<stem>.map``.

    M11: *runtime_sections* names runtime sections whose code goes to one more
    bank after the procedures' banks (pbas/rtbank.py); empty = as in M9/M10."""
    asm_path = Path(asm_path)
    prg_path = Path(prg_path)
    spans = parts.spans
    if not spans:
        raise SourceError(1, 1, "the program has no SUB or FUNCTION to place in a "
                          "code bank; only procedures can be banked")
    stem = asm_path.with_suffix("")
    work = asm_path.parent
    sym_path = stem.with_suffix(".sym")
    split = None
    if runtime_sections:
        from . import rtbank
        values = rtbank.switches(parts.text)
        values.update(PB_CODEBANKS=1, PB_RTBANK=1)
        split = rtbank.split(runtime_text, values, runtime_sections, parts.text, "PB_RT_BANK")
        if split.moved_labels:
            runtime_text = split.resident
        else:
            split = None  # nothing to move: no runtime bank (as without the option)

    # 1. A provisional resident block: every stub's size is fixed, so its
    #    symbols are final even though its constants are not.
    provisional = {sym: (0, 0) for sym, _, _, _ in spans}
    table0 = [(0, 0)] * (len(spans) + (1 if split else 0))  # at most one bank per procedure
    resident0 = _resident_text(parts, provisional, table0, runtime_text + _rt_bank_equ(split, 0),
                               marker, 0 if split else None)
    # The table's length must not change between passes: fix it at the
    # final bank count by measuring and packing first.
    measure_res = work / (stem.name + ".res0.asm")
    measure_res.write_text(resident0, encoding="utf-8")
    _pasmo(measure_res, stem.with_suffix(".res0.bin"), sym_path)
    symbols0 = read_symbols(sym_path)

    # 2. Measure every procedure on its own at org 8000h.
    out = ["; ---- procedure sizes (pbas/codebanks.py) ----"]
    for i, (sym, first, end, line) in enumerate(spans):
        check_bank_text(sym, parts.lines[first:end], line)
        out.append(f"    org {BANK_ORIGIN:04X}h")
        out += parts.lines[first:end]
        out.append(f"pbm_end_{i}:")
    out += _imports(symbols0, {f"sub_{sym}" for sym, _, _, _ in spans})
    measure = work / (stem.name + ".measure.asm")
    measure.write_text("\n".join(out) + "\n", encoding="utf-8")
    _pasmo(measure, stem.with_suffix(".measure.bin"), stem.with_suffix(".measure.sym"))
    msyms = read_symbols(stem.with_suffix(".measure.sym"))
    sizes = [(sym, msyms[f"pbm_end_{i}"] - BANK_ORIGIN, line)
             for i, (sym, _, _, line) in enumerate(spans)]

    # 3. Pack, then assemble the real resident block (same symbols).
    banks = pack(sizes, limit)
    targets = {}
    for bank in banks:
        for slot, sym in enumerate(bank.procedures):
            targets[sym] = (bank.number, slot)
    rt_number = len(banks) + 1 if split else None
    rt_tail = _rt_bank_equ(split, rt_number)
    placeholder = [(0, 0)] * (len(banks) + (1 if split else 0))
    resident1 = _resident_text(parts, targets, placeholder, runtime_text + rt_tail, marker, rt_number)
    asm_path.write_text(resident1, encoding="utf-8")
    _pasmo(asm_path, prg_path, sym_path)
    symbols = read_symbols(sym_path)

    # 4. Every bank against the resident symbols.
    size_of = {sym: size for sym, size, _ in sizes}
    for bank in banks:
        bank_asm = work / f"{stem.name}.bank{bank.number}.asm"
        bank_bin = work / f"{stem.name}.bank{bank.number}.bin"
        bank_asm.write_text(_bank_text(bank, parts, symbols), encoding="utf-8")
        _pasmo(bank_asm, bank_bin)
        raw = bank_bin.read_bytes()
        if len(raw) != bank.used:
            raise SourceError(1, 1, f"internal: bank {bank.number} assembled to {len(raw)} "
                              f"bytes, measured {bank.used}")
        padded = raw + bytes(-len(raw) % FILE_ALIGN)
        if len(padded) > BANK_LIMIT:
            raise SourceError(1, 1, f"internal: bank {bank.number} is {len(padded)} bytes")
        bank.image = padded

    # 4b. M11: the runtime bank.
    all_banks = list(banks)
    if split:
        from . import rtbank
        rt_asm = work / f"{stem.name}.bank{rt_number}.asm"
        rt_bin = work / f"{stem.name}.bank{rt_number}.bin"
        rt_asm.write_text(rtbank.bank_text(split, rt_number, symbols), encoding="utf-8")
        _pasmo(rt_asm, rt_bin)
        raw = rt_bin.read_bytes()
        padded = raw + bytes(-len(raw) % FILE_ALIGN)
        if len(padded) > BANK_LIMIT:
            raise SourceError(1, 1, f"the runtime bank is {len(padded)} bytes, over the "
                              f"{BANK_LIMIT}-byte limit of one code bank; move fewer runtime sections")
        rt_bank = CodeBank(rt_number, [], len(raw) - BANK_MAGIC, padded)  # used = the whole bank
        all_banks.append(rt_bank)
        rt_bin.unlink()

    # 5. The final resident block with the banks' lengths and checksums.
    table = [(len(b.image), _checksum(b.image)) for b in all_banks]
    resident = _resident_text(parts, targets, table, runtime_text + rt_tail, marker, rt_number)
    asm_path.write_text(resident, encoding="utf-8")
    _pasmo(asm_path, prg_path, sym_path)
    if read_symbols(sym_path) != symbols:
        raise SourceError(1, 1, "internal: the resident symbols moved between passes")
    image = prg_path.read_bytes()
    if len(image) > RESIDENT_SIZE:
        hint = ("" if runtime_sections else
                "; or move runtime code to a code bank of its own (tools/build.py "
                "--runtime-banks all; pcw16basic build does this by itself)")
        raise SourceError(
            1, 1,
            f"the resident part is {len(image)} bytes, {len(image) - RESIDENT_SIZE} over the "
            f"{RESIDENT_SIZE}-byte first block even with every procedure in a code bank: "
            "the main line, the data and the runtime must fit #4000-#7FFF (move work "
            f"into SUBs, or large arrays to BANKED{hint}); tools/memreport.py shows "
            "where the bytes go")
    whole = image + bytes(RESIDENT_SIZE - len(image)) + b"".join(b.image for b in all_banks)
    prg_path.write_bytes(whole)
    layout = BankedLayout(len(image), all_banks, size_of, len(whole),
                          tuple(runtime_sections) if split else (),
                          tuple(split.entries) if split else ())
    stem.with_suffix(".map").write_text(layout.map_text(), encoding="utf-8")
    for leftover in (".res0.asm", ".res0.bin", ".measure.asm", ".measure.bin", ".measure.sym"):
        p = work / (stem.name + leftover)
        if p.exists():
            p.unlink()
    for bank in banks:
        p = work / f"{stem.name}.bank{bank.number}.bin"
        if p.exists():
            p.unlink()
    return layout


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
