"""M13 Stage C: tools/pbimage.py, PNG to PBI1 and back.

The PNG files here are written by a small encoder of this test's own (zlib,
the PNG chunk rules), not by the tool, for every colour type and bit depth,
interlaced too, so the tool's reader is checked against an independent
writer. PBI1 files are checked with tools/pbicheck.py; exported PNGs are
decompressed here and their bits compared directly.
"""
from __future__ import annotations

import io
import struct
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pbicheck  # noqa: E402
import pbimage  # noqa: E402


def chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def pack(samples, depth):
    if depth == 8:
        return bytes(samples)
    if depth == 16:
        return b"".join(struct.pack(">H", s) for s in samples)
    per = 8 // depth
    out = bytearray((len(samples) + per - 1) // per)
    for i, s in enumerate(samples):
        out[i // per] |= s << (8 - depth * (i % per + 1))
    return bytes(out)


def png(pixels, ctype, depth, *, plte=None, trns=None, interlace=False, filt=0):
    """pixels: rows of tuples of samples (channels of the colour type)."""
    h, w = len(pixels), len(pixels[0])
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp = max(1, channels * depth // 8)

    def scanlines(rows):
        out = bytearray()
        prev = None
        for row in rows:
            line = bytearray(pack([s for px in row for s in px], depth))
            if filt == 1:  # Sub
                enc = bytearray(line)
                for i in range(len(line) - 1, bpp - 1, -1):
                    enc[i] = (line[i] - line[i - bpp]) & 0xFF
                out += bytes([1]) + enc
            elif filt == 2 and prev is not None:  # Up
                out += bytes([2]) + bytes((a - b) & 0xFF for a, b in zip(line, prev))
            else:
                out += bytes([0]) + line
            prev = line
        return out

    if interlace:
        raw = bytearray()
        for x0, y0, dx, dy in pbimage.ADAM7:
            rows = [[pixels[y][x] for x in range(x0, w, dx)] for y in range(y0, h, dy)]
            if rows and rows[0]:
                raw += scanlines(rows)
    else:
        raw = scanlines(pixels)
    data = pbimage.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, int(interlace)))
    if plte is not None:
        data += chunk(b"PLTE", bytes(c for rgb in plte for c in rgb))
    if trns is not None:
        data += chunk(b"tRNS", trns)
    return data + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")


def checker(w, h, cell=3):
    """1 = black squares of cell pixels."""
    return [[((x // cell) + (y // cell)) % 2 for x in range(w)] for y in range(h)]


def tool(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = pbimage.main([str(a) for a in args])
    return code, out.getvalue(), err.getvalue()


class ReadTests(unittest.TestCase):
    """Every colour type and depth decodes to the same black-and-white."""

    W, H = 13, 7

    def cases(self):
        bits = checker(self.W, self.H)
        for depth in (1, 2, 4, 8, 16):
            top = (1 << depth) - 1
            yield f"grey{depth}", png([[(0 if b else top,) for b in r] for r in bits], 0, depth)
        for depth in (8, 16):
            top = (1 << depth) - 1
            yield f"rgb{depth}", png([[((0, 0, 0) if b else (top, top, top)) for b in r] for r in bits], 2, depth)
            yield f"grey-alpha{depth}", png([[(0 if b else top, top) for b in r] for r in bits], 4, depth)
            yield f"rgba{depth}", png([[((0, 0, 0, top) if b else (top, top, top, top)) for b in r] for r in bits],
                                      6, depth)
        for depth in (1, 2, 4, 8):
            yield f"palette{depth}", png([[(1 if b else 0,) for b in r] for r in bits], 3, depth,
                                         plte=[(255, 255, 255), (0, 0, 0)])
        yield "interlaced", png([[(0 if b else 255,) for b in r] for r in bits], 0, 8, interlace=True)
        yield "interlaced-rgba", png([[((0, 0, 0, 255) if b else (255, 255, 255, 255)) for b in r] for r in bits],
                                     6, 8, interlace=True)
        yield "filter-sub", png([[((0, 0, 0) if b else (255, 255, 255)) for b in r] for r in bits], 2, 8, filt=1)
        yield "filter-up", png([[(0 if b else 255,) for b in r] for r in bits], 0, 8, filt=2)

    def test_every_format_reads_the_same(self):
        want = checker(self.W, self.H)
        for name, data in self.cases():
            with self.subTest(name=name):
                w, h, lum, alpha, _ = pbimage.read_png(data)
                self.assertEqual((w, h), (self.W, self.H))
                self.assertEqual(pbimage.to_bits(lum, alpha), want)

    def test_paeth_and_average_filters(self):
        # rows written with filter 4 (Paeth) / 3 (Average) by hand: a ramp
        w, h = 6, 3
        rows = [[(x * 40 + y * 10) for x in range(w)] for y in range(h)]
        raw = bytearray()
        prev = [0] * w
        for y, row in enumerate(rows):
            kind = 4 if y % 2 == 0 else 3
            enc = []
            for x, v in enumerate(row):
                a, b, c = (row[x - 1] if x else 0), prev[x], (prev[x - 1] if x else 0)
                if kind == 3:
                    pred = (a + b) >> 1
                else:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pred = a if pa <= pb and pa <= pc else b if pb <= pc else c
                enc.append((v - pred) & 0xFF)
            raw += bytes([kind] + enc)
            prev = row
        data = pbimage.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) + \
            chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")
        _, _, lum, _, _ = pbimage.read_png(data)
        self.assertEqual(lum, rows)

    def test_transparency_is_read(self):
        data = png([[(0, 0, 0, 255), (0, 0, 0, 0)]], 6, 8)
        self.assertEqual(pbimage.read_png(data)[3], [[255, 0]])
        data = png([[(0,), (1,)]], 3, 8, plte=[(0, 0, 0), (255, 255, 255)], trns=bytes([255, 0]))
        self.assertEqual(pbimage.read_png(data)[3], [[255, 0]])
        data = png([[(5,), (9,)]], 0, 8, trns=struct.pack(">H", 9))
        self.assertEqual(pbimage.read_png(data)[3], [[255, 0]])

    def test_malformed_files(self):
        good = png([[(0,)]], 0, 8)
        cases = {
            "not a PNG": (b"GIF89a" + good[6:], "not a PNG file"),
            "cut short": (good[:30], "cut short"),
            "bad crc": (good[:20] + bytes([good[20] ^ 1]) + good[21:], "fails its CRC"),
            "bad combination": (pbimage.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 4, 2, 0, 0, 0)) +
                                chunk(b"IEND", b""), "colour type 2 with bit depth 4"),
            "empty": (pbimage.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", 0, 1, 8, 0, 0, 0, 0)) +
                      chunk(b"IEND", b""), "empty"),
            "no data": (pbimage.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)) +
                        chunk(b"IEND", b""), "no image data"),
            "short data": (pbimage.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 0, 0, 0, 0)) +
                           chunk(b"IDAT", zlib.compress(b"\0\0")) + chunk(b"IEND", b""), "cut short"),
            "bad filter": (pbimage.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)) +
                           chunk(b"IDAT", zlib.compress(b"\x09\x00")) + chunk(b"IEND", b""), "unknown row filter"),
            "palette index": (png([[(3,)]], 3, 8, plte=[(0, 0, 0)]), "palette entry 3"),
        }
        for name, (data, msg) in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(pbimage.ImageError) as ctx:
                    pbimage.read_png(data)
                self.assertIn(msg, str(ctx.exception))


class ConvertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        (self.dir / name).write_bytes(data)
        return self.dir / name

    def pixels(self, name):
        data = (self.dir / name).read_bytes()
        self.assertEqual(pbicheck.check(data)[0], 0)
        return pbicheck.pixels(data)

    def test_import_is_exact_and_reproducible(self):
        bits = checker(40, 20)
        src = self.write("c.png", png([[(0 if b else 255,) for b in r] for r in bits], 0, 8))
        self.assertEqual(tool("import", src, self.dir / "C.PBI")[0], 0)
        self.assertEqual(self.pixels("C.PBI"), bits)
        first = (self.dir / "C.PBI").read_bytes()
        tool("import", src, self.dir / "C.PBI")
        self.assertEqual((self.dir / "C.PBI").read_bytes(), first)

    def test_crop_and_size(self):
        bits = checker(40, 20, cell=4)
        src = self.write("c.png", png([[(0 if b else 255,) for b in r] for r in bits], 0, 8))
        tool("import", src, self.dir / "A.PBI", "--crop", "4,0,16,8")
        self.assertEqual(self.pixels("A.PBI"), [row[4:20] for row in bits[:8]])
        tool("import", src, self.dir / "B.PBI", "--size", "10,5")  # 4-pixel squares to 1-pixel
        self.assertEqual(self.pixels("B.PBI"), checker(10, 5, cell=1))
        tool("import", src, self.dir / "D.PBI", "--size", "80,40")  # doubled
        self.assertEqual(self.pixels("D.PBI"), checker(80, 40, cell=8))
        code, _, err = tool("import", src, self.dir / "E.PBI", "--crop", "30,0,20,5")
        self.assertEqual(code, 1)
        self.assertIn("is not inside the 40 x 20 image", err)

    def test_threshold_dither_invert(self):
        grey = [[x * 255 // 15 for x in range(16)] for _ in range(8)]
        src = self.write("g.png", png([[(v,) for v in r] for r in grey], 0, 8))
        tool("import", src, self.dir / "T.PBI", "--threshold", "100")
        self.assertEqual(self.pixels("T.PBI")[0], [1 if v < 100 else 0 for v in grey[0]])
        tool("import", src, self.dir / "I.PBI", "--threshold", "100", "--invert")
        self.assertEqual(self.pixels("I.PBI")[0], [0 if v < 100 else 1 for v in grey[0]])
        for mode in ("ordered", "floyd"):
            tool("import", src, self.dir / "O.PBI", "--dither", mode)
            rows = self.pixels("O.PBI")
            blacks = [sum(r[x] for r in rows) for x in range(16)]
            self.assertEqual(blacks[0], 8)  # black stays black
            self.assertEqual(blacks[-1], 0)  # white stays white
            self.assertTrue(0 < sum(blacks[6:10]) < 32, (mode, blacks))  # mid-grey is mixed
            first = (self.dir / "O.PBI").read_bytes()
            tool("import", src, self.dir / "O.PBI", "--dither", mode)
            self.assertEqual((self.dir / "O.PBI").read_bytes(), first)

    def test_masks(self):
        # a black disc on transparency
        rows = [[((0, 0, 0, 255) if (x - 5) ** 2 + (y - 5) ** 2 <= 16 else (0, 0, 0, 0)) for x in range(11)]
                for y in range(11)]
        src = self.write("d.png", png(rows, 6, 8))
        self.assertEqual(tool("import", src, self.dir / "D.PBI", "--mask", self.dir / "DM.PBI")[0], 0)
        img, mask = self.pixels("D.PBI"), self.pixels("DM.PBI")
        for y in range(11):
            for x in range(11):
                inside = (x - 5) ** 2 + (y - 5) ** 2 <= 16
                self.assertEqual(mask[y][x], 0 if inside else 1)  # white = drawn
                self.assertEqual(img[y][x], 1 if inside else 0)  # transparent over white
        flat = self.write("f.png", png([[(0,), (255,)]], 0, 8))
        code, _, err = tool("import", flat, self.dir / "F.PBI", "--mask", self.dir / "FM.PBI")
        self.assertEqual(code, 1)
        self.assertIn("has no transparency", err)
        tool("import", flat, self.dir / "F.PBI", "--mask", self.dir / "FM.PBI", "--mask-from", "white")
        self.assertEqual(self.pixels("FM.PBI"), [[0, 1]])  # white pixels transparent

    def test_sheet(self):
        # 3 x 2 frames of 8 x 6, frame k has k + 1 black pixels in its top row
        w, h = 24, 12
        grid = [[255] * w for _ in range(h)]
        for k in range(6):
            fx, fy = (k % 3) * 8, (k // 3) * 6
            for i in range(k + 1):
                grid[fy][fx + i] = 0
        src = self.write("s.png", png([[(v,) for v in r] for r in grid], 0, 8))
        code, out, _ = tool("sheet", src, self.dir / "S.PBI", "--frame", "8,6", "--count", "5")
        self.assertEqual(code, 0)
        self.assertIn("frame k is the part 0, k * 6, 8, 6", out)
        rows = self.pixels("S.PBI")
        self.assertEqual((len(rows[0]), len(rows)), (8, 30))
        for k in range(5):
            self.assertEqual(sum(rows[6 * k]), k + 1)
        code, _, err = tool("sheet", src, self.dir / "S.PBI", "--frame", "8,6", "--count", "7")
        self.assertEqual(code, 1)
        self.assertIn("holds 6 frames", err)

    def test_build_from_a_manifest(self):
        bits = checker(16, 8)
        self.write("a.png", png([[(0 if b else 255,) for b in r] for r in bits], 0, 8))
        rgba = [[(0, 0, 0, 255) if (x + y) % 3 else (255, 255, 255, 0) for x in range(16)] for y in range(8)]
        self.write("s.png", png(rgba, 6, 8))
        man = self.write("ASSETS.txt", b"# comment\n\nA.PBI import a.png\n"
                                       b"S.PBI sheet s.png --frame 8,8 --mask SM.PBI  # two frames\n")
        out = self.dir / "out"
        code, _, err = tool("build", man, out)
        self.assertEqual(code, 0, err)
        self.assertEqual(pbicheck.pixels((out / "A.PBI").read_bytes()), bits)
        self.assertEqual(len(pbicheck.pixels((out / "S.PBI").read_bytes())), 16)
        mask = pbicheck.pixels((out / "SM.PBI").read_bytes())
        self.assertEqual(mask[0][:3], [1, 0, 0])  # transparent (alpha 0) is black in a mask: pixel 1
        for line, message in [(b"a.pbi import a.png\n", "not an 8.3 PcW16 name"),
                              (b"A.PBI paint a.png\n", "want TARGET.PBI import|sheet"),
                              (b"A.PBI import none.png\n", "A.PBI was not made"),
                              (b"S.PBI sheet s.png --frame 8,8 --mask sm.pbi\n", "the mask sm.pbi")]:
            with self.subTest(line=line):
                man = self.write("BAD.txt", b"A.PBI import a.png\n" + line)
                code, _, err = tool("build", man, out)
                self.assertEqual(code, 1)
                self.assertIn("BAD.txt:2: ", err)
                self.assertIn(message, err)

    def test_the_project_assets_build(self):
        code, _, err = tool("build", ROOT / "examples" / "assets" / "ASSETS.txt", self.dir / "assets")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.dir / "assets" / "P2ICONS.PBI").exists())

    def test_too_large(self):
        src = self.write("big.png", png([[(255,)] * 600], 0, 8))
        code, _, err = tool("import", src, self.dir / "B.PBI")
        self.assertEqual(code, 1)
        self.assertIn("a BITMAP holds at most 568 x 300 pixels and 16384 bytes", err)
        self.assertFalse((self.dir / "B.PBI").exists())

    def test_export_and_round_trip(self):
        bits = checker(37, 11)
        pbi = self.write("R.PBI", pbicheck.from_rows(bits))
        self.assertEqual(tool("export", pbi, self.dir / "r.png")[0], 0)
        data = (self.dir / "r.png").read_bytes()
        # independent check: a 1-bit greyscale PNG whose bits are the picture (1 = white)
        ihdr = data[16:29]
        self.assertEqual(struct.unpack(">IIBB", ihdr[:10]), (37, 11, 1, 0))
        idat_at = data.index(b"IDAT")
        length = struct.unpack(">I", data[idat_at - 4:idat_at])[0]
        raw = zlib.decompress(data[idat_at + 4:idat_at + 4 + length])
        stride = (37 + 7) // 8
        for y in range(11):
            line = raw[y * (stride + 1):(y + 1) * (stride + 1)]
            self.assertEqual(line[0], 0)
            for x in range(37):
                white = line[1 + x // 8] >> (7 - x % 8) & 1
                self.assertEqual(white, 1 - bits[y][x])
        # and back: the same PBI1 bytes
        tool("import", self.dir / "r.png", self.dir / "R2.PBI")
        self.assertEqual((self.dir / "R2.PBI").read_bytes(), pbi.read_bytes())
        tool("export", pbi, self.dir / "r3.png", "--scale", "3")
        w, h, lum, alpha, _ = pbimage.read_png((self.dir / "r3.png").read_bytes())
        self.assertEqual((w, h), (111, 33))
        self.assertEqual(pbimage.to_bits(lum, alpha)[4][::3], bits[1])

    def test_export_refuses_a_damaged_file(self):
        bad = self.write("X.PBI", pbicheck.from_rows(checker(8, 8))[:-1])
        code, _, err = tool("export", bad, self.dir / "x.png")
        self.assertEqual(code, 1)
        self.assertIn("is not a valid PBI1 file", err)

    def test_info(self):
        p = self.write("i.png", png([[(0, 0, 0, 0)]], 6, 8))
        self.assertIn("PNG, 1 x 1, with transparency", tool("info", p)[1])
        q = self.write("I.PBI", pbicheck.from_rows([[1, 0]]))
        self.assertIn("PBI1, 2 x 1, 1 bytes", tool("info", q)[1])

    def test_m12_pictures_still_read(self):
        # the accepted M12 sample picture: export and import give it back unchanged
        sample = ROOT / "tests" / "fixtures" / "m12" / "SAMPLE.PBI"
        tool("export", sample, self.dir / "s.png")
        tool("import", self.dir / "s.png", self.dir / "S.PBI")
        self.assertEqual((self.dir / "S.PBI").read_bytes(), sample.read_bytes())


if __name__ == "__main__":
    unittest.main()
