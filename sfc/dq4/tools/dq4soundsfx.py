"""NDS DQ4 효과음을 DQ5 효과음 시퀀스의 갈래로 바꿔 끼운다.

DQ5 효과음 시퀀스(32~46)는 트랙 첫머리의 if_flag(E0)로 갈래(명령 0C n X 의 X)를 고른다. 바꿀 갈래마다 NDS 효과음을
dq4soundport.convert 로 바꾸고, 원래 시퀀스를 글(dq5song.listing)로 풀어 트랙 첫머리에 그 갈래로 뛰는 if_flag 를 더한 뒤
다시 싼다(점프는 상대 주소라 글로 다루면 원래 갈래가 그대로 남는다).

효과음 샘플을 늘 두면 SPC 샘플 칸(20개)을 이미 다 쓰는 곡이 있어, 갈래를 바꿔 끼우는 효과음(build_effects)은 새 샘플을 받지 않는다.
샘플이 드는 효과음은 build_spare 가 DQ4 가 부르지 않는 빈 효과음 시퀀스에 모으고, 부르는 쪽이 그 샘플을 자리가 남는 곡에만 붙인다.
NDS PSG 잡음 악기만 쓰는 효과음은 DSP 잡음(E3)으로 옮기므로 샘플이 들지 않는다. 짧은 음정 파형만 쓰는 효과음은
waves({NDS 샘플 파일: 늘 두는 샘플 번호})로 늘 두는 DQ5 효과음 파형 자리(20~22)에 넣은 한 주기 파형으로 울린다.
"""
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dq5' / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4soundbank as bank  # noqa: E402
import dq4soundport as port  # noqa: E402
from dq5song import assemble, listing  # noqa: E402

NOISE_TYPE = '잡음'
MAX_VOICES = 2  # 효과음 목소리(6·7). 곡은 목소리 0~6 을 쓰므로 둘째 목소리는 곡의 6 을 잠시 빌린다


def sfx_path(assets, ident):
    found = sorted((Path(assets) / 'nds/dq4/sound/sfx').glob(f'{ident.upper()}-*.json'))
    if len(found) != 1:
        raise ValueError(f'NDS sound effect {ident}: expected one score, found {len(found)}')
    return found[0]


def noise_program_map(score, waves=None):
    """잡음 악기와 waves 에 든 파형만 쓰는 효과음의 program_map. 그 밖의 샘플이 드는 악기가 있으면 None."""
    used = {e['program'] for e in score['timeline'] if e.get('op') == 'note'}
    instruments = score.get('instruments') or {}
    waves = waves or {}
    out = {}
    for p in used:
        instrument = instruments.get(str(p)) or {}
        if instrument.get('type') == NOISE_TYPE:
            out[p] = port.NOISE
            continue
        regions = instrument.get('regions') or []
        if not regions or any(r.get('sample') not in waves for r in regions):
            return None
        out[p] = [{'lo': r['lo'], 'hi': r['hi'], 'sample': waves[r['sample']]} for r in regions]
    return out


def wave_region(assets, sample):
    """그 NDS 샘플을 쓰는 첫 효과음 영역(기준음·엔벨로프)."""
    for path in sorted((Path(assets) / 'nds/dq4/sound/sfx').glob('*.json')):
        if path.name == 'index.json':
            continue
        for instrument in (json.loads(path.read_text()).get('instruments') or {}).values():
            for region in (instrument or {}).get('regions') or []:
                if region.get('sample') == sample:
                    return region
    raise ValueError(f'no NDS sound effect uses {sample}')


def wave_resources(assets, spec):
    """spec = {늘 두는 샘플 번호: [NDS 샘플 파일, ...]}. 첫 샘플을 한 주기 파형으로 만들고 나머지는 그 파형으로 울린다.
    ({번호: 자원}, waves, 보고서)."""
    resources, waves, report = {}, {}, {}
    for ident, names in sorted(spec.items()):
        resource, detail = bank.wave_resource(Path(assets) / 'nds/dq4/sound/samples' / names[0], wave_region(assets, names[0]))
        resources[ident] = resource
        waves |= {name: ident for name in names}
        report[f'{ident:02X}'] = detail | {'plays': list(names)}
    return resources, waves, report


def convert_branch(score, program_map, record=(), voice_volume=0x30, all_rests=False):
    """(트랙 입구 이름표 목록, 본문 글 줄, 빠진 음 수, 레코드에 더할 샘플). 목소리 하나로 빠지는 음이 있으면 둘로 바꾼다.
    record 는 그 효과음 시퀀스의 곡 묶음 레코드 샘플 순서로, 악기 번호를 그 순서로 바꾸고 없는 샘플은 끝에 더한다."""
    best = None
    for voices in range(1, MAX_VOICES + 1):
        result = port.convert(score, voices=voices, program_map=program_map, voice_volume=voice_volume)
        dropped = result.report['dropped_notes']
        if best is None or dropped < best[1]:
            best = (result, dropped)
        if not dropped:
            break
    result, dropped = best
    order = list(record) + [x for x in result.samples if x not in record]
    lines = listing(result.sequence)
    # 변환은 쓰는 샘플을 번호 순으로 악기 번호를 매긴다. 효과음은 원래 레코드 순서를 따른다
    lines = [f'  instrument {order.index(result.samples[int(ln.split()[1], 16)]):02X}'
             if ln.split()[:1] == ['instrument'] else ln for ln in lines]
    starts = [w.split()[1] for w in lines if w.startswith('track ')]
    # 곡 변환은 트랙끼리 부르는 토막(call)을 함께 쓸 수 있어, 본문은 통째로 옮기고 트랙 입구만 가리킨다
    body = [ln for ln in lines if ln and (ln[0].isspace() or ln.endswith(':'))]
    # 끝의 쉼은 효과음에선 트랙만 더 오래 살려 SPC 처리를 늘리고(맵을 불러오는 동안 받기가 느려져 곡이 늦게 나옴),
    # 늘 두는 시퀀스 바이트도 늘린다. 마지막 음 뒤 바로 끝낸다.
    # all_rests 면 end 앞에 이어진 쉼을 모두 뺀다(뺀 음이 남긴 빈 시간). 같은 효과음을 울리는 중에 다시 부르면 소리가 나지
    # 않아(くさりがま 의 두 번째 부르기가 조용했음) 남은 쉼이 다음 공격 소리를 막는다. 늘 두는 효과음(build_effects)은 바꾸면
    # 곡 예산이 달라져 승인한 곡이 바뀌므로 하나만 뺀다.
    while True:
        cut = [i for i, ln in enumerate(body)
               if ln.split()[:1] == ['rest'] and i + 1 < len(body) and body[i + 1].split() == ['end']]
        if not cut:
            break
        body = [ln for i, ln in enumerate(body) if i not in cut]
        if not all_rests:
            break

    return starts, body, dropped, [x for x in order if x not in record]


def _rename(lines, prefix):
    """이름표를 prefix 붙인 이름으로(다른 갈래·원래 시퀀스와 겹치지 않게)."""
    def fix(word):
        return prefix + word[1:] if word.startswith('L') else word
    out = []
    for line in lines:
        if line.endswith(':') and not line[0].isspace():
            out.append(fix(line[:-1]) + ':')
        else:
            out.append('  ' + ' '.join(fix(w) for w in line.split()))
    return out


def _track_branches(body, start):
    """원래 트랙 첫머리의 if_flag 들이 고르는 갈래(넘어가면 갈래 00)."""
    at = body.index(f'{start}:') + 1
    found = {0}
    for line in body[at:]:
        words = line.split()
        if line.endswith(':') or not words:
            continue
        if words[0] == 'gate_preset':
            continue
        if words[0] != 'if_flag':
            break
        found.add(int(words[1], 16))
    return found


def splice(sequence, branches):
    """branches = {갈래: (트랙 입구 이름표, 본문 글 줄)}. 원래 시퀀스의 그 갈래를 새 트랙들로 바꾼 시퀀스 바이트.

    트랙마다 새 입구에서 바꾼 갈래의 if_flag 를 먼저 보고, 나머지는 원래 트랙 첫머리로 뛴다. 새 갈래에 없는 트랙은
    그 갈래에서 바로 끝내(원래 갈래의 둘째 목소리가 섞이지 않게). 효과음 시퀀스는 늘 SPC 에 두어 곡 예산을 줄이므로,
    같은 본문은 한 번만 두고, 바꾼 갈래의 원래 본문과 갈래를 모두 바꾼 트랙의 원래 첫머리는 닿지 않게 해 뺀다."""
    lines = listing(sequence)
    head = [ln for ln in lines if ln and not ln[0].isspace() and not ln.endswith(':')]
    body = [ln for ln in lines if ln and (ln[0].isspace() or ln.endswith(':'))]
    tempo, starts = head[0], [w.split()[1] for w in head[1:]]
    body = [f'  if_flag {ln.split()[1]} -> LsfxEnd' if ln.split()[:1] == ['if_flag'] and int(ln.split()[1], 16) in branches
            else ln for ln in body]
    owner = {}
    for branch, (_, text) in sorted(branches.items()):
        owner.setdefault(tuple(text), branch)
    count = max([len(starts)] + [len(entries) for entries, _ in branches.values()])
    new_head, new_body = [tempo], body + ['LsfxEnd:', '  end']
    for i in range(count):
        entry = f'LsfxTrack{i}'
        new_head.append(f'track {entry}')
        new_body.append(f'{entry}:')
        for branch, (entries, text) in sorted(branches.items()):
            shared = owner[tuple(text)]
            target = f'Lsfx{shared:02X}_' + entries[i][1:] if i < len(entries) else 'LsfxEnd'
            new_body.append(f'  if_flag {branch:02X} -> {target}')
        if i < len(starts) and not _track_branches(body, starts[i]) <= set(branches):
            new_body.append(f'  jump -> {starts[i]}')
        else:
            new_body.append('  end')
    for text, branch in owner.items():
        new_body += _rename(list(text), f'Lsfx{branch:02X}_')
    # 닿지 않는 바이트(db)를 빼고 다시 싼다
    pruned = [ln for ln in listing(assemble(new_head + new_body)) if not ln.split()[:1] == ['db']]
    return assemble(pruned)


def build_effects(data, assets, spec, sequence_bytes, records=None, waves=None, volumes=None):
    """spec = {(효과음, 갈래): NDS 번호}. records 는 {효과음: 곡 묶음 레코드 샘플}, waves 는 noise_program_map 의 것,
    volumes 는 {(효과음, 갈래): 목소리 음량 ED}(DQ5 효과음과 세기를 맞춤).
    ({효과음: 새 시퀀스 바이트}, {효과음: 레코드에 더할 샘플}, 보고서)."""
    by_seq, extras, report = {}, {}, {}
    for (seq, branch), ident in sorted(spec.items()):
        score = json.loads(sfx_path(assets, ident).read_text())
        program_map = noise_program_map(score, waves)
        if program_map is None:
            raise ValueError(f'{seq:02X}-{branch:02X} <- {ident}: uses samples (SPC sample slots are full); '
                             'only noise and wave effects are supported')
        record = list((records or {}).get(seq, ())) + extras.get(seq, [])
        entries, text, dropped, more = convert_branch(score, program_map, record, (volumes or {}).get((seq, branch), 0x30))
        extras.setdefault(seq, []).extend(more)
        by_seq.setdefault(seq, {})[branch] = (entries, text)
        report[f'{seq:02X}-{branch:02X}'] = {'nds': ident.upper(), 'title': score.get('title'), 'tracks': len(entries),
                                              'dropped_notes': dropped}
    sequences = {seq: splice(sequence_bytes(data, seq), branches) for seq, branches in by_seq.items()}
    return sequences, {seq: more for seq, more in extras.items() if more}, report


def bend_slides(score, dump):
    """NDS 효과음 시퀀스 글(ndssound 의 sfx/*.txt)에서 음마다 울리는 동안 바뀌는 벤드를 읽어 'slide'(반음, 틱)를 붙인 악보.

    악보에는 음이 시작할 때의 벤드만 남는데, 무기 소리는 틱마다 벤드를 바꿔 음을 몇 옥타브씩 쓸어 올리거나 내린다(양날 검은
    -2 → 80, 범위 60 이면 약 38반음). 음이 울리는 동안(다음 음 또는 길이 끝까지) 마지막 벤드와 처음 벤드의 차를 반음으로
    반올림해 한 번의 고른 미끄럼으로 옮긴다. note-wait 0 인 트랙만 읽는다(효과음은 모두 그렇다)."""
    events, tick, track, wait, scale = {}, 0, None, True, 2
    for line in dump.splitlines():
        head = re.match(r'\[(track\d+)\]', line)
        if head:
            track, tick, wait, scale = head.group(1), 0, True, 2
            continue
        m = re.match(r'\s+[0-9A-F]{4}\s+(?:[0-9A-F]{2} )+\s*(\S+)\s*(.*)', line)
        if not m or track is None:
            continue
        op, rest = m.groups()
        if op == 'note-wait':
            wait = rest.split()[0] != '0'
        elif op == 'bend-range':
            scale = int(rest.split()[0])
        elif op == 'bend':
            events.setdefault(track, []).append((tick, int(rest.split()[0]), scale))
        elif op == 'rest':
            tick += int(rest.split('=')[1])
        elif op == 'note' and wait:
            tick += int(rest.split('gate=')[1])
        elif op in ('jump', 'call', 'end'):
            track = None
    notes = [e for e in score['timeline'] if e.get('op') == 'note']
    timeline = []
    for e in score['timeline']:
        if e.get('op') == 'note' and events.get(e['ch']):
            after = [n['tick'] for n in notes if n['ch'] == e['ch'] and n['tick'] > e['tick']]
            stop = min([e['tick'] + max(e.get('gate', 0), 1)] + after)
            inside = [(t, b, r) for t, b, r in events[e['ch']] if e['tick'] < t < stop]
            if inside:
                t, b, r = inside[-1]
                semis = round((b - (e.get('bend') or 0)) * r / 128)
                if semis:
                    e = e | {'slide': (max(-128, min(127, semis)), t - e['tick'])}
        timeline.append(e)
    return score | {'timeline': timeline}


BASE_KEY = 60
# 샘플 자원의 기준 음높이 값은 약 0x07E8(8kHz)이고 DSP 음높이는 0x3FFF 까지라, 기준음보다 36반음 넘게 높은 음은 음높이가
# 넘쳐 엉뚱한 소리가 난다(どくばり 의 +50 반음이 아주 작게 울림). 그런 음은 옥타브씩 내린다.
MAX_SHIFT = 36


def one_base(score):
    """악기 영역마다 따로 된 프로그램(기준음 BASE_KEY, 음역 전체)으로 나누고 음을 그만큼 옮긴 악보. 같은 NDS 샘플을 다른 기준음으로
    쓰는 효과음(19C 의 00-3C 는 기준음 60, 19F 는 32)도 같은 자원 하나로 울리게 한다. 음높이는 그대로다(벤드 나머지는
    반음 1/128 단위로 반올림). 기준음보다 MAX_SHIFT 넘게 높은 음은 옥타브씩 내린다."""
    instruments, mapping = {}, {}
    for program, instrument in (score.get('instruments') or {}).items():
        for k, region in enumerate((instrument or {}).get('regions') or []):
            new = int(program) * 16 + k
            if k >= 16:
                raise ValueError('more than 16 regions in one instrument')
            mapping[(int(program), k)] = (new, BASE_KEY - region['base'])
            instruments[str(new)] = instrument | {'regions': [region | {'lo': 0, 'hi': 127, 'base': BASE_KEY}]}
    timeline = []
    for e in score['timeline']:
        if e.get('op') == 'note':
            regions = score['instruments'][str(e['program'])]['regions']
            k = next(i for i, r in enumerate(regions) if r['lo'] <= e['note'] <= r['hi'])
            program, shift = mapping[(e['program'], k)]
            # 고정 벤드의 온 반음도 음으로 옮긴다(벤드는 샘플 음높이에 구워져 같은 샘플이 다른 자원이 된다)
            scale = e.get('bend_range', 2)
            units = (e.get('bend') or 0) * scale
            semis = round(units / 128)
            if not 0 <= e['note'] + shift + semis <= 127:
                raise ValueError('note leaves the MIDI range when moved to the common base key')
            note = e['note'] + shift + semis
            while note - BASE_KEY > MAX_SHIFT and instruments[str(program)].get('type') != NOISE_TYPE:
                note -= 12
            e = e | {'program': program, 'note': note, 'bend': round((units - semis * 128) / scale) if scale else 0}
            if e.get('slide'):
                # 미끄럼 끝도 음높이 한계 안에(넘치면 음높이가 돌아 엉뚱한 소리). 낮은 쪽은 0 까지 내려도 깨지지 않는다
                top = BASE_KEY + MAX_SHIFT - note
                e = e | {'slide': (min(e['slide'][0], top), e['slide'][1])}
        timeline.append(e)
    return score | {'instruments': instruments, 'timeline': timeline}


def build_spare(data, assets, specs, sequence_bytes, tempo_from=0x37, volumes=None, keep=None, waves=None, max_rate=8000,
                cache_dir=None, substitutes=None):
    """샘플이 드는 NDS 효과음을 DQ4 가 부르지 않는 빈 효과음 시퀀스에 모은다. specs = {빈 효과음: {갈래: NDS 번호 또는 None}}.

    None 은 소리 없는 갈래로, 부르면 레코드의 샘플만 받는다(미리 받기). 갈래 번호는 0C n X 의 X 라 21 보다 작아야 스크립트가
    곡 변수를 두고, 템포는 tempo_from 효과음의 것을 쓴다. keep 은 {빈 효과음: 쓸 NDS 샘플 파일 집합} 으로, 그 밖의 샘플을 쓰는 음은 뺀다
    (샘플 칸이 모자람). NDS PSG 잡음 악기는 DSP 잡음으로, waves({NDS 샘플 파일: 늘 두는 파형 번호})의 샘플은 늘 두는 파형으로
    울린다(레코드에 그 번호가 그대로 들어감). volumes 는 {(빈 효과음, 갈래): 목소리 음량 ED}. substitutes 는
    {(빈 효과음, 갈래): {NDS 샘플: 대신 쓸 NDS 샘플}} 로, keep 에 없는 샘플의 음을 빼는 대신 비슷한 샘플로 울린다.
    샘플은 임시 번호(26~)로 돌려주고, 음높이만 다른 같은 샘플은 시퀀스를 가리지 않고 한 번만 둔다(같은 곡에 함께 붙일 때
    샘플 칸을 아낌). 번호를 매기고 곡에 붙이는 것은 부르는 쪽(dq4soundset) 몫이다.
    ({빈 효과음: (시퀀스 바이트, 레코드 순서 [임시 번호], 보고서)}, {임시 번호: 자원})."""
    lines = listing(sequence_bytes(data, tempo_from))
    tempo = next(ln for ln in lines if ln and not ln[0].isspace() and not ln.endswith(':'))
    resources, by_bytes, baked, out = {}, {}, {}, {}
    # 대신 쓸 샘플은 그 샘플을 쓰는 다른 갈래의 영역(기준음·엔벨로프)을 그대로 써야 같은 자원이 되어 칸이 늘지 않는다
    regions = {}
    for spec in specs.values():
        for ident in spec.values():
            if ident and not ident.endswith('!'):
                for ins in json.loads(sfx_path(assets, ident).read_text())['instruments'].values():
                    for r in (ins or {}).get('regions') or []:
                        regions.setdefault(r.get('sample'), r)
    for seq, spec in sorted(specs.items()):
        out[seq] = _spare_sequence(assets, seq, spec, tempo, resources, by_bytes, baked, (volumes or {}),
                                   (keep or {}).get(seq), waves or {}, max_rate, cache_dir, substitutes or {}, regions)
    return out, resources


def prerendered(assets, ident, cache_dir=None):
    """NDS 가 실제로 낸 그 효과음 소리(sfx/*.wav, 스테레오)를 모노 WAV 로(cache_dir 아래, 없으면 임시 폴더). 음 여럿이 샘플
    여럿을 쓰는 효과음을 샘플 칸 하나로 울릴 때 쓴다(맨손 1C4: 00-2F 셋 + 00-05 하나)."""
    import tempfile
    import wave
    import numpy as np
    source = sfx_path(assets, ident).with_suffix('.wav')
    with wave.open(str(source)) as w:
        rate, channels = w.getframerate(), w.getnchannels()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').reshape(-1, channels).astype(float).mean(axis=1)
    loud = np.nonzero(np.abs(pcm) > 64)[0]
    pcm = pcm[:loud[-1] + 1] if len(loud) else pcm
    folder = Path(cache_dir) / 'prerendered' if cache_dir else Path(tempfile.mkdtemp())
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f'{ident.upper()}.wav'
    with wave.open(str(out), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.clip(np.round(pcm), -32768, 32767).astype('<i2').tobytes())
    return out


def _prerendered_score(score, ident):
    """원래 악보의 첫 음을 본으로, 0 틱에 기준음 하나를 끝까지 울리는 악보(프로그램 0 = 렌더한 소리)."""
    first = next(e for e in score['timeline'] if e.get('op') == 'note')
    note = first | {'tick': 0, 'note': BASE_KEY, 'velocity': 127, 'gate': score.get('end_tick', 48), 'len': 0,
                    'program': 0, 'bend': 0, 'volume': 127, 'expression': 127, 'pan': 64, 'uid': 0}
    note.pop('slide', None)
    region = {'lo': 0, 'hi': 127, 'base': BASE_KEY, 'attack': 127, 'decay': 127, 'sustain': 127, 'release': 125,
              'type': 'PCM', 'sample': f'{ident.upper()}!'}
    return score | {'timeline': [note], 'instruments': {'0': {'type': 'PCM', 'regions': [region]}}}


def _spare_sequence(assets, seq, spec, tempo, resources, by_bytes, baked, volumes, keep, waves, max_rate, cache_dir,
                    substitutes, regions):
    order, branches, report = [], {}, {}
    for branch, ident in sorted(spec.items()):
        if not 0 <= branch < 0x21:
            raise ValueError(f'branch {branch:02X}: effect branches select scripts 00..20')
        if ident is None:
            branches[branch] = ([], [])
            report[f'{branch:02X}'] = {'nds': None}
            continue
        whole = ident.endswith('!')
        ident = ident.rstrip('!')
        path = sfx_path(assets, ident)
        dump = path.with_suffix('.txt')
        score = json.loads(path.read_text())
        if whole:
            score = _prerendered_score(score, ident)
        elif dump.exists():
            score = bend_slides(score, dump.read_text())
        swap = substitutes.get((seq, branch), {})
        if swap:
            score = score | {'instruments': {p: ins and ins | {'regions': [
                regions[swap[r['sample']]] | {'lo': r['lo'], 'hi': r['hi'], 'base': r['base']} if r.get('sample') in swap else r
                for r in ins.get('regions') or []]} for p, ins in score['instruments'].items()}}
        score = one_base(score)
        instruments = score['instruments']
        noise = {int(p) for p, ins in instruments.items() if (ins or {}).get('type') == NOISE_TYPE}
        waved = {int(p): waves[ins['regions'][0]['sample']] for p, ins in instruments.items()
                 if int(p) not in noise and ins and ins.get('regions') and ins['regions'][0]['sample'] in waves}

        def kept(e):
            return (e['program'] in noise or e['program'] in waved or keep is None or whole
                    or instruments[str(e['program'])]['regions'][0]['sample'] in keep)
        notes = [e for e in score['timeline'] if e.get('op') == 'note']
        left_out = sorted({instruments[str(e['program'])]['regions'][0]['sample'] for e in notes if not kept(e)})
        score = score | {'timeline': [e for e in score['timeline'] if e.get('op') != 'note' or kept(e)]}
        pcm = score | {'timeline': [e for e in score['timeline']
                                    if e.get('op') != 'note' or (e['program'] not in noise and e['program'] not in waved)]}
        remap, program_map, samples = {}, {}, {}
        if whole:
            program, region = next((int(p), ins['regions'][0]) for p, ins in instruments.items())
            resource, sample_detail = bank.convert_sample(prerendered(assets, ident, cache_dir), region, max_rate=max_rate,
                                                          cache_dir=cache_dir)
            found, program_map = {0x26: resource}, {program: [{'lo': 0, 'hi': 127, 'sample': 0x26}]}
            detail = {'samples': {'26': sample_detail}}
        if whole or any(e.get('op') == 'note' for e in pcm['timeline']):
            if not whole:
                found, program_map, detail = bank.build_bank(pcm, assets, start_id=0x26, max_rate=max_rate,
                                                             cache_dir=cache_dir)
            for temp, payload in sorted(found.items()):
                # 자원 머리 [길이 2][반복 2][ADSR 2][GAIN][음높이 2] 에서 음높이만 다르면(구운 벤드만 다름) 한 자원으로 울리고,
                # 그 차이는 변환기가 음마다 미세 조정(E9)으로 낸다(프로그램 표 'tune' = 그 자원에 구운 벤드)
                body = payload[:7] + payload[9:]
                if body not in by_bytes:
                    by_bytes[body] = 0x26 + len(resources)
                    resources[by_bytes[body]] = payload
                    baked[by_bytes[body]] = detail['samples'][f'{temp:02X}'].get('tune', 0)
                remap[temp] = by_bytes[body]
            program_map = {p: [{k: v for k, v in r.items() if k != 'tune'} | {'sample': remap[r['sample']]}
                               | ({'tune': baked[remap[r['sample']]]} if baked[remap[r['sample']]] else {})
                               for r in regions] for p, regions in program_map.items()}
            samples = {f'{remap[int(k, 16)]:02X}': {'source': v['source'], 'hz': round(v['effective_rate']),
                                                     'brr_bytes': v['brr_bytes']} for k, v in detail['samples'].items()}
        program_map |= {p: port.NOISE for p in noise} | {p: [{'lo': 0, 'hi': 127, 'sample': w}] for p, w in waved.items()}
        entries, text, dropped, more = convert_branch(score, program_map, order, volumes.get((seq, branch), 0x30),
                                                      all_rests=True)
        order += more
        branches[branch] = (entries, text)
        report[f'{branch:02X}'] = {'nds': ident.upper(), 'title': score.get('title'), 'tracks': len(entries),
                                   'dropped_notes': dropped, 'left_out_samples': left_out, 'samples': samples}
    base = assemble([tempo, 'track Lnone', 'Lnone:', '  end'])
    return splice(base, branches), order, report
