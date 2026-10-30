"""NDS DQ4 효과음을 DQ5 효과음 시퀀스의 갈래로 바꿔 끼운다.

DQ5 효과음 시퀀스(32~46)는 트랙 첫머리의 if_flag(E0)로 갈래(명령 0C n X 의 X)를 고른다. 바꿀 갈래마다 NDS 효과음을
dq4soundport.convert 로 바꾸고, 원래 시퀀스를 글(dq5song.listing)로 풀어 트랙 첫머리에 그 갈래로 뛰는 if_flag 를 더한 뒤
다시 싼다(점프는 상대 주소라 글로 다루면 원래 갈래가 그대로 남는다).

효과음 샘플은 늘 둬야 하는데 SPC 샘플 칸(20개)을 이미 다 쓰는 곡이 있어, 새 샘플이 드는 효과음은 받지 않는다.
NDS PSG 잡음 악기만 쓰는 효과음은 DSP 잡음(E3)으로 옮기므로 샘플이 들지 않는다.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dq5' / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4soundport as port  # noqa: E402
from dq5song import assemble, listing  # noqa: E402

NOISE_TYPE = '잡음'
MAX_VOICES = 2  # 효과음 목소리(6·7). 곡은 목소리 0~6 을 쓰므로 둘째 목소리는 곡의 6 을 잠시 빌린다


def sfx_path(assets, ident):
    found = sorted((Path(assets) / 'nds/dq4/sound/sfx').glob(f'{ident.upper()}-*.json'))
    if len(found) != 1:
        raise ValueError(f'NDS sound effect {ident}: expected one score, found {len(found)}')
    return found[0]


def noise_program_map(score):
    """잡음 악기만 쓰는 효과음의 program_map. 샘플이 드는 악기가 있으면 None."""
    used = {e['program'] for e in score['timeline'] if e.get('op') == 'note'}
    instruments = score.get('instruments') or {}
    if any(instruments.get(str(p), {}).get('type') != NOISE_TYPE for p in used):
        return None
    return {p: port.NOISE for p in used}


def convert_branch(score, program_map):
    """(트랙 입구 이름표 목록, 본문 글 줄, 빠진 음 수). 목소리 하나로 빠지는 음이 있으면 둘로 바꾼다."""
    best = None
    for voices in range(1, MAX_VOICES + 1):
        result = port.convert(score, voices=voices, program_map=program_map)
        dropped = result.report['dropped_notes']
        if best is None or dropped < best[1]:
            best = (result, dropped)
        if not dropped:
            break
    result, dropped = best
    if result.samples:
        raise ValueError('sound effect needs samples; only noise effects are supported')
    lines = listing(result.sequence)
    starts = [w.split()[1] for w in lines if w.startswith('track ')]
    # 곡 변환은 트랙끼리 부르는 토막(call)을 함께 쓸 수 있어, 본문은 통째로 옮기고 트랙 입구만 가리킨다
    body = [ln for ln in lines if ln and (ln[0].isspace() or ln.endswith(':'))]
    # 곡 변환이 끝에 붙이는 쉼(rest len 30)은 효과음에선 트랙만 더 오래 살려 SPC 처리를 늘린다(맵을 불러오는 동안 받기가
    # 느려져 곡이 늦게 나옴). 마지막 음 뒤 바로 끝낸다.
    body = [ln for i, ln in enumerate(body)
            if not (ln.split() == ['rest', 'len', '30'] and i + 1 < len(body) and body[i + 1].split() == ['end'])]
    return starts, body, dropped


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


def splice(sequence, branches):
    """branches = {갈래: (트랙 입구 이름표, 본문 글 줄)}. 원래 시퀀스의 그 갈래를 새 트랙들로 바꾼 시퀀스 바이트.

    트랙마다 새 입구에서 바꾼 갈래의 if_flag 를 먼저 보고, 나머지는 원래 트랙 첫머리로 뛴다. 새 갈래에 없는 트랙은
    그 갈래에서 바로 끝내(원래 갈래의 둘째 목소리가 섞이지 않게)."""
    lines = listing(sequence)
    head = [ln for ln in lines if ln and not ln[0].isspace() and not ln.endswith(':')]
    body = [ln for ln in lines if ln and (ln[0].isspace() or ln.endswith(':'))]
    tempo, starts = head[0], [w.split()[1] for w in head[1:]]
    count = max([len(starts)] + [len(entries) for entries, _ in branches.values()])
    new_head, new_body = [tempo], body + ['LsfxEnd:', '  end']
    for i in range(count):
        entry = f'LsfxTrack{i}'
        new_head.append(f'track {entry}')
        new_body.append(f'{entry}:')
        for branch, (entries, _) in sorted(branches.items()):
            target = f'Lsfx{branch:02X}_' + entries[i][1:] if i < len(entries) else 'LsfxEnd'
            new_body.append(f'  if_flag {branch:02X} -> {target}')
        new_body.append(f'  jump -> {starts[i]}' if i < len(starts) else '  end')
    for branch, (_, text) in sorted(branches.items()):
        new_body += _rename(text, f'Lsfx{branch:02X}_')
    return assemble(new_head + new_body)


def build_effects(data, assets, spec, sequence_bytes):
    """spec = {(효과음, 갈래): NDS 번호}. {효과음: 새 시퀀스 바이트}, 보고서."""
    by_seq, report = {}, {}
    for (seq, branch), ident in sorted(spec.items()):
        score = json.loads(sfx_path(assets, ident).read_text())
        program_map = noise_program_map(score)
        if program_map is None:
            raise ValueError(f'{seq:02X}-{branch:02X} <- {ident}: uses samples (SPC sample slots are full); '
                             'only noise effects are supported')
        entries, text, dropped = convert_branch(score, program_map)
        by_seq.setdefault(seq, {})[branch] = (entries, text)
        report[f'{seq:02X}-{branch:02X}'] = {'nds': ident.upper(), 'title': score.get('title'), 'tracks': len(entries),
                                              'dropped_notes': dropped}
    return {seq: splice(sequence_bytes(data, seq), branches) for seq, branches in by_seq.items()}, report
