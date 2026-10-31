import unittest

import dq4chapter1 as ch
import dq4ch1event as ev
import dq4msgwait as mw
import dq4prologue as pro


def msg(m):
    return {"op": "msg", "id": f"{m:03X}"}


def cmd(op, *args):
    return {"op": op, "args": list(args)}


class PlanTests(unittest.TestCase):
    def test_talk(self):
        body = [msg(1), msg(2), {"op": "if", "cond": {"code": "05"}, "then": [msg(3), msg(4)], "else": msg(5)},
                {"op": "flag-on", "index": 0, "mask": 1}]
        wait, keep = mw.plan(talks=[body])
        self.assertEqual(wait, {1, 3})
        self.assertEqual(keep, {2, 4, 5})

    def test_talk_branch_starting_with_message(self):
        body = [msg(1), {"op": "if", "cond": {"code": "1B", "index": 0, "mask": 1}, "then": msg(2)}]
        self.assertEqual(mw.plan(talks=[body])[0], {1})

    def test_talk_call_keeps(self):
        body = [msg(1), {"op": "call", "target": "8000"}, msg(2)]
        self.assertEqual(mw.plan(talks=[body]), (set(), {1, 2}))

    def test_script(self):
        script = [cmd('3F'), cmd('30', 1, 0), cmd('37', 0, 0, 0), cmd('21', 2, 0), cmd('13', 0, 0), cmd('40'),
                  cmd('30', 3, 0), cmd('40'), cmd('21', 4, 0), cmd('32', 5, 0), cmd('37', 0, 0, 0), cmd('16')]
        self.assertEqual(mw.plan(scripts=[script]), ({1}, {2, 3, 4, 5}))

    def test_script_pause(self):
        script = [cmd('30', 1, 0), cmd('30', 9, 0), cmd('30', 2, 0), cmd('34')]
        self.assertEqual(mw.plan(scripts=[script], pauses={9}), ({9}, {1, 2}))

    def test_event(self):
        tokens = [b'\x08\x04', ('msg', 1), ('msg', 2), b'\xff']
        self.assertEqual(mw.plan(events=[tokens]), (set(), {1, 2}))

    def test_conflict(self):
        with self.assertRaises(ValueError):
            mw.plan(talks=[[msg(1)]], scripts=[[cmd('30', 1, 0), cmd('21', 2, 0)]])

    def test_apply_keeps_other_ends(self):
        texts = {1: ['a', mw.LINE_END], 2: ['b', mw.WAIT_END]}
        self.assertEqual(mw.apply(texts, {1, 2}), {1: ['a', mw.WAIT_END], 2: ['b', mw.WAIT_END]})

    def test_apply_rejects_wait_in_kept(self):
        with self.assertRaises(ValueError):
            mw.apply({1: ['a', mw.WAIT_END]}, set(), {1})


class GameTests(unittest.TestCase):
    """서장·1장에서 A 없이 넘어가던 대화 속 자리(헤드리스 실측)가 1010, 대화 끝·조작 풀기 앞과 닫기 대기를 하는
    인물 명령 21·이벤트 명령 60 의 메시지는 1001(실측: 1010 이면 A 를 두 번)."""

    def test_game_plan(self):
        first = 0xF00
        wait, keep = mw.plan(**ch.message_flow(first))
        m = ev.message_ids(first)
        must_wait = {pro.M_FROG_YES, pro.M_FROG_NO, m['king_praise']}
        self.assertLessEqual(must_wait, wait)
        must_keep = {pro.M_SORRY, m['chapter_end'], pro.M_CALL, pro.M_HELP, pro.M_FROG_ASK, pro.M_FROG_STORY, pro.M_SUPPER, ch.MSG_KING,
                     m['hint'], m['king_farewell'], m['hoimin_ask'], pro.M_MORPH, pro.M_MIMIC, pro.M_BYE,
                     pro.M_STORY_BEGINS, ch.MSG_NARRATION, ch.MSG_MINISTER, m['reunion'],
                     *pro.M_SUPPER_LINES}
        self.assertLessEqual(must_keep, keep)
        # 레벨업 줄은 다음 줄 앞의 line_pause 가 ▼ 를 기다려, 마지막 줄 뒤 34 의 닫기 대기와 겹치지 않는다
        self.assertLessEqual({m['level_up'], *(m[f'stat_{k}'] for k, _ in ev.STATS)}, keep)

    def test_game_texts_keep_single_wait(self):
        """닫기 대기를 하는 명령(인물 21·32, 이벤트 60)이나 대화 끝에서 띄우는 메시지의 글이 1010 으로 끝나지 않는다."""
        first = 0xF00
        wait, keep = mw.plan(**ch.message_flow(first))
        import dq4ch2event
        import dq4sysmsg
        texts = {**ch.TEXTS, **pro.TEXTS, **dq4sysmsg.TEXTS, **ev.texts(first),
                 **dq4ch2event.texts(ch.chapter2_message(first))}
        mw.apply(texts, wait, keep)


if __name__ == '__main__':
    unittest.main()
