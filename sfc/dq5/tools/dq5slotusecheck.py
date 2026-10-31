"""맵을 놓은 뒤 7E:1983 부터 슬롯을 더 쓰는 장면(04:FB1C, 01:BA95)을 MesenCE 에서 잰다.

  inn       1A/02 アルカパ 여관, 대체 목록 10:B7BA(7E:2195 bit3). パパス 에게 말을 걸어 번호 01 → 02:AE69 → 04:FB1C.
  inn-leave 같은 장면에 A 를 쉰 번 이어 넣음. 메시지 20C~20F·214~217(24:8BAF 에 들어선 번호) 뒤 1A/04 로 옮겨 감
  inn-grown 같은 장면, dq5npcrelocate.py --allow-growth 로 10:B7BA 를 인물 23명(슬롯 1F 까지)으로 늘린 롬
  ev3       06/08 이벤트 3((37,16)-(38,21) 에 들어섬) → 06:D704 → 04:FB1C
  talk23a   선실 パパス 대화 번호를 23A(06/00 의 マスタードラゴン 대화)로 → 06:B4F7 → 01:BA95
  overflow  같은 장면에 시작 때 7E:1983 = 1E 를 두어, 01:BA95 가 슬롯 20·21 을 쓰게 함
  alt0605   06/05 대체 목록 10:AB3A(7E:2190 bit7)의 10:ABB5 스크립트 → 05:E931 → 01:BA95. 기다리는 7E:21A1 bit6 을 켜 둠
  map1100   11/00 기본 목록 05:A3D2 스크립트(7E:219F bit7 을 기다림) → 05:E72A → 05:E838·05:E7EC → 04:FB1C 두 번.
            05:E72A 는 인물 01·02 가 일행에 살아 있을 때만 슬롯을 만들므로, 도착 뒤 일행 레코드 1·2 에
            인물 레코드 표(23:C014)의 01·02 를 베낌
  map0109   01/09 대체 목록 10:8E0D(7E:2190 bit5)의 ヘンリー(15,6) 대화 234 → 06:B83C → 번호 3D(15:F588, 7E:219F bit1 을
            기다림) → 1E:DDB3 → 05:E830·05:E7E4 → 04:FB1C 두 번. 06:B83C 는 일행의 인물 01·02 마다 7E:21D2 bit2·bit1 을
            켜므로 map1100 과 같은 일행을 두고 219F bit1 을 켜 둠

  talk04d   선실 パパス 대화 번호를 04D(22/00 ポワン)로, 7E:219A bit5 를 켜고 2190 bit5 를 끔 → 메시지 25E → 06:C00A →
            02:B0DC → 04:FB1C 한 번
  map0600   06/00 대체 목록 10:AA73(7E:2190 bit7) 의 (37,51) 대화 점 아래 (37,54) 에서 위를 보고 대화 23A → 01:BA95.
            02:B3B4 가 베끼는 원본 슬롯 X = 07, 메시지 512~516 뒤 장면이 18/03 으로 옮겨 감
  enter0206 02/06 에 들어서기만 함. 메시지 1D1 을 띄운 인라인 스크립트 자리를 스택(01:CEA9 가 넣은 $AE~$B0·$90)에서 읽음
  morning1a00  1A/00 대체 목록 10:B4E3(7E:2198 bit6). 아침 장면(메시지 23C~241) 뒤 06:CAC8 → 02:AF66 이 슬롯 08 을 슬롯 02 로
            베낌. 끝의 인물 표로 02:AF9B 의 LDX #$13·#$12 가 가리키는 인물을 봄

장면마다 부르는 곳을 지날 때의 $1983·Y(슬롯), 메시지 번호(와 스택 24바이트), 끝의 $1995(OBJ VRAM 다음 타일)를 적는다(lua/dq5slotuse.lua).
원본 롬·선실 상태는 읽기만 하고 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5slotusecheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5progresscheck import command, environment, require, run, save_json

HERE = Path(__file__).resolve().parent
TALK = 'b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4'
PRESS = 'a:4,wait:30,a:4,wait:200,a:4,wait:200,a:4,wait:200,a:4,wait:200,a:4,wait:200,a:4,wait:200,a:4,wait:2000'
INN = {'DRIVER': 'dq5warp.lua', 'TO': '1A/02,12,14', 'SET': '2195|0C', 'MAXF': '6000', 'SETTLE': '120',
       'TEST': f'up:16,wait:30,{PRESS}'}
EV3 = {'DRIVER': 'dq5warp.lua', 'TO': '06/08,36,18', 'MAXF': '4000', 'SETTLE': '120', 'TEST': 'right:20,wait:2500'}
T23A = {'DRIVER': 'dq5msg.lua', 'MAXF': '1200', 'POKE': '7E36EB=3A;7E370B=02',
        'PRE': TALK + ',a:4,wait:200' * 5}
PRESS20 = 'wait:30,' + 'a:4,wait:150,' * 20 + 'wait:1500'
ALT0605 = {'DRIVER': 'dq5warp.lua', 'TO': '06/05,25,23', 'SET': '2190|80;21A1|40;219F&BF', 'MAXF': '6000',
           'SETTLE': '120', 'TEST': PRESS20}
PRESS30 = 'wait:30,' + 'a:4,wait:150,' * 30 + 'wait:2000'
T04D = dict(T23A, POKE='7E36EB=4D;7E370B=00', SET='219A|20;2190&DF', MAXF='2400', PRE=TALK + ',a:4,wait:200' * 10)
MAP0600 = {'DRIVER': 'dq5warp.lua', 'TO': '06/00,37,54', 'SET': '2190|80', 'MAXF': '5000', 'SETTLE': '120',
           'TEST': 'up:3,' + 'a:4,wait:150,' * 15 + 'wait:1500'}
ENTER0206 = {'DRIVER': 'dq5warp.lua', 'TO': '02/06,24,14', 'MAXF': '1500', 'SETTLE': '120', 'TEST': 'wait:300'}
INN_LEAVE = dict(INN, MAXF='10500', TEST='up:16,wait:30,' + 'a:4,wait:150,' * 50 + 'wait:2000')
MORNING1A00 = {'DRIVER': 'dq5warp.lua', 'TO': '1A/00,38,35', 'SET': '2198|40', 'MAXF': '9000', 'SETTLE': '120',
               'TEST': PRESS30}
INN_LIST = '10:B7BA'
PERSONS = 0x23C014          # 인물 레코드 표, 42바이트씩(일행 레코드 7E:2040 + i×42 와 같은 꼴)


def party_sets(rom, flag):
    """일행을 주인공·인물 01·인물 02 셋으로 두고 flag(예: 219F|98)를 켜는 LATESET."""
    data = rom.read_bytes()
    at = (PERSONS >> 16 & 0x7F) * 0x8000 + (PERSONS & 0x7FFF)
    sets = [f'{0x2040 + i * 42 + k:04X}={b:02X}' for i in (1, 2) for k, b in enumerate(data[at + i * 42:at + i * 42 + 42])]
    return ';'.join(sets + ['201D=03', '201E=03', '201F=03', '2020=00', '2021=01', '2022=02', flag])


# 슬롯을 더 쓰는 루틴과 스크립트가 부르는 그 앞 루틴. 롬 전체에서 부르는 바이트 꼴을 찾아 아래와 같아야 한다.
CALLERS = {
    0x04FB1C: {('JSL', '02:AE7B'), ('JSL', '02:AFB8'), ('JSL', '02:AFE5'), ('JSL', '02:B0F3'), ('JSL', '05:E806'),
               ('JSL', '05:E852'), ('JSL', '06:D716')},
    0x01BA95: {('JSL', '05:E931'), ('JSL', '06:B52D')},
    0x05E931: {('스크립트 37', '10:ABD1')},
    0x05E72A: {('스크립트 37', '05:A3E5')},
    0x05E7E4: {('JSL', '1E:DDE3')},
    0x05E830: {('JSL', '1E:DDC7')},
    0x1EDDB3: {('이벤트 A0', '15:F58B')},
}


def callers(data, target):
    """target 을 부르는 곳. 긴 호출(JSL·JML, 인물 스크립트 05·37, 이벤트 스크립트 A0)은 롬 전체,
    같은 뱅크 호출(JSR·JMP·JSR (a,X)·JMP (a,X), 뱅크 06 이면 대화 스크립트 00)은 그 뱅크에서 찾는다.
    긴 호출은 FastROM 미러(뱅크 | 80) 꼴도 찾는다."""
    def name(o):
        return f'{o // 0x8000:02X}:{0x8000 | o % 0x8000:04X}'
    long = {0x22: 'JSL', 0x5C: 'JML', 0x05: '스크립트 05', 0x37: '스크립트 37', 0xA0: '이벤트 A0'}
    near = {0x20: 'JSR', 0x4C: 'JMP', 0xFC: 'JSR', 0x7C: 'JMP'} | ({0x00: '대화 00'} if target >> 16 == 6 else {})
    out = {(long[data[m.start() - 1]], name(m.start() - 1))
           for bank in (target >> 16 & 0x7F, target >> 16 | 0x80)
           for m in re.finditer(re.escape(bytes([target & 0xFF, target >> 8 & 0xFF, bank])), data)
           if m.start() and data[m.start() - 1] in long}
    base = (target >> 16 & 0x7F) * 0x8000
    for m in re.finditer(re.escape(bytes([target & 0xFF, target >> 8 & 0xFF])), data[base:base + 0x8000]):
        if m.start() and data[base + m.start() - 1] in near:
            out.add((near[data[base + m.start() - 1]], name(base + m.start() - 1)))
    return out


def scenes(rom):
    map1100 = dict(ALT0605, TO='11/00,100,67', LATESET=party_sets(rom, '219F|98'))
    del map1100['SET']
    map0109 = dict(ALT0605, TO='01/09,15,8', SET='2190|20', LATESET=party_sets(rom, '219F|02'), MAXF='9000',
                   TEST='wait:30,up:8,' + 'a:4,wait:150,' * 40 + 'wait:1500')
    return {'inn': ('original', INN), 'inn-leave': ('original', INN_LEAVE), 'inn-grown': ('grown', INN), 'ev3': ('original', EV3),
            'talk23a': ('original', T23A), 'overflow': ('original', dict(T23A, SET='1983=1E')),
            'alt0605': ('original', ALT0605), 'map1100': ('original', map1100),
            'map0109': ('original', map0109), 'talk04d': ('original', T04D), 'map0600': ('original', MAP0600),
            'enter0206': ('original', ENTER0206), 'morning1a00': ('original', MORNING1A00)}


def grow_document():
    """1A/02 대체 목록 10:B7BA 의 다섯 명 뒤에 첫 인물의 사본 18명을 더해 23명(인물 뒤 슬롯 1F)으로."""
    filler = [{'from': 0, 'fields': {'x': 30 + i, 'y': 2}} for i in range(18)]
    entries = [{'from': i} for i in range(5)] + filler
    return {'format': 'dq5npcrelocate/1', 'lists': [{'list': INN_LIST, 'entries': entries}]}


def scene(name, rom, options, state, out, mesence, libdir):
    dest = out / name
    env = environment(libdir, state, dest)
    env.update({k: v for k, v in options.items() if k != 'DRIVER'}, DRIVER=str(HERE / 'lua' / options['DRIVER']))
    run(mesence, rom, HERE / 'lua/dq5slotuse.lua', dest, env)
    text = (dest / 'slots.txt').read_text()
    calls = [(m[1], int(m[2], 16), int(m[3], 16), int(m[5], 16)) for m in
             re.finditer(r'pc (\w{6}) map \S+ 1982=\w\w 1983=(\w\w) 1995=(\w{4}) X=(\w\w) Y=(\w\w)', text)]
    sources = [(m[1], int(m[2], 16)) for m in re.finditer(r'pc (\w{6}) map \S+ 1982=\w\w 1983=\w\w 1995=\w{4} '
                                                           r'X=(\w\w) Y=\w\w', text)]
    end = re.search(r'end f\d+ map (\S+) 1982=(\w\w) 1983=(\w\w) 1995=(\w{4})', text)
    return {'calls': calls, 'sources': sources, 'messages': re.findall(r'msg (\w{3})', text), 'map': end[1],
            'stacks': dict(re.findall(r'msg (\w{3}) st=(\w+)', text)),
            'placed': int(end[2], 16), 'free': int(end[3], 16), 'obj_tiles': int(end[4], 16)}


def script_of(stack):
    """메시지 루틴 24:8BAF 에 들어설 때 스택에서, 인라인 스크립트 명령(01:CEA9)이 부른 것이면 (명령 자리, 슬롯).
    위에서부터 JSR 돌아갈 곳 2·Y·X·A 6·B·P 2·24:815A 2·JSL 돌아갈 곳 3·B 1·$B0·$AF·$AE·$90."""
    b = bytes.fromhex(stack)
    if b[12:15] != bytes.fromhex('b9ce01'):
        return None
    return f'{b[16]:02X}:{b[17]:02X}{b[18]:02X}', b[19]


def slot_table(out, name, slots):
    """끝 WRAM 인물 표의 슬롯마다 (X, Y, 그림)."""
    w = (out / name / 'final.wram').read_bytes()
    return {s: (w[0x3020 + s], w[0x3080 + s], w[0x3220 + s]) for s in slots}


def overwritten(out, name):
    """01:BA95 앞뒤 WRAM 에서, 인물 표 칸(7E:3000~37FF, $20 슬롯씩)의 슬롯 0·1 자리가 바뀐 바이트."""
    before = (out / name / 'ba95-before.wram').read_bytes()
    after = (out / name / 'ba95-after.wram').read_bytes()
    return [f'7E:{a:04X}' for a in range(0x3000, 0x3800) if (a - 0x3000) % 0x20 in (0, 1) and before[a] != after[a]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/slotusecheck')
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
        save_json(out / 'grow.json', grow_document())
        command('dq5npcrelocate.py', original, 'patch', out / 'grow.json', '-o', out / 'grow.dq5patch.json',
                '--allow-growth')
        command('dq5build.py', original, 'build', out / 'grow.dq5patch.json', '-o', out / 'grown.sfc')
        # 한 명 더 늘리면 1A/02 는 장면이 슬롯 하나를 더 써 한도 1F 를 넘으므로 거부되어야 한다.
        over = grow_document()
        over['lists'][0]['entries'].append({'from': 0, 'fields': {'x': 48, 'y': 2}})
        save_json(out / 'grow-over.json', over)
        refused = subprocess.run([sys.executable, str(HERE / 'dq5npcrelocate.py'), str(original), 'patch',
                                  str(out / 'grow-over.json'), '-o', str(out / 'grow-over.dq5patch.json'),
                                  '--allow-growth'], capture_output=True, text=True, timeout=120)
        roms = {'original': original, 'grown': out / 'grown.sfc'}
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {n: pool.submit(scene, n, roms[r], o, state, out, mesence, libdir)
                       for n, (r, o) in scenes(original).items()}
            seen = {n: f.result() for n, f in futures.items()}

        def made(name, site):
            return [(f, y) for pc, f, _, y in seen[name]['calls'] if pc == site]

        data = original.read_bytes()
        found = {f'{t:06X}': sorted(callers(data, t)) for t in CALLERS}
        checks = {
            'callers': all(callers(data, t) == want for t, want in CALLERS.items()),
            'inn': made('inn', '02B3B4') == [(0x0E, 0x0D)] and '77F' in seen['inn']['messages']
            and seen['inn']['free'] == 0x0E,
            'inn-grown': made('inn-grown', '02B3B4') == [(0x20, 0x1F)] and seen['inn-grown']['free'] == 0x20
            and '20C' in seen['inn-grown']['messages'] and '20C' in seen['inn']['messages'],
            # 대화 029 뒤 입력을 이어 넣으면 메시지 20C~20F·214~217 이 이어지고 1A/04 로 옮겨 가, 같은 방문에서 다시 걸 수 없다.
            'inn-leave': {f'{m:03X}' for m in (*range(0x20C, 0x210), *range(0x214, 0x218))}
            <= set(seen['inn-leave']['messages'])
            and not {f'{m:03X}' for m in range(0x210, 0x214)} & set(seen['inn-leave']['messages'])
            and seen['inn-leave']['map'] == '1A/04',
            'refuse': refused.returncode != 0 and '한도' in refused.stderr,
            'ev3': made('ev3', '02B3B4') == [(0x0E, 0x0D)] and seen['ev3']['free'] == 0x0E,
            'talk23a': [y for _, y in made('talk23a', '02B3B4')] == [0x0D, 0x0E, 0x0F, 0x10]
            and all(f == 0x0D for f, _ in made('talk23a', '02B3B4')) and not overwritten(out, 'talk23a'),
            'overflow': [y for _, y in made('overflow', '02B3B4')] == [0x1E, 0x1F, 0x20, 0x21]
            and len(overwritten(out, 'overflow')) > 0,
            # 01:BA95 는 $1983 부터 넷을 쓰고 $1983 은 그대로. 그 뒤의 02:B3B4 는 일행 슬롯으로 되돌려 베끼는 것.
            'alt0605': [y - f for f, y in made('alt0605', '02B3B4')[:4]] == [0, 1, 2, 3]
            and any(pc == '05E931' for pc, *_ in seen['alt0605']['calls'])
            and seen['alt0605']['free'] == made('alt0605', '02B3B4')[0][0],
            'map1100': [pc for pc, *_ in seen['map1100']['calls'] if pc in ('05E852', '05E806')] == ['05E852', '05E806']
            and len(made('map1100', '02B3B4')) == 2 and all(f == y + 1 for f, y in made('map1100', '02B3B4'))
            and seen['map1100']['free'] == made('map1100', '02B3B4')[0][1] + 2,
            'map0109': [pc for pc, *_ in seen['map0109']['calls'] if pc in ('06B83C', '1EDDB3', '05E852', '05E806')]
            == ['06B83C', '1EDDB3', '05E852', '05E806']
            and len(made('map0109', '02B3B4')) == 2 and all(f == y + 1 for f, y in made('map0109', '02B3B4'))
            and seen['map0109']['free'] == made('map0109', '02B3B4')[0][1] + 2,
            'talk04d': [pc for pc, *_ in seen['talk04d']['calls'] if pc in ('02B0F3', '04FB1C')] == ['02B0F3', '04FB1C']
            and made('talk04d', '02B3B4') == [(0x0E, 0x0D)] and '25E' in seen['talk04d']['messages'],
            'map0600': [y for _, y in made('map0600', '02B3B4')] == [0x0C, 0x0D, 0x0E, 0x0F]
            and all(f == 0x0C for f, _ in made('map0600', '02B3B4'))
            and [pc for pc, *_ in seen['map0600']['calls']][:2] == ['06B52D', '01BA95']
            and {x for pc, x in seen['map0600']['sources'] if pc == '02B3B4'} == {0x07}
            and seen['map0600']['map'] == '18/03',
            'enter0206': script_of(seen['enter0206']['stacks'].get('1D1', '')) == ('05:8D25', 0x09),
            'morning1a00': [pc for pc, *_ in seen['morning1a00']['calls'] if pc == '02AF66'] == ['02AF66']
            and '241' in seen['morning1a00']['messages']
            and slot_table(out, 'morning1a00', (0x02, 0x12, 0x13)) == {0x02: (22, 68, 0x32), 0x12: (84, 2, 0x30),
                                                                         0x13: (37, 71, 0x08)},
        }
        results = {n: {**v, 'calls': [(pc, f'{f:02X}', f'{t:04X}', f'{y:02X}') for pc, f, t, y in v['calls']],
                       'sources': [(pc, f'{x:02X}') for pc, x in v['sources']]} for n, v in seen.items()}
        results['overflow']['slot01_changed'] = overwritten(out, 'overflow')
        results['refuse'] = refused.stderr.strip().splitlines()[-1:] if refused.stderr else []
        save_json(out / 'results.json', {'scenes': results, 'callers': found, 'checks': checks})
        for n, v in seen.items():
            print(f'{n}: 맵 {v["map"]} 슬롯 쓰기 {[(f"{f:02X}", f"{y:02X}") for f, y in made(n, "02B3B4")]} '
                  f'끝 $1983 {v["free"]:02X} $1995 {v["obj_tiles"]:04X}')
        for t, sites in found.items():
            print(f'{t} 부르는 곳: {sites}')
        print(f'overflow: 슬롯 0·1 자리가 바뀐 바이트 {len(results["overflow"]["slot01_changed"])}개')
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        require(all(checks.values()), '불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'{len(checks)}건 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
