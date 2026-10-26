"""DQ5(SFC) 장면을 여러 개 돌려 MesenCE CDL(코드·자료 표시)을 모은다. 결과는 dq5-hangul-format.md 「옮긴 레코드를 둘 자리」.

장면 목록은 dq5freesweep.py 와 같다(실내 맵 346곳에 들어가 걷기, 몬스터 236종과 싸우기, 세계 0·1·2 걷기).
effects 는 행동 00~AA 마다 dq5effectgif.py 처럼 슬라임 셋 이벤트 전투에서 파파스(< 39)나 슬라임이 그 행동을 쓰게 한다.
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

    def run(job):
        kind, name, env = job
        d = os.path.abspath(os.path.join(a.out, kind, name))
        os.makedirs(d, exist_ok=True)
        e = dict(os.environ, LIBDIR=krlua, STATE=os.path.abspath(a.state), SHOT_DIR=d)
        e.update(env)
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
    return 0


if __name__ == '__main__':
    sys.exit(main())
