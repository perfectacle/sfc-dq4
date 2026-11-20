"""알려진 깨짐 눈금은 장면을 폴더 꼬리 이름 하나로만 찾는다: 같은 장면을 다른 길(창 검사·호환 장면 window-high·io,
세이브 검사·save-high·save-io)로 돌려도 같은 판정이어야 한다. 실행 이름·감시 범위·가드 이름에 묶이면 다른 길에서
눈금이 안 맞아 main 이 빨개졌다."""
import fnmatch
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4winwatch as ww  # noqa: E402

RUNS = ('work/wc/out', 'work/compat-scenes/window-high', 'work/compat-scenes/window-io', 'work/ch1save',
        'work/compat-scenes/save-high', 'work/compat-scenes/save-io', 'work/screens', 'other/out')


def gauges():
    return [(rule.NAME, k) for rule in ww.rules() for k in getattr(rule, 'KNOWN', ())]


class TailNameTest(unittest.TestCase):
    def test_every_gauge_finds_its_scene_by_the_tail_name_alone(self):
        for name, k in gauges():
            with self.subTest(rule=name, scene=k.scene):
                tail = k.scene.removeprefix('*/')
                self.assertTrue(k.scene.startswith('*/') and tail and not set(tail) & set('/*?['), k.scene)
                self.assertTrue(all(fnmatch.fnmatch(f'/x/{run}/{tail}', k.scene) for run in RUNS))

    def test_same_record_judged_the_same_on_every_run_path(self):
        name, k = gauges()[0]
        rule = next(r for r in ww.rules() if r.NAME == name)
        # 그 장면의 눈금 칸을 모두 눈금 프레임 수만큼 걸리게(하나라도 빠지면 「걸리지 않음」 으로 실패)
        same = [g for g in rule.KNOWN if g.scene == k.scene]
        shot = SimpleNamespace(id=1, hs=0, vs=0, map=tuple([0] * 1024))
        cells = [(r, c, name, '시험', 'fail', g.frames) for g in same for r, c in g.cells]
        found = [(shot, 10, max(g.frames for g in same), cells)]
        got = set()
        for run in RUNS:
            with tempfile.TemporaryDirectory() as d:
                folder = Path(d) / run / k.scene.removeprefix('*/')
                folder.mkdir(parents=True)
                with mock.patch.object(ww, 'analyze', return_value=found), \
                        mock.patch.object(ww, 'run_hits', return_value=[]), \
                        mock.patch.object(ww, 'rules', return_value=[rule]), \
                        mock.patch.object(ww, 'picture', return_value=[]), \
                        mock.patch.dict('os.environ', {'DQ4_WINDOW_WATCH': 'rules'}):
                    _, failing = ww.report(folder, b'')
                lines = [ln for ln in (folder / ww.LOG).read_text(encoding='utf-8').splitlines() if ln.startswith('알려진')]
                got.add((failing, tuple(lines)))
        self.assertEqual(len(got), 1, got)
        self.assertEqual(next(iter(got))[0], 0)


if __name__ == '__main__':
    unittest.main()
