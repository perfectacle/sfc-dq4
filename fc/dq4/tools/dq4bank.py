"""DQ4(FC) BRK 뱅크 호출 풀기. 형식은 fc/dq4/docs/dq4-bank-format.md.

사용:
  python fc/dq4/tools/dq4bank.py rom/dq4.nes call C9FC [--bank 1D]   BRK 한 곳 풀기(--bank: 그때 $0507)
  python fc/dq4/tools/dq4bank.py rom/dq4.nes table 1D [N]            뱅크의 $8000 함수 표 앞 N 개
  python fc/dq4/tools/dq4bank.py rom/dq4.nes compare trace.txt       probe/trace.lua 기록과 비교
  python fc/dq4/tools/dq4bank.py rom/dq4.nes free [최소 길이]         뱅크마다 FF·00 연속 구간(빈 자리 후보)
  python fc/dq4/tools/dq4bank.py rom/dq4.nes cover cover.txt ...      probe/cover.lua 결과의 뱅크별 실행 오프셋 수

근거 루틴(뱅크 0F): BRK 처리기 $C408, 호출 $C38B, 포인터 꺼내기 $C3CE, 표 읽기 $C3BA,
뱅크 전환 $FF91. compare 용 기록은 TRACE=C446,C455,C3CD LOG=0023,0024,0025,0026,0027,0507.
"""
import sys

from kr_patch.fc import ines


def prg_offset(bank, addr):
    return bank * 0x4000 + (addr & 0x3FFF)


def mapped(cur, addr):
    """$0507 이 cur 일 때 CPU addr 의 PRG 뱅크. $C000- 는 그 256KB 절반의 마지막 뱅크."""
    return (cur & 0x10) | 0x0F if addr >= 0xC000 else cur


def entry(prg, bank, func):
    o = prg_offset(bank, 0x8000 + 2 * func)
    return prg[o] | prg[o + 1] << 8


def x3_length(b2):
    """x3 형식의 BRK 부터 복귀 자리까지 바이트 수(불린 함수가 복귀 주소를 고침). 모르면 None.
    뱅크 10 함수 02~07 은 둘씩 같은 코드로 b2 가 33·53·73 이면 BRK+3, 23·43·63 이면 셋째까지 읽어 BRK+4.
    함수 08·09 는 93 이면 셋째까지(BRK+4), 83 이면 넷째까지(BRK+5) 읽는다(10:$812B)."""
    n = b2 >> 4
    if n == 8:
        return 5
    if 2 <= n <= 9:
        return 4 if n == 9 or not n & 1 else 3
    return {0x0: 3, 0x1: 3, 0xA: 3, 0xB: 3, 0xC: 4, 0xD: 4, 0xE: 3}.get(n)


def call(prg, site, cur):
    """BRK 가 있는 CPU 주소 site 를 ($0507=cur 에서) 풀어 dict 로. 특수 경로는 kind 만."""
    o = prg_offset(mapped(cur, site), site)
    assert prg[o] == 0x00, f'{site:04X} 는 BRK 가 아님'
    b1, b2 = prg[o + 1], prg[o + 2]
    c = {'site': site, 'b1': b1, 'b2': b2}
    if b2 & 0x0F == 0x03:
        # $C4F8: b1·b2·셋째 바이트를 $76·$77·$78 에 두고 뱅크 10(·12) 함수로 간다.
        n = b2 >> 4
        bank, func = (0x10, n) if n < 0x0A else (0x10, n + 0x18) if n < 0x0D else (0x12, n - 0x0C)
        return c | {'kind': 'x3', 'bank': bank, 'func': func, 'target': entry(prg, bank, func),
                    'length': x3_length(b2)}
    if b2 & 0x0F == 0x0B:
        if b2 < 0xCB:
            return c | {'kind': 'message', 'msg': (b2 >> 4) << 8 | b1, 'bank': 0x16, 'func': 0x04,
                        'target': entry(prg, 0x16, 0x04)}
        if b2 == 0xFB:
            return c | {'kind': 'sound', 'sound': b1, 'bank': 0x19, 'func': 0x03, 'target': entry(prg, 0x19, 0x03)}
        kind = {0xCB: 'flag-set', 0xDB: 'flag-clear'}.get(b2, 'flag-test')
        return c | {'kind': kind, 'flag': 0x627B + b1, 'mask': prg[o + 3]}
    bank = (b2 >> 4) | (b2 & 0x08) << 1
    if b1 & 0x80:
        func, kind = b1 & 0x3F, 'pointer'
    else:
        func, kind = b1, 'call'
    return c | {'kind': kind, 'bank': bank, 'func': func, 'target': entry(prg, bank, func)}


def fmt(c):
    s = f"{c['site']:04X}: 00 {c['b1']:02X} {c['b2']:02X} {c['kind']}"
    if 'msg' in c:
        s += f" msg={c['msg']:04X}"
    if 'sound' in c:
        s += f" sound={c['sound']:02X}"
    if 'flag' in c:
        s += f" ${c['flag']:04X} mask={c['mask']:02X}"
    elif 'bank' in c:
        s += f" bank={c['bank']:02X} func={c['func']:02X} -> {c['bank']:02X}:{c['target']:04X}"
    if c['kind'] == 'x3':
        s += f" len={c['length'] or '?'}"
    return s


STUB = 0xBFD8   # 바꿔 끼우는 뱅크마다 $BFD8- 에 리셋 조각·「 DRAGON QUEST IV」·벡터가 있다


def free_runs(prg, bank, minlen=16):
    """뱅크 안 같은 값(FF 또는 00)이 minlen 이상 이어진 구간 (CPU 주소, 길이, 값)."""
    base = 0xC000 if bank in (0x0F, 0x1F) else 0x8000
    d = prg[bank * 0x4000:(bank + 1) * 0x4000]
    out, i = [], 0
    while i < len(d):
        j = i
        while j < len(d) and d[j] == d[i]:
            j += 1
        if j - i >= minlen and d[i] in (0x00, 0xFF):
            out.append((base + i, j - i, d[i]))
        i = j
    return out


def cover_counts(paths):
    """cover.txt 들의 실행 오프셋을 합쳐 뱅크별 개수로."""
    seen = set()
    for p in paths:
        for ln in open(p):
            seen.add(int(ln.split()[0], 16))
    counts = [0] * 32
    for o in seen:
        counts[o >> 14] += 1
    return counts


def compare(prg, path):
    lines = open(path).read().split('---\n', 1)[1].splitlines()
    regs = [dict(kv.split('=') for kv in ln.split()[3:] if '=' in kv) | {'pc': ln.split()[1]} for ln in lines]
    ok = bad = 0
    sites = set()
    for i, r in enumerate(regs):
        if r['pc'] not in ('C446', 'C455'):
            continue
        site = (int(r['0026'], 16) | int(r['0027'], 16) << 8) - 1
        c = call(prg, site, int(r['0507'], 16))
        got_bank, got_func = int(r['0023'], 16), int(r['0024'], 16)
        nxt = next((x for x in regs[i + 1:] if x['pc'] == 'C3CD'), None)
        got_target = int(nxt['0024'], 16) | int(nxt['0025'], 16) << 8 if nxt else None
        good = (c['kind'] == ('call' if r['pc'] == 'C446' else 'pointer') and c['bank'] == got_bank
                and c['func'] == got_func and c['target'] == got_target)
        if good:
            ok += 1
        else:
            bad += 1
            print('다름:', fmt(c), f'기록 bank={got_bank:02X} func={got_func:02X} target={got_target}')
        sites.add((site, int(r['0507'], 16)))
    print(f'{ok + bad} 호출 중 {bad} 다름, 호출 위치 {len(sites)} 곳')
    for site, cur in sorted(sites):
        print(' ', fmt(call(prg, site, cur)))
    return bad == 0


def main():
    prg = ines.prg(open(sys.argv[1], 'rb').read())
    cmd = sys.argv[2]
    if cmd == 'call':
        cur = int(sys.argv[sys.argv.index('--bank') + 1], 16) if '--bank' in sys.argv else 0
        print(fmt(call(prg, int(sys.argv[3], 16), cur)))
    elif cmd == 'table':
        bank = int(sys.argv[3], 16)
        for f in range(int(sys.argv[4]) if len(sys.argv) > 4 else 16):
            print(f'{bank:02X}[{f:02X}] = {entry(prg, bank, f):04X}')
    elif cmd == 'compare':
        sys.exit(0 if compare(prg, sys.argv[3]) else 1)
    elif cmd == 'free':
        minlen = int(sys.argv[3]) if len(sys.argv) > 3 else 16
        total = 0
        for bank in range(32):
            rs = free_runs(prg, bank, minlen)
            n = sum(r[1] for r in rs)
            total += n
            print(f'{bank:02X} {n:5d}', ' '.join(f'{a:04X}+{ln}({v:02X})' for a, ln, v in rs))
        print(f'# {minlen}바이트 이상 연속 구간 합 {total}')
    elif cmd == 'cover':
        for bank, n in enumerate(cover_counts(sys.argv[3:])):
            print(f'{bank:02X} {n}')


if __name__ == '__main__':
    main()
