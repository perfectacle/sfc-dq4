"""문서 검사. 규칙은 .agents/skills/journal/SKILL.md (JOURNAL-01, DOC-01).

- 일지는 트랙 폴더의 <플랫폼>/<게임>/journal/YYYY-MM-DD-NN-<주제>.md(아직 옮기지 않은 트랙은
  docs/journal/<트랙>/)이고, 제목의 날짜·순번이 파일 이름과 같다. 순번은 트랙마다 따로다.
- 한 트랙 안에 같은 날짜·순번의 일지가 둘 이상 없다(같은 트랙의 두 세션이 같은 번호를 잡은 경우).
- 트랙 README(옮기지 않은 트랙은 저장소 README)의 일지 목록에 모든 일지가 있고, 날짜·순번 순서다.
- 문서 안 상대 링크가 가리키는 파일이 있다.
- 추적 대상 텍스트 파일에 개인 경로가 없다.
- 추적 대상 텍스트 파일에 rebase·merge 충돌 표시가 남아 있지 않다.

사용:
  python tools/check_docs.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOURNAL = ROOT / 'docs' / 'journal'
# 아직 <플랫폼>/<게임>/ 폴더로 옮기지 않은 트랙. 옮기면 여기서 뺀다.
TRACKS = ()
# 한 트랙이 폴더 여럿에 걸치면 일지 순번을 함께 쓴다(같은 날짜·순번이 두 폴더에 있으면 안 됨).
SHARED_NUMBERS = {'sfc/dq4': 'dq4', 'fc/dq4': 'dq4'}
NAME = re.compile(r'^(\d{4}-\d{2}-\d{2})-(\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$')
TITLE = re.compile(r'^# (\d{4}-\d{2}-\d{2})-(\d{2}): \S')
LINK = re.compile(r'\]\(([^)\s]+)\)')
TEXT_SUFFIXES = {'.md', '.py', '.lua', '.sh', '.toml', '.yml', '.yaml', '.json'}
# 홈 폴더 절대 경로와 "~/" 로 시작하는 경로. 이 파일 자체는 검사하지 않는다.
PERSONAL = re.compile(r'(/Users/[^/\s]+|/home/[^/\s]+|(?<![\w.])~/)')
CONFLICT = re.compile(r'^(<{7}|={7}|>{7})( |$)')


def files():
    out = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard'],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.splitlines() if (ROOT / p).is_file()]


def journal_dirs():
    """(일지 폴더, 목록이 있는 README, README 안 링크 접두어)."""
    for track in TRACKS:
        yield JOURNAL / track, ROOT / 'README.md', f'docs/journal/{track}/'
    for d in sorted(ROOT.glob('*/*/journal')):
        if not d.parts[-3].startswith('.'):  # .agents/skills/journal 은 스킬이다
            yield d, d.parent / 'README.md', 'journal/'


def check_journal(errors):
    for p in sorted(JOURNAL.rglob('*.md')):
        if p.parent.parent != JOURNAL or p.parent.name not in TRACKS:
            errors.append(f'{p.relative_to(ROOT)}: 일지는 <플랫폼>/<게임>/journal/ 아래에 둠')
    shared = {}
    for folder, readme, prefix in journal_dirs():
        text = readme.read_text(encoding='utf-8') if readme.is_file() else ''
        listed = re.findall(r'\(' + re.escape(prefix) + r'([^)/]+)\)', text)
        group = SHARED_NUMBERS.get(folder.parent.relative_to(ROOT).as_posix(), folder)
        seen, names = shared.setdefault(group, {}), []
        for p in sorted(folder.glob('*.md')):
            m = NAME.match(p.name)
            if not m:
                errors.append(f'{p.relative_to(ROOT)}: 이름이 YYYY-MM-DD-NN-<주제>.md 가 아님')
                continue
            key = (m.group(1), m.group(2))
            if key in seen:
                errors.append(f'{p.relative_to(ROOT)}: {key[0]}-{key[1]} 이 {seen[key]} 와 겹침')
            seen[key] = p.relative_to(ROOT).as_posix()
            first = p.read_text(encoding='utf-8').splitlines()[0] if p.stat().st_size else ''
            t = TITLE.match(first)
            if not t or (t.group(1), t.group(2)) != key:
                errors.append(f'{p.relative_to(ROOT)}: 제목이 「# {key[0]}-{key[1]}: 주제」 가 아님')
            names.append(p.name)
        where = readme.relative_to(ROOT)
        for n in names:
            if n not in listed:
                errors.append(f'{where}: 일지 목록에 {prefix}{n} 이 없음')
        ordered = [n for n in listed if n in names]
        if ordered != sorted(ordered):
            errors.append(f'{where}: {folder.relative_to(ROOT)} 일지 목록이 날짜·순번 순서가 아님')


def check_links(paths, errors):
    for p in paths:
        if p.suffix != '.md':
            continue
        text = p.read_text(encoding='utf-8')
        # 코드 블록·인라인 코드 안의 괄호는 링크가 아니다.
        text = re.sub(r'```.*?```', '', text, flags=re.S)
        text = re.sub(r'`[^`\n]*`', '', text)
        for target in LINK.findall(text):
            if re.match(r'^[a-z]+:', target) or target.startswith('#'):
                continue
            path = target.split('#', 1)[0]
            if path and not (p.parent / path).exists():
                errors.append(f'{p.relative_to(ROOT)}: 링크 대상 없음 {target}')


def check_personal(paths, errors):
    me = Path(__file__).resolve()
    for p in paths:
        if p.suffix not in TEXT_SUFFIXES or p.resolve() == me:
            continue
        for i, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
            if PERSONAL.search(line):
                errors.append(f'{p.relative_to(ROOT)}:{i}: 개인 경로 {PERSONAL.search(line).group(0)}')


def check_conflicts(paths, errors):
    for p in paths:
        if p.suffix not in TEXT_SUFFIXES:
            continue
        for i, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
            if CONFLICT.match(line):
                errors.append(f'{p.relative_to(ROOT)}:{i}: 충돌 표시 {line[:7]}')


def main():
    errors = []
    paths = files()
    check_journal(errors)
    check_links(paths, errors)
    check_personal(paths, errors)
    check_conflicts(paths, errors)
    for e in errors:
        print(e)
    print(f'{len(errors)} errors')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
