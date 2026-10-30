"""맵마다 블록 표를 바꾸는 01:936E 훅을 롬 바이트로 읽고, 디코더·상자 칸 세기가 그 표를 따르는지."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dq5chest import chests
from dq5chestplace import furniture_cells
from dq5map import LOAD_TAIL, Decoder, Rom, block_hook, block_table, lorom
from test_dq5chestwrite import ROM

STUB, LOADER, FIND, TARGETS, HIT, REBUILD = 0x01FF00, 0x3BE100, 0x3BE000, 0x3BD000, 0x3BE140, 0x01FF10


def put(data, addr, raw):
    data[lorom(addr):lorom(addr) + len(raw)] = raw


def hook(data, maps, bank, table, count, probe=0x800B):
    """01:936E 훅을 환경 패치와 같은 꼴로 써 넣는다: JMP 스텁 → JSL 로더(찾기·BCS·$1823·MVN)."""
    put(data, LOAD_TAIL, bytes((0x4C, STUB & 0xFF, STUB >> 8 & 0xFF)))
    put(data, STUB, bytes((0x22, *LOADER.to_bytes(3, 'little'), 0x28, 0xAB, 0x60)))
    rel = HIT - (LOADER + 12)
    put(data, LOADER, bytes((0x08, 0xC2, 0x30, 0x48, 0xDA, 0x5A, 0x22, *FIND.to_bytes(3, 'little'), 0xB0, rel)))
    # 못 찾은 길: 7E:B002 가 probe(훅 표 1번)이면 원래 표를 다시 만든다
    put(data, LOADER + 12, bytes((0xC2, 0x20, 0xAF, 0x02, 0xB0, 0x7E, 0xC9, probe & 0xFF, probe >> 8, 0xD0, 0x04,
                                  0x22, *REBUILD.to_bytes(3, 'little'))))
    put(data, REBUILD, bytes((0x20, 0xD8, 0x8C, 0x6B)))
    put(data, FIND, bytes((0x08, 0xE2, 0x30, 0xA2, 0x00, 0xBF, *TARGETS.to_bytes(3, 'little'), 0xC9, 0xFF, 0xF0, 0x10,
                           0xC5, 0xBC, 0xD0, 0x08, 0xBF, *(TARGETS + 1).to_bytes(3, 'little'), 0xC5, 0xBD, 0xF0, 0x07,
                           0xE8, 0xE8, 0x80, 0xE8, 0x28, 0x18, 0x6B, 0x28, 0x38, 0x6B)))
    size = count * 2 - 1
    put(data, HIT, bytes((0xE2, 0x20, 0xA9, bank, 0x8D, 0x23, 0x18, 0xC2, 0x20, 0xA9, size & 0xFF, size >> 8,
                          0xA2, table & 0xFF, table >> 8 & 0xFF, 0xA0, 0x00, 0xB0, 0x54, 0x7E, bank)))
    put(data, TARGETS, bytes(v for m in maps for v in m) + b'\xff')


def blank():
    """원래 블록 뱅크 즉값과 1×1 블록 0(원래 표 1번 = 8005)만 둔 빈 롬."""
    data = bytearray(0x200000)
    put(data, 0x0192F4, bytes((0xA9, 0x16, 0x8D, 0x23, 0x18)))
    put(data, 0x018CDE, bytes((0xA9, 0x16, 0x85, 0xAA)))
    put(data, 0x018CE6, bytes((0xA9, 0x00, 0x80)))
    return data


class BlockHookTests(unittest.TestCase):
    def test_reads_hook_from_bytes(self):
        data = blank()
        put(data, LOAD_TAIL, bytes((0x28, 0xAB, 0x60)))
        self.assertIsNone(block_hook(Rom(data)))
        put(data, 0x3D8C00, bytes((0x00, 0x80, 0x0B, 0x80)))
        hook(data, [(0x16, 2), (0x36, 0)], 0x3D, 0x8C00, 150)
        self.assertEqual(block_hook(Rom(data)), ([(0x16, 2), (0x36, 0)], 0x3D, 0x3D8C00, 150))
        self.assertEqual(block_table(Rom(data), key=(0x36, 0))[:2], [0x3D8000, 0x3D800B])
        self.assertEqual(len(block_table(Rom(data), count=4, key=(0x36, 0))), 150)
        # 훅이 있는 롬에서 맵 번호 없이 부르거나, 그룹 50 이상 맵이 목록에 들면 멈춘다
        with self.assertRaisesRegex(ValueError, '맵 번호'):
            block_table(Rom(data))
        # 못 찾은 길이 훅 표 1번이 아닌 값을 보거나, 훅 표 1번이 원래 표 1번(8005)과 같으면 목록 밖 맵의 표를 알 수 없다
        for probe, first in ((0x800C, 0x800B), (0x8005, 0x8005)):
            put(data, 0x3D8C02, first.to_bytes(2, 'little'))
            hook(data, [(0x16, 2)], 0x3D, 0x8C00, 150, probe)
            with self.subTest(probe=hex(probe)), self.assertRaisesRegex(ValueError, '7E:B002'):
                block_hook(Rom(data))
        put(data, 0x3D8C02, bytes((0x0B, 0x80)))
        hook(data, [(0x51, 0x51)], 0x3D, 0x8C00, 150)
        with self.assertRaisesRegex(ValueError, '그룹 50 이상'):
            Decoder(Rom(data), 0xBE, True, (0x51, 0x51))

    def test_unknown_hook_shapes_stop(self):
        for addr, value, message in ((LOAD_TAIL, 0x20, '01:936E'), (STUB + 4, 0xEA, '스텁'), (FIND + 13, 0xC6, '찾기'), (FIND + 31, 0x18, '찾기'),
                                     (HIT + 4, 0x8E, '\\$1823'), (LOADER + 26, 0x02, '뱅크 01'), (REBUILD + 1, 0xD9, 'JSR'),
                                     # BNE 가 JSL 을 건너뛰지 않거나 뒤로 감, JSL 대상이 뱅크 01 의 8000 미만이거나 스텁이
                                     # 뱅크 끝을 넘음(01:FFFD), 스텁 끝이 RTL 아님
                                     (LOADER + 22, 0x03, 'BNE'), (LOADER + 22, 0x80, 'BNE'), (LOADER + 25, 0x7F, '뱅크 01'),
                                     (LOADER + 24, 0xFD, '뱅크 01'), (REBUILD + 3, 0x60, 'RTL'),
                                     (HIT + 18, 0x44, 'MVN'), (HIT + 20, 0x3C, '포인터 표')):
            data = blank()
            put(data, 0x3D8C00, bytes((0x00, 0x80, 0x0B, 0x80)))
            hook(data, [(0x16, 2)], 0x3D, 0x8C00, 150)
            put(data, addr, bytes((value,)))
            with self.subTest(addr=hex(addr)), self.assertRaisesRegex(ValueError, message):
                block_hook(Rom(data))


@unittest.skipUnless(ROM.is_file(), '롬 없음')
class BlockHookRomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = Rom(ROM.read_bytes())

    def test_original_rom_has_one_table(self):
        self.assertIsNone(block_hook(self.rom))
        table = block_table(self.rom)
        self.assertEqual(table[0], 0x168000)
        self.assertEqual(block_table(self.rom, key=(1, 2)), table)

    def test_listed_map_follows_hook_table(self):
        # 뱅크 16 의 블록을 3A 로 옮기고 포인터 표를 3A:F000 에 둔다. 사본의 블록 384(상자)와 204(タンス)의
        # 속성을 지우면, 목록에 든 맵만 상자·가구 칸이 없어진다
        data = bytearray(self.rom.d) + bytes(0x200000 - len(self.rom.d))
        table = block_table(self.rom)
        # 6바이트 밀어 두어 훅 표 1번(800B)이 원래 표 1번(8005)과 다르게 한다(로더의 못 찾은 길 전제)
        data[lorom(0x3A8006):lorom(0x3A8000) + 0x8000] = self.rom.d[lorom(0x168000):lorom(0x168000) + 0x8000 - 6]
        n = 0x7F8
        put(data, 0x3AF000, b''.join(((a & 0xFFFF) + 6).to_bytes(2, 'little') for a in table[:n]))
        for block in (384, 204):
            data[lorom(0x3A0000 | table[block] & 0xFFFF) + 8] = 0
        hook(data, [(0x01, 0x02)], 0x3A, 0xF000, n)
        rom = Rom(bytes(data))
        self.assertEqual(len(chests(self.rom, 0x01, 0x02, 0)), 2)
        self.assertEqual(len(chests(rom, 0x01, 0x02, 0)), 0)
        self.assertEqual(furniture_cells(rom.d, 0x01, 0x02), set())
        # 목록에 없는 맵은 원래 표를 쓴다
        for key in ((0x31, 0x03), (0x19, 0x00)):
            with self.subTest(key=key):
                self.assertEqual(chests(rom, *key, 0), chests(self.rom, *key, 0))
                self.assertEqual(furniture_cells(rom.d, *key), furniture_cells(self.rom.d, *key))


if __name__ == '__main__':
    unittest.main()
