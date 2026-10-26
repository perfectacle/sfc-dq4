"""DQ5(SFC) 롬 전체에서 낮은 WRAM 범위(기본 7E:1ABC~1BB1)에 닿을 수 있는 명령 모양을 모두 찾아 나눈다.
결과는 sfc/dq5/docs/dq5-hangul-format.md 의 「옮긴 레코드를 둘 자리」.

롬의 모든 바이트를 명령 시작으로 보고 아래 모양을 센다(자료 바이트도 들어가므로 거짓 양성이 많다).
  절대(abs·abs,X·abs,Y)   피연산자가 범위 안. 데이터 뱅크가 00~3F·80~BF·7E 면 낮은 WRAM 이다
  롱(long·long,X)         뱅크가 7E 이거나 00~3F·80~BF 의 거울이고 주소가 범위 안
  간접 포인터              JMP (a)·(a,X)·JSR (a,X)·JML [a] 의 a 가 범위 안(그 자리에서 주소를 읽음)
  즉값                     LDA·LDX·LDY #, PEA 의 16비트 값이 범위 안(간접 주소의 바탕이 될 수 있음)
  TCD·PLD                  앞 8바이트의 LDA #·PEA 로 D 를 알 수 없거나, D~D+FF 가 범위에 걸침
  MVN·MVP                  대상 뱅크가 낮은 WRAM 이고, 앞 15바이트의 LDY #·LDA # 로 대상 범위를 알 수 없거나 걸침

나누기: --exec 폴더(lua/dq5execcov.lua 의 exec.txt)로 실행된 바이트인지, --probe 폴더(같은 Lua 의 probe.txt)로
그 자리가 실제 명령 시작으로 실행됐는지를 본다. 실행된 바이트가 하나도 없는 뱅크는 따로 센다.

  uv run --locked python sfc/dq5/tools/dq5wramrefs.py rom/dq5.sfc --exec work/cov/* --positions work/cov/pos.txt
  uv run --locked python sfc/dq5/tools/dq5wramrefs.py rom/dq5.sfc --exec work/cov/* --probe work/cov/*
"""
import argparse
import collections
import glob
import os

ABS = dict.fromkeys([0x0D, 0x2D, 0x4D, 0x6D, 0x8D, 0xAD, 0xCD, 0xED, 0x0E, 0x2E, 0x4E, 0x6E, 0xCE, 0xEE, 0x2C, 0x8C, 0x8E,
                     0x9C, 0xAC, 0xAE, 0xCC, 0xEC, 0x0C, 0x1C], 'abs')
ABS.update(dict.fromkeys([0x1D, 0x3D, 0x5D, 0x7D, 0x9D, 0xBD, 0xDD, 0xFD, 0x1E, 0x3E, 0x5E, 0x7E, 0xDE, 0xFE, 0x3C, 0x9E,
                          0xBC], 'abs,X'))
ABS.update(dict.fromkeys([0x19, 0x39, 0x59, 0x79, 0x99, 0xB9, 0xD9, 0xF9, 0xBE], 'abs,Y'))
ABS.update({0x6C: '간접 포인터', 0x7C: '간접 포인터', 0xFC: '간접 포인터', 0xDC: '간접 포인터'})
LONG = dict.fromkeys([0x0F, 0x2F, 0x4F, 0x6F, 0x8F, 0xAF, 0xCF, 0xEF], 'long')
LONG.update(dict.fromkeys([0x1F, 0x3F, 0x5F, 0x7F, 0x9F, 0xBF, 0xDF, 0xFF], 'long,X'))
KINDS = ['abs', 'abs,X', 'abs,Y', 'long', 'long,X', '간접 포인터', '즉값', 'TCD', 'PLD', 'MVN·MVP']


def low_wram_bank(b):
    return b == 0x7E or (b & 0x7F) < 0x40


def scan(d, lo, hi):
    """(종류, 파일 오프셋, 설명) 목록."""
    out = []
    for o in range(len(d) - 3):
        op = d[o]
        w = d[o + 1] | d[o + 2] << 8
        if op in ABS and lo <= w <= hi:
            out.append((ABS[op], o, f'{w:04X}'))
        if op in LONG and lo <= w <= hi and low_wram_bank(d[o + 3]):
            out.append((LONG[op], o, f'{d[o + 3]:02X}:{w:04X}'))
        if op in (0xA9, 0xA2, 0xA0, 0xF4) and lo <= w <= hi:
            out.append(('즉값', o, f'#{w:04X}'))
        if op in (0x5B, 0x2B):
            src = next((d[o - k + 1] | d[o - k + 2] << 8 for k in range(1, 9) if o >= k and d[o - k] in (0xA9, 0xF4)), None)
            if src is None or (src <= hi and src + 0xFF >= lo):
                out.append(('TCD' if op == 0x5B else 'PLD', o, 'D=?' if src is None else f'D={src:04X}'))
        if op in (0x54, 0x44) and low_wram_bank(d[o + 1]):
            y = next((d[o - k + 1] | d[o - k + 2] << 8 for k in range(1, 16) if d[o - k] == 0xA0), None)
            n = next((d[o - k + 1] | d[o - k + 2] << 8 for k in range(1, 16) if d[o - k] == 0xA9), None)
            if y is None or n is None:
                hit = True
            else:
                a, b = (y, y + n) if op == 0x54 else (y - n, y)
                hit = a <= hi and b >= lo
            if hit:
                out.append(('MVN·MVP', o, f'대상 {d[o + 1]:02X}'))
    return out


def cpu(o):
    return (o // 0x8000) << 16 | 0x8000 | o % 0x8000


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('--range', default='1ABC-1BB1')
    ap.add_argument('--exec', nargs='*', default=[], help='exec.txt 가 든 폴더들')
    ap.add_argument('--probe', nargs='*', default=[], help='probe.txt 가 든 폴더들')
    ap.add_argument('--cdl', help='lua/dq5execcov.lua CDL=1 의 cdl.bin. 미실행 후보를 CDL 코드·자료·없음으로 더 나눔')
    ap.add_argument('--positions', help='실행된 후보 자리를 CPU 주소(00~3F 와 80~BF 거울 둘 다)로 이 파일에 씀(POSFILE 용)')
    a = ap.parse_args()
    d = open(a.rom, 'rb').read()
    lo, hi = (int(x, 16) for x in a.range.split('-'))
    ex = set()
    for f in a.exec:
        p = os.path.join(f, 'exec.txt')
        if os.path.exists(p):
            ex |= {int(line.split()[0], 16) for line in open(p) if line.strip()}
    starts = collections.defaultdict(list)
    for f in a.probe:
        p = os.path.join(f, 'probe.txt')
        if os.path.exists(p):
            for line in open(p):
                if line.strip():
                    starts[int(line.split()[0], 16)].append(line.split(None, 1)[1].strip())
    bank_exec = collections.Counter(o // 0x8000 for o in ex)
    cands = scan(d, lo, hi)
    if a.positions:
        pos = sorted({o for _, o, _ in cands if o in ex})
        with open(a.positions, 'w') as f:
            f.write(','.join(f'{cpu(o) | m:06X}' for o in pos for m in (0, 0x800000)))
        print(f'실행된 후보 자리 {len(pos)}곳 -> {a.positions}')
    rows = {k: [0] * 5 for k in KINDS}
    for k, o, _ in cands:
        r = rows[k]
        r[0] += 1
        if o in ex:
            r[1 if cpu(o) in starts else 2] += 1
        else:
            r[3 if bank_exec[o // 0x8000] == 0 else 4] += 1
    print(f'실행된 롬 바이트 {len(ex)}, 실행된 뱅크 {len(bank_exec)}')
    print('| 모양 | 후보 | 실행된 명령 시작 | 실행된 다른 명령 중간 | 실행 코드가 없는 뱅크 | 코드가 있는 뱅크의 미실행 |')
    print('| --- | --- | --- | --- | --- | --- |')
    for k, r in rows.items():
        print(f'| {k} | ' + ' | '.join(f'{v:,}' for v in r) + ' |')
    print('| 합계 | ' + ' | '.join(f'{sum(r[i] for r in rows.values()):,}' for i in range(5)) + ' |')
    if a.cdl:
        cdl = open(a.cdl, 'rb').read()
        sub = collections.Counter()
        for k, o, _ in cands:
            if o in ex:
                continue
            f = cdl[o] if o < len(cdl) else 0
            where = '자료 뱅크' if bank_exec[o // 0x8000] == 0 else '코드 뱅크'
            sub[(k in KINDS[:7], where, '코드' if f & 1 else '자료' if f & 2 else '없음')] += 1
        print('\n미실행 후보의 CDL(직접 피연산자 여부, 뱅크, CDL):')
        for key, v in sorted(sub.items()):
            print(f'  {"직접" if key[0] else "값 모름"} {key[1]} {key[2]}: {v:,}')
        print('\nCDL 이 코드라 한 직접 피연산자 후보(정렬된 디스어셈블로 명령 중간인지 볼 것):')
        for k, o, det in cands:
            if o not in ex and k in KINDS[:7] and o < len(cdl) and cdl[o] & 1:
                print(f'  {cpu(o) >> 16:02X}:{cpu(o) & 0xFFFF:04X} {k} {det} {d[o:o + 4].hex(" ")}')
    if starts:
        print('\n명령으로 실행된 후보:')
        byo = {cpu(o): (k, det) for k, o, det in cands}
        for addr, ls in sorted(starts.items()):
            if addr in byo:
                k, det = byo[addr]
                print(f'  {addr >> 16:02X}:{addr & 0xFFFF:04X} {k} {det} {len(ls)}번, 예 {ls[0]}')


if __name__ == '__main__':
    main()
