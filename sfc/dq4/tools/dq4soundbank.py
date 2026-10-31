"""NDS 악보의 PCM 악기를 DQ5 BRR 샘플로 만든다. 출력은 work/에 둔다.

피치식: dq4-overture-format.md 「시간과 음높이」, DQ5 SPC 1B73.
NDS ADSR과 SPC ADSR의 시간 곡선은 다르므로 엔벨로프는 명시적인 근사다.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
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


# S-DSP 엔벨로프 속도 번호(0~31)마다 몇 표본에 한 걸음 가는지. 줄어드는 걸음은 지금 값의 1/256(약 0.034dB).
SNES_RATE_PERIODS = (None, 2048, 1536, 1280, 1024, 768, 640, 512, 384, 320, 256, 192, 160, 128, 96, 80,
                     64, 48, 40, 32, 24, 20, 16, 12, 10, 8, 6, 5, 4, 3, 2, 1)
SNES_STEP_DB = -20 * math.log10(1 - 1 / 256)
NDS_ENVELOPE_HZ = 192  # NDS 엔벨로프 갱신 빈도. 감쇠 단위 1 = 1/1280 dB(0 ~ -723*128 이 0 ~ -72.3dB)


def nds_fall_db_per_second(value):
    """NDS 감쇠·릴리스 값(0~127)이 1초에 줄이는 dB. 127 은 바로 끝남(inf)."""
    if value >= 127:
        return math.inf
    rate = 0x3C00 if value == 126 else value * 2 + 1 if value < 50 else 0x1E00 / (126 - value)
    return rate * NDS_ENVELOPE_HZ / 1280


def nds_sustain_db(value):
    """NDS 서스테인 값의 dB. 세기 값처럼 제곱으로 줄어든다."""
    return 0.0 if value >= 127 else -math.inf if value <= 0 else 40 * math.log10(value / 127)


def snes_rate(db_per_second, choices=range(1, 32)):
    """1초에 db_per_second 만큼 줄어드는 데 가장 가까운 S-DSP 속도 번호(choices 안에서)."""
    if db_per_second <= 0:
        return 0
    want = 32000 * SNES_STEP_DB / db_per_second
    return min(choices, key=lambda i: abs(math.log(SNES_RATE_PERIODS[i] / want)))


def nds_release_rate(value):
    """NDS 릴리스 값을 DQ5 release 명령(ADSR2 하위 5비트, 소리 길이 뒤 줄어드는 속도)으로."""
    return snes_rate(nds_fall_db_per_second(value)) if value < 127 else 0x1F


def approximate_adsr(region):
    attack = min(15, max(0, round(region.get('attack', 127) * 15 / 127)))
    decay = min(7, max(0, round(region.get('decay', 127) * 7 / 127)))
    sustain = min(7, max(0, round(region.get('sustain', 127) * 7 / 127)))
    return 0x80 | decay << 4 | attack, sustain << 5


RELEASE_ONLY = 'release'


def nds_adsr(region):
    """NDS 영역의 attack·decay·sustain 을 ADSR1·ADSR2 로. decay 는 dB/초가 같은 DR, sustain 은 가장 가까운 SL 이며,
    SL 의 바닥(-18dB)보다 낮은 sustain 은 SR 로 decay 와 같은 빠르기로 계속 줄여 붙들린 음으로 남지 않게 한다."""
    attack = min(15, max(0, round(region.get('attack', 127) * 15 / 127)))
    fall = nds_fall_db_per_second(region.get('decay', 127))
    decay = 7 if math.isinf(fall) else (snes_rate(fall, range(16, 31, 2)) - 16) // 2
    level = nds_sustain_db(region.get('sustain', 127))
    levels = [20 * math.log10((n + 1) / 8) for n in range(8)]
    sustain = min(range(8), key=lambda n: abs(levels[n] - level)) if level > levels[0] else 0
    keep = 0 if level > levels[0] - 3 else 0x1F if math.isinf(fall) else snes_rate(fall)
    return 0x80 | decay << 4 | attack, sustain << 5 | keep


def treble(pcm, db, loop_start=None):
    """고음 올리기: x + k·(x - [1/4 1/2 1/4]·x). 나이퀴스트에서 db, 표본율의 1/4 에서 약 db/2 오른다. S-DSP 가우스 보간이
    고음을 깎는 것을 바이트를 늘리지 않고 메운다. 반복 구간은 끝과 처음을 이어 걸러 반복 이음매가 바뀌지 않는다."""
    k = 10 ** (db / 20) - 1

    def boost(x, periodic):
        before, after = (np.roll(x, 1), np.roll(x, -1)) if periodic else (np.r_[x[:1], x[:-1]], np.r_[x[1:], x[-1:]])
        return x + k * (x - (before + 2 * x + after) / 4)

    if loop_start is None:
        return boost(pcm, False)
    return np.concatenate((boost(pcm[:loop_start], False) if loop_start else pcm[:0], boost(pcm[loop_start:], True)))


WAVE_SAMPLES = 32


def wave_resource(path, region, length=WAVE_SAMPLES):
    """반복 구간이 기준음(base) 주기를 되풀이하는 짧은 음정 샘플을 한 주기 length 표본의 반복 샘플로. (자원, 보고서).
    NDS UI·전투 효과음의 작은 파형(수 KB)이 수십 바이트가 된다. 잡음을 줄이려고 반복 구간의 주기들을 평균한다."""
    pcm, rate, loop = read_wave(path)
    if loop is None:
        raise ValueError(f'{path.name}: wave samples must loop')
    period = rate / (440 * 2 ** ((region['base'] - 69) / 12))
    segment = pcm[loop[0]:loop[1]]
    cycles = int(len(segment) // period)
    if cycles < 1:
        # 반복 구간이 기준음 한 주기보다 짧으면 그 구간 자체가 (더 높은 음의) 한 주기다
        period, cycles = len(segment), 1
    cycle = resample_segment(segment[:round(cycles * period)], cycles * length).reshape(cycles, length).mean(axis=0)
    converted = np.concatenate((np.zeros(16), np.clip(np.rint(cycle), -16384, 16383))).astype('<i2')
    encoded = encode_hw(converted.tolist(), 16)
    effective_rate = rate * length / period
    adsr1, adsr2 = approximate_adsr(region)
    pitch = pitch_word(effective_rate, region['base'])
    report = {'source': path.name, 'base_midi': region['base'], 'cycles_averaged': cycles, 'samples': len(converted),
              'brr_bytes': len(encoded), 'pitch': pitch, 'snr_db': round(hw_snr(converted, encoded), 3),
              'envelope': {'adsr1': adsr1, 'adsr2': adsr2}}
    return brr.resource(encoded, 1, adsr1=adsr1, adsr2=adsr2, pitch=pitch), report


def convert_sample(path, region, *, max_rate=12000, cache_dir=None, seconds=None, envelope=False, treble_db=0.0):
    pcm, rate, loop = read_wave(path)
    if seconds is not None and loop is None:
        # 반복 없는 긴 샘플은 끝을 잘라 짧게 사라지게 한다(꼬리 20% 를 선형으로 줄임).
        pcm = pcm[:int(rate * seconds)].copy()
        fade = max(1, len(pcm) // 5)
        pcm[-fade:] *= np.linspace(1, 0, fade)
    converted, effective_rate, loop_start = prepare_pcm(pcm, rate, loop, max_rate)
    if treble_db:
        converted = treble(converted, treble_db, loop_start)
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
    adsr1, adsr2 = (nds_adsr if envelope else approximate_adsr)(region)
    pitch = pitch_word(effective_rate, region['base'])
    if region.get('tune'):
        pitch = round(pitch * 2 ** (region['tune'] / 128 / 12))
        if not 1 <= pitch <= 65535:
            raise ValueError(f'DQ5 샘플 음높이 범위 초과: tune={region["tune"]}')
    result = brr.resource(encoded, (loop_start or 0) // 16, adsr1=adsr1, adsr2=adsr2, pitch=pitch)
    if len(result) - 2 > 65535:
        raise ValueError('샘플 자원 길이 16-bit 초과')
    report = {
        'source': path.name, 'original_samples': len(pcm), 'original_rate': rate,
        'effective_rate': round(effective_rate, 6), 'samples': len(converted),
        'source_loop': list(loop) if loop else None, 'loop_start': loop_start,
        'brr_bytes': len(encoded), 'resource_bytes': len(result), 'pitch': pitch,
        'base_midi': region['base'], 'tune': region.get('tune', 0), 'snr_db': round(hw_snr(converted, encoded), 3),
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


BEND_MIN_UNITS = 10  # 1/128 반음 단위. 10 은 약 8센트


def bend_units(note, drums=()):
    """NDS 음마다 고정 벤드를 1/128 반음 단위로(NDS 벤드 b 는 b/128 × 범위 반음). 겹친 트랙을 맥놀이로 어긋내는 몇 센트와
    드럼 세트의 벤드는 0 으로 본다."""
    units = round((note.get('bend') or 0) * note.get('bend_range', 2))
    return units if abs(units) >= BEND_MIN_UNITS and note['program'] not in drums else 0


def gliding_bends(timeline):
    """벤드가 앞뒤(다른 틱) 음과 다른 음의 색인. NDS 는 음 안에서 벤드를 조금씩 바꿔 끌어올리기·떨어뜨리기를 하는데
    악보에는 음이 시작할 때의 값만 남는다. 그 값을 음 내내 붙들면 음이 틀려 들리므로, 앞이나 뒤 음과 같은 벤드만
    고정 벤드로 보고, 나머지는 그 영역의 흔한 벤드(region_tunes)로 울린다."""
    ticks = {}
    for i, e in enumerate(timeline):
        if e.get('op') == 'note':
            ticks.setdefault(e.get('ch'), {}).setdefault(e.get('tick', i), []).append(i)
    out = set()
    for by_tick in ticks.values():
        order = sorted(by_tick)
        for k, tick in enumerate(order):
            near = [timeline[j].get('bend') or 0 for t in order[max(0, k - 1):k] + order[k + 1:k + 2] for j in by_tick[t]]
            for i in by_tick[tick]:
                e = timeline[i]
                b, scale = e.get('bend') or 0, e.get('bend_range', 2)
                if b and all(abs((x - b) * scale) >= BEND_MIN_UNITS for x in near):
                    out.add(i)
    return out


def drum_programs(score):
    return {int(p) for p, ins in (score.get('instruments') or {}).items() if ins and ins.get('type') == '드럼 세트'}


def region_tunes(score):
    """영역마다 그 영역 음들의 고정 벤드 중앙값. 샘플 음높이에 미리 구워 음마다 미세 조정 명령을 쓰지 않게 한다."""
    drums, units = drum_programs(score), {}
    gliding = gliding_bends(score['timeline'])
    for i, e in enumerate(score['timeline']):
        instrument = e.get('op') == 'note' and score['instruments'].get(str(e['program']))
        if not instrument:
            continue
        for k, region in enumerate(instrument['regions']):
            if region['lo'] <= e['note'] <= region['hi']:
                if i not in gliding:
                    units.setdefault((e['program'], k), []).append(bend_units(e, drums))
                break
    return {key: round(statistics.median(v)) for key, v in units.items() if round(statistics.median(v))}


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
               rates=RATES, keep_regions=(), envelope=False, treble_db=0.0, sample_rates=None):
    """(resources, program_map, report). sample은 DQ5 전역 번호.

    budget(바이트)·max_samples(곡 묶음 칸)를 넘으면 손실이 가장 작은 줄이기를 하나씩 고른다.
    쓰이는 음이 적은 영역을 같은 프로그램의 이웃 영역 샘플로 합치기, 표본율 낮추기, 반복 없는 샘플 자르기.
    무엇을 줄였는지는 report['reductions']에 남긴다. envelope 이면 샘플 머리를 nds_adsr 로 하고, 프로그램 표에 영역의
    엔벨로프 값과 머리 ADSR('header')을 담아 변환기가 음마다 adsr·release 를 쓰게 한다. envelope 가 RELEASE_ONLY 면
    샘플 머리는 그대로(다른 곡과 같은 샘플을 나눠 쓴다) 두고 음마다 release 만 쓰게 한다. 영역 음들의 고정 벤드 중앙값
    (region_tunes)은 샘플 음높이에 굽고 프로그램 표의 'tune' 에 남긴다. sample_rates({NDS 샘플 파일: Hz})는 그 샘플의
    첫 표본율을 max_rate 대신 그 값으로 한다(소리가 높은 음역에만 있는 짧은 타악기).
    """
    full = envelope is True
    sample_rates = sample_rates or {}

    def hz(ident):
        level = rate.get(ident, 0)
        return sample_rates.get(ident[0], rates[0]) if level == 0 else rates[level]

    adsr_of = nds_adsr if full else approximate_adsr
    if not 0x26 <= start_id < 0xC8:
        raise ValueError('custom sample IDs must start in 26..C7')
    root = Path(asset_root)
    samples = root / 'nds/dq4/sound/samples'
    counts, silent = used_regions(score)
    tunes = region_tunes(score)
    regions = {}
    for (program, k), n in counts.items():
        region = score['instruments'][str(program)]['regions'][k]
        if region['type'] != 'PCM':
            raise ValueError(f'unsupported instrument program {program}: {region["type"]}')
        path = samples / region['sample']
        if not path.resolve().is_relative_to(samples.resolve()):
            raise ValueError('sample path outside asset root')
        tune = tunes.get((program, k))
        regions[(program, k)] = (region | {'tune': tune} if tune else region, path, n)
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
        return region['sample'], region['base'], adsr_of(region), region.get('tune', 0)

    sizes = {}

    def size(ident, path):
        key = (ident, rate.get(ident, 0), cut.get(ident, 0))
        if key not in sizes:
            seconds = ONE_SHOT_SECONDS[cut.get(ident, 0)]
            sizes[key] = estimate(path, hz(ident), seconds)
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
        resource, detail = convert_sample(path, region, max_rate=hz(ident), envelope=full,
                                          treble_db=treble_db,
                                          cache_dir=cache_dir, seconds=ONE_SHOT_SECONDS[cut.get(ident, 0)])
        resources[identifier], details[f'{identifier:02X}'] = resource, detail
        ids[ident] = identifier
    mapping = {}
    for (program, k) in sorted(regions):
        region = regions[(program, k)][0]
        entry = {'lo': region['lo'], 'hi': region['hi'], 'sample': ids[identity(target[(program, k)])]}
        if regions[target[(program, k)]][0].get('tune'):
            entry['tune'] = regions[target[(program, k)]][0]['tune']
        if envelope:
            entry |= {x: region[x] for x in ('attack', 'decay', 'sustain', 'release') if x in region}
            entry['header'] = list(adsr_of(regions[target[(program, k)]][0]))
            if not full:
                entry['release_only'] = True
        mapping.setdefault(program, []).append(entry)
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
