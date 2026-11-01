"""MesenCE 를 subprocess 로 직접 띄우는 코드는 공통 러너 파일에만 있어야 한다.

직접 띄우면 머신 전체의 헤드리스 에뮬레이터 자리(tools/headless_slots.py)를 잡지 않아, 여러 세션이 함께 돌 때
에뮬레이터가 HEADLESS_SLOTS 보다 많이 뜬다. 도구는 dq4mesen(run·Runner·testrunner)이나 dq5mesen 을 부른다.
"""
import ast
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
RUNNERS = {'sfc/dq4/tools/dq4mesen.py', 'sfc/dq5/tools/dq5mesen.py'}
LAUNCH = {('subprocess', name) for name in ('run', 'Popen', 'call', 'check_call', 'check_output')} | {
    ('os', name) for name in ('system', 'popen', 'execv', 'execve', 'execvp', 'execvpe', 'spawnv', 'spawnve')}
EMULATOR = {'mesence', 'mesen'}


def _docstrings(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


def _names_emulator(node):
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id.lower() in EMULATOR:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr.lower() in EMULATOR:
            return True
        if isinstance(sub, ast.Constant) and sub.value == 'MESENCE':
            return True
    return False


def problems(source, name='<src>'):
    """'--testrunner' 문자열과, 실행 파일이 mesence·MESENCE 인 subprocess 호출을 찾아 줄마다 알린다."""
    tree = ast.parse(source)
    docs = _docstrings(tree)
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs
                and '--testrunner' in node.value.split()):
            found.append(f'{name}:{node.lineno}: --testrunner')
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and (node.func.value.id, node.func.attr) in LAUNCH):
            continue
        cmd = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == 'args'), None)
        if isinstance(cmd, (ast.List, ast.Tuple)):
            cmd = cmd.elts[0] if cmd.elts else None
        if cmd is not None and _names_emulator(cmd):
            found.append(f'{name}:{node.lineno}: {node.func.value.id}.{node.func.attr} 로 MesenCE')
    return found


class CheckerTests(unittest.TestCase):
    def test_finds_direct_launches(self):
        src = '''
import os, subprocess
subprocess.run([str(mesence), '--testrunner', rom, lua], timeout=9)
cmd = [mesen, "--testrunner", rom]
subprocess.Popen([os.environ['MESENCE'], rom])
subprocess.run(args=[args.mesen, rom])
'''
        self.assertEqual(sorted(int(p.split(':')[1]) for p in problems(src)), [3, 3, 4, 5, 6])

    def test_allows_runners_and_children(self):
        src = '''
"""MesenCE @TR 를 부른다."""
import subprocess, sys
dq5mesen.testrunner(mesence, rom, lua, timeout=9)
subprocess.run([sys.executable, 'dq5x.py', '--mesence', mesence])
subprocess.run(['krpatch', 'sfc', 'lua'])
'''
        # 이 파일도 저장소 검사에 걸리므로 docstring 속 낱말은 띄울 때 만든다
        self.assertEqual(problems(src.replace('@TR', '--' + 'testrunner')), [])


class RepoTests(unittest.TestCase):
    def test_only_runner_files_launch_mesence(self):
        files = subprocess.run(['git', 'ls-files', '*.py'], cwd=ROOT, capture_output=True, text=True,
                               check=True).stdout.split()
        self.assertGreater(len(files), 100)
        found = []
        for rel in files:
            if rel in RUNNERS:
                continue
            path = ROOT / rel
            if path.exists():
                found += problems(path.read_bytes(), rel)
        self.assertEqual(found, [], 'MesenCE 는 sfc/dq4/tools/dq4mesen.py 나 sfc/dq5/tools/dq5mesen.py 로 띄운다')

    def test_runner_files_exist(self):
        for rel in RUNNERS:
            self.assertTrue((ROOT / rel).is_file(), rel)


if __name__ == '__main__':
    unittest.main()
