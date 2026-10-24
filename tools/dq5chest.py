"""DQ5(SFC) 보물상자와 タンス·ツボ 류. 형식은 docs/dq5-map-format.md 의 「보물상자」.

말을 걸거나 しらべる 로 앞 칸을 보면 12:E4C9 가 앞 칸 종류를 차례로 검사한다.
  보물상자: 셀 +4 또는 +7 이 $84(2A:FF3E). 25:FAB0 이 1E:EF90 표의 맵 시작 번호에, 셀 버퍼에서 그 칸 앞에 있는 상자 셀 수를
            더해(2A:FBCD, 출구 번호와 같은 방식) 상자 번호 n 을 낸다. 내용물은 1E:EE4E + n*2, 열림은 7E:2210 + n/8 의 비트(12:E675).
  タンス 류: 셀 속성 $93(タンス)·$A7·$D4(ツボ)·$B9·$D3(タル) 이면 12:FB9D 가 1F:F5CB 표에서 맵과 좌표로 항목을 찾는다.
  발밑: 12:E6BE 가 선 칸과 이웃 칸을 1E:F08B 표에서 맵·좌표·방향($C3)으로 찾는다. 열림은 7E:2240 + 번호 & 마스크.
내용물 값(16비트, 12:F43B): 100 미만 = 물건 번호, 100~CFFF = 금화(값 - 100), D000~D009 = 장소마다 정한 일(12:F51F),
FFFC 잠김, FFFD 人くい箱(상자 밖은 あくまのツボ), FFFE ミミック(상자 밖은 ツボック), FFFF 빈 상자.

사용:
  python tools/dq5chest.py rom/dq5.sfc            # 전체
  python tools/dq5chest.py rom/dq5.sfc 01 02      # 맵 하나
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5exit import apply_hook, exit_cells  # noqa: E402
from dq5map import Decoder, Rom, map_pointer  # noqa: E402
from dq5text import string, string_codes, text  # noqa: E402

CHEST_MAPS = 0x1EEF90
CHEST_ITEMS = 0x1EEE4E
CHEST_ATTR = 0x84
CHEST_FLAGS = 0x7E2210
# 25:FAE9. 상자 번호 하위 3비트 → 비트 마스크.
BIT_MASKS = (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01)
# 1F:F5CB. [BC][BD][X][Y][?][내용물 16비트][플래그 번호][마스크], FFFF 로 끝. 열림은 7E:222C + 번호 & 마스크.
# +4 는 12:FB9D 도 맵에 들어갈 때도 읽지 않는다.
SEARCH_TABLE = 0x1FF5CB
SEARCH_FLAGS = 0x7E222C
# 1E:F08B. [BC][BD][X][Y][방향 $C3][내용물 16비트][플래그 번호][마스크], FFFF 로 끝(12:E6D7).
FOOT_TABLE = 0x1EF08B
FOOT_FLAGS = 0x7E2240
ITEM_NAMES = 5
SPECIAL = {0xFFFC: '잠김', 0xFFFD: '人くい箱', 0xFFFE: 'ミミック', 0xFFFF: '빈 상자'}
# 상자가 아닌 곳($1E76 이 0 이 아님)에서는 FFFD·FFFE 가 다른 몬스터다(12:F493).
SPECIAL_JAR = {0xFFFD: 'あくまのツボ', 0xFFFE: 'ツボック'}
# 12:F51F 의 갈래. 괄호는 띄우는 메시지 번호.
EVENTS = {
    0xD000: 'カギの技法(264·165)',
    0xD001: '$1948 = 0 이면 BD 04 (56,33) 으로 이동',
    0xD002: '$1948 = 0 이면 BD 02 (23,17) 로 이동',
    0xD003: 'イスをどかせて(28C) おりる階段(150)',
    0xD004: 'ドレイたちのトイレ(2B3)',
    0xD005: 'ツボを見た(155)·青い光(152)',
    0xD006: 'おりる階段(150)',
    0xD007: 'でっぱった石(2F1)',
    0xD008: 'おりる階段(150)',
    0xD009: '플래그에 따라 갈림',
}


def item_name(rom, n):
    return text(string_codes(rom, string(rom, ITEM_NAMES, n)))


def describe(rom, v, chest=True):
    if not chest and v in SPECIAL_JAR:
        return SPECIAL_JAR[v]
    if v in SPECIAL:
        return SPECIAL[v]
    if v < 0x100:
        return f'물건 {v:02X} {item_name(rom, v)}'
    if v >= 0xD000:
        return f'{v:04X} {EVENTS.get(v, "?")}'
    return f'{v - 0x100}G'


def chest_maps(rom):
    """1E:EF90. [(bc, bd, 시작 번호, 개수)]."""
    out, a, n = [], CHEST_MAPS, 0
    while rom.u16(a) != 0xFFFF:
        count = rom.u8(a + 2)
        out.append((rom.u8(a), rom.u8(a + 1), n, count))
        n += count
        a += 3
    return out


def chests(rom, bc, bd, start):
    """맵의 상자 [(번호, (x, y), 내용물)]. 상자 셀은 맵별 루틴까지 반영한 셀 버퍼에서 센다."""
    w, h, buf, _ = Decoder(rom, 0xBE).decode(map_pointer(rom, bc, bd))
    buf = bytearray(buf)
    apply_hook(rom, bc, bd, buf, w)
    return [(start + k, xy, rom.u16(CHEST_ITEMS + (start + k) * 2))
            for k, xy in enumerate(exit_cells(buf, w, h, [CHEST_ATTR]))]


def search_entries(rom):
    """1F:F5CB. [(bc, bd, x, y, +4, 내용물, 플래그 번호, 마스크)]."""
    out, a = [], SEARCH_TABLE
    while rom.u16(a) != 0xFFFF:
        e = [rom.u8(a + i) for i in range(9)]
        out.append((e[0], e[1], e[2], e[3], e[4], e[5] | e[6] << 8, e[7], e[8]))
        a += 9
    return out


def foot_entries(rom):
    """1E:F08B. [(bc, bd, x, y, 방향, 내용물, 플래그 번호, 마스크)]."""
    out, a = [], FOOT_TABLE
    while rom.u16(a) != 0xFFFF:
        e = [rom.u8(a + i) for i in range(9)]
        out.append((e[0], e[1], e[2], e[3], e[4], e[5] | e[6] << 8, e[7], e[8]))
        a += 9
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('map', nargs='*', type=lambda s: int(s, 16))
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    want = tuple(args.map) if args.map else None
    for bc, bd, start, count in chest_maps(rom):
        if want and (bc, bd) != want:
            continue
        for n, (x, y), v in chests(rom, bc, bd, start):
            flag = f'7E:{(CHEST_FLAGS + (n >> 3)) & 0xFFFF:04X}&{BIT_MASKS[n & 7]:02X}'
            print(f'{bc:02X}/{bd:02X} 상자 {n:3d} ({x},{y}) {flag} {describe(rom, v)}')
    for bc, bd, x, y, _, v, idx, mask in search_entries(rom):
        if want and (bc, bd) != want:
            continue
        print(f'{bc:02X}/{bd:02X} タンス류 ({x},{y}) 7E:{(SEARCH_FLAGS + idx) & 0xFFFF:04X}&{mask:02X} '
              f'{describe(rom, v, chest=False)}')
    for bc, bd, x, y, face, v, idx, mask in foot_entries(rom):
        if want and (bc, bd) != want:
            continue
        print(f'{bc:02X}/{bd:02X} 발밑 ({x},{y}) 방향 {face} 7E:{(FOOT_FLAGS + idx) & 0xFFFF:04X}&{mask:02X} '
              f'{describe(rom, v, chest=False)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
