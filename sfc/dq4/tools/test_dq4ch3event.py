"""3장 넘김과 첫머리: flag, 맡길 칸, 넘김 코드, 주인공 그림 갈래, 2장 끝 갈래, 첫머리 인물·스크립트, 곡 고르기."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dq4ch2event as ch2  # noqa: E402
import dq4ch2slots as slots  # noqa: E402
import dq4ch3event as ev  # noqa: E402
import dq4chapterbox as box  # noqa: E402
import dq4growth  # noqa: E402
import dq4itemport  # noqa: E402

ROOT = HERE.parents[2]
DQ5, DQ4 = ROOT / 'rom' / 'dq5.sfc', ROOT / 'rom' / 'dq4.nes'
HAVE_ROMS = DQ5.exists() and DQ4.exists()
POINTS = {'box2': 0x5F8100, 'box3': 0x5F8180, 'reveal': 0x5F8200, 'end2': 0x5F8300}


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


class FlagTest(unittest.TestCase):
    def test_flags_are_the_reserved_spare_bits_of_2208(self):
        self.assertEqual(slots.CHAPTER3_BITS, (ev.CHAPTER3, ev.OPENING))
        self.assertEqual((ev.CODE_AT, ev.CODE_END), slots.CHAPTER3_CODE)
        used = {ch2.CHAPTER2, ch2.OPENING, ch2.TEMPE_HEARD, ch2.TEMPE_GONE, ch2.TEMPE_ALTAR, slots.BATTLE_WON}
        self.assertEqual({f[1] for f in used if f[0] == 0x78} | {ev.CHAPTER3[1], ev.OPENING[1]}, {1 << b for b in range(8)})
        self.assertFalse({ev.CHAPTER3, ev.OPENING} & used)

    def test_other_tools_name_the_same_bits(self):
        self.assertEqual(dq4growth.CHAPTER3, (0x7E2190 + ev.CHAPTER3[0], ev.CHAPTER3[1]))
        self.assertEqual(box.CHAPTER3.since, (0x7E2190 + ev.OPENING[0], ev.OPENING[1]))
        self.assertEqual(box.CHAPTER3.where, tuple(int(v, 16) for v in ev.HOUSE.split('/')))
        self.assertIn(box.CHAPTER3, box.GAME_SCENES)
        self.assertEqual(box.CHAPTER3.title, box.ENDING2.title)
        self.assertIsNone(box.CHAPTER3.subtitle)

    def test_field_song_picks_the_chapter_three_song(self):
        args = (HERE / 'dq4sound-game.args').read_text(encoding='utf-8').split()
        picks = [args[k + 1] for k, a in enumerate(args) if a == '--song-pick']
        self.assertIn(f'02=0E@{0x7E2190 + ev.CHAPTER3[0]:06X}&{ev.CHAPTER3[1]:02X}', picks)


class StashTest(unittest.TestCase):
    def test_pieces_hold_three_records_and_the_name_inside_the_last_monster_slots(self):
        pieces = ev.stash_pieces()
        self.assertEqual(sum(n for _, _, n in pieces), 42 * ev.STASH_PARTY + 8)
        # 원본은 일행 기록 0~2 와 이름을 빈틈없이 덮는다
        src = sorted((s, s + n) for s, _, n in pieces)
        self.assertEqual(src[0], (ev.NAME_AT, ev.NAME_AT + 8))
        records = src[1:]
        self.assertEqual(records[0][0], ev.PARTY_AT)
        self.assertEqual(records[-1][1], ev.PARTY_AT + 42 * ev.STASH_PARTY)
        self.assertTrue(all(a[1] == b[0] for a, b in zip(records, records[1:])))
        # 맡기는 곳은 칸마다 +1~+25 라 첫 바이트(찬 칸 표시)를 건드리지 않는다
        for _, dst, n in pieces:
            k, off = divmod(dst - ev.MONSTER_SLOTS, ev.MONSTER_SLOT)
            self.assertGreaterEqual(k, ev.STASH_FIRST)
            self.assertLess(k, ev.MONSTER_COUNT)
            self.assertGreaterEqual(off, 1)
            self.assertLessEqual(off + n, ev.MONSTER_SLOT)
        self.assertLess(max(d + n for _, d, n in pieces), 0x7E2AA0)       # 저장 기록 7E:2000~2A9F 안


class TransferTest(unittest.TestCase):
    def test_addresses_do_not_depend_on_the_roms(self):
        code, at = ev.native()
        self.assertEqual(at['record'], ev.CODE_AT)
        self.assertLessEqual(ev.CODE_AT + len(code), ev.CODE_END)
        if HAVE_ROMS:
            code2, at2 = ev.native(DQ5.read_bytes(), DQ4)
            self.assertEqual((len(code2), at2), (len(code), at))
            self.assertEqual(code2[42:], code[42:])

    def test_transfer_writes_torneko_flags_and_moves_to_the_house(self):
        code, at = ev.native()
        t = code[at['transfer'] - ev.CODE_AT:at['pad'] - ev.CODE_AT]
        self.assertEqual(t[:len(box.ENTER)], box.ENTER)
        # 먼저 「제2장 … / 완」 상자(JSL), 그 뒤 넘김
        n = len(box.ENTER)
        self.assertEqual(t[n:n + 4], bytes((0x22, *box.entry_points(box.GAME_SCENES)['done2'].to_bytes(3, 'little'))))
        t = t[:n] + t[n + 4:]
        self.assertEqual(t[-len(box.LEAVE):], box.LEAVE)
        self.assertIn(ch2._mvn(at['record'], ev.PARTY_AT, 42), t)
        self.assertIn(ch2._mvn(at['name'], ev.NAME_AT, 8), t)
        for src, dst, n in ev.stash_pieces():
            self.assertLess(t.index(ch2._mvn(src, dst, n)), t.index(ch2._mvn(at['record'], ev.PARTY_AT, 42)))
        flag = _al(0x7E2190 + 0x78)
        self.assertIn(bytes((0xAF,)) + flag + bytes((0x29, ~ch2.CHAPTER2[1] & 0xFF, 0x8F)) + flag, t)
        self.assertIn(ch2._flag_or(ev.CHAPTER3), t)
        self.assertIn(ch2._flag_or(ev.OPENING), t)
        self.assertIn(bytes((0x22,)) + _al(ev.SONG_STOP), t)
        import dq4fieldtravel
        self.assertIn(dq4fieldtravel.chapter_slot_code(ev.CHURCH_FC, ev.VISITED_FC), t)
        # 금화 0(24비트)
        self.assertIn(bytes((0xA9, 0x00, 0x00, 0x8F)) + _al(ev.GOLD_AT), t)
        self.assertIn(bytes((0xE2, 0x20, 0xA9, 0x00, 0x8F)) + _al(ev.GOLD_AT + 2), t)
        e = at['event'] - ev.CODE_AT
        g, n = (int(v, 16) for v in ev.HOUSE.split('/'))
        skip = ch2.native()[1]['skip_song']
        self.assertEqual(code[e:e + 12], bytes((0xA0, *_al(skip), 0x90, g, n, *ev.START_CELL, 0x01, 0x80, 0xFF)))
        # 옮기는 이벤트는 기록 물음 뒤 transfer_go 가 건다(transfer 는 상태만)
        self.assertNotIn(bytes((0xA9, e + ev.CODE_AT & 0xFF, 0x8D, 0xB3, 0x19)), t)
        go = code[at['transfer_go'] - ev.CODE_AT:at['chapter_save'] - ev.CODE_AT]
        self.assertIn(bytes((0xA9, e + ev.CODE_AT & 0xFF, 0x8D, 0xB3, 0x19)), go)

    def test_pad_returns_zero_only_while_a_direction_is_held(self):
        code = ev._pad()
        self.assertEqual(code[:3], bytes((0x08, 0xE2, 0x20)))
        self.assertEqual(code[3:9], bytes((0xAF, 0x19, 0x42, 0x00, 0x29, 0x0F)))
        branch = 11 + code[10]                                   # BEQ 눌림
        self.assertEqual(code[branch:], bytes((0xC2, 0x30, 0xA9, 0x00, 0x00, 0x28, 0x6B)))
        self.assertEqual(code[11:branch], bytes((0xC2, 0x30, 0xA9, 0x01, 0x00, 0x28, 0x6B)))

    def test_hero_picture_picks_torneko_in_chapter_three(self):
        code = ch2._hero_picture()
        ch3 = bytes((0xAF,)) + _al(0x7E2190 + ev.CHAPTER3[0]) + bytes((0x29, ev.CHAPTER3[1], 0xF0, 0x03, 0xA9,
                                                                        ev.TORNEKO_PICTURE, 0x6B))
        ch2_ = bytes((0xAF,)) + _al(0x7E2190 + ch2.CHAPTER2[0]) + bytes((0x29, ch2.CHAPTER2[1], 0xF0, 0x03, 0xA9,
                                                                         ch2.ALENA_PICTURE, 0x6B))
        self.assertTrue(code.startswith(ch2_ + ch3))
        self.assertTrue(code.endswith(bytes((0xA9, 0x3A, 0x6B))))


@unittest.skipUnless(HAVE_ROMS, 'rom/dq5.sfc·rom/dq4.nes 가 없음')
class RomTest(unittest.TestCase):
    def test_torneko_starts_with_the_fc_chapter_three_record(self):
        s = ev.start(DQ5.read_bytes(), DQ4)
        hp, mp, st, agi, it, luck, vit = dq4growth.MEASURED[dq4growth.FC_TORNEKO][1][0]
        self.assertEqual((s['hp'], s['mp'], s['agility'], s['stats']), (hp, mp, agi, (st, vit, it, luck)))
        self.assertEqual(s['next'], dq4growth.MEASURED[dq4growth.FC_TORNEKO][1][1])
        # Eぬののふく, おべんとう 는 사건 물건 자리(dq4itemport.BENTO)
        self.assertEqual(s['items'], [(0x42, True), (dq4itemport.BENTO, False)])
        self.assertEqual(s['dropped'], [])
        r = ev.torneko_record(ch2.person_record(DQ5.read_bytes(), 0), s)
        self.assertEqual((r[0x12], r[2], r[0xE], r[0x14:0x16], r[0x16:0x19]),
                         (1, hp, hp, b'\x01\x00', bytes((0x42, dq4itemport.BENTO, 0xFF))))

    def test_opener_script_fits_the_borrowed_one(self):
        import dq5npcwrite
        from dq5map import Rom
        from dq5npc import script_bytes
        rom = Rom(DQ5.read_bytes())
        script = ev.scripts(0x1100, POINTS)[0]
        addr = int(ev.OPENER_SCRIPT.replace(':', ''), 16)
        code = dq5npcwrite.encode({'format': dq5npcwrite.FORMAT, 'commands': script['commands']})
        self.assertLessEqual(len(code), len(script_bytes(rom, addr)))


class ScriptTest(unittest.TestCase):
    def test_opener_runs_box_story_reveal_nene_pad_nene(self):
        m = ev.message_ids(0x1100)
        script = ev.scripts(0x1100, POINTS)[0]
        self.assertEqual(script['address'], ev.OPENER_SCRIPT)
        cmds = script['commands']
        self.assertEqual([c['op'] for c in cmds], ['3F', '37', '21', '37', '21', '05', '21', '10', '11', '40', '16'])
        self.assertEqual(cmds[1]['args'], list(_al(POINTS['box3'])))
        self.assertEqual(cmds[3]['args'], list(_al(POINTS['reveal'])))
        self.assertEqual([cmds[k]['args'] for k in (2, 4, 6)],
                         [[m[k] & 0xFF, m[k] >> 8] for k in ('opening', 'nene_call', 'nene_wake')])
        self.assertEqual(cmds[5]['args'], list(_al(ev.native()[1]['pad'])))
        self.assertEqual(cmds[7]['args'], list(ev.FRESH))
        self.assertEqual(cmds[8]['args'], [ev.OPENING[0], ~ev.OPENING[1] & 0xFF])

    def test_chapter_two_ender_hands_over_only_in_the_chapter_three_build(self):
        import dq4ch2ending as en
        ender = en.SCRIPTS['ender'][1]

        def call(chapter3):
            made = ch2.scripts(0x1000, POINTS, chapter3)
            cmds = next(s['commands'] for s in made if s['address'] == ender)
            return [(c['op'], c['args']) for c in cmds if c['op'] in ('37', '05')][-1]
        self.assertEqual(call(False), ('37', list(_al(POINTS[en.END_SCENE]))))
        # 3장 빌드: 「완」 상자·기록 물음·넘김 흐름을 명령 05 로(A 가 0 이 될 때까지 다시 부름)
        self.assertEqual(call(True), ('05', list(_al(ev.native()[1]['chapter_flow']))))

    def test_messages_number_after_chapter_two(self):
        import dq4chapter1
        first = dq4chapter1.chapter3_message(0xC80)
        self.assertEqual(first, dq4chapter1.chapter2_message(0xC80) + len(ch2.texts(dq4chapter1.chapter2_message(0xC80))))
        # 사건 모듈 메시지는 이 모듈 메시지 바로 뒤에 빈 번호 없이
        self.assertEqual(sorted(ev.texts(first)), list(range(first, first + ev.message_count())))


class ListTest(unittest.TestCase):
    def ported(self):
        def e(x, y, time, interval=0):
            return {"from": {"list": "05:870A", "index": 2}, "time": time,
                    "fields": {"x": x, "y": y, "facing": "down", "talk": 1, "gfx": 0x22, "layer": 0, "interval": interval}}
        return [{"map": ev.HOUSE, "entries": [e(*ev.NENE_CELL, 'day'), e(66, 5, 'day', 15), e(*ev.NENE_CELL, 'night')]},
                {"map": ev.CASTLE, "entries": []}]

    def test_only_the_day_nene_runs_the_opening(self):
        new, over = ev.npc_lists(self.ported())
        (lst,) = new
        self.assertEqual(lst['name'], 'ch3_opening')
        opener = [x for x in lst['entries'] if x['from'] == ev.OPENER_SRC]
        self.assertEqual(len(opener), 1)
        self.assertEqual((opener[0]['time'], opener[0]['fields']['interval']), ('day', 1))
        self.assertEqual(len(lst['entries']), 3)
        import dq4ch2ending as en
        self.assertEqual(over, [
            {"map": ev.HOUSE, "flag": ev.OPENING[0], "when": "on", "mask": ev.OPENING[1], "list": "new:ch3_opening"},
            {"map": ev.CASTLE, "flag": ev.CHAPTER3[0], "when": "on", "mask": ev.CHAPTER3[1],
             "list": f"new:{en.EMPTY_CASTLE}"}])

    def test_lists_without_people_add_nothing(self):
        self.assertEqual(ev.npc_lists([{"map": ev.CASTLE, "entries": []}]), ([], []))


if __name__ == '__main__':
    unittest.main()
