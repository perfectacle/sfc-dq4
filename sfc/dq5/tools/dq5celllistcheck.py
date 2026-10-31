"""슬롯 칸 목록(7E:8000 주소 표, 7E:8060~ 칸 워드)이 어디서 깨지는지 MesenCE 에서 잰다.

02/06 의 두 인물을 눕힌 롬(dq5spritewritecheck.py 의 lying-right 과 같은 엔트리)에서, 맵을 불러올 때 칸 목록 자리를
lua/dq5cellshift.lua 로 옮기고 dq5gfxdump.lua 로 덤프해 dq5sprite.py 의 비교(VRAM 타일·칸 목록·OAM 묶음 픽셀)로 본다.
  shift-XX   $1A2B = XX: 목록 일곱 개가 7E:8060 + XX00 부터 놓인다
  ptr-XX     $1A2C = XX: 첫 목록 주소가 7E:8000 + XX 에 적힌다(주소 표는 7E:805F 까지 48칸)
기대: 목록이 모두 7E:9000 밑이거나(shift-0D) 누운 인물의 돌린 타일 자리(이 맵에서 7E:9000~928F) 위면(shift-13·20)
그대로이고, 누운 세트 둘의 목록이 7E:9040·90A0 에 걸리면(shift-0E) 그 둘이 깨진다. 주소 표 일곱째가 7E:805E 에
들면(ptr-52) 그대로이고 7E:8060 을 넘으면(ptr-54) 첫 목록(주인공)의 첫 칸을 덮어 주인공이 깨진다. 깨진 두 경우는
디코더와 맞는 OAM 묶음 수도 shift-00 보다 줄어야 한다.
원본 롬·선실 상태는 읽기만 하고 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5celllistcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5sprite as S  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5spritewritecheck import lay_down, pose_records  # noqa: E402

HERE = Path(__file__).resolve().parent
# 이름: (SHIFT, PTR, 그대로여야 하는지, 깨져야 할 세트)
CASES = {'shift-00': ('0', '0', True, ()), 'shift-0D': ('D', '0', True, ()), 'shift-0E': ('E', '0', False, ('04', '84')),
         'shift-13': ('13', '0', True, ()), 'shift-20': ('20', '0', True, ()),
         'ptr-52': ('0', '52', True, ()), 'ptr-54': ('0', '54', False, ('82',))}
SETS = ('00', '04', '82', '84')


def tool(name, *args):
    subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True, text=True,
                   timeout=300)


def run(name, rom_path, rom, out, state, mesence, libdir):
    shift, ptr, _, _ = CASES[name]
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ('POKE', 'ROMPATCH', 'SET', 'LATESET', 'SAVE', 'EVERY')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1500', SETTLE='120',
               TO='02/06,24,14,1', TEST='wait:400', DUMPF='620,700,780,860', SHIFT=shift, PTR=ptr,
               INNER=str(HERE / 'lua/dq5gfxdump.lua'))
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom_path), str(HERE / 'lua/dq5cellshift.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=200)
    stats = {}
    tags = sorted(p.stem for p in dest.glob('f[0-9]*.wram'))
    if not tags:
        raise ValueError(f'{name}: 덤프가 없음')
    for tag in tags:
        rd = lambda ext: (dest / f'{tag}.{ext}').read_bytes()  # noqa: E731
        S.compare(rom, rd('wram'), rd('vram'), rd('oam'), rd('cgram'), stats, False)
    wram = (dest / f'{tags[-1]}.wram').read_bytes()
    count = (wram[0x1A2C] | wram[0x1A2D] << 8) // 2
    base = 0x8000 + int(ptr, 16)
    lists = [wram[base + i * 2] | wram[base + i * 2 + 1] << 8 for i in range(count - int(ptr, 16) // 2)]
    sets = {f'{s:02X}': v for s, v in stats.get('sets', {}).items()}
    return {'lists': [f'{a:04X}' for a in lists], 'sets': sets, 'groups': stats.get('groups', 0),
            'hits': stats.get('hits', 0), 'shown': sorted({f'{s:02X}' for s, _, _ in stats.get('frames', set())})}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/celllistcheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            if not path.is_file():
                raise ValueError(f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        (out / 'lying.json').write_text(json.dumps(pose_records('right'), indent=1) + '\n', encoding='utf-8')
        tool('dq5npcrecord.py', original, 'patch', out / 'lying.json', '-o', out / 'lying.dq5patch.json')
        rom_path = out / 'lying.sfc'
        tool('dq5build.py', original, 'build', out / 'lying.dq5patch.json', '--size', '2', '-o', rom_path)
        rom_path.write_bytes(lay_down(rom_path.read_bytes()))
        rom = Rom(rom_path.read_bytes())
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {n: pool.submit(run, n, rom_path, rom, out, state, mesence, libdir) for n in CASES}
            results = {n: job.result() for n, job in jobs.items()}
        failed = []
        for name, (_, _, intact, broken) in CASES.items():
            r = results[name]
            good = [s for s in SETS if s in r['sets'] and r['sets'][s][0] == r['sets'][s][1] and s in r['shown']]
            r['intact'] = good
            # 깨진 경우는 디코더와 맞는 OAM 묶음 수도 그대로인 shift-00 보다 줄어야 한다(지워진 목록의 인물이 빠지거나 틀림).
            ok = (good == list(SETS) and r['groups'] == r['hits'] > 0) if intact else \
                (sorted(set(SETS) - set(good)) == sorted(broken) and r['hits'] < results['shift-00']['hits'])
            r['passed'] = ok
            print(f'{name}: 목록 {" ".join(r["lists"])}, 그대로인 세트 {" ".join(good)}, OAM 묶음 {r["hits"]}/{r["groups"]}'
                  f'{"" if ok else " 불일치"}')
            if not ok:
                failed.append(name)
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if failed:
            raise ValueError('불일치: ' + ', '.join(failed))
        print(f'{len(CASES)}개 검사 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
