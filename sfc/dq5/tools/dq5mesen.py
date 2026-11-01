"""MesenCE --testrunner 를 머신 전체의 헤드리스 에뮬레이터 자리(tools/headless_slots.py, HEADLESS_SLOTS)를 쥔 채 띄운다.

dq5 도구가 MesenCE 를 subprocess 로 직접 부르지 않고 이것을 부른다(tools/tests/test_testrunner_callers.py 가 본다).
인자는 '--testrunner' 뒤에 받은 그대로 붙인다. timeout 은 자리를 잡은 뒤부터 잰다.

  testrunner(mesence, rom, lua, '--Snes.DisableFrameSkipping=true', env=env, stdout=log, timeout=90)
  p = testrunner_popen(mesence, rom, lua, env=env)   # 끝나면 자리를 놓는다. p.wait() 는 그대로
"""
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[3] / 'tools'))
import headless_slots  # noqa: E402


def _name(tag):
    return f'MesenCE {tag or Path(sys.argv[0]).stem}'


def testrunner(mesence, *args, tag=None, **kwargs):
    """subprocess.run 과 같다. TimeoutExpired 는 그대로 올린다(MesenCE 는 꺼진 뒤다)."""
    return headless_slots.run([mesence, '--testrunner', *args], _name(tag), **kwargs)


def testrunner_popen(mesence, *args, tag=None, timeout=None, **kwargs):
    """subprocess.Popen 과 같다. timeout 초를 넘기면 끈다."""
    return headless_slots.popen([mesence, '--testrunner', *args], _name(tag), timeout=timeout, **kwargs)
