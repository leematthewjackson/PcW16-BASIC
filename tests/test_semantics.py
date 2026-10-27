"""Tier-2 semantic tests: type rules, declarations, limits, dialog collection.

Ported from ``POC/tests/test_semantics.py`` (adapted to the typed AST and
the Stage-1 contract — concatenation moved from POC acceptance to rejection,
the POC ``requires {typ} binding`` message maps onto the catalogued
``has incompatible UI bindings`` message) plus the semantic negative cases
from ``POC/tests/test_for_loops.py``, ``POC/tests/test_while_step.py`` and
``POC/tests/test_substrings.py``, and every new Stage-1 semantics rule.
Diagnostic text is asserted against the exact catalog messages.
"""
from __future__ import annotations

import unittest

from pbas.errors import SourceError
from pbas.lexer import tokenize
from pbas import check_source
from pbas.parser import Parser
from pbas.policy import (
    ALERT_BUFFER_SIZE,
    BUTTON_CAPTION_MAX,
    CAPTION_MAX,
    LABEL_TEXT_MAX,
    MAX_BUTTONS,
    MAX_CHECKBOXES,
    MAX_LABELS,
    MESSAGE_LITERAL_MAX,
    WINDOW_TITLE_MAX,
)
from pbas.semantics import _require_textbox_capacity, analyze


def check(src, **kwargs):
    return analyze(Parser(tokenize(src)).parse(), **kwargs)


class SemanticTests(unittest.TestCase):
    def assert_rejects(self, src, fragment, **kwargs):
        with self.assertRaises(SourceError) as caught:
            check(src, **kwargs)
        self.assertIn(fragment, str(caught.exception))
        return caught.exception

    def assert_rejects_exact(self, src, message, **kwargs):
        with self.assertRaises(SourceError) as caught:
            check(src, **kwargs)
        self.assertEqual(caught.exception.message, message)
        return caught.exception

    # ---------------------------------------------------- ported POC positives
    def test_symbol_type(self):
        analysis = check('DIM Counter AS INTEGER\nCounter = 4\nEND\n')
        self.assertEqual(analysis.variables['COUNTER'].type, 'INTEGER')

    def test_case_insensitivity(self):
        analysis = check('dim a as integer\na = 2\nend\n')
        self.assertEqual(analysis.variables['A'].type, 'INTEGER')

    def test_forward_binding(self):
        analysis = check(
            'WINDOW "T"\n'
            'IF Ready = TRUE THEN\nMESSAGE "OK"\nEND IF\n'
            'CHECKBOX Ready, "Ready"\nEND\n'
        )
        self.assertEqual(analysis.variables['READY'].type, 'BOOLEAN')

    def test_auto_checkbox(self):
        analysis = check('WINDOW "T"\nCHECKBOX Agree, "Agree"\nEND\n')
        self.assertEqual(analysis.variables['AGREE'].type, 'BOOLEAN')

    def test_auto_textbox(self):
        analysis = check('WINDOW "T"\nTEXTBOX Name$, "Name"\nEND\n')
        self.assertEqual(analysis.variables['NAME$'].type, 'STRING')

    def test_integer_precedence(self):
        check('DIM X AS INTEGER\nX = 2 + 3 * 4\nEND\n')

    # ---------------------------------------------------- ported POC negatives
    def test_string_concat_in_assignment(self):
        # M5a: concatenation is a STRING expression anywhere (spec section 3);
        # the POC accepted this and Stage 1 had restricted it.
        check('DIM Name$ AS STRING\nName$ = "hello" + " world"\nEND\n')
        check('DIM A$ AS STRING\nA$ = "<" + A$ + ">"\nEND\n')

    def test_concat_with_a_non_string_is_still_rejected(self):
        self.assert_rejects(
            'DIM A$ AS STRING\nDIM N AS INTEGER\nA$ = A$ + N\nEND\n',
            'operator + requires numbers (or STRING + STRING)',
        )

    def test_undefined_variable(self):
        error = self.assert_rejects_exact(
            'DIM X AS INTEGER\nX = Missing\nEND\n',
            'undefined variable MISSING; declare it with DIM or a UI binding',
        )
        self.assertEqual((error.line, error.column), (2, 5))

    def test_assignment_mismatch(self):
        self.assert_rejects_exact(
            'DIM X AS INTEGER\nX = "oops"\nEND\n',
            'cannot assign STRING to INTEGER variable X',
        )

    def test_if_integer_rejected(self):
        self.assert_rejects_exact(
            'IF 1 THEN\nMESSAGE "no"\nEND IF\nEND\n',
            'IF requires BOOLEAN condition, got INTEGER',
        )

    def test_duplicate_dim(self):
        self.assert_rejects_exact(
            'DIM X AS INTEGER\nDIM X AS INTEGER\nEND\n',
            'duplicate declaration of X (first at line 1)',
        )

    def test_binding_conflict(self):
        # POC: 'requires BOOLEAN binding'; Stage-1 catalog: incompatible bindings.
        self.assert_rejects_exact(
            'WINDOW "T"\nDIM Checked AS STRING\nCHECKBOX Checked\nEND\n',
            'CHECKED has incompatible UI bindings (STRING and BOOLEAN)',
        )

    def test_dollar_suffix(self):
        self.assert_rejects_exact(
            'DIM A$ AS INTEGER\nEND\n',
            'A$ uses $ suffix but is declared INTEGER; expected STRING',
        )

    def test_bad_arithmetic(self):
        self.assert_rejects_exact(
            'DIM X AS INTEGER\nX = "x" - 1\nEND\n',
            'operator - requires numbers, got STRING and INTEGER',
        )

    def test_function_not_yet_supported(self):
        self.assert_rejects_exact(
            'DIM X AS INTEGER\nX = FROBNICATE(2)\nEND\n',
            'unknown function FROBNICATE',
        )

    def test_number_range(self):
        # 32768 rejection happens in the parser; verified end-to-end here.
        self.assert_rejects_exact(
            'DIM X AS INTEGER\nX = 70000\nEND\n',
            'integer literal 70000 is outside the range 0..32767',
        )

    def test_mixed_comparison(self):
        self.assert_rejects_exact(
            'IF 1 = "1" THEN\nMESSAGE "x"\nEND IF\nEND\n',
            'comparison = requires matching types, got INTEGER and STRING',
        )

    def test_caption_type(self):
        self.assert_rejects_exact(
            'WINDOW "T"\nBUTTON 123, Go\nSUB Go\nEND SUB\nEND\n',
            'BUTTON caption expects STRING, got INTEGER',
        )

    def test_symbol_sub_collision(self):
        self.assert_rejects_exact(
            'DIM Go AS INTEGER\nSUB Go\nEND SUB\nEND\n',
            'GO is both a SUB and a variable',
        )

    # ------------------------------------------- ported loop/substring negatives
    def test_noninteger_counter_rejected(self):
        self.assert_rejects_exact(
            'DIM I$ AS STRING\nFOR I$ = 1 TO 5\nNEXT I$\nEND\n',
            'FOR counter I$ must be INTEGER',
        )

    def test_noninteger_limit_rejected(self):
        self.assert_rejects_exact(
            'DIM I AS INTEGER\nFOR I = 1 TO "hey"\nNEXT I\nEND\n',
            'FOR bounds must be INTEGER',
        )

    def test_step_two_accepted(self):  # M7: any non-zero INTEGER constant
        check_source('DIM I AS INTEGER\nFOR I = 1 TO 5 STEP 2\nNEXT I\nEND\n')

    def test_step_variable_rejected(self):
        self.assert_rejects_exact(
            'DIM I AS INTEGER\nDIM S AS INTEGER\n'
            'FOR I = 1 TO 4 STEP S\nNEXT I\nEND\n',
            'STEP must be a non-zero INTEGER constant (a literal or CONST)',
        )

    def test_while_requires_boolean(self):
        self.assert_rejects_exact(
            'WHILE 1\nWEND\nEND\n',
            'WHILE requires BOOLEAN condition',
        )

    def test_substring_bad_types(self):
        self.assert_rejects_exact(
            'DIM T$ AS STRING\nMESSAGE LEFT$(3, 2)\nEND\n',
            'LEFT$ expects (STRING, INTEGER)',
        )

    def test_substring_mid_zero(self):
        self.assert_rejects_exact(
            'DIM T$ AS STRING\nMESSAGE MID$(T$, 0, 3)\nEND\n',
            'MID$ start position must be at least 1 (positions are 1-based)',
        )

    def test_substring_computed_positions_accepted(self):
        # M5a: positions and counts are INTEGER expressions; computed ones
        # are checked at run time.
        check('DIM T$ AS STRING\nDIM N AS INTEGER\nMESSAGE RIGHT$(T$, N)\nEND\n')
        check('DIM T$ AS STRING\nDIM N AS INTEGER\n'
              'MESSAGE MID$(T$ + "x", N + 1, LEN(T$) - N)\nEND\n')

    def test_substring_constant_negative_forms_rejected(self):
        self.assert_rejects_exact(
            'DIM T$ AS STRING\nMESSAGE MID$(T$, -2, 3)\nEND\n',
            'MID$ start position must be at least 1 (positions are 1-based)',
        )

    def test_substring_arguments_must_be_integer(self):
        self.assert_rejects(
            'DIM T$ AS STRING\nMESSAGE LEFT$(T$, "3")\nEND\n',
            'LEFT$ expects (STRING, INTEGER)',
        )

    def test_substring_negative_count(self):
        self.assert_rejects_exact(
            'DIM T$ AS STRING\nMESSAGE LEFT$(T$, -1)\nEND\n',
            'LEFT$ count must be at least 0 (counts are non-negative)',
        )

    def test_substring_mid_arity(self):
        self.assert_rejects_exact(
            'DIM T$ AS STRING\nMESSAGE MID$(T$, 1)\nEND\n',
            'MID$ expects 3 arguments, got 2',
        )

    def test_substring_mid_type_tuple(self):
        self.assert_rejects_exact(
            'DIM T$ AS STRING\nMESSAGE MID$(T$, "1", 2)\nEND\n',
            'MID$ expects (STRING, INTEGER, INTEGER)',
        )

    def test_len_arity_and_type(self):
        self.assert_rejects_exact(
            'DIM T$ AS STRING\nMESSAGE LEN(T$, 1)\nEND\n',
            'LEN expects 1 arguments, got 2',
        )
        self.assert_rejects_exact(
            'DIM T$ AS STRING\nMESSAGE LEN(5)\nEND\n',
            'LEN expects a STRING',
        )

    def test_strs_type(self):
        self.assert_rejects_exact(
            'DIM S$ AS STRING\nMESSAGE STR$(S$)\nEND\n',
            'STR$ expects a number (INTEGER or REAL)',
        )

    def test_unary_requires_integer(self):
        self.assert_rejects_exact(
            'DIM S$ AS STRING\nS$ = -S$\nEND\n',
            'unary - requires INTEGER or REAL, got STRING',
        )

    # ------------------------------------------------------- new Stage-1 rules
    def test_literal_32768_rejected_end_to_end(self):
        self.assert_rejects_exact(
            'DIM X AS INTEGER\nX = 32768\nEND\n',
            'integer literal 32768 is outside the range 0..32767',
        )

    def test_negative_literal_bounds(self):
        check('DIM X AS INTEGER\nX = -32768\nEND\n')
        self.assert_rejects_exact(
            'DIM X AS INTEGER\nX = -32769\nEND\n',
            'integer literal -32769 is outside the range -32768..32767',
        )

    def test_division_accepted_and_constant_zero_rejected(self):
        # M5b: integer / and MOD; a constant zero divisor is a compile error.
        check('DIM X AS INTEGER\nX = 4 / 2 + 7 MOD 3\nEND\n')
        self.assert_rejects_exact('DIM X AS INTEGER\nX = X / 0\nEND\n', 'division by zero (/ 0)')
        self.assert_rejects_exact('DIM X AS INTEGER\nX = X MOD -0\nEND\n', 'division by zero (MOD 0)')

    def test_string_ordering_accepted_mixed_types_rejected(self):
        # M5b: STRING ordering is byte order; operands must match.
        for op in ('<', '<=', '>', '>='):
            with self.subTest(op=op):
                check(f'DIM A$ AS STRING\nDIM B$ AS STRING\nIF A$ {op} B$ THEN\nEND IF\nEND\n')
        self.assert_rejects(
            'DIM A$ AS STRING\nDIM N AS INTEGER\nIF A$ < N THEN\nEND IF\nEND\n',
            'require two INTEGER or two STRING operands',
        )
        self.assert_rejects(
            'DIM B AS BOOLEAN\nIF B < TRUE THEN\nEND IF\nEND\n',
            'require two INTEGER or two STRING operands',
        )

    def test_print_rejected(self):
        error = self.assert_rejects_exact(
            'PRINT "x"\nEND\n',
            'PRINT to the screen does not exist in PcW16 BASIC: show text with MESSAGE, a LABEL '
            'or DRAW TEXT (PRINT #n, value writes a line to an open file)',  # M14 (D13)
        )
        self.assertEqual((error.line, error.column), (1, 1))

    def test_concat_allowed_in_message_and_filesave(self):
        check('DIM N$ AS STRING\nMESSAGE "hi " + N$\nEND\n')
        check('DIM N AS INTEGER\nMESSAGE "n=" + STR$(N)\nEND\n')
        check('DIM T$ AS STRING\nMESSAGE LEFT$(T$, 2) + "..."\nEND\n')
        check('DIM T$ AS STRING\nFILESAVE "A.B", T$ + "!"\nEND\n')

    def test_concat_accepted_in_comparisons_and_len(self):
        # M5a: no longer restricted to MESSAGE / FILESAVE values.
        check('DIM A$ AS STRING\nIF A$ + "x" = "y" THEN\nEND IF\nEND\n')
        check('DIM A$ AS STRING\nDIM N AS INTEGER\nN = LEN(A$ + "x")\nEND\n')

    def test_computed_operands_still_bounded_by_scratch(self):
        # A computed operand is built in a 128-byte scratch string: its
        # longest possible length must be at most 127 (M2.1 rule, kept).
        self.assert_rejects(
            'DIM A$ AS STRING\nDIM B$ AS STRING\nDIM C$ AS STRING\n'
            'IF A$ + B$ + C$ = "y" THEN\nEND IF\nEND\n',
            'computed strings used by string comparison are limited to 127',
        )

    def test_fileload_value_must_be_variable(self):
        # Concatenation types here (FILELOAD is an allowed value position)
        # but the destination must still be a plain string variable.
        self.assert_rejects_exact(
            'DIM A$ AS STRING\nFILELOAD "A.B", "x" + "y"\nEND\n',
            'FILELOAD destination must be a string variable',
        )
        self.assert_rejects_exact(
            'DIM N AS INTEGER\nFILELOAD "A.B", N\nEND\n',
            'FILELOAD destination must be a string variable',
        )

    def test_window_title_must_be_literal(self):
        self.assert_rejects_exact(
            'DIM T$ AS STRING\nWINDOW T$\nEND\n',
            'WINDOW title must be a string literal',
        )
        self.assert_rejects_exact(
            'WINDOW 5\nEND\n',
            'WINDOW expects STRING, got INTEGER',
        )

    def test_label_text_must_be_literal_or_string_variable(self):
        # M5d: LABEL T$ (a STRING variable) is a dynamic label; any other
        # non-literal text is still rejected.
        self.assert_rejects_exact(
            'WINDOW "T"\nDIM T$ AS STRING\nLABEL T$ + "x"\nEND\n',
            'LABEL text must be a string literal or a STRING variable',
        )

    def test_captions_must_be_literal(self):
        self.assert_rejects_exact(
            'WINDOW "T"\nDIM C$ AS STRING\nTEXTBOX V$, C$\nEND\n',
            'TEXTBOX caption must be a string literal',
        )
        self.assert_rejects_exact(
            'WINDOW "T"\nDIM C$ AS STRING\nCHECKBOX V, C$\nEND\n',
            'CHECKBOX caption must be a string literal',
        )
        self.assert_rejects_exact(
            'WINDOW "T"\nDIM C$ AS STRING\nBUTTON C$, Go\nSUB Go\nEND SUB\nEND\n',
            'BUTTON caption must be a string literal',
        )

    def test_ascii_enforced_on_ui_text_only(self):
        self.assert_rejects_exact(
            'WINDOW "caf\u00e9"\nEND\n',
            'WINDOW title must be ASCII for Rosanne display',
        )
        self.assert_rejects_exact(
            'WINDOW "T"\nLABEL "caf\u00e9"\nEND\n',
            'LABEL text must be ASCII for Rosanne display',
        )
        self.assert_rejects_exact(
            'WINDOW "T"\nTEXTBOX V$, "caf\u00e9"\nEND\n',
            'TEXTBOX caption must be ASCII for Rosanne display',
        )
        # The same character in an ordinary string is fine.
        check('DIM V$ AS STRING\nV$ = "caf\u00e9"\nEND\n')

    def test_multiple_window_rejected(self):
        self.assert_rejects_exact(
            'WINDOW "T"\nWINDOW "U"\nEND\n',
            'multiple WINDOW declarations are not allowed (exactly one per program)',
        )

    def test_widgets_require_window(self):
        for kind, line in (
            ('LABEL', 'LABEL "x"'),
            ('TEXTBOX', 'TEXTBOX V$'),
            ('CHECKBOX', 'CHECKBOX V'),
            ('BUTTON', 'BUTTON "b", Go\nSUB Go\nEND SUB'),
        ):
            with self.subTest(kind=kind):
                self.assert_rejects_exact(
                    f'{line}\nEND\n',
                    f'{kind} requires a WINDOW declaration',
                )

    def test_widget_count_caps(self):
        def widgets(kind, n):
            if kind == 'LABEL':
                return '\n'.join(f'LABEL "l{i}"' for i in range(n))
            if kind == 'CHECKBOX':
                return '\n'.join(f'CHECKBOX C{i}' for i in range(n))
            return '\n'.join(f'BUTTON "b{i}", Go' for i in range(n))

        limits = (('LABEL', MAX_LABELS), ('CHECKBOX', MAX_CHECKBOXES), ('BUTTON', MAX_BUTTONS))
        for kind, maximum in limits:
            with self.subTest(kind=kind):
                over = widgets(kind, maximum + 1)
                sub = '\nSUB Go\nEND SUB' if kind == 'BUTTON' else ''
                self.assert_rejects_exact(
                    f'WINDOW "T"\n{over}\n{sub}\nEND\n',
                    f'too many {kind}s: {maximum + 1} declared, the maximum is {maximum}',
                )
                check(f'WINDOW "T"\n{widgets(kind, maximum)}\n{sub}\nEND\n')

    def test_text_length_limits(self):
        cases = (
            ('WINDOW', 'WINDOW "{}"', WINDOW_TITLE_MAX, 'WINDOW title is {} characters; the maximum is {}'),
            ('LABEL', 'WINDOW "T"\nLABEL "{}"', LABEL_TEXT_MAX, 'LABEL text is {} characters; the maximum is {}'),
            ('TEXTBOX', 'WINDOW "T"\nTEXTBOX V$, "{}"', CAPTION_MAX, 'TEXTBOX caption is {} characters; the maximum is {}'),
            ('CHECKBOX', 'WINDOW "T"\nCHECKBOX V, "{}"', CAPTION_MAX, 'CHECKBOX caption is {} characters; the maximum is {}'),
            ('BUTTON', 'WINDOW "T"\nBUTTON "{}", Go\nSUB Go\nEND SUB', BUTTON_CAPTION_MAX, 'BUTTON caption is {} characters; the maximum is {}'),
        )
        for kind, template, maximum, message in cases:
            with self.subTest(kind=kind):
                check(template.format('x' * maximum) + '\nEND\n')
                bad = template.format('x' * (maximum + 1)) + '\nEND\n'
                self.assert_rejects_exact(bad, message.format(maximum + 1, maximum))

    def test_filename_validation(self):
        good = 'WINDOW "T"\nDIM V$ AS STRING\nFILESAVE "{}", V$\nEND\n'
        for name in ('A.B', '123_4.XY', 'data.txt', 'LONG1234.ABC', 'A.123'):
            with self.subTest(name=name):
                check(good.format(name))
        bad_names = (
            'BAD NAME.X',  # space
            'TOOLONGGX.X',  # base of 9
            'NAME.LONGG',  # 4-char extension
            'NOEXT',  # missing extension
            'NAME.',  # empty extension
        )
        for name in bad_names:
            with self.subTest(name=name):
                self.assert_rejects_exact(
                    good.format(name),
                    f"file name '{name}' is not a valid DOS 8.3 name "
                    '([A-Z0-9_]{1,8}.[A-Z0-9]{1,3})',
                )

    def test_filename_must_be_literal(self):
        self.assert_rejects_exact(
            'DIM V$ AS STRING\nFILESAVE Name$, V$\nEND\n',
            'this file name must be written in the program as a string, such as "NOTES.TXT", or be '
            'a CONST (OPEN, KILL, NAME, TEXT, DB and BITMAP statements also accept a STRING variable)',  # M14
        )

    def test_textbox_capacity_rule(self):
        # Accepted at the largest legal program-wide capacity. The
        # TEXTBOX_CAPACITY_MAX check itself is unreachable through analyze()
        # (policy caps capacity at 127 < 128) but must exist for when the
        # policy bound moves; exercised directly here.
        check('WINDOW "T"\nTEXTBOX V$\nEND\n', string_capacity=127)
        with self.assertRaises(SourceError) as caught:
            _require_textbox_capacity('V$', 129, 2, 1)
        self.assertEqual(
            caught.exception.message,
            'TEXTBOX-bound string V$ has capacity 129, exceeding the '
            'textedit maximum of 128',
        )

    def test_literal_longer_than_capacity(self):
        self.assert_rejects_exact(
            'DIM V$ AS STRING\nV$ = "{}"\nEND\n'.format('x' * 65),
            'cannot assign a 65-character literal to V$ with capacity 64',
        )
        check('DIM V$ AS STRING\nV$ = "{}"\nEND\n'.format('x' * 63))

    def test_message_literal_limit(self):
        check('MESSAGE "{}"\nEND\n'.format('x' * MESSAGE_LITERAL_MAX))
        self.assert_rejects_exact(
            'MESSAGE "{}"\nEND\n'.format('x' * (MESSAGE_LITERAL_MAX + 1)),
            f'MESSAGE literal is {MESSAGE_LITERAL_MAX + 1} bytes; '
            f'the maximum is {MESSAGE_LITERAL_MAX}',
        )

    def test_message_dynamic_budget(self):
        # 90 literal bytes + capacity 64 + 6 for STR$ = 160: fits.
        fits = 'DIM V$ AS STRING\nDIM N AS INTEGER\nMESSAGE "{}" + V$ + STR$(N)\nEND\n'
        check(fits.format('x' * 90))
        overflow = 'DIM V$ AS STRING\nDIM N AS INTEGER\nMESSAGE "{}" + V$ + STR$(N)\nEND\n'
        self.assert_rejects_exact(
            overflow.format('x' * 91),
            f'MESSAGE may need up to {ALERT_BUFFER_SIZE + 1} bytes (literal text '
            f'+ string capacities + 6 per STR$) but the alert buffer is '
            f'{ALERT_BUFFER_SIZE} bytes',
        )

    def test_message_ascii_enforced(self):
        # MESSAGE text enters a Rosanne alert: literal parts must be ASCII
        # (spec section 1). Non-ASCII content of ordinary STRING variables
        # stays legal outside Rosanne-facing positions.
        self.assert_rejects_exact(
            'MESSAGE "héllo"\nEND\n',
            'MESSAGE text must be ASCII for Rosanne display',
        )
        self.assert_rejects_exact(
            'DIM V$ AS STRING\nDIM N AS INTEGER\n'
            'MESSAGE "x" + V$ + "héllo" + STR$(N)\nEND\n',
            'MESSAGE text must be ASCII for Rosanne display',
        )
        check('DIM V$ AS STRING\nV$ = "héllo"\nEND\n')

    def test_zero_button_dialog_accepted(self):
        analysis = check('WINDOW "T"\nLABEL "l"\nEND\n')
        self.assertEqual(analysis.dialog_title, 'T')
        self.assertEqual([w.kind for w in analysis.widgets], ['LABEL'])

    def test_for_counter_must_be_declared(self):
        self.assert_rejects_exact(
            'FOR I = 1 TO 5\nNEXT I\nEND\n',
            'FOR counter I must be declared with DIM',
        )

    def test_step_zero_rejected(self):
        self.assert_rejects_exact(
            'DIM I AS INTEGER\nFOR I = 1 TO 5 STEP 0\nNEXT I\nEND\n',
            'STEP must be a non-zero INTEGER constant (a literal or CONST)',
        )


if __name__ == '__main__':
    unittest.main()
