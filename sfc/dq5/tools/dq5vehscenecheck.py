"""탈것을 타고 내리는 장면(융단 펴기·내리기, 天空城 내려앉기, マスタードラゴン 부르기·내려앉기, 天空城 의 マスタードラゴン
장면 둘)을 MesenCE 에서 재고, 블록을 늘린 롬·고친 マスタードラゴン 롬이 원본과 같게 움직이는지 본다.

장면마다 lua/dq5vehscene.lua(앞에 dq5warp.lua)로 00:FC60 의 탈것 블록, 03:CB1B 를 부른 곳과 돌려준 A, EXEC 주소의 실행,
$1954·맵·세계·필드 좌표가 바뀐 프레임을 모은다. 롬은 원본, dq5blockgrowcheck 의 same 롬 10·11비트(블록 512+b·1024+b·
1536+b 는 블록 b 그대로), マスタードラゴン 4프레임 롬(dq5vehiclecheck 의 dragon4, 칸 표 --dragon-at)이다.

  carpet0     세계 0 (310,60) 에서 まほうのじゅうたん 을 펴고(01:BBD4) 세 방향으로 걷고 A 로 내린다. 그린 블록이 걷기 블록
              (방향 4 × 프레임)뿐인지, 늘린 롬이 원본과 같은 곳·같은 지형 값으로 움직이는지.
  carpetN     세계 1·2 (50,28) 에서 같은 입력. 01:BBDE 의 $1949 검사로 지형을 보지 않고 「ここでは ひろげられない!」.
  rideN       세계 1·2 에 융단을 탄 채($1954 = 80) 놓고 네 방향으로 걸어 제자리로 와서 A 로 내린다(게임에서는 펼 수 없는
              세계라 $1954 를 둠).
  tenkuuN     天空城($1954 = 81)을 세계 0 (306,40)·1 (60,14)·2 (46,13) 에 두고 A. 01:C375 가 4x3 칸(x−1~x+2, y−1~y+1)이
              모두 지형 01·06 이면 내려앉아 06/08 로 들어간다.
  dragonN     マスタードラゴン($1954 = 82)을 같은 세 자리에 두고 A 로 내려앉는다(01:C179 → 01:C200 → 01:BF7C). 착륙 블록
              (land0·land1)을 그리는지도 본다. 날아다니는 둘은 A 를 입력을 읽는 프레임에 맞춰 누른다(dq5vehscene.lua APRESS).
  bell        세계 0 (310,60) 에서 てんくうのベル(D2)을 써서(11:8E0F → 01:BBF0, 11:8E18 → 01:BEA9) 부르고 A 로 내린다.
  script41    06/00(7E:2190 bit7)에서 스크립트 41(15:F60B, $19B3 에 넣어 검)이 03:8EC7 → 03:8F1F 로 01:BB7C 를 부른다.
  battle0600  06/00 에 조우 구역 01 을 단 롬(dq5encounterwrite, 조우 계수 FF)에서 무작위 전투를 にげる 로 끝내면 01:867C →
              01:8A87 → 12:8B82 가 $1A0C = 05(01:BB7C 가 둠)를 보고 12:8BE9 로 01:BB7C 를 다시 부른다.
bell·script41·battle0600 은 원본과 dragon4 롬에서, 슬롯 7 이 dq5objlayout 이 둔 즉값(착륙 37C0 = 걷기 간격·32A0 = 8X,
天空城 37C0 = S·32A0 = 83)으로 도구가 둔 장면 블록을 그리는지와, 그린 블록의 칸이 두 프레임 뒤 OAM 에 그대로 놓였는지 본다.

  MESENCE=… python sfc/dq5/tools/dq5vehscenecheck.py rom/dq5.sfc --state work/state/ship.mss
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dq5blockgrowcheck as bgc  # noqa: E402
import dq5sprite as S  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5objlayout import VEHICLE_PARTS, vehicle_part  # noqa: E402
from dq5objlayoutcheck import find_grid, w16  # noqa: E402
from dq5vehiclecheck import build, dragon_doc, dragon_runs, mirror, scene_expect, tool  # noqa: E402

USE = 'a:8,wait:60,right:8,wait:40,down:8,wait:40,a:8,wait:80,a:8,wait:80,a:8'
CARPET_TEST = USE + ',wait:300,left:32,up:32,right:32,wait:100,a:8,wait:300'
RIDE_TEST = 'wait:60,left:32,up:32,right:32,down:32,wait:100,a:8,wait:300'
# 날아다니는 탈것은 서 있다가 앞으로 저절로 나아가며, 그동안 입력을 몇 프레임에 한 번만 읽는다. A 는 APRESS 로 그 창에 맞춘다.
LAND = {'SETTLE': '1', 'APRESS': '470', 'TEST': 'wait:600'}
ENC_RATE = '11EA44=FFFFFFFFFFFFFFFF'
SPOT = {0: '306,40', 1: '60,14', 2: '46,13'}
# 06/00 에 들어선 뒤 스크립트 41 을 건다(23:E2F4 가 하는 것과 같이).
SCRIPT41 = '19B3=0B;19B4=F6;19B5=15;19B1=00;19AE|80'
EXEC = '01BBD4,01BBE3,01BE8E,0181D6,01C30A,01C319,01C36D,01C200,01BF7C,01BBF0,01BEA9,01BF47,01BB7C,038F1F,128BE9,' \
       '2B80E5,208001'
SCENES = {
    'carpet0': {'FIELD': '310,60', 'SET': '2056=CC', 'TEST': CARPET_TEST},
    **{f'carpet{w}': {'FIELD': '50,28', 'POKE': f'7E1949={w:02X}', 'SET': '2056=CC', 'TEST': USE + ',wait:300'}
       for w in (1, 2)},
    **{f'ride{w}': {'FIELD': SPOT[w], 'POKE': f'7E1949={w:02X}', 'LATESET': '1954=80', 'SETTLE': '1',
                    'TEST': RIDE_TEST} for w in (1, 2)},
    **{f'tenkuu{w}': {'FIELD': SPOT[w], 'POKE': f'7E1949={w:02X}', 'LATESET': '1954=81'} | LAND for w in (0, 1, 2)},
    **{f'dragon{w}': {'FIELD': SPOT[w], 'POKE': f'7E1949={w:02X}', 'LATESET': '1954=82'} | LAND for w in (0, 1, 2)},
    'bell': {'FIELD': '310,60', 'SET': '2056=D2', 'TEST': USE + ',wait:120,a:8,wait:120,a:8,wait:900'},
    'script41': {'TO': '06/00,37,58', 'SET': '2190|80', 'LATESET': SCRIPT41, 'SHOTS': '760,900,1000',
                 'TEST': 'wait:200' + ',a:4,wait:60' * 6 + ',wait:300'},
    'battle0600': {'TO': '06/00,37,58', 'SET': '2190|80', 'ROMPATCH': ENC_RATE, 'FLEE': '1',
                   'TEST': ','.join(['right:150,left:150'] * 4) + ',wait:1500'},
}
GROWN = ('carpet0', 'carpet1', 'carpet2', 'ride1', 'ride2', 'tenkuu0', 'tenkuu1', 'tenkuu2', 'dragon0', 'dragon1',
         'dragon2')
DRAGON = ('bell', 'script41', 'battle0600')
LAG = 2


def flip_doc(rom):
    """マスタードラゴン 칸 수·프레임 수는 그대로 두고 칸만 제자리에서 바꾼다: 두 부분의 up1·down1 과 부분 1 의 land0·tenkuu1 을
    좌우로 뒤집는다. land1 과 tenkuu3 은 같은 블록 15 라 건드리지 않는다."""
    doc = dragon_doc(rom, 3, None)
    for v in doc['vehicles']:
        for key in ('up1', 'down1') + (('land0', 'tenkuu1') if v['part'] == '82-1' else ()):
            v['cells'][key] = mirror(v['cells'][key])
    return doc


def run(rom, name, extra, out, state, mesence, libdir):
    """dq5vehscene.lua 한 번. MesenCE 테스트 러너가 가끔 첫 프레임에 255 로 끝나서 한 번 더 돌린다."""
    dest = out / name
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'TO', 'FLEE',
                        'ROMPATCH', 'SAVE', 'SET', 'WAGON', 'EVERY', 'EXEC', 'SHOTS', 'FROM', 'UNTIL')}
    env.update({'LIBDIR': str(libdir), 'STATE': str(state), 'SHOT_DIR': str(dest), 'MAXF': '3200', 'SETTLE': '60',
                'EXEC': EXEC, 'SHOTLAG': str(LAG)} | extra)
    for _ in range(2):
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir()
        with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
            done = subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5vehscene.lua'),
                                   '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                                  timeout=600)
        if (dest / 'warp.txt').exists():
            return dest
        if done.returncode != 255:
            break
        print(f'{name}: MesenCE 가 {done.returncode} 로 끝나 한 번 더 돌림', file=sys.stderr)
    raise ValueError(f'{name}: MesenCE 가 끝나지 않음({done.returncode})')


def lines(path):
    return [x for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def parse(dest):
    """calls.txt·state.txt·blocks.txt·warp.txt → 사전."""
    cb1b, execs = {}, {}
    for line in lines(dest / 'calls.txt'):
        kind, pc, count, first, last, *rest = line.split()
        if kind == 'cb1b':
            cb1b[pc] = {'count': int(count), 'first': int(first),
                        'a': {a: int(c) for a, c in (x.split(':') for x in rest[0].split(','))}}
        else:
            execs[pc] = (int(count), int(first), int(last))
    states = []
    for line in lines(dest / 'state.txt'):
        f, v, mp, world, xy = line.split()
        states.append((int(f), v, mp, world, xy))
    blocks = []
    for line in lines(dest / 'blocks.txt'):
        slot, base, size, d, fs, a0, off, dr, fr, count, first, last = line.split()
        blocks.append({'slot': int(slot, 16), 'base': int(base, 16), 'size': size, '37C0': int(d, 16),
                       '37E0': int(fs, 16), '32A0': int(a0, 16), 'off': int(off), 'first': int(first),
                       'last': int(last)})
    end = next(x for x in (dest / 'warp.txt').read_text().splitlines() if ' end ' in x)
    return {'cb1b': cb1b, 'exec': execs, 'states': states, 'blocks': blocks, 'end': end.split(' end ')[1]}


def runs_of(r, pc):
    return r['exec'].get(pc, (0, -1, -1))[0]


def vehicle_values(r):
    """$1954 가 거친 값 차례(같은 값이 이어지면 하나)."""
    out = []
    for _, v, *_ in r['states']:
        if not out or out[-1] != v:
            out.append(v)
    return out


def part_blocks(rom, r):
    """부분마다 그린 블록 번호(블록 = 오프셋 / 2 / 칸 수, 간격이 그 부분의 걷기 간격인 것만)."""
    out = {}
    for n, site in VEHICLE_PARTS.items():
        p = vehicle_part(rom, n)
        per = p['cols'] * p['rows']
        got = {b['off'] // 2 // per for b in r['blocks']
               if b['size'] == f'{p["cols"]}x{p["rows"]}' and (b['37C0'], b['37E0']) == (p['dir'], p['frame'])}
        if got:
            out[n] = sorted(got)
    return out


def same_motion(a, b):
    """두 롬의 같은 장면이 같은 곳에서 같은 지형 값으로 끝났는지: 03:CB1B 부른 곳·횟수·A, $1954 차례, 끝 줄."""
    strip = lambda r: {k: (v['count'], v['a']) for k, v in r['cb1b'].items()}  # noqa: E731
    return strip(a) == strip(b) and vehicle_values(a) == vehicle_values(b) and a['end'] == b['end']


def dragon_scene(rom, r, keys, start, dest):
    """슬롯 7 이 start 프레임 뒤에 그린 82-1 장면 블록과, 그 블록을 그린 동안(+ LAG)의 덤프 가운데 슬롯 7 칸 목록이 칸 표와
    같고 OAM 에 그 블록의 칸이 그대로 놓인 것이 있는지."""
    p = vehicle_part(rom, '82-1')
    per = p['cols'] * p['rows']
    stride, a0, want = scene_expect(rom, keys)
    spans = {}
    for b in r['blocks']:
        if b['slot'] == 7 and b['last'] >= start and (b['37C0'], b['32A0']) == (stride, a0):
            f0, f1 = spans.get(b['off'] // 2 // per, (10 ** 9, 0))
            spans[b['off'] // 2 // per] = (min(f0, max(b['first'], start)), max(f1, b['last']))
    cells = [0x180 + (c & 0x7F) | (0x4000 if c & 0x80 else 0) for c in (rom.u8(p['table'] + i)
                                                                         for i in range(p['copied']))]
    dumps = sorted(int(f.stem[1:]) for f in dest.glob('f*.oam'))
    shown = {}
    for blk, (f0, f1) in spans.items():
        shown[blk] = []
        for f in (f for f in dumps if f0 + LAG <= f <= f1 + LAG):
            w = (dest / f'f{f:05d}.wram').read_bytes()
            items = S.oam_groups((dest / f'f{f:05d}.oam').read_bytes())
            listed = [w16(w, w16(w, 0x8000 + w[0x3207]) + i * 2) & 0x41FF for i in range(len(cells))] == cells
            if listed and find_grid(items, cells[blk * per:(blk + 1) * per], p['cols']):
                shown[blk].append(f)
    return {'stride': f'{stride:02X}', '32A0': f'{a0:02X}', 'want': sorted(want), 'drawn': sorted(spans),
            'oam': {b: v[:3] for b, v in shown.items()}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/vehscenecheck')
    ap.add_argument('--dragon-at', default='0B:FBB0', help='고친 マスタードラゴン 의 칸 표 자리')
    ap.add_argument('--only', nargs='*', help='이 장면만 돌린다')
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
        roms = {'original': original}
        for bits in (10, 11):
            (out / f'g{bits}').mkdir()
            bgc.make_roms(original, out / f'g{bits}', bits, only=('same',))
            roms[f'same{bits}'] = out / f'g{bits}' / 'same.sfc'
        roms['dragon4'] = build(original, out, 'dragon4', dragon_doc(base, 4, None), args.dragon_at)
        roms['dragonflip'] = build(original, out, 'dragonflip', flip_doc(base), args.dragon_at)
        (out / 'enc.json').write_text(json.dumps({'format': 'dq5encounter/1',
                                                  'maps': [{'map': '06/00', 'areas': [1, 1, 1]}]}) + '\n')
        tool('dq5encounterwrite.py', original, 'patch', out / 'enc.json', '-o', out / 'enc.dq5patch.json')
        for name, patches in (('original', ()), ('dragon4', (out / 'dragon4.dq5patch.json',))):
            path = out / f'{name}-enc.sfc'
            tool('dq5build.py', original, 'build', *patches, out / 'enc.dq5patch.json', '-o', path)
            roms[f'{name}-enc'] = path
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        cases = []
        for scene in SCENES:
            if args.only and scene not in args.only:
                continue
            if scene in GROWN:
                cases += [(scene, k) for k in ('original', 'same10', 'same11')]
            elif scene == 'battle0600':
                cases += [(scene, 'original-enc'), (scene, 'dragon4-enc')]
            else:
                cases += [(scene, 'original'), (scene, 'dragon4')]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            dirs = dict(zip(cases, pool.map(lambda c: run(roms[c[1]], f'{c[0]}-{c[1]}', SCENES[c[0]], out, state, mesence,
                                                          libdir), cases)))
        res = {c: parse(d) for c, d in dirs.items()}
        results, checks = {}, {}
        if not args.only or 'dragonflip' in args.only:
            # 제자리 칸 쓰기: dq5vehiclecheck 의 걷기 블록·덤프와 장면 넷(착륙 오른쪽·왼쪽, 이륙, 天空城 06/00)을 그대로 거친다.
            dragon_runs('dragonflip', roms['dragonflip'], out, state, mesence, libdir, results, checks)
        for (scene, rom_name), r in res.items():
            rom = Rom(roms[rom_name].read_bytes())
            row = {'end': r['end'], '1954': vehicle_values(r), 'cb1b': {k: (v['count'], v['a']) for k, v in r['cb1b'].items()},
                   'exec': {k: v for k, v in r['exec'].items() if v[0]}, 'blocks': part_blocks(rom, r)}
            if scene in DRAGON or scene.startswith('dragon'):
                keys = ('land0', 'land1') if scene == 'bell' or scene.startswith('dragon') else ('tenkuu0', 'tenkuu1', 'tenkuu2', 'tenkuu3')
                start = 0 if scene.startswith('dragon') else {'bell': 0, 'script41': r['exec'].get('038F1F', (0, 0))[1],
                         'battle0600': r['exec'].get('128BE9', (0, 0))[1]}[scene]
                row['dragon'] = dragon_scene(rom, r, keys, start, dirs[(scene, rom_name)])
            results[f'{scene}-{rom_name}'] = row
        for scene in SCENES:
            if args.only and scene not in args.only:
                continue
            if scene in GROWN:
                o = res[(scene, 'original')]
                for k in ('same10', 'same11'):
                    checks[f'{scene}-{k}'] = same_motion(o, res[(scene, k)])
            if scene == 'carpet0':
                blocks = results['carpet0-original']['blocks']
                checks['carpet0-blocks'] = set(blocks) == {'80-1', '80-2', '80-3'} and \
                    all(max(v) < 4 * vehicle_part(base, k)['frames'] for k, v in blocks.items())
                checks['carpet0-ride'] = vehicle_values(o) == ['00', '80', '00'] and runs_of(o, '01BBD4') == 1
            if scene in ('carpet1', 'carpet2'):
                o = res[(scene, 'original')]
                checks[f'{scene}-refused'] = runs_of(o, '01BBD4') == 1 and runs_of(o, '01BBE3') == 0 and \
                    runs_of(o, '01BE8E') == 0 and vehicle_values(o) == ['00']
            if scene in ('ride1', 'ride2'):
                o = res[(scene, 'original')]
                checks[f'{scene}-ride'] = o['cb1b'].get('0181D6', {}).get('count', 0) > 0 and \
                    vehicle_values(o)[-2:] == ['80', '00']
            if scene.startswith('tenkuu'):
                o = res[(scene, 'original')]
                checks[f'{scene}-land'] = runs_of(o, '01C319') == 1 and ' 06/08 ' in o['end'] and \
                    results[f'{scene}-original']['blocks'] == {'81-1': [0], '81-2': [0]}
            if scene in ('dragon0', 'dragon1', 'dragon2'):
                o = res[(scene, 'original')]
                d = results[f'{scene}-original']['dragon']
                checks[f'{scene}-land'] = runs_of(o, '01C200') == 1 and vehicle_values(o)[-1] == '00' and \
                    set(d['drawn']) == set(d['want']) and bool(d['oam'].get(max(d['want'])))
            if scene in DRAGON:
                for k in (('original-enc', 'dragon4-enc') if scene == 'battle0600' else ('original', 'dragon4')):
                    d = results[f'{scene}-{k}']['dragon']
                    p = vehicle_part(Rom(roms[k].read_bytes()), '82-1')
                    blk = lambda key: p['scene'][key][0] // (p['cols'] * p['rows'])  # noqa: E731
                    # 03:8F1F 뒤에는 장면이 프레임을 넘기지 않아 tenkuu0 만 그린다. land1 은 그린 프레임 안에 걷기 블록으로
                    # 다시 그려져 OAM 에 나오지 않는다(dq5vehiclecheck 와 같음).
                    want, visible = {'bell': ({blk('land0'), blk('land1')}, {blk('land0')}),
                                     'script41': ({blk('tenkuu0')},) * 2,
                                     'battle0600': (set(d['want']),) * 2}[scene]
                    called = {'bell': '01BEA9', 'script41': '038F1F', 'battle0600': '128BE9'}[scene]
                    checks[f'{scene}-{k}'] = runs_of(res[(scene, k)], called) == 1 and set(d['drawn']) == want and \
                        all(d['oam'].get(b) for b in visible)
        (out / 'results.json').write_text(json.dumps({'results': results, 'checks': checks}, ensure_ascii=False,
                                                     indent=1, default=str) + '\n', encoding='utf-8')
        for case, row in results.items():
            print(f'{case}: {json.dumps(row, ensure_ascii=False, default=str)}')
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        if not all(checks.values()):
            raise ValueError('불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stdout, error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
