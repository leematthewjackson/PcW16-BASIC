"""Sample input files for the M8 benchmarks (owner XAnne tests).

    python3 tools/m8_sample_data.py OUTDIR

writes OUTDIR/SALES.DAT (3000 sales for examples/records_m8.pbas) and
OUTDIR/CONTBOOK.DAT (150 contacts for examples/contacts_m8.pbas). The data
is made up by formula, so the expected results can be computed: the script
prints the summary line records_m8 should show and the first page of names
contacts_m8 should list. CR LF line ends, as the programs write them.
"""
from __future__ import annotations

import sys
from pathlib import Path

REGIONS = ["North", "South", "East", "West", "Central", "Islands", "Harbour"]


def sales(n: int) -> list[tuple[str, int, float]]:
    """The same formula as tests/test_m8_benchmarks.py: distinct amounts."""
    return [(REGIONS[i * 3 % len(REGIONS)], i % 13 + 1, (i * 37 % 1000) / 4 + i / 8192) for i in range(1, n + 1)]


def contacts(n: int) -> list[tuple[str, str, str]]:
    return [(f"Person {i:03}", f"01632 {i:06}", f"person.{i:03}@example.org") for i in range(1, n + 1)]


def text(lines) -> bytes:
    return "".join(f"{x}\r\n" for x in lines).encode("ascii")


def number(x: float) -> str:
    return str(int(x)) if x == int(x) else f"{x:.9g}"


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    rows = sales(3000)
    (out / "SALES.DAT").write_bytes(text(["PBSALES1"] + [f"{r};{q};{number(p)}" for r, q, p in rows]))
    book = contacts(150)
    (out / "CONTBOOK.DAT").write_bytes(text(["PBCONTBOOK1", "150"] + [x for entry in book for x in entry]))
    regions = len({r for r, _, _ in rows})
    print(f"SALES.DAT: 3000 sales; RECORDS should say: Report written: 3000 sales, {regions} regions")
    top = max(rows, key=lambda t: t[1] * t[2])
    print(f"  largest sale: {top[0]} {top[1]} for about {top[1] * top[2]:.6g}")
    print(f"CONTBOOK.DAT: 150 contacts; first page: {', '.join(b[0] for b in book[:6])}")


if __name__ == "__main__":
    main()
