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


def allocate(score, voices, end, tail_ticks=0):
    """원래 우선순위와 선율·저음을 보존하며, 넘친 음은 늦게 재발음하지 않고 버린다."""
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
    for channel in {n['ch'] for n in candidates}:
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

    for tick, incoming in sorted(starts.items()):
        active = {lane: n for lane, n in active.items() if n['end'] > tick}
        selected = sorted(list(active.values()) + incoming, key=priority, reverse=True)[:voices]
        keep = {n['uid'] for n in selected}
        for lane, note in list(active.items()):
            if note['uid'] not in keep:
                old_end = note['end']
                note['end'] = tick
                truncated.append({'source': note['uid'], 'tick': tick, 'lost_ticks': old_end - tick})
                del active[lane]
        for note in sorted(incoming, key=priority, reverse=True):
            if note['uid'] not in keep:
                dropped.append(note['uid'])
                continue
            free = [lane for lane in range(voices) if lane not in active]

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


def compact(lines):
    """반복되는 명령을 깊이 1인 서브루틴으로 묶는다. 명령 경계·순서는 그대로다."""
    head = [s for s in lines if s and not s[0].isspace() and not s.endswith(':')]
    body = [s for s in lines if s not in head]
    subs = []
    serial = 0
    for width in (64, 32, 16, 8, 6, 4):
        groups = defaultdict(list)
        valid = 0
        for i, line in enumerate(body):
            barrier = line.endswith(':') or line.split()[0] in ('call', 'ret', 'jump', 'end')
            valid = 0 if barrier else valid + 1
            if valid >= width:
                start = i - width + 1
                groups[tuple(body[start:i + 1])].append(start)
        choices = []
        for block, positions in groups.items():
            if len(positions) < 2:
                continue
            size = sum(len(_encode_line(line.split(), 0, None)) for line in block)
            saving = (size - 3) * len(positions) - size - 1
            if saving > 0:
                choices.append((saving, block, positions, size))
        reserved = set()
        replacements = {}
        for _, block, positions, size in sorted(choices, reverse=True):
            selected = []
            for start in positions:
                if not any(i in reserved for i in range(start, start + width)) and (not selected or start >= selected[-1] + width):
                    selected.append(start)
            if (size - 3) * len(selected) - size - 1 <= 0:
                continue
            label = f'Lphrase{serial}'
            serial += 1
            subs += [label + ':', *block, '  ret']
            for start in selected:
                replacements[start] = f'  call -> {label}'
                reserved.update(range(start, start + width))
        new = []
        i = 0
        while i < len(body):
            if i in replacements:
                new.append(replacements[i])
                i += width
            else:
                new.append(body[i])
                i += 1
        body = new
    return head + body + subs


def execution_trace(seq, ticks):
    """생성한 명령의 실행 시각·순서를 기록해 서브루틴 치환을 검산한다."""
    tracks = []
    for start in header(seq)[1]:
        pc, tick, duration, stack, events = start, 0, 0, [], []
        guard = 0
        while tick < ticks:
            guard += 1
            if guard > max(10000, ticks * 100):
                raise ValueError('sequence does not advance')
            op = seq[pc]
            nxt, _, target, _ = step(seq, pc)
            if op == 0xEA:
                pc = target
                continue
            if op == 0xF8:
                if len(stack) >= 3:
                    raise ValueError('SPC call stack overflow')
                stack.append(nxt)
                pc = target
                continue
            if op == 0xF9:
                if not stack:
                    raise ValueError('SPC call stack underflow')
                pc = stack.pop()
                continue
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


def convert(score, *, voices=7, program_map=None, tempo_tolerance=0.012, level_tolerance_db=1.0,
            tail_ticks=12, release_rate=0x1C):
    """악보 → 글·바이너리·곡 묶음의 DQ5 샘플 번호·손실 보고서.

    시퀀스만 만들며 ROM/SPC 공간 검사는 삽입기가 맡는다. 모든 샘플을 첫 음 전에
    전송해야 한다. 8번째 목소리를 BGM에서 쓰지 않지만 실제 SFX 우선권은 드라이버 검증이 필요하다.
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
    lanes, report = allocate(score, voices, end, tail_ticks)
    used = {n['program'] for lane in lanes for n in lane}
    missing = sorted(used - mapping.keys())
    if missing:
        raise ValueError(f'programs require explicit mapping: {missing}')
    samples = sorted({resolve_sample(mapping, n['program'], n['note']) for lane in lanes for n in lane})
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
    folded = []
    cc_emitted = 0
    level_skips, level_error = 0, 0.0
    for lane_id, lane in enumerate(lanes):
        lines += [f'Lvoice{lane_id}:', '  volume 30', f'  release {release_rate:02X}', '  echo_on']
        cuts = {0, end}
        if loop_start is not None:
            cuts.add(loop_start)
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
                setting('instrument', samples.index(resolve_sample(mapping, note['program'], note['note'])))
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
    uncompressed = assemble(lines)
    lines = compact(lines)
    seq = assemble(lines)
    if execution_trace(uncompressed, end * 2 + 49) != execution_trace(seq, end * 2 + 49):
        raise ValueError('sequence compression changed timed commands')
    if len(seq) >= 65536:
        raise ValueError(f'sequence exceeds 16-bit offsets: {len(seq)}')
    for start in header(seq)[1]:
        _, problems = walk(seq, start)
        if problems:
            raise ValueError(f'invalid sequence: {problems}')
    if assemble(listing(seq)) != seq:
        raise ValueError('sequence listing round trip failed')
    boundary_clips = [n['uid'] for lane in lanes for n in lane if n['tick'] + n['gate'] > end]
    report |= {
        'id': score.get('id'), 'title': score.get('title', score.get('name')),
        'status': 'arrangement-draft', 'source': 'NDS DQ4 score', 'voices': voices,
        'undefined_program_notes': len(undefined),
        'sequence_bytes': len(seq), 'uncompressed_bytes': len(uncompressed), 'sequence_sha256': hashlib.sha256(seq).hexdigest(),
        'samples': samples, 'send_first': len(samples), 'end_tick': end,
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
    return Conversion('\n'.join(lines) + '\n', seq, samples, report)


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
