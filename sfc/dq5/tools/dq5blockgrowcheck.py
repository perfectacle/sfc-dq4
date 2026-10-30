"""필드 블록 번호 512개 넘기기와 세계 1·2 의 시간대 벌 늘리기를 MesenCE 에서 확인한다.

시험 롬(원본에서 만듦)
  same    dq5fieldtables --blocks-at 3C:8000 으로 블록 511~1022 를 더하고(블록 512+b 는 블록 b 의 두 층·지형 그대로,
          511 은 블록 0), dq5fieldwrite --planes-at 3D:8000 으로 세 세계 지도의 모든 칸 b 를 b+512 로 바꾼다(00:CF50 이 바꾸는
          칸은 그대로). 원본 게임과 화면·걸음·지형이 모두 같아야 옮긴 표와 10번째 비트 평면을 맞게 읽는 것이다
  swap    same 과 같되 새 블록의 두 층 모두 왼쪽·오른쪽 칸을 맞바꾸고 지형을 0D 로. 타일맵이 원본 게임의 블록마다 좌우를
          바꾼 것이어야 하고, 걸음마다 지형($1AA0)이 0D 여야 한다
  wall-lower / wall-upper  same 과 같되 새 블록의 아래층(위층은 0) / 위층(아래층은 그대로) 네 칸을 속성 80 인 타일로.
          00:BCA8 이 위층 타일이 0 이 아니면 위층 속성을 읽으므로 둘 다 한 칸도 걷지 못해야 한다
  w12pal  세계 1 에 벌 셋·시간대 [0→0, 0080→1, 0100→2], 세계 2 에 벌 둘·시간대 [0→0, 00F0→1]
          (dq5fieldgfxwrite --palettes-at 36:8000)
장면
  세계 0 (341,56) 에 서기·네 방향으로 32프레임씩 걷기, 세계 1·2 (50,28) 에 서기(원본 롬과 견줌).
  w12pal: 세계 1·2 에 서서 $075E 를 매 프레임 고정하고(불러올 때 0 으로 두므로) 2·3번 줄 색 1~13 이 고른 벌인지,
          원본 롬은 그대로인지
--bits 11
  same·swap·wall-lower·wall-upper 를 블록 2,047개로 만든다. 블록 1024+b·1536+b 가 블록 b 를 따르고(511~1023 은 블록 0),
  지도의 칸 b 를 칸 좌표 x+y 가 짝수면 b+1024(11번째 비트만), 홀수면 b+1536(10·11번째 비트)으로 바꾼다.
  세 세계 모두 서기와 걷기를 본다(세계 1·2 는 (50,28) 에 서고, 세계 2 걷기는 바다 (62,64) 에서 왼쪽 해안까지). w12pal 은 돌리지 않는다

  MESENCE=… python sfc/dq5/tools/dq5blockgrowcheck.py rom/dq5.sfc --state work/state/ship.mss --out work/blockgrowcheck
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
import dq5fieldwrite as fw  # noqa: E402
import dq5gfxwritecheck as gwc  # noqa: E402
from dq5field import terrain  # noqa: E402
from dq5map import Rom  # noqa: E402

require, command = fgc.require, fgc.command
STAND_FRAME = 900
STAND = {'FIELD': '341,56', 'SETTLE': str(STAND_FRAME), 'DUMPF': str(STAND_FRAME), 'MAXF': '1100'}
WORLD = {w: {'FIELD': '50,28', 'POKE': f'7E1949={w:02X}', 'SETTLE': str(STAND_FRAME), 'DUMPF': str(STAND_FRAME),
             'MAXF': '1100'} for w in (1, 2)}
# 걷기: 서서 네 방향으로 32프레임씩(dq5gfxlimitcheck 의 move 와 같음). 걷기 앞(700프레임)의 화면과, 입력이 끝나 남는
# final.wram 의 좌표·지형을 본다.
MOVE_FRAME = 700
MOVE = {'FIELD': '341,56', 'SETTLE': '300', 'MAXF': '1300', 'DUMPF': str(MOVE_FRAME),
        'TEST': 'wait:60,left:32,up:32,right:32,down:32,wait:60'}
SWAP_TERRAIN = 0x0D
WALL = 0x80
# 세계 1·2 의 벌과 시간대 표. 하한 위의 $075E 값 → 고르는 벌.
W12 = {1: ([[0, 0], [0x80, 1], [0x100, 2]], {0x0000: 0, 0x0090: 1, 0x0150: 2}),
       2: ([[0, 0], [0xF0, 1]], {0x0000: 0, 0x0100: 1})}
PAL_FRAME = 1000


def swapped(layer):
    return [layer[1], layer[0], layer[3], layer[2]]


def offset(bits, i):
    """칸 i 의 블록 번호에 더하는 값."""
    if bits == 10:
        return 512
    return 1024 if (i % 256 + i // 256) % 2 == 0 else 1536


def source_block(bits, n):
    """새 블록 n 이 따르는 원래 블록 번호. 원래 블록은 0~510 이라 그 밖(1535 등)은 블록 0."""
    for base in ((1536, 1024) if bits == 11 else (512,)):
        if n >= base:
            return n - base if n - base < 511 else 0
    return 0


def make_roms(original, out, bits=10):
    rom = Rom(original.read_bytes())
    command('dq5fieldtables.py', original, 'dump', '-o', out / 'tables.json')
    blocks = json.loads((out / 'tables.json').read_text(encoding='utf-8'))['blocks']
    attrs = fgw.original(rom)['tile_attributes']
    wall = next(t for t in range(1, fgw.TILES) if attrs[t] == WALL and t not in fgc.ANIM_TILES)
    variants = {
        'same': lambda b: (b['lower'], b['upper'], b['terrain']),
        'swap': lambda b: (swapped(b['lower']), swapped(b['upper']), SWAP_TERRAIN),
        'wall-lower': lambda b: ([wall] * 4, [0] * 4, b['terrain']),
        'wall-upper': lambda b: (b['lower'], [wall] * 4, b['terrain']),
    }
    grids = {}
    for w in range(3):
        g = fw.world_grid(rom, w)
        keep = {y * 256 + x for x, y in fw.changed_cells(rom)}
        grids[w] = [v if i in keep else v + offset(bits, i) for i, v in enumerate(g)]
        (out / f'w{w}.bin').write_bytes(b''.join(v.to_bytes(2, 'little') for v in grids[w]))
    for name, make in variants.items():
        new = []
        for n in range(511, 1023 if bits == 10 else 2047):
            lower, upper, land = make(blocks[source_block(bits, n)])
            new.append({'index': n, 'lower': lower, 'upper': upper, 'terrain': land})
        (out / f'{name}-tables.json').write_text(json.dumps({'format': 'dq5fieldtables/1', 'blocks': new}), encoding='utf-8')
        command('dq5fieldtables.py', original, 'patch', out / f'{name}-tables.json', '-o', out / f'{name}-blocks.json',
                '--blocks-at', '3C:8000')
        command('dq5build.py', original, 'build', out / f'{name}-blocks.json', '--size', '4', '-o', out / f'{name}-step.sfc')
        command('dq5fieldwrite.py', out / f'{name}-step.sfc', 'patch', *(x for w in range(3) for x in ('--world', str(w))),
                *(out / f'w{w}.bin' for w in range(3)), '--planes-at', '3D:8000', '-o', out / f'{name}-map.json')
        command('dq5build.py', original, 'build', out / f'{name}-blocks.json', out / f'{name}-map.json', '--size', '4',
                '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')
    if bits == 11:
        return wall
    src = out / 'w12-src'
    doc = fgw.dump(rom, src)
    for k, (times, _) in W12.items():
        base = doc['palettes'][f'world{k}'][0]
        for j in range(1, len({s for _, s in times})):
            doc['palettes'][f'world{k}'].append([0x0842 * (j + k) + i if i not in fgw.CYCLED else base[i] for i in range(30)])
        doc[f'world{k}_times'] = times
    (src / 'fieldgfx.json').write_text(json.dumps(doc), encoding='utf-8')
    command('dq5fieldgfxwrite.py', original, 'patch', src / 'fieldgfx.json', '-o', out / 'w12pal.json',
            '--palettes-at', '36:8000')
    command('dq5build.py', original, 'build', out / 'w12pal.json', '--size', '4', '-o', out / 'w12pal.sfc')
    return wall


def frame(dump, n, ext):
    return (dump / f'f{n:05d}.{ext}').read_bytes()


def tilemap(vram):
    """BG2(워드 0000)·BG1(워드 0800) 타일맵 64x32 워드씩(32x32 화면 둘)."""
    return [vram[i * 2] | vram[i * 2 + 1] << 8 for i in range(0x1000)]


def standing(name, dump, n, world):
    w = frame(dump, n, 'wram')
    require(w[0x1949] == world and not w[0xBE] & 0x80 and w[0x1001] == 0, f'{name}: {n}프레임에 세계 {world} 필드에 서지 않음')
    return w


def check_same(name, dump, orig, n, world, swap=False):
    """same 롬이면 BG1·2 타일맵·VRAM 필드 타일이 원본 게임과 같고, swap 롬이면 타일맵이 원본 게임의 블록마다 좌우를 바꾼 것인지.
    둘 다 옮긴 블록(512 이상)으로 그린 칸이어야 하므로 지도에서 그 자리의 블록 번호도 본다."""
    w = standing(name, dump, n, world)
    standing(name, orig, n, world)
    got, want = tilemap(frame(dump, n, 'vram')), tilemap(frame(orig, n, 'vram'))
    cells = range(len(want))
    if swap:
        # 블록이 타일맵의 짝수 열에서 시작하는지 홀수 열에서 시작하는지는 장면마다 다르다(세계 1 (50,28) 은 홀수).
        # 둘 가운데 맞는 쪽으로 짝을 짓고, 화면 가장자리처럼 블록 한쪽 칸만 그린 열은 짝 칸이 둘 다 채워진 칸만 본다.
        def pair(i, p):
            # 64x32 타일맵은 32x32 화면 둘(워드 0~3FF, 400~7FF)이 나란히 있다.
            layer, k = divmod(i, 0x800)
            gx, y = k // 0x400 * 32 + k % 32, k % 0x400 // 32
            gx = ((gx - p ^ 1) + p) % 64
            return layer * 0x800 + gx // 32 * 0x400 + y * 32 + gx % 32
        tries = []
        for p in (0, 1):
            cs = [i for i in cells if want[i] not in (0, 0x2000) and want[pair(i, p)] not in (0, 0x2000)]
            tries.append((sum(got[i] != want[pair(i, p)] for i in cs), p, cs))
        _, parity, cells = min(tries)
        want = [want[pair(i, parity)] for i in range(len(want))]
    filled = sum(want[i] not in (0, 0x2000) for i in cells)
    bad = sum(got[i] != want[i] for i in cells)
    what = '좌우를 바꾼 ' if swap else ''
    require(filled and not bad, f'{name}: 타일맵 워드 {bad}개가 {what}원본 게임과 다름(채운 칸 {filled})')
    tiles = frame(dump, n, 'vram')[0x4000:0x8000] == frame(orig, n, 'vram')[0x4000:0x8000]
    bx, by = (w[0xB6] | w[0xB7] << 8) >> 1, (w[0xB8] | w[0xB9] << 8) >> 1
    return {'case': name, 'frame': n, 'world': world, 'tilemap_words': len(cells), 'filled': filled,
            'swapped': swap, 'field_tiles_same': tiles, 'hero_block': [bx, by]}


def check_walk(name, rom_path, dump, orig, want, world=0):
    """걷기 뒤 좌표·지형. want 가 'same' 이면 원본 게임과 같은 자리·지형, 'swap' 이면 같은 자리에 지형 0D,
    'wall' 이면 한 칸도 못 감."""
    line = next(x for x in (dump / 'warp.txt').read_text().splitlines() if ' test ' in x)
    w, ow = ((d / 'final.wram').read_bytes() for d in (dump, orig))
    pos, opos = (list(x[0xB6:0xBA]) for x in (w, ow))
    if want == 'wall':
        require('moved=no' in line, f'{name}: 속성 {WALL:02X} 타일 블록인데 걸음 {line}')
    else:
        require(pos == opos and 'moved=yes' in line, f'{name}: 걸은 뒤 자리 {pos} 가 원본 게임 {opos} 와 다름')
        land = SWAP_TERRAIN if want == 'swap' else ow[0x1AA0]
        require(w[0x1AA0] == land, f'{name}: 지형 $1AA0 = {w[0x1AA0]:02X}({land:02X} 이어야 함)')
    rom = Rom(rom_path.read_bytes())
    require(w[0x1949] == world, f'{name}: 걸은 뒤 세계가 {w[0x1949]}')
    b = fw.world_grid(rom, world)[((w[0xB8] | w[0xB9] << 8) >> 1) * 256 + ((w[0xB6] | w[0xB7] << 8) >> 1)]
    return {'case': name, 'world': world, 'walk': line.split(' test ')[1], 'terrain': f'{w[0x1AA0]:02X}', 'block_here': b,
            'block_terrain': terrain(rom, b)}


def rows23(cg):
    return [fgc.cg_color(cg, row, c) for row in (2, 3) for c in range(1, 14)]


def check_w12(name, rom_path, dumps, orig_dumps, world):
    cur = fgw.current(Rom(rom_path.read_bytes()))
    sets = cur['palettes'][f'world{world}']
    out = []
    for t, k in W12[world][1].items():
        w = standing(name, dumps[t], PAL_FRAME, world)
        require(w[0x75E] | w[0x75F] << 8 == t, f'{name} {t:04X}: $075E 가 {w[0x75E] | w[0x75F] << 8:04X}')
        got = rows23(frame(dumps[t], PAL_FRAME, 'cgram'))
        want = [sets[k][i] for i in range(30) if i % 15 < 13]
        require(got == want, f'{name} {t:04X}: 2·3번 줄이 벌 {k} 와 다름')
        ocg = frame(orig_dumps[t], PAL_FRAME, 'cgram')
        orig_set = [sets[0][i] for i in range(30) if i % 15 < 13]
        require(rows23(ocg) == orig_set, f'{name} {t:04X}: 원본 게임의 2·3번 줄이 원래 벌이 아님')
        out.append({'075E': f'{t:04X}', 'set': k, 'rows_2_3': len(got), 'differs_from_original': got != orig_set})
    return {'case': name, 'world': world, 'times': out}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default=Path('work/blockgrowcheck'))
    ap.add_argument('--bits', type=int, choices=(10, 11), default=10, help='시험 롬의 블록 번호 비트 수')
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
        wall = make_roms(original, out, args.bits)
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True,
                                    timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        gfx = HERE / 'lua/dq5gfxdump.lua'
        if args.bits == 11:
            return main11(args, out, original, state, mesence, libdir, gfx, wall)
        roms = {k: out / f'{k}.sfc' for k in ('same', 'swap', 'wall-lower', 'wall-upper', 'w12pal')}
        cases = []
        for scene, env in (('stand', STAND), ('world1', WORLD[1]), ('world2', WORLD[2]), ('move', MOVE)):
            cases += [(f'{scene}-orig', original, env), (f'{scene}-same', roms['same'], env),
                      (f'{scene}-swap', roms['swap'], env)]
        cases += [(f'move-{k}', roms[k], MOVE) for k in ('wall-lower', 'wall-upper')]
        for world, (_, picks) in W12.items():
            for t in picks:
                env = dict(WORLD[world], SETTLE=str(PAL_FRAME), DUMPF=str(PAL_FRAME), MAXF='1200',
                           POKE=f'7E1949={world:02X};7E075E={t & 0xFF:02X};7E075F={t >> 8:02X}')
                cases += [(f'pal{world}-{t:04X}-{k}', r, env) for k, r in (('orig', original), ('grow', roms['w12pal']))]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            dirs = dict(zip([c[0] for c in cases], pool.map(
                lambda c: gwc.run(mesence, c[1], gfx, c[2], out / c[0], libdir, state), cases)))
        results = []
        for scene, world in (('stand', 0), ('world1', 1), ('world2', 2)):
            for k in ('same', 'swap'):
                results.append(check_same(f'{scene}-{k}', dirs[f'{scene}-{k}'], dirs[f'{scene}-orig'], STAND_FRAME, world,
                                          k == 'swap'))
        results.append(check_same('move-same', dirs['move-same'], dirs['move-orig'], MOVE_FRAME, 0))
        for k, want in (('same', 'same'), ('swap', 'swap'), ('wall-lower', 'wall'), ('wall-upper', 'wall')):
            results.append(check_walk(f'move-{k}', roms[k], dirs[f'move-{k}'], dirs['move-orig'], want))
        for world, (_, picks) in W12.items():
            results.append(check_w12(f'w12pal-world{world}', roms['w12pal'],
                                     {t: dirs[f'pal{world}-{t:04X}-grow'] for t in picks},
                                     {t: dirs[f'pal{world}-{t:04X}-orig'] for t in picks}, world))
        results.append({'wall_tile': wall})
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'{len(results) - 1}건 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, StopIteration, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


def main11(args, out, original, state, mesence, libdir, gfx, wall):
    variants = ('same', 'swap', 'wall-lower', 'wall-upper')
    roms = {k: out / f'{k}.sfc' for k in variants}
    moves = {0: MOVE, **{w: dict(MOVE, FIELD=WORLD[w]['FIELD'], POKE=WORLD[w]['POKE']) for w in (1, 2)}}
    # 세계 2 (50,28) 은 배가 뭍에 있어 원본 게임도 걷지 못한다. 바다 (62,64) 에서 왼쪽 해안 (52,64) 에 닿을 때까지 민다.
    # 이 장면은 블록을 늘린 롬이 원본보다 한 걸음(8프레임) 늦게 떠나서, 걸음 수가 아니라 막히는 자리로 견준다
    moves[2].update(FIELD='62,64', TEST='wait:60,left:120,wait:60')
    stands = {0: STAND, **WORLD}
    cases = []
    for world in range(3):
        cases += [(f'stand{world}-{k}', r, stands[world]) for k, r in (('orig', original), ('same', roms['same']),
                                                                         ('swap', roms['swap']))]
        cases += [(f'move{world}-{k}', r, moves[world]) for k, r in (('orig', original), *roms.items())]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        dirs = dict(zip([c[0] for c in cases], pool.map(
            lambda c: gwc.run(mesence, c[1], gfx, c[2], out / c[0], libdir, state), cases)))
    results = []
    for world in range(3):
        for k in ('same', 'swap'):
            r = check_same(f'stand{world}-{k}', dirs[f'stand{world}-{k}'], dirs[f'stand{world}-orig'], STAND_FRAME,
                           world, k == 'swap')
            bx, by = r['hero_block']
            r['hero_block_number'] = fw.world_grid(Rom(roms[k].read_bytes()), world)[by * 256 + bx]
            require(r['hero_block_number'] >= 1024, f'stand{world}-{k}: 주인공 칸 블록 {r["hero_block_number"]}')
            results.append(r)
        results.append(check_same(f'move{world}-same', dirs[f'move{world}-same'], dirs[f'move{world}-orig'], MOVE_FRAME,
                                  world))
        for k, want in (('same', 'same'), ('swap', 'swap'), ('wall-lower', 'wall'), ('wall-upper', 'wall')):
            r = check_walk(f'move{world}-{k}', roms[k], dirs[f'move{world}-{k}'], dirs[f'move{world}-orig'], want, world)
            if want != 'wall':
                require(r['block_here'] >= 1024, f'move{world}-{k}: 걸은 뒤 칸 블록 {r["block_here"]}')
            results.append(r)
    results.append({'wall_tile': wall, 'bits': 11})
    (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'{len(results) - 1}건 통과')
    print(json.dumps(results, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
