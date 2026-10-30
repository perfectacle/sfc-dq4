"""빌드가 부르는 도구 하위 프로세스를 입력·도구 소스 해시를 키로 저장해 두고 다시 쓴다.

키는 도구 스크립트에서 import·도구 이름·데이터 파일 이름 문자열을 따라 닿는 도구 폴더의 파일, uv.lock, 파이썬 판,
인자로 만든다. 인자가 파일·폴더면 경로 대신 내용을 넣고, JSON 이면 그 안의 문자열 가운데 파일을 가리키는 것
(JSON 파일 기준 또는 현재 폴더 기준 경로)도 내용을 넣는다. 출력은 OUT_FLAGS 뒤의 경로와 표준 출력이다.
도구나 입력을 고치면 키가 바뀌어 저절로 다시 돌린다.

기본 자리는 원래 체크아웃의 work/cache/calls 라 워크트리끼리 함께 쓴다. DQ4_BUILD_CACHE 로 자리를 바꾸고,
DQ4_BUILD_CACHE=off 로 끈다. 롬에서 나온 자료라 커밋하지 않는다. 통째로 지워도 된다.
"""
import ast
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TOOL_DIRS = (HERE, ROOT / 'sfc' / 'dq5' / 'tools', ROOT / 'fc' / 'dq4' / 'tools')
FILE_NAME = re.compile(r'[\w.-]+\.\w+')
# 도구가 결과를 쓰는 인자. 이 뒤의 경로는 키에 넣지 않고(빌드마다 임시 폴더가 다름) 결과로 저장한다.
OUT_FLAGS = ('-o', '--out', '--ips', '--report')


@functools.cache
def _resolve(name):
    for d in TOOL_DIRS:
        if (d / name).is_file():
            return d / name
    return None


@functools.cache
def _refs(path):
    """path 가 import 하거나 이름으로 부르는 도구 폴더 파일. 함수 안의 import 와 'dq5build.py' 같은 이름 문자열도 든다."""
    if path.suffix != '.py':
        return ()
    refs = []
    for node in ast.walk(ast.parse(path.read_bytes())):
        if isinstance(node, ast.Import):
            refs += [a.name.split('.')[0] + '.py' for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            refs.append(node.module.split('.')[0] + '.py')
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and FILE_NAME.fullmatch(node.value):
            refs.append(node.value)
    return tuple(p for p in map(_resolve, dict.fromkeys(refs)) if p)


@functools.cache
def _digest(path):
    return hashlib.sha256(path.read_bytes()).digest()


def sources(*entries):
    """entries 에서 닿는 도구 폴더 파일."""
    seen, todo = set(), [Path(e).resolve() for e in entries]
    while todo:
        path = todo.pop()
        if path not in seen:
            seen.add(path)
            todo += _refs(path)
    return sorted(seen)


@functools.cache
def _tool_hash(tool):
    h = hashlib.sha256((ROOT / 'uv.lock').read_bytes() + sys.version.encode())
    for path in sources(tool):
        h.update(path.name.encode() + b'\0' + _digest(path))
    return h.hexdigest()


def _strings(doc):
    if isinstance(doc, str):
        yield doc
    elif isinstance(doc, dict):
        for v in doc.values():
            yield from _strings(v)
    elif isinstance(doc, list):
        for v in doc:
            yield from _strings(v)


def _content(path, h, seen):
    path = path.resolve()
    if path in seen:
        return
    seen.add(path)
    if path.is_dir():
        for p in sorted(path.rglob('*')):
            if p.is_file():
                h.update(str(p.relative_to(path)).encode() + b'\0')
                _content(p, h, seen)
        return
    data = path.read_bytes()
    h.update(hashlib.sha256(data).digest())
    if path.suffix != '.json':
        return
    try:
        doc = json.loads(data)
    except ValueError:
        return
    for s in _strings(doc):
        if len(s) > 255 or '\n' in s:
            continue
        for ref in (path.parent / s, Path(s)):
            if ref.is_file():
                h.update(s.encode() + b'\0')
                _content(ref, h, seen)
                break


def _key(tool, args):
    h = hashlib.sha256(_tool_hash(tool).encode() + Path(tool).name.encode())
    outs = []
    for i, a in enumerate(args):
        if i and args[i - 1] in OUT_FLAGS:
            outs.append(Path(a))
            h.update(f'\0out{len(outs)}'.encode())
        elif (os.sep in a or FILE_NAME.fullmatch(a)) and Path(a).exists():
            # 임시 폴더 경로는 빌드마다 달라 이름과 내용만 넣는다
            h.update(b'\0file' + Path(a).name.encode())
            _content(Path(a), h, set())
        else:
            h.update(b'\0arg' + a.encode())
    return h.hexdigest()[:40], outs


@functools.cache
def _main_checkout():
    try:
        out = subprocess.run(['git', '-C', str(ROOT), 'worktree', 'list', '--porcelain'],
                             capture_output=True, text=True, check=True).stdout
        return Path(out.splitlines()[0].removeprefix('worktree '))
    except (OSError, subprocess.CalledProcessError, IndexError):
        return ROOT


def cache_dir():
    env = os.environ.get('DQ4_BUILD_CACHE')
    if env == 'off':
        return None
    return Path(env) / 'calls' if env else _main_checkout() / 'work' / 'cache' / 'calls'


def _copy(src, dst):
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def run(tool, *args):
    """python tool args 의 표준 출력. 실패하면 RuntimeError(도구 이름·앞 인자 둘·표준 오류 끝)."""
    tool = Path(tool).resolve()
    args = [str(a) for a in args]
    cache = cache_dir()
    if cache is not None:
        key, outs = _key(tool, args)
        entry = cache / key
        if entry.is_dir():
            for k, out in enumerate(outs):
                if (entry / f'out{k}').exists():
                    _copy(entry / f'out{k}', out)
            return (entry / 'stdout').read_text(encoding='utf-8')
    proc = subprocess.run([sys.executable, str(tool), *args], capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(f"{tool.name} {' '.join(args[:2])}: {proc.stderr[-1500:]}")
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(dir=cache, prefix='.tmp-'))
        for k, out in enumerate(outs):
            if out.exists():
                _copy(out, tmp / f'out{k}')
        (tmp / 'stdout').write_text(proc.stdout, encoding='utf-8')
        try:
            os.rename(tmp, entry)
        except OSError:  # 다른 세션이 먼저 넣었다
            shutil.rmtree(tmp, ignore_errors=True)
    return proc.stdout
