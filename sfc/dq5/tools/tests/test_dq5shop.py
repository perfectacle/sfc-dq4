"""상점·가격·경품·여관·격투장·슬라임 레이스(dq5shop). 표 걷기와 倍率 계산은 합성 롬으로, 명령줄은 롬이 있으면 본다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5shop as S  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from test_dq5spc import run_main  # noqa: E402

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'


def put(d, addr, raw):
    d[lorom(addr):lorom(addr) + len(raw)] = raw


def shop_rom():
    d = bytearray(0x200000)
    lists = [bytes([1, 0x10, 0x11, 0xFF]), bytes([1, 0x20, 0xFF, 2, 0xFF]), bytes([3, 0x30, 0xFF]),
             bytes([S.MEDAL_KEY, 0x40, 0x41, 0xFF, S.COIN_KEY, 0x50, 0xFF])]
    a = S.END - len(lists[3]) - len(lists[2]) - len(lists[1]) - len(lists[0])
    for k, raw in enumerate(lists):
        put(d, S.LISTS + 2 * k, (a & 0xFFFF).to_bytes(2, 'little'))
        put(d, a, raw)
        a += len(raw)
    put(d, S.MEDAL_PRICES, bytes([5, 9]))
    put(d, S.COIN_PRICES, (0x012345).to_bytes(3, 'little'))
    put(d, S.PRICE_BASE + 0x10, bytes([25, 3]))
    put(d, S.PRICE_SCALE + 0x10, bytes([0x02, 0xFF]))
    put(d, S.INNS, bytes([0x01, 0x05, 0x22, 0x88]))
    put(d, S.ARENA_MATCHES, bytes([0x10, 3, 0xFF, 0, 0x11, 5, 0xFF, 0]))
    put(d, S.ARENA_LEVELS, bytes([4]))
    put(d, S.SLIME_PAIRS, bytes([0, 1, 0, 4, 2, 3]))
    return Rom(d)


class ShopTest(unittest.TestCase):
    def setUp(self):
        self.rom = shop_rom()

    def test_price_uses_scale_table(self):
        self.assertEqual(S.price(self.rom, 0x10), 2500)
        self.assertEqual(S.price(self.rom, 0x11), 3000)

    def test_lists_split_by_kind_and_key(self):
        self.assertEqual(S.shop_lists(self.rom), [(0, 1, [0x10, 0x11]), (1, 1, [0x20]), (1, 2, []), (2, 3, [0x30]),
                                                  (3, S.MEDAL_KEY, [0x40, 0x41]), (3, S.COIN_KEY, [0x50])])

    def test_prizes_inns_arena(self):
        self.assertEqual(S.prize_lists(self.rom), [('작은 메달', [(0x40, 5), (0x41, 9)]), ('코인 교환', [(0x50, 0x012345)])])
        self.assertEqual(S.inns(self.rom)[:2], [(0x01, 5, 0), (0x22, 8, 1)])
        self.assertEqual(len(S.inns(self.rom)), S.INN_COUNT)
        arena = S.arena(self.rom)
        self.assertEqual(len(arena), S.ARENA_COUNT)
        # 몬스터 FF 칸은 빈 자리라 빠진다.
        self.assertEqual(arena[0], (4, [(0x10, 3), (0x11, 5)]))
        self.assertEqual(arena[1], (0, [(0, 0)] * 4))

    def test_slime_odds(self):
        odds = S.slime_odds(self.rom, [56, 56, 7, 7, 32])
        self.assertEqual(odds[:3], [(1, 2, 7), (1, 5, 10), (3, 4, 168)])
        # 몫이 2 미만이면 2.
        self.assertEqual(S.slime_odds(self.rom, [196] * 5)[0], (1, 2, 2))


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class RomTest(unittest.TestCase):
    def test_main(self):
        rom = Rom(ROM.read_bytes())
        code, out = run_main(S, [str(ROM)])
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), len(S.shop_lists(rom)) + 2 + S.ARENA_COUNT + 5 + 1)
        self.assertEqual(sum(ln.startswith('격투장 ') for ln in lines), S.ARENA_COUNT)
        self.assertTrue(lines[-1].startswith('여관(1인): '))
        self.assertEqual(lines[-1].count('G'), S.INN_COUNT)


if __name__ == '__main__':
    unittest.main()
