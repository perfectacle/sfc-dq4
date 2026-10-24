"""DQ4(FC) BRK 뱅크 호출 풀기. 형식은 docs/dq4-bank-format.md.

사용:
  python tools/dq4bank.py rom/dq4.nes call C9FC [--bank 1D]   BRK 한 곳 풀기(--bank: 그때 $0507)
  python tools/dq4bank.py rom/dq4.nes table 1D [N]            뱅크의 $8000 함수 표 앞 N 개
  python tools/dq4bank.py rom/dq4.nes compare trace.txt       probe/trace.lua 기록과 비교

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


def call(prg, site, cur):
    """BRK 가 있는 CPU 주소 site 를 ($0507=cur 에서) 풀어 dict 로. 특수 경로는 kind 만."""
    o = prg_offset(mapped(cur, site), site)
    assert prg[o] == 0x00, f'{site:04X} 는 BRK 가 아님'
    b1, b2 = prg[o + 1], prg[o + 2]
    if b2 & 0x07 == 0x03:
        return {'site': site, 'b1': b1, 'b2': b2, 'kind': 'special'}
    bank = (b2 >> 4) | (b2 & 0x08) << 1
    if b1 & 0x80:
        func, kind = b1 & 0x3F, 'pointer'
    else:
        func, kind = b1, 'call'
    return {'site': site, 'b1': b1, 'b2': b2, 'kind': kind, 'bank': bank, 'func': func,
            'target': entry(prg, bank, func)}


def fmt(c):
    s = f"{c['site']:04X}: 00 {c['b1']:02X} {c['b2']:02X} {c['kind']}"
    if 'bank' in c:
        s += f" bank={c['bank']:02X} func={c['func']:02X} -> {c['bank']:02X}:{c['target']:04X}"
    return s


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


if __name__ == '__main__':
    main()
