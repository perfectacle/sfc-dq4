"""창 글자 표(build)와 창 레코드 고쳐 쓰기(fixed_records)를 합성 롬으로 검사한다. 글꼴은 열 수만 흉내 낸다."""
import hashlib
import sys
import unittest
from pathlib import Path
from unittest import mock

import dq4menupatch
import dq4windowtext as wt

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dq5' / 'tools'))
import dq5text  # noqa: E402
from dq5map import lorom  # noqa: E402

KANA = 'あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんっゃゅょ'
WINDOW_COUNT = 0x34
DUMMY = bytes.fromhex('000004010000ff80')
INLINE = 0x04C000


class FakeFont:
    def __init__(self, name='galmuri9'):
        self.name = name


def fake_columns(font, text):
    """Galmuri9 처럼 1점 여백 + 글자마다 10점(Galmuri7 은 6점)을 8점 열로. 그림은 글자·글꼴마다 다르게."""
    step = 6 if font.name == wt.NARROW_FONT else 10
    n = -(-(1 + step * len(text)) // 8)
    return [hashlib.sha1(f'{font.name}/{text}/{i}'.encode()).digest()[:9] for i in range(n)]


def width(text):
    return len(fake_columns(FakeFont(), text))


def enc(text):
    return bytes(0x01 if c == '　' else 0x10 + KANA.index(c) for c in text)


class WindowRom:
    """창 표(04:EB48)·제목 목록·이름 바이트 → 글자 코드 표만 채운 4MB 롬."""

    def __init__(self, windows, shared=None, titles=None, inline=b''):
        self.data = bytearray(0x400000)
        for i, ch in enumerate(KANA):
            self.put(dq5text.STRING_CODES + (0x10 + i) * 2, dq5text.CHARS.index(ch).to_bytes(2, 'little'))
        at = (dq5text.WINDOWS & 0xFFFF) + 2 * WINDOW_COUNT
        dummy = at
        self.put(0x040000 | at, DUMMY)
        at += len(DUMMY)
        self.addr = {}
        for n in range(WINDOW_COUNT):
            if n in windows:
                self.put(0x040000 | at, windows[n])
                self.addr[n], at = 0x040000 | at, at + len(windows[n])
            ptr = self.addr[n] & 0xFFFF if n in self.addr else dummy
            self.put(dq5text.WINDOWS + n * 2, ptr.to_bytes(2, 'little'))
        off = 0
        for n, rec in (shared or {}).items():
            self.put(dq5text.WINDOWS + n * 2, (dq4menupatch.SHARED_WRAM + off).to_bytes(2, 'little'))
            self.put(dq4menupatch.SHARED_JP + off, rec)
            self.addr[n] = dq4menupatch.SHARED_JP + off
            off += len(rec)
        titles = titles or {}
        self.titles = b''.join(titles.get(t, b'') + b'\xff' for t in range(wt.TITLE_COUNT)) + b'\x55' * 4
        self.put(dq5text.WINDOW_TITLES, self.titles)
        self.put(INLINE, inline)

    def put(self, addr, raw):
        self.data[lorom(addr):lorom(addr) + len(raw)] = raw


def head(*b):
    return bytes(b)


# 기본 장면: 항목 창 두 개(한 줄에 하나·한 줄에 둘), 공용 창 하나, 한 줄 창, 능력치 창 07, 제목 있는 라벨 창 06
FIXED_WINDOWS = {0x10: 3, 0x11: 0}
SHARED = {0x32: 1}
LINE_WINDOWS = {0x2D: 1}
COUNT_WINDOWS = {0x12: (0xC8, 1)}


def records(exp_w=0x0C, w11=0x0A, label_w=9, unit='ひき'):
    return {
        0x12: head(2, 3, 0x12, 3, 0, 1) + bytes.fromhex('fee60188c8') + enc(unit) + b'\xff\x80',
        0x10: head(2, 3, 8, 3, 0, 2) + b'\xfe' + enc('はい') + b'\x01' * 3 + b'\xff\xfe' + enc('いいえ') + b'\x01\xff\x80',
        0x11: head(2, 3, w11, 2, 0, 1) + b'\xfe' + enc('はい') + b'\x01' + enc('みる') + b'\x01\x01\xff\x80',
        0x2D: head(1, 1, 0x0B, 1, 0, 1) + enc('しようしていません') + b'\xff\x80',
        0x07: head(5, 2, exp_w, 0x0B, 0, 10) + b'\x01\x01' + enc('ちから') + b'\x85\xb1\xff'
              + b'\x01' + enc('かしこさ') + b'\x85\xb2\xff' + bytes((wt.EXP_TILE, 0x85, wt.EXP_VALUE)) + b'\xff\x80',
        0x06: head(0, 0, label_w, 4, 1, 3, 2) + b'\x01\x01' + enc('うんのよさ') + b'\x85\xb3\xff' + b'\xb4\xff\x80',
        # 마지막 레코드는 다음 시작이 없어 40바이트로 읽히므로 끝을 막아 둔다
        0x33: DUMMY,
    }


def shared_records():
    return {0x32: head(4, 4, 6, 3, 0, 2) + b'\xfe' + enc('はい') + b'\xff\xfe' + enc('いいえ') + b'\xff\x80'}


TITLES = {3: enc('たて'), 5: enc('ぬぬ'), 0x11: enc('たてよろい')}
INLINE_TEXT = b'\x01\x01' + enc('もっている') + b'\xff' + enc('ぬ') + b'\xff'


def scene(**kw):
    return WindowRom(records(**kw), shared_records(), TITLES, INLINE_TEXT)


def patched():
    return mock.patch.multiple(wt, FIXED_WINDOWS={**FIXED_WINDOWS, **SHARED}, LINE_WINDOWS=LINE_WINDOWS,
                               COUNT_WINDOWS=COUNT_WINDOWS,
                               LABEL_WINDOWS=(0x07, 0x06), INLINE_STRINGS=((INLINE, INLINE + len(INLINE_TEXT)),),
                               columns=fake_columns)


def run(rom):
    with patched(), mock.patch.dict(wt.TITLES, {'たてよろい': '창'}):
        return wt.fixed_records(rom.data, FakeFont())


class FixedRecordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = scene()
        cls.writes, cls.numbers = run(cls.rom)
        cls.at = {o: rec for o, rec in cls.writes}

    def written(self, n):
        return self.at[lorom(self.rom.addr[n])]

    def test_count_unit_becomes_a_phrase_and_window_widens(self):
        rec = self.written(0x12)
        k = self.numbers['ひき']
        self.assertEqual(rec[6:13], bytes.fromhex('fee60188c8') + bytes((wt.FIXED_PREFIX, k)))
        self.assertEqual(rec[2], 0x12 + 1)
        self.assertEqual(len(rec), len(records()[0x12]))

    def test_unknown_count_unit(self):
        with self.assertRaises(ValueError):
            run(scene(unit='ぬぬ'))

    def test_writes_do_not_overlap(self):
        spans = sorted((o, o + len(rec)) for o, rec in self.writes)
        for (_, end), (start, _) in zip(spans, spans[1:]):
            self.assertLessEqual(end, start)

    def test_window_records_stay_in_their_own_bytes(self):
        recs = {**records(), **shared_records()}
        for n in (0x10, 0x11, 0x32, 0x2D, 0x06):
            self.assertEqual(len(self.written(n)), len(recs[n]), f'{n:02X}')

    def test_items_keep_their_columns_and_window_widens(self):
        k = self.numbers
        pad = wt.FIXED_PREFIX
        # はい 2칸 + 빈칸 3 = 5열, いいえ 3칸 + 빈칸 1 = 4열을 그대로 둔다(뒤 열 자리와 칸 셈이 원래와 같게)
        want = (head(2, 3, 8 + 3, 3, 0, 2) + bytes((0xFE, pad, k['はい'])) + b'\x01' * (5 - width('예'))
                + bytes((0xFF, 0xFE, pad, k['いいえ'])) + b'\x01' * (4 - width('아니요')) + b'\xff\x80')
        self.assertEqual(self.written(0x10), want.ljust(len(records()[0x10]), b'\xff'))

    def test_second_item_in_a_row_starts_at_the_same_column(self):
        rec = self.written(0x11)
        second = rec.index(bytes((wt.FIXED_PREFIX, self.numbers['みる'])))
        first = rec.index(bytes((wt.FIXED_PREFIX, self.numbers['はい'])))
        spaces = rec[first + 2:second].count(1)
        # 원래 みる 는 FE 뒤 はい 2칸 + 빈칸 1 = 3열 뒤
        self.assertEqual(width('예') + spaces, 3)

    def test_shared_window_rewrites_the_rom_copy(self):
        o = lorom(self.rom.addr[0x32])
        self.assertIn(o, self.at)
        self.assertGreaterEqual(self.rom.addr[0x32] & 0xFFFF, dq4menupatch.SHARED_JP & 0xFFFF)
        self.assertEqual(self.at[o][2], 6 + 1)

    def test_line_window(self):
        rec = self.written(0x2D)
        self.assertEqual(rec[2], 0x0B + 1)
        self.assertEqual(rec[6:8], bytes((wt.FIXED_PREFIX, self.numbers[wt.EMPTY_SLOT])))
        self.assertEqual(rec[8:10], b'\xff\x80')

    def test_exp_record_moves_and_aligns_colons(self):
        o = lorom(wt.EXP_SPOT)
        rec = self.at[o]
        self.assertEqual(rec[2], 0x0C + wt.EXP_WIDEN)
        table = lorom(dq5text.WINDOWS + 2 * wt.EXP_WINDOW)
        self.assertEqual(self.at[table], (wt.EXP_SPOT & 0xFFFF).to_bytes(2, 'little'))
        rows = rec[6:-1].split(b'\xff')[:-1]
        inner = 0x0C + wt.EXP_WIDEN - 2
        colons = set()
        for row, (jp, ko) in zip(rows, (('ちから', '힘'), ('かしこさ', '현명함'), ('けいけんち', '경험치'))):
            self.assertEqual(row[:2], bytes((wt.FIXED_PREFIX, self.numbers[jp])))
            c = row.index(0x85)
            colons.add(width(ko) + c - 2)
            value = 8 if row[-1] == wt.EXP_VALUE else 3
            self.assertEqual(width(ko) + (len(row) - 2) - 1 + value, inner, jp)
        self.assertEqual(len(colons), 1)

    def test_label_keeps_colon_column(self):
        rec = self.written(0x06)
        row = rec[7:rec.index(0xFF, 7)]
        k = row.index(wt.FIXED_PREFIX)
        self.assertEqual(row[k + 1], self.numbers['うんのよさ'])
        # 빈칸 2 + 가나 5 = 7열 뒤에 「:」
        self.assertEqual(k + width('운'), 7)
        self.assertEqual(row[k + 2:], b'\x85\xb3')
        self.assertEqual(rec[rec.index(0xFF, 7) + 1:], b'\xb4\xff\x80')

    def test_titles_keep_their_numbering(self):
        start = lorom(dq5text.WINDOW_TITLES)
        new = self.at[start]
        self.assertLessEqual(len(new), len(self.rom.titles) - 4)
        parts = new.split(b'\xff')
        self.assertEqual(parts[3], bytes((wt.FIXED_PREFIX, self.numbers['たて'])))
        self.assertEqual(parts[5], enc('ぬぬ'))
        # 열 머리 제목은 남는 칸을 앞에 두어 오른쪽에 붙인다
        self.assertEqual(parts[0x11], b'\x01' * (5 - width('창')) + bytes((wt.FIXED_PREFIX, self.numbers['たてよろい'])))
        self.assertTrue(all(p == b'' for t, p in enumerate(parts[:wt.TITLE_COUNT]) if t not in (3, 5, 0x11)))

    def test_inline_strings_keep_length(self):
        new = self.at[lorom(INLINE)]
        self.assertEqual(len(new), len(INLINE_TEXT))
        self.assertEqual(new[:2], bytes((wt.FIXED_PREFIX, self.numbers['　　もっている'])))
        self.assertEqual(new[2:8], b'\x01' * 5 + b'\xff')
        self.assertEqual(new[8:], INLINE_TEXT[8:])


class FixedRecordsRejectTests(unittest.TestCase):
    def test_unknown_kana(self):
        rom = scene()
        rom.put(rom.addr[0x10] + 7, enc('ぬ'))
        with self.assertRaisesRegex(ValueError, '한글 문구가 없음'):
            run(rom)

    def test_row_wider_than_window(self):
        with self.assertRaisesRegex(ValueError, '창 11.*창 안쪽'):
            run(scene(w11=9))

    def test_exp_row_wider_than_window(self):
        with self.assertRaisesRegex(ValueError, '창 안쪽'):
            run(scene(exp_w=0x0A))

    def test_exp_spot_must_be_empty(self):
        rom = scene()
        rom.put(wt.EXP_SPOT + 0x10, b'\x01')
        with self.assertRaisesRegex(ValueError, '비어 있지 않음'):
            run(rom)

    def test_title_wider_than_its_window(self):
        with self.assertRaisesRegex(ValueError, '제목 03'):
            run(scene(label_w=4))


def names_for(kinds):
    return lambda data, kind: kinds.get(kind, [''] * 256)


class BuildTests(unittest.TestCase):
    def build(self, names, adopted=None, numbered=None, kinds=None):
        with mock.patch.multiple(wt, columns=fake_columns, rom_names=names_for(names),
                                 adopted=lambda table: dict(adopted or {}), numbered_names=lambda: numbered or {},
                                 **({'KINDS': kinds} if kinds else {})), \
                mock.patch.object(dq4menupatch, 'Font', FakeFont):
            return wt.build(bytes(16), FakeFont())

    def blob(self, out, ptr):
        o = ptr - wt.INDEX
        n = out[o]
        return [out[o + 1 + 9 * i:o + 10 + 9 * i] for i in range(n)]

    def ptr(self, out, kind, n):
        o = kind * 0x200 + n * 2
        return int.from_bytes(out[o:o + 2], 'little')

    def test_fixed_phrases_point_to_their_columns(self):
        out, report = self.build({})
        phrases = wt.phrases()
        self.assertEqual(report[wt.FIXED_KIND], (len(phrases), len(phrases)))
        for k, (_, ko, _) in enumerate(phrases):
            p = self.ptr(out, wt.FIXED_KIND, k)
            self.assertGreaterEqual(p, wt.DATA)
            self.assertEqual(self.blob(out, p), fake_columns(FakeFont(), ko), ko)

    def test_safe_window_cells_stay_in_range_and_do_not_overlap(self):
        out, _ = self.build({})
        spans = {}
        for k, (_, ko, w) in enumerate(wt.phrases()):
            o = wt.SAFE - wt.INDEX + 2 * k
            first = int.from_bytes(out[o:o + 2], 'little')
            if w is None:
                self.assertEqual(first, 0)
                continue
            n = 2 * width(ko)
            self.assertTrue(wt.SAFE_FIRST <= first and first + n <= wt.SAFE_FIRST + wt.SAFE_TILES)
            spans.setdefault(w, []).append((first, first + n))
        for w, s in spans.items():
            s.sort()
            self.assertEqual(s[0][0], wt.SAFE_FIRST)
            for (_, end), (start, _) in zip(s, s[1:]):
                self.assertEqual(end, start, f'{w:02X}')

    def test_same_picture_is_stored_once(self):
        names = {5: ['ぬの', 'ぬの', 'かさ'] + [''] * 253}
        out, report = self.build(names, adopted={'ぬの': '천', 'かさ': '삿갓'})
        self.assertEqual(self.ptr(out, 5, 0), self.ptr(out, 5, 1))
        self.assertNotEqual(self.ptr(out, 5, 0), self.ptr(out, 5, 2))
        self.assertEqual(report[5], (256, 3))
        body = out[wt.DATA - wt.INDEX:]
        seen, o = set(), 0
        while o < len(body):
            n = body[o]
            b = bytes(body[o:o + 1 + 9 * n])
            self.assertNotIn(b, seen)
            seen.add(b)
            o += 1 + 9 * n

    def test_kana_items_fall_back_to_kana_only_below_limit(self):
        names = [''] * 256
        names[1] = 'ぬの'
        names[wt.KANA_LIMIT] = 'ぬの'
        out, report = self.build({5: names})
        self.assertEqual(self.blob(out, self.ptr(out, 5, 1)), fake_columns(FakeFont(), 'ぬの'))
        self.assertEqual(self.ptr(out, 5, wt.KANA_LIMIT), 0)
        self.assertEqual(report[5], (256, 1))

    def test_long_kana_item_uses_narrow_font(self):
        names = [''] * 256
        names[2] = 'あいうえおかきくけ'          # Galmuri9 로 12열, Galmuri7 로 7열
        out, _ = self.build({5: names})
        self.assertEqual(self.blob(out, self.ptr(out, 5, 2)), fake_columns(FakeFont(wt.NARROW_FONT), names[2]))

    def test_numbered_name_wins_over_rom_name(self):
        names = [''] * 256
        names[3] = 'かさ'
        out, _ = self.build({4: names}, adopted={'かさ': '삿갓'}, numbered={4: {3: '부하'}})
        self.assertEqual(self.blob(out, self.ptr(out, 4, 3)), fake_columns(FakeFont(), '부하'))

    def test_wide_monster_name_drops_its_spaces(self):
        names = ['かさ'] + [''] * 255
        wide = {'かさ': '슬라임 베호마즌'}                # 11열, 띄어쓰기를 빼면 9열
        out, report = self.build({4: names}, adopted=wide)
        self.assertEqual(self.blob(out, self.ptr(out, 4, 0)), fake_columns(FakeFont(), '슬라임베호마즌'))
        out, report = self.build({3: names}, adopted=wide)
        self.assertEqual(self.ptr(out, 3, 0), 0)

    def test_placeholder_dq5_monsters_have_korean(self):
        names = ['ドラキー'] + [''] * 255
        out, _ = self.build({4: names})
        self.assertEqual(self.blob(out, self.ptr(out, 4, 0)), fake_columns(FakeFont(), '드라키'))

    def test_too_long_name_is_an_error_only_in_strict_kinds(self):
        names = ['かさ'] + [''] * 255
        long = {'かさ': '아주 긴 이름입니다'}
        with self.assertRaisesRegex(ValueError, '열, 창은'):
            self.build({5: names}, adopted=long)
        out, report = self.build({3: names}, adopted=long)
        self.assertEqual(self.ptr(out, 3, 0), 0)
        self.assertEqual(report[3], (256, 0))

    def test_pictures_must_fit_one_bank(self):
        base = len(self.build({})[0]) - (wt.DATA - wt.INDEX)
        names = [chr(0xAC00 + n) for n in range(256)]
        ko = {n: n * 70 for n in names}
        size = 1 + 9 * width(names[0] * 70)
        # 마지막 그림이 뱅크 끝을 넘되 그 첫머리는 뱅크 안이어서 색인에는 들어가는 수
        count = (0x10000 - wt.DATA - base) // size + 1
        kinds = {5: ('아이템', 99, False)}
        with self.assertRaisesRegex(ValueError, '뱅크 하나를 넘음'):
            self.build({5: names[:count] + [''] * (256 - count)}, adopted=ko, kinds=kinds)
        out, _ = self.build({5: names[:count - 1] + [''] * (257 - count)}, adopted=ko, kinds=kinds)
        self.assertLessEqual(wt.INDEX + len(out), 0x10000)

class DotFont:
    """글자마다 10점 진행, 점 하나를 띠의 y 줄에."""
    name = 'dot'

    def __init__(self, y):
        self.y = y

    def char(self, ch):
        return 10, [(0, self.y)]


class ColumnsTests(unittest.TestCase):
    def test_band_rows_shift_into_upper_tile_row_7(self):
        # 띠 1줄(한글 윗줄)이 위 줄 타일 7줄째, 띠 2~9줄이 글자 줄 0~7
        top = wt.columns(DotFont(1), '가')
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0], b'\x40' + bytes(8))
        self.assertEqual(wt.columns(DotFont(9), '가')[0], bytes(8) + b'\x40')
        self.assertTrue(all(len(c) == 9 for c in top))

    def test_dots_outside_the_two_rows_are_errors(self):
        with self.assertRaisesRegex(ValueError, '위로 넘침'):
            wt.columns(DotFont(0), '가')
        with self.assertRaisesRegex(ValueError, '아래로 넘침'):
            wt.columns(DotFont(10), '가')


class RomNamesTests(unittest.TestCase):
    def test_reads_length_prefixed_names_of_one_table(self):
        rom = WindowRom({})
        names = [enc('かさ'), b'', enc('ぬの\u3000くつ')]
        at = 0x218000
        rom.put(dq5text.STRING_TABLES + 3 * 5, at.to_bytes(3, 'little'))
        rom.put(at, b''.join(bytes((len(n),)) + n for n in names))
        self.assertEqual(wt.rom_names(rom.data, 5, 3), ['かさ', '', 'ぬの\u3000くつ'])

    def test_kana_key_ignores_spaces_and_katakana(self):
        self.assertEqual(wt.kana_key('カサ 　ぬの'), 'かさぬの')


if __name__ == '__main__':
    unittest.main()
