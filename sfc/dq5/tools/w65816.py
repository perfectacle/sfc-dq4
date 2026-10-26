"""작은 65C816 해석기. 롬의 루틴을 WRAM 사본 위에서 그대로 돌려 결과를 얻는 데 쓴다(LoROM, 네이티브 모드만).

하드웨어는 거의 흉내 내지 않는다. PPU·DMA 레지스터 쓰기는 `io_writes` 에 남기고, 읽기는 곱셈·나눗셈 결과
($4214~$4217)만 계산하고 나머지는 0 이다. `ppu=True` 면 VRAM·CGRAM·OAM 에 들어가는 CPU 쓰기와 일반 DMA($420B, A→B)만
따라 해 `vram`·`cgram`·`oam` 에 남긴다(HDMA·래스터 효과는 없음). 특정 주소에 닿으면 파이썬 함수를 부르는 `hooks` 로 프레임 기다림 같은
곳을 바꿔 끼운다. 쓰는 곳: sfc/dq5/tools/dq5fxvm.py(전투 연출 스크립트를 롬 코드로 돌림).
"""
from __future__ import annotations


class Stop(Exception):
    pass


class Cpu:
    def __init__(self, rom: bytes, wram: bytes | bytearray, ppu: bool = False):
        self.rom = rom
        self.ppu = ppu
        self.vram = bytearray(0x10000)
        self.cgram = bytearray(0x200)
        self.oam = bytearray(0x220)
        self.reg = bytearray(0x10000)   # 마지막으로 쓴 하드웨어 레지스터 값
        self.vaddr = self.cgaddr = self.oamaddr = 0
        self._cglatch = None
        self.scroll, self._ofs_prev, self._ofs_turn = {}, {}, {}
        self.wram = bytearray(wram)
        self.a = self.x = self.y = 0
        self.s = 0x1FF
        self.d = 0
        self.dbr = self.pbr = 0
        self.pc = 0
        self.p = 0x30  # M·X = 8비트
        self.hooks = {}          # 24비트 PC → fn(cpu). fn 이 True 를 돌려주면 그 명령을 실행하지 않는다(fn 이 PC 를 옮김)
        self.io_writes = []      # (주소, 값)
        self.wram_reads = None   # set 이면 WRAM 읽기 오프셋을 모은다
        self.wram_written = None
        self.steps = 0
        self._mul = [0, 0]
        self._div = [0, 0, 0]
        self._res = [0, 0, 0, 0]

    # --- 메모리 ---
    def _rom_off(self, bank, addr):
        return ((bank & 0x7F) << 15) | (addr & 0x7FFF)

    def read(self, a):
        bank, addr = (a >> 16) & 0xFF, a & 0xFFFF
        if bank in (0x7E, 0x7F):
            off = ((bank - 0x7E) << 16) | addr
            if self.wram_reads is not None and off not in self.wram_written:
                self.wram_reads.add(off)
            return self.wram[off]
        lo = (bank & 0x7F) < 0x40
        if addr < 0x2000 and lo:
            if self.wram_reads is not None and addr not in self.wram_written:
                self.wram_reads.add(addr)
            return self.wram[addr]
        if addr >= 0x8000:
            return self.rom[self._rom_off(bank, addr) % len(self.rom)]
        if lo and 0x4214 <= addr <= 0x4217:
            return self._res[addr - 0x4214]
        return 0

    def write(self, a, v):
        v &= 0xFF
        bank, addr = (a >> 16) & 0xFF, a & 0xFFFF
        if bank in (0x7E, 0x7F):
            off = ((bank - 0x7E) << 16) | addr
        elif addr < 0x2000 and (bank & 0x7F) < 0x40:
            off = addr
        else:
            if (bank & 0x7F) < 0x40 and 0x2100 <= addr < 0x4400:
                self.io_writes.append((addr, v))
                self.reg[addr] = v
                if self.ppu:
                    self._ppu_write(addr, v)
                if addr == 0x4202:
                    self._mul[0] = v
                elif addr == 0x4203:
                    r = self._mul[0] * v
                    self._res = [0, 0, r & 0xFF, r >> 8]
                elif addr in (0x4204, 0x4205):
                    self._div[addr - 0x4204] = v
                elif addr == 0x4206:
                    n = self._div[0] | self._div[1] << 8
                    q, m = (n // v, n % v) if v else (0xFFFF, n)
                    self._res = [q & 0xFF, q >> 8, m & 0xFF, m >> 8]
            return
        if self.wram_written is not None:
            self.wram_written.add(off)
        self.wram[off] = v

    # --- PPU 쓰기와 DMA(ppu=True) ---
    def _vinc(self, high):
        vm = self.reg[0x2115]
        if bool(vm & 0x80) == high:
            self.vaddr = (self.vaddr + (1, 32, 128, 128)[vm & 3]) & 0x7FFF

    def _ppu_write(self, addr, v):
        if addr == 0x2116:
            self.vaddr = (self.vaddr & 0x7F00) | v
        elif addr == 0x2117:
            self.vaddr = (self.vaddr & 0xFF) | (v & 0x7F) << 8
        elif addr == 0x2118:
            self.vram[self.vaddr * 2] = v
            self._vinc(False)
        elif addr == 0x2119:
            self.vram[self.vaddr * 2 + 1] = v
            self._vinc(True)
        elif addr == 0x2121:
            self.cgaddr = v * 2
            self._cglatch = None
        elif addr == 0x2122:
            if self._cglatch is None:
                self._cglatch = v
            else:
                self.cgram[self.cgaddr & 0x1FE] = self._cglatch
                self.cgram[(self.cgaddr & 0x1FE) + 1] = v
                self.cgaddr = (self.cgaddr + 2) & 0x1FF
                self._cglatch = None
        elif addr == 0x2102:
            self.oamaddr = (self.oamaddr & 0x200) | v << 1
        elif addr == 0x2103:
            self.oamaddr = (self.oamaddr & 0x1FE) | (v & 1) << 9
        elif addr == 0x2104:
            self.oam[self.oamaddr % 0x220] = v
            self.oamaddr = (self.oamaddr + 1) % 0x220
        elif 0x210D <= addr <= 0x2114:
            # BGnHOFS/VOFS 는 두 번 써서 10비트(앞 값이 낮은 바이트)
            lo = self._ofs_prev.get(addr, 0)
            self.scroll[addr] = (lo | (v & 3) << 8) if self._ofs_turn.get(addr) else v
            self._ofs_turn[addr] = not self._ofs_turn.get(addr, False)
            self._ofs_prev[addr] = v
        elif addr == 0x420B:
            for ch in range(8):
                if v & (1 << ch):
                    self._dma(ch)

    def _dma(self, ch):
        b = 0x4300 + ch * 16
        ctl, bb = self.reg[b], self.reg[b + 1]
        if ctl & 0x80:
            return  # B→A 는 쓰지 않음
        src = self.reg[b + 2] | self.reg[b + 3] << 8
        bank = self.reg[b + 4]
        n = self.reg[b + 5] | self.reg[b + 6] << 8 or 0x10000
        pattern = ((0,), (0, 1), (0, 0), (0, 0, 1, 1), (0, 1, 2, 3), (0, 1, 0, 1), (0, 0), (0, 0, 1, 1))[ctl & 7]
        step = 0 if ctl & 0x08 else (-1 if ctl & 0x10 else 1)
        for i in range(n):
            val = self.read((bank << 16) | src)
            self._ppu_write(0x2100 + ((bb + pattern[i % len(pattern)]) & 0xFF), val)
            src = (src + step) & 0xFFFF
        self.reg[b + 5] = self.reg[b + 6] = 0

    def r16(self, a, wrap_bank=True):
        lo = self.read(a)
        b = (a & 0xFF0000) | ((a + 1) & 0xFFFF) if wrap_bank else (a + 1) & 0xFFFFFF
        return lo | self.read(b) << 8

    def w16(self, a, v, wrap_bank=False):
        self.write(a, v & 0xFF)
        b = (a & 0xFF0000) | ((a + 1) & 0xFFFF) if wrap_bank else (a + 1) & 0xFFFFFF
        self.write(b, v >> 8)

    # --- 플래그 ---
    @property
    def m8(self):
        return bool(self.p & 0x20)

    @property
    def x8(self):
        return bool(self.p & 0x10)

    def setp(self, v):
        self.p = v & 0xFF
        if self.x8:
            self.x &= 0xFF
            self.y &= 0xFF

    def nz(self, v, eight):
        if eight:
            v &= 0xFF
            self.p = (self.p & 0x7D) | (v & 0x80) | (0 if v else 2)
        else:
            v &= 0xFFFF
            self.p = (self.p & 0x7D) | ((v >> 8) & 0x80) | (0 if v else 2)

    # --- 스택 ---
    def push(self, v):
        self.write(self.s, v)
        self.s = (self.s - 1) & 0xFFFF

    def pull(self):
        self.s = (self.s + 1) & 0xFFFF
        return self.read(self.s)

    def push16(self, v):
        self.push(v >> 8)
        self.push(v & 0xFF)

    def pull16(self):
        lo = self.pull()
        return lo | self.pull() << 8

    # --- 명령 가져오기 ---
    def fetch(self):
        v = self.read((self.pbr << 16) | self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def fetch16(self):
        lo = self.fetch()
        return lo | self.fetch() << 8

    def fetch24(self):
        lo = self.fetch16()
        return lo | self.fetch() << 16

    # --- 주소 방식(유효 주소 24비트) ---
    def ea(self, mode):
        db = self.dbr << 16
        if mode == 'dp':
            return (self.d + self.fetch()) & 0xFFFF
        if mode == 'dpx':
            return (self.d + self.fetch() + self.x) & 0xFFFF
        if mode == 'dpy':
            return (self.d + self.fetch() + self.y) & 0xFFFF
        if mode == 'abs':
            return db | self.fetch16()
        if mode == 'absx':
            return (db | self.fetch16()) + self.x & 0xFFFFFF
        if mode == 'absy':
            return (db | self.fetch16()) + self.y & 0xFFFFFF
        if mode == 'long':
            return self.fetch24()
        if mode == 'longx':
            return (self.fetch24() + self.x) & 0xFFFFFF
        if mode == 'ind':     # (dp)
            p = (self.d + self.fetch()) & 0xFFFF
            return db | self.r16(p)
        if mode == 'indx':    # (dp,X)
            p = (self.d + self.fetch() + self.x) & 0xFFFF
            return db | self.r16(p)
        if mode == 'indy':    # (dp),Y
            p = (self.d + self.fetch()) & 0xFFFF
            return ((db | self.r16(p)) + self.y) & 0xFFFFFF
        if mode == 'indl':    # [dp]
            p = (self.d + self.fetch()) & 0xFFFF
            return self.r16(p) | self.read(p + 2) << 16
        if mode == 'indly':   # [dp],Y
            p = (self.d + self.fetch()) & 0xFFFF
            return ((self.r16(p) | self.read(p + 2) << 16) + self.y) & 0xFFFFFF
        if mode == 'sr':
            return (self.s + self.fetch()) & 0xFFFF
        if mode == 'sry':     # (sr,S),Y
            p = (self.s + self.fetch()) & 0xFFFF
            return ((db | self.r16(p)) + self.y) & 0xFFFFFF
        raise ValueError(mode)

    def load(self, mode, eight):
        if mode == 'imm':
            return self.fetch() if eight else self.fetch16()
        a = self.ea(mode)
        return self.read(a) if eight else self.r16(a, wrap_bank=False)

    def store(self, mode, v, eight):
        a = self.ea(mode)
        if eight:
            self.write(a, v)
        else:
            self.w16(a, v)

    # --- 연산 ---
    def adc(self, v):
        c = self.p & 1
        if self.m8:
            a = self.a & 0xFF
            if self.p & 8:
                lo = (a & 0x0F) + (v & 0x0F) + c
                if lo > 9:
                    lo += 6
                r = (a & 0xF0) + (v & 0xF0) + (0x10 if lo > 0x0F else 0) + (lo & 0x0F)
                ov = ~(a ^ v) & (a ^ r) & 0x80
                if r > 0x9F:
                    r += 0x60
            else:
                r = a + v + c
                ov = ~(a ^ v) & (a ^ r) & 0x80
            self.p = (self.p & ~0x41) | (1 if r > 0xFF else 0) | (0x40 if ov else 0)
            self.a = (self.a & 0xFF00) | (r & 0xFF)
            self.nz(r, True)
        else:
            a = self.a
            if self.p & 8:
                r, cc = 0, c
                for sh in (0, 4, 8, 12):
                    d = ((a >> sh) & 0xF) + ((v >> sh) & 0xF) + cc
                    cc = 1 if d > 9 else 0
                    if cc:
                        d += 6
                    r |= (d & 0xF) << sh
                ov = ~(a ^ v) & (a ^ r) & 0x8000
                carry = cc
            else:
                r = a + v + c
                ov = ~(a ^ v) & (a ^ r) & 0x8000
                carry = 1 if r > 0xFFFF else 0
            self.p = (self.p & ~0x41) | carry | (0x40 if ov else 0)
            self.a = r & 0xFFFF
            self.nz(r, False)

    def sbc(self, v):
        if self.p & 8:
            eight = self.m8
            mask = 0xFF if eight else 0xFFFF
            a = self.a & mask
            c = self.p & 1
            r, borrow = 0, 1 - c
            for sh in range(0, 8 if eight else 16, 4):
                d = ((a >> sh) & 0xF) - ((v >> sh) & 0xF) - borrow
                borrow = 1 if d < 0 else 0
                if borrow:
                    d += 10
                r |= (d & 0xF) << sh
            sign = 0x80 if eight else 0x8000
            ov = (a ^ v) & (a ^ r) & sign
            self.p = (self.p & ~0x41) | (0 if borrow else 1) | (0x40 if ov else 0)
            self.a = (self.a & 0xFF00) | r if eight else r
            self.nz(r, eight)
        else:
            self.adc(v ^ (0xFF if self.m8 else 0xFFFF))

    def cmp(self, reg, v, eight):
        mask = 0xFF if eight else 0xFFFF
        r = (reg & mask) - v
        self.p = (self.p & ~1) | (1 if r >= 0 else 0)
        self.nz(r, eight)

    def rmw(self, mode, fn):
        eight = self.m8
        if mode == 'acc':
            v = self.a & (0xFF if eight else 0xFFFF)
            r = fn(v, eight)
            self.a = (self.a & 0xFF00) | (r & 0xFF) if eight else r & 0xFFFF
            return
        a = self.ea(mode)
        v = self.read(a) if eight else self.r16(a, wrap_bank=False)
        r = fn(v, eight)
        if eight:
            self.write(a, r)
        else:
            self.w16(a, r)

    def _asl(self, v, e):
        top = 0x80 if e else 0x8000
        self.p = (self.p & ~1) | (1 if v & top else 0)
        r = (v << 1) & (0xFF if e else 0xFFFF)
        self.nz(r, e)
        return r

    def _lsr(self, v, e):
        self.p = (self.p & ~1) | (v & 1)
        r = v >> 1
        self.nz(r, e)
        return r

    def _rol(self, v, e):
        top = 0x80 if e else 0x8000
        c = self.p & 1
        self.p = (self.p & ~1) | (1 if v & top else 0)
        r = ((v << 1) | c) & (0xFF if e else 0xFFFF)
        self.nz(r, e)
        return r

    def _ror(self, v, e):
        top = 0x80 if e else 0x8000
        c = self.p & 1
        self.p = (self.p & ~1) | (v & 1)
        r = (v >> 1) | (top if c else 0)
        self.nz(r, e)
        return r

    def _inc(self, v, e):
        r = (v + 1) & (0xFF if e else 0xFFFF)
        self.nz(r, e)
        return r

    def _dec(self, v, e):
        r = (v - 1) & (0xFF if e else 0xFFFF)
        self.nz(r, e)
        return r

    def _bit(self, v, e, imm=False):
        a = self.a & (0xFF if e else 0xFFFF)
        self.p = (self.p & ~2) | (0 if a & v else 2)
        if not imm:
            top = 0x80 if e else 0x8000
            self.p = (self.p & ~0xC0) | (0x80 if v & top else 0) | (0x40 if v & (top >> 1) else 0)

    def branch(self, cond):
        off = self.fetch()
        if cond:
            self.pc = (self.pc + (off - 256 if off & 0x80 else off)) & 0xFFFF

    def setreg(self, name, v, eight):
        if eight:
            if name == 'a':
                self.a = (self.a & 0xFF00) | (v & 0xFF)
            else:
                setattr(self, name, v & 0xFF)
        else:
            setattr(self, name, v & 0xFFFF)

    # --- 한 명령 ---
    def step(self):
        full = (self.pbr << 16) | self.pc
        h = self.hooks.get(full)
        if h is not None and h(self):
            return
        self.steps += 1
        op = self.fetch()
        m8, x8 = self.m8, self.x8
        grp = ALU.get(op)
        if grp:
            name, mode = grp
            if name == 'STA':
                self.store(mode, self.a, m8)
                return
            v = self.load(mode, m8)
            if name == 'ORA':
                r = (self.a | v)
            elif name == 'AND':
                r = (self.a & v)
            elif name == 'EOR':
                r = (self.a ^ v)
            elif name == 'ADC':
                self.adc(v)
                return
            elif name == 'SBC':
                self.sbc(v)
                return
            elif name == 'CMP':
                self.cmp(self.a, v, m8)
                return
            elif name == 'LDA':
                r = v
            self.setreg('a', r, m8)
            self.nz(r, m8)
            return
        fn = OPS[op]
        fn(self, m8, x8)

    def rts(self):
        self.pc = (self.pull16() + 1) & 0xFFFF

    def rtl(self):
        self.rts()
        self.pbr = self.pull()

    def run(self, max_steps=5_000_000):
        while True:
            if self.steps > max_steps:
                raise Stop('step limit')
            self.step()

    def jsl(self, addr, max_steps=5_000_000):
        """addr(24비트)를 JSL 로 부르듯 돌리고 RTL 로 돌아오면 멈춘다."""
        self.push(0xFF)
        self.push16(0xFFFD)
        self.pbr, self.pc = addr >> 16, addr & 0xFFFF
        start = self.steps
        while not (self.pbr == 0xFF and self.pc == 0xFFFE):
            if self.steps - start > max_steps:
                raise Stop('step limit at %06X' % ((self.pbr << 16) | self.pc))
            self.step()

    def jsr(self, addr, max_steps=5_000_000):
        """addr(24비트, 같은 뱅크)를 JSR 로 부르듯 돌리고 RTS 로 돌아오면 멈춘다."""
        self.push16(0xFFFD)
        self.pbr, self.pc = addr >> 16, addr & 0xFFFF
        start = self.steps
        while not self.pc == 0xFFFE:
            if self.steps - start > max_steps:
                raise Stop('step limit at %06X' % ((self.pbr << 16) | self.pc))
            self.step()


ALU = {}
for base, name in ((0x00, 'ORA'), (0x20, 'AND'), (0x40, 'EOR'), (0x60, 'ADC'), (0x80, 'STA'), (0xA0, 'LDA'),
                   (0xC0, 'CMP'), (0xE0, 'SBC')):
    for low, mode in ((0x01, 'indx'), (0x03, 'sr'), (0x05, 'dp'), (0x07, 'indl'), (0x09, 'imm'), (0x0D, 'abs'),
                      (0x0F, 'long'), (0x11, 'indy'), (0x12, 'ind'), (0x13, 'sry'), (0x15, 'dpx'), (0x17, 'indly'),
                      (0x19, 'absy'), (0x1D, 'absx'), (0x1F, 'longx')):
        if name == 'STA' and mode == 'imm':
            continue
        ALU[base + low] = (name, mode)

OPS = [None] * 256


def op(*codes):
    def deco(f):
        for c in codes:
            OPS[c] = f
        return f
    return deco


def _mk_rmw(code_mode, fname):
    for code, mode in code_mode:
        OPS[code] = (lambda md: lambda c, m8, x8: c.rmw(md, getattr(c, fname)))(mode)


_mk_rmw(((0x0A, 'acc'), (0x06, 'dp'), (0x0E, 'abs'), (0x16, 'dpx'), (0x1E, 'absx')), '_asl')
_mk_rmw(((0x4A, 'acc'), (0x46, 'dp'), (0x4E, 'abs'), (0x56, 'dpx'), (0x5E, 'absx')), '_lsr')
_mk_rmw(((0x2A, 'acc'), (0x26, 'dp'), (0x2E, 'abs'), (0x36, 'dpx'), (0x3E, 'absx')), '_rol')
_mk_rmw(((0x6A, 'acc'), (0x66, 'dp'), (0x6E, 'abs'), (0x76, 'dpx'), (0x7E, 'absx')), '_ror')
_mk_rmw(((0x1A, 'acc'), (0xE6, 'dp'), (0xEE, 'abs'), (0xF6, 'dpx'), (0xFE, 'absx')), '_inc')
_mk_rmw(((0x3A, 'acc'), (0xC6, 'dp'), (0xCE, 'abs'), (0xD6, 'dpx'), (0xDE, 'absx')), '_dec')


def _tsb_trb(mode, setbits):
    def f(c, m8, x8):
        def g(v, e):
            a = c.a & (0xFF if e else 0xFFFF)
            c.p = (c.p & ~2) | (0 if a & v else 2)
            return (v | a) if setbits else (v & ~a)
        c.rmw(mode, g)
    return f


OPS[0x04], OPS[0x0C] = _tsb_trb('dp', True), _tsb_trb('abs', True)
OPS[0x14], OPS[0x1C] = _tsb_trb('dp', False), _tsb_trb('abs', False)

for code, mode in ((0x24, 'dp'), (0x2C, 'abs'), (0x34, 'dpx'), (0x3C, 'absx')):
    OPS[code] = (lambda md: lambda c, m8, x8: c._bit(c.load(md, m8), m8))(mode)
OPS[0x89] = lambda c, m8, x8: c._bit(c.load('imm', m8), m8, imm=True)


def _ld(reg, codes):
    for code, mode in codes:
        def f(c, m8, x8, md=mode):
            v = c.load(md, x8)
            c.setreg(reg, v, x8)
            c.nz(v, x8)
        OPS[code] = f


_ld('x', ((0xA2, 'imm'), (0xA6, 'dp'), (0xAE, 'abs'), (0xB6, 'dpy'), (0xBE, 'absy')))
_ld('y', ((0xA0, 'imm'), (0xA4, 'dp'), (0xAC, 'abs'), (0xB4, 'dpx'), (0xBC, 'absx')))


def _st(reg, codes):
    for code, mode in codes:
        def f(c, m8, x8, md=mode):
            if reg == 'z':
                c.store(md, 0, m8)
            else:
                c.store(md, getattr(c, reg), x8)
        OPS[code] = f


_st('x', ((0x86, 'dp'), (0x8E, 'abs'), (0x96, 'dpy')))
_st('y', ((0x84, 'dp'), (0x8C, 'abs'), (0x94, 'dpx')))
_st('z', ((0x64, 'dp'), (0x9C, 'abs'), (0x74, 'dpx'), (0x9E, 'absx')))

for code, reg, mode in ((0xE0, 'x', 'imm'), (0xE4, 'x', 'dp'), (0xEC, 'x', 'abs'),
                        (0xC0, 'y', 'imm'), (0xC4, 'y', 'dp'), (0xCC, 'y', 'abs')):
    OPS[code] = (lambda r, md: lambda c, m8, x8: c.cmp(getattr(c, r), c.load(md, x8), x8))(reg, mode)

for code, cond in ((0x10, lambda c: not c.p & 0x80), (0x30, lambda c: c.p & 0x80), (0x50, lambda c: not c.p & 0x40),
                   (0x70, lambda c: c.p & 0x40), (0x90, lambda c: not c.p & 1), (0xB0, lambda c: c.p & 1),
                   (0xD0, lambda c: not c.p & 2), (0xF0, lambda c: c.p & 2), (0x80, lambda c: True)):
    OPS[code] = (lambda cd: lambda c, m8, x8: c.branch(cd(c)))(cond)


@op(0x82)
def _brl(c, m8, x8):
    off = c.fetch16()
    c.pc = (c.pc + (off - 0x10000 if off & 0x8000 else off)) & 0xFFFF


@op(0x4C)
def _jmp(c, m8, x8):
    c.pc = c.fetch16()


@op(0x5C)
def _jml(c, m8, x8):
    a = c.fetch24()
    c.pbr, c.pc = a >> 16, a & 0xFFFF


@op(0x6C)
def _jmpi(c, m8, x8):
    c.pc = c.r16(c.fetch16())


@op(0x7C)
def _jmpix(c, m8, x8):
    p = (c.fetch16() + c.x) & 0xFFFF
    c.pc = c.r16((c.pbr << 16) | p)


@op(0xDC)
def _jmli(c, m8, x8):
    p = c.fetch16()
    a = c.r16(p) | c.read(p + 2) << 16
    c.pbr, c.pc = a >> 16, a & 0xFFFF


@op(0x20)
def _jsr(c, m8, x8):
    t = c.fetch16()
    c.push16((c.pc - 1) & 0xFFFF)
    c.pc = t


@op(0xFC)
def _jsrix(c, m8, x8):
    p = (c.fetch16() + c.x) & 0xFFFF
    c.push16((c.pc - 1) & 0xFFFF)
    c.pc = c.r16((c.pbr << 16) | p)


@op(0x22)
def _jsl(c, m8, x8):
    t = c.fetch24()
    c.push(c.pbr)
    c.push16((c.pc - 1) & 0xFFFF)
    c.pbr, c.pc = t >> 16, t & 0xFFFF


@op(0x60)
def _rts(c, m8, x8):
    c.pc = (c.pull16() + 1) & 0xFFFF


@op(0x6B)
def _rtl(c, m8, x8):
    c.pc = (c.pull16() + 1) & 0xFFFF
    c.pbr = c.pull()


@op(0x40)
def _rti(c, m8, x8):
    c.setp(c.pull())
    c.pc = c.pull16()
    c.pbr = c.pull()


def _interrupt(vec):
    def f(c, m8, x8):
        c.fetch()
        c.push(c.pbr)
        c.push16(c.pc)
        c.push(c.p)
        c.p = (c.p | 0x04) & ~0x08
        c.pbr, c.pc = 0, c.r16(vec)
    return f


OPS[0x00] = _interrupt(0xFFE6)
OPS[0x02] = _interrupt(0xFFE4)

for code, bit, val in ((0x18, 1, 0), (0x38, 1, 1), (0x58, 4, 0), (0x78, 4, 1), (0xB8, 0x40, 0), (0xD8, 8, 0),
                       (0xF8, 8, 1)):
    OPS[code] = (lambda b, v: lambda c, m8, x8: setattr(c, 'p', (c.p | b) if v else (c.p & ~b)))(bit, val)

OPS[0xC2] = lambda c, m8, x8: c.setp(c.p & ~c.fetch())
OPS[0xE2] = lambda c, m8, x8: c.setp(c.p | c.fetch())
OPS[0xFB] = lambda c, m8, x8: None  # XCE: 네이티브만
OPS[0xEA] = lambda c, m8, x8: None
OPS[0x42] = lambda c, m8, x8: c.fetch()  # WDM
OPS[0xCB] = lambda c, m8, x8: None  # WAI
OPS[0xDB] = lambda c, m8, x8: (_ for _ in ()).throw(Stop('STP'))


def _t(src, dst, flags=True, width=None):
    def f(c, m8, x8):
        e = {'m': m8, 'x': x8, '16': False}[width]
        v = getattr(c, src)
        if dst == 'a' and e:
            c.a = (c.a & 0xFF00) | (v & 0xFF)
        else:
            setattr(c, dst, v & (0xFF if e else 0xFFFF))
        if flags:
            c.nz(v, e)
    return f


OPS[0xAA] = _t('a', 'x', width='x')
OPS[0xA8] = _t('a', 'y', width='x')
OPS[0x8A] = _t('x', 'a', width='m')
OPS[0x98] = _t('y', 'a', width='m')
OPS[0x9B] = _t('x', 'y', width='x')
OPS[0xBB] = _t('y', 'x', width='x')
OPS[0xBA] = _t('s', 'x', width='x')
OPS[0x9A] = lambda c, m8, x8: setattr(c, 's', c.x)
OPS[0x5B] = _t('a', 'd', width='16')
OPS[0x7B] = _t('d', 'a', width='16')
OPS[0x1B] = lambda c, m8, x8: setattr(c, 's', c.a)
OPS[0x3B] = _t('s', 'a', width='16')


@op(0xEB)
def _xba(c, m8, x8):
    c.a = ((c.a >> 8) | (c.a << 8)) & 0xFFFF
    c.nz(c.a & 0xFF, True)


for code, reg, delta in ((0xE8, 'x', 1), (0xCA, 'x', -1), (0xC8, 'y', 1), (0x88, 'y', -1)):
    def f(c, m8, x8, r=reg, d=delta):
        v = (getattr(c, r) + d) & (0xFF if x8 else 0xFFFF)
        setattr(c, r, v)
        c.nz(v, x8)
    OPS[code] = f


@op(0x48)
def _pha(c, m8, x8):
    if m8:
        c.push(c.a)
    else:
        c.push16(c.a)


@op(0x68)
def _pla(c, m8, x8):
    v = c.pull() if m8 else c.pull16()
    c.setreg('a', v, m8)
    c.nz(v, m8)


for pcode, lcode, reg in ((0xDA, 0xFA, 'x'), (0x5A, 0x7A, 'y')):
    def ph(c, m8, x8, r=reg):
        if x8:
            c.push(getattr(c, r))
        else:
            c.push16(getattr(c, r))

    def pl(c, m8, x8, r=reg):
        v = c.pull() if x8 else c.pull16()
        setattr(c, r, v)
        c.nz(v, x8)
    OPS[pcode], OPS[lcode] = ph, pl

OPS[0x08] = lambda c, m8, x8: c.push(c.p)
OPS[0x28] = lambda c, m8, x8: c.setp(c.pull())
OPS[0x8B] = lambda c, m8, x8: c.push(c.dbr)
OPS[0x4B] = lambda c, m8, x8: c.push(c.pbr)


@op(0xAB)
def _plb(c, m8, x8):
    c.dbr = c.pull()
    c.nz(c.dbr, True)


OPS[0x0B] = lambda c, m8, x8: c.push16(c.d)


@op(0x2B)
def _pld(c, m8, x8):
    c.d = c.pull16()
    c.nz(c.d, False)


OPS[0xF4] = lambda c, m8, x8: c.push16(c.fetch16())


@op(0xD4)
def _pei(c, m8, x8):
    c.push16(c.r16((c.d + c.fetch()) & 0xFFFF))


@op(0x62)
def _per(c, m8, x8):
    off = c.fetch16()
    c.push16((c.pc + off) & 0xFFFF)


def _move(step):
    def f(c, m8, x8):
        dst = c.fetch()
        src = c.fetch()
        c.dbr = dst
        c.write((dst << 16) | c.y, c.read((src << 16) | c.x))
        mask = 0xFF if x8 else 0xFFFF
        c.x = (c.x + step) & mask
        c.y = (c.y + step) & mask
        c.a = (c.a - 1) & 0xFFFF
        if c.a != 0xFFFF:
            c.pc = (c.pc - 3) & 0xFFFF
    return f


OPS[0x54] = _move(1)
OPS[0x44] = _move(-1)

missing = [i for i in range(256) if OPS[i] is None and i not in ALU]
assert not missing, missing
