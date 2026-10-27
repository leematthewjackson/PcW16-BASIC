; ============================================================================
; MEMDIAG — why did MEMPROBE report W=BAD? (M8, after owner XAnne A1)
; ============================================================================
; NOT compiler output and NOT part of the runtime: a hand-written test tool.
;
; Owner XAnne A1:  MEMPROBE F=6C A=01 G=02 94 95 O=0107 P=0107 0107 W=BAD R=6C E=6C
;
; Hypothesis H-ROLL (static, PCW045.SYS os_copy_24bit, block 6 #5CB6):
; os_copy_24bit checks for a block end after EVERY byte, the last one
; included. A copy that ends exactly at the end of a block (offset #4000)
; looks up the owner's next block (os_get_next_mem) and returns carry if
; there is none, AFTER all bytes were copied. MEMPROBE's offset-#3FF0 copies
; end at #4000, and its second block is the owner's last: carry, so "BAD".
;
; Each test separates one possible cause. One alert:
;
;   MEMDIAG G=xx yy P=a b c G4=d e G5=f g B=h i j N=k X=llll Y=mm nn
;
;   G   the two blocks (X = first, Y = second = the owner's last)
;   P   put 16 bytes with os_copy_24bit; N = no carry, C = carry:
;         a: to Y:#0000 (ends #0010)            expected N
;         b: to Y:#3FF0 (ends #4000, last block) H-ROLL: C
;         c: to X:#3FF0 (ends #4000, Y follows)  H-ROLL: N
;   G4  copy Y:#3FF0, 16 bytes, back: carry, then the data (ok/BAD)
;         H-ROLL: C ok   (carry, but the bytes arrived)
;   G5  copy Y:#3FF0, 15 bytes (ends #3FFF) back: N ok
;   B   read with os_get_byte_24bit (fn 42), one byte per call, no
;       os_copy_24bit involved:  Y:#0000..#000F, Y:#3FF0..#3FFF,
;       X:#3FF0..#3FFF against the patterns: ok ok ok if every write landed
;   N   the neighbours Y:#3FEF and X:#3FEF and Y:#0010 still hold the fill
;       byte written first: ok if no write strayed
;   X   IX after test b (ROSAN283: "amount uncopied (0 if OK)")
;   Y   the two bytes fn 42 reads at Y:#0000 and Y:#0001: 50 63 ("Pc")
;       when correct; ?? 50 if writes land one byte late; anything else
;       (the block's old contents) if writes are lost
;
;   Reading: B=ok ok ok and N=ok mean the writes are correct and in place;
;   then G4 tells whether a read that ends at the block end returns the
;   data despite its carry. A "BAD" in B means the writes are wrong;
;   B ok but G5 BAD means reads are wrong.
;
; Safety: as MEMPROBE: writes only into the two blocks os_get_mem gives,
; only if both are RAM (#80..) and owned like the program's own block;
; both released before os_app_exit. No files. No bank switched by the probe.
;
; Build:  pasmo --bin xanne/memdiag.asm artifacts/m8-diag/memdiag.prg
; ============================================================================

    org 4000h
    defs 100h

start:
    call 0CBh                   ; bios_getmem1
    ld (pb_bank),a
    ld e,a
    ld a,38
    call 003Bh                  ; owner of our own block
    jp nc,own_ok
    ld de,0FFFFh
own_ok:
    ld (r_own),de
    ld b,2
    ld e,0
    ld a,34
    call 003Bh                  ; os_get_mem: 2 x 16K
    jp c,report
    ld a,b
    cp 2
    jp nz,keep_some             ; fewer than 2: release what came, report
    ld a,(hl)
    ld (blk_x),a
    inc hl
    ld a,(hl)
    ld (blk_y),a
    ld hl,blk_x
    call safe
    jp nz,release
    ld hl,blk_y
    call safe
    jp nz,release
    ld a,'R'
    ld (r_ran),a

    ; fill: 16 bytes of '.' at Y:#3FE0, X:#3FE0 and Y:#0010 (no block end)
    ld a,(blk_y)
    ld b,a
    ld de,3FE0h
    ld hl,fill
    call put16
    ld a,(blk_x)
    ld b,a
    ld de,3FE0h
    ld hl,fill
    call put16
    ld a,(blk_y)
    ld b,a
    ld de,0010h
    ld hl,fill
    call put16

    ; P a / b / c
    ld a,(blk_y)
    ld b,a
    ld de,0000h
    ld hl,pat1
    call put16
    ld (r_pa),a
    ld a,(blk_y)
    ld b,a
    ld de,3FF0h
    ld hl,pat2
    call put16
    ld (r_pb),a
    ld (r_ix),ix
    ld a,(blk_x)
    ld b,a
    ld de,3FF0h
    ld hl,pat3
    call put16
    ld (r_pc),a

    ; G4: 16 bytes back from Y:#3FF0
    ld hl,rbuf
    ld b,16
g4_clear:
    ld (hl),0
    inc hl
    djnz g4_clear
    ld a,(blk_y)
    ld c,a
    ld hl,3FF0h
    ld ix,16
    call get_n
    ld (r_g4),a
    ld hl,rbuf
    ld de,pat2
    ld b,16
    call compare
    ld (r_g4d),a

    ; G5: 15 bytes back from Y:#3FF0
    ld hl,rbuf
    ld b,16
g5_clear:
    ld (hl),0
    inc hl
    djnz g5_clear
    ld a,(blk_y)
    ld c,a
    ld hl,3FF0h
    ld ix,15
    call get_n
    ld (r_g5),a
    ld hl,rbuf
    ld de,pat2
    ld b,15
    call compare
    ld (r_g5d),a

    ; B: byte reads with fn 42
    ld a,(blk_y)
    ld (rd_blk),a
    ld hl,0000h
    ld de,pat1
    call bytes16
    ld (r_b1),a
    ld a,(blk_y)
    ld (rd_blk),a
    ld hl,3FF0h
    ld de,pat2
    call bytes16
    ld (r_b2),a
    ld a,(blk_x)
    ld (rd_blk),a
    ld hl,3FF0h
    ld de,pat3
    call bytes16
    ld (r_b3),a

    ; Y: the first two bytes of Y as read by fn 42
    push de
    ld a,(blk_y)
    ld c,a
    ld hl,0000h
    ld b,0
    ld a,42
    call 003Bh
    ld a,e
    ld (r_y0),a
    ld a,(blk_y)
    ld c,a
    ld hl,0001h
    ld b,0
    ld a,42
    call 003Bh
    ld a,e
    ld (r_y1),a
    pop de

    ; N: neighbours
    ld a,'K'
    ld (r_nb),a
    ld a,(blk_y)
    ld c,a
    ld hl,3FEFh
    call nb_check
    ld a,(blk_x)
    ld c,a
    ld hl,3FEFh
    call nb_check
    ld a,(blk_y)
    ld c,a
    ld hl,0010h
    call nb_check

release:
    ld a,(pb_bank)
    ld c,a
    ld hl,blk_x
    ld e,0
    ld a,35
    call 003Bh                  ; os_release_mem (list blk_x, blk_y, 0)
report:
    call show
    ld a,23
    call 003Bh                  ; os_app_exit
    ret

; keep_some — os_get_mem gave fewer than 2 (B = count, HL = list): give
; them back unused.
keep_some:
    ld a,b
    or a
    jp z,report
    ld a,(hl)
    ld (blk_x),a                ; list becomes blk_x, 0
    xor a
    ld (blk_y),a
    jp release

; safe — Z if the block at (HL) is #80.. and owned like our own block.
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
    ret
unsafe:
    or 1
    ret

; put16 — 16 bytes from HL (our block) to B:DE. A = 'N' or 'C'; IX as
; os_copy_24bit leaves it.
put16:
    ld a,(pb_bank)
    ld c,a
    ld ix,16
    ld a,41
    call 003Bh
    ld a,'N'
    ret nc
    ld a,'C'
    ret

; get_n — IX bytes from C:HL to rbuf. A = 'N' or 'C'.
get_n:
    ld a,(pb_bank)
    ld b,a
    ld de,rbuf
    ld a,41
    call 003Bh
    ld a,'N'
    ret nc
    ld a,'C'
    ret

; compare — B bytes at HL against DE. A = 'K' (ok) or 'B'.
compare:
    ld a,(de)
    cp (hl)
    jp nz,cmp_bad
    inc hl
    inc de
    djnz compare
    ld a,'K'
    ret
cmp_bad:
    ld a,'B'
    ret

; bytes16 — read 16 bytes at rd_blk:HL with os_get_byte_24bit (B = 0, no
; wind-on), compare with DE. A = 'K' or 'B'. Registers are reloaded for
; every call: the OS keeps only C,HL as documented.
bytes16:
    ld (rd_off),hl
    ld (rd_pat),de
    ld a,16
    ld (rd_n),a
    ld a,'K'
    ld (rd_res),a
b16_loop:
    ld a,(rd_blk)
    ld c,a
    ld hl,(rd_off)
    ld b,0
    ld a,42
    call 003Bh                  ; E = byte
    ld hl,(rd_pat)
    ld a,e
    cp (hl)
    jp z,b16_same
    ld a,'B'
    ld (rd_res),a
b16_same:
    inc hl
    ld (rd_pat),hl
    ld hl,(rd_off)
    inc hl
    ld (rd_off),hl
    ld a,(rd_n)
    dec a
    ld (rd_n),a
    jp nz,b16_loop
    ld a,(rd_res)
    ret

; nb_check — the byte at C:HL must be the fill byte, else r_nb = 'B'.
nb_check:
    ld b,0
    ld a,42
    call 003Bh
    ld a,e
    cp '.'
    ret z
    ld a,'B'
    ld (r_nb),a
    ret

; show — one alert with every result
show:
    ld de,pb_text
    ld hl,t_head
    call puts
    ld a,(blk_x)
    call hex
    call space
    ld a,(blk_y)
    call hex
    ld a,(r_ran)
    cp 'R'
    jp z,show_all
    ld hl,t_skip
    call puts
    jp show_end
show_all:
    ld hl,t_p
    call puts
    ld a,(r_pa)
    call putc_sp
    ld a,(r_pb)
    call putc_sp
    ld a,(r_pc)
    ld (de),a
    inc de
    ld hl,t_g4
    call puts
    ld a,(r_g4)
    call putc_sp
    ld a,(r_g4d)
    call verdict
    ld hl,t_g5
    call puts
    ld a,(r_g5)
    call putc_sp
    ld a,(r_g5d)
    call verdict
    ld hl,t_b
    call puts
    ld a,(r_b1)
    call verdict
    call space
    ld a,(r_b2)
    call verdict
    call space
    ld a,(r_b3)
    call verdict
    ld hl,t_n
    call puts
    ld a,(r_nb)
    call verdict
    ld hl,t_x
    call puts
    ld a,(r_ix+1)
    call hex
    ld a,(r_ix)
    call hex
    ld hl,t_y
    call puts
    ld a,(r_y0)
    call hex
    call space
    ld a,(r_y1)
    call hex
show_end:
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
    ret

verdict:                        ; 'K' -> ok, else BAD
    ld hl,t_ok
    cp 'K'
    jp z,puts
    ld hl,t_bad
    jp puts
putc_sp:
    ld (de),a
    inc de
space:
    ld a,' '
    ld (de),a
    inc de
    ret
puts:
    ld a,(hl)
    or a
    ret z
    ld (de),a
    inc hl
    inc de
    jp puts
hex:
    push af
    srl a
    srl a
    srl a
    srl a
    call nib
    pop af
    and 15
nib:
    add a,'0'
    cp '9'+1
    jp c,nib_out
    add a,7
nib_out:
    ld (de),a
    inc de
    ret

; ---------------------------------------------------------------- data
t_head:  db "MEMDIAG G=",0
t_skip:  db " not run (fewer than 2 blocks, or not ours)",0
t_p:     db " P=",0
t_g4:    db " G4=",0
t_g5:    db " G5=",0
t_b:     db " B=",0
t_n:     db " N=",0
t_x:     db " X=",0
t_y:     db " Y=",0
t_ok:    db "ok",0
t_bad:   db "BAD",0
ok_tail: dw 800Dh,80FBh,0,0
         db 79,75,0
fill:    db "................"
pat1:    db "PcW16-M8-DIAG-#1"
pat2:    db "PcW16-M8-DIAG-#2"
pat3:    db "PcW16-M8-DIAG-#3"

pb_bank: db 0
r_own:   dw 0
blk_x:   db 0
blk_y:   db 0
         db 0                   ; ends the release list
r_ran:   db 0
r_pa:    db '?'
r_pb:    db '?'
r_pc:    db '?'
r_ix:    dw 0FFFFh
r_g4:    db '?'
r_g4d:   db '?'
r_g5:    db '?'
r_g5d:   db '?'
r_b1:    db '?'
r_b2:    db '?'
r_b3:    db '?'
r_nb:    db '?'
r_y0:    db 0
r_y1:    db 0
rd_blk:  db 0
rd_off:  dw 0
rd_pat:  dw 0
rd_n:    db 0
rd_res:  db 0
rbuf:    defs 16
pb_text: defs 120
