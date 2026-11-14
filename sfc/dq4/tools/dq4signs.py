"""필드 팻말을 FC 처럼 읽힌다.

DQ5 는 필드에서 「はなす」·「しらべる」 둘 다 주인공 앞 칸에서 팻말 타일(속성 98)을 찾고(12:E5AE), 그 칸 좌표를
팻말 표 1E:F4BF([X][Y][메시지] 16비트 셋, FFFF 끝)에서 찾는다(12:FC9E). 아래를 보고 있으면 표를 보지 않고
뒷면 메시지(137·138)를 띄우는데, 이것은 FC 의 031B 와 같은 규칙이다. 그래서 표를 FC 필드 팻말(1E:$BBB6 의
필드 쪽)로 바꾸고 그 메시지를 한글로 넣는다.

FC 블록 (x, y) 는 DQ5 칸 (2x~2x+1, 2y~2y+1) 이고, 팻말 블록(dq4fieldport 의 15 → 빌린 블록 21)의 속성 98 타일은
오른쪽 아래 칸 (2x+1, 2y+1) 이다.

실내(맵 쪽) 팻말도 같은 길이다. DQ5 실내의 「はなす」(앞에 인물이 없을 때 12:FD9B)·「しらべる」(12:E4C9 의 차례)는
12:EB53 에서 주인공 앞 칸들의 위층 속성(+7)이 97 인 칸을 찾고, 아래를 보고 있으면 뒷면(종류 6), 아니면 그 칸을 실내
팻말 표 1E:F12F([BC BD][X Y][메시지] 16비트 셋, FFFF 끝)에서 찾는다(12:FC60). 옮긴 맵의 FC 팻말 블록(속성 A8)은
dq4environmentrom.FURNITURE 가 위층 속성 97 로 두고, 표는 그 블록에서 12:EB53 이 찾는 세 칸을 FC 실내 팻말 메시지로 둔다.

형식은 sfc/dq4/docs/dq4-field-format.md 「팻말」.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

from dq5map import lorom  # noqa: E402

TABLE = 0x1EF4BF
TABLE_ORIG = bytes.fromhex('b700c5008101 85009900 8001 2700f900 8201 d1007101 8501 97014300 7f01 ffff')
# DQ5 팻말 글이 쓰던 번호. 183·184 는 책장이라 남긴다
SLOTS = (0x17F, 0x180, 0x181, 0x182, 0x185)
# 12:F2E7 BRK 0B 40 00 / BNE: 7E:2190 bit6(어른)이 꺼져 있으면 「まだ字が読めなかった」(169)로 가고 팻말 글을 띄우지
# 않는다. DQ4 에는 글을 못 읽는 시절이 없으므로 늘 「팻말을 읽었다」(136) 뒤 팻말 글로 가게 BRA 로 바꾼다
READ_BRANCH = 0x12F2EB
READ_BRANCH_ORIG = b'\xd0'
READ_BRANCH_NEW = b'\x80'
FIELD_TABLE = 1
# FC 메시지 → 한글. 원문은 두 줄이고 / 에서 줄을 바꾼다. 지명은 NDS 한글패치 명칭(nds/dq4/tables/adopt.tsv)
KOREAN = {
    0x3D9: '수상한 것을 발견하면/성으로! 바트랜드 왕.',
    0x3DA: '다리는 모두의 것./부수지 않도록 합시다.',
    0x3DB: '여기서 동쪽/텐페 마을.',
    0x3DC: '숲 속에서는/놀지 않도록.',
    0x3FE: '여기서 북쪽/코미즈 마을.',
}
# FC 필드 팻말 표(1E:$BBB6 의 필드 쪽)의 메시지 차례. 메시지 번호를 롬 없이 정하려고 둔다. apply 가 롬 표와 같은지 본다
ORDER = (0x3D9, 0x3DA, 0x3DB, 0x3DC, 0x3FE)


MAP_TABLE = 0x1EF12F
# DQ5 실내 팻말 25개(DQ5 그룹 00~31 의 맵). 이 해킹은 그 맵들을 쓰지 않으므로 표를 통째로 바꾼다
MAP_TABLE_ORIG = bytes.fromhex(
    '0007 0a09 8b03 0100 2347 f002 010b 0b04 f802 010c 2116 f002 0201 1e21 7c01 0202 1a2a 7601 0400 141b 1e02'
    '0400 111b 2002 0402 0302 2202 0407 0302 2202 0900 3d2b 7301 1400 0925 6f01 1403 4011 7e01 1900 1e14 7001'
    '1900 0620 7701 1d00 3105 7401 1d03 0302 7501 1f04 0e02 7801 1f08 1104 4c05 2000 1a34 7901 2006 1b22 7a01'
    '2102 271d 6d01 2109 0904 8301 2302 0802 7b01 310b 0b0b 7d01 ffff')
# 위 표의 DQ5 실내 팻말 글 번호(책장 183 은 남긴다)
MAP_SLOTS = (0x16D, 0x16F, 0x170, 0x173, 0x174, 0x175)
# FC 블록 (x, y) 의 팻말에서 12:EB53 이 찾는 칸(실측): 아래에서 주인공 X 가 2x-1·2x·2x+1 이면 (2x,2y)·(2x+1,2y)·
# (2x+1,2y+1), 왼쪽·오른쪽에서는 (2x+1,2y)·(2x+1,2y+1). (2x,2y+1) 은 어느 쪽에서도 찾지 않았다
MAP_CELLS = ((0, 0), (1, 0), (1, 1))
MAP_TABLE_FC = 0
# FC 표 0 의 메시지 00 은 장마다 셋 가운데 하나(dq4block.SIGN_CHAPTER: 1·2장, 3장, 4장부터). 이 롬은 2장까지라 첫째
MAP_CHAPTER = 0
MAP_KOREAN = {
    0x3D0: '무술 대회/개최 중!',
    0x3D3: '사막의 바자/개최 중!',
    0x3D5: '잠깐 기다려!/그런 장비로는 위험하다!/사란 무기 방어구 연맹.',
    0x3D6: ('하늘 저 높은 곳에는 천공성이 있고 용의 신님이 살고 있대.|'
            '용의 신님은 무척 강해서 아주 먼 옛날 지옥의 제왕을 어둠 속에 봉인했을 정도래.|'
            '천공성에 대해서는 북쪽 바다의 스탄시아라 사람들이 잘 알 거야.'),
    0x3D7: '화단에 들어가서는/안 됩니다!',
    0x3D8: '연금술사 에드간의 집.',
}
# 말로 된 팻말(FC 원문이 ＊「 로 시작)
MAP_SPEECH = {0x3D6}
# 옮긴 맵의 FC 실내 팻말 메시지 차례(DQ5 그룹·맵·칸 차례로 처음 나온 차례). 롬 없이 번호를 정하려고 둔다. apply 가 롬과 같은지 본다
MAP_ORDER = (0x3D7, 0x3D0, 0x3D8, 0x3D6, 0x3D5, 0x3D3)


def texts():
    """{DQ5 메시지 번호: 한글 서술}. dq4chapter1.messages 가 넣는다."""
    import dq4sysmsg
    out = {slot: dq4sysmsg.message(KOREAN[msg]) for slot, msg in zip(SLOTS, ORDER)}
    out.update({slot: dq4sysmsg.message(MAP_KOREAN[msg], narrate=msg not in MAP_SPEECH)
                for slot, msg in zip(MAP_SLOTS, MAP_ORDER)})
    return out


SIGN_PROP = 0xA8


def map_sign_sources(prg):
    """옮긴 맵의 FC 실내 팻말 [(DQ5 그룹, 맵, FC 블록 x, y, FC 메시지, FC 맵)]. FC 표 0 은 좌표만 보므로(그룹을 보지
    않음) 옮긴 맵 가운데 그 좌표 블록이 팻말(속성 A8)인 맵에 둔다."""
    import dq4block
    import dq4groupbuild
    place = dq4groupbuild.placement(prg)
    table = [e for e in dq4block.signs(prg) if e['table'] == MAP_TABLE_FC]
    out = []
    for _, source in dq4block.all_maps(prg):
        if source.buf is None or (source.g, source.k) not in place:
            continue
        g, m = place[source.g, source.k]
        for e in table:
            x, y = e['x'], e['y']
            if x < source.w and y < source.h and source.blocks['prop'].get(source.cell(x, y) & 31) == SIGN_PROP:
                out.append((g, m, x, y, e['msg'][MAP_CHAPTER] if len(e['msg']) > 1 else e['msg'][0], source))
    return sorted(out, key=lambda t: t[:5])


def map_signs(prg):
    """옮긴 맵의 FC 실내 팻말 [(DQ5 그룹, 맵, FC 블록 x, y, FC 메시지)]."""
    return [t[:5] for t in map_sign_sources(prg)]


def map_table(prg):
    """(1E:F12F 에 쓸 바이트, {DQ5 메시지 번호: FC 메시지})."""
    signs = map_signs(prg)
    order = list(dict.fromkeys(msg for *_, msg in signs))
    if len(order) > len(MAP_SLOTS):
        raise ValueError(f'FC 실내 팻말 메시지 {len(order)}개가 자리 {len(MAP_SLOTS)}개보다 많음')
    slot_of = dict(zip(order, MAP_SLOTS))
    body = bytearray()
    for g, m, x, y, msg in signs:
        for dx, dy in MAP_CELLS:
            body += bytes((g, m, 2 * x + dx, 2 * y + dy)) + slot_of[msg].to_bytes(2, 'little')
    body += b'\xff\xff'
    if len(body) > len(MAP_TABLE_ORIG):
        raise ValueError(f'실내 팻말 표 {len(body)}바이트가 원래 자리 {len(MAP_TABLE_ORIG)}바이트보다 김')
    return bytes(body), {slot: msg for msg, slot in slot_of.items()}


def field_signs(prg):
    """FC 필드 팻말 [(DQ5 칸 x, y, FC 메시지)]. FC 표 차례."""
    import dq4block
    out = []
    for e in dq4block.signs(prg):
        if e['table'] == FIELD_TABLE:
            (msg,) = e['msg']
            out.append((2 * e['x'] + 1, 2 * e['y'] + 1, msg))
    return out


def table(prg):
    """(1E:F4BF 에 쓸 바이트, {DQ5 메시지 번호: FC 메시지})."""
    signs = field_signs(prg)
    if len(signs) > len(SLOTS):
        raise ValueError(f'FC 필드 팻말 {len(signs)}개가 메시지 자리 {len(SLOTS)}개보다 많음')
    body, slots = bytearray(), {}
    for (x, y, msg), slot in zip(signs, SLOTS):
        body += x.to_bytes(2, 'little') + y.to_bytes(2, 'little') + slot.to_bytes(2, 'little')
        slots[slot] = msg
    body += b'\xff\xff'
    if len(body) > len(TABLE_ORIG):
        raise ValueError('팻말 표가 원래 자리보다 김')
    return bytes(body), slots


def apply(data, prg):
    body, slots = table(prg)
    if tuple(slots[s] for s in SLOTS[:len(slots)]) != ORDER:
        raise SystemExit(f'FC 필드 팻말 메시지 차례가 ORDER 와 다름: {[f"{m:03X}" for m in slots.values()]}')
    map_body, map_slots = map_table(prg)
    if tuple(map_slots[s] for s in MAP_SLOTS[:len(map_slots)]) != MAP_ORDER:
        raise SystemExit(f'FC 실내 팻말 메시지 차례가 MAP_ORDER 와 다름: {[f"{m:03X}" for m in map_slots.values()]}')
    d = bytearray(data)
    for addr, orig, new in ((TABLE, TABLE_ORIG, body), (READ_BRANCH, READ_BRANCH_ORIG, READ_BRANCH_NEW),
                            (MAP_TABLE, MAP_TABLE_ORIG, map_body)):
        o = lorom(addr)
        if bytes(d[o:o + len(orig)]) != orig:
            raise SystemExit(f'{addr:06X}: 원래 바이트가 아님 {d[o:o + len(orig)].hex(" ")}')
        d[o:o + len(new)] = new
    return bytes(d)
