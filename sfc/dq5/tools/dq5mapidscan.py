"""맵 번호 $BC·$BD 를 읽는 코드를 여러 장면(맵 걷기·출구, 대화, 필드 주문 메뉴, 필드·실내 전투, 전투 주문)에서 모은다.

장면마다 lua/dq5mapidscan.lua 가 기존 드라이버(dq5warp·dq5msg·dq5battle)를 감싸 읽은 PC 를 적는다. 모은 PC 를
읽은 값을 어떻게 쓰는지(다음 명령)로 나눈다: 비교·분기면 「견줌」, 알려진 색인 자리면 「색인」, 나머지는 「살핌」 으로 두고
명령을 보여 준다. 원본 롬·선실 상태는 읽기만 한다. 형식: sfc/dq5/docs/dq5-build-format.md 「맵 번호로 찾는 표」.
  MESENCE=… python sfc/dq5/tools/dq5mapidscan.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from kr_patch.sfc.dis65816 import decode
from kr_patch.sfc.mapper import LoROM
import dq5mesen

HERE = Path(__file__).resolve().parent
WARP, MSG, BATTLE = (str(HERE / f'lua/{n}') for n in ('dq5warp.lua', 'dq5msg.lua', 'dq5battle.lua'))
TALK = 'b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4,wait:150,a:4' + ',wait:100,a:4' * 5
# (이름, 드라이버, 시작 상태(None 이면 선실, 'battle' 이면 battle-prep 이 남긴 전투 상태), 환경)
SCENES = [
    ('walk-0103', WARP, None, {'TO': '01/03,19,6,1', 'TEST': 'down:40,left:60,down:40'}),
    ('exit-2102', WARP, None, {'TO': '21/02,111,8,1', 'TEST': 'up:16,wait:200,down:40'}),
    ('exit-0100', WARP, None, {'TO': '01/00,60,79,2', 'TEST': 'down:16,wait:200,down:30'}),
    ('high-5050', WARP, None, {'TO': '50/50,31,17,1', 'TEST': 'down:16,wait:200'}),
    ('encounter-2102', WARP, None, {'TO': '21/02,50,43', 'SETTLE': '100', 'MAXF': '1800',
                                    'TEST': 'right:150,left:150,right:150,left:150'}),
    ('talk', MSG, None, {'MAXF': '1200', 'PRE': TALK}),
    ('field-spell', MSG, None, {'MAXF': '700',
                                'PRE': 'b:4,wait:40,a:4,wait:30,right:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200'}),
    ('battle-prep', WARP, None, {'FIELD': '341,56', 'BATTLE': '00:1', 'SETTLE': '300', 'SAVE': 'battle.mss',
                                 'MAXF': '1800'}),
    ('battle', BATTLE, 'battle', {'MAXF': '2400', 'LOOP': 'a:4,wait:20'}),
    ('battle-spell', BATTLE, 'battle', {'MAXF': '650', 'LOOP': 'wait:500',
                                        'PRE': 'a:4,wait:30,down:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200'}),
]
ENV_CLEAR = ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH', 'SAVE', 'SET',
             'TEST', 'TO', 'WAGON', 'PRE', 'LOOP', 'WAYPOINTS', 'PEEK', 'SHOTMSG', 'CALLS', 'WW', 'DRIVER', 'MAXF')
# 번호로 곧장 색인하는 곳(읽은 다음 명령의 PC). 맵 포인터·맵 속성·인물 기본 목록·출구.
INDEX = {0x01930F: '맵 포인터 01:9316', 0x01931B: '맵 포인터 01:9316', 0x0183F2: '맵 속성 01:83FB',
         0x018407: '맵 속성 01:83FB', 0x128049: '인물 기본 목록 12:8050', 0x128059: '인물 기본 목록 12:8050',
         0x2AF734: '출구 2A:F732'}
COMPARE = re.compile(r'^(CMP|CPX|CPY|BEQ|BNE|BCC|BCS|BMI|BPL|BIT|AND|EOR)\b')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def run(scene, rom, state, battle, out, mesence, libdir):
    name, driver, start, extra = scene
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ENV_CLEAR}
    env.update(LIBDIR=str(libdir), STATE=str(battle if start == 'battle' else state), SHOT_DIR=str(dest),
               DRIVER=driver, **{'MAXF': '1500', 'SETTLE': '60', **extra})
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        dq5mesen.testrunner(str(mesence), str(rom), str(HERE / 'lua/dq5mapidscan.lua'),
                            '--Snes.DisableFrameSkipping=true', env=env, stdout=log, stderr=subprocess.STDOUT,
                            check=True, timeout=600)
    path = dest / 'mapid.txt'
    require(path.is_file(), f'{name}: mapid.txt 가 없음')
    return {int(pc, 16): int(n) for pc, n in (line.split() for line in path.read_text().split('\n') if line)}


def classify(data, pc):
    """읽은 다음 명령 세 개와 분류."""
    ops, at, m8, x8 = [], pc, True, True
    for _ in range(3):
        text, n, m8, x8 = decode(data, at, m8=m8, x8=x8, mapper=LoROM())
        ops.append(text[22:])
        at = (at & 0xFF0000) | ((at + n) & 0xFFFF)
    if pc in INDEX:
        return '색인', INDEX[pc], ops
    if COMPARE.match(ops[0]):
        return '견줌', '', ops
    return '살핌', '', ops


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/mapidscan')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        rom, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(WARP, libdir / 'boot.lua')
        first = [s for s in SCENES if s[2] != 'battle']
        later = [s for s in SCENES if s[2] == 'battle']
        battle = out / 'battle-prep' / 'battle.mss'
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            seen = dict(zip([s[0] for s in first],
                            pool.map(lambda s: run(s, rom, state, battle, out, mesence, libdir), first)))
            require(battle.is_file(), 'battle-prep 이 전투 상태를 남기지 않음')
            seen.update(zip([s[0] for s in later], pool.map(lambda s: run(s, rom, state, battle, out, mesence, libdir), later)))
        data = rom.read_bytes()
        rows = {}
        for name, pcs in seen.items():
            for pc in pcs:
                rows.setdefault(pc, []).append(name)
        report = []
        for pc in sorted(rows):
            kind, note, ops = classify(data, pc)
            report.append({'pc': f'{pc >> 16:02X}:{pc & 0xFFFF:04X}', 'kind': kind, 'note': note, 'next': ops,
                           'scenes': rows[pc]})
        (out / 'mapid.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        for r in report:
            if r['kind'] != '견줌':
                print(f'{r["pc"]} {r["kind"]} {r["note"]} | {" | ".join(r["next"])} | {",".join(r["scenes"])}')
        counts = {k: sum(r['kind'] == k for r in report) for k in ('색인', '견줌', '살핌')}
        print(f'장면 {len(seen)}개, PC {len(report)}곳: ' + ', '.join(f'{k} {v}' for k, v in counts.items()))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
