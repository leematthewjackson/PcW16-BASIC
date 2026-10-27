; ============================================================================
; READDIAG — XAnne diagnostic for os_read_file return values (M4 repair)
; ============================================================================
; NOT compiler output and NOT part of the runtime: a hand-written, read-only
; test tool. It exists because ROSAN283 states the #A1 result as
; "Premature EoF (BDE = amount NOT loaded, CHL = filesize)" — the same words
; as for os_copy_file, which has no CHL input — and the Ranger document that
; defines r_read_file is not in this repository. The owner's XAnne run of
; ROUNDTRP.PRG (M4) got #A1 with registers that did not fit that reading.
; This program shows the raw values so the contract can be recorded.
;
; Safety: it NEVER writes, creates, deletes or renames a file. It only opens
; for READ (B=0) two files in \PCW\FOLDER01 and closes them again:
;   PBRTRIP.TXT  (5 bytes "Short", left by ROUNDTRP.PRG)
;   PBEMPTY.TXT  (0 bytes, created by the owner on the host)
; A missing file is reported ("open failed A=02") and the program continues.
;
; For each test Dn it opens the file, performs the listed os_read_file
; requests (the buffer first filled with #EE so bytes the OS writes are
; visible), closes, and shows three alerts:
;   "Dn results: <per read: NC, or the A code>"
;   "Dn last: Cy=x A=xx BDE=xxxxxx CHL=xxxxxx"   (registers after the last read)
;   "Dn buf: xx xx xx xx xx xx xx xx"            (first 8 buffer bytes)
; Tests:
;   D1 PBRTRIP.TXT  read 64             (what M4 FILELOAD does, capacity 64)
;   D2 PBRTRIP.TXT  read 5, read 1      (exact size, then one more)
;   D3 PBRTRIP.TXT  read 1 six times    (the repaired FILELOAD method)
;   D4 PBRTRIP.TXT  read 3, read 64     (EoF part-way, after a first read)
;   D5 PBEMPTY.TXT  read 1              (empty file)
; Each read goes to buffer + (bytes requested so far); the buffer is 600
; bytes so a read may fill "the remainder of the last 512-/510-byte block"
; (ROSAN283 os_read_file) without leaving it.
;
; OS calls (ROSAN283, numbers from OSCALLS.INC.txt counted from 1, as in
; runtime/runtime.z80.asm): os_set_device 127, os_set_cwd 135,
; os_open_file 144, os_close_file 145, os_read_file 147, os_alert 76,
; os_app_exit 23; bios_getmem1 = call #0CB.
;
; Build:  pasmo --bin xanne/readdiag.asm artifacts/m4-fix/readdiag.prg
; ============================================================================

    org 4000h
    defs 100h

start:
    ld b,1
    ld a,127
    call 003Bh                  ; os_set_device: floppy
    ld hl,dg_path
    ld de,2100h
    call dg_copyz
    ld hl,2100h
    ld a,135
    call 003Bh                  ; os_set_cwd \PCW\FOLDER01
    jp nc,dg_cwd_ok
    ld (dg_a),a
    ld hl,dg_t_cwdfail
    call dg_text_alert_a
    jp dg_exit
dg_cwd_ok:
    ld hl,dg_tests
dg_test_loop:
    ld a,(hl)
    or a
    jp z,dg_exit
    ld (dg_tag),a
    inc hl
    ld (dg_test),hl             ; -> name pointer word, then read sizes
    call dg_run_test
    ld hl,(dg_next)
    jp dg_test_loop

dg_exit:
    ld a,23
    call 003Bh                  ; os_app_exit (closes any open file, doc)
    ret

; ----------------------------------------------------------------------------
; dg_run_test — one Dn test. (dg_test) points at: dw name, then read sizes
; as words, terminated by dw 0. Sets dg_next to the following table entry.
; ----------------------------------------------------------------------------
dg_run_test:
    ld hl,(dg_test)
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld (dg_sizes),hl
    ex de,hl                    ; HL = name ("NAME",0,".EXT",0)
    ld de,2100h
    call dg_copyz
    ld de,2120h
    call dg_copyz
    ; fill the buffer with #EE
    ld hl,dg_buf
    ld de,dg_buf+1
    ld bc,599
    ld a,0EEh
    ld (hl),a
    ldir
    ; skip to the table entry after this test's size list
    ld hl,(dg_sizes)
dg_skip:
    ld a,(hl)
    inc hl
    or (hl)
    inc hl
    jp nz,dg_skip
    ld (dg_next),hl
    ; results line "Dn results:"
    ld de,dg_line
    call dg_tag_out
    ld hl,dg_t_results
    call dg_puts
    ex de,hl
    ld (dg_lpos),hl
    ex de,hl
    ld hl,2100h
    ld de,2120h
    ld b,0
    ld a,144
    call 003Bh                  ; os_open_file for READ
    jp nc,dg_opened
    ld (dg_a),a
    ld de,dg_line
    call dg_tag_out
    ld hl,dg_t_openfail
    call dg_puts
    ld a,(dg_a)
    call dg_hex
    call dg_alert_line
    ret
dg_opened:
    ld hl,0
    ld (dg_offset),hl
dg_read_loop:
    ld hl,(dg_sizes)
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld (dg_sizes),hl
    ex de,hl
    ld a,l
    or h
    jp z,dg_reads_done
    ld (dg_req),hl
    call 0CBh
    ld c,a
    ld hl,(dg_offset)
    ld de,dg_buf
    add hl,de
    ld de,(dg_req)
    ld b,0
    ld a,147
    call 003Bh                  ; os_read_file CHL = buffer+offset, BDE = request
    push hl
    push de
    push bc
    push af
    pop hl
    ld (dg_af),hl               ; H = A, L = F
    pop hl
    ld (dg_bc),hl
    pop hl
    ld (dg_de),hl
    pop hl
    ld (dg_hl),hl
    ; offset += request
    ld hl,(dg_offset)
    ld de,(dg_req)
    add hl,de
    ld (dg_offset),hl
    ; append " NC" or " xx" (A) to the results line
    ld de,(dg_lpos)
    ld a,32
    ld (de),a
    inc de
    ld a,(dg_af)
    and 1
    jp nz,dg_res_c
    ld a,78
    ld (de),a
    inc de
    ld a,67
    ld (de),a
    inc de
    jp dg_res_done
dg_res_c:
    ld a,(dg_af+1)
    call dg_hex
dg_res_done:
    ex de,hl
    ld (dg_lpos),hl
    ex de,hl
    jp dg_read_loop
dg_reads_done:
    ld b,0
    ld a,145
    call 003Bh                  ; os_close_file READ
    ld de,(dg_lpos)
    call dg_alert_line          ; "Dn results: ..."
    ; "Dn last: Cy=x A=xx BDE=xxxxxx CHL=xxxxxx"
    ld de,dg_line
    call dg_tag_out
    ld hl,dg_t_last
    call dg_puts
    ld a,(dg_af)
    and 1
    add a,48
    ld (de),a
    inc de
    ld hl,dg_t_a
    call dg_puts
    ld a,(dg_af+1)
    call dg_hex
    ld hl,dg_t_bde
    call dg_puts
    ld a,(dg_bc+1)              ; B
    call dg_hex
    ld a,(dg_de+1)              ; D
    call dg_hex
    ld a,(dg_de)                ; E
    call dg_hex
    ld hl,dg_t_chl
    call dg_puts
    ld a,(dg_bc)                ; C
    call dg_hex
    ld a,(dg_hl+1)              ; H
    call dg_hex
    ld a,(dg_hl)                ; L
    call dg_hex
    call dg_alert_line
    ; "Dn buf: b0 b1 ... b7"
    ld de,dg_line
    call dg_tag_out
    ld hl,dg_t_buf
    call dg_puts
    ld hl,dg_buf
    ld b,8
dg_buf_loop:
    ld a,32
    ld (de),a
    inc de
    ld a,(hl)
    call dg_hex
    inc hl
    djnz dg_buf_loop
    call dg_alert_line
    ret

; dg_tag_out — "Dn" at DE.
dg_tag_out:
    ld a,68
    ld (de),a
    inc de
    ld a,(dg_tag)
    ld (de),a
    inc de
    ret

; dg_puts — copy a NUL-terminated string HL to DE (no NUL); DE advanced.
dg_puts:
    ld a,(hl)
    or a
    ret z
    ld (de),a
    inc hl
    inc de
    jp dg_puts

; dg_copyz — copy a NUL-terminated string HL to DE including the NUL;
; HL ends one past the NUL.
dg_copyz:
    ld a,(hl)
    ld (de),a
    inc hl
    inc de
    or a
    jp nz,dg_copyz
    ret

; dg_hex — A as two upper-case hex digits at DE; DE advanced. Keeps HL, B.
dg_hex:
    push af
    srl a
    srl a
    srl a
    srl a
    call dg_nibble
    pop af
    and 15
    jp dg_nibble
dg_nibble:
    add a,48
    cp 58
    jp c,dg_nibble_out
    add a,7
dg_nibble_out:
    ld (de),a
    inc de
    ret

; dg_text_alert_a — alert "<text HL>xx" with xx = (dg_a) in hex.
dg_text_alert_a:
    ld de,dg_line
    call dg_puts
    ld a,(dg_a)
    call dg_hex
    jp dg_alert_line

; dg_alert_line — finish the text in dg_line (DE = end) as an os_alert
; definition (ROSAN283 'os_alert': text NUL, extra NUL, button count, 4 key
; words, button text NUL; POC-proven layout) and show it.
dg_alert_line:
    xor a
    ld (de),a
    inc de
    ld (de),a
    inc de
    ld a,1
    ld (de),a
    inc de
    ld hl,dg_keys
    ld bc,11
    ldir
    ld hl,dg_line
    ex de,hl
    or a
    sbc hl,de
    ex de,hl                    ; DE = length
    ld hl,dg_line
    call 0CBh
    ld c,a
    ld a,76
    call 003Bh                  ; os_alert
    ret

; ---------------------------------------------------------------- data
dg_tests:
    db "1"
    dw dg_n_rtrip
    dw 64,0
    db "2"
    dw dg_n_rtrip
    dw 5,1,0
    db "3"
    dw dg_n_rtrip
    dw 1,1,1,1,1,1,0
    db "4"
    dw dg_n_rtrip
    dw 3,64,0
    db "5"
    dw dg_n_empty
    dw 1,0
    db 0

dg_n_rtrip:
    db "PBRTRIP",0,".TXT",0
dg_n_empty:
    db "PBEMPTY",0,".TXT",0
dg_path:
    db 92,"PCW",92,"FOLDER01",0
dg_t_results:
    db " results:",0
dg_t_openfail:
    db " open failed A=",0
dg_t_cwdfail:
    db "Folder ",92,"PCW",92,"FOLDER01 not set, A=",0
dg_t_last:
    db " last: Cy=",0
dg_t_a:
    db " A=",0
dg_t_bde:
    db " BDE=",0
dg_t_chl:
    db " CHL=",0
dg_t_buf:
    db " buf:",0
dg_keys:
    dw 800Dh,80FBh,0,0
    db 79,75,0

dg_tag:
    defs 1
dg_a:
    defs 1
dg_test:
    defs 2
dg_next:
    defs 2
dg_sizes:
    defs 2
dg_req:
    defs 2
dg_offset:
    defs 2
dg_lpos:
    defs 2
dg_af:
    defs 2
dg_bc:
    defs 2
dg_de:
    defs 2
dg_hl:
    defs 2
dg_line:
    defs 96
dg_buf:
    defs 600
