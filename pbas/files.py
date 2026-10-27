"""File location and file-name encoding for FILESAVE / FILELOAD (M4).

LANGUAGE-SPEC.md section 7. The drive and folder a program's files live in
are *program data chosen at build time* (``tools/build.py --drive/--folder``),
not runtime constants: the compiler emits them as ``PB_FILE_DEVICE`` and the
``pb_file_path`` string, and the runtime (``runtime/runtime.z80.asm``,
section "Files") passes them to Rosanne before every file operation.

Platform contracts (ROSAN283.DOC, "THE FILING FUNCTIONS"):

- ``os_set_device``: "B ....... 1 = Floppy / 2 = Flash".
- ``os_set_cwd``: "set current working directory (DOS-compatible floppy
  only)"; the path is "0-terminated ... in bottom quarter of memory";
  errors "#03 Path Not Found", "#B7 Invalid name - path contains invalid
  chars", "#BA Too Big - new path exceeds 64 chars"; ``os_get_cwd`` needs a
  buffer of "at least 65 bytes".
- Flash folders are numbers (``os_set_flashfolder``: "B = 0..16") and flash
  files carry a Ranger header; the Ranger "Low-Level Disk Interface"
  document that defines flash names is not in this repository. Flash is
  therefore rejected in M4 (no fabricated capability, AGENTS.md rule 5).

Defaults are the POC's XAnne-proven location: floppy, ``\\PCW\\FOLDER01``
(``POC/NOTES.asm`` ``pb_path``; POC README-v0.5.1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DRIVE_FLOPPY = "floppy"
DRIVE_DEVICE = {DRIVE_FLOPPY: 1}  # os_set_device: 1 = Floppy
DEFAULT_DRIVE = DRIVE_FLOPPY
DEFAULT_FOLDER = "\\PCW\\FOLDER01"
FOLDER_MAX = 63  # spec section 7: path <= 63 bytes ("exceeds 64 chars" is #BA)

_COMPONENT_RE = re.compile(r"[A-Z0-9_]{1,8}(\.[A-Z0-9_]{1,3})?")
# DOS reserved device names: a file with one of these names is a device on
# DOS-compatible systems. Not documented for Rosanne either way, so they are
# refused rather than risk writing to a device (policy).
RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL", "CLOCK$"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)


class FileLocationError(ValueError):
    """An invalid --drive / --folder value (a build option, not source)."""


@dataclass(frozen=True)
class FileLocation:
    """Where a program's FILESAVE / FILELOAD files live."""

    drive: str = DEFAULT_DRIVE
    folder: str = DEFAULT_FOLDER

    @property
    def device(self) -> int:
        return DRIVE_DEVICE[self.drive]


def make_location(drive: str = DEFAULT_DRIVE, folder: str = DEFAULT_FOLDER) -> FileLocation:
    """Validate and normalise build options into a FileLocation."""
    drive = drive.lower()
    if drive == "flash":
        raise FileLocationError(
            "--drive=flash is not supported: Rosanne's flash folders are "
            "numbered and their file naming is not documented in the material "
            "the project has; use --drive=floppy (the default)"
        )
    if drive not in DRIVE_DEVICE:
        raise FileLocationError(f"--drive must be 'floppy', not {drive!r}")
    return FileLocation(drive, normalise_folder(folder))


def normalise_folder(folder: str) -> str:
    """Upper-case and check an absolute DOS folder path such as ``\\PCW\\FOLDER01``.

    ``\\`` alone is the root. Each component is a DOS 8.3 name of letters,
    digits and ``_``; ``/`` is accepted as a separator and converted. The
    folder must already exist on the disk: the runtime never creates it.
    """
    path = folder.replace("/", "\\").upper()
    if not path.startswith("\\"):
        raise FileLocationError(f"--folder must be an absolute path starting with \\, not {folder!r}")
    if path != "\\":
        path = path.rstrip("\\")
        for part in path[1:].split("\\"):
            if _COMPONENT_RE.fullmatch(part) is None:
                raise FileLocationError(
                    f"--folder component {part!r} is not a DOS 8.3 name "
                    "(letters, digits and _; at most 8.3 characters)"
                )
    if len(path) > FOLDER_MAX:
        raise FileLocationError(f"--folder path is {len(path)} characters; at most {FOLDER_MAX}")
    return path


def split_filename(name: str) -> tuple[str, str]:
    """``"note.txt"`` -> (``"NOTE"``, ``".TXT"``): the os_open_file arguments.

    ROSAN283 os_open_file: "HL = ... 0-terminated filename", "DE = ...
    0-terminated extension (incl .)". Names are matched case-insensitively
    by DOS and stored upper-case, so the compiler upper-cases them; the name
    has already passed the spec's 8.3 pattern in semantics.
    """
    stem, ext = name.upper().split(".")
    return stem, "." + ext


def descriptor_bytes(name: str) -> bytes:
    """Runtime file descriptor: stem NUL, extension (with dot) NUL."""
    stem, ext = split_filename(name)
    return stem.encode("ascii") + b"\0" + ext.encode("ascii") + b"\0"
