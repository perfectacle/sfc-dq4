"""DQ4(FC) 미실행 코드 찾기. 형식과 결과는 fc/dq4/docs/dq4-debug.md.

probe/cover.lua 기록 여러 개를 합쳐, 실행된 명령에서 갈 수 있는데(분기·JMP·JSR·BRK 뱅크 호출의
대상, 조건 분기의 다른 쪽) 한 번도 실행되지 않은 코드를 따라가 덩어리로 모은다.

사용:
  python fc/dq4/tools/dq4debug.py rom/dq4.nes unrun COVER...        미실행 코드 덩어리(시작, 크기, 들어오는 곳)
  python fc/dq4/tools/dq4debug.py rom/dq4.nes find COVER...         닿는 코드(실행·미실행) 중 디버그 흔적 후보
  python fc/dq4/tools/dq4debug.py rom/dq4.nes brk COVER...          BRK 함수 표에서 아무도 부르지 않는 항목

근거: 고정 영역 $C000- 는 $0507 의 256KB 절반의 마지막 뱅크(0F/1F), BRK 형식은 dq4bank.py.
패드 읽기 0F:$C8EC 가 패드 1 을 $14, 패드 2 를 $15 에 둔다(bit0 A … bit7 오른쪽).
디버그 스위치는 고정 영역 첫 바이트 $C000(제품판 FF, 비트가 0 이면 켜짐).
"""
import sys

from kr_patch.fc import dis6502, ines

import dq4bank

BANK = 0x4000
END = {'RTS', 'RTI', 'JMP'}


def cpu(off):
    b, a = off // BANK, 0x8000 + off % BANK
    return a + 0x4000 if b & 0x0F == 0x0F else a


def offset(src_off, addr):
    """src_off 에서 본 CPU addr 의 PRG 오프셋. 고정 영역에서 $8000- 로 가면 뱅크를 모르므로 None."""
    b = src_off // BANK
    if addr >= 0xC000:
        return ((b & 0x10) | 0x0F) * BANK + (addr & 0x3FFF)
    if 0x8000 <= addr and b & 0x0F != 0x0F:
        return b * BANK + (addr & 0x3FFF)
    return None


def read_covers(paths):
    run = set()
    for p in paths:
        run.update(r[0] for r in dis6502.read_cover(open(p)))
    return run


def succ(prg, off):
    """명령 하나의 (다음 오프셋들, 끝남 여부). BRK 는 뱅크 호출 대상과 BRK+3."""
    op = dis6502.OPS.get(prg[off])
    if op is None:
        return None
    mn, md = op
    n = 1 + dis6502.SIZE[md]
    arg = int.from_bytes(prg[off + 1:off + n], 'little')
    a = cpu(off)
    out = []
    if mn == 'BRK':
        b1, b2 = prg[off + 1], prg[off + 2]
        if b2 & 7 == 7 and not b1 & 0x80:
            bank = (b2 >> 4) | (b2 & 8) << 1
            t = dq4bank.entry(prg, bank, b1)
            if 0x8000 <= t < 0xC000:
                out.append(bank * BANK + (t & 0x3FFF))
            elif t >= 0xC000:
                out.append(((bank & 0x10) | 0x0F) * BANK + (t & 0x3FFF))
        return out + [off + 3], False
    if md == 'rel':
        t = (a + 2 + (arg - 256 if arg & 0x80 else arg)) & 0xFFFF
        out.append(offset(off, t))
        return out + [off + n], False
    if mn == 'JSR':
        return [offset(off, arg), off + n], False
    if mn == 'JMP':
        return ([offset(off, arg)] if md == 'abs' else []), True
    if mn in END:
        return [], True
    return [off + n], False


def unrun(prg, run):
    """실행된 명령에서 출발해 닿는 미실행 명령 집합과 그 덩어리 목록 [(시작, 끝, 들어오는 곳들, 깨끗한지)]."""
    entries = {}
    for off in run:
        s = succ(prg, off)
        if s is None:
            continue
        for t in s[0]:
            if t is not None and t not in run and 0 <= t < len(prg):
                entries.setdefault(t, set()).add(off)
    seen, blocks = set(), []
    for start in sorted(entries):
        if start in seen:
            continue
        stack, mine, bad = [start], set(), False
        while stack:
            o = stack.pop()
            if o in seen or o in run or o is None or not 0 <= o < len(prg):
                continue
            s = succ(prg, o)
            if s is None:
                bad = True
                continue
            seen.add(o)
            mine.add(o)
            for t in s[0]:
                if t is not None and t not in run:
                    stack.append(t)
                    if t not in entries:
                        entries.setdefault(t, set())
        if mine:
            blocks.append((start, mine, entries[start], bad))
    return seen, blocks


def regions(prg, ins):
    """명령 오프셋 집합을 이어진 바이트 구간 [(시작, 끝)] 으로."""
    spans = sorted((o, o + 1 + dis6502.SIZE[dis6502.OPS[prg[o]][1]]) for o in ins)
    out = []
    for s, e in spans:
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def label(off):
    return f'{off // BANK:02X}:{cpu(off):04X}'


# 디버그 흔적으로 볼 명령: 패드 2($15, $4017), 고정 영역 첫 바이트 $C000(디버그 스위치), 패드와 여러 비트 비교
def suspicious(prg, off, nxt):
    raw = prg[off:off + 3]
    op = raw[0]
    if op in (0xA5, 0xA6, 0xA4, 0x24, 0x25, 0x05, 0x45, 0xC5) and raw[1] == 0x15:
        return '패드 2($15) 읽기'
    if op in (0xAD, 0xAE, 0xAC, 0x2C) and raw[1:3] == b'\x17\x40':
        return '$4017 읽기'
    if op in (0xAD, 0xAE, 0xAC, 0x2C) and raw[1:3] == b'\x00\xc0':
        return '디버그 스위치 $C000 읽기'
    if op == 0xA5 and raw[1] in (0x14, 0x15) and nxt is not None and prg[nxt] in (0xC9, 0x29) and prg[nxt + 1] not in (
            0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x03, 0x0F, 0xF0, 0xF3, 0xFF):
        return f'패드 ${raw[1]:02X} 와 조합 #{prg[nxt + 1]:02X}'
    return None


def brk_tables(prg, run, ins):
    """뱅크마다 $8000 함수 표(첫 함수 주소 앞까지)와, 실행·미실행 코드의 BRK 가 부르는 항목."""
    called = set()
    for o in run | ins:
        if prg[o] == 0 and o + 2 < len(prg):
            b1, b2 = prg[o + 1], prg[o + 2]
            if b2 & 7 == 7:
                called.add(((b2 >> 4) | (b2 & 8) << 1, b1 & (0x3F if b1 & 0x80 else 0x7F)))
            elif b2 & 0x0F == 3:
                n = b2 >> 4
                called.add((0x10, n) if n < 0xA else (0x10, n + 0x18) if n < 0xD else (0x12, n - 0xC))
            elif b2 == 0xFB:
                called.add((0x19, 3))
            elif b2 & 0x0F == 0x0B and b2 < 0xCB:
                called.add((0x16, 4))
    out = {}
    for bank in range(32):
        base = bank * BANK
        if not any(base <= o < base + BANK for o in run):
            continue
        ents, lo = [], 0xC000
        for f in range(0x80):
            if 0x8000 + 2 * f >= lo:
                break
            t = dq4bank.entry(prg, bank, f)
            if not 0x8000 <= t < 0xC000 and t < 0xC000:
                break
            if t < 0xC000:
                lo = min(lo, t)
            ents.append(t)
        out[bank] = [(f, t, (bank, f) in called, offset(base, t) in run if t < 0xC000 else None)
                     for f, t in enumerate(ents)]
    return out


def main():
    a = sys.argv
    prg = ines.prg(open(a[1], 'rb').read())
    cmd, covers = a[2], a[3:]
    run = read_covers(covers)
    ins, blocks = unrun(prg, run)
    if cmd == 'unrun':
        total = sum(e - s for s, e in regions(prg, ins))
        print(f'실행된 명령 {len(run)}개, 미실행 코드 {len(ins)}명령 {total}바이트, 덩어리 {len(blocks)}개')
        for start, mine, src, bad in sorted(blocks, key=lambda b: -len(b[1])):
            size = sum(e - s for s, e in regions(prg, mine))
            frm = ' '.join(label(s) for s in sorted(src)[:4])
            print(f'{label(start)} {size:5d}B {len(mine):4d}명령 {"?" if bad else " "} <- {frm}')
    elif cmd == 'find':
        code = run | ins
        for o in sorted(code):
            n = 1 + dis6502.SIZE[dis6502.OPS[prg[o]][1]]
            why = suspicious(prg, o, o + n if o + n in code else None)
            if why:
                print(f'{label(o)} {prg[o:o + n].hex(" "):<9} {"실행" if o in run else "미실행"} {why}')
    elif cmd == 'brk':
        for bank, ents in brk_tables(prg, run, ins).items():
            for f, t, called, ran in ents:
                if not called and not ran:
                    print(f'{bank:02X}[{f:02X}] = {t:04X} 부르는 BRK 없음, 실행 안 됨')


if __name__ == '__main__':
    main()
