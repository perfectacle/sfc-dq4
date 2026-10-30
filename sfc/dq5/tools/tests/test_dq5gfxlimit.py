"""필드 타일 1,024개 늘리기·세계 0 의 2·3번 줄 벌 늘리기·실내 BG 팔레트 세트 늘리기를 원본 롬 없이 확인한다."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import dq5field  # noqa: E402
import dq5fieldgfxwrite as fgw  # noqa: E402
import dq5fieldtables as ft  # noqa: E402
import dq5map  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
import dq5mapgfxwrite as mgw  # noqa: E402
import dq5palsetwrite as psw  # noqa: E402
from dq5mapgfxwrite import encode_block  # noqa: E402
from w65816 import Cpu  # noqa: E402


def put(data, addr, raw):
    o = lorom(addr)
    data[o:o + len(raw)] = raw


def apply(data, manifest):
    d = bytearray(data) + bytes(max(0, 0x400000 - len(data)))
    for w in manifest['writes']:
        put(d, int(w['at'].replace(':', ''), 16), bytes.fromhex(w['hex']))
    return bytes(d)


ORIGINAL_TIMES = ((0, 4), (1, 3), (2, 2), (0xEE, 3), (0xEF, 4), (0xF0, 5), (0xF1, 6), (0xF2, 7), (0x1FD, 6), (0x1FE, 5))


def field_rom():
    """dq5fieldgfxwrite 가 원래 롬으로 보는 자리만 채운 롬."""
    d = bytearray(0x200000)
    for sites in fgw.SITES.values():
        for at, want in sites:
            put(d, at, want)
    for at, want in fgw.ANIM_SITES.values():
        put(d, at, want)
    put(d, fgw.LOAD_SITE, fgw.LOAD_ORIG)
    put(d, fgw.PALETTE_READ, fgw.PALETTE_READ_ORIG)
    put(d, fgw.BLOCK_READ, fgw.BLOCK_READ_ORIG)
    put(d, fgw.REDRAW_SITE, fgw.REDRAW_ORIG)
    put(d, fgw.REDRAW_RTL, b'\x6b')
    put(d, fgw.WATER_SITE, fgw.WATER_ORIG)
    for at, want in (fgw.SEARCH_SITE, fgw.PTR_SITE, fgw.NIGHT_SITE, fgw.PAL_BANK_SITE, fgw.WAVE_SITE,
                     *fgw.ATTR_SITES.items(), fgw.REFRESH_SITE, *(x for pair in fgw.W12_LOAD.values() for x in pair)):
        put(d, at, want)
    for i, (lo, k) in enumerate(ORIGINAL_TIMES):
        put(d, fgw.TIMES + i * 3, lo.to_bytes(2, 'little') + bytes([k * 2]))
    for k in range(8):
        put(d, fgw.TIME_PTRS + k * 2, (0xA1D5 + k * 60).to_bytes(2, 'little'))
        put(d, 0x01A1D5 + k * 60, bytes([k + 1, 0]) * 30)
    put(d, fgw.ANIM_TABLE, fgw.encode_anim_table(8))
    tiles = bytes((i // 32) & 0xFF if i % 3 else 0 for i in range(fgw.TILES * 32))
    put(d, fgw.FIELD_CHR, fgw.encode_rle(fgw.tiles_to_planar(tiles)))
    put(d, fgw.ANIM, fgw.encode_rle(bytes(fgw.ANIM_BYTES)))
    put(d, fgw.TILE_ATTR, bytes(i & 0x7F for i in range(fgw.TILES)))
    return bytes(d)


def old_block_hook(table):
    """블록 표 읽기를 제자리에서 바꾸기 전 판이 00:BC80·BC8D 의 JSL 로 부르던 훅(9·10번째 비트를 마스크 둘로 읽음)."""
    return (b'\xbf' + fgw.long_addr(table) + b'\x39\xa4\xbc' + b'\xc9\x01' + b'\xa9\x00' + b'\x2a' + b'\xeb'
            + b'\xbf' + fgw.long_addr(table) + b'\x39\x9c\xbc' + b'\xc9\x01' + b'\xeb' + b'\x2a' + b'\x6b')


def old_grow_rom(data, at):
    """지금 판으로 타일을 늘린 롬을 그 전 판(블록 훅 둘·니블 훅 넷, 칸 비트 표·팔레트 표 없음)이 쓰던 꼴로 바꾼다.
    고르기 표·니블 표·속성은 그대로 옮긴다."""
    new, old = fgw.grow_layout(at), fgw.grow_layout(at, block_hooks=True)
    d = bytearray(data)
    o = lorom(new['table'])
    tables = bytes(d[o:o + new['tile_bits'] - new['table']])
    o = lorom(at)
    d[o:o + new['rles'] - at] = bytes(new['rles'] - at)
    put(d, at, fgw.grow_load_hook(old['table'], old['dma']) + fgw.nib_hook(old['tables'], wide=True)
        + old_block_hook(dq5field.BLOCK_LOWER + 4) + old_block_hook(dq5field.BLOCK_UPPER + 4)
        + fgw.redraw_hook(old['dma']) + fgw.dma_sub(old['table']) + tables)
    put(d, fgw.LOAD_SITE + 1, fgw.long_addr(old['load']))
    put(d, fgw.PALETTE_READ, fgw.PALETTE_READ_ORIG)
    put(d, fgw.BLOCK_READ, fgw.BLOCK_READ_ORIG)
    for site in fgw.NIB_SITES:
        put(d, site, b'\x22' + fgw.long_addr(old['nib']))
    for site, key, dp in ((0x00BC80, 'block_lower', 0x95), (0x00BC8D, 'block_upper', 0x97)):
        put(d, site, b'\x22' + fgw.long_addr(old[key]) + bytes([0x85, dp]) + b'\xea' * 7)
    put(d, fgw.REDRAW_SITE + 1, fgw.long_addr(old['redraw']))
    put(d, 0x00BCBE, fgw.long_addr(old['attrs']))
    return bytes(d)


class TileGrowTests(unittest.TestCase):
    def setUp(self):
        self.data = field_rom()
        self.rom = Rom(self.data)
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.doc = fgw.dump(self.rom, self.tmp.name)
        base = (self.folder / 'tiles.bin').read_bytes()
        self.extra = bytes((k * 7 + i) & 0xFF for k in range(300) for i in range(32))
        (self.folder / 'tiles.bin').write_bytes(base + self.extra)
        self.doc['tile_palettes'] = self.doc['tile_palettes'] + [k % 16 for k in range(300)]

    def tearDown(self):
        self.tmp.cleanup()

    def test_needs_places_and_rejects_bad_sizes(self):
        with self.assertRaisesRegex(ValueError, '--worlds-at.*--extra-at'):
            fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000)
        self.doc['tile_palettes'].pop()
        with self.assertRaisesRegex(ValueError, '타일 수와 같게'):
            fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000, extra_at=0x358000)
        self.doc['tile_palettes'].append(0)
        (self.folder / 'tiles.bin').write_bytes((self.folder / 'tiles.bin').read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, '512~1024'):
            fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000, extra_at=0x358000)
        (self.folder / 'tiles.bin').write_bytes(bytes(32 * 1025))
        with self.assertRaisesRegex(ValueError, '512~1024'):
            fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000, extra_at=0x358000)

    def test_hooks_and_current_roundtrip(self):
        m = fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000, extra_at=0x358000)
        sites = {w['at']: w for w in m['writes']}
        lay = fgw.grow_layout(0x348000)
        self.assertEqual(sites['01:A4A7']['hex'], f'22 {fgw.long_addr(lay["load"]).hex(" ")} 80 04 ea ea ea ea')
        self.assertEqual(sites['00:BC6D']['hex'], fgw.block_read(lay['tile_bits']).hex(' '))
        self.assertEqual(sites['00:BBAC']['hex'], fgw.palette_fast(lay['palettes'], lay['palettes'] + 1024).hex(' '))
        self.assertNotIn('00:BBB4', sites)
        self.assertEqual(sites['01:B4D5']['hex'], f'5c {fgw.long_addr(lay["redraw"]).hex(" ")}')
        self.assertEqual(fgw.redraw_hook(0)[-7:], bytes.fromhex('f4 b9 8a 5c 0a b5 01'))
        self.assertEqual((sites['00:BCB0']['hex'], sites['00:BCB7']['hex']), ('29 ff 03', '29 ff 03'))
        self.assertEqual(sites['00:BCBD']['hex'], f'bf {fgw.long_addr(lay["attrs"]).hex(" ")}')
        self.assertEqual(sites['35:8000']['hex'], self.extra.hex(' '))
        rom = Rom(apply(self.data, m))
        cur = fgw.current(rom)
        tiles, nib = cur['worlds']['world0']
        self.assertEqual((len(tiles) // 32, len(nib)), (812, 812))
        self.assertEqual(tiles, (self.folder / 'tiles.bin').read_bytes())
        self.assertEqual(nib, self.doc['tile_palettes'])
        self.assertEqual(cur['worlds']['world1'], cur['worlds']['world0'])
        # 늘린 타일의 속성은 따로 주지 않으면 타일 - 512 의 것(원래 AND #$01FF 와 같음)
        self.assertEqual(cur['tile_attributes'], self.doc['tile_attributes'] * 2)
        # 세 세계의 니블이 같으면 디코더는 00:BBAC 가 읽는 타일마다 1바이트 표로 타일 812 의 팔레트를 낸다(아래층은 3비트).
        self.assertEqual(dq5field.tile_word(rom, 811, True) >> 10 & 7, (299 % 16 + 2) & 7)
        self.assertEqual(dq5field.tile_word(rom, 811, False), 811 | (((299 % 16) & 7) * 4 + 8) << 8)
        self.assertEqual(dq5field.tile_word(rom, 811, True, 2), dq5field.tile_word(rom, 811, True, 0))
        # 이 롬에는 니블 표가 없어 2A:D712 를 내지 않고 멈춘다.
        with self.assertRaises(ValueError):
            dq5field.nibble_table(rom)
        self.assertEqual(m['rom_size'], 2)

    def test_old_block_hook_rom(self):
        """그 전 판(00:BC80·BC8D 의 JSL 블록 훅)으로 만든 롬도 10번째 비트·고르기 표·니블 표를 읽는다."""
        d = bytearray(apply(self.data, fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000,
                                                 extra_at=0x358000)))
        put(d, dq5field.BLOCK_LOWER + 7 * 5, ft.encode_block(bytes(5), [811, 0, 0, 0], wide=True))
        new, old = Rom(bytes(d)), Rom(old_grow_rom(bytes(d), 0x348000))
        self.assertEqual((old.u8(dq5field.BLOCK_READ_SITE), old.u8(dq5field.BLOCK_HOOK_SITE)), (0x8B, 0x22))
        self.assertEqual(fgw.rom_layout(old), fgw.grow_layout(0x348000, block_hooks=True))
        self.assertEqual(fgw.rom_layout(new), fgw.grow_layout(0x348000))
        self.assertTrue(dq5field.wide_tiles(old))
        self.assertEqual(dq5field.block_tiles(old, dq5field.BLOCK_LOWER, 7), [811, 0, 0, 0])   # 9비트로 읽으면 299
        self.assertEqual((fgw.tile_counts(old), ft.tile_limit(old)), ([812] * 3, 811))
        cur_old, cur_new = fgw.current(old), fgw.current(new)
        self.assertEqual(cur_old['worlds'], cur_new['worlds'])
        self.assertEqual(cur_old['tile_attributes'], cur_new['tile_attributes'])
        for t in (0, 511, 512, 811):
            for upper in (True, False):
                self.assertEqual(dq5field.tile_word(old, t, upper), dq5field.tile_word(new, t, upper))

    def test_wide_nibble_hook_clears_high_byte(self):
        """00:BBAC 는 LDA $94 / LSR 의 윗바이트를 XBA 로 타일맵 워드에 넣으므로 넓은 훅은 윗바이트를 0 으로 돌려준다."""
        narrow, wide = fgw.nib_hook(0x123456), fgw.nib_hook(0x123456, wide=True)
        self.assertEqual(narrow[dq5field.NIB_HOOK_STRIDE], 0x18)
        self.assertEqual(wide[dq5field.NIB_HOOK_STRIDE], 0x0A)
        self.assertEqual(wide[dq5field.NIB_HOOK_TABLE:dq5field.NIB_HOOK_TABLE + 3], fgw.long_addr(0x123456))
        self.assertEqual(wide[-6:], bytes.fromhex('fa eb 29 00 eb 6b'))

    def test_world_extras_and_bank_crossing(self):
        w1 = bytearray((self.folder / 'tiles.bin').read_bytes()[:fgw.TILES * 32])
        w1 += bytes([0x5A]) * (32 * 512)
        (self.folder / 'w1.bin').write_bytes(w1)
        self.doc['worlds'] = {'world1': {'tiles_file': 'w1.bin', 'tile_palettes': [3] * 1024}}
        m = fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000, extra_at=0x35C000)
        notes = [w for w in m['writes'] if w['note'].startswith('늘린 타일')]
        # 세계 0 의 9,600바이트는 35:C000 에, 세계 1 의 16KB 는 뱅크 끝을 넘으므로 36:8000 에
        self.assertEqual([w['at'] for w in notes], ['35:C000', '36:8000'])
        rom = Rom(apply(self.data, m))
        cur = fgw.current(rom)
        self.assertEqual(cur['worlds']['world1'], (bytes(w1), [3] * 1024))
        self.assertEqual(cur['worlds']['world2'], cur['worlds']['world0'])
        # 세계 1 의 니블이 다르면 니블 훅 대신 00:BBAC 를 $1949 로 세계마다 워드 표를 고르는 코드로 바꾼다.
        # 표 16KB 는 늘린 타일 뒤(36:C000)에 둔다.
        self.assertEqual(rom.d[lorom(fgw.PALETTE_READ):lorom(fgw.PALETTE_READ) + 38],
                         fgw.palette_worlds(0x36C000, 0x36E000))
        self.assertEqual([w['at'] for w in m['writes'] if w['note'].startswith('세계마다 타일맵 워드 표')], ['36:C000'])
        for upper in (True, False):
            self.assertEqual(dq5field.tile_word(rom, 811, upper, 1), 811 | (3 * 4 + 8) << 8)
        self.assertEqual(dq5field.tile_word(rom, 811, True, 0), 811 | (299 % 16 * 4 + 8) << 8)
        with self.assertRaisesRegex(ValueError, '겹침'):
            fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x358000, extra_at=0x358100)
        with self.assertRaisesRegex(ValueError, '30~7D'):
            fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000, extra_at=0x7E8000)

    def world_doc(self, key, extra, nib):
        (self.folder / f'{key}.bin').write_bytes((self.folder / 'tiles.bin').read_bytes()[:fgw.TILES * 32] + extra)
        self.doc.setdefault('worlds', {})[key] = {'tiles_file': f'{key}.bin', 'tile_palettes': nib}

    def word_notes(self, m):
        return [w['at'] for w in m['writes'] if w['note'].startswith('세계마다 타일맵 워드 표')]

    def test_word_table_same_bytes_as_tiles(self):
        # 워드 표 16KB 와 바이트가 같은 늘린 타일 512개를 세계 1 에 두어도 타일 주소와 표 주소가 따로다.
        nib0 = self.doc['tile_palettes']
        nib1 = nib0[:fgw.TILES] + [3] * fgw.TILES
        words = b''.join(fgw.palette_world_words([nib0, nib1, nib0, nib0]))
        self.world_doc('world1', words, nib1)
        m = fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000, extra_at=0x358000)
        rom = Rom(apply(self.data, m))
        self.assertEqual(fgw.current(rom)['worlds']['world1'][0][fgw.TILES * 32:], words)
        self.assertEqual(self.word_notes(m), ['36:8000'])
        self.assertEqual(dq5field.tile_word(rom, 1023, True, 1), 1023 | (3 * 4 + 8) << 8)

    def test_word_table_moves_to_next_bank(self):
        nib1 = list(self.doc['tile_palettes'])
        nib1[600] ^= 1
        self.world_doc('world1', self.extra, nib1)
        m = fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000, extra_at=0x35C000)
        # 늘린 타일 9,600바이트(35:C000~E57F) 뒤에 16KB 가 들어가지 않아 36:8000 으로
        self.assertEqual(self.word_notes(m), ['36:8000'])
        rom = Rom(apply(self.data, m))
        self.assertEqual(dq5field.tile_word(rom, 600, True, 1) >> 10 & 15, (nib1[600] + 2) & 15)
        with self.assertRaisesRegex(ValueError, '30~7D'):
            fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000, extra_at=0x7DC000)

    def test_three_extras_and_word_table(self):
        nib0 = self.doc['tile_palettes']
        w1, w2 = bytes([0x11]) * (32 * 512), bytes([0x22]) * (32 * 512)
        nib1, nib2 = nib0[:fgw.TILES] + [5] * fgw.TILES, nib0[:fgw.TILES] + [9] * fgw.TILES
        self.world_doc('world1', w1, nib1)
        self.world_doc('world2', w2, nib2)
        m = fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000, extra_at=0x358000)
        notes = [w['at'] for w in m['writes'] if w['note'].startswith('늘린 타일')]
        # 9,600바이트·16KB 는 35:8000·35:A580, 셋째 16KB 는 36:8000, 표는 36:C000~FFFF 에 꼭 들어감
        self.assertEqual(notes, ['35:8000', '35:A580', '36:8000'])
        self.assertEqual(self.word_notes(m), ['36:C000'])
        rom = Rom(apply(self.data, m))
        cur = fgw.current(rom)
        self.assertEqual([cur['worlds'][f'world{w}'][0][fgw.TILES * 32:] for w in (1, 2)], [w1, w2])
        for w, nib in enumerate((nib0, nib1, nib2)):
            for upper in (True, False):
                self.assertEqual(dq5field.tile_word(rom, 700, upper, w),
                                 700 | ((nib[700] & (15 if upper else 7)) * 4 + 8) << 8)

    def test_world_counts_limit_blocks(self):
        w1 = (self.folder / 'tiles.bin').read_bytes()[:fgw.TILES * 32] + bytes(32 * 100)
        (self.folder / 'w1.bin').write_bytes(w1)
        self.doc['worlds'] = {'world1': {'tiles_file': 'w1.bin', 'tile_palettes': [0] * 612}}
        m = fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000, extra_at=0x358000)
        rom = Rom(apply(self.data, m))
        self.assertEqual(fgw.tile_counts(rom), [812, 612, 812])
        self.assertEqual(fgw.tile_counts(self.rom), [512] * 3)
        self.assertEqual(ft.tile_limit(rom), 611)                                 # 블록 표는 세 세계가 함께 씀
        raw = bytes(5)
        self.assertEqual(ft.encode_block(raw, [611, 0, 0, 0], True, 611)[:1], bytes([0x63]))
        with self.assertRaisesRegex(ValueError, '모든 세계에 그 타일을 둘 것'):
            ft.encode_block(raw, [612, 0, 0, 0], True, 611)

    def test_rejects_blocks_beyond_a_world(self):
        """블록 표가 이미 512 이상을 쓰는데 타일이 그보다 적은 세계가 있으면 거부한다."""
        d = bytearray(self.data)
        put(d, dq5field.BLOCK_READ_SITE, b'\xe2')
        put(d, dq5field.BLOCK_LOWER, bytes([0xF0, 0, 0, 0, 0x80 | 0x08]))           # 타일 1008(세계는 812개)
        # check_sites 가 00:BC6D 를 보므로 디코더만 넓게 읽는 롬을 따로 쓰지 않고 write_grow 를 바로 부른다.
        rom = Rom(bytes(d))
        tiles = (self.folder / 'tiles.bin').read_bytes()
        with self.assertRaisesRegex(ValueError, '모든 세계에 그 타일을 둘 것'):
            fgw.write_grow(rom, 0x348000, 0x358000, fgw.FIELD_CHR, tiles, self.doc['tile_palettes'], {}, [],
                           lambda *a, **k: None, bytes(1024))

    def test_grown_blocks_count_in_tile_check(self):
        """블록 표를 늘린 롬이면 번호 511 이상의 블록이 쓰는 타일도 센다."""
        d = bytearray(self.data) + bytes(0x200000 - len(self.data))
        hook = 0x3C8000
        put(d, dq5field.BLOCK_GROW_SITE, b'\x5c' + hook.to_bytes(3, 'little'))
        put(d, hook, b'\x80\x08' + (0x3C9000).to_bytes(3, 'little') + (0x3C9100).to_bytes(3, 'little') + (520).to_bytes(2, 'little'))
        put(d, 0x3C9000 + 8 * 5, bytes([0xF0, 0, 0, 0, 0x88]))                   # 블록 519 아래층 타일 3F0(세계는 812개)
        tiles = (self.folder / 'tiles.bin').read_bytes()
        with self.assertRaisesRegex(ValueError, '타일 1008'):
            fgw.write_grow(Rom(bytes(d)), 0x348000, 0x358000, fgw.FIELD_CHR, tiles, self.doc['tile_palettes'], {}, [],
                           lambda *a, **k: None, bytes(1024))

    def test_attributes(self):
        self.doc['tile_attributes'] = list(range(256)) * 4
        rom = Rom(apply(self.data, fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000,
                                             extra_at=0x358000)))
        self.assertEqual(fgw.current(rom)['tile_attributes'], list(range(256)) * 4)
        self.doc['tile_attributes'] = [0] * 700
        with self.assertRaisesRegex(ValueError, 'tile_attributes'):
            fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000, extra_at=0x358000)

    def test_attributes_in_place_without_grow(self):
        doc = fgw.dump(self.rom, self.tmp.name)
        doc['tile_attributes'][5] = 0x80
        m = fgw.patch(self.rom, doc, self.tmp.name)
        self.assertEqual([(w['at'], w['hex']) for w in m['writes']], [('2A:D517', '80')])
        doc['tile_attributes'] = [0] * 1024
        with self.assertRaisesRegex(ValueError, 'tile_attributes'):
            fgw.patch(self.rom, doc, self.tmp.name)
        with self.assertRaisesRegex(ValueError, '--extra-at'):
            fgw.patch(self.rom, fgw.dump(self.rom, self.tmp.name), self.tmp.name, extra_at=0x358000)

    def test_rejects_patched_rom(self):
        rom = Rom(apply(self.data, fgw.patch(self.rom, self.doc, self.tmp.name, worlds_at=0x348000,
                                             extra_at=0x358000)))
        with self.assertRaisesRegex(ValueError, '원본 롬으로'):
            fgw.patch(rom, self.doc, self.tmp.name, worlds_at=0x348000, extra_at=0x358000)


class BlockBitTests(unittest.TestCase):
    def test_tenth_bit_needs_hooked_rom(self):
        raw = bytes([1, 2, 3, 4, 0])
        self.assertEqual(ft.encode_block(raw, [513, 2, 768, 1023], wide=True), bytes([1, 2, 0, 255, 0x08 | 0x22 | 0x11]))
        with self.assertRaisesRegex(ValueError, '타일 늘리기'):
            ft.encode_block(raw, [512, 2, 3, 4])
        with self.assertRaises(ValueError):
            ft.encode_block(raw, [1024, 2, 3, 4], wide=True)
        self.assertEqual(ft.block_tiles(bytes([1, 2, 0, 255, 0xBB]), wide=True), [769, 2, 768, 1023])
        self.assertEqual(ft.block_tiles(bytes([1, 2, 0, 255, 0xBB])), [257, 2, 256, 511])

    def test_decoder_reads_tenth_bit_only_with_hook(self):
        d = bytearray(0x180000)
        put(d, dq5field.BLOCK_LOWER, bytes([1, 2, 3, 4, 0x0F]))
        self.assertEqual(dq5field.block_tiles(Rom(bytes(d)), dq5field.BLOCK_LOWER, 0), [1, 2, 3, 4])
        put(d, dq5field.BLOCK_READ_SITE, b'\xe2')
        self.assertEqual(dq5field.block_tiles(Rom(bytes(d)), dq5field.BLOCK_LOWER, 0), [513, 514, 515, 516])


class TileWordBoundaryTests(unittest.TestCase):
    """타일 511·512·1023 의 타일맵 워드를 타일마다 1바이트 표(00:BBAC 를 바꾼 롬)와 세계마다 512바이트 니블 훅 둘로 낸다."""
    NIB = [(i * 5 + 3) % 16 for i in range(1024)]

    def word(self, t, upper, nib):
        return t | ((nib[t] if upper else nib[t] & 7) * 4 + 8) << 8

    def test_palette_tables(self):
        d = bytearray(0x200000)
        put(d, dq5field.PALETTE_SITE, fgw.palette_fast(0x308000, 0x308400))
        put(d, 0x308000, b''.join(fgw.palette_bytes(self.NIB)))
        rom = Rom(bytes(d))
        for t in (511, 512, 1023):
            for upper in (True, False):
                self.assertEqual(dq5field.tile_word(rom, t, upper, 2), self.word(t, upper, self.NIB))

    def test_world_word_tables(self):
        d = bytearray(0x200000)
        put(d, dq5field.PALETTE_SITE, fgw.palette_worlds(0x308000, 0x30A000))
        worlds = [self.NIB, self.NIB[::-1], [n ^ 5 for n in self.NIB], self.NIB]
        put(d, 0x308000, b''.join(fgw.palette_world_words(worlds)))
        rom = Rom(bytes(d))
        for w, nib in enumerate(worlds):
            for t in (0, 511, 512, 1023):
                for upper in (True, False):
                    self.assertEqual(dq5field.tile_word(rom, t, upper, w), self.word(t, upper, nib))
        with self.assertRaisesRegex(ValueError, '니블 표가 없음'):
            dq5field.nibble_table(rom)

    def test_wide_nibble_hook(self):
        d = bytearray(0x200000)
        put(d, dq5field.PALETTE_SITE, fgw.PALETTE_READ_ORIG)
        put(d, dq5field.NIB_SITE, b'\x22' + fgw.long_addr(0x308000))
        put(d, 0x308000, fgw.nib_hook(0x318000, wide=True))
        worlds = [self.NIB, self.NIB[::-1]]
        for w, nib in enumerate(worlds):
            put(d, 0x318000 + w * 0x200, bytes(nib[i] << 4 | nib[i + 1] for i in range(0, 1024, 2)))
        rom = Rom(bytes(d))
        for w, nib in enumerate(worlds):
            for t in (511, 512, 1023):
                for upper in (True, False):
                    self.assertEqual(dq5field.tile_word(rom, t, upper, w), self.word(t, upper, nib))


class FieldPaletteTests(unittest.TestCase):
    def setUp(self):
        self.data = field_rom()
        self.rom = Rom(self.data)
        self.tmp = tempfile.TemporaryDirectory()
        self.doc = fgw.dump(self.rom, self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_original_times(self):
        self.assertEqual(self.doc['world0_times'], [list(t) for t in ORIGINAL_TIMES])
        self.assertEqual(self.doc['world0_night_from'], 6)

    def test_more_sets_need_place(self):
        self.doc['palettes']['world0'].append([0x7FFF] * 30)
        self.doc['world0_times'] = self.doc['world0_times'] + [[0x300, 8]]
        with self.assertRaisesRegex(ValueError, '--palettes-at'):
            fgw.patch(self.rom, self.doc, self.tmp.name)
        m = fgw.patch(self.rom, self.doc, self.tmp.name, palettes_at=0x368000)
        sites = {w['at']: w['hex'] for w in m['writes']}
        self.assertEqual((sites['01:A0B1'], sites['01:A145']), ('36', '0c'))
        rom = Rom(apply(self.data, m))
        cur = fgw.current(rom)
        self.assertEqual(cur['world0_times'], self.doc['world0_times'])
        self.assertEqual(cur['palettes']['world0'], self.doc['palettes']['world0'])
        self.assertEqual(cur['wave'], self.doc['wave'])
        # 찾기 훅: LDX #(11-1)*3, 시간대 표는 36:8000
        hook = rom.u24(0x01A133)
        self.assertEqual((rom.u8(hook + 1), rom.u24(hook + 7)), (30, 0x368000))
        self.assertEqual(rom.u24(0x01A167), hook + fgw.SEARCH_LEN)

    def test_bad_times(self):
        for times in ([[1, 0]], [[0, 0], [0, 1]], [[0, 8]], [[0, 0]] * 87, [[0, 0], [5]]):
            self.doc['world0_times'] = times
            with self.assertRaisesRegex(ValueError, 'world0_times'):
                fgw.patch(self.rom, self.doc, self.tmp.name, palettes_at=0x368000)
        self.doc['world0_times'] = [[0, 0]]
        self.doc['world0_night_from'] = 200
        with self.assertRaisesRegex(ValueError, 'world0_night_from'):
            fgw.patch(self.rom, self.doc, self.tmp.name, palettes_at=0x368000)
        self.doc['world0_night_from'] = 6
        self.doc['palettes']['world0'] = []
        with self.assertRaisesRegex(ValueError, 'palettes'):
            fgw.patch(self.rom, self.doc, self.tmp.name, palettes_at=0x368000)

    def test_place_only_when_moving(self):
        with self.assertRaisesRegex(ValueError, '--palettes-at 은'):
            fgw.patch(self.rom, self.doc, self.tmp.name, palettes_at=0x368000)

    def test_world12_sets_and_refresh_hook(self):
        new = [[0x0400 + i for i in range(30)], [0x0800 + i for i in range(30)]]
        for sets in new:
            for i in fgw.CYCLED:
                sets[i] = self.doc['palettes']['world1'][0][i]
        self.doc['palettes']['world1'] += new
        self.doc['world1_times'] = [[0, 2], [0x80, 1], [0x100, 0]]
        self.doc['world2_times'] = [[0, 0]]
        with self.assertRaisesRegex(ValueError, '--palettes-at'):
            fgw.patch(self.rom, self.doc, self.tmp.name)
        m = fgw.patch(self.rom, self.doc, self.tmp.name, palettes_at=0x368000)
        sites = {w['at']: w['hex'] for w in m['writes']}
        self.assertEqual(sites['01:9F91'], 'a9 36')
        self.assertNotIn('01:9FA6', sites)                  # 세계 2 는 그대로
        data = bytearray(apply(self.data, m))
        rom = Rom(bytes(data))
        cur = fgw.current(rom)
        self.assertEqual(cur['palettes']['world1'], self.doc['palettes']['world1'])
        self.assertEqual(cur['world1_times'], self.doc['world1_times'])
        self.assertEqual(cur['world2_times'], [[0, 0]])
        self.assertEqual(len(cur['palettes']['world2']), 1)
        # 불러올 때 넘기는 벌은 시간대 표 첫 항목(벌 2)
        first = rom.u16(0x019F8D)
        self.assertEqual(fgw.colors(rom, 0x360000 | first, 30), new[1])
        put(data, 0x01A055, b'\x6b')                        # 세계 0 갈래가 부르는 01:A055 자리
        hook = rom.u24(0x02AD39)
        for world, t, want in ((1, 0x0000, new[1]), (1, 0x0090, new[0]), (1, 0x0150, self.doc['palettes']['world1'][0]),
                               (2, 0x0150, None), (0, 0x0150, None)):
            cpu = Cpu(bytes(data), bytes(0x20000))
            cpu.wram[0x1949], cpu.wram[0x75E], cpu.wram[0x75F] = world, t & 0xFF, t >> 8
            cpu.p = 0x30
            cpu.jsl(hook)
            got = [cpu.wram[0x3956 + i * 2] | cpu.wram[0x3957 + i * 2] << 8 for i in range(15)] + \
                [cpu.wram[0x3976 + i * 2] | cpu.wram[0x3977 + i * 2] << 8 for i in range(15)]
            self.assertEqual(got, want or [0] * 30, f'세계 {world} {t:04X}')
            self.assertEqual(cpu.p, 0x30)

    def test_world12_bad_times(self):
        for times in ([[1, 0]], [[0, 1]], [[0, 0], [0, 0]]):
            self.doc['world2_times'] = times
            with self.assertRaisesRegex(ValueError, 'world2_times'):
                fgw.patch(self.rom, self.doc, self.tmp.name, palettes_at=0x368000)
        self.doc.pop('world2_times')
        self.doc['palettes']['world2'] = []
        with self.assertRaisesRegex(ValueError, 'palettes'):
            fgw.patch(self.rom, self.doc, self.tmp.name, palettes_at=0x368000)


def indoor_rom():
    d = bytearray(0x180000)
    for key, (at, n) in mgw.SITES.items():
        put(d, at, mgw.EXPECT[key])
    b0 = encode_block({'w': 1, 'h': 1, 'flags': 0, 'b1': 0, 'attr': 1, 'words': [0]}, 1)
    put(d, 0x168000, b0 + b'\xff\xff\xff')
    put(d, mgw.chr_addr(0x13, 0), bytes([1]) * 32)
    first = (dq5map.PALSET_LISTS & 0xFFFF) + mgw.SET_COUNT * 4
    put(d, dq5map.PALSET_LISTS, first.to_bytes(2, 'little') * (mgw.SET_COUNT * 2))
    put(d, 0x100000 | first, b''.join(r.to_bytes(2, 'little') for r in (1, 2, 3, 4, 5, 6, 7)))
    put(d, mgw.ROW_READ, bytes.fromhex('b9 c8 e5'))
    put(d, mgw.SET_READ, mgw.SET_ORIG)
    for r in range(mgw.PALETTE_ROWS):
        put(d, dq5map.PALETTES + r * 32, bytes([r, 0]) * 16)
    put(d, dq5map.PALSET_TABLE, bytes([0x01, 0x00, 0xFF, 0xFF]))
    return bytes(d)


class IndoorSetTests(unittest.TestCase):
    def setUp(self):
        self.data = indoor_rom()
        self.rom = Rom(self.data)
        self.tmp = tempfile.TemporaryDirectory()
        self.doc = mgw.dump(self.rom, self.tmp.name)
        self.lid = next(iter(self.doc['palette_lists']))

    def tearDown(self):
        self.tmp.cleanup()

    def test_grow_needs_place(self):
        self.doc['palette_lists']['0000'] = [9] * 7
        self.doc['palette_sets'].append(['0000', self.lid])
        with self.assertRaisesRegex(ValueError, '--sets-at'):
            mgw.patch(self.rom, self.doc, self.tmp.name)
        with self.assertRaisesRegex(ValueError, '30~3F'):
            mgw.patch(self.rom, self.doc, self.tmp.name, sets_at=0x408000)
        m = mgw.patch(self.rom, self.doc, self.tmp.name, sets_at=0x378000)
        rom = Rom(apply(self.data, m))
        self.assertEqual(rom.d[lorom(mgw.SET_READ):lorom(mgw.SET_READ) + 3], bytes.fromhex('20 e8 ff'))
        self.assertEqual(rom.d[lorom(mgw.SET_STUB):lorom(mgw.SET_STUB) + 15],
                         bytes.fromhex('bf 00 80 37 48 e2 20 a9 37 48 ab c2 20 68 60'))
        # 줄은 옮기지 않았어도 DB 가 바뀌므로 원래 자리를 긴 주소로 읽는 스텁을 둔다.
        self.assertEqual(rom.d[lorom(mgw.ROW_STUB):lorom(mgw.ROW_STUB) + 8], bytes.fromhex('da bb bf c8 e5 10 fa 60'))
        sets, lists = mgw.palette_lists(rom)
        self.assertEqual(len(sets), mgw.SET_COUNT + 1)
        self.assertEqual([lists[v] for v in sets[-1]], [[9] * 7, [1, 2, 3, 4, 5, 6, 7]])
        self.assertEqual(psw.set_count(rom), mgw.SET_COUNT + 1)
        self.assertEqual(dq5map.palset_lists(rom), 0x378000)
        # 디코더도 옮긴 표·목록을 따른다(그룹 01 기본 세트 0).
        self.assertEqual(dq5map.map_cgram(rom, 0x01, 0x00)[0x20:0x22], bytes([1, 0]))
        with self.assertRaisesRegex(ValueError, '원본 롬으로'):
            mgw.patch(rom, self.doc, self.tmp.name, sets_at=0x378000)

    def test_moved_rom_counts_its_sets_and_refuses_in_place(self):
        self.doc['palette_sets'].append([self.lid, self.lid])
        rom = Rom(apply(self.data, mgw.patch(self.rom, self.doc, self.tmp.name, sets_at=0x378000)))
        doc = mgw.dump(rom, self.tmp.name)
        self.assertEqual(len(doc['palette_sets']), mgw.SET_COUNT + 1)
        self.assertEqual(mgw.patch(rom, doc, self.tmp.name)['writes'], [])       # 옮긴 롬의 세트 수와 견줌
        lid = next(iter(doc['palette_lists']))                                    # 옮긴 롬의 id 는 뱅크 37 주소
        self.assertNotIn(self.lid, doc['palette_lists'])
        doc['palette_lists'][lid] = [9] * 7
        with self.assertRaisesRegex(ValueError, '이미 --sets-at'):
            mgw.patch(rom, doc, self.tmp.name)
        doc['palette_sets'].append([lid, lid])
        with self.assertRaisesRegex(ValueError, f'세트 {mgw.SET_COUNT + 1}개'):
            mgw.patch(rom, doc, self.tmp.name)

    def test_bad_sets(self):
        self.doc['palette_sets'] = self.doc['palette_sets'] * 4
        with self.assertRaisesRegex(ValueError, '1~256'):
            mgw.patch(self.rom, self.doc, self.tmp.name, sets_at=0x378000)
        self.doc['palette_sets'] = [['ABCD', self.lid]]
        with self.assertRaisesRegex(ValueError, 'palette_sets'):
            mgw.patch(self.rom, self.doc, self.tmp.name, sets_at=0x378000)
        self.doc['palette_sets'] = [[self.lid, self.lid]]
        self.doc['palette_lists']['zz00'] = [0] * 7
        with self.assertRaisesRegex(ValueError, '4자리'):
            mgw.patch(self.rom, self.doc, self.tmp.name, sets_at=0x378000)


class CliTests(unittest.TestCase):
    def run_tool(self, *args):
        return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, timeout=60)

    def test_field_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'rom.sfc').write_bytes(field_rom())
            tool = HERE / 'dq5fieldgfxwrite.py'
            self.assertEqual(self.run_tool(tool, tmp / 'rom.sfc', 'dump', '-o', tmp / 'src').returncode, 0)
            doc = json.loads((tmp / 'src' / 'fieldgfx.json').read_text(encoding='utf-8'))
            (tmp / 'src' / 'tiles.bin').write_bytes((tmp / 'src' / 'tiles.bin').read_bytes() * 2)
            doc['tile_palettes'] *= 2
            (tmp / 'src' / 'fieldgfx.json').write_text(json.dumps(doc), encoding='utf-8')
            r = self.run_tool(tool, tmp / 'rom.sfc', 'patch', tmp / 'src' / 'fieldgfx.json', '-o', tmp / 'p.json')
            self.assertEqual(r.returncode, 1)
            self.assertIn('--extra-at', r.stderr)
            r = self.run_tool(tool, tmp / 'rom.sfc', 'patch', tmp / 'src' / 'fieldgfx.json', '-o', tmp / 'p.json',
                              '--worlds-at', '34:8000', '--extra-at', '35:8000')
            self.assertEqual(r.returncode, 0, r.stderr)
            notes = [w['note'] for w in json.loads((tmp / 'p.json').read_text(encoding='utf-8'))['writes']]
            self.assertIn('타일맵 다시 그리기(전투 뒤·00:A771) 때 늘린 타일 다시 보내기', notes)
            r = self.run_tool(tool, tmp / 'rom.sfc', 'patch', tmp / 'src' / 'fieldgfx.json', '-o', tmp / 'p.json',
                              '--worlds-at', '34:8000', '--extra-at', '3x:8000')
            self.assertEqual(r.returncode, 1)
            self.assertIn('BB:AAAA', r.stderr)

    def test_indoor_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'rom.sfc').write_bytes(indoor_rom())
            tool = HERE / 'dq5mapgfxwrite.py'
            self.assertEqual(self.run_tool(tool, tmp / 'rom.sfc', 'dump', '-o', tmp / 'src').returncode, 0)
            doc = json.loads((tmp / 'src' / 'mapgfx.json').read_text(encoding='utf-8'))
            doc['palette_sets'].append(doc['palette_sets'][0])
            (tmp / 'src' / 'mapgfx.json').write_text(json.dumps(doc), encoding='utf-8')
            r = self.run_tool(tool, tmp / 'rom.sfc', 'patch', tmp / 'src' / 'mapgfx.json', '-o', tmp / 'p.json')
            self.assertEqual(r.returncode, 1)
            self.assertIn('--sets-at', r.stderr)
            r = self.run_tool(tool, tmp / 'rom.sfc', 'patch', tmp / 'src' / 'mapgfx.json', '-o', tmp / 'p.json',
                              '--sets-at', '37:8000')
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()
