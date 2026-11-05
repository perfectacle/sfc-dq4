import contextlib
import io
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


if __name__ == '__main__':
    unittest.main()


class ReleaseTests(unittest.TestCase):
    def test_release_needs_a_passed_report_of_this_commit(self):
        """배포판은 passed·고친 것 없음·지금 HEAD·롬 SHA-1 이 있는 보고서로만 만든다."""
        import dq4publish as pub
        ok = {'verdict': 'passed', 'rehearse': False, 'dirty': False, 'commit': 'abc', 'rom_sha1': 'f' * 40}
        pub.check_report(ok, 'abc')
        for bad, why in (({'verdict': 'failed'}, 'passed'), ({'verdict': 'rehearsal'}, 'passed'),
                         ({'rehearse': True}, 'passed'), ({'dirty': True}, '고친 것'), ({'commit': 'def'}, 'HEAD'),
                         ({'rom_sha1': None}, '롬 SHA-1')):
            with self.assertRaisesRegex(SystemExit, why):
                pub.check_report({**ok, **bad}, 'abc')

    def test_release_rejects_a_different_rom(self):
        import dq4publish as pub
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'dq5.sfc').write_bytes(bytes(64))
            rom = d / 'out.sfc'
            rom.write_bytes(bytes(32) + b'\x01' * 32)
            report = d / 'report.json'
            sha = __import__('hashlib').sha1(rom.read_bytes()).hexdigest()
            report.write_text(__import__('json').dumps(
                {'verdict': 'passed', 'dirty': False, 'commit': 'abc', 'rom_sha1': '0' * 40, 'when': 'now'}))
            fake_build = mock.Mock(build=mock.Mock(return_value=rom))
            with mock.patch.object(pub, 'merged_commit', return_value='abc'), \
                    mock.patch.dict('sys.modules', {'dq4build': fake_build}):
                with self.assertRaisesRegex(SystemExit, '보고서의'):
                    pub.release(d / 'assets', d / 'dq5.sfc', d / 'dq4.nes', report, False)
                report.write_text(report.read_text().replace('0' * 40, sha))
                pub.release(d / 'assets', d / 'dq5.sfc', d / 'dq4.nes', report, False)
            self.assertTrue((d / 'assets' / pub.RELEASE_DIR / pub.IPS_NAME).exists())
            self.assertIn(sha, (d / 'assets' / pub.RELEASE_DIR / 'RELEASE.txt').read_text(encoding='utf-8'))
            self.assertFalse((d / 'assets' / pub.IPS_DIR).exists())
