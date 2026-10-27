"""Tier-1 parser tests: AST shape, positions and every structural diagnostic.

Every case from POC/tests/test_frontend.py is ported here (adapted from the
POC's dict-based nodes to the typed AST) plus the Stage-1 additions: unary
literal folding with the exact range messages, REM comment forms, numbered
blank lines, the validate() negative corpus with exact message text and
position, and the declaration-inside-block rejection.
"""
from __future__ import annotations

import unittest

from pbas.ast_nodes import (
    Assign,
    Binary,
    BoolLiteral,
    Button,
    Call,
    Dim,
    Else,
    EndIf,
    EndProgram,
    EndSub,
    Exit,
    For,
    If,
    IntLiteral,
    Label,
    Next,
    Print,
    StrLiteral,
    Sub,
    Textbox,
    Unary,
    Var,
    Wend,
    While,
    Window,
)
from pbas.errors import SourceError
from pbas.lexer import tokenize
from pbas.parser import Message, Parser, parse, validate


def parse_error(source: str) -> SourceError:
    """Parse *source*, returning the SourceError it must raise."""
    try:
        parse(source)
    except SourceError as error:
        return error
    raise AssertionError(f'expected SourceError, parsed cleanly: {source!r}')


class TestPocPort(unittest.TestCase):
    """POC/tests/test_frontend.py cases, adapted to the typed AST."""

    def test_expression_precedence(self):
        nodes = parse('DIM X AS INTEGER\nX = 2 + 3 * 4\nEND\n')
        value = nodes[1].value
        self.assertIsInstance(value, Binary)
        self.assertEqual(value.op, '+')
        self.assertIsInstance(value.right, Binary)
        self.assertEqual(value.right.op, '*')

    def test_optional_numbers(self):
        nodes = parse('10 PRINT "Hi"\n20 END\n')
        self.assertEqual(len(nodes), 2)
        self.assertIsInstance(nodes[0], Print)
        self.assertIsInstance(nodes[1], EndProgram)

    def test_escaped_quote(self):
        nodes = parse('PRINT "Hi ""there"""\nEND\n')
        self.assertEqual(nodes[0].value.value, 'Hi "there"')

    def test_button_handler(self):
        nodes = parse('BUTTON "OK", Go\nSUB Go\nPRINT "ok"\nEND SUB\nEND\n')
        self.assertEqual(len(nodes), 5)
        self.assertEqual(
            [type(node) for node in nodes],
            [Button, Sub, Print, EndSub, EndProgram],
        )

    def test_missing_handler(self):
        error = parse_error('BUTTON "OK", Missing\nEND\n')
        self.assertEqual(error.message, 'button handler MISSING is not defined by SUB')

    def test_unclosed_if(self):
        error = parse_error('IF 1 = 1 THEN\nPRINT "yes"\nEND\n')
        self.assertEqual(error.message, 'END inside an unclosed block')

    def test_bad_order(self):
        error = parse_error('20 PRINT "Hi"\n10 END\n')
        self.assertEqual(error.message, 'line numbers must strictly increase')

    def test_unknown_statement(self):
        error = parse_error('GOTO 100\nEND\n')
        self.assertEqual(error.message, 'unsupported statement GOTO')

    def test_unclosed_string(self):
        error = parse_error('PRINT "hi\nEND\n')
        self.assertEqual(error.message, 'unterminated string')


class TestStatementShapes(unittest.TestCase):
    def test_dim(self):
        node = parse('DIM X AS INTEGER\nEND\n')[0]
        self.assertIsInstance(node, Dim)
        self.assertEqual((node.name, node.type_name, node.line, node.column), ('X', 'INTEGER', 1, 1))

    def test_dim_string_and_boolean(self):
        nodes = parse('DIM A$ AS STRING\nDIM B AS BOOLEAN\nEND\n')
        self.assertEqual((nodes[0].name, nodes[0].type_name), ('A$', 'STRING'))
        self.assertEqual(nodes[1].type_name, 'BOOLEAN')

    def test_dim_bad_type(self):
        # a non-type word after AS is still a parse error
        error = parse_error('DIM X AS 5\nEND\n')
        self.assertEqual(error.message, 'expected INTEGER, REAL, STRING or BOOLEAN')  # M7: REAL
        self.assertEqual((error.line, error.column), (1, 10))
        # M10: a name after AS is a record TYPE; an undeclared one is an error
        # of the full front end (pbas/records.py), at the DIM
        from pbas import SourceError, check_source
        with self.assertRaises(SourceError) as caught:
            check_source('DIM X AS FOO\nEND\n')
        self.assertEqual(caught.exception.message, 'unknown type FOO (TYPEs: none is declared)')
        self.assertEqual((caught.exception.line, caught.exception.column), (1, 1))

    def test_assign_uppercases_name(self):
        node = parse('dim x as integer\nx = 1\nend\n')[1]
        self.assertIsInstance(node, Assign)
        self.assertEqual((node.name, node.value), ('X', IntLiteral(2, 5, 1)))

    def test_window_label_message_take_string_expressions(self):
        window, label, message, end = parse('WINDOW "T"\nLABEL "L"\nMESSAGE "M"\nEND\n')
        self.assertEqual((window.title.value, label.text.value, message.value.value), ('T', 'L', 'M'))
        self.assertEqual([type(node) for node in (window, label, message, end)], [Window, Label, Message, EndProgram])

    def test_message_node(self):
        node = parse('MESSAGE "M"\nEND\n')[0]
        self.assertIsInstance(node, Message)
        self.assertEqual(node.value.value, 'M')

    def test_print_parses(self):
        node = parse('PRINT 1\nEND\n')[0]
        self.assertIsInstance(node, Print)
        self.assertIsInstance(node.value, IntLiteral)

    def test_textbox_with_and_without_caption(self):
        bare, with_caption = parse('TEXTBOX T$\nTEXTBOX U$, "Cap"\nEND\n')[:2]
        self.assertIsInstance(bare, Textbox)
        self.assertIsNone(bare.caption)
        self.assertEqual(bare.name, 'T$')
        self.assertIsInstance(with_caption.caption, StrLiteral)
        self.assertEqual(with_caption.caption.value, 'Cap')

    def test_button_uppercases_handler(self):
        node = parse('BUTTON "OK", Go\nSUB Go\nEND SUB\nEND\n')[0]
        self.assertEqual(node.handler, 'GO')
        self.assertEqual(node.caption.value, 'OK')

    def test_filesave_fileload(self):
        nodes = parse('FILESAVE "A.TXT", X$\nFILELOAD "B.TXT", Y$\nEND\n')
        self.assertEqual(nodes[0].filename.value, 'A.TXT')
        self.assertEqual(nodes[1].filename.value, 'B.TXT')
        self.assertEqual((nodes[0].value.name, nodes[1].value.name), ('X$', 'Y$'))

    def test_for_default_step_is_literal_one(self):
        node = parse('DIM I AS INTEGER\nFOR I = 1 TO 3\nNEXT I\nEND\n')[1]
        self.assertIsInstance(node, For)
        self.assertEqual(node.step, IntLiteral(2, 1, 1))
        self.assertEqual((node.start.value, node.finish.value), (1, 3))

    def test_for_explicit_negative_step(self):
        node = parse('DIM I AS INTEGER\nFOR I = 3 TO 1 STEP -1\nNEXT I\nEND\n')[1]
        self.assertEqual(node.step, IntLiteral(2, 21, -1))

    def test_while_wend_if_else_end_if(self):
        nodes = parse('IF 1 = 1 THEN\nWHILE 2 = 2\nWEND\nELSE\nEND IF\nEND\n')
        self.assertEqual(
            [type(node) for node in nodes],
            [If, While, Wend, Else, EndIf, EndProgram],
        )

    def test_next_name_optional(self):
        nodes = parse('DIM I AS INTEGER\nFOR I = 1 TO 2\nNEXT\nEND\n')
        self.assertIsInstance(nodes[2], Next)
        self.assertIsNone(nodes[2].name)

    def test_sub_end_sub_and_exit(self):
        nodes = parse('SUB Go\nEXIT\nEND SUB\nEND\n')
        self.assertEqual([type(node) for node in nodes], [Sub, Exit, EndSub, EndProgram])
        self.assertEqual(nodes[0].name, 'GO')

    def test_end_if_and_end_sub_suffixes(self):
        nodes = parse('IF 1 = 1 THEN\nEND IF\nEND\n')
        self.assertIsInstance(nodes[1], EndIf)
        nodes = parse('SUB S\nEND SUB\nEND\n')
        self.assertIsInstance(nodes[1], EndSub)

    def test_expected_error_format(self):
        error = parse_error('DIM X\nEND\n')
        self.assertEqual(error.message, 'expected AS, got NEWLINE')

    def test_expected_expression_error(self):
        error = parse_error('DIM X AS INTEGER\nX = \nEND\n')
        self.assertEqual(error.message, 'expected expression')
        self.assertEqual((error.line, error.column), (2, 5))

    def test_bare_end_only_program(self):
        self.assertEqual(parse('END\n'), [EndProgram(1, 1)])


class TestExpressions(unittest.TestCase):
    def value_of(self, source: str):
        return parse(source + 'END\n')[0].value

    def test_literal_positions(self):
        self.assertEqual(self.value_of('X = 42\n'), IntLiteral(1, 5, 42))
        self.assertEqual(self.value_of('X = TRUE\n'), BoolLiteral(1, 5, True))
        self.assertEqual(self.value_of('X = FALSE\n'), BoolLiteral(1, 5, False))
        self.assertEqual(self.value_of('X = "s"\n'), StrLiteral(1, 5, 's'))

    def test_variable_uppercased(self):
        self.assertEqual(self.value_of('X = count\n'), Var(1, 5, 'COUNT'))

    def test_call_with_args(self):
        value = self.value_of('X = MID$(A$, 1, 2)\n')
        self.assertIsInstance(value, Call)
        self.assertEqual(value.name, 'MID$')
        self.assertEqual(value.args, [Var(1, 10, 'A$'), IntLiteral(1, 14, 1), IntLiteral(1, 17, 2)])

    def test_call_without_args(self):
        value = self.value_of('X = F()\n')
        self.assertEqual((value.name, value.args), ('F', []))

    def test_comparison_has_lowest_precedence(self):
        value = self.value_of('X = 2 + 3 = 5\n')
        self.assertEqual(value.op, '=')
        self.assertEqual((value.left.op, value.left.left.value, value.left.right.value), ('+', 2, 3))
        self.assertEqual(value.right.value, 5)

    def test_left_associativity(self):
        value = self.value_of('X = 10 - 4 - 3\n')
        self.assertEqual(
            value,
            Binary(1, 12, '-',
                   Binary(1, 8, '-', IntLiteral(1, 5, 10), IntLiteral(1, 10, 4)),
                   IntLiteral(1, 14, 3)),
        )

    def test_parentheses_override(self):
        value = self.value_of('X = (2 + 3) * 4\n')
        self.assertEqual(value.op, '*')
        self.assertEqual(value.left.op, '+')
        self.assertEqual(value.right.value, 4)

    def test_unary_binds_tighter_than_star(self):
        value = self.value_of('X = -2 * 3\n')
        self.assertEqual(value, Binary(1, 8, '*', IntLiteral(1, 5, -2), IntLiteral(1, 10, 3)))

    def test_division_parses(self):
        value = self.value_of('X = 6 / 2\n')
        self.assertIsInstance(value, Binary)
        self.assertEqual(value.op, '/')


class TestUnaryFolding(unittest.TestCase):
    def value_of(self, source: str):
        return parse(source + 'END\n')[0].value

    def test_minus_32768_folds_to_single_literal(self):
        self.assertEqual(self.value_of('X = -32768\n'), IntLiteral(1, 5, -32768))

    def test_plus_folds(self):
        self.assertEqual(self.value_of('X = +5\n'), IntLiteral(1, 5, 5))

    def test_minus_folds(self):
        self.assertEqual(self.value_of('X = -5\n'), IntLiteral(1, 5, -5))

    def test_positive_literal_out_of_range(self):
        error = parse_error('X = 32768\n')
        self.assertEqual(error.message, 'integer literal 32768 is outside the range 0..32767')
        self.assertEqual((error.line, error.column), (1, 5))

    def test_unary_plus_out_of_range(self):
        error = parse_error('X = +32768\n')
        self.assertEqual(error.message, 'integer literal 32768 is outside the range 0..32767')

    def test_unary_minus_out_of_range(self):
        error = parse_error('X = -32769\n')
        self.assertEqual(error.message, 'integer literal -32769 is outside the range -32768..32767')
        self.assertEqual((error.line, error.column), (1, 6))

    def test_minus_variable_stays_unary(self):
        value = self.value_of('X = -X\n')
        self.assertIsInstance(value, Unary)
        self.assertEqual(value.op, '-')
        self.assertEqual(value.operand, Var(1, 6, 'X'))

    def test_double_unary_does_not_refold(self):
        value = self.value_of('X = --5\n')
        self.assertIsInstance(value, Unary)
        self.assertEqual(value.op, '-')
        self.assertIsInstance(value.operand, IntLiteral)
        self.assertEqual(value.operand.value, -5)

    def test_spaced_minus_still_folds(self):
        self.assertEqual(self.value_of('X = - 7\n'), IntLiteral(1, 5, -7))


class TestCommentsAndBlankLines(unittest.TestCase):
    def test_rem_full_line(self):
        nodes = parse('REM hello\nDIM X AS INTEGER\nEND\n')
        self.assertEqual([type(node) for node in nodes], [Dim, EndProgram])

    def test_rem_trailing(self):
        nodes = parse('DIM X AS INTEGER REM note\nX = 1 REM another\nEND\n')
        self.assertEqual([type(node) for node in nodes], [Dim, Assign, EndProgram])

    def test_apostrophe_comment(self):
        nodes = parse("' full line\nDIM X AS INTEGER ' trailing\nEND\n")
        self.assertEqual([type(node) for node in nodes], [Dim, EndProgram])

    def test_lone_numbered_blank_line_skipped(self):
        nodes = parse('10\n20 DIM X AS INTEGER\n30 END\n')
        self.assertEqual([type(node) for node in nodes], [Dim, EndProgram])

    def test_numbered_comment_and_blank_lines_among_statements(self):
        nodes = parse('10 REM comment\n20\n30 DIM X AS INTEGER\n40 X = 1 REM t\n50 END\n')
        self.assertEqual([type(node) for node in nodes], [Dim, Assign, EndProgram])

    def test_only_numbered_blank_lines_still_require_end(self):
        error = parse_error('10\n20\n30\n')
        self.assertEqual(error.message, 'program requires a final END')
        self.assertEqual((error.line, error.column), (1, 1))

    def test_number_glued_to_statement_rejected(self):
        error = parse_error('10END\n')
        self.assertEqual(error.message, 'unsupported statement 10')

    def test_non_ascii_letter_rejected_not_crash(self):
        error = parse_error('DIM é AS INTEGER\nEND\n')
        self.assertEqual(error.message, "unexpected character 'é'")


class TestLineNumbers(unittest.TestCase):
    def test_strictly_increasing(self):
        parse('10 DIM X AS INTEGER\n20 X = 1\n30 END\n')

    def test_decreasing_rejected(self):
        error = parse_error('20 END\n10 END\n')
        self.assertEqual(error.message, 'line numbers must strictly increase')
        self.assertEqual((error.line, error.column), (2, 1))

    def test_equal_rejected(self):
        error = parse_error('10 END\n10 END\n')
        self.assertEqual(error.message, 'line numbers must strictly increase')

    def test_first_number_is_free(self):
        parse('100 END\n')


class TestValidateNegatives(unittest.TestCase):
    CASES = [
        ('DIM X AS INTEGER\nEND\nX = 1\n', 'statements after END are not allowed', (3, 1)),
        ('IF 1 = 1 THEN\nSUB S\nEND IF\nEND\n', 'SUB must be top-level', (2, 1)),
        ('SUB S\nEND SUB\nSUB S\nEND SUB\nEND\n', 'duplicate subroutine S', (3, 1)),
        ('WEND\nEND\n', 'WEND without matching WHILE', (1, 1)),
        ('DIM I AS INTEGER\nFOR I = 1 TO 2\nFOR I = 1 TO 2\nNEXT I\nNEXT I\nEND\n',
         'nested FOR reuses active counter I', (3, 1)),
        ('NEXT\nEND\n', 'NEXT without matching FOR', (1, 1)),
        ('DIM I AS INTEGER\nFOR I = 1 TO 2\nNEXT J\nEND\n', 'NEXT J does not match FOR I', (3, 1)),
        ('ELSE\nEND\n', 'ELSE without matching IF', (1, 1)),
        ('IF 1 = 1 THEN\nEND\n', 'END inside an unclosed block', (2, 1)),
        ('WHILE 1 = 1\nEND\n', 'END inside an unclosed block', (2, 1)),
        ('END IF\nEND\n', 'END IF without matching IF', (1, 1)),
        ('END SUB\nEND\n', 'END SUB without matching SUB', (1, 1)),
        ('IF 1 = 1 THEN\nDIM X AS INTEGER\n', 'unclosed IF block', (2, 1)),
        ('WHILE 1 = 1\nDIM X AS INTEGER\n', 'unclosed WHILE block', (2, 1)),
        ('DIM I AS INTEGER\nFOR I = 1 TO 2\n', 'unclosed FOR block', (2, 1)),
        ('SUB S\nDIM X AS INTEGER\n', 'unclosed SUB block', (2, 1)),
        ('DIM X AS INTEGER\n', 'program requires a final END', (1, 1)),
        ('', 'program requires a final END', (1, 1)),
        ('BUTTON "OK", MISSING\nEND\n', 'button handler MISSING is not defined by SUB', (1, 1)),
        ('IF 1 = 1 THEN\nELSE\nELSE\nEND IF\nEND\n',
         'multiple ELSE clauses for one IF', (3, 1)),
    ]

    def test_each_negative(self):
        for source, message, position in self.CASES:
            with self.subTest(source=source):
                error = parse_error(source)
                self.assertEqual(error.message, message)
                self.assertEqual((error.line, error.column), position)


class TestDeclarationPlacement(unittest.TestCase):
    CASES = [
        ('IF 1 = 1 THEN\nWINDOW "T"\nEND IF\nEND\n', 'WINDOW'),
        ('IF 1 = 1 THEN\nLABEL "L"\nEND IF\nEND\n', 'LABEL'),
        ('DIM I AS INTEGER\nFOR I = 1 TO 2\nTEXTBOX T$\nNEXT I\nEND\n', 'TEXTBOX'),
        ('WHILE 1 = 1\nCHECKBOX C\nWEND\nEND\n', 'CHECKBOX'),
        ('SUB S\nBUTTON "B", S\nEND SUB\nEND\n', 'BUTTON'),
    ]

    def test_declaration_inside_block_rejected(self):
        for source, kind in self.CASES:
            with self.subTest(kind=kind):
                error = parse_error(source)
                self.assertEqual(error.message, f'{kind} is only allowed at the top level')

    def test_declaration_after_main_line_statement_is_top_level(self):
        nodes = parse('DIM X AS INTEGER\nWINDOW "T"\nEND\n')
        self.assertEqual([type(node) for node in nodes], [Dim, Window, EndProgram])

    def test_dim_inside_block_allowed(self):
        nodes = parse('IF 1 = 1 THEN\nDIM X AS INTEGER\nEND IF\nEND\n')
        self.assertEqual(len(nodes), 4)


class TestNestingPositive(unittest.TestCase):
    def test_deep_nesting_validates(self):
        source = (
            'DIM I AS INTEGER\n'
            'FOR I = 1 TO 2\n'
            'WHILE I < 2\n'
            'IF I = 1 THEN\n'
            'I = I + 1\n'
            'ELSE\n'
            'I = I - 1\n'
            'END IF\n'
            'WEND\n'
            'NEXT I\n'
            'SUB Done\n'
            'EXIT\n'
            'END SUB\n'
            'END\n'
        )
        nodes = parse(source)
        self.assertEqual(
            [type(node) for node in nodes],
            [Dim, For, While, If, Assign, Else, Assign, EndIf, Wend, Next,
             Sub, Exit, EndSub, EndProgram],
        )

    def test_sibling_for_loops_may_reuse_counter(self):
        source = (
            'DIM I AS INTEGER\n'
            'FOR I = 1 TO 2\n'
            'NEXT I\n'
            'FOR I = 3 TO 4\n'
            'NEXT I\n'
            'END\n'
        )
        self.assertEqual(len(parse(source)), 6)

    def test_validate_module_function(self):
        nodes = Parser(tokenize('END\n')).parse()
        validate(nodes)
        self.assertEqual(len(nodes), 1)


if __name__ == '__main__':
    unittest.main()
