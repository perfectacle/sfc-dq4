"""MesenCE --testrunner 를 배터리 기록(.srm) 없이 띄운다.

MesenCE 는 배터리 기록을 세이브 폴더에 「롬 파일 이름.srm」 으로 두고, 같은 이름의 롬을 띄우면 그것을 읽는다.
검사마다 롬을 c.sfc 같은 같은 이름으로 띄우면 한 검사가 교회에서 남긴 기록이 다른 검사의 새 게임 입력을
이어 하기로 바꾼다. 그래서 실행마다 롬을 유일한 이름으로 복사하고, 그 이름의 기록을 앞뒤로 지운다.

띄우기 전에 tools/headless_slots.py 의 자리를 하나 잡고, MesenCE 가 끝나면 놓는다(HEADLESS_SLOTS).

  run(mesence, rom, script, cwd=dest, env=env, stdout=log, timeout=600)
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import uuid

sys.path.append(str(Path(__file__).resolve().parents[3] / 'tools'))
import headless_slots  # noqa: E402

ARGS = ('--Snes.DisableFrameSkipping=true',)
# Runner 의 기본 시간 상한(초)
RUNNER_TIMEOUT = 900


def save_dirs(mesence=None):
    """MesenCE 가 배터리 기록을 둘 수 있는 폴더. MESENCE_SAVES 가 있으면 그것만."""
    if os.environ.get('MESENCE_SAVES'):
        return [Path(os.environ['MESENCE_SAVES'])]
    home = Path.home()
    if sys.platform == 'darwin':
        dirs = [home / 'Library/Application Support/MesenCE/Saves']
    elif sys.platform == 'win32':
        dirs = [Path(os.environ.get('APPDATA', home)) / 'MesenCE/Saves']
    else:
        dirs = [Path(os.environ.get('XDG_CONFIG_HOME', home / '.config')) / 'MesenCE/Saves']
    if mesence:
        # 포터블 모드(실행 파일 옆에 settings.json)면 Saves 도 실행 파일 옆이다.
        dirs.append(Path(mesence).resolve().parent / 'Saves')
    return dirs


def clear_saves(rom, mesence=None):
    """rom 이름으로 남은 배터리 기록을 지우고, 지운 경로를 돌려준다."""
    gone = []
    for folder in save_dirs(mesence):
        path = folder / (Path(rom).stem + '.srm')
        if path.exists():
            path.unlink()
            gone.append(path)
    return gone


def unique_copy(rom, folder, tag='probe'):
    """rom 을 folder 안에 실행마다 다른 이름으로 복사한다."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / f'{tag}-{uuid.uuid4().hex[:12]}.sfc'
    shutil.copyfile(rom, copy)
    return copy


class Runner:
    """Popen 으로 띄운다. wait() 가 끝나기를 기다리고 복사본과 기록을 치운다.

    timeout 초(자리를 잡은 뒤부터)를 넘기면 MesenCE 를 끈다. 멈춘 MesenCE 가 자리를 계속 쥐지 않게 한다.
    """

    def __init__(self, mesence, rom, script, folder, tag='probe', extra=ARGS, timeout=RUNNER_TIMEOUT, **kwargs):
        self.mesence = mesence
        self.timeout = timeout
        self.timed_out = False
        self.rom = unique_copy(rom, folder, tag)
        clear_saves(self.rom, mesence)
        self.slot = headless_slots.acquire(f'MesenCE {tag}')
        try:
            self.proc = subprocess.Popen([str(mesence), '--testrunner', str(self.rom), str(script), *extra], **kwargs)
        except BaseException:
            self.slot.release()
            raise
        # 호출하는 쪽이 여러 Runner 를 띄운 뒤 앞엣것부터 wait() 하므로, wait() 까지 자리를 쥐고 있으면
        # 자리보다 많이 띄울 때 서로 막힌다. 프로세스가 끝나는 즉시 놓는다.
        threading.Thread(target=self._release_on_exit, daemon=True).start()

    def _release_on_exit(self):
        try:
            self.proc.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            self.timed_out = True
            self._kill()
        self.slot.release()

    def _kill(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()

    def wait(self):
        try:
            return self.proc.wait()
        finally:
            self.close()

    def close(self):
        # KeyboardInterrupt 등으로 MesenCE 가 살아 있을 때 불려도, 끄기 전에는 자리와 롬 복사본을 놓지 않는다
        self._kill()
        self.slot.release()
        clear_saves(self.rom, self.mesence)
        self.rom.unlink(missing_ok=True)


def run(mesence, rom, script, folder=None, tag='probe', extra=ARGS, **kwargs):
    """subprocess.run 과 같이 띄운다. TimeoutExpired 는 그대로 올린다."""
    folder = Path(folder or kwargs.get('cwd') or Path(rom).parent)
    copy = unique_copy(rom, folder, tag)
    clear_saves(copy, mesence)
    try:
        with headless_slots.slot(f'MesenCE {tag}'):
            return subprocess.run([str(mesence), '--testrunner', str(copy), str(script), *extra], **kwargs)
    finally:
        clear_saves(copy, mesence)
        copy.unlink(missing_ok=True)
