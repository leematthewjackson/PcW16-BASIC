"""M7 lowering: procedures with parameters, FUNCTION, LOCAL, CONST and
SELECT CASE are rewritten into statements the compiler already compiles
(LANGUAGE-SPEC.md §5.3).

The pass runs on the flat parser output, before ``validate``:

* ``CONST N = literal`` — every later use of ``N`` becomes a copy of the
  literal; the CONST statement disappears. Assigning to or declaring ``N`` is
  an error.
* ``SUB S(a AS T, ...)`` / ``FUNCTION F(...) AS T`` — each parameter, each
  ``LOCAL`` and a FUNCTION's result become globals with compiler names
  (``S.A``, ``F..R``) that a program cannot spell, so they never collide with
  its own names. Procedures therefore use static storage: recursion stays a
  compile error (validate's call-graph check sees the lowered CALLs).
* ``CALL S(x, y)`` — ``S.A = x``, ``S.B = y``, then ``CALL S``. Arguments are
  assigned in order; they are caller-scope expressions, and with recursion
  impossible they cannot read the callee's own parameters.
* a FUNCTION call inside an expression is evaluated *before* the statement
  that contains it, in source order (innermost first), into a temporary
  (``..T1``…). A call in the right operand of AND/OR is a compile error,
  because evaluating it first would defeat short-circuit evaluation. A
  WHILE condition's calls are evaluated before the WHILE and again before
  its WEND, so they are fresh on every test.
* ``RETURN e`` — ``F..R = e`` and ``EXIT SUB``; ``END FUNCTION`` ends the
  body like ``END SUB``. The result starts at 0 / "" / FALSE / 0.0 on each
  call, so falling off the end returns that value.
* ``LOCAL x AS T`` — a variable of the procedure, reset to its type's
  initial value each time the procedure starts.
* ``SELECT CASE e`` — ``..Sn = e`` once, then one IF per CASE guarded by a
  "matched" flag, so exactly one CASE body (or CASE ELSE) runs.
"""
from __future__ import annotations

import copy

from . import ast_nodes as ast
from .errors import SourceError
from .names import check_function_name, hides_builtin

RESULT = '..R'  # suffix of a FUNCTION's result variable
_EXPR_FIELDS = ('value', 'condition', 'start', 'finish', 'step', 'index', 'title', 'text',
                'filename', 'count', 'caption', 'new_name')
_HANDLER_NODES = (ast.Button, ast.Item, ast.Timer, ast.ListCtl, ast.Slider, ast.Canvas)
# statements whose `name` is a variable they write
_RENAMED = (ast.Assign, ast.AssignIndex, ast.For, ast.LineInput)


def display_name(name: str) -> str:
    """How a compiler-named variable appears in messages."""
    if '%' in name:  # M10: a record field, NAME%FIELD
        base, _, field = name.partition('%')
        return f'{field} of {display_name(base)}' if '.' in base else f'{base}.{field}'
    if name.endswith(RESULT):
        return f'the result of FUNCTION {name[:-len(RESULT)]}'
    if name.startswith('..'):
        return 'a temporary value'
    if '.' in name:
        proc, _, local = name.partition('.')
        return f'{local} (in {proc})'
    return name


def _default(type_name: str, line: int, column: int) -> ast.Expr:
    if type_name not in ('STRING', 'BOOLEAN', 'REAL', 'INTEGER', '?'):
        # M10: a record TYPE; pbas/records.py turns `x = <this>` into a clear
        value = ast.IntLiteral(line, column, 0)
        value.record_reset = True
        return value
    if type_name == 'STRING':
        return ast.StrLiteral(line, column, '')
    if type_name == 'BOOLEAN':
        return ast.BoolLiteral(line, column, False)
    if type_name == 'REAL':
        return ast.RealLiteral(line, column, 0.0)
    return ast.IntLiteral(line, column, 0)


def _is_literal(expr) -> bool:
    if isinstance(expr, (ast.IntLiteral, ast.StrLiteral, ast.BoolLiteral, ast.RealLiteral)):
        return True
    return (isinstance(expr, ast.Unary) and expr.op in ('+', '-')
            and isinstance(expr.operand, (ast.IntLiteral, ast.RealLiteral)))


class _Lowerer:
    def __init__(self, nodes):
        self.nodes = nodes
        self.out: list = []
        self.decls: list = []  # Dim nodes for compiler names, emitted first
        self.consts: dict[str, ast.Expr] = {}
        self.procs: dict[str, tuple[str, list, str | None]] = {}  # name -> (kind, params, type)
        self.temps = 0
        self.proc = None  # (name, kind, scope names)
        self.whiles: list = []  # preludes of open WHILEs (copied before WEND)
        self.selects: list = []  # (temp, flag, open IF count, else seen, line)

    # ------------------------------------------------------------- scanning
    def scan(self) -> None:
        for node in self.nodes:
            if isinstance(node, (ast.Sub, ast.FunctionDef)):
                kind = 'FUNCTION' if isinstance(node, ast.FunctionDef) else 'SUB'
                if kind == 'FUNCTION':  # M14 (D5): a built-in's name would be ambiguous
                    check_function_name(node.name, node.line, node.column)
                seen = set()
                for p in node.params:
                    if p.name in seen:
                        raise SourceError(p.line, p.column, f'duplicate parameter {p.name}')
                    if p.name.endswith('$') and p.type_name != 'STRING':
                        raise SourceError(p.line, p.column,
                                          f'{p.name} uses $ suffix but is declared {p.type_name}')
                    seen.add(p.name)
                if kind == 'FUNCTION' and node.name.endswith('$') and node.type_name != 'STRING':
                    raise SourceError(node.line, node.column,
                                      f'{node.name} uses $ suffix but returns {node.type_name}')
                self.procs[node.name] = (kind, node.params,
                                         node.type_name if kind == 'FUNCTION' else None)
            elif isinstance(node, ast.Const):
                if hides_builtin(node.name):  # M14 (D5): it would replace PI, SECONDS, ... everywhere
                    raise SourceError(node.line, node.column,
                                      f'{node.name} is a built-in function, so a CONST cannot have '
                                      'that name: choose another name')
                if node.name in self.consts:
                    raise SourceError(node.line, node.column, f'duplicate CONST {node.name}')
                if not _is_literal(node.value):
                    raise SourceError(node.value.line, node.value.column,
                                      'CONST value must be a literal (a number, string, TRUE or FALSE)')
                if node.name.endswith('$') and not isinstance(node.value, ast.StrLiteral):
                    raise SourceError(node.line, node.column,
                                      f'{node.name} uses $ suffix but its value is not a STRING')
                self.consts[node.name] = node.value
        scope: set = set()  # M13: a parameter or LOCAL may have a CONST's name (it shadows it)
        for node in self.nodes:
            name = getattr(node, 'name', None)
            if isinstance(node, (ast.Sub, ast.FunctionDef)):
                scope = {p.name for p in node.params} | {l.name for l in self.locals_of(node)}
            elif isinstance(node, (ast.EndSub, ast.EndFunction)):
                scope = set()
            elif isinstance(node, ast.Dim) and name in self.consts and name not in scope:
                raise SourceError(node.line, node.column,  # M13: say why a DIM clashes
                                  f'{name} is already a CONST (names do not depend on upper or '
                                  'lower case): DIM another name')
            elif isinstance(node, (ast.Assign, ast.AssignIndex, ast.For)) \
                    and name in self.consts and name not in scope:
                raise SourceError(node.line, node.column, f'{name} is a CONST and cannot be changed')
            if isinstance(node, _HANDLER_NODES):
                attrs = ('handler', 'change', 'action')
                if isinstance(node, ast.Canvas):  # M9 (a BUTTON's `keys` are key names)
                    attrs = ('paint', 'mouse', 'keys')
                for attr in attrs:
                    target = getattr(node, attr, None)
                    info = self.procs.get(target) if target else None
                    if info and (info[0] == 'FUNCTION' or info[1]):
                        raise SourceError(node.line, node.column,
                                          f'{target} cannot be an event handler: handlers are '
                                          'SUBs without parameters')

    # -------------------------------------------------------------- names
    def scoped(self, name: str) -> str:
        if '%' in name:  # M10: NAME%FIELD of a parameter / LOCAL record
            base, _, field = name.partition('%')
            return f'{self.scoped(base)}%{field}'
        if self.proc is not None and name in self.proc[2]:
            return f'{self.proc[0]}.{name}'
        return name

    def new_temp(self, type_name: str, line: int, column: int, infer=None) -> str:
        self.temps += 1
        name = f'..T{self.temps}'
        dim = ast.Dim(line, column, name, type_name)
        dim.infer_from = infer
        self.decls.append(dim)
        return name

    # --------------------------------------------------------- expressions
    def expr(self, e, prelude: list, guarded: bool = False):
        """Rename, substitute constants and hoist FUNCTION calls (post-order)."""
        if e is None:
            return None
        if isinstance(e, ast.Var):
            if e.name in self.consts and self.scoped(e.name) == e.name:
                return copy.deepcopy(self.consts[e.name])
            e.name = self.scoped(e.name)
            return e
        if isinstance(e, ast.Index):
            e.name = self.scoped(e.name)
            e.index = self.expr(e.index, prelude, guarded)
            return e
        if isinstance(e, ast.Unary):
            e.operand = self.expr(e.operand, prelude, guarded)
            return e
        if isinstance(e, ast.Binary):
            if e.op in ('AND', 'OR') and not guarded and self.calls_function(e.right) and self.boolean(e):
                return self.short_circuit(e, prelude, guarded)
            e.left = self.expr(e.left, prelude, guarded)
            e.right = self.expr(e.right, prelude, guarded or e.op in ('AND', 'OR'))
            return e
        if isinstance(e, ast.Call):
            info = self.procs.get(e.name)
            if info is None:  # a built-in function or (semantics) an array element
                e.args = [self.expr(a, prelude, guarded) for a in e.args]
                return e
            kind, params, type_name = info
            if kind != 'FUNCTION':
                raise SourceError(e.line, e.column,
                                  f'{e.name} is a SUB: use CALL {e.name}(…) as a statement')
            if guarded:
                raise SourceError(e.line, e.column,
                                  f'FUNCTION {e.name} is called on the right of an AND/OR that is '
                                  'not plainly BOOLEAN here (a comparison, NOT, or a FUNCTION AS '
                                  'BOOLEAN on one side makes it so); otherwise call it in a separate '
                                  'statement first')
            args = [self.expr(a, prelude, guarded) for a in e.args]
            self.call_prelude(e.name, params, args, e, prelude)
            prelude.append(ast.Assign(e.line, e.column, e.name + RESULT,
                                      _default(type_name, e.line, e.column)))
            prelude.append(ast.CallSub(e.line, e.column, e.name))
            temp = self.new_temp(type_name, e.line, e.column)
            prelude.append(ast.Assign(e.line, e.column, temp, ast.Var(e.line, e.column, e.name + RESULT)))
            return ast.Var(e.line, e.column, temp)
        return e

    # M13: a FUNCTION call on the right of a BOOLEAN AND / OR.
    def calls_function(self, e) -> bool:
        """*e* (not yet lowered) calls one of the program's FUNCTIONs."""
        if isinstance(e, ast.Call):
            info = self.procs.get(e.name)
            if info is not None and info[0] == 'FUNCTION':
                return True
            return any(self.calls_function(a) for a in e.args)
        if isinstance(e, ast.Binary):
            return self.calls_function(e.left) or self.calls_function(e.right)
        if isinstance(e, ast.Unary):
            return self.calls_function(e.operand)
        if isinstance(e, ast.Index):
            return self.calls_function(e.index)
        return False

    _COMPARISONS = ('=', '==', '<>', '<', '<=', '>', '>=')

    def boolean(self, e) -> bool:
        """*e* is BOOLEAN by its form: a comparison, NOT, TRUE / FALSE, a
        FUNCTION AS BOOLEAN, or AND / OR / XOR with such an operand (the two
        operands of AND and OR have one type, or semantics refuses them)."""
        if isinstance(e, ast.BoolLiteral):
            return True
        if isinstance(e, ast.Unary):
            return e.op == 'NOT' and self.boolean(e.operand)
        if isinstance(e, ast.Binary):
            if e.op in self._COMPARISONS:
                return True
            if e.op in ('AND', 'OR', 'XOR'):
                return self.boolean(e.left) or self.boolean(e.right)
            return False
        if isinstance(e, ast.Call):
            info = self.procs.get(e.name)
            if info is not None:
                return info[0] == 'FUNCTION' and info[2] == 'BOOLEAN'
            return e.name in ('KEYDOWN', 'EOF')
        return False

    def short_circuit(self, e, prelude: list, guarded: bool):
        """``a AND f()`` as ``T = a : IF T THEN (f's calls) : T = f()``, and
        ``a OR f()`` with ``IF NOT T``: the right operand's FUNCTION calls run
        only when its value is needed, so short-circuit evaluation (§3) holds."""
        line, column = e.line, e.column
        left = self.expr(e.left, prelude, guarded)
        temp = self.new_temp('BOOLEAN', line, column)
        prelude.append(ast.Assign(line, column, temp, left))
        test = ast.Var(line, column, temp)
        if e.op == 'OR':
            test = ast.Unary(line, column, 'NOT', test)
        inner: list = []
        right = self.expr(e.right, inner, False)
        prelude.append(ast.If(line, column, test))
        prelude.extend(inner)
        prelude.append(ast.Assign(line, column, temp, right))
        prelude.append(ast.EndIf(line, column))
        return ast.Var(line, column, temp)

    def call_prelude(self, name, params, args, at, prelude) -> None:
        if len(args) != len(params):
            raise SourceError(at.line, at.column,
                              f'{name} expects {len(params)} argument'
                              f'{"" if len(params) == 1 else "s"}, got {len(args)}')
        for param, arg in zip(params, args):
            prelude.append(ast.Assign(arg.line, arg.column, f'{name}.{param.name}', arg))

    def fields(self, node, prelude: list) -> None:
        for field in _EXPR_FIELDS:
            value = getattr(node, field, None)
            if isinstance(value, ast.Expr):
                setattr(node, field, self.expr(value, prelude))
        if isinstance(getattr(node, 'values', None), list):  # PRINT; M9 DRAW / TEXT
            node.values = [self.expr(v, prelude) for v in node.values]

    # ----------------------------------------------------------- statements
    def run(self) -> list:
        self.scan()
        for node in self.nodes:
            self.statement(node)
        if self.selects:
            line = self.selects[-1][4]
            raise SourceError(line[0], line[1], 'SELECT CASE without END SELECT')
        return self.decls + self.out

    def statement(self, node) -> None:
        out = self.out
        if (self.selects and not self.selects[-1][5]
                and not isinstance(node, (ast.Case, ast.EndSelect, ast.EndProgram, ast.EndSub, ast.EndFunction))):
            # M14 (D4): LANGUAGE-SPEC §5.3: nothing may come between SELECT CASE and its first
            # CASE. It compiled, and such statements ran before the first CASE's test.
            line, column = self.selects[-1][4]
            raise SourceError(node.line, node.column,
                              f'a statement between SELECT CASE (line {line}) and its first CASE: '
                              'put it before SELECT CASE, or inside a CASE')
        if isinstance(node, ast.Const):
            if self.proc is not None:
                raise SourceError(node.line, node.column, 'CONST is only allowed at the top level')
            return
        if isinstance(node, (ast.Sub, ast.FunctionDef)):
            if self.proc is not None:
                raise SourceError(node.line, node.column,
                                  'SUB/FUNCTION must be top-level (missing END SUB or END FUNCTION?)')
            kind = 'FUNCTION' if isinstance(node, ast.FunctionDef) else 'SUB'
            locals_ = self.locals_of(node)
            scope = {p.name for p in node.params} | {l.name for l in locals_}
            self.proc = (node.name, kind, scope)
            self.bitmap_params = {p.name for p in node.params if p.type_name == 'BITMAP'}  # M14 (D4)
            for p in node.params:
                # M13: a BITMAP parameter is a reference: a cell holding the
                # argument's bitmap record address (a bitmap is never copied)
                self.decls.append(ast.Dim(p.line or node.line, p.column or node.column,
                                          f'{node.name}.{p.name}',
                                          'BITMAPREF' if p.type_name == 'BITMAP' else p.type_name))
            if kind == 'FUNCTION':
                self.decls.append(ast.Dim(node.line, node.column, node.name + RESULT, node.type_name))
            out.append(ast.Sub(node.line, node.column, node.name))
            for local in locals_:
                name = f'{node.name}.{local.name}'
                self.decls.append(ast.Dim(local.line, local.column, name, local.type_name))
                out.append(ast.Assign(local.line, local.column, name,
                                      _default(local.type_name, local.line, local.column)))
            return
        if isinstance(node, (ast.EndSub, ast.EndFunction)):
            want = 'FUNCTION' if isinstance(node, ast.EndFunction) else 'SUB'
            if self.proc is None or self.proc[1] != want:
                raise SourceError(node.line, node.column, f'END {want} without matching {want}')
            if self.selects:
                raise SourceError(node.line, node.column, f'END {want} inside an unclosed SELECT CASE')
            self.proc = None
            out.append(ast.EndSub(node.line, node.column))
            return
        if isinstance(node, ast.Local):
            if self.proc is None:
                raise SourceError(node.line, node.column, 'LOCAL is only allowed inside a SUB or FUNCTION')
            return  # declared at procedure entry (statement() for the Sub)
        if isinstance(node, ast.Return):
            if self.proc is None or self.proc[1] != 'FUNCTION':
                raise SourceError(node.line, node.column, 'RETURN is only allowed inside a FUNCTION')
            prelude: list = []
            value = self.expr(node.value, prelude)
            out.extend(prelude)
            out.append(ast.Assign(node.line, node.column, self.proc[0] + RESULT, value))
            out.append(ast.Exit(node.line, node.column, sub=True))
            return
        if isinstance(node, ast.Exit) and getattr(node, 'function', False):
            if self.proc is None or self.proc[1] != 'FUNCTION':
                raise SourceError(node.line, node.column, 'EXIT FUNCTION is only allowed inside a FUNCTION')
            out.append(ast.Exit(node.line, node.column, sub=True))
            return
        if isinstance(node, ast.Exit) and node.sub and self.proc is not None and self.proc[1] == 'FUNCTION':
            raise SourceError(node.line, node.column, 'use EXIT FUNCTION or RETURN inside a FUNCTION')
        if isinstance(node, ast.SelectCase):
            self.select(node)
            return
        if isinstance(node, ast.Case):
            self.case(node)
            return
        if isinstance(node, ast.EndSelect):
            self.end_select(node)
            return
        if isinstance(node, ast.CallSub):
            info = self.procs.get(node.name)
            prelude = []
            if info is not None and info[0] == 'FUNCTION':
                raise SourceError(node.line, node.column,
                                  f'{node.name} is a FUNCTION: use its value in an expression')
            args = [self.expr(a, prelude) for a in node.args]
            if info is not None:
                self.call_prelude(node.name, info[1], args, node, prelude)
            elif args:
                raise SourceError(node.line, node.column,
                                  f'CALL {node.name}: no SUB {node.name} is defined')
            out.extend(prelude)
            node.args = []
            out.append(node)
            return
        # every other statement: rename its targets, lower its expressions
        if (isinstance(node, ast.Assign) and self.proc is not None
                and node.name in getattr(self, 'bitmap_params', ())):
            # M14 (D4): LANGUAGE-SPEC §5.14 says a BITMAP parameter cannot be assigned; it
            # compiled and did nothing (the parameter names the caller's bitmap; nothing is copied)
            raise SourceError(node.line, node.column,
                              f'{node.name} is a BITMAP parameter and cannot be assigned: it names the '
                              'BITMAP the caller passed (copy pictures with BITMAP GET and PUT)')
        if isinstance(node, _RENAMED):
            node.name = self.scoped(node.name)
        if isinstance(node, ast.BitmapOp):  # M13: a BITMAP parameter in a procedure
            node.name = self.scoped(node.name)
            if node.mask is not None:
                node.mask = self.scoped(node.mask)
        if isinstance(node, ast.Next) and node.name is not None:
            node.name = self.scoped(node.name)
        if isinstance(node, ast.Dim) and self.proc is not None and node.name in self.proc[2]:
            raise SourceError(node.line, node.column,
                              f'{node.name} is a parameter or LOCAL of {self.proc[0]}')
        if isinstance(node, ast.Dim) and self.proc is not None:
            node.in_proc = self.proc[0]  # M14 (D6): a global declared inside a procedure (lint warns)
        prelude = []
        self.fields(node, prelude)
        out.extend(prelude)
        if isinstance(node, ast.While):
            self.whiles.append(prelude)
        elif isinstance(node, ast.Wend) and self.whiles:
            out.extend(copy.deepcopy(self.whiles.pop()))
        out.append(node)

    def locals_of(self, start) -> list:
        """The LOCAL statements of the procedure starting at node *start*."""
        found, inside = [], False
        names = {p.name for p in start.params}
        for node in self.nodes:
            if node is start:
                inside = True
                continue
            if not inside:
                continue
            if isinstance(node, (ast.EndSub, ast.EndFunction, ast.Sub, ast.FunctionDef)):
                break
            if isinstance(node, ast.Local):
                if node.name in names:
                    raise SourceError(node.line, node.column,
                                      f'{node.name} is already a parameter or LOCAL of {start.name}')
                if node.name.endswith('$') and node.type_name != 'STRING':
                    raise SourceError(node.line, node.column,
                                      f'{node.name} uses $ suffix but is declared {node.type_name}')
                names.add(node.name)
                found.append(node)
        return found

    # ---------------------------------------------------------- SELECT CASE
    def select(self, node) -> None:
        prelude: list = []
        value = self.expr(node.value, prelude)
        self.out.extend(prelude)
        temp = self.new_temp('?', node.line, node.column, infer=value)
        flag = self.new_temp('BOOLEAN', node.line, node.column)
        self.out.append(ast.Assign(node.line, node.column, temp, value))
        self.out.append(ast.Assign(node.line, node.column, flag, ast.BoolLiteral(node.line, node.column, False)))
        self.selects.append([temp, flag, 0, False, (node.line, node.column), False])

    def case(self, node) -> None:
        if not self.selects:
            raise SourceError(node.line, node.column, 'CASE without SELECT CASE')
        sel = self.selects[-1]
        temp, flag = sel[0], sel[1]
        if sel[3]:
            raise SourceError(node.line, node.column, 'CASE after CASE ELSE')
        if sel[5]:  # close the previous CASE's IF
            self.out.append(ast.EndIf(node.line, node.column))
        line, column = node.line, node.column
        cond = ast.Unary(line, column, 'NOT', ast.Var(line, column, flag))
        if not node.is_else:
            test = None
            for item in node.items:
                for part in (item.value, item.high):
                    if part is not None and self._has_call(part):
                        raise SourceError(part.line, part.column,
                                          'CASE values may not call a FUNCTION; compute it before SELECT CASE')
                low = self.expr(item.value, [])
                subject = ast.Var(line, column, temp)
                if item.kind == 'EQ':
                    t = ast.Binary(line, column, '=', subject, low)
                elif item.kind == 'IS':
                    t = ast.Binary(line, column, item.op, subject, low)
                else:
                    high = self.expr(item.high, [])
                    t = ast.Binary(line, column, 'AND',
                                   ast.Binary(line, column, '>=', subject, low),
                                   ast.Binary(line, column, '<=', ast.Var(line, column, temp), high))
                test = t if test is None else ast.Binary(line, column, 'OR', test, t)
            cond = ast.Binary(line, column, 'AND', cond, test)
        else:
            sel[3] = True
        self.out.append(ast.If(line, column, cond))
        self.out.append(ast.Assign(line, column, flag, ast.BoolLiteral(line, column, True)))
        sel[5] = True

    def _has_call(self, e) -> bool:
        if isinstance(e, ast.Call):
            return e.name in self.procs or any(self._has_call(a) for a in e.args)
        if isinstance(e, ast.Binary):
            return self._has_call(e.left) or self._has_call(e.right)
        if isinstance(e, ast.Unary):
            return self._has_call(e.operand)
        if isinstance(e, ast.Index):
            return self._has_call(e.index)
        return False

    def end_select(self, node) -> None:
        if not self.selects:
            raise SourceError(node.line, node.column, 'END SELECT without SELECT CASE')
        sel = self.selects.pop()
        if sel[5]:
            self.out.append(ast.EndIf(node.line, node.column))


def lower(nodes: list) -> list:
    """Return the flat statement list with every M7 construct lowered."""
    return _Lowerer(nodes).run()
