"""곡 고르기(dq4soundpatch.song_pick_code)를 롬 없이 작은 65816 해석기로 돌려 보고, 설치 자리·게임 인자·2장 맵 곡 바이트를 고정한다."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4ch2event  # noqa: E402
import dq4groupbuild  # noqa: E402
import dq4soundpatch as patch  # noqa: E402
from dq5map import lorom  # noqa: E402

ARGS = Path(__file__).resolve().parent / 'dq4sound-game.args'
CH2_FLAG = 0x7E2190 + dq4ch2event.CHAPTER2[0]
GAME_PICKS = [(0x01, 0x30, ('night',)), (0x06, 0x31, ('night',)), (0x02, 0x05, ('flag', CH2_FLAG, dq4ch2event.CHAPTER2[1]))]


def run_pick(code, base, a, *, night=False, wram=None, m16=False, high=0x12):
    """고르기 루틴만 흉내 낸다(쓰는 명령만). (A, 돌아올 때 P, 스택이 제자리인지)."""
    wram = wram or {}
    pc, p, stack = base, 0x20 if not m16 else 0x00, [0xEE]   # 0xEE: 부른 쪽 스택 표시
    p_in = p
    acc = (high << 8) | a
    flags = {'z': False, 'c': False}
    while True:
        op = code[pc - base]
        if op == 0x08:
            stack.append(('P', p)); pc += 1
        elif op == 0xE2:
            p |= code[pc - base + 1]; pc += 2
        elif op == 0xC9:
            flags['z'] = (acc & 0xFF) == code[pc - base + 1]; pc += 2
        elif op in (0xD0, 0xF0, 0x90, 0x80):
            rel = code[pc - base + 1]
            rel -= 256 * (rel > 127)
            taken = {0xD0: not flags['z'], 0xF0: flags['z'], 0x90: not flags['c'], 0x80: True}[op]
            pc += 2 + (rel if taken else 0)
        elif op == 0x22:
            target = int.from_bytes(code[pc - base + 1:pc - base + 4], 'little')
            assert target == patch.NIGHT_TEST, f'{target:06X}'
            flags['c'] = night
            pc += 4
        elif op == 0x48:
            stack.append(('A', acc & 0xFF)); pc += 1
        elif op == 0x68:
            kind, v = stack.pop()
            assert kind == 'A'
            acc = (acc & 0xFF00) | v
            flags['z'] = v == 0
            pc += 1
        elif op == 0xAF:
            addr = int.from_bytes(code[pc - base + 1:pc - base + 4], 'little')
            acc = (acc & 0xFF00) | wram.get(addr, 0); pc += 4
        elif op == 0x29:
            acc = (acc & 0xFF00) | (acc & code[pc - base + 1]); flags['z'] = (acc & 0xFF) == 0; pc += 2
        elif op == 0xA9:
            acc = (acc & 0xFF00) | code[pc - base + 1]; pc += 2
        elif op == 0x28:
            kind, p = stack.pop()
            assert kind == 'P'
            pc += 1
        elif op == 0x6B:
            return acc, p == p_in, stack == [0xEE]
        else:
            raise AssertionError(f'unexpected opcode {op:02X} at {pc:06X}')


class SongPickTests(unittest.TestCase):
    def setUp(self):
        self.code, self.pick, self.map_stub, self.stubs = patch.song_pick_code(GAME_PICKS)

    def pick_of(self, song, **kw):
        acc, p_kept, stack_kept = run_pick(self.code, self.pick, song, **kw)
        self.assertTrue(p_kept)
        self.assertTrue(stack_kept)
        self.assertEqual(acc >> 8, kw.get('high', 0x12))
        return acc & 0xFF

    def test_night_songs_only_at_night(self):
        self.assertEqual(self.pick_of(0x01), 0x01)
        self.assertEqual(self.pick_of(0x06), 0x06)
        self.assertEqual(self.pick_of(0x01, night=True), 0x30)
        self.assertEqual(self.pick_of(0x06, night=True), 0x31)

    def test_field_song_follows_the_chapter_flag(self):
        on = {CH2_FLAG: dq4ch2event.CHAPTER2[1] | 0x40}
        off = {CH2_FLAG: 0xFF & ~dq4ch2event.CHAPTER2[1]}
        self.assertEqual(self.pick_of(0x02, wram=on), 0x05)
        self.assertEqual(self.pick_of(0x02, wram=on, night=True), 0x05)
        self.assertEqual(self.pick_of(0x02, wram=off), 0x02)

    def test_other_songs_pass(self):
        for song in (0x09, 0x0A, 0x17, 0x1D, 0x30, 0x31, 0x05):
            self.assertEqual(self.pick_of(song, night=True, wram={CH2_FLAG: 0xFF}), song)

    def test_sixteen_bit_caller_keeps_its_mode(self):
        self.assertEqual(self.pick_of(0x01, night=True, m16=True), 0x30)

    def test_rejects_a_picked_song_that_is_picked_again(self):
        with self.assertRaisesRegex(ValueError, 'picked again'):
            patch.song_pick_code([(0x01, 0x30, ('night',)), (0x30, 0x02, ('night',))])

    def test_stubs_queue_the_original_command(self):
        self.assertEqual(self.code[self.map_stub - self.pick:][:9],
                         bytes([0x22]) + self.pick.to_bytes(3, 'little') + bytes.fromhex('CF 8B 1D 7E 6B'))
        for site, command in patch.SONG_ARG_ENTRIES.items():
            at = self.stubs[site] - self.pick
            # 02·03·04 는 인자가 지금 곡이면 고르지 않는다(BEQ 가 JSL 4바이트를 건너뜀)
            keep = '' if command == 0x01 else 'CF 8B 1D 7E F0 04 '
            want = (bytes.fromhex('08 E2 20 ' + keep + '22') + self.pick.to_bytes(3, 'little')
                    + bytes.fromhex(f'48 A9 {command:02X} 5C 83 FF 24'))
            self.assertEqual(self.code[at:at + len(want)], want)

    def test_map_routine_entry_bytes_stay(self):
        # 00:CE75(BMI)·CE86(BRA) 가 CE9D(AND #$7F)로 뛰므로 CE9A~CE9E 는 건드리지 않는다
        self.assertEqual(patch.SONG_PICK_SITE, 0x00CEAB)

    def test_parse(self):
        self.assertEqual(patch.parse_song_pick('01=30@night'), (0x01, 0x30, ('night',)))
        self.assertEqual(patch.parse_song_pick('02=05@7E2208&10'), (0x02, 0x05, ('flag', 0x7E2208, 0x10)))
        for bad in ('01=01@night', '02=05@7F2208&10', '02=05@7E2208&00', '00=05@night'):
            with self.assertRaises(ValueError):
                patch.parse_song_pick(bad)

    def test_vehicle_code_compares_the_picked_song(self):
        code = patch.vehicle_song_code(self.pick)
        self.assertTrue(code.startswith(bytes.fromhex('48 AD 4B 19 22') + self.pick.to_bytes(3, 'little')
                                        + bytes.fromhex('CD 8B 1D F0')))


class InstallSiteTests(unittest.TestCase):
    def test_install_writes_the_hooks(self):
        from test_dq4soundpatch import melody, synthetic_base
        data = bytearray(synthetic_base())
        data[lorom(patch.NIGHT_TEST):lorom(patch.NIGHT_TEST) + len(patch.NIGHT_TEST_ORIGINAL)] = patch.NIGHT_TEST_ORIGINAL
        data[lorom(patch.SONG_PICK_SITE):lorom(patch.SONG_PICK_SITE) + 4] = patch.SONG_PICK_ORIGINAL
        for site, command in patch.SONG_ARG_ENTRIES.items():
            data[lorom(site):lorom(site) + 9] = bytes.fromhex(f'08 E2 20 48 A9 {command:02X} 4C 83 FF')
        data[lorom(patch.VEHICLE_SONG_SITE):lorom(patch.VEHICLE_SONG_SITE) + 11] = bytes.fromhex(
            '22 91 FE 24 AD 4B 19 22 9A FE 24')
        out, report = patch.install(bytes(data), {0x48: patch.Replacement(melody(), (0x03,))},
                                    song_picks=GAME_PICKS, vehicle_song=True)
        code, pick, map_stub, stubs = patch.song_pick_code(GAME_PICKS)
        self.assertEqual(out[lorom(patch.SONG_PICK):lorom(patch.SONG_PICK) + len(code)], code)
        self.assertEqual(out[lorom(patch.SONG_PICK_SITE):lorom(patch.SONG_PICK_SITE) + 4],
                         bytes([0x22]) + map_stub.to_bytes(3, 'little'))
        for site in patch.SONG_ARG_ENTRIES:
            self.assertEqual(out[lorom(site):lorom(site) + 4], bytes([0x5C]) + stubs[site].to_bytes(3, 'little'))
        vehicle = patch.vehicle_song_code(pick)
        self.assertEqual(out[lorom(patch.VEHICLE_SONG):lorom(patch.VEHICLE_SONG) + len(vehicle)], vehicle)
        self.assertEqual(report['song_picks'], ['01=30@night', '06=31@night', '02=05@7E2208&10'])


class GameArgsTests(unittest.TestCase):
    def test_game_args_pick_night_and_chapter2_field_songs(self):
        lines = ARGS.read_text(encoding='utf-8').split()
        picks = [patch.parse_song_pick(lines[i + 1]) for i, v in enumerate(lines) if v == '--song-pick']
        self.assertEqual(picks, GAME_PICKS)


class Chapter2MapSongTests(unittest.TestCase):
    def test_chapter2_towns_and_castle_take_fc_branch_songs(self):
        # FC 맵 곡은 맵 갈래로 고른다: 갈래 0(성) → 王宮のメヌエット(자리 01), 갈래 1(마을) → 街でのひととき(자리 06),
        # 갈래 3(사당) → 不思議のほこら(18), 갈래 4(탑) → 呪われし塔(0A), 갈래 5(동굴) → 恐怖の洞窟(09)
        songs = {part['fc']: part.get('music') for group in (0x3D, 0x45) for part in dq4groupbuild.LINKS[group]}
        self.assertEqual(songs, {0x01: 0x01, 0x0E: 0x06, 0x0F: 0x06, 0x13: 0x06, 0x0C: 0x06, 0x2E: 0x0A, 0x39: 0x09,
                                 0x1E: 0x18, 0x1F: 0x18})


if __name__ == '__main__':
    unittest.main()
