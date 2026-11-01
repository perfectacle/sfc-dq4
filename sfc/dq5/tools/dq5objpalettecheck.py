"""OBJ 팔레트 색·세트 팔레트 배정·맵 팔레트 쓰기를 MesenCE에서 원본과 견준다.

02/06 의 밤 인물 둘을 낮으로 바꿔 주인공 위에 세운다(dq5npcrecord.py, 세트 04 = 팔레트 1, 세트 84 = 팔레트 0).
고친 롬은 OBJ 팔레트 1 의 색을 바꾸고, 세트 84 를 팔레트 2 로 옮기고, 04/06 의 맵 팔레트(01:9A12 13번, OBJ 팔레트 3 줄)
색을 바꾼다. 원본 롬과 고친 롬에서 dq5gfxdump.lua 로 덤프하고, CGRAM OBJ 줄과 OAM 의 팔레트 번호·픽셀을
그 롬에서 예측한 값과 견준다. 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5objpalettecheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
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
from dq5objpalette import FORMAT  # noqa: E402
import dq5mesen  # noqa: E402

HERE = Path(__file__).resolve().parent
RECORDS = {'format': 'dq5npcrecord/1', 'entries': [
    {'list': '05:8CD4', 'index': 3, 'time': 'day', 'fields': {'x': 24, 'y': 12, 'facing': 'down'}},
    {'list': '05:8CD4', 'index': 2, 'time': 'day', 'fields': {'x': 28, 'y': 12, 'facing': 'down', 'gfx': 0x29}}]}
PALETTE, MOVED_SET, NEW_PALETTE, MAP_ENTRY = 1, 0x84, 2, 13
SCENES = [('0206', '02/06,24,14,1', 0x0206), ('0406', '04/06,10,10,1', 0x0406)]
DUMPF = '620,700,780'


def tool(name, *args):
    subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True, text=True,
                   timeout=300)


def run(rom, name, to, out, state, mesence, libdir):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE',
                        'ROMPATCH', 'SAVE', 'SET', 'WAGON', 'EVERY')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1500', SETTLE='120',
               TO=to, TEST='wait:400', DUMPF=DUMPF)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        dq5mesen.testrunner(str(mesence), str(rom), str(HERE / 'lua/dq5gfxdump.lua'),
                            '--Snes.DisableFrameSkipping=true', env=env, stdout=log, stderr=subprocess.STDOUT,
                            check=True, timeout=180)
    return dest


def look(rom, dest, scene):
    """덤프마다 CGRAM OBJ 줄 0~7 이 롬과 같은지(04/06 은 줄 0B 를 맵 팔레트로), OAM 묶음이 레코드 팔레트로 그려졌는지."""
    pals = [[rom.u16(S.OBJ_PALETTES + (p * 16 + i) * 2) for i in range(16)] for p in range(8)]
    entry = S.map_palettes(rom)[MAP_ENTRY]
    out = []
    for tag in DUMPF.split(','):
        name = f'f{int(tag):05d}'
        rd = lambda ext: (dest / f'{name}.{ext}').read_bytes()  # noqa: E731
        cgram = rd('cgram')
        lines = [[cgram[256 + (p * 16 + i) * 2] | cgram[257 + (p * 16 + i) * 2] << 8 for i in range(16)] for p in range(8)]
        want = [list(p) for p in pals]
        if scene == 0x0406:
            want[entry['line'] - 8] = entry['colors']
        same = [lines[p][1:] == want[p][1:] for p in range(8)]
        stats = {}
        S.compare(rom, rd('wram'), rd('vram'), rd('oam'), cgram, stats, False)
        out.append({'dump': name, 'cgram_lines_same': same, 'groups': stats.get('groups', 0),
                    'hits': stats.get('hits', 0), 'other_palette': stats.get('other_palette', 0),
                    'sets': sorted(f'{s:02X}' for s in stats.get('sets', {}))})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/objpalettecheck')
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
        base = Rom(original.read_bytes())
        # 팔레트 1 은 색마다 다른 회색·원색 띠, 맵 팔레트는 원래 색의 빨강·파랑을 바꾼 색.
        new_colors = [(i * 2) | (31 - i * 2) << 10 | (i % 4) * 8 << 5 for i in range(1, 16)]
        entry = S.map_palettes(base)[MAP_ENTRY]
        if (entry['bc'], entry['bd'], entry['line']) != (4, 6, 0x0B) or sum(
                1 for e in S.map_palettes(base) if (e['bc'], e['bd']) in ((4, 6), (4, 0xFF)) and 8 <= e['line'] <= 0x0F) != 1:
            raise ValueError('04/06 의 OBJ 줄을 덮는 맵 팔레트가 13번 하나가 아님(look 의 예측이 틀어짐)')
        new_map = [((c & 0x1F) << 10) | (c & 0x3E0) | (c >> 10) for c in entry['colors'][1:]]
        doc = {'format': FORMAT, 'palettes': [{'palette': PALETTE, 'colors': new_colors}],
               'map_palettes': [{'index': MAP_ENTRY, 'colors': new_map}],
               'sets': [{'set': f'{MOVED_SET:02X}', 'palette': NEW_PALETTE}]}
        (out / 'palette.json').write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8')
        (out / 'records.json').write_text(json.dumps(RECORDS, indent=1) + '\n', encoding='utf-8')
        tool('dq5objpalette.py', original, 'check', out / 'palette.json')
        tool('dq5objpalette.py', original, 'patch', out / 'palette.json', '-o', out / 'palette.dq5patch.json')
        tool('dq5npcrecord.py', original, 'patch', out / 'records.json', '-o', out / 'records.dq5patch.json')
        roms = {}
        for name, patches in (('original', [out / 'records.dq5patch.json']),
                              ('edited', [out / 'records.dq5patch.json', out / 'palette.dq5patch.json'])):
            roms[name] = out / f'{name}.sfc'
            tool('dq5build.py', original, 'build', *patches, '-o', roms[name], '--ips', out / f'{name}.ips')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        results = {}
        for name, rom in roms.items():
            built = Rom(rom.read_bytes())
            for scene, to, key in SCENES:
                results[f'{name}-{scene}'] = look(built, run(rom, f'{name}-{scene}', to, out, state, mesence, libdir), key)
        edited = Rom(roms['edited'].read_bytes())

        def every(case, test):
            return all(test(r) for r in results[case])

        checks = {
            'cgram': all(every(case, lambda r: all(r['cgram_lines_same'])) for case in results),
            'oam': all(every(case, lambda r: r['groups'] == r['hits'] > 0) for case in results),
            'record-palette': S.set_record(edited, MOVED_SET)['palette'] == NEW_PALETTE
            and every('edited-0206', lambda r: '84' in r['sets'] and r['other_palette'] == 0),
            'changed': S.obj_palettes(edited)[PALETTE] != S.obj_palettes(base)[PALETTE]
            and S.map_palettes(edited)[MAP_ENTRY]['colors'] != entry['colors'],
        }
        (out / 'results.json').write_text(json.dumps({'results': results, 'checks': checks}, ensure_ascii=False,
                                                     indent=2) + '\n', encoding='utf-8')
        for case, rows in results.items():
            r = rows[-1]
            print(f'{case} {r["dump"]}: CGRAM OBJ 줄 0~7 같음 {sum(r["cgram_lines_same"])}/8, OAM 묶음 {r["hits"]}/{r["groups"]}, '
                  f'세트 {" ".join(r["sets"])}')
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        if not all(checks.values()):
            raise ValueError('불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
