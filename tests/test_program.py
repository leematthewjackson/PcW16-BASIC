"""Tier-2 program-model tests: lowering the flat AST into the Program model.

Covers ``build_program`` end-to-end: main line vs procedure bodies, block
structuring (IfBlock/WhileBlock/ForBlock, ELSE-less IFs, nesting), parser
node pass-through for simple statements, and the dialog description taken
from the Analysis (title, widgets, bindings, handlers in source order).
Violated nesting invariants must raise AssertionError, never build a
silently wrong tree.
"""
from __future__ import annotations

import unittest

from pbas import ast_nodes as ast
from pbas.lexer import tokenize
from pbas.parser import Message, Parser
from pbas.program import (
    Binding,
    ForBlock,
    Handler,
    IfBlock,
    Procedure,
    Program,
    WhileBlock,
    Widget,
    build_program,
)
from pbas.semantics import Analysis, analyze


def compile_model(src):
    nodes = Parser(tokenize(src)).parse()
    analysis = analyze(nodes)
    return build_program(nodes, analysis), analysis


REPRESENTATIVE = '''WINDOW "Demo"
LABEL "Name"
TEXTBOX Name$, "Enter"
CHECKBOX Ok, "OK?"
BUTTON "Save", DoSave
BUTTON "Quit", DoQuit
DIM Count AS INTEGER
Count = 1
IF Ok THEN
  Count = 2
ELSE
  Count = 3
END IF
WHILE Count < 10
  FOR Count = 1 TO 2
    MESSAGE "tick" + STR$(Count)
  NEXT Count
  Count = Count + 1
WEND
SUB DoSave
  IF Ok THEN
    FILESAVE "DATA.TXT", Name$
  END IF
END SUB
SUB DoQuit
  EXIT
END SUB
END
'''


class BuildProgramTests(unittest.TestCase):
    def test_representative_program(self):
        program, analysis = compile_model(REPRESENTATIVE)
        self.assertIsInstance(program, Program)
        self.assertEqual(program.dialog_title, 'Demo')
        self.assertEqual(program.string_capacity, 64)

        self.assertEqual(
            [(w.kind, w.caption, w.var_name, w.handler) for w in program.widgets],
            [
                ('LABEL', 'Name', None, None),
                ('TEXTBOX', 'Enter', 'NAME$', None),
                ('CHECKBOX', 'OK?', 'OK', None),
                ('BUTTON', 'Save', None, 'DOSAVE'),
                ('BUTTON', 'Quit', None, 'DOQUIT'),
            ],
        )
        self.assertEqual([w.line for w in program.widgets], [2, 3, 4, 5, 6])
        self.assertEqual(
            [(b.var_name, b.widget, b.capacity) for b in program.bindings],
            [('NAME$', 'TEXTBOX', 64), ('OK', 'CHECKBOX', None)],
        )
        self.assertEqual(
            [(h.button_index, h.sub) for h in program.handlers],
            [(3, 'DOSAVE'), (4, 'DOQUIT')],
        )
        self.assertEqual(
            [(name, v.type, v.capacity, v.origin) for name, v in program.variables.items()],
            [
                ('NAME$', 'STRING', 64, 'TEXTBOX'),
                ('OK', 'BOOLEAN', None, 'CHECKBOX'),
                ('COUNT', 'INTEGER', None, 'DIM'),
            ],
        )

    def test_main_line_structuring(self):
        program, _ = compile_model(REPRESENTATIVE)
        self.assertEqual(
            [type(item).__name__ for item in program.main],
            ['Assign', 'IfBlock', 'WhileBlock'],
        )
        assign = program.main[0]
        self.assertIsInstance(assign, ast.Assign)
        self.assertEqual((assign.name, assign.value.value), ('COUNT', 1))

    def test_if_block_then_else(self):
        program, _ = compile_model(REPRESENTATIVE)
        if_block = program.main[1]
        self.assertIsInstance(if_block, IfBlock)
        self.assertIsInstance(if_block.condition, ast.Var)
        self.assertEqual(if_block.condition.name, 'OK')
        self.assertEqual(
            [stmt.name for stmt in if_block.then_body], ['COUNT']
        )
        self.assertEqual(if_block.then_body[0].value.value, 2)
        self.assertEqual(
            [stmt.name for stmt in if_block.else_body], ['COUNT']
        )
        self.assertEqual(if_block.else_body[0].value.value, 3)

    def test_if_block_without_else(self):
        program, _ = compile_model(
            'DIM B AS BOOLEAN\nIF B THEN\nDIM X AS INTEGER\nX = 1\nEND IF\nEND\n'
        )
        if_block = program.main[0]
        self.assertIsInstance(if_block, IfBlock)
        self.assertEqual(if_block.else_body, [])
        self.assertEqual([stmt.name for stmt in if_block.then_body], ['X'])

    def test_while_for_nesting(self):
        program, _ = compile_model(REPRESENTATIVE)
        while_block = program.main[2]
        self.assertIsInstance(while_block, WhileBlock)
        self.assertIsInstance(while_block.condition, ast.Binary)
        for_block = while_block.body[0]
        self.assertIsInstance(for_block, ForBlock)
        self.assertEqual(for_block.name, 'COUNT')
        self.assertEqual(
            (for_block.start.value, for_block.finish.value, for_block.step.value),
            (1, 2, 1),
        )
        message = for_block.body[0]
        self.assertIsInstance(message, Message)
        self.assertEqual(
            [type(stmt).__name__ for stmt in while_block.body],
            ['ForBlock', 'Assign'],
        )

    def test_simple_statements_pass_through_as_parser_nodes(self):
        program, _ = compile_model(REPRESENTATIVE)
        save = program.procedures[0].body[0]
        self.assertIsInstance(save, IfBlock)
        self.assertIsInstance(save.condition, ast.Var)
        filesave = save.then_body[0]
        self.assertIsInstance(filesave, ast.Filesave)
        self.assertEqual(filesave.filename.value, 'DATA.TXT')
        self.assertIsInstance(filesave.value, ast.Var)
        quit_body = program.procedures[1].body
        self.assertEqual([type(stmt).__name__ for stmt in quit_body], ['Exit'])
        self.assertIsInstance(quit_body[0], ast.Exit)

    def test_procedures_source_order_and_bodies(self):
        program, _ = compile_model(REPRESENTATIVE)
        self.assertEqual([p.name for p in program.procedures], ['DOSAVE', 'DOQUIT'])
        self.assertTrue(all(isinstance(p, Procedure) for p in program.procedures))
        save_body = program.procedures[0].body
        self.assertEqual([type(stmt).__name__ for stmt in save_body], ['IfBlock'])
        inner = save_body[0]
        self.assertIsInstance(inner, IfBlock)
        self.assertEqual(inner.else_body, [])
        self.assertIsInstance(inner.then_body[0], ast.Filesave)

    def test_variables_and_tables_come_from_analysis(self):
        program, analysis = compile_model(REPRESENTATIVE)
        self.assertIs(program.variables, analysis.variables)
        self.assertIs(program.widgets, analysis.widgets)
        self.assertIs(program.bindings, analysis.bindings)
        self.assertIs(program.handlers, analysis.handlers)
        self.assertEqual(program.string_capacity, analysis.string_capacity)
        self.assertEqual(program.dialog_title, analysis.dialog_title)

    def test_program_without_window(self):
        program, _ = compile_model('DIM X AS INTEGER\nX = 1\nEND\n')
        self.assertIsNone(program.dialog_title)
        self.assertEqual(program.widgets, [])
        self.assertEqual(program.bindings, [])
        self.assertEqual(program.handlers, [])
        self.assertEqual([type(s).__name__ for s in program.main], ['Assign'])


class InvariantTests(unittest.TestCase):
    """build_program asserts on violated invariants, never mis-lowers."""

    def empty_analysis(self):
        return Analysis(
            variables={},
            string_capacity=64,
            dialog_title=None,
            widgets=[],
            bindings=[],
            handlers=[],
        )

    def test_else_without_if_asserts(self):
        nodes = [ast.If(1, 1, ast.BoolLiteral(1, 4, True)), ast.Else(2, 1), ast.Else(3, 1)]
        with self.assertRaises(AssertionError):
            build_program(nodes, self.empty_analysis())

    def test_endif_without_if_asserts(self):
        with self.assertRaises(AssertionError):
            build_program([ast.EndIf(1, 1)], self.empty_analysis())

    def test_wend_without_while_asserts(self):
        with self.assertRaises(AssertionError):
            build_program([ast.Wend(1, 1)], self.empty_analysis())

    def test_next_without_for_asserts(self):
        with self.assertRaises(AssertionError):
            build_program([ast.Next(1, 1)], self.empty_analysis())

    def test_sub_inside_sub_asserts(self):
        nodes = [ast.Sub(1, 1, 'A'), ast.Sub(2, 1, 'B')]
        with self.assertRaises(AssertionError):
            build_program(nodes, self.empty_analysis())

    def test_end_sub_without_sub_asserts(self):
        with self.assertRaises(AssertionError):
            build_program([ast.EndSub(1, 1)], self.empty_analysis())

    def test_end_inside_unclosed_block_asserts(self):
        nodes = [ast.If(1, 1, ast.BoolLiteral(1, 4, True)), ast.EndProgram(2, 1)]
        with self.assertRaises(AssertionError):
            build_program(nodes, self.empty_analysis())

    def test_print_never_reaches_build_program(self):
        # Semantics rejects PRINT first; a raw Print node hitting the
        # lowering is an invariant violation.
        nodes = [ast.Print(1, 1, ast.StrLiteral(1, 7, 'x')), ast.EndProgram(2, 1)]
        with self.assertRaises(AssertionError):
            build_program(nodes, self.empty_analysis())

    def test_valid_handbuilt_nodes_lower(self):
        nodes = [
            ast.Assign(1, 1, 'X', ast.IntLiteral(1, 5, 1)),
            ast.If(2, 1, ast.BoolLiteral(2, 4, True)),
            ast.Exit(3, 1),
            ast.EndIf(4, 1),
            ast.EndProgram(5, 1),
        ]
        program = build_program(nodes, self.empty_analysis())
        self.assertEqual(len(program.main), 2)
        self.assertIsInstance(program.main[1], IfBlock)
        self.assertIsInstance(program.main[1].then_body[0], ast.Exit)


if __name__ == '__main__':
    unittest.main()
