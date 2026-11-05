import argparse
import hashlib
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dq4ch1walkcheck as wc


class Ch1WalkCheckTests(unittest.TestCase):
    def test_boss_patch_sets_hp_one_and_defence_zero(self):
        rom = bytearray(0x200000)
        for n in (0xE2, 0x52):
            base = wc.MONSTERS + n * 25
            rom[base + 2], rom[base + 3], rom[base + 8], rom[base + 10] = 36, 250, 0xFF, 0xFF
        patch = dict(p.split('=') for p in wc.boss_patch(rom).split(';'))
        for n in (0xE2, 0x52):
            base = wc.MONSTERS + n * 25
            for off, value in ((2, 0), (3, 1), (8, 0xBF), (10, 0xF8)):
                rom[base + off] = int(patch[f'{base + off:X}'], 16)
            self.assertEqual(rom[base + 3] | (rom[base + 10] & 7) << 8, 1)
            self.assertEqual(rom[base + 2] | (rom[base + 8] >> 6 & 1) << 8, 0)
            self.assertEqual(rom[base + 8] | 0x40, 0xFF)

    def test_segments(self):
        for segments in (wc.SEGMENTS, wc.SEGMENTS[:-2] + wc.CHAPTER2_END):
            self.check_segments(segments)
        self.assertEqual([s[0] for s in wc.SEGMENTS[-3:]], ['castle', 'king', 'ending'])

    def check_segments(self, segments):
        names = [s[0] for s in segments]
        self.assertEqual(len(names), len(set(names)))
        for name, how, arg, opt in segments:
            self.assertIn(how, ('warp', 'walk', 'ending'), name)
            for k in (*opt.get('want', ()), *opt.get('off', ())):
                self.assertIn(k, wc.FLAGS, name)
            if how == 'walk':
                for tok in arg.split(';'):
                    self.assertRegex(tok, r'^(\d+,\d+|[a-z]+:\d+)$', name)

    def test_units_split_at_warps(self):
        for segments in (wc.SEGMENTS, wc.SEGMENTS[:-2] + wc.CHAPTER2_END):
            groups = wc.units(segments)
            self.assertEqual(groups[0], [0])
            self.assertEqual([i for u in groups for i in u], list(range(len(segments))))
            for u in groups[1:]:
                self.assertTrue(all(segments[i][1] != 'warp' for i in u[1:]))
                self.assertTrue(segments[u[0]][1] == 'warp' or u[0] == 1)
        names = [[wc.SEGMENTS[i][0] for i in u] for u in wc.units(wc.SEGMENTS)]
        self.assertIn(['castle_town', 'field', 'fly', 'kidnap'], names)
        self.assertIn(['castle', 'king', 'ending'], names)
        # 실제 계단으로 걸어 들어가는 구간: 순간이동은 계단 옆까지, 영역 이동은 걷는 구간이 한다
        self.assertIn(['jail_gate', 'jail', 'reunion'], names)
        self.assertIn(['imuru_gate', 'imuru', 'homecoming'], names)
        seg = {x[0]: x for x in wc.SEGMENTS}
        self.assertEqual((seg['jail'][1], seg['jail'][3]['map']), ('walk', '37/02'))
        self.assertEqual((seg['imuru'][1], seg['imuru'][3]['map']), ('walk', '37/00'))

    def test_setup_carries_flags_and_effects(self):
        names = [s[0] for s in wc.SEGMENTS]
        extra, party = wc.setup(wc.SEGMENTS, names.index('castle'))
        sets = extra.split(';')
        for k in ('CHAPTER1', 'HOIMIN', 'BOSS_WON', 'SOLDIER'):
            addr, mask = wc.FLAGS[k]
            self.assertIn(f'{addr & 0xFFFF:04X}|{mask:02X}', sets, k)
        addr, mask = wc.FLAGS['KIDS_FOLLOW']
        self.assertNotIn(f'{addr & 0xFFFF:04X}|{mask:02X}', sets)   # homecoming 이 끔
        self.assertIn('2058=CD', sets)
        self.assertIn('29EF|01', sets)
        self.assertEqual(party, '05')
        self.assertEqual(wc.setup(wc.SEGMENTS, names.index('hoimin_side')), (
            ';'.join(f'{wc.FLAGS[k][0] & 0xFFFF:04X}|{wc.FLAGS[k][1]:02X}'
                     for k in ('CHAPTER1', 'NIGHT_TOLD', 'FLARE', 'REUNITED')), ''))
        self.assertEqual(wc.setup(wc.SEGMENTS, 0), ('', ''))

    def test_pins_fix_rng_and_time(self):
        self.assertEqual(wc.pins({}), wc.RNG + ';' + wc.DAY_SET)
        self.assertEqual(wc.pins({'poke': wc.NIGHT + ';' + wc.HOLD_CHILD}), wc.RNG + ';' + wc.NIGHT_SET)
        self.assertEqual({a for a, _ in (p.split('=') for p in wc.RNG.split(';'))}, {'075B', '075C', '075D'})

    def test_seed_zero_is_the_fixed_rng(self):
        self.assertEqual(wc.rng_for(0), '075B=00;075C=00;075D=00')
        self.assertEqual(wc.pins({}, 0), wc.pins({}))

    def test_seed_values_are_deterministic(self):
        for seed in (1, 2, 16, 123456):
            text = wc.rng_for(seed)
            self.assertEqual(text, wc.rng_for(seed))
            self.assertRegex(text, r'^075B=[0-9A-F]{2};075C=[0-9A-F]{2};075D=[0-9A-F]{2}$')
            self.assertTrue(wc.pins({}, seed).startswith(text + ';'))
        # 바뀌면 이미 기록한 시드 결과와 견줄 수 없으므로 값을 묶어 둔다
        self.assertEqual(wc.rng_for(1), '075B=44;075C=20;075D=82')
        self.assertEqual(wc.rng_for(2), '075B=1C;075C=2E;075D=2B')
        self.assertGreater(len({wc.rng_for(s) for s in range(32)}), 30)

    def test_seed_args(self):
        ap = argparse.ArgumentParser()
        wc.add_seed_args(ap)
        self.assertEqual(wc.seeds_of(ap.parse_args([])), [0])
        self.assertEqual(wc.seeds_of(ap.parse_args(['--seed', '7'])), [7])
        self.assertEqual(wc.seeds_of(ap.parse_args(['--seeds', '0,5,9,5'])), [0, 5, 9])
        self.assertFalse(ap.parse_args([]).no_state_cache)
        with self.assertRaises(SystemExit):
            wc.seeds_of(ap.parse_args(['--seeds', '-1']))
        out = Path('o')
        self.assertEqual(wc.seed_dir(out, 3, [3]), out)
        self.assertEqual(wc.seed_dir(out, 3, [0, 3]), out / 'seed-3')

    def test_state_cache_key_is_rom_sha1(self):
        rom = bytes(range(256)) * 4
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = wc.StateCache(rom, root)
            self.assertEqual(cache.folder, root / 'prologue' / hashlib.sha1(rom).hexdigest())
            self.assertIsNone(cache.get('prologue', 'k1', '.mss'))
            src = root / 'end.mss'
            src.write_bytes(b'state')
            stored = cache.put('prologue', 'k1', '.mss', src, {'name': 'prologue', 'status': 'passed'})
            self.assertEqual(stored, cache.folder / 'prologue-k1.mss')
            state, result = wc.StateCache(rom, root).get('prologue', 'k1', '.mss')
            self.assertEqual((state.read_bytes(), result['status']), (b'state', 'passed'))
            self.assertIsNone(cache.get('prologue', 'k2', '.mss'))
            self.assertIsNone(wc.StateCache(rom + b'\0', root).get('prologue', 'k1', '.mss'))
            self.assertEqual(sorted(f.name for f in cache.folder.iterdir()), ['prologue-k1.json', 'prologue-k1.mss'])
            # 결과 .json 이 없으면 상태를 반쯤 쓴 것으로 본다
            (cache.folder / 'prologue-k1.json').unlink()
            self.assertIsNone(cache.get('prologue', 'k1', '.mss'))
            self.assertEqual(wc.fingerprint('a', src), wc.fingerprint('a', src))
            src.write_bytes(b'other')
            self.assertNotEqual(wc.fingerprint('a', src), wc.fingerprint('a', b'state'.decode()))
            self.assertNotEqual(wc.fingerprint('a', src), wc.fingerprint('b', src))

    def test_state_cache_hit_copies_to_walk_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = wc.StateCache(b'rom', root / 'states')
            src = root / 'src.mss'
            src.write_bytes(b'state')
            cache.put('prologue', 'k', '.mss', src, {'status': 'passed'})
            dest = root / 'out' / 'prologue' / 'end.mss'
            state, _ = cache.get('prologue', 'k', '.mss', dest)
            self.assertEqual((state, dest.read_bytes()), (dest, b'state'))

    def test_prologue_files_cover_warp_and_lua(self):
        files = set(wc.prologue_files())
        import dq5exitcheck
        for f in (wc.WARP, wc.WALK, wc.WALK_STATE, wc.pc.MKSTATE, Path(dq5exitcheck.__file__), wc.ROOT / 'uv.lock'):
            self.assertIn(f, files)

    def test_lua_env_covers_what_launched_lua_reads(self):
        # 검사가 띄우는 저장소 Lua 가 새 환경 변수를 읽기 시작하면 LUA_ENV 에도 더해야 셸 값이 새지 않는다
        for f in (wc.WALK, wc.WALK_STATE, wc.WARP, wc.MSG, wc.pc.MKSTATE):
            names = set(re.findall(r'getenv\([\'"]([A-Z_0-9]+)', f.read_text(encoding='utf-8'))) - {'LIBDIR'}
            self.assertLessEqual(names, wc.LUA_ENV, f.name)

    def test_run_drops_shell_lua_env(self):
        seen = {}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {'SEQ': 'y@1:2', 'HOLD': '9', 'KEEP': '1'}), \
                mock.patch.object(wc.mesen, 'run', lambda *a, **kw: seen.update(kw['env']) or mock.Mock(returncode=0)):
            wc.run(Path('mesen'), Path('rom'), Path('x.lua'), Path(tmp), {'STATE': 's'}, 1)
        self.assertNotIn('SEQ', seen)
        self.assertNotIn('HOLD', seen)
        self.assertEqual((seen['KEEP'], seen['STATE']), ('1', 's'))

    def test_prologue_key_covers_inputs(self):
        before = wc.prologue_inputs()
        self.assertIn(wc.PROLOGUE_START['SEQ'], before)
        self.assertIn(wc.RNG, before)
        old = wc.PROLOGUE_START['TAPUNTIL']
        try:
            wc.PROLOGUE_START['TAPUNTIL'] = old + '0'
            self.assertNotEqual(wc.prologue_inputs(), before)
        finally:
            wc.PROLOGUE_START['TAPUNTIL'] = old

    def test_trace_ignores_repeated_warp_end(self):
        once = 'f00002 anywhere\nf00259 end map 37/00\nflags 7E2190: 00\n'
        twice = once + 'f00260 end map 37/00\nflags 7E2190: 00\n'
        self.assertEqual(wc.trace_text('warp.txt', twice), once)
        self.assertEqual(wc.trace_text('walk.txt', twice), twice)

    def test_frames_cover_presses(self):
        self.assertEqual(wc.frames('a:8;wait:50;3,4'), 300 + 58 + 400)


class MessageBaselineTests(unittest.TestCase):
    def test_order_keeps_first_appearance(self):
        self.assertEqual(wc.message_order(['E79', 'E90', 'E7A', 'E90', 'E79', '129']), ['E79', 'E90', 'E7A', '129'])

    def test_problems(self):
        base = {('chapter1', 0, 'flare'): {'messages': ['E65', '129'], 'reason': 'x'}}
        ok = {'name': 'flare', 'messages': ['E65', '129', '129']}
        self.assertEqual(wc.message_problems('chapter1', 0, ok, base), [])
        lost = wc.message_problems('chapter1', 0, {'name': 'flare', 'messages': ['129']}, base)
        self.assertIn('빠짐 E65', lost[0])
        swap = wc.message_problems('chapter1', 0, {'name': 'flare', 'messages': ['129', 'E65']}, base)
        self.assertIn('기준 E65 129, 실제 129 E65', swap[0])
        self.assertIn('더함 E66', wc.message_problems('chapter1', 0, {'name': 'flare', 'messages': ['E65', 'E66', '129']},
                                                       base)[0])
        self.assertEqual(wc.message_problems('chapter1', 0, {'name': 'jail', 'messages': []}, base),
                         ['메시지 기준 없음(chapter1, 시드 0)'])
        # 기준이 없는 변형·시드와 메시지를 모으지 않는 구간(ending)은 보지 않는다
        self.assertEqual(wc.message_problems('chapter2', 0, ok, base), [])
        self.assertEqual(wc.message_problems('chapter1', 5, ok, base), [])
        self.assertEqual(wc.message_problems('chapter1', 0, {'name': 'ending'}, base), [])
        # 기본 변형·시드는 기준이 비면 조용히 꺼지지 않고 실패한다
        self.assertEqual(wc.message_problems('chapter1', 0, ok, {}), ['메시지 기준 없음(chapter1, 시드 0)'])
        self.assertEqual(wc.message_problems('chapter1', 0, {'name': 'flare', 'messages': ['E65', 'truncated']}, base),
                         ['메시지 기록이 400개를 넘어 잘림'])

    def test_warp_messages_after_arrival(self):
        # 맵 번호가 목적지와 처음 같아진 프레임(map@)부터 본다
        self.assertEqual(wc.warp_messages('E10@50\nmap@120\nE66@120\nE67@200\n'), ['E66', 'E67'])
        self.assertEqual(wc.warp_messages('E10@50\n'), ['E10'])
        self.assertEqual(wc.warp_messages('map@100\nE66@130\ntruncated\n'), ['E66', 'truncated'])

    def test_hand_edit_is_caught(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'm.toml'
            wc.write_messages([('chapter1', 0, 'flare', ['E65', '129'])], '처음', path)
            text = path.read_text(encoding='utf-8')
            path.write_text(text.replace('"E65", "129"', '"E65"'), encoding='utf-8')
            with self.assertRaises(ValueError):
                wc.load_messages(path)
            path.write_text(text.replace('reason = "처음"', 'reason = " "'), encoding='utf-8')
            with self.assertRaises(ValueError):
                wc.load_messages(path)
            # 손으로 고친 기준도 --write-messages 로 다시 만들 수 있다(고친 항목은 앞 까닭 없이 새 까닭)
            path.write_text(text.replace('"E65", "129"', '"E65"'), encoding='utf-8')
            wc.write_messages([('chapter1', 0, 'flare', ['E65', '129'])], '다시 만듦', path)
            self.assertEqual(wc.load_messages(path)['chapter1', 0, 'flare'], {'messages': ['E65', '129'], 'reason': '다시 만듦'})
            with self.assertRaises(ValueError):
                wc.write_messages([('chapter1', 0, 'flare', ['E65'])], '  ', path)
            with self.assertRaises(ValueError):
                wc.write_messages([('chapter1', 0, 'flare', ['E65', 'truncated'])], '잘림', path)

    def test_write_messages_cli_rejects(self):
        for argv in (['--write-messages', ''], ['--write-messages', '   '], ['--write-messages', 'x', '--chapter2'],
                     ['--write-messages', 'x', '--seed', '5'], ['--write-messages', 'x', '--seeds', '0,5'],
                     ['--write-messages', 'x', '--units', '--only', 'castle_day'], ['--write-messages', 'x', '--until', 'jail'],
                     ['--write-messages', 'x', '--from', 'jail'], ['--write-messages', 'x', '--msg-limit', '1']):
            with mock.patch.object(wc.sys, 'argv', ['dq4ch1walkcheck.py', '--rom', 'r', '--out', 'o', *argv]), \
                    mock.patch('sys.stderr'), self.assertRaises(SystemExit) as e:
                wc.main()
            self.assertEqual(e.exception.code, 2, argv)

    def test_write_keeps_reason_of_unchanged(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'm.toml'
            wc.write_messages([('chapter1', 0, 'flare', ['E65', '129']), ('chapter1', 0, 'jail', [])], '처음', path)
            wc.write_messages([('chapter1', 0, 'flare', ['E65', '129', '129']), ('chapter1', 0, 'jail', ['E66'])],
                              '감옥 대사', path)
            got = wc.load_messages(path)
        self.assertEqual(got['chapter1', 0, 'flare'], {'messages': ['E65', '129'], 'reason': '처음'})
        self.assertEqual(got['chapter1', 0, 'jail'], {'messages': ['E66'], 'reason': '감옥 대사'})

    def test_msg_limit_is_a_constant_in_the_prologue_key(self):
        self.assertEqual(wc.MSG_LIMIT, 400)
        before = wc.prologue_inputs()
        try:
            wc.set_msg_limit(1)
            self.assertNotEqual(wc.prologue_inputs(), before)
        finally:
            wc.set_msg_limit(400)
        self.assertEqual(wc.prologue_inputs(), before)
        with mock.patch.dict(os.environ, {'DQ4_WALK_MSG_LIMIT': '1'}):
            import importlib
            self.assertEqual(importlib.reload(wc).MSG_LIMIT, 400)

    def test_baseline_file_covers_segments(self):
        base = wc.load_messages()
        names = {k[2] for k in base if k[:2] == ('chapter1', 0)}
        want = {s[0] for s in wc.SEGMENTS if s[1] != 'ending'}
        self.assertEqual(names, want)
        # load_messages 가 항목마다 reason 비공백·check 표지를 확인한다(손으로 고친 기준이면 ValueError)
        for e in base.values():
            self.assertTrue(e['reason'].strip())
            self.assertEqual(e['messages'], wc.message_order(e['messages']))



class RunFailureTests(unittest.TestCase):
    def test_readset_failure_reasons(self):
        """읽은 바이트 캐시로 돌린 실행이 끝까지 가지 못한 까닭을 글로 돌려준다. 캐시에서 펼쳤거나 0 으로 끝났으면 None."""
        import dq4readset
        self.assertIsNone(wc.run_failure({'cached': True, 'returncode': 1}, 60))
        self.assertIsNone(wc.run_failure({'cached': False, 'returncode': 0, 'timed_out': False}, 60))
        timeout = wc.run_failure({'cached': False, 'returncode': None, 'timed_out': True}, 60)
        self.assertIn('60초', timeout)
        self.assertTrue(timeout.timed_out)
        self.assertFalse(wc.run_failure({'cached': False, 'returncode': 3}, 60).timed_out)
        self.assertIn('시간 제한', wc.run_failure({'cached': False, 'returncode': dq4readset.LUA_WATCHDOG}, 60))
        self.assertIn('Lua 오류', wc.run_failure({'cached': False, 'returncode': dq4readset.LUA_ERROR}, 60))
        self.assertEqual(wc.run_failure({'cached': False, 'returncode': 3}, 60), '종료 코드 3')

    def test_segment_names_the_run_failure_when_the_segment_fails(self):
        """구간이 실패하면 MesenCE 실행 실패의 까닭을 문제에 덧붙인다. 출력으로 통과한 구간에는 덧붙이지 않는다.
        다만 읽은 바이트 캐시로 돈 실행이 시간 초과면 출력이 있어도 실패다."""
        seg = ('s', 'walk', '10,10', {'maxf': 400})
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / 's'
            dest.mkdir()
            with mock.patch.object(wc, 'run', return_value='300초 안에 끝나지 않음'):
                r = wc.segment(Path('m'), Path('r.sfc'), Path('x.mss'), dest, seg, '')
            self.assertEqual(r['status'], 'failed')
            self.assertIn('MesenCE 실행: 300초 안에 끝나지 않음', r['problems'])
            (dest / 'end.mss').write_bytes(b'x')
            with mock.patch.object(wc, 'run', return_value='종료 코드 1'):
                r = wc.segment(Path('m'), Path('r.sfc'), Path('x.mss'), dest, seg, '')
            self.assertEqual(r['status'], 'passed', r['problems'])
            with mock.patch.object(wc, 'run', return_value=wc.run_failure({'cached': False, 'timed_out': True}, 300)):
                r = wc.segment(Path('m'), Path('r.sfc'), Path('x.mss'), dest, seg, '')
            self.assertEqual(r['status'], 'failed')
            self.assertEqual(r['problems'], ['MesenCE 실행: 300초 안에 끝나지 않음'])


if __name__ == '__main__':
    unittest.main()
