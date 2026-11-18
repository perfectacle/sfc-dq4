"""창 레코드 정적 검사(dq4windowlint)를 합성 롬과 원래 DQ5 롬으로 검사한다."""
import unittest
from pathlib import Path

import dq4windowlint as wl

DQ5_ROM = Path(__file__).resolve().parents[3] / 'rom' / 'dq5.sfc'
RECORDS = 0x04F000
TITLES = 0x04AD78


def rom(records, titles=(b'',), fixed=None):
    """창 n → 레코드 바이트, 제목 목록, 고정 문구 번호 → 열 수로 만든 4MB 롬."""
    d = bytearray(0x400000)
    at = RECORDS
    for n, rec in records.items():
        o = wl.lorom(wl.WINDOWS + n * 2)
        d[o:o + 2] = (at & 0xFFFF).to_bytes(2, 'little')
        d[wl.lorom(at):wl.lorom(at) + len(rec)] = rec
        at += len(rec) + 1
    o = wl.lorom(TITLES)
    for t in titles:
        d[o:o + len(t) + 1] = t + b'\xff'
        o += len(t) + 1
    pic = 0x9200
    for k, cols in (fixed or {}).items():
        o = wl.lorom(wl.TEXT_BANK << 16 | wl.INDEX + wl.FIXED_KIND * 0x200 + k * 2)
        d[o:o + 2] = pic.to_bytes(2, 'little')
        d[wl.lorom(wl.TEXT_BANK << 16 | pic)] = cols
        pic += 1
    return bytes(d)


# 가게 동료 창 3A: 제목(E4 장비 비교 라벨) 아래 줄마다 「이름 + 상태」 둘
SHOP_MEMBERS = bytes.fromhex('010f1d4b0a1804') + bytes.fromhex('efccefccff') * 4 + b'\x80'
SHOP_TITLES = (b'',) * 0x18 + (b'\xe4',)


def kinds(found, n):
    return [k for m, k, _ in found if m == n]


class RowTest(unittest.TestCase):
    def test_two_names_and_states_overflow_a_29_wide_window(self):
        found = wl.check(rom({0x3A: SHOP_MEMBERS}, SHOP_TITLES))
        self.assertEqual(kinds(found, 0x3A), ['넘침'] * 4)
        self.assertIn('28칸 > 안쪽 27칸', found[0][2])

    def test_two_names_and_states_fit_a_30_wide_window(self):
        wide = SHOP_MEMBERS[:1] + bytes((SHOP_MEMBERS[1], 0x1E)) + SHOP_MEMBERS[3:]
        self.assertEqual(wl.check(rom({0x3A: wide}, SHOP_TITLES)), [])

    def test_original_widths_fit_the_original_28_wide_window(self):
        orig = bytes.fromhex('020f1c4b0a1804') + SHOP_MEMBERS[7:]
        widths = wl.Widths(rom({0x3A: orig}, SHOP_TITLES), 'base')
        win = wl.parse(rom({0x3A: orig}, SHOP_TITLES), 0x3A, widths)
        self.assertEqual([wl.row_end(r) for r in win.rows], [26] * 4)

    def test_fixed_phrase_takes_its_picture_columns(self):
        rec = bytes.fromhex('020408a50002') + bytes.fromhex('fe9e00ff fe9e01ff') + b'\x80'
        self.assertEqual(wl.check(rom({0x01: rec}, fixed={0: 5, 1: 5})), [])
        found = wl.check(rom({0x01: rec}, fixed={0: 5, 1: 6}))
        self.assertEqual(kinds(found, 0x01), ['넘침'])

    def test_name_stepping_four_under_its_fifth_column_is_covered(self):
        rec = bytes.fromhex('0004 0c a3 00 01') + bytes.fromhex('fed001ff') + b'\x80'
        self.assertEqual(kinds(wl.check(rom({0x01: rec})), 0x01), ['덮음'])

    def test_name_before_its_state_mark_steps_five(self):
        rec = bytes.fromhex('0004 0c a3 00 01') + bytes.fromhex('fed0ddff') + b'\x80'
        self.assertEqual(wl.check(rom({0x01: rec})), [])

    def test_unknown_code_without_base_is_reported(self):
        rec = bytes.fromhex('0004 0c a3 00 01') + bytes.fromhex('fef2ff') + b'\x80'
        self.assertEqual(kinds(wl.check(rom({0x01: rec})), 0x01), ['모름'])


class PlaceTest(unittest.TestCase):
    def test_window_past_the_right_edge(self):
        rec = bytes.fromhex('190408a30001') + bytes.fromhex('fe02ff') + b'\x80'
        self.assertEqual(kinds(wl.check(rom({0x01: rec})), 0x01), ['화면'])

    def test_alias_opens_the_target_at_its_own_place(self):
        target = bytes.fromhex('0f030da30001') + bytes.fromhex('fe02ff') + b'\x80'
        d = rom({0x0F: target, 0x37: bytes.fromhex('89020f')})
        win = wl.parse(d, 0x37, wl.Widths(d, 'hack'))
        self.assertEqual((win.x, win.y, win.w), (9, 2, 13))

    def test_title_wider_than_its_window(self):
        rec = bytes.fromhex('000406a5020101') + bytes.fromhex('fe02ff') + b'\x80'
        found = wl.check(rom({0x01: rec}, (b'', b'\xe0')))
        self.assertEqual(kinds(found, 0x01), ['제목'])


class SceneTest(unittest.TestCase):
    def test_status_window_grows_one_column_per_person(self):
        import dq4windowscenes as ws
        status = bytes.fromhex('1673c749d112121212') + bytes.fromhex('83 0cb001ff 0db101ff 8785c601ff') + b'\x80'
        d = rom({0x02: status})
        for people, width in ((1, 7), (4, 25)):
            scene = ws.Scene('t', 'shop', people, '', '', (0x02,), '')
            self.assertEqual(ws.expected(d, scene)[0x02]['rect'][2], width)

    def test_party_sets_put_hp_mp_and_level_in_each_record(self):
        import dq4windowscenes as ws
        sets = dict(kv.split('=') for kv in ws.maxed(2).split(';'))
        self.assertEqual((sets['7E2042'], sets['7E2043']), ('E7', '03'))       # 사람 0 HP 999
        self.assertEqual(sets[f'7E{0x2040 + 42 + 0x12:04X}'], '63')             # 사람 1 레벨 99

    def test_long_name_fills_eight_name_bytes(self):
        import dq4windowscenes as ws
        self.assertEqual(len(ws.name_sets().split(';')), 8)


@unittest.skipUnless(DQ5_ROM.is_file(), 'rom/dq5.sfc 가 필요')
class OriginalRomTest(unittest.TestCase):
    """코드별 너비 표가 원래 DQ5 창에 모두 들어맞아야 표가 맞다."""

    def test_every_known_row_and_title_fits(self):
        data = DQ5_ROM.read_bytes()
        widths, wins = wl.windows(data, 'base')
        for n, win in wins.items():
            for r, cells in enumerate(win.rows):
                end = wl.row_end(cells)
                if end is not None:
                    self.assertLessEqual(end, wl.inner_width(win), f'창 {n:02X} 줄 {r}: {wl.describe(cells)}')
                self.assertEqual(wl.covered(cells), [], f'창 {n:02X} 줄 {r}')
            if win.title is not None:
                cols = wl.title_cols(data, widths, win.title)
                if cols is not None:
                    self.assertLessEqual(win.title_x + cols, win.w - 1, f'창 {n:02X} 제목')

    def test_shop_members_window_is_full_in_the_original(self):
        data = DQ5_ROM.read_bytes()
        win = wl.windows(data, 'base')[1][0x3A]
        self.assertEqual([wl.row_end(r) for r in win.rows], [wl.inner_width(win)] * 4)


if __name__ == '__main__':
    unittest.main()
