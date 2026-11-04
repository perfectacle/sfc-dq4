"""MesenCE 장면 실행을 「실제로 읽은 롬 바이트」 단위로 캐시한다. 형식은 sfc/dq4/docs/dq4-readset-format.md.

장면 하나(MesenCE 프로세스 하나)를 돌릴 때 lua/dq4readset.lua 를 앞에 붙여 그 실행이 읽은 롬 파일 오프셋을 적고,
출력 파일과 함께 원래 체크아웃의 work/cache/readset/ 에 둔다. 다음에 같은 장면(같은 코드·에뮬레이터·입력·출발
상태)을 돌릴 때 지금 롬의 그 오프셋 바이트가 적어 둔 것과 같으면 돌리지 않고 출력을 펼친다.

이것이 건전한 까닭: 장면은 결정적이다(난수·시각·입력 고정). 출발 상태와 입력이 같고 기록된 오프셋의 바이트가
모두 같으면, 새 롬에서도 같은 주소를 같은 차례로 읽어 같은 결과를 낸다(처음으로 다른 주소를 읽으려면 그 전에
다른 값을 읽었어야 한다).

  run(mesence, rom, script, dest, env, timeout=...)   돌리거나 캐시에서 펼친다. 결과 dict 의 'cached'

환경 변수
  DQ4_READSET=off          캐시를 읽지 않고 모두 돌린다(쓰기는 함). 배포 관문(guards.py --no-cache)
  DQ4_READSET_VERIFY=0.05  캐시가 맞은 장면 가운데 이 비율을 다시 돌려 출력이 같은지 본다. 다르면 실패
  DQ4_READSET_CACHE=폴더    캐시 뿌리(기본 원래 체크아웃 work/cache/readset)
  DQ4_READSET_MAX_GB=20    이보다 커지면 오래 안 쓴 항목부터 지운다
  DQ4_READSET_STATS=파일    실행마다 한 줄(JSON: 스크립트·출력 폴더·맞았는가·읽은 바이트 수)을 덧붙인다(적중률 재기)
"""
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import random
import re
import struct
import subprocess
import sys
import time
import zlib

try:
    import fcntl
except ImportError:  # Windows: 잠그지 않는다
    fcntl = None

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import dq4mesen as mesen  # noqa: E402
sys.path.insert(0, str(ROOT / 'tools'))
from mesence_settings import settings_digest, settings_path  # noqa: E402

PRELUDE = HERE / 'lua' / 'dq4readset.lua'
# 장면 Lua 가 dofile·require 할 수 있는 곳. 하나라도 바뀌면 모든 장면이 빗나간다
LUA_DIRS = (ROOT / 'tools' / 'lua', HERE / 'lua', HERE.parents[1] / 'dq5' / 'tools' / 'lua')
VERSION = 'readset-1'
ENTRY = '.readset-entry.lua'
OUT = '.readset.txt'
HDMA = OUT + '.hdma'
# 머리말이 장면 Lua 의 오류를 여기 적는다. MesenCE --testrunner 는 콜백 안 오류를 삼키고 0 으로 끝날 수 있다
ERR = OUT + '.err'
# 머리말이 읽은 집합을 이 이름으로 쓴 뒤 OUT 으로 옮긴다. 도중에 끊기면 남는다
OUT_TMP = OUT + '.tmp'
# 키를 만든 롬 바이트 그대로의 사본. 그 사이 롬 파일이 바뀌어도 키와 실제로 돌린 롬이 같다
ROM_COPY = '.readset-rom.sfc'
SKIP = (ENTRY, OUT, HDMA, ERR, OUT_TMP, ROM_COPY)
# 머리말이 읽은 집합 끝줄에 쓰는 표시. 장면 Lua 가 오류를 냈으면 LUAERROR
DONE = 'OK'
# 결과에 닿는 MesenCE 설정을 명령줄로 고정한다. 사용자 settings.json 의 값과 상관없이 같게 돈다
FIXED_ARGS = ('--Snes.RamPowerOnState=AllZeros', '--Snes.EnableRandomPowerOnState=false')
# 롬을 불러올 때 에뮬레이터는 매핑(LoROM·HiROM·Ex·카피어 머리)을 머리 후보의 점수로 고른다. 이 읽기는 접근 카운터에도
# bsnes 비트맵에도 잡히지 않으므로 후보마다 그 바이트를 키에 넣는다(rom_shape). 후보의 시작 자리는 MesenCE
# BaseCartridge::LoadRom 의 목록이고, bsnes heuristics::SuperFamicom 의 네 후보($7FB0·$FFB0·$407FB0·$40FFB0)는 그
# 가운데 카피어 머리 없는 넷이다. 각 후보는 시작 + $7FB0 부터 $50 바이트(머리와 벡터)다
HEADER_BASES = (0, 0x200, 0x8000, 0x8200, 0x400000, 0x400200, 0x408000, 0x408200)
HEADER_AT, HEADER_LEN = 0x7FB0, 0x50
# 머리 안 보수(2)·체크섬(2). 점수는 두 값이 아니라 「합이 $FFFF」·「둘 다 0 아님」 만 보므로 키에는 그 둘만 넣는다.
# 체크섬은 빌드마다 바뀐다
SUM_AT, SUM_LEN = 0x2C, 4
# MesenCE 는 매핑을 고르기 전에 롬 앞 27바이트가 SPC 파일 머리인지 견준다(같으면 SPC 로 불러온다)
SPC_MAGIC = b'SNES-SPC700 Sound File Data'
CHECKSUM = range(0x7FDC, 0x7FE0)
KEEP_ENTRIES = 8
# emu.takeScreenshot 화면은 같은 실행을 되풀이해도 다를 수 있다(메모리·VRAM 덤프는 같은데 화면만 다름). 재검증은 이것을
# 키에 빠진 입력의 증거로 보지 않는다. 그래서 장면 판정이 화면 찍기를 읽지 않는 검사만 이 캐시를 쓴다
SCREENS = ('.png',)
GETENV = re.compile(r'''os\.getenv\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']\s*\)''')
# 출발 상태 머리의 롬 파일 이름(dq4mesen.unique_copy 가 실행마다 다르게 짓는다) 앞의 길이 칸
_NAME = re.compile(rb'([\x01-\xff])\x00\x00\x00([ -~]{1,255}?\.(?:sfc|smc))', re.S)


# ---------------------------------------------------------------- 순수 함수(단위 테스트)

def parse_ranges(text):
    """「시작 길이」(16진) 줄 → [(시작, 길이)] 정렬·합침."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2:
            out.append((int(parts[0], 16), int(parts[1], 16)))
    return merge(out)


def merge(ranges):
    out = []
    for s, n in sorted(r for r in ranges if r[1] > 0):
        if out and s <= out[-1][0] + out[-1][1]:
            ps, pn = out[-1]
            out[-1] = (ps, max(pn, s + n - ps))
        else:
            out.append((s, n))
    return out


def pack(ranges):
    return base64.b64encode(zlib.compress(b''.join(struct.pack('<II', s, n) for s, n in ranges), 9)).decode()


def unpack(text):
    raw = zlib.decompress(base64.b64decode(text))
    return [struct.unpack_from('<II', raw, i) for i in range(0, len(raw), 8)]


def digest(rom, ranges):
    """읽은 구간의 지금 롬 바이트 해시. 롬 밖으로 나가는 구간은 없는 바이트로 표시한다(롬이 줄었으면 빗나감)."""
    h = hashlib.sha256()
    for s, n in ranges:
        chunk = rom[s:s + n]
        h.update(struct.pack('<II', s, n))
        h.update(chunk)
        if len(chunk) != n:
            h.update(b'\xff-short')
    return h.hexdigest()


def _candidates(rom):
    """롬에 걸치는 머리 후보마다 (머리 시작, 끝, 리셋 벡터가 가리키는 첫 명령 자리 또는 None)."""
    out = []
    for base in HEADER_BASES:
        start = base + HEADER_AT
        if start >= len(rom):
            continue
        end = min(start + HEADER_LEN, len(rom))
        op = None
        if end - start == HEADER_LEN:
            reset = rom[start + 0x4C] | rom[start + 0x4D] << 8
            # 리셋 벡터가 $8000 아래면 MesenCE 는 그 후보를 버리고 bsnes 는 0점을 준다. 둘 다 첫 명령은 읽지 않는다.
            # 아니면 base + (벡터 & $7FFF) 를 읽는다
            if reset >= 0x8000 and base + (reset & 0x7FFF) < len(rom):
                op = base + (reset & 0x7FFF)
        out.append((start, end, op))
    return out


def loader_ranges(rom):
    """에뮬레이터가 매핑을 고를 때 읽는 롬 구간 (시작, 길이). 보수·체크섬 칸은 빼고, 첫 명령 바이트는 넣는다."""
    ranges = [(0, min(len(SPC_MAGIC), len(rom)))]
    for start, end, op in _candidates(rom):
        ranges += [(i, 1) for i in range(start, end) if not 0 <= i - start - SUM_AT < SUM_LEN]
        if op is not None:
            ranges.append((op, 1))
    return merge(ranges)


def rom_shape(rom):
    """롬 크기, 롬 앞이 SPC 파일 머리인지, 머리 후보마다 보수·체크섬을 뺀 머리, 보수·체크섬의 두 조건, 첫 명령 바이트."""
    parts = [str(len(rom)), f'spc{int(bytes(rom[:len(SPC_MAGIC)]) == SPC_MAGIC)}']
    for start, end, op in _candidates(rom):
        head = bytearray(rom[start:end])
        cond = ''
        if end - start == HEADER_LEN:
            comp = head[SUM_AT] | head[SUM_AT + 1] << 8
            csum = head[SUM_AT + 2] | head[SUM_AT + 3] << 8
            cond = f'{int(comp + csum == 0xFFFF)}{int(comp != 0 and csum != 0)}'
            head[SUM_AT:SUM_AT + SUM_LEN] = bytes(SUM_LEN)
        parts.append(f'{start:x}={head.hex()}/{cond}/{"" if op is None else f"{rom[op]:02x}"}')
    return ':'.join(parts)


def state_hash(data):
    """세이브스테이트 해시. 머리에 든 롬 파일 이름(실행마다 다름)은 지우고 본다. 이름은 압축한 화면 그림 뒤에 오므로
    그림 크기에 따라 자리가 달라진다. 그래서 파일 앞 일부가 아니라 전체에서 찾는다."""
    data = bytes(data)
    # 길이 칸이 이름 길이와 맞지 않는 매치(압축 본문에 우연히 든 꼴)는 건너뛰고 한 바이트 뒤부터 다시 찾는다
    m = _NAME.search(data)
    while m and m.group(1)[0] != len(m.group(2)):
        m = _NAME.search(data, m.start() + 1)
    if m:
        data = data[:m.start()] + b'<rom>' + data[m.end():]
    return hashlib.sha256(data).hexdigest()


# dq4mesen.unique_copy 가 실행마다 짓는 롬 복사본 이름. 기록 글에 찍히면 같은 실행이라도 달라 보인다
_COPY = re.compile(rb'[A-Za-z0-9_.-]+-[0-9a-f]{12}\.sfc')


def content_hash(data, name):
    """출력·입력 파일의 해시. 세이브스테이트는 머리의 롬 이름을, 글 기록은 복사본 이름을 지우고 본다."""
    if str(name).endswith('.mss'):
        return state_hash(data)
    if str(name).endswith(('.log', '.txt')):
        data = _COPY.sub(b'<rom>', bytes(data))
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    path = Path(path)
    return content_hash(path.read_bytes(), path.name)


def tree_hash(folder, skip=()):
    """폴더 안 파일들의 (상대 경로, 해시)."""
    folder = Path(folder)
    out = {}
    for f in sorted(folder.rglob('*')):
        rel = f.relative_to(folder).as_posix()
        if f.is_file() and rel not in skip:
            out[rel] = file_hash(f)
    return out


def lua_files(libdir=None):
    dirs = list(LUA_DIRS) + ([Path(libdir)] if libdir else [])
    return sorted({f.resolve() for d in dirs if Path(d).is_dir() for f in Path(d).rglob('*.lua')})


def lua_env_names(files):
    """Lua 가 os.getenv 로 읽는 이름. 이 이름들의 값만 키에 넣는다(셸에 남은 다른 변수는 결과와 무관)."""
    names = set()
    for f in files:
        names |= set(GETENV.findall(Path(f).read_text(encoding='utf-8', errors='replace')))
    return sorted(names)


def canon_env(env, names, dest, code_dirs=(), cwd=None):
    """키에 넣을 환경 변수 값. 경로는 내용으로 바꾼다: dest 안이면 상대 경로(아직 없는 출력 경로도), 파일이면 해시
    (.mss 는 이름 지운 해시), Lua 폴더(LIBDIR 등)면 'code'(Lua 는 따로 해시), 폴더면 안 파일들의 해시.
    상대 경로는 Lua 가 도는 작업 폴더(cwd) 기준으로 본다. dest 밖의 없는 절대 경로는 'absent:' 를 붙여, 같은 경로에
    나중에 파일이 생기면 빗나가게 한다(키가 원 문자열과 같으면 내용 없이 맞을 수 있다)."""
    dest = Path(dest).resolve()
    base = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()
    code = {Path(d).resolve() for d in code_dirs}
    out = {}
    for n in names:
        if n in ('SHOT_DIR', 'READSET_OUT', 'READSET_HDMA'):
            continue
        v = env.get(n)
        if v is None:
            continue
        out[n] = _canon_value(v, dest, base, code)
    return out


def _canon_value(v, dest, base, code):
    if not v:
        return v
    p = Path(v)
    r = (p if p.is_absolute() else base / p).resolve()
    if r == dest or dest in r.parents:
        return 'dest:' + r.relative_to(dest).as_posix()
    if r.is_file():
        return 'file:' + file_hash(r)
    if r in code:
        return 'code'
    if r.is_dir():
        return 'dir:' + json.dumps(tree_hash(r), sort_keys=True)
    return 'absent:' + v if p.is_absolute() else v


def index_key(parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def matches(entries, rom):
    """entries 가운데 지금 롬과 읽은 바이트가 같은 것들(최근 것부터)."""
    for e in entries:
        if digest(rom, unpack(e['ranges'])) == e['digest']:
            yield e


def find(entries, rom):
    """entries 가운데 지금 롬과 읽은 바이트가 같은 첫 것."""
    return next(matches(entries, rom), None)


# ---------------------------------------------------------------- 저장소

def main_checkout():
    try:
        common = subprocess.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.strip()
        return Path(common).parent
    except (OSError, subprocess.CalledProcessError):
        return ROOT


def cache_root():
    return Path(os.environ.get('DQ4_READSET_CACHE') or main_checkout() / 'work' / 'cache' / 'readset')


def enabled():
    return os.environ.get('DQ4_READSET', '').strip().lower() not in ('off', '0', 'no')


def verify_rate():
    try:
        return float(os.environ.get('DQ4_READSET_VERIFY', '0.05'))
    except ValueError:
        return 0.05


@contextlib.contextmanager
def locked(root):
    root.mkdir(parents=True, exist_ok=True)
    with open(root / '.lock', 'a') as f:
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_UN)


def _replace(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.{random.getrandbits(32):08x}')
    tmp.write_bytes(data)
    os.replace(tmp, path)


class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root else cache_root()

    def index_path(self, key):
        return self.root / 'index' / key[:2] / f'{key}.json'

    def blob_path(self, sha):
        return self.root / 'blob' / sha[:2] / sha

    def entries(self, key):
        p = self.index_path(key)
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return []

    def get_blob(self, sha):
        """없거나, 풀리지 않거나, 푼 내용의 SHA-256 이 이름과 다르면 FileNotFoundError(prune 이 지운 뒤 읽은 항목, 깨진
        파일). 부르는 쪽은 빗나감으로 친다."""
        try:
            data = zlib.decompress(self.blob_path(sha).read_bytes())
        except zlib.error as e:
            raise FileNotFoundError(f'blob {sha} 깨짐: {e}') from e
        if hashlib.sha256(data).hexdigest() != sha:
            raise FileNotFoundError(f'blob {sha} 내용이 이름과 다름')
        return data

    def add(self, key, entry, blobs):
        """blobs(상대 경로 → 바이트)를 넣고 entry['files'] 를 채워 index 맨 앞에 둔다. blob 과 index 를 한 잠금 안에서
        써서, prune 이 index 에 들어가기 전의 blob 이나 index 가 가리키는 blob 을 지우지 못하게 한다."""
        packed = {rel: (hashlib.sha256(data).hexdigest(), zlib.compress(data, 1)) for rel, data in blobs.items()}
        with locked(self.root):
            for sha, z in packed.values():
                if not self._blob_ok(sha):
                    _replace(self.blob_path(sha), z)
            entry = {**entry, 'files': {rel: sha for rel, (sha, _) in packed.items()}}
            old = [e for e in self.entries(key) if e['digest'] != entry['digest']]
            _replace(self.index_path(key), json.dumps([entry] + old[:KEEP_ENTRIES - 1]).encode())
        return entry

    def _blob_ok(self, sha):
        """있고 풀리며 내용 해시가 이름과 같은가. 깨진 blob 을 그대로 두면 그 내용의 항목이 늘 빗나간다."""
        try:
            return hashlib.sha256(zlib.decompress(self.blob_path(sha).read_bytes())).hexdigest() == sha
        except (OSError, zlib.error):
            return False

    def touch(self, key, entry):
        """맞은 항목을 맨 앞으로(오래 안 쓴 것부터 지우게). 그 사이 prune·drop 이 지웠으면 되살리지 않는다."""
        with locked(self.root):
            es = self.entries(key)
            now = [e for e in es if e['digest'] == entry['digest']]
            if not now:
                return
            _replace(self.index_path(key), json.dumps(now[:1] + [e for e in es if e['digest'] != entry['digest']]).encode())

    def drop(self, key, entry):
        with locked(self.root):
            es = [e for e in self.entries(key) if e['digest'] != entry['digest']]
            _replace(self.index_path(key), json.dumps(es).encode())

    def size(self):
        return sum(f.stat().st_size for f in (self.root / 'blob').rglob('*') if f.is_file())

    def prune(self, limit):
        """limit 바이트를 넘으면 오래 안 쓴 index 부터 지우고, 어느 index 도 가리키지 않는 blob 을 지운다."""
        with locked(self.root):
            # _replace 가 쓰다 끊긴 임시 파일(.이름.pid.난수). 잠금 안이라 지금 쓰는 것은 없다
            for f in self.root.rglob('.*.*'):
                if f.is_file() and f.name != '.lock':
                    f.unlink(missing_ok=True)
            if self.size() <= limit:
                return
            idx = sorted((self.root / 'index').rglob('*.json'), key=lambda p: p.stat().st_mtime)
            for p in idx[:max(1, len(idx) // 4)]:
                p.unlink(missing_ok=True)
            live = set()
            for p in (self.root / 'index').rglob('*.json'):
                try:
                    for e in json.loads(p.read_text(encoding='utf-8')):
                        live |= set(e['files'].values())
                except (OSError, ValueError):
                    pass
            for f in (self.root / 'blob').rglob('*'):
                if f.is_file() and f.name not in live and not f.name.startswith('.'):
                    f.unlink(missing_ok=True)


# ---------------------------------------------------------------- 실행

def mesence_settings(mesence):
    """MesenCE 설정 파일 원 바이트의 해시(tools/mesence_settings.py). 명령줄로 고정하지 않은 설정도 결과에 닿을 수 있다.
    못 찾으면 멈춘다."""
    digest = settings_digest(mesence)
    if digest is None:
        raise SystemExit(f'MesenCE 설정 파일을 찾지 못함: {settings_path(mesence)}. 읽은 바이트 캐시 키에 넣어야 한다'
                         '(한 번 띄우면 생긴다)')
    return digest


def mesence_stamp(mesence):
    st = Path(mesence).stat()
    return f'{st.st_size}:{st.st_mtime_ns}'


def key_parts(mesence, rom, script, dest, env, extra, cwd=None):
    libdir = env.get('LIBDIR')
    files = lua_files(libdir) + [Path(script).resolve(), PRELUDE.resolve()]
    files = sorted(set(files))
    code = hashlib.sha256()
    for f in files:
        code.update(str(f.name).encode() + b'\0' + hashlib.sha256(f.read_bytes()).digest())
    names = lua_env_names(files)
    return {
        'version': VERSION,
        'script': Path(script).name,
        'code': code.hexdigest(),
        'emulator': [mesence_stamp(mesence), list(extra), list(FIXED_ARGS), mesence_settings(mesence)],
        'env': canon_env(env, names, dest, [d for d in LUA_DIRS] + ([libdir] if libdir else []),
                         cwd=cwd),
        'inputs': tree_hash(dest, skip=SKIP),
        'cwd': _cwd_key(cwd, dest),
        'rom': rom_shape(rom),
    }


def _cwd_key(cwd, dest):
    """환경 변수의 상대 경로(SAVE=end.mss 등)는 작업 폴더 기준이라 키에 넣는다."""
    if cwd is None:
        return 'inherit:' + str(Path.cwd().resolve())
    c, d = Path(cwd).resolve(), Path(dest).resolve()
    return 'dest' if c == d else ('dest:' + c.relative_to(d).as_posix() if d in c.parents else str(c))


def _outputs(dest, before):
    """돌린 뒤 새로 생겼거나 바뀐 파일."""
    out = {}
    for rel, h in tree_hash(dest, skip=SKIP).items():
        if before.get(rel) != h:
            out[rel] = h
    return out


def _clear(dest, before):
    for rel in tree_hash(dest, skip=SKIP):
        if rel not in before:
            (Path(dest) / rel).unlink(missing_ok=True)


def _execute(mesence, rom_path, script, dest, env, timeout, extra, log, cwd, tag):
    entry = dest / ENTRY
    out = dest / OUT
    err = dest / ERR
    out.unlink(missing_ok=True)
    err.unlink(missing_ok=True)
    # 맨 위 오류는 testrunner 를 멈추지 않아 시간 초과까지 돈다. 적고 바로 1 로 멈춘다
    entry.write_text(f'READSET_OUT = {json.dumps(str(out))}\n'
                     f'dofile({json.dumps(str(PRELUDE))})\n'
                     f'local ok, e = pcall(dofile, {json.dumps(str(Path(script).resolve()))})\n'
                     'if not ok then READSET_FAIL(e); emu.stop(1) end\n', encoding='utf-8')
    full = dict(env, READSET_OUT=str(out))
    rc, timed_out = None, False
    try:
        with (dest / log).open('w', encoding='utf-8') as fp:
            p = mesen.run(mesence, rom_path, entry, folder=dest, tag=tag, extra=(*extra, *FIXED_ARGS), env=full,
                          cwd=cwd, stdout=fp, stderr=subprocess.STDOUT, timeout=timeout, check=False)
            rc = p.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
    text = out.read_text() if out.exists() else None
    ranges = parse_ranges(text) if text is not None else None
    done = text is not None and text.split()[-1:] == [DONE]
    if timed_out:
        print(f'[dq4readset] {dest}: {timeout}초 안에 끝나지 않음(캐시에 넣지 않음)', file=sys.stderr)
    if err.exists() or (text is not None and not done and not timed_out):
        why = err.read_text(errors='replace').strip() if err.exists() else '읽은 집합 끝줄이 OK 가 아님'
        print(f'[dq4readset] {dest}: 장면 Lua 오류(캐시에 넣지 않음): {why[:500]}', file=sys.stderr)
        if WATCHDOG in why:
            rc = LUA_WATCHDOG
            print(f'[dq4readset] {dest}: MesenCE 가 Lua 콜백을 시간 제한으로 끊음(머신이 바쁠 때). 장면을 다시 돌릴 것',
                  file=sys.stderr)
        elif rc == 0:
            rc = LUA_ERROR
    elif text is None and rc == 0 and not timed_out:
        # 0 으로 끝났는데 읽은 집합이 없다: 머리말이 쓰지 못했거나 emu.stop 을 거치지 않고 끝났다
        print(f'[dq4readset] {dest}: 읽은 집합이 없음(캐시에 넣지 않음)', file=sys.stderr)
        rc = LUA_ERROR
    for f in (entry, out, err, dest / OUT_TMP):
        f.unlink(missing_ok=True)
    return rc, timed_out, ranges


# 장면 Lua 가 오류를 냈는데 MesenCE 가 0 으로 끝났을 때 돌려주는 종료 코드
LUA_ERROR = 70
# MesenCE 가 Lua 콜백 하나를 벽시계 시간 제한(사용자 설정 Debug.ScriptWindow.ScriptTimeout)으로 끊은 실행. 형식 문서
# 「장면 Lua 의 오류」. 다시 돌리지 않고 이 종료 코드로 실패를 알린다
WATCHDOG = 'Maximum execution time'
LUA_WATCHDOG = 71


def run(mesence, rom_path, script, dest, env, timeout=1800, extra=mesen.ARGS, log='mesen.log', cwd=None,
        tag='probe', accept=None, store=None):
    """장면 하나. dest 에 출력이 생긴다(맞으면 캐시에서 펼침). accept(dest) 가 거짓이면 캐시에 넣지 않는다.

    돌려주는 dict: cached(맞음), returncode, timed_out, readset(읽은 바이트 수), key."""
    info = _run(mesence, rom_path, script, dest, env, timeout, extra, log, cwd, tag, accept, store)
    stats = os.environ.get('DQ4_READSET_STATS')
    if stats:
        line = json.dumps({'script': Path(script).name, 'dest': str(dest), 'cached': info['cached'],
                           'readset': info.get('readset'), 'returncode': info.get('returncode')})
        with open(stats, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    return info


def _run(mesence, rom_path, script, dest, env, timeout, extra, log, cwd, tag, accept, store):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    rom = Path(rom_path).read_bytes()
    store = store or Store()
    parts = key_parts(mesence, rom, script, dest, env, extra, cwd)
    key = index_key(parts)
    before = parts['inputs']
    snapshot = dest / ROM_COPY
    hit, blobs = None, {}
    for e in (matches(store.entries(key), rom) if enabled() else ()):
        try:
            blobs = {rel: store.get_blob(sha) for rel, sha in e['files'].items()}
        except FileNotFoundError:
            store.drop(key, e)
            continue
        hit = e
        break
    if hit:
        for rel, data in blobs.items():
            p = dest / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        store.touch(key, hit)
        info = {'cached': True, 'returncode': hit.get('returncode'), 'timed_out': False,
                'readset': sum(n for _, n in unpack(hit['ranges'])), 'ranges': len(unpack(hit['ranges'])),
                'key': key}
        if random.random() >= verify_rate():
            return info
        _clear(dest, before)
        rc, timed_out, ranges = _snapshot_run(snapshot, rom, mesence, script, dest, env, timeout, extra, log, cwd, tag)
        # 다시 돌린 실행이 끝까지 가지 못했으면 출력을 견줄 수 없다. 항목은 두고 그 실패로 알린다
        if timed_out:
            raise SystemExit(f'읽은 바이트 캐시 재검증이 {timeout}초 안에 끝나지 않음: {dest}(항목은 그대로 둠)')
        # 0 이 아닌 종료(시간 제한·Lua 오류·MesenCE 가 죽음·emu.stop(n))는 키와 상관없는 실패일 수 있다. 캐시에는 0 으로
        # 끝난 실행만 들어가므로 견주지 않는다
        if rc != 0:
            raise SystemExit(f'읽은 바이트 캐시 재검증 실행이 실패함(종료 코드 {rc}): {dest}(항목은 그대로 둠)')
        want = {rel: content_hash(data, rel) for rel, data in blobs.items()}
        got = _outputs(dest, before)
        diff = mismatch(want, got, hit, rc, ranges)
        if diff:
            store.drop(key, hit)
            raise SystemExit(f'읽은 바이트 캐시가 틀렸다: {dest} 를 다시 돌린 결과가 캐시와 다름({diff}, 항목을 지움). '
                             'dq4readset 의 키에 빠진 입력이 있다')
        shots = differing(want, got, screens=True)
        if shots:
            print(f'[dq4readset] {dest}: 다시 돌린 화면 {",".join(shots[:8])} 이 캐시와 다름(화면 찍기는 결정적이지 않아 '
                  '판정에 쓰지 않는 출력)', file=sys.stderr)
        return {**info, 'verified': True, 'screens_differ': shots}
    rc, timed_out, ranges = _snapshot_run(snapshot, rom, mesence, script, dest, env, timeout, extra, log, cwd, tag)
    info = {'cached': False, 'returncode': rc, 'timed_out': timed_out,
            'readset': sum(n for _, n in ranges) if ranges is not None else None, 'ranges': len(ranges or ()),
            'key': key}
    # 0 이 아닌 종료(스크립트 오류·끝까지 못 감)나 읽은 집합이 없는 실행은 넣지 않는다
    if timed_out or rc != 0 or ranges is None or (accept and not accept(dest)):
        return info
    store.add(key, {'ranges': pack(ranges), 'digest': digest(rom, ranges), 'returncode': rc,
                    'when': time.strftime('%Y-%m-%d %H:%M')},
              {rel: (dest / rel).read_bytes() for rel in _outputs(dest, before)})
    try:
        limit = float(os.environ.get('DQ4_READSET_MAX_GB', '20')) * (1 << 30)
    except ValueError:
        limit = 20 * (1 << 30)
    if random.random() < 0.02:
        store.prune(limit)
    return info


def _snapshot_run(snapshot, rom, mesence, script, dest, env, timeout, extra, log, cwd, tag):
    """키를 만든 롬 바이트(rom)를 dest 에 써 두고 그 사본으로 돌린다."""
    snapshot.write_bytes(rom)
    try:
        return _execute(mesence, snapshot, script, dest, env, timeout, extra, log, cwd, tag)
    finally:
        snapshot.unlink(missing_ok=True)


def warp_timed_out(text):
    """dq5warp.lua 의 warp.txt 글이 MAXF 에 닿아 멈춘 장면인가. 그때도 종료 코드는 0 이고, 도착한 뒤였으면
    「arrived map」 과 「end map」 이 함께 찍혀 있어 그 줄만 보는 판정은 성공으로 읽는다. warp.txt 를 읽는 판정은 이것을 먼저 본다."""
    return ' timeout phase=' in text


def warp_finished(dest):
    """dq5warp.lua 장면이 끝까지 갔는가(warp.txt 가 있고 MAXF 에 닿지 않음). run 의 accept 로도 쓴다."""
    path = Path(dest) / 'warp.txt'
    return path.is_file() and not warp_timed_out(path.read_text(encoding='utf-8', errors='replace'))


def is_screen(rel):
    return str(rel).endswith(SCREENS)


def differing(want, got, screens=False):
    """want·got(상대 경로 → 해시)에서 다른 경로. screens 면 화면 찍기만, 아니면 그 밖의 것만."""
    return sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k) and is_screen(k) == screens)


def mismatch(want, got, entry, rc, ranges):
    """재검증: 캐시 항목과 다시 돌린 결과가 어디서 다른지(같으면 빈 글). 화면 찍기(SCREENS)는 견주지 않는다."""
    out = []
    files = differing(want, got)
    if files:
        out.append('출력 ' + ','.join(files[:8]))
    if rc != entry.get('returncode'):
        out.append(f'종료 코드 {entry.get("returncode")}→{rc}')
    if ranges is None or pack(ranges) != entry['ranges']:
        out.append('읽은 집합')
    return '; '.join(out)
