"""DQ4(FC) 루틴을 롬만으로 따라가 보는 작은 6502 해석기.

화면을 그리는 루틴이 어떤 부품 함수를 어떤 인자로 부르는지 롬에서 바로 뽑으려고 쓴다. PPU·APU·매퍼 쓰기는 버리고,
$2002 는 늘 vblank(bit7)를 돌려준다. 뱅크는 `$FF91`(A = 뱅크, `$0507` 에도 적음)만 따르고, `$C000-$FFFF` 는 그 256KB 절반의 마지막 뱅크다.
BRK 는 dq4bank.call 로 풀어 일반 호출이면 그 뱅크 함수를 부르고, 소리·메시지 같은 다른 형식은 건너뛴다.
프레임을 기다리는 고정 뱅크 함수는 stubs 로 바로 돌아오게 한다(NMI 가 없으므로 기다리면 끝나지 않음).
"""
import dq4bank
from kr_patch.fc.dis6502 import OPS

SIZE = {'imp': 0, 'acc': 0, 'imm': 1, 'zp': 1, 'zpx': 1, 'zpy': 1, 'izx': 1, 'izy': 1, 'rel': 1,
        'abs': 2, 'abx': 2, 'aby': 2, 'ind': 2}


class Halt(Exception):
    pass


class CPU:
    def __init__(self, prg, bank, ram=None, wram=None):
        self.prg, self.bank = prg, bank
        self.ram = bytearray(ram or bytes(0x800))
        self.wram = bytearray(wram or bytes(0x2000))
        self.ram[0x507] = bank
        self.a = self.x = self.y = 0
        self.s = 0xFF
        self.c = self.z = self.n = self.v = 0
        self.pc = 0
        self.hooks = {}     # CPU 주소 → fn(cpu): 그 주소를 실행하기 직전에 부름(뱅크 무관)
        self.stubs = set()  # 이 주소에 닿으면 바로 RTS(JSR·JMP 모두)
        self.steps = 0
        self.skipped = []   # 건너뛴 BRK [(주소, b1, b2)]

    # --- 메모리 ---
    def fixed(self):
        return (self.bank & 0x10) | 0x0F

    def rom(self, addr):
        b = self.fixed() if addr >= 0xC000 else self.bank
        return self.prg[b * 0x4000 + (addr & 0x3FFF)]

    def rd(self, addr):
        addr &= 0xFFFF
        if addr < 0x2000:
            return self.ram[addr & 0x7FF]
        if addr < 0x6000:
            return 0x80 if addr == 0x2002 else 0
        if addr < 0x8000:
            return self.wram[addr - 0x6000]
        return self.rom(addr)

    def wr(self, addr, v):
        addr &= 0xFFFF
        if addr < 0x2000:
            self.ram[addr & 0x7FF] = v & 0xFF
        elif 0x6000 <= addr < 0x8000:
            self.wram[addr - 0x6000] = v & 0xFF

    def rd16(self, addr):
        return self.rd(addr) | self.rd(addr + 1) << 8

    def push(self, v):
        self.wr(0x100 | self.s, v)
        self.s = (self.s - 1) & 0xFF

    def pull(self):
        self.s = (self.s + 1) & 0xFF
        return self.rd(0x100 | self.s)

    # --- 플래그 ---
    def nz(self, v):
        v &= 0xFF
        self.n, self.z = v >> 7, int(v == 0)
        return v

    def p(self):
        return self.n << 7 | self.v << 6 | 0x30 | self.z << 1 | self.c

    def setp(self, v):
        self.n, self.v, self.z, self.c = v >> 7 & 1, v >> 6 & 1, v >> 1 & 1, v & 1

    # --- 실행 ---
    def call(self, addr, limit=2_000_000):
        """addr 를 JSR 처럼 불러 RTS 로 돌아올 때까지 실행한다."""
        base = self.s
        self.push(0xFF)
        self.push(0xFE)    # 돌아올 자리 $FFFF: 여기 닿으면 끝
        self.pc = addr
        while True:
            if self.pc == 0xFFFF and self.s == base:
                return
            self.steps += 1
            if self.steps > limit:
                raise Halt(f'{self.bank:02X}:{self.pc:04X} 에서 {limit} 명령을 넘음')
            self.exec1()

    def operand(self, md):
        pc = self.pc
        if md in ('imm', 'rel'):
            return pc + 1
        b = self.rd(pc + 1)
        w = b | self.rd(pc + 2) << 8
        if md == 'zp':
            return b
        if md == 'zpx':
            return (b + self.x) & 0xFF
        if md == 'zpy':
            return (b + self.y) & 0xFF
        if md == 'abs':
            return w
        if md == 'abx':
            return (w + self.x) & 0xFFFF
        if md == 'aby':
            return (w + self.y) & 0xFFFF
        if md == 'izx':
            z = (b + self.x) & 0xFF
            return self.rd(z) | self.rd((z + 1) & 0xFF) << 8
        if md == 'izy':
            return ((self.rd(b) | self.rd((b + 1) & 0xFF) << 8) + self.y) & 0xFFFF
        if md == 'ind':
            return self.rd(w) | self.rd((w & 0xFF00) | ((w + 1) & 0xFF)) << 8
        return None

    def brk(self):
        site = self.pc
        c = dq4bank.call(self.prg, site, self.bank)
        if c['kind'] == 'call':
            saved = self.bank
            self.bank = c['bank']
            ret = self.pc
            self.call(c['target'])
            self.bank = saved
            self.pc = ret + 3
        else:
            self.skipped.append((site, c['b1'], c['b2']))
            n = c.get('length') or (4 if c['kind'].startswith('flag') else 3)
            self.pc = site + n

    def exec1(self):
        pc = self.pc
        if pc == 0xFF91:
            # 뱅크 전환: $0507 에 적고 MMC1 직렬 쓰기 대신 바로 바꾼 뒤 RTS
            self.wr(0x507, self.a)
            self.bank = self.a & 0x1F
            lo = self.pull()
            self.pc = ((self.pull() << 8 | lo) + 1) & 0xFFFF
            return
        if pc in self.hooks:
            self.hooks[pc](self)
        if pc in self.stubs:
            lo = self.pull()
            self.pc = ((self.pull() << 8 | lo) + 1) & 0xFFFF
            return
        op = self.rd(pc)
        if op not in OPS:
            raise Halt(f'{self.bank:02X}:{pc:04X} 공식 명령이 아님({op:02X})')
        mn, md = OPS[op]
        ea = self.operand(md)
        nxt = (pc + 1 + SIZE[md]) & 0xFFFF
        self.pc = nxt

        def val():
            return self.a if md == 'acc' else self.rd(ea)

        def put(v):
            if md == 'acc':
                self.a = v & 0xFF
            else:
                self.wr(ea, v)
        if mn == 'BRK':
            self.pc = pc
            self.brk()
        elif mn in ('LDA', 'LDX', 'LDY'):
            setattr(self, mn[2].lower(), self.nz(self.rd(ea)))
        elif mn in ('STA', 'STX', 'STY'):
            self.wr(ea, getattr(self, mn[2].lower()))
        elif mn in ('TAX', 'TAY', 'TXA', 'TYA'):
            setattr(self, mn[2].lower(), self.nz(getattr(self, mn[1].lower())))
        elif mn == 'TSX':
            self.x = self.nz(self.s)
        elif mn == 'TXS':
            self.s = self.x
        elif mn in ('INX', 'INY', 'DEX', 'DEY'):
            r = mn[2].lower()
            setattr(self, r, self.nz(getattr(self, r) + (1 if mn[0] == 'I' else -1)))
        elif mn in ('INC', 'DEC'):
            self.wr(ea, self.nz(self.rd(ea) + (1 if mn == 'INC' else -1)))
        elif mn in ('AND', 'ORA', 'EOR'):
            v = self.rd(ea)
            self.a = self.nz(self.a & v if mn == 'AND' else self.a | v if mn == 'ORA' else self.a ^ v)
        elif mn in ('ADC', 'SBC'):
            v = self.rd(ea) ^ (0xFF if mn == 'SBC' else 0)
            t = self.a + v + self.c
            self.v = int(((self.a ^ t) & (v ^ t) & 0x80) != 0)
            self.c = t >> 8
            self.a = self.nz(t)
        elif mn in ('CMP', 'CPX', 'CPY'):
            r = {'CMP': self.a, 'CPX': self.x, 'CPY': self.y}[mn]
            v = self.rd(ea)
            self.c = int(r >= v)
            self.nz(r - v)
        elif mn == 'BIT':
            v = self.rd(ea)
            self.n, self.v, self.z = v >> 7, v >> 6 & 1, int(self.a & v == 0)
        elif mn in ('ASL', 'LSR', 'ROL', 'ROR'):
            v = val()
            if mn == 'ASL':
                self.c, r = v >> 7, v << 1
            elif mn == 'LSR':
                self.c, r = v & 1, v >> 1
            elif mn == 'ROL':
                r, self.c = v << 1 | self.c, v >> 7
            else:
                r, self.c = v >> 1 | self.c << 7, v & 1
            put(self.nz(r))
        elif mn[0] == 'B' and md == 'rel':
            flag = {'BPL': not self.n, 'BMI': self.n, 'BVC': not self.v, 'BVS': self.v,
                    'BCC': not self.c, 'BCS': self.c, 'BNE': not self.z, 'BEQ': self.z}[mn]
            if flag:
                d = self.rd(pc + 1)
                self.pc = (nxt + (d - 256 if d & 0x80 else d)) & 0xFFFF
        elif mn == 'JMP':
            self.pc = ea
        elif mn == 'JSR':
            r = nxt - 1
            self.push(r >> 8)
            self.push(r & 0xFF)
            self.pc = ea
        elif mn == 'RTS':
            lo = self.pull()
            self.pc = ((self.pull() << 8 | lo) + 1) & 0xFFFF
        elif mn == 'RTI':
            self.setp(self.pull())
            lo = self.pull()
            self.pc = self.pull() << 8 | lo
        elif mn == 'PHA':
            self.push(self.a)
        elif mn == 'PHP':
            self.push(self.p())
        elif mn == 'PLA':
            self.a = self.nz(self.pull())
        elif mn == 'PLP':
            self.setp(self.pull())
        elif mn in ('CLC', 'SEC'):
            self.c = int(mn == 'SEC')
        elif mn == 'CLV':
            self.v = 0
        elif mn in ('CLI', 'SEI', 'CLD', 'SED', 'NOP'):
            pass
        else:
            raise Halt(f'{mn} 미구현')
