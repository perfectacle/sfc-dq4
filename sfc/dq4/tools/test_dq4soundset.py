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


if __name__ == '__main__':
    unittest.main()
