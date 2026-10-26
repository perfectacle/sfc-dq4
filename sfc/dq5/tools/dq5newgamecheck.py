"""새 게임 일행 쓰기를 MesenCE 로 전원부터 돌려, 첫 장면의 WRAM 이 쓴 값과 같은지 본다.

원본 롬과 고친 롬(금화 1234, 주인공 레벨 3·물건 셋, 23:C014 칸 3 ビアンカ 를 둘째로, 걷는 수 2)을 처음 쓰는
이름의 사본으로 켜고 6,600프레임에 7E:2000~ 을 견준다. 이름 입력이 쓰는 주인공 이름(7E:2001~2008)과 게임이
나중에 쓰는 7E:2033 은 견주지 않는다. 롬·기록은 --out 의 새 폴더에만 쓴다.
  MESENCE=… python sfc/dq5/tools/dq5newgamecheck.py rom/dq5.sfc
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from dq5map import Rom
from dq5newgame import HEADER_SIZE, new_game

HERE = Path(__file__).resolve().parent
SKIP = set(range(0x01, 0x09)) | {0x33}
DOC = {'format': 'dq5newgame/1', 'gold': 1234, 'walking': 2,
       'members': [{'base': 0, 'level': 3, 'hp': 40, 'max_hp': 40, 'items': [0, 66, 0xA1], 'equipped': [0, 1]},
                   {'base': 3, 'level': 5}]}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run(mesence, libdir, rom, dest):
    dest.mkdir(parents=True)
    # MesenCE 는 롬 파일 이름마다 SRAM 을 남기므로, 처음 쓰는 이름으로 복사해 빈 SRAM 으로 켠다.
    copy = dest / f'dq5ng-{dest.parent.name}-{dest.name}.sfc'
    shutil.copyfile(rom, copy)
    env = os.environ.copy()
    env.update(LIBDIR=libdir, SHOT_DIR=str(dest))
    with (dest / 'mesen.log').open('w') as log:
        subprocess.run([str(mesence), '--testrunner', str(copy), str(HERE / 'lua/dq5newgamecheck.lua'),
                        '--Snes.DisableFrameSkipping=true', '--Snes.RamPowerOnState=AllZeros'],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
    copy.unlink()
    return (dest / 'newgame.txt').read_text().strip(), (dest / 'final.wram').read_bytes()


def compare(name, rom_path, text, ram):
    head, records = new_game(Rom(rom_path.read_bytes()))
    require(text.endswith('map 17/00'), f'{name}: 첫 장면 17/00 에 닿지 않음({text})')
    bad = [f'20{i:02X}' for i in range(HEADER_SIZE) if i not in SKIP and ram[0x2000 + i] != head[i]]
    bad += [f'{0x2040 + i:04X}' for i in range(len(records)) if ram[0x2040 + i] != records[i]]
    require(not bad, f'{name}: 쓴 값과 다른 WRAM {bad[:8]}')
    return {'case': name, 'members': len(records) // 0x2A, 'gold': int.from_bytes(ram[0x2019:0x201C], 'little'),
            'count': ram[0x201D], 'walking': ram[0x201E], 'order': list(ram[0x2020:0x2020 + ram[0x201D]]),
            'compared': HEADER_SIZE - len(SKIP) + len(records)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/newgamecheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, mesence = args.rom.resolve(), Path(args.mesence).resolve()
        for path in (original, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        (out / 'newgame.json').write_text(json.dumps(DOC, indent=2) + '\n')
        for tool, extra in (('dq5newgame.py', ['patch', out / 'newgame.json', '--at', '3C:8000',
                                               '-o', out / 'newgame.patch.json']),
                            ('dq5build.py', ['build', out / 'newgame.patch.json', '-o', out / 'party.sfc',
                                             '--ips', out / 'party.ips'])):
            subprocess.run([sys.executable, str(HERE / tool), str(original), *map(str, extra)], check=True,
                           capture_output=True, text=True, timeout=120)
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], check=True, capture_output=True, text=True,
                                timeout=30).stdout.strip()
        cases = [('original', original), ('party', out / 'party.sfc')]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            seen = list(pool.map(lambda c: run(mesence, libdir, c[1], out / c[0]), cases))
        results = [compare(name, path, *result) for (name, path), result in zip(cases, seen)]
        require(results[1]['gold'] == 1234 and results[1]['count'] == 2 and results[1]['walking'] == 2,
                '고친 롬의 금화·일행 수·걷는 수가 쓴 값과 다름')
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps(results))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
