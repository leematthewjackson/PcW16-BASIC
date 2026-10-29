"""Tier-3/4 tests for the hand-written M2 runtime (runtime/runtime.z80.asm).

Proves, without executing anything:

- the textual contract: every required rt_* label present exactly once,
  wrapper headers cite the right ROSAN283 function numbers and register
  contracts, no `org` directive, no IX/IY register usage (A5 discipline),
  and `call 003Bh` appears only inside rt_exit / rt_alert (A4);
- structural sanity (A1-lite): every call/jp/djnz target is defined;
- tier 4: the runtime assembles standalone under Pasmo (org prepended
  synthetically) with a non-trivial image size;
- once tools/asmcheck.py lands, the A-rule lint runs against this file.

No behavioural simulation: per TESTING-STRATEGY.md a Python simulation of
Rosanne is not a test tier, and XAnne evidence (tier 5) is owner-executed.
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from toolchain import requires_pasmo

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime" / "runtime.z80.asm"
ASMCHECK = ROOT / "tools" / "asmcheck.py"

TEXT: str
CODE_LINES: list[str]

# Code routines (labels whose section must terminate in a ret/jp path).
CODE_ROUTINES = (
    "rt_exit",
    "rt_alert",
    "rt_alert_dynamic",
    "rt_err_string_overflow",
    "rt_gui_run",
    "rt_gui_failed",
    "rt_gui_loop",
    "rt_gui_process",
    "rt_gui_after",
    "rt_bind_start",
    "rt_bind_next",
    "rt_bind_load",
    "rt_bind_set_end",
    "rt_ctl_locate",
    "rt_ctl_read_text",
    "rt_ctl_read_check",
    "rt_sync_in",
    "rt_sync_out",
    "rt_redraw_checks",
    "rt_ctl_failed",
    "rt_mul16",
    "rt_compare_signed",
    "rt_append_int",
    "rt_str_len",
    "rt_str_skip",
    "rt_put",
    "rt_str_copy",
    "rt_str_compare",
    # M4 files (IF PB_FILES)
    "rt_file_save",
    "rt_file_load",
    "rt_file_prepare",
    "rt_low_copy",
    "rt_file_os_error",
    "rt_file_report",
    "rt_put_hex",
    "rt_put_nibble",
    # M5a substrings (IF PB_SLICE)
    "rt_chk_count",
    "rt_chk_start",
    "rt_slice_mid",
    "rt_slice_right",
    "rt_err_substring",
    # M5b numbers and text (IF PB_DIV / PB_VAL / PB_ASC / PB_CHR / PB_INSTR)
    "rt_div16",
    "rt_mod16",
    "rt_divmod",
    "rt_neg_hl",
    "rt_err_div",
    "rt_val",
    "rt_err_val",
    "rt_asc",
    "rt_chr_put",
    "rt_err_chr",
    "rt_instr",
    "rt_err_msg",
    # M5c case conversion (IF PB_CASE)
    "rt_ucase",
    "rt_lcase",
    # M7 sequential files (IF PB_FIO)
    "rt_fio_open",
    "rt_fio_prep_fail",
    "rt_fio_slot",
    "rt_fio_fetch",
    "rt_fio_close",
    "rt_fio_close_all",
    "rt_fio_close_one",
    "rt_fio_print",
    "rt_fio_input",
    "rt_fio_eof",
    "rt_fio_kill",
    "rt_fio_name",
    # M8 BANKED arrays (IF PB_BANK)
    "rt_bank_init",
    "rt_bank_free",
    "rt_bank_get",
    "rt_bank_wref",
    "rt_bank_put",
    "rt_bank_locate",
    "rt_bk_udiv",
    "rt_bk_copy",
    # M9 code banks (IF PB_CODEBANKS)
    "rt_code_load",
    "rt_cl_read",
    "rt_code_unread",
    "rt_code_short",
    "rt_code_free",
    "rt_farcall",
    "rt_fc_jump",
    # M9 CANVAS (IF PB_CANVAS)
    "rt_cv_open",
    "rt_cv_after",
    "rt_cv_raw",
    "rt_cv_local",
    "rt_cv_inside",
    "rt_cv_objevent",
    "rt_cv_span",
    "rt_cv_ready",
    "rt_cv_rect",
    "rt_cv_point",
    "rt_cv_outside",
    "rt_cv_dg",
    "rt_cv_empty",
    "rt_draw_clear",
    "rt_draw_fill",
    "rt_draw_invert",
    "rt_draw_scroll",
    "rt_cv_neg",
    "rt_cv_shift_ok",
    "rt_cv_abs",
    "rt_cv_bios",
    "rt_cv_par",
    "rt_draw_pixel",
    "rt_draw_line",
    "rt_draw_box",
    "rt_draw_text",
    "rt_draw_cells",  # M11
    "rt_text_width",  # M11 corrective: TEXTWIDTH, SECONDS
    "rt_seconds",
    "rt_draw_font",  # M15 W2: DRAW FONT, the measured cut, ALIGN
    "rt_cv_tw",
    "rt_cv_text_fit",
    "rt_cv_fits",
    "rt_gui_stopsel",  # M15 W1: Tasks > Stop in a program with ON STOP and no menus
    "rt_gui_stop",
    "rt_type_font",  # M15 W3: screen typography (IF PB_TYPO)
    "rt_ty_ready",
    "rt_ty_want",
    "rt_ty_px_up",
    "rt_ty_adv",
    "rt_ty_start",
    "rt_ty_step",
    "rt_type_width",
    "rt_type_height",
    "rt_draw_type",
    "rt_ty_pgslot",
    "rt_draw_on",  # M15 W4: several canvases (IF PB_CVMULTI)
    "rt_cvm_restore",
    "rt_cvm_next",
    "rt_cvm_select",
    "rt_cvm_entry",
    "rt_cvm_save",
    "rt_cvm_load",
    "rt_cvm_slot",
    "rt_cvm_win_ok",
    "rt_cvm_mask",
    "rt_cvm_first",
    "rt_cvm_raw",
    "rt_cvm_keys",
    "rt_cvm_oe_pick",
    "rt_rbc",  # M11 runtime bank
    "rt_rbc_back",
    # M9 TEXT buffers and file names (IF PB_TEXT, PB_FNAME)
    "rt_tx_enter",
    "rt_tx_leave",
    "rt_tx_unmap",
    "rt_tx_fail",
    "rt_tx_addr",
    "rt_tx_phys",
    "rt_tx_get",
    "rt_tx_len_all",
    "rt_tx_gap_to",
    "rt_tx_move",
    "rt_tx_min",
    "rt_tx_room_after",
    "rt_tx_room_before",
    "rt_tx_put",
    "rt_tx_room",
    "rt_tx_seek",
    "rt_tx_col",
    "rt_tx_bad_pos",
    "rt_tx_full",
    "rt_text_len",
    "rt_text_free",
    "rt_text_used",
    "rt_text_get",
    "rt_text_find",
    "rt_tx_atend",
    "rt_text_clear",
    "rt_tx_reset",
    "rt_text_insert",
    "rt_text_delete",
    "rt_text_split",
    "rt_text_join",
    "rt_text_load",
    "rt_text_io",
    "rt_text_save",
    "rt_tx_write_run",
    "rt_fname",
    "rt_rec_zfill",  # M10
    "rt_tx_range",
    "rt_tx_pos",
    "rt_tx_whole",
    "rt_tx_count_lf",
    "rt_tx_read_chunk",
    "rt_tx_next_chunk",
    "rt_tx_advance",
    "rt_tx_xfer",
    "rt_text_remove",
    "rt_text_copy",
    "rt_text_paste",
    "rt_text_same",
    "rt_db_setup",
    "rt_db_ncheck",
    "rt_db_prepare",
    "rt_db_ext_is",
    "rt_db_ext",
    "rt_db_name",
    "rt_db_delete_file",
    "rt_db_rename",
    "rt_db_owns",  # M14 (KI-91)
    "rt_db_own",
    "rt_db_strs_ok",  # M14: STRING fields of a loaded record
    "rt_db_read",
    "rt_db_need",
    "rt_db_sum",
    "rt_db_write",
    "rt_db_wlocate",
    "rt_db_zero",
    "rt_db_peek",
    "rt_db_load_one",
    "rt_db_close_r",
    "rt_db_load",
    "rt_db_save",
    "rt_db_new",
    "rt_db_delete",
    "rt_db_find",
    "rt_db_nextid",
    "rt_db_order",
    "rt_db_oaddr",
    "rt_db_fkey",
    "rt_db_cmp",
    "rt_db_cmp_real",
    "rt_db_rclass",
    "rt_db_sort",
    "rt_db_pattern",
    "rt_db_search",
    "rt_db_contains",
    "rt_fname_upper",
    "rt_fname_char",
    "rt_bmp_blk",  # M12 BITMAPs (IF PB_BITMAP, PB_BMPFILE)
    "rt_bmp_white",
    "rt_bmp_bpr",
    "rt_bmp_get",
    "rt_bmp_big",
    "rt_bmp_put",
    "rt_bmp_mask",  # M13 parts and masks (IF PB_BMPPART)
    "rt_bmp_part",
    "rt_bmp_inside",
    "rt_bmp_quot",
    "rt_bmp_fewer",
    "rt_bmp_fetch",
    "rt_bmp_begin",
    "rt_bmp_end",
    "rt_bmp_blit",
    "rt_keydown",  # M13 held keys (IF PB_KEYDOWN)
    "rt_clockticks",  # M13 corrective: CLOCKTICKS (IF PB_CLOCKTICKS)
    "rt_point",
    "rt_bmp_header",
    "rt_bmp_save",
    "rt_bmp_load",
    "rt_bmp_read",
    "rt_bmp_range",
    "rt_pg_need",  # M12 printing (IF PB_PAGE)
    "rt_pg_outside",
    "rt_pg_25",
    "rt_pg_range",
    "rt_pg_family",
    "rt_pg_new",
    "rt_pg_font",
    "rt_pg_char",
    "rt_pg_text",
    "rt_pg_width",
    "rt_pg_fill",
    "rt_pg_solid",
    "rt_pg_rect",
    "rt_pg_line",
    "rt_pg_order",
    "rt_pg_box",
    "rt_pg_vbar",
    "rt_pg_print",
    "rt_pg_close",
)

# Data labels (storage declarations, checked separately).
DATA_LABELS = (
    "rt_db_magic",  # M10: the database file's constant texts (code section)
    "rt_db_x_new",
    "rt_db_x_bak",
    "rt_bmp_magic",  # M12
    "rt_pg_block",
    "rt_pg_sizes",
    "rt_bank_n",  # M8
    "rt_bank_list",
    "rt_alert_buf",
    "rt_alert_keys",
    "rt_cmp_buf1",
    "rt_cmp_buf2",
    "rt_int_scratch",
    "rt_dst_end",
    "rt_err_line",
    "rt_err_text",
    "rt_err_text_end",
    "rt_gui_fail_alert",
    "rt_gui_fail_alert_end",
    "rt_dialog_open",
    "rt_gui_table",
    "rt_gui_object",
    "rt_gui_evtype",
    "rt_gui_handler",
    "rt_ctl_fail_alert",
    "rt_ctl_fail_alert_end",
    "rt_gui_bindings",
    "rt_bind_row",
    "rt_bind_left",
    "rt_bind_mode",
    "rt_bind_obj",
    "rt_bind_kind",
    "rt_bind_var",
    "rt_bind_cap",
    "rt_bind_tpl",
    "rt_bind_dst",
    "rt_bind_off",
    "rt_bind_val",
    "rt_obj_buf",
    "rt_file_buf",
    "rt_file_desc",
    "rt_file_var",
    "rt_file_cap",
    "rt_file_len",
    "rt_file_op",
    "rt_file_reason",
    "rt_file_code",
    "rt_file_t_saved",
    "rt_file_t_loaded",
    "rt_file_t_not",
    "rt_file_t_open",
    "rt_file_t_folder",
    "rt_file_t_nottext",
    "rt_file_t_drive",
    "rt_file_t_error",
    "rt_file_t_longer",
    "rt_file_t_chars",
    "rt_err_sub_text",
    "rt_err_sub_text_end",
    "rt_str_tmp3",
    "rt_str_tmp4",
    "rt_str_tmp5",
    "rt_str_tmp6",
    "rt_slc_count",
    "rt_err_div_text",
    "rt_err_div_text_end",
    "rt_err_val_text",
    "rt_err_val_text_end",
    "rt_err_chr_text",
    "rt_err_chr_text_end",
    "rt_div_qsign",
    "rt_div_rsign",
    "rt_val_neg",
    "rt_ins_pos",
    "rt_ins_ndl",
)


def setUpModule() -> None:
    global TEXT, CODE_LINES
    if not RUNTIME.exists():
        raise RuntimeError(f"runtime source missing: {RUNTIME}")
    TEXT = RUNTIME.read_text(encoding="utf-8")
    # Instruction view: comments stripped, blank lines dropped. Quoted
    # documentation (e.g. the os_alert "BC, DE, HL, IX, IY corrupt" contract)
    # lives in comments and is therefore not mistaken for register use.
    CODE_LINES = [
        line.split(";", 1)[0].rstrip()
        for line in TEXT.splitlines()
    ]
    CODE_LINES = [line for line in CODE_LINES if line.strip()]


def sections() -> dict[str, list[str]]:
    """Map each column-0 label to the instruction lines directly under it."""
    result: dict[str, list[str]] = {}
    current = "<header>"
    for line in CODE_LINES:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):", line)
        if m:
            current = m.group(1)
            result.setdefault(current, [])
            continue
        result[current].append(line.strip())
    return result


TOP_LEVEL = frozenset(CODE_ROUTINES + DATA_LABELS)


def routine_body(label: str) -> list[str]:
    """All instructions of a routine, across its internal local labels.

    A routine runs from its own label until the next top-level label
    (another routine or a data label); label lines of internal locals
    (e.g. rt_mul16_loop:) belong to the routine and are skipped.
    """
    lines = CODE_LINES
    start = next(
        i for i, line in enumerate(lines)
        if re.match(rf"^{re.escape(label)}:", line)
    )
    body_lines: list[str] = []
    for line in lines[start + 1:]:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):", line)
        if m and m.group(1) in TOP_LEVEL:
            break
        if m:
            continue
        body_lines.append(re.sub(r"\s+", " ", line).strip())
    return body_lines


def body(label: str) -> list[str]:
    """Instruction lines directly under a label with no internal locals."""
    return [re.sub(r"\s+", " ", line).strip() for line in sections()[label]]


class TestTextualContract(unittest.TestCase):
    """Static contract of runtime.z80.asm (TESTING-STRATEGY.md tier 3)."""

    def test_required_labels_present(self) -> None:
        found = set(sections())
        for label in CODE_ROUTINES + DATA_LABELS:
            with self.subTest(label=label):
                self.assertIn(label, found)

    def test_labels_defined_exactly_once(self) -> None:
        defined = re.findall(r"^([A-Za-z_][A-Za-z0-9_]*):", "\n".join(CODE_LINES), re.M)
        for label in set(defined):
            with self.subTest(label=label):
                self.assertEqual(defined.count(label), 1)

    def test_no_two_symbols_differ_only_in_case(self) -> None:
        # M12: the runtime bank imports resident symbols except its own
        # labels, compared without case (pbas/rtbank.py bank_text), so an
        # equ RT_BMP_STRIP beside a moved label rt_bmp_strip went unimported
        names = re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)(?::|\s+equ\b)", "\n".join(CODE_LINES), re.M | re.I)
        seen: dict[str, str] = {}
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(seen.setdefault(name.lower(), name), name)

    def test_no_org_directive(self) -> None:
        for line in CODE_LINES:
            with self.subTest(line=line):
                self.assertIsNone(re.match(r"\s*org\b", line, re.IGNORECASE))

    def test_ix_only_in_event_loop_and_no_iy(self) -> None:
        # A5 (M3a): IY never appears; IX only as the event record returned by
        # os_wait_event, i.e. inside rt_gui_loop. Comment-stripped, so the
        # quoted 'IX, IY corrupt' doc lines are not hits.
        for label, lines in sections().items():
            for line in lines:
                with self.subTest(routine=label, line=line):
                    # M7: rt_fio_name loads IX / IY as os_rename_file's inputs
                    # (new name, extension) — checked separately below.
                    # M10: rt_db_rename likewise (the database's backup steps).
                    if label not in ("rt_fio_name", "rt_db_rename"):
                        self.assertIsNone(re.search(r"\biy\b", line, re.IGNORECASE))
                    # M6: rt_gui_menu reads a menu selection's record (+2
                    # title, +3 entry) straight after os_wait_event too.
                    # M9: rt_cv_raw / rt_cv_keyev read a raw mouse or key
                    # event's record, before any OS call (checked below).
                    # M12: the print lines' thickness is IX (os_meta_hline / vline)
                    # M15: rt_gui_stopsel reads a menu selection's title and entry likewise.
                    if label not in ("rt_gui_loop", "rt_gui_menu", "rt_gui_stopsel", "rt_fio_name", "rt_db_rename", "rt_bk_copy",
                                     "rt_cv_raw", "rt_cv_keyev", "rt_pg_solid", "rt_pg_solid_w",
                                     "rt_pg_vbar", "rt_ty_d_next"):  # M15: os_typo_charscreen's style, mode
                        self.assertIsNone(re.search(r"\bix\b", line, re.IGNORECASE))
        # M15: DRAW TYPE's IX is os_typo_charscreen's input only, kept around the call
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in routine_body("rt_draw_type")]
        uses = [i for i, ln in enumerate(lines) if re.search(r"\bix\b", ln)]
        self.assertEqual([lines[i] for i in uses], ["pop ix"])
        self.assertEqual(lines[uses[0] + 1:uses[0] + 8], ["ld hl,(rt_ty_x0)", "ld de,(rt_ty_px)", "add hl,de",
                                                         "ex de,hl", "ld hl,(rt_ty_sy)", "ld a,93",
                                                         "call 003Bh"])
        # M9: the canvas's raw-event path reads the record and makes no OS call.
        self.assertFalse(any(re.search(r"\bcall\s+003[Bb]h?\b", ln) for ln in routine_body("rt_cv_raw")))
        # M8 rt_bk_copy: IX is only loaded, as os_copy_24bit's length input,
        # just before the call, and never read.
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in routine_body("rt_bk_copy")]
        uses = [i for i, ln in enumerate(lines) if re.search(r"\bi[xy]\b", ln)]
        self.assertEqual([lines[i] for i in uses], ["pop ix"])
        self.assertEqual(lines[uses[0] + 1: uses[0] + 4], ["pop hl", "ld a,41", "call 003Bh"])
        # rt_fio_name: IX and IY are only loaded, just before the rename call,
        # and never read (nothing is kept live across an OS call — F4).
        for label in ("rt_fio_name", "rt_db_rename"):
            lines = [re.sub(r"\s+", " ", ln).strip() for ln in routine_body(label)]
            uses = [i for i, ln in enumerate(lines) if re.search(r"\bi[xy]\b", ln)]
            self.assertEqual([lines[i] for i in uses], ["ld ix,rt_low_name2", "ld iy,rt_low_ext2"])
            call = lines.index("ld a,154")
            self.assertEqual(lines[call + 1], "call 003Bh")
            self.assertLess(call - uses[-1], 4)

    def test_event_loop_no_event_discipline(self) -> None:
        # ROSAN283 os_wait_event/os_get_event: Z = no event, IX corrupt. The
        # Z test comes straight after the call; IX is read only after it and
        # only before the next OS call (os_process_event needs IX as input).
        loop = body("rt_gui_loop")
        # M6 Phase 1: timer (event bit 0) and menu (bit 1) events branch off
        # before the OS-message test; neither makes an OS call first.
        # M13 responsiveness: a TIMER of TICKS is the loop's own, polled from
        # the clock before the OS call (rt_tick_poll makes no OS call)
        self.assertEqual(loop[:4], ["IF PB_TICKPOLL", "call rt_tick_poll", "jp nz,rt_gui_timer", "ENDIF"])
        self.assertEqual([ln for ln in body("rt_tick_poll") if "003Bh" in ln], [])
        loop = loop[4:]
        # M13 RT6: a loop that runs the TIMER itself looks with os_get_event
        # (fn 1, Z when nothing is pending); os_wait_event (fn 2) does not
        # return without an event, and the TIMER never ran with no input
        self.assertEqual(loop[:6], ["ld hl,0FFFFh", "IF PB_TICKPOLL", "ld a,1", "ELSE", "ld a,2", "ENDIF"])
        loop = [loop[0], loop[4]] + loop[6:]
        self.assertEqual(
            loop[:23],
            ["ld hl,0FFFFh", "ld a,2", "call 003Bh", "jp z,rt_gui_loop",
             "IF PB_TIMER", "bit 0,l", "jp nz,rt_gui_timer", "ENDIF",
             "IF PB_MENUS", "bit 1,l", "jp nz,rt_gui_menu", "ENDIF",
             "IF PB_STOPNM", "bit 1,l", "jp nz,rt_gui_stopsel", "ENDIF",  # M15: Stop, no menus
             "IF PB_CANVAS", "ld a,h", "and 4Dh", "jp nz,rt_cv_raw", "ENDIF",  # M9 raw events
             "bit 5,h", "jp z,rt_gui_loop"],
        )
        self.assertEqual(body("rt_gui_stopsel")[:4], ["ld a,(ix+3)", "ld c,a", "ld a,(ix+2)", "or c"])
        self.assertEqual(body("rt_gui_menu")[:4],
                         ["ld a,(ix+2)", "ld (rt_menu_t),a", "ld a,(ix+3)", "ld (rt_menu_e),a"])
        ix_lines = [i for i, ln in enumerate(loop) if "(ix+" in ln]
        self.assertEqual(
            [loop[i] for i in ix_lines], ["ld a,(ix+2)", "ld a,(ix+3)", "ld a,(ix+5)"]
        )
        process = loop.index("ld a,4")
        self.assertEqual(loop[process + 1], "call 003Bh")
        self.assertLess(max(ix_lines), process)
        # object number and event type are saved before os_process_event
        self.assertIn("ld (rt_gui_object),a", loop[:process])
        self.assertIn("ld (rt_gui_evtype),a", loop[:process])
        # om_exit (5) leaves through rt_exit, which removes the dialog first
        self.assertIn("jp z,rt_exit", loop)

    def test_call_003b_only_in_exit_and_alert(self) -> None:
        # A4: the only OS call sites in the whole runtime are the wrappers.
        offenders = [
            label
            for label in CODE_ROUTINES
            if not label.startswith(("rt_fio_", "rt_bank_", "rt_bk_", "rt_code_", "rt_cl_", "rt_cv_",
                                     "rt_draw_", "rt_tx_", "rt_text_", "rt_fname", "rt_db_",
                                     "rt_bmp_", "rt_point", "rt_pg_", "rt_ty_", "rt_type_"))  # M7-M15: below
            and any(re.search(r"\bcall\s+003[Bb]h?\b", ln) for ln in routine_body(label))
        ]
        self.assertEqual(
            sorted(offenders),
            ["rt_alert", "rt_ctl_locate", "rt_ctl_read_check", "rt_ctl_read_text",
             "rt_exit", "rt_file_load", "rt_file_prepare", "rt_file_save",
             "rt_gui_loop", "rt_gui_process", "rt_gui_run",
             "rt_redraw_checks", "rt_sync_out"],
        )
        # M6 Phase 1 call sites, each in its own guarded runtime part.
        phase1 = [
            label
            for label in ("rt_beep", "rt_radio_set", "rt_sync_in_number", "rt_num_write",
                          "rt_win_switch", "rt_gui_post", "rt_menu_init", "rt_menu_ticks",
                          "rt_timer_start", "rt_timer_stop", "rt_ctl_ev_spin")
            if any(re.search(r"\bcall\s+003[Bb]h?\b", ln) for ln in routine_body(label))
        ]
        self.assertEqual(len(phase1), 11)
        total = sum(
            1
            for line in CODE_LINES
            if re.search(r"\bcall\s+003[Bb]h?\b", line)
        )
        # exit: dialog_remove + app_exit; alert; run: define, display, focus;
        # loop: wait, process; process: process; M3b: locate (get_define,
        # add_24bit), read_text (get_byte), read_check (get_byte), sync_out
        # (object_define, field-box object_update, object_update), redraw
        # (object_update); M4: prepare (set_device, set_cwd), save (open,
        # write, close after a failed write, close), load (open, read,
        # close).
        # M6 Phase 1 (15 more): beep; radio set (object_define, update);
        # invalid number (set_focus); number write (object_define, box and
        # edit update); window switch (dialog_remove); post (set_focus);
        # menu init (get_tasks, ddm_define, ddm_display); ticks
        # (put_entry_status); timer start (set_timer), stop (kill_timer).
        # Phase 1 fix: a spinner step flushes the event pipe (1 more).
        # M6 Phase 2 (6 more, IF PB_CTL2): live word (two get_byte), define
        # (object_define), update (object_update), display (object_display,
        # the U6 repair), flush (flush_events).
        phase2 = [
            label
            for label in ("rt_live_word", "rt_define_obj", "rt_update_obj", "rt_display_obj",
                          "rt_flush_after")
            if any(re.search(r"\bcall\s+003[Bb]h?\b", ln) for ln in routine_body(label))
        ]
        self.assertEqual(len(phase2), 5)
        # M7 files (6 more, IF PB_FIO): open, read one byte, close, write,
        # delete, rename.
        m7 = [
            label
            for label in ("rt_fio_open", "rt_fio_fetch", "rt_fio_close", "rt_fio_print",
                          "rt_fio_kill", "rt_fio_name")
            if any(re.search(r"\bcall\s+003[Bb]h?\b", ln) for ln in routine_body(label))
        ]
        self.assertEqual(len(m7), 6)
        # M8 BANKED arrays (5 more, IF PB_BANK): get_mem and two
        # get_mem_ownerid (init), release_mem (free), copy_24bit (copy).
        m8 = {label: sum(1 for ln in routine_body(label) if re.search(r"\bcall\s+003[Bb]h?\b", ln))
              for label in ("rt_bank_init", "rt_bank_free", "rt_bk_copy", "rt_bank_get", "rt_bank_wref",
                            "rt_bank_put", "rt_bank_locate", "rt_bk_udiv")}
        self.assertEqual(m8, {"rt_bank_init": 3, "rt_bank_free": 1, "rt_bk_copy": 1, "rt_bank_get": 0,
                              "rt_bank_wref": 0, "rt_bank_put": 0, "rt_bank_locate": 0, "rt_bk_udiv": 0})
        # M9 code banks (8 more, IF PB_CODEBANKS): the loader's get_mem, two
        # get_mem_ownerid, open and close; one read; the close on a failed
        # read; release_mem when the program ends.
        m9 = {label: sum(1 for ln in routine_body(label) if re.search(r"\bcall\s+003[Bb]h?\b", ln))
              for label in ("rt_code_load", "rt_cl_read", "rt_code_unread", "rt_code_free",
                            "rt_farcall", "rt_code_short")}
        self.assertEqual(m9, {"rt_code_load": 5, "rt_cl_read": 1, "rt_code_unread": 1,
                              "rt_code_free": 1, "rt_farcall": 0, "rt_code_short": 0})
        # M9 CANVAS (7 more): os_get_mouse_xy for a click on the canvas;
        # os_scr_direct; mouse off / on around the BIOS and around
        # os_dialog_string. TEXT (7 more): open, one-byte read, close (load);
        # open, two closes (save); os_write_file per piece.
        m9b = {label: sum(1 for ln in routine_body(label) if re.search(r"\bcall\s+003[Bb]h?\b", ln))
               for label in ("rt_cv_objevent", "rt_cv_dg", "rt_cv_bios", "rt_draw_text",
                             "rt_text_load", "rt_text_save", "rt_tx_write_run", "rt_tx_seek",
                             "rt_text_get", "rt_fname")}
        self.assertEqual(m9b, {"rt_cv_objevent": 1, "rt_cv_dg": 1, "rt_cv_bios": 2, "rt_draw_text": 3,
                               "rt_text_load": 3, "rt_text_save": 3, "rt_tx_write_run": 1,
                               "rt_tx_seek": 0, "rt_text_get": 0, "rt_fname": 0})
        # M10 databases (9 more, IF PB_DB): delete and rename (the backup
        # steps); one read; one write; open and close for reading; open,
        # close, and the close after a failed write for the save.
        # M14 (2 more, IF PB_FSAFE): open for reading in rt_db_own (each companion's
        # kind) and in the save's steps (is the file there?), each closed by rt_db_close_r.
        m10 = {label: sum(1 for ln in routine_body(label) if re.search(r"\bcall\s+003[Bb]h?\b", ln))
               for label in ("rt_db_delete_file", "rt_db_rename", "rt_db_read", "rt_db_write",
                             "rt_db_load_one", "rt_db_close_r", "rt_db_save",
                             "rt_db_load", "rt_db_new", "rt_db_delete", "rt_db_find", "rt_db_peek",
                             "rt_db_own", "rt_db_owns", "rt_db_strs_ok")}
        self.assertEqual(m10, {"rt_db_delete_file": 1, "rt_db_rename": 1, "rt_db_read": 1,
                               "rt_db_write": 1, "rt_db_load_one": 1, "rt_db_close_r": 1,
                               "rt_db_save": 4, "rt_db_load": 0, "rt_db_new": 0,
                               "rt_db_delete": 0, "rt_db_find": 0, "rt_db_peek": 0,
                               "rt_db_own": 1, "rt_db_owns": 0, "rt_db_strs_ok": 0})
        # M11 (4 more, IF PB_CVCELL): DRAW TEXT with a cell: mouse off,
        # os_dialog_string per character, mouse on (done, refused). The
        # runtime bank's rt_rbc makes no OS call (BIOS memory calls only).
        m11 = {label: sum(1 for ln in routine_body(label) if re.search(r"\bcall\s+003[Bb]h?\b", ln))
               for label in ("rt_draw_cells", "rt_rbc", "rt_rbc_back")}
        self.assertEqual(m11, {"rt_draw_cells": 4, "rt_rbc": 0, "rt_rbc_back": 0})
        # M11 corrective (1 more, IF PB_TEXTW): os_dialog_string_width for
        # TEXTWIDTH. SECONDS reads the clock through the BIOS, not the OS.
        m11c = {label: sum(1 for ln in routine_body(label) if re.search(r"\bcall\s+003[Bb]h?\b", ln))
                for label in ("rt_text_width", "rt_seconds")}
        self.assertEqual(m11c, {"rt_text_width": 1, "rt_seconds": 0})
        # M12 BITMAPs (9 more, IF PB_BITMAP / PB_BMPFILE): mouse off / on
        # around GET's strips, PUT and POINT (the BIOS does not hide the
        # pointer); SAVE: open NAME.NEW, close; the read: open (the closes
        # and the database steps are rt_db_*'s own).
        m12 = {label: sum(1 for ln in routine_body(label) if re.search(r"\bcall\s+003[Bb]h?\b", ln))
               for label in ("rt_bmp_blk", "rt_bmp_white", "rt_bmp_get", "rt_bmp_put", "rt_point",
                             "rt_bmp_header", "rt_bmp_save", "rt_bmp_load", "rt_bmp_read")}
        self.assertEqual(m12, {"rt_bmp_blk": 0, "rt_bmp_white": 0, "rt_bmp_get": 2, "rt_bmp_put": 2,
                               "rt_point": 2, "rt_bmp_header": 0, "rt_bmp_save": 2, "rt_bmp_load": 0,
                               "rt_bmp_read": 1})
        # M12 printing (24 more, IF PB_PAGE): the typo list and its bytes
        # (getlist, five os_get_byte_24bit); typo init and meta open; the
        # font (select, clr, def, info, meta font, meta style); text (meta y,
        # charwidth, meta char); PAGEWIDTH (charwidth); every solid
        # rectangle (FILL, LINE, the box's top and bottom) in rt_pg_solid: an
        # hline, or an hline square and a vline; the box's sides (vline);
        # print; close.
        m12p = {label: sum(1 for ln in routine_body(label) if re.search(r"\bcall\s+003[Bb]h?\b", ln))
                for label in ("rt_pg_family", "rt_pg_new", "rt_pg_font", "rt_pg_text", "rt_pg_width",
                              "rt_pg_fill", "rt_pg_solid", "rt_pg_line", "rt_pg_box", "rt_pg_vbar",
                              "rt_pg_print", "rt_pg_close")}
        self.assertEqual(m12p, {"rt_pg_family": 6, "rt_pg_new": 2, "rt_pg_font": 6, "rt_pg_text": 3,
                                "rt_pg_width": 1, "rt_pg_fill": 0, "rt_pg_solid": 3, "rt_pg_line": 0,
                                "rt_pg_box": 0, "rt_pg_vbar": 1, "rt_pg_print": 1, "rt_pg_close": 1})
        # M13 parts and masks (2 more, IF PB_BMPPART): os_mouse_off / on
        # around the strips (rt_bmp_begin / rt_bmp_end); the strips are
        # fetched with rt_bk_copy (os_copy_24bit, counted in M8).
        m13 = {label: sum(1 for ln in routine_body(label) if re.search(r"\bcall\s+003[Bb]h?\b", ln))
               for label in ("rt_bmp_mask", "rt_bmp_part", "rt_bmp_inside", "rt_bmp_fetch", "rt_bmp_begin",
                             "rt_bmp_end", "rt_bmp_blit")}
        self.assertEqual(m13, {"rt_bmp_mask": 0, "rt_bmp_part": 0, "rt_bmp_inside": 0, "rt_bmp_fetch": 0,
                               "rt_bmp_begin": 1, "rt_bmp_end": 1, "rt_bmp_blit": 0})
        # M15 W2 (1 more, IF PB_DWFONT): os_dialog_string_width measuring DRAW TEXT
        m15 = {label: sum(1 for ln in routine_body(label) if re.search(r"\bcall\s+003[Bb]h?\b", ln))
               for label in ("rt_draw_font", "rt_cv_tw", "rt_cv_text_fit", "rt_cv_fits")}
        self.assertEqual(m15, {"rt_draw_font": 0, "rt_cv_tw": 1, "rt_cv_text_fit": 0, "rt_cv_fits": 0})
        # M15 W3 (19 more, IF PB_TYPO): the set-up (init, list, five byte reads), the
        # definition (select, clr, def, info), a character's width, DRAW TYPE (mouse off,
        # charscreen, mouse on on either way out) and, with PAGE, the PAGE font again
        m15t = {label: sum(1 for ln in routine_body(label) if re.search(r"\bcall\s+003[Bb]h?\b", ln))
                for label in ("rt_type_font", "rt_ty_ready", "rt_ty_want", "rt_ty_adv", "rt_draw_type",
                              "rt_ty_pgslot", "rt_type_width", "rt_type_height")}
        self.assertEqual(m15t, {"rt_type_font": 0, "rt_ty_ready": 7, "rt_ty_want": 4, "rt_ty_adv": 1,
                                "rt_draw_type": 4, "rt_ty_pgslot": 3, "rt_type_width": 0, "rt_type_height": 0})
        self.assertEqual(total, 152)  # M14: +2 (rt_db_own, the save's file check); M15: +1, +19

    def test_rt_put_body(self) -> None:
        # M2.1: the single guarded string writer. Writes only if
        # DE < rt_dst_end (the last byte is reserved for the NUL); otherwise
        # jumps to the runtime-error report, writing nothing.
        self.assertEqual(
            body("rt_put"),
            [
                "push hl",
                "ld hl,(rt_dst_end)",
                "or a",
                "sbc hl,de",
                "jp z,rt_err_string_overflow",
                "jp c,rt_err_string_overflow",
                "pop hl",
                "ld (de),a",
                "inc de",
                "ret",
            ],
        )

    def test_string_text_is_written_only_through_rt_put(self) -> None:
        # No routine other than rt_put stores string text with ld (de),a.
        # Allowed besides: a NUL terminator ('xor a' then 'ld (de),a' — DE is
        # within the destination by rt_put's invariant), rt_alert_dynamic's
        # fixed 14-byte definition tail, and the checkbox status byte that
        # rt_sync_out_record stores into the 105-byte rt_obj_buf after a
        # 9-byte template. M4: rt_low_copy copies compiler-emitted path /
        # name / extension (lengths bounded at compile time by pbas/files.py)
        # into the fixed bottom-quarter workspace — not string text into a
        # string object.
        for label, lines in sections().items():
            # M9: rt_code_load copies the loader's name block (at most 32 +
            # 8 bytes, counted with djnz) into its bottom-quarter workspace.
            # M9: rt_text_get collects at most 128 bytes into the 128-byte
            # rt_tx_tmp (then rt_put copies them); rt_fname fills a 14-byte
            # descriptor (stem <= 8, extension <= 3, both counted);
            # rt_draw_text copies at most 127 characters into rt_ds_buf+8
            # (136 bytes).
            if label in ("rt_put", "rt_alert_dynamic", "rt_sync_out_record", "rt_low_copy",
                         "rt_code_load", "rt_cl_copy", "rt_cl_ext_copy",
                         "rt_text_get_keep", "rt_fname_stem", "rt_fname_dot", "rt_fname_ext",
                         "rt_fname_end", "rt_cv_text_put", "rt_cv_text_end",
                         "rt_tw_put",  # M11c: at most 127 into rt_tw_buf+8 (136 bytes)
                         "rt_bmp_fetch_put"):  # M13: a strip's part rows, at most 192 bytes
                # (rows a strip = 192 \ bytes a row) into RT_BMP_D / RT_BMP_M
                continue
            norm = [re.sub(r"\s+", " ", ln).strip() for ln in lines]
            for i, ln in enumerate(norm):
                if re.search(r"ld \(de\),a", ln):
                    with self.subTest(routine=label, line=i):
                        self.assertGreater(i, 0)
                        self.assertEqual(norm[i - 1], "xor a", "only a NUL may be stored outside rt_put")

    def test_rt_alert_dynamic_body(self) -> None:
        self.assertEqual(
            body("rt_alert_dynamic"),
            [
                "xor a", "ld (de),a", "inc de",
                "ld (de),a", "inc de",
                "ld a,1", "ld (de),a", "inc de",
                "ld hl,rt_alert_keys", "ld bc,11", "ldir",
                "ld hl,rt_alert_buf", "ex de,hl", "or a", "sbc hl,de", "ex de,hl",
                "jp rt_alert",
            ],
        )

    def test_rt_exit_body(self) -> None:
        # M3a: an open dialog is removed (os_dialog_remove, fn 68) before
        # os_app_exit (fn 23); the flag is cleared first so it cannot loop.
        # M6: a running timer is stopped first (IF PB_TIMER).
        # M12: an open print page is discarded (IF PB_PAGE, os_meta_close).
        self.assertEqual(
            routine_body("rt_exit"),
            ["IF PB_TIMER", "call rt_timer_stop", "ENDIF",
             "IF PB_PAGE", "call rt_pg_close", "ENDIF",
             "IF PB_BANK", "call rt_bank_free", "ENDIF",  # M8: blocks back first
             "IF PB_CODEBANKS", "call rt_code_free", "ENDIF",  # M9: then the code blocks
             "ld a,(rt_dialog_open)", "or a", "jp z,rt_exit_app", "xor a",
             "ld (rt_dialog_open),a", "ld a,68", "call 003Bh",
             "ld a,23", "call 003Bh", "ret"],
        )

    def test_rt_alert_body(self) -> None:
        self.assertEqual(
            body("rt_alert"),
            ["call 0CBh", "ld c,a", "ld a,76", "call 003Bh",
             # M9: an alert may cover the canvas: ask for a repaint (not
             # while PAINT itself runs); A and the flags are kept
             "IF PB_CANVAS", "push af", "ld a,(rt_cv_painting)", "xor 1", "ld hl,rt_cv_dirty",
             "or (hl)", "ld (hl),a", "pop af", "ENDIF", "ret"],
        )

    def test_rt_alert_uses_bios_getmem1(self) -> None:
        self.assertIn("call 0CBh", body("rt_alert"))
        # bios_getmem1 header quote must document the preservation of HL/DE.
        self.assertIn("bios_getmem1", TEXT)
        self.assertIn("all flags & other regs preserved", TEXT)

    def test_wrapper_headers_cite_os_contracts(self) -> None:
        citations = {
            "rt_exit / os_app_exit fn 23": "os_app_exit",
            "fn 23": "fn 23",
            "no exit quote": "out: no exit!",
            "auto-close note": "automatically closes any opened",
            "rt_alert / os_alert fn 76": "os_alert",
            "fn 76": "fn 76",
            "alert clobber quote": "BC, DE, HL, IX, IY corrupt",
            "alert definition format": "Total Data Length of definition",
        }
        for what, needle in citations.items():
            with self.subTest(citation=what):
                self.assertIn(needle, TEXT)

    def test_port_citations_present(self) -> None:
        for needle in (
            "POC/pbas/codegen.py:150-159",  # rt_mul16 port source
            "POC/pbas/codegen.py:160-170",  # rt_compare_signed port source
            "POC/NOTES.asm:386-516",  # rt_append_int port source
            "POC/NOTES.asm:543-544",  # rt_alert_keys source
            "POC/NOTES.asm:545",  # 160-byte dyn_message buffer source
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, TEXT)

    def test_mul16_two_complement_note(self) -> None:
        self.assertIn("two's-complement", TEXT)
        self.assertIn("mod 65536", TEXT)

    def test_data_buffer_sizes(self) -> None:
        patterns = {
            "rt_alert_buf": r"^rt_alert_buf:\s*\n\s*defs\s+174\s*$",
            "rt_cmp_buf1": r"^rt_cmp_buf1:\s*\n\s*defs\s+128\s*$",
            "rt_cmp_buf2": r"^rt_cmp_buf2:\s*\n\s*defs\s+128\s*$",
            "rt_int_scratch": r"^rt_int_scratch:\s*\n\s*defs\s+2\s*$",
            "rt_dst_end": r"^rt_dst_end:\s*\n\s*defs\s+2\s*$",
            "rt_err_line": r"^rt_err_line:\s*\n\s*defs\s+2\s*$",
        }
        for label, pattern in patterns.items():
            with self.subTest(label=label):
                self.assertIsNotNone(re.search(pattern, TEXT, re.M))
        self.assertIsNotNone(
            re.search(
                r"^rt_alert_keys:\s*\n\s*dw\s+800Dh,80FBh,0,0\s*\n\s*db\s+79,75,0\s*$",
                TEXT,
                re.M,
            )
        )

    def test_memory_map_citations(self) -> None:
        for needle in (
            "Memory Layout",
            "org 4000h",
            "#4000-#7FFF",
            "#2000-#2FFF",
            "#3FFE",
            "#4100",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, TEXT)

    def test_extension_point_citations(self) -> None:
        # M3/M4 extension block: cite, do not implement.
        for needle in (
            "os_get_event 1, os_wait_event 2",
            "fns 41-47",
            "os_set_cwd (fn 135)",
            "os_object_get_define (fn 70)",
            "os_object_update (fn 72)",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, TEXT)

    def test_jump_and_call_targets_defined(self) -> None:
        # A1-lite: every call/jp/djnz target that is a plain label is defined.
        defined = set(sections())
        conditions = {"nz", "z", "nc", "c", "po", "pe", "p", "m"}
        for line in CODE_LINES:
            m = re.match(r"^(?:call|djnz)\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", line.strip())
            if m:
                self.assertIn(m.group(1), defined)
                continue
            m = re.match(r"^jp\s+(.+)$", line.strip())
            if m:
                rest = m.group(1)
                parts = [p.strip() for p in rest.split(",")]
                target = parts[-1]
                if len(parts) > 1:
                    self.assertIn(parts[0], conditions)
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", target):
                    self.assertIn(target, defined)

    def test_code_routines_terminate(self) -> None:
        # Every code routine reaches at least one ret or jp (no accidental
        # fall-through into the next routine or the data pool).
        for label in CODE_ROUTINES:
            with self.subTest(routine=label):
                self.assertTrue(
                    any(ln == "ret" or ln.startswith("jp") for ln in routine_body(label)),
                    f"{label} has no ret/jp",
                )

    def test_style_matches_poc(self) -> None:
        # POC/NOTES.asm conventions: 4-space instruction indent, no tabs.
        self.assertNotIn("\t", TEXT)
        self.assertTrue(TEXT.endswith("\n"))


@requires_pasmo
class TestPasmoAssembly(unittest.TestCase):
    """Tier 4: the runtime assembles standalone under Pasmo."""

    def test_runtime_assembles_standalone(self) -> None:
        # Both variants of the conditional dialog section (M3a): PB_DIALOG 0
        # for programs without a WINDOW, 1 with one.
        # M4: and the file section (PB_FILES, which also needs the
        # program-emitted PB_FILE_DEVICE and pb_file_path).
        sizes = {}
        # M5a: PB_STR_TEMPS (extra scratch strings) and PB_SLICE.
        for dialog, bindings, files in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 0, 1), (1, 1, 1)):
            with self.subTest(PB_DIALOG=dialog, PB_BINDINGS=bindings, PB_FILES=files), \
                    tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / "runtime_standalone.asm"
                out = Path(tmp) / "runtime_standalone.bin"
                head = (f"PB_DIALOG equ {dialog}\nPB_BINDINGS equ {bindings}\nPB_FILES equ {files}\n"
                        f"PB_STR_TEMPS equ {4 * files}\nPB_SLICE equ {files}\n"
                        f"PB_LABELS equ {bindings}\nPB_KEYS equ {dialog}\n"
                        + "".join(f"PB_{n} equ {files}\n" for n in ("DIV", "VAL", "ASC", "CHR", "INSTR", "CASE", "ARRAYS", "IMATH", "STRFN", "FIO", "REAL", "BANK"))
                        # M6 Phase 1 parts: all on with the binding section
                        + "".join(f"PB_{n} equ {bindings}\n" for n in (
                            "RADIO", "NUMBERS", "SPIN", "MENUS", "TIMER", "WINDOWS", "FOCUS",
                            "ASK", "BEEP", "POST"))
                        # M6 Phase 2 parts, likewise
                        + "".join(f"PB_{n} equ {bindings}\n" for n in (
                            "LIST", "CHOICE", "SLIDER", "SCROLL", "CTL2", "CHANGE")))
                if files:
                    head += "PB_FILE_DEVICE equ 1\n"
                head += f"PB_CODEBANKS equ {files}\nPB_CODE_N equ 1\n"  # M9
                # M9: the canvas with the dialog parts, TEXT with the file
                # parts, never both (all of it would not fit 16K together)
                canvas, text = int(bindings and not files), int(files and not bindings)
                head += f"PB_TEXTW equ {files}\nPB_CLOCK equ {files}\n"  # M11 corrective
                head += f"PB_CANVAS equ {canvas}\nPB_CVLINE equ {canvas}\nPB_CVCELL equ {canvas}\nPB_TEXT equ {text}\nPB_FNAME equ {text}\nPB_RECORDS equ {text}\nPB_DB equ {text}\nPB_TXRANGE equ {text}\n"
                # M12: BITMAP is off here: the file parts alone are already 16382 bytes;
                # tests/test_m12_bitmap.py assembles it in programs, banked and not
                head += f"PB_BITMAP equ 0\nPB_BMPFILE equ 0\nPB_POINT equ 0\nPB_PAGE equ 0\nPB_BMPPART equ 0\nPB_KEYDOWN equ 0\nPB_CLOCKTICKS equ 0\nPB_TICKPOLL equ 0\nPB_CKCAL equ 0\n"
                # M14: the file-safety and rounding variants are off here too (the image is full);
                # tests/test_m14_filesafety.py and test_m14_real.py assemble them in programs
                head += "PB_FSAFE equ 0\nPB_RSTICKY equ 0\n"
                # M15: Stop without menus, DRAW FONT, ALIGN: assembled in programs
                # (tests/test_m15_stop.py, test_m15_fonts.py)
                head += "PB_STOPNM equ 0\nPB_DWFONT equ 0\nPB_DWALIGN equ 0\nPB_TYPO equ 0\nPB_TYPG equ 0\nPB_CVMULTI equ 0\n"
                tail = "\npb_file_path: db 92,0\n" if files else ""
                if files:  # M9: the code-bank table the linker emits
                    tail += "rt_code_tab: dw 512,0\n"
                if files:  # M8: program-emitted BANKED array data
                    tail += ("cgbank_need equ 1\ncgbank_wsize equ 2\ncgbank_win: defs 256\n"
                             "cgbank_wwin: defs 2\n")
                if canvas:  # M9: a canvas descriptor and its window's text fields
                    tail += "\ncgcanvas: dw 10,10,100,50,0,0,0\n    db 2,0\ncgcv_edits: db 0\n"
                if bindings:  # program-emitted M6 tables
                    tail += ("\ngui_menu_def: db 0\ngui_menu_def_end:\ngui_menu_items: db 0\n"
                             "gui_menu_ticks: db 0\ngui_timer_rec: dw 1,1,16,0,0,0\n"
                             "gui_timer_handler: dw 0\n")
                src.write_text(head + "    org 4000h\n" + TEXT + tail, encoding="utf-8")
                proc = subprocess.run(
                    ["pasmo", "--bin", str(src), str(out)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"pasmo failed:\n{proc.stdout}\n{proc.stderr}",
                )
                sizes[(dialog, bindings, files)] = size = os.path.getsize(out)
                self.assertGreaterEqual(size, 400, f"runtime image too small: {size}")
                self.assertLessEqual(size, 16384, f"runtime image exceeds the 16K bank: {size}")
        self.assertGreater(sizes[(1, 0, 0)], sizes[(0, 0, 0)], "dialog section must be conditional")
        self.assertGreater(sizes[(1, 1, 0)], sizes[(1, 0, 0)], "binding section must be conditional")
        self.assertGreater(sizes[(0, 0, 1)], sizes[(0, 0, 0)] + 512 + 4 * 128,
                           "file, scratch-pool, slice and M5b sections must be conditional")


class TestAsmcheck(unittest.TestCase):
    """A-rule lint via tools/asmcheck.py once that tool has landed."""

    def test_asmcheck_runtime(self) -> None:
        self.assertTrue(ASMCHECK.exists(), "tools/asmcheck.py is missing")
        spec = importlib.util.spec_from_file_location("asmcheck", ASMCHECK)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("asmcheck", module)  # dataclasses resolve via sys.modules
        spec.loader.exec_module(module)
        result = None
        called = False
        for name in ("check_file", "check", "run", "lint"):
            fn = getattr(module, name, None)
            if callable(fn):
                result = fn(str(RUNTIME))
                called = True
                break
        if not called and callable(getattr(module, "main", None)):
            try:
                module.main([str(RUNTIME)])
            except SystemExit as exc:
                result = exc.code
            called = True
        self.assertTrue(called, "tools/asmcheck.py has no recognisable entry point")
        if isinstance(result, bool):
            self.assertTrue(result)
        elif isinstance(result, int):
            self.assertEqual(result, 0)
        elif result is None:
            pass
        else:
            self.assertEqual(len(result), 0)


if __name__ == "__main__":
    unittest.main()
