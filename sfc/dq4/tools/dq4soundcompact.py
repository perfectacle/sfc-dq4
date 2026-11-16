"""dq4soundport 가 만든 시퀀스 글에서 반복되는 명령을 되풀이(F5)·부르기(F8)로 묶는다.

곡 빌드 시간의 대부분이 여기라 결과를 파일 캐시에 둔다. 키는 입력 줄과 이 파일·dq5song.py 의 해시라, 변환 규칙
(dq4soundport)을 고쳐도 묶기 결과는 그대로 다시 쓰고, 묶기·인코딩을 고치면 옛 결과를 쓰지 않는다.
"""

import atexit
from array import array
import functools
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'sfc/dq5/tools'))

from dq5song import _encode_line  # noqa: E402
import dq4native  # noqa: E402

_COMPACTED = {}
COMPACT_HASH = hashlib.sha256(Path(__file__).read_bytes() + (ROOT / 'sfc/dq5/tools/dq5song.py').read_bytes()).hexdigest()


# 드라이버 15E5 는 음이 끝나기 1틱 전에 다음 바이트를 실제 자리에서 미리 본다. 이 명령은 건너뛰고(A0~B5 는 바이트
# 범위로 따로 봄), 처음 만난 바이트가 쉼(00·50)이면 KOF 를 걸지 않는다. 부르기·돌아가기·되풀이는 따라가지 않는다.
PEEK_SKIP = {'gate_preset', 'gate', 'volume2', 'tempo', 'follow', 'follow_off'}
MAX_CALL_DEPTH = 3  # SPC 0267 의 돌아올 자리 칸(192E: 0240+X 가 6 이상이면 부르기를 무시)
LOOP_OPS = {'loop'}
BARRIER_OPS = {'jump', 'end', 'loop', 'call', 'ret'}
_KIND_CODE = {'label': 0, 'note': 1, 'rest': 2, 'skip': 3, 'cmd': 4}
_NOTE, _REST, _SKIP, _CMD, _WALL = 1, 2, 3, 4, 5


@functools.cache
def _op(line):
    return line.split()[0]


@functools.cache
def _kind(line):
    op = _op(line)
    if op.endswith(':'):
        return 'label'
    if op in ('note', 'tie'):
        return 'note'
    if op == 'rest':
        return 'rest'
    if op in PEEK_SKIP:
        return 'skip'
    return 'cmd'


@functools.cache
def _size(line):
    return 0 if line.split()[0].endswith(':') else len(_encode_line(line.split(), 0, None))


class _Program:
    """목소리 본문과 서브루틴 본문(명령 줄 목록)을 들고, 반복을 되풀이(F5)·부르기(F8)로 바꾼다.

    바꾸는 것은 바이트의 실행 순서를 그대로 두는 묶음뿐이다. 다만 15E5 의 미리 보기는 실제 자리의 다음 바이트를
    보므로, 음표(쉼 포함, 1583 이 쉼의 15 를 0 으로 둠) 바로 뒤에 F8·F9·F5 가 오고 실행상 다음이 쉼이면 원래 없던 KOF 가
    생긴다. 그런 자리는 묶지 않는다.
    """

    def __init__(self, voices):
        self.seqs = dict(voices)
        self.voices = [name for name, _ in voices]
        self.subs = []
        self.serial = 0

    def lead(self, name, index, depth=0):
        """seqs[name][index] 부터 실행했을 때 미리 보기가 처음 만나는 것의 종류. 서브루틴 본문 끝이면 'end'."""
        body = self.seqs[name]
        for line in body[index:]:
            kind = _kind(line)
            if kind in ('skip', 'label'):
                continue
            if _op(line) == 'call' and depth < 8:
                inner = self.lead(line.split()[-1], 0, depth + 1)
                if inner != 'end':
                    return inner
                continue
            return kind
        return 'end'

    def block_ok(self, name, start, stop):
        """seqs[name][start:stop] 을 부르기로 바꿔도 미리 보기 결과가 같은가."""
        body = self.seqs[name]
        prev = next((_kind(x) for x in reversed(body[:start]) if _kind(x) not in ('skip', 'label')), None)
        if prev in ('note', 'rest'):
            head = next((x for x in body[start:] if _kind(x) not in ('skip', 'label')), None)
            if head is not None and _op(head) == 'call':
                kind = self.lead(name, start)
            else:
                kind = _kind(head) if head is not None else 'end'
            if kind in ('rest', 'end'):
                return False
        last = next((_kind(x) for x in reversed(body[start:stop]) if _kind(x) != 'skip'), None)
        if last in ('note', 'rest') and self.lead(name, stop) == 'rest':
            return False
        return True

    def depths(self):
        """서브루틴마다 (아래로 가장 긴 부르기 사슬의 길이, 위에서 내려와 닿는 가장 긴 사슬의 길이). 둘 다 자신을 셈."""
        calls = {sub: {x.split()[-1] for x in self.seqs[sub] if _op(x) == 'call'} for sub in self.subs}
        callers = {}
        for sub, inner in calls.items():
            for c in inner:
                callers.setdefault(c, []).append(sub)
        down, up = {}, {}

        def height(sub):
            if sub not in down:
                down[sub] = 1 + max((height(c) for c in calls.get(sub, ())), default=0)
            return down[sub]

        def depth(sub):
            if sub not in up:
                up[sub] = 1 + max((depth(c) for c in callers.get(sub, ())), default=0)
            return up[sub]
        for sub in calls:
            height(sub)
            depth(sub)
        return down, up

    def loops(self):
        """목소리 본문에서 바로 이어 되풀이되는 묶음을 F5 로. 되풀이 셈은 트랙마다 하나라 겹치지 않게 맨 위에서만."""
        for name in self.voices:
            body = self.seqs[name]
            sizes = [_size(x) for x in body]
            barrier = [_kind(x) == 'label' or _op(x) in BARRIER_OPS for x in body]
            found = []
            n = len(body)
            for period in range(1, min(256, n // 2) + 1):
                run = 0
                for i in range(n - period - 1, -1, -1):
                    run = run + 1 if body[i] == body[i + period] and not barrier[i] else 0
                    if run >= period and (i == 0 or body[i - 1] != body[i - 1 + period] or barrier[i - 1]):
                        reps = (run + period) // period
                        size = sum(sizes[i:i + period])
                        if (reps - 1) * size - 4 > 0:
                            found.append(((reps - 1) * size - 4, i, period, reps, run + period))
            taken = [False] * n
            chosen = []
            for _, i, period, reps, length in sorted(found, reverse=True):
                for shift in range(min(period, length - 2 * period + 1)):
                    start = i + shift
                    r = min(255, (length - shift) // period)
                    stop = start + r * period
                    if r < 2 or any(taken[start:stop]):
                        continue
                    if (r - 1) * sum(sizes[start:start + period]) - 4 <= 0 or not self.loop_ok(body, start, period, stop):
                        continue
                    chosen.append((start, period, r))
                    for k in range(start, stop):
                        taken[k] = True
                    break
            new = []
            i = 0
            starts = {c[0]: c for c in chosen}
            while i < n:
                if i in starts:
                    _, period, r = starts[i]
                    label = f'Lrepeat{self.serial}'
                    self.serial += 1
                    new += [label + ':', *body[i:i + period], f'  loop {r:02X} -> {label}']
                    i += period * r
                else:
                    new.append(body[i])
                    i += 1
            self.seqs[name] = new

    def loop_ok(self, body, start, period, stop):
        last = next((_kind(x) for x in reversed(body[start:start + period]) if _kind(x) != 'skip'), None)
        if last not in ('note', 'rest'):
            return True

        def lead(index):
            return next((_kind(x) for x in body[index:] if _kind(x) not in ('skip', 'label')), 'end')
        return lead(start) not in ('rest', 'end') and lead(stop) not in ('rest', 'end')

    def calls(self, max_tokens=256):
        """여러 곳에 나오는 묶음을 깊이 3 안의 서브루틴으로. 한 번에 아끼는 바이트가 가장 큰 것부터."""
        cache, intern = {}, {}
        while True:
            parts = [cache.get(name) or cache.setdefault(name, self._layout(name, intern)) for name in self.seqs]
            where = list(itertools.chain.from_iterable(part[0] for part in parts))
            line_ids = np.concatenate([part[1] for part in parts])
            kinds = np.concatenate([part[2] for part in parts])
            sizes = np.concatenate([part[3] for part in parts])
            positions_all = np.arange(len(line_ids))
            # 벽(이름표·되돌아갈 수 없는 흐름·시퀀스 끝)은 자리마다 다른 음수, 나머지 줄은 처음 나온 차례의 번호
            wall = line_ids < 0
            body = line_ids[~wall]
            _, first, inverse = np.unique(body, return_index=True, return_inverse=True)
            rank = np.empty(len(first), dtype=np.int64)
            rank[np.argsort(first, kind='stable')] = np.arange(len(first))
            arr = np.where(wall, -positions_all - 1, 0)
            arr[~wall] = rank[inverse]
            arr = arr.tolist()
            prefix = [0, *np.cumsum(sizes).tolist()]
            # 토막마다 쓰는 것: 그 안에서 마지막으로 쉼·skip 이 아닌 자리(last_good), 쉼 바로 뒤의 skip 이 아닌 첫 자리(next_after_rest)
            last_good = np.maximum.accumulate(np.where((kinds == _NOTE) | (kinds == _CMD), positions_all, -1)).tolist()
            after_rest = np.zeros(len(kinds), dtype=bool)
            after_rest[1:] = (kinds[:-1] == _REST) & (kinds[1:] != _SKIP)
            ahead = np.where(after_rest, positions_all, len(kinds))
            next_after_rest = np.minimum.accumulate(ahead[::-1])[::-1].tolist()
            best = None
            down, up = self.depths()
            top, subs = max(down.values(), default=0), set(self.subs)

            def consider(positions, length):
                nonlocal best
                size = prefix[positions[0] + length] - prefix[positions[0]]
                if size <= 4 or (size - 3) * len(positions) - size - 1 <= (best[0] if best else 0):
                    return
                chosen = []
                for p in sorted(positions):
                    if chosen and p < chosen[-1] + length:
                        continue
                    name, index = where[p]
                    if self.block_ok(name, index, index + length):
                        chosen.append(p)
                saving = (size - 3) * len(chosen) - size - 1
                if len(chosen) < 2 or saving <= (best[0] if best else 0):
                    return
                name, index = where[chosen[0]]
                block = self.seqs[name][index:index + length]
                label = f'Lphrase{self.serial}'
                # 새 서브루틴이 늘리는 사슬은 그것을 품는 서브루틴을 지나는 것뿐이다
                own = 1 + max((down.get(x.split()[-1], 1) for x in block if _op(x) == 'call'), default=0)
                hosts = {where[p][0] for p in chosen} & subs
                if max([top, own] + [up[h] + own for h in hosts]) > MAX_CALL_DEPTH:
                    return
                best = (saving, label, block, [where[p] for p in chosen], length)

            for length, positions in _repeats(arr, max_tokens):
                if len(positions) < 2:
                    continue
                first = positions[0]
                # 음표로 끝나 뒤가 쉼이거나 쉼으로 시작해 앞이 음표인 곳은 block_ok 가 거른다. 끝을 쉼이 아닌 것 앞으로 당기고
                # 처음을 쉼 뒤로 미룬 토막도 함께 본다(같은 자리 집합에서 나오므로 따로 찾지 않아도 된다).
                shrink = last_good[first + length - 1] - first
                shrink = shrink if shrink >= 2 else None
                shift = next_after_rest[first + 1] - first
                shift = shift if shift <= length - 2 else None
                for head in (0, shift):
                    if head is None:
                        continue
                    for stop in (length, shrink):
                        if stop is not None and stop - head >= 2:
                            consider([q + head for q in positions], stop - head)
            if best is None:
                return
            _, label, block, places, length = best
            self.serial += 1
            call = f'  call -> {label}'
            for name, index in sorted(places, key=lambda x: -x[1]):
                self.seqs[name][index:index + length] = [call]
                cache[name] = self._splice(name, cache[name], index, length, call, intern)
            self.seqs[label] = list(block)
            self.subs.append(label)

    def _layout(self, name, intern):
        """calls 가 반복마다 잇는 시퀀스 하나의 몫: 자리(where), 줄 번호(벽은 -1), 종류 부호, 바이트 크기. 끝에 벽 하나."""
        body = self.seqs[name]
        where = [(name, index) for index in range(len(body))] + [(name, None)]
        ids = [-1 if _kind(line) == 'label' or _op(line) in BARRIER_OPS - {'call'} else intern.setdefault(line, len(intern))
               for line in body] + [-1]
        kinds = [_KIND_CODE[_kind(line)] for line in body] + [_WALL]
        sizes = [_size(line) for line in body] + [0]
        return where, np.array(ids, dtype=np.int64), np.array(kinds, dtype=np.int8), np.array(sizes, dtype=np.int64)

    def _splice(self, name, part, index, length, line, intern):
        """_layout(name) 의 몫에서 [index, index + length) 를 줄 하나로 바꾼 것(self.seqs[name] 은 이미 바뀜)."""
        _, ids, kinds, sizes = part
        where = [(name, i) for i in range(len(self.seqs[name]))] + [(name, None)]
        tail = index + length
        return (where,
                np.concatenate((ids[:index], [intern.setdefault(line, len(intern))], ids[tail:])),
                np.concatenate((kinds[:index], [_KIND_CODE[_kind(line)]], kinds[tail:])).astype(np.int8),
                np.concatenate((sizes[:index], [_size(line)], sizes[tail:])))

    def lines(self):
        out = []
        for name in self.voices:
            out += [name + ':', *self.seqs[name]]
        for sub in self.subs:
            out += [sub + ':', *self.seqs[sub], '  ret']
        return out


class _Native:
    """Go 도구 dq4repeats(sfc/dq4/tools/native/dq4repeats)를 한 번 띄워 두고 요청마다 쓴다."""

    def __init__(self, path):
        self.proc = subprocess.Popen([str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.lock = threading.Lock()
        atexit.register(self.close)

    def repeats(self, arr, max_tokens):
        data = array('i', [len(arr), max_tokens, *arr])
        if sys.byteorder != 'little':
            data.byteswap()
        with self.lock:
            self.proc.stdin.write(data.tobytes())
            self.proc.stdin.flush()
            count = self._ints(1)[0]
            out = []
            for _ in range(count):
                length, k = self._ints(2)
                out.append((length, self._ints(k).tolist()))
        return out

    def _ints(self, k):
        raw = self.proc.stdout.read(4 * k)
        if len(raw) != 4 * k:
            raise RuntimeError('dq4repeats 가 답하지 않음')
        got = array('i', raw)
        if sys.byteorder != 'little':
            got.byteswap()
        return got

    def close(self):
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write(array('i', [-1, 0]).tobytes())
                self.proc.stdin.close()
            except OSError:
                pass
            self.proc.wait()


@functools.cache
def _native():
    path = dq4native.binary('dq4repeats')
    return _Native(path) if path else None


def _repeats(arr, max_tokens):
    """arr 에서 두 번 이상 나오는 토막(음수는 서로 다른 벽)을 (길이, [시작 자리]) 로. 접미사 배열의 LCP 구간.
    Go 도구를 만들어 두었으면 그것이, 없으면 _repeats_py 가 같은 차례로 낸다."""
    native = _native()
    if native is not None:
        return native.repeats(arr, max_tokens)
    return _repeats_py(arr, max_tokens)


def _repeats_py(arr, max_tokens):
    n = len(arr)
    if not n:
        return
    # 토큰을 차례를 지키는 고정 폭 빅엔디언 바이트(가장 작은 값이 1, 끝 뒤는 0 으로 채움)로 바꿔, 자리마다 앞 max_tokens 토큰을
    # 바이트 문자열 하나로 만든다. 그 문자열의 안정 정렬이 arr[i:i + max_tokens] 목록의 안정 정렬과 같은 차례다(짧은 쪽이 앞).
    shifted = np.asarray(arr, dtype=np.int64)
    shifted = shifted - shifted.min() + 1
    width = 2 if shifted.max() < 1 << 16 else 4
    span = width * max_tokens
    flat = np.zeros(n * width + span, dtype=np.uint8)
    flat[:n * width] = np.frombuffer(shifted.astype(f'>u{width}').tobytes(), dtype=np.uint8)
    windows = np.lib.stride_tricks.as_strided(flat, shape=(n, span), strides=(width, 1))
    keys = np.ascontiguousarray(windows)
    order = np.argsort(keys.view(f'S{span}').ravel(), kind='stable')
    ranked = keys[order]
    # 이웃한 두 자리가 함께 갖는 앞 토큰 수. 벽(음수)은 자리마다 달라 같을 수 없고, 끝 뒤 0 은 어떤 토큰과도 다르다
    differ = ranked[1:] != ranked[:-1]
    first = np.where(differ.any(axis=1), differ.argmax(axis=1), span)
    lcp = [0, *(first // width).tolist()]
    order = order.tolist()
    stack = [(0, 0)]
    for k in range(1, n + 1):
        value = lcp[k] if k < n else 0
        left = k - 1
        while value < stack[-1][0]:
            length, left = stack.pop()
            if length >= 2:
                yield length, order[left:k]
        if value > stack[-1][0]:
            stack.append((value, left))


def compact(lines, cache_dir=None):
    """반복되는 명령을 되풀이(F5)와 깊이 3 안의 부르기(F8)로 묶는다. 실행되는 바이트의 순서·시각과
    15E5 미리 보기가 보는 바이트의 종류는 그대로다(dq4soundport.execution_trace(peek=True) 로 검산).

    cache_dir 를 주면 결과를 COMPACT_HASH 와 입력으로 만든 키의 파일에 두고 다시 쓴다."""
    key = hashlib.sha256((COMPACT_HASH + '\n' + '\n'.join(lines)).encode()).hexdigest()
    if cache_dir is None:
        # 같은 빌드가 같은 줄을 여러 번 묶는다. 캐시를 끈 빌드도 프로세스 안에서는 한 번만 묶는다
        if key not in _COMPACTED:
            _COMPACTED[key] = tuple(_compact(lines))
        return list(_COMPACTED[key])
    path = Path(cache_dir) / 'compact' / key[:2] / (key + '.json.gz')
    if path.is_file():
        return json.loads(gzip.decompress(path.read_bytes()))
    result = _compact(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 여러 세션이 같은 캐시를 함께 쓰므로 다 쓴 파일만 제자리로 옮긴다
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as f:
        f.write(gzip.compress(json.dumps(result).encode(), mtime=0))
    Path(f.name).replace(path)
    return result


def _compact(lines):
    head = [s for s in lines if s and not s[0].isspace() and not s.endswith(':')]
    voices, name = [], None
    for line in lines:
        if line in head:
            continue
        if line.endswith(':') and line.startswith('Lvoice'):
            name = line[:-1]
            voices.append((name, []))
        else:
            voices[-1][1].append(line)
    program = _Program(voices)
    program.loops()
    program.calls()
    return head + program.lines()
