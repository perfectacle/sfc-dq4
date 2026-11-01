import json
import tempfile
import unittest
import unittest.mock
from collections import Counter
from pathlib import Path

from PIL import Image

import dq4people as P
from dq4chapter1 import lorom
from w65816 import Cpu

TABLE = 0x2586D0
# 실제 표만큼 긴 줄 목록. 맵 그룹을 보는 줄을 앞에 둔다(hook_entries 와 같은 차례)
ENTRIES = [(0x2B, 0x3C, 0x70), (0x2E, 0x3C, 0x70), (0x08, 0x3C, 0x63), (0x17, 0x3C, 0x09), (0x09, 0x3C, 0x22),
           (0x1F, 0x3C, 0x2D), (0x2B, None, 0x71), (0x2E, None, 0x71), (0x5B, None, 0x20), (0x14, None, 0x04),
           (0x04, None, 0x3C), (0x9B, None, 0x39)]


def run(picture, group, p=0x30):
    rom = bytearray(0x400000)
    at = P.cpu(P.HOOK_AT)
    code = P.hook(ENTRIES)
    rom[lorom(at):lorom(at) + len(code)] = code
    for g in range(0x100):
        rom[lorom(TABLE + g)] = g ^ 0x80
    cpu = Cpu(bytes(rom), bytearray(0x20000))
    cpu.wram[0xBC] = group
    cpu.x, cpu.p = picture, p
    cpu.jsl(at)
    return cpu


class HookTests(unittest.TestCase):
    def test_every_entry_picks_its_set(self):
        for picture, group, s in ENTRIES:
            self.assertEqual(run(picture, 0x3C if group else 0x36).a & 0xFF, s, f'{picture:02X}')

    def test_prologue_only_entries_fall_back_elsewhere(self):
        self.assertEqual(run(0x08, 0x36).a & 0xFF, 0x08 ^ 0x80)
        self.assertEqual(run(0x2B, 0x36).a & 0xFF, 0x71)

    def test_other_pictures_read_the_table(self):
        for picture in (0x00, 0x06, 0x2C, 0xA8):
            self.assertEqual(run(picture, 0x3C).a & 0xFF, picture ^ 0x80)

    def test_flag_entry_wins_only_when_the_flag_is_on(self):
        entries = [(0x2B, None, (0x78, 0x10), 0x83)] + ENTRIES
        for flag, want in ((0x10, 0x83), (0x00, 0x71)):
            rom = bytearray(0x400000)
            at = P.cpu(P.HOOK_AT)
            code = P.hook(entries)
            rom[lorom(at):lorom(at) + len(code)] = code
            cpu = Cpu(bytes(rom), bytearray(0x20000))
            cpu.wram[0xBC], cpu.wram[0x2190 + 0x78] = 0x3D, flag
            cpu.x, cpu.p = 0x2B, 0x30
            cpu.jsl(at)
            self.assertEqual(cpu.a & 0xFF, want)

    def test_register_widths_come_back(self):
        # 03:D202 는 X 16비트(상위 0)로 부를 수 있다. PLP 가 폭을 되돌리고 X 는 그대로여야 한다
        cpu = run(0x9B, 0x36, p=0x20)
        self.assertEqual(cpu.p & 0x30, 0x20)
        self.assertEqual(cpu.x, 0x9B)


PAL_TABLE, SWAP_AT = 0x3DEA55, 0x3DEA19


def swap_rom():
    """인물 훅·그림 표·세트 팔레트 표·그림 바꾸기 팔레트 루틴을 넣고 03:D202·03:D24D 를 JSL 로 돌린 롬."""
    import dq5objpalette
    rom = bytearray(0x400000)
    at = P.cpu(P.HOOK_AT)
    code = P.hook(ENTRIES)
    rom[lorom(at):lorom(at) + len(code)] = code
    for g in range(0x100):
        rom[lorom(TABLE + g)] = g ^ 0x80
        rom[lorom(PAL_TABLE + g)] = 0xFF
    rom[lorom(PAL_TABLE + 0x71)], rom[lorom(PAL_TABLE + 0x20)] = 6, 5
    routine = dq5objpalette.swap_routine(PAL_TABLE)
    rom[lorom(SWAP_AT):lorom(SWAP_AT) + len(routine)] = routine
    rom[lorom(0x03D202):lorom(0x03D202) + 4] = bytes((0x22, at & 0xFF, at >> 8 & 0xFF, at >> 16))
    rom[lorom(P.SWAP_SITE):lorom(P.SWAP_SITE) + 4] = bytes((0x22, SWAP_AT & 0xFF, SWAP_AT >> 8 & 0xFF, SWAP_AT >> 16))
    return rom


def swap_run(rom, picture, group=0x36):
    cpu = Cpu(bytes(rom), bytearray(0x20000))
    cpu.wram[0xBC], cpu.wram[0x1EC0] = group, picture
    cpu.x, cpu.p = 0x80C0, 0x20
    cpu.jsl(SWAP_AT)
    return cpu


class SwapTests(unittest.TestCase):
    def test_hooked_picture_site_breaks_the_plain_routine(self):
        # 03:D202 가 JSL 이면 원래 루틴은 훅 코드 바이트를 세트로 읽는다
        self.assertNotEqual(swap_run(swap_rom(), 0x2B).wram[0x08], 6 * 2)

    def test_patched_routine_takes_the_hook_set(self):
        rom = swap_rom()
        write = P.swap_patch(bytes(rom))['writes'][0]
        head = bytes.fromhex(write['hex'])
        rom[lorom(SWAP_AT):lorom(SWAP_AT) + len(head)] = head
        for picture, want in ((0x2B, 6), (0x5B, 5)):
            cpu = swap_run(rom, picture)
            self.assertEqual(cpu.wram[0x08], want * 2, f'{picture:02X}')
            self.assertEqual((cpu.x, cpu.y, cpu.p & 0x30), (0x80C0, 2, 0x20))

    def test_hook_patch_widens_the_reload_bank_mask(self):
        rom = bytearray(0x400000)
        for site in P.HOOK_SITES:
            rom[lorom(P.cpu(site)):lorom(P.cpu(site)) + 4] = P.LOAD_SET
        rom[lorom(P.BANK_MASK_SITE):lorom(P.BANK_MASK_SITE) + 2] = b'\x29\x0f'
        rom[lorom(P.FIELD_MATH_SITE):lorom(P.FIELD_MATH_SITE) + 2] = b'\xa9\x50'
        with unittest.mock.patch.object(P, 'hook_entries', return_value=[]):
            writes = P.hook_patch(bytes(rom))['writes']
        self.assertIn({'at': '03:D2C7', 'hex': '29 3f', 'orig': '29 0f',
                       'note': '일행 그림 다시 싣기의 타일 자료 뱅크 6비트'}, writes)

    def test_hook_patch_turns_off_field_obj_color_math(self):
        # 장 주인공·동료는 OBJ 팔레트 5~7 이라, 필드의 OBJ 반 더하기가 남으면 BG 와 반씩 섞여 보인다
        rom = bytearray(0x400000)
        for site in P.HOOK_SITES:
            rom[lorom(P.cpu(site)):lorom(P.cpu(site)) + 4] = P.LOAD_SET
        rom[lorom(P.BANK_MASK_SITE):lorom(P.BANK_MASK_SITE) + 2] = b'\x29\x0f'
        rom[lorom(P.FIELD_MATH_SITE):lorom(P.FIELD_MATH_SITE) + 2] = b'\xa9\x50'
        with unittest.mock.patch.object(P, 'hook_entries', return_value=[]):
            writes = P.hook_patch(bytes(rom))['writes']
        self.assertEqual([(w['hex'], w['orig']) for w in writes if w['at'] == '2B:82F7'], [('a9 00', 'a9 50')])


def body(color=(200, 30, 30, 255)):
    c = Image.new('RGBA', (16, 24))
    for y in range(P.BOTTOM - 17, P.BOTTOM):
        for x in range(3, 13):
            c.putpixel((x, y), (60, 90, 120, 255) if y < P.BOTTOM - 5 else color)
    return c


class SheetTests(unittest.TestCase):
    def test_steps_change_only_the_legs(self):
        for name in ('down', 'left', 'right', 'up'):
            cells = [body(), body()]
            P.step(cells, name, 17)
            a, b = (list(c.get_flattened_data()) for c in cells)
            top = (P.BOTTOM - 5) * 16
            self.assertEqual(a[:top], b[:top], name)
            self.assertNotEqual(a[top:], b[top:], name)
            self.assertFalse(any(p[3] for p in a[P.BOTTOM * 16:]), name)

    def test_overlap_sheet_keeps_head_and_bodies(self):
        cells = {name: [body(), body((30, 200, 30, 255))] for name, _ in P.ROWS8}
        pal = [(60, 90, 120), (200, 30, 30), (30, 200, 30)]
        im = P.index_image(cells, pal, 'overlap')
        self.assertEqual(im.size, (48, 64))
        # 몸 열은 프레임의 8~23행이라 몸 0 과 몸 1 의 아랫줄(발) 색이 다르다
        self.assertEqual(im.getpixel((16 + 5, 16 - 3)), 2)
        self.assertEqual(im.getpixel((32 + 5, 16 - 3)), 3)

    def test_four_row_sheet_faces_right_on_row_one(self):
        sheet = Image.new('RGBA', (128, 128))
        for row in range(4):
            for y in range(row * 32 + 4, row * 32 + 28):
                for x in range(4, 12):
                    sheet.putpixel((x, y), (row * 60, 0, 0, 255))
        with tempfile.TemporaryDirectory() as d:
            sheet.save(Path(d) / 's.png')
            out = P.frames(Path(d) / 's.png', 'legs')
        self.assertEqual(out['right'][0].getpixel((4, 12))[0], 60)
        self.assertEqual(out['left'][0].getpixel((4, 12))[0], 180)

    def test_shrink_keeps_a_dark_eye(self):
        f = Image.new('RGBA', (28, 28), (230, 180, 140, 255))
        for y in (10, 11):
            f.putpixel((9, y), (0, 0, 0, 255))
        s = P.shrink(f)
        self.assertIn((0, 0, 0, 255), list(s.get_flattened_data()))

    def test_outline_darkens_only_the_edge(self):
        c = Image.new('RGBA', (16, 24))
        for y in range(10, 20):
            for x in range(4, 12):
                c.putpixel((x, y), (10, 10, 10, 255) if (x, y) == (7, 15) else (60, 180, 40, 255))
        P.outline(c)
        self.assertEqual(c.getpixel((4, 12)), (10, 10, 10, 255))
        self.assertEqual(c.getpixel((6, 14)), (60, 180, 40, 255))
        self.assertEqual(c.getpixel((3, 12))[3], 0)

    def test_place_keeps_one_slot_per_color_and_tunes_each_group(self):
        a = P.Person((0x10,), None, 'x', 'a')
        b = P.Person((0x11,), None, 'x', 'b')
        hists = {a: Counter({(200, 30, 30): 50, (20, 20, 20): 10}), b: Counter({(220, 40, 40): 50, (20, 20, 20): 10})}
        placed, board = P.place([a, b], hists, {a: {0x36}, b: {0x37}})
        for p, g in ((a, 0x36), (b, 0x37)):
            line, mapping = placed[p]
            for c, k in mapping.items():
                self.assertEqual(board[(g, line)][k], c)

    def test_where_adds_groups_that_use_the_spare_picture(self):
        elder = P.Person((0x1F,), 0x3C, 'x', 'elder', spare=0x9C)
        scholar = P.Person((0x1F,), None, 'x', 'scholar')
        out = P.where([elder, scholar], {0x9C: {0x36}, 0x1F: {0x3C, 0x45}})
        self.assertEqual(out[elder], {0x3C, 0x36})
        self.assertEqual(out[scholar], {0x45})

    def test_pack_backtracks_when_largest_first_fragments(self):
        bins = P.pack([('a', 6), ('b', 5), ('c', 5)], [10, 6])
        self.assertEqual(sorted(sorted(b) for b in bins), [['a'], ['b', 'c']])

    def test_reduce_keeps_the_most_used_colors(self):
        hist = Counter({(k * 10, 0, 0): 100 - k for k in range(20)})
        pal = P.reduce(hist)
        self.assertEqual(len(pal), 15)
        self.assertIn((0, 0, 0), pal)


class BuildFlowTests(unittest.TestCase):
    """롬 없이 build 가 시트 준비 결과로 스프라이트·팔레트 문서를 짜고 패치를 얹는 차례를 본다. 시트 준비·패치 만들기는
    가짜로 바꾼다."""
    RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (8, 16, 248)

    def person(self, role, new_set=None, palette=None, flag=None):
        from types import SimpleNamespace
        return SimpleNamespace(role=role, new_set=new_set, palette=palette, flag=flag)

    def rows(self, over=False):
        p = self.person
        return [(p('a'), 0x90, 'overlap', 48, 49 if over else 30, [], 1, [self.RED]),
                (p('hero1', new_set=0), 0xA5, 'overlap', 48, 40, [], 2, [self.GREEN]),
                (p('fixed', palette='x'), 0x91, 'simple', 24, 20, [], 3, [self.BLUE]),
                (p('hero2', new_set=1), 0xA6, 'overlap', 48, 40, [], 2, [self.GREEN]),
                (p('flagged', palette='y', flag=(0x12, 0x40)), 0x92, 'simple', 24, 20, [], 4, [self.RED, None])]

    BOARD = {(0x36, 1): [(0, 0, 0), None], (0x36, 2): [None, None], (0x37, 1): [(0, 0, 0), (8, 8, 8)],
             (0x37, 2): [(16, 16, 16), None]}

    def run_build(self, rows):
        calls = {'applied': [], 'palette_docs': []}

        def run(cmd, **kw):
            calls['dq5build'] = [str(c) for c in cmd]
            Path(cmd[cmd.index('-o') + 1]).write_bytes(b'mid')

        def objpalette(rom, doc, at):
            calls['palette_docs'].append((doc, at))
            return {'format': 'dq5patch/1', 'writes': [], 'at': at}

        def apply_writes(data, original, paths):
            calls['applied'].append([Path(p).name for p in paths])
            return bytearray(data)

        with tempfile.TemporaryDirectory() as t:
            work = Path(t)
            base, dq5, out = work / 'base.sfc', work / 'dq5.sfc', work / 'out.sfc'
            base.write_bytes(bytes(0x400000))
            dq5.write_bytes(b'dq5')
            with unittest.mock.patch.multiple(P, prepare=lambda *a: (rows, self.BOARD),
                                              split_patches=lambda rom, doc, w, areas: [{'n': 0}, {'n': 1}],
                                              tile_areas=lambda data: (('3F:8000', 16),),
                                              hook_patch=lambda rom: {'hook': 1}, swap_patch=lambda rom: {'swap': 1},
                                              apply_writes=apply_writes), \
                    unittest.mock.patch.object(P.subprocess, 'run', run), \
                    unittest.mock.patch.object(P.dq5objpalette, 'patch', objpalette):
                P.build(base, dq5, work / 'assets', out, work)
                calls['sprite'] = json.loads((work / 'sprite.json').read_text())
                calls['out'] = out.read_bytes()
        return calls

    def test_tile_limit_stops_the_build(self):
        with self.assertRaisesRegex(SystemExit, 'a 49>48'):
            self.run_build(self.rows(over=True))

    def test_sprite_doc_links_the_new_leader_sets_to_the_leader_pictures(self):
        doc = self.run_build(self.rows())['sprite']
        self.assertEqual([r['set'] for r in doc['sets']], ['90', '91', '92'])
        self.assertEqual([(r['set'], r['palette']) for r in doc['new_sets']], [('A5', 0), ('A6', 0)])
        self.assertEqual(doc['gfx'], [{'gfx': f'{g:02X}', 'set': s} for g, s in zip(P.LEADER_PICTURES, ('A5', 'A6'))])

    def test_patches_go_on_sprites_then_palettes_then_the_swap(self):
        calls = self.run_build(self.rows())
        self.assertEqual(calls['applied'], [['sprite0.dq5patch.json', 'sprite1.dq5patch.json', 'palette.dq5patch.json',
                                             'maps.dq5patch.json', 'hook.dq5patch.json'], ['swap.dq5patch.json']])
        build = calls['dq5build']
        self.assertEqual([Path(a).name for a in build if a.endswith('.json')],
                         ['sprite0.dq5patch.json', 'sprite1.dq5patch.json'])
        out = calls['out']
        checksum = int.from_bytes(out[0x7FDE:0x7FE0], 'little')
        self.assertEqual(checksum ^ int.from_bytes(out[0x7FDC:0x7FDE], 'little'), 0xFFFF)

    def test_palette_lines_take_the_fullest_group_then_the_fixed_lines(self):
        docs = dict((at, doc) for doc, at in self.run_build(self.rows())['palette_docs'])
        pal = docs[P.PALETTES_AT]
        lines = {p['palette']: p['colors'] for p in pal['palettes']}
        # 37 이 칸이 더 찬 그룹이라 기본 줄 1·2 는 37 의 것, 깃발 없는 고정 줄 3 은 그 인물의 색
        self.assertEqual(sorted(lines), [1, 2, 3])
        self.assertEqual(lines[1][:2], [0, 1 << 10 | 1 << 5 | 1])
        self.assertEqual(lines[3][0], 31 << 10 | 2 << 5 | 1)
        self.assertTrue(all(len(c) == 15 for c in lines.values()))
        self.assertEqual(pal['sets'][0], {'set': '90', 'palette': 1})
        maps = docs[P.MAP_PALETTES_AT]['new_map_palettes']
        plain = [m for m in maps if m['flag'] == 'FF']
        self.assertEqual([(m['map'], m['line']) for m in plain], [('36/FF', '09'), ('36/FF', '0A'), ('37/FF', '09'),
                                                                   ('37/FF', '0A')])
        flagged = [m for m in maps if m['flag'] != 'FF']
        every = [f'{g:02X}/FF' for g in P.chapter_groups(2)] + ['FE/00', 'FE/01', 'FE/02']
        self.assertEqual([m['map'] for m in flagged], every)
        self.assertTrue(all((m['line'], m['flag'], m['mask']) == ('0C', '12', '40') for m in flagged))
        self.assertEqual(flagged[0]['colors'][:2], [31, 0])


if __name__ == '__main__':
    unittest.main()
