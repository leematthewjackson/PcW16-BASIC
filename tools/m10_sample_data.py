"""Write the M10 CONTACTS III test databases (deterministic; PDB1 format of
LANGUAGE-SPEC §5.9, encoded here from the specification).

    python3 tools/m10_sample_data.py OUTDIR

OUTDIR/CONTACTS.PDB   160 contacts (ids 1..160, next id 161), names, phones,
                      e-mails and towns drawn from fixed lists by a seeded
                      generator, some sharing a name or a town
OUTDIR/DAMAGED.PDB    the same file with one record byte changed (DB LOAD:
                      IOERR 251) — for the recovery checks, copied to
                      CONTACTS.PDB on a disposable disk only

The files are disposable test data: nothing here reads or changes a real
address book. Check one with tools/pdbcheck.py --type with CONTACT_TYPE.
"""
from __future__ import annotations

import random
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdbcheck import crc16  # noqa: E402

CONTACT_TYPE = "ID:I;NAME:S30;PHONE:S20;EMAIL:S32;TOWN:S20"
WIDTHS = (31, 21, 33, 21)
SIZE = 2 + sum(WIDTHS)
FIRST = ["Ann", "Bob", "Cara", "Dev", "Eve", "Finn", "Gita", "Hal", "Ivy", "Jon", "Kim", "Lee",
         "Mo", "Nia", "Oscar", "Pia", "Quinn", "Raj", "Sue", "Tom"]
LAST = ["Archer", "Baker", "Carter", "Dawson", "Ellis", "Fisher", "Grant", "Hughes", "Irwin",
        "Jones", "Khan", "Lewis", "Mason", "Nolan", "Owen", "Patel", "Reid", "Shaw", "Taylor", "Wood"]
TOWNS = ["Bolton", "Bury", "Chester", "Derby", "Leeds", "Oldham", "Salford", "Wigan", "York", ""]


def record(pid: int, name: str, phone: str, email: str, town: str) -> bytes:
    out = struct.pack("<h", pid)
    for text, width in zip((name, phone, email, town), WIDTHS):
        data = text.encode("ascii")
        assert len(data) < width, text
        out += data.ljust(width, b"\0")
    return out


def database(records: list[bytes], next_id: int) -> bytes:
    head = b"PDB1" + bytes((1, 0)) + struct.pack("<HhhHH", SIZE, len(records), next_id,
                                                crc16(CONTACT_TYPE.encode("ascii")), 0)
    body = head + b"".join(records)
    s1 = s2 = 0
    for b in body:
        s1 = (s1 + b) & 0xFFFF
        s2 = (s2 + s1) & 0xFFFF
    return body + struct.pack("<HH", s1, s2)


def contacts(n: int = 160, seed: int = 1010) -> list[tuple]:
    rnd = random.Random(seed)
    rows = []
    for pid in range(1, n + 1):
        name = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
        phone = rnd.choice(["", f"0161 {rnd.randint(100, 999)} {rnd.randint(1000, 9999)}",
                            f"+44 {rnd.randint(1000, 9999)} {rnd.randint(100000, 999999)}"])
        email = rnd.choice(["", f"{name.split()[0].lower()}{pid}@example.org"])
        rows.append((pid, name, phone, email, rnd.choice(TOWNS)))
    return rows


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(args[0])
    out.mkdir(parents=True, exist_ok=True)
    rows = contacts()
    data = database([record(*r) for r in rows], len(rows) + 1)
    (out / "CONTACTS.PDB").write_bytes(data)
    damaged = bytearray(data)
    damaged[16 + 5 * SIZE + 3] ^= 0x01
    (out / "DAMAGED.PDB").write_bytes(bytes(damaged))
    print(f"{out / 'CONTACTS.PDB'}: {len(rows)} contacts, {len(data)} bytes")
    print(f"{out / 'DAMAGED.PDB'}: one record byte changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
