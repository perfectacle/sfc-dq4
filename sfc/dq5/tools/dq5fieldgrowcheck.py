"""필드 그림 늘리기(세계마다 타일 벌·움직이는 타일 16벌·세계 0 낮밤 인물 팔레트)와 그룹 50 이상 맵 18개 그림 쓰기를
MesenCE 에서 확인한다.

시험 롬(원본에서 만듦)
  grow      세계 1 의 타일 2 를 줄무늬로·그 니블을 2↔3번 줄로, 세계 2 의 타일 2 를 점무늬로(세계 0 은 그대로,
            --worlds-at 34:8000). 움직이는 타일을 16벌로(8~15벌은 0~7벌의 첫 타일을 벌 번호로 칠함, --anim-at 33:8000).
            세계 0 인물 팔레트 낮·밤 30색을 새 색으로
  high-all  그룹 50 이상 CHR 628개를 모두 반전하고 블록 295개의 모든 칸을 좌우 반전해 --chr-at 41:8000 --blocks-at 34:8000
장면
  세계 0 (341,56) 에서 $075E = 00F0 으로 두고 시간 멈춤(7E:2190 bit1)을 끈 채 서 있다가(움직이는 타일 벌을 매 프레임),
  한 걸음 내려가 00F1(밤)이 된 뒤를 덤프. 세계 1·2 는 $1949 를 고정하고 (50,28). grow 롬으로 이벤트 전투를 이기고
  돌아온 뒤, 배에 타고 돌다 내린 뒤에도 16벌이 차례로 도는지 보고, 그동안 7E:C000~DFFF 의 CPU 접근을
  lua/dq5rangewatch.lua 로 모아 벌을 푼 뒤 7E:CE00~D3FF 를 DMA 말고 건드린 곳이 없는지 본다.
  세계를 옮기는 장면(ルーラ 0 → 1 → 2·1 → 0, キメラのつばさ 2 → 0 → 2, 52/50 석상 이벤트, 융단, 天空城 이륙)도 grow 롬으로
  돌려 내린 뒤 창마다 VRAM 타일이 그 세계 벌이고 16벌이 차례로 도는지, 필드를 불러올 때마다 벌을 푼 뒤 7E:CE00~D3FF 에
  DMA 말고 닿은 것이 없는지(RWLOG) 본다.
  그룹 50 이상 맵 18개는 순간이동해 맵별 루틴 직후(15:F7EE).

  MESENCE=… python sfc/dq5/tools/dq5fieldgrowcheck.py rom/dq5.sfc --state work/state/ship.mss --out work/fieldgrowcheck
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
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import dq5fieldgfxcheck as fgc  # noqa: E402
import dq5fieldgfxwrite as fgw  # noqa: E402
import dq5gfxlimitcheck as glc  # noqa: E402
import dq5gfxwritecheck as gwc  # noqa: E402
from dq5field import tile_word  # noqa: E402
from dq5map import Rom, map_pointer  # noqa: E402
import dq5mapgfxwrite as mgw  # noqa: E402
from dq5mapwrite import all_maps  # noqa: E402

require, command = fgc.require, fgc.command
STRIPE, DOTS = gwc.STRIPE, gwc.DOTS
WORLD_TILE = 2                       # 세계 1·2 의 (50,28) 화면에 보이는 타일(세계 0 의 (341,56) 에는 없음)
DAY = [0x7C00 + i for i in range(30)]
NIGHT = [0x03E0 + i for i in range(30)]
SETS = 16
# 서 있는 동안(800~1040) 매 프레임, 한 걸음 내려간 뒤 1100 에 덤프한다. 걸음은 도착(438) + SETTLE 300 + wait 300 쯤.
DUSK = {'FIELD': '341,56', 'SET': '075E=F0;075F=00;2190&FD', 'SETTLE': '300', 'TEST': 'wait:300,down:16,wait:500',
        'EVERY': '1', 'FROM': '800', 'TO': '1040', 'DUMPF': '1100', 'MAXF': '2000'}
DAY_FRAME, NIGHT_FRAME = 1000, 1100
NIB_TILES = {1: WORLD_TILE, 2: 63}   # grow 롬에서 니블을 바꾸는 타일. 세계 2 의 (50,28) 에 보임
# 16벌이 새로 쓰는 WRAM. 2B:8063 이 벌을 풀고, 00:8F75 의 DMA 가 VRAM 으로 읽는다.
SPARE, ANIM_WRITER, ANIM_DMA = (0x7ECE00, 0x7ED3FF), '2B8063', '008F75'
WATCH = {'WATCHR': '7EC000-7EDFFF'}
# 이벤트 전투(스라임 하나)를 A 로 이겨 1,790프레임쯤 필드로 돌아온다. 그 뒤 이벤트 대사 동안(~1975)은 $7F 가 서서
# 벌이 멈추므로, 다시 돌기 시작한 1975~2140 을 본다. 2,160프레임쯤 무작위 전투가 붙어 그 전에 끝낸다.
BATTLE = {'FIELD': '341,56', 'BATTLE': '00:1', 'SETTLE': '300', 'MAXF': '2200', 'DUMPF': '500,1790',
          'EVERY': '1', 'FROM': '1975', 'TO': '2140', **WATCH,
          'TEST': 'wait:100,' + ','.join(['a:4,wait:30'] * 60) + ',wait:600'}
# 세워 둔 배(dq5cdlsweep 의 ship-board)에 올라 바다를 돌고 내린 뒤 걸은 동안(1110~1290). 1,303프레임쯤 무작위 전투가
# 붙어 벌이 멈추므로 그 전에 끝낸다.
SHIP = {'FIELD': '328,39', 'SET': '21B5|80;21CD=48;21CE=01;21CF=25;21D0=00', 'SETTLE': '300', 'MAXF': '1500',
        'DUMPF': '900', 'EVERY': '1', 'FROM': '1110', 'TO': '1290', **WATCH,
        'TEST': 'up:60,wait:60,left:200,up:200,right:200,down:200,left:200,wait:300'}
OBJ_PALETTES = 0x0496D6
# 세계를 옮기는 장면(dq5gfxlimitcheck 의 세계 장면과 같은 입력). grow 롬으로 돌리며 7E:C000~DFFF 의 접근을 프레임마다 모으고
# (RWLOG), 내린 뒤 서 있는 창마다 매 프레임 덤프한다. 이름 → (환경, [(창 시작, 끝, 세계)], 그때 $1954).
MOVES = {
    'rula-1to2': (glc.WORLD_SCENES['rula-1to2'][0], [(1200, 1360, 1), (2200, 2360, 2)], 0),
    'rula-back': (glc.WORLD_SCENES['rula-back'][0], [(1200, 1360, 1), (2300, 2460, 0)], 0),
    'chimera-cross': (glc.WORLD_SCENES['chimera-cross'][0], [(700, 860, 2), (1900, 2060, 0), (2900, 3060, 2)], 0),
    'statue-5250': (glc.WORLD_SCENES['statue-5250'][0], [(3400, 3560, 2)], 0),
    'carpet': ({'FIELD': '310,60', 'SET': '2056=CC', 'MAXF': '2000',
                'TEST': glc.ITEM_MENU + 'wait:300,left:32,up:32,right:32,wait:300'}, [(1100, 1260, 0)], 0x80),
    'castle-0608': (glc.WORLD_SCENES['castle-0608'][0], [(600, 760, 0)], 0x81),
}
# 움직이는 타일 벌을 푸는 2B:8039~ 는 롬 → $2180 DMA 라 쓰기 PC 가 DMA 를 건 자리 언저리(2B:8040·8063·8082)로 잡힌다.
ANIM_UNPACK = {'2B8040', ANIM_WRITER, '2B8082'}


def make_roms(original, out):
    rom = Rom(original.read_bytes())
    src = out / 'grow-src'
    doc = fgw.dump(rom, src)
    tiles = (src / 'tiles.bin').read_bytes()
    for key, pattern in (('world1', STRIPE), ('world2', DOTS)):
        t = bytearray(tiles)
        t[WORLD_TILE * 32:WORLD_TILE * 32 + 32] = pattern
        (src / f'tiles-{key}.bin').write_bytes(t)
        nib = list(doc['tile_palettes'])
        t = NIB_TILES[int(key[-1])]
        require(nib[t] in (0, 1), f'타일 {t} 의 니블이 {nib[t]}')
        nib[t] ^= 1
        doc.setdefault('worlds', {})[key] = {'tiles_file': f'tiles-{key}.bin', 'tile_palettes': nib}
    anim = (src / 'anim.bin').read_bytes()
    extra = bytearray(anim)
    for k in range(8):
        extra[k * fgw.ANIM_SET:k * fgw.ANIM_SET + 32] = bytes([0x11 * (k + 1)]) * 32
    (src / 'anim.bin').write_bytes(anim + extra)
    doc['person_palettes'] = {'day': DAY, 'night': NIGHT}
    (src / 'fieldgfx.json').write_text(json.dumps(doc), encoding='utf-8')
    command('dq5fieldgfxwrite.py', original, 'patch', src / 'fieldgfx.json', '-o', out / 'grow.json',
            '--anim-at', '33:8000', '--worlds-at', '34:8000')
    hsrc = out / 'high-src'
    hdoc = mgw.dump(rom, hsrc, 'high')
    chrs = (hsrc / 'chr.bin').read_bytes()
    (hsrc / 'chr.bin').write_bytes(bytes(b ^ 0xFF for b in chrs))
    for b in hdoc['blocks']:
        b['words'] = [w ^ 0x4000 for w in b['words']]
    (hsrc / 'mapgfx.json').write_text(json.dumps(hdoc), encoding='utf-8')
    command('dq5mapgfxwrite.py', original, 'patch', hsrc / 'mapgfx.json', '-o', out / 'high-all.json',
            '--chr-at', '41:8000', '--blocks-at', '34:8000')
    for name in ('grow', 'high-all'):
        command('dq5build.py', original, 'build', out / f'{name}.json', '--size', '4',
                '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')


def frame(dump, n, ext):
    return (dump / f'f{n:05d}.{ext}').read_bytes()


def person_colors(cg):
    return [fgc.cg_color(cg, row, c) for row in (11, 12) for c in range(1, 16)]


def anim_order(name, dump, frames, sets):
    """frames 마다 VRAM 타일 454~459 가 sets 의 몇째 벌인지, 바뀐 차례대로."""
    order, last = [], None
    for n in frames:
        shown = b''.join(fgc.field_vram_tiles(frame(dump, n, 'vram'))[454:460])
        require(shown in sets, f'{name}: {n}프레임 움직이는 타일 454~459 가 {len(sets)}벌 어디와도 다름')
        k = sets.index(shown)
        if not order or order[-1] != k:
            order.append(k)
            last = n
    steps = [(b - a) % len(sets) for a, b in zip(order, order[1:])]
    require(set(steps) == {1} and len(set(order)) == len(sets), f'{name}: 움직이는 타일 벌 차례 {order}')
    # 벌은 8프레임(가끔 11)마다 넘어가므로, 창 끝까지 돌았다면 마지막으로 바뀐 프레임이 끝에서 16 안이다.
    require(frames[-1] - last <= 16, f'{name}: {last}프레임 뒤로 창 끝({frames[-1]})까지 벌이 멈춤')
    return order


def check_dusk(name, rom_path, dump):
    """서 있는 동안 VRAM 타일·움직이는 타일 벌 차례, 낮 프레임과 한 걸음 뒤 밤 프레임의 11·12번 줄."""
    cur = fgw.current(Rom(rom_path.read_bytes()))
    tiles, _ = cur['worlds']['world0']
    got = fgc.field_vram_tiles(frame(dump, DAY_FRAME, 'vram'))
    bad = [t for t in range(fgw.TILES) if t not in fgc.ANIM_TILES and got[t] != tiles[t * 32:t * 32 + 32]]
    require(not bad, f'{name}: 세계 0 타일 {len(bad)}개가 기대와 다름 {bad[:8]}')
    order = anim_order(name, dump, range(int(DUSK['FROM']), int(DUSK['TO']) + 1), cur['anim_sets'])
    out = {'case': name, 'tiles': fgw.TILES - len(fgc.ANIM_TILES), 'anim_order': order}
    for when, n, want, key in (('day', DAY_FRAME, 0x00F0, 'day'), ('night', NIGHT_FRAME, 0x00F1, 'night')):
        w = frame(dump, n, 'wram')
        t = w[0x75E] | w[0x75F] << 8
        require(t == want and w[0x1949] == 0 and not w[0xBE] & 0x80, f'{name}: {n}프레임 $075E {t:04X}')
        colors = person_colors(frame(dump, n, 'cgram'))
        require(colors == cur['person_palettes'][key], f'{name}: {when} 11·12번 줄이 {key} 인물 팔레트와 다름')
        out[when] = {'frame': n, '075E': f'{t:04X}', 'rows_11_12': 30, 'first': f'{colors[0]:04X}'}
    return out


def palette_cells(name, rom, vram, world, tile):
    """그 타일을 쓰는 타일맵 칸이 모두 dq5field.tile_word(그 세계 니블 표)와 같은지. 칸 수를 돌려준다."""
    words = fgc.tilemap_words(vram, tile)
    require(words, f'{name}: 타일 {tile} 을 쓰는 타일맵 칸이 없음')
    wrong = [v for upper, v in words if v & 0x1FFF != tile_word(rom, tile, upper, world) & 0x1FFF]
    require(not wrong, f'{name}: 타일 {tile} 칸 {len(wrong)}개의 팔레트가 세계 {world} 니블과 다름')
    return len(words)


def check_world(name, rom_path, dump, orig, world):
    """orig 는 (원본 롬, 원본 덤프) 또는 None. 고친 니블은 원본 덤프의 칸이 모두 원래 니블 워드이고 고친 덤프의 칸이
    모두 새 니블 워드이며 두 니블이 다른 것으로 가린다."""
    rom = Rom(rom_path.read_bytes())
    cur = fgw.current(rom)
    tiles, nib = cur['worlds'][f'world{world}']
    w, vram = frame(dump, 900, 'wram'), frame(dump, 900, 'vram')
    require(w[0x1949] == world and not w[0xBE] & 0x80, f'{name}: 세계 {world} 필드에 서지 않음')
    got = fgc.field_vram_tiles(vram)
    bad = [t for t in range(fgw.TILES) if t not in fgc.ANIM_TILES and got[t] != tiles[t * 32:t * 32 + 32]]
    require(not bad, f'{name}: 타일 {len(bad)}개가 세계 {world} 벌과 다름 {bad[:8]}')
    cells = {t: palette_cells(name, rom, vram, world, t) for t in sorted({WORLD_TILE, NIB_TILES[world]})}
    # 세계 1·2 에서는 01:9F4A 가 01:A04B 를 건너뛰어 11·12번 줄이 맵의 OBJ 팔레트 3·4 그대로다.
    obj = [rom.u16(OBJ_PALETTES + (row * 16 + c) * 2) for row in (3, 4) for c in range(1, 16)]
    require(person_colors(frame(dump, 900, 'cgram')) == obj, f'{name}: 11·12번 줄이 04:96D6 의 OBJ 팔레트 3·4 와 다름')
    out = {'case': name, 'tiles': fgw.TILES - len(fgc.ANIM_TILES), 'tilemap_cells': cells,
           'rows_11_12': 'OBJ 팔레트 3·4(04:96D6)'}
    if orig is not None:
        orom, odump = orig
        ov = frame(odump, 900, 'vram')
        pattern = STRIPE if world == 1 else DOTS
        require(got[WORLD_TILE] == pattern != fgc.field_vram_tiles(ov)[WORLD_TILE],
                f'{name}: 고친 타일 {WORLD_TILE} 이 VRAM 에 없음')
        out['edited_tile'] = '줄무늬' if world == 1 else '점무늬'
        t = NIB_TILES[world]
        onib = fgw.current(orom)['worlds'][f'world{world}'][1]
        require(onib[t] != nib[t], f'{name}: 타일 {t} 니블이 원본과 같음')
        ocells = palette_cells(f'{name}(원본)', orom, ov, world, t)
        out['tile_palette'] = f'타일 {t} 칸: 원본 {ocells}개 모두 니블 {onib[t]}, 고친 롬 {cells[t]}개 모두 니블 {nib[t]}'
    return out


def check_scene(name, rom_path, dump, window, before, after):
    """탈것·전투 뒤 서 있는 window 동안 16벌 차례와, 벌을 푼 뒤 7E:CE00~D3FF 를 건드린 것이 DMA(00:8F75)뿐인지.
    before·after 는 (프레임, WRAM 검사 함수, 설명)."""
    cur = fgw.current(Rom(rom_path.read_bytes()))
    for n, test, what in (before, after):
        w = frame(dump, n, 'wram')
        require(test(w), f'{name}: {n}프레임에 {what} 아님')
    for n in window:
        w = frame(dump, n, 'wram')
        require(not w[0xBE] & 0x80 and w[0x1954] == 0, f'{name}: {n}프레임에 걸어서 필드에 서지 않음')
    order = anim_order(name, dump, window, cur['anim_sets'])
    rows = [line.split() for line in (dump / 'rw.txt').read_text().splitlines()]
    loads = [int(r[3]) for r in rows if r[:2] == ['w', ANIM_WRITER]]
    require(loads, f'{name}: 벌을 푸는 {ANIM_WRITER} 의 쓰기가 없음')
    late = [f'{r[0]} {r[1]}' for r in rows if int(r[3]) > max(loads) and int(r[5], 16) <= SPARE[1]
            and int(r[6], 16) >= SPARE[0] and r[:2] != ['r', ANIM_DMA]]
    require(not late, f'{name}: 벌을 푼 뒤 7E:CE00~D3FF 를 건드린 곳 {late}')
    return {'case': name, 'window': f'{window[0]}~{window[-1]}', 'anim_order': order,
            'after_load': f'7E:CE00~D3FF 접근은 {ANIM_DMA} DMA 읽기뿐(벌 풀기 마지막 {max(loads)}프레임)'}


def spare_loads(name, dump):
    """lua/dq5rangewatch.lua 의 rwlog.txt 에서 필드를 불러올 때마다 움직이는 타일 벌을 푼 프레임 묶음과, 7E:CE00~D3FF 에 닿은
    DMA 읽기·벌 풀기 말고의 접근이 모두 어느 벌 풀기보다 앞서는지. 실내 셀 버퍼·타일 RLE 풀기도 이 자리를 쓰므로,
    필드에 올라선 뒤 벌을 다시 풀기 전에 다른 것이 닿으면 안 된다."""
    rows = [x.split() for x in (dump / 'rwlog.txt').read_text().splitlines() if x]
    ev = [(int(r[0]), r[1], r[2]) for r in rows if int(r[3], 16) <= SPARE[1] and int(r[4], 16) >= SPARE[0]]
    unpack = sorted({n for n, k, pc in ev if k == 'w' and pc in ANIM_UNPACK})
    loads = []
    for n in unpack:
        if loads and n - loads[-1][1] <= 2:
            loads[-1][1] = n
        else:
            loads.append([n, n])
    other = [(n, k, pc) for n, k, pc in ev if not (k == 'w' and pc in ANIM_UNPACK) and (k, pc) != ('r', ANIM_DMA)]
    late = [e for e in other if not any(a > e[0] for a, _ in loads)]
    require(loads and not late, f'{name}: 벌을 푼 뒤 7E:CE00~D3FF 에 닿은 것 {late[:5]}')
    return loads, len({pc for _, _, pc in other})


def check_move(name, rom_path, dump, windows, vehicle):
    """세계를 옮긴 뒤 서 있는 창마다 VRAM 타일이 그 세계 벌(다른 세계 벌과는 다름)이고 니블을 바꾼 타일 칸이 그 세계 니블의
    디코더 워드이며, 16벌이 차례로 도는지. 7E:CE00~D3FF 는 spare_loads."""
    rom = Rom(rom_path.read_bytes())
    cur = fgw.current(rom)
    out = []
    for lo, hi, world in windows:
        for n in (lo, hi):
            w = frame(dump, n, 'wram')
            require(w[0x1949] == world and not w[0xBE] & 0x80 and w[0x1954] == vehicle and w[0x1001] == 0,
                    f'{name}: {n}프레임이 세계 {world} 필드·$1954 {vehicle:02X} 가 아님')
        vram = frame(dump, lo, 'vram')
        got = fgc.field_vram_tiles(vram)
        diff = {k: sum(got[t] != v[0][t * 32:t * 32 + 32] for t in range(fgw.TILES) if t not in fgc.ANIM_TILES)
                for k, v in cur['worlds'].items()}
        require(diff[f'world{world}'] == 0 and all(v for k, v in diff.items() if k != f'world{world}'),
                f'{name}: {lo}프레임 타일이 세계 벌과 다른 수 {diff}')
        # 타일맵 전체는 天空城 그림·실내에서 남은 가장자리 줄 같은 필드 밖 칸이 섞여 디코더와 견줄 수 없다. 세계마다 니블을
        # 바꾼 타일 칸만 본다(화면에 없으면 0칸).
        cells = {t: sum(v & 0x1FFF == tile_word(rom, t, u, world) & 0x1FFF for u, v in fgc.tilemap_words(vram, t))
                 for t in sorted({WORLD_TILE, *NIB_TILES.values()})}
        shown = {t: len(fgc.tilemap_words(vram, t)) for t in cells}
        require(cells == shown, f'{name}: {lo}프레임 니블을 바꾼 타일 칸 {shown} 가운데 세계 {world} 워드 {cells}')
        row = {'window': f'{lo}~{hi}', 'world': world, 'tiles_differ_from_other_worlds':
               {k: v for k, v in diff.items() if k != f'world{world}'}, 'nibble_tile_cells': shown}
        row['anim_order'] = anim_order(name, dump, range(lo, hi + 1), cur['anim_sets'])
        out.append(row)
    loads, others = spare_loads(name, dump)
    return {'case': name, 'vehicle': f'{vehicle:02X}', 'windows': out, 'anim_loads': [a for a, _ in loads],
            'other_pcs_before_unpack': others}


def check_high(name, rom_path, dump, orig_dump, bcbd):
    rom = Rom(rom_path.read_bytes())
    buf, chr_map, bank = fgc.expect_map(rom, bcbd, False)
    wram, vram = (dump / 'at_15F7EE.bin').read_bytes(), (dump / 'at_15F7EE.vram').read_bytes()
    require(wram[0xBC:0xBE] == bytes(bcbd), f'{name}: 맵이 {wram[0xBC]:02X}/{wram[0xBD]:02X}')
    cells = sum(a != b for a, b in zip(buf, wram[0xC000:0xC000 + len(buf)]))
    bad = fgc.bad_chr(rom, chr_map, bank, vram)
    require(cells == 0 and not bad, f'{name}: 셀 {cells}바이트·CHR {[f"{i:03X}" for i in bad]} 가 기대와 다름')
    out = {'map': f'{bcbd[0]:02X}/{bcbd[1]:02X}', 'cell_bytes': len(buf), 'chr_slots': len(chr_map)}
    if orig_dump is not None:
        ow, ov = (orig_dump / 'at_15F7EE.bin').read_bytes(), (orig_dump / 'at_15F7EE.vram').read_bytes()
        changed = sum(a != b for a, b in zip(wram[0xC000:0xC000 + len(buf)], ow[0xC000:0xC000 + len(buf)]))
        same = [i for i, word in chr_map.items() if gwc.tile_at(vram, word) == gwc.tile_at(ov, word)]
        require(changed and not same, f'{name}: 원본 게임과 셀 {changed}바이트 다름, 같은 CHR 슬롯 {len(same)}개')
        out['differs_from_original'] = {'cell_bytes': changed, 'chr_slots': len(chr_map)}
    return out


def dump_frames(env):
    """lua/dq5gfxdump.lua 가 이 환경으로 덤프할 프레임."""
    if env.get('EVERY'):
        end = int(env.get('EVERYTO') or env.get('TO') or 0)
        return list(range(int(env.get('FROM', 0)), end + 1, int(env['EVERY'])))
    return [int(n) for n in env.get('DUMPF', '').split(',') if n]


def run_case(mesence, case, out, libdir, state):
    """gwc.run 뒤 덤프할 프레임의 파일이 모두 있는지 보고, 빠졌으면 한 번 다시 돌린다. 그래도 빠지면 mesen.log 끝을 붙여 멈춘다."""
    name, rom, lua, env = case
    want, dest = dump_frames(env), out / name
    for attempt in (1, 2):
        if dest.exists():
            shutil.rmtree(dest)
        gwc.run(mesence, rom, lua, env, dest, libdir, state)
        missing = sorted({n for n in want for ext in ('wram', 'vram', 'cgram')
                          if not (dest / f'f{n:05d}.{ext}').is_file()})
        if not missing:
            return dest
        print(f'{name}: {attempt}번째 실행에서 덤프 {missing[:8]} 빠짐', file=sys.stderr, flush=True)
    log = (dest / 'mesen.log').read_text(encoding='utf-8', errors='replace').splitlines()
    log = [x for x in log if 'Uninitialized memory read' not in x][-20:]
    raise RuntimeError(f'{name}: 두 번 돌려도 덤프 {missing[:8]} 가 없음\n' + '\n'.join(log))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default=Path('work/fieldgrowcheck'))
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
        grow, high = out / 'grow.sfc', out / 'high-all.sfc'
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True,
                                    timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        gfx, atpc, watch = HERE / 'lua/dq5gfxdump.lua', ROOT / 'tools/lua/atpc.lua', HERE / 'lua/dq5rangewatch.lua'
        world = {w: {'FIELD': '50,28', 'POKE': f'7E1949={w:02X}', 'SETTLE': '900', 'DUMPF': '900', 'MAXF': '1800'}
                 for w in (1, 2)}
        rom = Rom(original.read_bytes())
        maps = [m for m in all_maps(rom) if m[0] >= 0x50]
        cases = [('dusk-orig', original, gfx, DUSK), ('dusk-grow', grow, gfx, DUSK),
                 *[(f'world{w}-{k}', r, gfx, world[w]) for w in (1, 2) for k, r in (('orig', original), ('grow', grow))],
                 ('battle-grow', grow, watch, dict(BATTLE, NEXT=str(gfx))),
                 ('ship-grow', grow, watch, dict(SHIP, NEXT=str(gfx)))]
        for k, (env, windows, _) in MOVES.items():
            dumpf = ','.join(str(n) for lo, hi, _ in windows for n in range(lo, hi + 1))
            cases.append((f'move-{k}', grow, watch, dict(env, WATCHR=WATCH['WATCHR'], RWLOG='1', SETTLE='60',
                                                          DUMPF=dumpf, NEXT=str(gfx))))
        for m in maps:
            a = map_pointer(rom, *m)
            env = {'TO': f'{m[0]:02X}/{m[1]:02X},{rom.u8(a + 1) // 2},{rom.u8(a + 2) // 2},1', 'AT': '15F7EE',
                   'SETTLE': '400', 'MAXF': '1500'}
            cases += [(f'high-{m[0]:02X}{m[1]:02X}-{k}', r, atpc, env) for k, r in (('orig', original), ('all', high))]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            dirs = dict(zip([c[0] for c in cases], pool.map(
                lambda c: run_case(mesence, c, out, libdir, state), cases)))
        results = [check_dusk('dusk-orig', original, dirs['dusk-orig']), check_dusk('dusk-grow', grow, dirs['dusk-grow'])]
        orig_person = fgw.current(rom)['person_palettes']
        require(results[0]['day']['first'] == f'{orig_person["day"][0]:04X}', 'dusk-orig: 낮 색이 01:A45E 가 아님')
        for w in (1, 2):
            results.append(check_world(f'world{w}-orig', original, dirs[f'world{w}-orig'], None, w))
            results.append(check_world(f'world{w}-grow', grow, dirs[f'world{w}-grow'], (rom, dirs[f'world{w}-orig']), w))
        results.append(check_scene('battle-grow', grow, dirs['battle-grow'], range(1975, 2141),
                                   (500, lambda w: w[0x1001] == 0, '전투 전($1001 = 0)'),
                                   (1790, lambda w: w[0x1001] != 0, '전투 뒤($1001 ≠ 0)')))
        results.append(check_scene('ship-grow', grow, dirs['ship-grow'], range(1110, 1291),
                                   (900, lambda w: w[0x1954] == 0x03, '배에 탐($1954 = 03)'),
                                   (1110, lambda w: (w[0xB6], w[0xB8]) != (328 & 0xFF, 39), '배에서 내려 옮겨 감')))
        for k, (_, windows, vehicle) in MOVES.items():
            results.append(check_move(k, grow, dirs[f'move-{k}'], windows, vehicle))
        high_results = []
        for m in maps:
            key = f'high-{m[0]:02X}{m[1]:02X}'
            high_results.append({'orig': check_high(f'{key}-orig', original, dirs[f'{key}-orig'], None, m),
                                 'all': check_high(f'{key}-all', high, dirs[f'{key}-all'], dirs[f'{key}-orig'], m)})
        results.append({'case': 'high', 'maps': len(maps), 'results': high_results})
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'{len(results) - 1 + len(maps) * 2}/{len(results) - 1 + len(maps) * 2} 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
