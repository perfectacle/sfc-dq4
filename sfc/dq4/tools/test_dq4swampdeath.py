"""dq4swampdeath 의 06:80A1 훅을 65816 해석기로 돈다(롬 없이)."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4swampdeath as sd  # noqa: E402


class Out(Exception):
    pass


def run(hp, damage, record, alive, count, safe=False, chapter3=False, armed=False):
    """(빠져나간 자리, wram)."""
    import w65816
    blob, labels = sd.code()
    rom = bytearray(0x400000)
    o = (sd.CODE_AT >> 16 & 0x7F) * 0x8000 + (sd.CODE_AT & 0x7FFF)
    rom[o:o + len(blob)] = blob
    cpu = w65816.Cpu(bytes(rom), bytearray(0x20000))
    cpu.p, cpu.x, cpu.y = 0x30, 0, record
    w = cpu.wram
    w[0x42], w[0x43], w[0x46] = record, damage, hp
    w[0x201D] = count
    for n in range(count):
        w[0x2041 + 42 * n] = 0x80 if n in alive else 0x00
        w[0x2042 + 42 * n] = hp if n == record else 0x30
    w[0x2019:0x201C] = (1001).to_bytes(3, 'little')
    if safe:
        w[sd.PARTY_ITEMS & 0xFFFF] = __import__('dq4itemport').IRON_SAFE
    if chapter3:
        w[0x2208] |= 0x08
    if armed:
        w[0x19AE] = 0x80
    for at in (sd.AFTER_ONE, sd.NO_DAMAGE, sd.SUBTRACT):
        cpu.hooks[at] = lambda c, at=at: (_ for _ in ()).throw(Out(at))
    cpu.push(0x00)
    cpu.push16(0x0000)
    cpu.pbr, cpu.pc = labels['check'] >> 16, labels['check'] & 0xFFFF
    try:
        for _ in range(10000):
            cpu.step()
    except Out as e:
        return e.args[0], w, labels
    raise AssertionError('훅이 끝나지 않음')


class HookTests(unittest.TestCase):
    def test_other_hp_and_damage_keep_the_original_path(self):
        self.assertEqual(run(5, 1, 0, {0}, 1)[0], sd.AFTER_ONE)
        self.assertEqual(run(1, 7, 0, {0}, 1)[0], sd.NO_DAMAGE)     # 실내 결계(피해 7)는 DQ5 처럼 1 에서 멈춤

    def test_hero_gets_hp_zero_and_the_message_script(self):
        at, w, labels = run(1, 1, 0, {0, 1}, 2)
        self.assertEqual(at, sd.NO_DAMAGE)
        self.assertEqual((w[0x2042], w[0x2043], w[sd.WHO & 0xFFFF]), (0, 0, 0))
        self.assertEqual(w[0x19B3] | w[0x19B4] << 8 | w[0x19B5] << 16, labels['script'])
        self.assertEqual(w[0x19AE] & 0x80, 0x80)
        self.assertEqual(w[0x2041] & 0x80, 0x80)                      # 쓰러짐 표시는 메시지 뒤(after)

    def test_companion_last_alive_halves_gold_and_lets_dq5_kill(self):
        at, w, _ = run(1, 1, 1, {1}, 2)
        self.assertEqual(at, sd.SUBTRACT)
        self.assertEqual(int.from_bytes(w[0x2019:0x201C], 'little'), 500)
        self.assertEqual(w[0x19AE] & 0x80, 0)

    def test_iron_safe_keeps_gold_in_chapter3(self):
        _, w, _ = run(1, 1, 1, {1}, 2, safe=True, chapter3=True)
        self.assertEqual(int.from_bytes(w[0x2019:0x201C], 'little'), 1001)
        _, w, _ = run(1, 1, 1, {1}, 2, safe=True)
        self.assertEqual(int.from_bytes(w[0x2019:0x201C], 'little'), 500)

    def test_companion_with_others_alive_arms_the_redraw(self):
        at, w, labels = run(1, 1, 1, {0, 1}, 2)
        self.assertEqual(at, sd.SUBTRACT)
        self.assertEqual(w[0x19B3] | w[0x19B4] << 8 | w[0x19B5] << 16, labels['redraw'])
        self.assertEqual(int.from_bytes(w[0x2019:0x201C], 'little'), 1001)


if __name__ == '__main__':
    unittest.main()
