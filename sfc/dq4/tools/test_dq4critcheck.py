"""dq4critcheck: 판정 기록 읽기, 첫 판정 확인, 난수 고정 바이트(롬 없이)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4critcheck as c  # noqa: E402


class CritCheck(unittest.TestCase):
    def test_parse(self):
        text = '\n'.join(['384 enter 10F5=00 100E=00', '384 f41 49=00 reads=0765,0767', '384 have C=0', '384 crit',
                          '500 enter 10F5=00 100E=80', '500 nocrit'])
        got = c.parse(text)
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0], {'enter': {'10F5': '00', '100E': '00'}, 'f41': '00', 'reads': ['0765', '0767'],
                                  'have': '0', 'result': 'crit'})
        self.assertEqual(got[1], {'enter': {'10F5': '00', '100E': '80'}, 'result': 'nocrit'})

    def test_first_must_be_hero(self):
        hero = [{'enter': {'10F5': '00'}, 'result': 'nocrit'}]
        self.assertEqual(c.first_problems(hero, 'nocrit'), [])
        self.assertIn('기대', c.first_problems(hero, 'crit')[0])
        self.assertIn('몬스터', c.first_problems([{'enter': {'10F5': '81'}, 'result': 'nocrit'}], 'nocrit')[0])
        self.assertIn('칸 1', c.first_problems([{'enter': {'10F5': '01'}, 'result': 'nocrit'}], 'nocrit')[0])
        self.assertEqual(c.first_problems([], 'crit'), ['회심 판정을 지나지 않음'])

    def test_roll_bytes(self):
        # 늘 회심: LDA #$20 의 값(20:C6B3)을 01, 회심 없음: CMP #$00 의 값(20:C6B9)을 FF
        self.assertEqual(c.roll('always'), '1046B3=01')
        self.assertEqual(c.roll('never'), '1046B9=FF')
        o = c.SITE_BYTES
        self.assertEqual(o[0x20C6B3 - c.SITE], 0x20)
        self.assertEqual(o[0x20C6B9 - c.SITE], 0x00)
        self.assertEqual(o[0x20C6B8 - c.SITE], 0xC9)

    def test_cases(self):
        self.assertEqual([x[0] for x in c.CASES], ['always', 'never', 'flag100e', 'state1a', 'items'])
        self.assertEqual({x[4] for x in c.CASES}, {'crit', 'nocrit'})


if __name__ == '__main__':
    unittest.main()
