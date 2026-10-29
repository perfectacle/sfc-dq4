"""상자 도구 셋(표 옮기기·고정 표 쓰기·상자 놓기)이 dq5newmap.py 로 더하는 새 맵을 --new-map·--with-patch 로 받는지."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5chestplace as place
import dq5chestreloc as reloc
import dq5chestwrite as write
import dq5newmap
from dq5build import build, load
from dq5chestwrite import NewMaps
from dq5map import Rom
from test_dq5chestwrite import ROM, fixture

# 36/00 은 31/03(상자 칸 (8,17)·(10,17), ツボ 칸 (8,21)·(10,21))과 같은 레코드·속성
NEWMAP = {'format': 'dq5newmap/1', 'groups': [{'group': '36', 'entrance': {'copy': '31'}}],
          'maps': [{'map': '36/00', 'record': {'copy': '31/03'}, 'attrs': {'copy': '31/03'}}]}
NEW = (0x36, 0)


def run(module, *args):
    out, err = io.StringIO(), io.StringIO()
    with mock.object(sys, 'argv', [module.__name__, *map(str, args)]), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        try:
            code = module.main()
        except SystemExit as stop:
            code = stop.code
    return code, out.getvalue() + err.getvalue()


class NewMapArgumentTests(unittest.TestCase):
    def test_new_map_and_patch_lists_go_together(self):
        self.assertEqual(NewMaps(None).keys, set())
        for keys, patches in (([NEW], []), ([], ['a.json']), ([NEW, NEW], ['a.json'])):
            with self.subTest(keys=keys, patches=patches), self.assertRaises(ValueError):
                NewMaps(None, keys, patches)

    def test_cli_rejects_new_map_without_patch_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / 'rom.sfc'
            rom.write_bytes(fixture().d)
            doc = Path(tmp) / 'doc.json'
            doc.write_text('{"format": "dq5chest/1"}', encoding='utf-8')
            cases = ((reloc, 'check', '--new-map', '36/00'), (write, 'check', doc, '--new-map', '36/00'),
                     (place, 'check', doc, '--new-map', '36/00'), (reloc, 'check', '--with-patch', doc))
            for module, *args in cases:
                with self.subTest(module=module.__name__, args=args):
                    code, text = run(module, rom, *args)
                    self.assertEqual(code, 1)
                    self.assertIn('--with-patch', text)
            for module, *args in ((reloc, 'check', '--new-map', '36/0'), (write, 'check', '--new-map', '3g/00')):
                with self.subTest(module=module.__name__, args=args):
                    self.assertEqual(run(module, rom, *args)[0], 2)


@unittest.skipUnless(ROM.is_file(), '롬 없음')
class NewMapRomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = Rom(ROM.read_bytes())
        cls.tmp = tempfile.TemporaryDirectory()
        cls.newmap = Path(cls.tmp.name) / 'newmap.dq5patch.json'
        manifest = dq5newmap.patch(cls.rom, NEWMAP, at={'entrance': 0x3EC000}, allow_doors=True)
        cls.newmap.write_text(json.dumps(manifest), encoding='utf-8')
        cls.new = NewMaps(cls.rom, [NEW], [cls.newmap])
        cls.extended = Rom(build(cls.rom.d, [load(str(cls.newmap))], manifest.get('rom_size', 0))[0])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def tables(self):
        doc = reloc.parse(self.rom)
        doc['chest_maps'].append({'group': 0x36, 'map': 0, 'count': 2})
        doc['chests'] += [{'reward': 0x200}, {'reward': 0x201}]
        doc['search'].append({'group': 0x36, 'map': 0, 'x': 8, 'y': 21, 'unused': 1, 'reward': 0x202,
                              'flag_index': 0x0B, 'mask': 0x01})
        doc['ahead'].append({'group': 0x36, 'map': 0, 'x': 20, 'y': 19, 'reward': 0x203,
                             'flag_index': 0x2E, 'mask': 0x04})
        return doc

    AT = {'chests': 0x3F8000, 'chest_maps': 0x3F9000, 'search': 0x3FA000, 'ahead': 0x3FB000}

    def test_new_map_must_be_added_by_the_patch_list(self):
        for keys, message in (([(0x36, 1)], '붙인 롬에도 없는'), ([(0x31, 3)], '이미 롬에 있는'),
                              ([(0x50, 0x52)], '그룹 50 미만')):
            with self.subTest(keys=keys), self.assertRaisesRegex(ValueError, message):
                NewMaps(self.rom, keys, [self.newmap])
        # 새 맵이 이미 들어간 롬에서는 원래 롬의 맵처럼 읽으므로 알리지 않는다
        with self.assertRaisesRegex(ValueError, '이미 롬에 있는'):
            NewMaps(self.extended, [NEW], [self.newmap])

    def test_reloc_reads_new_map_cells_and_builds_with_patch_list(self):
        doc = self.tables()
        with self.assertRaisesRegex(ValueError, '존재하지 않는 맵'):
            reloc.writes_for(self.rom, doc, self.AT)
        writes, mb = reloc.writes_for(self.rom, doc, self.AT, self.new)
        self.assertEqual(mb, 2)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            reloc.check(self.rom, doc, self.AT, self.new)
        self.assertIn('새 맵 1개', out.getvalue())
        wrong = self.tables()
        wrong['chest_maps'][-1]['count'] = 1
        wrong['chests'].pop()
        with self.assertRaisesRegex(ValueError, '상자 셀 2개'):
            reloc.writes_for(self.rom, wrong, self.AT, self.new)
        outside = self.tables()
        outside['ahead'][-1]['x'] = 54
        with self.assertRaisesRegex(ValueError, '54×38 밖'):
            reloc.writes_for(self.rom, outside, self.AT, self.new)
        # 들어가는 곳 표 자리(3E:C000)는 새 맵 패치가 쓰므로 한 빌드로 합치면 겹친다
        with self.assertRaisesRegex(ValueError, '한 빌드로 합치지 못함'):
            reloc.patch(self.rom, doc, self.AT | {'chests': 0x3EC000}, self.new)

    def test_extended_rom_gives_same_table_writes(self):
        doc = self.tables()
        plain, _ = reloc.writes_for(self.rom, doc, self.AT, self.new)
        again, mb = reloc.writes_for(self.extended, doc, self.AT)
        self.assertEqual(mb, 2)
        self.assertEqual([(a, n) for a, n, _, _ in again], [(a, n) for a, n, _, _ in plain])
        # 이미 늘린 롬에서는 다른 패치가 쓴 뱅크 끝 앞쪽을 빈 자리로 보지 않는다
        with self.assertRaisesRegex(ValueError, '어느 한 곳에도 들지 않음'):
            reloc.writes_for(self.extended, doc, self.AT | {'chests': 0x3EC000})

    def test_fixed_tables_can_point_at_new_map(self):
        doc = {'format': write.FORMAT,
               'chest_maps': [{'index': i, 'group': 0x36, 'map': 0} for i, row in
                              enumerate(write.dump(self.rom, False)['chest_maps']) if (row['group'], row['map']) == (0x31, 3)],
               'search': [{'index': i, 'group': 0x36, 'map': 0} for i, row in enumerate(write.dump(self.rom, False)['search'])
                          if (row['group'], row['map']) == (0x31, 3)]}
        self.assertEqual((len(doc['chest_maps']), len(doc['search'])), (1, 2))
        with self.assertRaisesRegex(ValueError, '존재하지 않는 맵'):
            write.patch(self.rom, doc)
        self.assertEqual(len(write.patch(self.rom, doc, self.new)['writes']), 3)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            write.check(self.rom, doc, self.new)
        self.assertIn('새 맵 1개', out.getvalue())

    def test_place_takes_cells_of_new_map(self):
        doc = {'format': place.FORMAT, 'maps': [{'map': '36/00', 'chests': [
            {'x': 10, 'y': 17, 'reward': 0x201}, {'x': 8, 'y': 17, 'reward': 0x200}],
            'furniture': [{'x': 8, 'y': 21, 'reward': 0x202, 'flag_index': 0x0B, 'mask': 0x01}]}]}
        base = reloc.parse(self.rom)
        base['ahead'].append(self.tables()['ahead'][-1])
        maps, _, mb, tables, new = place.plan(self.rom, doc, None, self.AT, base, self.new)
        self.assertEqual((maps, mb), ([], 2))
        self.assertEqual(tables, self.tables())
        # 상자 번호는 셀 순서라 적은 순서와 달리 (8,17) 이 먼저다
        self.assertEqual(new, [(0x36, 0, (8, 17), 0x200), (0x36, 0, (10, 17), 0x201)])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            place.check(self.rom, doc, None, self.AT, base, self.new)
        self.assertIn('놓은 2개', out.getvalue())

    def test_place_rejects_new_map_input(self):
        def one(**item):
            return {'format': place.FORMAT, 'maps': [{'map': '36/00', **item}]}
        box = {'x': 8, 'y': 17, 'reward': 1}
        other = {'x': 10, 'y': 17, 'reward': 2}
        jar = {'x': 8, 'y': 21, 'reward': 3, 'flag_index': 0x0B, 'mask': 1}
        for doc, message in ((one(chests=[box | {'block': 384}, other]), 'block 을 놓지 않음'),
                             (one(chests=[box]), '모두 한 번씩'), (one(chests=[box, box, other]), '모두 한 번씩'),
                             (one(furniture=[jar]), '모두 한 번씩'),
                             (one(chests=[box, other], furniture=[jar | {'x': 9}]), '가구 칸'),
                             (one(chests=[box, other], furniture=[jar, jar]), '두 번'),
                             (one(chests=[box, {'x': 60, 'y': 17, 'reward': 2}]), '맵 54×38 밖'),
                             ({'format': place.FORMAT, 'maps': [{'map': '01/02', 'chests': [
                                 {'x': 36, 'y': 26, 'block': 384, 'reward': 1}]}]}, '--map-at')):
            with self.subTest(doc=doc), self.assertRaisesRegex(ValueError, message):
                place.plan(self.rom, doc, None, self.AT, None, self.new)
        with self.assertRaisesRegex(ValueError, '그룹 50 미만'):
            place.plan(self.rom, one(chests=[box, other]), None, self.AT)
        # 바탕 표에 이미 상자 연결이 있는 새 맵은 한 입력에 모두 적으라고 거부한다
        with self.assertRaisesRegex(ValueError, '바탕 표에 이미 상자 연결이'):
            place.plan(self.rom, one(chests=[box, other]), None, self.AT, self.tables(), self.new)

    def test_place_mixed_and_existing_cell_entries(self):
        mixed = {'format': place.FORMAT, 'maps': [{'map': '01/02', 'chests': [
            {'x': 36, 'y': 26, 'block': 384, 'reward': 1}, {'x': 37, 'y': 27, 'reward': 2}]}]}
        with self.assertRaisesRegex(ValueError, '섞지 않음'):
            place.plan(self.rom, mixed, 0x3E8000, self.AT)
        # 블록 없이 적은 기존 맵은 레코드에 있는 칸에 보상을 단다. 표에 이미 있는 맵이면 한 입력에 모두 적으라고 거부한다
        listed = {'format': place.FORMAT, 'maps': [{'map': '31/03', 'chests': [
            {'x': 8, 'y': 17, 'reward': 1}, {'x': 10, 'y': 17, 'reward': 2}]}]}
        with self.assertRaisesRegex(ValueError, '바탕 표에 이미 상자 연결이'):
            place.plan(self.rom, listed, None, self.AT)

    def test_place_cells_of_unlisted_map(self):
        # 상자 표에 없는 19/00 의 상자 칸 다섯을 블록 없이 모두 적으면 맵 연결을 끝에 붙이고 셀 순서로 번호를 매긴다
        cells = place.chest_cells(self.rom, 0x19, 0)
        self.assertEqual(len(cells), 5)
        doc = {'format': place.FORMAT, 'maps': [{'map': '19/00', 'chests': [
            {'x': x, 'y': y, 'reward': 0x100 + k} for k, (x, y) in enumerate(reversed(cells))]}]}
        at = {'chests': 0x3F8000, 'chest_maps': 0x3F9000}
        _, _, _, tables, new = place.plan(self.rom, doc, None, at)
        self.assertEqual(tables['chest_maps'][-1], {'group': 0x19, 'map': 0, 'count': 5})
        self.assertEqual([xy for _, _, xy, _ in new], cells)
        self.assertEqual(tables['chests'][-5:], [{'reward': 0x104 - k} for k in range(5)])
        with contextlib.redirect_stdout(io.StringIO()):
            place.check(self.rom, doc, None, at)
        short = {'format': place.FORMAT, 'maps': [{'map': '19/00', 'chests': doc['maps'][0]['chests'][1:]}]}
        with self.assertRaisesRegex(ValueError, '모두 한 번씩'):
            place.plan(self.rom, short, None, at)

    def test_place_furniture_only_on_map_with_search_rows(self):
        # 선실 17/00 은 タンス (4,4) 가 서랍 표에 있다. 가구만 적으면 (2,4) 를 서랍 표 끝에 붙인다
        def jar(x):
            return {'format': place.FORMAT, 'maps': [{'map': '17/00', 'furniture': [
                {'x': x, 'y': 4, 'reward': 0x100 + 111, 'flag_index': 0x0B, 'mask': 0x01}]}]}
        _, _, _, tables, new = place.plan(self.rom, jar(2), None, {'search': 0x3FA000})
        self.assertEqual(new, [])
        self.assertEqual(tables['search'][-1], {'group': 0x17, 'map': 0, 'x': 2, 'y': 4, 'unused': 1,
                                                'reward': 0x100 + 111, 'flag_index': 0x0B, 'mask': 0x01})
        self.assertEqual(tables['chest_maps'], reloc.parse(self.rom)['chest_maps'])
        with contextlib.redirect_stdout(io.StringIO()):
            place.check(self.rom, jar(2), None, {'search': 0x3FA000})
        with self.assertRaisesRegex(ValueError, '이미 서랍 항목이 있음'):
            place.plan(self.rom, jar(4), None, {'search': 0x3FA000})

    def test_place_cells_on_extended_rom(self):
        # 새 맵을 이미 붙인 롬에서는 --new-map 없이 블록을 뺀 항목으로 같은 표가 나온다
        doc = {'format': place.FORMAT, 'maps': [{'map': '36/00', 'chests': [
            {'x': 8, 'y': 17, 'reward': 0x200}, {'x': 10, 'y': 17, 'reward': 0x201}],
            'furniture': [{'x': 8, 'y': 21, 'reward': 0x202, 'flag_index': 0x0B, 'mask': 0x01}]}]}
        base = reloc.parse(self.rom)
        base['ahead'].append(self.tables()['ahead'][-1])
        _, plain, _, tables, _ = place.plan(self.rom, doc, None, self.AT, base, self.new)
        _, again, mb, grown, _ = place.plan(self.extended, doc, None, self.AT, base)
        self.assertEqual(grown, tables)
        self.assertEqual(mb, 2)
        self.assertEqual([(a, n) for a, n, _, _ in again], [(a, n) for a, n, _, _ in plain])

    def test_place_tables_in_front_of_record_bank(self):
        # 맵 레코드를 3F:C000 에 두어도 같은 뱅크 앞쪽 3F:8000 은 표 자리로 받는다(빈 자리는 입력 롬으로 봄)
        doc = {'format': place.FORMAT, 'maps': [{'map': '01/02', 'chests': [
            {'x': 36, 'y': 26, 'block': 384, 'reward': 0x4BA}]}]}
        for new in (reloc.NO_NEW_MAPS, self.new):
            with self.subTest(new=bool(new.keys)):
                maps, writes, _, _, _ = place.plan(self.rom, doc, 0x3FC000, {'chests': 0x3F8000}, None, new)
                self.assertTrue(maps)
                self.assertTrue(any(a == 0x3F8000 for a, _, _, _ in writes))
        # 레코드와 겹치는 표는 여전히 거부한다
        with self.assertRaisesRegex(ValueError, '맵 레코드 자리와 겹침'):
            place.plan(self.rom, doc, 0x3F8000, {'chests': 0x3F8010})

    def test_place_rejects_moved_pointer_list(self):
        # 새 맵 패치가 맵 포인터 목록을 옮기면 원래 목록에 쓴 포인터는 읽히지 않는다
        moved = Path(self.tmp.name) / 'moved.dq5patch.json'
        manifest = dq5newmap.patch(self.rom, NEWMAP, at={'entrance': 0x3EC000, 'pointer': 0x3CC000}, allow_doors=True)
        moved.write_text(json.dumps(manifest), encoding='utf-8')
        new = NewMaps(self.rom, [NEW], [moved])
        doc = {'format': place.FORMAT, 'maps': [{'map': '01/02', 'chests': [
            {'x': 36, 'y': 26, 'block': 384, 'reward': 1}]}]}
        with self.assertRaisesRegex(ValueError, '포인터 자리나 값을 바꿈'):
            place.plan(self.rom, doc, 0x3E8000, {'chests': 0x3F8000}, None, new)
        # 같은 자리 목록이면 --with-patch 를 붙인 롬에서 칸을 세어 --new-map 없을 때와 같은 표가 나온다
        plain = place.plan(self.rom, doc, 0x3E8000, {'chests': 0x3F8000})
        withnew = place.plan(self.rom, doc, 0x3E8000, {'chests': 0x3F8000}, None, self.new)
        self.assertEqual(withnew[3], plain[3])
        self.assertEqual(withnew[0], plain[0])

    def test_new_map_on_rom_larger_than_patch_lists(self):
        # 4MB 로 늘린 롬에 2MB 로 적은 새 맵 패치를 붙여도 롬을 줄이지 않는다(빌더의 negative count)
        big = Rom(build(self.rom.d, [load(str(self.newmap))], 4)[0])
        second = Path(self.tmp.name) / 'second.dq5patch.json'
        manifest = dq5newmap.patch(big, {'format': 'dq5newmap/1', 'maps': [
            {'map': '36/01', 'record': {'copy': '31/04'}, 'attrs': {'copy': '31/04'}}]}, allow_doors=True)
        second.write_text(json.dumps(manifest | {'rom_size': 2}), encoding='utf-8')
        new = NewMaps(big, [(0x36, 1)], [second])
        self.assertEqual(len(new.view.d), 0x400000)

    def test_cli_with_new_map(self):
        tmp = Path(self.tmp.name)
        source = tmp / 'tables.json'
        source.write_text(json.dumps(self.tables()), encoding='utf-8')
        places = [arg for name, at in self.AT.items() for arg in (f'--{name.replace("_", "-")}-at', reloc.cpu(at))]
        args = ('--new-map', '36/00', '--with-patch', self.newmap, *places)
        code, text = run(reloc, ROM, 'patch', source, '-o', tmp / 'out.dq5patch.json', *args)
        self.assertEqual(code, 0, text)
        code, text = run(reloc, ROM, 'check', source, *args)
        self.assertEqual(code, 0, text)
        self.assertEqual(run(reloc, ROM, 'check', source, *places)[0], 1)


if __name__ == '__main__':
    unittest.main()
