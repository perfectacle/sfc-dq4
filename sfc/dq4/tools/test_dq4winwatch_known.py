"""dq4winwatch 알려진 깨짐 눈금(Known) 단위 테스트: 눈금과 꼭 같은 걸림만 실패에서 빠진다."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4winwatch as ww  # noqa: E402
import dq4winrule_align as align  # noqa: E402

GAUGE = ww.Known('*/equip-ch3', frozenset({(5, 19)}), 7, '시험 눈금')
RULE = SimpleNamespace(NAME='커서', MODE='fail', ALLOW=(), KNOWN=(GAUGE,))
SHOT = SimpleNamespace(id=17, hs=0, vs=0, map=tuple([0] * 1024))


def cell(r, c, frames, rule='커서', mode='fail'):
    return (r, c, rule, '시험', mode, frames)


class KnownTest(unittest.TestCase):
    def judge(self, cells, scene='equip-ch3', found=None, rules=(RULE,)):
        if found is None:
            found = [(SHOT, 789, max(c[5] for c in cells), cells)] if cells else []
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / scene
            folder.mkdir()
            with mock.patch.object(ww, 'analyze', return_value=found), \
                    mock.patch.object(ww, 'run_hits', return_value=[]), \
                    mock.patch.object(ww, 'rules', return_value=list(rules)), \
                    mock.patch.object(ww, 'picture', return_value=[]), \
                    mock.patch.dict('os.environ', {'DQ4_WINDOW_WATCH': 'rules'}):
                _, failing = ww.report(folder, b'')
                return failing, (folder / ww.LOG).read_text(encoding='utf-8')

    def test_exact_gauge_is_known_not_failing(self):
        failing, log = self.judge([cell(5, 19, 7)])
        self.assertEqual(failing, 0)
        self.assertIn('알려진 깨짐', log)

    def test_longer_than_gauge_fails(self):
        self.assertGreater(self.judge([cell(5, 19, 8)])[0], 0)

    def test_shorter_than_gauge_fails_to_lower_it(self):
        failing, log = self.judge([cell(5, 19, 6)])
        self.assertGreater(failing, 0)
        self.assertIn('내리거나', log)

    def test_gauge_not_hit_fails(self):
        self.assertEqual(self.judge([])[0], 1)

    def test_other_cell_fails(self):
        self.assertGreater(self.judge([cell(5, 19, 7), cell(6, 19, 7)])[0], 0)

    def test_other_scene_ignores_gauge(self):
        self.assertEqual(self.judge([], scene='shopwho')[0], 0)
        self.assertEqual(self.judge([cell(5, 19, 7)], scene='shopwho')[0], 1)

    def test_same_cell_in_shorter_shots_is_measured_by_the_longest(self):
        found = [(SHOT, 100, 3, [cell(5, 19, 3)]), (SHOT, 789, 7, [cell(5, 19, 7)])]
        self.assertEqual(self.judge(None, found=found)[0], 0)

    def test_report_cells_do_not_count(self):
        self.assertEqual(self.judge([cell(5, 19, 7), cell(4, 29, 7, '테두리', 'report')])[0], 0)


PAIR = '창 (4, 3, 10, 12) 과 (4, 2, 12, 13) 의 왼쪽 변이 한 칸 어긋남'


class PairTest(unittest.TestCase):
    """변 어긋남은 장면·칸이 아니라 어긋난 창 짝으로 알려진 깨짐을 가른다."""

    def setUp(self):
        # 실제 PAIRS 는 고치면 비므로 시험용 짝 하나를 둔다
        key = (frozenset({(4, 3, 10, 12), (4, 2, 12, 13)}), '왼쪽')
        patcher = mock.patch.dict(align.PAIRS, {key: 'E: 명령 창 위 장비 「누구」 창'}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def judge(self, why, scene='any-scene'):
        hit = (4, 3, align.NAME, why, 'fail', 123)
        return KnownTest.judge(self, [hit], scene=scene, rules=(align,))

    def test_known_pair_in_any_scene_and_either_order(self):
        for why in (PAIR, '창 (4, 2, 12, 13) 과 (4, 3, 10, 12) 의 왼쪽 변이 한 칸 어긋남'):
            failing, log = self.judge(why)
            self.assertEqual(failing, 0)
            self.assertIn('알려진 깨짐 변 어긋남 최대 123프레임: E:', log)

    def test_unknown_pair_fails(self):
        self.assertEqual(self.judge('창 (4, 3, 10, 11) 과 (4, 2, 12, 13) 의 왼쪽 변이 한 칸 어긋남')[0], 1)

    def test_known_pair_on_the_other_side_fails(self):
        self.assertEqual(self.judge(PAIR.replace('왼쪽', '오른쪽'))[0], 1)


if __name__ == '__main__':
    unittest.main()
