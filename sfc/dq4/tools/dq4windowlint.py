"""롬 실행 없이 창 레코드(04:EB48)의 꼴을 본다.

형식은 sfc/dq4/docs/dq4-window-text-format.md 「창 레코드 정적 검사」. 빌드한 롬의 창마다 줄 내용 칸 수를 코드별 너비 표
(CODE_WIDTHS)로 더해 다음을 본다.

  넘침: 한 줄의 마지막 칸이 창 안쪽 너비(너비 − 2)를 넘는다. 넘친 칸은 오른쪽 테두리를 덮는다.
  덮음: 이름(5칸 그림)이 4칸만 나아가 다음 내용이 다섯째 칸을 덮는다.
  화면: 창이 화면(32열, 버퍼 줄 1~28)을 벗어난다. 일행마다 되풀이하는 창은 일행 넷으로 잰다.
  제목: 제목 자리 + 제목 열 수가 너비 − 1 을 넘는다.
  겹침: 함께 뜨는 창(SHOWN_TOGETHER) 가운데 이 해킹이 옮기거나 넓힌 창이 원래는 겹치지 않던 짝과 겹친다.
  모름: 너비를 모르는 코드가 든 줄. 원래 롬의 같은 줄이 꽉 찼다고 놓고(보수 상한) 넘침을 본다.

  uv run --locked python sfc/dq4/tools/dq4windowlint.py --rom work/ch1/dq4-ch1.sfc --base rom/dq5.sfc
"""
import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'dq5' / 'tools'))

import dq5text  # noqa: E402

WINDOWS = 0x04EB48
WINDOW_COUNT = (0x04EC70 - WINDOWS) // 2     # dq4menupatch.window_count. 뒤는 창마다 1바이트인 다른 표
SHARED_RAM, SHARED_ROM = 0x1AC0, 0x60B400    # 맵을 불러올 때 7E:1AC0 으로 베끼는 공용 창 레코드(dq4menupatch.SHARED_JP)
SCREEN_W, SCREEN_ROWS = 32, 28
# 타일맵 버퍼 줄 y 는 화면에서 한 줄 위(y − 1)에 보인다(BG3 세로 스크롤, dq4windowname.NENE_VIEW_XY). 보이는 버퍼 줄은 1~28
FIRST_ROW = 1
PARTY_MAX = 4
TEXT_BANK, INDEX, FIXED_KIND, MONSTER_KIND, ITEM_KIND = 0x58, 0x8000, 7, 4, 5   # dq4windowtext 의 색인


FC_ROM = Path(__file__).resolve().parents[3] / 'rom' / 'dq4.nes'
DQ5_ROM = Path(__file__).resolve().parents[3] / 'rom' / 'dq5.sfc'


def reachable_items(dq4, dq5=DQ5_ROM):
    """FC 물건 표 전체(1~5장)를 이식 길로 바꾼 DQ5 물건 번호. 가게·보물·몬스터가 떨어뜨림·초기 소지품·사건 지급을 옮기는 길은
    FC 물건을 이름이 같은 DQ5 물건으로 바꾸고(dq4shopport.dq5_items), 이름이 다른 것은 빌린 자리(dq4itemport.BORROWED·
    EVENT_ITEMS)나 상자 대체(dq4chestport.SUBSTITUTE)로 둔다. 이 집합 밖의 물건은 FC 어느 장의 데이터에서도 오지 않는다.
    장마다 실제로 손에 드는 집합보다 넓다(5장 물건도 든다) — 창 너비를 넓게 잡으려는 것이다."""
    import dq4growth
    import dq4itemport
    import dq4shopport
    from dq5map import Rom
    import dq4chestport
    dq4data, prg = dq4growth._fc(dq4)
    known = dq4shopport.dq5_items(Rom(Path(dq5).read_bytes()))
    names = [dq4shopport._fold(name) for _, name, *_ in dq4data.items(prg)]
    # 상자 이식은 DQ5 에 없는 FC 물건을 같은 종류의 다른 DQ5 물건으로 바꾼다(dq4chestport.SUBSTITUTE·SPECIAL_ITEMS)
    names += [dq4shopport._fold(n) for n in (*dq4chestport.SUBSTITUTE.values(), *dq4chestport.SPECIAL_ITEMS.values())]
    out = {known[k] for k in names if k in known}
    return out | set(dq4itemport.BORROWED) | set(dq4itemport.EVENT_ITEMS) | set(dq4chestport.EVENT_CHEST_ITEMS.values())


# 장비한 물건(E0~E3)과 장비 고르기 목록(DE)은 무기·갑옷·방패·투구만 찍는다
EQUIP_CODES = (0xDE, 0xE0, 0xE1, 0xE2, 0xE3)
ITEM_SLOT = 0x23B231               # 물건마다 bit0-2 장비 칸: 0 무기, 1 갑옷, 2 방패, 3 투구, 4 도구(dq5-data-format 「물건 표」)


def is_equipment(data, n):
    return n < 0xD8 and data[lorom(ITEM_SLOT + n)] & 7 < 4


def nine_windows():
    """물건 이름을 아홉 칸 그림으로 그리는 창. 3장 네네 보기 창(extras)도 같은 갈래를 탄다(dq4windowname.asm WnText)."""
    import dq4windowname
    return dq4windowname.NINE_WINDOWS + tuple(range(NENE_KEYS, NENE_KEYS + NENE_PAGES))
FIXED_PREFIX, PIECE_PREFIX = 0x9E, 0x9F      # 9E k = 고정 문구 k(dq4windowtext), 9F n k = 메뉴 패치 그림 조각 n 열
NAME_CELLS = {'base': 4, 'hack': 5}
# 가게 동료 창 3A 의 상태 칸(CC). 원래는 04:B6EA → BC08 아홉 자, 이 해킹은 이 창에서 여덟 자(dq4windowname.SHOP_STATE_CELLS)
import dq4windowname as _wn  # noqa: E402
SHOP_STATE_CELLS = _wn.SHOP_STATE_CELLS

# 코드 → (원래 칸, 이 해킹의 칸, 근거). 칸은 그 코드가 찍고 나아가는 칸 수. 'name' 은 일행 이름(NAME_CELLS, 나아감은
# name_step), ('table', 종류, 원래 칸) 은 이름 표 문자열(이 해킹은 색인 그림 열 수의 최대, 한글이 없으면 가나 글자 수).
# 처리기는 04:B3A2 표(코드 B0~), 숫자는 04:C0AB 가 $00~$07 여덟 자리로 나눈 것을 끝 자리부터 몇 개 찍는지로 잰다(코드 읽기)
CODE_WIDTHS = {
    **{c: (3, 3, '04:B443 $05~$07') for c in range(0xB0, 0xBB)},
    0xBB: (5, 5, '04:B4D8 $03~$07'), 0xBC: (8, 8, '04:B4F8 $00~$07'), 0xBD: (2, 2, '04:B517 $06~$07'),
    0xBE: (1, 1, '04:B529 한 칸 또는 INY×2'), 0xBF: (2, 2, '04:BF67 → B50E 두 자리. 앞 창이 디버그 창 91·92 일 때만 B4D8 다섯 자리'),
    0xC0: (2, 2, '04:B554 → B68D → B516'), 0xC1: (7, 7, '04:B58E $01~$07'), 0xC2: (3, 3, '04:B594 → B443'),
    0xC3: (3, 3, '04:B5B0 → B443'), 0xC4: (2, 2, '04:B5CC → B513'), 0xC5: (5, 5, '04:B5E8 3 + 7E + $07'),
    0xC6: (2, 2, '04:B621 두 칸(탁점은 위 칸)'), 0xC8: (2, 2, '04:B67B → B516'), 0xC9: (9, 9, '04:B6A0 → BC08 아홉 자'),
    0xCA: (3, 3, '04:B6A6 → B446'), 0xCB: (5, 5, '04:B6D6 → B4D8'), 0xCC: (9, SHOP_STATE_CELLS, '04:B6EA → BC08 아홉 자'),
    0xCD: (2, 2, '04:B709 → B516'), 0xCE: (6, 6, '04:B774 $02~$07'), 0xCF: (2, 2, '04:B77A → B516'),
    0xD0: ('name', 'name', '04:B790 → B79B 넉 자, dq4windowname.asm WnList'),
    0xD1: (3, 3, '04:B7D7 석 자, WnText 3열'),
    0xD2: (('table', 1, 10), ('table', 1, 10), '04:B7E2 → B808 표 1(사람)·4'),
    0xD3: (('table', 5, 8), ('table', 5, 10), '04:B82F → BADB → B808 표 5'),
    0xD4: (10, 10, '04:B880 열 자, WnArena'),
    0xD5: (('table', 0x0B, 9), ('table', 0x0B, 9), '04:B88A → B808 표 0B'),
    0xD6: (5, ('table', 3, 5), '04:B8F2 다섯 자, WnSpell'),
    0xD7: (('table', 6, 8), ('table', 6, 10), '04:B911 → B808 표 6'),
    0xD8: (9, 9, '04:B923 → BC41 → BC08 아홉 자'),
    0xD9: ('name', 6, '04:B946 → B79B / dq4windowname ShopSellPrice SHOP_PRICE_COLS'),
    0xDA: (1, 1, '04:B963 → BA1F 한 칸'),
    0xDB: (('table', 1, 10), ('table', 1, 10), '04:B983 → B7FA → B808 표 1·4'),
    0xDC: (20, 'dc', '04:B9A7 이름 넉 자 + 01 01 87 + 두 자리 + 01 01 + B808 표 0B 아홉 자'),
    0xDD: (1, 1, '04:BA14 상태 표시 한 칸'),
    0xC7: ('dc+2', 'dc+2', '04:B65C 번호 + 85, 뒤는 DC 와 같은 04:B9B3'),
    0xDF: ('name+8', 'name+8', '04:BA76 → BE1A: 번호 + 커서 칸 + 이름 + 상태 표시 + 01 87 85 + 두 자리'),
    0xF1: ('name+8', 'name+8', '04:BE00 → BE1A'),
    0xDE: (('table', 5, 8), ('table', 5, 10), '04:BA4B → B84C → B808 표 5'),
    0xE0: (('table', 5, 8), ('table', 5, 10), '04:BAC4 → B808 표 5(장비)'),
    0xE1: (('table', 5, 8), ('table', 5, 10), '04:BAE7 → BACF'), 0xE2: (('table', 5, 8), ('table', 5, 10), '04:BAF5'),
    0xE3: (('table', 5, 8), ('table', 5, 10), '04:BB03'),
    0xE5: (4, 5, '04:BB61 넉 자 두 줄, WnTactic 줄마다 다섯 칸'),
    0xE6: (9, 9, '04:BBB2 → BC08 아홉 자'), 0xED: (9, 9, '04:BDA2 → BC08'), 0xEE: (9, 9, '04:BDA8 → BC08'),
    0xEF: ('name', 'name', '04:BDBB → B794 → B79B'),
}
# 제목 문자열(04:AD78)의 코드(04:AA10 고리). dq4windowtext.TITLE_CODE_COLS 와 같다
# E7 은 제목 14·25 가운데 하나로 이어 가고 그 뒤 바이트는 읽지 않는다(04:AAF3)
TITLE_CODES = {0xE0: ('name', '04:AB06 사람 이름'), 0xE1: ('name', '04:AB06 사람 이름'), 0xE2: (1, '04:AA89'),
               0xE3: (('table', 5, 8), '04:AA68 → ABD6 $0F22 물건 이름'), 0xE4: (9, '04:AA5E 장비 비교 라벨 아홉 자'),
               0xE5: (1, '04:AA4C'), 0xE6: ('name', '04:AAD7 → AB3D 사람 이름'), 0xE7: ('titles', '04:AAF3 제목 14·25')}
TITLE_JUMPS = (0x14, 0x25)


# 함께 뜨는 창 묶음: (장면, 그리는 차례의 창 번호들, 근거). 뒤 창이 앞 창 위에 그려진다. 앞 창의 글자 칸을 뒤 창이 원래보다
# 더 덮으면 「겹침」. 일행마다 열을 되풀이하는 창(02·17 등)은 자리를 게임이 일행 수로 셈해 넣지 않는다
SHOWN_TOGETHER = (
    ('필드 도구', (0x01, 0x0E, 0x0F, 0x10, 0x11), '제목 どうぐ → 물건 목록 → どうする → だれに. 「누구」 창 오른쪽에 도구 목록이 붙음(dq4windowname.NAME_LISTS)'),
    ('필드 주문', (0x01, 0x2C, 0x28, 0x3D), '제목 じゅもん → 주문 목록 → だれを(dq4windowname.NAME_LISTS·SPELL_WINDOW)'),
    ('가게 사기', (0x33, 0x05, 0x39, 0x00, 0x3A), '가게 창 → 골드 창 → 사기 목록(오른쪽에 골드 창이 붙음) → 메시지 창 00 → 누구에게(dq4-window-text-format 「누가」 창)'),
    # 가게 팔기 목록은 창을 열 때 ShopListRes 가 바꿔 주는 레코드라 화면 자리가 창 37·0F 레코드와 다르다(화면에서 목록 x 2,
    # 골드 창·「누가」 창은 그 오른쪽에 가리지 않고 뜸). 자리를 정적으로 알 수 없어 묶음에 넣지 않는다
    ('대열 바꾸기', (0x46, 0x45), 'dq4windowname.FORMATION: 46 은 왼쪽, 45 는 오른쪽으로만 넓혀 둘이 겹치지 않게'),
)


# 숫자 코드 → (값, 자릿수를 넘지 않아야 할 최댓값 또는 None(아직 근거 없음), 근거). 자릿수는 CODE_WIDTHS
NUMBER_FIELDS = {
    0xB0: ('HP', 999, 'fc/dq4/docs/dq4-data-format.md 「상한」 최대 HP 999'),
    0xB1: ('MP', 999, 'fc/dq4/docs/dq4-data-format.md 「상한」 최대 MP 999'),
    0xBB: ('금화', 99999, '7E:2019~201B 24비트. 21:949E·94AE 가 한계 01869F 를 $4A~$4C 에 두고 21:94E8 로 자름(코드 읽기)'),
    0xBC: ('경험치', 0xFFFFFF, '24비트(여덟 자리 안)'),
    0xBD: ('레벨', 99, 'DQ5 엔진 레벨 상한 99'),
    0xC6: ('레벨', 99, 'DQ5 엔진 레벨 상한 99'),
    0xCB: ('값', 0xFFFF, '가게 값 16비트(FC 물건 값, fc/dq4/docs/dq4-shop-format.md)'),
}
# 알려진 걸림 (창, 종류) → 까닭. 고치는 PR 이 그 줄을 지운다. 창·종류 하나씩만 둔다
# 창 표에 없고 창을 열 때 코드가 바꿔 주는 레코드(dq4windowname.asm). 키는 창 번호와 겹치지 않게 100 부터
EXTRA = 0x100
SHOP_SPOT, SHOP_SPOT_END = 0x04FF40, 0x050000          # dq4windowname.SHOP_SPOT: ShopQtyRec·ShopSellRec
NENE_SPOT, NENE_RECORD, NENE_PAGES = 0x04AE21, 10, 8   # dq4windowname.NENE_SPOT: 쪽 줄 수 1~8 마다 레코드 하나
NENE_KEYS = EXTRA + 0x10

ALLOW = {
    (0x7D, '제목'): '제목 사람 이름 5칸(자리 1, 너비 6). 롬에 BRK 95 7D 가 없고 LDA #7D 도 창 열기가 아님. 메뉴 표로 여는 길은 미확인',
    (0x73, '창 밖'): 'D9 를 ShopSellPrice 가 가로챔. 창 73 은 대화 07(몬스터 맡기기 06:E95A)·0A(ルイーダ 06:ED01)의 BRK 95 73 으로만 열리고, DQ4 가게 이식(dq4shopport.SERVICE)은 대화 번호 1~6 만 줘 DQ4 에서 열리지 않음',
    # 「누구」 고르기 창은 오른쪽에 이어 열리는 도구·주문 목록이 붙어 있어 한 칸 왼쪽으로 넓혔다(dq4windowname.NAME_LISTS).
    # 그만큼 뒤에 깔린 창 글자를 한 칸 더 가린다: 설계로 받아들인 값이고, 묶음은 창 제목으로 고른 것이라 화면 확인이 남았다
    (0x0E, '가림'): '도구의 「누구」 창 0E 를 왼쪽으로 한 칸 넓혀 뒤 명령 창 01 글자를 한 칸 더 가림(NAME_LISTS 설계). 화면 확인 남음',
    (0x2C, '가림'): '주문의 「누구」 창 2C 를 왼쪽으로 한 칸 넓혀 뒤 명령 창 01 글자를 한 칸 더 가림(NAME_LISTS 설계). 화면 확인 남음',
    (0x11, '가림'): '건네기 「누구에게」 창 11 이 왼쪽으로 넓힌 0E 의 이름(5칸) 한 칸을 더 가림(NAME_LISTS 설계). 화면 확인 남음',
}


@dataclass
class Cell:
    code: int
    start: int
    step: int
    width: int | None          # 찍는 칸(그림이 덮는 칸). None = 모름
    inner_cover: bool = False  # 코드 안에서 이름(5칸 그림)을 찍고 4칸만 나아가 바로 뒤 글자가 다섯째 칸을 덮음


@dataclass
class Window:
    n: int
    addr: int
    x: int
    y: int
    w: int
    h: int
    per_member: bool
    vertical: bool
    party_height: bool
    tall: bool = False             # +3 bit7: 줄 간격 16점
    title: int | None = None
    title_x: int = 0
    rows: list = field(default_factory=list)

    def row_y(self, r):
        """줄 r 의 글자가 놓이는 버퍼 줄. 제목 창은 제목·가로줄 다음 줄부터(dq5gfx.window_grid)."""
        return self.y + (3 if self.title is not None else 1) + r * (2 if self.tall else 1)


def lorom(a):
    return ((a >> 16) & 0x7F) * 0x8000 + (a & 0x7FFF)


def u16(data, a):
    o = lorom(a)
    return data[o] | data[o + 1] << 8


def record(data, n, depth=0):
    """창 n 의 (주소, 바이트). +0 bit7 은 별칭: +2 의 창을 별칭 +0·+1 의 자리에 연다(04:9C5C, 창 37 = 89 02 0F 는 0F 를
    x 9 y 2 에). 뱅크 04 의 8000 아래는 공용 창 레코드(낮은 WRAM)."""
    a = u16(data, WINDOWS + n * 2)
    if a < 0x8000:
        o = lorom(SHARED_ROM + a - SHARED_RAM)
        addr = 0x7E0000 | a
    else:
        o, addr = lorom(0x040000 | a), 0x040000 | a
    rec = bytes(data[o:o + 0x80])
    if rec[0] & 0x80 and depth < 4 and rec[2] < WINDOW_COUNT:
        _, target = record(data, rec[2], depth + 1)
        return addr, bytes((target[0] & 0xE0 | rec[0] & 0x1F, target[1] & 0xE0 | rec[1] & 0x1F)) + target[2:]
    return addr, rec


class Widths:
    """롬 하나의 코드 너비. kind = 'base'(원래 DQ5 롬) / 'hack'(빌드한 롬)."""

    def __init__(self, data, kind, dq4=None):
        self.data, self.kind, self.dq4 = data, kind, dq4
        self._tables = {}
        self._fixed = {}
        self.wide_items = []        # 아홉 칸 창에서 뺀 열 칸 물건(DQ5 전용, 가나 그림만)
        from dq5map import Rom
        self.rom = Rom(bytes(data))

    def fixed(self, k):
        """고정 문구 k 의 열 수(색인 58:8000 + 7 × 200, 그림 첫 바이트)."""
        if k not in self._fixed:
            at = u16(self.data, TEXT_BANK << 16 | INDEX + FIXED_KIND * 0x200 + k * 2)
            self._fixed[k] = self.data[lorom(TEXT_BANK << 16 | at)] if at else None
        return self._fixed[k]

    def table(self, kind, base_cells):
        """이름 표 kind 문자열이 차지하는 가장 넓은 칸. 원래 롬은 base_cells(처리기가 찍는 최대 글자 수).
        이 해킹은 색인 그림(한글, 또는 Galmuri9 가나)의 열 수 최대. 그림 없이 원래 가나로 찍는 이름은 dq4windowtext.build 가
        종류마다 열 수 상한(KINDS)으로 막는다"""
        if self.kind == 'base':
            return base_cells
        if kind in self._tables:
            return self._tables[kind]
        import dq4windowtext as wt
        widest = 0
        for n in range(0x100 - wt.PLACE_BASE if kind == wt.PLACE_KIND else 0x100):
            slot = wt.index_at(kind, n) if kind == wt.PLACE_KIND else kind * 0x200 + n * 2
            at = u16(self.data, TEXT_BANK << 16 | INDEX + slot)
            if at:
                bank = wt.MONSTER_BANK if kind == MONSTER_KIND else TEXT_BANK
                widest = max(widest, self.data[lorom(bank << 16 | at)])
        self._tables[kind] = widest
        return widest

    def nine(self, equip=False):
        """아홉 칸 창(dq4windowname.NINE_WINDOWS)에서 물건 이름이 차지하는 가장 넓은 칸. 열 칸 그림 뒤(1 + 열 × 9)의
        아홉 칸 그림을 쓰고, 그 열 수가 0 이면 열 칸 그대로(dq4windowname.asm WtNineName)."""
        key = ('nine', equip)
        if key not in self._tables:
            widest = 0
            for n in range(0x100):
                at = u16(self.data, TEXT_BANK << 16 | INDEX + ITEM_KIND * 0x200 + n * 2)
                if not at or equip and not is_equipment(self.data, n):
                    continue
                cols = self.data[lorom(TEXT_BANK << 16 | at)]
                if cols >= 10:
                    second = self.data[lorom(TEXT_BANK << 16 | at + 1 + cols * 9)]
                    if not second and self.excludable(n):
                        # 한글이 없어 가나 그림만 있는 열 칸 이름은 DQ4 명칭표에 없고 FC 물건 표 전체에서도 오지 않는 DQ5 전용 물건이다
                        self.wide_items.append(n)
                        continue
                    cols = second or cols
                widest = max(widest, cols)
            self._tables[key] = widest
        return self._tables[key]

    def dq5_only(self):
        """DQ4 명칭표(nds/dq4/tables/adopt.tsv, dq4windowtext.adopted)에 일본어 이름이 없는 물건 번호."""
        if 'dq5only' not in self._tables:
            import dq4windowtext as wt
            known = wt.adopted(wt.KINDS[ITEM_KIND][0])
            known.update({wt.kana_key(jp): ko for jp, ko in wt.EXTRA_NAMES.get(ITEM_KIND, {}).items()})
            numbered = wt.numbered_names().get(ITEM_KIND, {})
            names = wt.rom_names(self.data, ITEM_KIND)
            self._tables['dq5only'] = {n for n, name in enumerate(names)
                                       if n not in numbered and wt.kana_key(name) not in known}
        return self._tables['dq5only']

    def excludable(self, n):
        """아홉 칸 창의 너비에서 뺄 수 있는 물건: DQ4 명칭표에 없고(dq5_only) FC 물건 표 전체에서도 오지 않는다(reachable)."""
        return n in self.dq5_only() and n not in self.reachable()

    def reachable(self):
        """FC 물건 표 전체에서 올 수 있는 DQ5 물건 번호(reachable_items). FC 롬이 없으면 모든 번호로 보아 아무것도 빼지 않는다."""
        if 'reach' not in self._tables:
            self._tables['reach'] = reachable_items(self.dq4) if self.dq4 else None
        reach = self._tables['reach']
        return set(range(0x100)) if reach is None else reach

    def code(self, b, window=None):
        """코드 b 의 칸 수와 근거. 모르면 (None, None)."""
        if b not in CODE_WIDTHS:
            return None, None
        base, hack, why = CODE_WIDTHS[b]
        v = base if self.kind == 'base' else hack
        if v == 'name':
            return NAME_CELLS[self.kind], why
        if v in ('dc', 'dc+2'):
            name = NAME_CELLS[self.kind]
            dc = 20 if self.kind == 'base' else name + 3 + 2 + 2 + self.table(0x0B, 9)
            return dc + (2 if v == 'dc+2' else 0), why
        if v == 'name+8':
            return NAME_CELLS[self.kind] + 8, why
        if isinstance(v, tuple):
            if v[1] == ITEM_KIND and self.kind == 'hack' and window in nine_windows():
                return self.nine(b in EQUIP_CODES), why
            return self.table(v[1], v[2]), why
        return v, why


def name_step(widths, window, nxt):
    """이름을 찍은 뒤 나아가는 칸(dq4windowname.asm WnList). 원래는 넉 칸."""
    import dq4windowname
    if widths.kind == 'base':
        return NAME_CELLS['base']
    return 5 if nxt in (0xDD, 0xCC) or window in dq4windowname.NAME_STEP5_WINDOWS else 4


def parse(data, n, widths, rec=None, addr=None):
    if rec is None:
        addr, rec = record(data, n)
    win = Window(n, addr, rec[0] & 0x1F, rec[1] & 0x1F, rec[2] & 0x1F, rec[3] & 0x0F,
                 per_member=False, vertical=bool(rec[0] & 0x40), party_height=bool(rec[0] & 0x40 and rec[0] & 0x20))
    win.tall = bool(rec[3] & 0x80)
    if rec[4] & 0x0F:
        win.title, win.title_x = rec[5], rec[4] & 0x0F
        k = 6 + (rec[4] >> 6)
    else:
        k = 5
    # 줄 수 바이트: bit7 = 일행마다 되풀이, 아래 4비트 = 줄 수. bit4 는 줄 수가 아니다(창 06 의 15 는 다섯 줄, 29 의 91 은 한 줄)
    count = rec[k]
    win.per_member = bool(count & 0x80)
    rows, i = count & 0x0F, k + 1
    for _ in range(rows):
        cells, x = [], 0
        while i < len(rec) and rec[i] != 0xFF:
            b = rec[i]
            if b in (0x83, 0x84) and i + 1 < len(rec) and rec[i + 1] not in (0xFE, 0xFF):
                cells.append(Cell(b, x, 1, 1))
                i += 2
            elif b == FIXED_PREFIX:
                w = widths.fixed(rec[i + 1])
                cells.append(Cell(b, x, w or 0, w))
                i += 2
            elif b == PIECE_PREFIX:
                cells.append(Cell(b, x, rec[i + 1], rec[i + 1]))
                i += 3
            elif b < 0xB0 or b == 0xFE:
                cells.append(Cell(b, x, 1, 1))
                i += 1
            else:
                w, _ = widths.code(b, n)
                nxt = rec[i + 1] if i + 1 < len(rec) else 0xFF
                step = name_step(widths, n, nxt) if CODE_WIDTHS.get(b, (None, None))[widths.kind == 'hack'] == 'name' else w
                cells.append(Cell(b, x, step if step is not None else 0, w))
                # 이름을 안에 찍는 묶음 코드(DC·C7·DF·F1)는 이름 뒤 바이트가 자기 레코드의 다음 바이트가 아니라
                # 04:B79B 를 부를 때 X 가 가리키는 그 다음 바이트라, WnList 는 창 번호(45·46)로만 5칸을 고른다
                kind = CODE_WIDTHS.get(b, (None, None))[widths.kind == 'hack']
                # 처리기 안에서 이름 바로 뒤에 찍는 빈칸은 이름 다섯째 칸을 지운다(교회 기록 목록 5D 「크리프ㅡ」, 화면 실측).
                # 레코드 바이트로 오는 빈칸은 지우지 않는다(아래 covered)
                if widths.kind == 'hack' and kind in ('dc', 'dc+2', 'name+8') and name_step(widths, n, nxt) < NAME_CELLS['hack']:
                    cells[-1].inner_cover = True
                i += 1
            x += cells[-1].step
        win.rows.append(cells)
        i += 1
    return win


def title_cols(data, widths, t, window=None):
    """제목 t 의 열 수. 모르는 코드가 있으면 None."""
    a, cols = lorom(dq5text.WINDOW_TITLES), 0
    for _ in range(t):
        a = data.index(0xFF, a) + 1
    i = a
    while data[i] != 0xFF:
        b = data[i]
        if b in (0x92, 0x93):
            i += 2
            cols += 1
            continue
        if b == FIXED_PREFIX:
            w = widths.fixed(data[i + 1])
            if w is None:
                return None
            cols, i = cols + w, i + 2
            continue
        if b >= 0xB0:
            if b not in TITLE_CODES:
                return None
            v = TITLE_CODES[b][0]
            if v == 'titles':
                jumps = [title_cols(data, widths, j, window) for j in TITLE_JUMPS]
                return None if None in jumps else cols + max(jumps)
            if v == 'name':
                cols += NAME_CELLS[widths.kind]
            elif isinstance(v, tuple):
                cols += widths.nine() if v[1] == ITEM_KIND and widths.kind == 'hack' and window in nine_windows() \
                    else widths.table(v[1], v[2])
            else:
                cols += v
        else:
            cols += 1
        i += 1
    return cols


def inner_width(win):
    """줄 내용이 쓸 수 있는 칸. 일행마다 열을 되풀이하는 가로 창은 열 끝 빈칸이 다음 사람과의 경계 열에 놓여 너비 − 1
    (원래 롬의 상태 창 02·17·26·27 이 모두 꼭 맞음)."""
    return win.w - 1 if win.per_member and not win.vertical else win.w - 2


def row_end(cells):
    """줄이 덮는 마지막 칸 + 1. 모르는 칸이 있으면 None."""
    end = 0
    for c in cells:
        if c.width is None:
            return None
        end = max(end, c.start + c.width)
    return end


def covered(cells):
    """이름 그림의 다섯째 칸을 뒤 내용이 덮는 자리 [(이름 코드, 덮은 코드)]."""
    out = [(c.code, 0x01) for c in cells if c.inner_cover]
    for k, c in enumerate(cells):
        if c.width is not None and c.step < c.width:
            for d in cells[k + 1:]:
                # 빈칸 01 은 이름 그림을 지우지 않는다(창 0D 의 「D0 01 01」, 고치기 전후 화면이 같았음)
                if d.start < c.start + c.width and d.code != 0x01:
                    out.append((c.code, d.code))
    return out


def bounds(win):
    """화면에서 차지하는 (왼쪽, 위, 너비, 높이). 일행마다 되풀이하는 창은 일행 넷."""
    w, h = win.w, win.h
    if win.per_member and not win.vertical:
        w = PARTY_MAX * (win.w - 1) + 1
    elif win.party_height:
        h = PARTY_MAX * 2 + 3           # +0 bit6·bit5: 높이 = 일행 수 × 2 + 3(04:9FD3). bit5 가 꺼진 창은 메뉴마다 다른 셈
    return win.x, win.y, w, h




def extras(data):
    """[(키, 이름, 주소, 레코드)]. 가게 팔기 목록(창 37 을 가게일 때 바꿈, 자리는 37 의 것)·가게 개수 창·3장 네네 보기 창."""
    import re
    out = []
    lo, hi = lorom(SHOP_SPOT), lorom(SHOP_SPOT_END - 1) + 1
    seg = bytes(data[lo:hi])
    alias = record(data, 0x37)[1]
    for name, pat, at in (('가게 팔기 목록', rb'\x4f\x03[\x80-\x9f]\xb9\x00\x81\xfe\xd3\x01\xd9\xff', alias),
                          ('가게 개수 창', rb'\x16\x05\x08\x25\x00\x01\x01\xff\x52', None)):
        m = re.search(pat, seg)
        if m:
            rec = seg[m.start():]
            if at is not None:
                rec = bytes((rec[0] & 0xE0 | at[0] & 0x1F, rec[1] & 0xE0 | at[1] & 0x1F)) + rec[2:]
            out.append((name, SHOP_SPOT + m.start(), rec))
    for k in range(NENE_PAGES):
        a = NENE_SPOT + k * NENE_RECORD
        rec = bytes(data[lorom(a):lorom(a) + NENE_RECORD])
        if rec[0] != 0xFF:
            out.append((f'네네 보기 창 {k + 1}줄', a, rec))
    keys = {}
    for i, (name, a, rec) in enumerate(out):
        keys[name] = NENE_KEYS + int(name.split()[-1][:-1]) - 1 if name.startswith('네네') else EXTRA + i
    return [(keys[name], name, a, rec) for name, a, rec in out]


def label(data, n):
    if n is None:
        return '--'
    if n < EXTRA:
        return f'{n:02X}'
    return next(name for k, name, _, _ in extras(data) if k == n)


def windows(data, kind, dq4=None):
    widths = Widths(data, kind, dq4)
    out = {}
    if kind == 'hack':
        for k, _, a, rec in extras(data):
            out[k] = parse(data, k, widths, rec, a)
    for n in range(WINDOW_COUNT):
        try:
            win = parse(data, n, widths)
        except (IndexError, ValueError):
            continue
        if win.w >= 3 and win.h >= 1:
            out[n] = win
    return widths, out


def check(data, base=None, dq4=None):
    """[(창, 종류, 설명)]. base(원래 DQ5 롬)를 주면 모르는 코드가 든 줄을 원래 줄이 꽉 찼다고 놓고 잰다. dq4(FC 롬)가 없으면
    가나 그림만 있는 열 칸 물건을 아홉 칸 창에서 빼지 않는다."""
    widths, wins = windows(data, 'hack', dq4)
    base_wins = windows(base, 'base')[1] if base is not None else {}
    found = []
    for n, win in wins.items():
        inner = inner_width(win)
        for r, cells in enumerate(win.rows):
            end = row_end(cells)
            if end is None:
                b = base_wins.get(n)
                known = sum(c.width for c in cells if c.width is not None)
                if b is None or r >= len(b.rows):
                    unknown = sorted({c.code for c in cells if c.width is None})
                    found.append((n, '모름', f'줄 {r}: 코드 {" ".join(f"{c:02X}" for c in unknown)} 너비 모름'))
                    continue
                bknown = sum(c.width for c in b.rows[r] if c.width is not None)
                slack = inner_width(b) - bknown            # 원래 줄의 모르는 코드가 쓸 수 있던 칸(보수 상한)
                end = known + slack
                if end > inner:
                    found.append((n, '창 밖', f'줄 {r}: 아는 칸 {known} + 원래 남은 칸 {slack} > 안쪽 {inner}(보수 상한)'))
                continue
            if end > inner:
                found.append((n, '창 밖', f'줄 {r}: {end}칸 > 안쪽 {inner}칸 ({describe(cells)})'))
            for a, b in covered(cells):
                found.append((n, '테두리', f'줄 {r}: 이름({a:02X}) 다섯째 칸을 {b:02X} 가 덮음'))
        x, y, w, h = bounds(win)
        if not (win.per_member and not win.vertical) and x + w > SCREEN_W:
            found.append((n, '화면 밖', f'x {x} + 너비 {w} > {SCREEN_W}'))
        if win.per_member and not win.vertical and w > SCREEN_W:
            found.append((n, '화면 밖', f'일행 {PARTY_MAX} 너비 {w} > {SCREEN_W}'))
        if y < FIRST_ROW - 1 or y + h > SCREEN_ROWS + FIRST_ROW:
            found.append((n, '화면 밖', f'y {y} + 높이 {h} > {SCREEN_ROWS + FIRST_ROW}'))
        if win.title is not None:
            cols = title_cols(data, widths, win.title, n)
            if cols is None:
                found.append((n, '모름', f'제목 {win.title:02X} 너비 모름'))
            elif win.title_x + cols > win.w - 1:
                found.append((n, '제목', f'제목 {win.title:02X}: 자리 {win.title_x} + {cols}열 > {win.w - 1}'))
    if base is not None:
        found += [(n, '가림', text) for n, text in overlaps(data, base)]
        found += [(n, '변 어긋남', text) for n, text in edges(data, base)]
    for code, (what, top, _) in NUMBER_FIELDS.items():
        digits = CODE_WIDTHS[code][1]
        if top is not None and len(str(top)) > digits:
            found.append((None, '자릿수', f'{code:02X} {what}: 최대 {top} 이 {digits}자리를 넘음'))
    return found


def unknown_numbers():
    """최댓값 근거가 없는 숫자 코드(남은 것)."""
    return [(code, what, why) for code, (what, top, why) in NUMBER_FIELDS.items() if top is None]


def content(win, data, widths):
    """창이 글자를 찍는 화면 칸 집합(빈칸 01 은 뺌)."""
    out = set()
    for r, cells in enumerate(win.rows):
        y = win.row_y(r)
        for c in cells:
            if c.code != 0x01 and c.width:
                out.update((win.x + 1 + c.start + k, y) for k in range(c.width))
    if win.title is not None:
        cols = title_cols(data, widths, win.title) or 0
        out.update((win.x + win.title_x + k, win.y + 1) for k in range(cols))
    return out


def rect_cells(win):
    return {(x, y) for x in range(win.x, win.x + win.w) for y in range(win.y, win.y + win.h)}


def hidden(data, widths, wins, group):
    """묶음에서 앞 창의 글자 칸 가운데 뒤 창이 덮는 칸 {(앞, 뒤): 칸 수}."""
    out = {}
    for i, a in enumerate(group):
        if a not in wins:
            continue
        text = content(wins[a], data, widths)
        for b in group[i + 1:]:
            if b in wins:
                out[(a, b)] = len(text & rect_cells(wins[b]))
    return out


def overlaps(data, base):
    """[(창, 설명)]. 원래 롬보다 앞 창 글자를 더 덮는 짝."""
    hw, hack = windows(data, 'hack')
    bw, orig = windows(base, 'base')
    found = []
    for scene, group, _ in SHOWN_TOGETHER:
        now, was = hidden(data, hw, hack, group), hidden(base, bw, orig, group)
        for (a, b), k in now.items():
            if k > was.get((a, b), 0):
                found.append((b, f'{scene}: 창 {b:02X} 가 앞 창 {a:02X} 의 글자 {k}칸을 덮음(원래 {was.get((a, b), 0)}칸)'))
    return found


def sides(win):
    x, y, w, h = win.x, win.y, win.w, win.h
    return {'왼쪽': x, '오른쪽': x + w - 1, '위': y, '아래': y + h - 1}


def misaligned(wins, group):
    """{(앞, 뒤, 쪽)}: 함께 뜨는 두 창의 같은 쪽 변이 정확히 1칸 차이. 사람마다 되풀이하는 창은 자리를 게임이 셈해 뺀다."""
    out = set()
    shown = [n for n in group if n in wins and not wins[n].per_member]
    for i, a in enumerate(shown):
        for b in shown[i + 1:]:
            sa, sb = sides(wins[a]), sides(wins[b])
            out.update((a, b, k) for k in sa if abs(sa[k] - sb[k]) == 1)
    return out


def edges(data, base):
    """[(창, 설명)]. 원래 롬에 없던 1칸 변 어긋남(원래부터 있던 쌍은 원본과 같아 뺌)."""
    _, hack = windows(data, 'hack')
    _, orig = windows(base, 'base')
    found = []
    for scene, group, _ in SHOWN_TOGETHER:
        for a, b, k in sorted(misaligned(hack, group) - misaligned(orig, group)):
            found.append((b, f'{scene}: 창 {b:02X} 의 {k} 변이 창 {a:02X} 와 1칸 어긋남'))
    return found


def describe(cells):
    return ' '.join(f'{c.code:02X}@{c.start}+{c.width}' for c in cells)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', required=True, help='빌드한 롬')
    ap.add_argument('--base', required=True, help='원래 DQ5 롬(모르는 코드가 든 줄의 보수 상한, 겹침의 원래 꼴)')
    ap.add_argument('--dump', action='store_true', help='창마다 줄 칸을 찍음')
    ap.add_argument('--dq4', default=str(FC_ROM), help='FC 롬(FC 물건 표 전체가 옮겨 오는 DQ5 물건을 셈)')
    args = ap.parse_args()
    data = Path(args.rom).read_bytes()
    base = Path(args.base).read_bytes()
    if args.dump:
        _, wins = windows(data, 'hack')
        for n, win in wins.items():
            print(f'{n:02X} {win.addr:06X} x{win.x} y{win.y} w{win.w} h{win.h}'
                  f'{" 일행" if win.per_member else ""}{" 세로" if win.vertical else ""}')
            for cells in win.rows:
                print('   ', describe(cells))
    found = check(data, base, args.dq4)
    fail = 0
    for n, kind, text in found:
        why = ALLOW.get((n, kind))
        print(f'{label(data, n)} {kind} {text}' + (f' [예외: {why}]' if why else ''))
        fail += not why
    # 고쳐서 더 걸리지 않는 예외는 지워야 다음 넘침을 가리지 않는다
    stale = sorted(set(ALLOW) - {(n, kind) for n, kind, _ in found})
    for n, kind in stale:
        print(f'{label(data, n)} {kind} 지난 예외: 더 걸리지 않으니 ALLOW 에서 지울 것')
    fail += len(stale)
    widths = Widths(data, 'hack', args.dq4)
    widths.nine()
    if widths.wide_items:
        print('-- 남은 것 아홉 칸 창에서 뺀 DQ5 전용 열 칸 물건: ' + ' '.join(f'{n:02X}' for n in widths.wide_items))
    for code, what, why in unknown_numbers():
        print(f'-- 남은 것 {code:02X} {what}: {why}')
    print(f'걸림 {fail}건, 예외 {len(found) - fail + len(stale)}건')
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
