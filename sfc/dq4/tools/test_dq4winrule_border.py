"""테두리 규칙이 설계된 창 꼴을 깨짐으로 걸지 않는지: 앞 쪽 위에 겹친 짧은 쪽(네네 보기 창), 위 변의 다음 쪽 표시 →."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4winwatch as ww  # noqa: E402
from test_dq4winwatch import H, TEXT, V, draw, fake_rom, planes, vram_chr  # noqa: E402

NEXT_PAGE = 0x7D
# 엔진 그리기 기록: 메시지 창 뒤 첫 쪽 목록. 짧은 둘째 쪽은 엔진 창 그리기를 거치지 않고 그 위에 그린다
ENGINE = [(17, 2, 27, 29), (3, 18, 20, 29)]
# 이음 모서리 08B: 롬 그림처럼 옆 변 선이 모서리를 지나 이어지는 T 자(겹친 창이 변을 나눌 때)
JOINT = ['21122222', '21111111', '21111111', '21122222', '21122222', '21122222', '21122222', '21122222']


def shot(m):
    chr_ = bytearray(vram_chr())
    p0, p1 = planes(JOINT)
    chr_[0x8B * 16:0x8B * 16 + 16] = bytes(x for pair in zip(p0, p1) for x in pair)
    return ww.Shot(1, 0, tuple(m), bytes(chr_), 0, 0)


class BorderDesignTest(unittest.TestCase):
    def setUp(self):
        self.ref = ww.Ref(fake_rom())
        self.m = [0x2C00] * 1024

    def hits(self, rule='테두리', engine=None):
        return sorted((b[0], b[1]) for b in ww.check(shot(self.m), self.ref, engine=engine) if b[2] == rule)

    def test_short_page_over_the_previous_page(self):
        # 메시지 창 위에 첫 쪽 목록(3~20줄)을 열고, 짧은 둘째 쪽(3~9줄)을 그 위에 겹친다. 첫 쪽의 아래 부분(10~20줄)은
        # 옆 변·아래 변과 함께 남고, 그 위 변은 둘째 쪽의 아래 변이다
        draw(self.m, 17, 2, 27, 29)
        draw(self.m, 3, 18, 20, 29)
        self.m[17 * 32 + 21] = 0x2000 | TEXT
        self.split()
        self.assertEqual(self.hits(engine=ENGINE), [])
        self.assertEqual(self.hits(), [])

    def split(self):
        draw(self.m, 3, 18, 9, 29)
        self.m[9 * 32 + 18] = 0x2000 | V | 0x8B
        self.m[9 * 32 + 29] = 0x2000 | H | V | 0x8B

    def test_message_border_erased_beside_the_split_list(self):
        draw(self.m, 17, 2, 27, 29)
        draw(self.m, 3, 18, 20, 29)
        self.split()
        self.m[17 * 32 + 10] = 0x2001
        self.assertEqual(self.hits(engine=ENGINE), [(17, 10)])

    def test_next_page_mark_on_top_edge(self):
        draw(self.m, 3, 18, 20, 29)
        self.m[3 * 32 + 19] = 0x2000 | NEXT_PAGE
        self.assertEqual(self.hits(), [])

    def test_next_page_mark_elsewhere_is_caught(self):
        draw(self.m, 3, 18, 20, 29)
        self.m[20 * 32 + 19] = 0x2000 | V | NEXT_PAGE
        self.m[10 * 32 + 29] = 0x2000 | H | NEXT_PAGE
        self.assertEqual(self.hits(), [(10, 29), (20, 19)])


if __name__ == '__main__':
    unittest.main()
