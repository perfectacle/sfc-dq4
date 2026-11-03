"""dq4readset: 읽은 롬 바이트 캐시의 키·찾기·저장과, 머리말 Lua·러너가 지켜야 할 규칙(롬 없이)."""
import ast
import contextlib
import io
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
import zlib
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
            st.prune(1 << 40)            # 상한 아래여도 쓴다
            self.assertFalse(tmp.exists())
            self.assertTrue((Path(d) / '.lock').exists())

    def test_blob_with_other_content_reads_as_missing(self):
        """zlib 으로는 풀리지만 내용이 이름(SHA-256)과 다른 blob 은 펼치지 않는다."""
        with tempfile.TemporaryDirectory() as d:
            st = rs.Store(d)
            e = st.add('k' * 64, {'ranges': rs.pack([(0, 1)]), 'digest': 'a'}, {'o': b'x'})
            st.blob_path(e['files']['o']).write_bytes(zlib.compress(b'y'))
            with self.assertRaisesRegex(FileNotFoundError, '이름과 다름'):
                st.get_blob(e['files']['o'])

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
        self.timeout = False
        self.during = None
        self.watchdog = 0

    def __call__(self, mesence, rom, script, folder=None, tag='probe', extra=(), env=None, stdout=None, **kw):
        self.calls += 1
        if self.during:
            self.during()
        data = Path(rom).read_bytes()
        s, n = self.READ
        Path(folder, 'out.bin').write_bytes(data[s:s + n])
        Path(folder, 'end.mss').write_bytes(mss(f'probe-{self.calls:012x}.sfc'.encode(), data[s:s + 2]))
        Path(env['READSET_OUT']).write_text(f'{s:X} {n:X}\n' + ('' if self.no_done else f'{rs.DONE}\n'))
        Path(folder, rs.OUT_TMP).write_text('half-written')
        Path(folder, 'mesen.log').write_text(f'loaded {Path(rom).name}\n')
        if self.lua_error:
            Path(env['READSET_OUT'] + '.err').write_text('scene.lua:3: boom\n')
        if self.watchdog:
            self.watchdog -= 1
            Path(env['READSET_OUT'] + '.err').write_text('scene.lua:9: Maximum execution time (1 seconds) exceeded.\n')
            Path(folder, 'half.bin').write_bytes(b'cut')
        if self.shot:
            Path(folder, 's00300.png').write_bytes(bytes([self.calls]))
        if self.timeout:
            raise subprocess.TimeoutExpired('mesen', 1)
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
        """읽은 집합과 끝줄 OK 가 있어도 종료 코드가 0 이 아니면 넣지 않는다."""
        self.fake.rc = 1
        info, _ = self.go()
        self.assertEqual(info['readset'], 0x10)
        self.fake.rc = 0
        self.assertFalse(self.go()[0]['cached'])

    def test_timed_out_run_is_not_cached_and_does_not_stop(self):
        """끝줄 OK 까지 썼어도 시간이 초과되면 넣지 않고, 검사를 멈추지 않으며(SystemExit 없음), Lua 오류라 하지 않는다."""
        self.fake.timeout = True
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            info, _ = self.go()
        self.assertTrue(info['timed_out'])
        self.assertIn('끝나지 않음', err.getvalue())
        self.assertNotIn('Lua 오류', err.getvalue())
        self.fake.timeout = False
        self.assertFalse(self.go()[0]['cached'])

    def test_callback_watchdog_is_a_clear_failure(self):
        """MesenCE 가 콜백을 시간 제한으로 끊은 실행은 다시 돌리지 않고 종료 코드 71 로 알리며 넣지 않는다."""
        self.fake.watchdog = 1
        with contextlib.redirect_stderr(io.StringIO()) as err:
            info, _ = self.go()
        self.assertEqual((info['returncode'], self.fake.calls), (rs.LUA_WATCHDOG, 1))
        self.assertIn('시간 제한', err.getvalue())
        self.assertFalse(self.go()[0]['cached'])

    def test_verify_run_that_fails_keeps_entry(self):
        """재검증으로 다시 돌린 실행이 0 이 아닌 값(시간 제한 71, MesenCE 가 죽은 134, emu.stop(3))이나 시간 초과로
        끝나면, 출력을 견주지 않고 그 실패로 알리며 항목은 둔다."""
        key = self.go()[0]['key']
        with mock.patch.dict(os.environ, {'DQ4_READSET_VERIFY': '1'}):
            self.fake.watchdog = 1
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaisesRegex(SystemExit, '실패함'):
                self.go()
            for rc in (134, 3):
                self.fake.rc = rc
                with contextlib.redirect_stderr(io.StringIO()), \
                        self.assertRaisesRegex(SystemExit, f'실패함\\(종료 코드 {rc}\\)'):
                    self.go()
            self.fake.rc = 0
            self.fake.timeout = True
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaisesRegex(SystemExit, '끝나지 않음'):
                self.go()
        self.assertEqual(len(self.store.entries(key)), 1)

    def test_zero_exit_without_readset_is_a_failure(self):
        """0 으로 끝났는데 읽은 집합 파일이 없으면(머리말이 쓰지 못함) 실패로 본다."""
        real = self.fake.__call__

        def drop(*a, **k):
            r = real(*a, **k)
            Path(k['env']['READSET_OUT']).unlink()
            return r
        with mock.patch.object(rs.mesen, 'run', drop), contextlib.redirect_stderr(io.StringIO()):
            info, _ = self.go()
        self.assertEqual(info['returncode'], rs.LUA_ERROR)

    def test_runs_the_rom_bytes_the_key_was_made_from(self):
        """키를 만든 뒤 실행 전에 롬 파일이 바뀌어도, 실행은 키를 만든 바이트의 사본으로 돈다."""
        orig = self.rom.read_bytes()

        def swap():
            self.flip(0x45)              # 읽은 구간 안
        self.fake.during = swap
        info, dest = self.go()
        self.fake.during = None
        self.assertEqual((dest / 'out.bin').read_bytes(), orig[0x40:0x50])
        self.assertFalse((dest / rs.ROM_COPY).exists())
        self.rom.write_bytes(orig)
        self.assertTrue(self.go()[0]['cached'])

    def test_leftover_tmp_in_dest_does_not_change_key(self):
        a, _ = self.go()
        self.n += 1
        dest = Path(self.tmp.name) / f'run{self.n}'
        dest.mkdir()
        (dest / rs.OUT_TMP).write_text('left by a killed run')
        (dest / rs.ROM_COPY).write_bytes(b'left')
        b = rs.run(self.mesence, self.rom, self.script, dest, {'STATE': 'x'}, store=self.store)
        self.assertEqual(a['key'], b['key'])
        self.assertTrue(b['cached'])

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


def uses_readset_run(path):
    """그 모듈이 읽은 바이트 캐시로 장면을 돌리는가: dq4readset 의 run 이나 순간이동 장면(dq4groupcheck.scene·field_scene)을
    참조하거나(부르기·값으로 넘기기, 별칭 import·from import·* 포함), readset=True 를 넘긴다."""
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    aliases = {'dq4readset': set(), 'dq4groupcheck': set()}     # 모듈 이름 별칭
    names = {'dq4readset': set(), 'dq4groupcheck': set()}       # from import 로 들인 함수 이름
    wanted = {'dq4readset': {'run'}, 'dq4groupcheck': {'scene', 'field_scene'}}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name in aliases:
                    aliases[a.name].add(a.asname or a.name)
        elif isinstance(n, ast.ImportFrom) and n.module in names:
            for a in n.names:
                if a.name == '*':
                    return True
                if a.name in wanted[n.module]:
                    names[n.module].add(a.asname or a.name)
    # 부르는 자리만이 아니라 값으로 넘기는 자리(pool.submit(scene, …), fn = g.field_scene)도 쓰는 것으로 본다
    for n in ast.walk(tree):
        for module in aliases:
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in aliases[module] \
                    and n.attr in wanted[module]:
                return True
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in names[module]:
                return True
        if isinstance(n, ast.Call) and any(k.arg == 'readset' and getattr(k.value, 'value', None) is True
                                           for k in n.keywords):
            return True
    return False


class UsesReadsetTests(unittest.TestCase):
    def test_aliases_and_from_imports(self):
        cases = {'import dq4readset as rs\nrs.run(1)\n': True,
                 'from dq4readset import run as go\ngo(1)\n': True,
                 'import dq4readset\ndq4readset.run(1)\n': True,
                 'import dq4readset\ndq4readset.warp_timed_out("")\n': False,
                 'import dq4ch1walkcheck as wc\nwc.run(1, readset=True)\n': True,
                 'from dq4groupcheck import field_scene\nfield_scene(1)\n': True,
                 'from dq4groupcheck import field_scene\n': False,
                 'from dq4groupcheck import scene\npool.submit(scene, 1)\n': True,
                 'import dq4groupcheck as g\nfn = g.field_scene\n': True,
                 'from dq4readset import run as go\njobs = [go]\n': True,
                 'import dq4groupcheck\ndq4groupcheck.scene(1)\n': True,
                 'import dq4groupcheck as g\ng.same_place(1)\n': False,
                 'from dq4readset import *\n': True,
                 'from dq4groupcheck import *\n': True,
                 'import os\n': False}
        with tempfile.TemporaryDirectory() as d:
            for i, (src, want) in enumerate(cases.items()):
                p = Path(d, f'm{i}.py')
                p.write_text(src)
                self.assertEqual(uses_readset_run(p), want, src)


class SceneTests(unittest.TestCase):
    """dq4groupcheck.scene 이 run 의 결과를 보고 시간 초과·0 이 아닌 종료를 분명한 오류로 돌려준다."""

    def scene(self, info, warp=None):
        import dq4groupcheck
        with tempfile.TemporaryDirectory() as d:
            def fake(mesence, rom, script, dest, env, **kw):
                if warp is not None:
                    Path(dest, 'warp.txt').write_text(warp, encoding='utf-8')
                self.accept = kw.get('accept')
                return info
            with mock.patch.object(rs, 'run', fake), mock.patch.dict(os.environ, {'LIBDIR': d}), \
                    mock.patch.object(dq4groupcheck, 'warp_exit', return_value=0), \
                    mock.patch.object(dq4groupcheck, 'dp86_allowed', return_value='0'):
                return dq4groupcheck.scene('m', Path(d) / 'r.sfc', Path(d) / 's.mss', Path(d), 'x')

    def test_timeout_is_reported(self):
        got = self.scene({'timed_out': True, 'returncode': None})
        self.assertIn('끝나지 않음', got['error'])

    def test_missing_warp_log_is_reported(self):
        self.assertIn('warp.txt 없음', self.scene({'timed_out': False, 'returncode': 0})['error'])

    def test_nonzero_exit_is_reported(self):
        self.assertIn('종료 코드 3', self.scene({'timed_out': False, 'returncode': 3})['error'])

    def test_warp_that_hit_maxf_is_an_error(self):
        """MAXF 에 닿아도 종료 코드는 0 이고 「end map」 이 찍힌다. 저장만 막지 않고 판정에도 실패로 돌려준다."""
        got = self.scene({'timed_out': False, 'returncode': 0},
                         'f02400 timeout phase=warp\nf02400 end map 36/00 cell 5,6 BE=80 1949=00\n')
        self.assertIn('MAXF', got['error'])
        self.assertIs(self.accept, rs.warp_finished)
        ok = self.scene({'timed_out': False, 'returncode': 0}, 'f00300 end map 36/00 cell 5,6 BE=80 1949=00\n')
        self.assertEqual(ok, {'map': '36/00', 'cell': [5, 6]})
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'warp.txt').write_text('f02400 timeout phase=warp\n')
            self.assertFalse(rs.warp_finished(d))
            Path(d, 'warp.txt').write_text('f00300 end map 36/00 cell 5,6\n')
            self.assertTrue(rs.warp_finished(d))


class WalkJudgeTests(unittest.TestCase):
    """도착한 뒤 MAXF 에 닿은 순간이동은 「arrived map」 과 「timeout phase=」 가 함께 찍힌다. 판정이 실패로 본다."""

    def run_segment(self, warp_text):
        import dq4ch1walkcheck as wc
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / 'seg'

            def fake(mesence, rom, script, dest_, env, timeout, readset=False):
                dest_.mkdir(parents=True, exist_ok=True)
                (dest_ / 'warp.txt').write_text(warp_text, encoding='utf-8')
                (dest_ / 'end.mss').write_bytes(b'MSS')
            with mock.patch.object(wc, 'run', fake), mock.patch.object(wc, 'warp_exit', return_value=0):
                return wc.segment('m', Path(d) / 'r.sfc', Path(d) / 's.mss', dest, ('x', 'warp', '36/00,10,10', {}),
                                  wc.NO_ENCOUNTERS)

    def test_timeout_after_arrival_fails(self):
        r = self.run_segment('f00431 arrived map 36/00 cell 10,10\nf01500 timeout phase=test\n'
                             'f01500 end map 36/00 cell 10,10 BE=80 1949=00\n')
        self.assertEqual(r['status'], 'failed')
        self.assertIn('순간이동이 MAXF 에 닿아 멈춤(timeout phase)', r['problems'])

    def test_finished_warp_passes(self):
        r = self.run_segment('f00431 arrived map 36/00 cell 10,10\nf00700 end map 36/00 cell 10,10 BE=80 1949=00\n')
        self.assertEqual(r['status'], 'passed', r['problems'])


TIMED_OUT = ('f00431 arrived map 01/00 cell 10,10\nf01500 timeout phase=test\n'
             'f01500 end map 01/00 cell 10,10 BE=80 1949=00\nmessages 12A\n')
FINISHED = 'f00431 arrived map 01/00 cell 10,10\nf00700 end map 01/00 cell 10,10 BE=80 1949=00\nmessages 12A\n'


class WarpLogTests(unittest.TestCase):
    """warp.txt 를 읽는 판정마다 도착 뒤 MAXF 에 닿은 장면을 실패로 본다."""

    def test_helper(self):
        self.assertTrue(rs.warp_timed_out(TIMED_OUT))
        self.assertFalse(rs.warp_timed_out(FINISHED))

    def test_bg3slot_arrival(self):
        import dq4bg3slotcheck as bg
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'warp.txt').write_text(TIMED_OUT)
            self.assertIsNone(bg.arrival_of(Path(d)))
            Path(d, 'warp.txt').write_text(FINISHED)
            self.assertIsNotNone(bg.arrival_of(Path(d)))

    def test_environment_rom_warp(self):
        import dq4environmentromcheck as er
        for log, ok in ((TIMED_OUT, False), (FINISHED, True)):
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / 'w'

                def fake(mesence, rom, script, env):
                    Path(env['SHOT_DIR'], 'warp.txt').write_text(log)
                    Path(env['SHOT_DIR'], 'x.mss').write_bytes(b'MSS')
                with mock.patch.object(er, '_run', fake), mock.patch.object(er, 'warp_exit', return_value=0), \
                        mock.patch.object(er, 'dp86_allowed', return_value='0'):
                    if ok:
                        self.assertEqual(er.warp('m', 'r', 's', '01/00,1,1', out, 'x')[0], out / 'x.mss')
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'MAXF'):
                            er.warp('m', 'r', 's', '01/00,1,1', out, 'x')

    def test_save_church(self):
        import dq4ch1savecheck as sc
        for log, want in ((TIMED_OUT, (None, '순간이동이 MAXF 에 닿아 멈춤(timeout phase)')), (FINISHED, ('01/00', None)),
                          (None, (None, 'warp.txt 없음'))):
            with tempfile.TemporaryDirectory() as d:
                def fake(mesence, rom, script, dest, env, timeout, readset=False):
                    dest.mkdir(parents=True, exist_ok=True)
                    if log is not None:
                        (dest / 'warp.txt').write_text(log, encoding='utf-8')
                with mock.patch.object(sc.walk, 'run', fake), mock.patch.object(sc, 'free', return_value='s'), \
                        mock.patch.object(sc, 'warp_exit', return_value=0):
                    self.assertEqual(sc.church('m', 'r', 's', Path(d) / 'c'), want)

    def test_wrap_warp(self):
        import dq4wrapcheck as wr
        runner = wr.Run('m', Path('r.sfc'), 0x123456, {})
        for log, arrived in ((TIMED_OUT, None), (FINISHED, (1, 0))):
            with tempfile.TemporaryDirectory() as d:
                def fake(mesence, rom, script, dest, env, timeout, readset=False):
                    Path(dest).mkdir(parents=True, exist_ok=True)
                    Path(dest, 'warp.txt').write_text(log, encoding='utf-8')
                with mock.patch.object(wr.wc, 'run', fake), mock.patch.object(wr, 'warp_exit', return_value=0):
                    self.assertEqual(runner.warp(Path(d) / 'w', 's.mss', '01/00,1,1')[1], arrived)

    def test_npc_timeout_is_one_scene_failure(self):
        """main 을 실제로 돌린다(장면 실행만 가짜): 밤 인물 표 장면이 MAXF 에 닿으면 그 장면만 실패로 적히고, 낮 장면은
        판정까지 가며, 끝에 1 로 끝난다."""
        import dq4npccheck as npc
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            build, out, lib = d / 'build', d / 'out', d / 'lib'
            for p in (build, lib):
                p.mkdir()
            (build / 'groups.sfc').write_bytes(bytes(0x8000))
            (build / 'npc-layout.json').write_text(json.dumps({'lists': {'01/00': '01:8000'}}))
            (build / 'npc-report.json').write_text(json.dumps({'01/00': []}))
            (build / 'shop-report.json').write_text(json.dumps({'shops': [], 'prices': {}, 'inns': []}))
            (d / 'dq4.nes').write_bytes(b'')

            class Map:
                w = h = 4

            def scene_run(mesence, rom, state, out_, name, libdir, to, test, night, *a, **k):
                if night:
                    raise npc.WarpTimeout(f'{name}: dq5warp 가 MAXF 에 닿아 멈춤(timeout phase)')
                return bytes(0x20000), None
            argv = ['dq4npccheck.py', '--build', str(build), '--out', str(out), '--dq4', str(d / 'dq4.nes'),
                    '--jobs', '2']
            patches = [mock.patch.object(npc, 'run', scene_run), mock.patch.object(npc, 'expected_codes', return_value={}),
                       mock.patch.object(npc, 'decoder_return', return_value=None),
                       mock.patch.object(npc.ines, 'prg', return_value=b''),
                       mock.patch.object(npc, 'fc_map', return_value=(0, 0)),
                       mock.patch.object(npc.dq4block, 'Map', return_value=Map()),
                       mock.patch.object(npc, 'walkable', return_value=True),
                       mock.patch.object(npc, 'list_entries', return_value=[]),
                       mock.patch.object(npc, 'table_values', return_value={}),
                       mock.patch.object(npc, 'compare', return_value=[]),
                       mock.patch.object(npc.dq4freshstate, 'resolve', return_value=d / 's.mss'),
                       mock.patch.object(sys, 'argv', argv),
                       mock.patch.dict(os.environ, {'MESENCE': 'm', 'LIBDIR': str(lib)})]
            with contextlib.ExitStack() as stack, contextlib.redirect_stdout(io.StringIO()):
                for p in patches:
                    stack.enter_context(p)
                rc = npc.main()
            scenes = json.loads((out / 'results.json').read_text())['scenes']
        self.assertEqual(rc, 1)
        self.assertEqual(scenes['table-0100-day'], {'ok': True, 'people': 0, 'mismatch': []})
        self.assertEqual(scenes['table-0100-night'],
                         {'ok': False, 'error': 'table-0100-night: dq5warp 가 MAXF 에 닿아 멈춤(timeout phase)'})

    def test_npc_run(self):
        import dq4npccheck as npc
        for log, ok in ((TIMED_OUT, False), (FINISHED, True)):
            with tempfile.TemporaryDirectory() as d:
                def fake(mesence, rom, probe, *args, env=None, **kw):
                    Path(env['SHOT_DIR'], 'warp.txt').write_text(log, encoding='utf-8')
                with mock.patch.object(npc.dq4mesen, 'testrunner', fake), \
                        mock.patch.object(npc, 'warp_exit', return_value=0), \
                        mock.patch.object(npc, 'dp86_allowed', return_value='0'):
                    call = lambda: npc.run('m', 'r', 's', Path(d), 'x', d, '01/00,1,1', 'a:4', False)  # noqa: E731
                    if ok:
                        self.assertEqual(call()[1], [0x12A])
                    else:
                        with self.assertRaisesRegex(npc.WarpTimeout, 'MAXF'):
                            call()


class RuleTests(unittest.TestCase):
    def test_runner_copies_rom_so_no_battery_save_leaks(self):
        """소스 모양 확인: testrunner() 는 롬을 복사하지 않아 앞 실행의 .srm 을 읽는다. 캐시 실행은 run/Runner 만 쓴다."""
        tree = ast.parse((HERE / 'dq4readset.py').read_text(encoding='utf-8'))
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                 and n.value.id == 'mesen'}
        self.assertIn('run', attrs)
        self.assertNotIn('testrunner', attrs)

    def test_scene_checks_run_through_cache(self):
        """소스 모양 확인: 장면형 검사가 MesenCE 를 직접(testrunner·mesen.run) 띄우면 캐시도 .srm 막이도 비껴간다."""
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
        """소스 모양 확인: 감싸기를 머리말 자신의 콜백(HDMA)보다 먼저 건다. 반환값은 개수까지 그대로 넘긴다."""
        lua = (HERE / 'lua' / 'dq4readset.lua').read_text(encoding='utf-8')
        wrap = lua.index('emu[name] = function(fn, ...) return orig(guarded(fn), ...) end')
        first_cb = min(lua.index(k) for k in ('emu.addMemoryCallback(function', 'emu.addEventCallback(function') if k in lua)
        self.assertLess(wrap, first_cb)
        self.assertIn('return pass(pcall(fn, ...))', lua)
        # emu.stop 뒤 더 도는 프레임 수는 실행마다 달라, 그 뒤 장면 콜백을 부르면 출력이 흔들린다
        self.assertIn('if stopped then return end', lua)
        self.assertNotIn('if stopped then dump() end', lua)
        self.assertIn('pcall(os.remove, out)', lua)
        self.assertIn('local ok, e = pcall(dump)', lua)

    def test_prelude_records_lua_errors(self):
        """소스 모양 확인: 머리말이 콜백을 감싸 오류를 .err 에 적고, 진입 파일이 맨 위 오류를 잡아 멈춘다."""
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
        """소스 모양 확인: 흔한 꼴만 막는 정적 휴리스틱이다(변수에 담은 이름, 다른 모듈을 거친 읽기는 못 본다): 이 캐시를 쓰는 검사에서
        PIL 로 여는 것은 모음 그림을 만드는 sheet* 함수 안에서만, 화면 파일 이름 글자를 open()·read_bytes() 등으로
        직접 읽지 않는다. 대상은 dq4readset.run 을 부르거나 readset=True 를 넘기거나 순간이동 장면(scene)을 쓰는 모듈이다
        (warp_timed_out 처럼 도움 함수만 쓰는 모듈은 아니다). 재검증이 화면을 견주지 않는다는 동작은 RunTests 와
        test_screen_rule 이 직접 본다."""
        users = [p for p in sorted(HERE.glob('dq4*.py')) if p.name != 'dq4readset.py' and uses_readset_run(p)]
        self.assertNotIn('dq4npccheck.py', [p.name for p in users])        # 도움 함수만 쓴다
        self.assertIn('dq4windowcheck.py', [p.name for p in users])
        self.assertIn('dq4readsetcheck.py', [p.name for p in users])     # import dq4readset as rs → rs.run
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

    def test_walk_guards_watch_their_imports(self):
        """소스 모양 확인: 서장 끝 걷기·저장 검사의 실행 검사 paths 에, 명령이 부르는 진입 스크립트(빌드 스크립트 포함),
        빌드 스크립트가 하위 프로세스로 부르는 빌드 단계 스크립트, 그 각각이 바로 import 하는 dq4·dq5 모듈이 모두 있다. 모듈 파일을 찾지 못하면(옮겼거나 이름이 바뀜) 실패한다."""
        import tomllib
        checks = {c['name']: c for c in tomllib.loads((HERE.parent / 'guards.toml').read_text(encoding='utf-8'))['check']}
        root = HERE.parents[2]
        bases = (HERE, root / 'sfc' / 'dq5' / 'tools', root / 'fc' / 'dq4' / 'tools')
        for name in ('dq4-heroblock', 'dq4-field-obj-math', 'dq4-battle-check', 'dq4-wrap-routine', 'dq4-ch1-save'):
            entries = re.findall(r'((?:sfc|fc)/\S+?\.py)', checks[name]['run'])
            self.assertTrue(entries, name)
            if 'sfc/dq4/tools/dq4build.py' in entries:
                # dq4build 는 빌드 단계를 import 가 아니라 하위 프로세스로 부른다(dq4build.STAGES, script() 가 지킨다)
                import dq4build
                entries += [f'sfc/dq4/tools/{x}' for x in dq4build.STAGES]
            want = set(entries)
            for entry in entries:
                src = (root / entry).read_text(encoding='utf-8')
                for m in set(re.findall(r'^\s*(?:import|from)\s+(dq[45]\w+)', src, re.M)):
                    found = [b / f'{m}.py' for b in bases if (b / f'{m}.py').exists()]
                    self.assertTrue(found, f'{name}: {entry} 의 import {m} 파일을 찾지 못함')
                    want.add(found[0].relative_to(root).as_posix())
            self.assertFalse(want - set(checks[name]['paths']), name)

    def test_build_stages_go_through_the_list(self):
        """dq4build 가 단계 스크립트를 부르는 길은 script() 하나이고, STAGES 에 없는 이름은 거부한다.
        소스 모양 확인(빌드 파일의 글자 상수만 본다): '…py' 글자는 STAGES 의 원소이거나 step()·script() 의 첫 인자일 때만
        쓴다(pool.submit(step, '…py') 포함). 변수·f-string·문자열 이어 붙이기로 만든 이름은 이 시험이 못 본다. 그런 길은 script() 의 거부가 막는다."""
        import dq4build
        self.assertTrue(dq4build.STAGES)
        for name in ('dq4menupatch.py', 'dq4chapter1.py', 'dq4soundset.py', 'dq4people.py'):
            self.assertIn(name, dq4build.STAGES)
        self.assertEqual(dq4build.script('dq4menupatch.py'), HERE / 'dq4menupatch.py')
        with self.assertRaises(ValueError):
            dq4build.script('dq4new.py')
        for name in dq4build.STAGES:
            self.assertTrue((HERE / name).is_file(), name)
        tree = ast.parse((HERE / 'dq4build.py').read_text(encoding='utf-8'))
        allowed = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'STAGES' for t in n.targets):
                allowed |= {id(e) for e in ast.walk(n.value)}
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ('step', 'script') and n.args:
                allowed.add(id(n.args[0]))
            # pool.submit(step, '…py', …)
            if isinstance(n, ast.Call) and len(n.args) > 1 and isinstance(n.args[0], ast.Name) and n.args[0].id == 'step':
                allowed.add(id(n.args[1]))
        doc = tree.body[0].value if tree.body and isinstance(tree.body[0], ast.Expr) else None
        loose = [(n.lineno, n.value) for n in ast.walk(tree) if isinstance(n, ast.Constant) and n is not doc
                 and isinstance(n.value, str) and n.value.endswith('.py') and id(n) not in allowed]
        self.assertEqual(loose, [])

    def test_battle_rounds_bypass_cache(self):
        """소스 모양 확인: 전투 검사는 같은 상태에서 전투를 여러 번 돌려 결과가 같은지 보고 화면을 견준다. 그 전투 실행은 캐시를 거치지 않는다
        (거치면 둘째 실행이 첫 실행의 사본이 된다)."""
        tree = ast.parse((HERE / 'dq4battlecheck.py').read_text(encoding='utf-8'))
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'run_scene')
        runs = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == 'run' and isinstance(n.func.value, ast.Name) and n.func.value.id == 'wc']
        self.assertTrue(runs)
        for n in runs:
            # readset=flag 처럼 변수로 넘겨도 캐시를 거칠 수 있어, readset 키워드가 아예 없어야 한다
            self.assertFalse([k for k in n.keywords if k.arg in ('readset', None)])

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
