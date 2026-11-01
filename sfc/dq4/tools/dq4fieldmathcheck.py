"""1장 롬의 필드에서 OBJ 색 연산이 꺼져 장 주인공이 불투명하게 그려지는지 본다.

DQ5 는 필드 맵을 불러올 때(2B:82E5) OBJ 반 더하기($2131 = 50)를 켠다. SNES 색 연산은 OBJ 팔레트 4~7 에만 걸리고,
인물 그림 단계(dq4people.py)는 장 주인공·동료를 5~7 에 두므로, 이것이 켜져 있으면 필드에서 주인공이 BG 와 반씩
섞인다(dq4people.hook_patch 가 끈다). 서장 성 마을 출발 상태(dq4heroblockcheck.make_base, 상태 캐시)에서 FC 필드
0 의 이무르 근처 칸으로 워프해(dq5warp.lua FIELD), 120프레임 서 있은 끝 프레임의 PPU 색 연산 층과 화면 가운데 OAM
팔레트를 lua/dq4fieldmath.lua 로 읽는다. 필드($BE bit7 = 0)이고, 가운데 OBJ 가 팔레트 4~7 이고, OBJ 색 연산
비트가 꺼져 있어야 통과다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4fieldmathcheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/fieldmath
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4fieldencountercheck as fe  # noqa: E402
import dq4fieldport  # noqa: E402
import dq4heroblockcheck  # noqa: E402
from dq5exitcheck import warp_exit  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

PROBE = HERE / 'lua' / 'dq4fieldmath.lua'
ZONE = (0x09, 0x01)          # 필드 0 의 이무르 근처 조우 구역 칸(사용자 제보 자리)
OBJ_MATH = 0x10
CENTER = range(96, 160)      # 주인공이 서는 화면 가운데(x·y)


def judge(text):
    """math.txt → (통과, 이유)."""
    lines = text.split('\n')
    head = lines[0].split()
    layers, be = int(head[1]), int(head[2][3:], 16)
    centre = [tuple(map(int, line.split()[1:])) for line in lines[1:] if line.startswith('oam ')]
    centre = [(i, x, y, pal) for i, x, y, pal in centre if x in CENTER and y in CENTER]
    if be & 0x80:
        return False, f'필드가 아님($BE={be:02X})'
    if not any(pal >= 4 for *_, pal in centre):
        return False, f'화면 가운데에 팔레트 4~7 OBJ 가 없음({centre})'
    if layers & OBJ_MATH:
        return False, f'OBJ 색 연산이 켜져 있음(층 비트 {layers:02X}): 팔레트 4~7 주인공이 BG 와 섞임'
    return True, f'OBJ 색 연산 꺼짐(층 비트 {layers:02X}), 가운데 OBJ {len(centre)}장 팔레트 {sorted({p for *_, p in centre})}'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--dq4', default='rom/dq4.nes', type=Path)
    ap.add_argument('--no-state-cache', action='store_true', help='출발 상태 캐시(work/cache/states)를 쓰지 않음')
    args = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    cache = None if args.no_state_cache else wc.StateCache(data)
    base, _ = dq4heroblockcheck.make_base(mesence, rom, out, cache)
    grid, props = dq4fieldport.fc_field(ines.prg(args.dq4.read_bytes()), 0)
    x, y = dq4fieldport.stand(*fe.stand(grid, props, ZONE))
    dest = out / 'field'
    wc.run(mesence, rom, PROBE, dest, {
        'STATE': str(base), 'FIELD': f'{x},{y}', 'SETTLE': '120', 'MAXF': '1500', 'WARPEXIT': f'{warp_exit(rom):X}',
        'ROMPATCH': f'{dq4fieldport.warp_patch(data, x, y)};{wc.NO_ENCOUNTERS}', 'SET': f'{wc.RNG};{wc.DAY_SET}'}, 300)
    math = dest / 'math.txt'
    ok, why = judge(math.read_text(encoding='utf-8')) if math.exists() else (False, '끝 기록(math.txt)이 없음')
    report = {'status': 'passed' if ok else 'failed', 'field': [x, y], 'why': why}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
