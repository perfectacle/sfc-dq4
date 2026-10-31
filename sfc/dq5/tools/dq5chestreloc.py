"""DQ5 보물상자·조사 보상 표 여섯을 통째로 다시 쓰고, 필요하면 늘려서 다른 자리로 옮긴다.

sfc/dq5/docs/dq5-build-format.md 의 「보물상자·조사 보상 표 옮기기」. 표 크기가 지금 자리에 맞으면 그 자리에 쓰고
코드는 고치지 않는다. 옮기면 표를 읽는 명령의 즉값만 고친다.

  chests(1E:EE4E)     12:E6AC 의 LDA long 하나. 뱅크 00~7D 어디든.
  ahead(1E:F435)      12:FCE5·FCF4·FCFE·FD1D 의 LDA long. 뱅크 00~7D 어디든.
  search(1F:F5CB)     12:FB9D 가 DB 를 12:FBA2 의 즉값으로 두고 abs 8곳(+0·+2·+3)으로 읽는다. 같은 DB 로 WRAM($1E71 등)을
                      abs 로 쓰므로 뱅크 00~3F.
  foot(1E:F08B)       12:E6D7 이 DB 를 12:E6E1 의 즉값으로 두고 abs 8곳으로 읽는다. 뱅크 00~3F(같은 까닭).
  chest_maps(1E:EF90) 1F:FD18·1F:FDD0·25:FAB0 이 DB 를 즉값 셋(1F:FD1B·FDD8·25:FAB5)으로 두고 abs 6곳으로 읽는다.
  lower(1E:F4DF)      12:FD46 의 LDA long 4곳과, 맵에 들어갈 때 1F:FC7B 가 DB 를 1F:FC7E 의 즉값으로 두고 abs 3곳.
                      이 둘은 DB 를 둔 채 2A:FBCD·25:FA15·01:EFE7·00:95DA 등을 부르지만, 그동안 DB 로 닿는 곳은 표 읽기와
                      WRAM($1E71 등)뿐이라(lua/dq5dbread.lua 의 DB 창 감사) 서랍·발밑과 같이 뱅크 00~3F.
일반 상자 수(chest_maps 의 count 합)는 256 까지. 상자 번호 n 은 8비트 덧셈(25:FAB0·1F:FDD0)으로 나오고, 열림 비트는
7E:2210 + n/8(12:E680·1F:FE02 읽기, 12:E697 이 2190 기준 번호 (n/8 | 80) 으로 켬)이라 2210~222F 를 쓴다. 상자가 193개를
넘으면 원래 아래층 상자(2228~2229)·서랍(222C~)의 비트와 겹치므로, 그 항목들의 flag_index 를 빈 비트로 옮겨야 한다.
다섯 표의 열림 비트는 모두 7E:2210~224F 안이어야 하고 서로 겹치면 거부한다. 표 밖의 코드가 직접 보는 비트(RESERVED)는
원래 주인 항목만 쓴다. 발밑·두 칸 앞·아래층 상자는 8비트 색인으로 읽어 행 수 한도(ROW_LIMIT)가 있다.
게임에서는 상자 192·193·256 을 확인했고, 194~255번은 코드 읽기(12:E691·1F:FDD0·25:FAB0)로만 정했다.
--wide-at BB:AAAA 는 상자 번호를 16비트로 바꾸는 훅을 그 자리에 두어 상자를 576개까지 쓴다. 12:E66F(열 때)를 JML 로,
1F:FDD0(들어갈 때)·12:F839(켜기)를 JSL 훅 / RTS 로 바꾸고, 256 이상의 비트는 7E:28F3~291A, 넘길 마스크는 7E:291B 에 둔다.
256 미만은 원래 루틴과 원래 비트(2210~222F)를 그대로 쓴다.
원래 롬에 없는 맵(dq5newmap.py 로 더하는 맵)은 --new-map GG/MM 으로 알리고, 그 맵을 더하는 패치 목록을 --with-patch 로 준다.
그 맵의 크기와 상자 칸은 원래 롬에 그 패치들을 붙여 만든 롬에서 읽고, patch 는 그 패치들과 한 빌드로 겹치지 않는지 보며,
check 는 그 패치들과 함께 빌드한 롬을 다시 읽는다.

  python sfc/dq5/tools/dq5chestreloc.py rom/dq5.sfc dump -o work/chest-tables.json
  python sfc/dq5/tools/dq5chestreloc.py rom/dq5.sfc patch work/chest-tables.json -o work/chest-tables.dq5patch.json \\
      [--chests-at BB:AAAA] [--chest-maps-at …] [--search-at …] [--foot-at …] [--ahead-at …] [--lower-at …] [--wide-at …]
  python sfc/dq5/tools/dq5chestreloc.py rom/dq5.sfc check [work/chest-tables.json] [같은 자리 선택]
  새 맵: patch·check 에 --new-map 36/00 … --with-patch work/newmap.dq5patch.json …
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5build import BANK, FREE_MARGIN, ORIGINAL_SIZE, free_ranges, parse_at
from dq5chest import AHEAD_TABLE, CHEST_ITEMS, CHEST_MAPS, FOOT_TABLE, LOWER_TABLE, SEARCH_TABLE, chests
from dq5chestwrite import NO_NEW_MAPS, NewMaps, decode, encode, field_reward, integer, light_clash, map_dimensions
from dq5gfx import map_ids
from dq5map import Rom, lorom
from dq5palsetwrite import new_map

FORMAT = 'dq5chesttables/1'
ORIGINAL = {'chests': CHEST_ITEMS, 'chest_maps': CHEST_MAPS, 'search': SEARCH_TABLE, 'foot': FOOT_TABLE,
            'ahead': AHEAD_TABLE, 'lower': LOWER_TABLE}
ENTRY = {'chests': 2, 'chest_maps': 3, 'search': 9, 'foot': 9, 'ahead': 8, 'lower': 8}
# 명령 자리(옵코드 주소). LONG 은 3바이트 즉값, ABS 는 (자리, 표 시작에서 더한 값)
LONG = {'chests': (0x12E6AC,), 'ahead': (0x12FCE5, 0x12FCF4, 0x12FCFE, 0x12FD1D),
        'lower': (0x12FD4B, 0x12FD5A, 0x12FD65, 0x12FD71)}
ABS = {'chest_maps': ((0x1FFD23, 0), (0x1FFD38, 0), (0x1FFDE2, 0), (0x1FFDEC, 0), (0x25FAC3, 0), (0x25FAD2, 0)),
       'search': ((0x12FBAA, 0), (0x12FBC6, 0), (0x12FBD8, 2), (0x12FBDF, 3), (0x12FBF2, 0), (0x12FC1F, 2),
                  (0x12FC2A, 3), (0x12FC2D, 0)),
       'foot': ((0x12E6E8, 0), (0x12E700, 0), (0x12E719, 0), (0x12E726, 2), (0x12E72B, 3), (0x12E73C, 0),
                (0x12E742, 2), (0x12E74F, 3)),
       'lower': ((0x1FFC83, 0), (0x1FFC91, 0), (0x1FFC9A, 0))}
# 표 뱅크를 DB 로 두는 즉값 자리. 같은 표의 자리끼리 값이 같아야 한다
DB_SITES = {'search': (0x12FBA2,), 'foot': (0x12E6E1,), 'chest_maps': (0x1FFD1B, 0x1FFDD8, 0x25FAB5),
            'lower': (0x1FFC7E,)}
MAX_CHESTS = 256
# --wide-at: 상자 번호를 16비트로. 상자 256 이상의 열림 비트는 WIDE_BITS + (n - 256)/8 에 둔다. 7E:28E2~2949 는 맡긴 몬스터
# 칸(2332 + 26 × 56) 뒤, 사람 동료 칸(294A) 앞의 틈이다. 770장면 접근 카운터에서 기록·불러오기 말고는 닿은 적이 없고,
# 28F2·291C·2946 만 전투 35~37 에서 읽혀(2238 과 같은 42바이트 간격) 그 사이 41바이트를 쓴다. 끝 바이트 WIDE_PENDING 은 상자를
# 열 때 마스크를 12:F839 까지 넘기는 칸이고, 쓰고 나면 0 으로 되돌린다
WIDE_BITS, WIDE_PENDING = 0x28F3, 0x291B
MAX_WIDE = 256 + (WIDE_PENDING - WIDE_BITS) * 8
# 훅이 덮는 자리와 원래 바이트. 12:E66F 의 JSL $25FAB0 을 JML 로, 1F:FDD0·12:F839 의 머리를 JSL 훅 / RTS 로 바꾼다
WIDE_SITES = {'open': (0x12E66F, bytes.fromhex('22 b0 fa 25')), 'entry': (0x1FFDD0, bytes.fromhex('8b e2 20 48 da')),
              'set': (0x12F839, bytes.fromhex('ae 80 1e bf 90'))}
# 표마다 (열림 비트의 WRAM 주소 = 기준 + flag_index, flag_index 한도). 두 칸 앞은 12:FD7A 가 2190 + (번호 | 80) 으로,
# 아래층 상자는 같은 식과 1F:FCB5 의 2210 + 번호 둘로 읽으므로 7F 이하만 받는다
FLAG_BASE = {'search': (0x222C, 0xFF), 'foot': (0x2240, 0xFF), 'ahead': (0x2210, 0x7F), 'lower': (0x2210, 0x7F)}
FLAG_AREA = (0x2210, 0x2250)
# 표 밖의 코드가 직접 보는 열림 비트: (주소, 비트) → (보는 곳, 그 비트를 원래 쓰는 두 칸 앞 항목의 (BC, BD, X, Y) 또는 None).
# 주인 항목만 그 비트를 쓸 수 있고, 주인 항목의 flag_index·mask 는 바꿀 수 없다. 2238 은 어느 비트를 보는지 몰라 바이트 전체
RESERVED = {**{(0x2238, bit): ('21:8C2F(전투 0C 에서 읽음)', None) for bit in (1, 2, 4, 8, 16, 32, 64, 128)},
            (0x223C, 0x80): ('06:D3CB', (0x10, 0x02, 29, 9)), (0x223D, 0x08): ('12:AE9C', (0x03, 0x04, 10, 7)),
            (0x223D, 0x20): ('12:ADB0', (0x03, 0x0B, 13, 16)), (0x223D, 0x80): ('12:AEA9', (0x15, 0x0A, 28, 35)),
            (0x223E, 0x01): ('12:AEB4', (0x15, 0x0A, 30, 35))}
# 8비트 색인으로 읽는 표의 행 수 한도. 마지막 종료자 낱말을 색인 FE 이하에서 읽어야 한다(행 수 × 크기 ≤ FE)
ROW_LIMIT = {'foot': (28, '12:E6E6'), 'ahead': (31, '12:FCE3'), 'lower': (31, '12:FD48·1F:FC81')}
# 종료자를 못 찾은 표를 끝없이 읽지 않게 두는 한도. 서랍 표 86 이 원래 가장 길다
MAX_ROWS = 255
ORIGINAL_BYTES = {'chests': 161 * 2, 'chest_maps': 83 * 3 + 2, 'search': 86 * 9 + 2, 'foot': 18 * 9 + 2,
                  'ahead': 17 * 8 + 2, 'lower': 11 * 8 + 2}
ROW_FIELDS = {'chests': ('reward',), 'chest_maps': ('group', 'map', 'count'),
              'search': ('group', 'map', 'x', 'y', 'unused', 'reward', 'flag_index', 'mask'),
              'foot': ('group', 'map', 'x', 'y', 'layer', 'reward', 'flag_index', 'mask'),
              'ahead': ('group', 'map', 'x', 'y', 'reward', 'flag_index', 'mask'),
              'lower': ('group', 'map', 'x', 'y', 'reward', 'flag_index', 'mask')}


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def read(rom, addr, size):
    raw = bytes(rom.d[lorom(addr):lorom(addr) + size])
    if len(raw) != size:
        raise ValueError(f'{cpu(addr)}: 롬 범위 밖')
    return raw


def assemble(items):
    """[바이트 | ('label', 이름) | ('br', 옵코드, 이름) | ('table', 옵코드, 더할 값)] → (코드, 표 피연산자 [(오프셋, 더할 값)],
    이름별 오프셋). table 은 표 자리를 긴 주소로 읽는 명령이고 피연산자는 0 으로 비워 둔다."""
    labels, at = {}, 0
    for item in items:
        if isinstance(item, bytes):
            at += len(item)
        elif item[0] == 'label':
            labels[item[1]] = at
        else:
            at += 2 if item[0] == 'br' else 4
    code, sites = bytearray(), []
    for item in items:
        if isinstance(item, bytes):
            code += item
        elif item[0] == 'br':
            delta = labels[item[2]] - (len(code) + 2)
            if not -128 <= delta < 128:
                raise ValueError(f'분기 {item[2]} 가 멂')
            code += bytes([item[1], delta & 0xFF])
        elif item[0] == 'table':
            sites.append((len(code) + 1, item[2]))
            code += bytes([item[1]]) + bytes(3)
    return code, sites, labels


def long(addr):
    return addr.to_bytes(3, 'little')


def wide_items():
    """상자 번호 16비트 훅 셋(open·entry·set). 맵 앞 상자 수를 16비트로 더하고, 256 이상이면 WIDE_BITS 의 비트를 쓴다.
    open 은 12:E66F 에서 JML 로 와서 원래 루틴의 갈래(E669 없음, E675 256 미만, E68B 이미 열림, E6A7 보상)로 JML 한다.
    256 이상이면 $1E80 = 바이트 번호, $1E81 = 0, 마스크는 WIDE_PENDING 에 두고, set(12:F839)은 $1E81 = 0 이고
    WIDE_PENDING 이 0 이 아니고 $1E80 이 WIDE_BITS 안의 바이트 번호일 때만 그 비트를 켠다. 다른 보상은 마스크가 0 이
    아니므로 원래 길로 간다. 잠긴 상자처럼 12:F839 를 거치지 않는 보상은 WIDE_PENDING 을 남기므로 open 이 들어올 때
    지운다.
    entry 는 1F:FDD0 자리(맵에 들어갈 때, A = 맵 안 순서)에서 열렸으면 C 를 켠다."""
    b = bytes.fromhex
    pend, bits = long(0x7E0000 | WIDE_PENDING), long(0x7E0000 | WIDE_BITS)

    def prefix(tag):
        # M·X 16비트. 스택 1,S 에 이 맵 앞 상자 수를 쌓고, 표 끝 FFFF 까지 못 찾으면 none 으로
        return [b('f4 00 00 a2 00 00'), ('label', f'{tag}loop'), ('table', 0xBF, 0), b('c5 bc'), ('br', 0xF0, f'{tag}found'),
                b('c9 ff ff'), ('br', 0xF0, f'{tag}none'), ('table', 0xBF, 2), b('29 ff 00 18 63 01 83 01 e8 e8 e8'),
                ('br', 0x80, f'{tag}loop')]
    return [('label', 'open'), b('e2 20 a9 00 8f') + pend + b('c2 30 af 71 1e 7e 85 00'), *prefix('o'),
            ('label', 'onone'), b('68 e2 30 5c 69 e6 12'),
            # 맵 안 순서는 원래처럼 2A:F224 가 $00(= $1E71) 로 셈
            ('label', 'ofound'), b('e2 30 22 24 f2 2a c2 30 29 ff 00 18 63 01 83 01 c9 00 01'), ('br', 0xB0, 'oext'),
            b('68 e2 30 5c 75 e6 12'),
            ('label', 'oext'), b('38 e9 00 01 48 29 07 00 aa e2 20 bf e9 fa 25 85 07 c2 20 a3 01 4a 4a 4a aa e2 20 bf')
            + bits + b('25 07'), ('br', 0xD0, 'oopen'),
            # 12:E6A7 은 REP #$30 / TYA / ASL 로 내용물 색인을 만들므로 Y 에 16비트 번호를 둔다
            b('8a 8f 80 1e 7e a9 00 8f 81 1e 7e a5 07 8f') + pend + b('c2 30 68 68 a8 5c a7 e6 12'),
            ('label', 'oopen'), b('c2 30 68 68 e2 30 5c 8b e6 12'),
            ('label', 'entry'), b('48 da 85 06 c2 30'), *prefix('e'),
            ('label', 'enone'), b('68 e2 30 fa 68 18 6b'),
            ('label', 'efound'), b('a5 06 29 ff 00 18 63 01 83 01 29 07 00 aa e2 20 bf e9 fa 25 85 06 c2 20 a3 01 c9 00 01'),
            ('br', 0xB0, 'eext'), b('4a 4a 4a aa e2 20 bf 10 22 7e'), ('br', 0x80, 'etest'),
            ('label', 'eext'), b('e9 00 01 4a 4a 4a aa e2 20 bf') + bits,
            ('label', 'etest'), b('25 06 85 06 c2 30 68 e2 30 fa 68 a4 06 c0 01 6b'),
            ('label', 'set'), b('08 e2 30 af 81 1e 7e'), ('br', 0xD0, 'sorig'), b('af') + pend, ('br', 0xF0, 'sorig'),
            # 남은 마스크와 다른 보상의 $1E81 = 0 이 겹쳐도 28F3~291A 밖(294A 사람 동료 칸 등)에 쓰지 않는다
            b('af 80 1e 7e c9') + bytes((WIDE_PENDING - WIDE_BITS,)), ('br', 0xB0, 'sorig'),
            b('aa af') + pend + b('1f') + bits + b('9f') + bits + b('a9 00 8f') + pend, ('br', 0x80, 'send'),
            ('label', 'sorig'), b('af 80 1e 7e aa bf 90 21 7e 0f 81 1e 7e 9f 90 21 7e'),
            ('label', 'send'), b('28 18 6b')]


def wide_code(at, table):
    """at 에 둘 훅 코드와 덮을 자리 쓰기 [(CPU 주소, 바이트, 원래 바이트, 설명)]. table 은 상자 맵 연결 표 자리."""
    code, sites, labels = assemble(wide_items())
    for site, plus in sites:
        code[site:site + 3] = long(table + plus)
    hooks = {'open': b'\x5c' + long(at + labels['open']), 'entry': b'\x22' + long(at + labels['entry']) + b'\x60',
             'set': b'\x22' + long(at + labels['set']) + b'\x60'}
    return [(at, bytes(code), None, '상자 번호 16비트 훅')] + [
        (WIDE_SITES[name][0], hooks[name], WIDE_SITES[name][1], f'상자 번호 16비트 훅으로({name})') for name in hooks]


def wide_at(rom):
    """12:E66F 가 JML 이면 그 자리(이 도구의 훅인지는 locate 가 봄), 아니면 None."""
    head = read(rom, WIDE_SITES['open'][0], 4)
    return int.from_bytes(head[1:], 'little') if head[0] == 0x5C else None


def locate(rom):
    """코드가 가리키는 표 여섯의 CPU 주소. 같은 표를 읽는 자리끼리 값이 다르면 거부한다."""
    out = {}
    wide = wide_at(rom)
    for name in ORIGINAL:
        found = {int.from_bytes(read(rom, site + 1, 3), 'little') for site in LONG.get(name, ())}
        if name == 'chest_maps' and wide is not None:
            # 훅도 이 표를 긴 주소로 읽는다. 훅 코드와 덮은 자리는 그 표 자리로 다시 만든 것과 같아야 한다
            table = int.from_bytes(read(rom, wide + assemble(wide_items())[1][0][0], 3), 'little')
            if any(read(rom, addr, len(data)) != data for addr, data, _, _ in wide_code(wide, table)):
                raise ValueError('12:E66F 의 JML 이 가리키는 곳이 이 도구의 상자 번호 훅이 아님')
            found.add(table)
        if name in ABS:
            banks = {read(rom, site, 1)[0] for site in DB_SITES[name]}
            if len(banks) != 1:
                raise ValueError(f'{name}: DB 즉값 자리끼리 뱅크가 다름 {[f"{b:02X}" for b in sorted(banks)]}')
            bank = banks.pop()
            found |= {bank << 16 | (int.from_bytes(read(rom, site + 1, 2), 'little') - plus) & 0xFFFF
                      for site, plus in ABS[name]}
        if len(found) != 1:
            raise ValueError(f'{name}: 표를 읽는 명령들이 가리키는 자리가 다름 {[cpu(a) for a in sorted(found)]}')
        out[name] = found.pop()
    return out


def row_decode(name, raw):
    if name == 'chests':
        return {'reward': int.from_bytes(raw, 'little')}
    if name == 'chest_maps':
        return dict(zip(ROW_FIELDS[name], raw))
    value = decode(name, raw)
    if name == 'search':
        value['unused'] = raw[4]
    return {key: value[key] for key in ROW_FIELDS[name]}


def parse(rom, loc=None):
    loc = loc or locate(rom)
    doc = {'format': FORMAT}
    for name in ('chest_maps', 'search', 'foot', 'ahead', 'lower'):
        rows, a = [], loc[name]
        while read(rom, a, 2) != b'\xff\xff':
            rows.append(row_decode(name, read(rom, a, ENTRY[name])))
            a += ENTRY[name]
            if len(rows) > MAX_ROWS:
                raise ValueError(f'{name}: 종료자 FFFF 가 없음')
        doc[name] = rows
    total = sum(row['count'] for row in doc['chest_maps'])
    doc['chests'] = [row_decode('chests', read(rom, loc['chests'] + i * 2, 2)) for i in range(total)]
    return {key: doc[key] for key in ('format', *ORIGINAL)}


def row_encode(name, row, label):
    if not isinstance(row, dict) or set(row) != set(ROW_FIELDS[name]):
        raise ValueError(f'{label}: 필드 {list(ROW_FIELDS[name])}를 모두 적은 객체여야 함')
    if name == 'chests':
        return encode(name, bytes(2), row)
    if name == 'chest_maps':
        for key in ROW_FIELDS[name]:
            integer(row[key], 255, f'{label}.{key}')
        if row['count'] == 0:
            raise ValueError(f'{label}: count 는 1 이상이어야 함')
        return bytes(row[key] for key in ROW_FIELDS[name])
    changes = {k: v for k, v in row.items() if k != 'unused'}
    out = bytearray(encode(name, bytes(ENTRY[name]), changes))
    if name == 'search':
        out[4] = integer(row['unused'], 255, f'{label}.unused')
    return bytes(out)


def serialize(rom, doc, new_maps=NO_NEW_MAPS, wide=False):
    """문서 → 표 이름별 바이트. 표에 든 맵·좌표·상자 수를 검사한다. wide 면 상자 번호 16비트 훅과 함께 쓴다."""
    most = MAX_WIDE if wide else MAX_CHESTS
    if not isinstance(doc, dict) or set(doc) != {'format', *ORIGINAL} or doc['format'] != FORMAT:
        raise ValueError(f'format={FORMAT} 과 표 여섯 {list(ORIGINAL)}을 모두 적어야 함')
    available = set(map_ids(rom)) | new_maps.keys
    blobs, dimensions = {}, {}
    for name in ORIGINAL:
        rows, limit = doc[name], most if name == 'chests' else MAX_ROWS
        if not isinstance(rows, list) or len(rows) > limit:
            raise ValueError(f'{name}: {limit}개까지의 배열이어야 함'
                             + ('(257개부터는 --wide-at)' if name == 'chests' and not wide else ''))
        if name in ROW_LIMIT and len(rows) > ROW_LIMIT[name][0]:
            raise ValueError(f'{name}: {ROW_LIMIT[name][1]} 가 8비트 색인으로 읽으므로 {ROW_LIMIT[name][0]}행까지')
        seen, raws = set(), []
        for i, row in enumerate(rows):
            raws.append(row_encode(name, row, f'{name}[{i}]'))
            if name == 'chests':
                continue
            key = (row['group'], row['map'])
            if key not in available:
                raise ValueError(f'{name}[{i}]: 존재하지 않는 맵(새 맵은 --new-map 으로 알림)')
            if name == 'chest_maps' and row['group'] >= 0x50:
                raise ValueError(f'{name}[{i}]: 일반 실내 맵(그룹 50 미만)만 지원함')
            if name != 'chest_maps':
                if key not in dimensions:
                    dimensions[key] = map_dimensions(new_maps.rom_for(rom, key), *key)
                width, height = dimensions[key]
                if row['x'] >= width or row['y'] >= height:
                    raise ValueError(f'{name}[{i}]: 좌표가 맵 {width}×{height} 밖')
                key += (row['x'], row['y']) + ((row['layer'],) if name == 'foot' else ())
            if key in seen:
                raise ValueError(f'{name}[{i}]: 먼저 나오는 항목에 가려지는 중복 {key}')
            seen.add(key)
        blobs[name] = b''.join(raws) + (b'' if name == 'chests' else b'\xff\xff')
    total = sum(row['count'] for row in doc['chest_maps'])
    if total > most or len(doc['chests']) != total:
        raise ValueError(f'chests: 상자 수는 chest_maps 의 count 합({total})과 같고 {most} 이하여야 함'
                         + ('' if wide else '(257개부터는 --wide-at)'))
    flag_bits(doc, wide)
    reward = field_reward(rom)
    if reward is not None:
        light_clash(doc['foot'], reward)
    return blobs


def flag_bits(doc, wide=False):
    """다섯 표의 열림 비트 → {(WRAM 주소, 비트): 항목 이름}. 두 항목이 한 비트를 나눠 쓰면 하나를 열 때 다른 것도 열린다."""
    owner = {}
    keep = {place: bit for bit, (_, place) in RESERVED.items() if place}

    def claim(addr, mask, label, place=None, allow_wide=False):
        if not (FLAG_AREA[0] <= addr < FLAG_AREA[1] or allow_wide and WIDE_BITS <= addr < WIDE_PENDING):
            raise ValueError(f'{label}: 열림 비트 7E:{addr:04X} 가 상자 비트 자리 7E:2210~224F 밖')
        for bit in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01):
            if mask & bit:
                if (addr, bit) in owner:
                    raise ValueError(f'{label}: 열림 비트 7E:{addr:04X} & {bit:02X} 를 {owner[addr, bit]} 가 이미 씀')
                if (addr, bit) in RESERVED and keep.get(place) != (addr, bit):
                    raise ValueError(f'{label}: 열림 비트 7E:{addr:04X} & {bit:02X} 는 {RESERVED[addr, bit][0]} 가 '
                                     '직접 보는 비트라 쓸 수 없음')
                owner[addr, bit] = label
    if len(doc['chests']) > MAX_WIDE:
        raise ValueError(f'chests: 상자는 {MAX_WIDE}개까지(비트 7E:{WIDE_BITS:04X}~{WIDE_PENDING - 1:04X})')
    for n in range(len(doc['chests'])):
        # 256 이상은 --wide-at 훅이 WIDE_BITS 에 둔다. 다른 표의 비트는 2210~224F 안이라 닿지 않는다
        claim((0x2210 if n < 256 else WIDE_BITS - 32) + (n >> 3), 0x80 >> (n & 7), f'일반 상자 {n}', allow_wide=n >= 256)
    for name, (base, limit) in FLAG_BASE.items():
        for i, row in enumerate(doc[name]):
            if row['flag_index'] > limit:
                raise ValueError(f'{name}[{i}]: flag_index 는 {limit:02X} 이하여야 함')
            # 12:F839 훅은 $1E81 = 0 을 상자 256 이상의 표시로 본다
            if wide and row['mask'] == 0:
                raise ValueError(f'{name}[{i}]: --wide-at 에서는 mask 가 0 이 아니어야 함')
            place = (row['group'], row['map'], row['x'], row['y']) if name == 'ahead' else None
            if place in keep and (base + row['flag_index'], row['mask']) != keep[place]:
                addr, bit = keep[place]
                raise ValueError(f'{name}[{i}]: 이 자리의 열림 비트 7E:{addr:04X} & {bit:02X} 는 '
                                 f'{RESERVED[addr, bit][0]} 가 직접 보므로 바꿀 수 없음')
            claim(base + row['flag_index'], row['mask'], f'{name}[{i}]', place)
    return owner


def check_cells(rom, doc, new_maps=NO_NEW_MAPS):
    start = 0
    for i, row in enumerate(doc['chest_maps']):
        key = (row['group'], row['map'])
        cells = chests(new_maps.rom_for(rom, key), *key, start)
        if len(cells) != row['count']:
            raise ValueError(f'chest_maps[{i}]: 맵 상자 셀 {len(cells)}개와 count 가 다름')
        start += row['count']


def original_spans():
    """원래 롬에서 표 여섯이 차지한 자리(종료자 포함). 옮기면 비므로 다른 표를 넣어도 된다.
    이미 옮긴 롬에서는 원래 자리를 다시 읽을 수 없으므로 크기를 적어 두고, check 가 원본과 맞는지 본다."""
    return {name: (ORIGINAL[name], ORIGINAL[name] + ORIGINAL_BYTES[name]) for name in ORIGINAL}


def allowed(original):
    free = []
    for off, size in free_ranges(original):
        start = (off // BANK) << 16 | 0x8000 | off % BANK
        free.append((start, start + size))
    out = [*original_spans().values(), *free]
    for bank in range(ORIGINAL_SIZE // BANK, 0x7E):
        # 이미 늘린 롬(dq5newmap.py 등을 붙여 만든 롬)이면 뱅크 끝의 0 줄만 빈 자리로 본다. 첫 8바이트는 늘릴 때의 표지
        chunk = bytearray(original[bank * BANK:(bank + 1) * BANK])
        if chunk[:8] == b'DQ5X' + bank.to_bytes(4, 'little'):
            chunk[:8] = bytes(8)
        used = len(chunk.rstrip(b'\0'))
        first = (used + FREE_MARGIN + 15) & ~15 if used else 0
        if first < BANK:
            out.append(((bank << 16) + 0x8000 + first, (bank + 1) << 16))
    return merge(out)


def unused(data, start, end):
    """늘린 자리(파일 위치 start~end)에 아직 아무것도 쓰지 않았는지. 원래 크기 롬이면 늘 비어 있고, 이미 늘린 롬이면
    0 이 아닌 바이트가 없어야 한다(뱅크 첫 8바이트 표지는 뺌)."""
    for off in range(start, min(end, len(data))):
        bank = off - off % BANK
        if data[off] and not (off - bank < 8 and data[bank:bank + 4] == b'DQ5X'):
            return False
    return start >= ORIGINAL_SIZE


def rom_mb(rom):
    """이미 늘린 롬의 크기(MB). 만드는 패치의 rom_size 가 이보다 작으면 빌더가 롬을 줄이려 한다."""
    return len(rom.d) // 0x100000 if len(rom.d) > ORIGINAL_SIZE else 0


def merge(spans):
    # 1E:EE4E~F12F 의 상자 내용물·맵 연결·발밑 표처럼 붙어 있는 자리는 하나로 본다. 겹침은 placement 가 따로 본다
    out = []
    for lo, hi in sorted(spans):
        if out and lo <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def placement(rom, sizes, at, extra, space=None):
    """at: 표 이름 → CPU 주소(없으면 지금 자리). 지금 자리는 extra 로 허용한다. 빈 자리는 space(기본 rom)의 바이트로 본다."""
    current = locate(rom)
    free = allowed((space or rom).d)
    at = {name: at.get(name) or current[name] for name in ORIGINAL} | ({'wide': at['wide']} if at.get('wide') else {})
    spans = {}
    for name, size in sizes.items():
        start, bank = at[name], at[name] >> 16
        if not 0x8000 <= start & 0xFFFF or start + size > (bank + 1) << 16:
            raise ValueError(f'{name}: {cpu(start)} 에서 {size}바이트가 한 뱅크(8000~FFFF)에 들어가지 않음')
        if name in DB_SITES and bank > 0x3F:
            raise ValueError(f'{name}: 뱅크 00~3F 만 됨(같은 DB 로 WRAM 을 abs 로 씀)')
        if bank > 0x7D:
            raise ValueError(f'{name}: 뱅크 00~7D 로 적어야 함')
        if not any(lo <= start and start + size <= hi for lo, hi in [*free, *extra.get(name, ())]):
            raise ValueError(f'{name}: {cpu(start)}~ {size}바이트가 원래 표 자리·빈 자리·늘린 뱅크 어느 한 곳에도 들지 않음')
        spans[name] = (start, start + size)
    order = sorted(spans.items(), key=lambda kv: kv[1])
    for (a, (_, end)), (b, (start, _)) in zip(order, order[1:]):
        if start < end:
            raise ValueError(f'{a} 와 {b} 의 자리가 겹침')
    return at


def rom_size(addresses):
    top = max(a >> 16 for a in addresses)
    return 0 if top < 0x30 else 2 if top < 0x40 else 3 if top < 0x60 else 4


def writes_for(rom, doc, at=None, new_maps=NO_NEW_MAPS, space=None):
    """문서와 자리 → [(CPU 주소, 새 바이트, 원래 바이트 또는 None, 설명)] 과 롬 크기(MB). 상자 놓기는 맵 레코드를 쓴
    롬을 rom 으로 주므로, 표를 둘 빈 자리는 입력 롬(space)으로 본다. 레코드와의 겹침은 상자 놓기가 본다."""
    # orig 는 원래 롬 바이트여야 빌더가 붙일 수 있으므로, 이미 옮긴 롬에는 쓰지 않는다
    if locate(rom) != ORIGINAL:
        raise ValueError('표를 옮긴 롬에는 패치를 만들지 않음. 원래 롬에서 만든다')
    at = at or {}
    blobs = serialize(rom, doc, new_maps, bool(at.get('wide')))
    check_cells(rom, doc, new_maps)
    sizes = {name: len(blob) for name, blob in blobs.items()}
    if at.get('wide'):
        sizes['wide'] = len(wide_code(0, 0)[0][1])
    at = placement(rom, sizes, at, {}, space)
    data = [(at[name], blobs[name], f'{name} 표') for name in ORIGINAL]
    if 'wide' in at:
        data += [(addr, new, note) for addr, new, _, note in wide_code(at['wide'], at['chest_maps'])]
    code = []
    for name in ORIGINAL:
        code += [(site + 1, at[name].to_bytes(3, 'little'), f'{name} 표 자리(long)') for site in LONG.get(name, ())]
        code += [(site + 1, ((at[name] + plus) & 0xFFFF).to_bytes(2, 'little'), f'{name} 표 자리(abs)')
                 for site, plus in ABS.get(name, ())]
        code += [(site, bytes([at[name] >> 16]), f'{name} 표 뱅크(DB)') for site in DB_SITES.get(name, ())]
    out = []
    for addr, new, note in data + code:
        old = bytes(rom.d[lorom(addr):lorom(addr) + len(new)]) if lorom(addr) + len(new) <= len(rom.d) else None
        if new != old:
            out.append((addr, new, old if lorom(addr) < ORIGINAL_SIZE else None, note))
    if out:
        # 원래 표 자리 중 새 표가 들지 않은 곳도 같은 바이트로 써서 이 도구가 맡는다. 고정 표 쓰기(dq5chestwrite.py)를
        # 한 빌드에 함께 넣으면 빌더가 겹침으로 거부한다. 같이 넣으면 그 편집이 옮겨 간 표에 닿지 않기 때문이다.
        gaps = []
        for lo, hi in original_spans().values():
            taken = sorted((max(a, lo), min(a + len(n), hi)) for a, n, _, _ in out if a < hi and a + len(n) > lo)
            cursor = lo
            for first, last in taken + [(hi, hi)]:
                if first > cursor:
                    old = read(rom, cursor, first - cursor)
                    gaps.append((cursor, old, old, '원래 표 자리 맡음(바이트 그대로)'))
                cursor = max(cursor, last)
        out += gaps
        out.sort()
    return out, max(rom_size([a for a, _, _, _ in out] or [0]), rom_mb(rom))


def patch(rom, doc, at=None, new_maps=NO_NEW_MAPS):
    writes, mb = writes_for(rom, doc, at, new_maps)
    if new_maps.keys:
        new_maps.merged(rom, [('chest-tables', mb, [(lorom(a), n, o, note) for a, n, o, note in writes])], mb)
    result = {'format': 'dq5patch/1', 'name': 'chest-tables', 'writes': [
        {'at': cpu(addr), 'hex': new.hex(' '), **({'orig': old.hex(' ')} if old is not None else {}), 'note': note}
        for addr, new, old, note in writes]}
    if mb:
        result['rom_size'] = mb
    return result


def check(rom, doc=None, at=None, new_maps=NO_NEW_MAPS):
    if locate(rom) != ORIGINAL:
        raise ValueError('check 는 원래 롬에서 돌린다')
    original = parse(rom)
    if {name: len(blob) for name, blob in serialize(rom, original).items()} != ORIGINAL_BYTES:
        raise ValueError('원래 표 크기가 적어 둔 값과 다름')
    if patch(rom, original)['writes']:
        raise ValueError('원본을 다시 직렬화한 결과가 원래 바이트와 다름')
    source = original if doc is None else doc
    manifest = patch(rom, source, at, new_maps)
    writes = [(lorom(int(w['at'][:2], 16) << 16 | int(w['at'][3:], 16)), bytes.fromhex(w['hex']),
               bytes.fromhex(w['orig']) if 'orig' in w else None, w['note']) for w in manifest['writes']]
    # 새 맵은 --with-patch 와 함께 빌드한 롬에만 있으므로, 그 롬에서 다시 읽는다
    moved = new_maps.merged(rom, [('chest-tables', manifest.get('rom_size', 0), writes)], manifest.get('rom_size', 0))
    loc = locate(moved)
    if parse(moved, loc) != json.loads(json.dumps(source)):
        raise ValueError('만든 롬을 코드가 가리키는 자리에서 다시 읽은 결과가 입력과 다름')
    check_cells(moved, source)
    wide = (at or {}).get('wide')
    if wide_at(moved) != (wide or None):
        raise ValueError('만든 롬의 12:E66F 가 --wide-at 자리를 가리키지 않음')
    if any(read(moved, loc[name], len(blob)) != blob for name, blob in serialize(moved, source, new_maps, bool(wide)).items()):
        raise ValueError('만든 롬의 표 바이트가 입력을 다시 직렬화한 것과 다름')
    counts = ', '.join(f'{name} {len(source[name])}' for name in ORIGINAL)
    print(f'{counts}; 표 자리 {", ".join(f"{k} {cpu(v)}" for k, v in loc.items())}'
          + (f'; 상자 번호 16비트 훅 {cpu(wide)}' if wide else '') + f'; 쓰기 {len(writes)}개, 롬 {manifest.get("rom_size") or 1.5}MB'
          + (f', 새 맵 {len(new_maps.keys)}개를 --with-patch {len(new_maps.lists)}개와 함께 빌드해' if new_maps.keys else '') + ' 검사 통과')


def address(text):
    if not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', text):
        raise argparse.ArgumentTypeError('BB:AAAA 로 적어야 함')
    try:
        off, _ = parse_at(text)
    except Exception as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return (off // BANK) << 16 | 0x8000 | off % BANK


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('dump')
    export.add_argument('-o', '--out', type=Path, required=True)
    write = sub.add_parser('patch')
    write.add_argument('source', type=Path)
    write.add_argument('-o', '--out', type=Path, required=True)
    verify = sub.add_parser('check')
    verify.add_argument('source', type=Path, nargs='?')
    for p in (write, verify):
        for name in ORIGINAL:
            p.add_argument(f'--{name.replace("_", "-")}-at', dest=f'{name}_at', type=address,
                           help=f'기본 지금 자리(원래 {cpu(ORIGINAL[name])})')
        p.add_argument('--wide-at', type=address,
                       help=f'상자 번호 16비트 훅을 둘 자리. 상자를 {MAX_WIDE}개까지 씀(257번째부터 7E:{WIDE_BITS:04X}~)')
        p.add_argument('--new-map', action='append', default=[], type=new_map,
                       help='dq5newmap.py 로 함께 더하는 새 맵 GG/MM(여럿이면 되풀이)')
        p.add_argument('--with-patch', action='append', default=[], type=Path,
                       help='새 맵을 더하는 패치 목록(dq5patch/1). 새 맵을 이 목록들을 붙인 롬에서 읽음')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        at = {k: getattr(args, f'{k}_at', None) for k in (*ORIGINAL, 'wide')}
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        new_maps = NewMaps(rom, getattr(args, 'new_map', []), getattr(args, 'with_patch', []))
        if args.command == 'check':
            check(rom, doc, at, new_maps)
        else:
            result = parse(rom) if args.command == 'dump' else patch(rom, doc, at, new_maps)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'{args.command} → {args.out}')
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
