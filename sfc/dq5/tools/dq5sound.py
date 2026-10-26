"""DQ5(SFC) 소리 명령. 형식은 sfc/dq5/docs/dq5-sound-format.md.

게임은 소리를 [명령][인자] 두 바이트로 다룬다. 24:FE91~ 의 입구(9바이트씩, PHP / SEP #$20 / PHA / LDA #명령 /
JMP 24:FF83)가 명령 번호를 정하고, 24:FF83 이 인자와 함께 7E:1D95~(16칸) 대기열에 넣는다. 대기열은 2B:C30F~ 가
APU 포트 $2141(명령)·$2142(인자)·$2143·$2140 에 써서 보낸다.
BRK 0F~19 는 이 입구를 부르는 서비스 호출이다(00:9256, 표 00:928C). BRK 19 nn 이 명령 0C 인자 nn.
맵마다의 곡: 맵 레코드 23:FD6A[BC] + BD*6 의 +5 를 맵을 불러올 때 00:CEB1 이 명령 1A 의 인자로 보낸다.

사용:
  python sfc/dq5/tools/dq5sound.py rom/dq5.sfc            # 명령 입구, BRK 0F~19, 맵 곡 표
  python sfc/dq5/tools/dq5sound.py rom/dq5.sfc --battle   # 이벤트 무리 00~3F 의 전투 곡 등급과 곡
  python sfc/dq5/tools/dq5sound.py rom/dq5.sfc --check snd.txt
      # sfc/dq5/tools/lua/dq5sndlog.lua 의 기록에서 맵 곡(명령 1A, 00:CEB1)을 표와 견줌. --map BC/BD 로 그 맵
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5encounter import EVENT_COUNT, event_group, map_entries, map_entry, monster_name  # noqa: E402
from dq5map import Rom  # noqa: E402

ENTRIES = 0x24FE91
BRK_TABLE = 0x00928C  # BRK 0F~19 의 처리 루틴(00 뱅크 16비트)
BATTLE_SONGS = 0x268F96  # [$1014] 전투 곡. 26:8F78 이 이벤트 무리(40 미만) 첫 바이트 하위 2비트를 $1014 에 둠


def entries(rom):
    """[(입구 주소, 명령 번호)]."""
    out, a = [], ENTRIES
    while True:
        b = [rom.u8(a + i) for i in range(9)]
        if b[:5] != [0x08, 0xE2, 0x20, 0x48, 0xA9] or b[6:] != [0x4C, 0x83, 0xFF]:
            return out
        out.append((a, b[5]))
        a += 9


def brk_calls(rom):
    """BRK 0F~19 마다 (명령 번호, 끝날 때까지 기다리는지). 처리 루틴은 JSL 입구 [+ JSL 24:FE44] / RTS."""
    names = dict(entries(rom))
    out = {}
    for i in range(11):
        a = rom.u16(BRK_TABLE + i * 2)
        if rom.u8(a) == 0xBB:  # TYX: 인자를 둘째 바이트로
            a += 1
        target = rom.u24(a + 1) if rom.u8(a) == 0x22 else None
        wait = rom.u8(a + 4) == 0x22 and rom.u24(a + 5) == 0x24FE44
        out[0x0F + i] = (names.get(target), wait)
    return out


def map_songs(rom):
    return [(bc, bd, e[5]) for bc, bd, e in map_entries(rom)]


def battle_songs(rom):
    """[(무리, 등급, 곡, [(몬스터, 마릿수)])]. 이벤트 무리 00~3F 만. 마주침 무리(40 이상)는 늘 등급 0."""
    out = []
    for g in range(EVENT_COUNT):
        flags, mons, _ = event_group(rom, g)
        grade = flags & 3
        out.append((g, grade, rom.u8(BATTLE_SONGS + grade), mons))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--check')
    ap.add_argument('--map')
    ap.add_argument('--battle', action='store_true', help='이벤트 무리마다 전투 곡')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.battle:
        for g, grade, song, mons in battle_songs(rom):
            desc = ', '.join('%s(%02X) %d' % (monster_name(rom, m), m, c) for m, c in mons)
            print('%02X 등급 %d 곡 %02X  %s' % (g, grade, song, desc))
        return 0
    if args.check:
        bc, bd = (int(v, 16) for v in args.map.split('/'))
        want = map_entry(rom, bc, bd)[5]
        got = [int(f.split('=')[1], 16) for line in open(args.check)
               for f in line.split() if 'cmd=1A' in line and 'from=00:CEB1' in line and f.startswith('arg=')]
        print('%02X/%02X 표 %02X, 게임 %s' % (bc, bd, want, ' '.join('%02X' % g for g in got)))
        return 0
    print('입구     명령')
    for a, c in entries(rom):
        print('%06X  %02X' % (a, c))
    print('BRK  명령  기다림')
    for n, (c, w) in brk_calls(rom).items():
        print('%02X   %s    %s' % (n, '--' if c is None else '%02X' % c, '예' if w else ''))
    print('맵 곡(명령 1A 인자)')
    for bc, bd, s in map_songs(rom):
        print('%02X/%02X %02X' % (bc, bd, s))
    return 0


if __name__ == '__main__':
    sys.exit(main())
