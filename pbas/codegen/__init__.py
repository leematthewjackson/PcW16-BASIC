"""Code-generator package: compatibility re-export of the flat M2 modules.

ARCHITECTURE.md section 3 draws the code generator under ``codegen/``
(``emit.py`` / ``statements.py`` / ``prg.py``), but the package is kept flat
like M1, so the implementations live directly in ``pbas/emit.py``,
``pbas/statements.py`` and ``pbas/prg.py``. This shim keeps the documented
import path working; new generator modules are added flat alongside these.
"""
from __future__ import annotations

from ..emit import AsmWriter, mangle
from ..prg import PRG_IMAGE_MAX, PREFIX_SIZE, BuildReport, assemble, build
from ..statements import generate

__all__ = [
    "AsmWriter",
    "BuildReport",
    "PRG_IMAGE_MAX",
    "PREFIX_SIZE",
    "assemble",
    "build",
    "generate",
    "mangle",
]
