"""dq4heroblockcheck.make_base 가 성 마을에 닿은 상태만 돌려주는지(에뮬레이터 없이 순간이동 결과를 흉내 냄)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4heroblockcheck as hb  # noqa: E402


class MakeBaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.hub = self.out / 'hub'

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, warp):
        """warp(dest, env): 순간이동 한 번이 dest 에 남기는 것을 흉내 낸다. 나머지 실행은 아무것도 남기지 않는다."""
        def run(mesence, rom, script, dest, env, timeout, readset=False):
            # 출발 상태를 만드는 실행은 읽은 바이트 캐시를 거친다
            self.assertTrue(readset)
            if script == hb.wc.WARP:
                warp(Path(dest), env)
        with mock.patch.object(hb.wc, 'prologue_start', return_value=self.out / 'start.mss'), \
                mock.patch.object(hb.wc, 'run', side_effect=run), mock.patch.object(hb, 'warp_exit', return_value=0):
            return hb.make_base('mesence', self.out / 'x.sfc', self.out)

    @staticmethod
    def leave(dest, arrived):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / 'end.mss').write_bytes(b'MSS')
        (dest / 'warp.txt').write_text(f'arrived map {arrived}\n' if arrived else 'timeout\n', encoding='utf-8')

    def test_arrived_at_the_hub_is_returned(self):
        base, cached = self.make(lambda dest, env: self.leave(dest, hb.HUB[:5]))
        self.assertEqual(base, self.hub / 'end.mss')
        self.assertFalse(cached)

    def test_state_left_without_arriving_is_refused(self):
        with self.assertRaises(SystemExit):
            self.make(lambda dest, env: self.leave(dest, None))

    def test_state_on_another_map_is_refused(self):
        with self.assertRaises(SystemExit):
            self.make(lambda dest, env: self.leave(dest, '36/01'))

    def test_old_state_in_the_same_out_is_not_reused(self):
        self.leave(self.hub, hb.HUB[:5])
        with self.assertRaises(SystemExit):
            self.make(lambda dest, env: None)


if __name__ == '__main__':
    unittest.main()
