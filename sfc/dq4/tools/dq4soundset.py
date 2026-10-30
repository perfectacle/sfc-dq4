"""NDS 곡 여러 개를 SPC 예산에 맞춰 샘플을 줄이고 DQ5 곡 자리에 한꺼번에 넣는다.

곡마다 시퀀스 크기를 먼저 어림해 dq4soundpatch.sample_budget 으로 샘플 예산을 정하고,
dq4soundbank.build_bank 가 그 안으로 샘플을 줄인 뒤 dq4soundport 로 변환해 dq4soundpatch.install 로 넣는다.
형식과 실측은 sfc/dq4/docs/dq4-sound-port-format.md. 롬·IPS·보고서는 work/ 에만 둔다.

  uv run --locked python sfc/dq4/tools/dq4soundset.py --base 롬 --assets ../sfc-dq4-assets \
    --song 06=0E --song 02=05 --song 17=1E --stream 17=9000 --out work/sound/set/set.sfc [--preview 06] [--map-fades]
    [--budget 06=15967 ...] [--pin 17 --resident-from 17 --drop-resident 00 --lanes 17=JSON --drop-track 17=track10
    --level-db 17=2 --program 21=56:3C --record 1D=2:1F,05]
"""
import argparse
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dq4soundbank as bank  # noqa: E402
import dq4soundcheck as check  # noqa: E402
import dq4soundpatch as patch  # noqa: E402
import dq4soundport as port  # noqa: E402

MARGIN = 128  # 어림한 시퀀스와 실제 시퀀스의 악기 명령 차이
# 곡이 울리는 동안 보내는 샘플은 샘플 사이에 0~40프레임씩 쉬어, 전투 시작 실측에서 평균 프레임당 약 59바이트였다
# (손잡기만 보면 약 118). 도착 어림은 늦게 잡아야 안전하다: 이르게 잡으면 도착 전에 마지막 instrument 를 써 버려
# 그 트랙이 다음 악기 바꿈까지 막힌다. 늦게 잡으면 instrument 가 몇 개 더 들 뿐이다.
STREAM_BYTES_PER_FRAME = 59
ARRIVAL_SLACK_FRAMES = 30
# 나눈 곡의 앞부분 길이: 본체 도착 어림보다 이만큼 길게(본체가 늦으면 앞부분 끝에서 1틱씩 쉬며 기다림)
CHAIN_SLACK_SECONDS = 0.5
# 나눈 곡은 앞부분 시퀀스도 SPC 에 있으므로 샘플 예산에서 이만큼 더 뺀다(앞부분은 19곡에서 232~873바이트, 나중 순서면 더 김)
CHAIN_INTRO_BYTES = 1536
FRAME_RATE = 60.0988
# 곡 붙들기: 붙든 샘플의 남은 바이트가 오는 속도. 곡 뒤 샘플 어림과 같은 늦은 값으로 잡아, 실제 전송이 이보다 느리지
# 않으면 재생이 받은 끝을 앞지르지 않는다(앞지르면 덜 온 자리의 옛 바이트가 잡음으로 울린다).
HOLD_BYTES_PER_FRAME = STREAM_BYTES_PER_FRAME
HOLD_TIMEOUT_FRAMES = 70  # SPC 가 255틱(1.27초, 76프레임) 뒤 놓으므로 그 안에 문턱이 와야 한다
HOLD_ARRIVAL_BYTES_PER_FRAME = 126  # 붙드는 동안(그 곡을 처리하지 않음) 실측
BRR_HEADER_BYTES = 9  # 자원 [길이 2][반복 2][ADSR1][ADSR2][GAIN][음높이 2] 는 DIR 자리에 오르지 않는다


def hold_units(size, notes, rate, base_midi, bytes_per_frame=HOLD_BYTES_PER_FRAME):
    """붙든 샘플을 몇 x 256 바이트 받은 뒤 곡을 나아가게 할지. notes 는 곡이 나아간 뒤의 [(초, MIDI 음)].

    받은 끝은 X + v t, 음 j 의 재생 자리는 t_j 부터 P_j (t - t_j) 로 늘어 샘플 끝(size)에서 반복 구간으로 돌아간다
    (반복 구간은 끝보다 앞이라 그때는 이미 받음). 끝에 닿는 순간이 가장 빠듯하므로 X >= size (1 - v / P_j) - v t_j.
    SPC 는 받은 바이트를 위 바이트 차로 재 255바이트까지 많게 보므로 한 단위를 더한다.
    """
    need = 0.0
    for seconds, midi in notes:
        frames = seconds * FRAME_RATE
        if frames * bytes_per_frame >= size:
            continue
        speed = rate * 2 ** ((midi - base_midi) / 12) * 9 / 16 / FRAME_RATE
        need = max(need, size * (1 - bytes_per_frame / speed) - bytes_per_frame * frames)
    return math.ceil(need / 256) + 1


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


def transfer_plan(first_tick, notes, sizes, pre_bytes, lead_bytes=0):
    """곡 묶음의 샘플 순서·곡 앞 샘플 수 k·곡 뒤 샘플의 도착 어림(곡 시작부터 초)을 정한다.

    먼저 쓰이는 샘플(같으면 음이 많은 것)부터 늘어놓고, 앞에서부터 pre_bytes 안에 드는 만큼을
    곡 앞(시퀀스와 함께 곡을 틀기 전에 보냄)으로, 나머지는 곡이 울리는 동안 이 순서로 보낸다. lead_bytes 는 곡이 시작한
    뒤 샘플보다 먼저 보내는 바이트(나눈 곡의 본체 시퀀스)다.
    """
    order = sorted(sizes, key=lambda s: (first_tick[s], -notes[s], s))
    k, used = 0, 0
    while k < len(order) and used + sizes[order[k]] <= pre_bytes:
        used += sizes[order[k]]
        k += 1
    arrivals, sent = {}, lead_bytes
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


def song_score(score, drop_tracks=(), drop_programs=(), track_db=None):
    """drop_tracks(트랙 이름)·drop_programs 의 음을 빼고, track_db({트랙 또는 트랙@프로그램: dB}) 음의 세기를 바꾼 악보."""
    if not drop_tracks and not drop_programs and not track_db:
        return score
    gain = {ch: 10 ** (db / 20) for ch, db in (track_db or {}).items()}
    timeline = []
    for e in score['timeline']:
        if e.get('op') == 'note':
            if e['ch'] in drop_tracks or e['program'] in drop_programs:
                continue
            g = gain.get(f"{e['ch']}@{e['program']}", gain.get(e['ch']))
            if g is not None:
                e = e | {'velocity': max(1, min(127, round(e['velocity'] * g)))}
        timeline.append(e)
    return score | {'timeline': timeline}


def build(base, assets, songs, *, cache_dir, max_rate=8000, max_samples=14, map_fades=False, preview=None,
          stream=None, stream_ticks=None, budgets=None, pinned=(), resident_from=None, drop_resident=(), lanes=None, drop_tracks=None,
          level_db=None, programs=None, set_records=None, keep_regions=None, track_db=None,
          fast_receive=False, chains=(), holds=(), early_song=False, load_pump=False, vehicle_song=False):
    """stream 은 {곡 자리: 곡 앞 샘플 바이트 상한}. 그 곡은 샘플 일부를 곡이 울리는 동안 보낸다(transfer_plan).

    stream_ticks 는 {곡 자리: 틱}. 곡 앞 바이트 상한을 곡이 처음 그 틱 안에 쓰는 샘플의 합으로 정하고, 도착 어림보다
    먼저 쓰여 빠지는 음이 남으면 다음 샘플을 곡 앞에 더한다.

    budgets 는 {곡 자리: 샘플 예산 바이트}. 주면 시퀀스 크기로 정한 예산 대신 이 값으로 샘플을 줄인다. 시퀀스가
    작아져도 청취 승인한 샘플(줄이기 결과)을 그대로 두려면 그때의 예산을 준다. SPC 예산 검사는 install 이 그대로 한다.

    pinned 는 늘 두는 시퀀스 목록에 남길 바꾸는 곡. resident_from 은 stream 을 준 곡 하나로, 그 곡의 곡 앞 샘플을
    늘 두는 샘플 목록 끝에 더한다(drop_resident 는 원래 목록에서 뺄 샘플). 늘 두는 곡은 2B 로더가 곡 앞 전송을
    건너뛰므로, 늘 두지 않은 샘플은 모두 곡이 울리는 동안 온다. 늘 두는 샘플을 함께 쓰는 곡은 그 바이트를 예산에
    돌려받아 한 번 더 줄이고, 샘플 칸(늘 두는 것과 합쳐 0x14)이 넘치면 곡의 샘플 수를 줄여 다시 만든다.
    lanes·drop_tracks·level_db 는 곡마다 convert 의 lanes_for·뺄 트랙·level_tolerance_db, programs 는
    {곡: {프로그램: 이미 넣은 전역 샘플}} 로 그 프로그램을 새로 만들지 않고 그 샘플로 울린다. keep_regions 는
    {곡: {프로그램}} 으로 샘플을 줄일 때 그 프로그램의 음역 영역을 합치지 않는다. track_db 는 {곡: {트랙: dB}} 로
    그 트랙 음의 세기(velocity)를 바꾼다. chains 는 앞부분·본체로 나눌 곡 자리(stream_ticks 를 준 곡)로, 앞부분 길이는
    본체 도착 어림 + CHAIN_SLACK_SECONDS 로 정한다. holds 는 곡 붙들기를 쓸 곡 자리(stream_ticks 를 준 곡)로, 곡 앞
    샘플 하나를 곡 뒤 맨 앞으로 돌리고 그 샘플이 hold_units 만큼 오면 곡을 나아가게 한다(아끼는 바이트가 가장 큰 것).
    set_records 는 바꾸지 않는 곡의 곡 묶음 레코드(install 과 같음). cache_dir 는 BRR(brr/)·시퀀스 묶기(compact/) 결과를
    두는 곳으로, 키가 입력과 도구 소스의 해시라 다른 워크트리와 함께 써도 된다.
    """
    stream, stream_ticks, budgets, lanes = stream or {}, stream_ticks or {}, budgets or {}, lanes or {}
    drop_tracks, level_db, programs = drop_tracks or {}, level_db or {}, programs or {}
    keep_regions, track_db = keep_regions or {}, track_db or {}
    brr_cache = None if cache_dir is None else Path(cache_dir) / 'brr'
    data = bytes(base)
    records = patch.read_sets(data)
    if len({slot for slot, _ in songs}) != len(songs):
        raise ValueError('each DQ5 slot may be replaced once')
    replaced = {slot for slot, _ in songs}
    if resident_from is not None and (resident_from not in stream or resident_from not in budgets):
        raise ValueError('the resident_from song must be streamed and have a fixed budget')
    resident_plan = bool(pinned or resident_from is not None or drop_resident)

    def convert_args(slot):
        return {'lanes_for': lanes.get(slot), 'level_tolerance_db': level_db.get(slot, 1.0), 'cache_dir': cache_dir}

    if not set(chains) <= set(stream_ticks):
        raise ValueError('chained songs must use stream_ticks')
    chain_numbers = {slot: patch.FIRST_CHAIN_SONG + i for i, slot in enumerate(sorted(chains))}
    replacements, resources, reports, known, mains, chain_late = {}, {}, {}, {}, {}, set()
    next_id = 0x26
    plans = []
    for slot, ident in songs:
        path = score_path(assets, ident)
        score = song_score(json.loads(path.read_text()), drop_tracks.get(slot, ()), track_db=track_db.get(slot))
        mapping, regions = provisional_map(score)
        plans.append((slot, ident, path, score,
                      len(port.convert(score, program_map=mapping, **convert_args(slot)).sequence),
                      min(regions, max_samples)))
    # 표는 모든 곡을 넣은 뒤의 길이로 늘어나므로, 곡마다 예산에 전체 증가분을 쓴다.
    growth = sum(2 + slots - (len(records[slot]) if slot < len(records) else 0) for slot, _, _, _, _, slots in plans)
    if chains or any(slot >= patch.NEW_SONG_FIRST for slot, _ in songs):
        # 빈 번호 레코드(2바이트씩)·나눈 곡 본체 레코드(3바이트씩)·SPC 판정 도우미
        top = max([patch.FIRST_CHAIN_SONG + len(chains)] if chains else []
                  + [slot + 1 for slot, _ in songs if slot >= patch.NEW_SONG_FIRST])
        growth += 2 * (top - len(records)) + len(chains) + len(patch.SPC_EFFECT_HELPER)
    resident = [x for x in patch.resident_samples(data) if x not in drop_resident]
    resident_sizes = {x: patch.sample_size(data, x) for x in resident}
    resident_done = resident_from is None
    pinned_sizes = {x: len(patch.sequence_bytes(data, x)) for x in patch.pinned_sequences(data) if x not in replaced}
    pinned_sizes |= {slot: size + MARGIN for slot, _, _, _, size, _ in plans if slot in pinned}

    def make_bank(score, budget, limit, loose, overrides, keep=()):
        bank_score = song_score(score, drop_programs=set(overrides))
        if not bank.used_regions(bank_score)[0]:
            report = {'samples': {}, 'sample_count': 0, 'reductions': []}
            return {}, {}, report, [], dict(known)
        snapshot = dict(known)
        try:
            found, program_map, report = bank.build_bank(bank_score, assets, start_id=0x26, max_rate=max_rate,
                                                         cache_dir=brr_cache, budget=budget, max_samples=limit,
                                                         keep_regions=keep)
        except ValueError as exc:
            if 'cannot fit samples' not in str(exc):
                raise
            found, program_map, report = bank.build_bank(bank_score, assets, start_id=0x26, max_rate=max_rate,
                                                         cache_dir=brr_cache, budget=budget, max_samples=limit,
                                                         rates=bank.LOW_RATES, keep_regions=keep)
            report['low_rates'] = True
        found, program_map, _, shared = share_samples(found, report['samples'], program_map, resources, known,
                                                      next_id, budget=budget, loose=loose)
        report['samples'] = {f'{x:02X}': known[x][3] for x in sorted(found)}
        return found, program_map, report, shared, snapshot

    for slot, ident, path, score, sequence_size, _ in plans:
        if slot not in budgets and not resident_done:
            raise ValueError('songs without a fixed budget must come after the resident_from song')
        overrides = programs.get(slot, {})
        if any(x not in resources for x in overrides.values()):
            raise ValueError(f'{slot:02X}: program overrides must name samples of earlier songs')
        if slot in budgets:
            budget = budgets[slot]
        elif resident_plan:
            budget = patch.sample_budget(data, slot, sequence_size + MARGIN + (CHAIN_INTRO_BYTES if slot in chains else 0),
                                         extra_table=max(0, growth), resident=resident_sizes, pinned=pinned_sizes)
        else:
            budget = patch.sample_budget(data, slot, sequence_size + MARGIN, extra_table=max(0, growth))
        limit, rebate, settle = max_samples, 0, False
        for attempt in range(5):
            found, program_map, bank_report, loose, snapshot = make_bank(score, budget + rebate, limit,
                                                                         slot not in budgets, overrides,
                                                                         keep_regions.get(slot, ()))
            program_map |= {p: [{'lo': 0, 'hi': 127, 'sample': x}] for p, x in overrides.items()}
            conversion = port.convert(score, program_map=program_map, **convert_args(slot))
            if not resident_done or slot in budgets:
                break
            used = set(conversion.samples)
            shared_resident = sum(resident_sizes[x] for x in used & set(found) if x in resident_sizes)
            over = len(used | set(resident)) - patch.SAMPLE_SLOTS
            if over <= 0 and (shared_resident == rebate or settle):
                break
            if over <= 0 and attempt >= 2:
                # 돌려받은 예산으로 늘 두는 샘플을 함께 쓰지 않게 되고, 돌려받지 않으면 다시 함께 쓰며 오갔다(곡 04).
                # 예산을 넘기지 않는 쪽(돌려받지 않음)으로 정한다.
                known.clear()
                known.update(snapshot)
                rebate, settle = 0, True
                continue
            if attempt == 4 or (over > 0 and len(found) <= over):
                raise ValueError(f'{slot:02X}: cannot settle resident sharing ({shared_resident} bytes, rebate {rebate}) '
                                 f'and sample slots ({over} over); map programs to resident samples with --program')
            known.clear()
            known.update(snapshot)
            rebate = shared_resident
            if over > 0:
                limit = len(found) - over
        bank_report['samples_limit'] = limit
        bank_report['resident_rebate'] = rebate
        bank_report['shared_samples'] = sorted(f'{x:02X}' for x in found if x in resources)
        bank_report['shared_other_rate'] = loose
        bank_report['resource_bytes'] = sum(map(len, found.values()))
        send_first, plan = None, None
        if slot in stream or slot in stream_ticks:
            if set(conversion.samples) - found.keys():
                raise ValueError('streamed songs must use only their own converted samples')
            usage = conversion.report
            first = {int(k, 16): v for k, v in usage['sample_first_tick'].items()}
            notes = {int(k, 16): v for k, v in usage['sample_notes'].items()}
            sizes = {x: len(found[x]) for x in conversion.samples}
            cap0 = stream[slot] if slot in stream else sum(sizes[x] for x in conversion.samples
                                                           if first[x] <= stream_ticks[slot])
            plain = conversion
            tempos = dict(plain.report['tempo_changes'])

            def stream_plan(lead, split):
                cap = cap0
                while True:
                    order, send_first, arrivals = transfer_plan(first, notes, sizes, cap, lead_bytes=lead)
                    result = port.convert(score, program_map=program_map, sample_order=order, arrivals=arrivals,
                                          **convert_args(slot), **split)
                    # stream_ticks 곡은 도착 전이라 빠지는 음이 없을 때까지 곡 앞 샘플을 하나씩 늘린다(빠진 음은 어색하게 들림)
                    if (slot not in stream_ticks or send_first == len(order)
                            or not any(result.report['late_notes'].values())):
                        return cap, order, send_first, arrivals, result
                    cap = sum(sizes[x] for x in order[:send_first + 1])

            def split_at(sent_bytes):
                seconds = (sent_bytes / STREAM_BYTES_PER_FRAME + ARRIVAL_SLACK_FRAMES) / FRAME_RATE + CHAIN_SLACK_SECONDS
                tick = min(port.seconds_to_tick(tempos, seconds), plain.report['end_tick'] - 1)
                return {'split_tick': tick, 'chain_song': chain_numbers[slot]}

            def hold_plan(late, order, send_first, arrivals, conversion):
                """곡 붙들기를 걸 수 있으면 건 계획과, 소리 나기 전에 받아야 할 붙든 샘플 바이트(본체가 먼저면 본체 포함)."""
                held, wait = None, 0
                if slot not in holds or not send_first:
                    return order, send_first, arrivals, conversion, held, wait
                main = len(plain.sequence)
                # 본체를 먼저 보내는 나눈 곡은 붙든 샘플이 본체 뒤에 온다
                lead = main if slot in chains and not late else 0
                timed = check.expected_notes(conversion.sequence, port.seconds_to_tick(tempos, 30), conversion.chain)
                details = bank_report['samples']
                first_seconds = {}
                for track in timed:
                    for t, _, i in track:
                        first_seconds[conversion.samples[i]] = min(t, first_seconds.get(conversion.samples[i], math.inf))
                candidates = []
                for x in order[:send_first]:
                    detail = details.get(f'{x:02X}')
                    if detail is None:
                        continue
                    index = conversion.samples.index(x)
                    notes_x = [(t, n + 23) for track in timed for t, n, i in track if i == index]
                    units = hold_units(sizes[x] - BRR_HEADER_BYTES, notes_x, detail['effective_rate'], detail['base_midi'])
                    # 붙드는 동안 받는 바이트가 많을수록 곡 뒤 샘플이 일찍 온다. 곡 뒤 샘플이 처음 쓰이기 전에 오도록 문턱을 키운다
                    # (곡이 울리면 SPC 가 곡을 처리하느라 받기가 반쯤 느려지지만, 붙드는 동안은 그 곡을 처리하지 않는다).
                    sent = lead + sizes[x]
                    for y in order[send_first:]:
                        sent += sizes[y]
                        if y not in first_seconds:
                            continue
                        need = sent - (first_seconds[y] * FRAME_RATE - ARRIVAL_SLACK_FRAMES) * STREAM_BYTES_PER_FRAME
                        units = max(units, math.ceil(need / 256) + 1)
                    if (lead + units * 256) / HOLD_ARRIVAL_BYTES_PER_FRAME > HOLD_TIMEOUT_FRAMES:
                        continue
                    candidates.append((sizes[x] - lead - units * 256, x, units))
                if candidates and max(candidates)[0] > 0:
                    _, x, units = max(candidates)
                    new_order = [y for y in order[:send_first] if y != x] + [x] + list(order[send_first:])
                    new_first = send_first - 1
                    # 붙들기가 풀릴 때 SPC 는 문턱보다 255바이트까지 덜 받았을 수 있다
                    sent, new_arrivals = lead + sizes[x] - (units - 1) * 256, {}
                    for y in new_order[new_first + 1:]:
                        sent += sizes[y]
                        new_arrivals[y] = (sent / STREAM_BYTES_PER_FRAME + ARRIVAL_SLACK_FRAMES) / FRAME_RATE
                    split = {}
                    if slot in chains:
                        after = sum(sizes[y] for y in new_order[new_first:])
                        split = split_at(after + main) if late else split_at(main)
                    result = port.convert(score, program_map=program_map, sample_order=new_order, arrivals=new_arrivals,
                                          hold=(x, units), **convert_args(slot), **split)
                    if not any(result.report['late_notes'].values()):
                        order, send_first, arrivals, conversion = new_order, new_first, new_arrivals, result
                        held = {'sample': f'{x:02X}', 'bytes': units * 256, 'saved_bytes': max(candidates)[0]}
                        wait = lead + units * 256
                return order, send_first, arrivals, conversion, held, wait

            if slot in chains:
                # 본체를 곡 뒤 샘플보다 먼저(곧 쓸 샘플이 곡 앞으로 당겨짐) 또는 나중(앞부분이 길어짐) 보내는 두 길 중
                # 소리가 나기 전에 받을 바이트(곡 앞 샘플 + 앞부분 시퀀스 + 붙든 샘플의 문턱)가 적은 쪽을 고른다.
                # 붙들기를 빼고 견주면 본체를 먼저 보내는 쪽이 붙들기를 못 걸어 오히려 늦었다(보스 18 +125 → +113).
                main = len(plain.sequence)
                options = []
                cap, order, send_first, arrivals, result = stream_plan(main, split_at(main))
                options.append((False, cap, order, send_first, arrivals, result))
                cap, order, send_first, arrivals, _ = stream_plan(0, {})
                after = sum(sizes[x] for x in order[send_first:])
                late_split = split_at(after + main)
                result = port.convert(score, program_map=program_map, sample_order=order, arrivals=arrivals,
                                      **convert_args(slot), **late_split)
                options.append((True, cap, order, send_first, arrivals, result))
                planned = []
                for late, cap, order, send_first, arrivals, result in options:
                    order, send_first, arrivals, result, held, wait = hold_plan(late, order, send_first, arrivals, result)
                    cost = sum(sizes[x] for x in order[:send_first]) + len(result.sequence) + wait
                    planned.append((cost, late, cap, order, send_first, arrivals, result, held))
                _, late, cap, order, send_first, arrivals, conversion, held = min(planned, key=lambda o: o[0])
                if late:
                    chain_late.add(slot)
            else:
                cap, order, send_first, arrivals, conversion = stream_plan(0, {})
                order, send_first, arrivals, conversion, held, _ = hold_plan(False, order, send_first, arrivals, conversion)
            plan = {'pre_bytes_cap': cap, 'send_first': send_first, 'chain_after_samples': slot in chain_late, 'hold': held,
                    'pre_sample_bytes': sum(len(found[s]) for s in order[:send_first]),
                    'arrival_seconds': {f'{s:02X}': round(t, 3) for s, t in arrivals.items()}}
            if slot == resident_from:
                resident += order[:send_first]
                resident_sizes |= {x: len(found[x]) for x in order[:send_first]}
                resident_done = True
        if slot in pinned:
            pinned_sizes[slot] = len(conversion.sequence)
        replacements[slot] = patch.Replacement(conversion.sequence, tuple(conversion.samples), send_first)
        if conversion.chain is not None:
            mains[slot] = conversion.chain
        resources.update(found)
        next_id = max(resources) + 1
        print(f'{slot:02X} <- NDS {ident.upper()}: {len(found)} samples ({len(bank_report["shared_samples"])} shared), '
              f'sequence {len(conversion.sequence)}', file=sys.stderr, flush=True)
        reports[f'{slot:02X}'] = {'nds_song': ident.upper(), 'score': path.name, 'sample_budget': budget,
                                   'bank': bank_report, 'conversion': conversion.report, 'stream': plan}
    if sorted(mains) != sorted(chains):
        raise ValueError('every chained song must be a replaced song (install numbers the bodies in slot order)')
    rom, install_report = patch.install(base, replacements, sample_resources=resources, map_fades=map_fades,
                                        preview=preview, pinned=tuple(pinned),
                                        resident=resident if resident_plan else None, set_records=set_records,
                                        fast_receive=fast_receive, chains=mains, chain_late=chain_late,
                                        hold=bool(holds), early_song=early_song, load_pump=load_pump,
                                        vehicle_song=vehicle_song)
    # 바꾸지 않은 DQ5 곡도 늘 두는 목록이 바뀐 뒤의 SPC 에 드는지 본다. 넘치는 곡은 그 까닭을 남긴다.
    sets, unreplaced = patch.read_sets(rom), {}
    for song in range(1, 0x32):
        if song in replaced:
            continue
        try:
            unreplaced[f'{song:02X}'] = patch.memory_budget(
                rom, song, patch.Replacement(patch.sequence_bytes(rom, song), tuple(dict.fromkeys(sets[song][2:]))))
        except ValueError as exc:
            unreplaced[f'{song:02X}'] = {'error': str(exc)}
    install_report['unreplaced_songs'] = unreplaced
    return rom, {'install': install_report, 'songs': reports}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 fromfile_prefix_chars='@')
    ap.add_argument('--base', type=Path, required=True)
    ap.add_argument('--assets', type=Path, required=True)
    ap.add_argument('--song', action='append', required=True, metavar='DQ5_SLOT=NDS_ID')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--cache-dir', type=Path,
                    help='BRR and sequence compaction cache (default: ASSETS/sfc/dq4/cache/sound, keyed by input and tool source hashes)')
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
    ap.add_argument('--stream-ticks', action='append', default=[], metavar='DQ5_SLOT=TICKS',
                    help='like --stream, sending first the samples the song uses within its first TICKS ticks and any '
                         'sample that would otherwise arrive after its first note')
    ap.add_argument('--pin', action='append', default=[], metavar='DQ5_SLOT',
                    help='keep this replaced song in the resident sequence list')
    ap.add_argument('--resident-from', metavar='DQ5_SLOT',
                    help='add the samples this streamed song sends before it starts to the resident sample list')
    ap.add_argument('--drop-resident', action='append', default=[], metavar='SAMPLE',
                    help='remove this sample from the original resident sample list')
    ap.add_argument('--lanes', action='append', default=[], metavar='DQ5_SLOT=JSON',
                    help='pin NDS tracks to voices, e.g. 17=\'{"track0": [0]}\'')
    ap.add_argument('--drop-track', action='append', default=[], metavar='DQ5_SLOT=TRACK')
    ap.add_argument('--level-db', action='append', default=[], metavar='DQ5_SLOT=DB',
                    help='merge volume changes within DB (default 1)')
    ap.add_argument('--program', action='append', default=[], metavar='DQ5_SLOT=PROGRAM:SAMPLE',
                    help='play this NDS program with an already built sample (hex ID) instead of its own')
    ap.add_argument('--keep-regions', action='append', default=[], metavar='DQ5_SLOT=PROGRAM',
                    help='never merge the key regions of this NDS program when shrinking samples')
    ap.add_argument('--track-db', action='append', default=[], metavar='DQ5_SLOT=TRACK:DB',
                    help='scale the note velocity of one NDS track (or TRACK@PROGRAM), e.g. 09=track6:-4 or 09=track8@45:-6')
    ap.add_argument('--fast-receive', action='store_true',
                    help='let the SPC driver take several 3-byte groups per handshake loop (dq4soundpatch.fast_receive_code)')
    ap.add_argument('--chain', action='append', default=[], metavar='DQ5_SLOT',
                    help='split this streamed song into a short intro and a main sequence sent after it starts')
    ap.add_argument('--early-song', action='store_true',
                    help='request the destination map song before the exit fade-out (dq4soundpatch.early_song_code)')
    ap.add_argument('--vehicle-song', action='store_true',
                    help='keep the playing field song when dismounting the dragon instead of resending it (dq4soundpatch.vehicle_song_code)')
    ap.add_argument('--load-pump', action='store_true',
                    help='keep sending the early song data while NMI is off during map loads (dq4soundpatch.load_pump_code)')
    ap.add_argument('--hold', action='append', default=[], metavar='DQ5_SLOT',
                    help='start this streamed song while its last early sample is still arriving (dq4soundpatch.hold_check_code)')
    ap.add_argument('--record', action='append', default=[], metavar='DQ5_SLOT=K:SAMPLE,...',
                    help='song set record of an unreplaced song')
    args = ap.parse_args()
    songs = []
    for value in args.song:
        slot, ident = value.split('=', 1)
        songs.append((int(slot, 16), ident))
    base = args.base.read_bytes()
    stream = {int(slot, 16): int(cap) for slot, cap in (value.split('=', 1) for value in args.stream)}
    budgets = {int(slot, 16): int(value) for slot, value in (item.split('=', 1) for item in args.budget)}

    def per_slot(items):
        return [(int(slot, 16), value) for slot, value in (item.split('=', 1) for item in items)]

    drop_tracks, programs, records = {}, {}, {}
    for slot, track in per_slot(args.drop_track):
        drop_tracks.setdefault(slot, set()).add(track)
    for slot, value in per_slot(args.program):
        program, sample = value.split(':')
        programs.setdefault(slot, {})[int(program)] = int(sample, 16)
    keep, track_db = {}, {}
    for slot, value in per_slot(args.track_db):
        track, db = value.split(':')
        track_db.setdefault(slot, {})[track] = float(db)
    for slot, value in per_slot(args.keep_regions):
        keep.setdefault(slot, set()).add(int(value))
    for slot, value in per_slot(args.record):
        first, ids = value.split(':')
        records[slot] = (int(first), *(int(x, 16) for x in ids.split(',')))
    rom, report = build(base, args.assets, songs, cache_dir=args.cache_dir or args.assets / 'sfc/dq4/cache/sound', max_rate=args.max_rate,
                        max_samples=args.max_samples, map_fades=args.map_fades, preview=args.preview, stream=stream,
                        stream_ticks={slot: int(v) for slot, v in per_slot(args.stream_ticks)},
                        budgets=budgets, pinned=[int(x, 16) for x in args.pin],
                        resident_from=int(args.resident_from, 16) if args.resident_from else None,
                        drop_resident=[int(x, 16) for x in args.drop_resident],
                        lanes={slot: json.loads(value) for slot, value in per_slot(args.lanes)},
                        drop_tracks=drop_tracks, level_db={slot: float(v) for slot, v in per_slot(args.level_db)},
                        programs=programs, set_records=records, keep_regions=keep,
                        track_db=track_db, fast_receive=args.fast_receive,
                        chains=[int(x, 16) for x in args.chain], holds=[int(x, 16) for x in args.hold],
                        early_song=args.early_song, load_pump=args.load_pump,
                        vehicle_song=args.vehicle_song)
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
    print(json.dumps({'heap_start': report['install']['heap_start'],
                      'resident_samples': report['install']['resident_samples'],
                      'pinned_sequences': report['install']['pinned_sequences'],
                      'unreplaced_over_budget': sorted(k for k, v in report['install']['unreplaced_songs'].items()
                                                       if 'error' in v),
                      'songs': summary}, indent=2))


if __name__ == '__main__':
    main()
