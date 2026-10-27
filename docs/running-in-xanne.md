# Running programs in XAnne

XAnne is the PcW16 part of John Elliott's JOYCE emulator. Every runtime result this project reports as *Tested in XAnne* came from the project owner's own XAnne set-up, running Rosanne 1.12. This page describes that set-up and the route the owner used to copy and start programs. Each step is marked:
- **(used by the owner)**: what the owner did in the recorded XAnne sessions;
- **(suggested)**: advice that follows from how the programs work, which no recorded session has needed.

Nothing here has been tried on a real PcW16. [real-hardware.md](real-hardware.md) covers that.

## What you need

- **XAnne, set up with your own PcW16 system software.** XAnne runs Rosanne, the PcW16's operating system. This repository does not include Rosanne, its fonts, a ROM image or a rescue disk, and none is needed to build programs. Use the system software from your own PcW16, as JOYCE's documentation describes. Only Rosanne 1.12 has been tested.
- Programs built with `pcw16basic build` ([first-program.md](first-program.md)), or the prebuilt ones in [`programs/`](../programs/MANIFEST.md).

## XAnne settings

- **Rosanne acceleration: do not select Graphics (used by the owner).** With Graphics acceleration on, the owner saw typing lag and slow drawing, wrong in places. Every result since then was recorded with Graphics acceleration **off**.
- **Floppy filesystem acceleration on (used by the owner).** A folder on your computer then acts as the PcW16's floppy disc. In the owner's set-up that folder is `~/Joyce/PcW16FS`, and its `PCW/FOLDER01` subfolder is the PcW16's `\PCW\FOLDER01`. Your set-up may use another folder. Use whichever one your XAnne shows as the floppy.

## Where the files go

A program looks for its files in one folder, fixed when it is built. That folder is `\PCW\FOLDER01` on the floppy unless the program was built with `--folder` ([manual/16-building-and-commands.md](manual/16-building-and-commands.md)). The program never creates the folder. `\PCW\FOLDER01` is the folder the PcW16's own File Manager uses, so it is normally there already.

Put these three things in that folder:
- **the `.PRG`**, under a DOS 8.3 name in capitals: `build/jumper.prg` becomes `JUMPER.PRG`, and `build/t1_hello.prg` becomes `T1HELLO.PRG`;
- **the pictures it loads**, the `.PBI` files, under the exact names the program uses;
- **any data files it reads**, named as its opening comment says.

A program larger than 16K is split into code banks, which it reads from its own `.PRG` file when it starts. Copy such a file whole. Run it from the folder you copied it to, under the name you gave it, and do not rename it while it runs.

### Which programs need pictures

| program | pictures it loads | what happens without them |
|---|---|---|
| T1HELLO (Tutorial 1) | none | — |
| T2DRAW (Tutorial 2) | `T2ICONS.PBI` | the status line says `T2ICONS.PBI is missing`, and the icons are missing |
| T3HOP (Tutorial 3) | `T3HERO.PBI`, `T3HEROM.PBI` | no message: the program does not check, and the figure is missing or wrong |
| JUMPER | `JHERO.PBI`, `JHEROM.PBI`, `JBUG.PBI`, `JBUGM.PBI`, `JCOIN.PBI`, `JCOINM.PBI` | the game says which file is missing |
| PAINT II | `P2ICONS.PBI` | it works, with letters in place of icons |
| DESIGNER | `P2ICONS.PBI` | it works, with framed `?` marks in place of icons |

Every `.PBI` above is in [`programs/`](../programs/MANIFEST.md), and the same files can be rebuilt from `examples/assets/`:

```sh
python3 pcw16basic assets examples/assets/ASSETS.txt build/assets
```

[graphics-assets.md](graphics-assets.md) shows how to make your own.

## Running a program

1. **Protect your files first (used by the owner).** Before the owner tested programs that write files, the whole XAnne disc folder was backed up, and a checksum was recorded of each file in the folder:
   ```sh
   cp -a ~/Joyce/PcW16FS ~/PcW16FS-backup-$(date +%Y%m%d-%H%M)
   cd ~/Joyce/PcW16FS/PCW/FOLDER01 && sha256sum * > ~/folder01-before.sha256
   ```
   Restoring means copying the backup back. A floppy folder kept only for testing is safer still.
2. **Check what you copy (used by the owner).** For a prebuilt program, compare its checksum with [`programs/MANIFEST.md`](../programs/MANIFEST.md):
   ```sh
   sha256sum programs/JUMPER.PRG
   ```
3. **Copy the program and its pictures into the folder (used by the owner):**
   ```sh
   cp build/t3_hop.prg ~/Joyce/PcW16FS/PCW/FOLDER01/T3HOP.PRG
   cp programs/T3HERO.PBI programs/T3HEROM.PBI ~/Joyce/PcW16FS/PCW/FOLDER01/
   ```
4. **In XAnne (used by the owner):** refresh the disc view with **Ctrl+L**, open the File Manager, go to `\PCW\FOLDER01`, and start the program by name. Refresh again with Ctrl+L whenever you have changed files on the computer's side.
5. **When it ends,** the program removes its window and you are back in the File Manager. A program that only shows `MESSAGE` alerts ends after the last one.

Files that a program saves appear in the same folder on your computer. `tools/pbicheck.py` checks a saved picture, and `tools/pdbcheck.py` checks a database file. `python3 pcw16basic image export NAME.PBI out.png` turns a picture into a PNG you can look at.

## Never overwrite your own data

- Read a program's opening comment before you run it for the first time. Each example's comment names the files it writes. Many examples write none: the three tutorials and JUMPER write nothing.
- Some examples **replace** files of fixed names in their folder, for example `JOURNAL.TXT` and `CONTACTS.DAT`. If you keep a file of that name in the folder, move it away first, or use a test folder.
- `cp` replaces a file of the same name without asking. When you copy something into a folder that holds your own files, copy only names that are not there yet. The owner's first file tests used a loop like this one (used by the owner):
  ```sh
  D=~/Joyce/PcW16FS/PCW/FOLDER01
  for f in T3HOP.PRG T3HERO.PBI T3HEROM.PBI; do
    if [ -e "$D/$f" ]; then echo "EXISTS, not copied: $f"; else cp "programs/$f" "$D/$f" && echo "copied $f"; fi
  done
  ```

## Rebuilding and replacing a program

After you change a program, rebuild it and copy the new `.PRG` over the old one, under the same name:

```sh
python3 pcw16basic build examples/tutorial/t3_hop.pbas
cp build/t3_hop.prg ~/Joyce/PcW16FS/PCW/FOLDER01/T3HOP.PRG
```

Then press Ctrl+L in XAnne and start it again. Replacing a program of the same name was the owner's route for each retest, which used a fresh build: "copy them over the programs of the same names" (used by the owner). Pictures only need copying again if you remade them.

Replace only a `.PRG` that you built yourself. Make sure the name is not also used by a program or a document of yours.

## When something goes wrong

- **An alert `Runtime error: ... at line N`.** The program found a problem, named the line, and ended cleanly. [troubleshooting.md](troubleshooting.md) and [manual/09-errors-and-diagnostics.md](manual/09-errors-and-diagnostics.md) explain the messages.
- **The program is not in the File Manager.** Refresh with Ctrl+L, and check that the file is in the folder XAnne uses as `\PCW\FOLDER01`, under an 8.3 name.
- **Anything else** is worth reporting: a freeze, a wrong picture, screen corruption, or behaviour that differs from what a document says. Give the program, its SHA-256, what you did, and your XAnne settings (the Rosanne version and the acceleration options). [../CONTRIBUTING.md](../CONTRIBUTING.md) says where to report it.

What has been tested in XAnne, and what has not, is listed per program in [`programs/MANIFEST.md`](../programs/MANIFEST.md), [../examples/README.md](../examples/README.md) and [limitations.md](limitations.md).
