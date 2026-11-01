"""롬 없이: 체크섬, 칸 배치, 머리, 금화·flag·자리 쓰기 위치(합성 바이트). 1장 롬(work/ch1/dq4-ch1-full.sfc,
DQ4_CH1_ROM 으로 바꿈)이 있으면 이어 할 자리 표 읽기도."""
import os
import unittest
from pathlib import Path

import dq4ch1walkcheck as wc
import dq4compatcheck as cc
import dq4savefixture as fx
from dq5sram import MAGIC, SLOT_SIZE, SLOTS, SUM_AT, checksum

ROOT = Path(__file__).resolve().parents[3]
CH1 = Path(os.environ.get('DQ4_CH1_ROM') or ROOT / 'work' / 'ch1' / 'dq4-ch1-full.sfc')


def synth_rom():
    """칸 표 25:85D5 와 자리 표 25:8621 만 둔 합성 롬. 칸 k 의 그룹은 0x30 + k, 표에는 그룹 0x37 항목 하나."""
    rom = bytearray(0x200000)
    rom[0x8001] = 1
    groups = fx.lorom(fx.SLOT_TABLE)
    rom[groups:groups + fx.SLOT_COUNT] = bytes(0x30 + k for k in range(fx.SLOT_COUNT))
    t = fx.lorom(fx.PLACE_TABLE)
    rom[t:t + 13] = bytes((0x3C, 0x01, 1, 2, 3, 4, 0x37, 0x00, 50, 9, 0, 0, 0xFF))
    return bytes(rom)


def slot():
    return fx.SaveSlot(bytes(SLOT_SIZE), synth_rom())


class SramTest(unittest.TestCase):
    def test_layout_head_and_checksum(self):
        blk = bytearray(SLOT_SIZE)
        blk[0] = 0x34
        blk[1] = 0x12
        blk[SUM_AT - 1] = 0x01
        s = fx.frame_sram({1: blk})
        self.assertEqual(len(s), 0x2000)
        self.assertEqual(s[0:14], MAGIC)
        self.assertEqual(s[0x1FF2:0x1FF2 + 14], MAGIC)
        self.assertEqual((s[0x0E], list(s[0x0F:0x12])), (0x02, [0x00, 0xC0, 0x00]))
        self.assertEqual(s[SLOTS[1]], 0x34)
        # 앞 54F 워드의 16비트 합: 1234 + 0100(끝 워드 바로 앞 바이트가 윗바이트)
        self.assertEqual(s[SLOTS[1] + SUM_AT] | s[SLOTS[1] + SUM_AT + 1] << 8, 0x1334)
        self.assertEqual(fx.saved_slots(s), [1])
        self.assertEqual(fx.base_block(s)[:2], b'\x34\x12')

    def test_bad_checksum_is_not_a_saved_slot(self):
        s = bytearray(fx.frame_sram({0: bytes(SLOT_SIZE)}))
        s[SLOTS[0] + SUM_AT] ^= 1
        self.assertEqual(fx.saved_slots(bytes(s)), [])
        self.assertEqual(fx.saved_slots(bytes(0x2000)), [])

    def test_last_saved_slot_gets_c0(self):
        s = fx.frame_sram({0: bytes(SLOT_SIZE), 2: bytes(SLOT_SIZE)}, last=0)
        self.assertEqual((s[0x0E], list(s[0x0F:0x12])), (0x05, [0xC0, 0x00, 0x00]))


class SlotTest(unittest.TestCase):
    def test_gold_and_hero_offsets(self):
        s = slot()
        s.gold = 12345
        s.set_hero(level=10, hp=999, max_hp=999, items=[0xCD])
        b = s.block
        self.assertEqual(b[0x19:0x1C], (12345).to_bytes(3, 'little'))
        self.assertEqual(b[0x52], 10)
        self.assertEqual((b[0x42], b[0x43], b[0x4E], b[0x4F]), (0xE7, 0x03, 0xE7, 0x03))
        self.assertEqual(b[0x56:0x56 + 12], bytes([0xCD] + [0xFF] * 11))
        self.assertEqual(s.gold, 12345)
        self.assertEqual(s.items(), [0xCD])

    def test_flag_lands_on_its_wram_bit(self):
        s = slot()
        addr, mask = wc.FLAGS['HOIMIN']
        s.flag('HOIMIN')
        self.assertEqual(s.block[(addr & 0xFFFF) - 0x2000], mask)
        self.assertEqual(s.flags(), ['HOIMIN'])
        s.flag('HOIMIN', False)
        self.assertEqual(s.flags(), [])

    def test_party_matches_compatcheck(self):
        s = slot()
        s.set_party('05')
        for a, v in cc.party_pokes('05', s.rom):
            self.assertEqual(s.block[(a & 0xFFFF) - 0x2000], v)

    def test_place_and_night_share_2033(self):
        s = slot()
        s.place = 7
        s.night = True
        self.assertEqual(s.block[0x33], 0x87)
        self.assertEqual((s.place, s.night), (7, True))
        self.assertEqual(s.goal, (0x37, 0x00, 50, 9))
        s.night = False
        self.assertEqual(s.block[0x33], 0x07)
        s.place = 'imuru'                     # 그룹 0x37 = 합성 칸 7
        self.assertEqual(s.place, 7)
        s.place = 0xC                         # 그룹 0x3C = 표 항목 0
        self.assertEqual(s.goal, (0x3C, 0x01, 1, 2))
        s.place = 3                           # 표에 그룹 0x33 이 없으면 이어 하기가 필드에 선다
        with self.assertRaises(ValueError):
            s.goal

    def test_outside_the_slot_is_refused(self):
        s = slot()
        for addr in (0x7E075B, 0x1FFF, 0x2A9E):
            with self.assertRaises(ValueError):
                s.poke(addr, 0)

    def test_set_parses_cli_values(self):
        s = slot()
        for kv in ('gold=500', 'flag=HOIMIN,KIDNAPPED', 'flag=-KIDNAPPED', 'poke=2058=CD;2223|08', 'night=1',
                   'place=7', 'items=CD,01'):
            s.set(*kv.split('=', 1))
        self.assertEqual((s.gold, s.flags(), s.night, s.place), (500, ['HOIMIN'], True, 7))
        self.assertEqual(s.block[0x223], 0x08)
        self.assertEqual(s.items(), [0xCD, 0x01])

    def test_to_sram_checksums_the_edited_block(self):
        s = slot()
        s.gold = 1
        sram = s.to_sram()
        blk = sram[SLOTS[0]:SLOTS[0] + SLOT_SIZE]
        self.assertEqual(blk[SUM_AT] | blk[SUM_AT + 1] << 8, checksum(blk))
        # 7E:2019 는 워드 2018 의 윗바이트
        self.assertEqual(checksum(blk), 0x100)


@unittest.skipUnless(CH1.exists(), 'work/ch1/dq4-ch1-full.sfc(dq4build.py) 또는 DQ4_CH1_ROM')
class Ch1RomTest(unittest.TestCase):
    def test_ruler_slots_of_ported_towns(self):
        rows = fx.place_rows(CH1.read_bytes())
        self.assertEqual({k: rows[k][0] for k in (2, 7, 8)}, {2: 0x36, 7: 0x37, 8: 0x3C})
        self.assertEqual(rows[7][1][:4], (0x37, 0x00, 50, 9))
        self.assertEqual(fx.place_slot(CH1.read_bytes(), 'batland'), 2)
        self.assertIsNone(rows[11][1])        # 그룹 42(コーミズ)는 1장 롬 표에 없음


if __name__ == '__main__':
    unittest.main()
