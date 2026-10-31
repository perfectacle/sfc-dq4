"""인물 그림을 얹은 1장 롬에서 서장·1장 맵마다 일행·인물의 OBJ 가 제 세트로 실렸는지 VRAM 으로 본다.

걷기 검사(dq4ch1walkcheck.py)가 남긴 세이브스테이트 셋에서 맵마다 그 맵의 칸으로 워프하고(dq5warp.lua), 몇 프레임
뒤 VRAM·OAM·CGRAM·WRAM 을 덤프한다(lua/dq4peopledump.lua).

  day     castle_day 끝(낮, 일행은 주인공 하나)
  night   castle_day 끝에서 7E:075E 를 F0 으로 붙들어 밤 인물로(imuru_night 끝은 빠른 상태 창이 열려 있어 워프가 막힘)
  hoimin  shoes_chest 끝(호이민이 일행에 있음. 맵에 들어간 뒤 일행 그림을 다시 싣는 03:D1C3 이 돈다)

인물 슬롯(7E:3220)마다 세트는 덤프한 WRAM($BC 맵 그룹, 7E:2190 flag)을 넣고 롬의 인물 훅(dq4people.HOOK_AT)을
65816 해석기로 그대로 돌려 얻는다. 그 세트 레코드로 칸 목록(7E:8060-)의 타일·좌우 반전이 레코드와 같은지, 칸의
팔레트 비트가 세트의 OBJ 팔레트와 같은지, 세트 타일이 VRAM 에 그대로 있는지 본다. 일행 슬롯은 칸 목록이 어긋나도
실패이고, 인물 슬롯은 칸 목록이 레코드와 다르면 쓰지 않는 슬롯(앞 맵의 목록이 남음)으로 보고 건너뛴다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4peoplecheck.py --rom work/ch1/dq4-ch1-full.sfc --states work/ch1walk \\
      --out work/peoplecheck [--jobs 4] [--maps 36/00 3B/03] [--scenes hoimin]
"""
import argparse
import concurrent.futures
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
sys.path[:0] = [str(HERE), str(DQ5_TOOLS)]

import dq4ch1walkcheck as walk  # noqa: E402
import dq4mesen  # noqa: E402
import dq4people  # noqa: E402
import dq5sprite as S  # noqa: E402
from dq5exitcheck import warp_exit  # noqa: E402
from dq5map import Rom  # noqa: E402
from w65816 import Cpu  # noqa: E402

DUMP = HERE / 'lua' / 'dq4peopledump.lua'
# 서장·1장 그룹(36~3C)의 맵과 걸어 설 수 있는 칸(dq4groupcheck 의 도착 칸)
MAPS = {
    '36/00': (36, 23), '36/01': (30, 70), '36/03': (6, 4), '37/00': (26, 51), '37/01': (12, 13), '37/02': (12, 7),
    '38/00': (26, 33), '38/01': (12, 7), '39/00': (18, 7), '39/01': (30, 29), '39/02': (50, 9), '39/03': (32, 67),
    '39/04': (10, 37), '39/05': (16, 31), '3A/00': (6, 7), '3B/00': (30, 99), '3B/02': (6, 5), '3B/03': (10, 81),
    '3B/05': (10, 5), '3B/06': (54, 5), '3C/00': (20, 45), '3C/01': (2, 2),
}
SCENES = {'day': ('castle_day', walk.DAY), 'night': ('castle_day', walk.NIGHT), 'hoimin': ('shoes_chest', '')}
# 시작 상태가 선 맵. 같은 맵으로의 워프는 dq5warp.lua 가 도착을 알아보지 못하므로 HOP 을 거친다
STATE_MAP = {'castle_day': '36/00', 'shoes_chest': '3B/03'}
HOP = '37/02'
PARTY_SLOTS = 3                                     # 7E:3220 슬롯 0~2 가 일행(00:E3BD)


def hook_set(rom, wram, picture):
    """롬의 인물 훅을 덤프한 WRAM 으로 돌려 그림 → 세트."""
    cpu = Cpu(rom, bytearray(wram))
    cpu.x, cpu.p = picture, 0x30
    cpu.jsl(dq4people.cpu(dq4people.HOOK_AT))
    return cpu.a & 0xFF


def judge(rom, wram, vram):
    """슬롯마다 {'slot', 'picture', 'set', 'base', 'tiles', 'cells', 'palette', 'ok'}. 쓰지 않는 인물 슬롯은 뺀다."""
    r = Rom(rom)
    table = S.set_palette_table(r)
    w16 = lambda a: wram[a] | wram[a + 1] << 8  # noqa: E731
    party = {s for s in range(PARTY_SLOTS) if wram[0x196F + s] != 0}
    out = []
    for slot in range(0x20):
        g = wram[0x3220 + slot]
        # 32A0 이 0 인 슬롯은 놓이지 않은 인물(그림 칸에 앞 맵 값이 남음)
        if g in (0xFE, 0xFF) or (slot < PARTY_SLOTS and slot not in party and slot) or not wram[0x32A0 + slot]:
            continue
        s = hook_set(rom, wram, g)
        rec = S.decode_set(r, s)
        if rec is None:
            if slot in party or slot == 0:
                out.append({'slot': slot, 'picture': g, 'set': s, 'ok': False, 'note': '세트 레코드 없음'})
            continue
        lst = w16(0x8000 + wram[0x3200 + slot])
        cells = [w16(lst + i * 2) for i in range(48)]
        lying = bool(wram[0x31C0 + slot] & 1)
        if lying:
            want = [(t, hf) for t, hf, _ in rec['lying_cells']]
            tiles = rec['lying_tiles']
        else:
            want = [(c & 0x7F, bool(c & 0x80)) for c in rec['cells']]
            tiles = rec['tile_data']
        base = (cells[0] & 0x1FF) - want[0][0]
        cell_ok = sum(1 for c, (t, hf) in zip(cells, want) if (c & 0x1FF) == base + t and bool(c & 0x4000) == hf)
        if cell_ok < 48 and slot not in party and slot != 0:
            continue
        pal = S.set_obj_palette(r, s, table)
        pal_ok = sum(1 for c in cells if (c >> 9) & 7 == pal)
        vt = sum(1 for i, t in enumerate(tiles) if 0 <= base + i < 0x200 and
                 bytes(vram[0xC000 + (base + i) * 32:0xC000 + (base + i) * 32 + 32]) == t)
        ok = cell_ok == 48 and vt == len(tiles) and (pal_ok == 48 or s in (0x63, 0x6C))
        out.append({'slot': slot, 'picture': g, 'set': s, 'base': base, 'tiles': f'{vt}/{len(tiles)}',
                    'cells': f'{cell_ok}/48', 'palette': f'{pal_ok}/48 ({pal})', 'ok': ok})
    return out


def scene(mesence, rom, states, out, name, m):
    seg, poke = SCENES[name]
    dest = out / f'{name}-{m.replace("/", "")}'
    dest.mkdir(parents=True, exist_ok=True)
    state = (states / seg / 'end.mss').resolve()

    def warp(to, where, save):
        x, y = MAPS[to]
        env = {'STATE': str(state), 'TO': f'{to},{x},{y}', 'SAVE': save, 'SETTLE': '120', 'MAXF': '1500',
               'WARPEXIT': f'{warp_exit(rom):X}', 'ANYWHERE': '1', **({'POKE': poke} if poke else {})}
        walk.run(mesence, rom, walk.WARP, where, env, 300)
    if STATE_MAP[seg] == m:
        hop = dest / 'hop'
        hop.mkdir(exist_ok=True)
        warp(HOP, hop, 'hop.mss')
        state = (hop / 'hop.mss').resolve()
    warp(m, dest, 'end.mss')
    if not (dest / 'end.mss').exists():
        return {'scene': dest.name, 'ok': False, 'note': '워프 실패'}
    env = dict(os.environ, STATE=str((dest / 'end.mss').resolve()), OUT=str(dest.resolve()), WAIT='30',
               POKE=poke)
    dq4mesen.run(mesence, rom, DUMP, folder=dest, tag='people', env=env, timeout=120, capture_output=True)
    if not (dest / 'wram.bin').exists():
        return {'scene': dest.name, 'ok': False, 'note': '덤프 없음'}
    wram, vram = (dest / 'wram.bin').read_bytes(), (dest / 'vram.bin').read_bytes()
    found = f'{wram[0xBC]:02X}/{wram[0xBD]:02X}'
    slots = judge(rom.read_bytes(), wram, vram)
    return {'scene': dest.name, 'map': found, 'ok': found == m and all(s['ok'] for s in slots), 'slots': slots}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--states', required=True, type=Path, help='dq4ch1walkcheck.py 의 출력 폴더')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--maps', nargs='+', default=list(MAPS))
    ap.add_argument('--scenes', nargs='+', default=list(SCENES), choices=list(SCENES))
    args = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rom = args.rom.resolve()
    jobs = [(n, m) for n in args.scenes for m in args.maps]
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(lambda j: scene(mesence, rom, args.states, out, *j), jobs))
    for r in results:
        bad = [s for s in r.get('slots', []) if not s['ok']]
        print(f"{r['scene']:14s} {'ok' if r['ok'] else 'FAIL'} {r.get('map', '')} {r.get('note', '')}"
              + ''.join(f"\n    슬롯 {s['slot']:02X} 그림 {s['picture']:02X} 세트 {s['set']:02X} "
                        f"타일 {s.get('tiles')} 칸 {s.get('cells')} 팔레트 {s.get('palette')} {s.get('note', '')}"
                        for s in bad))
    ok = all(r['ok'] for r in results)
    report = {'status': 'passed' if ok else 'failed', 'scenes': results}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'status': report['status'], 'scenes': len(results),
                      'failed': [r['scene'] for r in results if not r['ok']]}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
