import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dq4publish as publish


class StampTests(unittest.TestCase):
    def test_inputs_cover_build_steps_and_lock(self):
        names = {p.as_posix() for p in publish.inputs()}
        for tool in ('dq4build.py', 'dq4chapter1.py', 'dq4menupatch.py', 'dq4overture.py', 'dq4titlelayerpatch.py',
                     'dq4soundset.py', 'dq4sound-game.args'):
            self.assertIn(f'sfc/dq4/tools/{tool}', names)
        self.assertIn('uv.lock', names)
        self.assertFalse(any('__pycache__' in n or n.startswith('rom/') or n.startswith('work/') for n in names))

    def test_stamp_is_stable(self):
        self.assertEqual(publish.stamp(), publish.stamp())
        self.assertRegex(publish.stamp(), r'^[0-9a-f]{64}$')


class CheckTests(unittest.TestCase):
    def assets(self, stamp):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (tmp / publish.IPS_DIR).mkdir(parents=True)
        (tmp / publish.IPS_DIR / 'SOURCE.txt').write_text(
            f'sfc-dq4 커밋: {"ab" * 20}\n{publish.STAMP_KEY}: {stamp}\n', encoding='utf-8')
        return tmp

    def check(self, assets):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            return publish.check(assets), out.getvalue()

    def test_current_stamp_passes(self):
        self.assertEqual(self.check(self.assets(publish.stamp()))[0], 0)

    def test_other_stamp_is_stale(self):
        code, out = self.check(self.assets('0' * 64))
        self.assertEqual(code, 1)
        self.assertIn('abababab', out)

    def test_missing_source_asks_for_first_build(self):
        with self.assertRaisesRegex(SystemExit, 'build --commit'):
            publish.check(Path(self.enterContext(tempfile.TemporaryDirectory())))


class RemoteTests(unittest.TestCase):
    def test_token_goes_through_environment_not_arguments(self):
        with mock.patch.dict('os.environ', {'GH_TOKEN': 'secret-token'}), \
                mock.patch.object(publish.subprocess, 'run') as run:
            publish.remote(Path('.'), 'push', '-q', 'origin', 'HEAD')
        args, kwargs = run.call_args
        self.assertNotIn('secret-token', ' '.join(args[0]))
        self.assertTrue(kwargs['env']['GIT_CONFIG_VALUE_0'].startswith('Authorization: Basic '))
        self.assertNotIn('secret-token', kwargs['env']['GIT_CONFIG_VALUE_0'])


def passed_report(**over):
    stages = {s: {'status': 'passed', 'seconds': 1} for s in publish.GATE_STAGES}
    stages['guards']['rows'] = [{'name': 'g', 'status': 'passed'}]
    return {'verdict': 'passed', 'rehearse': False, 'dirty': False, 'commit': 'abc', 'rom_sha1': 'f' * 40,
            'when': 'now', 'stages': stages, **over}


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.enterContext(mock.patch.object(publish, 'ROOT', self.root))

    def report_path(self, sha, suffix=''):
        return self.root / publish.REPORT_DIR / f'{sha[:12]}{suffix}' / 'report.json'

    def test_release_needs_a_passed_report_of_this_commit(self):
        """배포판은 passed·고친 것 없음·지금 HEAD·롬 SHA-1 이 있는 보고서로만 만든다."""
        path = self.report_path('f' * 40)
        publish.check_report(passed_report(), 'abc', path)
        publish.check_report(passed_report(), 'abc', self.report_path('f' * 40, '-20261105-130445'))
        for bad, why in (({'verdict': 'failed'}, 'passed'), ({'verdict': 'rehearsal'}, 'passed'),
                         ({'rehearse': True}, 'passed'), ({'dirty': True}, '고친 것'), ({'commit': 'def'}, 'HEAD'),
                         ({'rom_sha1': None}, '롬 SHA-1')):
            with self.assertRaisesRegex(SystemExit, why):
                publish.check_report(passed_report(**bad), 'abc', path)

    def test_verdict_is_recounted_from_stages(self):
        """verdict 만 passed 로 고친 보고서는 단계 결과로 다시 세어 거부한다(실수 막기용, 위조 방지는 아님)."""
        path = self.report_path('f' * 40)
        failed = passed_report()
        failed['stages']['sweep']['status'] = 'failed'
        with self.assertRaisesRegex(SystemExit, 'sweep'):
            publish.check_report(failed, 'abc', path)
        row_failed = passed_report()
        row_failed['stages']['guards']['rows'][0]['status'] = 'failed'
        with self.assertRaisesRegex(SystemExit, 'guards'):
            publish.check_report(row_failed, 'abc', path)
        missing = passed_report()
        del missing['stages']['coverage']
        with self.assertRaisesRegex(SystemExit, 'coverage'):
            publish.check_report(missing, 'abc', path)
        with self.assertRaisesRegex(SystemExit, '단계'):
            publish.check_report(passed_report(stages={}), 'abc', path)

    def test_report_must_sit_in_its_rom_folder(self):
        for path in (self.report_path('e' * 40), self.root / 'elsewhere' / ('f' * 12) / 'report.json',
                     self.report_path('f' * 40, '-x'), self.root / 'report.json'):
            with self.assertRaisesRegex(SystemExit, '있지 않다'):
                publish.check_report(passed_report(), 'abc', path)

    def test_release_rejects_a_different_rom(self):
        d = self.root
        (d / 'dq5.sfc').write_bytes(bytes(64))
        rom = d / 'out.sfc'
        rom.write_bytes(bytes(32) + b'\x01' * 32)
        sha = hashlib.sha1(rom.read_bytes()).hexdigest()
        fake_build = mock.Mock(build=mock.Mock(return_value=rom))
        with mock.patch.object(publish, 'merged_commit', return_value='abc'), \
                mock.patch.dict('sys.modules', {'dq4build': fake_build}):
            other = self.report_path('0' * 40)
            other.parent.mkdir(parents=True)
            other.write_text(json.dumps(passed_report(rom_sha1='0' * 40)))
            with self.assertRaisesRegex(SystemExit, '보고서의'):
                publish.release(d / 'assets', d / 'dq5.sfc', d / 'dq4.nes', other, False)
            report = self.report_path(sha)
            report.parent.mkdir(parents=True)
            report.write_text(json.dumps(passed_report(rom_sha1=sha)))
            publish.release(d / 'assets', d / 'dq5.sfc', d / 'dq4.nes', report, False)
        self.assertTrue((d / 'assets' / publish.RELEASE_DIR / publish.IPS_NAME).exists())
        self.assertIn(sha, (d / 'assets' / publish.RELEASE_DIR / 'RELEASE.txt').read_text(encoding='utf-8'))
        self.assertFalse((d / 'assets' / publish.IPS_DIR).exists())


if __name__ == '__main__':
    unittest.main()
