"""장 제목 상자 판정(dq4boxjudge)을 합성 화면과 빌드 제목으로 검사한다."""
import unittest

from PIL import Image

import dq4boxjudge as bj
import dq4chapterbox as cb


def screen(left=24, top=64, right=231, bottom=111, text=((40, 80),), sub=()):
    """금테 상자(두 점 굵기) + 파란 바탕 + 흰 점."""
    im = Image.new('RGB', (bj.SCREEN_W, bj.SCREEN_H))
    px = im.load()
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            ring = min(x - left, right - x, y - top, bottom - y) < 2
            px[x, y] = cb.GOLD if ring else cb.BLUE
    for x, y in (*text, *sub):
        px[x, y] = cb.WHITE
    return im


def kinds(im):
    return [k for k, _ in bj.judge(im)]


class JudgeTest(unittest.TestCase):
    def test_whole_box_passes(self):
        self.assertEqual(bj.judge(screen()), [])

    def test_no_box(self):
        self.assertEqual(kinds(Image.new('RGB', (256, 224))), ['상자 없음'])

    def test_broken_side(self):
        im = screen()
        for x in range(100, 104):
            for y in range(64, 66):
                im.putpixel((x, y), cb.BLUE)
        self.assertEqual(kinds(im), ['테두리'])

    def test_text_in_the_border_band(self):
        self.assertEqual(kinds(screen(text=((28, 80),))), ['글자 침범'])

    def test_box_cut_by_the_screen_edge(self):
        self.assertIn('화면 밖', kinds(screen(right=255)))

    def test_subtitle_cut_by_the_screen_edge(self):
        self.assertEqual(kinds(screen(sub=((255, 130),))), ['화면 밖'])


class TitleFormTest(unittest.TestCase):
    def test_table_titles_take_the_build_form(self):
        # 명칭표 제목 → 빌드 제목 꼴(form)이 빌드가 넣는 1~4장 제목을 그대로 만든다
        rows = {}
        for line in bj.ADOPT.read_text(encoding='utf-8').splitlines():
            cols = line.split('\t')
            if len(cols) > 3 and cols[0] == bj.TITLE_TABLE and cols[1].isdigit():
                rows[int(cols[1])] = cols[3]
        built = {cb.CHAPTER2.title, cb.ENDING2.title, cb.ENDING3.title}
        self.assertTrue(built <= {bj.form(rows[n]) for n in range(bj.FIRST_TITLE + 1, bj.FIRST_TITLE + 4)})

    def test_later_titles_are_previewed_once_with_and_without_subtitle(self):
        names = [n for n, _, _ in bj.preview_cases()]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn('chapter5', names)
        self.assertIn('chapter5-end', names)


@unittest.skipUnless(bj.FC_ROM.is_file(), 'rom/dq4.nes 가 필요')
class PreviewTest(unittest.TestCase):
    def test_every_title_fits_its_box(self):
        import os
        if not os.environ.get('DQ4_GALMURI'):
            self.skipTest('DQ4_GALMURI 가 필요')
        import dq4menupatch
        self.assertEqual(bj.run_preview(bj.FC_ROM.read_bytes(), dq4menupatch.Font('galmuri11')), [])


if __name__ == '__main__':
    unittest.main()
