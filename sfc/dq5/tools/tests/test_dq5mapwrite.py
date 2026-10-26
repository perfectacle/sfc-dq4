"""맵 입력이 이웃 그룹의 포인터를 덮거나 필드를 버리지 않는지 검사한다."""
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5map import Rom, lorom  # noqa: E402
from dq5mapwrite import (  # noqa: E402
    FORMAT, GROUP_TABLE, HEADER, HIGH_GROUPS, all_maps, encode, main, parse, pointer_addr,
)


def fixture():
    data = bytearray(0x180000)
    for group in range(54):
        addr = GROUP_TABLE - 6 + min(group, 2) * 3
        off = lorom(GROUP_TABLE + group * 2)
        data[off:off + 2] = (addr & 0xFFFF).to_bytes(2, 'little')
    for group in range(5):
        off = lorom(HIGH_GROUPS + group * 2)
        data[off:off + 2] = (HIGH_GROUPS & 0xFFFF).to_bytes(2, 'little')
    return Rom(data)


def document():
    return {'format': FORMAT, 'map': '00/00', **dict.fromkeys(HEADER, 0),
            'width': 1, 'height': 1, 'bits': 1, 'commands': [['end']],
            'passes': [{'vertical': False, 'entries': []} for _ in range(3)]}


class MapInputTests(unittest.TestCase):
    def test_record_and_dump_metadata_roundtrip(self):
        doc = document()
        raw = encode(doc)
        data = bytearray(0x8000)
        data[:len(raw)] = raw
        decoded, size = parse(Rom(data), 0x008000)
        self.assertEqual(size, len(raw))
        self.assertEqual(encode(decoded), raw)
        decoded['map'] = '00/00'
        self.assertEqual(encode(decoded), raw)

    def test_top_level_fields_are_not_ignored(self):
        for field in ('exits', 'entries', 'placements', 'commmands'):
            doc = document()
            doc[field] = []
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, '지원하지 않는 맵 필드'):
                encode(doc)
        for doc in (None, [], {'format': FORMAT}):
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                encode(doc)

    def test_out_of_range_map_cannot_alias_next_group(self):
        rom = fixture()
        self.assertEqual(all_maps(rom), [(0, 0), (1, 0)])
        self.assertEqual(pointer_addr(rom, 1, 0), GROUP_TABLE - 3)
        for bc, bd in ((0, 1), (1, 1), (54, 0), (0x50, 0x50), (-1, 0)):
            with self.subTest(bc=bc, bd=bd), self.assertRaises(ValueError):
                pointer_addr(rom, bc, bd)

    def test_cli_rejects_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            rom_path, source, output = (folder / n for n in ('source.sfc', 'input.json', 'output.json'))
            rom_path.write_bytes(fixture().d)
            for change in ({'map': '00/01'}, {'map': '00/100'}, {'map': None}, {'exits': []}):
                doc = copy.deepcopy(document()) | change
                source.write_text(json.dumps(doc))
                output.write_text('keep')
                args = ['dq5mapwrite', str(rom_path), 'patch', str(source), '-o', str(output)]
                with self.subTest(change=change), patch.object(sys, 'argv', args), contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(main(), 1)
                self.assertIn('오류:', err.getvalue())
                self.assertEqual(output.read_text(), 'keep')
            with patch.object(sys, 'argv', ['dq5mapwrite', str(rom_path), 'dump', '00', '01']), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(), 1)


if __name__ == '__main__':
    unittest.main()
