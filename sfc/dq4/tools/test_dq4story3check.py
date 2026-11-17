"""3장 한 줄 걷기 구간 표(dq4story3)와 판정(dq4story3check.problems_of)을 롬 없이 본다."""
import re
import unittest

import dq4story3 as story
import dq4story3check as check

TOKEN = re.compile(r'^(\d+,\d+|(up|down|left|right|wait):\d+|face:(up|down|left|right)|talk|free|yes\*?|no|await|fight|close|field|'
                   r'cmd:[a-z,]+|msg:[0-9A-F]+|win:[0-9A-F/]+|map:[0-9A-F]{2}/[0-9A-F]{2}|near:[0-9A-F]{2}|'
                   r'pick:[0-9A-F]{4}=[0-9A-F]{2}|see:[0-9A-F]{4}=[0-9A-F]{2}|serve:[0-9A-F]{4}>=[0-9A-F]{4}|'
                   r'until:[0-9A-F]{4}>=[0-9A-F]{4},[a-z]+,[a-z]+)$')
OPTIONS = {'part', 'map', 'cell', 'field', 'want', 'off', 'items', 'no_items', 'bytes', 'gold_min', 'rng', 'battle', 'fight',
           'maxf', 'tokmax', 'gold', 'give', 'why', 'side'}


class StoryTable(unittest.TestCase):
    def test_names_unique_and_tokens_known(self):
        names = [n for n, _, _ in story.SEGMENTS]
        self.assertEqual(len(names), len(set(names)))
        for name, toks, opt in story.SEGMENTS:
            self.assertLessEqual(set(opt), OPTIONS, name)
            if toks.startswith('ending:'):
                continue
            for tok in toks.split(';'):
                self.assertRegex(tok, TOKEN, f'{name}: {tok}')

    def test_flags_exist(self):
        for name, _, opt in story.SEGMENTS:
            for k in [*opt.get('want', ()), *opt.get('off', ()), *opt.get('bytes', {})]:
                self.assertTrue(k in story.FLAGS or k in ('GOLD', 'TIME'), f'{name}: {k}')

    def test_only_gold_and_delivery_weapons_are_written(self):
        """써 넣기는 금화와 납품 무기뿐이고, 모두 까닭과 함께 표에 나온다."""
        for name, _, opt in story.SEGMENTS:
            for slot, item in opt.get('give', ()):
                self.assertIn(item, story.ALLOWED_ITEMS, name)
            sets = story.writes_set(opt)
            for tok in filter(None, sets.split(';')):
                addr = int(tok.split('=')[0], 16)
                gold = range(story.ch3.GOLD_AT & 0xFFFF, (story.ch3.GOLD_AT & 0xFFFF) + 3)
                slots = range(story.ITEM_SLOT, story.ITEM_SLOT + 12)
                self.assertTrue(addr in gold or addr in slots, f'{name}: {tok}')
        self.assertEqual({w['segment'] for w in story.writes()},
                         {n for n, _, o in story.SEGMENTS if 'gold' in o or 'give' in o})
        with self.assertRaises(ValueError):
            story.writes_set({'give': [(4, 0xBC)], 'why': 'x'})
        with self.assertRaises(ValueError):
            story.writes_set({'gold': 1})

    def test_parts_cover_table_in_order(self):
        idx = [i for _, ii in story.parts() for i in ii]
        self.assertEqual(idx, list(range(len(story.SEGMENTS))))
        self.assertTrue(story.SEGMENTS[-1][1].startswith('ending:'))
        keys = check.part_keys('root', 0)
        self.assertEqual(keys, check.part_keys('root', 0))
        self.assertNotEqual([k for *_, k in keys], [k for *_, k in check.part_keys('root', 5)])

    def test_no_warp_or_flag_writes(self):
        """순간이동 구간이 없고(모두 걷기 토막), 써 넣기 선택 밖의 SET 이 없다."""
        for name, toks, opt in story.SEGMENTS:
            self.assertNotIn('set', opt, name)
            self.assertNotIn('warp', toks, name)


class Judge(unittest.TestCase):
    TEXT = 'f00010 token 4,4\nf00020 end map 3E/00 x=4 y=53\nSEEN=02\nGOLD=000126\nBE=80\nITEMS0=FFFFFFFFBB42\nITEMS1=FFFFFFFFFFFF\n'

    def test_pass_and_fail(self):
        flags = {'SEEN': (0x7E2200, 0x02)}
        ok, seen = check.problems_of(self.TEXT, {'map': '3E/00', 'cell': (4, 53), 'want': ['SEEN'], 'gold_min': 0x126,
                                                 'items': [0xBB], 'field': False}, flags)
        self.assertEqual(ok, [])
        self.assertEqual(seen['GOLD'], 0x126)
        bad, _ = check.problems_of(self.TEXT.replace('f00010 token', 'f00011 fail stuck at 1,1 heading 2,2\nf00010 token'),
                                   {'cell': (4, 55), 'off': ['SEEN'], 'no_items': [0xBB]}, flags)
        self.assertEqual(len(bad), 4)
        self.assertIn('stuck at 1,1 heading 2,2', bad)


if __name__ == '__main__':
    unittest.main()
