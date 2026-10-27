; ============================================================================
; MEMPROBE2 — Rosanne memory blocks for an application (M8, after A1/MEMDIAG)
; ============================================================================
; NOT compiler output and NOT part of the runtime: a hand-written test tool
; for the calls the M8 BANKED arrays depend on. One alert reports:
;
;   F=ff A=aa   os_ask_mem (33) at start: 16ks free / owned by applications
;   G=g n1 n2   os_get_mem (34) for 2 blocks: how many given, block numbers
;   O=oooo      os_get_mem_ownerid (38) of the program's own block (bios_getmem1)
;   P=pppp qqqq ... of the two blocks given
;   W=OK / W=BAD / W=SKIP   write two 16-byte patterns into each owned block
;               (offsets #0000 and #3FF0) with os_copy_24bit (41), read all
;               back and compare (block 1 must still hold its own pattern
;               after block 2 is written)
;   R=ff        os_release_mem (35): 16ks free after the release
;   E=ff        os_ask_mem again: should equal F
;   L=n         how many end-of-last-block carries were excused (expected 2)
;
; MEMPROBE2 vs MEMPROBE (owner XAnne A1 W=BAD, MEMDIAG confirmed H-ROLL):
; os_copy_24bit returns carry when a copy ends exactly at the end of the
; owner's last block, after copying (KNOWN-ISSUES KI-34). MEMPROBE2, like the
; fixed BANKED runtime, excuses that one carry only: a copy at offset #3FF0
; (16 bytes, so it ends at #4000) of the SECOND block, the owner's last. The
; bytes are still compared. Any other carry is W=BAD.
;
; Safety: it writes only into a block that os_get_mem returned, that is a
; RAM block (#80..#FF) and that os_get_mem_ownerid reports with the same
; owner as the program's own block (#01xx); otherwise W=SKIP and nothing is
; written. Both blocks are released before os_app_exit. No files. No bank
; is ever switched by the probe (the OS maps blocks for os_copy_24bit).
;
; Build:  pasmo --bin xanne/memprobe2.asm artifacts/m8-fix/memprobe2.prg
; ============================================================================

    org 4000h
    defs 100h

start:
    call 0CBh                   ; bios_getmem1: the program's own block
    ld (pb_bank),a
    ld a,33
    call 003Bh                  ; os_ask_mem
    ld (r_free0),a
    ld a,b
    ld (r_apps0),a
    ld a,(pb_bank)
    ld e,a
    ld a,38
    call 003Bh                  ; owner of the program's own block
    jp nc,own_ok
    ld de,0FFFFh
own_ok:
    ld (r_own),de
    ld b,2
    ld e,0
    ld a,34
    call 003Bh                  ; os_get_mem: 2 x 16K for this application
    jp nc,got
    xor a
    ld b,a
got:
    ld a,b
    ld (r_got),a
    or a
    jp z,owners                 ; nothing given (blist stays 0,0,0)
    cp 3
    jp c,got_copy
    ld b,2                      ; never more than asked for
got_copy:
    ld de,blist
    ld c,b
    ld b,0
    ldir
    xor a
    ld (de),a

owners:
    ld hl,blist
    ld de,r_own1
    call owner_of
    ld hl,blist+1
    ld de,r_own2
    call owner_of

    ; write only if both blocks are RAM and ours
    ld a,'S'
    ld (r_rw),a                 ; SKIP unless proved safe
    ld a,(r_got)
    cp 2
    jp nz,release
    ld hl,blist
    call safe
    jp nz,release
    ld hl,blist+1
    call safe
    jp nz,release
    ld a,'K'
    ld (r_rw),a                 ; OK unless a comparison fails
    ld a,(blist)
    ld b,a
    ld de,0000h
    ld hl,pat1
    call put16
    ld a,(blist)
    ld b,a
    ld de,3FF0h
    ld hl,pat1
    call put16
    ld a,(blist+1)
    ld b,a
    ld de,0000h
    ld hl,pat2
    call put16
    ld a,(blist+1)
    ld b,a
    ld de,3FF0h
    ld hl,pat2
    call put16
    ld a,(blist)
    ld c,a
    ld hl,0000h
    ld de,pat1
    call check16
    ld a,(blist)
    ld c,a
    ld hl,3FF0h
    ld de,pat1
    call check16
    ld a,(blist+1)
    ld c,a
    ld hl,0000h
    ld de,pat2
    call check16
    ld a,(blist+1)
    ld c,a
    ld hl,3FF0h
    ld de,pat2
    call check16

release:
    ld a,(r_got)
    or a
    jp z,asked
    ld a,(pb_bank)
    ld c,a
    ld hl,blist
    ld e,0
    ld a,35
    call 003Bh                  ; os_release_mem
    jp nc,released
    ld a,0FFh
released:
    ld (r_rel),a
asked:
    ld a,33
    call 003Bh
    ld (r_free1),a
    call report
    ld a,23
    call 003Bh                  ; os_app_exit
    ret

; owner_of — (DE) = owner word of the block at (HL); #FFFF if none / error.
owner_of:
    ld a,(hl)
    push de
    ld de,0FFFFh
    or a
    jp z,owner_put
    ld e,a
    ld a,38
    call 003Bh
    jp nc,owner_put
    ld de,0FFFFh
owner_put:
    ex de,hl
    pop de
    ex de,hl
    ld (hl),e
    inc hl
    ld (hl),d
    ret

; safe — Z if the block at (HL) is #80..#FF and owned like the program's
; own block (owner word equal, high byte #01).
safe:
    ld a,(hl)
    cp 80h
    jp c,unsafe
    ld e,a
    ld a,38
    call 003Bh
    jp c,unsafe
    ld a,d
    cp 1
    jp nz,unsafe
    ld hl,(r_own)
    ld a,h
    cp d
    jp nz,unsafe
    ld a,l
    cp e
    ret                         ; Z when equal
unsafe:
    or 1                        ; NZ
    ret

; put16 — copy 16 bytes from HL (program bank) to block B, offset DE.
put16:
    ld a,b
    ld (cur_blk),a
    ld (cur_off),de
    ld a,(pb_bank)
    ld c,a
    ld ix,16
    ld a,41
    call 003Bh
    ret nc
    call excusable
    ret z
    ld a,'B'
    ld (r_rw),a
    ret

; excusable — Z if the copy just made (cur_blk : cur_off, 16 bytes) ended
; exactly at #4000 of the second block, the owner's last; counts it in r_lc.
excusable:
    ld hl,(cur_off)
    ld de,16
    add hl,de
    ld a,h
    cp 40h
    ret nz
    ld a,l
    or a
    ret nz
    ld a,(blist+1)
    ld hl,cur_blk
    cp (hl)
    ret nz
    ld hl,r_lc
    inc (hl)
    xor a
    ret

; check16 — read 16 bytes from block C, offset HL into rbuf; compare with DE.
check16:
    ld a,c
    ld (cur_blk),a
    ld (cur_off),hl
    push de
    ld a,(pb_bank)
    ld b,a
    ld de,rbuf
    ld ix,16
    ld a,41
    call 003Bh
    pop de
    jp nc,check_data
    push de
    call excusable
    pop de
    jp nz,bad
check_data:
    ld hl,rbuf
    ld b,16
check_byte:
    ld a,(de)
    cp (hl)
    jp nz,bad
    inc hl
    inc de
    djnz check_byte
    ret
bad:
    ld a,'B'
    ld (r_rw),a
    ret

; report — one alert with every value
report:
    ld de,pb_text
    ld hl,t_f
    call pb_puts
    ld a,(r_free0)
    call pb_hex
    ld hl,t_a
    call pb_puts
    ld a,(r_apps0)
    call pb_hex
    ld hl,t_g
    call pb_puts
    ld a,(r_got)
    call pb_hex
    ld a,' '
    ld (de),a
    inc de
    ld a,(blist)
    call pb_hex
    ld a,' '
    ld (de),a
    inc de
    ld a,(blist+1)
    call pb_hex
    ld hl,t_o
    call pb_puts
    ld hl,r_own
    call pb_word
    ld hl,t_p
    call pb_puts
    ld hl,r_own1
    call pb_word
    ld a,' '
    ld (de),a
    inc de
    ld hl,r_own2
    call pb_word
    ld hl,t_w
    call pb_puts
    ld hl,t_skip
    ld a,(r_rw)
    cp 'S'
    jp z,report_w
    ld hl,t_ok
    cp 'K'
    jp z,report_w
    ld hl,t_bad
report_w:
    call pb_puts
    ld hl,t_r
    call pb_puts
    ld a,(r_rel)
    call pb_hex
    ld hl,t_e
    call pb_puts
    ld a,(r_free1)
    call pb_hex
    ld hl,t_l
    call pb_puts
    ld a,(r_lc)
    call pb_hex
    ; os_alert definition: text, NUL, NUL, 1 button, 4 key words, "OK"
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

; pb_word — the word at HL as four hex digits at DE.
pb_word:
    inc hl
    ld a,(hl)
    call pb_hex
    dec hl
    ld a,(hl)
    jp pb_hex

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
t_f:     db "MEMPROBE2 F=",0
t_a:     db " A=",0
t_g:     db " G=",0
t_o:     db " O=",0
t_p:     db " P=",0
t_w:     db " W=",0
t_ok:    db "OK",0
t_bad:   db "BAD",0
t_skip:  db "SKIP",0
t_r:     db " R=",0
t_e:     db " E=",0
t_l:     db " L=",0
ok_tail: dw 800Dh,80FBh,0,0
         db 79,75,0
pat1:    db "PcW16-M8-BLOCK-1"
pat2:    db "PcW16-M8-BLOCK-2"

pb_bank:  defs 1
r_free0:  defs 1
r_apps0:  defs 1
r_got:    defs 1
r_own:    defs 2
r_own1:   defs 2
r_own2:   defs 2
r_rw:     defs 1
r_rel:    defs 1
r_free1:  defs 1
blist:    defs 3
rbuf:     defs 16
cur_blk:  db 0
cur_off:  dw 0
r_lc:     db 0
pb_text:  defs 120
