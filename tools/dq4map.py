"""DQ4(FC) 맵 블록 배치 풀기. 형식은 docs/dq4-map-format.md.

사용:
  python tools/dq4map.py rom/dq4.nes list                  맵 269개: (그룹 $63/순번 $64), 맵 번호, 위치, 크기
  python tools/dq4map.py rom/dq4.nes check                 해제 끝이 다음 맵 시작과 같은지 전수 검사
  python tools/dq4map.py rom/dq4.nes G K                   해제한 블록 배치를 16진 격자로
  python tools/dq4map.py rom/dq4.nes G K --compare at.bin  tools/lua/fc/atpc.lua 덤프($7800)와 비교

근거 루틴: 0F:$E549(해제 진입), $E5BF(바탕 채우기), $E588(명령 고르기), $E672(블록 값 정하기),
$E6A1(사각형), $E793(길 그리기), $E86D(점), $E5A3(위 3비트 두 번째 패스), $E618(비트 읽기).
"""
import sys

from kr_patch.fc import ines

BUF = 0x7800


class Bits:
    """$E618: MSB 부터 한 비트씩. 포인터가 $BFD8 에 닿으면 다음 뱅크 $8000(뱅크 0B 다음은 $801A)."""

    def __init__(self, prg, bank, ptr):
        self.prg, self.bank, self.ptr, self.pos, self.count = prg, bank, ptr, 0, 0

    def bit(self):
        self.count += 1
        if self.count > 1 << 17:
            raise ValueError('끝나지 않음')
        b = self.prg[self.bank * 0x4000 + (self.ptr & 0x3FFF)] >> (7 - self.pos) & 1
        self.pos += 1
        if self.pos == 8:
            self.pos = 0
            self.ptr += 1
            if self.ptr == 0xBFD8:
                self.bank += 1
                self.ptr = 0x801A if self.bank == 0x0B else 0x8000
        return b

    def read(self, n):
        v = 0
        for _ in range(n):
            v = v << 1 | self.bit()
        return v


def decode(prg, bank, ptr, w, h, posbits, tilebits, quad=False):
    """$7800 에 풀리는 w×h 바이트를 돌려준다(해제 직후, 뒤처리 BRK 호출 전)."""
    bits = Bits(prg, bank, ptr)
    buf = bytearray([bits.read(tilebits)]) * (w * h)
    st = {'attr': False, 'quad': quad, 'v': [0, 0, 0, 0], 'tb': tilebits}

    def put(i, v):
        if not 0 <= i < len(buf):
            return
        if st['attr']:
            buf[i] = (buf[i] & 0x1F) | (v << 5 & 0xFF)
        else:
            buf[i] = v

    def put_block(i):
        v = st['v']
        put(i, v[0])
        if st['quad']:
            put(i + 1, v[1])
            put(i + w, v[2])
            put(i + w + 1, v[3])

    def run():
        cmd = bits.read(2)
        while True:
            if cmd == 0:                          # $E672: 블록 값(1개 또는 2×2)을 정하고 다시
                st['quad'] = False
                st['v'][0] = bits.read(st['tb'])
                cmd = bits.read(2)
                if cmd != 0:
                    continue
                if bits.bit():
                    return
                st['quad'] = True
                st['v'][1:] = [bits.read(st['tb']) for _ in range(3)]
                cmd = bits.read(2)
            elif cmd == 1:                        # $E6A1: 두 모서리 위치로 사각형 채우기
                a, b = bits.read(posbits), bits.read(posbits)
                r0, c0 = divmod(a, w)
                r1, c1 = divmod(b, w)
                rows, cols = r1 - r0, c1 - c0
                if st['quad']:
                    rows, cols = rows >> 1, cols >> 1
                if st['attr']:                    # 위 3비트 패스는 2×2 여도 한 칸씩 쓴다($E6F7)
                    for r in range(rows + 1):
                        for c in range(cols + 1):
                            put(a + r * w + c, st['v'][0])
                else:
                    step = 2 if st['quad'] else 1
                    for r in range(rows + 1):
                        for c in range(cols + 1):
                            put_block(a + r * step * w + c * step)
                cmd = bits.read(2)
            else:                                 # $E78A/$E793: 점, 또는 점에서 시작하는 길
                p = bits.read(posbits)
                put_block(p)
                if cmd == 3:
                    cmd = bits.read(2)
                    continue
                d = bits.read(2)
                stack = []
                step = 2 if st['quad'] else 1
                delta = [-w * step, step, w * step, -step]   # 위, 오른쪽, 아래, 왼쪽($E809)
                while True:
                    if not bits.bit():                        # 그 방향으로 한 칸
                        p += delta[d]
                        put_block(p)
                        continue
                    op = bits.read(2)
                    if op == 0:
                        d = (d + 1) & 3
                    elif op == 1:
                        d = (d - 1) & 3
                    elif op == 2:                             # 갈림길: 지금 자리를 쌓고 돌기
                        right = bits.bit()
                        stack.append((p, d))
                        d = (d - 1) & 3 if right else (d + 1) & 3
                    else:
                        if not bits.bit():                    # 새 길
                            p = bits.read(posbits)
                            put_block(p)
                            d = bits.read(2)
                            continue
                        if not stack:
                            break
                        p, d = stack.pop()
                        continue
                    p += delta[d]
                    put_block(p)
                cmd = bits.read(2)

    run()
    n = bits.read(2)                              # $E5A3: 위 3비트 패스
    if n:
        st.update(attr=True, tb=n)
        run()
    decode.end = (bits.bank, bits.ptr, bits.pos)
    return bytes(buf)


GROUPS = (0x17, 0xB181)   # $63 마다 레코드 목록 포인터(BRK 81 7F = 뱅크 17 함수 1 의 주소)


def rd(prg, bank, addr):
    return prg[bank * 0x4000 + (addr & 0x3FFF)]


def data_bank(g, k):
    """0F:$E9AB: (그룹, 순번) 순서로 뱅크 09 → 0A → 0B 에 이어 붙어 있다."""
    if (g, k) < (0x2C, 8):
        return 0x09
    if (g, k) < (0x45, 4):
        return 0x0A
    return 0x0B


def maps(prg):
    """(그룹 $63, 순번 $64, 맵 번호, 데이터 뱅크, 포인터) 목록. 그룹 표는 FFFF 로 끝난다."""
    gp = []
    while (p := rd(prg, *GROUPS[:1], GROUPS[1] + 2 * len(gp)) | rd(prg, GROUPS[0], GROUPS[1] + 2 * len(gp) + 1) << 8) != 0xFFFF:
        gp.append(p)
    out = []
    for g in range(len(gp) - 1):
        for k in range((gp[g + 1] - gp[g]) // 3):
            a = gp[g] + 3 * k
            out.append((g, k, rd(prg, 0x17, a), data_bank(g, k),
                        rd(prg, 0x17, a + 1) | rd(prg, 0x17, a + 2) << 8))
    return out


def header(prg, bank, ptr):
    """0F:$E957: 폭, 높이, 그다음 바이트 bit7-6 + 2 = 블록 비트 수, bit4-0 → $0520. 위치 비트는 폭×높이−1 의 길이."""
    w, h, f = (rd(prg, bank, ptr + i) for i in range(3))
    return w, h, (w * h - 1).bit_length(), (f >> 6) + 2, f & 0x1F


def load(prg, g, k):
    m = next(x for x in maps(prg) if x[:2] == (g, k))
    w, h, pb, tb, _ = header(prg, m[3], m[4])
    return m, w, h, decode(prg, m[3], m[4] + 3, w, h, pb, tb)


def check(prg):
    """맵마다 해제가 끝난 자리가 다음 맵 시작과 같은지(마지막 맵은 뺌)."""
    ms, bad = maps(prg), 0
    for i, (g, k, mid, b, ptr) in enumerate(ms[:-1]):
        w, h, pb, tb, _ = header(prg, b, ptr)
        decode(prg, b, ptr + 3, w, h, pb, tb)
        e = decode.end
        if (e[0], e[1] + (1 if e[2] else 0)) != ms[i + 1][3:]:
            bad += 1
            print(f'{g:02X}/{k:02X}: 끝 {e[0]:02X}:{e[1]:04X} 다음 시작 {ms[i + 1][3]:02X}:{ms[i + 1][4]:04X}')
    print(f'맵 {len(ms)}개, 경계 {len(ms) - 1}곳 중 {bad}곳 다름')
    return bad == 0


def main():
    a = sys.argv
    prg = ines.prg(open(a[1], 'rb').read())
    if a[2] == 'list':
        for g, k, mid, b, ptr in maps(prg):
            w, h, pb, tb, f = header(prg, b, ptr)
            print(f'{g:02X}/{k:02X} 맵번호 {mid:02X} {b:02X}:{ptr:04X} {w:3d}x{h:<3d} 블록 {tb}비트 0520={f:02X}')
        return
    if a[2] == 'check':
        sys.exit(0 if check(prg) else 1)
    g, k = int(a[2], 16), int(a[3], 16)
    m, w, h, buf = load(prg, g, k)
    if '--compare' in a:
        ram = open(a[a.index('--compare') + 1], 'rb').read()
        want = ram[BUF:BUF + w * h]
        diff = [i for i in range(w * h) if buf[i] != want[i]]
        print(f'{g:02X}/{k:02X}: {w * h} 바이트 중 {len(diff)} 차이' + (f', 처음 ({diff[0] % w},{diff[0] // w})' if diff else ''))
        sys.exit(1 if diff else 0)
    for r in range(h):
        print(' '.join(f'{buf[r * w + c]:02X}' for c in range(w)))


if __name__ == '__main__':
    main()
