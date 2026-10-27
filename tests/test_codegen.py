"""Tier-3 structural tests for the M2 code generator (TESTING-STRATEGY.md).

Per-construct emission-shape tests on independent throwaway programs (never
the shipped examples), plus the label-discipline collector required by the
milestone brief: every ``jp``/``call`` target must be defined exactly once.
Runtime symbols (``rt_*``) are external by definition — the program portion
references them, ``runtime/runtime.z80.asm`` defines them (ARCHITECTURE.md D2).

NOTE on the frozen contract: the brief's MID$/RIGHT$ sequences re-load SRC
after ``call rt_str_skip``; the tests assert that contract literally. The
POC algorithm (POC/pbas/ui_codegen.py ``pb_slice_append``) copies from the
advanced HL instead — flagged for the orchestrator at integration.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pbas import check_source
from pbas.codegen import AsmWriter, BuildReport, assemble, build, generate, mangle
from pbas.errors import SourceError
from pbas.prg import RUNTIME_MARKER
from toolchain import requires_pasmo

REPO_ROOT = Path(__file__).resolve().parent.parent

# Runtime symbols the program portion references but never defines (D2).
RT_SYMBOLS = frozenset(
    {
        "rt_exit",
        "rt_mul16",
        "rt_compare_signed",
        "rt_str_compare",
        "rt_str_len",
        "rt_str_skip",
        "rt_str_copy",
        "rt_append_int",
        "rt_alert",
        "rt_alert_dynamic",
        "rt_gui_run",
    }
)

LABEL_DEF = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):", re.MULTILINE)
JUMP_OP = re.compile(r"^    (?:jp|jr|djnz|call)\s+(\S+)", re.MULTILINE)


def gen(src: str, *, string_capacity: int | None = None) -> str:
    """Frontend + generate for a throwaway program (string_CAPACITY optional)."""
    if string_capacity is None:
        return generate(check_source(src))
    return generate(check_source(src, string_capacity=string_capacity))


def label_defs(asm: str) -> list[str]:
    return LABEL_DEF.findall(asm)


def jump_targets(asm: str) -> set[str]:
    targets = set()
    for match in JUMP_OP.finditer(asm):
        targets.add(match.group(1).split(",")[-1])
    return targets


def assert_label_discipline(testcase: unittest.TestCase, asm: str) -> None:
    """A1 on the program portion: unique definitions, all jump targets defined."""
    defs = label_defs(asm)
    dupes = sorted({name for name in defs if defs.count(name) > 1})
    testcase.assertEqual(dupes, [], f"labels defined more than once: {dupes}")
    undefined = sorted(jump_targets(asm) - set(defs) - RT_SYMBOLS)
    testcase.assertEqual(undefined, [], f"jump targets with no definition: {undefined}")


class EmitterTests(unittest.TestCase):
    def test_mangle_trailing_dollar(self):
        self.assertEqual(mangle("NOTE$"), "NOTE_S")

    def test_mangle_plain_and_case(self):
        self.assertEqual(mangle("count"), "COUNT")
        self.assertEqual(mangle("MiXeD"), "MIXED")
        self.assertEqual(mangle("A$"), "A_S")

    def test_mangle_doubles_underscores(self):
        # M2.1 (D5): '_' -> '__' keeps the encoding injective.
        self.assertEqual(mangle("A_STR"), "A__STR")
        self.assertEqual(mangle("A_S"), "A__S")
        self.assertEqual(mangle("_X$"), "__X_S")

    def test_emit_and_render(self):
        w = AsmWriter()
        w.emit("    org 4000h", "start:")
        self.assertEqual(w.render(), "    org 4000h\nstart:\n")

    def test_new_label_unique(self):
        w = AsmWriter()
        self.assertEqual(w.new_label("cgelse"), "cgelse_1")
        self.assertEqual(w.new_label("cgelse"), "cgelse_2")
        self.assertEqual(w.new_label("cgendif"), "cgendif_3")

    def test_pool_bytes_nul_terminated_and_deduplicated(self):
        w = AsmWriter()
        first = w.pool_label("hi")
        again = w.pool_label("hi")
        other = w.pool_label("ho")
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        items = dict(w.pool_items())
        self.assertEqual(items[first], b"hi\0")
        self.assertEqual(items[other], b"ho\0")

    def test_annotate_source_line(self):
        w = AsmWriter()
        w.annotate(7)
        self.assertEqual(w.render(), "; .pbas line 7\n")


class ExpressionEmissionTests(unittest.TestCase):
    def test_int_literal(self):
        asm = gen("DIM X AS INTEGER\nX = 42\nEND\n")
        self.assertIn("    ld hl,42\n    ld (var_X),hl", asm)

    def test_bool_literals(self):
        asm = gen("DIM B AS BOOLEAN\nB = TRUE\nB = FALSE\nEND\n")
        self.assertIn("    ld hl,1\n    ld (var_B),hl", asm)
        self.assertIn("    ld hl,0\n    ld (var_B),hl", asm)

    def test_unary_minus_sequence(self):
        asm = gen("DIM X AS INTEGER\nDIM Y AS INTEGER\nY = -X\nEND\n")
        self.assertIn(
            "    ld hl,(var_X)\n"
            "    xor a\n"
            "    ld de,0\n"
            "    ex de,hl\n"
            "    sbc hl,de\n"
            "    ld (var_Y),hl",
            asm,
        )

    def test_unary_minus_literal_folds_to_negative(self):
        asm = gen("DIM X AS INTEGER\nX = -5\nEND\n")
        self.assertIn("    ld hl,-5\n    ld (var_X),hl", asm)
        self.assertNotIn("sbc hl,de", asm)

    def test_unary_minus_32768_folds(self):
        asm = gen("DIM X AS INTEGER\nX = -32768\nEND\n")
        self.assertIn("    ld hl,-32768", asm)
        self.assertNotIn("sbc hl,de", asm)

    def test_binary_add_sub_mul(self):
        asm = gen(
            "DIM A AS INTEGER\nDIM B AS INTEGER\nDIM X AS INTEGER\n"
            "X = A + B\nX = A - B\nX = A * B\nEND\n"
        )
        self.assertIn("    push hl\n    ld hl,(var_B)\n    pop de\n    add hl,de", asm)
        self.assertIn("    pop de\n    ex de,hl\n    or a\n    sbc hl,de", asm)
        self.assertIn("    pop de\n    call rt_mul16", asm)

    def test_comparison_wanted_sets(self):
        cases = {
            "=": ["    cp 1"],
            "==": ["    cp 1"],
            "<>": ["    cp 0", "    cp 2"],
            "<": ["    cp 0"],
            "<=": ["    cp 0", "    cp 1"],
            ">": ["    cp 2"],
            ">=": ["    cp 1", "    cp 2"],
        }
        for op, expected in cases.items():
            with self.subTest(op=op):
                asm = gen(
                    f"DIM A AS INTEGER\nDIM B AS INTEGER\nIF A {op} B THEN\nEND IF\nEND\n"
                )
                self.assertIn("    call rt_compare_signed", asm)
                lines = [line for line in asm.splitlines() if line.startswith("    cp ")]
                self.assertEqual(lines, expected)
                # result tail: 0/1 in HL
                self.assertIn("    ld hl,0\n", asm)
                self.assertIn("    ld hl,1\n", asm)
                assert_label_discipline(self, asm)

    def test_comparison_de_left_hl_right(self):
        asm = gen("DIM A AS INTEGER\nDIM B AS INTEGER\nIF A < B THEN\nEND IF\nEND\n")
        self.assertIn("    pop de\n    call rt_compare_signed", asm)

    def test_string_equality_comparison(self):
        asm = gen(
            "DIM S AS STRING\nDIM T AS STRING\nIF S = T THEN\nEND IF\nEND\n"
        )
        # M2.1 (D3): variable/literal operands are compared in place, no copy.
        self.assertIn(
            "    ld hl,var_S\n    push hl\n    ld hl,var_T\n"
            "    ex de,hl\n    pop hl\n    call rt_str_compare",
            asm,
        )
        self.assertNotIn("rt_cmp_buf", asm)

    def test_computed_comparison_operand_uses_guarded_scratch(self):
        asm = gen('DIM N AS INTEGER\nIF STR$(N) = "1" THEN\nEND IF\nEND\n')
        self.assertIn(
            "    ld hl,rt_cmp_buf1+127\n    ld (rt_dst_end),hl\n    ld de,rt_cmp_buf1", asm
        )
        self.assertIn("    xor a\n    ld (de),a\n    ld hl,rt_cmp_buf1\n    push hl", asm)
        self.assertIn("    ld hl,2\n    ld (rt_err_line),hl", asm)

    def test_string_inequality_comparison(self):
        asm = gen('DIM S AS STRING\nIF S <> "x" THEN\nEND IF\nEND\n')
        lines = [line for line in asm.splitlines() if line.startswith("    cp ")]
        self.assertEqual(lines, ["    cp 0", "    cp 2"])

    def test_len_variable(self):
        asm = gen("DIM S AS STRING\nDIM X AS INTEGER\nX = LEN(S)\nEND\n")
        self.assertIn(
            "    ld hl,var_S\n    call rt_str_len\n    ld h,b\n    ld l,c", asm
        )

    def test_len_literal_folds(self):
        asm = gen("DIM X AS INTEGER\nX = LEN(\"abc\")\nEND\n")
        self.assertIn("    ld hl,3\n    ld (var_X),hl", asm)


class StatementEmissionTests(unittest.TestCase):
    def test_integer_assignment(self):
        asm = gen("DIM X AS INTEGER\nX = 1\nEND\n")
        self.assertIn("    ld hl,1\n    ld (var_X),hl", asm)

    # M2.1: every STRING assignment records its line, opens the destination
    # (rt_dst_end = last byte, DE = start), appends through rt_put-guarded
    # routines, then writes the NUL at DE.
    def test_string_assignment_literal(self):
        asm = gen('DIM S AS STRING\nS = "hi"\nEND\n')
        self.assertIn(
            "    ld hl,2\n    ld (rt_err_line),hl\n"
            "    ld hl,var_S+63\n    ld (rt_dst_end),hl\n    ld de,var_S\n"
            "    ld hl,lit_1\n    ld bc,2\n    call rt_str_copy\n"
            "    xor a\n    ld (de),a",
            asm,
        )
        self.assertIn("lit_1: db 104,105,0", asm)

    def test_string_assignment_variable(self):
        asm = gen("DIM S AS STRING\nDIM T AS STRING\nS = T\nEND\n")
        self.assertIn(
            "    ld hl,var_S+63\n    ld (rt_dst_end),hl\n    ld de,var_S\n"
            "    ld hl,var_T\n    ld bc,64\n    call rt_str_copy\n"
            "    xor a\n    ld (de),a",
            asm,
        )

    def test_string_assignment_strs_append_int(self):
        asm = gen("DIM N AS INTEGER\nDIM S AS STRING\nS = STR$(N)\nEND\n")
        self.assertIn(
            "    ld hl,var_S+63\n    ld (rt_dst_end),hl\n    ld de,var_S\n"
            "    push de\n"
            "    ld hl,(rt_dst_end)\n"
            "    push hl\n"
            "    ld hl,(var_N)\n"
            "    pop de\n"
            "    ex de,hl\n"
            "    ld (rt_dst_end),hl\n"
            "    ex de,hl\n"
            "    pop de\n"
            "    call rt_append_int\n"
            "    xor a\n"
            "    ld (de),a",
            asm,
        )

    def test_integer_statement_without_strings_records_no_line(self):
        asm = gen("DIM X AS INTEGER\nX = 1 + 2\nEND\n")
        self.assertNotIn("rt_err_line", asm)

    def test_string_assignment_left_slice(self):
        asm = gen("DIM S AS STRING\nDIM T AS STRING\nS = LEFT$(T, 2)\nEND\n")
        self.assertIn(
            "    ld de,var_S\n"
            "    ld hl,var_T\n"
            "    ld bc,2\n"
            "    call rt_str_copy\n"
            "    xor a\n"
            "    ld (de),a",
            asm,
        )

    def test_string_assignment_mid_slice(self):
        asm = gen("DIM S AS STRING\nDIM T AS STRING\nS = MID$(T, 2, 3)\nEND\n")
        # Copies from the HL advanced by rt_str_skip (POC pb_slice_append
        # shape): no source reload after the skip.
        self.assertIn(
            "    ld de,var_S\n"
            "    ld hl,var_T\n"
            "    ld bc,1\n"
            "    call rt_str_skip\n"
            "    ld bc,3\n"
            "    call rt_str_copy\n"
            "    xor a\n"
            "    ld (de),a",
            asm,
        )

    def test_string_assignment_right_slice(self):
        asm = gen("DIM S AS STRING\nDIM T AS STRING\nS = RIGHT$(T, 2)\nEND\n")
        self.assertIn(
            "    push de\n"
            "    ld hl,var_T\n"
            "    call rt_str_len\n"
            "    ld h,b\n"
            "    ld l,c\n"
            "    ld de,2\n"
            "    or a\n"
            "    sbc hl,de\n"
            "    ld b,h\n"
            "    ld c,l\n"
            "    jp nc,cgright_",
            asm,
        )
        self.assertIn("    ld bc,0\n", asm)
        self.assertIn("    pop de\n", asm)
        self.assertIn("    call rt_str_skip\n    ld bc,2\n    call rt_str_copy", asm)
        assert_label_discipline(self, asm)

    def test_left_slice_bounded_by_destination(self):
        # M2.1 (D2): the count only bounds reading; the destination bound is
        # rt_dst_end = var_S + capacity - 1, enforced by rt_put.
        asm = gen(
            "DIM S AS STRING\nDIM T AS STRING\nS = LEFT$(T, 200)\nEND\n",
            string_capacity=16,
        )
        self.assertIn("    ld hl,var_S+15\n    ld (rt_dst_end),hl\n    ld de,var_S", asm)
        self.assertIn("    ld hl,var_T\n    ld bc,200\n    call rt_str_copy", asm)

    def test_if_else_label_discipline(self):
        asm = gen(
            "DIM B AS BOOLEAN\nDIM X AS INTEGER\n"
            "IF B THEN\n  X = 1\nELSE\n  X = 2\nEND IF\nEND\n"
        )
        self.assertIn("    ld a,h\n    or l\n    jp z,cgelse_", asm)
        self.assertIn("    jp cgendif_", asm)
        assert_label_discipline(self, asm)

    def test_if_without_else(self):
        asm = gen("DIM B AS BOOLEAN\nDIM X AS INTEGER\nIF B THEN\n  X = 1\nEND IF\nEND\n")
        self.assertNotIn("    jp cgendif", asm)
        assert_label_discipline(self, asm)

    def test_while_back_edge(self):
        asm = gen(
            "DIM A AS INTEGER\nA = 0\nWHILE A < 3\n  A = A + 1\nWEND\nEND\n"
        )
        top = re.search(r"^(cgwhiletop_\d+):", asm, re.MULTILINE).group(1)
        end = re.search(r"^(cgwhileend_\d+):", asm, re.MULTILINE).group(1)
        self.assertIn(f"    jp z,{end}", asm)
        self.assertIn(f"    jp {top}\n{end}:", asm)
        assert_label_discipline(self, asm)

    def test_for_ascending_shape(self):
        asm = gen("DIM I AS INTEGER\nFOR I = 1 TO 3\nNEXT\nEND\n")
        limit = re.search(r"^(cgforlimit_\d+):", asm, re.MULTILINE).group(1)
        top = re.search(r"^(cgfortop_\d+):", asm, re.MULTILINE).group(1)
        end = re.search(r"^(cgforend_\d+):", asm, re.MULTILINE).group(1)
        self.assertIn(f"    ld ({limit}),hl\n", asm)
        self.assertIn(f"{top}:\n", asm)
        self.assertIn(f"    call rt_compare_signed\n    cp 2\n    jp z,{end}", asm)
        self.assertIn(f"    call rt_compare_signed\n    cp 1\n    jp z,{end}", asm)
        self.assertIn(f"    inc hl\n    ld (var_I),hl\n    jp {top}\n{end}:", asm)
        self.assertEqual(asm.count(f"{limit}: dw 0"), 1)

    def test_for_descending_shape(self):
        asm = gen("DIM I AS INTEGER\nFOR I = 3 TO 1 STEP -1\nNEXT\nEND\n")
        end = re.search(r"^(cgforend_\d+):", asm, re.MULTILINE).group(1)
        self.assertIn(f"    call rt_compare_signed\n    cp 0\n    jp z,{end}", asm)
        self.assertIn("    dec hl\n    ld (var_I),hl", asm)

    def test_for_two_loops_two_limit_cells(self):
        asm = gen(
            "DIM I AS INTEGER\nFOR I = 1 TO 2\nNEXT\nFOR I = 5 TO 9\nNEXT\nEND\n"
        )
        defs = [name for name in label_defs(asm) if name.startswith("cgforlimit")]
        self.assertEqual(len(defs), 2)
        self.assertEqual(len(set(defs)), 2)
        assert_label_discipline(self, asm)

    def test_exit_jumps_to_rt_exit(self):
        asm = gen("DIM B AS BOOLEAN\nIF B THEN\n  EXIT\nEND IF\nEND\n")
        self.assertIn("    jp rt_exit", asm)

    def test_procedure_emission_and_end_guard(self):
        asm = gen(
            "DIM X AS INTEGER\nX = 1\nSUB DoIt\n  X = 2\nEND SUB\nEND\n"
        )
        main_end = asm.index("    jp rt_exit")
        self.assertLess(main_end, asm.index("sub_DOIT:"))
        body = asm[asm.index("sub_DOIT:") :]
        self.assertIn("    ld hl,2\n    ld (var_X),hl\n    ret", body)
        assert_label_discipline(self, asm)

    def test_source_line_comments(self):
        asm = gen("DIM X AS INTEGER\nX = 1\nEND\n")
        self.assertIn("; .pbas line 2\n    ld hl,1", asm)


class MessageEmissionTests(unittest.TestCase):
    def test_static_message_block_bytes(self):
        asm = gen('MESSAGE "Hi"\nEND\n')
        self.assertIn(
            "msgdef_1: db 72,105,0,0,1\n"
            "    dw 800Dh,80FBh,0,0\n"
            "    db 79,75,0\n"
            "msgdef_1_end:",
            asm,
        )
        self.assertIn(
            "    ld hl,msgdef_1\n"
            "    ld de,msgdef_1_end-msgdef_1\n"
            "    call rt_alert",
            asm,
        )
        assert_label_discipline(self, asm)

    def test_static_empty_message(self):
        asm = gen('MESSAGE ""\nEND\n')
        self.assertIn("msgdef_1: db 0,0,1\n", asm)

    def test_two_static_messages(self):
        asm = gen('MESSAGE "A"\nMESSAGE "B"\nEND\n')
        self.assertIn("msgdef_1: db 65,0,0,1", asm)
        self.assertIn("msgdef_2: db 66,0,0,1", asm)

    def test_dynamic_message_trailer(self):
        asm = gen(
            "DIM N AS INTEGER\nDIM S AS STRING\n"
            'MESSAGE "n=" + STR$(N)\nEND\n'
        )
        # M2.1: text is built under the rt_put guard in the 160-byte text
        # area; the os_alert definition tail moved into rt_alert_dynamic.
        self.assertIn(
            "    ld hl,3\n    ld (rt_err_line),hl\n"
            "    ld hl,rt_alert_buf+160\n    ld (rt_dst_end),hl\n    ld de,rt_alert_buf",
            asm,
        )
        self.assertTrue(asm.rstrip().count("    call rt_alert_dynamic") == 1)
        self.assertNotIn("ldir", asm)
        assert_label_discipline(self, asm)

    def test_dynamic_message_parts(self):
        # Small capacity keeps the M1 MESSAGE budget (2+6+16x4 = 72 <= 160).
        asm = gen(
            "DIM N AS INTEGER\nDIM S AS STRING\n"
            'MESSAGE "n=" + STR$(N) + S + LEFT$(S, 2) + MID$(S, 2, 3) + RIGHT$(S, 1)\n'
            "END\n",
            string_capacity=16,
        )
        self.assertIn("    ld hl,lit_1\n    ld bc,2\n    call rt_str_copy", asm)
        self.assertIn(
            "    push de\n    ld hl,(rt_dst_end)\n    push hl\n    ld hl,(var_N)\n"
            "    pop de\n    ex de,hl\n    ld (rt_dst_end),hl\n    ex de,hl\n"
            "    pop de\n    call rt_append_int",
            asm,
        )
        self.assertIn("    ld hl,var_S\n    ld bc,16\n    call rt_str_copy", asm)
        self.assertIn("    call rt_str_skip", asm)  # MID$ and RIGHT$
        self.assertIn("    call rt_alert_dynamic", asm)

    def test_message_variable_is_dynamic(self):
        asm = gen("DIM S AS STRING\nMESSAGE S\nEND\n")
        self.assertIn("    ld de,rt_alert_buf", asm)
        self.assertNotIn("msgdef_1", asm)
        self.assertIn("    ld hl,var_S\n    ld bc,64\n    call rt_str_copy", asm)


class DataSectionTests(unittest.TestCase):
    def test_variable_storage_by_type(self):
        asm = gen(
            "DIM A AS INTEGER\nDIM B AS BOOLEAN\nDIM NOTE AS STRING\nA = 1\nEND\n"
        )
        self.assertIn("var_A: dw 0", asm)
        self.assertIn("var_B: dw 0", asm)
        self.assertIn("var_NOTE: defs 64", asm)

    def test_string_capacity_option(self):
        asm = gen("DIM S AS STRING\nS = \"x\"\nEND\n", string_capacity=16)
        self.assertIn("var_S: defs 16", asm)
        self.assertIn("    ld hl,var_S+15\n    ld (rt_dst_end),hl", asm)

    def test_variable_insertion_order(self):
        asm = gen(
            "DIM Z AS INTEGER\nDIM A AS INTEGER\nDIM M AS STRING\nZ = 1\nEND\n"
        )
        names = label_defs(asm)
        self.assertEqual(
            [n for n in names if n.startswith("var_")], ["var_Z", "var_A", "var_M"]
        )

    def test_data_section_order(self):
        asm = gen(
            "DIM I AS INTEGER\nDIM S AS STRING\n"
            'MESSAGE "hi"\n'
            "FOR I = 1 TO 2\nNEXT\nEND\n"
        )
        limit = [n for n in label_defs(asm) if n.startswith("cgforlimit")][0]
        self.assertLess(asm.index("msgdef_1: db"), asm.index(f"{limit}: dw 0"))
        self.assertLess(asm.index(f"{limit}: dw 0"), asm.index("var_I: dw 0"))

    def test_program_portion_has_no_runtime_definitions(self):
        asm = gen("DIM A AS INTEGER\nA = 1\nEND\n")
        self.assertNotIn("rt_exit:", asm)
        self.assertNotIn("rt_mul16:", asm)


class NegativeMilestoneTests(unittest.TestCase):
    def test_window_without_button_is_rejected_at_window(self):
        # M3a: no XAnne-verified close path without a button (R-DLG).
        for src in ('WINDOW "Demo"\nLABEL "Hi"\nEND\n', 'DIM X AS INTEGER\nWINDOW "Demo"\nEND\n'):
            with self.subTest(src=src), self.assertRaises(SourceError) as ctx:
                gen(src)
            err = ctx.exception
            self.assertIn("at least one BUTTON", err.message)
            self.assertEqual(err.line, src.split("\n").index('WINDOW "Demo"') + 1)

    def test_textbox_and_checkbox_generate_binding_rows(self):
        # M3b: bindings are table rows, not generated per-widget code.
        src = 'WINDOW "Demo"\nBUTTON "Go", Go\nTEXTBOX Name$\nCHECKBOX Ok\nSUB Go\nEND SUB\nEND\n'
        asm = gen(src)
        self.assertIn("gui_bindings:\n    db 2\n", asm)
        self.assertIn("    dw var_NAME_S\n", asm)
        self.assertIn("    dw var_OK\n", asm)
        self.assertIn("    ld hl,gui_bindings\n    ld (rt_gui_bindings),hl\n", asm)
        assert_label_discipline(self, asm)

    def test_filesave_builds_in_the_file_buffer_then_calls_the_runtime(self):
        # M4: the value is built through the guarded writer in rt_file_buf
        # (128-byte limit), then rt_file_save gets the file descriptor.
        asm = gen('DIM S AS STRING\nFILESAVE "data.txt", S\nEND\n')
        self.assertIn("PB_FILES equ 1", asm)
        self.assertIn("PB_FILE_DEVICE equ 1", asm)
        self.assertIn("ld hl,rt_file_buf+127", asm)
        self.assertIn("call rt_file_save", asm)
        # folder and upper-cased descriptor "DATA",0,".TXT",0 are program data
        self.assertIn("pb_file_path: db " + ",".join(str(b) for b in b"\\PCW\\FOLDER01\0"), asm)
        self.assertIn("pb_file_0: db " + ",".join(str(b) for b in b"DATA\0.TXT\0"), asm)
        self.assertNotRegex(asm, r"call\s+003Bh")

    def test_fileload_passes_variable_and_capacity(self):
        asm = gen('DIM S AS STRING\nFILELOAD "DATA.TXT", S\nEND\n', string_capacity=40)
        self.assertIn("ld de,var_S\n    ld c,40\n    call rt_file_load", asm)

    def test_programs_without_files_do_not_carry_the_file_runtime(self):
        asm = gen('DIM S AS STRING\nMESSAGE "hi"\nEND\n')
        self.assertIn("PB_FILES equ 0", asm)
        self.assertNotIn("PB_FILE_DEVICE", asm)
        self.assertNotIn("pb_file_path", asm)

    def test_one_descriptor_per_file_name(self):
        asm = gen(
            'DIM S AS STRING\nFILESAVE "A.TXT", S\nFILELOAD "a.txt", S\n'
            'FILESAVE "B.TXT", S\nEND\n'
        )
        self.assertEqual(asm.count("pb_file_0:"), 1)
        self.assertEqual(asm.count("pb_file_1:"), 1)
        self.assertNotIn("pb_file_2:", asm)

    def test_computed_substring_uses_the_general_slice_path(self):
        # M5a: the source is built in a scratch buffer, then sliced.
        asm = gen("DIM N AS INTEGER\nDIM S AS STRING\nS = LEFT$(STR$(N), 1)\nEND\n")
        self.assertIn("PB_SLICE equ 1", asm)
        self.assertIn("ld hl,rt_cmp_buf1", asm)

    def test_literal_substrings_keep_the_m2_code(self):
        asm = gen('DIM S AS STRING\nS = "abcdef"\nMESSAGE MID$(S, 2, 3)\nEND\n')
        self.assertIn("PB_SLICE equ 0", asm)
        self.assertIn("PB_STR_TEMPS equ 0", asm)
        self.assertIn("    ld bc,1\n    call rt_str_skip\n    ld bc,3\n    call rt_str_copy", asm)


class AsmShapeTests(unittest.TestCase):
    """A2/A4/A7 over a battery of generated program portions."""

    BATTERY = [
        "DIM X AS INTEGER\nX = 1\nEND\n",
        'DIM S AS STRING\nS = "ab"\nMESSAGE "m" + S\nEND\n',
        "DIM I AS INTEGER\nFOR I = -32768 TO 32767 STEP 1\nNEXT I\nEND\n",
        "DIM B AS BOOLEAN\nWHILE B\n  B = FALSE\nWEND\nEND\n",
        'DIM S AS STRING\nIF S = "" THEN\n  S = RIGHT$(S, 1)\nEND IF\nEND\n',
    ]

    def test_no_raw_dollar_in_symbols(self):
        for src in self.BATTERY:
            with self.subTest(src=src):
                self.assertNotIn("$", gen(src))

    def test_no_direct_os_access(self):
        for src in self.BATTERY:
            with self.subTest(src=src):
                asm = gen(src)
                self.assertNotIn("003B", asm)
                self.assertNotIn("call 0CB", asm)

    def test_container_header_once(self):
        for src in self.BATTERY:
            with self.subTest(src=src):
                asm = gen(src)
                self.assertEqual(asm.count("    org 4000h"), 1)
                self.assertIn("    defs 100h", asm)
                self.assertIn("start:", asm)

    def test_label_discipline_battery(self):
        for src in self.BATTERY:
            with self.subTest(src=src):
                assert_label_discipline(self, gen(src))

    def test_label_discipline_kitchen_sink(self):
        asm = gen(
            "DIM I AS INTEGER\nDIM J AS INTEGER\nDIM N AS INTEGER\n"
            "DIM B AS BOOLEAN\nDIM S AS STRING\nDIM T AS STRING\n"
            'S = "abc"\n'
            "T = S\n"
            "N = -I + 2 * 3 - (I - 1)\n"
            "B = N >= 4\n"
            "IF B THEN\n"
            '  MESSAGE "pos " + STR$(N) + T\n'
            "ELSE\n"
            '  IF S <> "" THEN\n'
            "    WHILE I < 10\n"
            "      I = I + 1\n"
            "      T = LEFT$(S, 2)\n"
            "    WEND\n"
            "  END IF\n"
            "END IF\n"
            "FOR I = 1 TO 3\n"
            "  FOR J = 2 TO 0 STEP -1\n"
            "    MESSAGE MID$(S, 2, 1)\n"
            "  NEXT J\n"
            "NEXT I\n"
            "SUB DoIt\n"
            "  S = RIGHT$(T, 1)\n"
            "  IF LEN(S) = 1 THEN\n"
            "    EXIT\n"
            "  END IF\n"
            "END SUB\n"
            "END\n"
        )
        assert_label_discipline(self, asm)
        self.assertNotIn("$", asm)
        self.assertNotIn("003B", asm)


# --------------------------------------------------------------------- prg.py
STUB_RUNTIME = "rt_exit:\n    ret\n"
MINIMAL_PROGRAM_ASM = "    org 4000h\n    defs 100h\nstart:\n    jp rt_exit\n"


@requires_pasmo
class ContainerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.runtime = root / "runtime.z80.asm"
        self.runtime.write_text(STUB_RUNTIME, encoding="utf-8")
        self.asm_path = root / "out.asm"
        self.prg_path = root / "out.prg"

    def test_assemble_happy_path(self):
        report = assemble(MINIMAL_PROGRAM_ASM, self.runtime, self.asm_path, self.prg_path)
        self.assertIsInstance(report, BuildReport)
        image = self.prg_path.read_bytes()
        self.assertEqual(report.prg_size, len(image))
        self.assertEqual(report.sha256, hashlib.sha256(image).hexdigest())
        self.assertEqual(image[:256], bytes(256))
        text = self.asm_path.read_text(encoding="utf-8")
        self.assertIn(RUNTIME_MARKER, text)
        self.assertLess(text.index("start:"), text.index(RUNTIME_MARKER))

    def test_assemble_pasmo_failure_quotes_stderr(self):
        bad_program = "    org 4000h\n    defs 100h\nstart:\n    jp rt_nope\n"
        with self.assertRaises(SourceError) as ctx:
            assemble(bad_program, self.runtime, self.asm_path, self.prg_path)
        self.assertIn("pasmo", ctx.exception.message)

    def test_zero_prefix_guard(self):
        def fake_run(cmd, **kwargs):
            Path(cmd[3]).write_bytes(b"\x01" * 300)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with mock.patch("pbas.prg.subprocess.run", side_effect=fake_run):
            with self.assertRaises(SourceError) as ctx:
                assemble(MINIMAL_PROGRAM_ASM, self.runtime, self.asm_path, self.prg_path)
        self.assertIn("zero prefix", ctx.exception.message)

    def test_size_guard(self):
        # M2.1 (D6): the image must fit the first 16K bank, #4000-#7FFF.
        fits = MINIMAL_PROGRAM_ASM + f"    defs {16384 - 256 - 3 - 1}\n"
        report = assemble(fits, self.runtime, self.asm_path, self.prg_path)
        self.assertEqual(report.prg_size, 16384)
        over = MINIMAL_PROGRAM_ASM + f"    defs {16384 - 256 - 3}\n"
        with self.assertRaises(SourceError) as ctx:
            assemble(over, self.runtime, self.asm_path, self.prg_path)
        self.assertIn("16384-byte .PRG image limit", ctx.exception.message)

    def test_build_end_to_end(self):
        source = Path(self._tmp.name) / "prog.pbas"
        source.write_text("DIM A AS INTEGER\nA = 1\nEND\n", encoding="utf-8")
        report = build(
            source, self.asm_path, self.prg_path, runtime_path=self.runtime
        )
        image = self.prg_path.read_bytes()
        self.assertEqual(report.prg_size, len(image))
        self.assertEqual(report.sha256, hashlib.sha256(image).hexdigest())
        self.assertEqual(image[:256], bytes(256))
        text = self.asm_path.read_text(encoding="utf-8")
        self.assertIn("    ld (var_A),hl", text)

    def test_build_rejects_buttonless_window_before_pasmo(self):
        source = Path(self._tmp.name) / "ui.pbas"
        source.write_text('WINDOW "Demo"\nLABEL "x"\nEND\n', encoding="utf-8")
        with self.assertRaises(SourceError) as ctx:
            build(source, self.asm_path, self.prg_path, runtime_path=self.runtime)
        self.assertIn("at least one BUTTON", ctx.exception.message)
        self.assertFalse(self.prg_path.exists())

    def test_build_rejects_device_file_name_before_pasmo(self):
        # M4: FILESAVE builds; a DOS device name is refused by the frontend,
        # before any assembly or output.
        source = Path(self._tmp.name) / "fs.pbas"
        source.write_text(
            'DIM S AS STRING\nFILESAVE "CON.TXT", S\nEND\n', encoding="utf-8"
        )
        with self.assertRaises(SourceError) as ctx:
            build(source, self.asm_path, self.prg_path, runtime_path=self.runtime)
        self.assertEqual((ctx.exception.line, ctx.exception.column), (2, 10))
        self.assertIn("device name CON", ctx.exception.message)
        self.assertFalse(self.prg_path.exists())


if __name__ == "__main__":
    unittest.main()
