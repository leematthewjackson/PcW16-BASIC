"""Tier-2 boundary tests: numeric edges, capacity extremes, exact budgets.

Covers empty strings, the minimum program-wide string capacity, FOR at the
signed 16-bit extremes in both directions, zero-iteration loops, MID$ at
positions 1 and 32767, maximal-length UI text, exact MESSAGE budget
arithmetic against the alert buffer size, and case-insensitive name
collisions.
"""
from __future__ import annotations

import unittest

from pbas.errors import SourceError
from pbas.lexer import tokenize
from pbas.parser import Parser
from pbas.policy import (
    ALERT_BUFFER_SIZE,
    BUTTON_CAPTION_MAX,
    CAPTION_MAX,
    LABEL_TEXT_MAX,
    MAX_STRING_CAPACITY,
    MIN_STRING_CAPACITY,
    WINDOW_TITLE_MAX,
)
from pbas.semantics import analyze, dynamic_message_budget


def check(src, **kwargs):
    return analyze(Parser(tokenize(src)).parse(), **kwargs)


class BoundaryTests(unittest.TestCase):
    def assert_rejects_exact(self, src, message, **kwargs):
        with self.assertRaises(SourceError) as caught:
            check(src, **kwargs)
        self.assertEqual(caught.exception.message, message)
        return caught.exception

    # ------------------------------------------------------------ capacities
    def test_empty_string_literal_assignment(self):
        check('DIM V$ AS STRING\nV$ = ""\nEND\n')

    def test_minimum_capacity_program(self):
        src = 'DIM V$ AS STRING\nV$ = "{}"\nEND\n'
        check(src.format('a'), string_capacity=MIN_STRING_CAPACITY)
        check(src.format(''), string_capacity=MIN_STRING_CAPACITY)
        self.assert_rejects_exact(
            src.format('ab'),
            f'cannot assign a 2-character literal to V$ with capacity '
            f'{MIN_STRING_CAPACITY}',
            string_capacity=MIN_STRING_CAPACITY,
        )

    def test_string_capacity_option_validation(self):
        src = 'DIM V$ AS STRING\nEND\n'
        for bad in (MIN_STRING_CAPACITY - 1, MAX_STRING_CAPACITY + 1):
            with self.subTest(capacity=bad):
                with self.assertRaises(SourceError) as caught:
                    check(src, string_capacity=bad)
                self.assertEqual(
                    caught.exception.message,
                    f'string capacity must be between {MIN_STRING_CAPACITY} '
                    f'and {MAX_STRING_CAPACITY}',
                )
                self.assertEqual((caught.exception.line, caught.exception.column), (1, 1))

    # ------------------------------------------------------- numeric extremes
    def test_for_at_integer_extremes_ascending(self):
        check('DIM I AS INTEGER\nFOR I = -32768 TO 32767\nNEXT I\nEND\n')

    def test_for_at_integer_extremes_descending(self):
        check('DIM I AS INTEGER\nFOR I = 32767 TO -32768 STEP -1\nNEXT I\nEND\n')

    def test_zero_iteration_forms(self):
        check('DIM I AS INTEGER\nFOR I = 5 TO 1\nNEXT I\nEND\n')
        check('DIM I AS INTEGER\nFOR I = 1 TO 5 STEP -1\nNEXT I\nEND\n')

    def test_mid_start_positions(self):
        check('DIM T$ AS STRING\nMESSAGE MID$(T$, 1, 1)\nEND\n')
        check('DIM T$ AS STRING\nMESSAGE MID$(T$, 32767, 5)\nEND\n')

    def test_zero_count_substring(self):
        check('DIM T$ AS STRING\nMESSAGE LEFT$(T$, 0)\nEND\n')
        check('DIM T$ AS STRING\nMESSAGE RIGHT$(T$, 0)\nEND\n')

    # --------------------------------------------------------- text at the cap
    def test_maximal_window_title(self):
        check('WINDOW "{}"\nEND\n'.format('x' * WINDOW_TITLE_MAX))

    def test_maximal_label_text(self):
        check('WINDOW "T"\nLABEL "{}"\nEND\n'.format('x' * LABEL_TEXT_MAX))

    def test_maximal_captions(self):
        check('WINDOW "T"\nTEXTBOX V$, "{}"\nEND\n'.format('x' * CAPTION_MAX))
        check('WINDOW "T"\nCHECKBOX V, "{}"\nEND\n'.format('x' * CAPTION_MAX))
        check(
            'WINDOW "T"\nBUTTON "{}", Go\nSUB Go\nEND SUB\nEND\n'.format(
                'x' * BUTTON_CAPTION_MAX
            )
        )

    # -------------------------------------------------------- MESSAGE budgets
    def _budget_of(self, expr_src):
        src = f'DIM V$ AS STRING\nDIM N AS INTEGER\nMESSAGE {expr_src}\nEND\n'
        nodes = Parser(tokenize(src)).parse()
        analysis = analyze(nodes)
        return dynamic_message_budget(nodes[-2].value, analysis.variables)

    def test_dynamic_message_budget_arithmetic(self):
        self.assertEqual(self._budget_of('"ab"'), 2)
        self.assertEqual(self._budget_of('V$'), 64)
        self.assertEqual(self._budget_of('V$ + V$'), 128)
        self.assertEqual(self._budget_of('"ab" + V$ + STR$(N)'), 2 + 64 + 6)
        self.assertEqual(self._budget_of('STR$(N) + STR$(N)'), 12)

    def test_message_budget_exactly_fits(self):
        # 90 literal bytes + capacity 64 + 6 per STR$ = 160 = ALERT_BUFFER_SIZE.
        self.assertEqual(90 + 64 + 6, ALERT_BUFFER_SIZE)
        check(
            'DIM V$ AS STRING\nDIM N AS INTEGER\n'
            'MESSAGE "{}" + V$ + STR$(N)\nEND\n'.format('x' * 90)
        )

    def test_message_budget_one_over(self):
        self.assert_rejects_exact(
            'DIM V$ AS STRING\nDIM N AS INTEGER\n'
            'MESSAGE "{}" + V$ + STR$(N)\nEND\n'.format('x' * 91),
            f'MESSAGE may need up to {ALERT_BUFFER_SIZE + 1} bytes (literal text '
            f'+ string capacities + 6 per STR$) but the alert buffer is '
            f'{ALERT_BUFFER_SIZE} bytes',
        )

    def test_empty_dynamic_message(self):
        check('DIM V$ AS STRING\nMESSAGE "" + V$\nEND\n')

    # ------------------------------------------------------------ name clashes
    def test_case_collision_on_duplicate_dim(self):
        self.assert_rejects_exact(
            'DIM x AS INTEGER\nDIM X AS INTEGER\nEND\n',
            'duplicate declaration of X (first at line 1)',
        )

    def test_case_insensitive_assignment(self):
        check('dim x as integer\nX = 1\nx = 2\nEND\n')

    def test_sub_variable_case_collision(self):
        self.assert_rejects_exact(
            'DIM go AS INTEGER\nSUB Go\nEND SUB\nEND\n',
            'GO is both a SUB and a variable',
        )


if __name__ == '__main__':
    unittest.main()
