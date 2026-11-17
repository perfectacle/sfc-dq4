"""빈 산트하임 성과 2장 끝(dq4ch2ending)의 검사 표. 내놓는 것은 dq4eventchecks 머리말."""
import dq4ch1walkcheck as wc
import dq4ch2event as ch2
import dq4ch2ending as ending
from dq4ch2walkparts import CLOSE, flag, taps

FLAGS = {
    'SEEN_BREY': flag(ending.SEEN_BREY),
    'SEEN_KIRYL': flag(ending.SEEN_KIRYL),
    # 지금 울리는 곡 자리(선택 bytes 로만 본다)
    'SONG': (0x7E1D8B, 0xFF),
}

# 왕좌의 방에서 성 앞마당으로 내려가는 계단(셀 (22,35), dq4groupcheck 의 stair-3D01-1)의 오른쪽 칸에서 왼쪽으로
ENDING_STAIRS = '24,35;left:32'
SARAN = '45/00'
SARAN_OUT, GATE_IN = 'down:60;68,149', '78,149;78,147'

# 빈 산트하임 성과 2장 끝(dq4ch2ending). 우승 flag 가 켜진 앞 구간 뒤라 성이 비어 있다. 왕좌의 방·왕의 방에 들어서면
# 브라이·크리프트가 말한다. 본 flag 가 켜진 채 성 앞마당에 들어서면 장 끝이라, 앞마당을 들르는(HOPS) 왕좌의 방 묶음을
# 먼저 두고 그 묶음에서 계단으로 내려가 장 끝 서술 → 「다음에 계속」 상자 → 리셋까지 본다
SEGMENTS = [
    ('empty_throne_side', 'warp', f'{ch2.THRONE},24,36', {'map': ch2.THRONE}),
    ('empty_brey', 'walk', 'wait:60;' + taps(1, 60) + ';' + CLOSE, {'want': ['SEEN_BREY'], 'map': ch2.THRONE}),
    ('empty_leave', 'walk', ENDING_STAIRS, {'map': ch2.CASTLE, 'changes': 1, 'after': 60}),
    ('empty_end', 'ending', ending.END_SCENE, {}),
    ('empty_bedroom_side', 'warp', f'{ch2.BEDROOM},22,9', {'map': ch2.BEDROOM}),
    ('empty_kiryl', 'walk', 'wait:60;' + taps(2, 60) + ';' + CLOSE, {'want': ['SEEN_KIRYL'], 'map': ch2.BEDROOM}),
    # 두 사람의 말을 본 뒤 성을 나갔다가 필드에서 성문으로 들어와도 끝난다. 이웃 사란(FC 13/00, 필드 입구 (22,49))의
    # 도착 칸에서 아래로 나가 필드 (68,149), 오른쪽으로 걸어 성 입구 블록 (27,49) 아래에서 위로 든다
    ('gate_end_side', 'warp', f'{SARAN},24,50', {'map': SARAN}),
    ('gate_out', 'walk', SARAN_OUT, {'field': True, 'cell': (68, 149), 'poke': wc.DAY}),
    ('gate_in', 'walk', GATE_IN, {'map': ch2.CASTLE, 'changes': 1, 'after': 60, 'poke': wc.DAY}),
    ('gate_end', 'ending', ending.END_SCENE, {}),
    # 엔딩 곡은 들어선 뒤 약 190프레임에 지금 곡이 되고 서술이 바로 뒤따른다(곡 자료를 올리는 동안 검은 화면).
    # 장 끝 구간과 묶음을 나누는 것은 그만큼 늦게 남긴 상태로 끝 상자를 넘기면 서술을 넘기는 A 가 남아 리셋 뒤 타이틀에서 눌리기 때문이다(bsnes 에서 소리 없음)
    ('song_side', 'warp', f'{SARAN},24,50', {'map': SARAN}),
    ('song_out', 'walk', SARAN_OUT, {'field': True, 'poke': wc.DAY}),
    ('song_in', 'walk', GATE_IN, {'map': ch2.CASTLE, 'changes': 1, 'after': 400, 'poke': wc.DAY,
                                  'bytes': {'SONG': ending.ENDING_SONG}}),
]
