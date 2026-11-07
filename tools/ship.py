"""PR 마무리 한 줄. 규칙은 .agents/skills/git-workflow/SKILL.md (GIT-01·GIT-02), guards·ci·journal 스킬.

워크트리 안에서:

  uv run --locked python tools/ship.py --title "<PR 제목>" --body <본문 파일>

이 한 줄이 차례로 한다. 단계마다 `[단계] …` 한 줄을 찍고, 마지막 줄은 `SHIP: merged #N` 또는
`SHIP: stopped <단계> <이유>` 다. 긴 단계도 모두 포그라운드에서 스스로 기다린다.

  1 rebase   git fetch → origin/main 으로 rebase. 충돌이면 rebase 를 그대로 두고 멈춘다(--auto-lists 면 README·todo
             목록 파일의 목록 줄 충돌만 양쪽 줄을 다 살려 푼다). 끝나면 충돌 표시가 남았는지 본다.
  2 journal  이 브랜치가 더한 일지가 origin/main 의 같은 날짜·트랙 번호와 겹치거나 NN 이면 다음 빈 번호로 이름·제목·
             목록 줄을 고쳐 새 커밋을 만든다.
  3 checks   check_docs, 바뀐 .py compileall·.lua luac, 바뀐 파일에 닿는 단위 테스트(tests_for).
  4 guards   guards.py --base origin/main --run. 부하가 HEADLESS_SLOTS×2 를 넘으면 기다린다. 결과는 work/ship/ 에 남겨
             --rerun 과 충돌 뒤 다시 돌 때 합친다.
  5 body     본문 파일의 「## 가드」 절을 결과 줄로 넣거나 바꾸고 🤖 줄을 붙인 뒤 --pr-body 검사.
  6 push     원격에 같은 이름이 있으면 이 작업 것일 때만 --force-with-lease, 아니면 <브랜치>-2 같은 새 이름.
  7 pr       없으면 만들고 있으면 본문을 고친 뒤 gh pr merge --auto --merge.
  8 watch    30초마다 본다. 충돌이면 1 부터 다시, CI 실패면 실패 잡 로그 끝을 찍고 멈춘다.
  9 cleanup  머지되면 워크트리·로컬·원격 브랜치를 지우고 원래 체크아웃을 pull --ff-only.

옵션: --dry-run(아무것도 바꾸지 않고 계획만), --no-watch(7 까지), --skip-guards(걸린 실행 검사가 0개일 때만),
--rerun 이름,…(그 가드만 다시 돌려 앞 결과와 합침), --only 이름,…(guards.py --only 로 넘김), --auto-lists.
GH_TOKEN 이 없으면 `gh auth token -u perfectacle` 을 명령마다 넘긴다(전역 계정은 바꾸지 않는다).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_docs  # noqa: E402
import guards  # noqa: E402
import headless_slots  # noqa: E402

OWNER = 'perfectacle'
BASE = 'origin/main'
ROBOT = '🤖 Generated with [Claude Code](https://claude.com/claude-code)'
JOURNAL = re.compile(r'^(\d{4}-\d{2}-\d{2})-(\d{2,3}|NN)-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$')
LIST_LINE = re.compile(r'^\s*(?:[-*+] |\d+\. |\|)|^\s*$')
JOURNAL_ITEM = re.compile(r'^\s*[-*] \[(\d{4}-\d{2}-\d{2})-(\d{2,3}|NN): .*\]\(journal/')
STATUS = re.compile(r'^  ([a-z0-9-]+): (passed|failed|skipped) \((.*)\)$')
RESULT = re.compile(r'^- \[([x ])\] ([a-z0-9-]+): (.*)$')
# 이 파일들이 바뀌면 어느 테스트에 닿는지 가리기 어려워 모든 테스트 폴더를 돌린다
GLOBAL_INPUTS = {'uv.lock', 'pyproject.toml', '.python-version'}
FAILED_CHECK = {'FAILURE', 'TIMED_OUT', 'ACTION_REQUIRED', 'STARTUP_FAILURE', 'ERROR'}
POLL = 30


class Stop(Exception):
    def __init__(self, step, reason):
        super().__init__(f'{step} {reason}')
        self.step, self.reason = step, reason


# ---- 순수 함수(테스트가 바로 부름) -------------------------------------------------------------------------

def is_list_file(path):
    """양쪽 줄을 다 살려도 되는 목록 파일: README 와 todo."""
    return PurePosixPath(path).name in ('README.md', 'todo.md')


def union_conflicts(text):
    """충돌 표시 블록마다 main 쪽 줄 뒤에 이쪽 줄(같은 줄은 한 번)을 둔 글. 블록에 목록·표·빈 줄이 아닌 줄이 있거나
    블록이 닫히지 않으면 None — 산문은 두 쪽을 이어 붙이면 뜻이 깨진다."""
    lines = text.splitlines(keepends=True)
    out, i = [], 0
    while i < len(lines):
        if not check_docs.CONFLICT.match(lines[i]) or not lines[i].startswith('<'):
            out.append(lines[i])
            i += 1
            continue
        sides, cur = ([], [], []), 0
        i += 1
        while i < len(lines) and not lines[i].startswith('>' * 7):
            if lines[i].startswith('|' * 7):
                cur = 2  # diff3 의 base 쪽은 버린다
            elif check_docs.CONFLICT.match(lines[i]) and lines[i].startswith('='):
                cur = 1
            else:
                sides[cur].append(lines[i])
            i += 1
        if i == len(lines):
            return None
        block = sides[0] + [x for x in sides[1] if x not in sides[0]]
        if not all(LIST_LINE.match(x) for x in block):
            return None
        out += block
        i += 1
    return ''.join(out)


def has_markers(text):
    return any(check_docs.CONFLICT.match(x) for x in text.splitlines())


def number_group(path):
    """일지 번호를 함께 쓰는 묶음(check_docs.SHARED_NUMBERS: sfc/dq4 와 fc/dq4 는 하나)."""
    track = PurePosixPath(path).parent.parent.as_posix()
    return check_docs.SHARED_NUMBERS.get(track, track)


def journal_path(path):
    p = PurePosixPath(path)
    return (len(p.parts) == 4 and p.parts[2] == 'journal' and not p.parts[0].startswith('.')
            and JOURNAL.match(p.name) is not None)


def fmt_number(n):
    return f'{n:02d}'


def journal_renames(added, main_files):
    """[(옛 경로, 새 경로)]. added 는 이 브랜치가 더한 일지, main_files 는 origin/main 의 파일. NN 이거나 main 과
    (또는 앞서 정한 이 브랜치 일지와) 날짜·번호가 겹치면 그 날짜의 가장 큰 번호 + 1."""
    taken = {}
    for f in main_files:
        if journal_path(f):
            m = JOURNAL.match(PurePosixPath(f).name)
            if m[2] != 'NN':
                taken.setdefault(number_group(f), set()).add((m[1], int(m[2])))

    def order(f):
        m = JOURNAL.match(PurePosixPath(f).name)
        return m[1], (10 ** 6 if m[2] == 'NN' else int(m[2])), f
    renames = []
    for f in sorted((f for f in added if journal_path(f)), key=order):
        m = JOURNAL.match(PurePosixPath(f).name)
        used = taken.setdefault(number_group(f), set())
        if m[2] != 'NN' and (m[1], int(m[2])) not in used:
            used.add((m[1], int(m[2])))
            continue
        n = max((k for d, k in used if d == m[1]), default=0) + 1
        used.add((m[1], n))
        new = PurePosixPath(f).with_name(f'{m[1]}-{fmt_number(n)}-{m[3]}.md').as_posix()
        renames.append((f, new))
    return renames


def rename_refs(text, old, new):
    """글 안의 옛 일지 이름과 그 줄의 「[날짜-번호:」 표시를 새 것으로."""
    o, n = JOURNAL.match(PurePosixPath(old).name), JOURNAL.match(PurePosixPath(new).name)
    oldname, newname = PurePosixPath(old).name, PurePosixPath(new).name
    out = []
    for line in text.splitlines(keepends=True):
        if oldname in line:
            line = line.replace(oldname, newname).replace(f'[{o[1]}-{o[2]}:', f'[{n[1]}-{n[2]}:')
        out.append(line)
    return ''.join(out)


def retitle(text, old, new):
    o, n = JOURNAL.match(PurePosixPath(old).name), JOURNAL.match(PurePosixPath(new).name)
    head, sep, rest = text.partition('\n')
    return head.replace(f'# {o[1]}-{o[2]}:', f'# {n[1]}-{n[2]}:', 1) + sep + rest


def sort_journal_lists(text):
    """이어진 일지 목록 줄 묶음마다 날짜·번호 차례로(합치기로 줄 차례가 뒤집혀도 check_docs 가 통과하게)."""
    lines = text.splitlines(keepends=True)
    out, run = [], []

    def key(x):
        m = JOURNAL_ITEM.match(x)
        return m[1], (10 ** 6 if m[2] == 'NN' else int(m[2]))
    for x in lines + [None]:
        if x is not None and JOURNAL_ITEM.match(x):
            run.append(x)
            continue
        out += sorted(run, key=key)
        run = []
        if x is not None:
            out.append(x)
    return ''.join(out)


def guard_section(lines, full_lines=()):
    body = list(full_lines) + ([''] if full_lines else []) + (list(lines) or ['걸리는 실행 검사 없음.'])
    return ['## 가드', '', *body]


def build_body(body, lines):
    """본문의 「## 가드」 절을 결과 줄로 바꾸거나(없으면 끝에 넣고), 🤖 줄을 맨 끝에 하나 둔다. 옛 절의 `가드: 전체`
    줄은 남긴다(넓힌 판정을 지우면 CI 가 좁게 본다)."""
    rest = [x for x in body.rstrip('\n').split('\n') if not x.startswith('🤖 Generated with')]
    start = next((i for i, x in enumerate(rest) if re.match(r'^## 가드\s*$', x)), None)
    if start is None:
        while rest and not rest[-1].strip():
            rest.pop()
        full = [x for x in rest if guards.FULL_LINE.match(x)]
        rest = [x for x in rest if not guards.FULL_LINE.match(x)]
        rest += [''] + guard_section(lines, full)
    else:
        end = next((i for i in range(start + 1, len(rest)) if rest[i].startswith('## ')), len(rest))
        full = [x for x in rest[start:end] if guards.FULL_LINE.match(x)]
        new = guard_section(lines, full) + ([''] if end < len(rest) else [])
        rest = rest[:start] + new + rest[end:]
        while rest and not rest[-1].strip():
            rest.pop()
    return '\n'.join(rest + ['', ROBOT]) + '\n'


def remote_decision(known_local, prs):
    """원격에 같은 이름 브랜치가 있을 때: 'force'(이 작업 것) 또는 'rename'(남의 것). known_local 은 원격 커밋이 이
    브랜치의 조상이거나 reflog 에 있었는지. 모르는 커밋에 열린 PR 이 있으면 다른 세션이 살아 있는 작업이라 덮지 않는다."""
    states = {p['state'] for p in prs}
    if not known_local:
        return 'rename'
    if prs and 'OPEN' not in states:
        return 'rename'  # 이미 머지·닫힌 PR 의 브랜치: 같은 이름에 다시 올리면 옛 PR 에 묻힌다
    return 'force'


def free_name(branch, taken):
    k = 2
    while f'{branch}-{k}' in taken:
        k += 1
    return f'{branch}-{k}'


def passed(line):
    return line.startswith('- [x] ') and bool(guards.PASSED.match(line.split(': ', 1)[1]) or
                                              guards.NOT_APPLICABLE.match(line.split(': ', 1)[1]))


def parse_guards(output):
    """guards.py --run 출력에서 {이름: 본문 결과 줄}."""
    lines, on = {}, False
    for x in output.splitlines():
        if x.startswith('PR 본문 결과 줄:'):
            on = True
        elif on and (m := RESULT.match(x)):
            lines[m[2]] = x
    return lines


def touches(check, files):
    pats = check['paths'] + check.get('full_paths', [])
    return any(guards.matches(f, p) for f in files for p in pats)


def guards_to_run(hit, stored, touched, edited=()):
    """다시 돌릴 가드 이름. 앞서 가드를 돈 HEAD 뒤로 바뀐 파일(touched)이 걸린 가드의 paths·묶음·[full] 에 맞거나
    guards.toml 에서 run·needs 가 바뀐 가드는 다시, 앞 결과가 없거나 통과가 아닌 가드도 다시. 나머지(.md·목록만
    바뀐 rebase)는 앞 결과를 쓴다."""
    return [c['name'] for c in hit
            if c['name'] not in stored or not passed(stored[c['name']]) or c['name'] in edited or touches(c, touched)]


def test_dirs(ci_text):
    """CI test 잡 matrix 의 dir(중복 뺌, 차례 유지)."""
    return list(dict.fromkeys(re.findall(r'\{track: [^,]+, dir: ([^,}]+)', ci_text)))


def tests_for(changed, dirs, sources):
    """{테스트 폴더: [모듈 이름]}. sources 는 {경로: 글} (dirs 안의 .py 와 그 상위 폴더 .py).

    테스트는 바뀐 파일에 닿을 때만 고른다. 모듈은 이름이 다른 모듈 글에 낱말로 나오면(import·`이름.py` 를 띄우는
    subprocess) 그 모듈에 닿는다고 보고 전이로 따라간다. .py 밖 파일은 이름이 글에 나오는 모듈에 닿는다. 의존성 고정
    파일이 바뀌면 모든 폴더를 다 돈다."""
    words = {p: set(re.findall(r'\w+', t)) for p, t in sources.items()}
    whole = any(f in GLOBAL_INPUTS for f in changed)
    out = {}
    for d in dirs:
        here = [p for p in sources if PurePosixPath(p).parent.as_posix() == d]
        up = PurePosixPath(d).parent.as_posix() if PurePosixPath(d).name == 'tests' else None
        mods = here + [p for p in sources if up and PurePosixPath(p).parent.as_posix() == up]
        stem = {p: PurePosixPath(p).stem for p in mods}
        tests = sorted(p for p in here if PurePosixPath(p).name.startswith('test_'))
        if whole:
            if tests:
                out[d] = [stem[t] for t in tests]
            continue
        hit = {p for p in mods if p in changed}
        for f in changed:
            if f.endswith('.py') or f.endswith('.md'):
                continue
            name = PurePosixPath(f).name
            hit |= {p for p in mods if name in sources[p]}
        if not hit:
            continue
        deps = {p: {q for q in mods if q != p and stem[q] in words[p]} for p in mods}
        picked = []
        for t in tests:
            seen, todo = {t}, [t]
            while todo:
                for q in deps[todo.pop()]:
                    if q not in seen:
                        seen.add(q)
                        todo.append(q)
            if seen & hit:
                picked.append(stem[t])
        if picked:
            out[d] = picked
    return out


def check_job(url):
    m = re.search(r'/actions/runs/(\d+)/job/(\d+)', url or '')
    return m and m[2]


def fmt_secs(s):
    s = int(s)
    return f'{s // 60}분 {s % 60}초' if s >= 60 else f'{s}초'


# ---- 실행 ------------------------------------------------------------------------------------------------

class Ship:
    def __init__(self, root, args, gh=None, sleep=time.sleep, clock=time.time, out=None):
        self.root = Path(root)
        self.args = args
        self._gh = gh
        self.sleep = sleep
        self.clock = clock
        self.out = out or (lambda s: print(s, flush=True))
        self.t0 = clock()
        self.branch = None
        self.pr = None
        self.lines = {}
        self.auto = False
        self.token = None
        self.step = 'preflight'

    # 셸
    def git(self, *a, check=True, cwd=None, env=None):
        r = subprocess.run(['git', *a], cwd=cwd or self.root, capture_output=True, text=True,
                           env=dict(os.environ, **(env or {})))
        if check and r.returncode:
            tail = ((r.stderr or r.stdout).strip().splitlines() or [''])[-1]
            raise Stop(self.step, f'git {" ".join(a[:2])} 실패: {tail}')
        return r if not check else r.stdout

    def gh_env(self):
        if self.token is None:
            self.token = os.environ.get('GH_TOKEN') or self.gh(['auth', 'token', '-u', OWNER], raw=True).stdout.strip()
        return {'GH_TOKEN': self.token}

    def gh(self, a, check=True, raw=False):
        env = {} if raw else self.gh_env()
        if self._gh:
            r = self._gh(a, env)
        else:
            r = subprocess.run(['gh', *a], cwd=self.root, capture_output=True, text=True, env=dict(os.environ, **env))
        if check and r.returncode:
            raise Stop(self.step, f'gh {" ".join(a[:2])} 실패: {(r.stderr or r.stdout).strip()[-200:]}')
        return r

    def say(self, msg):
        self.out(f'[{self.step}] {msg}')

    def py(self, *a, cwd=None):
        return subprocess.run([sys.executable, *a], cwd=cwd or self.root, capture_output=True, text=True)

    def state_file(self):
        return self.root / 'work' / 'ship' / 'guards.json'

    def load_state(self):
        try:
            return json.loads(self.state_file().read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def save_state(self, head, lines):
        f = self.state_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({'head': head, 'lines': lines}, ensure_ascii=False, indent=1), encoding='utf-8')

    def head(self):
        return self.git('rev-parse', 'HEAD').strip()

    # 0
    def preflight(self):
        self.step = 'preflight'
        gitdir = Path(self.git('rev-parse', '--absolute-git-dir').strip())
        common = Path(self.git('rev-parse', '--path-format=absolute', '--git-common-dir').strip())
        if gitdir == common:
            raise Stop('preflight', '원래 체크아웃이 아니라 작업 워크트리 안에서 돌릴 것(GIT-02)')
        if (gitdir / 'rebase-merge').exists() or (gitdir / 'rebase-apply').exists():
            raise Stop('preflight', 'rebase 중: 충돌을 풀고 git add, git rebase --continue 한 뒤 다시')
        self.branch = self.git('rev-parse', '--abbrev-ref', 'HEAD').strip()
        if self.branch in ('main', 'master', 'HEAD'):
            raise Stop('preflight', f'브랜치가 {self.branch}: 작업 브랜치에서만')
        dirty = self.git('status', '--porcelain', '--untracked-files=no').splitlines()
        if dirty:
            raise Stop('preflight', f'커밋 안 된 변경: {" ".join(x[3:] for x in dirty[:5])}')
        if not self.args.body.is_file():
            raise Stop('preflight', f'본문 파일 없음 {self.args.body}')
        self.say(f'{self.branch}')

    # 1
    def rebase(self):
        self.step = 'rebase'
        self.git('fetch', '-q', 'origin', 'main')
        behind = int(self.git('rev-list', '--count', f'HEAD..{BASE}').strip())
        if self.args.dry_run:
            r = self.git('merge-tree', '--write-tree', '--name-only', BASE, 'HEAD', check=False)
            files = r.stdout.split('\n\n')[0].splitlines()[1:] if r.returncode == 1 else []
            self.say(f'main 이 {behind}개 앞섬' + (f', 충돌 예상: {" ".join(files)}' if files else ', 충돌 없음'))
            return
        if behind == 0:
            self.say('이미 최신 origin/main 위')
        else:
            r = self.git('rebase', BASE, check=False, env={'GIT_EDITOR': 'true'})
            fixed = []
            while r.returncode:
                files = [f for f in self.git('diff', '--name-only', '--diff-filter=U').splitlines() if f]
                if not files:
                    raise Stop('rebase', f'rebase 실패: {(r.stderr or r.stdout).strip()[-200:]}')
                bad = [f for f in files if not (self.args.auto_lists and is_list_file(f))]
                if not bad:
                    for f in files:
                        text = union_conflicts((self.root / f).read_text(encoding='utf-8'))
                        if text is None:
                            bad.append(f)
                            break
                        (self.root / f).write_text(text, encoding='utf-8')
                if bad:
                    for f in files:
                        self.out(f'  충돌: {f}')
                    raise Stop('rebase', f'충돌 {len(files)}개({" ".join(files)}): 풀고 git add, '
                                         'git rebase --continue 한 뒤 다시(rebase 는 그대로 둠)')
                self.git('add', '--', *files)
                fixed += files
                r = self.git('rebase', '--continue', check=False, env={'GIT_EDITOR': 'true'})
            self.say(f'main {behind}개 위로 옮김' + (f', 목록 충돌 양쪽 살림: {" ".join(fixed)}' if fixed else ''))
        left = [f for f in self.changed() if (self.root / f).is_file() and f.endswith(tuple(check_docs.TEXT_SUFFIXES))
                and has_markers((self.root / f).read_text(encoding='utf-8', errors='replace'))]
        if left:
            raise Stop('rebase', f'충돌 표시가 남음: {" ".join(left)}')

    def changed(self, base=BASE, head='HEAD'):
        return [f for f in self.git('diff', '--name-only', f'{base}...{head}').splitlines() if f]

    # 2
    def journal(self):
        self.step = 'journal'
        added = [x.split('\t')[-1] for x in self.git('diff', '--name-status', '--diff-filter=AR', f'{BASE}...HEAD')
                 .splitlines() if x]
        main = self.git('ls-tree', '-r', '--name-only', BASE).splitlines()
        renames = journal_renames(added, main)
        if not renames:
            self.say('고칠 순번 없음')
            return
        for old, new in renames:
            self.say(f'{PurePosixPath(old).name} → {PurePosixPath(new).name}')
        if self.args.dry_run:
            return
        md = [f for f in self.git('ls-files', '*.md').splitlines() if f]
        touched = set()
        # 높은 번호부터 바꿔야 03→04, 04→05 가 서로를 덮지 않는다
        for old, new in reversed(renames):
            self.git('mv', old, new)
            p = self.root / new
            p.write_text(retitle(p.read_text(encoding='utf-8'), old, new), encoding='utf-8')
            touched.add(new)
            for f in md:
                q = self.root / f
                if f == old or not q.is_file():
                    continue
                text = q.read_text(encoding='utf-8')
                if PurePosixPath(old).name in text:
                    q.write_text(rename_refs(text, old, new), encoding='utf-8')
                    touched.add(f)
        for f in sorted(touched):
            if PurePosixPath(f).name == 'README.md':
                q = self.root / f
                q.write_text(sort_journal_lists(q.read_text(encoding='utf-8')), encoding='utf-8')
        self.git('add', '--', *sorted(touched))
        tracks = sorted({PurePosixPath(n).parts[1] for _, n in renames})
        self.git('commit', '-q', '-m', f'docs({",".join(tracks)}): 일지 순번을 origin/main 다음 번호로')
        self.say(f'{len(renames)}개 고쳐 커밋')

    # 3
    def checks(self):
        self.step = 'checks'
        r = self.py('tools/check_docs.py')
        if r.returncode:
            for x in r.stdout.splitlines()[:20]:
                self.out(f'  {x}')
            raise Stop('checks', 'check_docs 실패')
        changed = [f for f in self.changed() if (self.root / f).is_file()]
        py = [f for f in changed if f.endswith('.py')]
        if py:
            r = self.py('-m', 'compileall', '-q', *py)
            if r.returncode:
                self.out((r.stdout + r.stderr)[-1500:])
                raise Stop('checks', 'compileall 실패')
        lua = [f for f in changed if f.endswith('.lua')]
        if lua and shutil.which('luac'):
            for f in lua:
                r = subprocess.run(['luac', '-p', f], cwd=self.root, capture_output=True, text=True)
                if r.returncode:
                    raise Stop('checks', f'luac {f}: {r.stderr.strip()[-200:]}')
        ci = self.root / '.github' / 'workflows' / 'ci.yml'
        dirs = test_dirs(ci.read_text(encoding='utf-8')) if ci.is_file() else []
        sources = {}
        for d in dirs:
            folders = {d} | ({PurePosixPath(d).parent.as_posix()} if PurePosixPath(d).name == 'tests' else set())
            for folder in folders:
                for p in (self.root / folder).glob('*.py'):
                    sources[p.relative_to(self.root).as_posix()] = p.read_text(encoding='utf-8', errors='replace')
        picked = tests_for(set(changed), dirs, sources)
        if self.args.dry_run:
            self.say('check_docs·compileall 통과, 돌릴 단위 테스트: ' +
                     ('; '.join(f'{d} {len(m)}개' for d, m in picked.items()) or '없음'))
            return
        n = 0
        for d, mods in picked.items():
            r = self.py('-m', 'unittest', '-q', *mods, cwd=self.root / d)
            if r.returncode:
                for x in (r.stdout + r.stderr).strip().splitlines()[-30:]:
                    self.out(f'  {x}')
                raise Stop('checks', f'단위 테스트 실패 ({d})')
            n += len(mods)
        self.say(f'check_docs·compileall 통과, 단위 테스트 {n}개 파일 통과'
                 + (f' ({", ".join(picked)})' if picked else ''))

    # 4
    def hit(self, full):
        files = [f for f in self.git('ls-files').splitlines() if f]
        checks, problems = guards.load(files, read=lambda f: (self.root / f).read_text(encoding='utf-8'))
        if problems:
            raise Stop('guards', f'guards.toml 문제: {problems[0]}')
        changed = self.changed()
        edited = self.edited(BASE, 'HEAD', changed, merge_base=True)
        return guards.triggered(checks, changed, edited, full)

    def edited(self, base, head, changed, merge_base=False):
        mb = self.git('merge-base', base, head).strip() if merge_base else base
        names = set()
        for f in changed:
            if PurePosixPath(f).name != 'guards.toml':
                continue
            show = [self.git('show', f'{rev}:{f}', check=False) for rev in (mb, head)]
            names |= guards.edited_checks(*(r.stdout if r.returncode == 0 else '' for r in show))
        return names

    def full(self):
        return self.args.full or bool(guards.FULL_LINE.search(self.args.body.read_text(encoding='utf-8')))

    def wait_load(self):
        slots = headless_slots.limit()
        if not slots:
            return
        waited, last = 0, -60
        while os.getloadavg()[0] > slots * 2 and waited < self.args.load_wait:
            if waited - last >= 60:
                self.say(f'부하 {os.getloadavg()[0]:.1f} > HEADLESS_SLOTS×2={slots * 2}, 기다림 {fmt_secs(waited)}')
                last = waited
            self.sleep(POLL)
            waited += POLL

    def guards(self):
        self.step = 'guards'
        full = self.full()
        hit = self.hit(full)
        names = [c['name'] for c in hit]
        if self.args.skip_guards:
            if hit:
                raise Stop('guards', f'--skip-guards 는 걸린 실행 검사가 0개일 때만(걸림: {", ".join(names)})')
            self.say('걸린 실행 검사 없음, 건너뜀')
            self.lines = {}
            return
        state = self.load_state()
        stored = state.get('lines', {})
        head = self.head()
        if state.get('head') and state['head'] != head:
            r = self.git('diff', '--name-only', state['head'], head, check=False)
            touched = r.stdout.split() if r.returncode == 0 else None
            edited = self.edited(state['head'], head, touched or []) if touched is not None else set()
        else:
            touched, edited = [], set()
        if touched is None:
            todo = names
        else:
            todo = guards_to_run(hit, stored, touched, edited)
        if self.args.rerun:
            todo = list(dict.fromkeys(todo + [n for n in self.args.rerun.split(',') if n]))
        if self.args.only:
            todo = [n for n in self.args.only.split(',') if n]
        if not hit and not todo:
            self.say('걸린 실행 검사 없음')
            self.lines = {}
            self.save_state(head, {})
            return
        if not todo:
            self.say(f'{len(hit)}개 모두 앞 결과를 씀(그 뒤 바뀐 파일이 가드 paths 에 안 닿음)')
            self.lines = {n: stored[n] for n in names}
            return
        if self.args.dry_run:
            self.say(f'걸림 {len(hit)}개: {", ".join(names) or "-"}; 돌릴 것: {", ".join(todo)}')
            self.lines = {n: stored.get(n, f'- [ ] {n}: (돌릴 차례)') for n in names}
            return
        self.wait_load()
        cmd = ['tools/guards.py', '--base', BASE, '--run']
        if full:
            cmd.append('--full')
        if self.args.only or set(todo) != set(names):
            cmd += ['--only', ','.join(todo)]
        log = self.root / 'work' / 'ship' / 'guards.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        self.say(f'{len(todo)}개 돌림: {", ".join(todo)} (로그 {log.relative_to(self.root)})')
        text = []
        with log.open('w', encoding='utf-8') as f:
            proc = subprocess.Popen([sys.executable, '-u', *cmd], cwd=self.root, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            for x in proc.stdout:
                f.write(x)
                text.append(x)
                if STATUS.match(x.rstrip('\n')):
                    self.out(f'  {x.strip()}')
            code = proc.wait()
        new = parse_guards(''.join(text))
        if code and not new:
            for x in [y for y in text if y.startswith('오류:')][:10]:
                self.out(f'  {x.rstrip()}')
            raise Stop('guards', f'guards.py 종료 코드 {code} (로그 {log.relative_to(self.root)})')
        merged = dict(stored, **new)
        bad = {n: merged.get(n, '') for n in todo if not passed(merged.get(n, ''))}
        # 실패한 결과는 남기지 않아 다음 실행이 그 가드를 다시 돌린다
        self.save_state(head, {n: v for n, v in merged.items() if passed(v)})
        if bad:
            for n, v in bad.items():
                self.out(f'  실패: {v or n + " (결과 줄 없음)"}')
            raise Stop('guards', f'실패 {",".join(bad)} — 고친 뒤 다시, 또는 --rerun {",".join(bad)}')
        self.lines = {n: merged[n] for n in names}
        self.say(f'{len(names)}개 통과')

    # 5
    def body(self):
        self.step = 'body'
        text = self.args.body.read_text(encoding='utf-8')
        new = build_body(text, list(self.lines.values()))
        if self.args.dry_run:
            sec = new.split('## 가드', 1)[1].split('\n## ', 1)[0].replace(ROBOT, '').strip()
            self.say('가드 절: ' + ' / '.join(sec.splitlines()))
            return
        if new != text:
            self.args.body.write_text(new, encoding='utf-8')
        r = self.py('tools/guards.py', '--base', BASE, '--pr-body', str(self.args.body.resolve()),
                    *(['--full'] if self.args.full else []))
        if r.returncode:
            for x in [y for y in r.stdout.splitlines() if y.startswith('오류:')][:10]:
                self.out(f'  {x}')
            raise Stop('body', '--pr-body 검사 문제')
        self.say('가드 절을 넣고 --pr-body 문제 0개')

    # 6
    def push(self):
        self.step = 'push'
        heads = {}
        for x in self.git('ls-remote', '--heads', 'origin', check=False).stdout.splitlines():
            sha, ref = x.split('\t')
            heads[ref.removeprefix('refs/heads/')] = sha
        remote = heads.get(self.branch)
        if remote is None:
            plan, target = 'new', self.branch
        else:
            known = (self.git('merge-base', '--is-ancestor', remote, 'HEAD', check=False).returncode == 0
                     or remote in self.git('reflog', '--format=%H', self.branch, '--', check=False).stdout.split())
            prs = json.loads(self.gh(['pr', 'list', '--head', self.branch, '--state', 'all',
                                      '--json', 'number,state']).stdout or '[]')
            plan = remote_decision(known, prs)
            target = self.branch if plan == 'force' else free_name(self.branch, heads)
        if self.args.dry_run:
            self.say({'new': f'새로 push {target}', 'force': f'{target} 에 --force-with-lease',
                      'rename': f'원격 {self.branch} 는 남의 것: {target} 로 push'}[plan])
            return
        if target in ('main', 'master'):
            raise Stop('push', 'main 에는 push 하지 않음')
        if plan == 'rename':
            self.git('branch', '-m', target)
            self.say(f'원격 {self.branch} 는 이 작업 것이 아님: 브랜치를 {target} 로 바꿈')
            self.branch = target
        lease = [f'--force-with-lease=refs/heads/{target}:{remote}'] if plan == 'force' else []
        self.git('push', '-q', *lease, '-u', 'origin', f'HEAD:refs/heads/{target}', env=self.gh_env())
        self.say(f'{target} ' + ('덮어 올림(--force-with-lease)' if plan == 'force' else '올림'))

    # 7
    def open_pr(self):
        self.step = 'pr'
        prs = json.loads(self.gh(['pr', 'list', '--head', self.branch, '--state', 'open',
                                  '--json', 'number,body']).stdout or '[]')
        body = self.args.body.read_text(encoding='utf-8')
        if self.args.dry_run:
            self.say(f'#{prs[0]["number"]} 본문 고침' if prs else 'PR 새로 만듦')
            return
        if prs:
            self.pr = prs[0]['number']
            # 본문을 고치면 CI 가 처음부터 다시 돌므로(GUARD-02) 같으면 건드리지 않는다
            if prs[0].get('body', '').strip() != body.strip():
                self.gh(['pr', 'edit', str(self.pr), '--body-file', str(self.args.body)])
                self.say(f'#{self.pr} 본문 고침')
            else:
                self.say(f'#{self.pr} 본문 그대로')
        else:
            if not self.args.title:
                raise Stop('pr', 'PR 을 새로 만들려면 --title')
            r = self.gh(['pr', 'create', '--base', 'main', '--head', self.branch, '--title', self.args.title,
                         '--body-file', str(self.args.body)])
            m = re.search(r'/pull/(\d+)', r.stdout)
            if not m:
                raise Stop('pr', f'PR 번호를 못 읽음: {r.stdout.strip()[-200:]}')
            self.pr = int(m[1])
            self.say(f'#{self.pr} 만듦')
        r = self.gh(['pr', 'merge', str(self.pr), '--auto', '--merge'], check=False)
        self.auto = r.returncode == 0
        self.say('auto-merge 켬' if self.auto else 'auto-merge 못 켬: ci-ok 초록이면 직접 머지')

    def cycle(self):
        self.rebase()
        self.journal()
        self.checks()
        self.guards()
        self.body()
        self.push()
        self.open_pr()

    # 8
    def watch(self):
        self.step = 'watch'
        deadline = self.clock() + self.args.watch_timeout
        last = None
        while True:
            v = json.loads(self.gh(['pr', 'view', str(self.pr), '--json',
                                    'state,mergeable,mergeStateStatus,statusCheckRollup']).stdout)
            if v['state'] == 'MERGED':
                self.say('MERGED')
                return
            if v['state'] == 'CLOSED':
                raise Stop('watch', f'#{self.pr} 이 머지 없이 닫힘')
            if v.get('mergeable') == 'CONFLICTING':
                self.say('main 과 충돌: 1 단계부터 다시')
                self.cycle()
                self.step = 'watch'
                continue
            checks = v.get('statusCheckRollup') or []
            bad = [c for c in checks if c.get('conclusion') in FAILED_CHECK]
            if bad:
                for c in bad:
                    self.out(f'  실패: {c.get("name")} {c.get("detailsUrl", "")}')
                    job = check_job(c.get('detailsUrl'))
                    if job:
                        r = self.gh(['run', 'view', '--job', job, '--log-failed'], check=False)
                        for x in r.stdout.strip().splitlines()[-25:]:
                            self.out(f'    {x}')
                raise Stop('watch', f'CI 실패 {",".join(c.get("name", "?") for c in bad)}')
            done = sum(1 for c in checks if c.get('status') == 'COMPLETED')
            ok = checks and all(c.get('conclusion') in ('SUCCESS', 'SKIPPED', 'NEUTRAL') for c in checks)
            if ok and not self.auto and v.get('mergeStateStatus') == 'CLEAN':
                self.gh(['pr', 'merge', str(self.pr), '--merge'])
                self.auto = True
            now = f'검사 {done}/{len(checks)} 끝, {v.get("mergeStateStatus")}'
            if now != last:
                self.say(now)
                last = now
            if self.clock() > deadline:
                raise Stop('watch', f'{fmt_secs(self.args.watch_timeout)} 넘게 머지 안 됨(#{self.pr})')
            self.sleep(POLL)

    # 9
    def cleanup(self):
        self.step = 'cleanup'
        main = Path(self.git('rev-parse', '--path-format=absolute', '--git-common-dir').strip()).parent
        left = self.git('status', '--porcelain').splitlines()
        if left:
            raise Stop('cleanup', f'워크트리에 커밋 안 된 변경이 있어 지우지 않음: {" ".join(x[3:] for x in left[:5])}')
        self.git('worktree', 'remove', str(self.root), cwd=main)
        self.git('branch', '-D', self.branch, cwd=main, check=False)
        self.git('push', '-q', 'origin', '--delete', self.branch, cwd=main, check=False, env=self.gh_env())
        self.git('worktree', 'prune', cwd=main)
        on = self.git('rev-parse', '--abbrev-ref', 'HEAD', cwd=main).strip()
        dirty = self.git('status', '--porcelain', '--untracked-files=no', cwd=main).strip()
        if on == 'main' and not dirty:
            r = self.git('pull', '-q', '--ff-only', cwd=main, check=False, env=self.gh_env())
            pulled = '원래 체크아웃 pull 함' if r.returncode == 0 else '원래 체크아웃 pull 실패(그대로 둠)'
        else:
            pulled = f'원래 체크아웃은 {on}{"·변경 있음" if dirty else ""}이라 pull 안 함'
        self.say(f'워크트리·브랜치 지움, {pulled} (셸은 {main} 로 옮길 것)')

    def summary(self):
        lines = list(self.lines.values())
        cached = sum('캐시:' in x for x in lines)
        g = f'가드 {len(lines)}개 통과' + (f'(캐시 {cached})' if cached else '') if lines else '가드 없음'
        self.out(f'요약: PR #{self.pr} · {g} · {fmt_secs(self.clock() - self.t0)}')

    def run(self):
        self.step = 'preflight'
        try:
            self.preflight()
            self.cycle()
            if self.args.dry_run:
                self.out('SHIP: dry-run ok')
                return 0
            if not self.args.watch:
                self.summary()
                self.out(f'SHIP: open #{self.pr}')
                return 0
            self.watch()
            self.cleanup()
            self.summary()
            self.out(f'SHIP: merged #{self.pr}')
            return 0
        except Stop as e:
            self.out(f'SHIP: stopped {e.step} {e.reason}')
            return 1


def parse(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--title', help='PR 제목(새로 만들 때 필요)')
    ap.add_argument('--body', type=Path, required=True, help='PR 본문 파일(「## 가드」 절과 🤖 줄을 고쳐 씀)')
    ap.add_argument('--dry-run', action='store_true', help='아무것도 바꾸지 않고 단계마다 할 일만 찍음')
    ap.add_argument('--watch', action=argparse.BooleanOptionalAction, default=True, help='머지까지 지켜보고 정리(기본 켬)')
    ap.add_argument('--skip-guards', action='store_true', help='실행 검사를 건너뜀(걸린 검사가 0개일 때만)')
    ap.add_argument('--rerun', metavar='이름,…', help='이 가드만 다시 돌려 앞 결과와 합침')
    ap.add_argument('--only', metavar='이름,…', help='guards.py --only 로 넘김(guards.py 를 바꾼 PR 의 대표 셋)')
    ap.add_argument('--full', action='store_true', help='guards.py --full(본문 `가드: 전체` 와 같음)')
    ap.add_argument('--auto-lists', action='store_true', help='README·todo 목록 줄 충돌은 양쪽 줄을 다 살려 품')
    ap.add_argument('--load-wait', type=int, default=1800, help='가드 전에 부하가 내리기를 기다릴 최대 초')
    ap.add_argument('--watch-timeout', type=int, default=5400, help='머지를 기다릴 최대 초')
    return ap.parse_args(argv)


def main(argv=None):
    args = parse(argv)
    root = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
                               check=True).stdout.strip())
    args.body = args.body.resolve()
    return Ship(root, args).run()


if __name__ == '__main__':
    sys.exit(main())
