"""2장 검사 틀(롬 없이): 2장 걷기 구간 표, 묶음 나누기와 묶음 첫 구간의 flag, npccheck·heroblockcheck 의 2장 사례.

헤드리스 실측은 dq4ch2walkcheck.py·dq4npccheck.py --chapter2·dq4heroblockcheck.py --chapter2·
dq4compatcheck.py walk --chapter2(sfc/dq4/guards.toml 의 dq4-ch2-*).
"""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch2walkcheck as cw  # noqa: E402
import dq4compatcheck as compat  # noqa: E402
import dq4heroblockcheck as hb  # noqa: E402
import dq4npccheck as npc  # noqa: E402

TOKEN = re.compile(r'^(\d+,\d+|[a-z]+:\d+)$')


class SegmentTableTests(unittest.TestCase):
    def test_segments_are_well_formed(self):
        names = [s[0] for s in cw.SEGMENTS]
        self.assertEqual(len(names), len(set(names)))
        for name, how, arg, opt in cw.SEGMENTS:
            self.assertIn(how, ('warp', 'walk'), name)
            for k in (*opt.get('want', ()), *opt.get('off', ())):
                self.assertIn(k, cw.FLAGS, name)
            if how == 'walk':
                for tok in arg.split(';'):
                    self.assertRegex(tok, TOKEN, name)
            else:
                self.assertRegex(arg, r'^[0-9A-F]{2}/[0-9A-F]{2},\d+,\d+$', name)
            if 'cell' in opt:
                self.assertEqual(len(opt['cell']), 2, name)

    def test_head_is_chapter1_end_then_opening(self):
        self.assertEqual(cw.SEGMENTS[0], wc.SEGMENTS[cw.KING_INDEX])
        self.assertEqual(cw.SEGMENTS[1], wc.CHAPTER2_END[0])
        name, _, _, opt = cw.SEGMENTS[cw.HEAD - 1]
        self.assertEqual((name, opt['map']), ('opening', ch2.THRONE))
        self.assertIn('OPENING', opt['off'])

    def test_head_deposits_in_chapter1_and_opening_expects_it_cleared(self):
        chain = wc.SEGMENTS[:cw.KING_INDEX] + cw.SEGMENTS[:cw.HEAD]
        sets, _ = wc.setup(chain, cw.KING_INDEX, cw.FLAGS, cw.head_effects())
        for part in cw.CH1_BANK.split(';'):
            self.assertIn(part, sets.split(';'))
        # 1장 검사의 효과(そらとぶくつ 등)도 그대로 남는다
        for v in wc.EFFECTS.values():
            for part in v.get('set', '').split(';'):
                self.assertIn(part, sets.split(';'))
        opt = cw.SEGMENTS[cw.HEAD - 1][3]
        self.assertIn('BANK_HERB', opt['off'])
        self.assertIn('BANK_GOLD', opt['off'])
        self.assertEqual(cw.FLAGS['BANK_HERB'], (ch2.BANK_ITEMS_AT + 0xA1, 0xFF))
        self.assertEqual(opt['items'], [ch2.SILK_ROBE])

    def test_units_split_at_warps_after_the_head(self):
        groups = cw.units()
        self.assertEqual([i for u in groups for i in u], list(range(cw.HEAD, len(cw.SEGMENTS))))
        for u in groups:
            self.assertEqual(cw.SEGMENTS[u[0]][1], 'warp', cw.SEGMENTS[u[0]][0])
            self.assertTrue(all(cw.SEGMENTS[i][1] == 'walk' for i in u[1:]))

    def test_unit_start_sets_flags_of_earlier_segments(self):
        names = [s[0] for s in cw.SEGMENTS]
        sets, _ = cw.setup(names.index('wall_side'))
        for k in ('TALKED_GATE', 'TALKED_BREY', 'TALKED_KIRYL', 'READY'):
            a, m = cw.FLAGS[k]
            self.assertIn(f'{a & 0xFFFF:04X}|{m:02X}', sets, k)
        # 머리 구간의 flag(1장 보고 등)는 2장 출발 상태에 이미 있어 두지 않는다
        a, m = cw.FLAGS['REPORTED']
        self.assertNotIn(f'{a & 0xFFFF:04X}|{m:02X}', sets)
        self.assertEqual(cw.setup(cw.HEAD), ('', ''))

    def test_flags_point_at_the_event_bits(self):
        for k, pair in (('KICKED', ch2.KICKED), ('JOINED', ch2.JOINED), ('TEMPE_ALTAR', ch2.TEMPE_ALTAR)):
            self.assertEqual(cw.FLAGS[k], (0x7E2190 + pair[0], pair[1]))

    def test_same_map_warp_hops(self):
        for u in cw.units():
            name, how, arg, _ = cw.SEGMENTS[u[0]]
            if arg.split(',')[0] == ch2.THRONE:
                self.assertNotEqual(cw.HOPS[ch2.THRONE][:5], ch2.THRONE, name)

    def test_compare_runs_flags_differing_traces(self):
        a = [{'name': 'x', 'trace': '1', 'status': 'passed'}]
        self.assertEqual(cw.compare_runs(a, a), {})
        self.assertIn('x', cw.compare_runs(a, [{'name': 'x', 'trace': '2', 'status': 'passed'}]))
        self.assertIn('_', cw.compare_runs(a, []))


class ChapterTwoCaseTests(unittest.TestCase):
    def test_npc_warp_lands_on_the_talk_cell(self):
        # 2장 롬의 dq5warp 는 TO 한 셀 아래에 내린다. FC (22,8) 의 셀은 (44,17). 그룹 빌드 롬은 TO 그대로라 올리지 않는다
        self.assertEqual(npc.warp_to('3D/01', 22, 8, 1), '3D/01,44,16')
        self.assertEqual(npc.warp_to('3D/01', 22, 8), '3D/01,44,17')
        self.assertEqual(set(npc.CHAPTER2_GROUPS), {'3D', '45'})

    def test_heroblock_chapter2_cases_are_well_formed(self):
        cases = hb.chapter2_cases()
        self.assertTrue({'wall-left', 'wall-no', 'join-down', 'priest-below'} <= set(cases))
        for name, case in cases.items():
            for tok in case['walk'].split(';'):
                self.assertRegex(tok, TOKEN, name)
            self.assertRegex(case['warp'], r'^3D/0[23],\d+,\d+$', name)
            self.assertTrue(case['want'], name)
        self.assertNotIn(set(cases), set(hb.cases()))

    def test_compat_chapter2_groups_cover_every_segment_once(self):
        groups = compat.chapter2_groups()
        flat = [i for u in groups for i in u]
        self.assertEqual(flat, [0, *range(cw.KING_INDEX, cw.KING_INDEX + len(cw.SEGMENTS))])
        self.assertEqual(len(flat), 1 + len(cw.SEGMENTS))
        segs = wc.SEGMENTS[:cw.KING_INDEX] + cw.SEGMENTS
        self.assertEqual([segs[i][0] for i in groups[1]], [s[0] for s in cw.SEGMENTS[:cw.HEAD]])


if __name__ == '__main__':
    unittest.main()
