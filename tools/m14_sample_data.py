"""Write the M14 acceptance data file into a folder (default artifacts/m14).

    python3 tools/m14_sample_data.py [OUT_DIR]

M14S.PDB  a PDB1 database of M14PRB's TYPE Item (ID:I;NAME:S10) with one
          record whose STRING field has no terminating 0 (11 bytes of "X"),
          and a correct header and check: DB LOAD must take it as damaged
          (IOERR 251, M14-DEFECT-REGISTER F4). Generated, not personal data.
The same command always writes the same bytes (tests/test_m14_probe.py).
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIGNATURE = "ID:I;NAME:S10"
SIZE = 2 + 11


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE, as the compiler's database signature."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def unterminated() -> bytes:
    record = struct.pack("<h", 1) + b"X" * 11
    body = b"PDB1" + bytes((1, 0)) + struct.pack("<HhhHH", SIZE, 1, 2, crc16(SIGNATURE.encode()), 0) + record
    s1 = s2 = 0
    for b in body:
        s1 = (s1 + b) & 0xFFFF
        s2 = (s2 + s1) & 0xFFFF
    return body + struct.pack("<HH", s1, s2)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = Path(argv[0]) if argv else ROOT / "artifacts" / "m14"
    out.mkdir(parents=True, exist_ok=True)
    (out / "M14S.PDB").write_bytes(unterminated())
    print(f"{out}/M14S.PDB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
