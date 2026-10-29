"""블록 번호 511~1023(dq5fieldtables --blocks-at)·10번째 비트 평면(dq5fieldwrite --planes-at)·세계 1·2 시간대 벌을
원본 롬 없이 검사한다. 훅은 작은 해석기(w65816)로 돌린다."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5field  # noqa: E402
import dq5fieldtables as ft  # noqa: E402
import dq5fieldwrite as fw  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from test_dq5fieldtables import document, fixture  # noqa: E402
from w65816 import Cpu  # noqa: E402


def put(d, at, raw):
    d[lorom(at):lorom(at) + len(raw)] = raw


def apply(raw, rows, size=0x200000):
    d = bytearray(raw) + bytes(size - len(raw))
    for addr, new, _, _ in rows:
        put(d, addr, new)
    return d


def grow_fixture():
    d = bytearray(fixture())
    put(d, dq5field.BLOCK_GROW_SITE, ft.BLOCK_GROW_ORIG)
    for site in dq5field.TERRAIN_SITES:
        put(d, site, ft.TERRAIN_ORIG)
    return d


def new_blocks(n, terrain=3):
    return [{'index': i, 'lower': [i & 255, 1, 2, 3], 'upper': [0, 0, 0, i & 7], 'terrain': terrain}
            for i in range(ft.BLOCK_COUNT, n)]


class BlockGrowTests(unittest.TestCase):
    def test_grow_roundtrip_and_hook(self):
        d = grow_fixture()
        rows = ft.edits(Rom(bytes(d)), document(blocks=new_blocks(700) + [{'index': 4, 'terrain': 9}]), blocks_at=0x3C8000)
        rom = Rom(bytes(apply(d, rows)))
        self.assertEqual(dq5field.block_count(rom), 700)
        doc = ft.dump(rom)
        self.assertEqual(len(doc['blocks']), 700)
        self.assertEqual(doc['blocks'][600], {'index': 600, 'lower': [600 & 255, 1, 2, 3], 'upper': [0, 0, 0, 0],
                                              'terrain': 3})
        self.assertEqual(doc['blocks'][4]['terrain'], 9)
        self.assertEqual(sum(new != old for _, new, old, _ in ft.edits(rom, doc)), 0)
        self.assertFalse(ft.check(rom))
        # 훅: 블록 601, 칸 (1, 1)(오른쪽 아래). 00:BC52 에는 RTS 를, 00:BC47 에도 RTS 를 둔다.
        data = bytearray(rom.d)
        put(data, 0x00BC52, b'\x60')
        put(data, 0x00BC47, b'\x60')
        for block, quad, want in ((601, 3, (601 & 255, 0, 1, 0)), (511, 0, (511 & 255, 0, 0, 0)),
                                  (300, 0, None)):
            cpu = Cpu(bytes(data), bytes(0x20000))
            cpu.p = 0x30
            cpu.wram[0x90], cpu.wram[0x92] = quad & 1, quad >> 1
            cpu.a = block
            cpu.jsr(dq5field.BLOCK_GROW_SITE)
            if want is None:
                self.assertEqual(cpu.wram[0] | cpu.wram[1] << 8, 300)          # 원래 갈래: STA $00 뒤 00:BC52
                continue
            entry = [rom.u8(dq5field.block_entry(rom, u, block) + i) for u in (False, True) for i in (quad, 4)]
            self.assertEqual(tuple(cpu.wram[0x94:0x98]), (entry[0], entry[1] >> 7 - quad & 1, entry[2],
                                                          entry[3] >> 7 - quad & 1 | (entry[3] >> 3 - quad & 1) << 1))
        self.assertEqual(dq5field.terrain(rom, 650), 3)

    def test_grow_rejects(self):
        d = grow_fixture()
        rom = Rom(bytes(d))
        cases = [
            (document(blocks=new_blocks(600)), None, '--blocks-at'),
            (document(blocks=new_blocks(600)[1:]), 0x3C8000, '빈 번호'),
            (document(blocks=[{'index': 3, 'lower': [1, 1, 1, 1]}]), 0x3C8000, '511 이상'),
            (document(blocks=[{'index': 600, 'lower': [1, 1, 1, 1], 'upper': [0, 0, 0, 0]}]), 0x3C8000, 'terrain'),
            (document(blocks=new_blocks(600, terrain=16)), 0x3C8000, 'terrain'),
            (document(blocks=[{'index': 511, 'lower': [600, 1, 1, 1], 'upper': [0] * 4, 'terrain': 0}]), 0x3C8000,
             '타일'),
            (document(blocks=new_blocks(1025)), 0x3C8000, 'index'),
            (document(blocks=new_blocks(600)), 0x2F8000, '30~7D'),
            (document(blocks=new_blocks(1024)), 0x3CF000, '한 뱅크'),
        ]
        for doc, at, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                ft.edits(rom, doc, blocks_at=at)
        grown = Rom(bytes(apply(d, ft.edits(rom, document(blocks=new_blocks(520)), blocks_at=0x3C8000))))
        with self.assertRaisesRegex(ValueError, '이미 블록을 늘린'):
            ft.edits(grown, document(blocks=new_blocks(530)), blocks_at=0x3D8000)
        with self.assertRaisesRegex(ValueError, 'index'):
            ft.edits(grown, document(blocks=[{'index': 520, 'lower': [1, 1, 1, 1]}]))
        bad = bytearray(d)
        put(bad, dq5field.TERRAIN_SITES[1], b'\xbf\x00\x00\x03')
        with self.assertRaisesRegex(ValueError, '원래 롬의 블록'):
            ft.edits(Rom(bytes(bad)), document(blocks=new_blocks(520)), blocks_at=0x3C8000)

    def test_cli_blocks_at(self):
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            (tmp / 'rom.sfc').write_bytes(bytes(grow_fixture()))
            (tmp / 'b.json').write_text(json.dumps(document(blocks=new_blocks(512))), encoding='utf-8')
            run = [sys.executable, str(HERE / 'dq5fieldtables.py'), str(tmp / 'rom.sfc'), 'patch', str(tmp / 'b.json'),
                   '-o', str(tmp / 'p.json')]
            self.assertEqual(subprocess.run(run + ['--blocks-at', '3C:8000'], capture_output=True).returncode, 0)
            writes = json.loads((tmp / 'p.json').read_text(encoding='utf-8'))['writes']
            self.assertEqual({w['at'] for w in writes}, {'3C:8000', '00:BC4E', '03:CB2A', '03:CB36'})
            r = subprocess.run(run + ['--blocks-at', '3C:0000'], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn('--blocks-at', r.stderr)
            r = subprocess.run(run, capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn('--blocks-at 으로', r.stderr)


def bit9_rom(planes):
    d = bytearray(0x200000)
    put(d, 0x00BCA0, bytes([0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01]))
    put(d, 0x308000, fw.bit9_hook(planes))
    return d


class Bit9HookTests(unittest.TestCase):
    def test_hook_reads_plane_of_world(self):
        planes = [0x309000, None, 0x30B000]
        d = bit9_rom(planes)
        put(d, 0x309000 + 0x123, b'\x20')            # 세계 0: 바이트 123 의 비트 2
        put(d, 0x30B000 + 0x123, b'\xff')
        for world, e000, want in ((0, 0x00, 0x2), (0, 0x20, 0x3), (1, 0x20, 0x1), (2, 0x00, 0x2), (3, 0x20, 0x1)):
            cpu = Cpu(bytes(d), bytes(0x20000))
            cpu.wram[0x1949] = world
            cpu.wram[0xE123] = e000
            cpu.p = 0x20                               # M 8비트, X 16비트
            cpu.a, cpu.x, cpu.y = 0x5A00, 0x123, 0x5A02   # A 윗바이트 = 번호 하위 8비트, Y 윗바이트도 그 값(TAY)
            cpu.jsl(0x308000)
            self.assertEqual(cpu.a & 0xFFFF, want << 8 | 0x5A, f'세계 {world}')

    def test_plane_writes_rejects(self):
        d = bit9_rom([None] * 3)
        for site, want in zip(dq5field.BIT9_SITES, fw.BIT9_ORIG):
            put(d, site, want)
        rom = Rom(bytes(d))
        grid = [600] * fw.SIZE
        for x, y in fw.CHANGED_CELLS:
            grid[y * 256 + x] = 5
        out, size = fw.plane_writes(rom, bytes(d), {0: grid, 2: [3] * fw.SIZE}, 0x618000)
        self.assertEqual([w['at'] for w in out], ['61:8000', '61:804E', '00:BC33', '00:BE06'])
        self.assertEqual(size, 4)
        self.assertEqual(fw.plane_writes(rom, bytes(d), {0: [3] * fw.SIZE}, None), ([], 2))
        for grids, at, message in (({0: grid}, None, '--planes-at'), ({0: [3] * fw.SIZE}, 0x618000, '512 이상'),
                                   ({1: [600] * fw.SIZE}, 0x618000, '00:CF50')):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                fw.plane_writes(rom, bytes(d), grids, at)
        hooked = bytearray(d)
        put(hooked, dq5field.BIT9_SITES[0], b'\x22\x00\x80\x30')
        with self.assertRaisesRegex(ValueError, '이미 10번째 비트'):
            fw.plane_writes(Rom(bytes(hooked)), bytes(hooked), {0: grid}, 0x618000)

    def test_cli_rejects_without_grown_blocks(self):
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            (tmp / 'rom.sfc').write_bytes(bytes(0x180000))
            (tmp / 'g.bin').write_bytes((600).to_bytes(2, 'little') * fw.SIZE)
            r = subprocess.run([sys.executable, str(HERE / 'dq5fieldwrite.py'), str(tmp / 'rom.sfc'), 'patch', '--world', '0',
                                str(tmp / 'g.bin'), '--planes-at', '61:8000', '-o', str(tmp / 'p.json')],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn('--blocks-at', r.stderr)
            r = subprocess.run([sys.executable, str(HERE / 'dq5fieldwrite.py'), str(tmp / 'rom.sfc'), 'patch', '--world', '0',
                                str(tmp / 'g.bin'), '--planes-at', '7E:8000', '-o', str(tmp / 'p.json')],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn('30~7D', r.stderr)


if __name__ == '__main__':
    unittest.main()
