import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4people  # noqa: E402
import dq4peoplematchcheck as m  # noqa: E402

KINDS = {'노인': '노인', '여자': '여자', '남자': '남자', '농부': '남자', '개': '동물', '고양이': '동물',
         m.UNSEEN: m.UNSEEN}


def doc(allow=()):
    return {'kinds': KINDS, 'fc': {'13': '여자', '16': '노인', '14': '남자', '25': '고양이', '5E': m.UNSEEN},
            'sfc': {'03': '남자', '20': '개'}, 'roles': {'노인': '노인', '농부': '농부'}, 'allow': list(allow)}


def person(picture, x=16, y=71, night=False, talk=0x0F):
    return {'picture': picture, 'night': night, 'x': x // 2, 'y': y // 2, 'talk': talk, 'shows': [],
            'dq5': {'x': x, 'y': y}}


class JudgeTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(m.judge('노인', '노인', KINDS), '맞음')
        # 사람 갈래가 같으면 종류가 달라도 실패가 아니다(남자 → 농부)
        self.assertEqual(m.judge('남자', '농부', KINDS), '비슷함')
        # 여자를 노인 그림으로 싣는 것(1장 바트랜드의 프레아)은 어긋남
        self.assertEqual(m.judge('여자', '노인', KINDS), '어긋남')
        # 사람이 아닌 갈래는 종류까지 같아야 한다
        self.assertEqual(m.judge('고양이', '개', KINDS), '어긋남')
        self.assertEqual(m.judge(m.UNSEEN, '남자', KINDS), '건너뜀')


class CueTest(unittest.TestCase):
    def test_cues(self):
        self.assertEqual(m.cue('かいぶつだって{LINE}まちのなか　までは{LINE}はいってこれないわ{END}'), '여자')
        self.assertEqual(m.cue('わしも　おしろに　つかえたいのう。{END}'), '노인')
        self.assertEqual(m.cue('ねえ　おじちゃん　だしてよ。{END}'), '아이')
        # 「うみぞいを」 의 ぞい, 「じゃない」 는 노인 말투가 아니다
        self.assertEqual(m.cue('うみぞいをいくと　イムルのむら{END}'), '')
        self.assertEqual(m.cue('そうじゃないか{END}'), '')

    def test_disagree(self):
        self.assertTrue(m.cue_disagrees('여자', '노인'))
        self.assertFalse(m.cue_disagrees('', '노인'))


class ValidateTest(unittest.TestCase):
    def test_repo_table(self):
        d = m.load_kinds()
        self.assertEqual(m.validate(d), [])
        # dq4people 가 세트를 바꿔 넣는 역할마다 종류가 있어야 한다(없으면 검사가 그 롬에서 멈춤)
        roles = {p.role for p in dq4people.PEOPLE if p.pictures != dq4people.LEADER_PICTURES}
        self.assertEqual(roles - d['roles'].keys(), set())

    def test_problems(self):
        bad = {'kinds': {'노인': '사람'}, 'fc': {'13': '여자', '3': '노인'}, 'allow': [{'map': '36/00'}]}
        problems = m.validate(bad)
        self.assertEqual(len(problems), 4)


class CompareTest(unittest.TestCase):
    def rows(self, gfx=0x09):
        return [{'map': '36/00', 'list': '기본', 'night': False, 'x': 16, 'y': 71, 'gfx': gfx}]

    def run_compare(self, fc, gfx=0x09, allow=(), sets=None):
        index = m.fc_index({'36/00': [person(fc)]}, {})
        sets = sets or {0x8D: '노인'}
        return m.compare(self.rows(gfx), index, doc(allow), lambda group, g: 0x8D if g == 0x09 else 0x40, sets)[0]

    def test_woman_as_old_man(self):
        r = self.run_compare(0x13)
        self.assertEqual((r['result'], r['want'], r['kind'], r['set']), ('어긋남', '여자', '노인', 0x8D))

    def test_old_man(self):
        self.assertEqual(self.run_compare(0x16)['result'], '맞음')

    def test_allow(self):
        allow = [{'map': '36/00', 'fc': '13', 'gfx': '09', 'reason': '근거'}]
        r = self.run_compare(0x13, allow=allow)
        self.assertEqual((r['result'], r['reason']), ('허용', '근거'))

    def test_original_set(self):
        # 바꿔 넣은 세트가 아니면 DQ5 원래 그림의 종류로 본다
        r = self.run_compare(0x25, gfx=0x20)
        self.assertEqual((r['kind'], r['source'], r['result']), ('개', 'DQ5 원래', '어긋남'))

    def test_no_pair(self):
        index = m.fc_index({'36/00': [person(0x13, night=True)]}, {})
        r = m.compare(self.rows(), index, doc(), lambda group, g: 0x8D, {0x8D: '노인'})[0]
        self.assertEqual(r['result'], '짝 없음')

    def test_alt_list_map(self):
        index = m.fc_index({'after_boss-3600': [person(0x16)]}, {'after_boss-3600': '36/00'})
        self.assertIn((False, 16, 71), index['36/00'])

    def test_unknown_role(self):
        with self.assertRaises(SystemExit):
            m.actual_kind(0x09, 0x8D, {0x8D: '모르는 역할'}, doc())


class HookTest(unittest.TestCase):
    def test_table_without_hook(self):
        # 훅이 없는 롬은 그림 → 세트 표(25:86D0)를 그대로 읽는다
        from dq5map import lorom
        rom = bytearray(0x130000)
        rom[lorom(0x2586D0 + 0x09)] = 0x8D
        self.assertEqual(m.hook_set(bytes(rom), 0x36, 0x09), 0x8D)


if __name__ == '__main__':
    unittest.main()
