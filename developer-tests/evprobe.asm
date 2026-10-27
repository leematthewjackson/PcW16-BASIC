; ============================================================================
; EVPROBE — what Rosanne reports when a list item is double-clicked
; ============================================================================
; NOT compiler output and NOT part of the runtime: a hand-written test tool
; for owner issue L3 (M7 retest: double-clicking a LIST item never ran its
; ACTION handler in SHOPLST2). The compiled runtime runs ACTION on an
; om_objevent for the list with event type obev_dclick (2; CONSTOS.Z80
; "RSSET #01: obev_click, obev_dclick"). This probe shows which events
; really arrive, so the repair can follow evidence:
;
;   line 1  the last four events, oldest first, each "cccc:oo.tt.bb":
;           cccc = event code from os_wait_event (ROSAN283 bit 13 #2000 = OS
;           message; bit 8 #0100 left click, bit 9 #0200 left double-click,
;           bit 10 #0400 release), oo = object, tt = object event type
;           (01 click, 02 double-click), bb = B from os_process_event;
;           "--.--.--" for an event that is not an OS message.
;           Mouse-movement / rectangle events (bits 11, 12) are not listed.
;   line 2  C = list clicks (type 1), D = list double-clicks (type 2),
;           R = raw left double-clicks (#0200), M = mode, and the last
;           scroll-bar B / DE (for the drag question, owner issue L4).
;
;   Redraw  toggles mode R: after every click or double-click on the list
;           the probe redefines the list (first row and selection read
;           back from the live record, "previous" words #FFFF) and draws
;           it with os_object_display, which is what compiled programs do.
;           Mode P (plain) only passes events to os_process_event.
;
; Safety: no files; no memory requested from the OS. Six items in four
; rows, so every visible row has a real item.
;
; OS calls: as UIPROBE3 (2 wait, 4 process, 23 exit, 66/67/68 dialog,
; 69 object define, 70/48/42 live record words, 71 display, 72 update,
; 76 alert).
;
; Build:  pasmo --bin xanne/evprobe.asm artifacts/m7-fix/evprobe.prg
; ============================================================================

    org 4000h
    defs 100h

start:
    call 0CBh
    ld (pb_bank),a
    ld (dlg_list+27),a           ; Wd24 bank bytes of the string table
    ld (rec_list+27),a
    ld hl,item_table+2           ; and the bank byte of every item pointer
    ld b,6
patch:
    ld (hl),a
    inc hl
    inc hl
    inc hl
    dec b
    jp nz,patch
    ld hl,ring                   ; four empty log entries
    ld b,4*14
blank:
    ld (hl),' '
    inc hl
    djnz blank
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
    call show

loop:
    ld hl,0FFFFh
    ld a,2
    call 003Bh
    jp z,loop
    ld (ev_code),hl
    ld a,0FFh
    ld (ev_obj),a
    ld (ev_typ),a
    ld (ev_b),a
    bit 5,h
    jp z,raw
    ld a,(ix+2)
    cp 5
    jp z,quit                    ; om_exit
    ld (ev_msg),a
    ld a,(ix+3)
    ld (ev_obj),a
    ld a,(ix+5)
    ld (ev_typ),a
    ld a,4                       ; os_process_event, IX = the record
    call 003Bh
    ld a,b
    ld (ev_b),a
    ld (ev_de),de
    ld a,(ev_msg)
    cp 4
    jp nz,logged                 ; not om_objevent
    ld a,(ev_obj)
    cp 3
    jp z,on_list
    cp 4
    jp z,on_bar
    ld a,(ev_typ)
    cp 1
    jp nz,logged
    ld a,(ev_obj)
    cp 10
    jp z,b_redraw
    cp 11
    jp z,b_clear
    cp 12
    jp z,quit
    jp logged

raw:
    ld a,h
    and 18h                      ; mouse movement / rectangle: not listed
    jp nz,loop
    ld a,h
    and 2
    jp z,logged
    ld hl,n_raw2
    inc (hl)
    jp logged

on_bar:
    ld a,(ev_b)
    ld (bar_b),a
    ld hl,(ev_de)
    ld (bar_de),hl
    jp logged

on_list:
    ld a,(ev_typ)
    cp 1
    jp nz,on_list2
    ld hl,n_click
    inc (hl)
    jp on_list3
on_list2:
    cp 2
    jp nz,logged
    ld hl,n_dclick
    inc (hl)
on_list3:
    ld a,(pb_mode)
    or a
    jp z,logged
    ; mode R: rebuild the list as compiled programs do
    ld a,3
    ld b,14
    call live_word
    ld (rec_list+14),hl          ; first visible
    ld a,3
    ld b,18
    call live_word
    ld (rec_list+18),hl          ; selection
    ld hl,0FFFFh
    ld (rec_list+16),hl
    ld (rec_list+20),hl
    ld a,(pb_bank)
    ld c,a
    ld hl,rec_list
    ld e,3
    ld a,69
    call 003Bh
    ld e,3
    ld a,71
    call 003Bh
    jp logged

b_redraw:
    ld a,(pb_mode)
    xor 1
    ld (pb_mode),a
    jp logged
b_clear:
    xor a
    ld (n_click),a
    ld (n_dclick),a
    ld (n_raw2),a
    ld hl,ring
    ld b,4*14
b_clear2:
    ld (hl),' '
    inc hl
    djnz b_clear2
    call show
    jp loop

; logged — add the event to the ring (oldest dropped), redraw both lines.
logged:
    ld hl,ring+14
    ld de,ring
    ld bc,3*14
    ldir
    ld de,ring+3*14
    ld a,(ev_code+1)
    call pb_hex
    ld a,(ev_code)
    call pb_hex
    ld a,':'
    ld (de),a
    inc de
    ld a,(ev_code+1)
    bit 5,a
    jp z,logged_raw
    ld a,(ev_obj)
    call pb_hex
    ld a,'.'
    ld (de),a
    inc de
    ld a,(ev_typ)
    call pb_hex
    ld a,'.'
    ld (de),a
    inc de
    ld a,(ev_b)
    call pb_hex
    jp logged_end
logged_raw:
    ld hl,t_none
    call pb_puts
logged_end:
    ld a,' '
    ld (de),a
    call show
    jp loop

; show — rebuild line 1 (the ring) and line 2 (counters), update both.
show:
    ld hl,ring
    ld de,line1_text
    ld bc,4*14
    ldir
    xor a
    ld (de),a
    ld de,line2_text
    ld hl,t_c
    call pb_puts
    ld a,(n_click)
    call pb_hex
    ld hl,t_d
    call pb_puts
    ld a,(n_dclick)
    call pb_hex
    ld hl,t_r
    call pb_puts
    ld a,(n_raw2)
    call pb_hex
    ld hl,t_mp
    ld a,(pb_mode)
    or a
    jp z,show_mode
    ld hl,t_mr
show_mode:
    call pb_puts
    ld hl,t_b
    call pb_puts
    ld a,(bar_b)
    call pb_hex
    ld hl,t_de
    call pb_puts
    ld a,(bar_de+1)
    call pb_hex
    ld a,(bar_de)
    call pb_hex
    xor a
    ld (de),a
    ld a,(pb_bank)
    ld c,a
    ld hl,rec_line1
    ld e,6
    ld a,69
    call 003Bh
    ld e,5
    ld a,72
    call 003Bh
    ld e,6
    ld a,72
    call 003Bh
    ld a,(pb_bank)
    ld c,a
    ld hl,rec_line2
    ld e,8
    ld a,69
    call 003Bh
    ld e,7
    ld a,72
    call 003Bh
    ld e,8
    ld a,72
    call 003Bh
    ret

; live_word — HL = the word at offset B of object A's live definition
; (the UIPROBE3 sequence: fn 70, fn 48, two fn 42 reads); #FFFF on error.
live_word:
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
    ld (pb_w),a
    ld b,0
    ld a,42
    call 003Bh
    ld a,e
    ld (pb_w+1),a
    ld hl,(pb_w)
    ret
live_fail:
    ld hl,0FFFFh
    ret

fail:
    ld de,pb_text
    ld hl,t_fail
    call pb_puts
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
t_none:    db "--.--.--",0
t_c:       db "C=",0
t_d:       db " D=",0
t_r:       db " R=",0
t_mp:      db " M=P",0
t_mr:      db " M=R",0
t_b:       db " B=",0
t_de:      db " DE=",0
t_fail:    db "EVPROBE: the window could not be opened",0
ok_tail:   dw 800Dh,80FBh,0,0
           db 79,75,0

item_1: db "Item one",0
item_2: db "Item two",0
item_3: db "Item three",0
item_4: db "Item four",0
item_5: db "Item five",0
item_6: db "Item six",0
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
    db "Event probe", 0
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
    dw 6, 4, 0, 0FFFFh           ; +10 Ntot, +12 Nvis, +14 first, +16
    dw 0FFFFh, 0FFFFh            ; +18 selection (none), +20
    db 7                         ; +22 font
    dw 16                        ; +23 entry height
    dw item_table                ; +25 Wd24 (bank patched)
    db 0
    dw 0                         ; +28 tab
    db 11
    dw 335, 48, 17, 68
    db 3                         ; +9 linked list
    dw 0, 22                     ; +10 handle position, +12 handle size
    ; 5 box + 6 line 1, 7 box + 8 line 2 (60 characters reserved each)
    db 1
    dw 26, 180, 560, 24
    db 0, 8, 0, 0, 0
    db 2
    dw 30, 185, 550, 1
    db 0, 7, 0
    db "Double-click Item two, then read both lines.                ", 0  ; 60: never shorter than a log line
    db 1
    dw 26, 214, 560, 24
    db 0, 8, 0, 0, 0
    db 2
    dw 30, 219, 550, 1
    db 0, 7, 0
    db "C=00 D=00 R=00 M=P                                          ", 0
    ; 9 a fixed hint
    db 2
    dw 30, 150, 550, 1
    db 0, 7, 0
    db "Redraw switches P / R. Clear empties the log.", 0
    ; 10-12 buttons
    db 3
    dw 470, 48, 110, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "Redraw", 0
    db 3
    dw 470, 78, 110, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "Clear", 0
    db 3
    dw 470, 108, 110, 24
    db 0, 0, 0, 0, 0, 0, 0, 0
    db 0
    db "Quit", 0
    db 0

; mode R: the list record defined again after a click (same length)
rec_list:
    db 9
    dw 27, 49, 305, 66
    db 4
    dw 6, 4, 0, 0FFFFh
    dw 0FFFFh, 0FFFFh
    db 7
    dw 16
    dw item_table
    db 0
    dw 0
rec_line1:
    db 2
    dw 30, 185, 550, 1
    db 0, 7, 0
line1_text:
    defs 62
rec_line2:
    db 2
    dw 30, 219, 550, 1
    db 0, 7, 0
line2_text:
    defs 62

pb_bank:   defs 1
pb_open:   defs 1
pb_mode:   defs 1
ev_code:   defs 2
ev_msg:    defs 1
ev_obj:    defs 1
ev_typ:    defs 1
ev_b:      defs 1
ev_de:     defs 2
bar_b:     defs 1
bar_de:    defs 2
n_click:   defs 1
n_dclick:  defs 1
n_raw2:    defs 1
pb_w:      defs 2
pb_off:    defs 2
ring:      defs 4*14
pb_text:   defs 80
