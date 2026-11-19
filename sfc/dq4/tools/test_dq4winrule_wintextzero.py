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

    def test_ink_lines_with_nothing_recognised_fail(self):
        fail, note = self.judge((3, 5, 0, 0))
        self.assertEqual(len(fail), 1)
        self.assertIn('알아본 줄 0개', note[0][1])

    def test_read_lines_pass_and_are_logged(self):
        fail, note = self.judge((3, 12, 11, 1))
        self.assertEqual(fail, [])
        self.assertIn('알아본 줄 11개', note[0][1])

    def test_empty_windows_are_counted_not_failed(self):
        # 메시지 창을 연 순간처럼 창 안에 잉크가 없는 모습은 못 읽음이 아니다. 대신 결과 줄에 따로 센다
        fail, note = self.judge((1, 0, 0, 1))
        self.assertEqual(fail, [])
        self.assertIn('창 안이 빈 모습 1개', note[0][1])

    def test_scene_without_windows_passes(self):
        self.assertEqual(self.judge((0, 0, 0, 0))[0], [])

    def test_fake_rom_is_silent(self):
        self.assertEqual(self.judge(status.FAKE_ROM), ([], []))

    def test_missing_font_on_a_real_rom_fails(self):
        fail, note = self.judge(status.NO_FONT)
        self.assertEqual(len(fail), 1)
        self.assertIn('DQ4_GALMURI', fail[0][1])
        self.assertIn('DQ4_GALMURI', note[0][1])


class KnownLineTest(unittest.TestCase):
    def test_only_unread_ink_is_not_known(self):
        self.assertFalse(status.known(SimpleNamespace(text=f'{wt.UNREAD} {wt.UNREAD}')))
        self.assertTrue(status.known(SimpleNamespace(text=f'{wt.UNREAD}가')))


def titled(size):
    rom = bytearray(size)
    rom[wt.HEADER_TITLE:wt.HEADER_TITLE + 12] = b'DRAGONQUEST5'
    return bytes(rom)


class ComparableTest(unittest.TestCase):
    def test_fake_rom_is_not_compared(self):
        self.assertFalse(wt.comparable(bytes(0x30000)))

    def test_fake_rom_larger_than_dq5_is_not_compared(self):
        # 판정 틀 시험(test_dq4winwatch)의 가짜 롬은 3MB 로 원본 DQ5 보다 크다
        dq5 = mock.Mock(is_file=lambda: True, stat=lambda: SimpleNamespace(st_size=0x180000))
        with mock.patch.object(wt, 'DQ5_ROM', dq5):
            self.assertFalse(wt.comparable(bytes(0x300000)))

    def test_real_rom_shorter_than_dq5_is_an_error(self):
        dq5 = mock.Mock(is_file=lambda: True, stat=lambda: SimpleNamespace(st_size=0x300000))
        with mock.patch.object(wt, 'DQ5_ROM', dq5):
            with self.assertRaises(ValueError):
                wt.comparable(titled(0x200000))
            self.assertTrue(wt.comparable(titled(0x400000)))


if __name__ == '__main__':
    unittest.main()
