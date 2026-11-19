"""3장 굴과 장 끝(dq4ch3tunnel): FC 굴 인물·걷는 길·계단, 입구 훅·동쪽 끝 판정(w65816 로 돌림), 대화·인물 스크립트,
장 끝 상자 장면."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4ch3event as ev  # noqa: E402
import dq4ch3slots as slots  # noqa: E402
import dq4ch3tunnel as tunnel  # noqa: E402
import dq4chapterbox as box  # noqa: E402

DQ5, DQ4 = ROOT / 'rom' / 'dq5.sfc', ROOT / 'rom' / 'dq4.nes'


def _ctx(points=None):
    return next(c for c in ev.contexts(0x1000, 0x900, points=points) if c.key == 'T')


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def machine(extra=None):
    from w65816 import Cpu
    code, at = tunnel.native(_ctx())
    rom = bytearray(0x300000)
    for addr, data in ((tunnel.native(_ctx())[1]['bump'], code), *(extra or {}).items()):
        rom[lorom(addr):lorom(addr) + len(data)] = data
    return Cpu(bytes(rom), bytearray(0x20000)), at


def _fc():
    from kr_patch.fc import ines
    return ines.prg(DQ4.read_bytes())


class FcTest(unittest.TestCase):
    @unittest.skipUnless(DQ4.exists(), 'FC 롬 없음')
    def test_people_are_the_fc_tunnel_people(self):
        import dq4talk
        prg = _fc()
        got = {}
        for k in (0, 1):
            for r in dq4talk.npc_list(prg, 0x42, k, False, None):
                got[(k, dq4talk.pos(r, False))] = dq4talk.talk_id(r, False)
        want = {(0, tunnel.WORKERS[0]): 0x2E3, (0, tunnel.WORKERS[1]): 0x2E4, (0, tunnel.OLD_MAN): 0x06C,
                (1, tunnel.MIGRANTS[0]): 0x2E8, (1, tunnel.MIGRANTS[1]): 0x2E7, (1, tunnel.OLD_MAN_OPEN): 0x06D,
                (1, tunnel.TRAVELER): 0x06E, (1, tunnel.GUIDE): 0x06F}
        for key, talk in want.items():
            self.assertEqual(got.get(key), talk, key)
        self.assertEqual({m: t for m, t in tunnel.FC_TALKS.items()},
                         {'old_man': 0x06C, 'dig': 0x2E3, 'heave': 0x2E4, 'opened': 0x06D, 'guide': 0x06F})

    @unittest.skipUnless(DQ4.exists(), 'FC 롬 없음')
    def test_walks_are_the_fc_blocks(self):
        import contextlib
        import io
        import dq4npcblock
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            dq4npcblock.cmd_map(_fc(), 0x42, 1)
        goals = [tuple(int(v, 16) for v in g.split(',')) for g in
                 __import__('re').findall(r'목표 \(([0-9A-F]{2},[0-9A-F]{2})\)', text.getvalue())]
        # 나그네는 FC 끝 칸 (1F,02) 계단 대신 그 바로 아래에서 숨는다(계단에는 장 끝 인물이 섬)
        fc_last = tunnel.END_STAIRS
        self.assertEqual(goals, [*tunnel.MIGRANT_PATH, *tunnel.TRAVELER_PATH[:-1], fc_last])
        self.assertEqual(tunnel.TRAVELER_PATH[-1], (fc_last[0], fc_last[1] + 1))

    @unittest.skipUnless(DQ4.exists(), 'FC 롬 없음')
    def test_stairs_and_east_column(self):
        import dq4block
        prg = _fc()
        m = dq4block.Map(prg, 0x42, 1)
        prop = lambda x, y: m.blocks["prop"].get(m.buf[y * m.w + x] & 0x1F, 0)  # noqa: E731
        stairs = prop(0x05, 0x0F)
        self.assertEqual(prop(*tunnel.END_STAIRS), stairs)
        self.assertEqual(tunnel.OPEN_ARRIVAL, (0x0A, 0x1F))
        # 계단 앞 칸은 둘뿐: 왼쪽 (1E,02)·아래 (1F,03). 오른쪽·위는 벽(80)
        x, y = tunnel.END_STAIRS
        self.assertEqual({(fc, prop(*fc)) for fc, _ in tunnel.END_APPROACH}, {((x - 1, y), 0), ((x, y + 1), 0)})
        self.assertEqual((prop(x + 1, y), prop(x, y - 1)), (0x80, 0x80))


class ScriptTest(unittest.TestCase):
    def test_scripts_fit_the_borrowed_records(self):
        import dq5npcwrite
        ctx = _ctx({'end3': 0x5F8C68})
        got = {s['address']: s['commands'] for s in tunnel.scripts(ctx)}
        self.assertEqual(set(got), {a for _, a, _ in tunnel.SCRIPTS.values()})
        for index, address, room in tunnel.SCRIPTS.values():
            code = dq5npcwrite.encode({'format': dq5npcwrite.FORMAT, 'commands': got[address]})
            self.assertLessEqual(len(code), room, address)
        lst, indexes = slots.SLOTS['T'].scripts[0]
        self.assertEqual(lst, tunnel.SCRIPT_LIST)
        self.assertLessEqual({i for i, _, _ in tunnel.SCRIPTS.values()}, set(indexes))

    @unittest.skipUnless(DQ5.exists(), 'DQ5 롬 없음')
    def test_borrowed_records_have_those_scripts(self):
        import dq5npc
        from dq5map import Rom
        rom = Rom(DQ5.read_bytes())
        entries = dq5npc.list_entries(rom, 0x05996C)
        for index, address, room in tunnel.SCRIPTS.values():
            a = int(address.replace(':', ''), 16)
            e, _ = entries[index]
            self.assertIn(a, (dq5npc.script_address(rom, e, False), dq5npc.script_address(rom, e, True)), address)
            self.assertEqual(rom.u8(a), room, address)

    def test_ender_calls_dark_message_song_and_box(self):
        ctx = _ctx({'end3': 0x5F8C68})
        ender = next(s['commands'] for s in tunnel.scripts(ctx) if s['address'] == tunnel.SCRIPTS['ender'][1])
        ops = [c['op'] for c in ender]
        # 계단을 막고 있어야 하므로 52 로 치우지 않는다
        self.assertEqual(ops, ['28', '05', '3F', '37', '21', '37', '37', '37', '16'])
        at = ctx.at
        self.assertEqual(ender[1]['args'], list(tunnel._al(at['bump'])))
        self.assertEqual([ender[k]['args'] for k in (3, 5, 6, 7)],
                         [list(tunnel._al(at['dark'])), list(tunnel._al(at['ending_song'])),
                          list(tunnel._al(at['handover'])), [0x68, 0x8C, 0x5F]])
        m = ctx.msg['end']
        self.assertEqual(ender[4]['args'], [m & 0xFF, m >> 8])

    def test_walkers_keep_control_pace_like_fc_and_vanish(self):
        ctx = _ctx()
        got = {s['address']: s['commands'] for s in tunnel.scripts(ctx)}
        for name in ('migrant', 'traveler'):
            cmds = got[tunnel.SCRIPTS[name][1]]
            ops = [c['op'] for c in cmds]
            self.assertNotIn('3F', ops)
            self.assertEqual(ops, ['1E', '1D', '02', '05', '14', '01', '52', '16'])
            self.assertEqual(cmds[1]['args'], [tunnel.TILE_FRAMES[name]])
            self.assertEqual(cmds[2]['args'], [tunnel.tiles(name)])
            self.assertEqual(cmds[3]['args'], list(tunnel._al(ctx.at[f'{name}_pace'])))
        self.assertEqual((tunnel.tiles('migrant'), tunnel.tiles('traveler')), (29, 23))

    def test_old_man_talk_follows_fc_06c(self):
        ctx = _ctx()
        bodies = tunnel.talk_scripts(ctx)
        self.assertEqual(len(bodies), len(tunnel.TALKS))
        old = bodies[0][0]
        self.assertEqual(old['cond'], ctx.flag(tunnel.WAITING))
        self.assertEqual(old['then'], [ctx.say('plan')])
        paid = old['else'][0]
        self.assertEqual(paid['cond'], ctx.flag(tunnel.PAID))
        self.assertEqual(paid['then'], [ctx.say('resumed'), ctx.flag_on(tunnel.RESUMED)])
        import dq4ch3endor as endor
        ask, yes = paid['else']
        self.assertEqual(ask, ctx.say('ask'))
        self.assertEqual(yes['else'], [ctx.say('refused')])
        shop, = yes['then']
        self.assertEqual((shop['cond'], shop['else']), (ctx.flag(endor.SHOP), [ctx.say('no_shop')]))
        call, result = shop['then']
        self.assertEqual(call, ctx.call('pay_works'))
        self.assertEqual(result['then'], [ctx.say('paid'), ctx.say('plan'), ctx.flag_on(tunnel.PAID),
                                          ctx.flag_on(tunnel.WAITING)])
        self.assertEqual(result['else'], [ctx.say('short')])
        self.assertEqual(ev.AMOUNTS.index(tunnel.CALLS['pay_works'][1]), ev._param('pay', 60000))

    def test_news_talk_opens_the_tunnel_after_the_shop_visit(self):
        own = next(c for c in ev.contexts(0x1000, 0x900) if c.key == 'T')
        entered, normal = (0x75, 0x01), [{"op": "msg", "id": "123"}]
        body, = tunnel.news_talk(own, entered, normal)
        say = own.say
        self.assertEqual(body['cond'], own.flag(entered))
        self.assertEqual(body['then'], [say('news'), own.when(tunnel.YES_COND, [say('news_yes')], [say('news_no')]),
                                        say('news_farewell'), own.flag_on(tunnel.OPENED)])
        self.assertEqual(body['else'], [own.when(own.flag(tunnel.RESUMED), [say('no_news')], normal)])
        # 다른 모듈의 Context 로 불러도 이 모듈의 메시지 번호
        for other in ev.contexts(0x1000, 0x900):
            self.assertEqual(tunnel._own(other).msg, own.msg, other.key)

    def test_notice_comes_in_endor_40_01_after_the_works_resume(self):
        import dq4ch3endor as endor
        ctx = _ctx()
        cmds = next(s['commands'] for s in tunnel.scripts(ctx) if s['address'] == tunnel.SCRIPTS['notice'][1])
        self.assertEqual([c['op'] for c in cmds], ['28', '52', '06', '10', '16'])
        self.assertEqual((cmds[2]['args'], cmds[2]['target'], cmds[4]['label']),
                         ([0x80 | tunnel.RESUMED[0], tunnel.RESUMED[1]], 'end', 'end'))
        self.assertEqual(cmds[3]['args'], list(endor.NOTICE))
        # 엔돌 네네의 대화가 이 갈래로 감싸여 있다
        self.assertFalse(hasattr(endor, 'OPENED'))

    def test_flags_are_the_slot(self):
        for idx, _ in tunnel.FLAGS:
            self.assertIn(idx, slots.SLOTS['T'].flags)
        self.assertIn(tunnel.OPEN, tunnel.FLAGS)


class RunTest(unittest.TestCase):
    def enter_case(self, group, number, flag):
        marks = {tunnel.ENTER_NEXT: bytes((0xA9, 0xBB, 0x6B)), tunnel.ENTER_28: bytes((0xA9, 0xAA, 0x6B))}
        cpu, at = machine(marks)
        w = cpu.wram
        w[0xBC], w[0xBD], w[0xC1], w[0xC2] = group, number, 0x0A, 0x17
        w[0x2190 + tunnel.OPEN[0]] = tunnel.OPEN[1] if flag else 0
        cpu.p = 0x30
        cpu.a = group
        cpu.jsl(at['enter'], max_steps=200)
        return cpu.a & 0xFF, w[0xBD], w[0xC1], w[0xC2]

    def test_open_tunnel_enters_the_east_stairs(self):
        x, y = tunnel.OPEN_ARRIVAL
        self.assertEqual(self.enter_case(0x47, 0, True), (0xBB, 1, x, y))
        self.assertEqual(self.enter_case(0x47, 0, False), (0xBB, 0, 0x0A, 0x17))
        self.assertEqual(self.enter_case(0x47, 1, True), (0xBB, 1, 0x0A, 0x17))
        self.assertEqual(self.enter_case(0x28, 0, True), (0xAA, 0, 0x0A, 0x17))
        self.assertEqual(self.enter_case(0x3E, 0, True), (0xBB, 0, 0x0A, 0x17))

    def bump(self, x, y, pad):
        cpu, at = machine()
        cpu.wram[0x3020], cpu.wram[0x3080] = x, y
        read = cpu.read
        cpu.read = lambda a: pad if a == 0x004219 else read(a)     # 자동 조이패드 읽기 결과(위 바이트)
        cpu.jsl(at['bump'], max_steps=300)
        return cpu.a & 0xFFFF

    def test_handover_clears_what_chapter3_leaves(self):
        """FC 3장 끝 뒤(실측): 금화 100, 가방·맡긴 돈 비움. 3장 칸 43~49 와 3장 flag 도 끈다. 그 밖은 건드리지 않는다."""
        import dq4ch2event as ch2
        import dq4ch3event as ch3
        import dq4ch3slots as slots
        cpu, at = machine()
        w = cpu.wram
        w[0x2000:0x2A00] = bytes([0x55]) * 0xA00
        flag = 0x2190 + ch3.CHAPTER3[0]
        w[flag] = 0xFF
        cpu.p = 0x30
        cpu.jsl(at['handover'], max_steps=2000)
        lo, hi = (a & 0xFFFF for a in slots.CHAPTER_END_CLEAR)
        bank = ch2.BANK_ITEMS_AT & 0xFFFF
        self.assertEqual(bytes(w[lo:hi]), bytes(hi - lo))
        self.assertEqual(bytes(w[bank:bank + ch2.BANK_ITEMS]), bytes(ch2.BANK_ITEMS))
        self.assertEqual((w[0x203A], w[0x203B]), (0, 0))
        self.assertEqual(int.from_bytes(w[0x2019:0x201C], 'little'), tunnel.NEXT_GOLD)
        self.assertEqual(w[flag], 0xFF ^ ch3.CHAPTER3[1])
        self.assertEqual((w[lo - 1], w[hi], w[bank - 1], w[bank + ch2.BANK_ITEMS], w[0x2018], w[0x203C]),
                         (0x55,) * 6)

    def test_bump_needs_the_front_cell_and_the_key_toward_the_stairs(self):
        right, up, down = 0x01, 0x08, 0x04
        self.assertEqual(self.bump(60, 5, right), 0)
        self.assertEqual(self.bump(61, 6, right), 0)
        self.assertEqual(self.bump(62, 7, up), 0)
        self.assertEqual(self.bump(63, 8, up | right), 0)
        self.assertEqual(self.bump(60, 5, 0), 1)
        self.assertEqual(self.bump(60, 5, up), 1)
        self.assertEqual(self.bump(62, 7, right), 1)
        self.assertEqual(self.bump(62, 7, down), 1)
        self.assertEqual(self.bump(58, 5, right), 1)
        self.assertEqual(self.bump(62, 9, up), 1)

    SLOT = 8

    def pace(self, name, npc, hero):
        cpu, at = machine()
        w = cpu.wram
        w[0x0090] = self.SLOT
        w[0x3020 + self.SLOT], w[0x3080 + self.SLOT] = npc
        w[0x3040 + self.SLOT], w[0x30A0 + self.SLOT] = 0x01, 0x02
        w[0x3020], w[0x3080] = hero
        w[0x3560 + self.SLOT] = w[0x35A0 + self.SLOT] = 0xEE
        cpu.p = 0x00
        cpu.jsl(at[f'{name}_pace'], max_steps=3000)
        goal = (w[0x3560 + self.SLOT], w[0x35A0 + self.SLOT], w[0x3580 + self.SLOT], w[0x35C0 + self.SLOT])
        return cpu.a & 0xFFFF, goal, cpu.p

    def test_pace_steps_one_tile_along_the_fc_path(self):
        far = (0x3C, 0x05)
        # 이주민 첫 토막 (17,04)→(12,04): 셀 (46,9) 에서 왼쪽 한 칸
        self.assertEqual(self.pace('migrant', (46, 9), far)[:2], (0, (44, 9, 0x01, 0x02)))
        self.assertEqual(self.pace('migrant', (44, 9), far)[:2], (0, (42, 9, 0x01, 0x02)))
        # 토막 끝 (12,04) 은 다음 토막 (12,04)→(12,06) 의 시작: 아래로
        self.assertEqual(self.pace('migrant', (36, 9), far)[:2], (0, (36, 11, 0x01, 0x02)))
        # 마지막 토막 (05,0C)→(05,0F)
        self.assertEqual(self.pace('migrant', (10, 25), far)[:2], (0, (10, 27, 0x01, 0x02)))
        # 끝 칸 (05,0F): 자리를 건드리지 않음
        self.assertEqual(self.pace('migrant', (10, 31), far)[:2], (0, (0xEE, 0xEE, 0, 0)))
        # 나그네 (0C,07)→(13,07): 오른쪽, 끝 (1F,03) 에서 그대로
        self.assertEqual(self.pace('traveler', (24, 15), far)[:2], (0, (26, 15, 0x01, 0x02)))
        self.assertEqual(self.pace('traveler', (62, 7), (0, 0))[:2], (0, (0xEE, 0xEE, 0, 0)))
        # bit7 이 켜진 자리도 셀로 본다
        self.assertEqual(self.pace('migrant', (46 | 0x80, 9), far)[0], 0)

    def test_pace_waits_while_the_hero_is_ahead_on_the_leg(self):
        # 마지막 토막 (05,0C)→(05,0F) = 셀 x 10, y 25~31. 이주민이 (10,25) 일 때
        npc = (10, 25)
        for hero in ((10, 31), (8, 31), (12, 29), (10, 33), (10, 25)):
            self.assertEqual(self.pace('migrant', npc, hero)[0], 1, hero)
        for hero in ((7, 31), (13, 31), (10, 34), (10, 23), (6, 31)):
            self.assertEqual(self.pace('migrant', npc, hero)[0], 0, hero)
        # 왼쪽으로 가는 토막 (0A,0C)→(05,0C) = 셀 y 25, x 20→10. 이주민이 (16,25) 면 뒤(오른쪽)는 보지 않음
        self.assertEqual(self.pace('migrant', (16, 25), (18, 25))[0], 0)
        self.assertEqual(self.pace('migrant', (16, 25), (8, 25))[0], 1)
        self.assertEqual(self.pace('migrant', (16, 25), (7, 25))[0], 0)

    def test_pace_keeps_p(self):
        for hero in ((0x3C, 0x05), (10, 31)):
            self.assertEqual(self.pace('migrant', (10, 25), hero)[2], 0x00)

    def test_hook_jumps_to_the_routine(self):
        ctx = _ctx()
        (addr, orig, new), = tunnel.hooks(ctx)
        self.assertEqual((addr, orig), (tunnel.ENTER_SITE, tunnel.ENTER_ORIG))
        self.assertEqual(new, bytes((0x5C, *tunnel._al(ctx.at['enter']))))
        code, _ = tunnel.native(ctx)
        start, end = slots.SLOTS['T'].code
        self.assertLessEqual(start + len(code), end)

    @unittest.skipUnless(DQ5.exists(), 'DQ5 롬 없음')
    def test_site_holds_the_original_bytes(self):
        data = DQ5.read_bytes()
        self.assertEqual(data[lorom(tunnel.ENTER_SITE):lorom(tunnel.ENTER_SITE) + 4], tunnel.ENTER_ORIG)
        # BNE 의 거리 18 이 ENTER_NEXT
        self.assertEqual(tunnel.ENTER_SITE + 4 + tunnel.ENTER_ORIG[3], tunnel.ENTER_NEXT)
        self.assertEqual(tunnel.ENTER_SITE + 4, tunnel.ENTER_28)

    def test_ending_song_plays_the_third_chapter_ending(self):
        song = tunnel._ending_song()
        self.assertIn(bytes((0xA9, tunnel.ENDING_SONG, 0x22, *tunnel._al(tunnel.SONG_PLAY))), song)
        self.assertIn(bytes((0x22, *tunnel._al(tunnel.SONG_STOP))), song)
        self.assertIn(bytes((0xAD, 0x8B, 0x1D, 0xC9, tunnel.ENDING_SONG)), song)
        # 곡이 울기 시작하면 곧 돌아온다. FC 징글 동안(415프레임)은 끝 상자가 먼저 부르는 「완」 상자가 뜬다
        self.assertNotIn(bytes((0x00, 0x09)), song[song.rindex(bytes((0xCA,))):])
        self.assertEqual((box.ENDING3.before, box.DONE3.hold, box.DONE3.subtitle), ('done3', 415, '완'))


class SceneTest(unittest.TestCase):
    def test_ending3_is_the_last_scene_with_the_adopted_title(self):
        self.assertIs(box.GAME_SCENES[box.GAME_SCENES.index(box.DONE1) - 1], box.ENDING3)
        self.assertEqual(box.ENDING3.name, tunnel.END_SCENE)
        self.assertEqual(box.ENDING3.subtitle, box.ENDING.subtitle)
        adopt = (ROOT / 'nds' / 'dq4' / 'tables' / 'adopt.tsv').read_text(encoding='utf-8')
        adopted = next(line.split('\t')[3] for line in adopt.splitlines() if '第四章' in line)
        self.assertEqual(box.ENDING3.title.split(), adopted.replace('４', '4').split())

    def test_earlier_boxes_keep_their_addresses(self):
        before = box.entry_points(box.GAME_SCENES[:-1])
        after = box.entry_points(box.GAME_SCENES)
        for scene in box.GAME_SCENES[:-1]:
            self.assertEqual(after[scene.name], before[scene.name], scene.name)


if __name__ == '__main__':
    unittest.main()
