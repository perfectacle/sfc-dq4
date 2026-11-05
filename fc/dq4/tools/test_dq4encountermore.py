"""조우 표의 명령줄 출력·특수 전투 표·조우 기록(enc.lua) 대조를 합성 PRG 와 합성 기록으로 검사한다."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
import warnings
from unittest import mock

import dq4encounter as en
import dq4map
from test_dq4encounter import enc_prg, put, word
from test_dq4npcblock import world_prg


def run_main(prg, *args):
    """합성 PRG 를 iNES 파일로 써서 main() 을 돌린다. (출력 줄, 종료 코드)."""
    head = bytes([0x4E, 0x45, 0x53, 0x1A, 32, 0]) + bytes(10)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'x.nes')
        with open(path, 'wb') as f:
            f.write(head + bytes(prg))
        out, code = io.StringIO(), None
        with mock.patch.object(sys, 'argv', ['x', path, *args]), contextlib.redirect_stdout(out), \
                warnings.catch_warnings():
            warnings.simplefilter('ignore', ResourceWarning)
            try:
                en.main()
            except SystemExit as e:
                code = e.code
    return out.getvalue().splitlines(), code


def put_bank(prg, bank, addr, data):
    o = bank * 0x4000 + (addr & 0x3FFF)
    prg[o:o + len(data)] = bytes(data)


def lists_prg():
    prg = enc_prg()
    put(en.GROUP_SIZE + 0x3A, [2], prg)
    put(en.GROUP_SIZE + 4, [1], prg)
    put(en.DUNGEON, word(0x9000), prg)
    put(en.DUNGEON5, word(0x9100), prg)
    put(0x9000, [0x3A, 0x05, 0xFF, 0x04, 0x21, 0xFF], prg)
    put(0x9100, [0xFF], prg)
    return prg


class ShowTests(unittest.TestCase):
    def setUp(self):
        self.prg = enc_prg()

    def test_zones_header_and_slots(self):
        out, _ = run_main(self.prg, 'zones', '5')
        self.assertEqual(out[0], '구역 05 18:8450 바이트0=69 기본율 30 무게줄 2 기습·선제 0/256·248/256 '
                                 '레벨 07 셋째·넷째 무리 64/256·32/256')
        self.assertEqual(out[1], '  칸  0 무게  10 10 10?')
        self.assertIn('  칸 12 무게   5 01 편성 01', out)
        self.assertFalse(any(l.startswith('  칸  4 ') for l in out))        # 칸 4 는 FF

    def test_zones_without_argument_lists_all(self):
        out, _ = run_main(self.prg, 'zones')
        self.assertEqual(sum(l.startswith('구역 ') for l in out), en.N_ZONES)

    def test_odds_day(self):
        out, _ = run_main(self.prg, 'odds', '5')
        self.assertEqual(out[0], '구역 05 (day) 첫 칸 고르기 256 경우')
        rows = {int(l.split()[1]): l for l in out[1:]}
        self.assertEqual(set(rows), {0, 1, 2, 3, 5, 6, 7, 11, 12})
        self.assertEqual(sum(int(l.split()[2].split('/')[0]) for l in rows.values()), 256)
        self.assertTrue(rows[0].endswith('무리: 10? 1~8 + 10?/11?/12?/13? 1~8'))
        self.assertTrue(rows[6].endswith('한 무리: 30? 5~8'))
        self.assertTrue(rows[12].endswith('편성 01: 50? 1~2 + 51? 2~4 + 52? 1~1'))

    def test_odds_modes_pick_different_masks(self):
        night, _ = run_main(self.prg, 'odds', '5', '--night')
        dungeon, _ = run_main(self.prg, 'odds', '5', '--dungeon')
        self.assertEqual(night[0], '구역 05 (night) 첫 칸 고르기 256 경우')
        self.assertEqual(dungeon[0], '구역 05 (dungeon) 첫 칸 고르기 256 경우')
        rows = lambda out: {int(l.split()[1]) for l in out[1:]}
        self.assertEqual(rows(night), {1, 2, 3, 5, 7, 11, 12})
        self.assertEqual(rows(dungeon), {0, 1, 2, 3, 5, 6, 7, 11, 12})

    def test_maps_prints_three_grids(self):
        out, _ = run_main(self.prg, 'maps')
        heads = [l for l in out if l.startswith('# ') and '구역 지도' in l]
        self.assertEqual(heads, ['# 1·2·4장 구역 지도 18:8000 (16줄, 칸 = 필드 16×16)',
                                 '# 3장 구역 지도 18:8100 (8줄, 칸 = 필드 16×16)',
                                 '# 5장 구역 지도 18:8200 (16줄, 칸 = 필드 16×16)'])
        row2 = [l for l in out if l.startswith('20  ')]
        self.assertEqual(row2[0].split()[1:5], ['00', '00', '00', '05'])     # 1장 줄 2, 칸 3 = 05 (C5 & 3F)
        self.assertTrue(row2[2].endswith('bit7-6: 0000000000000000'))
        self.assertEqual(row2[2].split()[4], '07')

    def test_formations_lines_skip_ff(self):
        out, _ = run_main(self.prg, 'formations')
        self.assertEqual(len(out), en.N_FORMATIONS)
        self.assertEqual(out[1], '편성 01: 50? 1~2, 51? 2~4, 52? 1~1')
        self.assertEqual(out[0], '편성 00: ' + ', '.join(['00? 1~1'] * 4))

    def test_dungeons_lists_both_tables(self):
        out, _ = run_main(lists_prg(), 'dungeons')
        self.assertEqual(out, ['# 장 1~4 18:9000~9005', '그룹 3A: 05 --', '그룹 04: 21',
                               '# 5장 18:9100~9100'])


class BossTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = enc_prg()
        put(en.BOSS, word(0x9200), prg)
        put(0x9200, [0x20, 0xFF, 0xFF, 0xFF, 0xF3, 0, 0, 0], prg)
        put(0x9200 + 8 * 7, [0x21, 0x22, 0xFF, 0xFF, 0x01, 0x02, 0, 0], prg)
        put_bank(prg, en.ARENA[0], en.ARENA[1], [7, 8, 9, 10, 11])

    def test_bosses_masks_counts_to_low_nibble(self):
        b = en.bosses(self.prg)
        self.assertEqual(len(b), en.N_BOSSES)
        self.assertEqual(b[0][:2], (0, [(0x20, 3)]))
        self.assertEqual(b[7][1], [(0x21, 1), (0x22, 2)])
        self.assertEqual(b[7][2], [0x21, 0x22, 0xFF, 0xFF, 1, 2, 0, 0])

    def test_arena_and_despalace_lists(self):
        put_bank(self.prg, *en.DESPALACE, [0x10, 0x11, 0xFF])
        self.assertEqual(en.arena_list(self.prg), [7, 8, 9, 10, 11])
        self.assertEqual(en.despalace_list(self.prg), [(0x10, 0x1C), (0x11, 0x1D)])

    def test_boss_callers_direct_and_branch_forms(self):
        o = 0x1F * 0x4000 + 0x100
        self.prg[o:o + 5] = bytes([0xA9, 0x02, 0x00, 0x01, 0x8F])
        o = 0x05 * 0x4000 + 0x200
        self.prg[o:o + 9] = bytes([0xA9, 0x09, 0xF0, 0x02, 0xEA, 0xEA, 0x00, 0x01, 0x8F])
        self.assertEqual(sorted(en.boss_callers(self.prg)), [(2, 0x1F, 0xC100), (9, 0x05, 0x8200)])

    def test_bosses_command(self):
        put_bank(self.prg, *en.DESPALACE, [0x10, 0x11, 0xFF])
        o = 0x1F * 0x4000 + 0x100
        self.prg[o:o + 5] = bytes([0xA9, 0x00, 0x00, 0x01, 0x8F])
        out, _ = run_main(self.prg, 'bosses')
        self.assertEqual(len(out), en.N_BOSSES + 2 + 2)
        self.assertEqual(out[0], '00 20?×3  [20 FF FF FF F3 00 00 00]  ← 1F:C100')
        self.assertEqual(out[7], '07 21?×1, 22?×2  [21 22 FF FF 01 02 00 00]  ← 1C:B024(표, $6287 & 7 = 0)')
        self.assertTrue(out[34].startswith('# 1C: 08:B756 표 — デスパレス(그룹 03)에서 겉모습 10 인'))
        self.assertTrue(out[35].startswith('# 1D: '))


class CheckLogTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = lists_prg()
        put(en.AFTER_BATTLE, [4, 8, 12], prg)
        put(en.TERRAIN_DAY, [0x10, 0x20], prg)
        put(en.TOGGLE, [0x85, 0x46, 0x05, 0x86, 0xFF], prg)
        put(en.HOLY + 1, [0x80], prg)
        put(en.BOSS, word(0x9200), prg)
        put(0x9200 + 16, [0x30, 0xFF, 0xFF, 0xFF, 0x01, 0, 0, 0], prg)

    def check(self, *lines):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'enc.txt')
            with open(path, 'w') as f:
                f.write('\n'.join(lines) + '\n')
            out = io.StringIO()
            with contextlib.redirect_stdout(out), warnings.catch_warnings():
                warnings.simplefilter('ignore', ResourceWarning)
                ok = en.check_log(self.prg, path)
        return ok, out.getvalue().splitlines(), path

    CHK = 'chk 35 2f 05 01 00 05 60 10'
    ENC = 'enc 1 35 2f 05 01 00 0 10 ff ff ff 01 00 00 00'

    def test_matching_chk_and_enc(self):
        ok, out, path = self.check(self.CHK, self.ENC)
        self.assertTrue(ok)
        self.assertEqual(out[0], '구역 05: 나온 몬스터 10?')
        self.assertEqual(out[1], f'{path}: 판정 1번(전투 조건이 맞은 것 1번), 전투 1번, 다름 0')

    def test_wrong_rate_is_reported(self):
        ok, out, _ = self.check('chk 35 2f 05 01 00 05 61 10')
        self.assertFalse(ok)
        self.assertEqual(out[0], '다름 chk 35 2f 05 01 00 05 61 10: 구역 05 조우율 60')
        self.assertTrue(out[-1].endswith('다름 1'))

    def test_wrong_zone_is_reported(self):
        _, out, _ = self.check('chk 35 2f 06 01 00 05 60 10')
        self.assertIn('다름 chk 35 2f 06 01 00 05 60 10: 구역 05 조우율 10', out)

    def test_extended_chk_rates(self):
        ext = lambda *v: ' '.join(f'{x:x}' for x in v)
        base = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        x4 = base[:5] + [1] + base[6:]
        holy = base[:6] + [1, 0, 0, 0, 9]
        dungeon = [0x80, 0x3A, 0, 0, 0] + base[5:]
        ok, out, _ = self.check(
            f'chk 35 2f 05 01 00 05 180 10 {ext(*x4)}',          # 몬스터 조우율 ×4
            f'chk 35 2f 05 01 00 05 30 10 {ext(*holy)}',         # 성수: 선두 9 > 구역 7, 표 HOLY[1] = 80
            f'chk 05 06 05 01 00 05 2d 10 {ext(*dungeon)}')      # 맵 안은 지형 배수 0F
        self.assertEqual([l for l in out if l.startswith('다름')], [])
        self.assertTrue(out[-1].endswith('판정 3번(전투 조건이 맞은 것 3번), 전투 0번, 다름 0'))

    def test_merchant_without_group_selection(self):
        ext = '0 0 0 2 0 0 0 0 0 0 0'
        ok, out, path = self.check('chk 35 2f 00 00 00 05 08 00 ' + ext,
                                   'enc 1 35 2f 00 01 00 -1 ad ff ff ff 01 00 00 00 ' + ext)
        self.assertTrue(ok)
        self.assertEqual(out[-1], f'{path}: 판정 1번(전투 조건이 맞은 것 1번), 전투 1번(たびのしょうにん 1번), 다름 0')

    def test_enc_with_wrong_monster_is_reported(self):
        ok, out, _ = self.check(self.CHK, self.ENC.replace('0 10 ff', '0 11 ff'))
        self.assertFalse(ok)
        self.assertTrue(any(l.startswith('다름 enc') for l in out))

    def test_enc_with_too_many_monsters_is_reported(self):
        ok, out, _ = self.check(self.CHK, self.ENC.replace('01 00 00 00', '02 00 00 00'))
        self.assertFalse(ok)

    def test_boss_lines(self):
        ok, out, _ = self.check('boss 0 02 30 ff ff ff 01 00 00 00 c0', 'boss 0 ff 30 ff ff ff 01 00 00 00 c0')
        self.assertTrue(ok)
        self.assertEqual(out[0], '이벤트 특수 전투 boss 0 ff 30 ff ff ff 01 00 00 00 c0: 번호 02')
        self.assertTrue(out[-1].endswith('특수 전투 2번, 다름 0'))

    def test_boss_mismatch_and_missing_flag_bits(self):
        ok, out, _ = self.check('boss 0 02 30 ff ff ff 02 00 00 00 c0', 'boss 0 02 30 ff ff ff 01 00 00 00 40')
        self.assertEqual(sum(l.startswith('다름') for l in out), 2)
        self.assertFalse(ok)

    def test_e44_tally_after_enc(self):
        ok, out, _ = self.check(self.CHK, self.ENC, 'e44 0 1 1', 'e44 0 1 1')
        self.assertTrue(ok)
        self.assertIn('$6E44(k=1): 보통 0 기습 1 선제 0  (기대 /256: [8, 0, 248])', out)

    def test_e44_out_of_range(self):
        _, out, _ = self.check(self.CHK, self.ENC, 'e44 0 3 1')
        self.assertIn('다름 e44 0 3 1: $6E44 는 0~2', out)

    def test_group_3a_toggle_steps(self):
        step = 'stp 80 3a 00 05 06 80'
        ok, out, _ = self.check(step, 'c55 05 06 10', step)
        self.assertEqual([l for l in out if l.startswith('다름')], [])
        self.assertTrue(out[-1].endswith('판정 0번과 $627D 판정 1번(전투 조건이 맞은 것 1번), 전투 0번, 그룹 3A 걸음 1번, 다름 0'))

    def test_group_3a_missing_judgement_is_reported(self):
        step = 'stp 80 3a 00 05 06 80'
        _, out, _ = self.check(step, step)
        self.assertTrue(any(l.startswith('다름 그룹 3A 걸음') and '판정 False' in l for l in out))

    def test_group_3a_wrong_bit7_is_reported(self):
        _, out, _ = self.check('stp 80 3a 00 05 06 80', 'c55 05 06 10', 'stp 80 3a 00 05 06 00')
        self.assertTrue(any(l.startswith('다름 그룹 3A 걸음') and 'bit7 1' in l for l in out))


def consistent_prg():
    """check_tables 의 경계 조건을 모두 만족하는 합성 표."""
    prg = enc_prg()
    put(en.FORMATION, word(0x8A50), prg)
    put(0x8004, word(0x8AB0), prg)                 # 뱅크 18 함수 02 의 주소
    put(en.BOSS, word(0xA34C), prg)
    put(en.ZONE_MAPS[0], word(0xA4BD), prg)
    put(en.ZONE_MAPS[4], word(0xA5BD), prg)
    put(en.ZONE_MAPS[2], word(0xA6BD), prg)
    put(en.DUNGEON, word(0xA73D), prg)
    put(en.DUNGEON5, word(0xA73E), prg)
    put(0xA73D, [0xFF, 0xFF], prg)
    put(en.GROUP_SIZE, [2], prg)
    put_bank(prg, 0x17, dq4map.GROUPS[1], word(0xA000) + word(0xA006) + [0xFF, 0xFF])
    put_bank(prg, 0x17, 0xA000, [1, 0, 0, 2, 0, 0, 0xFF])
    return prg


class CheckTablesTests(unittest.TestCase):
    def test_consistent_tables_pass(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ok = en.check_tables(consistent_prg())
        lines = out.getvalue().splitlines()
        self.assertTrue(ok)
        self.assertEqual(sum(l.startswith('같음') for l in lines), 8)
        self.assertIn('같음 구역 레코드 끝 = 고정 편성 시작: 8A50 / 8A50', lines)
        self.assertIn('그룹 크기 $A474 와 맵 표(17:$B181) 그룹별 맵 수: 73/73 같음', lines)
        self.assertEqual(lines[-1], '지도·던전 목록이 가리키는 구역 최댓값 36 (< 65)')

    def test_broken_boundary_and_group_size_are_reported(self):
        prg = consistent_prg()
        put(en.FORMATION, word(0x8A51), prg)
        put(en.GROUP_SIZE + 1, [4], prg)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ok = en.check_tables(prg)
        lines = out.getvalue().splitlines()
        self.assertFalse(ok)
        self.assertIn('다름 구역 레코드 끝 = 고정 편성 시작: 8A50 / 8A51', lines)
        self.assertIn('그룹 크기 $A474 와 맵 표(17:$B181) 그룹별 맵 수: 72/73 같음, 다름 [\'01\']', lines)

    def test_zone_beyond_table_fails(self):
        prg = consistent_prg()
        put(0xA73D, [0x00, 0x70, 0x01, 0xFF, 0xFF], prg)
        put(en.DUNGEON5, word(0xA741), prg)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertFalse(en.check_tables(prg))
        self.assertEqual(out.getvalue().splitlines()[-1], '지도·던전 목록이 가리키는 구역 최댓값 70 (< 65)')

    def test_check_command_exit_code(self):
        self.assertEqual(run_main(consistent_prg(), 'check')[1], 0)
        broken = consistent_prg()
        put(en.FORMATION, word(0x8A51), broken)
        self.assertEqual(run_main(broken, 'check')[1], 1)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.prg = world_prg()
        put_bank(self.prg, en.dq4npcblock.NPC_BANK, 0x9000,
                 [0x10, 0, 0, 0, 0x11, 5, 6, 5, 0x21, 0x07, 0x2A, 0x21, 0x09, 0])

    def test_scan_blocks_finds_command_21(self):
        n_blocks, n_cmds, bad, hits = en.scan_blocks(self.prg)
        self.assertEqual(hits, [(5, 0x9008, 7, '00/00 레코드 0 블록1'), (5, 0x900B, 9, '00/00 레코드 0 블록1')])
        self.assertEqual((n_blocks, n_cmds, bad), (2, 5, 2))        # 이벤트 목록의 모르는 명령·넘치는 명령

    def test_scripts_command(self):
        out, _ = run_main(self.prg, 'scripts')
        self.assertEqual(out, ['블록 2개(본문 주소가 다른 것), 명령 5개, 못 읽은·넘친 명령 2, 명령 21 2번',
                               '05:9008 21 07  00/00 레코드 0 블록1', '05:900B 21 09  00/00 레코드 0 블록1'])

    def test_henge_table_and_command(self):
        put_bank(self.prg, *en.HENGE, [0x00, 0x0F])
        put_bank(self.prg, en.HENGE[0], en.HENGE[1] + en.HENGE_PEOPLE, [0x0F])
        table = en.henge_table(self.prg)
        self.assertEqual(len(table), 0x25 + 0x0F)
        self.assertEqual(table[1], (1, 0x0F, False))
        self.assertEqual(table[0x25], (0x25, 0x0F, True))
        out, _ = run_main(self.prg, 'henge')
        self.assertEqual(out[0], '00 그림 00 → $6297=00 사람  勇者')
        self.assertEqual(out[1], '01 그림 0F → $6297=0F 사람  맵 인물 1곳')
        self.assertEqual(out[0x25], '25 그림 0F → $6297=8F 몬스터  맵 인물 1곳')
        self.assertEqual(out[0x26], '26 그림 00 → $6297=80 몬스터  勇者')


class PngTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = enc_prg()
        put_bank(prg, 0x0F, 0xD2D6, [4])          # 필드 0 폭
        put_bank(prg, 0x0F, 0xD2D9, [4])          # 필드 0 높이
        put_bank(prg, 0x0B, 0x8000, word(0x9000))
        for y in range(8):
            put_bank(prg, 0x0B, 0x9000 + 4 * y, word(0xA000) + [0, 0])
        put_bank(prg, 0x0B, 0xA000, [0x42, 0x61])  # 칸 0~2 = 타일 2, 칸 3·4 = 타일 3

    def test_png_gray_tiles_zone_labels_and_grid(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'z.png')
            en.draw_png(self.prg, path)
            with Image.open(path) as f:
                im = f.convert('RGB')
        self.assertEqual(im.size, (1024, 1024))
        self.assertEqual(im.getpixel((15, 15)), (24, 24, 24))          # 칸 (3, 3) = 타일 3 × 8
        self.assertEqual(im.getpixel((500, 900)), (0, 0, 0))
        self.assertEqual(im.getpixel((64, 500)), (60, 60, 60))
        red = {im.getpixel((x, y)) for x in range(194, 212) for y in range(130, 144)}
        blue = {im.getpixel((x, y)) for x in range(194, 212) for y in range(162, 176)}
        self.assertTrue(any(r > 200 and g < 80 and b < 80 for r, g, b in red))        # 안티앨리어싱으로 섞인 색
        self.assertTrue(any(b > 200 and r < b // 2 for r, g, b in blue))

    def test_maps_command_png_option(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'z.png')
            out, _ = run_main(self.prg, 'maps', '--png', path)
            with Image.open(path) as f:
                self.assertEqual(f.size, (1024, 1024))
        self.assertEqual(out[-1], '# 5장 필드 1: Y < 0C 이면 구역 35, 아니면 34. 필드 3(闇の世界): 구역 36')


class CheckCommandLogTests(unittest.TestCase):
    def test_check_command_reads_log_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'enc.txt')
            with open(path, 'w') as f:
                f.write('chk 0 0 0 0 0 5 0 0\n')
            out, code = run_main(consistent_prg(), 'check', path)
            self.assertEqual(code, 0)
            self.assertEqual(out[-1], f'{path}: 판정 1번(전투 조건이 맞은 것 0번), 전투 0번, 다름 0')
            with open(path, 'w') as f:
                f.write('chk 0 0 0 0 0 5 7 0\n')
            self.assertEqual(run_main(consistent_prg(), 'check', path)[1], 1)


class MainTests(unittest.TestCase):
    def test_unknown_command_prints_nothing(self):
        out, code = run_main(enc_prg(), 'nothing')
        self.assertEqual((out, code), ([], None))


if __name__ == '__main__':
    unittest.main()
