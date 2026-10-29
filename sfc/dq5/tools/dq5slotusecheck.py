"""맵을 놓은 뒤 7E:1983 부터 슬롯을 더 쓰는 장면(04:FB1C, 01:BA95)을 MesenCE 에서 잰다.

  inn       1A/02 アルカパ 여관, 대체 목록 10:B7BA(7E:2195 bit3). パパス 에게 말을 걸어 번호 01 → 02:AE69 → 04:FB1C
  inn-grown 같은 장면, dq5npcrelocate.py --allow-growth 로 10:B7BA 를 인물 23명(슬롯 1F 까지)으로 늘린 롬
  ev3       06/08 이벤트 3((37,16)-(38,21) 에 들어섬) → 06:D704 → 04:FB1C
  talk23a   선실 パパス 대화 번호를 23A(06/00 의 マスタードラゴン 대화)로 → 06:B4F7 → 01:BA95
  overflow  같은 장면에 시작 때 7E:1983 = 1E 를 두어, 01:BA95 가 슬롯 20·21 을 쓰게 함
  alt0605   06/05 대체 목록 10:AB3A(7E:2190 bit7)의 10:ABB5 스크립트 → 05:E931 → 01:BA95. 기다리는 7E:21A1 bit6 을 켜 둠
  map1100   11/00 기본 목록 05:A3D2 스크립트(7E:219F bit7 을 기다림) → 05:E72A → 05:E838·05:E7EC → 04:FB1C 두 번.
            05:E72A 는 인물 01·02 가 일행에 살아 있을 때만 슬롯을 만들므로, 도착 뒤 일행 레코드 1·2 에
            인물 레코드 표(23:C014)의 01·02 를 베낌

장면마다 부르는 곳을 지날 때의 $1983·Y(슬롯), 메시지 번호, 끝의 $1995(OBJ VRAM 다음 타일)를 적는다(lua/dq5slotuse.lua).
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
INN_LIST = '10:B7BA'
PERSONS = 0x23C014          # 인물 레코드 표, 42바이트씩(일행 레코드 7E:2040 + i×42 와 같은 꼴)


def party_sets(rom):
    """일행을 주인공·인물 01·인물 02 셋으로 두고 11/00 장면을 거는 LATESET."""
    data = rom.read_bytes()
    at = (PERSONS >> 16 & 0x7F) * 0x8000 + (PERSONS & 0x7FFF)
    sets = [f'{0x2040 + i * 42 + k:04X}={b:02X}' for i in (1, 2) for k, b in enumerate(data[at + i * 42:at + i * 42 + 42])]
    return ';'.join(sets + ['201D=03', '201E=03', '201F=03', '2020=00', '2021=01', '2022=02', '219F|98'])


# 슬롯을 더 쓰는 루틴과 스크립트가 부르는 그 앞 루틴. 롬 전체에서 부르는 바이트 꼴을 찾아 아래와 같아야 한다.
CALLERS = {
    0x04FB1C: {('JSL', '02:AE7B'), ('JSL', '02:AFB8'), ('JSL', '02:AFE5'), ('JSL', '02:B0F3'), ('JSL', '05:E806'),
               ('JSL', '05:E852'), ('JSL', '06:D716')},
    0x01BA95: {('JSL', '05:E931'), ('JSL', '06:B52D')},
    0x05E931: {('스크립트 37', '10:ABD1')},
    0x05E72A: {('스크립트 37', '05:A3E5')},
}


def callers(data, target):
    """target 을 부르는 곳. 긴 호출(JSL·JML, 인물 스크립트 05·37, 이벤트 스크립트 A0)은 롬 전체,
    같은 뱅크 호출(JSR·JMP·JSR (a,X)·JMP (a,X), 뱅크 06 이면 대화 스크립트 00)은 그 뱅크에서 찾는다."""
    def name(o):
        return f'{o // 0x8000:02X}:{0x8000 | o % 0x8000:04X}'
    long = {0x22: 'JSL', 0x5C: 'JML', 0x05: '스크립트 05', 0x37: '스크립트 37', 0xA0: '이벤트 A0'}
    near = {0x20: 'JSR', 0x4C: 'JMP', 0xFC: 'JSR', 0x7C: 'JMP'} | ({0x00: '대화 00'} if target >> 16 == 6 else {})
    out = {(long[data[m.start() - 1]], name(m.start() - 1))
           for m in re.finditer(re.escape(bytes([target & 0xFF, target >> 8 & 0xFF, target >> 16])), data)
           if m.start() and data[m.start() - 1] in long}
    base = (target >> 16 & 0x7F) * 0x8000
    for m in re.finditer(re.escape(bytes([target & 0xFF, target >> 8 & 0xFF])), data[base:base + 0x8000]):
        if m.start() and data[base + m.start() - 1] in near:
            out.add((near[data[base + m.start() - 1]], name(base + m.start() - 1)))
    return out


def scenes(rom):
    map1100 = dict(ALT0605, TO='11/00,100,67', LATESET=party_sets(rom))
    del map1100['SET']
    return {'inn': ('original', INN), 'inn-grown': ('grown', INN), 'ev3': ('original', EV3),
            'talk23a': ('original', T23A), 'overflow': ('original', dict(T23A, SET='1983=1E')),
            'alt0605': ('original', ALT0605), 'map1100': ('original', map1100)}


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
    calls = [(m[1], int(m[2], 16), int(m[3], 16), int(m[4], 16)) for m in
             re.finditer(r'pc (\w{6}) map \S+ 1982=\w\w 1983=(\w\w) 1995=(\w{4}) X=\w\w Y=(\w\w)', text)]
    end = re.search(r'end f\d+ map (\S+) 1982=(\w\w) 1983=(\w\w) 1995=(\w{4})', text)
    return {'calls': calls, 'messages': re.findall(r'msg (\w{3})', text), 'map': end[1],
            'placed': int(end[2], 16), 'free': int(end[3], 16), 'obj_tiles': int(end[4], 16)}


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
        }
        results = {n: {**v, 'calls': [(pc, f'{f:02X}', f'{t:04X}', f'{y:02X}') for pc, f, t, y in v['calls']]}
                   for n, v in seen.items()}
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
