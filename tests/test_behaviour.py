"""Behavioural tests for M2 code generation — an engineering aid, not an evidence tier.

PURPOSE: exercise the M2 compiler end-to-end on small, independent throwaway
programs — write a .pbas source to a temp dir, build it with
``python3 tools/build.py SOURCE --prg OUT.PRG`` (PcW16-BASIC/README.md), then
execute the resulting .PRG on the ``tests/z80sim.py`` CPU model and assert the
exact sequence of MESSAGE alert texts plus a clean stop via os_app_exit.

Per PcW16-BASIC/TESTING-STRATEGY.md the simulator is NOT an evidence tier and
these tests must never be cited as runtime, emulator or XAnne evidence; XAnne
remains the only runtime evidence (tier 5, owner-executed). The first test
class instead unit-tests the simulator itself against hand-assembled byte
sequences, so the model is verified independently of the compiler.

Every .pbas program below is an independent client of the language (project
rule 9); none mirrors the implementation tests. Each is written against
LANGUAGE-SPEC.md Stage 1 and verified against the M1 frontend
(``python3 -m pbas check``) before being used here.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import z80sim  # noqa: E402  (tests/ is not a package)
from toolchain import requires_pasmo  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_TOOL = REPO_ROOT / 'tools' / 'build.py'
RUNTIME_SOURCE = REPO_ROOT / 'runtime' / 'runtime.z80.asm'

EXIT_CALL = bytes((0x3E, 23, 0xCD, 0x3B, 0x00))  # ld a,23 / call 003Bh


def image(code: bytes) -> bytes:
    """Wrap entry code with the 256-byte zero prefix (container, ARCHITECTURE D7)."""
    return bytes(0x100) + code


class TestSimulatorPrimitives(unittest.TestCase):
    """Verify the CPU model against hand-assembled sequences (no Pasmo needed)."""

    def test_app_exit_stops_cleanly(self):
        cpu = z80sim.run(image(EXIT_CALL))
        self.assertTrue(cpu.exited)
        self.assertEqual(cpu.alerts, [])
        self.assertEqual(cpu.steps, 2)

    def test_alert_definition_is_decoded(self):
        definition = (
            b'Hello, PcW\x00\x00\x01'  # one line, extra NUL, one button
            b'\x0d\x80\xfb\x80\x00\x00\x00\x00'  # dw 800Dh,80FBh,0,0
            b'yu\x00'
        )
        code = (
            bytes((0x21, 0x00, 0x00))  # ld hl,def (address patched below)
            + bytes((0x11, len(definition) & 0xFF, len(definition) >> 8))
            + bytes((0x3E, 76, 0xCD, 0x3B, 0x00))  # ld a,76 / call 003Bh
            + bytes((0x32, 0x01, 0x90))  # ld (9001h),a — A as the alert left it
            + EXIT_CALL
            + definition
        )
        def_addr = 0x4100 + len(code) - len(definition)
        code = code[:1] + bytes((def_addr & 0xFF, def_addr >> 8)) + code[3:]
        cpu = z80sim.run(image(code))
        self.assertTrue(cpu.exited)
        self.assertEqual(cpu.alerts, ['Hello, PcW'])
        self.assertEqual(cpu.mem[0x9001], 0)  # os_alert returns with A=0
        self.assertFalse(cpu.f & z80sim.FLAG_C)  # and NC

    def test_multiline_alert_text_joins_with_newline(self):
        definition = b'Line1\x00Line2\x00\x00\x01' + b'\x00' * 8 + b'ok\x00'
        code = (
            bytes((0x21, 0x10, 0x41))
            + bytes((0x11, len(definition) & 0xFF, len(definition) >> 8))
            + bytes((0x3E, 76, 0xCD, 0x3B, 0x00))
            + EXIT_CALL
            + definition
        )
        cpu = z80sim.run(image(code))
        self.assertEqual(cpu.alerts, ['Line1\nLine2'])

    def test_unsupported_opcode_names_it_in_hex(self):
        with self.assertRaisesRegex(z80sim.SimError, 'D3'):
            z80sim.run(image(b'\xd3\x00'), max_steps=100)  # out (0),a

    def test_unsupported_cb_opcode_names_it_in_hex(self):
        with self.assertRaisesRegex(z80sim.SimError, 'CB 00'):
            z80sim.run(image(b'\xcb\x00'), max_steps=100)  # rlc b

    def test_unknown_os_function_lists_a(self):
        # M12: 99 (os_meta_char) is modelled now; 100 (os_meta_score) is not
        with self.assertRaisesRegex(z80sim.SimError, 'A=100'):
            z80sim.run(image(bytes((0x3E, 100, 0xCD, 0x3B, 0x00))))
        with self.assertRaisesRegex(z80sim.SimError, 'A=200'):
            z80sim.run(image(bytes((0x3E, 200, 0xCD, 0x3B, 0x00))))

    def test_bios_getmem1_returns_fake_bank(self):
        code = bytes((0xCD, 0xCB, 0x00)) + bytes((0x32, 0x00, 0x90)) + EXIT_CALL
        cpu = z80sim.run(image(code))
        self.assertTrue(cpu.exited)
        self.assertEqual(cpu.mem[0x9000], z80sim.FAKE_APP_BANK)

    def test_halt_is_a_runaway(self):
        with self.assertRaises(z80sim.SimRunaway):
            z80sim.run(image(b'\x76'), max_steps=100)

    def test_nop_slide_off_the_image_is_a_runaway(self):
        with self.assertRaises(z80sim.SimRunaway):
            z80sim.run(image(b'\x00' * 0x10), max_steps=1000)

    def test_djnz_loop_counts_iterations(self):
        code = (
            bytes((0x06, 5))  # ld b,5
            + bytes((0x26, 0))  # ld h,0
            + bytes((0x24,))  # inc h            <- loop head (4104h)
            + bytes((0x10, 0xFD))  # djnz -3
            + bytes((0x22, 0x00, 0x90))  # ld (9000h),hl
            + EXIT_CALL
        )
        cpu = z80sim.run(image(code))
        self.assertEqual((cpu.h, cpu.b), (5, 0))
        self.assertEqual(cpu.mem[0x9001], 5)  # (9000h) holds L, (9001h) holds H

    def test_add_hl_sets_carry_and_result(self):
        code = (
            bytes((0x21, 0xFF, 0xFF))  # ld hl,0FFFFh
            + bytes((0x01, 0x01, 0))  # ld bc,1
            + bytes((0x09,))  # add hl,bc -> 0000h, carry out of bit 15
            + bytes((0x22, 0x00, 0x90))
            + EXIT_CALL
        )
        cpu = z80sim.run(image(code))
        self.assertEqual(bytes(cpu.mem[0x9000 : 0x9002]), b'\x00\x00')
        self.assertTrue(cpu.f & z80sim.FLAG_C)

    def test_adc_sbc_hl(self):
        code = (
            bytes((0x21, 0xFF, 0x7F))  # ld hl,7FFFh
            + bytes((0x01, 0, 0))  # ld bc,0
            + bytes((0x37,))  # scf
            + bytes((0xED, 0x4A))  # adc hl,bc -> 8000h
            + bytes((0x22, 0x00, 0x90))
            + bytes((0x21, 0x00, 0x80))  # ld hl,8000h
            + bytes((0x01, 0x01, 0))  # ld bc,1
            + bytes((0xED, 0x42))  # sbc hl,bc -> 7FFFh
            + bytes((0x22, 0x02, 0x90))
            + EXIT_CALL
        )
        cpu = z80sim.run(image(code))
        self.assertEqual(bytes(cpu.mem[0x9000 : 0x9002]), b'\x00\x80')
        self.assertEqual(bytes(cpu.mem[0x9002 : 0x9004]), b'\xff\x7f')

    def test_ldi_then_ldir_transfers_all_bytes(self):
        src = b'XYZ'
        code = (
            bytes((0x21, 0x00, 0x00))  # ld hl,src (patched below)
            + bytes((0x11, 0x00, 0x90))  # ld de,9000h
            + bytes((0x01, 3, 0))  # ld bc,3
            + bytes((0xED, 0xA0))  # ldi -> one byte, PV set
            + bytes((0xED, 0xB0))  # ldir -> remaining two bytes, PV clear
            + EXIT_CALL
        )
        src_addr = 0x4100 + len(code)
        code = code[:1] + bytes((src_addr & 0xFF, src_addr >> 8)) + code[3:]
        cpu = z80sim.run(image(code + src))
        self.assertTrue(cpu.exited)
        self.assertEqual(bytes(cpu.mem[0x9000 : 0x9003]), b'XYZ')
        self.assertFalse(cpu.f & z80sim.FLAG_PV)  # BC reached 0

    def test_cb_shifts_res_set_and_bit_test(self):
        code = (
            bytes((0x3E, 1))  # ld a,1
            + bytes((0xCB, 0x27))  # sla a -> 2
            + bytes((0xCB, 0x2F))  # sra a -> 1
            + bytes((0xCB, 0x17))  # rl a  -> 2
            + bytes((0xCB, 0x1F))  # rr a  -> 1
            + bytes((0xCB, 0x4F))  # bit 1,a -> Z=1 (bit clear on a=1)
            + bytes((0xCB, 0x87))  # res 0,a -> 0
            + bytes((0xCB, 0xCF))  # set 1,a -> 2
            + bytes((0xCB, 0x47))  # bit 0,a -> Z=1 (bit clear on a=2)
            + bytes((0x28, 0x02))  # jr z,+2 (taken) past the halt
            + b'\x76\x00'  # halt + pad (reached only if bit 0 looked set)
            + bytes((0x32, 0x00, 0x90))  # ld (9000h),a
            + EXIT_CALL
        )
        cpu = z80sim.run(image(code))
        self.assertTrue(cpu.exited)
        self.assertEqual(cpu.mem[0x9000], 2)

    def test_ex_push_pop_call_and_ret(self):
        body = (
            bytes((0x21, 0x34, 0x12))  # ld hl,1234h
            + bytes((0x11, 0x78, 0x56))  # ld de,5678h
            + bytes((0xEB,))  # ex de,hl -> hl=5678 de=1234
            + bytes((0xE5,))  # push hl
            + bytes((0xD5,))  # push de
            + bytes((0x21, 0, 0))  # ld hl,0
            + bytes((0x11, 0, 0))  # ld de,0
            + bytes((0xD1,))  # pop de -> 1234h
            + bytes((0xE1,))  # pop hl -> 5678h
            + bytes((0xCD, 0x00, 0x00))  # call sub (address patched below)
            + bytes((0x22, 0x00, 0x90))  # ld (9000h),hl
            + EXIT_CALL
        )
        sub_addr = 0x4100 + len(body)
        code = (
            body[:17]
            + bytes((0xCD, sub_addr & 0xFF, sub_addr >> 8))
            + body[20:]
            + bytes((0x26, 0x2A))  # sub: ld h,2Ah
            + bytes((0x2E, 0))  # ld l,0
            + bytes((0xC9,))  # ret
        )
        cpu = z80sim.run(image(code))
        self.assertTrue(cpu.exited)
        self.assertEqual(bytes(cpu.mem[0x9000 : 0x9002]), b'\x00\x2a')
        self.assertEqual(cpu.sp, 0x3FFE)  # stack balanced across the call

    def test_conditional_jp_jr_call_and_ret_paths(self):
        code = (
            bytes((0x3E, 5))  # ld a,5
            + bytes((0xD6, 5))  # sub 5 -> Z=1
            + bytes((0xCA, 0x0B, 0x41))  # jp z,410Bh (taken)
            + b'\x76' + bytes(3)  # halt + pad (4107h..410Ah)
            + bytes((0xC2, 0x13, 0x41))  # jp nz,4113h (not taken)
            + bytes((0x18, 0x04))  # jr +4 -> 4114h
            + b'\x76' + bytes(2)  # halt + pad (4110h..4112h)
            + bytes((0x76,))  # halt: wrong target of jp nz (4113h)
            + bytes((0xCD, 0x21, 0x41))  # call sub (4114h)
            + bytes((0x3E, 0x5A))  # ld a,5Ah
            + bytes((0x32, 0x00, 0x90))  # ld (9000h),a
            + EXIT_CALL  # 411Ch..4120h
            + bytes((0xCC, 0x25, 0x41))  # sub(4121h): call z,4125h (taken)
            + bytes((0xC9,))  # ret -> back to the ld a,5Ah
            + bytes((0xC8,))  # ret z -> pops the 4124h return address
        )
        cpu = z80sim.run(image(code))
        self.assertTrue(cpu.exited)
        self.assertEqual(cpu.mem[0x9000], 0x5A)
        self.assertEqual(cpu.sp, 0x3FFE)

    def test_inc_dec_hl_and_memory_indirect(self):
        code = (
            bytes((0x21, 0x00, 0x90))  # ld hl,9000h
            + bytes((0x36, 0x42))  # ld (hl),42h
            + bytes((0x23,))  # inc hl
            + bytes((0x36, 0x43))  # ld (hl),43h
            + bytes((0x2B,))  # dec hl
            + bytes((0x7E,))  # ld a,(hl)
            + bytes((0x32, 0x02, 0x90))  # ld (9002h),a
            + EXIT_CALL
        )
        cpu = z80sim.run(image(code))
        self.assertEqual(bytes(cpu.mem[0x9000 : 0x9003]), b'\x42\x43\x42')

    def test_immediate_alu_and_flag_sensitive_jumps(self):
        code = (
            bytes((0x3E, 0x7F))  # ld a,7Fh
            + bytes((0xC6, 0x01))  # add a,1 -> 80h: S=1, PV=1
            + bytes((0xFA, 0x0C, 0x41))  # jp m,410Ch (taken)
            + b'\x76' + bytes(4)  # halt + pad (4107h..410Bh)
            + bytes((0x32, 0x00, 0x90))  # ld (9000h),a
            + bytes((0xE6, 0))  # and 0 -> A=0, Z=1, H=1
            + bytes((0xCA, 0x17, 0x41))  # jp z,4117h (taken)
            + b'\x76' + bytes(2)  # halt + pad (4114h..4116h)
            + bytes((0xFE, 0))  # cp 0 -> Z=1, N=1
            + bytes((0x28, 0x02))  # jr z,+2 -> 411Dh
            + b'\x76' + bytes(1)  # halt + pad (411Bh..411Ch)
            + EXIT_CALL  # 411Dh
        )
        cpu = z80sim.run(image(code))
        self.assertTrue(cpu.exited)
        self.assertEqual(cpu.mem[0x9000], 0x80)

    def test_add_wraps_and_sets_zero_and_carry(self):
        code = (
            bytes((0x3E, 0xFF))  # ld a,0FFh
            + bytes((0xC6, 0x01))  # add a,1 -> A=0, Z=1, C=1
            + bytes((0xDA, 0x0C, 0x41))  # jp c,410Ch (taken)
            + b'\x76' + bytes(4)  # halt + pad (4107h..410Bh)
            + bytes((0x32, 0x00, 0x90))  # ld (9000h),a
            + EXIT_CALL
        )
        cpu = z80sim.run(image(code))
        self.assertTrue(cpu.exited)
        self.assertEqual(cpu.mem[0x9000], 0)


# ---------------------------------------------------------------------------
# Independent Stage-1 programs and the exact alert text each must produce.
# ---------------------------------------------------------------------------

ARITH_PRECEDENCE = """\
DIM R AS INTEGER
R = 2 + 3 * 4
MESSAGE "2+3*4=" + STR$(R)
END
"""

SIGNED_COMPARES = """\
DIM A AS INTEGER
DIM B AS INTEGER
A = -5
B = 3
IF A < B THEN
MESSAGE "LT signed"
END IF
IF B > A THEN
MESSAGE "GT signed"
END IF
IF -3 = -3 THEN
MESSAGE "EQ literal"
END IF
IF -3 <> 3 THEN
MESSAGE "NE literal"
END IF
END
"""

SUB_UNARY = """\
DIM A AS INTEGER
DIM B AS INTEGER
A = 10 - 4
B = -A
MESSAGE "diff=" + STR$(A)
MESSAGE "neg=" + STR$(B)
END
"""

INT_WRAP = """\
DIM A AS INTEGER
A = 32767
A = A + 1
MESSAGE "wrap=" + STR$(A)
END
"""

FOR_ASC = """\
DIM I AS INTEGER
DIM S AS INTEGER
S = 0
FOR I = 1 TO 5
S = S + I
NEXT I
MESSAGE "sum=" + STR$(S)
END
"""

FOR_DESC = """\
DIM I AS INTEGER
DIM S AS INTEGER
S = 0
FOR I = 5 TO 1 STEP -1
S = S + I
NEXT I
MESSAGE "dsum=" + STR$(S)
END
"""

FOR_ZERO = """\
DIM I AS INTEGER
DIM C AS INTEGER
C = 0
FOR I = 5 TO 1
C = C + 1
NEXT I
MESSAGE "count=" + STR$(C)
END
"""

FOR_ONCE = """\
DIM I AS INTEGER
DIM C AS INTEGER
C = 0
FOR I = 32767 TO 32767
C = C + 1
NEXT I
MESSAGE "once=" + STR$(C)
END
"""

NESTED_IF = """\
DIM A AS INTEGER
DIM B AS INTEGER
A = 5
B = 5
IF A < B THEN
MESSAGE "lt"
ELSE
IF A = B THEN
MESSAGE "eq"
ELSE
MESSAGE "gt"
END IF
END IF
END
"""

WHILE_COUNT = """\
DIM N AS INTEGER
N = 5
WHILE N > 0
MESSAGE "n=" + STR$(N)
N = N - 1
WEND
END
"""

STR_LITERAL = """\
DIM S AS STRING
S = "Hello PcW"
MESSAGE S
END
"""

STR_COPY = """\
DIM A AS STRING
DIM B AS STRING
A = "copy me"
B = A
MESSAGE B
END
"""

STR_FUNCS = """\
DIM N AS INTEGER
DIM X AS STRING
N = 42
X = STR$(N)
MESSAGE "n=" + X
X = LEFT$("PcW16", 2)
MESSAGE "left=" + X
X = RIGHT$("PcW16", 2)
MESSAGE "right=" + X
X = MID$("PcW16", 2, 3)
MESSAGE "mid=" + X
MESSAGE "len=" + STR$(LEN("PcW16"))
END
"""

STR_EQUAL = """\
DIM X AS STRING
DIM Y AS STRING
X = "ab"
Y = "ab"
IF X = Y THEN
MESSAGE "same"
END IF
Y = "cd"
IF X = Y THEN
MESSAGE "unexpected"
ELSE
MESSAGE "diff"
END IF
END
"""

DYN_TOTAL = """\
DIM T AS INTEGER
T = 2 + 3 * 4
MESSAGE "Total: " + STR$(T)
END
"""

LEN_EMPTY = """\
DIM E AS STRING
E = ""
MESSAGE "len=" + STR$(LEN(E))
END
"""

MSG_LITERAL = """\
MESSAGE "Exact text 123"
END
"""


@requires_pasmo
class TestGeneratedProgramBehaviour(unittest.TestCase):
    """Build independent .pbas programs and run them on the simulator.

    Requires Pasmo (tests/toolchain.py): a missing assembler is an error, not
    a skip. A failure is reported with the build output.
    """

    maxDiff = None

    def setUp(self):
        self.assertTrue(BUILD_TOOL.exists(), 'tools/build.py is missing')
        self.assertTrue(RUNTIME_SOURCE.exists(), 'runtime/runtime.z80.asm is missing')

    def _build(self, name: str, source: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix='pbw16-beh-') as tmp:
            src = Path(tmp) / f'{name}.pbas'
            prg = Path(tmp) / f'{name}.prg'
            src.write_text(source, encoding='utf-8')
            proc = subprocess.run(
                [sys.executable, str(BUILD_TOOL), str(src), '--prg', str(prg)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f'build failed for {name}.pbas:\n{proc.stdout}\n{proc.stderr}',
            )
            return prg.read_bytes()

    def assert_alerts(self, name: str, source: str, expected: list[str]) -> None:
        cpu = z80sim.run(self._build(name, source))
        self.assertTrue(cpu.exited, f'{name}: program did not stop via os_app_exit')
        self.assertEqual(cpu.alerts, expected)

    def test_arithmetic_precedence(self):
        self.assert_alerts('arith_precedence', ARITH_PRECEDENCE, ['2+3*4=14'])

    def test_signed_compare_paths(self):
        self.assert_alerts(
            'signed_compares',
            SIGNED_COMPARES,
            ['LT signed', 'GT signed', 'EQ literal', 'NE literal'],
        )

    def test_subtraction_and_unary_minus(self):
        self.assert_alerts('sub_unary', SUB_UNARY, ['diff=6', 'neg=-6'])

    def test_integer_wrap(self):
        self.assert_alerts('int_wrap', INT_WRAP, ['wrap=-32768'])

    def test_for_ascending_sum(self):
        self.assert_alerts('for_asc', FOR_ASC, ['sum=15'])

    def test_for_descending_step(self):
        self.assert_alerts('for_desc', FOR_DESC, ['dsum=15'])

    def test_for_zero_iterations(self):
        self.assert_alerts('for_zero', FOR_ZERO, ['count=0'])

    def test_for_32767_to_32767_executes_once(self):
        self.assert_alerts('for_once', FOR_ONCE, ['once=1'])

    def test_nested_if_else_chain(self):
        self.assert_alerts('nested_if', NESTED_IF, ['eq'])

    def test_while_countdown(self):
        self.assert_alerts(
            'while_count', WHILE_COUNT, ['n=5', 'n=4', 'n=3', 'n=2', 'n=1']
        )

    def test_string_literal_assignment(self):
        self.assert_alerts('str_literal', STR_LITERAL, ['Hello PcW'])

    def test_string_var_to_var_copy(self):
        self.assert_alerts('str_copy', STR_COPY, ['copy me'])

    def test_str_substrings_and_len(self):
        self.assert_alerts(
            'str_funcs',
            STR_FUNCS,
            ['n=42', 'left=Pc', 'right=16', 'mid=cW1', 'len=5'],
        )

    def test_string_equality_true_and_false(self):
        self.assert_alerts('str_equal', STR_EQUAL, ['same', 'diff'])

    def test_dynamic_message_concat(self):
        self.assert_alerts('dyn_total', DYN_TOTAL, ['Total: 14'])

    def test_len_of_empty_string(self):
        self.assert_alerts('len_empty', LEN_EMPTY, ['len=0'])

    def test_message_literal_exact_text(self):
        self.assert_alerts('msg_literal', MSG_LITERAL, ['Exact text 123'])


if __name__ == '__main__':
    unittest.main()
