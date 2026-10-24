"""DQ5(SFC) 이벤트(주인공을 조종하는 스크립트). 형식은 sfc/dq5/docs/dq5-event-format.md.

23:E29A(A = 이벤트 번호)는 23:E2C2 의 5바이트 항목 [X][Y][스크립트 24비트] 를 02:B705 에 넘긴다.
02:B705 는 7E:1A0D 에 「지금 자리에서 (X,Y) 까지 걷기」 명령과 C3(스크립트로 점프)를 만들고 7E:19B3 을 그곳으로 두어,
00:BEC3 이 매 걸음 명령을 하나씩 실행한다($19AE bit7 이 켜진 동안 주인공은 입력 대신 이 스크립트로 움직인다).

명령(00:BED2):
  00~0F d n        방향 d(01 오른쪽·02 왼쪽·04 아래·08 위)로 n 칸
  10 i m / 20 i m  7E:2190+i 에 m 을 OR / AND
  B0 i m           7E:2190+i & m 이 켜질 때까지 기다림
  60 lo hi         메시지(24:8157)
  90 BC BD X Y 층 198E  맵 옮기기
  A0 l h b         네이티브 호출
  C1 v             바라보는 방향 7E:31E0 = v
  C2               한 프레임 쉼
  C3 l h b         스크립트 점프
  C4 / C5 l h b    01:D915 / 01:F117 (인물 인라인 명령 41·43 과 같은 루틴)
  C6 / C9          23:FE69 / 23:FE8F
  C7 v / C8 v      23:FE77 / 23:FE80
  91               00:CC04 (말 걸기와 같은 루틴)
  FF               끝

사용:
  python sfc/dq5/tools/dq5event.py rom/dq5.sfc            # 이벤트 표 10개와 스크립트
  python sfc/dq5/tools/dq5event.py rom/dq5.sfc 15F702     # 그 주소의 스크립트
  python sfc/dq5/tools/dq5event.py rom/dq5.sfc --all      # 15:F150~F7CF 의 스크립트 전부
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402

EVENTS = 0x23E2C2
EVENT_COUNT = 10
# 15:F150~F7CF 에 스크립트가 FF 로 끝나며 이어져 있다(15:F7D0 부터는 맵별 루틴 코드).
SCRIPT_START, SCRIPT_END = 0x15F150, 0x15F7D0
DIRS = {0x01: '오른쪽', 0x02: '왼쪽', 0x04: '아래', 0x08: '위'}
LENGTHS = {0x10: 3, 0x20: 3, 0xB0: 3, 0x60: 3, 0x90: 7, 0xA0: 4, 0xC1: 2, 0xC2: 1, 0xC3: 4,
           0xC4: 4, 0xC5: 4, 0xC6: 1, 0xC7: 2, 0xC8: 2, 0xC9: 1, 0x91: 1, 0xFF: 1}


def events(rom):
    """[(번호, X, Y, 스크립트 주소)]."""
    out = []
    for n in range(EVENT_COUNT):
        a = EVENTS + n * 5
        out.append((n, rom.u8(a), rom.u8(a + 1), rom.u24(a + 2)))
    return out


def all_scripts(rom):
    """15:F150~F7CF 를 명령 길이로 읽어 FF 다음마다 나누는 스크립트 시작 주소."""
    a, starts = SCRIPT_START, [SCRIPT_START]
    while a < SCRIPT_END:
        op = rom.u8(a)
        a += 2 if op < 0x10 else LENGTHS[op]
        if op == 0xFF and a < SCRIPT_END:
            starts.append(a)
    return starts


def decode(rom, a, limit=200):
    """스크립트를 [(주소, 바이트, 설명)] 으로. FF 나 C3(점프)에서 멈춘다."""
    out = []
    for _ in range(limit):
        op = rom.u8(a)
        n = 2 if op < 0x10 else LENGTHS.get(op)
        if n is None:
            out.append((a, bytes([op]), f'모르는 명령 {op:02X}'))
            break
        raw = bytes(rom.u8(a + i) for i in range(n))
        out.append((a, raw, describe(raw)))
        a += n
        if op in (0xFF, 0xC3):
            break
    return out


def describe(raw):
    op = raw[0]
    if op < 0x10:
        return f'{DIRS.get(op, f"방향 {op:02X}")} {raw[1]}칸'
    if op in (0x10, 0x20, 0xB0):
        name = {0x10: '플래그 켜기', 0x20: '플래그 AND', 0xB0: '플래그 대기'}[op]
        return f'{name} 7E:{0x2190 + raw[1]:04X} & {raw[2]:02X}'
    if op == 0x60:
        return f'메시지 {raw[2]:02X}{raw[1]:02X}'
    if op == 0x90:
        return f'맵 옮기기 {raw[1]:02X}/{raw[2]:02X} ({raw[3]},{raw[4]}) 층 {raw[5]} 198E={raw[6]:02X}'
    if op in (0xA0, 0xC3, 0xC4, 0xC5):
        name = {0xA0: '네이티브 호출', 0xC3: '점프', 0xC4: '01:D915', 0xC5: '01:F117'}[op]
        return f'{name} {raw[3]:02X}:{raw[2]:02X}{raw[1]:02X}'
    if op == 0xC1:
        return f'방향 7E:31E0 = {raw[1]:02X}'
    names = {0xC2: '한 프레임 쉼', 0xC6: '23:FE69', 0xC9: '23:FE8F', 0x91: '00:CC04', 0xFF: '끝'}
    if op in (0xC7, 0xC8):
        return f'{"23:FE77" if op == 0xC7 else "23:FE80"} {raw[1]:02X}'
    return names[op]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('addr', nargs='?', type=lambda s: int(s, 16))
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.all:
        targets = [(None, None, None, a) for a in all_scripts(rom)]
    elif args.addr is not None:
        targets = [(None, None, None, args.addr)]
    else:
        targets = events(rom)
    for n, x, y, a in targets:
        if n is not None:
            print(f'이벤트 {n}: ({x},{y}) 까지 걸은 뒤 {a >> 16:02X}:{a & 0xFFFF:04X}')
        elif args.all:
            print(f'{a >> 16:02X}:{a & 0xFFFF:04X}')
        for addr, raw, text in decode(rom, a):
            print(f'  {addr >> 16:02X}:{addr & 0xFFFF:04X} {raw.hex(" "):21} {text}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
