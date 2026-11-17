"""2장 일행(아리나·크리프트·브라이)의 OBJ 팔레트 줄 7·6·5 가 2장 일행이 들르는 맵마다 실제 CGRAM 에 실리는지 본다.

2장 출발 상태(dq4ch2walkcheck 의 머리, 산트하임 3D/01)에서 맵마다 순간이동(dq5warp.lua)하고 30프레임 뒤
CGRAM·OAM·WRAM 을 덤프한다(lua/dq4peopledump.lua). 기대 색은 롬의 맵 팔레트 루틴(01:996A)을 2장 flag 를 켜고
산트하임 성 3D/00 으로 돌린 줄 5~7 이다. 맵마다 CGRAM 의 줄 5~7 이 그 색과 같고, 화면 안 OAM 에 줄 7(선두 아리나)을
쓰는 것이 있어야 통과한다. 줄을 덮는 맵 목록(dq4people.flag_maps)에서 그룹이 빠지면 그 맵에 1장 일행 색이 남는다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4ch2partypalcheck.py --rom work/ch2/dq4-ch1-full.sfc --out work/ch2partypal
"""
import argparse
import concurrent.futures
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch2endor as endor  # noqa: E402
import dq4ch2walkcheck as cw  # noqa: E402
import dq4mesen  # noqa: E402
import dq4peoplecheck as pc  # noqa: E402
import dq5objpalette  # noqa: E402
from dq4ch2event import CHAPTER2  # noqa: E402
from dq5exitcheck import warp_exit  # noqa: E402
from w65816 import Cpu  # noqa: E402

wc = cw.wc
PARTY_LINES = (5, 6, 7)
LEADER_LINE = 7
# 2장 일행이 서는 그룹(3D·40·45)마다 맵과 칸. 출발 상태의 맵(3D/01)은 순간이동 없이 그대로 덤프한다
SPOTS = {
    '3D/03': pc.EVENT_MAPS['3D/03'], '3D/04': pc.EVENT_MAPS['3D/04'], '45/09': pc.EVENT_MAPS['45/09'],
    endor.TOWN: pc.EVENT_MAPS['40/00'], endor.ARENA: (28, 26), endor.BEDROOM: endor.BED_CELL,
}
START_MAP = '3D/01'


def expected_lines(data):
    """2장 flag 를 켜고 산트하임 성 3D/00 으로 맵 팔레트 루틴을 돌린 OBJ 줄 5~7(CGRAM 바이트)."""
    c = Cpu(data, bytearray(0x20000))
    c.wram[0xBC], c.wram[0xBD], c.wram[0xBE] = 0x3D, 0x00, 0x80
    c.wram[0x2190 + CHAPTER2[0]] |= CHAPTER2[1]
    c.dbr = 0x01
    c.jsr(dq5objpalette.MAP_LOADER)
    w = bytes(c.wram[0x3914:0x3D14])
    return {n: w[(8 + n) * 32 + 2:(8 + n) * 32 + 32] for n in PARTY_LINES}


def obj_lines(cgram):
    return {n: cgram[0x100 + n * 32 + 2:0x100 + n * 32 + 32] for n in PARTY_LINES}


def oam_lines(oam):
    """화면 안(y < 224) OAM 이 쓰는 팔레트 줄."""
    return {oam[i * 4 + 3] >> 1 & 7 for i in range(128) if oam[i * 4 + 1] < 224}


def judge(want, cgram, oam):
    got = obj_lines(cgram)
    problems = [f'줄 {n} 색이 다름({got[n][:6].hex()}… 기대 {want[n][:6].hex()}…)' for n in PARTY_LINES
                if got[n] != want[n]]
    if LEADER_LINE not in oam_lines(oam):
        problems.append(f'화면 안 OAM 에 줄 {LEADER_LINE} 이 없음')
    return problems


def dump(mesence, rom, state, dest):
    env = dict(os.environ, STATE=str(state), OUT=str(dest), WAIT='30', POKE='')
    dq4mesen.run(mesence, rom, pc.DUMP, folder=dest, tag='partypal', env=env, timeout=120, capture_output=True)


def scene(mesence, rom, base, out, m, want):
    dest = out / m.replace('/', '')
    dest.mkdir(parents=True, exist_ok=True)
    state = base
    if m != START_MAP:
        x, y = SPOTS[m]
        env = {'STATE': str(base), 'TO': f'{m},{x},{y}', 'SAVE': 'end.mss', 'SETTLE': '120', 'MAXF': '1500',
               'WARPEXIT': f'{warp_exit(rom):X}', 'ANYWHERE': '1'}
        wc.run(mesence, rom, wc.WARP, dest, env, 300)
        state = dest / 'end.mss'
        if not state.exists():
            return {'map': m, 'ok': False, 'problems': ['워프 실패']}
    dump(mesence, rom, state.resolve(), dest.resolve())
    if not (dest / 'wram.bin').exists():
        return {'map': m, 'ok': False, 'problems': ['덤프 없음']}
    wram = (dest / 'wram.bin').read_bytes()
    found = f'{wram[0xBC]:02X}/{wram[0xBD]:02X}'
    problems = ([] if found == m else [f'맵 {found}']) + \
        judge(want, (dest / 'cgram.bin').read_bytes(), (dest / 'oam.bin').read_bytes())
    return {'map': m, 'ok': not problems, 'problems': problems}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help='dq4build.py --chapter2 의 롬')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=4, help='함께 띄울 MesenCE 수')
    ap.add_argument('--no-state-cache', action='store_true', help='2장 출발 상태 캐시를 쓰지 않음')
    args = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    want = expected_lines(data)
    if not all(any(v) for v in want.values()):
        raise SystemExit('롬이 3D/00 에서 2장 일행 줄을 덮지 않음')
    base, head = cw.head(mesence, rom, data, out, None if args.no_state_cache else wc.StateCache(data))
    if base is None:
        print(json.dumps({'status': 'failed', 'head': head}, ensure_ascii=False))
        return 1
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(lambda m: scene(mesence, rom, base.resolve(), out, m, want),
                                [START_MAP, *SPOTS]))
    for r in results:
        print(json.dumps(r, ensure_ascii=False), flush=True)
    failed = [r['map'] for r in results if not r['ok']]
    print(json.dumps({'status': 'failed' if failed else 'passed', 'maps': len(results), 'failed': failed},
                     ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
