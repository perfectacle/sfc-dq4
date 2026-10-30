"""NDS DQ4 악보를 DQ5 SPC 시퀀스로 옮긴다.

입력은 nds/dq4/tools/ndssound.py가 내는 악보 JSON이다. 시퀀스 형식과
드라이버 근거는 sfc/dq5/docs/dq5-sound-format.md의 SPC 154E·17B1·182E.
음색 대응은 청취 승인을 받지 않은 편곡 초안이며 손실은 보고서에 남긴다.
생성한 악보·바이너리는 롬 파생 자료이므로 work/에만 둔다.
"""

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / 'sfc/dq5/tools'), str(ROOT / 'nds/dq4/tools')]

from dq5song import _encode_line, assemble, header, listing, step, walk  # noqa: E402

# NDS 프로그램 번호는 GM 이름을 보장하지 않는다. 이 표는 교체 가능한 편곡 설정이다.
PROGRAM_MAP = {
    0: 0x0A, 1: 0x0A, 2: 0x0A, 3: 0x0A, 5: 0x0A, 6: 0x0A,
    9: 0x0A, 15: 0x0A, 18: 0x18, 19: 0x18, 25: 0x0A,
    35: 0x16, 39: 0x16, 40: 0x18, 41: 0x18, 43: 0x16, 44: 0x18,
    45: 0x0A, 46: 0x0A, 47: 0x15, 48: 0x18, 50: 0x18,
    52: 0x18, 53: 0x18, 54: 0x18, 55: 0x18,
    56: 0x1C, 58: 0x0B, 59: 0x0B, 60: 0x0B, 62: 0x0B, 63: 0x0B,
    64: 0x0B, 65: 0x0B, 68: 0x18, 73: 0x03, 80: 0x1F,
    81: 0x18, 93: 0x18, 100: 0x18, 110: 0x18, 127: 0x13,
}
NDS_TICKS_PER_SECOND_PER_TEMPO = (33513982 / (64 * 2728)) / 240
DQ5_TICKS_PER_SECOND_PER_TEMPO = 0.8


@dataclass
class Conversion:
    text: str
    sequence: bytes
    samples: list[int]
    report: dict
    chain: bytes | None = None  # split_tick 를 주면 본체 시퀀스(sequence 는 앞부분)


def dq5_tempo(value):
    result = round(value * NDS_TICKS_PER_SECOND_PER_TEMPO / DQ5_TICKS_PER_SECOND_PER_TEMPO)
    if not 1 <= result <= 255:
        raise ValueError(f'tempo outside DQ5 range: {value}')
    return result


def simplify_tempo(points, end, tolerance):
    """조각별 일정한 템포를 시각 오차 tolerance초 안에서 더 적은 정수 DQ5 템포로 합친다.

    NDS 악보는 1 BPM 단위 루바토라 그대로 옮기면 템포 명령이 시퀀스를 채운다.
    오차는 원래 템포 경계마다 누적 시각으로 재며, 앞 구간의 반올림 오차도 이어서 센다.
    points: [(tick, 실수 DQ5 템포)], 첫 tick 은 0. 반환: ({tick: 정수 템포}, 최대 오차초).
    """
    points = sorted(points)
    # 정수 템포는 긴 구간에서 소수 템포만큼 밀린다. 박마다 나눌 자리를 두어 이웃 정수를 번갈아 쓰게 한다.
    known = {t for t, _ in points}
    beats = [(k, v) for (t, v), (nxt, _) in zip(points, points[1:] + [(end, 0)])
             for k in range(t + 48, nxt, 48) if k not in known]
    points = sorted(points + beats)
    cuts = [t for t, _ in points if t < end] + [end]
    real = [0.0]
    for (t, v), nxt in zip(points, cuts[1:]):
        real.append(real[-1] + (nxt - t) / (v * DQ5_TICKS_PER_SECOND_PER_TEMPO))
    result, worst = {}, 0.0
    i, model = 0, 0.0
    while i < len(cuts) - 1:
        best = None
        for j in range(i + 1, len(cuts)):
            span = real[j] - model
            if span <= 0:
                continue
            value = max(1, min(255, round((cuts[j] - cuts[i]) / (span * DQ5_TICKS_PER_SECOND_PER_TEMPO))))
            rate = 1 / (value * DQ5_TICKS_PER_SECOND_PER_TEMPO)
            error = max(abs(model + (cuts[k] - cuts[i]) * rate - real[k]) for k in range(i + 1, j + 1))
            if error > tolerance and best is not None:
                break
            best = (j, value, error, model + (cuts[j] - cuts[i]) * rate)
            if error > tolerance:
                break
        if best is None:
            # 앞 구간의 반올림으로 모형 시각이 이미 남은 경계를 모두 지났다. 가장 빠른 템포로 한 구간만 간다.
            j = i + 1
            value = 255
            end_time = model + (cuts[j] - cuts[i]) / (value * DQ5_TICKS_PER_SECOND_PER_TEMPO)
            best = (j, value, abs(end_time - real[j]), end_time)
        j, value, error, model = best
        if not result or result[max(result)] != value:
            result[cuts[i]] = value
        worst = max(worst, error)
        i = j
    return result, worst


def score_bounds(score):
    start, length = score.get('loop_start'), score.get('loop_len')
    if start is not None:
        if not isinstance(length, int) or length <= 0 or start < 0:
            raise ValueError('invalid loop bounds')
        end = start + length
    else:
        end = score['end_tick']
    if not isinstance(end, int) or end <= 0 or end > score['end_tick']:
        raise ValueError('invalid score end')
    return start, end


def controllers(score, end):
    """명령을 재생해 음 도중의 CC를 복원한다. timeline의 음표 시점 값만으로는 부족하다."""
    if not score.get('channels') or not all('items' in c for c in score['channels']):
        return {}, False
    from ndssound import score_events
    events, _ = score_events(score | {'end_tick': end})
    names = [c['name'] for c in score['channels']]
    result = defaultdict(list)
    for tick, channel, op, *args in events:
        if op == 'cc' and args[0] in (7, 10, 11):
            result[names[channel]].append((tick, args[0], args[1]))
    return dict(result), True


def allocate(score, voices, end, tail_ticks=0, lanes_for=None):
    """원래 우선순위와 선율·저음을 보존하며, 넘친 음은 늦게 재발음하지 않고 버린다.

    lanes_for 는 {NDS 트랙 이름: 쓸 목소리 목록}. 준 트랙의 음은 그 목소리에만 들어가고, 그 목소리가 모두
    울리는 중이면 우선순위가 낮은 쪽을 끊거나 버린다. 목소리마다 트랙이 바뀌지 않아 악기·팬·세기 명령이 준다.
    """
    candidates = []
    silent = 0
    for i, source in enumerate(score['timeline']):
        if source.get('op') != 'note' or source['tick'] >= end:
            continue
        if source['tick'] < 0 or source['gate'] < 0:
            raise ValueError('negative note time')
        if not source['velocity'] or not source.get('volume', 127) or not source.get('expression', 127):
            silent += 1
            continue
        if not source['gate']:
            raise ValueError('zero-gate indefinite notes require explicit release conversion')
        candidates.append(dict(source, uid=i, end=min(end, source['tick'] + source['gate'])))
    medians = {}
    for channel in sorted({n['ch'] for n in candidates}):
        pitches = [n['note'] for n in candidates if n['ch'] == channel and n['program'] not in (47, 127)]
        if pitches:
            medians[channel] = statistics.median(pitches)
    bass = min(medians, key=medians.get) if medians else None
    melody = score.get('channels', [{}])[0].get('name', 'track0')
    starts = defaultdict(list)
    for note in candidates:
        starts[note['tick']].append(note)
    lanes = [[] for _ in range(voices)]
    active = {}
    dropped, truncated = [], []
    peak = 0
    edges = []
    for n in candidates:
        edges += [(n['tick'], 1), (n['end'], -1)]
    concurrent = 0
    for _, delta in sorted(edges):
        concurrent += delta
        peak = max(peak, concurrent)

    def priority(n):
        role = 2 if n['ch'] == melody or n['ch'] == bass else 1
        outer = -n['note'] if n['ch'] == bass else n['note']
        return role, n.get('priority', 64), n['velocity'], outer, -n['uid']

    lanes_for = lanes_for or {}
    if any(not ls or any(not 0 <= k < voices for k in ls) for ls in lanes_for.values()):
        raise ValueError('lanes_for lists lanes outside the voice range')

    def cut(lane, tick):
        note = active.pop(lane)
        old_end = note['end']
        note['end'] = tick
        truncated.append({'source': note['uid'], 'tick': tick, 'lost_ticks': old_end - tick})

    for tick, incoming in sorted(starts.items()):
        active = {lane: n for lane, n in active.items() if n['end'] > tick}
        if lanes_for:
            # 목소리를 고정하면 목소리마다 따로 겨룬다. 전체 상위 voices 개로 고르면 제 목소리가 비어 있는 음도 버려진다.
            keep = {n['uid'] for n in incoming}
        else:
            selected = sorted(list(active.values()) + incoming, key=priority, reverse=True)[:voices]
            keep = {n['uid'] for n in selected}
            for lane, note in list(active.items()):
                if note['uid'] not in keep:
                    cut(lane, tick)
        for note in sorted(incoming, key=priority, reverse=True):
            if note['uid'] not in keep:
                dropped.append(note['uid'])
                continue
            allowed = lanes_for.get(note['ch'], range(voices))
            free = [lane for lane in allowed if lane not in active]
            if not free:
                weaker = [lane for lane in allowed if priority(active[lane]) < priority(note)]
                if not weaker:
                    dropped.append(note['uid'])
                    continue
                lane = min(weaker, key=lambda k: priority(active[k]))
                cut(lane, tick)
                free = [lane]

            def idle(k):
                return tick - lanes[k][-1]['end'] if lanes[k] else 1 << 30

            # DQ5 드라이버는 다음 바이트가 음이면 1틱 전에 KOF 해 8ms 만에 끊는다(SPC 15E5). 앞 음 꼬리가
            # 소프트 릴리스로 줄어들 틈이 있는 목소리를 먼저 고르고, 그중 같은 성부를 고르면 팬·악기 명령이 준다.
            lane = min(free, key=lambda k: (idle(k) < tail_ticks, not lanes[k] or lanes[k][-1]['ch'] != note['ch'],
                                            -min(idle(k), tail_ticks), k))
            lanes[lane].append(note)
            active[lane] = note
    return lanes, {'source_notes': len(candidates), 'silent_notes': silent,
                   'emitted_notes': sum(map(len, lanes)), 'dropped_notes': len(dropped),
                   'dropped_source_indices': dropped, 'shortened_notes': truncated,
                   'peak_source_voices': peak, 'melody_channel': melody, 'bass_channel': bass}


def resolve_sample(mapping, program, note):
    value = mapping[program]
    if isinstance(value, int):
        return value
    matches = [r['sample'] for r in value if r['lo'] <= note <= r['hi']]
    if len(matches) != 1:
        raise ValueError(f'program {program} key {note}: expected one sample region, got {len(matches)}')
    return matches[0]


def _pan(value):
    # DQ5의 양수는 오른쪽, 00은 중앙이다. NDS는 00~7F, 중앙 40.
    return max(-127, min(127, (value - 64) * 2)) & 255


def _level(note, volume, expression, master):
    return max(0, min(255, round(255 * note['velocity'] * volume * expression * master / 127 ** 4)))


def _near(a, b, tolerance_db):
    return a == b or (a and b and abs(20 * math.log10(a / b)) <= tolerance_db)


def _unsupported(score, end):
    notes = [n for n in score['timeline'] if n.get('op') == 'note' and n['tick'] < end]
    counts = {}
    for key in ('bend', 'tie', 'mod', 'sweep', 'portamento'):
        n = sum(bool(e.get(key)) for e in notes)
        if n:
            counts[key] = n
    adsr = sum(any(x is not None for x in e.get('adsr', [])) for e in notes)
    if adsr:
        counts['NDS_ADSR_replaced_by_DQ5_sample_and_release'] = adsr
    controls = Counter(i['op'] for c in score.get('channels', []) for i in c.get('items', [])
                       if i['op'] in ('bend', 'mod-depth', 'mod-speed', 'mod-range', 'mod-type', 'mod-delay', 'master-volume'))
    return {'note_features': counts, 'source_commands': dict(controls)}


# 드라이버 15E5 는 음이 끝나기 1틱 전에 다음 바이트를 실제 자리에서 미리 본다. 이 명령은 건너뛰고(A0~B5 는 바이트
# 범위로 따로 봄), 처음 만난 바이트가 쉼(00·50)이면 KOF 를 걸지 않는다. 부르기·돌아가기·되풀이는 따라가지 않는다.
PEEK_SKIP = {'gate_preset', 'gate', 'volume2', 'tempo', 'follow', 'follow_off'}
MAX_CALL_DEPTH = 3  # SPC 0267 의 돌아올 자리 칸(192E: 0240+X 가 6 이상이면 부르기를 무시)
LOOP_OPS = {'loop'}
BARRIER_OPS = {'jump', 'end', 'loop', 'call', 'ret'}


def _op(line):
    return line.split()[0]


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

    def heights(self, extra=None):
        calls = {sub: {x.split()[-1] for x in self.seqs[sub] if _op(x) == 'call'} for sub in self.subs}
        if extra:
            for key, value in extra.items():
                calls.setdefault(key, set()).update(value)
        memo = {}

        def height(sub, seen=()):
            if sub not in memo:
                memo[sub] = 1 + max((height(c, seen + (sub,)) for c in calls.get(sub, ())), default=0)
            return memo[sub]
        return {sub: height(sub) for sub in calls}

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
        while True:
            names = list(self.seqs)
            ids, arr, where, sizes = {}, [], [], []
            for name in names:
                for index, line in enumerate(self.seqs[name]):
                    if _kind(line) == 'label' or _op(line) in BARRIER_OPS - {'call'}:
                        arr.append(-len(arr) - 1)
                    else:
                        arr.append(ids.setdefault(line, len(ids)))
                    where.append((name, index))
                    sizes.append(_size(line))
                arr.append(-len(arr) - 1)
                where.append((name, None))
                sizes.append(0)
            prefix = [0]
            for size in sizes:
                prefix.append(prefix[-1] + size)
            best = None

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
                extra = {label: {x.split()[-1] for x in block if _op(x) == 'call'}}
                for p in chosen:
                    host = where[p][0]
                    if host in self.subs:
                        extra.setdefault(host, set()).add(label)
                if max(self.heights(extra).values()) > MAX_CALL_DEPTH:
                    return
                best = (saving, label, block, [where[p] for p in chosen], length)

            for length, positions in _repeats(arr, max_tokens):
                if len(positions) < 2:
                    continue
                name, index = where[positions[0]]
                block = self.seqs[name][index:index + length]
                kinds = [_kind(x) for x in block]
                # 음표로 끝나 뒤가 쉼이거나 쉼으로 시작해 앞이 음표인 곳은 block_ok 가 거른다. 끝을 쉼이 아닌 것 앞으로 당기고
                # 처음을 쉼 뒤로 미룬 토막도 함께 본다(같은 자리 집합에서 나오므로 따로 찾지 않아도 된다).
                ahead, lead = [None] * (length + 1), None
                for k in range(length - 1, -1, -1):
                    lead = kinds[k] if kinds[k] != 'skip' else lead
                    ahead[k] = lead
                shrink = next((k for k in range(length - 1, 1, -1) if ahead[k] not in (None, 'rest')), None)
                shift = next((k for k in range(1, length - 1) if kinds[k - 1] == 'rest' and kinds[k] != 'skip'), None)
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
            for name, index in sorted(places, key=lambda x: -x[1]):
                self.seqs[name][index:index + length] = [f'  call -> {label}']
            self.seqs[label] = list(block)
            self.subs.append(label)

    def lines(self):
        out = []
        for name in self.voices:
            out += [name + ':', *self.seqs[name]]
        for sub in self.subs:
            out += [sub + ':', *self.seqs[sub], '  ret']
        return out


def _repeats(arr, max_tokens):
    """arr 에서 두 번 이상 나오는 토막(음수는 서로 다른 벽)을 (길이, [시작 자리]) 로. 접미사 배열의 LCP 구간."""
    n = len(arr)
    order = sorted(range(n), key=lambda i: arr[i:i + max_tokens])
    lcp = [0] * n
    for k in range(1, n):
        a, b = order[k - 1], order[k]
        m = 0
        while m < max_tokens and a + m < n and b + m < n and arr[a + m] == arr[b + m] and arr[a + m] >= 0:
            m += 1
        lcp[k] = m
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


def compact(lines):
    """반복되는 명령을 되풀이(F5)와 깊이 3 안의 부르기(F8)로 묶는다. 실행되는 바이트의 순서·시각과
    15E5 미리 보기가 보는 바이트의 종류는 그대로다(execution_trace(peek=True) 로 검산)."""
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


def execution_trace(seq, ticks, peek=False, chain=None):
    """생성한 명령의 실행 시각·순서를 기록해 서브루틴·되풀이 치환을 검산한다.

    peek 이면 음표(00~9F) 사건마다 15E5 가 실제 자리에서 미리 보는 다음 바이트가 쉼인지를 셋째 값으로 붙인다.
    chain(본체 시퀀스)을 주면 F7 m t 에서 본체의 t 번째 트랙 머리로 넘어간다(본체가 이미 있다고 봄).
    """
    tracks = []
    top = seq
    for start in header(top)[1]:
        seq = top
        pc, tick, duration, stack, events = start, 0, 0, [], []
        counter = 0
        guard = 0
        while tick < ticks:
            guard += 1
            if guard > max(10000, ticks * 100):
                raise ValueError('sequence does not advance')
            op = seq[pc]
            if op == 0xF7:
                # dq5song.step 은 F7 을 1바이트(원래 드라이버에서 아무것도 안 함)로 읽지만, 고친 드라이버는 F7 m t 를 읽는다.
                # m < 80 은 나눈 곡의 본체로 넘어감, FE·FF 는 곡 붙들기(시각에 영향 없음)
                if chain is not None and seq[pc + 1] < 0x80:
                    pc, seq = header(chain)[1][seq[pc + 2]], chain
                else:
                    pc += 3
                continue
            nxt, _, target, _ = step(seq, pc)
            if op == 0xEA:
                pc = target
                continue
            if op == 0xF8:
                if len(stack) >= MAX_CALL_DEPTH:
                    raise ValueError('SPC call stack overflow')
                stack.append(nxt)
                pc = target
                continue
            if op == 0xF9:
                if not stack:
                    raise ValueError('SPC call stack underflow')
                pc = stack.pop()
                continue
            if op == 0xF5:
                # 191C: 셈이 0 이면 횟수로 두고 1 을 빼, 0 이 아니면 점프
                counter = (counter or seq[pc + 1]) - 1
                pc = target if counter else nxt
                continue
            if op in (0xDB, 0xDC, 0xF4, 0xE0):
                raise ValueError(f'unsupported flow command {op:02X}')
            if peek and op < 0xA0:
                events.append((tick, bytes(seq[pc:nxt]), _peeks_rest(seq, nxt)))
            else:
                events.append((tick, bytes(seq[pc:nxt])))
            if op == 0xFF:
                break
            if op < 0xA0:
                if op >= 0x50:
                    duration = seq[pc + 1] or 256
                if not duration:
                    raise ValueError('uninitialized note duration')
                tick += duration
            pc = nxt
        tracks.append(events)
    return tracks


def _peeks_rest(seq, pc):
    """15E5~1627: A0~B5·F2·F3 는 1바이트, EC·F6·EB 는 2바이트 건너뛰고 처음 만난 바이트가 00·50 인가."""
    while pc < len(seq):
        b = seq[pc]
        if 0xA0 <= b < 0xB6 or b in (0xF2, 0xF3):
            pc += 1
        elif b in (0xEC, 0xF6, 0xEB):
            pc += 2
        else:
            return b in (0x00, 0x50)
    return False


def seconds_to_tick(tempos, seconds):
    """곡 시작에서 seconds 초가 지난 시각을 틱으로(올림). tempos 는 {틱: DQ5 템포}."""
    points = sorted(tempos.items())
    elapsed = 0.0
    for i, (tick, value) in enumerate(points):
        rate = value * DQ5_TICKS_PER_SECOND_PER_TEMPO
        span = (points[i + 1][0] - tick) / rate if i + 1 < len(points) else math.inf
        if elapsed + span >= seconds:
            return tick + math.ceil((seconds - elapsed) * rate)
        elapsed += span
    raise AssertionError('unreachable')


def convert(score, *, voices=7, program_map=None, tempo_tolerance=0.012, level_tolerance_db=1.0,
            tail_ticks=12, release_rate=0x1C, sample_order=None, arrivals=None, lanes_for=None,
            split_tick=None, chain_song=None, hold=None):
    """악보 → 글·바이너리·곡 묶음의 DQ5 샘플 번호·손실 보고서.

    시퀀스만 만들며 ROM/SPC 공간 검사는 삽입기가 맡는다. 8번째 목소리를 BGM에서 쓰지 않지만
    실제 SFX 우선권은 드라이버 검증이 필요하다.

    sample_order 는 곡 묶음 레코드의 샘플 순서(악기 번호)다. 주지 않으면 번호 순.
    arrivals 는 곡이 시작한 뒤에 도착하는 샘플의 {샘플: 도착 어림 초}다. 드라이버는 없는 샘플의
    instrument(F0, SPC 182E)에서 그 트랙의 KON 을 막고(02CB+X bit7), 샘플이 있을 때의 instrument 만
    풀어 준다. 그래서 그 샘플의 음마다 도착 어림 시각까지 instrument 를 다시 쓴다. 도착 전 음은 울리지 않는다.
    lanes_for 는 allocate 의 트랙별 목소리 고정이다.

    split_tick 만 주면 그 지점에서 자르기만 한다(나눈 곡을 견줄 기준). split_tick·chain_song 을 주면 곡을 앞부분([0, split_tick))과 본체로 나눈다. 앞부분 트랙은 끝에서 드라이버 명령
    F7 chain_song 트랙(dq4soundpatch.chain_code)으로 본체 시퀀스의 같은 트랙 머리로 넘어가고, 본체가 아직 SPC 에
    없으면 1틱 쉬고 다시 시도한다. 본체 트랙 머리는 split_tick 지점을 가리키며(루프 시작이 그 앞이면 루프 부분도
    둠), 앞부분이 실행한 악기·세기·팬 상태를 이어 쓴다. 이어지는 음은 비율 00 붙임이라 다시 치지 않는다.

    hold 는 (샘플, 256바이트 단위 문턱)으로, 트랙 0 머리에 곡 붙들기(F7 FE 샘플 / F7 FF 문턱, dq4soundpatch.hold_check_code)
    를 둔다. 그 샘플을 받는 동안 곡을 틀고 문턱만큼 오면 곡이 나아간다. 붙들기는 그 틱의 나머지 트랙을 막지 못하므로 모든
    트랙을 1틱 쉼으로 시작한다(그 틱에 instrument 가 오면 아직 없는 샘플로 보아 트랙이 조용해진다).
    """
    if not 1 <= voices <= 7:
        raise ValueError('BGM voices must be between 1 and 7')
    if score.get('ticks_per_quarter', 48) != 48:
        raise ValueError('expected 48 ticks per quarter')
    loop_start, end = score_bounds(score)
    instruments = score.get('instruments') or {}
    # NDS 뱅크에 정의가 없는 프로그램(None)의 음은 NDS 에서도 소리가 나지 않는다.
    undefined = [e for e in score['timeline'] if e.get('op') == 'note' and instruments
                 and instruments.get(str(e['program'])) is None]
    if undefined:
        skip = {id(e) for e in undefined}
        score = score | {'timeline': [e for e in score['timeline'] if id(e) not in skip]}
    mapping = PROGRAM_MAP | (program_map or {})
    lanes, report = allocate(score, voices, end, tail_ticks, lanes_for)
    used = {n['program'] for lane in lanes for n in lane}
    missing = sorted(used - mapping.keys())
    if missing:
        raise ValueError(f'programs require explicit mapping: {missing}')
    samples = sorted({resolve_sample(mapping, n['program'], n['note']) for lane in lanes for n in lane})
    if sample_order is not None:
        if sorted(sample_order) != samples:
            raise ValueError('sample_order must list exactly the samples the song uses')
        samples = list(sample_order)
    usage = {}
    for lane in lanes:
        for n in lane:
            first, count = usage.get(resolve_sample(mapping, n['program'], n['note']), (math.inf, 0))
            usage[resolve_sample(mapping, n['program'], n['note'])] = (min(first, n['tick']), count + 1)
    if any(not isinstance(n, int) or not 0 <= n < 0xC8 for n in samples):
        raise ValueError('sample ID outside DQ5 table')
    ccs, restored = controllers(score, end)
    cc_times = {ch: [e[0] for e in events] for ch, events in ccs.items()}
    initial_tempo = score['tempo']
    startup_delay = 0.0
    if initial_tempo > 255:
        changes = [(t, v) for t, v in score.get('tempo_changes', []) if t <= 2 and v <= 255]
        if not changes:
            raise ValueError('high initial tempo without a bounded startup change')
        startup_ticks = min(t for t, _ in changes)
        startup_delay = startup_ticks * (1 / (255 * 0.8) - 1 / (initial_tempo * NDS_TICKS_PER_SECOND_PER_TEMPO))
        initial_tempo = 255
    dq5_tempo(initial_tempo)
    raw = {0: initial_tempo}
    for t, v in score.get('tempo_changes', []):
        if 0 < t < end:
            dq5_tempo(v)
            raw[t] = v
    exact = sorted((t, v * NDS_TICKS_PER_SECOND_PER_TEMPO / DQ5_TICKS_PER_SECOND_PER_TEMPO) for t, v in raw.items())
    tempos, tempo_error = {}, 0.0
    # 루프 시작에서 템포를 다시 정해야 반복할 때 같은 시각이 나온다.
    for lo, hi in ([(0, loop_start), (loop_start, end)] if loop_start else [(0, end)]):
        part = [(t - lo, v) for t, v in exact if lo <= t < hi]
        if not part or part[0][0]:
            part.insert(0, (0, [v for t, v in exact if t <= lo][-1]))
        simplified, error = simplify_tempo(part, hi - lo, tempo_tolerance)
        tempos.update({t + lo: v for t, v in simplified.items()})
        tempo_error = max(tempo_error, error)
    lines = [f'tempo {tempos[0]:02X}'] + [f'track Lvoice{i}' for i in range(voices)]
    arrival_ticks = {sample: seconds_to_tick(tempos, seconds) for sample, seconds in (arrivals or {}).items()}
    if not arrival_ticks.keys() <= set(samples):
        raise ValueError('arrivals name samples the song does not use')
    late_notes = Counter()
    reissued = 0
    folded = []
    cc_emitted = 0
    level_skips, level_error = 0, 0.0
    for lane_id, lane in enumerate(lanes):
        lines.append(f'Lvoice{lane_id}:')
        if hold is not None:
            if lane_id == 0:
                lines += [f'  db F7 FE {hold[0]:02X}', f'  db F7 FF {hold[1]:02X}']
            lines.append('  rest len 01')
        lines += ['  volume 30', f'  release {release_rate:02X}', '  echo_on']
        cuts = {0, end}
        if loop_start is not None:
            cuts.add(loop_start)
        if split_tick is not None:
            cuts.add(split_tick)
        if lane_id == 0:
            cuts.update(tempos)
        for note in lane:
            cuts.update((note['tick'], note['end']))
            times = cc_times.get(note['ch'], [])
            events = ccs.get(note['ch'], [])
            values = {7: note.get('volume', 127), 10: note.get('pan', 64), 11: note.get('expression', 127)}
            previous = (_level(note, values[7], values[11], score.get('volume', 127)), _pan(values[10]))
            for t, cc, value in events[bisect_right(times, note['tick']):bisect_right(times, note['end'] - 1)]:
                values[cc] = value
                changed = (_level(note, values[7], values[11], score.get('volume', 127)), _pan(values[10]))
                if changed[1] != previous[1] or not _near(changed[0], previous[0], level_tolerance_db):
                    cuts.add(t)
                    previous = changed
        boundaries = sorted(cuts)
        current = 0
        cache = {}
        last_note = None
        note_cc = {}
        for i, tick in enumerate(boundaries[:-1]):
            stop = boundaries[i + 1]
            while current < len(lane) and lane[current]['end'] <= tick:
                current += 1
            note = lane[current] if current < len(lane) and lane[current]['tick'] <= tick else None
            if tick == loop_start:
                lines.append(f'Lloop{lane_id}:')
                cache.clear()
                last_note = None
            if tick == split_tick:
                lines.append(f'Lsplit{lane_id}:')
                # 앞부분의 다시 시도 쉼(1틱)이 길이를 바꿀 수 있어 본체 첫 음은 길이를 다시 쓴다
                cache.pop('duration', None)
            if lane_id == 0 and tick in tempos:
                lines.append(f'  tempo {tempos[tick]:02X}')
            def setting(name, value):
                nonlocal cc_emitted
                if cache.get(name) != value:
                    lines.append(f'  {name} {value:02X}')
                    cache[name] = value
                    cc_emitted += name in ('volume2', 'pan')
            if note:
                fresh = note is not last_note
                if fresh:
                    note_cc = {7: note.get('volume', 127), 10: note.get('pan', 64), 11: note.get('expression', 127)}
                events = ccs.get(note['ch'], [])
                times = cc_times.get(note['ch'], [])
                for t, cc, value in events[bisect_right(times, note['tick']):bisect_right(times, tick)]:
                    note_cc[cc] = value
                sample = resolve_sample(mapping, note['program'], note['note'])
                index = samples.index(sample)
                arrival = arrival_ticks.get(sample)
                if fresh and arrival is not None and note['tick'] < arrival:
                    late_notes[sample] += 1
                # 마지막 instrument 가 샘플 도착 전이었으면 막힌 채일 수 있으니 다시 쓴다.
                if fresh and arrival is not None and cache.get('instrument_at', -1) < arrival:
                    if cache.get('instrument') == index:
                        reissued += 1
                    cache.pop('instrument', None)
                if cache.get('instrument') != index:
                    setting('instrument', index)
                    cache['instrument_at'] = tick
                setting('release', release_rate)
                level = _level(note, note_cc[7], note_cc[11], score.get('volume', 127))
                held = cache.get('volume2')
                # 사람이 거의 못 듣는 세기 차이까지 옮기면 음마다 명령이 붙어 SPC 메모리를 넘는다.
                if held and level and abs(20 * math.log10(level / held)) <= level_tolerance_db:
                    level_skips += 1
                    level_error = max(level_error, abs(20 * math.log10(level / held)))
                else:
                    setting('volume2', level)
                setting('pan', _pan(note_cc[10]))
                midi = note['note']
                while midi < 24:
                    midi += 12
                while midi > 101:
                    midi -= 12
                if fresh and midi != note['note']:
                    folded.append({'source': note['uid'], 'from': note['note'], 'to': midi})
                word = f'note {midi - 23:02X}' if fresh else 'tie'
            else:
                word = 'rest'
            remaining = stop - tick
            while remaining:
                length = min(remaining, 240)
                final = note is None or tick + length in (note['end'], loop_start)
                if note:
                    setting('gate_preset', 0xFE if final else 0)
                if cache.get('duration') != length:
                    lines.append(f'  {word} len {length:02X}')
                    cache['duration'] = length
                else:
                    lines.append(f'  {word}')
                remaining -= length
                tick += length
                if note:
                    word = 'tie'
            last_note = note
        if loop_start is None:
            lines += ['  rest len 30', '  end']
        else:
            lines.append(f'  jump -> Lloop{lane_id}')
    def pack(part):
        raw = assemble(part)
        part = compact(part)
        out = assemble(part)
        if execution_trace(raw, end * 2 + 49, peek=True) != execution_trace(out, end * 2 + 49, peek=True):
            raise ValueError('sequence compression changed timed commands or KOF look-ahead')
        if len(out) >= 65536:
            raise ValueError(f'sequence exceeds 16-bit offsets: {len(out)}')
        for start in header(out)[1]:
            _, problems = walk(out, start)
            if problems:
                raise ValueError(f'invalid sequence: {problems}')
        if assemble(listing(out)) != out:
            raise ValueError('sequence listing round trip failed')
        return raw, part, out

    chain = None
    if split_tick is not None and not 0 < split_tick < end:
        raise ValueError('split_tick must be inside the song')
    if split_tick is not None and chain_song is not None:
        if not 0 <= chain_song < 0x64:
            raise ValueError('chain_song must be a sequence number')
        intro_lines, main_lines = list(lines[:1 + voices]), list(lines[:1 + voices])
        bodies, name = {}, None
        for line in lines[1 + voices:]:
            if line.startswith('Lvoice') and line.endswith(':'):
                name = int(line[6:-1])
                bodies[name] = []
            else:
                bodies[name].append(line)
        for lane_id in range(voices):
            body = bodies[lane_id]
            cut = body.index(f'Lsplit{lane_id}:')
            intro_lines += [f'Lvoice{lane_id}:', *body[:cut], f'Lchain{lane_id}:',
                            f'  db F7 {chain_song:02X} {lane_id:02X}', '  rest len 01', f'  jump -> Lchain{lane_id}']
            loop = f'Lloop{lane_id}:'
            start = body.index(loop) if loop in body and body.index(loop) < cut else cut
            main_lines += [f'Lvoice{lane_id}:', f'  jump -> Lsplit{lane_id}', *body[start:]]
        _, intro_lines, seq = pack(intro_lines)
        uncompressed, main_lines, chain = pack(main_lines)
        lines = intro_lines + ['# chain'] + main_lines
    else:
        uncompressed, lines, seq = pack(lines)
    boundary_clips = [n['uid'] for lane in lanes for n in lane if n['tick'] + n['gate'] > end]
    report |= {
        'id': score.get('id'), 'title': score.get('title', score.get('name')),
        'status': 'arrangement-draft', 'source': 'NDS DQ4 score', 'voices': voices,
        'undefined_program_notes': len(undefined),
        'sequence_bytes': len(seq), 'uncompressed_bytes': len(uncompressed), 'sequence_sha256': hashlib.sha256(seq).hexdigest(),
        'hold': None if hold is None else {'sample': f'{hold[0]:02X}', 'bytes': hold[1] * 256},
        'split_tick': split_tick, 'chain_song': chain_song, 'chain_bytes': None if chain is None else len(chain),
        'samples': samples, 'send_first': len(samples), 'end_tick': end,
        'sample_first_tick': {f'{k:02X}': v[0] for k, v in sorted(usage.items())},
        'sample_notes': {f'{k:02X}': v[1] for k, v in sorted(usage.items())},
        'arrival_ticks': {f'{k:02X}': v for k, v in sorted(arrival_ticks.items())},
        'late_notes': {f'{k:02X}': late_notes[k] for k in sorted(arrival_ticks)},
        'reissued_instruments': reissued,
        'loop_start': loop_start, 'loop_len': score.get('loop_len'),
        'tempo_changes': [[t, v] for t, v in sorted(tempos.items())],
        'source_tempo_changes': len(raw) - 1, 'tempo_max_error_seconds': round(tempo_error, 4),
        'level_changes_merged': level_skips, 'level_max_error_db': round(level_error, 2),
        'initial_tempo_delay_seconds': startup_delay,
        'program_map': {str(p): mapping[p] for p in sorted(used)},
        'instrument_mapping_status': 'provisional; requires comparative listening',
        'controllers_restored': restored, 'controller_commands': cc_emitted,
        'octave_folded_notes': folded, 'loop_boundary_clipped_notes': boundary_clips,
        'loop_start_retriggered_notes': [n['uid'] for lane in lanes for n in lane if loop_start is not None and n['tick'] < loop_start < n['end']],
        'unsupported': _unsupported(score, end),
        'limitations': [
            'Timbres use the supplied program map (DQ5 or converted NDS samples); NDS envelopes are approximated.',
            'Rubato tempo and per-note velocity are merged within the reported time and level errors.',
            'Pitch bend, modulation, portamento and NDS release tails require separate adaptation.',
            'Final note segments use DQ5 FE gate (one tick early release).',
            'Notes crossing the loop boundary are clipped; seamless tails require listening.',
            'SPC memory, sample transfer and voice arbitration require ROM runtime verification.',
        ],
    }
    return Conversion('\n'.join(lines) + '\n', seq, samples, report, chain)


def export(assets, out, *, voices=7, program_map=None):
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(assets.glob('*.json')):
        score = json.loads(path.read_text())
        if not isinstance(score, dict) or 'timeline' not in score:
            continue
        ident = str(score['id'])
        if not ident.isalnum():
            raise ValueError(f'invalid score ID: {ident}')
        try:
            result = convert(score, voices=voices, program_map=program_map)
        except ValueError as error:
            rows.append({'id': ident, 'title': score.get('title'), 'status': 'unsupported', 'reason': str(error)})
            continue
        (out / f'{ident}.seq').write_bytes(result.sequence)
        (out / f'{ident}.txt').write_text(result.text)
        (out / f'{ident}.json').write_text(json.dumps(result.report, ensure_ascii=False, indent=2) + '\n')
        rows.append(result.report)
    index = {'source': 'NDS DQ4', 'scores': len(rows), 'converted': sum(r['status'] != 'unsupported' for r in rows), 'items': rows}
    (out / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n')
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    batch = sub.add_parser('export')
    batch.add_argument('--assets', type=Path, required=True, help='NDS sound/songs directory')
    batch.add_argument('--out', type=Path, required=True)
    batch.add_argument('--voices', type=int, default=7)
    batch.add_argument('--program-map', type=Path, help='JSON NDS program -> DQ5 sample integer')
    args = parser.parse_args()
    mapping = {int(k): v for k, v in json.loads(args.program_map.read_text()).items()} if args.program_map else None
    result = export(args.assets, args.out, voices=args.voices, program_map=mapping)
    print(json.dumps({'scores': result['scores'], 'converted': result['converted'], 'unsupported': result['scores'] - result['converted']}))


if __name__ == '__main__':
    main()
