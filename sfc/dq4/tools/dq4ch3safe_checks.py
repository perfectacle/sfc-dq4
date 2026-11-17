"""북쪽 동굴과 금고·여신상 동굴의 배(dq4ch3safe)의 검사 표. 내놓는 것은 dq4ch3checks 머리말.

걷기 표는 묶음 셋이다: gates(수문·금고 상자), cave(입구에서 금고까지 걷기·구르는 바위), raft(여신상 동굴의 배).
"""
import dq4ch1walkcheck as wc
import dq4ch3endor as endor
import dq4ch3safe as safe
from dq4ch3walkparts import CLOSE, FACE_UP, SEARCH

FLAG_BLOCKS = {
    'gates': {
        'SAFE_DRAINED': wc.flag(safe.DRAINED),
        'SAFE_ANSWERED': wc.flag(safe.ANSWERED),
        'SAFE_YES': wc.flag(safe.YES),
        # 톨네코 물건 칸 2(칸 0 옷, 칸 1 도시락 다음): 금고 상자를 열면 철 금고가 들어오는 칸
        'SAFE_SLOT': (0x7E2056 + 2, 0xFF),
    },
    'cave': {
        # 구르는 바위(dq4boulder)의 메움 비트(bit0 왼쪽 구덩이, bit1 가운데)
        'SAFE_FILL': (safe.BOULDER_VARS(safe.boulder.FILL), 0xFF),
    },
    'raft': {
        'RAFT_RIDING': wc.flag(safe.RIDING),
        'RAFT_X': (safe.RAFT_VARS + safe.raft.RX, 0xFF),
        'RAFT_Y': (safe.RAFT_VARS + safe.raft.RY, 0xFF),
    },
}

# 북쪽 동굴: 오른쪽·왼쪽 수문 앞 주인공 셀(dq4ch3safe.RIGHT·LEFT 의 사각형 왼쪽 아래). 순간이동은 두 셀 아래에 내려
# 위로 걸어 선다. 바닥 글은 세 쪽 뒤 「예」 에 커서
SAFE_RIGHT = (safe.RIGHT['rect'][0], safe.RIGHT['rect'][3])
SAFE_LEFT = (safe.LEFT['rect'][0], safe.LEFT['rect'][3])
SAFE_OFF = ['SAFE_ANSWERED', 'SAFE_YES']
SAFE_ASK = 'wait:30'
SAFE_FLOOR = 'a:8;wait:80;a:8;wait:80;a:8;wait:120'

SEGMENT_BLOCKS = {
    # 북쪽 동굴(dq4ch3safe). 수문 앞 칸에 서면 묻고, 「아니요」 면 그대로, 칸을 떠났다 다시 서서 「예」 면 물살에 계단으로
    'gates': [
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
        ('safe_open', 'walk', SEARCH, {'poke': FACE_UP, 'items': [safe.IRON_SAFE]}),
        ('safe_return', 'walk', f'8,9;wait:60;8,8;wait:300;{SAFE_FLOOR};a:8;wait:200;a:8;wait:200;{CLOSE}',
         {'map': safe.VAULT, 'cell': (8, 8), 'bytes': {'SAFE_SLOT': 0xFF}, 'off': SAFE_OFF}),
        ('safe_reopen', 'walk', f'8,9;wait:60;{SEARCH}', {'poke': FACE_UP, 'items': [safe.IRON_SAFE]}),
    ],
    # 입구에서 금고까지 순간이동 없이: 입구 층 → 3E/04 위 → 오른쪽 통로 계단으로 입구 층 아래 → 3E/04 왼쪽 방 →
    # 왼쪽 수문 「예」 → 3E/06 → 3E/07 → 바위를 줄 13 오른쪽·열 0B 아래·줄 1E 왼쪽으로 이끌어 왼쪽 구덩이를 메움 →
    # 메운 구덩이를 건너 3E/09 → 금고 상자. 기다림은 바위가 멈출 자리에 닿을 때까지(헤드리스 실측 + 여유). 끝에 금고 방
    # 계단으로 돌아와 위로 걸으면 바위가 처음 자리로 돌아가 있어 3E/08 로 떨어짐
    'cave': [
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
        ('safe_take', 'walk', f'20,39;8,39;8,9;wait:30;{SEARCH}', {'map': safe.VAULT, 'items': [safe.IRON_SAFE]}),
        ('safe_fall_back', 'walk', '8,39;24,39;down:20;wait:300;8,73;wait:300',
         {'map': safe.PIT_BELOW, 'changes': 2, 'after': 60, 'bytes': {'SAFE_FILL': 0x00}}),
        # 바위를 가운데 구덩이로: 줄 1E 에서 주인공이 X ≥ 05 면 바위가 오른쪽으로, 열 0B 에서 아래로 굴러 가운데 구덩이를
        # 메움(그 길은 3E/08 아래 계단으로 이어짐)
        ('safe_boulder_mid_side', 'warp', f'{safe.ROLL},6,22', {'map': safe.ROLL}),
        ('safe_boulder_mid', 'walk', '6,29;8,29;8,61;16,61;wait:810;22,61;22,53;wait:270;22,39;8,39;8,43;wait:520;'
         '8,39;22,39;22,89;22,91;wait:200', {'map': safe.PIT_BELOW, 'changes': 1, 'after': 60, 'bytes': {'SAFE_FILL': 0x02}}),
    ],
    # 여신상 동굴 배(dq4raft): 단추 앞(앞 구간이 켠 BUTTON 을 끔). 입구 층의 배 칸으로 걸어 들어가 타고 호수를 돌아
    # 아래 끝에서 48/05 의 물로 넘어간다
    'raft': [
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
        ('raft_statue', 'walk', f'wait:200;18,39;18,37;16,37;16,33;12,33;12,11;wait:30;{SEARCH}',
         {'map': endor.STATUE_ROOM, 'items': [endor.STATUE]}),
    ],
}

# 48/02 의 배 인물 슬롯: 목록 첫 인물이라 첫 인물 슬롯(dq5npclists.SLOT_FIRST)
RAFT_SLOT = 0x08


def hero_cases():
    out = {}
    # 북쪽 동굴 수문 앞 칸(FC 한 칸 = 주인공 두 열)마다: 아래에서 올라서 「예」 면 물살에 밀려 옮겨 가고 조작이 돌아온다
    yes = 'up:40;wait:230;a:8;wait:60;a:8;wait:1300'
    for side, spec, free, want in (('right', safe.RIGHT, '18,47', []), ('left', safe.LEFT, '20,27', [('SAFE_DRAINED', safe.DRAINED)])):
        x0, _, _, y1 = spec['rect']
        for x in (x0, x0 + 1):
            out[f'safe-{side}-{x}'] = {'warp': f'{safe.GATES},{x},{y1 + 2}', 'set': '', 'walk': yes, 'free': free,
                                       'want': want, 'map': spec['to'][0], 'maxf': 4000}
    # 구르는 바위(3E/07): 풀리는 칸 (03~04,0E)를 주인공 두 열(셀 X 6·7·8)로 지나 왼쪽 통로를 내려가 기다리면 바위가 바로
    # 위에서 멈춘다. 위로 밀어도 지나가지 못하고, 줄 1E 로 비켜 가운데 통로로 걸어 갈 수 있어야 한다(바위가 일행과 겹치거나
    # 길을 영영 막지 않음). 구덩이 바로 위에서 기다리면 갇히지 않고 구덩이로 떨어져 3E/08 로
    for x in (6, 7, 8):
        out[f'safe-boulder-{x}'] = {'warp': f'{safe.ROLL},{x},22', 'set': '',
                                    'walk': f'{x},49;wait:500;up:30;wait:60;{x},61', 'free': '20,61',
                                    'want': [], 'map': safe.ROLL, 'maxf': 4000}
    out['safe-boulder-pit'] = {'warp': f'{safe.ROLL},6,22', 'set': '', 'walk': '6,73;wait:900;down:40;wait:300',
                               'free': '6,29', 'want': [], 'map': safe.PIT_BELOW, 'maxf': 4000}
    # 여신상 동굴 배(48/02, FC 40/00 배 (16,05)). 배 칸이 아닌 물 칸으로는 못 걷는다: 배 위 칸 (15,04)에서 오른쪽 물
    # (16,04)로 밀기, 배를 타고 한 칸 가서 땅에 내린 뒤(배는 (16,05)에 남음) 위 칸에서 다시 물로 밀기. 배는 단추 앞에만 있다
    off = f'{0x2190 + endor.BUTTON[0]:04X}&{~endor.BUTTON[1] & 0xFF:02X}'
    out['raft-water'] = {'warp': f'{endor.CAVE_ENTRY},42,8', 'set': off, 'walk': 'right:40;wait:30', 'hero_at': (42, 9),
                         'free': '24,9', 'want': [], 'map': endor.CAVE_ENTRY, 'maxf': 2000}
    out['raft-left-water'] = {'warp': f'{endor.CAVE_ENTRY},42,10', 'set': off,
                              'walk': '44,11;46,11;44,11;42,11;42,9;right:40;wait:30', 'hero_at': (42, 9),
                              'free': '24,9', 'want': [], 'not': [('RAFT_RIDING', safe.RIDING)], 'map': endor.CAVE_ENTRY,
                              'maxf': 3000, 'ride': (RAFT_SLOT,)}
    return out
