"""Check a PDB1 database file on the host (LANGUAGE-SPEC §5.9). Read-only.

    python3 tools/pdbcheck.py PEOPLE.PDB
    python3 tools/pdbcheck.py PEOPLE.PDB --type "ID:I;NAME:S40;PHONE:S20" --rows 5

Prints the header, whether the check bytes, length and (with --type) the
TYPE signature are right, the file's SHA-256, and with --type and --rows the
first records decoded. Exit status 0 = valid, 1 = not valid, 2 = usage.
The checker is written from the specification and does not import the
compiler, so it is an independent reading of the format. It never writes.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

CODES = {248: "not a database", 249: "another TYPE", 250: "another version",
         251: "damaged", 252: "more records than the array holds"}


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def fields(signature: str) -> list[tuple[str, str, int]]:
    """'ID:I;NAME:S40' -> [(name, kind, size)]."""
    out = []
    for part in signature.split(";"):
        name, _, code = part.partition(":")
        if code in ("I", "B"):
            out.append((name, code, 2))
        elif code == "R":
            out.append((name, code, 5))
        elif code.startswith("S") and code[1:].isdigit():
            out.append((name, "S", int(code[1:]) + 1))
        else:
            raise ValueError(f"bad field {part!r} (NAME:I, NAME:R, NAME:B or NAME:Sn)")
    return out


def real_value(raw: bytes) -> float:
    """The M7 REAL (LANGUAGE-SPEC §3.1): bytes 0-3 the mantissa, least
    significant first, with bit 7 of byte 3 the sign (the mantissa's top bit
    is an implied 1); byte 4 the exponent, bias 128 (0 = zero); value =
    mantissa / 2^32 * 2^(exponent - 128)."""
    if raw[4] == 0:
        return 0.0
    m = raw[0] | (raw[1] << 8) | (raw[2] << 16) | (((raw[3] & 0x7F) | 0x80) << 24)
    value = m / 2 ** 32 * 2.0 ** (raw[4] - 128)
    return -value if raw[3] & 0x80 else value


def check(data: bytes, signature: str | None = None, capacity: int | None = None) -> tuple[int, dict]:
    """(code, header): 0 when valid, else the DB LOAD code it would give."""
    if len(data) < 16:
        return 251, {}
    magic, version, flags, size, count, next_id, sig, reserved = struct.unpack("<4sBBHhhHH", data[:16])
    head = {"version": version, "flags": flags, "record size": size, "count": count,
            "next identifier": next_id, "signature": f"{sig:04X}h"}
    if magic != b"PDB1":
        return 248, head
    if version != 1 or flags or reserved:
        return 250, head
    if signature is not None:
        want = sum(f[2] for f in fields(signature))
        if size != want or sig != crc16(signature.encode("ascii")):
            return 249, head
    if count < 0:
        return 251, head
    if capacity is not None and count > capacity:
        return 252, head
    end = 16 + count * size
    if len(data) != end + 4:
        return 251, head
    s1 = s2 = 0
    for b in data[:end]:
        s1 = (s1 + b) & 0xFFFF
        s2 = (s2 + s1) & 0xFFFF
    if struct.unpack("<HH", data[end:]) != (s1, s2):
        return 251, head
    return 0, head


def decode(data: bytes, signature: str, n: int) -> list[list]:
    size = struct.unpack("<H", data[6:8])[0]
    count = struct.unpack("<h", data[8:10])[0]
    rows = []
    for i in range(min(n, count)):
        rec, at, row = data[16 + i * size: 16 + (i + 1) * size], 0, []
        for _, kind, width in fields(signature):
            raw = rec[at:at + width]
            if kind == "I":
                row.append(struct.unpack("<h", raw)[0])
            elif kind == "B":
                row.append(bool(struct.unpack("<H", raw)[0]))
            elif kind == "R":
                row.append(real_value(raw))
            else:
                row.append(raw.split(b"\0", 1)[0].decode("latin-1"))
            at += width
        rows.append(row)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", type=Path)
    ap.add_argument("--type", dest="signature", help='the TYPE field list, e.g. "ID:I;NAME:S40"')
    ap.add_argument("--capacity", type=int, help="the program's array length")
    ap.add_argument("--rows", type=int, default=0, help="decode the first N records (needs --type)")
    args = ap.parse_args(argv)
    try:
        data = args.file.read_bytes()
        if args.signature:
            fields(args.signature)
    except (OSError, ValueError) as exc:
        print(f"pdbcheck: {exc}", file=sys.stderr)
        return 2
    code, head = check(data, args.signature, args.capacity)
    print(f"file: {args.file} ({len(data)} bytes)")
    print(f"sha256: {hashlib.sha256(data).hexdigest()}")
    for key, value in head.items():
        print(f"{key}: {value}")
    if args.signature:
        print(f"expected signature: {crc16(args.signature.encode('ascii')):04X}h")
    print("result: valid" if code == 0 else f"result: NOT VALID — DB LOAD would give {code} ({CODES[code]})")
    if code == 0 and args.signature and args.rows:
        for row in decode(data, args.signature, args.rows):
            print("  " + " | ".join(str(v) for v in row))
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
