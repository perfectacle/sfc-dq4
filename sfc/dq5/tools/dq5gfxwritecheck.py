"""전투 배경·실내 맵 그림 쓰기 결과를 MesenCE 에서 확인한다.

시험 롬 다섯 벌을 원본에서 만든다.
  bg-inplace  배경 06 의 그림 B 칸 하나를 같은 그림의 다른 타일로, 팔레트 레코드 첫 색을 빨강으로
              (그림이 원래 크기 안이라 제자리에 씀)
  bg-repack   그 칸을 줄무늬로(그림이 커져 그림 자리를 다시 놓음)과 같은 색
  bg-moved    bg-repack 수정 + 그림 전체를 --at 40:8000 으로
  bg-tables   bg-repack 수정 + 팔레트 레코드 --palettes-at 43:8000, 목록 --lists-at 44:8000
  map-rows    BG 팔레트 줄 208 을 더하고 01/05 낮 목록의 줄 50 자리를 208 로, 줄 52 의 색 4~15 를 바꿔
              --palettes-at 42:8000(10:DE84 훅). 필드에 서서 줄 52 를 쓰는 4번 줄도 본다
  map-inplace CHR 080 을 줄무늬로, BG 팔레트 줄 50 의 1번 색을 빨강으로, CHR 080 을 쓰는 블록 하나를 좌우 반전(제자리)
  map-moved   CHR 을 늘려(새 CHR) --chr-at 40:8000, 새 블록(그 CHR 2x2)을 더해 --blocks-at 31:8000,
              01/05 맵 끝에 그 블록을 (4,2) 에 놓음(dq5mapwrite --at 30:8000)
원본과 함께 배경은 이벤트 전투(배경 06), 맵은 01/05 에 들어가 덤프하고,
게임의 VRAM·CGRAM·셀 버퍼가 그 롬을 따라 푼 기대값과 같은지, 고친 자리가 원본 게임과 다른지 본다.
map-moved 는 21/02 에서 무작위 전투를 붙여 にげる 로 나온 뒤와 명령 창을 연 동안에도 CHR 슬롯이 원본 게임과
같은 만큼 맞는지 본다(움직이는 타일은 두 롬 모두 디코더와 다름).

  MESENCE=… python sfc/dq5/tools/dq5gfxwritecheck.py rom/dq5.sfc --state work/state/ship.mss --out work/gfxwritecheck
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
import dq5battlebg as bg  # noqa: E402
import dq5map  # noqa: E402
from dq5map import Rom, lorom, map_pointer  # noqa: E402
import dq5battlebgwrite as bgw  # noqa: E402
import dq5mapgfxwrite as mgw  # noqa: E402
import dq5mesen  # noqa: E402

STRIPE = bytes(v for r in range(8) for v in ((0xAA if r % 2 == 0 else 0x55), 0xFF)) + bytes([0x0F, 0]) * 8
DOTS = bytes(v for r in range(8) for v in (0x81 << (r % 4) & 0xFF, 0)) + bytes([0xFF, 0xFF]) * 8
BG, BG_CELL, BG_PALETTE = 6, 10, 0x18 // 2
MAP, MAP_CHR, MAP_ROW, NEW_BLOCK_AT = (1, 5), 0x080, 50, (4, 2)
NEW_ROW = [0] + [0x001F, 0x03E0, 0x7C00] * 5                    # 더하는 BG 팔레트 줄: 빨강·초록·파랑
ENTRY = '01/05,34,48'
# 실내 맵 BG 의 글자 기준은 VRAM 바이트 4000(타일 200)이다(01/05 덤프에서 CHR 이 슬롯 + 200 자리에 있음).
CHR_VRAM = 0x200


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command(tool, *args):
    subprocess.run([sys.executable, str(HERE / tool), *map(str, args)], check=True, capture_output=True,
                   text=True, timeout=300)


def make_roms(original, out):
    rom = Rom(original.read_bytes())
    src = out / 'bg-src'
    doc = bgw.dump(rom, src)
    pic_id = bgw.ident(0x280000 | rom.u16(bg.PICS + bg.entry(rom, BG)[0] + 2))
    pic = next(p for p in doc['pictures'] if p['id'] == pic_id)
    data = bytearray((src / pic['file']).read_bytes())
    original_tiles = bytes(data)
    data[BG_CELL * 32:BG_CELL * 32 + 32] = STRIPE
    (src / pic['file']).write_bytes(data)
    pic['cells'] = pic['cells'][:BG_CELL] + '1' + pic['cells'][BG_CELL + 1:]
    pal = next(p for p in doc['palettes'] if p['id'] == doc['palette_table'][BG_PALETTE])
    pal['rows'][0][0] = 0x001F
    (src / 'bg.json').write_text(json.dumps(doc), encoding='utf-8')
    for name, extra in (('bg-repack', []), ('bg-moved', ['--at', '40:8000']),
                        ('bg-tables', ['--palettes-at', '43:8000', '--lists-at', '44:8000'])):
        command('dq5battlebgwrite.py', original, 'patch', src / 'bg.json', '-o', out / f'{name}.json', *extra)
    # 제자리: 칸 하나를 같은 그림의 다른 타일로 바꿔 그림이 원래 크기 안에 드는 것을 고른다.
    cells = pic['cells']
    for j in range(len(cells)):
        tile = original_tiles[j * 32:j * 32 + 32]
        if cells[j] != '1' or j == BG_CELL or tile == original_tiles[BG_CELL * 32:BG_CELL * 32 + 32] or not any(tile):
            continue
        trial = bytearray(original_tiles)
        trial[BG_CELL * 32:BG_CELL * 32 + 32] = tile
        (src / pic['file']).write_bytes(trial)
        manifest, _ = bgw.patch(rom, doc, src)
        notes = [w['note'] for w in manifest['writes']]
        if f'pictures {pic_id}' in notes and not any(n.endswith('표') for n in notes):
            (out / 'bg-inplace.json').write_text(json.dumps(manifest), encoding='utf-8')
            inplace_tile = bytes(tile)
            break
    else:
        raise ValueError('제자리에 들어가는 그림 수정을 찾지 못함')

    msrc = out / 'map-src'
    mdoc = mgw.dump(rom, msrc)
    chrs = bytearray((msrc / 'chr.bin').read_bytes())
    chrs[MAP_CHR * 32:MAP_CHR * 32 + 32] = STRIPE
    mdoc['palettes'][MAP_ROW][1] = 0x001F
    from dq5mapwrite import parse
    commands = parse(rom, map_pointer(rom, *MAP))[0]['commands']
    in_map = sorted({c[1] for c in commands if c[0] == 'block'})
    flipped = next(i for i in in_map if any(w & 0xFFF == MAP_CHR for w in mdoc['blocks'][i]['words']))
    mdoc['blocks'][flipped]['words'] = [w ^ 0x4000 for w in mdoc['blocks'][flipped]['words']]
    (msrc / 'chr.bin').write_bytes(chrs)
    (msrc / 'mapgfx.json').write_text(json.dumps(mdoc), encoding='utf-8')
    command('dq5mapgfxwrite.py', original, 'patch', msrc / 'mapgfx.json', '-o', out / 'map-inplace.json')
    rsrc = out / 'map-rows-src'
    rdoc = mgw.dump(rom, rsrc)
    rdoc['palettes'].append(list(NEW_ROW))
    # 필드 4번 줄이 쓰는 줄 52 의 색 4~15 도 바꿔, 필드도 옮긴 표를 읽는지 가른다(원래 자리에는 옛 색이 남음).
    rdoc['palettes'][0x34][4:] = NEW_ROW[4:]
    day = rdoc['palette_sets'][dq5map.palette_set(rom, *MAP)][0]
    rdoc['palette_lists'][day] = [len(rdoc['palettes']) - 1 if v == MAP_ROW else v for v in rdoc['palette_lists'][day]]
    (rsrc / 'mapgfx.json').write_text(json.dumps(rdoc), encoding='utf-8')
    command('dq5mapgfxwrite.py', original, 'patch', rsrc / 'mapgfx.json', '-o', out / 'map-rows.json',
            '--palettes-at', '42:8000')

    grow = out / 'map-grow'
    gdoc = mgw.dump(rom, grow)
    new_chr = len(gdoc['chr_palettes'])
    (grow / 'chr.bin').write_bytes((grow / 'chr.bin').read_bytes() + DOTS)
    gdoc['chr_palettes'].append(gdoc['chr_palettes'][MAP_CHR])
    template = mdoc['blocks'][flipped]
    new_block = len(gdoc['blocks'])
    gdoc['blocks'].append({'w': 2, 'h': 2, 'flags': template['flags'], 'b1': template['b1'],
                           'attr': template['attr'],
                           'words': [new_chr, new_chr | 0x4000, new_chr | 0x8000, new_chr | 0xC000]})
    (grow / 'mapgfx.json').write_text(json.dumps(gdoc), encoding='utf-8')
    command('dq5mapgfxwrite.py', original, 'patch', grow / 'mapgfx.json', '-o', out / 'map-grow.json',
            '--chr-at', '40:8000', '--blocks-at', '31:8000')
    command('dq5mapwrite.py', original, 'dump', '01', '05', '-o', grow / 'map0105.json')
    m = json.loads((grow / 'map0105.json').read_text(encoding='utf-8'))
    require(m['commands'][-1] == ['end'], '01/05 명령 끝이 end 가 아님')
    m['commands'][-1:] = [['block', new_block], ['put', *NEW_BLOCK_AT], ['end']]
    (grow / 'map0105.json').write_text(json.dumps(m), encoding='utf-8')
    command('dq5mapwrite.py', original, 'patch', grow / 'map0105.json', '-o', out / 'map-0105.json')

    builds = {'bg-inplace': ['bg-inplace.json'], 'bg-repack': ['bg-repack.json'], 'bg-moved': ['bg-moved.json'],
              'bg-tables': ['bg-tables.json'], 'map-rows': ['map-rows.json'],
              'map-inplace': ['map-inplace.json'], 'map-moved': ['map-grow.json', 'map-0105.json']}
    for name, lists in builds.items():
        command('dq5build.py', original, 'build', *(out / p for p in lists), '--size', '4',
                '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')
    return {'new_chr': new_chr, 'new_block': new_block, 'flipped_block': flipped, 'bg_tiles': {
        'bg-inplace': inplace_tile, 'bg-repack': STRIPE, 'bg-moved': STRIPE, 'bg-tables': STRIPE}}


# 프로브(sfc/dq5/tools/lua, tools/lua)와 드라이버(dq5warp.lua, krpatch sfc lua 의 boot·lib)가 os.getenv 로 읽는 키
# (LIBDIR·STATE·SHOT_DIR 는 run 이 둠). 셸에 남은 값이 장면에 섞이지 않게 모두 지운 뒤 env_extra 만 넣는다.
# 그 Lua 들에 새 키를 더하면 여기에도 더할 것.
LUA_ENV = (
    'A0', 'ACC', 'ACCESS', 'ACCRANGE', 'ADULT', 'AFTER', 'ANYWHERE', 'APRESS', 'APUF', 'APUPORTS', 'AT', 'AUDIT',
    'AUDITMISS', 'AUDITOPEN', 'BATTLE', 'BBUS', 'BG3FONT', 'BOOT', 'BUDGET', 'CALLS', 'CAP', 'CDL', 'CDLEVERY',
    'CELL', 'CGF', 'CGW', 'CHANGES', 'CHECKAT', 'CHECK_GROUP', 'CHECK_MAP', 'CMDS', 'COUNT', 'COVER', 'COVHI',
    'COVLO', 'DBMISS', 'DBREAD', 'DBWIN', 'DELAY', 'DP86OK', 'DRIVER', 'DSP', 'DSPFROM', 'DUMP', 'DUMPAT', 'DUMPER',
    'DUMPF', 'DUMPFROM', 'DUMPTO', 'ENVLOG', 'EVERY', 'EVERYTO', 'EXEC', 'EXECLOG', 'EXECS', 'FIELD', 'FIELDSNAP',
    'FIELDT', 'FLAG', 'FLEE', 'FORCE', 'FRAMES', 'FREE', 'FREEWATCH', 'FROM', 'FROMMSG', 'FULLSET', 'GAP',
    'GRIDDELAY', 'GROUP', 'HARG', 'HCMD', 'HFROM_ARG', 'HFROM_CMD', 'HI', 'HOLD', 'HOOK', 'HX', 'INIT', 'INNER',
    'INPUT', 'JITTER', 'LAST', 'LATE', 'LATESET', 'LEARNED', 'LIMIT', 'LO', 'LOG', 'LOGEVERY', 'LOGFROM', 'LOOP',
    'LVLUP', 'MAXCALL', 'MAXF', 'MAXK', 'MAXN', 'MEM', 'MESSAGE', 'MODE', 'MSGLOG', 'NAME', 'NEXT', 'OLD_FLAG',
    'ONLY', 'OUT', 'PARTY', 'PEEK', 'PEEKF', 'PERIOD', 'PF', 'POKE', 'POKE1', 'POKEAT', 'POKEONCE', 'POSFILE',
    'POST', 'PRE', 'PREPARE', 'RANGE', 'READPC', 'READS', 'RESETAT', 'RETURN_PC', 'RNGLOG', 'ROMPATCH', 'ROMREAD',
    'RWATCH', 'RWLOG', 'SAVE', 'SAVEAT', 'SAVENAME', 'SCRIPT', 'SEED', 'SEQ', 'SET', 'SETTLE', 'SFROM', 'SHADOW',
    'SHOTDELAY', 'SHOTEVERY', 'SHOTLAG', 'SHOTMSG', 'SHOTS', 'SLOT', 'SPCDUMP', 'SPINS', 'SRAMAT', 'SRM', 'SSADDR',
    'SSAT', 'SSCRIPT', 'SSFROM', 'SSROMPATCH', 'STALE', 'STEP', 'STO', 'STOPF', 'SWAP', 'SWF', 'TAIL', 'TAP',
    'TAPUNTIL', 'TARGET', 'TEST', 'TO', 'TOMSG', 'TRACE', 'UNTIL', 'VFRAMES', 'VHI', 'VLO', 'VMADD', 'VMDUMP',
    'VMSCREENS', 'VMWRAM', 'VRAMDUMP', 'VSTEP', 'WADDR', 'WAGON', 'WAITSONG', 'WARPEXIT', 'WARPLUA', 'WATCH',
    'WATCHR', 'WATCHW', 'WATCH_FMT', 'WATCH_WRAM', 'WAYPOINTS', 'WF', 'WFROM', 'WIPE', 'WIPEF', 'WLEN', 'WLOG', 'WR',
    'WRAMWATCH', 'WRAMWATCHBY', 'WRAMWATCHREAD', 'WRN', 'WSTART', 'WT', 'WW', 'WWATCH', 'WWFROM', 'WWRANGE',
)


def run(mesence, rom, lua, env_extra, dest, libdir, state):
    dest.mkdir()
    copy = dest / f'{dest.name}.sfc'
    shutil.copyfile(rom, copy)
    env = os.environ.copy()
    for key in LUA_ENV:
        env.pop(key, None)
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), **env_extra)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        dq5mesen.testrunner(str(mesence), str(copy), str(lua), '--Snes.DisableFrameSkipping=true',
                            env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    return dest


def bg_expect(rom, n):
    """dq5battlebg.build 와 같되 그림 뱅크를 22:CB35 의 즉값에서 읽는다(그림을 옮긴 롬)."""
    k, hi, _ = bg.entry(rom, n)
    bank = rom.u8(bgw.PICTURE_BANK_SITES[0]) << 16
    pa, pb = bank | rom.u16(bg.PICS + k), bank | rom.u16(bg.PICS + k + 2)
    bufb = bytearray(bg.picture(rom, pb)[0])
    bufb[0:32] = bytes(32)
    bufa = bg.picture(rom, pa)[0]
    x = k + (k >> 1)
    lbank = rom.u8(bgw.BANK_SITES['lists'][0]) << 16
    l1, l2, l3 = (lbank | rom.u16(bg.LISTS + x + i) for i in (0, 2, 4))
    low, o = bytearray(0x2000), 0
    for t, c in bg.tile_list(rom, l3):
        for _ in range(c):
            if o < 0x2000:
                low[o:o + 32] = bufa[t * 32:t * 32 + 32]
            o += 32
    tiles = {0x200 + i: bytes(low[i * 32:i * 32 + 32]) for i in range(256)}
    tiles.update({0x300 + i: bytes(bufb[i * 32:i * 32 + 32]) for i in range(256)})
    record, _ = bgw.read_palette(rom, rom.u8(bgw.BANK_SITES['palettes'][0]) << 16 | rom.u16(bg.PALS + k))
    pals = {(record['slot'] + i) & 15: row for i, row in enumerate(record['rows'])}
    m1 = (bg.map_list(rom, l1, hi) + [0] * 0x100)[:0x100]
    m2 = (bg.map_list(rom, l2, hi) + [0] * 0x100)[:0x100]
    return tiles, m1, m2, pals


def check_bg(name, rom_path, dump, orig_dump, edited=None):
    rom = Rom(rom_path.read_bytes())
    vram, cg = (dump / 'v01100.vram').read_bytes(), (dump / 'c01100.cgram').read_bytes()
    tiles, m1, m2, pals = bg_expect(rom, BG)
    # 아래 띠 타일($200~)에는 몬스터 그림자가 칠해지므로(형식 문서) 위 띠 타일맵이 쓰는 타일만 바이트로 견주고,
    # 아래 띠는 다른 타일 수만 남긴다.
    used = {v & 0x3FF for v in m1 + m2 if v}
    bad_tiles = [t for t in used if vram[(0x2000 + t * 16) * 2:][:32] != tiles[t]]
    lower = sum(vram[(0x2000 + t * 16) * 2:][:32] != tiles[t] for t in range(0x200, 0x300))
    words = lambda base: [vram[(base + i) * 2] | vram[(base + i) * 2 + 1] << 8 for i in range(0x100)]
    bad_map = sum(a != b for a, b in zip(words(0x0CC0), m1)) + sum(a != b for a, b in zip(words(0x04C0), m2))
    bad_pal = sum(cg[(p * 16 + 1 + j) * 2] | cg[(p * 16 + 1 + j) * 2 + 1] << 8 != c
                  for p, cs in pals.items() for j, c in enumerate(cs))
    require(not bad_tiles and not bad_map and not bad_pal,
            f'{name}: 타일 {len(bad_tiles)}·타일맵 {bad_map}·색 {bad_pal}개가 기대와 다름')
    result = {'case': name, 'tiles': len(used), 'tilemap': 512, 'colors': sum(map(len, pals.values())),
              'lower_band_tiles_differing': lower}
    if orig_dump is not None:
        ov, oc = (orig_dump / 'v01100.vram').read_bytes(), (orig_dump / 'c01100.cgram').read_bytes()
        t = 0x300 + BG_CELL
        slot = min(pals)
        at = (slot * 16 + 1) * 2
        require(vram[(0x2000 + t * 16) * 2:][:32] == edited != ov[(0x2000 + t * 16) * 2:][:32],
                f'{name}: 고친 타일 {t:03X} 이 게임에 없음')
        require(cg[at:at + 2] == b'\x1f\x00' != oc[at:at + 2], f'{name}: 고친 색이 게임에 없음')
        result['edited'] = {'tile': f'{t:03X}', 'color': f'팔레트 {slot} 1번 001F'}
    return result


def map_expect(rom, moved):
    """맵 01/05 의 (셀 버퍼, {CHR 번호: 슬롯}, CHR 뱅크, 니블 표). 옮긴 롬이면 블록·CHR·니블 자리를 즉값에서 읽는다."""
    saved = dq5map.BLOCK_BANK, dq5map.CHR_BANK
    try:
        if moved:
            dq5map.BLOCK_BANK = rom.u8(mgw.SITES['block_bank'][0])
            require(rom.u16(mgw.SITES['builder_start'][0]) == 0x8000, '블록 시작이 뱅크 첫머리가 아님')
        dq5map.CHR_BANK = rom.u8(mgw.SITES['chr_bank'][0])
        dec = dq5map.Decoder(rom, 0xBE)
        dec.chr_palette = rom.u8(mgw.SITES['chrpal_bank'][0]) << 16 | rom.u16(mgw.SITES['chrpal_addr'][0])
        dec.preload(*MAP)
        _, _, buf, _ = dec.decode(map_pointer(rom, *MAP))
        return bytes(buf), dict(dec.chr_map), dq5map.CHR_BANK
    finally:
        dq5map.BLOCK_BANK, dq5map.CHR_BANK = saved


def check_map(name, rom_path, dump, orig_dump, info):
    rom = Rom(rom_path.read_bytes())
    moved = name == 'map-moved'
    buf, chr_map, chr_bank = map_expect(rom, moved)
    wram, vram = (dump / 'at_01BA4C.bin').read_bytes(), (dump / 'at_01BA4C.vram').read_bytes()
    require(wram[0xBC:0xBE] == bytes(MAP), f'{name}: 맵이 {wram[0xBC]:02X}/{wram[0xBD]:02X}')
    cells = sum(a != b for a, b in zip(buf, wram[0xC000:0xC000 + len(buf)]))
    bad = [i for i, word in chr_map.items()
           if tile_at(vram, word) !=
           rom.d[lorom(mgw.chr_addr(chr_bank, i)):lorom(mgw.chr_addr(chr_bank, i)) + 32]]
    require(cells == 0 and not bad, f'{name}: 셀 버퍼 {cells}바이트·CHR {len(bad)}개가 기대와 다름')
    result = {'case': name, 'cell_bytes': len(buf), 'chr_slots': len(chr_map)}
    later = (dump / 'f00700.cgram')
    require(later.exists(), f'{name}: 700프레임 CGRAM 덤프가 없음')
    if True:
        cg = later.read_bytes()
        rows = rom_rows(rom)
        bad_c = sum(cg[0x20 + r * 32 + c * 2:0x22 + r * 32 + c * 2] != rows[r][c * 2:c * 2 + 2]
                    for r in range(7) for c in range(1, 16))
        require(bad_c == 0, f'{name}: BG 팔레트 1~7번 줄 색 {bad_c}개가 기대와 다름')
        result['colors'] = 7 * 15
    if name == 'map-rows':
        oc = (orig_dump / 'f00700.cgram').read_bytes()
        row = rows_index(Rom(original_rom_bytes(orig_dump))).index(MAP_ROW)
        got = [cg[0x20 + row * 32 + c * 2] | cg[0x21 + row * 32 + c * 2] << 8 for c in range(1, 16)]
        require(got == NEW_ROW[1:] and cg[0x20 + row * 32:0x40 + row * 32] != oc[0x20 + row * 32:0x40 + row * 32],
                f'{name}: 더한 줄 208 이 CGRAM {row + 1}번 줄에 없음')
        result['edited'] = {'row': f'줄 208 → CGRAM {row + 1}번 줄', 'base': f'{row_base(rom):06X}'}
    if name == 'map-inplace':
        slot = chr_map[MAP_CHR] & 0x3FF
        ov = (orig_dump / 'at_01BA4C.vram').read_bytes()
        require(tile_at(vram, slot) == STRIPE != tile_at(ov, slot),
                f'{name}: 고친 CHR 이 VRAM 에 없음')
        ow = (orig_dump / 'at_01BA4C.bin').read_bytes()
        result['cells_changed_from_original'] = sum(
            wram[0xC000 + i:0xC008 + i] != ow[0xC000 + i:0xC008 + i] for i in range(0, len(buf), 8))
        require(result['cells_changed_from_original'] > 0, f'{name}: 반전한 블록 {info["flipped_block"]} 이 셀에 없음')
        result['flipped_block'] = info['flipped_block']
        oc = (orig_dump / 'f00700.cgram').read_bytes()
        row = rows_index(rom).index(MAP_ROW)
        at = 0x20 + row * 32 + 2
        require(cg[at:at + 2] == b'\x1f\x00' != oc[at:at + 2], f'{name}: 고친 BG 색이 CGRAM 에 없음')
        result['edited'] = {'chr': f'{MAP_CHR:03X} → 슬롯 {slot:03X}', 'color': f'줄 {MAP_ROW}(CGRAM {row + 1}번 줄) 1번'}
    if moved:
        new = info['new_chr']
        require(new in chr_map, f'{name}: 새 CHR {new:03X} 을 맵이 쓰지 않음')
        slot = chr_map[new] & 0x3FF
        require(tile_at(vram, slot) == DOTS, f'{name}: 새 CHR 이 VRAM 에 없음')
        x, y = NEW_BLOCK_AT
        width = 68
        cell = wram[0xC000 + (y * width + x) * 8:0xC000 + (y * width + x) * 8 + 8]
        result['new'] = {'chr': f'{new:03X} → 슬롯 {slot:03X}', 'block': info['new_block'], 'cell_4_2': cell.hex(' ')}
    return result


def tile_at(vram, word):
    o = (CHR_VRAM + (word & 0x3FF)) * 32
    return vram[o:o + 32]


# 21/02 에서 긴 통로를 왕복해 무작위 전투를 붙이고(일지 2026-10-25-06), FLEE 동안 にげる. 그 뒤 A 가 명령 창을 연다.
WALK = {'PRE': 'b:4,wait:40', 'WAYPOINTS': '3,11;3,24;7,24;up:10;70,43;46,43', 'ROMPATCH': '156FF5=E2322B0121',
        'CHANGES': '99', 'MAXF': '3000', 'DUMPF': '700,2100,2900', 'FLEE': '900-1800'}
WALK_MAP = (0x21, 2)


def check_walk(rom_path, original, dump, orig_dump):
    """옮긴 롬의 전투 전(700)·にげる 뒤(2100)·명령 창(2900) CHR 슬롯이 기대값과 맞는 집합이 원본 게임과 같은지."""
    global MAP
    saved, MAP = MAP, WALK_MAP
    try:
        rom, orom = Rom(rom_path.read_bytes()), Rom(original.read_bytes())
        _, chr_map, bank = map_expect(rom, True)
        _, ochr, obank = map_expect(orom, False)
    finally:
        MAP = saved
    require(chr_map == ochr, '21/02 의 CHR 슬롯 배정이 원본과 다름')

    def bad(r, b, cm, path):
        v = path.read_bytes()
        return sorted(i for i, word in cm.items() if tile_at(v, word) != r.d[lorom(mgw.chr_addr(b, i)):][:32])

    base = bad(orom, obank, ochr, orig_dump / 'f02100.vram')
    w0, w1 = (dump / 'f00700.wram').read_bytes(), (dump / 'f02100.wram').read_bytes()
    require(w1[0xBC:0xBE] == bytes(WALK_MAP) and w0[0x1001] == 0 and w1[0x1001] != 0,
            '옮긴 롬에서 21/02 무작위 전투가 붙고 맵으로 돌아오지 않음')
    out = {'case': 'map-moved-battle', 'map': '21/02', 'chr_slots': len(chr_map), 'original_mismatch': len(base)}
    for frame in ('00700', '02100', '02900'):
        got = bad(rom, bank, chr_map, dump / f'f{frame}.vram')
        require(got == base, f'map-moved-battle {frame}: 기대와 다른 CHR {[f"{i:03X}" for i in got]}, '
                             f'원본 {[f"{i:03X}" for i in base]}')
        out[f'f{frame}'] = len(chr_map) - len(got)
    out['monster'] = f'{w1[0x1001]:02X}'
    return out


def check_field_row4(rom_path, dump, orig_dump):
    """필드 4번 줄(세트 목록의 줄 $34)도 옮긴 줄 표에서 읽는지. 색 1~3 은 물결이 덮으므로 4~15 만."""
    rom = Rom(rom_path.read_bytes())
    cg, oc = (dump / 'f00900.cgram').read_bytes(), (orig_dump / 'f00900.cgram').read_bytes()
    w = (dump / 'f00900.wram').read_bytes()
    require(w[0xBE] & 0x80 == 0, 'field-rows: 필드에 서지 않음')
    want = rom_rows(rom, [0x34])[0]
    require(cg[4 * 32 + 8:5 * 32] == want[8:] != oc[4 * 32 + 8:5 * 32],
            'field-rows: 4번 줄 색 4~15 가 옮긴 줄 52(고친 색)와 다르거나 원본 게임과 같음')
    return {'case': 'field-rows', 'row': '4번 줄 색 4~15 = 옮긴 표의 줄 52', 'base': f'{row_base(rom):06X}'}


def rows_index(rom):
    s = dq5map.palette_set(rom, *MAP)
    lst = 0x100000 | rom.u16(dq5map.PALSET_LISTS + s * 4)
    return [rom.u16(lst + r * 2) & 0x7FF for r in range(7)]


def original_rom_bytes(dump):
    """원본 롬 장면 폴더에 복사해 둔 롬."""
    return (dump / f'{dump.name}.sfc').read_bytes()


def row_base(rom):
    """BG 팔레트 줄 표 자리. 10:DE84 를 훅으로 바꾼 롬이면 10:FFE0 스텁의 롱 주소."""
    if rom.d[lorom(mgw.ROW_READ):lorom(mgw.ROW_READ) + 3] == bytes.fromhex('20 e0 ff'):
        return rom.u24(mgw.ROW_STUB + 3)
    return dq5map.PALETTES


def rom_rows(rom, rows=None):
    base = row_base(rom)
    return [rom.d[lorom(base + i * 32):lorom(base + i * 32) + 32] for i in (rows or rows_index(rom))]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default=Path('work/gfxwritecheck'))
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
        info = make_roms(original, out)
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True,
                                    timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        battle = {'FIELD': '341,56', 'BATTLE': '00:1', 'SETTLE': '800', 'DUMPF': '1100', 'MAXF': '2000'}
        enter = {'TO': ENTRY, 'AT': '01BA4C', 'SETTLE': '400', 'MAXF': '1500'}
        cases = [(name, rom, 'lua/dq5battledump.lua', battle) for name, rom in (
            ('bg-orig', original), ('bg-inplace', out / 'bg-inplace.sfc'), ('bg-repack', out / 'bg-repack.sfc'),
            ('bg-moved', out / 'bg-moved.sfc'), ('bg-tables', out / 'bg-tables.sfc'))]
        # 블록 포인터 표(7E:B000)는 게임을 시작할 때(00:A6BD) 만든다. 원본 롬으로 만든 선실 상태에는 옛 표가 남아
        # 블록을 옮긴 롬에서는 쓸 수 없으므로, 그 롬으로 전원부터 선실 상태를 새로 만든다.
        from dq5assets import ship_state
        ship_state(str(out / 'map-moved.sfc'), str(out / 'map-moved-state'), dict(os.environ, MESENCE=str(mesence)))
        moved_state = out / 'map-moved-state' / 'ship' / 'ship.mss'
        states = {}
        for name, rom in (('map-orig', original), ('map-inplace', out / 'map-inplace.sfc'),
                          ('map-moved', out / 'map-moved.sfc'), ('map-rows', out / 'map-rows.sfc')):
            cases.append((name, rom, ROOT / 'tools/lua/atpc.lua', enter))
            cases.append((name + '-late', rom, HERE / 'lua/dq5gfxdump.lua',
                          {'TO': ENTRY, 'DUMPF': '700', 'SETTLE': '400', 'MAXF': '1500'}))
            states[name] = states[name + '-late'] = moved_state if name == 'map-moved' else state
        field = {'FIELD': '341,56', 'SETTLE': '900', 'DUMPF': '900', 'MAXF': '1800'}
        for name, rom in (('field-orig', original), ('field-rows', out / 'map-rows.sfc')):
            cases.append((name, rom, HERE / 'lua/dq5gfxdump.lua', field))
        walklib = out / 'walklib'
        shutil.copytree(krlua, walklib)
        shutil.copyfile(ROOT / 'tools/lua/walk.lua', walklib / 'boot.lua')
        for name, rom in (('walk-orig', original), ('walk-moved', out / 'map-moved.sfc')):
            cases.append((name, rom, 'lua/dq5battleflee.lua', dict(WALK, DUMPER=str(HERE / 'lua/dq5gfxdump.lua'))))
            states[name] = moved_state if name == 'walk-moved' else state
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            dirs = dict(zip([c[0] for c in cases], pool.map(
                lambda c: run(mesence, c[1], HERE / c[2] if isinstance(c[2], str) else c[2], c[3], out / c[0],
                              walklib if c[0].startswith('walk') else libdir, states.get(c[0], state)), cases)))
        for name in ('map-orig', 'map-inplace', 'map-moved', 'map-rows'):
            for f in dirs[name + '-late'].glob('f00700.*'):
                shutil.copyfile(f, dirs[name] / f.name)
        results = [check_bg('bg-orig', original, dirs['bg-orig'], None)]
        results += [check_bg(name, out / f'{name}.sfc', dirs[name], dirs['bg-orig'], info['bg_tiles'][name])
                    for name in ('bg-inplace', 'bg-repack', 'bg-moved', 'bg-tables')]
        results += [
                   check_map('map-orig', original, dirs['map-orig'], None, info),
                   check_map('map-inplace', out / 'map-inplace.sfc', dirs['map-inplace'], dirs['map-orig'], info),
                   check_map('map-moved', out / 'map-moved.sfc', dirs['map-moved'], dirs['map-orig'], info),
                   check_map('map-rows', out / 'map-rows.sfc', dirs['map-rows'], dirs['map-orig'], info),
                   check_field_row4(out / 'map-rows.sfc', dirs['field-rows'], dirs['field-orig']),
                   check_walk(out / 'map-moved.sfc', original, dirs['walk-moved'], dirs['walk-orig'])]
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
