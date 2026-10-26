"""NDS 곡 여러 개를 SPC 예산에 맞춰 샘플을 줄이고 DQ5 곡 자리에 한꺼번에 넣는다.

곡마다 시퀀스 크기를 먼저 어림해 dq4soundpatch.sample_budget 으로 샘플 예산을 정하고,
dq4soundbank.build_bank 가 그 안으로 샘플을 줄인 뒤 dq4soundport 로 변환해 dq4soundpatch.install 로 넣는다.
형식과 실측은 sfc/dq4/docs/dq4-sound-port-format.md. 롬·IPS·보고서는 work/ 에만 둔다.

  uv run --locked python sfc/dq4/tools/dq4soundset.py --base 롬 --assets ../sfc-dq4-assets \
    --song 06=0E --song 02=05 --out work/sound/set/set.sfc [--preview 06] [--map-fades]
"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dq4soundbank as bank  # noqa: E402
import dq4soundpatch as patch  # noqa: E402
import dq4soundport as port  # noqa: E402

MARGIN = 128  # 어림한 시퀀스와 실제 시퀀스의 악기 명령 차이


def score_path(assets, ident):
    found = sorted((Path(assets) / 'nds/dq4/sound/songs').glob(f'{ident.upper()}-*.json'))
    if len(found) != 1:
        raise ValueError(f'NDS song {ident}: expected one score JSON, found {len(found)}')
    return found[0]


def provisional_map(score):
    """영역마다 다른 가짜 샘플 번호를 주어 시퀀스 크기와 곡 묶음 레코드 길이의 위한계를 어림한다."""
    counts, _ = bank.used_regions(score)
    mapping, ids = {}, {}
    for program, k in sorted(counts):
        region = score['instruments'][str(program)]['regions'][k]
        key = (region['sample'], region['base'], bank.approximate_adsr(region))
        ids.setdefault(key, 0x26 + len(ids))
        mapping.setdefault(program, []).append({'lo': region['lo'], 'hi': region['hi'], 'sample': ids[key]})
    return mapping, len(ids)


def build(base, assets, songs, *, cache_dir, max_rate=8000, max_samples=14, map_fades=False, preview=None):
    data = bytes(base)
    records = patch.read_sets(data)
    if len({slot for slot, _ in songs}) != len(songs):
        raise ValueError('each DQ5 slot may be replaced once')
    replacements, resources, reports = {}, {}, {}
    next_id = 0x26
    plans = []
    for slot, ident in songs:
        path = score_path(assets, ident)
        score = json.loads(path.read_text())
        mapping, regions = provisional_map(score)
        plans.append((slot, ident, path, score, len(port.convert(score, program_map=mapping).sequence),
                      min(regions, max_samples)))
    # 표는 모든 곡을 넣은 뒤의 길이로 늘어나므로, 곡마다 예산에 전체 증가분을 쓴다.
    growth = sum(2 + slots - len(records[slot]) for slot, _, _, _, _, slots in plans)
    for slot, ident, path, score, sequence_size, _ in plans:
        budget = patch.sample_budget(data, slot, sequence_size + MARGIN, extra_table=max(0, growth))
        found, program_map, bank_report = bank.build_bank(score, assets, start_id=next_id, max_rate=max_rate,
                                                          cache_dir=cache_dir, budget=budget, max_samples=max_samples)
        conversion = port.convert(score, program_map=program_map)
        replacements[slot] = patch.Replacement(conversion.sequence, tuple(conversion.samples))
        resources.update(found)
        next_id += len(found)
        reports[f'{slot:02X}'] = {'nds_song': ident.upper(), 'score': path.name, 'sample_budget': budget,
                                   'bank': bank_report, 'conversion': conversion.report}
    rom, install_report = patch.install(base, replacements, sample_resources=resources,
                                        map_fades=map_fades, preview=preview)
    return rom, {'install': install_report, 'songs': reports}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', type=Path, required=True)
    ap.add_argument('--assets', type=Path, required=True)
    ap.add_argument('--song', action='append', required=True, metavar='DQ5_SLOT=NDS_ID')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--max-rate', type=int, default=8000)
    ap.add_argument('--max-samples', type=int, default=14)
    ap.add_argument('--map-fades', action='store_true')
    ap.add_argument('--preview', type=lambda x: int(x, 16))
    args = ap.parse_args()
    songs = []
    for value in args.song:
        slot, ident = value.split('=', 1)
        songs.append((int(slot, 16), ident))
    base = args.base.read_bytes()
    rom, report = build(base, args.assets, songs, cache_dir=args.out.parent / 'brr-cache', max_rate=args.max_rate,
                        max_samples=args.max_samples, map_fades=args.map_fades, preview=args.preview)
    from dq5build import make_ips
    from kr_patch import ips
    patch_bytes = make_ips(base, rom)
    if ips.apply(base, patch_bytes) != rom:
        raise ValueError('IPS round trip mismatch')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(rom)
    args.out.with_suffix('.ips').write_bytes(patch_bytes)
    args.out.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    summary = {slot: {'budget': r['sample_budget'], 'samples': r['bank']['sample_count'],
                      'brr': r['bank']['resource_bytes'], 'sequence': r['conversion']['sequence_bytes'],
                      'reductions': len(r['bank']['reductions']), 'dropped_notes': r['conversion']['dropped_notes']}
               for slot, r in report['songs'].items()}
    print(json.dumps({'heap_start': report['install']['heap_start'], 'songs': summary}, indent=2))


if __name__ == '__main__':
    main()
