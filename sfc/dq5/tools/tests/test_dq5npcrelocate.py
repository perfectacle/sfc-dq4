"""인물 레코드 안 스크립트 길이 변경과 낮·밤 공유 경계 검사."""
import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5map import GROUP_TABLE, Rom, lorom  # noqa: E402
from dq5npc import entry_size, parse, script_address  # noqa: E402
from dq5npc import ALT_END, ALT_START, NO_NPC, NPC_GROUPS, OVERRIDE_LISTS, all_lists, script_bytes  # noqa: E402
from dq5npclists import MAP_OBJECTS  # noqa: E402
from dq5npcrelocate import (  # noqa: E402
    BASE_START, FORMAT, GROUP_COUNT, HOOKS, OVERRIDE_COUNT, apply_manifest, banks_of, bank_stub, check,
    condition_writes, cpu, destination, pack_alt, pack_base, pack_region, patch, repack_entry, replacements,
)

OLD, NEW = 0x058000, 0x328000


def fixture(record):
    data = bytearray(0x30000)
    off = lorom(OLD)
    data[off:off + len(record)] = record
    return Rom(data)


def relocated(record):
    data = bytearray(0x200000)
    off = lorom(NEW)
    data[off:off + len(record)] = record
    return Rom(data)


class NpcRelocateTests(unittest.TestCase):
    def test_long_single_script_preserves_prefix(self):
        raw = bytes.fromhex('b0 12 03 04 05 06 07 01 16')
        rom = fixture(raw)
        code = bytes([0x1A] * 24 + [0x16])
        out, mapping = repack_entry(rom, OLD, NEW, {OLD + 7: code})
        self.assertEqual(out[:7], raw[:7])
        self.assertEqual(out[7:], bytes([25]) + code)
        self.assertEqual(mapping, {OLD + 7: NEW + 7})
        self.assertEqual(entry_size(relocated(out), NEW), len(out))

    def test_record_edits_are_copied(self):
        rom = fixture(bytes.fromhex('b0 12 03 04 05 06 07 01 16'))
        edited = bytes.fromhex('b0 34 03 09 05 18 07 01 16')
        out, mapping = repack_entry(rom, OLD, NEW, {OLD + 7: bytes.fromhex('2b 05 0d 16')}, edited)
        self.assertEqual(out, edited[:7] + bytes.fromhex('04 2b 05 0d 16'))
        self.assertEqual(mapping, {OLD + 7: NEW + 7})

    def test_record_length_must_not_change(self):
        rom = fixture(bytes.fromhex('b0 12 03 04 05 06 07 01 16'))
        with self.assertRaises(ValueError):
            repack_entry(rom, OLD, NEW, {}, bytes.fromhex('b0 12 03 04 05 06 07 01 16 00'))

    def test_condition_rows_follow_moved_lists(self):
        data = bytearray(0x98000)
        rows = bytearray()
        for i in range(296):
            rows += bytes([1, 2, 0x1D, 0x10, 0x00, 0x80])
        off = lorom(OVERRIDE_LISTS)
        data[off:off + len(rows)] = rows
        rom = Rom(data)
        edited = {OVERRIDE_LISTS + 6: bytes([1, 3, 0x9D, 0x10, 0x10, 0x80]), NO_NPC: bytes([1, 2, 0x82, 0x80])}
        moved = {0x108000: 0x338000, 0x108010: 0x338020}
        out = condition_writes(rom, edited, moved)
        self.assertEqual(out[0], (OVERRIDE_LISTS + 4, bytes([0x00, 0x80]), '대체 표 0 목록 주소'))
        self.assertEqual(out[1], (OVERRIDE_LISTS + 6, bytes([1, 3, 0x9D, 0x10, 0x20, 0x80]), '대체 표 1 조건과 목록 주소'))
        self.assertNotIn(OVERRIDE_LISTS + 10, [at for at, _, _ in out])
        self.assertEqual(out[-1], (NO_NPC, bytes([1, 2, 0x82, 0x80]), '빈 맵 표 조건'))
        with self.assertRaises(ValueError):
            condition_writes(rom, {OVERRIDE_LISTS: bytes([1, 2, 0x1D, 0x10, 0x01, 0x80])}, moved)

    def test_shared_day_night_script(self):
        raw = bytes.fromhex('f0 ff 12 03 04 05 06 07 01 16')
        rom = fixture(raw)
        out, mapping = repack_entry(rom, OLD, NEW, {OLD + 8: bytes.fromhex('2b 05 0d 16')})
        moved = relocated(out)
        self.assertEqual(len(mapping), 1)
        self.assertEqual(script_address(moved, NEW, False), NEW + 8)
        self.assertEqual(script_address(moved, NEW, True), NEW + 8)
        for night in (False, True):
            a, b = parse(rom, OLD, night), parse(moved, NEW, night)
            self.assertEqual({k: v for k, v in a.items() if k != 'script'}, {k: v for k, v in b.items() if k != 'script'})

    def test_separate_night_script_moves_after_day(self):
        raw = bytes.fromhex('f0 fe 12 03 04 05 06 07 01 16 01 1b')
        rom = fixture(raw)
        out, mapping = repack_entry(rom, OLD, NEW, {OLD + 8: bytes.fromhex('2b 05 0d 16')})
        moved = relocated(out)
        self.assertEqual(mapping[OLD + 10], NEW + 13)
        self.assertEqual(script_address(moved, NEW, True), NEW + 13)
        self.assertEqual(out[-2:], b'\x01\x1b')
        self.assertEqual(entry_size(moved, NEW), len(out))

    def test_next_record_and_list_shift(self):
        raw = bytes.fromhex('b0 12 03 04 05 06 07 01 16 90 21 03 04 05 06 07 00')
        out, lists, scripts, entries = pack_region(fixture(raw), [(OLD, [(OLD, None), (OLD + 9, None)])], NEW, {OLD + 7: b'\x1a\x16'}, prefix=4)
        self.assertEqual(lists[OLD], NEW + 4)
        self.assertEqual(entries[OLD + 9], NEW + 14)
        self.assertEqual(scripts[OLD + 7], NEW + 11)
        self.assertEqual(out[-8:], raw[-8:])
        with self.assertRaises(ValueError):
            pack_region(fixture(raw), [(OLD, [(OLD, None), (OLD + 9, None)])], 0x32FFF0, {OLD + 7: b'\x1a\x16'}, prefix=4)

    def test_absolute_and_fallthrough_rejected(self):
        rom = fixture(bytes.fromhex('b0 12 03 04 05 06 07 01 16'))
        with self.assertRaises(ValueError):
            repack_entry(rom, OLD, NEW, {OLD + 7:bytes.fromhex('04 00 80')})
        with self.assertRaises(ValueError):
            repack_entry(rom, OLD, NEW, {OLD + 7: b'\x1a'})

    def test_input_and_destination_validation(self):
        rom = fixture(bytes.fromhex('b0 12 03 04 05 06 07 01 16'))
        row = {'address':'05:8007','commands':[{'op':'16'}]}
        for doc in (None,[],{}, {'format':FORMAT,'scripts':None}, {'format':FORMAT,'scripts':[row,row]},
                    {'format':FORMAT,'scripts':[dict(row,address='05:8008')]},
                    {'format':FORMAT,'scripts':[dict(row,commands=[{'op':'04','args':[0,128]}])]}):
            with self.assertRaises(ValueError):
                replacements(rom,doc,{OLD + 7})
        self.assertEqual(destination('32:8000'),NEW)
        for v in ('05:8000','60:8000','32:0000','32:10000','32: 800','032:8000'):
            with self.assertRaises(ValueError):
                destination(v)


DAY = bytes.fromhex('84 12 cb 85 0a 2c 44 f0')


class SplitBankTests(unittest.TestCase):
    """목록을 여러 뱅크에 나눌 때의 배치. 인물 하나(9바이트 목록)짜리 목록으로 센다."""
    def setUp(self):
        self.rom = fixture(DAY)
        self.lists = [(f'{g:02X}/00', [(OLD, DAY)]) for g in range(3)]

    def test_single_bank_keeps_one_region(self):
        regions, home, lm, _, _, stub = pack_base(self.rom, self.lists, [0x328000], {}, {}, 3, {})
        self.assertIsNone(stub)
        self.assertEqual([(b, len(r)) for b, r in regions], [(0x328000, 6 + 27)])
        self.assertEqual(set(home.values()), {0x328000})

    def test_pinned_group_and_bank_stub(self):
        regions, home, lm, _, _, stub = pack_base(self.rom, self.lists, [0x328000, 0x348000], {1: 0x34}, {}, 3, {})
        self.assertEqual(home, {0: 0x328000, 1: 0x348000, 2: 0x328000})
        self.assertEqual(lm, {'00/00': 0x328006, '02/00': 0x32800F, '01/00': 0x348006})
        first = regions[0][1]
        table = 0x328000 + 6 + 18 + 1
        self.assertEqual(stub, table + 3)
        self.assertEqual(bytes(first[24:]), bytes([3, 0x32, 0x34, 0x32]) + bank_stub(table))
        self.assertEqual(bank_stub(table), bytes.fromhex('da a6 bc bf 19 80 32 85 a7 fa 6b'))

    def test_groups_fill_banks_in_order(self):
        # 32:FFE0 은 표 6 + 뱅크 표·루틴 15 를 빼면 11바이트라 그룹 00 만 들어간다.
        _, home, _, _, _, _ = pack_base(self.rom, self.lists, [0x32FFE0, 0x34FFE0], {}, {}, 3, {})
        self.assertEqual(home, {0: 0x32FFE0, 1: 0x34FFE0, 2: 0x34FFE0})
        with self.assertRaises(ValueError):
            pack_base(self.rom, self.lists, [0x32FFE0, 0x34FFF0], {}, {}, 3, {})
        with self.assertRaises(ValueError):
            pack_base(self.rom, self.lists, [0x32FFE0], {0: 0x35}, {}, 3, {})

    def test_alt_lists_and_tail_spill(self):
        lists = [(f'new:a{i}', [(OLD, DAY)]) for i in range(3)]
        # 33:FFF0 은 16바이트라 목록 하나, 35:FFE0 은 32바이트라 둘. 꼬리 14바이트까지는 35 의 목록 뒤.
        regions, lm, _, _, table = pack_alt(self.rom, lists, [0x33FFF0, 0x35FFE0], {}, 14)
        self.assertEqual(lm, {'new:a0': 0x33FFF0, 'new:a1': 0x35FFE0, 'new:a2': 0x35FFE9})
        self.assertEqual(table, 0x35FFE0 + 18)
        regions, lm, _, _, table = pack_alt(self.rom, lists, [0x33FFF0, 0x35FFE0, 0x36FFE0], {}, 20)
        self.assertEqual(table, 0x36FFE0)
        self.assertEqual(regions[-1], (0x36FFE0, bytearray()))
        with self.assertRaises(ValueError):
            pack_alt(self.rom, lists, [0x33FFF0, 0x35FFE0], {}, 20)
        with self.assertRaises(ValueError):
            pack_alt(self.rom, lists, [0x33FFF0, 0x35FFF0], {}, 0)

    def test_alt_first_bank_too_small_moves_on(self):
        # 33:FFFC 는 4바이트라 9바이트 목록이 하나도 안 들어가, 모두 다음 뱅크로 간다.
        lists = [(f'new:a{i}', [(OLD, DAY)]) for i in range(2)]
        regions, lm, _, _, _ = pack_alt(self.rom, lists, [0x33FFFC, 0x358000], {}, 0)
        self.assertEqual(lm, {'new:a0': 0x358000, 'new:a1': 0x358009})
        self.assertEqual([b for b, _ in regions], [0x358000])

    def test_bank_lists_validated(self):
        self.assertEqual(banks_of(0x328000, '기본'), [0x328000])
        self.assertEqual(banks_of([0x328000, 0x348000], '기본'), [0x328000, 0x348000])
        for bad in ([], [0x328000, 0x32C000], [0x408000], ['32:8000']):
            with self.assertRaises(ValueError):
                banks_of(bad, '기본')


FILLER = bytes.fromhex('b0 12 03 04 05 06 07 01 16')    # 스크립트 한 바이트(16)를 단 9바이트 인물


def filled_list(size):
    """끝 0 까지 size 바이트인 목록 하나. 마지막 인물의 스크립트 길이로 크기를 맞춘다."""
    body = bytearray()
    while size - 1 - len(body) > 260:
        body += FILLER
    script = size - 1 - len(body) - 8
    return bytes(body + FILLER[:7] + bytes([script]) + b'\x1a' * (script - 1) + b'\x16' + b'\x00')


def full_rom():
    """원본 인물 목록 자리를 그대로 채운 합성 롬: 기본 54그룹 346목록(05:8651~D4B2), 대체 293목록(10:8000~DDB1),
    대체 표 296행, 맵 포인터 그룹 표와 빈 맵 물체 표. 마지막 목록이 남은 자리를 채운다."""
    data = bytearray(0x200000)

    def put(addr, raw):
        data[lorom(addr):lorom(addr) + len(raw)] = raw

    for addr, raw in HOOKS.items():
        put(addr, raw)
    starts = [BASE_START + g for g in range(GROUP_COUNT)]
    last = starts[-1] + 346 - GROUP_COUNT
    put(last, filled_list(NPC_GROUPS - last))
    put(NPC_GROUPS, b''.join((a & 0xFFFF).to_bytes(2, 'little') for a in starts))
    put(ALT_START + 292, filled_list(ALT_END - (ALT_START + 292)))
    rows = b''.join(bytes([i % GROUP_COUNT, 0, 0x1D, 0x10]) + ((ALT_START + i % 292) & 0xFFFF).to_bytes(2, 'little')
                    for i in range(OVERRIDE_COUNT))
    put(OVERRIDE_LISTS, rows + b'\xff')
    # 맵 수는 그룹마다 인물 목록 수와 같다(옮긴 롬은 마지막 그룹의 목록 수를 이 표로 센다)
    low = GROUP_TABLE & 0xFFFF
    first = low - 3 * 346
    put(GROUP_TABLE, b''.join((first + 3 * g).to_bytes(2, 'little') for g in range(GROUP_COUNT)))
    put(0x1FCEB6, (0xCEB6).to_bytes(2, 'little') * 5)
    put(MAP_OBJECTS, b'\xff')
    return Rom(data), last


class FullPatchTests(unittest.TestCase):
    """patch 전체: 원본 꼴 롬의 모든 목록을 옮긴 뒤 목록·인물·스크립트가 그대로인지, 길이를 바꾼 뒤가 밀리는지."""

    @classmethod
    def setUpClass(cls):
        cls.rom, cls.last = full_rom()
        cls.lists = all_lists(cls.rom)

    def test_fixture_has_the_original_list_count(self):
        self.assertEqual(len(self.lists), 346 + 293)

    def test_untouched_relocation_passes_the_checker(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            check(self.rom)
        self.assertIn('목록 639개', out.getvalue())

    def test_writes_restore_on_the_original_and_repoint_the_loader(self):
        manifest, layout = patch(self.rom, {'format': FORMAT, 'scripts': []})
        moved = apply_manifest(self.rom, manifest)
        at = {w['at']: bytes.fromhex(w['hex']) for w in manifest['writes']}
        self.assertEqual(at['12:8021'], b'\x32')
        self.assertEqual(at['12:8051'], b'\x00\x80')
        self.assertEqual(at['12:833C'], b'\x33')
        # 32:8000 의 그룹 포인터는 옮긴 그룹 첫 목록을 가리키고, 목록 이름·수는 원본과 같다
        table = [moved.u16(0x328000 + g * 2) for g in range(GROUP_COUNT)]
        self.assertEqual(table, [int(layout['lists'][cpu(BASE_START + g)].replace(':', ''), 16) & 0xFFFF
                                 for g in range(GROUP_COUNT)])
        self.assertEqual(table[0], 0x8000 + GROUP_COUNT * 2)
        self.assertEqual(layout['base_bytes'], GROUP_COUNT * 2 + NPC_GROUPS - BASE_START)
        self.assertEqual(layout['alt_bytes'], ALT_END - ALT_START)
        for addr, _ in self.lists:
            target = int(layout['lists'][cpu(addr)].replace(':', ''), 16)
            self.assertIn(target >> 16, (0x32, 0x33))
        bad = dict(manifest)
        bad['writes'] = [dict(w, orig='00') if w['at'] == '12:8021' else w for w in manifest['writes']]
        with self.assertRaises(ValueError):
            apply_manifest(self.rom, bad)

    def test_longer_script_shifts_only_what_follows(self):
        slot = self.last + 7
        code = [{'op': '1a'}] * 20 + [{'op': '16'}]
        manifest, layout = patch(self.rom, {'format': FORMAT, 'scripts': [{'address': cpu(slot), 'commands': code}]})
        moved = apply_manifest(self.rom, manifest)
        new_slot = int(layout['scripts'][cpu(slot)].replace(':', ''), 16)
        self.assertEqual(script_bytes(moved, new_slot), b'\x1a' * 20 + b'\x16')
        start = int(layout['lists'][cpu(self.last)].replace(':', ''), 16)
        self.assertEqual(new_slot, start + 7)
        # 같은 목록의 다음 인물은 20바이트 밀리고, 기본 영역 전체도 20바이트 는다
        self.assertEqual(int(layout['entries'][cpu(self.last + len(FILLER))].replace(':', ''), 16),
                         start + len(FILLER) + 20)
        self.assertEqual(layout['base_bytes'], GROUP_COUNT * 2 + NPC_GROUPS - BASE_START + 20)
        self.assertEqual(int(layout['lists'][cpu(BASE_START + 1)].replace(':', ''), 16), 0x328000 + GROUP_COUNT * 2 + 1)
        after = all_lists(moved)
        self.assertEqual(len(after), len(self.lists))
        self.assertEqual([n for _, n in after[:346]], [n for _, n in self.lists[:346]])

    def test_bank_choices_are_checked(self):
        doc = {'format': FORMAT, 'scripts': []}
        with self.assertRaisesRegex(ValueError, '다른 뱅크'):
            patch(self.rom, doc, base=0x328000, alt=0x32C000)
        # 기본 목록 20KB 는 32:F000 뒤 4KB 에 들지 않는다
        with self.assertRaises(ValueError):
            patch(self.rom, doc, base=0x32F000)


if __name__ == '__main__':
    unittest.main()
