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


if __name__ == '__main__':
    unittest.main()
