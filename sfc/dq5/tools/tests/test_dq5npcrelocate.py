"""인물 레코드 안 스크립트 길이 변경과 낮·밤 공유 경계 검사."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5map import Rom, lorom  # noqa: E402
from dq5npc import entry_size, parse, script_address  # noqa: E402
from dq5npcrelocate import FORMAT, destination, pack_region, repack_entry, replacements  # noqa: E402

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
        out, lists, scripts, entries = pack_region(fixture(raw), [(OLD, 'test')], NEW, {OLD + 7: b'\x1a\x16'}, prefix=4)
        self.assertEqual(lists[OLD], NEW + 4)
        self.assertEqual(entries[OLD + 9], NEW + 14)
        self.assertEqual(scripts[OLD + 7], NEW + 11)
        self.assertEqual(out[-8:], raw[-8:])
        with self.assertRaises(ValueError):
            pack_region(fixture(raw), [(OLD, 'test')], 0x32FFF0, {OLD + 7: b'\x1a\x16'}, prefix=4)

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


if __name__ == '__main__':
    unittest.main()
