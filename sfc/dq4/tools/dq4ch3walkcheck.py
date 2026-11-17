"""3장 사건을 구간마다 따로 걷는 검사(MesenCE 헤드리스). 걷기·순간이동·판정과 묶음 나누기는 2장 검사와 같은
틀(dq4chapterwalk.py)이고, 구간 표·flag 표·출발 상태만 3장 것이다.

  머리  2장 걷기 검사의 2장 출발 상태(dq4ch2walkcheck.head, 캐시)에서 3장 첫머리 검사 구간(dq4ch3opencheck:
        우승 뒤 빈 산트하임 → 2장 끝 → 3장 넘김 → 톨네코 집 첫머리)을 시드 0 으로 걷는다. 끝 상태가 「3장 출발
        상태」(3E/01, 조작 풀림)이고, 같은 캐시 폴더에 둔다(ch3-start-<지문>.mss). 캐시는 --repeat 2 로 머리를 두 번
        걸어 기록이 같을 때만 넣는다.
  묶음  SEGMENTS 는 순간이동 구간마다 묶음 하나다. 묶음마다 3장 출발 상태에서 따로 시작해 함께 돈다(--jobs).
        묶음 첫 구간에는 앞 구간들이 켰을 flag(want·off)와 기록에 남기는 것(effects)을 SET·PARTY 로 둔다.

난수·시각·조우는 2장 검사와 같이 묶는다. --repeat 2 는 묶음마다 두 번 걸어 구간 기록의 SHA-1 이 같은지 본다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4ch3walkcheck.py --rom work/ch3/dq4-ch1-full.sfc --out work/ch3walk
  (--only 구간,… 은 그 구간으로 시작하는 묶음만, --base 는 3장 출발 상태를 다시 쓴다)

롬은 dq4build.py --chapter3 의 출력이어야 한다(2장 끝에서 3장으로 넘어감). 구간을 붙이는 법은
sfc/dq4/docs/dq4-chapter3-format.md 「검사」.
"""
import functools
import inspect
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch2walkcheck as cw  # noqa: E402
import dq4ch3endor as endor  # noqa: E402
import dq4ch3bonmalmo as bm  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
import dq4ch3lakanaba as lakanaba  # noqa: E402
import dq4ch3opencheck as opening  # noqa: E402
import dq4ch3safe as safe  # noqa: E402
import dq4ch3tunnel as tunnel  # noqa: E402
import dq4chapterwalk as cwk  # noqa: E402

talk, taps = wc.talk, wc.taps
CLOSE = wc.pc.CLOSE

# 2장 검사의 flag 표(dq4ch3opencheck 가 3장 flag 와 첫머리 바이트를 더한 것)에 3장 사건 flag 를 더한다. 새 사건 flag 는
# 여기에 한 줄씩: 'NAME': wc.flag(모듈.FLAG)
FLAGS = {
    **cw.FLAGS,
    'SAFE_DRAINED': wc.flag(safe.DRAINED),
    'SAFE_ANSWERED': wc.flag(safe.ANSWERED),
    'SAFE_YES': wc.flag(safe.YES),
    # 톨네코 물건 칸 2(칸 0 옷, 칸 1 도시락 다음): 금고 상자를 열면 철 금고가 들어오는 칸
    'SAFE_SLOT': (0x7E2056 + 2, 0xFF),
    'BENTO': wc.flag(lakanaba.BENTO_TODAY), 'SEEN': wc.flag(lakanaba.SEEN), 'SHIFT': wc.flag(lakanaba.SHIFT),
    'TOM_PUSH': wc.flag(lakanaba.TOM_PUSH), 'SCOTT_DAYS': (ch3.SCOTT_DAYS, 0xFF),
    # 구르는 바위(dq4boulder)의 메움 비트(bit0 왼쪽 구덩이, bit1 가운데)
    'SAFE_FILL': (safe.BOULDER_VARS(safe.boulder.FILL), 0xFF),
    'RAFT_RIDING': wc.flag(safe.RIDING),
    'RAFT_X': (safe.RAFT_VARS + safe.raft.RX, 0xFF),
    'RAFT_Y': (safe.RAFT_VARS + safe.raft.RY, 0xFF),
    **{f'ENDOR_{k}': wc.flag(getattr(endor, k)) for k in ('ALLOWED', 'SHOP', 'ORDER', 'DELIVERED', 'SOLD', 'SON_CHEER',
                                                          'NOTICE', 'BUTTON', 'ASKED', 'PRESSED')},
    'ENDOR_COUNT': (ch3.VARS_AT + ch3.SLOTS['E'].vars[0] + endor.VARS, 0xFF),
    'SCOTT': wc.flag(ch3.SCOTT), 'LAWRENCE': wc.flag(ch3.LAWRENCE), 'LAWRENCE_DAYS': (ch3.LAWRENCE_DAYS, 0xFF),
    'PARTY_N': (0x7E201D, 0xFF), 'PARTY1': (ch3.PARTY_ITEMS - 0x16 + ch3.RECORD, 0xFF),
    'GOLD0': (ch3.GOLD_AT, 0xFF), 'GOLD1': (ch3.GOLD_AT + 1, 0xFF), 'GOLD2': (ch3.GOLD_AT + 2, 0xFF),
    'DOG': wc.flag(ch3.DOG),
    'BM_FOXED': wc.flag(bm.FOXED),
    'BM_PRINCE_MET': wc.flag(bm.PRINCE_MET),
    'BM_SON_FREED': wc.flag(bm.SON_FREED),
    'BM_BRIDGE': wc.flag(bm.BRIDGE),
    'BM_LETTER1': wc.flag(bm.LETTER1),
    'BM_LETTER2': wc.flag(bm.LETTER2),
    'BM_FOX_SCENE': wc.flag(bm.FOX_SCENE),
    # 톨네코 물건 칸 2(칸 0 옷, 칸 1 도시락 다음): 사건 물건을 두고 빠지는지 보는 칸
    'BM_SLOT2': (0x7E2056 + 2, 0xFF),
    'BM_BAG_LETTER': (0x7E2250 + bm.PRINCE_LETTER, 0xFF),
    'TUNNEL_PAID': wc.flag(tunnel.PAID),
    'TUNNEL_WAITING': wc.flag(tunnel.WAITING),
    'TUNNEL_RESUMED': wc.flag(tunnel.RESUMED),
    'TUNNEL_OPENED': wc.flag(tunnel.OPENED),
    'TUNNEL_GOLD0': (0x7E2019, 0xFF), 'TUNNEL_GOLD1': (0x7E201A, 0xFF), 'TUNNEL_GOLD2': (0x7E201B, 0xFF),
}

TOWN = '3E/00'                 # FC 16/00 레이크나바
# 3장 출발 상태(3E/01)와 같은 맵으로 순간이동하는 묶음이 먼저 들르는 곳
HOPS = {ch3.HOUSE: f'{TOWN},4,26'}


def effects(data):
    """구간이 flag 말고 기록(7E:2000~2A9F)에 남기는 것(구간 이름 → SET(set)·dq5warp.lua PARTY(party)). 묶음 첫
    구간에 둔다. 롬의 기록 틀을 읽는 것이 있어 롬 바이트를 받는다."""
    import dq4mercenary as merc
    rec = merc.record(data, 'lawrence')
    party = ';'.join(f'{(ch3.PARTY_ITEMS - 0x16 + ch3.RECORD) + k & 0xFFFF:04X}={b:02X}' for k, b in enumerate(rec))
    return {'endor_lawrence_hire': {'set': f'{party};201D=02;201F=02;201E=02;2021=01;2029=01'}}


def battle_patch(data, kind):
    """3장 사건 전투 몬스터(사건 모듈의 BATTLES)를 덮는 ROMPATCH(dq4chapterwalk.battle_patch)."""
    modules = ch3.modules() if hasattr(ch3, 'modules') else ()
    every = sorted({m for _, mod in modules for b in getattr(mod, 'BATTLES', ()) for m, _ in b['members']})
    return cwk.battle_patch(data, kind, every)


# 머리는 SEGMENTS 밖(head_segments)에서 걷는다. 출발 상태 맵이 롬에 따라 다르지 않아 표에는 사건 구간만 둔다
HEAD = 0

# 레이크나바 마을 FC 16/00 의 왼쪽 가장자리 도착 칸(dq4groupbuild LINKS arrival (00,0D) = 셀 (0,27))의 두 칸 오른쪽.
# 순간이동은 TO 의 한 셀 아래에 내린다
TOWN_WEST = f'{TOWN},4,26'
# 나가면 필드의 레이크나바 입구 블록(dq4groupbuild.doors: 셀 (208,72)~(209,73)) 아래 (208,75)에 선다
FIELD_OUT = (208, 75)
TOWN_ARRIVAL = (0, 27)
# 집 계단(FC 16/01 (21,07))으로 내려서는 마을 칸
HOUSE_OUT = (56, 55)

# 북쪽 동굴: 오른쪽·왼쪽 수문 앞 주인공 셀(dq4ch3safe.RIGHT·LEFT 의 사각형 왼쪽 아래). 순간이동은 두 셀 아래에 내려
# 위로 걸어 선다. 바닥 글은 세 쪽 뒤 「예」 에 커서
SAFE_RIGHT = (safe.RIGHT['rect'][0], safe.RIGHT['rect'][3])
SAFE_LEFT = (safe.LEFT['rect'][0], safe.LEFT['rect'][3])
SAFE_OFF = ['SAFE_ANSWERED', 'SAFE_YES']
SAFE_ASK = 'wait:30'
SAFE_FLOOR = 'a:8;wait:80;a:8;wait:80;a:8;wait:120'
SAFE_FACE_UP = '7E31E0=88'
# 명령 창 → しらべる(dq4chestcheck.SEARCH), 상자 메시지를 넘기고 창을 닫는다
SAFE_SEARCH = ('a:8;wait:60;down:6;wait:25;down:6;wait:25;down:6;wait:25;right:6;wait:25;a:8;wait:200;'
               'a:4;wait:150;a:4;wait:150;b:4;wait:220')

# 엔돌: 사람 바로 아래 셀(FC 칸 한 칸 아래). 순간이동은 TO 의 한 셀 아래에 내린다
KING_BELOW = endor.cell(endor.KING[2][0], endor.KING[2][1] + 1)
ENDOR_OFF = ['ENDOR_ALLOWED', 'ENDOR_SHOP', 'ENDOR_ORDER']
BUTTON_CELL = endor.BUTTON_LAND[1]
BENTO = 0xBB


def _set(flag):
    return f'{0x2190 + flag[0]:04X}|{flag[1]:02X}'


def _gold(n):
    return ';'.join(f'{(ch3.GOLD_AT & 0xFFFF) + k:04X}={n >> 8 * k & 0xFF:02X}' for k in range(3))


def _items(*items):
    """톨네코 물건 칸 2 부터(칸 0 옷, 칸 1 도시락)."""
    return ';'.join(f'{(ch3.PARTY_ITEMS & 0xFFFF) + 2 + k:04X}={item:02X}' for k, item in enumerate(items))


def _below(mp, fc):
    """FC 칸 fc 의 사람 바로 아래 셀에 내리는 순간이동 인자(TO 의 한 셀 아래에 내린다)."""
    x, y = endor.cell(fc[0], fc[1] + 1)
    return f'{mp},{x},{y - 1}'
LETTER2_SET = f'{0x2190 + endor.LETTER2[0]:04X}|{endor.LETTER2[1]:02X}'

# (이름, 방법, 인자, 선택). 꼴은 dq4ch2walkcheck.SEGMENTS 와 같다(선택은 dq4chapterwalk 머리말)
SEGMENTS = [
    # 첫머리 뒤 침대(시작 칸)에서 침대 아래로 내려서 방을 지나 문(FC (1F,07))을 열고 계단(FC (21,07))으로 마을에
    ('house', 'walk', '54,13;58,13;58,15;66,15',
     {'map': TOWN, 'changes': 1, 'after': 60, 'cell': HOUSE_OUT, 'want': ['CHAPTER3'], 'off': ['OPENING3']}),
    # 마을 왼쪽 가장자리로 나가 필드의 입구 아래 칸에 서고, 위로 걸어 다시 마을 도착 칸에
    ('town_side', 'warp', TOWN_WEST, {'map': TOWN}),
    ('town_out', 'walk', 'left:64', {'field': True, 'cell': FIELD_OUT, 'poke': wc.DAY}),
    # 필드에서는 7E:00BC·00BD 가 떠난 맵 그대로라 맵 바뀜으로 잡히지 않는다. 실내(field False)와 끝 셀로 본다
    ('town_in', 'walk', f'{FIELD_OUT[0]},{FIELD_OUT[1] - 2}', {'map': TOWN, 'field': False, 'cell': TOWN_ARRIVAL,
                                                                'poke': wc.DAY}),
    # 북쪽 동굴(dq4ch3safe). 수문 앞 칸에 서면 묻고, 「아니요」 면 그대로, 칸을 떠났다 다시 서서 「예」 면 물살에 계단으로
    ('safe_gates', 'warp', f'{safe.GATES},{SAFE_RIGHT[0]},{SAFE_RIGHT[1] + 2}', {'map': safe.GATES}),
    ('safe_no', 'walk', f'up:40;wait:200;{SAFE_ASK};down:4;wait:30;a:8;wait:200;{CLOSE}',
     {'map': safe.GATES, 'cell': SAFE_RIGHT, 'off': SAFE_OFF}),
    ('safe_right', 'walk', f'down:20;wait:60;up:30;wait:200;{SAFE_ASK};a:8;wait:60;a:8;wait:1300',
     {'map': safe.ENTRY, 'cell': safe.RIGHT['to'][1], 'off': SAFE_OFF, 'changes': 1, 'after': 60}),
    # 왼쪽 수문은 통로 끝 구덩이로 떨어뜨리고 물이 빠졌다는 flag 를 켠다
    ('safe_left_side', 'warp', f'{safe.GATES},{SAFE_LEFT[0]},{SAFE_LEFT[1] + 2}', {'map': safe.GATES}),
    ('safe_left', 'walk', f'up:40;wait:200;{SAFE_ASK};a:8;wait:60;a:8;wait:1300',
     {'map': safe.PIT, 'cell': safe.LEFT['to'][1], 'want': ['SAFE_DRAINED'], 'changes': 1, 'after': 60}),
    # 물이 빠진 뒤 입구 층의 계단(출구 번호 1)은 3E/04 대신 3E/05 의 같은 계단으로
    ('safe_dry_side', 'warp', f'{safe.ENTRY},6,34', {'map': safe.ENTRY}),
    ('safe_dry', 'walk', 'left:40;wait:300', {'map': safe.DRY, 'cell': (22, 29), 'want': ['SAFE_DRAINED']}),
    # 금고 상자 아래에서 위를 보고 しらべる → 철 금고. 상자 칸을 떠났다 밟으면 바닥 글, 「예」 면 되돌리고 상자가 닫힘
    ('safe_vault', 'warp', f'{safe.VAULT},8,8', {'map': safe.VAULT}),
    ('safe_open', 'walk', SAFE_SEARCH, {'poke': SAFE_FACE_UP, 'items': [safe.IRON_SAFE]}),
    ('safe_return', 'walk', f'8,9;wait:60;8,8;wait:300;{SAFE_FLOOR};a:8;wait:200;a:8;wait:200;{CLOSE}',
     {'map': safe.VAULT, 'cell': (8, 8), 'bytes': {'SAFE_SLOT': 0xFF}, 'off': SAFE_OFF}),
    ('safe_reopen', 'walk', f'8,9;wait:60;{SAFE_SEARCH}', {'poke': SAFE_FACE_UP, 'items': [safe.IRON_SAFE]}),
    # 레이크나바(dq4ch3lakanaba). 네네: 오늘 도시락 전이라 잠 → 아침(날수 + 1) → 오늘 도시락. 손님 갈래·톰을 교회까지
    # 미는 길은 dq4ch3lakanabacheck 가 롬 사본·톰 자리로 본다
    ('nene_house', 'warp', f'{ch3.HOUSE},54,6', {'map': ch3.HOUSE}),
    ('nene_sleep', 'walk', talk('down', 10), {'map': ch3.HOUSE, 'want': ['BENTO'], 'bytes': {'SCOTT_DAYS': 1}}),
    # 톰 노인: 「예」 뒤 밀리는 인물이 되고, 밀며 집 남쪽으로 걸어 나간다(막히면 끝 셀이 다름)
    ('tom_room', 'warp', f'{TOWN},48,24', {'map': TOWN}),
    ('tom_ask', 'walk', talk('up', 5), {'map': TOWN, 'want': ['TOM_PUSH']}),
    ('tom_push', 'walk', '50,25;50,21;48,21;48,25', {'map': TOWN, 'cell': (48, 25)}),
    # 무기점 첫 출근: 문 밖에 서면 꾸지람 뒤 카운터 안으로 걸려 들어간다
    ('shop_door', 'warp', f'{TOWN},20,52', {'map': TOWN}),
    # 꾸지람 뒤 주인이 비키고 주인공이 걷는 동안 누른 A 는 버려지므로 넉넉히 누른다
    ('shop_first', 'walk', f'16,53;{taps(12)};{CLOSE}',
     {'map': TOWN, 'cell': lakanaba.COUNTER_IN, 'want': ['SEEN', 'SHIFT'], 'maxf': 2400}),
    # 입구에서 금고까지 순간이동 없이: 입구 층 → 3E/04 위 → 오른쪽 통로 계단으로 입구 층 아래 → 3E/04 왼쪽 방 →
    # 왼쪽 수문 「예」 → 3E/06 → 3E/07 → 바위를 줄 13 오른쪽·열 0B 아래·줄 1E 왼쪽으로 이끌어 왼쪽 구덩이를 메움 →
    # 메운 구덩이를 건너 3E/09 → 금고 상자. 기다림은 바위가 멈출 자리에 닿을 때까지(헤드리스 실측 + 여유). 끝에 금고 방
    # 계단으로 돌아와 위로 걸으면 바위가 처음 자리로 돌아가 있어 3E/08 로 떨어짐
    ('safe_cave', 'warp', f'{safe.ENTRY},22,8', {'map': safe.ENTRY, 'set': f'{0x2190 + safe.DRAINED[0]:04X}=00'}),
    # 입구 층 FC (07~08,04)가 물이라 한 줄 위(03)로 돌아 (03,04) 계단에. (0B,03)은 필드로 나가는 계단이라 밟지 않음
    ('safe_cave_top', 'walk', '20,9;20,7;6,7;6,9;wait:200', {'map': safe.GATES, 'changes': 1, 'after': 60}),
    ('safe_cave_round', 'walk', '14,9;28,9;28,23;40,23;40,55;wait:200', {'map': safe.ENTRY, 'changes': 1, 'after': 60}),
    ('safe_cave_left', 'walk', '12,51;12,33;4,33;4,35;wait:200', {'map': safe.GATES, 'changes': 1, 'after': 60}),
    ('safe_cave_button', 'walk', f'16,31;16,29;wait:200;{SAFE_ASK};a:8;wait:60;a:8;wait:1300',
     {'map': safe.PIT, 'want': ['SAFE_DRAINED'], 'changes': 1, 'after': 60}),
    ('safe_cave_down', 'walk', '16,13;8,13;8,7;4,7;wait:200', {'map': safe.ROLL, 'changes': 1, 'after': 60}),
    ('safe_boulder', 'walk', '38,29;34,29;34,21;6,21;6,29;6,39;22,39;22,43;wait:800;22,61;16,61;wait:330;8,61;8,53;wait:260;'
     '8,39;12,39;wait:600', {'map': safe.ROLL, 'bytes': {'SAFE_FILL': 0x01}}),
    ('safe_cross', 'walk', '8,39;8,89;6,89;6,91;wait:200', {'map': safe.VAULT, 'changes': 1, 'after': 60}),
    ('safe_take', 'walk', f'20,39;8,39;8,9;wait:30;{SAFE_SEARCH}', {'map': safe.VAULT, 'items': [safe.IRON_SAFE]}),
    ('safe_fall_back', 'walk', '8,39;24,39;down:20;wait:300;8,73;wait:300',
     {'map': safe.PIT_BELOW, 'changes': 2, 'after': 60, 'bytes': {'SAFE_FILL': 0x00}}),
    # 바위를 가운데 구덩이로: 줄 1E 에서 주인공이 X ≥ 05 면 바위가 오른쪽으로, 열 0B 에서 아래로 굴러 가운데 구덩이를
    # 메움(그 길은 3E/08 아래 계단으로 이어짐)
    ('safe_boulder_mid_side', 'warp', f'{safe.ROLL},6,22', {'map': safe.ROLL}),
    ('safe_boulder_mid', 'walk', '6,29;8,29;8,61;16,61;wait:810;22,61;22,53;wait:270;22,39;8,39;8,43;wait:520;'
     '8,39;22,39;22,89;22,91;wait:200', {'map': safe.PIT_BELOW, 'changes': 1, 'after': 60, 'bytes': {'SAFE_FILL': 0x02}}),
    # 엔돌(dq4ch3endor), 이야기 차례로: 왕 첫 알현(flag 없음) → 허락 전의 가게 주인 → 왕의 편지 뒤 허락 → 금화가 모자람 →
    # 35001 골드로 가게를 삼(아침, 네네 옆으로) → 왕의 주문
    ('endor_king', 'warp', _below(endor.THRONE, endor.KING[2]), {'map': endor.THRONE}),
    ('endor_king_first', 'walk', talk('up', 6), {'map': endor.THRONE, 'off': ENDOR_OFF}),
    ('endor_seller', 'warp', _below(endor.SHOP_UP, endor.SELLER[0][2]), {'map': endor.SHOP_UP}),
    ('endor_seller_wish', 'walk', talk('up', 4), {'map': endor.SHOP_UP, 'off': ENDOR_OFF}),
    ('endor_king_letter', 'warp', _below(endor.THRONE, endor.KING[2]), {'map': endor.THRONE, 'set': LETTER2_SET}),
    ('endor_king_allow', 'walk', talk('up', 6), {'map': endor.THRONE, 'want': ['ENDOR_ALLOWED']}),
    ('endor_seller_allowed', 'warp', _below(endor.SHOP_UP, endor.SELLER[0][2]), {'map': endor.SHOP_UP}),
    ('endor_seller_poor', 'walk', talk('up', 6), {'map': endor.SHOP_UP, 'off': ['ENDOR_SHOP']}),
    ('endor_seller_buy', 'walk', talk('up', 14),
     {'set': _gold(endor.SHOP_PRICE + 1), 'map': endor.TOWN, 'cell': endor.NENE_SIDE[1], 'want': ['ENDOR_SHOP'],
      'bytes': {'GOLD0': 1, 'GOLD1': 0, 'GOLD2': 0}, 'changes': 1, 'after': 900}),
    ('endor_king_shop', 'warp', _below(endor.THRONE, endor.KING[2]), {'map': endor.THRONE}),
    ('endor_king_order', 'walk', talk('up', 6), {'map': endor.THRONE, 'want': ['ENDOR_ORDER']}),
    # 네네: 가게를 산 뒤 낮에는 「쉴래요?」 → 「예」 면 잠, 개통 소식이 왔으면 08A0 → 개통
    ('endor_nene', 'warp', f'{endor.TOWN},{endor.NENE_SIDE[1][0]},{endor.NENE_SIDE[1][1] - 1}', {'map': endor.TOWN}),
    ('endor_nene_sleep', 'walk', talk('right', 8), {'map': endor.TOWN, 'cell': endor.NENE_SIDE[1], 'changes': 1,
                                                     'after': 600, 'items': [BENTO]}),
    ('endor_nene_notice', 'walk', talk('right', 12), {'map': endor.TOWN, 'set': _set(endor.NOTICE),
                                                       'want': ['TUNNEL_OPENED']}),
    # 납품: 주문 전에는 안내만, 주문 뒤 없으면 그대로, 칼 둘·갑옷 하나를 받고, 다 차면 60000 골드
    ('endor_deliver', 'warp', _below(endor.CASTLE_HALL, endor.DELIVER[2]), {'map': endor.CASTLE_HALL}),
    ('endor_deliver_none', 'walk', talk('up', 8), {'map': endor.CASTLE_HALL, 'bytes': {'ENDOR_COUNT': 0}}),
    ('endor_deliver_some', 'walk', talk('up', 10),
     {'map': endor.CASTLE_HALL, 'set': _items(endor.STEEL_SWORD, endor.STEEL_SWORD, endor.IRON_ARMOR),
      'bytes': {'ENDOR_COUNT': 0x12}, 'items': [0x42, BENTO]}),
    ('endor_deliver_full', 'walk', talk('up', 10),
     {'map': endor.CASTLE_HALL,
      'set': ';'.join((_items(endor.STEEL_SWORD, endor.IRON_ARMOR), _gold(0), f'{FLAGS["ENDOR_COUNT"][0] & 0xFFFF:04X}=66')),
      'want': ['ENDOR_DELIVERED'], 'bytes': {'ENDOR_COUNT': 0x77, 'GOLD0': 0x60, 'GOLD1': 0xEA, 'GOLD2': 0}}),
    # 수집가: 여신상을 25000 골드에. 낮의 수집가는 걸어 다녀 밤에 서 있는 자리로 본다
    ('endor_collector', 'warp', _below(endor.COLLECTOR, endor.COLLECTORS[1][2]), {'map': endor.COLLECTOR,
                                                                                    'poke': wc.NIGHT}),
    ('endor_collector_sell', 'walk', talk('up', 4),
     {'map': endor.COLLECTOR, 'poke': wc.NIGHT, 'set': ';'.join((_items(endor.STATUE), _gold(0))), 'want': ['ENDOR_SOLD'],
      'bytes': {'GOLD0': 0xA8, 'GOLD1': 0x61, 'GOLD2': 0}, 'items': [0x42, BENTO]}),
    # 단추를 누른 뒤 입구 층의 계단은 48/03 대신 물이 빠진 48/04 로(누르기 전은 48/03)
    ('endor_cave_stair', 'warp', f'{endor.CAVE_ENTRY},22,8', {'map': endor.CAVE_ENTRY}),
    ('endor_cave_wet', 'walk', 'up:40;wait:300', {'map': endor.CAVE_WET, 'changes': 1, 'after': 60, 'off': ['ENDOR_BUTTON']}),
    ('endor_cave_stair2', 'warp', f'{endor.CAVE_ENTRY},22,8', {'map': endor.CAVE_ENTRY, 'set': _set(endor.BUTTON)}),
    ('endor_cave_dry', 'walk', 'up:40;wait:300', {'map': endor.CAVE_DRY, 'changes': 1, 'after': 60}),
    # 용병 로렌스(dq4mercenary): 600 골드로 고용하면 일행 기록 1 이 손님 로렌스(+0 = C0 | 29)
    ('endor_lawrence', 'warp', _below(endor.BARD_HALL, endor.LAWRENCE[0][2]), {'map': endor.BARD_HALL}),
    ('endor_lawrence_hire', 'walk', talk('up', 8),
     {'map': endor.BARD_HALL, 'set': ';'.join((_gold(600), f'{ch3.LAWRENCE_DAYS & 0xFFFF:04X}=03')), 'want': ['LAWRENCE'],
      'bytes': {'PARTY_N': 2, 'PARTY1': 0xE9, 'LAWRENCE_DAYS': 0, 'GOLD0': 0, 'GOLD1': 0}}),
    # 날수: 시간이 01FF 인 필드 걸음에 하루가 지나고(3 → 4), 날수 5 인 필드 걸음에 0379 뒤 일행에서 빠진다
    ('endor_day_side', 'warp', TOWN_WEST, {'map': TOWN, 'set': f'{ch3.LAWRENCE_DAYS & 0xFFFF:04X}=03'}),
    ('endor_day', 'walk', 'left:64;wait:60;down:16', {'field': True, 'cell': (FIELD_OUT[0], FIELD_OUT[1] + 2),
                                                       'set': '075E=FF;075F=01',
                                       'bytes': {'LAWRENCE_DAYS': 4, 'PARTY_N': 2}, 'want': ['LAWRENCE']}),
    ('endor_leave_side', 'warp', TOWN_WEST, {'map': TOWN, 'set': f'{ch3.LAWRENCE_DAYS & 0xFFFF:04X}=05'}),
    ('endor_leave', 'walk', f'left:64;wait:60;down:16;wait:60;{taps(6)};{CLOSE}', {'field': True, 'poke': wc.DAY, 'off': ['LAWRENCE'],
                                                           'bytes': {'PARTY_N': 1}}),
    # 여신상 방(48/07, FC 40/05)의 상자 아래에서 위를 보고 しらべる → 은의 여신상
    ('endor_statue', 'warp', f'{endor.STATUE_ROOM},12,10', {'map': endor.STATUE_ROOM}),
    ('endor_statue_open', 'walk', SAFE_SEARCH, {'poke': SAFE_FACE_UP, 'items': [endor.STATUE]}),
    # 여신상 동굴 단추: 「예」 면 물이 빠진 48/04 의 같은 칸으로
    ('endor_button_side', 'warp', f'{endor.CAVE_WET},{BUTTON_CELL[0]},{BUTTON_CELL[1] + 1}', {'map': endor.CAVE_WET}),
    ('endor_button', 'walk', f'up:40;wait:200;a:8;wait:60;a:8;wait:600',
     {'map': endor.CAVE_DRY, 'cell': endor.BUTTON_LAND[1], 'want': ['ENDOR_BUTTON'], 'changes': 1, 'after': 60}),
    # 여신상 동굴 배(dq4raft): 단추 앞(앞 구간이 켠 BUTTON 을 끔). 입구 층의 배 칸으로 걸어 들어가 타고 호수를 돌아
    # 아래 끝에서 48/05 의 물로 넘어간다
    ('raft_entry', 'warp', f'{endor.CAVE_ENTRY},22,8',
     {'map': endor.CAVE_ENTRY, 'set': f'{0x2190 + endor.BUTTON[0]:04X}&{~endor.BUTTON[1] & 0xFF:02X}', 'off': ['ENDOR_BUTTON']}),
    ('raft_board', 'walk', '24,9;24,11;44,11;wait:30', {'map': endor.CAVE_ENTRY, 'cell': (44, 11), 'want': ['RAFT_RIDING']}),
    ('raft_lake', 'walk', '62,11;62,31;50,31;left:20;wait:300',
     {'map': endor.CAVE_LOW_WET, 'changes': 1, 'after': 60, 'want': ['RAFT_RIDING']}),
    ('raft_low', 'walk', 'wait:200;6,63;6,55;8,55;22,55;22,39;26,39;26,35;64,35;64,53;68,53;68,63;wait:300',
     {'map': endor.CAVE_WET, 'changes': 1, 'after': 60, 'off': ['RAFT_RIDING'], 'bytes': {'RAFT_X': 3, 'RAFT_Y': 0x1B}}),
    ('raft_button', 'walk', 'wait:200;56,55;56,47;52,47;52,39;48,39;48,35;20,35;20,25;22,25;22,21;24,21;24,19;26,19;'
     '26,11;30,11;30,7;34,7;34,5;wait:200;a:8;wait:60;a:8;wait:600',
     {'map': endor.CAVE_DRY, 'cell': endor.BUTTON_LAND[1], 'want': ['ENDOR_BUTTON'], 'changes': 1, 'after': 60}),
    ('raft_dry', 'walk', 'wait:200;24,5;24,31;28,31;28,33;54,33;54,45;60,45;60,49;wait:300',
     {'map': endor.CAVE_LOW_DRY, 'changes': 1, 'after': 60}),
    ('raft_board2', 'walk', 'wait:200;60,57;60,55;58,55;wait:30', {'map': endor.CAVE_LOW_DRY, 'want': ['RAFT_RIDING']}),
    ('raft_island', 'walk', '58,53;64,53;64,47;60,47;60,43;56,43;56,39;52,39;52,35;30,35;30,17;30,15;28,15;28,13;wait:300',
     {'map': endor.STATUE_ROOM, 'changes': 1, 'after': 60, 'off': ['RAFT_RIDING']}),
    ('raft_statue', 'walk', f'wait:200;18,39;18,37;16,37;16,33;12,33;12,11;wait:30;{SAFE_SEARCH}',
     {'map': endor.STATUE_ROOM, 'items': [endor.STATUE]}),
]

# 본몰·여우 마을(dq4ch3bonmalmo). 물건은 톨네코 물건 칸 2 에 SET 으로 두고 말을 건다
BM_SLOT2 = '2058'
BM_FOX_OFF = ['BM_FOX_SCENE']
# 예·아니요 창에서 「아니요」 를 고르는 누름(창이 없을 때의 아래는 대사 창에 먹히지 않음)
BM_NO = 'wait:60;down:8;wait:40;a:8;wait:60'
# 톨네코 물건 칸 2~11 을 こんぼう(02)로 채운다(칸 0 옷, 칸 1 도시락)
# 낮 왕자(3F/01 낮 목록 첫 사람, 인물 칸 4)는 오가는 사람이라 이동 간격(7E:3300 + 2 × 칸)을 0 으로 붙든다. 붙들지 않으면
# snes9x 에서 왕자가 비켜 말이 걸리지 않았다
BM_PRINCE_HOLD = wc.DAY + ';7E3308=00'
# 여우 마을 필드 입구 블록(FC (7C,34))의 왼쪽 위 칸
BM_FOX_GATE = (0x7C * 2, 0x34 * 2)
BM_FULL = ';'.join(f'{0x2058 + k:04X}=02' for k in range(10))
# 본몰 성 출구 줄(dq4groupbuild LINKS 3F arrival (11,1F) 위 칸)과 나가면 서는 필드 칸, 다리(FC (6F,4F)) 서쪽·동쪽 칸
BM_GATE = (0x11 * 2, 0x1E * 2 + 1)
BM_FIELD_GATE = (0x74 * 2, 0x47 * 2)
BM_WEST = (0x6E * 2, 0x4F * 2)
BM_EAST = (0x71 * 2, 0x4F * 2)
SEGMENTS += [
    # 감옥: 창살 너머 아들에게 오른쪽을 보고 말을 걸어 키메라의 날개를 준다. 「아니요」 면 0841 뒤 다시 묻고(두 번),
    # 「예」 면 날개가 빠지고 아들이 사라진다
    ('bm_prison_no', 'warp', f'{bm.PRISON},{bm.SON[0] - 4},{bm.SON[1] - 1}',
     {'map': bm.PRISON, 'set': f'{BM_SLOT2}={bm.WINGS:02X}', 'poke': wc.DAY}),
    ('bm_son_no', 'walk', f'right:8;wait:30;a:8;wait:60;a:8;wait:60;{";".join([BM_NO] * 5)};{taps(8)};{CLOSE}',
     {'want': ['BM_SON_FREED'], 'bytes': {'BM_SLOT2': 0xFF}, 'poke': wc.DAY}),
    # 여우 마을 촌장: 개가 없으면 「예」·「예」 로 묵고 숲에서 아침에 깬다
    ('bm_inn_town', 'warp', f'{bm.FOX_TOWN},{bm.CHIEF[0] - 2},{bm.CHIEF[1] - 1}', {'map': bm.FOX_TOWN, 'poke': wc.NIGHT}),
    ('bm_inn', 'walk', f'{talk("right", 8)};wait:600', {'map': bm.FOREST, 'cell': bm.FOREST_WAKE, 'off': ['BM_FOXED']}),
    # 왕자: 낮에 처음 말을 걸면 유모가 꾸짖고 일행은 그 자리. 밤에는 무기점 뒤에서 왕자의 편지를 준다
    ('bm_prince_side', 'warp', f'{bm.CASTLE},{bm.PRINCE["day"][0] + 2},{bm.PRINCE["day"][1] - 1}',
     {'map': bm.CASTLE, 'poke': BM_PRINCE_HOLD}),
    ('bm_prince', 'walk', f'{talk("left", 10)};wait:300',
     {'map': bm.CASTLE, 'cell': (bm.PRINCE['day'][0] + 2, bm.PRINCE['day'][1]), 'want': ['BM_PRINCE_MET'],
      'poke': BM_PRINCE_HOLD}),
    ('bm_prince_night_side', 'warp', f'{bm.CASTLE},{bm.PRINCE["night"][0]},{bm.PRINCE["night"][1] + 1}',
     {'map': bm.CASTLE, 'poke': wc.NIGHT}),
    ('bm_prince_night', 'walk', talk('up', 12), {'items': [bm.PRINCE_LETTER], 'poke': wc.NIGHT}),
    # 소지품이 가득이면(열 칸을 채움) 036A 만, 편지는 소지품에도 맡긴 물건에도 들지 않는다
    ('bm_prince_full_side', 'warp', f'{bm.CASTLE},{bm.PRINCE["night"][0]},{bm.PRINCE["night"][1] + 1}',
     {'map': bm.CASTLE, 'set': BM_FULL, 'poke': wc.NIGHT}),
    ('bm_prince_full', 'walk', talk('up', 8), {'bytes': {'BM_SLOT2': 0x02, 'BM_BAG_LETTER': 0}, 'poke': wc.NIGHT}),
    # 개가 따라오면 촌장이 놀라 숲으로 바뀌고, 여우가 빌어 「예」 면 강철 갑옷, 돈 가아데가 떠나 FOXED
    ('bm_fox_town', 'warp', f'{bm.FOX_TOWN},{bm.CHIEF[0] - 2},{bm.CHIEF[1] - 1}',
     {'map': bm.FOX_TOWN, 'set': '21FF|02', 'poke': wc.DAY}),
    # 여우가 처음 빌 때 「아니요」(084E) 면 다시 빌고, 「예」 에 갑옷
    ('bm_fox', 'walk', f'{talk("right", 2)};wait:200;{";".join([BM_NO] * 3)};{taps(16, 80)};wait:600;{CLOSE}',
     {'map': bm.FOREST, 'want': ['BM_FOXED'], 'off': BM_FOX_OFF, 'items': [bm.STEEL_ARMOR], 'maxf': 6000,
      'poke': wc.DAY}),
    # 여우를 쫓은 뒤: 숲 어귀에서 필드로 나가 위의 입구로 들면 마을 대신 숲 어귀에 선다
    ('bm_forest_side', 'warp', f'{bm.FOREST},{bm.FOREST_ENTRY[0] + 2},{bm.FOREST_ENTRY[1] - 1}',
     {'map': bm.FOREST, 'poke': wc.DAY}),
    ('bm_forest_out', 'walk', 'left:80', {'field': True, 'poke': wc.DAY}),
    # 입구 블록 칸까지 걷는다(누름 길이로 걸으면 snes9x 에서 입구에 못 닿았다). 48/00 을 거쳐 숲 어귀 (0,31)에 내린 뒤에도
    # 걷기가 그 칸 쪽(오른쪽)으로 이어 걸어 나무에 막힌 (4,31)에서 멈춘다. 그 줄은 숲 어귀로만 닿는다
    ('bm_forest_in', 'walk', f'{BM_FOX_GATE[0]},{BM_FOX_GATE[1]}',
     {'map': bm.FOREST, 'cell': (bm.FOREST_ENTRY[0] + 4, bm.FOREST_ENTRY[1]), 'changes': 2, 'after': 300,
      'poke': wc.DAY}),
    # 다리: 고치기 전에는 본몰에서 나가 다리 서쪽 칸(FC (6E,4F))에서 동쪽으로 걸어도 그 자리
    ('bm_castle_gate', 'warp', f'{bm.CASTLE},{BM_GATE[0]},{BM_GATE[1] - 1}', {'map': bm.CASTLE, 'poke': wc.DAY}),
    ('bm_castle_out', 'walk', 'down:64', {'field': True, 'poke': wc.DAY}),
    ('bm_bridge_shut', 'walk', f'{BM_WEST[0]},{BM_FIELD_GATE[1]};{BM_WEST[0]},{BM_WEST[1]};right:60;wait:30',
     {'field': True, 'cell': BM_WEST, 'off': ['BM_BRIDGE'], 'poke': wc.DAY}),
    # 여우를 쫓은 뒤 왕에게 말을 걸면 다리가 고쳐진다
    ('bm_king', 'warp', f'{bm.CASTLE},{bm.KING[0]},{bm.KING[1] + 1}', {'map': bm.CASTLE, 'poke': wc.DAY}),
    ('bm_bridge', 'walk', talk('up', 6), {'want': ['BM_BRIDGE'], 'poke': wc.DAY}),
    # 고친 뒤에는 같은 길로 다리를 건너 동쪽 섬(FC (71,4F))에 선다
    ('bm_castle_gate2', 'warp', f'{bm.CASTLE},{BM_GATE[0]},{BM_GATE[1] - 1}', {'map': bm.CASTLE, 'poke': wc.DAY}),
    ('bm_castle_out2', 'walk', 'down:64', {'field': True, 'poke': wc.DAY}),
    ('bm_bridge_open', 'walk', f'{BM_WEST[0]},{BM_FIELD_GATE[1]};{BM_WEST[0]},{BM_WEST[1]};{BM_EAST[0]},{BM_EAST[1]}',
     {'field': True, 'cell': BM_EAST, 'poke': wc.DAY}),
    # 편지: 왕자의 편지를 가진 채 모니카에게 말을 걸면 왕의 편지로 바뀌고, 그것을 가진 채 본몰 왕에게
    ('bm_monica_side', 'warp', f'{bm.ENDOR_THRONE},{bm.MONICA[0]},{bm.MONICA[1] + 1}',
     {'map': bm.ENDOR_THRONE, 'set': f'{BM_SLOT2}={bm.PRINCE_LETTER:02X}', 'poke': wc.DAY}),
    ('bm_monica', 'walk', talk('up', 24), {'want': ['BM_LETTER1'], 'bytes': {'BM_SLOT2': bm.KING_LETTER},
                                           'poke': wc.DAY}),
    ('bm_king_side', 'warp', f'{bm.CASTLE},{bm.KING[0]},{bm.KING[1] + 1}',
     {'map': bm.CASTLE, 'set': f'{BM_SLOT2}={bm.KING_LETTER:02X}', 'poke': wc.DAY}),
    ('bm_king_letter', 'walk', talk('up', 12), {'want': ['BM_LETTER2'], 'bytes': {'BM_SLOT2': 0xFF}, 'poke': wc.DAY}),
]

# 굴(dq4ch3tunnel). 47/00 노인 아래 칸에서 위를 보고 말을 건다. 쪽마다 A 하나(글이 다 찍히도록 90프레임 간격), 마지막
# A 하나가 연 명령 창은 닫는다. 「예」 는 커서 그대로 A
TUNNEL_BELOW_OLD = tunnel.cell(tunnel.OLD_MAN[0], tunnel.OLD_MAN[1] + 1)
TUNNEL_ARRIVAL = tunnel.cell(0x05, 0x0B)


def tunnel_talk(presses):
    return f'up:8;wait:30;a:8;wait:60;a:8;wait:90;{taps(presses + 1, 90)};wait:60;{CLOSE}'


# 노인 아래 칸 ↔ 47/00 계단: FC (11,0B) → 줄 08 → (05,08) → 계단 (05,0B). 계단은 웨이포인트 대신 아래 누르기로
# 밟는다(필드에 나온 뒤에도 웨이포인트 셀로 걸어가 버림)
TUNNEL_TO_STAIRS = '34,23;34,17;10,17;10,21;down:16;wait:60'
TUNNEL_TO_OLD = '10,21;10,17;34,17;34,23;36,23'
# 47/00 을 나서면 서는 필드 칸(dq4groupbuild 의 입구 블록 아래)과 그 위 입구
TUNNEL_FIELD = (0xF2, 0xBD)
TUNNEL_GOLD = lambda v: f'2019={v & 0xFF:02X};201A={v >> 8 & 0xFF:02X};201B={v >> 16:02X}'  # noqa: E731
# 47/01 동쪽 통로(FC 줄 04)에서 계단 앞 (1E,02)로 가 오른쪽 계단 (1F,02)을 밟는다
TUNNEL_EAST = f'{tunnel.OPEN_MAP},50,8'
TUNNEL_TO_END = f'60,9;60,5;right:16'
SEGMENTS += [
    # 금화가 모자라면 「예」 를 해도 그대로(0895)
    ('tunnel_short_side', 'warp', f'{tunnel.BLOCKED},{TUNNEL_BELOW_OLD[0]},{TUNNEL_BELOW_OLD[1] - 1}',
     {'map': tunnel.BLOCKED, 'set': TUNNEL_GOLD(10000)}),
    ('tunnel_short', 'walk', tunnel_talk(5),
     {'map': tunnel.BLOCKED, 'off': ['TUNNEL_PAID', 'TUNNEL_WAITING'],
      'bytes': {'TUNNEL_GOLD0': 0x10, 'TUNNEL_GOLD1': 0x27, 'TUNNEL_GOLD2': 0}}),
    # 가게를 사기 전이면 「예」 뒤 0894(엔돌 모듈 SHOP 을 끔)
    ('tunnel_noshop_side', 'warp', f'{tunnel.BLOCKED},{TUNNEL_BELOW_OLD[0]},{TUNNEL_BELOW_OLD[1] - 1}',
     {'map': tunnel.BLOCKED, 'set': f'{TUNNEL_GOLD(65000)};{0x2190 + endor.SHOP[0]:04X}=00'}),
    ('tunnel_noshop', 'walk', tunnel_talk(5),
     {'map': tunnel.BLOCKED, 'off': ['TUNNEL_PAID', 'TUNNEL_WAITING'],
      'bytes': {'TUNNEL_GOLD0': 0xE8, 'TUNNEL_GOLD1': 0xFD, 'TUNNEL_GOLD2': 0}}),
    # 60000 을 내고(0896·0897), 다시 말을 걸면 0897. 필드에 나갔다 들어오면 WAITING 이 꺼지고, 말을 걸면 공사 재개(0898)
    # 앞의 엔돌 구간(endor_nene_notice)이 켠 OPENED 를 끄고 시작한다
    ('tunnel_pay_side', 'warp', f'{tunnel.BLOCKED},{TUNNEL_BELOW_OLD[0]},{TUNNEL_BELOW_OLD[1] - 1}',
     {'map': tunnel.BLOCKED, 'set': f'{TUNNEL_GOLD(65000)};{0x2190 + tunnel.IDX:04X}=00'}),
    ('tunnel_pay', 'walk', tunnel_talk(6),
     {'map': tunnel.BLOCKED, 'want': ['TUNNEL_PAID', 'TUNNEL_WAITING'],
      'bytes': {'TUNNEL_GOLD0': 0x88, 'TUNNEL_GOLD1': 0x13, 'TUNNEL_GOLD2': 0}}),
    ('tunnel_wait', 'walk', tunnel_talk(1), {'map': tunnel.BLOCKED, 'want': ['TUNNEL_WAITING'], 'off': ['TUNNEL_RESUMED']}),
    ('tunnel_out', 'walk', TUNNEL_TO_STAIRS, {'field': True, 'cell': TUNNEL_FIELD, 'poke': wc.DAY}),
    ('tunnel_in', 'walk', f'{TUNNEL_FIELD[0]},{TUNNEL_FIELD[1] - 2};wait:60',
     {'map': tunnel.BLOCKED, 'field': False, 'cell': TUNNEL_ARRIVAL, 'poke': wc.DAY, 'off': ['TUNNEL_WAITING']}),
    ('tunnel_resume', 'walk', f'{TUNNEL_TO_OLD};{tunnel_talk(2)}', {'map': tunnel.BLOCKED, 'want': ['TUNNEL_RESUMED']}),
    # 공사 재개만으로는 뚫리지 않는다(엔돌 네네의 알림 전): 나갔다 들어와도 47/00
    ('tunnel_closed_out', 'walk', TUNNEL_TO_STAIRS, {'field': True, 'cell': TUNNEL_FIELD, 'poke': wc.DAY}),
    ('tunnel_closed_in', 'walk', f'{TUNNEL_FIELD[0]},{TUNNEL_FIELD[1] - 2};wait:60',
     {'map': tunnel.BLOCKED, 'field': False, 'cell': TUNNEL_ARRIVAL, 'poke': wc.DAY, 'off': ['TUNNEL_OPENED']}),
    # 엔돌 네네의 개통 알림(dq4ch3tunnel.news_talk, OPENED) 뒤 엔돌 쪽 입구는 뚫린 47/01 의 (05,0F) 계단으로. 알림부터
    # 걷는 길은 seam_* 묶음이 보고, 여기서는 set 으로 둔다
    ('tunnel_open_side', 'warp', f'{tunnel.BLOCKED},{TUNNEL_ARRIVAL[0]},{TUNNEL_ARRIVAL[1] - 3}',
     {'map': tunnel.BLOCKED, 'set': f'{0x2190 + tunnel.OPENED[0]:04X}|{tunnel.OPENED[1]:02X}'}),
    ('tunnel_open_out', 'walk', 'down:16;wait:60', {'field': True, 'cell': TUNNEL_FIELD, 'poke': wc.DAY}),
    ('tunnel_open_in', 'walk', f'{TUNNEL_FIELD[0]},{TUNNEL_FIELD[1] - 2};wait:60',
     {'map': tunnel.OPEN_MAP, 'field': False, 'cell': tunnel.OPEN_ARRIVAL, 'poke': wc.DAY, 'want': ['TUNNEL_OPENED']}),
    # 동쪽 계단을 밟으면 장 끝 서술 → 엔딩 곡 → 「제4장 … 다음에 계속」 상자 → 버튼으로 타이틀
    ('tunnel_end_side', 'warp', TUNNEL_EAST, {'map': tunnel.OPEN_MAP}),
    ('tunnel_end_walk', 'walk', f'{TUNNEL_TO_END};wait:20', {'map': tunnel.OPEN_MAP}),
    ('tunnel_end', 'ending', tunnel.END_SCENE, {}),
    # 서술을 넘기면 엔딩 곡(14)이 지금 곡이 된 뒤 끝 상자가 버튼을 기다린다. 장 끝 구간과 묶음을 나누는 까닭은 2장 끝
    # song_in 과 같다(남은 A 가 리셋 뒤 타이틀에서 눌림)
    ('tunnel_song_side', 'warp', TUNNEL_EAST, {'map': tunnel.OPEN_MAP}),
    ('tunnel_song', 'walk', f'{TUNNEL_TO_END};wait:60;{taps(3, 120)};wait:400',
     {'map': tunnel.OPEN_MAP, 'bytes': {'SONG': tunnel.ENDING_SONG}}),
    # 계단 앞 칸에 서기만 해서는 걸리지 않고(다시 걸어 나옴), 아래 칸 (1F,03) 에서 위로 누르면 걸린다
    ('tunnel_near_side', 'warp', TUNNEL_EAST, {'map': tunnel.OPEN_MAP}),
    ('tunnel_near', 'walk', '60,9;60,5;wait:200;60,9', {'map': tunnel.OPEN_MAP, 'cell': (60, 9)}),
    ('tunnel_below', 'walk', f'62,9;62,7;up:16;wait:60;{taps(3, 120)};wait:400',
     {'map': tunnel.OPEN_MAP, 'bytes': {'SONG': tunnel.ENDING_SONG}}),
]

# 굴과 엔돌을 잇는 길(둘 다 머지된 뒤 나중 PR 이 붙임): 노인에게 60000G(tunnel_pay 묶음) → 필드 → 0898 → 공사 재개 뒤 엔돌
# 40/01 에 들면 소식(NOTICE) → 네네 「예」 → OPENED → 엔돌 쪽 입구가 뚫린 굴로 → 굴을 지나 동쪽 계단 → 장 끝. 소식·개통
# flag 는 set 으로 켜지 않는다(묶음 사이로는 앞 구간 want 만 이어짐). 가게를 산 것(SHOP)만 네네가 서도록 둔다
SEAM_NOTICE_CELL = (24, 14)                 # 40/01(FC 04/01) 의 바닥 FC (12,07) 위 셀(한 셀 아래에 내림)
# 47/01 도착 계단 (10,31) → 이주민이 지나가게 (6,31) 로 비켰다가 계단을 밟지 않게 열 03 으로 → (03,0C) → (0A,0C) → (0A,06) →
# (12,06) → (12,04) → (1E,04) → 계단 앞 (1E,02)
SEAM_THROUGH = '6,31;wait:1200;6,25;20,25;20,13;36,13;36,9;60,9;60,5'
SEAM = [
    ('seam_notice_side', 'warp', f'{tunnel.NOTICE_MAP},{SEAM_NOTICE_CELL[0]},{SEAM_NOTICE_CELL[1]}',
     {'map': tunnel.NOTICE_MAP}),
    ('seam_notice', 'walk', 'wait:60', {'map': tunnel.NOTICE_MAP, 'want': ['ENDOR_NOTICE'], 'off': ['TUNNEL_OPENED']}),
    ('seam_nene_side', 'warp', f'{endor.TOWN},{endor.NENE_SIDE[1][0]},{endor.NENE_SIDE[1][1] - 1}',
     {'map': endor.TOWN, 'set': _set(endor.SHOP)}),
    ('seam_nene', 'walk', talk('right', 12), {'map': endor.TOWN, 'want': ['TUNNEL_OPENED']}),
    ('seam_tunnel_side', 'warp', f'{tunnel.BLOCKED},{TUNNEL_ARRIVAL[0]},{TUNNEL_ARRIVAL[1] - 3}', {'map': tunnel.BLOCKED}),
    ('seam_out', 'walk', 'down:16;wait:60', {'field': True, 'cell': TUNNEL_FIELD, 'poke': wc.DAY}),
    ('seam_in', 'walk', f'{TUNNEL_FIELD[0]},{TUNNEL_FIELD[1] - 2};wait:60',
     {'map': tunnel.OPEN_MAP, 'field': False, 'cell': tunnel.OPEN_ARRIVAL, 'poke': wc.DAY}),
    ('seam_through', 'walk', f'{SEAM_THROUGH};right:16;wait:60;{taps(3, 120)};wait:400',
     {'map': tunnel.OPEN_MAP, 'maxf': 9000, 'bytes': {'SONG': tunnel.ENDING_SONG}}),
]
# 공사 재개(tunnel_resume)·「재개만으로는 막힘」(tunnel_closed_in, OPENED 꺼짐) 뒤, OPENED 를 set 하는 tunnel_open 묶음 앞에
_at = next(k for k, seg in enumerate(SEGMENTS) if seg[0] == 'tunnel_closed_in') + 1
SEGMENTS[_at:_at] = SEAM


def units(segments=None):
    return cwk.units(SEGMENTS if segments is None else segments, HEAD)


def setup(first, segments=None, data=None):
    return cwk.setup(SEGMENTS if segments is None else segments, HEAD, first, FLAGS,
                     effects(data) if data is not None else {})


def walk_unit(mesence, rom, data, out, unit, base, seed=0, segments=None):
    """한 묶음을 3장 출발 상태에서 걷는다."""
    return cwk.walk_unit(mesence, rom, data, out, unit, base, seed, SEGMENTS if segments is None else segments, HEAD,
                         FLAGS, effects, HOPS, battle_patch)


@functools.cache
def head_segments():
    """머리 구간 표: 2장 검사 표를 빈 성 계단까지 쓰고 3장 첫머리(ch3_open)를 더한 것(dq4ch3opencheck.segments 의
    ch3_open 까지)과 그 가운데 걷는 묶음(빈 성 왕좌의 방부터)."""
    import dq4growth
    segs = opening.segments(ch3.start(HERE.parents[2] / 'rom' / 'dq5.sfc', dq4growth.DQ4))
    names = [s[0] for s in segs]
    segs = segs[:names.index('ch3_open') + 1]
    return segs, list(range(names.index(opening.FIRST), len(segs)))


def head_key(mesence, data):
    """3장 출발 상태를 정하는 것: 2장 출발 상태의 키에 머리를 걷는 코드·머리 구간 표·그 묶음의 시작 flag 를 더한다.
    사건 구간(SEGMENTS)은 넣지 않아 구간을 붙여도 머리를 다시 걷지 않는다."""
    segs, unit = head_segments()
    return wc.fingerprint(cw.head_key(mesence), inspect.getsource(head), Path(cwk.__file__),
                          repr([segs[i] for i in unit]), repr(cw.setup(unit[0], segs, data)), repr(sorted(FLAGS.items())))


def head(mesence, rom, data, out, cache=None, repeat=1):
    """3장 출발 상태와 머리 결과(2장 머리 결과 + 3장 머리 묶음 결과). 머리는 시드 0 으로 걷는다."""
    segs, unit = head_segments()
    key = head_key(mesence, data) if cache else None
    state = out / 'head' / segs[-1][0] / 'end.mss'
    hit = cache.get('ch3-start', key, '.mss', state) if cache else None
    if hit:
        return state, [{**r, 'cached': cache.path('ch3-start', key, '.mss').name} for r in hit[1]['segments']]
    base, results = cw.head(mesence, rom, data, out, cache)
    if base is None:
        return None, results
    runs = []
    for n in range(1, repeat + 1):
        dest = out / ('head' if n == 1 else f'head-{n}')
        rs = cw.walk_unit(mesence, rom, data, dest, unit, base, 0, segments=segs)
        runs.append(rs)
        if len(rs) != len(unit) or any(r['status'] != 'passed' for r in rs):
            return None, results + rs
    if repeat > 1:
        bad = cwk.compare_runs(*runs)
        if bad:
            return None, results + [{**r, 'status': 'failed', 'problems': r['problems'] + [bad[r['name']]]}
                                    if r['name'] in bad else r for r in runs[0]]
    results = results + runs[0]
    # 한 번만 걸은 머리는 결정적인지 모르므로 캐시에 넣지 않는다(가드는 --repeat 2)
    if cache and repeat > 1:
        cache.put('ch3-start', key, '.mss', state, {'segments': results})
    return state, results


def main():
    return cwk.main(sys.modules[__name__], __doc__, 'dq4build.py --chapter3 의 롬',
                    '같은 롬으로 만든 3장 출발 상태(head/ch3_open/end.mss). 주면 머리를 건너뜀')


if __name__ == '__main__':
    sys.exit(main())
