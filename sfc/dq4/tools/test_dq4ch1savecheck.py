import unittest

import dq4ch1savecheck as sc
import dq4ch1walkcheck as wc


class Ch1SaveCheckTests(unittest.TestCase):
    def test_points_are_walk_segments(self):
        segments = [s[0] for s in wc.SEGMENTS]
        names = [n for n, _ in sc.POINTS]
        self.assertEqual(len(names), len(set(names)))
        for _, segment in sc.POINTS:
            self.assertIn(segment, segments)

    def test_talk_ends_before_the_save_dump(self):
        total = sum(int(t.split(':')[1]) for t in sc.TALK.split(','))
        self.assertLess(total, sc.SAVED - 50)

    def test_used_talks_stop_at_used_slots(self):
        table = bytearray(0x40)
        table[8], table[0x28] = 0x05, 0x0A
        table[9], table[0x29] = 0xC4, 0x08
        table[10] = 0x99                   # 앞 맵이 남긴 값
        got = {(1, sc.TALKS): bytes(table), (1, sc.USED_SLOTS): bytes([10])}
        self.assertEqual(sc.used_talks(got, 1), ['A05', '8C4'])

    def test_flags_read_from_save_area(self):
        ram = bytearray(0xAA0)
        address, mask = wc.FLAGS['CHAPTER1']
        ram[(address & 0xFFFF) - 0x2000] = mask
        self.assertEqual(sc.flags(ram), ['CHAPTER1'])


class RunFailureTests(unittest.TestCase):
    """저장·이어 하기 장면이 실패한 까닭을 「덤프가 모자람」 대신 종료 코드대로 알린다."""

    def test_messages(self):
        import dq4readset as rs
        self.assertIsNone(sc.run_failure({'timed_out': False, 'returncode': 0}, 900))
        self.assertIn('900초', sc.run_failure({'timed_out': True, 'returncode': None}, 900))
        self.assertIn('시간 제한', sc.run_failure({'timed_out': False, 'returncode': rs.LUA_WATCHDOG}, 900))
        self.assertIn('Lua 오류', sc.run_failure({'timed_out': False, 'returncode': rs.LUA_ERROR}, 900))
        self.assertIn('134', sc.run_failure({'timed_out': False, 'returncode': 134}, 900))

if __name__ == '__main__':
    unittest.main()
