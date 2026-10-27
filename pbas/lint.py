"""M11 Stage D4: warnings about programs that build but may fail when run.

These never change a build or stop it; ``tools/build.py`` prints them.

* A dynamic ``LABEL S$`` shows at most 24 characters (M5d); a longer value
  stops the program with "Runtime error: string too long" at the LABEL's
  line. A LABEL whose STRING can hold more than 24 characters is reported,
  because a long value is then possible (KI-63: CONTACTS III's status),
  unless every statement that writes it provably writes at most 24
  characters (a short literal, or LEFT$(..., n) with a literal n <= 24).
"""
from __future__ import annotations

import dataclasses

from . import ast_nodes as ast
from .lower import display_name
from .names import hides_builtin

LABEL_MAX = 24  # pbas/layout.py dynamic label limit (M5d)


def _statements(program):
    """Every statement node of the main line and the procedures, nested ones too."""
    stack = list(program.main) + [s for proc in program.procedures for s in proc.body]
    while stack:
        node = stack.pop()
        yield node
        if dataclasses.is_dataclass(node):
            for f in dataclasses.fields(node):
                value = getattr(node, f.name)
                if isinstance(value, list):
                    stack.extend(v for v in value if isinstance(v, ast.Stmt))


def _short(value) -> bool:
    if isinstance(value, ast.StrLiteral):
        return len(value.value) <= LABEL_MAX
    return (isinstance(value, ast.Call) and value.name == "LEFT$" and len(value.args) == 2
            and isinstance(value.args[1], ast.IntLiteral) and value.args[1].value <= LABEL_MAX)


def _always_short(program, name: str) -> bool:
    """TRUE if every statement that writes *name* writes at most 24 characters."""
    for node in _statements(program):
        if isinstance(node, ast.Assign):
            if node.name == name and not _short(node.value):
                return False
        elif any(getattr(node, attr, None) == name for attr in ("name", "var", "target", "var_name")):
            return False  # another statement that may write it (LINE INPUT, FILELOAD, ...)
    return True


def warnings(program) -> list[tuple[int, int, str]]:
    """(line, column, message) for each finding in a checked program."""
    out = []
    for window in program.windows or []:
        for widget in window.widgets:
            if widget.kind != "LABEL" or widget.var_name is None:
                continue
            var = program.variables.get(widget.var_name)
            if var is None or var.type != "STRING":
                continue
            chars = var.capacity - 1
            if chars > LABEL_MAX and not _always_short(program, widget.var_name):
                out.append((widget.line, widget.column,
                            f"LABEL {widget.var_name} can hold {chars} characters but a LABEL shows "
                            f"at most {LABEL_MAX}; a longer value stops the program with "
                            "\"string too long\" (cut it, e.g. LEFT$(text, 24), or "
                            "use lib/app.pbas AppSay)"))
    for name, var in program.variables.items():  # M14 (D6): DIM in a procedure is global
        proc = getattr(var, "dim_in", None)
        if proc is not None and "%" not in name:
            out.append((var.line, var.column,
                        f"DIM {name} inside {display_name(proc)} declares a variable for the whole "
                        f"program (it keeps its value between calls); use LOCAL {name} AS ... for one "
                        "that belongs to this procedure"))
    for name, var in program.variables.items():  # M14 (D5): a name that hides a built-in
        if "%" in name or not hides_builtin(name):
            continue
        base = name.split(".")[-1]
        if "." in name:
            what = f"inside {display_name(name.split('.')[0])}, {base} means this parameter or LOCAL"
        else:
            what = f"everywhere in the program, {base} means this variable"
        out.append((getattr(var, "line", 1) or 1, getattr(var, "column", 1) or 1,
                    f"{base} is also a built-in function: {what}, not the built-in "
                    "(choose another name to use both)"))
    return out
