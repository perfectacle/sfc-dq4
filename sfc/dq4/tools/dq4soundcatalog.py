"""NDS DQ4 사운드 에셋의 포팅 목록. 악보·소리는 출력하지 않고 메타데이터만 쓴다.

장면 대응 근거: nds/dq4/docs/sound-format.md 「곡 목록」.
DQ5 호출 근거: sfc/dq5/docs/dq5-sound-format.md 「효과음마다」.
장면이 같은 후보는 음원이 같은 것으로 간주하지 않는다.
"""
import argparse
import json
from pathlib import Path
import sys


FC_SCENES = {
    '01': '02', '02': '03', '03': '03', '04': '1F', '05': '05', '06': '25',
    '07': '16', '08': '26', '09': '17', '0A': '27', '0B': '20', '0C': '0B',
    '0D': '28', '0E': '0C', '0F': '0C', '10': '04', '11': '15', '12': '1B',
    '13': '1C', '14': '1D', '15': '06', '16': '07', '17': '0E', '18': '08',
    '19': '09', '1C': '13', '1D': '0A', '1E': '0D', '20': '1E', '21': '35',
    '22': '31', '26': '2D', '28': '10', '29': '0F', '2A': '1A', '2C': '2E',
    '2D': '2F', '2E': '30', '2F': '01', '31': '2B',
}

# 이는 DQ5 엔진에서 확인한 호출이다. NDS와의 선율·음색 일치 판정은 아니다.
NATIVE_CUES = {
    'menu_select': ('33-00', '00:8110,04:CCAA,24:8476', 'verified_native_scene'),
    'dialog_open': ('32-00', '04:9DA2', 'verified_native_scene'),
    'menu_close': ('34-03', '00:83CF', 'verified_native_scene'),
    'map_move': ('34-02', '00:CA3B,00:CC20', 'observed_call_scene_uncertain'),
    'door_open': ('35-01', '01:E01B', 'verified_native_scene'),
    'damage': ('37-01', '26:8B11', 'verified_native_scene'),
    'cast_spell': ('37-0E', '26:8AFF', 'verified_native_scene'),
}
SFX_CANDIDATES = {
    '12C': ('menu_select',), '12D': ('dialog_open',), '12E': ('dialog_open',),
    '12F': ('dialog_open',), '130': ('menu_select',), '131': ('map_move',),
    '132': ('cast_spell',), '134': ('door_open',), '135': ('door_open',),
    '136': ('door_open',), '137': ('door_open',), '192': ('damage',), '193': ('damage',),
}
BGM_CANDIDATES = {'29': ('1D',), '27': ('20',)}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def score_path(directory, filename):
    path = directory / filename
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError(f'악보 경로가 에셋 폴더 밖을 가리킴: {filename}')
    return path


def score_metrics(score):
    """게이트 동안의 음 중첩. ADSR 릴리스가 더 차지하는 목소리는 포함하지 않는다."""
    notes = [e for e in score['timeline'] if e.get('op') == 'note']
    changes = []
    features = set()
    for e in notes:
        start, gate = e['tick'], e['gate']
        if gate > 0:
            changes.extend(((start, 1), (start + gate, -1)))
        for key in ('bend', 'mod', 'sweep', 'portamento', 'tie'):
            if e.get(key):
                features.add(key)
        if any(v is not None for v in e.get('adsr', []) or []):
            features.add('adsr_override')
    active = peak = 0
    for _, delta in sorted(changes):
        active += delta
        peak = max(peak, active)
    pitches = [e['note'] for e in notes]
    return {
        'tracks': len(score['channels']), 'notes': len(notes), 'peak_gate_voices': peak,
        'voice_measurement': 'gate_only_release_tail_excluded',
        'midi_range': [min(pitches), max(pitches)] if pitches else None,
        'programs': sorted(score.get('instruments', {}), key=int),
        'expressive_features': sorted(features),
        'loop_start': score.get('loop_start'), 'loop_len': score.get('loop_len'),
    }


def verify_inn(score, rom_path):
    """주선율·화음 전체를 대조한다. NDS의 지연 겹침 파트·음색은 같다고 판정하지 않는다."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dq5/tools'))
    from dq5map import Rom
    from dq5song import play
    from dq5spc import body, sequences

    rom = Rom(Path(rom_path).read_bytes())
    _, address, length = sequences(rom)[0x1D]
    tracks = play(bytes(body(rom, address, length)), 1000)
    evidence = []
    for channel, indices in (('track0', (0, 1)), ('track1', (2, 3))):
        source = [(e['tick'], e['note']) for e in score['timeline']
                  if e['ch'] == channel and e.get('op') == 'note']
        target = sorted((tick, note + 23) for i in indices for tick, note, _, _ in tracks[i]
                        if isinstance(note, int))
        if not source or len(source) != len(target):
            raise ValueError('여관 징글 음 수 불일치')
        if [n for _, n in source] != [n for _, n in target]:
            raise ValueError('여관 징글 음높이 불일치')
        error = max(abs(a[0] - b[0]) for a, b in zip(source, target))
        if error > 1:
            raise ValueError('여관 징글 음 시각 차이 1틱 초과')
        evidence.append({'nds_track': channel, 'dq5_tracks': list(indices),
                         'matched_notes': len(source), 'max_tick_difference': error})
    return {'dq5': '1D', 'command': '01 1D', 'status': 'verified_melody_and_harmony',
            'evidence': evidence, 'arrangement_difference': 'NDS delayed doubles and instrument timbre differ'}


def build_catalog(asset_root, *, dq5_rom=None):
    root = Path(asset_root)
    native_sfx = {e['id']: e for e in read_json(root / 'sfc/dq5/sound/sfx/index.json')}
    native_songs = {e['id']: e for e in read_json(root / 'sfc/dq5/sound/songs/index.json')}
    cues = {}
    for cue, (identifier, calls, status) in NATIVE_CUES.items():
        e = native_sfx[identifier]
        cues[cue] = {
            'dq5': identifier, 'command': e['command'], 'scene': e['scene'],
            'evidence_status': status, 'calls': calls.split(','),
            'evidence': 'sfc/dq5/docs/dq5-sound-format.md#효과음마다',
            'nds_identity_verified': False,
        }
    entries = []
    for kind, folder in (('song', 'songs'), ('sfx', 'sfx')):
        directory = root / 'nds/dq4/sound' / folder
        index = read_json(directory / 'index.json')
        for identifier, e in sorted(index.items(), key=lambda pair: int(pair[0], 16)):
            row = {
                'id': identifier, 'kind': kind, 'title': e['title'], 'name': e['name'],
                'scenes': e.get('scenes', []), 'score': e.get('score'),
                'fc_same_scene': FC_SCENES.get(identifier) if kind == 'song' else None,
                'fc_evidence': 'nds/dq4/docs/sound-format.md#곡-목록' if kind == 'song' else None,
                'exact_reuse': None, 'reuse_candidates': [],
                'conversion_status': 'not_evaluated', 'requirements': [],
            }
            if kind == 'song' and identifier in BGM_CANDIDATES:
                for candidate in BGM_CANDIDATES[identifier]:
                    source = native_songs[candidate]
                    row['reuse_candidates'].append({
                        'dq5': candidate, 'scene': source['scene'],
                        'status': 'same_function_only', 'identity_verified': False,
                    })
            if kind == 'sfx':
                for cue in SFX_CANDIDATES.get(identifier, ()):
                    row['reuse_candidates'].append({
                        'dq5': cues[cue]['dq5'], 'cue': cue,
                        'status': 'same_function_only', 'identity_verified': False,
                    })
            if kind == 'song' and identifier == '01' and e.get('kind') == 'STRM':
                row['conversion_status'] = 'existing_overture'
                row['implementation'] = 'sfc/dq4/tools/dq4overture.py'
                row['requirements'] = ['preserve_existing_title_arrangement']
            elif not e.get('score'):
                row['conversion_status'] = 'unsupported'
                row['requirements'] = ['missing_sequence_score']
            else:
                path = score_path(directory, e['score'])
                if not path.is_file():
                    row['conversion_status'] = 'unsupported'
                    row['requirements'] = ['missing_score_file']
                else:
                    score = read_json(path)
                    if score['id'] != identifier or score['kind'] != kind:
                        raise ValueError(f'인덱스와 악보 번호/종류 불일치: {folder}/{identifier}')
                    row['metrics'] = metrics = score_metrics(score)
                    row['requirements'] = ['instrument_mapping', 'runtime_verification']
                    if metrics['peak_gate_voices'] > (7 if kind == 'song' else 1):
                        row['requirements'].append('voice_reduction')
                    if metrics['expressive_features']:
                        row['requirements'].append('expressive_controls')
                    if metrics['midi_range'] and not (
                        24 <= metrics['midi_range'][0] <= metrics['midi_range'][1] <= 101
                    ):
                        row['requirements'].append('pitch_range_adaptation')
                    if not metrics['notes']:
                        row['conversion_status'] = 'unsupported'
                        row['requirements'] = ['no_note_events']
                    if kind == 'song' and identifier == '29' and dq5_rom is not None:
                        row['exact_reuse'] = verify_inn(score, dq5_rom)
            entries.append(row)
    return {
        'schema_version': 1, 'source': 'nds/dq4/sound',
        'summary': {
            'songs': sum(e['kind'] == 'song' for e in entries),
            'sfx': sum(e['kind'] == 'sfx' for e in entries),
            'exact_reuse_verified': sum(e['exact_reuse'] is not None for e in entries),
            'unsupported': sum(e['conversion_status'] == 'unsupported' for e in entries),
        },
        'native_engine_cues': cues, 'entries': entries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--dq5-rom', type=Path, help='여관 징글의 선율·화음 재사용 근거를 다시 검증')
    args = parser.parse_args()
    result = build_catalog(args.assets, dq5_rom=args.dq5_rom)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
