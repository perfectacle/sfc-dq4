"""DQ4(FC) 적 조우 표. 형식은 fc/dq4/docs/dq4-encounter-format.md.

사용:
  python fc/dq4/tools/dq4encounter.py rom/dq4.nes maps [--png out.png]   필드 조우 구역 지도(장마다 16×16)
  python fc/dq4/tools/dq4encounter.py rom/dq4.nes zones [Z]               구역 101개: 조우율·무게 줄·칸 14개
  python fc/dq4/tools/dq4encounter.py rom/dq4.nes odds Z [--night|--dungeon]  칸별 확률과 마릿수 범위
  python fc/dq4/tools/dq4encounter.py rom/dq4.nes dungeons                던전 그룹 → 층(순번)마다 구역
  python fc/dq4/tools/dq4encounter.py rom/dq4.nes formations              고정 편성 16개(칸 12·13)
  python fc/dq4/tools/dq4encounter.py rom/dq4.nes bosses                  특수 전투 34개와 부르는 곳
  python fc/dq4/tools/dq4encounter.py rom/dq4.nes check [enc.txt ...]     표 경계 검사, fc/dq4/tools/lua/enc.lua 기록 대조

근거 루틴(뱅크 18): $9BE6(걸음마다 조우 판정), $9C19(필드 구역), $9F79·$A069(던전 구역),
$9C88(구역 레코드), $9CB2·$9CCC·$9CF6(조우율), $9D0E~$9F5D(무리 고르기), $A1AD(특수 전투).
"""
import re
import sys

from kr_patch.fc import ines

import dq4data
import dq4map

BANK = 0x18
ZONE_MAPS = {0: 0xA241, 2: 0xA243, 4: 0xA245}   # $615A(장 − 1) → 구역 지도 포인터. 0·1·3 장은 0 의 것
ZONE_REC, FORMATION, DUNGEON, DUNGEON5, BOSS = 0xA239, 0xA237, 0xA23B, 0xA23D, 0xA23F
TERRAIN_DAY, TERRAIN_NIGHT = 0xA27B, 0xA283     # 지형($7140) 0~7 → 조우율 배수
WEIGHTS = 0xA28D            # 무게 줄 8개 × 18바이트: 칸 14개 무게, 3·4번째 무리 확률 2개, 마릿수 부호 16비트
BASE_RATE = 0xA340          # 구역 바이트 0 bit7-5 → 기본 조우율
AFTER_BATTLE = 0xA33D       # 전투·맵 진입 뒤 처음 3걸음의 배수(그 뒤 16)
GROUP_SIZE = 0xA474         # 그룹마다 맵 수(던전 목록 레코드 길이)
FORM_CNT, FORM_ADD = 0xA31D, 0xA325     # 고정 편성 마릿수 = ADD[c] + rand(CNT[c])
SOLO_CNT, SOLO_ADD = 0xA32D, 0xA335     # 칸 6~10 마릿수 = ADD[c] + rand(CNT[c])
EXTRA_MAX, EXTRA_P = 0xA464, 0xA46C     # 칸 0~4 덧붙는 마리: 합계 상한, 한 마리 더 붙을 확률(/256)
N_ZONES, N_FORMATIONS, N_BOSSES = 0x65, 16, 34
FIELD_FIXED = {(1, 'y<0C'): 0x35, (1, 'y>=0C'): 0x34, (2, ''): 0x36}   # 5장 필드 1·2 는 지도 없이 고정(18:$9C3F)
# 무리 고르기 칸 마스크(18:$9D6B, $9F34). 낮/밤은 걸음 시계 $62ED < 78 / ≥ 78
MASK_FIRST = {'day': 0x1BEF, 'night': 0x3FBE, 'dungeon': 0x3FFF}
MASK_SECOND = {'day': 0x000F, 'night': 0x001E, 'dungeon': 0x001F}


def rd(prg, a):
    return prg[BANK * 0x4000 + (a & 0x3FFF)]


def rw(prg, a):
    return rd(prg, a) | rd(prg, a + 1) << 8


def zone_map(prg, chapter):
    """$615A(0~4) 의 필드 0 구역 지도: 줄 16개 × 칸 16개, 칸 = (X >> 4, Y >> 4). 5장 값의 bit7-6 은 배(코드 읽기)."""
    key = 4 if chapter == 4 else 2 if chapter == 2 else 0
    base = rw(prg, ZONE_MAPS[key])
    rows = 8 if key == 2 else 16     # 3장 지도 뒤 128바이트는 던전 목록이 이어진다
    return base, [[rd(prg, base + 16 * y + x) for x in range(16)] for y in range(rows)]


def zone_at(prg, chapter, x, y):
    base, _ = zone_map(prg, chapter)
    return rd(prg, base + ((y & 0xF0) | (x >> 4))) & 0x3F


def zone(prg, z):
    """구역 레코드 16바이트: 0 = bit7-5 기본 조우율, bit4-2 무게 줄, bit1-0 기습·선제 문턱, 1 = $6E01(구역 레벨), 2~15 = 칸 14개."""
    a = rw(prg, ZONE_REC) + 16 * z
    r = [rd(prg, a + i) for i in range(16)]
    return {'addr': a, 'b0': r[0], 'b1': r[1], 'rate': rd(prg, BASE_RATE + (r[0] >> 5)),
            'row': (r[0] >> 2) & 7, 'slots': r[2:]}


def weights(prg, row):
    return [rd(prg, WEIGHTS + 18 * row + i) for i in range(18)]


def rand_values(n):
    """10:$A1F6: rand(n) = n × r ≫ 8, r 는 $C891 의 8비트. r 이 고르다고 보고 값마다 경우의 수(합 256)."""
    out = {}
    for r in range(256):
        v = (n * r) >> 8
        out[v] = out.get(v, 0) + 1
    return out


def pick(prg, slots, row, mask):
    """18:$9D9C~$9E09: FF 칸을 마스크에서 빼고, 남은 칸 무게 합 S 에서 rand(S)(S=FF 면 $C891 그대로) 를 뽑아
    누적 무게가 그 값 이상이 되는 첫 칸. 칸마다 256 경우 중 몇 번인지."""
    w = weights(prg, row)
    live = [i for i in range(14) if mask >> i & 1 and slots[i] != 0xFF]
    total = sum(w[i] for i in live) & 0xFF
    dist = {}
    rs = {r: 1 for r in range(256)} if total == 0xFF else rand_values(total)
    for r, n in rs.items():
        cum = 0
        for i in live:
            cum += w[i]
            if (cum & 0xFF) >= r:
                dist[i] = dist.get(i, 0) + n
                break
    return dist


def count_range(add, cnt):
    return (add, add + max(cnt - 1, 0))


def outcomes(prg, z, mode='day'):
    """칸 → (종류, 나올 수 있는 무리 [(몬스터 ID 집합, 마릿수 최소, 최대)…]). 18:$9E0D 의 칸 나누기."""
    rec = zone(prg, z)
    s, w = rec['slots'], weights(prg, rec['row'])
    second = {s[i] for i in pick(prg, s, rec['row'], MASK_SECOND[mode])}
    code16 = w[16] | w[17] << 8
    out = {}
    for y in range(14):
        if s[y] == 0xFF:
            continue
        if y < 5:
            # 첫 무리 + 둘째 무리(칸 0~3/1~4 에서 다시 뽑기), w[14]·w[15]/256 확률로 셋째·넷째 무리. 덧붙는 마리는 상한까지
            out[y] = ('무리', [({s[y]}, 1, 8), (second, 1, 8), (second, 0, 8), (second, 0, 8)])
        elif y == 5:
            out[y] = ('우두머리+떼', [({s[y]}, 1, 1), (second, 3, 7)])
        elif y < 11:
            c = code16 >> 3 * (y - 6) & 7
            out[y] = ('한 무리', [({s[y]}, *count_range(rd(prg, SOLO_ADD + c), rd(prg, SOLO_CNT + c)))])
        elif y == 11:
            out[y] = ('한 마리', [({s[y]}, 1, 1)])
        else:
            f = formation(prg, s[y])
            out[y] = (f'편성 {s[y]:02X}', [({m}, lo, hi) for m, lo, hi in f if m != 0xFF])
    return out


def formation(prg, i):
    """6바이트: 0-1 = 무리 4개의 마릿수 부호(3비트씩, 바이트 0 bit2-0·bit5-3, 바이트 1 …), 2-5 = 몬스터 ID(18:$9E19)."""
    a = rw(prg, FORMATION) + 6 * i
    r = [rd(prg, a + k) for k in range(6)]
    out = []
    for g in range(4):
        c = r[g >> 1] >> (3 if g & 1 else 0) & 7
        out.append((r[2 + g], *count_range(rd(prg, FORM_ADD + c), rd(prg, FORM_CNT + c))))
    return out


def dungeon_lists(prg):
    """18:$A069: [그룹, 순번마다 구역…] 레코드, 길이 1 + $A474[그룹], FF 로 끝. (장 1~4 표, 5장 표)."""
    sizes = [rd(prg, GROUP_SIZE + g) for g in range(0x49)]
    out = []
    for ptr in (DUNGEON, DUNGEON5):
        a, recs = rw(prg, ptr), []
        while (g := rd(prg, a)) != 0xFF:
            recs.append((g, [rd(prg, a + 1 + k) for k in range(sizes[g])]))
            a += 1 + sizes[g]
        out.append((rw(prg, ptr), a, recs))
    return out


def bosses(prg):
    """18:$A1AD: A = 번호, 8바이트 = 몬스터 ID 4개 + 마릿수 4개(bit3-0). 마지막 바이트 bit7-6·bit6 은 $6E44 로."""
    out = []
    for i in range(N_BOSSES):
        a = rw(prg, BOSS) + 8 * i
        r = [rd(prg, a + k) for k in range(8)]
        out.append((i, [(r[k], r[4 + k] & 0x0F) for k in range(4) if r[k] != 0xFF], r))
    return out


def boss_callers(prg):
    """LDA #번호 ; BRK 01 8F(뱅크 18 함수 1 = $A1AD) 꼴로 부르는 곳(정적 검색)."""
    out = []
    for m in re.finditer(rb'\xA9(.)\x00\x01\x8F', prg, re.DOTALL):
        o = m.start()
        bank = o // 0x4000
        cpu = (0xC000 if bank in (0x0F, 0x1F) else 0x8000) + o % 0x4000
        out.append((prg[o + 1], bank, cpu))
    return out


ARENA = (0x1C, 0xB024)      # 1C:$AF04: LDA $B024,X (X = $6287 & 7) ; BRK 01 8F. 투기장 상대 5명(07~0B)


def arena_list(prg):
    """1C:$B024 의 특수 전투 번호. 다음 바이트가 코드(20 0B D2 = JSR $D20B)라 07~0B 다섯 개."""
    o = ARENA[0] * 0x4000 + (ARENA[1] & 0x3FFF)
    out = []
    while prg[o] < N_BOSSES and len(out) < 8:
        out.append(prg[o])
        o += 1
    return out


def names(prg):
    return [n for _, n, *_ in dq4data.monsters(prg)]


def mname(nm, m):
    return nm[m] if m < len(nm) else f'{m:02X}?'


def show_maps(prg, png):
    for ch, title in ((0, '1·2·4장'), (2, '3장'), (4, '5장')):
        base, grid = zone_map(prg, ch)
        print(f'# {title} 구역 지도 18:{base:04X} ({len(grid)}줄, 칸 = 필드 16×16)')
        print('    ' + ' '.join(f'{x:X}0' for x in range(16)))
        for y, row in enumerate(grid):
            print(f'{y:X}0  ' + ' '.join(f'{v & 0x3F:02X}' for v in row) + ('   bit7-6: ' + ''.join(str(v >> 6) for v in row) if ch == 4 else ''))
    print('# 5장 필드 1: Y < 0C 이면 구역 35, 아니면 34. 필드 2: 구역 36')
    if png:
        draw_png(prg, png)


def draw_png(prg, path):
    """필드 0 회색조 위에 5장 구역 경계와 번호. work/ 에만 둔다(롬 화면이므로 커밋하지 않음)."""
    from PIL import Image, ImageDraw
    import dq4field
    w, h = dq4field.size(prg, 0)
    grid = dq4field.decode(prg, 0)
    scale = 4
    im = Image.new('RGB', (256 * scale, 256 * scale))
    px = im.load()
    for y in range(h):
        for x in range(w):
            v = dq4field.lookup(grid, w, h, x, y) * 8
            for dy in range(scale):
                for dx in range(scale):
                    px[x * scale + dx, y * scale + dy] = (v, v, v)
    dr = ImageDraw.Draw(im)
    for ch, color in ((0, (255, 80, 80)), (4, (80, 200, 255))):
        _, zm = zone_map(prg, ch)
        for gy, row in enumerate(zm):
            for gx, v in enumerate(row):
                off = 0 if ch == 0 else 8
                dr.text((gx * 16 * scale + 2, gy * 16 * scale + 2 + off * scale), f'{v & 0x3F:02X}', fill=color)
        for i in range(17):
            dr.line([(i * 64, 0), (i * 64, 1024)], fill=(60, 60, 60))
            dr.line([(0, i * 64), (1024, i * 64)], fill=(60, 60, 60))
    im.save(path)


def show_zones(prg, which):
    nm = names(prg)
    for z in which:
        r = zone(prg, z)
        w = weights(prg, r['row'])
        a = ambush_odds(prg, r['b0'] & 3)
        print(f"구역 {z:02X} 18:{r['addr']:04X} 바이트0={r['b0']:02X} 기본율 {r['rate']:02X} 무게줄 {r['row']} "
              f"기습·선제 {a[1]}/256·{a[2]}/256 레벨 {r['b1']:02X} 셋째·넷째 무리 {w[14]}/256·{w[15]}/256")
        for y, m in enumerate(r['slots']):
            if m != 0xFF:
                what = f'편성 {m:02X}' if y >= 12 else mname(nm, m)
                print(f'  칸 {y:2d} 무게 {w[y]:3d} {m:02X} {what}')


def show_odds(prg, z, mode):
    nm = names(prg)
    r = zone(prg, z)
    dist = pick(prg, r['slots'], r['row'], MASK_FIRST[mode])
    out = outcomes(prg, z, mode)
    print(f'구역 {z:02X} ({mode}) 첫 칸 고르기 256 경우')
    for y in sorted(dist):
        kind, groups = out[y]
        desc = ' + '.join('/'.join(mname(nm, m) for m in sorted(ms)) + f' {lo}~{hi}' for ms, lo, hi in groups[:2 if y < 5 else 4])
        print(f'  칸 {y:2d} {dist[y]:3d}/256 {kind}: {desc}')


def check_tables(prg):
    ok = True

    def expect(what, got, want):
        nonlocal ok
        good = got == want
        ok &= good
        print(f'{"같음" if good else "다름"} {what}: {got:04X} / {want:04X}')

    bank_fn = lambda f: rd(prg, 0x8000 + 2 * f) | rd(prg, 0x8001 + 2 * f) << 8
    expect('구역 레코드 끝 = 고정 편성 시작', rw(prg, ZONE_REC) + 16 * N_ZONES, rw(prg, FORMATION))
    expect('고정 편성 끝 = 뱅크 18 함수 02', rw(prg, FORMATION) + 6 * N_FORMATIONS, bank_fn(2))
    expect('특수 전투 끝 = 선제 표 $A45C', rw(prg, BOSS) + 8 * N_BOSSES, 0xA45C)
    expect('1·2·4장 지도 끝 = 5장 지도', rw(prg, ZONE_MAPS[0]) + 256, rw(prg, ZONE_MAPS[4]))
    expect('5장 지도 끝 = 3장 지도', rw(prg, ZONE_MAPS[4]) + 256, rw(prg, ZONE_MAPS[2]))
    expect('3장 지도 128바이트 끝 = 던전 목록', rw(prg, ZONE_MAPS[2]) + 128, rw(prg, DUNGEON))
    expect('그룹 크기 표 끝 = 1·2·4장 지도', GROUP_SIZE + 0x49, rw(prg, ZONE_MAPS[0]))
    lists = dungeon_lists(prg)
    expect('장 1~4 던전 목록 끝(FF 다음) = 5장 목록', lists[0][1] + 1, lists[1][0])
    sizes = {}
    for g, k, *_ in dq4map.maps(prg):
        sizes[g] = sizes.get(g, 0) + 1
    # dq4map.maps 는 다음 그룹 포인터로 길이를 재므로 마지막 그룹(48)이 없다. 그 그룹은 3바이트 레코드가 FF 앞까지
    last = len(sizes)
    a = dq4map.rd(prg, 0x17, dq4map.GROUPS[1] + 2 * last) | dq4map.rd(prg, 0x17, dq4map.GROUPS[1] + 2 * last + 1) << 8
    while dq4map.rd(prg, 0x17, a) != 0xFF:
        sizes[last] = sizes.get(last, 0) + 1
        a += 3
    bad = [f'{g:02X}' for g in range(0x49) if rd(prg, GROUP_SIZE + g) != sizes.get(g, 0)]
    ok &= not bad
    print(f'그룹 크기 $A474 와 맵 표(17:$B181) 그룹별 맵 수: {0x49 - len(bad)}/{0x49} 같음' + (f', 다름 {bad}' if bad else ''))
    used = {v & 0x3F for ch in (0, 2, 4) for row in zone_map(prg, ch)[1] for v in row}
    used |= {z for _, _, recs in lists for _, zs in recs for z in zs if z != 0xFF}
    used |= set(FIELD_FIXED.values())
    print(f'지도·던전 목록이 가리키는 구역 최댓값 {max(used):02X} (< {N_ZONES:02X})')
    ok &= max(used) < N_ZONES
    return ok


MERCHANT = 0xAD             # たびのしょうにん
HOLY = 0xA348               # 성수: 선두 레벨 − 구역 레벨(1~4) → 조우율 배수(/256). 5 이상이면 조우 없음


def expected_zone(prg, lists, ext, x, y):
    """chk·enc 줄의 덧붙은 칸($41 $63 $64 $615A $0515 … $65)으로 구역을 셈. 배($0515=1)면 None(지도 값을 안 씀)."""
    m41, g, k, ch, ship = ext[:5]
    field = ext[9] if len(ext) > 9 else 0
    if m41 & 0x80:
        recs = dict(lists[1 if ch == 4 else 0][2])
        zs = recs.get(g)
        return zs[k] if zs and k < len(zs) else 0xFF
    if ship == 1:
        return None
    if ch == 4 and field == 1:
        return FIELD_FIXED[(1, 'y<0C' if y < 0x0C else 'y>=0C')]
    if ch == 4 and field == 2:
        return FIELD_FIXED[(2, '')]
    return zone_at(prg, ch, x, y)


def expected_rate(prg, z, terr, clock, steps, ext):
    """18:$9CCC·$9CB2(맵 안은 0F)·$A0BA(성수, 필드만)·$9CF6($6BEB ×4). ext 가 없으면 옛 기록(필드, 성수 없음)."""
    mult = rd(prg, AFTER_BATTLE + steps) if steps < 3 else 0x10
    dungeon = bool(ext) and ext[0] & 0x80
    t = 0x0F if dungeon else rd(prg, (TERRAIN_NIGHT if clock >= 0x78 else TERRAIN_DAY) + terr)
    rate = (zone(prg, z)['rate'] * mult * t >> 8) & 0xFF
    if ext and not dungeon and ext[6] & 0x7F:
        lead, lv = ext[10], zone(prg, z)['b1']
        if lead > lv:
            rate = rate * rd(prg, HOLY + lead - lv - 1) >> 8
    if ext and ext[5]:
        rate = rate << 2
    return rate


TOGGLE = 0xA247             # 그룹 3A 순번 0·3 의 조우 켬/끔 칸 표(18:$9FB8)


def toggles(prg, k):
    """그룹 3A 순번 k(0 또는 3)의 칸 표: 2바이트씩 FF 까지. (X, Y) 둘레 네 칸 → 켬(True)/끔."""
    a = TOGGLE + {0: 0, 3: 7}[k]
    out = {}
    while (b0 := rd(prg, a)) != 0xFF:
        b1 = rd(prg, a + 1)
        x, y = b0 & 0x3F, b1 & 0x3F
        for (dx, dy), on in (((0, 0), b0 & 0x80), ((1, 0), b0 & 0x40), ((0, 1), b1 & 0x80), ((1, 1), b1 & 0x40)):
            out.setdefault((x + dx, y + dy), bool(on))
        a += 2
    return out


def toggle_after(prg, k, x, y, bit):
    """18:$9FB8: 순번 0·3 에서 표의 칸을 밟으면 $6E05 bit7 을 그 칸 값으로. 처음 맞는 칸(표 순서)이 이긴다."""
    if k in (0, 3):
        t = toggles(prg, k)
        if (x, y) in t:
            return t[(x, y)]
    return bit


AMBUSH = 0xA45C             # 구역 바이트 0 bit1-0 = k → 문턱 2개(k×2, k×2+1)


def ambush_odds(prg, k):
    """18:$A20E: r = rand(33), r ≤ T0 이면 0(보통), ≤ T1 이면 1(기습: 01DB/01DC), 그 위는 2(선제: 01DF/01E0). 256 경우 중 몇 번."""
    t0, t1 = rd(prg, AMBUSH + 2 * k), rd(prg, AMBUSH + 2 * k + 1)
    out = [0, 0, 0]
    for v, n in rand_values(0x21).items():
        out[0 if v <= t0 else 1 if v <= t1 else 2] += n
    return out


def check_log(prg, path):
    """enc.lua 기록: chk 줄은 구역과 조우율 $0E 예측, enc 줄은 구역·칸·몬스터·마릿수가 표 안에 있는지."""
    bad = n_chk = n_enc = n_hit = n_c55 = n_merchant = n_boss = 0
    seen = {}
    lists = dungeon_lists(prg)
    prev, judged, n_3a = None, False, 0
    tally, last_enc = {}, None
    for line in open(path):
        p = line.split()
        if p[0] == 'stp':
            m41, g, k, x, y, e05 = (int(v, 16) for v in p[1:7])
            if prev:
                # 앞 걸음에서 $6E05 bit7 이 어떻게 됐어야 하는지, 그리고 켜져 있을 때만 판정이 났는지
                want = toggle_after(prg, prev[2], prev[3], prev[4], prev[5] >> 7)
                zs = dict(lists[0][2]).get(0x3A)
                live = zs and zs[prev[2]] != 0xFF
                n_3a += 1
                if (g, m41 & 0x80) == (0x3A, 0x80) and bool(e05 & 0x80) != bool(want) or judged != bool(want and live):
                    bad += 1
                    print(f'다름 그룹 3A 걸음 {prev} → {line.strip()}: bit7 {int(bool(want))}, 판정 {judged}')
            prev = (m41, g, k, x, y, e05) if g == 0x3A and m41 & 0x80 else None
            judged = False
            continue
        if p[0] in ('chk', 'c55'):
            judged = True
        if p[0] in ('enc', 'none', 'boss'):
            prev = None
        if p[0] == 'boss':
            # BOSS=NN 으로 18:$A1AD 를 부른 전투: 무리·마릿수가 특수 전투 표와 같은지, $6E44 bit7·6 이 켜졌는지
            i = int(p[2], 16)
            v = [int(x, 16) for x in p[3:12]]
            table = {n: raw[:4] + [c & 0x0F for c in raw[4:8]] for n, _, raw in bosses(prg)}
            n_boss += 1
            if i == 0xFF:
                # 이벤트가 스스로 부른 특수 전투(BOSS 없이): 같은 무리를 가진 번호
                hits = [f'{n:02X}' for n, t in table.items() if t == v[:8]]
                print(f'이벤트 특수 전투 {line.strip()}: 번호 {"·".join(hits) or "없음"}')
                want = v[:8] if hits else None
            else:
                want = table[i]
            if v[:8] != want or v[8] & 0xC0 != 0xC0:
                bad += 1
                print(f'다름 {line.strip()}: 표 {want}')
            continue
        if p[0] == 'e44' and last_enc is not None:
            v, k = int(p[2], 16), int(p[3], 16) & 3
            tally.setdefault(k, [0, 0, 0])
            if v > 2:
                bad += 1
                print(f'다름 {line.strip()}: $6E44 는 0~2')
            else:
                tally[k][v] += 1
            last_enc = None
            continue
        if p[0] == 'chk':
            x, y, z, terr, clock, steps, rate, rnd = (int(v, 16) for v in p[1:9])
            ext = [int(v, 16) for v in p[9:]]
            n_chk += 1
            n_hit += rnd < rate
            want_zone = expected_zone(prg, lists, ext, x, y) if ext else zone_at(prg, 0, x, y)
            want = expected_rate(prg, z, terr, clock, steps, ext)
            if (want_zone is not None and z != want_zone) or rate != want:
                bad += 1
                print(f'다름 {line.strip()}: 구역 {want_zone if want_zone is None else f"{want_zone:02X}"} 조우율 {want:02X}')
        elif p[0] == 'c55':
            # 18:$9FA0: 맵 안에서 $627D bit4(0F:$CF52 가 지형 종류 $7140 bit7-5 가 바뀐 걸음에 켬)면 난수 < 55
            n_c55 += 1
            n_hit += int(p[3], 16) < 0x55
        elif p[0] == 'enc':
            x, y, z, terr, clock = (int(v, 16) for v in p[2:7])
            slot = int(p[7])
            ids = [int(v, 16) for v in p[8:12]]
            cnt = [int(v, 16) for v in p[12:16]]
            ext = [int(v, 16) for v in p[16:]]
            ch = ext[3] if ext else 0
            n_enc += 1
            mode = 'dungeon' if ext and ext[0] & 0x80 else 'night' if clock >= 0x78 else 'day'
            if slot == -1 and ch == 2 and mode != 'dungeon' and ids == [MERCHANT, 0xFF, 0xFF, 0xFF] and cnt[0] == 1:
                n_merchant += 1        # 18:$9D12: 3장 필드는 rand(10) = 0 이면 무리 고르기 없이 たびのしょうにん 한 마리
                continue
            r = zone(prg, z)
            first = pick(prg, r['slots'], r['row'], MASK_FIRST[mode])
            kind, groups = outcomes(prg, z, mode).get(slot, ('', []))
            want_zone = expected_zone(prg, lists, ext[:5] + [0] * 4 + ext[8:9], x, y) if ext else zone_at(prg, 0, x, y)
            fail = (want_zone is not None and z != want_zone) or slot not in first
            if ext and ext[5] != r['b1']:
                fail = True                 # 18:$9D58: $6E01 = 구역 레코드 바이트 1
            got = [(m, c) for m, c in zip(ids, cnt) if m != 0xFF]
            if len(got) > len(groups) or not got:
                fail = True
            for (m, c), (ms, lo, hi) in zip(got, groups):
                if m not in ms or not (max(lo, 1) <= c <= hi):
                    fail = True
            # 5장의 k 는 BRK 62 33 값(4~8, 코드 읽기)이라 그 범위의 가장 큰 상한으로 본다
            cap = max(rd(prg, EXTRA_MAX + i) for i in range(4, 8)) if ch == 4 else rd(prg, EXTRA_MAX + ch)
            if slot < 5 and sum(c for _, c in got) > max(cap, len(got)):
                fail = True
            seen.setdefault(z, set()).update(m for m, _ in got)
            last_enc = z
            if fail:
                bad += 1
                print(f'다름 {line.strip()}: 칸 {slot} {kind} {groups}')
    for k, n in sorted(tally.items()):
        print(f'$6E44(k={k}): 보통 {n[0]} 기습 {n[1]} 선제 {n[2]}  (기대 /256: {ambush_odds(prg, k)})')
    nm = names(prg)
    for z, ms in sorted(seen.items()):
        print(f'구역 {z:02X}: 나온 몬스터 ' + ', '.join(mname(nm, m) for m in sorted(ms)))
    print(f'{path}: 판정 {n_chk}번' + (f'과 $627D 판정 {n_c55}번' if n_c55 else '') + f'(전투 조건이 맞은 것 {n_hit}번), 전투 {n_enc}번' + (f'(たびのしょうにん {n_merchant}번)' if n_merchant else '') + (f', 그룹 3A 걸음 {n_3a}번' if n_3a else '') + (f', 특수 전투 {n_boss}번' if n_boss else '') + f', 다름 {bad}')
    return bad == 0 and (n_hit == n_enc or n_boss > 0)


def main():
    prg = ines.prg(open(sys.argv[1], 'rb').read())
    cmd, args = sys.argv[2], sys.argv[3:]
    nm = names(prg)
    if cmd == 'maps':
        show_maps(prg, args[args.index('--png') + 1] if '--png' in args else None)
    elif cmd == 'zones':
        show_zones(prg, [int(args[0], 16)] if args else range(N_ZONES))
    elif cmd == 'odds':
        show_odds(prg, int(args[0], 16), 'night' if '--night' in args else 'dungeon' if '--dungeon' in args else 'day')
    elif cmd == 'dungeons':
        for title, (start, end, recs) in zip(('장 1~4', '5장'), dungeon_lists(prg)):
            print(f'# {title} 18:{start:04X}~{end:04X}')
            for g, zs in recs:
                print(f'그룹 {g:02X}: ' + ' '.join('--' if v == 0xFF else f'{v:02X}' for v in zs))
    elif cmd == 'formations':
        for i in range(N_FORMATIONS):
            print(f'편성 {i:02X}: ' + ', '.join(f'{mname(nm, m)} {lo}~{hi}' for m, lo, hi in formation(prg, i) if m != 0xFF))
    elif cmd == 'bosses':
        calls = boss_callers(prg)
        arena = arena_list(prg)
        for i, groups, raw in bosses(prg):
            where = ' '.join(f'{b:02X}:{a:04X}' for n, b, a in calls if n == i)
            if i in arena:
                where += f' 1C:{ARENA[1] + arena.index(i):04X}(표, $6287 & 7 = {arena.index(i)})'.lstrip()
            print(f'{i:02X} ' + ', '.join(f'{mname(nm, m)}×{c}' for m, c in groups)
                  + f'  [{" ".join(f"{v:02X}" for v in raw)}]' + (f'  ← {where}' if where else ''))
        print('# 그 밖에 0F:$DA8A(스크립트 명령: 다음 바이트 = 번호 → BRK 01 8F)가 부름')
    elif cmd == 'check':
        ok = check_tables(prg)
        for path in args:
            ok &= check_log(prg, path)
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
