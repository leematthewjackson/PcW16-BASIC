"""M8 BANKED arrays and STRING * n (LANGUAGE-SPEC §5.4).

Runs on the project simulator, whose memory-management model follows
ROSAN283 (os_ask_mem .. os_copy_24bit; tests/z80sim.py "M8 memory
management"):
- a program gets blocks filled with junk;
- any access to a block it does not own is an error;
- nothing is released for it at os_app_exit.
Every run is checked by the memory guard, and the blocks still held at exit
must be none. Engineering evidence, not XAnne.
"""
from __future__ import annotations

import unittest

import z80sim
from memguard import guarded_run
from pbas import SourceError, check_source, generate
from pbas.real import unpack
from toolchain import requires_pasmo

FOLDER = "\\PCW\\FOLDER01"


# All runs use the simulator's faithful os_copy_24bit (PCW045.SYS #5CB6,
# owner XAnne MEMDIAG): a copy ending exactly at the end of the owner's last
# block returns carry after copying; the runtime accepts only that carry
# (KNOWN-ISSUES KI-34, RollOverTests).


def run(src: str, **kw):
    r = guarded_run(src, **kw)
    assert r.violations == [], r.violations[:5]
    assert not r.cpu.exited or r.cpu.blocks_at_exit == [], f"blocks still held: {r.cpu.blocks_at_exit}"
    return r


def gets(log, fn):
    return [d for f, d in log if f == fn]


class FrontendTests(unittest.TestCase):
    def reject(self, src: str) -> str:
        with self.assertRaises(SourceError) as caught:
            generate(check_source(src))
        return caught.exception.message

    def test_rules(self):
        cases = {
            "DIM X AS INTEGER BANKED\n": "only an array can be BANKED",
            "DIM X(0) AS INTEGER BANKED\n": "a BANKED array has 1 to 32767 elements, got 0",
            "DIM X(32768) AS INTEGER BANKED\n": "a BANKED array has 1 to 32767 elements",
            "DIM X(300) AS INTEGER\n": "an array has 1 to 250 elements, got 300 (a larger array can be BANKED)",
            "DIM X AS INTEGER * 5\n": "* n gives a STRING its length",
            "DIM S$ AS STRING * 0\n": "STRING * n holds 1 to 126 characters, got 0",
            "DIM S$ AS STRING * 127\n": "STRING * n holds 1 to 126 characters, got 127",
            # 17 blocks of 2 + 16 blocks: 33 > 32
            "DIM A$(4000) AS STRING * 63 BANKED\nDIM B$(4000) AS STRING * 63 BANKED\n":
                "BANKED arrays may use at most 32 16K blocks together (512K); this one brings the total to 32",
            "DIM A(5) AS INTEGER BANKED\nDIM N AS INTEGER\nN = A(1) + A(2) + A(3) + A(4) + A(5)\n":
                "this statement reads 5 BANKED array elements; at most 4",
            'DIM A$(5) AS STRING BANKED\nDIM N AS INTEGER\nWINDOW "W"\nLIST N, A$, 5\n':
                "LIST cannot show the BANKED array A$",
        }
        for body, fragment in cases.items():
            with self.subTest(body=body):
                if "at most 32" in fragment:
                    body = body.replace("4000) AS STRING * 63", "4300) AS STRING * 63")
                    fragment = fragment.replace("to 32", "to 34")
                self.assertIn(fragment, self.reject(body + "END\n"))

    def test_accepted_and_still_names(self):
        generate(check_source("DIM Banked AS INTEGER\nBanked = 1\nDIM S$ AS STRING * 126\n"
                              "DIM A(32767) AS INTEGER BANKED\nDIM T$(10) AS STRING * 5\nEND\n"))


@requires_pasmo
class BehaviourTests(unittest.TestCase):
    def test_types_round_trip_and_start_at_zero(self):
        src = ('DIM I(3000) AS INTEGER BANKED\nDIM R(100) AS REAL BANKED\nDIM B(50) AS BOOLEAN BANKED\n'
               'DIM S$(500) AS STRING * 40 BANKED\n'
               'I(3000) = -12345\nR(100) = 2.5\nB(50) = TRUE\nS$(500) = "the last one"\n'
               'MESSAGE STR$(I(3000)) + " " + STR$(R(100)) + " " + S$(500)\n'
               'IF B(50) AND NOT B(1) THEN\nMESSAGE "bool ok"\nEND IF\n'
               'MESSAGE "[" + STR$(I(1)) + STR$(R(1)) + S$(1) + "]"\n'
               'S$(2) = "the last one"\nIF S$(500) = S$(2) AND S$(1) <> S$(2) THEN\nMESSAGE "cmp ok"\nEND IF\nEND\n')
        r = run(src)
        self.assertEqual(r.cpu.alerts, ["-12345 2.5 the last one", "bool ok", "[00]", "cmp ok"])
        self.assertEqual(gets(r.cpu.os_log, z80sim.FN_OS_GET_MEM), [(5, 5)])  # 1 + 1 + 1 + 2 blocks
        self.assertEqual(len(gets(r.cpu.os_log, z80sim.FN_OS_RELEASE_MEM)), 1)

    def test_block_boundaries(self):
        # STRING * 40 = 41 bytes: 399 per block, so 399 / 400 straddle blocks 1 / 2
        # and 798 / 799 blocks 2 / 3; INTEGER: 8192 per block.
        src = ('DIM S$(1200) AS STRING * 40 BANKED\nDIM N(20000) AS INTEGER BANKED\nDIM K AS INTEGER\n'
               'FOR K = 397 TO 402\nS$(K) = "s" + STR$(K)\nNEXT K\nFOR K = 796 TO 801\nS$(K) = "t" + STR$(K)\nNEXT K\n'
               'S$(1200) = "end"\nN(8192) = 1\nN(8193) = 2\nN(16384) = 3\nN(16385) = 4\nN(20000) = 5\n'
               'MESSAGE S$(398) + S$(399) + S$(400)\nMESSAGE S$(401) + S$(797) + S$(798)\n'
               'MESSAGE S$(799) + S$(1200)\n'
               'MESSAGE STR$(N(8192)) + STR$(N(8193)) + STR$(N(16384)) + STR$(N(16385))\n'
               'MESSAGE STR$(N(20000)) + STR$(N(8191)) + STR$(N(1))\nEND\n')
        r = run(src)
        self.assertEqual(r.cpu.alerts, ["s398s399s400", "s401t797t798", "t799end", "1234", "500"])
        copies = gets(r.cpu.os_log, z80sim.FN_OS_COPY_24BIT)
        self.assertTrue(all(off + n <= 0x4000 and doff + n <= 0x4000 for _, off, _, doff, n in copies))

    def test_data_spans_many_blocks_with_its_own_contents(self):
        # 6 blocks of REAL (3276 per block): each element keeps its own value
        src = ('DIM V(19000) AS REAL BANKED\nDIM K AS INTEGER\nDIM T AS REAL\n'
               'FOR K = 1 TO 19000 STEP 997\nV(K) = K * 0.5\nNEXT K\n'
               'FOR K = 1 TO 19000 STEP 997\nT = T + V(K)\nNEXT K\nMESSAGE STR$(T)\nEND\n')
        r = run(src, max_steps=30_000_000)
        want = sum(k * 0.5 for k in range(1, 19001, 997))
        self.assertEqual(r.cpu.alerts, [str(int(want)) if want == int(want) else f"{want:g}"])
        self.assertEqual(gets(r.cpu.os_log, z80sim.FN_OS_GET_MEM), [(6, 6)])

    def test_index_errors(self):
        # M14 (D8): a literal index outside the array is a compile error now, so the run-time
        # check is exercised with computed indexes (N is 0): the same values, the same line 5
        for stmt in ("N = A(N + 0)", "N = A(N + 11)", "N = A(N - 1)", "A(N + 11) = 1", "A(N) = 1",
                     "LINE INPUT #1, S$(4)"):
            with self.subTest(stmt=stmt):
                src = ('DIM A(10) AS INTEGER BANKED\nDIM S$(3) AS STRING BANKED\nDIM N AS INTEGER\n'
                       'OPEN "X.TXT" FOR INPUT AS #1\n' + stmt + "\nEND\n")
                r = run(src, disk=z80sim.Disk(files={(FOLDER, "X.TXT"): b"a\r\n"}))
                self.assertEqual(r.cpu.alerts, ["Runtime error: index out of range at line 5"])
        for stmt in ("N = A(0)", "N = A(11)", "N = A(-1)", "A(11) = 1", "A(0) = 1"):
            with self.subTest(literal=stmt), self.assertRaises(SourceError) as caught:
                check_source('DIM A(10) AS INTEGER BANKED\nDIM N AS INTEGER\n' + stmt + "\nEND\n")
            self.assertIn("is outside the array", caught.exception.message)

    def test_not_enough_memory(self):
        src = 'DIM A(10) AS INTEGER\nDIM Big$(1000) AS STRING BANKED\nA(1) = 5\nMESSAGE "ran"\nEND\n'
        for free in (0, 1, 3):
            with self.subTest(free=free):
                r = run(src, free_blocks=free)
                self.assertEqual(r.cpu.alerts,
                                 ["Runtime error: not enough free memory for BANKED arrays at line 2"])
                self.assertEqual(r.cpu.blocks_at_exit, [])
                # nothing was written into the partial allocation
                self.assertEqual(gets(r.cpu.os_log, z80sim.FN_OS_COPY_24BIT), [])
        self.assertEqual(run(src, free_blocks=4).cpu.alerts, ["ran"])  # exactly enough

    def test_refuses_blocks_it_does_not_own(self):
        src = 'DIM A(10) AS INTEGER BANKED\nMESSAGE "ran"\nEND\n'
        for owner in (0x0108, 0x0000, 0x0081):  # another application, free, the OS
            for own in (None, 0x0081):  # the program's own id known, or not (then any #01xx)
                with self.subTest(owner=hex(owner), own=own):
                    hook = {z80sim.MEM_POOL[0]: owner}
                    if own is not None:
                        hook[z80sim.FAKE_APP_BANK] = own
                    r = run(src, mem_owner=hook)
                    if own is not None and owner == 0x0108:  # any application id is accepted then
                        self.assertEqual(r.cpu.alerts, ["ran"])
                        continue
                    self.assertEqual(r.cpu.alerts,
                                     ["Runtime error: not enough free memory for BANKED arrays at line 1"])
                    self.assertEqual(gets(r.cpu.os_log, z80sim.FN_OS_COPY_24BIT), [])

    def test_a_failed_copy_stops_the_program(self):
        r = run('DIM A(10) AS INTEGER BANKED\nMESSAGE "ran"\nEND\n', mem_copy_fails=True)
        self.assertEqual(r.cpu.alerts, ["Runtime error: a BANKED array block could not be copied at line 1"])
        self.assertEqual(r.cpu.blocks_at_exit, [])

    def test_released_on_every_exit(self):
        head = 'DIM A(10) AS INTEGER BANKED\n'
        for name, src, kw in (
                ("END", head + "A(1) = 1\nEND\n", {}),
                ("error", head + "A(1) = 1 / A(2)\nEND\n", {}),
                ("EXIT in a handler", head + 'WINDOW "W"\nBUTTON "Q", Q\nSUB Q\nEXIT\nEND SUB\nEND\n',
                 {"events": [("click", 2)]}),
                ("system quit", head + 'WINDOW "W"\nBUTTON "Q", Q\nSUB Q\nEND SUB\nEND\n',
                 {"events": [("exit",)]})):
            with self.subTest(exit=name):
                r = run(src, **kw)
                self.assertTrue(r.cpu.exited)
                self.assertEqual(r.cpu.blocks_at_exit, [])
                self.assertEqual(len(gets(r.cpu.os_log, z80sim.FN_OS_RELEASE_MEM)), 1)

    def test_files_with_banked_elements(self):
        src = ('DIM L$(300) AS STRING * 30 BANKED\nDIM N AS INTEGER\nDIM K AS INTEGER\n'
               'OPEN "IN.TXT" FOR INPUT AS #1\nWHILE NOT EOF(1)\nN = N + 1\nL$(N) = "keep"\nL$(300) = "other"\n'
               'LINE INPUT #1, L$(N)\nIF IOERR <> 0 THEN\nMESSAGE "line " + STR$(N) + " error " + STR$(IOERR)\nEND IF\n'
               'WEND\nCLOSE #1\nOPEN "OUT.TXT" FOR OUTPUT AS #2\nFOR K = N TO 1 STEP -1\nPRINT #2, L$(K)\nNEXT K\n'
               'CLOSE #2\nMESSAGE STR$(N)\nEND\n')
        lines = [f"row {i}" for i in range(1, 201)] + ["x" * 40, "last"]
        disk = z80sim.Disk(files={(FOLDER, "IN.TXT"): "".join(f"{t}\r\n" for t in lines).encode()})
        r = run(src, disk=disk, max_steps=40_000_000)
        self.assertEqual(r.cpu.alerts, ["line 201 error 243", "202"])
        out = disk.files[(FOLDER, "OUT.TXT")].decode().split("\r\n")[:-1]
        # the too-long line left its element unchanged ("keep")
        self.assertEqual(out, ["last", "keep"] + [f"row {i}" for i in range(200, 0, -1)])

    def test_procedures_and_sorting(self):
        src = ('DIM W$(400) AS STRING * 12 BANKED\nDIM N AS INTEGER\nDIM I AS INTEGER\nDIM J AS INTEGER\n'
               'DIM T$ AS STRING\nFUNCTION Key$(K AS INTEGER) AS STRING\nRETURN W$(K)\nEND FUNCTION\n'
               'SUB Swap(A AS INTEGER, B AS INTEGER)\nT$ = W$(A)\nW$(A) = W$(B)\nW$(B) = T$\nEND SUB\n'
               'N = 40\nFOR I = 1 TO N\nW$(I) = STR$((I * 37) MOD 41)\nNEXT I\n'
               'FOR I = 1 TO N - 1\nFOR J = 1 TO N - I\nIF VAL(Key$(J)) > VAL(Key$(J + 1)) THEN\n'
               'CALL Swap(J, J + 1)\nEND IF\nNEXT J\nNEXT I\n'
               'MESSAGE W$(1) + "," + W$(2) + "," + W$(39) + "," + W$(40)\nEND\n')
        r = run(src, max_steps=40_000_000)
        values = sorted((i * 37) % 41 for i in range(1, 41))
        self.assertEqual(r.cpu.alerts, [f"{values[0]},{values[1]},{values[38]},{values[39]}"])

    def test_gui_handler_uses_banked_data(self):
        src = ('DIM Log$(1000) AS STRING * 20 BANKED\nDIM N AS INTEGER\nDIM Shown$ AS STRING\n'
               'WINDOW "W"\nTEXTBOX Entry$, "Entry"\nLABEL Shown$\nBUTTON "Add", AddIt\n'
               'SUB AddIt\nN = N + 1\nLog$(N) = Entry$\nShown$ = STR$(N) + ": " + Log$(N) + " / " + Log$(1)\nEND SUB\nEND\n')
        from test_list_rows import objects
        o = objects(src)
        r = run(src, events=[("edit", o["ENTRY$"], "first"), ("click", o["Add"]),
                             ("edit", o["ENTRY$"], "second"), ("click", o["Add"])])
        self.assertEqual(r.cpu.label_text(o["SHOWN$"], shown=True), "2: second / first")

    def test_string_star_n(self):
        src = ('DIM S$ AS STRING * 5\nDIM L$(3) AS STRING * 120\nS$ = "12345"\n'
               'L$(1) = STRING$(120, 65)\nMESSAGE S$ + STR$(LEN(L$(1)))\nS$ = S$ + "6"\nEND\n')
        r = run(src)
        self.assertEqual(r.cpu.alerts, ["12345120", "Runtime error: string too long at line 6"])

    def test_textbox_holds_what_its_variable_holds(self):
        # regression (found in M8 review): the box used the program-wide
        # capacity, so typing more than n characters overran a STRING * n
        from pbas.layout import build_dialog
        src = ('DIM N$ AS STRING * 10\nWINDOW "w"\nTEXTBOX N$, "n"\nBUTTON "Go", G\n'
               'SUB G\nMESSAGE N$\nEXIT\nEND SUB\nEND\n')
        program = check_source(src)
        lay = build_dialog(program, program.windows[0], False)
        row = next(b for b in lay.bindings if b.var_name == "N$")
        self.assertEqual(row.capacity, 11)
        number = row.number
        r = run(src, events=[("edit", number, "A" * 10), ("click", next(o.number for o in lay.objects
                                                                         if o.kind == "BUTTON"))])
        self.assertEqual(r.cpu.alerts, ["A" * 10])
        with self.assertRaisesRegex(AssertionError, "exceeds max length 10"):
            run(src, events=[("edit", number, "A" * 11)])

    def test_star_n_after_the_widget_is_an_error(self):
        with self.assertRaisesRegex(SourceError, r"DIM N\$ AS STRING \* 10 must come before the TEXTBOX at line 2"):
            check_source('WINDOW "w"\nTEXTBOX N$, "n"\nDIM N$ AS STRING * 10\nBUTTON "Q", Q\nSUB Q\nEXIT\nEND SUB\nEND\n')
        check_source('WINDOW "w"\nTEXTBOX N$, "n"\nDIM N$ AS STRING\nBUTTON "Q", Q\nSUB Q\nEXIT\nEND SUB\nEND\n')


@requires_pasmo
class RollOverTests(unittest.TestCase):
    """KI-34: the end-of-last-block carry is harmless, every other carry is
    fatal. Faithful copy model; carries Rosanne would not give are forced
    with the copy_carry_if hook (bytes copied first, as Rosanne does)."""

    def test_start_up_clears_every_block_including_the_last(self):
        r = run("DIM A(10) AS INTEGER BANKED\nA(1) = 1\nMESSAGE STR$(A(1)) + STR$(A(10))\nEND\n")
        self.assertEqual(r.cpu.alerts, ["10"])
        self.assertEqual(len(r.cpu.copy_end_errors), 1)  # the 64th clearing copy of block #90

    def test_elements_ending_at_a_block_end(self):
        # INTEGER: 8192 per block, so A(8192) ends at #4000 of block 1 (block 2
        # follows: no carry) and A(16384) at #4000 of block 2, the last (carry)
        src = ('DIM A(16384) AS INTEGER BANKED\nDIM S$(1024) AS STRING * 15 BANKED\n'
               'A(8192) = 81\nA(8193) = 82\nA(16384) = -1\nS$(1024) = "last of block"\n'
               'MESSAGE STR$(A(8192)) + " " + STR$(A(8193)) + " " + STR$(A(16384)) + " " + S$(1024)\n'
               'A(16384) = A(16384) - 1\nMESSAGE STR$(A(16384))\nEND\n')
        r = run(src)
        self.assertEqual(r.cpu.alerts, ["81 82 -1 last of block", "-2"])
        self.assertEqual(r.cpu.mem_free[-3:], [0x90, 0x91, 0x92])  # all three released
        last = [e for e in r.cpu.copy_end_errors if e[2] == 0x92 or e[0] == 0x92]
        self.assertTrue(last and all(e[2] == 0x92 or e[0] == 0x92 for e in r.cpu.copy_end_errors))

    def test_write_back_checks_its_own_element(self):
        # the element written back (A(16384), ends at the last block's end) is
        # not the one read last (A(1) or S$(1), in block #90): the check must
        # use the written element's block and offset
        src = ('DIM A(16384) AS INTEGER BANKED\nDIM S$(1024) AS STRING * 15 BANKED\nA(1) = 41\n'
               'A(16384) = A(1) + 1\nS$(1) = "x"\nS$(1024) = S$(1) + "y"\n'
               'MESSAGE STR$(A(16384)) + S$(1024)\nEND\n')
        self.assertEqual(run(src).cpu.alerts, ["42xy"])

    def test_end_of_a_block_that_has_a_successor_is_not_excused(self):
        # forced carry at the end of block 1 of 2: Rosanne would roll over; a
        # carry there is a real failure
        src = 'DIM A(16384) AS INTEGER BANKED\nA(8192) = 1\nEND\n'
        r = run(src, copy_carry_if=lambda c: c[2] == 0x90 and c[3] + c[4] == 0x4000 and c[4] == 2)
        self.assertEqual(r.cpu.alerts, ["Runtime error: a BANKED array block could not be copied at line 2"])
        self.assertEqual(r.cpu.blocks_at_exit, [])

    def test_carry_before_the_end_of_the_last_block_is_not_excused(self):
        src = 'DIM A(100) AS INTEGER BANKED\nA(50) = 1\nEND\n'
        r = run(src, copy_carry_if=lambda c: c[2] == 0x90 and c[3] == 98)
        self.assertEqual(r.cpu.alerts, ["Runtime error: a BANKED array block could not be copied at line 2"])
        self.assertEqual(r.cpu.blocks_at_exit, [])

    def test_reads_and_write_back_with_a_forced_carry_mid_block(self):
        for line, pred in ((2, lambda c: c[0] == 0x90 and c[4] == 2),  # read from the block
                           (3, lambda c: c[2] == 0x90 and c[4] == 2)):  # write back into it
            with self.subTest(line=line):
                src = 'DIM A(100) AS INTEGER BANKED\nMESSAGE STR$(A(7))\nA(7) = 3\nEND\n'
                r = run(src, copy_carry_if=pred)
                self.assertEqual(r.cpu.alerts[-1], f"Runtime error: a BANKED array block could not be copied at line {line}")
                self.assertEqual(r.cpu.blocks_at_exit, [])

    def test_a_copy_that_fails_outright_still_stops_the_program(self):
        r = run("DIM A(10) AS INTEGER BANKED\nA(1) = 1\nEND\n", mem_copy_fails=True)
        self.assertEqual(r.cpu.alerts, ["Runtime error: a BANKED array block could not be copied at line 1"])
        self.assertEqual(r.cpu.blocks_at_exit, [])


if __name__ == "__main__":
    unittest.main()
