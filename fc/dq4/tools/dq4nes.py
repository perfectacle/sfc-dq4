"""DQ4(FC) 를 롬만으로 프레임 단위로 돌리는 작은 NES. 장면 화면(nametable·CHR·팔레트·OAM)을 에뮬레이터 없이 뜨려고 쓴다.

dq4cpu.CPU 위에 MMC1(SUROM: CHR 0 레지스터 bit4 가 256KB 절반), PPU 레지스터(nametable·CHR RAM·팔레트, $2007 읽기 버퍼 없음),
OAM DMA, 패드 하나, 진짜 BRK($FFFE)·NMI($FFFA)를 더했다. 소리(APU)는 버린다.
한 프레임은 NMI 에서 시작하는 29781 CPU 사이클이고, 명령마다 기본 사이클과 분기 성립 1 을 센다(페이지를 넘는 1 은 세지 않음).
그래서 프레임 안의 정확한 자리는 실기와 몇 사이클 어긋날 수 있지만, 게임은 NMI 로 프레임을 세므로 장면 순서는 같다.
$2002 bit7 은 vblank(프레임 처음 2273 사이클), bit6(sprite 0 hit)은 OAM 0 의 Y+1 줄에 닿으면 켠다(BG 가 겹치는지는 보지 않음).
"""
import copy

import dq4cpu
from kr_patch.fc.dis6502 import OPS

FRAME = 29781
VBLANK = 2273            # 20 scanline
LINE = 341 / 3           # scanline 하나의 CPU 사이클
TOP = VBLANK + LINE      # pre-render 줄 다음, 보이는 줄 0 이 시작하는 사이클
BUTTON = {'a': 1, 'b': 2, 'select': 4, 'start': 8, 'up': 16, 'down': 32, 'left': 64, 'right': 128}

_MODE = {'imp': 2, 'acc': 2, 'imm': 2, 'zp': 3, 'zpx': 4, 'zpy': 4, 'abs': 4, 'abx': 4, 'aby': 4,
         'izx': 6, 'izy': 5, 'rel': 3, 'ind': 5}
_FIXED = {'JSR': 6, 'RTS': 6, 'RTI': 6, 'PHA': 3, 'PHP': 3, 'PLA': 4, 'PLP': 4, 'BRK': 7}
CYCLES = [2] * 256
for _op, (_mn, _md) in OPS.items():
    c = _FIXED.get(_mn, _MODE[_md])
    if _mn in ('ASL', 'LSR', 'ROL', 'ROR', 'INC', 'DEC') and _md != 'acc':
        c = {'zp': 5, 'zpx': 6, 'abs': 6, 'abx': 7}[_md]
    elif _mn == 'STA' and _md in ('abx', 'aby', 'izy'):
        c = 5 if _md != 'izy' else 6
    elif _mn == 'JMP':
        c = 3 if _md == 'abs' else 5
    CYCLES[_op] = c


BRANCH = {op for op, (mn, md) in OPS.items() if md == 'rel'}


def pad_bits(spec):
    """'a', 'up+b' 같은 버튼 이름들 → 패드 바이트($4016 으로 A 가 먼저 나가는 순서)."""
    v = 0
    for b in spec.split('+'):
        v |= BUTTON[b]
    return v


class NES(dq4cpu.CPU):
    def __init__(self, prg):
        super().__init__(prg, 0x1F)
        self.ram[0x507] = 0
        self.vram = bytearray(0x4000)   # $0000-$1FFF CHR RAM, $2000-$27FF nametable RAM 2KB, $3F00 팔레트
        self.oam = bytearray(256)
        self.ctrl = self.mask = 0
        self.w = 0
        self.vaddr = 0
        self.t = self.fx = 0          # loopy t·fine X: 다음 프레임 맨 위 스크롤
        self.top = ((0, 0, 0), 0)      # 이 프레임 보이는 줄이 시작할 때의 (스크롤 x, y, nametable), $2001
        self.inc = 1
        self.mmc = [0x0C, 0x10, 0, 0]   # control, CHR0, CHR1, PRG
        self.sr = self.sn = 0
        self.pad = 0
        self.shift = 0
        self.fc = 0                     # 프레임 안 사이클
        self.frame = 0
        self.log = []                   # 이 프레임의 ($2000·$2001·$2005·$2006 쓰기) (scanline, dot, 레지스터, 값, w)
        self.vbl = False
        self.hit = None
        self.pc = self.rd16(0xFFFC)

    # --- 매퍼 ---
    def mmc1(self, addr, v):
        if v & 0x80:
            self.sr = self.sn = 0
            self.mmc[0] |= 0x0C
            return
        self.sr |= (v & 1) << self.sn
        self.sn += 1
        if self.sn == 5:
            self.mmc[(addr >> 13) & 3] = self.sr
            self.bank = (self.mmc[1] & 0x10) | (self.mmc[3] & 0x0F)
            self.sr = self.sn = 0

    def nt_addr(self, a):
        """PPU $2000-$2FFF → nametable RAM 2KB 의 자리. MMC1 control bit0-1: 0·1 한 장, 2 세로, 3 가로 미러링."""
        a &= 0xFFF
        m = self.mmc[0] & 3
        if m == 2:
            page = (a >> 10) & 1
        elif m == 3:
            page = (a >> 11) & 1
        else:
            page = m
        return 0x2000 + page * 0x400 + (a & 0x3FF)

    def ppu_at(self, a):
        a &= 0x3FFF
        if a >= 0x3F00:
            a = 0x3F00 | (a & 0x1F)
            if a & 0x13 == 0x10:
                a &= ~0x10
            return a
        if a >= 0x2000:
            return self.nt_addr(a)
        return a

    def scan(self):
        """지금 사이클의 (scanline, dot). vblank 는 241~260, pre-render 는 -1."""
        if self.fc < VBLANK:
            return 241 + int(self.fc / LINE), int(self.fc % LINE * 3)
        if self.fc < TOP:
            return -1, int((self.fc - VBLANK) * 3)
        t = self.fc - TOP
        return int(t / LINE), int(t % LINE * 3)

    # --- 메모리 ---
    def rd(self, addr):
        addr &= 0xFFFF
        if 0x2000 <= addr < 0x4000:
            r = addr & 7
            if r == 2:
                v = (0x80 if self.vbl else 0) | (0x40 if self.hit is not None and self.fc >= self.hit else 0)
                self.vbl = False
                self.w = 0
                return v
            if r == 7:
                a = self.ppu_at(self.vaddr)
                self.vaddr = (self.vaddr + self.inc) & 0x3FFF
                return self.vram[a]
            return 0
        if addr == 0x4016:
            b = self.shift & 1
            self.shift >>= 1
            return 0x40 | b
        if 0x4000 <= addr < 0x6000:
            return 0
        return super().rd(addr)

    def wr(self, addr, v):
        addr &= 0xFFFF
        v &= 0xFF
        if addr >= 0x8000:
            self.mmc1(addr, v)
            return
        if 0x2000 <= addr < 0x4000:
            r = addr & 7
            if r in (0, 1, 5, 6):
                sl, dot = self.scan()
                self.log.append((sl, dot, 0x2000 + r, v, self.w + 1 if r in (5, 6) else 0))
            if r == 0:
                self.ctrl = v
                self.inc = 32 if v & 4 else 1
                self.t = (self.t & ~0xC00) | (v & 3) << 10
            elif r == 1:
                self.mask = v
            elif r == 5:
                if self.w == 0:
                    self.t = (self.t & ~0x1F) | v >> 3
                    self.fx = v & 7
                else:
                    self.t = (self.t & ~0x73E0) | (v & 7) << 12 | (v >> 3) << 5
                self.w ^= 1
            elif r == 6:
                if self.w == 0:
                    self.t = (self.t & 0xFF) | (v & 0x3F) << 8
                else:
                    self.t = (self.t & 0x7F00) | v
                    self.vaddr = self.t & 0x3FFF
                self.w ^= 1
            elif r == 7:
                self.vram[self.ppu_at(self.vaddr)] = v
                self.vaddr = (self.vaddr + self.inc) & 0x3FFF
            return
        if addr == 0x4014:
            self.oam[:] = bytes(self.rd((v << 8) + i) for i in range(256))
            self.fc += 513
            return
        if addr == 0x4016:
            if v & 1:
                self.shift = self.pad
            return
        if 0x4000 <= addr < 0x6000:
            return
        super().wr(addr, v)

    # --- 실행 ---
    def brk(self):
        ret = (self.pc + 2) & 0xFFFF
        self.push(ret >> 8)
        self.push(ret & 0xFF)
        self.push(self.p() | 0x30)
        self.pc = self.rd16(0xFFFE)

    def step(self):
        pc = self.pc
        if pc == 0xFF77 and self.fc >= TOP:
            # 1F:$FF74 프레임 기다리기(NOP NOP INC $12 CMP $050C BEQ, 한 바퀴 16사이클). NMI 전까지 도는 바퀴 수만큼
            # $12 를 올리고 프레임 끝으로 건너뛴다(빠르게 하려고. 결과는 한 명령씩 돌린 것과 같다)
            k = int((FRAME - self.fc) // 16)
            if k > 0:
                self.ram[0x12] = (self.ram[0x12] + k) & 0xFF
                self.fc += 16 * k
                return
        op = self.rd(pc) if pc != 0xFF91 else 0x60
        self.exec1()
        if pc == 0xFF91:
            # dq4cpu 는 뱅크 전환 루틴을 바로 건너뛰므로 MMC1 레지스터를 그 뱅크에 맞춘다
            self.mmc[1] = (self.mmc[1] & ~0x10) | (self.bank & 0x10)
            self.mmc[3] = self.bank & 0x0F
        c = CYCLES[op]
        if op in BRANCH:
            # 분기: 성립하지 않으면 2, 성립하면 3(페이지를 넘는 1 은 뺌)
            c = 2 if self.pc == (pc + 2) & 0xFFFF else 3
        self.fc += c

    def run_frame(self):
        """NMI 하나부터 다음 NMI 직전까지. 끝나면 self.log 가 이 프레임의 PPU 쓰기, 화면은 이 프레임에 보인 것."""
        self.frame += 1
        self.log = []
        self.fc = 0
        if self.ctrl & 0x80:
            self.push(self.pc >> 8)
            self.push(self.pc & 0xFF)
            self.push(self.p() & ~0x10 | 0x20)
            self.pc = self.rd16(0xFFFA)
        self.vbl = True
        self.hit = None
        while self.fc < VBLANK:
            self.step()
        self.vbl = False
        t = self.t
        self.top = (((t & 0x1F) * 8 + self.fx, (t >> 5 & 0x1F) * 8 + (t >> 12 & 7), t >> 10 & 3), self.mask)
        if self.mask & 0x18 and self.oam[0] < 0xEF:
            self.hit = TOP + (self.oam[0] + 1) * LINE + self.oam[3] / 3
        while self.fc < FRAME:
            self.step()

    def run(self, frames, buttons=0, each=None):
        for _ in range(frames):
            self.pad = buttons
            self.run_frame()
            if each:
                each(self)

    def snapshot(self):
        return copy.deepcopy(self)

    def nametables(self):
        return bytes(self.vram[0x2000:0x2800])
