"""dq5clock 의 주기 차례·리프레시·HDMA 시각 검사(롬 없이 짧은 코드로)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5clock  # noqa: E402


def cpu(code, h=100, v=10, t=0, wram=None):
    rom = bytearray(0x80000)
    rom[:len(code)] = code
    clock = {'masterClock': str(t), 'memoryManager.hClock': str(h), 'ppu.scanline': str(v),
             'memoryManager.dramRefreshPosition': str(538 - ((t - h) & 7)), 'ppu.frameCount': '0'}
    c = dq5clock.Cpu(bytes(rom), wram or bytes(0x20000), clock)
    c.pbr, c.pc, c.s = 0, 0x8000, 0x1FF
    return c


def deltas(c, n):
    out = []
    for _ in range(n):
        t = c.t
        c.step()
        out.append(c.t - t)
    return out


class Timing(unittest.TestCase):
    def test_cycle_order(self):
        # REP #$30(22) · STA $1234,X 16비트(46) · NOP(14) · LDA $00 16비트(32)
        c = cpu(bytes([0xC2, 0x30, 0x9D, 0x34, 0x12, 0xEA, 0xA5, 0x00]))
        self.assertEqual(deltas(c, 4), [22, 46, 14, 32])

    def test_refresh_alternates(self):
        # 줄마다 538 - (줄 첫머리 클록 & 7) 에서 40. 1364 가 8 의 배수가 아니라 줄마다 534·538 을 오간다
        c = cpu(bytes([0xEA] * 0x4000), h=0, v=10, t=4)
        seen = []
        for _ in range(600):
            v0, t0 = c.v, c.t
            c.step()
            if c.t - t0 > 14:
                seen.append((v0, c.ref))
        self.assertGreaterEqual(len(seen), 4)
        refs = {r for _, r in seen}
        self.assertEqual(refs, {534, 538})

    def test_hdma_waits_one_cycle(self):
        # 1104 에 걸린 HDMA 는 한 주기 늦게 한다. 1090 에서 시작한 NOP(1090~1104)가 아니라 다음 NOP 에 붙고,
        # 채널 하나·옮김 없음이면 맞춤 4 + 덧 8 + 표 8 + 끝 맞춤 4 = 24
        w = bytearray(0x20000)
        w[0x1000] = 0x7F
        c = cpu(bytes([0xEA] * 0x400), h=1090, v=10, t=1090 + 4, wram=bytes(w))
        c.reg[0x420C] = 1
        c.reg[0x4304] = 0x7E
        c.hch[0] = {'do': 0, 'cnt': 0x40, 'p': 0x1000, 'ia': 0}
        d = deltas(c, 4)
        self.assertEqual(d, [14, 38, 14, 14])


if __name__ == '__main__':
    unittest.main()
