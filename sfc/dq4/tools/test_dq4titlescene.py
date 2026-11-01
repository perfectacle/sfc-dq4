"""dq4titlescene: 이름 조합·지우기 모델, 자모판 길 찾기, 이름 바이트(롬 없이)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4nameentry as ne  # noqa: E402
import dq4nameentrycheck as nec  # noqa: E402
import dq4titlescene as ts  # noqa: E402


def typed(keys):
    m = ts.NameModel()
    for k in keys:
        if k == '<':
            m.back()
        elif k != '!':
            m.press(k)
    return m


class NameModelTest(unittest.TestCase):
    def test_matches_mesence_cases(self):
        # dq4nameentrycheck 가 MesenCE 로 롬 루틴과 견주는 사례와 같은 결과
        for keys, want in nec.CASES:
            with self.subTest(keys=keys):
                self.assertEqual(typed(keys).text(), want)

    def test_matches_compose_without_back(self):
        for keys in ('ㄹㅏㅇㅣㅇㅏㄴ', 'ㄱㅏㅂㅅㅏ', 'ㅋㅡㄹㅣㅍㅡㅌㅡ', 'ㄷㅏㄹㄱㅏ'):
            want = ''.join(ne.GLYPHS[g] for g in ne.compose(keys))
            self.assertEqual(typed(keys).text(), want)

    def test_back_after_split_leaves_initial(self):
        # 라잉 + ㅏ 는 라이 + 아 로 나뉘고, 지우면 받침으로 돌아가지 않고 초성 ㅇ 만 남는다
        self.assertEqual(typed('ㄹㅏㅇㅣㅇㅏ<').text(), '라이ㅇ')

    def test_fifth_char_rejected(self):
        m = typed('ㄹㅏㅇㅣㅇㅏㄴㄷㅏㄹ')
        self.assertEqual(m.text(), '라이안달')
        self.assertFalse(m.press('ㅏ'))
        self.assertEqual(m.text(), '라이안달')

    def test_scene_keys(self):
        m = ts.NameModel()
        accepted = []
        for k in ts.KEYS:
            if k in (ts.BACK_KEY, ts.ERASE_CELL):
                m.back()
            else:
                accepted.append(m.press(k))
        self.assertEqual(m.text(), '라이안다')
        self.assertEqual(accepted.count(False), 1)


class BoardTest(unittest.TestCase):
    def test_board_keys(self):
        keys = ts.board_keys()
        self.assertEqual(len(keys), len(ne.GRID) * ne.ROW_CELLS)
        self.assertEqual(keys.index(ne.JAMO.index(ne.CURSOR_START)), 11)   # 둘째 줄 첫 칸(이름 입력 첫 커서 0B 실측)
        self.assertIn(ne.BACK, keys)
        self.assertIn(ne.DONE, keys)

    def test_route_reaches_every_key(self):
        keys = ts.board_keys()
        nav = ne.navigation(keys)
        start = keys.index(ne.JAMO.index(ne.CURSOR_START))
        n = len(keys)
        for goal, k in enumerate(keys):
            if k == ne.NONE:
                continue
            at = start
            for d, nxt in ts.route(nav, start, goal):
                at = nav[ts.DIRS.index(d) * n + at]
                self.assertEqual(at, nxt)
            self.assertEqual(at, goal)

    def test_name_bytes(self):
        self.assertEqual(ts.name_bytes('라이안'), b''.join(ne.code_bytes(ne.GLYPHS.index(c)) for c in '라이안') + b'\x01\x01')
        self.assertEqual(ne.decode_name(ts.name_bytes('라이안다')), '라이안다')

    def test_slot_diff(self):
        self.assertEqual(ts.slot_diff(b'abcd', b'abXd'), [2])


if __name__ == '__main__':
    unittest.main()
