"""Write the M12 acceptance data files into a folder (default artifacts/m12).

    python3 tools/m12_sample_data.py [OUT_DIR]

SAMPLE.PBI  a 544 x 240 picture for PAINT's Open (Session 1): a frame, a
            circle, a filled ellipse, a checkerboard, diagonals and a
            staircase, drawn here in Python and written with
            tools/pbicheck.py's PBI1 writer (generated, not personal data)
WRAPTEST.MD the wrapping document for MDEDIT IV (Session 4), a copy of
            developer-tests/wraptest.md
EDTEST.MD   MDEDIT's acceptance document, a copy of developer-tests/edtest.md
The same command always writes the same bytes (tests/test_m12_programs.py).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pbicheck  # noqa: E402

W, H = 544, 240


def sample_rows() -> list[list[int]]:
    """The picture, 1 = black."""
    px = [[0] * W for _ in range(H)]

    def dot(x, y):
        if 0 <= x < W and 0 <= y < H:
            px[y][x] = 1

    for x in range(W):  # the frame
        dot(x, 0)
        dot(x, H - 1)
    for y in range(H):
        dot(0, y)
        dot(W - 1, y)
    cx, cy, r = 90, 120, 70  # a circle (midpoint)
    x, y, err = r, 0, 1 - r
    while x >= y:
        for sx, sy in ((x, y), (y, x), (-y, x), (-x, y), (-x, -y), (-y, -x), (y, -x), (x, -y)):
            dot(cx + sx, cy + sy)
        y += 1
        if err < 0:
            err += 2 * y + 1
        else:
            x -= 1
            err += 2 * (y - x) + 1
    for y in range(-40, 41):  # a filled ellipse, 80 x 40 half-axes
        for x in range(-80, 81):
            if x * x * 1600 + y * y * 6400 <= 1600 * 6400:
                dot(270 + x, 120 + y)
    for y in range(20, 100):  # a checkerboard of 8-pixel squares
        for x in range(380, 524):
            if ((x - 380) // 8 + (y - 20) // 8) % 2 == 0:
                dot(x, y)
    for k in range(144):  # two diagonals
        dot(380 + k, 120 + k * 100 // 144)
        dot(523 - k, 120 + k * 100 // 144)
    for step in range(10):  # a staircase along the bottom
        for x in range(10 + step * 20, 30 + step * 20):
            for y in range(230 - step * 4, 236):
                dot(x, y)
    return px


def write(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "SAMPLE.PBI").write_bytes(pbicheck.from_rows(sample_rows()))
    shutil.copyfile(ROOT / "developer-tests" / "wraptest.md", out / "WRAPTEST.MD")
    shutil.copyfile(ROOT / "developer-tests" / "edtest.md", out / "EDTEST.MD")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "artifacts" / "m12"
    write(target)
    for name in ("SAMPLE.PBI", "WRAPTEST.MD", "EDTEST.MD"):
        print(f"{target / name}: {(target / name).stat().st_size} bytes")
