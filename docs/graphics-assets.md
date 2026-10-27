# Making pictures: PNG to PBI

Pictures for a PcW16 BASIC program (icons, sprites, backgrounds) are drawn on a PC in any paint
program that saves PNG, converted to the PBI1 picture format with `tools/pbimage.py`, and copied
to the PcW16 next to the program. The program loads them with `BITMAP LOAD`
([manual chapter 13](manual/13-bitmaps-and-sprites.md)). The PcW16 never reads PNG.

*Evidence:* the converter is tested on the PC by the project's tests (every PNG colour type and
bit depth, interlacing, damaged files), and its output is loaded by the simulator. The pictures
of `examples/paint2.pbas`, `examples/designer.pbas` and `examples/jumper.pbas`, made this way,
were loaded and drawn in XAnne by the owner. Not yet tested on a real PcW16.

Contents: [Drawing conventions](#drawing-conventions) · [The commands](#the-commands) ·
[Options](#options) · [Sheets of frames](#sheets-of-frames) · [Masks](#masks) ·
[Manifests and pcw16basic assets](#manifests-and-pcw16basic-assets) ·
[Sizes and limits](#sizes-and-limits) · [Loading pictures in a program](#loading-pictures-in-a-program) ·
[Copying pictures with the program](#copying-pictures-with-the-program) ·
[Checking a picture](#checking-a-picture) · [The project's own pictures](#the-projects-own-pictures)

## Drawing conventions

- **One PNG pixel is one screen pixel.** Draw at the size the program uses; the PcW16 has no
  scaling.
- **Black and white.** The screen has one bit a pixel. Pure black and white drawings convert
  exactly. Grey and colour are reduced to black and white by a threshold, or by dithering for
  shaded pictures (below).
- **Transparency** (a PNG with an alpha channel) is mixed over white by default, and can be
  turned into a mask for `BITMAP MASK`.
- **Frames side by side or in a grid.** For an animation or a set of icons, draw the frames on
  a regular grid in one PNG (for example 8 frames of 16 × 24 in a 128 × 24 PNG). `sheet` turns
  the grid into the strip the libraries expect.
- Any PNG works: every colour type and bit depth, interlaced or not.

## The commands

```sh
python3 tools/pbimage.py import PICTURE.png PICTURE.PBI [options]
python3 tools/pbimage.py sheet  FRAMES.png  STRIP.PBI --frame W,H [--count N] [options]
python3 tools/pbimage.py export PICTURE.PBI picture.png [--scale N]
python3 tools/pbimage.py info   FILE.png|FILE.PBI
python3 tools/pbimage.py build  MANIFEST.txt OUTDIR
```

`pcw16basic image …` is the same command, and `pcw16basic assets` runs `build`
([chapter 16](manual/16-building-and-commands.md#pcw16basic-assets-and-pcw16basic-image)). For a
subcommand's options use `python3 tools/pbimage.py import --help` (not `pcw16basic image import
--help`, which fails). Exit status: 0 done, 1 an error (the message says why), 2 a usage
mistake. The same PNG and options always give the same bytes.

- **import** converts one picture.
- **sheet** converts a grid of frames into a strip (below).
- **export** writes a PBI1 file back as a PNG, enlarged `--scale` times, so that you can look
  at the result on the PC.
- **info** describes a PNG or PBI1 file.
- **build** makes every picture a manifest lists.

```text
$ python3 tools/pbimage.py info examples/assets/jumper-hero.png
examples/assets/jumper-hero.png: PNG, 128 x 24, with transparency
$ python3 tools/pbimage.py import examples/assets/tutorial-icons.png ICONS.PBI
ICONS.PBI: 48 x 24, 144 bytes
$ python3 tools/pbimage.py export ICONS.PBI icons-x4.png --scale 4
icons-x4.png: 192 x 96
```

## Options

For `import` and `sheet`, applied in this order:

| Option | Does | Default |
|---|---|---|
| `--crop X,Y,W,H` | keep that rectangle of the PNG (`import` only) | the whole picture |
| `--size W,H` | scale to W × H by averaging (`import` only) | no scaling |
| `--background white\|black` | what transparent pixels are mixed over | white |
| `--threshold N` | a pixel darker than N (0 to 255) becomes black | 128 |
| `--dither none\|ordered\|floyd` | for photographs and shading: a 4 × 4 ordered pattern, or Floyd–Steinberg error diffusion | none |
| `--invert` | swap black and white | — |
| `--mask FILE.PBI` | also write a mask for `BITMAP MASK` (below) | no mask |
| `--mask-from alpha\|white\|black` | the mask from the PNG's transparency, or treat the picture's white (or black) pixels as transparent | alpha |
| `--alpha-threshold N` | alpha of N or more counts as opaque | 128 |

Errors name the problem:

```text
$ python3 tools/pbimage.py import jumper-coin.png COIN.PBI --crop 0,0,80,8
pbimage.py: --crop 0,0,80,8 is not inside the 16 x 8 image
$ python3 tools/pbimage.py sheet jumper-hero.png H.PBI --frame 16,25
pbimage.py: --frame 16,25 does not fit the 128 x 24 image
```

## Sheets of frames

`sheet` reads the PNG as a grid of W × H frames, left to right and top to bottom, and writes
them **one under another** as a strip W pixels wide. `--count N` keeps only the first N frames.
Frame k (0 for the first) is then the part `0, k * H, W, H` of the bitmap:

```text
$ python3 tools/pbimage.py sheet examples/assets/jumper-hero.png HERO.PBI --frame 16,24 --mask HEROM.PBI
HERO.PBI: 8 frames of 16 x 24, a 16 x 192 strip; frame k is the part 0, k * 24, 16, 24
HEROM.PBI: the mask strip
```

The vertical strip is the layout `BITMAP PUT` and `BITMAP MASK` draw fastest (a part as wide as
the bitmap is drawn straight from it), and the one `lib/sprite.pbas` and `lib/toolbar.pbas`
expect. Square icons for `lib/toolbar.pbas` are a sheet too (`--frame 24,24`).

## Masks

`--mask FILE.PBI` writes a second picture of the same size: **white where the picture is drawn,
black where it is transparent**. That is the convention of `BITMAP MASK Image, Mask, x, y`.
By default the mask comes from the PNG's transparency (`--mask-from alpha`); for a PNG without
transparency, `--mask-from white` treats the picture's white pixels as transparent.

## Manifests and pcw16basic assets

A manifest lists every picture a program needs, one per line, so that one command remakes them
all:

```text
# target       command  source              options
P2ICONS.PBI    sheet    paint2-icons.png    --frame 24,24
JHERO.PBI      sheet    jumper-hero.png     --frame 16,24 --mask JHEROM.PBI
```

- `#` starts a comment.
- The target must be a PcW16 file name: at most 8 letters or digits, `.PBI`, in **capitals**.
- The source is relative to the manifest's folder; targets and `--mask` files are written to
  OUTDIR.
- It stops at the first line that fails and names it:

```text
$ python3 tools/pbimage.py build mf/A.txt mfout
pbimage.py: mf/A.txt:1: coin.pbi is not an 8.3 PcW16 name in capitals ending .PBI
```

A project made by `pcw16basic new` has an empty `assets/ASSETS.txt`. Put your PNG files in
`assets/`, add a line for each, and run, in the project folder:

```sh
pcw16basic assets
```

which uses `assets/ASSETS.txt` and writes to `build`, next to the program's `.prg`. (In a folder
without `assets/ASSETS.txt` it builds the examples' pictures instead.) Give the manifest and the
output folder to choose others: `pcw16basic assets assets/ASSETS.txt build`.

## Sizes and limits

A picture must fit one BITMAP: at most 568 × 300 pixels **and** at most 16384 bytes, where the
bytes are (width + 7) \ 8 × height. A full-width picture is therefore at most 568 × 230. A
result that is too large is refused, never cut:

```text
$ python3 tools/pbimage.py import paint2-icons.png BIG.PBI --size 600,10
pbimage.py: --size would be 600 x 10 pixels (750 bytes); a BITMAP holds at most 568 x 300
pixels and 16384 bytes: use --size, --crop or fewer frames
```

For a sheet the limit applies to the whole strip, so many tall frames may need two sheets.
The program's `DIM … AS BITMAP * w, h` must be at least as large in bytes as the file
(otherwise `BITMAP LOAD` sets `IOERR` 252). Each bitmap uses a 16K block of the PcW16's memory,
outside the resident 16K ([memory](memory.md)).

## Loading pictures in a program

Declare a bitmap at least the picture's size (use `info` to see it), load it in the main line,
and check `IOERR` before you draw it:

```pbas
INCLUDE "lib/geom.pbas"
INCLUDE "lib/sprite.pbas"

DIM Hero AS BITMAP * 16, 192
DIM HeroM AS BITMAP * 16, 192
DIM Back AS BITMAP * 200, 80
DIM Ready AS BOOLEAN
DIM Loaded AS BOOLEAN

WINDOW "Hero"
CANVAS 200, 80, PAINT Paint
BUTTON "Next frame", NextFrame, DEFAULT
BUTTON "Quit", Quit

SUB Paint
    IF NOT Ready THEN
        DRAW CLEAR
        DRAW FILL 0, 64, 200, 16, 4
        BITMAP GET Back, 0, 0
        Ready = TRUE
    END IF
    BITMAP PUT Back, 0, 0
    IF Loaded THEN
        CALL SpriteShow(Hero, HeroM, 1)
    ELSE
        DRAW TEXT 4, 4, "JHERO.PBI is missing"
    END IF
END SUB

SUB NextFrame
    IF Loaded THEN
        CALL SpriteMove(Hero, HeroM, Back, 1, SprX(1), SprY(1), (SprF(1) + 1) MOD 8)
    END IF
END SUB

SUB Quit
    EXIT
END SUB

SprCW = 200
SprCH = 80
SprW(1) = 16
SprH(1) = 24
SprX(1) = 92
SprY(1) = 40
BITMAP LOAD Hero, "JHERO.PBI"
Loaded = IOERR = 0
IF Loaded THEN
    BITMAP LOAD HeroM, "JHEROM.PBI"
    Loaded = IOERR = 0
END IF
END
```

`JHERO.PBI` and `JHEROM.PBI` are made by `pcw16basic assets` from
`examples/assets/jumper-hero.png`. A program should work, or say clearly what is missing, when a
picture is absent, as this one does and as `examples/paint2.pbas` (letters instead of icons)
and `examples/jumper.pbas` (it names the missing file) do.

## Copying pictures with the program

**How a program finds its pictures at run time.** `BITMAP LOAD` takes a bare file name. The
program looks for it in the folder it was built for: `\PCW\FOLDER01` on the floppy, unless you
built with `--folder` ([chapter 16](manual/16-building-and-commands.md#toolsbuildpy-options)).
There is no search path and no other drive. So:

1. build the program and its pictures (`pcw16basic build NAME.pbas`, `pcw16basic assets`);
2. copy `build/NAME.prg` as `NAME.PRG` **and every `.PBI` file it loads** into that folder,
   on the disk the PcW16 (or XAnne) uses;
3. start the program from there.

Which example programs need which pictures:

| Program | Pictures |
|---|---|
| `examples/paint2.pbas` | `P2ICONS.PBI` (works without it, with letters instead of icons) |
| `examples/designer.pbas` | `P2ICONS.PBI` (a framed `?` without it) |
| `examples/jumper.pbas` | `JHERO.PBI`, `JHEROM.PBI`, `JBUG.PBI`, `JBUGM.PBI`, `JCOIN.PBI`, `JCOINM.PBI` |
| `examples/tutorial/t2_draw.pbas` | `T2ICONS.PBI` |
| `examples/tutorial/t3_hop.pbas` | `T3HERO.PBI`, `T3HEROM.PBI` |

The `programs/` folder holds prebuilt copies of some of these with their pictures
(`programs/MANIFEST.md`). Copying files to XAnne is described in
[Running in XAnne](running-in-xanne.md), and to a real machine in
[real hardware](real-hardware.md).

## Checking a picture

```sh
python3 tools/pbimage.py info HERO.PBI
python3 tools/pbimage.py export HERO.PBI check.png --scale 4
python3 tools/pbicheck.py HERO.PBI
```

```text
HERO.PBI: PBI1, 16 x 192, 384 bytes
...
result: valid
```

`tools/pbicheck.py` is an independent reader of the format (it also checks pictures your program
saved with `BITMAP SAVE`, and converts to and from PBM: see
[chapter 16](manual/16-building-and-commands.md#toolspbicheckpy)).

## The project's own pictures

The PNG sources of the example programs' pictures are in `examples/assets/`, listed in
`examples/assets/ASSETS.txt`:

```text
P2ICONS.PBI    sheet    paint2-icons.png    --frame 24,24
JHERO.PBI      sheet    jumper-hero.png     --frame 16,24 --mask JHEROM.PBI
JCOIN.PBI      sheet    jumper-coin.png     --frame 8,8 --mask JCOINM.PBI
JBUG.PBI       sheet    jumper-beetle.png   --frame 16,12 --mask JBUGM.PBI
T2ICONS.PBI    sheet    tutorial-icons.png  --frame 24,24
T3HERO.PBI     sheet    tutorial-hero.png   --frame 16,16 --mask T3HEROM.PBI
```

Build them all with:

```sh
python3 tools/pbimage.py build examples/assets/ASSETS.txt build/assets
```

They were drawn for this project, pixel by pixel, and are covered by its licence
([LICENSING](../LICENSING.md)); no Rosanne graphics, fonts or ROM images are used.

The jumper's hero is `examples/assets/jumper-hero.png`. (An older engineering note gave the
name as `hero.png`; there is no such file, and the command
`pbimage.py sheet examples/assets/hero.png …` fails with `No such file or directory`.)

**See also.** [manual chapter 13](manual/13-bitmaps-and-sprites.md) (BITMAP statements, masks,
sprites), [libraries](libraries/README.md) (`sprite`, `toolbar`), spec
[§5.12](../LANGUAGE-SPEC.md#512-m12--bitmaps-and-point) and
[§5.14](../LANGUAGE-SPEC.md#514-m13--parts-of-bitmaps-masks-and-bitmap-parameters).
