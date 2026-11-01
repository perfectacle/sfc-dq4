"""필드 타일 속성 표(2A:D512, 512바이트)의 값마다 걷기·배·걸음 피해를 MesenCE 에서 본다.

원본 롬에 나오는 값 18가지마다, 표 512칸을 모두 그 값으로 둔 시험 롬을 만든다. 세계 0 (341,56) 에서 오른쪽으로 48프레임
걷고(dq5warp.lua 의 TEST) 걸은 칸 수와 끝 HP(7E:2042)를 적는다. 배($1954 = 03, LATESET)로도 같은 입력을 넣어
배가 가는 값과 내리는 값을 본다. 원본 롬·선실 상태는 읽기만 하고 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5tileattrcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import collections
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from dq5map import lorom
import dq5mesen

HERE = Path(__file__).resolve().parent
TABLE, SIZE = 0x2AD512, 512
START = (341, 56)
WALK = {'FIELD': f'{START[0]},{START[1]}', 'SETTLE': '120', 'TEST': 'right:48,wait:20', 'MAXF': '1500'}
SHIP = WALK | {'LATESET': '1954=03'}
HP = 0x2042
# 값 → (걸은 칸 수, 끝 HP, 배로 걸은 칸 수, 배 끝의 $1954). 선실 상태의 주인공 HP 는 24.
# bit7 이 켜진 값은 걸어서 들어가지 못하고, 배는 80 위로만 가며 bit6 값으로 가면 내려 걷는다($1954 = 0).
# 4D 는 걸음마다 HP 1 을 잃고 그 사이 멈춰 같은 시간에 두 칸 덜 간다.
EXPECT = {**{v: (6, 24, 6, 0) for v in (0x43, 0x45, 0x4A, 0x4B, 0x4C, 0x4E, 0x50, 0x54)}, 0x4D: (4, 20, 4, 0),
          0x80: (0, 24, 6, 3), **{v: (0, 24, 0, 3) for v in (0x81, 0x82, 0x93, 0x95, 0x96, 0x97, 0x98, 0xD1)}}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def run(rom, dest, env, mesence, libdir, state):
    dest.mkdir()
    full = {k: v for k, v in os.environ.items() if k not in ('FIELD', 'TEST', 'LATESET', 'SET', 'POKE', 'TO')}
    full.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), **env)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        dq5mesen.testrunner(str(mesence), str(rom), str(HERE / 'lua/dq5warp.lua'),
                            '--Snes.DisableFrameSkipping=true', env=full, stdout=log, stderr=subprocess.STDOUT,
                            check=True, timeout=300)
    line = next(x for x in (dest / 'warp.txt').read_text(encoding='utf-8').splitlines() if ' test ' in x)
    end = re.search(r'-> field (\d+),(\d+)', line)
    require(end is not None, f'{dest.name}: 필드에서 끝나지 않음 {line}')
    wram = (dest / 'final.wram').read_bytes()
    return int(end[1]) - START[0], int.from_bytes(wram[HP:HP + 2], 'little'), wram[0x1954]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default=Path('work/tileattrcheck'))
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE 가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        data = original.read_bytes()
        at = lorom(TABLE)
        counts = collections.Counter(data[at:at + SIZE])
        require(set(counts) == set(EXPECT), f'원본 표의 값 {sorted(counts)} 이 기대 목록과 다름')
        roms = {}
        for v in EXPECT:
            patched = bytearray(data)
            patched[at:at + SIZE] = bytes([v]) * SIZE
            roms[v] = out / f'attr-{v:02X}.sfc'
            roms[v].write_bytes(patched)
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True,
                                timeout=30).stdout.strip()
        jobs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            for v in EXPECT:
                jobs[v, 'walk'] = pool.submit(run, roms[v], out / f'walk-{v:02X}', WALK, mesence, libdir, state)
                jobs[v, 'ship'] = pool.submit(run, roms[v], out / f'ship-{v:02X}', SHIP, mesence, libdir, state)
            got = {k: j.result() for k, j in jobs.items()}
        results = []
        for v, want in EXPECT.items():
            (cells, hp, _), (ship, _, vehicle) = got[v, 'walk'], got[v, 'ship']
            seen = (cells, hp, ship, vehicle)
            results.append({'value': f'{v:02X}', 'tiles': counts[v], 'walk_cells': cells, 'hp': hp, 'ship_cells': ship,
                            'ship_1954': vehicle, 'passed': seen == want})
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        for r in results:
            print(json.dumps(r, ensure_ascii=False))
        failed = [r['value'] for r in results if not r['passed']]
        require(not failed, f'불일치: {", ".join(failed)}')
        print(f'{len(results)}개 값 통과')
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
