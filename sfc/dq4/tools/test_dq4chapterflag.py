"""장 판별 문(dq4ch3event.CHAPTER3_GATE, 7E:2208 bit3)이 3장 밖에서 늘 꺼져 있다는 근거를 지킨다(롬 없이).

모든 롬에 드는 공용 코드가 3장 칸을 빌린 바이트를 이 문으로 가른다(가게 한 번 쓰는 키 등). 그래서 서장·1장·2장의 대화·
인물·이벤트 스크립트와 네이티브는 이 비트를 켜지 않아야 하고, 켜는 네이티브는 2장 끝 → 3장 넘김(dq4ch3event transfer)
하나, 끄는 네이티브는 3장 끝 넘김(dq4ch3tunnel._handover) 하나여야 한다."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

import dq4ch3event as ch3  # noqa: E402

FIRST = 0xF00
INDEX, MASK = ch3.CHAPTER3


def sets_chapter3(node):
    """스크립트 자료 안에서 CHAPTER3 비트를 켜는 명령(대화·이벤트의 flag-on, 인물 명령 10 = OR)."""
    if isinstance(node, dict):
        if node.get('op') == 'flag-on' and node.get('index') == INDEX and node.get('mask', 0) & MASK:
            return True
        if node.get('op') == '10' and list(node.get('args', ()))[:1] == [INDEX] and node['args'][1] & MASK:
            return True
        return any(sets_chapter3(v) for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(sets_chapter3(v) for v in node)
    return False


def long_or(code):
    """네이티브 바이트 안의 LDA 7E:2208 / ORA #(bit3 포함) / STA 7E:2208 수."""
    a = ch3.CHAPTER3_GATE[0].to_bytes(3, 'little')
    n = 0
    for i in range(len(code) - 9):
        if code[i] == 0xAF and code[i + 1:i + 4] == a and code[i + 4] == 0x09 and code[i + 5] & MASK and \
                code[i + 6] == 0x8F and code[i + 7:i + 10] == a:
            n += 1
    return n


class GateTests(unittest.TestCase):
    def test_gate_is_the_chapter3_flag(self):
        self.assertEqual(ch3.CHAPTER3_GATE, (0x7E2208, 0x08))

    def test_chapter1_and_2_scripts_never_set_chapter3(self):
        import dq4ch1event
        import dq4ch2event
        import dq4chapter1 as ch
        import dq4chapterbox
        import dq4prologue
        points = dq4chapterbox.entry_points(ch.scenes(True))
        talks = ([s["body"] for s in dq4prologue.talk_doc()["scripts"]] + dq4ch1event.talk_scripts(FIRST) +
                 dq4ch2event.talk_scripts(ch.chapter2_message(FIRST)))
        # 2장 끝 스크립트는 3장으로 넘기지 않는 판(2장 롬)만: 넘기는 판은 3장 롬에만 든다
        scripts = (dq4prologue.npc_lists()[3] + dq4ch1event.scripts(FIRST, dq4ch2event.native()[1]['transfer']) +
                   dq4ch2event.scripts(ch.chapter2_message(FIRST), points))
        _, at = dq4prologue.native()
        events = [dq4prologue.end_event(at), dq4ch2event.join_event(ch.chapter2_message(FIRST), dq4ch2event.native()[1]),
                  dq4ch2event.altar_event(ch.chapter2_message(FIRST))] + dq4ch2event.event_tokens(ch.chapter2_message(FIRST))
        for name, part, least in (('talks', talks, 50), ('scripts', scripts, 50), ('events', events, 5)):
            with self.subTest(part=name):
                self.assertGreater(len(part), least)
                self.assertFalse(sets_chapter3(part))

    def test_finder_catches_both_forms(self):
        self.assertTrue(sets_chapter3([{"op": "x", "then": [{"op": "flag-on", "index": INDEX, "mask": MASK}]}]))
        self.assertTrue(sets_chapter3({"commands": [{"op": "10", "args": [INDEX, MASK | 1]}]}))
        self.assertFalse(sets_chapter3([{"op": "flag-on", "index": INDEX, "mask": MASK ^ 0xFF}]))

    def test_chapter1_and_2_natives_never_set_chapter3(self):
        import dq4ch1event
        import dq4ch2event
        import dq4prologue
        codes = [dq4prologue.native()[0], dq4ch1event.native()[0], dq4ch2event.native()[0]]
        codes += [c.module.native(c)[0] for c in dq4ch2event.contexts() if hasattr(c.module, 'native')]
        self.assertGreater(len(codes), 3)
        self.assertEqual(sum(long_or(c) for c in codes), 0)

    def test_only_the_transfer_sets_it_and_only_the_handover_clears_it(self):
        import dq4ch3tunnel
        self.assertEqual(long_or(ch3.native()[0]), 1)
        off = ch3._flag_off(ch3.CHAPTER3)
        self.assertIn(off, dq4ch3tunnel._handover())


if __name__ == '__main__':
    unittest.main()
