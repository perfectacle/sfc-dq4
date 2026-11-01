"""머신 전체에서 함께 도는 헤드리스 에뮬레이터 프로세스 수를 제한하는 자리(slot).

여러 세션이 한 머신에서 각자 검사를 병렬로 돌리면 에뮬레이터 프로세스가 코어 수보다 훨씬 많아져 모두 느려진다.
원래 체크아웃(워크트리가 공유하는 .git 의 부모)의 work/cache/slots/ 에 잠금 파일 N 개를 두고, 에뮬레이터
프로세스 하나가 그중 하나를 flock 으로 쥔 동안만 돈다. 쥔 프로세스가 죽으면 커널이 잠금을 풀어 주므로
파일은 지우지 않는다.

  HEADLESS_SLOTS   자리 수. 기본 max(1, CPU 수 // 2). 0 이나 off 면 제한하지 않는다.

  with headless_slots.slot('dq4ch1walkcheck') as s:
      subprocess.run([...])
  s.waited  # 자리를 기다린 초
"""
import contextlib
import functools
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

try:
    import fcntl
except ImportError:  # Windows: flock 이 없으므로 제한하지 않는다
    fcntl = None

ENV = 'HEADLESS_SLOTS'
POLL = 0.2


def limit(value=None):
    """자리 수. 0 이면 제한 없음."""
    if fcntl is None:
        return 0
    value = os.environ.get(ENV, '') if value is None else value
    value = value.strip().lower()
    if not value:
        return max(1, (os.cpu_count() or 2) // 2)
    if value in ('0', 'off'):
        return 0
    n = int(value)
    if n < 0:
        raise ValueError(f'{ENV}={value}: 0 이상이어야 함')
    return n


@functools.lru_cache(maxsize=None)
def slots_dir():
    """워크트리마다 따로 두면 머신 전체를 묶지 못하므로 원래 체크아웃 한 곳에 둔다."""
    here = Path(__file__).resolve().parent
    try:
        common = subprocess.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'], cwd=here,
                                capture_output=True, text=True, check=True).stdout.strip()
        root = Path(common).parent
    except (OSError, subprocess.CalledProcessError):
        root = here.parent
    return root / 'work' / 'cache' / 'slots'


class Slot:
    """잡은 자리. release() 하거나 프로세스가 끝나면 풀린다. index 가 None 이면 제한 없이 지나온 것."""

    def __init__(self, fd, index, waited):
        self.fd, self.index, self.waited = fd, index, waited
        self._lock = threading.Lock()

    def release(self):
        # 여러 스레드가 함께 불러도 한 번만 닫는다. 두 번 닫으면 그새 다른 파일이 받은 번호를 닫는다
        with self._lock:
            if self.fd is not None:
                # 잠금은 이 파일 설명자에 붙어 있어 닫으면 풀린다
                os.close(self.fd)
                self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def _try(folder, i, name):
    fd = os.open(folder / f'{i}.lock', os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    # 누가 쥐었는지 사람이 볼 수 있게만 적는다. 잠금 판단에는 쓰지 않는다
    os.ftruncate(fd, 0)
    os.write(fd, f'{os.getpid()} {name}\n'.encode())
    return fd


def acquire(name='', n=None, folder=None, timeout=None, poll=POLL, log=sys.stderr):
    """빈 자리를 잡을 때까지 기다린다. timeout 초를 넘기면 TimeoutError. 기다렸으면 log 에 한 줄씩 남긴다."""
    n = limit() if n is None else n
    if n == 0:
        return Slot(None, None, 0.0)
    folder = Path(folder) if folder else slots_dir()
    folder.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    told = False
    while True:
        for i in range(n):
            fd = _try(folder, i, name)
            if fd is not None:
                waited = time.monotonic() - t0
                if told and log:
                    print(f'[headless_slots] {name}: 자리 {i} 잡음, {waited:.1f}초 기다림', file=log, flush=True)
                return Slot(fd, i, waited)
        if not told and log:
            print(f'[headless_slots] {name}: 자리 {n}개 모두 사용 중, 기다림 ({folder})', file=log, flush=True)
        told = True
        if timeout is not None and time.monotonic() - t0 >= timeout:
            raise TimeoutError(f'{name}: {timeout}초 안에 빈 자리가 나지 않음')
        time.sleep(poll)


@contextlib.contextmanager
def slot(name='', **kwargs):
    s = acquire(name, **kwargs)
    try:
        yield s
    finally:
        s.release()
