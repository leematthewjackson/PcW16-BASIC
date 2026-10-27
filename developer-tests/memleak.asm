; ============================================================================
; MEMLEAK — does Rosanne take back a program's RAM at os_app_exit? (M8)
; ============================================================================
; NOT compiler output: a hand-written test tool. It gets ONE 16K block with
; os_get_mem (34) and exits WITHOUT os_release_mem, after one alert:
;
;   MEMLEAK F=ff G=gg L=ll
;     F  16ks free before (os_ask_mem, 33)
;     G  the block given (00 = none)
;     L  16ks free after the os_get_mem (should be F - 1)
;
; Run MEMPROBE straight after it: MEMPROBE's F equal to MEMLEAK's F means
; the block came back at exit (static analysis of os_app_exit says
; "release all memory": docs/rosanne-research/reference/api-verification.md);
; F one lower means it leaked until the next reset. The compiled programs
; release their blocks themselves either way (rt_bank_free in rt_exit).
; Nothing is written to the block, to any file or to the disk.
;
; Build:  pasmo --bin xanne/memleak.asm artifacts/m8/memleak.prg
; ============================================================================

    org 4000h
    defs 100h

start:
    call 0CBh                   ; bios_getmem1
    ld (pb_bank),a
    ld a,33
    call 003Bh
    ld (r_f),a
    ld b,1
    ld e,0
    ld a,34
    call 003Bh
    jp c,asked
    ld a,b
    or a
    jp z,asked
    ld a,(hl)
    ld (r_g),a
asked:
    ld a,33
    call 003Bh
    ld (r_l),a
    ld de,pb_text
    ld hl,t_f
    call pb_puts
    ld a,(r_f)
    call pb_hex
    ld hl,t_g
    call pb_puts
    ld a,(r_g)
    call pb_hex
    ld hl,t_l
    call pb_puts
    ld a,(r_l)
    call pb_hex
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
    call 003Bh                  ; os_alert
    ld a,23
    call 003Bh                  ; os_app_exit, block deliberately NOT released
    ret

pb_puts:
    ld a,(hl)
    or a
    ret z
    ld (de),a
    inc hl
    inc de
    jp pb_puts

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

t_f:     db "MEMLEAK F=",0
t_g:     db " G=",0
t_l:     db " L=",0
ok_tail: dw 800Dh,80FBh,0,0
         db 79,75,0
pb_bank: db 0
r_f:     db 0
r_g:     db 0
r_l:     db 0
pb_text: defs 40
