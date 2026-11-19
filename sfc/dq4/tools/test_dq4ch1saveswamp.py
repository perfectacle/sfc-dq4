"""롬 없이: 독늪 장면이 엔진이 창을 다 지우기 전에 끝나지 않는지."""
import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4ch1savecheck as sc  # noqa: E402


class SwampTailTest(unittest.TestCase):
    def test_the_scene_rests_after_its_last_input(self):
        """창을 아래 줄부터 지우는 데 약 10프레임 걸린다(swamp-hoimin 3840~3852 실측). 그보다 넉넉히 쉬고 끝난다."""
        self.assertGreaterEqual(sc.SWAMP_TAIL, 60)
        self.assertIn("f',wait:{SWAMP_TAIL}'", inspect.getsource(sc.swamp_scene))


if __name__ == '__main__':
    unittest.main()
