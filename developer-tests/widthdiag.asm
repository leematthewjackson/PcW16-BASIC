; ============================================================================
; WIDTHDG — XAnne diagnostic for os_dialog_string_width (fn 82), M5d repair
; ============================================================================
; NOT compiler output and NOT part of the runtime: a hand-written test tool.
; The first M5d label repair (PR #14) called fn 82 with its parameter block
; in the app image (C = app bank, HL in #4000-#7FFF); in XAnne every program
; then stopped before its window opened with "Runtime error: a window control
; could not be updated". This program shows the raw results, so the cause
; can be recorded instead of assumed.
;
; Safety: no files, no keyboard input; it only measures text, defines one
; small dialog (a label), redefines that label, shows the dialog briefly and
; removes it. All results are collected first and shown afterwards, because
; os_alert would disturb a defined dialog.
;
; Tests (all text "WWWWWWWWWW" = 10 W's unless stated; expected 110 px if a
; font-7 W is 11 px, as measured in the D3 screenshots):
;   T1  fn 82, block in the app image, C = app bank   (the first repair)
;   T2  fn 82, block at #2200, C = #80                  (the second repair)
;   T3  as T2, text "Label tests: long, short, empty" (170 px on screen)
;   T4  os_dialog_define of a one-label dialog          (fn 66)
;   T5  as T2, after the define, before display         (the runtime's order)
;   T6  os_object_define of the label after T5          (fn 69)
;   T7  as T1, after the define                         (block in the image)
;   T8  os_object_define of the label after T7          (does T7 disturb it?)
;   T9  os_dialog_display, then os_dialog_remove        (fn 67, 68)
; Each result is shown as one alert:
;   "Tn Cy=c A=aa HL=hhhh (ddddd)"
; Cy = carry after the call (1 = error), A and HL as returned (for T4, T6,
; T8 and T9 HL is undefined: only Cy and A matter there).
;
; OS calls (ROSAN283; numbers from OSCALLS.INC.txt counted from 1, as in
; runtime/runtime.z80.asm): os_dialog_define 66, os_dialog_display 67,
; os_dialog_remove 68, os_object_define 69, os_alert 76,
; os_dialog_string_width 82, os_app_exit 23; bios_getmem1 = call #0CB.
;
; Build:  pasmo --bin xanne/widthdiag.asm artifacts/m5d-fix2/widthdiag.prg
; ============================================================================

    org 4000h
    defs 100h

start:
    ; T1: block in the app image
    ld hl,wd_ten
    ld de,wd_app
    call wd_block
    call 0CBh
    ld c,a
    ld hl,wd_app
    ld a,82
    call 003Bh
    ld (wd_hl),hl
    push af
    pop hl
    ld (wd_af),hl
    ld hl,wd_res+0
    call wd_keep
    ; T2: block at #2200, C = #80
    ld hl,wd_ten
    ld de,2200h
    call wd_block
    ld c,80h
    ld hl,2200h
    ld a,82
    call 003Bh
    ld (wd_hl),hl
    push af
    pop hl
    ld (wd_af),hl
    ld hl,wd_res+4
    call wd_keep
    ; T3: as T2 with the label text
    ld hl,wd_tests
    ld de,2200h
    call wd_block
    ld c,80h
    ld hl,2200h
    ld a,82
    call 003Bh
    ld (wd_hl),hl
    push af
    pop hl
    ld (wd_af),hl
    ld hl,wd_res+8
    call wd_keep
    ; T4: define the dialog
    call 0CBh
    ld c,a
    ld hl,wd_dialog
    ld a,66
    call 003Bh
    ld (wd_hl),hl
    push af
    pop hl
    ld (wd_af),hl
    ld hl,wd_res+12
    call wd_keep
    ; T5: as T2 after the define
    ld hl,wd_ten
    ld de,2200h
    call wd_block
    ld c,80h
    ld hl,2200h
    ld a,82
    call 003Bh
    ld (wd_hl),hl
    push af
    pop hl
    ld (wd_af),hl
    ld hl,wd_res+16
    call wd_keep
    ; T6: redefine the label
    call wd_relabel
    ld (wd_hl),hl
    push af
    pop hl
    ld (wd_af),hl
    ld hl,wd_res+20
    call wd_keep
    ; T7: as T1 after the define
    ld hl,wd_ten
    ld de,wd_app
    call wd_block
    call 0CBh
    ld c,a
    ld hl,wd_app
    ld a,82
    call 003Bh
    ld (wd_hl),hl
    push af
    pop hl
    ld (wd_af),hl
    ld hl,wd_res+24
    call wd_keep
    ; T8: redefine the label again
    call wd_relabel
    ld (wd_hl),hl
    push af
    pop hl
    ld (wd_af),hl
    ld hl,wd_res+28
    call wd_keep
    ; T9: display, then remove (carry of the display is kept)
    ld a,67
    call 003Bh
    ld (wd_hl),hl
    push af
    pop hl
    ld (wd_af),hl
    ld hl,wd_res+32
    call wd_keep
    ld a,68
    call 003Bh
    ; show the nine results
    ld a,'1'
    ld (wd_n),a
    ld hl,wd_res
    ld (wd_p),hl
wd_show:
    call wd_line
    ld hl,(wd_p)
    ld de,4
    add hl,de
    ld (wd_p),hl
    ld a,(wd_n)
    inc a
    ld (wd_n),a
    cp '9'+1
    jp nz,wd_show
    ld a,23
    call 003Bh
    ret

; wd_keep — copy the saved F, A (wd_af) and L, H (wd_hl) of the last OS
; call to the 4-byte result slot at HL. The caller saves them straight
; after the call (push af / pop hl puts F in L and A in H).
wd_keep:
    ld de,(wd_af)
    ld (hl),e
    inc hl
    ld (hl),d
    inc hl
    ld de,(wd_hl)
    ld (hl),e
    inc hl
    ld (hl),d
    ret

; wd_block — build an os_dialog_string_width block at DE: font 7, then
; alignment, style, mode, x, y all 0, then the NUL-terminated text at HL.
wd_block:
    ld a,7
    ld (de),a
    inc de
    xor a
    ld b,7
wd_block_zero:
    ld (de),a
    inc de
    djnz wd_block_zero
wd_block_text:
    ld a,(hl)
    ld (de),a
    inc hl
    inc de
    or a
    jp nz,wd_block_text
    ret

; wd_relabel — os_object_define object 1 with the shorter label record.
wd_relabel:
    ld e,1
    call 0CBh
    ld c,a
    ld hl,wd_label2
    ld a,69
    call 003Bh
    ret

; wd_line — alert "Tn Cy=c A=aa HL=hhhh (ddddd)" for the result at (wd_p).
wd_line:
    ld de,wd_text
    ld a,'T'
    ld (de),a
    inc de
    ld a,(wd_n)
    ld (de),a
    inc de
    ld hl,wd_t_cy
    call wd_puts
    ld hl,(wd_p)
    ld a,(hl)
    and 1
    add a,'0'
    ld (de),a
    inc de
    ld hl,wd_t_a
    call wd_puts
    ld hl,(wd_p)
    inc hl
    ld a,(hl)
    call wd_hex
    ld hl,wd_t_hl
    call wd_puts
    ld hl,(wd_p)
    inc hl
    inc hl
    inc hl
    ld a,(hl)
    call wd_hex
    dec hl
    ld a,(hl)
    call wd_hex
    ld a,' '
    ld (de),a
    inc de
    ld a,'('
    ld (de),a
    inc de
    ld a,(hl)
    inc hl
    ld h,(hl)
    ld l,a
    call wd_dec
    ld a,')'
    ld (de),a
    inc de
    ; os_alert definition tail: NUL, extra NUL, 1 button, 4 key words, "OK"
    xor a
    ld (de),a
    inc de
    ld (de),a
    inc de
    ld a,1
    ld (de),a
    inc de
    ld hl,wd_keys
    ld bc,11
    ldir
    ld hl,wd_text
    ex de,hl
    or a
    sbc hl,de
    ex de,hl
    ld hl,wd_text
    call 0CBh
    ld c,a
    ld a,76
    call 003Bh
    ret

; wd_puts — copy NUL-terminated HL to DE (no NUL); DE advanced.
wd_puts:
    ld a,(hl)
    or a
    ret z
    ld (de),a
    inc hl
    inc de
    jp wd_puts

; wd_hex — A as two hex digits at DE; DE advanced; HL kept.
wd_hex:
    push af
    srl a
    srl a
    srl a
    srl a
    call wd_nib
    pop af
    and 15
wd_nib:
    add a,'0'
    cp '9'+1
    jp c,wd_nib_out
    add a,7
wd_nib_out:
    ld (de),a
    inc de
    ret

; wd_dec — HL as 5 decimal digits at DE; DE advanced.
wd_dec:
    ld bc,10000
    call wd_digit
    ld bc,1000
    call wd_digit
    ld bc,100
    call wd_digit
    ld bc,10
    call wd_digit
    ld bc,1
wd_digit:
    ld a,'0'
wd_digit_loop:
    or a
    sbc hl,bc
    jp c,wd_digit_done
    inc a
    jp wd_digit_loop
wd_digit_done:
    add hl,bc
    ld (de),a
    inc de
    ret

; ---------------------------------------------------------------- data
wd_ten:
    db "WWWWWWWWWW",0
wd_tests:
    db "Label tests: long, short, empty",0
wd_t_cy:
    db " Cy=",0
wd_t_a:
    db " A=",0
wd_t_hl:
    db " HL=",0
wd_keys:
    dw 800Dh,80FBh,0,0
    db 79,75,0
; one-label dialog (layout as the compiler's: 360x120 box at 140,110,
; label at 24,48, w 305, font 7, left-aligned)
wd_dialog:
    db 0,0,1,0
    db 16
    dw 140,110,360,120
    db "Width diagnostic",0
    db 2
    dw 24,48,305,1
    db 0,7,0
    db "Width test, please wait",0
    db 0
; the label's new record, shorter than the original
wd_label2:
    db 2
    dw 24,48,305,1
    db 0,7,0
    db "Width test OK",0

wd_n:
    defs 1
wd_af:
    defs 2
wd_hl:
    defs 2
wd_p:
    defs 2
wd_res:
    defs 36
wd_app:
    defs 64
wd_text:
    defs 80
