"""2장 사건을 구간마다 따로 걷는 검사(MesenCE 헤드리스). 1장 걷기 검사(dq4ch1walkcheck.py)의 걷기·순간이동·판정을
그대로 쓰고, 구간 표와 flag 표만 2장 것이다.

  머리  서장 끝 상태(dq4ch1walkcheck.prologue, 롬 SHA-1 별 캐시)에서 1장 왕 보고 앞까지의 flag 를 두고 1장 끝을 걸어
        2장 왕좌의 방 첫머리를 넘긴다. 이 끝 상태가 「2장 출발 상태」이고, 같은 캐시 폴더에 둔다(ch2-opening-<지문>.mss).
  묶음  나머지 구간은 순간이동 구간마다 묶음 하나다. 묶음마다 2장 출발 상태에서 따로 시작해 함께 돈다(--jobs).
        묶음 첫 구간에는 앞 구간들이 켰을 flag(want·off)와 기록에 남기는 것(effects)을 SET·PARTY 로 둔다.

난수·시각·조우는 1장 검사와 같이 묶는다: 구간 시작과 순간이동 도착에 난수(--seed)·시각(낮 50, 밤 구간은 F0)을 두고,
조우 판정을 덮어 걸음 전투를 없앤다. --repeat 2 는 묶음마다 두 번 걸어 구간 기록(walk.txt·warp.txt)의 SHA-1 이 같은지
본다. 같지 않으면 실패다(운으로 통과하지 않는다는 근거).

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4ch2walkcheck.py --rom work/ch2/dq4-ch1-full.sfc --out work/ch2walk
  (--only 구간,… 은 그 구간으로 시작하는 묶음만, --base 는 2장 출발 상태를 다시 쓴다)

롬은 dq4build.py --chapter2 의 출력이어야 한다(1장 끝에서 2장으로 넘어감). 구간을 붙이는 법은
sfc/dq4/docs/dq4-chapter2-format.md 「검사에 구간 붙이기」.
"""
import argparse
import concurrent.futures
import inspect
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch2endor as endor  # noqa: E402
import dq4ch2tempe as tempe  # noqa: E402
import dq4ch2frenol as frenol  # noqa: E402
import dq4ch2king as king  # noqa: E402

talk, taps = wc.talk, wc.taps
CLOSE = wc.pc.CLOSE


def flag(pair):
    return wc.flag(pair)


# 1장 flag(머리 구간이 보는 REPORTED·CHAPTER2·OPENING 등)에 2장 flag 를 더한다. 새 사건 flag 는 여기에 한 줄씩
FLAGS = {
    **wc.FLAGS,
    'TALKED_GATE': flag(ch2.TALKED_GATE),
    'TALKED_BREY': flag(ch2.TALKED_BREY),
    'TALKED_KIRYL': flag(ch2.TALKED_KIRYL),
    'READY': flag(ch2.READY),
    'KICKED': flag(ch2.KICKED),
    'JOINED': flag(ch2.JOINED),
    'TEMPE_HEARD': flag(ch2.TEMPE_HEARD),
    'TEMPE_GONE': flag(ch2.TEMPE_GONE),
    'TEMPE_ALTAR': flag(ch2.TEMPE_ALTAR),
    'TEMPE_WON': flag(tempe.WON),
    'ENDOR_IN': flag(endor.IN),
    'ENDOR_LOST': flag(endor.LOST),
    'ENDOR_CHAMPION': flag(endor.CHAMPION),
    'ENDOR_MESSENGER': flag(endor.MESSENGER),
    # 선택 bytes 로 값을 견주는 칸(want·off 에 넣지 않는다: 뒤 묶음 첫머리에 OR 로 놓이므로). 대회에서 이긴 수, 일행 수,
    # 일행 순서 셋, 아리나의 장비 비트·물건 첫 두 칸
    'ENDOR_STAGE': flag(endor.STAGE),
    'PARTY_COUNT': (endor.COUNTS[0], 0xFF),
    **{f'ORDER{k}': (endor.ORDERS[0] + k, 0xFF) for k in range(3)},
    'ALENA_EQUIP': (endor.ALENA_EQUIP, 0xFF),
    **{f'ALENA_ITEM{k}': (endor.ALENA_ITEMS + k, 0xFF) for k in range(2)},
    'FRENOL_KIDNAPPED': flag(frenol.KIDNAPPED),
    'FRENOL_LEFT': flag(frenol.LEFT),
    'FRENOL_RESCUED': flag(frenol.RESCUED),
    # 묘지 장면 동안만 켜는 flag 다섯(끝에 모두 꺼짐)
    'FRENOL_SCENE': (0x7E2190 + frenol.IDX, frenol.SCENE_BITS),
    'BRACELET_CHEST': (0x7E0000 | frenol.CHEST_OPEN[0], frenol.CHEST_OPEN[1]),
    'KING_BAZAAR': flag(king.BAZAAR),
    'KING_HEARD': flag(king.HEARD),
    'KING_SEEN': flag(king.SEEN),
    'KING_GOT': flag(king.GOT),
    'KING_CURED': flag(king.CURED),
    # flag 가 아니라 바이트 전체(마스크 FF)를 본다: 1장에 맡긴 やくそう 개수와 맡긴 금화(1000G 단위) 아래 바이트
    'BANK_HERB': (ch2.BANK_ITEMS_AT + 0xA1, 0xFF),
    'BANK_GOLD': (ch2.BANK_GOLD_AT, 0xFF),
}

# 1장 왕 보고 앞에 맡긴 것: やくそう 3 개와 금화 2000. FC 장 초기화처럼 2장 첫머리에는 둘 다 0 이어야 한다
CH1_BANK = f'{(ch2.BANK_ITEMS_AT + 0xA1) & 0xFFFF:04X}=03;{ch2.BANK_GOLD_AT & 0xFFFF:04X}=02'

def join_set(data):
    """두 사람 합류(dq4ch2event._join)가 기록에 남기는 것: 일행 기록 1·2, 일행 수 3, 순서 0 1 2. 다음 레벨 경험치는
    틀 값 그대로다(합류 이벤트는 21:805A 로 다시 셈). dq5warp.lua PARTY 는 몬스터 동료 기록만 만들어 쓰지 않는다."""
    records = b''.join(ch2.recruit_records(data))
    at = ch2.JOIN_RECORDS_AT & 0xFFFF
    out = [f'{at + i:04X}={v:02X}' for i, v in enumerate(records)]
    n = 1 + len(ch2.RECRUITS)
    out += [f'{a:04X}={n:02X}' for a in (0x201D, 0x201E, 0x201F)]
    out += [f'{base + k:04X}={k:02X}' for k in range(n) for base in (0x2020, 0x2028)]
    return ';'.join(out)


def effects(data):
    """구간이 flag 말고 기록(7E:2000~2A9F)에 남기는 것(구간 이름 → SET(set)·dq5warp.lua PARTY(party)). 묶음 첫
    구간에 둔다. 롬의 기록 틀을 읽는 것이 있어 롬 바이트를 받는다."""
    return {'join': {'set': join_set(data)}, 'chest': {'set': BRACELET_SET}, 'honey': {'set': HONEY_SET}}



# 남쪽 동굴의 상자를 연 기록: 주인공(비단 로브 하나를 가짐)의 둘째 칸에 황금의 팔찌, 상자 열림 비트
BRACELET_SET = f'{(wc.ITEMS & 0xFFFF) + 1:04X}={frenol.BRACELET:02X};{frenol.CHEST_OPEN[0]:04X}|{frenol.CHEST_OPEN[1]:02X}'

# 탑 꼭대기에서 찾은 지저귐의 꿀. 묶음마다 따로 시작하므로 크리프트(일행 기록 1, 물건 둘)의 셋째 칸에 둔다. 주인공의
# 칸은 앞 사건의 물건과 겹친다
HONEY_SET = f'{(ch2.JOIN_RECORDS_AT & 0xFFFF) + 0x16 + 2:04X}={king.HONEY:02X}'

# 같은 맵 안으로 순간이동하는 묶음이 먼저 들르는 곳(2장 출발 상태는 왕좌의 방 3D/01)
HOPS = {ch2.THRONE: f'{ch2.CASTLE},28,45'}

# 낮의 왕좌의 방에서 걸어 다니는 브라이(목록 첫 인물 = 물체 슬롯 08)의 걸음 간격을 0 으로 묶어 제자리에 세운다.
# 묶지 않으면 난수에 따라 비켜 서서 시드 5·9 에서 「その方向には誰もいない」(129)가 났다
HOLD_BREY = '7E3308=00'

KING_INDEX = [s[0] for s in wc.SEGMENTS].index('castle')

# (이름, 방법, 인자, 선택). 꼴은 dq4ch1walkcheck.SEGMENTS 와 같다. 첫 셋이 머리(2장 출발 상태까지)다
SEGMENTS = [
    wc.SEGMENTS[KING_INDEX],
    wc.CHAPTER2_END[0],
    # 제목 상자·서두 서술·부르는 소리·왕의 말을 넘기면 첫머리 flag 가 꺼지고 조작이 풀린다. A 를 더 누르면 왕에게
    # 다시 말을 걸어 물음이 되풀이되므로(12번째 A 에서 실측) 넘길 만큼만 누른다
    ('opening', 'walk', 'wait:200;' + taps(10, 90) + ';wait:300;' + CLOSE,
     {'maxf': 4000, 'map': ch2.THRONE, 'want': ['CHAPTER2'], 'off': ['OPENING', 'BANK_HERB', 'BANK_GOLD'],
      'items': [ch2.SILK_ROBE]}),
]
HEAD = 3

# 신부에게 대신 간다 → 바구니 서술. 제단 앞에 닿으면 곧 보스 전투(dq4ch2tempe)다
BASKET = talk('up', 14) + ';wait:600;' + taps(10)
# 지면 FC 2장 시작 귀환 자리(サラン 교회 45/02, dq4fieldtravel 의 2장 칸)에서 다시 시작한다
WIPE_MAP, WIPE_CELL = '45/02', (8, 19)
# 아침의 제단 위에서 곧장 아래로(교회를 지나) 촌장 위 칸까지 걸어 내려온다
LEAVE_ALTAR = f'{tempe.CHIEF_TALK_CELL[0]},{tempe.CHIEF_TALK_CELL[1]}'


def battle_patch(data, kind):
    """사건 전투 몬스터(dq4ch2event 모듈의 BATTLES)를 덮는 ROMPATCH. win 은 HP 1·수비 0(1장 boss_patch 와 같음),
    weak 는 win 에 공격 0·MP 0·행동 여섯 모두 たたかう(일행이 다치지 않음), lose 는 HP 1000·공격 511·민첩 255(일행이 먼저
    쓰러짐). 「weak:5A+lose:4C」 처럼 + 로 잇고 : 뒤에 몬스터(16진, 쉼표)를 주면 그 몬스터만 덮는다."""
    every = sorted({m for _, mod in ch2.modules() for b in getattr(mod, 'BATTLES', ()) for m, _ in b['members']})
    out = []
    for piece in kind.split('+'):
        how, _, only = piece.partition(':')
        for n in [int(m, 16) for m in only.split(',')] if only else every:
            base = wc.MONSTERS + n * 25
            if how in ('win', 'weak'):
                out += [f'{base + 2:X}=00', f'{base + 3:X}=01',
                        f'{base + 8:X}={data[base + 8] & ~(0xC0 if how == "weak" else 0x40) & 0xFF:02X}',
                        f'{base + 10:X}={data[base + 10] & ~0x07 & 0xFF:02X}']
                if how == 'weak':
                    out += [f'{base + 1:X}=00', f'{base + 4:X}=00', *(f'{base + k:X}=73' for k in range(17, 23))]
            elif how == 'lose':
                out += [f'{base:X}=FF', f'{base + 1:X}=FF', f'{base + 3:X}=E8', f'{base + 8:X}={data[base + 8] | 0x80:02X}',
                        f'{base + 10:X}={data[base + 10] & ~0x07 | 0x03:02X}']
            else:
                raise ValueError(f'전투 선택 {kind}: win·weak·lose')
    return ';'.join(out)


# 명령 창 → 「조사하기」(dq4chestcheck.SEARCH 를 walk.lua 꼴로)
CHEST_SEARCH = ('a:8;wait:60;down:6;wait:25;down:6;wait:25;down:6;wait:25;right:6;wait:25;a:8;wait:200;'
                'a:4;wait:150;a:4;wait:150;b:4;wait:220')


# 2장 사건 구간. 순간이동(warp) 구간마다 새 묶음이고, 묶음 첫 구간에는 앞 구간들의 want·off·effects 가 놓인다.
# 선택은 dq4ch1walkcheck.SEGMENTS 의 것에 더해 cell(끝에 주인공이 선 셀 (x, y))
SEGMENTS += [
    # 산트하임 성: 크리프트·브라이·성문 병사와 이야기해 「셋 다」를 켠다(dq4ch2event TALKED_*·READY)
    ('kiryl_side', 'warp', f'{ch2.CASTLE},52,22', {'map': ch2.CASTLE}),
    ('kiryl', 'walk', talk('up'), {'want': ['TALKED_KIRYL']}),
    ('brey_side', 'warp', f'{ch2.THRONE},24,26', {'map': ch2.THRONE, 'poke': HOLD_BREY}),
    ('brey', 'walk', talk('right'), {'want': ['TALKED_BREY'], 'poke': HOLD_BREY}),
    ('gate_side', 'warp', f'{ch2.CASTLE},28,48', {'map': ch2.CASTLE}),
    ('gate', 'walk', talk('down'), {'want': ['TALKED_GATE', 'READY']}),
    # 왕의 방 벽 앞에서 오른쪽을 보면 묻고, 예 → 걷어차 필드 산트하임 나오는 칸 (78,149)로. 필드 네 걸음째에 두
    # 사람이 합류한다. 필드에서도 7E:00BC·00BD 는 떠난 맵 번호 그대로라 끝 맵 대신 필드인지를 본다
    ('wall_side', 'warp', f'{ch2.BEDROOM},22,9', {'map': ch2.BEDROOM}),
    ('wall', 'walk', f'{ch2.WALL_STAND[0]},{ch2.WALL_STAND[1]};right:8;wait:60;' + taps(5, 60) + ';wait:400',
     {'want': ['KICKED'], 'field': True, 'cell': (78, 149)}),
    ('join', 'walk', 'down:120;wait:200;' + taps(8) + ';' + CLOSE, {'want': ['JOINED'], 'field': True}),
    # 텐페 제물 사건 앞 절반: 촌장의 부탁 → 신부에게 대신 간다 → 바구니로 제단 앞(밤)
    ('chief_side', 'warp', f'{ch2.TEMPE},{ch2.CHIEF[0]},{ch2.CHIEF[1] + 1}', {'map': ch2.TEMPE}),
    ('chief', 'walk', talk('up', 10), {'want': ['TEMPE_HEARD']}),
    # 텐페 뒤 절반: 바구니로 제단 앞에 닿으면 보스 전투(dq4ch2tempe). 지면 기록한 교회(サラン)로 가고 앞 절반 flag 가
    # 꺼져 촌장에게 다시 듣는다. 이기면 서술 뒤 아침의 제단 앞, 괴물이 사라진 뒤의 마을
    ('lose_side', 'warp', f'{ch2.TEMPE},{ch2.PRIEST[0]},{ch2.PRIEST[1] + 1}', {'map': ch2.TEMPE}),
    ('lose', 'walk', BASKET + ';' + taps(40, 40) + ';wait:300;' + CLOSE,
     {'battle': 'lose', 'off': ['TEMPE_HEARD', 'TEMPE_GONE', 'TEMPE_ALTAR', 'TEMPE_WON'], 'map': WIPE_MAP,
      'cell': WIPE_CELL}),
    ('rechief_side', 'warp', f'{ch2.TEMPE},{ch2.CHIEF[0]},{ch2.CHIEF[1] + 1}', {'map': ch2.TEMPE}),
    ('rechief', 'walk', talk('up', 10), {'want': ['TEMPE_HEARD']}),
    ('priest_side', 'warp', f'{ch2.TEMPE},{ch2.PRIEST[0]},{ch2.PRIEST[1] + 1}', {'map': ch2.TEMPE}),
    ('priest', 'walk', BASKET + ';' + taps(110, 40) + ';wait:600;' + taps(6) + ';' + CLOSE,
     {'battle': 'win', 'poke': wc.HERO_HP, 'want': ['TEMPE_WON'], 'off': ['TEMPE_HEARD', 'TEMPE_GONE', 'TEMPE_ALTAR'],
      'map': ch2.TEMPE, 'cell': tempe.MORNING_CELL}),
    ('leave_altar', 'walk', LEAVE_ALTAR, {'map': ch2.TEMPE, 'cell': tempe.CHIEF_TALK_CELL}),
    ('chief_won', 'walk', talk('down', 6), {'want': ['TEMPE_WON'], 'map': ch2.TEMPE}),
    # 프레놀 가짜 공주(dq4ch2frenol): 여관 2층 방 아래 (1E,08)에서 위로 올라가면 비명 → 「멈춰라!」 → 셋이 계단으로
    ('inn_side', 'warp', f'{frenol.INN},60,17', {'map': frenol.INN}),
    ('kidnap', 'walk', '60,16;wait:60;' + taps(1) + ';' + CLOSE + ';60,14;58,14;58,12;wait:60;' + taps(6) + ';wait:400;' + CLOSE,
     {'want': ['FRENOL_KIDNAPPED'], 'map': frenol.INN}),
    # 마을에서는 셋이 서쪽 길로 빠져나간다. 서쪽 어귀 위 (05,06)에서 기다린다
    ('kidnap_town_side', 'warp', f'{frenol.TOWN},10,13', {'map': frenol.TOWN}),
    ('kidnap_town', 'walk', 'wait:1200', {'want': ['FRENOL_LEFT'], 'map': frenol.TOWN}),
    # 납치 뒤에는 여관 주인이 「아이고, 아이고……」 뒤 여관을 연다(FC 대화 033 의 15:BF30). 카운터 아래 (11,0E)에서
    ('inn_open_side', 'warp', f'{frenol.TOWN},34,28', {'map': frenol.TOWN}),
    ('inn_open', 'walk', talk('up', 2), {'map': frenol.TOWN}),
    # 남쪽 동굴: 상자 아래 칸에서 위를 보고 「조사하기」
    ('cave_side', 'warp', f'{frenol.CAVE},20,71', {'map': frenol.CAVE}),
    ('chest', 'walk', 'up:8;wait:30;' + CHEST_SEARCH + ';' + CLOSE,
     {'want': ['BRACELET_CHEST'], 'items': [frenol.BRACELET], 'map': frenol.CAVE}),
    # 밤의 묘지: 서쪽 어귀에서 내려와 (03,0B)에 서면 망토가 요구 → 예 → 메이 → 도적의 열쇠 → 아침의 같은 칸
    ('grave_side', 'warp', f'{frenol.TOWN},6,19', {'map': frenol.TOWN, 'poke': wc.NIGHT}),
    ('grave', 'walk', '6,23;wait:120;' + taps(30, 50) + ';wait:300;' + CLOSE,
     {'want': ['FRENOL_RESCUED'], 'off': ['FRENOL_SCENE'], 'items': [frenol.THIEF_KEY], 'map': frenol.TOWN}),
]

# 왕의 병(dq4ch2king): 바자 병사 → 왕좌의 방 병사 → 사당이 막힘 → 탑 꼭대기의 엘프와 꿀 → 왕 회복 → 사당의 여행의 문
SEGMENTS += [
    ('bazaar_side', 'warp', f'{king.BAZAAR_MAP},{king.BAZAAR_SOLDIER[0]},{king.BAZAAR_SOLDIER[1] + 1}',
     {'map': king.BAZAAR_MAP}),
    ('bazaar', 'walk', talk('up'), {'want': ['KING_BAZAAR']}),
    # 계단 아래 칸에서 위로 걸어 계단 위 줄에 들면 병사가 알린다
    ('throne_side', 'warp', f'{ch2.THRONE},24,36', {'map': ch2.THRONE}),
    ('throne', 'walk', '24,34;wait:120;' + taps(4, 60) + ';' + CLOSE, {'want': ['KING_HEARD']}),
    # 왕이 낫기 전에는 사당 병사가 위 방으로 가는 틈에 서 있어 여행의 문에 닿지 못한다
    ('closed_side', 'warp', f'{king.SHRINE},10,20', {'map': king.SHRINE}),
    ('closed', 'walk', '10,15;8,15;8,11;wait:60;' + taps(4, 60) + ';' + CLOSE,
     {'map': king.SHRINE, 'maxf': 1500, 'cell': (8, 15)}),
    # 탑 꼭대기: 계단 옆에서 위로 걸어 줄 0C 에 들면 엘프가 달아나고, 엘프가 섰던 칸을 밟으면 꿀을 찾는다
    ('tower_side', 'warp', f'{king.TOWER_TOP},14,28', {'map': king.TOWER_TOP}),
    ('tower', 'walk', '14,25;wait:60;' + taps(6, 60) + ';wait:200', {'want': ['KING_SEEN']}),
    ('honey', 'walk', '16,18;wait:60;' + taps(3, 60) + ';' + CLOSE, {'want': ['KING_GOT']}),
    # 꿀을 가진 채 왕에게 말을 걸면 먹이고 왕이 낫는다
    ('cure_side', 'warp', f'{ch2.THRONE},{ch2.START_CELL[0]},{ch2.START_CELL[1] - 1}', {'map': ch2.THRONE}),
    ('cure', 'walk', talk('up', 20), {'want': ['KING_CURED']}),
    # 병사가 비켜선 사당: 위 방의 여행의 문으로 엔돌 쪽 사당에 닿는다
    ('shrine_side', 'warp', f'{king.SHRINE},10,20', {'map': king.SHRINE}),
    ('shrine', 'walk', '10,15;8,15;8,11;10,11;10,7', {'map': king.SHRINE_FAR, 'changes': 1}),
]


# 엔돌 무술 대회(dq4ch2endor). 일행 순서를 0 1 2 가 아닌 브라이·아리나·크리프트로 두고 들어가, 빼고 되돌린 뒤에도 그
# 순서인지 본다. 대회 중 상태(IN·이긴 수·일행 하나)로 링에 서면 링 인물이 그 판부터 잇는다
ENDOR_ORDER = (2, 0, 1)
ENDOR_ORDER_POKE = ';'.join(f'7E{a + k & 0xFFFF:04X}={v:02X}' for a in endor.ORDERS for k, v in enumerate(ENDOR_ORDER))
ENDOR_RING = f'{endor.ARENA},28,26'        # 링 아래 길 (28,27)에 내린다. 위로 걸어 (28,25)에서 링에 든다
ENDOR_IN_RING = '28,24;wait:60;'
ENDOR_BACK = {'PARTY_COUNT': 3, **{f'ORDER{k}': v for k, v in enumerate(ENDOR_ORDER)}}
ENDOR_FLAGS_OFF = ['ENDOR_IN', 'ENDOR_LOST']


def endor_in(stage):
    """대회 중 상태: IN 과 맡긴 순서 첫 둘, 이긴 수, 일행 하나(아리나)."""
    keep = (ENDOR_ORDER[0] | ENDOR_ORDER[1] << 2) << endor.ORDER_SHIFT | endor.IN[1]
    return (f'7E{endor.FLAG_AT & 0xFFFF:04X}={keep:02X};7E{endor.STAGE_AT & 0xFFFF:04X}={stage:02X};' +
            ';'.join(f'7E{c & 0xFFFF:04X}=01' for c in endor.COUNTS) + ';' +
            ';'.join(f'7E{a & 0xFFFF:04X}=00' for a in endor.ORDERS))


def endor_monster(k):
    return f'{endor.OPPONENTS[k][1]:02X}'


# 약초 둘과 셋째 칸의 장비한 비단 로브. 둘 다 쓰면 로브가 첫 칸으로 당겨지고 장비 비트도 따라온다
ENDOR_HERBS = (f'7E{endor.ALENA_ITEMS & 0xFFFF:04X}={endor.HERB:02X};7E{endor.ALENA_ITEMS + 1 & 0xFFFF:04X}={endor.HERB:02X};'
               f'7E{endor.ALENA_ITEMS + 2 & 0xFFFF:04X}={ch2.SILK_ROBE:02X};7E{endor.ALENA_ITEMS + 3 & 0xFFFF:04X}=FF;'
               f'7E{endor.ALENA_EQUIP & 0xFFFF:04X}=04;7E{endor.ALENA_EQUIP + 1 & 0xFFFF:04X}=00')

SEGMENTS += [
    # ① 출전·③ 짐: 링에 들어서면 응원·규칙 뒤 첫 상대. 지면 대기실 침대 옆에서 깨어나고 일행이 그 순서로 돌아온다
    ('endor_lose_side', 'warp', ENDOR_RING, {'map': endor.ARENA, 'poke': ENDOR_ORDER_POKE}),
    ('endor_lose', 'walk', ENDOR_IN_RING + taps(30, 60) + ';wait:300;' + CLOSE,
     {'battle': f'lose:{endor_monster(0)}', 'map': endor.BEDROOM, 'cell': endor.BED_CELL,
      'off': ENDOR_FLAGS_OFF + ['ENDOR_CHAMPION'], 'bytes': {'ENDOR_STAGE': 0, **ENDOR_BACK}, 'maxf': 5500}),
    # ② 상대마다 따로: 이긴 수 k 인 대회 중 상태로 링에 서서 k 번째 상대를 이기고, 다음 상대에게 져 침대로. 첫 상대는
    # 약초 둘을 쥐고 이긴 뒤 둘 다 쓴다(047D → 047E → 047F)
    *[seg for k in range(endor.ROUNDS - 1) for seg in (
        (f'endor_bout{k}_side', 'warp', ENDOR_RING,
         {'map': endor.ARENA, 'poke': endor_in(k) + (';' + ENDOR_HERBS if k == 0 else '')}),
        (f'endor_bout{k}', 'walk', ENDOR_IN_RING + taps(50, 60) + ';wait:300;' + CLOSE,
         {'battle': f'weak:{endor_monster(k)}+lose:{endor_monster(k + 1)}', 'map': endor.BEDROOM,
          'cell': endor.BED_CELL, 'off': ENDOR_FLAGS_OFF + ['ENDOR_CHAMPION'], 'maxf': 7000,
          'bytes': {'ENDOR_STAGE': k + 1, **ENDOR_BACK,
                    **({'ALENA_ITEM0': ch2.SILK_ROBE, 'ALENA_ITEM1': 0xFF, 'ALENA_EQUIP': 0x01} if k == 0 else {})}}))],
    # 대회 중 판 사이마다 방향 키를 눌러도 링 인물의 대화가 끊기지 않고 넷째·다섯째를 잇달아 이겨 우승, 일행이
    # 돌아온다(일행 하나인 채 대회 밖으로 나가는 길이 없음). 아래·위는 전투 명령 창에서 「도망」 을 골라 오른쪽을 쓴다
    ('endor_held_side', 'warp', ENDOR_RING, {'map': endor.ARENA, 'poke': endor_in(endor.ROUNDS - 2)}),
    ('endor_held', 'walk', ENDOR_IN_RING + taps(6, 60) + ';' + ';'.join(['a:8;wait:40;right:24;wait:20'] * 90) + ';wait:300;' + CLOSE,
     {'battle': f'weak:{endor_monster(endor.ROUNDS - 2)},{endor_monster(endor.ROUNDS - 1)}', 'map': endor.ARENA,
      'want': ['ENDOR_CHAMPION'], 'off': ENDOR_FLAGS_OFF, 'bytes': {'ENDOR_STAGE': endor.ROUNDS, **ENDOR_BACK},
      'maxf': 12000}),
    # 다섯째 상대를 이기면 결승 상대 데스피사로가 없어 우승, 브라이·크리프트와 일행이 돌아온다
    ('endor_final_side', 'warp', ENDOR_RING, {'map': endor.ARENA, 'poke': endor_in(endor.ROUNDS - 1)}),
    ('endor_final', 'walk', ENDOR_IN_RING + taps(40, 60) + ';wait:300;' + CLOSE,
     {'battle': f'weak:{endor_monster(endor.ROUNDS - 1)}', 'map': endor.ARENA, 'want': ['ENDOR_CHAMPION'],
      'off': ENDOR_FLAGS_OFF, 'bytes': {'ENDOR_STAGE': endor.ROUNDS, **ENDOR_BACK}, 'maxf': 5500}),
    # ④ 우승 뒤 엔돌 성 앞: 해자 다리 아래에서 성 쪽으로 오르면 산트하임에서 온 사자가 말한다
    ('endor_messenger_side', 'warp', f'{endor.TOWN},46,28', {'map': endor.TOWN}),
    ('endor_messenger', 'walk', '46,23;wait:60;' + taps(4) + ';wait:200;' + CLOSE,
     {'map': endor.TOWN, 'want': ['ENDOR_MESSENGER']}),
]


def units(segments=None):
    """머리 뒤 구간을 묶음으로 나눈다: 순간이동 구간마다 새 묶음."""
    segments = SEGMENTS if segments is None else segments
    out = []
    for i in range(HEAD, len(segments)):
        if segments[i][1] == 'warp' or not out:
            out.append([i])
        else:
            out[-1].append(i)
    return out


def setup(first, segments=None, data=None):
    """first 번째 구간 앞까지 걸었다면 켜져 있을 flag·기록(SET)과 동료(PARTY). 머리 구간의 flag 는 2장 출발 상태에
    이미 있으므로 머리 뒤 구간만 센다. data(롬 바이트)가 없으면 기록 효과는 두지 않는다."""
    segments = SEGMENTS if segments is None else segments
    return wc.setup(segments[HEAD:], first - HEAD, FLAGS, effects(data) if data is not None else {})


def head_key(mesence):
    """2장 출발 상태를 정하는 것: 서장 캐시 키(1장 검사·사건 코드·Lua·에뮬레이터)에 머리를 걷는 코드와 머리 구간·그
    시작 flag 를 더한다. 이 파일 전체를 넣지 않는 것은 사건 구간이 붙을 때마다 머리를 다시 걷지 않게 하려는 것이다."""
    return wc.code_key(mesence, inspect.getsource(head), repr(SEGMENTS[:HEAD]), CH1_BANK,
                       repr(wc.setup(wc.SEGMENTS, KING_INDEX)))


def head_effects():
    """머리 묶음 첫 구간에 둘 기록: 1장 검사의 것에 1장에 맡긴 것(CH1_BANK)을 더한다. setup 은 첫 구간 앞 구간의
    효과만 모으므로 왕 보고 바로 앞 구간에 붙인다."""
    effects = dict(wc.EFFECTS)
    before = wc.SEGMENTS[KING_INDEX - 1][0]
    effects[before] = {**effects.get(before, {}),
                       'set': ';'.join(v for v in (effects.get(before, {}).get('set'), CH1_BANK) if v)}
    return effects


def head(mesence, rom, data, out, cache=None):
    """2장 출발 상태와 머리 구간 결과. 서장은 dq4ch1walkcheck.prologue(캐시)로, 머리는 시드 0 으로 한 번만 걷는다."""
    key = head_key(mesence) if cache else None
    state = out / SEGMENTS[HEAD - 1][0] / 'end.mss'
    hit = cache.get('ch2-opening', key, '.mss', state) if cache else None
    if hit:
        return state, [{**r, 'cached': cache.path('ch2-opening', key, '.mss').name} for r in hit[1]['segments']]
    base, pro = wc.prologue(mesence, rom, data, out, wc.SEGMENTS, cache)
    if pro['status'] != 'passed':
        return None, [pro]
    # 1장 구간 표의 왕 보고 앞까지에 머리를 이어, 1장 묶음 걷기와 같은 flag·동료·같은 맵 들르기로 시작한다
    chain = wc.SEGMENTS[:KING_INDEX] + SEGMENTS[:HEAD]
    results = wc.walk_unit(mesence, rom, data, out, chain, list(range(KING_INDEX, KING_INDEX + HEAD)), base,
                           flags=FLAGS, effects=head_effects())
    if len(results) != HEAD or any(r['status'] != 'passed' for r in results):
        return None, results
    if cache:
        cache.put('ch2-opening', key, '.mss', state, {'segments': results})
    return state, results


def walk_unit(mesence, rom, data, out, unit, base, seed=0, segments=None):
    """한 묶음을 2장 출발 상태에서 걷는다."""
    segments = SEGMENTS if segments is None else segments
    extra, party = setup(unit[0], segments, data)
    state, results = base, []
    name, how, arg, _ = segments[unit[0]]
    if how == 'warp' and arg.split(',')[0] == ch2.THRONE:
        hop = HOPS[ch2.THRONE]
        r = wc.segment(mesence, rom, state, out / f'{name}-hop', (f'{name}-hop', 'warp', hop, {'map': hop[:5]}),
                       wc.NO_ENCOUNTERS, extra, party, seed, flags=FLAGS)
        if r['status'] != 'passed':
            return [r]
        state, extra, party = out / f'{name}-hop' / 'end.mss', '', ''
    for k, i in enumerate(unit):
        seg = segments[i]
        patch = wc.NO_ENCOUNTERS + (';' + battle_patch(data, seg[3]['battle']) if 'battle' in seg[3] else '')
        r = wc.segment(mesence, rom, state, out / seg[0], seg, patch,
                       *((extra, party) if k == 0 else ('', '')), seed, flags=FLAGS)
        more = [p for p in (end_cell_problem(out / seg[0], seg), *end_byte_problems(out / seg[0], seg)) if p]
        if more:
            r = {**r, 'status': 'failed', 'problems': r['problems'] + more}
        results.append(r)
        if r['status'] != 'passed':
            break
        state = out / seg[0] / 'end.mss'
    return results


def end_cell_problem(dest, seg):
    """선택 cell 이 있는 걷기 구간에서 끝에 선 셀이 다르면 그 까닭."""
    name, how, _, opt = seg
    if 'cell' not in opt or how != 'walk':
        return None
    log = dest / 'walk.txt'
    found = re.search(r'end map \w\w/\w\w x=(\d+) y=(\d+)', log.read_text(encoding='utf-8')) if log.exists() else None
    got = (int(found[1]), int(found[2])) if found else None
    return None if got == tuple(opt['cell']) else f"끝 셀 {got}, 기대 {tuple(opt['cell'])}"


def end_byte_problems(dest, seg):
    """선택 bytes({FLAGS 이름: 값})가 있는 걷기 구간에서 끝 값이 다른 칸들. walk.lua 는 FLAGS 의 바이트를 이름=값으로 찍는다."""
    name, how, _, opt = seg
    if 'bytes' not in opt or how != 'walk':
        return []
    log = dest / 'walk.txt'
    seen = dict(re.findall(r'^(\w+)=([0-9A-F]+)$', log.read_text(encoding='utf-8'), re.M)) if log.exists() else {}
    return [f'{k} = {seen.get(k)}, 기대 {v:02X}' for k, v in opt['bytes'].items()
            if k not in seen or int(seen[k], 16) & 0xFF != v]


def compare_runs(first, second):
    """두 번 걸은 묶음 결과에서 구간 기록 SHA-1 이 다른 구간의 까닭."""
    problems = {}
    for a, b in zip(first, second):
        if a.get('trace') != b.get('trace') or a['status'] != b['status']:
            problems[a['name']] = f"두 번 걸은 기록이 다름: {a.get('trace')}/{a['status']} ≠ {b.get('trace')}/{b['status']}"
    if len(first) != len(second):
        problems['_'] = f'두 번 걸은 구간 수가 다름: {len(first)} ≠ {len(second)}'
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help='dq4build.py --chapter2 의 롬')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=6, help='함께 띄울 MesenCE 수')
    ap.add_argument('--base', type=Path, help='같은 롬으로 만든 2장 출발 상태(opening/end.mss). 주면 머리를 건너뜀')
    ap.add_argument('--only', help='이 구간으로 시작하는 묶음만(쉼표로 여럿)')
    ap.add_argument('--repeat', type=int, default=1, choices=(1, 2), help='2 면 묶음마다 두 번 걸어 기록을 견줌')
    wc.add_seed_args(ap)
    args = ap.parse_args()
    seeds = wc.seeds_of(args)
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    cache = None if args.no_state_cache else wc.StateCache(data)
    began = time.monotonic()
    names = [s[0] for s in SEGMENTS]
    groups = units()
    if args.only:
        wanted = args.only.split(',')
        unknown = [w for w in wanted if w not in names[HEAD:]]
        if unknown:
            raise SystemExit(f'없는 구간: {", ".join(unknown)}')
        groups = [u for u in groups if names[u[0]] in wanted]
    if args.base:
        base, head_results = args.base.resolve(), []
    else:
        base, head_results = head(mesence, rom, data, out, cache)
        for r in head_results:
            print(json.dumps(r, ensure_ascii=False), flush=True)
    runs = {s: [] for s in seeds}
    unit_seconds = {}
    repeat_problems = {}
    if base is not None:
        def one(seed, unit, n):
            t0 = time.monotonic()
            dest = wc.seed_dir(out, seed, seeds) / (f'run-{n}' if args.repeat > 1 else '')
            rs = walk_unit(mesence, rom, data, dest, unit, base, seed)
            return rs, round(time.monotonic() - t0)
        with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
            jobs = {(s, tuple(u), n): pool.submit(one, s, u, n)
                    for s in seeds for u in groups for n in range(1, args.repeat + 1)}
            for job in concurrent.futures.as_completed(jobs.values()):
                for r in job.result()[0]:
                    print(json.dumps(r, ensure_ascii=False), flush=True)
        for s in seeds:
            for u in groups:
                rs, secs = jobs[s, tuple(u), 1].result()
                unit_seconds[f'{s}:{names[u[0]]}'] = secs
                if args.repeat > 1:
                    bad = compare_runs(rs, jobs[s, tuple(u), 2].result()[0])
                    for r in rs:
                        if r['name'] in bad:
                            r['problems'] = r['problems'] + [bad[r['name']]]
                            r['status'] = 'failed'
                    if '_' in bad:
                        repeat_problems[f'{s}:{names[u[0]]}'] = bad['_']
                runs[s] += rs
    head_ok = base is not None and all(r['status'] == 'passed' for r in head_results)
    expected = sum(len(u) for u in groups)
    per_seed = [{'seed': s, 'rng': wc.rng_for(s),
                 'status': 'passed' if head_ok and len(rs) == expected and all(r['status'] == 'passed' for r in rs)
                 and not any(k.startswith(f'{s}:') for k in repeat_problems) else 'failed',
                 'segments': rs} for s, rs in runs.items()]
    ok = head_ok and all(r['status'] == 'passed' for r in per_seed)
    report = {'status': 'passed' if ok else 'failed', 'seconds': round(time.monotonic() - began),
              'state_cache': 'off' if cache is None or args.base else
              'hit' if head_results and head_results[0].get('cached') else 'miss',
              'repeat': args.repeat, 'head': head_results, 'unit_seconds': unit_seconds,
              'repeat_problems': repeat_problems, 'seeds': per_seed}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'status': report['status'], 'seconds': report['seconds'], 'state_cache': report['state_cache'],
                      'units': len(groups), 'unit_seconds': unit_seconds,
                      'failed': [f"{s['seed']}:{r['name']}" for s in per_seed for r in s['segments']
                                 if r['status'] != 'passed']}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
