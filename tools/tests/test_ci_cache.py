"""tools/ci_cache.py: 암호화 묶음이 평문을 담지 않고 되살아나는지, 같은 내용은 다시 저장하지 않는지, 단계 이름·칸 정리."""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import ci_cache  # noqa: E402

HAVE_AGE = all(shutil.which(x) for x in ('age', 'age-keygen', 'zstd', 'tar'))


def outputs(path):
    return dict(line.split('=', 1) for line in Path(path).read_text(encoding='utf-8').splitlines() if '=' in line)


class CiCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out = self.tmp / 'gh-out'
        self.env = mock.patch.dict(os.environ, {'RUNNER_TEMP': str(self.tmp / 'runner'),
                                                'GITHUB_OUTPUT': str(self.out)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def quiet(self, fn, *args, **kw):
        with redirect_stdout(io.StringIO()) as buf:
            fn(*args, **kw)
        return buf.getvalue()

    def test_content_hash_follows_names_and_bytes(self):
        d = self.tmp / 'd'
        (d / 'a').mkdir(parents=True)
        (d / 'a' / 'x').write_bytes(b'1')
        (d / 'guards').mkdir()
        (d / 'guards' / 'r.json').write_text('{}')
        h = ci_cache.content_hash(d)
        self.assertEqual(h, ci_cache.content_hash(d))
        self.assertNotEqual(ci_cache.content_hash(d, ('guards',)), h)
        (d / 'guards' / 'r.json').write_text('{"a": 1}')
        self.assertNotEqual(ci_cache.content_hash(d), h)
        self.assertEqual(ci_cache.content_hash(d, ('guards',)), ci_cache.content_hash(d, ('guards',)))
        self.assertIsNone(ci_cache.content_hash(self.tmp / 'none'))

    def test_labels(self):
        self.assertEqual(ci_cache.label('/x/dq4titlelayers.py', ['--out', 'o']), 'titlelayers')
        self.assertEqual(ci_cache.label('/x/dq4chapter1.py', ['messages', '--dq5']), 'chapter1-messages')
        self.assertEqual(ci_cache.label('/x/dq4chapter1.py', ['build']), 'chapter1-build')
        self.assertEqual(ci_cache.label('/x/dq4newstage.py', ['build']), 'other')

    def test_prune_drops_entries_older_than_the_mark(self):
        calls = self.tmp / 'calls'
        for name in ('old', 'new'):
            (calls / name).mkdir(parents=True)
        past = time.time() - 3600
        os.utime(calls / 'old', (past, past))
        mark = self.tmp / 'mark'
        mark.touch()
        os.utime(mark, (past + 60, past + 60))
        self.quiet(ci_cache.prune, calls, mark)
        self.assertEqual(sorted(p.name for p in calls.iterdir()), ['new'])

    def test_empty_folder_is_not_saved(self):
        self.quiet(ci_cache.pack, 'n', self.tmp / 'missing', 'p')
        self.assertEqual(outputs(self.out)['save'], 'false')

    @unittest.skipUnless(HAVE_AGE, 'age·zstd 가 없음')
    def test_roundtrip_is_encrypted_and_skips_unchanged(self):
        key = subprocess.run(['age-keygen'], capture_output=True, text=True, check=True).stdout
        os.environ['CI_ROM_AGE_KEY'] = key
        src = self.tmp / 'src'
        (src / 'calls' / 'k1').mkdir(parents=True)
        secret = b'ROM-BYTES-' * 200
        (src / 'calls' / 'k1' / 'out0').write_bytes(secret)
        (src / 'guards').mkdir()
        (src / 'guards' / 'r.json').write_text('{}')
        log = self.quiet(ci_cache.pack, 'chunk', src, 'pre', exclude=('guards',))
        # 개인 키는 가리는 줄(::add-mask::)로만 나온다
        self.assertTrue(all(line.startswith('::add-mask::') for line in log.splitlines() if 'AGE-SECRET-KEY-' in line))
        got = outputs(self.out)
        self.assertEqual(got['save'], 'true')
        self.assertEqual(got['key'], 'pre-' + ci_cache.content_hash(src, ('guards',)))
        blob = self.tmp / 'runner' / 'enc-cache' / 'chunk.age'
        self.assertNotIn(b'ROM-BYTES', blob.read_bytes())
        self.assertFalse(list((self.tmp / 'runner' / 'enc-cache').glob('age-*')), '키 파일이 남음')

        dst = self.tmp / 'dst'
        self.quiet(ci_cache.unpack, 'chunk', dst, got['key'])
        self.assertEqual((dst / 'calls' / 'k1' / 'out0').read_bytes(), secret)
        self.assertFalse((dst / 'guards').exists())
        self.out.unlink()
        self.quiet(ci_cache.pack, 'chunk', dst, 'pre')
        self.assertEqual(outputs(self.out)['save'], 'false')
        (dst / 'calls' / 'k2').mkdir()
        (dst / 'calls' / 'k2' / 'out0').write_bytes(b'2')
        self.out.unlink()
        self.quiet(ci_cache.pack, 'chunk', dst, 'pre', max_mb=1)
        self.assertEqual(outputs(self.out)['save'], 'true')

    def test_prebuilt_copies_a_matching_build_or_builds(self):
        import json
        pre = self.tmp / 'pre-ch2'
        (pre / 'title').mkdir(parents=True)
        (pre / 'dq4-ch1-full.sfc').write_bytes(b'rom')
        (pre / 'title' / 'x').write_bytes(b'1')
        (pre / ci_cache.MANIFEST).write_text(json.dumps({'commit': 'c', 'args': ['--chapter2'], 'rom': 'dq4-ch1-full.sfc',
                                                         'roms': {'dq5.sfc': 'h'}}))
        os.environ['DQ4_PREBUILT'] = str(self.tmp / 'none') + os.pathsep + str(pre)
        out = self.tmp / 'work' / 'ch2'
        out.mkdir(parents=True)
        (out / 'stale').write_bytes(b's')
        with mock.patch.object(ci_cache, 'head_commit', return_value='c'), \
                mock.patch.object(ci_cache, 'rom_digests', return_value={'dq5.sfc': 'h'}), \
                mock.patch.object(ci_cache.subprocess, 'run') as run:
            log = self.quiet(ci_cache.prebuilt, out, ['--chapter2'])
            self.assertFalse(run.called)
            self.assertEqual(sorted(p.name for p in out.iterdir()), ['dq4-ch1-full.sfc', 'title'])
            self.assertIn('dq4-ch1-full.sfc sha1=', log)
            run.return_value.returncode = 0
            self.quiet(ci_cache.prebuilt, out, [])                      # 인자가 다름
            self.assertIn('dq4build.py', str(run.call_args[0][0][1]))
        with mock.patch.object(ci_cache, 'head_commit', return_value='other'), \
                mock.patch.object(ci_cache, 'rom_digests', return_value={'dq5.sfc': 'h'}), \
                mock.patch.object(ci_cache.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.quiet(ci_cache.prebuilt, out, ['--chapter2'])           # 커밋이 다름
            self.assertTrue(run.called)

    def _build(self, name, rom=b'rom', leader=b'l'):
        out = self.tmp / name
        (out / 'leader').mkdir(parents=True)
        (out / 'dq4-ch1-full.sfc').write_bytes(rom)
        (out / 'dq4-ch1.sfc').write_bytes(b'ch1')
        (out / 'leader' / 'x.bin').write_bytes(leader)
        (out / ci_cache.MANIFEST).write_text('{"commit": "x"}')
        return out

    def test_digest_hashes_every_build_file_but_the_prebuilt_mark(self):
        doc = ci_cache.digest(self._build('a'), 'ch1', 'cold')
        self.assertEqual(sorted(doc['files']), ['dq4-ch1-full.sfc', 'dq4-ch1.sfc', 'leader/x.bin'])
        self.assertEqual((doc['variant'], doc['kind'], doc['format']), ('ch1', 'cold', ci_cache.DIGEST_FORMAT))
        self.assertNotIn('rom', str(doc['files'].values()))

    def test_verify_build_needs_every_kind_to_match_the_cold_build(self):
        cold = ci_cache.digest(self._build('cold'), 'ch1', 'cold')
        same = ci_cache.digest(self._build('cached'), 'ch1', 'cached')
        text, ok = ci_cache.verify_build([cold, same], variants=('ch1',))
        self.assertTrue(ok, text)
        bad = ci_cache.digest(self._build('shard', leader=b'other'), 'ch1', 'shard-2')
        text, ok = ci_cache.verify_build([cold, same, bad], variants=('ch1',))
        self.assertFalse(ok)
        self.assertIn('캐시 키에 빠진 입력', text)
        # 단계 표에서 다른 것은 인물 단계뿐
        self.assertRegex(text, r'\| people \| `[0-9a-f]{12}` \| \*\*[0-9a-f]{12}\*\* \|')
        self.assertRegex(text, r'\| chapter1 build \| `[0-9a-f]{12}` \| 같음 \|')
        self.assertIn('`leader/x.bin`', text)
        # 무캐시 빌드나 캐시 빌드가 빠져도, 다른 변형이 비어도 통과가 아니다
        self.assertFalse(ci_cache.verify_build([same], variants=('ch1',))[1])
        self.assertFalse(ci_cache.verify_build([cold], variants=('ch1',))[1])
        self.assertFalse(ci_cache.verify_build([cold, same])[1])
        self.assertFalse(ci_cache.verify_build([cold, dict(same, commit='other')], variants=('ch1',))[1])

    def test_load_digests_reads_only_digest_files(self):
        import json
        (self.tmp / 'd' / 'sub').mkdir(parents=True)
        (self.tmp / 'd' / 'sub' / 'a.json').write_text(json.dumps(ci_cache.digest(self._build('a'), 'ch1', 'cold')))
        (self.tmp / 'd' / 'shard-1.json').write_text('{"commit": "c", "rows": []}')
        (self.tmp / 'd' / 'bad.json').write_text('{')
        self.assertEqual([d['kind'] for d in ci_cache.load_digests(self.tmp / 'd')], ['cold'])

    def test_unpack_without_a_restored_tar(self):
        self.quiet(ci_cache.unpack, 'none', self.tmp / 'd', '')
        self.assertFalse((self.tmp / 'd').exists())

    def test_unit_slots_become_output_lines(self):
        import json
        f = self.tmp / 'slots.json'
        f.write_text(json.dumps([{'prefix': 'guard-unit-a~1of4', 'dir': '/w/u/a~1,3of4'},
                                 {'prefix': 'guard-unit-b', 'dir': '/w/u/b'}]))
        got = ci_cache.slots(f, 3)
        self.assertEqual(got, ['p0=guard-unit-a~1of4', 'd0=/w/u/a~1,3of4', 'p1=guard-unit-b', 'd1=/w/u/b', 'p2=', 'd2='])
        self.assertEqual(ci_cache.slots(self.tmp / 'none.json', 1), ['p0=', 'd0='])
        with self.assertRaises(SystemExit):
            ci_cache.slots(f, 1)
        for bad in ({'prefix': 'guard-unit-a,b', 'dir': '/d'}, {'prefix': 'x', 'dir': '/d'},
                    {'prefix': 'guard-unit-a', 'dir': '/d\nq=1'}):
            f.write_text(json.dumps([bad]))
            with self.assertRaises(SystemExit):
                ci_cache.slots(f, 1)


if __name__ == '__main__':
    unittest.main()
