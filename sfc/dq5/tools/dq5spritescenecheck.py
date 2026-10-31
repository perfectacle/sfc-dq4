"""인물 스프라이트의 장면 몇을 MesenCE 로 잰다(lua/dq5spritescene.lua).

  ghost      04/00 에 7E:2198 bit6 을 켜고 들어가면 맵 루틴(12:90E4 → 12:911D)이 슬롯 08·09·0E·0F 의 7E:3800 에 84 를 두고
             12:8C9F 를 부름. 켜지 않으면 둘 다 없음
  translucent 12:8C9F 를 맵 루틴으로 부르는 12/09·23/00 에 들어가 색 연산 레지스터·CGRAM OBJ 팔레트 4~7 = 0~3 을 봄.
             23/00 은 슬롯 09~0B 의 3800 에 C1
  setpalette 주인공 세트 82 를 dq5objpalette.py 로 OBJ 팔레트 5(색 띠)에 둔 롬: 12/09 에서는 팔레트 5 가 1 의 사본이 되고,
             12/00 에서는 띠 그대로
  land       マスタードラゴン 착륙에서 둘째 블록(land1, 칸 오프셋 1E0)을 그린 뒤 다음 OAM DMA 전에 같은 슬롯을 다른 블록으로
             다시 그리는지
  picture    첫 필드 이벤트 전투(몬스터 11)가 끝난 뒤 02:C95D 가 03:D1C3 으로 일행 슬롯 0 의 그림을 다시 정하고 03:D202 가
             그림 표를 읽는지(X = 그림 2E)
--sweep 은 위 대신 dq5freesweep.py 의 장면(실내 맵 346곳에 들어가 걷기, 첫 필드 이벤트 전투 236종, 세계 셋)마다 같은 프로브로
12:8C9F·03:D1C3·03:D202·03:D24D 의 실행과 7E:3800 쓰기를 모아, 불린 맵(실행 줄의 map=)과 전투 끝의 7E:2192 bit3 별로 센다.
원본 롬·선실 상태는 읽기만 하고, 입력·패치·롬·기록은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5spritescenecheck.py rom/dq5.sfc --state work/state/ship.mss [--sweep --jobs 10]
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
# 팔레트 5 의 색 1~15: 빨강이 오르고 파랑이 내림. 원래 OBJ 팔레트 0~3 과 겹치지 않는다
BAND = [(i * 2) | (31 - i * 2) << 10 for i in range(1, 16)]
HERO_SET, HERO_PALETTE = '82', 5
FIGHT = ','.join(['a:8,wait:40'] * 12)
SCENES = {
    'ghost-0400': ('original', {'TO': '04/00,38,60', 'SET': '2198|40', 'EXEC': '128C9F', 'TEST': 'wait:200'}),
    'plain-0400': ('original', {'TO': '04/00,38,60', 'EXEC': '128C9F', 'TEST': 'wait:200'}),
    'translucent-1209': ('original', {'TO': '12/09,20,20', 'EXEC': '128C9F', 'TEST': 'wait:200', 'DUMPAT': '500'}),
    'translucent-2300': ('original', {'TO': '23/00,37,39', 'EXEC': '128C9F', 'TEST': 'wait:200', 'DUMPAT': '500'}),
    'setpalette-1209': ('palette', {'TO': '12/09,20,20', 'EXEC': '128C9F', 'TEST': 'wait:200', 'DUMPAT': '500'}),
    'setpalette-1200': ('palette', {'TO': '12/00,20,20', 'EXEC': '128C9F', 'TEST': 'wait:200', 'DUMPAT': '500'}),
    'land': ('original', {'FIELD': '341,56', 'LATESET': '1954=82', 'SETTLE': '120', 'VEHICLE': '1', 'FROM': '700',
                          'UNTIL': '800', 'EXEC': '01BFB1,01BFC1', 'TEST': 'wait:150,right:4,wait:10,a:6,wait:700',
                          'MAXF': '2000'}),
    'picture': ('original', {'FIELD': '341,56', 'BATTLE': '11:1', 'EXEC': '03D1C3,03D202,03D24D', 'TEST': FIGHT,
                             'MAXF': '1300'}),
}
CLEAR = ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'TO', 'ROMPATCH', 'SAVE', 'SET',
         'WAGON', 'TEST', 'EXEC', 'VEHICLE', 'FROM', 'UNTIL', 'DUMPAT', 'SETTLE')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def tool(name, *args):
    subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True, text=True,
                   timeout=120)


def run(name, rom, out, mesence, libdir, state, extra):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in CLEAR}
    env.update({'LIBDIR': libdir, 'STATE': str(state), 'SHOT_DIR': str(dest), 'SETTLE': '60', 'MAXF': '700',
                'DRIVER': str(HERE / 'lua/dq5warp.lua')} | extra)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5spritescene.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=300)
    text = dest / 'scene.txt'
    return dest, text.read_text(encoding='utf-8').splitlines() if text.is_file() else []


def palettes(dest):
    oam, cgram = (dest / 'oam.bin').read_bytes(), (dest / 'cgram.bin').read_bytes()
    used = collections.Counter(oam[i * 4 + 3] >> 1 & 7 for i in range(128) if oam[i * 4 + 1] < 0xE0)
    obj = [[int.from_bytes(cgram[256 + 32 * p + 2 * k:258 + 32 * p + 2 * k], 'little') for k in range(16)]
           for p in range(8)]
    return dict(sorted(used.items())), obj


def measure(name, lines, dest):
    calls = [line for line in lines if ' exec ' in line]
    slots = sorted({re.search(r'w7E38(..)=(..)', line).groups() for line in lines if ' w7E38' in line})
    regs = sorted({re.search(r' r(....)=(..)', line).groups() for line in lines if re.search(r' r21..=', line)})
    out = {'calls': len(calls), 'slots_3800': [f'{s}={v}' for s, v in slots], 'regs': [f'{r}={v}' for r, v in regs]}
    if (dest / 'oam.bin').is_file():
        used, obj = palettes(dest)
        out |= {'oam_palettes': used, 'pal47_copy': obj[4:] == obj[:4], 'pal5_band': obj[5][1:] == BAND,
                'pal5_is_pal1': obj[5] == obj[1]}
    if name == 'land':
        # land1(칸 오프셋 1E0)을 그린 뒤 다음 OAM DMA 까지 슬롯 07 을 마지막으로 그린 블록
        events = [line for line in lines if 'draw slot=07' in line or 'oamdma' in line]
        at = [k for k, line in enumerate(events) if 'off=1E0' in line]
        out['land1_draws'] = len(at)
        if at:
            nxt = next((k for k in range(at[0], len(events)) if 'oamdma' in events[k]), None)
            last = [e for e in events[at[0]:nxt] if 'draw' in e][-1] if nxt else ''
            out['before_dma'] = re.search(r'off=(\w+)', last)[1] if last else None
            out['trace'] = events[max(0, at[0] - 2):(nxt or at[0]) + 1]
    if name == 'picture':
        out['picture'] = sorted({re.search(r'X=00(..)', line)[1] for line in calls if 'exec 03D202' in line})
        out['from_02C95D'] = all('7C C9 02' in line for line in calls if 'exec 03D1C3' in line)
        out['d24d'] = sum('exec 03D24D' in line for line in calls)
    return out


EXPECT = {
    'ghost-0400': lambda r: r['calls'] == 1 and r['slots_3800'] == ['08=84', '09=84', '0E=84', '0F=84']
    and r['regs'] == ['212D=07', '2130=02', '2131=50'],
    'plain-0400': lambda r: r['calls'] == 0 and not r['slots_3800'],
    'translucent-1209': lambda r: r['calls'] == 1 and r['pal47_copy'] and r['regs'] == ['212D=07', '2130=02', '2131=50'],
    'translucent-2300': lambda r: r['calls'] == 1 and r['pal47_copy'] and r['slots_3800'] == ['09=C1', '0A=C1', '0B=C1'],
    'setpalette-1209': lambda r: r['calls'] == 1 and r['oam_palettes'].get(HERO_PALETTE) and r['pal5_is_pal1']
    and not r['pal5_band'],
    'setpalette-1200': lambda r: r['calls'] == 0 and r['oam_palettes'].get(HERO_PALETTE) and r['pal5_band'],
    'land': lambda r: r['land1_draws'] == 1 and r.get('before_dma') not in (None, '1E0'),
    'picture': lambda r: r['picture'] == ['2E'] and r['from_02C95D'] and r['d24d'] > 0,
}


def sweep(original, state, out, mesence, libdir, jobs):
    """dq5freesweep.py 의 장면마다 프로브를 돌려 맵·전투별로 센다."""
    from dq5freesweep import jobs as sweep_jobs
    from dq5map import Rom
    todo = sweep_jobs(str(original), Rom(original.read_bytes()), ['maps', 'battles', 'field'], jobs)
    extra = {'EXEC': '128C9F,03D1C3,03D202,03D24D'}

    def one(job):
        kind, name, env = job
        dest, lines = run(f'{kind}-{name}', original, out, mesence, libdir, state, extra | env)
        wram = dest / 'final.wram'
        return kind, name, lines, wram.read_bytes()[0x2192] if wram.is_file() else None
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        got = list(pool.map(one, todo))
    calls, writes, battles = collections.defaultdict(set), collections.defaultdict(set), collections.Counter()
    for kind, name, lines, flags in got:
        for line in lines:
            hit = re.search(r'exec 128C9F .* map=(\S+)', line)
            if hit:
                calls[hit[1]].add(f'{kind}/{name}')
            hit = re.search(r'w7E38(..)=(..) map=(\S+)', line)
            if hit:
                writes[hit[3]].add(hit[2])
        if kind == 'battles':
            ran = any('exec 03D1C3' in line for line in lines)
            battles['기록 없음' if flags is None else f'2192.3={flags >> 3 & 1} D1C3={int(ran)}'] += 1
    result = {'runs': len(got), 'calls_8C9F': {k: sorted(v) for k, v in sorted(calls.items())},
              'writes_3800': {k: sorted(v) for k, v in sorted(writes.items())}, 'battles': dict(sorted(battles.items()))}
    (out / 'sweep.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/spritescene')
    ap.add_argument('--at', default='3B:8000', help='세트 팔레트 표 자리(dq5objpalette.py --at)')
    ap.add_argument('--sweep', action='store_true', help='dq5freesweep.py 의 장면으로 훑기만 함')
    ap.add_argument('--jobs', type=int, default=4)
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True,
                                timeout=30).stdout.strip()
        if args.sweep:
            return sweep(original, state, out, mesence, libdir, args.jobs)
        doc = {'format': 'dq5objpalette/1', 'palettes': [{'palette': HERO_PALETTE, 'colors': BAND}],
               'sets': [{'set': HERO_SET, 'palette': HERO_PALETTE}]}
        (out / 'palette.json').write_text(json.dumps(doc) + '\n', encoding='utf-8')
        tool('dq5objpalette.py', original, 'patch', out / 'palette.json', '-o', out / 'palette.dq5patch.json',
             '--at', args.at)
        roms = {'original': original, 'palette': out / 'palette.sfc'}
        tool('dq5build.py', original, 'build', out / 'palette.dq5patch.json', '-o', roms['palette'])
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {name: pool.submit(run, name, roms[rom], out, mesence, libdir, state, extra)
                    for name, (rom, extra) in SCENES.items()}
            got = {name: measure(name, *reversed(job.result())) for name, job in jobs.items()}
        results = [{'scene': name, **value, 'passed': bool(EXPECT[name](value))} for name, value in got.items()]
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for r in results:
            print(json.dumps({k: v for k, v in r.items() if k != 'trace'}, ensure_ascii=False))
        failed = [r['scene'] for r in results if not r['passed']]
        require(not failed, f'불일치: {", ".join(failed)}')
        print(f'{len(results)}개 장면 통과')
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
