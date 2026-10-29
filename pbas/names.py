"""M14: names and the built-in functions (LANGUAGE-SPEC §4, "Names").

Before M14 a FUNCTION could have the name of a built-in function, and the
compiler silently used one or the other: ``FUNCTION Min`` made every
``MIN(1, 2)`` call the program's function, while ``FUNCTION Pi()`` was
silently ignored in favour of the built-in ``PI``. Both are called with the
same syntax, so the program cannot say which it means: a FUNCTION with a
built-in's name is a compile error now.

Other names are unambiguous and keep working as they did (accepted programs
rely on them): a variable, CONST, parameter or LOCAL named like a built-in
that takes arguments (``Max``, ``Len``) is used without parentheses and the
built-in with them. A name that equals a built-in without arguments
(``SECONDS``, ``PI``) hides the built-in where the name is visible, as it
always has (STOPWATCH's ``DIM Seconds``); tools/build.py warns about it
(pbas/lint.py). A SUB may have a statement word's name (PAINT's ``SUB Show``),
and is called with CALL.
"""
from __future__ import annotations

from .errors import SourceError

#: built-in functions written without arguments: a variable of the same name hides them
NO_ARGUMENT_BUILTINS = frozenset({"PI", "SECONDS", "CLOCKTICKS", "IOERR", "MOUSEX", "MOUSEY",
                                  "MOUSEEVENT", "KEYCODE", "KEYSHIFT", "DBRECOVERED",
                                  "TYPEHEIGHT"})  # M15


def builtin_names() -> frozenset[str]:
    from .semantics import _BUILTINS  # imported late: semantics imports the parser
    return frozenset(_BUILTINS)


def check_function_name(name: str, line: int, column: int) -> None:
    """Refuse a FUNCTION with the name of a built-in function."""
    base = name.upper()
    if base in builtin_names():
        raise SourceError(line, column,
                          f"{base} is a built-in function, so a FUNCTION cannot have that name "
                          "(names do not depend on upper or lower case): choose another name")


def hides_builtin(name: str) -> bool:
    """True if a variable, CONST, parameter or LOCAL called *name* hides a built-in."""
    return name.upper().split(".")[-1] in NO_ARGUMENT_BUILTINS
