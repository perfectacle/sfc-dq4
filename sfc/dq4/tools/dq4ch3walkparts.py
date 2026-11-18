"""3장 걷기·주인공 막기 표(dq4ch3*_checks.py)가 함께 쓰는 자리와 입력 조각."""
import dq4ch1walkcheck as wc
import dq4ch3event as ch3

talk, taps, talk_yes = wc.talk, wc.taps, wc.talk_yes
CLOSE = wc.pc.CLOSE

TOWN = '3E/00'                 # FC 16/00 레이크나바
# 레이크나바 마을 FC 16/00 의 왼쪽 가장자리 도착 칸(dq4groupbuild LINKS arrival (00,0D) = 셀 (0,27))의 두 칸 오른쪽.
# 순간이동은 TO 의 한 셀 아래에 내린다
TOWN_WEST = f'{TOWN},4,26'
# 나가면 필드의 레이크나바 입구 블록(dq4groupbuild.doors: 셀 (208,72)~(209,73)) 아래 (208,75)에 선다
FIELD_OUT = (208, 75)
TOWN_ARRIVAL = (0, 27)
# 집 계단(FC 16/01 (21,07))으로 내려서는 마을 칸
HOUSE_OUT = (56, 55)
# 출발 상태(톨네코 집 3E/01)와 같은 맵으로 가는 주인공 막기 사례가 먼저 들르는 곳
HOP = TOWN_WEST

# 명령 창 → しらべる(dq4chestcheck.SEARCH), 상자 메시지를 넘기고 창을 닫는다
SEARCH = ('a:8;wait:60;down:6;wait:25;down:6;wait:25;down:6;wait:25;right:6;wait:25;a:8;wait:200;'
          'a:4;wait:150;a:4;wait:150;b:4;wait:220')
# 상자 아래에서 위를 본다
FACE_UP = '7E31E0=88'
BENTO = 0xBB


def set_flag(flag):
    """(7E:2190 + i, 마스크) flag 를 켜는 SET 조각."""
    return f'{0x2190 + flag[0]:04X}|{flag[1]:02X}'


def gold(n):
    return ';'.join(f'{(ch3.GOLD_AT & 0xFFFF) + k:04X}={n >> 8 * k & 0xFF:02X}' for k in range(3))


def items(*things):
    """톨네코 물건 칸 2 부터(칸 0 옷, 칸 1 도시락)."""
    return ';'.join(f'{(ch3.PARTY_ITEMS & 0xFFFF) + 2 + k:04X}={item:02X}' for k, item in enumerate(things))
