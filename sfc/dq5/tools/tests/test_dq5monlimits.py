"""무리 조합 늘어놓기와 조각 합·줄마다 타일 합 한도(여유·걸리는 조합)를 원본 롬 없이 확인한다."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5monlimits as L  # noqa: E402
import dq5mongfx as M  # noqa: E402
from dq5encounter import AREA_SIZE  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

# 그림 0: 2x2 칸, 조각 1, 줄마다 타일 2. 그림 1: 4x4 칸, 조각 6, 줄마다 타일 4.
SHAPES = {0: (2, 2, 1, [2, 2]), 1: (4, 4, 6, [4, 4, 4, 4]), 2: (2, 2, 1, [1, 1]), 3: (2, 2, 1, [2, 2])}
HEADS = {0: 0, 1: 1, 2: 2, 3: 3}
SLOTS = {0: 1, 1: 6, 2: 1, 3: 1}
FOUND = {((0, 8, 0),): 'a', ((0, 4, 0), (1, 1, 0)): 'b'}


def head(w, h):
    return {'float': False, 'raise': 0, 'w': w, 'h': h}


class Fakes:
    def __enter__(self):
        self.mocks = [mock('dq5monlimits.M.monster', side_effect=lambda rom, m: (m, [])),
                      mock('dq5monlimits.M.decode', side_effect=lambda rom, g: {'pieces': [None] * SHAPES[g][2], 'g': g}),
                      mock('dq5monlimits.M.band_counts', side_effect=lambda d: list(SHAPES[d['g']][3])),
                      mock('dq5monlimits.M.slot_count', side_effect=lambda d: SLOTS[d['g']]),
                      mock('dq5monlimits.M.header', side_effect=lambda rom, g: head(*SHAPES[g][:2])),
                      mock('dq5monlimits.M.head', side_effect=lambda rom, g: HEADS[g]),
                      mock('dq5monlimits.M.COUNT', 2)]
        for m in self.mocks:
            m.start()

    def __exit__(self, *exc):
        for m in self.mocks:
            m.stop()


class PlaceTests(unittest.TestCase):
    def test_cuts(self):
        slime = (head(2, 2), 1, [2, 2])
        # 줄 폭: 2 × 13 = 26 < 28, 14 째는 28 이라 잘림.
        self.assertEqual([k[1] for k in M.place([(0, 20, 0, *slime)])[0]], [13])
        # 조각 합: 40 × 2 = 80, 셋째 40 은 100 이 되어 잘림.
        big = (head(2, 2), 40, [2, 2])
        self.assertEqual([k[1] for k in M.place([(0, 1, 0, *big), (1, 1, 1, *big), (2, 1, 0x80, *big)])[0]], [1, 1, 0])
        # 줄마다 타일 합: 9 × 3 = 27, 넷째는 28 이라 놓지 않음(조각 한도까지 센 수는 4).
        wide = (head(2, 2), 1, [9, 9])
        kept, pieces, bands = M.place([(0, 4, 0, *wide)])
        self.assertEqual((kept[0][1], kept[0][5], pieces, bands[11], bands[12]), (3, 4, 4, 27, 27))
        # 4x14 칸이면 줄 0 의 상자 위가 $30 이라 첫 줄 번호가 -1 이다. 그 줄은 표 끝(31)에 돌아가 세지 않는다.
        kept, _, bands = M.place([(0, 1, 0, head(4, 14), 1, [4] * 14)])
        self.assertEqual((kept[0][4], kept[0][1], bands[31], bands[:13]), (0x30, 1, 0, [4] * 13))


class LimitTests(unittest.TestCase):
    def test_budgets(self):
        with Fakes():
            got = L.budgets(None, FOUND)
        # 조각: 조각 목록 합이 가장 큰 b(7) 에 걸려 0. 줄: a 는 (27 - 16) // 8 = 1, b 는 (27 - 12) // 4 = 3.
        # 자리: 합이 가장 큰 b(1 + 6 = 7) 에 걸려 0.
        self.assertEqual(got[0], {'pieces': 0, 'bands': [1, 1], 'slots': 0, 'compositions': 2})
        self.assertEqual(got[1], {'pieces': 0, 'bands': [23, 23, 15, 15], 'slots': 0, 'compositions': 1})

    def test_losses(self):
        with Fakes():
            self.assertEqual(L.losses(None, {0: (1, [2, 2])}, found=FOUND), [])
            self.assertEqual(L.losses(None, {0: (1, [3, 3])}, found=FOUND), [])
            band = L.losses(None, {0: (1, [4, 4])}, found=FOUND)
            listed = L.losses(None, {0: (2, [2, 2])}, found=FOUND)
            missing = L.losses(None, {5: (1, [1])}, found=FOUND)
            swapped = L.losses(None, monsters={0: 1}, found=FOUND)
            # 조합에 나오지 않는 그림 2 로 바꾼 몬스터가 있어도, 늘린 그림 0 만 한도를 따진다.
            unshown = L.losses(None, {0: (1, [2, 2])}, monsters={1: 2}, found=FOUND)
        self.assertEqual(band, [(((0, 8, 0),), [8], [6], 'a', '덜 놓임')])
        self.assertEqual([(x[3], x[4]) for x in listed], [('b', '조각 목록 8개 > 7개')])
        self.assertEqual([x[4] for x in missing], ['세는 조합에 나오지 않아 한도를 정할 수 없음'])
        self.assertEqual([x[3] for x in swapped], ['a'])   # 8 × 가로 4 칸이 줄 폭 28 을 넘음
        self.assertEqual(unshown, [])

    def test_losses_slots(self):
        # c 는 자리 30 + 30 = 60 으로 원래 합이 가장 큰 조합. 그림 0 을 자리 2 로 늘리면 b 가 8 이 되지만 60 안이다.
        found = {**FOUND, ((2, 1, 0), (3, 1, 0)): 'c'}
        with Fakes(), mock.dict(SLOTS, {2: 30, 3: 30}):
            self.assertEqual(L.losses(None, {0: (1, [2, 2], 2)}, found=found), [])
            self.assertEqual([x[3] for x in L.losses(None, {0: (1, [2, 2], 55)}, found=found)], ['b'])
            many = L.losses(None, {0: (1, [2, 2], 2)}, found=FOUND)
            loads = L.Pictures(None).loads(((0, 4, 0), (1, 1, 0), (0, 1, 0)))
        self.assertEqual([(x[3], x[4]) for x in many], [('b', '16x16 자리 8개 > 7개')])
        self.assertEqual(loads, [(0, 0, 1), (1, 1, 6)])      # 그림 0 은 한 번만 푼다

    def test_losses_size(self):
        # 그림 1 을 4x14 칸으로 키우면 줄 0 의 상자 위가 $A0 - 112 = $30 이라 줄마다 타일 표(7E:2F00) 앞이다.
        # 4x5 칸이면 위는 $78 이고, 세로 칸 합은 b 가 2 + 5 = 7 로 원래 가장 큰 6(b 의 2 + 4) 을 넘는다.
        with Fakes():
            high = L.losses(None, {1: (6, [4] * 14, 6, head(4, 14))}, found=FOUND)
            rows = L.losses(None, {1: (6, [4] * 5, 6, head(4, 5))}, found=FOUND)
            same = L.losses(None, {1: (6, [4] * 4, 6, head(4, 4))}, found=FOUND)
            wide = L.losses(None, {0: (1, [2, 2], 1, head(4, 2))}, found=FOUND)
        self.assertEqual([x[4] for x in high], ['몬스터 01 상자 위 y $30 < $38'])
        self.assertEqual([x[4] for x in rows], ['그림 세로 칸 7개 > 6개'])
        self.assertEqual(same, [])
        self.assertEqual([(x[3], x[4]) for x in wide], [('a', '덜 놓임')])   # 가로 4칸 8마리는 줄 폭 28 을 넘음

    def test_slot_count(self):
        pieces = [(0, 0, True, [], False), (16, 0, True, [], False), (0, 0, True, [], True)] + \
                 [(0, 0, False, [], False)] * 5 + [(0, 0, False, [], True)] * 2
        self.assertEqual(M.slot_count({'pieces': pieces}), 4)

    def test_losses_uncountable_users(self):
        with Fakes(), mock('dq5monlimits.M.COUNT', 0xEC):
            # 늘린 그림을 ミルドラース(E7) 가 쓰게 바꾸면 E7 조합은 세지 않으므로 거부한다.
            boss = L.losses(None, {0: (1, [2, 2])}, monsters={0xE7: 0}, found=FOUND)
            # 그림 2 는 몬스터 2 만 쓰고 몬스터 2 는 조합에 없다. 몬스터 1 을 그림 2 로 바꾸면 셀 수 있다.
            unseen = L.losses(None, {2: (1, [1, 1])}, found=FOUND)
            moved = L.losses(None, {2: (1, [1, 1])}, monsters={1: 2}, found=FOUND)
        self.assertEqual([x[4] for x in boss], ['무리를 더하는 몬스터(E7~EB)가 써서 한도를 정할 수 없음'])
        self.assertEqual([x[4] for x in unseen], ['세는 조합에 나오지 않아 한도를 정할 수 없음'])
        self.assertEqual(moved, [])

    def test_budgets_merge_same_head(self):
        # 몬스터 1 이 그림 3(그림 0 과 같은 머리)을 쓰면, 두 번호의 여유는 함께 센 하나다.
        found = {((0, 4, 0), (1, 4, 0)): 'c', ((0, 2, 0),): 'd'}
        with Fakes(), mock.dict(HEADS, {3: 0}), mock('dq5monlimits.M.monster', side_effect=lambda rom, m: ([0, 3][m], [])):
            got = L.budgets(None, found)
        # 조각: 조각 목록 합이 가장 큰 c(번호 둘, 2)에서 남는 0. 줄: c 는 같은 줄에 8마리라 (27 - 16) // 8 = 1.
        self.assertEqual(got[0], got[3])
        self.assertEqual(got[0], {'pieces': 0, 'bands': [1, 1], 'slots': 0, 'compositions': 2})

    def test_compositions(self):
        data = bytearray(0x180000)
        events = [[0, 0x6A, 0xFF, 0xFF, 0xFF, 4, 0, 0, 0, 0, 0, 0, 0],
                  [0, 0xE7, 0xFF, 0xFF, 0xFF, 1, 0, 0, 0, 0, 0, 0, 0]]
        for g, raw in enumerate(events):
            at = lorom(L.EVENT_GROUPS + g * L.EVENT_SIZE)
            data[at:at + len(raw)] = bytes(raw)
        record = {'weights': [1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1], 'count_codes': [0] * 11,
                  'species_weights': [1, 0, 0], 'monsters': [0x10, 0x11, 0, 0, 0, 0x15, 0, 0, 0, 0], 'fixed_group': 3}
        with mock('dq5monlimits.area_base', return_value=0x239000), mock('dq5monlimits.EVENT_COUNT', 2), \
                mock('dq5monlimits.area', return_value=record), \
                mock('dq5monlimits.count_range', side_effect=lambda rom, code: (1, 2) if code == 7 else (1, 1)), \
                mock('dq5monlimits.fixed_group', return_value=[(0x20, (1, 1), 1)]):
            found, skipped = L.compositions(Rom(bytes(data)), areas=1)
            seen = L.area.call_args.args
        self.assertEqual(seen[1:], (0, 0x239000))
        with mock('dq5monlimits.area_base', return_value=0x239000), \
                self.assertRaisesRegex(ValueError, '구역 표를 옮긴 롬은 --progress 나 --areas 를 주어야 함'):
            L.compositions(Rom(bytes(data)))
        self.assertEqual(skipped, 1)
        self.assertEqual(len(found), 19)
        self.assertIn(((0x10, 2, 0), (0x11, 1, 0)), found)
        self.assertEqual(found[((0x15, 1, 0),)], '구역 00 칸 5')
        self.assertEqual(found[((0x20, 1, 1),)], '구역 00 칸 10')
        self.assertEqual(found[((0x6A, 3, 0),)], '이벤트 무리 00')


class CliTests(unittest.TestCase):
    """report·dq5monwrite.py 의 CLI 가 구역 수를 주지 않으면 None 을 넘겨, 옮긴 구역 표를 85개로 세지 않는다."""
    MOVED = L.AREAS + AREA_SIZE

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.rom = self.dir / 'rom.sfc'
        self.rom.write_bytes(bytes(0x180000))
        empty = {'weights': [0] * 11, 'count_codes': [0] * 11, 'species_weights': [0, 0, 0], 'monsters': [0] * 10,
                 'fixed_group': 0}
        self.mocks = [mock('dq5monlimits.area', return_value=empty)]
        for m in self.mocks:
            m.start()

    def tearDown(self):
        for m in self.mocks:
            m.stop()

    def report(self, *extra, base=MOVED):
        err = io.StringIO()
        with mock('dq5monlimits.area_base', return_value=base), mock.object(sys, 'argv', ['x', str(self.rom), 'report', *extra]), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            return L.main(), err.getvalue()

    def progress(self, name, writes):
        path = self.dir / f'{name}.json'
        path.write_text(json.dumps({'format': 'dq5patch/1', 'writes': writes}), encoding='utf-8')
        return str(path)

    def test_report(self):
        code, err = self.report()
        self.assertEqual(code, 1)
        self.assertIn('구역 표를 옮긴 롬은 --progress 나 --areas 를 주어야 함', err)
        self.assertEqual(self.report()[0], 1)
        self.assertEqual(self.report(base=L.AREAS), (0, ''))
        self.assertEqual(self.report('--areas', '2'), (0, ''))
        # 구역 표를 옮긴 기록이 없는 패치 목록은 구역 수를 알려 주지 않는다.
        plain = self.progress('plain', [{'at': '23:8000', 'hex': '00', 'note': 'growth'}])
        self.assertEqual(self.report('--progress', plain)[0], 1)
        moved = self.progress('moved', [{'at': '30:8000', 'hex': '00 ' * (2 * AREA_SIZE), 'note': 'area table relocated'}])
        self.assertEqual(self.report('--progress', moved), (0, ''))
        self.assertEqual(L.area_count(moved), 2)
        self.assertIsNone(L.area_count(plain))
        self.assertIsNone(L.area_count())

    def test_monwrite_passes_none(self):
        import dq5monwrite as W
        doc = self.dir / 'mon.json'
        doc.write_text(json.dumps({'format': W.FORMAT}), encoding='utf-8')
        for command in (['patch', str(doc), '-o', str(self.dir / 'out.json')], ['check', str(doc)]):
            target = 'patch' if command[0] == 'patch' else 'check'
            with self.subTest(command=command[0]), mock(f'dq5monwrite.{target}', return_value={'writes': []}) as seen, \
                    mock.object(sys, 'argv', ['x', str(self.rom), *command]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(W.main(), 0)
            self.assertIsNone(seen.call_args.args[4])


if __name__ == '__main__':
    unittest.main()
