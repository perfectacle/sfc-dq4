import random
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'sfc' / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4fieldencounter as m  # noqa: E402

DQ4, DQ5 = ROOT / 'rom' / 'dq4.nes', ROOT / 'rom' / 'dq5.sfc'
# fc/dq4/docs/dq4-chapter3-format.md 「전투 뒤 물건」
DOC_TABLE = [(16, 0x01), (4, 0x02), (2, 0x04), (2, 0x05), (0, 0x06), (4, 0x25), (4, 0x26), (2, 0x27), (0, 0x28),
             (4, 0x3D), (4, 0x3E), (4, 0x46), (4, 0x47), (4, 0x53), (2, 0x54), (4, 0x56)]
ITEMS = [(t, k) for k, (t, _) in enumerate(DOC_TABLE)]
# 지어낸 무리 고르기 표: 구역 78 은 낮·밤 목록이 다르고 구역 35 는 던전(낮·밤 같음)
DAY, NIGHT = ([(1, 25), (2, 25), (5, 23)], [(1, 25), (2, 25)]), ([(1, 25), (4, 50), (9, 23)], [(1, 25), (4, 50)])
DATA = {'monsters': list(range(0x40, 0x4E)), 'codes': 0, 'formations': {}}
PICKS = [(35, 0x42, 8, 0, {'day': NIGHT, 'night': NIGHT}, DATA), (78, 0x16, 8, 0, {'day': DAY, 'night': NIGHT}, DATA)]
TABLES = {k: [0] * 8 for k in ('extra_max', 'extra_p', 'solo_add', 'solo_cnt', 'surprise')}


class ModelTests(unittest.TestCase):
    def test_roll_walks_from_the_start_slot_and_wraps(self):
        table = [(4, k) for k in range(16)]
        self.assertEqual(m.drop_roll(table, 1, 14, [9, 3]), 15)
        self.assertEqual(m.drop_roll(table, 1, 15, [9, 3]), 0)
        self.assertIsNone(m.drop_roll(table, 1, 0, [4] * 16))

    def test_zero_threshold_is_the_level(self):
        table = DOC_TABLE
        self.assertEqual(m.drop_roll(table, 0x28, 4, [0x27]), 4)
        self.assertEqual(m.drop_roll(table, 0x28, 4, [0x28, 0x03]), 5)

    def test_chance_matches_the_doc(self):
        # 레벨 1·10·20 에서 21.8%·27.2%·33.0%
        for level, want in ((1, 0.218), (10, 0.272), (20, 0.330)):
            self.assertAlmostEqual(m.drop_chance(DOC_TABLE, level), want, places=3)

    def test_code_and_sites(self):
        blob, labels = m.ch3_code([78, 35], PICKS, ITEMS, TABLES)
        self.assertLess(len(blob), 0x500)
        self.assertEqual(blob[labels['thresholds'] - m.CH3_CODE_AT:][:16], bytes(t for t, _ in DOC_TABLE))
        zones = blob[labels['zones'] - m.CH3_CODE_AT:labels['thresholds'] - m.CH3_CODE_AT]
        self.assertEqual(zones, bytes((0xB4, 0x06, 0x02, 0x03)))
        # 무리 고르기 표: 구역마다 [구역 × 22][낮 묶음][밤 묶음], 같은 목록은 한 벌(NIGHT 두 목록 + DAY 두 목록)
        at = labels['picks'] - m.CH3_CODE_AT
        row = blob[at:at + 2 + 2 * m.PICK_BLOCK]
        self.assertEqual(row[:4], bytes((0x02, 0x03, 8, 0)))
        self.assertEqual(row[2:2 + m.PICK_BLOCK], row[2 + m.PICK_BLOCK:])
        first = int.from_bytes(row[4:6], 'little') | m.CH3_CODE_AT & 0xFF0000
        self.assertEqual(blob[first - m.CH3_CODE_AT:][:7], bytes((3, 1, 25, 4, 50, 9, 23)))
        # 목록 넷(7·5·7·5) 뒤 구역 자료 둘(몬스터 14·부호 5·편성 주소 2×2) 뒤 표 다섯(8칸씩)
        self.assertEqual(len(blob) - at, 2 * (2 + 2 * m.PICK_BLOCK) + 7 + 5 + 7 + 5 + 2 * 23 + 5 * 8)
        data = int.from_bytes(row[8:10], 'little') - (m.CH3_CODE_AT & 0xFFFF)
        self.assertEqual(blob[data:data + 14], bytes(range(0x40, 0x4E)))
        # 훅 자리는 원래 명령 경계에서 같은 길이로 덮는다
        self.assertEqual(len(m.NIGHT_ORIG), 6)
        self.assertEqual(len(m.PICK_ORIG), 6)
        self.assertEqual(len(m.DROP_ORIG), 7)
        # 25:8966 의 BNE 는 JSL 뒤 두 바이트에서 25:8970 으로 간다
        self.assertEqual(m.DROP_SITE + 4 + 2 + 4, 0x258970)
        # 떠돌이 상인: 이벤트 스크립트는 네이티브 talk 하나(A0 주소) 뒤 끝(FF), 여관에서 깬 뒤 갈래는 4바이트 그대로 JSL
        script = blob[labels['script'] - m.CH3_CODE_AT:][:5]
        self.assertEqual(script, bytes((0xA0, *labels['talk'].to_bytes(3, 'little'), 0xFF)))
        self.assertEqual(len(m.WAKE_ORIG), 4)
        # rand(10) 다음이 0 이면 상인, 대화 번호 02·06 은 특수 기능 도구점·여관(06:DBDB 표의 E01F·E384)
        self.assertEqual(blob[labels['found'] - m.CH3_CODE_AT:][:3], bytes((0xA9, m.MERCHANT_RATE, 0x00)))
        self.assertEqual((m.TALK_SHOP, m.TALK_INN), (0x02, 0x06))

    def test_drop_message_by_battle_species(self):
        # 전투 무리 몬스터 사본(7E:1156~1159)의 FF 아닌 것이 모두 같으면 0B1(BRK 9E B1), 아니면 1A8(BRK 9F A8), 그 뒤 원래의
        # BRK 9E 00 과 25:89C5(RTL). BRK 는 자리에서 가로채 적는다
        import w65816
        import dq4monspecial
        data, labels = m.drop_msg_code()
        import dq4monport
        far = dq4monspecial.far_code(dq4monport.summon_code()[1]['same'])[0]
        self.assertLessEqual(dq4monspecial.CODE_AT + len(far), m.DROP_MSG_AT)   # 앞의 몬스터 행동 코드와 겹치지 않음
        rom = bytearray(0x400000)
        o = (m.DROP_MSG_AT >> 16) * 0x8000 + (m.DROP_MSG_AT & 0x7FFF)
        rom[o:o + len(data)] = data

        class Done(Exception):
            pass
        for species, want in (([0x50, 0xFF, 0xFF, 0xFF], 0x9EB1), ([0x50, 0x50, 0xFF, 0xFF], 0x9EB1),
                              ([0x50, 0x07, 0xFF, 0xFF], 0x9FA8), ([0xFF, 0x07, 0x50, 0xFF], 0x9FA8),
                              ([0xFF, 0xFF, 0x07, 0x07], 0x9EB1)):
            cpu = w65816.Cpu(bytes(rom), bytearray(0x20000))
            cpu.p, cpu.dbr = 0x30, 0x25
            cpu.wram[0x1156:0x115A] = bytes(species)
            shown = []
            for i in range(len(data) - 2):
                if data[i] == 0x00 and data[i + 1] in (0x9E, 0x9F, 0x16):
                    def brk(c, v=data[i + 1] << 8 | data[i + 2], n=4 if data[i + 1] == 0x16 else 3):
                        shown.append(v)
                        c.pc += n
                        return True
                    cpu.hooks[m.DROP_MSG_AT + i] = brk
            cpu.hooks[m.DROP_MSG_NEXT] = lambda c: (_ for _ in ()).throw(Done())   # RTL 로 25:89C5
            with self.assertRaises(Done):
                cpu.jsl(labels['drop_msg'])
            self.assertEqual(shown, [want, 0x9E00], species)

    def test_last_kill_patch(self):
        # 20:A363 의 16바이트(다른 종류를 쓰러뜨리면 후보 FF)를 LDA $46 / STA $1116 과 NOP 로, 떨어뜨림 종류 읽기 둘을 $111C 로
        self.assertEqual(len(m.LAST_KILL), len(m.LAST_KILL_ORIG))
        self.assertEqual(m.LAST_KILL[:5], bytes((0xA5, 0x46, 0x8D, 0x16, 0x11)))
        for _, orig, new in m.DROP_SPECIES:
            self.assertEqual((orig[0], orig[1:], new[0], new[1:]), (new[0], b'\x13\x11', orig[0], b'\x1c\x11'))

    def test_code_has_no_brk_and_stays_in_its_share(self):
        # BRK 처리기는 BRK 가 놓인 뱅크를 DB 로 둔다: 4E 코드에서 부르면 WRAM 대신 롬을 읽는다
        blob, labels = m.ch3_code([32, 33, 78, 35], PICKS, ITEMS, TABLES)
        self.assertLessEqual(m.CH3_CODE_AT + len(blob), m.CH3_CODE_END)
        from kr_patch.sfc.dis65816 import decode
        from kr_patch.sfc.mapper import LoROM
        rom = bytearray(0x400000)
        o = (m.CH3_CODE_AT >> 16 & 0x7F) * 0x8000
        rom[o:o + len(blob)] = blob
        for start, end in (('drop', 'zones'),):
            pc, m8, x8 = labels[start], True, True
            while pc < labels[end]:
                text, n, _, _ = decode(bytes(rom), pc, m8=m8, x8=x8, mapper=LoROM())
                op = blob[pc - m.CH3_CODE_AT]
                self.assertNotEqual(op, 0x00, text)
                if op in (0xC2, 0xE2):
                    v = blob[pc - m.CH3_CODE_AT + 1]
                    m8 = m8 if not v & 0x20 else op == 0xE2
                    x8 = x8 if not v & 0x10 else op == 0xE2
                pc += n

    def test_merchant_writes_include_the_wake_hook(self):
        blob, labels = m.ch3_code([32, 33, 78, 35], PICKS, ITEMS, TABLES)
        zones = blob[labels['zones'] - m.CH3_CODE_AT:labels['thresholds'] - m.CH3_CODE_AT]
        self.assertEqual(len(zones), 2 * 4)

    def test_pick_follows_the_cumulative_weight(self):
        # r = S × 난수 >> 8, 누적 무게가 r 이상인 첫 칸: 첫 칸은 r = 0 도 받아 무게보다 하나 많다
        entries = [(0, 10), (1, 0), (2, 30)]
        self.assertEqual(m.fc_pick(entries, 0), 0)
        odds = m.fc_pick_odds(entries)
        self.assertEqual(sum(odds.values()), 256)
        self.assertEqual(odds, {0: sum(1 for x in range(256) if 40 * x >> 8 <= 10), 2: sum(1 for x in range(256) if 40 * x >> 8 > 10)})
        # 무게 0 인 첫 칸도 r = 0 이면 고른다. 합 FF 면 난수 그대로
        self.assertEqual(m.fc_pick([(3, 0), (4, 9)], 0), 3)
        self.assertEqual(m.fc_pick([(3, 0xFE), (4, 1)], 0xFF), 4)
        with self.assertRaises(ValueError):
            m.fc_pick([(0, 200), (1, 100)], 0)

    def test_species_odds(self):
        self.assertEqual(m.species_odds(8, 0), {2: 1 - 8 / 256, 3: 8 / 256, 4: 0.0})
        self.assertAlmostEqual(sum(m.species_odds(32, 64).values()), 1.0)

    def test_rng_is_dq5_23_eafd(self):
        # ×3 + 15AD(32비트), 난수 바이트는 위 16비트의 아래 바이트
        self.assertEqual(m.rng_next(0), (0x15AD, 0))
        self.assertEqual(m.rng_next(0x00010000), (0x000315AD, 3))
        self.assertEqual(m.rng_next(0xFFFFFFFF)[0], (0xFFFFFFFF * 3 + 0x15AD) & 0xFFFFFFFF)


@unittest.skipUnless(DQ4.is_file() and DQ5.is_file(), 'rom/dq4.nes and rom/dq5.sfc')
class RomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(DQ4.read_bytes())
        cls.dq5 = DQ5.read_bytes()

    def test_fc_table_is_the_doc(self):
        self.assertEqual(m.fc_drop_table(self.prg), DOC_TABLE)

    def fc_roll(self, level, start, rolls):
        """FC 12:$91DE 를 6502 해석기로: rand(16)·톨네코 레벨·rand(256) 을 넣어 얻은 칸(없으면 None)."""
        import dq4cpu
        prg = bytearray(self.prg)
        o = m.FC_BANK * 0x4000
        # BRK 17 0F(rand(16))·BRK 63 73(일행에서 인물 5)·BRK 0F 33(레벨)을 같은 길이의 JSR 로 바꿔 값을 넣는다
        for addr, stub in ((0x91E7, 0xFFF0), (0x91F4, 0xFFF1), (0x91F9, 0xFFF2)):
            self.assertEqual(prg[o + (addr & 0x3FFF)], 0x00)
            prg[o + (addr & 0x3FFF):o + (addr & 0x3FFF) + 3] = bytes((0x20, stub & 0xFF, stub >> 8))
        cpu = dq4cpu.CPU(bytes(prg), m.FC_BANK)
        cpu.wram[0x615A - 0x6000] = 2
        left = list(rolls)

        class Hit(Exception):
            pass

        def put(v):
            def hook(c):
                c.a = v() if callable(v) else v
            return hook
        cpu.hooks.update({0xFFF0: put(start), 0xFFF1: put(0), 0xFFF2: put(level), 0xC891: put(lambda: left.pop(0))})
        cpu.stubs.update({0xFFF0, 0xFFF1, 0xFFF2, 0xC891})

        def hit(c):
            raise Hit(c.x)
        cpu.hooks[0x9246] = hit
        try:
            cpu.call(0x91DE)
        except Hit as e:
            return e.args[0], len(rolls) - len(left)
        return None, len(rolls) - len(left)

    def test_model_matches_the_fc_routine(self):
        table = m.fc_drop_table(self.prg)
        rng = random.Random(273)
        cases = [(level, rng.randrange(16), [rng.randrange(256) for _ in range(16)])
                 for level in (0x01, 0x28, 0x63) for _ in range(91)]
        cases += [(0x63, 4, [0x62]), (0x63, 4, [0x63] + [0xFF] * 15), (0x01, 8, [0x00])]
        for level, start, rolls in cases:
            got, used = self.fc_roll(level, start, rolls)
            want = m.drop_roll(table, level, start, rolls)
            self.assertEqual(got, want, (level, start, rolls))
            self.assertEqual(used, 16 if want is None else (want - start) % 16 + 1)

    def test_merchant_matches_fc(self):
        # FC 18:$9D19 LDA #$0A / BRK 17 0F: rand(10) = 0 이면 たびのしょうにん. 15:$BEF4 rand < 10 이면 여관
        import dq4encounter
        o = 0x18 * 0x4000 + (0x9D19 & 0x3FFF)
        self.assertEqual(bytes(self.prg[o:o + 5]), bytes((0xA9, m.MERCHANT_RATE, 0x00, 0x17, 0x0F)))
        self.assertEqual(m.MERCHANT_INN, dq4encounter.MERCHANT_INN)
        self.assertEqual(self.dq5[(0x06 & 0x7F) * 0x8000 + (m.WAKE_SITE & 0x7FFF):][:4], m.WAKE_ORIG)

    def test_every_chapter3_field_zone_is_in_the_table(self):
        report = {f'{z:02X}': {'zone': z} for z in m.CH3_FIELD}
        self.assertEqual(m.merchant_zones(report), list(m.CH3_FIELD))

    def test_items_have_dq5_counterparts(self):
        items = m.dq5_drop_items(self.prg, self.dq5)
        self.assertEqual(len(set(items)), 16)

    def test_lists_take_out_the_night_slots_by_day(self):
        # 구역 16 칸 4·10(メラゴースト)은 밤에만, 칸 0·5·6 은 비어 있다. 목록은 FC 칸 번호. 둘째 무리부터는 낮 칸 0~3·밤 1~4
        day, night = m.pick_lists(self.prg, 0x16, 'day'), m.pick_lists(self.prg, 0x16, 'night')
        self.assertEqual([k for k, _ in day[0]], [1, 2, 3, 7, 8, 9, 11])
        self.assertEqual([k for k, _ in night[0]], [1, 2, 3, 4, 7, 8, 9, 10, 11])
        self.assertEqual(([k for k, _ in day[1]], [k for k, _ in night[1]]), ([1, 2, 3], [1, 2, 3, 4]))
        self.assertEqual(dict(night[0])[4], 50)

    def test_chapter3_zones_are_the_reached_ones(self):
        # dq4fieldencounter.CH3_ZONES 는 FC 3장 일행이 걸어 닿는 필드 구역과 그 입구 던전의 구역
        import dq4encounter
        import dq4fieldencounter
        field, groups = set(), set()
        for bridge in (False, True):
            cells, hits = dq4encounter.ch3_reach(self.prg, bridge)
            field |= {dq4encounter.zone_at(self.prg, 2, x, y) for x, y in cells}
            groups |= {g for g, _ in hits}
        lists = dict(dq4encounter.dungeon_lists(self.prg)[0][2])
        dungeon = {z for g in groups if g in lists for z in lists[g] if z != 0xFF}
        self.assertEqual(set(dq4fieldencounter.CH3_FIELD), field)
        self.assertEqual(set(dq4fieldencounter.CH3_DUNGEON), dungeon)


@unittest.skipUnless(DQ4.is_file() and DQ5.is_file(), 'rom/dq4.nes and rom/dq5.sfc')
class PickTests(unittest.TestCase):
    """무리 고르기: 모형(fc_pick·species_odds)이 FC 루틴(6502 해석기)과 같고, 훅(65816 해석기)이 모형과 같다."""

    @classmethod
    def setUpClass(cls):
        import json
        import subprocess
        import tempfile
        import dq4groupbuild
        from kr_patch.fc import ines
        cls.prg = ines.prg(DQ4.read_bytes())
        cls.dq5 = DQ5.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'enc.json'
            subprocess.run([sys.executable, str(m.DQ5_TOOLS / 'dq5encounterwrite.py'), str(DQ5), 'dump', '-o',
                            str(path)], check=True, capture_output=True)
            orig = json.loads(path.read_text(encoding='utf-8'))
        _, _, cls.report = m.docs(cls.prg, cls.dq5, orig, dq4groupbuild.dungeon_zones(cls.prg).values())
        cls.picks = m.pick_rows(cls.prg, cls.report)

    def fc_cpu(self, z, mode, prg=None):
        import dq4cpu
        import dq4encounter
        rec = dq4encounter.zone(self.prg, z)
        cpu = dq4cpu.CPU(prg or self.prg, 0x18)
        cpu.ram[0x41] = 0x80 if mode == 'dungeon' else 0
        cpu.wram[0x62ED - 0x6000] = 0x90 if mode == 'night' else 0x10      # 78 이상이 밤
        slots = rec['addr'] + 2
        cpu.ram[0], cpu.ram[1], cpu.ram[0x0E] = slots & 0xFF, slots >> 8, rec['row'] * 18
        return cpu, rec

    def test_model_is_the_fc_slot_pick(self):
        # 18:$9D6B 마스크, $9D9C FF 칸 빼기, $9DBB 합, $9DDE 고르기. 난수는 모두 $C891 을 거친다(BRK 17 0F 의 10:$A1F6 도)
        for z, mode in ((0x04, 'day'), (0x04, 'night'), (0x16, 'day'), (0x16, 'night'), (0x42, 'dungeon'),
                        (0x00, 'day'), (0x0C, 'night')):
            first, _ = m.pick_lists(self.prg, z, mode)
            for rnd in range(256):
                cpu, _ = self.fc_cpu(z, mode)
                cpu.hooks[0xC891] = lambda c, v=rnd: setattr(c, 'a', v)
                cpu.stubs.add(0xC891)
                for f in (0x9D6B, 0x9D9C, 0x9DBB, 0x9DDE):
                    cpu.call(f)
                self.assertEqual(cpu.y, m.fc_pick(first, rnd), (hex(z), mode, rnd))

    def test_model_is_the_fc_group_of_species(self):
        # 18:$9EB9: 둘째 무리, 난수 < 바이트 14 면 셋째, 그다음 난수 < 바이트 15 면 넷째(바이트를 덮어 넷째도 본다)
        import dq4encounter
        rng = random.Random(14)
        for z, mode in ((0x04, 'day'), (0x16, 'night'), (0x42, 'dungeon')):
            rec = dq4encounter.zone(self.prg, z)
            _, second = m.pick_lists(self.prg, z, mode)
            for third, fourth in ((8, 0), (0x80, 0x40), (0xFF, 0xFF)):
                prg = bytearray(self.prg)
                o = 0x18 * 0x4000 + (dq4encounter.WEIGHTS + 18 * rec['row'] + 14 & 0x3FFF)
                prg[o:o + 2] = bytes((third, fourth))
                for _ in range(60):
                    slot = rng.choice([i for i in range(5) if rec['slots'][i] != 0xFF])
                    rnds = [rng.randrange(256) for _ in range(5)]
                    cpu, _ = self.fc_cpu(z, mode, bytes(prg))
                    cpu.wram[0x6E45 - 0x6000:0x6E49 - 0x6000] = b'\xFF' * 4
                    left = list(rnds)
                    cpu.hooks[0xC891] = lambda c: setattr(c, 'a', left.pop(0) if left else 0xFF)
                    cpu.stubs.add(0xC891)
                    cpu.y = slot
                    cpu.call(0x9EB9)
                    got = [g for g in cpu.wram[0x6E45 - 0x6000:0x6E49 - 0x6000] if g != 0xFF]
                    it = iter(rnds)
                    want = [rec['slots'][slot], rec['slots'][m.fc_pick(second, next(it))]]
                    if next(it) < third:
                        want.append(rec['slots'][m.fc_pick(second, next(it))])
                        if next(it) < fourth:
                            want.append(rec['slots'][m.fc_pick(second, next(it))])
                    self.assertEqual(got, want, (hex(z), mode, third, fourth, slot, rnds))

    def dq5_cpu(self, blob, state):
        import w65816
        rom = bytearray(self.dq5) + bytes(max(0, 0x400000 - len(self.dq5)))
        o = (m.CH3_CODE_AT >> 16 & 0x7F) * 0x8000
        rom[o:o + len(blob)] = blob
        cpu = w65816.Cpu(bytes(rom), bytearray(0x20000))
        cpu.dbr, cpu.p = 0x23, 0x20                    # 훅 자리: M 8비트, X 16비트, DB 23
        cpu.wram[m.RNG_LOW:m.RNG_LOW + 4] = state.to_bytes(4, 'little')
        return cpu

    def test_model_is_the_fc_formation(self):
        # 18:$9D6B~$9DDE 첫 칸, $9E0D 무리 짓기(칸 0~4 의 덧붙는 마리 $9F04, 칸 5 $9F5D, 칸 6~10 $9E7B, 칸 11, 고정
        # 편성 $9E19)를 6502 해석기로 같은 난수 바이트 차례로 돌린 무리·마릿수가 모형과 같다. 장 k 는 $615A
        import dq4encounter
        rng = random.Random(9)
        tables = m.fc_tables(self.prg)
        ids = {fc: fc for fc in range(0x100)}
        for z, mode in ((0x04, 'day'), (0x04, 'night'), (0x16, 'day'), (0x16, 'night'), (0x42, 'dungeon'),
                        (0x0C, 'night'), (0x48, 'dungeon'), (0x14, 'day')):
            rec = dq4encounter.zone(self.prg, z)
            lists = m.pick_lists(self.prg, z, mode)
            data = m.zone_data(self.prg, z, ids)
            row = (0, z, rec['row'], 0, {'day': lists, 'night': lists}, data)
            w = dq4encounter.weights(self.prg, rec['row'])
            row = (0, z, w[14], w[15], {'day': lists, 'night': lists}, data)
            for k in (0, 1, 2):
                for _ in range(40):
                    state = rng.randrange(1 << 32)
                    want, _ = m.fc_formation(row, tables, k, False, state)
                    rnds, st = [], state
                    for _ in range(40):
                        st, r = m.rng_next(st)
                        rnds.append(r)
                    cpu, _ = self.fc_cpu(z, mode)
                    cpu.wram[0x615A - 0x6000] = k
                    cpu.wram[0x6E45 - 0x6000:0x6E4D - 0x6000] = b'\xFF' * 4 + b'\x00' * 4
                    left = list(rnds)
                    cpu.hooks[0xC891] = lambda c: setattr(c, 'a', left.pop(0))
                    cpu.stubs.add(0xC891)
                    for f in (0x9D6B, 0x9D9C, 0x9DBB, 0x9DDE):
                        cpu.call(f)
                    cpu.call(0x9E0D)
                    mons = cpu.wram[0x6E45 - 0x6000:0x6E49 - 0x6000]
                    counts = cpu.wram[0x6E49 - 0x6000:0x6E4D - 0x6000]
                    got = [(g, n) for g, n in zip(mons, counts) if g != 0xFF]
                    self.assertEqual(got, want, (hex(z), mode, k, state))

    def test_hook_forms_like_the_model(self):
        # 표의 모든 구역·낮밤·장(1~3장 flag)에서 난수 상태마다 훅(65816 해석기)이 지은 무리(7E:1001~1008)와 줄 번호 0,
        # 돌린 난수 상태가 모형과 같다
        import dq4ch2event

        class Done(Exception):
            pass
        rng = random.Random(5)
        merchant = m.merchant_zones(self.report)
        items = [(0, 0)] * m.DROP_SLOTS
        tables = m.fc_tables(self.prg)
        blob, labels = m.ch3_code(merchant, self.picks, items, tables)
        flag3, bit3 = m.chapter3_flag()
        flag2, bit2 = m.FLAG_BASE + dq4ch2event.CHAPTER2[0], dq4ch2event.CHAPTER2[1]
        for row in self.picks:
            zone = row[0]
            for night in (False, True):
                for k in (0, 1, 2):
                    for _ in range(6):
                        state = rng.randrange(1 << 32)
                        cpu = self.dq5_cpu(blob, state)
                        cpu.wram[0x075E] = 0xF8 if night else 0x50
                        cpu.wram[flag2 & 0xFFFF] = cpu.wram[flag3 & 0xFFFF] = 0
                        cpu.wram[flag2 & 0xFFFF] |= bit2 if k == 1 else 0
                        cpu.wram[flag3 & 0xFFFF] |= bit3 if k == 2 else 0
                        cpu.wram[0x1001:0x1009] = b'\xFF' * 4 + b'\x00' * 4
                        cpu.wram[0x1009:0x100C] = b'\x07' * 3
                        cpu.x = zone * m.CH3_ZONE_RECORD
                        for at in (m.FORMED, m.NO_ENCOUNTER):
                            cpu.hooks[at] = lambda c, at=at: (_ for _ in ()).throw(Done(at))
                        with self.assertRaises(Done) as got:
                            cpu.jsl(labels['pick'])
                        want, after = m.fc_formation(row, tables, k, night, state)
                        mons, counts = cpu.wram[0x1001:0x1005], cpu.wram[0x1005:0x1009]
                        formed = [(g, n) for g, n in zip(mons, counts) if g != 0xFF]
                        self.assertEqual(got.exception.args[0], m.FORMED if want else m.NO_ENCOUNTER)
                        self.assertEqual(formed, want, (zone, night, k, state))
                        self.assertEqual(bytes(cpu.wram[m.RNG_LOW:m.RNG_LOW + 4]), after.to_bytes(4, 'little'))
                        if want:
                            self.assertEqual(bytes(cpu.wram[0x1009:0x100C]), bytes(3))
        # 표에 없는 구역은 원래 고르기(23:E904)로 가고 PICK = FFFF
        cpu = self.dq5_cpu(blob, 1)
        cpu.x = 0xE6 * m.CH3_ZONE_RECORD
        cpu.hooks[m.FIRST_LOOP] = lambda c: (_ for _ in ()).throw(Done(c.wram[m.PICK & 0xFFFF] | c.wram[(m.PICK & 0xFFFF) + 1] << 8))
        with self.assertRaises(Done) as got:
            cpu.jsl(labels['pick'])
        self.assertEqual(got.exception.args[0], 0xFFFF)

    def test_surprise_hook_is_fc(self):
        # 26:832E 훅(65816 해석기, rand(33) 을 값으로 끼움)이 k 0~3·r 0~32 모두 FC 18:$A20E 문턱대로 $1000 아래 두 비트를
        # 두고 위 비트는 그대로. 문턱은 FC 표 $A45C(fc/dq4/docs/dq4-encounter-format.md 「기습과 선제」)
        class Done(Exception):
            pass
        tables = m.fc_tables(self.prg)
        self.assertEqual(tables['surprise'], [0x1E, 0x1F, 0x1B, 0x1F, 0x1B, 0x1C, 0x18, 0x1C])
        blob, labels = m.ch3_code(m.merchant_zones(self.report), self.picks, [(0, 0)] * m.DROP_SLOTS, tables)
        for k in range(4):
            for r in range(33):
                cpu = self.dq5_cpu(blob, 1)
                cpu.p = 0x30
                cpu.wram[0x1000] = 0x40 | k

                def rand(c, r=r):
                    self.assertEqual(c.a & 0xFF, 0x21)
                    c.a = c.a & 0xFF00 | r
                    c.rtl()
                    return True
                cpu.hooks[m.RAND8] = rand
                cpu.hooks[m.SURPRISE_DONE] = lambda c: (_ for _ in ()).throw(Done())
                with self.assertRaises(Done):
                    cpu.jsl(labels['surprise_hook'])
                self.assertEqual(cpu.wram[0x1000], 0x40 | m.fc_surprise(tables['surprise'], k, r), (k, r))

    def test_coef_hook_gives_own_coefficient_only_to_its_zone(self):
        # 23:E892 훅: 기본 조우율 28 의 구역 08 만 계수 31(셈: FC 풀밭 31.3셀에 33.3셀, 표의 2B 는 35.8셀), 다른 구역은
        # 원래처럼 표 23:EA44[$01]. 돌아갈 때 A 위 바이트 0
        coefs = m.own_coefs(self.prg, self.report)
        self.assertEqual(coefs, [(self.report['08']['zone'], 0x31)])
        table = self.dq5[m._lorom(m.RATE_COEF):m._lorom(m.RATE_COEF) + 8]
        blob, labels = m.ch3_code(m.merchant_zones(self.report), self.picks, [(0, 0)] * m.DROP_SLOTS,
                                  m.fc_tables(self.prg), coefs)
        for zone in sorted({r['zone'] for r in self.report.values()}):
            for index in range(8):
                cpu = self.dq5_cpu(blob, 1)
                cpu.x, cpu.a = zone * m.CH3_ZONE_RECORD, 0x1234
                cpu.wram[0x01] = index
                cpu.jsl(labels['coef'])
                want = 0x31 if zone == coefs[0][0] else table[index]
                self.assertEqual(cpu.a, want, (zone, index))
        self.assertGreater(m.rate_error(self.prg, 28, 0x2B), 2 * m.rate_error(self.prg, 28, 0x31))

    def test_swamp_hook_damages_one_cell_in_two(self):
        # 06:804E 훅: 늪(4D)·トラマナ 없음이면 사람 셀 X + Y 가 홀수일 때만 원래 피해 길(06:8087, A = 1), 짝수면 RTL.
        # 다른 종류·トラマナ 이면 늘 원래 길. 어느 쪽이든 $80 = 1(늪 위)
        class Hit(Exception):
            pass
        blob, labels = m.ch3_code(m.merchant_zones(self.report), self.picks, [(0, 0)] * m.DROP_SLOTS,
                                  m.fc_tables(self.prg))
        for kind, tramana in ((m.SWAMP_KIND, 0), (m.SWAMP_KIND, 0x81), (0x02, 0)):
            for slot in (0, 1, 2):
                hits = []
                for cell in range(0xFE, 0x106):
                    cpu = self.dq5_cpu(blob, 1)
                    cpu.p, cpu.x = 0x30, slot
                    cpu.wram[0x00], cpu.wram[0x80], cpu.wram[0x194E] = kind, 0, tramana
                    cpu.wram[0x3020 + slot], cpu.wram[0x3080 + slot] = cell & 0xFF, 0x83
                    cpu.hooks[m.SWAMP_DAMAGE] = lambda c: (_ for _ in ()).throw(Hit(c.a & 0xFF))
                    try:
                        cpu.jsl(labels['swamp'])
                        hits.append(False)
                    except Hit as e:
                        self.assertEqual(e.args[0], 1)
                        hits.append(True)
                    self.assertEqual(cpu.wram[0x80], 1)
                plain = kind == m.SWAMP_KIND and not tramana
                self.assertEqual(hits, [(c + 0x83) % 2 == 1 for c in range(0xFE, 0x106)] if plain else [True] * 8,
                                 (kind, tramana, slot))

    def test_table_has_every_zone_and_fits(self):
        # docs 가 레코드를 쓰는 구역 모두(바다 81·82 포함), 목록 무게 합은 8비트
        zones = [r[0] for r in self.picks]
        self.assertEqual(len(zones), len(set(zones)))
        self.assertLessEqual({r['zone'] for r in self.report.values()}, set(zones))
        self.assertIn(81, zones)
        for *_, modes, _ in self.picks:
            for first, second in modes.values():
                self.assertTrue(first and second)
                self.assertLessEqual(sum(w for _, w in first), 0xFF)


if __name__ == '__main__':
    unittest.main()
