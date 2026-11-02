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
"""
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
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

PRELUDE = HERE / 'lua' / 'dq4readset.lua'
# 장면 Lua 가 dofile·require 할 수 있는 곳. 하나라도 바뀌면 모든 장면이 빗나간다
LUA_DIRS = (ROOT / 'tools' / 'lua', HERE / 'lua', HERE.parents[1] / 'dq5' / 'tools' / 'lua')
VERSION = 'readset-1'
ENTRY = '.readset-entry.lua'
OUT = '.readset.txt'
HDMA = OUT + '.hdma'
# 결과에 닿는 MesenCE 설정을 명령줄로 고정한다. 사용자 settings.json 의 값과 상관없이 같게 돈다
FIXED_ARGS = ('--Snes.RamPowerOnState=AllZeros', '--Snes.EnableRandomPowerOnState=false')
# 롬 머리 가운데 에뮬레이터가 매핑을 정하는 데 쓰는 칸(LoROM $7FD5~$7FD9). 체크섬은 빌드마다 바뀌고 결과와 무관해 뺀다
HEADER_MAP = slice(0x7FD5, 0x7FDA)
KEEP_ENTRIES = 8
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


def rom_shape(rom):
    """매핑을 정하는 머리 칸과 크기."""
    return f'{len(rom)}:{bytes(rom[HEADER_MAP]).hex()}'


def state_hash(data):
    """세이브스테이트 해시. 머리에 든 롬 파일 이름(실행마다 다름)은 지우고 본다."""
    data = bytes(data)
    m = _NAME.search(data, 0, 8192)
    if m and m.group(1)[0] == len(m.group(2)):
        data = data[:m.start()] + b'<rom>' + data[m.end():]
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    path = Path(path)
    data = path.read_bytes()
    return state_hash(data) if path.suffix == '.mss' else hashlib.sha256(data).hexdigest()


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


def canon_env(env, names, dest, code_dirs=()):
    """키에 넣을 환경 변수 값. 경로는 내용으로 바꾼다: dest 안이면 상대 경로, 파일이면 해시(.mss 는 이름 지운 해시),
    Lua 폴더(LIBDIR 등)면 'code'(Lua 는 따로 해시)."""
    dest = Path(dest).resolve()
    code = {Path(d).resolve() for d in code_dirs}
    out = {}
    for n in names:
        if n in ('SHOT_DIR', 'READSET_OUT', 'READSET_HDMA'):
            continue
        v = env.get(n)
        if v is None:
            continue
        p = Path(v)
        if v and p.is_absolute() and p.exists():
            r = p.resolve()
            if r == dest or dest in r.parents:
                v = 'dest:' + r.relative_to(dest).as_posix()
            elif r.is_file():
                v = 'file:' + file_hash(r)
            elif r in code:
                v = 'code'
            else:
                v = 'dir:' + json.dumps(tree_hash(r), sort_keys=True)
        out[n] = v
    return out


def index_key(parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def find(entries, rom):
    """entries 가운데 지금 롬과 읽은 바이트가 같은 첫 것."""
    for e in entries:
        if digest(rom, unpack(e['ranges'])) == e['digest']:
            return e
    return None


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

    def put_blob(self, data):
        sha = hashlib.sha256(data).hexdigest()
        p = self.blob_path(sha)
        if not p.exists():
            _replace(p, zlib.compress(data, 1))
        return sha

    def get_blob(self, sha):
        return zlib.decompress(self.blob_path(sha).read_bytes())

    def add(self, key, entry):
        with locked(self.root):
            old = [e for e in self.entries(key) if e['digest'] != entry['digest']]
            _replace(self.index_path(key), json.dumps([entry] + old[:KEEP_ENTRIES - 1]).encode())

    def touch(self, key, entry):
        """맞은 항목을 맨 앞으로(오래 안 쓴 것부터 지우게)."""
        with locked(self.root):
            es = self.entries(key)
            es = [entry] + [e for e in es if e['digest'] != entry['digest']]
            _replace(self.index_path(key), json.dumps(es).encode())

    def drop(self, key, entry):
        with locked(self.root):
            es = [e for e in self.entries(key) if e['digest'] != entry['digest']]
            _replace(self.index_path(key), json.dumps(es).encode())

    def size(self):
        return sum(f.stat().st_size for f in (self.root / 'blob').rglob('*') if f.is_file())

    def prune(self, limit):
        """limit 바이트를 넘으면 오래 안 쓴 index 부터 지우고, 어느 index 도 가리키지 않는 blob 을 지운다."""
        with locked(self.root):
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
                if f.is_file() and f.name not in live:
                    f.unlink(missing_ok=True)


# ---------------------------------------------------------------- 실행

def mesence_settings(mesence):
    """사용자 settings.json 가운데 SNES·에뮬레이션 절(명령줄로 고정하지 않은 설정도 결과에 닿을 수 있다)."""
    for folder in mesen.save_dirs(mesence):
        p = folder.parent / 'settings.json'
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding='utf-8-sig'))
            except ValueError:
                return 'unreadable'
            return {k: data.get(k) for k in ('Snes', 'Emulation')}
    return None


def mesence_stamp(mesence):
    st = Path(mesence).stat()
    return f'{st.st_size}:{st.st_mtime_ns}'


def key_parts(mesence, rom, script, dest, env, extra):
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
        'env': canon_env(env, names, dest, [d for d in LUA_DIRS] + ([libdir] if libdir else [])),
        'inputs': tree_hash(dest, skip=(ENTRY, OUT, HDMA)),
        'rom': rom_shape(rom),
    }


def _outputs(dest, before):
    """돌린 뒤 새로 생겼거나 바뀐 파일."""
    out = {}
    for rel, h in tree_hash(dest, skip=(ENTRY, OUT, HDMA)).items():
        if before.get(rel) != h:
            out[rel] = h
    return out


def _clear(dest, before):
    for rel in tree_hash(dest, skip=(ENTRY, OUT, HDMA)):
        if rel not in before:
            (Path(dest) / rel).unlink(missing_ok=True)


def _execute(mesence, rom_path, script, dest, env, timeout, extra, log, cwd, tag):
    entry = dest / ENTRY
    out = dest / OUT
    out.unlink(missing_ok=True)
    entry.write_text(f'READSET_OUT = {json.dumps(str(out))}\n'
                     f'dofile({json.dumps(str(PRELUDE))})\n'
                     f'dofile({json.dumps(str(Path(script).resolve()))})\n', encoding='utf-8')
    full = dict(env, READSET_OUT=str(out))
    rc, timed_out = None, False
    try:
        with (dest / log).open('w', encoding='utf-8') as fp:
            p = mesen.run(mesence, rom_path, entry, folder=dest, tag=tag, extra=(*extra, *FIXED_ARGS), env=full,
                          cwd=cwd, stdout=fp, stderr=subprocess.STDOUT, timeout=timeout, check=False)
            rc = p.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
    ranges = parse_ranges(out.read_text()) if out.exists() else None
    entry.unlink(missing_ok=True)
    out.unlink(missing_ok=True)
    return rc, timed_out, ranges


def run(mesence, rom_path, script, dest, env, timeout=1800, extra=mesen.ARGS, log='mesen.log', cwd=None,
        tag='probe', accept=None, store=None):
    """장면 하나. dest 에 출력이 생긴다(맞으면 캐시에서 펼침). accept(dest) 가 거짓이면 캐시에 넣지 않는다.

    돌려주는 dict: cached(맞음), returncode, timed_out, readset(읽은 바이트 수), key."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    rom = Path(rom_path).read_bytes()
    store = store or Store()
    parts = key_parts(mesence, rom, script, dest, env, extra)
    key = index_key(parts)
    before = parts['inputs']
    hit = find(store.entries(key), rom) if enabled() else None
    if hit:
        for rel, sha in hit['files'].items():
            p = dest / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(store.get_blob(sha))
        store.touch(key, hit)
        info = {'cached': True, 'returncode': hit.get('returncode'), 'timed_out': False,
                'readset': sum(n for _, n in unpack(hit['ranges'])), 'ranges': len(unpack(hit['ranges'])),
                'key': key}
        if random.random() >= verify_rate():
            return info
        _clear(dest, before)
        rc, timed_out, ranges = _execute(mesence, rom_path, script, dest, env, timeout, extra, log, cwd, tag)
        got = _outputs(dest, before)
        if timed_out or got != {rel: _hash_blob(store, sha, rel) for rel, sha in hit['files'].items()}:
            store.drop(key, hit)
            raise SystemExit(f'읽은 바이트 캐시가 틀렸다: {dest} 를 다시 돌린 출력이 캐시와 다름(항목을 지움). '
                             'dq4readset 의 키에 빠진 입력이 있다')
        return {**info, 'verified': True}
    rc, timed_out, ranges = _execute(mesence, rom_path, script, dest, env, timeout, extra, log, cwd, tag)
    info = {'cached': False, 'returncode': rc, 'timed_out': timed_out,
            'readset': sum(n for _, n in ranges) if ranges is not None else None, 'ranges': len(ranges or ()),
            'key': key}
    if timed_out or ranges is None or (accept and not accept(dest)):
        return info
    files = {}
    for rel in _outputs(dest, before):
        files[rel] = store.put_blob((dest / rel).read_bytes())
    store.add(key, {'ranges': pack(ranges), 'digest': digest(rom, ranges), 'files': files, 'returncode': rc,
                    'when': time.strftime('%Y-%m-%d %H:%M')})
    try:
        limit = float(os.environ.get('DQ4_READSET_MAX_GB', '20')) * (1 << 30)
    except ValueError:
        limit = 20 * (1 << 30)
    if random.random() < 0.02:
        store.prune(limit)
    return info


def _hash_blob(store, sha, rel):
    data = store.get_blob(sha)
    return state_hash(data) if rel.endswith('.mss') else hashlib.sha256(data).hexdigest()
