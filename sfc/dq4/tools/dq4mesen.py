"""MesenCE --testrunner 를 배터리 기록(.srm) 없이 띄운다.

MesenCE 는 배터리 기록을 세이브 폴더에 「롬 파일 이름.srm」 으로 두고, 같은 이름의 롬을 띄우면 그것을 읽는다.
검사마다 롬을 c.sfc 같은 같은 이름으로 띄우면 한 검사가 교회에서 남긴 기록이 다른 검사의 새 게임 입력을
이어 하기로 바꾼다. 그래서 실행마다 롬을 유일한 이름으로 복사하고, 그 이름의 기록을 앞뒤로 지운다.

띄우기 전에 tools/headless_slots.py 의 자리를 하나 잡고, MesenCE 가 끝나면 놓는다(HEADLESS_SLOTS).

MesenCE --testrunner 는 --timeout=초 를 주지 않으면 벽시계로 약 100초 뒤 아무 기록 없이 종료 코드 255 로 스스로
끝난다. 부하가 높으면 평소 100초 안에 끝나는 장면도 이를 넘겨 운으로 실패하므로, 세 길 모두 MesenCE 에
--timeout 을 붙여 끝을 Python 쪽 timeout(없으면 RUNNER_TIMEOUT)에 맡긴다(timeout_args). 인자에 --timeout= 이
이미 있으면 그것을 따른다.

리눅스는 환경 변수 한 줄을 128KiB 까지만 넘긴다(넘으면 띄우기부터 E2BIG). run·Runner 는 그보다 긴 값을 임시 파일로
옮기고 lua/dq4bigenv.lua 를 앞에 붙여 스크립트의 os.getenv 가 그 내용을 그대로 받게 한다(with_bigenv). 인자를 그대로
넘기는 testrunner 는 하지 않는다.

run 은 스크립트 앞에 심장 박동 Lua(with_heartbeat)를 붙인다. 시작할 때와 HEARTBEAT_FRAMES 프레임마다 프레임 수·PC·맵
($BC/$BD)·$BE·세계($1949)·메시지 스트림($F0~$F2)을 임시 파일에 덮어 쓴다. 시간 초과면 TimeoutExpired 의 heartbeat 에
마지막 박동을 달아 올린다(timeout_detail). 박동이 없으면 MesenCE 가 Lua 를 부르기 전에 멈췄고, 프레임이 적으면 에뮬레이션이
멈췄고, 프레임이 장면의 MAXF 를 넘었으면 Lua 가 끝내지 못한 것이다. 박동은 WRAM·CPU 상태를 읽기만 하고 출력 폴더 밖에
쓰므로 장면 출력·읽은 롬 바이트에 닿지 않는다.

  run(mesence, rom, script, cwd=dest, env=env, stdout=log, timeout=600)

롬을 복사하지 않고 받은 인자 그대로 띄우려면 testrunner 를 쓴다. 셸 스크립트는
`uv run --locked python sfc/dq4/tools/dq4mesen.py 인자…` 로 부른다(MESENCE 환경 변수의 실행 파일에 --testrunner 와 인자를
붙여 띄우고, 그 종료 코드로 끝난다). MesenCE --testrunner 를 subprocess 로
부르는 코드는 이 파일과 sfc/dq5/tools/dq5mesen.py 에만 둔다(tools/tests/test_testrunner_callers.py 가 본다).
"""
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid

sys.path.append(str(Path(__file__).resolve().parents[3] / 'tools'))
import headless_slots  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4winwatch as winwatch  # noqa: E402

ARGS = ('--Snes.DisableFrameSkipping=true',)
# Runner 의 기본 시간 상한(초). timeout 없이 부른 run·testrunner 에서는 MesenCE 의 --timeout 이 된다
RUNNER_TIMEOUT = 900
# Python 쪽 timeout 이 먼저 끊어(Runner.timed_out·TimeoutExpired) 시간 초과로 알리게, MesenCE 의 제한은 이만큼 뒤에 둔다
TIMEOUT_MARGIN = 60
# DQ4_OPENBUS_LOG 가 있으면 띄우는 스크립트마다 lua/dq4openbus.lua 를 앞에 붙여 열린 버스·롬 거울 접근을 그 파일에 적는다
# (dq4compatcheck.py scenes). 범위는 DQ4_OPENBUS_RANGES(dq4openbus.lua 의 OPENBUS_RANGES)
OPENBUS = Path(__file__).resolve().parent / 'lua' / 'dq4openbus.lua'
BIGENV = Path(__file__).resolve().parent / 'lua' / 'dq4bigenv.lua'
# 모든 실행 앞에 붙여 BG3 창 모습을 적는다(dq4winwatch.py 가 판정)
WINWATCH = Path(__file__).resolve().parent / 'lua' / 'dq4winwatch.lua'
# 심장 박동 사이 프레임 수(60fps 로 10초)
HEARTBEAT_FRAMES = 600
# 리눅스 MAX_ARG_STRLEN(131072, 「이름=값」 과 끝 NUL 포함)보다 넉넉히 아래
ENV_LIMIT = 120_000


def with_openbus(script, kwargs):
    """DQ4_OPENBUS_LOG 가 있으면 (dq4openbus.lua, 그 스크립트를 PROBE_TARGET 으로 둔 kwargs), 없으면 그대로."""
    log = os.environ.get('DQ4_OPENBUS_LOG')
    if not log:
        return script, kwargs
    env = dict(kwargs.get('env') or os.environ)
    env.update(PROBE_TARGET=str(script), OPENBUS_LOG=log,
               OPENBUS_RANGES=os.environ.get('DQ4_OPENBUS_RANGES', env.get('OPENBUS_RANGES', '')))
    return OPENBUS, {**kwargs, 'env': env}


def with_winwatch(script, kwargs, folder):
    """(dq4winwatch.lua, 그 스크립트를 WINWATCH_TARGET 으로 둔 kwargs, 기록이 쌓일 폴더). 기록은 장면 출력 폴더(SHOT_DIR,
    없으면 folder)의 winwatch.bin 이라 읽은 바이트 캐시가 장면 출력과 함께 넣고 펼친다."""
    env = dict(kwargs.get('env') or os.environ)
    where = Path(env.get('SHOT_DIR') or folder)
    env.update(WINWATCH_TARGET=str(script), WINWATCH_OUT=str(where / winwatch.DATA))
    return WINWATCH, {**kwargs, 'env': env}, where


def with_bigenv(script, kwargs):
    """(스크립트, kwargs, 지울 임시 파일). env 에 ENV_LIMIT 보다 긴 값이 있으면 그 값을 임시 파일로 옮기고
    dq4bigenv.lua 가 원래 스크립트를 이어 돌게 한다. 없으면 그대로."""
    env = kwargs.get('env')
    big = [k for k, v in (env or {}).items() if len(k) + len(str(v)) + 2 > ENV_LIMIT]
    if not big:
        return script, kwargs, []
    env, files = dict(env), []
    for name in big:
        fd, path = tempfile.mkstemp(prefix=f'dq4bigenv-{name}-', suffix='.txt')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(str(env.pop(name)))
        env[f'{name}__FILE'] = path
        files.append(Path(path))
    env.update(BIGENV=','.join(big), BIGENV_TARGET=str(script))
    return BIGENV, {**kwargs, 'env': env}, files


def with_heartbeat(script):
    """(박동 Lua, 지울 임시 파일, 박동 파일). 박동 Lua 는 박동을 걸고 script 를 이어 돈다."""
    fd, beat = tempfile.mkstemp(prefix='dq4beat-', suffix='.txt')
    os.close(fd)
    Path(beat).unlink()
    fd, lua = tempfile.mkstemp(prefix='dq4beat-', suffix='.lua')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(HEARTBEAT_LUA.replace('@BEAT@', _lua_string(beat)).replace('@TARGET@', _lua_string(script))
                .replace('@EVERY@', str(HEARTBEAT_FRAMES)))
    return Path(lua), [Path(lua), Path(beat)], Path(beat)


def _lua_string(path):
    return '"' + str(path).replace('\\', '\\\\').replace('"', '\\"') + '"'


HEARTBEAT_LUA = """local path, n, m = @BEAT@, 0, emu.memType.snesMemory
local function beat()
  local s = emu.getState()
  local f = io.open(path, "w")
  if not f then return end
  f:write(string.format("frame=%d pc=%02X:%04X map=%02X/%02X BE=%02X 1949=%02X F0=%02X%02X%02X",
    n, s["cpu.k"] or 0, s["cpu.pc"] or 0, emu.read(0x7E00BC, m), emu.read(0x7E00BD, m), emu.read(0x7E00BE, m),
    emu.read(0x7E1949, m), emu.read(0x7E00F2, m), emu.read(0x7E00F1, m), emu.read(0x7E00F0, m)))
  f:close()
end
beat()
emu.addEventCallback(function()
  n = n + 1
  if n % @EVERY@ == 0 then beat() end
end, emu.eventType.endFrame)
dofile(@TARGET@)
"""


def last_beat(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace').strip() or None
    except OSError:
        return None


def timeout_detail(error, log=None):
    """시간 초과 TimeoutExpired 와 MesenCE 출력 파일에서 까닭을 가를 글: 마지막 박동과 출력 끝 줄."""
    beat = getattr(error, 'heartbeat', None)
    parts = [f'마지막 박동 {beat}' if beat else '박동 없음(Lua 를 부르기 전에 멈춤)']
    tail = ''
    if log is not None:
        try:
            lines = [ln for ln in Path(log).read_text(encoding='utf-8', errors='replace').splitlines() if ln.strip()]
            tail = ' / '.join(lines[-3:])[-300:]
        except OSError:
            pass
    parts.append(f'MesenCE 출력 끝: {tail}' if tail else 'MesenCE 출력 없음')
    return '; '.join(parts)


def _unlink(files):
    for f in files:
        f.unlink(missing_ok=True)


def timeout_args(args, timeout):
    """MesenCE 에 덧붙일 --timeout 인자. args 에 이미 있으면 없음."""
    if any(str(a).startswith('--timeout=') for a in args):
        return []
    return [f'--timeout={math.ceil(RUNNER_TIMEOUT if timeout is None else timeout) + TIMEOUT_MARGIN}']


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
    """rom 이름으로 남은 배터리 기록과 코드·데이터 기록(Debugger/<이름>.cdl)을 지우고, 지운 경로를 돌려준다.

    MesenCE 는 롬을 내릴 때 Debugger 폴더에 롬 크기만 한 .cdl 을 남긴다. 실행마다 이름이 다른 복사본은 그 파일이
    다시 쓰이지 않고 쌓이기만 하므로 기록과 함께 지운다."""
    gone = []
    for folder in save_dirs(mesence):
        for path in (folder / (Path(rom).stem + '.srm'), folder.parent / 'Debugger' / (Path(rom).stem + '.cdl')):
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
        self.source = rom
        script, kwargs, self.watch = with_winwatch(script, kwargs, folder)
        script, kwargs = with_openbus(script, kwargs)
        script, kwargs, self.bigenv = with_bigenv(script, kwargs)
        try:
            self.proc = subprocess.Popen([str(mesence), '--testrunner', str(self.rom), str(script), *extra,
                                          *timeout_args(extra, timeout)], **kwargs)
        except BaseException:
            self.slot.release()
            _unlink(self.bigenv)
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
            rc = self.proc.wait()
        finally:
            self.close()
        winwatch.verdict(self.watch, self.source)
        return rc

    def close(self):
        # KeyboardInterrupt 등으로 MesenCE 가 살아 있을 때 불려도, 끄기 전에는 자리와 롬 복사본을 놓지 않는다
        self._kill()
        self.slot.release()
        clear_saves(self.rom, self.mesence)
        self.rom.unlink(missing_ok=True)
        _unlink(self.bigenv)


def run(mesence, rom, script, folder=None, tag='probe', extra=ARGS, **kwargs):
    """subprocess.run 과 같이 띄운다. TimeoutExpired 는 그대로 올린다."""
    folder = Path(folder or kwargs.get('cwd') or Path(rom).parent)
    script, kwargs, watch = with_winwatch(script, kwargs, folder)
    script, kwargs = with_openbus(script, kwargs)
    script, kwargs, bigenv = with_bigenv(script, kwargs)
    script, temps, beat = with_heartbeat(script)
    copy = unique_copy(rom, folder, tag)
    clear_saves(copy, mesence)
    try:
        with headless_slots.slot(f'MesenCE {tag}'):
            done = subprocess.run([str(mesence), '--testrunner', str(copy), str(script), *extra,
                                   *timeout_args(extra, kwargs.get('timeout'))], **kwargs)
        winwatch.verdict(watch, copy)
        return done
    except subprocess.TimeoutExpired as e:
        e.heartbeat = last_beat(beat)
        raise
    finally:
        clear_saves(copy, mesence)
        copy.unlink(missing_ok=True)
        _unlink(bigenv + temps)


def testrunner(mesence, *args, tag=None, **kwargs):
    """[mesence, '--testrunner', *args] 를 자리를 쥔 채 subprocess.run 으로 띄운다. 롬은 복사하지 않는다."""
    name = f'MesenCE {tag or Path(sys.argv[0]).stem}'
    return headless_slots.run([mesence, '--testrunner', *args, *timeout_args(args, kwargs.get('timeout'))], name,
                              **kwargs)


if __name__ == '__main__':
    if not os.environ.get('MESENCE'):
        sys.exit('MESENCE 에 MesenCE 실행 파일을 주세요')
    sys.exit(testrunner(os.environ['MESENCE'], *sys.argv[1:]).returncode)
