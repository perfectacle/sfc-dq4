"""곡 뒤 샘플 전송 계획(순서·곡 앞 샘플 수·도착 어림)을 검사한다."""
import unittest

import dq4soundset as soundset


class TransferPlanTests(unittest.TestCase):
    FIRST = {0x26: 0, 0x27: 0, 0x28: 100, 0x29: 5000}
    NOTES = {0x26: 10, 0x27: 50, 0x28: 5, 0x29: 1}
    SIZES = {0x26: 1000, 0x27: 2000, 0x28: 590, 0x29: 1180}

    def test_orders_by_first_use_then_note_count(self):
        order, _, _ = soundset.transfer_plan(self.FIRST, self.NOTES, self.SIZES, 0)
        self.assertEqual(order, [0x27, 0x26, 0x28, 0x29])

    def test_pre_bytes_cap_is_a_prefix(self):
        _, k, arrivals = soundset.transfer_plan(self.FIRST, self.NOTES, self.SIZES, 3500)
        self.assertEqual(k, 2)
        self.assertEqual(set(arrivals), {0x28, 0x29})
        # 첫 샘플이 커서 상한에 안 들면 뒤의 작은 샘플도 앞으로 보내지 않는다
        _, k, _ = soundset.transfer_plan(self.FIRST, self.NOTES, self.SIZES, 1500)
        self.assertEqual(k, 0)

    def test_arrivals_accumulate_after_song_start(self):
        _, _, arrivals = soundset.transfer_plan(self.FIRST, self.NOTES, self.SIZES, 3000)
        rate, slack, fps = soundset.STREAM_BYTES_PER_FRAME, soundset.ARRIVAL_SLACK_FRAMES, soundset.FRAME_RATE
        self.assertAlmostEqual(arrivals[0x28], (590 / rate + slack) / fps)
        self.assertAlmostEqual(arrivals[0x29], (1770 / rate + slack) / fps)


def detail(source, rate, size):
    return {'source': source, 'base_midi': 60, 'envelope': {'adsr1': 0xFF, 'adsr2': 0xE0}, 'source_loop': [0, 16],
            'effective_rate': rate, 'resource_bytes': size}


class ShareSamplesTests(unittest.TestCase):
    def setUp(self):
        self.resources, self.known = {}, {}
        first = {0x26: b'A' * 100, 0x27: b'B' * 50}
        details = {'26': detail('a.wav', 8000, 100), '27': detail('b.wav', 6000, 50)}
        found, _, _, _ = soundset.share_samples(first, details, {}, self.resources, self.known, 0x26)
        self.resources.update(found)

    def test_identical_bytes_reuse_the_id(self):
        found, mapping, remap, loose = soundset.share_samples(
            {0x26: b'B' * 50}, {'26': detail('b.wav', 6000, 50)}, {5: [{'lo': 0, 'hi': 127, 'sample': 0x26}]},
            self.resources, self.known, 0x28)
        self.assertEqual(remap, {0x26: 0x27})
        self.assertEqual(mapping[5][0]['sample'], 0x27)
        self.assertEqual(loose, [])

    def test_strict_mode_does_not_share_other_rates(self):
        _, _, remap, _ = soundset.share_samples({0x26: b'a' * 75}, {'26': detail('a.wav', 6000, 75)}, {},
                                                self.resources, self.known, 0x28)
        self.assertEqual(remap, {0x26: 0x28})

    def test_loose_mode_takes_a_higher_rate_only_within_budget(self):
        args = ({0x26: b'a' * 75}, {'26': detail('a.wav', 6000, 75)}, {}, self.resources, self.known, 0x28)
        _, _, remap, loose = soundset.share_samples(*args, budget=100, loose=True)
        self.assertEqual(remap, {0x26: 0x26})
        self.assertEqual(loose[0]['used_rate'], 8000)
        _, _, remap, _ = soundset.share_samples(*args, budget=99, loose=True)
        self.assertNotEqual(remap[0x26], 0x26)

    def test_loose_mode_takes_a_lower_rate_one_step_down(self):
        _, _, remap, _ = soundset.share_samples({0x26: b'b' * 70}, {'26': detail('b.wav', 8000, 70)}, {},
                                                self.resources, self.known, 0x28, budget=60, loose=True)
        self.assertEqual(remap, {0x26: 0x27})
        _, _, remap, _ = soundset.share_samples({0x26: b'b' * 90}, {'26': detail('b.wav', 9000, 90)}, {},
                                                self.resources, self.known, 0x28, budget=60, loose=True)
        self.assertEqual(remap, {0x26: 0x28})


if __name__ == '__main__':
    unittest.main()
