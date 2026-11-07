"""2장 엔돌 무술 대회(dq4ch2endor)."""

import itertools
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4ch1event  # noqa: E402
import dq4ch2battle  # noqa: E402
import dq4ch2event as ev  # noqa: E402
import dq4ch2endor as en  # noqa: E402
import dq4ch2slots as slots  # noqa: E402
from dq4chapter1 import lorom  # noqa: E402
from w65816 import Cpu  # noqa: E402

DQ4 = ROOT / 'rom' / 'dq4.nes'
DQ5 = ROOT / 'rom' / 'dq5.sfc'
SEEN_GROUP = 0x0F00            # 전투 흉내가 받은 무리를 적어 두는 WRAM 자리(시험용)


def context(message=0x1000, talk=0x0B00):
    return next(c for c in ev.contexts(message, talk) if c.module is en)


def w(a):
    return a & 0xFFFF


class Machine:
    """사건 네이티브를 빈 롬에 놓고, 그것이 부르는 엔진 루틴은 흉내(RTL)로 바꿔 돌린다."""

    def __init__(self, battle_result=0x00):
        code, self.at = en.native(context())
        rom = bytearray(0x400000)
        start = slots.SLOTS['E4'].code[0]
        rom[lorom(start):lorom(start) + len(code)] = code
        rtl = b'\x6B'
        for r in (en.BATTLE_SONG, en.BATTLE_PREP, en.BATTLE_PREP2, en.BATTLE_AFTER, dq4ch1event.PARTY_OBJECTS):
            rom[lorom(r)] = rtl[0]
        # 전투: 받은 무리를 적고 결과를 A 로
        run = bytes((0x8F, *SEEN_GROUP.to_bytes(2, 'little'), 0x7E, 0xA9, battle_result, 0x6B))
        rom[lorom(en.BATTLE_RUN):lorom(en.BATTLE_RUN) + len(run)] = run
        self.cpu = Cpu(bytes(rom), bytearray(0x20000))
        self.ram = self.cpu.wram

    def call(self, name):
        self.cpu.jsl(self.at[name])

    def party(self, order, count=3):
        for t in en.ORDERS:
            self.ram[w(t):w(t) + 3] = bytes(order)
        for c in en.COUNTS:
            self.ram[w(c)] = count

    def order(self):
        return tuple(tuple(self.ram[w(t):w(t) + 3]) for t in en.ORDERS)

    def counts(self):
        return tuple(self.ram[w(c)] for c in en.COUNTS)

    def flag(self):
        return self.ram[w(en.FLAG_AT)]

    def stage(self):
        return self.ram[w(en.STAGE_AT)]


class ModuleTest(unittest.TestCase):
    def test_registered_with_its_slot(self):
        self.assertIn('dq4ch2endor', ev.EVENTS)
        slot = slots.SLOTS['E4']
        self.assertEqual(context().key, 'E4')
        self.assertTrue({i for i, _ in en.FLAGS} <= set(slot.flags))
        self.assertIn(en.STAGE[0], slot.byte_flags)
        masks = [m for i, m in en.FLAGS if i == en.IDX]
        self.assertEqual(sum(masks), 0xFF)
        self.assertEqual([b['group'] for b in en.BATTLES], list(slot.groups))
        self.assertTrue({m for b in en.BATTLES for m, _ in b['members']} <= set(slot.monsters))
        self.assertEqual(set(en.CALLS), set(slot.battles))

    def test_native_fits_and_does_not_move_with_message_numbers(self):
        code_a, at_a = en.native(context(0x1000))
        code_b, at_b = en.native(context(0x1400))
        self.assertEqual(at_a, at_b)
        start, end = slots.SLOTS['E4'].code
        self.assertEqual(at_a['leave'], start)
        self.assertLessEqual(start + len(code_a), end)
        self.assertEqual(len(code_a), len(code_b))

    def test_call_stubs_reach_the_routines(self):
        stubs = ev.call_stubs()
        _, at = en.native(context())
        self.assertEqual(stubs[1], (at['leave'], b''))
        # 전투 입구는 공용 전투 루틴처럼 뱅크 06 에서 BRK 0E 를 먼저 돈다
        self.assertEqual(stubs[2], (at['fight'], bytes((0x00, 0x0E))))
        self.assertEqual(stubs[3], (at['herb'], b''))
        for k, (a, pre) in stubs.items():
            code = dq4ch2battle.call_stub(a, pre)
            self.assertLessEqual(len(code), dq4ch2battle.STUB_SIZE)
            self.assertEqual(code[-5:], b'\x22' + a.to_bytes(3, 'little') + b'\x60')
        self.assertFalse(set(stubs) & set(ev.battle_stubs()))

    def test_scripts_use_only_the_borrowed_slots_and_encode(self):
        import dq5npcwrite
        ctx = context()
        owned = dict(slots.SLOTS['E4'].scripts)
        self.assertTrue(all(k in owned[en.SCRIPT_LIST] for k, _ in en.SCRIPTS.values()))
        made = en.scripts(ctx)
        self.assertEqual({s['address'] for s in made}, {a for _, a in en.SCRIPTS.values()})
        for s in made:
            code = dq5npcwrite.encode({'format': dq5npcwrite.FORMAT, 'commands': s['commands']})
            self.assertLessEqual(len(code), 255)

    def test_talks(self):
        ctx = context()
        bodies = en.talk_scripts(ctx)
        self.assertEqual(len(bodies), len(en.TALKS))
        self.assertTrue(set(en.TALKS) - {'ring'} <= set(en.MESSAGES))
        ring = bodies[en.TALKS.index('ring')]
        # 대회 앞: 응원 → 일행 빼기(입구 1) → 규칙. 대회 중: 전투(입구 2)
        self.assertEqual(ring[0]['cond'], {"code": "1B", "index": en.IN[0], "mask": en.IN[1]})
        self.assertEqual(ring[0]['else'][1], dq4ch2battle.talk_call(1))
        self.assertEqual(ring[0]['then'][0], dq4ch2battle.talk_call(2))
        self.assertEqual(ring[-1], {"op": "flag-on", "index": ev.ANSWERED[0], "mask": ev.ANSWERED[1]})

    def test_lists_are_chapter_two_only_and_prefixed(self):
        lists = {m: {"entries": []} for m in (en.ARENA, en.TOWN, *{m for m, _, _ in en.TOWNSFOLK})}
        for (m, time, fc), _ in en.TOWNSFOLK.items():
            lists[m]["entries"].append({"time": time, "fields": {"x": en.cell(*fc)[0], "y": en.cell(*fc)[1],
                                                                 "talk": 0}})
        new, over = en.npc_lists(lists, context())
        prefix = slots.SLOTS['E4'].lists
        self.assertTrue(all(n['name'].startswith(prefix) for n in new))
        self.assertEqual({o['list'][4:] for o in over}, {n['name'] for n in new})
        # 엔돌은 3장도 쓰므로 2장 flag(또는 2장에서만 켜지는 우승·사자 flag)가 켜졌을 때만 바꾼다
        for o in over:
            self.assertIn((o['flag'], o['mask']), (ev.CHAPTER2, en.CHAMPION, en.MESSENGER))
        town = [o['list'] for o in over if o['map'] == en.TOWN]
        self.assertEqual(town, [f'new:{en.TOWN_SEEN}', f'new:{en.TOWN_MESSENGER}'])


class PartyTest(unittest.TestCase):
    """일행 빼기(입구 1)와 되돌리기(우승·짐). 일행 기록은 손대지 않고 순서와 수만 바꿨다 되돌린다."""

    def test_leave_and_restore_every_order(self):
        for order in itertools.permutations(range(3)):
            m = Machine()
            m.party(order)
            m.ram[w(en.FLAG_AT)] = en.CHAMPION[1] | en.LOST[1]
            m.ram[w(en.STAGE_AT)] = 3
            record = bytes(range(42 * 3))
            m.ram[w(en.PARTY_AT):w(en.PARTY_AT) + len(record)] = record
            m.call('leave')
            self.assertEqual(m.counts(), (1, 1, 1), order)
            self.assertEqual([o[0] for o in m.order()], [0, 0], order)
            self.assertEqual(m.stage(), 0)
            # LOST 는 지우고 CHAMPION 은 그대로, 위 니블에 순서 첫 둘
            self.assertEqual(m.flag(), en.IN[1] | en.CHAMPION[1] | (order[0] | order[1] << 2) << en.ORDER_SHIFT)
            m.call('champion')
            self.assertEqual(m.order(), (order, order), order)
            self.assertEqual(m.counts(), (3, 3, 3), order)
            self.assertEqual(m.flag(), en.CHAMPION[1], order)
            self.assertEqual(bytes(m.ram[w(en.PARTY_AT):w(en.PARTY_AT) + len(record)]), record)

    def test_restore_without_in_does_nothing(self):
        # 대회 밖에서 되돌리기가 돌아도(저장을 불러온 뒤 따위) 일행을 덮지 않는다
        m = Machine()
        m.party((1, 0, 2), count=2)
        m.ram[w(en.FLAG_AT)] = en.MESSENGER[1]
        m.call('champion')
        self.assertEqual(m.order(), ((1, 0, 2), (1, 0, 2)))
        self.assertEqual(m.counts(), (2, 2, 2))
        self.assertEqual(m.flag(), en.MESSENGER[1])

    def test_won_bout_counts_and_keeps_alena_alone(self):
        for stage in range(en.ROUNDS):
            m = Machine(battle_result=0x00)
            m.party((2, 0, 1))
            m.call('leave')
            m.ram[w(en.STAGE_AT)] = stage
            m.call('fight')
            self.assertEqual(m.ram[SEEN_GROUP], en.GROUP0 + stage)
            self.assertEqual(m.stage(), stage + 1)
            self.assertTrue(m.ram[w(dq4ch2battle.WON_AT)] & dq4ch2battle.BATTLE_WON[1])
            self.assertEqual(m.counts(), (1, 1, 1))
            self.assertTrue(m.flag() & en.IN[1])
            self.assertFalse(m.flag() & en.LOST[1])

    def test_stage_past_the_last_fights_the_last(self):
        m = Machine()
        m.call('leave')
        m.ram[w(en.STAGE_AT)] = 7
        m.call('fight')
        self.assertEqual(m.ram[SEEN_GROUP], en.GROUP0 + en.ROUNDS - 1)

    def test_lost_bout_revives_alena_and_restores_the_party(self):
        m = Machine(battle_result=en.LOSE)
        m.party((2, 0, 1))
        m.ram[w(en.ALENA_MAX_HP):w(en.ALENA_MAX_HP) + 2] = (300).to_bytes(2, 'little')
        m.call('leave')
        m.ram[w(en.STAGE_AT)] = 2
        m.ram[w(dq4ch2battle.WON_AT)] = dq4ch2battle.BATTLE_WON[1]
        m.ram[w(en.ALENA_HP):w(en.ALENA_HP) + 2] = b'\x00\x00'
        m.ram[w(en.ALENA_STATUS)] = 0x05
        m.call('fight')
        self.assertFalse(m.ram[w(dq4ch2battle.WON_AT)] & dq4ch2battle.BATTLE_WON[1])
        self.assertEqual(int.from_bytes(m.ram[w(en.ALENA_HP):w(en.ALENA_HP) + 2], 'little'), 300)
        self.assertEqual(m.ram[w(en.ALENA_STATUS)], 0x85)
        self.assertEqual(m.order(), ((2, 0, 1), (2, 0, 1)))
        self.assertEqual(m.counts(), (3, 3, 3))
        self.assertEqual(m.flag(), en.LOST[1])
        self.assertEqual(m.stage(), 2)          # 침대 장면 뒤 링에서 다시 들어서면 leave 가 0 으로


class HerbTest(unittest.TestCase):
    def herb(self, items, equip, hp, max_hp=100):
        m = Machine()
        m.ram[w(en.ALENA_ITEMS):w(en.ALENA_ITEMS) + en.ITEM_SLOTS] = bytes(items + [0xFF] * (en.ITEM_SLOTS - len(items)))
        m.ram[w(en.ALENA_EQUIP):w(en.ALENA_EQUIP) + 2] = equip.to_bytes(2, 'little')
        m.ram[w(en.ALENA_HP):w(en.ALENA_HP) + 2] = hp.to_bytes(2, 'little')
        m.ram[w(en.ALENA_MAX_HP):w(en.ALENA_MAX_HP) + 2] = max_hp.to_bytes(2, 'little')
        m.call('herb')
        got = list(m.ram[w(en.ALENA_ITEMS):w(en.ALENA_ITEMS) + en.ITEM_SLOTS])
        return ([i for i in got if i != 0xFF], int.from_bytes(m.ram[w(en.ALENA_EQUIP):w(en.ALENA_EQUIP) + 2], 'little'),
                int.from_bytes(m.ram[w(en.ALENA_HP):w(en.ALENA_HP) + 2], 'little'))

    def test_first_herb_goes_and_the_rest_moves_up_with_equip_bits(self):
        robe, claw = ev.SILK_ROBE, 0x10
        # 칸 0 로브(장비) · 1 약초 · 2 발톱(장비) · 3 약초 → 약초 하나가 빠지고 발톱이 칸 1 로
        self.assertEqual(self.herb([robe, en.HERB, claw, en.HERB], 0b0101, 10),
                         ([robe, claw, en.HERB], 0b0011, 10 + en.HERB_HEAL))
        # 칸 0 의 약초: 장비 비트가 모두 한 칸 내려온다
        self.assertEqual(self.herb([en.HERB, en.HERB, robe], 0b100, 10), ([en.HERB, robe], 0b10, 10 + en.HERB_HEAL))

    def test_heal_stops_at_max_and_no_herb_changes_nothing(self):
        self.assertEqual(self.herb([en.HERB], 0, 90), ([], 0, 100))
        self.assertEqual(self.herb([ev.SILK_ROBE], 1, 50), ([ev.SILK_ROBE], 1, 50))

    def test_last_slot_herb(self):
        items = [0x01] * (en.ITEM_SLOTS - 1) + [en.HERB]
        got, equip, _ = self.herb(items, 1 << (en.ITEM_SLOTS - 2), 1)
        self.assertEqual(got, [0x01] * (en.ITEM_SLOTS - 1))
        self.assertEqual(equip, 1 << (en.ITEM_SLOTS - 2))


@unittest.skipUnless(DQ4.exists(), 'rom/dq4.nes 없음')
class FcTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(DQ4.read_bytes())

    def test_townsfolk_say_the_fc_chapter_two_lines(self):
        import dq4npcport
        import dq4talk
        for (m, time, fc), name in en.TOWNSFOLK.items():
            night = time == 'night'
            state = dq4npcport.fc_state(night, None, 2)
            shows = [dq4talk.predict(self.prg, dq4talk.talk_id(rec, night), state)
                     for rec in dq4talk.npc_list(self.prg, 0x04, int(m.split('/')[1], 16), night)
                     if dq4talk.pos(rec, night) == fc]
            self.assertEqual([tuple(s) for s in shows], [en.FC_SHOWS[name]], (m, time, fc))

    def test_opponents_are_fc_special_battles(self):
        import dq4encounter
        bosses = dq4encounter.bosses(self.prg)
        for k, (_, _, fc, _) in enumerate(en.OPPONENTS):
            _, members, _ = bosses[0x07 + k]
            self.assertEqual(members, [(fc, 1)], k)

    def test_monster_doc_uses_monster_actions(self):
        doc = en.monster_doc(self.prg)
        self.assertEqual({d['id'] for d in doc}, {f'{m:02X}' for m in en.MONSTERS})
        if DQ5.exists():
            import dq4ch1walkcheck as wc
            data = DQ5.read_bytes()
            used = {f'{b:02X}' for n in range(236) for b in data[wc.MONSTERS + n * 25 + 17:wc.MONSTERS + n * 25 + 23]}
            for d in doc:
                for k in range(1, 7):
                    self.assertIn(d[f'행동{k}'], used, (d['id'], k))


if __name__ == '__main__':
    unittest.main()
