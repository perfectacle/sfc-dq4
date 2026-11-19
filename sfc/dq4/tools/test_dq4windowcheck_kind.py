"""창 깨짐 검사의 장면 나눔: 무작위 입력 장면은 main 머지 뒤 가드, 나머지 결정적 장면은 PR 가드."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dq4windowcheck as wc  # noqa: E402


class KindTest(unittest.TestCase):
    def names(self):
        return [s[0] for s in wc.scenes('s', 'p', 'sh', 'b')]

    def test_random_scenes_are_the_fuzz_and_sweep_ones(self):
        got = {n for n in self.names() if wc.is_random(n)}
        self.assertIn('talk00', got)
        self.assertIn('talk3F', got)
        self.assertEqual({n for n in got if n.startswith('ship')}, {'ship1', 'ship2', 'ship3', 'ship4'})
        self.assertEqual({n for n in got if n.startswith(('party', 'battle'))}, {'party21', 'party22', 'battle11', 'battle12'})

    def test_deterministic_scenes_stay_in_the_pr_guard(self):
        fixed = {n for n in self.names() if not wc.is_random(n)}
        self.assertEqual(fixed, {'shopwho', 'shopflip', 'talk02-full', 'ruler', 'partyitems'})

    def test_new_scene_names_default_to_the_pr_guard(self):
        for n in ('give-bag', 'sell-armor', 'equip-ring', 'partyspell', 'partytactic', 'partyitems', 'talk02-full'):
            self.assertFalse(wc.is_random(n), n)

    def test_every_scene_is_in_exactly_one_kind(self):
        names = self.names()
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len([n for n in names if wc.is_random(n)]) + len([n for n in names if not wc.is_random(n)]),
                         len(names))


if __name__ == '__main__':
    unittest.main()
