"""NDS 악보의 PCM 악기를 DQ5 BRR 샘플로 만든다. 출력은 work/에 둔다.

피치식: dq4-overture-format.md 「시간과 음높이」, DQ5 SPC 1B73.
NDS ADSR과 SPC ADSR의 시간 곡선은 다르므로 엔벨로프는 명시적인 근사다.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import wave

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'sfc/dq5/tools'))
import dq5brr  # noqa: E402
import dq5brrenc as brr  # noqa: E402

PITCH_C = 8372  # DQ5 SPC 07E5 표의 C. 음 n=1일 때 표의 두 번째 원소를 쓴다.
ENCODER_HASH = hashlib.sha256(Path(__file__).read_bytes() + Path(dq5brr.__file__).read_bytes()).hexdigest()


def hw_sample(nib, shift, filt, p1, p2):
    """S-DSP 의 BRR 표본 하나(dq5brr.decode 와 같은 계산). p1·p2 와 결과는 16비트 짝수 값.

    16비트로 자른 뒤 1비트 밀기라 넘치면 부호가 뒤집힌다. dq5brrenc 는 15비트로 자른다고 보아
    큰 진폭에서 실기와 다른 표본을 골랐다(음마다 같은 자리의 딸깍 소리와 잡음).
    """
    s = nib - 16 if nib >= 8 else nib
    s = (s << shift) >> 1 if shift <= 12 else (-2048 if s < 0 else 0)
    half = p2 >> 1
    if filt == 1:
        s += (p1 >> 1) + ((-p1) >> 5)
    elif filt == 2:
        s += p1 - half + (half >> 4) + ((p1 * -3) >> 6)
    elif filt == 3:
        s += p1 - half + ((p1 * -13) >> 7) + ((half * 3) >> 4)
    s = (max(-0x8000, min(0x7FFF, s)) << 1) & 0xFFFF
    return s - 0x10000 if s & 0x8000 else s


def _hw_block(target, p1, p2, filters):
    best = None
    for filt in filters:
        for shift in range(13):
            q1, q2, nibs, err = p1, p2, [], 0
            for x in target:
                e, nib, out = min(((hw_sample(n, shift, filt, q1, q2) - x) ** 2, n, hw_sample(n, shift, filt, q1, q2))
                                  for n in range(16))
                err += e
                nibs.append(nib)
                q2, q1 = q1, out
                if best is not None and err >= best[0]:
                    break
            else:
                if best is None or err < best[0]:
                    best = (err, filt, shift, nibs, q1, q2)
    return best


def encode_hw(pcm, loop=None):
    """15비트 PCM → BRR. 표본마다 실기 디코드 결과로 오차를 잰다. loop 는 반복 시작 표본(16의 배수) 또는 None."""
    target = [2 * max(-16384, min(16383, int(x))) for x in pcm]
    target += [0] * (-len(target) % 16)
    if loop is not None and loop % 16:
        raise ValueError('loop must be a multiple of 16')
    out, p1, p2 = bytearray(), 0, 0
    count = len(target) // 16
    for i in range(count):
        first = i == 0 or (loop is not None and i * 16 == loop)
        _, filt, shift, nibs, p1, p2 = _hw_block(target[i * 16:i * 16 + 16], p1, p2, (0,) if first else (0, 1, 2, 3))
        head = shift << 4 | filt << 2
        if loop is not None:
            head |= 2
        if i == count - 1:
            head |= 1
        out.append(head)
        out += bytes(nibs[k] << 4 | nibs[k + 1] for k in range(0, 16, 2))
    return bytes(out)


def hw_snr(pcm, encoded):
    """실기 디코드(가우스 보간 전) 대 15비트 PCM 의 SNR(dB)."""
    decoded = np.array(dq5brr.decode(encoded)[0][:len(pcm)], dtype=float) / 2
    reference = np.asarray(pcm, dtype=float)[:len(decoded)]
    noise = ((decoded - reference) ** 2).sum()
    return float('inf') if not noise else 10 * math.log10((reference ** 2).sum() / noise)


def read_wave(path):
    data = path.read_bytes()
    loop = None
    offset = 12
    while offset + 8 <= len(data):
        tag, size = data[offset:offset + 4], struct.unpack_from('<I', data, offset + 4)[0]
        body = data[offset + 8:offset + 8 + size]
        if tag == b'smpl' and len(body) >= 60 and struct.unpack_from('<I', body, 28)[0]:
            loop_type, start, end = struct.unpack_from('<III', body, 40)
            if loop_type != 0:
                raise ValueError('forward WAV loop만 지원')
            loop = (start, end + 1)
        offset += 8 + size + (size & 1)
    with wave.open(str(path)) as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError('16-bit mono WAV 필요')
        rate = wav.getframerate()
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').astype(float) / 2
    if loop is not None and not 0 <= loop[0] < loop[1] <= len(pcm):
        raise ValueError('WAV loop 범위 오류')
    return pcm, rate, loop


def resample_segment(pcm, length, periodic=False):
    if length == 0:
        return np.empty(0)
    ratio = length / len(pcm)
    cutoff = min(1.0, ratio) * 0.94
    positions = np.arange(length) / ratio
    centers = np.floor(positions).astype(int)
    offsets = np.arange(-31, 33)
    indices = centers[:, None] + offsets[None, :]
    distances = positions[:, None] - indices
    weights = cutoff * np.sinc(cutoff * distances) * np.maximum(0, 0.5 + 0.5 * np.cos(np.pi * distances / 32))
    weights[np.abs(distances) >= 32] = 0
    indices = indices % len(pcm) if periodic else np.clip(indices, 0, len(pcm) - 1)
    return (pcm[indices] * weights).sum(axis=1) / weights.sum(axis=1)


def prepare_pcm(pcm, rate, loop, max_rate):
    if max_rate <= 0 or not len(pcm):
        raise ValueError('양수 표본율과 비어 있지 않은 PCM 필요')
    ratio = min(rate, max_rate) / rate
    if loop is None:
        length = max(16, round(len(pcm) * ratio / 16) * 16)
        return resample_segment(pcm, length), rate * length / len(pcm), None
    start, end = loop
    loop_len = max(16, round((end - start) * ratio / 16) * 16)
    effective_rate = rate * loop_len / (end - start)
    prefix_len = max(16, round(start * effective_rate / rate / 16) * 16) if start else 0
    prefix = resample_segment(pcm[:start], prefix_len) if start else np.empty(0)
    cycle = resample_segment(pcm[start:end], loop_len, periodic=True)
    return np.concatenate((prefix, cycle)), effective_rate, prefix_len


def pitch_word(rate, base):
    # C 기준으로 식을 풀면 어느 MIDI 기본음에서도 같은 값으로 조율된다.
    value = round((4096 * rate / 32000) * 256 * 2 ** (9 - (base - 24) / 12) / PITCH_C)
    if not 1 <= value <= 65535:
        raise ValueError(f'DQ5 샘플 음높이 범위 초과: rate={rate}, base={base}')
    return value


def approximate_adsr(region):
    attack = min(15, max(0, round(region.get('attack', 127) * 15 / 127)))
    decay = min(7, max(0, round(region.get('decay', 127) * 7 / 127)))
    sustain = min(7, max(0, round(region.get('sustain', 127) * 7 / 127)))
    return 0x80 | decay << 4 | attack, sustain << 5


def convert_sample(path, region, *, max_rate=12000, cache_dir=None, seconds=None):
    pcm, rate, loop = read_wave(path)
    if seconds is not None and loop is None:
        # 반복 없는 긴 샘플은 끝을 잘라 짧게 사라지게 한다(꼬리 20% 를 선형으로 줄임).
        pcm = pcm[:int(rate * seconds)].copy()
        fade = max(1, len(pcm) // 5)
        pcm[-fade:] *= np.linspace(1, 0, fade)
    converted, effective_rate, loop_start = prepare_pcm(pcm, rate, loop, max_rate)
    # DQ5 샘플처럼 무음 블록으로 시작한다. KON 직후 보간 버퍼에 앞 음 표본이 남아 첫 블록이 크면 음머리가 튄다.
    converted = np.concatenate((np.zeros(16), np.clip(np.rint(converted), -16384, 16383))).astype('<i2')
    if loop_start is not None:
        loop_start += 16
    key = hashlib.sha256(converted.tobytes() + str(loop_start).encode() + ENCODER_HASH.encode()).hexdigest()
    cache = Path(cache_dir) / (key + '.brr') if cache_dir else None
    hit = cache is not None and cache.is_file()
    encoded = cache.read_bytes() if hit else encode_hw(converted.tolist(), loop_start)
    if cache is not None and not hit:
        cache.parent.mkdir(parents=True, exist_ok=True)
        partial = cache.with_suffix('.tmp')
        partial.write_bytes(encoded)
        partial.replace(cache)
    adsr1, adsr2 = approximate_adsr(region)
    pitch = pitch_word(effective_rate, region['base'])
    result = brr.resource(encoded, (loop_start or 0) // 16, adsr1=adsr1, adsr2=adsr2, pitch=pitch)
    if len(result) - 2 > 65535:
        raise ValueError('샘플 자원 길이 16-bit 초과')
    report = {
        'source': path.name, 'original_samples': len(pcm), 'original_rate': rate,
        'effective_rate': round(effective_rate, 6), 'samples': len(converted),
        'source_loop': list(loop) if loop else None, 'loop_start': loop_start,
        'brr_bytes': len(encoded), 'resource_bytes': len(result), 'pitch': pitch,
        'base_midi': region['base'], 'snr_db': round(hw_snr(converted, encoded), 3),
        'snr_reference': 'S-DSP BRR decode (dq5brr) vs resampled 15-bit PCM, before gaussian interpolation',
        'envelope': {'status': 'linear_parameter_approximation', 'adsr1': adsr1, 'adsr2': adsr2,
                     'nds_attack': region.get('attack'), 'nds_decay': region.get('decay'),
                     'nds_sustain': region.get('sustain'), 'nds_release': region.get('release')},
        'release_policy': 'sequence_release_required',
        'pitch_error_cents': round(1200 * math.log2(pitch / ((4096 * effective_rate / 32000) * 256 *
                                                          2 ** (9 - (region['base'] - 24) / 12) / PITCH_C)), 6),
    }
    return result, report


RATES = (8000, 6000, 4500, 3200)
# 시퀀스가 커서 샘플 예산이 작은 곡이 RATES 로도 들지 않을 때만 쓴다. RATES 에 넣으면 고르는 순서가 바뀌어 다른 곡의 샘플도 달라진다.
LOW_RATES = RATES + (2400,)
ONE_SHOT_SECONDS = (None, 1.2, 0.6)


def used_regions(score):
    """곡에 쓰이는 (프로그램, 영역)과 그 영역에 드는 음 수. NDS 뱅크에 없는 프로그램(None)의 음은 NDS 에서도 소리가 없다."""
    counts = {}
    silent = 0
    for e in score['timeline']:
        if e.get('op') != 'note':
            continue
        instrument = score['instruments'].get(str(e['program']))
        if instrument is None:  # 정의가 없거나 None
            silent += 1
            continue
        for k, region in enumerate(instrument['regions']):
            if region['lo'] <= e['note'] <= region['hi']:
                counts[(e['program'], k)] = counts.get((e['program'], k), 0) + 1
                break
    return counts, silent


def estimate(path, max_rate, seconds):
    """encode 하지 않고 자원 바이트 수를 센다(무음 머리 블록·머리 9바이트 포함)."""
    pcm, rate, loop = read_wave(path)
    if seconds is not None and loop is None:
        pcm = pcm[:int(rate * seconds)]
    converted, _, _ = prepare_pcm(pcm, rate, loop, max_rate)
    return 2 + 7 + (len(converted) + 16 + 15) // 16 * 9


def build_bank(score, asset_root, *, start_id=0x26, max_rate=8000, cache_dir=None, budget=None, max_samples=14,
               rates=RATES, keep_regions=()):
    """(resources, program_map, report). sample은 DQ5 전역 번호.

    budget(바이트)·max_samples(곡 묶음 칸)를 넘으면 손실이 가장 작은 줄이기를 하나씩 고른다.
    쓰이는 음이 적은 영역을 같은 프로그램의 이웃 영역 샘플로 합치기, 표본율 낮추기, 반복 없는 샘플 자르기.
    무엇을 줄였는지는 report['reductions']에 남긴다.
    """
    if not 0x26 <= start_id < 0xC8:
        raise ValueError('custom sample IDs must start in 26..C7')
    root = Path(asset_root)
    samples = root / 'nds/dq4/sound/samples'
    counts, silent = used_regions(score)
    regions = {}
    for (program, k), n in counts.items():
        region = score['instruments'][str(program)]['regions'][k]
        if region['type'] != 'PCM':
            raise ValueError(f'unsupported instrument program {program}: {region["type"]}')
        path = samples / region['sample']
        if not path.resolve().is_relative_to(samples.resolve()):
            raise ValueError('sample path outside asset root')
        regions[(program, k)] = (region, path, n)
    rates = [max_rate] + [r for r in rates if r < max_rate]
    looped = {}

    def has_loop(path):
        if path not in looped:
            looped[path] = read_wave(path)[2] is not None
        return looped[path]

    target = {key: key for key in regions}      # 영역 → 실제로 쓸 영역
    rate, cut = {}, {}                          # identity → 표본율·자르기 단계

    def identity(key):
        region = regions[key][0]
        return region['sample'], region['base'], approximate_adsr(region)

    sizes = {}

    def size(ident, path):
        key = (ident, rate.get(ident, 0), cut.get(ident, 0))
        if key not in sizes:
            seconds = ONE_SHOT_SECONDS[cut.get(ident, 0)]
            sizes[key] = estimate(path, rates[rate.get(ident, 0)], seconds)
        return sizes[key]

    def active():
        out = {}
        for key in set(target.values()):
            out.setdefault(identity(key), regions[key][1])
        return out

    def notes_of(ident):
        return sum(regions[k][2] for k in regions if identity(target[k]) == ident)

    reductions = []
    while True:
        live = active()
        total = sum(size(i, p) for i, p in live.items())
        if len(live) <= max_samples and (budget is None or total <= budget):
            break
        options = []
        for key in set(target.values()):
            program = key[0]
            # keep_regions 의 프로그램은 영역을 합치지 않는다. 한 샘플을 넓은 음역에 늘려 쓰면 오르간처럼 튀었다(곡 04 의 54)
            if program in keep_regions:
                continue
            mates = sorted({target[k] for k in regions if k[0] == program and target[k] != key}, key=lambda m: abs(m[1] - key[1]))
            if not mates:
                continue
            ident = identity(key)
            if sum(1 for k in set(target.values()) if identity(k) == ident) > 1:
                saving = 0
            else:
                saving = size(ident, regions[key][1])
            moved = sum(regions[k][2] for k in regions if target[k] == key)
            options.append((moved * 1.0, max(saving, 1), 'merge', key, mates[0]))  # saving 1 = 칸을 비우지 못함
        for ident, path in live.items():
            if rate.get(ident, 0) + 1 < len(rates):
                before = size(ident, path)
                rate[ident] = rate.get(ident, 0) + 1
                saving = before - size(ident, path)
                rate[ident] -= 1
                options.append((notes_of(ident) * 0.25, max(saving, 1), 'rate', ident, None))
            if not has_loop(path) and cut.get(ident, 0) + 1 < len(ONE_SHOT_SECONDS):
                before = size(ident, path)
                cut[ident] = cut.get(ident, 0) + 1
                saving = before - size(ident, path)
                cut[ident] -= 1
                if saving > 0:
                    options.append((notes_of(ident) * 0.15, saving, 'cut', ident, None))
        if not options:
            raise ValueError(f'cannot fit samples: {len(live)} slots, {total} bytes (budget {budget})')
        need_slots = len(live) > max_samples
        if need_slots:
            # 칸이 모자라면 샘플 하나를 통째로 없애는 합치기만 칸을 줄인다.
            options = [o for o in options if o[2] == 'merge' and o[1] > 1]
            if not options:
                raise ValueError(f'cannot fit samples: {len(live)} slots > {max_samples}')
        options.sort(key=lambda o: o[0] / o[1])
        loss, saving, kind, what, into = options[0]
        if kind == 'merge':
            for k in regions:
                if target[k] == what:
                    target[k] = into
            reductions.append({'merge': f'program {what[0]} region {what[1]} -> region {into[1]}', 'notes': int(loss)})
        elif kind == 'rate':
            rate[what] = rate.get(what, 0) + 1
            reductions.append({'rate': what[0], 'hz': rates[rate[what]], 'notes': notes_of(what)})
        else:
            cut[what] = cut.get(what, 0) + 1
            reductions.append({'cut': what[0], 'seconds': ONE_SHOT_SECONDS[cut[what]], 'notes': notes_of(what)})

    resources, details, ids = {}, {}, {}
    for key in sorted(set(target.values())):
        ident = identity(key)
        if ident in ids:
            continue
        identifier = start_id + len(ids)
        if identifier >= 0xC8:
            raise ValueError('sample ID table exhausted')
        region, path, _ = regions[key]
        resource, detail = convert_sample(path, region, max_rate=rates[rate.get(ident, 0)],
                                          cache_dir=cache_dir, seconds=ONE_SHOT_SECONDS[cut.get(ident, 0)])
        resources[identifier], details[f'{identifier:02X}'] = resource, detail
        ids[ident] = identifier
    mapping = {}
    for (program, k) in sorted(regions):
        region = regions[(program, k)][0]
        mapping.setdefault(program, []).append({'lo': region['lo'], 'hi': region['hi'],
                                                'sample': ids[identity(target[(program, k)])]})
    return resources, mapping, {
        'samples': details, 'sample_count': len(resources),
        'resource_bytes': sum(map(len, resources.values())),
        'spc_brr_bytes': sum(d['brr_bytes'] for d in details.values()),
        'budget': budget, 'max_samples': max_samples, 'reductions': reductions,
        'undefined_program_notes': silent,
        'runtime_verified': False,
        'limitations': ['ADSR parameter approximation', 'release supplied by sequence',
                        'merged regions play another NDS sample of the same program, transposed'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--score', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--max-rate', type=int, default=8000)
    parser.add_argument('--budget', type=int, help='SPC bytes available for this song\'s samples')
    parser.add_argument('--max-samples', type=int, default=14)
    parser.add_argument('--start-id', type=lambda s: int(s, 16), default=0x26)
    args = parser.parse_args()
    resources, mapping, report = build_bank(json.loads(args.score.read_text()), args.assets,
                                           start_id=args.start_id, max_rate=args.max_rate,
                                           budget=args.budget, max_samples=args.max_samples,
                                           cache_dir=args.out / 'cache')
    args.out.mkdir(parents=True, exist_ok=True)
    for identifier, resource in resources.items():
        (args.out / f'{identifier:02X}.bin').write_bytes(resource)
    (args.out / 'program-map.json').write_text(json.dumps(mapping, indent=2) + '\n')
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'samples'}))


if __name__ == '__main__':
    main()
