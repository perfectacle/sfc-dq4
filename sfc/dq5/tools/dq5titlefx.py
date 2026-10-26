"""DQ5(SFC) 오프닝 타이틀의 프레임마다 바뀌는 것(바다 물결 HDMA 표, BG4 가로 HDMA 표, 링 반짝이 OBJ)을 롬만으로 계산한다.

형식은 sfc/dq5/docs/dq5-graphics-format.md 「오프닝 타이틀 로고」. 근거 루틴:
  02:ED3E 타이틀 기다리는 고리. 7E:21EA bit1 이면 프레임마다 03:AA67(물결)과 02:EC67(BG4 표)을 부른다.
  03:AA3C 물결 준비: 7E:A007~ 240낱말을 $2B 로 채우고 간접 표 머리(03:99DA)를 쓴 뒤 03:AA92 를 240번.
  03:AA71 프레임마다 $75 += 1, ($75 + 1) & 7 = 0 이면 03:AA92.
  03:AA92 03:998E(표를 한 낱말 밀고 맨 앞에 $2B + sin($71) × $73) 뒤 $71 += 10 + ($075B & 0F).
  03:A82C sin: 0~90도는 03:A88E 표(87바이트, 87도부터는 진폭 그대로), 나머지 사분면은 대칭.
  02:EC67 7E:A4DC: 191줄 0, 8줄 $75/16, 16줄 $75/8, 1줄 $75/4.
  02:EB22 링을 한 열씩 그리며 02:EB96 으로 반짝이 3줄 × 4개를 머리 열 뒤에 붙인다(02:EC00 이 자리).

  uv run --locked python sfc/dq5/tools/dq5titlefx.py rom/dq5.sfc                     # 표를 찍는다
  uv run --locked python sfc/dq5/tools/dq5titlefx.py rom/dq5.sfc --check titlefx.bin # lua/dq5titlefx.lua 덤프와 견준다
"""
import argparse
import struct


def cpu(rom, bank, addr):
    return (bank & 0x7F) * 0x8000 + addr - 0x8000


class Title:
    def __init__(self, rom):
        self.sin_tab = rom[cpu(rom, 3, 0xA88E):cpu(rom, 3, 0xA88E) + 0x57]
        t = rom[cpu(rom, 2, 0xEDFE):cpu(rom, 2, 0xEDFE) + 88]
        self.cols = [t[i:i + 4] for i in range(0, 88, 4)]  # 링 열 [X][Y][세로 타일 수][속성]
        self.spark_dy = rom[cpu(rom, 2, 0xEE57):cpu(rom, 2, 0xEE57) + 3]  # 반짝이 줄마다 Y 더함(FC·00·08)
        self.col_dy = rom[cpu(rom, 2, 0xEE5A):cpu(rom, 2, 0xEE5A) + 22]   # 열마다 Y 더함

    def sin(self, a, amp):
        def f(x):
            return amp if x >= 0x57 else (self.sin_tab[x] * amp) >> 8
        if a < 91:
            return f(a)
        if a < 181:
            return f(180 - a)
        if a < 271:
            return -f(a - 180) & 0xFFFF
        return -f(360 - a) & 0xFFFF

    def wave_step(self, wave, a71, counter, base=0, amp=0x30):
        """03:AA92 한 번. 03:99B7 의 MVP 는 A006~A1E3 → A008~A1E5 라 끝 낱말의 높은 바이트(A1E6)는 그대로 남는다."""
        w = [0] + wave[:239]
        w[239] = (wave[238] & 0xFF) | (wave[239] & 0xFF00)
        while a71 >= 360:
            a71 -= 360
        w[0] = (base + self.sin(a71, amp)) & 0xFFFF
        return w, (a71 + 0x10 + (counter & 0x0F)) & 0xFFFF

    @staticmethod
    def bg4_table(a75):
        """02:EC67 이 만드는 7E:A4DC(HDMA 채널 5 → $2113, 모드 2)."""
        v = a75 >> 2
        return (bytes([0x7F, 0, 0, 0x40, 0, 0, 8]) + struct.pack('<H', v >> 2) + bytes([0x10]) + struct.pack('<H', v >> 1)
                + bytes([1]) + struct.pack('<H', v) + b'\0')

    def sparkles(self, head):
        """링 열 head 를 그린 프레임의 OAM 0~11. 02:EB66 이 $08 = head + 1 로 두고, 줄 k(0~2)마다 4개를 한 열씩 뒤로."""
        out = []
        for k in range(3):
            for i in range(4):
                c = head + 1 - i
                if 0 <= c < 22:
                    x, y, _, attr = self.cols[c]
                    tile = 0x142 + 2 * i + (c & 1)
                    out.append((x + 3, (self.col_dy[c] + y + self.spark_dy[k]) & 0xFF, tile & 0xFF, attr | tile >> 8))
                else:
                    out.append((0xF7, 0xF7, None, None))
        return out


REC = 1 + 2 + 2 + 0x1E7 + 16 + 48


def check(title, path):
    d = open(path, 'rb').read()
    fr = []
    for i in range(0, len(d) - REC + 1, REC):
        r = d[i:i + REC]
        t = r[5:5 + 0x1E7]
        fr.append(dict(c=r[0], a71=struct.unpack('<H', r[1:3])[0], a75=struct.unpack('<H', r[3:5])[0], hdr=t[:7],
                       wave=list(struct.unpack('<240H', t[7:487])), bg4=r[5 + 0x1E7:5 + 0x1E7 + 16], oam=r[-48:]))
    # 물결: $75 가 처음 1 이 된 프레임 상태에서 시작해 $75·$075B 만으로 끝까지 진행
    i0 = next(i for i, p in enumerate(fr) if p['a75'] > 0 and p['hdr'] == bytes.fromhex('f807a0f8f7a000'))
    w, a71, a75 = fr[i0]['wave'], fr[i0]['a71'], fr[i0]['a75']
    wave_bad = bg4_bad = 0
    for p in fr[i0 + 1:]:
        while a75 != p['a75']:
            a75 = (a75 + 1) & 0xFFFF
            if (a75 + 1) & 7 == 0:
                w, a71 = title.wave_step(w, a71, p['c'])
        wave_bad += w != p['wave'] or a71 != p['a71']
    for p in fr[i0:]:
        bg4_bad += title.bg4_table(p['a75']) != p['bg4']
    print(f'물결 표: 프레임 {i0 + 1} 부터 {len(fr) - i0 - 1}프레임 중 다름 {wave_bad}')
    print(f'BG4 표($75>0): {len(fr) - i0}프레임 중 다름 {bg4_bad}')

    def match(oam, head):
        e = title.sparkles(head)
        return all((x == 0xF7 and y == 0xF7) if t is None else tuple(oam[4 * q:4 * q + 4]) == (x, y, t, a)
                   for q, (x, y, t, a) in enumerate(e))
    first = next(n for n, p in enumerate(fr) if match(p['oam'], 0))
    heads, bad = [], 0
    for p in fr[first:]:
        h = next((h for h in list(range(22)) + [25] if match(p['oam'], h)), None)
        bad += h is None
        heads.append(h)
    runs = []
    for h in heads:
        if runs and runs[-1][0] == h:
            runs[-1][1] += 1
        else:
            runs.append([h, 1])
    print(f'반짝이: 프레임 {first + 1} 부터 {len(heads)}프레임 중 맞는 머리 열이 없는 프레임 {bad}')
    print('머리 열(25 = 모두 숨김)과 머문 프레임 수:', ' '.join(f'{h}x{n}' for h, n in runs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--check', metavar='TITLEFX_BIN')
    a = ap.parse_args()
    rom = open(a.rom, 'rb').read()
    title = Title(rom)
    if a.check:
        check(title, a.check)
        return
    print('sin 표(03:A88E):', title.sin_tab.hex())
    for h in (0, 10, 21):
        print(f'머리 열 {h} 반짝이:', title.sparkles(h))


if __name__ == '__main__':
    main()
