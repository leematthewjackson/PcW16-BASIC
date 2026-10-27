; ============================================================================
; UIPROBE2 — XAnne probe for the M6 Phase 2 Rosanne contracts
; ============================================================================
; NOT compiler output and NOT part of the runtime: a hand-written test tool,
; like UIPROBE (M6 Phase 1). It defines an ob_list with its linked
; ob_vscroll, an ob_dropbutton with its readout label, and an ob_hscroll,
; with the same record layouts and data placement the Phase 2 runtime uses
; (item texts in the app image, reached through a table of 24-bit pointers
; whose bank bytes come from bios_getmem1), and shows what Rosanne reports.
;
; Safety: no files; no memory requested from the OS.
;
; After every event on objects 3, 4, 7 or 8 the status line (object 10)
; shows:  O=obj E=evtype B=bb DE=dddd F=first S=sel C=current
; (all hex; F and S are the list's live +14 / +18 words, C the drop-down's
; live +22 word, read back with os_object_get_define / os_get_byte_24bit).
;
; Questions (owner steps in docs/M6-PHASE2-ACCEPTANCE.md, U1-U6):
;   U1  are the six items drawn from the pointer table; is selection #FFFF
;       ("none") accepted (no item highlighted)?
;   U2  a click on an item: E, and S = the item (0-based); does a double-
;       click report E=02?
;   U3  the list's scroll bar was defined with handle position 0, size 17
;       (as NIKMACRO n_list_box): does Rosanne size and move the handle
;       itself? arrows / page clicks / drag: B (doc 1,2,3,4,5) and DE; does
;       F change by itself (does Rosanne scroll the linked list)?
;   U4  the drop-down: does the list open below the readout; after a
;       choice, C = the item, and does Rosanne write the readout label?
;   U5  the horizontal bar: B and DE for arrows, page clicks and drag; does
;       the handle move by itself?
;   U6  "Set" redefines the list (first 2, selection 2), its bar (position
;       20, size 30), the drop-down (current 3) and the bar (position 100)
;       with os_object_define + os_object_update, as the runtime does.
;
; OS calls (ROSAN283; numbers from OSCALLS.INC.txt counted from 1):
; os_wait_event 2, os_process_event 4, os_app_exit 23, os_get_byte_24bit 42,
; os_add_24bit 48, os_dialog_define 66, os_dialog_display 67,
; os_dialog_remove 68, os_object_define 69, os_object_get_define 70,
; os_object_update 72, os_alert 76; bios_getmem1 = call #0CB.
;
; Build:  pasmo --bin xanne/uiprobe2.asm artifacts/m6-phase2/uiprobe2.prg
; ============================================================================

    org 4000h
    defs 100h

start:
    call 0CBh
    ld (pb_bank),a
    ld (rec_list+27),a           ; Wd24 bank bytes of the two string tables
    ld (rec_drop+26),a
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
    jp z,do_read
    cp 12
    jp z,do_set
    cp 13
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

do_read:
    ld de,pb_text
    ld hl,t_read
    call pb_puts
    call live_fsc
    call pb_alert_ok
    jp loop

; U6 — redefine every Phase 2 object, then update each (box first)
do_set:
    ld a,(pb_bank)
    ld c,a
    ld hl,rec_list
    ld e,3
    ld a,69
    call 003Bh
    jp c,set_fail
    ld a,(pb_bank)
    ld c,a
    ld hl,rec_vbar
    ld e,4
    ld a,69
    call 003Bh
    jp c,set_fail
    ld a,(pb_bank)
    ld c,a
    ld hl,rec_drop
    ld e,7
    ld a,69
    call 003Bh
    jp c,set_fail
    ld a,(pb_bank)
    ld c,a
    ld hl,rec_hbar
    ld e,8
    ld a,69
    call 003Bh
    jp c,set_fail
    ld e,2
    ld a,72
    call 003Bh
    ld e,3
    ld a,72
    call 003Bh
    ld e,4
    ld a,72
    call 003Bh
    ld e,7
    ld a,72
    call 003Bh
    ld e,8
    ld a,72
    call 003Bh
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
t_read:    db "Live:",0
t_fail:    db "UIPROBE2: the window could not be opened",0
t_setfail: db "UIPROBE2: os_object_define failed (Set)",0
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
    db "UI probe 2", 0
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
    dw 26, 280, 560, 24
    db 0, 8, 0, 0, 0
    db 2
    dw 30, 285, 550, 1
    db 0, 7, 0
    db "Click the list, the bars or the drop button.", 0
    ; 11-13 buttons
    db 3
    dw 22, 340, 96, 24
    db 0Dh, 80h, 0, 0, 0, 0, 0, 0
    db 0
    db "Read", 0
    db 3
    dw 132, 340, 96, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "Set", 0
    db 3
    dw 242, 340, 96, 24
    db 0FEh, 80h, 0, 0, 0, 0, 0, 0
    db 0
    db "Quit", 0
    db 0

; records for "Set" (same lengths as the originals)
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
    dw 30, 285, 550, 1
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
