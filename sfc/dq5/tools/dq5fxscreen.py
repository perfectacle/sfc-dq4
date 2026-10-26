"""DQ5(SFC) 전투 연출 화면을 dq5ppu 로 그려 MesenCE 화면 버퍼와 화소째 견준다. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의
「연출 층과 화면 전체」.

입력은 lua/dq5fxscreen.lua 가 남긴 폴더다. 프레임마다 첫머리 WRAM(.wram0)과 그 프레임 동안 CPU 가 HDMA 표 자리에 쓴 것(.wlog)으로
HDMA 를 줄마다 따라가고, CGRAM 을 HDMA 로 바꾸는 장면은 첫머리 CGRAM(.cgram0)에 줄마다 더하며, 화면을 그리는 동안 CPU 가 쓴
PPU 레지스터(.plog 에서 HDMA 쓰기를 뺀 것)는 첫머리 상태(.state0)에 더해 줄·점마다 건다. $2130 은 .preg 에서 읽는다.
첫 프레임은 연출이 그 프레임 도중에 시작해 첫머리 덤프가 없으므로 견주지 않는다.

  python sfc/dq5/tools/dq5fxscreen.py rom/dq5.sfc work/fxscreen/h02 [work/fxscreen/h03 …]
"""
import argparse
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import dq5ppu  # noqa: E402

HDMA_FROM = 1100   # HDMA 가 쓰는 줄 안 자리(이 뒤에 HDMA 채널의 목적지 레지스터에 쓴 것은 HDMA 쓰기로 본다)


def log(path):
    return [(int(a), int(b), int(c, 16), int(d, 16)) for a, b, c, d in (ln.split() for ln in open(path) if ln.strip())]


def with_preg(P, path):
    if os.path.exists(path):
        for ln in open(path):
            if ln.startswith('2130='):
                v = int(ln[5:], 16)
                P['ppu.colorMathPreventMode'], P['ppu.colorMathClipMode'] = str((v >> 4) & 3), str(v >> 6)
    return P


def hdma_dests(P):
    """켠 HDMA 채널들이 쓰는 B 버스 레지스터(16비트 주소) 집합."""
    out, en = set(), int(P['dmaController.hdmaChannels'])
    for ch in range(8):
        if (en >> ch) & 1:
            k = f'dmaController.channel[{ch}].'
            mode, dest = int(P[k + 'transferMode']), int(P[k + 'destAddress'])
            out |= {0x2100 + dest + o for o in dq5ppu.B_OFFSETS[mode]}
    return out


def frame(rom, folder, fx, k):
    """(그림, 화면) RGB 배열."""
    p = os.path.join(folder, f'e{fx:02X}-{k:03d}')
    rd = lambda s: open(p + s, 'rb').read()  # noqa: E731
    P = with_preg(dq5ppu.load_state(p + '.state'), p + '.preg')
    P0 = with_preg(dq5ppu.load_state(p + '.state0'), p + '.preg0')
    dests = hdma_dests(P) | hdma_dests(P0)
    cpu = [w for w in log(p + '.plog') if not (w[1] >= HDMA_FROM and w[2] in dests)]
    img = dq5ppu.render(dq5ppu.state_from(P, rd('.vram'), rd('.cgram'), rd('.oam'), rd('.wram0'), rom=rom,
                                          writes=log(p + '.wlog'), cgram0=rd('.cgram0'), cpu_writes=cpu, P0=P0))
    raw = np.frombuffer(rd('.raw'), '<u4').reshape(239, 256)
    scr = np.stack([(raw >> 16) & 255, (raw >> 8) & 255, raw & 255], -1).astype(np.uint8)
    return img, scr


def frames(folder):
    """[(연출 번호, k)]."""
    out = []
    for path in sorted(glob.glob(os.path.join(folder, 'e??-???.raw'))):
        name = os.path.basename(path)
        out.append((int(name[1:3], 16), int(name[4:7])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('folders', nargs='+')
    args = ap.parse_args()
    rom = open(args.rom, 'rb').read()
    total = bad = 0
    for folder in args.folders:
        fr = frames(folder)
        fr = [(fx, k) for fx, k in fr if os.path.exists(os.path.join(folder, f'e{fx:02X}-{k:03d}.state0'))]
        diffs = []
        for fx, k in fr:
            img, scr = frame(rom, folder, fx, k)
            n = int(np.any(img != scr, -1).sum())
            if n:
                diffs.append((k, n))
        total += len(fr)
        bad += len(diffs)
        fxs = sorted({fx for fx, _ in fr})
        print(f'{os.path.basename(folder.rstrip("/"))} 연출 {",".join(f"{x:02X}" for x in fxs)} 프레임 {len(fr)} '
              f'다른 프레임 {len(diffs)}' + (' ' + ' '.join(f'{k}:{n}' for k, n in diffs[:12]) if diffs else ''), flush=True)
    print(f'합계 프레임 {total} 다른 프레임 {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
