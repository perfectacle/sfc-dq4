"""글자 읽기 상태·「글자 못 읽음」 규칙과 dq4wintext.comparable 단위 테스트."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4wintext as wt  # noqa: E402
import dq4winrule_wintextstatus as status  # noqa: E402
import dq4winrule_wintextzero as zero  # noqa: E402

RUN = SimpleNamespace(ref=SimpleNamespace(rom=b''))


class ZeroRuleTest(unittest.TestCase):
    def judge(self, got):
        with mock.patch.object(status, 'read_lines', return_value=got):
            return zero.check_run(RUN), status.check_run(RUN)

    def test_windows_without_any_read_line_fail(self):
        fail, note = self.judge((3, 0))
        self.assertEqual(len(fail), 1)
        self.assertIn('0줄', note[0][1])

    def test_read_lines_pass_and_are_logged(self):
        fail, note = self.judge((3, 12))
        self.assertEqual(fail, [])
        self.assertIn('12줄', note[0][1])

    def test_scene_without_windows_passes(self):
        self.assertEqual(self.judge((0, 0))[0], [])

    def test_fake_rom_is_silent(self):
        self.assertEqual(self.judge(status.FAKE_ROM), ([], []))

    def test_missing_font_is_noted_not_failed(self):
        fail, note = self.judge(status.NO_FONT)
        self.assertEqual(fail, [])
        self.assertIn('DQ4_GALMURI', note[0][1])


class ComparableTest(unittest.TestCase):
    def test_fake_rom_is_not_compared(self):
        self.assertFalse(wt.comparable(bytes(0x30000)))

    def test_real_sized_rom_shorter_than_dq5_is_an_error(self):
        dq5 = mock.Mock(is_file=lambda: True, stat=lambda: SimpleNamespace(st_size=0x300000))
        with mock.patch.object(wt, 'DQ5_ROM', dq5):
            with self.assertRaises(ValueError):
                wt.comparable(bytes(0x200000))
            self.assertTrue(wt.comparable(bytes(0x400000)))


if __name__ == '__main__':
    unittest.main()
