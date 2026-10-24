"""DQ4(FC) 맵 블록 배치 풀기. 형식은 docs/dq4-map-format.md.

사용:
  python tools/dq4map.py rom/dq4.nes list                  맵 269개: (그룹 $63/순번 $64), 맵 번호, 위치, 크기
  python tools/dq4map.py rom/dq4.nes check                 해제 끝이 다음 맵 시작과 같은지 전수 검사
  python tools/dq4map.py rom/dq4.nes exits G K [--compare end.ram]   출구($05A0 에 들어가는 것)
  python tools/dq4map.py rom/dq4.nes npcs G K [--ram D | --set 6283=80,6282=10] [--night] [--compare D]
                                                           인물(진행 플래그로 고른 목록, D 는 덤프 파일이나 end.* 폴더)
  python tools/dq4map.py rom/dq4.nes lists [G K]           진행 플래그로 고르는 인물 목록 표(1C:$9D0E)
  python tools/dq4map.py rom/dq4.nes G K                   해제한 블록 배치를 16진 격자로
  python tools/dq4map.py rom/dq4.nes G K --compare at.bin  tools/lua/fc/atpc.lua 덤프($7800)와 비교

근거 루틴: 0F:$E549(해제 진입), $E5BF(바탕 채우기), $E588(명령 고르기), $E672(블록 값 정하기),
$E6A1(사각형), $E793(길 그리기), $E86D(점), $E5A3(위 3비트 두 번째 패스), $E618(비트 읽기).
"""
import sys
from pathlib import Path

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


LINKS_PTR = (0x1B, 0x8221)        # 연결 표 포인터(1B:$8101 이 읽음)
STEP = [(0, -1), (1, 0), (0, 1), (-1, 0)]   # 0F:$D22C: 위·오른쪽·아래·왼쪽


def links(prg):
    """연결 표: 10바이트 = 끝점 둘, 끝점마다 (그룹, 순번, X, Y, 플래그). 그룹 FF 로 끝난다."""
    a = rd(prg, *LINKS_PTR) | rd(prg, LINKS_PTR[0], LINKS_PTR[1] + 1) << 8
    out = []
    while rd(prg, 0x1B, a) != 0xFF:
        e = [rd(prg, 0x1B, a + i) for i in range(10)]
        out.append((tuple(e[:5]), tuple(e[5:])))
        a += 10
    return out


def special_group(g, k, flags):
    """1B:$8151: 목적지 그룹 45·40·32 는 이벤트 플래그 $62AA 등으로 순번이 바뀐다(코드 읽기)."""
    if g == 0x45 and k == 5:
        return 7 if flags & 0x02 else 5
    if g == 0x45 and k == 4:
        return 6 if flags & 0x10 else 4
    if g == 0x40:
        return 4 if flags & 0x20 else 3
    return k


def exits(prg, g, k, flags=0):
    """1B:$8101 이 $05A0 에 채우는 출구: (출구 X, Y, 목적지 그룹, 순번, 도착 X, Y, 플래그)."""
    out = []
    for a, b in links(prg):
        for here, there in ((a, b), (b, a)):
            hk = special_group(here[0], here[1], flags) if here[0] == 0x45 else here[1]
            if (here[0], hk) != (g, k):
                continue
            dk = special_group(there[0], there[1], flags)
            ax, ay, f = there[2], there[3], there[4]
            if f & 0x04:
                dx, dy = STEP[f & 3]
                ax, ay = (ax + dx) & 0xFF, (ay + dy) & 0xFF
            out.append((here[2], here[3], there[0], dk, ax, ay, f & 0xC3))
    return out


NPC_BANK = 0x05     # 인물 목록: 05:$8000 + 그룹 × 2 의 포인터부터 순번마다 목록(1C:$9B08)
EVENT_LISTS = (0x1C, 0x9D0E)   # 진행 플래그로 고르는 인물 목록 표의 포인터(1C:$9CC1 이 읽음)
FLAGS = 0x627B                 # 이벤트 플래그 영역(플래그 번호 n = $627B + n)
NIGHT = 0x78                   # $62ED 가 이 값 이상이면 밤(1C:$9BD9)


def records_at(prg, bank, a):
    """bank 의 a 부터 인물 레코드들. 레코드 = 머리 + [F bit4: 블록] + [F bit3: 블록],
    블록은 길이 바이트 + 본문(1C:$9B71). 첫 바이트 00 에서 끝나고, (레코드들, 끝 다음 주소) 를 돌려준다."""
    recs = []
    while (f := rd(prg, bank, a)) != 0:
        n = 7
        if f & 0x10 and f & 0x08:
            n += (0 if f & 1 else 1) + (0 if f & 2 else 1) + (0 if f & 4 else 2)
        size = n
        for bit in (0x10, 0x08):
            if f & bit:
                size += 1 + rd(prg, bank, a + size)
        recs.append(bytes(rd(prg, bank, a + i) for i in range(size)))
        a += size
    return recs, a + 1


def npc_records(prg, g, k):
    """(그룹, 순번) 의 보통 인물 목록(뱅크 05)."""
    a = rd(prg, NPC_BANK, 0x8000 + 2 * g) | rd(prg, NPC_BANK, 0x8001 + 2 * g) << 8
    for _ in range(k + 1):
        recs, a = records_at(prg, NPC_BANK, a)
    return recs


def event_entries(prg):
    """1C:$9D0E 가 가리키는 6바이트 줄(FF 로 끝): (그룹, 순번, 마스크, 플래그 번호, 목록 주소)."""
    b, p = EVENT_LISTS
    a, out = rd(prg, b, p) | rd(prg, b, p + 1) << 8, []
    while rd(prg, b, a) != 0xFF:
        e = [rd(prg, b, a + i) for i in range(6)]
        out.append((e[0], e[1], e[2], e[3], e[4] | e[5] << 8))
        a += 6
    return out


def withdrawn(g, k, flags):
    """1C:$9C6F: 줄을 고른 뒤 보통 목록으로 되돌리는지. flags(n) = $627B+n 바이트.
    $62A5 bit7 이 켜져 있으면 늘 그대로 두고, $6282 bit4 나 $6287 bit7 이 켜져 있을 때
    04/01, 12/02, 03 이 아닌 02/xx, $6295 bit1 이 켜진 15/02 를 되돌린다(04/01 은 $6286 bit0 을 켬)."""
    if flags(0x2A) & 0x80 or not (flags(0x07) & 0x10 or flags(0x0C) & 0x80):
        return False
    return (g, k) in ((0x04, 0x01), (0x12, 0x02)) or (g == 0x02 and k != 0x03) \
        or ((g, k) == (0x15, 0x02) and bool(flags(0x1A) & 0x02))


def pick_list(prg, g, k, flags):
    """1C:$9CC1: (g, k) 이고 플래그 $627B+n & 마스크 가 켜진 첫 줄의 목록 주소(뱅크 1C). 없거나 되돌리면 None."""
    for eg, ek, m, i, a in event_entries(prg):
        if (eg, ek) == (g, k) and flags(i) & m:
            return None if withdrawn(g, k, flags) else a
    return None


def place_records(prg, g, k, flags=None):
    """맵에 들어갈 때 쓰는 목록(1C:$9B00): flags 를 주면 진행 플래그로 고른 목록, 아니면 보통 목록."""
    a = pick_list(prg, g, k, flags) if flags else None
    return records_at(prg, EVENT_LISTS[0], a)[0] if a is not None else npc_records(prg, g, k)


def ram_flags(ram):
    return lambda i: ram[FLAGS + i]


def npcs(prg, g, k, flags=None, night=False):
    """인물 표 슬롯 6~ 에 들어가는 것: 낮은 F bit4, 밤은 F bit3 인 레코드마다
    (X, Y, 방향, 머리 바이트 0~6). 낮 X·Y 는 머리 5·6번째 바이트 bit6-0, 방향은 3번째 바이트 bit1-0(1C:$98ED).
    밤 X·Y 는 F bit2 가 꺼져 있으면 덧붙은 두 바이트(1C:$9907), 방향은 F bit0 이 꺼져 있으면 바이트 7."""
    out = []
    for r in place_records(prg, g, k, flags):
        if not r[0] & (0x08 if night else 0x10):
            continue
        i = 7 + (0 if r[0] & 1 else 1) + (0 if r[0] & 2 else 1) if night and r[0] & 0x10 and not r[0] & 4 else 5
        d = r[7] if night and not r[0] & 1 else r[3]
        out.append({'x': r[i] & 0x7F, 'y': r[i + 1] & 0x7F, 'dir': d & 3, 'head': r[:7].hex(' '), 'size': len(r)})
    return out


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


def cpu_dump(path):
    """CPU $0000-$7FFF 덤프. 폴더면 seq.lua·warp.lua 의 end.ram($0000-$07FF)과 end.sram($6000-$7FFF)을 합친다."""
    p = Path(path)
    if p.is_dir():
        return (p / 'end.ram').read_bytes().ljust(0x6000, b'\0') + (p / 'end.sram').read_bytes()
    return p.read_bytes()


def main():
    a = sys.argv
    prg = ines.prg(open(a[1], 'rb').read())
    if a[2] == 'list':
        for g, k, mid, b, ptr in maps(prg):
            w, h, pb, tb, f = header(prg, b, ptr)
            print(f'{g:02X}/{k:02X} 맵번호 {mid:02X} {b:02X}:{ptr:04X} {w:3d}x{h:<3d} 블록 {tb}비트 0520={f:02X}')
        return
    if a[2] == 'exits':
        g, k = int(a[3], 16), int(a[4], 16)
        for e in exits(prg, g, k):
            print('출구 (%02X,%02X) → %02X/%02X 도착 (%02X,%02X) 플래그 %02X' % e)
        if '--compare' in a:
            ram = open(a[a.index('--compare') + 1], 'rb').read()
            got = [tuple(ram[0x5A0 + 7 * i:0x5A7 + 7 * i]) for i in range(len(exits(prg, g, k)) + 1)]
            want = [tuple(e) for e in exits(prg, g, k)] + [got[-1]]
            ok = got[:-1] == want[:-1] and got[-1][0] == 0xFF
            print('RAM $05A0 과', '같음' if ok else '다름')
            sys.exit(0 if ok else 1)
        return
    if a[2] == 'npcs':
        g, k = int(a[3], 16), int(a[4], 16)
        ram = cpu_dump(a[a.index('--compare') + 1]) if '--compare' in a else \
            cpu_dump(a[a.index('--ram') + 1]) if '--ram' in a else None
        flags = ram_flags(ram) if ram is not None else None
        if '--set' in a:
            sets = {int(x, 16) - FLAGS: int(y, 16) for x, y in (t.split('=') for t in a[a.index('--set') + 1].split(','))}
            flags = lambda i: sets.get(i, 0)
        night = '--night' in a or (ram is not None and ram[0x62ED] >= NIGHT)
        lst = pick_list(prg, g, k, flags) if flags else None
        print(f'{g:02X}/{k:02X} ' + ('밤 ' if night else '낮 ') + (f'진행 목록 1C:{lst:04X}' if lst is not None else '보통 목록'))
        ns = npcs(prg, g, k, flags, night)
        for i, n in enumerate(ns):
            print(f"{i:2d}: ({n['x']:02X},{n['y']:02X}) 방향 {n['dir']}  머리 {n['head']}  {n['size']}바이트")
        if '--compare' in a:
            got = [(ram[0x6F66 + i], ram[0x6F86 + i], ram[0x7006 + i]) for i in range(len(ns))]
            want = [(n['x'], n['y'], n['dir']) for n in ns]
            bad = sum(x != y for x, y in zip(got, want)) + (ram[0x6F66 + len(ns)] != 0xFF and len(ns) < 26)
            used = sum(ram[0x6F66 + i] != 0xFF for i in range(26))
            hidden = sum(ram[0x6F66 + i] == 0x80 for i in range(26))
            print(f'인물 표(슬롯 6~) 와 {len(ns)}명 중 {bad} 다름, 인물 표에서 FF 가 아닌 슬롯 {used}(그중 숨은 80 {hidden})')
            sys.exit(1 if bad else 0)
        return
    if a[2] == 'lists':
        want = (int(a[3], 16), int(a[4], 16)) if len(a) > 4 else None
        for g, k, m, i, p in event_entries(prg):
            if want is None or want == (g, k):
                n = len(records_at(prg, EVENT_LISTS[0], p)[0])
                w = ' (1C:$9C6F 가 되돌릴 수 있음)' if withdrawn(g, k, lambda j: 0x10 if j == 0x07 else 0) else ''
                print(f'{g:02X}/{k:02X} ${FLAGS + i:04X} & {m:02X} → 1C:{p:04X} 레코드 {n}{w}')
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
