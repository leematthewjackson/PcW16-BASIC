"""Build the M15a probe M15PRB.PRG (docs/M15A-PROBE.md).

    python3 xanne/m15prb_build.py [OUTDIR]      (default: artifacts/m15a)

M15PRB is probe scaffolding, not a compiled program: xanne/m15prb.pbas is
compiled as usual (no code banks, no runtime bank), then its assembly is
changed in three ways, and assembled with Pasmo:
  1. the body of each placeholder SUB NatX becomes "jp nat_x";
  2. xanne/m15native.asm is put before the first SUB (after the main line's
     final jump to the window);
  3. the event loop's om_exit dispatch ("cp 5 / jp z,rt_exit") goes to
     nat_omexit, which runs SUB OnExit first; r4: each OS message's id is
     counted first (nat_msg), and a menu choice that is not one of the
     program's goes to nat_ddm_other (counted; passed to os_process_event
     when the probe's switch is on) instead of being dropped; r5: with the
     probe's other switch on, Tasks menu title 0, entry 0 goes to nat_omexit.
The compiler, the runtime and every other program are unchanged.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent  # xanne/, or developer-tests/ in the public copy
SOURCE = HERE / "m15prb.pbas"
NATIVE = HERE / "m15native.asm"
NATIVES = {"NATDLG": "nat_dlg",
           "NATTYPOLIST": "nat_typo_list", "NATTYPODEF": "nat_typo_def", "NATTYPODRAW": "nat_typo_draw",
           "NATCLIPGET": "nat_clip_get", "NATEVENTS": "nat_events",
           "NATTASKS": "nat_tasks"}
FIRST_JUMP = "    ld hl,gui_windows\n    jp rt_win_start\n\nsub_"
OM_EXIT = "    ld a,(ix+2)\n    cp 5\n    jp z,rt_exit\n"
MENU_MISS = "    ld a,b\n    or a\n    jp z,rt_gui_loop\n    ld a,(rt_menu_t)\n"


def patch(asm: str) -> str:
    for sub, target in NATIVES.items():
        asm, n = re.subn(rf"^sub_{sub}:\n.*?^    ret\n", f"sub_{sub}:\n    jp {target}\n", asm,
                         count=1, flags=re.M | re.S)
        if n != 1:
            raise SystemExit(f"m15prb_build: SUB {sub} not found")
    if asm.count(FIRST_JUMP) != 1:
        raise SystemExit("m15prb_build: the main line's jump to the window not found")
    asm = asm.replace(FIRST_JUMP, FIRST_JUMP[:-4] + NATIVE.read_text(encoding="utf-8") + "\nsub_", 1)
    if asm.count(OM_EXIT) != 1:
        raise SystemExit(f"m15prb_build: {asm.count(OM_EXIT)} om_exit dispatches, 1 expected")
    asm = asm.replace(OM_EXIT, "    ld a,(ix+2)\n    call nat_msg\n    cp 5\n    jp z,nat_omexit\n", 1)
    if asm.count(MENU_MISS) != 1:
        raise SystemExit(f"m15prb_build: {asm.count(MENU_MISS)} menu look-ups, 1 expected")
    return asm.replace(MENU_MISS, MENU_MISS.replace("jp z,rt_gui_loop", "jp z,nat_ddm_other"), 1)


def build(outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        asm, prg = Path(tmp) / "m15prb.asm", Path(tmp) / "plain.prg"
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "build.py"), str(SOURCE), "--asm", str(asm),
                              "--prg", str(prg), "--code-banks", "never"], capture_output=True, text=True)
        if out.returncode != 0:
            raise SystemExit("m15prb_build: m15prb.pbas did not build:\n" + out.stderr + out.stdout)
        patched = ROOT / "build" / "m15prb.asm"  # kept for reading, not an artefact
        patched.parent.mkdir(exist_ok=True)
        patched.write_text(patch(asm.read_text(encoding="utf-8")), encoding="utf-8")
    target = outdir / "M15PRB.PRG"
    out = subprocess.run(["pasmo", "--bin", str(patched), str(target)], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("m15prb_build: pasmo refused the patched assembly:\n" + out.stderr)
    if target.stat().st_size > 16384:  # r5: the image must fit the 16K block at #4000
        size = target.stat().st_size
        target.unlink()
        raise SystemExit(f"m15prb_build: M15PRB.PRG is {size} bytes, over 16384")
    sha = hashlib.sha256(target.read_bytes()).hexdigest()
    (outdir / "MANIFEST.md").write_text(
        "# Artefacts (m15a)\n\n"
        "The M15a XAnne probe (docs/M15A-PROBE.md), built by `python3 xanne/m15prb_build.py`. Probe "
        "scaffolding: not a PcW16 BASIC program and not an accepted build.\n\n"
        "| file | built from | SHA-256 |\n|---|---|---|\n"
        f"| M15PRB.PRG | xanne/m15prb.pbas + xanne/m15native.asm (xanne/m15prb_build.py) | `{sha}` |\n",
        encoding="utf-8")
    return target


if __name__ == "__main__":
    t = build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "artifacts" / "m15a")
    print(f"{t}: {t.stat().st_size} bytes, sha256 {hashlib.sha256(t.read_bytes()).hexdigest()}")
