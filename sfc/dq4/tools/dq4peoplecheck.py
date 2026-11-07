"""인물 그림을 얹은 1장 롬에서 서장·1장 맵마다 일행·인물의 OBJ 가 제 세트로 실렸는지 VRAM 으로 본다.

걷기 검사(dq4ch1walkcheck.py)가 남긴 세이브스테이트 셋에서 맵마다 그 맵의 칸으로 워프하고(dq5warp.lua), 몇 프레임
뒤 VRAM·OAM·CGRAM·WRAM 을 덤프한다(lua/dq4peopledump.lua).

  day     castle_day 끝(낮, 일행은 주인공 하나)
  night   castle_day 끝에서 7E:075E 를 F0 으로 붙들어 밤 인물로(imuru_night 끝은 빠른 상태 창이 열려 있어 워프가 막힘)
  hoimin  shoes_chest 끝(호이민이 일행에 있음. 맵에 들어간 뒤 일행 그림을 다시 싣는 03:D1C3 이 돈다)
  event   castle_day 끝에서 2장 사건 인물(dq4people.EVENT_PEOPLE)이 나올 그룹의 맵으로. 사건이 아직 인물을 놓지 않으므로
          그 맵 인물 목록의 앞 엔트리 그림을 사건 그림으로 바꾼 시험 롬(--out 아래 event.sfc)을 쓴다. 사건 그림마다 판정을
          지난 슬롯이 하나 이상이어야 한다

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
import dq5npcrecord  # noqa: E402
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
SCENES = {'day': ('castle_day', walk.DAY), 'night': ('castle_day', walk.NIGHT), 'hoimin': ('shoes_chest', ''),
          'event': ('castle_day', walk.DAY)}
# 사건 인물이 나올 그룹마다 들어설 맵과 칸(필드에서 들어설 때의 칸 dq4groupbuild.LINKS 의 arrival 은 맵 가장자리라 그대로
# 워프하면 바로 필드로 나가므로 몇 칸 안쪽). 한 맵에 큰 세트를 다 넣으면 OBJ VRAM(512타일)을 넘어 그룹 3D 는 두 맵에 나눈다
EVENT_MAPS = {'3D/03': (20, 89), '3D/04': (44, 7), '40/00': (46, 59), '45/09': (42, 57)}
# 시작 상태가 선 맵. 같은 맵으로의 워프는 dq5warp.lua 가 도착을 알아보지 못하므로 HOP 을 거친다
STATE_MAP = {'castle_day': '36/00', 'shoes_chest': '3B/03'}
HOP = '37/02'
PARTY_SLOTS = 3                                     # 7E:3220 슬롯 0~2 가 일행(00:E3BD)


# 사건 그림을 놓을 칸: 워프 칸에서의 (가로, 세로) 차이. 화면(16×14칸) 안이고 나무·지붕 밑(OBJ 우선순위 0)이 아닌 칸.
# 프레놀 3D/04 는 워프 칸 양옆이 나무라 위쪽 길에 둔다
EVENT_SPOTS = ((-4, -2), (-2, -2), (2, -2), (4, -2), (0, -3))
EVENT_SPOTS_AT = {'3D/04': ((0, -2), (0, -4))}


def event_rom(data):
    """(시험 롬, {맵: [사건 그림]}). 사건 그림을 그 그룹의 EVENT_MAPS 맵에 차례로 나눠, 맵마다 인물 목록의 앞
    엔트리(낮에 나오는 것)에 하나씩 넣고 그 엔트리를 워프 칸 둘레(EVENT_SPOTS)로 옮긴다. 원래 칸은 화면 밖일 수 있어
    VRAM 에 실려도 그려지지 않는다. 낮·밤 두 벌 엔트리는 두 벌 모두 바꾼다."""
    rom = Rom(data)
    out = bytearray(data)
    by_map = {m: [] for m in EVENT_MAPS}
    for k, (_, pic, _, group, _) in enumerate(dq4people.EVENT_PEOPLE):
        maps = [m for m in EVENT_MAPS if int(m[:2], 16) == group]
        by_map[maps[sum(1 for e in dq4people.EVENT_PEOPLE[:k] if e[3] == group) % len(maps)]].append(pic)
    entries = dq5npcrecord.dump(rom)['entries']
    for m, pictures in by_map.items():
        rows = [e for e in entries if e['name'] == m and e['time'] in ('day', 'both')]
        if len(rows) < len(pictures):
            raise SystemExit(f'{m}: 사건 그림 {len(pictures)}개를 넣을 낮 엔트리가 {len(rows)}개뿐')
        spots = EVENT_SPOTS_AT.get(m, EVENT_SPOTS)
        if len(pictures) > len(spots):
            raise SystemExit(f'{m}: 사건 그림 {len(pictures)}개를 놓을 칸이 {len(spots)}개뿐')
        wx, wy = EVENT_MAPS[m]
        for e, pic, (dx, dy) in zip(rows, pictures, spots):
            at = dq5npcrecord.lorom(int(e['address'].replace(':', ''), 16))
            size = dq5npcrecord.entry_size(rom, int(e['address'].replace(':', ''), 16))
            where = dq5npcrecord.offsets(bytes(data[at:at + size]))
            for part in (('day', 'night') if e['time'] == 'both' else ('day',)):
                w = where[part]
                out[at + w['gfx']] = pic
                # x·y 의 bit7 은 방향. y 는 misc bit7 만큼 위로 읽힌다(dq5npcrecord.decode)
                out[at + w['x']] = out[at + w['x']] & 0x80 | (wx + dx) & 0x7F
                out[at + w['y']] = out[at + w['y']] & 0x80 | (wy + dy + (out[at + w['misc']] >> 7)) & 0x7F
    return bytes(out), by_map


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
        pal = S.set_obj_palette(r, s, table)
        pal_ok = sum(1 for c in cells if (c >> 9) & 7 == pal)
        vt = sum(1 for i, t in enumerate(tiles) if 0 <= base + i < 0x200 and
                 bytes(vram[0xC000 + (base + i) * 32:0xC000 + (base + i) * 32 + 32]) == t)
        ok = cell_ok == 48 and vt == len(tiles) and (pal_ok == 48 or s in (0x63, 0x6C))
        out.append({'slot': slot, 'picture': g, 'set': s, 'base': base, 'tiles': f'{vt}/{len(tiles)}',
                    'cells': f'{cell_ok}/48', 'palette': f'{pal_ok}/48 ({pal})', 'ok': ok})
    return out


def shown(oam, base, count):
    """OAM 128개 가운데 타일이 [base, base + count) 이고 화면(세로 224줄, 가로 -16~255) 안에 놓이고 우선순위가 2 이상인
    것의 수. 맵은 나무·지붕 밑 칸의 인물을 우선순위 0 으로 두어 BG 뒤로 가리므로, 그것은 보이지 않는 것으로 센다."""
    n = 0
    for i in range(128):
        x, y, tile, attr = oam[i * 4:i * 4 + 4]
        x |= (oam[512 + i // 4] >> (i % 4 * 2) & 1) << 8
        if x >= 256:
            x -= 512
        if base <= (tile | (attr & 1) << 8) < base + count and y < 224 and -16 < x < 256 and attr >> 4 & 3 >= 2:
            n += 1
    return n


def scene_ok(found, want, slots):
    """맵이 맞고 판정한 슬롯이 하나 이상이며 모두 통과. 슬롯이 비면 덤프가 인물을 놓기 전이라 실패로 친다."""
    return found == want and bool(slots) and all(s['ok'] for s in slots)


def scene(mesence, rom, states, out, name, m):
    seg, poke = SCENES[name]
    dest = out / f'{name}-{m.replace("/", "")}'
    dest.mkdir(parents=True, exist_ok=True)
    state = (states / seg / 'end.mss').resolve()

    def warp(to, where, save):
        x, y = {**MAPS, **EVENT_MAPS}[to]
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
    oam = (dest / 'oam.bin').read_bytes()
    for sl in slots:
        if 'base' in sl:
            sl['shown'] = shown(oam, sl['base'], int(sl['tiles'].split('/')[1]))
    return {'scene': dest.name, 'map': found, 'ok': scene_ok(found, m, slots), 'slots': slots,
            **({} if slots else {'note': '판정할 슬롯 없음'})}


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
    jobs = [(rom, n, m) for n in args.scenes if n != 'event' for m in args.maps]
    wanted = {}
    if 'event' in args.scenes:
        data, wanted = event_rom(rom.read_bytes())
        test = out / 'event.sfc'
        test.write_bytes(data)
        jobs += [(test, 'event', m) for m in EVENT_MAPS]
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(lambda j: scene(mesence, j[0], args.states, out, *j[1:]), jobs))
    for r in results:
        if r['scene'].startswith('event-') and r['ok']:
            m = r['map']
            missing = [g for g in wanted[m] if not any(s['picture'] == g and s['ok'] for s in r['slots'])]
            hidden = [g for g in wanted[m] if not any(s['picture'] == g and s['ok'] and s.get('shown') for s in r['slots'])]
            if missing:
                r['ok'], r['note'] = False, '판정을 지난 슬롯이 없는 사건 그림 ' + ' '.join(f'{g:02X}' for g in missing)
            elif hidden:
                r['ok'], r['note'] = False, '화면 OAM 에 없는 사건 그림 ' + ' '.join(f'{g:02X}' for g in hidden)
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
