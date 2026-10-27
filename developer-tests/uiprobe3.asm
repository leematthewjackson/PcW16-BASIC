; ============================================================================
; UIPROBE3 — focused XAnne retest after UIPROBE2 U6 (blank list after Set)
; ============================================================================
; NOT compiler output and NOT part of the runtime: a hand-written test tool,
; derived from UIPROBE2 (same window, same records, same status line). Each
; button applies ONE way of redrawing a redefined list, so the owner can see
; which one Rosanne needs. Press Reset (a fresh os_dialog_remove /
; os_dialog_define / os_dialog_display) before each variant.
;
; Safety: no files; no memory requested from the OS.
;
;   A  Update   — U6 again: define the list (first 2, selection 2, the
;                 "previous" words +16/+20 equal to the new values), repaint
;                 the frame box (fn 72), update the list (fn 72). Expected
;                 from U6: blank.
;   B  Display  — the same record and box repaint, then os_object_display
;                 (fn 71, ROSAN283 "display one object") instead of update.
;   C  Prev     — previous words = #FFFF, box repaint, os_object_update.
;   D  Focus    — after clicking an item: os_set_focus(list) only. Does the
;                 highlight (missing in U2) appear?
;   E  Hilite   — define the list with selection 1 (first 0), then
;                 os_object_display, no box: is the selection highlighted?
;   F  Drop none — define the drop button with current #FFFF ("none") and
;                 os_object_update: what does the readout show? (last: the
;                 value is outside the list; Rosanne may draw garbage)
;
; Compiled programs (repair in runtime "LIST") use B and C together.
; OS calls as UIPROBE2, plus os_object_display 71 and os_set_focus 73.
;
; Build:  pasmo --bin xanne/uiprobe3.asm artifacts/m6-phase2-fix/uiprobe3.prg
; ============================================================================

    org 4000h
    defs 100h

start:
    call 0CBh
    ld (pb_bank),a
    ld (rec_list+27),a           ; Wd24 bank bytes of the string tables
    ld (rec_list_ff+27),a
    ld (rec_list_hl+27),a
    ld (rec_drop_none+26),a
    ld (dlg_list+27),a
    ld (dlg_drop+26),a
    ld hl,item_table+2           ; and the bank byte of every item pointer
    ld b,6
patch:
    ld (hl),a
    inc hl
    inc hl
    inc hl
    dec b
    jp nz,patch
    call open_dlg
    jp loop

open_dlg:
    ld a,(pb_bank)
    ld c,a
    ld hl,dlg
    ld a,66
    call 003Bh
    jp c,fail
    ld a,67
    call 003Bh
    jp c,fail
    ld a,1
    ld (pb_open),a
    ret

loop:
    ld hl,0FFFFh
    ld a,2
    call 003Bh
    jp z,loop
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
    ld (pb_de),de
    ld a,(pb_obj)
    cp 3
    jp z,show
    cp 4
    jp z,show
    cp 7
    jp z,show
    cp 8
    jp z,show
    ld a,(pb_ev)
    cp 1
    jp nz,loop
    ld a,(pb_obj)
    cp 11
    jp z,v_a
    cp 12
    jp z,v_b
    cp 13
    jp z,v_c
    cp 14
    jp z,v_d
    cp 15
    jp z,v_e
    cp 16
    jp z,v_f
    cp 17
    jp z,v_reset
    cp 18
    jp z,quit
    jp loop

pass:
    ld a,4
    call 003Bh
    jp loop

; the status line: O=oo E=ee B=bb DE=dddd F=ffff S=ssss C=cccc
show:
    ld de,status_text
    ld hl,t_o
    call pb_puts
    ld a,(pb_obj)
    call pb_hex
    ld hl,t_e
    call pb_puts
    ld a,(pb_ev)
    call pb_hex
    ld hl,t_b
    call pb_puts
    ld a,(pb_b)
    call pb_hex
    ld hl,t_de
    call pb_puts
    ld a,(pb_de+1)
    call pb_hex
    ld a,(pb_de)
    call pb_hex
    call live_fsc
    xor a
    ld (de),a
    ld a,(pb_bank)
    ld c,a
    ld hl,rec_status
    ld e,10
    ld a,69
    call 003Bh
    ld e,9
    ld a,72
    call 003Bh
    ld e,10
    ld a,72
    call 003Bh
    jp loop

; live_fsc — append " F=ffff S=ssss C=cccc" at DE from the live records.
live_fsc:
    ld hl,t_f
    call pb_puts
    ld a,3
    ld b,14
    call live_word
    ld hl,t_s
    call pb_puts
    ld a,3
    ld b,18
    call live_word
    ld hl,t_c
    call pb_puts
    ld a,7
    ld b,22
    jp live_word

; live_word — the word at offset B of object A's live definition, as four
; hex digits at DE (DE advanced); "????" if the OS reports an error.
live_word:
    ld (pb_dst),de
    ld (pb_off),a
    ld a,b
    ld (pb_off+1),a
    ld a,(pb_off)
    ld e,a
    ld a,70
    call 003Bh
    jp c,live_fail
    ld a,(pb_off+1)
    ld e,a
    ld d,0
    ld b,0
    ld a,48
    call 003Bh
    jp c,live_fail
    ld b,1
    ld a,42
    call 003Bh
    ld a,e
    ld (pb_w),a                  ; low byte
    ld b,0
    ld a,42
    call 003Bh
    ld a,e
    ld (pb_w+1),a                ; high byte
    ld de,(pb_dst)
    ld a,(pb_w+1)
    call pb_hex
    ld a,(pb_w)
    jp pb_hex
live_fail:
    ld de,(pb_dst)
    ld hl,t_xx
    jp pb_puts

; def_obj — os_object_define of object E from HL (app bank); C = error.
def_obj:
    ld a,(pb_bank)
    ld c,a
    ld a,69
    call 003Bh
    ret
; obj_call — fn A for object E (72 update, 71 display, 73 focus).
obj_call:
    call 003Bh
    jp loop

v_a:
    ld hl,rec_list
    ld e,3
    call def_obj
    jp c,set_fail
    ld e,2
    ld a,72
    call 003Bh
    ld e,3
    ld a,72
    jp obj_call
v_b:
    ld hl,rec_list
    ld e,3
    call def_obj
    jp c,set_fail
    ld e,2
    ld a,72
    call 003Bh
    ld e,3
    ld a,71
    jp obj_call
v_c:
    ld hl,rec_list_ff
    ld e,3
    call def_obj
    jp c,set_fail
    ld e,2
    ld a,72
    call 003Bh
    ld e,3
    ld a,72
    jp obj_call
v_d:
    ld e,3
    ld a,73
    jp obj_call
v_e:
    ld hl,rec_list_hl
    ld e,3
    call def_obj
    jp c,set_fail
    ld e,3
    ld a,71
    jp obj_call
v_f:
    ld hl,rec_drop_none
    ld e,7
    call def_obj
    jp c,set_fail
    ld e,7
    ld a,72
    jp obj_call
v_reset:
    ld a,68
    call 003Bh
    xor a
    ld (pb_open),a
    call open_dlg
    jp loop

set_fail:
    ld de,pb_text
    ld hl,t_setfail
    call pb_puts
    call pb_alert_ok
    jp loop

fail:
    ld de,pb_text
    ld hl,t_fail
    call pb_puts
    call pb_alert_ok
quit:
    ld a,(pb_open)
    or a
    jp z,quit2
    ld a,68
    call 003Bh
quit2:
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

; ---------------------------------------------------------------- data
t_o:       db "O=",0
t_e:       db " E=",0
t_b:       db " B=",0
t_de:      db " DE=",0
t_f:       db " F=",0
t_s:       db " S=",0
t_c:       db " C=",0
t_xx:      db "????",0
t_fail:    db "UIPROBE3: the window could not be opened",0
t_setfail: db "UIPROBE3: os_object_define failed",0
ok_tail:   dw 800Dh,80FBh,0,0
           db 79,75,0

item_1: db "Item one",0
item_2: db "Item two",0
item_3: db "Item three",0
item_4: db "Item four",0
item_5: db "Item five",0
item_6: db "Item six (24 characters)",0
; ROSAN283 ob_list "+25 Wd24 24-bit address of string-list = list of 24-bit
; addresses": 3 bytes per item, bank bytes patched at start
item_table:
    dw item_1
    db 0
    dw item_2
    db 0
    dw item_3
    db 0
    dw item_4
    db 0
    dw item_5
    db 0
    dw item_6
    db 0

; the window: 600x400 at 20,50 (the LARGE geometry)
dlg:
    db 1, 0, 1, 0                ; focus, exit-by-click, screen-store, ddm_enable
    db 16
    dw 20, 50, 600, 400
    db "UI probe 3", 0
    ; 1 background box
    db 1
    dw 2, 26, 596, 372
    db 0, 8, 0, 0, 0
    ; 2 list frame, 3 list (4 rows of 16 px, font 7), 4 its scroll bar
    db 1
    dw 26, 48, 307, 68
    db 0, 8, 0, 1, 0
dlg_list:
    db 9
    dw 27, 49, 305, 66
    db 4                         ; +9 linked scroll bar
    dw 6, 4, 0, 0                ; +10 Ntot, +12 Nvis, +14 first, +16
    dw 0FFFFh, 0FFFFh            ; +18 selection (none), +20
    db 7                         ; +22 font
    dw 16                        ; +23 entry height
    dw item_table                ; +25 Wd24 (bank patched)
    db 0
    dw 0                         ; +28 tab
    db 11
    dw 335, 48, 17, 68
    db 3                         ; +9 linked list
    dw 0, 17                     ; +10 handle position, +12 handle size
    ; 5 readout box, 6 readout label (24 spaces), 7 drop button
    db 1
    dw 26, 140, 307, 22
    db 7, 8, 0, 1, 0
    db 2
    dw 30, 144, 288, 1
    db 7, 7, 0
    db "                        ", 0
dlg_drop:
    db 5
    dw 335, 142, 17, 17
    db 6                         ; +9 linked readout label
    dw 26, 163, 307, 54          ; +10 droplist x,y,w,h (4 rows of 13 + 2)
    dw 6, 4, 0                   ; +18 Ntot, +20 Nvis, +22 current
    dw item_table                ; +24 Wd24 (bank patched)
    db 0
    ; 8 horizontal scroll bar (handle 20 px at 0)
    db 12
    dw 26, 240, 280, 17
    db 0
    dw 0, 20
    ; 9 status box, 10 status line (60 characters reserved)
    db 1
    dw 26, 280, 430, 24
    db 0, 8, 0, 0, 0
    db 2
    dw 30, 285, 420, 1
    db 0, 7, 0
    db "Press Reset, then one of the variants A to F.", 0
    ; 11-18 buttons, one column at the right
    db 3
    dw 470, 48, 110, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "A Update", 0
    db 3
    dw 470, 78, 110, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "B Display", 0
    db 3
    dw 470, 108, 110, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "C Prev", 0
    db 3
    dw 470, 138, 110, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "D Focus", 0
    db 3
    dw 470, 168, 110, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "E Hilite", 0
    db 3
    dw 470, 198, 110, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "F Drop none", 0
    db 3
    dw 470, 228, 110, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "Reset", 0
    db 3
    dw 470, 258, 110, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "Quit", 0
    db 0

; records for the variants (same lengths as the originals)
rec_list:
    db 9
    dw 27, 49, 305, 66
    db 4
    dw 6, 4, 2, 2
    dw 2, 2
    db 7
    dw 16
    dw item_table
    db 0
    dw 0
rec_list_ff:
    db 9
    dw 27, 49, 305, 66
    db 4
    dw 6, 4, 2, 0FFFFh
    dw 2, 0FFFFh
    db 7
    dw 16
    dw item_table
    db 0
    dw 0
rec_list_hl:
    db 9
    dw 27, 49, 305, 66
    db 4
    dw 6, 4, 0, 0
    dw 1, 1
    db 7
    dw 16
    dw item_table
    db 0
    dw 0
rec_drop_none:
    db 5
    dw 335, 142, 17, 17
    db 6
    dw 26, 163, 307, 54
    dw 6, 4, 0FFFFh
    dw item_table
    db 0
rec_vbar:
    db 11
    dw 335, 48, 17, 68
    db 3
    dw 20, 30
rec_drop:
    db 5
    dw 335, 142, 17, 17
    db 6
    dw 26, 163, 307, 54
    dw 6, 4, 3
    dw item_table
    db 0
rec_hbar:
    db 12
    dw 26, 240, 280, 17
    db 0
    dw 100, 20
rec_status:
    db 2
    dw 30, 285, 420, 1
    db 0, 7, 0
status_text:
    defs 62

pb_bank:   defs 1
pb_open:   defs 1
pb_obj:    defs 1
pb_ev:     defs 1
pb_b:      defs 1
pb_w:      defs 2
pb_de:     defs 2
pb_off:    defs 2
pb_dst:    defs 2
pb_text:   defs 120
