"""M10 Stage A: record TYPEs (LANGUAGE-SPEC.md §5.8).

Runs at the start of ``semantics.analyze`` on the lowered flat list
(after ``pbas.lower``, which scopes ``NAME%FIELD`` names of parameters and
LOCALs). The parser spells a field access ``P.Name`` as the name
``P%NAME`` (``People(i).Name`` as an element of ``PEOPLE%NAME``); this pass
makes those names real:

* every ``TYPE`` gets a fixed layout: fields in declaration order, no
  padding; INTEGER 2 bytes (little-endian), BOOLEAN 2 (0 / 1), REAL 5
  (the M7 format), ``STRING * n`` n + 1 bytes (NUL-terminated; the bytes
  after the NUL are zero, so a record's bytes depend only on its values);
* a record variable or array is declared with the record's size, and each
  field becomes an *alias* variable of the field's own type that shares the
  record's storage: ``P%NAME`` at the record's address + offset, or for an
  array, an array with the record size as its stride. Expressions,
  assignments, STRING capacity rules, index checks and BANKED windows then
  work exactly as for ordinary variables (pbas/statements.py emits the
  alias storage);
* a whole-record assignment ``A = B`` (also ``A(i) = B``, ``A = B(j)``,
  ``A(i) = B(j)``, and the parameter copies of ``CALL S(rec)``) between
  records of one TYPE becomes a ``RecordCopy``; a LOCAL record's fresh
  value (pbas.lower) becomes a clearing ``RecordCopy``.

Everything else a record name could appear in is a positioned error.
"""
from __future__ import annotations

from . import ast_nodes as ast
from .errors import SourceError

BASE_TYPES = ('INTEGER', 'REAL', 'BOOLEAN', 'STRING')
FIELD_SIZE = {'INTEGER': 2, 'REAL': 5, 'BOOLEAN': 2}  # BOOLEAN: the 16-bit cell (§1)
RECORD_SIZE_MAX = 512  # policy: copies, windows and files stay small (§5.8)
_NOT_TYPE_NAMES = BASE_TYPES + ('TEXT', 'BITMAP', 'BITMAPREF', '?')  # M12: BITMAP; M13: its parameters


class Layout:
    """A TYPE's fields as (name, type, capacity, offset) and its size."""

    def __init__(self, node: ast.TypeDef):
        self.name = node.name
        self.node = node
        self.fields: dict[str, tuple[str, int | None, int]] = {}
        offset = 0
        for f in node.fields:
            if f.name in self.fields:
                raise SourceError(f.line, f.column, f'duplicate field {f.name} in TYPE {node.name}')
            if f.type_name not in BASE_TYPES:
                raise SourceError(f.line, f.column,
                                  f'field {f.name}: a field is INTEGER, REAL, BOOLEAN or STRING * n'
                                  + (' (records inside records are not supported)'
                                     if f.type_name not in _NOT_TYPE_NAMES else ''))
            if f.name.endswith('$') and f.type_name != 'STRING':
                raise SourceError(f.line, f.column,
                                  f'{f.name} uses $ suffix but is declared {f.type_name}; expected STRING')
            if f.type_name == 'STRING':
                if f.capacity is None:
                    raise SourceError(f.line, f.column,
                                      f'field {f.name}: a STRING field states its length, '
                                      f'{f.name} AS STRING * n (1 to 126)')
                if not 2 <= f.capacity <= 127:
                    raise SourceError(f.line, f.column,
                                      f'STRING * n holds 1 to 126 characters, got {f.capacity - 1}')
                size = f.capacity
            else:
                size = FIELD_SIZE[f.type_name]
            self.fields[f.name] = (f.type_name, f.capacity, offset)
            offset += size
        if not self.fields:
            raise SourceError(node.line, node.column, f'TYPE {node.name} has no fields')
        if offset > RECORD_SIZE_MAX:
            raise SourceError(node.line, node.column,
                              f'TYPE {node.name} is {offset} bytes; a record is at most '
                              f'{RECORD_SIZE_MAX} bytes')
        self.size = offset

    def signature(self) -> str:
        """The canonical field list (the database TYPE check, §5.9)."""
        parts = []
        for name, (typ, cap, _) in self.fields.items():
            code = {'INTEGER': 'I', 'REAL': 'R', 'BOOLEAN': 'B'}.get(typ) or f'S{cap - 1}'
            parts.append(f'{name}:{code}')
        return ';'.join(parts)


def expand(nodes: list) -> list:
    """Return *nodes* with record declarations and whole-record assignments
    expanded (see the module docstring). Programs without TYPE are returned
    unchanged (the same list object's contents)."""
    if not any(isinstance(n, ast.TypeDef) for n in nodes) and not any(
            isinstance(n, ast.Dim) and n.type_name not in _NOT_TYPE_NAMES for n in nodes):
        return nodes
    types: dict[str, Layout] = {}
    for node in nodes:
        if isinstance(node, ast.TypeDef):
            if node.name in types:
                raise SourceError(node.line, node.column,
                                  f'duplicate TYPE {node.name} (first at line {types[node.name].node.line})')
            if node.name in _NOT_TYPE_NAMES or node.name in ('TEXT', 'REAL'):
                raise SourceError(node.line, node.column, f'{node.name} is a built-in type')
            types[node.name] = Layout(node)
    records: dict[str, tuple[Layout, int | None, bool]] = {}  # name -> (type, length, banked)
    out: list = []
    for node in nodes:
        if isinstance(node, ast.TypeDef):
            continue
        if isinstance(node, ast.Dim) and node.type_name not in _NOT_TYPE_NAMES:
            layout = types.get(node.type_name)
            if layout is None:
                known = ', '.join(sorted(types)) or 'none is declared'
                raise SourceError(node.line, node.column,
                                  f'unknown type {node.type_name} (TYPEs: {known})')
            if '%' in node.name:
                raise SourceError(node.line, node.column, 'a field of a field is not supported')
            if node.name.endswith('$'):
                raise SourceError(node.line, node.column,
                                  f'{node.name} uses $ suffix but is a record of TYPE {layout.name}')
            node.record = layout
            records[node.name] = (layout, node.length, node.banked)
            out.append(node)
            for fname, (typ, cap, offset) in layout.fields.items():
                alias = ast.Dim(node.line, node.column, f'{node.name}%{fname}', typ,
                                node.length, cap, node.banked)
                alias.alias = (node.name, offset, layout.size)
                out.append(alias)
            continue
        out.append(node)
    _check(out, records)
    nodes[:] = out
    return nodes


def _record_ref(expr, records):
    """(name, index) if *expr* names a whole record, else None."""
    if isinstance(expr, ast.Var) and expr.name in records:
        return expr.name, None
    if isinstance(expr, (ast.Call, ast.Index)) and expr.name in records:
        args = expr.args if isinstance(expr, ast.Call) else [expr.index]
        return expr.name, args
    return None


def _check(nodes: list, records: dict) -> None:
    def describe(name):
        layout = records[name][0]
        return f'{name} is a record of TYPE {layout.name}'

    def check_name(name, at, indexed):
        """A NAME%FIELD reference or a whole-record name used as a value."""
        if '%' in name:
            base, _, field = name.partition('%')
            if base not in records:
                raise SourceError(at.line, at.column,
                                  f'{base.split(".")[-1]} is not a record, so it has no field {field}')
            layout, length, _ = records[base]
            if field not in layout.fields:
                raise SourceError(at.line, at.column,
                                  f'TYPE {layout.name} has no field {field}; its fields are '
                                  + ', '.join(layout.fields))
            if indexed and length is None:
                raise SourceError(at.line, at.column, f'{base} is a single record, not an array')
            if not indexed and length is not None:
                raise SourceError(at.line, at.column,
                                  f'{base} is an array of records: use {base}(index).{field}')
        elif name in records:
            raise SourceError(at.line, at.column,
                              f'{describe(name)}: use one of its fields ({name}.field), or copy '
                              f'it whole with another record of the same TYPE')

    def walk(value):
        if isinstance(value, ast.Var):
            check_name(value.name, value, False)
        elif isinstance(value, ast.Call):
            if value.name in records or '%' in value.name:
                check_name(value.name, value, True)
            args = value.args
            if value.name in ('DBFIND', 'DBNEXTID') and args and isinstance(args[0], ast.Var) \
                    and args[0].name in records:
                args = args[1:]  # M10: names the database itself (semantics checks it)
            for arg in args:
                walk(arg)
        elif isinstance(value, ast.Index):
            check_name(value.name, value, True)
            walk(value.index)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, ast.Expr):
            for field in vars(value).values():
                walk(field)

    for i, node in enumerate(nodes):
        if isinstance(node, (ast.Assign, ast.AssignIndex)) and node.name in records:
            nodes[i] = _record_assign(node, records, walk)
            continue
        if isinstance(node, (ast.For, ast.LineInput, ast.Textbox, ast.Checkbox)) \
                and getattr(node, 'name', None) in records:
            raise SourceError(node.line, node.column,
                              f'{describe(node.name)}: use one of its fields')
        if isinstance(node, (ast.Assign, ast.AssignIndex, ast.LineInput, ast.For)) \
                and '%' in node.name:
            indexed = isinstance(node, ast.AssignIndex) or getattr(node, 'index', None) is not None
            check_name(node.name, node, indexed)
            if isinstance(node, ast.For):
                raise SourceError(node.line, node.column,
                                  'a FOR counter is a plain INTEGER variable, not a record field')
        if isinstance(node, ast.Dim):
            continue
        for field_name, value in vars(node).items():
            if field_name in ('line', 'column', 'name'):
                continue
            walk(value)


def _record_assign(node, records, walk):
    layout, length, _ = records[node.name]
    index = node.index if isinstance(node, ast.AssignIndex) else None
    if index is None and length is not None:
        raise SourceError(node.line, node.column,
                          f'{node.name} is an array of records: assign one element, {node.name}(i) = …')
    if index is not None and length is None:
        raise SourceError(node.line, node.column, f'{node.name} is a single record, not an array')
    if index is not None:
        walk(index)
    value = node.value
    if getattr(value, 'record_reset', False):  # a LOCAL record's fresh value (pbas.lower)
        return ast.RecordCopy(node.line, node.column, node.name, index, None, None, layout.size)
    ref = _record_ref(value, records)
    if ref is None:
        raise SourceError(value.line, value.column,
                          f'{node.name} is a record of TYPE {layout.name}: assign a record of the '
                          'same TYPE, or set its fields one by one')
    src, args = ref
    src_layout, src_length, _ = records[src]
    if src_layout is not layout:
        raise SourceError(value.line, value.column,
                          f'{src} is a record of TYPE {src_layout.name}, {node.name} of TYPE '
                          f'{layout.name}: a record is copied only from the same TYPE')
    if args is None and src_length is not None:
        raise SourceError(value.line, value.column,
                          f'{src} is an array of records: copy one element, {src}(i)')
    if args is not None and src_length is None:
        raise SourceError(value.line, value.column, f'{src} is a single record, not an array')
    if args is not None and len(args) != 1:
        raise SourceError(value.line, value.column, f'{src} takes one index')
    src_index = args[0] if args is not None else None
    if src_index is not None:
        walk(src_index)
    return ast.RecordCopy(node.line, node.column, node.name, index, src, src_index, layout.size)
