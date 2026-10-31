"""NDS DQ4 효과음을 DQ5 효과음 시퀀스의 갈래로 바꿔 끼운다.

DQ5 효과음 시퀀스(32~46)는 트랙 첫머리의 if_flag(E0)로 갈래(명령 0C n X 의 X)를 고른다. 바꿀 갈래마다 NDS 효과음을
dq4soundport.convert 로 바꾸고, 원래 시퀀스를 글(dq5song.listing)로 풀어 트랙 첫머리에 그 갈래로 뛰는 if_flag 를 더한 뒤
다시 싼다(점프는 상대 주소라 글로 다루면 원래 갈래가 그대로 남는다).

효과음 샘플은 늘 둬야 하는데 SPC 샘플 칸(20개)을 이미 다 쓰는 곡이 있어, 새 샘플이 드는 효과음은 받지 않는다.
NDS PSG 잡음 악기만 쓰는 효과음은 DSP 잡음(E3)으로 옮기므로 샘플이 들지 않는다. 짧은 음정 파형만 쓰는 효과음은
waves({NDS 샘플 파일: 늘 두는 샘플 번호})로 늘 두는 DQ5 효과음 파형 자리(20~22)에 넣은 한 주기 파형으로 울린다.
"""
import json
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


def convert_branch(score, program_map, record=(), voice_volume=0x30):
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
    body = [ln for i, ln in enumerate(body)
            if not (ln.split()[:1] == ['rest'] and i + 1 < len(body) and body[i + 1].split() == ['end'])]

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
