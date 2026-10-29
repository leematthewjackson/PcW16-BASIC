; ============================================================================
; M15NATIVE — the hand-written routines of the M15a probe M15PRB
; ============================================================================
; NOT compiler output and NOT part of the runtime. xanne/m15prb_build.py
; compiles xanne/m15prb.pbas, puts this file after its first jump, replaces
; the body of each placeholder SUB NatX with "jp nat_x", and sends om_exit
; to nat_omexit. The routines read and write the BASIC program's globals
; (var_*) and its canvas origin (cgcanvas: dw screen x, screen y, ...).
;
; In (BASIC globals): NF font/number, NS style, NA alignment, NM mode, NK
; 1/1800" per pixel, NX NY canvas position, NSLOT NSZ NID typo slot / size /
; font ID, CW CH clip size, T$ text (NUL-terminated).
; Out: NC NE NW NH ND, NN count, FID/FST/FFM 1..4 and N1$..N4$ (font list).
;
; Rosanne calls (ROSAN283; docs/rosanne-research/reference/api-catalogue-
; official.md): 42 os_get_byte_24bit, 81 os_dialog_string, 82
; os_dialog_string_width, 83 os_typo_init, 84 os_typo_getlist, 85
; os_typo_select, 87 os_typo_def, 88 os_typo_clr, 90 os_typo_info, 91
; os_typo_charwidth, 93 os_typo_charscreen, 111/112 os_mouse_off/on, 119
; os_scr_getwindow. Calls 81-91 are the ones the runtime already makes (DRAW
; TEXT, TEXTWIDTH, PAGE); 93 and 119 are new. (r3: the BIOS font calls are
; removed, below.)
; r2 (after T4 corrupted XAnne's whole screen; docs/M15A-PROBE.md "T4"): the
; clipping window is only read (os_scr_window 118 is not called), only slot 0
; at 10 or 12 points is defined (PAGE's own sequence), and nat_typo_draw
; draws only after a successful definition, inside the canvas, and stops at
; the first non-zero code.
; ============================================================================

nat_mouse_off:
    ld a,111
    call 003Bh
    ret
nat_mouse_on:
    ld a,112
    call 003Bh
    ret

; nat_canvas_xy — HL = NX + canvas x, DE = NY + canvas y (screen pixels)
nat_canvas_xy:
    ld hl,(var_NY)
    ld de,(cgcanvas+2)
    add hl,de
    ex de,hl
    ld hl,(var_NX)
    push de
    ld de,(cgcanvas)
    add hl,de
    pop de
    ret

; nat_flag — HL = 1 if carry, else 0 (flags from the call before)
nat_flag:
    ld hl,0
    ret nc
    inc hl
    ret

; ---------------------------------------------------------------- dialog fonts
; os_dialog_string (81) with font NF, alignment NA, style NS, mode 0 at NX,
; NY: NC = its carry; then os_dialog_string_width (82) of the same block:
; NW = HL, NE = its carry.
nat_dlg:
    ld a,(var_NF)
    ld (nat_blk),a
    ld a,(var_NA)
    ld (nat_blk+1),a
    ld a,(var_NS)
    ld (nat_blk+2),a
    xor a
    ld (nat_blk+3),a
    call nat_canvas_xy
    ld (nat_blk+4),hl
    ld (nat_blk+6),de
    ld hl,var_T_S
    ld de,nat_blk+8
nat_dlg_copy:
    ld a,(hl)
    ld (de),a
    inc hl
    inc de
    or a
    jp nz,nat_dlg_copy
    call nat_mouse_off
    call 0CBh
    ld c,a
    ld hl,nat_blk
    ld a,81
    call 003Bh                  ; os_dialog_string
    call nat_flag
    ld (var_NC),hl
    call nat_mouse_on
    call 0CBh
    ld c,a
    ld hl,nat_blk
    ld a,82
    call 003Bh                  ; os_dialog_string_width: HL = width
    ld (var_NW),hl
    call nat_flag
    ld (var_NE),hl
    ret

; ---------------------------------------------------------------- BIOS fonts
; r3: removed. bios_setfont 0 + bios_string crashed Rosanne in XAnne (owner
; r2 retest; RAM dump: the call block was correct, bios_getfont had returned
; 7, the dialog font; docs/M15A-PROBE.md "Option 4").

; ---------------------------------------------------------------- typo fonts
; nat_typo_list — os_typo_init (83) once (NC = its carry), then
; os_typo_getlist (84): NN = entries; the first four into FIDn, FSTn, FFMn
; and Nn$ (name, at most 33 characters).
nat_typo_list:
    ld hl,0
    ld (var_NC),hl
    ld a,(nat_tinit)
    or a
    jp nz,nat_tl_list
    ld a,83
    call 003Bh                  ; os_typo_init
    call nat_flag
    ld (var_NC),hl
    ld a,h
    or l
    ret nz
    ld a,1
    ld (nat_tinit),a
nat_tl_list:
    ld a,84
    call 003Bh                  ; os_typo_getlist: B entries at CHL
    ld a,b
    ld (var_NN),a
    xor a
    ld (var_NN+1),a
    ld a,b
    cp 5
    jp c,nat_tl_n
    ld b,4
nat_tl_n:
    ld a,b
    or a
    ret z
    ld (nat_k),a
    ld de,nat_ent_tab
    ld (nat_ep),de
nat_tl_entry:
    call nat_byte                ; ID low
    ld (nat_t),a
    call nat_byte                ; ID high
    ld (nat_t+1),a
    call nat_next                ; DE = FIDn
    push hl
    ld hl,(nat_t)
    ex de,hl
    ld (hl),e
    inc hl
    ld (hl),d
    pop hl
    call nat_byte                ; styles
    call nat_next_byte           ; FSTn = A
    call nat_byte                ; RTF family
    call nat_next_byte           ; FFMn = A
    call nat_next                ; DE = Nn$: 33 bytes, 0-terminated and padded
    ld a,33
nat_tl_name:
    push af
    call nat_byte
    ld (de),a
    inc de
    pop af
    dec a
    jp nz,nat_tl_name
    xor a
    ld (de),a
    ld a,(nat_k)
    dec a
    ld (nat_k),a
    jp nz,nat_tl_entry
    ret

; nat_next — DE = the next word of nat_ent_tab (CHL kept)
nat_next:
    push hl
    ld hl,(nat_ep)
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld (nat_ep),hl
    pop hl
    ret

; nat_next_byte — the next INTEGER of nat_ent_tab = A (CHL kept)
nat_next_byte:
    push af
    call nat_next
    pop af
    ld (de),a
    inc de
    xor a
    ld (de),a
    ret

; nat_byte — A = the byte at CHL, CHL wound on (os_get_byte_24bit, B = 1)
nat_byte:
    push de
    ld b,1
    ld a,42
    call 003Bh
    ld a,e
    pop de
    ret

; nat_typo_def — slot NSLOT: select (NC = A), clear, install font NID at NSZ
; points, all styles (NE = A); if that worked, os_typo_info: NW pitch, NH
; ascender, ND descender (1/1800").
nat_typo_def:
    xor a
    ld (nat_defok),a
    ld hl,97                    ; r2 guard: slot 0 only
    ld (var_NE),hl
    ld a,(var_NSLOT+1)
    or a
    ret nz
    ld a,(var_NSLOT)
    or a
    ret nz
    ld hl,96                    ; r2 guard: 10 or 12 points only
    ld (var_NE),hl
    ld a,(var_NSZ+1)
    or a
    ret nz
    ld a,(var_NSZ)
    cp 10
    jp z,nat_tdf_size
    cp 12
    ret nz
nat_tdf_size:
    ld e,0
    ld a,85
    call 003Bh                  ; os_typo_select
    ld l,a
    ld h,0
    ld (var_NC),hl
    ld a,88
    call 003Bh                  ; os_typo_clr
    ld hl,(var_NID)
    ld d,0FFh
    ld a,(var_NSZ)
    ld b,a
    ld a,87
    call 003Bh                  ; os_typo_def
    ld l,a
    ld h,0
    ld (var_NE),hl
    ld hl,0
    ld (var_NW),hl
    ld (var_NH),hl
    ld (var_ND),hl
    or a
    ret nz
    ld a,1
    ld (nat_defok),a
    ld a,90
    call 003Bh                  ; os_typo_info: HL -> pitch, ascender, descender
    or a
    ret nz
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld (var_NW),de
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld (var_NH),de
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld (var_ND),de
    ret

; nat_typo_draw — T$ from slot NSLOT at NX, NY, style NS, mode NM: for each
; character os_typo_charwidth (91) then os_typo_charscreen (93), the next x
; = x + width / NK (rounded). NC = os_typo_select's A, NE = the first
; non-zero A of 91 or 93 (0: none), NW = the advance in pixels.
nat_typo_draw:
    ld hl,0
    ld (var_NW),hl
    ld hl,99                    ; r2 guard: only after a successful nat_typo_def
    ld (var_NE),hl
    ld (var_NC),hl
    ld a,(nat_defok)
    or a
    ret z
    ld hl,98                    ; r2 guard: start inside the canvas, 0 <= NX <= 500
    ld (var_NE),hl              ; and 20 <= NY <= 170 (room above and below)
    ld hl,(var_NX)
    ld a,h
    and 80h
    ret nz                      ; negative
    ld de,501
    or a
    sbc hl,de
    ret nc                      ; over 500
    ld de,(var_NY)
    ld a,d
    or a
    ret nz
    ld a,e
    cp 20
    ret c
    cp 171
    ret nc
    push ix
    ld e,0
    ld a,85
    call 003Bh                  ; os_typo_select slot 0
    ld l,a
    ld h,0
    ld (var_NC),hl
    ld hl,0
    ld (var_NE),hl
    or a
    jp nz,nat_td_out            ; no font in the slot: nothing drawn
    call nat_canvas_xy
    ld (nat_x),hl
    ld (nat_x0),hl
    ld (nat_y),de
    ld hl,var_T_S
    ld (nat_p),hl
    ld a,50
    ld (nat_left),a             ; r2 guard: at most 50 characters
    call nat_mouse_off
nat_td_char:
    ld a,(nat_left)
    or a
    jp z,nat_td_end
    dec a
    ld (nat_left),a
    ld hl,(nat_x)               ; r2 guard: stop before the canvas's right edge
    ld de,(cgcanvas)
    or a
    sbc hl,de
    ld de,530
    or a
    sbc hl,de
    jp nc,nat_td_end
    ld hl,(nat_p)
    ld a,(hl)
    or a
    jp z,nat_td_end
    inc hl
    ld (nat_p),hl
    ld (nat_ch),a
    ld c,a
    ld b,0
    ld a,(var_NS)
    and 1                       ; 91 obeys bold only (bit 0)
    ld d,a
    ld a,91
    call 003Bh                  ; os_typo_charwidth: DE = width (1/1800")
    or a
    jp nz,nat_td_stop           ; r2: stop at the first refusal
    ld hl,1800                  ; r2 guard: a width over 1" is not plausible at 10 pt
    or a
    sbc hl,de
    ld a,95
    jp c,nat_td_stop
    ld (nat_w),de
    ld a,(nat_ch)
    ld c,a
    ld b,0
    ld a,(var_NM)
    ld h,a
    ld a,(var_NS)
    ld l,a
    push hl
    pop ix                      ; IX = mode * 256 + style
    ld de,(nat_x)
    ld hl,(nat_y)
    ld a,93
    call 003Bh                  ; os_typo_charscreen
    or a
    jp nz,nat_td_stop
    ld hl,(nat_w)               ; x += (width + NK / 2) / NK
    ld a,(var_NK)
    or a
    jp z,nat_td_char
    ld c,a
    srl a
    ld e,a
    ld d,0
    add hl,de
    ld de,0
nat_td_div:
    ld a,l
    sub c
    ld l,a
    ld a,h
    sbc a,0
    ld h,a
    jp c,nat_td_q
    inc de
    jp nat_td_div
nat_td_q:
    ld hl,(nat_x)
    add hl,de
    ld (nat_x),hl
    jp nat_td_char
nat_td_stop:
    ld l,a
    ld h,0
    ld (var_NE),hl
nat_td_end:
    call nat_mouse_on
    ld hl,(nat_x)
    ld de,(nat_x0)
    or a
    sbc hl,de
    ld (var_NW),hl
nat_td_out:
    pop ix
    ret

; ---------------------------------------------------------------- clipping
; nat_clip_get — the screen clipping window (os_scr_getwindow 119, read
; only: CHL -> x, y, w, h): CX, CY, CW, CH.
nat_clip_get:
    ld a,119
    call 003Bh
    ld de,var_CX
    call nat_word
    ld de,var_CY
    call nat_word
    ld de,var_CW
    call nat_word
    ld de,var_CH
nat_word:                       ; (DE) = the word at CHL, wound on
    call nat_byte
    ld (de),a
    inc de
    call nat_byte
    ld (de),a
    ret

; ---------------------------------------------------------------- om_exit
; Tasks > Stop sends om_exit (ROSAN283: "close all ram and os_app_exit").
; The runtime ends at once; the probe first runs SUB OnExit (a file write
; after the chosen delay), to show whether there is time for one.
nat_omexit:
    call sub_ONEXIT
    jp rt_exit

; ---------------------------------------------------------------- events (r4)
; nat_msg — from the event loop, A = an OS message's id (record +2): counted
; (ids 1..5 each, anything else as 0); A and the flags it is compared with
; are kept.
nat_msg:
    push af
    push hl
    push de
    cp 6
    jp c,nat_msg_id
    xor a
nat_msg_id:
    ld e,a
    ld d,0
    ld hl,nat_msgcnt
    add hl,de
    inc (hl)
    jp nz,nat_msg_end
    dec (hl)                    ; stays at 255
nat_msg_end:
    pop de
    pop hl
    pop af
    ret

; nat_ddm_other — a menu choice (event bit 1) that is none of the program's
; menu items, which the runtime drops. Counted, its title and entry kept
; (record +2, +3, +4: IX is still the event record); r5: title 0, entry 0
; is an exit request when StopExit is on; anything else is dropped, as the
; runtime does.
nat_ddm_other:
    ld a,(ix+2)
    ld (nat_dt),a
    ld a,(ix+3)
    ld (nat_de),a
    ld a,(ix+4)
    ld (nat_ds),a
    ld hl,nat_dn
    inc (hl)
    jp nz,nat_ddm_n
    dec (hl)
nat_ddm_n:
    ld a,(var_STOPEXIT)         ; r5: title 0 (the Tasks menu), entry 0 as an
    or a                        ; exit request, when the switch is on
    jp z,nat_ddm_pass
    ld a,(nat_dt)
    ld hl,nat_de
    or (hl)
    jp nz,nat_ddm_pass
    ld hl,1
    ld (var_EXITBY),hl          ; the log says which request it was
    jp nat_omexit
nat_ddm_pass:
    jp rt_gui_loop              ; dropped, as the runtime does (r4's switch to
                                ; pass it to os_process_event had no effect)

; nat_events — the counts into M0..M5, DN, DT, DEN
nat_events:
    ld hl,nat_msgcnt
    ld de,var_M0
    call nat_ev_byte
    ld de,var_M1
    call nat_ev_byte
    ld de,var_M2
    call nat_ev_byte
    ld de,var_M3
    call nat_ev_byte
    ld de,var_M4
    call nat_ev_byte
    ld de,var_M5
    call nat_ev_byte
    ld hl,nat_dn
    ld de,var_DN
    call nat_ev_byte
    ld hl,nat_dt
    ld de,var_DT
    call nat_ev_byte
    ld hl,nat_de
    ld de,var_DEN
    call nat_ev_byte
    ld hl,nat_ds
    ld de,var_DS
nat_ev_byte:                    ; (DE) word = (HL) byte; HL on by one
    ld a,(hl)
    ld (de),a
    inc de
    xor a
    ld (de),a
    inc hl
    ret

; nat_tasks — E$ = the first 110 bytes of the menu bar definition the runtime
; built at #2400 of block #80 (rt_menu_init: the Tasks menu from
; os_ddm_get_tasks, then the program's titles): printable ASCII as it is,
; any other byte as '.'.
nat_tasks:
    ld hl,2400h
    ld de,var_E_S
    ld b,110
nat_tk_byte:
    ld a,(hl)
    cp 32
    jp c,nat_tk_dot
    cp 127
    jp c,nat_tk_put
nat_tk_dot:
    ld a,'.'
nat_tk_put:
    ld (de),a
    inc hl
    inc de
    djnz nat_tk_byte
    xor a
    ld (de),a
    ret

; ---------------------------------------------------------------- data
nat_ent_tab:
    dw var_FID1,var_FST1,var_FFM1,var_N1_S
    dw var_FID2,var_FST2,var_FFM2,var_N2_S
    dw var_FID3,var_FST3,var_FFM3,var_N3_S
    dw var_FID4,var_FST4,var_FFM4,var_N4_S
nat_tinit: db 0
nat_oldfont: db 0
nat_k: db 0
nat_ep: dw 0
nat_ch: db 0
nat_t: dw 0
nat_x: dw 0
nat_x0: dw 0
nat_y: dw 0
nat_w: dw 0
nat_p: dw 0
nat_defok: db 0
nat_msgcnt: db 0,0,0,0,0,0
nat_dn: db 0
nat_dt: db 0
nat_de: db 0
nat_ds: db 0
nat_left: db 0
nat_blk: defs 96
