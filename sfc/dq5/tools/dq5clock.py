"""DQ5(SFC) 롬 코드를 마스터 클록 단위로 돌리는 해석기. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의
「롬 코드로 돌리기」.

dq5titlevm.Cpu 의 주기 셈(NMI 마다 0 에서 다시 셈, 리프레시를 한 프레임 길이에서 뺌)을 절대 시각으로 바꾸고, 명령마다
메모리 접근·내부 주기의 차례를 MesenCE(Core/SNES/SnesCpu.Instructions.h)와 같게 둔 것이다. 출발점의 마스터 클록·줄·
줄 안 자리(MesenCE 상태 masterClock·ppu.scanline·memoryManager.hClock)와 DMA/HDMA 채널 상태를 받는다
(lua/dq5fx3e.lua 의 VMSCREENS=1 이 v<연출>.clock0 으로 남김).

- CPU 한 주기: 주기 시작에 걸린 DMA·HDMA 를 하고 NMI 신호를 보고, 접근 시간(ROM·WRAM 8, I/O 6, $4000~$41FF 12,
  내부 주기 6)만큼 시계를 민다.
- 줄: 1364 마스터 주기(홀수 프레임의 240줄은 1360). 줄 안 538 - (줄 첫머리 클록 & 7)에서 리프레시로
  40 을 멈추고, 보이는 줄(0~239)의 1104 에서 HDMA 를, 0줄의 12 + (클록 & 7) 에서 HDMA 초기화를 건다. 둘 다 한 주기 늦게 한다.
- DMA·HDMA: 시작에 8 마스터 주기 단위로 맞추고(2~8), 끝에 그때의 CPU 접근 시간 단위로 다시 맞춘다. 일반 DMA 는 덧 8 +
  채널마다 8 + 바이트마다 8, HDMA 는 덧 8 + 채널마다 8(표 읽기) + 바이트마다 8 + 간접 주소 16. HDMA 는 PPU 레지스터에
  실제로 써서(줄마다 스크롤·CGRAM 등) 프레임 기다림 때의 화면 메모리·스크롤이 게임과 같다.
- NMI: 240줄의 줄 안 6 에서 신호가 서고, 다음 CPU 주기에 받기로 정해져 그 명령이 끝난 뒤 받는다. 받기는 코드 읽기·내부 주기·
  스택 쓰기 넷·벡터 읽기 둘. 받기로 정해진 뒤의 내부 주기 하나짜리 명령은 그 주기를 코드 읽기로 한다.
"""
import bisect
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import dq5titlevm  # noqa: E402
from w65816 import Cpu as _Cpu  # noqa: E402

LINE = 1364
HDMA_AT = 276 * 4
VBLANK = 240
LINES = 262
C, Z, I, D, X, M, V, N = 1, 2, 4, 8, 0x10, 0x20, 0x40, 0x80
OFFSETS = ((0,), (0, 1), (0, 0), (0, 0, 1, 1), (0, 1, 2, 3), (0, 1, 0, 1), (0, 0), (0, 0, 1, 1))


def load_clock(path):
    st = {}
    for ln in open(path):
        k, _, v = ln.strip().partition('=')
        if k:
            st[k] = v
    return st


def load_apu(path):
    """lua/dq5fx3e.lua 가 남긴 v<연출>.apu(「마스터 클록 포트 값」) → 포트마다 (시각 목록, 값 목록)."""
    out = [([], []) for _ in range(4)]
    for ln in open(path):
        t, a, v = ln.split()
        out[int(a, 16)][0].append(int(t))
        out[int(a, 16)][1].append(int(v, 16))
    return out


def _int(v):
    return 1 if v == 'true' else 0 if v == 'false' else int(v)


class Cpu(dq5titlevm.Cpu):
    def __init__(self, rom, wram, clock):
        super().__init__(rom, wram)
        self.t = _int(clock['masterClock'])
        self.h = _int(clock['memoryManager.hClock'])
        self.v = _int(clock['ppu.scanline'])
        self.ref = _int(clock.get('memoryManager.dramRefreshPosition', '538'))
        # 240줄이 짧은 프레임(MesenCE _oddFrame)은 그 프레임의 240줄 전 프레임 수가 홀수인 프레임이다. 프레임 수는 240줄에서,
        # _oddFrame 은 줄 0 으로 넘어갈 때 바뀌므로 240줄 뒤에서 시작하면 하나 어긋난다
        self.odd = (_int(clock.get('ppu.frameCount', '0')) & 1) ^ (self.v >= VBLANK)
        self.stopped = 0
        self.hch = {}
        for ch in range(8):
            p = f'dmaController.channel[{ch}].'
            if p + 'doTransfer' not in clock:
                continue
            self.hch[ch] = {'do': _int(clock[p + 'doTransfer']), 'cnt': _int(clock[p + 'hdmaLineCounterAndRepeat']),
                            'p': _int(clock[p + 'hdmaTableAddress']), 'ia': _int(clock[p + 'transferSize'])}
            if _int(clock[p + 'hdmaFinished']):
                self.stopped |= 1 << ch
        # NMITIMEN 은 쓰기 전용이라 상태 값(없으면 켠 것으로)
        self.reg[0x4200] |= 0x80 if _int(clock.get('internalRegisters.enableNmi', 'true')) else 0
        self.auto_start = _int(clock.get('internalRegisters.autoReadClockStart', '0'))
        self.nmi_cnt = 0
        self.need_nmi = False
        self.irq_lock = False
        self.hdma_pending = self.init_pending = False
        self.dma_pending = self.start_delay = False
        self.dma_active = []
        self.dma_counter = 0
        self.init_at = -1
        self.quiet = False
        self.cur_speed = 8
        self.nmis = []
        self.base = 0
        self.apu = None
        self.apu_miss = 0
        self._mask = 0xFFFFFF
        self._imm = False
        self._op = 0

    # --- 시계 ---
    def advance(self, n):
        while n > 0:
            if self.h < self.ref:
                nxt, kind = self.ref, 0
            elif self.h < HDMA_AT and self.v < VBLANK:
                nxt, kind = HDMA_AT, 1
            else:
                nxt, kind = (LINE - 4 if self.v == VBLANK and self.odd else LINE), 2
            if self.h < self.init_at <= nxt:
                nxt, kind = self.init_at, 3
            if self.h < 6 <= nxt and self.v == VBLANK:
                nxt, kind = 6, 4
            d = nxt - self.h
            if d > n:
                self.h += n
                self.t += n
                return
            self.h += d
            self.t += d
            n -= d
            if kind == 0:
                self.h += 40
                self.t += 40
            elif kind == 1:
                if self.reg[0x420C] & ~self.stopped:
                    self.hdma_pending = self.start_delay = True
            elif kind == 3:
                self.init_pending = self.start_delay = True
                self.init_at = -1
            elif kind == 4:
                if self.reg[0x4200] & 0x80:
                    self.nmi_cnt = 1
            else:
                self.h = 0
                self.v += 1
                self.ref = 538 - (self.t & 7)
                if self.v == VBLANK:
                    r = self.t + 130
                    self.auto_start = r + ((256 - (r & 0xFF)) if r & 0xFF else 0) - 128
                elif self.v == LINES:
                    self.v = 0
                    self.odd ^= 1
                    self.init_at = 12 + (self.t & 7)

    def cycle(self, speed):
        """CPU 한 주기(SnesCpu::Read·Write·Idle): 주기 시작에 걸린 DMA 와 NMI 검출, 그다음 접근 시간."""
        self.cur_speed = speed
        self.base += speed
        if self.start_delay or self.hdma_pending or self.init_pending or self.dma_pending:
            self.irq_lock = self.pending()
        else:
            self.irq_lock = False
        if self.nmi_cnt:
            self.nmi_cnt -= 1
            if not self.nmi_cnt:
                if not self.irq_lock:
                    self.need_nmi = True
                else:
                    self.nmi_cnt = 1
        self.advance(speed)

    # --- DMA (SnesDmaController) ---
    def sync_start(self):
        self.dma_counter = 8 - (self.t & 7)
        self.advance(self.dma_counter)

    def sync_end(self):
        sp = self.cur_speed
        self.advance(sp - self.dma_counter % sp)

    def pending(self):
        if self.start_delay:
            self.start_delay = False
            return False
        if self.hdma_pending:
            return self.do_hdma()
        if self.init_pending:
            return self.do_init()
        if self.dma_pending:
            self.dma_pending = False
            self.sync_start()
            self.advance(8)
            self.dma_counter += 8
            self.pending()
            for n in self.dma_active:
                self.dma_counter += 8
                self.advance(8)
                self.pending()
                for _ in range(n):
                    self.advance(8)
                    if self.start_delay or self.hdma_pending or self.init_pending:
                        self.pending()
                self.dma_counter += 8 * n
            self.dma_active = []
            self.sync_end()
            return True
        return False

    def _tab(self, bank, a):
        return _Cpu.read(self, bank << 16 | (a & 0xFFFF))

    def do_init(self):
        self.init_pending = False
        for st in self.hch.values():
            st['do'] = 0
        self.stopped = 0
        en = self.reg[0x420C]
        if not en:
            return False
        sync = not self.dma_active
        if sync:
            self.sync_start()
        self.dma_counter += 8
        self.advance(8)
        for ch in range(8):
            st = self.hch.setdefault(ch, {'do': 0, 'cnt': 0, 'p': 0, 'ia': 0})
            st['do'] = 1
            if not en >> ch & 1:
                continue
            b = 0x4300 + ch * 16
            ctl, bank = self.reg[b], self.reg[b + 4]
            st['p'] = self.reg[b + 2] | self.reg[b + 3] << 8
            self.advance(4)
            st['cnt'] = self._tab(bank, st['p'])
            self.advance(4)
            self.dma_counter += 8
            st['p'] = (st['p'] + 1) & 0xFFFF
            stop = st['cnt'] == 0
            if stop:
                self.stopped |= 1 << ch
            if ctl & 0x40:
                self.advance(8)
                lo = self._tab(bank, st['p'])
                st['p'] = (st['p'] + 1) & 0xFFFF
                self.dma_counter += 8
                if not stop:
                    self.advance(8)
                    hi = self._tab(bank, st['p'])
                    st['p'] = (st['p'] + 1) & 0xFFFF
                    self.dma_counter += 8
                    st['ia'] = lo | hi << 8
                else:
                    st['ia'] = lo << 8
        if sync:
            self.sync_end()
        return True

    def do_hdma(self):
        self.hdma_pending = False
        act = self.reg[0x420C] & ~self.stopped
        if not act:
            return False
        sync = not self.dma_active
        if sync:
            self.sync_start()
        self.dma_counter += 8
        self.advance(8)
        live = [ch for ch in range(8) if act >> ch & 1]
        for ch in live:
            st = self.hch[ch]
            if st['do']:
                b = 0x4300 + ch * 16
                ctl, bb = self.reg[b], self.reg[b + 1]
                for off in OFFSETS[ctl & 7]:
                    if ctl & 0x40:
                        v = self._tab(self.reg[b + 7], st['ia'])
                        st['ia'] = (st['ia'] + 1) & 0xFFFF
                    else:
                        v = self._tab(self.reg[b + 4], st['p'])
                        st['p'] = (st['p'] + 1) & 0xFFFF
                    self.advance(8)
                    self.dma_counter += 8
                    self.reg[0x2100 + ((bb + off) & 0xFF)] = v
                    self._ppu_write(0x2100 + ((bb + off) & 0xFF), v)
        for ch in live:
            st = self.hch[ch]
            b = 0x4300 + ch * 16
            ctl, bank = self.reg[b], self.reg[b + 4]
            st['cnt'] = (st['cnt'] - 1) & 0xFF
            st['do'] = 1 if st['cnt'] & 0x80 else 0
            self.advance(4)
            nc = self._tab(bank, st['p'])
            self.advance(4)
            self.dma_counter += 8
            if st['cnt'] & 0x7F == 0:
                st['cnt'] = nc
                st['p'] = (st['p'] + 1) & 0xFFFF
                if ctl & 0x40:
                    last = not (act & ~((1 << (ch + 1)) - 1))
                    if nc == 0 and last:
                        self.advance(8)
                        st['ia'] = self._tab(bank, st['p']) << 8
                        st['p'] = (st['p'] + 1) & 0xFFFF
                        self.dma_counter += 8
                    else:
                        self.advance(16)
                        st['ia'] = self._tab(bank, st['p']) | self._tab(bank, st['p'] + 1) << 8
                        st['p'] = (st['p'] + 2) & 0xFFFF
                        self.dma_counter += 16
                if nc == 0:
                    self.stopped |= 1 << ch
                st['do'] = 1
        if sync:
            self.sync_end()
        return True

    def _dma(self, ch):
        # 자료는 쓰는 순간 옮기고(롬·WRAM 만 읽음), 시간은 다음다음 주기 시작에 센다
        b = 0x4300 + ch * 16
        self.dma_active.append(self.reg[b + 5] | self.reg[b + 6] << 8 or 0x10000)
        self.dma_pending = self.start_delay = True
        self.quiet = True
        try:
            _Cpu._dma(self, ch)
        finally:
            self.quiet = False

    # --- 메모리 ---
    def read(self, a):
        if self.quiet:
            return _Cpu.read(self, a)
        self.cycle(self.speed(a))
        lo = ((a >> 16) & 0x7F) < 0x40
        r = a & 0xFFFF
        if lo and r == 0x4212:
            # 값은 접근 끝 4 주기 앞에서 정해진다(SnesMemoryManager::Read)
            t, h = self.t - 4, self.h - 4
            act = self.auto_start + 128 <= t < self.auto_start + 34 * 128
            return (0x80 if self.v >= VBLANK else 0) | (0 if 4 <= h <= 274 * 4 else 0x40) | (1 if act else 0)
        if lo and r == 0x4210:
            return 0x02
        if lo and 0x2140 <= r <= 0x2143 and self.apu is not None:
            ts, vs = self.apu[r & 3]
            i = bisect.bisect_right(ts, self.t) - 1
            if i < 0 or ts[i] != self.t:
                self.apu_miss += 1
            return vs[i] if i >= 0 else 0
        if self.pad and lo and r in (0x4218, 0x4219):
            v = self.pad(self.nframe)
            return v & 0xFF if r == 0x4218 else v >> 8
        return _Cpu.read(self, a)

    def write(self, a, v):
        if not self.quiet:
            self.cycle(self.speed(a))
        _Cpu.write(self, a, v)

    def idle(self):
        self.cycle(6)

    def idle_or_read(self):
        if not self.irq_lock and (self.nmi_cnt == 1 or self.need_nmi):
            self.read(self.pbr << 16 | self.pc)
        else:
            self.idle()

    def opb(self):
        v = self.read(self.pbr << 16 | self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def opw(self):
        lo = self.opb()
        return lo | self.opb() << 8

    def opl(self):
        lo = self.opw()
        return lo | self.opb() << 16

    def rd(self, a):
        return self.read(a & self._mask)

    def rdw(self, a):
        lo = self.rd(a)
        return lo | self.rd(a + 1) << 8

    def wr(self, a, v):
        self.write(a & self._mask, v & 0xFF)

    def wrw(self, a, v):
        self.wr(a, v)
        self.wr(a + 1, v >> 8)

    def wrw_rmw(self, a, v):
        self.wr(a + 1, v >> 8)
        self.wr(a, v)

    def push8(self, v):
        self.write(self.s, v & 0xFF)
        self.s = (self.s - 1) & 0xFFFF

    def pull8(self):
        self.s = (self.s + 1) & 0xFFFF
        return self.read(self.s)

    def pushw(self, v):
        self.push8(v >> 8)
        self.push8(v)

    def pullw(self):
        lo = self.pull8()
        return lo | self.pull8() << 8

    # --- 명령 ---
    def nmi(self):
        self.nframe += 1
        self.nmis.append(self.t)
        self.read(self.pbr << 16 | self.pc)
        self.idle()
        self.push8(self.pbr)
        self.pushw(self.pc)
        self.push8(self.p)
        self.p = (self.p | I) & ~D
        self.pbr = 0
        self._mask = 0xFFFFFF
        self.pc = self.rdw(0x00FFEA)
        self.in_nmi = True

    def step(self):
        full = (self.pbr << 16) | self.pc
        h = self.hooks.get(full)
        if h is not None and h(self):
            return
        self.steps += 1
        self._imm = False
        self._mask = 0xFFFFFF
        op = self.opb()
        _OPS[op](self)
        if self.need_nmi:
            self.need_nmi = False
            self.nmi()

    def setnz8(self, v):
        self.p = (self.p & 0x7D) | (v & 0x80) | (0 if v & 0xFF else 2)

    def setnz16(self, v):
        self.p = (self.p & 0x7D) | ((v >> 8) & 0x80) | (0 if v & 0xFFFF else 2)

    def setps(self, v):
        self.p = v & 0xFF
        if self.p & X:
            self.x &= 0xFF
            self.y &= 0xFF

    def byte(self):
        return self._op & 0xFF if self._imm else self.rd(self._op)

    def word(self):
        return self._op & 0xFFFF if self._imm else self.rdw(self._op)


# --- 주소 꼴 (SnesCpu::AddrMode_*) ---
def _da(c, a):
    return (c.dbr << 16 | (a & 0xFFFF)) & 0xFFFFFF


def _dir_byte(c):
    v = c.opb()
    if c.d & 0xFF:
        c.idle()
    return v


def m_abs(c):
    c._op = _da(c, c.opw())


def m_absx(write):
    def f(c):
        base = _da(c, c.opw())
        c._op = (base + c.x) & 0xFFFFFF
        if write or not (c.p & X) or (c._op & 0xFF00) != (base & 0xFF00):
            c.idle()
    return f


def m_absy(write):
    def f(c):
        base = _da(c, c.opw())
        c._op = (base + c.y) & 0xFFFFFF
        if write or not (c.p & X) or (c._op & 0xFF00) != (base & 0xFF00):
            c.idle()
    return f


def m_absl(c):
    c._op = c.opl()


def m_abslx(c):
    c._op = (c.opl() + c.x) & 0xFFFFFF


def m_abs_jmp(c):
    c._op = c.pbr << 16 | c.opw()


def m_absind(c):
    a = c.opw()
    lo = c.read(a)
    c._op = lo | c.read((a + 1) & 0xFFFF) << 8


def m_absindl(c):
    a = c.opw()
    b1 = c.read(a)
    b2 = c.read((a + 1) & 0xFFFF)
    c._op = b1 | b2 << 8 | c.read((a + 2) & 0xFFFF) << 16


def m_dir(c):
    c._mask = 0xFFFF
    c._op = (c.d + _dir_byte(c)) & 0xFFFF


def m_dirx(c):
    c._mask = 0xFFFF
    c._op = (c.d + _dir_byte(c) + c.x) & 0xFFFF
    c.idle()


def m_diry(c):
    c._mask = 0xFFFF
    c._op = (c.d + _dir_byte(c) + c.y) & 0xFFFF
    c.idle()


def _dind(c, off):
    lo = c.read((c.d + off) & 0xFFFF)
    return lo | c.read((c.d + off + 1) & 0xFFFF) << 8


def m_dind(c):
    c._op = _da(c, _dind(c, _dir_byte(c)))


def m_dxind(c):
    b = _dir_byte(c)
    c.idle()
    c._op = _da(c, _dind(c, b + c.x))


def m_dindy(write):
    def f(c):
        base = _da(c, _dind(c, _dir_byte(c)))
        c._op = (base + c.y) & 0xFFFFFF
        if write or not (c.p & X) or (c._op & 0xFF00) != (base & 0xFF00):
            c.idle()
    return f


def _dindl(c, off):
    b1 = c.read((c.d + off) & 0xFFFF)
    b2 = c.read((c.d + off + 1) & 0xFFFF)
    return b1 | b2 << 8 | c.read((c.d + off + 2) & 0xFFFF) << 16


def m_dindl(c):
    c._op = _dindl(c, _dir_byte(c))


def m_dindly(c):
    c._op = (_dindl(c, _dir_byte(c)) + c.y) & 0xFFFFFF


def m_imm8(c):
    c._imm = True
    c._op = c.opb()


def m_imm16(c):
    c._imm = True
    c._op = c.opw()


def m_immx(c):
    c._imm = True
    c._op = c.opb() if c.p & X else c.opw()


def m_immm(c):
    c._imm = True
    c._op = c.opb() if c.p & M else c.opw()


def m_imp(c):
    c.idle_or_read()


def m_rel(c):
    c._op = c.opb()


def m_rell(c):
    c._op = c.opw()
    c.idle()


def m_sr(c):
    c._op = (c.opb() + c.s) & 0xFFFF
    c.idle()


def m_sriy(c):
    a = (c.opb() + c.s) & 0xFFFF
    c.idle()
    lo = c.read(a)
    hi = c.read((a + 1) & 0xFFFF)
    c._op = (_da(c, lo | hi << 8) + c.y) & 0xFFFFFF
    c.idle()


# --- 명령 (SnesCpu::*) ---
def _add(c, v, m8):
    a = c.a
    if m8:
        if c.p & D:
            r = (a & 0x0F) + (v & 0x0F) + (c.p & C)
            if r > 0x09:
                r += 0x06
            r = (a & 0xF0) + (v & 0xF0) + (0x10 if r > 0x0F else 0) + (r & 0x0F)
        else:
            r = (a & 0xFF) + v + (c.p & C)
        ov = ~(a ^ v) & (a ^ r) & 0x80
        if c.p & D and r > 0x9F:
            r += 0x60
        c.p = (c.p & ~(C | N | Z | V)) | (V if ov else 0) | (C if r > 0xFF else 0)
        c.setnz8(r & 0xFF)
        c.a = (a & 0xFF00) | (r & 0xFF)
    else:
        if c.p & D:
            r = (a & 0x0F) + (v & 0x0F) + (c.p & C)
            if r > 0x09:
                r += 0x06
            r = (a & 0xF0) + (v & 0xF0) + (0x10 if r > 0x0F else 0) + (r & 0x0F)
            if r > 0x9F:
                r += 0x60
            r = (a & 0xF00) + (v & 0xF00) + (0x100 if r > 0xFF else 0) + (r & 0xFF)
            if r > 0x9FF:
                r += 0x600
            r = (a & 0xF000) + (v & 0xF000) + (0x1000 if r > 0xFFF else 0) + (r & 0xFFF)
        else:
            r = a + v + (c.p & C)
        ov = ~(a ^ v) & (a ^ r) & 0x8000
        if c.p & D and r > 0x9FFF:
            r += 0x6000
        c.p = (c.p & ~(C | N | Z | V)) | (V if ov else 0) | (C if r > 0xFFFF else 0)
        c.setnz16(r & 0xFFFF)
        c.a = r & 0xFFFF


def _sub(c, v, m8):
    a = c.a
    if m8:
        if c.p & D:
            r = (a & 0x0F) + (v & 0x0F) + (c.p & C)
            if r <= 0x0F:
                r -= 0x06
            r = (a & 0xF0) + (v & 0xF0) + (0x10 if r > 0x0F else 0) + (r & 0x0F)
        else:
            r = (a & 0xFF) + v + (c.p & C)
        ov = ~(a ^ v) & (a ^ r) & 0x80
        if c.p & D and r <= 0xFF:
            r -= 0x60
        c.p = (c.p & ~(C | N | Z | V)) | (V if ov else 0) | (C if r > 0xFF else 0)
        c.setnz8(r & 0xFF)
        c.a = (a & 0xFF00) | (r & 0xFF)
    else:
        if c.p & D:
            r = (a & 0x0F) + (v & 0x0F) + (c.p & C)
            if r <= 0x0F:
                r -= 0x06
            r = (a & 0xF0) + (v & 0xF0) + (0x10 if r > 0x0F else 0) + (r & 0x0F)
            if r <= 0xFF:
                r -= 0x60
            r = (a & 0xF00) + (v & 0xF00) + (0x100 if r > 0xFF else 0) + (r & 0xFF)
            if r <= 0xFFF:
                r -= 0x600
            r = (a & 0xF000) + (v & 0xF000) + (0x1000 if r > 0xFFF else 0) + (r & 0xFFF)
        else:
            r = a + v + (c.p & C)
        ov = ~(a ^ v) & (a ^ r) & 0x8000
        if c.p & D and r <= 0xFFFF:
            r -= 0x6000
        c.p = (c.p & ~(C | N | Z | V)) | (V if ov else 0) | (C if r > 0xFFFF else 0)
        c.setnz16(r & 0xFFFF)
        c.a = r & 0xFFFF


def i_adc(c):
    if c.p & M:
        _add(c, c.byte(), True)
    else:
        _add(c, c.word(), False)


def i_sbc(c):
    if c.p & M:
        _sub(c, ~c.byte() & 0xFF, True)
    else:
        _sub(c, ~c.word() & 0xFFFF, False)


def _logic(f):
    def g(c):
        if c.p & M:
            r = f(c.a & 0xFF, c.byte()) & 0xFF
            c.setnz8(r)
            c.a = (c.a & 0xFF00) | r
        else:
            r = f(c.a, c.word()) & 0xFFFF
            c.setnz16(r)
            c.a = r
    return g


i_and = _logic(lambda a, b: a & b)
i_eor = _logic(lambda a, b: a ^ b)
i_ora = _logic(lambda a, b: a | b)


def _branch(cond):
    def f(c):
        if cond(c):
            off = c._op - 256 if c._op & 0x80 else c._op
            c.idle()
            c.pc = (c.pc + off) & 0xFFFF
    return f


def i_brl(c):
    c.pc = (c.pc + c._op) & 0xFFFF


def _flag(set_, bit):
    def f(c):
        c.p = (c.p | bit) if set_ else (c.p & ~bit)
    return f


def i_rep(c):
    c.idle()
    c.p &= ~c._op & 0xFF


def i_sep(c):
    c.idle()
    c.setps(c.p | c._op)


def _incdec_reg(name, d):
    def f(c):
        if c.p & X:
            v = (getattr(c, name) + d) & 0xFF
            c.setnz8(v)
        else:
            v = (getattr(c, name) + d) & 0xFFFF
            c.setnz16(v)
        setattr(c, name, v)
    return f


def _rmw(fn8, fn16):
    def f(c):
        if c.p & M:
            v = c.byte()
            c.idle()
            c.wr(c._op, fn8(c, v))
        else:
            v = c.word()
            c.idle()
            c.wrw_rmw(c._op, fn16(c, v))
    return f


def _accop(fn8, fn16):
    def f(c):
        if c.p & M:
            c.a = (c.a & 0xFF00) | fn8(c, c.a & 0xFF)
        else:
            c.a = fn16(c, c.a)
    return f


def _inc8(c, v):
    r = (v + 1) & 0xFF
    c.setnz8(r)
    return r


def _dec8(c, v):
    r = (v - 1) & 0xFF
    c.setnz8(r)
    return r


def _inc16(c, v):
    r = (v + 1) & 0xFFFF
    c.setnz16(r)
    return r


def _dec16(c, v):
    r = (v - 1) & 0xFFFF
    c.setnz16(r)
    return r


def _shift(bits, kind):
    top = 1 << (bits - 1)
    mask = (1 << bits) - 1

    def f(c, v):
        if kind == 'asl':
            r, cy = v << 1, v & top
        elif kind == 'rol':
            r, cy = v << 1 | (c.p & C), v & top
        elif kind == 'lsr':
            r, cy = v >> 1, v & 1
        else:
            r, cy = v >> 1 | ((c.p & C) << (bits - 1)), v & 1
        r &= mask
        c.p = (c.p & ~C) | (C if cy else 0)
        if bits == 8:
            c.setnz8(r)
        else:
            c.setnz16(r)
        return r
    return f


def _cmp(name, flag):
    def f(c):
        reg = getattr(c, name)
        if c.p & flag:
            v = c.byte()
            c.p = (c.p & ~C) | (C if (reg & 0xFF) >= v else 0)
            c.setnz8(((reg & 0xFF) - v) & 0xFF)
        else:
            v = c.word()
            c.p = (c.p & ~C) | (C if reg >= v else 0)
            c.setnz16((reg - v) & 0xFFFF)
    return f


def i_jml(c):
    c.pbr = (c._op >> 16) & 0xFF
    c.pc = c._op & 0xFFFF


def i_jmp(c):
    c.pc = c._op & 0xFFFF


def i_jsl(c):
    b1 = c.opb()
    b2 = c.opb()
    c.push8(c.pbr)
    c.idle()
    b3 = c.opb()
    c.pushw((c.pc - 1) & 0xFFFF)
    c.pbr = b3
    c.pc = b1 | b2 << 8


def i_jsr(c):
    c.pushw((c.pc - 1) & 0xFFFF)
    c.pc = c._op & 0xFFFF


def i_jmp_xind(c):
    base = (c.opw() + c.x) & 0xFFFF
    c.idle()
    lo = c.read(c.pbr << 16 | base)
    hi = c.read(c.pbr << 16 | ((base + 1) & 0xFFFF))
    c.pc = lo | hi << 8


def i_jsr_xind(c):
    lo = c.opb()
    c.pushw(c.pc)
    hi = c.opb()
    base = ((lo | hi << 8) + c.x) & 0xFFFF
    c.idle()
    lo = c.read(c.pbr << 16 | base)
    hi = c.read(c.pbr << 16 | ((base + 1) & 0xFFFF))
    c.pc = lo | hi << 8


def i_rti(c):
    c.idle()
    c.idle()
    c.setps(c.pull8())
    c.pc = c.pullw()
    c.pbr = c.pull8()
    c.in_nmi = False


def i_rtl(c):
    c.idle()
    c.idle()
    c.pc = (c.pullw() + 1) & 0xFFFF
    c.pbr = c.pull8()


def i_rts(c):
    c.idle()
    c.idle()
    c.pc = c.pullw()
    c.idle()
    c.pc = (c.pc + 1) & 0xFFFF


def _brk(vec):
    def f(c):
        c.push8(c.pbr)
        c.pushw(c.pc)
        c.push8(c.p)
        c.p = (c.p | I) & ~D
        c.pbr = 0
        c._mask = 0xFFFFFF
        c.pc = c.rdw(vec)
    return f


def _move(step):
    def f(c):
        c.dbr = c._op & 0xFF
        src = (c._op << 8) & 0xFF0000
        v = c.read(src | c.x)
        c.write(c.dbr << 16 | c.y, v)
        c.idle()
        c.idle()
        mask = 0xFF if c.p & X else 0xFFFF
        c.x = (c.x + step) & mask
        c.y = (c.y + step) & mask
        c.a = (c.a - 1) & 0xFFFF
        if c.a != 0xFFFF:
            c.pc = (c.pc - 3) & 0xFFFF
    return f


def i_pea(c):
    c.pushw(c._op)


def i_pei(c):
    c.pushw(c.rdw(c._op))


def i_per(c):
    c.pushw((c._op + c.pc) & 0xFFFF)


def i_phb(c):
    c.idle()
    c.push8(c.dbr)


def i_phd(c):
    c.idle()
    c.pushw(c.d)


def i_phk(c):
    c.idle()
    c.push8(c.pbr)


def i_php(c):
    c.idle()
    c.push8(c.p)


def i_plb(c):
    c.idle()
    c.idle()
    c.dbr = c.pull8()
    c.setnz8(c.dbr)


def i_pld(c):
    c.idle()
    c.idle()
    c.d = c.pullw()
    c.setnz16(c.d)


def i_plp(c):
    c.idle()
    c.idle()
    c.setps(c.pull8())


def _push_reg(name, flag):
    def f(c):
        c.idle()
        v = getattr(c, name)
        if c.p & flag:
            c.push8(v)
        else:
            c.pushw(v)
    return f


def _pull_reg(name, flag):
    def f(c):
        c.idle()
        c.idle()
        if c.p & flag:
            v = c.pull8()
            c.setnz8(v)
            setattr(c, name, (getattr(c, name) & 0xFF00) | v)
        else:
            v = c.pullw()
            c.setnz16(v)
            setattr(c, name, v)
    return f


def _load(name, flag):
    def f(c):
        if c.p & flag:
            v = c.byte()
            c.setnz8(v)
            setattr(c, name, (getattr(c, name) & 0xFF00) | v)
        else:
            v = c.word()
            c.setnz16(v)
            setattr(c, name, v)
    return f


def _store(name, flag):
    def f(c):
        v = getattr(c, name) if name else 0
        if c.p & flag:
            c.wr(c._op, v)
        else:
            c.wrw(c._op, v)
    return f


def i_bit(c):
    if c.p & M:
        v = c.byte()
        if c._imm:
            c.p = (c.p & ~Z) | (0 if c.a & v & 0xFF else Z)
        else:
            c.p = (c.p & ~(Z | V | N)) | (0 if c.a & v & 0xFF else Z) | (v & 0xC0)
    else:
        v = c.word()
        if c._imm:
            c.p = (c.p & ~Z) | (0 if c.a & v else Z)
        else:
            c.p = (c.p & ~(Z | V | N)) | (0 if c.a & v else Z) | ((v >> 8) & 0xC0)


def _tsb_trb(setb):
    def f(c):
        if c.p & M:
            v = c.byte()
            c.p = (c.p & ~Z) | (0 if c.a & v & 0xFF else Z)
            c.idle()
            c.wr(c._op, (v | c.a) & 0xFF if setb else v & ~c.a & 0xFF)
        else:
            v = c.word()
            c.p = (c.p & ~Z) | (0 if c.a & v else Z)
            c.idle()
            c.wrw_rmw(c._op, (v | c.a) & 0xFFFF if setb else v & ~c.a & 0xFFFF)
    return f


def _xfer(src, dst, flag):
    def f(c):
        v = getattr(c, src)
        if flag is None or not (c.p & flag):
            v &= 0xFFFF
            c.setnz16(v)
            setattr(c, dst, v)
        else:
            v &= 0xFF
            c.setnz8(v)
            setattr(c, dst, (getattr(c, dst) & 0xFF00) | v)
    return f


def i_tcs(c):
    c.s = c.a & 0xFFFF


def i_txs(c):
    c.s = c.x & 0xFFFF


def i_xba(c):
    c.idle()
    c.a = ((c.a & 0xFF) << 8) | (c.a >> 8)
    c.setnz8(c.a & 0xFF)


def i_xce(c):
    if c.p & C:
        raise NotImplementedError('emulation mode')


def i_nop(c):
    pass


def i_stp(c):
    raise NotImplementedError('STP/WAI')


_OPS = [None] * 256


def _op(code, mode, fn):
    if mode is None:
        _OPS[code] = fn
    else:
        def f(c):
            mode(c)
            fn(c)
        _OPS[code] = f


_A = {'adc': i_adc, 'sbc': i_sbc, 'and': i_and, 'eor': i_eor, 'ora': i_ora, 'cmp': _cmp('a', M),
      'lda': _load('a', M), 'sta': _store('a', M)}
for _base, _name in ((0x00, 'ora'), (0x20, 'and'), (0x40, 'eor'), (0x60, 'adc'), (0x80, 'sta'), (0xA0, 'lda'),
                     (0xC0, 'cmp'), (0xE0, 'sbc')):
    _fn, _w = _A[_name], _name == 'sta'
    _op(_base + 0x01, m_dxind, _fn)
    _op(_base + 0x03, m_sr, _fn)
    _op(_base + 0x05, m_dir, _fn)
    _op(_base + 0x07, m_dindl, _fn)
    if not _w:
        _op(_base + 0x09, m_immm, _fn)
    _op(_base + 0x0D, m_abs, _fn)
    _op(_base + 0x0F, m_absl, _fn)
    _op(_base + 0x11, m_dindy(_w), _fn)
    _op(_base + 0x12, m_dind, _fn)
    _op(_base + 0x13, m_sriy, _fn)
    _op(_base + 0x15, m_dirx, _fn)
    _op(_base + 0x17, m_dindly, _fn)
    _op(_base + 0x19, m_absy(_w), _fn)
    _op(_base + 0x1D, m_absx(_w), _fn)
    _op(_base + 0x1F, m_abslx, _fn)

for _base, _kind in ((0x00, 'asl'), (0x20, 'rol'), (0x40, 'lsr'), (0x60, 'ror')):
    _f8, _f16 = _shift(8, _kind), _shift(16, _kind)
    _op(_base + 0x06, m_dir, _rmw(_f8, _f16))
    _op(_base + 0x0E, m_abs, _rmw(_f8, _f16))
    _op(_base + 0x16, m_dirx, _rmw(_f8, _f16))
    _op(_base + 0x1E, m_absx(True), _rmw(_f8, _f16))
    _op(_base + 0x0A, m_imp, _accop(_f8, _f16))

_op(0x00, m_imm8, _brk(0xFFE6))
_op(0x02, m_imm8, _brk(0xFFE4))
_op(0x04, m_dir, _tsb_trb(True))
_op(0x0C, m_abs, _tsb_trb(True))
_op(0x14, m_dir, _tsb_trb(False))
_op(0x1C, m_abs, _tsb_trb(False))
_op(0x08, None, i_php)
_op(0x0B, None, i_phd)
_op(0x10, m_rel, _branch(lambda c: not c.p & N))
_op(0x30, m_rel, _branch(lambda c: c.p & N))
_op(0x50, m_rel, _branch(lambda c: not c.p & V))
_op(0x70, m_rel, _branch(lambda c: c.p & V))
_op(0x80, m_rel, _branch(lambda c: True))
_op(0x90, m_rel, _branch(lambda c: not c.p & C))
_op(0xB0, m_rel, _branch(lambda c: c.p & C))
_op(0xD0, m_rel, _branch(lambda c: not c.p & Z))
_op(0xF0, m_rel, _branch(lambda c: c.p & Z))
_op(0x82, m_rell, i_brl)
_op(0x18, m_imp, _flag(False, C))
_op(0x38, m_imp, _flag(True, C))
_op(0x58, m_imp, _flag(False, I))
_op(0x78, m_imp, _flag(True, I))
_op(0xB8, m_imp, _flag(False, V))
_op(0xD8, m_imp, _flag(False, D))
_op(0xF8, m_imp, _flag(True, D))
_op(0x1A, m_imp, _accop(_inc8, _inc16))
_op(0x3A, m_imp, _accop(_dec8, _dec16))
_op(0x1B, m_imp, i_tcs)
_op(0x5B, m_imp, _xfer('a', 'd', None))
_op(0x7B, m_imp, _xfer('d', 'a', None))
_op(0x3B, m_imp, _xfer('s', 'a', None))
_op(0x20, m_abs_jmp, lambda c: (c.idle(), i_jsr(c)))
_op(0x22, None, i_jsl)
_op(0x24, m_dir, i_bit)
_op(0x2C, m_abs, i_bit)
_op(0x34, m_dirx, i_bit)
_op(0x3C, m_absx(False), i_bit)
_op(0x89, m_immm, i_bit)
_op(0x28, None, i_plp)
_op(0x2B, None, i_pld)
_op(0x40, None, i_rti)
_op(0x42, m_imm8, i_nop)
_op(0x44, m_imm16, _move(-1))
_op(0x54, m_imm16, _move(1))
_op(0x48, None, _push_reg('a', M))
_op(0xDA, None, _push_reg('x', X))
_op(0x5A, None, _push_reg('y', X))
_op(0x68, None, _pull_reg('a', M))
_op(0xFA, None, _pull_reg('x', X))
_op(0x7A, None, _pull_reg('y', X))
_op(0x4B, None, i_phk)
_op(0x8B, None, i_phb)
_op(0xAB, None, i_plb)
_op(0x4C, m_abs_jmp, i_jmp)
_op(0x5C, m_absl, i_jml)
_op(0x60, None, i_rts)
_op(0x62, m_rell, i_per)
_op(0x6B, None, i_rtl)
_op(0x6C, m_absind, i_jmp)
_op(0x7C, None, i_jmp_xind)
_op(0xDC, m_absindl, i_jml)
_op(0xFC, None, i_jsr_xind)
_op(0x64, m_dir, _store(None, M))
_op(0x74, m_dirx, _store(None, M))
_op(0x9C, m_abs, _store(None, M))
_op(0x9E, m_absx(True), _store(None, M))
_op(0x84, m_dir, _store('y', X))
_op(0x8C, m_abs, _store('y', X))
_op(0x94, m_dirx, _store('y', X))
_op(0x86, m_dir, _store('x', X))
_op(0x8E, m_abs, _store('x', X))
_op(0x96, m_diry, _store('x', X))
_op(0x88, m_imp, _incdec_reg('y', -1))
_op(0xC8, m_imp, _incdec_reg('y', 1))
_op(0xCA, m_imp, _incdec_reg('x', -1))
_op(0xE8, m_imp, _incdec_reg('x', 1))
_op(0x8A, m_imp, _xfer('x', 'a', M))
_op(0x98, m_imp, _xfer('y', 'a', M))
_op(0xA8, m_imp, _xfer('a', 'y', X))
_op(0xAA, m_imp, _xfer('a', 'x', X))
_op(0x9B, m_imp, _xfer('x', 'y', X))
_op(0xBB, m_imp, _xfer('y', 'x', X))
_op(0xBA, m_imp, _xfer('s', 'x', X))
_op(0x9A, m_imp, i_txs)
_op(0xA0, m_immx, _load('y', X))
_op(0xA4, m_dir, _load('y', X))
_op(0xAC, m_abs, _load('y', X))
_op(0xB4, m_dirx, _load('y', X))
_op(0xBC, m_absx(False), _load('y', X))
_op(0xA2, m_immx, _load('x', X))
_op(0xA6, m_dir, _load('x', X))
_op(0xAE, m_abs, _load('x', X))
_op(0xB6, m_diry, _load('x', X))
_op(0xBE, m_absy(False), _load('x', X))
_op(0xC0, m_immx, _cmp('y', X))
_op(0xC4, m_dir, _cmp('y', X))
_op(0xCC, m_abs, _cmp('y', X))
_op(0xE0, m_immx, _cmp('x', X))
_op(0xE4, m_dir, _cmp('x', X))
_op(0xEC, m_abs, _cmp('x', X))
_op(0xC2, m_imm8, i_rep)
_op(0xE2, m_imm8, i_sep)
_op(0xC6, m_dir, _rmw(_dec8, _dec16))
_op(0xCE, m_abs, _rmw(_dec8, _dec16))
_op(0xD6, m_dirx, _rmw(_dec8, _dec16))
_op(0xDE, m_absx(True), _rmw(_dec8, _dec16))
_op(0xE6, m_dir, _rmw(_inc8, _inc16))
_op(0xEE, m_abs, _rmw(_inc8, _inc16))
_op(0xF6, m_dirx, _rmw(_inc8, _inc16))
_op(0xFE, m_absx(True), _rmw(_inc8, _inc16))
_op(0xCB, None, i_stp)
_op(0xDB, m_imp, i_stp)
_op(0xD4, m_dir, i_pei)
_op(0xEA, m_imp, i_nop)
_op(0xEB, m_imp, i_xba)
_op(0xF4, m_imm16, i_pea)
_op(0xFB, m_imp, i_xce)

assert all(_OPS), [hex(i) for i, f in enumerate(_OPS) if f is None]
