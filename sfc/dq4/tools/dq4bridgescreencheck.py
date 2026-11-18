"""본몰 앞 다리 화면을 기준(sfc/dq4/screens.toml)과 칸 해시로 견준다(MesenCE 헤드리스). 형식은
sfc/dq4/docs/dq4-screen-baseline-format.md, 다리는 sfc/dq4/docs/dq4-chapter3-bonmalmo-format.md 「다리」.

3장 걷기 검사(dq4ch3walkcheck)의 묶음 bm_castle_gate·bm_castle_gate2 를 돌려 두 상태를 얻고, 그 끝에서 정한 입력만 넣어
정한 프레임의 화면을 찍는다. 물이 움직이는 칸도 같은 상태·같은 프레임이라 늘 같다.
  bridge-broken  고치기 전: 다리 서쪽 칸에서 오른쪽으로 걸어도 막혀 선 자리(끊긴 석교: 아래층 물, 위층 석교 조각)
  bridge-mended  고친 뒤: 다리를 건너 동쪽 섬에 선 자리에서 서쪽으로 되건넌 자리(석교)

  uv run --locked python sfc/dq4/tools/dq4bridgescreencheck.py --rom work/ch3/dq4-ch1-full.sfc --out work/bridgescreen
  … --write-screens "까닭"     지금 화면으로 기준을 고친다
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dq4screencheck as screen  # noqa: E402
import dq4screens as sc  # noqa: E402

# (장면, 걷기 묶음, 끝 상태를 남기는 구간, 입력, 찍을 프레임)
SCENES = (
    ('bridge-broken', 'bm_castle_gate', 'bm_bridge_shut', 'b:4,wait:30,right:20,wait:40', 80),
    ('bridge-mended', 'bm_castle_gate2', 'bm_bridge_open', 'b:4,wait:10,left:16,wait:20,left:16,wait:20', 94),
)


def states(rom, out):
    """{구간: 끝 상태}. 걷기 검사가 3장 출발 상태(캐시)에서 묶음을 돌린다."""
    walk = out / 'walk'
    only = ','.join(unit for _, unit, _, _, _ in SCENES)
    subprocess.run([sys.executable, str(HERE / 'dq4ch3walkcheck.py'), '--rom', str(rom), '--out', str(walk),
                    '--only', only, '--jobs', '2'], check=True, stdout=subprocess.DEVNULL)
    found = {}
    for _, _, seg, _, _ in SCENES:
        path = walk / seg / 'end.mss'
        if not path.exists():
            raise SystemExit(f'{seg}: 끝 상태가 없음({walk})')
        found[seg] = path
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help='dq4build.py --chapter3 의 롬')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--write-screens', metavar='까닭', help='지금 화면으로 기준을 고친다')
    args = ap.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    mesence = os.environ['MESENCE']
    found = states(args.rom.resolve(), out)
    rows, results = [], {}
    for scene, _, seg, pre, frame in SCENES:
        img = screen.mesen_screen(mesence, args.rom.resolve(), out / scene, found[seg], pre, frame)
        rows.append((scene, 'mesence', img, (), 0))
        if not args.write_screens:
            results[scene] = sc.check_screen(img, scene, 'mesence', out)
    if args.write_screens:
        sc.write_baselines(rows, args.write_screens)
        print(json.dumps({'status': 'written', 'scenes': [r[0] for r in rows]}, ensure_ascii=False))
        return 0
    ok = all(r['status'] == 'passed' for r in results.values())
    print(json.dumps({'status': 'passed' if ok else 'failed',
                      'scenes': {k: {kk: v for kk, v in r.items() if kk != 'tiles'} for k, r in results.items()}},
                     ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
