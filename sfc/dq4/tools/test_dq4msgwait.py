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
        script = [cmd('3F'), cmd('21', 1, 0), cmd('37', 0, 0, 0), cmd('21', 2, 0), cmd('13', 0, 0), cmd('40'),
                  cmd('21', 3, 0), cmd('21', 4, 0), cmd('37', 0, 0, 0), cmd('16')]
        self.assertEqual(mw.plan(scripts=[script]), ({1, 3}, {2, 4}))

    def test_event(self):
        tokens = [b'\x08\x04', ('msg', 1), ('msg', 2), b'\xff']
        self.assertEqual(mw.plan(events=[tokens]), ({1, 2}, set()))
        self.assertEqual(mw.plan(events=[[('msg', 1)]]), (set(), {1}))

    def test_conflict(self):
        with self.assertRaises(ValueError):
            mw.plan(talks=[[msg(1)]], scripts=[[cmd('21', 1, 0), cmd('21', 2, 0)]])

    def test_apply_keeps_other_ends(self):
        texts = {1: ['a', mw.LINE_END], 2: ['b', mw.WAIT_END]}
        self.assertEqual(mw.apply(texts, {1, 2}), {1: ['a', mw.WAIT_END], 2: ['b', mw.WAIT_END]})


class GameTests(unittest.TestCase):
    """서장·1장에서 A 없이 넘어가던 자리(헤드리스 실측)가 1010, 대화 끝·조작 풀기 앞은 1001."""

    def test_game_plan(self):
        first = 0xF00
        wait, keep = mw.plan(**ch.message_flow(first))
        m = ev.message_ids(first)
        must_wait = {pro.M_FROG_YES, pro.M_FROG_NO, pro.M_MORPH, pro.M_MIMIC, pro.M_BYE,
                     pro.M_STORY_BEGINS, ch.MSG_MINISTER, m['reunion'], m['king_praise'], *pro.M_SUPPER_LINES}
        self.assertLessEqual(must_wait, wait)
        must_keep = {pro.M_SORRY, m['chapter_end'], pro.M_CALL, pro.M_HELP, pro.M_FROG_ASK, pro.M_FROG_STORY, pro.M_SUPPER, ch.MSG_KING,
                     m['hint'], m['king_farewell'], m['hoimin_ask']}
        self.assertLessEqual(must_keep, keep)


if __name__ == '__main__':
    unittest.main()
