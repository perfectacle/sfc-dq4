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
        self.assertEqual(kinds(found, 0x3A), ['창 밖'] * 4)
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
        self.assertEqual(kinds(found, 0x01), ['창 밖'])

    def test_name_stepping_four_under_its_fifth_column_is_covered(self):
        rec = bytes.fromhex('0004 0c a3 00 01') + bytes.fromhex('fed002ff') + b'\x80'
        self.assertEqual(kinds(wl.check(rom({0x01: rec})), 0x01), ['테두리'])

    def test_blank_after_a_name_keeps_its_fifth_column(self):
        rec = bytes.fromhex('0004 0c a3 00 01') + bytes.fromhex('fed00101ff') + b'\x80'
        self.assertEqual(wl.check(rom({0x01: rec})), [])

    def test_name_before_its_state_mark_steps_five(self):
        rec = bytes.fromhex('0004 0c a3 00 01') + bytes.fromhex('fed0ddff') + b'\x80'
        self.assertEqual(wl.check(rom({0x01: rec})), [])

    def test_unknown_code_without_base_is_reported(self):
        rec = bytes.fromhex('0004 0c a3 00 01') + bytes.fromhex('fef2ff') + b'\x80'
        self.assertEqual(kinds(wl.check(rom({0x01: rec})), 0x01), ['모름'])


class AllowTest(unittest.TestCase):
    def test_fixed_exception_is_reported_stale(self):
        from unittest import mock
        import io
        import contextlib
        d = rom({0x3A: SHOP_MEMBERS[:1] + bytes((SHOP_MEMBERS[1], 0x1E)) + SHOP_MEMBERS[3:]}, SHOP_TITLES)
        out = io.StringIO()
        with mock.patch.object(wl, 'ALLOW', {(0x3A, '창 밖'): '고칠 때까지'}), \
                mock.patch('sys.argv', ['x', '--rom', 'r', '--base', 'b']), \
                mock.patch.object(wl.Path, 'read_bytes', lambda self: d), contextlib.redirect_stdout(out):
            self.assertEqual(wl.main(), 1)
        self.assertIn('지난 예외', out.getvalue())


class EdgeTest(unittest.TestCase):
    def test_one_column_apart_sides_are_misaligned(self):
        a = bytes.fromhex('020408a30001') + bytes.fromhex('fe02ff') + b'\x80'
        b = bytes.fromhex('030408a30001') + bytes.fromhex('fe02ff') + b'\x80'
        d = rom({0x01: a, 0x02: b})
        _, wins = wl.windows(d, 'hack')
        self.assertEqual(wl.misaligned(wins, (0x01, 0x02)), {(0x01, 0x02, '왼쪽'), (0x01, 0x02, '오른쪽')})


class ExtraRecordTest(unittest.TestCase):
    def test_shop_sell_record_opens_at_the_alias_place_and_is_checked(self):
        target = bytes.fromhex('4f038db90081fed3ff83')
        d = bytearray(rom({0x0F: target, 0x37: bytes.fromhex('89020f')}))
        sell = bytes.fromhex('4f0395b90081fed301d9ff83')           # 너비 21, 자리는 창 37 의 x 9 y 2
        o = wl.lorom(wl.SHOP_SPOT + 9)
        d[o:o + len(sell)] = sell
        (key, name, _, _), = [e for e in wl.extras(bytes(d)) if e[1] == '가게 팔기 목록']
        win = wl.windows(bytes(d), 'hack')[1][key]
        self.assertEqual((win.x, win.y, win.w), (9, 2, 21))
        self.assertEqual(wl.label(bytes(d), key), '가게 팔기 목록')


class PlaceTest(unittest.TestCase):
    def test_window_past_the_right_edge(self):
        rec = bytes.fromhex('190408a30001') + bytes.fromhex('fe02ff') + b'\x80'
        self.assertEqual(kinds(wl.check(rom({0x01: rec})), 0x01), ['화면 밖'])

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

    def test_input_length_counts_holds_and_waits(self):
        import dq4windowscenes as ws
        self.assertEqual(ws.frames('b:4,wait:40,up:10'), 54)

    def test_long_name_fills_eight_name_bytes(self):
        import dq4windowscenes as ws
        self.assertEqual(len(ws.name_sets().split(';')), 8)


@unittest.skipUnless(DQ5_ROM.is_file() and wl.FC_ROM.is_file(), 'rom/dq5.sfc 와 rom/dq4.nes 가 필요')
class ReachableItemTest(unittest.TestCase):
    """아홉 칸 창에서 빼는 가나 열 칸 물건이 넓은 예외가 아니게: DQ4 명칭표에 없는 DQ5 전용 물건은 DQ4 데이터가 주는
    물건(reachable_items)과 하나도 겹치지 않고, DQ4 에서 손에 드는 물건은 모두 한글 이름이 있다."""

    def test_dq5_only_items_never_come_from_dq4_data(self):
        widths = wl.Widths(DQ5_ROM.read_bytes(), 'hack')
        reach = wl.reachable_items(wl.FC_ROM)
        self.assertGreater(len(reach), 90)
        self.assertEqual(sorted(widths.dq5_only() & reach), [])

    def test_every_item_dq4_gives_has_a_korean_name(self):
        # 이름이 같은 물건은 위 시험(DQ5 전용과 겹치지 않음 = 명칭표에 있음)이 덮고, 빌린 자리는 한글 이름 표가 따로다
        import dq4itemport
        borrowed = set(dq4itemport.BORROWED) | set(dq4itemport.EVENT_ITEMS)
        self.assertEqual(sorted(borrowed - set(dq4itemport.korean_names())), [])


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
