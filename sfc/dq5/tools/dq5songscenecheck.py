"""장면을 못 찾았던 곡(1C·24·2A·2B·2C·2D·2E)과 15 의 즉위식·엔딩을 MesenCE 에서 띄워 곡 번호를 확인한다.

모든 장면을 lua/dq5songtrace.lua 로 돌려 곡 틀기 24:FE9A, 곡 BRK 0F·11 의 자리, 25:FD00(짧은 곡)을 JSL 한 곳, 보행 메시지
24:8157 을 모은다. 대화 장면은 드라이버를 dq5msg.lua(배 선실 パパス 에게 말 걸기)로, 순간이동 장면은 dq5warp.lua 로 둔다.
기대한 곡이 나오고, 그 앞에 나와야 할 메시지가 차례대로 나오고, 뒤에 나와야 할 메시지가 그 뒤에 나오는지 본다.
부른 곳은 24:FE9A 를 JSL 한 곳이고, 그곳이 BRK 처리기(00:92A2·92AB)면 같은 프레임의 곡 BRK 자리, 25:FD07 이면 같은
프레임에 25:FD00 을 JSL 한 곳으로 바꿔 적는다.
  join-1B3 / join-170 / join-24D  대화 스크립트 012 를 네이티브 06:F646·B4B1·B45C(대화 1B3·170·24D 가 부름) 부르기 하나로
           바꾼 롬. 메시지 5D9「…が 仲間に くわわった！」(B45C 는 42B·42C 뒤) 뒤 1C
  bride-1F6 / bride-1FF  パパス 의 대화 번호를 1F6(ビアンカ)·1FF(フローラ)로. はい 뒤 24
  horn-ship / horn-5051  주인공 물건 셋째 칸을 ようせいのホルン(CE)으로 두고 불기. 배 선실은 2B, 50/51 (30,50) 은 2C
  flute    22/00 에 들어선 뒤 7E:21A6 bit6 을 켬(flag 를 켜 들어섬). ベラ 의 메시지 269 뒤 2A
  queen    08/00 의 대체 목록(7E:219A bit7)으로 들어선 뒤 7E:219F bit7 을 켬. 2D 뒤 女王 의 메시지 268
  stone    10/02 (18,73) 에서 아래로 한 걸음. 메시지 2F1「なにやら でっぱった石がある。」 에 はい 뒤 2E
  crown    02/06 의 대체 목록(7E:21A8 bit3)으로 들어선 뒤 7E:21A1 bit7 을 켜고, オジロン 의 3D7·3D8 뒤 (38,9) 로 걸어감
  ending   02/06 의 엔딩 목록(7E:2190 bit7)으로 들어선 뒤 7E:219F bit6 을 켬
원본 롬·선실 상태는 읽기만 하고 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5songscenecheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import os
import re
import shutil
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
CALLS = {'join-1B3': 'F646', 'join-170': 'B4B1', 'join-24D': 'B45C'}
BRK_HANDLERS = ('00:92A2', '00:92AB')
SHORT_INNER = '25:FD07'


def talk(number):
    return {'PRE': TALK, 'MAXF': '1300', 'POKE': f'7E36EB={number & 0xFF:02X};7E370B={number >> 8:02X}'}


# 이름: (롬, 대화 장면인지, 환경, 기대 곡, 앞에 차례대로 나올 메시지, 뒤에 나올 메시지)
SCENES = {
    'join-1B3': ('join-1B3', True, {'PRE': TALK, 'MAXF': '1300'}, '1C', ['05D9'], []),
    'join-170': ('join-170', True, {'PRE': TALK, 'MAXF': '1300'}, '1C', ['05D9'], []),
    'join-24D': ('join-24D', True, {'PRE': TALK, 'MAXF': '1700'}, '1C', ['042B', '042C'], []),
    'bride-1F6': ('original', True, talk(0x1F6), '24', ['097E', '0980'], []),
    'bride-1FF': ('original', True, talk(0x1FF), '24', ['0981', '0983', '0984'], []),
    'horn-ship': ('original', True, {'PRE': ITEM, 'MAXF': '900', 'SET': '2058=CE'}, '2B', ['01C7'], ['01A8']),
    'horn-5051': ('original', False, {'TO': '50/51,30,50', 'SET': '2058=CE', 'MAXF': '2400',
                                      'TEST': 'wait:60,' + ITEM}, '2C', ['01C7'], []),
    'flute': ('original', False, {'TO': '22/00,37,13', 'LATESET': '21A6|40', 'MAXF': '2400', 'TEST': PRESS},
              '2A', ['0269'], []),
    'queen': ('original', False, {'TO': '08/00,29,28', 'SET': '219A|80', 'LATESET': '219F|80', 'MAXF': '1800',
                                  'TEST': PRESS}, '2D', [], ['0268']),
    'stone': ('original', False, {'TO': '10/02,18,73', 'MAXF': '2000',
                                  'TEST': 'down:20,wait:120' + ',a:4,wait:150' * 4}, '2E', ['02F1'], []),
    'crown': ('original', False, {'TO': '02/06,38,9', 'SET': '21A8|08', 'LATESET': '21A1|80', 'MAXF': '3400',
                                  'TEST': CROWN}, '15', ['03D7', '03D8'], []),
    'ending': ('original', False, {'TO': '02/06,38,11', 'SET': '2190|80', 'LATESET': '219F|40', 'MAXF': '1500',
                                   'TEST': PRESS}, '15', [], []),
}
LINE = re.compile(r'^(\d+) (play|short|brk|msg) (.*)$')


def build(original, out):
    """대화 스크립트 012 를 네이티브 부르기 하나로 바꾼 롬."""
    roms = {'original': original}
    for name, target in CALLS.items():
        save_json(out / f'{name}.json', {'format': 'dq5talk/1', 'scripts': [
            {'talk': '012', 'body': [{'op': 'call', 'target': target}]}]})
        command('dq5talkwrite.py', original, 'patch', out / f'{name}.json', '-o', out / f'{name}.patch.json')
        roms[name] = out / f'{name}.sfc'
        command('dq5build.py', original, 'build', out / f'{name}.patch.json', '-o', roms[name])
    return roms


def libraries(out):
    """dq5songtrace.lua 는 TO·FIELD 가 없으면 LIBDIR 의 boot.lua 를 드라이버로 돈다. 대화 장면은 boot.lua 를 dq5msg.lua 로."""
    krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip())
    talk_lib = out / 'talklib'
    shutil.copytree(krlua, talk_lib)
    shutil.copyfile(HERE / 'lua/dq5msg.lua', talk_lib / 'boot.lua')
    return {True: talk_lib, False: krlua}


def scene(name, roms, state, out, mesence, libs):
    rom, is_talk, options, _, _, _ = SCENES[name]
    dest = out / name
    env = environment(libs[is_talk], state, dest)
    env.update(options)
    run(mesence, roms[rom], HERE / 'lua/dq5songtrace.lua', dest, env)
    events = []
    for line in (dest / 'songtrace.txt').read_text().splitlines():
        found = LINE.match(line)
        if found:
            events.append((int(found[1]), found[2], found[3].split()))
    return events


def caller(events, frame, song, at):
    """24:FE9A 를 부른 곳을 BRK 자리나 25:FD00 을 JSL 한 곳으로 바꾼다."""
    if at in BRK_HANDLERS:
        return next((f'{e[2][0]} BRK {e[2][1]}' for e in events
                     if e[0] == frame and e[1] == 'brk' and e[2][2] == song), at)
    if at == SHORT_INNER:
        return next((f'{e[2][2]} JSL 25:FD00' for e in events
                     if e[0] == frame and e[1] == 'short' and e[2][0] == song), at)
    return f'{at} JSL 24:FE9A'


def judge(name, events):
    _, _, _, song, before, after = SCENES[name]
    plays = [(e[0], e[2][2]) for e in events if e[1] == 'play' and e[2][0] == song]
    require(plays, f'{name}: 곡 {song} 이 나오지 않음')
    frame, at = plays[0]
    said = [(e[0], e[2][0]) for e in events if e[1] == 'msg']
    seen = []
    for f, m in said:
        if f <= frame and len(seen) < len(before) and m == before[len(seen)]:
            seen.append(m)
    require(seen == before, f'{name}: 곡 앞 메시지 {before} 가 차례대로 없음 {said}')
    later = [m for f, m in said if f >= frame]
    require(all(m in later for m in after), f'{name}: 곡 뒤 메시지 {after} 가 없음 {said}')
    return {'곡': song, '프레임': frame, '부른 곳': caller(events, frame, song, at),
            '앞 메시지': before, '뒤 메시지': after,
            '곡 순서': [e[2][0] for e in events if e[1] == 'play']}


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
        roms = build(original, out)
        libs = libraries(out)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            got = dict(zip(SCENES, pool.map(lambda n: scene(n, roms, state, out, mesence, libs), SCENES)))
        results = {name: judge(name, events) for name, events in got.items()}
        save_json(out / 'results.json', results)
        for name, r in results.items():
            shown = ' '.join(r['앞 메시지']) or '-'
            print(f'{name}: 곡 {r["곡"]} {r["프레임"]}프레임 {r["부른 곳"]}, 앞 메시지 {shown}'
                  + (f', 뒤 메시지 {" ".join(r["뒤 메시지"])}' if r['뒤 메시지'] else '')
                  + f', 곡 순서 {" ".join(r["곡 순서"])}')
        print(f'{len(SCENES)}장면 곡 확인 통과')
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
