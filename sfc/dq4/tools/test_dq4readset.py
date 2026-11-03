"""dq4readset: 읽은 롬 바이트 캐시의 키·찾기·저장과, 머리말 Lua·러너가 지켜야 할 규칙(롬 없이)."""
import ast
import contextlib
import json
import os
import re
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4mesen  # noqa: E402
import dq4readset as rs  # noqa: E402

HERE = Path(__file__).resolve().parent


def mss(name, payload=b'payload'):
    """MesenCE 세이브스테이트 머리 꼴: 앞 칸, 이름 길이(u32), 이름, 압축된 본문."""
    return b'MSS\x01' + b'\x00' * 40 + b'\xfb\xc9\x9c' + struct.pack('<I', len(name)) + name + b'x\x01' + payload


class PureTests(unittest.TestCase):
    def test_ranges_round_trip_and_merge(self):
        r = rs.parse_ranges('10 4\n12 4\n0 1\n20 0\n')
        self.assertEqual(r, [(0, 1), (0x10, 6)])
        self.assertEqual(rs.unpack(rs.pack(r)), r)

    def test_digest_sees_only_read_bytes(self):
        rom = bytearray(range(256)) * 4
        ranges = [(0x10, 4), (0x100, 2)]
        d = rs.digest(rom, ranges)
        outside = bytearray(rom)
        outside[0x20] ^= 0xFF
        outside[0x3FF] ^= 0xFF
        self.assertEqual(rs.digest(outside, ranges), d)
        inside = bytearray(rom)
        inside[0x101] ^= 0x01
        self.assertNotEqual(rs.digest(inside, ranges), d)
        self.assertNotEqual(rs.digest(rom[:0x101], ranges), d)

    def test_find_returns_matching_entry(self):
        rom = bytes(1024)
        other = bytearray(rom)
        other[5] = 1
        a = {'ranges': rs.pack([(0, 8)]), 'digest': rs.digest(other, [(0, 8)])}
        b = {'ranges': rs.pack([(0, 8)]), 'digest': rs.digest(rom, [(0, 8)])}
        self.assertIs(rs.find([a, b], rom), b)
        self.assertIsNone(rs.find([a], rom))

    def test_rom_shape_keeps_header_but_checksum(self):
        rom = bytearray(0x8000)
        rom[0x7FD5] = 0x20
        before = rs.rom_shape(rom)
        rom[0x7FDC:0x7FE0] = b'\x12\x34\x56\x78'
        self.assertEqual(rs.rom_shape(rom), before)
        for at in (0x7FB0, 0x7FC0, 0x7FD7, 0x7FDB, 0x7FFC, 0x7FFF):
            changed = bytearray(rom)
            changed[at] ^= 1
            self.assertNotEqual(rs.rom_shape(changed), before, hex(at))

    def test_state_hash_ignores_rom_file_name_only(self):
        a = mss(b'probe-855474adcaf4.sfc')
        b = mss(b'windowcheck-e302b892a00a.sfc')
        self.assertEqual(rs.state_hash(a), rs.state_hash(b))
        self.assertNotEqual(rs.state_hash(a), rs.state_hash(mss(b'probe-855474adcaf4.sfc', b'payloae')))

    def test_content_hash_ignores_copy_name_in_logs(self):
        a = rs.content_hash(b'load probe-0123456789ab.sfc ok', 'mesen.log')
        self.assertEqual(a, rs.content_hash(b'load windowcheck-ba9876543210.sfc ok', 'mesen.log'))
        self.assertNotEqual(a, rs.content_hash(b'load probe-0123456789ab.sfc no', 'mesen.log'))

    def test_lua_env_names(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'a.lua'
            f.write_text('local x = os.getenv("STATE") or os.getenv( \'PRE\' )\n-- getenv(NOPE)\n')
            self.assertEqual(rs.lua_env_names([f]), ['PRE', 'STATE'])

    def test_canon_env_uses_contents_not_paths(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            dest, code = d / 'dest', d / 'lua'
            dest.mkdir()
            code.mkdir()
            s1, s2 = d / 's1.mss', d / 's2.mss'
            s1.write_bytes(mss(b'probe-000000000001.sfc'))
            s2.write_bytes(mss(b'probe-000000000002.sfc'))
            names = ['SHOT_DIR', 'STATE', 'SAVE', 'LIBDIR', 'OUT', 'MISSING']
            env1 = {'SHOT_DIR': str(dest), 'STATE': str(s1), 'SAVE': 'end.mss', 'LIBDIR': str(code),
                    'OUT': str(dest / 'x.txt')}
            env2 = dict(env1, STATE=str(s2), SHOT_DIR='/elsewhere')
            (dest / 'x.txt').write_text('1')
            c1 = rs.canon_env(env1, names, dest, [code])
            self.assertEqual(c1, rs.canon_env(env2, names, dest, [code]))
            self.assertNotIn('SHOT_DIR', c1)
            self.assertEqual(c1['LIBDIR'], 'code')
            self.assertEqual(c1['OUT'], 'dest:x.txt')
            self.assertEqual(c1['SAVE'], 'end.mss')
            s2.write_bytes(mss(b'probe-000000000002.sfc', b'other'))
            self.assertNotEqual(c1, rs.canon_env(env2, names, dest, [code]))

    def test_canon_env_paths_that_do_not_exist_yet(self):
        """없는 경로를 원 문자열로 두면, 나중에 그 자리에 생긴 파일 내용이 키에 들지 않는다."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            dest, work = d / 'dest', d / 'work'
            dest.mkdir()
            work.mkdir()
            names = ['IN', 'REL', 'OUT']
            env = {'IN': str(d / 'later.bin'), 'REL': 'input.bin', 'OUT': str(dest / 'not-yet.txt')}
            c1 = rs.canon_env(env, names, dest, cwd=work)
            self.assertEqual(c1['IN'], 'absent:' + str(d / 'later.bin'))
            self.assertEqual(c1['OUT'], 'dest:not-yet.txt')
            (d / 'later.bin').write_bytes(b'1')
            (work / 'input.bin').write_bytes(b'2')
            c2 = rs.canon_env(env, names, dest, cwd=work)
            self.assertTrue(c2['IN'].startswith('file:'))
            self.assertTrue(c2['REL'].startswith('file:'))
            (work / 'input.bin').write_bytes(b'3')
            self.assertNotEqual(c2['REL'], rs.canon_env(env, names, dest, cwd=work)['REL'])
            other = d / 'other'
            other.mkdir()
            (other / 'input.bin').write_bytes(b'3')
            self.assertEqual(rs.canon_env(env, names, dest, cwd=work)['REL'],
                             rs.canon_env(env, names, dest, cwd=other)['REL'])


class StoreTests(unittest.TestCase):
    def test_keeps_recent_entries_and_prunes_unreferenced_blobs(self):
        with tempfile.TemporaryDirectory() as d:
            st = rs.Store(d)
            for i in range(rs.KEEP_ENTRIES + 3):
                st.add('k' * 64, {'ranges': rs.pack([(0, 1)]), 'digest': str(i)}, {'o': f'out{i}'.encode()})
            es = st.entries('k' * 64)
            self.assertEqual(len(es), rs.KEEP_ENTRIES)
            self.assertEqual(es[0]['digest'], str(rs.KEEP_ENTRIES + 2))
            st.touch('k' * 64, es[-1])
            self.assertEqual(st.entries('k' * 64)[0]['digest'], es[-1]['digest'])
            st.drop('k' * 64, es[-1])
            self.assertNotIn(es[-1]['digest'], [e['digest'] for e in st.entries('k' * 64)])
            st.prune(0)
            live = {s for e in st.entries('k' * 64) for s in e['files'].values()}
            blobs = {p.name for p in (Path(d) / 'blob').rglob('*') if p.is_file()}
            self.assertLessEqual(blobs, live)

    def test_touch_does_not_resurrect_pruned_entry(self):
        """맞은 항목을 읽은 뒤 prune 이 index 를 지웠으면, touch 가 옛 항목으로 다시 쓰지 않는다(blob 은 이미 없다)."""
        with tempfile.TemporaryDirectory() as d:
            st = rs.Store(d)
            hit = st.add('k' * 64, {'ranges': rs.pack([(0, 1)]), 'digest': 'a'}, {'o': b'x'})
            for p in (Path(d) / 'index').rglob('*.json'):
                p.unlink()
            st.prune(0)
            st.touch('k' * 64, hit)
            self.assertEqual(st.entries('k' * 64), [])
            with self.assertRaises(FileNotFoundError):
                st.get_blob(hit['files']['o'])

    def test_add_writes_blobs_under_the_lock(self):
        """blob 쓰기와 index 쓰기 사이에 prune 이 끼면 index 가 없는 blob 을 가리킨다. 둘 다 잠금 안에서 한다."""
        with tempfile.TemporaryDirectory() as d:
            st = rs.Store(d)
            seen = []
            real = rs._replace

            def spy(path, data):
                seen.append((Path(path).parent.parent.name, (Path(d) / '.lock').exists() and held[0]))
                real(path, data)
            held = [False]
            real_locked = rs.locked

            @contextlib.contextmanager
            def lock(root):
                with real_locked(root):
                    held[0] = True
                    try:
                        yield
                    finally:
                        held[0] = False
            with mock.patch.object(rs, '_replace', spy), mock.patch.object(rs, 'locked', lock):
                st.add('k' * 64, {'ranges': rs.pack([(0, 1)]), 'digest': 'a'}, {'o': b'x', 'p': b'y'})
            self.assertEqual(sorted(kind for kind, _ in seen), ['blob', 'blob', 'index'])
            self.assertTrue(all(under for _, under in seen))

    def test_add_rewrites_corrupt_blob(self):
        with tempfile.TemporaryDirectory() as d:
            st = rs.Store(d)
            e = st.add('k' * 64, {'ranges': rs.pack([(0, 1)]), 'digest': 'a'}, {'o': b'x'})
            st.blob_path(e['files']['o']).write_bytes(b'not zlib')
            st.add('k' * 64, {'ranges': rs.pack([(0, 1)]), 'digest': 'b'}, {'o': b'x'})
            self.assertEqual(st.get_blob(e['files']['o']), b'x')

    def test_prune_removes_leftover_temp_files(self):
        with tempfile.TemporaryDirectory() as d:
            st = rs.Store(d)
            st.add('k' * 64, {'ranges': rs.pack([(0, 1)]), 'digest': 'a'}, {'o': b'x'})
            tmp = Path(d) / 'blob' / 'ab' / '.abcd.123.deadbeef'
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(b'half')
            st.prune(0)
            self.assertFalse(tmp.exists())
            self.assertTrue((Path(d) / '.lock').exists())

    def test_corrupt_blob_reads_as_missing(self):
        with tempfile.TemporaryDirectory() as d:
            st = rs.Store(d)
            e = st.add('k' * 64, {'ranges': rs.pack([(0, 1)]), 'digest': 'a'}, {'o': b'x'})
            st.blob_path(e['files']['o']).write_bytes(b'not zlib')
            with self.assertRaises(FileNotFoundError):
                st.get_blob(e['files']['o'])


class FakeMesen:
    """mesen.run 대신: ROM 의 READ 구간을 읽고 그 바이트로 출력을 만든다(읽은 집합 밖은 결과와 무관한 장면)."""

    READ = (0x40, 0x10)

    def __init__(self):
        self.calls = 0
        self.rc = 0
        self.shot = False
        self.lua_error = False
        self.no_done = False

    def __call__(self, mesence, rom, script, folder=None, tag='probe', extra=(), env=None, stdout=None, **kw):
        self.calls += 1
        data = Path(rom).read_bytes()
        s, n = self.READ
        Path(folder, 'out.bin').write_bytes(data[s:s + n])
        Path(folder, 'end.mss').write_bytes(mss(f'probe-{self.calls:012x}.sfc'.encode(), data[s:s + 2]))
        Path(env['READSET_OUT']).write_text(f'{s:X} {n:X}\n' + ('' if self.no_done else f'{rs.DONE}\n'))
        Path(folder, rs.OUT_TMP).write_text('half-written')
        Path(folder, 'mesen.log').write_text(f'loaded {Path(rom).name}\n')
        if self.lua_error:
            Path(env['READSET_OUT'] + '.err').write_text('scene.lua:3: boom\n')
        if self.shot:
            Path(folder, 's00300.png').write_bytes(bytes([self.calls]))
        return subprocess.CompletedProcess([], self.rc)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.mesence = d / 'Mesen'
        self.mesence.write_bytes(b'emu')
        self.settings = d / 'settings.json'
        self.settings.write_text('{"Snes": {"RamPowerOnState": "Random"}}')
        (d / 'Saves').mkdir()
        self.rom = d / 'rom.sfc'
        self.rom.write_bytes(bytes(0x8000))
        self.script = d / 'scene.lua'
        self.script.write_text('local s = os.getenv("STATE")\n')
        self.store = rs.Store(d / 'cache')
        self.fake = FakeMesen()
        self.env = mock.patch.dict(os.environ, {'MESENCE_SAVES': str(d / 'Saves'), 'DQ4_READSET': '',
                                                'DQ4_READSET_VERIFY': '0'})
        self.env.start()
        self.patch = mock.patch.object(rs.mesen, 'run', self.fake)
        self.patch.start()
        self.n = 0

    def tearDown(self):
        self.patch.stop()
        self.env.stop()
        self.tmp.cleanup()

    def go(self, env=None, cwd=None):
        self.n += 1
        dest = Path(self.tmp.name) / f'run{self.n}'
        return rs.run(self.mesence, self.rom, self.script, dest, env or {'STATE': 'x'}, store=self.store,
                      cwd=cwd), dest

    def flip(self, at):
        data = bytearray(self.rom.read_bytes())
        data[at] ^= 0xFF
        self.rom.write_bytes(data)

    def test_hit_outside_miss_inside(self):
        info, d1 = self.go()
        self.assertFalse(info['cached'])
        self.assertEqual(info['readset'], 0x10)
        info, d2 = self.go()
        self.assertTrue(info['cached'])
        self.assertEqual((d2 / 'out.bin').read_bytes(), (d1 / 'out.bin').read_bytes())
        self.assertFalse((d2 / rs.ENTRY).exists() or (d2 / rs.OUT).exists())
        self.flip(0x10)        # 읽은 집합 밖
        self.assertTrue(self.go()[0]['cached'])
        self.flip(0x45)        # 안
        self.assertFalse(self.go()[0]['cached'])
        self.assertEqual(self.fake.calls, 2)

    def test_inputs_outside_rom_miss(self):
        self.go()
        self.assertTrue(self.go()[0]['cached'])
        self.assertFalse(self.go(env={'STATE': 'y'})[0]['cached'])
        self.settings.write_text('{"Snes": {"RamPowerOnState": "AllZeros"}}')
        self.assertFalse(self.go()[0]['cached'])
        self.assertFalse(self.go(cwd=self.tmp.name)[0]['cached'])

    def test_missing_settings_is_an_error(self):
        self.settings.unlink()
        empty = Path(self.tmp.name) / 'home'
        with mock.patch.object(rs.Path, 'home', return_value=empty), \
                mock.patch.dict(os.environ, {'APPDATA': str(empty), 'XDG_CONFIG_HOME': str(empty)}):
            with self.assertRaises(SystemExit):
                self.go()

    def test_failed_run_is_not_cached(self):
        self.fake.rc = 1
        self.go()
        self.fake.rc = 0
        self.assertFalse(self.go()[0]['cached'])

    def test_lua_error_with_zero_exit_is_not_cached(self):
        """testrunner 는 콜백 안 오류를 삼키고 0 으로 끝난다(실측). 머리말이 남긴 .err 가 있으면 넣지 않는다."""
        self.fake.lua_error = True
        info, dest = self.go()
        self.assertEqual(info['returncode'], rs.LUA_ERROR)
        self.assertFalse((dest / rs.ERR).exists())
        self.fake.lua_error = False
        self.assertFalse(self.go()[0]['cached'])
        self.assertTrue(self.go()[0]['cached'])

    def test_readset_without_done_line_is_not_cached(self):
        """오류를 .err 에 적지 못했어도 머리말이 끝줄을 OK 로 쓰지 않았으면 넣지 않는다."""
        self.fake.no_done = True
        info, dest = self.go()
        self.assertEqual(info['returncode'], rs.LUA_ERROR)
        self.fake.no_done = False
        self.assertFalse(self.go()[0]['cached'])

    def test_half_written_readset_is_not_an_output(self):
        info, dest = self.go()
        self.assertFalse((dest / rs.OUT_TMP).exists())
        self.assertNotIn(rs.OUT_TMP, self.store.entries(info['key'])[0]['files'])

    def test_older_entry_used_when_newer_blob_missing(self):
        """맞는 항목이 여럿이면, 앞 항목의 blob 이 없을 때 다음 항목을 본다."""
        key = self.go()[0]['key']
        self.fake.READ = (0x80, 0x10)
        with mock.patch.dict(os.environ, {'DQ4_READSET': 'off'}):
            self.go()                    # 같은 키에 읽은 구간이 다른 항목 하나 더(둘 다 지금 롬과 맞음)
        es = self.store.entries(key)
        self.assertEqual(len(es), 2)
        for sha in set(es[0]['files'].values()) - set(es[1]['files'].values()):
            self.store.blob_path(sha).unlink(missing_ok=True)
        info, dest = self.go()
        self.assertTrue(info['cached'])
        self.assertEqual(self.fake.calls, 2)
        self.assertEqual([e['digest'] for e in self.store.entries(key)], [es[1]['digest']])

    def test_missing_blob_is_a_miss(self):
        self.go()
        for f in (Path(self.tmp.name) / 'cache' / 'blob').rglob('*'):
            if f.is_file():
                f.unlink()
        info, dest = self.go()
        self.assertFalse(info['cached'])
        self.assertEqual(self.fake.calls, 2)
        self.assertTrue((dest / 'out.bin').is_file())
        self.assertTrue(self.go()[0]['cached'])

    def test_off_runs_everything(self):
        self.go()
        with mock.patch.dict(os.environ, {'DQ4_READSET': 'off'}):
            self.assertFalse(self.go()[0]['cached'])

    def test_verify_reruns_and_catches_wrong_cache(self):
        self.go()
        with mock.patch.dict(os.environ, {'DQ4_READSET_VERIFY': '1'}):
            info, _ = self.go()
            self.assertTrue(info['verified'])
            self.assertEqual(self.fake.calls, 2)
            # 키에 없는 입력이 결과를 바꾼 것처럼: 종료 코드만 달라져도 틀린 캐시로 본다
            self.fake.rc = 3
            with self.assertRaisesRegex(SystemExit, '종료 코드'):
                self.go()
            self.fake.rc = 0
            self.go()
            self.fake.READ = (0x80, 0x10)
            self.flip(0x80)
            with self.assertRaisesRegex(SystemExit, '출력'):
                self.go()

    def test_verify_does_not_trust_screenshots(self):
        """화면 찍기는 같은 실행에서도 프레임이 어긋날 수 있어 재검증이 견주지 않는다. 다른 출력은 그대로 견준다."""
        self.fake.shot = True
        self.go()
        with mock.patch.dict(os.environ, {'DQ4_READSET_VERIFY': '1'}):
            info, dest = self.go()
        self.assertTrue(info['verified'])
        self.assertEqual(info['screens_differ'], ['s00300.png'])
        self.assertEqual((dest / 's00300.png').read_bytes(), bytes([2]))
        self.assertTrue(self.go()[0]['cached'])

    def test_accept_false_is_not_cached(self):
        dest = Path(self.tmp.name) / 'rej'
        rs.run(self.mesence, self.rom, self.script, dest, {}, store=self.store, accept=lambda d: False)
        self.assertFalse(self.go()[0]['cached'])

    def test_stats_records_each_run(self):
        stats = Path(self.tmp.name) / 'stats.jsonl'
        with mock.patch.dict(os.environ, {'DQ4_READSET_STATS': str(stats)}):
            self.go()
            self.go()
        rows = [json.loads(line) for line in stats.read_text(encoding='utf-8').splitlines()]
        self.assertEqual([(r['script'], r['cached'], r['readset']) for r in rows],
                         [('scene.lua', False, 0x10), ('scene.lua', True, 0x10)])


class RuleTests(unittest.TestCase):
    def test_runner_copies_rom_so_no_battery_save_leaks(self):
        """testrunner() 는 롬을 복사하지 않아 앞 실행의 .srm 을 읽는다. 캐시 실행은 run/Runner 만 쓴다."""
        tree = ast.parse((HERE / 'dq4readset.py').read_text(encoding='utf-8'))
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                 and n.value.id == 'mesen'}
        self.assertIn('run', attrs)
        self.assertNotIn('testrunner', attrs)

    def test_scene_checks_run_through_cache(self):
        """장면형 검사가 MesenCE 를 직접(testrunner·mesen.run) 띄우면 캐시도 .srm 막이도 비껴간다."""
        for name in ('dq4signcheck.py', 'dq4battlemsgcheck.py', 'dq4chestcheck.py', 'dq4namegamecheck.py',
                     'dq4wellresetcheck.py'):
            tree = ast.parse((HERE / name).read_text(encoding='utf-8'))
            calls = {(n.func.value.id, n.func.attr) for n in ast.walk(tree) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)}
            self.assertIn(('dq4readset', 'run'), calls, name)
            self.assertFalse({c for c in calls if c[0] in ('dq4mesen', 'mesen')}, name)

    def test_screen_rule(self):
        """재검증·건전성 검사가 견주지 않는 출력은 화면 찍기(.png)뿐이다. 덤프·상태·글 기록은 그대로 견준다."""
        want = {'s00300.png': 'a', 'v00300.bin': 'a', 'msg.txt': 'a', 'end.mss': 'a', 'sub/end.png': 'a'}
        got = {'s00300.png': 'b', 'v00300.bin': 'b', 'msg.txt': 'b', 'end.mss': 'b', 'sub/end.png': 'b'}
        self.assertEqual(rs.differing(want, got, screens=True), ['s00300.png', 'sub/end.png'])
        self.assertEqual(rs.differing(want, got), ['end.mss', 'msg.txt', 'v00300.bin'])
        self.assertIn('출력', rs.mismatch(want, got, {'returncode': 0, 'ranges': rs.pack([(0, 1)])}, 0, [(0, 1)]))
        only_shots = dict(want, **{'s00300.png': 'b'})
        self.assertEqual(rs.mismatch(want, only_shots, {'returncode': 0, 'ranges': rs.pack([(0, 1)])}, 0, [(0, 1)]), '')

    def test_prelude_wraps_callbacks_before_its_own(self):
        """감싸기를 머리말 자신의 콜백(HDMA·endFrame)보다 먼저 건다. 반환값은 개수까지 그대로 넘긴다."""
        lua = (HERE / 'lua' / 'dq4readset.lua').read_text(encoding='utf-8')
        wrap = lua.index('emu[name] = function(fn, ...) return orig(guarded(fn), ...) end')
        first_cb = min(lua.index('emu.addMemoryCallback(function'), lua.index('emu.addEventCallback(function'))
        self.assertLess(wrap, first_cb)
        self.assertIn('return pass(pcall(fn, ...))', lua)
        self.assertIn('os.remove(out)', lua)

    def test_prelude_records_lua_errors(self):
        """머리말이 콜백을 감싸 오류를 .err 에 적고, 진입 파일이 맨 위 오류를 잡아 멈춘다."""
        lua = (HERE / 'lua' / 'dq4readset.lua').read_text(encoding='utf-8')
        self.assertIn('function READSET_FAIL', lua)
        self.assertRegex(lua, r'"addEventCallback", "addMemoryCallback"')
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(rs.mesen, 'run', return_value=subprocess.CompletedProcess([], 0)):
            seen = {}
            real = Path.write_text

            def spy(path, text, *a, **k):
                if path.name == rs.ENTRY:
                    seen['entry'] = text
                return real(path, text, *a, **k)
            with mock.patch.object(Path, 'write_text', spy):
                rs._execute('m', 'r.sfc', Path(d) / 's.lua', Path(d), {}, 1, (), 'log.txt', None, 'probe')
        self.assertIn('pcall(dofile', seen['entry'])
        self.assertIn('READSET_FAIL(e); emu.stop(1)', seen['entry'])

    def test_readset_users_do_not_judge_from_screenshots(self):
        """흔한 꼴만 막는 정적 휴리스틱이다(변수에 담은 이름, 다른 모듈을 거친 읽기는 못 본다): 이 캐시를 쓰는 검사에서
        PIL 로 여는 것은 모음 그림을 만드는 sheet* 함수 안에서만, 화면 파일 이름 글자를 open()·read_bytes() 등으로
        직접 읽지 않는다. 재검증이 화면을 견주지 않는다는 동작은 RunTests 와 test_screen_rule 이 직접 본다."""
        users = [p for p in sorted(HERE.glob('dq4*.py'))
                 if p.name not in ('dq4readset.py',) and re.search(
                     r'^\s*import dq4readset\b|^\s*import dq4groupcheck\b|^\s*from dq4groupcheck import .*\b(field_)?scene\b'
                     r'|readset=True', p.read_text(encoding='utf-8'), re.M)]
        self.assertIn('dq4windowcheck.py', [p.name for p in users])
        self.assertIn('dq4fieldtravelcheck.py', [p.name for p in users])
        self.assertIn('dq4heroblockcheck.py', [p.name for p in users])
        # (파일, 함수): 화면을 견주지만 그 화면을 만드는 실행은 캐시를 거치지 않는다
        allowed = {('dq4battlecheck.py', 'same_pixels')}
        bad = []
        for p in users:
            tree = ast.parse(p.read_text(encoding='utf-8'))
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.Module)):
                    continue
                if isinstance(fn, ast.FunctionDef) and (fn.name.startswith('sheet') or (p.name, fn.name) in allowed):
                    continue
                body = fn.body if isinstance(fn, ast.Module) else fn.body
                for node in (n for stmt in body for n in ast.walk(stmt)
                             if not isinstance(stmt, ast.FunctionDef)):
                    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                        continue
                    f = node.func
                    if isinstance(f.value, ast.Name) and f.value.id == 'Image' and f.attr == 'open':
                        bad.append(f'{p.name}:{node.lineno} Image.open')
                    if f.attr in ('read_bytes', 'read_text', 'open') and any(
                            isinstance(c, ast.Constant) and isinstance(c.value, str) and c.value.endswith(rs.SCREENS)
                            for c in ast.walk(node)):
                        bad.append(f'{p.name}:{node.lineno} {f.attr}')
        self.assertEqual(bad, [])

    def test_battle_rounds_bypass_cache(self):
        """전투 검사는 같은 상태에서 전투를 여러 번 돌려 결과가 같은지 보고 화면을 견준다. 그 전투 실행은 캐시를 거치지 않는다
        (거치면 둘째 실행이 첫 실행의 사본이 된다)."""
        tree = ast.parse((HERE / 'dq4battlecheck.py').read_text(encoding='utf-8'))
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'run_scene')
        runs = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == 'run' and isinstance(n.func.value, ast.Name) and n.func.value.id == 'wc']
        self.assertTrue(runs)
        for n in runs:
            self.assertFalse([k for k in n.keywords if k.arg == 'readset' and getattr(k.value, 'value', False)])

    def test_clear_saves_removes_cdl(self):
        with tempfile.TemporaryDirectory() as d:
            saves, dbg = Path(d) / 'Saves', Path(d) / 'Debugger'
            saves.mkdir()
            dbg.mkdir()
            (saves / 'probe-0123456789ab.srm').write_bytes(b'')
            (dbg / 'probe-0123456789ab.cdl').write_bytes(b'')
            (dbg / 'keep.cdl').write_bytes(b'')
            with mock.patch.dict(os.environ, {'MESENCE_SAVES': str(saves)}):
                dq4mesen.clear_saves('x/probe-0123456789ab.sfc')
            self.assertEqual(sorted(p.name for p in dbg.iterdir()), ['keep.cdl'])
            self.assertEqual(list(saves.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
