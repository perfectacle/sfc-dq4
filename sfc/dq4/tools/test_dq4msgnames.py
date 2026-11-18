import unittest
from pathlib import Path

import dq4msgnames as names


def target(code, at):
    d = code[at + 1]
    return at + 2 + (d - 256 if d > 127 else d)


class HookTests(unittest.TestCase):
    def setUp(self):
        self.hook = names.Layout({k: {0: '곤봉'} for k in names.KINDS}).hook({k: 0x9100 for k in names.KINDS})
        self.none = self.hook.index(bytes((0x28, 0xA5, 0xF5, 0x48)))
        self.found = self.hook.index(bytes((0xA0, 0x00, 0x00)))

    def test_mode_check_goes_to_original_path(self):
        self.assertEqual(self.hook[:3], bytes((0x85, 0x43, 0x08)))
        self.assertEqual(target(self.hook, 5), self.none)

    def test_each_kind_branches(self):
        at = 7
        for _ in names.KINDS:
            self.assertEqual(self.hook[at], 0xC9)
            nxt = target(self.hook, at + 2)
            beq = self.hook.index(bytes((0xF0,)), at + 4)
            self.assertEqual(target(self.hook, beq), self.none)
            self.assertEqual(self.hook[beq + 9], 0x80)
            self.assertEqual(target(self.hook, beq + 9), self.found)
            at = nxt
        self.assertEqual(at, self.none)

    def test_none_path_pops_the_number_and_returns_after_the_hook(self):
        # 89BB~89BF 는 훅의 JML·NOP 이라, 덮인 JSR $889F 를 대신하고 그 다음 24:89C0 으로 간다
        none = self.hook[self.none:self.found]
        self.assertEqual(none[-4:], bytes((0x5C, *names.le(0x2489C0, 3))))
        self.assertIn(bytes((0xA5, 0xF6, 0x85, 0xF5)), none)

    def test_copy_loop_returns_to_load(self):
        bne = self.hook.index(bytes((0xC9, 0xFF, 0xFF, 0xD0)), self.found) + 3
        self.assertEqual(target(self.hook, bne), self.found + 3)
        self.assertEqual(self.hook[-4:], bytes((0x5C, *names.le(names.QUEUE_RUN, 3))))

    def test_monster_exit_pops_its_handler_frame(self):
        # {100F}(24:8506)은 PHX / PHY / PHP 뒤 JSR $89B6 이라 몬스터만 PLP / PLY / PLX 를 더 꺼낸 뒤 대기열로 간다.
        # 이것이 빠지면 격투장 116 이 몬스터 이름 뒤에서 멈춘다
        at = self.hook.index(bytes((0xA5, 0x43, 0xC9, names.MONSTER, 0xD0)), self.found)
        monster = self.hook[at + 6:target(self.hook, at + 4)]
        self.assertEqual(monster, bytes((0x68, 0x68, 0xC2, 0x20, 0x68, 0x28, 0x7A, 0xFA, 0xC2, 0x30,
                                         0x5C, *names.le(names.QUEUE_RUN, 3))))
        self.assertIn(names.MONSTER, names.KINDS)


ROM = Path(__file__).resolve().parents[3] / 'rom' / 'dq5.sfc'


@unittest.skipUnless(ROM.is_file(), 'local source ROM not present')
class NumberedTests(unittest.TestCase):
    def test_borrowed_slots_take_their_fc_names(self):
        # 빌린 주문 칸(1D·38)은 롬 이름이 DQ5 マホキテ·シャナク 라 이름으로는 한글이 없고, 메시지 「{100B}을/를」 이 가나와
        # 받침 없는 조사로 찍혔다. 창 글자·전투 글과 같은 번호 덮기가 메시지에도 든다
        import dq4party
        import dq4windowtext
        got = names.korean_names(ROM.read_bytes())
        self.assertEqual({n: got[3][n] for n in dq4party.BORROWED_SPELLS}, dq4party.korean_names())
        for kind, table in dq4windowtext.numbered_names(window=False).items():
            if kind in (3, 5):
                self.assertLessEqual(table.items(), got[kind].items(), kind)


if __name__ == '__main__':
    unittest.main()
