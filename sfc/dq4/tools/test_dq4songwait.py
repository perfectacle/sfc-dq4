import unittest
from pathlib import Path

import dq4soundpatch as P
import dq4songwait as W
from dq5song import RELOC_SEQ_TABLE

ARGS = Path(__file__).resolve().parent / 'dq4sound-game.args'
SIZE = 0x400000
# NDS 곡 가운데 되풀이하지 않는 징글(SYMB ME01~ME16, nds/dq4/docs/sound-format.md 「곡 목록」)
NDS_JINGLES = range(0x23, 0x33)
ENDS = bytes((0x20, 1, 4, 0, 0x51, 0x10, 0xFF))                 # 트랙 하나: 음 하나 / 끝
LOOPS = bytes((0x20, 1, 4, 0, 0x51, 0x10, 0xEA, 0xFB, 0xFF))    # 음 하나 / 맨 앞으로 점프


def put(rom, addr, data):
    o = W.offset(addr)
    rom[o:o + len(data)] = data


def call(op, target):
    return bytes([op, target & 0xFF, target >> 8 & 0xFF, target >> 16])


def args():
    words = ARGS.read_text(encoding='utf-8').split()
    songs = dict(words[i + 1].split('=') for i, w in enumerate(words) if w == '--song')
    calls = {int(a, 16): int(v.split(':')[1], 16)
             for a, v in (words[i + 1].split('=') for i, w in enumerate(words) if w == '--song-call')}
    return songs, calls, words


class Rom:
    """빈 4MB 롬에 시퀀스·기다림 자리를 써 넣는 도구."""

    def __init__(self, guard=True):
        self.rom = bytearray(SIZE)
        self.next = 0x6A8000
        self.seq(0x1E, ENDS)
        if guard:
            put(self.rom, W.WAIT, bytes([0x5C]) + P.WAIT_GUARD.to_bytes(3, 'little'))
            put(self.rom, P.WAIT_GUARD, P.wait_guard_code())

    def seq(self, n, data):
        put(self.rom, self.next, len(data).to_bytes(2, 'little') + data)
        put(self.rom, RELOC_SEQ_TABLE + n * 3, self.next.to_bytes(3, 'little'))
        self.next += len(data) + 2

    def table(self):
        put(self.rom, P.LOOP_TABLE, W.loop_table(bytes(self.rom)))

    def check(self, dq5=None):
        self.table()
        return W.check(bytes(self.rom), bytes(SIZE) if dq5 is None else dq5)

    @staticmethod
    def row(rows, at):
        return [r for r in rows if r[0] == at]


class Loops(unittest.TestCase):
    def test_walk(self):
        self.assertEqual(W.classify(ENDS), '끝남')
        self.assertEqual(W.classify(LOOPS), '되풀이')
        self.assertEqual(W.classify(b''), '끝남')

    def test_counted_loop_ends(self):
        # 음 / F5 3바퀴 맨 앞으로 / 끝: 카운터를 세면 끝남
        seq = bytes((0x20, 1, 4, 0, 0x51, 0x10, 0xF5, 0x03, 0xFA, 0xFF, 0xFF))
        self.assertEqual(W.classify(seq), '끝남')
        self.assertTrue(W.has_branches(seq))
        self.assertFalse(W.has_branches(ENDS))

    def test_flag_branch_both_ways(self):
        # E0 이 v 면 끝으로, 아니면 맨 앞으로 점프: 갈래에 따라 갈림
        mixed = bytes((0x20, 1, 4, 0, 0x51, 0x10, 0xE0, 0x03, 0x00, 0x01, 0xEA, 0xF7, 0xFF, 0xFF))
        self.assertEqual(W.classify(mixed), '판정 불가')
        # 두 갈래 모두 끝
        both = bytes((0x20, 1, 4, 0, 0xE0, 0x02, 0x00, 0x01, 0x51, 0x10, 0xFF))
        self.assertEqual(W.classify(both), '끝남')

    def test_table_covers_every_index(self):
        r = Rom()
        t = W.loop_table(bytes(r.rom))
        self.assertEqual(len(t), 0x100)
        self.assertEqual(t[0x64:], bytes(0x9C))

    def test_mixed_song_at_wait_fails_and_stays_out_of_table(self):
        r = Rom()
        # 첫머리 E0: 변수가 1 이면 끝으로, 아니면 음 하나 뒤 첫머리로(음 뒤 변수는 0 이라 되풀이)
        r.seq(0x1E, bytes((0x20, 1, 4, 0, 0xE0, 0x05, 0x00, 0x01, 0x51, 0x10, 0xEA, 0xF7, 0xFF, 0xFF)))
        put(r.rom, 0x069000, bytes((0xA9, 0x1E)) + call(0x22, W.WAIT))                 # 곡 변수를 모르는 자리
        put(r.rom, 0x069100, bytes((0x00, 0x16, 0x1E, 0x01, 0xA9, 0x1E)) + call(0x22, W.WAIT))   # 0C 1E 01
        put(r.rom, 0x069200, bytes((0xA9, 0x1E)) + call(0x22, W.JINGLE))               # 01 1E: 변수 0
        rows, bad = r.check()
        self.assertEqual(Rom.row(rows, 0x069002)[0][2], '판정 불가')
        self.assertTrue(any('06:9002' in p and 'E0' in p for p in bad))
        self.assertEqual(Rom.row(rows, 0x069106)[0][2], '끝남')
        self.assertEqual(Rom.row(rows, 0x069202)[0][2], '되풀이')
        self.assertEqual(W.loop_table(bytes(r.rom))[0x1E], 0)

    def test_chained_front_loops(self):
        r = Rom()
        r.seq(0x06, ENDS)
        put(r.rom, P.CHAIN_PAIRS + 0x06, b'\x4C')
        self.assertEqual(W.loop_table(bytes(r.rom))[0x06], 1)


class Sites(unittest.TestCase):
    def test_looping_song_at_church_wait_fails(self):
        r = Rom()
        r.seq(0x1E, LOOPS)
        put(r.rom, 0x06E17C, bytes((0xA9, 0x1E)) + call(0x22, W.JINGLE))
        rows, bad = r.check()
        self.assertEqual(r.row(rows, 0x06E17E)[0][1:], (0x1E, '되풀이'))
        self.assertTrue(any(p.startswith('06:E17E: 곡 1E') for p in bad))

    def test_jingle_passes(self):
        r = Rom()
        put(r.rom, 0x06E17C, bytes((0xA9, 0x1E)) + call(0x22, W.JINGLE))
        rows, bad = r.check(dq5=bytes(r.rom))                     # 원본에도 있는 자리
        self.assertEqual(r.row(rows, 0x06E17E)[0][2], '끝남')
        self.assertEqual([p for p in bad if '06:E17E' in p], [])

    def test_every_call_form_is_collected(self):
        r = Rom()
        put(r.rom, 0x069000, bytes((0xA9, 0x1E)) + call(0x5C, W.WAIT))                  # JML
        put(r.rom, 0x249000, bytes((0xA9, 0x1E, 0x20, 0x0F, 0xFF)))                      # 같은 뱅크 JSR
        put(r.rom, 0x259000, bytes((0xA9, 0x1E, 0x4C, 0x00, 0xFD)))                      # 같은 뱅크 JMP
        put(r.rom, 0x069100, bytes((0xA9, 0x1E, 0x20, 0x0F, 0xFF)))                      # 다른 뱅크 JSR 은 아님
        rows, _ = r.check()
        self.assertEqual({x[0] for x in rows if x[1] == 0x1E}, {0x069002, 0x249002, 0x259002})

    def test_wrapper_song_read_from_rom(self):
        r = Rom()
        r.seq(0x2F, LOOPS)
        put(r.rom, 0x25FCF6, bytes((0xE2, 0x20, 0xA9, 0x2F, 0x80, 0x04)))
        put(r.rom, 0x069000, call(0x22, 0x25FCF6))
        rows, _ = r.check()
        self.assertEqual(r.row(rows, 0x069000)[0][1:], (0x2F, '되풀이'))

    def test_fall_through_wrapper(self):
        r = Rom()
        put(r.rom, 0x25FCFC, bytes((0xE2, 0x20, 0xA9, 0x24)))
        put(r.rom, 0x069000, call(0x22, 0x25FCFC))
        rows, _ = r.check()
        self.assertEqual(r.row(rows, 0x069000)[0][1], 0x24)

    def test_indirect_needs_guard(self):
        for guard in (True, False):
            r = Rom(guard=guard)
            put(r.rom, 0x038EA4, call(0x22, 0x03A518) + call(0x22, W.WAIT))
            rows, bad = r.check()
            self.assertEqual(r.row(rows, 0x038EA8)[0][2], '가드' if guard else '곡 모름')
            self.assertEqual(any('반복 곡 가드가 없음' in p for p in bad), not guard)

    def test_unlisted_indirect_fails(self):
        r = Rom()
        put(r.rom, 0x069000, bytes((0xA5, 0x03)) + call(0x22, W.WAIT))
        _, bad = r.check()
        self.assertTrue(any(p.startswith('06:9002:') and 'INDIRECT' in p for p in bad))

    def test_guard_table_tail_is_checked(self):
        r = Rom()
        r.table()
        put(r.rom, P.LOOP_TABLE + 0xC8, b'\x01')
        _, bad = W.check(bytes(r.rom), bytes(SIZE))
        self.assertTrue(any('가드 표가 롬 시퀀스와 다른 곡 C8' in p for p in bad))

    def test_stale_guard_table_fails(self):
        r = Rom()
        r.table()
        r.seq(0x1E, LOOPS)
        _, bad = W.check(bytes(r.rom), bytes(SIZE))
        self.assertTrue(any('가드 표가 롬 시퀀스와 다른 곡 1E' in p for p in bad))

    def test_port_code_song_must_be_known(self):
        r = Rom()
        put(r.rom, 0x5E9000, bytes((0xA9, 0x1E)) + call(0x22, W.WAIT))
        _, bad = r.check()
        self.assertTrue(any('5E:9002' in p and 'PORT_SONGS' in p for p in bad))

    def test_original_sites_must_match_table(self):
        _, bad = Rom().check()
        self.assertTrue(any('DQ5_SITES 와 다름' in p for p in bad))

    def test_casino_table(self):
        r = Rom()
        put(r.rom, 0x23FEEC, bytes.fromhex('BD 0A FF'))
        put(r.rom, 0x23FF0A, bytes((0x28, 0x27, 0x26, 0x25)))
        put(r.rom, 0x23FEFC, call(0x22, W.WAIT))
        rows, _ = r.check()
        self.assertEqual(sorted(x[1] for x in r.row(rows, 0x23FEFC)), [0x25, 0x26, 0x27, 0x28])


class Guard(unittest.TestCase):
    def test_guard_shape(self):
        code = P.wait_guard_code()
        self.assertEqual(code[:12], bytes.fromhex('08 C2 30 48 DA 29 FF 00 AA E2 20 BF'))
        self.assertEqual(code[12:15], P.LOOP_TABLE.to_bytes(3, 'little'))
        self.assertEqual(code[15], 0xD0)
        self.assertEqual(17 + code[16], len(code) - 6)            # BNE 은 되풀이 갈래(RTL 쪽)로
        self.assertEqual(code[-6:], bytes.fromhex('C2 30 FA 68 28 6B'))
        self.assertIn(bytes.fromhex('22 5E FF 24 5C 16 FF 24'), code)
        self.assertEqual(P.WAIT_ORIGINAL, bytes.fromhex('08 C2 30 22 5E FF 24'))


class GameArgs(unittest.TestCase):
    def test_waited_slots_hold_jingles(self):
        """원본 DQ5 기다림 자리(--song-call 을 적용한 곡)와 포팅 코드가 기다리는 곡이 NDS 징글이거나, 대응표에 없는
        DQ5 그대로의 승리 1F 인지."""
        songs, calls, words = args()
        waited = {calls.get(lda, song) for song, lda in W.DQ5_SITES.values()
                  if song is not None and song < 0x32} | set(W.PORT_SONGS)
        # 1E 는 되풀이하는 コロシアム楽屋(엔돌 대기실 맵 곡). 원본이 1E 를 기다리던 교회 등 여덟 자리는 25 教会治療 로
        self.assertNotIn(0x1E, waited)
        self.assertIn(0x25, waited)
        for slot in sorted(waited):
            nds = songs.get(f'{slot:02X}')
            if nds is None:
                self.assertEqual(slot, 0x1F, f'곡 자리 {slot:02X} 는 끝을 기다리는데 대응표에 없음')
            else:
                self.assertIn(int(nds, 16), NDS_JINGLES, f'곡 자리 {slot:02X} 는 끝을 기다리는데 NDS {nds}')
        self.assertIn('--wait-guard', words)

    def test_song_calls_point_at_known_sites(self):
        _, calls, _ = args()
        ldas = {lda for _, lda in W.DQ5_SITES.values() if lda is not None}
        self.assertEqual(set(calls) - ldas, set())


if __name__ == '__main__':
    unittest.main()
