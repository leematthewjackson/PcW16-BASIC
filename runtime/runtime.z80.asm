; ============================================================================
; PcW16 BASIC — hand-written Z80 runtime, milestone M2 core subset
; ============================================================================
;
; This file is the ONLY place generated code may reach the Rosanne OS
; (ARCHITECTURE.md D2). Generated code calls rt_* routines and references
; rt_* data labels; it must never contain `call 003Bh`, an `org` directive,
; literal OS function numbers, or IX/IY usage (asmcheck rules A4/A5,
; TESTING-STRATEGY.md tier 3).
;
; tools/build.py assembles the final image by concatenating the generated
; program text with this file and invoking `pasmo --bin`
; (ARCHITECTURE.md D2/D7). This file therefore contains NO `org` — the
; generated program header owns the origin, the 256-byte zero prefix and
; the `start:` entry label.
;
; Instruction subset: only documented Z80 instructions are used (ld all
; forms, ldir (alert trailer and binding-record copies), inc/dec, add/adc/sbc hl,rr,
; or/and/xor/cp/sub/add a,n, bit, sla/srl/rr/rl, cpl, push/pop, jp and
; jp cc, call/ret, ex de,hl, djnz; M7 adds neg, ld a,r, ldd/lddr and the
; accumulator rotates rla/rra/rlca/rrca), so a behavioural simulator can
; cover the whole file. IX and IY are used as registers only where a
; Rosanne call takes them as inputs: the event loop, and rt_fio_name
; (os_rename_file's new name in IX/IY, M7; asmcheck A5 allows exactly
; these). (The decimal conversion
; workspace is accessed as rt_int_scratch / rt_int_scratch+1, i.e.
; `ld (nn),a` / `ld a,(nn)` absolute-byte forms under "ld all forms".)
;
; ----------------------------------------------------------------------------
; Memory map (all facts cited ROSAN283.DOC, section 'Memory Layout'):
;   * The generated program sets `org 4000h`; the application image lives
;     in the second quarter, #4000-#7FFF (ROSAN283 bios table: bios_setmem1
;     / bios_getmem1 manage "memory block for #4000...#7FFF", table #15/#19).
;   * Execution starts at #4100 (ROSAN283 'Memory Layout': "When an app is
;     run execution starts at #4100 with CHL = 24-bit address ..."; also
;     "initial execution address = #4100 (for historical reasons - you can
;     put what you want in the first 256 bytes of your first ROM)").
;   * App-private workspace is #2000-#2FFF of quarter-0 block #80
;     (ROSAN283 'Memory Layout': "RAM block #80 is in 1st quarter
;     (#0000...#3FFF) and should stay there! AP may use #2000...#2FFF of
;     this as its own").
;   * The stack descends from #3FFE with about 2K of space
;     (ROSAN283 'Memory Layout': "Stack descends from #3FFE (i.e. top of
;     block #80) and has about 2k space").
; ----------------------------------------------------------------------------
; Calling convention (ARCHITECTURE.md D6):
;   * Inputs/outputs travel in AF/BC/DE/HL exactly as each routine header
;     documents; every header states in:/out:/clobbers.
;   * Across ANY `call 003Bh`, only the registers that call's documented
;     contract preserves may be assumed live — Rosanne documents corruption
;     per call, and "all registers not specified are assumed corrupted"
;     (ARCHITECTURE.md section 4).
;   * IX/IY carry no runtime state (only Rosanne call inputs, above);
;     long-lived pointers live in generated variable storage or on the stack.
;   * STRING data is fixed-capacity, NUL-terminated; capacity is a
;     compile-time property, minimum 2 bytes (LANGUAGE-SPEC.md section 4,
;     ARCHITECTURE.md D5).
;   * Every byte of string text is written through rt_put, which checks the
;     active destination limit rt_dst_end (M2.1). Generated code sets
;     rt_dst_end and DE before building any string, and writes only the
;     final NUL itself, at DE, which rt_put guarantees is <= rt_dst_end.
;     Text that would not fit is never truncated and never written past the
;     destination: rt_put jumps to rt_err_string_overflow, which reports
;     "Runtime error: string too long at line N" and exits the app.
; ----------------------------------------------------------------------------
; OS function numbers: Supporting Docs/OSCALLS.INC.txt is a list of `rb 1`
; entries included by CONSTOS.Z80 after `RSSET 1`, so the Nth entry is
; function N: os_get_event 1, os_wait_event 2, os_put_event 3,
; os_process_event 4 (M3a correction: earlier notes called fn 2
; os_get_event; it is os_wait_event).
;
; Dialogs and events (M3a, implemented below): os_dialog_define 66,
; os_dialog_display 67, os_dialog_remove 68, os_set_focus 73,
; os_wait_event 2, os_process_event 4.
;
; M3b/M4 platform areas (implemented in the sections named below):
;   * Banked 24-bit access (M3b dialog/variable sync): fns 41-47 —
;     os_copy_24bit, os_get_byte_24bit, os_get_word_24bit,
;     os_get_wd24_24bit, os_put_byte_24bit, os_put_word_24bit,
;     os_put_wd24_24bit. Fns 42/45 document B as a wind-on flag (0=peek,
;     1=advance) — the only two values the docs define.
;   * Object sync (M3): os_object_get_define (fn 70),
;     os_object_update (fn 72); both are documented as corrupting IY
;     (ROSAN283), which is exactly why the A5 no-IX/IY discipline exists.
;   * File I/O (M4): implemented below in "Files" — os_set_device
;     (fn 127), os_set_cwd (fn 135), os_open_file (fn 144), os_close_file
;     (fn 145), os_write_file (fn 146), os_read_file (fn 147).
; ============================================================================


; ----------------------------------------------------------------------------
; rt_exit — terminate the application (END / EXIT statement path).
;
; ROSAN283 'os_app_exit' (fn 23; OSCALLS.INC.txt line 23):
;   "# os_app_exit    exit current app (return to desktop)
;    in:  none
;    out: no exit!"
; ROSAN283 file-system note: "os_app_exit automatically closes any opened
; read and/or write files" — so the exit path needs no file-close calls of
; its own.
;
; M3a: if the program's dialog is on screen (rt_dialog_open), it is removed
; first with os_dialog_remove (fn 68; ROSAN283: "in: none; out: C none to
; remove / NC OK, screen contents restored if required; AF, BC, DE, HL, IX,
; IY corrupt") — the POC-proven close sequence (POC ui_codegen close_dlg).
; The flag is cleared before the call so a failure cannot loop.
;
; in:  none
; out: never returns ("no exit!")
; clobbers: everything (neither call documents preserved registers)
; ----------------------------------------------------------------------------
rt_exit:
    IF PB_TIMER
    call rt_timer_stop
    ENDIF
    IF PB_PAGE
    call rt_pg_close            ; M12: a page still open is discarded
    ENDIF
    IF PB_BANK
    call rt_bank_free           ; M8: BANKED array blocks back to the OS
    ENDIF
    IF PB_CODEBANKS
    call rt_code_free           ; M9: code blocks back to the OS
    ENDIF
    ld a,(rt_dialog_open)
    or a
    jp z,rt_exit_app
    xor a
    ld (rt_dialog_open),a
    ld a,68
    call 003Bh
rt_exit_app:
    ld a,23
    call 003Bh
    ret

; ----------------------------------------------------------------------------
; rt_alert — display a modal alert dialog (MESSAGE statement).
;
; ROSAN283 'os_alert' (fn 76; OSCALLS.INC.txt line 76):
;   "in:  C,HL = 24-bit address of alert definition
;         DE    = Total Data Length of definition
;                 Byte 0... ASCII. Each line 0-terminated, plus extra 0 to
;                 indicate end of text.
;                 Byte    Number of buttons
;                 Button  4 Words for keys ( 4 pairs of Ascii, Shift
;                         [#80=ignore] ); 0-terminated ASCII text
;                         ( N.B. no repeat-flag byte! )
;   out: C  ....... error in definition
;        NC ....... A = Exit code (Number of Selected Button 0...n-1)
;         BC, DE, HL, IX, IY corrupt"
; C = the app image bank, obtained here from bios_getmem1
; (call #0CBh; ROSAN283 bios table #19: "in: none; out: A = block number
; (#00..#7F=ROM, #80..#FF=RAM); all flags & other regs preserved" — so HL/DE
; set by the caller survive this call).
;
; in:  HL = alert definition pointer within the app image
;      DE = total definition length in bytes
; out: C flag = definition rejected (alerts are informational; callers
;      ignore); NC + A = selected button index otherwise
; clobbers: AF, BC, DE, HL (doc: "BC, DE, HL, IX, IY corrupt")
; ----------------------------------------------------------------------------
rt_alert:
    call 0CBh
    ld c,a
    ld a,76
    call 003Bh
    IF PB_CANVAS
    push af                     ; M9: the canvas may need repainting,
    ld a,(rt_cv_painting)       ; unless this alert is PAINT's own
    xor 1
    ld hl,rt_cv_dirty           ; (HL is corrupt after os_alert anyway)
    or (hl)
    ld (hl),a
    pop af
    ENDIF
    ret

; ----------------------------------------------------------------------------
; rt_alert_dynamic — finish and show an alert whose text was built in
; rt_alert_buf (dynamic MESSAGE, runtime error reports).
;
; Appends the os_alert definition tail (ROSAN283 'os_alert', format quoted at
; rt_alert above): the text's NUL, the extra end-of-text NUL, button count 1
; and the 11-byte rt_alert_keys trailer, then calls rt_alert with the total
; length. The text was written through rt_put with rt_dst_end =
; rt_alert_buf+160, so DE <= rt_alert_buf+160 and the 14 tail bytes end at
; or before rt_alert_buf+173, inside the 174-byte buffer.
;
; in:  DE = one past the last text byte in rt_alert_buf
; out: as rt_alert
; clobbers: AF, BC, DE, HL
; ----------------------------------------------------------------------------
rt_alert_dynamic:
    xor a
    ld (de),a
    inc de
    ld (de),a
    inc de
    ld a,1
    ld (de),a
    inc de
    ld hl,rt_alert_keys
    ld bc,11
    ldir
    ld hl,rt_alert_buf
    ex de,hl
    or a
    sbc hl,de
    ex de,hl
    jp rt_alert

; ----------------------------------------------------------------------------
; rt_err_string_overflow — runtime error: a string did not fit its
; destination (LANGUAGE-SPEC.md section 4, M2.1 policy: runtime overflow is
; a defined, reported error; never truncation or corruption).
;
; Reached by `jp` from rt_put, with nothing written past the destination.
; Shows "Runtime error: string too long at line N" (N = rt_err_line, the
; .pbas source line set by generated code before each string-writing
; statement), then exits through rt_exit (os_app_exit, which also closes any
; open files). Never returns; the few stack words left by the interrupted
; routine are abandoned with the app.
;
; The report text is 39 bytes plus at most 6 digits, well inside the
; 160-byte alert text area, so its own rt_put calls cannot fail.
; ----------------------------------------------------------------------------
rt_err_string_overflow:
    ld hl,rt_alert_buf+160
    ld (rt_dst_end),hl
    ld de,rt_alert_buf
    ld hl,rt_err_text
    ld bc,rt_err_text_end-rt_err_text
    call rt_str_copy
    ld hl,(rt_err_line)
    call rt_append_int
    call rt_alert_dynamic
    jp rt_exit

rt_err_text:
    db "Runtime error: string too long at line "
rt_err_text_end:

    IF PB_ASK
; ----------------------------------------------------------------------------
; rt_ask — show a question built in rt_alert_buf with 2 or 3 buttons (ASK,
; M6 Phase 1). The text (at most 100 bytes, written through rt_put) is
; followed by its end-of-text NUL, the extra NUL and the generated button
; block (count, then per button 4 keycode words and a NUL-terminated
; caption) — the os_alert definition of ROSAN283, quoted at rt_alert. The
; block is at most 58 bytes, so everything ends inside the 174-byte buffer.
; in:  DE = one past the last text byte; HL = button block; BC = its length
; out: HL = the chosen button, 1..n (os_alert "A = Exit code (Number of
;      Selected Button 0...n-1)"); a refused alert is "the question could
;      not be shown" at rt_err_line
; clobbers: AF, BC, DE, HL
; ----------------------------------------------------------------------------
rt_ask:
    xor a
    ld (de),a
    inc de
    xor a
    ld (de),a
    inc de
    ldir
    ld hl,rt_alert_buf
    ex de,hl
    or a
    sbc hl,de
    ex de,hl
    ld hl,rt_alert_buf
    call rt_alert
    jp c,rt_ask_failed
    inc a
    ld l,a
    ld h,0
    ret
rt_ask_failed:
    ld hl,rt_err_ask_text
    ld bc,rt_err_ask_text_end-rt_err_ask_text
    jp rt_err_msg
rt_err_ask_text:
    db "Runtime error: the question could not be shown at line "
rt_err_ask_text_end:
    ENDIF

    IF PB_BEEP
; rt_beep — BEEP (M6 Phase 1): os_beep (fn 50, ROSAN283 "in: none; out:
; none; AF corrupt").
rt_beep:
    ld a,50
    call 003Bh
    ret
    ENDIF


; ============================================================================
; Dialogs and events (M3a)
; ============================================================================
; Assembled only for programs with a WINDOW: the generated program header
; defines PB_DIALOG (1 with a dialog, 0 without), so programs without a
; dialog do not carry this code (it would otherwise cost every program
; about 240 bytes of the 16K image limit). rt_exit and rt_dialog_open are
; unconditional.
    IF PB_DIALOG

; ----------------------------------------------------------------------------
; rt_gui_run — open the program's dialog and serve its events. Never returns.
;
; Reached by `jp` from generated code after the main line has finished
; (ARCHITECTURE.md D1: main-line statements run once, then the dialog).
;
; in:  HL = dialog definition (built by pbas/layout.py in the app image)
;      DE = handler table:  +0 Byte  focus object number (0 = none)
;                           +1 Byte  row count N
;                           +2 ...   N rows of: Byte object number,
;                                    Word handler address (a SUB routine
;                                    ending in `ret`)
;
; ROSAN283 'os_dialog_define' (fn 66): "in: C,HL = 24-bit address of dialog
; definition (max length 16k) ... out: C error in definition / NC OK; AF, BC,
; DE, HL, IX, IY corrupt". C is the app bank from bios_getmem1, the same
; 24-bit addressing rt_alert uses; the image (and so the definition) lies in
; #4000-#7FFF (16K limit, pbas/prg.py).
; 'os_dialog_display' (fn 67): "out: C none to display / NC OK; all corrupt"
; — "only do ONCE for each os_dialog_define".
; 'os_set_focus' (fn 73): "in: E = object number; out: C error ...; all
; corrupt". A focus failure is harmless and ignored.
; If define or display fails, the program reports it with an alert and
; exits (defined behaviour; the POC exited silently).
; ----------------------------------------------------------------------------
rt_gui_run:
    ex de,hl
    ld (rt_gui_table),hl
    ex de,hl
    call 0CBh
    ld c,a
    ld a,66
    call 003Bh
    jp c,rt_gui_failed
    IF PB_BINDINGS
    xor a
    ld (rt_bind_mode),a
    call rt_sync_out
    ENDIF
    ld a,67
    call 003Bh
    jp c,rt_gui_failed
    ld a,1
    ld (rt_dialog_open),a
    ld hl,(rt_gui_table)
    ld a,(hl)
    or a
    IF PB_POST
    jp z,rt_gui_opened
    ELSE
    IF PB_CANVAS
    jp z,rt_cv_open
    ELSE
    jp z,rt_gui_loop
    ENDIF
    ENDIF
    ld e,a
    ld a,73
    call 003Bh
    IF PB_POST
rt_gui_opened:
    call rt_gui_post
    ENDIF
    IF PB_CANVAS
    jp rt_cv_open               ; M9: the canvas is on screen; PAINT
    ELSE
    jp rt_gui_loop
    ENDIF

rt_gui_failed:
    ld hl,rt_gui_fail_alert
    ld de,rt_gui_fail_alert_end-rt_gui_fail_alert
    call rt_alert
    jp rt_exit

rt_gui_fail_alert:
    db "Runtime error: the window could not be opened",0,0,1
    dw 800Dh,80FBh,0,0
    db 79,75,0
rt_gui_fail_alert_end:

; ----------------------------------------------------------------------------
; rt_gui_loop — the event loop.
;
; ROSAN283 'os_wait_event' (fn 2): "in: HL = mask of events to wait for
; (must be #FFFF); out: as os_get_event (but can't be Z for no event!!)".
; 'os_get_event' out: "Z if no matching event pending... IX & AF corrupt";
; "NZ ... HL = Event Code (any one bit set only), IX = 16-bit address of
; 12-byte Event record; AF, BC, DE corrupt". Z is tested anyway, before IX
; or HL is used, so a no-event return can never dispatch from a stale record
; (the class of bug ARCHITECTURE F3 describes).
;
; Event code bit 13 = OS message. OS message record: IX+2 message id,
; IX+3 object number, IX+5 object event type (om_objevent). Message ids and
; event types from CONSTOS.Z80 (RSSET #01): om_topbar 1, om_objevent 4,
; om_exit 5; obev_click 1.
;
; Actions, per the ROSAN283 message table:
;   om_exit      -> "close all ram and os_app_exit": rt_exit (dialog removed
;                   first). The app owns no extra RAM.
;   om_objevent  -> "pass to os_process_event", then, for obev_click, look
;                   the object up in the handler table and call its SUB.
;   other OS messages (om_topbar, ...) -> pass to os_process_event.
;   non-message events (keys, raw mouse) -> no action (none documented;
;                   POC-proven).
; M5d (IF PB_KEYS, programs with a DEFAULT button): obev_key (3, CONSTOS.Z80
; RSSET #01; ROSAN283 "object key pressed (txt/bmpbutton only)") dispatches
; exactly like obev_click. The DEFAULT button's definition carries the Return
; key (#0D, shift #80 = ignore), so Rosanne reports Return as obev_key on it.
; 'os_process_event' (fn 4): "N.B.! in: IX = 16-bit address of 12-byte event
; record (passed on from os_get_event !)" — IX is left untouched from the
; wait until this call. Its outputs (CHL, BDE) are not needed and no
; register is documented as preserved, so the object number and event type
; are saved to memory first (the F4 register-discipline rule).
; Handlers run with nothing live in registers and return here with `ret`.
; ----------------------------------------------------------------------------
rt_gui_loop:
    IF PB_TICKPOLL
    call rt_tick_poll           ; M13: a TIMER of TICKS that is due runs first
    jp nz,rt_gui_timer
    ENDIF
    ld hl,0FFFFh
    IF PB_TICKPOLL
    ld a,1                      ; os_get_event: Z when nothing is pending (rt_tick_poll)
    ELSE
    ld a,2
    ENDIF
    call 003Bh
    jp z,rt_gui_loop
    IF PB_TIMER
    bit 0,l
    jp nz,rt_gui_timer
    ENDIF
    IF PB_MENUS
    bit 1,l
    jp nz,rt_gui_menu
    ENDIF
    IF PB_STOPNM
    bit 1,l                     ; M15: no menus of its own, but ON STOP: the
    jp nz,rt_gui_stopsel        ; Tasks menu's selections
    ENDIF
    IF PB_CANVAS
    ld a,h
    and 4Dh                     ; M9: keyboard, left click / release, movement
    jp nz,rt_cv_raw
    ENDIF
    bit 5,h
    jp z,rt_gui_loop
    ld a,(ix+2)
    cp 5
    jp z,rt_exit
    cp 4
    jp nz,rt_gui_process
    ld a,(ix+3)
    ld (rt_gui_object),a
    ld a,(ix+5)
    ld (rt_gui_evtype),a
    ld a,4
    call 003Bh
    IF PB_SPIN + PB_SCROLL
    ld a,b
    ld (rt_gui_b),a
    ENDIF
    IF PB_SCROLL
    ld (rt_gui_de),de
    ENDIF
    IF PB_BINDINGS
    call rt_redraw_checks
    ENDIF
    IF PB_RADIO + PB_SPIN + PB_CTL2
    call rt_ctl_event
    ENDIF
    IF PB_CHANGE
    ld hl,(rt_ctl_pending)
    ld a,h
    or l
    jp z,rt_gui_nopend
    IF PB_NUMBERS
    xor a
    ld (rt_sync_strict),a
    ENDIF
    jp rt_gui_dispatch
rt_gui_nopend:
    ENDIF
    IF PB_CANVAS
    call rt_cv_objevent         ; M9: a click on the canvas, a key for it
    ld a,h
    or l
    jp nz,rt_gui_call
    ENDIF
    ld a,(rt_gui_evtype)
    cp 1
    IF PB_KEYS
    jp z,rt_gui_hit
    cp 3
    ENDIF
    jp nz,rt_gui_loop
    IF PB_KEYS
rt_gui_hit:
    ENDIF
    ld hl,(rt_gui_table)
    inc hl
    ld b,(hl)
    inc hl
    ld a,(rt_gui_object)
    ld c,a
rt_gui_find:
    ld a,b
    or a
    jp z,rt_gui_loop
    ld a,(hl)
    inc hl
    cp c
    jp z,rt_gui_found
    inc hl
    inc hl
    dec b
    jp rt_gui_find
rt_gui_found:
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    IF PB_CANVAS
rt_gui_call:                    ; M9: HL = a handler to run as a button's
    ENDIF
    IF PB_BINDINGS
    IF PB_NUMBERS
    ld a,1
    ld (rt_sync_strict),a
    ENDIF
rt_gui_dispatch:
    ld (rt_gui_handler),hl
    call rt_sync_in
    IF PB_NUMBERS
    jp c,rt_gui_loop
    ENDIF
    ld hl,rt_gui_after
    push hl
    ld hl,(rt_gui_handler)
    jp (hl)

rt_gui_after:
    IF PB_WINDOWS
    ld a,(rt_win_next)
    or a
    jp nz,rt_win_switch
    ENDIF
    ld a,1
    ld (rt_bind_mode),a
    call rt_sync_out
    IF PB_POST
    call rt_gui_post
    ENDIF
    IF PB_CANVAS
    jp rt_cv_after              ; M9: repaint after an alert
    ELSE
    jp rt_gui_loop
    ENDIF
    ELSE
    ld de,rt_gui_loop
    push de
    jp (hl)
    ENDIF

rt_gui_process:
    ld a,4
    call 003Bh
    jp rt_gui_loop

    IF PB_STOPNM
; ----------------------------------------------------------------------------
; M15 Tasks > Stop (LANGUAGE-SPEC 6.1; docs/M15A-PROBE.md). Rosanne does not
; send om_exit for it: the choice arrives as a menu selection, title 0 (the
; Tasks menu the runtime puts first, rt_menu_init), entry 0 (Stop), and is
; the application's to act on (owner XAnne, M15a r4 X3/X4, r5 Y1-Y3).
; A program with menus finds it in its own gui_menu_items: the compiler adds
; the row title 0, entry 0 with rt_exit (no ON STOP: the program ends) or
; cgstop_hook (ON STOP F: calls F and ends the program if F returned TRUE,
; or returns), so rt_gui_menu needs no code of its own. A program without
; menus but with ON STOP comes here (PB_STOPNM).
; ----------------------------------------------------------------------------
rt_gui_stopsel:                 ; no menus of its own: a selection event, IX = its record
    ld a,(ix+3)
    ld c,a
    ld a,(ix+2)
    or c
    jp z,rt_gui_stop
    jp rt_gui_loop              ; any other Tasks entry: left to Rosanne
rt_gui_stop:
    IF PB_NUMBERS
    ld a,1
    ld (rt_sync_strict),a       ; as a menu choice (rt_gui_menu)
    ENDIF
    ld hl,cgstop_hook
    jp rt_gui_dispatch
    ENDIF

; ============================================================================
; Control bindings (M3b): TEXTBOX <-> STRING, CHECKBOX <-> BOOLEAN
; ============================================================================
; Assembled only when the program binds at least one control (PB_BINDINGS,
; defined by the generated program header), so dialog programs without
; TEXTBOX/CHECKBOX assemble to exactly their M3a code.
    IF PB_BINDINGS
; The program's binding table (address in rt_gui_bindings) is a count byte
; followed by 9-byte rows: +0 object number, +1 kind (1 TEXTBOX, 2
; CHECKBOX, 3 LABEL — M5d, IF PB_LABELS), +2 variable address, +4 capacity
; (TEXTBOX, bytes incl. NUL; LABEL: 25, i.e. at most 24 characters shown),
; +5 record template address, +7 declaring source line.
; A LABEL row moves values one way only (variable -> label): rt_sync_in
; skips it; rt_sync_out treats it like a TEXTBOX whose text is at record +12
; (ROSAN283 ob_label "+12 Ascii Text, 0-terminated (max 128 chars)") and whose
; clearing box is object number - 1 (pbas/layout.py, LABELBOX).
;
; When values move (LANGUAGE-SPEC.md section 5, M3b):
;   window opens        rt_sync_out, mode 0: every control set from its
;                       variable, before os_dialog_display;
;   button click        rt_sync_in after os_process_event: every variable
;                       set from its control, then the handler runs;
;   handler returns     rt_sync_out, mode 1: a control whose variable now
;                       differs is redefined and redrawn;
;   any object event    rt_redraw_checks: checkboxes redrawn (the OS records
;                       the toggle in os_process_event but does not repaint
;                       it — POC v0.4.1, XAnne-observed).
;
; OS contracts used (ROSAN283; numbers from OSCALLS under RSSET 1):
;   os_object_get_define 70: "in: E = object number; out: C error / NC
;     CHL = 24-bit address of object definition; AF, B, DE, IX, IY corrupt"
;   os_add_24bit 48: "in: C,HL; BDE = amount to add; out: NC/C, C,HL =
;     updated address; A corrupt" — used instead of `add hl,de`, which
;     would not roll over into the next 16K block.
;   os_get_byte_24bit 42: "in: C,HL; B = wind-on flag 0/1; out: E = byte,
;     C,HL unaffected / wound-on (C=#00 if no more source blocks); A corrupt"
;     (B and D are not specified, so treated as corrupt: B is reloaded each
;     time and the write pointer lives in rt_bind_dst).
;   os_object_define 69: "in: E = object number, CHL = definition (as for
;     os_dialog_define) N.B. Must not be longer than existing definition;
;     out: C error; all corrupt". Records are rebuilt from the template in
;     rt_obj_buf; a TEXTBOX record is at most 41 + capacity bytes, exactly
;     the slot reserved by the initial definition (pbas/layout.py).
;   os_object_update 72: "in: E = object number; out: C error; all corrupt".
; Every byte copied into a BASIC variable or a record goes through rt_put
; (M2.1), so a control text longer than its variable is the reported
; runtime error, attributed to the TEXTBOX's source line, never an overrun.
; Failure of 69/70/48/72 during synchronisation is reported as
; "Runtime error: a window control could not be updated" and exits.
; ----------------------------------------------------------------------------

; rt_bind_start — point rt_bind_row at the first row, rt_bind_left = count.
rt_bind_start:
    ld hl,(rt_gui_bindings)
    ld a,(hl)
    ld (rt_bind_left),a
    inc hl
    ld (rt_bind_row),hl
    ret

; rt_bind_next — advance to the next row.
rt_bind_next:
    ld hl,(rt_bind_row)
    ld de,9
    add hl,de
    ld (rt_bind_row),hl
    ld a,(rt_bind_left)
    dec a
    ld (rt_bind_left),a
    ret

; rt_bind_load — copy the current row's fields into rt_bind_* cells and set
; rt_err_line to the control's declaring line.
rt_bind_load:
    ld hl,(rt_bind_row)
    ld a,(hl)
    ld (rt_bind_obj),a
    inc hl
    ld a,(hl)
    ld (rt_bind_kind),a
    inc hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ex de,hl
    ld (rt_bind_var),hl
    ex de,hl
    ld a,(hl)
    ld (rt_bind_cap),a
    inc hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ex de,hl
    ld (rt_bind_tpl),hl
    ex de,hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    ld (rt_err_line),hl
    ret

; rt_bind_set_end — rt_dst_end = HL + capacity - 1 (the NUL byte of a
; destination of the current TEXTBOX's capacity starting at HL).
rt_bind_set_end:
    ld a,(rt_bind_cap)
    dec a
    ld e,a
    ld d,0
    add hl,de
    ld (rt_dst_end),hl
    ret

; rt_ctl_locate — C,HL = 24-bit address of field A of the current object's
; live definition (os_object_get_define, then os_add_24bit).
rt_ctl_locate:
    ld (rt_bind_off),a
    ld a,(rt_bind_obj)
    ld e,a
    ld a,70
    call 003Bh
    jp c,rt_ctl_failed
    ld a,(rt_bind_off)
    ld e,a
    ld d,0
    ld b,0
    ld a,48
    call 003Bh
    jp c,rt_ctl_failed
    ret

; rt_ctl_read_text — copy the current TEXTBOX's live text (record +41) to
; (rt_bind_dst) through rt_put, then NUL-terminate. Caller sets rt_bind_dst
; and rt_dst_end. Stops at the text's NUL (or if C reports no more blocks).
rt_ctl_read_text:
    ld a,41
    call rt_ctl_locate
rt_ctl_read_loop:
    ld b,1
    ld a,42
    call 003Bh
    ld a,c
    or a
    jp z,rt_ctl_read_done
    ld a,e
    or a
    jp z,rt_ctl_read_done
    ld de,(rt_bind_dst)
    call rt_put
    ex de,hl
    ld (rt_bind_dst),hl
    ex de,hl
    jp rt_ctl_read_loop
rt_ctl_read_done:
    ld hl,(rt_bind_dst)
    ld (hl),0
    ret

; rt_ctl_read_check — A = #00 / #FF: the current CHECKBOX's live status
; (record +9; any non-zero byte counts as checked).
rt_ctl_read_check:
    ld a,9
    call rt_ctl_locate
    ld b,0
    ld a,42
    call 003Bh
    ld a,e
    or a
    ret z
    ld a,0FFh
    ret

; rt_sync_in — every bound variable from its control (before a handler).
; CHECKBOX: BOOLEAN 1 / 0. TEXTBOX: text copied into the variable under
; rt_put with rt_dst_end = variable + capacity - 1.
rt_sync_in:
    call rt_bind_start
rt_sync_in_loop:
    ld a,(rt_bind_left)
    or a
    ret z
    call rt_bind_load
    ld a,(rt_bind_kind)
    IF PB_LABELS
    cp 3
    jp z,rt_sync_in_next
    ENDIF
    IF PB_RADIO
    cp 4
    jp z,rt_sync_in_radio
    ENDIF
    IF PB_NUMBERS
    cp 5
    jp z,rt_sync_in_number
    ENDIF
    IF PB_LIST
    cp 6
    jp z,rt_sync_in_list
    ENDIF
    IF PB_CHOICE
    cp 7
    jp z,rt_sync_in_choice
    ENDIF
    IF PB_SLIDER
    cp 8
    jp z,rt_sync_in_slider
    ENDIF
    cp 2
    jp z,rt_sync_in_check
    ld hl,(rt_bind_var)
    ld (rt_bind_dst),hl
    call rt_bind_set_end
    call rt_ctl_read_text
    jp rt_sync_in_next
rt_sync_in_check:
    call rt_ctl_read_check
    and 1
    ld hl,(rt_bind_var)
    ld (hl),a
    inc hl
    ld (hl),0
rt_sync_in_next:
    call rt_bind_next
    jp rt_sync_in_loop

; rt_sync_out — controls from their variables. rt_bind_mode 0 (window
; opening, before display): every control is redefined, nothing redrawn.
; Mode 1 (after a handler): a control is redefined and redrawn only if its
; live value differs from its variable. A TEXTBOX is redrawn box-first: its
; linked field ob_box (object number - 1, proven by validate_layout) is
; updated before the text edit, because the edit draws only its glyphs and
; the box paints the background (NIKMACRO.Z80 textentry64, "ob_box
; OBLIGATORY"). Without it the new text was drawn over the old (XAnne,
; EDITOR "Keep 5").
rt_sync_out:
    call rt_bind_start
rt_sync_out_loop:
    ld a,(rt_bind_left)
    or a
    ret z
    call rt_bind_load
    ld a,(rt_bind_kind)
    IF PB_LABELS
    cp 3
    jp z,rt_sync_out_label
    ENDIF
    IF PB_RADIO
    cp 4
    jp z,rt_sync_out_radio
    ENDIF
    IF PB_NUMBERS
    cp 5
    jp z,rt_sync_out_number
    ENDIF
    IF PB_LIST
    cp 6
    jp z,rt_sync_out_list
    ENDIF
    IF PB_CHOICE
    cp 7
    jp z,rt_sync_out_choice
    ENDIF
    IF PB_SLIDER
    cp 8
    jp z,rt_sync_out_slider
    ENDIF
    cp 2
    jp z,rt_sync_out_check
    ld a,(rt_bind_mode)
    or a
    jp z,rt_sync_out_text
    ld hl,rt_cmp_buf1
    ld (rt_bind_dst),hl
    call rt_bind_set_end
    call rt_ctl_read_text
    ld hl,rt_cmp_buf1
    ld de,(rt_bind_var)
    call rt_str_compare
    cp 1
    jp z,rt_sync_out_next
rt_sync_out_text:
    ld hl,(rt_bind_tpl)
    ld de,rt_obj_buf
    ld bc,41
    ldir
    ld hl,rt_obj_buf+41
    call rt_bind_set_end
    ld de,rt_obj_buf+41
    ld hl,(rt_bind_var)
    ld a,(rt_bind_cap)
    ld c,a
    ld b,0
    call rt_str_copy
    xor a
    ld (de),a
    jp rt_sync_out_define
rt_sync_out_check:
    ld hl,(rt_bind_var)
    ld a,(hl)
    inc hl
    or (hl)
    jp z,rt_sync_out_value
    ld a,0FFh
rt_sync_out_value:
    ld (rt_bind_val),a
    ld a,(rt_bind_mode)
    or a
    jp z,rt_sync_out_record
    call rt_ctl_read_check
    ld hl,rt_bind_val
    cp (hl)
    jp z,rt_sync_out_next
rt_sync_out_record:
    ld hl,(rt_bind_tpl)
    ld de,rt_obj_buf
    ld bc,9
    ldir
    ld a,(rt_bind_val)
    ld (de),a
rt_sync_out_define:
    ld a,(rt_bind_obj)
    ld e,a
    call 0CBh
    ld c,a
    ld hl,rt_obj_buf
    ld a,69
    call 003Bh
    jp c,rt_ctl_failed
    ld a,(rt_bind_mode)
    or a
    jp z,rt_sync_out_next
    ld a,(rt_bind_kind)
    cp 2
    jp z,rt_sync_out_update
    ld a,(rt_bind_obj)
    dec a
    ld e,a
    ld a,72
    call 003Bh
    jp c,rt_ctl_failed
rt_sync_out_update:
    ld a,(rt_bind_obj)
    ld e,a
    ld a,72
    call 003Bh
    jp c,rt_ctl_failed
rt_sync_out_next:
    call rt_bind_next
    jp rt_sync_out_loop

    IF PB_LABELS
; rt_sync_out_label — a dynamic LABEL row (M5d). Mode 1: compare the live
; label text (record +12) with the variable; equal -> nothing to do. Else
; rebuild the record (template + text) in rt_obj_buf through rt_put with
; rt_dst_end = rt_obj_buf + 12 + 24: a value longer than 24 characters is
; "string too long" at the LABEL's line (rt_err_line), never cut.
; M5d recovery: then every character must be printable ASCII (#20-#7E),
; else "label text has an unsupported character" at the LABEL's line. Both
; checks come before anything is defined or drawn. Why: Rosanne does not
; reliably clip a label to its object (XAnne D3) and its width call is not
; usable (WIDTHDG: os_dialog_string_width returned carry in every test), so
; the label's width is bounded by its content instead: 24 characters of at
; most 12 px (font-7 W = 11 px, measured; every printable character checked
; by XAnne script G1) = 288 px <= the label's 305 px. Then the common
; define/redraw path: os_object_define, and in mode 1 os_object_update of
; the label's box (number - 1) and then of the label.
rt_sync_out_label:
    ld a,(rt_bind_mode)
    or a
    jp z,rt_sync_out_ltext
    ld hl,rt_cmp_buf1
    ld (rt_bind_dst),hl
    call rt_bind_set_end
    ld a,12
    call rt_ctl_locate
    call rt_ctl_read_loop
    ld hl,rt_cmp_buf1
    ld de,(rt_bind_var)
    call rt_str_compare
    cp 1
    jp z,rt_sync_out_next
rt_sync_out_ltext:
    ld hl,(rt_bind_tpl)
    ld de,rt_obj_buf
    ld bc,12
    ldir
    ld hl,rt_obj_buf+12
    call rt_bind_set_end
    ld de,rt_obj_buf+12
    ld hl,(rt_bind_var)
    ld a,(rt_bind_cap)
    ld c,a
    ld b,0
    call rt_str_copy
    xor a
    ld (de),a
    ld hl,rt_obj_buf+12
rt_sync_out_lchar:
    ld a,(hl)
    or a
    jp z,rt_sync_out_define
    cp 20h
    jp c,rt_sync_out_lbad
    cp 7Fh
    jp nc,rt_sync_out_lbad
    inc hl
    jp rt_sync_out_lchar
rt_sync_out_lbad:
    ld hl,rt_err_lchar_text
    ld bc,rt_err_lchar_text_end-rt_err_lchar_text
    jp rt_err_msg
rt_err_lchar_text:
    db "Runtime error: label text has an unsupported character at line "
rt_err_lchar_text_end:
    ENDIF

; rt_redraw_checks — os_object_update for every CHECKBOX binding (after
; os_process_event). Update errors are ignored: this is a repaint only.
rt_redraw_checks:
    call rt_bind_start
rt_redraw_loop:
    ld a,(rt_bind_left)
    or a
    ret z
    call rt_bind_load
    ld a,(rt_bind_kind)
    cp 2
    jp nz,rt_redraw_next
    ld a,(rt_bind_obj)
    ld e,a
    ld a,72
    call 003Bh
rt_redraw_next:
    call rt_bind_next
    jp rt_redraw_loop

; ============================================================================
; M6 Phase 1: radio groups, number fields, windows, menus, timer
; (LANGUAGE-SPEC.md section 5.1). Each part is assembled only for programs
; that use it (PB_RADIO, PB_NUMBERS, PB_SPIN, PB_WINDOWS, PB_POST, PB_FOCUS,
; PB_MENUS, PB_TIMER, defined after the generated program). All of them run
; inside the binding machinery above, which pbas/statements.py assembles
; (PB_BINDINGS = 1) whenever one of these flags is set.
;
; Evidence: documented contracts (ROSAN283, CONSTOS, CONSTBIO, NIKMACRO,
; MACROS), not yet seen in XAnne; UIPROBE.PRG exercises the same calls with
; the same data placement first.
; ============================================================================

    IF PB_RADIO
; ----------------------------------------------------------------------------
; Radio groups (binding kind 4). Row: +0 the first radio's object number,
; +4 the option count n, +5 the address of n 11-byte ob_radio records
; (ROSAN283 os_dialog_define: type, x,y,w,h, "+9 Status #00/#FF", "+10
; Radio Number 0...15"). Option i's caption label is object first+2i-1 and
; its radio first+2i (pbas/layout.py; validate_layout proves it). The
; variable holds 0 (none) or 1..n.
;
; Who clears the rest of a group when one option is clicked is not stated by
; ROSAN283 (UIPROBE P2), so the runtime enforces it: after os_process_event
; reports a click (or the space bar, obev_focfire 12) on a radio or its
; caption, rt_ctl_event redefines every radio of that group with only the
; chosen one set, and redraws them.
; ----------------------------------------------------------------------------

; rt_radio_value — A = 1..n: the first option whose live status is set; 0 if
; none (os_object_get_define via rt_ctl_read_check, which reads rt_bind_obj).
rt_radio_value:
    xor a
    ld (rt_rad_i),a
    ld (rt_rad_v),a
    ld a,(rt_bind_obj)
    ld (rt_rad_obj),a
rt_radio_value_loop:
    ld a,(rt_rad_i)
    ld hl,rt_bind_cap
    cp (hl)
    jp nc,rt_radio_value_done
    inc a
    ld (rt_rad_i),a
    ld a,(rt_bind_obj)
    push af
    ld a,(rt_rad_obj)
    ld (rt_bind_obj),a
    call rt_ctl_read_check
    ld e,a
    pop af
    ld (rt_bind_obj),a
    ld a,e
    or a
    jp z,rt_radio_value_next
    ld a,(rt_rad_v)
    or a
    jp nz,rt_radio_value_next
    ld a,(rt_rad_i)
    ld (rt_rad_v),a
rt_radio_value_next:
    ld a,(rt_rad_obj)
    add a,2
    ld (rt_rad_obj),a
    jp rt_radio_value_loop
rt_radio_value_done:
    ld a,(rt_rad_v)
    ret

; rt_radio_set — redefine the current row's radios with only option
; rt_rad_sel (1..n; 0 = none) set; in rt_bind_mode 1 also redraw each
; (os_object_update). Records come from the row's templates.
rt_radio_set:
    xor a
    ld (rt_rad_i),a
    ld a,(rt_bind_obj)
    ld (rt_rad_obj),a
    ld hl,(rt_bind_tpl)
    ld (rt_rad_tpl),hl
rt_radio_set_loop:
    ld a,(rt_rad_i)
    ld hl,rt_bind_cap
    cp (hl)
    ret nc
    inc a
    ld (rt_rad_i),a
    ld hl,(rt_rad_tpl)
    ld de,rt_obj_buf
    ld bc,11
    ldir
    ld (rt_rad_tpl),hl
    ld a,(rt_rad_i)
    ld hl,rt_rad_sel
    cp (hl)
    ld a,0
    jp nz,rt_radio_set_status
    ld a,0FFh
rt_radio_set_status:
    ld (rt_obj_buf+9),a
    ld a,(rt_rad_obj)
    ld e,a
    call 0CBh
    ld c,a
    ld hl,rt_obj_buf
    ld a,69
    call 003Bh
    jp c,rt_ctl_failed
    ld a,(rt_bind_mode)
    or a
    jp z,rt_radio_set_next
    ld a,(rt_rad_obj)
    ld e,a
    ld a,72
    call 003Bh
    jp c,rt_ctl_failed
rt_radio_set_next:
    ld a,(rt_rad_obj)
    add a,2
    ld (rt_rad_obj),a
    jp rt_radio_set_loop

; rt_sync_in_radio — the variable from the live statuses (0..n).
rt_sync_in_radio:
    call rt_radio_value
    ld hl,(rt_bind_var)
    ld (hl),a
    inc hl
    ld (hl),0
    jp rt_sync_in_next

; rt_sync_out_radio — the radios from the variable. A value outside 0..n is
; "option number out of range" at the RADIO's line (rt_err_line, set by
; rt_bind_load). Mode 1: nothing to do if the live value already matches.
rt_sync_out_radio:
    ld hl,(rt_bind_var)
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld a,d
    or a
    jp nz,rt_radio_range
    ld a,(rt_bind_cap)
    cp e
    jp c,rt_radio_range
    ld a,e
    ld (rt_rad_sel),a
    ld a,(rt_bind_mode)
    or a
    jp z,rt_radio_write
    call rt_radio_value
    ld hl,rt_rad_sel
    cp (hl)
    jp z,rt_sync_out_next
rt_radio_write:
    call rt_radio_set
    jp rt_sync_out_next
rt_radio_range:
    ld hl,rt_err_radio_text
    ld bc,rt_err_radio_text_end-rt_err_radio_text
    jp rt_err_msg
rt_err_radio_text:
    db "Runtime error: option number out of range at line "
rt_err_radio_text_end:
    ENDIF

    IF PB_NUMBERS
; ----------------------------------------------------------------------------
; Number fields (binding kind 5). Row: +0 the text edit's object number (its
; field box is number - 1, its spinner, if any, number + 1), +4 capacity 7,
; +5 the descriptor:
;   +0  the 41-byte ob_textedit record prefix (max length 6; +30/+31 the
;       address of rt_num_legal, +32 its bank, patched here from
;       bios_getmem1; +33 length 11) — ROSAN283 os_text_edit "+21 Wd24
;       24-bit add of legal chrs list", "+24 Byte Length of legal chrs list"
;   +41 Word MIN, +43 Word MAX, +45 Byte spinner object (0 = none),
;   +46 Byte shadow index, +47 Word alert address, +49 Word alert length.
; The shadow (rt_num_shadow) is the value last written to or read from the
; field: after a handler the field is redrawn only if the variable differs
; from it (LANGUAGE-SPEC 5.1 rule 2).
; ----------------------------------------------------------------------------
rt_num_legal:
    db "-0123456789"

; rt_num_low / rt_num_high — HL = the row's MIN / MAX. clobbers DE.
rt_num_low:
    ld hl,(rt_bind_tpl)
    ld de,41
    jp rt_num_word
rt_num_high:
    ld hl,(rt_bind_tpl)
    ld de,43
rt_num_word:
    add hl,de
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    ret

; rt_num_shadow_addr — HL = address of the row's shadow word. clobbers A, DE.
rt_num_shadow_addr:
    ld hl,(rt_bind_tpl)
    ld de,46
    add hl,de
    ld a,(hl)
    add a,a
    ld e,a
    ld d,0
    ld hl,rt_num_shadow
    add hl,de
    ret

; rt_num_shadow_set — shadow = HL. clobbers A, DE, HL.
rt_num_shadow_set:
    push hl
    call rt_num_shadow_addr
    pop de
    ld (hl),e
    inc hl
    ld (hl),d
    ret

; rt_num_shadow_get — HL = shadow. clobbers A, DE.
rt_num_shadow_get:
    call rt_num_shadow_addr
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    ret

; rt_num_parse — HL = NUL-terminated text: an optional '-' and 1+ digits
; giving -32768..32767. out: NC, HL = value; C = anything else. Every
; intermediate magnitude stays below 32779, so nothing wraps.
rt_num_parse:
    ld b,0
    ld a,(hl)
    cp '-'
    jp nz,rt_num_parse_first
    ld b,1
    inc hl
rt_num_parse_first:
    ld a,(hl)
    or a
    jp z,rt_num_parse_bad
    ld de,0
rt_num_parse_loop:
    ld a,(hl)
    or a
    jp z,rt_num_parse_end
    sub '0'
    jp c,rt_num_parse_bad
    cp 10
    jp nc,rt_num_parse_bad
    ld c,a
    ld a,d
    cp 0Ch
    jp c,rt_num_parse_small
    jp nz,rt_num_parse_bad
    ld a,e
    cp 0CEh
    jp nc,rt_num_parse_bad
rt_num_parse_small:
    push hl
    ld h,d
    ld l,e
    add hl,hl
    add hl,hl
    add hl,de
    add hl,hl
    ld e,c
    ld d,0
    add hl,de
    ex de,hl
    pop hl
    ld a,d
    cp 80h
    jp c,rt_num_parse_next
    jp nz,rt_num_parse_bad
    ld a,e
    or a
    jp nz,rt_num_parse_bad
rt_num_parse_next:
    inc hl
    jp rt_num_parse_loop
rt_num_parse_end:
    ld a,b
    or a
    jp nz,rt_num_parse_neg
    ld a,d
    cp 80h
    jp nc,rt_num_parse_bad
    ex de,hl
    or a
    ret
rt_num_parse_neg:
    xor a
    ld h,a
    ld l,a
    sbc hl,de
    or a
    ret
rt_num_parse_bad:
    scf
    ret

; rt_num_read — the current field's live text parsed: NC, HL = value; C =
; not a whole number. The text (at most 6 bytes, the field's max length) is
; copied to rt_cmp_buf1 under rt_put.
rt_num_read:
    ld hl,rt_cmp_buf1
    ld (rt_bind_dst),hl
    call rt_bind_set_end
    call rt_ctl_read_text
    ld hl,rt_cmp_buf1
    jp rt_num_parse

; rt_num_inrange — HL = value: NC if MIN <= value <= MAX, else C; HL kept,
; also left in rt_num_val.
rt_num_inrange:
    ld (rt_num_val),hl
    call rt_num_low
    ld de,(rt_num_val)
    call rt_compare_signed
    or a
    jp z,rt_num_inrange_bad
    call rt_num_high
    ld de,(rt_num_val)
    call rt_compare_signed
    cp 2
    jp z,rt_num_inrange_bad
    ld hl,(rt_num_val)
    or a
    ret
rt_num_inrange_bad:
    ld hl,(rt_num_val)
    scf
    ret

; rt_num_write — show HL in the current field: rebuild the record (template,
; app bank of rt_num_legal, decimal text through rt_put into the 7-byte
; slot), os_object_define, shadow = HL; in mode 1 redraw the field box
; (number - 1) and then the edit, as for a TEXTBOX.
rt_num_write:
    ld (rt_num_val),hl
    ld hl,(rt_bind_tpl)
    ld de,rt_obj_buf
    ld bc,41
    ldir
    call 0CBh
    ld (rt_obj_buf+32),a
    ld hl,rt_obj_buf+47
    ld (rt_dst_end),hl
    ld de,rt_obj_buf+41
    ld hl,(rt_num_val)
    call rt_append_int
    xor a
    ld (de),a
    ld a,(rt_bind_obj)
    ld e,a
    call 0CBh
    ld c,a
    ld hl,rt_obj_buf
    ld a,69
    call 003Bh
    jp c,rt_ctl_failed
    ld hl,(rt_num_val)
    call rt_num_shadow_set
    ld a,(rt_bind_mode)
    or a
    ret z
    ld a,(rt_bind_obj)
    dec a
    ld e,a
    ld a,72
    call 003Bh
    jp c,rt_ctl_failed
    ld a,(rt_bind_obj)
    ld e,a
    ld a,72
    call 003Bh
    jp c,rt_ctl_failed
    ret

; rt_sync_in_number — the variable from the field. Invalid text: before a
; timer handler (rt_sync_strict 0) the variable is left alone; before a
; button or menu handler the field's alert is shown, the field is put back
; to its last valid number (the shadow) so that the next action is not
; refused again, it gets the focus (os_set_focus, ROSAN283: errors
; ignored) and rt_sync_in returns C, so the handler does not run.
rt_sync_in_number:
    call rt_num_read
    jp c,rt_num_invalid
    call rt_num_inrange
    jp c,rt_num_invalid
    ex de,hl
    ld hl,(rt_bind_var)
    ld (hl),e
    inc hl
    ld (hl),d
    ex de,hl
    call rt_num_shadow_set
    jp rt_sync_in_next
rt_num_invalid:
    ld a,(rt_sync_strict)
    or a
    jp z,rt_sync_in_next
    ld hl,(rt_bind_tpl)
    ld de,47
    add hl,de
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld c,(hl)
    inc hl
    ld b,(hl)
    ex de,hl
    ld d,b
    ld e,c
    call rt_alert
    ld a,1
    ld (rt_bind_mode),a
    call rt_num_shadow_get
    call rt_num_write
    ld a,(rt_bind_obj)
    ld e,a
    ld a,73
    call 003Bh
    scf
    ret

; rt_sync_out_number — the field from the variable; outside MIN..MAX is
; "number out of range" at the NUMBERBOX's line. Mode 1: redrawn only if the
; variable differs from the shadow (the handler changed it).
rt_sync_out_number:
    ld hl,(rt_bind_var)
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    call rt_num_inrange
    jp c,rt_num_range_err
    ld a,(rt_bind_mode)
    or a
    jp z,rt_num_out_write
    call rt_num_shadow_get
    ld de,(rt_num_val)
    or a
    sbc hl,de
    jp z,rt_sync_out_next
    ld hl,(rt_num_val)
rt_num_out_write:
    call rt_num_write
    jp rt_sync_out_next
rt_num_range_err:
    ld hl,rt_err_num_text
    ld bc,rt_err_num_text_end-rt_err_num_text
    jp rt_err_msg
rt_err_num_text:
    db "Runtime error: number out of range at line "
rt_err_num_text_end:
    ENDIF

    IF PB_RADIO + PB_SPIN + PB_CTL2
; ----------------------------------------------------------------------------
; rt_ctl_event — after os_process_event: apply what Rosanne leaves to the
; program. A click, double-click or space bar on a radio or its caption
; selects that option alone (see "Radio groups"); a click on a spinner
; (ROSAN283: "ob_spinner: B = 1 spinner up / 5 spinner down", not recorded by
; os_process_event) moves its field by 1 within MIN..MAX — from the field's
; number, or from the shadow if the text is not a number.
; Phase 1 fix (owner XAnne: a click sometimes jumped the number by more than
; ten): only obev_click / obev_dclick (1 / 2) step — B is documented for
; those event types alone ("extra info for certain object types only") and
; any other event on the spinner left a stale B that stepped again — and
; after each step os_flush_events (fn 5: "flush all pending events from the
; OS event pipe"; in: none, out: AF, HL corrupt) drops whatever queued up
; while the field was redrawn, so a backlog of repeat events cannot replay
; as a burst after the mouse button is released.
; ----------------------------------------------------------------------------
rt_ctl_event:
    IF PB_CHANGE
    ld hl,0
    ld (rt_ctl_pending),hl
    ENDIF
    call rt_bind_start
rt_ctl_ev_loop:
    ld a,(rt_bind_left)
    or a
    ret z
    call rt_bind_load
    ld a,(rt_bind_kind)
    IF PB_RADIO
    cp 4
    jp z,rt_ctl_ev_radio
    ENDIF
    IF PB_SPIN
    cp 5
    jp z,rt_ctl_ev_spin
    ENDIF
    IF PB_LIST
    cp 6
    jp z,rt_ctl_ev_list
    ENDIF
    IF PB_CHOICE
    cp 7
    jp z,rt_ctl_ev_choice
    ENDIF
    IF PB_SLIDER
    cp 8
    jp z,rt_ctl_ev_slider
    ENDIF
rt_ctl_ev_next:
    call rt_bind_next
    jp rt_ctl_ev_loop

    IF PB_RADIO
rt_ctl_ev_radio:
    ld a,(rt_gui_evtype)
    cp 1
    jp z,rt_ctl_ev_r1
    cp 2
    jp z,rt_ctl_ev_r1
    cp 12
    jp nz,rt_ctl_ev_next
rt_ctl_ev_r1:
    ld a,(rt_bind_obj)
    dec a
    ld c,a
    ld a,(rt_gui_object)
    sub c
    jp c,rt_ctl_ev_next
    srl a
    ld hl,rt_bind_cap
    cp (hl)
    jp nc,rt_ctl_ev_next
    inc a
    ld (rt_rad_sel),a
    ld a,1
    ld (rt_bind_mode),a
    call rt_radio_set
    jp rt_ctl_ev_next
    ENDIF

    IF PB_SPIN
rt_ctl_ev_spin:
    ld hl,(rt_bind_tpl)
    ld de,45
    add hl,de
    ld a,(hl)
    or a
    jp z,rt_ctl_ev_next
    ld c,a
    ld a,(rt_gui_object)
    cp c
    jp nz,rt_ctl_ev_next
    ld a,(rt_gui_evtype)
    cp 1
    jp z,rt_spin_click
    cp 2
    jp nz,rt_ctl_ev_next
rt_spin_click:
    ld a,(rt_gui_b)
    cp 1
    jp z,rt_spin_go
    cp 5
    jp nz,rt_ctl_ev_next
rt_spin_go:
    ld (rt_spin_dir),a
    call rt_num_read
    jp nc,rt_spin_have
    call rt_num_shadow_get
rt_spin_have:
    ld (rt_num_val),hl
    ld a,(rt_spin_dir)
    cp 1
    jp z,rt_spin_up
    call rt_num_high
    ld de,(rt_num_val)
    call rt_compare_signed
    cp 2
    jp z,rt_spin_high
    call rt_num_low
    ld de,(rt_num_val)
    call rt_compare_signed
    cp 2
    jp nz,rt_spin_low
    ld hl,(rt_num_val)
    dec hl
    jp rt_spin_set
rt_spin_up:
    call rt_num_low
    ld de,(rt_num_val)
    call rt_compare_signed
    or a
    jp z,rt_spin_low
    call rt_num_high
    ld de,(rt_num_val)
    call rt_compare_signed
    or a
    jp nz,rt_spin_high
    ld hl,(rt_num_val)
    inc hl
    jp rt_spin_set
rt_spin_high:
    call rt_num_high
    jp rt_spin_set
rt_spin_low:
    call rt_num_low
rt_spin_set:
    ld a,1
    ld (rt_bind_mode),a
    call rt_num_write
    ld a,5
    call 003Bh
    jp rt_ctl_ev_next
    ENDIF
    ENDIF

    IF PB_WINDOWS
; ----------------------------------------------------------------------------
; Windows (SHOW). The generated window table: count, then per window three
; words: dialog definition, handler table, binding table. rt_win_cur is the
; open window (1-based); SHOW stores the next one in rt_win_next.
; rt_win_start (from the main line, HL = table) opens rt_win_next, or window
; 1; rt_win_switch (after a handler) removes the open dialog first
; (os_dialog_remove, ROSAN283: "Screen contents restored if required") and
; then opens the next window exactly as the first one opened (rt_gui_run:
; define, controls from variables, display, focus).
; ----------------------------------------------------------------------------
rt_win_start:
    ld (rt_win_table),hl
    ld a,(rt_win_next)
    or a
    jp nz,rt_win_start_n
    ld a,1
rt_win_start_n:
    ld (rt_win_cur),a
    xor a
    ld (rt_win_next),a
rt_win_open:
    ld a,(rt_win_cur)
    dec a
    ld l,a
    ld h,0
    ld d,h
    ld e,l
    add hl,hl
    add hl,de
    add hl,hl
    ld de,(rt_win_table)
    inc de
    add hl,de
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    push de
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    push de
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    ld (rt_gui_bindings),hl
    pop de
    pop hl
    jp rt_gui_run

rt_win_switch:
    ld hl,rt_win_cur
    cp (hl)
    jp z,rt_win_same
    ld (hl),a
    xor a
    ld (rt_win_next),a
    ld (rt_dialog_open),a
    IF PB_CANVAS
    ld (rt_cv_on),a             ; M9: no drawing while no canvas is shown
    ENDIF
    ld a,68
    call 003Bh
    jp rt_win_open
rt_win_same:
    xor a
    ld (rt_win_next),a
    jp rt_gui_after
    ENDIF

    IF PB_POST
; ----------------------------------------------------------------------------
; rt_gui_post — after a window opens and after every handler: a pending
; FOCUS request for the open window (os_set_focus, errors ignored), then the
; menu ticks.
; ----------------------------------------------------------------------------
rt_gui_post:
    IF PB_FOCUS
    ld a,(rt_focus_obj)
    or a
    jp z,rt_post_menu
    IF PB_WINDOWS
    ld a,(rt_focus_win)
    ld hl,rt_win_cur
    cp (hl)
    jp nz,rt_post_menu
    ENDIF
    ld a,(rt_focus_obj)
    ld e,a
    xor a
    ld (rt_focus_obj),a
    ld a,73
    call 003Bh
rt_post_menu:
    ENDIF
    IF PB_MENUS
    jp rt_menu_ticks
    ELSE
    ret
    ENDIF
    ENDIF

    IF PB_MENUS
; ----------------------------------------------------------------------------
; Menus. rt_menu_init (once, before the first window opens): the Tasks menu
; into the workspace at #2400 of block #80 (os_ddm_get_tasks, fn 14: "C,HL =
; 24-bit address of buffer ... out: HL = 14-bit address of next byte after
; tasks list (in block defined by C) i.e. CHL points to where to add your
; own data for other menus"), the program's titles copied after it, then
; os_ddm_define (fn 12, C,HL, B = 0: no Undo/Help) and os_ddm_display (13).
; The area ends at #2C00 (2048 bytes, the documented maximum); a Tasks menu
; leaving no room is "the menus are too large", never cut. ROSAN283
; 'Memory Layout': "AP may use #2000...#2FFF"; the file routines use #2100-
; #2140.
; ----------------------------------------------------------------------------
rt_menu_init:
    ld c,80h
    ld hl,2400h
    ld a,14
    call 003Bh
    ld a,h
    and 3Fh
    ld h,a
    ld (rt_menu_end),hl
    ld de,gui_menu_def_end-gui_menu_def
    add hl,de
    ld de,2C01h
    or a
    sbc hl,de
    jp nc,rt_menu_too_large
    ld hl,(rt_menu_end)
    ex de,hl
    ld hl,gui_menu_def
    ld bc,gui_menu_def_end-gui_menu_def
    ldir
    ld c,80h
    ld hl,2400h
    ld b,0
    ld a,12
    call 003Bh
    ld a,13
    call 003Bh
    ret
rt_menu_too_large:
    ld hl,rt_menu_large_alert
    ld de,rt_menu_large_alert_end-rt_menu_large_alert
    call rt_alert
    jp rt_exit
rt_menu_large_alert:
    db "Runtime error: the menus are too large",0,0,1
    dw 800Dh,80FBh,0,0
    db 79,75,0
rt_menu_large_alert_end:

; rt_gui_menu — a menu selection event (event code bit 1; record +2 title,
; +3 entry). Looks up gui_menu_items (count, rows: title, entry, handler)
; and runs the handler like a button's; anything else (the Tasks menu,
; dividers) is left to Rosanne.
rt_gui_menu:
    ld a,(ix+2)
    ld (rt_menu_t),a
    ld a,(ix+3)
    ld (rt_menu_e),a
    ld hl,gui_menu_items
    ld b,(hl)
    inc hl
rt_menu_find:
    ld a,b
    or a
    jp z,rt_gui_loop
    ld a,(rt_menu_t)
    cp (hl)
    jp nz,rt_menu_skip
    inc hl
    ld a,(rt_menu_e)
    cp (hl)
    jp nz,rt_menu_skip1
    inc hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    IF PB_NUMBERS
    ld a,1
    ld (rt_sync_strict),a
    ENDIF
    jp rt_gui_dispatch
rt_menu_skip:
    inc hl
rt_menu_skip1:
    inc hl
    inc hl
    inc hl
    dec b
    jp rt_menu_find

; rt_menu_ticks — every TICK item from its BOOLEAN (gui_menu_ticks: count,
; rows: title, entry, variable address): os_ddm_put_entry_status (fn 18:
; "C = title, B = entry, E = entry status"), status #80 (bit 7 always 1) +
; tickable #02 + ticked #04 (CONSTOS ddc_tkbl, ddc_tked). Errors ignored.
rt_menu_ticks:
    ld hl,gui_menu_ticks
    ld a,(hl)
    ld (rt_menu_n),a
    inc hl
rt_menu_tick_loop:
    ld a,(rt_menu_n)
    or a
    ret z
    dec a
    ld (rt_menu_n),a
    ld c,(hl)
    inc hl
    ld b,(hl)
    inc hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld (rt_menu_p),hl
    ex de,hl
    ld a,(hl)
    inc hl
    or (hl)
    ld e,82h
    jp z,rt_menu_tick_put
    ld e,86h
rt_menu_tick_put:
    ld a,18
    call 003Bh
    ld hl,(rt_menu_p)
    jp rt_menu_tick_loop
    ENDIF

    IF PB_TIMER
; ----------------------------------------------------------------------------
; Timer. gui_timer_rec is a 12-byte timer record (ROSAN283 os_set_timer, fn
; 8: "C,HL = 24-bit address of Timer Record (... only bytes 2..5 needed)":
; +2 timer 0, +3 1 = repeating, +4 interval in 1/16 s); os_kill_timer (fn 9:
; "E = timer number 0..3"). rt_timer_run is 1 while it runs; a tick that
; arrives after TIMER OFF is ignored.
; ----------------------------------------------------------------------------
rt_timer_start:
    ld a,(rt_timer_run)
    or a
    ret nz
    IF PB_TICKPOLL
    ld a,0FFh                   ; rt_clockticks: no second seen yet
    ld (rt_ck_d),a
    call rt_clockticks
    ld de,(gui_timer_rec+4)
    call rt_tick_add
    ld (rt_tick_due),hl
    ld a,1
    ld (rt_timer_run),a
    ret
    ELSE
    call 0CBh
    ld c,a
    ld hl,gui_timer_rec
    ld a,8
    call 003Bh
    jp c,rt_timer_failed
    ld a,1
    ld (rt_timer_run),a
    ret
    ENDIF
rt_timer_failed:
    ld hl,rt_timer_alert
    ld de,rt_timer_alert_end-rt_timer_alert
    call rt_alert
    jp rt_exit
rt_timer_alert:
    db "Runtime error: the timer could not be started",0,0,1
    dw 800Dh,80FBh,0,0
    db 79,75,0
rt_timer_alert_end:

rt_timer_stop:
    ld a,(rt_timer_run)
    or a
    ret z
    xor a
    ld (rt_timer_run),a
    IF PB_TICKPOLL
    ret
    ENDIF
    ld e,0
    ld a,9
    call 003Bh
    ret

    IF PB_TICKPOLL
; ----------------------------------------------------------------------------
; M13 responsiveness: TIMER Handler, EVERY n TICKS (n 1..240) is not a
; Rosanne timer. Rosanne's timer service (PCW045.SYS block 6 #6830) compares
; a deadline of seconds and ticks byte (#6958: ticks + interval, carried
; into the seconds, and #F0) with bios_gettime; with #F9 out of step with
; the seconds (XAnne) a deadline past #F9's wrap is reached only when the
; seconds register changes, so the timer stopped for up to a second, once a
; second (owner: JUMPER ran, paused, ran; TIMEPRB 90 events of 160, TIMEPR4
; 28 of 40; docs/M13-RESPONSIVENESS.md). Instead the event loop compares
; CLOCKTICKS with rt_tick_due before each look for an event: when due, the
; handler runs and the next one is due an interval later, or an interval
; from now if the handler fell more than an interval behind (no burst of
; catching up: lib/pace.pbas counts the time).
; The loop then looks with os_get_event (fn 1: "Z if no matching event
; pending"), not os_wait_event (fn 2: "can't be Z for no event"), which
; does not return until an event comes: with no Rosanne timer and no input
; the handler never ran (owner, RT6: TIMEPRB Idle stopped until the mouse
; moved; JUMPER froze when no key was held). This costs no more processor
; time than waiting: os_wait_event is itself a loop over the same retrieval
; [static: block 6 #558E calls #55A8 and repeats while Z (#5596); no HALT].
; rt_tick_poll — NZ: due (rt_tick_due moved on); Z: not due, or no TIMER.
; clobbers: AF, BC, DE, HL
; ----------------------------------------------------------------------------
rt_tick_poll:
    ld a,(rt_timer_run)
    or a
    ret z
    call rt_clockticks
    push hl                     ; now
    ld de,(rt_tick_due)
    call rt_tick_diff           ; HL = now - due, 0..959
    ld de,480
    or a
    sbc hl,de
    jr nc,rt_tick_not           ; 480..959: the due time is still ahead
    add hl,de
    ld de,(gui_timer_rec+4)
    or a
    sbc hl,de                   ; NC: behind by an interval or more
    pop hl
    jr nc,rt_tick_from          ; then the next one an interval from now
    ld hl,(rt_tick_due)
rt_tick_from:
    ld de,(gui_timer_rec+4)
    call rt_tick_add
    ld (rt_tick_due),hl
    or 1
    ret
rt_tick_not:
    pop hl
    xor a
    ret

; rt_tick_diff — HL = (HL - DE) mod 960, HL and DE 0..959. clobbers: AF
rt_tick_diff:
    or a
    sbc hl,de
    ret nc
    ld de,960
    add hl,de
    ret

; rt_tick_add — HL = (HL + DE) mod 960, HL 0..959, DE 1..240. clobbers: AF
rt_tick_add:
    add hl,de
    push hl
    ld de,960
    or a
    sbc hl,de
    pop de
    ret nc
    ex de,hl
    ret
    ENDIF

rt_gui_timer:
    ld a,(rt_timer_run)
    or a
    jp z,rt_gui_loop
    ld hl,(gui_timer_handler)
    IF PB_NUMBERS
    xor a
    ld (rt_sync_strict),a
    ENDIF
    jp rt_gui_dispatch
    ENDIF

    IF PB_CTL2
; ============================================================================
; M6 Phase 2: lists, drop-down choices, sliders (LANGUAGE-SPEC.md §5.2)
; ============================================================================
; Binding kinds 6 LIST, 7 CHOICE, 8 SLIDER. Rosanne records a list's or a
; drop-down's selection in its own copy of the dialog when os_process_event
; handles a click ("records the value changes in the dialog data"), but not
; scroll bars ("except scroll-bars / spinners"), so the runtime applies
; scroll events itself, through one shared step routine. Items are shown
; from a table of 24-bit pointers into the program's STRING array (ROSAN283
; ob_list "+25 Wd24 24-bit address of string-list = list of 24-bit
; addresses"; ob_dropbutton "+24 Wd24"), built here; each item shown must be
; at most 24 printable ASCII characters (the M5d label basis: font 7, 305 px)
; or the program stops with a defined error at the control's line.
; Evidence: documented (ROSAN283, CONSTOS, NIKMACRO n_list_box, MACROS
; bb_droplist); UIPROBE2 checks the open points (selection "none", scroll
; codes and handle geometry, who writes a drop-down's readout).
; ----------------------------------------------------------------------------

; rt_tpl_word / rt_tpl_byte — HL / A = the word / byte at (rt_bind_tpl)+A.
; clobbers DE.
rt_tpl_word:
    ld hl,(rt_bind_tpl)
    ld e,a
    ld d,0
    add hl,de
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    ret
rt_tpl_byte:
    ld hl,(rt_bind_tpl)
    ld e,a
    ld d,0
    add hl,de
    ld a,(hl)
    ret

; rt_live_word — HL = the word at offset A of the current object's live
; definition (os_object_get_define, os_add_24bit, two os_get_byte_24bit).
rt_live_word:
    call rt_ctl_locate
    ld b,1
    ld a,42
    call 003Bh
    ld a,e
    ld (rt_c2_word),a
    ld b,0
    ld a,42
    call 003Bh
    ld a,e
    ld (rt_c2_word+1),a
    ld hl,(rt_c2_word)
    ret

; rt_udiv — HL = HL / DE, unsigned, DE > 0. clobbers AF, BC.
rt_udiv:
    ld b,h
    ld c,l
    ld hl,0
    ld a,16
rt_udiv_loop:
    sla c
    rl b
    adc hl,hl
    or a
    sbc hl,de
    jp nc,rt_udiv_fits
    add hl,de
    jp rt_udiv_next
rt_udiv_fits:
    inc c
rt_udiv_next:
    dec a
    jp nz,rt_udiv_loop
    ld h,b
    ld l,c
    ret

; rt_count_get — HL = the control's item count (the INTEGER whose address is
; at descriptor offset A), checked 0..array length: else "Runtime error:
; list count out of range at line N". rt_c2_arr = the array descriptor
; (offset A+2), rt_c2_n = the count.
rt_count_get:
    push af
    call rt_tpl_word
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld (rt_c2_n),de
    pop af
    add a,2
    call rt_tpl_word
    ld (rt_c2_arr),hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld hl,(rt_c2_n)
    ld a,h
    or a
    jp m,rt_count_bad
    ex de,hl
    or a
    sbc hl,de
    jp c,rt_count_bad
    ld hl,(rt_c2_n)
    ret
rt_count_bad:
    ld hl,rt_err_count_text
    ld bc,rt_err_count_text_end-rt_err_count_text
    jp rt_err_msg
rt_err_count_text:
    db "Runtime error: list count out of range at line "
rt_err_count_text_end:

; rt_sel_get — rt_c2_sel = the selection variable, checked 0..rt_c2_n:
; else "Runtime error: list position out of range at line N".
rt_sel_get:
    ld hl,(rt_bind_var)
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld (rt_c2_sel),de
    ld a,d
    or a
    jp m,rt_sel_bad
    ld hl,(rt_c2_n)
    or a
    sbc hl,de
    ret nc
rt_sel_bad:
    ld hl,rt_err_pos_text
    ld bc,rt_err_pos_text_end-rt_err_pos_text
    jp rt_err_msg
rt_err_pos_text:
    db "Runtime error: list position out of range at line "
rt_err_pos_text_end:

; rt_live_sel — rt_c2_sel from the live selection word at offset A: n+1 if
; below the count, else 0 ("none").
rt_live_sel:
    call rt_live_word
    ld de,(rt_c2_n)
    push hl
    or a
    sbc hl,de
    pop hl
    jp nc,rt_live_sel_none
    inc hl
    ld (rt_c2_sel),hl
    ret
rt_live_sel_none:
    ld hl,0
    ld (rt_c2_sel),hl
    ret

; rt_items_build — fill the pointer table at HL with rt_c2_n entries of
; (address, app bank) for the elements of the array rt_c2_arr, checking each
; text: more than 24 characters is "string too long", a character outside
; #20-#7E is "list text has an unsupported character" (both at rt_err_line).
; Every other slot of the table (its slot count is the word before it)
; points at an empty string. Owner XAnne (M7 retest): Rosanne draws visible
; rows past the count from the table too; zero slots showed OS text and a
; slot left from a longer list showed a stale ("ghost") item.
rt_items_build:
    ld (rt_c2_tab),hl
    dec hl
    ld d,(hl)
    dec hl
    ld e,(hl)
    ld hl,(rt_c2_n)
    ex de,hl
    or a
    sbc hl,de
    ld (rt_c2_pad),hl           ; slots - count (count <= length <= slots)
    ld hl,(rt_c2_arr)
    inc hl
    inc hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld (rt_c2_size),de
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld (rt_c2_ptr),de
    ld hl,(rt_c2_n)
    ld (rt_c2_left),hl
rt_items_loop:
    ld hl,(rt_c2_left)
    ld a,h
    or l
    jp z,rt_items_pad
    dec hl
    ld (rt_c2_left),hl
    ld hl,(rt_c2_ptr)
    ld b,25
rt_items_char:
    ld a,(hl)
    or a
    jp z,rt_items_ok
    dec b
    jp z,rt_err_string_overflow
    cp 20h
    jp c,rt_items_bad
    cp 7Fh
    jp nc,rt_items_bad
    inc hl
    jp rt_items_char
rt_items_ok:
    ld hl,(rt_c2_tab)
    ld de,(rt_c2_ptr)
    ld (hl),e
    inc hl
    ld (hl),d
    inc hl
    call 0CBh
    ld (hl),a
    inc hl
    ld (rt_c2_tab),hl
    ld hl,(rt_c2_ptr)
    ld de,(rt_c2_size)
    add hl,de
    ld (rt_c2_ptr),hl
    jp rt_items_loop
rt_items_pad:
    ld hl,(rt_c2_pad)
    ld a,h
    or l
    ret z
    dec hl
    ld (rt_c2_pad),hl
    ld hl,(rt_c2_tab)
    ld de,rt_items_none
    ld (hl),e
    inc hl
    ld (hl),d
    inc hl
    call 0CBh
    ld (hl),a
    inc hl
    ld (rt_c2_tab),hl
    jp rt_items_pad
rt_items_none:
    db 0                        ; the text of an unused row
rt_items_bad:
    ld hl,rt_err_ltext_text
    ld bc,rt_err_ltext_text_end-rt_err_ltext_text
    jp rt_err_msg
rt_err_ltext_text:
    db "Runtime error: list text has an unsupported character at line "
rt_err_ltext_text_end:

; rt_sel_word — HL = rt_c2_sel - 1, or #FFFF for "none" (0).
rt_sel_word:
    ld hl,(rt_c2_sel)
    dec hl
    ret

; rt_define_buf — os_object_define of object A from rt_obj_buf; in
; rt_bind_mode 1 also os_object_update (errors: the window-control alert).
rt_define_buf:
    call rt_define_obj
    ld a,(rt_bind_mode)
    or a
    ret z
    ld a,(rt_c2_obj)
rt_update_obj:
    ld e,a
    ld a,72
    call 003Bh
    jp c,rt_ctl_failed
    ret

; rt_define_obj — os_object_define of object A from rt_obj_buf only.
rt_define_obj:
    ld (rt_c2_obj),a
    ld e,a
    call 0CBh
    ld c,a
    ld hl,rt_obj_buf
    ld a,69
    call 003Bh
    jp c,rt_ctl_failed
    ret

; rt_display_obj — os_object_display (fn 71) of object A: "display one
; object in current dialog"; out: C error (the window-control alert).
rt_display_obj:
    ld e,a
    ld a,71
    call 003Bh
    jp c,rt_ctl_failed
    ret

; rt_flush_after — os_flush_events (fn 5) after a step, as for spinners
; (M6 Phase 1): input queued while the control was redrawn is dropped.
rt_flush_after:
    ld a,5
    call 003Bh
    ret

    IF PB_SCROLL
; rt_scroll_step — the shared scroll rule. in: rt_sc_val (current value),
; rt_sc_min, rt_sc_max, rt_sc_page, rt_sc_span (handle travel in pixels),
; rt_gui_b / rt_gui_de from os_process_event (ROSAN283: B = 1 arrow
; up/left, 2 page up/left, 3 handle moved with DE = new position, 4 page
; down/right, 5 arrow down/right). out: HL = the new value within min..max.
rt_scroll_step:
    ld hl,(rt_sc_val)
    ld a,(rt_gui_b)
    cp 1
    jp z,rt_scroll_m1
    cp 5
    jp z,rt_scroll_p1
    ld de,(rt_sc_page)
    cp 2
    jp z,rt_scroll_mpage
    cp 4
    jp z,rt_scroll_ppage
    cp 3
    jp nz,rt_scroll_clamp
    ld hl,(rt_sc_span)
    ld a,h
    or l
    jp z,rt_scroll_tomin
    ld de,(rt_gui_de)
    or a
    sbc hl,de
    jp nc,rt_scroll_drag
    ld de,(rt_sc_span)
rt_scroll_drag:
    ld hl,(rt_sc_max)
    push de
    ld de,(rt_sc_min)
    or a
    sbc hl,de
    pop de
    call rt_mul16
    ld de,(rt_sc_span)
    srl d
    rr e
    add hl,de
    ld de,(rt_sc_span)
    call rt_udiv
    ld de,(rt_sc_min)
    add hl,de
    jp rt_scroll_clamp
rt_scroll_m1:
    dec hl
    jp rt_scroll_clamp
rt_scroll_p1:
    inc hl
    jp rt_scroll_clamp
rt_scroll_mpage:
    or a
    sbc hl,de
    jp rt_scroll_clamp
rt_scroll_ppage:
    add hl,de
rt_scroll_clamp:
    ld (rt_sc_val),hl
    ex de,hl
    ld hl,(rt_sc_min)
    call rt_compare_signed
    or a
    jp z,rt_scroll_tomin
    ld de,(rt_sc_val)
    ld hl,(rt_sc_max)
    call rt_compare_signed
    cp 2
    jp z,rt_scroll_tomax
    ld hl,(rt_sc_val)
    ret
rt_scroll_tomin:
    ld hl,(rt_sc_min)
    ret
rt_scroll_tomax:
    ld hl,(rt_sc_max)
    ret

; rt_scroll_pos — HL = handle position: rt_sc_span * (HL - min) / (max -
; min), 0 when max = min.
rt_scroll_pos:
    ld de,(rt_sc_min)
    or a
    sbc hl,de
    push hl
    ld hl,(rt_sc_max)
    or a
    sbc hl,de
    ld a,h
    or l
    pop de
    ret z
    push hl
    ld hl,(rt_sc_span)
    call rt_mul16
    pop de
    jp rt_udiv
    ENDIF

    IF PB_LIST
; ----------------------------------------------------------------------------
; LIST (kind 6). Descriptor: +0 the 30-byte ob_list record (+25 pointer
; table, +27 bank patched here), +30 the 14-byte ob_vscroll record, +44
; count address, +46 array descriptor, +48 pointer table, +50 rows shown,
; +51 scroll-bar object, +52 track length, +54 CHANGE, +56 ACTION handler.
; ----------------------------------------------------------------------------

; rt_list_limits — rt_c2_vis = rows shown, rt_sc_max = the last possible
; first row (n - rows, or 0 when everything fits).
rt_list_limits:
    ld a,50
    call rt_tpl_byte
    ld l,a
    ld h,0
    ld (rt_c2_vis),hl
    ex de,hl
    ld hl,(rt_c2_n)
    or a
    sbc hl,de
    jp nc,rt_list_limits2
    ld hl,0
rt_list_limits2:
    ld (rt_sc_max),hl
    ret

; rt_list_show — show rt_c2_n items with selection rt_c2_sel from first row
; rt_c2_first, moved (within 0..rt_sc_max) so that a selected item is
; visible; rt_list_show_at keeps rt_c2_first as it is (scrolling). The list
; and its scroll bar are rebuilt and, in mode 1, redrawn (frame box first).
rt_list_show:
    call rt_list_limits
    ld hl,(rt_sc_max)
    ld de,(rt_c2_first)
    or a
    sbc hl,de
    jp nc,rt_list_first_ok
    ld hl,(rt_sc_max)
    ld (rt_c2_first),hl
rt_list_first_ok:
    ld hl,(rt_c2_sel)
    ld a,h
    or l
    jp z,rt_list_show_at
    dec hl
    ld de,(rt_c2_first)
    push hl
    or a
    sbc hl,de
    pop hl
    jp nc,rt_list_below
    ld (rt_c2_first),hl
    jp rt_list_show_at
rt_list_below:
    ex de,hl
    ld hl,(rt_c2_first)
    ld bc,(rt_c2_vis)
    add hl,bc
    ex de,hl
    or a
    sbc hl,de
    jp c,rt_list_show_at
    inc hl
    ld de,(rt_c2_first)
    add hl,de
    ld (rt_c2_first),hl
rt_list_show_at:
    call rt_list_limits
    ld a,48
    call rt_tpl_word
    call rt_items_build
    ld hl,(rt_bind_tpl)
    ld de,rt_obj_buf
    ld bc,30
    ldir
    call 0CBh
    ld (rt_obj_buf+27),a
    ld hl,(rt_c2_n)
    ld (rt_obj_buf+10),hl
    ld hl,(rt_c2_first)
    ld (rt_obj_buf+14),hl
    call rt_sel_word
    ld (rt_obj_buf+18),hl
; Repair (owner XAnne, UIPROBE2 U6: a list redefined, then updated after its
; frame box was repainted, stayed blank): the "previous first visible /
; previous selection" words (ROSAN283 ob_list +16 / +20, "Reserved") are set
; to #FFFF, not to the new values, and the list is drawn with
; os_object_display (fn 71, "display one object") instead of
; os_object_update (fn 72, "update display"), which XAnne showed does not
; repaint unchanged rows. UIPROBE3 checks each half separately.
    ld hl,0FFFFh
    ld (rt_obj_buf+16),hl
    ld (rt_obj_buf+20),hl
    ld a,(rt_bind_mode)
    or a
    jp z,rt_list_define
    ld a,(rt_bind_obj)
    dec a
    call rt_update_obj
rt_list_define:
    ld a,(rt_bind_obj)
    call rt_define_obj
    ld a,(rt_bind_mode)
    or a
    jp z,rt_list_bar
    ld a,(rt_bind_obj)
    call rt_display_obj
; the scroll bar, from rt_c2_first
rt_list_bar:
    call rt_list_geom
    ld hl,(rt_c2_first)
    call rt_scroll_pos
    push hl
    ld hl,(rt_bind_tpl)
    ld de,30
    add hl,de
    ld de,rt_obj_buf
    ld bc,14
    ldir
    pop hl
    ld (rt_obj_buf+10),hl
    ld hl,(rt_c2_hsize)
    ld (rt_obj_buf+12),hl
    ld a,51
    call rt_tpl_byte
    jp rt_define_buf

; rt_list_geom — scroll-bar geometry after rt_list_limits: handle size
; track * rows / n (at least 8; the whole track when everything fits),
; rt_sc_span = track - handle size (the handle's travel), rt_sc_min = 0.
rt_list_geom:
    ld a,52
    call rt_tpl_word
    ld (rt_c2_track),hl
    ld hl,0
    ld (rt_sc_min),hl
    ld (rt_sc_span),hl
    ld hl,(rt_sc_max)
    ld a,h
    or l
    jp nz,rt_list_geom_size
    ld hl,(rt_c2_track)
    ld (rt_c2_hsize),hl
    ret
rt_list_geom_size:
    ld hl,(rt_c2_track)
    ld de,(rt_c2_vis)
    call rt_mul16
    ld de,(rt_c2_n)
    call rt_udiv
    ld de,8
    push hl
    or a
    sbc hl,de
    pop hl
    jp nc,rt_list_geom_big
    ld hl,8
rt_list_geom_big:
    ld (rt_c2_hsize),hl
    ex de,hl
    ld hl,(rt_c2_track)
    or a
    sbc hl,de
    ld (rt_sc_span),hl
    ret

; rt_sync_out_list — mode 0: from row 0, the selection made visible. Mode 1
; (after a handler): the list is always rebuilt (the array may have
; changed), keeping the live first row, which moves only if the handler
; changed the selection.
rt_sync_out_list:
    ld a,44
    call rt_count_get
    call rt_sel_get
    ld hl,0
    ld (rt_c2_first),hl
    ld a,(rt_bind_mode)
    or a
    jp z,rt_sync_out_list2
    ld a,14
    call rt_live_word
    ld (rt_c2_first),hl
    ld a,18
    call rt_live_word
    push hl
    call rt_sel_word
    pop de
    or a
    sbc hl,de
    jp nz,rt_sync_out_list2
    call rt_list_limits
    ld hl,(rt_sc_max)
    ld de,(rt_c2_first)
    or a
    sbc hl,de
    jp nc,rt_sync_out_list3
    ld hl,(rt_sc_max)
    ld (rt_c2_first),hl
rt_sync_out_list3:
    call rt_list_show_at
    jp rt_sync_out_next
rt_sync_out_list2:
    call rt_list_show
    jp rt_sync_out_next

rt_sync_in_list:
    ld a,44
    call rt_count_get
    ld a,18
    call rt_live_sel
    ld hl,(rt_c2_sel)
    ex de,hl
    ld hl,(rt_bind_var)
    ld (hl),e
    inc hl
    ld (hl),d
    jp rt_sync_in_next

; rt_ctl_ev_list — an event on the list: Rosanne has recorded the
; selection; the scroll bar is redrawn from the live first row, then
; ACTION (double-click, when given) or CHANGE is run. A click or
; double-click on its scroll bar: the first row is stepped by the shared
; rule (page = rows shown), the list rebuilt and redrawn, queued input
; flushed.
rt_ctl_ev_list:
    ld a,(rt_gui_object)
    ld hl,rt_bind_obj
    cp (hl)
    jp z,rt_ctl_ev_lpick
    ld a,51
    call rt_tpl_byte
    ld hl,rt_gui_object
    cp (hl)
    jp nz,rt_ctl_ev_next
    ld a,(rt_gui_evtype)
    cp 1
    jp z,rt_ctl_ev_lscroll
    cp 2
    jp nz,rt_ctl_ev_next
rt_ctl_ev_lscroll:
    ld a,44
    call rt_count_get
    ld a,18
    call rt_live_sel
    ld a,14
    call rt_live_word
    ld (rt_sc_val),hl
    ld (rt_c2_first),hl
    call rt_list_limits
    call rt_list_geom
    ld hl,(rt_c2_vis)
    ld (rt_sc_page),hl
    call rt_scroll_step
    ld de,(rt_c2_first)
    ld (rt_c2_first),hl
    or a
    sbc hl,de
    jp z,rt_ctl_ev_lflush
    ld a,1
    ld (rt_bind_mode),a
    call rt_list_show_at
rt_ctl_ev_lflush:
    call rt_flush_after
    jp rt_ctl_ev_next
; A pick: Rosanne records the selection (XAnne U2) but was not seen to
; highlight it, so the list is rebuilt from the live first row and selection
; and displayed again, with its scroll bar.
rt_ctl_ev_lpick:
    ld a,44
    call rt_count_get
    ld a,18
    call rt_live_sel
    ld a,14
    call rt_live_word
    ld (rt_c2_first),hl
    ld a,1
    ld (rt_bind_mode),a
    call rt_list_show_at
    ld a,(rt_gui_evtype)
    cp 2
    jp nz,rt_ctl_ev_lchange
    ld a,56
    call rt_tpl_word
    ld a,h
    or l
    jp nz,rt_ctl_ev_pend
rt_ctl_ev_lchange:
    ld a,54
    call rt_tpl_word
    jp rt_ctl_ev_pend
    ENDIF

    IF PB_CHOICE
; ----------------------------------------------------------------------------
; CHOICE (kind 7). Descriptor: +0 the 27-byte ob_dropbutton record (+24
; pointer table, +26 bank patched here), +27 the readout label's 12-byte
; record prefix, +39 count address, +41 array descriptor, +43 pointer table,
; +45 readout label object, +46 CHANGE handler. The runtime writes the
; readout itself (whether Rosanne does is UIPROBE2's question).
; ----------------------------------------------------------------------------
rt_choice_show:
    ld a,43
    call rt_tpl_word
    call rt_items_build
    ld hl,(rt_bind_tpl)
    ld de,rt_obj_buf
    ld bc,27
    ldir
    call 0CBh
    ld (rt_obj_buf+26),a
    ld hl,(rt_c2_n)
    ld (rt_obj_buf+18),hl
    ex de,hl
    ld hl,(rt_obj_buf+20)
    or a
    sbc hl,de
    jp c,rt_choice_vis
    ld (rt_obj_buf+20),de
rt_choice_vis:
    ld hl,(rt_obj_buf+20)
    ld a,h
    or l
    jp z,rt_choice_vis2
    ld de,13
    call rt_mul16
    inc hl
    inc hl
    ld (rt_obj_buf+16),hl
rt_choice_vis2:
    call rt_sel_word
    ld (rt_obj_buf+22),hl
    ld a,(rt_bind_obj)
    call rt_define_buf
; the readout: the chosen item's text (checked by rt_items_build) or empty
    ld hl,(rt_bind_tpl)
    ld de,27
    add hl,de
    ld de,rt_obj_buf
    ld bc,12
    ldir
    xor a
    ld (rt_obj_buf+12),a
    ld hl,(rt_c2_sel)
    ld a,h
    or l
    jp z,rt_choice_label
    dec hl
    ld de,(rt_c2_arr)
    inc de
    inc de
    ex de,hl
    ld c,(hl)
    inc hl
    ld b,(hl)
    inc hl
    ld a,(hl)
    inc hl
    ld h,(hl)
    ld l,a
    push hl
    ex de,hl
    ld d,b
    ld e,c
    call rt_mul16
    pop de
    add hl,de
    push hl
    ld hl,rt_obj_buf+12+24
    ld (rt_dst_end),hl
    pop hl
    ld de,rt_obj_buf+12
    ld bc,24
    call rt_str_copy
    xor a
    ld (de),a
rt_choice_label:
    ld a,(rt_bind_mode)
    or a
    jp z,rt_choice_label2
    ld a,45
    call rt_tpl_byte
    dec a
    call rt_update_obj
rt_choice_label2:
    ld a,45
    call rt_tpl_byte
    call rt_define_buf
    ld a,(rt_bind_mode)
    or a
    ret z
    ld a,(rt_bind_obj)
    jp rt_update_obj

; Safety (owner XAnne, UIPROBE3 F): a drop button defined with current #FFFF
; ("none") showed an empty readout, and opening it then froze XAnne. So a
; CHOICE must always show one of its items: Sel = 0 (also the only value
; when Count = 0) stops the program, before Rosanne is given the record.
rt_sync_out_choice:
    ld a,39
    call rt_count_get
    ld a,h
    or l
    jp z,rt_choice_none
    call rt_sel_get
    ld hl,(rt_c2_sel)
    ld a,h
    or l
    jp z,rt_choice_none
    call rt_choice_show
    jp rt_sync_out_next
rt_choice_none:
    ld hl,rt_err_choice_text
    ld bc,rt_err_choice_text_end-rt_err_choice_text
    jp rt_err_msg
rt_err_choice_text:
    db "Runtime error: a CHOICE must show an item from 1 to its count at line "
rt_err_choice_text_end:

rt_sync_in_choice:
    ld a,39
    call rt_count_get
    ld a,22
    call rt_live_sel
    ld hl,(rt_c2_sel)
    ex de,hl
    ld hl,(rt_bind_var)
    ld (hl),e
    inc hl
    ld (hl),d
    jp rt_sync_in_next

; rt_ctl_ev_choice — after the drop-down was used (a click on the button;
; Rosanne runs the drop list and records the choice): rewrite the readout
; from the live choice, then CHANGE.
rt_ctl_ev_choice:
    ld a,(rt_gui_object)
    ld hl,rt_bind_obj
    cp (hl)
    jp nz,rt_ctl_ev_next
    ld a,(rt_gui_evtype)
    cp 1
    jp nz,rt_ctl_ev_next
    ld a,39
    call rt_count_get
    ld a,22
    call rt_live_sel
    ld a,1
    ld (rt_bind_mode),a
    call rt_choice_show
    ld a,46
    call rt_tpl_word
    jp rt_ctl_ev_pend
    ENDIF

    IF PB_SLIDER
; ----------------------------------------------------------------------------
; SLIDER (kind 8). Descriptor: +0 the 14-byte ob_hscroll record, +14 MIN,
; +16 MAX, +18 page step, +20 handle travel, +22 CHANGE handler, +24 value
; slot index. The value lives in rt_sl_value (Rosanne does not record
; scroll bars); the handle is drawn from it.
; ----------------------------------------------------------------------------
rt_slider_slot:
    ld a,24
    call rt_tpl_byte
    add a,a
    ld e,a
    ld d,0
    ld hl,rt_sl_value
    add hl,de
    ret

rt_slider_limits:
    ld a,14
    call rt_tpl_word
    ld (rt_sc_min),hl
    ld a,16
    call rt_tpl_word
    ld (rt_sc_max),hl
    ld a,18
    call rt_tpl_word
    ld (rt_sc_page),hl
    ld a,20
    call rt_tpl_word
    ld (rt_sc_span),hl
    ret

; rt_slider_show — value HL into the slot and the handle; define (redraw in
; mode 1).
rt_slider_show:
    push hl
    call rt_slider_slot
    pop de
    ld (hl),e
    inc hl
    ld (hl),d
    push de
    call rt_slider_limits
    ld hl,(rt_bind_tpl)
    ld de,rt_obj_buf
    ld bc,14
    ldir
    pop hl
    call rt_scroll_pos
    ld (rt_obj_buf+10),hl
    ld a,(rt_bind_obj)
    jp rt_define_buf

rt_sync_out_slider:
    ld hl,(rt_bind_var)
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld (rt_sc_val),de
    call rt_slider_limits
    ld de,(rt_sc_val)
    ld hl,(rt_sc_min)
    call rt_compare_signed
    or a
    jp z,rt_slider_range
    ld de,(rt_sc_val)
    ld hl,(rt_sc_max)
    call rt_compare_signed
    cp 2
    jp z,rt_slider_range
    ld a,(rt_bind_mode)
    or a
    jp z,rt_sync_out_slider2
    call rt_slider_slot
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld hl,(rt_sc_val)
    or a
    sbc hl,de
    jp z,rt_sync_out_next
rt_sync_out_slider2:
    ld hl,(rt_sc_val)
    call rt_slider_show
    jp rt_sync_out_next
rt_slider_range:
    ld hl,rt_err_slider_text
    ld bc,rt_err_slider_text_end-rt_err_slider_text
    jp rt_err_msg
rt_err_slider_text:
    db "Runtime error: number out of range at line "
rt_err_slider_text_end:

rt_sync_in_slider:
    call rt_slider_slot
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld hl,(rt_bind_var)
    ld (hl),e
    inc hl
    ld (hl),d
    jp rt_sync_in_next

rt_ctl_ev_slider:
    ld a,(rt_gui_object)
    ld hl,rt_bind_obj
    cp (hl)
    jp nz,rt_ctl_ev_next
    ld a,(rt_gui_evtype)
    cp 1
    jp z,rt_ctl_ev_slide
    cp 2
    jp nz,rt_ctl_ev_next
rt_ctl_ev_slide:
    call rt_slider_limits
    call rt_slider_slot
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld (rt_sc_val),de
    ld (rt_c2_word),de
    call rt_scroll_step
    ld de,(rt_c2_word)
    push hl
    or a
    sbc hl,de
    pop hl
    jp z,rt_ctl_ev_slflush
    ld a,1
    ld (rt_bind_mode),a
    call rt_slider_show
    call rt_flush_after
    ld a,22
    call rt_tpl_word
    jp rt_ctl_ev_pend
rt_ctl_ev_slflush:
    call rt_flush_after
    jp rt_ctl_ev_next
    ENDIF

; rt_ctl_ev_pend — remember handler HL (0 = none) to run when the event has
; been handled (rt_gui_loop, PB_CHANGE), then continue with the next row.
rt_ctl_ev_pend:
    IF PB_CHANGE
    ld a,h
    or l
    jp z,rt_ctl_ev_next
    ld (rt_ctl_pending),hl
    ENDIF
    jp rt_ctl_ev_next
    ENDIF

rt_ctl_failed:
    ld hl,rt_ctl_fail_alert
    ld de,rt_ctl_fail_alert_end-rt_ctl_fail_alert
    call rt_alert
    jp rt_exit

rt_ctl_fail_alert:
    db "Runtime error: a window control could not be updated",0,0,1
    dw 800Dh,80FBh,0,0
    db 79,75,0
rt_ctl_fail_alert_end:
    ENDIF
    ENDIF


; ============================================================================
; 16-bit arithmetic
; ============================================================================

; ----------------------------------------------------------------------------
; rt_mul16 — 16-bit multiply, low word (INTEGER `*`).
;
; Unsigned shift-add is correct for two's-complement operands modulo 2^16:
; every step is an addition or shift taken mod 65536, and the low 16 bits
; of a signed product equal those of the unsigned product of the same bit
; patterns — so no sign handling is needed. Port of the POC-proven
; pb_mul16 algorithm (POC/pbas/codegen.py:150-159).
;
; in:  HL = multiplicand, DE = multiplier
; out: HL = (HL * DE) mod 65536
; clobbers: AF, BC, DE (DE is shifted out to 0)
; ----------------------------------------------------------------------------
rt_mul16:
    ld bc,0
    ld a,16
rt_mul16_loop:
    bit 0,l
    jp z,rt_mul16_skip_add
    push hl
    ld h,b
    ld l,c
    add hl,de
    ld b,h
    ld c,l
    pop hl
rt_mul16_skip_add:
    sla e
    rl d
    srl h
    rr l
    dec a
    jp nz,rt_mul16_loop
    ld h,b
    ld l,c
    ret

; ----------------------------------------------------------------------------
; rt_compare_signed — signed 16-bit comparison (IF/WHILE/FOR conditions).
;
; Port of the POC-proven pb_compare_signed algorithm
; (POC/pbas/codegen.py:160-170): XOR of the sign bytes selects same- vs
; different-sign handling; same-sign operands are compared by exact
; two's-complement subtraction (signs equal means the borrow is truthful).
;
; in:  DE = left operand, HL = right operand
; out: A = 0 if DE < HL; A = 1 if DE = HL; A = 2 if DE > HL
; clobbers: AF, HL; DE and HL are exchanged on the subtraction path, so
; callers must treat DE as clobbered too
; ----------------------------------------------------------------------------
rt_compare_signed:
    ld a,d
    xor h
    jp p,rt_compare_same_sign
    bit 7,d
    jp nz,rt_compare_less
    ld a,2
    ret
rt_compare_same_sign:
    ex de,hl
    or a
    sbc hl,de
    jp z,rt_compare_equal
    jp c,rt_compare_less
    ld a,2
    ret
rt_compare_less:
    xor a
    ret
rt_compare_equal:
    ld a,1
    ret


; ============================================================================
; Decimal conversion
; ============================================================================

; ----------------------------------------------------------------------------
; rt_append_int — append decimal text of a signed 16-bit value to a buffer
; (STR$, dynamic MESSAGE, FILESAVE lengths). No terminator is written.
;
; Worst case is "-32768", 6 bytes. Port of the POC-proven pb_append_int
; digit algorithm (POC/NOTES.asm:386-516): the sign is emitted first, the
; value is negated in 16 bits, and each digit position is produced by
; counting unsigned subtractions of 10000/1000/100/10/1 with the borrow
; restored afterwards — unsigned digit subtraction after the 16-bit negate
; is what makes -32768 (whose magnitude is not representable as positive
; signed 16-bit) format correctly. Leading zeros are suppressed via the
; "seen" flag in rt_int_scratch; the units digit is always written.
;
; Every byte goes through rt_put, so a destination too small for the digits
; raises the string-overflow runtime error instead of being overrun.
;
; in:  HL = signed 16-bit value
;      DE = destination write position (rt_dst_end set by the caller)
; out: DE advanced past the last digit written
; clobbers: AF, BC, HL; workspace rt_int_scratch (2 bytes)
; ----------------------------------------------------------------------------
rt_append_int:
    bit 7,h
    jp z,rt_ai_positive
    ld a,45
    call rt_put
    ld a,h
    cpl
    ld h,a
    ld a,l
    cpl
    ld l,a
    inc hl
rt_ai_positive:
    xor a
    ld (rt_int_scratch),a
    ld bc,10000
    ld a,0
rt_ai_digit_10000_loop:
    or a
    sbc hl,bc
    jp c,rt_ai_digit_10000_done
    inc a
    jp rt_ai_digit_10000_loop
rt_ai_digit_10000_done:
    add hl,bc
    ld (rt_int_scratch+1),a
    or a
    jp nz,rt_ai_digit_10000_write
    ld a,(rt_int_scratch)
    or a
    jp z,rt_ai_digit_10000_skip
rt_ai_digit_10000_write:
    ld a,1
    ld (rt_int_scratch),a
    ld a,(rt_int_scratch+1)
    add a,48
    call rt_put
rt_ai_digit_10000_skip:
    ld bc,1000
    ld a,0
rt_ai_digit_1000_loop:
    or a
    sbc hl,bc
    jp c,rt_ai_digit_1000_done
    inc a
    jp rt_ai_digit_1000_loop
rt_ai_digit_1000_done:
    add hl,bc
    ld (rt_int_scratch+1),a
    or a
    jp nz,rt_ai_digit_1000_write
    ld a,(rt_int_scratch)
    or a
    jp z,rt_ai_digit_1000_skip
rt_ai_digit_1000_write:
    ld a,1
    ld (rt_int_scratch),a
    ld a,(rt_int_scratch+1)
    add a,48
    call rt_put
rt_ai_digit_1000_skip:
    ld bc,100
    ld a,0
rt_ai_digit_100_loop:
    or a
    sbc hl,bc
    jp c,rt_ai_digit_100_done
    inc a
    jp rt_ai_digit_100_loop
rt_ai_digit_100_done:
    add hl,bc
    ld (rt_int_scratch+1),a
    or a
    jp nz,rt_ai_digit_100_write
    ld a,(rt_int_scratch)
    or a
    jp z,rt_ai_digit_100_skip
rt_ai_digit_100_write:
    ld a,1
    ld (rt_int_scratch),a
    ld a,(rt_int_scratch+1)
    add a,48
    call rt_put
rt_ai_digit_100_skip:
    ld bc,10
    ld a,0
rt_ai_digit_10_loop:
    or a
    sbc hl,bc
    jp c,rt_ai_digit_10_done
    inc a
    jp rt_ai_digit_10_loop
rt_ai_digit_10_done:
    add hl,bc
    ld (rt_int_scratch+1),a
    or a
    jp nz,rt_ai_digit_10_write
    ld a,(rt_int_scratch)
    or a
    jp z,rt_ai_digit_10_skip
rt_ai_digit_10_write:
    ld a,1
    ld (rt_int_scratch),a
    ld a,(rt_int_scratch+1)
    add a,48
    call rt_put
rt_ai_digit_10_skip:
    ld bc,1
    ld a,0
rt_ai_digit_1_loop:
    or a
    sbc hl,bc
    jp c,rt_ai_digit_1_done
    inc a
    jp rt_ai_digit_1_loop
rt_ai_digit_1_done:
    add hl,bc
    ld (rt_int_scratch+1),a
rt_ai_digit_1_write:
    ld a,1
    ld (rt_int_scratch),a
    ld a,(rt_int_scratch+1)
    add a,48
    call rt_put
    ret


; ============================================================================
; String routines (LANGUAGE-SPEC.md section 4, ARCHITECTURE.md D5:
; NUL-terminated, capacity passed explicitly; since M2.1 overflow is never
; truncated: rt_put raises the reported runtime error)
; ============================================================================

; ----------------------------------------------------------------------------
; rt_str_len — length of a NUL-terminated string.
;
; in:  HL = string pointer
; out: BC = length in bytes (NUL not counted)
; clobbers: AF, HL
; ----------------------------------------------------------------------------
rt_str_len:
    ld bc,0
rt_str_len_loop:
    ld a,(hl)
    or a
    ret z
    inc hl
    inc bc
    jp rt_str_len_loop

; ----------------------------------------------------------------------------
; rt_str_skip — advance HL across up to BC characters.
;
; Stops at the NUL: HL advances past min(skip count, string length). The
; canonical first step of MID$/RIGHT$ (1-based start positions are adjusted
; by the caller before entry).
;
; in:  HL = string pointer, BC = count of bytes to skip
; out: HL advanced; BC = number of bytes not skipped (0 unless the NUL was
;      reached first)
; clobbers: AF, BC
; ----------------------------------------------------------------------------
rt_str_skip:
    ld a,c
    or b
    ret z
    ld a,(hl)
    or a
    ret z
    inc hl
    dec bc
    jp rt_str_skip

; ----------------------------------------------------------------------------
; rt_put — the single guarded writer for string text (M2.1).
;
; Stores A at DE and advances DE, but only if DE < rt_dst_end: the byte at
; rt_dst_end is reserved for the destination's NUL terminator, which the
; caller writes at DE after building the text. If DE >= rt_dst_end nothing
; is written and control passes to rt_err_string_overflow (never returns).
;
; Invariant for callers: with DE <= rt_dst_end on entry to a string build,
; DE <= rt_dst_end holds after every rt_put, so the final `ld (de),a` NUL
; store is inside the destination.
;
; in:  A = byte, DE = write position, rt_dst_end = last destination byte
; out: DE advanced by 1
; preserves: A, BC, HL; clobbers: F
; ----------------------------------------------------------------------------
rt_put:
    push hl
    ld hl,(rt_dst_end)
    or a
    sbc hl,de
    jp z,rt_err_string_overflow
    jp c,rt_err_string_overflow
    pop hl
    ld (de),a
    inc de
    ret

; ----------------------------------------------------------------------------
; rt_str_copy — append NUL-terminated text through rt_put, no terminator.
;
; BC bounds how many source bytes are *read* (a substring count, or a
; source's capacity); the destination is protected by rt_put.
;
; in:  HL = source pointer, DE = destination write position,
;      BC = maximum bytes to copy
; out: DE, HL advanced past the bytes copied; fewer than BC bytes copied iff
;      the source NUL was reached
; clobbers: AF, BC
; ----------------------------------------------------------------------------
rt_str_copy:
    ld a,c
    or b
    ret z
    ld a,(hl)
    or a
    ret z
    call rt_put
    inc hl
    dec bc
    jp rt_str_copy

; ----------------------------------------------------------------------------
; rt_str_compare — lexicographic comparison of two NUL-terminated strings
; (STRING = and <> tests; ordering available for later milestones).
;
; Unsigned byte order throughout. A string that is an initial segment of a
; longer one compares less than that longer one (the NUL sorts below every
; text byte).
;
; in:  HL = first string, DE = second string
; out: A = 0 if first < second; A = 1 if equal; A = 2 if first > second
; clobbers: AF, BC, HL, DE (both pointers end at the first differing byte,
; or at their respective NULs when equal)
; ----------------------------------------------------------------------------
rt_str_compare:
    ld a,(de)
    ld b,a
    ld a,(hl)
    cp b
    jp nz,rt_str_compare_diff
    or a
    jp z,rt_str_compare_equal
    inc hl
    inc de
    jp rt_str_compare
rt_str_compare_diff:
    jp c,rt_str_compare_less
    ld a,2
    ret
rt_str_compare_less:
    xor a
    ret
rt_str_compare_equal:
    ld a,1
    ret


; ============================================================================
; Substrings with run-time arguments (M5a; LANGUAGE-SPEC.md section 3)
; ============================================================================
; Assembled only for programs that use LEFT$/MID$/RIGHT$ with a computed
; position or count (the generated header defines PB_SLICE 0/1); literal
; arguments keep the M2 code paths, so programs without such substrings are
; unchanged. A computed count below 0 or a computed MID$ start below 1 is
; the reported runtime error "Runtime error: substring position out of range
; at line N" (constant ones are compile errors). Counts beyond the string's
; length simply take what is there (as for literal counts).
    IF PB_SLICE

; ----------------------------------------------------------------------------
; rt_chk_count — accept a substring count >= 0.
; in:  HL = count (signed 16-bit)   out: HL unchanged   clobbers: F
; ----------------------------------------------------------------------------
rt_chk_count:
    bit 7,h
    jp nz,rt_err_substring
    ret

; ----------------------------------------------------------------------------
; rt_chk_start — accept a MID$ start >= 1 and return the bytes to skip.
; in:  HL = start (signed 16-bit)   out: HL = start - 1   clobbers: AF
; ----------------------------------------------------------------------------
rt_chk_start:
    bit 7,h
    jp nz,rt_err_substring
    ld a,h
    or l
    jp z,rt_err_substring
    dec hl
    ret

; ----------------------------------------------------------------------------
; rt_slice_mid — MID$: skip BC bytes of the source, then append up to
; (rt_slc_count) bytes through rt_put.
; in:  HL = source, BC = bytes to skip, DE = write position,
;      rt_slc_count = count, rt_dst_end = destination limit
; out: DE advanced; clobbers: AF, BC, HL
; ----------------------------------------------------------------------------
rt_slice_mid:
    call rt_str_skip
    ld bc,(rt_slc_count)
    jp rt_str_copy

; ----------------------------------------------------------------------------
; rt_slice_right — RIGHT$: append the last BC bytes of the source (all of
; it when shorter) through rt_put.
; in:  HL = source, BC = count, DE = write position, rt_dst_end
; out: DE advanced; clobbers: AF, BC, HL
; ----------------------------------------------------------------------------
rt_slice_right:
    push de
    push bc
    push hl
    call rt_str_len
    pop hl
    pop de
    push de
    push hl
    ld h,b
    ld l,c
    or a
    sbc hl,de
    jp nc,rt_slice_right_skip
    ld hl,0
rt_slice_right_skip:
    ld b,h
    ld c,l
    pop hl
    call rt_str_skip
    pop bc
    pop de
    jp rt_str_copy

; ----------------------------------------------------------------------------
; rt_err_substring — runtime error: a computed substring position or count
; is out of range (count < 0, MID$ start < 1). Same reporting path as
; rt_err_string_overflow: alert with the .pbas line, then rt_exit.
; ----------------------------------------------------------------------------
rt_err_substring:
    ld hl,rt_alert_buf+160
    ld (rt_dst_end),hl
    ld de,rt_alert_buf
    ld hl,rt_err_sub_text
    ld bc,rt_err_sub_text_end-rt_err_sub_text
    call rt_str_copy
    ld hl,(rt_err_line)
    call rt_append_int
    call rt_alert_dynamic
    jp rt_exit

rt_err_sub_text:
    db "Runtime error: substring position out of range at line "
rt_err_sub_text_end:

    ENDIF

; ============================================================================
; Numbers and text (M5b; LANGUAGE-SPEC.md sections 3 and 8)
; ============================================================================
; Each routine group is assembled only when a program uses it (PB_DIV,
; PB_VAL, PB_ASC, PB_CHR, PB_INSTR), so programs without M5b constructs are
; unchanged. New runtime errors (alert with the .pbas line, then rt_exit,
; the same path as the string-overflow error):
;   "Runtime error: division by zero at line N"            (/ and MOD)
;   "Runtime error: number out of range at line N"         (VAL)
;   "Runtime error: character code out of range at line N" (CHR$)

    IF PB_DIV

; ----------------------------------------------------------------------------
; rt_div16 / rt_mod16 — signed 16-bit integer division (M5b).
; Quotient truncates toward zero; the remainder has the sign of the dividend
; (dividend = quotient * divisor + remainder). -32768 / -1 wraps to -32768
; and -32768 MOD -1 is 0, consistent with + - * wrapping (spec section 2).
; in:  DE = dividend, HL = divisor
; out: HL = quotient (rt_div16) or remainder (rt_mod16)
; clobbers: AF, BC, DE
; ----------------------------------------------------------------------------
rt_div16:
    call rt_divmod
    ret
rt_mod16:
    call rt_divmod
    ex de,hl
    ret

; rt_divmod — in: DE = dividend, HL = divisor; out: HL = quotient,
; DE = remainder; division by zero is the runtime error. Unsigned
; shift-and-subtract on the magnitudes (-32768 is 8000h, still exact).
rt_divmod:
    ld a,h
    or l
    jp z,rt_err_div
    ld a,d
    xor h
    ld (rt_div_qsign),a
    ld a,d
    ld (rt_div_rsign),a
    bit 7,h
    call nz,rt_neg_hl
    ld b,h
    ld c,l
    ex de,hl
    bit 7,h
    call nz,rt_neg_hl
    ld de,0
    ld a,16
rt_divmod_loop:
    add hl,hl
    ex de,hl
    adc hl,hl
    or a
    sbc hl,bc
    jp nc,rt_divmod_fits
    add hl,bc
    ex de,hl
    jp rt_divmod_next
rt_divmod_fits:
    ex de,hl
    inc hl
rt_divmod_next:
    dec a
    jp nz,rt_divmod_loop
    ld a,(rt_div_qsign)
    bit 7,a
    call nz,rt_neg_hl
    ld a,(rt_div_rsign)
    bit 7,a
    ret z
    ex de,hl
    call rt_neg_hl
    ex de,hl
    ret

; rt_neg_hl — HL = -HL (two's complement). clobbers: AF
rt_neg_hl:
    ld a,h
    cpl
    ld h,a
    ld a,l
    cpl
    ld l,a
    inc hl
    ret

rt_err_div:
    ld hl,rt_err_div_text
    ld bc,rt_err_div_text_end-rt_err_div_text
    jp rt_err_msg
rt_err_div_text:
    db "Runtime error: division by zero at line "
rt_err_div_text_end:

    ENDIF

    IF PB_VAL

; ----------------------------------------------------------------------------
; rt_val — VAL(s$): the leading decimal number of a string (M5b).
; Leading spaces are skipped, then an optional + or -, then digits; the
; number ends at the first non-digit (VAL("12abc") = 12). No digits gives 0
; (VAL(""), VAL("abc"), VAL("-")). A value outside -32768..32767 is the
; runtime error "number out of range" — never wrapped.
; in:  HL = string; out: HL = value; clobbers: AF, BC, DE
; ----------------------------------------------------------------------------
rt_val:
    ld a,(hl)
    cp 32
    jp nz,rt_val_sign
    inc hl
    jp rt_val
rt_val_sign:
    ld b,0
    cp 45
    jp nz,rt_val_plus
    ld b,1
    inc hl
    jp rt_val_start
rt_val_plus:
    cp 43
    jp nz,rt_val_start
    inc hl
rt_val_start:
    ld a,b
    ld (rt_val_neg),a
    ex de,hl
    ld hl,0
rt_val_loop:
    ld a,(de)
    sub 48
    jp c,rt_val_done
    cp 10
    jp nc,rt_val_done
    push af
    push de
    ex de,hl
    ld hl,3276
    or a
    sbc hl,de
    jp c,rt_err_val
    ex de,hl
    add hl,hl
    ld d,h
    ld e,l
    add hl,hl
    add hl,hl
    add hl,de
    pop de
    pop af
    ld c,a
    ld b,0
    add hl,bc
    inc de
    jp rt_val_loop
rt_val_done:
    ld a,(rt_val_neg)
    or a
    jp nz,rt_val_negative
    bit 7,h
    jp nz,rt_err_val
    ret
rt_val_negative:
    push hl
    ld de,32769
    or a
    sbc hl,de
    pop hl
    jp nc,rt_err_val
    ld a,h
    cpl
    ld h,a
    ld a,l
    cpl
    ld l,a
    inc hl
    ret

rt_err_val:
    ld hl,rt_err_val_text
    ld bc,rt_err_val_text_end-rt_err_val_text
    jp rt_err_msg
rt_err_val_text:
    db "Runtime error: number out of range at line "
rt_err_val_text_end:

    ENDIF

    IF PB_ASC

; ----------------------------------------------------------------------------
; rt_asc — ASC(s$): code 1..255 of the first character, or -1 for "" (M5b;
; BBC BASIC's convention: no runtime error for an empty string).
; in:  HL = string; out: HL = code; clobbers: AF
; ----------------------------------------------------------------------------
rt_asc:
    ld a,(hl)
    ld l,a
    ld h,0
    or a
    ret nz
    ld hl,0FFFFh
    ret

    ENDIF

    IF PB_TEXTW

; ----------------------------------------------------------------------------
; rt_text_width — TEXTWIDTH(s$) (M11 corrective): the width in pixels of s$
; drawn by DRAW TEXT (font 7, style 0), from os_dialog_string_width (fn 82,
; ROSAN283 "THE DIALOG FONT SYSTEM": "in: CHL = 24-bit address of data ...
; (as for os_dialog_string, x/y irrelevant); out: C Error in
; font/alignment/style/mode, NC HL = pixel width of string; AF corrupt, all
; other regs preserved"). Characters are mapped as DRAW TEXT maps them
; (outside 32..223: '?'), so the width is the drawn width.
; The carry is not tested. In XAnne (M5d WIDTHDG) fn 82 returned carry set
; and A = #07 for every call, yet HL held 110 for ten W's and 172 for
; "Label tests: long, short, empty": exactly the advances in Rosanne 1.12's
; seventh dialog-font table [static: PCW045.SYS, block 1; the fn 82 handler
; (block 10 #B23C) passes the same parameter check as fn 81 before it
; measures]. docs/M11-CORRECTIVE.md §3. The parameter block is in the
; program's own block (C from bios_getmem1), as in WIDTHDG T1.
; in:  HL = string; out: HL = width; clobbers: AF, BC, DE
; ----------------------------------------------------------------------------
rt_text_width:
    ld de,rt_tw_buf+8
    ld b,127
rt_tw_copy:
    ld a,(hl)
    or a
    jp z,rt_tw_end
    cp 32
    jp c,rt_tw_odd
    cp 0E0h
    jp c,rt_tw_put
rt_tw_odd:
    ld a,'?'
rt_tw_put:
    ld (de),a
    inc hl
    inc de
    dec b
    jp nz,rt_tw_copy
rt_tw_end:
    xor a
    ld (de),a
    ld (rt_tw_buf+1),a          ; left-aligned
    ld (rt_tw_buf+2),a          ; style 0
    ld (rt_tw_buf+3),a          ; mode 0
    IF PB_DWFONT
    ld a,(rt_dw_font)           ; M15: the DRAW FONT
    ELSE
    ld a,7
    ENDIF
    ld (rt_tw_buf),a            ; font 7
    call 0CBh                   ; bios_getmem1: the block holding rt_tw_buf
    ld c,a
    ld hl,rt_tw_buf
    ld a,82
    call 003Bh                  ; os_dialog_string_width: HL = width
    ret

    ENDIF

    IF PB_CLOCK

; ----------------------------------------------------------------------------
; rt_seconds — SECONDS (M11 corrective): minutes * 60 + seconds of the
; PcW16 clock, 0..3599, from bios_gettime (BIOS #10, call #B0; ROSAN283
; BIOS table: "out: E = ticks 0..255, D = seconds 0..59, C = minutes 0..59,
; B = hours 0..23, F corrupt"). Used in XAnne by the owner's PCW16-Fonts
; capture programs, which read D, C and B the same way. The ticks byte is
; not used (it is not a 1/256 s counter there).
; out: HL; clobbers: AF, BC, DE
; ----------------------------------------------------------------------------
rt_seconds:
    IF PB_CKCAL
    call rt_ck_gettime          ; M13: the same read keeps CLOCKTICKS in step
    ELSE
    call 0B0h                   ; bios_gettime
    ENDIF
    ld l,c
    ld h,0
    add hl,hl
    add hl,hl                   ; 4 * minutes
    ld b,h
    ld c,l
    add hl,hl
    add hl,hl
    add hl,hl
    add hl,hl                   ; 64 * minutes
    or a
    sbc hl,bc                   ; 60 * minutes
    ld c,d
    ld b,0
    add hl,bc
    ret

    ENDIF

    IF PB_CLOCKTICKS
; ----------------------------------------------------------------------------
; rt_clockticks — CLOCKTICKS (M13 corrective, LANGUAGE-SPEC §5.15): the clock
; in sixteenths of a second within the minute, 0..959: seconds * 16 + the
; sixteenths since the seconds register last changed, from one bios_gettime
; (BIOS #10, call #B0: "E = ticks 0..255, D = seconds 0..59").
; [static: PCW045.SYS #0E53 reads port #F9 (the 1/256 s byte), then #FA
; (seconds), #FB, #FC, and reads #F9 again, starting over only if it went
; down; #0E92 is the date, #FD..#FF.] Nothing makes #F9 wrap when the
; seconds change, and in XAnne it does not (owner, M13 corrective retest:
; the clock probe saw two steps back and steps of 16-17/16 s in 2 seconds,
; and the timers stalled about once a second; docs/M13-RESPONSIVENESS.md
; models both). So the fraction is counted from the ticks byte's value when
; the seconds last changed (rt_ck_e0): its value at the first read after a
; change, when the read before it was within 1/16 s (the event loop's
; polling reads it every few hundred instructions). Reads further apart
; cannot be used: two reads just over a second apart, in consecutive
; seconds, have ticks bytes that look close. The closest such pair seen is
; kept (rt_ck_q), so the polling's pairs replace any unlucky one. Until the
; first pair it is the ticks byte itself (right where #F9 wraps with the
; seconds). The fraction never goes back within a second, so CLOCKTICKS
; only goes back at the minute. SECONDS reads the clock through the same routine
; (rt_ck_gettime), so a program waiting for the seconds to change also keeps
; the fraction in step.
; out: HL; clobbers: AF, BC, DE
; ----------------------------------------------------------------------------
rt_clockticks:
    IF PB_CKCAL
    call rt_ck_gettime
    ELSE
    call 0B0h                   ; bios_gettime (legacy_timing: the ticks byte \ 16)
    ld a,e
    rrca
    rrca
    rrca
    rrca
    and 0Fh
    ENDIF
    ld l,d
    ld h,0
    add hl,hl
    add hl,hl
    add hl,hl
    add hl,hl                   ; 16 * seconds
    ld c,a
    ld b,0
    add hl,bc
    ret

    IF PB_CKCAL
; rt_ck_gettime — bios_gettime (B hours, C minutes, D seconds, E ticks byte)
; and A = the sixteenths since the seconds changed, 0..15. clobbers: F
rt_ck_gettime:
    call 0B0h                   ; bios_gettime
    push bc
    ld a,(rt_ck_d)
    cp d
    jr z,rt_ck_same
    inc a                       ; the seconds changed: by one, since a read
    cp 60                       ; within 1/16 s?
    jr c,rt_ck_next
    xor a
rt_ck_next:
    cp d
    jr nz,rt_ck_new
    ld a,(rt_ck_e)
    ld b,a
    ld a,e
    sub b                       ; 1/256 s between the two reads
    cp 16
    jr nc,rt_ck_new
    cpl
    ld b,a                      ; 255 - that
    ld a,(rt_ck_q)
    cp b
    jr z,rt_ck_take
    jr nc,rt_ck_new             ; a closer pair gave the change before
rt_ck_take:
    ld a,b
    ld (rt_ck_q),a
    ld a,e                      ; the change: at the first read after it
    ld (rt_ck_e0),a
rt_ck_new:
    ld a,d
    ld (rt_ck_d),a
    xor a
    ld (rt_ck_f),a
rt_ck_same:
    ld a,e
    ld (rt_ck_e),a
    ld a,(rt_ck_e0)
    ld b,a
    ld a,e
    sub b                       ; 1/256 s since the seconds changed
    rrca
    rrca
    rrca
    rrca
    and 0Fh
    ld b,a
    ld a,(rt_ck_f)
    and 0Fh
    cp b
    jr nc,rt_ck_keep            ; never back within a second
    ld a,b
rt_ck_keep:
    ld (rt_ck_f),a
    pop bc
    ret

    ENDIF
    ENDIF

    IF PB_KEYDOWN
; ----------------------------------------------------------------------------
; M13 KEYDOWN(code) (LANGUAGE-SPEC §5.15): whether a key is held down now.
; ROSAN283 bios_keystate #03 (#89): "get up/down status of a key; in: A =
; keyno; out: A = 0 / non-0 = key up / down; F corrupt". [static: PCW045.SYS
; #0D97: it maps block #84 at #8000 for one read of #8000 + keyno and puts
; the old block back; a keyno of 128 or more returns non-zero at once. The
; keyboard interrupt (block 6 #6A6B) writes that table by PS/2 scan code
; set 2: Caps Lock #58 toggles the LED, Shift is #12 / #59, Ctrl #14, Alt
; #11, the keypad #69..#7A.] So a code is 0..127, a set-2 scan code
; (lib/keys.pbas names them); the cursor keys share the keypad's codes.
; Resident: the BIOS maps #8000 away while it reads (code in the runtime
; bank must not call it).
; in: HL = code; out: HL = 1 down, 0 up
; ----------------------------------------------------------------------------
rt_keydown:
    ld a,h
    or a
    jp nz,rt_keydown_bad
    ld a,l
    cp 128
    jp nc,rt_keydown_bad
    call 089h                   ; bios_keystate
    or a
    ld hl,0
    ret z
    inc hl
    ret
rt_keydown_bad:
    ld hl,rt_keydown_text
    ld bc,rt_keydown_text_end-rt_keydown_text
    jp rt_err_msg
rt_keydown_text:
    db "Runtime error: a key code is 0 to 127 at line "
rt_keydown_text_end:

    ENDIF

    IF PB_CHR

; ----------------------------------------------------------------------------
; rt_chr_put — CHR$(n) appended through rt_put; n must be 1..255 (0 cannot
; be part of a STRING), else the runtime error.
; in:  HL = code, DE = write position, rt_dst_end; out: DE advanced
; clobbers: AF
; ----------------------------------------------------------------------------
rt_chr_put:
    ld a,h
    or a
    jp nz,rt_err_chr
    ld a,l
    or a
    jp z,rt_err_chr
    jp rt_put

rt_err_chr:
    ld hl,rt_err_chr_text
    ld bc,rt_err_chr_text_end-rt_err_chr_text
    jp rt_err_msg
rt_err_chr_text:
    db "Runtime error: character code out of range at line "
rt_err_chr_text_end:

    ENDIF

    IF PB_INSTR

; ----------------------------------------------------------------------------
; rt_instr — INSTR: 1-based position of the first occurrence of the needle
; in the haystack at or after start, or 0 (M5b). An empty needle is found at
; start when start <= LEN + 1; a start past LEN + 1 gives 0.
; in:  HL = haystack, DE = needle, BC = start - 1 (checked >= 0 by caller)
; out: HL = position or 0; clobbers: AF, BC, DE
; ----------------------------------------------------------------------------
rt_instr:
    ex de,hl
    ld (rt_ins_ndl),hl
    ld h,b
    ld l,c
    ld (rt_ins_pos),hl
    ex de,hl
    call rt_str_skip
    ld a,b
    or c
    jp nz,rt_instr_none
rt_instr_try:
    push hl
    ld de,(rt_ins_ndl)
rt_instr_cmp:
    ld a,(de)
    or a
    jp z,rt_instr_found
    cp (hl)
    jp nz,rt_instr_next
    inc hl
    inc de
    jp rt_instr_cmp
rt_instr_next:
    pop hl
    ld a,(hl)
    or a
    jp z,rt_instr_none
    inc hl
    push hl
    ld hl,(rt_ins_pos)
    inc hl
    ld (rt_ins_pos),hl
    pop hl
    jp rt_instr_try
rt_instr_found:
    pop hl
    ld hl,(rt_ins_pos)
    inc hl
    ret
rt_instr_none:
    ld hl,0
    ret

    ENDIF

    IF PB_CASE

; ----------------------------------------------------------------------------
; rt_ucase / rt_lcase — UCASE$ / LCASE$ (M5c): change the case of the ASCII
; letters in [HL, DE) in place. The caller has just appended the argument's
; text there through rt_put, so every byte is inside the destination. Bytes
; outside 'a'..'z' (rt_ucase) or 'A'..'Z' (rt_lcase) are left alone,
; including Rosanne's codes 128..255. For a letter the two cases differ only
; in bit 5, so flipping it converts in either direction.
; in:  HL = first byte, DE = one past the last byte (DE >= HL)
; out: DE unchanged (the build position); clobbers: AF, BC, HL
; ----------------------------------------------------------------------------
rt_ucase:
    ld bc,617Ah                 ; B = 'a', C = 'z'
    jp rt_case_loop
rt_lcase:
    ld bc,415Ah                 ; B = 'A', C = 'Z'
rt_case_loop:
    ld a,l
    cp e
    jp nz,rt_case_byte
    ld a,h
    cp d
    ret z
rt_case_byte:
    ld a,(hl)
    cp b
    jp c,rt_case_next           ; below the first letter
    ld a,c
    cp (hl)
    jp c,rt_case_next           ; above the last letter
    ld a,(hl)
    xor 20h
    ld (hl),a
rt_case_next:
    inc hl
    jp rt_case_loop

    ENDIF

    IF PB_IMATH
; ----------------------------------------------------------------------------
; M7 integer helpers (LANGUAGE-SPEC §3): MIN, MAX, SHL, SHR, RND, RANDOMIZE.
; in: DE = first argument, HL = second; out: HL. clobbers AF, BC, DE.
; ----------------------------------------------------------------------------
rt_imin:
    push hl
    push de
    call rt_compare_signed      ; A = 0 if DE < HL
    pop de
    pop hl
    or a
    ret nz
    ex de,hl
    ret
rt_imax:
    push hl
    push de
    call rt_compare_signed      ; A = 2 if DE > HL
    pop de
    pop hl
    cp 2
    ret nz
    ex de,hl
    ret

; rt_ishl / rt_ishr — DE shifted left / right (logically) by HL places;
; HL < 0 is "number out of range", HL >= 16 gives 0.
rt_ishl:
    call rt_shift_count
    ret z
rt_ishl_loop:
    add hl,hl
    djnz rt_ishl_loop
    ret
rt_ishr:
    call rt_shift_count
    ret z
rt_ishr_loop:
    srl h
    rr l
    djnz rt_ishr_loop
    ret
; rt_shift_count — in: DE = value, HL = count. out: HL = value, B = count,
; NZ; or Z with HL = value (count 0) / HL = 0 (count 16 or more).
rt_shift_count:
    bit 7,h
    jp nz,rt_imath_range
    ld a,h
    or a
    jp nz,rt_shift_zero
    ld a,l
    cp 16
    jp nc,rt_shift_zero
    ex de,hl
    ld b,a
    or a
    ret
rt_shift_zero:
    ld hl,0
    xor a
    ret

; rt_rnd — HL = a pseudo-random number 1..HL (HL >= 1, else "number out of
; range"). Generator: 16-bit xorshift x ^= x<<7, x ^= x>>9, x ^= x<<8 (period
; 65535, x never 0); the result is (x AND #7FFF) MOD n + 1.
rt_rnd:
    ld a,h
    or l
    jp z,rt_imath_range
    bit 7,h
    jp nz,rt_imath_range
    push hl
    ld hl,(rt_rnd_seed)
    ld a,h
    or l
    jp nz,rt_rnd_seeded
    inc hl                      ; never seeded: start from 1 (reproducible)
rt_rnd_seeded:
    ld d,h
    ld e,l
    ld b,7
rt_rnd_shl7:
    sla e
    rl d
    djnz rt_rnd_shl7
    ld a,h
    xor d
    ld h,a
    ld a,l
    xor e
    ld l,a
    ld a,h                      ; x ^= x >> 9: low byte ^= high byte >> 1
    srl a
    xor l
    ld l,a
    ld a,h                      ; x ^= x << 8: high byte ^= low byte
    xor l
    ld h,a
    ld (rt_rnd_seed),hl
    ld a,h
    and 7Fh
    ld d,a
    ld e,l
    pop hl
    call rt_mod16
    inc hl
    ret

; rt_randomize — seed = HL (0 becomes 1). rt_randomize_r: the seed mixed
; with the Z80 refresh register (RANDOMIZE without a seed; varying, weak).
rt_randomize_r:
    ld hl,(rt_rnd_seed)
    ld a,r
    xor l
    ld l,a
    ld a,r
    xor h
    ld h,a
rt_randomize:
    ld a,h
    or l
    jp nz,rt_randomize_set
    inc hl
rt_randomize_set:
    ld (rt_rnd_seed),hl
    ret
rt_imath_range:
    ld hl,rt_err_imath_text
    ld bc,rt_err_imath_text_end-rt_err_imath_text
    jp rt_err_msg
rt_err_imath_text:
    db "Runtime error: number out of range at line "
rt_err_imath_text_end:
    ENDIF

    IF PB_STRFN
; ----------------------------------------------------------------------------
; M7 string helpers. The caller has just appended text at [HL, DE) through
; rt_put; trimming only moves bytes left inside that range (ldir) and moves
; DE back, so nothing is written outside the destination.
; rt_ltrim / rt_rtrim / rt_trim — remove leading / trailing / both spaces
; (#20 only). in: HL = start, DE = end; out: DE = new end. clobbers AF, BC, HL.
; ----------------------------------------------------------------------------
rt_trim:
    push hl
    call rt_rtrim
    pop hl
rt_ltrim:
    push hl
rt_ltrim_scan:
    ld a,l
    cp e
    jp nz,rt_ltrim_byte
    ld a,h
    cp d
    jp nz,rt_ltrim_byte
    pop de                      ; all spaces: empty
    ret
rt_ltrim_byte:
    ld a,(hl)
    cp 20h
    jp nz,rt_ltrim_found
    inc hl
    jp rt_ltrim_scan
rt_ltrim_found:
    ex de,hl
    or a
    sbc hl,de                   ; HL = bytes kept
    ld b,h
    ld c,l
    ex de,hl                    ; HL = first kept byte
    pop de                      ; DE = start
    ldir
    ret
rt_rtrim:
    ld a,l
    cp e
    jp nz,rt_rtrim_byte
    ld a,h
    cp d
    ret z
rt_rtrim_byte:
    dec de
    ld a,(de)
    cp 20h
    jp z,rt_rtrim
    inc de
    ret

; rt_repeat — append HL copies of character BC (1..255) through rt_put.
; HL < 0: substring error; a code outside 1..255: character code error.
rt_repeat:
    bit 7,h
    jp nz,rt_err_substring
    ld a,b
    or a
    jp nz,rt_err_chr
    ld a,c
    or a
    jp z,rt_err_chr
rt_repeat_loop:
    ld a,h
    or l
    ret z
    ld a,c
    call rt_put
    dec hl
    jp rt_repeat_loop
    ENDIF

    IF PB_REAL
; ============================================================================
; M7 REAL arithmetic (LANGUAGE-SPEC §2, pbas/real.py): 5-byte floating point
; in the Locomotive BASIC layout — packed m0 m1 m2 m3|sign exponent (biased
; #80, 0 = zero), 32-bit mantissa with an implicit leading 1, fraction in
; [0.5, 1). Work is done in two unpacked accumulators FA (rt_fa) and FB
; (rt_fb): +0 sign (#00/#80), +1 exponent, +2 guard byte, +3..+6 mantissa
; m0..m3 (bit 7 of +6 set when normalised). Every operation leaves FA
; rounded to 32 bits (guard >= #80 rounds up: to nearest, ties away from
; zero) with guard 0. Binary operations compute FA = FB op FA. Overflow is
; "Runtime error: number out of range"; underflow gives 0. Nothing here
; calls the OS. Error reports use rt_err_line (set by the generated code).
; ============================================================================

; rt_fld — FA = the packed REAL at HL. rt_fldb — FB = it. rt_fld_to — the
; unpacked accumulator at DE = it. clobbers AF, BC, DE, HL.
rt_fld:
    ld de,rt_fa
    jp rt_fld_to
rt_fldb:
    ld de,rt_fb
rt_fld_to:
    push hl
    ld bc,4
    add hl,bc
    ld a,(hl)                   ; exponent
    pop hl
    ex de,hl                    ; HL = accumulator, DE = packed
    ld (hl),0                   ; sign, set below
    inc hl
    ld (hl),a
    inc hl
    ld (hl),0                   ; guard
    inc hl
    ex de,hl                    ; HL = packed, DE = accumulator+3
    ld bc,3
    ldir                        ; m0 m1 m2
    ld a,(hl)
    ld b,a
    ex de,hl                    ; HL = accumulator+6
    or 80h                      ; the implicit leading 1
    ld (hl),a
    ld a,b
    and 80h
    ld bc,-6
    add hl,bc
    ld (hl),a                   ; sign
    inc hl
    ld a,(hl)
    or a
    ret nz
    dec hl
    ld (hl),0                   ; zero has no sign
    ret

; rt_fst — store FA (rounded) packed at HL. clobbers AF, BC, DE, HL.
rt_fst:
    ex de,hl
    ld hl,rt_fa+3
    ld bc,3
    ldir
    ld a,(hl)
    and 7Fh
    ld b,a
    ld a,(rt_fa)
    or b
    ex de,hl
    ld (hl),a
    inc hl
    ld a,(rt_fa+1)
    ld (hl),a
    ret

; rt_fpush — push FA (6 bytes, packed) on the Z80 stack under the return
; address. rt_fpopb / rt_fpopa — pop such a value into FB / FA (DE kept).
rt_fpush:
    pop hl
    ld (rt_fret),hl
    ld hl,rt_fpk
    call rt_fst
    ld hl,(rt_fpk+4)
    push hl
    ld hl,(rt_fpk+2)
    push hl
    ld hl,(rt_fpk)
    push hl
    ld hl,(rt_fret)
    jp (hl)
rt_fpopb:
    ld (rt_fsave),de
    ld de,rt_fb
    jp rt_fpop_to
rt_fpopa:
    ld (rt_fsave),de
    ld de,rt_fa
rt_fpop_to:
    pop hl
    ld (rt_fret),hl
    pop hl
    ld (rt_fpk),hl
    pop hl
    ld (rt_fpk+2),hl
    pop hl
    ld (rt_fpk+4),hl
    ld hl,rt_fpk
    call rt_fld_to
    ld de,(rt_fsave)
    ld hl,(rt_fret)
    jp (hl)

; rt_fa2b — FB = FA. rt_fswap — exchange FA and FB.
rt_fa2b:
    ld hl,rt_fa
    ld de,rt_fb
    ld bc,8
    ldir
    ret
rt_fswap:
    ld hl,rt_fa
    ld de,rt_fb
    ld b,8
rt_fswap_loop:
    ld a,(de)
    ld c,(hl)
    ld (hl),a
    ex de,hl
    ld (hl),c
    ex de,hl
    inc hl
    inc de
    djnz rt_fswap_loop
    ret

; rt_fzero — FA = 0.
rt_fzero:
    xor a
    ld (rt_fa),a
    ld (rt_fa+1),a
    ret

; mantissa shifts of the 40 bits at +2..+6 (B is kept)
rt_fa_shr:
    ld hl,rt_fa+6
    jp rt_m_shr
rt_fb_shr:
    ld hl,rt_fb+6
rt_m_shr:
    srl (hl)
    dec hl
    rr (hl)
    dec hl
    rr (hl)
    dec hl
    rr (hl)
    dec hl
    rr (hl)
    ret
rt_fa_shl:
    ld hl,rt_fa+2
    sla (hl)
    inc hl
    rl (hl)
    inc hl
    rl (hl)
    inc hl
    rl (hl)
    inc hl
    rl (hl)
    ret

; rt_fnorm — normalise FA (mantissa top bit set), or make it 0.
rt_fnorm:
    ld hl,rt_fa+2
    ld a,(hl)
    inc hl
    or (hl)
    inc hl
    or (hl)
    inc hl
    or (hl)
    inc hl
    or (hl)
    jp z,rt_fzero
rt_fnorm_loop:
    ld a,(rt_fa+6)
    bit 7,a
    ret nz
    call rt_fa_shl
    ld hl,rt_fa+1
    dec (hl)
    jp nz,rt_fnorm_loop
    jp rt_fzero                 ; underflow

; rt_fround — round FA to 32 bits on its guard byte; guard = 0.
rt_fround:
    ld a,(rt_fa+1)
    or a
    ret z
    ld hl,rt_fa+2
    ld a,(hl)
    ld (hl),0
    rla                         ; carry = guard bit 7
    ret nc
    inc hl
    ld b,4
rt_fround_loop:
    inc (hl)
    ret nz                      ; no carry out of this byte
    inc hl
    djnz rt_fround_loop
    ; the mantissa wrapped to 0: it is 1.0 * 2^(e-128) = 0.5 * 2^(e+1-128)
    ld a,80h
    ld (rt_fa+6),a
rt_fexp_inc:
    ld hl,rt_fa+1
    inc (hl)
    ret nz
    jp rt_freal_range

; rt_fneg — FA = -FA.
rt_fneg:
    ld a,(rt_fa+1)
    or a
    ret z
    ld a,(rt_fa)
    xor 80h
    ld (rt_fa),a
    ret

; rt_fsub — FA = FB - FA. rt_fadd — FA = FB + FA.
rt_fsub:
    call rt_fneg
rt_fadd:
    ld a,(rt_fb+1)
    or a
    ret z                       ; FB = 0: FA
    ld a,(rt_fa+1)
    or a
    jp z,rt_fswap               ; FA = 0: FB
    ld b,a
    ld a,(rt_fb+1)
    cp b
    jp c,rt_fadd_ordered
    jp z,rt_fadd_ordered
    call rt_fswap               ; FA has the larger exponent
rt_fadd_ordered:
    ld a,(rt_fb+1)
    ld b,a
    ld a,(rt_fa+1)
    sub b
    cp 41
    ret nc                      ; FB is below the guard byte: FA
    or a
    jp z,rt_fadd_aligned
    ld b,a
    IF PB_RSTICKY
    ld c,0                      ; M14: a bit shifted out below the guard byte
    ENDIF
rt_fadd_shift:
    call rt_fb_shr
    IF PB_RSTICKY
    jp nc,rt_fadd_kept
    ld c,1
rt_fadd_kept:
    ENDIF
    djnz rt_fadd_shift
    IF PB_RSTICKY
    ld a,(rt_fb+2)              ; ... is kept as the guard's lowest bit, so
    or c                        ; that a result just under a half is never
    ld (rt_fb+2),a              ; rounded as a half (sticky rounding)
    ENDIF
rt_fadd_aligned:
    ld a,(rt_fb)
    ld b,a
    ld a,(rt_fa)
    xor b
    jp nz,rt_fadd_sub
    ld hl,rt_fa+2
    ld de,rt_fb+2
    ld b,5
    or a
rt_fadd_add:
    ld a,(de)
    adc a,(hl)
    ld (hl),a
    inc hl
    inc de
    djnz rt_fadd_add
    jp nc,rt_fround
    call rt_fa_shr
    ld hl,rt_fa+6
    set 7,(hl)
    call rt_fexp_inc
    jp rt_fround
rt_fadd_sub:
    ld hl,rt_fa+2
    ld de,rt_fb+2
    ld b,5
    or a
rt_fadd_sbc:
    ld a,(de)
    ld c,a
    ld a,(hl)
    sbc a,c
    ld (hl),a
    inc hl
    inc de
    djnz rt_fadd_sbc
    jp nc,rt_fadd_norm
    ld hl,rt_fa+2               ; FB was larger: negate, FB's sign
    ld b,5
    or a
rt_fadd_neg:
    ld a,0
    sbc a,(hl)
    ld (hl),a
    inc hl
    djnz rt_fadd_neg
    ld a,(rt_fb)
    ld (rt_fa),a
rt_fadd_norm:
    call rt_fnorm
    jp rt_fround

; rt_fsetexp — FA exponent from HL (a 16-bit biased exponent): 0 or less is
; underflow (0), above 255 overflow.
rt_fsetexp:
    bit 7,h
    jp nz,rt_fzero
    ld a,h
    or a
    jp nz,rt_freal_range
    ld a,l
    or a
    jp z,rt_fzero
    ld (rt_fa+1),a
    ret

; rt_fmul — FA = FB * FA.
rt_fmul:
    ld a,(rt_fa+1)
    or a
    ret z
    ld a,(rt_fb+1)
    or a
    jp z,rt_fzero
    ld a,(rt_fb)
    ld b,a
    ld a,(rt_fa)
    xor b
    ld (rt_fa),a
    ld a,(rt_fa+1)
    ld l,a
    ld h,0
    ld a,(rt_fb+1)
    ld e,a
    ld d,0
    add hl,de
    ld de,-128
    add hl,de
    ld (rt_fe),hl
    ld hl,rt_fprod              ; the 64-bit product = 0
    ld b,8
rt_fmul_clear:
    ld (hl),0
    inc hl
    djnz rt_fmul_clear
    ld a,32
    ld (rt_fcnt),a
rt_fmul_bit:
    ld hl,rt_fa+6               ; next multiplier bit (FA mantissa, LSB first)
    srl (hl)
    dec hl
    rr (hl)
    dec hl
    rr (hl)
    dec hl
    rr (hl)
    jp nc,rt_fmul_noadd
    ld hl,rt_fprod+4
    ld de,rt_fb+3
    ld b,4
    or a
rt_fmul_add:
    ld a,(de)
    adc a,(hl)
    ld (hl),a
    inc hl
    inc de
    djnz rt_fmul_add
    jp rt_fmul_shift
rt_fmul_noadd:
    or a
rt_fmul_shift:
    ld hl,rt_fprod+7
    ld b,8
rt_fmul_rr:
    rr (hl)
    dec hl
    djnz rt_fmul_rr
    ld hl,rt_fcnt
    dec (hl)
    jp nz,rt_fmul_bit
    ld a,(rt_fprod+7)
    bit 7,a
    jp nz,rt_fmul_top
    ld hl,rt_fprod              ; product in [1/4, 1/2): one place left
    ld b,8
    or a
rt_fmul_rl:
    rl (hl)
    inc hl
    djnz rt_fmul_rl
    ld hl,(rt_fe)
    dec hl
    ld (rt_fe),hl
rt_fmul_top:
    ld hl,rt_fprod+3
    ld de,rt_fa+2
    ld bc,5
    ldir
    ld hl,(rt_fe)
    call rt_fsetexp
    jp rt_fround

; rt_fdiv — FA = FB / FA (FA = 0: "division by zero").
rt_fdiv:
    ld a,(rt_fa+1)
    or a
    jp z,rt_freal_div0
    ld a,(rt_fb+1)
    or a
    jp z,rt_fzero
    ld a,(rt_fb)
    ld b,a
    ld a,(rt_fa)
    xor b
    ld (rt_fa),a
    ld a,(rt_fb+1)
    ld l,a
    ld h,0
    ld a,(rt_fa+1)
    ld e,a
    ld d,0
    or a
    sbc hl,de
    ld de,128
    add hl,de
    ld (rt_fe),hl
    ; R (5 bytes) = FB mantissa, D (5 bytes) = FA mantissa, Q (5 bytes) = 0
    ld hl,rt_fb+3
    ld de,rt_frem
    ld bc,4
    ldir
    xor a
    ld (rt_frem+4),a
    ld hl,rt_fa+3
    ld de,rt_fdv
    ld bc,4
    ldir
    ld (rt_fdv+4),a
    ld hl,rt_fq
    ld b,5
rt_fdiv_clear:
    ld (hl),0
    inc hl
    djnz rt_fdiv_clear
    call rt_fdiv_step           ; the integer bit: quotient >= 1 ?
    ld a,0
    rla
    ld (rt_fqtop),a
    ld a,40
    ld (rt_fcnt),a
rt_fdiv_loop:
    ld hl,rt_frem               ; R <<= 1
    ld b,5
    or a
rt_fdiv_rl:
    rl (hl)
    inc hl
    djnz rt_fdiv_rl
    call rt_fdiv_step
    ld hl,rt_fq                 ; Q = Q * 2 + the new bit
    ld b,5
rt_fdiv_ql:
    rl (hl)
    inc hl
    djnz rt_fdiv_ql
    ld hl,rt_fcnt
    dec (hl)
    jp nz,rt_fdiv_loop
    ld hl,rt_fq
    ld de,rt_fa+2
    ld bc,5
    ldir
    ld a,(rt_fqtop)
    or a
    jp z,rt_fdiv_done
    call rt_fa_shr              ; quotient in [1, 2): 1.Q / 2, exponent + 1
    ld hl,rt_fa+6
    set 7,(hl)
    ld hl,(rt_fe)
    inc hl
    ld (rt_fe),hl
rt_fdiv_done:
    ld hl,(rt_fe)
    call rt_fsetexp
    jp rt_fround
; rt_fdiv_step — if R >= D: R -= D, carry set; else R kept, carry clear.
rt_fdiv_step:
    ld hl,rt_frem
    ld de,rt_fdv
    ld b,5
    or a
rt_fdiv_sbc:
    ld a,(de)
    ld c,a
    ld a,(hl)
    sbc a,c
    ld (hl),a
    inc hl
    inc de
    djnz rt_fdiv_sbc
    jp c,rt_fdiv_restore
    scf
    ret
rt_fdiv_restore:
    ld hl,rt_frem
    ld de,rt_fdv
    ld b,5
    or a
rt_fdiv_adc:
    ld a,(de)
    adc a,(hl)
    ld (hl),a
    inc hl
    inc de
    djnz rt_fdiv_adc
    or a
    ret

; rt_fcmp — A = 0 if FB < FA, 1 if equal, 2 if FB > FA.
rt_fcmp:
    ld a,(rt_fb)
    ld b,a
    ld a,(rt_fa)
    cp b
    jp z,rt_fcmp_same
    ld a,b                      ; signs differ: the negative one is smaller
    or a
    ld a,0
    ret nz
    ld a,2
    ret
rt_fcmp_same:
    call rt_fcmp_mag
    ld b,a
    ld a,(rt_fa)
    or a
    ld a,b
    ret z
    ld a,2                      ; both negative: reverse
    sub b
    ret
; rt_fcmp_mag — A = 0/1/2 comparing |FB| with |FA| (exponent, then mantissa).
rt_fcmp_mag:
    ld a,(rt_fa+1)
    ld b,a
    ld a,(rt_fb+1)
    cp b
    jp nz,rt_fcmp_ne
    or a
    ld a,1
    ret z                       ; both 0
    ld hl,rt_fb+6
    ld de,rt_fa+6
    ld b,4
rt_fcmp_byte:
    ld a,(de)
    ld c,a
    ld a,(hl)
    cp c
    jp nz,rt_fcmp_ne
    dec hl
    dec de
    djnz rt_fcmp_byte
    ld a,1
    ret
rt_fcmp_ne:
    ld a,0
    ret c
    ld a,2
    ret

; rt_fint — FA = the INTEGER in HL (exact).
rt_fint:
    ld a,h
    or l
    jp z,rt_fzero
    xor a
    bit 7,h
    jp z,rt_fint_pos
    ex de,hl
    ld hl,0
    or a
    sbc hl,de                   ; magnitude (-32768 gives 32768)
    ld a,80h
rt_fint_pos:
    ld (rt_fa),a
    ld a,h
    ld (rt_fa+6),a
    ld a,l
    ld (rt_fa+5),a
    xor a
    ld (rt_fa+4),a
    ld (rt_fa+3),a
    ld (rt_fa+2),a
    ld a,144
    ld (rt_fa+1),a
    jp rt_fnorm

; rt_fcint — HL = FA rounded to the nearest INTEGER (halves away from 0);
; outside -32768..32767 is "number out of range". FA is destroyed.
rt_fcint:
    ld hl,0
    ld a,(rt_fa+1)
    cp 128
    ret c                       ; |x| < 0.5 (or 0)
    cp 145
    jp nc,rt_freal_range        ; |x| >= 65536
    ld b,a
    ld a,159
    sub b                       ; shift so that the result * 2 remains
    jp z,rt_fcint_shifted
    ld b,a
rt_fcint_shift:
    call rt_fa_shr
    djnz rt_fcint_shift
rt_fcint_shifted:
    ld hl,(rt_fa+3)             ; value * 2 (+ the half bit)
    ld a,(rt_fa+5)
    ld de,1
    add hl,de
    adc a,0
    srl a                       ; (value*2 + 1) / 2: rounded, 17 bits
    rr h
    rr l
    or a
    jp nz,rt_freal_range
    ld a,(rt_fa)
    or a
    jp nz,rt_fcint_neg
    bit 7,h
    jp nz,rt_freal_range
    ret
rt_fcint_neg:
    ld a,h
    cp 80h
    jp c,rt_fcint_negate
    jp nz,rt_freal_range
    ld a,l
    or a
    jp nz,rt_freal_range        ; above 32768
rt_fcint_negate:
    ex de,hl
    ld hl,0
    or a
    sbc hl,de
    ret

; rt_ffix — FA = FA truncated toward 0; rt_ffrac = #FF if bits were cut.
; rt_ffloor — FA = the largest whole number not above FA (INT).
rt_ffix:
    xor a
    ld (rt_ffrac),a
    ld a,(rt_fa+1)
    or a
    ret z
    cp 129
    jp nc,rt_ffix_big
    ld a,0FFh                   ; |x| < 1: 0
    ld (rt_ffrac),a
    jp rt_fzero
rt_ffix_big:
    cp 160
    ret nc                      ; already whole
    ld b,a
    ld a,160
    sub b                       ; bits to clear: 1..31
    ld hl,rt_fa+3
rt_ffix_byte:
    cp 8
    jp c,rt_ffix_bits
    ld b,a
    ld a,(hl)
    or a
    jp z,rt_ffix_clear
    ld a,0FFh
    ld (rt_ffrac),a
rt_ffix_clear:
    ld (hl),0
    inc hl
    ld a,b
    sub 8
    jp rt_ffix_byte
rt_ffix_bits:
    or a
    ret z
    ld b,a
    ld a,0FFh
rt_ffix_mask:
    add a,a                     ; the mask: ones above the cut
    djnz rt_ffix_mask
    ld b,a
    cpl
    and (hl)
    jp z,rt_ffix_masked
    ld a,0FFh
    ld (rt_ffrac),a
rt_ffix_masked:
    ld a,(hl)
    and b
    ld (hl),a
    ret
rt_ffloor:
    ld a,(rt_fa)                ; the sign, read first: FIX of |x| < 1 is +0
    push af
    call rt_ffix
    pop bc
    ld a,(rt_ffrac)
    or a
    ret z
    ld a,b
    or a
    ret z                       ; not negative: done
    call rt_fa2b                ; negative with a fraction: one less
    ld hl,rt_fone
    call rt_fld
    jp rt_fsub

; rt_fsgn — HL = -1, 0 or 1. rt_fabs — FA = |FA|.
rt_fsgn:
    ld hl,0
    ld a,(rt_fa+1)
    or a
    ret z
    ld a,(rt_fa)
    or a
    inc hl
    ret z
    dec hl
    dec hl
    ret
rt_fabs:
    xor a
    ld (rt_fa),a
    ret

; rt_fmin / rt_fmax — FA = the smaller / larger of FB and FA.
rt_fmin:
    call rt_fcmp
    or a
    ret nz                      ; FA <= FB: FA
    jp rt_fswap
rt_fmax:
    call rt_fcmp
    cp 2
    ret nz
    jp rt_fswap

rt_fone:
    db 0,0,0,0,129              ; 1.0

; ----------------------------------------------------------------------------
; REAL runtime errors (reported at rt_err_line)
; ----------------------------------------------------------------------------
rt_freal_range:
    ld hl,rt_err_frange_text
    ld bc,rt_err_frange_text_end-rt_err_frange_text
    jp rt_err_msg
rt_err_frange_text:
    db "Runtime error: number out of range at line "
rt_err_frange_text_end:
rt_freal_div0:
    ld hl,rt_err_fdiv_text
    ld bc,rt_err_fdiv_text_end-rt_err_fdiv_text
    jp rt_err_msg
rt_err_fdiv_text:
    db "Runtime error: division by zero at line "
rt_err_fdiv_text_end:
rt_freal_arg:
    ld hl,rt_err_farg_text
    ld bc,rt_err_farg_text_end-rt_err_farg_text
    jp rt_err_msg
rt_err_farg_text:
    db "Runtime error: function argument out of range at line "
rt_err_farg_text_end:
    ENDIF

    IF PB_REAL
; realconst.py begin (generated by tools/realconst.py; do not edit by hand)
rt_fc_half:
    db 0,0,0,0,128  ; 0.5
rt_fc_inv_ln2:
    db 41,59,170,56,129  ; 1 / ln 2
rt_fc_ln2_hi:
    db 0,20,114,49,128  ; ln 2, high 22 bits
rt_fc_ln2_lo:
    db 222,115,244,125,106  ; ln 2 - LN2_HI
rt_fc_exp_max:
    db 199,51,15,48,135  ; above: EXP overflows
rt_fc_exp_min:
    db 205,204,204,178,135  ; below: EXP underflows to 0
rt_fc_sqrt_half:
    db 52,243,4,53,128  ; sqrt(1/2)
rt_fc_two_pi:
    db 110,131,249,34,128  ; 2 / pi
rt_fc_pio2_hi:
    db 0,0,15,73,129  ; pi/2, high 16 bits
rt_fc_pio2_lo:
    db 105,33,162,90,113  ; pi/2 - PIO2_HI
rt_fc_trig_max:
    db 0,0,56,71,144  ; largest |x| for SIN/COS/TAN
rt_fc_pio2:
    db 162,218,15,73,129  ; pi/2
rt_fc_pio6:
    db 193,145,10,6,128  ; pi/6
rt_fc_sqrt3:
    db 67,215,179,93,129  ; sqrt 3
rt_fc_tan15:
    db 245,162,48,9,127  ; tan(pi/12)
rt_fc_exp_poly:  ; exp(r) = sum r^k / k!, k = 11..0 (Horner)
    db 12
    db 64,43,50,87,103
    db 188,125,242,19,107
    db 43,29,239,56,110
    db 208,0,13,80,113
    db 208,0,13,80,116
    db 182,96,11,54,119
    db 137,136,136,8,122
    db 171,170,170,42,124
    db 171,170,170,42,126
    db 0,0,0,0,128
    db 0,0,0,0,129
    db 0,0,0,0,129
rt_fc_log_poly:  ; ln m = 2z * sum w^k / (2k+1), w = z^2, k = 7..0
    db 8
    db 137,136,136,8,125
    db 158,216,137,29,125
    db 163,139,46,58,125
    db 228,56,142,99,125
    db 146,36,73,18,126
    db 205,204,204,76,126
    db 171,170,170,42,127
    db 0,0,0,0,129
rt_fc_sin_poly:  ; sin r = r * sum (-1)^k w^k / (2k+1)!, w = r^2, k = 6..0
    db 7
    db 157,48,146,48,96
    db 64,43,50,215,103
    db 43,29,239,56,110
    db 208,0,13,208,116
    db 137,136,136,8,122
    db 171,170,170,170,126
    db 0,0,0,0,129
rt_fc_cos_poly:  ; cos r = sum (-1)^k w^k / (2k)!, k = 7..0
    db 8
    db 70,165,203,201,92
    db 128,199,118,15,100
    db 188,125,242,147,107
    db 208,0,13,80,113
    db 182,96,11,182,119
    db 171,170,170,42,124
    db 0,0,0,128,128
    db 0,0,0,0,129
rt_fc_atn_poly:  ; atn a = a * sum (-1)^k w^k / (2k+1), k = 8..0
    db 9
    db 241,240,240,112,124
    db 137,136,136,136,125
    db 158,216,137,29,125
    db 163,139,46,186,125
    db 228,56,142,99,125
    db 146,36,73,146,126
    db 205,204,204,76,126
    db 171,170,170,170,127
    db 0,0,0,0,129
; realconst.py end

; ----------------------------------------------------------------------------
; REAL helpers on packed operands in memory (HL = a packed REAL):
; rt_fmulm FA *= [HL]; rt_faddm FA += [HL]; rt_fsubm FA -= [HL];
; rt_fdivm FA /= [HL].
; ----------------------------------------------------------------------------
rt_fmulm:
    call rt_fldb
    jp rt_fmul
rt_faddm:
    call rt_fldb
    jp rt_fadd
rt_fsubm:
    call rt_fldb
    call rt_fsub                ; FA = [HL] - FA
    jp rt_fneg
rt_fdivm:
    push hl
    call rt_fa2b
    pop hl
    call rt_fld
    jp rt_fdiv

; rt_fpoly — FA = the polynomial of table HL (count, then packed
; coefficients, highest degree first) at the value in rt_fw (Horner).
rt_fpoly:
    ld a,(hl)
    inc hl
    ld (rt_fpn),a
    ld (rt_fpp),hl
    call rt_fld
rt_fpoly_next:
    ld hl,rt_fpn
    dec (hl)
    ret z
    ld hl,rt_fw
    call rt_fmulm
    ld hl,(rt_fpp)
    ld de,5
    add hl,de
    ld (rt_fpp),hl
    call rt_faddm
    jp rt_fpoly_next

; rt_fhalve — FA = FA / 2 (FA <> 0; underflow gives 0).
rt_fhalve:
    ld a,(rt_fa+1)
    or a
    ret z
    dec a
    ld (rt_fa+1),a
    ret

; ----------------------------------------------------------------------------
; SQR: Newton's iteration g = (g + x/g) / 2 from g = x with its exponent
; halved (within a factor of 2), six times (error 2^-1 -> 2^-63).
; ----------------------------------------------------------------------------
rt_fsqr:
    ld a,(rt_fa+1)
    or a
    ret z
    ld a,(rt_fa)
    or a
    jp nz,rt_freal_arg          ; negative
    ld hl,rt_fx
    call rt_fst
    ld a,(rt_fa+1)
    sub 128
    sra a
    add a,128
    ld (rt_fa+1),a
    ld a,6
    ld (rt_fiter),a
rt_fsqr_step:
    ld hl,rt_fy
    call rt_fst                 ; g
    ld hl,rt_fx
    call rt_fldb
    call rt_fdiv                ; x / g
    ld hl,rt_fy
    call rt_faddm
    call rt_fhalve
    ld hl,rt_fiter
    dec (hl)
    jp nz,rt_fsqr_step
    ret

; ----------------------------------------------------------------------------
; EXP: n = CINT(x / ln 2), r = x - n*ln2 (Cody–Waite: high part exact),
; |r| <= 0.35, exp(r) by its series to r^11 (error < 1E-14), then 2^n.
; ----------------------------------------------------------------------------
rt_fexp:
    ld hl,rt_fx
    call rt_fst
    ld hl,rt_fc_exp_max
    call rt_fldb
    call rt_fcmp
    or a
    jp z,rt_freal_range         ; x > 88.03: overflow
    ld hl,rt_fc_exp_min
    call rt_fldb
    call rt_fcmp
    cp 2
    jp z,rt_fzero               ; x < -89.4: 0
    ld hl,rt_fc_inv_ln2
    call rt_fmulm
    call rt_fcint
    ld (rt_fk),hl
    ld hl,rt_fc_ln2_hi
    ld de,rt_fx
    call rt_freduce
    ld hl,rt_fw
    call rt_fst
    ld hl,rt_fc_exp_poly
    call rt_fpoly
    ld a,(rt_fa+1)
    ld e,a
    ld d,0
    ld hl,(rt_fk)
    add hl,de
    jp rt_fsetexp

; rt_freduce — FA = [DE] - k*[HL] - k*[HL+5] for k = rt_fk (the high and
; low parts of a constant). The result is also stored at rt_fz.
rt_freduce:
    ld (rt_frc),hl
    ld (rt_frx),de
    ld hl,(rt_fk)
    call rt_fint
    ld hl,(rt_frc)
    call rt_fmulm               ; k * high (exact)
    ld hl,(rt_frx)
    call rt_fldb
    call rt_fsub                ; x - k*high
    ld hl,rt_fz
    call rt_fst
    ld hl,(rt_fk)
    call rt_fint
    ld hl,(rt_frc)
    ld de,5
    add hl,de
    call rt_fmulm               ; k * low
    ld hl,rt_fz
    call rt_fldb
    call rt_fsub
    ld hl,rt_fz
    jp rt_fst_keep
; rt_fst_keep — store FA at HL and keep it in FA.
rt_fst_keep:
    jp rt_fst

; ----------------------------------------------------------------------------
; LOG (natural): x = m * 2^k, m in [sqrt(1/2), sqrt 2); z = (m-1)/(m+1),
; ln m = 2z(1 + z^2/3 + ... + z^14/15) (|z| <= 0.172, error < 1E-14);
; ln x = k*ln2_lo + ln m + k*ln2_hi.
; ----------------------------------------------------------------------------
rt_flog:
    ld a,(rt_fa+1)
    or a
    jp z,rt_freal_arg           ; LOG(0)
    ld a,(rt_fa)
    or a
    jp nz,rt_freal_arg          ; negative
    ld a,(rt_fa+1)
    sub 128
    ld l,a
    ld h,0
    bit 7,a
    jp z,rt_flog_k
    dec h
rt_flog_k:
    ld (rt_fk),hl
    ld a,128
    ld (rt_fa+1),a              ; m in [0.5, 1)
    ld hl,rt_fx
    call rt_fst
    ld hl,rt_fc_sqrt_half
    call rt_fldb
    call rt_fcmp
    cp 2
    jp nz,rt_flog_m
    ld a,129                    ; m < sqrt(1/2): 2m, k - 1
    ld (rt_fa+1),a
    ld hl,rt_fx
    call rt_fst
    ld hl,(rt_fk)
    dec hl
    ld (rt_fk),hl
rt_flog_m:
    ld hl,rt_fone
    call rt_fsubm               ; m - 1
    ld hl,rt_fy
    call rt_fst
    ld hl,rt_fx
    call rt_fld
    ld hl,rt_fone
    call rt_faddm               ; m + 1
    ld hl,rt_fy
    call rt_fldb
    call rt_fdiv                ; z
    ld hl,rt_fz
    call rt_fst
    ld hl,rt_fz
    call rt_fmulm               ; z^2
    ld hl,rt_fw
    call rt_fst
    ld hl,rt_fc_log_poly
    call rt_fpoly
    ld hl,rt_fz
    call rt_fmulm
    ld a,(rt_fa+1)              ; * 2
    or a
    jp z,rt_flog_mz
    call rt_fexp_inc
rt_flog_mz:
    ld hl,rt_fy
    call rt_fst                 ; ln m
    ld hl,(rt_fk)
    call rt_fint
    ld hl,rt_fc_ln2_lo
    call rt_fmulm
    ld hl,rt_fy
    call rt_faddm
    ld hl,rt_fy
    call rt_fst
    ld hl,(rt_fk)
    call rt_fint
    ld hl,rt_fc_ln2_hi
    call rt_fmulm
    ld hl,rt_fy
    jp rt_faddm

; ----------------------------------------------------------------------------
; SIN, COS, TAN: n = CINT(x * 2/pi) (|x| <= 51000, else "number out of
; range"), r = x - n*pi/2 (Cody–Waite), |r| <= pi/4; sin r and cos r by
; their series (to r^13 / r^14, error < 1E-13); the quadrant n MOD 4
; selects sin r, cos r, -sin r or -cos r.
; ----------------------------------------------------------------------------
rt_fsin:
    call rt_ftrig_reduce
    ld a,(rt_fk)
    jp rt_ftrig_q
rt_fcos:
    call rt_ftrig_reduce
    ld a,(rt_fk)
    inc a
    jp rt_ftrig_q
rt_ftan:
    call rt_ftrig_reduce
    ld a,(rt_fk)
    call rt_ftrig_q
    ld hl,rt_fp1
    call rt_fst                 ; sin x
    ld a,(rt_fk)
    inc a
    call rt_ftrig_q             ; cos x
    ld hl,rt_fp1
    call rt_fldb
    jp rt_fdiv

rt_ftrig_reduce:
    ld hl,rt_fx
    call rt_fst
    call rt_fabs
    ld hl,rt_fc_trig_max
    call rt_fldb
    call rt_fcmp
    or a
    jp z,rt_freal_range
    ld hl,rt_fx
    call rt_fld
    ld hl,rt_fc_two_pi
    call rt_fmulm
    call rt_fcint
    ld (rt_fk),hl
    ld hl,rt_fc_pio2_hi
    ld de,rt_fx
    call rt_freduce             ; r, also in rt_fz
    ld hl,rt_fz
    call rt_fmulm
    ld hl,rt_fw
    jp rt_fst                   ; w = r^2

; rt_ftrig_q — FA = sin r (A bit 0 = 0) or cos r (bit 0 = 1), negated if
; bit 1 of A is set; r in rt_fz, w = r^2 in rt_fw.
rt_ftrig_q:
    ld (rt_fquad),a
    and 1
    jp nz,rt_ftrig_cos
    ld hl,rt_fc_sin_poly
    call rt_fpoly
    ld hl,rt_fz
    call rt_fmulm
    jp rt_ftrig_sign
rt_ftrig_cos:
    ld hl,rt_fc_cos_poly
    call rt_fpoly
rt_ftrig_sign:
    ld a,(rt_fquad)
    and 2
    ret z
    jp rt_fneg

; ----------------------------------------------------------------------------
; ATN: a = |x|; a > 1: a = 1/a (result pi/2 - atn); a > tan(pi/12):
; a = (a*sqrt3 - 1)/(a + sqrt3) (result + pi/6); |a| <= 0.268, series to
; a^17 (error < 1E-12).
; ----------------------------------------------------------------------------
rt_fatn:
    ld a,(rt_fa)
    ld (rt_fsign),a
    call rt_fabs
    xor a
    ld (rt_fflag),a
    ld hl,rt_fone
    call rt_fldb
    call rt_fcmp
    or a
    jp nz,rt_fatn_le1           ; 1 >= a
    call rt_fdiv                ; 1 / a
    ld a,1
    ld (rt_fflag),a
rt_fatn_le1:
    ld hl,rt_fc_tan15
    call rt_fldb
    call rt_fcmp
    or a
    jp nz,rt_fatn_small
    ld hl,rt_fx
    call rt_fst                 ; a
    ld hl,rt_fc_sqrt3
    call rt_fmulm
    ld hl,rt_fone
    call rt_fsubm
    ld hl,rt_fy
    call rt_fst                 ; a*sqrt3 - 1
    ld hl,rt_fx
    call rt_fld
    ld hl,rt_fc_sqrt3
    call rt_faddm
    ld hl,rt_fy
    call rt_fldb
    call rt_fdiv
    ld a,(rt_fflag)
    or 2
    ld (rt_fflag),a
rt_fatn_small:
    ld hl,rt_fz
    call rt_fst
    ld hl,rt_fz
    call rt_fmulm
    ld hl,rt_fw
    call rt_fst
    ld hl,rt_fc_atn_poly
    call rt_fpoly
    ld hl,rt_fz
    call rt_fmulm
    ld a,(rt_fflag)
    and 2
    jp z,rt_fatn_noadd
    ld hl,rt_fc_pio6
    call rt_faddm
rt_fatn_noadd:
    ld a,(rt_fflag)
    and 1
    jp z,rt_fatn_sign
    ld hl,rt_fc_pio2
    call rt_fldb
    call rt_fsub                ; pi/2 - atn
rt_fatn_sign:
    ld a,(rt_fsign)
    or a
    ret z
    jp rt_fneg

; ----------------------------------------------------------------------------
; ^: FA = FB ^ FA. A whole exponent of at most 32767 in size is done by
; repeated squaring (any base; 0^0 = 1; a negative exponent divides, so
; 0^-n is "division by zero"); otherwise the base must be positive and the
; result is EXP(y * LOG(x)) (0^y = 0 for y > 0), else "function argument
; out of range".
; ----------------------------------------------------------------------------
rt_fpow:
    ld hl,rt_fp1
    call rt_fst                 ; y
    call rt_fswap
    ld hl,rt_fp2
    call rt_fst                 ; x
    ld hl,rt_fp1
    call rt_fld
    ld a,(rt_fa+1)
    cp 144
    jp nc,rt_fpow_real          ; |y| >= 32768
    call rt_ffix
    ld a,(rt_ffrac)
    or a
    jp nz,rt_fpow_real
    ld hl,rt_fp1
    call rt_fld
    call rt_fcint
    ld a,h
    ld (rt_fsign),a             ; the exponent's sign
    bit 7,h
    jp z,rt_fpow_pos
    ex de,hl
    ld hl,0
    or a
    sbc hl,de
rt_fpow_pos:
    ld (rt_fk),hl               ; |n|
    ld a,(rt_fsign)
    bit 7,a
    jp z,rt_fpow_start
    ld a,(rt_fp2+4)             ; n < 0: could x^|n| overflow on the way?
    sub 128                     ; |x| < 2^(e-128); only e > 128 can
    jp c,rt_fpow_start
    jp z,rt_fpow_start
    ld e,a
    ld d,0
    ld bc,127
    or a
    sbc hl,bc
    jp nc,rt_fpow_invert        ; |n| >= 127
    ld hl,(rt_fk)
    call rt_mul16               ; (e-128) * |n| <= 126 * 126
    ld bc,127
    or a
    sbc hl,bc
    jp c,rt_fpow_start          ; below 2^127: no overflow
rt_fpow_invert:
    ld hl,rt_fone               ; the result is below 2^-126: use (1/x)^|n|
    call rt_fldb
    ld hl,rt_fp2
    call rt_fld
    call rt_fdiv
    ld hl,rt_fp2
    call rt_fst
    xor a
    ld (rt_fsign),a
rt_fpow_start:
    ld hl,rt_fone
    call rt_fld
    ld hl,rt_fz
    call rt_fst                 ; result 1
    ld hl,rt_fp2
    call rt_fld
    ld hl,rt_fw
    call rt_fst                 ; base
rt_fpow_bit:
    ld hl,(rt_fk)
    ld a,h
    or l
    jp z,rt_fpow_done
    srl h
    rr l
    ld (rt_fk),hl
    jp nc,rt_fpow_square
    ld hl,rt_fz
    call rt_fld
    ld hl,rt_fw
    call rt_fmulm
    ld hl,rt_fz
    call rt_fst
rt_fpow_square:
    ld hl,(rt_fk)
    ld a,h
    or l
    jp z,rt_fpow_done
    ld hl,rt_fw
    call rt_fld
    ld hl,rt_fw
    call rt_fmulm
    ld hl,rt_fw
    call rt_fst
    jp rt_fpow_bit
rt_fpow_done:
    ld hl,rt_fz
    call rt_fld
    ld a,(rt_fsign)
    bit 7,a
    ret z
    ld a,(rt_fa+1)
    or a
    jp nz,rt_fpow_recip
    ld a,(rt_fp2+4)
    or a
    jp nz,rt_freal_range        ; x^|n| underflowed: 1 / it is too large
rt_fpow_recip:                  ; (x = 0: 1 / 0 is division by zero)
    ld hl,rt_fone
    call rt_fldb
    jp rt_fdiv                  ; 1 / result
rt_fpow_real:
    ld hl,rt_fp2
    call rt_fld
    ld a,(rt_fa+1)
    or a
    jp nz,rt_fpow_log
    ld hl,rt_fp1                ; 0 ^ y: 0 for y > 0
    call rt_fld
    ld a,(rt_fa)
    or a
    jp nz,rt_freal_arg
    jp rt_fzero
rt_fpow_log:
    ld a,(rt_fa)
    or a
    jp nz,rt_freal_arg          ; negative base, fractional exponent
    call rt_flog
    ld hl,rt_fp1
    call rt_fmulm
    jp rt_fexp

; ----------------------------------------------------------------------------
; STR$ of a REAL — rt_fstr appends the text of FA at DE (through rt_put):
; 9 significant digits (trailing zeros dropped); plain notation for
; 1E-4 <= |x| < 1E9 ("0.1", "123.456", "-2"), otherwise d.ddddE+nn.
; ----------------------------------------------------------------------------
rt_fstr:
    ld (rt_fsde),de
    ld a,(rt_fa+1)
    or a
    jp nz,rt_fstr_nonzero
    ld a,'0'
    jp rt_fput
rt_fstr_nonzero:
    ld a,(rt_fa)
    or a
    jp z,rt_fstr_pos
    ld a,'-'
    call rt_fput
    call rt_fabs
rt_fstr_pos:
    ld a,(rt_fa+1)              ; k ~ floor(log10 x) >= floor((e-129) * 77 / 256)
    sub 129
    ld l,a
    ld h,0
    bit 7,a
    jp z,rt_fstr_est
    dec h
rt_fstr_est:
    ld de,77
    call rt_mul16
    ld l,h
    ld h,0
    bit 7,l
    jp z,rt_fstr_try
    dec h
rt_fstr_try:
    ld (rt_fdexp),hl
    call rt_fstr_exact          ; N = x * 10^(8-k) rounded, exactly
    or a
    jp z,rt_fstr_n
    ld hl,(rt_fdexp)
    dec a
    jp nz,rt_fstr_less
    inc hl                      ; N >= 1E9: k was too small
    jp rt_fstr_try
rt_fstr_less:
    dec hl                      ; N < 1E8: k was too large
    jp rt_fstr_try

; rt_fstr_exact — rt_fn32 = N = round(x * 10^s), s = 8 - rt_fdexp, for the
; positive FA, rounded half away from zero, computed exactly in rt_fbig:
; x = m * 2^(e-160) (m = the 32-bit mantissa), so q = floor(2 x 10^s) =
; floor(m * 10^s * 2^(e-159)) and N = (q + 1) >> 1. Nested floor divisions
; equal one floor division, so the order below loses nothing.
; out: A = 0 (1E8 <= N < 1E9), 1 (N >= 1E9) or 2 (N < 1E8).
rt_fstr_exact:
    call rt_fbig_clear
    ld hl,rt_fa+3
    ld de,rt_fbig
    ld bc,4
    ldir
    ld hl,8
    ld de,(rt_fdexp)
    or a
    sbc hl,de
    ld (rt_fsn),hl              ; s
    bit 7,h
    jp nz,rt_fstr_x_shl
    ld a,l
    or a
    jp z,rt_fstr_x_shl
    ld b,a                      ; s <= 48 (k >= -40)
rt_fstr_x_mul:
    push bc
    call rt_fbig_mul10
    pop bc
    djnz rt_fstr_x_mul
rt_fstr_x_shl:
    ld a,(rt_fa+1)
    sub 159                     ; t = e - 159 (-158..96): shift left if t >= 0
    call nc,rt_fbig_shl
    ld hl,(rt_fsn)
    bit 7,h
    jp z,rt_fstr_x_shr
    ld a,l
    neg
    ld b,a                      ; -s <= 31 (k <= 38)
rt_fstr_x_div:
    push bc
    call rt_fbig_div10
    pop bc
    djnz rt_fstr_x_div
rt_fstr_x_shr:
    ld a,(rt_fa+1)
    ld b,a
    ld a,159
    sub b                       ; -t: shift right if t < 0
    jp c,rt_fstr_x_q
    call rt_fbig_shr
rt_fstr_x_q:
    ld hl,rt_fbig+4             ; q must be below 2^32
    ld b,BIGN-4
    xor a
rt_fstr_x_top:
    or (hl)
    inc hl
    djnz rt_fstr_x_top
    or a
    jp nz,rt_fstr_x_big
    ld hl,rt_fbig
    ld de,rt_fn32
    ld bc,4
    ldir
    ld hl,rt_fn32               ; q + 1
    ld b,4
rt_fstr_x_inc:
    inc (hl)
    jp nz,rt_fstr_x_half
    inc hl
    djnz rt_fstr_x_inc
    jp rt_fstr_x_big            ; q + 1 = 2^32
rt_fstr_x_half:
    ld hl,rt_fn32+3             ; >> 1
    srl (hl)
    dec hl
    rr (hl)
    dec hl
    rr (hl)
    dec hl
    rr (hl)
    ld hl,(rt_fn32+2)           ; N >= 1E9 (#3B9ACA00)?
    ld de,3B9Ah
    or a
    sbc hl,de
    jp c,rt_fstr_x_low
    jp nz,rt_fstr_x_big
    ld hl,(rt_fn32)
    ld de,0CA00h
    or a
    sbc hl,de
    jp nc,rt_fstr_x_big
rt_fstr_x_low:
    ld hl,(rt_fn32+2)           ; N < 1E8 (#05F5E100)?
    ld de,05F5h
    or a
    sbc hl,de
    jp c,rt_fstr_x_small
    jp nz,rt_fstr_x_ok
    ld hl,(rt_fn32)
    ld de,0E100h
    or a
    sbc hl,de
    jp c,rt_fstr_x_small
rt_fstr_x_ok:
    xor a
    ret
rt_fstr_x_big:
    ld a,1
    ret
rt_fstr_x_small:
    ld a,2
    ret

rt_fstr_n:
    ld b,9                      ; nine digits, last first
    ld hl,rt_fdig+8
rt_fstr_div:
    push hl
    push bc
    call rt_fdiv10
    pop bc
    pop hl
    ld (hl),a
    dec hl
    djnz rt_fstr_div
    ld a,9                      ; significant digits, trailing zeros off
    ld (rt_fnd),a
rt_fstr_trim:
    ld a,(rt_fnd)
    cp 1
    jp z,rt_fstr_form
    ld e,a
    ld d,0
    ld hl,rt_fdig-1
    add hl,de
    ld a,(hl)
    or a
    jp nz,rt_fstr_form
    ld hl,rt_fnd
    dec (hl)
    jp rt_fstr_trim
rt_fstr_form:
    ld hl,(rt_fdexp)
    ld de,-4
    call rt_compare_signed      ; A = 0 if -4 < k? (DE = -4, HL = k): DE < HL
    ld hl,(rt_fdexp)
    cp 2
    jp z,rt_fstr_sci            ; k < -4
    ld de,(rt_fdexp)
    ld hl,8
    call rt_compare_signed
    cp 2
    jp z,rt_fstr_sci            ; k > 8
    ld a,(rt_fdexp+1)
    bit 7,a
    jp nz,rt_fstr_small
    ; plain, k >= 0: digits 0..k (zeros past the significant ones), then
    ; a point and the rest
    ld a,(rt_fdexp)
    inc a
    ld (rt_fdi),a               ; integer digits
    xor a
    ld (rt_fdn),a
rt_fstr_int:
    ld a,(rt_fdn)
    ld hl,rt_fdi
    cp (hl)
    jp z,rt_fstr_frac
    call rt_fdigit
    ld hl,rt_fdn
    inc (hl)
    jp rt_fstr_int
rt_fstr_frac:
    ld a,(rt_fnd)
    ld hl,rt_fdn
    cp (hl)
    ret z
    ret c
    ld a,'.'
    call rt_fput
rt_fstr_frac_loop:
    ld a,(rt_fdn)
    ld hl,rt_fnd
    cp (hl)
    ret nc
    call rt_fdigit
    ld hl,rt_fdn
    inc (hl)
    jp rt_fstr_frac_loop
rt_fstr_small:
    ld a,'0'                    ; k < 0: "0." then -k-1 zeros, the digits
    call rt_fput
    ld a,'.'
    call rt_fput
    ld a,(rt_fdexp)
    neg
    dec a
    jp z,rt_fstr_small_d
    ld b,a
rt_fstr_zeros:
    push bc
    ld a,'0'
    call rt_fput
    pop bc
    djnz rt_fstr_zeros
rt_fstr_small_d:
    xor a
    ld (rt_fdn),a
    jp rt_fstr_frac_loop
rt_fstr_sci:
    xor a
    ld (rt_fdn),a
    call rt_fdigit
    ld a,1
    ld (rt_fdn),a
    ld a,(rt_fnd)
    cp 1
    jp z,rt_fstr_exp
    ld a,'.'
    call rt_fput
rt_fstr_sci_loop:
    ld a,(rt_fdn)
    ld hl,rt_fnd
    cp (hl)
    jp nc,rt_fstr_exp
    call rt_fdigit
    ld hl,rt_fdn
    inc (hl)
    jp rt_fstr_sci_loop
rt_fstr_exp:
    ld a,'E'
    call rt_fput
    ld a,(rt_fdexp)
    ld b,'+'
    bit 7,a
    jp z,rt_fstr_esign
    neg
    ld b,'-'
rt_fstr_esign:
    ld c,a
    ld a,b
    push bc
    call rt_fput
    pop bc
    ld a,c
    ld b,'0'-1
rt_fstr_tens:
    inc b
    sub 10
    jp nc,rt_fstr_tens
    add a,10+'0'
    ld c,a
    ld a,b
    push bc
    call rt_fput
    pop bc
    ld a,c
    jp rt_fput

; rt_fdigit — put digit rt_fdn of rt_fdig ('0' past the significant ones).
rt_fdigit:
    ld a,(rt_fdn)
    ld hl,rt_fnd
    cp (hl)
    ld a,'0'
    jp nc,rt_fput
    ld a,(rt_fdn)
    ld e,a
    ld d,0
    ld hl,rt_fdig
    add hl,de
    ld a,(hl)
    add a,'0'
; rt_fput — one character through rt_put at the saved position.
rt_fput:
    ld de,(rt_fsde)
    call rt_put
    ld (rt_fsde),de
    ret

; rt_fdiv10 — rt_fn32 = rt_fn32 / 10, A = the remainder.
rt_fdiv10:
    ld hl,rt_fn32+3
    ld b,4
    xor a                       ; the running remainder
rt_fdiv10_byte:
    push bc
    ld d,a
    ld e,(hl)                   ; DE = remainder * 256 + byte
    ld c,0                      ; quotient byte
    ex de,hl
rt_fdiv10_sub:
    ld a,h
    or a
    jp nz,rt_fdiv10_more
    ld a,l
    cp 10
    jp c,rt_fdiv10_done
rt_fdiv10_more:
    push de
    ld de,-10
    add hl,de
    pop de
    inc c
    jp rt_fdiv10_sub
rt_fdiv10_done:
    ex de,hl
    ld (hl),c
    ld a,e                      ; the remainder carries into the next byte
    dec hl
    pop bc
    djnz rt_fdiv10_byte
    ret

; ----------------------------------------------------------------------------
; REALVAL(s) — FA = the number at the start of s (like VAL: leading spaces,
; sign, digits with an optional point, an optional E[sign]digits; it stops
; at the first other character; no digits gives 0). Too large is "number
; out of range". ISNUM(s) — HL = 1 if the whole of s (spaces around it
; allowed) is such a number within range, else 0; never an error.
; At most 9 significant digits are used.
; ----------------------------------------------------------------------------
rt_fval:
    call rt_fparse
    ld a,(rt_fpbad)
    and 2
    jp nz,rt_freal_range
    jp rt_fparse_value
rt_fisnum:
    call rt_fparse
    ld hl,0
    ld a,(rt_fpbad)
    or a
    ret nz
    inc hl
    ret

; rt_fparse — read the text at HL. out: rt_fn32 = up to 9 significant digits,
; rt_fdexp = the power of 10 to apply, rt_fpsgn = sign, rt_fpbad bit 0 = not
; a complete number (ISNUM), bit 1 = out of range.
rt_fparse:
    xor a
    ld (rt_fpsgn),a
    ld (rt_fnd),a
    ld (rt_fdi),a               ; any digit seen
    ld (rt_fpbad),a
    ld (rt_fn32),a
    ld (rt_fn32+1),a
    ld (rt_fn32+2),a
    ld (rt_fn32+3),a
    ld (rt_fdexp),a
    ld (rt_fdexp+1),a
    call rt_fparse_spaces
    ld a,(hl)
    cp '-'
    jp nz,rt_fparse_plus
    ld a,80h
    ld (rt_fpsgn),a
    inc hl
    jp rt_fparse_int
rt_fparse_plus:
    cp '+'
    jp nz,rt_fparse_int
    inc hl
rt_fparse_int:
    ld a,(hl)
    sub '0'
    cp 10
    jp nc,rt_fparse_point
    call rt_fparse_digit
    jp nc,rt_fparse_int_next
    ld de,(rt_fdexp)            ; digit beyond the ninth: one more place
    inc de
    ld (rt_fdexp),de
rt_fparse_int_next:
    inc hl
    jp rt_fparse_int
rt_fparse_point:
    ld a,(hl)
    cp '.'
    jp nz,rt_fparse_exp
    inc hl
rt_fparse_frac:
    ld a,(hl)
    sub '0'
    cp 10
    jp nc,rt_fparse_exp
    call rt_fparse_digit
    jp c,rt_fparse_frac_next    ; beyond the ninth: ignored
    ld de,(rt_fdexp)
    dec de
    ld (rt_fdexp),de
rt_fparse_frac_next:
    inc hl
    jp rt_fparse_frac
rt_fparse_exp:
    ld a,(rt_fdi)
    or a
    jp z,rt_fparse_none
    ld a,(hl)
    and 0DFh
    cp 'E'
    jp nz,rt_fparse_end
    push hl
    inc hl
    ld a,(hl)
    ld c,0
    cp '+'
    jp z,rt_fparse_esign
    cp '-'
    jp nz,rt_fparse_edigits
    inc c
rt_fparse_esign:
    inc hl
rt_fparse_edigits:
    ld a,(hl)
    sub '0'
    cp 10
    jp c,rt_fparse_evalue
    pop hl                      ; "E" without digits: not part of the number
    jp rt_fparse_end
rt_fparse_evalue:
    pop de                      ; drop the saved position
    ld de,0
rt_fparse_eloop:
    ld a,(hl)
    sub '0'
    cp 10
    jp nc,rt_fparse_eend
    push hl
    ld h,d
    ld l,e
    add hl,hl
    add hl,hl
    add hl,de
    add hl,hl                   ; 10 * exponent
    ld e,a
    ld d,0
    add hl,de
    ex de,hl
    pop hl
    inc hl
    ld a,d                      ; keep it below 1000
    cp 3
    jp c,rt_fparse_eloop
    ld de,999
    jp rt_fparse_eloop
rt_fparse_eend:
    push hl
    ld a,c
    or a
    jp z,rt_fparse_eadd
    ld hl,0
    or a
    sbc hl,de
    ex de,hl
rt_fparse_eadd:
    ld hl,(rt_fdexp)
    add hl,de
    ld (rt_fdexp),hl
    pop hl
rt_fparse_end:
    call rt_fparse_spaces
    ld a,(hl)
    or a
    jp z,rt_fparse_range
    ld a,1
    ld (rt_fpbad),a
rt_fparse_range:
    ; out of range: the decimal exponent of the value, nd + dexp - 1, is
    ; above 38, or 38 with the nine-digit form above 170141183 (the largest
    ; REAL is 1.70141183E+38)
    ld a,(rt_fnd)
    or a
    ret z                       ; zero
    ld l,a
    ld h,0
    ld de,(rt_fdexp)
    add hl,de
    dec hl
    ld de,38
    ex de,hl
    call rt_compare_signed      ; DE = exponent, HL = 38
    or a
    ret z                       ; below 38
    cp 1
    jp nz,rt_fparse_over
    call rt_fparse_nine         ; exactly 38: compare the leading digits
    ld hl,(rt_fn32+2)
    ld de,0A24h
    or a
    sbc hl,de
    jp c,rt_fparse_nine_back
    jp nz,rt_fparse_over_back
    ld hl,(rt_fn32)
    ld de,25FFh
    or a
    sbc hl,de
    jp z,rt_fparse_nine_back
    jp nc,rt_fparse_over_back
rt_fparse_nine_back:
    jp rt_fparse_unnine
rt_fparse_over_back:
    call rt_fparse_unnine
rt_fparse_over:
    ld a,(rt_fpbad)
    or 2
    ld (rt_fpbad),a
    ret
rt_fparse_none:
    ld a,1                      ; no digit at all: 0, and not a number
    ld (rt_fpbad),a
    ret

; rt_fparse_digit — A = digit 0..9: N = N*10 + A unless 9 significant
; digits are held (then carry set). Leading zeros are not significant.
rt_fparse_digit:
    push hl
    ld b,a
    ld a,1
    ld (rt_fdi),a
    ld a,(rt_fnd)
    cp 9
    jp nc,rt_fparse_full
    or a
    jp nz,rt_fparse_take
    ld a,b
    or a
    jp z,rt_fparse_lead         ; a leading zero
rt_fparse_take:
    ld hl,rt_fnd
    inc (hl)
    push bc
    call rt_fn_times10
    pop bc
    ld hl,rt_fn32
    ld a,(hl)
    add a,b
    ld (hl),a
    ld b,3
rt_fparse_carry:
    inc hl
    ld a,(hl)
    adc a,0
    ld (hl),a
    djnz rt_fparse_carry
rt_fparse_lead:
    pop hl
    or a
    ret
rt_fparse_full:
    pop hl
    scf
    ret

; rt_fn_times10 — rt_fn32 = rt_fn32 * 10 (it stays below 10^9 here).
rt_fn_times10:
    call rt_fn_shl              ; * 2
    ld hl,(rt_fn32)
    ld (rt_fn2),hl
    ld hl,(rt_fn32+2)
    ld (rt_fn2+2),hl
    call rt_fn_shl
    call rt_fn_shl              ; * 8
    ld hl,rt_fn32               ; + 2N
    ld de,rt_fn2
    ld b,4
    or a
rt_fn_add:
    ld a,(de)
    adc a,(hl)
    ld (hl),a
    inc hl
    inc de
    djnz rt_fn_add
    ret
rt_fn_shl:
    ld hl,rt_fn32
    sla (hl)
    inc hl
    rl (hl)
    inc hl
    rl (hl)
    inc hl
    rl (hl)
    ret

; rt_fparse_nine / rt_fparse_unnine — scale N to nine digits (for the range
; check) and back (rt_fnd and rt_fdexp are restored).
rt_fparse_nine:
    ld a,(rt_fnd)
    ld (rt_fnd9),a
rt_fparse_nine_loop:
    ld a,(rt_fnd)
    cp 9
    ret nc
    call rt_fn_times10
    ld hl,rt_fnd
    inc (hl)
    jp rt_fparse_nine_loop
rt_fparse_unnine:
    ld a,(rt_fnd9)
    ld b,a
    ld a,(rt_fnd)
    sub b
    ret z
    ld b,a
rt_fparse_unnine_loop:
    push bc
    call rt_fdiv10
    pop bc
    djnz rt_fparse_unnine_loop
    ld a,(rt_fnd9)
    ld (rt_fnd),a
    ret

rt_fparse_spaces:
    ld a,(hl)
    cp 20h
    ret nz
    inc hl
    jp rt_fparse_spaces

; rt_fparse_value — FA = sign * N * 10^dexp (after rt_fparse).
rt_fparse_value:
    ; FA = N * 10^d, the REAL nearest to it (halves away from zero), with
    ; N = rt_fn32 (below 1E9) and d = rt_fdexp, computed exactly in rt_fbig:
    ; d >= 0: B = N * 10^d; d < 0: B = floor(N * 2^192 / 10^-d), which keeps
    ; at least 33 significant bits for -d <= 48 (smaller values underflow).
    ; Only the bit after the 32nd decides the rounding (ties go up).
    ld hl,(rt_fn32)
    ld a,h
    or l
    ld hl,(rt_fn32+2)
    or h
    or l
    jp z,rt_fzero
    call rt_fbig_clear
    ld hl,(rt_fdexp)
    bit 7,h
    jp nz,rt_fpv_neg
    ld (rt_fsn),hl              ; d <= 38 here (the range check)
    ld hl,rt_fn32
    ld de,rt_fbig
    ld bc,4
    ldir
    ld a,(rt_fsn)
    or a
    jp z,rt_fpv_scaled
    ld b,a
rt_fpv_mul:
    push bc
    call rt_fbig_mul10
    pop bc
    djnz rt_fpv_mul
    ld hl,0
    jp rt_fpv_scaled_at
rt_fpv_neg:
    ld de,-48
    call rt_compare_signed      ; DE = -48, HL = d: is d below -48?
    cp 2
    jp nz,rt_fpv_room
    jp rt_fzero
rt_fpv_room:
    ld hl,rt_fn32
    ld de,rt_fbig+24
    ld bc,4
    ldir
    ld hl,(rt_fdexp)
    ld a,l
    neg
    ld b,a
rt_fpv_div:
    push bc
    call rt_fbig_div10
    pop bc
    djnz rt_fpv_div
    ld hl,-192
    jp rt_fpv_scaled_at
rt_fpv_scaled:
    ld hl,0
rt_fpv_scaled_at:
    ld (rt_fsn),hl              ; the power of 2 applied to B
rt_fpv_bytes:
    ld a,(rt_fbig+BIGN-1)       ; top byte non-zero: B is never 0 here
    or a
    jp nz,rt_fpv_bits
    ld a,8
    call rt_fbig_shl
    ld hl,(rt_fsn)
    ld de,-8
    add hl,de
    ld (rt_fsn),hl
    jp rt_fpv_bytes
rt_fpv_bits:
    ld a,(rt_fbig+BIGN-1)
    bit 7,a
    jp nz,rt_fpv_round
    ld a,1
    call rt_fbig_shl
    ld hl,(rt_fsn)
    dec hl
    ld (rt_fsn),hl
    jp rt_fpv_bits
rt_fpv_round:
    ; B = M * 2^208 + rest, M = the top 32 bits: x = M/2^32 * 2^(240 + p),
    ; so the exponent byte is 368 + p (p = rt_fsn)
    ld hl,rt_fbig+BIGN-4
    ld de,rt_fa+3
    ld bc,4
    ldir
    ld hl,(rt_fsn)
    ld de,368
    add hl,de
    ld a,(rt_fbig+BIGN-5)
    bit 7,a
    jp z,rt_fpv_exp
    push hl
    ld hl,rt_fa+3
    ld b,4
rt_fpv_inc:
    inc (hl)
    jp nz,rt_fpv_incd
    inc hl
    djnz rt_fpv_inc
    ld a,80h                    ; carried out: M = 2^31, one more power
    ld (rt_fa+6),a
    pop hl
    inc hl
    jp rt_fpv_exp
rt_fpv_incd:
    pop hl
rt_fpv_exp:
    ld a,h
    or a
    jp nz,rt_fpv_range          ; above 255 (or negative: below 1)
    ld a,l
    or a
    jp z,rt_fzero               ; below the smallest REAL: 0
    ld (rt_fa+1),a
    xor a
    ld (rt_fa+2),a
    ld a,(rt_fpsgn)
    ld (rt_fa),a
    ret
rt_fpv_range:
    bit 7,h
    jp nz,rt_fzero
    jp rt_freal_range

; ----------------------------------------------------------------------------
; rt_fbig — a BIGN-byte unsigned integer, low byte first, for the exact
; decimal conversions of STR$ and REALVAL.
; ----------------------------------------------------------------------------
BIGN equ 30                     ; the size of rt_fbig (its defs below)
rt_fbig_clear:
    ld hl,rt_fbig
    ld b,BIGN
    xor a
rt_fbig_clear_next:
    ld (hl),a
    inc hl
    djnz rt_fbig_clear_next
    ret

; rt_fbig_mul10 — B = B * 10 (the result is known to fit).
rt_fbig_mul10:
    ld hl,rt_fbig
    ld b,BIGN
    ld c,0                      ; carry, 0..9
rt_fbig_mul10_next:
    ld a,(hl)
    push hl
    ld l,a
    ld h,0
    ld e,l
    ld d,h
    add hl,hl
    add hl,hl
    add hl,de
    add hl,hl                   ; byte * 10
    ld e,c
    ld d,0
    add hl,de
    ld c,h
    ld a,l
    pop hl
    ld (hl),a
    inc hl
    djnz rt_fbig_mul10_next
    ret

; rt_fbig_div10 — B = floor(B / 10), top byte first (remainder < 10 in C).
rt_fbig_div10:
    ld hl,rt_fbig+BIGN-1
    ld b,BIGN
    ld c,0
rt_fbig_div10_next:
    push bc
    push hl
    ld a,(hl)
    ld l,a
    ld h,c                      ; remainder * 256 + byte, remainder < 10
    ld b,8
rt_fbig_div10_bit:
    add hl,hl
    ld a,h
    sub 10
    jp c,rt_fbig_div10_skip
    ld h,a
    inc l                       ; a quotient bit
rt_fbig_div10_skip:
    djnz rt_fbig_div10_bit
    ld a,l
    ld e,h
    pop hl
    ld (hl),a
    pop bc
    ld c,e
    dec hl
    djnz rt_fbig_div10_next
    ret

; rt_fbig_shl / rt_fbig_shr — B shifted left / right by A places (A >= 0).
rt_fbig_shl:
    cp 8
    jp c,rt_fbig_shl_bits
    push af
    ld hl,rt_fbig+BIGN-2
    ld de,rt_fbig+BIGN-1
    ld bc,BIGN-1
    lddr
    ld hl,rt_fbig
    ld (hl),0
    pop af
    sub 8
    jp rt_fbig_shl
rt_fbig_shl_bits:
    or a
    ret z
rt_fbig_shl_bit:
    ld hl,rt_fbig
    ld b,BIGN
    or a
rt_fbig_shl_byte:
    rl (hl)
    inc hl
    djnz rt_fbig_shl_byte
    dec a
    jp nz,rt_fbig_shl_bit
    ret
rt_fbig_shr:
    cp 8
    jp c,rt_fbig_shr_bits
    push af
    ld hl,rt_fbig+1
    ld de,rt_fbig
    ld bc,BIGN-1
    ldir
    ld hl,rt_fbig+BIGN-1
    ld (hl),0
    pop af
    sub 8
    jp rt_fbig_shr
rt_fbig_shr_bits:
    or a
    ret z
rt_fbig_shr_bit:
    ld hl,rt_fbig+BIGN-1
    ld b,BIGN
    or a
rt_fbig_shr_byte:
    rr (hl)
    dec hl
    djnz rt_fbig_shr_byte
    dec a
    jp nz,rt_fbig_shr_bit
    ret
    ENDIF

    IF PB_ARRAYS
; ----------------------------------------------------------------------------
; rt_index — the address of an array element (M6 Phase 2, LANGUAGE-SPEC
; §5.2). Arrays are 1-based; an index below 1 or above the length stops the
; program with "Runtime error: index out of range at line N" (rt_err_line,
; set by the statement). The generated descriptor is three words: length,
; element size (2, or the STRING capacity), base address.
; in:  HL = index, DE = descriptor
; out: HL = element address
; clobbers: AF, BC, DE
; ----------------------------------------------------------------------------
rt_index:
    ld a,h
    or a
    jp m,rt_index_bad
    or l
    jp z,rt_index_bad
    ex de,hl
    ld c,(hl)
    inc hl
    ld b,(hl)
    inc hl
    ex de,hl
    push hl
    or a
    sbc hl,bc
    pop hl
    jp z,rt_index_ok
    jp nc,rt_index_bad
rt_index_ok:
    dec hl
    ex de,hl
    ld c,(hl)
    inc hl
    ld b,(hl)
    inc hl
    ld a,(hl)
    inc hl
    ld h,(hl)
    ld l,a
    push hl
    ex de,hl
    ld d,b
    ld e,c
    call rt_mul16
    pop de
    add hl,de
    ret
rt_index_bad:
    ld hl,rt_err_index_text
    ld bc,rt_err_index_text_end-rt_err_index_text
    jp rt_err_msg
rt_err_index_text:
    db "Runtime error: index out of range at line "
rt_err_index_text_end:
    ENDIF

    IF PB_TEXT
; ============================================================================
; M9 TEXT buffers (LANGUAGE-SPEC §5.7): a document of bytes kept exactly as
; in its file (CR, LF and every other byte), in 16K blocks the program owns.
; ============================================================================
; The blocks are slots of the M8 BANKED block list (rt_bank_init gets, checks
; and clears them; rt_bank_free gives them back). A buffer of capacity C
; bytes is a gap buffer: physical bytes [0, gs) and [ge, C) hold the text,
; the gap [gs, ge) is free; logical position i is physical i below gs, else
; i + (ge - gs). A byte at physical p lives in block p >> 14 of the buffer,
; at offset p & #3FFF; the runtime maps that block at #8000 itself
; (bios_setmem2, as code banks are mapped: ROSAN283 'Memory Layout', "you
; can do what you want with the 2nd, 3rd and 4th quarters"), and maps the
; block found there back before it returns. These routines are resident and
; run nothing from #8000 while a text block is there.
; Lines: a line ends at LF (#0A); a CR right before that LF belongs to the
; line end. Line n's length and text exclude its end. The last line has no
; end. TEXTLINES = number of LFs + 1.
; Buffer record (generated, 18 bytes at var_NAME): +0 capacity, +2 first
; slot, +3 blocks, +4 gs, +6 ge, +8 lines, +10 changed, +11 line-end style
; (0 CR LF, 1 LF: that of the first line end loaded), +12 cache line,
; +14 its logical start, +16 the column of the last TEXTFIND.
; Each routine copies the record to rt_tx_s, works there, and copies it back.
; ----------------------------------------------------------------------------

; rt_tx_enter — HL = the buffer record: copy it in; nothing mapped yet.
rt_tx_enter:
    ld (rt_tx_rec),hl
    ld de,rt_tx_s
    ld bc,18
    ldir
    ld a,0FFh
    ld (rt_tx_cur),a
    ret

; rt_tx_leave — map back what was at #8000, copy the record out.
rt_tx_leave:
    call rt_tx_unmap
    ld hl,rt_tx_s
    ld de,(rt_tx_rec)
    ld bc,18
    ldir
    ret

rt_tx_unmap:
    ld a,(rt_tx_cur)
    cp 0FFh
    ret z
    ld a,0FFh
    ld (rt_tx_cur),a
    ld a,(rt_tx_q2)
    call 0C2h                   ; bios_setmem2 (all registers preserved)
    ret

; rt_tx_fail — HL = error text, BC = its length: unmap, then the report.
rt_tx_fail:
    push hl
    push bc
    call rt_tx_unmap
    pop bc
    pop hl
    jp rt_err_msg

; rt_tx_addr — HL = physical position: map its block, HL = its address.
; Preserves BC, DE.
rt_tx_addr:
    ld a,h
    rlca
    rlca
    and 3                       ; block = p >> 14
    push hl
    ld hl,rt_tx_cur
    cp (hl)
    jp z,rt_tx_addr_mapped
    push de
    ld e,a
    ld a,(hl)
    cp 0FFh
    jp nz,rt_tx_addr_swap
    call 0CEh                   ; first mapping: remember the block at #8000
    ld (rt_tx_q2),a
rt_tx_addr_swap:
    ld a,e
    ld (rt_tx_cur),a
    ld a,(TX_SLOT)
    add a,e
    ld e,a
    ld d,0
    ld hl,rt_bank_list
    add hl,de
    ld a,(hl)
    call 0C2h                   ; bios_setmem2
    pop de
rt_tx_addr_mapped:
    pop hl
    ld a,h
    and 3Fh
    or 80h
    ld h,a
    ret

; rt_tx_phys — HL = logical position -> physical. Preserves BC, DE.
rt_tx_phys:
    push de
    ld de,(TX_GS)
    ld a,l
    sub e
    ld a,h
    sbc a,d
    jp c,rt_tx_phys_done        ; below the gap
    push hl
    ld hl,(TX_GE)
    or a
    sbc hl,de                   ; the gap's size
    pop de
    add hl,de
rt_tx_phys_done:
    pop de
    ret

; rt_tx_get — HL = logical position: A = the byte. Preserves BC, DE.
rt_tx_get:
    call rt_tx_phys
    call rt_tx_addr
    ld a,(hl)
    ret

; rt_tx_len_all — HL = the text's length = gs + capacity - ge.
rt_tx_len_all:
    ld hl,(TX_CAP)
    ld de,(TX_GE)
    or a
    sbc hl,de
    ld de,(TX_GS)
    add hl,de
    ret

; rt_tx_gap_to — move the gap so that it starts at logical position HL.
; The bytes between move in pieces of at most 128 that cross no block end
; on either side, each through rt_tx_tmp (so overlapping ranges are safe).
rt_tx_gap_to:
    ld (rt_tx_to),hl
rt_tx_gap_loop:
    ld hl,(rt_tx_to)
    ld de,(TX_GS)
    or a
    sbc hl,de
    ret z
    jp c,rt_tx_gap_left
    ld de,128                   ; the gap moves right: bytes from ge to gs
    call rt_tx_min
    push hl
    ld hl,(TX_GE)
    call rt_tx_room_after
    pop de
    call rt_tx_min
    push hl
    ld hl,(TX_GS)
    call rt_tx_room_after
    pop de
    call rt_tx_min
    ld (rt_tx_mv),hl
    ld hl,(TX_GE)
    ld de,(TX_GS)
    call rt_tx_move
    ld de,(rt_tx_mv)
    ld hl,(TX_GS)
    add hl,de
    ld (TX_GS),hl
    ld hl,(TX_GE)
    add hl,de
    ld (TX_GE),hl
    jp rt_tx_gap_loop
rt_tx_gap_left:
    ex de,hl                    ; the gap moves left: bytes before gs to before ge
    ld hl,0
    or a
    sbc hl,de                   ; distance
    ld de,128
    call rt_tx_min
    push hl
    ld hl,(TX_GS)
    call rt_tx_room_before
    pop de
    call rt_tx_min
    push hl
    ld hl,(TX_GE)
    call rt_tx_room_before
    pop de
    call rt_tx_min
    ld (rt_tx_mv),hl
    ex de,hl
    ld hl,(TX_GS)
    or a
    sbc hl,de
    ld (TX_GS),hl               ; the source
    push hl
    ld hl,(TX_GE)
    or a
    sbc hl,de
    ld (TX_GE),hl               ; the destination
    ex de,hl
    pop hl
    call rt_tx_move
    jp rt_tx_gap_loop

; rt_tx_move — rt_tx_mv (1..128) bytes from physical HL to physical DE,
; neither range crossing a block end, through rt_tx_tmp.
rt_tx_move:
    push de
    call rt_tx_addr
    ld de,rt_tx_tmp
    ld bc,(rt_tx_mv)
    ldir
    pop hl
    call rt_tx_addr
    ex de,hl
    ld hl,rt_tx_tmp
    ld bc,(rt_tx_mv)
    ldir
    ret

; rt_tx_min — HL = the smaller of HL and DE (unsigned).
rt_tx_min:
    push hl
    or a
    sbc hl,de
    pop hl
    ret c
    ex de,hl
    ret

; rt_tx_room_after — HL = bytes from physical HL to its block's end.
rt_tx_room_after:
    ld a,h
    and 3Fh
    ld h,a
    ex de,hl
    ld hl,4000h
    or a
    sbc hl,de
    ret

; rt_tx_room_before — HL = bytes from its block's start up to physical HL
; (HL >= 1).
rt_tx_room_before:
    dec hl
    ld a,h
    and 3Fh
    ld h,a
    inc hl
    ret

; rt_tx_put — A = a byte to insert at the gap start (room checked).
rt_tx_put:
    ld hl,(TX_GS)
    push hl
    push af
    call rt_tx_addr
    pop af
    ld (hl),a
    pop hl
    inc hl
    ld (TX_GS),hl
    ret

; rt_tx_room — C unless at least DE bytes are free (ge - gs >= DE).
rt_tx_room:
    ld hl,(TX_GE)
    ld bc,(TX_GS)
    or a
    sbc hl,bc
    or a
    sbc hl,de
    ret

; rt_tx_seek — rt_tx_n = a line number: check 1..lines, set rt_tx_lp to
; its logical start, rt_tx_ll to its length, rt_tx_tl to the length of its
; end (0, 1 LF, 2 CR LF); the cache becomes this line.
rt_tx_seek:
    ld hl,(rt_tx_n)
    ld a,h
    or l
    jp z,rt_tx_bad_pos
    bit 7,h
    jp nz,rt_tx_bad_pos
    ex de,hl
    ld hl,(TX_LINES)
    or a
    sbc hl,de
    jp c,rt_tx_bad_pos
    ; from the cache, or from the start if the line is above it
    ld hl,(TX_CL)
    or a
    sbc hl,de                   ; cache line - n
    jp z,rt_tx_seek_found
    jp c,rt_tx_seek_fwd
    ld hl,1                     ; above the cache: start again
    ld (TX_CL),hl
    ld hl,0
    ld (TX_CP),hl
    ld hl,(rt_tx_n)
    dec hl
    ld a,h
    or l
    jp z,rt_tx_seek_found
rt_tx_seek_fwd:
    call rt_tx_len_all
    ld (rt_tx_end),hl
    ld hl,(TX_CP)
rt_tx_seek_scan:
    push hl
    call rt_tx_get
    pop hl
    inc hl
    cp 10
    jp nz,rt_tx_seek_scan
    ld (TX_CP),hl               ; the next line starts after this LF
    ld de,(TX_CL)
    inc de
    ld (TX_CL),de
    ex de,hl
    ld bc,(rt_tx_n)
    or a
    sbc hl,bc
    ex de,hl
    jp nz,rt_tx_seek_scan
rt_tx_seek_found:
    ld hl,(TX_CP)
    ld (rt_tx_lp),hl
    ; the length: up to the LF or the end of the text
    call rt_tx_len_all
    ld (rt_tx_end),hl
    ld hl,(rt_tx_lp)
rt_tx_seek_len:
    ex de,hl
    ld hl,(rt_tx_end)
    or a
    sbc hl,de
    ex de,hl
    jp z,rt_tx_seek_last        ; the end of the text: no line end
    push hl
    call rt_tx_get
    pop hl
    cp 10
    jp z,rt_tx_seek_lf
    inc hl
    jp rt_tx_seek_len
rt_tx_seek_last:
    xor a
    ld (rt_tx_tl),a
    jp rt_tx_seek_set
rt_tx_seek_lf:
    ld a,1
    ld (rt_tx_tl),a
    ld de,(rt_tx_lp)
    or a
    sbc hl,de
    add hl,de
    jp z,rt_tx_seek_set         ; an empty line: no CR before its LF
    dec hl
    push hl
    call rt_tx_get
    pop hl
    cp 13
    jp z,rt_tx_seek_cr
    inc hl
    jp rt_tx_seek_set
rt_tx_seek_cr:
    ld a,2
    ld (rt_tx_tl),a
rt_tx_seek_set:
    ld de,(rt_tx_lp)
    or a
    sbc hl,de
    ld (rt_tx_ll),hl
    ret

; rt_tx_col — rt_tx_c = a column: check 1..length + 1 (rt_tx_c_max = 0)
; or 1..length (rt_tx_c_max = 1); HL = its logical position.
rt_tx_col:
    ld hl,(rt_tx_c)
    ld a,h
    or l
    jp z,rt_tx_bad_pos
    bit 7,h
    jp nz,rt_tx_bad_pos
    ex de,hl                    ; DE = column
    ld hl,(rt_tx_ll)
    ld a,(rt_tx_c_max)
    or a
    jp nz,rt_tx_col_end
    inc hl                      ; up to length + 1
rt_tx_col_end:
    or a
    sbc hl,de
    jp c,rt_tx_bad_pos          ; limit < column
    ld hl,(rt_tx_lp)
    add hl,de
    dec hl
    ret

rt_tx_bad_pos:
    ld hl,rt_tx_pos_text
    ld bc,rt_tx_pos_text_end-rt_tx_pos_text
    jp rt_tx_fail
rt_tx_full:
    ld hl,rt_tx_full_text
    ld bc,rt_tx_full_text_end-rt_tx_full_text
    jp rt_tx_fail

; ---------------------------------------------------------------- functions
; rt_text_len — TEXTLEN: HL = record, rt_tx_n = line; out HL = its length.
rt_text_len:
    call rt_tx_enter
    call rt_tx_seek
    call rt_tx_leave
    ld hl,(rt_tx_ll)
    ret

; rt_text_free — TEXTFREE: HL = record; out HL = free bytes (ge - gs);
; rt_text_used — TEXTSIZE: bytes of text. Both at most 32767 (an INTEGER).
rt_text_free:
    call rt_tx_enter
    ld hl,(TX_GE)
    ld de,(TX_GS)
    or a
    sbc hl,de
    jp rt_text_clamp
rt_text_used:
    call rt_tx_enter
    call rt_tx_len_all
rt_text_clamp:
    bit 7,h
    ret z
    ld hl,32767
    ret

; rt_text_get — TEXTGET$: HL = record; rt_tx_n line, rt_tx_c column
; (1..length + 1), rt_tx_k count (>= 0); appends at DE through rt_put the
; line's bytes from the column on, at most count of them (a zero byte as
; '?'). DE is advanced.
rt_text_get:
    push de
    call rt_tx_enter
    call rt_tx_seek
    xor a
    ld (rt_tx_c_max),a
    call rt_tx_col
    ld (rt_tx_at),hl
    ld hl,(rt_tx_k)
    bit 7,h
    jp nz,rt_tx_bad_pos
    ; available = lp + ll - at
    ld hl,(rt_tx_lp)
    ld de,(rt_tx_ll)
    add hl,de
    ld de,(rt_tx_at)
    or a
    sbc hl,de
    ex de,hl
    ld hl,(rt_tx_k)
    or a
    sbc hl,de
    jp c,rt_text_get_n          ; count < available: count bytes
    ld (rt_tx_k),de
rt_text_get_n:
    ld hl,(rt_tx_k)             ; at most 128 bytes: more cannot fit a STRING
    ld de,129
    or a
    sbc hl,de
    jp c,rt_text_get_some
    ld hl,128
    ld (rt_tx_k),hl
rt_text_get_some:
    ld de,rt_tx_tmp
rt_text_get_loop:
    ld hl,(rt_tx_k)
    ld a,h
    or l
    jp z,rt_text_get_done
    dec hl
    ld (rt_tx_k),hl
    ld hl,(rt_tx_at)
    push hl
    call rt_tx_get
    pop hl
    inc hl
    ld (rt_tx_at),hl
    or a
    jp nz,rt_text_get_keep
    ld a,'?'                    ; a STRING cannot hold a zero byte
rt_text_get_keep:
    ld (de),a
    inc de
    jp rt_text_get_loop
rt_text_get_done:
    ld (rt_tx_to),de            ; the end of what was collected
    call rt_tx_leave            ; nothing mapped while rt_put may report
    pop de
    ld hl,rt_tx_tmp
rt_text_get_put:
    push hl
    ld bc,(rt_tx_to)
    or a
    sbc hl,bc
    pop hl
    ret z
    ld a,(hl)
    call rt_put
    inc hl
    jp rt_text_get_put

; rt_text_find — TEXTFIND: HL = record, rt_tx_str = the text sought,
; rt_tx_n line, rt_tx_c column (1..length + 1) to start at; out HL = the
; line it starts in (0 = not found), record +16 = its column. An empty text
; is never found. The text never spans a line end (it cannot hold an LF).
rt_text_find:
    call rt_tx_enter
    call rt_tx_seek
    xor a
    ld (rt_tx_c_max),a
    call rt_tx_col
    ld (rt_tx_at),hl
    ld hl,(rt_tx_n)
    ld (rt_tx_fl),hl            ; the line being searched
    ld hl,(rt_tx_lp)
    ld (rt_tx_fs),hl            ; and where it starts
    call rt_tx_len_all
    ld (rt_tx_end),hl
    ld hl,(rt_tx_str)
    ld a,(hl)
    or a
    jp z,rt_text_find_none
rt_text_find_at:
    ld hl,(rt_tx_at)            ; does the text start at rt_tx_at?
    ld (rt_tx_to),hl
    ld de,(rt_tx_str)
rt_text_find_cmp:
    ld a,(de)
    or a
    jp z,rt_text_find_hit       ; all of it matched
    ld hl,(rt_tx_to)
    call rt_tx_atend
    jp z,rt_text_find_none      ; the text runs past the end
    push de
    push hl
    call rt_tx_get
    pop hl
    pop de
    ex de,hl
    cp (hl)
    ex de,hl
    jp nz,rt_text_find_next
    inc hl
    ld (rt_tx_to),hl
    inc de
    jp rt_text_find_cmp
rt_text_find_next:
    ld hl,(rt_tx_at)            ; one byte on (past an LF: the next line)
    call rt_tx_atend
    jp z,rt_text_find_none
    push hl
    call rt_tx_get
    pop hl
    inc hl
    ld (rt_tx_at),hl
    cp 10
    jp nz,rt_text_find_at
    ld (rt_tx_fs),hl
    ld hl,(rt_tx_fl)
    inc hl
    ld (rt_tx_fl),hl
    jp rt_text_find_at

; rt_tx_atend — Z if HL is the end of the text (rt_tx_end). Keeps HL, DE.
rt_tx_atend:
    push de
    ex de,hl
    ld hl,(rt_tx_end)
    or a
    sbc hl,de
    ex de,hl
    pop de
    ret

rt_text_find_hit:
    ld hl,(rt_tx_at)
    ld de,(rt_tx_fs)
    or a
    sbc hl,de
    inc hl
    ld (TX_FC),hl
    call rt_tx_leave
    ld hl,(rt_tx_fl)
    ret
rt_text_find_none:
    ld hl,0
    ld (TX_FC),hl
    call rt_tx_leave
    ld hl,0
    ret

; --------------------------------------------------------------- statements
; rt_text_clear — TEXT CLEAR: HL = record; empty, unchanged.
rt_text_clear:
    call rt_tx_enter
    call rt_tx_reset
    jp rt_tx_leave
rt_tx_reset:
    ld hl,0
    ld (TX_GS),hl
    ld (TX_CP),hl
    ld (TX_FC),hl
    ld hl,(TX_CAP)
    ld (TX_GE),hl
    ld hl,1
    ld (TX_LINES),hl
    ld (TX_CL),hl
    xor a
    ld (TX_CHG),a
    ld (TX_STYLE),a
    ret

; rt_text_insert — TEXT INSERT: HL = record; rt_tx_n line, rt_tx_c column
; (1..length + 1), rt_tx_str the text (no CR or LF in it).
rt_text_insert:
    call rt_tx_enter
    call rt_tx_seek
    xor a
    ld (rt_tx_c_max),a
    call rt_tx_col
    push hl
    ld hl,(rt_tx_str)
    ld de,0
rt_text_ins_len:
    ld a,(hl)
    or a
    jp z,rt_text_ins_room
    cp 10
    jp z,rt_text_ins_break
    cp 13
    jp z,rt_text_ins_break
    inc hl
    inc de
    jp rt_text_ins_len
rt_text_ins_break:
    pop hl
    ld hl,rt_tx_brk_text
    ld bc,rt_tx_brk_text_end-rt_tx_brk_text
    jp rt_tx_fail
rt_text_ins_room:
    call rt_tx_room
    pop hl
    jp c,rt_tx_full
    call rt_tx_gap_to
    ld hl,(rt_tx_str)
rt_text_ins_copy:
    ld a,(hl)
    or a
    jp z,rt_tx_changed
    push hl
    call rt_tx_put
    pop hl
    inc hl
    jp rt_text_ins_copy
rt_tx_changed:
    ld a,1
    ld (TX_CHG),a
    jp rt_tx_leave

; rt_text_delete — TEXT DELETE: rt_tx_n line, rt_tx_c column (1..length),
; rt_tx_k count: the count bytes from the column, all within the line.
rt_text_delete:
    call rt_tx_enter
    call rt_tx_seek
    ld hl,(rt_tx_k)
    bit 7,h
    jp nz,rt_tx_bad_pos
    ld a,h
    or l
    jp z,rt_text_delete_none
    ld a,1
    ld (rt_tx_c_max),a
    call rt_tx_col
    push hl                     ; the first byte
    ld de,(rt_tx_k)
    add hl,de                   ; one past the last
    ld de,(rt_tx_lp)
    or a
    sbc hl,de
    ex de,hl
    ld hl,(rt_tx_ll)
    or a
    sbc hl,de
    pop hl
    jp c,rt_tx_bad_pos          ; past the line's end
    call rt_tx_gap_to
    ld hl,(TX_GE)
    ld de,(rt_tx_k)
    add hl,de
    ld (TX_GE),hl
    jp rt_tx_changed

rt_text_delete_none:            ; count 0: only the column is checked (1..length + 1)
    xor a
    ld (rt_tx_c_max),a
    call rt_tx_col
    jp rt_tx_leave

; rt_text_split — TEXT SPLIT: rt_tx_n line, rt_tx_c column (1..length + 1):
; a line end goes in before the column — the line's own kind of end, or for
; the last line the buffer's style.
rt_text_split:
    call rt_tx_enter
    call rt_tx_seek
    xor a
    ld (rt_tx_c_max),a
    call rt_tx_col
    push hl
    ld a,(rt_tx_tl)
    or a
    jp nz,rt_text_split_kind
    ld a,(TX_STYLE)             ; the last line: 0 -> CR LF (2), 1 -> LF (1)
    xor 1
    inc a
rt_text_split_kind:
    ld (rt_tx_tl),a
    ld e,a
    ld d,0
    call rt_tx_room
    pop hl
    jp c,rt_tx_full
    call rt_tx_gap_to
    ld a,(rt_tx_tl)
    cp 2
    jp nz,rt_text_split_lf
    ld a,13
    call rt_tx_put
rt_text_split_lf:
    ld a,10
    call rt_tx_put
    ld hl,(TX_LINES)
    inc hl
    ld (TX_LINES),hl
    jp rt_tx_changed

; rt_text_join — TEXT JOIN: rt_tx_n line (1..lines - 1): its end goes, the
; next line joins it.
rt_text_join:
    call rt_tx_enter
    call rt_tx_seek
    ld a,(rt_tx_tl)
    or a
    jp z,rt_tx_bad_pos          ; the last line has no end to remove
    ld hl,(rt_tx_lp)
    ld de,(rt_tx_ll)
    add hl,de
    call rt_tx_gap_to
    ld a,(rt_tx_tl)
    ld e,a
    ld d,0
    ld hl,(TX_GE)
    add hl,de
    ld (TX_GE),hl
    ld hl,(TX_LINES)
    dec hl
    ld (TX_LINES),hl
    jp rt_tx_changed

; rt_text_load — TEXT LOAD: HL = record, rt_file_desc = file descriptor.
; The buffer is emptied, then filled from the file one byte per
; os_read_file (the XAnne-proven M7 read: Rosanne's registers at the end of
; a file are not reliable, M4 repair). IOERR: 0, a Rosanne code, or 246 when
; the file does not fit (the buffer is then left empty). Unchanged after.
rt_text_load:
    call rt_tx_enter
    call rt_tx_reset
    ld a,0FFh
    ld (rt_tx_first),a          ; no line end seen yet
    xor a
    ld (rt_tx_prev),a
    call rt_file_prepare
    jp c,rt_text_load_prep
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld b,0
    ld a,144
    call 003Bh
    jp c,rt_text_load_err
rt_text_load_byte:
    ld hl,rt_file_buf+639
    ld (rt_dst_end),hl          ; the buffer is the active destination (as M7)
    call 0CBh
    ld c,a
    ld hl,rt_file_buf
    ld b,0
    ld de,1
    ld a,147
    call 003Bh
    jp c,rt_text_load_end
    ld de,1
    call rt_tx_room
    jp c,rt_text_load_big
    ld a,(rt_file_buf)
    ld (rt_tx_byte),a
    call rt_tx_put
    ld a,(rt_tx_byte)
    cp 10
    jp nz,rt_text_load_prev
    ld hl,(TX_LINES)
    inc hl
    ld (TX_LINES),hl
    ld a,(rt_tx_first)          ; the first line end decides the style
    cp 0FFh
    jp nz,rt_text_load_prev
    ld a,(rt_tx_prev)
    cp 13
    ld a,0
    jp z,rt_text_load_style
    inc a
rt_text_load_style:
    ld (TX_STYLE),a
    ld (rt_tx_first),a
rt_text_load_prev:
    ld a,(rt_tx_byte)
    ld (rt_tx_prev),a
    jp rt_text_load_byte
rt_text_load_end:
    cp 0A1h                     ; "Premature EoF": the whole file is in
    jp nz,rt_text_load_rerr
    call rt_text_load_close
    xor a
    jp rt_text_io
rt_text_load_rerr:
    push af
    call rt_text_load_close
    call rt_tx_reset
    pop af
    jp rt_text_io
rt_text_load_big:
    call rt_text_load_close
    call rt_tx_reset
    ld a,246
    jp rt_text_io
rt_text_load_close:
    call rt_tx_unmap
    ld b,0
    ld a,145
    call 003Bh
    ret
rt_text_load_err:
    jp rt_text_io
rt_text_load_prep:
    call rt_fio_prep_fail       ; sets IOERR from rt_file_prepare's reason
    jp rt_tx_leave

; rt_text_io — A = IOERR: set it, copy the record out.
rt_text_io:
    call rt_fio_set
    jp rt_tx_leave

; rt_text_save — TEXT SAVE: HL = record, rt_file_desc = descriptor. The
; file is created or replaced (Rosanne truncates on open, M4 F1) and the
; text written from its blocks with os_write_file (146: "CHL = 24-bit
; address to write data from, BDE = 24-bit length"), one piece per block
; and side of the gap. IOERR as for PRINT #; unchanged after a good save.
rt_text_save:
    call rt_tx_enter
    call rt_file_prepare
    jp c,rt_text_load_prep
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld b,1
    ld a,144
    call 003Bh
    jp c,rt_text_io
    ld hl,0                     ; [0, gs)
    ld de,(TX_GS)
    call rt_tx_write_run
    jp c,rt_text_save_fail
    ld hl,(TX_GE)               ; [ge, capacity)
    ld de,(TX_CAP)
    call rt_tx_write_run
    jp c,rt_text_save_fail
    ld b,1
    ld a,145
    call 003Bh
    jp c,rt_text_io
    xor a
    ld (TX_CHG),a
    jp rt_text_io
rt_text_save_fail:
    push af
    ld b,1
    ld a,145
    call 003Bh                  ; close; the write's error is the one reported
    pop af
    jp rt_text_io

; rt_tx_write_run — write physical [HL, DE) in pieces that do not cross a
; block end. C = error (A = Rosanne's code).
rt_tx_write_run:
    ld (rt_tx_at),hl
    ld (rt_tx_to),de
rt_tx_write_piece:
    ld hl,(rt_tx_to)
    ld de,(rt_tx_at)
    or a
    sbc hl,de                   ; bytes left
    ret z
    ; up to the end of this block: #4000 - (at & #3FFF)
    push hl
    ld a,d
    and 3Fh
    ld d,a
    ld hl,4000h
    or a
    sbc hl,de
    pop de                      ; DE = bytes left, HL = room in the block
    push hl
    or a
    sbc hl,de
    pop hl
    jp c,rt_tx_write_n          ; the block ends first: HL bytes
    ex de,hl                    ; all that is left
rt_tx_write_n:
    ld (rt_tx_k),hl
    ld hl,(rt_tx_at)
    ld a,h
    rlca
    rlca
    and 3
    ld e,a
    ld a,(TX_SLOT)
    add a,e
    ld e,a
    ld d,0
    push hl
    ld hl,rt_bank_list
    add hl,de
    ld c,(hl)                   ; the block
    pop hl
    ld a,h
    and 3Fh
    ld h,a                      ; its offset
    ld de,(rt_tx_k)
    ld b,0
    ld a,146
    call 003Bh
    ret c
    ld hl,(rt_tx_at)
    ld de,(rt_tx_k)
    add hl,de
    ld (rt_tx_at),hl
    jp rt_tx_write_piece

rt_tx_pos_text:
    db "Runtime error: text position out of range at line "
rt_tx_pos_text_end:
rt_tx_full_text:
    db "Runtime error: the TEXT buffer is full at line "
rt_tx_full_text_end:
rt_tx_brk_text:
    db "Runtime error: TEXT INSERT text has a line break at line "
rt_tx_brk_text_end:
    ENDIF

    IF PB_TXRANGE
; ----------------------------------------------------------------------------
; M10 Stage D: TEXT ranges across lines and between buffers (LANGUAGE-SPEC
; §5.7, M10 additions): TEXT REMOVE, TEXT COPY, TEXT PASTE, TEXTSAME. A
; separate part (PB_TXRANGE), so programs without them keep their bytes.
; Only one buffer is entered at a time (its blocks map at #8000, one at a
; time): bytes move between two buffers in pieces of at most 128 through
; rt_tx_tmp, entering the source, then the destination.
; A range is (rt_tx_n, rt_tx_c) .. (rt_tx_n2, rt_tx_c2), each column
; 1..length + 1 of its line, the start not after the end; it covers the
; bytes from the start up to, not including, the end (line ends included
; whole: a column never falls between a line end's CR and LF).
; ----------------------------------------------------------------------------
; rt_tx_range — in the entered buffer: rt_tx_p1 / rt_tx_p2 the range's
; logical positions, rt_tx_cnt its length, rt_tx_n1 / rt_tx_lp1 the start
; line and its first position. A bad position stops the program.
rt_tx_range:
    ld hl,(rt_tx_n)
    ld (rt_tx_n1),hl
    call rt_tx_pos
    ld (rt_tx_p1),hl
    ld hl,(rt_tx_lp)
    ld (rt_tx_lp1),hl
    ld hl,(rt_tx_n2)
    ld (rt_tx_n),hl
    ld hl,(rt_tx_c2)
    ld (rt_tx_c),hl
    call rt_tx_pos
    ld (rt_tx_p2),hl
    ld de,(rt_tx_p1)
    or a
    sbc hl,de
    jp c,rt_tx_bad_pos          ; the end before the start
    ld (rt_tx_cnt),hl
    ret

; rt_tx_pos — rt_tx_n / rt_tx_c (column 1..length + 1): HL = the logical
; position (rt_tx_seek, rt_tx_col).
rt_tx_pos:
    call rt_tx_seek
    xor a
    ld (rt_tx_c_max),a
    jp rt_tx_col

; rt_tx_whole — the entered buffer's whole text as the range.
rt_tx_whole:
    ld hl,0
    ld (rt_tx_p1),hl
    call rt_tx_len_all
    ld (rt_tx_p2),hl
    ld (rt_tx_cnt),hl
    ret

; rt_tx_count_lf — rt_tx_lf = the LFs in the entered buffer's range.
rt_tx_count_lf:
    ld hl,0
    ld (rt_tx_lf),hl
    ld hl,(rt_tx_p1)
    ld bc,(rt_tx_cnt)
rt_tx_clf_loop:
    ld a,b
    or c
    ret z
    push hl
    call rt_tx_get              ; BC, DE kept
    pop hl
    cp 10
    jp nz,rt_tx_clf_next
    push hl
    ld hl,(rt_tx_lf)
    inc hl
    ld (rt_tx_lf),hl
    pop hl
rt_tx_clf_next:
    inc hl
    dec bc
    jp rt_tx_clf_loop

; rt_tx_read_chunk — rt_tx_chunk (1..128) bytes of the entered buffer from
; logical rt_tx_q to rt_tx_tmp.
rt_tx_read_chunk:
    ld hl,(rt_tx_q)
    ld de,rt_tx_tmp
    ld bc,(rt_tx_chunk)
rt_tx_rc_loop:
    push hl
    call rt_tx_get              ; A = the byte; BC, DE kept
    ex de,hl
    ld (hl),a
    ex de,hl
    pop hl
    inc hl
    inc de
    dec bc
    ld a,b
    or c
    jp nz,rt_tx_rc_loop
    ret

; rt_tx_next_chunk — rt_tx_chunk = min(128, rt_tx_cnt); Z when nothing is left.
rt_tx_next_chunk:
    ld hl,(rt_tx_cnt)
    ld a,h
    or l
    ret z
    ld de,128
    call rt_tx_min
    ld (rt_tx_chunk),hl
    or 1
    ret

; rt_tx_advance — rt_tx_q += rt_tx_chunk, rt_tx_cnt -= rt_tx_chunk.
rt_tx_advance:
    ld de,(rt_tx_chunk)
    ld hl,(rt_tx_q)
    add hl,de
    ld (rt_tx_q),hl
    ld hl,(rt_tx_cnt)
    or a
    sbc hl,de
    ld (rt_tx_cnt),hl
    ret

; rt_tx_xfer — rt_tx_cnt bytes of buffer rt_tx_src from logical rt_tx_q into
; buffer rt_tx_dst at its gap (room already checked); rt_tx_lf counts the
; LFs. Neither buffer is entered before or after.
rt_tx_xfer:
    call rt_tx_next_chunk
    ret z
    ld hl,(rt_tx_src)
    call rt_tx_enter
    call rt_tx_read_chunk
    call rt_tx_leave
    ld hl,(rt_tx_dst)
    call rt_tx_enter
    ld hl,rt_tx_tmp
    ld bc,(rt_tx_chunk)
rt_tx_xf_put:
    ld a,(hl)
    cp 10
    jp nz,rt_tx_xf_byte
    push hl
    ld hl,(rt_tx_lf)
    inc hl
    ld (rt_tx_lf),hl
    pop hl
    ld a,10
rt_tx_xf_byte:
    push hl
    push bc
    call rt_tx_put
    pop bc
    pop hl
    inc hl
    dec bc
    ld a,b
    or c
    jp nz,rt_tx_xf_put
    call rt_tx_leave
    call rt_tx_advance
    jp rt_tx_xfer

; rt_text_remove — TEXT REMOVE: HL = record, the range in the cells: its
; bytes go (line ends inside it too: the lines join). An empty range
; changes nothing.
rt_text_remove:
    call rt_tx_enter
    call rt_tx_range
    ld hl,(rt_tx_cnt)
    ld a,h
    or l
    jp z,rt_tx_leave
    call rt_tx_count_lf
    ld hl,(rt_tx_p1)
    call rt_tx_gap_to
    ld hl,(TX_GE)
    ld de,(rt_tx_cnt)
    add hl,de
    ld (TX_GE),hl
    ld hl,(TX_LINES)
    ld de,(rt_tx_lf)
    or a
    sbc hl,de
    ld (TX_LINES),hl
    ld hl,(rt_tx_n1)            ; the start line is still where it was
    ld (TX_CL),hl
    ld hl,(rt_tx_lp1)
    ld (TX_CP),hl
    jp rt_tx_changed

; rt_text_copy — TEXT COPY: HL = the destination record, rt_tx_src the
; source's; rt_tx_all = 1: the whole source, else the range in the cells.
; The destination becomes exactly those bytes (with the source's line-end
; style); one that cannot hold them is the "buffer is full" error, before
; anything changes.
rt_text_copy:
    ld (rt_tx_dst),hl
    ld hl,(rt_tx_src)
    call rt_tx_enter
    ld a,(rt_tx_all)
    or a
    jp z,rt_text_copy_range
    call rt_tx_whole
    jp rt_text_copy_got
rt_text_copy_range:
    call rt_tx_range
rt_text_copy_got:
    ld a,(TX_STYLE)
    ld (rt_tx_sty),a
    call rt_tx_leave
    ld hl,(rt_tx_dst)
    call rt_tx_enter
    ld hl,(TX_CAP)
    ld de,(rt_tx_cnt)
    or a
    sbc hl,de
    jp c,rt_tx_full
    call rt_tx_reset
    call rt_tx_leave
    ld hl,0
    ld (rt_tx_lf),hl
    ld hl,(rt_tx_p1)
    ld (rt_tx_q),hl
    call rt_tx_xfer
    ld hl,(rt_tx_dst)
    call rt_tx_enter
    ld hl,(rt_tx_lf)
    inc hl
    ld (TX_LINES),hl
    ld a,(rt_tx_sty)
    ld (TX_STYLE),a
    jp rt_tx_changed

; rt_text_paste — TEXT PASTE: HL = the destination record, rt_tx_n /
; rt_tx_c the position (column 1..length + 1), rt_tx_src the source: the
; source's whole text goes in before the column. Not enough room: the
; "buffer is full" error, before anything changes. An empty source changes
; nothing.
rt_text_paste:
    ld (rt_tx_dst),hl
    ld hl,(rt_tx_src)
    call rt_tx_enter
    call rt_tx_whole
    call rt_tx_leave
    ld hl,(rt_tx_dst)
    call rt_tx_enter
    call rt_tx_pos
    push hl
    ld de,(rt_tx_cnt)
    call rt_tx_room
    pop hl
    jp c,rt_tx_full
    ld de,(rt_tx_cnt)
    ld a,d
    or e
    jp z,rt_tx_leave
    call rt_tx_gap_to
    call rt_tx_leave
    ld hl,0
    ld (rt_tx_lf),hl
    ld (rt_tx_q),hl
    call rt_tx_xfer
    ld hl,(rt_tx_dst)
    call rt_tx_enter
    ld hl,(TX_LINES)
    ld de,(rt_tx_lf)
    add hl,de
    ld (TX_LINES),hl
    jp rt_tx_changed

; rt_text_same — TEXTSAME: HL = one record, rt_tx_src the other; HL = 1 if
; their texts are the same bytes, else 0 (line-end style, cache and changed
; flags are not compared).
rt_text_same:
    ld (rt_tx_dst),hl
    call rt_tx_enter
    call rt_tx_whole
    call rt_tx_leave
    ld hl,(rt_tx_src)
    call rt_tx_enter
    call rt_tx_len_all
    push hl
    call rt_tx_leave            ; (HL not kept)
    pop hl
    ld de,(rt_tx_cnt)
    or a
    sbc hl,de
    jp nz,rt_text_same_no
    ld hl,0
    ld (rt_tx_q),hl
rt_text_same_loop:
    call rt_tx_next_chunk
    jp z,rt_text_same_yes
    ld hl,(rt_tx_dst)
    call rt_tx_enter
    call rt_tx_read_chunk
    call rt_tx_leave
    ld hl,(rt_tx_src)
    call rt_tx_enter
    ld hl,(rt_tx_q)
    ld de,rt_tx_tmp
    ld bc,(rt_tx_chunk)
rt_text_same_cmp:
    push hl
    call rt_tx_get              ; BC, DE kept
    pop hl
    ex de,hl
    cp (hl)
    ex de,hl
    jp nz,rt_text_same_diff
    inc hl
    inc de
    dec bc
    ld a,b
    or c
    jp nz,rt_text_same_cmp
    call rt_tx_leave
    call rt_tx_advance
    jp rt_text_same_loop
rt_text_same_diff:
    call rt_tx_leave
rt_text_same_no:
    ld hl,0
    ret
rt_text_same_yes:
    ld hl,1
    ret
    ENDIF

    IF PB_RECORDS
; ----------------------------------------------------------------------------
; M10 records (pbas/records.py, LANGUAGE-SPEC §5.8). A record is plain bytes:
; fields are aliases of its storage, copies are one ldir in the generated
; code. The runtime only keeps a STRING field's bytes canonical.
; ----------------------------------------------------------------------------
; rt_rec_zfill — after a STRING was written into a record field: DE = the NUL
; just written, rt_dst_end = the field's last byte; zero the bytes after the
; NUL, so a record's bytes depend only on its values.
rt_rec_zfill:
    ld hl,(rt_dst_end)
    or a
    sbc hl,de
    ret z
    ret c
    inc de
    xor a
    ld (de),a
    jp rt_rec_zfill
    ENDIF

    IF PB_DB
; ----------------------------------------------------------------------------
; M10 databases (LANGUAGE-SPEC §5.9, docs/M10-ARCHITECTURE.md). A database is
; a BANKED array of records and a record count, loaded and saved whole as a
; PDB1 file:
;   +0 "PDB1"  +4 version 1  +5 flags 0  +6 record size  +8 count
;   +10 next identifier  +12 the TYPE's signature (CRC-16/CCITT-FALSE of
;   the field list, pbas/statements.py _db_signature)  +14 0,0
; then count records of the record size, then a 4-byte check: s1, s2 (16-bit,
; little-endian) where for every byte of the header and the records
; s1 += byte, s2 += s1.
; The generated code passes HL = the database's table
;   cgdb_X: dw cgbank_X (the array's descriptor), signature, cgdbid_X
; (cgdbid_X: the next identifier). Rosanne facts relied on (M4, XAnne):
; opening for write truncates; files are written sequentially; at the end of
; a file os_read_file returns carry with A = #A1 (its other registers are not
; relied on); a read may fill RAM to the end of the 512-byte disc block, so
; every read is at most 128 bytes into rt_file_buf (640 bytes); os_rename_file
; refuses an existing target (#50), so the old backup is deleted first.
; IOERR: 0, a Rosanne code, 247 invalid name, 248 not a database, 249 another
; TYPE, 250 another version, 251 damaged (check, length, or bytes after the
; end; M14: also a STRING field without its 0), 252 too many records (LOAD) /
; the array is full (DB NEW), 253 (M14)
; NAME.NEW or NAME.BAK is another file's (rt_db_own).
; ----------------------------------------------------------------------------
; rt_db_setup — HL = table: the descriptor, signature, identifier cell, the
; array's length and record size into the rt_db_ cells.
rt_db_setup:
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld (rt_db_desc),de
    ld c,(hl)
    inc hl
    ld b,(hl)
    inc hl
    ld (rt_db_sig),bc
    ld c,(hl)
    inc hl
    ld b,(hl)
    ld (rt_db_idp),bc
    IF PB_FSAFE
    inc hl
    ld c,(hl)
    inc hl
    ld b,(hl)
    ld (rt_db_strs),bc          ; M14: the STRING fields (rt_db_strs_ok)
    ENDIF
    ex de,hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld (rt_db_len),de
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld (rt_db_size),de
    ret

; rt_db_ncheck — the count rt_db_n must be 0 .. the array's length (else the
; index error: the count is the program's, not the file's).
rt_db_ncheck:
    ld hl,(rt_db_n)
    ld a,h
    or a
    jp m,rt_index_bad
    ex de,hl
    ld hl,(rt_db_len)
    or a
    sbc hl,de
    jp c,rt_index_bad
    ret

; rt_db_prepare — device, folder and the name (rt_file_prepare); the name's
; own extension is kept in rt_db_ext0. C = failed, A = the IOERR code (as
; rt_fio_prep_fail; 247 when the extension is .NEW or .BAK, which the
; database's own temporary and backup files use).
rt_db_prepare:
    call rt_file_prepare
    jp c,rt_db_prep_bad
    ld hl,rt_low_ext
    ld de,rt_db_ext0
    call rt_low_copy
    ld hl,rt_db_x_new
    call rt_db_ext_is
    jp z,rt_db_prep_name
    ld hl,rt_db_x_bak
    call rt_db_ext_is
    jp z,rt_db_prep_name
    or a
    ret
rt_db_prep_name:
    ld a,247
    scf
    ret
rt_db_prep_bad:
    ld a,(rt_file_reason)
    cp 1
    ld a,3                      ; os_set_cwd #03 Path Not Found
    jp z,rt_db_prep_cf
    ld a,(rt_file_reason)
    cp 6
    ld a,240                    ; os_set_device failed
    jp z,rt_db_prep_cf
    ld a,(rt_file_code)
rt_db_prep_cf:
    scf
    ret

; rt_db_ext_is — Z if the text at HL equals rt_db_ext0.
rt_db_ext_is:
    ld de,rt_db_ext0
rt_db_ext_is_c:
    ld a,(de)
    cp (hl)
    ret nz
    or a
    ret z
    inc hl
    inc de
    jp rt_db_ext_is_c

; rt_db_ext — A = 0 the file's own extension, 1 .NEW, 2 .BAK: HL = its text.
rt_db_ext:
    ld hl,rt_db_ext0
    or a
    ret z
    ld hl,rt_db_x_new
    dec a
    ret z
    ld hl,rt_db_x_bak
    ret

; rt_db_name — A as rt_db_ext: that name to rt_low_name / rt_low_ext.
rt_db_name:
    push af
    ld hl,(rt_file_desc)
    ld de,rt_low_name
    call rt_low_copy
    pop af
    call rt_db_ext
    ld de,rt_low_ext
    jp rt_low_copy

; rt_db_delete_file — A as rt_db_ext: os_delete_file of that name.
rt_db_delete_file:
    call rt_db_name
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld a,153
    call 003Bh
    ret

; rt_db_rename — A = the old name, C = the new one (as rt_db_ext):
; os_rename_file (HL, DE = old; IX, IY = new name, extension; B = #00 file).
; C = failed, A = Rosanne's code.
rt_db_rename:
    ld b,c
    push bc
    call rt_db_name
    ld hl,rt_low_name
    ld de,rt_low_name2
    call rt_low_copy
    pop af                      ; A = the new name
    call rt_db_ext
    ld de,rt_low_ext2
    call rt_low_copy
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld ix,rt_low_name2
    ld iy,rt_low_ext2
    ld b,0
    ld a,154
    call 003Bh
    ret

    IF PB_FSAFE
; rt_db_owns — M14 (KI-91): rt_db_own for NAME.NEW, then NAME.BAK.
rt_db_owns:
    ld a,1
    call rt_db_own
    ret c
    ld a,2
    jp rt_db_own

; rt_db_own — M14 (KI-91): A = 1 NAME.NEW, 2 NAME.BAK. A same-name file with
; another extension shares these companions, so before a save writes or
; deletes one it must be this save's kind: NC when it is not there, is
; shorter than a magic, or begins as rt_db_hdr ("PBI1"; "PDB1" with this
; TYPE's signature, or shorter than a header). C, A = 253 when it is another
; file's; C, A = Rosanne's code when it cannot be opened or read.
rt_db_own:
    call rt_db_name
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld b,0
    ld a,144
    call 003Bh
    jp nc,rt_db_own_rd
    cp 2
    scf
    ret nz
    or a                        ; not there
    ret
rt_db_own_rd:
    ld bc,4
    call rt_db_read
    jp c,rt_db_own_end
    ld hl,rt_file_buf
    ld de,rt_db_hdr
    ld b,4
rt_db_own_m:
    ld a,(de)
    cp (hl)
    jp nz,rt_db_own_no
    inc hl
    inc de
    djnz rt_db_own_m
    ld a,(rt_db_hdr+1)
    cp 'D'                      ; "PDB1": the signature too
    jp nz,rt_db_own_yes
    ld bc,12
    call rt_db_read
    jp c,rt_db_own_end
    ld hl,(rt_file_buf+8)
    ld de,(rt_db_hdr+12)
    or a
    sbc hl,de
    jp z,rt_db_own_yes
rt_db_own_no:
    ld a,253
rt_db_own_fail:
    push af
    call rt_db_close_r
    pop af
    scf
    ret
rt_db_own_end:
    cp 0A1h                     ; it ended first: a leftover, not a file
    jp nz,rt_db_own_fail
rt_db_own_yes:
    call rt_db_close_r
    or a
    ret
    ENDIF

    IF PB_FSAFE
; rt_db_strs_ok — M14: NC if each STRING field of the record in cgbank_wwin
; has its 0 within its capacity; C, A = 251 (damaged) if one has not. The
; fields: rt_db_strs -> db count, then per field dw offset, db capacity.
rt_db_strs_ok:
    ld hl,(rt_db_strs)
    ld b,(hl)
    inc hl
rt_db_sc_field:
    ld a,b
    or a
    ret z
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld c,(hl)
    inc hl
    push hl
    ld hl,cgbank_wwin
    add hl,de
rt_db_sc_byte:
    ld a,(hl)
    or a
    jp z,rt_db_sc_ended
    inc hl
    dec c
    jp nz,rt_db_sc_byte
    pop hl
    ld a,251
    scf
    ret
rt_db_sc_ended:
    pop hl
    dec b
    jp rt_db_sc_field
    ENDIF

; rt_db_read — read BC (1 .. 128) bytes to rt_file_buf. C = failed, A =
; Rosanne's code (#A1: the file ended first).
rt_db_read:
    push bc
    ld hl,rt_file_buf+639
    ld (rt_dst_end),hl          ; the buffer is the active destination (as M7)
    call 0CBh
    ld c,a
    pop de
    ld hl,rt_file_buf
    ld b,0
    ld a,147
    call 003Bh
    ret

; rt_db_need — rt_db_read where the bytes must be there: the end of the file
; becomes 251 (damaged: shorter than its header says).
rt_db_need:
    call rt_db_read
    ret nc
    cp 0A1h
    scf
    ret nz
    ld a,251
    scf
    ret

; rt_db_sum — add BC bytes at HL to the check (rt_db_s1, rt_db_s2).
rt_db_sum:
    ld a,b
    or c
    ret z
    push bc
    ld e,(hl)
    ld d,0
    push hl
    ld hl,(rt_db_s1)
    add hl,de
    ld (rt_db_s1),hl
    ex de,hl
    ld hl,(rt_db_s2)
    add hl,de
    ld (rt_db_s2),hl
    pop hl
    inc hl
    pop bc
    dec bc
    jp rt_db_sum

; rt_db_write — add BC bytes at HL to the check, then write them (os_write_file:
; CHL = address, BDE = length). C = failed, A = Rosanne's code.
rt_db_write:
    ld (rt_db_p),hl
    ld (rt_db_left),bc
    call rt_db_sum
    call 0CBh
    ld c,a
    ld hl,(rt_db_p)
    ld de,(rt_db_left)
    ld b,0
    ld a,146
    call 003Bh
    ret

; rt_db_wlocate — HL = index: the write window's cells name that element
; (rt_bank_put then stores cgbank_wwin there).
rt_db_wlocate:
    ld de,(rt_db_desc)
    call rt_bank_locate
    ld a,(rt_bk_blk)
    ld (rt_bk_wblk),a
    ld hl,(rt_bk_off)
    ld (rt_bk_woff),hl
    ld hl,(rt_bk_size)
    ld (rt_bk_wsize),hl
    ret

; rt_db_zero — clear BC bytes at HL.
rt_db_zero:
    ld a,b
    or c
    ret z
    ld (hl),0
    inc hl
    dec bc
    jp rt_db_zero

; rt_db_peek — HL = index, DE = offset in the record, BC = length (<= 128):
; those bytes of the element to rt_db_key (os_copy_24bit, rt_bk_copy).
rt_db_peek:
    push bc
    push de
    ld de,(rt_db_desc)
    call rt_bank_locate
    pop de
    ld hl,(rt_bk_off)
    add hl,de
    ld (rt_bk_off),hl
    pop bc
    ld (rt_bk_size),bc
    call 0CBh
    ld b,a
    ld a,(rt_bk_blk)
    ld c,a
    ld hl,(rt_bk_off)
    ld de,rt_db_key
    jp rt_bk_copy

; rt_db_load_one — read the file rt_db_try names (as rt_db_ext) into the
; array; with rt_db_vfy set, only check it (the save's read-back). NC = good,
; HL = its count, the identifier cell set (not when checking); C = not
; used, A = the IOERR code (2: there is no such file). The file is closed.
rt_db_load_one:
    ld a,(rt_db_try)
    call rt_db_name
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld b,0
    ld a,144
    call 003Bh
    ret c
    ld hl,0
    ld (rt_db_s1),hl
    ld (rt_db_s2),hl
    ld bc,16
    call rt_db_need
    jp c,rt_db_l_fail
    ld hl,rt_file_buf
    ld de,rt_db_hdr
    ld bc,16
    ldir
    ld hl,rt_db_hdr
    ld bc,16
    call rt_db_sum
    ld hl,rt_db_hdr
    ld de,rt_db_magic
    ld b,4
rt_db_l_magic:
    ld a,(de)
    cp (hl)
    ld a,248                    ; not a database
    jp nz,rt_db_l_fail
    inc hl
    inc de
    djnz rt_db_l_magic
    ld a,(rt_db_hdr+4)
    cp 1
    ld a,250                    ; another version
    jp nz,rt_db_l_fail
    ld hl,(rt_db_hdr+14)
    ld a,(rt_db_hdr+5)
    or h
    or l
    ld a,250
    jp nz,rt_db_l_fail
    ld hl,(rt_db_hdr+6)
    ld de,(rt_db_size)
    or a
    sbc hl,de
    ld a,249                    ; another TYPE
    jp nz,rt_db_l_fail
    ld hl,(rt_db_hdr+12)
    ld de,(rt_db_sig)
    or a
    sbc hl,de
    jp nz,rt_db_l_fail
    ld hl,(rt_db_hdr+8)
    ld (rt_db_cnt),hl
    ld a,h
    or a
    ld a,251
    jp m,rt_db_l_fail
    ex de,hl
    ld hl,(rt_db_len)
    or a
    sbc hl,de
    ld a,252                    ; more records than the array holds
    jp c,rt_db_l_fail
    ld hl,1
    ld (rt_db_i),hl
rt_db_l_rec:
    ld hl,(rt_db_cnt)
    ld de,(rt_db_i)
    or a
    sbc hl,de
    jp c,rt_db_l_tail
    ld a,(rt_db_vfy)
    or a
    jp nz,rt_db_l_start
    ex de,hl
    call rt_db_wlocate
rt_db_l_start:
    ld hl,cgbank_wwin
    ld (rt_db_p),hl
    ld hl,(rt_db_size)
    ld (rt_db_left),hl
rt_db_l_piece:
    ld hl,(rt_db_left)
    ld a,h
    or l
    jp z,rt_db_l_put
    ld bc,128
    or a
    sbc hl,bc
    jp nc,rt_db_l_n
    ld bc,(rt_db_left)
rt_db_l_n:
    push bc
    call rt_db_need
    pop bc
    jp c,rt_db_l_fail
    push bc
    ld hl,rt_file_buf
    call rt_db_sum
    pop bc
    ld a,(rt_db_vfy)
    or a
    jp nz,rt_db_l_next
    ld hl,rt_file_buf
    ld de,(rt_db_p)
    push bc
    ldir
    pop bc
    ld (rt_db_p),de
rt_db_l_next:
    ld hl,(rt_db_left)
    or a
    sbc hl,bc
    ld (rt_db_left),hl
    jp rt_db_l_piece
rt_db_l_put:
    ld a,(rt_db_vfy)
    or a
    IF PB_FSAFE
    jp nz,rt_db_l_inc
    call rt_db_strs_ok          ; M14: every STRING field ends within it
    jp c,rt_db_l_fail
    call rt_bank_put
rt_db_l_inc:
    ELSE
    call z,rt_bank_put
    ENDIF
    ld hl,(rt_db_i)
    inc hl
    ld (rt_db_i),hl
    jp rt_db_l_rec
rt_db_l_tail:
    ld bc,4
    call rt_db_need
    jp c,rt_db_l_fail
    ld hl,(rt_file_buf)
    ld de,(rt_db_s1)
    or a
    sbc hl,de
    ld a,251                    ; the check does not match
    jp nz,rt_db_l_fail
    ld hl,(rt_file_buf+2)
    ld de,(rt_db_s2)
    or a
    sbc hl,de
    jp nz,rt_db_l_fail
    ld bc,1                     ; nothing may follow the check
    call rt_db_read
    jp nc,rt_db_l_extra
    cp 0A1h
    jp nz,rt_db_l_fail
    call rt_db_close_r
    ld a,(rt_db_vfy)
    or a
    jp nz,rt_db_l_good
    ld hl,(rt_db_idp)
    ld de,(rt_db_hdr+10)
    ld (hl),e
    inc hl
    ld (hl),d
rt_db_l_good:
    ld hl,(rt_db_cnt)
    or a
    ret
rt_db_l_extra:
    ld a,251                    ; bytes after the check
rt_db_l_fail:
    push af
    call rt_db_close_r
    pop af
    scf
    ret
rt_db_close_r:
    ld b,0
    ld a,145
    call 003Bh
    ret

; rt_db_load — DB LOAD: HL = table, rt_file_desc = the name. The file, else
; NAME.NEW (a save stopped after writing and checking it), else NAME.BAK (the
; previous save) — the first that reads back whole (M14: the companions are
; tried only when the file is missing, not a database (248) or damaged (251);
; any other failure of the file is reported). Out HL = its count,
; DBRECOVERED = 0 / 1 / 2, IOERR 0. None: HL = 0, the next identifier 1,
; IOERR = the first error of a file that exists, else 2. Elements after the
; count are not changed; after a failed file the elements it reached may
; hold its bytes (a later good file, if any, is then loaded over them).
rt_db_load:
    call rt_db_setup
    xor a
    ld (rt_db_err),a
    ld (rt_db_try),a
    ld (rt_db_vfy),a
    ld hl,0
    ld (rt_db_recov),hl
    call rt_db_prepare
    jp c,rt_db_load_none
rt_db_load_try:
    call rt_db_load_one
    jp nc,rt_db_load_ok
    cp 2
    jp z,rt_db_load_next
    ld b,a
    ld a,(rt_db_err)
    or a
    jp nz,rt_db_load_next
    ld a,b
    ld (rt_db_err),a
    IF PB_FSAFE
    ld a,(rt_db_try)            ; M14: the file itself, whole but not loadable
    or a                        ; here (another TYPE or version, too many
    jp nz,rt_db_load_next       ; records, a read error): report it, never
    ld a,b                      ; load an older copy over it
    cp 248
    jp z,rt_db_load_next
    cp 251
    jp nz,rt_db_load_none
    ENDIF
rt_db_load_next:
    ld a,(rt_db_try)
    inc a
    ld (rt_db_try),a
    cp 3
    jp nz,rt_db_load_try
    ld a,(rt_db_err)
    or a
    jp nz,rt_db_load_none
    ld a,2
rt_db_load_none:
    call rt_fio_set
    ld hl,(rt_db_idp)
    ld (hl),1
    inc hl
    ld (hl),0
    ld hl,0
    ret
rt_db_load_ok:
    push hl
    ld a,(rt_db_try)
    ld l,a
    ld h,0
    ld (rt_db_recov),hl
    xor a
    call rt_fio_set
    pop hl
    ret

; rt_db_save — DB SAVE: HL = table, rt_db_n = count, rt_file_desc = name.
; 0 (M14) refuse (253) if NAME.NEW or NAME.BAK is another file's (rt_db_own);
; 1 write NAME.NEW; 2 read it back (rt_db_load_one, checking only);
; 3 delete NAME.BAK (#02 not found is fine; M14: not when the file itself is
; not there, which goes to 5); 4 rename the file to NAME.BAK
; (#02 is fine: a first save); 5 rename NAME.NEW to the file. A failure in
; 1 .. 4 deletes NAME.NEW and leaves the file as it was; a failure in 5
; leaves the new data in NAME.NEW and the previous file as NAME.BAK, both of
; which DB LOAD reads. IOERR: 0 or the first failure's code.
rt_db_save:
    call rt_db_setup
    call rt_db_ncheck
    call rt_db_prepare
    jp c,rt_fio_set
    ld hl,rt_db_magic
    ld de,rt_db_hdr
    ld bc,4
    ldir
    ld a,1
    ld (rt_db_hdr+4),a
    xor a
    ld (rt_db_hdr+5),a
    ld hl,(rt_db_size)
    ld (rt_db_hdr+6),hl
    ld hl,(rt_db_n)
    ld (rt_db_hdr+8),hl
    ld hl,(rt_db_idp)
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld (rt_db_hdr+10),de
    ld hl,(rt_db_sig)
    ld (rt_db_hdr+12),hl
    ld hl,0
    ld (rt_db_hdr+14),hl
    ld (rt_db_s1),hl
    ld (rt_db_s2),hl
    IF PB_FSAFE
    call rt_db_owns             ; M14 (KI-91)
    jp c,rt_fio_set
    ENDIF
    ld a,1
    call rt_db_name
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld b,1
    ld a,144
    call 003Bh
    jp c,rt_db_s_drop
    ld hl,rt_db_hdr
    ld bc,16
    call rt_db_write
    jp c,rt_db_s_fail
    ld hl,1
    ld (rt_db_i),hl
rt_db_s_rec:
    ld hl,(rt_db_n)
    ld de,(rt_db_i)
    or a
    sbc hl,de
    jp c,rt_db_s_tail
    ex de,hl
    ld de,(rt_db_desc)
    call rt_bank_wref           ; HL = cgbank_wwin, a copy of the element
    ld bc,(rt_db_size)
    call rt_db_write
    jp c,rt_db_s_fail
    ld hl,(rt_db_i)
    inc hl
    ld (rt_db_i),hl
    jp rt_db_s_rec
rt_db_s_tail:
    ld hl,(rt_db_s1)
    ld (rt_db_t),hl
    ld hl,(rt_db_s2)
    ld (rt_db_t+2),hl
    ld hl,rt_db_t
    ld bc,4
    call rt_db_write
    jp c,rt_db_s_fail
    ld b,1
    ld a,145
    call 003Bh
    jp c,rt_db_s_drop
    ld a,1                      ; 2: read NAME.NEW back
    ld (rt_db_try),a
    ld (rt_db_vfy),a
    call rt_db_load_one
    push af
    xor a
    ld (rt_db_vfy),a
    pop af
    jp c,rt_db_s_drop
rt_db_s_steps:                  ; M12: BITMAP SAVE continues here too
    IF PB_FSAFE
    xor a                       ; M14: no file (a first save, or a failed
    call rt_db_name             ; step 5 last time): keep NAME.BAK, step 5
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld b,0
    ld a,144
    call 003Bh
    jp nc,rt_db_s_there
    cp 2
    jp z,rt_db_s_new
    jp rt_db_s_bak
rt_db_s_there:
    call rt_db_close_r
rt_db_s_bak:
    ENDIF
    ld a,2                      ; 3
    call rt_db_delete_file
    jp nc,rt_db_s_old
    cp 2
    jp nz,rt_db_s_drop
rt_db_s_old:
    xor a                       ; 4
    ld c,2
    call rt_db_rename
    jp nc,rt_db_s_new
    cp 2
    jp nz,rt_db_s_drop
rt_db_s_new:
    ld a,1                      ; 5
    ld c,0
    call rt_db_rename
    jp c,rt_fio_set
    xor a
    jp rt_fio_set
rt_db_s_fail:
    push af
    ld b,1
    ld a,145
    call 003Bh                  ; close; the write's error is the one reported
    pop af
rt_db_s_drop:
    push af
    ld a,1
    call rt_db_delete_file      ; its own result is not reported
    pop af
    jp rt_fio_set

; rt_db_new — DB NEW: HL = table, rt_db_n = count. A cleared record with the
; next identifier in its first field becomes element count + 1; out HL = the
; new count, IOERR 0. The array full, or no identifier left (32767 used):
; HL = count unchanged, IOERR 252.
rt_db_new:
    call rt_db_setup
    call rt_db_ncheck           ; HL = length - count
    ld a,h
    or l
    jp z,rt_db_full
    ld hl,(rt_db_idp)
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld a,d
    or e
    jp nz,rt_db_new_id
    inc de                      ; 0 (never set) means 1
rt_db_new_id:
    ld a,d
    or a
    jp m,rt_db_full
    ld (rt_db_k),de
    ld hl,(rt_db_n)
    inc hl
    ld (rt_db_n),hl
    call rt_db_wlocate
    ld hl,cgbank_wwin
    ld bc,(rt_db_size)
    call rt_db_zero
    ld hl,(rt_db_k)
    ld (cgbank_wwin),hl
    call rt_bank_put
    ld hl,(rt_db_k)
    inc hl
    ex de,hl
    ld hl,(rt_db_idp)
    ld (hl),e
    inc hl
    ld (hl),d
    xor a
    call rt_fio_set
    ld hl,(rt_db_n)
    ret
rt_db_full:
    ld a,252
    call rt_fio_set
    ld hl,(rt_db_n)
    ret

; rt_db_delete — DB DELETE: HL = table, rt_db_n = count, rt_db_k = the
; element (1 .. count, else the index error). Later elements move down one
; (their order is kept), the last is cleared; out HL = count - 1. IOERR is
; not changed.
rt_db_delete:
    call rt_db_setup
    call rt_db_ncheck
    ld hl,(rt_db_k)
    ld a,h
    or a
    jp m,rt_index_bad
    or l
    jp z,rt_index_bad
    ex de,hl
    ld hl,(rt_db_n)
    or a
    sbc hl,de
    jp c,rt_index_bad
    ld hl,(rt_db_k)
    ld (rt_db_i),hl
rt_db_d_move:
    ld hl,(rt_db_n)
    ld de,(rt_db_i)
    or a
    sbc hl,de
    jp z,rt_db_d_last
    ex de,hl
    inc hl
    ld de,(rt_db_desc)
    call rt_bank_wref           ; the window = element i + 1
    ld hl,(rt_db_i)
    call rt_db_wlocate          ; stored as element i
    call rt_bank_put
    ld hl,(rt_db_i)
    inc hl
    ld (rt_db_i),hl
    jp rt_db_d_move
rt_db_d_last:
    ld hl,(rt_db_n)
    call rt_db_wlocate
    ld hl,cgbank_wwin
    ld bc,(rt_db_size)
    call rt_db_zero
    call rt_bank_put
    ld hl,(rt_db_n)
    dec hl
    ret

; rt_db_find — DBFIND: HL = table, rt_db_n = count, rt_db_k = identifier.
; Out HL = the first element 1 .. count whose first field holds it, else 0.
rt_db_find:
    call rt_db_setup
    call rt_db_ncheck
    ld hl,1
    ld (rt_db_i),hl
rt_db_f_loop:
    ld hl,(rt_db_n)
    ld de,(rt_db_i)
    or a
    sbc hl,de
    jp c,rt_db_f_none
    ex de,hl
    ld de,0
    ld bc,2
    call rt_db_peek
    ld hl,(rt_db_key)
    ld de,(rt_db_k)
    or a
    sbc hl,de
    jp z,rt_db_f_hit
    ld hl,(rt_db_i)
    inc hl
    ld (rt_db_i),hl
    jp rt_db_f_loop
rt_db_f_hit:
    ld hl,(rt_db_i)
    ret
rt_db_f_none:
    ld hl,0
    ret

; rt_db_nextid — DBNEXTID: HL = table; out HL = the identifier DB NEW gives
; next (a cell never set counts as 1).
rt_db_nextid:
    call rt_db_setup
    ld hl,(rt_db_idp)
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    ld a,h
    or l
    ret nz
    inc hl
    ret

; ----------------------------------------------------------------------------
; M10 Stage C: DB SORT / DB SEARCH (LANGUAGE-SPEC §5.10). The records stay in
; place; an index (a resident INTEGER array: cgarr_X = length, stride 2,
; address) receives element numbers. The generated code sets rt_db_n (the
; count), rt_db_ord (the index's cgarr_ descriptor), rt_db_foff / rt_db_flen
; (the field's offset and size) and rt_db_fk (bits 0-1: 0 INTEGER, 1 STRING,
; 2 REAL; bit 4 DESC; bit 5 NOCASE; bit 6 KEEP), then calls with HL = the table.
; A field's bytes are copied to rt_db_key (rt_db_peek) and a NUL is put after
; them; with NOCASE the copy is upper-cased (a-z only), so one case-sensitive
; comparison serves both.
; ----------------------------------------------------------------------------
; rt_db_order — the index must hold rt_db_n entries (else the index error);
; rt_db_ob = its first element.
rt_db_order:
    ld hl,(rt_db_ord)
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    inc hl
    inc hl
    ld a,(hl)
    inc hl
    ld h,(hl)
    ld l,a
    ld (rt_db_ob),hl
    ex de,hl
    ld de,(rt_db_n)
    or a
    sbc hl,de
    jp c,rt_index_bad
    ret

; rt_db_oaddr — HL = index position (1 ..): HL = its address.
rt_db_oaddr:
    dec hl
    add hl,hl
    ld de,(rt_db_ob)
    add hl,de
    ret

; rt_db_fkey — HL = element: its field to rt_db_key, NUL after, upper-cased
; with NOCASE.
rt_db_fkey:
    ld de,(rt_db_foff)
    ld bc,(rt_db_flen)
    call rt_db_peek
    ld hl,rt_db_key
    ld de,(rt_db_flen)
    add hl,de
    ld (hl),0
    ld a,(rt_db_fk)
    and 20h
    ret z
    ld hl,rt_db_key
rt_db_fkey_up:
    ld a,(hl)
    or a
    ret z
    cp 'a'
    jp c,rt_db_fkey_n
    cp 'z'+1
    jp nc,rt_db_fkey_n
    sub 20h
    ld (hl),a
rt_db_fkey_n:
    inc hl
    jp rt_db_fkey_up

; rt_db_cmp — A = 0 if the key in rt_db_key is below the one in rt_db_kx,
; 1 equal, 2 above (signed INTEGER; REAL; STRING in unsigned byte order, a
; prefix first — as the language's own comparisons).
rt_db_cmp:
    ld a,(rt_db_fk)
    and 3
    jp z,rt_db_cmp_int
    dec a
    jp z,rt_db_cmp_str
    jp rt_db_cmp_real
rt_db_cmp_int:
    ld de,(rt_db_key)
    ld hl,(rt_db_kx)
    jp rt_compare_signed
rt_db_cmp_str:
    ld hl,rt_db_key
    ld de,rt_db_kx
    jp rt_str_compare

; rt_db_cmp_real — the packed REALs (§3.1) at rt_db_key and rt_db_kx,
; compared in their packed form (so a database needs no part of the REAL
; library, pbas/prune.py): first by class (negative, zero, positive; an
; exponent byte 0 is zero), then by magnitude — exponent, then the mantissa
; from its top byte (sign bit cleared) down — reversed for negatives.
rt_db_cmp_real:
    ld hl,rt_db_key
    call rt_db_rclass
    ld (rt_db_rc),a
    ld b,a
    ld hl,rt_db_kx
    call rt_db_rclass
    cp b
    jp z,rt_db_cr_same
    ld a,2                      ; classes differ: carry = the probe's is higher
    ret c
    xor a
    ret
rt_db_cr_same:
    ld a,b
    cp 1
    ret z                       ; both zero: A = 1
    ld a,(rt_db_kx+3)
    and 7Fh
    ld c,a
    ld a,(rt_db_key+4)
    ld hl,rt_db_kx+4
    cp (hl)
    jp nz,rt_db_cr_mag
    ld a,(rt_db_key+3)
    and 7Fh
    cp c
    jp nz,rt_db_cr_mag
    ld de,rt_db_key+2
    ld hl,rt_db_kx+2
    ld b,3
rt_db_cr_byte:
    ld a,(de)
    cp (hl)
    jp nz,rt_db_cr_mag
    dec de
    dec hl
    djnz rt_db_cr_byte
    ld a,1
    ret
rt_db_cr_mag:
    ld a,0                      ; carry: the probe's magnitude is smaller
    jp c,rt_db_cr_sign
    ld a,2
rt_db_cr_sign:
    ld c,a
    ld a,(rt_db_rc)
    or a
    ld a,c
    ret nz                      ; positive
    ld a,2                      ; negative: the larger magnitude is smaller
    sub c
    ret

; rt_db_rclass — HL = a packed REAL: A = 0 negative, 1 zero, 2 positive.
rt_db_rclass:
    push hl
    ld de,4
    add hl,de
    ld a,(hl)
    pop hl
    or a
    ld a,1
    ret z
    inc hl
    inc hl
    inc hl
    ld a,(hl)
    and 80h
    ld a,0
    ret nz
    ld a,2
    ret

; rt_db_sort — DB SORT: the index's entries 1 .. count become the element
; numbers 1 .. count in the field's order (DESC: reversed); records with equal
; keys keep their element order (stable). With KEEP the entries already there
; are sorted instead (each an element number, else the index error), equal
; keys keeping their order in the index. Binary insertion: entry i is
; inserted after the last entry in 1 .. i-1 that it does not precede, with
; its key copied once (rt_db_kx); one field read per comparison.
rt_db_sort:
    call rt_db_setup
    call rt_db_ncheck
    call rt_db_order
    ld a,(rt_db_fk)
    and 40h
    jp nz,rt_db_so_keep
    ld hl,1
    ld (rt_db_i),hl
rt_db_so_fill:
    ld hl,(rt_db_n)
    ld de,(rt_db_i)
    or a
    sbc hl,de
    jp c,rt_db_so_start
    ex de,hl
    push hl
    call rt_db_oaddr
    pop de
    ld (hl),e
    inc hl
    ld (hl),d
    inc de
    ld (rt_db_i),de
    jp rt_db_so_fill
rt_db_so_keep:
    ld hl,(rt_db_n)             ; KEEP with one entry: check it is an element
    ld a,h
    or a
    jp nz,rt_db_so_start
    ld a,l
    dec a
    jp nz,rt_db_so_start
    call rt_db_oaddr            ; HL = 1: the first entry
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    ld de,(rt_db_desc)
    call rt_bank_locate
rt_db_so_start:
    ld hl,2
    ld (rt_db_i),hl
rt_db_so_next:
    ld hl,(rt_db_n)
    ld de,(rt_db_i)
    or a
    sbc hl,de
    ret c
    ex de,hl
    call rt_db_oaddr
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld (rt_db_x),de
    ex de,hl
    call rt_db_fkey
    ld hl,rt_db_key
    ld de,rt_db_kx
    ld bc,128
    ldir
    ld hl,1
    ld (rt_db_lo),hl
    ld hl,(rt_db_i)
    ld (rt_db_hi),hl
rt_db_so_find:
    ld hl,(rt_db_hi)
    ld de,(rt_db_lo)
    or a
    sbc hl,de
    jp z,rt_db_so_put
    add hl,de
    add hl,de
    srl h
    rr l                        ; mid = (lo + hi) / 2 (both <= 32767)
    ld (rt_db_mid),hl
    call rt_db_oaddr
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    call rt_db_fkey
    call rt_db_cmp              ; the probe against the entry being placed
    ld b,a
    ld a,(rt_db_fk)
    and 10h
    ld a,b
    jp z,rt_db_so_asc
    or a                        ; DESC: the entry goes before a smaller probe
    jp z,rt_db_so_left
    jp rt_db_so_right
rt_db_so_asc:
    cp 2                        ; ascending: before a larger probe
    jp z,rt_db_so_left
rt_db_so_right:
    ld hl,(rt_db_mid)
    inc hl
    ld (rt_db_lo),hl
    jp rt_db_so_find
rt_db_so_left:
    ld hl,(rt_db_mid)
    ld (rt_db_hi),hl
    jp rt_db_so_find
rt_db_so_put:
    ld hl,(rt_db_i)             ; move entries lo .. i-1 up one
    ld de,(rt_db_lo)
    or a
    sbc hl,de
    jp z,rt_db_so_store
    add hl,hl
    ld b,h
    ld c,l                      ; 2 * (i - lo) bytes
    ld hl,(rt_db_i)
    call rt_db_oaddr
    inc hl
    ld d,h
    ld e,l                      ; the last byte of entry i
    dec hl
    dec hl                      ; the last byte of entry i - 1
    lddr
rt_db_so_store:
    ld hl,(rt_db_lo)
    call rt_db_oaddr
    ld de,(rt_db_x)
    ld (hl),e
    inc hl
    ld (hl),d
    ld hl,(rt_db_i)
    inc hl
    ld (rt_db_i),hl
    jp rt_db_so_next

; rt_db_pattern — HL = the text DB SEARCH looks for: copied to rt_db_kx
; through rt_put (at most 127 characters, else "string too long"; never
; cut), upper-cased with NOCASE.
rt_db_pattern:
    ld de,rt_db_kx+127
    ld (rt_dst_end),de
    ld de,rt_db_kx
rt_db_pat_c:
    ld a,(hl)
    or a
    jp z,rt_db_pat_end
    call rt_put
    inc hl
    jp rt_db_pat_c
rt_db_pat_end:
    xor a
    ld (de),a
    ld a,(rt_db_fk)
    and 20h
    ret z
    ld hl,rt_db_kx
    jp rt_db_fkey_up

; rt_db_search — DB SEARCH: the elements 1 .. count whose field contains the
; text (rt_db_kx; empty: every element) go to index entries 1 .. found, in
; element order. Out HL = found.
rt_db_search:
    call rt_db_setup
    call rt_db_ncheck
    call rt_db_order
    ld hl,0
    ld (rt_db_cnt),hl
    ld hl,1
    ld (rt_db_i),hl
rt_db_se_next:
    ld hl,(rt_db_n)
    ld de,(rt_db_i)
    or a
    sbc hl,de
    jp c,rt_db_se_done
    ex de,hl
    call rt_db_fkey
    call rt_db_contains
    jp nz,rt_db_se_skip
    ld hl,(rt_db_cnt)
    inc hl
    ld (rt_db_cnt),hl
    call rt_db_oaddr
    ld de,(rt_db_i)
    ld (hl),e
    inc hl
    ld (hl),d
rt_db_se_skip:
    ld hl,(rt_db_i)
    inc hl
    ld (rt_db_i),hl
    jp rt_db_se_next
rt_db_se_done:
    ld hl,(rt_db_cnt)
    ret

; rt_db_contains — Z if rt_db_kx occurs in rt_db_key (both NUL-terminated).
rt_db_contains:
    ld hl,rt_db_key
rt_db_co_at:
    ld de,rt_db_kx
    push hl
rt_db_co_cmp:
    ld a,(de)
    or a
    jp z,rt_db_co_yes
    ld b,a
    ld a,(hl)
    or a
    jp z,rt_db_co_no            ; the text ends first: no later start fits
    cp b
    jp nz,rt_db_co_step
    inc hl
    inc de
    jp rt_db_co_cmp
rt_db_co_step:
    pop hl
    inc hl
    jp rt_db_co_at
rt_db_co_yes:
    pop hl
    xor a
    ret
rt_db_co_no:
    pop hl
    or 1
    ret

rt_db_magic:
    db "PDB1"
rt_db_x_new:
    db ".NEW",0
rt_db_x_bak:
    db ".BAK",0
    ENDIF

    IF PB_FNAME
; ----------------------------------------------------------------------------
; M9 file names given as STRINGs (KILL, NAME, TEXT LOAD / SAVE): the text,
; upper-cased, must be a DOS 8.3 name [A-Z0-9_]{1,8}.[A-Z0-9]{1,3} that is
; not a device name (CON, PRN, AUX, NUL, COM1-9, LPT1-9), as the compiler
; checks a literal (pbas/files.py). rt_fname — HL = the text, DE = a
; 14-byte descriptor to fill (stem NUL, extension with its dot NUL). C = not
; valid: IOERR is set to 247.
; ----------------------------------------------------------------------------
rt_fname:
    ld (rt_fn_out),de
    ld b,0                      ; stem length
rt_fname_stem:
    ld a,(hl)
    call rt_fname_upper
    cp '.'
    jp z,rt_fname_dot
    call rt_fname_char
    jp c,rt_fname_bad
    ld (de),a
    inc de
    inc hl
    inc b
    ld a,b
    cp 9
    jp nc,rt_fname_bad
    jp rt_fname_stem
rt_fname_dot:
    ld a,b
    or a
    jp z,rt_fname_bad
    xor a
    ld (de),a                   ; the stem's NUL
    inc de
    ld (rt_fn_ext),de
    ld a,'.'
    ld (de),a
    inc de
    inc hl
    ld b,0
rt_fname_ext:
    ld a,(hl)
    or a
    jp z,rt_fname_end
    call rt_fname_upper
    cp '_'
    jp z,rt_fname_bad           ; no underscore in an extension
    call rt_fname_char
    jp c,rt_fname_bad
    ld (de),a
    inc de
    inc hl
    inc b
    ld a,b
    cp 4
    jp nc,rt_fname_bad
    jp rt_fname_ext
rt_fname_end:
    ld a,b
    or a
    jp z,rt_fname_bad
    xor a
    ld (de),a
    ; device names: CON PRN AUX NUL, COMn LPTn (n 1..9)
    ld hl,(rt_fn_out)
    ld de,rt_fname_devices
rt_fname_dev:
    ld a,(de)
    or a
    jp z,rt_fname_digit
    push hl
    ld b,3
rt_fname_dev_cmp:
    ld a,(de)
    cp (hl)
    jp nz,rt_fname_dev_skip
    inc hl
    inc de
    djnz rt_fname_dev_cmp
    ld a,(hl)
    pop hl
    or a
    jp z,rt_fname_bad           ; exactly a device name
    jp rt_fname_dev
rt_fname_dev_skip:
    inc de
    djnz rt_fname_dev_skip
    pop hl
    jp rt_fname_dev
rt_fname_digit:
    ld de,rt_fname_ports
rt_fname_port:
    ld a,(de)
    or a
    ret z                       ; NC: a good name
    push hl
    ld b,3
rt_fname_port_cmp:
    ld a,(de)
    cp (hl)
    jp nz,rt_fname_port_skip
    inc hl
    inc de
    djnz rt_fname_port_cmp
    ld a,(hl)
    sub '1'
    cp 9
    jp nc,rt_fname_port_next
    inc hl
    ld a,(hl)
    pop hl
    or a
    jp z,rt_fname_bad           ; COMn / LPTn
    jp rt_fname_port
rt_fname_port_skip:
    inc de
    djnz rt_fname_port_skip
    pop hl
    jp rt_fname_port
rt_fname_port_next:
    pop hl
    jp rt_fname_port
rt_fname_bad:
    ld a,247
    call rt_fio_set
    scf
    ret

; rt_fname_upper — A lower-case letter -> upper case.
rt_fname_upper:
    cp 'a'
    ret c
    cp 'z'+1
    ret nc
    sub 32
    ret
; rt_fname_char — C unless A is A-Z, 0-9 or '_'.
rt_fname_char:
    cp '_'
    ret z
    cp '0'
    ret c
    cp '9'+1
    jp c,rt_fname_ok
    cp 'A'
    ret c
    cp 'Z'+1
    jp c,rt_fname_ok
    scf
    ret
rt_fname_ok:
    or a
    ret

rt_fname_devices: db "CONPRNAUXNUL",0
rt_fname_ports: db "COMLPT",0
    ENDIF

    IF PB_CANVAS
; ============================================================================
; M9 CANVAS (LANGUAGE-SPEC §5.6): a drawing area in a window, DRAW
; statements, and the canvas's PAINT / MOUSE / KEYS handlers.
; ============================================================================
; Generated data (pbas/statements.py): cgcanvas: dw screen x, screen y,
; width, height (the drawing area: the frame box's inside), PAINT, MOUSE,
; KEYS handler addresses (0 = none); db frame object number, window number
; (0 = the program's only window). cgcv_edits: db n, then the object numbers
; of the text fields in the canvas's window (their keys are theirs).
;
; Drawing, all in screen pixels, after the canvas coordinates are checked
; against the canvas (an error, never silent clipping, except text, which
; is cut at the right edge — see rt_draw_text):
;   os_scr_direct (117, ROSAN283: "C,HL = 24-bit address of input
;     parameters: +0 Byte direct graphic function number, +1... Words
;     parameters ... out: A = 0 OK, 1 Error"; "all functions executed with
;     automatic mouse off/on"; function numbers CONSTOS.Z80 RSSET #01:
;     dg_blk_white 1, dg_blk_black 2, dg_blk_grey 3 (+9 grey value 0..8 =
;     black..white), dg_blk_grey_xor 4, dg_blk_copy 10 (+9,+11 x2,y2))
;     for CLEAR, FILL, INVERT and SCROLL;
;   the BIOS (ROSAN283 BIOS table, call #80 + 3n): bios_setink #20 (#E0),
;     bios_getink #21 (#E3), bios_setmode #22 (#E6), bios_getmode #23
;     (#E9), bios_pixel #26 (#F2: DE = x, HL = y), bios_line #28 (#F8: HL
;     -> x1,y1,x2,y2), bios_rectang #29 (#FB: HL -> x,y,w,h), for LINE,
;     PIXEL and BOX. The BIOS takes 16-bit parameter addresses, so the block
;     is in the bottom quarter (#2200, the program's #2000..#2FFF: ROSAN283
;     "AP may use #2000...#2FFF"); the BIOS does not hide the mouse pointer,
;     so os_mouse_off (111) / os_mouse_on (112) bracket each call; the ink
;     and mode found are put back afterwards;
;   os_dialog_string (81: "+0 Font No 1..12, +1 Alignment, +2 Style (0 for
;     now), +3 Mode 0/1/2/3 = Opq/Wht Transp/Blk Transp/XOR, +4,+6 x,y,
;     +8... text, 0-terminated") for TEXT, font 7 (the dialogs' font).
; Events (rt_gui_loop): Rosanne's raw events (os_get_event: bit 8 left
; click, 10 left release, 11 movement, 14 keyboard; record +2 ASCII, +3
; shift, +6/+8 mouse x/y, +10 buttons bit 2 = left) and the dialog's own
; om_objevent messages for the canvas (a click on its frame box, then
; os_get_mouse_xy 114 "out: DE,HL = x,y") or for a non-text object
; (obev_curup..obev_curpgdn 4..9 and obev_focfire 12: the cursor keys and
; space the dialog reports on the focused object) become MOUSE / KEYS calls.
; Which of these reach a program in XAnne is for GFXPROBE to show.
; ----------------------------------------------------------------------------
rt_bios_par equ 2200h           ; 8 bytes: BIOS line / rectangle parameters
RT_CV_CHAR_W equ 11             ; widest font-7 glyph (XAnne, M5d: "W" = 11 px)
RT_CV_TEXT_H equ 16             ; font-7 line height (pbas/layout.py LABEL_GLYPH_H)

; rt_cv_open — the canvas's window is on screen (from rt_gui_run): allow
; drawing and run PAINT. Reached by jp; continues to the event loop.
rt_cv_open:
    IF PB_CVMULTI
    call rt_cvm_mask            ; M15: every canvas of the window on screen
    or a
    jp z,rt_gui_loop            ; none in this window
    ld (rt_cvm_pend),a          ; each one's PAINT, in turn (rt_cvm_next)
    ld a,1
    ld (rt_cv_on),a
    xor a
    ld (rt_cv_down),a
    ld (rt_cv_dirty),a
    jp rt_cvm_next
    ELSE
    ld a,(cgcanvas+15)
    or a
    jp z,rt_cv_open_yes
    IF PB_WINDOWS
    ld hl,rt_win_cur
    cp (hl)
    jp nz,rt_gui_loop           ; another window: no canvas on screen
    ENDIF
rt_cv_open_yes:
    ld a,1
    ld (rt_cv_on),a
    xor a
    ld (rt_cv_down),a
    ld (rt_cv_dirty),a
    ENDIF
rt_cv_paint:
    ld a,1
    ld (rt_cv_painting),a       ; an alert during PAINT asks for no repaint
    ld hl,(cgcanvas+8)
; rt_cv_run — HL = a handler or 0: run it like a button's (rt_gui_call).
rt_cv_run:
    ld a,h
    or l
    jp z,rt_cv_after
    jp rt_gui_call

; rt_cv_after — after every handler (rt_gui_after): an alert shown while
; the canvas was on screen may have left its area to be redrawn (Rosanne
; does not say whether it restores the screen under an alert), so PAINT
; runs once more.
rt_cv_after:
    xor a
    ld (rt_cv_painting),a
    ld a,(rt_cv_dirty)
    or a
    IF PB_CVMULTI
    jp z,rt_cvm_next            ; M15: the next PAINT due, or back to the target
    xor a
    ld (rt_cv_dirty),a
    ld a,(rt_cv_on)
    or a
    jp z,rt_cvm_next
    call rt_cvm_mask            ; every canvas on screen is repainted
    ld (rt_cvm_pend),a
    jp rt_cvm_next
    ELSE
    jp z,rt_gui_loop
    xor a
    ld (rt_cv_dirty),a
    ld a,(rt_cv_on)
    or a
    jp z,rt_gui_loop
    jp rt_cv_paint
    ENDIF

; rt_cv_raw — a raw mouse or key event (HL = event code, IX = record).
rt_cv_raw:
    ld (rt_cv_code),hl
    ld a,(rt_cv_on)
    or a
    jp z,rt_gui_loop
    bit 6,h
    jp nz,rt_cv_keyev
    ld e,(ix+6)
    ld d,(ix+7)
    ld l,(ix+8)
    ld h,(ix+9)
    IF PB_CVMULTI
    call rt_cvm_raw             ; M15: the canvas pressed, or the one held (C: none)
    jp c,rt_gui_loop
    ENDIF
    call rt_cv_local
    ld a,(rt_cv_code+1)
    bit 0,a
    jp nz,rt_cv_press
    bit 2,a
    jp nz,rt_cv_release
    ld a,(rt_cv_down)           ; movement: a drag only after a press here
    or a
    jp z,rt_gui_loop
    ld a,(ix+10)
    bit 2,a
    jp z,rt_cv_release          ; the button is up: the release was missed
    ld a,2
    jp rt_cv_mouse
rt_cv_press:
    call rt_cv_inside
    jp c,rt_gui_loop
    ld a,1
    ld (rt_cv_down),a
    jp rt_cv_mouse
rt_cv_release:
    ld a,(rt_cv_down)
    or a
    jp z,rt_gui_loop
    xor a
    ld (rt_cv_down),a
    ld a,3
rt_cv_mouse:
    ld l,a
    ld h,0
    ld (rt_cv_mev),hl
    ld hl,(rt_cv_tx)
    ld (rt_cv_mx),hl
    ld hl,(rt_cv_ty)
    ld (rt_cv_my),hl
    ld hl,(cgcanvas+10)
    jp rt_cv_run
rt_cv_keyev:
    IF PB_CVMULTI
    call rt_cvm_keys            ; M15: the keyboard's canvas (C: none on screen)
    jp c,rt_gui_loop
    ENDIF
    ld l,(ix+2)
    ld h,0
    ld (rt_cv_key),hl
    ld l,(ix+3)
    ld (rt_cv_shift),hl
    ld hl,(cgcanvas+12)
    jp rt_cv_run

; rt_cv_local — DE, HL = screen x, y -> rt_cv_tx, rt_cv_ty canvas-relative.
rt_cv_local:
    push hl
    ld hl,(cgcanvas)
    ex de,hl
    or a
    sbc hl,de
    ld (rt_cv_tx),hl
    pop hl
    ld de,(cgcanvas+2)
    or a
    sbc hl,de
    ld (rt_cv_ty),hl
    ret

; rt_cv_inside — C unless rt_cv_tx, rt_cv_ty lie in the canvas.
rt_cv_inside:
    ld hl,(rt_cv_tx)
    ld de,1
    ld bc,(cgcanvas+4)
    call rt_cv_span
    ret c
    ld hl,(rt_cv_ty)
    ld de,1
    ld bc,(cgcanvas+6)
    jp rt_cv_span

; rt_cv_objevent — after os_process_event for an om_objevent: out HL = the
; canvas handler the event calls for (0 = none: handled as before).
rt_cv_objevent:
    IF PB_CVMULTI
    call rt_cvm_oe_pick         ; M15: the canvas clicked, or the keyboard's
    ld hl,0
    ret c
    call rt_cv_oe_one
    ld a,h
    or l
    ret nz
    jp rt_cvm_restore           ; not for it after all: the target again (HL = 0)
rt_cv_oe_one:
    ENDIF
    ld hl,0
    ld a,(rt_cv_on)
    or a
    ret z
    ld a,(rt_gui_evtype)
    cp 1
    jp nz,rt_cv_oe_key
    ld a,(cgcanvas+14)
    ld hl,rt_gui_object
    cp (hl)
    ld hl,0
    ret nz                      ; a click on another object
    ld a,114
    call 003Bh                  ; os_get_mouse_xy: DE, HL = x, y
    call rt_cv_local
    call rt_cv_inside
    ld hl,0
    ret c                       ; on the frame line itself
    ld a,1
    ld (rt_cv_down),a
    ld l,a
    ld (rt_cv_mev),hl
    ld hl,(rt_cv_tx)
    ld (rt_cv_mx),hl
    ld hl,(rt_cv_ty)
    ld (rt_cv_my),hl
    ld hl,(cgcanvas+10)
    ret
rt_cv_oe_key:
    ld hl,(cgcanvas+12)
    ld a,h
    or l
    ret z                       ; no KEYS handler
    IF PB_CVMULTI
    ld hl,(rt_cv_edp)           ; M15: the current canvas's window's text fields
    ELSE
    ld hl,cgcv_edits
    ENDIF
    ld b,(hl)
    ld a,(rt_gui_object)
    ld c,a
rt_cv_oe_edit:
    ld a,b
    or a
    jp z,rt_cv_oe_map
    inc hl
    ld a,(hl)
    cp c
    jp z,rt_cv_oe_none          ; a text field's own key
    dec b
    jp rt_cv_oe_edit
rt_cv_oe_none:
    ld hl,0
    ret
rt_cv_oe_map:
    ld a,(rt_gui_evtype)
    sub 4
    ld hl,0
    ret c
    cp 8                        ; obev_focfire (12) - 4
    jp z,rt_cv_oe_space
    cp 6
    ret nc
    ld e,a
    ld d,0
    ld hl,rt_cv_cursor_keys
    add hl,de
    ld a,(hl)
    jp rt_cv_oe_code
rt_cv_oe_space:
    ld a,32
rt_cv_oe_code:
    ld l,a
    ld h,0
    ld (rt_cv_key),hl
    ld l,h
    ld (rt_cv_shift),hl
    ld hl,(cgcanvas+12)
    ret
rt_cv_cursor_keys:              ; ROSAN283 Appendix A: Up, Down, Home, End, PgUp, PgDn
    db 0E0h,0E1h,0E6h,0E7h,0E8h,0E9h

    IF PB_CVMULTI
; ----------------------------------------------------------------------------
; M15 W4 several canvases (LANGUAGE-SPEC 5.6). Generated: cgcv_tab: db n,
; then per canvas the 16 bytes of a cgcanvas descriptor and dw its window's
; text fields (cgcv_ed_k), and cgcanvas: defs 16, the working copy of the
; current canvas, so every drawing routine above and below is unchanged:
; rt_cvm_select copies a canvas in (keeping each canvas's DRAW FONT and TYPE
; FONT, rt_cvm_state). rt_cvm_sel is the DRAW ON target; a canvas's own
; PAINT, MOUSE and KEYS handlers run with it as the target, which is put
; back after every handler (rt_cvm_next). A press goes to the canvas under
; the pointer (and gives it the keyboard), movement and release to the
; canvas pressed, keys to the keyboard's canvas (the last pressed, or FOCUS,
; or the window's first). A canvas is on screen when its window is.
; ----------------------------------------------------------------------------
RT_CVM_ROW equ 18
RT_CVM_S equ PB_DWFONT+PB_TYPO+PB_TYPO+PB_TYPO+PB_TYPO

; DRAW ON Name — HL = the canvas's number (0..n-1).
rt_draw_on:
    ld a,l
    ld (rt_cvm_sel),a
    jp rt_cvm_select

; rt_cvm_restore — the DRAW ON target again; HL kept.
rt_cvm_restore:
    push hl
    ld a,(rt_cvm_sel)
    call rt_cvm_select
    pop hl
    ret

; rt_cvm_next — after a handler (from rt_cv_after) or when a window opens:
; the PAINT of the next canvas in rt_cvm_pend (bit k = canvas k), else the
; DRAW ON target again and the event loop.
rt_cvm_next:
    ld a,(rt_cvm_pend)
    or a
    jp z,rt_cvm_back
    ld c,a
    dec a
    and c
    ld (rt_cvm_pend),a          ; the lowest bit cleared
    xor c                       ; and kept alone in A
    ld b,0
rt_cvm_nx_bit:
    rra
    jp c,rt_cvm_nx_k
    inc b
    jp rt_cvm_nx_bit
rt_cvm_nx_k:
    ld a,b
    call rt_cvm_select
    jp rt_cv_paint
rt_cvm_back:
    ld a,(rt_cvm_sel)
    call rt_cvm_select
    jp rt_gui_loop

; rt_cvm_select — A = a canvas number: it becomes the current canvas.
rt_cvm_select:
    inc a
    ld hl,rt_cvm_cur
    cp (hl)
    ret z
    ld b,(hl)
    ld (hl),a
    push af
    ld a,b
    or a
    call nz,rt_cvm_save         ; the canvas that was current keeps its fonts
    pop af
    dec a
    push af
    call rt_cvm_entry
    ld de,cgcanvas
    ld bc,16
    ldir
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld (rt_cv_edp),de
    pop af
    jp rt_cvm_load

; rt_cvm_entry — A = a canvas number: HL = its entry in cgcv_tab. DE corrupt.
rt_cvm_entry:
    ld l,a
    ld h,0
    add hl,hl
    ld d,h
    ld e,l                      ; 2k
    add hl,hl
    add hl,hl
    add hl,hl                   ; 16k
    add hl,de
    ld de,cgcv_tab+1
    add hl,de
    ret

; rt_cvm_save — A = 1 + the canvas number: its DRAW FONT and TYPE FONT kept.
; rt_cvm_load — A = a canvas number: its fonts back (font 7 and no TYPE
; FONT until it chooses them).
rt_cvm_save:
    dec a
    call rt_cvm_slot
    IF PB_DWFONT
    ld a,(rt_dw_font)
    ld (hl),a
    inc hl
    ENDIF
    IF PB_TYPO
    ex de,hl
    ld hl,rt_ty_id              ; rt_ty_id, rt_ty_size, rt_ty_style
    ld bc,4
    ldir
    ENDIF
    ret
rt_cvm_load:
    call rt_cvm_slot
    IF PB_DWFONT
    ld a,(hl)
    or a
    jp nz,rt_cvm_ld_font
    ld a,7
rt_cvm_ld_font:
    ld (rt_dw_font),a
    inc hl
    ENDIF
    IF PB_TYPO
    ld de,rt_ty_id
    ld bc,4
    ldir
    ENDIF
    ret

; rt_cvm_slot — A = a canvas number: HL = its RT_CVM_S bytes of rt_cvm_state.
rt_cvm_slot:
    ld hl,rt_cvm_state
    ld de,RT_CVM_S
    or a
    ret z
rt_cvm_slot_k:
    add hl,de
    dec a
    jp nz,rt_cvm_slot_k
    ret

; rt_cvm_win_ok — A = a canvas's window byte: Z if that window is the one on
; screen (0: the program's only window). BC, DE, HL kept.
rt_cvm_win_ok:
    or a
    ret z
    IF PB_WINDOWS
    push hl
    ld hl,rt_win_cur
    cp (hl)
    pop hl
    ENDIF
    ret

; rt_cvm_mask — A = the canvases whose window is on screen (bit k = canvas k).
rt_cvm_mask:
    ld a,(cgcv_tab)
    ld b,a
    ld c,0
    ld e,1
    ld hl,cgcv_tab+1+15
rt_cvm_m_next:
    ld a,(hl)
    call rt_cvm_win_ok
    jp nz,rt_cvm_m_skip
    ld a,c
    or e
    ld c,a
rt_cvm_m_skip:
    push de
    ld de,RT_CVM_ROW
    add hl,de
    pop de
    sla e
    dec b
    jp nz,rt_cvm_m_next
    ld a,c
    ret

; rt_cvm_first — A = a mask: B = its lowest canvas, NC; C if A = 0.
rt_cvm_first:
    or a
    scf
    ret z
    ld b,0
rt_cvm_f_bit:
    rra
    jp c,rt_cvm_f_done
    inc b
    jp rt_cvm_f_bit
rt_cvm_f_done:
    or a
    ret

; rt_cvm_raw — a raw mouse event at screen DE, HL (kept): a press selects
; the canvas under it (and gives it the keyboard); movement and release the
; canvas pressed. C: no canvas (the DRAW ON target is current again).
rt_cvm_raw:
    push hl
    push de
    ld (rt_cvm_px),de
    ld (rt_cvm_py),hl
    ld a,(rt_cv_code+1)
    bit 0,a
    jp z,rt_cvm_raw_held
    call rt_cvm_mask
    ld (rt_cvm_m),a
    ld a,0FFh
    ld (rt_cvm_k),a
rt_cvm_raw_try:
    ld a,(rt_cvm_k)
    inc a
    ld (rt_cvm_k),a
    ld hl,rt_cvm_m
    srl (hl)
    jp c,rt_cvm_raw_test
    jp nz,rt_cvm_raw_try        ; more canvases on screen to try
    jp rt_cvm_raw_none
rt_cvm_raw_test:
    call rt_cvm_select
    ld de,(rt_cvm_px)
    ld hl,(rt_cvm_py)
    call rt_cv_local
    call rt_cv_inside
    jp c,rt_cvm_raw_next
    ld a,(rt_cvm_k)
    ld (rt_cvm_downk),a
    inc a
    ld (rt_cvm_focus),a
    or a
    jp rt_cvm_raw_out
rt_cvm_raw_next:
    ld a,(rt_cvm_m)
    or a
    jp nz,rt_cvm_raw_try
rt_cvm_raw_none:
    ld a,(rt_cvm_sel)
    call rt_cvm_select
    scf
    jp rt_cvm_raw_out
rt_cvm_raw_held:
    ld a,(rt_cv_down)
    or a
    scf
    jp z,rt_cvm_raw_out         ; no press on a canvas: not ours
    ld a,(rt_cvm_downk)
    call rt_cvm_select
    or a
rt_cvm_raw_out:
    pop de
    pop hl
    ret

; rt_cvm_keys — the keyboard's canvas current: FOCUS's or the last pressed
; if its window is on screen, else the first on screen. C: none.
rt_cvm_keys:
    ld a,(rt_cvm_focus)
    or a
    jp z,rt_cvm_k_first
    dec a
    ld b,a
    call rt_cvm_entry
    ld de,15
    add hl,de
    ld a,(hl)
    call rt_cvm_win_ok
    jp z,rt_cvm_k_this
rt_cvm_k_first:
    call rt_cvm_mask
    call rt_cvm_first
    ret c
rt_cvm_k_this:
    ld a,b
    call rt_cvm_select
    or a
    ret

; rt_cvm_oe_pick — an om_objevent: a click on a canvas's frame selects that
; canvas (and gives it the keyboard); any other event the keyboard's canvas.
; C: none.
rt_cvm_oe_pick:
    ld a,(rt_cv_on)
    or a
    scf
    ret z
    ld a,(rt_gui_evtype)
    cp 1
    jp nz,rt_cvm_keys
    call rt_cvm_mask
    ld c,a
    ld b,0
    ld hl,cgcv_tab+1+14
rt_cvm_oe_next:
    ld a,(cgcv_tab)
    cp b
    scf
    ret z                       ; no canvas's frame: another object
    srl c
    jp nc,rt_cvm_oe_skip
    ld a,(rt_gui_object)
    cp (hl)
    jp z,rt_cvm_oe_hit
rt_cvm_oe_skip:
    ld de,RT_CVM_ROW
    add hl,de
    inc b
    jp rt_cvm_oe_next
rt_cvm_oe_hit:
    ld a,b
    ld (rt_cvm_downk),a
    inc a
    ld (rt_cvm_focus),a
    ld a,b
    call rt_cvm_select
    or a
    ret
    ENDIF

; rt_cv_span — HL = start, DE = length, BC = limit: C unless 0 <= start,
; 0 <= length and start + length <= limit (all INTEGERs, so the sum of two
; non-negative values cannot wrap).
rt_cv_span:
    ld a,h
    or d
    and 80h
    jp nz,rt_cv_span_bad
    add hl,de
    ld a,c
    sub l
    ld a,b
    sbc a,h
    ret
rt_cv_span_bad:
    scf
    ret

; rt_cv_ready — stop with an error unless the canvas is on screen.
rt_cv_ready:
    ld a,(rt_cv_on)
    or a
    IF PB_CVMULTI
    jp z,rt_cv_ready_off
    ld a,(cgcanvas+15)          ; M15: the target's own window is the one on screen
    call rt_cvm_win_ok
    ret z
rt_cv_ready_off:
    ELSE
    ret nz
    ENDIF
    ld hl,rt_cv_off_text
    ld bc,rt_cv_off_text_end-rt_cv_off_text
    jp rt_err_msg

; rt_cv_rect — the rectangle x,y,w,h (rt_dw_args +0..+7) lies in the canvas.
rt_cv_rect:
    call rt_cv_ready
    ld hl,(rt_dw_args)
    ld de,(rt_dw_args+4)
    ld bc,(cgcanvas+4)
    call rt_cv_span
    jp c,rt_cv_outside
    ld hl,(rt_dw_args+2)
    ld de,(rt_dw_args+6)
    ld bc,(cgcanvas+6)
    call rt_cv_span
    jp c,rt_cv_outside
    ret

; rt_cv_point — the point HL, DE (x, y) lies in the canvas.
rt_cv_point:
    push de
    ld de,1
    ld bc,(cgcanvas+4)
    call rt_cv_span
    pop hl
    jp c,rt_cv_outside
    ld de,1
    ld bc,(cgcanvas+6)
    call rt_cv_span
    jp c,rt_cv_outside
    ret

rt_cv_outside:
    ld hl,rt_cv_out_text
    ld bc,rt_cv_out_text_end-rt_cv_out_text
    jp rt_err_msg

; rt_cv_dg — os_scr_direct function A on the rectangle in rt_dw_args, with
; rt_dg_buf+9.. already set by the caller.
; ROSAN283 says "out: A=0 OK, =1 error". Rosanne 1.12 reports the result in
; CARRY: each handler ends "ret c" on an error and "and a / ret" on success,
; and the r1call return passes the handler's AF back unchanged, so after a
; successful dg_blk_grey A holds the grey value [static: PCW045.SYS, OS
; block 6 #5DAC; XAnne: GFXPROBE stopped at shade 1 while A was tested].
rt_cv_dg:
    ld (rt_dg_buf),a
    ld hl,(rt_dw_args)
    ld de,(cgcanvas)
    add hl,de
    ld (rt_dg_buf+1),hl
    ld hl,(rt_dw_args+2)
    ld de,(cgcanvas+2)
    add hl,de
    ld (rt_dg_buf+3),hl
    ld hl,(rt_dw_args+4)
    ld (rt_dg_buf+5),hl
    ld hl,(rt_dw_args+6)
    ld (rt_dg_buf+7),hl
rt_cv_dg_call:
    call 0CBh
    ld c,a
    ld hl,rt_dg_buf
    ld a,117
    call 003Bh                  ; os_scr_direct
    ret nc                      ; the result is carry, not A (KI-46)
rt_cv_refused:
    ld hl,rt_cv_ref_text
    ld bc,rt_cv_ref_text_end-rt_cv_ref_text
    jp rt_err_msg

; rt_cv_empty — Z if the rectangle has no area (nothing to draw).
rt_cv_empty:
    ld hl,(rt_dw_args+4)
    ld a,h
    or l
    ret z
    ld hl,(rt_dw_args+6)
    ld a,h
    or l
    ret

; DRAW CLEAR — the whole canvas white.
rt_draw_clear:
    call rt_cv_ready
    ld hl,0
    ld (rt_dw_args),hl
    ld (rt_dw_args+2),hl
    ld hl,(cgcanvas+4)
    ld (rt_dw_args+4),hl
    ld hl,(cgcanvas+6)
    ld (rt_dw_args+6),hl
    ld a,1                      ; dg_blk_white
    jp rt_cv_dg

; DRAW FILL x, y, w, h [, shade] — shade (+8) 0 black .. 8 white.
rt_draw_fill:
    call rt_cv_rect
    ld hl,(rt_dw_args+8)
    ld a,h
    or a
    jp nz,rt_cv_bad_shade
    ld a,l
    cp 9
    jp nc,rt_cv_bad_shade
    call rt_cv_empty
    ret z
    ld a,(rt_dw_args+8)
    cp 8
    jp z,rt_cv_fill_white
    ld (rt_dg_buf+9),a
    ld a,3                      ; dg_blk_grey
    jp rt_cv_dg
; Shade 8 is dg_blk_white. ROSAN283 lists grey 0..8 for dg_blk_grey, but
; Rosanne 1.12 refuses 8 (its handler returns carry for a grey value >= 8;
; it has 8 patterns, 0..7) [static: PCW045.SYS; XAnne: MDEDIT line 79].
rt_cv_fill_white:
    ld a,1                      ; dg_blk_white
    jp rt_cv_dg
rt_cv_bad_shade:
    ld hl,rt_cv_shade_text
    ld bc,rt_cv_shade_text_end-rt_cv_shade_text
    jp rt_err_msg

; DRAW INVERT x, y, w, h — XOR with black (grey value 0) flips every pixel.
rt_draw_invert:
    call rt_cv_rect
    call rt_cv_empty
    ret z
    xor a
    ld (rt_dg_buf+9),a
    ld a,4                      ; dg_blk_grey_xor
    jp rt_cv_dg

; DRAW SCROLL x, y, w, h, dx, dy — the rectangle's contents move by dx, dy
; (|dx| < w, |dy| < h); what falls outside it is lost, the strip uncovered
; is cleared white. dg_blk_copy of the part that stays, then dg_blk_white.
rt_draw_scroll:
    call rt_cv_rect
    ld hl,(rt_dw_args+8)
    ld de,(rt_dw_args+4)
    call rt_cv_shift_ok
    ld hl,(rt_dw_args+10)
    ld de,(rt_dw_args+6)
    call rt_cv_shift_ok
    ld hl,(rt_dw_args+8)
    ld a,h
    or l
    ld hl,(rt_dw_args+10)
    or h
    or l
    ret z                       ; no movement
    ; source and destination of the copy, sizes reduced by |dx|, |dy|
    ld hl,(rt_dw_args)
    ld (rt_cv_sx),hl
    ld (rt_cv_dx),hl
    ld hl,(rt_dw_args+2)
    ld (rt_cv_sy),hl
    ld (rt_cv_dy),hl
    ld hl,(rt_dw_args+8)        ; x: copy width w - |dx|; dx > 0 moves the
    call rt_cv_abs              ; destination right, dx < 0 the source
    ex de,hl
    ld hl,(rt_dw_args+4)
    or a
    sbc hl,de
    ld (rt_cv_cw),hl
    ld a,(rt_cv_wasneg)
    or a
    ld hl,(rt_cv_dx)
    jp z,rt_cv_scroll_dx
    ld hl,(rt_cv_sx)
    add hl,de
    ld (rt_cv_sx),hl
    jp rt_cv_scroll_y
rt_cv_scroll_dx:
    add hl,de
    ld (rt_cv_dx),hl
rt_cv_scroll_y:
    ld hl,(rt_dw_args+10)       ; y, the same way
    call rt_cv_abs
    ex de,hl
    ld hl,(rt_dw_args+6)
    or a
    sbc hl,de
    ld (rt_cv_ch),hl
    ld a,(rt_cv_wasneg)
    or a
    ld hl,(rt_cv_dy)
    jp z,rt_cv_scroll_dy
    ld hl,(rt_cv_sy)
    add hl,de
    ld (rt_cv_sy),hl
    jp rt_cv_scroll_copy
rt_cv_scroll_dy:
    add hl,de
    ld (rt_cv_dy),hl
rt_cv_scroll_copy:
    ; the copy: rect = source, x2,y2 = destination (screen)
    ld hl,(rt_cv_sx)
    ld de,(cgcanvas)
    add hl,de
    ld (rt_dg_buf+1),hl
    ld hl,(rt_cv_sy)
    ld de,(cgcanvas+2)
    add hl,de
    ld (rt_dg_buf+3),hl
    ld hl,(rt_cv_cw)
    ld (rt_dg_buf+5),hl
    ld hl,(rt_cv_ch)
    ld (rt_dg_buf+7),hl
    ld hl,(rt_cv_dx)
    ld de,(cgcanvas)
    add hl,de
    ld (rt_dg_buf+9),hl
    ld hl,(rt_cv_dy)
    ld de,(cgcanvas+2)
    add hl,de
    ld (rt_dg_buf+11),hl
    ld a,10                     ; dg_blk_copy
    ld (rt_dg_buf),a
    call rt_cv_dg_call
    ; the uncovered strips: horizontal movement, then vertical
    ld hl,(rt_dw_args+8)
    ld a,h
    or l
    jp z,rt_cv_scroll_v
    ld hl,(rt_dw_args)
    ld (rt_cv_fx),hl
    ld hl,(rt_dw_args+2)
    ld (rt_cv_fy),hl
    ld hl,(rt_dw_args+6)
    ld (rt_cv_fh),hl
    ld hl,(rt_dw_args+8)
    bit 7,h
    jp z,rt_cv_scroll_hr
    ld de,(rt_dw_args+4)        ; dx < 0: the right edge, -dx wide
    add hl,de
    ld de,(rt_dw_args)
    add hl,de
    ld (rt_cv_fx),hl
    ld hl,(rt_dw_args+8)
    call rt_cv_neg
rt_cv_scroll_hr:
    ld (rt_cv_fw),hl
    call rt_cv_white
rt_cv_scroll_v:
    ld hl,(rt_dw_args+10)
    ld a,h
    or l
    ret z
    ld hl,(rt_dw_args)
    ld (rt_cv_fx),hl
    ld hl,(rt_dw_args+2)
    ld (rt_cv_fy),hl
    ld hl,(rt_dw_args+4)
    ld (rt_cv_fw),hl
    ld hl,(rt_dw_args+10)
    bit 7,h
    jp z,rt_cv_scroll_vd
    ld de,(rt_dw_args+6)        ; dy < 0: the bottom edge, -dy high
    add hl,de
    ld de,(rt_dw_args+2)
    add hl,de
    ld (rt_cv_fy),hl
    ld hl,(rt_dw_args+10)
    call rt_cv_neg
rt_cv_scroll_vd:
    ld (rt_cv_fh),hl
; rt_cv_white — dg_blk_white on rt_cv_fx, fy, fw, fh (canvas-relative).
rt_cv_white:
    ld hl,(rt_cv_fx)
    ld de,(cgcanvas)
    add hl,de
    ld (rt_dg_buf+1),hl
    ld hl,(rt_cv_fy)
    ld de,(cgcanvas+2)
    add hl,de
    ld (rt_dg_buf+3),hl
    ld hl,(rt_cv_fw)
    ld (rt_dg_buf+5),hl
    ld hl,(rt_cv_fh)
    ld (rt_dg_buf+7),hl
    ld a,1
    ld (rt_dg_buf),a
    jp rt_cv_dg_call

; rt_cv_neg — HL = -HL. Keeps DE.
rt_cv_neg:
    push de
    ex de,hl
    ld hl,0
    or a
    sbc hl,de
    pop de
    ret

; rt_cv_shift_ok — |HL| < DE (DE > 0), else the drawing error.
rt_cv_shift_ok:
    bit 7,h
    call nz,rt_cv_neg
    or a
    sbc hl,de
    ret c
    jp rt_cv_outside

; rt_cv_abs — HL = |HL|; rt_cv_wasneg = 1 if it was negative, else 0.
rt_cv_abs:
    xor a
    bit 7,h
    jp z,rt_cv_abs_done
    call rt_cv_neg
    ld a,1
rt_cv_abs_done:
    ld (rt_cv_wasneg),a
    ret

; rt_cv_bios — A = 0 bios_pixel (DE, HL = x, y from rt_bios_par), 1
; bios_line, 2 bios_rectang (HL -> rt_bios_par): run it with the mouse
; pointer hidden and the program's ink and mode, then put the old ones back.
rt_cv_bios:
    ld (rt_cv_bios_op),a
    ld a,111
    call 003Bh                  ; os_mouse_off
    call 0E3h                   ; bios_getink
    ld (rt_cv_oldink),a
    call 0E9h                   ; bios_getmode
    ld (rt_cv_oldmode),a
    ld a,(rt_dw_ink)            ; 0 black, 1 white, 2 XOR (black ink, mode 3)
    cp 2
    jp z,rt_cv_bios_xor
    call 0E0h                   ; bios_setink
    xor a
    jp rt_cv_bios_mode
rt_cv_bios_xor:
    xor a
    call 0E0h
    ld a,3
rt_cv_bios_mode:
    call 0E6h                   ; bios_setmode
    ld a,(rt_cv_bios_op)
    or a
    jp nz,rt_cv_bios_ptr
    ld de,(rt_bios_par)
    ld hl,(rt_bios_par+2)
    call 0F2h                   ; bios_pixel
    jp rt_cv_bios_back
rt_cv_bios_ptr:
    ld hl,rt_bios_par
    cp 1
    jp nz,rt_cv_bios_rect
    IF PB_CVLINE
    call rt_cv_line
    ELSE
    call 0F8h                   ; bios_line (not reached: no DRAW LINE)
    ENDIF
    jp rt_cv_bios_back
rt_cv_bios_rect:
    call 0FBh                   ; bios_rectang
rt_cv_bios_back:
    ld a,(rt_cv_oldmode)
    call 0E6h
    ld a,(rt_cv_oldink)
    call 0E0h
    ld a,112
    call 003Bh                  ; os_mouse_on
    ret

    IF PB_CVLINE
; rt_cv_line — the line rt_bios_par x1, y1, x2, y2 (screen) in the ink and
; mode already set. Rosanne 1.12's bios_line draws only horizontal and
; vertical lines: with x1 <> x2 and y1 <> y2 it returns without drawing
; [static: PCW045.SYS bios_line #0FB5; XAnne: the GFXPROBE diagonal was
; missing, KI-49]. A sloped line is therefore drawn as runs along its major
; axis, one bios_line each, chosen by Bresenham's rule, so each pixel is
; set exactly once (XOR stays correct) and both ends are included.
rt_cv_line:
    ld hl,(rt_bios_par)
    ld (rt_ln_x),hl
    ld de,(rt_bios_par+4)
    or a
    sbc hl,de
    jp z,rt_cv_line_one         ; vertical
    ld hl,(rt_bios_par+2)
    ld (rt_ln_y),hl
    ld de,(rt_bios_par+6)
    or a
    sbc hl,de
    jp nz,rt_cv_line_runs
rt_cv_line_one:
    ld hl,rt_bios_par
    call 0F8h                   ; bios_line
    ret
rt_cv_line_runs:
    ld hl,(rt_bios_par+4)       ; dx = |x2 - x1|, step +-1
    ld de,(rt_ln_x)
    call rt_cv_line_d
    ld (rt_ln_dx),hl
    ld (rt_ln_sx),bc
    ld hl,(rt_bios_par+6)       ; dy = |y2 - y1|, step +-1
    ld de,(rt_ln_y)
    call rt_cv_line_d
    ld (rt_ln_dy),hl
    ld (rt_ln_sy),bc
    ld de,(rt_ln_dx)            ; major axis: x if dy <= dx, else y
    or a
    sbc hl,de
    jp c,rt_cv_line_xmaj
    jp z,rt_cv_line_xmaj
    xor a
    ld hl,(rt_ln_y)
    ld (rt_ln_maj),hl
    ld hl,(rt_bios_par+6)
    ld (rt_ln_end),hl
    ld hl,(rt_ln_sy)
    ld (rt_ln_mstep),hl
    ld hl,(rt_ln_x)
    ld (rt_ln_min),hl
    ld hl,(rt_ln_sx)
    ld (rt_ln_nstep),hl
    ld hl,(rt_ln_dy)
    ld de,(rt_ln_dx)
    jp rt_cv_line_go
rt_cv_line_xmaj:
    ld a,1
    ld hl,(rt_ln_x)
    ld (rt_ln_maj),hl
    ld hl,(rt_bios_par+4)
    ld (rt_ln_end),hl
    ld hl,(rt_ln_sx)
    ld (rt_ln_mstep),hl
    ld hl,(rt_ln_y)
    ld (rt_ln_min),hl
    ld hl,(rt_ln_sy)
    ld (rt_ln_nstep),hl
    ld hl,(rt_ln_dx)
    ld de,(rt_ln_dy)
rt_cv_line_go:                  ; A = 1 x-major; HL = dmaj, DE = dmin
    ld (rt_ln_xmaj),a
    add hl,hl
    ld (rt_ln_dmaj2),hl
    ex de,hl
    add hl,hl
    ld (rt_ln_dmin2),hl
    ld de,(rt_ln_dmaj2)         ; err = 2 dmin - dmaj
    srl d
    rr e
    or a
    sbc hl,de
    ld (rt_ln_err),hl
    ld hl,(rt_ln_maj)
    ld (rt_ln_run),hl
rt_cv_line_loop:                ; pixel (maj, min) is in the current run
    ld hl,(rt_ln_maj)
    ld de,(rt_ln_end)
    or a
    sbc hl,de
    jp z,rt_cv_line_emit        ; the last pixel: the last run
    ld hl,(rt_ln_err)
    bit 7,h
    jp nz,rt_cv_line_step
    ld a,h
    or l
    jp z,rt_cv_line_step
    call rt_cv_line_emit        ; err > 0: the minor axis steps after it
    ld hl,(rt_ln_min)
    ld de,(rt_ln_nstep)
    add hl,de
    ld (rt_ln_min),hl
    ld hl,(rt_ln_err)
    ld de,(rt_ln_dmaj2)
    or a
    sbc hl,de
    ld (rt_ln_err),hl
    ld hl,(rt_ln_maj)
    ld de,(rt_ln_mstep)
    add hl,de
    ld (rt_ln_run),hl
rt_cv_line_step:
    ld hl,(rt_ln_err)
    ld de,(rt_ln_dmin2)
    add hl,de
    ld (rt_ln_err),hl
    ld hl,(rt_ln_maj)
    ld de,(rt_ln_mstep)
    add hl,de
    ld (rt_ln_maj),hl
    jp rt_cv_line_loop
; rt_cv_line_emit — bios_line from (run, min) to (maj, min), axes as set.
rt_cv_line_emit:
    ld hl,(rt_ln_run)
    ld de,(rt_ln_maj)
    ld bc,(rt_ln_min)
    ld a,(rt_ln_xmaj)
    or a
    jp z,rt_cv_line_emit_v
    ld (rt_bios_par),hl
    ld (rt_bios_par+2),bc
    ld (rt_bios_par+4),de
    ld (rt_bios_par+6),bc
    ld hl,rt_bios_par
    call 0F8h
    ret
rt_cv_line_emit_v:
    ld (rt_bios_par),bc
    ld (rt_bios_par+2),hl
    ld (rt_bios_par+4),bc
    ld (rt_bios_par+6),de
    ld hl,rt_bios_par
    call 0F8h
    ret
; rt_cv_line_d — HL = |HL - DE|, BC = +1 if HL >= DE else -1.
rt_cv_line_d:
    or a
    sbc hl,de
    ld bc,1
    bit 7,h
    ret z
    ld bc,0FFFFh
    jp rt_cv_neg
    ENDIF

; rt_cv_par — rt_bios_par = screen x, y of canvas point HL, DE (at +0, +2)
; or BC = offset +4 for a second point.
rt_cv_par:
    push bc
    push de
    ld de,(cgcanvas)
    add hl,de
    ex de,hl
    ld hl,rt_bios_par
    add hl,bc
    ld (hl),e
    inc hl
    ld (hl),d
    inc hl
    pop de
    push hl
    ld hl,(cgcanvas+2)
    add hl,de
    ex de,hl
    pop hl
    ld (hl),e
    inc hl
    ld (hl),d
    pop bc
    ret

; DRAW PIXEL x, y
rt_draw_pixel:
    call rt_cv_ready
    ld hl,(rt_dw_args)
    ld de,(rt_dw_args+2)
    call rt_cv_point
    ld hl,(rt_dw_args)
    ld de,(rt_dw_args+2)
    ld bc,0
    call rt_cv_par
    xor a                       ; bios_pixel
    jp rt_cv_bios

; DRAW LINE x1, y1, x2, y2 — both ends inside the canvas.
rt_draw_line:
    call rt_cv_ready
    ld hl,(rt_dw_args)
    ld de,(rt_dw_args+2)
    call rt_cv_point
    ld hl,(rt_dw_args+4)
    ld de,(rt_dw_args+6)
    call rt_cv_point
    ld hl,(rt_dw_args)
    ld de,(rt_dw_args+2)
    ld bc,0
    call rt_cv_par
    ld hl,(rt_dw_args+4)
    ld de,(rt_dw_args+6)
    ld bc,4
    call rt_cv_par
    ld a,1                      ; bios_line
    jp rt_cv_bios

; DRAW BOX x, y, w, h — an outline; w and h at least 1.
rt_draw_box:
    call rt_cv_rect
    call rt_cv_empty
    ret z
    ld hl,(rt_dw_args)
    ld de,(rt_dw_args+2)
    ld bc,0
    call rt_cv_par
    ld hl,(rt_dw_args+4)
    ld (rt_bios_par+4),hl
    ld hl,(rt_dw_args+6)
    ld (rt_bios_par+6),hl
    ld a,2                      ; bios_rectang
    jp rt_cv_bios

; DRAW TEXT x, y, s$ (HL = the text) — font 7 from the top-left x, y, which
; must lie in the canvas with a whole line (RT_CV_TEXT_H) below it. Only as
; many characters are drawn as are certain to fit before the right edge at
; RT_CV_CHAR_W pixels each (no width call works in XAnne: M5d WIDTHDG).
; Characters outside 32..223 are drawn as '?' (Rosanne reserves 0-31 and
; E0-FF for control codes, ROSAN283 "The Text System").
rt_draw_text:
    push hl
    call rt_cv_ready
    ld hl,(rt_dw_args)
    ld de,1
    ld bc,(cgcanvas+4)
    call rt_cv_span
    jp c,rt_cv_outside
    ld hl,(rt_dw_args+2)
    ld de,RT_CV_TEXT_H
    ld bc,(cgcanvas+6)
    call rt_cv_span
    jp c,rt_cv_outside
    IF PB_DWFONT
    ld b,127                    ; M15: all of it; rt_cv_text_fit measures what fits
    ELSE
    ld hl,(cgcanvas+4)          ; room = (width - x) / RT_CV_CHAR_W
    ld de,(rt_dw_args)
    or a
    sbc hl,de
    ld de,RT_CV_CHAR_W
    ld b,0
rt_cv_text_room:
    or a
    sbc hl,de
    jp c,rt_cv_text_roomed
    inc b
    ld a,b
    cp 127
    jp c,rt_cv_text_room
    ENDIF
rt_cv_text_roomed:
    IF PB_DWFONT
    ld a,(rt_dw_font)           ; M15: DRAW FONT n (1..12; 7 until one is chosen)
    ELSE
    ld a,7
    ENDIF
    ld (rt_ds_buf),a            ; font 7
    xor a
    ld (rt_ds_buf+1),a          ; left-aligned
    ld (rt_ds_buf+2),a          ; style 0
    ld a,(rt_dw_ink)
    cp 2
    ld a,0
    jp nz,rt_cv_text_mode
    ld a,3                      ; XOR
rt_cv_text_mode:
    ld (rt_ds_buf+3),a
    ld hl,(rt_dw_args)
    ld de,(cgcanvas)
    add hl,de
    ld (rt_ds_buf+4),hl
    ld hl,(rt_dw_args+2)
    ld de,(cgcanvas+2)
    add hl,de
    ld (rt_ds_buf+6),hl
    pop hl
    ld de,rt_ds_buf+8
rt_cv_text_copy:
    ld a,b
    or a
    jp z,rt_cv_text_end
    ld a,(hl)
    or a
    jp z,rt_cv_text_end
    cp 32
    jp c,rt_cv_text_odd
    cp 0E0h
    jp c,rt_cv_text_put
rt_cv_text_odd:
    ld a,'?'
rt_cv_text_put:
    ld (de),a
    inc hl
    inc de
    dec b
    jp rt_cv_text_copy
rt_cv_text_end:
    xor a
    ld (de),a
    IF PB_DWFONT
    call rt_cv_text_fit         ; M15: cut where it stops fitting, by measuring
    ENDIF
    ld a,111
    call 003Bh                  ; os_mouse_off
    call 0CBh
    ld c,a
    ld hl,rt_ds_buf
    ld a,81
    call 003Bh                  ; os_dialog_string
    push af
    ld a,112
    call 003Bh                  ; os_mouse_on
    pop af
    jp c,rt_cv_refused
    ret

    IF PB_CVCELL
; DRAW TEXT x, y, s$, cell (M11; HL = the text, rt_dw_args+4 = cell) — each
; character drawn on its own with font 7 at x + i * cell, so that columns
; line up and a caret or a selection can be shown exactly with DRAW INVERT
; over whole cells: Rosanne's fonts are proportional ("The Text System") and
; no width call works in XAnne (M5d WIDTHDG). cell is 11 (RT_CV_CHAR_W, the
; widest glyph) .. 64, so no glyph reaches into the next cell. As for DRAW
; TEXT: x, y and a whole line below y must lie in the canvas; only the
; characters whose cells fit before the right edge are drawn; characters
; outside 32..223 are drawn as '?'. A space is not drawn: its cell is left
; as it is. The mouse pointer is hidden once for the whole text.
rt_draw_cells:
    push hl
    call rt_cv_ready
    ld hl,(rt_dw_args+4)
    ld de,RT_CV_CHAR_W
    or a
    sbc hl,de
    jp c,rt_cv_cell_bad
    ld de,64-RT_CV_CHAR_W+1
    or a
    sbc hl,de
    jp nc,rt_cv_cell_bad
    ld hl,(rt_dw_args)
    ld de,1
    ld bc,(cgcanvas+4)
    call rt_cv_span
    jp c,rt_cv_outside
    ld hl,(rt_dw_args+2)
    ld de,RT_CV_TEXT_H
    ld bc,(cgcanvas+6)
    call rt_cv_span
    jp c,rt_cv_outside
    ld hl,(cgcanvas+4)          ; cells = (width - x) / cell
    ld de,(rt_dw_args)
    or a
    sbc hl,de
    ld de,(rt_dw_args+4)
    ld b,0
rt_cv_cell_room:
    or a
    sbc hl,de
    jp c,rt_cv_cell_roomed
    inc b
    ld a,b
    cp 127
    jp c,rt_cv_cell_room
rt_cv_cell_roomed:
    ld a,b
    ld (rt_cv_cell_n),a
    ld a,7
    ld (rt_ds_buf),a            ; font 7
    xor a
    ld (rt_ds_buf+1),a          ; left-aligned
    ld (rt_ds_buf+2),a          ; style 0
    ld (rt_ds_buf+9),a          ; one character, then its NUL
    ld a,(rt_dw_ink)
    cp 2
    ld a,0
    jp nz,rt_cv_cell_mode
    ld a,3                      ; XOR
rt_cv_cell_mode:
    ld (rt_ds_buf+3),a
    ld hl,(rt_dw_args)
    ld de,(cgcanvas)
    add hl,de
    ld (rt_ds_buf+4),hl
    ld hl,(rt_dw_args+2)
    ld de,(cgcanvas+2)
    add hl,de
    ld (rt_ds_buf+6),hl
    pop hl
    ld (rt_cv_cell_p),hl
    ld a,111
    call 003Bh                  ; os_mouse_off
rt_cv_cell_next:
    ld a,(rt_cv_cell_n)
    or a
    jp z,rt_cv_cell_done
    dec a
    ld (rt_cv_cell_n),a
    ld hl,(rt_cv_cell_p)
    ld a,(hl)
    or a
    jp z,rt_cv_cell_done
    inc hl
    ld (rt_cv_cell_p),hl
    cp ' '
    jp z,rt_cv_cell_step
    cp 32
    jp c,rt_cv_cell_odd
    cp 0E0h
    jp c,rt_cv_cell_put
rt_cv_cell_odd:
    ld a,'?'
rt_cv_cell_put:
    ld (rt_ds_buf+8),a
    call 0CBh
    ld c,a
    ld hl,rt_ds_buf
    ld a,81
    call 003Bh                  ; os_dialog_string (AF, BC, DE, HL corrupt)
    jp c,rt_cv_cell_refused
rt_cv_cell_step:
    ld hl,(rt_ds_buf+4)         ; the next cell
    ld de,(rt_dw_args+4)
    add hl,de
    ld (rt_ds_buf+4),hl
    jp rt_cv_cell_next
rt_cv_cell_done:
    ld a,112
    call 003Bh                  ; os_mouse_on
    ret
rt_cv_cell_refused:
    ld a,112
    call 003Bh                  ; os_mouse_on
    jp rt_cv_refused
rt_cv_cell_bad:
    ld hl,rt_cv_cell_text
    ld bc,rt_cv_cell_text_end-rt_cv_cell_text
    jp rt_err_msg
rt_cv_cell_text:
    db "Runtime error: a text cell is 11 to 64 pixels at line "
rt_cv_cell_text_end:
    ENDIF

rt_cv_off_text:
    db "Runtime error: the canvas is not on screen at line "
rt_cv_off_text_end:
rt_cv_out_text:
    db "Runtime error: drawing outside the canvas at line "
rt_cv_out_text_end:
rt_cv_shade_text:
    db "Runtime error: a shade is 0 to 8 at line "
rt_cv_shade_text_end:
rt_cv_ref_text:
    db "Runtime error: Rosanne refused a drawing at line "
rt_cv_ref_text_end:

    IF PB_DWFONT
; ----------------------------------------------------------------------------
; M15 DRAW FONT n (LANGUAGE-SPEC 5.6): the dialog font of later DRAW TEXT and
; TEXTWIDTH, 1..12 (owner XAnne, M15a T1/T2: all twelve draw). In such a
; program DRAW TEXT measures what fits before the right edge with
; os_dialog_string_width (82: HL = the width; its carry is not used, M5d
; WIDTHDG) instead of the RC1 rule of RT_CV_CHAR_W pixels a character.
; ----------------------------------------------------------------------------
rt_draw_font:
    ld hl,(rt_dw_args)
    dec hl
    ld de,12
    or a
    sbc hl,de
    jp nc,rt_dw_font_bad        ; 0 or over 12 (or negative)
    ld a,(rt_dw_args)
    ld (rt_dw_font),a
    ret
rt_dw_font_bad:
    ld hl,rt_dw_font_text
    ld bc,rt_dw_font_end-rt_dw_font_text
    jp rt_err_msg
rt_dw_font_text:
    db "Runtime error: a font is 1 to 12 at line "
rt_dw_font_end:

; rt_cv_tw — HL = the width of the text in rt_ds_buf (its font) in pixels
rt_cv_tw:
    call 0CBh                   ; bios_getmem1: the block holding rt_ds_buf
    ld c,a
    ld hl,rt_ds_buf
    ld a,82
    call 003Bh                  ; os_dialog_string_width
    ret

; rt_cv_text_fit — rt_ds_buf holds the whole text, DE at its NUL. With ALIGN
; (rt_dw_align 1 centre, 2 right) the left edge moves left by half or all of
; the width (not past the canvas's left edge). Then the text is cut to the
; longest start that fits before the right edge (a binary search on the
; length, the NUL moved).
rt_cv_text_fit:
    ld hl,rt_ds_buf+8
    ex de,hl
    or a
    sbc hl,de
    ld a,l
    ld (rt_dw_len),a            ; the length, 0..127
    IF PB_DWALIGN
    ld a,(rt_dw_align)
    or a
    jp z,rt_cv_fit_x
    ld b,a
    xor a
    ld (rt_dw_align),a          ; one DRAW TEXT only
    push bc
    call rt_cv_tw
    pop bc
    dec b
    jp nz,rt_cv_fit_all         ; 2: right, the whole width
    srl h                       ; 1: centre, half of it
    rr l
rt_cv_fit_all:
    ex de,hl
    ld hl,(rt_dw_args)
    or a
    sbc hl,de
    jp nc,rt_cv_fit_left
    ld hl,0                     ; not past the left edge
rt_cv_fit_left:
    ld (rt_dw_args),hl
    ld de,(cgcanvas)
    add hl,de
    ld (rt_ds_buf+4),hl
    ENDIF
rt_cv_fit_x:
    ld hl,(cgcanvas+4)          ; room = width - x
    ld de,(rt_dw_args)
    or a
    sbc hl,de
    ld (rt_dw_room),hl
    ld a,(rt_ds_buf)
    cp 7
    jp z,rt_cv_fit_room         ; font 7: its widths match the drawn text (M11, RENDPRB)
    ld hl,(rt_ds_buf+8)         ; M15c F3 (XAnne): other fonts' ink may pass the
    push hl                     ; measured end, so half a W + 1 px is kept free
    ld hl,'W'                   ; "W", 0 measured in place of the text
    ld (rt_ds_buf+8),hl
    call rt_cv_tw
    pop de
    ld (rt_ds_buf+8),de
    srl h
    rr l
    inc hl
    ex de,hl
    ld hl,(rt_dw_room)
    or a
    sbc hl,de
    jp nc,rt_cv_fit_keep
    ld hl,0
rt_cv_fit_keep:
    ld (rt_dw_room),hl
rt_cv_fit_room:
    call rt_cv_tw
    call rt_cv_fits
    ret nc                      ; all of it fits
    xor a
    ld (rt_dw_lo),a             ; a start of lo characters fits, of hi does not
    ld a,(rt_dw_len)
    ld (rt_dw_hi),a
rt_cv_fit_step:
    ld a,(rt_dw_lo)
    ld b,a
    ld a,(rt_dw_hi)
    sub b
    cp 2
    jp c,rt_cv_fit_done
    srl a
    add a,b                     ; mid
    ld (rt_dw_mid),a
    ld e,a
    ld d,0
    ld hl,rt_ds_buf+8
    add hl,de
    ld a,(hl)
    ld (rt_dw_save),a
    ld (hl),0
    push hl
    call rt_cv_tw
    call rt_cv_fits
    pop hl
    ld a,(rt_dw_save)
    ld (hl),a
    ld a,(rt_dw_mid)
    jp c,rt_cv_fit_hi
    ld (rt_dw_lo),a
    jp rt_cv_fit_step
rt_cv_fit_hi:
    ld (rt_dw_hi),a
    jp rt_cv_fit_step
rt_cv_fit_done:
    ld a,(rt_dw_lo)
    ld e,a
    ld d,0
    ld hl,rt_ds_buf+8
    add hl,de
    ld (hl),0
    ret

; rt_cv_fits — NC if HL (a width) <= rt_dw_room, else C
rt_cv_fits:
    ex de,hl
    ld hl,(rt_dw_room)
    or a
    sbc hl,de
    ret
    ENDIF
    ENDIF

    IF PB_BITMAP
; ============================================================================
; M12 BITMAPs (LANGUAGE-SPEC §5.12): rectangles of the screen kept in one
; 16K block the program owns (a slot of the M8 block list, like a TEXT
; buffer), captured from the canvas and drawn back with the BIOS bitmap
; calls, and saved to / loaded from a PBI1 file (docs/M12-ARCHITECTURE.md).
; ROSAN283 BIOS table (call #80 + 3 x n):
;   bios_getpxl #27 (#F5): "in: DE = x, HL = y; out: A = 0 (black) or 1
;     (white); F, HL corrupt";
;   bios_plotbitmap #2E (#10A): "in: HL = 16-bit address of bitmap data: +0
;     x coord, +2 y coord, +4 width in pxls, +6 height in pxls, +8 24-bit
;     address of data; out: AF, BC, DE, HL corrupt";
;   bios_getbitmap #31 (#113): "get screen bitmap to memory. in: HL = addr
;     of 4 words x,y,w,h; DE = 16-bit address of buffer to put ((width+7)
;     DIV 8)*height bytes of data". [static] its code copies the rows to the
;     24-bit address at +8..+10 of the block, as plotbitmap reads them, so
;     the runtime gives both: DE and +8..+10 name the same buffer.
; [static: PCW045.SYS] the screen is 80 bytes a row (640 pixels), bit 7
; leftmost, a set bit white (bios_getpxl returns the bit; mask table at
; #0400 = 80 40 .. 01); bios_getbitmap (#1231) and bios_plotbitmap (#1226)
; are one blitter entered with A = 0 (screen to memory) or 1 (memory to
; screen). Their 16-bit inputs are read through the current memory map, so
; the parameters (RT_BMP_PAR) and the capture strip (RT_BMP_BUF) are in
; the program's part of the bottom quarter (ROSAN283 "AP may use
; #2000...#2FFF"; #2C00..#2FFF is otherwise unused: menus #2400..#2BFF,
; drawing parameters #2200, file names #2100..#21C7). The BIOS does not hide
; the mouse pointer: os_mouse_off / os_mouse_on bracket each use.
; A bitmap's data: (width + 7) \ 8 bytes a row, rows top to bottom, from
; offset 0 of its block, as bios_getbitmap writes them.
; Record (generated, 8 bytes at var_NAME): +0 capacity in bytes, +2 block
; slot, +3 0, +4 width, +6 height (the current size: the DIM size, then
; that of the last GET or LOAD).
; ----------------------------------------------------------------------------
RT_BMP_PAR equ 2208h            ; 14 bytes: the BIOS bitmap parameters (M13: +11 a mask)
RT_BMP_BUF equ 2C00h          ; 1024 bytes: rows captured in one call

; rt_bmp_blk — HL = record: A = its block (rt_bank_list[slot]). Keeps HL.
rt_bmp_blk:
    push hl
    inc hl
    inc hl
    ld e,(hl)
    ld d,0
    ld hl,rt_bank_list
    add hl,de
    ld a,(hl)
    pop hl
    ret

; rt_bmp_white — HL = record: every byte of its block #FF (white).
rt_bmp_white:
    call rt_bmp_blk
    ld (rt_bk_blk),a
    ld hl,RT_BMP_BUF
    ld de,RT_BMP_BUF+1
    ld bc,1023
    ld (hl),0FFh
    ldir
    ld hl,1024
    ld (rt_bk_size),hl
    ld hl,0
rt_bmp_white_part:
    ld (rt_bk_off),hl
    ex de,hl
    ld a,(rt_bk_blk)
    ld b,a
    ld c,80h                    ; the bottom quarter's block
    ld hl,RT_BMP_BUF
    call rt_bk_copy
    ld hl,(rt_bk_off)
    ld de,1024
    add hl,de
    ld a,h
    cp 40h
    jp c,rt_bmp_white_part
    ret

; rt_bmp_bpr — HL = width: HL = bytes a row, (width + 7) \ 8.
rt_bmp_bpr:
    ld de,7
    add hl,de
    srl h
    rr l
    srl h
    rr l
    srl h
    rr l
    ret

    IF PB_CANVAS
; rt_bmp_get — BITMAP GET: HL = record, rt_dw_args = x, y, w, h (canvas).
; The rectangle must lie in the canvas, and its bytes fit the bitmap.
rt_bmp_get:
    ld (rt_bmp_rec),hl
    call rt_cv_rect
    ld hl,(rt_dw_args+4)
    call rt_bmp_bpr
    ld (rt_bmp_rowb),hl
    ex de,hl
    ld hl,(rt_dw_args+6)
    call rt_mul16               ; HL = bytes
    ex de,hl
    ld hl,(rt_bmp_rec)
    ld a,(hl)
    inc hl
    ld h,(hl)
    ld l,a                      ; HL = capacity
    or a
    sbc hl,de
    jp c,rt_bmp_big
    ld hl,(rt_bmp_rec)
    call rt_bmp_blk
    ld (rt_bk_blk),a
    call rt_cv_empty
    jp z,rt_bmp_got
    ld hl,(rt_bmp_rowb)         ; rows a strip: 1024 \ bytes a row
    ex de,hl
    ld hl,1024
    ld bc,0                     ; 16 bits: a 1-byte row makes 1024 rows
rt_bmp_k:
    or a
    sbc hl,de
    jp c,rt_bmp_k_done
    inc bc
    jp rt_bmp_k
rt_bmp_k_done:
    ld (rt_bmp_k_n),bc
    ld hl,0
    ld (rt_bmp_row),hl
    ld (rt_bk_off),hl
    ld a,111
    call 003Bh                  ; os_mouse_off
rt_bmp_strip:
    ld hl,(rt_dw_args+6)
    ld de,(rt_bmp_row)
    or a
    sbc hl,de                   ; rows left
    jp z,rt_bmp_strips_done
    ld de,(rt_bmp_k_n)
    push hl
    or a
    sbc hl,de
    pop hl
    jp c,rt_bmp_n
    ex de,hl                    ; a whole strip
rt_bmp_n:
    ld (rt_bmp_rows),hl
    ld (RT_BMP_PAR+6),hl
    ld hl,(rt_dw_args)
    ld de,(cgcanvas)
    add hl,de
    ld (RT_BMP_PAR),hl
    ld hl,(rt_dw_args+2)
    ld de,(cgcanvas+2)
    add hl,de
    ld de,(rt_bmp_row)
    add hl,de
    ld (RT_BMP_PAR+2),hl
    ld hl,(rt_dw_args+4)
    ld (RT_BMP_PAR+4),hl
    ld hl,RT_BMP_BUF            ; the buffer as a 24-bit address too: the
    ld (RT_BMP_PAR+8),hl        ; blitter writes the rows to +8..+10 [static:
    ld a,80h                    ; PCW045.SYS #1359], ROSAN283 says to DE
    ld (RT_BMP_PAR+10),a
    ld hl,RT_BMP_PAR
    ld de,RT_BMP_BUF
    call 0113h                  ; bios_getbitmap
    ld hl,(rt_bmp_rows)
    ld de,(rt_bmp_rowb)
    call rt_mul16
    ld (rt_bk_size),hl
    ld de,(rt_bk_off)
    ld a,(rt_bk_blk)
    ld b,a
    ld c,80h
    ld hl,RT_BMP_BUF
    call rt_bk_copy             ; the strip into the bitmap's block
    ld hl,(rt_bk_off)
    ld de,(rt_bk_size)
    add hl,de
    ld (rt_bk_off),hl
    ld hl,(rt_bmp_row)
    ld de,(rt_bmp_rows)
    add hl,de
    ld (rt_bmp_row),hl
    jp rt_bmp_strip
rt_bmp_strips_done:
    ld a,112
    call 003Bh                  ; os_mouse_on
rt_bmp_got:
    ld hl,(rt_bmp_rec)
    ld de,4
    add hl,de
    ex de,hl
    ld hl,rt_dw_args+4
    ld bc,4
    ldir                        ; the bitmap's size: w, h
    ret
rt_bmp_big:
    ld hl,rt_bmp_big_text
    ld bc,rt_bmp_big_text_end-rt_bmp_big_text
    jp rt_err_msg
rt_bmp_big_text:
    db "Runtime error: the rectangle is larger than the BITMAP at line "
rt_bmp_big_text_end:

; rt_bmp_put — BITMAP PUT: HL = record, rt_dw_args = x, y (canvas). The
; bitmap's rectangle must lie in the canvas. Drawn opaque (white bits white,
; the others black), whatever DRAW INK says; the ink and mode are restored.
rt_bmp_put:
    ld (rt_bmp_rec),hl
    ld de,4
    add hl,de
    ld de,rt_dw_args+4
    ld bc,4
    ldir                        ; w, h
    call rt_cv_rect
    call rt_cv_empty
    ret z
    ld hl,(rt_dw_args)
    ld de,(cgcanvas)
    add hl,de
    ld (RT_BMP_PAR),hl
    ld hl,(rt_dw_args+2)
    ld de,(cgcanvas+2)
    add hl,de
    ld (RT_BMP_PAR+2),hl
    ld hl,(rt_dw_args+4)
    ld (RT_BMP_PAR+4),hl
    ld hl,(rt_dw_args+6)
    ld (RT_BMP_PAR+6),hl
    ld hl,0
    ld (RT_BMP_PAR+8),hl        ; the data: offset 0 of the block
    ld hl,(rt_bmp_rec)
    call rt_bmp_blk
    ld (RT_BMP_PAR+10),a
    ld a,111
    call 003Bh                  ; os_mouse_off
    call 0E3h                   ; bios_getink
    ld (rt_cv_oldink),a
    call 0E9h                   ; bios_getmode
    ld (rt_cv_oldmode),a
    xor a
    call 0E0h                   ; bios_setink: black
    xor a
    call 0E6h                   ; bios_setmode: opaque
    ld hl,RT_BMP_PAR
    call 010Ah                  ; bios_plotbitmap
    ld a,(rt_cv_oldmode)
    call 0E6h
    ld a,(rt_cv_oldink)
    call 0E0h
    ld a,112
    call 003Bh                  ; os_mouse_on
    ret

    IF PB_BMPPART
; ----------------------------------------------------------------------------
; M13 BITMAP PUT Name, x, y, sx, sy, w, h (a part of a bitmap) and BITMAP
; MASK Name, Mask, x, y [, sx, sy, w, h] (drawn through a mask): LANGUAGE-
; SPEC §5.14, docs/M13-SPRITES.md.
; ROSAN283 bios_plotmaskedbitmap #2F (#10D): bios_plotbitmap's block plus
; "+11 24-bit address of mask data (0=transp)". [static: PCW045.SYS #121E
; sets the blitter's mask flag; #12EC / #1478 AND each data byte with its
; mask byte, and the screen keeps its pixel where the mask bit is 0.] A
; mask's set bit is a white pixel (as in every bitmap), so a WHITE mask
; pixel draws the image's pixel and a BLACK one leaves the screen alone.
; The blitter reads rows of (w + 7) \ 8 bytes with no stride (doc). A part
; as wide as its bitmap (and its mask) is plotted straight from the block,
; its first row's offset added. Any other part is copied, a strip of whole
; rows at a time, into the bottom quarter (os_copy_24bit, the M12 way) and
; repacked there, shifted left by sx mod 8:
;   RT_BMP_T #2C00, 640 bytes: the strip's source rows;
;   RT_BMP_D #2E80, 192 bytes: the part's image rows;
;   RT_BMP_M #2F40, 192 bytes: the part's mask rows.
; rt_dw_args: +0 x, +2 y, +4 w, +6 h (canvas), +8 sx, +10 sy (bitmap).
; ----------------------------------------------------------------------------
RT_BMP_T equ 2C00h
RT_BMP_D equ 2E80h
RT_BMP_M equ 2F40h

; rt_bmp_mask — BITMAP MASK: HL = the image's record, rt_bmp_mrec the mask's.
rt_bmp_mask:
    ld (rt_bmp_rec),hl
    ld a,1
    jp rt_bmp_part_go

; rt_bmp_part — BITMAP PUT of a part: HL = record.
rt_bmp_part:
    ld (rt_bmp_rec),hl
    xor a
rt_bmp_part_go:
    ld (rt_bmp_masked),a
    ld hl,(rt_bmp_rec)
    call rt_bmp_inside          ; the part lies in the image
    ld (rt_bmp_rowb),hl
    ld a,(rt_bmp_masked)
    or a
    jp z,rt_bmp_part_in
    ld hl,(rt_bmp_mrec)
    call rt_bmp_inside          ; and in the mask
    ld (rt_bmp_mrb),hl
rt_bmp_part_in:
    call rt_cv_rect
    call rt_cv_empty
    ret z
    ld hl,(rt_dw_args)
    ld de,(cgcanvas)
    add hl,de
    ld (RT_BMP_PAR),hl          ; screen x
    ld hl,(rt_dw_args+4)
    ld (RT_BMP_PAR+4),hl        ; w
    call rt_bmp_bpr
    ld (rt_bmp_drb),hl          ; the part's bytes a row
    call rt_bmp_begin
    ld hl,(rt_dw_args+8)
    ld a,h
    or l
    jp nz,rt_bmp_slow           ; not from the left edge
    ld hl,(rt_bmp_rowb)
    ld de,(rt_bmp_drb)
    or a
    sbc hl,de
    jp nz,rt_bmp_slow           ; narrower than the image
    ld a,(rt_bmp_masked)
    or a
    jp z,rt_bmp_fast
    ld hl,(rt_bmp_mrb)
    ld de,(rt_bmp_drb)
    or a
    sbc hl,de
    jp nz,rt_bmp_slow           ; narrower than the mask
rt_bmp_fast:                    ; whole rows: straight from the blocks
    ld hl,(rt_dw_args+2)
    ld de,(cgcanvas+2)
    add hl,de
    ld (RT_BMP_PAR+2),hl
    ld hl,(rt_dw_args+6)
    ld (RT_BMP_PAR+6),hl
    ld hl,(rt_dw_args+10)
    ld de,(rt_bmp_rowb)
    call rt_mul16
    ld (RT_BMP_PAR+8),hl        ; the first row's offset in the block
    ld hl,(rt_bmp_rec)
    call rt_bmp_blk
    ld (RT_BMP_PAR+10),a
    ld a,(rt_bmp_masked)
    or a
    jp z,rt_bmp_fast_go
    ld hl,(rt_dw_args+10)
    ld de,(rt_bmp_mrb)
    call rt_mul16
    ld (RT_BMP_PAR+11),hl
    ld hl,(rt_bmp_mrec)
    call rt_bmp_blk
    ld (RT_BMP_PAR+13),a
rt_bmp_fast_go:
    call rt_bmp_blit
    jp rt_bmp_end
rt_bmp_slow:                    ; rows a strip: 640 \ source bytes a row,
    ld hl,640                   ; 192 \ the part's, and 640 \ the mask's
    ld de,(rt_bmp_rowb)
    call rt_bmp_quot
    ld (rt_bmp_k_n),bc
    ld hl,192
    ld de,(rt_bmp_drb)
    call rt_bmp_quot
    call rt_bmp_fewer
    ld a,(rt_bmp_masked)
    or a
    jp z,rt_bmp_slow_n
    ld hl,640
    ld de,(rt_bmp_mrb)
    call rt_bmp_quot
    call rt_bmp_fewer
rt_bmp_slow_n:
    ld hl,0
    ld (rt_bmp_row),hl
rt_bmp_slow_strip:
    ld hl,(rt_dw_args+6)
    ld de,(rt_bmp_row)
    or a
    sbc hl,de                   ; rows left
    jp z,rt_bmp_end
    ld de,(rt_bmp_k_n)
    push hl
    or a
    sbc hl,de
    pop hl
    jp c,rt_bmp_slow_rows
    ex de,hl                    ; a whole strip
rt_bmp_slow_rows:
    ld (rt_bmp_rows),hl
    ld (RT_BMP_PAR+6),hl
    ld hl,(rt_dw_args+2)
    ld de,(cgcanvas+2)
    add hl,de
    ld de,(rt_bmp_row)
    add hl,de
    ld (RT_BMP_PAR+2),hl
    ld hl,(rt_bmp_rec)
    ld de,(rt_bmp_rowb)
    ld bc,RT_BMP_D
    call rt_bmp_fetch
    ld hl,RT_BMP_D
    ld (RT_BMP_PAR+8),hl
    ld a,80h                    ; the bottom quarter's block
    ld (RT_BMP_PAR+10),a
    ld a,(rt_bmp_masked)
    or a
    jp z,rt_bmp_slow_go
    ld hl,(rt_bmp_mrec)
    ld de,(rt_bmp_mrb)
    ld bc,RT_BMP_M
    call rt_bmp_fetch
    ld hl,RT_BMP_M
    ld (RT_BMP_PAR+11),hl
    ld a,80h
    ld (RT_BMP_PAR+13),a
rt_bmp_slow_go:
    call rt_bmp_blit
    ld hl,(rt_bmp_row)
    ld de,(rt_bmp_rows)
    add hl,de
    ld (rt_bmp_row),hl
    jp rt_bmp_slow_strip

; rt_bmp_inside — HL = record: the part sx, sy, w, h (rt_dw_args +8, +10,
; +4, +6) lies in the bitmap's current size, or the program stops. HL = its
; bytes a row.
rt_bmp_inside:
    ld de,4
    add hl,de
    ld c,(hl)
    inc hl
    ld b,(hl)                   ; BC = width
    inc hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld (rt_bmp_lim),de          ; height
    push bc
    ld hl,(rt_dw_args+8)
    ld de,(rt_dw_args+4)
    call rt_cv_span
    jp c,rt_bmp_partout
    ld hl,(rt_dw_args+10)
    ld de,(rt_dw_args+6)
    ld bc,(rt_bmp_lim)
    call rt_cv_span
    jp c,rt_bmp_partout
    pop hl
    jp rt_bmp_bpr
rt_bmp_partout:
    ld hl,rt_bmp_partout_text
    ld bc,rt_bmp_partout_text_end-rt_bmp_partout_text
    jp rt_err_msg
rt_bmp_partout_text:
    db "Runtime error: the part is outside the BITMAP at line "
rt_bmp_partout_text_end:

; rt_bmp_quot — BC = HL \ DE (unsigned, DE > 0).
rt_bmp_quot:
    ld bc,0
rt_bmp_quot_loop:
    or a
    sbc hl,de
    ret c
    inc bc
    jp rt_bmp_quot_loop

; rt_bmp_fewer — rt_bmp_k_n = the smaller of itself and BC.
rt_bmp_fewer:
    ld hl,(rt_bmp_k_n)
    or a
    sbc hl,bc
    ret c
    ld (rt_bmp_k_n),bc
    ret

; rt_bmp_fetch — HL = record, DE = its bytes a row, BC = out: the rows
; sy + rt_bmp_row .. (+ rt_bmp_rows) of the record's block into RT_BMP_T,
; then the part's bits of each (from sx, w wide) packed into out at
; rt_bmp_drb bytes a row.
rt_bmp_fetch:
    ld (rt_bmp_out),bc
    ld (rt_bmp_frb),de
    call rt_bmp_blk
    ld (rt_bk_blk),a
    ld hl,(rt_dw_args+10)
    ld de,(rt_bmp_row)
    add hl,de
    ld de,(rt_bmp_frb)
    call rt_mul16
    ld (rt_bk_off),hl
    ld hl,(rt_bmp_rows)
    ld de,(rt_bmp_frb)
    call rt_mul16
    ld (rt_bk_size),hl
    ld a,(rt_bk_blk)
    ld c,a
    ld b,80h
    ld hl,(rt_bk_off)
    ld de,RT_BMP_T
    call rt_bk_copy             ; whole rows of the block into T
    ld a,(rt_dw_args+8)
    and 7
    ld (rt_bmp_sh),a
    ld hl,(rt_dw_args+8)
    srl h
    rr l
    srl h
    rr l
    srl h
    rr l
    ld de,RT_BMP_T
    add hl,de
    ld (rt_bmp_src),hl          ; the part's first byte in the first row
    ld hl,(rt_bmp_out)
    ld (rt_bmp_dst),hl
    ld hl,(rt_bmp_rows)
    ld (rt_bmp_left),hl
rt_bmp_fetch_row:
    ld hl,(rt_bmp_src)
    ld de,(rt_bmp_dst)
    ld bc,(rt_bmp_drb)
rt_bmp_fetch_byte:
    push bc
    ld a,(rt_bmp_sh)
    ld b,a
    ld a,(hl)
    inc hl
    ld c,(hl)
    inc b
    dec b
    jp z,rt_bmp_fetch_put
rt_bmp_fetch_shift:
    sla c
    rla
    djnz rt_bmp_fetch_shift
rt_bmp_fetch_put:
    ld (de),a
    inc de
    pop bc
    dec bc
    ld a,b
    or c
    jp nz,rt_bmp_fetch_byte
    ld hl,(rt_bmp_src)
    ld de,(rt_bmp_frb)
    add hl,de
    ld (rt_bmp_src),hl
    ld hl,(rt_bmp_dst)
    ld de,(rt_bmp_drb)
    add hl,de
    ld (rt_bmp_dst),hl
    ld hl,(rt_bmp_left)
    dec hl
    ld (rt_bmp_left),hl
    ld a,h
    or l
    jp nz,rt_bmp_fetch_row
    ret

; rt_bmp_begin / rt_bmp_end — the pointer hidden, black ink and opaque mode
; for the blitter; then the program's ink and mode back, the pointer shown.
rt_bmp_begin:
    ld a,111
    call 003Bh                  ; os_mouse_off
    call 0E3h                   ; bios_getink
    ld (rt_cv_oldink),a
    call 0E9h                   ; bios_getmode
    ld (rt_cv_oldmode),a
    xor a
    call 0E0h                   ; bios_setink: black
    xor a
    call 0E6h                   ; bios_setmode: opaque
    ret
rt_bmp_end:
    ld a,(rt_cv_oldmode)
    call 0E6h
    ld a,(rt_cv_oldink)
    call 0E0h
    ld a,112
    call 003Bh                  ; os_mouse_on
    ret

; rt_bmp_blit — RT_BMP_PAR to the screen: bios_plotmaskedbitmap if
; rt_bmp_masked, bios_plotbitmap otherwise.
rt_bmp_blit:
    ld hl,RT_BMP_PAR
    ld a,(rt_bmp_masked)
    or a
    jp nz,rt_bmp_blit_mask
    call 010Ah                  ; bios_plotbitmap
    ret
rt_bmp_blit_mask:
    call 010Dh                  ; bios_plotmaskedbitmap
    ret
    ENDIF
    ENDIF
    ENDIF

    IF PB_POINT
; rt_point — POINT(x, y): HL = x, DE = y (canvas): HL = 1 black, 0 white.
; Its own switch: a program may read pixels without any BITMAP.
rt_point:
    push hl
    push de
    call rt_cv_ready
    pop de
    pop hl
    push hl
    push de
    call rt_cv_point
    ld a,111
    call 003Bh                  ; os_mouse_off
    pop hl
    ld de,(cgcanvas+2)
    add hl,de                   ; HL = screen y
    pop de
    push hl
    ld hl,(cgcanvas)
    add hl,de
    ex de,hl                    ; DE = screen x
    pop hl
    call 0F5h                   ; bios_getpxl: A = 0 black, 1 white
    ld (rt_bmp_px),a
    ld a,112
    call 003Bh                  ; os_mouse_on
    ld a,(rt_bmp_px)
    xor 1
    and 1
    ld l,a
    ld h,0
    ret
    ENDIF

    IF PB_BMPFILE
; ----------------------------------------------------------------------------
; M12 BITMAP SAVE / LOAD: a PBI1 file (docs/M12-BITMAP-FORMAT.md):
;   +0 "PBI1", +4 version 1, +5 flags 0, +6 width, +8 height, +10 bytes a
;   row, +12 data bytes (+10 x +8), +14 0; then the data; then the check:
;   two words, the sum of every byte before it and the sum of those running
;   sums (as a PDB1 database, runtime "databases": rt_db_sum).
; SAVE writes NAME.NEW, reads it back whole, deletes NAME.BAK, renames the
; file to NAME.BAK and NAME.NEW to the file (the database's steps and
; routines: a failure before the renames leaves the file as it was and
; deletes NAME.NEW; M14: 253 when NAME.NEW or NAME.BAK is another file's,
; and NAME.BAK is kept when there is no file). LOAD reads the file only; a damaged or wrong file sets
; IOERR and leaves the bitmap's size unchanged (its pixels may have been
; partly overwritten). IOERR: 0 or the code (248 not a PBI1 file, 250
; another version, 251 damaged, 252 larger than the bitmap).
; ----------------------------------------------------------------------------
rt_bmp_magic:
    db "PBI1"

; rt_bmp_header — HL = record: the 16-byte header of its current size in
; rt_db_hdr.
rt_bmp_header:
    ld (rt_bmp_rec),hl
    ld hl,rt_bmp_magic
    ld de,rt_db_hdr
    ld bc,4
    ldir
    ld a,1
    ld (rt_db_hdr+4),a
    xor a
    ld (rt_db_hdr+5),a
    ld hl,(rt_bmp_rec)
    ld de,4
    add hl,de
    ld de,rt_db_hdr+6
    ld bc,4
    ldir                        ; width, height
    ld hl,(rt_db_hdr+6)
    call rt_bmp_bpr
    ld (rt_db_hdr+10),hl
    ex de,hl
    ld hl,(rt_db_hdr+8)
    call rt_mul16
    ld (rt_db_hdr+12),hl
    ld hl,0
    ld (rt_db_hdr+14),hl
    ret

; rt_bmp_save — BITMAP SAVE: HL = record, rt_file_desc = the name.
rt_bmp_save:
    call rt_bmp_header
    xor a
    ld (rt_db_vfy),a
    call rt_db_prepare
    jp c,rt_fio_set
    IF PB_FSAFE
    call rt_db_owns             ; M14 (KI-91)
    jp c,rt_fio_set
    ENDIF
    ld hl,0
    ld (rt_db_s1),hl
    ld (rt_db_s2),hl
    ld a,1
    call rt_db_name
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld b,1
    ld a,144
    call 003Bh                  ; os_open_file NAME.NEW for writing
    jp c,rt_db_s_drop
    ld hl,rt_db_hdr
    ld bc,16
    call rt_db_write
    jp c,rt_db_s_fail
    ld hl,(rt_bmp_rec)
    call rt_bmp_blk
    ld (rt_bk_blk),a
    ld hl,0
    ld (rt_bk_off),hl
    ld hl,(rt_db_hdr+12)
    ld (rt_bmp_left),hl
rt_bmp_s_piece:
    ld hl,(rt_bmp_left)
    ld a,h
    or l
    jp z,rt_bmp_s_tail
    ld bc,512
    or a
    sbc hl,bc
    jp nc,rt_bmp_s_n
    ld bc,(rt_bmp_left)
rt_bmp_s_n:
    ld (rt_bk_size),bc
    ld hl,rt_file_buf+639
    ld (rt_dst_end),hl          ; the buffer is the active destination (as rt_db_read)
    call 0CBh
    ld b,a
    ld de,rt_file_buf
    ld a,(rt_bk_blk)
    ld c,a
    ld hl,(rt_bk_off)
    call rt_bk_copy             ; block -> rt_file_buf
    ld hl,rt_file_buf
    ld bc,(rt_bk_size)
    call rt_db_write
    jp c,rt_db_s_fail
    ld hl,(rt_bk_off)
    ld de,(rt_bk_size)
    add hl,de
    ld (rt_bk_off),hl
    ld hl,(rt_bmp_left)
    or a
    sbc hl,de
    ld (rt_bmp_left),hl
    jp rt_bmp_s_piece
rt_bmp_s_tail:
    ld hl,(rt_db_s1)
    ld (rt_db_t),hl
    ld hl,(rt_db_s2)
    ld (rt_db_t+2),hl
    ld hl,rt_db_t
    ld bc,4
    call rt_db_write
    jp c,rt_db_s_fail
    ld b,1
    ld a,145
    call 003Bh                  ; close
    jp c,rt_db_s_drop
    ld a,1                      ; read NAME.NEW back
    ld (rt_db_vfy),a
    call rt_bmp_read
    push af
    xor a
    ld (rt_db_vfy),a
    pop af
    jp c,rt_db_s_drop
    jp rt_db_s_steps            ; the database's steps 3 - 5

; rt_bmp_load — BITMAP LOAD: HL = record, rt_file_desc = the name.
rt_bmp_load:
    ld (rt_bmp_rec),hl
    xor a
    ld (rt_db_vfy),a
    call rt_db_prepare
    jp c,rt_fio_set
    call rt_bmp_read
    jp c,rt_fio_set
    ld hl,(rt_bmp_rec)          ; the bitmap's size: the file's
    ld de,4
    add hl,de
    ex de,hl
    ld hl,rt_bmp_wh
    ld bc,4
    ldir
    xor a
    jp rt_fio_set

; rt_bmp_read — read the file (rt_db_vfy 0: the own name, into the bitmap;
; 1: NAME.NEW, only checked against rt_db_hdr). NC = good (rt_bmp_wh = its
; width, height); C = A the IOERR code. The file is closed.
rt_bmp_read:
    ld a,(rt_db_vfy)
    call rt_db_name
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld b,0
    ld a,144
    call 003Bh                  ; os_open_file for reading
    ret c
    ld hl,0
    ld (rt_db_s1),hl
    ld (rt_db_s2),hl
    ld bc,16
    call rt_db_need
    jp c,rt_db_l_fail
    ld hl,rt_file_buf
    ld bc,16
    call rt_db_sum
    ld a,(rt_db_vfy)
    or a
    jp z,rt_bmp_r_check
    ld hl,rt_file_buf           ; the read-back: the header as written
    ld de,rt_db_hdr
    ld b,16
rt_bmp_r_same:
    ld a,(de)
    cp (hl)
    ld a,251
    jp nz,rt_db_l_fail
    inc hl
    inc de
    djnz rt_bmp_r_same
rt_bmp_r_check:
    ld hl,rt_file_buf
    ld de,rt_bmp_magic
    ld b,4
rt_bmp_r_magic:
    ld a,(de)
    cp (hl)
    ld a,248                    ; not a PBI1 file
    jp nz,rt_db_l_fail
    inc hl
    inc de
    djnz rt_bmp_r_magic
    ld a,(rt_file_buf+4)
    cp 1
    ld a,250                    ; another version
    jp nz,rt_db_l_fail
    ld hl,(rt_file_buf+14)
    ld a,(rt_file_buf+5)
    or h
    or l
    ld a,250
    jp nz,rt_db_l_fail
    ld hl,(rt_file_buf+6)       ; 1 <= width <= 640, 1 <= height <= 480
    ld (rt_bmp_wh),hl
    ld de,641
    call rt_bmp_range
    jp c,rt_db_l_fail
    ld hl,(rt_file_buf+8)
    ld (rt_bmp_wh+2),hl
    ld de,481
    call rt_bmp_range
    jp c,rt_db_l_fail
    ld hl,(rt_bmp_wh)
    call rt_bmp_bpr
    ld de,(rt_file_buf+10)
    or a
    sbc hl,de
    ld a,251
    jp nz,rt_db_l_fail
    ld hl,(rt_bmp_wh+2)
    call rt_mul16               ; DE = bytes a row
    ld de,(rt_file_buf+12)
    or a
    sbc hl,de
    ld a,251
    jp nz,rt_db_l_fail
    ld (rt_bmp_left),de
    ld hl,(rt_bmp_rec)
    ld a,(hl)
    inc hl
    ld h,(hl)
    ld l,a
    or a
    sbc hl,de
    ld a,252                    ; larger than the bitmap
    jp c,rt_db_l_fail
    ld hl,(rt_bmp_rec)
    call rt_bmp_blk
    ld (rt_bk_blk),a
    ld hl,0
    ld (rt_bk_off),hl
rt_bmp_r_piece:
    ld hl,(rt_bmp_left)
    ld a,h
    or l
    jp z,rt_bmp_r_tail
    ld bc,128
    or a
    sbc hl,bc
    jp nc,rt_bmp_r_n
    ld bc,(rt_bmp_left)
rt_bmp_r_n:
    ld (rt_bk_size),bc
    call rt_db_need
    jp c,rt_db_l_fail
    ld hl,rt_file_buf
    ld bc,(rt_bk_size)
    call rt_db_sum
    ld a,(rt_db_vfy)
    or a
    jp nz,rt_bmp_r_next
    call 0CBh
    ld c,a
    ld hl,rt_file_buf
    ld a,(rt_bk_blk)
    ld b,a
    ld de,(rt_bk_off)
    call rt_bk_copy             ; rt_file_buf -> the block
rt_bmp_r_next:
    ld hl,(rt_bk_off)
    ld de,(rt_bk_size)
    add hl,de
    ld (rt_bk_off),hl
    ld hl,(rt_bmp_left)
    or a
    sbc hl,de
    ld (rt_bmp_left),hl
    jp rt_bmp_r_piece

rt_bmp_r_tail:
    ld bc,4
    call rt_db_need
    jp c,rt_db_l_fail
    ld hl,(rt_file_buf)
    ld de,(rt_db_s1)
    or a
    sbc hl,de
    ld a,251                    ; the check does not match
    jp nz,rt_db_l_fail
    ld hl,(rt_file_buf+2)
    ld de,(rt_db_s2)
    or a
    sbc hl,de
    jp nz,rt_db_l_fail
    ld bc,1                     ; nothing may follow the check
    call rt_db_read
    jp nc,rt_bmp_r_extra
    cp 0A1h
    jp nz,rt_db_l_fail
    call rt_db_close_r
    or a
    ret
rt_bmp_r_extra:
    ld a,251                    ; bytes after the check
    jp rt_db_l_fail

; rt_bmp_range — C (A = 251) unless 1 <= HL < DE.
rt_bmp_range:
    ld a,h
    or l
    jp z,rt_bmp_range_bad
    or a
    sbc hl,de
    ccf
    ld a,251
    ret
rt_bmp_range_bad:
    ld a,251
    scf
    ret
    ENDIF

    IF PB_PAGE
; ============================================================================
; M12 printing (LANGUAGE-SPEC §5.13, docs/M12-PRINTING.md): one page at a
; time in Rosanne's print meta-file, its text in a typo font.
; ROSAN283 (doc): os_meta_open 95 "CHL = 24-bit address of 13-byte
;   parameter block: +0 orientation, +1 page width, +3 height, +5 left
;   margin, +7 top margin (all in 1/1800")"; A = 0 OK / 7 no memory.
;   os_meta_font 96 (HL = font family ID, B = point size), os_meta_style 97
;   (D), os_meta_y 98 (HL baseline, DE top, BC bottom), os_meta_char 99 (C,
;   B accent, DE x), os_meta_hline 101 (DE left, BC right, HL top, IX
;   thickness), os_meta_vline 102 (DE x, HL top, BC bottom, IX), os_meta_print
;   103 (B = 0 full resolution; A = 0 OK / 1 memory / 2 font / 3 fonts / 4
;   aborted / 5 in use / 6 printer type), os_meta_close 105; each A = 255 if
;   no page is open.
;   os_typo_init 83 (C = no memory), os_typo_getlist 84 (B entries of 37
;   bytes at CHL: +0 ID, +2 styles, +3 RTF family 1 Times, 2 Swiss),
;   os_typo_select 85 (E slot), os_typo_def 87 (HL ID, D styles, B size),
;   os_typo_clr 88, os_typo_info 90 (HL -> pitch, ascender, descender),
;   os_typo_charwidth 91 (C, B accent, D style: DE width in 1/1800").
; [static: Shopping List, PCW055.PRG #4A37-#4BA3] the same sequence: typo
; init and list, the font's ID passed to os_typo_def and os_meta_font, an
; A4 page with half-inch margins (the block below), os_meta_print B = 0
; then os_meta_close. The ID is the first font of RTF family 1 (Times), or
; the list's first font.
; Coordinates are points (1/72") from the top left of the printable area:
; x 0..522, y 0..765 (A4 less the margins); 1 point = 25/1800".
; ----------------------------------------------------------------------------
RT_PG_W equ 522
RT_PG_H equ 765

rt_pg_block:                    ; os_meta_open: portrait, A4, 1/2" margins
    db 0
    dw 14850,20925,900,900
    db 0,0,0,0
rt_pg_sizes:
    db 6,8,10,11,12,14,18,24,36,72

; rt_pg_need — a runtime error unless a page is open.
rt_pg_need:
    ld a,(rt_pg_open)
    or a
    ret nz
    ld hl,rt_pg_none_text
    ld bc,rt_pg_none_end-rt_pg_none_text
    jp rt_err_msg
rt_pg_none_text:
    db "Runtime error: no page is open (PAGE NEW) at line "
rt_pg_none_end:

rt_pg_outside:
    ld hl,rt_pg_out_text
    ld bc,rt_pg_out_end-rt_pg_out_text
    jp rt_err_msg
rt_pg_out_text:
    db "Runtime error: printing outside the page at line "
rt_pg_out_end:

; rt_pg_25 — HL = HL * 25 (points to 1/1800"). DE corrupt.
rt_pg_25:
    ld d,h
    ld e,l
    add hl,hl
    add hl,hl
    add hl,de
    ld d,h
    ld e,l
    add hl,hl
    add hl,hl
    add hl,de
    ret

; rt_pg_range — HL = HL * 25 if 0 <= HL <= DE; else a runtime error.
rt_pg_range:
    ex de,hl
    or a
    sbc hl,de
    ex de,hl
    jp c,rt_pg_outside          ; also a negative HL (as unsigned)
    jp rt_pg_25

; rt_pg_family — rt_pg_id = the first typo font of RTF family 1 (Times), or
; the list's first font. C = no font (A = 2, as os_meta_print).
rt_pg_family:
    ld a,84
    call 003Bh                  ; os_typo_getlist: B entries at CHL
    ld a,b
    ld (rt_pg_n),a
    or a
    ld a,2
    scf
    ret z
    ld a,b
    ld (rt_pg_k),a              ; entries left
    xor a
    ld (rt_pg_found),a
rt_pg_f_entry:
    ld b,1
    ld a,42
    call 003Bh                  ; os_get_byte_24bit, wound on: ID low
    ld a,e
    ld (rt_pg_t),a
    ld b,1
    ld a,42
    call 003Bh                  ; ID high
    ld a,e
    ld (rt_pg_t+1),a
    ld b,1
    ld a,42
    call 003Bh                  ; styles
    ld b,1
    ld a,42
    call 003Bh                  ; RTF family
    ld a,(rt_pg_found)
    or a
    jp nz,rt_pg_f_skip
    ld a,(rt_pg_k)              ; the first entry is the fallback
    ld d,a
    ld a,(rt_pg_n)
    cp d
    jp nz,rt_pg_f_times
    push hl
    ld hl,(rt_pg_t)
    ld (rt_pg_id),hl
    pop hl
rt_pg_f_times:
    ld a,e
    cp 1
    jp nz,rt_pg_f_skip
    ld a,1
    ld (rt_pg_found),a
    push hl
    ld hl,(rt_pg_t)
    ld (rt_pg_id),hl
    pop hl
rt_pg_f_skip:
    ld a,33                     ; the name: 33 bytes
rt_pg_f_name:
    push af
    ld b,1
    ld a,42
    call 003Bh
    pop af
    dec a
    jp nz,rt_pg_f_name
    ld a,(rt_pg_k)
    dec a
    ld (rt_pg_k),a
    jp nz,rt_pg_f_entry
    or a
    ret

; rt_pg_new — PAGE NEW: a new, empty page (a page still open is discarded),
; in 10-point plain text. IOERR: 0, 7 no memory, or as PAGE FONT.
rt_pg_new:
    call rt_pg_close
    ld a,(rt_pg_typo)
    or a
    jp nz,rt_pg_new_open
    ld a,83
    call 003Bh                  ; os_typo_init
    ld a,7
    jp c,rt_fio_set
    call rt_pg_family
    jp c,rt_fio_set
    ld a,1
    ld (rt_pg_typo),a
rt_pg_new_open:
    call 0CBh                   ; bios_getmem1: the block holding rt_pg_block
    ld c,a
    ld hl,rt_pg_block
    ld a,95
    call 003Bh                  ; os_meta_open
    or a
    jp nz,rt_fio_set
    ld a,1
    ld (rt_pg_open),a
    ld hl,10
    ld (rt_pg_args),hl
    ld hl,0
    ld (rt_pg_args+2),hl
    jp rt_pg_font_set

; rt_pg_font — PAGE FONT size [, BOLD]: rt_pg_args = size, +2 = style
; (1 bold). IOERR: 0, or os_typo_def's 1 no such font / 2 size / 7 memory.
rt_pg_font:
    call rt_pg_need
rt_pg_font_set:
    ld a,(rt_pg_args+1)
    or a
    jp nz,rt_pg_bad_size
    ld a,(rt_pg_args)
    ld hl,rt_pg_sizes
    ld b,10
rt_pg_size_find:
    cp (hl)
    jp z,rt_pg_size_ok
    inc hl
    djnz rt_pg_size_find
rt_pg_bad_size:
    ld hl,rt_pg_size_text
    ld bc,rt_pg_size_end-rt_pg_size_text
    jp rt_err_msg
rt_pg_size_text:
    db "Runtime error: a print size is 6, 8, 10, 11, 12, 14, 18, 24, 36 or 72 at line "
rt_pg_size_end:
rt_pg_size_ok:
    ld (rt_pg_size),a
    ld a,(rt_pg_args+2)
    ld (rt_pg_style),a
    ld e,0
    ld a,85
    call 003Bh                  ; os_typo_select slot 0
    ld a,88
    call 003Bh                  ; os_typo_clr (4: it was empty)
    ld hl,(rt_pg_id)
    ld d,0FFh
    ld a,(rt_pg_size)
    ld b,a
    ld a,87
    call 003Bh                  ; os_typo_def
    or a
    jp nz,rt_fio_set
    IF PB_TYPG
    ld a,2
    ld (rt_ty_slot),a           ; M15: slot 0 holds the PAGE font
    ENDIF
    ld a,90
    call 003Bh                  ; os_typo_info: HL -> pitch, ascender, descender
    or a
    jp nz,rt_fio_set
    inc hl
    inc hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld (rt_pg_asc),de
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld (rt_pg_desc),de
    ld hl,(rt_pg_id)
    ld a,(rt_pg_size)
    ld b,a
    ld a,96
    call 003Bh                  ; os_meta_font
    or a
    jp nz,rt_fio_set
    ld a,(rt_pg_style)
    ld d,a
    ld a,97
    call 003Bh                  ; os_meta_style
    jp rt_fio_set

; rt_pg_char — A = a character of a string to print: C = the character
; (outside 32..255 as '?').
rt_pg_char:
    cp 32
    jp nc,rt_pg_char_ok
    ld a,'?'
rt_pg_char_ok:
    ld c,a
    ret

; rt_pg_text — PAGE TEXT x, y, text$: rt_pg_args = x, y (the line's top);
; HL = the text. The whole line must fit the page.
rt_pg_text:
    push hl
    call rt_pg_need
    IF PB_TYPG
    call rt_ty_pgslot           ; M15: the PAGE font back in slot 0 after DRAW TYPE
    ENDIF
    ld hl,(rt_pg_args+2)
    ld de,RT_PG_H
    call rt_pg_range
    ld (rt_pg_top),hl
    ld de,(rt_pg_asc)
    add hl,de
    ld (rt_pg_base),hl
    ld de,(rt_pg_desc)
    add hl,de
    push hl
    ld de,RT_PG_H*25+1
    or a
    sbc hl,de
    pop bc                      ; BC = bottom
    jp nc,rt_pg_outside
    ld hl,(rt_pg_base)
    ld de,(rt_pg_top)
    ld a,98
    call 003Bh                  ; os_meta_y
    ld hl,(rt_pg_args)
    ld de,RT_PG_W
    call rt_pg_range
    ld (rt_pg_x),hl
    pop hl
rt_pg_t_next:
    ld a,(hl)
    or a
    jp z,rt_pg_t_done
    inc hl
    push hl
    call rt_pg_char
    ld a,c
    ld (rt_pg_ch),a
    ld b,0
    ld a,(rt_pg_style)
    ld d,a
    ld a,91
    call 003Bh                  ; os_typo_charwidth: DE = width
    or a
    jp nz,rt_pg_t_fail
    ld hl,(rt_pg_x)
    add hl,de
    ld (rt_pg_nx),hl
    ld de,RT_PG_W*25+1
    or a
    sbc hl,de
    jp nc,rt_pg_outside
    ld a,(rt_pg_ch)
    ld c,a
    ld b,0
    ld de,(rt_pg_x)
    ld a,99
    call 003Bh                  ; os_meta_char
    or a
    jp nz,rt_pg_t_fail
    ld hl,(rt_pg_nx)
    ld (rt_pg_x),hl
    pop hl
    jp rt_pg_t_next
rt_pg_t_fail:
    pop hl
    jp rt_fio_set
rt_pg_t_done:
    xor a
    jp rt_fio_set

; rt_pg_width — PAGEWIDTH(text$): HL = the text; HL = its width in points
; (rounded up) in the current print font (a width over 2600 points is
; reported as 2600: no page is that wide).
rt_pg_width:
    push hl
    call rt_pg_need
    IF PB_TYPG
    call rt_ty_pgslot           ; M15: the PAGE font back in slot 0 after DRAW TYPE
    ENDIF
    pop hl
    ld de,0
    ld (rt_pg_nx),de
rt_pg_w_next:
    ld a,(hl)
    or a
    jp z,rt_pg_w_done
    inc hl
    push hl
    call rt_pg_char
    ld b,0
    ld a,(rt_pg_style)
    ld d,a
    ld a,91
    call 003Bh                  ; os_typo_charwidth
    or a
    jp z,rt_pg_w_add
    ld de,0                     ; refused (4 no font, 5 out of range): none
rt_pg_w_add:
    ld hl,(rt_pg_nx)
    add hl,de
    jp c,rt_pg_w_max
    ld de,65000
    push hl
    or a
    sbc hl,de
    pop hl
    jp nc,rt_pg_w_max
    ld (rt_pg_nx),hl
    pop hl
    jp rt_pg_w_next
rt_pg_w_max:
    pop hl
    ld hl,65000
    ld (rt_pg_nx),hl
rt_pg_w_done:
    ld hl,(rt_pg_nx)
    ld de,24
    add hl,de                   ; rounded up
    ld bc,0
    ld de,25
rt_pg_w_div:
    or a
    sbc hl,de
    jp c,rt_pg_w_q
    inc bc
    jp rt_pg_w_div
rt_pg_w_q:
    ld h,b
    ld l,c
    ret

; rt_pg_fill — PAGE FILL x, y, w, h: a black rectangle (rt_pg_solid).
; w = 0 or h = 0 prints nothing.
rt_pg_fill:
    call rt_pg_need
    call rt_pg_rect
    jp z,rt_pg_ok
rt_pg_fill_set:
    call rt_pg_solid
    jp rt_fio_set

; rt_pg_solid — the rectangle rt_pg_t (left, right, top, height, 1/1800")
; printed solid black, exactly. Rosanne's printer driver does not draw a
; line between the documented ends [static: PCW045.SYS block 10, #9802-#985B
; and #991E-#997B; XAnne: the owner's M12 Session 2 page at 300 dpi]:
;   os_meta_hline covers left .. right + thickness (x1 = right + t - 1 dot),
;   os_meta_vline covers top + thickness - 1 dot .. bottom (y0 moved down).
; So, whatever the printer's dot:
;   w >= h: one hline from left to right - h, h thick (Rosanne adds h back);
;   w < h:  a square at the top (an hline from left to left, w thick), then a
;           vline w thick from top to bottom: the square is what the vline
;           leaves out at its top.
; A = Rosanne's answer to the last call (0 OK, 7 no memory).
rt_pg_solid:
    ld hl,(rt_pg_t+2)
    ld de,(rt_pg_t)
    or a
    sbc hl,de                   ; HL = w
    ld de,(rt_pg_t+6)           ; DE = h
    or a
    sbc hl,de
    jp c,rt_pg_solid_tall       ; w < h
    ld hl,(rt_pg_t+2)
    or a
    sbc hl,de
    ld b,h
    ld c,l                      ; BC = right - h
    push de
    pop ix                      ; IX = h, the thickness
    ld de,(rt_pg_t)
    ld hl,(rt_pg_t+4)
    ld a,101
    call 003Bh                  ; os_meta_hline
    ret
rt_pg_solid_tall:
    call rt_pg_solid_w
    ld de,(rt_pg_t)
    ld b,d
    ld c,e                      ; BC = left: a w x w square
    ld hl,(rt_pg_t+4)
    ld a,101
    call 003Bh                  ; os_meta_hline (12 bytes, as the vline:
    call rt_pg_solid_w          ; if this one is refused, so is that)
    ld hl,(rt_pg_t+4)
    ld de,(rt_pg_t+6)
    add hl,de
    ld b,h
    ld c,l                      ; BC = bottom
    ld de,(rt_pg_t)
    ld hl,(rt_pg_t+4)
    ld a,102
    call 003Bh                  ; os_meta_vline
    ret
rt_pg_solid_w:                  ; IX = w = right - left
    ld hl,(rt_pg_t+2)
    ld de,(rt_pg_t)
    or a
    sbc hl,de
    push hl
    pop ix
    ret

; rt_pg_rect — rt_pg_args = x, y, w, h inside the page: rt_pg_t = left,
; right, top, height in 1/1800". Z = empty.
rt_pg_rect:
    ld a,(rt_pg_args+5)
    or a
    jp m,rt_pg_outside          ; w < 0
    ld a,(rt_pg_args+7)
    or a
    jp m,rt_pg_outside          ; h < 0
    ld hl,(rt_pg_args+4)
    ld de,(rt_pg_args)
    add hl,de                   ; x + w
    ld de,RT_PG_W
    call rt_pg_range
    ld (rt_pg_t+2),hl
    ld hl,(rt_pg_args+6)
    ld de,(rt_pg_args+2)
    add hl,de
    ld de,RT_PG_H
    call rt_pg_range
    ld hl,(rt_pg_args)
    ld de,RT_PG_W
    call rt_pg_range
    ld (rt_pg_t),hl
    ld hl,(rt_pg_args+2)
    ld de,RT_PG_H
    call rt_pg_range
    ld (rt_pg_t+4),hl
    ld hl,(rt_pg_args+6)
    call rt_pg_25
    ld (rt_pg_t+6),hl
    ld hl,(rt_pg_args+4)
    ld a,h
    or l
    ret z
    ld hl,(rt_pg_args+6)
    ld a,h
    or l
    ret

; rt_pg_line — PAGE LINE x1, y1, x2, y2, t: a horizontal or vertical line t
; points thick (below / right of the points).
rt_pg_line:
    call rt_pg_need
    ld hl,(rt_pg_args+8)        ; 1 <= t <= 72
    ld a,h
    or a
    jp nz,rt_pg_bad_t
    ld a,l
    or a
    jp z,rt_pg_bad_t
    cp 73
    jp nc,rt_pg_bad_t
    ld hl,(rt_pg_args+2)
    ld de,(rt_pg_args+6)
    or a
    sbc hl,de
    jp z,rt_pg_l_h
    ld hl,(rt_pg_args)
    ld de,(rt_pg_args+4)
    or a
    sbc hl,de
    jp z,rt_pg_l_v
    ld hl,rt_pg_slope_text
    ld bc,rt_pg_slope_end-rt_pg_slope_text
    jp rt_err_msg
rt_pg_slope_text:
    db "Runtime error: a printed line is horizontal or vertical at line "
rt_pg_slope_end:
rt_pg_bad_t:
    ld hl,rt_pg_thick_text
    ld bc,rt_pg_thick_end-rt_pg_thick_text
    jp rt_err_msg
rt_pg_thick_text:
    db "Runtime error: a printed line is 1 to 72 points thick at line "
rt_pg_thick_end:
rt_pg_l_h:                      ; x from the smaller to the larger, h = t
    ld hl,(rt_pg_args)
    ld de,(rt_pg_args+4)
    call rt_pg_order
    ld (rt_pg_args),hl
    ex de,hl
    or a
    sbc hl,de
    ld (rt_pg_args+4),hl        ; w = x2 - x1 (0: a point, nothing printed)
    ld hl,(rt_pg_args+8)
    ld (rt_pg_args+6),hl
    call rt_pg_rect
    jp z,rt_pg_ok
    jp rt_pg_fill_set
rt_pg_l_v:                      ; y from the smaller to the larger, w = t
    ld hl,(rt_pg_args+2)
    ld de,(rt_pg_args+6)
    call rt_pg_order
    ld (rt_pg_args+2),hl
    ex de,hl
    or a
    sbc hl,de
    ld (rt_pg_args+6),hl        ; h = y2 - y1
    ld hl,(rt_pg_args+8)
    ld (rt_pg_args+4),hl
    call rt_pg_rect             ; (y1 <> y2 here: never empty)
    jp rt_pg_fill_set
rt_pg_ok:
    xor a
    jp rt_fio_set

; rt_pg_order — HL, DE: HL = the smaller, DE = the larger (signed).
rt_pg_order:
    push hl
    or a
    sbc hl,de
    pop hl
    ret m
    ex de,hl
    ret

; rt_pg_box — PAGE BOX x, y, w, h: an outline one point thick inside the
; rectangle (w, h at least 2).
rt_pg_box:
    call rt_pg_need
    call rt_pg_rect
    jp z,rt_pg_ok
    ld hl,(rt_pg_args+4)
    dec hl
    ld a,h
    or l
    jp z,rt_pg_fill_it
    ld hl,(rt_pg_args+6)
    dec hl
    ld a,h
    or l
    jp z,rt_pg_fill_it
    ld hl,(rt_pg_t+6)
    ld (rt_pg_bh),hl            ; the height, kept
    ld hl,25
    ld (rt_pg_t+6),hl
    call rt_pg_solid            ; top
    ld hl,(rt_pg_t+4)
    ld de,(rt_pg_bh)
    add hl,de
    ld de,25
    or a
    sbc hl,de
    ld (rt_pg_t+4),hl
    call rt_pg_solid            ; bottom
    ld hl,(rt_pg_t+4)
    ld de,(rt_pg_bh)
    or a
    sbc hl,de
    ld de,25
    add hl,de
    ld (rt_pg_t+4),hl           ; the top again
    ld de,(rt_pg_t)
    call rt_pg_vbar             ; left
    ld hl,(rt_pg_t+2)
    ld de,25
    or a
    sbc hl,de
    ex de,hl
    call rt_pg_vbar             ; right
    jp rt_fio_set
rt_pg_fill_it:
    jp rt_pg_fill_set

; rt_pg_vbar — os_meta_vline at x = DE from rt_pg_t+4 down rt_pg_bh, 1 pt.
; Its top, which Rosanne leaves out (rt_pg_solid), is under the box's top
; line.
rt_pg_vbar:
    ld hl,(rt_pg_t+4)
    push hl
    ld bc,(rt_pg_bh)
    add hl,bc
    ld b,h
    ld c,l
    pop hl
    ld ix,25
    ld a,102
    call 003Bh
    ret

; rt_pg_print — PAGE PRINT: the page to the printer, then closed. IOERR =
; os_meta_print's result.
rt_pg_print:
    call rt_pg_need
    ld b,0
    ld a,103
    call 003Bh                  ; os_meta_print, full resolution
    push af
    call rt_pg_close
    pop af
    jp rt_fio_set

; rt_pg_close — PAGE CLOSE (and PAGE NEW, PAGE PRINT, the program's end):
; the open page, if any, discarded.
rt_pg_close:
    ld a,(rt_pg_open)
    or a
    ret z
    xor a
    ld (rt_pg_open),a
    ld a,105
    call 003Bh                  ; os_meta_close
    ret
    ENDIF

    IF PB_TYPO
; ============================================================================
; M15 W3 screen typography (LANGUAGE-SPEC 5.6): TYPE FONT, DRAW TYPE,
; TYPEWIDTH, TYPEHEIGHT. Rosanne's scalable typo fonts drawn on the canvas
; with os_typo_charscreen (93: "in: C = Character number, B = accent, DE = x
; in PIXELS, HL = y in PIXELS, IX(lo) = style (bit0 Bold, bit1 Italic),
; IX(hi) = mode (0 Opaque .. 3 XOR); out: A = 0 OK / 4 no font in slot / 5
; out of range / 6, 9 outside the clipping window", ROSAN283), after the
; init / list / select / define / info sequence the accepted PAGE printing
; uses (rt_pg_new, rt_pg_font).
; XAnne (owner, M15a T4a-T4e): slot 0 at 10 points, plain, bold and italic,
; mode 0, draws inside a canvas without disturbing the screen; one pixel is
; about 25/1800" (a screenshot reading). M15c (owner, XAnne): sizes up to 72
; draw without disturbing the screen; Times, bold and italic at 18.
; The guards: every character's advance is measured (os_typo_charwidth,
; 91) and drawing stops before the first character that would pass the
; canvas's right edge (italic: a quarter of the ascender earlier); and the
; line (TYPEHEIGHT) must lie in the canvas. M15c T2 (owner, XAnne): Rosanne's
; y is the baseline (text drawn at y = 40 stood above a rule at 40), so the
; runtime passes the line's top + the ascender. The screen clipping window
; is not used (os_scr_window is not called).
; Slot 0 is shared with PAGE: rt_ty_slot says which font it holds (1 the
; TYPE FONT, 2 the PAGE font) and each side defines it again only when the
; other has changed it.
; ----------------------------------------------------------------------------
rt_ty_sizes:
    db 6,8,10,11,12,14,18,24,36,72

; rt_type_font — TYPE FONT family, size [, BOLD] [, ITALIC]: rt_dw_args =
; size, +2 = RTF family (1 Times, 2 Swiss), +3 = style (bit 0 bold, 1 italic).
rt_type_font:
    ld a,(rt_dw_args+1)
    or a
    jp nz,rt_ty_bad_size
    ld a,(rt_dw_args)
    ld hl,rt_ty_sizes
    ld b,10
rt_ty_size_find:
    cp (hl)
    jp z,rt_ty_size_ok
    inc hl
    djnz rt_ty_size_find
rt_ty_bad_size:
    ld hl,rt_ty_size_text
    ld bc,rt_ty_size_end-rt_ty_size_text
    jp rt_err_msg
rt_ty_size_text:
    db "Runtime error: a type size is 6, 8, 10, 11, 12, 14, 18, 24, 36 or 72 at line "
rt_ty_size_end:
rt_ty_size_ok:
    ld (rt_ty_size),a
    ld a,(rt_dw_args+3)
    ld (rt_ty_style),a
    call rt_ty_ready
    ld a,(rt_dw_args+2)
    cp 1
    ld hl,(rt_ty_times)
    jp z,rt_ty_fam_ok
    ld hl,(rt_ty_swiss)
rt_ty_fam_ok:
    ld (rt_ty_id),hl
    jp rt_ty_want               ; defined now, so that an error is on this line

; rt_ty_ready — os_typo_init once (shared with PAGE) and the two families'
; fonts from the list: the first of RTF family 1 (Times) and of 2 (Swiss),
; each the list's first font if the family is missing.
rt_ty_ready:
    ld a,(rt_ty_init)
    or a
    ret nz
    IF PB_TYPG
    ld a,(rt_pg_typo)
    or a
    jp nz,rt_ty_list
    ENDIF
    ld a,83
    call 003Bh                  ; os_typo_init
    jp c,rt_ty_none
    IF PB_TYPG
    call rt_pg_family           ; PAGE NEW would otherwise look for it after this init
    ld a,1
    ld (rt_pg_typo),a
    ENDIF
rt_ty_list:
    ld a,84
    call 003Bh                  ; os_typo_getlist: B entries of 37 bytes at CHL
    ld a,b
    or a
    jp z,rt_ty_none
    ld (rt_ty_k),a
    xor a
    ld (rt_ty_seen),a           ; bit 0 the first, 1 Times, 2 Swiss
rt_ty_entry:
    ld b,1
    ld a,42
    call 003Bh                  ; os_get_byte_24bit, wound on: ID low
    ld a,e
    ld (rt_ty_t),a
    ld b,1
    ld a,42
    call 003Bh                  ; ID high
    ld a,e
    ld (rt_ty_t+1),a
    ld b,1
    ld a,42
    call 003Bh                  ; styles
    ld b,1
    ld a,42
    call 003Bh                  ; RTF family
    push hl
    ld hl,(rt_ty_t)
    ld a,(rt_ty_seen)
    bit 0,a
    jp nz,rt_ty_e_fam
    ld (rt_ty_times),hl         ; the first font: both fallbacks
    ld (rt_ty_swiss),hl
    or 1
rt_ty_e_fam:
    ld d,a
    ld a,e
    cp 1
    jp nz,rt_ty_e_swiss
    bit 1,d
    jp nz,rt_ty_e_done
    ld (rt_ty_times),hl
    set 1,d
    jp rt_ty_e_done
rt_ty_e_swiss:
    cp 2
    jp nz,rt_ty_e_done
    bit 2,d
    jp nz,rt_ty_e_done
    ld (rt_ty_swiss),hl
    set 2,d
rt_ty_e_done:
    ld a,d
    ld (rt_ty_seen),a
    pop hl
    ld a,33                     ; the name: 33 bytes
rt_ty_e_name:
    push af
    ld b,1
    ld a,42
    call 003Bh
    pop af
    dec a
    jp nz,rt_ty_e_name
    ld a,(rt_ty_k)
    dec a
    ld (rt_ty_k),a
    jp nz,rt_ty_entry
    ld a,1
    ld (rt_ty_init),a
    ret
rt_ty_none:
    ld hl,rt_ty_none_text
    ld bc,rt_ty_none_end-rt_ty_none_text
    jp rt_err_msg
rt_ty_none_text:
    db "Runtime error: Rosanne has no type fonts here at line "
rt_ty_none_end:

; rt_ty_want — slot 0 holds the TYPE FONT (Times 10 if none was chosen),
; and rt_ty_ascpx / rt_ty_hgt are its ascender and line height in pixels.
rt_ty_want:
    ld a,(rt_ty_size)
    or a
    jp nz,rt_ty_w_chosen
    call rt_ty_ready
    ld a,10
    ld (rt_ty_size),a
    ld hl,(rt_ty_times)
    ld (rt_ty_id),hl
rt_ty_w_chosen:
    ld a,(rt_ty_slot)
    cp 1
    jp nz,rt_ty_define
    ld a,(rt_ty_dsize)
    ld b,a
    ld a,(rt_ty_size)
    cp b
    jp nz,rt_ty_define
    ld hl,(rt_ty_did)
    ld de,(rt_ty_id)
    or a
    sbc hl,de
    ret z
rt_ty_define:
    xor a
    ld (rt_ty_slot),a           ; nothing known until it is defined
    ld e,0
    ld a,85
    call 003Bh                  ; os_typo_select slot 0
    ld a,88
    call 003Bh                  ; os_typo_clr (4: it was empty)
    ld hl,(rt_ty_id)
    ld d,0FFh                   ; every style
    ld a,(rt_ty_size)
    ld b,a
    ld a,87
    call 003Bh                  ; os_typo_def
    or a
    jp nz,rt_ty_refused
    ld a,90
    call 003Bh                  ; os_typo_info: HL -> pitch, ascender, descender
    or a
    jp nz,rt_ty_refused
    inc hl
    inc hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld c,(hl)
    inc hl
    ld b,(hl)
    push bc                     ; the descender
    ex de,hl
    push hl
    call rt_ty_px_up
    ld (rt_ty_ascpx),hl
    pop hl
    pop de
    add hl,de
    call rt_ty_px_up
    ld (rt_ty_hgt),hl
    ld hl,(rt_ty_id)
    ld (rt_ty_did),hl
    ld a,(rt_ty_size)
    ld (rt_ty_dsize),a
    ld a,1
    ld (rt_ty_slot),a
    ret
rt_ty_refused:
    ld hl,rt_ty_ref_text
    ld bc,rt_ty_ref_end-rt_ty_ref_text
    jp rt_err_msg
rt_ty_ref_text:
    db "Runtime error: Rosanne refused the type font at line "
rt_ty_ref_end:

; rt_ty_px_up — HL = HL / 25 rounded up (1/1800" to pixels). DE corrupt.
rt_ty_px_up:
    ld de,24
    add hl,de
    ld de,0
rt_ty_px_loop:
    ld a,l
    sub 25
    ld l,a
    ld a,h
    sbc a,0
    ld h,a
    jp c,rt_ty_px_done
    inc de
    jp rt_ty_px_loop
rt_ty_px_done:
    ex de,hl
    ret

; rt_ty_adv — the next character of the text at (rt_ty_p) measured: Z at its
; end; else NZ, rt_ty_ch = the character (outside 32..255 as '?'), rt_ty_npx
; / rt_ty_nrem = the pixel offset and remainder after it (rt_ty_px and
; rt_ty_rem: before it; position = (1/1800" so far + 12) / 25). A character
; the font refuses advances by nothing.
rt_ty_adv:
    ld hl,(rt_ty_p)
    ld a,(hl)
    or a
    ret z
    inc hl
    ld (rt_ty_p),hl
    cp 32
    jp nc,rt_ty_adv_ok
    ld a,'?'
rt_ty_adv_ok:
    ld (rt_ty_ch),a
    ld c,a
    ld b,0
    ld a,(rt_ty_style)
    and 1                       ; os_typo_charwidth obeys bold (bit 0) only
    ld d,a
    ld a,91
    call 003Bh                  ; os_typo_charwidth: DE = width (1/1800")
    or a
    jp z,rt_ty_adv_w
    ld de,0
rt_ty_adv_w:
    ld a,(rt_ty_rem)
    ld l,a
    ld h,0
    add hl,de
    ld de,(rt_ty_px)
rt_ty_adv_div:
    ld a,l
    sub 25
    ld c,a
    ld a,h
    sbc a,0
    jp c,rt_ty_adv_done
    ld h,a
    ld l,c
    inc de
    jp rt_ty_adv_div
rt_ty_adv_done:
    ld a,l
    ld (rt_ty_nrem),a
    ld (rt_ty_npx),de
    or 1                        ; NZ
    ret

; rt_ty_start — HL = the text: rt_ty_p, px 0, remainder 12 (rounding).
rt_ty_start:
    ld (rt_ty_p),hl
    ld hl,0
    ld (rt_ty_px),hl
    ld a,12
    ld (rt_ty_rem),a
    ret

; rt_ty_step — rt_ty_px / rt_ty_rem moved on past the character measured.
rt_ty_step:
    ld hl,(rt_ty_npx)
    ld (rt_ty_px),hl
    ld a,(rt_ty_nrem)
    ld (rt_ty_rem),a
    ret

; rt_type_width — TYPEWIDTH(text$): HL = the text; HL = its width in
; pixels in the TYPE FONT, as DRAW TYPE advances.
rt_type_width:
    push hl
    call rt_ty_want
    pop hl
    call rt_ty_start
rt_ty_tw_next:
    call rt_ty_adv
    jp z,rt_ty_tw_done
    call rt_ty_step
    jp rt_ty_tw_next
rt_ty_tw_done:
    ld hl,(rt_ty_px)
    ret

; rt_type_height — TYPEHEIGHT: HL = the TYPE FONT's line height in pixels
; (ascender + descender, rounded up).
rt_type_height:
    call rt_ty_want
    ld hl,(rt_ty_hgt)
    ret

; rt_draw_type — DRAW TYPE x, y, text$: HL = the text, rt_dw_args = x, y
; (the line's top left in the canvas). Drawn in the TYPE FONT, its style,
; mode 0 (opaque) or 3 under DRAW INK XOR, as far as it fits.
rt_draw_type:
    push hl
    call rt_cv_ready
    call rt_ty_want
    ld hl,(rt_dw_args)
    ld de,1
    ld bc,(cgcanvas+4)
    call rt_cv_span
    jp c,rt_cv_outside
    ld hl,(rt_dw_args+2)
    ld de,(rt_ty_hgt)
    ld bc,(cgcanvas+6)
    call rt_cv_span
    jp c,rt_cv_outside
    ld hl,(rt_dw_args+2)
    ld de,(cgcanvas+2)
    add hl,de
    ld de,(rt_ty_ascpx)         ; M15c T2 (XAnne): Rosanne's y is the baseline,
    add hl,de                   ; so the line's top + the ascender
    ld (rt_ty_sy),hl
    ld hl,(rt_dw_args)
    ld de,(cgcanvas)
    add hl,de
    ld (rt_ty_x0),hl
    ld hl,(cgcanvas+4)          ; the right edge: offset <= width - x
    ld de,(rt_dw_args)
    or a
    sbc hl,de
    ld a,(rt_ty_style)
    and 2
    jp z,rt_ty_upright
    ld de,(rt_ty_ascpx)         ; italic leans right: a quarter of the ascender
    srl d                       ; kept free at the edge
    rr e
    srl d
    rr e
    or a
    sbc hl,de
    jp nc,rt_ty_upright
    ld hl,0
rt_ty_upright:
    ld (rt_ty_room),hl
    ld a,(rt_dw_ink)
    cp 2
    ld a,0
    jp nz,rt_ty_mode
    ld a,3                      ; XOR
rt_ty_mode:
    ld (rt_ty_mode_b),a
    pop hl
    call rt_ty_start
    ld a,111
    call 003Bh                  ; os_mouse_off
rt_ty_d_next:
    call rt_ty_adv
    jp z,rt_ty_d_done
    ld hl,(rt_ty_room)
    ld de,(rt_ty_npx)
    or a
    sbc hl,de
    jp c,rt_ty_d_done           ; it would pass the right edge: the rest is cut
    ld a,(rt_ty_ch)
    ld c,a
    ld b,0
    ld a,(rt_ty_mode_b)
    ld h,a
    ld a,(rt_ty_style)
    ld l,a
    push hl
    pop ix                      ; IX = mode * 256 + style (an input only: no IX is live, A5)
    ld hl,(rt_ty_x0)
    ld de,(rt_ty_px)
    add hl,de
    ex de,hl                    ; DE = x
    ld hl,(rt_ty_sy)            ; HL = y
    ld a,93
    call 003Bh                  ; os_typo_charscreen
    or a
    jp nz,rt_ty_d_refused
    call rt_ty_step
    jp rt_ty_d_next
rt_ty_d_done:
    ld a,112
    call 003Bh                  ; os_mouse_on
    ret
rt_ty_d_refused:
    ld a,112
    call 003Bh                  ; os_mouse_on
    jp rt_cv_refused

; rt_ty_pgslot (with PAGE, PB_TYPG) — slot 0 holds the PAGE font again, if
; DRAW TYPE or TYPEWIDTH has defined the TYPE FONT there since.
    IF PB_TYPG
rt_ty_pgslot:
    ld a,(rt_ty_slot)
    cp 1
    ret nz                      ; 0 (none of ours) or 2: PAGE's own, or as PAGE left it
    xor a
    ld (rt_ty_slot),a
    ld e,0
    ld a,85
    call 003Bh                  ; os_typo_select slot 0
    ld a,88
    call 003Bh                  ; os_typo_clr
    ld hl,(rt_pg_id)
    ld d,0FFh
    ld a,(rt_pg_size)
    ld b,a
    ld a,87
    call 003Bh                  ; os_typo_def (a refusal: PAGE's own call reports it)
    or a
    ret nz
    ld a,2
    ld (rt_ty_slot),a
    ret
    ENDIF
    ENDIF

    IF PB_CODEBANKS
; ============================================================================
; M9 code banks (pbas/codebanks.py): procedures that live outside the
; program's own 16K block.
; ============================================================================
; The .PRG holds the resident 16K block first, then PB_CODE_N code banks,
; each padded to a multiple of 512 bytes (rt_code_tab: per bank, dw bytes in
; the file, dw 16-bit sum of those bytes). The loader reads only the first
; 16K (os_run_program, M8 research §3), so the program loads the rest itself
; — the pattern CODEPROBE proved in XAnne (stage 1 C=OK, stage 2 K=OK):
;   1. the name the loader left at #4000 (and its extension, or ".PRG")
;      is copied to the bottom quarter, where os_open_file needs it;
;   2. os_get_mem (34) for PB_CODE_N blocks, each checked as RAM (#80..#FF)
;      and owned by this program (os_get_mem_ownerid 38), as for BANKED
;      arrays (M8). This runs before rt_bank_init, so the code blocks come
;      first in allocation order and the last BANKED block stays the
;      program's last block (KI-34);
;   3. os_open_file (144) of the program's own file, read mode; the first
;      16K is skipped by reading it twice 8K into the first code block at
;      offset 0 (CODEPROBE method 1); every bank is then read in pieces of
;      at most 8K into its block at offset 0 (os_read_file 147, 24-bit
;      destination, no mapping needed); os_close_file (145);
;   4. each block is mapped at #8000 (bios_setmem2, ROSAN283 BIOS #16: "all
;      flags & regs preserved") and checked: 'P','B',k and the sum.
; Any failure: an alert naming it, every code block released, os_app_exit.
;
; ROSAN283 "Memory Layout": "Switching in further blocks of your app is up
; to you (you can do what you want with the 2nd, 3rd and 4th quarters of
; memory)". The block found at #8000 at start is put back after loading and
; before the program exits.
; ----------------------------------------------------------------------------
rt_cl_name equ 2180h            ; bottom quarter (#2000..#2FFF is the program's)
rt_cl_ext equ 21C0h

rt_code_load:
    call 0CEh                   ; bios_getmem2: the block at #8000 now
    ld (rt_code_q2),a
    ; 1. the program's file name, as CODEPROBE copies it
    ld hl,4000h
    ld de,rt_cl_name
    ld b,32
rt_cl_copy:
    ld a,(hl)
    ld (de),a
    inc hl
    inc de
    or a
    jp z,rt_cl_ext_part
    djnz rt_cl_copy
    xor a
    ld (de),a
    ld a,(hl)                   ; a 32-character name: skip its NUL too
    or a
    jp nz,rt_cl_ext_part
    inc hl
rt_cl_ext_part:
    ld a,(hl)
    cp '.'
    jp nz,rt_cl_default
    ld de,rt_cl_ext
    ld b,8
rt_cl_ext_copy:
    ld a,(hl)
    ld (de),a
    inc hl
    inc de
    or a
    jp z,rt_cl_blocks
    djnz rt_cl_ext_copy
    xor a
    ld (de),a
    jp rt_cl_blocks
rt_cl_default:
    ld hl,rt_cl_dot_prg
    ld de,rt_cl_ext
    ld bc,5
    ldir
    ; 2. the blocks
rt_cl_blocks:
    ld b,PB_CODE_N
    ld e,0
    ld a,34
    call 003Bh
    jp c,rt_code_short
    ld a,b
    or a
    jp z,rt_code_short
    cp PB_CODE_N+1
    jp nc,rt_code_short         ; more than asked for: not the documented reply
    ld (rt_code_n),a
    ld de,rt_code_list
    ld c,b
    ld b,0
    ldir                        ; the list, from the bottom quarter
    xor a
    ld (de),a
    ld a,(rt_code_n)
    cp PB_CODE_N
    jp nz,rt_code_short
    call 0CBh
    ld e,a
    ld a,38
    call 003Bh
    jp nc,rt_cl_me
    ld de,0
rt_cl_me:
    ld (rt_code_me),de
    ld hl,rt_code_list
rt_cl_owned:
    ld a,(hl)
    or a
    jp z,rt_cl_open
    cp 80h
    jp c,rt_code_short          ; not a RAM block (ROSAN283: #80..#FF)
    push hl
    ld e,a
    ld a,38
    call 003Bh
    pop hl
    jp c,rt_code_short
    ld a,d
    cp 1
    jp nz,rt_code_short         ; not owned by an application (#01xx)
    ld a,(rt_code_me+1)
    cp 1
    jp nz,rt_cl_onext           ; own id unknown: any application id
    ld a,(rt_code_me)
    cp e
    jp nz,rt_code_short         ; another application's block
rt_cl_onext:
    inc hl
    jp rt_cl_owned
    ; 3. read the banks from the program's own file
rt_cl_open:
    ld hl,rt_cl_name
    ld de,rt_cl_ext
    ld b,0
    ld a,144
    call 003Bh
    jp c,rt_code_unread
    ld a,1
    ld (rt_code_open),a
    ld de,2000h
    ld hl,0
    call rt_cl_read_first       ; skip the resident 16K: 8K ...
    jp c,rt_code_unread
    ld de,2000h
    ld hl,0
    call rt_cl_read_first       ; ... and 8K, both into the first block
    jp c,rt_code_unread
    ld hl,rt_code_list
    ld (rt_code_ptr),hl
    ld hl,rt_code_tab
    ld (rt_code_tp),hl
rt_cl_bank:
    ld hl,(rt_code_ptr)
    ld a,(hl)
    or a
    jp z,rt_cl_close
    ld (rt_code_blk),a
    ld hl,(rt_code_tp)
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    inc hl
    inc hl
    ld (rt_code_tp),hl
    ld (rt_code_left),de
    ld hl,0
    ld (rt_code_off),hl
rt_cl_piece:
    ld hl,(rt_code_left)
    ld a,h
    or l
    jp z,rt_cl_next
    ld de,2000h
    or a
    sbc hl,de
    jp nc,rt_cl_full            ; at least 8K left: read 8K
    ld de,(rt_code_left)        ; less: read the rest
    ld hl,0
rt_cl_full:
    ld (rt_code_left),hl
    push de
    ld a,(rt_code_blk)
    ld c,a
    ld hl,(rt_code_off)
    call rt_cl_read
    pop de
    jp c,rt_code_unread
    ld hl,(rt_code_off)
    add hl,de
    ld (rt_code_off),hl
    jp rt_cl_piece
rt_cl_next:
    ld hl,(rt_code_ptr)
    inc hl
    ld (rt_code_ptr),hl
    jp rt_cl_bank
rt_cl_close:
    xor a
    ld (rt_code_open),a
    ld b,0
    ld a,145
    call 003Bh                  ; os_close_file (read)
    ; 4. check every bank where it will run
    ld hl,rt_code_list
    ld (rt_code_ptr),hl
    ld hl,rt_code_tab
    ld (rt_code_tp),hl
    xor a
    ld (rt_code_k),a
rt_cl_check:
    ld hl,(rt_code_ptr)
    ld a,(hl)
    or a
    jp z,rt_cl_done
    inc hl
    ld (rt_code_ptr),hl
    call 0C2h                   ; bios_setmem2: this bank at #8000
    ld hl,rt_code_k
    inc (hl)
    ld a,(8000h)
    cp 'P'
    jp nz,rt_code_bad
    ld a,(8001h)
    cp 'B'
    jp nz,rt_code_bad
    ld a,(8002h)
    cp (hl)
    jp nz,rt_code_bad
    ld hl,(rt_code_tp)
    ld c,(hl)
    inc hl
    ld b,(hl)
    inc hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld (rt_code_tp),hl
    push de                     ; the expected sum
    ld hl,8000h
    ld de,0
rt_cl_sum:
    ld a,b
    or c
    jp z,rt_cl_summed
    ld a,(hl)
    add a,e
    ld e,a
    jp nc,rt_cl_sum_nc
    inc d
rt_cl_sum_nc:
    inc hl
    dec bc
    jp rt_cl_sum
rt_cl_summed:
    pop hl
    or a
    sbc hl,de
    jp nz,rt_code_bad
    jp rt_cl_check
rt_cl_done:
    ld a,(rt_code_q2)
    call 0C2h                   ; the block that was at #8000 before
    ret

; rt_cl_read_first — DE bytes into the first code block at HL.
rt_cl_read_first:
    ld a,(rt_code_list)
    ld c,a
; rt_cl_read — os_read_file (147): DE bytes (B = 0) to C:HL. C flag = error.
rt_cl_read:
    ld b,0
    ld a,147
    call 003Bh
    ret

rt_code_bad:
    ld a,(rt_code_q2)
    call 0C2h
rt_code_unread:
    ld a,(rt_code_open)
    or a
    jp z,rt_code_unread_msg
    xor a
    ld (rt_code_open),a
    ld b,0
    ld a,145
    call 003Bh
rt_code_unread_msg:
    ld hl,rt_code_read_alert
    ld de,rt_code_read_alert_end-rt_code_read_alert
    call rt_alert
    jp rt_exit
rt_code_short:
    ld hl,rt_code_mem_alert
    ld de,rt_code_mem_alert_end-rt_code_mem_alert
    call rt_alert
    jp rt_exit

; rt_code_free — map back the block that was at #8000, then give the code
; blocks back (os_release_mem 35, as rt_bank_free). A second call does
; nothing. Called by rt_exit, which may be reached from code in a bank: the
; bank stays readable until the release, and nothing returns into it.
rt_code_free:
    ld a,(rt_code_n)
    or a
    ret z
    xor a
    ld (rt_code_n),a
    ld a,(rt_code_q2)
    call 0C2h
    call 0CBh
    ld c,a
    ld hl,rt_code_list
    ld e,0
    ld a,35
    call 003Bh
    ret

; rt_farcall — call a procedure in a code bank (reached by `jp` from its
; resident stub). in: C = bank number 1..PB_CODE_N, HL = its jump-table
; entry at #8003+. The block now at #8000 is saved on the stack (quarter 0,
; which never moves) and put back after the procedure returns, so nested
; and cross-bank calls unwind correctly. Registers are not preserved:
; parameters and results are static variables (M7).
rt_farcall:
    push hl
    ld e,c
    ld d,0
    ld hl,rt_code_list-1
    add hl,de
    ld e,(hl)
    call 0CEh                   ; bios_getmem2 (other registers preserved)
    pop hl
    push af
    ld a,e
    call 0C2h                   ; bios_setmem2: the procedure's bank
    call rt_fc_jump
    pop af
    call 0C2h                   ; the caller's block back
    ret
rt_fc_jump:
    jp (hl)

    IF DEFINED PB_RTBANK
; ----------------------------------------------------------------------------
; M11 runtime bank (pbas/rtbank.py): runtime code that lives in a code bank.
; A moved routine's name is a resident veneer:
;     rt_x: call rt_rbc / db k / dw entry
; with k the runtime bank's number and entry its jump-table slot at #8003+.
; rt_rbc maps bank k at #8000 and enters the routine with AF, BC, DE, HL, IX
; and IY exactly as the caller left them; when it returns, the block that was
; at #8000 before is mapped back and rt_rbc returns with the routine's
; registers and flags. ROSAN283 BIOS #16 bios_setmem2: "out: all flags & regs
; preserved"; #1A bios_getmem2: "out: A = block number; all flags & other
; regs preserved". The four cells below hold values only between the entry
; and the jump into the routine, and between its return and rt_rbc's own
; return: no runtime code runs in between, so nested calls are safe. The
; saved block lives on the stack (quarter 0, which never moves).
; ----------------------------------------------------------------------------
rt_rbc:                         ; stack: [-> db k][caller's return]
    ld (rt_rb_hl),hl
    ld (rt_rb_de),de
    pop hl                      ; HL -> db k
    push af                     ; the caller's AF
    ld e,(hl)                   ; E = k
    inc hl
    ld a,(hl)
    inc hl
    ld h,(hl)
    ld l,a
    ld (rt_rb_go),hl            ; the entry
    ld d,0
    ld hl,rt_code_list-1
    add hl,de
    ld e,(hl)                   ; E = bank k's block
    call 0CEh                   ; bios_getmem2: A = the block at #8000 now
    ld d,a
    ld a,e
    call 0C2h                   ; bios_setmem2: the runtime bank
    pop af                      ; the caller's AF again
    push de                     ; D = the block to map back
    ld hl,rt_rbc_back
    push hl
    ld hl,(rt_rb_go)
    push hl
    ld hl,(rt_rb_hl)
    ld de,(rt_rb_de)
    ret                         ; into the routine; it returns to rt_rbc_back
rt_rbc_back:                    ; registers and flags: the routine's
    ld (rt_rb_hl),hl
    pop hl                      ; H = the block to map back
    ld (rt_rb_a),a
    ld a,h
    call 0C2h                   ; bios_setmem2 (all flags and registers kept)
    ld a,(rt_rb_a)
    ld hl,(rt_rb_hl)
    ret
    ENDIF

rt_cl_dot_prg: db ".PRG",0
rt_code_read_alert:
    db "Runtime error: the program's code",0
    db "could not be read from its file",0,0,1
    dw 800Dh,80FBh,0,0
    db 79,75,0
rt_code_read_alert_end:
rt_code_mem_alert:
    db "Runtime error: not enough free memory",0
    db "for the program's code",0,0,1
    dw 800Dh,80FBh,0,0
    db 79,75,0
rt_code_mem_alert_end:
    ENDIF

    IF PB_BANK
; ----------------------------------------------------------------------------
; M8 BANKED arrays (LANGUAGE-SPEC §5.4). The elements live in 16K RAM blocks
; the program gets from Rosanne, not in the program's own bank. ROSAN283
; "Memory Layout": "RAM can be got from the OS in 16k lumps ... You should
; NEVER use RAM which you haven't officially got from the OS. You must also
; remember to release RAM when you've done with it".
;   os_get_mem (34):      in B = no of 16ks, E = #00 (current app);
;                         out NC: B = no allocated (may be fewer),
;                         HL = 16-bit address of 0-terminated block list
;   os_get_mem_ownerid (38): in E = block; out NC: DE = owner (#01xx app)
;   os_release_mem (35):  in C,HL = 24-bit address of 0-terminated list,
;                         E = #00
;   os_copy_24bit (41):   in C,HL = source, B,DE = destination (24-bit),
;                         IX = length; out NC/C
; The program never maps a block itself: every access is an os_copy_24bit
; between the block and a window in the program's bank (the OS maps both;
; ROSAN283 "Addressing": the top two bits of a 14-bit address are ignored).
; An element never crosses a block end (elements per block = 16384 / size),
; so no copy relies on the documented roll-over into a next block.
; Generated data: cgbank_need (blocks), cgbank_wsize (window size),
; cgbank_win (4 read windows, at least 256 bytes, zero at start),
; cgbank_wwin (the write window); a descriptor per array: dw n, dw size,
; dw elements per block, db first slot in rt_bank_list.
; ----------------------------------------------------------------------------

; rt_bank_init — get, check and clear the blocks (before the main line).
; Fewer blocks than needed, or a block not reported as the program's own:
; release them and stop with "not enough free memory for BANKED arrays".
rt_bank_init:
    ld a,cgbank_need
    ld b,a
    ld e,0
    ld a,34
    call 003Bh
    jp c,rt_bank_short
    ld a,b
    ld (rt_bank_n),a
    or a
    jp z,rt_bank_short
    ld de,rt_bank_list
    ld c,b
    ld b,0
    ldir                        ; the list, from the bottom quarter
    xor a
    ld (de),a
    ld a,(rt_bank_n)
    cp cgbank_need
    jp c,rt_bank_short
    ; the program's own owner id: that of its image block, as the shipped
    ; PcW16 applications find it (os_get_mem_ownerid of their own block)
    call 0CBh
    ld e,a
    ld a,38
    call 003Bh
    jp nc,rt_bank_me
    ld de,0
rt_bank_me:
    ld (rt_bk_me),de
    ld hl,rt_bank_list
rt_bank_owned:
    ld a,(hl)
    or a
    jp z,rt_bank_clear
    cp 80h
    jp c,rt_bank_short          ; not a RAM block (ROSAN283: #80..#FF)
    push hl
    ld e,a
    ld a,38
    call 003Bh
    pop hl
    jp c,rt_bank_short
    ld a,d
    cp 1
    jp nz,rt_bank_short         ; not owned by an application (#01xx)
    ld a,(rt_bk_me+1)
    cp 1
    jp nz,rt_bank_next          ; own id unknown: any application id
    ld a,(rt_bk_me)
    cp e
    jp nz,rt_bank_short         ; another application's block
rt_bank_next:
    inc hl
    jp rt_bank_owned
rt_bank_clear:
    ld hl,256
    ld (rt_bk_size),hl
    ld hl,rt_bank_list
rt_bank_clear_blk:
    ld a,(hl)
    or a
    ret z
    ld (rt_bk_blk),a
    push hl
    ld hl,0
rt_bank_clear_part:
    ld (rt_bk_off),hl
    ex de,hl
    ld a,(rt_bk_blk)
    ld b,a
    call 0CBh
    ld c,a
    ld hl,cgbank_win            ; 256 zero bytes (never used yet)
    call rt_bk_copy
    ld hl,(rt_bk_off)
    ld de,256
    add hl,de
    ld a,h
    cp 40h
    jp c,rt_bank_clear_part
    pop hl
    inc hl
    jp rt_bank_clear_blk
rt_bank_short:
    call rt_bank_free
    ld hl,rt_err_bank_text
    ld bc,rt_err_bank_text_end-rt_err_bank_text
    jp rt_err_msg
rt_err_bank_text:
    db "Runtime error: not enough free memory for BANKED arrays at line "
rt_err_bank_text_end:

; rt_bank_free — give the blocks back (every exit path, through rt_exit).
; A second call does nothing.
rt_bank_free:
    ld a,(rt_bank_n)
    or a
    ret z
    xor a
    ld (rt_bank_n),a
    call 0CBh
    ld c,a
    ld hl,rt_bank_list
    ld e,0
    ld a,35
    call 003Bh
    ret

; rt_bank_get — HL = index, DE = descriptor; out HL = a read window holding
; a copy of the element (four windows in turn: a statement reads at most
; four BANKED elements, LANGUAGE-SPEC §5.4). Index outside 1..n: the array
; index error.
rt_bank_get:
    call rt_bank_locate
    ld a,(rt_bk_ring)
    inc a
    and 3
    ld (rt_bk_ring),a
    ld l,a
    ld h,0
    ld de,cgbank_wsize
    call rt_mul16
    ld de,cgbank_win
    add hl,de
    ld (rt_bk_win),hl
    ex de,hl
    call 0CBh
    ld b,a
    ld a,(rt_bk_blk)
    ld c,a
    ld hl,(rt_bk_off)
    call rt_bk_copy
    ld hl,(rt_bk_win)
    ret

; rt_bank_wref — HL = index, DE = descriptor; out HL = the write window,
; holding the element's current value (so a failed LINE INPUT # writes it
; back unchanged); rt_bank_put then stores the window into the element.
rt_bank_wref:
    call rt_bank_locate
    ld a,(rt_bk_blk)
    ld (rt_bk_wblk),a
    ld c,a
    ld hl,(rt_bk_off)
    ld (rt_bk_woff),hl
    ld de,(rt_bk_size)
    ld (rt_bk_wsize),de
    ld de,cgbank_wwin
    call 0CBh
    ld b,a
    call rt_bk_copy
    ld hl,cgbank_wwin
    ret
rt_bank_put:
    ld hl,(rt_bk_wsize)
    ld (rt_bk_size),hl
    ld a,(rt_bk_wblk)           ; rt_bk_copy's banked side (KI-34 check)
    ld (rt_bk_blk),a
    ld hl,(rt_bk_woff)
    ld (rt_bk_off),hl
    call 0CBh
    ld c,a
    ld hl,cgbank_wwin
    ld a,(rt_bk_wblk)
    ld b,a
    ld de,(rt_bk_woff)
    jp rt_bk_copy

; rt_bank_locate — HL = index, DE = descriptor; out rt_bk_blk / rt_bk_off /
; rt_bk_size: the element's block and offset (14-bit) and its size.
rt_bank_locate:
    ld a,h
    or a
    jp m,rt_index_bad
    or l
    jp z,rt_index_bad
    dec hl
    ld (rt_bk_i),hl             ; 0-based
    ex de,hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    push hl
    ld hl,(rt_bk_i)
    or a
    sbc hl,de                   ; carry when i - 1 < n
    pop hl
    jp nc,rt_index_bad
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld (rt_bk_size),de
    ld c,(hl)
    inc hl
    ld b,(hl)
    inc hl
    ld a,(hl)
    ld (rt_bk_slot),a
    ld hl,(rt_bk_i)
    call rt_bk_udiv             ; HL = block within the array, DE = element
    ld a,(rt_bk_slot)
    add a,l
    ld l,a
    ld h,0
    push de
    ld de,rt_bank_list
    add hl,de
    ld a,(hl)
    ld (rt_bk_blk),a
    pop hl
    ld de,(rt_bk_size)
    call rt_mul16               ; element * size < 16384
    ld (rt_bk_off),hl
    ret

; rt_bk_udiv — HL = HL / BC, DE = HL mod BC (unsigned; BC < 32768).
rt_bk_udiv:
    ld de,0
    ld a,16
rt_bk_udiv_bit:
    add hl,hl
    ex de,hl
    adc hl,hl
    or a
    sbc hl,bc
    jp nc,rt_bk_udiv_one
    add hl,bc
    ex de,hl
    jp rt_bk_udiv_next
rt_bk_udiv_one:
    ex de,hl
    inc hl
rt_bk_udiv_next:
    dec a
    jp nz,rt_bk_udiv_bit
    ret

; rt_bk_copy — os_copy_24bit of rt_bk_size bytes from C,HL to B,DE. IX is
; loaded only as the call's length input (nothing is kept in IX). The banked
; side of every copy is rt_bk_blk : rt_bk_off (callers set both).
; An error (carry) stops the program, with one exception (KNOWN-ISSUES KI-34,
; owner XAnne MEMDIAG): Rosanne's os_copy_24bit (PCW045.SYS block 6 #5CB6)
; looks for the owner's next block after the last byte too, so a copy that
; ends exactly at the end of the owner's LAST block returns carry although
; every byte was copied (MEMDIAG: G4=C ok, B=ok). That carry is accepted
; only when the banked side ended exactly at #4000 AND its block is the last
; one in rt_bank_list (the last in Rosanne's allocation order); any other
; carry is a real failure.
rt_bk_copy:
    push hl
    ld hl,(rt_bk_size)
    push hl
    pop ix
    pop hl
    ld a,41
    call 003Bh
    ret nc
    ld hl,(rt_bk_off)
    ld de,(rt_bk_size)
    add hl,de
    ld a,h
    cp 40h
    jp nz,rt_bk_copy_bad        ; did not end exactly at the block end
    ld a,l
    or a
    jp nz,rt_bk_copy_bad
    ld a,(rt_bank_n)
    or a
    jp z,rt_bk_copy_bad         ; no blocks held
    ld e,a
    ld d,0
    ld hl,rt_bank_list-1
    add hl,de                   ; the last block in the list
    ld a,(rt_bk_blk)
    cp (hl)
    ret z                       ; the harmless end-of-last-block carry
rt_bk_copy_bad:
    ld hl,rt_err_bkcopy_text
    ld bc,rt_err_bkcopy_text_end-rt_err_bkcopy_text
    jp rt_err_msg
rt_err_bkcopy_text:
    db "Runtime error: a BANKED array block could not be copied at line "
rt_err_bkcopy_text_end:
    ENDIF

    IF PB_DIV + PB_VAL + PB_CHR + PB_LABELS + PB_RADIO + PB_NUMBERS + PB_ASK + PB_ARRAYS + PB_CTL2 + PB_IMATH + PB_REAL + PB_BANK + PB_CANVAS + PB_TEXT + PB_PAGE + PB_KEYDOWN  ; M14 (D1): KEYDOWN's range check reports through rt_err_msg

; ----------------------------------------------------------------------------
; rt_err_msg — report "<text><line>" and exit (M5b runtime errors; M5d:
; unsupported label character).
; in:  HL = text, BC = its length; never returns.
; ----------------------------------------------------------------------------
rt_err_msg:
    push hl
    ld hl,rt_alert_buf+160
    ld (rt_dst_end),hl
    pop hl
    ld de,rt_alert_buf
    call rt_str_copy
    ld hl,(rt_err_line)
    call rt_append_int
    call rt_alert_dynamic
    jp rt_exit

    ENDIF

; ============================================================================
; Files (M4): FILESAVE / FILELOAD (LANGUAGE-SPEC.md section 7)
; ============================================================================
; Assembled only for programs that use FILESAVE or FILELOAD (the generated
; header defines PB_FILES 0/1 and, when 1, PB_FILE_DEVICE and the
; pb_file_path string). Every operation is self-contained: it selects the
; device and folder, opens, transfers, closes, and reports with an alert. No
; file is ever left open when a routine returns (os_app_exit would also close
; one: ROSAN283 "os_app_exit automatically closes any opened read and/or
; write files").
;
; ROSAN283.DOC, "THE FILING FUNCTIONS" (function numbers from
; OSCALLS.INC.txt, counted from 1 as everywhere in this file; POC-proven
; values in POC/NOTES.asm):
;   os_set_device  127  "in: B 1 = Floppy / 2 = Flash; out: NC OK / C Invalid
;                        device number"
;   os_set_cwd     135  "in: HL = 16-bit address of 0-terminated path in
;                        bottom quarter of memory. Must be enough space at HL
;                        to accept new path; out: NC OK / C A = #03 Path Not
;                        Found, #B7 Invalid name, #BA Too Big (exceeds 64
;                        chars)"
;   os_open_file   144  "in: HL = filename, DE = extension (incl .), both
;                        0-terminated in bottom quarter of memory; B = access
;                        mode 0 / 1 = read / write; out: NC OK / C A = #02
;                        File Not Found, #04 Too many open files, #05 Access
;                        Denied"
;   os_close_file  145  "in: B = access mode; out: NC OK / C A = #02 No Open
;                        File"
;   os_write_file  146  "in: CHL = 24-bit address to write data from, BDE =
;                        24-bit length; out: NC OK / C A = #02 File Not Open,
;                        #08 Insufficient RAM, #A3 Disk Full (no data has been
;                        written)"
;   os_read_file   147  "in: CHL = 24-bit address to load data to (there must
;                        be enough space at CHL to allow RAM to be filled up
;                        with the remainder of the last 512-/510-byte block
;                        read), BDE = 24-bit length; out: NC OK / C A = #02,
;                        #08, #A1 Premature EoF (BDE = amount NOT loaded, CHL
;                        = filesize)"
;   "All registers which are not specified on exit are assumed corrupted", so
;   every value that must survive a call lives in rt_file_* memory cells.
;
; Bottom-quarter workspace: the path, file name and extension must be "in
; bottom quarter of memory". ROSAN283 'Memory Layout': "AP may use
; #2000...#2FFF of this as its own". The POC used #2100 (path, then name) and
; #2120 (extension) — kept, XAnne-proven (POC/NOTES.asm pb_filesave_0). The
; path area is 65 bytes (#2100-#2140: a 64-character path plus NUL, the
; os_get_cwd buffer rule) because os_set_cwd may write the new path back;
; the name and extension are copied only after os_set_cwd returns.
;
; Policy (LANGUAGE-SPEC.md section 7, M4 decisions):
;   * FILESAVE writes exactly the text's bytes (no NUL, no line ending) to
;     the named file. os_open_file for write is used as the POC used it; the
;     ROSAN283 text does not say whether it truncates an existing longer
;     file; XAnne confirmed it does (F1: ROUNDTRP left exactly "Short").
;     An empty string is saved by open + close with no os_write_file call
;     (a zero BDE length is not documented).
;   * FILELOAD reads the file one byte per os_read_file call and counts the
;     calls that return NC; the first C with A=#A1 ends the file (M4 repair:
;     the CHL/BDE values of #A1 are not used — in XAnne they did not match
;     the ROSAN283 wording, see "rt_file_load_read"):
;       capacity bytes read -> the file is too long: refused, variable kept;
;       #A1 earlier         -> the file fits: copied + NUL;
;       any other error     -> failure, variable kept.
;     The read buffer is 640 bytes (byte i lands at +i, i <= 126; a fill of
;     up to 511 more bytes stays inside it under either reading of the
;     ROSAN283 block-fill rule, see "rt_file_load_read"). A file containing a zero byte cannot be a STRING
;     and is refused ("not text"). The variable is changed only after every
;     check has passed, through rt_put.
;   * Every operation ends with exactly one alert naming the file:
;     "File saved: N.E" / "File loaded: N.E" or "File not saved: N.E
;     (reason)" / "File not loaded: N.E (reason)".
; ============================================================================
    IF PB_FILES

rt_low_path equ 2100h
rt_low_name equ 2100h
rt_low_ext equ 2120h

; ----------------------------------------------------------------------------
; rt_file_save — FILESAVE: write the NUL-terminated text in rt_file_buf
; (built there by generated code through rt_put) to the file.
;
; in:  HL = file descriptor (stem NUL, extension-with-dot NUL)
; out: none (an alert reports the outcome)
; clobbers: AF, BC, DE, HL
; ----------------------------------------------------------------------------
rt_file_save:
    ld (rt_file_desc),hl
    xor a
    ld (rt_file_op),a
    call rt_file_prepare
    jp c,rt_file_report
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld b,1
    ld a,144
    call 003Bh
    jp c,rt_file_os_error
    ld hl,rt_file_buf
    call rt_str_len
    ld a,c
    ld (rt_file_len),a
    or a
    jp z,rt_file_save_close
    call 0CBh
    ld c,a
    ld hl,rt_file_buf
    ld b,0
    ld d,0
    ld a,(rt_file_len)
    ld e,a
    ld a,146
    call 003Bh
    jp nc,rt_file_save_close
    ld (rt_file_code),a
    ld a,7
    ld (rt_file_reason),a
    ld b,1
    ld a,145
    call 003Bh
    jp rt_file_report
rt_file_save_close:
    ld b,1
    ld a,145
    call 003Bh
    jp c,rt_file_os_error
    jp rt_file_report

; ----------------------------------------------------------------------------
; rt_file_load — FILELOAD: replace a STRING variable with a file's contents.
;
; in:  HL = file descriptor, DE = variable address, C = variable capacity
;      (bytes including the NUL; 2..127)
; out: none (an alert reports the outcome); the variable is changed only on
;      success
; clobbers: AF, BC, DE, HL
; ----------------------------------------------------------------------------
rt_file_load:
    ld (rt_file_desc),hl
    ex de,hl
    ld (rt_file_var),hl
    ld a,c
    ld (rt_file_cap),a
    ld a,1
    ld (rt_file_op),a
    call rt_file_prepare
    jp c,rt_file_report
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld b,0
    ld a,144
    call 003Bh
    jp nc,rt_file_load_read
    cp 2
    jp nz,rt_file_os_error
    ld a,2
    ld (rt_file_reason),a
    jp rt_file_report
rt_file_load_read:
    ; One byte per os_read_file call (M4 repair). The length is the count of
    ; reads that returned NC ("OK"); the first #A1 ends the file. Nothing is
    ; inferred from the CHL / BDE values of an #A1 result: in XAnne they did
    ; not match ROSAN283's "BDE = amount NOT loaded, CHL = filesize" reading
    ; (owner's ROUNDTRP run; xanne/readdiag.asm records the real values).
    ; Byte i is read to rt_file_buf+i (i <= capacity-1 <= 126). ROSAN283:
    ; "there must be enough space at CHL to allow RAM to be filled up with
    ; the remainder of the last 512-/510-byte block read". Read by file
    ; position that ends at rt_file_buf+512; read relative to the request,
    ; it is up to 511 bytes after the byte requested, i.e. rt_file_buf+638
    ; at most. The 640-byte buffer holds both. At most capacity reads: the
    ; capacity-th successful one proves the file is too long.
    ld hl,rt_file_buf+639
    ld (rt_dst_end),hl          ; the buffer is the active destination
    xor a
    ld (rt_file_len),a
rt_file_load_next:
    ld a,(rt_file_len)
    ld e,a
    ld d,0
    ld hl,rt_file_buf
    add hl,de
    call 0CBh
    ld c,a
    ld b,0
    ld d,0
    ld e,1
    ld a,147
    call 003Bh
    jp c,rt_file_load_eof
    ld a,(rt_file_cap)
    ld b,a
    ld a,(rt_file_len)
    inc a
    ld (rt_file_len),a
    cp b
    jp z,rt_file_load_long
    jp rt_file_load_next
rt_file_load_eof:
    cp 0A1h
    jp nz,rt_file_load_oserr
    ; End of file after rt_file_len bytes (< capacity). A zero byte cannot
    ; be part of a STRING: refuse the file rather than cut it.
    ld a,(rt_file_len)
    or a
    jp z,rt_file_load_close
    ld b,a
    ld hl,rt_file_buf
rt_file_load_scan:
    ld a,(hl)
    or a
    jp z,rt_file_load_nottext
    inc hl
    djnz rt_file_load_scan
    jp rt_file_load_close
rt_file_load_long:
    ld a,3
    jp rt_file_load_fail
rt_file_load_nottext:
    ld a,4
    jp rt_file_load_fail
rt_file_load_oserr:
    ld (rt_file_code),a
    ld a,7
rt_file_load_fail:
    ld (rt_file_reason),a
rt_file_load_close:
    ld b,0
    ld a,145
    call 003Bh
    jp nc,rt_file_load_closed
    ld b,a
    ld a,(rt_file_reason)
    or a
    jp nz,rt_file_report
    ld a,b
    jp rt_file_os_error
rt_file_load_closed:
    ld a,(rt_file_reason)
    or a
    jp nz,rt_file_report
    ; Every check passed: copy rt_file_len bytes + NUL into the variable,
    ; through rt_put with the variable as the active destination.
    ld a,(rt_file_cap)
    dec a
    ld e,a
    ld d,0
    ld hl,(rt_file_var)
    add hl,de
    ld (rt_dst_end),hl
    ld de,(rt_file_var)
    ld hl,rt_file_buf
    ld a,(rt_file_len)
    or a
    jp z,rt_file_load_term
    ld b,a
rt_file_load_copy:
    ld a,(hl)
    call rt_put
    inc hl
    djnz rt_file_load_copy
rt_file_load_term:
    xor a
    ld (de),a
    jp rt_file_report

; ----------------------------------------------------------------------------
; rt_file_prepare — select the program's device and folder, then copy the
; descriptor's name and extension to the bottom-quarter workspace.
;
; in:  rt_file_desc
; out: NC = ready; C = failed with rt_file_reason (and rt_file_code) set.
;      rt_file_reason is 0 on entry to every operation (set here).
; clobbers: AF, BC, DE, HL
; ----------------------------------------------------------------------------
rt_file_prepare:
    xor a
    ld (rt_file_reason),a
    ld b,PB_FILE_DEVICE
    ld a,127
    call 003Bh
    jp nc,rt_file_prep_cwd
    ld a,6
    ld (rt_file_reason),a
    scf
    ret
rt_file_prep_cwd:
    ld hl,pb_file_path
    ld de,rt_low_path
    call rt_low_copy
    ld hl,rt_low_path
    ld a,135
    call 003Bh
    jp nc,rt_file_prep_name
    cp 3
    jp nz,rt_file_prep_err
    ld a,1
    ld (rt_file_reason),a
    scf
    ret
rt_file_prep_err:
    ld (rt_file_code),a
    ld a,7
    ld (rt_file_reason),a
    scf
    ret
rt_file_prep_name:
    ld hl,(rt_file_desc)
    ld de,rt_low_name
    call rt_low_copy
    ld de,rt_low_ext
    call rt_low_copy
    or a
    ret

; ----------------------------------------------------------------------------
; rt_low_copy — copy a NUL-terminated compiler-emitted string (path <= 63,
; stem <= 8, extension <= 4 bytes; validated at compile time by
; pbas/files.py and semantics) to the bottom-quarter workspace.
;
; in:  HL = source, DE = destination
; out: HL = one past the source NUL, DE = one past the copied NUL
; clobbers: AF
; ----------------------------------------------------------------------------
rt_low_copy:
    ld a,(hl)
    ld (de),a
    inc hl
    inc de
    or a
    jp nz,rt_low_copy
    ret

; ----------------------------------------------------------------------------
; rt_file_os_error — record an unexpected OS error code (A), then report.
; Reached by jp at the level of rt_file_save / rt_file_load.
; ----------------------------------------------------------------------------
rt_file_os_error:
    ld (rt_file_code),a
    ld a,7
    ld (rt_file_reason),a
    jp rt_file_report

; ----------------------------------------------------------------------------
; rt_file_report — show the outcome alert and return to the generated code
; that called rt_file_save / rt_file_load (reached by jp at that level).
;
; "File saved: " / "File not saved: " / "File loaded: " / "File not
; loaded: ", the file name, and for a failure " (" reason ")":
;   1 folder not found (os_set_cwd #03)   2 not found (os_open_file #02)
;   3 longer than N characters            4 not text (contains a zero byte)
;   6 drive error (os_set_device)         (5 is unused since the M4 repair)
;   7 error #XX (any other OS error code, in hex as ROSAN283 writes them)
; At most 17 + 12 + 30 bytes, inside the 160-byte alert text area.
; ----------------------------------------------------------------------------
rt_file_report:
    ld hl,rt_alert_buf+160
    ld (rt_dst_end),hl
    ld de,rt_alert_buf
    ld a,(rt_file_op)
    or a
    ld hl,rt_file_t_saved
    jp z,rt_file_rep_op
    ld hl,rt_file_t_loaded
rt_file_rep_op:
    ld a,(rt_file_reason)
    or a
    jp z,rt_file_rep_head
    ld hl,rt_file_t_not
    ld bc,9
    call rt_str_copy
    ld a,(rt_file_op)
    or a
    ld hl,rt_file_t_saved+5
    jp z,rt_file_rep_head
    ld hl,rt_file_t_loaded+5
rt_file_rep_head:
    ld bc,16
    call rt_str_copy
    ld hl,(rt_file_desc)
    ld bc,9
    call rt_str_copy
    inc hl
    ld bc,5
    call rt_str_copy
    ld a,(rt_file_reason)
    or a
    jp z,rt_file_rep_show
    ld hl,rt_file_t_open
    ld bc,2
    call rt_str_copy
    ld a,(rt_file_reason)
    ld hl,rt_file_t_folder
    cp 1
    jp z,rt_file_rep_text
    ld hl,rt_file_t_folder+7
    cp 2
    jp z,rt_file_rep_text
    ld hl,rt_file_t_nottext
    cp 4
    jp z,rt_file_rep_text
    ld hl,rt_file_t_drive
    cp 6
    jp z,rt_file_rep_text
    cp 3
    jp z,rt_file_rep_long
    ld hl,rt_file_t_error
    ld bc,7
    call rt_str_copy
    ld a,(rt_file_code)
    call rt_put_hex
    jp rt_file_rep_close
rt_file_rep_long:
    ld hl,rt_file_t_longer
    ld bc,12
    call rt_str_copy
    ld a,(rt_file_cap)
    dec a
    ld l,a
    ld h,0
    call rt_append_int
    ld hl,rt_file_t_chars
rt_file_rep_text:
    ld bc,16
    call rt_str_copy
rt_file_rep_close:
    ld a,41
    call rt_put
rt_file_rep_show:
    call rt_alert_dynamic
    ret

; ----------------------------------------------------------------------------
; rt_put_hex — append A as two upper-case hex digits through rt_put.
; in:  A, DE, rt_dst_end; out: DE advanced by 2; clobbers: AF, B
; ----------------------------------------------------------------------------
rt_put_hex:
    ld b,a
    srl a
    srl a
    srl a
    srl a
    call rt_put_nibble
    ld a,b
    and 15
    jp rt_put_nibble

; rt_put_nibble — append A (0..15) as one hex digit through rt_put.
rt_put_nibble:
    add a,48
    cp 58
    jp c,rt_put_nibble_out
    add a,7
rt_put_nibble_out:
    jp rt_put

; Report texts (NUL-terminated; rt_file_t_saved+5 is "saved: ", etc.).
    IF PB_FIO
; ============================================================================
; M7 sequential files (LANGUAGE-SPEC §7.1): OPEN / CLOSE / PRINT # /
; LINE INPUT # / EOF / KILL / NAME, outcome in IOERR (rt_fio_err).
; ============================================================================
; Channels #1 and #2; each is closed (0), INPUT (1) or OUTPUT (2) in
; rt_fio_mode. Rosanne allows one file open for read and one for write
; (os_open_file "#04 Too many open files for requested access mode"), so at
; most one channel reads. Reading is one byte per os_read_file call into
; rt_file_buf+0 (the M4 pattern, XAnne-proven; the 640-byte buffer takes the
; "remainder of the last block" fill), with one byte of look-ahead
; (rt_fio_ahead, rt_fio_state 1 = a byte is waiting, 2 = end of file or a
; read error in rt_fio_rerr), so EOF is known before LINE INPUT is tried.
; Lines are written as text + CR LF; read up to LF, CR dropped.
; IOERR: 0 OK; a Rosanne code (2 not found, 3 folder not found, 4 too many
; open files, 5 access denied, #13 write protected, #A3 disk full, ...);
; 240 drive error, 241 channel already open, 242 channel not open for that,
; 243 line longer than the variable, 244 line contains a zero byte,
; 245 nothing left to read. A failed operation changes no variable.
; ----------------------------------------------------------------------------

; rt_fio_open — in: HL = file descriptor, B = 0 read / 1 write, C = channel.
rt_fio_open:
    ld (rt_file_desc),hl
    ld a,b
    ld (rt_fio_new),a
    ld a,c
    ld (rt_fio_chan),a
    call rt_fio_slot
    ld a,(hl)
    or a
    ld a,241
    jp nz,rt_fio_set
    call rt_file_prepare
    jp c,rt_fio_prep_fail
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld a,(rt_fio_new)
    ld b,a
    ld a,144
    call 003Bh
    jp c,rt_fio_set
    call rt_fio_slot
    ld a,(rt_fio_new)
    inc a
    ld (hl),a
    cp 1
    jp nz,rt_fio_ok
    xor a
    ld (rt_fio_rerr),a
    call rt_fio_fetch
    jp rt_fio_ok

; rt_fio_prep_fail — map rt_file_prepare's reason to an IOERR code.
rt_fio_prep_fail:
    ld a,(rt_file_reason)
    cp 1
    ld a,3                      ; os_set_cwd #03 Path Not Found
    jp z,rt_fio_set
    ld a,(rt_file_reason)
    cp 6
    ld a,240                    ; os_set_device failed
    jp z,rt_fio_set
    ld a,(rt_file_code)
    jp rt_fio_set

; rt_fio_slot — HL = the mode cell of channel rt_fio_chan (1 or 2).
rt_fio_slot:
    ld hl,rt_fio_mode-1
    ld a,(rt_fio_chan)
    ld e,a
    ld d,0
    add hl,de
    ret

; rt_fio_fetch — read the next byte into rt_fio_ahead (state 1), or record
; the end of the file / a read error (state 2).
rt_fio_fetch:
    ld hl,rt_file_buf+639
    ld (rt_dst_end),hl          ; the buffer is the active destination (as M4)
    call 0CBh
    ld c,a
    ld hl,rt_file_buf
    ld b,0
    ld de,1
    ld a,147
    call 003Bh
    jp c,rt_fio_fetch_end
    ld a,(rt_file_buf)
    ld (rt_fio_ahead),a
    ld a,1
    ld (rt_fio_state),a
    ret
rt_fio_fetch_end:
    cp 0A1h                     ; "Premature EoF": the end of the file
    jp z,rt_fio_fetch_eof
    ld (rt_fio_rerr),a
rt_fio_fetch_eof:
    ld a,2
    ld (rt_fio_state),a
    ret

; rt_fio_close — in: C = channel. rt_fio_close_all: every open channel
; (IOERR = the first error, else 0).
rt_fio_close:
    ld a,c
    ld (rt_fio_chan),a
    call rt_fio_slot
    ld a,(hl)
    or a
    ld a,242
    jp z,rt_fio_set
    ld a,(hl)
    ld (hl),0
    dec a
    ld b,a
    ld a,145
    call 003Bh
    jp c,rt_fio_set
    jp rt_fio_ok
rt_fio_close_all:
    xor a
    ld (rt_fio_new),a           ; the first error seen
    ld c,1
    call rt_fio_close_one
    ld c,2
    call rt_fio_close_one
    ld a,(rt_fio_new)
    jp rt_fio_set
rt_fio_close_one:
    ld a,c
    ld (rt_fio_chan),a
    call rt_fio_slot
    ld a,(hl)
    or a
    ret z
    call rt_fio_close
    ld a,(rt_fio_err)
    or a
    ret z
    ld b,a
    ld a,(rt_fio_new)
    or a
    ret nz
    ld a,b
    ld (rt_fio_new),a
    ret

; rt_fio_print — in: C = channel; the line's text is NUL-terminated in
; rt_file_buf (at most 127 bytes, built by the generated code under rt_put).
; CR LF is added after it (inside the 640-byte buffer) and the whole line is
; written with one os_write_file from the app bank.
rt_fio_print:
    ld a,c
    ld (rt_fio_chan),a
    call rt_fio_slot
    ld a,(hl)
    cp 2
    ld a,242
    jp nz,rt_fio_set
    ld hl,rt_file_buf
    call rt_str_len
    ld hl,rt_file_buf
    add hl,bc
    ld (hl),0Dh
    inc hl
    ld (hl),0Ah
    inc bc
    inc bc
    ld d,b
    ld e,c
    ld b,0
    call 0CBh
    ld c,a
    ld hl,rt_file_buf
    ld a,146
    call 003Bh
    jp c,rt_fio_set
    jp rt_fio_ok

; rt_fio_input — LINE INPUT. in: HL = STRING destination, B = its capacity,
; C = channel. Bytes up to LF (or the end of the file) are collected in
; rt_fio_line; CR is dropped. Too long (243) or containing a zero byte
; (244): the rest of the line is skipped and the variable is unchanged.
; Nothing left (245) or a read error (its code): unchanged.
rt_fio_input:
    ld (rt_file_var),hl
    ld a,b
    ld (rt_file_cap),a
    ld a,c
    ld (rt_fio_chan),a
    call rt_fio_slot
    ld a,(hl)
    cp 1
    ld a,242
    jp nz,rt_fio_set
    ld a,(rt_fio_state)
    cp 1
    jp nz,rt_fio_input_none
    xor a
    ld (rt_file_len),a
    ld (rt_fio_flags),a
rt_fio_input_next:
    ld a,(rt_fio_state)
    cp 1
    jp nz,rt_fio_input_end
    ld a,(rt_fio_ahead)
    ld (rt_fio_byte),a
    call rt_fio_fetch
    ld a,(rt_fio_byte)
    cp 0Ah
    jp z,rt_fio_input_end
    cp 0Dh
    jp z,rt_fio_input_next
    or a
    jp nz,rt_fio_input_keep
    ld a,(rt_fio_flags)
    or 2
    ld (rt_fio_flags),a
    jp rt_fio_input_next
rt_fio_input_keep:
    ld a,(rt_file_cap)
    dec a
    ld b,a
    ld a,(rt_file_len)
    cp b
    jp c,rt_fio_input_store
    ld a,(rt_fio_flags)
    or 1
    ld (rt_fio_flags),a
    jp rt_fio_input_next
rt_fio_input_store:
    ld e,a
    ld d,0
    inc a
    ld (rt_file_len),a
    ld hl,rt_fio_line
    add hl,de
    ld a,(rt_fio_byte)
    ld (hl),a
    jp rt_fio_input_next
rt_fio_input_end:
    ld a,(rt_fio_rerr)
    or a
    jp nz,rt_fio_set
    ld a,(rt_fio_flags)
    and 1
    ld a,243
    jp nz,rt_fio_set
    ld a,(rt_fio_flags)
    and 2
    ld a,244
    jp nz,rt_fio_set
    ; copy rt_file_len bytes + NUL into the variable through rt_put
    ld a,(rt_file_cap)
    dec a
    ld e,a
    ld d,0
    ld hl,(rt_file_var)
    add hl,de
    ld (rt_dst_end),hl
    ld de,(rt_file_var)
    ld hl,rt_fio_line
    ld a,(rt_file_len)
    or a
    jp z,rt_fio_input_term
    ld b,a
rt_fio_input_copy:
    ld a,(hl)
    call rt_put
    inc hl
    djnz rt_fio_input_copy
rt_fio_input_term:
    xor a
    ld (de),a
    jp rt_fio_ok
rt_fio_input_none:
    ld a,(rt_fio_rerr)
    or a
    jp nz,rt_fio_set
    ld a,245
    jp rt_fio_set

; rt_fio_eof — in: C = channel; HL = 1 (TRUE) unless the channel is open
; for INPUT with a byte waiting. IOERR is not changed.
rt_fio_eof:
    ld a,c
    ld (rt_fio_chan),a
    call rt_fio_slot
    ld a,(hl)
    ld hl,1
    cp 1
    ret nz
    ld a,(rt_fio_state)
    cp 1
    ret nz
    dec hl
    ret

; rt_fio_kill — KILL: in HL = descriptor; os_delete_file in the program's
; folder. rt_fio_name — NAME: HL = old, DE = new descriptor; the new name
; and extension go to #2140 / #2160 of the bottom-quarter workspace
; (ROSAN283 os_rename_file: IX, IY = new name, extension; B = #00 file).
rt_fio_kill:
    ld (rt_file_desc),hl
    call rt_file_prepare
    jp c,rt_fio_prep_fail
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld a,153
    call 003Bh
    jp c,rt_fio_set
    jp rt_fio_ok
rt_fio_name:
    ld (rt_file_desc),hl
    ld (rt_fio_desc2),de
    call rt_file_prepare
    jp c,rt_fio_prep_fail
    ld hl,(rt_fio_desc2)
    ld de,rt_low_name2
    call rt_low_copy
    ld de,rt_low_ext2
    call rt_low_copy
    ld hl,rt_low_name
    ld de,rt_low_ext
    ld ix,rt_low_name2
    ld iy,rt_low_ext2
    ld b,0
    ld a,154
    call 003Bh
    jp c,rt_fio_set
rt_fio_ok:
    xor a
rt_fio_set:
    ld l,a
    ld h,0
    ld (rt_fio_err),hl
    ret

rt_low_name2 equ 2140h
rt_low_ext2 equ 2160h
    ENDIF

rt_file_t_saved:
    db "File saved: ",0
rt_file_t_loaded:
    db "File loaded: ",0
rt_file_t_not:
    db "File not ",0
rt_file_t_open:
    db " (",0
rt_file_t_folder:
    db "folder not found",0
rt_file_t_nottext:
    db "not text",0
rt_file_t_drive:
    db "drive error",0
rt_file_t_error:
    db "error #",0
rt_file_t_longer:
    db "longer than ",0
rt_file_t_chars:
    db " characters",0

    ENDIF

; ============================================================================
; Runtime data (referenced by generated code as well as by rt_* routines)
; ============================================================================

; ----------------------------------------------------------------------------
; rt_alert_buf — dynamic alert definition buffer: text bytes written by
; generated code through rt_put (rt_dst_end = rt_alert_buf+160), then
; rt_alert_dynamic adds 0 (line terminator), 0 (end of text), 1 (button
; count) and the 11 trailer bytes copied from rt_alert_keys.
; Capacity: 160 bytes of text (ALERT_BUFFER_SIZE; LANGUAGE-SPEC.md section 6
; and pbas/policy.py) + 3 trailer bytes + 11 keys/title bytes = 174.
; 160 is the size of the POC's XAnne-proven dyn_message buffer
; (POC/NOTES.asm:545).
; ----------------------------------------------------------------------------
rt_alert_buf:
    defs 174

; ----------------------------------------------------------------------------
; rt_alert_keys — alert trailer: two action keys, 800Dh (Return) and 80FBh
; (Escape), in the ROSAN283 'os_alert' button format ("4 Words for keys (
; 4 pairs of Ascii, Shift [#80=ignore] )"), the remaining two key words 0,
; then the 0-terminated "OK" button title. POC-proven (POC/NOTES.asm:543-544,
; dyn_keys).
; ----------------------------------------------------------------------------
rt_alert_keys:
    dw 800Dh,80FBh,0,0
    db 79,75,0

; ----------------------------------------------------------------------------
; rt_cmp_buf1 / rt_cmp_buf2 — scratch for *computed* STRING operands of
; = / == / <> and LEN (STR$, substrings), 128 bytes each: up to 127 text
; bytes (SCRATCH_STRING_MAX in pbas/policy.py, enforced at compile time)
; plus the NUL. Literal and variable operands are compared in place.
; ----------------------------------------------------------------------------
rt_cmp_buf1:
    defs 128
rt_cmp_buf2:
    defs 128

    IF PB_TEXTW
; ----------------------------------------------------------------------------
; rt_tw_buf — TEXTWIDTH's os_dialog_string_width block (M11 corrective):
; +0 font, +1 alignment, +2 style, +3 mode, +4/+6 x, y (unused), +8 the
; text: at most 127 characters and the NUL. A program with a canvas shares
; DRAW TEXT's block (rt_ds_buf, same layout and size; its equ follows
; rt_ds_buf below): each fills it and makes its call before returning, and
; a DRAW TEXT's text is complete (any TEXTWIDTH in it already done) before
; rt_draw_text fills the block.
; ----------------------------------------------------------------------------
    IF PB_CANVAS
    ELSE
rt_tw_buf:
    defs 136
    ENDIF
    ENDIF

; ----------------------------------------------------------------------------
; rt_int_scratch — decimal conversion workspace for rt_append_int:
; byte 0 is the "digit seen" flag, byte 1 the current digit count.
; ----------------------------------------------------------------------------
rt_int_scratch:
    defs 2

; ----------------------------------------------------------------------------
; rt_dst_end — address of the last byte of the active string destination
; (the byte reserved for its NUL). Set by generated code before each string
; build; read by rt_put.
; ----------------------------------------------------------------------------
rt_dst_end:
    defs 2

; ----------------------------------------------------------------------------
; rt_err_line — .pbas source line of the statement currently building a
; string; reported by rt_err_string_overflow.
; ----------------------------------------------------------------------------
rt_err_line:
    defs 2
    IF PB_CKCAL
; M13 responsiveness (rt_ck_gettime): the seconds and the ticks byte last
; read, the ticks byte when the seconds last changed, the fraction returned,
; and how close the reads were that gave that change
rt_ck_d:
    defs 1
rt_ck_e:
    defs 1
rt_ck_e0:
    defs 1
rt_ck_f:
    defs 1
; rt_ck_q: 255 - the 1/256 s between that pair of reads (0: none yet)
rt_ck_q:
    defs 1
    ENDIF

; ----------------------------------------------------------------------------
; M3a dialog state: rt_dialog_open is non-zero while the program's dialog is
; displayed (rt_exit removes it first); rt_gui_table holds the handler table
; address; rt_gui_object / rt_gui_evtype keep the current event's object
; number and event type across os_process_event, which corrupts registers.
; ----------------------------------------------------------------------------
rt_dialog_open:
    defs 1
    IF PB_DIALOG
rt_gui_table:
    defs 2
rt_gui_object:
    defs 1
rt_gui_evtype:
    defs 1
    IF PB_BINDINGS
rt_gui_handler:
    defs 2
; M3b binding state (see "Control bindings"); rt_obj_buf holds one rebuilt
; record: a TEXTBOX template (41) + text of at most 64 bytes incl. NUL, or
; a CHECKBOX template (9) + status.
rt_gui_bindings:
    defs 2
rt_bind_row:
    defs 2
rt_bind_left:
    defs 1
rt_bind_mode:
    defs 1
rt_bind_obj:
    defs 1
rt_bind_kind:
    defs 1
rt_bind_var:
    defs 2
rt_bind_cap:
    defs 1
rt_bind_tpl:
    defs 2
rt_bind_dst:
    defs 2
rt_bind_off:
    defs 1
rt_bind_val:
    defs 1
rt_obj_buf:
    defs 105
; M6 Phase 1 state (see "M6 Phase 1"), each part only where it is used.
    IF PB_NUMBERS
rt_sync_strict:
    defs 1
rt_num_val:
    defs 2
rt_num_shadow:
    defs 32
    ENDIF
    IF PB_SPIN + PB_SCROLL
rt_gui_b:
    defs 1
    ENDIF
    IF PB_SPIN
rt_spin_dir:
    defs 1
    ENDIF
    IF PB_RADIO
rt_rad_i:
    defs 1
rt_rad_v:
    defs 1
rt_rad_obj:
    defs 1
rt_rad_sel:
    defs 1
rt_rad_tpl:
    defs 2
    ENDIF
    IF PB_WINDOWS
rt_win_table:
    defs 2
rt_win_cur:
    defs 1
rt_win_next:
    defs 1
    ENDIF
    IF PB_FOCUS
rt_focus_obj:
    defs 1
    IF PB_WINDOWS
rt_focus_win:
    defs 1
    ENDIF
    ENDIF
    IF PB_MENUS
rt_menu_end:
    defs 2
rt_menu_t:
    defs 1
rt_menu_e:
    defs 1
rt_menu_n:
    defs 1
rt_menu_p:
    defs 2
    ENDIF
    IF PB_TIMER
rt_timer_run:
    defs 1
    ENDIF
    IF PB_TICKPOLL
rt_tick_due:
    defs 2
    ENDIF
    IF PB_SCROLL
rt_gui_de:
    defs 2
rt_sc_val:
    defs 2
rt_sc_min:
    defs 2
rt_sc_max:
    defs 2
rt_sc_page:
    defs 2
rt_sc_span:
    defs 2
    ENDIF
    IF PB_CTL2
rt_c2_word:
    defs 2
rt_c2_n:
    defs 2
rt_c2_arr:
    defs 2
rt_c2_sel:
    defs 2
rt_c2_tab:
    defs 2
rt_c2_size:
    defs 2
rt_c2_ptr:
    defs 2
rt_c2_left:
    defs 2
rt_c2_pad:
    defs 2
rt_c2_obj:
    defs 1
    ENDIF
    IF PB_LIST
rt_c2_vis:
    defs 2
rt_c2_first:
    defs 2
rt_c2_track:
    defs 2
rt_c2_hsize:
    defs 2
    ENDIF
    IF PB_CHANGE
rt_ctl_pending:
    defs 2
    ENDIF
    IF PB_SLIDER
; one value per SLIDER (pbas/policy.py SLIDER_MAX): Rosanne does not record
; scroll bars, so the slider's value lives here.
rt_sl_value:
    defs 32
    ENDIF
    ENDIF
    ENDIF

; ----------------------------------------------------------------------------
; M4 file state (see "Files"). rt_file_buf is the 640-byte transfer buffer:
; FILESAVE text is built in its first 128 bytes; FILELOAD reads byte i to
; +i (i <= 126) and os_read_file may fill up to 511 bytes beyond (ROSAN283
; os_read_file block-fill rule, read pessimistically; M4 repair).
; ----------------------------------------------------------------------------
    IF PB_FILES
rt_file_buf:
    defs 640
rt_file_desc:
    defs 2
rt_file_var:
    defs 2
rt_file_cap:
    defs 1
rt_file_len:
    defs 1
rt_file_op:
    defs 1
rt_file_reason:
    defs 1
rt_file_code:
    defs 1
    IF PB_FIO
rt_fio_err:
    defs 2
rt_fio_mode:
    defs 2
rt_fio_chan:
    defs 1
rt_fio_new:
    defs 1
rt_fio_state:
    defs 1
rt_fio_ahead:
    defs 1
rt_fio_byte:
    defs 1
rt_fio_rerr:
    defs 1
rt_fio_flags:
    defs 1
rt_fio_desc2:
    defs 2
rt_fio_line:
    defs 128
    ENDIF
    ENDIF

; ----------------------------------------------------------------------------
; M5a: extra scratch strings (pool after rt_cmp_buf1/2; pbas/statements.py
; SCRATCH_POOL), assembled only as far as a program's nesting needs them
; (PB_STR_TEMPS), and the MID$ count cell (PB_SLICE).
; ----------------------------------------------------------------------------
    IF PB_STR_TEMPS >= 1
rt_str_tmp3:
    defs 128
    ENDIF
    IF PB_STR_TEMPS >= 2
rt_str_tmp4:
    defs 128
    ENDIF
    IF PB_STR_TEMPS >= 3
rt_str_tmp5:
    defs 128
    ENDIF
    IF PB_STR_TEMPS >= 4
rt_str_tmp6:
    defs 128
    ENDIF
    IF PB_SLICE
rt_slc_count:
    defs 2
    ENDIF
; M5b state (see "Numbers and text").
    IF PB_DIV
rt_div_qsign:
    defs 1
rt_div_rsign:
    defs 1
    ENDIF
    IF PB_VAL
rt_val_neg:
    defs 1
    ENDIF
    IF PB_REAL
; M7 REAL state (see "M7 REAL arithmetic")
rt_fa:
    defs 8
rt_fb:
    defs 8
rt_fpk:
    defs 6
rt_fret:
    defs 2
rt_fsave:
    defs 2
rt_fe:
    defs 2
rt_fcnt:
    defs 1
rt_fprod:
    defs 8
rt_frem:
    defs 5
rt_fdv:
    defs 5
rt_fq:
    defs 5
rt_fqtop:
    defs 1
rt_ffrac:
    defs 1
rt_fx:
    defs 5
rt_fy:
    defs 5
rt_fz:
    defs 5
rt_fw:
    defs 5
rt_fp1:
    defs 5
rt_fp2:
    defs 5
rt_fk:
    defs 2
rt_frc:
    defs 2
rt_frx:
    defs 2
rt_fiter:
    defs 1
rt_fpn:
    defs 1
rt_fpp:
    defs 2
rt_fsign:
    defs 1
rt_fflag:
    defs 1
rt_fquad:
    defs 1
rt_fsn:
    defs 2
rt_fbig:
    defs 30
rt_fsde:
    defs 2
rt_fdexp:
    defs 2
rt_fn32:
    defs 4
rt_fn2:
    defs 4
rt_fdig:
    defs 9
rt_fnd:
    defs 1
rt_fdi:
    defs 1
rt_fdn:
    defs 1
rt_fnd9:
    defs 1
rt_fpsgn:
    defs 1
rt_fpbad:
    defs 1
    ENDIF
    IF PB_IMATH
rt_rnd_seed:
    defs 2
    ENDIF
    IF PB_INSTR
rt_ins_pos:
    defs 2
rt_ins_ndl:
    defs 2
    ENDIF
    IF PB_BANK
; M8 BANKED arrays: the block list, the read-window ring position and the
; locate / write-back cells (data area, after rt_alert_buf, like every other
; runtime cell).
rt_bank_n:
    defs 1
rt_bank_list:
    defs 33
rt_bk_ring:
    defs 1
rt_bk_win:
    defs 2
rt_bk_i:
    defs 2
rt_bk_size:
    defs 2
rt_bk_slot:
    defs 1
rt_bk_blk:
    defs 1
rt_bk_off:
    defs 2
rt_bk_wblk:
    defs 1
rt_bk_woff:
    defs 2
rt_bk_wsize:
    defs 2
rt_bk_me:
    defs 2
    ENDIF
    IF PB_BITMAP
; M12 BITMAPs: the record in use, bytes a row, rows a strip, the next row,
; the rows of this strip, bytes left, a file's width and height.
rt_bmp_rec:
    defs 2
rt_bmp_rowb:
    defs 2
rt_bmp_k_n:
    defs 2
rt_bmp_row:
    defs 2
rt_bmp_rows:
    defs 2
rt_bmp_left:
    defs 2
rt_bmp_wh:
    defs 4
    ENDIF
    IF PB_BMPPART
; M13 parts and masks: the mask's record, image / mask / part bytes a row,
; a fetch's bytes a row and out buffer, its source and destination
; pointers, the shift, the height limit, whether a mask is used.
rt_bmp_mrec:
    defs 2
rt_bmp_mrb:
    defs 2
rt_bmp_drb:
    defs 2
rt_bmp_frb:
    defs 2
rt_bmp_out:
    defs 2
rt_bmp_src:
    defs 2
rt_bmp_dst:
    defs 2
rt_bmp_lim:
    defs 2
rt_bmp_sh:
    defs 1
rt_bmp_masked:
    defs 1
    ENDIF
    IF PB_POINT
; M12 POINT's pixel, kept across os_mouse_on.
rt_bmp_px:
    defs 1
    ENDIF
    IF PB_PAGE
; M12 printing: a page is open; the typo system is set up; the font's ID;
; the list's length, entries left, a Times font found; scratch (an ID, a
; rectangle in 1/1800"); size, style; ascender, descender; the line's top,
; baseline, x, next x; a character; a box's height; the statement's words.
rt_pg_open:
    defs 1
rt_pg_typo:
    defs 1
rt_pg_id:
    defs 2
rt_pg_n:
    defs 1
rt_pg_k:
    defs 1
rt_pg_found:
    defs 1
rt_pg_t:
    defs 8
rt_pg_size:
    defs 1
rt_pg_style:
    defs 1
rt_pg_asc:
    defs 2
rt_pg_desc:
    defs 2
rt_pg_top:
    defs 2
rt_pg_base:
    defs 2
rt_pg_x:
    defs 2
rt_pg_nx:
    defs 2
rt_pg_ch:
    defs 1
rt_pg_bh:
    defs 2
rt_pg_args:
    defs 10
    ENDIF
    IF PB_TYPO
; M15 W3 screen typography: set up; the chosen font (ID, size 0 = none yet,
; style); the font slot 0 holds (1 ours, 2 PAGE's, 0 unknown) and its ID and
; size; its ascender and line height in pixels; the families' fonts; the
; list's scan; a line being drawn or measured.
rt_ty_init:
    defs 1
rt_ty_id:
    defs 2
rt_ty_size:
    defs 1
rt_ty_style:
    defs 1
rt_ty_slot:
    defs 1
rt_ty_did:
    defs 2
rt_ty_dsize:
    defs 1
rt_ty_ascpx:
    defs 2
rt_ty_hgt:
    defs 2
rt_ty_times:
    defs 2
rt_ty_swiss:
    defs 2
rt_ty_k:
    defs 1
rt_ty_seen:
    defs 1
rt_ty_t:
    defs 2
rt_ty_p:
    defs 2
rt_ty_ch:
    defs 1
rt_ty_px:
    defs 2
rt_ty_rem:
    defs 1
rt_ty_npx:
    defs 2
rt_ty_nrem:
    defs 1
rt_ty_x0:
    defs 2
rt_ty_sy:
    defs 2
rt_ty_room:
    defs 2
rt_ty_mode_b:
    defs 1
    ENDIF
    IF PB_CODEBANKS
; M9 code banks (data area, after rt_alert_buf, like every other runtime cell).
; rt_code_n: blocks held (0 = none to release); rt_code_q2: the block at
; #8000 when the program started; rt_code_list: block numbers, 0-terminated
; (MAX_CODE_BANKS 16 in pbas/codebanks.py).
rt_code_n:
    defs 1
rt_code_q2:
    defs 1
rt_code_open:
    defs 1
rt_code_k:
    defs 1
rt_code_blk:
    defs 1
rt_code_me:
    defs 2
rt_code_ptr:
    defs 2
rt_code_tp:
    defs 2
rt_code_left:
    defs 2
rt_code_off:
    defs 2
rt_code_list:
    defs 17
    IF DEFINED PB_RTBANK
; M11 runtime bank: rt_rbc's cells (values only between its steps).
rt_rb_hl:
    defs 2
rt_rb_de:
    defs 2
rt_rb_go:
    defs 2
rt_rb_a:
    defs 1
    ENDIF
    ENDIF
    IF PB_CANVAS
; M9 CANVAS (data area, after rt_alert_buf). Bytes: on screen, a press in
; progress, repaint wanted, PAINT running, rt_cv_abs sign, BIOS operation,
; the ink and mode found. Words: the last event code, its canvas-relative
; position, the MOUSE/KEYS values the program reads, scroll workspace.
rt_cv_on:
    defs 1
rt_cv_down:
    defs 1
rt_cv_dirty:
    defs 1
rt_cv_painting:
    defs 1
    IF PB_CVMULTI
; M15 several canvases: the current canvas (a copy of its cgcv_tab entry)
; and its window's text fields; 1 + the current canvas's number (0: none
; yet); the DRAW ON target; 1 + the keyboard's canvas (0: the first on
; screen); the canvas pressed; PAINTs due (bit k); a press's search; each
; canvas's fonts. (The current canvas's copy, cgcanvas, is the program's: defs 16.)
rt_cv_edp:
    defs 2
rt_cvm_cur:
    defs 1
rt_cvm_sel:
    defs 1
rt_cvm_focus:
    defs 1
rt_cvm_downk:
    defs 1
rt_cvm_pend:
    defs 1
rt_cvm_m:
    defs 1
rt_cvm_k:
    defs 1
rt_cvm_px:
    defs 2
rt_cvm_py:
    defs 2
    IF PB_DWFONT+PB_TYPO
; 8 canvases of RT_CVM_S (at most 5) bytes
rt_cvm_state:
    defs 40
    ELSE
rt_cvm_state equ rt_cvm_py
    ENDIF
    ENDIF
rt_cv_wasneg:
    defs 1
rt_cv_bios_op:
    defs 1
    IF PB_CVLINE
rt_ln_xmaj:
    defs 1
rt_ln_x:
    defs 2
rt_ln_y:
    defs 2
rt_ln_dx:
    defs 2
rt_ln_dy:
    defs 2
rt_ln_sx:
    defs 2
rt_ln_sy:
    defs 2
rt_ln_maj:
    defs 2
rt_ln_end:
    defs 2
rt_ln_mstep:
    defs 2
rt_ln_min:
    defs 2
rt_ln_nstep:
    defs 2
rt_ln_dmaj2:
    defs 2
rt_ln_dmin2:
    defs 2
rt_ln_err:
    defs 2
rt_ln_run:
    defs 2
    ENDIF
rt_cv_oldink:
    defs 1
rt_cv_oldmode:
    defs 1
rt_cv_code:
    defs 2
rt_cv_tx:
    defs 2
rt_cv_ty:
    defs 2
rt_cv_mx:
    defs 2
rt_cv_my:
    defs 2
rt_cv_mev:
    defs 2
rt_cv_key:
    defs 2
rt_cv_shift:
    defs 2
rt_cv_sx:
    defs 2
rt_cv_sy:
    defs 2
rt_cv_dx:
    defs 2
rt_cv_dy:
    defs 2
rt_cv_cw:
    defs 2
rt_cv_ch:
    defs 2
rt_cv_fx:
    defs 2
rt_cv_fy:
    defs 2
rt_cv_fw:
    defs 2
rt_cv_fh:
    defs 2
rt_dw_args:
    defs 12
rt_dw_ink:
    defs 1
rt_dg_buf:
    defs 16
rt_ds_buf:
    defs 136
    IF PB_DWFONT
rt_dw_font:
    db 7                        ; M15: DRAW FONT's font (dialog font 7 by default)
rt_dw_len:
    defs 1
rt_dw_lo:
    defs 1
rt_dw_hi:
    defs 1
rt_dw_mid:
    defs 1
rt_dw_save:
    defs 1
rt_dw_room:
    defs 2
    IF PB_DWALIGN
rt_dw_align:
    db 0                        ; M15: ALIGN of the next DRAW TEXT (1 centre, 2 right)
    ENDIF
    ENDIF
    IF PB_TEXTW
; TEXTWIDTH's block (M11 corrective). Defined here, after rt_ds_buf: an equ
; to a label defined later takes that label's first-pass value (0) in Pasmo
; for code assembled before it, although the symbol table shows the final
; one (found by tests/memguard.py: a write to #0008).
rt_tw_buf equ rt_ds_buf
    ENDIF
    IF PB_CVCELL
; M11 DRAW TEXT ..., cell: the next character, and the cells left.
rt_cv_cell_p:
    defs 2
rt_cv_cell_n:
    defs 1
    ENDIF
    ENDIF
    IF PB_TEXT
; M9 TEXT buffers (data area): the working copy of a buffer record and the
; routines' cells; TX_* name the record's fields in the copy.
rt_tx_rec:
    defs 2
rt_tx_s:
    defs 18
TX_CAP equ rt_tx_s
TX_SLOT equ rt_tx_s+2
TX_GS equ rt_tx_s+4
TX_GE equ rt_tx_s+6
TX_LINES equ rt_tx_s+8
TX_CHG equ rt_tx_s+10
TX_STYLE equ rt_tx_s+11
TX_CL equ rt_tx_s+12
TX_CP equ rt_tx_s+14
TX_FC equ rt_tx_s+16
rt_tx_cur:
    defs 1
rt_tx_q2:
    defs 1
rt_tx_tl:
    defs 1
rt_tx_c_max:
    defs 1
rt_tx_first:
    defs 1
rt_tx_prev:
    defs 1
rt_tx_byte:
    defs 1
rt_tx_to:
    defs 2
rt_tx_n:
    defs 2
rt_tx_c:
    defs 2
rt_tx_k:
    defs 2
rt_tx_mv:
    defs 2
rt_tx_lp:
    defs 2
rt_tx_ll:
    defs 2
rt_tx_end:
    defs 2
rt_tx_at:
    defs 2
rt_tx_fl:
    defs 2
rt_tx_fs:
    defs 2
rt_tx_str:
    defs 2
rt_tx_tmp:
    defs 128
    ENDIF
    IF PB_TXRANGE
rt_tx_n1:
    defs 2
rt_tx_n2:
    defs 2
rt_tx_c2:
    defs 2
rt_tx_p1:
    defs 2
rt_tx_p2:
    defs 2
rt_tx_lp1:
    defs 2
rt_tx_cnt:
    defs 2
rt_tx_lf:
    defs 2
rt_tx_q:
    defs 2
rt_tx_chunk:
    defs 2
rt_tx_src:
    defs 2
rt_tx_dst:
    defs 2
rt_tx_all:
    defs 1
rt_tx_sty:
    defs 1
    ENDIF
    IF PB_FNAME
rt_fn_out:
    defs 2
rt_fn_ext:
    defs 2
rt_dyn_desc:
    defs 14
rt_dyn_desc2:
    defs 14
    ENDIF
    IF PB_DB
rt_db_desc:
    defs 2
rt_db_sig:
    defs 2
rt_db_idp:
    defs 2
    IF PB_FSAFE
rt_db_strs:
    defs 2
    ENDIF
rt_db_len:
    defs 2
rt_db_size:
    defs 2
rt_db_n:
    defs 2
rt_db_k:
    defs 2
rt_db_i:
    defs 2
rt_db_cnt:
    defs 2
rt_db_s1:
    defs 2
rt_db_s2:
    defs 2
rt_db_p:
    defs 2
rt_db_left:
    defs 2
rt_db_recov:
    defs 2
rt_db_try:
    defs 1
rt_db_vfy:
    defs 1
rt_db_err:
    defs 1
rt_db_t:
    defs 4
rt_db_hdr:
    defs 16
rt_db_ext0:
    defs 6
rt_db_key:
    defs 128
rt_db_kx:
    defs 128
rt_db_ord:
    defs 2
rt_db_ob:
    defs 2
rt_db_foff:
    defs 2
rt_db_flen:
    defs 2
rt_db_fk:
    defs 1
rt_db_x:
    defs 2
rt_db_lo:
    defs 2
rt_db_hi:
    defs 2
rt_db_mid:
    defs 2
rt_db_rc:
    defs 1
    ENDIF
