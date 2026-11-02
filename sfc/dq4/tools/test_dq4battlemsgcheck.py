import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dq4battlemsgcheck as bc


class RoundsTests(unittest.TestCase):
    def test_second_round_after_a_stall(self):
        """한 묶음이 멈추면 남은 번호를 다음 차례로 넘긴다. 차례 변수가 묶음 크기를 덮어 둘째 차례에서 죽은 적이 있다."""
        calls = []

        def run(mesence, libdir, rom, state, out, ids, field=False):
            calls.append(list(ids))
            out.mkdir(parents=True)
            # 첫 차례의 첫 묶음은 두 번째 번호 뒤에서 멈춘다
            return [(0, n) for n in (ids[:2] if len(calls) == 1 else ids)]

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'
            argv = ['x', '--rom', __file__, '--out', str(out), '--ids', '101,102,103,104', '--mesence', 'm']
            with mock.patch.object(sys, 'argv', argv), mock.patch.dict(os.environ, {'LIBDIR': tmp}), \
                    mock.patch.object(bc, 'run', run), mock.patch.object(bc.dq4freshstate, 'resolve',
                                                                         return_value=Path(tmp) / 's.mss'), \
                    mock.patch('builtins.print'):
                code = bc.main()
            report = json.loads((out / 'report.json').read_text())
        self.assertEqual(calls, [[0x101, 0x102, 0x103, 0x104], [0x103, 0x104]])
        self.assertEqual(report['stalled'], ['102'])
        self.assertEqual(code, 1)


if __name__ == '__main__':
    unittest.main()
