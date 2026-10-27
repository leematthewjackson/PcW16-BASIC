; ============================================================================
; UIPROBE — XAnne probe for the M6 Phase 1 Rosanne contracts
; ============================================================================
; NOT compiler output and NOT part of the runtime: a hand-written test tool,
; like READDIAG and WIDTHDG. It makes exactly the OS calls, with exactly the
; data placement, that the M6 Phase 1 runtime makes, and shows the raw
; results, so that each documented-but-unverified contract is checked once
; before it is relied on (docs/M5E-UI-AUDIT.md §6, §7).
;
; Safety: no files; no memory requested from the OS. The menu definition is
; built in the app workspace #2400-#2BFF of block #80 (ROSAN283 "AP may use
; #2000...#2FFF"). The timer is killed before exit.
;
; What it checks (owner steps in RUNTIME-RESULTS "M6 Phase 1 scripts"):
;   P1  menu bar while a dialog is open (global ddm_enable = 1): the Tasks
;       menu from os_ddm_get_tasks (fn 14) followed by a "Probe" menu, fns
;       12 (define) and 13 (display); selection events (event bit 1) show
;       title, entry and the new status (+2, +3, +4); a divider, a tickable
;       entry, a greyed entry, and a Ctrl+H hotkey on "Hello"
;   P2  a radio group of three (ob_radio, group 0): does Rosanne clear the
;       others when one is clicked, and repaint them? "Read" shows the
;       three stored statuses, then repaints the three radios
;   P3  a numeric field whose legal characters are an explicit list in the
;       app image ("-0123456789", Wd24 with the app bank), plus a spinner
;       (ob_spinner): each spinner click shows the event type and the B
;       value os_process_event returns (doc: 1 up, 5 down)
;   P4  an os_alert with three buttons: the returned A (doc: 0..2)
;   P5  os_beep (fn 50), on the "Beep" button and its F1 key
;   P6  button keys: Return on "Read", Green on "Ask", F1 on "Beep", Stop on
;       "Quit" (keycode pairs, shift #80 = ignore)
;   P7  a repeating timer (fns 8/9, timer 0, 2 s) while the dialog is open:
;       each tick redraws "Ticks: nnn"
;   P8  a second, larger dialog (600x400 at 20,50) after os_dialog_remove,
;       and back again (fns 68, 66, 67)
;
; OS calls (ROSAN283; numbers from OSCALLS.INC.txt counted from 1, as in
; runtime/runtime.z80.asm): os_wait_event 2, os_process_event 4,
; os_set_timer 8, os_kill_timer 9, os_ddm_define 12, os_ddm_display 13,
; os_ddm_get_tasks 14, os_app_exit 23, os_beep 50, os_dialog_define 66,
; os_dialog_display 67, os_dialog_remove 68, os_object_define 69,
; os_object_get_define 70, os_object_update 72, os_set_focus 73,
; os_alert 76, os_get_byte_24bit 42, os_add_24bit 48; bios_getmem1 =
; call #0CB.
;
; Build:  pasmo --bin xanne/uiprobe.asm artifacts/m6-phase1/uiprobe.prg
; ============================================================================

    org 4000h
    defs 100h

MENU_BUF equ 2400h               ; workspace, block #80 (C = #80)

start:
    call 0CBh
    ld (pb_bank),a
    ld (dlg_a_legal+2),a         ; Wd24 bank byte of the legal-character list
    ld (pb_alert_bank),a
    ; --- P1: Tasks menu, then the probe's own menu ------------------------
    ld c,80h
    ld hl,MENU_BUF
    ld a,14
    call 003Bh
    ld (pb_menu_end),hl
    ex de,hl                     ; DE = where our titles go
    ld hl,menu_ours
    ld bc,menu_ours_end-menu_ours
    ldir
    ; alert: "Tasks menu: nnnnn bytes at 2400"
    ld de,pb_text
    ld hl,t_tasks
    call pb_puts
    ld hl,(pb_menu_end)
    ld bc,MENU_BUF
    or a
    sbc hl,bc
    call pb_dec
    ld hl,t_bytes
    call pb_puts
    call pb_alert_ok
    ld c,80h
    ld hl,MENU_BUF
    ld b,0
    ld a,12
    call 003Bh
    ld a,13
    call 003Bh
    call open_a
    jp loop

; ---------------------------------------------------------------- windows
open_a:
    ld a,(pb_bank)
    ld c,a
    ld hl,dlg_a
    ld a,66
    call 003Bh
    jp c,fail_define
    ld a,67
    call 003Bh
    jp c,fail_define
    ld a,1
    ld (pb_win),a
    ld (pb_open),a
    ld e,13
    ld a,73
    call 003Bh
    ret

open_b:
    ld a,(pb_bank)
    ld c,a
    ld hl,dlg_b
    ld a,66
    call 003Bh
    jp c,fail_define
    ld a,67
    call 003Bh
    jp c,fail_define
    ld a,2
    ld (pb_win),a
    ld a,1
    ld (pb_open),a
    ld e,4
    ld a,73
    call 003Bh
    ret

close_win:
    xor a
    ld (pb_open),a
    ld a,68
    call 003Bh
    ret

fail_define:
    push af
    pop hl
    ld (pb_af),hl
    ld de,pb_text
    ld hl,t_deffail
    call pb_puts
    ld a,(pb_win)
    add a,'0'
    ld (de),a
    inc de
    ld hl,t_flags
    call pb_puts
    ld a,(pb_af)
    call pb_hex
    ld hl,t_a
    call pb_puts
    ld a,(pb_af+1)
    call pb_hex
    call pb_alert_ok
    jp quit

; ---------------------------------------------------------------- events
loop:
    ld hl,0FFFFh
    ld a,2
    call 003Bh
    jp z,loop
    ld a,l
    and 2
    jp nz,on_menu
    ld a,l
    and 1
    jp nz,on_timer
    bit 5,h
    jp z,loop
    ld a,(ix+2)
    cp 5
    jp z,quit
    cp 4
    jp nz,pass
    ld a,(ix+3)
    ld (pb_obj),a
    ld a,(ix+5)
    ld (pb_ev),a
    ld a,4
    call 003Bh
    ld a,b
    ld (pb_b),a
    ld a,(pb_win)
    cp 2
    jp z,events_b
    ; window A
    ld a,(pb_obj)
    cp 10
    jp z,on_spin
    ld a,(pb_ev)
    cp 1
    jp z,events_a
    cp 3
    jp nz,loop
events_a:
    ld a,(pb_obj)
    cp 13
    jp z,do_read
    cp 14
    jp z,do_ask
    cp 15
    jp z,do_beep
    cp 16
    jp z,do_timer
    cp 17
    jp z,do_window
    cp 18
    jp z,quit
    jp loop
events_b:
    ld a,(pb_ev)
    cp 1
    jp z,events_b2
    cp 3
    jp nz,loop
events_b2:
    ld a,(pb_obj)
    cp 4
    jp nz,loop
    call close_win
    call open_a
    jp loop

pass:
    ld a,4
    call 003Bh
    jp loop

; P1 — a menu selection: "Menu T=tt E=ee S=ss"
on_menu:
    ld a,(ix+2)
    ld (pb_t),a
    ld a,(ix+3)
    ld (pb_e),a
    ld a,(ix+4)
    ld (pb_s),a
    ld de,pb_text
    ld hl,t_menu
    call pb_puts
    ld a,(pb_t)
    call pb_hex
    ld hl,t_e
    call pb_puts
    ld a,(pb_e)
    call pb_hex
    ld hl,t_s
    call pb_puts
    ld a,(pb_s)
    call pb_hex
    call pb_alert_ok
    jp loop

; P7 — a timer tick: count and redraw "Ticks: nnnnn" in window A
on_timer:
    ld hl,(pb_ticks)
    inc hl
    ld (pb_ticks),hl
    ld a,(pb_win)
    cp 1
    jp nz,loop
    ld de,tick_text
    ld hl,(pb_ticks)
    call pb_dec
    ld a,(pb_bank)
    ld c,a
    ld hl,obj_tick
    ld e,12
    ld a,69
    call 003Bh
    ld e,11
    ld a,72
    call 003Bh
    ld e,12
    ld a,72
    call 003Bh
    jp loop

; P3 — a spinner event: "Spin ev=tt B=bb"
on_spin:
    ld de,pb_text
    ld hl,t_spin
    call pb_puts
    ld a,(pb_ev)
    call pb_hex
    ld hl,t_b
    call pb_puts
    ld a,(pb_b)
    call pb_hex
    call pb_alert_ok
    jp loop

; P2/P3 — "Read": "Radios aa bb cc Field [text]"
do_read:
    ld de,pb_text
    ld hl,t_radios
    call pb_puts
    ld a,3
    call read_byte9
    ld a,5
    call read_byte9
    ld a,7
    call read_byte9
    ld hl,t_field
    call pb_puts
    ; text of object 9 at +41
    ld (pb_dst),de
    ld e,9
    ld a,70
    call 003Bh
    jp c,read_fail
    ld de,41
    ld b,0
    ld a,48
    call 003Bh
    jp c,read_fail
    ld a,12
    ld (pb_n),a
read_text:
    ld b,1
    ld a,42
    call 003Bh
    ld a,e
    or a
    jp z,read_done
    ld de,(pb_dst)
    ld (de),a
    inc de
    ld (pb_dst),de
    ld a,(pb_n)
    dec a
    ld (pb_n),a
    jp nz,read_text
read_done:
    ld de,(pb_dst)
    ld a,']'
    ld (de),a
    inc de
    ld (pb_dst),de
    ; repaint the three radios so the screen shows what is stored
    ld e,3
    ld a,72
    call 003Bh
    ld e,5
    ld a,72
    call 003Bh
    ld e,7
    ld a,72
    call 003Bh
    ld de,(pb_dst)
    call pb_alert_ok
    jp loop
read_fail:
    ld de,(pb_dst)
    ld hl,t_fail
    call pb_puts
    call pb_alert_ok
    jp loop

; read_byte9 — append " hh" = byte +9 of object A (radio status)
read_byte9:
    ld (pb_dst),de
    ld e,a
    ld a,70
    call 003Bh
    jp c,rb9_fail
    ld de,9
    ld b,0
    ld a,48
    call 003Bh
    jp c,rb9_fail
    ld b,0
    ld a,42
    call 003Bh
    ld a,e
    ld de,(pb_dst)
    push af
    ld a,' '
    ld (de),a
    inc de
    pop af
    call pb_hex
    ret
rb9_fail:
    ld de,(pb_dst)
    ld hl,t_xx
    call pb_puts
    ret

; P4 — a three-button alert, then "Ask A=aa Cy=c"
do_ask:
    ld a,(pb_bank)
    ld c,a
    ld hl,ask_def
    ld de,ask_def_end-ask_def
    ld a,76
    call 003Bh
    push af
    pop hl
    ld (pb_af),hl
    ld de,pb_text
    ld hl,t_ask
    call pb_puts
    ld a,(pb_af+1)
    call pb_hex
    ld hl,t_cy
    call pb_puts
    ld a,(pb_af)
    and 1
    add a,'0'
    ld (de),a
    inc de
    call pb_alert_ok
    jp loop

; P5 — os_beep
do_beep:
    ld a,50
    call 003Bh
    jp loop

; P7 — start / stop the repeating timer; carry from either call is shown
do_timer:
    ld a,(pb_timer)
    or a
    jp nz,timer_stop
    ld a,(pb_bank)
    ld c,a
    ld hl,timer_rec
    ld a,8
    call 003Bh
    jp c,timer_fail
    ld a,1
    ld (pb_timer),a
    jp loop
timer_stop:
    ld e,0
    ld a,9
    call 003Bh
    jp c,timer_fail
    xor a
    ld (pb_timer),a
    jp loop
timer_fail:
    ld de,pb_text
    ld hl,t_tfail
    call pb_puts
    call pb_alert_ok
    jp loop

; P8 — the large window
do_window:
    call close_win
    call open_b
    jp loop

quit:
    ld a,(pb_timer)
    or a
    jp z,quit2
    ld e,0
    ld a,9
    call 003Bh
quit2:
    ld a,(pb_open)
    or a
    jp z,quit3
    call close_win
quit3:
    ld a,23
    call 003Bh
    ret

; ---------------------------------------------------------------- helpers
; pb_alert_ok — finish the text at pb_text..DE as a one-button alert.
pb_alert_ok:
    xor a
    ld (de),a
    inc de
    ld (de),a
    inc de
    ld a,1
    ld (de),a
    inc de
    ld hl,ok_tail
    ld bc,11
    ldir
    ld hl,pb_text
    ex de,hl
    or a
    sbc hl,de
    ex de,hl
    ld hl,pb_text
    ld a,(pb_bank)
    ld c,a
    ld a,76
    call 003Bh
    ret

; pb_puts — copy NUL-terminated HL to DE (no NUL); DE advanced.
pb_puts:
    ld a,(hl)
    or a
    ret z
    ld (de),a
    inc hl
    inc de
    jp pb_puts

; pb_hex — A as two hex digits at DE; DE advanced; HL kept.
pb_hex:
    push af
    srl a
    srl a
    srl a
    srl a
    call pb_nib
    pop af
    and 15
pb_nib:
    add a,'0'
    cp '9'+1
    jp c,pb_nib_out
    add a,7
pb_nib_out:
    ld (de),a
    inc de
    ret

; pb_dec — HL as 5 decimal digits at DE; DE advanced.
pb_dec:
    ld bc,10000
    call pb_digit
    ld bc,1000
    call pb_digit
    ld bc,100
    call pb_digit
    ld bc,10
    call pb_digit
    ld bc,1
pb_digit:
    ld a,'0'
pb_digit_loop:
    or a
    sbc hl,bc
    jp c,pb_digit_done
    inc a
    jp pb_digit_loop
pb_digit_done:
    add hl,bc
    ld (de),a
    inc de
    ret

; ---------------------------------------------------------------- data
t_tasks:   db "Tasks menu: ",0
t_bytes:   db " bytes at 2400",0
t_deffail: db "Window ",0
t_flags:   db " could not be opened, F=",0
t_menu:    db "Menu T=",0
t_e:       db " E=",0
t_s:       db " S=",0
t_spin:    db "Spin ev=",0
t_b:       db " B=",0
t_radios:  db "Radios",0
t_field:   db " Field [",0
t_fail:    db "?]",0
t_xx:      db " ??",0
t_ask:     db "Ask A=",0
t_cy:      db " Cy=",0
t_a:       db " A=",0
t_tfail:   db "Timer call failed",0
ok_tail:   dw 800Dh,80FBh,0,0
           db "OK",0

; the probe's own menu, appended after the Tasks menu (ROSAN283 DDM format)
menu_ours:
    db 80h
    dw 0
    db "Probe|"
    db 80h, 'h', 4               ; hotkey: ASCII 'h', shift state Ctrl
    db "Hello|"
    db 80h, '_', '|'             ; divider
    db 82h                       ; tickable
    dw 0
    db "Tick me|"
    db 88h                       ; greyed
    dw 0
    db "Grey item", 0            ; last entry 0-terminated
    db 0                         ; end of the whole definition
menu_ours_end:

; three-button alert
ask_def:
    db "Probe question: pick one",0,0
    db 3
    db 0Dh,80h,0FBh,80h,0,0,0,0
    db "Yes please",0
    db 0,0,0,0,0,0,0,0
    db "No thanks",0
    db 0FEh,80h,0FCh,80h,0,0,0,0
    db "Cancel",0
ask_def_end:

; timer record (ROSAN283 os_set_timer: bytes 2..5 used): timer 0, repeat,
; 32/16 s = 2 s
timer_rec:
    dw 1
    db 0, 1
    dw 32
    dw 0, 0, 0

; window A: 360x240 at 140,110 (the proven geometry), menus enabled
dlg_a:
    db 1, 0, 1, 1                ; focus, exit-by-click, screen-store, ddm_enable
    db 16
    dw 140, 110, 360, 240
    db "UI probe", 0
    ; 1 background box
    db 1
    dw 2, 26, 356, 212
    db 0, 8, 0, 0, 0
    ; 2-7 radio group 0: caption label linked to its radio, then the radio
    db 2
    dw 52, 45, 200, 1
    db 3, 7, 0
    db "Option 1", 0
    db 7
    dw 26, 43, 19, 19
    db 0FFh, 0
    db 2
    dw 52, 69, 200, 1
    db 5, 7, 0
    db "Option 2", 0
    db 7
    dw 26, 67, 19, 19
    db 0, 0
    db 2
    dw 52, 93, 200, 1
    db 7, 7, 0
    db "Option 3", 0
    db 7
    dw 26, 91, 19, 19
    db 0, 0
    ; 8 field box linked to 9, 9 numeric text edit, 10 spinner
    db 1
    dw 26, 118, 120, 25
    db 9, 8, 0, 1, 0
    db 8
    dw 30, 124, 112, 18
    db 0, 1                      ; +0 mode, +1 highlight
    dw 0                         ; +2 input length
    db 0, 0, 0                   ; +4 input address
    db 0                         ; +7 lines
    dw 0, 0, 0, 0                ; +8 x,y,w,h (set by OS)
    dw 7                         ; +16 font
    dw 0                         ; +18
    db 0                         ; +20
dlg_a_legal:
    dw legal_num                 ; +21 Wd24 legal characters (bank patched)
    db 0
    db legal_num_end-legal_num   ; +24 length
    db 0, 0, 0                   ; +25 output address (set by OS)
    dw 6                         ; +28 maximum length
    db 0, 0                      ; +30, +31
    db "42    ", 0               ; the slot reserves all 6 characters
    db 13
    dw 150, 114, 17, 33
    db 0
    ; 11 white box, 12 tick label (redefined by the timer)
    db 1
    dw 186, 120, 150, 20
    db 0, 8, 0, 0, 0
obj_tick_init:
    db 2
    dw 190, 124, 140, 1
    db 0, 7, 0
    db "Ticks: 00000", 0
    ; 13-18 buttons, two rows of three (96x24, pitch 110)
    db 3
    dw 22, 180, 96, 24
    db 0Dh, 80h, 0, 0, 0, 0, 0, 0
    db 0
    db "Read", 0
    db 3
    dw 132, 180, 96, 24
    db 0FBh, 80h, 0, 0, 0, 0, 0, 0
    db 0
    db "Ask", 0
    db 3
    dw 242, 180, 96, 24
    db 0F1h, 80h, 0, 0, 0, 0, 0, 0
    db 0
    db "Beep", 0
    db 3
    dw 22, 208, 96, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "Timer", 0
    db 3
    dw 132, 208, 96, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "Window", 0
    db 3
    dw 242, 208, 96, 24
    db 0FEh, 80h, 0, 0, 0, 0, 0, 0
    db 0
    db "Quit", 0
    db 0

; window B: 600x400 at 20,50, menus enabled
dlg_b:
    db 1, 0, 1, 1
    db 16
    dw 20, 50, 600, 400
    db "Large window", 0
    db 1
    dw 2, 26, 596, 372
    db 0, 8, 0, 0, 0
    db 2
    dw 24, 48, 305, 1
    db 0, 7, 0
    db "This window is 600 x 400.", 0
    db 2
    dw 24, 80, 305, 1
    db 0, 7, 0
    db "Try the Probe menu here too.", 0
    db 3
    dw 252, 340, 96, 24
    db 0Dh, 80h, 0, 0, 0, 0, 0, 0
    db 0
    db "Back", 0
    db 0

legal_num:
    db "-0123456789"
legal_num_end:

; the tick label's record for os_object_define (same length as the original)
obj_tick:
    db 2
    dw 190, 124, 140, 1
    db 0, 7, 0
    db "Ticks: "
tick_text:
    db "00000", 0

pb_bank:   defs 1
pb_alert_bank: defs 1
pb_win:    defs 1
pb_open:   defs 1
pb_timer:  defs 1
pb_obj:    defs 1
pb_ev:     defs 1
pb_b:      defs 1
pb_t:      defs 1
pb_e:      defs 1
pb_s:      defs 1
pb_n:      defs 1
pb_af:     defs 2
pb_dst:    defs 2
pb_ticks:  defs 2
pb_menu_end: defs 2
pb_text:   defs 120
