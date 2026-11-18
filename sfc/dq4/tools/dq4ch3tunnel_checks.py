"""굴 공사·개통·장 끝(dq4ch3tunnel)의 검사 표. 내놓는 것은 dq4eventchecks 머리말."""
import dq4ch1walkcheck as wc
import dq4ch2event as ch2
import dq4ch3endor as endor
import dq4ch3event as ch3
import dq4ch3slots as slots
import dq4ch3tunnel as tunnel
from dq4ch3walkparts import CLOSE, set_flag, talk, talk_yes, taps

FLAGS = {
    'TUNNEL_PAID': wc.flag(tunnel.PAID),
    'TUNNEL_WAITING': wc.flag(tunnel.WAITING),
    'TUNNEL_RESUMED': wc.flag(tunnel.RESUMED),
    'TUNNEL_OPENED': wc.flag(tunnel.OPENED),
    'TUNNEL_GOLD0': (0x7E2019, 0xFF), 'TUNNEL_GOLD1': (0x7E201A, 0xFF), 'TUNNEL_GOLD2': (0x7E201B, 0xFF),
    'HAND_CH3': wc.flag(ch3.CHAPTER3),
    # 넘김(dq4ch3tunnel._handover)이 비우는 칸의 앞·끝 바이트: 3장 칸 43~49, 맡긴 물건, 맡긴 금화
    'HAND_CLEAR0': (slots.CHAPTER_END_CLEAR[0] + 1, 0xFF), 'HAND_CLEAR1': (slots.CHAPTER_END_CLEAR[1] - 1, 0xFF),
    'HAND_BANK0': (ch2.BANK_ITEMS_AT, 0xFF), 'HAND_BANK1': (ch2.BANK_ITEMS_AT + ch2.BANK_ITEMS - 1, 0xFF),
    'HAND_BANKG0': (ch2.BANK_GOLD_AT, 0xFF), 'HAND_BANKG1': (ch2.BANK_GOLD_AT + 1, 0xFF),
}
# 장 끝 넘김 앞에 둘 표지 값(금화 12345, 비울 칸마다 55)
HAND_MARKS = ';'.join(['2019=39', '201A=30', '201B=00'] + [f'{FLAGS[k][0] & 0xFFFF:04X}=55' for k in
                                              ('HAND_CLEAR0', 'HAND_CLEAR1', 'HAND_BANK0', 'HAND_BANK1', 'HAND_BANKG0',
                                               'HAND_BANKG1')])
HAND_WANT = {'TUNNEL_GOLD0': tunnel.NEXT_GOLD, 'TUNNEL_GOLD1': 0, 'TUNNEL_GOLD2': 0,
             **{k: 0 for k in ('HAND_CLEAR0', 'HAND_CLEAR1', 'HAND_BANK0', 'HAND_BANK1', 'HAND_BANKG0', 'HAND_BANKG1')}}

# 굴(dq4ch3tunnel). 47/00 노인 아래 칸에서 위를 보고 말을 건다. 쪽마다 A 하나(글이 다 찍히도록 90프레임 간격), 마지막
# A 하나가 연 명령 창은 닫는다. 「예」 는 커서 그대로 A
TUNNEL_BELOW_OLD = tunnel.cell(tunnel.OLD_MAN[0], tunnel.OLD_MAN[1] + 1)
TUNNEL_ARRIVAL = tunnel.cell(0x05, 0x0B)


def tunnel_talk(presses):
    return f'up:8;wait:30;a:8;wait:60;a:8;wait:90;{taps(presses + 1, 90)};wait:60;{CLOSE}'


def tunnel_yes(presses):
    """tunnel_talk 와 같되 물음마다 「예」, 말이 끝날 때까지 넘긴다(dq4walk.lua done). presses 는 기다릴 상한만 정한다."""
    return f'up:8;wait:30;a:8;wait:60;a:8;wait:90;done:{98 * (presses + 1) + 400}'


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
SEGMENTS = [
    # 금화가 모자라면 「예」 를 해도 그대로(0895)
    ('tunnel_short_side', 'warp', f'{tunnel.BLOCKED},{TUNNEL_BELOW_OLD[0]},{TUNNEL_BELOW_OLD[1] - 1}',
     {'map': tunnel.BLOCKED, 'set': TUNNEL_GOLD(10000)}),
    ('tunnel_short', 'walk', tunnel_yes(5),
     {'map': tunnel.BLOCKED, 'off': ['TUNNEL_PAID', 'TUNNEL_WAITING'],
      'bytes': {'TUNNEL_GOLD0': 0x10, 'TUNNEL_GOLD1': 0x27, 'TUNNEL_GOLD2': 0}}),
    # 가게를 사기 전이면 「예」 뒤 0894(엔돌 모듈 SHOP 을 끔)
    ('tunnel_noshop_side', 'warp', f'{tunnel.BLOCKED},{TUNNEL_BELOW_OLD[0]},{TUNNEL_BELOW_OLD[1] - 1}',
     {'map': tunnel.BLOCKED, 'set': f'{TUNNEL_GOLD(65000)};{0x2190 + endor.SHOP[0]:04X}=00'}),
    ('tunnel_noshop', 'walk', tunnel_yes(5),
     {'map': tunnel.BLOCKED, 'off': ['TUNNEL_PAID', 'TUNNEL_WAITING'],
      'bytes': {'TUNNEL_GOLD0': 0xE8, 'TUNNEL_GOLD1': 0xFD, 'TUNNEL_GOLD2': 0}}),
    # 60000 을 내고(0896·0897), 다시 말을 걸면 0897. 필드에 나갔다 들어오면 WAITING 이 꺼지고, 말을 걸면 공사 재개(0898)
    # 앞의 엔돌 구간(endor_nene_notice)이 켠 OPENED 를 끄고 시작한다
    ('tunnel_pay_side', 'warp', f'{tunnel.BLOCKED},{TUNNEL_BELOW_OLD[0]},{TUNNEL_BELOW_OLD[1] - 1}',
     {'map': tunnel.BLOCKED, 'set': f'{TUNNEL_GOLD(65000)};{0x2190 + tunnel.IDX:04X}=00'}),
    ('tunnel_pay', 'walk', tunnel_yes(6),
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
    # 넘김(_handover): 끝 상자가 뜰 때 3장 flag 가 꺼지고 비울 칸이 0, 금화가 FC 4장 시작 금화
    ('tunnel_song_side', 'warp', TUNNEL_EAST, {'map': tunnel.OPEN_MAP, 'set': HAND_MARKS}),
    ('tunnel_song', 'walk', f'{TUNNEL_TO_END};wait:60;{taps(3, 120)};wait:400',
     {'map': tunnel.OPEN_MAP, 'bytes': {'SONG': tunnel.ENDING_SONG, **HAND_WANT}, 'off': ['HAND_CH3']}),
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
# 47/01 이주민 둘의 인물 슬롯: 47/01 목록 첫 두 사람(인물 슬롯 8 부터 목록 차례)
MIGRANT_SLOTS = (8, 9)
# 47/01 도착 계단 (10,31) → 이주민이 지나가게 (6,31) 로 비켜 둘 다 서쪽 계단에서 빠질 때까지 기다렸다가(FC 빠르기라 3000프레임
# 남짓) 계단을 밟지 않게 열 03 으로 → (03,0C) → (0A,0C) → (0A,06) → (12,06) → (12,04) → (1E,04) → 계단 앞 (1E,02)
SEAM_THROUGH = '6,31;' + ';'.join(f'gone:{s}' for s in MIGRANT_SLOTS) + ';6,25;20,25;20,13;36,13;36,9;60,9;60,5'
SEAM = [
    ('seam_notice_side', 'warp', f'{tunnel.NOTICE_MAP},{SEAM_NOTICE_CELL[0]},{SEAM_NOTICE_CELL[1]}',
     {'map': tunnel.NOTICE_MAP}),
    ('seam_notice', 'walk', 'wait:60', {'map': tunnel.NOTICE_MAP, 'want': ['ENDOR_NOTICE'], 'off': ['TUNNEL_OPENED']}),
    ('seam_nene_side', 'warp', f'{endor.TOWN},{endor.NENE_SIDE[1][0]},{endor.NENE_SIDE[1][1] - 1}',
     {'map': endor.TOWN, 'set': set_flag(endor.SHOP)}),
    ('seam_nene', 'walk', talk_yes('right', 12), {'map': endor.TOWN, 'want': ['TUNNEL_OPENED']}),
    ('seam_tunnel_side', 'warp', f'{tunnel.BLOCKED},{TUNNEL_ARRIVAL[0]},{TUNNEL_ARRIVAL[1] - 3}', {'map': tunnel.BLOCKED}),
    ('seam_out', 'walk', 'down:16;wait:60', {'field': True, 'cell': TUNNEL_FIELD, 'poke': wc.DAY}),
    ('seam_in', 'walk', f'{TUNNEL_FIELD[0]},{TUNNEL_FIELD[1] - 2};wait:60',
     {'map': tunnel.OPEN_MAP, 'field': False, 'cell': tunnel.OPEN_ARRIVAL, 'poke': wc.DAY}),
    ('seam_through', 'walk', f'{SEAM_THROUGH};right:16;wait:60;{taps(3, 120)};wait:400',
     {'map': tunnel.OPEN_MAP, 'maxf': 12000, 'bytes': {'SONG': tunnel.ENDING_SONG}}),
]
# 공사 재개(tunnel_resume)·「재개만으로는 막힘」(tunnel_closed_in, OPENED 꺼짐) 뒤, OPENED 를 set 하는 tunnel_open 묶음 앞에
_at = next(k for k, seg in enumerate(SEGMENTS) if seg[0] == 'tunnel_closed_in') + 1
SEGMENTS[_at:_at] = SEAM


def hero_cases():
    out = {}
    # 뚫린 굴의 이주민 둘은 조작을 막지 않고 서쪽 계단 (05,0F) 까지 걸어 사라진다. 주인공이 그 계단(엔돌 쪽에서 든 도착
    # 칸)이나 길 가운데 (0A,08) 에 서 있으면 다가와 기다리고, 주인공이 길 옆((03,0F)·(0B,08))으로 비키면 지나가 사라진다
    # 기다리는 프레임은 FC 빠르기(한 칸 96프레임)로 이주민이 주인공 앞 토막까지 오는 데 넉넉한 것: 계단은 26칸, 길 가운데는
    # 15칸 뒤
    sx, sy = tunnel.OPEN_ARRIVAL
    for name, (x, y), (ax, ay), before in (('stairs', (sx, sy), tunnel.cell(0x03, 0x0F), 2900),
                                           ('path', tunnel.cell(0x0A, 0x08), tunnel.cell(0x0B, 0x08), 1800)):
        away = f'{ax},{ay}'
        out[f'tunnel-migrants-{name}'] = {'warp': f'{tunnel.OPEN_MAP},{x},{y - 1}', 'set': '',
                                          'walk': f'wait:{before};{away};wait:700', 'free': away, 'want': [],
                                          'map': tunnel.OPEN_MAP, 'maxf': before + 1500}
    return out


# 조작을 막지 않고 걷는 인물(test_dq4heroblock.WALK_EXEMPT)
WALK_EXEMPT = {
    tunnel.SCRIPTS['migrant'][1]: '뚫린 굴 이주민: 조작을 막지 않고 FC 빠르기로 한 칸씩 서쪽 계단으로 나간다. 앞 길 둘레에 '
                                  '주인공이 있으면 기다린다(dq4ch3tunnel.GAP·pace, tunnel-migrants-* 사례 겹침 0)',
    tunnel.SCRIPTS['traveler'][1]: '뚫린 굴 나그네: 조작을 막지 않고 동쪽 계단으로 나간다. 이주민과 같음',
}
