"""필드 타일 1,024개 늘리기·세계 0 의 2·3번 줄 벌 늘리기·실내 BG 팔레트 세트 늘리기를 MesenCE 에서 확인한다.

시험 롬(원본에서 만듦)
  tiles   타일 512~1023 을 타일 0~511 의 비트 반전으로, 니블을 0~511 니블의 bit0 반전으로 두고(dq5fieldgfxwrite
          --worlds-at 34:8000 --extra-at 35:8000), 그 롬으로 만든 dq5fieldtables 패치로 블록 511개 두 층의 칸 타일
          번호에 512 를 더함(위층 타일 0 은 그대로). 블록에서 그린 필드 칸이 모두 늘린 타일을 써야 맞다
  wall    tiles 와 같되 타일 512~1023 의 속성(00:BCA8 이 읽는 표)을 모두 80 으로. 원래 속성 그대로인 tiles 롬에서는
          걷고, 이 롬에서는 못 걸어야 늘린 속성 표를 읽는 것이다
  fieldpal  세계 0 의 2·3번 줄 벌을 12개로(8~11 은 새 색), 시간대 표를 12항목으로(새 벌을 0·1·0100·0180 에), 밤 인물
          팔레트 시작을 벌 10 으로(dq5fieldgfxwrite --palettes-at 36:8000)
  indoor  실내 BG 팔레트 세트를 70개로(새 세트 69 의 낮 목록은 새 목록, 밤 목록은 세트 0 의 것), 01/01 을 세트 69 로
          (dq5mapgfxwrite --sets-at 37:8000, 그 롬으로 만든 dq5palsetwrite 패치)
장면
  tiles: 01:A4A7 뒤 00:A788 앞에 VRAM 워드 4000~5FFF 를 지우고 다시 오는지(lua/dq5vramwipe.lua), 세계 0 (341,56) 에 서기, 걷고 명령 창을 여닫은 뒤, 이벤트 전투(スライム 하나)를 이기고 돌아온 뒤, 세계 1·2 (50,28).
         VRAM 워드 2000~3FFF·4000~5FFF 의 타일과 BG1·2 타일맵의 채운 칸을 디코더(dq5field)와 견준다
  fieldpal: (341,56) 에서 $075E 를 여섯 값으로 두고 2·3번 줄 색 1~13 과 11·12번 줄(낮·밤 인물 팔레트)
  indoor: 01/01 과 세트를 그대로 둔 맵 셋(원본 게임과도 견줌)에서 BG 1~7번 줄

  MESENCE=… python sfc/dq5/tools/dq5gfxlimitcheck.py rom/dq5.sfc --state work/state/ship.mss --out work/gfxlimitcheck
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dq5fieldgfxcheck as fgc  # noqa: E402
import dq5fieldgfxwrite as fgw  # noqa: E402
import dq5gfxwritecheck as gwc  # noqa: E402
import dq5map  # noqa: E402
from dq5field import tile_word  # noqa: E402
from dq5map import Rom, map_pointer  # noqa: E402

require, command = fgc.require, fgc.command
SETTLE_FRAME = 900
# 이벤트 전투는 dq5fieldgrowcheck 와 같다. 1,000프레임은 전투 중, 1,990프레임은 돌아와 선 뒤.
BATTLE = {'FIELD': '341,56', 'BATTLE': '00:1', 'SETTLE': '300', 'MAXF': '2100', 'DUMPF': '1000,1990',
          'TEST': 'wait:100,' + ','.join(['a:4,wait:30'] * 60) + ',wait:600'}
IN_BATTLE, AFTER_BATTLE = 1000, 1990
# 다시 그리기 시험: 01/00 에서 걸어 나와 01:A4A7(439프레임)이 늘린 타일을 보낸 뒤, 화면 다시 그리기 00:A771 의
# JSL $01B4D5(00:A788, 462프레임) 앞인 450프레임에 VRAM 워드 4000~5FFF 를 지운다. 01:B4D5 훅이 다시 보내면 470프레임에 돌아와 있다.
WIPE = {'FIELD': '341,56', 'SETTLE': '500', 'MAXF': '1000', 'DUMPF': '455,470', 'WIPEF': '450', 'WIPE': '8000-BFFF'}
WIPED, REDRAWN = 455, 470
# 속성 시험: 서서 네 방향으로 32프레임씩 걷는다. dq5warp.lua 가 좌표가 바뀌었는지 warp.txt 에 moved= 로 적는다.
WALL = 0x80
MOVE = {'FIELD': '341,56', 'SETTLE': '300', 'MAXF': '1300', 'TEST': 'wait:60,left:32,up:32,right:32,down:32,wait:60'}
# 명령 창을 열어 고르고 닫은 뒤 몇 걸음 걷는다(01:A4A7·전투 뒤 말고 늘린 타일 자리를 덮는 곳이 없는지).
# 오래 걸으면 무작위 전투가 붙으므로 짧게 걷고, 덤프 때 $1001 = 0(전투 전)을 본다.
WALK = {'FIELD': '341,56', 'SETTLE': '300', 'MAXF': '1600', 'DUMPF': '1450',
        'TEST': 'wait:100,a:4,wait:60,down:4,wait:30,a:4,wait:60,b:4,wait:30,b:4,wait:30,b:4,wait:60,'
                'left:32,up:32,a:4,wait:60,b:4,wait:300'}
WALK_FRAME = 1450
# 늘린 벌 8~11 과 시간대 표. 하한 0·1 은 새 벌 8·9, 0100·0180 은 새 벌 10·11(밤 시작), 나머지는 원래와 같다.
NEW_SETS = 4
TIMES = [[0, 8], [1, 9], [2, 2], [0xEE, 3], [0xEF, 4], [0xF0, 5], [0xF1, 6], [0xF2, 7], [0x100, 10], [0x180, 11],
         [0x1FD, 6], [0x1FE, 5]]
NIGHT_FROM = 10
# $075E 값 → 고르는 벌. 0050 은 원래 벌 2, 00F1 은 원래 밤이지만 이 롬에서는 낮(벌 6 < 10).
TIME_CASES = {0x0000: 8, 0x0001: 9, 0x0050: 2, 0x00F1: 6, 0x0120: 10, 0x01A0: 11}
NEW_MAP = (0x01, 0x01)      # 세트 표에 원래 맵 항목이 있어 표 크기가 그대로다
# 세트를 바꾸지 않은 맵: 옮긴 표에서도 원래 세트·목록을 읽는지(세트 46·6·5).
SAME_MAPS = [(0x01, 0x00), (0x02, 0x00), (0x21, 0x02)]
NEW_SET = 69
INDOOR_FRAME = 700


def make_roms(original, out):
    rom = Rom(original.read_bytes())
    src = out / 'tiles-src'
    doc = fgw.dump(rom, src)
    tiles = (src / 'tiles.bin').read_bytes()
    (src / 'tiles.bin').write_bytes(tiles + bytes(b ^ 0xFF for b in tiles))
    doc['tile_palettes'] = doc['tile_palettes'] + [n ^ 1 for n in doc['tile_palettes']]
    (src / 'fieldgfx.json').write_text(json.dumps(doc), encoding='utf-8')
    command('dq5fieldgfxwrite.py', original, 'patch', src / 'fieldgfx.json', '-o', out / 'tiles-gfx.json',
            '--worlds-at', '34:8000', '--extra-at', '35:8000')
    doc['tile_attributes'] = doc['tile_attributes'] + [WALL] * fgw.TILES
    (src / 'wall.json').write_text(json.dumps(doc), encoding='utf-8')
    command('dq5fieldgfxwrite.py', original, 'patch', src / 'wall.json', '-o', out / 'wall-gfx.json',
            '--worlds-at', '34:8000', '--extra-at', '35:8000')
    command('dq5build.py', original, 'build', out / 'tiles-gfx.json', '--size', '4', '-o', out / 'tiles-step.sfc')
    command('dq5fieldtables.py', out / 'tiles-step.sfc', 'dump', '-o', out / 'tables.json')
    t = json.loads((out / 'tables.json').read_text(encoding='utf-8'))
    # 위층 타일 0 은 00:BCA8 이 「위층 없음」으로 보고 아래층 속성을 읽으므로 0 으로 둔다.
    blocks = [{'index': b['index'], 'lower': [v + 512 for v in b['lower']],
               'upper': [v and v + 512 for v in b['upper']]} for b in t['blocks']]
    (out / 'tables.json').write_text(json.dumps({'format': t['format'], 'blocks': blocks}), encoding='utf-8')
    command('dq5fieldtables.py', out / 'tiles-step.sfc', 'patch', out / 'tables.json', '-o', out / 'tiles-blocks.json')

    psrc = out / 'fieldpal-src'
    doc = fgw.dump(rom, psrc)
    base = doc['palettes']['world0'][0]
    for k in range(NEW_SETS):
        doc['palettes']['world0'].append([0x0421 * (k + 1) + i if i not in fgw.CYCLED else base[i] for i in range(30)])
    doc['world0_times'], doc['world0_night_from'] = TIMES, NIGHT_FROM
    (psrc / 'fieldgfx.json').write_text(json.dumps(doc), encoding='utf-8')
    command('dq5fieldgfxwrite.py', original, 'patch', psrc / 'fieldgfx.json', '-o', out / 'fieldpal.json',
            '--palettes-at', '36:8000')

    isrc = out / 'indoor-src'
    command('dq5mapgfxwrite.py', original, 'dump', '-o', isrc)
    m = json.loads((isrc / 'mapgfx.json').read_text(encoding='utf-8'))
    m['palette_lists']['0000'] = [52, 52, 60, 61, 62, 63, 64]
    m['palette_sets'].append(['0000', m['palette_sets'][0][1]])
    (isrc / 'mapgfx.json').write_text(json.dumps(m), encoding='utf-8')
    command('dq5mapgfxwrite.py', original, 'patch', isrc / 'mapgfx.json', '-o', out / 'indoor-sets.json',
            '--sets-at', '37:8000')
    command('dq5build.py', original, 'build', out / 'indoor-sets.json', '--size', '4', '-o', out / 'indoor-step.sfc')
    command('dq5palsetwrite.py', out / 'indoor-step.sfc', 'dump', '-o', out / 'palset.json')
    p = json.loads((out / 'palset.json').read_text(encoding='utf-8'))
    p['groups'] = [g for g in p['groups'] if g['group'] == f'{NEW_MAP[0]:02X}']
    g = p['groups'][0]
    for x in g['maps']:
        if x['map'] == f'{NEW_MAP[1]:02X}':
            x['set'] = NEW_SET
    (out / 'palset.json').write_text(json.dumps(p), encoding='utf-8')
    command('dq5palsetwrite.py', out / 'indoor-step.sfc', 'patch', out / 'palset.json', '-o', out / 'indoor-map.json')
    for name, lists in (('tiles', ['tiles-gfx.json', 'tiles-blocks.json']),
                        ('wall', ['wall-gfx.json', 'tiles-blocks.json']), ('fieldpal', ['fieldpal.json']),
                        ('indoor', ['indoor-sets.json', 'indoor-map.json'])):
        command('dq5build.py', original, 'build', *(out / x for x in lists), '--size', '4',
                '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')


def frame(dump, n, ext):
    return (dump / f'f{n:05d}.{ext}').read_bytes()


def vram_tiles(vram, n):
    return [vram[0x4000 + t * 32:0x4000 + t * 32 + 32] for t in range(n)]


def field_cells(rom, vram, world):
    """BG1·2 타일맵 칸마다 (층, 워드, 디코더 워드와 같은지). 0·2000 은 원본에서도 채우지 않는 칸이라 뺀다."""
    out = {}
    for base, upper in ((0, False), (0x1000, True)):
        for i in range(0x800):
            v = vram[base + i * 2] | vram[base + i * 2 + 1] << 8
            if v not in (0, 0x2000):
                out[base + i * 2] = (v, v & 0x1FFF == tile_word(rom, v & 0x3FF, upper, world) & 0x1FFF)
    return out


def check_tiles(name, rom_path, dump, n, orig, world=0, grown=True):
    """VRAM 타일이 그 세계 벌과 같고(움직이는 타일 제외), BG1·2 타일맵의 채운 칸이 모두 디코더 워드와 같은지.
    orig 는 같은 장면을 원본 롬으로 돌린 덤프(없으면 None). 시험 롬은 블록 칸 타일에 512 를 더했으므로(위층 0 빼고)
    두 덤프에서 값이 같은 칸은 늘린 타일로 그린 칸이 아니다(위층 0, 전투 뒤 남은 칸 등). 그 칸을 빼고, 남은 칸은 모두 같은 자리
    원본 게임 칸의 타일 + 512 여야 한다(grown). 워드만 보면 타일 번호가 다른 칸으로 바뀌어도 가를 수 없다."""
    rom = Rom(rom_path.read_bytes())
    tiles, _ = fgw.current(rom)['worlds'][f'world{world}']
    w, vram = frame(dump, n, 'wram'), frame(dump, n, 'vram')
    require(w[0x1949] == world and not w[0xBE] & 0x80, f'{name}: 세계 {world} 필드에 서지 않음')
    require(w[0x1001] == 0 or n == AFTER_BATTLE, f'{name}: {n}프레임에 전투가 붙음($1001 = {w[0x1001]:02X})')
    count = len(tiles) // 32
    got = vram_tiles(vram, count)
    bad = [t for t in range(count) if t not in fgc.ANIM_TILES and got[t] != tiles[t * 32:t * 32 + 32]]
    require(not bad, f'{name}: VRAM 타일 {len(bad)}개가 기대와 다름 {bad[:8]}')
    ov = frame(orig, n, 'vram') if orig else None
    cells = field_cells(rom, vram, world)
    stale = {a for a, (v, _) in cells.items() if ov and v == (ov[a] | ov[a + 1] << 8)}
    cells = {a: c for a, c in cells.items() if a not in stale}
    wrong = [a for a, (v, ok) in cells.items()
             if not ok or (ov and grown and v & 0x3FF != (ov[a] | ov[a + 1] << 8 & 0x300) + fgw.TILES)]
    high = sum((v & 0x3FF) >= fgw.TILES for v, _ in cells.values())
    require(cells and not wrong, f'{name}: 채운 칸 {len(cells)}개 가운데 {len(wrong)}개가 디코더 워드와 다름')
    require(high == (len(cells) if grown else 0), f'{name}: 타일 512 이상을 쓰는 칸 {high}/{len(cells)}')
    return {'case': name, 'frame': n, 'world': world, 'vram_tiles': count - len(fgc.ANIM_TILES),
            'tilemap_cells': len(cells), 'cells_using_512_up': high, 'same_as_original_game': len(stale)}


def check_battle(name, rom_path, dump, orig):
    """전투 중에는 VRAM 워드 4000~5FFF 가 늘린 타일과 다르고(전투가 덮음), 돌아온 뒤에는 다시 같은지."""
    rom = Rom(rom_path.read_bytes())
    tiles, _ = fgw.current(rom)['worlds']['world0']
    w = frame(dump, IN_BATTLE, 'wram')
    require(w[0x1001] == 0 and w[0xBE] & 0x80 == 0, f'{name}: {IN_BATTLE}프레임이 첫 전투 전 필드 자리 아님')
    inside = vram_tiles(frame(dump, IN_BATTLE, 'vram'), len(tiles) // 32)[fgw.TILES:]
    over = sum(a != tiles[(fgw.TILES + i) * 32:(fgw.TILES + i + 1) * 32] for i, a in enumerate(inside))
    require(over, f'{name}: 전투 중({IN_BATTLE}프레임)에도 늘린 타일이 그대로라 다시 보내기를 가를 수 없음')
    require(frame(dump, AFTER_BATTLE, 'wram')[0x1001] != 0, f'{name}: {AFTER_BATTLE}프레임에 전투를 마치지 않음')
    out = check_tiles(name, rom_path, dump, AFTER_BATTLE, orig)
    out['in_battle_overwritten'] = over
    return out


def check_redraw(name, rom_path, dump):
    rom = Rom(rom_path.read_bytes())
    extra = fgw.current(rom)['worlds']['world0'][0][fgw.TILES * 32:]
    wiped, back = (frame(dump, n, 'vram')[0x8000:0x8000 + len(extra)] for n in (WIPED, REDRAWN))
    require(wiped == bytes(len(extra)), f'{name}: {WIPED}프레임에 늘린 타일 자리가 지워지지 않음')
    require(back == extra, f'{name}: {REDRAWN}프레임에 늘린 타일이 돌아오지 않음(00:A788 → 01:B4D5 훅)')
    return {'case': name, 'wiped_at': int(WIPE['WIPEF']), 'restored_by': REDRAWN, 'tiles': len(extra) // 32}


def check_move(name, dump, want):
    line = next(x for x in (dump / 'warp.txt').read_text().splitlines() if ' test ' in x)
    require(f'moved={"yes" if want else "no"}' in line, f'{name}: {line}')
    return {'case': name, 'walk': line.split(' test ')[1]}


def rows23(cg):
    return [fgc.cg_color(cg, row, c) for row in (2, 3) for c in range(1, 14)]


def check_fieldpal(name, rom_path, dumps, orig_dumps):
    rom = Rom(rom_path.read_bytes())
    cur = fgw.current(rom)
    out = []
    for t, k in TIME_CASES.items():
        d, od = dumps[t], orig_dumps[t]
        w, cg, ocg = frame(d, SETTLE_FRAME, 'wram'), frame(d, SETTLE_FRAME, 'cgram'), frame(od, SETTLE_FRAME, 'cgram')
        require(w[0x75E] | w[0x75F] << 8 == t and w[0x1949] == 0 and not w[0xBE] & 0x80,
                f'{name} {t:04X}: $075E·필드가 맞지 않음')
        want = cur['palettes']['world0'][k]
        got = rows23(cg)
        require(got == [want[i] for i in range(30) if i % 15 < 13], f'{name} {t:04X}: 2·3번 줄이 벌 {k} 와 다름')
        night = k >= NIGHT_FROM
        person = [fgc.cg_color(cg, row, c) for row in (11, 12) for c in range(1, 16)]
        require(person == cur['person_palettes']['night' if night else 'day'],
                f'{name} {t:04X}: 11·12번 줄이 {"밤" if night else "낮"} 인물 팔레트와 다름')
        out.append({'075E': f'{t:04X}', 'set': k, 'night': night, 'rows_2_3': 26,
                    'differs_from_original': rows23(ocg) != got or (person != [fgc.cg_color(ocg, r, c)
                                                                         for r in (11, 12) for c in range(1, 16)])})
    changed = [o['075E'] for o in out if o['differs_from_original']]
    require(changed == [f'{t:04X}' for t, k in TIME_CASES.items() if k >= 8 or t == 0x00F1],
            f'{name}: 원본 게임과 다른 시간대가 {changed}')
    return {'case': name, 'times': out}


def check_indoor(name, rom_path, dump, orig_dump, bcbd, new):
    """맵에 선 뒤 CGRAM BG 1~7번 줄이 dq5map.map_cgram(옮긴 표를 따라감)과 같은지. new 면 원본 게임과 달라야 하고,
    아니면 원본 게임과 같아야 한다."""
    rom = Rom(rom_path.read_bytes())
    w, cg = frame(dump, INDOOR_FRAME, 'wram'), frame(dump, INDOOR_FRAME, 'cgram')
    require(w[0xBC:0xBE] == bytes(bcbd) and w[0xBE] & 0x80, f'{name}: 맵이 {w[0xBC]:02X}/{w[0xBD]:02X}')
    want = dq5map.map_cgram(rom, *bcbd)
    s = dq5map.palette_set(rom, *bcbd)
    require(cg[0x20:0x100] == want[0x20:0x100], f'{name}: BG 1~7번 줄이 세트 {s} 의 낮 목록과 다름')
    same = cg[0x20:0x100] == frame(orig_dump, INDOOR_FRAME, 'cgram')[0x20:0x100]
    require(same != new, f'{name}: 원본 게임과 {"같음" if same else "다름"}')
    return {'case': name, 'map': f'{bcbd[0]:02X}/{bcbd[1]:02X}', 'set': s, 'rows': 7, 'same_as_original': same}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default=Path('work/gfxlimitcheck'))
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE 가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        make_roms(original, out)
        tiles, wall, fieldpal, indoor = (out / f'{k}.sfc' for k in ('tiles', 'wall', 'fieldpal', 'indoor'))
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True,
                                    timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        gfx = HERE / 'lua/dq5gfxdump.lua'
        stand = {'FIELD': '341,56', 'SETTLE': str(SETTLE_FRAME), 'DUMPF': str(SETTLE_FRAME), 'MAXF': '1100'}
        world = {w: {'FIELD': '50,28', 'POKE': f'7E1949={w:02X}', 'SETTLE': str(SETTLE_FRAME),
                     'DUMPF': str(SETTLE_FRAME), 'MAXF': '1100'} for w in (1, 2)}
        scenes = {'stand': stand, 'walk': WALK, 'battle': BATTLE, 'world1': world[1], 'world2': world[2]}
        cases = [(f'tiles-{k}-{r}', path, env) for k, env in scenes.items()
                 for r, path in (('orig', original), ('grow', tiles))]
        cases += [('move-tiles', tiles, MOVE), ('move-wall', wall, MOVE)]
        luas = {'redraw-tiles': HERE / 'lua/dq5vramwipe.lua'}
        cases.append(('redraw-tiles', tiles, dict(WIPE, NEXT=str(gfx))))
        for t in TIME_CASES:
            env = dict(stand, SET=f'075E={t & 0xFF:02X};075F={t >> 8:02X}')
            cases += [(f'pal-{t:04X}-{k}', r, env) for k, r in (('orig', original), ('grow', fieldpal))]
        rom = Rom(original.read_bytes())
        for m in [NEW_MAP] + SAME_MAPS:
            a = map_pointer(rom, *m)
            env = {'TO': f'{m[0]:02X}/{m[1]:02X},{rom.u8(a + 1) // 2},{rom.u8(a + 2) // 2},1',
                   'DUMPF': str(INDOOR_FRAME), 'SETTLE': '400', 'MAXF': '1100'}
            cases += [(f'indoor-{m[0]:02X}{m[1]:02X}-{k}', r, env) for k, r in (('orig', original), ('grow', indoor))]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            dirs = dict(zip([c[0] for c in cases], pool.map(
                lambda c: gwc.run(mesence, c[1], luas.get(c[0], gfx), c[2], out / c[0], libdir, state), cases)))
        d = {k: (dirs[f'tiles-{k}-grow'], dirs[f'tiles-{k}-orig']) for k in scenes}
        results = [check_tiles('tiles-stand-orig', original, d['stand'][1], SETTLE_FRAME, None, grown=False),
                   check_tiles('tiles-stand', tiles, *d['stand'][:1], SETTLE_FRAME, d['stand'][1]),
                   check_tiles('tiles-walk', tiles, d['walk'][0], WALK_FRAME, d['walk'][1]),
                   check_battle('tiles-battle', tiles, *d['battle']),
                   *(check_tiles(f'tiles-world{w}', tiles, d[f'world{w}'][0], SETTLE_FRAME, d[f'world{w}'][1], w)
                     for w in (1, 2))]
        results += [check_move('move-tiles', dirs['move-tiles'], True), check_move('move-wall', dirs['move-wall'], False),
                    check_redraw('redraw-tiles', tiles, dirs['redraw-tiles'])]
        results.append(check_fieldpal('fieldpal', fieldpal, {t: dirs[f'pal-{t:04X}-grow'] for t in TIME_CASES},
                                      {t: dirs[f'pal-{t:04X}-orig'] for t in TIME_CASES}))
        for m in [NEW_MAP] + SAME_MAPS:
            key = f'indoor-{m[0]:02X}{m[1]:02X}'
            results.append(check_indoor(key, indoor, dirs[f'{key}-grow'], dirs[f'{key}-orig'], m, m == NEW_MAP))
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'{len(results)}/{len(results)} 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
