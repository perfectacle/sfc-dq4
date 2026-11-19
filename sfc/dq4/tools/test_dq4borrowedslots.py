"""빌린 DQ5 물건 자리는 DQ4 가 쓰지 않는 물건이어야 한다: 그 DQ5 원래 이름이 FC 물건 표에도, NDS 물건 표(채택 표의
「아이템」)에도 없다. 겹치면 뒤 장(NDS 늘어난 내용 포함)에서 그 물건을 옮길 때 같은 번호를 두 물건이 쓴다."""
import csv
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[2]
sys.path[:0] = [str(TOOLS), str(TOOLS.parents[1] / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4itemport  # noqa: E402

DQ5_ROM, DQ4_ROM = ROOT / 'rom' / 'dq5.sfc', ROOT / 'rom' / 'dq4.nes'
ADOPT = ROOT / 'nds' / 'dq4' / 'tables' / 'adopt.tsv'
# 표기 흔들림: 히라가나·가타카나, づ·ず, ぢ·じ, 가운뎃점·빈칸
SAME = str.maketrans({'ヅ': 'ズ', 'ヂ': 'ジ', '・': None, ' ': None, '　': None})


def key(name):
    kata = ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in name)
    return kata.translate(SAME)


def borrowed():
    """{DQ5 번호: 이 해킹이 그 자리에 둔 이름}: FC 물건 자리, 사건 물건 자리, 이름만 바꾼 자리."""
    return {**dq4itemport.RENAMED, **dq4itemport.BORROWED, **dq4itemport.EVENT_ITEMS}


class KeyTest(unittest.TestCase):
    def test_spelling_variants_meet(self):
        self.assertEqual(key('いかづちのつえ'), key('イカズチノツエ'))
        self.assertEqual(key('まもりのたね'), key('マモリノタネ'))


@unittest.skipUnless(DQ5_ROM.is_file() and DQ4_ROM.is_file(), 'rom/dq5.sfc·dq4.nes 가 필요')
class BorrowedSlotTest(unittest.TestCase):
    def test_dq5_names_of_borrowed_slots_are_not_dq4_items(self):
        import dq4shop
        import dq5item
        from kr_patch.fc import ines
        rom = dq5item.Rom(DQ5_ROM.read_bytes())
        fc = {key(n) for n in dq4shop.item_names(ines.prg(DQ4_ROM.read_bytes()))[0].values() if n}
        with ADOPT.open(encoding='utf-8') as f:
            nds = {key(r['DS 일본어']) for r in csv.DictReader(f, delimiter='\t') if r['표'] == '아이템'}
        self.assertGreater(len(fc), 100)
        self.assertGreater(len(nds), 150)
        clash = {f'{i:02X} {dq5item.item_name(rom, i)}': [src for src, names in (('FC', fc), ('NDS', nds))
                                                          if key(dq5item.item_name(rom, i)) in names]
                 for i in sorted(borrowed())}
        self.assertEqual({k: v for k, v in clash.items() if v}, {})

    def test_luck_seed_left_the_nds_seed(self):
        # まもりのたね(AE)는 NDS 물건이라 빌리지 않는다
        self.assertNotIn(0xAE, borrowed())


if __name__ == '__main__':
    unittest.main()
