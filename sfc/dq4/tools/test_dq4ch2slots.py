"""2장 사건 자원 예약표: 세션 몫끼리·이미 쓰는 자원과 겹치지 않는지, 등록된 사건 모듈이 자기 몫 안에 있는지."""

import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1event  # noqa: E402
import dq4ch2battle as battle  # noqa: E402
import dq4ch2event as ev  # noqa: E402
import dq4ch2slots as slots  # noqa: E402
import dq4prologue  # noqa: E402

SLOTS = slots.SLOTS


def _flag_constants(mod):
    """모듈의 대문자 상수 가운데 (번호, 한 비트 마스크) 꼴."""
    return {v for k, v in vars(mod).items() if k.isupper() and isinstance(v, tuple) and len(v) == 2
            and all(isinstance(x, int) for x in v) and v[0] < 0x80 and v[1] in (1, 2, 4, 8, 16, 32, 64, 128)}


class SlotTest(unittest.TestCase):
    def test_code_areas_are_disjoint_inside_one_bank_and_off_the_base(self):
        areas = [(k, s.code) for k, s in SLOTS.items()] + [('base', slots.BASE_CODE)] + \
            [(f'spare{i}', c) for i, c in enumerate(slots.SPARE['code'])]
        for k, (lo, hi) in areas:
            self.assertLess(lo, hi, k)
            self.assertEqual(lo >> 16, (hi - 1) >> 16, f'{k}: 뱅크를 넘음')
            self.assertGreaterEqual(lo & 0xFFFF, 0x8000, k)
        for i, (k, (lo, hi)) in enumerate(areas):
            for k2, (lo2, hi2) in areas[i + 1:]:
                self.assertTrue(hi <= lo2 or hi2 <= lo, f'{k} 와 {k2} 의 코드 자리가 겹침')

    def test_code_areas_miss_the_known_users_of_those_banks(self):
        # 5F:8000~ 장 제목 상자(dq4chapterbox), 5E:F000~ 2장 첫머리(dq4ch2event)
        import dq4chapterbox
        for k, s in SLOTS.items():
            lo, hi = s.code
            self.assertFalse(lo <= dq4chapterbox.CODE_AT < hi, k)
            self.assertFalse(lo <= ev.CODE_AT < hi, k)
        self.assertEqual(slots.BASE_CODE[0], ev.CODE_AT)

    def test_flag_bytes_are_owned_once_and_stay_in_the_free_stretch(self):
        seen = {}
        for k, s in SLOTS.items():
            for f in s.flags:
                self.assertNotIn(f, seen, f'{f + 0x2190:04X} 를 {seen.get(f)} 와 {k} 가 함께 가짐')
                seen[f] = k
            self.assertTrue(set(s.byte_flags) <= set(s.flags), k)
        for f in slots.SPARE['flags']:
            self.assertNotIn(f, seen)
        # 21F5·21F6·21F8~21FB 는 DQ5 가 고정 주소로도 쓴다. 21F0 앞은 비트가 남아 있어도 16비트 쓰기에 휩쓸린다
        fixed = {0x65, 0x66, 0x68, 0x69, 0x6A, 0x6B}
        for f in list(seen) + list(slots.SPARE['flags']):
            self.assertTrue(0x60 <= f <= 0x7C, f'{f + 0x2190:04X}')
            self.assertNotIn(f, fixed, f'{f + 0x2190:04X}')
            self.assertNotEqual(f, 0x78, '2208 은 2장 첫머리·텐페가 비트째 쓴다')

    def test_reserved_flags_are_not_used_by_the_earlier_chapters(self):
        earlier = _flag_constants(dq4ch1event) | _flag_constants(ev) | _flag_constants(dq4prologue)
        mine = {f for s in SLOTS.values() for f in s.flags} | set(slots.SPARE['flags'])
        self.assertFalse({idx for idx, _ in earlier} & mine)
        self.assertNotIn(slots.BATTLE_WON, earlier)
        for bit in slots.SPARE['flag_bits']:
            self.assertNotIn(bit, earlier)
        self.assertNotIn(slots.BATTLE_WON, slots.SPARE['flag_bits'])

    def test_no_tool_names_a_reserved_flag_byte(self):
        # 다른 도구가 이 자리를 롱 주소로 직접 읽고 쓰면 예약이 깨진다. 이 표와 사건 모듈만 쓸 수 있다
        mine = {f + 0x2190 for s in SLOTS.values() for f in s.flags} | {f + 0x2190 for f in slots.SPARE['flags']}
        owners = {s.module for s in SLOTS.values()}
        for path in HERE.glob('*.py'):
            if path.stem.startswith('test_') or path.stem in owners or path.stem == 'dq4ch2slots':
                continue
            for m in re.finditer(r'0x7E(2[12][0-9A-Fa-f]{2})\b|7E:(2[12][0-9A-F]{2})\b', path.read_text()):
                addr = int(m[1] or m[2], 16)
                self.assertNotIn(addr, mine, f'{path.name}: 예약된 flag 바이트 {addr:04X}')

    def test_battle_pieces_are_owned_once(self):
        for what in ('groups', 'monsters', 'battles'):
            seen = {}
            for k, s in SLOTS.items():
                for v in getattr(s, what):
                    self.assertNotIn(v, seen, f'{what} {v:02X}: {seen.get(v)} 와 {k}')
                    seen[v] = k
            self.assertFalse(set(seen) & set(slots.SPARE[what]), what)
        groups = {g for s in SLOTS.values() for g in s.groups} | set(slots.SPARE['groups'])
        self.assertNotIn(dq4ch1event.BOSS_GROUP, groups)
        # 무리 30~3F 는 DQ5 롬 안에서 부르는 곳이 없다(sfc/dq5/docs/dq5-data-format.md)
        self.assertTrue(all(0x31 <= g <= 0x3F for g in groups))
        stubs = {b for s in SLOTS.values() for b in s.battles} | set(slots.SPARE['battles'])
        self.assertEqual(stubs, set(range(battle.STUB_COUNT)))

    def test_monsters_do_not_appear_in_field_zones_or_chapter_one(self):
        import dq4fieldencounter
        mine = {m for s in SLOTS.values() for m in s.monsters} | set(slots.SPARE['monsters'])
        self.assertFalse(mine & set(dq4fieldencounter.MONSTERS.values()))
        self.assertFalse(mine & set(dq4ch1event.BOSS_MONSTERS))

    def test_borrowed_script_lists_belong_to_one_session_and_no_tool_yet(self):
        owners = slots.script_lists()
        self.assertEqual(len(owners), sum(len(s.scripts) for s in SLOTS.values()))
        modules = {s.module: k for k, s in SLOTS.items()}
        for path in HERE.glob('*.py'):
            if path.stem.startswith('test_') or path.stem == 'dq4ch2slots':
                continue
            text = path.read_text()
            for lst, key in owners.items():
                if f'"{lst}"' in text or f"'{lst}'" in text:
                    self.assertEqual(modules.get(path.stem), key, f'{path.name} 가 {key} 의 목록 {lst} 를 씀')

    def test_list_prefixes_are_distinct(self):
        prefixes = [s.lists for s in SLOTS.values()]
        for p in prefixes:
            self.assertTrue(p.startswith('ch2_') and p.endswith('_'), p)
            self.assertFalse([q for q in prefixes if q != p and q.startswith(p)], p)


class RegisteredModuleTest(unittest.TestCase):
    """dq4ch2event.EVENTS 에 넣은 모듈이 몫 안에 있는지. 모듈이 하나도 없으면 아무것도 보지 않는다."""

    def test_modules_stay_in_their_slots(self):
        for ctx in ev.contexts(0x1000):
            mod, slot = ctx.module, ctx.slot
            for idx, mask in getattr(mod, 'FLAGS', ()):
                self.assertIn(idx, slot.flags, f'{ctx.key}: flag {idx + 0x2190:04X}')
            for b in getattr(mod, 'BATTLES', ()):
                self.assertIn(b['group'], slot.groups, ctx.key)
                if b.get('stub') is not None:
                    self.assertIn(b['stub'], slot.battles, ctx.key)
                # 다른 세션 몫으로 덮을 몬스터는 쓰지 않는다(DQ5 몬스터를 그대로 쓰는 것은 된다)
                others = {m for k, s in SLOTS.items() if k != ctx.key for m in s.monsters}
                for m, _ in b['members']:
                    self.assertNotIn(m, others, f'{ctx.key}: 몬스터 {m:02X}')
            self.assertTrue(set(getattr(mod, 'MONSTERS', {})) <= set(slot.monsters), ctx.key)
            if hasattr(mod, 'native'):
                code, at = mod.native(ctx)
                self.assertLessEqual(ctx.code_at + len(code), slot.code[1], ctx.key)
                self.assertEqual(at, ctx.at, f'{ctx.key}: 주소가 롬에 따라 바뀜')


@unittest.skipUnless((ROOT / 'rom' / 'dq5.sfc').is_file(), 'local source ROM not present')
class Dq5RomTest(unittest.TestCase):
    def test_dq5_names_no_reserved_flag_byte(self):
        # dq5flags 가 모으는 모든 출처(대화·인물·목록·맵 루틴·이벤트·네이티브 BRK·롱 주소)에서 예약 바이트가 나오지 않는다.
        # 21EF·21F5·21F6·21FA·21FB 의 색인 쓰기는 이 해킹이 돌리지 않는 DQ5 장면 몫이다(dq4ch2slots 주석)
        import dq5flags
        from dq5map import Rom
        rom = Rom((ROOT / 'rom' / 'dq5.sfc').read_bytes())
        refs = dq5flags.by_bit(dq5flags.collect(rom, ['talk', 'npc', 'list', 'hook', 'event', 'code', 'long', 'short']))
        used = {addr for addr, _ in refs}
        mine = {f + 0x2190 for s in SLOTS.values() for f in s.flags} | {f + 0x2190 for f in slots.SPARE['flags']}
        self.assertFalse(used & mine, sorted(f'{a:04X}' for a in used & mine))
        bits = {(a, b) for a, b in refs}
        for idx, mask in (slots.BATTLE_WON, *slots.SPARE['flag_bits']):
            self.assertNotIn((idx + 0x2190, mask.bit_length() - 1), bits)
            self.assertNotIn((idx + 0x2190, -1), bits)

    def test_event_groups_are_unused_by_dq5(self):
        # 무리 표 23:D757 의 31~3A 는 비어 있는 꼴(c0 00 ff …)이고 부르는 곳이 없다
        data = (ROOT / 'rom' / 'dq5.sfc').read_bytes()
        o = (0x23 & 0x7F) * 0x8000 + (0xD757 & 0x7FFF)
        for g in {g for s in SLOTS.values() for g in s.groups} | set(slots.SPARE['groups']):
            self.assertEqual(data[o + 13 * g:o + 13 * g + 13].hex(), 'c000ffffff0100000000000000', f'{g:02X}')


if __name__ == '__main__':
    unittest.main()
