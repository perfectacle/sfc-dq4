"""새 맵 번호(dq5newmap.py + dq5exitreloc.py --new-map)를 MesenCE에서 밟아 확인한다.

새 맵 0D/05 를 0D/02 의 레코드·속성으로 만들고, 0D/01 의 출구 1(원래 0D/02 로 감)을 0D/05 로 돌린 롬을 만든다.
0D/05 의 출구는 0D/02 와 같은 0D/01 출구 1 이다. 0D/05 의 인물 목록은 다음 그룹 첫 맵(0E/00, 인물 없음)을 읽는다.
원본 롬과 같은 자리를 밟아 도착 맵·칸·층과, 맵 속성이 들어간 WRAM(구역·전투 배경·주문 막기·곡 인자)·인물 뒤 슬롯을 견준다.
출력은 --out의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5newmapcheck.py rom/dq5.sfc --state work/state/ship.mss
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

import dq5exitcheck
from dq5exit import arrival, exit_attrs
from dq5exitcheck import command, dp86_allowed, require, run, warp_exit
from dq5map import Rom, lorom

HERE = Path(__file__).resolve().parent
COPY_0D02 = {'record': {'copy': '0D/02'}, 'attrs': {'copy': '0D/02'}}
# 0D/01 의 출구 1(원래 0D/02 로 감)을 새 맵으로 돌리고, 새 맵의 출구는 0D/02 처럼 0D/01 출구 1 로 둔다.
# 롬마다 (dq5newmap 입력, 자리 선택, 새 맵, 출구 고치기 대상(0D/01 계단이 갈 맵, 출구 종류)).
#  n: 0D/05 하나(그룹 표만 같은 뱅크로).  m: 0D/05~0D/18 스무 개(맵 포인터·속성 덩어리를 뱅크 3E 로, DB 즉값까지).
#  g: 새 그룹 36 의 36/00(들어가는 곳 표를 3E 로, 인물 그룹 포인터·빈 목록은 인물 도구로).
#  h: 그룹 50 의 50/52(50/51 복사, 속성은 조우 도구로 목록째 3D 로).
#  m·g 의 새 맵은 문 표를 건너뛰어 다른 맵의 문 목록이나 표 밖을 읽는다(문 표 읽기 허용).
#  doors: 0D/05~0D/07 을 더하고 문 표를 늘림(뱅크 01 을 3D 에 복사).  thru: 같은 맵을 문 표 읽기 허용으로(대조).
# doors 롬은 문 표를 옮겼으므로 옛 문 표 자리를 읽는 곳이 없어야 한다.
dq5exitcheck.STALE['doors'] = '01D2FC-01D8C1'
# 01/04 (48,1) 문(잠금 6) 아래에서 위를 보고 명령 창의 とびら(왼쪽 아래)를 고름. 열쇠가 없으면 메시지 187.
DOOR_CMD = 'up:4,wait:20,a:6,wait:60,down:6,wait:15,down:6,wait:15,down:6,wait:15,a:6,wait:250'
# 같은 문에서 どうぐ(오른쪽 열 둘째)로 첫 칸의 ラインハットのカギ(C9)를 つかう. 11:8E54 의 JSL 로 입구 01:D97B 를 지나 문이 열림
# (메시지 1A2). 이 입구가 옛 문 표를 읽으면 STALE 감시가 잡는다.
# 01/00 성문 (31,51) 을 이벤트 명령 C4(입구 01:D915)로 열고, 이어 C5(01:F117)로 닫는다. 명령을 7E:1A0D 에 두고
# $19B3 으로 건다. 1A/00 (36,27)·19/00 (32,47) 은 문 종류 3F·40 이라 01:E170 갈래로 표 F037·F067 을 읽는다.
EVENT = '{},19B3=0D,19B4=1A,19B5=00,19AE|80'
OPEN = EVENT.format('1A0D=C4,1A0E=1F,1A0F=33,1A10=02,1A11=FF')
OPEN_3F = EVENT.format('1A0D=C4,1A0E=24,1A0F=1B,1A10=02,1A11=FF')
OPEN_40 = EVENT.format('1A0D=C4,1A0E=20,1A0F=2F,1A10=02,1A11=FF')
CLOSE = EVENT.format('1A0D=C4,1A0E=1F,1A0F=33,1A10=02,1A11=C5,1A12=1F,1A13=33,1A14=02,1A15=FF')
KEY_CMD = 'up:4,wait:20,a:6,wait:60,right:6,wait:15,down:6,wait:15,a:6,wait:60,a:6,wait:60,a:6,wait:120,a:6,wait:250'
VARIANTS = {
    'n': ({'format': 'dq5newmap/1', 'maps': [{'map': '0D/05', **COPY_0D02}]}, [], ['0D/05'], ('0D/05', 'same-group')),
    'm': ({'format': 'dq5newmap/1', 'maps': [{'map': f'0D/{bd:02X}', **COPY_0D02} for bd in range(5, 0x19)]},
          ['--pointer-table-at', '3E:8000', '--attr-table-at', '3E:A000', '--allow-door-readthrough'],
          [f'0D/{bd:02X}' for bd in range(5, 0x19)], ('0D/18', 'same-group')),
    'g': ({'format': 'dq5newmap/1', 'groups': [{'group': '36', 'entrance': {'copy': '0D'}}],
           'maps': [{'map': '36/00', **COPY_0D02}]}, ['--entrance-table-at', '3E:C000', '--allow-door-readthrough'], ['36/00'],
          ('36/00', 'other-group')),
    'h': ({'format': 'dq5newmap/1', 'maps': [{'map': '50/52', 'record': {'copy': '50/51'}}]}, [], [], None),
    'doors': ({'format': 'dq5newmap/1', 'maps': [{'map': f'0D/{bd:02X}', **COPY_0D02} for bd in range(5, 8)]},
              ['--door-bank', '3D'], ['0D/05', '0D/06', '0D/07'], ('0D/07', 'same-group')),
    'thru': ({'format': 'dq5newmap/1', 'maps': [{'map': f'0D/{bd:02X}', **COPY_0D02} for bd in range(5, 8)]},
             ['--allow-door-readthrough'], ['0D/05', '0D/06', '0D/07'], ('0D/07', 'same-group')),
}
# 인물 기본 목록을 인물 도구(dq5npcrelocate.py --new-map)로 더하는 롬.
NPC_NEW = {'g', 'doors'}
# 그룹 50 이상 새 맵의 속성(23:FDD6 목록)은 조우 도구로 쓴다. 50/52 는 50/51 과 같은 값(구역 없음, 꼬리 00 0A 0D).
ENCOUNTER = {'h': ({'format': 'dq5encounter/1', 'maps': [{'map': '50/52', 'areas': [255, 255, 255], 'tail': [0, 10, 13]}]},
                   ['--high-at', '3D:8000'])}
# 출구 표가 원래 자리보다 늘어 넘치므로 출구는 옛 레코드 자리로, 레코드는 늘린 뱅크로 옮긴다.
EXIT_PLACES = ('--exits-at', '2A:D812', '--records-at', '3F:8000')
# (이름, 롬, TO, TEST, 기대: 맵, 칸(('arrival', BC, BD, 출구) 면 그 출구의 도착 칸), 층, 속성을 견줄 장면,
#  인물 뒤 슬롯 7E:1983(None 이면 보지 않음))
# 0D/01·0D/02 의 계단 블록은 (14~15, 10~11). 블록 밖 (14,9) 에서 내려가야 발동한다(블록 안에서 시작하면 그대로 섬).
# 0D/02 의 인물 한 명이 (10,8) 에 서 있어 원본은 (10,6) 에서 멈춘다. 0D/05 는 인물이 없어(슬롯 08) 그 자리까지 간다.
CASES = [
    ('enter', 'n', '0D/01,14,9,1', 'down:16', ('0D/05', ('arrival', 0x0D, 5, 0), None, 'enter-original', 0x08)),
    ('enter-original', 'original', '0D/01,14,9,1', 'down:16', ('0D/02', ('arrival', 0x0D, 2, 0), None, None, 0x09)),
    ('walk', 'n', '0D/05,12,4,1', 'left:32,down:32', ('0D/05', (10, 8), 1, 'walk-original', 0x08)),
    ('walk-original', 'original', '0D/02,12,4,1', 'left:32,down:32', ('0D/02', (10, 6), 1, None, 0x09)),
    ('leave', 'n', '0D/05,14,9,1', 'down:16', ('0D/01', ('arrival', 0x0D, 1, 1), None, 'leave-original', None)),
    ('leave-original', 'original', '0D/02,14,9,1', 'down:16', ('0D/01', ('arrival', 0x0D, 1, 1), None, None, None)),
    ('later', 'n', '21/02,111,8,1', 'up:16', ('0E/03', ('arrival', 0x0E, 3, 1), None, 'later-original', None)),
    ('later-original', 'original', '21/02,111,8,1', 'up:16', ('0E/03', ('arrival', 0x0E, 3, 1), None, None, None)),
    ('later-stay', 'n', '21/02,50,43,1', 'wait:16', ('21/02', (50, 43), None, 'later-stay-original', None)),
    ('later-stay-original', 'original', '21/02,50,43,1', 'wait:16', ('21/02', (50, 43), None, None, None)),
    ('earlier', 'n', '01/00,60,79,2', 'down:16', ('01/03', ('arrival', 1, 3, 0), None, 'earlier-original', None)),
    ('earlier-original', 'original', '01/00,60,79,2', 'down:16', ('01/03', ('arrival', 1, 3, 0), None, None, None)),
    ('many-enter', 'm', '0D/01,14,9,1', 'down:16', ('0D/18', ('arrival', 0x0D, 0x18, 0), None, 'enter-original', None)),
    ('many-middle', 'm', '0D/0F,12,4,1', 'wait:16', ('0D/0F', (12, 4), 1, 'walk-original', None)),
    ('many-leave', 'm', '0D/18,14,9,1', 'down:16', ('0D/01', ('arrival', 0x0D, 1, 1), None, 'leave-original', None)),
    ('many-later', 'm', '21/02,111,8,1', 'up:16', ('0E/03', ('arrival', 0x0E, 3, 1), None, 'later-original', None)),
    ('many-earlier', 'm', '01/00,60,79,2', 'down:16', ('01/03', ('arrival', 1, 3, 0), None, 'earlier-original', None)),
    ('group-enter', 'g', '0D/01,14,9,1', 'down:16', ('36/00', ('arrival', 0x36, 0, 0), None, 'enter-original', 0x08)),
    ('group-leave', 'g', '36/00,14,9,1', 'down:16', ('0D/01', ('arrival', 0x0D, 1, 1), None, 'leave-original', None)),
    ('group-later', 'g', '21/02,111,8,1', 'up:16', ('0E/03', ('arrival', 0x0E, 3, 1), None, 'later-original', None)),
    ('high-new', 'h', '50/52,31,17,1', 'down:16', ('05/01', (33, 47), 1, 'high-original', None)),
    ('high-old', 'h', '50/51,31,17,1', 'down:16', ('05/01', (33, 47), 1, 'high-original', None)),
    ('high-original', 'original', '50/51,31,17,1', 'down:16', ('05/01', (33, 47), 1, None, None)),
    ('high-stay', 'h', '50/52,31,17,1', 'wait:16', ('50/52', (31, 17), 1, 'high-stay-original', None)),
    ('high-stay-original', 'original', '50/51,31,17,1', 'wait:16', ('50/51', (31, 17), 1, None, None)),
    ('doors-enter', 'doors', '0D/01,14,9,1', 'down:16', ('0D/07', ('arrival', 0x0D, 7, 0), None, 'enter-original', 0x08)),
    ('doors-new', 'doors', '0D/07,8,10,1', 'wait:10', ('0D/07', (8, 10), None, None, None), {'cell': '8,9', 'cell_like': 'doors-new-original'}),
    ('thru-new', 'thru', '0D/07,8,10,1', 'wait:10', ('0D/07', (8, 10), None, None, None),
     {'cell': '8,9', 'cell_unlike': 'doors-new-original'}),
    ('doors-new-original', 'original', '0D/02,8,10,1', 'wait:10', ('0D/02', (8, 10), None, None, None), {'cell': '8,9'}),
    ('doors-lock', 'doors', '01/04,48,2,1', DOOR_CMD, ('01/04', (48, 2), None, None, None),
     {'msglog': True, 'cell': '48,1', 'msgs_like': 'doors-lock-original', 'cell_like': 'doors-lock-original'}),
    ('doors-lock-original', 'original', '01/04,48,2,1', DOOR_CMD, ('01/04', (48, 2), None, None, None),
     {'msglog': True, 'cell': '48,1', 'msgs': '187'}),
    ('doors-key', 'doors', '01/04,48,2,1', KEY_CMD, ('01/04', (48, 2), None, None, None),
     {'late': '2056=C9', 'msglog': True, 'cell': '48,1', 'msgs_like': 'doors-key-original', 'cell_like': 'doors-key-original',
      'cell_unlike': 'doors-lock-original'}),
    ('doors-key-original', 'original', '01/04,48,2,1', KEY_CMD, ('01/04', (48, 2), None, None, None),
     {'late': '2056=C9', 'msglog': True, 'cell': '48,1', 'msgs': '1A2'}),
    ('doors-open', 'doors', '01/00,31,54,1', 'wait:400', ('01/00', (31, 54), None, None, None),
     {'late': OPEN, 'cell': '31,51', 'cell_like': 'doors-open-original', 'cell_unlike': 'doors-gate-original'}),
    ('doors-open-original', 'original', '01/00,31,54,1', 'wait:400', ('01/00', (31, 54), None, None, None),
     {'late': OPEN, 'cell': '31,51'}),
    ('doors-close', 'doors', '01/00,31,54,1', 'wait:500', ('01/00', (31, 54), None, None, None),
     {'late': CLOSE, 'cell': '31,51', 'cell_like': 'doors-close-original', 'cell_unlike': 'doors-open-original'}),
    ('doors-close-original', 'original', '01/00,31,54,1', 'wait:500', ('01/00', (31, 54), None, None, None),
     {'late': CLOSE, 'cell': '31,51'}),
    ('doors-gate-original', 'original', '01/00,31,54,1', 'wait:400', ('01/00', (31, 54), None, None, None), {'cell': '31,51'}),
    ('doors-open3f', 'doors', '1A/00,36,30,1', 'wait:400', ('1A/00', (36, 30), None, None, None),
     {'late': OPEN_3F, 'cell': '36,27', 'cell_like': 'doors-open3f-original', 'cell_unlike': 'doors-gate3f-original'}),
    ('doors-open3f-original', 'original', '1A/00,36,30,1', 'wait:400', ('1A/00', (36, 30), None, None, None),
     {'late': OPEN_3F, 'cell': '36,27'}),
    ('doors-gate3f-original', 'original', '1A/00,36,30,1', 'wait:400', ('1A/00', (36, 30), None, None, None), {'cell': '36,27'}),
    ('doors-open40', 'doors', '19/00,32,50,1', 'wait:400', ('19/00', (32, 50), None, None, None),
     {'late': OPEN_40, 'cell': '32,47', 'cell_like': 'doors-open40-original', 'cell_unlike': 'doors-gate40-original'}),
    ('doors-open40-original', 'original', '19/00,32,50,1', 'wait:400', ('19/00', (32, 50), None, None, None),
     {'late': OPEN_40, 'cell': '32,47'}),
    ('doors-gate40-original', 'original', '19/00,32,50,1', 'wait:400', ('19/00', (32, 50), None, None, None), {'cell': '32,47'}),
    ('doors-room', 'doors', '01/03,14,8,1', 'wait:10', ('01/03', (14, 8), None, None, None),
     {'cell': '14,7', 'cell_like': 'doors-room-original'}),
    ('doors-room-original', 'original', '01/03,14,8,1', 'wait:10', ('01/03', (14, 8), None, None, None), {'cell': '14,7'}),
]


def build_rom(original, out, key):
    """새 맵 패치와 출구 패치를 원본에서 따로 만들어 함께 빌드한다."""
    doc, places, new_maps, target = VARIANTS[key]
    source = out / f'{key}-newmap.json'
    source.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    command('dq5newmap.py', original, 'patch', source, '-o', out / f'{key}-newmap.dq5patch.json', *places)
    command('dq5newmap.py', original, 'check', source, *places)
    manifests = [out / f'{key}-newmap.dq5patch.json']
    new = [x for m in new_maps for x in ('--new-map', m)]
    if key in NPC_NEW:
        # 새 그룹의 인물 그룹 포인터와 빈 기본 목록은 인물 도구가 둔다(목록은 그 도구의 기본 자리로 옮김).
        npc = out / f'{key}-npc.json'
        npc.write_text(json.dumps({'format': 'dq5npcrelocate/1', 'scripts': []}) + '\n', encoding='utf-8')
        command('dq5npcrelocate.py', original, 'patch', npc, '-o', out / f'{key}-npc.dq5patch.json', *new)
        manifests.append(out / f'{key}-npc.dq5patch.json')
    if key in ENCOUNTER:
        enc, extra = ENCOUNTER[key]
        source = out / f'{key}-encounter.json'
        source.write_text(json.dumps(enc) + '\n', encoding='utf-8')
        command('dq5encounterwrite.py', original, 'patch', source, '-o', out / f'{key}-encounter.dq5patch.json', *extra)
        manifests.append(out / f'{key}-encounter.dq5patch.json')
    if target:
        exits = out / f'{key}-exits.json'
        command('dq5exitreloc.py', original, 'dump', '-o', exits, *new)
        table = json.loads(exits.read_text(encoding='utf-8'))
        rows = {r['map']: r for r in table['exits']}
        name, kind = target
        group, bd = (int(v, 16) for v in name.split('/'))
        back = dict(rows['0D/02']['records'][0])
        if kind == 'other-group':
            back = {'kind': 'other-group', 'destination_map': 1, 'exit': 1, 'group': 0x0D}
        for m in new_maps:
            rows[m]['records'] = [dict(back)]
        rows['0D/01']['records'][1] = ({'kind': 'same-group', 'destination_map': bd, 'exit': 0} if kind == 'same-group'
                                       else {'kind': 'other-group', 'destination_map': bd, 'exit': 0, 'group': group})
        exits.write_text(json.dumps(table, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        command('dq5exitreloc.py', original, 'patch', exits, '-o', out / f'{key}-exits.dq5patch.json', *new, *EXIT_PLACES)
        command('dq5exitreloc.py', original, 'check', exits, *new, *EXIT_PLACES)
        manifests.append(out / f'{key}-exits.dq5patch.json')
    rom = out / f'{key}.sfc'
    command('dq5build.py', original, 'build', *manifests, '-o', rom, '--ips', out / f'{key}.ips')
    return rom


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/newmapcheck')
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
        roms = {'original': (original, lorom(0x2AEFF5), dp86_allowed(original))}
        for key in VARIANTS:
            built = build_rom(original, out, key)
            roms[key] = (built, warp_exit(built), dp86_allowed(built))
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            seen = list(pool.map(lambda case: run(case, roms, state, out, mesence, libdir), CASES))
        attrs, slots, cells, msgs = {}, {}, {}, {}
        for case in CASES:
            text = (out / case[0] / 'warp.txt').read_text(encoding='utf-8')
            cell_line = re.search(r'^cell (.+)$', text, re.MULTILINE)
            msg_line = re.search(r'^msgs (\S+)', text, re.MULTILINE)
            cells[case[0]] = cell_line[1] if cell_line else None
            msgs[case[0]] = msg_line[1] if msg_line else None
            found = re.search(r'map attrs (1A98=\w\w 1AA0=\w\w 194D=\w\w 194B=\w\w) 1983=(\w\w)', text)
            require(found is not None, f'{case[0]}: 속성 줄이 없음')
            attrs[case[0]], slots[case[0]] = found[1], int(found[2], 16)
        results = []
        for case, (got_map, cell, layer, _) in zip(CASES, seen):
            name, rom, to, test, (want_map, want_cell, want_layer, pair, slot), *extra = case
            extra = extra[0] if extra else {}
            if want_cell and want_cell[0] == 'arrival':
                _, bc, bd, n = want_cell
                data = Rom(roms[rom][0].read_bytes())
                want_cell = arrival(data, bc, bd, n, exit_attrs(data))
            ok = (got_map == want_map and cell == tuple(want_cell) and (want_layer is None or layer == want_layer)
                  and (pair is None or attrs[name] == attrs[pair]) and (slot is None or slots[name] == slot)
                  and ('cell_like' not in extra or cells[name] == cells[extra['cell_like']])
                  and ('cell_unlike' not in extra or cells[name] != cells[extra['cell_unlike']])
                  and ('msgs_like' not in extra or msgs[name] == msgs[extra['msgs_like']])
                  and ('msgs' not in extra or msgs[name] == extra['msgs']))
            results.append({'case': name, 'rom': rom, 'to': to, 'test': test, 'map': got_map, 'cell': list(cell),
                            'layer': layer, 'attrs': attrs[name], 'slot': slots[name], 'expected_slot': slot,
                            'expected_map': want_map,
                            'expected_cell': list(want_cell), 'attrs_like': pair, 'cell_bytes': cells[name],
                            'msgs': msgs[name], 'passed': ok})
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for r in results:
            extra = (f' 셀 {r["cell_bytes"]}' if r['cell_bytes'] else '') + (f' 메시지 {r["msgs"]}' if r['msgs'] else '')
            print(f'{r["case"]}: {r["map"]} {tuple(r["cell"])} 층 {r["layer"]:02X} {r["attrs"]} 1983={r["slot"]:02X}'
                  f'{extra}{"" if r["passed"] else " 불일치"}')
        failed = [r['case'] for r in results if not r['passed']]
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
