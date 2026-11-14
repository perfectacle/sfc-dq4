import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dq4battlemsgcheck as bc


class RoundsTests(unittest.TestCase):
    def rounds(self, stall_again):
        """첫 차례 첫 묶음은 두 번째 번호(102) 뒤에서 멈춘다. stall_again 이면 다시 넣은 102 도 멈춘다."""
        calls = []

        def run(mesence, libdir, rom, state, out, ids, field=False):
            calls.append(list(ids))
            out.mkdir(parents=True)
            if len(calls) == 1:
                return [(0, n) for n in ids[:2]]
            if ids[0] == 0x102 and stall_again:
                return [(0, 0x102)]
            return [(0, n) for n in ids]

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'
            argv = ['x', '--rom', __file__, '--out', str(out), '--ids', '101,102,103,104', '--mesence', 'm',
                    '--jobs', '1']
            with mock.patch.object(sys, 'argv', argv), mock.patch.dict(os.environ, {'LIBDIR': tmp}), \
                    mock.patch.object(bc, 'run', run), mock.patch.object(bc.dq4freshstate, 'resolve',
                                                                         return_value=Path(tmp) / 's.mss'), \
                    mock.patch('builtins.print'):
                code = bc.main()
            report = json.loads((out / 'report.json').read_text())
        return calls, report, code

    def test_stalled_number_is_seen_again_alone_and_passes(self):
        """멈춘 번호는 다음 차례에 첫 메시지 자리(뒤에 찍힌 번호 하나)로, 남은 번호는 같은 묶음 크기로 다시 나눈다."""
        calls, report, code = self.rounds(stall_again=False)
        self.assertEqual(calls, [[0x101, 0x102, 0x103, 0x104], [0x102, 0x101], [0x103, 0x104]])
        self.assertEqual((report['stalled'], report['shown'], code), ([], 4, 0))

    def test_number_that_stalls_twice_is_stalled(self):
        calls, report, code = self.rounds(stall_again=True)
        self.assertEqual(report['stalled'], ['102'])
        self.assertEqual(code, 1)


if __name__ == '__main__':
    unittest.main()
