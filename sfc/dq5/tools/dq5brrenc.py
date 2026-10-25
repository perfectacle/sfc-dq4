"""DQ5(SFC) 샘플 만들기: 파형·WAV 를 BRR 로 싸서 샘플 자료([길이 2][반복 위치 2][ADSR1][ADSR2][GAIN][음높이 2][BRR])로.
형식은 sfc/dq5/docs/dq5-sound-format.md 「곡 자료」「악기 만들기」.

BRR 은 9바이트 블록([범위 4비트·필터 2비트·반복 1비트·끝 1비트][4비트 x 16])이다. 블록마다 필터 0~3·범위 0~12 를
모두 시험해 복호 오차가 가장 작은 것을 고른다. 첫 블록과 반복 시작 블록은 앞 샘플에 기대지 않게 필터 0 으로 둔다.

사용:
  python sfc/dq5/tools/dq5brrenc.py --wave square --period 32 --cycles 4 -o work/square.bin   # 반복하는 사각파
  python sfc/dq5/tools/dq5brrenc.py --wav in.wav --loop 1024 -o work/x.bin                      # 16비트 모노 WAV
  python sfc/dq5/tools/dq5brrenc.py --check rom/dq5.sfc     # 롬 샘플을 풀었다 다시 싸서 SNR
  python sfc/dq5/tools/dq5brrenc.py --nearest rom/dq5.sfc   # 롬 샘플의 반복 부분 배음으로 사각·삼각·톱니파에 가까운 것
"""
import argparse
import math
import os
import sys
import wave

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5spc import body, samples  # noqa: E402


def _clamp16(v):
    return max(-32768, min(32767, v))


def _predict(f, p1, p2):
    """SNES DSP 의 BRR 필터(정수 근사). p1·p2 는 15비트 범위의 앞 두 샘플."""
    if f == 0:
        return 0
    if f == 1:
        return p1 + ((-p1) >> 4)
    if f == 2:
        return (p1 << 1) + ((-((p1 << 1) + p1)) >> 5) - p2 + (p2 >> 4)
    return (p1 << 1) + ((-(p1 + (p1 << 2) + (p1 << 3))) >> 6) - p2 + (((p2 << 1) + p2) >> 4)


def _sample(nib, shift, f, p1, p2):
    """4비트 하나를 샘플로. 결과는 15비트 범위로 자른다(진폭을 그 안에 두면 DSP 의 넘침 처리와 같아짐)."""
    s = nib - 16 if nib >= 8 else nib
    s = (s << shift) >> 1
    return max(-16384, min(16383, _clamp16(s + _predict(f, p1, p2))))


def decode(brr):
    """BRR 을 15비트 샘플 목록으로(가우스 보간 없음)."""
    out, p1, p2 = [], 0, 0
    for b in range(0, len(brr) - len(brr) % 9, 9):
        hdr = brr[b]
        shift, f = hdr >> 4, hdr >> 2 & 3
        for k in range(16):
            byte = brr[b + 1 + k // 2]
            nib = byte >> 4 if k % 2 == 0 else byte & 15
            s = _sample(nib, shift, f, p1, p2)
            out.append(s)
            p2, p1 = p1, s
        if hdr & 1:
            break
    return out


def _block(pcm, p1, p2, filters):
    """16샘플 한 블록: (오차, 필터, 범위, 4비트 16개, 끝의 p1, p2)."""
    best = None
    for f in filters:
        for shift in range(13):
            q1, q2, nibs, err = p1, p2, [], 0
            for x in pcm:
                e, nib, smp = min(((_sample(n, shift, f, q1, q2) - x) ** 2, n, _sample(n, shift, f, q1, q2))
                                  for n in range(16))
                err += e
                nibs.append(nib)
                q2, q1 = q1, smp
                if best is not None and err >= best[0]:
                    break
            else:
                if best is None or err < best[0]:
                    best = (err, f, shift, nibs, q1, q2)
    return best


def encode(pcm, loop=None):
    """15비트 샘플(길이 16 배수로 0 을 채움)을 BRR 로. loop 는 반복 시작 샘플(16 배수) 또는 None."""
    pcm = [max(-16384, min(16383, int(x))) for x in pcm]
    pcm += [0] * (-len(pcm) % 16)
    if loop is not None and loop % 16:
        raise ValueError("loop must be a multiple of 16")
    out, p1, p2 = bytearray(), 0, 0
    nblocks = len(pcm) // 16
    for i in range(nblocks):
        first = i == 0 or (loop is not None and i * 16 == loop)
        _, f, shift, nibs, p1, p2 = _block(pcm[i * 16:i * 16 + 16], p1, p2, (0,) if first else (0, 1, 2, 3))
        hdr = shift << 4 | f << 2
        if i == nblocks - 1:
            hdr |= 1 | (2 if loop is not None else 0)
        elif loop is not None:
            hdr |= 2
        out.append(hdr)
        out += bytes(nibs[k] << 4 | nibs[k + 1] for k in range(0, 16, 2))
    return bytes(out)


def resource(brr, loop_block, adsr1=0xFF, adsr2=0xE0, gain=0xB8, pitch=0x0F9A):
    """롬 샘플 자료. 반복 위치는 BRR 안의 바이트 오프셋(블록 x 9). 음높이 2바이트는 롬 순서(상위 먼저)."""
    body_ = bytes([loop_block * 9 & 0xFF, loop_block * 9 >> 8, adsr1, adsr2, gain, pitch >> 8, pitch & 0xFF]) + brr
    return bytes([len(body_) & 0xFF, len(body_) >> 8]) + body_


def wave_pcm(kind, period, cycles, amp=12000):
    out = []
    for i in range(period * cycles):
        t = (i % period) / period
        if kind == "square":
            v = amp if t < 0.5 else -amp
        elif kind == "triangle":
            v = amp * (4 * t - 1 if t < 0.5 else 3 - 4 * t)
        elif kind == "saw":
            v = amp * (2 * t - 1)
        else:
            v = amp * math.sin(2 * math.pi * t)
        out.append(v)
    return out


def harmonics(loop, n=8):
    """반복 부분 전체를 한 창으로 DFT 해, 크기가 가장 큰 빈의 30% 를 넘는 첫 빈을 기본음으로 보고 그 배음 크기(기본음 = 1)를 낸다.
    반복 부분은 주기의 정수배이므로 창 끝이 이어진다. (기본 빈, [배음 n 개])."""
    m = len(loop)

    def mag(k):
        re = sum(x * math.cos(2 * math.pi * k * i / m) for i, x in enumerate(loop))
        im = sum(x * math.sin(2 * math.pi * k * i / m) for i, x in enumerate(loop))
        return math.hypot(re, im)
    top = max(1, min(m // 2, 64))
    spec = [0] + [mag(k) for k in range(1, top + 1)]
    peak = max(spec)
    f0 = next(k for k in range(1, top + 1) if spec[k] >= 0.3 * peak)
    h = [mag(f0 * j) if f0 * j <= m // 2 else 0 for j in range(1, n + 1)]
    return f0, [x / h[0] for x in h]


IDEAL = {
    "square": [1, 0, 1 / 3, 0, 1 / 5, 0, 1 / 7, 0],
    "triangle": [1, 0, 1 / 9, 0, 1 / 25, 0, 1 / 49, 0],
    "saw": [1, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 6, 1 / 7, 1 / 8],
    "sine": [1, 0, 0, 0, 0, 0, 0, 0],
}


def snr(a, b):
    n = min(len(a), len(b))
    sig = sum(x * x for x in a[:n]) or 1
    noise = sum((a[i] - b[i]) ** 2 for i in range(n)) or 1
    return 10 * math.log10(sig / noise)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wave", choices=("square", "triangle", "saw", "sine"))
    ap.add_argument("--period", type=int, default=32)
    ap.add_argument("--cycles", type=int, default=4)
    ap.add_argument("--wav")
    ap.add_argument("--loop", type=int, help="--wav 의 반복 시작 샘플(16 배수)")
    ap.add_argument("--pitch", type=lambda v: int(v, 16), default=0x0F9A, help="음높이 2바이트(롬 샘플 00 은 0F9A)")
    ap.add_argument("--check", metavar="ROM")
    ap.add_argument("--nearest", metavar="ROM")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    if a.check or a.nearest:
        rom = Rom(open(a.check or a.nearest, "rb").read())
        for i, addr, n in samples(rom):
            b = body(rom, addr, n)
            loop = (b[0] | b[1] << 8) // 9
            pcm = decode(b[7:])
            if a.check:
                re = decode(encode(pcm, loop * 16))
                print(f"{i:02X} blocks {len(b[7:]) // 9:4d} loop {loop:4d} SNR {snr(pcm, re):5.1f} dB")
                continue
            tail = pcm[loop * 16:]
            if len(tail) < 16:
                print(f"{i:02X} no loop")
                continue
            f0, h = harmonics(tail)
            dist = {k: sum((h[j] - v[j]) ** 2 for j in range(8)) for k, v in IDEAL.items()}
            near = min(dist, key=dist.get)
            print(f"{i:02X} loop {len(tail):5d} samples, {f0:2d} cycles, harmonics {' '.join(f'{x:.2f}' for x in h)}"
                  f"  nearest {near} ({dist[near]:.2f})")
        return
    if a.wave:
        pcm, loop = wave_pcm(a.wave, a.period, a.cycles), 0
    else:
        w = wave.open(a.wav)
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise SystemExit("16-bit mono WAV only")
        raw = w.readframes(w.getnframes())
        pcm = [int.from_bytes(raw[k:k + 2], "little", signed=True) >> 1 for k in range(0, len(raw), 2)]
        loop = a.loop
    brr = encode(pcm, loop)
    res = resource(brr, (loop or 0) // 16, pitch=a.pitch)
    open(a.out, "wb").write(res)
    print(f"{len(pcm)} samples -> {len(brr)} BRR bytes, SNR {snr(pcm, decode(brr)):.1f} dB, resource {len(res)} bytes")


if __name__ == "__main__":
    main()
