"""창 레코드 자리·크기 쓰기를 원본 롬 없이 검사한다."""
import contextlib
import hashlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5map import Rom, lorom  # noqa: E402
from w65816 import Cpu  # noqa: E402
from dq5text import WINDOWS  # noqa: E402
import dq5windowwrite  # noqa: E402
from dq5windowwrite import (COLOR_ORIG, COLOR_SITES, EFFECT_ORIG, EFFECT_RAM, EFFECT_SITE, FORMAT, GRID,  # noqa: E402
                            COLOR_LOADS, DMA_REGS, DMA_STARTS, ROUTINES, STUBS, WAVE_OPERANDS, assemble, check, dump,
                            edits, effect_items, effects_at, message_at, message_items, message_sites, patch, records)

COUNT = 0x30
# 원본처럼 진짜 창 뒤에 첫 레코드까지 창이 아닌 포인터가 남는다.
JUNK = (0x00FF, 0x0000, 0xFFFF, 0xFF00)


def pointer(data, n, low):
    data[lorom(WINDOWS + n * 2):lorom(WINDOWS + n * 2) + 2] = low.to_bytes(2, 'little')


def fixture():
    data = bytearray(0x180000)
    first = (WINDOWS & 0xFFFF) + (COUNT + len(JUNK)) * 2
    for n in range(COUNT):
        addr = first + n * 8
        pointer(data, n, addr)
        data[lorom(0x040000 | addr):lorom(0x040000 | addr) + 8] = bytes([0x02, 0x94, 0xC8, 0xA5, 0, 1, 0xFE, 0xFF])
    for n, low in enumerate(JUNK, COUNT):
        pointer(data, n, low)
    alias = lorom(0x040000 | first + 3 * 8)
    data[alias:alias + 3] = bytes([0x80, 0, 2])
    data[lorom(0x040000 | first + 5 * 8)] = 0x42
    pointer(data, 7, first + 6 * 8)
    # 전투 메시지 창 18·25 는 원본처럼 (2,21) 28 × 7 이고, 글자·▼ 칸을 박아 둔 코드도 원본 값으로 둔다.
    for n, head in ((0x18, 0x02), (0x25, 0x42)):
        at = lorom(0x040000 | first + n * 8)
        data[at:at + 4] = bytes([head, 0x95 if n == 0x18 else 0x15, 0x1C, 0x07])
    for addr, op, size, value, _ in message_sites(2, 21):
        data[lorom(addr):lorom(addr) + 1 + size] = bytes([op]) + value.to_bytes(size, 'little')
        if op == 0x9F:
            data[lorom(addr) + 1 + size] = 0x7E
    # 격자 루틴 자리는 원본 바이트 대신 자리마다 다른 바이트로 채우고, 그 해시를 ROUTINES 로 쓴다(routines()).
    for addr, (size, _, _) in ROUTINES.items():
        for i in range(size):
            if not 0x24A5EC <= addr + i < 0x24A5F0:
                data[lorom(addr) + i] = (addr + i * 7) & 0xFF
    data[lorom(EFFECT_SITE):lorom(EFFECT_SITE) + len(EFFECT_ORIG)] = EFFECT_ORIG
    sites = [(a, bytes([0xA9, v])) for a, v in WAVE_OPERANDS.items()] + [(a, COLOR_ORIG) for a in COLOR_SITES] + list(COLOR_LOADS.items())
    # NMI GP DMA 레지스터 자리는 채널 7 의 $4370~$4375 를 돌려 가며 둔다.
    sites += [(a, bytes([0x8D, 0x70 + i % 6, 0x43])) for i, a in enumerate(DMA_REGS)]
    sites += [(a, bytes.fromhex('a9 80 8d 0b 42')) for a in DMA_STARTS]
    for addr, orig in sites:
        data[lorom(addr):lorom(addr) + len(orig)] = orig
    return bytes(data)


def routines(data):
    """fixture 의 격자 루틴 자리에 맞춘 ROUTINES(앞 바이트 sha1, 원래 X 를 박은 24:A5ED·A5EE 를 0 으로 친 나머지 sha1)."""
    out = {}
    for addr, (size, _, _) in ROUTINES.items():
        raw = bytearray(data[lorom(addr):lorom(addr) + size])
        n = 6 if addr == 0x24813B else 5
        for m in (0x24A5ED, 0x24A5EE):
            if addr <= m < addr + size:
                raw[m - addr] = 0
        head, raw[:n] = bytes(raw[:n]), bytes(n)
        out[addr] = (size, hashlib.sha1(head).hexdigest()[:12], hashlib.sha1(bytes(raw)).hexdigest()[:12])
    return out


def apply_new(data, manifest):
    """orig 가 없는 쓰기(새 코드)도 붙인다."""
    out = bytearray(data)
    for w in manifest['writes']:
        off = lorom(int(w['at'].replace(':', ''), 16))
        raw = bytes.fromhex(w['hex'])
        if 'orig' in w:
            assert out[off:off + len(raw)] == bytes.fromhex(w['orig'])
        out[off:off + len(raw)] = raw
    return bytes(out)


def apply(data, manifest):
    out = bytearray(data)
    for w in manifest['writes']:
        off = lorom(int(w['at'].replace(':', ''), 16))
        raw = bytes.fromhex(w['hex'])
        assert out[off:off + len(raw)] == bytes.fromhex(w['orig'])
        out[off:off + len(raw)] = raw
    return bytes(out)


class WindowWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture()
        cls.rom = Rom(cls.data)
        cls.first = cls.rom.u16(WINDOWS) | 0x040000
        cls.routines = mock.patch.dict(dq5windowwrite.ROUTINES, routines(cls.data))
        cls.routines.start()

    @classmethod
    def tearDownClass(cls):
        cls.routines.stop()

    def with_byte(self, addr, value):
        data = bytearray(self.data)
        data[lorom(addr)] = value
        return bytes(data)

    def test_dump_and_unchanged(self):
        doc = dump(self.rom)
        self.assertEqual(len(records(self.rom)), COUNT)
        self.assertEqual(len(doc['windows']), COUNT - 1)
        self.assertEqual(doc['windows'][0], {'index': '00', 'x': 2, 'y': 20, 'w': 8, 'h': 5})
        self.assertEqual(patch(self.rom, doc)['writes'], [])

    def test_table_stops_at_junk_and_bank_end(self):
        table = records(self.rom)
        self.assertEqual(max(table), COUNT - 1)
        data = bytearray(self.data)
        pointer(data, 0x10, 0xFFFE)
        with self.assertRaises(ValueError):
            records(Rom(bytes(data)))
        pointer(data, 0x10, 0xFFFC)
        self.assertEqual(records(Rom(bytes(data)))[0x10], 0x04FFFC)

    def test_move_keeps_other_bits(self):
        manifest = patch(self.rom, {'format': FORMAT, 'windows': [{'index': '19', 'x': 12, 'y': 8, 'w': 6, 'h': 9}]})
        self.assertEqual(len(manifest['writes']), 1)
        rom = Rom(apply(self.data, manifest))
        addr = records(rom)[0x19]
        self.assertEqual(bytes(rom.d[lorom(addr):lorom(addr) + 8]), bytes([0x0C, 0x88, 0xC6, 0xA9, 0, 1, 0xFE, 0xFF]))

    def test_party_height_window(self):
        manifest = patch(self.rom, {'format': FORMAT, 'windows': [{'index': '05', 'x': 4, 'y': 6, 'w': 10, 'h': 5}]})
        rom = Rom(apply(self.data, manifest))
        addr = records(rom)[5]
        self.assertEqual(bytes(rom.d[lorom(addr):lorom(addr) + 4]), bytes([0x44, 0x86, 0xCA, 0xA5]))
        with self.assertRaises(ValueError):
            edits(self.rom, {'format': FORMAT, 'windows': [{'index': '05', 'h': 6}]})
        # 원래 Y 20 에서 내려가지 않으면 X·너비를 바꾸거나 올려도 받는다(원본 1B 와 같은 꼴).
        for row in ({'x': 4, 'w': 12}, {'y': 18}, {'y': 2}):
            with self.subTest(row=row):
                self.assertEqual(len(edits(self.rom, {'format': FORMAT, 'windows': [{'index': '05', **row}]})), 1)
        # 내려가면 엔진이 다시 센 최악 높이로 본다(bit5 꺼짐 15, 켜짐 11).
        for y in (21, 27):
            with self.subTest(y=y), self.assertRaises(ValueError):
                edits(self.rom, {'format': FORMAT, 'windows': [{'index': '05', 'y': y}]})
        party = Rom(self.with_byte(self.first + 5 * 8, 0x62))
        self.assertEqual(len(edits(party, {'format': FORMAT, 'windows': [{'index': '05', 'y': 21}]})), 1)
        with self.assertRaises(ValueError):
            edits(party, {'format': FORMAT, 'windows': [{'index': '05', 'y': 22}]})
        with self.assertRaises(ValueError):
            edits(self.rom, {'format': FORMAT, 'windows': [{'index': '05', 'x': 20, 'w': 13}]})

    def test_low_height_window_moves(self):
        rom = Rom(self.with_byte(self.first + 8 * 8 + 3, 0xA1))
        self.assertEqual(len(edits(rom, {'format': FORMAT, 'windows': [{'index': '08', 'x': 4}]})), 1)
        for row in ({'index': '08', 'h': 0}, {'index': '08', 'w': 1}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                edits(rom, {'format': FORMAT, 'windows': [row]})

    def test_shared_record(self):
        table = records(self.rom)
        self.assertEqual(table[6], table[7])
        self.assertEqual(len(edits(self.rom, {'format': FORMAT, 'windows': [{'index': '06', 'x': 2}]})), 1)
        for index in ('06', '07'):
            with self.subTest(index=index), self.assertRaises(ValueError):
                edits(self.rom, {'format': FORMAT, 'windows': [{'index': index, 'x': 3}]})

    def test_rejects(self):
        cases = [{'format': 'x', 'windows': []}, {'format': FORMAT}, {'format': FORMAT, 'windows': [], 'x': 1},
                 {'format': FORMAT, 'windows': [{'index': 25, 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '30', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '32', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': ' 1', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '+1', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '1', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': 'zz', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '03', 'x': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '25', 'y': 15}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'x': 32}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'h': 16}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'x': 30}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'y': 30}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'w': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'z': 1}]},
                 {'format': FORMAT, 'windows': [{'index': '19', 'x': 3}, {'index': '19', 'x': 4}]}]
        for doc in cases:
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                edits(self.rom, doc)
        self.assertEqual(edits(self.rom, {'format': FORMAT, 'windows': [{'index': '25', 'y': 21}]}), [])

    def test_message_window_x(self):
        manifest = patch(self.rom, {'format': FORMAT, 'windows': [{'index': '25', 'x': 4}]})
        writes = {w['at']: w['hex'] for w in manifest['writes']}
        table = records(self.rom)
        self.assertEqual(writes[f'04:{table[0x18] & 0xFFFF:04X}'], '04 95 1c 07')
        self.assertEqual(writes[f'04:{table[0x25] & 0xFFFF:04X}'], '44 15 1c 07')
        # 원본 7E:5546·5586·06B8·06F8·3 이 두 칸 오른쪽으로.
        self.assertEqual({k: v for k, v in writes.items() if not k.startswith('04:') or k == '04:BCF9'},
                         {'24:A5ED': '4a 55', '24:883C': '8a 55', '24:8850': '8a 55', '24:A51F': 'bc 06',
                          '24:A529': 'fc 06', '04:BCF9': '05'})
        rom = Rom(apply(self.data, manifest))
        self.assertEqual(edits(rom, {'format': FORMAT, 'windows': [{'index': '18', 'x': 4}]}), [])
        self.assertEqual(len(edits(rom, {'format': FORMAT, 'windows': [{'index': '18', 'x': 2}]})), 8)
        self.assertEqual(len(edits(self.rom, {'format': FORMAT, 'windows': [{'index': '18', 'x': 0},
                                                                            {'index': '25', 'x': 0}]})), 8)

    def test_message_window_rejects(self):
        rows = [[{'index': '25', 'y': 14}], [{'index': '18', 'h': 8}], [{'index': '25', 'y': 20, 'h': 8}],
                [{'index': '25', 'x': 1, 'w': 30}], [{'index': '25', 'w': 26}], [{'index': '25', 'x': 5}],
                [{'index': '18', 'x': 0}, {'index': '25', 'x': 4}]]
        for windows in rows:
            with self.subTest(windows=windows), self.assertRaises(ValueError):
                edits(self.rom, {'format': FORMAT, 'windows': windows})
        # 여는 바이트, 피연산자(24:A51F = B9), STA long 의 뱅크(24:A5EF = 7F)가 원래 꼴이 아니면 멈춘다.
        for addr, value in ((0x24A5EC, 0x8F), (0x24A51F, 0xB9), (0x24A5EF, 0x7F), (0x248852, 0x00)):
            with self.subTest(addr=hex(addr)), self.assertRaises(ValueError):
                edits(Rom(self.with_byte(addr, value)), {'format': FORMAT, 'windows': [{'index': '25', 'x': 4}]})
        moved = Rom(self.with_byte(self.first + 0x18 * 8, 0x04))
        with self.assertRaises(ValueError):
            edits(moved, {'format': FORMAT, 'windows': [{'index': '25', 'x': 3}]})

    def shaped(self, row, at=0x16FE10, fx_at=0x0BFC00):
        return patch(self.rom, {'format': FORMAT, 'windows': [{'index': '18', **row}]}, at=at, fx_at=fx_at)

    def test_message_window_shape(self):
        manifest = self.shaped({'x': 0, 'w': 31, 'h': 11})
        writes = {w['at']: w for w in manifest['writes']}
        table = records(self.rom)
        self.assertEqual(writes[f'04:{table[0x18] & 0xFFFF:04X}']['hex'], '00 91 1f 0b')
        self.assertEqual(writes[f'04:{table[0x25] & 0xFFFF:04X}']['hex'], '40 11 1f 0b')
        self.assertNotIn('orig', writes['16:FE10'])
        # 줄 수 5, 마지막 줄 4. 부분 전송은 17줄(1E20)부터 13줄, 효과 층은 7~16줄(0x280 바이트).
        self.assertEqual({k: writes[k]['hex'] for k in ('24:85FB', '24:8614', '24:864D', '24:8678', '24:A4FB',
                                                       '00:8E73', '00:8E7A', '00:8E82', '04:BCF1', '04:BCF5')},
                         {'24:85FB': '05', '24:8614': '04', '24:864D': '05', '24:8678': '05', '24:A4FB': '05',
                          '00:8E73': '20 1e', '00:8E7A': 'a0 01', '00:8E82': '40 54', '04:BCF1': '11', '04:BCF5': '12'})
        # ▼ 는 마지막 줄(26)·무리 넷(27)의 29칸, FD ▼ 는 1 + 13칸.
        self.assertEqual(writes['24:A51F']['hex'], 'ba 06')
        self.assertEqual(writes['24:A529']['hex'], 'fa 06')
        self.assertEqual(writes['24:8820']['hex'], '1a 00')
        self.assertEqual(writes['00:FD92']['hex'][:2], '22')
        rom = Rom(apply_new(self.data, manifest))
        self.assertEqual(message_at(rom), 0x16FE10)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(check(rom))
        self.assertEqual(edits(rom, {'format': FORMAT, 'windows': [{'index': '25', 'h': 11}]}), [])
        # 새 코드가 있는 롬은 --message-at 없이 다시 고치고, 원래 모양으로도 되돌린다(새 코드는 그대로).
        again = patch(rom, {'format': FORMAT, 'windows': [{'index': '25', 'x': 2, 'w': 28, 'h': 7}]})
        back = {w['at']: w['hex'] for w in again['writes']}
        self.assertEqual(back['24:A4FB'], '03')
        self.assertEqual(back['00:FD92'], 'a9 80 03 8d 75 43')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(check(Rom(apply_new(apply_new(self.data, manifest), again))))
        with self.assertRaises(ValueError):
            edits(rom, {'format': FORMAT, 'windows': [{'index': '25', 'w': 30}]}, at=0x15FE10)

    def test_message_window_shape_rejects(self):
        cases = [({'w': 30}, None), ({'h': 9, 'y': 21}, 0x16FE10), ({'h': 8}, 0x16FE10), ({'h': 15}, 0x16FE10),
                 ({'w': 27}, 0x16FE10), ({'x': 3, 'w': 30}, 0x16FE10), ({'h': 5}, 0x16FE10), ({'w': 30}, 0x16FFF0)]
        for row, at in cases:
            with self.subTest(row=row, at=at), self.assertRaises(ValueError):
                edits(self.rom, {'format': FORMAT, 'windows': [{'index': '18', **row}]}, at=at)
        # 격자 루틴 앞을 바꾼 롬은 X 만 옮겨도 멈춘다.
        with self.assertRaises(ValueError):
            edits(Rom(self.with_byte(0x24A5E9, 0x22)), {'format': FORMAT, 'windows': [{'index': '25', 'x': 4}]})

    def test_dq4_hooks(self):
        """DQ4 메뉴 빌드(sfc/dq4/tools/dq4windowname.asm)는 24:A4E0 에 JML, 24:A5E9 에 JSL 을 건다. 18·25 를 그대로 두면
        check·dump → patch 는 0 이고, X 만 옮기면 원래 도구처럼 24:A5EC 꼴에서, 모양을 바꾸면 격자 루틴 꼴에서 멈춘다."""
        data = bytearray(self.data)
        data[lorom(0x24A4E0):lorom(0x24A4E0) + 6] = bytes.fromhex('5c 00 81 30 ea ea')
        data[lorom(0x24A5E9):lorom(0x24A5E9) + 7] = bytes.fromhex('22 00 80 30 ea ea ea')
        rom = Rom(bytes(data))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(check(rom))
        self.assertEqual(patch(rom, dump(rom))['writes'], [])
        with self.assertRaisesRegex(ValueError, '24:A5EC'):
            edits(rom, {'format': FORMAT, 'windows': [{'index': '25', 'x': 4}]})
        data[lorom(0x24A5E9):lorom(0x24A5E9) + 7] = self.data[lorom(0x24A5E9):lorom(0x24A5E9) + 7]
        with self.assertRaisesRegex(ValueError, '격자 루틴'):
            edits(Rom(bytes(data)), {'format': FORMAT, 'windows': [{'index': '25', 'x': 4}]})
        with self.assertRaisesRegex(ValueError, '격자 루틴'):
            edits(Rom(bytes(data)), {'format': FORMAT, 'windows': [{'index': '18', 'w': 30}]}, at=0x16FE10)

    def test_message_code_runs(self):
        """옮긴 격자 루틴을 해석기로 돌려 원래 루틴과 같은 일을 하는지 본다: 채우기, 글자·탁점, 줄 지우기, 줄 올리기, 효과 층 크기."""
        x, y, w, h = 1, 15, 31, 13
        cols, rows, grid = w - 2, h - 1, GRID & 0xFFFF
        at = 0x16FE10
        code, labels = assemble(message_items(x, y, w, h), at)
        rom = bytearray(0x180000)
        rom[lorom(at):lorom(at) + len(code)] = code
        cpu = Cpu(bytes(rom), bytearray(0x20000))
        for wait in (0x04991D, 0x00950E):
            rom[lorom(wait)] = 0x6B
        cpu.rom = bytes(rom)
        cpu.dbr = 0x24

        def call(name, a=0, p=0x20):
            cpu.p, cpu.a, dbr = p, a, cpu.dbr
            cpu.jsl(labels[name])
            self.assertEqual(cpu.dbr, dbr)

        def cell(row, col):
            return cpu.wram[grid + row * cols + col]

        def screen(row, col):
            return cpu.wram[0x5000 + ((y + row) * 32 + x + 1 + col) * 2]

        call('fill')
        self.assertEqual([cell(0, c) for c in range(cols)], [0x8D] * cols)
        self.assertEqual({cell(r, c) for r in range(1, rows) for c in range(cols)}, {0x01})
        self.assertEqual(cpu.wram[grid + cols * rows], 0)
        cpu.wram[0x0F0D] = cpu.wram[0x0F0E] = 0
        for ch in (0x84, 0x20, 0x21):
            call('put', ch, 0x30)
        self.assertEqual((cell(0, 0), cell(1, 0), cell(1, 1), cpu.wram[0x0F0D]), (0x92, 0x20, 0x21, 2))
        self.assertEqual(screen(1, 1), 0x21)
        cpu.wram[0x0F0E], cpu.wram[0x0F0D] = 5, cols - 1
        call('put', 0x83, 0x30)
        call('put', 0x30, 0x30)
        self.assertEqual((cell(10, cols - 1), cell(11, cols - 1)), (0x83, 0x30))
        self.assertEqual((screen(10, cols - 1), screen(11, cols - 1)), (0x83, 0x30))
        # 줄 올리기: 줄 1(행 2·3)에 탁점 84 를 두면 올린 뒤 위 테두리에 92 로 얹힌다.
        cpu.wram[grid + 2 * cols + 3] = 0x84
        cpu.wram[grid + 3 * cols + 3] = 0x44
        call('scroll')
        self.assertEqual((cell(0, 3), cell(1, 3), cell(9, cols - 1), cell(11, cols - 1)), (0x92, 0x44, 0x30, 0x01))
        self.assertEqual(screen(1, 3), 0x44)
        cpu.wram[0x0F0E] = 1
        call('line', p=0x20)
        self.assertEqual({cell(r, c) for r in (2, 3) for c in range(cols)}, {0x01})
        cpu.wram[0x0F0E] = 0
        call('line', p=0x20)
        self.assertEqual(([cell(0, c) for c in range(cols)], cell(1, 3)), ([0x8D] * cols, 0x01))
        for vram, size in ((0x1CE0, (y - 7) * 64), (0x0CC0, 0x380)):
            cpu.wram[0x0F5E:0x0F60] = vram.to_bytes(2, 'little')
            cpu.io_writes.clear()
            cpu.dbr = 0
            call('eff', p=0x00)
            self.assertEqual([v for a, v in cpu.io_writes if a in (0x4305, 0x4306)], list(size.to_bytes(2, "little")))
            cpu.dbr = 0x24


    def test_effect_hooks(self):
        """창을 21줄 위로 올리면 연출 막기 훅을 걸고, 21줄로 되돌리면 원래 바이트로 둔다."""
        manifest = self.shaped({'h': 11})
        writes = {w['at']: w['hex'] for w in manifest['writes']}
        rom = Rom(apply_new(self.data, manifest))
        self.assertEqual(effects_at(rom), 0x0BFC00)
        _, labels = assemble(effect_items(17), 0x0BFC00)
        jsl = '22 ' + labels['color'].to_bytes(3, 'little').hex(' ')
        self.assertEqual({writes[f'{a >> 16:02X}:{a & 0xFFFF:04X}'] for a in COLOR_SITES}, {jsl})
        # 물결 표 머리: 55줄부터 창 맨 위 줄(17 × 8 - 1 = 135) 앞까지 80줄, 그 뒤 239 - 135 줄.
        self.assertEqual((writes['22:8EC7'], writes['22:8ECC']), ('d0', '68'))
        # NMI GP DMA 넷은 채널 7 → 0.
        self.assertEqual({writes[f'00:{a + 1 & 0xFFFF:04X}'] for a in DMA_STARTS}, {'01'})
        self.assertEqual(writes[f'00:{DMA_REGS[1] + 1 & 0xFFFF:04X}'], '01')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(check(rom))
        back = {w['at']: w['hex'] for w in patch(rom, {'format': FORMAT, 'windows': [{'index': '25', 'h': 7}]})['writes']}
        self.assertEqual((back['22:E175'], back['22:8EC7'], back[f'00:{DMA_REGS[1] + 1 & 0xFFFF:04X}']),
                         ('8f 31 21 00', 'f0', '71'))
        restored = Rom(apply_new(apply_new(self.data, manifest),
                                 patch(rom, {'format': FORMAT, 'windows': [{'index': '25', 'h': 7}]})))
        self.assertIsNone(effects_at(restored))
        with self.assertRaises(ValueError):
            self.shaped({'h': 11}, fx_at=None)

    def test_effect_code_runs(self):
        """$2131 쓰기 훅을 해석기로 돌린다: 표(직접 HDMA)·채널 7·$0D83, 화면 중간에 처음 켤 때 BG3 비트를 뺀 값을 쓰고,
        켜 둔 뒤에는 창 위 줄이면 원래 값(16비트면 $2132 도), 창 줄이면 BG3 비트를 뺀 값을 쓴다."""
        at, y = 0x0BFC00, 17
        code, labels = assemble(effect_items(y), at)
        rom = bytearray(0x180000)
        rom[lorom(at):lorom(at) + len(code)] = code
        cpu = Cpu(bytes(rom), bytearray(0x20000))
        line = {'v': 0}
        plain_read = cpu.read

        def read(a):
            if a & 0xFFFF == 0x213D:
                v, line['v'] = line['v'] & 0xFF, line['v'] >> 8
                return v
            return plain_read(a)
        cpu.read = read

        def call(a, p, v=0):
            line['v'] = v
            cpu.io_writes.clear()
            cpu.p, cpu.a = p, a
            cpu.jsl(labels['color'])
            return [(r, x) for r, x in cpu.io_writes if r in (0x2131, 0x2132, 0x420C)]

        ram = EFFECT_RAM & 0xFFFF
        self.assertEqual(call(0x47, 0x20), [(0x2131, 0x43)])
        self.assertEqual(bytes(cpu.wram[ram:ram + 7]), bytes([8, 0x47, 0x7F, 0x47, 1, 0x43, 0]))
        self.assertEqual(cpu.wram[0x0D83], 0x80)
        self.assertEqual([cpu.reg[0x4370 + i] for i in range(5)], [0x00, 0x31, ram & 0xFF, ram >> 8, 0x7E])
        self.assertEqual(call(0x00C3, 0x00, 100), [(0x2131, 0xC3), (0x2132, 0x00)])
        self.assertEqual(call(0x47, 0x20, 136), [(0x2131, 0x43)])
        self.assertEqual(call(0x0047, 0x00, 200), [(0x2131, 0x43), (0x2132, 0x00)])
        self.assertEqual(call(0x03, 0x20, 200), [(0x2131, 0x03)])
        self.assertEqual(cpu.wram[0x0D83], 0x80)


if __name__ == '__main__':
    unittest.main()
