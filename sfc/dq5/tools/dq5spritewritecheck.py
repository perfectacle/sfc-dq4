"""인물 스프라이트 세트 쓰기를 MesenCE에서 원본과 견준다.

02/06 기본 목록의 밤 인물 둘을 낮으로 바꿔 주인공 위에 세우고(dq5npcrecord.py), 그 둘과 걷는 인물의 그림을 바꾼다.
  세트 04(6타일, 그림 18): 다른 6타일 세트의 그림으로
  세트 84(8타일, 그림 29): 다른 8타일 세트의 그림으로
  새 세트 70(6타일): 방향·프레임마다 다른 시험 무늬, 그림 2B 를 70 으로
늘린 표 롬(grown)은 --sets-at 으로 세트 표를 256칸으로 옮기고, 세트 04 와 새 세트 70 은 위와 같게, 그림 29 는 세트 84 대신
새 8타일 세트 FF(세트 84 의 시험 그림, 팔레트 2)로 잇는다.
다시 늘린 롬(regrown)은 grown 롬 위에 dq5spritewrite.py 를 한 번 더 돌린다. --sets-at 없이 새 세트를 더하면 거부되는지 보고,
--regrow-at 으로 표를 다시 옮기며 새 세트 71(무늬, 팔레트 1)을 더해 그림 2B 를 잇는다.
원본 롬과 고친 롬에서 dq5gfxdump.lua 로 WRAM·VRAM·OAM·CGRAM 을 덤프하고, 각 롬을 dq5sprite.py 의 비교(VRAM 타일·칸 목록·
OAM 묶음 픽셀)로 본다. 시험 그림은 롬에서 뽑으므로 --out 의 새 하위 폴더에만 둔다.
방향 롬(face-*)은 같은 둘을 이동 간격 0 으로 세워 위·왼쪽·오른쪽을 보게 하고, 누운 롬(lying-*)은 둘의 엔트리 기타 bit7 을
켜(Y 바이트도 1 올림, 1E:DB44 가 빼는 몫) 네 방향으로 눕게 한다. 원본 롬과 edited 롬 위에 같은 엔트리 바이트를 써서
서 있는 아래 아닌 방향과 누운 모양이 화면(OAM)에 디코더 그대로 나오는지 본다.
  MESENCE=… python sfc/dq5/tools/dq5spritewritecheck.py rom/dq5.sfc --state work/state/ship.mss
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

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5sprite as S  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5npc import list_entries  # noqa: E402
from dq5npcrecord import offsets  # noqa: E402
from dq5spritewrite import FORMAT, apply, dump_image, patch  # noqa: E402
import dq5mesen  # noqa: E402

HERE = Path(__file__).resolve().parent
RECORDS = {'format': 'dq5npcrecord/1', 'entries': [
    {'list': '05:8CD4', 'index': 3, 'time': 'day', 'fields': {'x': 24, 'y': 12, 'facing': 'down'}},
    {'list': '05:8CD4', 'index': 2, 'time': 'day', 'fields': {'x': 28, 'y': 12, 'facing': 'down', 'gfx': 0x29}}]}
SIMPLE, OVERLAP, NEW, NEW_GFX = 0x04, 0x84, 0x70, 0x2B
NPC_LIST, NPC_INDEXES = 0x058CD4, (3, 2)
# 이름: (방향, 누움). 둘 다 이동 간격 0 으로 세운다.
POSES = {'face-up': ('up', False), 'face-left': ('left', False), 'face-right': ('right', False),
         'lying-up': ('up', True), 'lying-down': ('down', True), 'lying-right': ('right', True), 'lying-left': ('left', True)}
# 제자리 걸음 롬(step-*): 위 자세처럼 세우되 7E:2191 을 0 으로 붙잡아 05:8D0B 인물이 메시지 1D1 창을 열지 않게 한다.
# 창이 열려 있으면 인물이 모두 멈춰 걸음 프레임 1 이 나오지 않는다. 덤프는 걸음이 바뀌는 사이(약 16프레임)보다 촘촘히.
STEPS = {'step-down': 'down', 'step-up': 'up', 'step-left': 'left', 'step-right': 'right'}
STEP_HOLD = '7E2191=00'
STEP_DUMPS = '620,628,636,644,652,660,668,676'
GROWN, GROWN_GFX, GROWN_PALETTE = 0xFF, 0x29, 2
REGROWN, REGROWN_PALETTE = 0x71, 1


def pattern(path):
    """방향·프레임마다 다른 6타일 시험 무늬. 프레임 1 은 위 네 타일을 프레임 0 과 나눠 쓴다(타일 32개)."""
    grid = [[0] * 32 for _ in range(96)]
    for row in range(4):
        for f in (0, 1):
            for y in range(24):
                for x in range(16):
                    top = y < 16
                    edge = x in (0, 15) or y in (0, 23)
                    color = 2 + row if edge else (8 + row if (x + y + (0 if top else 3 * f)) % 4 == 0 else 0)
                    if not top and (x + 2 * f) % 5 == 0:
                        color = 12 + f
                    grid[row * 24 + y][f * 16 + x] = color
    image = Image.new('P', (32, 96))
    image.putpalette([c for i in range(16) for c in (i * 16, 255 - i * 16, (i * 64) % 256)])
    image.putdata([c for line in grid for c in line])
    image.save(path)


def donor(rom, layout, limit, exclude):
    """타일 수가 limit 이하인 같은 배치의 다른 세트 중 가장 큰 것(그림이 눈에 띄게 다르게)."""
    best = None
    for s in S.set_numbers(rom):
        rec = S.set_record(rom, s)
        if rec and rec['layout'] == layout and s not in exclude and rec['tiles'] <= limit:
            if best is None or rec['tiles'] > best[1]:
                best = (s, rec['tiles'])
    return best[0]


def tool(name, *args):
    subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True, text=True,
                   timeout=300)


def run(rom, name, out, state, mesence, libdir, dumps='620,700,780,860', poke=None):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE',
                        'ROMPATCH', 'SAVE', 'SET', 'WAGON', 'EVERY')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1500', SETTLE='120',
               TO='02/06,24,14,1', TEST='wait:400', DUMPF=dumps)
    if poke:
        env['POKE'] = poke
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        dq5mesen.testrunner(str(mesence), str(rom), str(HERE / 'lua/dq5gfxdump.lua'),
                            '--Snes.DisableFrameSkipping=true', env=env, stdout=log, stderr=subprocess.STDOUT,
                            check=True, timeout=180)
    return dest


def pose_records(facing):
    return {'format': 'dq5npcrecord/1', 'entries': [
        {**e, 'fields': {**e['fields'], 'facing': facing, 'interval': 0}} for e in RECORDS['entries']]}


def step_records(facing):
    """pose_records 와 같되 엔트리 2 의 추가 값(걷기·서기 애니메이션 간격, 원래 0/0 이라 제자리 걸음을 하지 않음)을
    추가 값이 없는 엔트리 3 과 같은 F/F 로 둔다."""
    doc = pose_records(facing)
    doc['entries'][1]['fields'].update(walk_anim=15, stand_anim=15)
    return doc


def lay_down(data):
    """02/06 의 두 인물 엔트리(낮 필드)에 기타 bit7(누움)을 켜고 Y 바이트를 1 올린다(디코더 dq5npcrecord.decode 와 같은 셈)."""
    out = bytearray(data)
    rom = Rom(bytes(out))
    entries = list_entries(rom, NPC_LIST)
    for index in NPC_INDEXES:
        at, size = entries[index]
        where = offsets(bytes(out[lorom(at):lorom(at) + size]))['day']
        misc, y = lorom(at) + where['misc'], lorom(at) + where['y']
        if out[misc] & 0x80 or out[y] & 0x7F == 0x7F:
            raise ValueError(f'{at:06X}: 이미 누웠거나 Y 를 올릴 수 없음')
        out[misc] |= 0x80
        out[y] = out[y] & 0x80 | (out[y] & 0x7F) + 1
    return bytes(out)


def compare(rom, dest):
    stats = {}
    tags = sorted(p.stem for p in dest.glob('f[0-9]*.wram'))
    if not tags:
        raise ValueError(f'{dest.name}: 덤프가 없음')
    for tag in tags:
        rd = lambda ext: (dest / f'{tag}.{ext}').read_bytes()
        S.compare(rom, rd('wram'), rd('vram'), rd('oam'), rd('cgram'), stats, False)
    sets = {f'{s:02X}': v for s, v in stats.get('sets', {}).items()}
    frames = sorted(f'{s:02X} {d}{f}' for s, d, f in stats.get('frames', set()))
    return {'dumps': len(tags), 'sets': sets, 'groups': stats.get('groups', 0), 'hits': stats.get('hits', 0),
            'other_palette': stats.get('other_palette', 0), 'frames': frames}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/spritewritecheck')
    ap.add_argument('--at', default='3A:8000', help='원래 자리에 들어가지 않는 자료를 놓을 곳(dq5spritewrite.py --at)')
    ap.add_argument('--sets-at', default='3B:8000', help='늘린 세트 표와 레코드를 놓을 곳(dq5spritewrite.py --sets-at)')
    ap.add_argument('--regrow-at', default='3C:8000', help='grown 롬의 표와 레코드를 다시 옮길 곳')
    ap.add_argument('--regrow-data-at', default='3D:8000', help='regrown 롬에 더하는 세트의 타일 자료를 놓을 곳')
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
        simple = donor(base, 'simple', S.set_record(base, SIMPLE)['tiles'], {SIMPLE})
        overlap = donor(base, 'overlap', S.set_record(base, OVERLAP)['tiles'], {OVERLAP})
        dump_image(base, simple, out / 'simple.png')
        dump_image(base, overlap, out / 'overlap.png')
        pattern(out / 'pattern.png')
        doc = {'format': FORMAT, 'sets': [{'set': f'{SIMPLE:02X}', 'image': 'simple.png'},
                                          {'set': f'{OVERLAP:02X}', 'image': 'overlap.png'}],
               'new_sets': [{'set': f'{NEW:02X}', 'image': 'pattern.png', 'palette': 0}],
               'gfx': [{'gfx': f'{NEW_GFX:02X}', 'set': f'{NEW:02X}'}]}
        (out / 'sprite.json').write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8')
        grown_doc = {'format': FORMAT, 'sets': doc['sets'][:1],
                     'new_sets': doc['new_sets'] + [{'set': f'{GROWN:02X}', 'image': 'overlap.png', 'palette': GROWN_PALETTE}],
                     'gfx': doc['gfx'] + [{'gfx': f'{GROWN_GFX:02X}', 'set': f'{GROWN:02X}'}]}
        (out / 'grown.json').write_text(json.dumps(grown_doc, indent=1) + '\n', encoding='utf-8')
        (out / 'records.json').write_text(json.dumps(RECORDS, indent=1) + '\n', encoding='utf-8')
        tool('dq5spritewrite.py', original, 'check', out / 'sprite.json', '--at', args.at)
        tool('dq5spritewrite.py', original, 'patch', out / 'sprite.json', '-o', out / 'sprite.dq5patch.json', '--at', args.at)
        grown_args = ('--at', args.at, '--sets-at', args.sets_at)
        tool('dq5spritewrite.py', original, 'check', out / 'grown.json', *grown_args)
        tool('dq5spritewrite.py', original, 'patch', out / 'grown.json', '-o', out / 'grown.dq5patch.json', *grown_args)
        tool('dq5npcrecord.py', original, 'patch', out / 'records.json', '-o', out / 'records.dq5patch.json')
        roms = {}
        for name, patches in (('original', [out / 'records.dq5patch.json']),
                              ('edited', [out / 'records.dq5patch.json', out / 'sprite.dq5patch.json']),
                              ('grown', [out / 'records.dq5patch.json', out / 'grown.dq5patch.json'])):
            roms[name] = out / f'{name}.sfc'
            tool('dq5build.py', original, 'build', *patches, '--size', '2', '-o', roms[name], '--ips', out / f'{name}.ips')
        grown = Rom(roms['grown'].read_bytes())
        regrown_doc = {'format': FORMAT, 'new_sets': [{'set': f'{REGROWN:02X}', 'image': 'pattern.png', 'palette': REGROWN_PALETTE}],
                       'gfx': [{'gfx': f'{NEW_GFX:02X}', 'set': f'{REGROWN:02X}'}]}
        regrow_data_at, regrow_at = (int(v.replace(':', ''), 16) for v in (args.regrow_data_at, args.regrow_at))
        try:
            patch(grown, regrown_doc, out, regrow_data_at)
            refused = False
        except ValueError:
            refused = True
        roms['regrown'] = out / 'regrown.sfc'
        roms['regrown'].write_bytes(apply(grown, patch(grown, regrown_doc, out, regrow_data_at, sets_at=regrow_at)).d)
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        for pose, (facing, lying) in POSES.items():
            (out / f'{pose}.json').write_text(json.dumps(pose_records(facing), indent=1) + '\n', encoding='utf-8')
            tool('dq5npcrecord.py', original, 'patch', out / f'{pose}.json', '-o', out / f'{pose}.dq5patch.json')
            for kind, extra in (('original', []), ('edited', [out / 'sprite.dq5patch.json'])):
                name = f'{pose}-{kind}'
                roms[name] = out / f'{name}.sfc'
                tool('dq5build.py', original, 'build', out / f'{pose}.dq5patch.json', *extra, '--size', '2',
                     '-o', roms[name])
                if lying:
                    roms[name].write_bytes(lay_down(roms[name].read_bytes()))
        for step, facing in STEPS.items():
            (out / f'{step}.json').write_text(json.dumps(step_records(facing), indent=1) + '\n', encoding='utf-8')
            tool('dq5npcrecord.py', original, 'patch', out / f'{step}.json', '-o', out / f'{step}.dq5patch.json')
            for kind, extra in (('original', []), ('edited', [out / 'sprite.dq5patch.json'])):
                name = f'{step}-{kind}'
                roms[name] = out / f'{name}.sfc'
                tool('dq5build.py', original, 'build', out / f'{step}.dq5patch.json', *extra, '--size', '2',
                     '-o', roms[name])
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {name: pool.submit(lambda n, r: compare(Rom(r.read_bytes()), run(
                r, n, out, state, mesence, libdir, *((STEP_DUMPS, STEP_HOLD) if n.startswith('step-') else ()))),
                name, rom) for name, rom in roms.items()}
            results = {name: job.result() for name, job in jobs.items()}
        edited = Rom(roms['edited'].read_bytes())
        changed = {}
        for s in (SIMPLE, OVERLAP, NEW):
            before, after = S.decode_set(base, s), S.decode_set(edited, s)
            changed[f'{s:02X}'] = before is None or before['tile_data'] != after['tile_data']
        changed[f'{GROWN:02X}'] = S.decode_set(base, GROWN) is None and S.decode_set(grown, GROWN) is not None
        mine, big, again = results['edited'], results['grown'], results['regrown']
        regrown = Rom(roms['regrown'].read_bytes())

        def same(r, sets):
            return all(f'{s:02X}' in r['sets'] and r['sets'][f'{s:02X}'][0] == r['sets'][f'{s:02X}'][1] for s in sets)

        def shown(r, sets):
            return all(any(f.startswith(f'{s:02X} ') for f in r['frames']) for s in sets)
        poses = {}
        for pose, (facing, lying) in POSES.items():
            want = {f'{s:02X} {facing}' + ('lying' if lying else '') for s in (SIMPLE, OVERLAP)}
            seen = {name: {f.rsplit(' ', 1)[0] + ' ' + f.rsplit(' ', 1)[1].rstrip('01') for f in results[f'{pose}-{name}']['frames']}
                    for name in ('original', 'edited')}
            poses[pose] = all(want <= seen[name] for name in seen) and all(
                results[f'{pose}-{name}']['groups'] == results[f'{pose}-{name}']['hits'] > 0 for name in seen) and same(
                results[f'{pose}-edited'], (SIMPLE, OVERLAP))
        steps = {}
        for step, facing in STEPS.items():
            want = {f'{s:02X} {facing}{f}' for s in (SIMPLE, OVERLAP) for f in (0, 1)}
            steps[step] = all(want <= set(results[f'{step}-{name}']['frames'])
                              and results[f'{step}-{name}']['groups'] == results[f'{step}-{name}']['hits'] > 0
                              for name in ('original', 'edited')) and same(results[f'{step}-edited'], (SIMPLE, OVERLAP))
        checks = {
            'poses': all(poses.values()),
            'steps': all(steps.values()),
            'vram': same(mine, (SIMPLE, OVERLAP, NEW)),
            'oam': mine['groups'] == mine['hits'] > 0 and results['original']['groups'] == results['original']['hits'],
            'shown': shown(mine, (SIMPLE, OVERLAP, NEW)),
            'changed': all(changed.values()),
            'original': all(v[0] == v[1] for v in results['original']['sets'].values()),
            'grown': same(big, (SIMPLE, NEW, GROWN)) and shown(big, (SIMPLE, NEW, GROWN)) and big['groups'] == big['hits'] > 0
                     and S.set_record(grown, GROWN)['palette'] == GROWN_PALETTE and big['other_palette'] == 0,
            'regrown': refused and S.set_table(regrown)[0] == regrow_at
                       and same(again, (SIMPLE, REGROWN, GROWN)) and shown(again, (SIMPLE, REGROWN, GROWN))
                       and again['groups'] == again['hits'] > 0 and again['other_palette'] == 0
                       and S.set_record(regrown, REGROWN)['palette'] == REGROWN_PALETTE,
        }
        report = {'donors': {'simple': f'{simple:02X}', 'overlap': f'{overlap:02X}'}, 'results': results,
                  'changed': changed, 'poses': poses, 'steps': steps, 'checks': checks}
        (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for name, r in results.items():
            print(f'{name}: 덤프 {r["dumps"]}개, 세트 ' + ' '.join(f'{s} {v[0]}/{v[1]}' for s, v in sorted(r['sets'].items()))
                  + f', OAM 묶음 {r["hits"]}/{r["groups"]}(레코드와 다른 팔레트 {r["other_palette"]}), 프레임 ' + ' '.join(r['frames']))
        print(f'시험 그림: 세트 {SIMPLE:02X} ← {simple:02X}, {OVERLAP:02X} ← {overlap:02X}, 새 세트 {NEW:02X} ← 무늬(그림 {NEW_GFX:02X}), '
              f'늘린 표의 새 세트 {GROWN:02X} ← {overlap:02X}(그림 {GROWN_GFX:02X}, 팔레트 {GROWN_PALETTE}), '
              f'다시 늘린 표의 새 세트 {REGROWN:02X} ← 무늬(그림 {NEW_GFX:02X}, 팔레트 {REGROWN_PALETTE}, --sets-at 없이 거부 {refused})')
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
