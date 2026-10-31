"""서장 자동 대화까지의 시각을 재는 프로브(MesenCE 헤드리스).

서장 걷기 검사(dq4prologuecheck.py)와 같은 입력으로 새 게임부터 수련 뒤 세이브스테이트를 만들고, 그 상태에서 같은 길을
걷는다. 두 실행 모두 lua/dq4talkdelay.lua 로 감싸 메시지 루틴·닫기 대기의 처음과 끝·서장 네이티브 루틴 진입·주인공
자리를 프레임과 함께 OUT/start/talkdelay.txt, OUT/walk/talkdelay.txt 에 적는다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4talkdelay.py --rom work/ch1/dq4-ch1-full.sfc --out work/talkdelay
형식은 sfc/dq4/docs/dq4-prologue-format.md 「자동 대화까지의 시각」.
"""
import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4prologue as pro  # noqa: E402
import dq4prologuecheck as pc  # noqa: E402

PROBE = HERE / 'lua' / 'dq4talkdelay.lua'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    rom = args.rom.resolve()
    _, at = pro.native()
    native = ';'.join(f'{k}={v:06X}' for k, v in at.items())
    seq = ','.join(f'y@{f}:2' for f in range(900, 1600, 150))
    pc.run(mesence, rom, PROBE, out / 'start', {'NATIVE': native, 'WALKLUA': str(pc.MKSTATE), 'SAVEAT': str(pc.START_AT),
                                                 'STATE': 'start.mss', 'MAXF': str(pc.START_AT + 10), 'EVERY': '0',
                                                 'PERIOD': '40', 'TAP': 'a', 'TAPUNTIL': str(pc.TAP_UNTIL), 'SEQ': seq}, 200)
    state = out / 'start' / 'start.mss'
    if not state.exists():
        raise SystemExit('세이브스테이트를 만들지 못함')
    pc.run(mesence, rom, PROBE, out / 'walk', {'NATIVE': native, 'WALKLUA': str(pc.WALK), 'STATE': str(state),
                                                'WAYPOINTS': ';'.join(w for _, w in pc.ROUTE), 'MAXF': '16000',
                                                'CHANGES': str(len(pc.MAPS) + 8)}, 600)
    for name in ('start', 'walk'):
        if not (out / name / 'talkdelay.txt').exists():
            raise SystemExit(f'{name}: 기록이 없음')
    return 0


if __name__ == '__main__':
    sys.exit(main())
