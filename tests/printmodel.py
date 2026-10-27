"""How Rosanne 1.12's printer driver puts the print meta-file's lines on paper
(M12 corrective), for the tests: the simulator keeps the records the program
sends (z80sim._print_call); this turns them into printed dots.

Written from a static reading of PCW045.SYS, block 10 (docs/M12-PRINTING.md
§6), not from the runtime:
  #9F4E  a coordinate becomes a dot: floor(value / d), d = 1/1800" a dot
         (6 at 300 dpi); x first has the page's left offset added (#9F61);
  #9837, #9950  a thickness t becomes ceil(t / d) dots;
  #9802-#985B  os_meta_score / os_meta_hline (left, right, top, t): x from
         dot(left) to dot(right) + ceil(t / d) - 1, ceil(t / d) rows down
         from dot(top): the line runs on past its right end by its thickness;
  #991E-#997B  os_meta_vline (x, top, bottom, t): ceil(t / d) columns from
         dot(x), rows from dot(top) + ceil(t / d) - 1 to dot(bottom): the line
         starts its thickness (less a dot) below its top.
Checked against the owner's XAnne page at 300 dpi (test_m12_printgeom
OwnerPageTests). Rectangles are (x0, y0, x1, y1) in dots, inclusive; ox, oy
are the page offsets in 1/1800".
"""
from __future__ import annotations


def ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def rects(records, d: int = 6, ox: int = 0, oy: int = 0) -> list[tuple[int, int, int, int]]:
    out = []
    for rec in records:
        if rec[0] in ("hline", "score"):
            _, left, right, top, t = rec
            n = ceil_div(t, d)
            if n:
                y0 = (top + oy) // d
                out.append(((left + ox) // d, y0, (right + ox) // d + n - 1, y0 + n - 1))
        elif rec[0] == "vline":
            _, x, top, bottom, t = rec
            n = ceil_div(t, d)
            y0, y1 = (top + oy) // d + n - 1, (bottom + oy) // d
            if n and y1 >= y0:
                x0 = (x + ox) // d
                out.append((x0, y0, x0 + n - 1, y1))
    return out


def merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Inclusive spans joined where they overlap or touch."""
    out: list[list[int]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def row(rs, y: int) -> list[tuple[int, int]]:
    """The black runs of dot row y."""
    return merge([(x0, x1) for x0, y0, x1, y1 in rs if y0 <= y <= y1])


def column(rs, x: int) -> list[tuple[int, int]]:
    """The black runs of dot column x."""
    return merge([(y0, y1) for x0, y0, x1, y1 in rs if x0 <= x <= x1])


def solid(rs, box: tuple[int, int, int, int]) -> bool:
    """Every dot of box is black."""
    x0, y0, x1, y1 = box
    return all(any(a <= x0 and x1 <= b for a, b in row(rs, y)) for y in range(y0, y1 + 1))


def extent(rs) -> tuple[int, int, int, int]:
    return (min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs))
