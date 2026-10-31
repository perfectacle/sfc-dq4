import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

import dq4mesen as mesen

# MesenCE 대신 띄우는 가짜: 받은 롬 이름을 적고, 그 이름의 .srm 이 이미 있었는지 남긴 뒤 새 .srm 을 쓴다
FAKE = '''#!{python}
import os, sys
from pathlib import Path
rom = Path(sys.argv[2])
srm = Path(os.environ['MESENCE_SAVES']) / (rom.stem + '.srm')
with open(os.environ['FAKE_LOG'], 'a') as log:
    log.write(f'{{rom.name}} {{srm.exists()}}\\n')
srm.write_bytes(b'saved')
'''


@unittest.skipIf(sys.platform == 'win32', 'shebang 가짜 실행 파일')
class MesenTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.saves = self.dir / 'Saves'
        self.saves.mkdir()
        self.fake = self.dir / 'Mesen'
        self.fake.write_text(FAKE.format(python=sys.executable))
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IEXEC)
        self.log = self.dir / 'log.txt'
        self.rom = self.dir / 'c.sfc'
        self.rom.write_bytes(b'rom')
        self.env = mock.patch.dict(os.environ, MESENCE_SAVES=str(self.saves), FAKE_LOG=str(self.log))
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def runs(self):
        return [line.split() for line in self.log.read_text().splitlines()]

    def test_each_run_gets_its_own_name_and_no_old_save(self):
        (self.saves / 'c.srm').write_bytes(b'church')           # 다른 검사가 남긴 기록
        work = self.dir / 'work'
        for _ in range(2):
            mesen.run(self.fake, self.rom, 'probe.lua', folder=work, env=dict(os.environ), check=True)
        (a, a_had), (b, b_had) = self.runs()
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, 'c.sfc')
        self.assertEqual((a_had, b_had), ('False', 'False'))
        self.assertEqual(sorted(p.name for p in self.saves.iterdir()), ['c.srm'])
        self.assertEqual(list(work.iterdir()), [])

    def test_runner_cleans_up_after_wait(self):
        work = self.dir / 'work'
        runner = mesen.Runner(self.fake, self.rom, 'probe.lua', work, tag='bg3', env=dict(os.environ))
        self.assertEqual(runner.wait(), 0)
        self.assertTrue(self.runs()[0][0].startswith('bg3-'))
        self.assertEqual(list(self.saves.iterdir()), [])
        self.assertEqual(list(work.iterdir()), [])

    def test_clear_saves_only_touches_that_name(self):
        (self.saves / 'a.srm').write_bytes(b'')
        (self.saves / 'b.srm').write_bytes(b'')
        self.assertEqual(mesen.clear_saves(self.dir / 'a.sfc'), [self.saves / 'a.srm'])
        self.assertTrue((self.saves / 'b.srm').exists())


if __name__ == '__main__':
    unittest.main()
