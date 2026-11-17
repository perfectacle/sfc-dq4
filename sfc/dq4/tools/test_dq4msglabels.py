"""메시지 이름표(dq4msglabels): 번호가 밀려도 같고, 글이 바뀌면 다르고, 같은 글도 사건 이름으로 갈린다(롬 없이)."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1event  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch2event  # noqa: E402
import dq4ch3event  # noqa: E402
import dq4chapter1  # noqa: E402
import dq4msglabels as ml  # noqa: E402

FIXED = {0x129: ['その方向には誰もいない', 4097], 0x186: ['고정 메시지', 4097], 0x187: ['고정 메시지', 4097]}


def build(first, change=None):
    """사건 메시지를 first 부터 빌드처럼 이어 매긴 messages(번호 → 내용). change 는 {번호: 내용} 덮어쓰기."""
    out = dict(FIXED)
    out.update(dq4ch1event.texts(first))
    out.update(dq4ch2event.texts(dq4chapter1.chapter2_message(first)))
    out.update(dq4ch3event.texts(dq4chapter1.chapter3_message(first)))
    out.update(change or {})
    return out


class LabelTests(unittest.TestCase):
    def test_shifted_numbers_keep_labels(self):
        a, b = ml.table(build(0xE71)), ml.table(build(0xE71 + 7))
        self.assertEqual({v for k, v in a.items() if k >= 0xE71}, {v for k, v in b.items() if k >= 0xE71})
        first = ml.table(build(0xE71))[0xE71]
        self.assertTrue(first.startswith('ch1.'), first)
        self.assertEqual(ml.table(build(0xE71 + 7))[0xE71 + 7], first)

    def test_changed_text_changes_the_label(self):
        base = build(0xE71)
        changed = build(0xE71, {0xE72: ['바뀐 글', 4097]})
        self.assertNotEqual(ml.table(base)[0xE72], ml.table(changed)[0xE72])
        self.assertEqual(ml.table(base)[0xE72].split('@')[0], ml.table(changed)[0xE72].split('@')[0])

    def test_same_text_in_two_events_stays_apart(self):
        t = ml.table(build(0xE71, {0xE73: dq4ch1event.texts(0xE71)[0xE72]}))
        self.assertNotEqual(t[0xE72], t[0xE73])
        self.assertEqual(t[0xE72].split('@')[1], t[0xE73].split('@')[1])
        # 이름 없는 번호의 같은 글은 번호 차례로 #k
        self.assertEqual((t[0x186], t[0x187]), (t[0x186], t[0x186] + '#2'))

    def test_misplaced_events_are_refused(self):
        bad = build(0xE71)
        for k in range(0xE71, 0xE71 + len(dq4ch1event.MESSAGES)):
            bad.pop(k, None)
        with self.assertRaises(ValueError):
            ml.table(bad)

    def test_unknown_number_fails_the_baseline(self):
        t = ml.table(build(0xE71))
        self.assertEqual(ml.labels(['FFFF', 'truncated'], t), ['?FFFF', 'truncated'])

    def test_baseline_is_written_in_labels(self):
        """기준 파일은 번호가 아니라 이름표다(16진 번호 그대로인 항목이 없음)."""
        for key, e in wc.load_messages().items():
            for m in e['messages']:
                self.assertIn('@', m, (key, m))


if __name__ == '__main__':
    unittest.main()
