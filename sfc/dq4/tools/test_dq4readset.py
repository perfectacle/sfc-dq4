"""dq4readset: 읽은 롬 바이트 캐시의 키·찾기·저장과, 머리말 Lua·러너가 지켜야 할 규칙(롬 없이)."""
import ast
import json
import os
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


class StoreTests(unittest.TestCase):
    def test_keeps_recent_entries_and_prunes_unreferenced_blobs(self):
        with tempfile.TemporaryDirectory() as d:
            st = rs.Store(d)
            for i in range(rs.KEEP_ENTRIES + 3):
                sha = st.put_blob(f'out{i}'.encode())
                st.add('k' * 64, {'ranges': rs.pack([(0, 1)]), 'digest': str(i), 'files': {'o': sha}})
            es = st.entries('k' * 64)
            self.assertEqual(len(es), rs.KEEP_ENTRIES)
            self.assertEqual(es[0]['digest'], str(rs.KEEP_ENTRIES + 2))
            st.touch('k' * 64, es[-1])
            self.assertEqual(st.entries('k' * 64)[0]['digest'], es[-1]['digest'])
            st.drop('k' * 64, es[-1])
            self.assertNotIn(es[-1]['digest'], [e['digest'] for e in st.entries('k' * 64)])
            old = time.time() - rs.BLOB_GRACE - 10
            for f in (Path(d) / 'blob').rglob('*'):
                os.utime(f, (old, old))
            young = st.put_blob(b'just written, not in any index yet')
            st.prune(0)
            self.assertTrue(st.blob_path(young).exists())
            os.utime(st.blob_path(young), (old, old))
            st.prune(0)
            live = {s for e in st.entries('k' * 64) for s in e['files'].values()}
            blobs = {p.name for p in (Path(d) / 'blob').rglob('*') if p.is_file()}
            self.assertLessEqual(blobs, live)
            self.assertNotIn(young, blobs)


class FakeMesen:
    """mesen.run 대신: ROM 의 READ 구간을 읽고 그 바이트로 출력을 만든다(읽은 집합 밖은 결과와 무관한 장면)."""

    READ = (0x40, 0x10)

    def __init__(self):
        self.calls = 0
        self.rc = 0
        self.shot = False

    def __call__(self, mesence, rom, script, folder=None, tag='probe', extra=(), env=None, stdout=None, **kw):
        self.calls += 1
        data = Path(rom).read_bytes()
        s, n = self.READ
        Path(folder, 'out.bin').write_bytes(data[s:s + n])
        Path(folder, 'end.mss').write_bytes(mss(f'probe-{self.calls:012x}.sfc'.encode(), data[s:s + 2]))
        Path(env['READSET_OUT']).write_text(f'{s:X} {n:X}\n')
        Path(folder, 'mesen.log').write_text(f'loaded {Path(rom).name}\n')
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
        for name in ('dq4signcheck.py', 'dq4battlemsgcheck.py'):
            tree = ast.parse((HERE / name).read_text(encoding='utf-8'))
            calls = {(n.func.value.id, n.func.attr) for n in ast.walk(tree) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)}
            self.assertIn(('dq4readset', 'run'), calls, name)
            self.assertFalse({c for c in calls if c[0] in ('dq4mesen', 'mesen')}, name)

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
