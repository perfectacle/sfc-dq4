"""dq5mesen 이 받은 인자를 '--testrunner' 뒤에 그대로 붙이고, 띄운 동안 자리를 쥐는지 롬 없이 본다."""
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5mesen  # noqa: E402

# MesenCE 대신: 받은 인자와, 같은 자리를 잡을 수 있었는지를 찍는다
FAKE = '''#!{python}
import sys
sys.path.insert(0, {tools!r})
import headless_slots as hs
try:
    hs.acquire('fake', n=1, folder={slots!r}, timeout=0, log=None).release()
    held = 'free'
except TimeoutError:
    held = 'busy'
print(held, *sys.argv[1:])
'''


@unittest.skipIf(dq5mesen.headless_slots.fcntl is None, 'flock 없음')
class Dq5MesenTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        slots = self.dir / 'slots'
        self.fake = self.dir / 'Mesen'
        self.fake.write_text(FAKE.format(python=sys.executable, tools=str(Path(dq5mesen.headless_slots.__file__).parent),
                                         slots=str(slots)))
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IEXEC)
        patches = [mock.patch.dict(os.environ, HEADLESS_SLOTS='1'),
                   mock.patch.object(dq5mesen.headless_slots, 'slots_dir', lambda: slots)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_testrunner(self):
        done = dq5mesen.testrunner(self.fake, 'r.sfc', 'p.lua', '--Snes.DisableFrameSkipping=true',
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(done.stdout.split(), ['busy', dq5mesen.TESTRUNNER, 'r.sfc', 'p.lua', '--Snes.DisableFrameSkipping=true'])

    def test_testrunner_popen(self):
        p = dq5mesen.testrunner_popen(str(self.fake), 'r.sfc', 'p.lua', stdout=subprocess.PIPE, text=True)
        out, _ = p.communicate(timeout=30)
        self.assertEqual(out.split(), ['busy', dq5mesen.TESTRUNNER, 'r.sfc', 'p.lua'])


if __name__ == '__main__':
    unittest.main()
