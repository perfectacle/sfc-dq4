"""장 끝 기록 물음과 넘김(dq4ch2event.chapter_flow·chapter_save·save_talk)을 w65816 흉내로 돌려 FC 1A:$B943 의 갈래를 본다."""
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(TOOLS), str(TOOLS.parents[1] / 'dq5' / 'tools')]

import dq4ch2event as ch2  # noqa: E402
import dq4fieldtravel as travel  # noqa: E402

FLOW, STATE, GO, TALK, SAVE, ENGINE_SAVE = 0x5E8000, 0x5E9000, 0x5E9100, 0x5E9200, 0x5E9300, 0x258026
RET = 0xFFFFFE
COUNT = 0x1F00          # 흉내 루틴마다 부른 횟수(WRAM): STATE, GO, TALK, SAVE 차례
FLAGS = 0x2190


def _counter(k, extra=b''):
    """WRAM COUNT + k 를 하나 올리고 RTL(M 8)."""
    at = (0x7E0000 | COUNT + k).to_bytes(3, 'little')
    return extra + bytes((0xAF, *at, 0x1A, 0x8F, *at, 0x6B))


def _flag(f):
    return FLAGS + f[0]


def _cpu(rom, wram, sram=None):
    from w65816 import Cpu

    class WithSram(Cpu):
        def read(self, a):
            if a >> 16 == 0x70 and a & 0xFFFF < 0x8000 and sram is not None:
                return sram[a & 0xFFFF]
            return super().read(a)
    return WithSram(rom, wram)


def _rom(started=ch2.CHAPTER2):
    rom = bytearray(0x400000)

    def put(at, code):
        o = travel.lorom(at)
        rom[o:o + len(code)] = code
    put(FLOW, ch2.chapter_flow(started, STATE, GO, TALK, SAVE))
    a = 0x7E0000 | _flag(started)
    # 상태: 시작 flag 를 켠다(넘김이 다음 장 flag 를 켜는 것과 같음)
    put(STATE, _counter(0, bytes((0xAF, *a.to_bytes(3, 'little'), 0x09, started[1], 0x8F, *a.to_bytes(3, 'little')))))
    put(GO, _counter(1))
    put(TALK, _counter(2))
    put(SAVE, _counter(3))
    return bytes(rom)


def _run(rom, entry, wram, sram=None, a=0):
    cpu = _cpu(rom, wram, sram)
    cpu.a, cpu.x, cpu.p = a, 0, 0x30
    cpu.push(0xFF)
    cpu.push16(0xFFFD)
    cpu.pbr, cpu.pc = entry >> 16, entry & 0xFFFF
    while (cpu.pbr << 16 | cpu.pc) != RET:
        if cpu.steps > 20000:
            raise AssertionError(f'no return by {cpu.pbr:02X}:{cpu.pc:04X}')
        cpu.step()
    return cpu


class FlowTest(unittest.TestCase):
    def frame(self, **flags):
        """흐름을 한 번 부른 뒤 (A, [STATE, GO, TALK, SAVE] 횟수, 7E:21A3)."""
        wram = bytearray(0x20000)
        for name, (f, m) in (('started', ch2.CHAPTER2), ('answered', ch2.ANSWERED), ('decided', ch2.DECIDED),
                             ('save_yes', ch2.SAVE_YES)):
            if flags.get(name):
                wram[_flag((f, m))] |= m
        cpu = _run(_rom(), FLOW, wram)
        return cpu.a & 0xFFFF, list(cpu.wram[COUNT:COUNT + 4]), cpu.wram[_flag(ch2.ANSWERED)]

    def test_first_frame_hands_over_the_state_and_asks(self):
        # 「완」 상자·다음 장 상태 → 기록 물음 대화, 다음 프레임에 다시
        self.assertEqual(self.frame()[:2], (1, [1, 0, 1, 0]))

    def test_waits_while_the_talk_runs(self):
        self.assertEqual(self.frame(started=True)[:2], (1, [0, 0, 0, 0]))

    def test_yes_saves_then_moves(self):
        a, counts, temps = self.frame(started=True, answered=True, decided=True, save_yes=True)
        self.assertEqual((a, counts), (0, [0, 1, 0, 1]))
        self.assertEqual(temps & (ch2.ANSWERED[1] | ch2.DECIDED[1] | ch2.SAVE_YES[1]), 0)

    def test_no_then_yes_moves_without_saving(self):
        a, counts, _ = self.frame(started=True, answered=True, decided=True)
        self.assertEqual((a, counts), (0, [0, 1, 0, 0]))

    def test_no_then_no_asks_again(self):
        # FC: 03BF 에서 아니요면 03BE 부터 다시
        a, counts, temps = self.frame(started=True, answered=True)
        self.assertEqual((a, counts), (1, [0, 0, 1, 0]))
        self.assertEqual(temps & ch2.ANSWERED[1], 0)


class SaveTest(unittest.TestCase):
    def run_save(self, sram_slots, place):
        rom = bytearray(0x400000)
        code = ch2.chapter_save(travel.slot_of_fc(travel.CHAPTER2_CHURCH_FC))
        o = travel.lorom(SAVE)
        rom[o:o + len(code)] = code
        # 25:8026 흉내: 받은 칸(A)과 그때의 7E:2033 을 적는다
        engine = bytes((0x8F, 0x10, 0x1F, 0x7E, 0xAF, 0x33, 0x20, 0x7E, 0x8F, 0x11, 0x1F, 0x7E, 0x6B))
        o = travel.lorom(ENGINE_SAVE)
        rom[o:o + len(engine)] = engine
        sram = bytearray(0x8000)
        sram[0x0F:0x12] = bytes(sram_slots)
        wram = bytearray(0x20000)
        wram[0x2033] = place
        cpu = _run(bytes(rom), SAVE, wram, sram)
        return cpu.wram[0x1F10], cpu.wram[0x1F11]

    def test_saves_the_chapter_church_into_the_current_book(self):
        church = travel.slot_of_fc(travel.CHAPTER2_CHURCH_FC)
        # 지금 칸 = bit7 칸(교회 기록 목록의 처음 커서). 기록하기 전에 귀환 자리를 두고, 밤 비트는 그대로
        self.assertEqual(self.run_save((0x40, 0xC0, 0x40), 0x82), (1, 0x80 | church))
        self.assertEqual(self.run_save((0x40, 0x40, 0xC0), 0x02), (2, church))
        self.assertEqual(self.run_save((0x40, 0x40, 0x40), 0x02), (0, church))


class TalkTest(unittest.TestCase):
    def test_talk_branches_like_fc(self):
        body = ch2.save_talk(0x1234, 0x1235)
        self.assertEqual(body[0], {"op": "msg", "id": "1234"})
        yes = body[1]
        flags = [(op["index"], op["mask"]) for op in yes["then"]]
        self.assertEqual(flags, [ch2.SAVE_YES, ch2.DECIDED, ch2.ANSWERED])
        no = yes["else"]
        self.assertEqual(no[0], {"op": "msg", "id": "1235"})
        self.assertEqual([(op["index"], op["mask"]) for op in no[1]["then"]], [ch2.DECIDED, ch2.ANSWERED])
        self.assertEqual([(op["index"], op["mask"]) for op in no[1]["else"]], [ch2.ANSWERED])

    def test_messages_name_the_ended_chapter(self):
        text = ''.join(p for p in ch2.save_messages(2)['save_skip'] if isinstance(p, str))
        self.assertIn('제2장', text)
        self.assertIn('모험의 서', ''.join(p for p in ch2.save_messages(1)['save_ask'] if isinstance(p, str)))

    def test_chapter_start_cells_match_the_openings(self):
        import dq4ch3event as ch3
        (_, g2, n2, c2, r2, o2), (_, g3, n3, c3, r3, o3) = travel.CHAPTER_STARTS
        self.assertEqual((f'{g2:02X}/{n2:02X}', c2, r2, o2), (ch2.THRONE, ch2.START_CELL, travel.CHAPTER2_CHURCH_FC,
                                                             (0x7E2190 + ch2.OPENING[0], ch2.OPENING[1])))
        self.assertEqual((f'{g3:02X}/{n3:02X}', c3, r3, o3), (ch3.HOUSE, ch3.START_CELL, ch3.CHURCH_FC,
                                                             (0x7E2190 + ch3.OPENING[0], ch3.OPENING[1])))
        # 첫머리 열쇠는 ルーラ 칸·새 게임 칸 밖이고, 저장 훅이 보는 flag 는 장 넘김 흐름의 것
        self.assertTrue(all(key > travel.UNSAVED for key, *_ in travel.CHAPTER_STARTS))
        self.assertEqual(travel.SAVE_YES_FLAG, (0x7E2190 + ch2.SAVE_YES[0], ch2.SAVE_YES[1]))


if __name__ == '__main__':
    unittest.main()
