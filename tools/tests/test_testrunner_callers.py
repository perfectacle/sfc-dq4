"""MesenCE 를 직접 띄우는 코드는 공통 러너 파일에만 있어야 한다.

직접 띄우면 머신 전체의 헤드리스 에뮬레이터 자리(tools/headless_slots.py)를 잡지 않아, 여러 세션이 함께 돌 때
에뮬레이터가 HEADLESS_SLOTS 보다 많이 뜬다. Python 도구는 dq4mesen(run·Runner·testrunner)이나 dq5mesen 을,
셸 스크립트는 `uv run --locked python sfc/dq4/tools/dq4mesen.py 인자…` 를 부른다.
"""
import ast
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
# 이 파일은 검사 예제로 우회 꼴을 그대로 담고 있어 뺀다
RUNNERS = {'sfc/dq4/tools/dq4mesen.py', 'sfc/dq5/tools/dq5mesen.py', 'tools/tests/test_testrunner_callers.py'}
FLAG = '--testrunner'
EMULATOR = {'mesence', 'mesen'}
SUBPROCESS = {'run', 'Popen', 'call', 'check_call', 'check_output', 'getoutput', 'getstatusoutput'}
SHELL_FLAG = re.compile(r'(?<![\w-])--testrunner(?![\w-])')
# ${MESENCE:?…} 같은 확인은 띄우는 것이 아니다
SHELL_EMULATOR = re.compile(r'\$\{?MESENCE(?![\w:])')


def _docstrings(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


def fold(node):
    """문자열 상수로 접을 수 있으면 그 값. 접히지 않는 조각(f-string 의 값)은 빈칸으로 둔다."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = fold(node.left), fold(node.right)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return fold(node.left)
    if isinstance(node, ast.JoinedStr):
        return ''.join(fold(v) if isinstance(v, ast.Constant) else (fold(v.value) or ' ') for v in node.values)
    if isinstance(node, ast.FormattedValue):
        return fold(node.value)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'join'
            and len(node.args) == 1 and isinstance(node.args[0], (ast.List, ast.Tuple))):
        sep, parts = fold(node.func.value), [fold(e) for e in node.args[0].elts]
        return None if sep is None or None in parts else sep.join(parts)
    return None


def _aliases(tree):
    """import 별칭: 모듈 이름 → 원래 모듈, from-import 한 이름 → (모듈, 함수)."""
    modules, names = {'subprocess': 'subprocess', 'os': 'os', 'asyncio': 'asyncio'}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in ('subprocess', 'os', 'asyncio'):
                    modules[a.asname or a.name] = a.name
        elif isinstance(node, ast.ImportFrom) and node.module in ('subprocess', 'os', 'asyncio'):
            for a in node.names:
                names[a.asname or a.name] = (node.module, a.name)
    return modules, names


def _launch(func, modules, names):
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in modules:
        target = (modules[func.value.id], func.attr)
    elif isinstance(func, ast.Name) and func.id in names:
        target = names[func.id]
    else:
        return None
    module, fn = target
    if module == 'subprocess' and fn in SUBPROCESS:
        return target
    if module == 'os' and (fn in ('system', 'popen', 'posix_spawn', 'posix_spawnp') or fn.startswith(('exec', 'spawn'))):
        return target
    if module == 'asyncio' and fn in ('create_subprocess_exec', 'create_subprocess_shell'):
        return target
    return None


def _emulator(node, tainted):
    """node 가 MesenCE 실행 파일(이나 그것으로 시작하는 명령)을 가리키는지."""
    if isinstance(node, (ast.List, ast.Tuple)):
        return bool(node.elts) and _emulator(node.elts[0], tainted)
    if isinstance(node, ast.Starred):
        return _emulator(node.value, tainted)
    if isinstance(node, ast.BinOp):
        return _emulator(node.left, tainted)
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and (sub.id.lower() in EMULATOR or sub.id in tainted):
            return True
        if isinstance(sub, ast.Attribute) and sub.attr.lower() in EMULATOR:
            return True
        if isinstance(sub, ast.Constant) and sub.value == 'MESENCE':
            return True
    return False


def _tainted(tree):
    """MesenCE 실행 파일이나 그것으로 시작하는 명령을 담는 이름. 대입을 따라 더 늘지 않을 때까지 넓힌다."""
    pairs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            pairs += [(t, node.value) for t in node.targets]
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
            pairs.append((node.target, node.value))
    tainted = set()
    while True:
        more = {t.id for t, v in pairs if isinstance(t, ast.Name) and t.id not in tainted and _emulator(v, tainted)}
        if not more:
            return tainted
        tainted |= more


def _command(call, target):
    module, fn = target
    if module == 'os' and fn.startswith('spawn'):
        return call.args[1] if len(call.args) > 1 else None
    if call.args:
        return call.args[0]
    return next((k.value for k in call.keywords if k.arg in ('args', 'cmd', 'program', 'path')), None)


def problems(source, name='<src>'):
    """FLAG 로 접히는 문자열과, MesenCE 를 실행 파일로 받는 subprocess·os·asyncio 실행 호출을 줄마다 알린다."""
    tree = ast.parse(source)
    docs = _docstrings(tree)
    modules, names = _aliases(tree)
    tainted = _tainted(tree)
    found = set()
    for node in ast.walk(tree):
        if id(node) not in docs:
            text = fold(node)
            if text and FLAG in text.split():
                found.add((node.lineno, FLAG))
        if not isinstance(node, ast.Call):
            continue
        target = _launch(node.func, modules, names)
        cmd = target and _command(node, target)
        if cmd is not None and target and _emulator(cmd, tainted):
            found.add((node.lineno, '.'.join(target) + ' 로 MesenCE'))
    return [f'{name}:{line}: {what}' for line, what in sorted(found)]


def shell_problems(text, name='<sh>'):
    """셸 스크립트에서 --testrunner 나 $MESENCE 를 쓰는 줄(주석 빼고)."""
    found = []
    for i, line in enumerate(text.splitlines(), 1):
        code = line.split(' #', 1)[0]
        if code.lstrip().startswith('#'):
            continue
        if SHELL_FLAG.search(code) or SHELL_EMULATOR.search(code):
            found.append(f'{name}:{i}: {line.strip()}')
    return found


def _lines(found):
    return [int(p.split(':')[1]) for p in found]


class CheckerTests(unittest.TestCase):
    def test_finds_direct_launches(self):
        src = '''
import os, subprocess
subprocess.run([str(mesence), '--testrunner', rom, lua], timeout=9)
cmd = [mesen, "--testrunner", rom]
subprocess.Popen([os.environ['MESENCE'], rom])
subprocess.run(args=[args.mesen, rom])
'''
        self.assertEqual(_lines(problems(src)), [3, 3, 4, 5, 6])

    def test_finds_emulator_through_assignments(self):
        src = '''
import os, subprocess
exe = os.environ['MESENCE']
subprocess.run([exe, rom])
path = Path(args.mesen)
argv = [str(path), rom]
subprocess.Popen(argv)
full = argv + extra
subprocess.call(full)
'''
        self.assertEqual(_lines(problems(src)), [4, 7, 9])

    def test_finds_folded_flag(self):
        src = '''
a = '--' + 'testrunner'
b = f'--test{"runner"}'
c = f'{exe} --testrunner {rom}'
d = ''.join(['--', 'test', 'runner'])
e = '%s --testrunner' % exe
'''
        self.assertEqual(_lines(problems(src)), [2, 3, 4, 5, 6])

    def test_finds_aliased_launchers(self):
        src = '''
import subprocess as sp
import os as o
from subprocess import run, Popen as P
from os import execv, system
sp.run([mesence, rom])
run([mesence, rom])
P([mesence, rom])
o.system(f'{mesence} {rom}')
system(mesence + ' ' + rom)
execv(mesence, [mesence, rom])
o.spawnv(o.P_WAIT, mesence, [mesence, rom])
o.execvp(args.mesen, [rom])
'''
        self.assertEqual(_lines(problems(src)), list(range(6, 14)))

    def test_allows_runners_and_children(self):
        src = '''
"""MesenCE --testrunner 를 부른다."""
import subprocess, sys
dq5mesen.testrunner(mesence, rom, lua, timeout=9)
subprocess.run([sys.executable, 'dq5x.py', '--mesence', mesence])
child = [sys.executable, 'dq5x.py', '--mesence', mesence]
subprocess.run(child)
subprocess.run(['krpatch', 'sfc', 'lua'])
env = dict(os.environ, MESENCE=mesence)
subprocess.run([sys.executable, 'x.py'], env=env)
'''
        self.assertEqual(problems(src), [])

    def test_shell(self):
        text = '''#!/bin/sh
# MESENCE=… "$MESENCE" --testrunner 는 주석
: "${MESENCE:?MESENCE 에 실행 파일}"
SHOT_DIR=$out "$MESENCE" --testrunner "$rom" x.lua
$MESENCE "$rom"
${MESENCE} "$rom"
exec "$mesence" --testrunner "$rom"
uv run --locked python "$root/sfc/dq4/tools/dq4mesen.py" "$rom" x.lua  # MesenCE 는 $MESENCE
'''
        self.assertEqual(_lines(shell_problems(text)), [4, 5, 6, 7])


def _tracked(*patterns):
    return subprocess.run(['git', 'ls-files', *patterns], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.split()


def _is_shell(path):
    if path.suffix in ('.sh', '.bash', '.zsh'):
        return True
    if path.suffix:
        return False
    try:
        with path.open('rb') as f:
            first = f.readline()
    except OSError:
        return False
    return first.startswith(b'#!') and b'sh' in first


class RepoTests(unittest.TestCase):
    def test_only_runner_files_launch_mesence(self):
        files = _tracked('*.py')
        self.assertGreater(len(files), 100)
        found = []
        for rel in files:
            path = ROOT / rel
            if rel not in RUNNERS and path.exists():
                found += problems(path.read_bytes(), rel)
        self.assertEqual(found, [], 'MesenCE 는 sfc/dq4/tools/dq4mesen.py 나 sfc/dq5/tools/dq5mesen.py 로 띄운다')

    def test_shell_scripts_use_runner(self):
        found = []
        for rel in _tracked():
            path = ROOT / rel
            if path.is_file() and not path.is_symlink() and _is_shell(path):
                found += shell_problems(path.read_text(encoding='utf-8', errors='replace'), rel)
        self.assertEqual(found, [], '셸 스크립트는 uv run --locked python sfc/dq4/tools/dq4mesen.py 인자… 로 띄운다')

    def test_runner_files_exist(self):
        for rel in RUNNERS:
            self.assertTrue((ROOT / rel).is_file(), rel)


if __name__ == '__main__':
    unittest.main()
