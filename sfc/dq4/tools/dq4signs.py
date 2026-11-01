"""필드 팻말을 FC 처럼 읽힌다.

DQ5 는 필드에서 「はなす」·「しらべる」 둘 다 주인공 앞 칸에서 팻말 타일(속성 98)을 찾고(12:E5AE), 그 칸 좌표를
팻말 표 1E:F4BF([X][Y][메시지] 16비트 셋, FFFF 끝)에서 찾는다(12:FC9E). 아래를 보고 있으면 표를 보지 않고
뒷면 메시지(137·138)를 띄우는데, 이것은 FC 의 031B 와 같은 규칙이다. 그래서 표를 FC 필드 팻말(1E:$BBB6 의
필드 쪽)로 바꾸고 그 메시지를 한글로 넣는다.

FC 블록 (x, y) 는 DQ5 칸 (2x~2x+1, 2y~2y+1) 이고, 팻말 블록(dq4fieldport 의 15 → 빌린 블록 21)의 속성 98 타일은
오른쪽 아래 칸 (2x+1, 2y+1) 이다.

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


def texts():
    """{DQ5 메시지 번호: 한글 서술}. dq4chapter1.messages 가 넣는다."""
    import dq4sysmsg
    return {slot: dq4sysmsg.message(KOREAN[msg]) for slot, msg in zip(SLOTS, ORDER)}


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
    d = bytearray(data)
    for addr, orig, new in ((TABLE, TABLE_ORIG, body), (READ_BRANCH, READ_BRANCH_ORIG, READ_BRANCH_NEW)):
        o = lorom(addr)
        if bytes(d[o:o + len(orig)]) != orig:
            raise SystemExit(f'{addr:06X}: 원래 바이트가 아님 {d[o:o + len(orig)].hex(" ")}')
        d[o:o + len(new)] = new
    return bytes(d)
