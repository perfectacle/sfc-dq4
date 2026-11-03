"""dq4sfxscene: 대응표 해석·기대값 계산·대기열 읽기·울림 판정·장면 목록이 대응표를 빠짐없이 맡는지(롬 없이)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4sfxscene as s  # noqa: E402

ARGS = '''--song
06=0E
--fast-receive
--sfx
34-02=131
--sfx-call
05E6A9=35:3F
--sfx-call
01E01B=35:45
--sfx-remap
37-14=45-03
--sfx-weapon
00=43-01
--sfx-weapon-songs
17
--sfx-item
3F-01
--sfx-pcm
40-03=-
--inn-jingle
'''


class TableTest(unittest.TestCase):
    def setUp(self):
        self.t = s.load_table(ARGS)

    def test_parse_options_without_values(self):
        opts = s.parse_args_file(ARGS)
        self.assertIn(('--fast-receive', None), opts)
        self.assertIn(('--inn-jingle', None), opts)
        self.assertIn(('--sfx', '34-02=131'), opts)

    def test_table_fields(self):
        t = self.t
        self.assertEqual(t.sfx, {(0x34, 0x02): '131'})
        self.assertEqual(t.calls, {0x05E6A9: (0x35, 0x3F), 0x01E01B: (0x35, 0x45)})
        self.assertEqual(t.remap, {(0x37, 0x14): (0x45, 0x03)})
        self.assertEqual(t.weapons, {0x00: (0x43, 0x01)})
        self.assertEqual(t.weapon_songs, [0x17])
        self.assertEqual(t.items, [(0x3F, 0x01)])
        self.assertTrue(t.inn_jingle)
        self.assertEqual(t.songs, {0x06: 0x0E})

    def test_routed(self):
        t = self.t
        self.assertEqual(s.routed(t, 0x35, 0x00, 0x05E6A9), (0x3F, 0x00))   # 부르는 자리의 번호만 바뀜
        self.assertEqual(s.routed(t, 0x35, 0x02, 0x01E01B), (0x45, 0x02))
        self.assertEqual(s.routed(t, 0x37, 0x14), (0x45, 0x03))             # 입구에서 돌려 부르기
        self.assertEqual(s.routed(t, 0x34, 0x02), (0x34, 0x02))             # 갈래만 바꾼 것은 번호 그대로
        with self.assertRaises(ValueError):
            s.routed(t, 0x36, 0x00, 0x05E6A9)

    def test_weapon_sound_only_in_weapon_songs(self):
        self.assertEqual(s.weapon_sound(self.t, 0x00, 0x17), (0x43, 0x01))
        self.assertIsNone(s.weapon_sound(self.t, 0x00, 0x18))
        self.assertIsNone(s.weapon_sound(self.t, 0x05, 0x17))

    def test_entries(self):
        self.assertEqual(sorted(self.t.entries()), sorted([
            'sfx 34-02', 'pcm 40-03', 'call 05E6A9', 'call 01E01B', 'remap 37-14', 'weapon 00', 'item 3F-01',
            'inn-jingle']))


class RomCheckTest(unittest.TestCase):
    def test_call_sites(self):
        t = s.load_table(ARGS)
        rom = bytearray(0x400000)
        for addr, new in ((0x05E6A9, 0x3F), (0x01E01B, 0x45)):
            o = s.lorom(addr)
            rom[o:o + 3] = bytes((0x00, 0x16, new))
        self.assertEqual(s.call_site_problems(bytes(rom), t), [])
        rom[s.lorom(0x01E01B) + 2] = 0x35                                   # 원래 번호로 되돌아감
        self.assertEqual(len(s.call_site_problems(bytes(rom), t)), 1)

    # 패치 전 뱅크 01 의 E000~E03F: 효과음 BRK(01:E01B) 앞뒤를 잇는 코드 바이트
    CODE = bytes(range(0x80, 0xC0))
    CODE = CODE[:0x1B] + bytes((0x00, 0x19, 0x35, 0x01)) + CODE[0x1F:]

    @classmethod
    def door_bank_base(cls):
        """패치 전 롬(원본 DQ5 꼴): 01:E000 에 CODE."""
        base = bytearray(0x180000)
        base[s.lorom(0x01E000):s.lorom(0x01E000) + len(cls.CODE)] = cls.CODE
        return bytes(base)

    @classmethod
    def door_bank_rom(cls, bank=0x3B, back=0x01):
        """문 표를 3B 에 늘린 꼴: 여섯 입구 → 22:FF30 의 스텁(PHP PHB PEA $BBBB PLB PLB JML back:입구+4).
        뱅크 3B 의 E000 은 --sfx-call 로 바꾸기 전에 복사한 CODE."""
        rom = bytearray(0x400000)
        rom[s.lorom(0x01E000):s.lorom(0x01E000) + len(cls.CODE)] = cls.CODE
        rom[s.lorom(0x3BE000):s.lorom(0x3BE000) + len(cls.CODE)] = cls.CODE
        for k, entry in enumerate(s.DOOR_ENTRIES):
            stub = 0x22FF30 + k * 11
            o = s.lorom(entry)
            rom[o:o + 4] = bytes((0x5C, *stub.to_bytes(3, 'little')))
            o = s.lorom(stub)
            rom[o:o + 11] = bytes((0x08, 0x8B, 0xF4, bank, bank, 0xAB, 0xAB, 0x5C,
                                   *(entry + 4 & 0xFFFF).to_bytes(2, 'little'), back))
        for addr, new in ((0x05E6A9, 0x3F), (0x01E01B, 0x45)):
            o = s.lorom(addr)
            rom[o:o + 3] = bytes((0x00, 0x19, new))
        return rom

    def test_leftover_in_door_copy_allowed(self):
        t = s.load_table(ARGS)
        rom = self.door_bank_rom()
        self.assertEqual(s.door_copy_bank(bytes(rom)), 0x3B)
        self.assertEqual(s.leftover_sites(bytes(rom), t), ['3BE01B 35-01'])
        self.assertEqual(s.leftover_problems(bytes(rom), t, self.door_bank_base()), [])

    def test_leftover_copy_with_other_bytes_fails(self):
        # 주소 쌍이 --sfx-call 자리와 맞아도, 둘레가 패치 전 뱅크 01 과 다르면 사본이 아닌 3B 코드다
        t = s.load_table(ARGS)
        for at in (0x3BE01B - 1, 0x3BE01B - s.COPY_WINDOW, 0x3BE01B + 4 + s.COPY_WINDOW - 1):
            rom = self.door_bank_rom()
            rom[s.lorom(at)] ^= 0xFF
            self.assertEqual(s.leftover_problems(bytes(rom), t, self.door_bank_base()),
                             ['3BE01B 35-01: 대응표대로 바뀌지 않은 자리'], f'{at:06X}')
        # 창 밖의 바이트는 보지 않는다
        rom = self.door_bank_rom()
        rom[s.lorom(0x3BE01B - s.COPY_WINDOW - 1)] ^= 0xFF
        self.assertEqual(s.leftover_problems(bytes(rom), t, self.door_bank_base()), [])

    def test_leftover_elsewhere_fails(self):
        t = s.load_table(ARGS)
        rom = self.door_bank_rom()
        rom[s.lorom(0x05A000):s.lorom(0x05A000) + 4] = bytes((0x00, 0x19, 0x35, 0x01))   # 대응표가 모르는 자리
        rom[s.lorom(0x3BE119):s.lorom(0x3BE119) + 4] = bytes((0x00, 0x19, 0x35, 0x01))   # 01:E119 는 --sfx-call 이 아님
        self.assertEqual(s.leftover_problems(bytes(rom), t, self.door_bank_base()),
                         ['05A000 35-01: 대응표대로 바뀌지 않은 자리', '3BE119 35-01: 대응표대로 바뀌지 않은 자리'])

    def test_leftover_in_copy_fails_when_copy_runs(self):
        t = s.load_table(ARGS)
        base = self.door_bank_base()
        # 스텁이 복사본 뱅크로 뛰면 사본 코드가 돌아 원래 번호가 울린다
        self.assertIsNone(s.door_copy_bank(bytes(self.door_bank_rom(back=0x3B))))
        self.assertEqual(s.leftover_problems(bytes(self.door_bank_rom(back=0x3B)), t, base),
                         ['3BE01B 35-01: 대응표대로 바뀌지 않은 자리'])
        # 문 표를 늘리지 않은 롬(입구가 원래 PHP PHB PHK PLB)에는 복사 뱅크가 없다
        rom = self.door_bank_rom()
        for entry in s.DOOR_ENTRIES:
            rom[s.lorom(entry):s.lorom(entry) + 4] = bytes((0x08, 0x8B, 0x4B, 0xAB))
        self.assertIsNone(s.door_copy_bank(bytes(rom)))
        self.assertEqual(len(s.leftover_problems(bytes(rom), t, base)), 1)

    def test_door_bank_jumps(self):
        rom = self.door_bank_rom()
        base = bytearray(self.door_bank_base())
        rom[s.lorom(0x0A8000):s.lorom(0x0A8000) + 4] = bytes((0x22, 0x1B, 0xE0, 0x3B))   # JSL 3B:E01B
        rom[s.lorom(0x0A9000):s.lorom(0x0A9000) + 4] = bytes((0x5C, 0x00, 0x90, 0xBB))   # JML BB:9000(거울)
        rom[s.lorom(0x0AA000):s.lorom(0x0AA000) + 4] = bytes((0x22, 0x00, 0x40, 0x3B))   # 3B:4000 은 롬이 아님
        rom[s.lorom(0x0AB000):s.lorom(0x0AB000) + 4] = bytes((0x22, 0x00, 0x90, 0x3C))   # 다른 뱅크
        base[s.lorom(0x0AC000):s.lorom(0x0AC000) + 4] = bytes((0x22, 0x00, 0x80, 0x3B))  # 원본 DQ5 에 있던 자료
        rom[s.lorom(0x0AC000):s.lorom(0x0AC000) + 4] = bytes((0x22, 0x00, 0x80, 0x3B))
        self.assertEqual(s.door_bank_jumps(bytes(rom), 0x3B, bytes(base)), [(0x0A8000, 0x3BE01B), (0x0A9000, 0xBB9000)])

    def test_weapon_table(self):
        t = s.load_table(ARGS)
        rom = bytearray(0x400000)
        rom[s.lorom(s.WEAPON_SEQ_TABLE):s.lorom(s.WEAPON_SEQ_TABLE) + 0x100] = b'\xff' * 0x100
        rom[s.lorom(s.WEAPON_SEQ_TABLE)] = 0x43
        rom[s.lorom(s.WEAPON_BRANCH_TABLE)] = 0x01
        self.assertEqual(s.weapon_table_problems(bytes(rom), t), [])
        rom[s.lorom(s.WEAPON_BRANCH_TABLE)] = 0x02
        self.assertEqual(len(s.weapon_table_problems(bytes(rom), t)), 1)

    def test_hook_patches(self):
        rom = bytearray(0x400000)
        for site in s.ENTRY_SITES:
            rom[s.lorom(site):s.lorom(site) + 5] = s.ENTRY_BYTES
        patches = dict(s.hook_patches(bytes(rom)))
        self.assertEqual(patches[s.lorom(0x24FFCC)], bytes.fromhex('2200FF7DEA'))
        self.assertEqual(patches[s.lorom(s.HOOK)][-1], 0x6B)                # RTL
        rom[s.lorom(0x34FFCC)] = 0xEA
        with self.assertRaises(ValueError):
            s.hook_patches(bytes(rom))

    def test_critical_patch_narrows_roll_only(self):
        # 난수 범위 LDA #$20 의 값만 1 로: (난수8 × 1) >> 8 = 0 이 회심 분기(CMP #$00 / BEQ)를 탄다
        rom = bytearray(0x400000)
        o = s.lorom(s.CRITICAL_SITE)
        rom[o:o + len(s.CRITICAL_BYTES)] = s.CRITICAL_BYTES
        self.assertEqual(s.critical_patch(bytes(rom)), [(0x1046B3, b'\x01')])
        rom[o + 2] = 0xEA
        with self.assertRaises(ValueError):
            s.critical_patch(bytes(rom))

    def test_critical_scene_uses_patch_not_seed(self):
        t = s.load_table(s.ARGS.read_text())
        crit = [x for x in s.scenes(t) if x.critical]
        self.assertEqual([x.name for x in crit], ['battle-critical'])
        self.assertEqual(crit[0].seed, 0)
        rom = bytearray(0x400000)
        for site in s.ENTRY_SITES:
            rom[s.lorom(site):s.lorom(site) + 5] = s.ENTRY_BYTES
        o = s.lorom(s.CRITICAL_SITE)
        rom[o:o + len(s.CRITICAL_BYTES)] = s.CRITICAL_BYTES
        self.assertEqual(s.scene_rom(bytes(rom), crit[0])[o + 1], 0x01)


class QueueTest(unittest.TestCase):
    def test_call_sites(self):
        rom = bytearray(0x10000)
        rom[0x8000 + 0x10:0x8000 + 0x14] = bytes((0x00, 0x16, 0x40, 0x03))
        rom[0x8000 + 0x20:0x8000 + 0x24] = bytes((0xA9, 0x40, 0xA2, 0x03))
        self.assertEqual(s.call_sites(bytes(rom), 0x40, 0x03), [0x018010, 0x018020])

    def test_drain_reads_matching_inverse_only(self):
        shadow, inverse = [0xFF] * 16, [0xFF] * 16
        args, xs = list(range(16)), list(range(0x20, 0x30))
        shadow[3], inverse[3] = 0x0C, 0xF3                                  # 훅이 쓴 칸
        shadow[1], inverse[1] = 0x00, 0x00                                  # 게임이 덮은 칸(보수가 맞지 않음)
        shadow[15], inverse[15] = 0x01, 0xFE
        self.assertEqual(s.drain(14, shadow, inverse, args, xs), [(0x01, 15, 0x2F), (0x0C, 3, 0x23)])

    def test_match_seq_in_order_and_wildcard(self):
        ev = [(10, 0x0C, 0x33, 0x00), (20, 0x01, 0x1D, 0x75), (30, 0x0C, 0x33, 0x00)]
        self.assertEqual(s.match_seq(ev, [(0x0C, 0x33, 0x00), (0x0C, 0x33, 0x00)]), [10, 30])
        self.assertEqual(s.match_seq(ev, [(0x01, 0x1D, None)]), [20])
        self.assertEqual(s.match_seq(ev, [(0x01, 0x1D, None), (0x0C, 0x40, 0x01), (0x0C, 0x33, 0x00)]), [20, None, None])

    def test_assign_key_ons_one_per_entry(self):
        # 항목 둘(프레임 0, 3)이 목소리 7 의 같은 울림을 나눠 갖지 못한다: 둘째 항목은 그 뒤 울림이 없으면 None
        frames = list(range(10))
        envx = [(n, (0,) * 7 + (e,)) for n, e in zip(frames, [0, 0, 0x7F, 0x60, 0x40, 0x20, 0, 0, 0, 0])]
        ev = [(0, s.SFX, 0x33, 0x00), (3, s.SFX, 0x33, 0x00)]
        got = s.assign_key_ons(ev, [0, 3], frames, envx, {(2, 7): 'nds'})
        self.assertEqual(got[0], (2, 7, [(7, 'nds')]))
        self.assertIsNone(got[1])

    def test_window_stops_at_next_entry(self):
        frames = list(range(10))
        envx = [(n, (0,) * 7 + (e,)) for n, e in zip(frames, [0, 0, 0, 0, 0, 0x7F, 0, 0, 0, 0])]
        ev = [(0, s.SFX, 0x33, 0x00), (3, s.SFX, 0x34, 0x02)]
        got = s.assign_key_ons(ev, [0, 3], frames, envx, {})
        self.assertIsNone(got[0])                                           # 울림은 다음 항목(3) 뒤
        self.assertEqual(got[1][0], 5)

    def test_earliest_voice_and_both_sources(self):
        # 대화 글자는 목소리 6 에서 먼저 울리고 7 은 앞 효과음 꼬리: 이른 쪽을 짝짓고 바탕은 둘 다 돌려준다
        frames = list(range(6))
        envx = [(n, (0,) * 6 + (a, b)) for n, a, b in zip(frames, [0, 0x7F, 0, 0, 0, 0], [0, 0, 0, 0x7F, 0, 0])]
        got = s.assign_key_ons([(0, s.SFX, 1, 1)], [0], frames, envx, {(1, 6): 'dq5 1F', (3, 7): 'nds'})
        self.assertEqual(got[0], (1, 6, [(6, 'dq5 1F'), (7, 'nds')]))

    def test_song_on_needs_switch_and_rise(self):
        songs = [0x06] * 3 + [0x1D] * 5
        envx = [(n, (e,) + (0,) * 7) for n, e in enumerate([0x7F, 0x60, 0x40, 0x30, 0x20, 0x7F, 0x60, 0x40])]
        self.assertEqual(s.song_on(songs, envx, 0, 0x1D), (3, 5))           # 바뀐 프레임 3, 그 뒤 첫 상승 5
        flat = [(n, (0x40,) + (0,) * 7) for n in range(8)]
        self.assertEqual(s.song_on(songs, flat, 0, 0x1D), (3, None))        # 울리던 소리가 이어지기만 하면 아님

    def test_source_ok(self):
        self.assertTrue(s.source_ok('dq5 1F', 'dq5'))
        self.assertTrue(s.source_ok('dq5 1F/20', 'dq5'))
        self.assertFalse(s.source_ok('nds', 'dq5'))
        self.assertFalse(s.source_ok('dq5 1F', 'nds'))
        self.assertTrue(s.source_ok('noise', 'noise'))
        self.assertFalse(s.source_ok(None, 'noise'))
        self.assertTrue(s.source_ok('noise', 'dq5'))                        # DQ5 효과음도 잡음을 씀
        self.assertTrue(s.source_ok('noise', 'not-dq5'))
        self.assertFalse(s.source_ok('dq5 20', 'not-dq5'))

    def test_key_on(self):
        env = [0, 0, 0, 0x7F, 0x60, 0x30, 0, 0]
        self.assertEqual(s.key_on(env, 1), 3)
        self.assertIsNone(s.key_on([0x7F, 0x60, 0x30, 0x10, 0], 0))        # 줄어들기만 하면 새 울림이 아님
        self.assertIsNone(s.key_on(env, 1, window=1))


class SceneListTest(unittest.TestCase):
    def test_runtime_gaps_are_exactly_known(self):
        # 장면이 맡지 않는 항목은 UNREACHED(롬으로 까닭 확인), RUNTIME_GAPS, --sfx-call 자리(롬 바이트만)뿐
        t = s.load_table(s.ARGS.read_text())
        calls = {f'call {a:06X}' for a in t.calls}
        self.assertEqual(set(s.uncovered(t, s.scenes(t))), s.RUNTIME_GAPS | calls)

    def test_scenes_do_not_claim_call_sites(self):
        t = s.load_table(s.ARGS.read_text())
        self.assertFalse([c for x in s.scenes(t) for c in x.covers if c.startswith('call ')])

    def test_decision_table_matches_build_input(self):
        # 손으로 적은 결정 표와 빌드 입력이 어긋나면(remap·--sfx-call 목표·--sfx NDS 번호) 실패
        t = s.load_table(s.ARGS.read_text())
        self.assertEqual(s.decision_problems(t), [])

    def test_decision_table_catches_wrong_build_input(self):
        t = s.load_table(s.ARGS.read_text())
        t.remap[(0x37, 0x14)] = (0x45, 0x04)
        t.sfx[(0x34, 0x02)] = '999'
        t.calls[0x05E6A9] = (0x35, 0x45)
        t.sfx[(0x37, 0x0B)] = '197'                                         # DQ5 로 고른 회심을 바꿈
        got = ' '.join(s.decision_problems(t))
        for k in ('boss-hit', 'stairs', 'chest', 'critical'):
            self.assertIn(k, got)

    def test_adopted_nds_waves_stay_dq5_numbers(self):
        self.assertEqual(sorted(s.ADOPTED_WAVES), [0x20, 0x21, 0x22])
        t = s.load_table(s.ARGS.read_text())
        t.sfx[(0x36, 0x02)] = '13B'
        t.remap[(0x37, 0x05)] = (0x45, 0x03)
        got = ' '.join(s.decision_problems(t))
        for k in ('chimera', 'boss-attack'):
            self.assertIn(k, got)

    def test_decision_kinds(self):
        for k, (_, _, choice, _, kind) in s.DECISIONS.items():
            self.assertEqual(kind == 'dq5', choice == 'DQ5', k)

    def test_unreached_are_table_entries(self):
        t = s.load_table(s.ARGS.read_text())
        self.assertEqual(set(s.UNREACHED) - set(t.entries()), set())

    def test_names_unique_and_wants_routed(self):
        t = s.load_table(s.ARGS.read_text())
        scenes = s.scenes(t)
        self.assertEqual(len({x.name for x in scenes}), len(scenes))
        by = {x.name: x for x in scenes}
        self.assertIn((s.SFX, 0x3F, 0x00, 'nds'), by['chest'].want)
        self.assertIn((s.SFX, 0x45, 0x03, 'noise'), by['battle-boss'].want)
        self.assertEqual(len([x for x in scenes if x.name.startswith('weapon-')]), len(t.weapons))


if __name__ == '__main__':
    unittest.main()
