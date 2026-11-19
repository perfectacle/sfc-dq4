"""항목마다 파일 하나인 문서 조각. 여러 세션이 todo·형식 문서의 「남은 것」 끝에 한 줄씩 덧붙이다 나던 충돌을 없앤다.

새 항목은 기존 큰 파일을 고치지 않고 조각 파일 하나를 더한다(기존 내용은 옮기지 않는다).

  <플랫폼>/<게임>/todo.d/<항목>.md                    todo.md 에 더할 항목
  <플랫폼>/<게임>/docs/remaining.d/<문서>/<항목>.md   docs/<문서>.md 의 「남은 것」 에 더할 항목

조각은 todo.md 와 같은 불릿 한 덩이다: 첫 줄이 `- **제목**: …` 이고 이어지는 줄은 들여쓴다. 상대 링크는 조각 파일 위치 기준이다.
이름은 소문자·숫자·- 만. 항목을 끝내면 그 파일을 지운다(남은 항목이 줄어드는 것이 PR 에 한 파일 삭제로 보인다).
check_docs.py 가 형식·이름·짝 문서·제목 중복을 본다.

사용:
  python tools/docfrag.py todo sfc/dq4                  todo.md 와 조각을 이어 보여 줌
  python tools/docfrag.py remaining sfc/dq4/docs/x.md   그 문서의 「남은 것」 절과 조각을 이어 보여 줌
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*\.md$')
TITLE = re.compile(r'^- \*\*(.+?)\*\*')
REMAINING_HEADING = re.compile(r'^#{2,3} 남은 것\s*$')


def todo_dirs(root=ROOT):
    return sorted(Path(root).glob('*/*/todo.d'))


def remaining_dirs(root=ROOT):
    return sorted(Path(root).glob('*/*/docs/remaining.d/*'))


def fragments(folder):
    return sorted(p for p in Path(folder).glob('*.md') if p.is_file())


def check_fragment(path):
    """조각 하나의 문제 문장 목록."""
    out = []
    if not NAME.match(path.name):
        out.append('이름은 소문자·숫자·- 만(확장자 .md)')
    lines = path.read_text(encoding='utf-8').splitlines()
    first = next((x for x in lines if x.strip()), '')
    if not TITLE.match(first):
        out.append('첫 줄이 `- **제목**: …` 불릿이 아님')
    elif not first.split('**', 2)[2].lstrip(':： ').strip() and len([x for x in lines if x.strip()]) < 2:
        out.append('제목만 있고 내용이 없음')
    for x in lines:
        if x.strip() and not x.startswith((' ', '-')):
            out.append(f'불릿 하나만 둔다(들여쓰지 않은 줄 {x[:20]!r})')
            break
    return out


def check(root=ROOT):
    """[(조각 경로, 문제)]. 짝 문서 없음, 제목 중복 포함."""
    errors = []
    titles = {}
    for folder in todo_dirs(root):
        for p in fragments(folder):
            titles.setdefault((folder.parent, 'todo'), {}).setdefault(_title(p), []).append(p)
    for folder in remaining_dirs(root):
        doc = folder.parent.parent / f'{folder.name}.md'
        if not doc.is_file():
            errors.append((folder, f'짝 문서 {doc.name} 가 없음(폴더 이름은 docs/ 의 문서 이름)'))
        for p in fragments(folder):
            titles.setdefault((folder, 'remaining'), {}).setdefault(_title(p), []).append(p)
    for folder in [*todo_dirs(root), *remaining_dirs(root)]:
        for p in fragments(folder):
            errors += [(p, m) for m in check_fragment(p)]
        stray = [p for p in folder.iterdir() if p.is_file() and p.suffix != '.md']
        errors += [(p, '조각은 .md 만') for p in stray]
    for by_title in titles.values():
        for t, ps in by_title.items():
            if t and len(ps) > 1:
                errors += [(p, f'같은 제목 {t!r} 조각이 둘 이상') for p in ps]
    return errors


def _title(path):
    first = next((x for x in path.read_text(encoding='utf-8').splitlines() if x.strip()), '')
    m = TITLE.match(first)
    return m[1] if m else ''


def remaining_section(text):
    """형식 문서 글에서 「남은 것」 절(제목 줄 포함). 없으면 빈 글."""
    lines = text.splitlines()
    for i, x in enumerate(lines):
        if REMAINING_HEADING.match(x):
            level = len(x) - len(x.lstrip('#'))
            end = next((j for j in range(i + 1, len(lines))
                        if re.match(r'^#{1,%d} ' % level, lines[j])), len(lines))
            return '\n'.join(lines[i:end]).rstrip() + '\n'
    return ''


def view_todo(track):
    base = Path(track)
    parts = [(base / 'todo.md').read_text(encoding='utf-8').rstrip() + '\n'] if (base / 'todo.md').is_file() else []
    for p in fragments(base / 'todo.d'):
        parts.append(f'<!-- {p.relative_to(base)} -->\n' + p.read_text(encoding='utf-8').rstrip() + '\n')
    return '\n'.join(parts)


def view_remaining(doc):
    doc = Path(doc)
    parts = [remaining_section(doc.read_text(encoding='utf-8'))]
    for p in fragments(doc.parent / 'remaining.d' / doc.stem):
        parts.append(f'<!-- {p.relative_to(doc.parent)} -->\n' + p.read_text(encoding='utf-8').rstrip() + '\n')
    return '\n'.join(x for x in parts if x)


def main(argv):
    if len(argv) == 3 and argv[1] == 'todo':
        print(view_todo(argv[2]), end='')
        return 0
    if len(argv) == 3 and argv[1] == 'remaining':
        print(view_remaining(argv[2]), end='')
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
