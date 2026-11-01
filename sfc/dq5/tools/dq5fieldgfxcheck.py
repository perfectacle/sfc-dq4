"""필드 그림·그룹 50 이상 맵 그림 쓰기와, 블록을 옮긴 롬의 문·상자·이어하기를 MesenCE 에서 확인한다.

시험 롬(원본에서 만듦)
  field-inplace  필드 타일 하나를 다른 타일로(RLE 가 원래 크기 안이라 제자리), 그 타일의 팔레트 니블을 2↔3번 줄로,
                 세계 0 의 2·3번 줄 1번 색(8벌)·세계 1·2 의 2번 줄 1번을 빨강, 물결 10단계의 1번 색을 초록
  field-moved    그 타일을 줄무늬로, 움직이는 타일 여덟 벌의 첫 타일을 점무늬로, --tiles-at 32:8000 --anim-at 33:8000.
                 8프레임마다 바뀌는 벌을 64프레임 동안 찍어 여덟 벌을 모두 본다
  high-inplace   50/50 이 쓰는 CHR 하나를 줄무늬로(dq5mapgfxwrite --set high)
  high-moved     새 CHR·새 블록을 더해 --chr-at 41:8000 --blocks-at 34:8000, 50/50 의 (4,4) 에 그 블록(dq5mapwrite)
  map-moved      dq5gfxwritecheck 와 같은 실내 맵 옮김 롬(블록 31:8000, CHR 40:8000)
  cont           블록만 31:9000 으로 옮긴 롬(블록 포인터가 원본과 달라지게)
장면
  필드(341,56) 900프레임, 50/50 에 들어가 01:BA4C. 실내 옮김 롬은 그 롬으로 만든 선실 상태에서 01/01 문을 지나
  01/00 으로, 01/02 상자를 열고(dq5chestcheck 의 입력), 원본 롬으로 같은 장면을 돌려 CHR 슬롯·셀 버퍼를 견준다.
  cont 는 선실 상태의 WRAM 으로 만든 SRAM 칸 1 을 두고 전원부터 A 를 눌러 이어하기로 들어간 뒤 블록 포인터 표를 본다.

  MESENCE=… python sfc/dq5/tools/dq5fieldgfxcheck.py rom/dq5.sfc --state work/state/ship.mss --out work/fieldgfxcheck
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
import dq5fieldgfxwrite as fgw  # noqa: E402
import dq5gfxwritecheck as gwc  # noqa: E402
import dq5map  # noqa: E402
from dq5map import Rom, lorom, map_pointer  # noqa: E402
import dq5mapgfxwrite as mgw  # noqa: E402
import dq5sram  # noqa: E402
import dq5mesen  # noqa: E402

STRIPE, DOTS = gwc.STRIPE, gwc.DOTS
FIELD_TILE_POS = (170, 26)          # (341,56) 부근 세계 0 블록. 이 블록 아래층 첫 타일을 고친다
ANIM_TILES = {4, 5, 20, 21} | set(range(454, 460))
HIGH_MAP, HIGH_ENTRY, HIGH_NEW_AT = (0x50, 0x50), '50/50,31,17,1', (4, 4)
# dq5warp 은 TEST 를 다 누르면 멈추므로 끝에 기다림을 붙여 덤프 프레임을 그 안에 둔다.
DOOR = {'TO': '01/01,13,8,1', 'TEST': 'up:24,wait:400', 'SETTLE': '150', 'DUMPF': '850', 'MAXF': '1500'}
CHEST = {'TO': '01/02,34,31', 'SETTLE': '150', 'DUMPF': '1700', 'MAXF': '2500',
         'TEST': 'up:8,wait:30,a:8,wait:60,down:6,wait:25,down:6,wait:25,down:6,wait:25,right:6,wait:25,a:8,'
                 'wait:200,a:4,wait:150,a:4,wait:150,b:4,wait:220,wait:400'}
CONT = {'PERIOD': '40', 'TAP': 'a', 'MAXF': '1300', 'DUMPF': '1200'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command(tool, *args):
    subprocess.run([sys.executable, str(HERE / tool), *map(str, args)], check=True, capture_output=True,
                   text=True, timeout=300)


def make_roms(original, out):
    rom = Rom(original.read_bytes())
    info = {}
    # 필드 타일
    src = out / 'field-src'
    doc = fgw.dump(rom, src)
    tiles = bytearray((src / 'tiles.bin').read_bytes())
    from dq5field import BLOCK_LOWER, WORLDS, block_number, block_tiles, rle
    w, e = (rle(rom, a)[0] for a in WORLDS[0])
    target = block_tiles(rom, BLOCK_LOWER, block_number(w, e, *FIELD_TILE_POS))[0]
    require(target not in ANIM_TILES, '고를 필드 타일이 움직이는 타일')
    for k in range(8):
        doc['palettes']['world0'][k][0] = doc['palettes']['world0'][k][15] = 0x001F
    for key in ('world1', 'world2'):
        doc['palettes'][key][0][0] = 0x001F
    for step in doc['wave']:
        step[0] = 0x03E0
    nib = doc['tile_palettes'][target]
    require(nib in (0, 1), f'타일 {target} 의 팔레트 니블이 {nib}')
    doc['tile_palettes'][target] = nib ^ 1
    o = fgw.original(rom)
    for u in range(fgw.TILES):
        t = tiles[u * 32:u * 32 + 32]
        if u in ANIM_TILES or t == tiles[target * 32:target * 32 + 32] or not any(t):
            continue
        trial = bytearray(tiles)
        trial[target * 32:target * 32 + 32] = t
        if len(fgw.encode_rle(fgw.tiles_to_planar(bytes(trial)))) <= len(o['rle']['tiles']):
            (src / 'tiles.bin').write_bytes(trial)
            info['field_inplace_tile'] = bytes(t)
            break
    else:
        raise ValueError('원래 크기 안에 드는 필드 타일 수정을 찾지 못함')
    (src / 'fieldgfx.json').write_text(json.dumps(doc), encoding='utf-8')
    command('dq5fieldgfxwrite.py', original, 'patch', src / 'fieldgfx.json', '-o', out / 'field-inplace.json')
    moved = out / 'field-moved-src'
    fgw.dump(rom, moved)
    tiles[target * 32:target * 32 + 32] = STRIPE
    (moved / 'tiles.bin').write_bytes(tiles)
    anim = bytearray((moved / 'anim.bin').read_bytes())
    for k in range(8):
        anim[k * 192:k * 192 + 32] = DOTS              # 여덟 벌 모두 첫 타일을 바꿔 어느 벌이 보여도 드러나게
    (moved / 'anim.bin').write_bytes(anim)
    mdoc = json.loads(json.dumps(doc))
    mdoc['tile_palettes'][target] = nib
    (moved / 'fieldgfx.json').write_text(json.dumps(mdoc), encoding='utf-8')
    command('dq5fieldgfxwrite.py', original, 'patch', moved / 'fieldgfx.json', '-o', out / 'field-moved.json',
            '--tiles-at', '32:8000', '--anim-at', '33:8000')
    info['field_tile'] = target
    # 그룹 50 이상
    hsrc = out / 'high-src'
    hdoc = mgw.dump(rom, hsrc, 'high')
    _, chr_map, _ = expect_map(rom, HIGH_MAP, False)
    info['high_chr'] = hchr = min(chr_map)
    chrs = bytearray((hsrc / 'chr.bin').read_bytes())
    chrs[hchr * 32:hchr * 32 + 32] = STRIPE
    (hsrc / 'chr.bin').write_bytes(chrs)
    (hsrc / 'mapgfx.json').write_text(json.dumps(hdoc), encoding='utf-8')
    command('dq5mapgfxwrite.py', original, 'patch', hsrc / 'mapgfx.json', '-o', out / 'high-inplace.json')
    hgrow = out / 'high-grow'
    gdoc = mgw.dump(rom, hgrow, 'high')
    new_chr = len(gdoc['chr_palettes'])
    (hgrow / 'chr.bin').write_bytes((hgrow / 'chr.bin').read_bytes() + DOTS)
    gdoc['chr_palettes'].append(gdoc['chr_palettes'][hchr])
    tmpl = next(b for b in gdoc['blocks'] if any(w & 0xFFF == hchr for w in b['words']))
    new_block = len(gdoc['blocks'])
    gdoc['blocks'].append({'w': 2, 'h': 2, 'flags': tmpl['flags'], 'b1': tmpl['b1'], 'attr': tmpl['attr'],
                           'words': [new_chr, new_chr | 0x4000, new_chr | 0x8000, new_chr | 0xC000]})
    (hgrow / 'mapgfx.json').write_text(json.dumps(gdoc), encoding='utf-8')
    command('dq5mapgfxwrite.py', original, 'patch', hgrow / 'mapgfx.json', '-o', out / 'high-grow.json',
            '--chr-at', '41:8000', '--blocks-at', '34:8000')
    command('dq5mapwrite.py', original, 'dump', '50', '50', '-o', hgrow / 'map5050.json')
    m = json.loads((hgrow / 'map5050.json').read_text(encoding='utf-8'))
    require(m['commands'][-1] == ['end'], '50/50 명령 끝이 end 가 아님')
    m['commands'][-1:] = [['block', new_block], ['put', *HIGH_NEW_AT], ['end']]
    (hgrow / 'map5050.json').write_text(json.dumps(m), encoding='utf-8')
    command('dq5mapwrite.py', original, 'patch', hgrow / 'map5050.json', '-o', out / 'high-5050.json')
    info.update(high_new_chr=new_chr, high_new_block=new_block)
    # 블록만 31:9000 으로
    csrc = out / 'cont-src'
    mgw.dump(rom, csrc)
    command('dq5mapgfxwrite.py', original, 'patch', csrc / 'mapgfx.json', '-o', out / 'cont.json',
            '--blocks-at', '31:9000')
    for name, lists in (('field-inplace', ['field-inplace.json']), ('field-moved', ['field-moved.json']),
                        ('high-inplace', ['high-inplace.json']), ('high-moved', ['high-grow.json', 'high-5050.json']),
                        ('cont', ['cont.json'])):
        command('dq5build.py', original, 'build', *(out / p for p in lists), '--size', '4',
                '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')
    info['cont_blocks'] = [a for _, a in mgw.read_blocks(rom)]
    return info


def expect_map(rom, bcbd, moved_normal):
    """맵의 (셀 버퍼, {CHR: 슬롯}, CHR 뱅크). 그룹 50 이상이면 high 자리를, 옮긴 롬이면 즉값에서 읽은 자리를 쓴다."""
    high = bcbd[0] >= 0x50
    st = mgw.SETS['high' if high else 'normal']
    sites = st['sites']
    saved = dq5map.BLOCK_BANK, dq5map.HIGH_BLOCKS
    try:
        bank = rom.u8(sites['block_bank'][0])
        start = bank << 16 | rom.u16(sites['builder_start'][0])
        if high:
            dq5map.HIGH_BLOCKS = start
        else:
            require(start & 0xFFFF == 0x8000, '실내 블록 시작이 뱅크 첫머리가 아님')
            dq5map.BLOCK_BANK = bank
        dec = dq5map.Decoder(rom, 0xBE, high)
        dec.chr_palette = rom.u8(sites['chrpal_bank'][0]) << 16 | rom.u16(sites['chrpal_addr'][0])
        dec.preload(*bcbd)
        _, _, buf, _ = dec.decode(map_pointer(rom, *bcbd))
        if high:
            buf = bytearray(buf)
            dq5map.high_marks(rom, *bcbd, buf)
        return bytes(buf), dict(dec.chr_map), rom.u8(sites['chr_bank'][0])
    finally:
        dq5map.BLOCK_BANK, dq5map.HIGH_BLOCKS = saved


def bad_chr(rom, chr_map, bank, vram):
    return sorted(i for i, word in chr_map.items()
                  if gwc.tile_at(vram, word) != rom.d[lorom(mgw.chr_addr(bank, i)):][:32])


def field_vram_tiles(vram):
    return [vram[0x4000 + t * 32:0x4000 + t * 32 + 32] for t in range(fgw.TILES)]


def cg_color(cg, row, c):
    return cg[(row * 16 + c) * 2] | cg[(row * 16 + c) * 2 + 1] << 8


def rows23(cg):
    """CGRAM 2·3번 줄 색 1~13(게임이 덮는 14·15 뺌)을 30색 목록의 번호로."""
    return {i: cg_color(cg, 2 + i // 15, 1 + i % 15) for i in range(30) if i not in fgw.CYCLED}


def check_palettes(name, cg, sets):
    got = rows23(cg)
    hit = [k for k, cs in enumerate(sets) if all(cs[i] == v for i, v in got.items())]
    require(hit, f'{name}: CGRAM 2·3번 줄 색 26개가 롬의 어느 벌과도 다름')
    return hit[0]


def tilemap_words(vram, tile):
    """BG 타일맵(아래층 VRAM 0~FFF, 위층 1000~1FFF 바이트)에서 그 타일을 쓰는 칸의 (층, 워드)."""
    out = []
    for base, upper in ((0, False), (0x1000, True)):
        for i in range(0x800):
            w = vram[base + i * 2] | vram[base + i * 2 + 1] << 8
            if w & 0x3FF == tile:
                out.append((upper, w))
    return out


def check_field(name, rom_path, dumps, orig_dump, info):
    """dumps: 필드 덤프 폴더와 프레임 목록. 첫 프레임으로 타일·색·타일맵을, 모든 프레임으로 움직이는 타일 벌을 본다."""
    from dq5field import tile_word
    rom = Rom(rom_path.read_bytes())
    o = fgw.current(rom)
    dump, frames = dumps
    vram, cg = (dump / f'f{frames[0]}.vram').read_bytes(), (dump / f'f{frames[0]}.cgram').read_bytes()
    got = field_vram_tiles(vram)
    want = [o['tiles'][t * 32:t * 32 + 32] for t in range(fgw.TILES)]
    bad = [t for t in range(fgw.TILES) if t not in ANIM_TILES and got[t] != want[t]]
    require(not bad, f'{name}: 필드 타일 {len(bad)}개가 기대와 다름 {bad[:8]}')
    sets = o['anim_sets']                      # 02:ACE7 의 AND 와 벌 주소 표대로(벌 수를 바꾼 롬도)
    seen = set()
    for f in frames:
        shown = b''.join(field_vram_tiles((dump / f'f{f}.vram').read_bytes())[454:460])
        require(shown in sets, f'{name}: {f}프레임 움직이는 타일 454~459 가 {len(sets)}벌 어디와도 다름')
        seen.add(sets.index(shown))
    pal_set = check_palettes(name, cg, o['palettes']['world0'])
    wave = (cg_color(cg, 4, 1), cg_color(cg, 4, 2), cg_color(cg, 4, 3))
    require(list(wave) in o['wave'], f'{name}: 4번 줄 색 1~3 이 물결 표의 어느 단계와도 다름')
    t = info['field_tile']
    words = tilemap_words(vram, t)
    require(words, f'{name}: 타일 {t} 을 쓰는 타일맵 칸이 없음')
    wrong = [w for upper, w in words if w & 0x1FFF != tile_word(rom, t, upper) & 0x1FFF]
    require(not wrong, f'{name}: 타일 {t} 칸의 팔레트가 니블 표와 다름 {[f"{w:04X}" for w in wrong[:4]]}')
    out = {'case': name, 'tiles': fgw.TILES - len(ANIM_TILES), 'anim_sets_seen': sorted(seen),
           'palette_set': pal_set, 'wave': f'{wave[0]:04X}', 'tilemap_cells_of_tile': len(words)}
    if orig_dump is not None:
        ov, oc = (orig_dump / f'f{frames[0]}.vram').read_bytes(), (orig_dump / f'f{frames[0]}.cgram').read_bytes()
        edited = info['field_inplace_tile'] if name == 'field-inplace' else STRIPE
        require(got[t] == edited != field_vram_tiles(ov)[t], f'{name}: 고친 타일 {t} 이 VRAM 에 없음')
        for row in (2, 3):
            require(cg_color(cg, row, 1) == 0x001F != cg_color(oc, row, 1), f'{name}: 고친 {row}번 줄 1번 색이 없음')
        require(wave[0] == 0x03E0 != cg_color(oc, 4, 1), f'{name}: 고친 물결 색이 없음')
        out['edited'] = {'tile': t, 'colors': '2·3번 줄 1번 001F, 4번 줄 1번 03E0'}
        if name == 'field-inplace':
            ow = dict(tilemap_words(ov, t))
            require(all(ow.get(u) != w for u, w in words), f'{name}: 고친 팔레트 니블이 타일맵에 없음')
            out['edited']['tile_palette'] = f'타일 {t} 칸 {len(words)}개의 팔레트 줄이 바뀜'
        if name == 'field-moved':
            require(seen == set(range(len(sets))), f"{name}: 64프레임 동안 본 벌이 {sorted(seen)}")
            require(got[454] == DOTS != field_vram_tiles(ov)[454], f'{name}: 고친 움직이는 타일이 VRAM 에 없음')
            out['anim_tile_454'] = '점무늬(여덟 벌 모두 옮긴 자료와 같음)'
    return out


def check_world(name, rom_path, dump, orig_dump, world, frame):
    """세계 1·2 의 2·3번 줄 색이 그 세계 한 벌과 같고, 고친 2번 줄 1번이 원본 게임과 다른지."""
    rom = Rom(rom_path.read_bytes())
    cg = (dump / f'f{frame}.cgram').read_bytes()
    w = (dump / f'f{frame}.wram').read_bytes()
    require(w[0x1949] == world and w[0xBE] & 0x80 == 0, f'{name}: 세계 {world} 필드에 서지 않음')
    check_palettes(name, cg, fgw.current(rom)['palettes'][f'world{world}'])
    out = {'case': name, 'colors': 26}
    if orig_dump is not None:
        oc = (orig_dump / f'f{frame}.cgram').read_bytes()
        require(cg_color(cg, 2, 1) == 0x001F != cg_color(oc, 2, 1), f'{name}: 고친 2번 줄 1번 색이 없음')
        out['edited'] = '2번 줄 1번 001F'
    return out


def check_high(name, rom_path, dump, orig_dump, info):
    rom = Rom(rom_path.read_bytes())
    buf, chr_map, bank = expect_map(rom, HIGH_MAP, False)
    wram, vram = (dump / 'at_01BA4C.bin').read_bytes(), (dump / 'at_01BA4C.vram').read_bytes()
    require(wram[0xBC:0xBE] == bytes(HIGH_MAP), f'{name}: 맵이 {wram[0xBC]:02X}/{wram[0xBD]:02X}')
    cells = sum(a != b for a, b in zip(buf, wram[0xC000:0xC000 + len(buf)]))
    bad = bad_chr(rom, chr_map, bank, vram)
    require(cells == 0 and not bad, f'{name}: 셀 버퍼 {cells}바이트·CHR {[f"{i:03X}" for i in bad]} 가 기대와 다름')
    out = {'case': name, 'cell_bytes': len(buf), 'chr_slots': len(chr_map)}
    if name == 'high-inplace':
        slot = chr_map[info['high_chr']]
        ov = (orig_dump / 'at_01BA4C.vram').read_bytes()
        require(gwc.tile_at(vram, slot) == STRIPE != gwc.tile_at(ov, slot), f'{name}: 고친 CHR 이 VRAM 에 없음')
        out['edited'] = f'CHR {info["high_chr"]:03X} → 슬롯 {slot & 0x3FF:03X}'
    if name == 'high-moved':
        new = info['high_new_chr']
        require(new in chr_map and gwc.tile_at(vram, chr_map[new]) == DOTS, f'{name}: 새 CHR 이 VRAM 에 없음')
        out['new'] = {'chr': f'{new:03X} → 슬롯 {chr_map[new] & 0x3FF:03X}', 'block': info['high_new_block']}
    return out


def check_scene(name, bcbd, moved_rom, original, dump, orig_dump, frame):
    """옮긴 롬과 원본 롬의 같은 장면 뒤 CHR 슬롯이 기대와 다른 집합·셀 버퍼가 같은지."""
    rom, orom = Rom(moved_rom.read_bytes()), Rom(original.read_bytes())
    _, cm, bank = expect_map(rom, bcbd, True)
    _, ocm, obank = expect_map(orom, bcbd, False)
    require(cm == ocm, f'{name}: CHR 슬롯 배정이 원본과 다름')
    w, ow = (dump / f'f{frame}.wram').read_bytes(), (orig_dump / f'f{frame}.wram').read_bytes()
    require(w[0xBC:0xBE] == bytes(bcbd) == ow[0xBC:0xBE], f'{name}: 끝 맵이 {w[0xBC]:02X}/{w[0xBD]:02X}')
    got = bad_chr(rom, cm, bank, (dump / f'f{frame}.vram').read_bytes())
    base = bad_chr(orom, ocm, obank, (orig_dump / f'f{frame}.vram').read_bytes())
    require(got == base, f'{name}: 기대와 다른 CHR {got}, 원본 {base}')
    size = len(expect_map(orom, bcbd, False)[0])
    # 셀 +0 bit0 은 걸어 다니는 인물이 선 칸이라(두 실행의 난수에 따라 다름) 빼고 견준다.
    diff = [i for i in range(size) if (w[0xC000 + i] ^ ow[0xC000 + i]) & (0xFE if i % 8 == 0 else 0xFF)]
    require(not diff, f'{name}: 셀 버퍼가 원본 장면과 {len(diff)}바이트 다름')
    return {'case': name, 'map': f'{bcbd[0]:02X}/{bcbd[1]:02X}', 'chr_slots': len(cm),
            'chr_equal': len(cm) - len(got), 'original_mismatch': len(base), 'cell_bytes_equal': size}


def make_sram(rom_path, wram, path):
    rom = rom_path.read_bytes()
    magic = rom[lorom(0x258000):lorom(0x258000) + 14]
    s = bytearray(dq5sram.SIZE)
    s[0:14] = s[dq5sram.MAGIC_COPY:dq5sram.MAGIC_COPY + 14] = magic
    s[dq5sram.USED] = 0x01
    s[dq5sram.STATUS] = 0xC0
    block = bytearray(wram[0x2000:0x2000 + dq5sram.SLOT_SIZE])
    block[dq5sram.SUM_AT:dq5sram.SUM_AT + 2] = dq5sram.checksum(block).to_bytes(2, 'little')
    s[dq5sram.SLOTS[0]:dq5sram.SLOTS[0] + dq5sram.SLOT_SIZE] = block
    path.write_bytes(s)


def check_cont(rom_path, dump, info):
    w = (dump / f'f{int(CONT["DUMPF"]):05d}.wram').read_bytes()
    want = [a & 0xFFFF for a in info['cont_blocks']]
    rom = Rom(rom_path.read_bytes())
    start = rom.u16(mgw.SITES['builder_start'][0])
    moved = [(a - 0x8000 + start) & 0xFFFF for a in want]
    got = [w[0xB000 + i * 2] | w[0xB001 + i * 2] << 8 for i in range(len(want))]
    require(w[0x2001:0x2005] != bytes(4) and w[0xBE] & 0x80, '이어하기로 실내 맵에 들어가지 않음')
    require(got == moved, f'cont: 블록 포인터 표가 옮긴 자리와 다름(첫 값 {got[0]:04X}, 기대 {moved[0]:04X})')
    return {'case': 'cont', 'map': f'{w[0xBC]:02X}/{w[0xBD]:02X}', 'block_pointers': len(got),
            'first': f'{got[0]:04X}', 'original_first': f'{want[0]:04X}'}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default=Path('work/fieldgfxcheck'))
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
        gwc.make_roms(original, out / 'gfx')
        moved = out / 'gfx' / 'map-moved.sfc'
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True,
                                    timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        from dq5assets import SAVES, ship_state
        ship_state(str(moved), str(out / 'moved-state'), dict(os.environ, MESENCE=str(mesence)))
        moved_state = out / 'moved-state' / 'ship' / 'ship.mss'
        frames = [f'{900 + i * 8:05d}' for i in range(9)]
        field = {'FIELD': '341,56', 'SETTLE': '900', 'DUMPF': ','.join(str(int(f)) for f in frames), 'MAXF': '1800'}
        world = {w: {'FIELD': '50,28', 'POKE': f'7E1949={w:02X}', 'SETTLE': '900', 'DUMPF': '900', 'MAXF': '1800'}
                 for w in (1, 2)}
        high = {'TO': HIGH_ENTRY, 'AT': '01BA4C', 'SETTLE': '400', 'MAXF': '1500'}
        gfx = HERE / 'lua/dq5gfxdump.lua'
        cases = [('field-orig', original, gfx, field, state), ('field-inplace', out / 'field-inplace.sfc', gfx, field, state),
                 ('field-moved', out / 'field-moved.sfc', gfx, field, state),
                 *[(f'world{w}-{k}', rom, gfx, world[w], state) for w in (1, 2)
                   for k, rom in (('orig', original), ('inplace', out / 'field-inplace.sfc'))],
                 ('high-orig', original, ROOT / 'tools/lua/atpc.lua', high, state),
                 ('high-inplace', out / 'high-inplace.sfc', ROOT / 'tools/lua/atpc.lua', high, state),
                 ('high-moved', out / 'high-moved.sfc', ROOT / 'tools/lua/atpc.lua', high, state),
                 ('door-orig', original, gfx, DOOR, state), ('door-moved', moved, gfx, DOOR, moved_state),
                 ('chest-orig', original, gfx, CHEST, state), ('chest-moved', moved, gfx, CHEST, moved_state)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            dirs = dict(zip([c[0] for c in cases], pool.map(
                lambda c: gwc.run(mesence, c[1], c[2], c[3], out / c[0], libdir, c[4]), cases)))
        # 이어하기: cont 롬으로 만든 선실 상태의 WRAM 을 SRAM 칸 1 에 두고 전원부터.
        cont = out / 'cont.sfc'
        ship_state(str(cont), str(out / 'cont-state'), dict(os.environ, MESENCE=str(mesence)))
        seqlib = out / 'seqlib'
        shutil.copytree(krlua, seqlib)
        shutil.copyfile(ROOT / 'tools/lua/seqboot.lua', seqlib / 'boot.lua')
        wram_dir = gwc.run(mesence, cont, gfx, {'DUMPF': '5', 'MAXF': '10', 'SEQ': 'wait:20'}, out / 'cont-wram',
                           seqlib, out / 'cont-state' / 'ship' / 'ship.mss')
        name = f'cont-{out.name}'
        dest = out / 'cont-run'
        dest.mkdir()
        copy = dest / f'{name}.sfc'
        shutil.copyfile(cont, copy)
        srm = Path(SAVES) / f'{name}.srm'
        make_sram(cont, (wram_dir / 'f00005.wram').read_bytes(), srm)
        env = dict(os.environ, LIBDIR=str(krlua), SHOT_DIR=str(dest), **CONT)
        for key in ('STATE', 'TO', 'FIELD', 'SEQ'):
            env.pop(key, None)
        with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
            dq5mesen.testrunner(str(mesence), str(copy), str(gfx), '--Snes.DisableFrameSkipping=true',
                                env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        srm.unlink(missing_ok=True)
        results = [check_field('field-orig', original, (dirs['field-orig'], frames), None, info)]
        results += [check_field(n, out / f'{n}.sfc', (dirs[n], frames), dirs['field-orig'], info)
                    for n in ('field-inplace', 'field-moved')]
        for w in (1, 2):
            results.append(check_world(f'world{w}-orig', original, dirs[f'world{w}-orig'], None, w, '00900'))
            results.append(check_world(f'world{w}-inplace', out / 'field-inplace.sfc', dirs[f'world{w}-inplace'],
                                       dirs[f'world{w}-orig'], w, '00900'))
        results += [check_high(n, out / f'{n}.sfc' if n != 'high-orig' else original, dirs[n], dirs['high-orig'], info)
                    for n in ('high-orig', 'high-inplace', 'high-moved')]
        results.append(check_scene('door', (1, 0), moved, original, dirs['door-moved'], dirs['door-orig'], '00850'))
        results.append(check_scene('chest', (1, 2), moved, original, dirs['chest-moved'], dirs['chest-orig'], '01700'))
        results.append(check_cont(cont, dest, info))
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
