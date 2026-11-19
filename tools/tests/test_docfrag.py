import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import docfrag  # noqa: E402


def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')
    return p


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        write(self.root, 'sfc/dq4/todo.md', '- **기존**: 내용\n')
        write(self.root, 'sfc/dq4/docs/x-format.md', '# x\n\n## 남은 것\n\n- 옛 줄\n\n## 다음\n')

    def problems(self):
        return [(p.name, m) for p, m in docfrag.check(self.root)]

    def test_good_fragments_pass(self):
        write(self.root, 'sfc/dq4/todo.d/new-item.md', '- **새 항목**: 내용\n  - 이어짐\n')
        write(self.root, 'sfc/dq4/docs/remaining.d/x-format/a-b.md', '- **그림**: 아직\n')
        self.assertEqual(self.problems(), [])

    def test_bad_name_shape_and_missing_pair(self):
        write(self.root, 'sfc/dq4/todo.d/Bad_Name.md', '- **a**: b\n')
        write(self.root, 'sfc/dq4/todo.d/no-bullet.md', '그냥 글\n')
        write(self.root, 'sfc/dq4/todo.d/two.md', '- **a**: b\n그 다음 문단\n')
        write(self.root, 'sfc/dq4/docs/remaining.d/gone-format/c.md', '- **a**: b\n')
        got = self.problems()
        self.assertTrue(any(n == 'Bad_Name.md' and '이름' in m for n, m in got), got)
        self.assertTrue(any(n == 'no-bullet.md' and '불릿' in m for n, m in got), got)
        self.assertTrue(any(n == 'two.md' and '불릿 하나' in m for n, m in got), got)
        self.assertTrue(any('짝 문서' in m for _, m in got), got)

    def test_duplicate_title(self):
        write(self.root, 'sfc/dq4/todo.d/a.md', '- **같은**: 1\n')
        write(self.root, 'sfc/dq4/todo.d/b.md', '- **같은**: 2\n')
        got = self.problems()
        self.assertEqual(sorted(n for n, m in got if '같은 제목' in m), ['a.md', 'b.md'])


class ViewTest(unittest.TestCase):
    def test_remaining_section_stops_at_next_heading(self):
        text = '# x\n\n## 남은 것\n\n- 하나\n- 둘\n\n## 검사\n\n- 셋\n'
        self.assertEqual(docfrag.remaining_section(text), '## 남은 것\n\n- 하나\n- 둘\n')
        self.assertEqual(docfrag.remaining_section('# x\n'), '')

    def test_views_join_the_big_file_and_fragments(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, 'todo.md', '- **옛**: 1\n')
            write(d, 'todo.d/z.md', '- **새**: 2\n')
            out = docfrag.view_todo(d)
            self.assertIn('- **옛**: 1', out)
            self.assertIn('<!-- todo.d/z.md -->\n- **새**: 2', out)
            write(d, 'docs/y.md', '## 남은 것\n\n- 가\n')
            write(d, 'docs/remaining.d/y/k.md', '- **나**: 3\n')
            out = docfrag.view_remaining(Path(d) / 'docs' / 'y.md')
            self.assertIn('- 가', out)
            self.assertIn('- **나**: 3', out)


class RepoTest(unittest.TestCase):
    def test_tracked_fragments_are_valid(self):
        self.assertEqual(docfrag.check(), [])


if __name__ == '__main__':
    unittest.main()
