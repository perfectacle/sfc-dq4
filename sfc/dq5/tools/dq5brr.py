"""DQ5(SFC) 악기 샘플(BRR)을 WAV 로 푼다. 샘플 표는 sfc/dq5/docs/dq5-sound-format.md 「곡 자료」, 위치는 dq5spc.py.

샘플마다 [길이 2][반복 위치 2][ADSR1][ADSR2][GAIN][음높이 2][BRR] 이고, BRR 은 9바이트 블록(머리 1 + 16 표본)이다.
WAV 는 16비트 모노, DSP 음높이 $1000 일 때의 빠르기(32000Hz)로 쓴다. 반복이 있으면 smpl 청크에 반복 구간을 넣는다.
결과(WAV·index.json)는 롬에서 나온 자료라 커밋하지 않는다.

사용:
  python sfc/dq5/tools/dq5brr.py rom/dq5.sfc                     # 표
  python sfc/dq5/tools/dq5brr.py rom/dq5.sfc --out work/sound/samples
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5spc import body, samples  # noqa: E402

RATE = 32000
BLOCK = 9


def decode(brr):
    """BRR 바이트 → (16비트 표본 목록, 끝 블록의 반복 비트). 블록 머리 bit0 = 끝, bit1 = 반복.

    계산은 S-DSP 의 정수 계산을 그대로 따른다(이전 두 표본, 필터 1~3, 16비트로 자른 뒤 1비트 왼쪽 밀기).
    """
    out = [0, 0]
    loop_flag = False
    for b in range(0, len(brr) - BLOCK + 1, BLOCK):
        head = brr[b]
        shift, filt = head >> 4, head & 0x0C
        for i in range(16):
            byte = brr[b + 1 + i // 2]
            s = (byte >> 4) if i % 2 == 0 else (byte & 0x0F)
            if s >= 8:
                s -= 16
            s = (s << shift) >> 1
            if shift >= 0x0D:
                s = -2048 if s < 0 else 0
            p1, p2 = out[-1], out[-2] >> 1
            if filt >= 8:
                s += p1 - p2
                if filt == 8:
                    s += (p2 >> 4) + ((p1 * -3) >> 6)
                else:
                    s += ((p1 * -13) >> 7) + ((p2 * 3) >> 4)
            elif filt:
                s += (p1 >> 1) + ((-p1) >> 5)
            s = max(-0x8000, min(0x7FFF, s))
            s = (s << 1) & 0xFFFF
            out.append(s - 0x10000 if s >= 0x8000 else s)
        if head & 1:
            loop_flag = bool(head & 2)
            break
    return out[2:], loop_flag


def wav(samples16, loop_start=None, rate=RATE):
    data = struct.pack(f'<{len(samples16)}h', *samples16)
    chunks = b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16)
    chunks += b'data' + struct.pack('<I', len(data)) + data
    if loop_start is not None:
        smpl = struct.pack('<9I', 0, 0, 1000000000 // rate, 60, 0, 0, 0, 1, 0)
        smpl += struct.pack('<6I', 0, 0, loop_start, len(samples16) - 1, 0, 0)
        chunks += b'smpl' + struct.pack('<I', len(smpl)) + smpl
    return b'RIFF' + struct.pack('<I', 4 + len(chunks)) + b'WAVE' + chunks


def table(rom):
    """[(번호, 롬 주소, 반복 위치(바이트), ADSR1, ADSR2, GAIN, 음높이, BRR)]."""
    out = []
    for i, a, n in samples(rom):
        b = body(rom, a, n)
        out.append((i, a, b[0] | b[1] << 8, b[2], b[3], b[4], b[5] << 8 | b[6], bytes(b[7:])))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('--out')
    a = ap.parse_args()
    rom = Rom(open(a.rom, 'rb').read())
    index = []
    for i, addr, loop, adsr1, adsr2, gain, pitch, brr in table(rom):
        pcm, looped = decode(brr)
        loop_sample = loop // BLOCK * 16 if looped else None
        print(f'{i:02X} {addr:06X} BRR {len(brr):5d} 바이트 {len(pcm):6d} 표본 반복 {"%d" % loop_sample if looped else "없음":>6}'
              f'  ADSR {adsr1:02X} {adsr2:02X} GAIN {gain:02X} 음높이 {pitch:04X}')
        if a.out:
            os.makedirs(a.out, exist_ok=True)
            name = f'{i:02X}.wav'
            with open(os.path.join(a.out, name), 'wb') as f:
                f.write(wav(pcm, loop_sample))
            index.append({'id': f'{i:02X}', 'file': name, 'rom': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}',
                          'brr_bytes': len(brr), 'samples': len(pcm), 'rate': RATE,
                          'loop_start': loop_sample, 'adsr1': f'{adsr1:02X}', 'adsr2': f'{adsr2:02X}',
                          'gain': f'{gain:02X}', 'pitch': f'{pitch:04X}'})
    if a.out:
        with open(os.path.join(a.out, 'index.json'), 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=1)
            f.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
