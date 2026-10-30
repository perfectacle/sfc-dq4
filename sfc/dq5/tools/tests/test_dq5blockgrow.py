"""블록 번호 511~2047(dq5fieldtables --blocks-at)·10·11번째 비트 평면(dq5fieldwrite --planes-at)·세계 1·2 시간대 벌을
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
        # 훅: 블록 601, 칸 (1, 1)(오른쪽 아래). 00:BC6D 에는 RTS 를, 00:BC47 에도 RTS 를 둔다.
        data = bytearray(rom.d)
        put(data, 0x00BC6D, b'\x60')
        put(data, 0x00BC47, b'\x60')
        for block, quad, want in ((601, 3, (601 & 255, 0, 1, 0)), (511, 0, (511 & 255, 0, 0, 0)),
                                  (300, 0, None), (300, 3, None)):
            cpu = Cpu(bytes(data), bytes(0x20000))
            cpu.p = 0x30
            cpu.wram[0x90], cpu.wram[0x92] = quad & 1, quad >> 1
            cpu.a = block
            cpu.jsr(dq5field.BLOCK_GROW_SITE)
            if want is None:
                # 원래 갈래: 00:BC50~BC6C 와 같은 X = 번호 × 5 + 칸, Y = 칸, $02 = 번호 × 5 로 00:BC6D
                self.assertEqual((cpu.x, cpu.y, cpu.wram[2] | cpu.wram[3] << 8), (1500 + quad, quad, 1500))
                continue
            entry = [rom.u8(dq5field.block_entry(rom, u, block) + i) for u in (False, True) for i in (quad, 4)]
            self.assertEqual(tuple(cpu.wram[0x94:0x98]), (entry[0], entry[1] >> 7 - quad & 1, entry[2],
                                                          entry[3] >> 7 - quad & 1 | (entry[3] >> 3 - quad & 1) << 1))
        self.assertEqual(dq5field.terrain(rom, 650), 3)

    def test_grow_to_2048(self):
        d = grow_fixture()
        blocks = new_blocks(2048)
        blocks[-1]['terrain'] = 7
        rom = Rom(bytes(apply(d, ft.edits(Rom(bytes(d)), document(blocks=blocks), blocks_at=0x3C8000))))
        self.assertEqual(dq5field.block_count(rom), 2048)
        self.assertEqual((dq5field.terrain(rom, 2046), dq5field.terrain(rom, 2047)), (3, 7))
        self.assertEqual(ft.dump(rom)['blocks'][2000]['lower'], [2000 & 255, 1, 2, 3])
        data = bytearray(rom.d)
        put(data, 0x00BC47, b'\x60')
        cpu = Cpu(bytes(data), bytes(0x20000))
        cpu.p = 0x30
        cpu.a = 2047
        cpu.jsr(dq5field.BLOCK_GROW_SITE)
        self.assertEqual(cpu.wram[0x94], 2047 & 255)

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
            (document(blocks=new_blocks(2049)), 0x3C8000, 'index'),
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


# 원본의 00:CF50 즉값: x0 x1·y0 y1 은 8픽셀 칸, n 은 되풀이 횟수 − 1.
CELL_VALUES = {0x01A01B: {'x': 0x16, 'y': 0xA6}, 0x12EFC1: {'x': 0x16, 'y': 0xA6}, 0x03BB3C: {'x': 0x22, 'y': 0xF8},
               0x05EF0F: {'x': 0x1C4, 'y': 0xEE, 'n': 2}}


def put_cells(d, values=CELL_VALUES):
    for at, text in fw.CHANGED_SITES:
        v = values[at]
        put(d, at, bytes(v[t[0]] >> 8 * int(t[1]) & 0xFF if t[0] in 'xyn' else int(t, 16) for t in text.split()))


def bit9_rom(planes, planes10=(None, None, None)):
    d = bytearray(0x200000)
    put(d, 0x00BCA0, bytes([0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01]))
    put(d, 0x308000, fw.bit9_hook(planes, planes10))
    put_cells(d)
    # 11비트 훅은 JML 로 원래 다음 명령에 돌아간다. 해석기의 jsl 이 끝나도록 그 자리에 RTL 을 두고, 어느 자리로 돌아왔는지
    # 보이게 앞에 자리마다 다른 INC $1000·INC $1002 를 둔다.
    for k, back in enumerate(fw.BIT11_RETURNS):
        put(d, back, bytes([0xEE, k * 2, 0x10, 0x6B]))
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

    def test_hook_reads_eleventh_bit(self):
        planes, planes10 = [0x309000, None, 0x30B000], [0x30A000, 0x30C000, None]
        d = bit9_rom(planes, planes10)
        put(d, 0x309000 + 0x123, b'\x20')            # 비트 2: 세계 0 의 10번째 비트
        put(d, 0x30A000 + 0x123, b'\x20')
        put(d, 0x30C000 + 0x123, b'\xdf')            # 세계 1: 비트 2 만 끔
        put(d, 0x30B000 + 0x123, b'\xff')
        cases = ((0, 0x00, 0x6), (0, 0x20, 0x7), (1, 0x20, 0x1), (1, 0x00, 0x0), (2, 0x00, 0x2), (3, 0x20, 0x1))
        entries = fw.bit11_entries(fw.bit9_hook(planes, planes10))
        for (world, e000, want), (k, entry) in ((c, e) for c in cases for e in enumerate(entries)):
            cpu = Cpu(bytes(d), bytes(0x20000))
            cpu.wram[0x1949] = world
            cpu.wram[0xE123] = e000
            cpu.p = 0x20
            cpu.a, cpu.x, cpu.y = 0x5A00, 0x123, 0x5A02
            s = cpu.s
            cpu.jsl(0x308000 + entry)
            self.assertEqual(cpu.a & 0xFFFF, want << 8 | 0x5A, f'세계 {world} 몸통 {entry}')
            self.assertEqual((cpu.x, cpu.y, cpu.s), (2, 2, s), f'세계 {world} 몸통 {entry}')
            self.assertEqual((cpu.wram[0x1000], cpu.wram[0x1002]), (k == 0, k == 1), f'세계 {world} 몸통 {entry}')
        put(d, dq5field.BIT9_SITES[0], b'\x22\x00\x80\x30')
        rom = Rom(bytes(d))
        self.assertEqual(dq5field.bit9_planes(rom), planes)
        self.assertEqual(dq5field.bit9_planes(rom, 10), planes10)
        # 10번째 비트만 읽던 훅(머리 9바이트)은 11번째 비트 평면이 없다
        put(d, 0x308000, b'\x80\x09' + (0x309000).to_bytes(3, 'little') + bytes(6))
        self.assertEqual(dq5field.bit9_planes(Rom(bytes(d)), 10), [None] * 3)
        self.assertEqual(dq5field.bit9_planes(Rom(bytes(d))), [0x309000, None, None])
        # 11번째 비트 평면이 없으면 10번째 비트만 읽던 훅 그대로
        self.assertEqual(fw.bit9_hook(planes)[:2], b'\x80\x09')
        self.assertEqual(len(fw.bit9_hook(planes)), 78)

    def test_plane_writes_eleventh_bit(self):
        d = bit9_rom([None] * 3)
        for site, want in zip(dq5field.BIT9_SITES, fw.BIT9_ORIG):
            put(d, site, want)
        rom = Rom(bytes(d))
        grid = [1030 + i % 2 * 512 for i in range(fw.SIZE)]       # 1030(11번째 비트만)·1542(10·11번째 비트)
        other = [1100] * fw.SIZE
        for x, y in fw.changed_cells(rom):
            grid[y * 256 + x] = other[y * 256 + x] = 5
        hook = len(fw.bit9_hook([1, None, None], [1, 1, None]))
        out, _ = fw.plane_writes(rom, bytes(d), {0: grid, 1: other}, 0x318000)
        a = 0x318000 + hook
        self.assertEqual([w['at'] for w in out], [f'31:{x & 0xFFFF:04X}' for x in (0x318000, a, a + 0x2000, a + 0x4000)]
                         + ['00:BC33', '00:BE06'])
        self.assertEqual([w['note'] for w in out[1:4]], ['세계 0 블록 번호 10번째 비트 평면', '세계 0 블록 번호 11번째 비트 평면',
                                                         '세계 1 블록 번호 11번째 비트 평면'])
        hooked = bytearray(d)
        for w in out:
            put(hooked, int(w['at'][:2], 16) << 16 | int(w['at'][3:], 16), bytes.fromhex(w['hex']))
        r = Rom(bytes(hooked))
        self.assertEqual(dq5field.bit9_planes(r), [a, None, None])
        self.assertEqual(dq5field.bit9_planes(r, 10), [a + 0x2000, a + 0x4000, None])
        plane = r.d[lorom(a + 0x2000):lorom(a + 0x2000) + 0x2000]
        self.assertEqual(plane[0x10], 0xFF)
        self.assertEqual(r.d[lorom(a) + 0x10], 0x55)
        # 지도(블록 하위 8비트 = 6)·9번째 비트(0)를 원래 자리에 두면 world_blocks 가 평면까지 더해 1030·1542 를 돌려준다.
        for src, part in zip(dq5field.WORLDS[0], (bytes([6]) * fw.SIZE, bytes(fw.PLANE))):
            put(hooked, src, fw.encode_rle(part))
        blocks = dq5field.world_blocks(Rom(bytes(hooked)), 0)
        cells = set(fw.changed_cells(rom))
        self.assertEqual([blocks[i] for i in range(fw.SIZE) if (i % 256, i // 256) not in cells],
                         [grid[i] for i in range(fw.SIZE) if (i % 256, i // 256) not in cells])
        self.assertEqual(blocks[:2], [1030, 1542])
        with self.assertRaises(ValueError):
            dq5field.bit9_planes(r, 11)
        with self.assertRaisesRegex(ValueError, '00:CF50'):
            fw.plane_writes(rom, bytes(d), {2: [1100] * fw.SIZE}, 0x318000)

    def test_fast_hook_matches_tables(self):
        # 블록을 1,600개로 늘린 롬에 세계 0(11번째 비트까지)·1(10번째 비트만) 지도를 쓰고, 00:BBF7 을 부르는 짧은 루틴으로
        # 빠른 훅을 돌린다. 00:BC6D 에는 RTS 를 둬 511 미만 갈래가 INDEX5 를 마친 X·Y 를 보고, 00:BC46 은 PLP / RTS 다.
        d = grow_fixture()
        put_cells(d)
        for site, want in zip(dq5field.BIT9_SITES, fw.BIT9_ORIG):
            put(d, site, want)
        put(d, 0x00BBF7, b'\x08' + fw.FAST_ORIG)
        put(d, 0x00BDC5, b'\x08\x8b\xc2\x30' + fw.FAST_ORIG)
        put(d, fw.MAP_SITE, fw.MAP_ORIG)
        put(d, fw.LAND_SITE - 1, b'\x08' + fw.LAND_ORIG)
        d = apply(d, ft.edits(Rom(bytes(d)), document(blocks=new_blocks(1600)), blocks_at=0x3C8000))
        rom = Rom(bytes(d))
        cells = {y * 256 + x for x, y in fw.changed_cells(rom)}
        grids = {0: [5 if i in cells else (i * 37 + i // 256) % 1600 for i in range(fw.SIZE)],
                 1: [5 if i in cells else (i * 11) % 1024 for i in range(fw.SIZE)]}
        out, _ = fw.plane_writes(rom, bytes(d), grids, 0x318000)
        self.assertEqual([w['at'] for w in out[-4:]], ['00:BBF8', '00:BDC9', '03:CB07', '03:CB1C'])
        self.assertEqual([w['at'] for w in out if '반 바이트' in w['note']], ['32:8000', '33:8000'])
        for w in out:
            put(d, int(w['at'][:2], 16) << 16 | int(w['at'][3:], 16), bytes.fromhex(w['hex']))
        put(d, 0x009000, b'\xc2\x30\x20\xf7\xbb\x6b')
        put(d, 0x009010, b'\xc2\x30\x20\xc5\xbd\x6b')
        put(d, 0x00BE14, b'\xab\x28\x60')
        put(d, 0x00BC46, b'\x28\x60')
        put(d, 0x00BC6D, b'\x60')
        put(d, 0x00BC43, b'\x20\x6d\xbc')
        # 세계 지도 화면의 점: M 8비트·X 16비트(X = 07FE, Y = 03FF)로 03:CB07 을 JSR 하고, 03:CB15 는 원래처럼
        # CLC / ADC #$20 / STA $CD / RTS.
        put(d, 0x039000, b'\xe2\x20\xc2\x10\xa2\xfe\x07\xa0\xff\x03\x20\x07\xcb\x6b')
        put(d, 0x03CB15, b'\x18\x69\x20\x85\xcd\x60')
        # 지형 루틴: 01:81D4 처럼 M·X 16비트로 A 윗바이트를 채운 채 03:CB1B 를 JSL 하고, 원래처럼 A = 지형(윗바이트 0)으로
        # 돌아오는지. 01:81DA 가 이 A 를 16비트 TAX 로 01:81FD 를 읽는다.
        put(d, 0x039020, b'\xc2\x30\xa9\xff\xff\xa2\xfe\x07\xa0\xff\x03\x22\x1b\xcb\x03\x6b')
        rom = Rom(bytes(d))
        checked = {'wide': 0, 'narrow': 0}
        for world, (x, y) in ((w, (x, y)) for w in (0, 1, 3) for x, y in ((0, 0), (1, 1), (37, 300), (300, 37), (511, 2),
                                                                              (2, 511), (130, 77), (131, 77), (64, 65))):
            grid = grids.get(world, grids[0])
            wram = bytearray(0x20000)
            for i, v in enumerate(grid):
                wram[0x10000 + i] = v & 0xFF
                wram[0xE000 + (i >> 3)] |= (v >> 8 & 1) << (7 - (i & 7))
            wram[0x1949] = world
            wram[0x90], wram[0x91], wram[0x92], wram[0x93] = x & 0xFF, x >> 8, y & 0xFF, y >> 8
            cpu = Cpu(bytes(d), bytes(wram))
            cpu.dbr = 0x7E
            s = cpu.s
            cpu.jsl(0x009000)
            n = grid[(y >> 1) * 256 + (x >> 1)] & (0x1FF if world == 3 else 0xFFFF)
            q = (x & 1) | (y & 1) << 1
            self.assertEqual(cpu.s, s, f'세계 {world} ({x},{y})')
            # 00:BDC5(번호만): 00:BE14 의 PLB / PLP / RTS 로 돌아와 A = 번호, DB 는 그대로
            terrain = Cpu(bytes(d), bytes(wram))
            terrain.dbr = 0x01
            terrain.jsl(0x009010)
            self.assertEqual((terrain.a & 0xFFFF, terrain.dbr, terrain.s), (n, 0x01, s), f'세계 {world} ({x},{y}) 지형')
            # 03:CB07: $CE·$D0 을 $90·$92 에 두고 지형 + 20 을 $CD 에, X 는 그대로
            if x < 0x200 and y < 0x200:
                dot = Cpu(bytes(d), bytes(wram))
                dot.wram[0xCE], dot.wram[0xCF], dot.wram[0xD0], dot.wram[0xD1] = x & 0xFF, x >> 8, y & 0xFF, y >> 8
                dot.dbr = 0x03
                dot.jsl(0x039000)
                self.assertEqual((dot.wram[0xCD], dot.x, dot.y, dot.s, bytes(dot.wram[0x90:0x94])),
                                 (dq5field.terrain(rom, n) + 0x20, 0x07FE, 0x03FF, s, bytes(wram[0x90:0x94])),
                                 f'세계 {world} ({x},{y}) 점')
            land = Cpu(bytes(d), bytes(wram))
            land.dbr = 0x01
            land.jsl(0x039020)
            # 훅은 M 8비트로 끝나므로 M·X 16비트가 돌아온 것은 PLP 가 부른 쪽의 P 를 되돌린 것이다
            self.assertEqual((land.a & 0xFFFF, land.x, land.y, land.s, land.dbr, land.p & 0x30),
                             (dq5field.terrain(rom, n), 0x07FE, 0x03FF, s, 0x01, 0), f'세계 {world} ({x},{y}) 지형 루틴')
            if n < 511:
                self.assertEqual((cpu.x, cpu.y), (n * 5 + q, q), f'세계 {world} ({x},{y}) 번호 {n}')
                checked['narrow'] += 1
                continue
            entry = [rom.u8(dq5field.block_entry(rom, u, n) + i) for u in (False, True) for i in (q, 4)]
            want = (entry[0], entry[1] >> 7 - q & 1 | (entry[1] >> 3 - q & 1) << 1,
                    entry[2], entry[3] >> 7 - q & 1 | (entry[3] >> 3 - q & 1) << 1)
            self.assertEqual(tuple(cpu.wram[0x94:0x98]), want, f'세계 {world} ({x},{y}) 번호 {n}')
            checked['wide'] += 1
        self.assertTrue(checked['wide'] and checked['narrow'])
        # 좌표가 0200 이상이면 원래처럼 A = 0 으로 00:BC43 에 간다(여기서는 JSR $BC6D 로 바꿔 둠).
        cpu = Cpu(bytes(d), bytes(0x20000))
        cpu.wram[0x90], cpu.wram[0x91], cpu.a = 0x00, 0x02, 0x1234
        cpu.jsl(0x009000)
        self.assertEqual(cpu.a & 0xFFFF, 0)
        dot = Cpu(bytes(d), bytes(0x20000))
        dot.wram[0xCE], dot.wram[0xCF], dot.wram[0x10000] = 0x00, 0x02, 0x33
        dot.jsl(0x039000)
        self.assertEqual((dot.wram[0xCD], dot.x, dot.y), (dq5field.terrain(rom, 0) + 0x20, 0x07FE, 0x03FF))
        self.assertEqual(fw.nibble_plane([0, 512, 1024, 1536])[:2], bytes([0x20, 0x64]))

    def test_plane_writes_rejects(self):
        d = bit9_rom([None] * 3)
        for site, want in zip(dq5field.BIT9_SITES, fw.BIT9_ORIG):
            put(d, site, want)
        rom = Rom(bytes(d))
        grid = [600] * fw.SIZE
        self.assertEqual(sorted(fw.changed_cells(rom)), sorted([(0x0B, 0x53)] * 2 + [(0x11, 0x7C), (0xE2, 0x75),
                                                                (0xE2, 0x76), (0xE2, 0x77)]))
        for x, y in fw.changed_cells(rom):
            grid[y * 256 + x] = 5
        hook = len(fw.bit9_hook([None] * 3))
        out, size = fw.plane_writes(rom, bytes(d), {0: grid, 2: [3] * fw.SIZE}, 0x618000)
        self.assertEqual([w['at'] for w in out], ['61:8000', f'61:{0x8000 + hook:04X}', '00:BC33', '00:BE06'])
        # 훅이 뱅크 끝에 딱 맞거나 평면이 FFFF 에서 끝나면 다음 평면은 다음 뱅크 0000(롬 아님)이 아니라 8000 에
        out, _ = fw.plane_writes(rom, bytes(d), {0: grid}, 0x620000 - hook)
        self.assertEqual([w['at'] for w in out[:2]], [f'61:{0x10000 - hook:04X}', '62:8000'])
        out, _ = fw.plane_writes(rom, bytes(d), {0: grid, 2: grid}, 0x61E000 - hook)
        self.assertEqual([w['at'] for w in out[:3]], [f'61:{0xE000 - hook:04X}', '61:E000', '62:8000'])
        self.assertEqual(size, 4)
        self.assertEqual(fw.plane_writes(rom, bytes(d), {0: [3] * fw.SIZE}, None), ([], 2))
        with self.assertRaisesRegex(ValueError, '한 뱅크'):
            fw.plane_writes(rom, bytes(d), {0: grid}, 0x620000 - hook + 0x20)
        for grids, at, message in (({0: grid}, None, '--planes-at'), ({0: [3] * fw.SIZE}, 0x618000, '512 이상'),
                                   ({1: [600] * fw.SIZE}, 0x618000, '00:CF50')):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                fw.plane_writes(rom, bytes(d), grids, at)
        moved = bytearray(d)
        put_cells(moved, {**CELL_VALUES, 0x01A01B: {'x': 0x40, 'y': 0x20}})
        with self.assertRaisesRegex(ValueError, r'\(32, 16\)'):
            fw.plane_writes(Rom(bytes(moved)), bytes(moved), {0: grid}, 0x618000)
        broken = bytearray(d)
        put(broken, 0x03BB3C, b'\xa9')
        with self.assertRaisesRegex(ValueError, '03:BB3C'):
            fw.changed_cells(Rom(bytes(broken)))
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
