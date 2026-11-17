"""3장 검사 틀(롬 없이): 3장 걷기 구간 표, 묶음 나누기와 묶음 첫 구간의 flag, npccheck·heroblockcheck·compatcheck 의
3장 몫.

헤드리스 실측은 dq4ch3walkcheck.py·dq4npccheck.py --chapter3·dq4heroblockcheck.py --chapter3·
dq4compatcheck.py walk --chapter3(sfc/dq4/guards.toml 의 dq4-ch3-*).
"""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch2walkcheck as cw  # noqa: E402
import dq4ch3checks  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
import dq4ch3walkcheck as tw  # noqa: E402
import dq4chapterwalk as cwk  # noqa: E402
import dq4heroblockcheck as hb  # noqa: E402
import dq4npccheck as npc  # noqa: E402

ROMS = HERE.parents[2] / 'rom'
TOKEN = re.compile(r'^(\d+,\d+|[a-z]+:\d+)$')
WARP = r'^[0-9A-F]{2}/[0-9A-F]{2},\d+,\d+$'


class ModuleTableTests(unittest.TestCase):
    """사건 모듈 _checks 의 표를 모을 때 이름이 겹쳐 덮이거나, 고정한 차례가 없는 묶음을 가리키지 않는다."""
    def test_order_names_exist(self):
        segs = {n for n, _ in dq4ch3checks.blocks('SEGMENTS', 'SEGMENT_BLOCKS')} | {'common'}
        flags = {n for n, _ in dq4ch3checks.blocks('FLAGS', 'FLAG_BLOCKS')} | set(tw.COMMON_FLAGS)
        self.assertLessEqual(set(tw.SEGMENT_ORDER), segs)
        self.assertLessEqual(set(tw.FLAG_ORDER), flags)

    def test_flag_names_do_not_overwrite(self):
        common = [k for f in tw.COMMON_FLAGS.values() for k in f]
        names = [k for _, f in dq4ch3checks.blocks('FLAGS', 'FLAG_BLOCKS') for k in f]
        self.assertEqual(len(common + names), len(set(common + names)))
        # 공용 금화 칸(GOLD0~2)은 2장 표의 같은 이름을 3장 자리로 덮는다. 사건 flag 는 앞 표를 덮지 않는다
        self.assertEqual(set(names) & set(cw.FLAGS), set())
        self.assertEqual(set(tw.FLAGS), set(cw.FLAGS) | set(common) | set(names))

    def test_new_module_tables_go_last_in_slot_order(self):
        got = dq4ch3checks.ordered([('A', 1), ('B.x', 2), ('C', 3), ('B.y', 4)], ('C', 'B.x'))
        self.assertEqual([n for n, _ in got], ['C', 'B.x', 'A', 'B.y'])

    def test_merged_rejects_duplicate_names(self):
        self.assertEqual(len(hb.chapter3_cases()), sum(len(m.hero_cases()) for _, m in dq4ch3checks.tables()
                                                         if hasattr(m, 'hero_cases')))


class SegmentTableTests(unittest.TestCase):
    def test_segments_are_well_formed(self):
        names = [s[0] for s in tw.SEGMENTS]
        self.assertEqual(len(names), len(set(names)))
        for name, how, arg, opt in tw.SEGMENTS:
            self.assertIn(how, ('warp', 'walk', 'ending'), name)
            for k in (*opt.get('want', ()), *opt.get('off', ()), *opt.get('bytes', {})):
                self.assertIn(k, tw.FLAGS, name)
            if how == 'walk':
                for tok in arg.split(';'):
                    self.assertRegex(tok, TOKEN, name)
            elif how == 'warp':
                self.assertRegex(arg, WARP, name)
            if 'cell' in opt:
                self.assertEqual(len(opt['cell']), 2, name)

    def test_first_unit_starts_at_the_house_and_warps_start_new_units(self):
        groups = tw.units()
        self.assertEqual([i for u in groups for i in u], list(range(len(tw.SEGMENTS))))
        for u in groups[1:]:
            self.assertEqual(tw.SEGMENTS[u[0]][1], 'warp')
        # 첫 묶음은 순간이동 없이 3장 출발 상태(톨네코 집)에서 걷는다
        self.assertEqual(tw.SEGMENTS[0][1], 'walk')
        self.assertIn('CHAPTER3', tw.SEGMENTS[0][3]['want'])

    def test_unit_start_carries_earlier_flags_and_set(self):
        segs = [('a', 'walk', 'up:1', {'want': ['CHAPTER3']}), ('b_side', 'warp', '3E/00,4,26', {}),
                ('b', 'walk', 'up:1', {'off': ['CHAPTER3'], 'set': '2057=FF'}), ('c_side', 'warp', '3E/00,4,26', {})]
        index, mask = ch3.CHAPTER3
        self.assertEqual(tw.setup(1, segs)[0], f'{0x2190 + index:04X}|{mask:02X}')
        # set 은 그 구간 시작에만 두고 뒤 묶음에는 잇지 않는다. off 는 앞 want 를 지운다
        self.assertEqual(tw.setup(3, segs)[0], '')
        self.assertEqual(cwk.units(segs, 0), [[0], [1, 2], [3]])

    def test_house_hop_leaves_the_start_map(self):
        self.assertIn(ch3.HOUSE, tw.HOPS)
        self.assertNotEqual(tw.HOPS[ch3.HOUSE][:5], ch3.HOUSE)

    def test_battle_patch_names_one_monster(self):
        data = bytes(0x120000)
        got = tw.battle_patch(data, 'win:5A')
        self.assertEqual(got, cwk.battle_patch(data, 'win:5A', []))
        self.assertEqual(len(got.split(';')), 4)


class ChapterThreeCaseTests(unittest.TestCase):
    def test_npc_chapter3_groups(self):
        # 3장 맵 그룹은 늘어나므로(굴 47·여우 마을 48 등) 처음 셋을 포함하고, 모두 LINKS 의 "chapter": 3 인지만 본다
        self.assertLessEqual({'3E', '3F', '40'}, set(npc.CHAPTER3_GROUPS))
        for g in npc.CHAPTER3_GROUPS:
            self.assertTrue(any(p.get('chapter') == 3 for p in npc.LINKS[int(g, 16)]), g)
        self.assertEqual(npc.CHAPTER2_GROUPS, npc.chapter_groups(2))

    def test_heroblock_chapter3_cases_are_well_formed(self):
        cases = hb.chapter3_cases()
        self.assertTrue(cases)
        for name, case in cases.items():
            for tok in case['walk'].split(';'):
                self.assertRegex(tok, TOKEN, name)
            self.assertRegex(case['warp'], WARP, name)
            # 출발 상태가 톨네코 집이라 같은 맵으로 가려면 다른 맵을 들러야 한다
            if case['warp'].split(',')[0] == ch3.HOUSE:
                self.assertRegex(case.get('hop', ''), WARP, name)
                self.assertNotEqual(case['hop'][:5], ch3.HOUSE, name)

    @unittest.skipUnless((ROMS / 'dq5.sfc').is_file() and (ROMS / 'dq4.nes').is_file(), '롬 없음')
    def test_compat_chapter3_groups_cover_every_segment_once(self):
        import dq4ch1walkcheck as wc
        import dq4ch2walkcheck as cw
        import dq4compatcheck as compat
        segs, groups, ch2_at, ch3_at = compat.chapter3_parts()
        head, unit = tw.head_segments()
        self.assertEqual(head[-1][0], 'ch3_open')
        self.assertEqual(ch2_at, cw.KING_INDEX + cw.HEAD)
        self.assertEqual(ch3_at, cw.KING_INDEX + len(head))
        flat = [i for u in groups for i in u]
        self.assertEqual(len(flat), len(set(flat)))
        self.assertEqual(flat[-len(tw.SEGMENTS):], list(range(ch3_at, ch3_at + len(tw.SEGMENTS))))
        self.assertEqual([segs[i][0] for i in groups[2]], [head[i][0] for i in unit])
        self.assertEqual(segs[:cw.KING_INDEX], wc.SEGMENTS[:cw.KING_INDEX])


if __name__ == '__main__':
    unittest.main()
