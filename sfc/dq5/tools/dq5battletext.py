"""DQ5(SFC) 전투 모드 메시지. 형식은 sfc/dq5/docs/dq5-data-format.md 의 「전투 모드 메시지」.

24:8C39(A = 메시지 번호)는 24:AECD 의 3바이트 색인((번호 >> 4) * 3)에서 비트 위치를 얻고, 끝 바이트(FE·EF·E7)를
(번호 & F) 번 건너뛴 뒤, 24:8C21 이 24:9E47 로 한 바이트씩 풀어 7E:0E4B(128바이트)에 둔다.
허프만 트리는 비트 1 → 24:9C2E, 0 → 24:9D18, 처음 X = E8, 잎(bit15)은 값 & FF, 아니면 다음 X = 값 * 2.
글자는 이름 문자열과 같은 1바이트 부호(83·84 는 다음 바이트와 함께 탁점·반탁점 글자)이고, E2 이상은 24:86F2 의 처리기로 간다.

사용:
  python sfc/dq5/tools/dq5battletext.py rom/dq5.sfc            # 메시지 432개
  python sfc/dq5/tools/dq5battletext.py rom/dq5.sfc 069 06A    # 고른 번호
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5text import BitReader, string_codes, text  # noqa: E402

INDEX = 0x24AECD
COUNT = 432  # 색인이 24:AF1E(보행 모드 색인) 앞까지 27개
NODES_1, NODES_0, ROOT = 0x249C2E, 0x249D18, 0xE8
ENDS = (0xFE, 0xEF, 0xE7)
HANDLERS = 0x2486F2
# 24:86F2 처리기(코드 읽기, F7·FB·FE·FF·FD 는 화면으로 확인). 이름·숫자는 $F5~$F8 대기열에서 하나씩 꺼낸다(24:889F).
CONTROLS = {
    0xE7: '끝', 0xEF: '끝(그대로 다음 메시지)', 0xFE: '끝(누르기 기다림)', 0xFF: '줄 바꿈', 0xFD: '쪽 넘김',
    0xF7: '대기열 이름(bit7 이면 몬스터 무리, 아니면 일행 칸. 24:88B6)', 0xFB: '대기열 3바이트 숫자(04:AE7C)',
    0xF4: '대기열 번호의 주문 이름(이름 표 3)', 0xF6: '몬스터 이름(이름 표 4)', 0xF5: '물건 이름(이름 표 5)',
    0xF3: '이름 표 7', 0xEB: '이름 표 6', 0xED: '주인공 이름(7E:2001)', 0xE8: '이름 7E:2009', 0xE9: '이름 7E:2011',
    0xEA: '이름(24:8A49)', 0xEC: '일행 이름(24:8ABB)', 0xEE: '일행 대표 이름(BRK 89 C0)', 0xFA: '여럿 붙임(24:8A80)',
    0xF9: '대기(BRK 19 32)', 0xF2: '효과음·흔들림(24:886C)', 0xE4: '주인공 또는 대표(BRK 88 3E)', 0xE2: '창 바꿈(24:85A5)',
}


# 이름 문자열 글자표로는 ダ·ズ 등으로 찍히지만 전투 창에서는 다른 글자로 그려지는 바이트(메시지 118·136 을 화면에 띄워 확인).
BATTLE_GLYPHS = {0x89: '＊', 0x9A: '。', 0x9C: '「', 0x9D: '…'}


def code(rom, br):
    x = ROOT
    while True:
        v = rom.u16((NODES_1 if br.read() else NODES_0) + x)
        if v & 0x8000:
            return v & 0xFF
        x = (v & 0xFF) << 1


def message(rom, n):
    """끝 바이트까지의 바이트 목록."""
    br = BitReader(rom, rom.u24(INDEX + (n >> 4) * 3))
    for _ in range(n & 0xF):
        while code(rom, br) not in ENDS:
            pass
    out = []
    while True:
        c = code(rom, br)
        out.append(c)
        if c in ENDS:
            return out


def show(rom, data):
    out, i = [], 0
    while i < len(data):
        b = data[i]
        if b >= 0xE2:
            out.append(f'{{{b:02X}}}')
        elif b in BATTLE_GLYPHS:
            out.append(BATTLE_GLYPHS[b])
        elif b in (0x83, 0x84):
            out.append(text(string_codes(rom, bytes(data[i:i + 2]))))
            i += 1
        else:
            out.append(text(string_codes(rom, bytes([b]))))
        i += 1
    return ''.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('msgs', nargs='*', type=lambda s: int(s, 16))
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    for n in args.msgs or range(COUNT):
        print(f'{n:03X} {show(rom, message(rom, n))}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
