"""통합 빌드의 text(over)로 고친 보행 메시지가 DQ4 1장 게임의 대화 창에 뜨는지 화면으로 견준다(MesenCE 헤드리스).

고정 롬(1장 롬)과 통합 빌드 롬을 dq4 트랙의 서장 검사(dq4prologuecheck.py)와 같은 부팅·길로 돌린다.
lua/dq5inlinecheck.lua 가 24:8BAF 에 온 메시지 번호와 프레임을 남기고 SHOTS 프레임마다 화면을 찍는다.
두 롬에서 --message 가 처음 불린 프레임이 같아야 하고, 그 뒤 창 자리(y 128~215)가 다른 장이 있어야 한다.
창이 다른 첫 장부터 창이 같아질 때까지의 마지막 장을 나란히 붙여 side.png 로 남긴다(글자는 사람이 읽는다).

  MESENCE=… LIBDIR=… python sfc/dq5/tools/dq5textovercheck.py work/ch1/dq4-ch1-full.sfc work/port/build/port.sfc \\
      --message CA8 --out work/textovercheck
고칠 메시지는 서장 길(새 게임 ~ 1장 왕좌의 방, 5,000프레임 안)에서 불리는 것이어야 한다.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parents[1] / 'dq4' / 'tools'), str(HERE)]
import dq4prologuecheck as pc  # noqa: E402

PROBE = HERE / 'lua' / 'dq5inlinecheck.lua'
WALK = ROOT / 'tools' / 'lua' / 'walk.lua'
WINDOW = (0, 128, 256, 216)
SPAN = 400      # 메시지가 불린 뒤 찍는 프레임 수(10프레임마다)
MAXF = 5000


def play(mesence, rom, dest, shots, maxf):
    """부팅 상태를 만들고 서장 길을 걸어 (메시지 번호 → 처음 불린 프레임 목록)을 돌려준다."""
    seq = ','.join(f'y@{f}:2' for f in range(900, 1600, 150))
    start = dest / 'start'
    if not (start / 'start.mss').exists():
        pc.run(mesence, rom, pc.MKSTATE, start, {'SAVEAT': str(pc.START_AT), 'STATE': 'start.mss',
                                                 'MAXF': str(pc.START_AT + 10), 'EVERY': '0', 'PERIOD': '40',
                                                 'TAP': 'a', 'TAPUNTIL': str(pc.TAP_UNTIL), 'SEQ': seq}, 200)
    if not (start / 'start.mss').exists():
        raise ValueError(f'세이브스테이트를 만들지 못함: {rom}')
    walk = dest / ('walk' if not shots else 'shots')
    pc.run(mesence, rom, PROBE, walk, {'STATE': str(start / 'start.mss'), 'DRIVER': str(WALK),
                                       'WAYPOINTS': ';'.join(w for _, w in pc.ROUTE), 'MAXF': str(maxf),
                                       'CHANGES': '99', 'SHOTS': ','.join(map(str, shots))}, 900)
    found = {}
    for f, number in re.findall(r'^f(\d+) message ([0-9A-F]{4})$', (walk / 'inline.txt').read_text(), re.M):
        found.setdefault(int(number, 16), []).append(int(f))
    return walk, found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('fixed', type=Path, help='고정 롬(1장 롬)')
    ap.add_argument('port', type=Path, help='text(over) 작업을 넣은 통합 빌드 롬')
    ap.add_argument('--message', required=True, type=lambda v: int(v, 16), help='고친 메시지 번호(16진)')
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    if not os.environ.get('MESENCE') or not os.environ.get('LIBDIR'):
        ap.error('MESENCE 와 LIBDIR 가 필요함')
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        ap.error(f'{out} 이 비어 있지 않음')
    try:
        roms = {'fixed': args.fixed.resolve(), 'port': args.port.resolve()}
        first = {}
        for name, rom in roms.items():
            _, found = play(mesence, rom, out / name, (), MAXF)
            if args.message not in found:
                raise ValueError(f'{name}: 메시지 {args.message:X} 가 서장 길에서 불리지 않음')
            first[name] = found[args.message][0]
        if first['fixed'] != first['port']:
            raise ValueError(f'메시지가 불린 프레임이 다름: {first}')
        at = first['fixed'] - first['fixed'] % 10
        shots = list(range(at, at + SPAN, 10))
        dirs = {name: play(mesence, rom, out / name, shots, at + SPAN + 10)[0] for name, rom in roms.items()}
        crop = {name: [Image.open(d / f'f{f:04d}.png').convert('RGB') for f in shots] for name, d in dirs.items()}
        differs = [f for f, a, b in zip(shots, crop['fixed'], crop['port'])
                   if ImageChops.difference(a.crop(WINDOW), b.crop(WINDOW)).getbbox()]
        report = {'message': f'{args.message:X}', 'called_at': first['fixed'], 'window_differs': differs}
        if differs:
            # 같은 창이 다 찍힌 뒤의 장(창이 다른 연속 구간의 끝)
            last = differs[0]
            while last + 10 in differs:
                last += 10
            k = shots.index(last)
            side = Image.new('RGB', (512, 224))
            side.paste(crop['fixed'][k], (0, 0))
            side.paste(crop['port'][k], (256, 0))
            side.resize((1024, 448), Image.NEAREST).save(out / 'side.png')
            report['side'] = f'f{last:04d}'
        (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
        return 0 if differs else 1
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
