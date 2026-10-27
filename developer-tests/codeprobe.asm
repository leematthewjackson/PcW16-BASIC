; ============================================================================
; CODEPROBE — can a program run code beyond its first 16K? (M8 research)
; ============================================================================
; NOT compiler output and NOT part of the runtime: a hand-written test tool
; for the self-loading pattern seen in two shipped third-party programs
; (docs/M8-ROSANNE-MEMORY-RESEARCH.md §6): the loader gives a program ONE
; 16K block (its first 16K); the program asks for more RAM, reads the rest
; of its own .PRG into it and maps it at #8000 itself.
;
; The image is 16K + a small tail. The tail is assembled at #8000 and holds
; 256 bytes 00..FF (sum #7F80) and a last byte #A5, plus two routines.
;
; Stage 1 (one alert, quarter 2 restored before it is shown):
;   N=name X=ext      the name block the loader left at #4000 (ROSAN283
;                     "Execution": 256 bytes free for the program; the
;                     loader copies the name over them - static analysis)
;   G=gg P=pppp       os_get_mem (34) 1 x 16K: block, its owner (38)
;   O=ee              os_open_file (144) of that name, read mode: 00 = OK
;   (method 2 runs first, method 1 last, each after its own open)
;   R=aa bb cc        method 1: three os_read_file (147) results (00 = OK):
;                     8K + 8K skip the first 16K, then the tail into block gg
;   C=OK|BAD|SKIP     map gg at #8000 (bios_setmem2), call the tail's sum
;                     routine, map the old block back (bios_getmem2 first)
;   S=ss T=tt D=OK..  method 2: os_set_ptr (156) to #4000 (documented "Flash
;                     only"), the tail read (T), the same call (D)
;   Q=qq qq           the #8000 block before / after (must be equal)
;   F=ff              16ks free at the start (os_ask_mem, 33)
; Stage 2 (only if C=OK; second alert): the tail calls os_ask_mem from
;   code at #8xxx and returns:  "CODEPROBE 2 K=OK A=ff M=gg"
;   If the PcW16 hangs after the first alert, that IS the result: an OS
;   call made from code in quarter 2 did not come back.
;
; Safety: the file is opened for READ only; nothing is written to any file
; or disk. RAM is written only in the block os_get_mem returned, only if it
; is #80..#FF and owned like the program's own block, and only through the
; window the probe maps itself. The block is released before os_app_exit.
;
; Build:  pasmo --bin xanne/codeprobe.asm artifacts/m8/codeprobe.prg
; ============================================================================

bios_setmem2 equ 0C2h           ; #80 + 3 x #16 (ROSAN283 BIOS table)
bios_getmem2 equ 0CEh           ; #80 + 3 x #1A
namebuf      equ 2F00h          ; bottom quarter: #2000..#2FFF is the program's
extbuf       equ 2F40h
TAIL_FILE_OFFSET equ 4000h

    org 4000h
    defs 100h

start:
    call 0CBh                   ; bios_getmem1: the program's own block
    ld (pb_bank),a
    call bios_getmem2
    ld (r_q0),a
    ld a,33
    call 003Bh
    ld (r_free0),a
    ld a,(pb_bank)
    ld e,a
    ld a,38
    call 003Bh
    jp nc,own_ok
    ld de,0FFFFh
own_ok:
    ld (r_own),de
    call name_copy
    ; one block for the tail
    ld b,1
    ld e,0
    ld a,34
    call 003Bh
    jp c,report1
    ld a,b
    or a
    jp z,report1
    ld a,(hl)
    ld (blk),a
    ld e,a
    ld a,38
    call 003Bh
    jp nc,blk_owner
    ld de,0FFFFh
blk_owner:
    ld (r_bown),de
    ; safe = RAM block, owned like the program's own block
    ld a,(blk)
    cp 80h
    jp c,report1
    ld hl,(r_own)
    ld a,h
    cp 1
    jp nz,report1
    ld de,(r_bown)
    ld a,d
    cp h
    jp nz,report1
    ld a,e
    cp l
    jp nz,report1
    ld a,1
    ld (safe),a

    ; method 2 first: os_set_ptr straight to the tail (documented "Flash only")
    call open_self
    ld (r_open),a
    or a
    jp nz,report1
    ld b,0
    ld de,TAIL_FILE_OFFSET
    ld a,156
    call 003Bh
    call result
    ld (r_sp),a
    or a
    jp nz,m1
    ld de,TAIL_LEN
    call read_to_blk
    ld (r_rd4),a
    or a
    jp nz,m1
    call call_sum
    ld (r_c2),a
m1:
    call close_self
    ; method 1, last (so the tail it loads stays for stage 2): reopen and
    ; skip the first 16K by reading it in 8K pieces (any filling up to the
    ; end of a 512-byte disc block stays inside our block), then the tail
    call clear_tail
    call open_self
    ld (r_open),a
    or a
    jp nz,report1
    ld de,2000h
    call read_to_blk
    ld (r_rd1),a
    ld de,2000h
    call read_to_blk
    ld (r_rd2),a
    ld de,TAIL_LEN
    call read_to_blk
    ld (r_rd3),a
    ld hl,r_rd1
    ld a,(hl)
    inc hl
    or (hl)
    inc hl
    or (hl)
    jp nz,m1_close
    call call_sum
    ld (r_c1),a
m1_close:
    call close_self

report1:
    call bios_getmem2
    ld (r_q1),a
    call report
    ld a,(r_c1)
    cp 'K'
    jp nz,release
    ; stage 2: an OS call from code at #8xxx
    call bios_getmem2
    push af
    ld a,(blk)
    call bios_setmem2
    call tail_os                ; returns A = os_ask_mem's A, B = block at #8000
    ld (r_k_a),a
    ld a,b
    ld (r_k_m),a
    pop af
    call bios_setmem2
    call report2

release:
    ld a,(blk)
    or a
    jp z,exit
    xor a
    ld (blk+1),a
    ld a,(pb_bank)
    ld c,a
    ld hl,blk
    ld e,0
    ld a,35
    call 003Bh                  ; os_release_mem
exit:
    ld a,23
    call 003Bh                  ; os_app_exit
    ret

; open_self — os_open_file (144) of namebuf/extbuf for READ. A = 0 or error.
open_self:
    ld hl,namebuf
    ld de,extbuf
    ld b,0
    ld a,144
    call 003Bh
    jp result

close_self:
    ld b,0
    ld a,145
    call 003Bh                  ; os_close_file (read)
    ret

; result — after an OS call: A = 0 if NC, else the error code in A.
result:
    ret c
    xor a
    ret

; read_to_blk — os_read_file DE bytes (B = 0) to blk:0000. A = 0 or error.
read_to_blk:
    ld b,0
    ld a,(blk)
    ld c,a
    ld hl,0000h
    ld a,147
    call 003Bh
    jp result

; call_sum — map blk at #8000, call the tail's sum routine, map back.
; A = 'K' if HL = #7F80 and the last byte is #A5, else 'B'.
call_sum:
    call bios_getmem2
    push af
    ld a,(blk)
    call bios_setmem2
    call tail_sum
    ld b,a
    pop af
    call bios_setmem2
    ld a,b
    cp 0A5h
    jp nz,call_bad
    ld a,h
    cp 7Fh
    jp nz,call_bad
    ld a,l
    cp 80h
    jp nz,call_bad
    ld a,'K'
    ret
call_bad:
    ld a,'B'
    ret

; clear_tail — zero the tail area of blk through our own #8000 window.
clear_tail:
    call bios_getmem2
    push af
    ld a,(blk)
    call bios_setmem2
    ld hl,8000h
    ld de,8001h
    ld bc,TAIL_LEN-1
    ld (hl),0
    ldir
    pop af
    call bios_setmem2
    ret

; name_copy — the name block at #4000 to namebuf / extbuf (bottom quarter,
; as os_open_file requires). The extension is the string after the name's
; NUL if it starts with '.', otherwise ".PRG" (r_xdef = 'D').
name_copy:
    ld hl,4000h
    ld de,namebuf
    ld b,32
nc_loop:
    ld a,(hl)
    ld (de),a
    inc hl
    inc de
    or a
    jp z,nc_ext
    djnz nc_loop
    xor a
    ld (de),a
    ld a,(hl)                   ; a 32-character name: skip its NUL too
    or a
    jp nz,nc_ext
    inc hl
nc_ext:
    ld a,(hl)
    cp '.'
    jp nz,nc_default
    ld de,extbuf
    ld b,8
nc_ext_loop:
    ld a,(hl)
    ld (de),a
    inc hl
    inc de
    or a
    ret z
    djnz nc_ext_loop
    xor a
    ld (de),a
    ret
nc_default:
    ld a,'D'
    ld (r_xdef),a
    ld hl,dot_prg
    ld de,extbuf
    ld bc,5
    ldir
    ret

report:
    ld de,pb_text
    ld hl,t_n
    call pb_puts
    ld hl,namebuf
    call pb_puts
    ld hl,t_x
    call pb_puts
    ld hl,extbuf
    call pb_puts
    ld a,(r_xdef)
    or a
    jp z,rep_g
    ld (de),a
    inc de
rep_g:
    ld hl,t_g
    call pb_puts
    ld a,(blk)
    call pb_hex
    ld hl,t_p
    call pb_puts
    ld hl,r_bown
    call pb_word
    ld hl,t_o
    call pb_puts
    ld a,(r_open)
    call pb_hex
    ld hl,t_r
    call pb_puts
    ld a,(r_rd1)
    call pb_hex_sp
    ld a,(r_rd2)
    call pb_hex_sp
    ld a,(r_rd3)
    call pb_hex
    ld hl,t_c
    call pb_puts
    ld a,(r_c1)
    call pb_verdict
    ld hl,t_s
    call pb_puts
    ld a,(r_sp)
    call pb_hex
    ld hl,t_t
    call pb_puts
    ld a,(r_rd4)
    call pb_hex
    ld hl,t_d
    call pb_puts
    ld a,(r_c2)
    call pb_verdict
    ld hl,t_q
    call pb_puts
    ld a,(r_q0)
    call pb_hex_sp
    ld a,(r_q1)
    call pb_hex
    ld hl,t_f
    call pb_puts
    ld a,(r_free0)
    call pb_hex
    jp alert

report2:
    ld de,pb_text
    ld hl,t_k
    call pb_puts
    ld a,(r_k_a)
    call pb_hex
    ld hl,t_m
    call pb_puts
    ld a,(r_k_m)
    call pb_hex
    jp alert

; alert — os_alert (76) with the text at pb_text..DE and one OK button.
alert:
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

; pb_verdict — 'K' -> OK, 'B' -> BAD, else SKIP
pb_verdict:
    ld hl,t_ok
    cp 'K'
    jp z,pb_puts
    ld hl,t_bad
    cp 'B'
    jp z,pb_puts
    ld hl,t_skip
    jp pb_puts

pb_word:
    inc hl
    ld a,(hl)
    call pb_hex
    dec hl
    ld a,(hl)
    jp pb_hex

pb_puts:
    ld a,(hl)
    or a
    ret z
    ld (de),a
    inc hl
    inc de
    jp pb_puts

pb_hex_sp:
    call pb_hex
    ld a,' '
    ld (de),a
    inc de
    ret

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
t_n:     db "CODEPROBE N=",0
t_x:     db " X=",0
t_g:     db " G=",0
t_p:     db " P=",0
t_o:     db " O=",0
t_r:     db " R=",0
t_c:     db " C=",0
t_s:     db " S=",0
t_t:     db " T=",0
t_d:     db " D=",0
t_q:     db " Q=",0
t_f:     db " F=",0
t_k:     db "CODEPROBE 2 K=OK A=",0
t_m:     db " M=",0
t_ok:    db "OK",0
t_bad:   db "BAD",0
t_skip:  db "SKIP",0
dot_prg: db ".PRG",0
ok_tail: dw 800Dh,80FBh,0,0
         db 79,75,0

pb_bank:  db 0
blk:      db 0,0                ; os_release_mem list: block, 0
safe:     db 0
r_q0:     db 0
r_q1:     db 0
r_free0:  db 0
r_own:    dw 0
r_bown:   dw 0FFFFh
r_open:   db 0FFh
r_rd1:    db 0FFh
r_rd2:    db 0FFh
r_rd3:    db 0FFh
r_rd4:    db 0FFh
r_sp:     db 0FFh
r_c1:     db 'S'
r_c2:     db 'S'
r_xdef:   db 0
r_k_a:    db 0
r_k_m:    db 0
pb_text:  defs 160                ; longest stage-1 text: 125 bytes + alert tail

code_end:
    defs 8000h - code_end       ; pad: the tail is file offset #4000 = #8000

; ---------------------------------------------------------------- tail
; Runs only from the block the probe loaded and mapped at #8000.
tail_start:
tail_sum:                       ; HL = sum of t_data, A = last byte
    ld hl,0
    ld de,t_data
    ld b,0
ts_loop:
    ld a,(de)
    add a,l
    ld l,a
    ld a,h
    adc a,0
    ld h,a
    inc de
    djnz ts_loop
    ld a,(t_last)
    ret
tail_os:                        ; an OS call from quarter-2 code
    ld a,33
    call 003Bh                  ; os_ask_mem: comes back here only if the
    push af                     ; OS leaves (or restores) quarter 2
    call bios_getmem2
    ld b,a
    pop af
    ret
t_data:
    db 000h,001h,002h,003h,004h,005h,006h,007h,008h,009h,00Ah,00Bh,00Ch,00Dh,00Eh,00Fh
    db 010h,011h,012h,013h,014h,015h,016h,017h,018h,019h,01Ah,01Bh,01Ch,01Dh,01Eh,01Fh
    db 020h,021h,022h,023h,024h,025h,026h,027h,028h,029h,02Ah,02Bh,02Ch,02Dh,02Eh,02Fh
    db 030h,031h,032h,033h,034h,035h,036h,037h,038h,039h,03Ah,03Bh,03Ch,03Dh,03Eh,03Fh
    db 040h,041h,042h,043h,044h,045h,046h,047h,048h,049h,04Ah,04Bh,04Ch,04Dh,04Eh,04Fh
    db 050h,051h,052h,053h,054h,055h,056h,057h,058h,059h,05Ah,05Bh,05Ch,05Dh,05Eh,05Fh
    db 060h,061h,062h,063h,064h,065h,066h,067h,068h,069h,06Ah,06Bh,06Ch,06Dh,06Eh,06Fh
    db 070h,071h,072h,073h,074h,075h,076h,077h,078h,079h,07Ah,07Bh,07Ch,07Dh,07Eh,07Fh
    db 080h,081h,082h,083h,084h,085h,086h,087h,088h,089h,08Ah,08Bh,08Ch,08Dh,08Eh,08Fh
    db 090h,091h,092h,093h,094h,095h,096h,097h,098h,099h,09Ah,09Bh,09Ch,09Dh,09Eh,09Fh
    db 0A0h,0A1h,0A2h,0A3h,0A4h,0A5h,0A6h,0A7h,0A8h,0A9h,0AAh,0ABh,0ACh,0ADh,0AEh,0AFh
    db 0B0h,0B1h,0B2h,0B3h,0B4h,0B5h,0B6h,0B7h,0B8h,0B9h,0BAh,0BBh,0BCh,0BDh,0BEh,0BFh
    db 0C0h,0C1h,0C2h,0C3h,0C4h,0C5h,0C6h,0C7h,0C8h,0C9h,0CAh,0CBh,0CCh,0CDh,0CEh,0CFh
    db 0D0h,0D1h,0D2h,0D3h,0D4h,0D5h,0D6h,0D7h,0D8h,0D9h,0DAh,0DBh,0DCh,0DDh,0DEh,0DFh
    db 0E0h,0E1h,0E2h,0E3h,0E4h,0E5h,0E6h,0E7h,0E8h,0E9h,0EAh,0EBh,0ECh,0EDh,0EEh,0EFh
    db 0F0h,0F1h,0F2h,0F3h,0F4h,0F5h,0F6h,0F7h,0F8h,0F9h,0FAh,0FBh,0FCh,0FDh,0FEh,0FFh
t_last:
    db 0A5h
tail_end:
TAIL_LEN equ tail_end - tail_start
