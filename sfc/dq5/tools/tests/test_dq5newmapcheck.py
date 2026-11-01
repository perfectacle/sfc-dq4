"""새 맵 실측 도구가 출구 실측 도구의 옛 표 감시 구간을 바꾸지 않고 자기 구간을 넘기는지."""
import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5exitcheck
import dq5newmapcheck


def fake_mesence(seen):
    def run(mesence, *args, env, **_):
        seen.append(env)
        Path(env['SHOT_DIR'], 'warp.txt').write_text(
            'final map 0D/07 cell 8,10 layer 01 BE=80 sound 0\ndp86 -\nstale reads 0 -\n', encoding='utf-8')
    return run


class StaleTests(unittest.TestCase):
    def test_import_keeps_exitcheck_ranges(self):
        before = dict(dq5exitcheck.STALE)
        importlib.reload(dq5newmapcheck)
        self.assertEqual(dq5exitcheck.STALE, before)
        self.assertNotIn('doors', dq5exitcheck.STALE)

    def test_run_watches_given_ranges(self):
        case = ('doors-new', 'doors', '0D/07,8,10,1', 'wait:10', None)
        roms = {'doors': (Path('doors.sfc'), 0x2AEFF5, '')}
        seen = []
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(dq5exitcheck.dq5mesen, 'testrunner', fake_mesence(seen)):
            out = Path(tmp)
            (out / 'a').mkdir()
            dq5exitcheck.run(case, roms, Path('s.mss'), out / 'a', Path('mesence'), Path('lib'),
                             stale=dq5newmapcheck.STALE)
            (out / 'b').mkdir()
            dq5exitcheck.run(case, roms, Path('s.mss'), out / 'b', Path('mesence'), Path('lib'))
        self.assertEqual(seen[0]['STALE'], '01D2FC-01D8C1')
        self.assertNotIn('STALE', seen[1])


if __name__ == '__main__':
    unittest.main()
