"""BG3 타일맵 옮기기(dq4bg3slot.py)를 MesenCE 로 검사한다. 배 선실 세이브스테이트에서 실내 맵마다 순간이동해
명령 창을 연 화면을 원래 롬과 견주고, 새 롬의 BG3SC 그림자 $0725 와 그 자리 타일맵이 채워졌는지 본다.

  MESENCE=... uv run --locked python sfc/dq4/tools/dq4bg3slotcheck.py --old 원래롬 --new 새롬 \\
      --state work/state/ship.mss --out 새폴더 [--maps 01/00,17/00] [--jobs 8]

맵 목록은 DQ5 트랙 dq5hangul.py slots(실내 맵 364개), 도착 칸은 (10,10) 이다(DQ5 트랙 실측과 같은 방법).
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'sfc' / 'dq5' / 'tools')]

import dq4mesen as mesen  # noqa: E402

TEST = 'wait:90,a:4,wait:90'


def interior_maps():
    import dq5hangul
    return [f'{bc:02X}/{bd:02X}' for bc, bd, _ in dq5hangul.slot_table((ROOT / 'rom' / 'dq5.sfc').read_bytes())]


def last_bg3(folder):
    p = folder / 'bg3.txt'
    lines = p.read_text().split('\n') if p.exists() else []
    lines = [x for x in lines if x]
    return lines[-1] if lines else ''


def arrived(folder):
    p = folder / 'warp.txt'
    return p.exists() and 'arrived' in p.read_text()


def run(mesence, libdir, rom, state, target, folder):
    folder.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, LIBDIR=libdir, SHOT_DIR=str(folder), STATE=str(state), TO=f'{target},10,10',
               SETTLE='60', TEST=TEST, MAXF='2400', WARPLUA=str(ROOT / 'sfc/dq5/tools/lua/dq5warp.lua'))
    return mesen.Runner(mesence, rom, HERE / 'lua/dq4bg3slotwarp.lua', folder, tag='bg3',
                        extra=('--Snes.RamPowerOnState=AllZeros',), env=env, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--old', type=Path, required=True)
    ap.add_argument('--new', type=Path, required=True)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--maps')
    ap.add_argument('--jobs', type=int, default=8)
    a = ap.parse_args()
    mesence = os.environ.get('MESENCE')
    if not mesence:
        ap.error('MESENCE 에 MesenCE 실행 파일을 주세요')
    out = a.out.resolve()
    if out.exists():
        ap.error('--out 은 아직 없는 폴더를 주세요')
    libdir = os.environ.get('LIBDIR') or subprocess.check_output(
        ['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], text=True).strip()
    maps = a.maps.split(',') if a.maps else interior_maps()
    jobs = []
    for mp in maps:
        for kind, rom in (('old', a.old), ('new', a.new)):
            jobs.append((mp, kind, rom))
    running = []
    for mp, kind, rom in jobs:
        running.append(run(mesence, libdir, rom.resolve(), a.state.resolve(), mp, out / mp.replace('/', '-') / kind))
        if len(running) >= a.jobs:
            running.pop(0).wait()
    for p in running:
        p.wait()
    from PIL import Image, ImageChops
    rows, bad = [], 0
    for mp in maps:
        d = out / mp.replace('/', '-')
        ok = arrived(d / 'old') and arrived(d / 'new')
        same = None
        if ok and (d / 'old/end.png').exists() and (d / 'new/end.png').exists():
            with Image.open(d / 'old/end.png') as x, Image.open(d / 'new/end.png') as y:
                same = ImageChops.difference(x.convert('RGB'), y.convert('RGB')).getbbox() is None
        state = last_bg3(d / 'new')
        if ok and not same:
            bad += 1
        rows.append(f'{mp} {"도착" if ok else "못감"} {"같음" if same else "다름" if same is False else "-"} {state}')
    (out / 'report.txt').write_text('\n'.join(rows) + '\n')
    print('\n'.join(rows))
    print(f'{len(maps)}맵, 도착해서 화면이 다른 맵 {bad}')


if __name__ == '__main__':
    main()
