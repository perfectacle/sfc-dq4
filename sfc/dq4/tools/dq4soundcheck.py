"""dq4soundpatch.py 로 바꿔 넣은 곡이 SPC 에서 실제로 그대로 울렸는지 견준다.

입력은 lua/dq4overturespc.lua 의 OUT 폴더(spc.bin·dspw.txt·events.txt)와 그 롬이다.
dq5spc.py --check·dq5song.py --kon 은 원래 자리의 시퀀스와 템포 하나를 가정하므로 재배치한 곡에는 쓰지 않는다.
1) SPC 칸 표에 오른 시퀀스·샘플이 재배치 표(70:8100·70:8300)가 가리키는 롬 자료와 같은지,
2) 목소리마다 KON 시각이 시퀀스의 템포 변화를 따른 예상 시각과 맞는지,
3) KON 때의 SRCN 이 곡 묶음 샘플의 칸인지, 같은 샘플끼리 음 간격이 맞는지 본다.
곡이 울리는 동안 도착하는 샘플(곡 묶음 k < L)의 음은 도착 전이면 드라이버가 막으므로 예상 음에서 뺀다.
"""
import argparse
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'sfc/dq5/tools')]
from dq4soundpatch import chained_song, read_sets, sequence_bytes  # noqa: E402
from dq4soundport import DQ5_TICKS_PER_SECOND_PER_TEMPO, execution_trace  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5song import RELOC_SMP_TABLE, header, read_kon  # noqa: E402
from dq5spc import (SPC_DIR, SPC_SAMPLE_INDEX, SPC_SAMPLE_SLOTS, SPC_SEQUENCE_INDEX,  # noqa: E402
                    SPC_SEQUENCE_SLOTS, samples)

NTSC_FPS = 60.0988


def sample_body(data, sample):
    ptr = int.from_bytes(data[lorom(RELOC_SMP_TABLE) + sample * 3:lorom(RELOC_SMP_TABLE) + sample * 3 + 3], 'little')
    if ptr:
        pos = lorom(ptr)
    else:
        pos = lorom(samples(Rom(data))[sample][1])
    size = int.from_bytes(data[pos:pos + 2], 'little')
    return bytes(data[pos + 2:pos + 2 + size])


def memory(data, spc, song):
    """곡의 시퀀스와 곡 묶음 샘플이 SPC 에 롬과 같은 바이트로 올랐는지."""
    seq = sequence_bytes(data, song)
    slot = spc[SPC_SEQUENCE_INDEX + song]
    result = {'sequence_slot': None if slot == 0xFF else slot, 'sequence_ok': False, 'samples': {}}
    if slot != 0xFF:
        e = spc[SPC_SEQUENCE_SLOTS + slot * 6:SPC_SEQUENCE_SLOTS + slot * 6 + 6]
        addr, size = e[1] | e[2] << 8, e[3] | e[4] << 8
        result['sequence_ok'] = size == len(seq) and spc[addr:addr + size] == seq
    record = read_sets(data)[song]
    for sample in record[2:]:
        slot = spc[SPC_SAMPLE_INDEX + sample]
        ok = False
        if slot != 0xFF:
            body = sample_body(data, sample)
            e = spc[SPC_SAMPLE_SLOTS + slot * 8:SPC_SAMPLE_SLOTS + slot * 8 + 8]
            start = spc[SPC_DIR + slot * 4] | spc[SPC_DIR + slot * 4 + 1] << 8
            loop = spc[SPC_DIR + slot * 4 + 2] | spc[SPC_DIR + slot * 4 + 3] << 8
            brr = e[0] | e[1] << 8
            ok = (brr == len(body) - 7 and bytes(e[2:7]) == body[2:7]
                  and loop - start == (body[0] | body[1] << 8) and spc[start:start + brr] == body[7:])
        result['samples'][f'{sample:02X}'] = {'slot': None if slot == 0xFF else slot, 'ok': ok}
    return seq, result


def expected_notes(seq, ticks, chain=None):
    """트랙마다 [(초, 음 번호, 곡 묶음 안 악기 번호)]. 템포는 트랙 0 의 EB 를 따른다. chain 은 나눈 곡의 본체."""
    tracks = execution_trace(seq, ticks, chain=chain)
    tempos = [(0, seq[0])] + [(t, b[1]) for t, b in tracks[0] if b[0] == 0xEB]
    tempos.sort()

    def seconds(tick):
        total, last_t, last_v = 0.0, 0, tempos[0][1]
        for t, v in tempos[1:]:
            if t >= tick:
                break
            total += (t - last_t) / (last_v * DQ5_TICKS_PER_SECOND_PER_TEMPO)
            last_t, last_v = t, v
        return total + (tick - last_t) / (last_v * DQ5_TICKS_PER_SECOND_PER_TEMPO)

    result = []
    for events in tracks:
        instrument, notes = 0, []
        for tick, raw in events:
            op = raw[0]
            if op == 0xF0:
                instrument = raw[1]
            elif op < 0xA0:
                n = op - 0x50 if op >= 0x50 else op
                if n not in (0, 0x4F):
                    notes.append((seconds(tick), n, instrument))
        result.append(notes)
    return result


def read_srcn(path):
    """목소리마다 [(프레임, SRCN)] — KON 직전에 쓰인 x4 값."""
    srcn, hits = [0] * 8, [[] for _ in range(8)]
    for line in open(path):
        f, rv = line.split()
        r, v = (int(x, 16) for x in rv.split('='))
        if r < 0x80 and r & 0x0F == 4:
            srcn[r >> 4] = v
        elif r == 0x4C:
            for vo in range(8):
                if v >> vo & 1:
                    hits[vo].append((int(f), srcn[vo]))
    return hits


def read_events(path):
    """events.txt → (곡이 처음 오른 프레임, {샘플: 마지막으로 칸이 생긴 프레임})."""
    start, on, arrivals = None, None, {}
    for line in path.read_text().splitlines():
        words = line.split()
        if 'started' in words:
            start = int(words[-1])
        elif words[:1] == ['song'] and 'on' in words:
            on = int(words[-1])
        elif words[:1] == ['sample']:
            sample, slot = int(words[1], 16), int(words[3], 16)
            if slot == 0xFF:
                arrivals.pop(sample, None)
            else:
                arrivals[sample] = int(words[-1])
    return (on if start is None else start), arrivals


ARRIVAL_MARGIN_FRAMES = 2


def blocked(note_seconds, sample, start, arrivals):
    """그 음이 샘플 도착 전에 나오는지. 첫 KON 은 곡이 오른 다음 프레임이라 1프레임을 더한다.

    칸이 생긴 프레임(events.txt)에 바로 이어지는 음도 막혔으므로(곡 0F, 도착 다음 프레임의 음) 2프레임을 더 본다.
    """
    return sample in arrivals and start + 1 + note_seconds * NTSC_FPS < arrivals[sample] + ARRIVAL_MARGIN_FRAMES


def timing(seq, run, start, slots, record, arrivals=None, chain=None):
    """KON 을 예상 음과 순서대로 짝짓고, 전 목소리 공통의 시작·속도 비를 최소제곱으로 맞춘 잔차를 본다.

    APU 발진기는 공칭 32kHz 보다 조금 빨라(실기·MesenCE 모두 약 32.04kHz) 공칭 속도로는 시간에 비례해 어긋난다.
    """
    kon, src = read_kon(run / 'dspw.txt'), read_srcn(run / 'dspw.txt')
    last = max(int(line.split()[0]) for line in open(run / 'dspw.txt'))
    ticks = math.ceil((last - start) / NTSC_FPS * 255 * DQ5_TICKS_PER_SECOND_PER_TEMPO) + 1
    notes = expected_notes(seq, ticks, chain)
    first = header(seq)[1][0]
    if seq[first:first + 2] == bytes([0xF7, 0xFE]):
        # 곡 붙들기: 곡이 오른 뒤 샘플을 기다린 만큼 음이 늦으므로, 첫 KON 에서 첫 예상 음 시각을 뺀 프레임을 시작으로 본다
        heard = min((f for voice in kon for f, _, _ in voice if f >= start - 1), default=start)
        start = max(start, round(heard - min(n[0] for v in notes for n in v) * NTSC_FPS) - 1)
        # 붙든 샘플은 다 받기 전에 울리는 것이 정상이다
        arrivals = {k: v for k, v in (arrivals or {}).items() if k != seq[first + 2]}
    horizon = (last - start - 2) / NTSC_FPS
    pairs, voices = [], []
    for voice, expected in enumerate(notes):
        # 곡 앞 샘플만 보내는 곡은 첫 KON 이 events.txt 의 시작 프레임보다 한 프레임 이를 수 있다(SPC 가 그 프레임 안에 시작)
        actual = [(f, p) for f, p, _ in kon[voice] if f >= start - 1]
        sources = [s for f, s in src[voice] if f >= start - 1]
        expected = [n for n in expected if n[0] * 1.002 < horizon]
        late = [n for n in expected if blocked(n[0], record[n[2]], start, arrivals or {})]
        expected = [n for n in expected if not blocked(n[0], record[n[2]], start, arrivals or {})]
        count = min(len(expected), len(actual))
        pairs += [(expected[i][0], actual[i][0] - start) for i in range(count)]
        wrong_source = sum(sources[i] != slots.get(record[expected[i][2]]) for i in range(count))
        intervals = bad = 0
        for i in range(1, count):
            if expected[i][2] == expected[i - 1][2] and actual[i][1] and actual[i - 1][1]:
                intervals += 1
                bad += round(12 * math.log2(actual[i][1] / actual[i - 1][1])) != expected[i][1] - expected[i - 1][1]
        voices.append({'voice': voice, 'expected_notes': len(expected), 'blocked_notes': len(late),
                       'kon': len(actual), 'compared': count,
                       'wrong_srcn': wrong_source, 'intervals': intervals, 'interval_mismatches': bad,
                       'pairs': pairs[len(pairs) - count:]})
    n = len(pairs)
    if n < 2 or len({x for x, _ in pairs}) < 2:
        raise SystemExit('not enough KON pairs to fit timing')
    mx, my = sum(x for x, _ in pairs) / n, sum(y for _, y in pairs) / n
    slope = sum((x - mx) * (y - my) for x, y in pairs) / sum((x - mx) ** 2 for x, _ in pairs)
    origin = my - slope * mx
    for v in voices:
        v['max_frame_error'] = round(max((abs(y - origin - slope * x) for x, y in v.pop('pairs')), default=0), 2)
    return {'start_frame': start, 'last_frame': last, 'origin_frames': round(origin, 2),
            'speed_ratio': round(slope / NTSC_FPS, 5), 'voices': voices}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('run', type=Path, help='lua/dq4overturespc.lua OUT 폴더')
    ap.add_argument('--song', type=lambda x: int(x, 16), required=True)
    args = ap.parse_args()
    data = args.rom.read_bytes()
    spc = (args.run / 'spc.bin').read_bytes()
    start, arrivals = read_events(args.run / 'events.txt')
    seq, mem = memory(data, spc, args.song)
    record = read_sets(data)[args.song][2:]
    number = chained_song(data, args.song)
    chain = None if number is None else sequence_bytes(data, number)
    slots = {int(k, 16): v['slot'] for k, v in mem['samples'].items()}
    report = {'song': f'{args.song:02X}', 'tracks': seq[1], 'memory': mem,
              'arrivals': {f'{k:02X}': v for k, v in sorted(arrivals.items()) if k in record},
              'timing': timing(seq, args.run, start, slots, record, arrivals, chain)}
    print(json.dumps(report, indent=2))
    speed = report['timing']['speed_ratio']
    ok = (0.995 < speed < 1.005 and mem['sequence_ok'] and all(v['ok'] for v in mem['samples'].values())
          and all(not v['wrong_srcn'] and not v['interval_mismatches'] and v['max_frame_error'] <= 2
                  and v['compared'] == v['expected_notes'] for v in report['timing']['voices']))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
