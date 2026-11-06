"""guards.toml 실행 검사의 paths 가, 아래 길로 따라갈 수 있는 저장소 파일을 덮는지 본다.

검사 명령(run)에 적힌 스크립트(.py·.lua·.asm)와 `unittest discover -s 폴더 -p 패턴` 이 고르는 시험 파일에서 시작한다.

  .py   import(함수 안 import 포함)하는 저장소 모듈. 찾는 곳은 그 파일의 폴더, sfc/dq4/tools, sfc/dq5/tools,
        fc/dq4/tools, tools 차례다. 그리고 값이 파일 이름 하나뿐인 글자 상수 가운데 .py·.lua·.asm 으로 끝나는 것
        (하위 프로세스로 부르는 스크립트, 띄우는 Lua, asar 에 넣는 asm. dq4build.STAGES 도 여기서 잡힌다)
        값이 파일 이름 하나뿐인 글자 상수 가운데 .toml·.json·.args·.patch·.tsv 로 끝나는 자료 파일(저장소 경로 그대로, 아니면
        그 파일의 폴더, 그 위 폴더, 위 도구 폴더 차례로 찾는다)
  .lua  require 와 글자 상수의 .lua(같은 폴더, tools/lua, sfc/dq4/tools/lua, sfc/dq5/tools/lua)
  .asm  incsrc

docstring 과 빈칸이 든 글(도움말)은 보지 않는다.

못 보는 길(이런 길로 닿는 파일은 paths 에 손으로 적는다):
  - importlib·__import__ 로 불러오는 모듈
  - 변수·f-string·이어 붙이기로 만든 파일 이름(하위 프로세스 인자를 조립하는 것 포함. dq4build 단계는 STAGES 의
    글자 상수라 잡힌다), Lua 의 dofile·loadfile 에 계산한 경로를 주는 것
  - 계산한 이름으로 여는 자료 파일(폴더째 읽는 그림 등)과 환경 변수가 가리키는 파일, 저장소 밖 툴킷 Lua(LIBDIR)

sfc/dq4/guards.toml 은 [cache] key = "paths" 라 검사 결과 캐시 키가 그 검사의 paths·묶음에 맞는 코드만 본다(자료
파일은 어느 검사의 paths 에도 낱낱이 적히지 않았으면 모든 키에 든다. tools/guards.py key_scope). 이 시험이 그 근거다.

많은 검사가 함께 닿는 묶음은 guards.toml 의 [groups] 에 둔다. 묶음마다 뿌리를 GROUP_ROOTS 에 적고(이름이 같아야
함), 묶음은 그 뿌리에서 위 길로 닿는 파일을 덮어야 한다.

  uv run --locked python sfc/dq4/tools/dq4guardpaths.py            # 빠진 것을 검사·묶음마다 찍음
  uv run --locked python sfc/dq4/tools/dq4guardpaths.py --group ch1-build   # 그 묶음이 덮어야 할 파일
"""
import argparse
import ast
from functools import lru_cache
import re
import subprocess
import sys
import tomllib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
GUARDS = 'sfc/dq4/guards.toml'
TOOL_DIRS = ('sfc/dq4/tools', 'sfc/dq5/tools', 'fc/dq4/tools', 'tools')
LUA_DIRS = ('tools/lua', 'sfc/dq4/tools/lua', 'sfc/dq5/tools/lua')
# 묶음 이름과 그 뿌리 스크립트
GROUP_ROOTS = {
    'ch1-build': ('sfc/dq4/tools/dq4build.py',),
    'ch1-walk': ('sfc/dq4/tools/dq4ch1walkcheck.py',),
}
FILE_NAME = re.compile(r'[\w./-]+\.(?:py|lua|asm)')
# 코드가 글자 상수로 이름을 적어 읽는 자료 파일
DATA_NAME = re.compile(r'[\w./-]+\.(?:toml|json|args|patch|tsv)')
ENTRY = re.compile(r'((?:sfc|fc|tools)/[\w./-]+\.(?:py|lua|asm))')


@lru_cache(maxsize=1)
def tracked():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return frozenset(out.split())


def resolve(name, here, dirs):
    for d in (here, *dirs):
        c = f'{d}/{name}' if d else name
        if c in tracked():
            return c
    return None


def docstrings(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body \
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):
            out.add(id(n.body[0].value))
    return out


def py_refs(path):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    here = str(PurePosixPath(path).parent)
    docs = docstrings(tree)
    out = set()
    for n in ast.walk(tree):
        mods = []
        if isinstance(n, ast.Import):
            mods = [a.name.split('.')[0] for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            mods = [n.module.split('.')[0]]
        for m in mods:
            r = resolve(f'{m}.py', here, TOOL_DIRS)
            if r:
                out.add(r)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs \
                and FILE_NAME.fullmatch(n.value):
            name = PurePosixPath(n.value).name
            if name.endswith('.lua'):
                r = resolve(name, here, (f'{here}/lua', *LUA_DIRS))
            else:
                r = resolve(name, here, TOOL_DIRS)
            if r:
                out.add(r)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs \
                and DATA_NAME.fullmatch(n.value):
            r = n.value if n.value in tracked() else resolve(
                PurePosixPath(n.value).name, here, (str(PurePosixPath(here).parent), *TOOL_DIRS))
            if r:
                out.add(r)
    return out


def lua_refs(path):
    src = (ROOT / path).read_text(encoding='utf-8', errors='replace')
    here = str(PurePosixPath(path).parent)
    out = set()
    for m in re.findall(r'require\s*\(?\s*["\']([\w.]+)["\']', src):
        r = resolve(m.replace('.', '/') + '.lua', here, LUA_DIRS)
        if r:
            out.add(r)
    for m in re.findall(r'["\']([\w./-]+\.lua)["\']', src):
        r = resolve(PurePosixPath(m).name, here, LUA_DIRS)
        if r:
            out.add(r)
    return out


def asm_refs(path):
    src = (ROOT / path).read_text(encoding='utf-8', errors='replace')
    here = str(PurePosixPath(path).parent)
    out = set()
    for m in re.findall(r'^\s*incsrc\s+"?([^"\s;]+)"?', src, re.M):
        r = resolve(PurePosixPath(m).name, here, TOOL_DIRS)
        if r:
            out.add(r)
    return out


@lru_cache(maxsize=None)
def refs(path):
    if path.endswith('.py'):
        return frozenset(py_refs(path))
    if path.endswith('.lua'):
        return frozenset(lua_refs(path))
    if path.endswith('.asm'):
        return frozenset(asm_refs(path))
    return frozenset()


def closure(roots):
    seen, todo = set(), [r for r in roots if r in tracked()]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        todo += [r for r in refs(f) if r not in seen]
    return seen


def entries(run):
    """명령의 진입 파일: 적힌 스크립트 경로, 그리고 `unittest discover -s 폴더 -p 패턴` 이 고르는 시험 파일."""
    out = [t for t in ENTRY.findall(run) if t in tracked()]
    for part in re.split(r'&&|\|\||[;|()]', run):
        if 'discover' not in part.split():
            continue
        s = re.search(r'(?:-s|--start-directory)\s+(\S+)', part)
        p = re.search(r'(?:-p|--pattern)\s+(\S+)', part)
        folder = s[1].rstrip('/') if s else '.'
        pattern = p[1] if p else 'test*.py'
        out += sorted(f for f in tracked() if PurePosixPath(f).parent == PurePosixPath(folder)
                      and PurePosixPath(f).match(pattern) and f not in out)
    return out


def covered(path, patterns):
    return any(PurePosixPath(path).full_match(p) for p in patterns)


def load(text=None):
    data = tomllib.loads(text if text is not None else (ROOT / GUARDS).read_text(encoding='utf-8'))
    groups = data.get('groups', {})
    checks = []
    for c in data.get('check', []):
        pats = [*c.get('paths', []), *(p for g in c.get('groups', []) for p in groups.get(g, []))]
        checks.append({**c, 'all_paths': pats})
    return checks, groups


def missing(checks, groups):
    """({검사 이름: 빠진 파일}, {묶음 이름: 빠진 파일})."""
    by_check = {}
    for c in checks:
        need = closure(entries(c['run']))
        miss = sorted(f for f in need if not covered(f, c['all_paths']))
        if miss:
            by_check[c['name']] = miss
    by_group = {}
    for g, roots in GROUP_ROOTS.items():
        miss = sorted(f for f in closure(roots) if not covered(f, groups.get(g, [])))
        if miss:
            by_group[g] = miss
    return by_check, by_group


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--group', choices=sorted(GROUP_ROOTS), help='그 묶음이 덮어야 할 파일을 찍는다')
    a = ap.parse_args()
    if a.group:
        for f in sorted(closure(GROUP_ROOTS[a.group])):
            print(f)
        return 0
    checks, groups = load()
    by_check, by_group = missing(checks, groups)
    for g, miss in by_group.items():
        print(f'묶음 {g}: 빠짐 {len(miss)}개')
        for f in miss:
            print(f'  "{f}",')
    for name, miss in by_check.items():
        hint = [g for g, roots in GROUP_ROOTS.items() if any(r in closure(entries(next(
            c['run'] for c in checks if c['name'] == name))) for r in roots)]
        print(f'{name}: 빠짐 {len(miss)}개' + (f' (묶음 {", ".join(hint)} 를 쓰면 줄어듦)' if hint else ''))
        for f in miss:
            print(f'  "{f}",')
    return 1 if by_check or by_group else 0


if __name__ == '__main__':
    sys.exit(main())
