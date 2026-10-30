"""DQ5 맵 OBJ 물체·탈것·인물 세트의 칸 배치 쓰기와 새 맵 OBJ 물체. 읽기 형식은
sfc/dq5/docs/dq5-graphics-format.md 의 「맵 OBJ 물체」·「탈것」·「프레임 배치」, 쓰기 형식은 dq5-build-format.md.

칸 하나는 OBJ 8x8 한 장이고, 칸 바이트는 bit7 = 좌우 반전, bit0-6 = 타일 번호(그 물체가 받은 첫 VRAM 타일에서 센다).
글에서는 `05`(그대로)·`h05`(좌우 반전)·`v05`/`hv05`(상하 반전, 탈것 그림자에만 있음)로 쓴다.

  맵 OBJ 물체: 16:F60D 가 16:F862 의 9바이트 항목(FF 로 끝)을 읽어 탈것 슬롯(7E:3220 = FE)을 만든다. 표와 칸 바이트는
    모두 16 뱅크(PHK·PLB)이고 칸 바이트 주소는 16비트다. 표를 늘리면 제자리에서 뒤로 늘리고, 늘어난 표에 덮이는
    칸 바이트와 바꾼 칸 바이트는 16 뱅크 안의 같은 바이트를 찾아 가리키거나 --at(16 뱅크)에 놓는다.
    물체마다 인물 슬롯($81)을 하나 쓴다. 물체가 늘어난 실내 맵은 8 + 인물(그 맵 목록 가운데 가장 많은 수) + 물체에
    장면이 더 쓰는 슬롯(dq5npclists.SCENE_SLOTS)을 더해 20 을 넘으면 거부한다(슬롯 20 은 인물 표 다음 칸의 슬롯 0).
    필드는 00:E1A9 가 $81 을 8 로 두고 그 세계($1949)의 물체만 놓으므로 8 + 물체가 20 을 넘으면 거부한다. 필드 물체의
    첫 두 슬롯(8·9)은 탈것이 덮어쓴다(양탄자 1·8·9, 天空城 8·9, マスタードラゴン 7·8).
  탈것: 01:BD29(양탄자)·01:C436(天空城)·01:C087(マスタードラゴン)이 부분마다 LDY #칸 표 / JSL 16:F7D9 를 부른다.
    가로·세로 칸 수·방향·프레임 간격·옮겨 쓰는 블록 수($06)와 프레임 수(7E:32A0 bit0-3 = 마지막 프레임)는 같은 루틴의
    즉값이다. 칸 수·프레임 수가 그대로면 칸 바이트만 제자리에 쓴다. 바꾸면 그 탈것의 부분 모두의 칸 표를
    --vehicle-at 에 차례로 두고 즉값을 고친다(바꾼 부분은 그리는 블록만 옮겨 쓰게 한다). 한 즉값을 함께 쓰는 값
    (80-2·81-1·82-1·82-2 의 가로·세로, 한 탈것의 프레임 수)은 같아야 하고, 天空城 은 간격·프레임 주기가 STZ 라
    프레임 수를 바꿀 수 없다. マスタードラゴン 부분 1 은 착륙·이륙(01:BF7C)과 天空城 장면(01:BB7C)이 걷기 밖 블록을
    그려(SCENES) 문서에 land0·land1·tenkuu0~3 열쇠로 둔다. 칸 수·프레임 수를 바꾸면 이 블록을 걷기 블록 뒤에 겹치지
    않게 두고 두 루틴의 프레임·간격 즉값을 고친다. 상하 반전은 01:C42D·01:C160 표가 슬롯 칸 목록에 나중에 더하므로
    칸 수가 그대로면 바꿀 수 없고, 바꾸면 표를 다시 쓴다(원래 표보다 길면 --vehicle-at 뒤에 두고 읽는 곳을 고침).
    필드 OAM 은 00:EB3F 가 128장 한도를 보지 않고 이어 써 129장째부터 7E:0500 높은 표를 덮으므로, 칸 수를 바꾼 탈것은
    부분마다 한 블록의 칸 수 합 + 주인공(RIDER)이 128 을 넘으면 거부한다.
  인물 세트(배 68 등): 세트 레코드 +3~+50 의 칸 48개(1F:CFC8·1F:D0FB 가 칸 목록으로 옮김). 자리는 00:F071(6타일)·
    00:F7AA(8타일)가 정한다. 타일 번호는 그 세트의 타일 수(+51)보다 작아야 한다.

  python sfc/dq5/tools/dq5objlayout.py rom/dq5.sfc dump -o work/objlayout/layout.json
  python sfc/dq5/tools/dq5objlayout.py rom/dq5.sfc patch work/objlayout/layout.json -o work/objlayout.dq5patch.json --at 16:FE10
  python sfc/dq5/tools/dq5objlayout.py rom/dq5.sfc check [문서] [--at 16:FE10] [--vehicle-at 04:FEE0]

문서(dq5objlayout/1). 세 칸 모두 생략할 수 있고, 생략한 것은 그대로 둔다.
  {"format": "dq5objlayout/1",
   "objects": [{"map": "04/06", "x": 39, "y": 9, "cond": null, "palette": 3, "priority": 2,
                "cells": ["00 01", "02 03", "04 05", "06 07"]}, ...],     # 표 전체(차례대로). 줄 수 = 세로, 낱말 수 = 가로
   "vehicles": [{"part": "80-1", "size": "3x2", "frames": 2, "cells": {"down0": ["09 0a 0b", "0c 0d h0c"], ...}}],
   "sets": [{"set": "68", "cells": {"down0": "18 19 1a 1b 1c 1d", ...}}]}
map 은 "04/06", 그룹 전체 "04/**", 필드 "field0"(세계). cond 는 null·"day"·"night"(+4 bit7·bit6, 21:8000 이 7E:075E >= F0 을
밤으로 봄). 필드에서 y 의 아래 바이트가 80(128·384)이면 16:F741 이 위 바이트를 80 으로 두어 놓지 않고 스크립트가 놓는다.
실내는 128 을 따로 보지 않아 그 셀에 그대로 놓인다(실내 맵은 폭 128·높이 124 이하라 맵 바로 밖이다. 16/00 의 X 128·
129, 50/50 의 Y 128·129 물체가 그 칸에 그려졌다).
bit7(+6 bit7)은 쓰임을 모르는 원래 값으로, 없으면 0.
8타일 세트(80~)의 cells 는 "up-head" 같은 머리 4칸과 "up0"·"up1" 몸 4칸이다.
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5sprite as S  # noqa: E402
from dq5build import PatchError  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5npc import OVERRIDE_LISTS, all_lists, entry_size, list_entries  # noqa: E402
from dq5npclists import SCENE_SLOTS, SLOT_END, SLOT_FIRST, placed, read  # noqa: E402

FORMAT = 'dq5objlayout/1'
TABLE = S.MAP_OBJECT_PLACES
BANK = TABLE >> 16
# 원래 표 뒤의 칸 바이트 구역 끝(16:FDFF 는 아무 항목도 가리키지 않는 0). 표는 이 앞까지만 늘릴 수 있다.
REGION_END = 0x16FDFF
ENTRY = 9
DIRS = ('up', 'right', 'down', 'left')     # 00:EE7C 차례(방향 번호 0~3)
# 탈것 부분. 01:BD29(양탄자)·01:C087(マスタードラゴン)·01:C436(天空城)이 슬롯마다 LDA #즉값 / STA 로 두는 값의
# 피연산자 주소: ldy 칸 표(LDY #), bank 칸 표 뱅크(LDA #$04 / PHA / PLB, 한 탈것의 부분이 같이 씀), cols·rows 가로·세로
# 칸 수(7E:34E0·3500, 같은 주소면 한 즉값을 둘이 씀), dir·frame 방향·프레임 간격(7E:37C0·37E0, None 이면 STZ 라 0),
# count 옮겨 쓰는 블록 수 − 1($06), vflip 상하 반전 칸 오프셋 표(FF 로 끝)를 읽는 LDA long 의 피연산자.
VEHICLE_PARTS = {
    '80-1': {'vid': 0x80, 'ldy': 0x01BDA5, 'bank': 0x01BDA8, 'cols': 0x01BD40, 'rows': 0x01BD45, 'dir': 0x01BD4A,
             'frame': 0x01BD4F, 'count': 0x01BDB1},
    '80-2': {'vid': 0x80, 'ldy': 0x01BDC1, 'bank': 0x01BDA8, 'cols': 0x01BD76, 'rows': 0x01BD76, 'dir': 0x01BD7E,
             'frame': 0x01BD83, 'count': 0x01BDC9},
    '80-3': {'vid': 0x80, 'ldy': 0x01BDD4, 'bank': 0x01BDA8, 'cols': 0x01BD8B, 'rows': 0x01BD90, 'dir': 0x01BD95,
             'frame': 0x01BD9A, 'count': 0x01BDDC},
    '81-1': {'vid': 0x81, 'ldy': 0x01C48E, 'bank': 0x01C491, 'cols': 0x01C44D, 'rows': 0x01C44D, 'dir': None,
             'frame': None, 'count': 0x01C4A0},
    '81-2': {'vid': 0x81, 'ldy': 0x01C4AA, 'bank': 0x01C491, 'cols': 0x01C47D, 'rows': 0x01C482, 'dir': None,
             'frame': None, 'count': 0x01C4B2, 'vflip': 0x01C40E},
    '82-1': {'vid': 0x82, 'ldy': 0x01C0EB, 'bank': 0x01C0EE, 'cols': 0x01C092, 'rows': 0x01C092, 'dir': 0x01C09A,
             'frame': 0x01C09F, 'count': 0x01C0F7},
    '82-2': {'vid': 0x82, 'ldy': 0x01C106, 'bank': 0x01C0EE, 'cols': 0x01C0C0, 'rows': 0x01C0C0, 'dir': 0x01C0C8,
             'frame': 0x01C0CD, 'count': 0x01C10E, 'vflip': 0x01C133},
}
# 7E:32A0 즉값(탈것의 부분 모두에 같은 값). bit6-7 은 그리기 루틴(00:EC82, 80 = 00:FBEB), bit0-3 은 00:EDD0 이
# 프레임을 0 으로 되돌리는 마지막 프레임 번호다. 天空城 은 32E0(프레임 주기)·37C0·37E0 을 STZ 로 두어 프레임이 늘 0 이다.
VEHICLE_FRAMES = {0x80: 0x01BD57, 0x81: None, 0x82: 0x01C0AA}
# 걷기 밖 장면이 슬롯 7(82-1)에 두는 값의 피연산자 주소. 둘 다 31E7 = 20 이라 00:FC08 이 방향 자리를 00:EE7C[2] = 3
# 으로 잡는다(TURN). land: 01:BF7C(착륙 01:C200·이륙 01:BF47)가 3287 = X(frame)·32A7 = 8X(last)로 그리고 X − 1 로 한 번
# 내린다. 37C7·37E7 은 걷기 값 그대로라 첫 칸 = (3 × 방향 간격 + X × 프레임 간격) / 2. tenkuu: 01:BB7C(天空城
# 06/00·06/05)가 37C7 = S(stride)·32A7 = 83(last)으로 프레임 0~3 을 그려 첫 칸 = (3 × S + 프레임 × 프레임 간격) / 2.
SCENES = {'82-1': {'land': {'frame': 0x01BF86, 'last': 0x01BF81}, 'tenkuu': {'stride': 0x01BBB4, 'last': 0x01BBB9}}}
TURN = 3
# 탈것에 탄 채 함께 그려지는 주인공 OBJ 수의 최댓값(양탄자에 탄 어린 주인공 8, 어른 6, 天空城·マスタードラゴン 0).
RIDER = 8
OAM_LIMIT = 128
TOKEN = re.compile(r'(h?)(v?)([0-9A-Fa-f]{2})')


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def address(value, any_bank=False):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', value):
        raise ValueError('주소는 BB:AAAA 문자열이어야 함')
    bank, low = (int(p, 16) for p in value.split(':'))
    if any_bank:
        vehicle_bank(bank << 16 | low)
        return bank << 16 | low
    if bank != BANK or low < 0x8000:
        raise ValueError(f'--at 은 {BANK:02X} 뱅크 8000~FFFF 여야 함(표와 칸 바이트를 PHK·PLB 로 읽음)')
    return bank << 16 | low


def token(value):
    """칸 바이트 + 상하 반전 → 글."""
    b, v = value
    return ('h' if b & 0x80 else '') + ('v' if v else '') + f'{b & 0x7F:02X}'


def parse_token(text, label, limit=0x80, vflip=False):
    m = TOKEN.fullmatch(text)
    if not m:
        raise ValueError(f'{label}: 칸 {text!r} 는 [h][v]두 자리 16진이어야 함')
    tile = int(m[3], 16)
    if tile >= limit:
        raise ValueError(f'{label}: 타일 {tile:02X} 는 {limit:02X} 보다 작아야 함')
    if m[2] and not vflip:
        raise ValueError(f'{label}: 상하 반전(v)은 탈것 그림자 칸에만 있음')
    return tile | (0x80 if m[1] else 0), bool(m[2])


def parse_row(text, label, **kw):
    if not isinstance(text, str):
        raise ValueError(f'{label}: 칸 줄은 문자열이어야 함')
    return [parse_token(t, label, **kw) for t in text.split()]


def parse_map(text, label):
    if text is not None and isinstance(text, str):
        m = re.fullmatch(r'field([0-9])', text)
        if m:
            return 0xFE, int(m[1])
        m = re.fullmatch(r'([0-9A-Fa-f]{2})/([0-9A-Fa-f]{2}|\*\*)', text)
        if m and int(m[1], 16) < 0xFE:
            return int(m[1], 16), 0x7F if m[2] == '**' else int(m[2], 16) & 0x7F
    raise ValueError(f'{label}: map 은 "04/06"·"04/**"·"field0" 꼴이어야 함')


def map_name(bc, bd):
    if bc == 0xFE:
        return f'field{bd}'
    return f'{bc:02X}/' + ('**' if bd & 0x7F == 0x7F else f'{bd & 0x7F:02X}')


# --- 맵 OBJ 물체 ---------------------------------------------------------------------------------------------------

def read_objects(rom):
    """16:F862 표. 항목마다 원래 바이트 9개와 칸 바이트."""
    out, a = [], TABLE
    while rom.u8(a) != 0xFF:
        b = bytes(rom.u8(a + i) for i in range(ENTRY))
        cols, rows = b[4] & 0x3F, b[5]
        ptr = BANK << 16 | b[7] | b[8] << 8
        out.append({'entry': a, 'raw': b, 'ptr': ptr, 'cells': bytes(rom.u8(ptr + i) for i in range(cols * rows))})
        a += ENTRY
    return out


def object_doc(o):
    b = o['raw']
    cols = b[4] & 0x3F
    row = {'map': map_name(b[0], b[1]), 'x': b[2] | (b[6] & 1) << 8, 'y': b[3] | (b[6] >> 1 & 1) << 8,
           'cond': None if not b[4] & 0x80 else ('night' if b[4] & 0x40 else 'day'),
           'palette': b[6] >> 2 & 7, 'priority': b[6] >> 5 & 3,
           'cells': [' '.join(token((c, False)) for c in o['cells'][r * cols:(r + 1) * cols]) for r in range(b[5])]}
    if b[6] & 0x80:
        row['bit7'] = True
    if b[0] != 0xFE and b[1] & 0x80:
        row['bd7'] = True
    return row


def object_entry(row, label):
    """문서 항목 → (항목 앞 7바이트, 칸 바이트)."""
    keys = {'map', 'x', 'y', 'cond', 'palette', 'priority', 'cells', 'bit7', 'bd7'}
    if not isinstance(row, dict) or row.keys() - keys or not {'map', 'x', 'y', 'cells'} <= row.keys():
        raise ValueError(f'{label}: map·x·y·cells(와 cond·palette·priority·bit7·bd7)만 받음')
    bc, bd = parse_map(row['map'], label)
    if row.get('bd7') and bc != 0xFE:
        bd |= 0x80
    x, y = row['x'], row['y']
    palette, priority = row.get('palette', 3), row.get('priority', 2)
    for name, v, top in (('x', x, 0x200), ('y', y, 0x200), ('palette', palette, 8), ('priority', priority, 4)):
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < top:
            raise ValueError(f'{label}: {name} 는 0~{top - 1} 정수여야 함')
    cond = row.get('cond')
    if cond not in (None, 'day', 'night'):
        raise ValueError(f'{label}: cond 는 null·"day"·"night"')
    rows = row['cells']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 0xFF:
        raise ValueError(f'{label}: cells 는 1~255 줄의 배열이어야 함')
    grid = [parse_row(r, f'{label} 줄 {i}') for i, r in enumerate(rows)]
    cols = len(grid[0])
    if not 1 <= cols <= 0x3F or any(len(r) != cols for r in grid):
        raise ValueError(f'{label}: 줄마다 칸 수가 같고 1~63 이어야 함')
    head = bytes([bc, bd, x & 0xFF, y & 0xFF,
                  cols | (0x80 if cond else 0) | (0x40 if cond == 'night' else 0), len(grid),
                  x >> 8 | (y >> 8) << 1 | palette << 2 | priority << 5 | (0x80 if row.get('bit7') else 0)])
    return head, bytes(c for r in grid for c, _ in r)


def map_people(rom):
    """실내 맵·낮밤마다 그 맵의 인물 목록(기본 목록과 12:8449 대체 표가 가리키는 목록) 가운데 가장 많이 놓는 인물 수."""
    lists = {}
    for at, name in all_lists(rom):
        if re.fullmatch(r'[0-9A-F]{2}/[0-9A-F]{2}', name):
            lists.setdefault(tuple(int(v, 16) for v in name.split('/')), []).append(at)
    t = OVERRIDE_LISTS
    while rom.u8(t) != 0xFF:
        lists.setdefault((rom.u8(t), rom.u8(t + 1)), []).append(0x100000 | rom.u16(t + 4))
        t += 6
    most = {}
    for (bc, bd), ats in lists.items():
        for at in ats:
            raws = [read(rom, e, entry_size(rom, e)) for e, _ in list_entries(rom, at)]
            for night in (False, True):
                most[bc, bd, night] = max(most.get((bc, bd, night), 0), placed(raws, night))
    return most


def objects_on(heads, bc, bd, night):
    """16:F60D 가 실내 맵 bc/bd(bc = FE 면 필드 세계 bd)에 놓는 물체 수(+4 bit7 이면 낮밤으로 고르고 bit6 이 밤).
    필드 항목은 +1 을 $1949 와 그대로 견준다(16:F685)."""
    if bc == 0xFE:
        return sum(h[0] == 0xFE and h[1] == bd and (not h[4] & 0x80 or bool(h[4] & 0x40) == night) for h in heads)
    return sum(h[0] == bc and h[1] & 0x7F in (0x7F, bd) and (not h[4] & 0x80 or bool(h[4] & 0x40) == night)
               for h in heads)


def check_field_slots(old_heads, new_heads):
    """필드 세계마다 물체가 늘었으면 8 + 물체(7E:1983)가 20 을 넘지 않는지. 세계 0 에 물체를 더해 1983 = 20 이면
    주인공이 그대로이고 21 이면 슬롯 20(주인공 X·Y 칸)이 덮여 주인공이 사라졌다(세계 0·1·2, dq5oamlimitcheck.py).
    필드 장면이 물체 뒤에 더 쓰는 슬롯은 보지 않는다(실내의 SCENE_SLOTS 같은 표가 필드에는 없음)."""
    for world in sorted({h[1] for h in new_heads if h[0] == 0xFE}):
        for night in (False, True):
            count = objects_on(new_heads, 0xFE, world, night)
            used = SLOT_FIRST + count
            if count > objects_on(old_heads, 0xFE, world, night) and used > SLOT_END:
                raise ValueError(f'field{world} {"밤" if night else "낮"}: 물체 뒤 슬롯 {used:#04x} 이 {SLOT_END:#04x} 를 넘음')


def check_slots(rom, old_heads, new_heads):
    """물체가 늘어난 실내 맵마다 8 + 인물 + 물체(물체를 다 놓은 뒤의 7E:1983)에 장면이 더 쓰는 슬롯을 더해 20 을
    넘으면 거부한다. 슬롯 20 은 인물 표 다음 칸의 슬롯 0(주인공)이다. 필드(FE)는 check_field_slots 가 본다.
    dq5npclists 의 SLOT_LIMIT(1F)는 인물을 늘릴 때 원본 최댓값까지만 여는 기준이고, 여기서는 19/02 에서 $1983 = 20
    까지 그대로임을 잰 SLOT_END 를 쓴다."""
    check_field_slots(old_heads, new_heads)
    maps = {(h[0], h[1] & 0x7F) for h in new_heads if h[0] != 0xFE}
    grown = [(bc, bd, night) for bc, bd in sorted(maps) for night in (False, True)
             if objects_on(new_heads, bc, bd, night) > objects_on(old_heads, bc, bd, night)]
    if not grown:
        return
    people = map_people(rom)
    for bc, bd, night in grown:
        targets = sorted({(c, d) for c, d, _ in people if c == bc}) if bd == 0x7F else [(bc, bd)]
        for c, d in targets:
            used = SLOT_FIRST + people.get((c, d, night), 0) + objects_on(new_heads, c, d, night)
            extra = SCENE_SLOTS.get((c, d), 0)
            if used + extra > SLOT_END:
                raise ValueError(f'{c:02X}/{d:02X} {"밤" if night else "낮"}: 인물·물체 뒤 슬롯 {used:#04x}'
                                 + (f' + 장면이 더 쓰는 {extra}칸' if extra else '') + f' 이 {SLOT_END:#04x} 를 넘음')


def plan_objects(rom, rows, at):
    """새 표와 칸 바이트 자리. (쓰기 목록 [(주소, 바이트, 원래 롬 안인지, 설명)], 옮기거나 새로 둔 칸 수)."""
    if not isinstance(rows, list):
        raise ValueError('objects 는 배열이어야 함')
    old = read_objects(rom)
    entries = [object_entry(r, f'objects[{i}]') for i, r in enumerate(rows)]
    check_slots(rom, [o['raw'] for o in old], [h for h, _ in entries])
    table_end = TABLE + len(entries) * ENTRY + 1
    if table_end > REGION_END:
        raise ValueError(f'objects {len(entries)}개: 표가 {cpu(REGION_END)} 를 넘음(최대 {(REGION_END - TABLE - 1) // ENTRY}개)')
    region = bytes(rom.u8(a) for a in range(table_end, REGION_END))
    placed, blob, cursor = [], bytearray(), at
    moved = 0
    for i, (head, cells) in enumerate(entries):
        orig = old[i] if i < len(old) else None
        if orig and orig['cells'] == cells and orig['ptr'] >= table_end:
            placed.append(orig['ptr'])
            continue
        # 표에 덮이지 않고 그대로 남는 구역에서 같은 바이트를 찾고, 없으면 --at 뒤에 둔다.
        k = region.find(cells)
        if k >= 0:
            placed.append(table_end + k)
        else:
            k = bytes(blob).find(cells)
            if k < 0:
                if cursor is None:
                    raise ValueError(f'objects[{i}]: 칸 바이트를 둘 곳이 없어 --at 이 필요함')
                k = len(blob)
                blob += cells
            placed.append(cursor + k)
        moved += 1
    if blob and cursor >> 16 != BANK:
        raise ValueError(f'--at {cpu(cursor)}: 칸 바이트는 {BANK:02X} 뱅크에 있어야 함')
    if blob and (cursor & 0xFFFF) + len(blob) > 0x10000:
        raise ValueError(f'--at {cpu(cursor)} 뒤 칸 바이트 {len(blob)}바이트가 16 뱅크를 넘음')
    table = b''.join(h + bytes([p & 0xFF, p >> 8 & 0xFF]) for (h, _), p in zip(entries, placed)) + b'\xff'
    writes = []
    old_table = bytes(rom.u8(TABLE + i) for i in range(len(table)))
    if table != old_table:
        writes.append((TABLE, table, True, f'맵 OBJ 물체 표 {len(entries)}항목'))
    if blob:
        writes.append((cursor, bytes(blob), False, f'맵 OBJ 물체 칸 바이트 {len(blob)}바이트'))
    return writes, moved


# --- 탈것 ----------------------------------------------------------------------------------------------------------

def vehicle_bank(at):
    """칸 표는 LDY # 로 읽고, 세 탈것 루틴은 PLB 로 칸 표 뱅크를 데이터 뱅크로 둔 채 STX $1997 을 쓴다(01:BDB7·01:C0FD·
    01:C49C). 40~7D 뱅크면 그 쓰기가 롬으로 가 타일 첫 자리가 깨진다."""
    if at & 0xFFFF < 0x8000 or at >> 16 & 0x7F >= 0x40:
        raise ValueError(f'--vehicle-at {cpu(at)}: 칸 표는 7E:1997 이 비치는 뱅크 00~3F·80~BF 의 8000~FFFF 여야 함'
                         '(탈것 루틴이 칸 표 뱅크를 데이터 뱅크로 두고 STX $1997 을 씀)')


def vehicle_frames(rom, vid):
    at = VEHICLE_FRAMES[vid]
    return (rom.u8(at) & 0x0F) + 1 if at else 1


def vehicle_blocks(cols, rows, dir_, frame, frames):
    """그리는 블록마다 칸 번호. 00:FC08 은 프레임 × 37E0 + 00:EE7C[방향] × 37C0 바이트(칸 하나 2바이트)부터 그린다."""
    per = cols * rows
    if not dir_:
        return {'all': list(range(per))}
    return {f'{d}{f}': list(range((DIRS.index(d) * dir_ + f * frame) // 2, (DIRS.index(d) * dir_ + f * frame) // 2 + per))
            for d in DIRS for f in range(frames)}


def vflip_offsets(rom, at):
    out, a = [], at
    while rom.u8(a) != 0xFF:
        out.append(rom.u8(a))
        a += 1
    return out


def vflip_at(rom, site):
    """상하 반전 표 주소(01:C132·01:C40D 의 LDA long 피연산자)."""
    return rom.u24(site['vflip'])


def scene_blocks(rom, name, cols, rows, dir_, frame):
    """걷기 밖 장면이 그리는 블록마다 칸 번호(SCENES). land0 이 먼저(프레임 X), land1 이 다음(X − 1)."""
    if name not in SCENES:
        return {}
    land, tenkuu = SCENES[name]['land'], SCENES[name]['tenkuu']
    per, x, stride = cols * rows, rom.u8(land['frame']), rom.u8(tenkuu['stride'])
    starts = {'land0': TURN * dir_ + x * frame, 'land1': TURN * dir_ + (x - 1) * frame}
    starts |= {f'tenkuu{f}': TURN * stride + f * frame for f in range((rom.u8(tenkuu['last']) & 0x0F) + 1)}
    return {k: list(range(v // 2, v // 2 + per)) for k, v in starts.items()}


def vehicle_part(rom, name):
    site = VEHICLE_PARTS[name]
    cols, rows = rom.u8(site['cols']), rom.u8(site['rows'])
    dir_ = rom.u8(site['dir']) if site['dir'] else 0
    frame = rom.u8(site['frame']) if site['frame'] else 0
    frames = vehicle_frames(rom, site['vid'])
    table = rom.u8(site['bank']) << 16 | rom.u16(site['ldy'])
    blocks = vehicle_blocks(cols, rows, dir_, frame, frames)
    scene = scene_blocks(rom, name, cols, rows, dir_, frame)
    used = max(i for b in (*blocks.values(), *scene.values()) for i in b) + 1
    copied = (rom.u8(site['count']) + 1) * cols * rows
    vflip = {off // 2 for off in vflip_offsets(rom, vflip_at(rom, site))} if site.get('vflip') else set()
    return {'cols': cols, 'rows': rows, 'dir': dir_, 'frame': frame, 'frames': frames, 'table': table, 'blocks': blocks,
            'scene': scene, 'vflip': vflip, 'used': used, 'copied': copied,
            'bytes': bytes(rom.u8(table + i) for i in range(used))}


def vehicle_doc(rom, name):
    p = vehicle_part(rom, name)
    cols = p['cols']
    cells = {}
    for key, idx in (p['blocks'] | p['scene']).items():
        toks = [token((p['bytes'][i], i in p['vflip'])) for i in idx]
        cells[key] = [' '.join(toks[r * cols:(r + 1) * cols]) for r in range(p['rows'])]
    return {'part': name, 'size': f'{cols}x{p["rows"]}', 'frames': p['frames'], 'cells': cells}


def parse_size(text, label):
    m = re.fullmatch(r'([1-9][0-9]?)x([1-9][0-9]?)', text) if isinstance(text, str) else None
    if not m:
        raise ValueError(f'{label}: size 는 "3x2" 꼴(가로x세로)이어야 함')
    return int(m[1]), int(m[2])


def vehicle_cells(row_cells, key, rows, per, label, vflip_ok):
    """문서의 블록 하나 → [(칸 바이트, 상하 반전)]."""
    if not isinstance(row_cells, list) or len(row_cells) != rows:
        raise ValueError(f'{label} {key}: 줄 {rows}개여야 함')
    toks = [t for r, text in enumerate(row_cells) for t in parse_row(text, f'{label} {key} 줄 {r}', vflip=vflip_ok)]
    if len(toks) != per:
        raise ValueError(f'{label} {key}: 칸 {per}개여야 함')
    return toks


def plan_vehicles(rom, rows, at=None):
    if not isinstance(rows, list):
        raise ValueError('vehicles 는 배열이어야 함')
    by_part = {}
    for i, row in enumerate(rows):
        label = f'vehicles[{i}]'
        if not isinstance(row, dict) or row.keys() - {'part', 'size', 'frames', 'cells'} or \
                row.get('part') not in VEHICLE_PARTS or row['part'] in by_part or not isinstance(row.get('cells'), dict):
            raise ValueError(f'{label}: part(80-1 등, 한 번씩)·cells(와 size·frames)만 받음')
        by_part[row['part']] = (label, row)
    writes = []
    for vid in sorted({VEHICLE_PARTS[n]['vid'] for n in by_part}):
        names = [n for n in VEHICLE_PARTS if VEHICLE_PARTS[n]['vid'] == vid]
        cur = {n: vehicle_part(rom, n) for n in names}
        asked = {row['frames'] for _, row in (by_part[n] for n in names if n in by_part) if 'frames' in row}
        if len(asked) > 1:
            raise ValueError(f'탈것 {vid:02X}: 부분마다 frames 가 다름(프레임 수는 탈것 하나에 즉값 하나)')
        frames = asked.pop() if asked else vehicle_frames(rom, vid)
        if not isinstance(frames, int) or isinstance(frames, bool) or not 1 <= frames <= 16:
            raise ValueError(f'탈것 {vid:02X}: frames 는 1~16')
        if frames != vehicle_frames(rom, vid) and not VEHICLE_FRAMES[vid]:
            raise ValueError(f'탈것 {vid:02X}: 32A0·32E0·37C0·37E0 을 STZ 로 두어 프레임 수를 바꿀 수 없음')
        layout = {}
        for n in names:
            label, row = by_part.get(n, (n, {}))
            cols, rows_ = parse_size(row['size'], label) if 'size' in row else (cur[n]['cols'], cur[n]['rows'])
            site = VEHICLE_PARTS[n]
            if site['cols'] == site['rows'] and cols != rows_:
                raise ValueError(f'{label}: 가로·세로 칸 수를 한 즉값({cpu(site["cols"] - 1)} LDA #)이 함께 써서 같아야 함')
            per = cols * rows_
            if site['dir']:
                dir_, frame = frames * per * 2, per * 2
                if dir_ > 0xFF:
                    raise ValueError(f'{label}: 방향 간격 {frames}프레임 × {per}칸 × 2 = {dir_} 가 즉값 한 바이트(255)를 넘음')
            else:
                dir_ = frame = 0
            changed = (cols, rows_, dir_, frame) != (cur[n]['cols'], cur[n]['rows'], cur[n]['dir'], cur[n]['frame'])
            layout[n] = {'cols': cols, 'rows': rows_, 'dir': dir_, 'frame': frame, 'changed': changed}
        moved = any(v['changed'] for v in layout.values())
        drawn = sum(v['cols'] * v['rows'] for v in layout.values())
        if moved and drawn + RIDER > OAM_LIMIT:
            raise ValueError(f'탈것 {vid:02X}: 부분마다 한 블록의 칸 {drawn}장 + 주인공 {RIDER}장이 OAM {OAM_LIMIT}장을 넘음'
                             '(00:EB3F 가 넘친 OBJ 를 7E:0500 높은 표에 써 앞 OBJ 의 크기·X 위 비트가 깨짐)')
        if not moved:
            writes += plan_vehicle_cells(rom, names, by_part, cur)
            continue
        if at is None:
            raise ValueError(f'탈것 {vid:02X}: 칸 수·프레임 수를 바꾸면 칸 표를 옮겨야 해 --vehicle-at 이 필요함')
        w = plan_vehicle_layout(rom, vid, names, by_part, cur, layout, frames, at)
        writes += w
        at += len(w[0][1])
    return writes


def plan_vehicle_cells(rom, names, by_part, cur):
    """칸 수·프레임 수 그대로: 칸 바이트만 제자리에. 같은 바이트를 두 블록(82-1 의 tenkuu3·land1 은 원래 같은 블록)이나
    두 부분이 쓰면 값이 같아야 하고, 문서에 없는 블록이 그리는 칸은 바꿀 수 없다."""
    want, given = {}, set()
    for n in names:
        if n not in by_part:
            continue
        label, row = by_part[n]
        p = cur[n]
        keys = p['blocks'] | p['scene']
        if row['cells'].keys() - keys.keys():
            raise ValueError(f'{label}: cells 의 열쇠는 {" ".join(keys)} 중 하나')
        for key, cells in row['cells'].items():
            toks = vehicle_cells(cells, key, p['rows'], p['cols'] * p['rows'], label, True)
            for i_, (b, v) in zip(keys[key], toks):
                if v != (i_ in p['vflip']):
                    raise ValueError(f'{label} {key}: 상하 반전 칸은 상하 반전 표가 정해 칸 수가 그대로면 바꿀 수 없음')
                addr = p['table'] + i_
                if want.setdefault(addr, (b, f'{label} {key}'))[0] != b:
                    raise ValueError(f'{label} {key}: {cpu(addr)} 을 {want[addr][1]} 이 다른 값으로 씀')
            given.add((n, key))
    changed = sorted(a for a, (b, _) in want.items() if rom.u8(a) != b)
    for n in names:
        p = cur[n]
        for key, idx in (p['blocks'] | p['scene']).items():
            hit = [a for a in changed if a - p['table'] in idx and (n, key) not in given]
            if hit:
                raise ValueError(f'{want[hit[0]][1]}: {cpu(hit[0])} 이 문서에 없는 {n} {key} 의 칸을 덮음')
    # 부분마다 그리는 범위를 쓰고, 겹치는 범위는 하나로 합친다(빌더는 겹친 쓰기를 거부).
    spans = sorted([cur[n]['table'], cur[n]['table'] + cur[n]['used'], [n]] for n in names
                   if any(cur[n]['table'] <= a < cur[n]['table'] + cur[n]['used'] for a in changed))
    merged = []
    for span in spans:
        if merged and span[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], span[1])
            merged[-1][2] += span[2]
        else:
            merged.append(span)
    return [(start, bytes(want.get(a, (rom.u8(a),))[0] for a in range(start, end)), True,
             f'탈것 {"·".join(parts)} 칸 {end - start}개') for start, end, parts in merged]


def scene_layout(rom, name, frames, per):
    """걷기 블록(0 ~ 4 × frames − 1) 뒤에 착륙 두 블록과 天空城 블록을 겹치지 않게 두는 (X, S, 블록 수) 가운데 블록 수가
    가장 적은 것. 착륙은 블록 3 × frames + X − 1·X, 天空城 은 3 × S / (칸 수 × 2) 부터다(X ≤ 15, S ≤ 255)."""
    tenkuu = (rom.u8(SCENES[name]['tenkuu']['last']) & 0x0F) + 1
    walk = set(range(4 * frames))
    best = None
    for k in range(0x100 // (per * 2) + 1):
        if k * per * 2 > 0xFF:
            break
        sit = set(range(3 * k, 3 * k + tenkuu))
        for x in range(1, 16):
            land = {3 * frames + x - 1, 3 * frames + x}
            if walk & sit or walk & land or sit & land:
                continue
            total = max(walk | sit | land) + 1
            if best is None or total < best[2]:
                best = (x, k * per * 2, total)
    if best is None:
        raise ValueError(f'{name}: {frames}프레임 × {per}칸이면 天空城 장면 간격(37C7, 3 × 블록이 걷기 블록 뒤)이 '
                         f'한 바이트를 넘거나 착륙 프레임(32A7)이 15 를 넘음')
    return best


def plan_vehicle_layout(rom, vid, names, by_part, cur, layout, frames, at):
    """칸 수·프레임 수를 바꾼 탈것: 부분 모두의 칸 표를 at 에 차례로 두고 즉값을 고친다. 바꾼 부분은 그리는 블록만
    옮겨 쓰게($06 = 블록 수 − 1) 하고 모든 블록의 칸을 받는다. 그대로인 부분은 원래 옮기던 범위를 그대로 베낀다.
    걷기 밖 장면 블록(SCENES)은 scene_layout 자리에 두고, 원래 표보다 긴 상하 반전 표는 칸 표 뒤에 둔다."""
    vehicle_bank(at)
    blob, imm, tables = bytearray(), [], []
    for n in names:
        site, p, new = VEHICLE_PARTS[n], cur[n], layout[n]
        label, row = by_part.get(n, (n, {'cells': {}}))
        start = at + len(blob)
        if not new['changed']:
            keys = p['blocks'] | p['scene']
            data = bytearray(rom.u8(p['table'] + i) for i in range(p['copied']))
            for key, cells in row['cells'].items():
                if key not in keys:
                    raise ValueError(f'{label}: cells 의 열쇠는 {" ".join(keys)} 중 하나')
                toks = vehicle_cells(cells, key, p['rows'], p['cols'] * p['rows'], label, True)
                for i_, (b, v) in zip(keys[key], toks):
                    if v != (i_ in p['vflip']):
                        raise ValueError(f'{label} {key}: 상하 반전 칸은 상하 반전 표가 정해 칸 수가 그대로면 바꿀 수 없음')
                    data[i_] = b
        else:
            blocks = vehicle_blocks(new['cols'], new['rows'], new['dir'], new['frame'], frames)
            per = new['cols'] * new['rows']
            count = len(blocks)
            if n in SCENES:
                x, stride, count = scene_layout(rom, n, frames, per)
                land, tenkuu = SCENES[n]['land'], SCENES[n]['tenkuu']
                imm += [(land['frame'], bytes([x]), f'탈것 {n} 착륙 프레임'),
                        (land['last'], bytes([rom.u8(land['last']) & 0xF0 | x]), f'탈것 {n} 착륙 마지막 프레임'),
                        (tenkuu['stride'], bytes([stride]), f'탈것 {n} 天空城 간격')]
                first = {'land0': 3 * frames + x, 'land1': 3 * frames + x - 1}
                first |= {f'tenkuu{f}': 3 * stride // (per * 2) + f for f in range((rom.u8(tenkuu['last']) & 0x0F) + 1)}
                blocks |= {k: list(range(b * per, b * per + per)) for k, b in first.items()}
            missing = blocks.keys() - row['cells'].keys()
            if missing or row['cells'].keys() - blocks.keys():
                raise ValueError(f'{label}: 칸 수·프레임 수를 바꾸면 cells 에 {" ".join(blocks)} 를 모두 주어야 함')
            data = bytearray(count * per)
            flips = []
            for key, idx in blocks.items():
                toks = vehicle_cells(row['cells'][key], key, new['rows'], per, label, bool(site.get('vflip')))
                for i_, (b, v) in zip(idx, toks):
                    data[i_] = b
                    if v:
                        flips.append(i_ * 2)
            if site.get('vflip'):
                if any(off > 0xFE for off in flips):
                    raise ValueError(f'{label}: 상하 반전 칸 오프셋은 FE(칸 127)까지')
                table = bytes(sorted(flips)) + b'\xff'
                old_at = vflip_at(rom, site)
                if len(table) <= len(vflip_offsets(rom, old_at)) + 1:
                    if bytes(rom.u8(old_at + i) for i in range(len(table))) != table:
                        imm.append((old_at, table, f'탈것 {n} 상하 반전 표'))
                else:
                    tables.append((site['vflip'], table, f'탈것 {n} 상하 반전 표'))
            for key, val in (('cols', new['cols']), ('rows', new['rows']), ('dir', new['dir']), ('frame', new['frame']),
                             ('count', count - 1)):
                if site[key] and rom.u8(site[key]) != val:
                    imm.append((site[key], bytes([val]), f'탈것 {n} {key}'))
        blob += data
        imm.append((site['ldy'], (start & 0xFFFF).to_bytes(2, 'little'), f'탈것 {n} 칸 표 주소'))
    for operand, table, note in tables:
        imm.append((operand, (at + len(blob)).to_bytes(3, 'little'), f'{note} 주소'))
        blob += table
    if (at & 0xFFFF) + len(blob) > 0x10000:
        raise ValueError(f'--vehicle-at {cpu(at)} 뒤 칸 표 {len(blob)}바이트가 뱅크를 넘음')
    bank = VEHICLE_PARTS[names[0]]['bank']
    imm.append((bank, bytes([at >> 16]), f'탈것 {vid:02X} 칸 표 뱅크'))
    if VEHICLE_FRAMES[vid]:
        imm.append((VEHICLE_FRAMES[vid], bytes([rom.u8(VEHICLE_FRAMES[vid]) & 0xF0 | frames - 1]), f'탈것 {vid:02X} 프레임 수'))
    out = [(at, bytes(blob), False, f'탈것 {vid:02X} 칸 표')]
    seen = {}
    for addr, data, note in imm:
        seen[addr] = (data, note)
    for addr, (data, note) in seen.items():
        if bytes(rom.u8(addr + i) for i in range(len(data))) != data:
            out.append((addr, data, True, note))
    return out


# --- 인물 세트 -----------------------------------------------------------------------------------------------------

def set_blocks(rec):
    if rec['layout'] == 'simple':
        return {f'{d}{f}': [S.SIMPLE_BASE[d] + f * 6 + i for i in range(6)] for d in DIRS for f in range(2)}
    out = {}
    for d in DIRS:
        out[f'{d}-head'] = [S.HEAD_BASE[d] + i for i in range(4)]
        for f in range(2):
            out[f'{d}{f}'] = [S.BODY_BASE[d] + f * 4 + i for i in range(4)]
    return out


def set_doc(rec):
    return {'set': f'{rec["set"]:02X}',
            'cells': {k: ' '.join(token((rec['cells'][i], False)) for i in idx) for k, idx in set_blocks(rec).items()}}


def plan_sets(rom, rows):
    if not isinstance(rows, list):
        raise ValueError('sets 는 배열이어야 함')
    writes, seen = [], set()
    for i, row in enumerate(rows):
        label = f'sets[{i}]'
        if not isinstance(row, dict) or row.keys() - {'set', 'cells'} or not isinstance(row.get('cells'), dict) or \
                not isinstance(row.get('set'), str) or not re.fullmatch(r'[0-9A-Fa-f]{2}', row['set']):
            raise ValueError(f'{label}: set(두 자리 16진)·cells 만 받음')
        s = int(row['set'], 16)
        rec = S.set_record(rom, s)
        if rec is None or s in seen:
            raise ValueError(f'{label}: 세트 {s:02X} 는 없거나 두 번 지정함')
        seen.add(s)
        blocks = set_blocks(rec)
        if row['cells'].keys() - blocks.keys():
            raise ValueError(f'{label}: cells 의 열쇠는 {" ".join(blocks)} 중 하나')
        cells = bytearray(rec['cells'])
        for key, text in row['cells'].items():
            toks = parse_row(text, f'{label} {key}', limit=rec['tiles'])
            if len(toks) != len(blocks[key]):
                raise ValueError(f'{label} {key}: 칸 {len(blocks[key])}개여야 함')
            for c, (b, _) in zip(blocks[key], toks):
                cells[c] = b
        if bytes(cells) != bytes(rec['cells']):
            writes.append((rec['record'] + 3, bytes(cells), True, f'세트 {s:02X} 칸 48개'))
    return writes


# --- 문서 ----------------------------------------------------------------------------------------------------------

def dump(rom):
    return {'format': FORMAT,
            'objects': [object_doc(o) for o in read_objects(rom)],
            'vehicles': [vehicle_doc(rom, n) for n in VEHICLE_PARTS],
            'sets': [set_doc(S.set_record(rom, s)) for s in S.set_numbers(rom) if S.set_record(rom, s)]}


def patch(rom, doc, at=None, vehicle_at=None):
    if not isinstance(doc, dict) or doc.get('format') != FORMAT or doc.keys() - {'format', 'objects', 'vehicles', 'sets'}:
        raise ValueError(f'문서는 format={FORMAT} 와 objects·vehicles·sets 만 담은 객체여야 함')
    writes, moved = [], 0
    if 'objects' in doc:
        w, moved = plan_objects(rom, doc['objects'], at)
        writes += w
    writes += plan_vehicles(rom, doc.get('vehicles', []), vehicle_at)
    writes += plan_sets(rom, doc.get('sets', []))
    out = []
    for addr, data, inside, note in writes:
        item = {'at': cpu(addr), 'hex': data.hex(' '), 'note': note}
        # 새 칸 바이트는 orig 없이 써서, 원래 롬 안이면 빌더가 빈 자리 지도 밖을 거부한다.
        if inside:
            item['orig'] = bytes(rom.d[lorom(addr):lorom(addr) + len(data)]).hex(' ')
        out.append(item)
    if moved:
        print(f'맵 OBJ 물체 칸 바이트 {moved}개를 다른 자리에서 가리킴', file=sys.stderr)
    return {'format': 'dq5patch/1', 'name': 'obj-layout', 'writes': out}


def built(rom, manifest):
    from dq5build import REACHABLE, build, parse_at
    lists = [(parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None, w['note'])
             for w in manifest['writes']]
    # parse_at 이 이미 파일 위치를 돌려주므로 lorom 을 다시 거치면 롬 밖(뱅크 30~) 쓰기를 롬 안으로 잘못 본다.
    end = max(a + len(d) for a, d, _, _ in lists) if lists else 0
    fits = [m for m, top in REACHABLE.items() if end <= top]
    if end > len(rom.d) and not fits:
        raise PatchError(f'쓰기 끝 {end:#x} 가 늘릴 수 있는 롬 크기를 넘음')
    mb = 0 if end <= len(rom.d) else fits[0]
    data, _ = build(rom.d, [('obj-layout', 0, lists)], mb)
    return Rom(data)


def normalized(doc, rom):
    """비교용: 생략한 칸은 롬 값으로 채운 dump 꼴."""
    base = dump(rom)
    if 'objects' in doc:
        base['objects'] = [object_doc({'raw': h + b'\0\0', 'cells': c}) for h, c in
                           (object_entry(r, '') for r in doc['objects'])]
    rows = doc.get('vehicles', [])
    for row in rows:
        if 'frames' in row:
            for v in base['vehicles']:
                if VEHICLE_PARTS[v['part']]['vid'] == VEHICLE_PARTS[row['part']]['vid']:
                    v['frames'] = row['frames']
    for row in rows:
        cur = next(v for v in base['vehicles'] if v['part'] == row['part'])
        if 'size' in row:
            cur['size'] = '{}x{}'.format(*parse_size(row['size'], ''))
        cells = {k: [canon(r) for r in v] for k, v in row['cells'].items()}
        orig = vehicle_doc(rom, row['part'])
        if cur['size'] != orig['size'] or cur['frames'] != orig['frames'] and VEHICLE_PARTS[row['part']]['dir']:
            cur['cells'] = cells
        else:
            cur['cells'].update(cells)
    for row in doc.get('sets', []):
        cur = next(s for s in base['sets'] if s['set'] == row['set'].upper())
        cur['cells'].update({k: canon(v) for k, v in row['cells'].items()})
    return base


def canon(text):
    return ' '.join(token(parse_token(t, '', vflip=True)) for t in text.split())


def check(rom, doc=None, at=None, vehicle_at=None):
    """원본을 dump 해 다시 넣으면 쓰기 0개인지. doc 를 주면 빌드한 롬을 다시 dump 해 문서와 같은지."""
    original = dump(rom)
    for v in S.VEHICLES:
        for k, part in enumerate(v['parts']):
            p = vehicle_part(rom, f'{v["id"]:02X}-{k + 1}')
            if (p['cols'], p['rows'], p['dir'], p['frame']) != (part['cols'], part['rows'], part['dir'], part['frame']):
                print(f'탈것 {v["id"]:02X}-{k + 1}: 즉값이 원본(dq5sprite.VEHICLES)과 다름', file=sys.stderr)
    if patch(rom, original)['writes']:
        raise ValueError('원본 문서를 그대로 넣었는데 쓰기가 생김')
    print(f'원본: 물체 {len(original["objects"])}개, 탈것 부분 {len(original["vehicles"])}개, '
          f'세트 {len(original["sets"])}개, 다시 넣어 쓰기 0개')
    if doc is None:
        return
    manifest = patch(rom, doc, at, vehicle_at)
    after = built(rom, manifest)
    got = dump(after)
    want = normalized(doc, rom)
    for key in ('objects', 'vehicles', 'sets'):
        if got[key] != want[key]:
            raise ValueError(f'빌드한 롬의 {key} 가 문서와 다름')
    print(f'문서: 쓰기 {len(manifest["writes"])}개, 빌드한 롬을 다시 읽어 물체 {len(got["objects"])}개·탈것·세트가 문서와 같음')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('dump')
    export.add_argument('-o', '--out', type=Path, required=True)
    write = sub.add_parser('patch')
    write.add_argument('source', type=Path)
    write.add_argument('-o', '--out', type=Path, required=True)
    write.add_argument('--at', help='새 칸 바이트를 놓을 곳(16:xxxx)')
    write.add_argument('--vehicle-at', help='칸 수·프레임 수를 바꾼 탈것의 칸 표를 놓을 곳(BB:xxxx)')
    verify = sub.add_parser('check')
    verify.add_argument('source', type=Path, nargs='?')
    verify.add_argument('--at')
    verify.add_argument('--vehicle-at')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        if args.command == 'dump':
            doc = dump(rom)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            print(f'물체 {len(doc["objects"])}개, 탈것 부분 {len(doc["vehicles"])}개, 세트 {len(doc["sets"])}개 → {args.out}')
            return 0
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        at = address(args.at) if args.at else None
        vehicle_at = address(args.vehicle_at, any_bank=True) if args.vehicle_at else None
        if args.command == 'check':
            check(rom, doc, at, vehicle_at)
            return 0
        manifest = patch(rom, doc, at, vehicle_at)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'patch → {args.out} (쓰기 {len(manifest["writes"])}개)')
        return 0
    except (ValueError, OSError, IndexError, PatchError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
