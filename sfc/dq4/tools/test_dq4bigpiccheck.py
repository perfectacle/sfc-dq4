"""롬 없이: 전투 큰 그림 길 검사의 기록 읽기·덩어리 나누기·판정."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4bigpiccheck as bp  # noqa: E402

LOG = '\n'.join([
    '10 8952 00 0', '11 8952 0A 0', '11 msg 05E', '12 8952 08 -1', '13 8952 0A 2', '14 8952 00 0',
    '15 inj 4 6 before differs after same at 11', '16 8926 00 0', '17 8952 04 0', '18 8952 00 0',
])

# 하위 스크립트 02 를 고른 뒤 메시지 063 까지의 효과: 4 NMI 길, 한 NMI 쉼, 11 NMI 길
EFFECT = ['100 sub 02'] + [f'{101 + i} 8952 {k} 0' for i, k in enumerate(
    ['0A', '08', '0A', '0A', '00'] + ['0A', '08', '0A'] * 3 + ['0A', '08', '00'])] + ['118 msg 063', '119 8952 0A 0']
ORIG = {0x02: (11, 15)}


def inject(at, wait, before=False, after=True):
    return (100, 100 + wait, before, after, at)


class ParseTest(unittest.TestCase):
    def test_reads_battle_nmis_messages_injections_and_subscripts(self):
        nmis, msgs, injects, subs = bp.parse(LOG + '\n9 sub 12')
        self.assertEqual(nmis, [(10, 0, 0), (11, 0x0A, 0), (12, 0x08, -1), (13, 0x0A, 2), (14, 0, 0), (17, 4, 0), (18, 0, 0)])
        self.assertEqual(msgs, [(11, 0x5E)])
        self.assertEqual(injects, [(4, 6, False, True, 11)])
        self.assertEqual(subs, [(9, 0x12)])

    def test_runs_split_on_the_normal_path(self):
        nmis, msgs, _, _ = bp.parse(LOG)
        found = bp.runs(nmis, msgs)
        self.assertEqual([(r['frame'], r['length'], r['kinds'], r['queued'], r['message'], r['sub']) for r in found],
                         [(11, 3, ['0A', '08', '0A'], 1, '05E', None), (17, 1, ['04'], 0, '05E', None)])
        self.assertEqual(found[0]['frames'], [11, 12, 13])

    def test_a_run_at_the_end_is_kept(self):
        self.assertEqual(len(bp.runs([(1, 0x0A, 0)], [])), 1)

    def test_runs_after_a_subscript_belong_to_it_until_the_next_message(self):
        nmis, msgs, _, subs = bp.parse('\n'.join(EFFECT))
        found = bp.runs(nmis, msgs, subs)
        self.assertEqual([(r['length'], r['sub']) for r in found], [(4, 2), (11, 2), (1, None)])
        self.assertEqual(bp.effect_shape(found, 2), (11, 15))


class JudgeTest(unittest.TestCase):
    def found(self, *lengths, sub=None):
        out, frame = [], 0
        for n in lengths:
            out.append({'length': n, 'frame': frame, 'frames': list(range(frame, frame + n)), 'message': None,
                        'sub': sub})
            frame += n + 1
        return out

    def test_passes_within_the_limit(self):
        injects = [inject(0, 1)] * bp.INJECT
        self.assertEqual(bp.judge(self.found(1, bp.LIMIT), injects, ORIG), (bp.LIMIT, 1, []))

    def test_a_run_outside_an_effect_fails_over_the_limit(self):
        self.assertTrue(bp.judge(self.found(bp.LIMIT + 1), [inject(0, 1)] * bp.INJECT, ORIG)[2])

    def test_an_effect_run_is_held_to_the_original_length(self):
        injects = [inject(0, 1)] * bp.INJECT
        self.assertEqual(bp.judge(self.found(11, sub=2), injects, ORIG)[2], [])
        self.assertTrue(bp.judge(self.found(12, sub=2), injects, ORIG)[2])
        self.assertTrue(bp.judge(self.found(4, sub=4), injects, ORIG)[2])     # 표에 원본 길이가 없음

    def test_an_unmatched_subscript_falls_back_to_the_limit(self):
        injects = [inject(0, 1)] * bp.INJECT
        sub = next(iter(bp.UNMATCHED))
        self.assertEqual(bp.judge(self.found(bp.LIMIT, sub=sub), injects, ORIG)[2], [])
        self.assertTrue(bp.judge(self.found(bp.LIMIT + 1, sub=sub), injects, ORIG)[2])

    def test_an_item_may_wait_out_the_rest_of_its_run_plus_after(self):
        found = self.found(11, sub=2)                      # 프레임 0~10
        rest = [inject(0, 1)] * (bp.INJECT - 1)
        self.assertEqual(bp.judge(found, [inject(3, 8 + bp.AFTER)] + rest, ORIG)[2], [])
        self.assertTrue(bp.judge(found, [inject(3, 9 + bp.AFTER)] + rest, ORIG)[2])

    def test_an_item_put_outside_a_run_fails(self):
        self.assertTrue(bp.judge(self.found(1), [inject(5, 1)] + [inject(0, 1)] * (bp.INJECT - 1), ORIG)[2])

    def test_fails_unless_vram_changed_to_the_picture(self):
        good = [inject(0, 1)] * (bp.INJECT - 1)
        self.assertTrue(bp.judge(self.found(1), good + [inject(0, 1, before=True)], ORIG)[2])
        self.assertTrue(bp.judge(self.found(1), good + [inject(0, 1, after=False)], ORIG)[2])

    def test_fails_when_items_did_not_go_out(self):
        self.assertTrue(bp.judge(self.found(1), [inject(0, 1)], ORIG)[2])


class EffectTest(unittest.TestCase):
    def setUp(self):
        self.nmis, self.msgs, _, self.subs = bp.parse('\n'.join(EFFECT))
        self.item = (100, 101, False, True, 116)            # 11 NMI 길의 마지막 NMI

    def test_the_forced_effect_matches_the_original(self):
        self.assertEqual(bp.judge_effect(2, self.nmis, self.msgs, [self.item], self.subs, ORIG), ((11, 15), []))

    def test_one_more_request_fails(self):
        self.assertTrue(bp.judge_effect(2, self.nmis, self.msgs, [self.item], self.subs, {0x02: (11, 14)})[1])

    def test_a_longer_run_fails_even_with_the_same_total(self):
        self.assertTrue(bp.judge_effect(2, self.nmis, self.msgs, [self.item], self.subs, {0x02: (10, 15)})[1])

    def test_the_effect_must_be_reached_and_fed_an_item(self):
        self.assertTrue(bp.judge_effect(4, self.nmis, self.msgs, [self.item], self.subs, ORIG)[1])
        self.assertTrue(bp.judge_effect(2, self.nmis, self.msgs, [], self.subs, ORIG)[1])


class TableTest(unittest.TestCase):
    def test_every_reachable_subscript_has_an_original_length(self):
        orig = bp.load_orig()
        self.assertEqual(sorted(orig), list(bp.SUBSCRIPTS))
        self.assertTrue(all(0 < longest <= total for longest, total in orig.values()))

    def test_the_table_round_trips(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 't.toml'
            bp.write_orig({0x02: (11, 18), 0x00: (4, 8)}, path)
            self.assertEqual(bp.load_orig(path), {0x00: (4, 8), 0x02: (11, 18)})


class FinishTest(unittest.TestCase):
    def test_battle_is_made_to_end_before_the_frame_cap(self):
        """회복하는 무리와의 전투는 난수에 따라 MAXF 를 넘으므로, 그 전에 몬스터 HP 를 1 로 묶는 프레임을 Lua 에 넘긴다.
        묶은 뒤 셋까지 쓰러뜨릴 여유(실측 4천여 프레임)를 MAXF 앞에 둔다."""
        self.assertLessEqual(bp.FINISH_AT + 6000, bp.MAXF)
        lua = bp.PROBE.read_text(encoding='utf-8')
        self.assertIn("os.getenv('FINISH_AT')", lua)
        self.assertIn('0x7E07C0', lua)

    def test_the_probe_forces_and_logs_the_subscript(self):
        lua = bp.PROBE.read_text(encoding='utf-8')
        self.assertIn('0x22EA46', lua)
        self.assertIn("os.getenv('SUBSCRIPT')", lua)


if __name__ == '__main__':
    unittest.main()
