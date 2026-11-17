"""3장 엔돌(dq4ch3endor): 맵·사람 칸(FC 3장 목록), 다른 모듈 flag, 출구 훅 잇기, 네이티브(w65816 로 돌림), 상자 보상."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4ch2event as ch2  # noqa: E402
import dq4ch3endor as endor  # noqa: E402
import dq4ch3event as ev  # noqa: E402
import dq4ch3safe as safe  # noqa: E402
import dq4itemport  # noqa: E402

DQ5, DQ4 = ROOT / 'rom' / 'dq5.sfc', ROOT / 'rom' / 'dq4.nes'


def _ctx(key='E'):
    return next(c for c in ev.contexts(0x1000, 0x900) if c.key == key)


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def machine(extra=None):
    """(w65816.Cpu, 이 모듈 네이티브 주소): 롬은 이 모듈·금고 모듈 코드와 extra({주소: 바이트}), WRAM 은 0."""
    from w65816 import Cpu
    rom = bytearray(0x300000)
    for key in ('S', 'E'):
        ctx = _ctx(key)
        code, at = ctx.module.native(ctx)
        rom[lorom(ctx.code_at):lorom(ctx.code_at) + len(code)] = code
    for addr, data in (extra or {}).items():
        rom[lorom(addr):lorom(addr) + len(data)] = data
    return Cpu(bytes(rom), bytearray(0x20000)), at


def _fc_people(group, number, night):
    """FC 3장 목록({(FC 칸): 대화 번호}): $615A = 2, $6282 = C0(장 끝 flag 가 켜져야 엔돌이 3장 목록을 고름)."""
    import dq4talk
    from kr_patch.fc import ines
    prg = ines.prg(DQ4.read_bytes())
    ram = bytearray(0x8000)
    ram[0x615A], ram[0x6282], ram[0x62ED] = 2, 0xC0, 0x80 if night else 0
    return {dq4talk.pos(r, night): dq4talk.talk_id(r, night)
            for r in dq4talk.npc_list(prg, group, number, night, ram=ram)}


class PlaceTest(unittest.TestCase):
    @unittest.skipUnless(DQ4.exists(), 'FC 롬 없음')
    def test_maps_are_the_placed_fc_maps(self):
        from kr_patch.fc import ines
        from dq4groupbuild import placement
        place = placement(ines.prg(DQ4.read_bytes()))
        for k, name in enumerate((endor.CAVE_ENTRY, endor.CAVE_WET, endor.CAVE_DRY, endor.CAVE_LOW_WET,
                                  endor.CAVE_LOW_DRY, endor.STATUE_ROOM)):
            self.assertEqual(place[0x40, k], (endor.CAVE_GROUP, endor._map(name)), name)
        for name in (endor.TOWN, endor.CASTLE_HALL, endor.THRONE, endor.SHOP_UP, endor.COLLECTOR):
            self.assertEqual(place[0x04, endor._map(name)], (0x40, endor._map(name)), name)

    @unittest.skipUnless(DQ4.exists(), 'FC 롬 없음')
    def test_people_stand_where_the_fc_chapter_three_lists_put_them(self):
        want = {endor.KING: 0x072, endor.DELIVER: 0x03F, endor.GUIDE: 0x03E,
                **{p: 0x04D for p in endor.SELLER}, **{p: 0x08B for p in endor.SON}, **{p: 0x075 for p in endor.NENE},
                **{p: 0x04C for p in endor.COLLECTORS}}
        for (mp, time, fc), talk in want.items():
            people = _fc_people(0x04, endor._map(mp), time == 'night')
            self.assertEqual(people.get(fc), talk, f'{mp} {time} {fc}')

    @unittest.skipUnless(DQ4.exists(), 'FC 롬 없음')
    def test_button_cell_and_chests(self):
        from kr_patch.fc import ines
        import dq4chest
        prg = ines.prg(DQ4.read_bytes())
        # 단추 전후 맵이 같은 상자 번호를 쓴다(FC 40/01·02, 40/03·04)
        for wet, dry in ((1, 2), (3, 4)):
            self.assertEqual([c[0] for c in dq4chest.chests(prg, 0x40, wet)],
                             [c[0] for c in dq4chest.chests(prg, 0x40, dry)])
        self.assertEqual([(x, y, c) for _, x, y, c, _ in dq4chest.chests(prg, 0x40, 5)], [(6, 4, 0x6D)])
        self.assertEqual(endor.BUTTON_LAND, (endor.CAVE_DRY, (0x22, 0x05)))

    @unittest.skipUnless(DQ4.exists() and DQ5.exists(), '롬 없음')
    def test_the_chest_gives_the_statue(self):
        import dq4chestport
        _, report = dq4chestport.port(DQ5, DQ4)
        row = next(r for r in report if r['map'] == endor.STATUE_ROOM)
        self.assertEqual(row['reward'], dq4itemport.STATUE)

    @unittest.skipUnless(DQ5.exists(), 'DQ5 롬 없음')
    def test_order_items_are_the_dq5_items_of_the_fc_names(self):
        import dq4shopport
        import dq5item
        items = dq4shopport.dq5_items(dq5item.Rom(DQ5.read_bytes()))
        self.assertEqual(items[dq4shopport._fold('はがねのつるぎ')], endor.STEEL_SWORD)
        self.assertEqual(items[dq4shopport._fold('てつのよろい')], endor.IRON_ARMOR)

    def test_other_modules_flags(self):
        if (HERE / 'dq4ch3bonmalmo.py').is_file():
            import dq4ch3bonmalmo as bonmalmo
            self.assertEqual((endor.LETTER1, endor.LETTER2), (bonmalmo.LETTER1, bonmalmo.LETTER2))
        self.assertTrue(all(f[0] in ev.SLOTS['E'].flags for f in endor.FLAGS))


class HookTest(unittest.TestCase):
    def test_exit_hook_takes_over_the_safe_jsl(self):
        ctx = _ctx()
        (site, old, new), *rest = endor.hooks(ctx)
        self.assertEqual([h[0] for h in rest], [endor.merc.PICTURE_TABLE + endor.merc.KINDS[w] for w in endor.merc.WHO] +
                         [endor.merc.AI_AT, endor.merc.STEP_HOOK_AT, endor.shop.LOW_STUBS[0]])
        safe_new = next(n for s, _, n in safe.hooks(_ctx('S')) if s == safe.EXIT_SITE)
        self.assertEqual((site, old), (safe.EXIT_SITE, safe_new))
        self.assertEqual(new, bytes((0x22, *endor._al(ctx.at['exit']))) + safe_new[4:])

    def test_code_fits_the_slot(self):
        ctx = _ctx()
        code, at = endor.native(ctx)
        start, end = ev.SLOTS['E'].code
        self.assertLessEqual(start + len(code), end)


class MercAiTest(unittest.TestCase):
    """로렌스 행동 가중치 = FC AI 레코드 C7 의 칸(ホイミ·ホイミ·ギラ·ラリホー·공격·ホイミ)에 고르는 법 1 의 칸 가중치
    (fc/dq4/docs/dq4-data-format.md 「행동 고르기」)를 같은 행동끼리 합친 것. 고르는 법 2 로 잘못 넣었던 것이 되돌아오지 않게."""
    METHOD1 = (67, 57, 47, 37, 28, 19)
    C7 = ('heal', 'heal', 'gira', 'rariho', 'attack', 'heal')
    # FC 실측(guestai.lua HOOK=10:B165, 로렌스 + 라이안 HP 10/100, 슬라임 HP 고정, 씨앗 여덟)
    FC_HURT = {'heal': 251, 'gira': 80, 'rariho': 43, 'attack': 58}

    def merged(self):
        out = {}
        for act, w in zip(self.C7, self.METHOD1):
            out[act] = out.get(act, 0) + w
        return out

    def test_weights_are_method_one_merged(self):
        m = endor.merc
        got = {'heal': m.HEAL_WEIGHT, **{{m.GIRA: 'gira', m.RARIHO: 'rariho', m.ATTACK: 'attack'}[a]: w
                                         for a, w in m.OTHER_WEIGHTS}}
        self.assertEqual(got, self.merged())
        self.assertEqual(sum(got.values()), 255)

    def test_weights_match_the_fc_sample(self):
        # ラリホー 는 FC 가 잠든 상대에게 칸을 지워 실측이 낮다. 나머지는 4 점 안
        total, want = sum(self.FC_HURT.values()), self.merged()
        for act in ('heal', 'gira', 'attack'):
            self.assertLess(abs(self.FC_HURT[act] / total - want[act] / 255), 0.04, act)


class RunTest(unittest.TestCase):
    """네이티브를 w65816 로 돌린다."""

    def exit_case(self, target, number, button, group=endor.CAVE_GROUP):
        table = 0x2A9000
        cpu, at = machine({0x2AF7D6: bytes((0xB1, 0x84)), table: bytes((0x40 | target, number))})
        w = cpu.wram
        w[0x84], w[0x85], w[0x86] = table & 0xFF, table >> 8 & 0xFF, table >> 16
        w[0x01], w[0xBC], w[0xBD] = target, group, 0x1F
        w[0x2190 + endor.BUTTON[0]] = endor.BUTTON[1] if button else 0
        cpu.dbr, cpu.y = 0x2A, 0
        cpu.jsl(at['exit'], max_steps=4000)
        return w[0xBD], cpu.a & 0xFF

    def test_exit_turns_the_first_stair_into_the_dry_floor_after_the_button(self):
        wet, dry = endor._map(endor.CAVE_WET), endor._map(endor.CAVE_DRY)
        self.assertEqual(self.exit_case(wet, 0, False), (wet, 0))
        self.assertEqual(self.exit_case(wet, 0, True), (dry, 0))
        self.assertEqual(self.exit_case(wet, 1, True), (wet, 1))
        self.assertEqual(self.exit_case(wet, 0, True, group=0x40), (wet, 0))
        # 금고 동굴 갈래는 그대로
        drained = safe.DRAINED
        cpu, at = machine({0x2AF7D6: bytes((0xB1, 0x84)), 0x2A9000: bytes((0x40 | 4, 1))})
        w = cpu.wram
        w[0x84], w[0x85], w[0x86] = 0x00, 0x90, 0x2A
        w[0x01], w[0xBC] = 4, safe.GROUP
        w[0x2190 + drained[0]] = drained[1]
        cpu.dbr, cpu.y = 0x2A, 0
        cpu.jsl(at['exit'], max_steps=4000)
        self.assertEqual((w[0xBD], cpu.a & 0xFF), (5, 2))

    def deliver_case(self, count, items, records=1, arg=0):
        cpu, at = machine()
        w = cpu.wram
        w[ev.ARG & 0xFFFF] = arg
        ctx = _ctx()
        w[0x201D] = records
        for r in range(4):
            base = (ev.PARTY_ITEMS & 0xFFFF) + ev.RECORD * r
            w[base:base + 12] = b'\xFF' * 12
        for r, its in enumerate(items):
            base = (ev.PARTY_ITEMS & 0xFFFF) + ev.RECORD * r
            w[base:base + len(its)] = bytes(its)
        v = ctx.vars_at & 0xFFFF
        w[v + endor.VARS] = count
        cpu.jsl(at['deliver'], max_steps=200000)
        flags = w[0x2190 + endor.IDX2]
        left = [bytes(w[(ev.PARTY_ITEMS & 0xFFFF) + ev.RECORD * r:][:12]).rstrip(b'\xFF') for r in range(len(items))]
        return (w[v + endor.VARS], w[v + endor.GAVE_SWORD], w[v + endor.GAVE_ARMOR],
                {n for n, f in (('s', endor.GAVE_SWORDS), ('a', endor.GAVE_ARMORS), ('full', endor.FULL),
                                ('ls', endor.LEFT_SWORDS), ('la', endor.LEFT_ARMORS)) if flags & f[1]},
                left)

    def test_deliver_takes_up_to_the_order_and_counts_in_nibbles(self):
        s, a = endor.STEEL_SWORD, endor.IRON_ARMOR
        self.assertEqual(self.deliver_case(0, [[0x42, 0xBB]]), (0, 0, 0, {'ls', 'la'}, [bytes((0x42, 0xBB))]))
        self.assertEqual(self.deliver_case(0, [[0x42, s, 0xBB, s, a]]),
                         (0x12, 2, 1, {'s', 'a', 'ls', 'la'}, [bytes((0x42, 0xBB))]))
        self.assertEqual(self.deliver_case(0x66, [[s, s, a, a]]), (0x77, 1, 1, {'s', 'a', 'full'}, [bytes((s, a))]))
        self.assertEqual(self.deliver_case(0x70, [[a]]), (0x70, 0, 0, {'ls'}, [bytes((a,))]))
        # FC 실측: 칼 4·갑옷 1 을 64 에 내면 칼 3 만 받고 하나는 남음, 다 참
        self.assertEqual(self.deliver_case(0x64, [[s, s, s, s, a]]), (0x77, 3, 1, {'s', 'a', 'full'}, [bytes((s,))]))
        # 「아니요」(인자 1): 빼지 않고 남은 종류만
        self.assertEqual(self.deliver_case(0x70, [[s, a]], arg=1), (0x70, 0, 0, {'ls'}, [bytes((s, a))]))
        # 3장에서 물건을 가진 것은 톨네코(기록 0)뿐이라 다른 기록은 보지 않는다
        self.assertEqual(self.deliver_case(0, [[0x42], [s]], records=2)[:3], (0x00, 0, 0))

    def test_deliver_keeps_the_equip_bits_of_the_other_items(self):
        cpu, at = machine()
        w = cpu.wram
        w[0x201D] = 1
        base = ev.PARTY_ITEMS & 0xFFFF
        w[base:base + 12] = bytes((0x42, endor.STEEL_SWORD, 0x10)) + b'\xFF' * 9
        w[(ev.EQUIP & 0xFFFF):(ev.EQUIP & 0xFFFF) + 2] = (0b101).to_bytes(2, 'little')
        cpu.jsl(at['deliver'], max_steps=200000)
        self.assertEqual(bytes(w[base:base + 3]), bytes((0x42, 0x10, 0xFF)))
        self.assertEqual(int.from_bytes(w[(ev.EQUIP & 0xFFFF):(ev.EQUIP & 0xFFFF) + 2], 'little'), 0b11)

    def number_case(self, name, arg, count, gave=(0, 0)):
        cpu, at = machine()
        v = _ctx().vars_at & 0xFFFF
        cpu.wram[v + endor.VARS] = count
        cpu.wram[v + endor.GAVE_SWORD], cpu.wram[v + endor.GAVE_ARMOR] = gave
        cpu.wram[ev.ARG & 0xFFFF] = arg
        cpu.jsl(at[name], max_steps=2000)
        return int.from_bytes(cpu.wram[0xF5:0xF8], 'little')

    def test_numbers_for_the_messages(self):
        self.assertEqual(self.number_case('left', 0, 0x25), 2)
        self.assertEqual(self.number_case('left', 4, 0x25), 5)
        self.assertEqual(self.number_case('show', endor.GAVE_SWORD, 0, (3, 4)), 3)
        self.assertEqual(self.number_case('show', endor.GAVE_ARMOR, 0, (3, 4)), 4)

    def press_case(self, rows, before):
        table = b''.join(bytes(r) for r in rows) + b'\xFF\xFF'
        cpu, at = machine({0x25FAB5: bytes((0x3C,)), 0x25FAC4: bytes((0x00, 0x88)), 0x3C8800: table,
                           0x25FAE9: bytes(0x80 >> k for k in range(8))})
        cpu.wram[0x2210:0x2210 + len(before)] = before
        cpu.jsl(at['press'], max_steps=100000)
        return bytes(cpu.wram[0x2210:0x2210 + len(before)]), cpu.wram[0x2190 + endor.BUTTON[0]] & endor.BUTTON[1]

    def test_press_copies_the_open_chests_to_the_dry_maps(self):
        g = endor.CAVE_GROUP
        rows = [(0x01, 0x00, 3), (g, 3, 4), (g, 4, 4), (g, 5, 5), (g, 6, 5)]
        # 번호: 48/03 = 3~6, 48/04 = 7~10, 48/05 = 11~15, 48/06 = 16~20
        before = bytes((0b00010100, 0b00000010, 0b00000000))    # 3·5 열림, 14 열림(비트 n 은 바이트 n/8 의 80 >> n%8)
        after, button = self.press_case(rows, before)
        self.assertEqual(button, endor.BUTTON[1])
        self.assertEqual(after, bytes((0b00010101, 0b01000010, 0b00010000)))    # 7·9, 19
        # 표에 없는 맵이면 비트를 건드리지 않는다
        self.assertEqual(self.press_case([(0x01, 0x00, 3)], before)[0], before)


class TalkTest(unittest.TestCase):
    def test_talks_scripts_and_lists_encode(self):
        import dq5talkwrite
        ctx = _ctx()
        for k, body in enumerate(endor.talk_scripts(ctx)):
            dq5talkwrite.encode_script(body, f'엔돌 {endor.TALKS[k]}')
        self.assertEqual(len(endor.talk_scripts(ctx)), len(endor.TALKS))
        self.assertEqual([x['address'] for x in endor.scripts(ctx)], [endor.SCRIPTS[k][0] for k in ('button', 'scott',
                                                                                                     'lawrence')])

    def test_absent_are_the_people_before_the_shop(self):
        self.assertEqual(endor.absent(_ctx()), {(m, *endor.cell(*fc), t == 'night')
                                                for m, t, fc in endor.BEFORE_SHOP + endor.BARD_HIDDEN})


if __name__ == '__main__':
    unittest.main()
