"""Z80 assembly emitter for the M2 code generator.

:class:`AsmWriter` accumulates output lines in the POC-proven style of
``POC/NOTES.asm`` (instructions indented by 4 spaces, labels at column 0),
allocates unique labels, owns the string-literal pool (NUL-terminated byte
strings referenced by generated code), and annotates statements with the
``.pbas`` source line they came from, for ASM review.

Symbol names never contain a raw ``$`` (TESTING-STRATEGY.md rule A7): BASIC
names are mapped through :func:`mangle` at symbol-emission time, replacing the
POC's whole-file ``re.sub`` post-pass (ARCHITECTURE.md D8). Since M2.1 the
mapping is injective, so two BASIC names can never collide in the assembly.
"""
from __future__ import annotations


def mangle(name: str) -> str:
    """Map a BASIC name to its assembly symbol, injectively (M2.1, D5).

    BASIC names match ``[A-Z_][A-Z0-9_]*$?`` (upper-cased by the parser).
    Every ``_`` is doubled and the trailing ``$`` becomes ``_S``. Because
    every original underscore is doubled, a single ``_`` followed by ``S`` can
    only have come from ``$``, so the encoding decodes uniquely and distinct
    names never share a symbol (the M2 scheme mapped both ``A$`` and
    ``A_STR`` to ``A_STR``). Output uses only ``[A-Z0-9_]``; callers add the
    ``var_``/``sub_`` namespace prefix.
    """
    base, dollar = (name[:-1], "_S") if name.endswith("$") else (name, "")
    # M7: compiler names of parameters, locals, results and temporaries
    # contain '.', which no BASIC name can; it becomes "_D" (a single '_'
    # before D, so it cannot come from a doubled user underscore).
    # M10: a record field NAME%FIELD has '%' (no BASIC name can): "_P".
    base = base.upper().replace("_", "__").replace(".", "_D").replace("$", "_S").replace("%", "_P")
    return base + dollar


class AsmWriter:
    """Accumulates program-portion assembly text."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self._uid = 0
        self._pool: list[tuple[str, bytes]] = []

    def emit(self, *lines: str) -> None:
        """Append instruction/label/comment lines verbatim."""
        self.lines.extend(lines)

    def annotate(self, line: int) -> None:
        """Record the .pbas source line the following statement came from."""
        self.lines.append(f"; .pbas line {line}")

    def new_label(self, prefix: str) -> str:
        """Allocate a unique label ``prefix_N`` (column-0 definition)."""
        self._uid += 1
        return f"{prefix}_{self._uid}"

    def pool_label(self, text: str) -> str:
        """Intern *text* in the literal pool; the returned label addresses the
        NUL-terminated UTF-8 bytes. Identical texts share one entry."""
        data = text.encode("utf-8") + b"\0"
        for label, existing in self._pool:
            if existing == data:
                return label
        label = self.new_label("lit")
        self._pool.append((label, data))
        return label

    def pool_items(self) -> list[tuple[str, bytes]]:
        """Literal-pool entries as (label, bytes-incl-NUL), in interning order."""
        return list(self._pool)

    def render(self) -> str:
        """Return the accumulated text, newline-terminated."""
        return "\n".join(self.lines) + "\n"
