import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
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
        self.env = mock.patch.dict(os.environ, MESENCE_SAVES=str(self.saves), FAKE_LOG=str(self.log),
                                   HEADLESS_SLOTS='1')
        self.env.start()
        self.slots = mock.patch.object(mesen.headless_slots, 'slots_dir', lambda: self.dir / 'slots')
        self.slots.start()

    def tearDown(self):
        self.slots.stop()
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

    def test_runners_beyond_slots_do_not_block_each_other(self):
        # 자리 하나에서 Runner 둘을 띄운 뒤에야 wait() 해도, 앞 MesenCE 가 끝나면 자리가 풀려 둘째가 뜬다
        work = self.dir / 'work'
        runners = []

        def start_two():
            for _ in range(2):
                runners.append(mesen.Runner(self.fake, self.rom, 'probe.lua', work, env=dict(os.environ)))
        t = threading.Thread(target=start_two, daemon=True)
        t.start()
        t.join(10)
        self.assertFalse(t.is_alive())
        self.assertEqual([r.wait() for r in runners], [0, 0])
        mesen.headless_slots.acquire('test', timeout=2, log=None).release()

    def test_run_waits_for_slot_and_releases_it(self):
        with mesen.headless_slots.slot('test', log=None):
            with self.assertRaises(TimeoutError):
                mesen.headless_slots.acquire('test', timeout=0.1, log=None)
        mesen.run(self.fake, self.rom, 'probe.lua', folder=self.dir / 'work', env=dict(os.environ), check=True)
        mesen.headless_slots.acquire('test', timeout=0, log=None).release()

    def hanging(self):
        fake = self.dir / 'Hang'
        fake.write_text(f'#!{sys.executable}\nimport time\ntime.sleep(60)\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        return fake

    def test_runner_timeout_kills_and_frees_slot(self):
        runner = mesen.Runner(self.hanging(), self.rom, 'probe.lua', self.dir / 'work', timeout=0.5,
                              env=dict(os.environ))
        mesen.headless_slots.acquire('test', timeout=5, log=None).release()
        self.assertTrue(runner.timed_out)
        self.assertNotEqual(runner.wait(), 0)

    def test_runner_close_kills_live_mesence_first(self):
        work = self.dir / 'work'
        runner = mesen.Runner(self.hanging(), self.rom, 'probe.lua', work, env=dict(os.environ))
        runner.close()
        self.assertIsNotNone(runner.proc.poll())
        self.assertEqual(list(work.iterdir()), [])
        mesen.headless_slots.acquire('test', timeout=0, log=None).release()

    def test_every_path_hands_mesence_a_timeout(self):
        """MesenCE 는 --timeout 이 없으면 약 100초에 종료 255 로 끝나므로, 세 길 모두 Python timeout 보다 조금 긴
        --timeout 을 넘긴다. timeout 이 없으면 RUNNER_TIMEOUT 기준, 인자에 이미 있으면 덧붙이지 않는다."""
        argv = self.dir / 'argv.txt'
        fake = self.dir / 'Argv'
        fake.write_text(f'#!{sys.executable}\nimport sys\nopen({str(argv)!r}, "a").write(" ".join(sys.argv[1:]) + "\\n")\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        env = dict(os.environ)
        work = self.dir / 'work'
        mesen.run(fake, self.rom, 'probe.lua', folder=work, env=env, timeout=30)
        mesen.Runner(fake, self.rom, 'probe.lua', work, timeout=200, env=env).wait()
        mesen.Runner(fake, self.rom, 'probe.lua', work, env=env).wait()
        mesen.testrunner(fake, str(self.rom), 'probe.lua', env=env)
        mesen.testrunner(fake, str(self.rom), 'probe.lua', '--timeout=5', env=env, timeout=30)
        got = [[a for a in line.split() if a.startswith('--timeout=')] for line in argv.read_text().splitlines()]
        margin, default = mesen.TIMEOUT_MARGIN, mesen.RUNNER_TIMEOUT
        self.assertEqual(got, [[f'--timeout={30 + margin}'], [f'--timeout={200 + margin}'],
                               [f'--timeout={default + margin}'], [f'--timeout={default + margin}'], ['--timeout=5']])

    def test_clear_saves_only_touches_that_name(self):
        (self.saves / 'a.srm').write_bytes(b'')
        (self.saves / 'b.srm').write_bytes(b'')
        self.assertEqual(mesen.clear_saves(self.dir / 'a.sfc'), [self.saves / 'a.srm'])
        self.assertTrue((self.saves / 'b.srm').exists())


# 받은 스크립트, DUMP 가 환경에 그대로 왔는지, BIGENV 와 DUMP__FILE 내용 길이를 적는 가짜
FAKE_ENV = '''#!{python}
import os, sys
from pathlib import Path
f = os.environ.get('DUMP__FILE')
with open(os.environ['FAKE_LOG'], 'a') as log:
    log.write(f"{{Path(sys.argv[3]).name}} {{'DUMP' in os.environ}} {{os.environ.get('BIGENV', '-')}} "
              f"{{len(Path(f).read_text()) if f else 0}} {{os.environ.get('BIGENV_TARGET', '-')}}\\n")
'''


@unittest.skipIf(sys.platform == 'win32', 'shebang 가짜 실행 파일')
class BigEnvTests(unittest.TestCase):
    """리눅스 MAX_ARG_STRLEN(128KiB)을 넘는 환경 변수(dq4windowcheck --every 의 DUMP)는 파일로 넘어가 dq4bigenv.lua 가
    되살린다. 넘지 않는 값은 그대로 환경으로 간다."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.fake = self.dir / 'Mesen'
        self.fake.write_text(FAKE_ENV.format(python=sys.executable))
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IEXEC)
        self.log = self.dir / 'log.txt'
        self.rom = self.dir / 'c.sfc'
        self.rom.write_bytes(b'rom')
        self.env = mock.patch.dict(os.environ, MESENCE_SAVES=str(self.dir), FAKE_LOG=str(self.log), HEADLESS_SLOTS='1')
        self.env.start()
        self.slots = mock.patch.object(mesen.headless_slots, 'slots_dir', lambda: self.dir / 'slots')
        self.slots.start()

    def tearDown(self):
        self.slots.stop()
        self.env.stop()

    def test_long_value_goes_through_a_file_and_is_removed(self):
        big = '1:7E0000:60,' * 20000
        env = dict(os.environ, DUMP=big)
        tmp = self.dir / 'tmp'
        tmp.mkdir()
        with mock.patch.object(tempfile, 'tempdir', str(tmp)):
            mesen.run(self.fake, self.rom, 'probe.lua', folder=self.dir / 'w', env=env, check=True)
            mesen.Runner(self.fake, self.rom, 'probe.lua', self.dir / 'w', env=env).wait()
        for line in self.log.read_text().splitlines():
            script, inline, names, size, target = line.split()
            self.assertEqual((script, inline, names, int(size), target), ('dq4bigenv.lua', 'False', 'DUMP', len(big),
                                                                           'probe.lua'))
        self.assertEqual(len(self.log.read_text().splitlines()), 2)
        self.assertEqual(list(tmp.iterdir()), [])

    def test_short_value_stays_in_the_environment(self):
        mesen.run(self.fake, self.rom, 'probe.lua', folder=self.dir / 'w', env=dict(os.environ, DUMP='1:7E0000:60'),
                  check=True)
        self.assertEqual(self.log.read_text().split()[:3], ['probe.lua', 'True', '-'])

    @unittest.skipUnless(shutil.which('lua5.4') or shutil.which('lua'), 'lua 없음')
    def test_lua_wrapper_restores_getenv(self):
        target = self.dir / 'target.lua'
        target.write_text('io.write(#os.getenv("DUMP"), " ", os.getenv("OTHER"))')
        data = self.dir / 'dump.txt'
        data.write_text('x' * 200000)
        out = subprocess.run([shutil.which('lua5.4') or shutil.which('lua'), str(mesen.BIGENV)], capture_output=True,
                             text=True, check=True,
                             env=dict(os.environ, BIGENV='DUMP', DUMP__FILE=str(data), BIGENV_TARGET=str(target),
                                      OTHER='kept'))
        self.assertEqual(out.stdout, '200000 kept')


if __name__ == '__main__':
    unittest.main()
