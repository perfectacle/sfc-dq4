import unittest
from pathlib import Path

import dq4songwait as W

ARGS = Path(__file__).resolve().parent / 'dq4sound-game.args'
SIZE = 0x30 * 0x8000
# 1장 롬에서 곡이 끝나기를 기다리는 자리가 있고 그 자리에 닿는 곡 자리(dq4songwait 의 자리 표, 사운드 포팅 형식 문서).
# 교회 치료 1E, 여관 1D, 기록 20, 레벨 업 21, 합류 26 등
WAITED = (0x1D, 0x1E, 0x20, 0x21, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2B, 0x2D, 0x2E)
# NDS 곡 가운데 되풀이하지 않는 징글(SYMB ME01~ME16, nds/dq4/docs/sound-format.md 「곡 목록」)
NDS_JINGLES = range(0x23, 0x33)


def put(rom, addr, data):
    o = W.offset(addr)
    rom[o:o + len(data)] = data


def sound(**loops):
    """{'1E': loop_start 또는 None} → dq4soundset 보고 꼴."""
    return {'songs': {k: {'nds_song': '00', 'conversion': {'loop_start': v}} for k, v in loops.items()}}


def call(op, target):
    return bytes([op, target & 0xFF, target >> 8 & 0xFF, target >> 16])


class Sites(unittest.TestCase):
    def setUp(self):
        self.rom = bytearray(SIZE)
        o = W.offset(0x23FF0A)
        self.rom[o:o + 4] = bytes((0x28, 0x27, 0x26, 0x25))

    def check(self, **loops):
        base = dict.fromkeys(['25', '26', '27', '28'], None)
        base.update(loops)
        return W.check(bytes(self.rom), b'', sound(**base))

    def row(self, rows, at):
        return [r for r in rows if r[0] == at]

    def test_looping_song_at_church_wait_fails(self):
        put(self.rom, 0x06E17C, bytes((0xA9, 0x1E)) + call(0x22, W.JINGLE))
        rows, bad = self.check(**{'1E': 191})
        self.assertEqual(self.row(rows, 0x06E17E)[0][1:], (0x1E, 'NDS 00', '되풀이'))
        self.assertTrue(any(p.startswith('06:E17E: 곡 1E') for p in bad))

    def test_jingle_at_church_wait_passes(self):
        put(self.rom, 0x06E17C, bytes((0xA9, 0x1E)) + call(0x22, W.JINGLE))
        rows, bad = self.check(**{'1E': None})
        self.assertEqual(self.row(rows, 0x06E17E)[0][3], '끝남')
        self.assertEqual([p for p in bad if '06:E17E' in p], [])

    def test_wait_without_immediate_needs_a_reason(self):
        put(self.rom, 0x069000, bytes((0xA5, 0x03)) + call(0x22, W.WAIT))
        _, bad = self.check()
        self.assertTrue(any(p.startswith('06:9002:') and '즉값이 아님' in p for p in bad))

    def test_long_jump_counts(self):
        put(self.rom, 0x069000, bytes((0xA9, 0x1E)) + call(0x5C, W.WAIT))
        rows, bad = self.check(**{'1E': 0})
        self.assertEqual(self.row(rows, 0x069002)[0][3], '되풀이')

    def test_unreached_site_is_reported_not_failed(self):
        put(self.rom, 0x05DE04, bytes((0xA9, 0x23)) + call(0x22, W.JINGLE))
        rows, bad = self.check(**{'23': 0})
        self.assertEqual(self.row(rows, 0x05DE06)[0][3], '되풀이(미확인 자리)')
        self.assertEqual([p for p in bad if '05:DE06' in p], [])

    def test_wrapper_carries_its_song(self):
        put(self.rom, 0x069000, call(0x22, 0x25FCF6))
        rows, _ = self.check(**{'22': 0})
        self.assertEqual(self.row(rows, 0x069000)[0][1], 0x22)

    def test_casino_table_songs(self):
        rows, _ = self.check()
        self.assertEqual(sorted(r[1] for r in self.row(rows, 0x23FEFC) if r[1] is not None), [0x25, 0x26, 0x27, 0x28])

    def test_inn_entry_counts_and_its_body_does_not(self):
        start, end = W.inn_wait_entry()
        put(self.rom, 0x06E422, bytes((0xA9, 0x1D)) + call(0x22, start))
        put(self.rom, start + 0x10, call(0x22, W.WAIT))
        rows, bad = self.check(**{'1D': 5})
        self.assertEqual(self.row(rows, 0x06E424)[0][3], '되풀이')
        self.assertEqual(self.row(rows, start + 0x10), [])

    def test_effects_are_not_judged(self):
        put(self.rom, 0x069000, bytes((0xA9, 0x37)) + call(0x22, W.WAIT))
        rows, bad = self.check()
        self.assertEqual(self.row(rows, 0x069002)[0][3], '효과음')


class GameArgs(unittest.TestCase):
    def test_waited_slots_hold_nds_jingles(self):
        words = ARGS.read_text(encoding='utf-8').split()
        songs = dict(words[i + 1].split('=') for i, w in enumerate(words) if w == '--song')
        for slot in WAITED:
            nds = songs.get(f'{slot:02X}')
            if nds is not None:
                self.assertIn(int(nds, 16), NDS_JINGLES, f'곡 자리 {slot:02X} 는 끝을 기다리는데 NDS {nds}')

    def test_church_slot_is_church_jingle(self):
        words = ARGS.read_text(encoding='utf-8').split()
        songs = dict(words[i + 1].split('=') for i, w in enumerate(words) if w == '--song')
        self.assertEqual(songs['1E'], '28')


if __name__ == '__main__':
    unittest.main()
