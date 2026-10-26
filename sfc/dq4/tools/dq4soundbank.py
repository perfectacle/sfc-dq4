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
ENCODER_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


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


def convert_sample(path, region, *, max_rate=12000, cache_dir=None):
    pcm, rate, loop = read_wave(path)
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


def build_bank(score, asset_root, *, start_id=0x26, max_rate=12000, cache_dir=None):
    """(resources, program_map, report). sample은 DQ5 전역 번호. PCM 이외는 거부한다."""
    if not 0x26 <= start_id < 0xC8:
        raise ValueError('custom sample IDs must start in 26..C7')
    root = Path(asset_root)
    samples = root / 'nds/dq4/sound/samples'
    resources, mapping, details, reused = {}, {}, {}, {}
    for program, instrument in sorted(score['instruments'].items(), key=lambda p: int(p[0])):
        notes = [e['note'] for e in score['timeline'] if e.get('op') == 'note' and e.get('program') == int(program)]
        mapping[int(program)] = []
        for region in instrument['regions']:
            if not any(region['lo'] <= n <= region['hi'] for n in notes):
                continue
            if region['type'] != 'PCM':
                raise ValueError(f'unsupported instrument program {program}: {region["type"]}')
            path = samples / region['sample']
            if not path.resolve().is_relative_to(samples.resolve()):
                raise ValueError('sample path outside asset root')
            identity = (region['sample'], region['base'], approximate_adsr(region))
            if identity not in reused:
                identifier = start_id + len(resources)
                if identifier >= 0xC8:
                    raise ValueError('sample ID table exhausted')
                resource, detail = convert_sample(path, region, max_rate=max_rate, cache_dir=cache_dir)
                resources[identifier], details[f'{identifier:02X}'] = resource, detail
                reused[identity] = identifier
            mapping[int(program)].append({'lo': region['lo'], 'hi': region['hi'], 'sample': reused[identity]})
    return resources, mapping, {
        'samples': details, 'sample_count': len(resources),
        'resource_bytes': sum(map(len, resources.values())),
        'spc_brr_bytes': sum(d['brr_bytes'] for d in details.values()),
        'runtime_verified': False,
        'limitations': ['ADSR parameter approximation', 'release supplied by sequence',
                        'SPC memory and sample slots require runtime budget validation'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--score', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--max-rate', type=int, default=12000)
    parser.add_argument('--start-id', type=lambda s: int(s, 16), default=0x26)
    args = parser.parse_args()
    resources, mapping, report = build_bank(json.loads(args.score.read_text()), args.assets,
                                           start_id=args.start_id, max_rate=args.max_rate,
                                           cache_dir=args.out / 'cache')
    args.out.mkdir(parents=True, exist_ok=True)
    for identifier, resource in resources.items():
        (args.out / f'{identifier:02X}.bin').write_bytes(resource)
    (args.out / 'program-map.json').write_text(json.dumps(mapping, indent=2) + '\n')
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'samples'}))


if __name__ == '__main__':
    main()
