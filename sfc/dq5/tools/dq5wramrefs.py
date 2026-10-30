"""DQ5(SFC) 롬 전체에서 낮은 WRAM 범위(기본 7E:1ABC~1BB1)에 닿을 수 있는 명령 모양을 모두 찾아 나눈다.
결과는 sfc/dq5/docs/dq5-hangul-format.md 의 「옮긴 레코드를 둘 자리」.

롬의 모든 바이트를 명령 시작으로 보고 아래 모양을 센다(자료 바이트도 들어가므로 거짓 양성이 많다).
  절대(abs·abs,X·abs,Y)   피연산자가 범위 안. 데이터 뱅크가 00~3F·80~BF·7E 면 낮은 WRAM 이다
  롱(long·long,X)         뱅크가 7E 이거나 00~3F·80~BF 의 거울이고 주소가 범위 안
  간접 포인터              JMP (a)·(a,X)·JSR (a,X)·JML [a] 의 a 가 범위 안(그 자리에서 주소를 읽음)
  즉값                     LDA·LDX·LDY #, PEA 의 16비트 값이 범위 안(간접 주소의 바탕이 될 수 있음)
  TCD·PLD                  앞 8바이트의 LDA #·PEA 로 D 를 알 수 없거나, D~D+FF 가 범위에 걸침
  MVN·MVP                  대상 뱅크가 낮은 WRAM 이고, 앞 15바이트의 LDY #·LDA # 로 대상 범위를 알 수 없거나 걸침

나누기: --exec 폴더(lua/dq5execcov.lua 의 exec.txt)로 실행된 바이트인지, --probe 폴더(같은 Lua 의 probe.txt)로
그 자리가 실제 명령 시작으로 실행됐는지를 본다. 실행된 바이트가 하나도 없는 뱅크는 따로 센다.

  uv run --locked python sfc/dq5/tools/dq5wramrefs.py rom/dq5.sfc --exec work/cov/* --positions work/cov/pos.txt
  uv run --locked python sfc/dq5/tools/dq5wramrefs.py rom/dq5.sfc --exec work/cov/* --probe work/cov/*

--cdl cdl.bin --align: dq5cdlsweep.py 로 모은 CDL 의 코드 구간을 기록된 M·X 폭으로 디스어셈블해 후보를 명령 시작·중간·자료·없음으로
나누고, 표시 없는 후보는 디코더·형식 문서의 자료 구조(decoded_ranges·KNOWN), 앞 실행 명령부터 틈 이어 읽기(gap_decode), 모양(pattern)으로 판정한다.
  uv run --locked python sfc/dq5/tools/dq5wramrefs.py rom/dq5.sfc --cdl work/cdlsweep/cdl.bin --align --untouched work/judged.txt
"""
import argparse
import collections
import glob
import os

ABS = dict.fromkeys([0x0D, 0x2D, 0x4D, 0x6D, 0x8D, 0xAD, 0xCD, 0xED, 0x0E, 0x2E, 0x4E, 0x6E, 0xCE, 0xEE, 0x2C, 0x8C, 0x8E,
                     0x9C, 0xAC, 0xAE, 0xCC, 0xEC, 0x0C, 0x1C], 'abs')
ABS.update(dict.fromkeys([0x1D, 0x3D, 0x5D, 0x7D, 0x9D, 0xBD, 0xDD, 0xFD, 0x1E, 0x3E, 0x5E, 0x7E, 0xDE, 0xFE, 0x3C, 0x9E,
                          0xBC], 'abs,X'))
ABS.update(dict.fromkeys([0x19, 0x39, 0x59, 0x79, 0x99, 0xB9, 0xD9, 0xF9, 0xBE], 'abs,Y'))
ABS.update({0x6C: '간접 포인터', 0x7C: '간접 포인터', 0xFC: '간접 포인터', 0xDC: '간접 포인터'})
LONG = dict.fromkeys([0x0F, 0x2F, 0x4F, 0x6F, 0x8F, 0xAF, 0xCF, 0xEF], 'long')
LONG.update(dict.fromkeys([0x1F, 0x3F, 0x5F, 0x7F, 0x9F, 0xBF, 0xDF, 0xFF], 'long,X'))
KINDS = ['abs', 'abs,X', 'abs,Y', 'long', 'long,X', '간접 포인터', '즉값', 'TCD', 'PLD', 'MVN·MVP']


def low_wram_bank(b):
    return b == 0x7E or (b & 0x7F) < 0x40


def scan(d, lo, hi):
    """(종류, 파일 오프셋, 설명) 목록."""
    out = []
    for o in range(len(d) - 3):
        op = d[o]
        w = d[o + 1] | d[o + 2] << 8
        if op in ABS and lo <= w <= hi:
            out.append((ABS[op], o, f'{w:04X}'))
        if op in LONG and lo <= w <= hi and low_wram_bank(d[o + 3]):
            out.append((LONG[op], o, f'{d[o + 3]:02X}:{w:04X}'))
        if op in (0xA9, 0xA2, 0xA0, 0xF4) and lo <= w <= hi:
            out.append(('즉값', o, f'#{w:04X}'))
        if op in (0x5B, 0x2B):
            src = next((d[o - k + 1] | d[o - k + 2] << 8 for k in range(1, 9) if o >= k and d[o - k] in (0xA9, 0xF4)), None)
            if src is None or (src <= hi and src + 0xFF >= lo):
                out.append(('TCD' if op == 0x5B else 'PLD', o, 'D=?' if src is None else f'D={src:04X}'))
        if op in (0x54, 0x44) and low_wram_bank(d[o + 1]):
            y = next((d[o - k + 1] | d[o - k + 2] << 8 for k in range(1, 16) if d[o - k] == 0xA0), None)
            n = next((d[o - k + 1] | d[o - k + 2] << 8 for k in range(1, 16) if d[o - k] == 0xA9), None)
            if y is None or n is None:
                hit = True
            else:
                a, b = (y, y + n) if op == 0x54 else (y - n, y)
                hit = a <= hi and b >= lo
            if hit:
                out.append(('MVN·MVP', o, f'대상 {d[o + 1]:02X}'))
    return out


def cdl_starts(d, cdl):
    """CDL 코드 표시(bit0)가 이어진 구간마다 첫 바이트부터, 그 바이트에 적힌 실행 때 폭(bit5 M 8비트, bit4 X 8비트)으로
    명령 길이를 따라가 명령 시작 자리를 모은다. 구간 끝을 넘는 구간 수와, 점프 대상 표시(bit2)인데 시작이 아닌 자리 수도 낸다."""
    from kr_patch.sfc.dis65816 import decode
    from kr_patch.sfc.mapper import LoROM
    mapper = LoROM()
    starts, over = set(), 0
    n = min(len(d), len(cdl))
    o = 0
    while o < n:
        if not cdl[o] & 1:
            o += 1
            continue
        end = o
        while end < n and cdl[end] & 1 and (end == o or end % 0x8000):
            end += 1
        while o < end:
            f = cdl[o]
            starts.add(o)
            o += decode(d, cpu(o), m8=bool(f & 0x20), x8=bool(f & 0x10), mapper=mapper)[1]
        if o != end:
            over += 1
    missed = sum(1 for i in range(n) if cdl[i] & 4 and cdl[i] & 1 and i not in starts)
    return starts, over, missed


# 형식 문서에 「빈틈없이 이어진다」 고 적힌 자료 덩어리(CPU 주소, [시작, 끝)). 이 안의 바이트는 그 형식의 자료다.
KNOWN = [
    ('전투 메시지 자료', 0x078000, 0x07980E),    # dq5battletext.py: 색인 24:AECD 의 첫 값이 07:8000, 글자 그림 앞까지
    ('글자 그림', 0x07980E, 0x07D77C),           # dq5-text-format.md: 1bpp, 07:980E~07:D77B
    ('메시지 자료', 0x07D77C, 0x0C8020),         # dq5-text-format.md: 3,200개가 07:D77C~0C:8020 에 이어짐
    ('인물 목록', 0x058651, 0x05D4B1),           # dq5-map-format.md: 54개 그룹 목록이 05:8651~D4B1 에 빈틈없이
    ('대체 인물 목록', 0x108000, 0x10DDB1),       # dq5-map-format.md: 대체 목록이 10:8000~DDB1 에 빈틈없이
    # dq5-data-format.md: 몬스터 23:8000, 구역 23:96F3 + 85 x 22 = 9E41, 성장 9E41 + 11 x 0x50 = A1B1, + 42 x 0x50 = AED1
    ('몬스터·구역·성장 표', 0x238000, 0x23AED1),
    ('물건 표', 0x23B081, 0x23B819),             # dq5-data-format.md: 물건 표 23:B081~B818
    ('주문 습득·목록', 0x23B819, 0x23C014),       # dq5-data-format.md: 23:B819~C013
    ('이름 표', 0x23C242, 0x23D6A1),             # dq5-text-format.md: 표마다 끝이 다음 표 시작과 바이트째 맞음
    ('필드 조우 격자', 0x23F1FC, 0x23F54E),
    # dq5-text-format.md·dq5text.window: 창 레코드는 주소 순으로 이어짐. 첫 레코드 04:ED04 부터 마지막 레코드 시작 04:FA34 까지
    ('창 레코드', 0x04ED04, 0x04FA34),
    ('상점 목록', 0x04FBDD, 0x04FD55),           # dq5-data-format.md: 04:FBDD~FD54 에 빈틈없이
    ('맵 레코드', 0x0F8F43, 0x0FCF68),           # dq5-map-format.md: 레코드는 0F:8F43 ~ 0F:CF68
    ('출구·영역 이동 표', 0x2AD812, 0x2AF224),     # dq5-build-format.md: 원래 표 자리 2A:D812~2A:F223
    ('엔딩 스태프 롤', 0x1EF5B8, 0x1EFEEC),       # dq5-text-format.md: 1E:F5B8~1E:FEEB(F5 로 끝)
    ('행동 → 연출 번호 표', 0x268BE0, 0x268C75),  # dq5fx.py: 26:8BE0 [행동] 95개
    ('인물 놓지 않는 표', 0x12839C, 0x12839C + 43 * 4),   # dq5-map-format.md: 12:839C 43개 x [BC][BD][플래그][마스크]
    ('대체 인물 목록 표', 0x128449, 0x128449 + 296 * 6),  # dq5-map-format.md: 12:8449 296개 x 6바이트
    ('타이틀 바다 타일맵 바이트', 0x03A478, 0x03A478 + 128),  # dq5-graphics-format.md: 03:A40A 가 03:A478 의 바이트 128개를 읽음       # dq5-data-format.md: F1FC 17x7, F273·F394 17x17, F4B5 17x5, F50A 17x4
]


def decoded_ranges(d):
    """디코더가 실제로 읽어 내는 자료의 (이름, 시작 파일 오프셋, 끝 파일 오프셋). 대화 스크립트 574개(dq5talk.py 의
    경계 검사와 같은 읽기), 필드 인물 스프라이트 세트의 레코드·런 길이 타일과 맵 OBJ 타일(dq5sprite.py)."""
    import dq5sprite
    import dq5talk
    from dq5map import Rom
    rom = Rom(d)
    out = []
    for n in range(dq5talk.FIRST_SPECIAL2 - dq5talk.FIRST_SCRIPT):
        a = dq5talk.script_address(rom, n)
        out.append(('대화 스크립트', off(a), off(dq5talk.parse_script(rom, a)[1])))
    for k in dq5sprite.set_numbers(rom):
        rec = dq5sprite.set_record(rom, k)
        if rec:
            out.append(('스프라이트 레코드', off(rec['record']), off(rec['record']) + 0x34))
            out.append(('스프라이트 타일', off(rec['data']), off(dq5sprite.set_tiles(rom, rec)[1])))
    for m in dq5sprite.map_objects(rom):
        out.append(('맵 OBJ 타일', off(m['data']), off(m['end'])))
    # 그룹 50 이상 맵의 CHR(1F:8000 + 번호 x 32, 01:8C15 가 DMA). 블록 표(17:8369~)가 쓰는 가장 큰 번호까지
    import dq5map
    top, blocks = 0, dq5map.high_block_table(rom)
    for a in blocks:
        b0 = rom.u8(a)
        n = ((b0 & 7) + 1) * (((b0 >> 3) & 7) + 1)
        out.append(('그룹 50 이상 블록', off(a), off(a) + 3 + n * 2))
        for i in range(n):
            top = max(top, rom.u16(a + 3 + 2 * i) & 0x0FFF)
    out.append(('그룹 50 이상 CHR', off(0x1F8000), off(0x1F8000) + (top + 1) * 32))
    # 전투 몬스터 그림(dq5mongfx.py: 27:E5DC 레코드, 머리부터 타일 자료 끝까지)
    import dq5mongfx
    for m in range(dq5mongfx.COUNT):
        rec = 0x270000 | rom.u16(dq5mongfx.RECORDS + m * 2)
        out.append(('몬스터 그림 레코드', off(rec), off(rec) + 2 + rom.u8(rec + 1) * 2))
        g = dq5mongfx.decode(rom, rom.u8(rec))
        out.append(('몬스터 그림', off(g['head']), off(g['end'])))
    # 전투 주문·특기 연출 조각과 색 묶음(dq5gfx.py 의 effect_lists·effect_cel·effect_colors 와 같은 읽기)
    import dq5gfx
    for n in range(dq5gfx.EFFECT_COUNT):
        lists = dq5gfx.effect_lists(rom, n)
        if lists:
            for obj, cels in ((False, lists[0]), (True, lists[1])):
                for a in cels:
                    out.append(('연출 조각', off(a), off(a) + effect_cel_size(rom, a, obj)))
        p = rom.u16(dq5gfx.EFFECT_COLORS + n * 2)
        if p != 0xFFFF:
            a = 0x290000 | p
            for _ in range(2 if rom.u8(a - 1) & 0xF0 else 1):
                k = rom.u8(a)
                out.append(('연출 색', off(a), off(a) + 1 + k * 2))
                a += 1 + k * 2
    # 전투 배경 49개(dq5battlebg.py): 그림 A·B, 목록 1~3(FF 까지), 시대마다의 팔레트 레코드
    import dq5battlebg as bb
    def flist(a):
        e = a
        while rom.u8(e) != 0xFF:
            e += 2
        return off(a), off(e) + 1
    lists = {bb.ALT_LIST2}
    for n in range(0x31):
        k = bb.entry(rom, n)[0]
        for pa in (0x280000 | rom.u16(bb.PICS + k), 0x280000 | rom.u16(bb.PICS + k + 2)):
            out.append(('전투 배경 그림', off(pa), off(bb.picture(rom, pa)[3])))
        x = k + (k >> 1)
        lists |= {0x280000 | rom.u16(bb.LISTS + x + i) for i in (0, 2, 4)}
        for kk in {k, k + 2} | ({k + 0x98, k + 0xB4} if k < 0x1E else set()):
            pp = 0x280000 | rom.u16(bb.PALS + kk)
            q = pp + 2
            for _ in range(rom.u8(pp)):
                q += 1 + rom.u8(q) * 2
            out.append(('전투 배경 팔레트', off(pp), off(q)))
    for a in lists:
        out.append(('전투 배경 목록', *flist(a)))
    # 목록에 없는 조각: 아는 조각의 끝에서 조각을 이어 풀어 다음 아는 조각 시작에 꼭 맞게 닿을 때만 받는다(조각은 차례로 이어짐)
    cels = sorted((x, y) for name, x, y in out if name == '연출 조각')
    starts = {x for x, _ in cels}
    for _, e in cels:
        if e in starts:
            continue
        nxt = min((x for x in starts if x > e), default=None)
        if nxt is None or nxt - e > 0x1000:
            continue
        for obj in (False, True):
            p, chain = e, []
            while p < nxt:
                a = (p // 0x8000) << 16 | 0x8000 | p % 0x8000
                n = effect_cel_size(rom, a, obj)
                chain.append((p, p + n))
                p += n
            if p == nxt:
                out += [('연출 조각(목록 밖, 이어 풂)', x, y) for x, y in chain]
                break
    # 이름 표 3(22:8000, [길이][바이트] 171개, dq5-text-format.md)
    a = 0x228000
    for _ in range(171):
        a += 1 + rom.u8(a)
    out.append(('이름 표 3', off(0x228000), off(a)))
    # 실내 맵 블록(16:8000 부터 빈틈없이, dq5map.block_table)
    for a in dq5map.block_table(rom):
        b0 = rom.u8(a)
        out.append(('실내 맵 블록', off(a), off(a) + 3 + ((b0 & 7) + 1) * (((b0 >> 3) & 7) + 1) * 2))
    # 탈것 그림(dq5sprite.VEHICLES): 압축 타일과 칸 표(16:F7D9 가 WRAM 으로 옮기는 범위, 그리는 블록보다 길다)
    for v in dq5sprite.VEHICLES:
        for a, _, _ in v['tiles']:
            out.append(('탈것 타일', off(a), off(dq5sprite.unpack(rom, a, False)[1])))
        for part in dq5sprite.vehicle_parts(rom, v):
            out.append(('탈것 칸 표', off(part['rom']), off(part['rom']) + part['copied']))
    # 상자·조사 보상 고정 표(dq5chestwrite.TABLES, 끝의 FFFF 포함)
    import dq5chestwrite
    for name, (start, count, size) in dq5chestwrite.TABLES.items():
        out.append(('보상 표', off(start), off(start) + count * size + (0 if name == 'chests' else 2)))
    # 필드(dq5field.py): 세 세계의 지도·9번째 비트 RLE, 필드 BG 타일 RLE, 블록 정의(층마다 511 x 5바이트)
    import dq5field
    for a in [x for w in dq5field.WORLDS for x in w] + [dq5field.FIELD_CHR]:
        out.append(('필드 RLE', off(a), off(dq5field.rle(rom, a)[1])))
    out.append(('필드 블록 정의', off(dq5field.BLOCK_LOWER), off(dq5field.BLOCK_UPPER) + 511 * 5))
    for a, n in fx_script_ranges(rom):
        out.append(('연출 스크립트', off(a), off(a) + n))
    return out


# 전투 연출 스크립트(22:D8FE) 명령 길이. dq5-graphics-format.md 「전투 주문·특기 연출」 의 명령표. 00~1F(+40·80)는 3바이트
FX_LEN = {0x20: 1, 0x21: 1, 0x22: 1, 0x23: 1, 0x24: 1, 0x25: 1, 0x26: 1, 0x27: 2, 0x28: 3, 0x29: 2, 0x2A: 2, 0x2B: 4,
          0x2C: 5, 0x2D: 5, 0x2E: 3, 0x2F: 1, 0x30: 4, 0x31: 3, 0x32: 4, 0x33: 1, 0x34: 2, 0x35: 1, 0x36: 1, 0x37: 1,
          0x38: 3, 0x39: 3, 0x3A: 1, 0x3B: 1, 0x3C: 3, 0x3D: 3, 0x3E: 3, 0x3F: 1}


def fx_walk(rom, starts):
    """연출 스크립트를 흐름대로 따라가 [(명령 주소, 길이)] 와 모르는 명령 수, 32 명령의 표 주소를 돌려준다."""
    seen, out, bad, tables, todo = set(), [], 0, set(), list(starts)
    while todo:
        a = todo.pop()
        while a not in seen:
            seen.add(a)
            op = rom.u8(a)
            n = 3 if op & 0x3F < 0x20 else FX_LEN.get(op)
            if n is None:
                bad += 1
                break
            out.append((a, n))
            if op == 0x2B:
                todo.append(0x240000 | rom.u16(a + 2))
            elif op in (0x2C, 0x2D):
                todo.append(0x240000 | rom.u16(a + 3))
            elif op == 0x2E:
                todo.append(0x240000 | rom.u16(a + 1))
            elif op == 0x32:
                tables.add(0x240000 | rom.u16(a + 2))
            if op == 0x3D:
                a = 0x240000 | rom.u16(a + 1)
                continue
            if op in (0x3F, 0x2F):
                break
            a += n
    return out, bad, tables


def fx_script_ranges(rom):
    """22:D7AA 의 연출 스크립트(A9 까지)를 따라간 명령들. 32 명령의 표는 칸 수가 롬에 없어, 칸이 가리키는 곳을
    따로 따라가 모르는 명령 없이 끝나는 동안만 칸으로 받는다."""
    starts = [0x240000 | rom.u16(0x22D7AA + n * 2) for n in range(0xAA) if rom.u16(0x22D7AA + n * 2) != 0xFFFF]
    done, extra = set(), []
    while True:
        cmds, _, tables = fx_walk(rom, starts + extra)
        new = False
        for t in tables - done:
            done.add(t)
            k = t
            while rom.u16(k) >= 0x8000 and fx_walk(rom, [0x240000 | rom.u16(k)])[1] == 0:
                cmds.append((k, 2))
                extra.append(0x240000 | rom.u16(k))
                k += 2
                new = True
        if not new:
            return fx_walk(rom, starts + extra)[0] + [(t + 2 * i, 2) for t in done for i in range(table_len(rom, t))]


def table_len(rom, t):
    k = t
    while rom.u16(k) >= 0x8000 and fx_walk(rom, [0x240000 | rom.u16(k)])[1] == 0:
        k += 2
    return (k - t) // 2


def effect_cel_size(rom, a, obj):
    """dq5gfx.effect_cel 과 같은 차례로 조각 하나를 읽고 그 길이를 돌려준다."""
    from dq5mongfx import Stream, tile
    s = Stream(rom, a)
    b = s.u8(0)
    w, h = (b >> 4) + 1, (b & 15) + 1
    cells = [i for i in range(w * h) if s.u8(1 + i // 8) >> (7 - i % 8) & 1]
    nib_at = 1 + (w * h + 7) // 8
    pos = [nib_at + ((len(cells) + 1) // 2 if obj else 0)]
    for k in range(len(cells)):
        nib = s.u8(nib_at + k // 2) >> (0 if k & 1 else 4) & 15 if obj else 0
        if nib & 0xC:
            pos[0] += 1
        else:
            for _ in range(4 if nib & 2 else 1):
                tile(s, pos)
    return pos[0]


def off(a):
    return (a >> 16 & 0x7F) * 0x8000 + (a & 0x7FFF)


def gap_decode(d, cdl, cs, o, brk_args):
    """CDL 표시가 없는 자리 o 가 든 틈을, 같은 뱅크에서 바로 앞의 실행된 명령부터 이어 읽는다(리스팅 판정).
    폭은 그 명령의 CDL 폭에서 시작해 REP·SEP 로 바꾸고, BRK 는 서비스 번호마다의 인자 수(dq5talk.brk_args), COP 는 1바이트를
    건너뛴다. 무조건 분기·끝 명령 뒤에도 이어 읽는다(다음 루틴이 바로 붙는 일이 많음). 자료 표시 바이트를 만나면 멈춘다.
    돌려주는 값: (판정, 틈 끝이 다음 실행 명령 시작과 맞았는지). 판정은 '명령 시작'·'명령 중간'·'자료에서 끊김'·'앞 코드 없음'."""
    from kr_patch.sfc.dis65816 import decode
    from kr_patch.sfc.mapper import LoROM
    mapper = LoROM()
    base = o - o % 0x8000
    s = o - 1
    while s >= base and s not in cs:
        if cdl[s] & 2:
            return '자료에서 끊김', None
        s -= 1
    if s < base:
        return '앞 코드 없음', None
    m8, x8 = bool(cdl[s] & 0x20), bool(cdl[s] & 0x10)
    p, verdict = s, None
    while p < base + 0x8000:
        if p > s and cdl[p] & 1:
            return verdict or '명령 중간', p in cs
        if p > s and cdl[p] & 2:
            return verdict or '자료에서 끊김', None
        if p == o:
            verdict = '명령 시작'
        op = d[p]
        n = decode(d, cpu(p), m8=m8, x8=x8, mapper=mapper)[1]
        if op == 0x00:
            n = 2 + brk_args(d[p + 1])
        elif op == 0xC2:
            m8, x8 = m8 and not d[p + 1] & 0x20, x8 and not d[p + 1] & 0x10
        elif op == 0xE2:
            m8, x8 = m8 or bool(d[p + 1] & 0x20), x8 or bool(d[p + 1] & 0x10)
        if verdict is None and p < o < p + n:
            verdict = '명령 중간'
        p += n
    return verdict or '명령 중간', None


def boundary_decode(d, cdl, cs, o, brk_args):
    """자료 표시 바로 뒤 바이트를 명령 시작으로 보고 다음 실행 명령까지 네 가지 M·X 폭으로 읽는다. 다음 실행 명령 시작에 꼭
    닿는 폭들이 모두 후보를 명령 중간으로 읽으면 '명령 중간', 그 밖은 None. 1바이트 명령처럼 읽히는 자료(2B 2B 2A …)도
    명령 시작으로 이어지므로 명령 시작 판정은 쓰지 않는다."""
    from kr_patch.sfc.dis65816 import decode
    from kr_patch.sfc.mapper import LoROM
    mapper = LoROM()
    base = o - o % 0x8000
    i = o - 1
    while i >= base and not cdl[i] & 3:
        i -= 1
    j = o + 1
    while j < base + 0x8000 and not cdl[j] & 3:
        j += 1
    if j >= base + 0x8000 or j not in cs:
        return None
    verdicts = set()
    for m8 in (False, True):
        for x8 in (False, True):
            p, v, mm, xx = i + 1, None, m8, x8
            while p < j:
                if p == o:
                    v = '명령 시작'
                op = d[p]
                n = 2 + brk_args(d[p + 1]) if op == 0x00 else decode(d, cpu(p), m8=mm, x8=xx, mapper=mapper)[1]
                if op == 0xC2:
                    mm, xx = mm and not d[p + 1] & 0x20, xx and not d[p + 1] & 0x10
                elif op == 0xE2:
                    mm, xx = mm or bool(d[p + 1] & 0x20), xx or bool(d[p + 1] & 0x10)
                if v is None and p < o < p + n:
                    v = '명령 중간'
                p += n
            if p == j:
                verdicts.add(v)
    return '명령 중간' if verdicts == {'명령 중간'} else None


def pattern(d, cdl, o, brk_args=None):
    """실측이 아닌 모양 판정(문서에는 「보임」 으로 적는다). 앞뒤 가장 가까운 CDL 표시가 모두 자료이고 그 틈이 16바이트
    이하면 '짧은 자료 틈', 피연산자 둘레(-8~+10)에 1씩 느는 바이트 6개 이상이나 같은 간격으로 느는 16비트 값 5개 이상이
    이어지면 '증가 수열'. 바로 앞 1~3바이트에 BRK 와 서비스 번호가 있고 그 인자 바이트가 후보를 덮으면 'BRK 인자 안'
    (코드라면 BRK 의 인자, 자료라면 명령이 아님). 모두 아니면 None."""
    base = o - o % 0x8000
    i = o - 1
    while i >= base and not cdl[i] & 3:
        i -= 1
    j = o + 1
    while j < base + 0x8000 and not cdl[j] & 3:
        j += 1
    if i >= base and j < base + 0x8000 and cdl[i] & 2 and cdl[j] & 2 and not cdl[i] & 1 and not cdl[j] & 1 \
            and j - i - 1 <= 16:
        return '짧은 자료 틈'
    if brk_args:
        for k in range(1, 4):
            if d[o - k - 1] == 0x00 and k <= brk_args(d[o - k]):
                return 'BRK 인자 안'
    w = d[o - 8:o + 11]
    run = best = 1
    for k in range(1, len(w)):
        run = run + 1 if w[k] == (w[k - 1] + 1) & 0xFF else 1
        best = max(best, run)
    if best >= 6:
        return '증가 수열'
    for ph in (0, 1):
        v = [w[k] | w[k + 1] << 8 for k in range(ph, len(w) - 1, 2)]
        run = 1
        for k in range(2, len(v)):
            run = run + 1 if v[k] - v[k - 1] == v[k - 1] - v[k - 2] != 0 else 1
            if run + 1 >= 5:
                return '증가 수열'
    return None


def cpu(o):
    return (o // 0x8000) << 16 | 0x8000 | o % 0x8000


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('--range', default='1ABC-1BB1')
    ap.add_argument('--exec', nargs='*', default=[], help='exec.txt 가 든 폴더들')
    ap.add_argument('--probe', nargs='*', default=[], help='probe.txt 가 든 폴더들')
    ap.add_argument('--cdl', help='lua/dq5execcov.lua CDL=1 의 cdl.bin. 미실행 후보를 CDL 코드·자료·없음으로 더 나눔')
    ap.add_argument('--align', action='store_true', help='--cdl 과 함께: 모든 후보를 CDL 코드 구간을 실행 폭으로 디스어셈블한 '
                    '명령 시작·명령 중간·자료·없음으로 나누고, 명령 시작인 후보를 찍음')
    ap.add_argument('--untouched', help='--align 과 함께: CDL 표시가 없는 후보와 판정을 이 파일에 씀')
    ap.add_argument('--positions', help='실행된 후보 자리를 CPU 주소(00~3F 와 80~BF 거울 둘 다)로 이 파일에 씀(POSFILE 용)')
    a = ap.parse_args()
    d = open(a.rom, 'rb').read()
    lo, hi = (int(x, 16) for x in a.range.split('-'))
    ex = set()
    for f in a.exec:
        p = os.path.join(f, 'exec.txt')
        if os.path.exists(p):
            ex |= {int(line.split()[0], 16) for line in open(p) if line.strip()}
    starts = collections.defaultdict(list)
    for f in a.probe:
        p = os.path.join(f, 'probe.txt')
        if os.path.exists(p):
            for line in open(p):
                if line.strip():
                    starts[int(line.split()[0], 16)].append(line.split(None, 1)[1].strip())
    bank_exec = collections.Counter(o // 0x8000 for o in ex)
    cands = scan(d, lo, hi)
    if a.positions:
        pos = sorted({o for _, o, _ in cands if o in ex})
        with open(a.positions, 'w') as f:
            f.write(','.join(f'{cpu(o) | m:06X}' for o in pos for m in (0, 0x800000)))
        print(f'실행된 후보 자리 {len(pos)}곳 -> {a.positions}')
    rows = {k: [0] * 5 for k in KINDS}
    for k, o, _ in cands:
        r = rows[k]
        r[0] += 1
        if o in ex:
            r[1 if cpu(o) in starts else 2] += 1
        else:
            r[3 if bank_exec[o // 0x8000] == 0 else 4] += 1
    print(f'실행된 롬 바이트 {len(ex)}, 실행된 뱅크 {len(bank_exec)}')
    print('| 모양 | 후보 | 실행된 명령 시작 | 실행된 다른 명령 중간 | 실행 코드가 없는 뱅크 | 코드가 있는 뱅크의 미실행 |')
    print('| --- | --- | --- | --- | --- | --- |')
    for k, r in rows.items():
        print(f'| {k} | ' + ' | '.join(f'{v:,}' for v in r) + ' |')
    print('| 합계 | ' + ' | '.join(f'{sum(r[i] for r in rows.values()):,}' for i in range(5)) + ' |')
    if a.cdl:
        cdl = open(a.cdl, 'rb').read()
        sub = collections.Counter()
        for k, o, _ in cands:
            if o in ex:
                continue
            f = cdl[o] if o < len(cdl) else 0
            where = '자료 뱅크' if bank_exec[o // 0x8000] == 0 else '코드 뱅크'
            sub[(k in KINDS[:7], where, '코드' if f & 1 else '자료' if f & 2 else '없음')] += 1
        print('\n미실행 후보의 CDL(직접 피연산자 여부, 뱅크, CDL):')
        for key, v in sorted(sub.items()):
            print(f'  {"직접" if key[0] else "값 모름"} {key[1]} {key[2]}: {v:,}')
        print('\nCDL 이 코드라 한 직접 피연산자 후보(정렬된 디스어셈블로 명령 중간인지 볼 것):')
        for k, o, det in cands:
            if o not in ex and k in KINDS[:7] and o < len(cdl) and cdl[o] & 1:
                print(f'  {cpu(o) >> 16:02X}:{cpu(o) & 0xFFFF:04X} {k} {det} {d[o:o + 4].hex(" ")}')
    if a.align:
        cdl = open(a.cdl, 'rb').read()
        cs, over, missed = cdl_starts(d, cdl)
        print(f'\nCDL 코드 구간 디스어셈블: 명령 시작 {len(cs):,}, 끝을 넘은 구간 {over}, 시작이 아닌 점프 대상 {missed}')
        cls = collections.Counter()
        hits, untouched = [], []
        for k, o, det in cands:
            f = cdl[o] if o < len(cdl) else 0
            c = '명령 시작' if o in cs else '명령 중간' if f & 1 else '자료' if f & 2 else '없음'
            cls[(k in KINDS[:7], c)] += 1
            if c == '명령 시작':
                hits.append((k, o, det))
            if c == '없음':
                untouched.append((k, o, det))
        print('| 후보 | 명령 시작 | 명령 중간 | 자료 | 없음 |')
        print('| --- | --- | --- | --- | --- |')
        for direct in (True, False):
            print(f'| {"직접 피연산자" if direct else "값 모름(TCD·PLD·MVN·MVP)"} | '
                  + ' | '.join(f'{cls[(direct, c)]:,}' for c in ('명령 시작', '명령 중간', '자료', '없음')) + ' |')
        print('\nCDL 상 명령 시작인 후보:')
        for k, o, det in hits:
            print(f'  {cpu(o) >> 16:02X}:{cpu(o) & 0xFFFF:04X} {k} {det} {d[o:o + 4].hex(" ")} P={cdl[o] & 0x30:02X}')
        dec = decoded_ranges(d)
        import dq5talk
        from dq5map import Rom
        rom = Rom(d)
        ba = lambda n: dq5talk.brk_args(rom, n)  # noqa: E731
        judged = collections.Counter()
        rows2 = []
        import bisect
        spans = sorted([(x, y, name) for name, x, y in dec] + [(off(x), off(y), name) for name, x, y in KNOWN])
        keys = [x for x, _, _ in spans]

        def inside(o):
            i = bisect.bisect_right(keys, o)
            for x, y, name in reversed(spans[max(0, i - 64):i]):
                if x <= o < y:
                    return name
            return None
        for k, o, det in untouched:
            name = inside(o)
            if name:
                j = name + ' 안'
            else:
                v, landed = gap_decode(d, cdl, cs, o, ba)
                j = v + ('' if landed is None else ', 틈 끝 맞음' if landed else ', 틈 끝 어긋남')
                pat = pattern(d, cdl, o, ba) if v != '명령 중간' else None
                if pat:
                    j = pat + ' 보임(' + j + ')'
                elif v in ('자료에서 끊김', '앞 코드 없음'):
                    bv = boundary_decode(d, cdl, cs, o, ba)
                    if bv:
                        j = '자료 뒤부터 읽으면 ' + bv + ' 보임'
            judged[(k in KINDS[:7], j)] += 1
            rows2.append((k, o, det, j))

        def coarse(j):
            return ('명령 시작' if j.startswith('명령 시작') else
                    '명령 중간' if j.startswith('명령 중간') else
                    '모양으로 자료 보임' if '보임' in j else '자료 구조 안' if j.endswith(' 안') else '미정')
        cols = ('자료 구조 안', '명령 중간', '모양으로 자료 보임', '명령 시작', '미정')
        print('\nCDL 표시가 없는 후보의 판정(디코더·형식 문서의 자료 구조 안, 앞의 실행 명령부터 틈 이어 읽기, 모양):')
        print('| 후보 | ' + ' | '.join(cols) + ' |')
        print('| --- |' + ' --- |' * len(cols))
        for direct in (True, False):
            c2 = collections.Counter()
            for (dd, j), v in judged.items():
                if dd == direct:
                    c2[coarse(j)] += v
            print(f'| {"직접 피연산자" if direct else "값 모름(TCD·PLD·MVN·MVP)"} | ' + ' | '.join(f'{c2[x]:,}' for x in cols) + ' |')
        print('\n자세한 판정(직접 피연산자):')
        for (direct, j), v in sorted(judged.items(), key=lambda kv: -kv[1]):
            if direct:
                print(f'  {j}: {v:,}')
        if a.untouched:
            with open(a.untouched, 'w') as f:
                for k, o, det, j in rows2:
                    f.write(f'{cpu(o) >> 16:02X}:{cpu(o) & 0xFFFF:04X} {k} {det} {j}\n')
            print(f'\nCDL 표시가 없는 후보 {len(untouched)}곳 -> {a.untouched}')
    if starts:
        print('\n명령으로 실행된 후보:')
        byo = {cpu(o): (k, det) for k, o, det in cands}
        for addr, ls in sorted(starts.items()):
            if addr in byo:
                k, det = byo[addr]
                print(f'  {addr >> 16:02X}:{addr & 0xFFFF:04X} {k} {det} {len(ls)}번, 예 {ls[0]}')


if __name__ == '__main__':
    main()
