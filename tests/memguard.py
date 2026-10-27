"""Memory-boundary checking for generated programs (M2.1) — engineering aid only.

Builds a .pbas program with the real pipeline (``pbas.prg.build`` + Pasmo),
asks Pasmo for the symbol table, then runs the image on ``tests/z80sim.py``
with a write observer that enforces:

R1  Every write lands in allocated storage: a BASIC variable cell, a FOR
    limit cell, a runtime ``defs`` object (``runtime/runtime.z80.asm``), or
    the documented stack area below #3FFE (ROSAN283 'Memory Layout': "about
    2k"). Writes to code, the literal pool, static alert definitions,
    ``rt_alert_keys`` or past the image end are violations.
R2  A write into a *string object* (a STRING variable, ``rt_alert_buf``,
    ``rt_cmp_buf1``/``rt_cmp_buf2``) is legal only while the runtime's active
    destination limit ``rt_dst_end`` points into that same object. This is
    what catches one string overrunning into its neighbour, which R1 alone
    cannot see.
R3  After the run, every STRING variable holds a NUL within its capacity.

M4: the file routines' bottom-quarter workspace (``rt_low_path``, 65 bytes)
is allocated storage; ``rt_file_buf`` is a string object (R2), and the
model OS's ``os_read_file`` writes into it go through the same observer.

Like the simulator, this is never runtime or XAnne evidence: it shows that
the *tested* programs, on this CPU model, wrote nothing outside their
allocated destinations. It does not prove that no program can.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import z80sim
from pbas import check_source
from pbas.emit import mangle
from pbas.errors import SourceError
from pbas.prg import build

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime" / "runtime.z80.asm"
STACK_LOW = z80sim.STACK_TOP - 2048
STACK_HIGH = 0x4000
STRING_RUNTIME_OBJECTS = ("rt_alert_buf", "rt_cmp_buf1", "rt_cmp_buf2", "rt_file_buf",
                          "rt_str_tmp3", "rt_str_tmp4", "rt_str_tmp5", "rt_str_tmp6")  # M5a pool
# M4: the file routines' bottom-quarter workspace (runtime "Files": path,
# name, extension at #2100..#2140; ROSAN283 "AP may use #2000...#2FFF").
FILE_WORKSPACE_SIZE = 0x68  # M4: path/name 65 bytes; M7 NAME: new name #2140, extension #2160
MENU_WORKSPACE, MENU_WORKSPACE_SIZE = 0x2400, 2048  # M6 Phase 1


@dataclass
class Region:
    name: str
    start: int
    size: int
    is_string: bool

    def __contains__(self, addr: int) -> bool:
        return self.start <= addr < self.start + self.size


@dataclass
class GuardedRun:
    cpu: z80sim.CPU
    regions: list[Region]
    symbols: dict[str, int]
    violations: list[str] = field(default_factory=list)
    report: object = None  # M9: the pbas.prg BuildReport

    @property
    def alerts(self) -> list[str]:
        return self.cpu.alerts


def _runtime_objects() -> dict[str, int]:
    """``label:`` followed by ``defs N`` in the runtime source -> size N."""
    text = RUNTIME.read_text(encoding="utf-8")
    return {
        m.group(1).lower(): int(m.group(2))
        for m in re.finditer(r"^(\w+):\s*\n\s+defs\s+(\d+)\s*$", text, re.M)
    }


def _symbols(asm: Path, tmp: Path) -> dict[str, int]:
    sym = tmp / "out.sym"
    subprocess.run(
        ["pasmo", "--bin", str(asm), str(tmp / "sym.bin"), str(sym)],
        check=True,
        capture_output=True,
    )
    table = {}
    for line in sym.read_text().splitlines():
        m = re.match(r"(\S+)\s+EQU\s+0*([0-9A-Fa-f]+)H", line)
        if m:
            table[m.group(1).lower()] = int(m.group(2), 16)
    return table


def region_table(regions: list[Region]) -> list:
    """M11: the region holding each address 0..#FFFF (None if none), built once
    instead of searching every region on every write. The first region in
    list order wins, exactly as ``next(r for r in regions if addr in r)``;
    the regions do not change during a run (tests/test_m11_harness.py)."""
    table = [None] * 0x10000
    for region in reversed(regions):
        for addr in range(max(region.start, 0), min(region.start + region.size, 0x10000)):
            table[addr] = region
    return table


def write_observer(run: GuardedRun):
    """The R1/R2 write check for *run* (its regions and symbols): a function
    for ``z80sim.run(on_write=...)`` that appends to ``run.violations``."""
    regions, symbols = run.regions, run.symbols
    dst_end_cell = symbols.get("rt_dst_end")
    code_list = symbols.get("rt_code_list")
    region_at = region_table(regions)

    def on_write(cpu, addr, value):
        if 0x8000 <= addr < 0xC000:
            # M9: the window at #8000 is writable only while one of the
            # program's own data blocks (a TEXT buffer's) is mapped there —
            # never a code bank, never the block found there at start.
            code = set()
            if code_list is not None:
                code = set(cpu.mem[code_list:code_list + 17]) - {0}
            if cpu.q2 in cpu.owned and cpu.q2 not in code:
                return
            run.violations.append(f"R1: write {value:02X}h to {addr:04X}h in the #8000 window "
                                  f"(block {cpu.q2:02X}h mapped)")
            return
        region = region_at[addr]
        if region is None:
            run.violations.append(f"R1: write {value:02X}h to {addr:04X}h outside allocated storage")
            return
        if region.is_string and dst_end_cell is not None:
            dst_end = cpu.mem[dst_end_cell] | (cpu.mem[dst_end_cell + 1] << 8)
            if dst_end not in region and dst_end not in getattr(region, "record", ()):
                # M10: a whole-record copy's destination is the record holding the field
                run.violations.append(
                    f"R2: write {value:02X}h to {addr:04X}h in {region.name} while the "
                    f"active destination ends at {dst_end:04X}h"
                )

    return on_write


def guarded_run(
    source: str,
    string_capacity: int = 64,
    events=None,
    fail_dialog_define: bool = False,
    disk: z80sim.Disk | None = None,
    location=None,
    build_options: dict | None = None,
    path=None,
    **sim_options,
) -> GuardedRun:
    """Build *source*, run it with R1/R2 write checks, then apply R3.

    *events* / *fail_dialog_define* are passed to ``z80sim.run`` (M3a).
    *build_options* go to ``pbas.prg.build`` (M9: ``code_banks``,
    ``code_bank_limit``); a code-banked program is checked the same way,
    with the resident block's symbols (its procedures run from #8000, so a
    write there is a write into code, R1).
    """
    # M10: *path* = the program's own file (its INCLUDEs are read beside it)
    program = check_source(source, string_capacity=string_capacity, path=path)
    with tempfile.TemporaryDirectory(prefix="pbw16-mem-") as tmp_name:
        tmp = Path(tmp_name)
        src, asm, prg = tmp / "t.pbas", tmp / "t.asm", tmp / "t.prg"
        if path is not None and Path(path).read_text(encoding="utf-8") == source:
            src = Path(path)
        elif path is not None:  # M13: a changed copy of a program: build the text given, its
            for entry in Path(path).parent.iterdir():  # INCLUDEs still found beside it
                if entry.name != Path(path).name and not (tmp / entry.name).exists():
                    (tmp / entry.name).symlink_to(entry.resolve())
            src = tmp / Path(path).name
            src.write_text(source, encoding="utf-8")
        else:
            src.write_text(source, encoding="utf-8")
        options = dict(build_options or {})
        # M11: PBAS_TEST_RUNTIME_BANKS=all builds every program that has
        # procedures with its runtime sections in a code bank, so whole
        # behaviour suites run unchanged against runtime-banked builds
        rt = os.environ.get("PBAS_TEST_RUNTIME_BANKS")
        if rt and "runtime_sections" not in options and options.get("code_banks") != "never":
            try:
                report = build(src, asm, prg, string_capacity=string_capacity, location=location,
                               runtime_sections=rt, **options)
            except SourceError as exc:
                if "no SUB or FUNCTION" not in str(exc):
                    raise
                report = build(src, asm, prg, string_capacity=string_capacity, location=location, **options)
        else:
            report = build(src, asm, prg, string_capacity=string_capacity, location=location, **options)
        symbols = _symbols(asm, tmp)
        image = prg.read_bytes()
        # M6 Phase 2: list / drop-down item pointer tables (program data)
        tables = re.findall(r"^(\w*ltab_\d+): defs (\d+)$", asm.read_text(encoding="utf-8"), re.M)
        # M8: the BANKED arrays' read windows and write window (program data)
        tables += re.findall(r"^(cgbank_w\w*): defs (\d+)$", asm.read_text(encoding="utf-8"), re.M)
        # M10: a database's next-identifier cell (program data)
        tables += re.findall(r"^(cgdbid_\w+): defs (\d+)$", asm.read_text(encoding="utf-8"), re.M)
        # M11: the program's runtime switches; with a runtime bank, a routine
        # called only from inside the bank has no resident symbol
        switches = {m.group(1) for m in re.finditer(r"^PB_(\w+) equ ([1-9]\d*)\s*$",
                                                    asm.read_text(encoding="utf-8"), re.M)}

    regions: list[Region] = []
    for name, var in program.variables.items():
        if getattr(var, "banked", False):  # M8: elements live in owned blocks, not here
            continue
        if getattr(var, "alias", None) is not None:  # M10: a field, inside its record's region
            continue
        if var.type == "RECORD":  # M10: each STRING field a string object, then the record
            base = symbols[f"var_{mangle(name)}".lower()]
            count = getattr(var, "length", None) or 1
            for fname, fvar in program.variables.items():
                alias = getattr(fvar, "alias", None)
                if alias is not None and alias[0] == name and fvar.type == "STRING":
                    for e in range(count):
                        field = Region(fname, base + e * var.capacity + alias[1], fvar.capacity, True)
                        field.record = range(base + e * var.capacity, base + (e + 1) * var.capacity)
                        regions.append(field)
            regions.append(Region(name, base, var.capacity * count, False))
            continue
        size = (var.capacity if var.type == "STRING" else 5 if var.type == "REAL"
                else 18 if var.type == "TEXT" else 8 if var.type == "BITMAP"
                else 2)  # M9: a TEXT buffer's record; M12: a BITMAP's
        size *= getattr(var, "length", None) or 1  # M6 Phase 2: arrays
        regions.append(
            Region(name, symbols[f"var_{mangle(name)}".lower()], size, var.type == "STRING")
        )
    for label, addr in symbols.items():
        if label.startswith("cgforlimit_"):
            regions.append(Region(label, addr, 2, False))
    for label, size in tables:
        regions.append(Region(label, symbols[label.lower()], int(size), False))
    for label, size in _runtime_objects().items():
        if label in symbols:  # conditional runtime sections may be absent
            regions.append(Region(label, symbols[label], size, label in STRING_RUNTIME_OBJECTS))
    if "rt_low_path" in symbols:
        regions.append(Region("file workspace", symbols["rt_low_path"], FILE_WORKSPACE_SIZE, False))
    if "rt_menu_init" in symbols or "MENUS" in switches:
        # M6: the menu bar is built in the workspace at #2400-#2BFF of block
        # #80 (runtime "Menus"; ROSAN283 "AP may use #2000...#2FFF").
        regions.append(Region("menu workspace", MENU_WORKSPACE, MENU_WORKSPACE_SIZE, False))
    if "rt_cv_bios" in symbols or "CANVAS" in switches:
        # M9: the BIOS line / rectangle parameter block (runtime "CANVAS":
        # #2200 of block #80, 8 bytes)
        regions.append(Region("BIOS drawing parameters", 0x2200, 8, False))
    if "rt_bmp_blk" in symbols or "BITMAP" in switches:
        # M12: the BIOS bitmap parameters (#2208, 11 bytes) and the capture
        # strip (#2C00..#2FFF) in block #80 (runtime "BITMAPs")
        regions.append(Region("bitmap parameters", 0x2208, 14, False))  # M13: +11..+13 a mask
        regions.append(Region("bitmap strip", 0x2C00, 1024, False))
    if "rt_code_load" in symbols:
        # M9: the loader's copy of the program's file name and extension
        # (runtime "code banks": #2180 and #21C0 of block #80).
        regions.append(Region("code loader workspace", 0x2180, 0x48, False))
    regions.append(Region("stack", STACK_LOW, STACK_HIGH - STACK_LOW, False))

    run = GuardedRun(cpu=None, regions=regions, symbols=symbols)  # type: ignore[arg-type]
    run.report = report
    on_write = write_observer(run)

    try:
        run.cpu = z80sim.run(
            image, on_write=on_write, events=events, fail_dialog_define=fail_dialog_define,
            disk=disk, **sim_options,
        )
    except (z80sim.SimError, z80sim.SimRunaway) as exc:
        run.violations.append(f"run aborted: {type(exc).__name__}: {exc}")
        return run
    for number, text, width, w in run.cpu.label_overflows:
        run.violations.append(
            f"L: label {number} drawn {width} px wide in a {w}-px object: {text!r} "
            "(XAnne showed such text drawn outside the window)"
        )
    for region in regions:
        if region.is_string and region.name in program.variables:
            cap = program.variables[region.name].capacity
            for at in range(region.start, region.start + region.size, cap):  # each element
                if 0 not in run.cpu.mem[at : at + cap]:
                    run.violations.append(f"R3: {region.name} has no NUL within {cap} bytes at {at:04X}h")
    return run


def string_var(run: GuardedRun, name: str) -> str:
    """Current text of STRING variable *name* (up to its NUL)."""
    region = next(r for r in run.regions if r.name == name)
    data = bytes(run.cpu.mem[region.start : region.start + region.size])
    return data.split(b"\0", 1)[0].decode("latin-1")
