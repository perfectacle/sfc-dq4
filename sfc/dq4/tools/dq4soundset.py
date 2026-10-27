"""NDS 곡 여러 개를 SPC 예산에 맞춰 샘플을 줄이고 DQ5 곡 자리에 한꺼번에 넣는다.

곡마다 시퀀스 크기를 먼저 어림해 dq4soundpatch.sample_budget 으로 샘플 예산을 정하고,
dq4soundbank.build_bank 가 그 안으로 샘플을 줄인 뒤 dq4soundport 로 변환해 dq4soundpatch.install 로 넣는다.
형식과 실측은 sfc/dq4/docs/dq4-sound-port-format.md. 롬·IPS·보고서는 work/ 에만 둔다.

  uv run --locked python sfc/dq4/tools/dq4soundset.py --base 롬 --assets ../sfc-dq4-assets \
    --song 06=0E --song 02=05 --song 17=1E --stream 17=9000 --out work/sound/set/set.sfc [--preview 06] [--map-fades]
    [--budget 06=15967 ...]
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
# 곡이 울리는 동안 보내는 샘플은 샘플 사이에 0~40프레임씩 쉬어, 전투 시작 실측에서 평균 프레임당 약 59바이트였다
# (손잡기만 보면 약 118). 도착 어림은 늦게 잡아야 안전하다: 이르게 잡으면 도착 전에 마지막 instrument 를 써 버려
# 그 트랙이 다음 악기 바꿈까지 막힌다. 늦게 잡으면 instrument 가 몇 개 더 들 뿐이다.
STREAM_BYTES_PER_FRAME = 59
ARRIVAL_SLACK_FRAMES = 30
FRAME_RATE = 60.0988


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


def transfer_plan(first_tick, notes, sizes, pre_bytes):
    """곡 묶음의 샘플 순서·곡 앞 샘플 수 k·곡 뒤 샘플의 도착 어림(곡 시작부터 초)을 정한다.

    먼저 쓰이는 샘플(같으면 음이 많은 것)부터 늘어놓고, 앞에서부터 pre_bytes 안에 드는 만큼을
    곡 앞(시퀀스와 함께 곡을 틀기 전에 보냄)으로, 나머지는 곡이 울리는 동안 이 순서로 보낸다.
    """
    order = sorted(sizes, key=lambda s: (first_tick[s], -notes[s], s))
    k, used = 0, 0
    while k < len(order) and used + sizes[order[k]] <= pre_bytes:
        used += sizes[order[k]]
        k += 1
    arrivals, sent = {}, 0
    for s in order[k:]:
        sent += sizes[s]
        frames = sent / STREAM_BYTES_PER_FRAME + ARRIVAL_SLACK_FRAMES
        arrivals[s] = frames / FRAME_RATE
    return order, k, arrivals


def sample_identity(detail):
    """표본율·자르기만 다르고 같은 NDS 샘플·기준음·ADSR·반복인 자원을 한 묶음으로 본다."""
    envelope = detail['envelope']
    return detail['source'], detail['base_midi'], envelope['adsr1'], envelope['adsr2'], bool(detail['source_loop'])


def share_samples(found, details, program_map, resources, known, next_id, *, budget=None, loose=False):
    """build_bank 의 임시 번호(26~)를 전역 번호로 바꾼다. 앞 곡이 넣은 샘플을 다시 쓸 수 있으면 그 번호를 쓴다.

    NDS 곡들은 파형 묶음 넷을 나눠 쓰므로 같은 샘플이 여러 곡에 나온다. 샘플 번호는 26~C7(162개)뿐이라
    합치지 않으면 곡 묶음 전체에 모자란다. 바이트까지 같은 자원은 늘 합친다. loose 면 같은 샘플의 다른 표본율도 쓴다:
    더 높은 표본율은 곡의 샘플 예산 안에 들 때, 낮은 것은 한 단계(0.7배) 안일 때만. 음높이는 자원 머리에 들어 있어
    표본율이 달라도 음정은 같다. known 은 {전역 번호: (샘플 묶음, 표본율, 바이트, 보고서)} 이고 이 함수가 채운다.
    """
    by_bytes = {payload: ident for ident, payload in resources.items()}
    total = sum(map(len, found.values()))
    remap, out, shared = {}, {}, []
    for ident, payload in sorted(found.items()):
        detail = details[f'{ident:02X}']
        key, rate = sample_identity(detail), detail['effective_rate']
        chosen = by_bytes.get(payload)
        if chosen is None and loose:
            mates = [(r, size, i) for i, (k, r, size, _) in known.items() if k == key]
            up = [m for m in mates if m[0] > rate and budget is not None and total - len(payload) + m[1] <= budget]
            down = [m for m in mates if rate * 0.7 <= m[0] < rate]
            pick = max(up or down, default=None)
            if pick is not None:
                chosen = pick[2]
                total += pick[1] - len(payload)
                shared.append({'sample': detail['source'], 'rate': round(rate), 'used': f'{chosen:02X}',
                               'used_rate': round(pick[0])})
        if chosen is None:
            if next_id >= 0xC8:
                raise ValueError('sample ID table exhausted (26..C7)')
            chosen = next_id
            by_bytes[payload] = chosen
            known[chosen] = (key, rate, len(payload), detail)
            next_id += 1
        remap[ident] = chosen
        out[chosen] = resources.get(chosen, payload)
    mapping = {program: [{**r, 'sample': remap[r['sample']]} for r in regions]
               for program, regions in program_map.items()}
    return out, mapping, remap, shared


def build(base, assets, songs, *, cache_dir, max_rate=8000, max_samples=14, map_fades=False, preview=None,
          stream=None, budgets=None):
    """stream 은 {곡 자리: 곡 앞 샘플 바이트 상한}. 그 곡은 샘플 일부를 곡이 울리는 동안 보낸다(transfer_plan).

    budgets 는 {곡 자리: 샘플 예산 바이트}. 주면 시퀀스 크기로 정한 예산 대신 이 값으로 샘플을 줄인다. 시퀀스가
    작아져도 청취 승인한 샘플(줄이기 결과)을 그대로 두려면 그때의 예산을 준다. SPC 예산 검사는 install 이 그대로 한다.
    """
    stream = stream or {}
    budgets = budgets or {}
    data = bytes(base)
    records = patch.read_sets(data)
    if len({slot for slot, _ in songs}) != len(songs):
        raise ValueError('each DQ5 slot may be replaced once')
    replacements, resources, reports, known = {}, {}, {}, {}
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
        budget = budgets.get(slot) or patch.sample_budget(data, slot, sequence_size + MARGIN, extra_table=max(0, growth))
        try:
            found, program_map, bank_report = bank.build_bank(score, assets, start_id=0x26, max_rate=max_rate,
                                                              cache_dir=cache_dir, budget=budget, max_samples=max_samples)
        except ValueError as exc:
            if 'cannot fit samples' not in str(exc):
                raise
            found, program_map, bank_report = bank.build_bank(score, assets, start_id=0x26, max_rate=max_rate,
                                                              cache_dir=cache_dir, budget=budget, max_samples=max_samples,
                                                              rates=bank.LOW_RATES)
            bank_report['low_rates'] = True
        # 청취 승인한 곡(예산을 준 곡)은 샘플을 바꾸지 않도록 바이트까지 같은 것만 합친다.
        found, program_map, remap, loose = share_samples(found, bank_report['samples'], program_map, resources, known,
                                                         next_id, budget=budget, loose=slot not in budgets)
        bank_report['samples'] = {f'{x:02X}': known[x][3] for x in sorted(found)}
        bank_report['shared_samples'] = sorted(f'{x:02X}' for x in found if x in resources)
        bank_report['shared_other_rate'] = loose
        bank_report['resource_bytes'] = sum(map(len, found.values()))
        conversion = port.convert(score, program_map=program_map)
        send_first, plan = None, None
        if slot in stream:
            if set(conversion.samples) - found.keys():
                raise ValueError('streamed songs must use only their own converted samples')
            usage = conversion.report
            first = {int(k, 16): v for k, v in usage['sample_first_tick'].items()}
            notes = {int(k, 16): v for k, v in usage['sample_notes'].items()}
            order, send_first, arrivals = transfer_plan(first, notes, {s: len(found[s]) for s in conversion.samples},
                                                        stream[slot])
            conversion = port.convert(score, program_map=program_map, sample_order=order, arrivals=arrivals)
            plan = {'pre_bytes_cap': stream[slot], 'send_first': send_first,
                    'pre_sample_bytes': sum(len(found[s]) for s in order[:send_first]),
                    'arrival_seconds': {f'{s:02X}': round(t, 3) for s, t in arrivals.items()}}
        replacements[slot] = patch.Replacement(conversion.sequence, tuple(conversion.samples), send_first)
        resources.update(found)
        next_id = max(resources) + 1
        print(f'{slot:02X} <- NDS {ident.upper()}: {len(found)} samples ({len(bank_report["shared_samples"])} shared), '
              f'sequence {len(conversion.sequence)}', file=sys.stderr, flush=True)
        reports[f'{slot:02X}'] = {'nds_song': ident.upper(), 'score': path.name, 'sample_budget': budget,
                                   'bank': bank_report, 'conversion': conversion.report, 'stream': plan}
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
    ap.add_argument('--preview-dir', type=Path,
                    help='also write pvNN.sfc (title and menu play song NN) for every replaced song into this folder')
    ap.add_argument('--budget', action='append', default=[], metavar='DQ5_SLOT=BYTES',
                    help='sample budget for that song instead of the one computed from its sequence size')
    ap.add_argument('--stream', action='append', default=[], metavar='DQ5_SLOT=PRE_BYTES',
                    help='send only the first samples (up to PRE_BYTES) before the song starts, the rest while it plays')
    args = ap.parse_args()
    songs = []
    for value in args.song:
        slot, ident = value.split('=', 1)
        songs.append((int(slot, 16), ident))
    base = args.base.read_bytes()
    stream = {int(slot, 16): int(cap) for slot, cap in (value.split('=', 1) for value in args.stream)}
    budgets = {int(slot, 16): int(value) for slot, value in (item.split('=', 1) for item in args.budget)}
    rom, report = build(base, args.assets, songs, cache_dir=args.out.parent / 'brr-cache', max_rate=args.max_rate,
                        max_samples=args.max_samples, map_fades=args.map_fades, preview=args.preview, stream=stream,
                        budgets=budgets)
    from dq5build import make_ips
    from kr_patch import ips
    patch_bytes = make_ips(base, rom)
    if ips.apply(base, patch_bytes) != rom:
        raise ValueError('IPS round trip mismatch')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(rom)
    args.out.with_suffix('.ips').write_bytes(patch_bytes)
    args.out.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    if args.preview_dir:
        args.preview_dir.mkdir(parents=True, exist_ok=True)
        for slot, _ in songs:
            (args.preview_dir / f'pv{slot:02X}.sfc').write_bytes(patch.preview_rom(rom, slot))
    summary = {slot: {'budget': r['sample_budget'], 'samples': r['bank']['sample_count'],
                      'brr': r['bank']['resource_bytes'], 'sequence': r['conversion']['sequence_bytes'],
                      'reductions': len(r['bank']['reductions']), 'dropped_notes': r['conversion']['dropped_notes'],
                      **({'send_first': r['stream']['send_first'], 'late_notes': r['conversion']['late_notes'],
                          'reissued_instruments': r['conversion']['reissued_instruments']} if r['stream'] else {})}
               for slot, r in report['songs'].items()}
    print(json.dumps({'heap_start': report['install']['heap_start'], 'songs': summary}, indent=2))


if __name__ == '__main__':
    main()
