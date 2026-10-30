"""새 게임부터 서장 끝(1장 왕좌의 방)까지 한 번에 걷는 검사(MesenCE 헤드리스).

  1. 전원부터 A 를 40프레임마다 눌러 새 게임 → 서장 상자 → 수련 → 검사의 물음(예) → 검사 퇴장.
     START_AT 프레임에 세이브스테이트를 남긴다(tools/lua/mkstate.lua).
  2. 그 상태에서 tools/lua/walk.lua 로 ROUTE 를 걷는다: 지하 문을 열고 마을로 → 개구리 → 지하의 신시아 →
     마을 집의 아버지와 저녁 → 1장 왕좌의 방.
  3. 맵이 바뀐 차례와 끝의 깃발로 판정한다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4prologuecheck.py --rom work/ch1/dq4-ch1.sfc --out work/prologuecheck
형식은 sfc/dq4/docs/dq4-prologue-format.md 「검증」.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4prologue as pro  # noqa: E402

MKSTATE = ROOT / 'tools' / 'lua' / 'mkstate.lua'
WALK = ROOT / 'tools' / 'lua' / 'walk.lua'
START_AT = 1800     # 검사가 나가고 조작이 풀린 뒤
TAP_UNTIL = 1700    # 그 앞까지 A 연타(물음은 예)


def door(face):
    """그 쪽을 보고 명령 창 「문」(첫 열 넷째 줄). 필드는 8프레임에 한 번 입력을 읽으므로 8프레임씩 누른다."""
    return f'{face}:8;wait:30;a:8;wait:60;down:4;wait:12;down:4;wait:12;down:4;wait:12;a:8;wait:90'


def talk(face):
    return f'{face}:8;wait:30;a:8;wait:60;a:8;wait:60'


def taps(n):
    """대사 넘기기. 글자를 찍는 동안 누른 A 는 남은 글자를 마저 찍을 뿐이라 쪽 수보다 넉넉히."""
    return ';'.join(['a:8;wait:50'] * n)


CLOSE = 'b:8;wait:30;b:8;wait:30'    # 남은 A 로 열린 명령 창 닫기
# DQ5 셀(FC 칸 (x, y) 는 (2x, 2y+1)). 지하 문 (3,6), 계단 (3,1), 마을 계단 (15,2), 개구리 (0F,0C) 아래 칸,
# 열 0E 를 따라 오르내림(열 0F 에는 남자), 아버지 (5,12) 의 오른쪽 칸
ROUTE = [
    ('train', '8,31;8,15;6,15;' + door('up') + ';6,9;6,3;up:24'),
    ('frog', '42,7;42,9;28,9;28,27;30,27;' + talk('up') + ';' + taps(60) + ';wait:300'),
    ('cellar', CLOSE + ';28,27;28,9;42,9;42,7;42,5;up:24;wait:60;6,11;' + door('down') +
     ';6,15;8,15;8,31;6,31;' + talk('up') + ';' + taps(60) + ';wait:300'),
    ('supper', CLOSE + ';8,30;8,15;6,15;6,3;up:24;wait:60;42,7;42,9;28,9;28,37;12,37;' + talk('left') + ';' +
     taps(70) + ';wait:600'),
]
MAPS = ['3C/00', '3C/01', '3C/00', '36/01']
FLAGS = {'DONE': pro.DONE, 'FROG_MET': pro.FROG_MET, 'SHINSIA_MET': pro.SHINSIA_MET, 'DINNER': pro.DINNER,
         'CHAPTER1': (0x0E, 0x04)}


def run(mesence, rom, script, dest, env, timeout):
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(rom, dest / 'c.sfc')
    full = {**os.environ, **env, 'SHOT_DIR': str(dest)}
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(dest / 'c.sfc'), str(script), '--Snes.DisableFrameSkipping=true'],
                       cwd=dest, env=full, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)


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
    # 1장 첫머리 시험과 같은 부팅 입력(A 연타에 Y 를 150프레임마다)
    seq = ','.join(f'y@{f}:2' for f in range(900, 1600, 150))
    run(mesence, rom, MKSTATE, out / 'start', {'SAVEAT': str(START_AT), 'STATE': 'start.mss', 'MAXF': str(START_AT + 10),
                                               'EVERY': '0', 'PERIOD': '40', 'TAP': 'a', 'TAPUNTIL': str(TAP_UNTIL),
                                               'SEQ': seq}, 200)
    state = out / 'start' / 'start.mss'
    if not state.exists():
        raise SystemExit('세이브스테이트를 만들지 못함')
    watch = ';'.join(f'{k}=7E{0x2190 + i:04X}:1' for k, (i, _) in FLAGS.items())
    run(mesence, rom, WALK, out / 'walk', {'STATE': str(state), 'WAYPOINTS': ';'.join(w for _, w in ROUTE),
                                           'MAXF': '16000', 'CHANGES': str(len(MAPS) + 8), 'WATCH': watch}, 600)
    text = (out / 'walk' / 'walk.txt').read_text(encoding='utf-8') if (out / 'walk' / 'walk.txt').exists() else ''
    maps = re.findall(r'map \w\w/\w\w -> (\w\w/\w\w)', text)
    seen = {k: int(v, 16) for k, v in re.findall(r'^(\w+)=([0-9A-F]+)$', text, re.M)}
    flags = {k: bool(seen.get(k, 0) & m) for k, (_, m) in FLAGS.items()}
    ok = maps == MAPS and all(flags.values())
    report = {'status': 'passed' if ok else 'failed', 'maps': maps, 'want_maps': MAPS, 'flags': flags}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
