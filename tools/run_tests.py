"""Run the test suite in tiers, with test modules in parallel processes (M11 Stage A).

    python3 tools/run_tests.py fast            # quick development check (not acceptance)
    python3 tools/run_tests.py full [-j N]     # every module: milestone verification
    python3 tools/run_tests.py module NAME...  # chosen modules, e.g. test_m11_mdedit3
    python3 tools/run_tests.py list            # the modules and their tiers

Each test module runs in its own Python process (``python3 -m unittest
MODULE`` with PYTHONPATH=.:tests, as a contributor runs it), at most N at a
time (default: the number of CPUs). A module's tests are never split or
skipped, and nothing is cached between modules: every module builds and runs
its own programs, exactly as when it runs alone. The summary lists each
module's result and time, the total of tests run, and the wall-clock time.

"fast" leaves out the modules that drive whole applications for minutes
(SLOW below). It is for quick feedback while working and is NOT enough for
a milestone: run "full" (and tools/accepted-gate.sh) on the final commit.
Exit status: 0 only if every module chosen passed.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Modules that run whole applications through long scripts (measured in
#: docs/M11-TEST-PERFORMANCE.md); everything else is in the fast tier.
SLOW = frozenset({
    "test_m10_mdedit2", "test_m10_mdedit2_view", "test_m10_contacts", "test_m11_mdedit3",
    "test_m11_contacts4", "test_m11_harness", "test_m11_rtbank", "test_m9_editor",
    "test_m9_programs", "test_m10_programs", "test_m8_benchmarks", "test_m7_examples",
    "test_examples_build", "test_m8_prune", "test_m11_acceptance", "test_m11_corrective",
    "test_m12_mdedit4", "test_m12_paint", "test_m12_reporter",  # M12 whole-application sessions
    "test_m13_probe", "test_m13_paint2", "test_m13_designer", "test_m13_jumper", "test_m13_sprited",  # M13 sessions
    "test_m13_install",  # M13: a release staged, built and tested from its copy
    "test_m13_responsive",  # M13: seconds of free-running programs
})


def modules() -> list[str]:
    return sorted(p.stem for p in (ROOT / "tests").glob("test_*.py"))


#: M14: the private development repository (the prototype beside it, the owner's builds
#: in artifacts/). There the tests that need those files must run, never skip.
PRIVATE_CHECKOUT = (ROOT.parent / "POC").is_dir() and (ROOT / "artifacts" / "m13-rt7").is_dir()


def run_module(name: str) -> tuple[str, int, float, str]:
    env = dict(os.environ, PYTHONPATH=f".{os.pathsep}tests")
    if PRIVATE_CHECKOUT:
        env.setdefault("PBAS_REQUIRE_PRIVATE", "1")
    start = time.time()
    proc = subprocess.run([sys.executable, "-m", "unittest", "-v", name], cwd=ROOT, env=env,
                          capture_output=True, text=True)
    elapsed = time.time() - start
    return name, proc.returncode, elapsed, proc.stderr


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tier", choices=("fast", "full", "module", "list"))
    ap.add_argument("names", nargs="*", help="module names for 'module'")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1)
    args = ap.parse_args(argv)
    every = modules()
    unknown = sorted(SLOW - set(every))
    if unknown:  # M14 (X2): a typo in SLOW is still an error here, but not in a copy without them
        print(f"run_tests.py: SLOW names modules that do not exist: {unknown}", file=sys.stderr)
        if PRIVATE_CHECKOUT:
            return 2
    if args.tier == "list":
        for name in every:
            print(f"{'slow' if name in SLOW else 'fast'}  {name}")
        return 0
    if args.tier == "module":
        chosen = [n[:-3] if n.endswith(".py") else n for n in args.names]
        missing = [n for n in chosen if n not in every]
        if missing or not chosen:
            print(f"run_tests.py: no such module(s): {missing or 'none given'}", file=sys.stderr)
            return 2
    elif args.tier == "fast":
        chosen = [n for n in every if n not in SLOW]
    else:
        chosen = every
    # the slow modules first, so they do not start last and stretch the run
    chosen.sort(key=lambda n: (n not in SLOW, n))
    start = time.time()
    results = []
    reasons: dict[str, int] = {}  # M14: every skip is reported, with its reason
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for name, code, elapsed, err in pool.map(run_module, chosen):
            ran = re.findall(r"^Ran (\d+) tests?", err, re.M)
            count = int(ran[-1]) if ran else 0
            skipped = re.findall(r"skipped=(\d+)", err)
            skips = int(skipped[-1]) if skipped else 0
            # unittest prints the reason as a Python string: in double quotes when it holds an apostrophe
            for reason in re.findall(r"\.\.\. skipped (?:'(.*)'|\"(.*)\")$", err, re.M):
                reason = reason[0] or reason[1]
                reasons[reason] = reasons.get(reason, 0) + 1
            status = "ok" if code == 0 else "FAILED"
            results.append((name, status, count, elapsed, skips))
            print(f"{status:6}  {count:4} tests  {elapsed:7.1f} s  {name}"
                  + (f"  ({skips} skipped)" if skips else ""), flush=True)
            if code != 0:
                print(err[-4000:], file=sys.stderr)
    wall = time.time() - start
    failed = [r for r in results if r[1] != "ok"]
    total = sum(r[2] for r in results)
    skipped_total = sum(r[4] for r in results)
    for reason, n in sorted(reasons.items()):
        print(f"skipped {n:3}: {reason}")
    print(f"{args.tier}: {len(results)} modules, {total} tests, {len(failed)} failed, "
          f"{skipped_total} skipped, {wall:.0f} s wall clock with {args.jobs} job(s)"
          + ("" if args.tier == "full" else " — not a milestone verification: run 'full'"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
