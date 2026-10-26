"""모험의 서(SRAM 8KB)의 주인공 이름을 보고, 표시 없이 저장된 예전 한글 이름을 표시 있는 한글 부호로 바꾼다.

조합형 이름 입력의 첫 판은 글자마다 (10 + n // 111, 10 + n % 111) 로 저장해 일본어 가나 이름과 바이트만으로 가를 수
없었다(예: ああああ = 10 10 10 10 이 「ㄱㄱ」 로도 읽힘). 지금은 첫 바이트가 85~9A 인 것만 한글로 읽으므로
(dq4nameentry.py), 예전 한글 저장은 사용자가 고른 칸만 바꾼다. 원본 파일은 덮어쓰지 않는다.

  python sfc/dq4/tools/dq4namesave.py show save.srm
  python sfc/dq4/tools/dq4namesave.py convert save.srm --korean-slots 1,3 --out new.srm
"""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4nameentry as ne  # noqa: E402
from dq5sram import MAGIC, SIZE, SLOTS, SUM_AT, USED, checksum  # noqa: E402

NAME = 0x01                 # 칸 안 오프셋 = 7E:2001 - 7E:2000


def name_kind(raw):
    """이름 8바이트 → (종류, 읽은 글). 종류는 korean·legacy(예전 한글로도 읽힘)·kana."""
    try:
        return 'korean', ne.decode_name(raw)
    except ValueError:
        pass
    try:
        return 'legacy', ne.decode_name(raw, ne.LEGACY_HI_BASE)
    except ValueError:
        return 'kana', ''


def show(sram):
    lines = []
    for n, off in enumerate(SLOTS):
        if not sram[USED] & 1 << n:
            lines.append(f'칸 {n + 1}: 빔')
            continue
        raw = sram[off + NAME:off + NAME + 8]
        kind, text = name_kind(raw)
        lines.append(f'칸 {n + 1}: {raw.hex(" ")} {kind} {text}')
    return lines


def convert(sram, slots):
    """slots(1부터)의 예전 한글 이름을 표시 있는 부호로 바꾸고 칸 체크섬을 다시 계산한 새 바이트."""
    if len(sram) < SIZE or sram[:len(MAGIC)] != MAGIC:
        raise ValueError('DQ5 모험의 서 SRAM 이 아님')
    out = bytearray(sram)
    for slot in slots:
        if not 1 <= slot <= len(SLOTS):
            raise ValueError(f'칸 번호 {slot}')
        if not sram[USED] & 1 << (slot - 1):
            raise ValueError(f'칸 {slot} 은 비어 있음')
        off = SLOTS[slot - 1]
        block = sram[off:off + SUM_AT + 2]
        if (block[SUM_AT] | block[SUM_AT + 1] << 8) != checksum(block):
            raise ValueError(f'칸 {slot} 의 체크섬이 맞지 않음')
        raw = sram[off + NAME:off + NAME + 8]
        kind, text = name_kind(raw)
        if kind != 'legacy':
            raise ValueError(f'칸 {slot} 이름 {raw.hex(" ")} 은 예전 한글 부호가 아님({kind})')
        name = b''.join(ne.code_bytes(ne.GLYPHS.index(ch)) for ch in text)
        out[off + NAME:off + NAME + 8] = name.ljust(8, b'\x01')
        s = checksum(out[off:off + SUM_AT + 2])
        out[off + SUM_AT:off + SUM_AT + 2] = s.to_bytes(2, 'little')
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('show')
    s.add_argument('sram', type=Path)
    c = sub.add_parser('convert')
    c.add_argument('sram', type=Path)
    c.add_argument('--korean-slots', required=True, help='예전 한글 이름이 든 칸(1~3, 쉼표로)')
    c.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    sram = a.sram.read_bytes()
    if a.cmd == 'show':
        print('\n'.join(show(sram)))
        return
    if a.out.exists() or a.out.resolve() == a.sram.resolve():
        ap.error('--out 은 아직 없는 새 파일이어야 합니다(원본을 덮어쓰지 않음)')
    out = convert(sram, [int(x) for x in a.korean_slots.split(',')])
    a.out.write_bytes(out)
    print('\n'.join(show(out)))


if __name__ == '__main__':
    main()
