"""M11: the simulator's instruction step as it was before the dispatch table
(tests/z80sim.py up to M10, verbatim). ``ReferenceCPU`` is used only by
tests/test_m11_harness.py, which runs programs on both and compares the whole
machine state after every instruction. Do not change it to match the new
code: it is the oracle.
"""
from __future__ import annotations

from z80sim import (CPU, FLAG_C, FLAG_H, FLAG_N, FLAG_PV, FLAG_S, FLAG_X, FLAG_Y, FLAG_Z,
                    SimError, SimRunaway)


class ReferenceCPU(CPU):
    def step(self) -> None:
        """Execute exactly one instruction; intercept OS calls at call sites."""
        op_addr = self.pc
        op = self._fetch8()
        self.steps += 1

        if op == 0x00:  # nop
            return
        if op == 0x76:
            raise SimRunaway(
                f"HALT at PC={op_addr:04X}h: program stopped without os_app_exit"
            )
        if op == 0xCB:
            self._cb(self._fetch8())
            return
        if op == 0xED:
            self._ed(self._fetch8())
            return
        if op == 0xDD:
            self._dd(self._fetch8())
            return
        if op == 0xFD:  # M7: only ld iy,nn (os_rename_file's new extension)
            sub = self._fetch8()
            if sub != 0x21:
                raise SimError(f"unsupported FD opcode FD {sub:02X}h near PC={self.pc:04X}h")
            self.iy = self._fetch16()
            return
        if op in (0x07, 0x0F, 0x17, 0x1F):  # rlca, rrca, rla, rra (M7): S, Z, PV kept
            a, carry = self.a, 1 if self.f & FLAG_C else 0
            if op == 0x07:
                out, a = a >> 7, ((a << 1) | (a >> 7)) & 0xFF
            elif op == 0x0F:
                out, a = a & 1, ((a >> 1) | ((a & 1) << 7)) & 0xFF
            elif op == 0x17:
                out, a = a >> 7, ((a << 1) | carry) & 0xFF
            else:
                out, a = a & 1, ((a >> 1) | (carry << 7)) & 0xFF
            self.a = a
            self.f = (self.f & (FLAG_S | FLAG_Z | FLAG_PV)) | (FLAG_C if out else 0) | (a & (FLAG_Y | FLAG_X))
            return
        if op == 0xE9:  # jp (hl)
            self.pc = self.hl
            return

        # --- 16-bit loads -------------------------------------------------
        if op in (0x01, 0x11, 0x21, 0x31):
            self._set_rr((op >> 4) & 3, self._fetch16())
            return
        if op == 0x02:
            self._wb(self.bc, self.a)
            return
        if op == 0x12:
            self._wb(self.de, self.a)
            return
        if op == 0x22:
            self._ww(self._fetch16(), self.hl)
            return
        if op == 0x32:
            self._wb(self._fetch16(), self.a)
            return
        if op == 0x0A:
            self.a = self._rb(self.bc)
            return
        if op == 0x1A:
            self.a = self._rb(self.de)
            return
        if op == 0x2A:
            self.set_hl(self._rw(self._fetch16()))
            return
        if op == 0x3A:
            self.a = self._rb(self._fetch16())
            return
        if op == 0x36:
            self._wb(self.hl, self._fetch8())
            return

        # --- 8-bit loads ---------------------------------------------------
        if op & 0xC7 == 0x06:  # ld r,n: 06 0E 16 1E 26 2E 3E (36 handled above)
            self._set_r((op >> 3) & 7, self._fetch8())
            return
        if 0x40 <= op <= 0x7F:  # ld r,r' — includes 70-75/77 ld (hl),r
            self._set_r((op >> 3) & 7, self._get_r(op & 7))
            return

        # --- 8-bit inc/dec --------------------------------------------------
        if op & 0xC7 == 0x04:
            idx = (op >> 3) & 7
            self._set_r(idx, self._inc8(self._get_r(idx)))
            return
        if op & 0xC7 == 0x05:
            idx = (op >> 3) & 7
            self._set_r(idx, self._dec8(self._get_r(idx)))
            return

        # --- 16-bit inc/dec and add hl,rr -----------------------------------
        if op & 0xCF == 0x03:
            idx = (op >> 4) & 3
            self._set_rr(idx, (self._get_rr(idx) + 1) & 0xFFFF)
            return
        if op & 0xCF == 0x0B:
            idx = (op >> 4) & 3
            self._set_rr(idx, (self._get_rr(idx) - 1) & 0xFFFF)
            return
        if op & 0xCF == 0x09:
            rr = self._get_rr((op >> 4) & 3)
            hl = self.hl
            total = hl + rr
            # ADD HL,rr touches only H, N, C (and the undocumented X/Y);
            # S, Z, PV are preserved.
            self.f = (
                (self.f & (FLAG_S | FLAG_Z | FLAG_PV))
                | (FLAG_H if (hl & 0x0FFF) + (rr & 0x0FFF) > 0x0FFF else 0)
                | (FLAG_C if total > 0xFFFF else 0)
                | ((total >> 8) & (FLAG_Y | FLAG_X))
            )
            self.set_hl(total & 0xFFFF)
            return

        # --- ALU -------------------------------------------------------------
        if 0x80 <= op <= 0xBF:  # alu a,r
            self._alu((op >> 3) & 7, self._get_r(op & 7))
            return
        if op & 0xC7 == 0xC6:  # alu a,n: C6 CE D6 DE E6 EE F6 FE
            self._alu((op >> 3) & 7, self._fetch8())
            return

        # --- jumps -----------------------------------------------------------
        if op == 0x10:  # djnz
            offset = self._fetch_rel()
            self.b = (self.b - 1) & 0xFF
            if self.b:
                self.pc = (self.pc + offset) & 0xFFFF
            return
        if op in (0x18, 0x20, 0x28, 0x30, 0x38):  # jr and jr cc
            offset = self._fetch_rel()
            if op == 0x18 or self._cond((op >> 3) & 3):
                self.pc = (self.pc + offset) & 0xFFFF
            return
        if op == 0xC3 or (op & 0xC7 == 0xC2):  # jp and jp cc
            target = self._fetch16()
            if op == 0xC3 or self._cond((op >> 3) & 7):
                self.pc = target
            return
        if op == 0xCD or (op & 0xC7 == 0xC4):  # call and call cc
            target = self._fetch16()
            if op == 0xCD or self._cond((op >> 3) & 7):
                self._call(target)
            return
        if op == 0xC9 or (op & 0xC7 == 0xC0):  # ret and ret cc
            if op == 0xC9 or self._cond((op >> 3) & 7):
                self.pc = self._pop16()
            return

        # --- stack -------------------------------------------------------------
        if op & 0xCF == 0xC5:  # push
            self._push16(self._get_rr_stack((op >> 4) & 3))
            return
        if op & 0xCF == 0xC1:  # pop
            idx = (op >> 4) & 3
            self._set_rr_stack(idx, self._pop16())
            return

        # --- misc ----------------------------------------------------------------
        if op == 0x2F:  # cpl
            self.a = (~self.a) & 0xFF
            self.f = (
                (self.f & (FLAG_S | FLAG_Z | FLAG_PV | FLAG_C))
                | FLAG_H
                | FLAG_N
                | (self.a & (FLAG_Y | FLAG_X))
            )
            return
        if op == 0x37:  # scf
            self.f = (
                (self.f & (FLAG_S | FLAG_Z | FLAG_PV))
                | FLAG_C
                | (self.a & (FLAG_Y | FLAG_X))
            )
            return
        if op == 0x3F:  # ccf
            carry = self.f & FLAG_C
            self.f = (
                (self.f & (FLAG_S | FLAG_Z | FLAG_PV))
                | (FLAG_H if carry else 0)
                | (0 if carry else FLAG_C)
                | (self.a & (FLAG_Y | FLAG_X))
            )
            return
        if op == 0xEB:  # ex de,hl
            self.d, self.h = self.h, self.d
            self.e, self.l = self.l, self.e
            return
        if op in (0xF3, 0xFB):  # di / ei: the model has no interrupts
            return

        raise SimError(f"unsupported opcode {op:02X}h at PC={op_addr:04X}h")
