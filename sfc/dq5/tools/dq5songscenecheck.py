"""장면을 못 찾았던 곡(1C·24·2A·2B·2C·2D·2E)과 15 의 즉위식·엔딩을 MesenCE 에서 띄워 곡 번호를 확인한다.

장면마다 곡 틀기 24:FE9A 에 들어온 곡 번호를 모아(대화 장면은 dq5msg.lua 의 CALLS, 순간이동 장면은 lua/dq5songtrace.lua),
기대한 곡이 기대한 메시지 뒤에 나오는지 본다.
  join     배 선실 パパス 의 대화 스크립트 012 를 네이티브 06:F646(대화 1B3 이 부름) 한 번으로 바꾼 롬. 메시지 5D9
           「…が 仲間に くわわった！」 뒤 1C
  bride    パパス 의 대화 번호를 1F6(ビアンカ 를 고름)으로. はい 뒤 24, 그다음 맵 곡 06
  horn     주인공 물건 셋째 칸을 ようせいのホルン(CE)으로 두고 필드에서 불기. 배 선실은 2B, 50/51 (30,50) 은 2C
  flute    22/00 에 들어서 7E:21A6 bit6 을 켬. ベラ 의 메시지 269「ポワンは はるかぜのフルートを…」 뒤 2A
  queen    08/00 의 대체 목록(7E:219A bit7)으로 들어서 7E:219F bit7 을 켬. 女王 의 메시지 268 앞에 2D
  stone    10/02 (18,73) 에서 아래로 한 걸음. 메시지 2F1「なにやら でっぱった石がある。」 에 はい 뒤 2E
  crown    02/06 의 대체 목록(7E:21A8 bit3)으로 들어서 7E:21A1 bit7 을 켜고, オジロン 의 3D8「その王座に すわるがよい」
           뒤 (38,9) 로 걸어감. 25:FED1 의 BRK 0F 15
  ending   02/06 의 엔딩 목록(7E:2190 bit7)으로 들어서 7E:219F bit6 을 켬. 02:F6FF 의 15
원본 롬·선실 상태는 읽기만 하고 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5songscenecheck.py rom/dq5.sfc --state work/state/ship.mss
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
TALK = 'b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4,wait:150' + ',a:4,wait:100' * 8
ITEM = ('b:4,wait:40,a:4,wait:30,down:4,wait:10,right:4,wait:10,a:4,wait:40,a:4,wait:40,a:4,wait:60,a:4,wait:60,'
        'a:4,wait:100,a:4,wait:200')
CROWN = ('wait:200' + ',a:4,wait:120' * 12 + ',b:4,wait:40,b:4,wait:40,right:56,up:24,wait:300'
         + ',a:4,wait:120' * 4)
PRESS = 'wait:200' + ',a:4,wait:150' * 6
# 이름: (롬, lua, 환경, 기대 곡, 그 곡 앞에 나와야 할 메시지)
SCENES = {
    'join': ('join', 'dq5msg.lua', {'PRE': TALK, 'MAXF': '1300', 'CALLS': '24FE9A,248157'}, '1C', '05D9'),
    'bride': ('original', 'dq5msg.lua', {'PRE': TALK, 'MAXF': '1300', 'CALLS': '24FE9A,248157',
                                         'POKE': '7E36EB=F6;7E370B=01'}, '24', '0980'),
    'horn-ship': ('original', 'dq5msg.lua', {'PRE': ITEM, 'MAXF': '900', 'CALLS': '24FE9A,248157',
                                             'SET': '2058=CE'}, '2B', '01C7'),
    'horn-5051': ('original', 'lua/dq5songtrace.lua', {'TO': '50/51,30,50', 'SET': '2058=CE', 'MAXF': '2400',
                                                       'TEST': 'wait:60,' + ITEM}, '2C', None),
    'flute': ('original', 'lua/dq5songtrace.lua', {'TO': '22/00,37,13', 'LATESET': '21A6|40', 'MAXF': '2400',
                                                   'TEST': PRESS}, '2A', None),
    'queen': ('original', 'lua/dq5songtrace.lua', {'TO': '08/00,29,28', 'SET': '219A|80', 'LATESET': '219F|80',
                                                   'MAXF': '1800', 'TEST': PRESS}, '2D', None),
    'stone': ('original', 'lua/dq5songtrace.lua', {'TO': '10/02,18,73', 'MAXF': '2000',
                                                   'TEST': 'down:20,wait:120' + ',a:4,wait:150' * 4}, '2E', None),
    'crown': ('original', 'lua/dq5songtrace.lua', {'TO': '02/06,38,9', 'SET': '21A8|08', 'LATESET': '21A1|80',
                                                   'MAXF': '3400', 'TEST': CROWN}, '15', None),
    'ending': ('original', 'lua/dq5songtrace.lua', {'TO': '02/06,38,11', 'SET': '2190|80', 'LATESET': '219F|40',
                                                    'MAXF': '1500', 'TEST': PRESS}, '15', None),
}
# 대화 장면의 메시지 번호와 곡 번호 기록: dq5msg.lua 의 msg.txt 꼴 「프레임 PC A=…」.
CALL = re.compile(r'^(\d+) (24FE9A|248157) A=([0-9A-F]{4})')
PLAY = re.compile(r'^(\d+) play ([0-9A-F]{2}) from ([0-9A-F]{2}:[0-9A-F]{4})')


def build(original, out):
    """대화 스크립트 012 를 06:F646 부르기 하나로 바꾼 롬."""
    save_json(out / 'join.json', {'format': 'dq5talk/1', 'scripts': [
        {'talk': '012', 'body': [{'op': 'call', 'target': 'F646'}]}]})
    command('dq5talkwrite.py', original, 'patch', out / 'join.json', '-o', out / 'join.patch.json')
    command('dq5build.py', original, 'build', out / 'join.patch.json', '-o', out / 'join.sfc')


def scene(name, roms, state, out, mesence, libdir):
    rom, lua, options, _, _ = SCENES[name]
    dest = out / name
    env = environment(libdir, state, dest)
    env.update(options)
    run(mesence, roms[rom], HERE / ('lua' if '/' not in lua else '') / lua, dest, env)
    if lua == 'dq5msg.lua':
        events = []
        for line in (dest / 'msg.txt').read_text().splitlines():
            found = CALL.match(line)
            if found:
                kind = 'play' if found[2] == '24FE9A' else 'msg'
                events.append((int(found[1]), kind, found[3][-2:] if kind == 'play' else found[3]))
        return events
    events = []
    for line in (dest / 'songtrace.txt').read_text().splitlines():
        found = PLAY.match(line)
        if found:
            events.append((int(found[1]), 'play', found[2], found[3]))
    return events


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/songscenecheck')
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
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        build(original, out)
        roms = {'original': original, 'join': out / 'join.sfc'}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            got = dict(zip(SCENES, pool.map(lambda n: scene(n, roms, state, out, mesence, libdir), SCENES)))
        results = {}
        for name, (_, _, _, song, after) in SCENES.items():
            events = got[name]
            plays = [e for e in events if e[1] == 'play' and e[2] == song]
            require(plays, f'{name}: 곡 {song} 이 나오지 않음 {events}')
            if after is not None:
                said = [e[0] for e in events if e[1] == 'msg' and e[2] == after]
                require(said and said[0] < plays[0][0], f'{name}: 메시지 {after} 뒤에 {song} 이 아님 {events}')
            results[name] = {'곡': song, '프레임': plays[0][0], '부른 곳': plays[0][3] if len(plays[0]) > 3 else None,
                             '곡 순서': [e[2] for e in events if e[1] == 'play']}
        save_json(out / 'results.json', results)
        print(f'{len(SCENES)}장면 곡 확인 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
