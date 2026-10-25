"""DQ5(SFC) SRAM 세이브(모험의 서) 읽기·체크섬 고치기. 형식은 sfc/dq5/docs/dq5-data-format.md 의 「SRAM 세이브」.

SRAM 8KB(70:0000~1FFF). 25:8062 가 머리 「DRAGON QUEST V」 를 0000·1FF2 두 곳에서 확인하고, 둘 다 다르면 SRAM 을 지운다.
70:000E 는 쓰는 칸 비트(칸 0 = 01, 1 = 02, 2 = 04), 000F~0011 은 칸마다 상태 바이트.
칸 n 은 25:800E[n] = 0012·0AB2·1552 에서 AA0 바이트이고 WRAM 7E:2000~2A9F 를 그대로 옮긴 것이다(25:83CE 저장, 25:8258 불러오기).
마지막 워드(7E:2A9E)가 체크섬: 앞 54F 워드의 16비트 합(25:8450). 켤 때 25:81CF 가 칸마다 맞춰 본다.

사용:
  python sfc/dq5/tools/dq5sram.py rom/dq5.sfc save.srm            # 칸마다 이름·레벨·금화·체크섬
  python sfc/dq5/tools/dq5sram.py rom/dq5.sfc save.srm --fix out  # 체크섬을 다시 계산해 out 에 씀
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5text import string_codes, text  # noqa: E402

SIZE = 0x2000
MAGIC = b'DRAGON QUEST V'
MAGIC_COPY = 0x1FF2
USED = 0x0E
STATUS = 0x0F
SLOTS = (0x0012, 0x0AB2, 0x1552)
SLOT_SIZE = 0xAA0
SUM_AT = 0xA9E
# 칸 안 오프셋 = WRAM 주소 - 7E:2000.
NAME, GOLD, LEVEL = 0x01, 0x19, 0x52


def checksum(block):
    return sum(block[i] | block[i + 1] << 8 for i in range(0, SUM_AT, 2)) & 0xFFFF


def slots(sram):
    """[(칸, 오프셋, 쓰는 칸인지, 상태, 저장된 체크섬, 계산한 체크섬, 칸 바이트)]."""
    out = []
    for n, off in enumerate(SLOTS):
        block = sram[off:off + SLOT_SIZE]
        stored = block[SUM_AT] | block[SUM_AT + 1] << 8
        out.append((n, off, bool(sram[USED] & 1 << n), sram[STATUS + n], stored, checksum(block), block))
    return out


def hero_name(rom, block):
    raw = block[NAME:NAME + 8]
    return text(string_codes(rom, raw.split(b'\x01')[0]))


def fix(sram):
    out = bytearray(sram)
    for _, off, _, _, _, calc, _ in slots(sram):
        out[off + SUM_AT] = calc & 0xFF
        out[off + SUM_AT + 1] = calc >> 8
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('sram')
    ap.add_argument('--fix', metavar='OUT')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    sram = open(args.sram, 'rb').read()[:SIZE]
    head = sram[:len(MAGIC)] == MAGIC, sram[MAGIC_COPY:MAGIC_COPY + len(MAGIC)] == MAGIC
    print(f'머리 0000 {"맞음" if head[0] else "다름"}, 1FF2 {"맞음" if head[1] else "다름"}, 쓰는 칸 {sram[USED]:02X}')
    for n, off, used, status, stored, calc, block in slots(sram):
        gold = block[GOLD] | block[GOLD + 1] << 8 | block[GOLD + 2] << 16
        ok = '맞음' if stored == calc else f'다름(계산 {calc:04X})'
        name = hero_name(rom, block) if used else '-'
        print(f'칸 {n + 1} {off:04X} {"쓰임" if used else "빔"} 상태 {status:02X} 체크섬 {stored:04X} {ok} '
              f'이름 {name} 레벨 {block[LEVEL]} 금화 {gold}')
    if args.fix:
        with open(args.fix, 'wb') as f:
            f.write(fix(sram))
    return 0


if __name__ == '__main__':
    sys.exit(main())
