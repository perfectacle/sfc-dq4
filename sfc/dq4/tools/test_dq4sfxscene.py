"""dq4sfxscene: 대응표 해석·기대값 계산·대기열 읽기·울림 판정·장면 목록이 대응표를 빠짐없이 맡는지(롬 없이)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4sfxscene as s  # noqa: E402

ARGS = '''--song
06=0E
--fast-receive
--sfx
34-02=131
--sfx-call
05E6A9=35:3F
--sfx-call
01E01B=35:45
--sfx-remap
37-14=45-03
--sfx-weapon
00=43-01
--sfx-weapon-songs
17
--sfx-item
3F-01
--sfx-pcm
40-03=-
--inn-jingle
'''


class TableTest(unittest.TestCase):
    def setUp(self):
        self.t = s.load_table(ARGS)

    def test_parse_options_without_values(self):
        opts = s.parse_args_file(ARGS)
        self.assertIn(('--fast-receive', None), opts)
        self.assertIn(('--inn-jingle', None), opts)
        self.assertIn(('--sfx', '34-02=131'), opts)

    def test_table_fields(self):
        t = self.t
        self.assertEqual(t.sfx, {(0x34, 0x02): '131'})
        self.assertEqual(t.calls, {0x05E6A9: (0x35, 0x3F), 0x01E01B: (0x35, 0x45)})
        self.assertEqual(t.remap, {(0x37, 0x14): (0x45, 0x03)})
        self.assertEqual(t.weapons, {0x00: (0x43, 0x01)})
        self.assertEqual(t.weapon_songs, [0x17])
        self.assertEqual(t.items, [(0x3F, 0x01)])
        self.assertTrue(t.inn_jingle)
        self.assertEqual(t.songs, {0x06: 0x0E})

    def test_routed(self):
        t = self.t
        self.assertEqual(s.routed(t, 0x35, 0x00, 0x05E6A9), (0x3F, 0x00))   # 부르는 자리의 번호만 바뀜
        self.assertEqual(s.routed(t, 0x35, 0x02, 0x01E01B), (0x45, 0x02))
        self.assertEqual(s.routed(t, 0x37, 0x14), (0x45, 0x03))             # 입구에서 돌려 부르기
        self.assertEqual(s.routed(t, 0x34, 0x02), (0x34, 0x02))             # 갈래만 바꾼 것은 번호 그대로
        with self.assertRaises(ValueError):
            s.routed(t, 0x36, 0x00, 0x05E6A9)

    def test_weapon_sound_only_in_weapon_songs(self):
        self.assertEqual(s.weapon_sound(self.t, 0x00, 0x17), (0x43, 0x01))
        self.assertIsNone(s.weapon_sound(self.t, 0x00, 0x18))
        self.assertIsNone(s.weapon_sound(self.t, 0x05, 0x17))

    def test_entries(self):
        self.assertEqual(sorted(self.t.entries()), sorted([
            'sfx 34-02', 'pcm 40-03', 'call 05E6A9', 'call 01E01B', 'remap 37-14', 'weapon 00', 'item 3F-01',
            'inn-jingle']))


class RomCheckTest(unittest.TestCase):
    def test_call_sites(self):
        t = s.load_table(ARGS)
        rom = bytearray(0x400000)
        for addr, new in ((0x05E6A9, 0x3F), (0x01E01B, 0x45)):
            o = s.lorom(addr)
            rom[o:o + 3] = bytes((0x00, 0x16, new))
        self.assertEqual(s.call_site_problems(bytes(rom), t), [])
        rom[s.lorom(0x01E01B) + 2] = 0x35                                   # 원래 번호로 되돌아감
        self.assertEqual(len(s.call_site_problems(bytes(rom), t)), 1)

    def test_weapon_table(self):
        t = s.load_table(ARGS)
        rom = bytearray(0x400000)
        rom[s.lorom(s.WEAPON_SEQ_TABLE):s.lorom(s.WEAPON_SEQ_TABLE) + 0x100] = b'\xff' * 0x100
        rom[s.lorom(s.WEAPON_SEQ_TABLE)] = 0x43
        rom[s.lorom(s.WEAPON_BRANCH_TABLE)] = 0x01
        self.assertEqual(s.weapon_table_problems(bytes(rom), t), [])
        rom[s.lorom(s.WEAPON_BRANCH_TABLE)] = 0x02
        self.assertEqual(len(s.weapon_table_problems(bytes(rom), t)), 1)

    def test_hook_patches(self):
        rom = bytearray(0x400000)
        for site in s.ENTRY_SITES:
            rom[s.lorom(site):s.lorom(site) + 5] = s.ENTRY_BYTES
        patches = dict(s.hook_patches(bytes(rom)))
        self.assertEqual(patches[s.lorom(0x24FFCC)], bytes.fromhex('2200FF7DEA'))
        self.assertEqual(patches[s.lorom(s.HOOK)][-1], 0x6B)                # RTL
        rom[s.lorom(0x34FFCC)] = 0xEA
        with self.assertRaises(ValueError):
            s.hook_patches(bytes(rom))


class QueueTest(unittest.TestCase):
    def test_drain_reads_matching_inverse_only(self):
        shadow, inverse = [0xFF] * 16, [0xFF] * 16
        args, xs = list(range(16)), list(range(0x20, 0x30))
        shadow[3], inverse[3] = 0x0C, 0xF3                                  # 훅이 쓴 칸
        shadow[1], inverse[1] = 0x00, 0x00                                  # 게임이 덮은 칸(보수가 맞지 않음)
        shadow[15], inverse[15] = 0x01, 0xFE
        self.assertEqual(s.drain(14, shadow, inverse, args, xs), [(0x01, 15, 0x2F), (0x0C, 3, 0x23)])

    def test_match_seq_in_order_and_wildcard(self):
        ev = [(10, 0x0C, 0x33, 0x00), (20, 0x01, 0x1D, 0x75), (30, 0x0C, 0x33, 0x00)]
        self.assertEqual(s.match_seq(ev, [(0x0C, 0x33, 0x00), (0x0C, 0x33, 0x00)]), [10, 30])
        self.assertEqual(s.match_seq(ev, [(0x01, 0x1D, None)]), [20])
        self.assertEqual(s.match_seq(ev, [(0x01, 0x1D, None), (0x0C, 0x40, 0x01), (0x0C, 0x33, 0x00)]), [20, None, None])

    def test_key_on(self):
        env = [0, 0, 0, 0x7F, 0x60, 0x30, 0, 0]
        self.assertEqual(s.key_on(env, 1), 3)
        self.assertIsNone(s.key_on([0x7F, 0x60, 0x30, 0x10, 0], 0))        # 줄어들기만 하면 새 울림이 아님
        self.assertIsNone(s.key_on(env, 1, window=1))


class SceneListTest(unittest.TestCase):
    def test_every_table_entry_is_covered(self):
        t = s.load_table(s.ARGS.read_text())
        self.assertEqual(s.uncovered(t, s.scenes(t)), [])

    def test_unreached_are_table_entries(self):
        t = s.load_table(s.ARGS.read_text())
        self.assertEqual(set(s.UNREACHED) - set(t.entries()), set())

    def test_names_unique_and_wants_routed(self):
        t = s.load_table(s.ARGS.read_text())
        scenes = s.scenes(t)
        self.assertEqual(len({x.name for x in scenes}), len(scenes))
        by = {x.name: x for x in scenes}
        self.assertIn((s.SFX, 0x3F, 0x00), by['chest'].want)
        self.assertIn((s.SFX, 0x45, 0x03), by['battle-boss'].want)
        self.assertEqual(len([x for x in scenes if x.name.startswith('weapon-')]), len(t.weapons))


if __name__ == '__main__':
    unittest.main()
