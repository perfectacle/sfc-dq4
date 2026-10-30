"""DQ5(SFC) 장면을 여러 개 돌려 MesenCE CDL(코드·자료 표시)을 모은다. 결과는 dq5-hangul-format.md 「옮긴 레코드를 둘 자리」.

장면 목록은 dq5freesweep.py 와 같다(실내 맵 346곳에 들어가 걷기, 몬스터 236종과 싸우기, 세계 0·1·2 걷기).
effects 는 행동 00~AA 마다 dq5effectgif.py 처럼 슬라임 셋 이벤트 전투에서 파파스(< 39)나 슬라임이 그 행동을 쓰게 한다.
extra 는 여관에서 묵기, 교회에서 기록한 뒤 리셋해 불러오기, 배에 걸어 오르기, 융단·天空城·드래곤으로 날기, 슬롯 셋(맞음 판정을
덮은 것 포함), 슬라임 레이스, 격투장이다. --acc 1ABC-1BB0 이면 실행마다 그 WRAM 범위의 주소별 읽기·쓰기 횟수(acc.txt)를 모아 찍는다.
saves 는 --saves 로 준 세이브스테이트(이야기 진행 세이브 등)마다 tools/lua/walk.lua 로 네 방향을 걷고, 명령 창 여덟 칸을 하나씩
골라 A 를 세 번, B 를 네 번 누른다.
sound 는 시퀀스 00~46 마다 dq5spcfile.py 처럼 대기열에 1A·94 n·01 n 을 넣어 곡 자료를 SPC 로 보낸다(lua/dq5spcdump.lua).
실행마다 lua/dq5cdldump.lua 가 남긴 cdl.bin 을 바이트 OR 로 합쳐 OUT/cdl.bin 에 쓴다. MesenCE 가 디스크에 두는 CDL 은
함께 돈 실행끼리 덮어쓰므로 실행마다 따로 받아 합친다. --base 로 앞서 모은 cdl.bin 들을 더한다.

  python sfc/dq5/tools/dq5cdlsweep.py rom/dq5.sfc work/state/ship.mss work/cdlsweep --kinds maps,battles,field
  python sfc/dq5/tools/dq5wramrefs.py rom/dq5.sfc --cdl work/cdlsweep/cdl.bin --align
"""
import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dq5freesweep import jobs  # noqa: E402
from dq5map import Rom  # noqa: E402

PROBE = os.path.join(HERE, 'lua', 'dq5cdldump.lua')


def merge(paths, size):
    out = bytearray(size)
    for p in paths:
        if os.path.exists(p):
            d = open(p, 'rb').read()
            for i in range(min(size, len(d))):
                out[i] |= d[i]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('state')
    ap.add_argument('out')
    ap.add_argument('--kinds', default='maps,battles,field')
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--base', nargs='*', default=[], help='함께 합칠 cdl.bin')
    ap.add_argument('--saves', nargs='*', default=[], help='saves 종류에서 돌릴 세이브스테이트')
    ap.add_argument('--acc', help='WRAM 오프셋 범위(예 1ABC-1BB0). 실행마다 그 범위의 주소별 읽기·쓰기 횟수를 모음')
    a = ap.parse_args()
    data = open(a.rom, 'rb').read()
    krlua = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True).stdout.strip()
    mesen = os.environ['MESENCE']
    kinds = a.kinds.split(',')
    todo = jobs(a.rom, Rom(data), kinds, a.jobs)
    if 'sound' in kinds:
        for n in range(0x47):
            todo.append(('sound', f'{n:02X}', {'NEXT': os.path.join(HERE, 'lua', 'dq5spcdump.lua'), 'CDLEVERY': '20',
                                                'CMDS': f'10:1A:00:00;14:94:{n:02X}:00;200:01:{n:02X}:00',
                                                'WAITSONG': f'{n:02X}', 'FULLSET': f'{n:02X}', 'MAXF': '900'}))

    if 'saves' in kinds:
        walk = os.path.join(HERE, '..', '..', '..', 'tools', 'lua', 'walk.lua')
        # 필드는 8프레임에 한 번 입력을 읽으므로(00:8185) 8프레임씩 누른다
        presses = ['left:40,right:80,left:40,up:40,down:80,up:40,b:8,wait:60,b:8,wait:60']
        for r in range(4):
            for c in range(2):
                presses.append('a:8,wait:40,' + 'down:8,wait:20,' * r + 'right:8,wait:20,' * c
                               + 'a:8,wait:60,' * 3 + ','.join(['b:8,wait:30'] * 4))
        for save in a.saves:
            for k, pre in enumerate(presses):
                todo.append(('saves', f'{os.path.splitext(os.path.basename(save))[0]}-{k}',
                             {'NEXT': walk, 'STATE_OVERRIDE': os.path.abspath(save), 'PRE': pre, 'MAXF': '900', 'CDLEVERY': '20'}))

    if 'effects' in kinds:
        import tempfile
        import dq5effectgif as fx
        lib = fx.driver_dir(os.path.join(tempfile.mkdtemp(prefix='dq5cdl-'), 'lib'))
        for n in range(0xAB):
            papas = n < 0x39
            todo.append(('effects', f'{n:02X}', {
                'NEXT': os.path.join(HERE, 'lua', 'dq5battle.lua'), 'LIBDIR': lib, 'PRE': fx.PRE, 'WAYPOINTS': fx.WAYPOINTS,
                'ROMPATCH': f'{fx.BASE_PATCH};{fx.PAPAS_ACTIONS if papas else fx.SLIME_ACTIONS:06X}={f"{n:02X}" * 6}',
                'MAXF': '2400' if papas else '1500'}))

    if 'extra' in kinds:
        msg = os.path.join(HERE, 'lua', 'dq5msg.lua')
        talk = 'b:4,wait:40,up:3,wait:20,' + ','.join(['a:4,wait:60'] * 40)
        ship = os.path.abspath(a.state)
        for name, env in (
                ('inn', {'NEXT': msg, 'POKE': '7E36EB=06;7E370B=00', 'PRE': talk, 'MAXF': '3000'}),
                ('church-save-load', {'NEXT': msg, 'POKE': '7E36EB=05;7E370B=00', 'PRE': talk + ',wait:300,'
                                      + ','.join(['start:4,wait:200'] * 3 + ['a:4,wait:120'] * 12), 'RESETAT': '2700',
                                      'MAXF': '6500'}),
                ('slime-race', {'NEXT': msg, 'SET': '36EB=0D;370B=00', 'POKE': '7E203C=64', 'ROMPATCH': '37210=80',
                                'PRE': talk + ',' + ','.join(['a:4,wait:60'] * 20), 'MAXF': '4000'}),
                ('arena', {'NEXT': msg, 'SET': '36EB=0E;370B=00', 'POKE': '7E203C=64', 'ROMPATCH': '37210=80',
                           'PRE': talk + ',' + ','.join(['a:4,wait:60'] * 20), 'MAXF': '4000'}),
                ('ship-board', {'FIELD': '328,39', 'SET': '21B5|80;21CD=48;21CE=01;21CF=25;21D0=00',
                                'TEST': 'up:60,wait:60,left:200,up:200,right:200', 'MAXF': '1800'}),
                ('carpet', {'FIELD': '328,27', 'LATESET': '1954=80', 'TEST': 'left:200,up:200,right:200,down:200', 'MAXF': '1800'}),
                ('tenkuujou', {'FIELD': '310,60', 'LATESET': '1954=81', 'TEST': 'left:200,up:200,right:200,down:200', 'MAXF': '1800'}),
                ('dragon', {'FIELD': '310,60', 'LATESET': '1954=82', 'TEST': 'left:200,up:200,right:200,down:200', 'MAXF': '1800'})):
            todo.append(('extra', name, env))
        for k in (1, 3, 5):
            spin = ','.join(['up:4,wait:30,a:4,wait:400'] * 7)
            for win in (False, True):
                env = {'NEXT': msg, 'STATE_OVERRIDE': os.path.join(os.path.dirname(ship), f'slot{k}-slotrng.mss'),
                       'PRE': spin, 'MAXF': '3200'}
                if win:
                    env['ROMPATCH'] = '8B39D=EAEA'
                todo.append(('extra', f'slot{k}{"-win" if win else ""}', env))

    def run(job):
        kind, name, env = job
        d = os.path.abspath(os.path.join(a.out, kind, name))
        os.makedirs(d, exist_ok=True)
        e = dict(os.environ, LIBDIR=krlua, STATE=os.path.abspath(a.state), SHOT_DIR=d)
        if a.acc:
            e['ACCRANGE'] = a.acc
        e.update(env)
        if 'STATE_OVERRIDE' in e:
            e['STATE'] = e.pop('STATE_OVERRIDE')
        subprocess.run([mesen, '--testrunner', os.path.abspath(a.rom), PROBE, '--Snes.DisableFrameSkipping=true'], env=e,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        return os.path.join(d, 'cdl.bin')
    with ThreadPoolExecutor(a.jobs) as ex:
        paths = list(ex.map(run, todo))
    got = [p for p in paths if os.path.exists(p)]
    out = merge(got + a.base, len(data))
    with open(os.path.join(a.out, 'cdl.bin'), 'wb') as f:
        f.write(out)
    print(f'실행 {len(todo)}, cdl.bin 을 남긴 실행 {len(got)}, 코드 바이트 {sum(1 for b in out if b & 1):,}, '
          f'자료 바이트 {sum(1 for b in out if b & 2):,}')
    if a.acc:
        hits, missing = {}, []
        for kind, name, _ in todo:
            path = os.path.join(a.out, kind, name, 'acc.txt')
            if not os.path.exists(path):
                missing.append(f'{kind}/{name}')
                continue
            for line in open(path).read().split('\n')[1:]:
                if line:
                    addr, r, w = line.split()
                    hits.setdefault(addr, []).append(f'{kind}/{name} 읽기 {r} 쓰기 {w}')
        print(f'{a.acc} 접근: 주소 {len(hits)}곳, acc.txt 없는 실행 {len(missing)}' + (f' ({" ".join(missing[:10])})' if missing else ''))
        for addr in sorted(hits):
            print(f'  {addr}: ' + '; '.join(hits[addr][:6]) + (f' 외 {len(hits[addr]) - 6}' if len(hits[addr]) > 6 else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
