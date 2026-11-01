import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import headless_slots as hs  # noqa: E402


@unittest.skipIf(hs.fcntl is None, 'flock 없음')
class SlotTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.log = io.StringIO()

    def take(self, **kw):
        return hs.acquire('test', n=2, folder=self.dir, poll=0.02, log=self.log, **kw)

    def test_third_waits_until_release(self):
        a, b = self.take(), self.take()
        self.assertEqual({a.index, b.index}, {0, 1})
        with self.assertRaises(TimeoutError):
            self.take(timeout=0.2)
        got = []
        t = threading.Thread(target=lambda: got.append(self.take(timeout=5)))
        t.start()
        time.sleep(0.2)
        self.assertEqual(got, [])
        a.release()
        t.join(5)
        self.assertEqual(got[0].index, a.index)
        self.assertGreater(got[0].waited, 0.1)
        self.assertIn('기다림', self.log.getvalue())
        b.release()
        got[0].release()

    def test_context_manager_releases(self):
        with hs.slot('test', n=1, folder=self.dir, log=self.log) as s:
            self.assertEqual(s.index, 0)
            self.assertLess(s.waited, 0.1)
        with hs.slot('test', n=1, folder=self.dir, log=self.log, timeout=0) as s:
            self.assertEqual(s.index, 0)

    def test_dead_process_frees_slot(self):
        code = ('import sys, time; sys.path.insert(0, sys.argv[1]); import headless_slots as hs; '
                'hs.acquire("child", n=1, folder=sys.argv[2]); print("held", flush=True); time.sleep(60)')
        child = subprocess.Popen([sys.executable, '-c', code, str(Path(hs.__file__).parent), str(self.dir)],
                                 stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'held')
            with self.assertRaises(TimeoutError):
                hs.acquire('test', n=1, folder=self.dir, timeout=0.1, poll=0.02, log=None)
        finally:
            child.kill()
            child.wait()
            child.stdout.close()
        hs.acquire('test', n=1, folder=self.dir, timeout=2, poll=0.02, log=None).release()

    def test_smaller_limit_elsewhere_wins_while_it_runs(self):
        small = hs.acquire('small', n=1, folder=self.dir, log=None)
        self.assertEqual(hs.effective_limit(self.dir, 3), 1)
        with self.assertRaises(TimeoutError):
            hs.acquire('big', n=3, folder=self.dir, timeout=0.2, poll=0.02, log=self.log)
        self.assertIn('1개로 줄임', self.log.getvalue())
        small.release()
        self.assertEqual(hs.effective_limit(self.dir, 3), 3)
        held = [hs.acquire('big', n=3, folder=self.dir, timeout=0, log=None) for _ in range(3)]
        self.assertEqual(sorted(s.index for s in held), [0, 1, 2])
        for s in held:
            s.release()

    def test_waiting_process_also_lowers_limit(self):
        # 기다리는 동안에도 작은 값을 알리므로, 큰 값 쪽이 빈 자리를 먼저 다 채우지 않는다
        a = hs.acquire('a', n=2, folder=self.dir, log=None)
        b = hs.acquire('b', n=2, folder=self.dir, log=None)
        got = []
        t = threading.Thread(target=lambda: got.append(
            hs.acquire('small', n=1, folder=self.dir, timeout=5, poll=0.02, log=None)))
        t.start()
        time.sleep(0.2)
        self.assertEqual(hs.effective_limit(self.dir, 2), 1)
        b.release()
        with self.assertRaises(TimeoutError):
            hs.acquire('c', n=2, folder=self.dir, timeout=0.2, poll=0.02, log=None)
        a.release()
        t.join(5)
        self.assertEqual(got[0].index, 0)
        got[0].release()

    def test_off(self):
        for value in ('0', 'off', 'OFF'):
            with mock.patch.dict(os.environ, {hs.ENV: value}):
                self.assertEqual(hs.limit(), 0)
                s = hs.acquire('test', folder=self.dir / 'never')
                self.assertIsNone(s.index)
                self.assertFalse((self.dir / 'never').exists())
                s.release()

    def test_limit(self):
        with mock.patch.dict(os.environ, {hs.ENV: '3'}):
            self.assertEqual(hs.limit(), 3)
        with mock.patch.dict(os.environ, {hs.ENV: ''}):
            self.assertEqual(hs.limit(), max(1, (os.cpu_count() or 2) // 2))
        with self.assertRaises(ValueError):
            hs.limit('-1')


@unittest.skipIf(hs.fcntl is None, 'flock 없음')
class LaunchTests(unittest.TestCase):
    """run·popen 이 띄운 프로세스가 도는 동안만 자리를 쥐고, 시간을 넘기면 끄는지."""

    # 자식이 같은 자리를 잡아 보고 결과를 찍는다. 부모가 쥐고 있으면 busy
    PROBE = ('import sys; sys.path.insert(0, sys.argv[1]); import headless_slots as hs\n'
             'try:\n    hs.acquire("child", n=1, folder=sys.argv[2], timeout=0, log=None).release(); print("free")\n'
             'except TimeoutError:\n    print("busy")')

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        patches = [mock.patch.dict(os.environ, {hs.ENV: '1'}), mock.patch.object(hs, 'slots_dir', lambda: self.dir)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def free(self):
        hs.acquire('test', n=1, folder=self.dir, timeout=2, poll=0.02, log=None).release()

    def probe(self):
        return [sys.executable, '-c', self.PROBE, str(Path(hs.__file__).parent), str(self.dir)]

    def test_run_holds_slot_while_child_runs(self):
        done = hs.run(self.probe(), 'test', capture_output=True, text=True, check=True)
        self.assertEqual(done.stdout.strip(), 'busy')
        self.free()

    def test_run_timeout_kills_and_releases(self):
        t0 = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            hs.run([sys.executable, '-c', 'import time; time.sleep(30)'], 'test', timeout=0.3)
        self.assertLess(time.monotonic() - t0, 10)
        self.free()

    def test_popen_holds_slot_until_exit(self):
        p = hs.popen(self.probe(), 'test', stdout=subprocess.PIPE, text=True)
        out, _ = p.communicate(timeout=10)
        self.assertEqual(out.strip(), 'busy')
        self.free()

    def test_popen_second_waits_for_first_to_exit(self):
        first = hs.popen([sys.executable, '-c', 'import time; time.sleep(0.4)'], 'first')
        second = hs.popen([sys.executable, '-c', 'pass'], 'second')
        self.assertIsNotNone(first.poll())
        self.assertGreater(second.slot.waited, 0.2)
        self.assertEqual(second.wait(timeout=10), 0)
        first.wait()

    def test_popen_timeout_kills_and_releases(self):
        p = hs.popen([sys.executable, '-c', 'import time; time.sleep(30)'], 'test', timeout=0.3)
        self.assertNotEqual(p.wait(timeout=10), 0)
        self.free()
        self.assertTrue(p.timed_out)


if __name__ == '__main__':
    unittest.main()
