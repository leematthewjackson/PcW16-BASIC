"""Check a PBI1 bitmap file on the host, and convert it (docs/M12-BITMAP-FORMAT.md).

    python3 tools/pbicheck.py ART.PBI                 # header, check, result
    python3 tools/pbicheck.py ART.PBI --pbm art.pbm   # also write a PBM image
    python3 tools/pbicheck.py --from-pbm art.pbm ART.PBI   # make a PBI1 file

Written from the format description, not from the compiler, so it is an
independent reading of the format. Exit status 0 = valid, 1 = not valid,
2 = usage. It never changes the file it checks.

The format: +0 "PBI1", +4 version 1, +5 flags 0, +6 width, +8 height,
+10 bytes a row = (width + 7) // 8, +12 data bytes = row * height, +14 0
(little-endian words); the rows top to bottom, bit 7 the leftmost pixel, a
set bit WHITE (as the PcW16 screen holds it); then two check words: s1 =
the sum (mod 65536) of every byte before them, s2 = the sum of the running
s1 after each byte.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

MAGIC = b"PBI1"
CODES = {248: "not a PBI1 file", 250: "another version", 251: "damaged"}


def sums(data: bytes) -> tuple[int, int]:
    s1 = s2 = 0
    for b in data:
        s1 = (s1 + b) & 0xFFFF
        s2 = (s2 + s1) & 0xFFFF
    return s1, s2


def check(data: bytes) -> tuple[int, dict]:
    """(code, header): 0 when valid, else the BITMAP LOAD code it would give
    (252, larger than the bitmap, depends on the program and is not checked)."""
    if data[:4] != MAGIC[:len(data[:4])]:
        return 248, {}
    if len(data) < 16:  # too short to tell (as BITMAP LOAD: damaged)
        return 251, {}
    version, flags, w, h, row, size, reserved = struct.unpack("<BBHHHHH", data[4:16])
    head = {"version": version, "width": w, "height": h, "row": row, "bytes": size}
    if version != 1 or flags or reserved:
        return 250, head
    if not (1 <= w <= 640 and 1 <= h <= 480) or row != (w + 7) // 8 or size != row * h:
        return 251, head
    if len(data) != 16 + size + 4:
        return 251, head
    if struct.unpack("<HH", data[16 + size:]) != sums(data[:16 + size]):
        return 251, head
    return 0, head


def pixels(data: bytes) -> list[list[int]]:
    """Rows of pixels, 1 = black (as PBM counts), from a valid file."""
    w, h, row = struct.unpack("<HHH", data[6:12])
    body = data[16:]
    return [[0 if body[y * row + x // 8] & (0x80 >> (x % 8)) else 1 for x in range(w)] for y in range(h)]


def to_pbm(data: bytes) -> bytes:
    rows = pixels(data)
    w, h = len(rows[0]), len(rows)
    out = bytearray(f"P4\n{w} {h}\n".encode("ascii"))
    for r in rows:
        for i in range(0, w, 8):
            byte = 0
            for b, v in enumerate(r[i:i + 8]):
                byte |= v << (7 - b)
            out.append(byte)
    return bytes(out)


def from_rows(rows: list[list[int]]) -> bytes:
    """A PBI1 file from rows of pixels (1 = black)."""
    w, h = len(rows[0]), len(rows)
    row = (w + 7) // 8
    body = bytearray()
    for r in rows:
        line = bytearray(row)
        for x in range(row * 8):
            if x >= w or not r[x]:
                line[x // 8] |= 0x80 >> (x % 8)  # white, and the unused bits of the last byte
        body += line
    head = MAGIC + struct.pack("<BBHHHHH", 1, 0, w, h, row, len(body), 0)
    data = head + bytes(body)
    return data + struct.pack("<HH", *sums(data))


def read_pbm(path: Path) -> list[list[int]]:
    raw = path.read_bytes()
    parts = raw.split(maxsplit=3)
    if parts[0] not in (b"P1", b"P4"):
        raise ValueError("not a PBM file (P1 or P4)")
    w, h = int(parts[1]), int(parts[2])
    if parts[0] == b"P1":
        bits = [int(c) for c in parts[3].decode("ascii") if c in "01"]
        return [bits[y * w:(y + 1) * w] for y in range(h)]
    row = (w + 7) // 8
    body = parts[3]
    return [[(body[y * row + x // 8] >> (7 - x % 8)) & 1 for x in range(w)] for y in range(h)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", nargs="?", help="the PBI1 file to check (or to make, with --from-pbm)")
    ap.add_argument("--pbm", help="also write the image as a PBM file")
    ap.add_argument("--from-pbm", help="make the PBI1 file FILE from this PBM image")
    args = ap.parse_args(argv)
    if args.from_pbm:
        target = Path(args.file or "")
        if not args.file:
            ap.error("give the PBI1 file to write")
        target.write_bytes(from_rows(read_pbm(Path(args.from_pbm))))
        print(f"wrote {target}")
        return 0
    if not args.file:
        ap.error("give a PBI1 file")
    data = Path(args.file).read_bytes()
    code, head = check(data)
    for key, value in head.items():
        print(f"{key}: {value}")
    print(f"result: {'valid' if code == 0 else f'NOT valid ({code}: {CODES[code]})'}")
    if code == 0 and args.pbm:
        Path(args.pbm).write_bytes(to_pbm(data))
        print(f"wrote {args.pbm}")
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
