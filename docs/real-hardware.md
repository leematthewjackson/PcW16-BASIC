# Running programs on a real PcW16

**No PcW16 BASIC program has yet been run on a real PcW16.** All the runtime evidence comes from the XAnne emulator ([running-in-xanne.md](running-in-xanne.md)) and from the project's simulator. Nothing in this repository claims that a program works on the hardware. Every step below is **not yet tested on a real PcW16**. It is the procedure for trying, written so that it cannot harm the data on a PcW16.

## What to copy

For each program:
- its `.PRG`, under a DOS 8.3 name in capitals (`build/jumper.prg` becomes `JUMPER.PRG`);
- the files it loads (`.PBI` pictures and data files), named as its opening comment says ([running-in-xanne.md](running-in-xanne.md#which-programs-need-pictures) lists the pictures);
- for a program larger than 16K, the whole `.PRG`. Such a program reads its own code banks from its file when it starts.

[`programs/`](../programs/MANIFEST.md) holds prebuilt programs and their pictures, with their SHA-256 checksums.

## How (not yet tested on a real PcW16)

The PcW16 reads and writes 3.5-inch floppy discs. The programs expect their files in `\PCW\FOLDER01` on the floppy, the folder the PcW16's own File Manager uses, unless they were built with another `--folder`. Programs cannot use the PcW16's internal flash storage: the build refuses `--drive flash`.

1. **Use a floppy kept for testing only.** Format it on the PcW16 itself, so that it has the PcW16's own folders. Do not use a disc that holds your documents.
2. **Copy the files** into that floppy's `PCW/FOLDER01` folder on a computer that can write PC-format 3.5-inch floppies, for example with a USB floppy drive. Whether the PcW16 then reads the disc is part of what this procedure tests. Check the copies against the checksums:
   ```sh
   sha256sum /media/floppy/PCW/FOLDER01/*.PRG
   ```
   (the path depends on where your computer mounts the floppy)
3. **On the PcW16,** insert the floppy, open the File Manager, go to the disc's `\PCW\FOLDER01`, and start the program by name.
4. **Write down the result**, as for XAnne results ([running-in-xanne.md](running-in-xanne.md#when-something-goes-wrong)), marked *real PcW16*, with the Rosanne version shown in the PcW16's Setup.

## Things that may differ from XAnne

These have been measured only in XAnne, and the hardware may behave differently:
- how often `TIMER ... EVERY n TICKS` runs its handler, and how fine `CLOCKTICKS` is ([manual/14-timers-and-animation.md](manual/14-timers-and-animation.md));
- the numbers `KEYDOWN` reports for the keys;
- drawing speed.

## Never

- Never copy a program over a file of the same name that holds your data.
- Never use the PcW16's internal storage, or a disc holding your documents, for a first test.
