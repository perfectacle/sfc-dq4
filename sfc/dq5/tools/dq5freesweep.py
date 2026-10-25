"""DQ5(SFC) 빈 자리 지도(dq5build.py free) 22곳을 여러 장면에서 롬 읽기·실행 감시한다. 결과는 dq5-build-format.md 「빈 자리 지도」.

선실 세이브스테이트에서 dq5warp.lua 로 장면을 옮기며 lua/dq5freewatch.lua 를 얹는다.
  maps     실내 맵 346곳(들어갈 칸은 dq5mapmusic.entry_cells)에 들어가 상하좌우로 걷기
  battles  몬스터 236종마다 첫 필드 이벤트 전투(BATTLE=XX:1)를 붙여 A 를 눌러 싸우기
  field    필드 세계 0·1·2 에서 걷기
결과는 OUT/<종류>/<이름>/free.txt 와 OUT/summary.txt(읽힌 곳만). MESENCE 가 있어야 한다.

  python sfc/dq5/tools/dq5freesweep.py rom/dq5.sfc work/state/ship.mss work/freesweep --kinds maps,battles,field
"""
import argparse
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dq5build import cpu, free_ranges  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5mapmusic import entry_cells  # noqa: E402
from dq5sound import map_songs  # noqa: E402

PROBE = os.path.join(HERE, 'lua', 'dq5freewatch.lua')
WALK = 'left:30,right:30,up:30,down:30,wait:30'
FIGHT = ','.join(['a:8,wait:40'] * 12)


def jobs(rom_path, rom, kinds, njobs):
    out = []
    if 'maps' in kinds:
        maps = [f'{bc:02X}/{bd:02X}' for bc, bd, _ in map_songs(rom)]
        for m, c in sorted(entry_cells(rom_path, maps, njobs).items()):
            out.append(('maps', m.replace('/', '_'), {'TO': f'{m},{",".join(str(v) for v in c)}', 'SETTLE': '60',
                                                       'TEST': WALK, 'MAXF': '900'}))
    if 'battles' in kinds:
        for k in range(236):
            out.append(('battles', f'{k:02X}', {'FIELD': '341,56', 'BATTLE': f'{k:02X}:1', 'TEST': FIGHT, 'MAXF': '1300'}))
    if 'field' in kinds:
        for w, (x, y) in enumerate(((174, 110), (174, 110), (174, 110))):
            out.append(('field', f'world{w}', {'FIELD': f'{x},{y}', 'POKE': f'7E1949={w:02X}',
                                               'TEST': 'left:90,up:90,right:90,down:90', 'MAXF': '1100'}))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('state')
    ap.add_argument('out')
    ap.add_argument('--kinds', default='maps,battles,field')
    ap.add_argument('--jobs', type=int, default=8)
    a = ap.parse_args()
    rom = Rom(open(a.rom, 'rb').read())
    free = ','.join(f'{cpu(o).replace(":", "")}-{cpu(o + n - 1).replace(":", "")}' for o, n in free_ranges(rom.d))
    krlua = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True).stdout.strip()
    lib = os.path.abspath(os.path.join(a.out, 'warplib'))
    os.makedirs(lib, exist_ok=True)
    for name in ('lib.lua', 'probe'):
        if not os.path.lexists(os.path.join(lib, name)):
            os.symlink(os.path.join(krlua, name), os.path.join(lib, name))
    shutil.copyfile(os.path.join(HERE, 'lua', 'dq5warp.lua'), os.path.join(lib, 'boot.lua'))
    mesen = os.environ['MESENCE']
    todo = jobs(a.rom, rom, a.kinds.split(','), a.jobs)

    def run(job):
        kind, name, env = job
        d = os.path.abspath(os.path.join(a.out, kind, name))
        os.makedirs(d, exist_ok=True)
        e = dict(os.environ, LIBDIR=lib, STATE=os.path.abspath(a.state), SHOT_DIR=d, FREE=free, **env)
        subprocess.run([mesen, '--testrunner', os.path.abspath(a.rom), PROBE], env=e,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        path = os.path.join(d, 'free.txt')
        lines = open(path).read().split('\n') if os.path.exists(path) else []
        frames = next((ln for ln in lines if ln.startswith('frames=')), 'frames=?')
        return kind, name, frames, [ln for ln in lines if ln and not ln.startswith('frames=')]
    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(run, todo))
    summary = [f'{k} {n} {fr} {h}' for k, n, fr, hits in res for h in hits]
    missing = [f'{k} {n}' for k, n, fr, _ in res if fr == 'frames=?']
    with open(os.path.join(a.out, 'summary.txt'), 'w') as f:
        f.write('\n'.join(summary) + '\n')
    for kind in sorted({k for k, _, _, _ in res}):
        rs = [r for r in res if r[0] == kind]
        print(f'{kind}: {len(rs)}개, 읽힌 것 {sum(len(r[3]) for r in rs)}줄, 기록 없음 {sum(r[2] == "frames=?" for r in rs)}개')
    if missing:
        print('기록 없음:', ' '.join(missing[:20]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
