"""DQ4(FC) 이름 목록·아이템·몬스터 표. 형식은 docs/dq4-data-format.md.

사용:
  python tools/dq4data.py rom/dq4.nes names [목록]     spell class sex item place tactic monster
  python tools/dq4data.py rom/dq4.nes items            아이템 ID, 이름, 강도, 가격
  python tools/dq4data.py rom/dq4.nes monsters         몬스터 ID, 이름, 경험치, 최대 HP, 레코드 22바이트

근거: 0B:$B006(이름 목록 포인터), 10:$8BED(가격), 10:$8C3B(강도 $9E17), 18:$8046(몬스터 레코드).
"""
import sys

from kr_patch.fc import ines

import dq4text

NAMES_BANK, NAMES_PTR = 0x0B, 0xB006
LISTS = ('spell', 'class', 'sex', 'item', 'monster', 'place', 'tactic')   # 0B:$B006 의 순서(뒤에 monster 한 번 더)
ITEM_BANK = 0x10
ITEM_POWER, ITEM_PRICE, ITEM_SCALE = 0x9E17, 0x8E19, 0x8D1B
MON_BANK, MON_TABLE, MON_SIZE = 0x18, 0x8046, 22


def rd(prg, bank, addr):
    return prg[bank * 0x4000 + (addr & 0x3FFF)]


def name_list(prg, which):
    """길이 바이트 + 글자 바이트 이름들. 다음 목록 시작에서 끝난다. 0번은 빈 이름이라 ID = 순번 − 1."""
    i = LISTS.index(which)
    ptrs = [rd(prg, NAMES_BANK, NAMES_PTR + 2 * j) | rd(prg, NAMES_BANK, NAMES_PTR + 2 * j + 1) << 8
            for j in range(len(LISTS))]
    a = ptrs[i]
    end = min([p for p in ptrs if p > a] or [0xBFFF])
    out = []
    while a < end:
        n = rd(prg, NAMES_BANK, a)
        if n > 0x10:
            break
        out.append([rd(prg, NAMES_BANK, a + 1 + k) for k in range(n)])
        a += 1 + n
    while out and all(b == 0 for b in out[-1]):
        out.pop()
    return out


def items(prg):
    """(ID, 이름, 강도, 가격). 가격 = ($8E19 & 7F) × 10^($8D1B & 3)(코드 읽기)."""
    out = []
    for i, nm in enumerate(name_list(prg, 'item')[1:]):
        price = (rd(prg, ITEM_BANK, ITEM_PRICE + i) & 0x7F) * 10 ** (rd(prg, ITEM_BANK, ITEM_SCALE + i) & 3)
        out.append((i, dq4text.text(nm), rd(prg, ITEM_BANK, ITEM_POWER + i), price,
                    rd(prg, ITEM_BANK, ITEM_PRICE + i) >> 7))
    return out


def monsters(prg):
    """(ID, 이름, 경험치(바이트 0-1), 최대 HP(바이트 4), 레코드)."""
    out = []
    for i, nm in enumerate(name_list(prg, 'monster')[1:]):
        r = bytes(rd(prg, MON_BANK, MON_TABLE + MON_SIZE * i + k) for k in range(MON_SIZE))
        out.append((i, dq4text.text(nm), r[0] | r[1] << 8, r[4], r))
    return out


def main():
    prg = ines.prg(open(sys.argv[1], 'rb').read())
    cmd = sys.argv[2]
    if cmd == 'names':
        for which in (sys.argv[3:] or LISTS):
            ns = name_list(prg, which)
            print(f'# {which} {len(ns) - 1}')
            for i, nm in enumerate(ns[1:]):
                print(f'{i:02X} {dq4text.text(nm)}')
    elif cmd == 'items':
        for i, nm, pw, price, flag in items(prg):
            print(f'{i:02X} {nm:<14} 강도 {pw:3d} 가격 {price:6d}' + (' *' if flag else ''))
    elif cmd == 'monsters':
        for i, nm, exp, hp, r in monsters(prg):
            print(f'{i:02X} {nm:<12} 경험치 {exp:5d} HP {hp:3d}  {r.hex(" ")}')


if __name__ == '__main__':
    main()
