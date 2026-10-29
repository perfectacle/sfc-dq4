"""필드 그림 늘리기(세계마다 타일 벌·움직이는 타일 16벌·세계 0 낮밤 인물 팔레트)와 그룹 50 이상 맵 18개 그림 쓰기를
MesenCE 에서 확인한다.

시험 롬(원본에서 만듦)
  grow      세계 1 의 타일 2 를 줄무늬로·그 니블을 2↔3번 줄로, 세계 2 의 타일 2 를 점무늬로(세계 0 은 그대로,
            --worlds-at 34:8000). 움직이는 타일을 16벌로(8~15벌은 0~7벌의 첫 타일을 벌 번호로 칠함, --anim-at 33:8000).
            세계 0 인물 팔레트 낮·밤 30색을 새 색으로
  high-all  그룹 50 이상 CHR 628개를 모두 반전하고 블록 295개의 모든 칸을 좌우 반전해 --chr-at 41:8000 --blocks-at 34:8000
장면
  세계 0 (341,56) 에서 $075E = 00F0 으로 두고 시간 멈춤(7E:2190 bit1)을 끈 채 서 있다가(움직이는 타일 벌을 매 프레임),
  한 걸음 내려가 00F1(밤)이 된 뒤를 덤프. 세계 1·2 는 $1949 를 고정하고 (50,28). 그룹 50 이상 맵 18개는 순간이동해
  맵별 루틴 직후(15:F7EE).

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
import dq5gfxwritecheck as gwc  # noqa: E402
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
OBJ_PALETTES = 0x0496D6


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
        if key == 'world1':
            require(nib[WORLD_TILE] in (0, 1), f'타일 {WORLD_TILE} 의 니블이 {nib[WORLD_TILE]}')
            nib[WORLD_TILE] ^= 1
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


def tile_word(nib, tile, upper):
    """00:BBAC 를 니블 목록으로(dq5field.tile_word 와 같은 셈)."""
    v = nib[tile]
    p = (v if upper else v & 7) << 2
    return tile | (p + 8) << 8


def check_dusk(name, rom_path, dump):
    """서 있는 동안 VRAM 타일·움직이는 타일 벌 차례, 낮 프레임과 한 걸음 뒤 밤 프레임의 11·12번 줄."""
    cur = fgw.current(Rom(rom_path.read_bytes()))
    tiles, _ = cur['worlds']['world0']
    got = fgc.field_vram_tiles(frame(dump, DAY_FRAME, 'vram'))
    bad = [t for t in range(fgw.TILES) if t not in fgc.ANIM_TILES and got[t] != tiles[t * 32:t * 32 + 32]]
    require(not bad, f'{name}: 세계 0 타일 {len(bad)}개가 기대와 다름 {bad[:8]}')
    sets, order = cur['anim_sets'], []
    for n in range(int(DUSK['FROM']), int(DUSK['TO']) + 1):
        shown = b''.join(fgc.field_vram_tiles(frame(dump, n, 'vram'))[454:460])
        require(shown in sets, f'{name}: {n}프레임 움직이는 타일 454~459 가 {len(sets)}벌 어디와도 다름')
        k = sets.index(shown)
        if not order or order[-1] != k:
            order.append(k)
    steps = [(b - a) % len(sets) for a, b in zip(order, order[1:])]
    require(set(steps) == {1} and len(set(order)) == len(sets),
            f'{name}: 움직이는 타일 벌 차례 {order}')
    out = {'case': name, 'tiles': fgw.TILES - len(fgc.ANIM_TILES), 'anim_order': order}
    for when, n, want, key in (('day', DAY_FRAME, 0x00F0, 'day'), ('night', NIGHT_FRAME, 0x00F1, 'night')):
        w = frame(dump, n, 'wram')
        t = w[0x75E] | w[0x75F] << 8
        require(t == want and w[0x1949] == 0 and not w[0xBE] & 0x80, f'{name}: {n}프레임 $075E {t:04X}')
        colors = person_colors(frame(dump, n, 'cgram'))
        require(colors == cur['person_palettes'][key], f'{name}: {when} 11·12번 줄이 {key} 인물 팔레트와 다름')
        out[when] = {'frame': n, '075E': f'{t:04X}', 'rows_11_12': 30, 'first': f'{colors[0]:04X}'}
    return out


def check_world(name, rom_path, dump, orig_dump, world):
    cur = fgw.current(Rom(rom_path.read_bytes()))
    tiles, nib = cur['worlds'][f'world{world}']
    w, vram = frame(dump, 900, 'wram'), frame(dump, 900, 'vram')
    require(w[0x1949] == world and not w[0xBE] & 0x80, f'{name}: 세계 {world} 필드에 서지 않음')
    got = fgc.field_vram_tiles(vram)
    bad = [t for t in range(fgw.TILES) if t not in fgc.ANIM_TILES and got[t] != tiles[t * 32:t * 32 + 32]]
    require(not bad, f'{name}: 타일 {len(bad)}개가 세계 {world} 벌과 다름 {bad[:8]}')
    words = fgc.tilemap_words(vram, WORLD_TILE)
    require(words, f'{name}: 타일 {WORLD_TILE} 을 쓰는 타일맵 칸이 없음')
    wrong = [v for upper, v in words if v & 0x1FFF != tile_word(nib, WORLD_TILE, upper) & 0x1FFF]
    require(not wrong, f'{name}: 타일 {WORLD_TILE} 칸의 팔레트가 세계 {world} 니블과 다름')
    # 세계 1·2 에서는 01:9F4A 가 01:A04B 를 건너뛰어 11·12번 줄이 맵의 OBJ 팔레트 3·4 그대로다.
    obj = [Rom(rom_path.read_bytes()).u16(OBJ_PALETTES + (row * 16 + c) * 2) for row in (3, 4) for c in range(1, 16)]
    require(person_colors(frame(dump, 900, 'cgram')) == obj, f'{name}: 11·12번 줄이 04:96D6 의 OBJ 팔레트 3·4 와 다름')
    out = {'case': name, 'tiles': fgw.TILES - len(fgc.ANIM_TILES), 'tilemap_cells_of_tile': len(words),
           'rows_11_12': 'OBJ 팔레트 3·4(04:96D6)'}
    if orig_dump is not None:
        ov = frame(orig_dump, 900, 'vram')
        pattern = STRIPE if world == 1 else DOTS
        require(got[WORLD_TILE] == pattern != fgc.field_vram_tiles(ov)[WORLD_TILE],
                f'{name}: 고친 타일 {WORLD_TILE} 이 VRAM 에 없음')
        out['edited_tile'] = '줄무늬' if world == 1 else '점무늬'
        if world == 1:
            ow = dict(fgc.tilemap_words(ov, WORLD_TILE))
            require(all(ow.get(u) != v for u, v in words), f'{name}: 고친 니블이 타일맵에 없음')
            out['tile_palette'] = f'타일 {WORLD_TILE} 칸 {len(words)}개의 팔레트 줄이 바뀜'
    return out


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
        gfx, atpc = HERE / 'lua/dq5gfxdump.lua', ROOT / 'tools/lua/atpc.lua'
        world = {w: {'FIELD': '50,28', 'POKE': f'7E1949={w:02X}', 'SETTLE': '900', 'DUMPF': '900', 'MAXF': '1800'}
                 for w in (1, 2)}
        rom = Rom(original.read_bytes())
        maps = [m for m in all_maps(rom) if m[0] >= 0x50]
        cases = [('dusk-orig', original, gfx, DUSK), ('dusk-grow', grow, gfx, DUSK),
                 *[(f'world{w}-{k}', r, gfx, world[w]) for w in (1, 2) for k, r in (('orig', original), ('grow', grow))]]
        for m in maps:
            a = map_pointer(rom, *m)
            env = {'TO': f'{m[0]:02X}/{m[1]:02X},{rom.u8(a + 1) // 2},{rom.u8(a + 2) // 2},1', 'AT': '15F7EE',
                   'SETTLE': '400', 'MAXF': '1500'}
            cases += [(f'high-{m[0]:02X}{m[1]:02X}-{k}', r, atpc, env) for k, r in (('orig', original), ('all', high))]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            dirs = dict(zip([c[0] for c in cases], pool.map(
                lambda c: gwc.run(mesence, c[1], c[2], c[3], out / c[0], libdir, state), cases)))
        results = [check_dusk('dusk-orig', original, dirs['dusk-orig']), check_dusk('dusk-grow', grow, dirs['dusk-grow'])]
        orig_person = fgw.current(rom)['person_palettes']
        require(results[0]['day']['first'] == f'{orig_person["day"][0]:04X}', 'dusk-orig: 낮 색이 01:A45E 가 아님')
        for w in (1, 2):
            results.append(check_world(f'world{w}-orig', original, dirs[f'world{w}-orig'], None, w))
            results.append(check_world(f'world{w}-grow', grow, dirs[f'world{w}-grow'], dirs[f'world{w}-orig'], w))
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
