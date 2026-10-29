"""걸음 루틴 표: 합성 롬에서 제자리 쓰기·옮겨 늘리기를 65816 해석기로 돌려 보고, 입력 검사와 CLI 를 본다."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5stepwrite as step  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from test_dq5palsetwrite import apply, fixture, put  # noqa: E402
from w65816 import Cpu  # noqa: E402

# 00:C652~C688: 원래 찾기(RTL 로 끝남)와 기본 루틴 00:C687(CLC / RTS)
LOOKUP_CODE = bytes.fromhex('08 8b 4b ab e2 30 a5 be 10 1e a2 00 bd 89 c6 30 17 c5 bc f0 05 e8 e8 e8 80 f2'
                            ' bd 8a c6 8d ad 1a bd 8b c6 8d ae 1a 80 0a a9 87 8d ad 1a a9 c6 8d ae 1a ab 28 6b 18 60')
# 원본처럼 15그룹(46바이트). 루틴 주소는 그룹마다 다르게 만든 값
ROWS = [(g, 0xC300 + g * 0x10) for g in (0x1A, 0x01, 0x07, 0x03, 0x1D, 0x31, 0x06, 0x20, 0x04, 0x18, 0x32, 0x1F, 0x02,
                                         0x51, 0x54)]


def rom():
    r = fixture()
    data = bytearray(r.d)
    put(data, step.LOOKUP, LOOKUP_CODE)
    put(data, step.TABLE, step.encode(ROWS))
    return Rom(bytes(data))


def routine(r, group, inside=True):
    """롬의 00:C652 를 JSL 로 돌려 $1AAD 에 남는 루틴 주소."""
    wram = bytearray(0x20000)
    wram[0xBC], wram[0xBE] = group, 0x80 if inside else 0
    cpu = Cpu(r.d, wram)
    cpu.jsl(step.LOOKUP, max_steps=10_000)
    return cpu.wram[0x1AAD] | cpu.wram[0x1AAE] << 8


def document(*rows):
    return {'format': step.FORMAT, 'groups': [{'group': g, 'routine': r} for g, r in rows]}


class StepRoutineTests(unittest.TestCase):
    def setUp(self):
        self.rom = rom()

    def test_original_lookup_and_round_trip(self):
        self.assertEqual(routine(self.rom, 0x07), 0xC370)
        self.assertEqual(routine(self.rom, 0x36), step.DEFAULT)
        self.assertEqual(routine(self.rom, 0x07, inside=False), step.DEFAULT)
        doc = step.dump(self.rom)
        self.assertEqual(len(doc['groups']), 15)
        self.assertEqual(step.patch(self.rom, doc)['writes'], [])

    def test_in_place_swap_and_remove(self):
        moved = apply(self.rom, step.writes_for(self.rom, document(('01', '00:C385'), ('07', '00:C687'),
                                                                   ('22', '00:C419'))))
        self.assertEqual(step.step_table(moved), step.TABLE)
        self.assertEqual((routine(moved, 0x01), routine(moved, 0x07), routine(moved, 0x22)),
                         (0xC385, step.DEFAULT, 0xC419))
        self.assertEqual(routine(moved, 0x03), 0xC330)

    def test_new_group_grows_into_hooked_table(self):
        doc = document(('36', '00:C385'), ('35', '00:C419'))
        with self.assertRaisesRegex(ValueError, '--table-at'):
            step.writes_for(self.rom, doc, new_maps=[(0x36, 0)])
        writes = step.writes_for(self.rom, doc, '3C:A000', [(0x36, 0)])
        self.assertEqual([hex(w[0]) for w in writes], ['0x3ca000', hex(step.LOOKUP)])
        moved = apply(self.rom, writes)
        self.assertEqual(step.step_table(moved), 0x3CA000 + len(step.assemble(0x3CA000)))
        for g, r in ROWS:
            self.assertEqual(routine(moved, g), r)
        self.assertEqual((routine(moved, 0x36), routine(moved, 0x35), routine(moved, 0x08)),
                         (0xC385, 0xC419, step.DEFAULT))
        self.assertEqual(routine(moved, 0x36, inside=False), step.DEFAULT)
        self.assertEqual(len(step.dump(moved)['groups']), 17)
        with self.assertRaisesRegex(ValueError, '이미'):
            step.writes_for(moved, doc, '3C:A000', [(0x36, 0)])
        self.assertEqual(step.patch(self.rom, doc, '3C:A000', [(0x36, 0)])['rom_size'], 2)

    def test_rejects(self):
        cases = [
            ({'format': 'x', 'groups': []}, 'format'),
            (document(('36', '00:C385')), '롬에 없음'),
            (document(('01', '01:C385')), '뱅크 00'),
            (document(('01', '00:7FFF')), '뱅크 00'),
            (document(('01', '00:C660')), '찾기 루틴 자리'),
            (document(('01', '00:c385')), '16진'),
            (document(('1', '00:C385')), '16진'),
            (document(('01', '00:C385'), ('01', '00:C419')), '두 번'),
            ({'format': step.FORMAT, 'groups': [{'group': '01'}]}, 'group·routine'),
        ]
        for doc, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                step.writes_for(self.rom, doc, '3C:A000')
        many = document(*((f'{g:02X}', '00:C385') for g in range(0x36)), *((f'{g:02X}', '00:C385') for g in range(0x50, 0x55)))
        self.assertEqual(len(step.writes_for(self.rom, many, '3C:A000')[0][1]), len(step.assemble(0)) + 59 * 3 + 1)
        data = bytearray(self.rom.d)
        put(data, step.TABLE, step.encode(ROWS[:14]))
        with self.assertRaisesRegex(ValueError, '크기'):
            step.writes_for(Rom(bytes(data)), document())
        put(data, step.LOOKUP, b'\x5c\x00\x80\x3c')
        with self.assertRaisesRegex(ValueError, '찾기 루틴이 아님'):
            step.writes_for(Rom(bytes(data)), document())
        with self.assertRaisesRegex(ValueError, '뱅크 끝'):
            step.writes_for(self.rom, document(('01', '00:C385')), '3C:FFE0')

    def test_max_groups(self):
        with mock.patch.object(step, 'known_maps', return_value={g: {0} for g in range(0x60)}):
            doc = document(*((f'{g:02X}', '00:C385') for g in range(0x55)))
            with self.assertRaisesRegex(ValueError, '84그룹'):
                step.writes_for(self.rom, doc, '3C:A000')

    def test_cli_patch_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'rom.sfc').write_bytes(self.rom.d)
            (folder / 'in.json').write_text(json.dumps(document(('36', '00:C385'))), encoding='utf-8')
            argv = ['dq5stepwrite.py', str(folder / 'rom.sfc'), 'patch', str(folder / 'in.json'),
                    '-o', str(folder / 'out.json'), '--table-at', '3C:A000', '--new-map', '36/00']
            with mock.patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(step.main(), 0)
            manifest = json.loads((folder / 'out.json').read_text(encoding='utf-8'))
            self.assertEqual([w['at'] for w in manifest['writes']], ['3C:A000', '00:C652'])
            out = io.StringIO()
            argv = ['dq5stepwrite.py', str(folder / 'rom.sfc'), 'check', str(folder / 'in.json'), '--table-at', '3C:A000',
                    '--new-map', '36/00']
            with mock.patch.object(sys, 'argv', argv), contextlib.redirect_stdout(out):
                self.assertEqual(step.main(), 0)
            self.assertIn('항목 16개', out.getvalue())
            err = io.StringIO()
            argv[4:6] = []
            with mock.patch.object(sys, 'argv', argv), contextlib.redirect_stderr(err):
                self.assertEqual(step.main(), 1)
            self.assertIn('--table-at 이 필요함', err.getvalue())


if __name__ == '__main__':
    unittest.main()
