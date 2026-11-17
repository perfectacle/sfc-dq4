"""엔돌 무술 대회(dq4ch2endor)의 검사 표. 내놓는 것은 dq4eventchecks 머리말."""
import dq4ch2event as ch2
import dq4ch2endor as endor
from dq4ch2walkparts import CLOSE, flag, taps

FLAGS = {
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
}

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

SEGMENTS = [
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
