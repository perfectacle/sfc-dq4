"""상자 번호 16비트 훅(dq5chestreloc --wide-at): 원본 롬에 훅을 붙여 65816 해석기로 열기·들어갈 때·켜기를 돌려 보고,
훅 롬의 표 자리 찾기와 입력 검사를 본다."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5chestreloc as reloc  # noqa: E402
import dq5chestwrite as chestwrite  # noqa: E402
from dq5build import build  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from test_dq5chestwrite import ROM  # noqa: E402
from w65816 import Cpu  # noqa: E402

CODE, TABLE = 0x3FD000, 0x3FC000
# 맵 01/02 앞에 200개, 19/00 앞에 300개. 19/00 의 맵 안 순서 n 은 상자 300 + n
ROWS = [(0x01, 0x02, 200), (0x03, 0x00, 100), (0x19, 0x00, 60)]
# 2A:F224 대신 맵 안 순서를 A 에 두고 돌아오는 자리
INDEX_AT = 0x3FE000


class Reached(Exception):
    pass


def hooked(index=0):
    data = bytearray(Path(ROM).read_bytes()) + bytes(0x200000 - Path(ROM).stat().st_size)
    for addr, new, old, _ in reloc.wide_code(CODE, TABLE):
        if old is not None:
            assert data[lorom(addr):lorom(addr) + len(old)] == old
        data[lorom(addr):lorom(addr) + len(new)] = new
    table = b''.join(bytes(r) for r in ROWS) + b'\xff\xff'
    data[lorom(TABLE):lorom(TABLE) + len(table)] = table
    # 원래 상자 맵 연결 코드(DB 즉값·abs)도 같은 표를 가리키게 해 locate 가 한 자리로 읽게 한다
    for site in reloc.DB_SITES['chest_maps']:
        data[lorom(site)] = TABLE >> 16
    for site, plus in reloc.ABS['chest_maps']:
        data[lorom(site) + 1:lorom(site) + 3] = (TABLE + plus & 0xFFFF).to_bytes(2, 'little')
    data[lorom(0x2AF224):lorom(0x2AF224) + 3] = bytes((0xA9, index, 0x6B))   # LDA #index / RTL
    return Rom(bytes(data))


def label(name):
    return CODE + reloc.assemble(reloc.wide_items())[2][name]


def cpu_for(rom, group, number, **wram):
    memory = bytearray(0x20000)
    memory[0xBC], memory[0xBD] = group, number
    for addr, value in wram.items():
        memory[int(addr[1:], 16)] = value
    cpu = Cpu(rom.d, memory)
    cpu.dbr = 0x12
    return cpu


def open_chest(rom, group, number, **wram):
    """12:E66F 의 JML 로 훅에 들어가 원래 루틴의 어느 갈래로 돌아가는지와 그때의 레지스터."""
    cpu = cpu_for(rom, group, number, **wram)
    seen = {}

    def stop(name):
        def hit(c):
            seen.update(name=name, a=c.a, y=c.y, p=c.p)
            raise Reached
        return hit
    for name, addr in (('none', 0x12E669), ('below', 0x12E675), ('opened', 0x12E68B), ('reward', 0x12E6A7)):
        cpu.hooks[addr] = stop(name)

    def counted(c):
        # 2A:F224 는 맵 안 순서를 DP $00·$01 의 좌표로 센다. 훅이 $1E71 을 그 자리에 옮겨 두었는지 본다
        seen['dp'] = bytes(c.wram[c.d:c.d + 2])
    cpu.hooks[0x2AF224] = counted
    cpu.pbr, cpu.pc = CODE >> 16, label('open') & 0xFFFF
    try:
        cpu.run(max_steps=10_000)
    except Reached:
        pass
    seen['wram'] = cpu.wram
    seen['s'] = cpu.s
    return seen


@unittest.skipUnless(ROM.is_file(), '롬 없음')
class ChestWideTests(unittest.TestCase):
    def test_open_branches(self):
        rom = hooked(index=4)
        # 19/00 의 맵 안 순서 4 = 상자 304: 바이트 28F3 + 48/8 = 28F9, 마스크 80
        got = open_chest(rom, 0x19, 0x00, w291B=0, w1E71=0x0C, w1E72=0x2D)
        self.assertEqual(got['name'], 'reward')
        self.assertEqual(got['dp'], bytes((0x0C, 0x2D)))
        self.assertEqual(got['y'], 304)
        self.assertEqual(got['p'] & 0x30, 0)
        self.assertEqual((got['wram'][0x1E80], got['wram'][0x1E81], got['wram'][0x291B]), (6, 0, 0x80))
        self.assertEqual(got['s'], 0x1FF)
        # 12:F839 를 거치지 않은 보상이 남긴 마스크는 열 때 지운다
        got = open_chest(rom, 0x19, 0x00, w28F9=0x80, w291B=0x04)
        self.assertEqual(got['name'], 'opened')
        self.assertEqual((got['s'], got['wram'][0x291B]), (0x1FF, 0))
        got = open_chest(rom, 0x01, 0x02, w291B=0x04)
        self.assertEqual((got['name'], got['wram'][0x291B]), ('below', 0))
        # 01/02 의 순서 4 는 256 미만이라 원래 루틴(A = 4)으로
        got = open_chest(rom, 0x01, 0x02)
        self.assertEqual((got['name'], got['a'] & 0xFF, got['p'] & 0x30), ('below', 4, 0x30))
        self.assertEqual(open_chest(hooked(index=55), 0x03, 0x00)['a'] & 0xFF, 0xFF)   # 200 + 55 = 255
        self.assertEqual(open_chest(hooked(index=56), 0x03, 0x00)['wram'][0x1E80], 0)   # 256
        self.assertEqual(open_chest(rom, 0x05, 0x00)['name'], 'none')

    def test_entry(self):
        rom = hooked()
        cases = [(0x19, 0x00, 4, {}, False), (0x19, 0x00, 4, {'w28F9': 0x80}, True),
                 (0x19, 0x00, 4, {'w28F9': 0x7F}, False), (0x01, 0x02, 9, {'w2211': 0x40}, True),
                 (0x03, 0x00, 55, {'w222F': 0x01}, True), (0x03, 0x00, 56, {'w222F': 0xFF}, False),
                 (0x03, 0x00, 56, {'w28F3': 0x80}, True),
                 (0x05, 0x00, 0, {'w2210': 0xFF}, False)]
        for group, number, index, wram, opened in cases:
            cpu = cpu_for(rom, group, number, **wram)
            cpu.a, cpu.x = index, 0x33
            cpu.jsl(label('entry'), max_steps=10_000)
            self.assertEqual(bool(cpu.p & 1), opened, (group, number, index, wram))
            self.assertEqual((cpu.a & 0xFF, cpu.x, cpu.p & 0x30), (index, 0x33, 0x30))

    def test_set(self):
        rom = hooked()
        cpu = cpu_for(rom, 0, 0, w1E80=6, w1E81=0, w291B=0x08, w28F9=0x01)
        cpu.jsl(label('set'), max_steps=1_000)
        self.assertEqual((cpu.wram[0x28F9], cpu.wram[0x291B], cpu.p & 1), (0x09, 0, 0))
        # 다른 보상은 원래처럼 2190 + $1E80 에 OR
        cpu = cpu_for(rom, 0, 0, w1E80=0x80, w1E81=0x20, w291B=0x08)
        cpu.jsl(label('set'), max_steps=1_000)
        self.assertEqual((cpu.wram[0x2210], cpu.wram[0x291B], cpu.wram[0x28F3]), (0x20, 0x08, 0))
        # 마스크 0 인데 넘길 마스크도 없으면 아무것도 켜지 않음
        cpu = cpu_for(rom, 0, 0, w1E80=6, w1E81=0)
        cpu.jsl(label('set'), max_steps=1_000)
        self.assertEqual(sum(cpu.wram[0x2190:0x2A00]), 0)
        # 남은 마스크가 있어도 $1E80 이 28F3~291A 의 바이트 번호가 아니면 원래 길(마스크 0 을 OR)로 간다
        for index in (0x28, 0x80, 0xFF):
            cpu = cpu_for(rom, 0, 0, w1E80=index, w1E81=0, w291B=0x08)
            cpu.jsl(label('set'), max_steps=1_000)
            self.assertEqual(sum(cpu.wram[0x28F3:0x291B]) + sum(cpu.wram[0x294A:0x2A00]), 0, hex(index))
            self.assertEqual((cpu.wram[0x2190 + index], cpu.wram[0x291B], cpu.p & 1), (0, 0x08, 0))

    def test_locate_and_limits(self):
        rom = hooked()
        self.assertEqual(reloc.locate(rom)['chest_maps'], TABLE)
        data = bytearray(rom.d)
        data[lorom(CODE) + 40] ^= 1
        with self.assertRaises(ValueError):
            reloc.locate(Rom(bytes(data)))
        self.assertEqual(reloc.MAX_WIDE, 576)
        doc = {'format': reloc.FORMAT, 'chests': [{'reward': 1}] * 577, 'chest_maps': [], 'search': [], 'foot': [],
               'ahead': [], 'lower': []}
        bits = reloc.flag_bits(dict(doc, chests=doc['chests'][:576]))
        self.assertEqual(bits[0x291A, 0x01], '일반 상자 575')
        self.assertEqual(bits[0x28F3, 0x80], '일반 상자 256')
        with self.assertRaisesRegex(ValueError, '576개까지'):
            reloc.flag_bits(doc)
        # 다른 표의 비트는 늘린 뒤에도 2210~224F 안이어야 함
        lower = {'group': 0x51, 'map': 0x51, 'x': 1, 'y': 1, 'reward': 1, 'flag_index': 0x7F, 'mask': 1}
        with self.assertRaises(ValueError):
            reloc.flag_bits(dict(doc, chests=[], lower=[lower]))
        # 상자 비트가 아닌 항목은 28F3~ 에 둘 수 없음
        with self.assertRaisesRegex(ValueError, '2210~224F 밖'):
            reloc.flag_bits(dict(doc, chests=[], search=[
                {'group': 0x17, 'map': 0, 'x': 2, 'y': 4, 'unused': 1, 'reward': 1, 'flag_index': 0xFF, 'mask': 1}]))
        # 마스크 0 인 항목은 --wide-at 에서 거부
        reloc.flag_bits(dict(doc, chests=[], lower=[dict(lower, flag_index=0, mask=0)]))
        with self.assertRaisesRegex(ValueError, 'mask'):
            reloc.flag_bits(dict(doc, chests=[], lower=[dict(lower, flag_index=0, mask=0)]), wide=True)

    def test_patch_writes_hooks(self):
        rom = Rom(Path(ROM).read_bytes())
        doc = reloc.parse(rom)
        writes, mb = reloc.writes_for(rom, doc, {'chest_maps': 0x3FC000, 'wide': 0x3FD000})
        sites = {addr for addr, *_ in writes}
        self.assertTrue({0x12E66F, 0x1FFDD0, 0x12F839, 0x3FD000} <= sites)
        built = Rom(build(rom.d, [('wide', mb, [(lorom(a), n, o, note) for a, n, o, note in writes])], mb)[0])
        self.assertEqual(reloc.wide_at(built), 0x3FD000)
        with self.assertRaises(ValueError):
            reloc.writes_for(rom, json.loads(json.dumps(doc)) | {'chests': doc['chests'] * 2}, {})

    def test_chestwrite_on_hooked_rom(self):
        # 표를 옮기지 않고 훅만 넣은 롬에서도 고정 표 쓰기가 같은 표를 읽고 쓴다
        rom = Rom(Path(ROM).read_bytes())
        writes, mb = reloc.writes_for(rom, reloc.parse(rom), {'wide': 0x3FD000})
        self.assertLessEqual({0x3FD000, *(site for site, _ in reloc.WIDE_SITES.values())}, {addr for addr, *_ in writes})
        built = Rom(build(rom.d, [('wide', mb, [(lorom(a), n, o, note) for a, n, o, note in writes])], mb)[0])
        self.assertEqual(reloc.locate(built), reloc.ORIGINAL)
        manifest = chestwrite.patch(built, {'format': chestwrite.FORMAT, 'chests': [{'index': 2, 'reward': 0x241}]})
        self.assertEqual([w['at'] for w in manifest['writes']], ['1E:EE52'])


if __name__ == '__main__':
    unittest.main()
