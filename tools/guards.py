"""회귀 가드 목록 검사. 규칙은 .agents/skills/guards/SKILL.md (GUARD-01~03).

트랙마다 자기 폴더에 guards.toml 을 두고, 롬이 있어야 도는 실행 검사를 등록한다.

    [[check]]
    name = "dq4-compat-walk"            # PR 본문에 적는 이름(소문자·숫자·-)
    why = "무엇이 다시 깨지지 않게 하나"
    paths = ["sfc/dq4/tools/dq4prologue.py"]   # 이 파일을 바꾼 PR 은 이 검사를 돌린다(glob, ** 가능)
    run = "uv run --locked python ..."  # 돌리는 명령
    needs = ["rom"]                     # 돌리는 데 필요한 것(설명용)

사용:
  python tools/guards.py                         목록 형식만 검사
  python tools/guards.py --base origin/main      바뀐 파일로 걸리는 검사와 명령을 찍음(PR 올리기 전)
  python tools/guards.py --base SHA --pr-body FILE
                                                 걸린 검사마다 본문에 결과 줄이 있는지 봄(CI)

결과 줄: `- [x] <이름>: 통과 …` 또는 `- [x] <이름>: 해당 없음 — <이유>`. `실패` 가 든 줄은 실패로 친다.
"""
import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
NAME = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
FIELDS = {'name': str, 'why': str, 'paths': list, 'run': str, 'needs': list}


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def tracked():
    return [line for line in git('ls-files').splitlines() if line]


def matches(path, pattern):
    return PurePosixPath(path).full_match(pattern)


def load(files, read=lambda f: (ROOT / f).read_text(encoding='utf-8')):
    """(검사 목록, 문제 목록). 검사는 {'file': guards.toml, **항목}. files 는 추적 파일 목록."""
    checks, problems = [], []
    for toml in sorted(f for f in files if PurePosixPath(f).name == 'guards.toml'):
        try:
            data = tomllib.loads(read(toml))
        except tomllib.TOMLDecodeError as e:
            problems.append(f'{toml}: TOML 오류 {e}')
            continue
        for key in data:
            if key != 'check':
                problems.append(f'{toml}: 모르는 키 {key}')
        for i, item in enumerate(data.get('check', [])):
            where = f'{toml} check[{i}]'
            for key, kind in FIELDS.items():
                if not isinstance(item.get(key), kind):
                    problems.append(f'{where}: {key} 가 없거나 {kind.__name__} 가 아님')
            for key in item:
                if key not in FIELDS:
                    problems.append(f'{where}: 모르는 키 {key}')
            if isinstance(item.get('name'), str) and not NAME.match(item['name']):
                problems.append(f'{where}: 이름 {item["name"]!r} 은 소문자·숫자·- 만')
            if isinstance(item.get('paths'), list):
                if not item['paths']:
                    problems.append(f'{where}: paths 가 비어 있음')
                for pattern in item['paths']:
                    if not isinstance(pattern, str) or not any(matches(f, pattern) for f in files):
                        problems.append(f'{where}: paths {pattern!r} 에 맞는 추적 파일이 없음')
            checks.append({'file': toml, **item})
    seen = {}
    for c in checks:
        name = c.get('name')
        if name in seen:
            problems.append(f'{c["file"]}: 이름 {name} 이 {seen[name]} 에도 있음')
        seen.setdefault(name, c['file'])
    return checks, problems


def triggered(checks, changed):
    return [c for c in checks if any(matches(f, p) for f in changed for p in c.get('paths', []))]


def body_problems(checks, body):
    """걸린 검사마다 `- [x] 이름: 통과` 또는 `해당 없음 — 이유` 줄이 있어야 한다."""
    problems = []
    for c in checks:
        line = re.compile(rf'^\s*[-*]\s*\[[xX]\]\s*`?{re.escape(c["name"])}`?\s*:\s*(.+)$', re.M)
        found = [m[1].strip() for m in line.finditer(body)]
        if not found:
            problems.append(f'{c["name"]}: PR 본문에 결과 줄이 없음 (`- [x] {c["name"]}: 통과 …`)')
        elif any('실패' in r for r in found):
            problems.append(f'{c["name"]}: 결과 줄이 실패')
        elif not any(r.startswith('통과') or re.match(r'^해당 없음\s*[—-]\s*\S', r) for r in found):
            problems.append(f'{c["name"]}: 결과는 「통과 …」 또는 「해당 없음 — 이유」')
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', help='이 커밋과 HEAD 사이에 바뀐 파일로 걸리는 검사를 고른다')
    ap.add_argument('--pr-body', type=Path, help='PR 본문 파일. 걸린 검사의 결과 줄을 확인한다')
    args = ap.parse_args()
    files = tracked()
    checks, problems = load(files)
    if args.base:
        changed = [f for f in git('diff', '--name-only', f'{args.base}...HEAD').splitlines() if f]
        hit = triggered(checks, changed)
        if hit:
            print('이 변경이 건드리는 실행 검사(돌리고 PR 본문에 결과 줄):')
            for c in hit:
                print(f'- {c["name"]} ({c["file"]}): {c["why"]}\n    {c["run"]}')
                print(f'    본문 줄: - [x] {c["name"]}: 통과 …')
        else:
            print('걸리는 실행 검사 없음')
        if args.pr_body:
            problems += body_problems(hit, args.pr_body.read_text(encoding='utf-8'))
    elif args.pr_body:
        ap.error('--pr-body 는 --base 와 함께')
    for p in problems:
        print(f'오류: {p}')
    print(f'가드 {len(checks)}개, 문제 {len(problems)}개')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
