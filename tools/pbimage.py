"""PNG to PBI1 and PBI1 to PNG for PcW16 BASIC (M13; docs/graphics-assets.md).

    python3 tools/pbimage.py import PICTURE.png PICTURE.PBI [options]
    python3 tools/pbimage.py sheet HERO.png HERO.PBI --frame 16,24 [--mask HEROM.PBI]
    python3 tools/pbimage.py export ART.PBI art.png [--scale 2]
    python3 tools/pbimage.py info FILE.png|FILE.PBI
    python3 tools/pbimage.py build examples/assets/ASSETS.txt OUTDIR

The PcW16 screen has one bit a pixel, so an image is reduced to black and
white here, on the PC; Rosanne never decodes PNG. Everything is plain
Python (zlib only) and deterministic: the same input and options always give
the same bytes (integer arithmetic throughout).

import options (applied in this order):
  --crop X,Y,W,H         keep that rectangle of the PNG
  --size W,H             scale to W x H pixels (area average)
  --background white|black   what transparent pixels are mixed over (white)
  --threshold N          0..255: a pixel darker than N is black (128)
  --dither none|ordered|floyd   ordered = 4x4 Bayer; floyd = Floyd-Steinberg
  --invert               swap black and white
  --mask FILE.PBI        also write a mask: WHITE where the image is drawn,
                         BLACK where it is transparent (BITMAP MASK's rule)
  --mask-from alpha|white|black   alpha (default: the PNG's transparency),
                         or: white / black pixels of the image are transparent
  --alpha-threshold N    alpha >= N counts as opaque (128)

sheet: the PNG is a grid of frames, each --frame W,H, read left to right,
top to bottom (--count N frames, default all); they are written one under
another (a W-pixel-wide strip), the layout BITMAP PUT and MASK draw fastest
(a frame k is the part 0, k * H, W, H). The same image options apply to each
frame except --crop and --size.

build: every line of a manifest (blank lines and # comments aside) is
  TARGET.PBI  import|sheet  SOURCE.png  [options]
with SOURCE relative to the manifest's folder; TARGET (and a --mask file)
is written to OUTDIR. Target names are PcW16 file names (8.3, capitals).
It stops at the first line that fails, naming it.

A BITMAP holds at most 568 x 300 pixels and 16384 bytes ((W + 7) \\ 8 x H);
a larger result is refused. Exit status: 0 done, 1 an error (the message
says why), 2 usage.
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pbicheck  # noqa: E402

PNG_SIG = b"\x89PNG\r\n\x1a\n"
MAX_W, MAX_H, MAX_BYTES = 568, 300, 16384  # LANGUAGE-SPEC §5.12: one BITMAP
ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


class ImageError(Exception):
    """A file that cannot be converted, with the reason."""


# ------------------------------------------------------------ PNG reading
def _chunks(data: bytes):
    if not data.startswith(PNG_SIG):
        raise ImageError("not a PNG file (its first 8 bytes are not the PNG signature)")
    at = len(PNG_SIG)
    while True:
        if at + 8 > len(data):
            raise ImageError("the PNG file is cut short (no IEND chunk)")
        length, kind = struct.unpack(">I4s", data[at:at + 8])
        body = data[at + 8:at + 8 + length]
        if len(body) != length or at + 12 + length > len(data):
            raise ImageError(f"the PNG file is cut short inside its {kind.decode('latin-1')!r} chunk")
        crc = struct.unpack(">I", data[at + 8 + length:at + 12 + length])[0]
        if zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            raise ImageError(f"the PNG file is damaged: the {kind.decode('latin-1')!r} chunk fails its CRC")
        yield kind, body
        if kind == b"IEND":
            return
        at += 12 + length


def _unfilter(raw: bytes, width: int, height: int, bpp: int, bits_per_row: int) -> list[bytes]:
    stride = (bits_per_row + 7) // 8
    rows, prev, at = [], bytearray(stride), 0
    for _ in range(height):
        if at + 1 + stride > len(raw):
            raise ImageError("the PNG image data is cut short")
        ftype, line = raw[at], bytearray(raw[at + 1:at + 1 + stride])
        at += 1 + stride
        if ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b, c = prev[i], (prev[i - bpp] if i >= bpp else 0)
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        elif ftype != 0:
            raise ImageError(f"the PNG image data has an unknown row filter ({ftype})")
        rows.append(bytes(line))
        prev = line
    return rows, at


def _samples(row: bytes, count: int, depth: int) -> list[int]:
    if depth == 8:
        return list(row[:count])
    if depth == 16:
        return [row[2 * i] << 8 | row[2 * i + 1] for i in range(count)]
    per, mask = 8 // depth, (1 << depth) - 1
    return [(row[i // per] >> (8 - depth * (i % per + 1))) & mask for i in range(count)]


def read_png(data: bytes) -> tuple[int, int, list[list[int]], list[list[int]], bool]:
    """(width, height, luminance rows 0..255, alpha rows 0..255, whether the
    file has any transparency)."""
    header = plte = trns = None
    idat = []
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            if len(body) != 13:
                raise ImageError("the PNG header (IHDR) has the wrong length")
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
    if header is None:
        raise ImageError("the PNG file has no IHDR header")
    width, height, depth, ctype, comp, filt, interlace = header
    allowed = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
    if ctype not in allowed or depth not in allowed[ctype]:
        raise ImageError(f"the PNG colour type {ctype} with bit depth {depth} is not a valid combination")
    if comp != 0 or filt != 0 or interlace not in (0, 1):
        raise ImageError("the PNG file uses an unknown compression, filter or interlace method")
    if width == 0 or height == 0:
        raise ImageError("the PNG image is empty (0 pixels wide or high)")
    if width > 4096 or height > 4096:
        raise ImageError(f"the PNG image is {width} x {height}: at most 4096 x 4096 is read")
    if ctype == 3 and plte is None:
        raise ImageError("the palette PNG has no PLTE chunk")
    if not idat:
        raise ImageError("the PNG file has no image data (IDAT)")
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as exc:
        raise ImageError(f"the PNG image data cannot be decompressed ({exc})") from None
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp = max(1, channels * depth // 8)
    lum = [[0] * width for _ in range(height)]
    alpha = [[255] * width for _ in range(height)]
    transparent = ctype in (4, 6) or trns is not None
    maxv = (1 << depth) - 1

    def scale(v: int) -> int:
        return v * 255 // maxv if depth != 8 else v

    def put(x: int, y: int, s: list[int]) -> None:
        if ctype == 3:
            index = s[0]
            if index * 3 + 2 >= len(plte):
                raise ImageError(f"the PNG uses palette entry {index}, which its PLTE does not have")
            r, g, b = plte[3 * index:3 * index + 3]
            a = trns[index] if trns is not None and index < len(trns) else 255
        elif ctype in (0, 4):
            r = g = b = scale(s[0])
            a = scale(s[1]) if ctype == 4 else 255
            if ctype == 0 and trns is not None and len(trns) >= 2 and s[0] == struct.unpack(">H", trns[:2])[0]:
                a = 0
        else:
            r, g, b = (scale(v) for v in s[:3])
            a = scale(s[3]) if ctype == 6 else 255
            if ctype == 2 and trns is not None and len(trns) >= 6 and tuple(s[:3]) == struct.unpack(">HHH", trns[:6]):
                a = 0
        # ITU-R BT.601 luma, in integers
        lum[y][x] = (299 * r + 587 * g + 114 * b + 500) // 1000
        alpha[y][x] = a

    passes = ADAM7 if interlace else ((0, 0, 1, 1),)
    at = 0
    for x0, y0, dx, dy in passes:
        pw = (width - x0 + dx - 1) // dx
        ph = (height - y0 + dy - 1) // dy
        if pw == 0 or ph == 0:
            continue
        rows, used = _unfilter(raw[at:], pw, ph, bpp, pw * channels * depth)
        at += used
        for j, row in enumerate(rows):
            values = _samples(row, pw * channels, depth)
            for i in range(pw):
                put(x0 + i * dx, y0 + j * dy, values[i * channels:(i + 1) * channels])
    return width, height, lum, alpha, transparent


# ------------------------------------------------------------ PNG writing
def write_png(rows: list[list[int]], scale: int = 1) -> bytes:
    """A 1-bit greyscale PNG of rows (1 = black), each pixel scale x scale."""
    height, width = len(rows), len(rows[0])
    out = bytearray()
    for row in rows:
        line = bytearray([0])
        bits = [0 if v else 1 for v in row for _ in range(scale)]  # PNG grey: 1 = white
        for i in range(0, len(bits), 8):
            chunk = bits[i:i + 8] + [0] * (8 - len(bits[i:i + 8]))
            line.append(sum(b << (7 - k) for k, b in enumerate(chunk)))
        for _ in range(scale):
            out += line

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width * scale, height * scale, 1, 0, 0, 0, 0)
    return PNG_SIG + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(out), 9)) + chunk(b"IEND", b"")


# ------------------------------------------------------------ processing
def crop(grid: list[list[int]], x: int, y: int, w: int, h: int) -> list[list[int]]:
    return [row[x:x + w] for row in grid[y:y + h]]


def resize(grid: list[list[int]], w: int, h: int) -> list[list[int]]:
    """Area average to w x h, in exact integers."""
    sh, sw = len(grid), len(grid[0])

    def axis(n_src: int, n_dst: int):
        # for each destination index: [(source index, overlap)], in units of
        # 1/(n_src * n_dst) of the image's extent; the weights add to n_src
        spans = []
        for d in range(n_dst):
            lo, hi = d * n_src, (d + 1) * n_src  # in units of 1/n_dst source pixels
            spans.append([(s, min(hi, (s + 1) * n_dst) - max(lo, s * n_dst))
                          for s in range(lo // n_dst, min(n_src, (hi + n_dst - 1) // n_dst))
                          if min(hi, (s + 1) * n_dst) > max(lo, s * n_dst)])
        return spans

    xs, ys = axis(sw, w), axis(sh, h)
    across = [[sum(row[s] * wt for s, wt in span) for span in xs] for row in grid]  # x weight sum: sw
    total = sw * sh
    return [[(sum(across[s][x] * wt for s, wt in ys[y]) + total // 2) // total for x in range(w)] for y in range(h)]


def to_bits(lum, alpha, *, threshold=128, dither="none", invert=False, background=255):
    """Rows of 1 = black. Transparent pixels are mixed over the background."""
    h, w = len(lum), len(lum[0])
    v = [[(lum[y][x] * alpha[y][x] + background * (255 - alpha[y][x]) + 127) // 255 for x in range(w)]
         for y in range(h)]
    out = [[0] * w for _ in range(h)]
    if dither == "floyd":
        err = [[0] * (w + 2) for _ in range(h + 1)]  # sixteenths of a level
        for y in range(h):
            for x in range(w):
                want = v[y][x] * 16 + err[y][x + 1]
                black = want < threshold * 16
                out[y][x] = 1 if black else 0
                e = want - (0 if black else 255 * 16)
                err[y][x + 2] += e * 7 // 16
                err[y + 1][x] += e * 3 // 16
                err[y + 1][x + 1] += e * 5 // 16
                err[y + 1][x + 2] += e - e * 7 // 16 - e * 3 // 16 - e * 5 // 16
    else:
        for y in range(h):
            for x in range(w):
                t = threshold
                if dither == "ordered":
                    t = (BAYER4[y % 4][x % 4] * 255 + 128) // 16 + 8
                out[y][x] = 1 if v[y][x] < t else 0
    if invert:
        out = [[1 - p for p in row] for row in out]
    return out


def mask_bits(lum, alpha, *, source="alpha", alpha_threshold=128, threshold=128):
    """Rows for a mask PBI1: 0 (white) = drawn, 1 (black) = transparent."""
    if source == "alpha":
        return [[0 if a >= alpha_threshold else 1 for a in row] for row in alpha]
    want_white = source == "white"
    return [[1 if (l >= threshold) == want_white else 0 for l in row] for row in lum]


def check_size(w: int, h: int, what: str) -> None:
    if not (1 <= w <= MAX_W and 1 <= h <= MAX_H) or (w + 7) // 8 * h > MAX_BYTES:
        raise ImageError(f"{what} would be {w} x {h} pixels ({(w + 7) // 8 * h} bytes); a BITMAP holds at most "
                         f"{MAX_W} x {MAX_H} pixels and {MAX_BYTES} bytes: use --size, --crop or fewer frames")


def pbi_bytes(rows) -> bytes:
    data = pbicheck.from_rows(rows)
    code, info = pbicheck.check(data)
    assert code == 0, info  # the writer and the checker agree
    return data


# ------------------------------------------------------------ commands
def _pair(text: str, n: int, what: str) -> list[int]:
    try:
        values = [int(v) for v in text.split(",")]
    except ValueError:
        values = []
    if len(values) != n or any(v < 0 for v in values):
        raise ImageError(f"{what} needs {n} whole numbers separated by commas, got {text!r}")
    return values


def load(path: Path):
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ImageError(f"{path}: {exc.strerror}") from None
    return read_png(data)


def cmd_import(args) -> int:
    w, h, lum, alpha, transparent = load(Path(args.source))
    if args.crop:
        cx, cy, cw, ch = _pair(args.crop, 4, "--crop")
        if cw == 0 or ch == 0 or cx + cw > w or cy + ch > h:
            raise ImageError(f"--crop {args.crop} is not inside the {w} x {h} image")
        lum, alpha, w, h = crop(lum, cx, cy, cw, ch), crop(alpha, cx, cy, cw, ch), cw, ch
    if args.size:
        nw, nh = _pair(args.size, 2, "--size")
        check_size(nw, nh, "--size")
        lum, alpha, w, h = resize(lum, nw, nh), resize(alpha, nw, nh), nw, nh
    check_size(w, h, "the picture")
    rows = to_bits(lum, alpha, threshold=args.threshold, dither=args.dither, invert=args.invert,
                   background=0 if args.background == "black" else 255)
    Path(args.target).write_bytes(pbi_bytes(rows))
    print(f"{args.target}: {w} x {h}, {(w + 7) // 8 * h} bytes")
    if args.mask:
        if args.mask_from == "alpha" and not transparent:
            raise ImageError(f"{args.source} has no transparency for --mask; use --mask-from white or black")
        Path(args.mask).write_bytes(pbi_bytes(mask_bits(lum, alpha, source=args.mask_from,
                                                        alpha_threshold=args.alpha_threshold,
                                                        threshold=args.threshold)))
        print(f"{args.mask}: the mask, {w} x {h}")
    return 0


def cmd_sheet(args) -> int:
    w, h, lum, alpha, transparent = load(Path(args.source))
    fw, fh = _pair(args.frame, 2, "--frame")
    if fw == 0 or fh == 0 or fw > w or fh > h:
        raise ImageError(f"--frame {args.frame} does not fit the {w} x {h} image")
    across, down = w // fw, h // fh
    count = args.count if args.count is not None else across * down
    if not 1 <= count <= across * down:
        raise ImageError(f"--count {count}: the image holds {across * down} frames of {fw} x {fh}")
    check_size(fw, fh * count, f"{count} frames of {fw} x {fh} one under another")
    frames_l, frames_a = [], []
    for k in range(count):
        x, y = (k % across) * fw, (k // across) * fh
        frames_l += crop(lum, x, y, fw, fh)
        frames_a += crop(alpha, x, y, fw, fh)
    rows = to_bits(frames_l, frames_a, threshold=args.threshold, dither=args.dither, invert=args.invert,
                   background=0 if args.background == "black" else 255)
    Path(args.target).write_bytes(pbi_bytes(rows))
    print(f"{args.target}: {count} frames of {fw} x {fh}, a {fw} x {fh * count} strip; frame k is the part "
          f"0, k * {fh}, {fw}, {fh}")
    if args.mask:
        if args.mask_from == "alpha" and not transparent:
            raise ImageError(f"{args.source} has no transparency for --mask; use --mask-from white or black")
        Path(args.mask).write_bytes(pbi_bytes(mask_bits(frames_l, frames_a, source=args.mask_from,
                                                        alpha_threshold=args.alpha_threshold,
                                                        threshold=args.threshold)))
        print(f"{args.mask}: the mask strip")
    return 0


def cmd_export(args) -> int:
    try:
        data = Path(args.source).read_bytes()
    except OSError as exc:
        raise ImageError(f"{args.source}: {exc.strerror}") from None
    code, info = pbicheck.check(data)
    if code:
        raise ImageError(f"{args.source} is not a valid PBI1 file: {info.get('reason', pbicheck.CODES.get(code, code))}")
    if not 1 <= args.scale <= 8:
        raise ImageError("--scale is 1 to 8")
    Path(args.target).write_bytes(write_png(pbicheck.pixels(data), args.scale))
    print(f"{args.target}: {info['width'] * args.scale} x {info['height'] * args.scale}")
    return 0


def cmd_info(args) -> int:
    path = Path(args.source)
    data = path.read_bytes()
    if data.startswith(PNG_SIG):
        w, h, _, _, transparent = read_png(data)
        print(f"{path}: PNG, {w} x {h}, {'with' if transparent else 'without'} transparency")
        return 0
    code, info = pbicheck.check(data)
    if code:
        raise ImageError(f"{path}: neither a PNG nor a valid PBI1 file ({pbicheck.CODES.get(code, code)})")
    print(f"{path}: PBI1, {info['width']} x {info['height']}, {info['bytes']} bytes")
    return 0


def cmd_build(args) -> int:
    import re
    import shlex
    manifest = Path(args.manifest)
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ImageError(f"{manifest}: {exc.strerror}") from None
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    name_ok = re.compile(r"^[A-Z0-9_]{1,8}\.PBI$")
    for number, line in enumerate(lines, 1):
        words = shlex.split(line, comments=True)
        if not words:
            continue
        where = f"{manifest}:{number}"
        if len(words) < 3 or words[1] not in ("import", "sheet"):
            raise ImageError(f"{where}: want TARGET.PBI import|sheet SOURCE.png [options]")
        target, command, source, options = words[0], words[1], words[2], words[3:]
        for i, word in enumerate(options):
            if word == "--mask" and i + 1 < len(options):
                if not name_ok.match(options[i + 1]):
                    raise ImageError(f"{where}: the mask {options[i + 1]} is not an 8.3 PcW16 name in capitals")
                options[i + 1] = str(out / options[i + 1])
        if not name_ok.match(target):
            raise ImageError(f"{where}: {target} is not an 8.3 PcW16 name in capitals ending .PBI")
        code = main([command, str(manifest.parent / source), str(out / target), *options])
        if code:
            raise ImageError(f"{where}: {target} was not made")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pbimage.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def image_options(p):
        p.add_argument("--background", choices=("white", "black"), default="white")
        p.add_argument("--threshold", type=int, default=128, metavar="N")
        p.add_argument("--dither", choices=("none", "ordered", "floyd"), default="none")
        p.add_argument("--invert", action="store_true")
        p.add_argument("--mask", metavar="FILE.PBI")
        p.add_argument("--mask-from", choices=("alpha", "white", "black"), default="alpha")
        p.add_argument("--alpha-threshold", type=int, default=128, metavar="N")

    p = sub.add_parser("import", help="a PNG to a PBI1 picture")
    p.add_argument("source")
    p.add_argument("target")
    p.add_argument("--crop", metavar="X,Y,W,H")
    p.add_argument("--size", metavar="W,H")
    image_options(p)
    p = sub.add_parser("sheet", help="a PNG grid of frames to a PBI1 strip")
    p.add_argument("source")
    p.add_argument("target")
    p.add_argument("--frame", required=True, metavar="W,H")
    p.add_argument("--count", type=int)
    image_options(p)
    p = sub.add_parser("export", help="a PBI1 picture to a PNG")
    p.add_argument("source")
    p.add_argument("target")
    p.add_argument("--scale", type=int, default=1)
    p = sub.add_parser("info", help="describe a PNG or PBI1 file")
    p.add_argument("source")
    p = sub.add_parser("build", help="make every picture a manifest lists")
    p.add_argument("manifest")
    p.add_argument("outdir")
    args = parser.parse_args(argv)
    for name in ("threshold", "alpha_threshold"):
        if hasattr(args, name) and not 0 <= getattr(args, name) <= 256:
            print(f"pbimage.py: --{name.replace('_', '-')} is 0 to 256", file=sys.stderr)
            return 2
    try:
        return {"import": cmd_import, "sheet": cmd_sheet, "export": cmd_export, "info": cmd_info,
                "build": cmd_build}[args.command](args)
    except ImageError as exc:
        print(f"pbimage.py: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:  # M14 (T4): a missing or unreadable file, without a traceback
        print(f"pbimage.py: {exc.filename or ''}: {exc.strerror or exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
