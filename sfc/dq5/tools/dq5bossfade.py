"""DQ5(SFC) ミルドラース 가 쓰러질 때(22:CC16)의 팔레트 바꾸기. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「몬스터 움직임」.

22:CC16 은 첫 무리 몬스터($0C10)가 EA 인지에 따라 단계 목록을 고르고, 단계마다 처음 처리($8587)·끝 처리($8585)·
$858A = 30 을 두고 22:A650 을 부른다. 22:A650 은 $8589 를 0 부터 29 까지 프레임마다 하나씩 늘리며 22:A668 을 부른다.
22:A668 은 원래 색(7E:0520 + 팔레트*32)마다 회색 g = (3R + 6G + B) / 10 을 내고, 처리 번호로 22:A7E2 표의 루틴을
골라 두 목표 색을 만든 뒤 (끝 x $8589 + 처음 x ($858A - $8589)) / $858A 로 섞어 7E:2D00 + 팔레트*32 에 쓴다.
처리 번호 00 은 루틴을 부르지 않아 원래 색 그대로다.

  python sfc/dq5/tools/dq5bossfade.py rom/dq5.sfc                     # 두 단계 목록과 처리 번호
  python sfc/dq5/tools/dq5bossfade.py rom/dq5.sfc --check work/m2B    # lua/dq5monlog.lua 덤프와 프레임마다 견줌
--check 는 덤프의 exec.txt(EXEC=22CC16,22A650)로 단계 시작 프레임을 알고, 원래 색은 몬스터 레코드(dq5mongfx.py)에서 읽는다.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402
import dq5mongfx  # noqa: E402

CC16 = 0x22CC16
STEPS = 30                         # $858A
PAL_LINE = 8                       # $858B: OBJ 팔레트 0 = CGRAM 줄 8


def clamp(v):
    return min(v, 0x1F)


# 22:A7E2 표의 처리 루틴. 받는 값은 원래 색(c)과 회색(g), 돌려주는 값은 (R, G, B).
def _h04(c, g):
    gg = clamp(2 * g + 2)          # 22:A822 가 G 를 두고 22:A833 으로 떨어짐
    b = clamp(2 * gg)
    return clamp(8 * g), b, b


def _h12(c, g):
    t = g // 2
    b = clamp(t // 4 + g)
    return g // 2, g, clamp(t + b)


def _h1e(c, g):
    r = clamp(2 * g)
    return r, r // 2, 0


def _h22(c, g):
    v = clamp(2 * g) if g >= 0x18 else g // 2
    return v, v, v


HANDLERS = {
    0x02: lambda c, g: (clamp(2 * g), g // 2, g // 2),          # 22:A855 붉게
    0x04: _h04,                                                   # 22:A822
    0x06: lambda c, g: (g // 2, g // 2, clamp(2 * g)),          # 22:A808 푸르게
    0x08: lambda c, g: (clamp(2 * g + 2), clamp(2 * g + 2), g // 2),   # 22:A86F 노랗게
    0x0A: lambda c, g: (g, g, g),                                # 22:A8E8 회색(RTS 뿐)
    0x0C: lambda c, g: (0x1F, 0x1F, 0x1F),                       # 22:A8E9 흰색
    0x0E: lambda c, g: (clamp(8 * g), clamp(2 * g), clamp(2 * g)),   # 22:A833 분홍
    0x10: lambda c, g: (clamp(8 * g), clamp(2 * g), clamp(8 * g)),   # 22:A8B7 자주
    0x12: _h12,                                                   # 22:A88B 하늘색
    0x14: lambda c, g: (g // 2, g // 2, g // 2),                 # 22:A8D9 어두운 회색
    0x16: lambda c, g: (g, g // 4, g // 2),                      # 22:A905
    0x18: lambda c, g: (0x1F, 0x1C, 0x13),                       # 22:A910 연노랑 한 색
    0x1A: lambda c, g: (c[0] // 2, c[1] // 2, c[2] // 2),        # 22:A922 원래 색의 반
    0x1C: lambda c, g: (0x1F - g,) * 3,                          # 22:A95A 회색 뒤집기
    0x1E: _h1e,                                                   # 22:A96C 주황
    0x20: lambda c, g: (clamp(2 * g), clamp(2 * g), clamp(8 * g)),   # 22:A985 푸르스름한 흰색
    0x22: _h22,                                                   # 22:A9A7 대비
    0x24: lambda c, g: (0, 0, 0),                                # 22:A8F7 검정
}


def stage_lists(rom):
    """{첫 몬스터: [(처음, 끝)]}. 22:CC16 의 LDA #x / STA $8587 · STA $8585 짝을 읽는다."""
    d = rom.d
    o = lorom(CC16)
    code = d[o:o + 0x200]
    # CMP #$EA / BEQ rel: 갈래 앞이 E7(그 밖), 뒤가 EA
    i = code.index(bytes([0xC9, 0xEA, 0xF0]))
    split = i + 4 + code[i + 3]
    end = code.index(bytes([0x6B]), split)                       # EA 갈래 끝 RTL
    out = {}
    for name, lo, hi in (('E7', i, split), ('EA', split, end)):
        seq = []
        start = None
        for j in range(lo, hi - 4):
            if code[j] == 0xA9 and code[j + 2] == 0x8D and code[j + 4] == 0x85:
                if code[j + 3] == 0x87:
                    start = code[j + 1]
                elif code[j + 3] == 0x85 and start is not None:
                    seq.append((start, code[j + 1]))
        out[name] = seq
    return out


def rgb(c):
    return c & 0x1F, (c >> 5) & 0x1F, (c >> 10) & 0x1F


def target(c, kind):
    if kind == 0:
        return rgb(c)
    r, g, b = rgb(c)
    grey = ((3 * r + 6 * g + b) // 10) & 0x1F
    return HANDLERS[kind](rgb(c), grey)


def blend(c, start, end, k, steps=STEPS):
    """22:A668: $8589 = k 일 때의 색."""
    e, s = target(c, end), target(c, start)
    r, g, b = ((e[i] * k + s[i] * (steps - k)) // steps & 0x1F for i in range(3))
    return b << 10 | g << 5 | r


def frames(colors, stages):
    """단계마다 k = 0..29 의 색 목록(OBJ 팔레트 1번 색부터). colors 는 몬스터 레코드의 색이다.
    22:A5A4 가 버퍼 색 0 자리에 색 수 + 1 을 적고, 22:A68E 는 그 값만큼(16 이하)만 바꾼다."""
    return [[[blend(c, s, e, k) for c in colors] for k in range(STEPS)] for s, e in stages]


def hdma_writes(folder):
    """{프레임: {CGRAM 색 번호: 값}} cgw.txt(lua/dq5monlog.lua 의 CGW=1)에서 화면을 그리는 동안 $2121·$2122 로 쓴 색."""
    path = os.path.join(folder, 'cgw.txt')
    out = {}
    if not os.path.exists(path):
        return out
    addr, low = 0, None
    for ln in open(path):
        p = ln.split()
        if len(p) != 4:
            continue
        f, reg, v = int(p[0]), int(p[2], 16), int(p[3], 16)
        if reg == 0x2121:
            addr, low = v, None
        elif low is None:
            low = v
        else:
            out.setdefault(f, {})[addr] = low | v << 8
            addr, low = (addr + 1) & 0xFF, None
    return out


def last_hdma(hw, f, idx):
    """프레임 f 까지 HDMA 가 색 idx 에 마지막으로 쓴 값. CGRAM 전체 DMA 가 매 프레임 있지는 않아 앞 프레임에 쓴 것이 남는다."""
    for g in sorted((g for g in hw if g <= f), reverse=True):
        if idx in hw[g]:
            return hw[g][idx]
    return None


def check(rom, folder):
    ex = [ln.split() for ln in open(os.path.join(folder, 'exec.txt')) if ln.strip()]
    cc = [int(x[0]) for x in ex if x[1] == '22CC16'][0]
    starts = [int(x[0]) for x in ex if x[1] == '22A650']

    def line(f):
        b = open(os.path.join(folder, 'c%05d.cgram' % f), 'rb').read()[PAL_LINE * 32:PAL_LINE * 32 + 32]
        return [b[i] | b[i + 1] << 8 for i in range(0, 32, 2)]

    before = line(cc - 1)
    w = open(os.path.join(folder, 'w%05d.bin' % (cc + 1)), 'rb').read()
    first = 'EA' if w[0x10] == 0xEA else 'E7'                    # 7E:0C10
    stages = stage_lists(rom)[first]
    colors = dq5mongfx.monster(rom, int(first, 16))[1]
    if colors != before[1:1 + len(colors)]:
        print('%s: CC16 직전 줄 8 이 몬스터 %s 레코드 색과 다름' % (folder, first))
    want = [[[before[0]] + pal + before[1 + len(pal):] for pal in st] for st in frames(colors, stages)]
    # 색 0 은 투명이라 OBJ 에 안 쓰이고, 버퍼에서는 색 수 자리라 견주지 않는다.
    # k = 0 은 앞 단계의 끝과 같으므로, 덤프가 몇 프레임 늦게 나오는지는 첫 단계의 가운데로 정한다
    mid = STEPS // 2
    lag = max(range(6), key=lambda d: sum(a == b for a, b in zip(line(starts[0] + mid + d)[1:], want[0][mid][1:])))
    hw = hdma_writes(folder)
    same = total = hdma = 0
    odd = []
    for si, s0 in enumerate(starts[:len(stages)]):
        for k in range(STEPS):
            total += 1
            f = s0 + k + lag
            got = line(f)
            diff = [i for i in range(1, 16) if got[i] != want[si][k][i]]
            if not diff:
                same += 1
            elif all(last_hdma(hw, f, PAL_LINE * 16 + i) == got[i] for i in diff):
                hdma += 1          # 그 프레임까지 화면 가운데에서 HDMA 가 그 색 칸에 마지막으로 쓴 값
            else:
                odd.append('%d(색 %s)' % (f, ','.join(str(i) for i in diff)))
    print('%s 첫 몬스터 %s, 단계 %d개 %s' % (folder, first, len(stages),
                                         ' → '.join('%02X' % s for s, _ in stages) + ' → %02X' % stages[-1][1]))
    print('  단계 시작 프레임 %s, 덤프는 %s 프레임 뒤' % (starts[:len(stages)], lag))
    print('  레코드 색 %d개, 줄 8 의 색 1~15 가 같은 프레임 %d/%d' % (len(colors), same, total))
    if hdma:
        print('  나머지 %d프레임은 다른 색이 모두 그 프레임까지 HDMA 가 CGRAM 에 마지막으로 쓴 값(cgw.txt)' % hdma)
    if odd:
        print('  설명 못 한 프레임: ' + ' '.join(odd))
    return same + hdma == total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--check', nargs='*', default=[], help='lua/dq5monlog.lua 덤프 폴더')
    a = ap.parse_args()
    rom = Rom(open(a.rom, "rb").read())
    if a.check:
        ok = all([check(rom, f) for f in a.check])
        sys.exit(0 if ok else 1)
    for name, st in stage_lists(rom).items():
        print('%s: %s' % (name, ' → '.join('%02X' % s for s, _ in st) + ' → %02X' % st[-1][1]))


if __name__ == '__main__':
    main()
