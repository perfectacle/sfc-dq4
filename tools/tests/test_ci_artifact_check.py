import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ci_artifact_check as cac  # noqa: E402

ROM = b'\x00ROM' * 64


class ArtifactCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / 'up'
        self.dir.mkdir()
        (self.dir / 'shard-1.json').write_text('{}')
        (self.dir / 'logs').mkdir()
        (self.dir / 'logs' / 'a.log').write_text('ok')
        self.hashes = {hashlib.sha256(ROM).hexdigest()}

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_folder_passes(self):
        self.assertEqual(cac.problems(self.dir, self.hashes), [])

    def test_rom_suffixes_fail_in_any_case_or_layer(self):
        for name in ('x.sfc', 'X.NES', 'y.nds.gz', 'state.mss', 'p.ips', 'k.ml1', 's.sav'):
            (self.dir / 'logs' / name).write_bytes(b'1')
        found = cac.problems(self.dir, self.hashes)
        self.assertEqual(len(found), 7, found)

    def test_renamed_rom_fails_by_hash(self):
        (self.dir / 'logs' / 'innocent.log').write_bytes(ROM)
        self.assertIn('내용이 롬과 같음', '\n'.join(cac.problems(self.dir, self.hashes)))

    def test_symlink_and_big_file_fail(self):
        os.symlink('/etc/hosts', self.dir / 'link.log')
        (self.dir / 'big.log').write_bytes(b'1' * 11)
        text = '\n'.join(cac.problems(self.dir, self.hashes, max_bytes=10))
        self.assertIn('심볼릭 링크', text)
        self.assertIn('한도', text)

    def test_empty_hash_list_fails(self):
        self.assertTrue(cac.problems(self.dir, set()))

    def test_cli_reads_sha256sum_output(self):
        hashes = Path(self.tmp.name) / 'h.txt'
        hashes.write_text(f'{hashlib.sha256(ROM).hexdigest()}  dq5.sfc\n')
        self.assertEqual(cac.main([str(self.dir), '--hashes', str(hashes)]), 0)
        (self.dir / 'copy.txt').write_bytes(ROM)
        self.assertEqual(cac.main([str(self.dir), '--hashes', str(hashes)]), 1)
        self.assertEqual(cac.main([str(self.dir), '--hashes', str(Path(self.tmp.name) / 'missing')]), 1)


if __name__ == '__main__':
    unittest.main()
