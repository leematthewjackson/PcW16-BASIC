"""Tier-1 lexer tests: token kinds, values and 1-based positions.

Covers every lexical rule of LANGUAGE-SPEC.md section 1, including the three
POC fixes this lexer ports (REM comment, non-ASCII identifier crash, lone
line numbers) and the exact position of every token class.
"""
from __future__ import annotations

import unittest

from pbas.errors import SourceError
from pbas.lexer import KEYWORDS, SINGLE, TWO_CHAR, Token, tokenize


class TestTokenStream(unittest.TestCase):
    def test_empty_source_yields_only_eof(self):
        tokens = tokenize('')
        self.assertEqual(tokens, [Token('EOF', '', 1, 1)])

    def test_simple_line_positions(self):
        self.assertEqual(
            tokenize('X = 1'),
            [
                Token('IDENT', 'X', 1, 1),
                Token('OP', '=', 1, 3),
                Token('NUMBER', '1', 1, 5),
                Token('NEWLINE', '', 1, 6),
                Token('EOF', '', 2, 1),
            ],
        )

    def test_multiline_newline_and_eof_positions(self):
        tokens = tokenize('A = 1\nBB = 22')
        self.assertEqual((tokens[3].kind, tokens[3].line, tokens[3].column), ('NEWLINE', 1, 6))
        self.assertEqual((tokens[4].kind, tokens[4].value, tokens[4].column), ('IDENT', 'BB', 1))
        self.assertEqual((tokens[7].kind, tokens[7].line, tokens[7].column), ('NEWLINE', 2, 8))
        self.assertEqual((tokens[8].kind, tokens[8].line, tokens[8].column), ('EOF', 3, 1))

    def test_trailing_newline_does_not_add_a_line(self):
        tokens = tokenize('X = 1\n')
        self.assertEqual((tokens[-1].kind, tokens[-1].line), ('EOF', 2))

    def test_keyword_sets_match_poc(self):
        self.assertEqual(KEYWORDS, {
            'WINDOW', 'LABEL', 'TEXTBOX', 'CHECKBOX', 'BUTTON', 'SUB', 'END',
            'DIM', 'AS', 'INTEGER', 'STRING', 'BOOLEAN', 'IF', 'THEN',
            'ELSE', 'PRINT', 'MESSAGE', 'REM', 'TRUE', 'FALSE', 'GOTO',
            'EXIT', 'FOR', 'TO', 'NEXT', 'STEP', 'WHILE', 'WEND',
            'FILESAVE', 'FILELOAD',
            'CALL',  # M5c, deliberately beyond the POC keyword set
        })
        self.assertEqual(TWO_CHAR, {'<=', '>=', '<>', '=='})
        self.assertEqual(SINGLE, set('+-*/=(),<>#^'))  # M7: '#' file channels, '^' power


class TestWordsAndKeywords(unittest.TestCase):
    def test_keywords_become_upper_kinds_keeping_value_case(self):
        tokens = tokenize('window "T"')
        self.assertEqual((tokens[0].kind, tokens[0].value), ('WINDOW', 'window'))
        self.assertEqual((tokens[1].kind, tokens[1].value), ('STRING', 'T'))

    def test_keywords_are_case_insensitive(self):
        kinds = [t.kind for t in tokenize('dim x as integer\nend\n')]
        self.assertEqual(kinds[:4], ['DIM', 'IDENT', 'AS', 'INTEGER'])
        self.assertEqual(kinds[5], 'END')

    def test_dollar_suffixed_identifier(self):
        tokens = tokenize('Name$')
        self.assertEqual((tokens[0].kind, tokens[0].value), ('IDENT', 'Name$'))

    def test_true_false_keywords(self):
        kinds = [t.kind for t in tokenize('TRUE FALSE true')]
        self.assertEqual(kinds[:3], ['TRUE', 'FALSE', 'TRUE'])

    def test_goto_is_a_keyword_token(self):
        tokens = tokenize('GOTO 100')
        self.assertEqual((tokens[0].kind, tokens[0].value), ('GOTO', 'GOTO'))
        self.assertEqual((tokens[1].kind, tokens[1].value), ('NUMBER', '100'))


class TestOperators(unittest.TestCase):
    def test_two_char_operators(self):
        for source in ('A <= B', 'A >= B', 'A <> B', 'A == B'):
            with self.subTest(source=source):
                tokens = tokenize(source)
                self.assertEqual((tokens[1].kind, tokens[1].value, tokens[1].column), ('OP', source[2:4], 3))

    def test_two_char_operator_consumes_both_chars(self):
        tokens = tokenize('A<=B')
        self.assertEqual([(t.kind, t.value) for t in tokens[:3]], [('IDENT', 'A'), ('OP', '<='), ('IDENT', 'B')])

    def test_single_operators_split(self):
        tokens = tokenize('A < = B')
        self.assertEqual([(t.kind, t.value) for t in tokens[:5]],
                         [('IDENT', 'A'), ('OP', '<'), ('OP', '='), ('IDENT', 'B'), ('NEWLINE', '')])

    def test_all_single_operators(self):
        tokens = tokenize('1 + 2 - 3 * 4 / 5 = 6 ( 7 ) , 8 < 9 > 0')
        ops = [t.value for t in tokens if t.kind == 'OP']
        self.assertEqual(ops, ['+', '-', '*', '/', '=', '(', ')', ',', '<', '>'])


class TestStrings(unittest.TestCase):
    def test_string_value_and_position(self):
        tokens = tokenize('X = "hello"')
        self.assertEqual((tokens[2].kind, tokens[2].value, tokens[2].line, tokens[2].column),
                         ('STRING', 'hello', 1, 5))

    def test_escaped_quote(self):
        tokens = tokenize('MESSAGE "Hi ""there"""')
        self.assertEqual(tokens[1].value, 'Hi "there"')

    def test_adjacent_strings_after_escape(self):
        tokens = tokenize('"a""b" "c"')
        self.assertEqual(tokens[0].value, 'a"b')
        self.assertEqual(tokens[1].value, 'c')

    def test_empty_string(self):
        self.assertEqual(tokenize('X = ""')[2].value, '')

    def test_unterminated_string_at_opening_quote(self):
        with self.assertRaises(SourceError) as caught:
            tokenize('PRINT "hi')
        self.assertEqual(caught.exception.message, 'unterminated string')
        self.assertEqual((caught.exception.line, caught.exception.column), (1, 7))

    def test_unterminated_string_on_later_line(self):
        with self.assertRaises(SourceError) as caught:
            tokenize('DIM X AS INTEGER\nX = "abc')
        self.assertEqual((caught.exception.line, caught.exception.column), (2, 5))


class TestComments(unittest.TestCase):
    def test_apostrophe_full_line(self):
        self.assertEqual([t.kind for t in tokenize("' a note")], ['NEWLINE', 'EOF'])

    def test_apostrophe_trailing(self):
        tokens = tokenize("X = 1 ' note")
        self.assertEqual([(t.kind, t.value) for t in tokens[:3]],
                         [('IDENT', 'X'), ('OP', '='), ('NUMBER', '1')])
        self.assertEqual([t.kind for t in tokens[3:]], ['NEWLINE', 'EOF'])

    def test_rem_full_line_emits_no_token(self):
        self.assertEqual([t.kind for t in tokenize('REM a note')], ['NEWLINE', 'EOF'])

    def test_rem_trailing_emits_no_token(self):
        tokens = tokenize('DIM X AS INTEGER REM a note')
        self.assertEqual([t.kind for t in tokens],
                         ['DIM', 'IDENT', 'AS', 'INTEGER', 'NEWLINE', 'EOF'])

    def test_rem_after_line_number(self):
        tokens = tokenize('10 REM a note')
        self.assertEqual([(t.kind, t.value, t.line, t.column) for t in tokens],
                         [('LINENO', '10', 1, 1), ('NEWLINE', '', 1, 14), ('EOF', '', 2, 1)])

    def test_rem_is_case_insensitive(self):
        for source in ('rem note', 'Rem note', 'rEM note'):
            with self.subTest(source=source):
                self.assertEqual([t.kind for t in tokenize(source)], ['NEWLINE', 'EOF'])

    def test_remark_and_remains_are_identifiers(self):
        tokens = tokenize('REMARK = 1')
        self.assertEqual((tokens[0].kind, tokens[0].value), ('IDENT', 'REMARK'))
        tokens = tokenize('REMAIN$ = 1')
        self.assertEqual((tokens[0].kind, tokens[0].value), ('IDENT', 'REMAIN$'))

    def test_rem_mid_line_ends_statement(self):
        tokens = tokenize('X = 1 REM 2 + 3')
        self.assertEqual([t.kind for t in tokens],
                         ['IDENT', 'OP', 'NUMBER', 'NEWLINE', 'EOF'])


class TestLineNumbers(unittest.TestCase):
    def test_lineno_column_with_indent(self):
        tokens = tokenize('  10 X = 1')
        self.assertEqual((tokens[0].kind, tokens[0].value, tokens[0].column), ('LINENO', '10', 3))
        self.assertEqual((tokens[1].kind, tokens[1].column), ('IDENT', 6))

    def test_lone_numbered_blank_line(self):
        tokens = tokenize('10')
        self.assertEqual([(t.kind, t.value, t.line, t.column) for t in tokens],
                         [('LINENO', '10', 1, 1), ('NEWLINE', '', 1, 3), ('EOF', '', 2, 1)])

    def test_numbered_blank_line_with_trailing_spaces(self):
        tokens = tokenize('10   ')
        self.assertEqual([t.kind for t in tokens], ['LINENO', 'NEWLINE', 'EOF'])

    def test_number_requires_space_or_line_end(self):
        tokens = tokenize('10X = 1')
        self.assertEqual((tokens[0].kind, tokens[0].value, tokens[0].column), ('NUMBER', '10', 1))
        self.assertEqual((tokens[1].kind, tokens[1].value, tokens[1].column), ('IDENT', 'X', 3))

    def test_number_not_at_line_start_is_not_lineno(self):
        tokens = tokenize('X = 10')
        self.assertEqual((tokens[2].kind, tokens[2].value), ('NUMBER', '10'))


class TestErrors(unittest.TestCase):
    def assert_character_error(self, source: str, ch: str, line: int, column: int):
        with self.assertRaises(SourceError) as caught:
            tokenize(source)
        self.assertEqual(caught.exception.message, f'unexpected character {ch!r}')
        self.assertEqual((caught.exception.line, caught.exception.column), (line, column))

    def test_unexpected_semicolon(self):
        self.assert_character_error('X = 1; Y = 2', ';', 1, 6)

    def test_unexpected_colon(self):
        self.assert_character_error('X: 1', ':', 1, 2)

    def test_unexpected_question_mark(self):
        self.assert_character_error('X = 1?', '?', 1, 6)

    def test_non_ascii_letter_is_an_error_not_a_crash(self):
        self.assert_character_error('DIM é AS INTEGER', 'é', 1, 5)

    def test_non_ascii_letter_in_identifier_position(self):
        self.assert_character_error('X = naïve', 'ï', 1, 7)


if __name__ == '__main__':
    unittest.main()
