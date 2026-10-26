"""인물 목록 구조(수·순서·새 목록)와 옮긴 등장 조건 표를 MesenCE에서 확인한다.

dq5npcrelocate.py 로 만든 롬 세 벌을 원본과 함께 돌린다.
  count  02/06 기본 목록을 [둘째, 첫째, 넷째(밤)를 낮으로 옮긴 사본] 으로: 순서 바꾸기·지우기·더하기
  table  대체 표를 옮겨(12:82FB → 새 루틴) 맨 앞에 02/06 새 목록 항목을 더하고, 빈 맵 표에 01/01 을 더함
  growth --allow-growth 로 02/06 낮 인물을 물체 뒤 슬롯 1F 까지 채움
인물 목록 로더 직후(12:803C) WRAM 의 인물 표 23칸과 목록 끝 주소($A5-$A7), 들어간 뒤의 다음 빈 슬롯(7E:1983)을
롬에서 예측한 값과 견주고, 더한 인물에게 말을 걸어 메시지 번호를 본다. 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5npclistcheck.py rom/dq5.sfc --state work/state/ship.mss
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dq5map import Rom  # noqa: E402
from dq5mapwrite import all_maps  # noqa: E402
from dq5npc import FLAGS, list_address, list_entries, parse, table_values  # noqa: E402
from dq5npclists import NO_NPC_COUNT, OVERRIDE_COUNT, SLOT_FIRST, map_objects  # noqa: E402
from dq5npcrecordcheck import command, compare, require  # noqa: E402

HERE = Path(__file__).resolve().parent
TALK = 0x300
MESSAGE = TALK + 0x3C6
BASE = '05:8CD4'                     # 02/06 기본 목록: 낮 8CD4·8D0B, 밤 8D2C·8D34
ADDED = {'from': 3, 'time': 'day', 'fields': {'x': 24, 'y': 12, 'facing': 'down', 'talk': TALK}}
TALK_TEST = 'up:40,wait:40,a:4,wait:60,a:4,wait:200'
NEW_MAP = '0D/05'
NEW_MAP_DOC = {'format': 'dq5newmap/1', 'maps': [{'map': NEW_MAP, 'record': {'copy': '0D/02'}, 'attrs': {'copy': '0D/02'}}]}


def condition(rom, at, count, size):
    rows = []
    for i in range(count):
        raw = [rom.u8(at + i * size + k) for k in range(size)]
        row = {'map': f'{raw[0]:02X}/{raw[1]:02X}', 'flag': raw[2] & 0x7F, 'when': 'off' if raw[2] & 0x80 else 'on',
               'mask': raw[3]}
        if size == 6:
            row['list'] = f'10:{raw[4] | raw[5] << 8:04X}'
        rows.append(row)
    return rows


def documents(rom):
    added = dict(ADDED, **{'from': {'list': BASE, 'index': 3}})
    filler = [{'from': {'list': BASE, 'index': 3}, 'time': 'day',
               'fields': {'x': 18 + 2 * i, 'y': 20, 'facing': 'down', 'talk': TALK}} for i in range(20)]
    return {
        'count': {'lists': [{'list': BASE, 'entries': [{'from': 1}, {'from': 0}, ADDED]}]},
        'table': {'new_lists': [{'name': 'extra', 'entries': [added, {'from': {'list': BASE, 'index': 1}}]}],
                  'overrides': [{'map': '02/06', 'flag': 0x1D, 'when': 'off', 'mask': 0x10, 'list': 'new:extra'}]
                  + condition(rom, 0x128449, OVERRIDE_COUNT, 6),
                  'no_npc': condition(rom, 0x12839C, NO_NPC_COUNT, 4)
                  + [{'map': '01/01', 'flag': 0x1D, 'when': 'off', 'mask': 0x10}]},
        'growth': {'lists': [{'list': BASE, 'entries': [{'from': 0}, {'from': 1}, ADDED] + filler}]},
        # 새 맵 0D/05(dq5newmap.py 로 0D/02 의 레코드·속성)에 인물 둘: 주인공 두 칸 위에 말 거는 인물, 옆에 하나.
        'newmap': {'lists': [{'map': NEW_MAP, 'entries': [
            dict(added, fields={'x': 12, 'y': 2, 'facing': 'down', 'talk': TALK}),
            dict(added, fields={'x': 16, 'y': 2, 'facing': 'down', 'talk': TALK})]}]},
    }


# (이름, 롬, TO, 밤, TEST)
CASES = [
    ('original-day', 'original', '02/06,24,14,1', False, TALK_TEST),
    ('original-night', 'original', '02/06,24,14,1', True, ''),
    ('original-0101', 'original', '01/01,13,8,1', False, ''),
    ('original-2100', 'original', '21/00,10,10,1', False, ''),
    ('count-day', 'count', '02/06,24,14,1', False, TALK_TEST),
    ('count-night', 'count', '02/06,24,14,1', True, ''),
    ('table-day', 'table', '02/06,24,14,1', False, TALK_TEST),
    ('table-0101', 'table', '01/01,13,8,1', False, ''),
    ('table-2100', 'table', '21/00,10,10,1', False, ''),
    ('growth-day', 'growth', '02/06,24,14,1', False, TALK_TEST),
    ('original-0D02', 'original', '0D/02,12,4,1', False, ''),
    ('original-0E00', 'original', '0E/00,10,10,1', False, ''),
    ('newmap-day', 'newmap', '0D/05,12,4,1', False, TALK_TEST),
    ('newmap-night', 'newmap', '0D/05,12,4,1', True, ''),
    ('newmap-0D02', 'newmap', '0D/02,12,4,1', False, ''),
    ('newmap-0E00', 'newmap', '0E/00,10,10,1', False, ''),
]


def run(case, roms, state, out, mesence, libdir):
    name, rom, to, night, test = case
    dest = out / name
    dest.mkdir()
    bc, bd = to.split(',')[0].split('/')
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE',
                        'ROMPATCH', 'SAVE', 'SET', 'WAGON')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1500', SETTLE='120',
               TO=to, TEST=f'{test},wait:30' if test else 'wait:30', CHECK_GROUP=bc, CHECK_MAP=bd)
    if night:
        env['POKE'] = '7E075E=F0;7E075F=00'
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(roms[rom]), str(HERE / 'lua/dq5npcrecordcheck.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=120)
    text = (dest / 'warp.txt').read_text(encoding='utf-8')
    require((dest / 'npc.bin').is_file(), f'{name}: 맵에 들어가지 못함')
    slots = re.search(r'slots ([0-9A-F]{2}) ([0-9A-F]{2})', text)
    require(slots is not None, f'{name}: 00:E1CC 를 지나지 않음')
    messages = re.search(r'^messages (.*)$', text, re.M)[1]
    return ((dest / 'npc.bin').read_bytes(), int(slots[2], 16), [int(v, 16) for v in messages.split(',') if v])


def expected(rom, layout, original, wram, bc, bd, night):
    """원본 롬은 dq5npc 의 선택 규칙으로, 옮긴 롬은 layout 의 목록 주소와 덤프 플래그로 목록을 정한다."""
    flags = {FLAGS + i: wram[0x2190 + i] for i in range(0x170)}
    source = list_address(original, bc, bd, flags)
    if layout is not None and source is not None:
        source = int(layout['lists'][f'{source >> 16:02X}:{source & 0xFFFF:04X}'].replace(':', ''), 16)
    return source, flags


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/npclistcheck')
    ap.add_argument('--objects', action='store_true', help='원본 롬에서 맵 OBJ 물체가 있는 맵 33곳의 낮·밤 물체 슬롯 수도 잰다')
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
        base = Rom(original.read_bytes())
        roms, layouts = {'original': original}, {'original': None}
        for key, doc in documents(base).items():
            source = out / f'{key}.json'
            source.write_text(json.dumps({'format': 'dq5npcrelocate/1', **doc}, ensure_ascii=False, indent=1) + '\n',
                              encoding='utf-8')
            command('dq5npcrelocate.py', original, 'patch', source, '-o', out / f'{key}.dq5patch.json',
                    '--report', out / f'{key}.layout.json', *(['--allow-growth'] if key == 'growth' else []),
                    *(['--new-map', NEW_MAP] if key == 'newmap' else []))
            roms[key] = out / f'{key}.sfc'
            extra = []
            if key == 'newmap':
                (out / 'newmap.map.json').write_text(json.dumps(NEW_MAP_DOC) + '\n', encoding='utf-8')
                command('dq5newmap.py', original, 'patch', out / 'newmap.map.json', '-o', out / 'newmap.map.dq5patch.json')
                extra = [out / 'newmap.map.dq5patch.json']
            command('dq5build.py', original, 'build', out / f'{key}.dq5patch.json', *extra, '-o', roms[key],
                    '--ips', out / f'{key}.ips')
            layouts[key] = json.loads((out / f'{key}.layout.json').read_text(encoding='utf-8'))
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        cases = list(CASES)
        if args.objects:
            cases += [(f'objects-{bc:02X}{bd:02X}-{"night" if night else "day"}', 'original',
                       f'{bc:02X}/{bd:02X},10,10,1', night, '')
                      for bc, bd in all_maps(base) for night in (False, True)
                      if map_objects(base, bc, bd, False) or map_objects(base, bc, bd, True)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            seen = list(pool.map(lambda case: run(case, roms, state, out, mesence, libdir), cases))
        results = {}
        objects = {}
        for (name, rom, to, night, _), (wram, free, messages) in zip(cases, seen):
            bc, bd = (int(v, 16) for v in to.split(',')[0].split('/'))
            if name.startswith('objects-'):
                objects[name] = {'npc_end': wram[0x81], 'free_slot': free, 'objects': free - wram[0x81],
                                 'expected_objects': map_objects(base, bc, bd, night)}
                continue
            built = Rom(roms[rom].read_bytes()) if rom != 'original' else base
            source, flags = expected(built, layouts[rom], base, wram, bc, bd, night)
            if rom == 'table' and (bc, bd) == (2, 6):
                source = int(layouts[rom]['lists']['new:extra'].replace(':', ''), 16)
            if rom == 'table' and (bc, bd) == (1, 1):
                source = None
            if rom == 'newmap' and f'{bc:02X}/{bd:02X}' == NEW_MAP:
                source = int(layouts[rom]['lists'][NEW_MAP].replace(':', ''), 16)
            placed = [] if source is None else [(at, f) for at, _ in list_entries(built, source)
                                                 if (f := parse(built, at, night))]
            bad = compare(wram, table_values(built, placed, flags))
            end = None if source is None else source + sum(n for _, n in list_entries(built, source))
            got_end = wram[0xA5] | wram[0xA6] << 8 | wram[0xA7] << 16
            slot = SLOT_FIRST + len(placed) + map_objects(base, bc, bd, night)
            results[name] = {'rom': rom, 'list': None if source is None else f'{source:06X}', 'slots': len(placed),
                             'npc_end': wram[0x81], 'free_slot': free, 'expected_free_slot': slot,
                             'list_end': f'{got_end:06X}', 'expected_list_end': None if end is None else f'{end:06X}',
                             'table_mismatch': bad[:20], 'messages': [f'{m:03X}' for m in messages],
                             'talk': MESSAGE in messages}
        checks = {
            'tables': all(not r['table_mismatch'] for r in results.values()),
            'slots': all(r['npc_end'] == SLOT_FIRST + r['slots'] and r['free_slot'] == r['expected_free_slot']
                         for r in results.values()),
            'list_end': all(r['expected_list_end'] in (None, r['list_end']) for r in results.values()),
            'count': results['count-day']['slots'] == 3 and results['count-night']['slots'] == 0
            and results['count-day']['talk'] and not results['original-day']['talk'],
            'table-new-list': results['table-day']['talk'] and results['table-day']['slots'] == 2,
            'table-no-npc': results['table-0101']['slots'] == 0 and results['original-0101']['slots'] == 5,
            'table-original-row': results['table-2100']['slots'] == results['original-2100']['slots'] > 0,
            'growth': results['growth-day']['free_slot'] == 0x1F and results['growth-day']['talk'],
            # 새 맵에 인물 둘이 서고 말이 걸리며, 같은 그룹 0D/02 와 다음 그룹 0E/00 의 인물은 원본과 같다.
            'new-map': results['newmap-day']['slots'] == 2 and results['newmap-day']['talk']
            and results['newmap-night']['slots'] == 0
            and results['newmap-0D02']['slots'] == results['original-0D02']['slots'] > 0
            and results['newmap-0E00']['slots'] == results['original-0E00']['slots'],
        }
        if objects:
            checks['objects'] = all(r['objects'] == r['expected_objects'] for r in objects.values())
        (out / 'results.json').write_text(json.dumps({'cases': results, 'objects': objects, 'checks': checks},
                                                     ensure_ascii=False,
                                                     indent=2) + '\n', encoding='utf-8')
        for name, r in results.items():
            print(f'{name}: 목록 {r["list"]} 인물 {r["slots"]} 슬롯 {r["npc_end"]:02X}/{r["free_slot"]:02X}'
                  f'(예측 {r["expected_free_slot"]:02X}) 끝 {r["list_end"]}/{r["expected_list_end"]} '
                  f'표 불일치 {len(r["table_mismatch"])} 메시지 {",".join(r["messages"]) or "-"}')
        for name, r in objects.items():
            print(f'{name}: 인물 끝 {r["npc_end"]:02X} 다음 빈 슬롯 {r["free_slot"]:02X} 물체 {r["objects"]}'
                  f'(예측 {r["expected_objects"]})')
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        require(all(checks.values()), '불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'{len(cases)}개 장면, 검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
