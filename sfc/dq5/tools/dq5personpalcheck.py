"""세계 0 낮밤 인물 팔레트(dq5fieldgfxwrite 의 person_palettes, CGRAM 11·12번 줄)를 ラナルータ 뒤에 MesenCE 에서 본다.

시험 롬 pp: 낮 팔레트 30색을 모두 001F, 밤 팔레트를 모두 7C00 으로(원본에서 dq5fieldgfxwrite patch).
장면: 세계 0 (310,60) 에 낮($075E = 0020), 시간 멈춤(7E:2190 bit1)을 끄고 주문을 배운 것으로(7E:2063 = FF) 서서
ラナルータ 를 두 번 외운다(주문 목록 다섯째 칸 23:BE28+4 를 37 로,
조우 판정 23:E7C2 를 CLC / RTL 로). 외우기 전·첫 번째 뒤·두 번째 뒤에 덤프하고, 그때 $075E 로 고른 시간대(01:A132 의
표, 색인 0C 이상이면 밤)의 인물 팔레트가 CGRAM 11·12번 줄 색 1~15 에 있는지 본다. 원본 롬도 같은 장면을 돌려 $075E 가
같게 바뀌었는지 견준다.

  MESENCE=… python sfc/dq5/tools/dq5personpalcheck.py rom/dq5.sfc --state work/state/ship.mss --out work/personpalcheck
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dq5fieldgfxcheck as fgc  # noqa: E402
import dq5fieldgfxwrite as fgw  # noqa: E402
import dq5gfxwritecheck as gwc  # noqa: E402
from dq5gfxlimitcheck import LANA  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5watercheck import frame  # noqa: E402

require, command = fgc.require, fgc.command
FRAMES = (600, 1750, 2850)
SCENE = {'FIELD': '310,60', 'SET': '2063=FF;2044=63;2050=63;075E=20;075F=00;2190&FD', 'ROMPATCH': '11BE2C=37;11E7C2=186B',
         'SETTLE': '60', 'MAXF': '3100', 'DUMPF': ','.join(map(str, FRAMES)),
         'TEST': 'wait:300,' + LANA + 'wait:200,' + LANA + 'wait:300'}
COLORS = {'day': 0x001F, 'night': 0x7C00}


def night(rom, t):
    """01:A132 처럼 world0_times 에서 $075E 의 시간대 벌을 고르고, world0_night_from 이상이면 밤."""
    now = fgw.current(rom)
    k = [s for lo, s in now['world0_times'] if lo <= t][-1]
    return k >= now['world0_night_from']


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default=Path('work/personpalcheck'))
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
        src = out / 'src'
        doc = fgw.dump(Rom(original.read_bytes()), src)
        doc['person_palettes'] = {k: [c] * 30 for k, c in COLORS.items()}
        (src / 'pp.json').write_text(json.dumps(doc), encoding='utf-8')
        command('dq5fieldgfxwrite.py', original, 'patch', src / 'pp.json', '-o', out / 'pp-patch.json')
        pp = out / 'pp.sfc'
        command('dq5build.py', original, 'build', out / 'pp-patch.json', '-o', pp, '--ips', out / 'pp.ips')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True,
                                    timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        gfx = HERE / 'lua/dq5gfxdump.lua'
        cases = [('pp', pp), ('orig', original)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            dirs = dict(zip([c[0] for c in cases], pool.map(
                lambda c: gwc.run(mesence, c[1], gfx, SCENE, out / c[0], libdir, state), cases)))
        rom, results = Rom(pp.read_bytes()), []
        for n in FRAMES:
            w, ow, cg = frame(dirs['pp'], n, 'wram'), frame(dirs['orig'], n, 'wram'), frame(dirs['pp'], n, 'cgram')
            t, ot = w[0x75E] | w[0x75F] << 8, ow[0x75E] | ow[0x75F] << 8
            require(w[0x1949] == 0 and not w[0xBE] & 0x80, f'{n}프레임: 세계 0 필드가 아님')
            require(t == ot, f'{n}프레임: $075E {t:04X} 가 원본 게임 {ot:04X} 와 다름')
            kind = 'night' if night(rom, t) else 'day'
            person = [fgc.cg_color(cg, row, c) for row in (11, 12) for c in range(1, 16)]
            require(person == [COLORS[kind]] * 30, f'{n}프레임 $075E {t:04X}: 11·12번 줄이 {kind} 인물 팔레트가 아님')
            results.append({'frame': n, '075E': f'{t:04X}', 'person': kind})
        require(len({r['person'] for r in results}) == 2, f'ラナルータ 로 낮밤이 바뀌지 않음 {results}')
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(json.dumps(results, ensure_ascii=False))
        print(f'{len(results)}/{len(results)} 통과')
        return 0
    except (OSError, ValueError, KeyError, IndexError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
