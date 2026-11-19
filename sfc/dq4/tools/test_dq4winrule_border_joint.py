"""테두리 규칙: 다른 창 모서리가 변 위에 놓인 이음 모서리(08B)는, 그 창이 위 창에 가려 창으로 찾히지 않아도 걸지 않는다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4winwatch as ww  # noqa: E402
from test_dq4winwatch import V, draw, fake_rom  # noqa: E402
from test_dq4winrule_border import shot  # noqa: E402

CMD = (4, 2, 12, 13)            # 명령 창
WHO = (6, 6, 12, 15)            # 도구 「누구」 창(왼쪽 아래 모서리가 명령 창 아래 변 위)
INFO = (2, 6, 8, 17)            # 물건 정보 창: 「누구」 창의 위 두 모서리를 가림
TO = (9, 8, 16, 20)             # 「누구에게」 창: 오른쪽 아래 모서리를 가림


class CornerCountTest(unittest.TestCase):
    def setUp(self):
        self.ref = ww.Ref(fake_rom())
        self.m = [0x2C00] * 1024
        for w in (CMD, WHO, INFO, TO):
            draw(self.m, *w)
        self.m[12 * 32 + 6] = 0x2000 | V | 0x8B

    def border_hits(self, engine):
        return [(b[0], b[1]) for b in ww.check(shot(self.m), self.ref, engine=engine) if b[2] == '테두리']

    def test_joint_on_the_command_window_bottom_edge_passes(self):
        # 원본 DQ5 꼴: 「누구」 창은 모서리 셋이 가리고 이음 모서리 하나만 보여 창으로 찾히지 않는다
        self.assertNotIn((12, 6), self.border_hits([CMD, WHO, INFO, TO]))

    def test_joint_tile_where_no_window_corner_meets_fails(self):
        # 그 칸에 모서리가 놓인 창이 엔진 기록에도 화면에도 없으면, 우연히 08B 인 조각이다
        self.assertIn((12, 6), self.border_hits([CMD, INFO, TO]))

    def test_plain_edge_erased_next_to_the_joint_still_fails(self):
        self.m[12 * 32 + 4] = 0x2C00
        self.assertIn((12, 4), self.border_hits([CMD, WHO, INFO, TO]))


if __name__ == '__main__':
    unittest.main()
