"""UI 깨짐 규칙 1a 테두리: 창 네 변의 칸에 그 자리 테두리 타일의 흰 선이 다 보여야 한다(dq4winwatch 의 규칙 파일).

자리마다 와야 할 타일은 모서리 08C, 위·아래 변 08D, 옆 변 08E 와 그 뒤집기다. 화면 칸 그림이 그 타일의 흰 선 점(색 1)을
모두 흰색으로 가져야 한다. 이름 위 줄을 합성한 칸·탁점 붙은 변(092~095)·구분선 이음(08F)·이음 모서리(08B)는 선이
그대로라 통과한다. 위에 있는 다른 창에 가려진 칸은 뺀다.
"""
import dq4winwatch as ww

NAME = '테두리'
MODE = 'fail'
ALLOW = ()
NEXT_PAGE = 0x7D

# 알려진 깨짐: 장면마다 (칸, 가장 오래 보인 프레임 수)와 까닭. 고치면 그 장면 눈금이 「걸리지 않음」 으로 실패하니 지운다
EQUIP = ('3장 장비 화면 「무기」 창 (2,18)-(12,29) 의 줄 글자 칸이 한 칸 밀려 오른쪽 테두리를 덮고 첫 줄이 조각남'
         '(창 글자 칸 넘침과 같은 화면)')
GIVE = '도구 → 건네기 때 「누구에게」 창 (17,10)-(25,18) 위 변을 글자 칸이 덮음(창 검사 give-full·give-shop 의 바뀜·비침과 같은 때)'
STATUS1 = '1인 상태 창 (19,22)-(27,28) 위 변 이름 자리에 이름 대신 조각 글자가 보임'
SAVE = '모험의 서 고르기 창 (8,5)-(11,29) 에서 장소 이름(바트랜드) 끝 글자 칸이 오른쪽 테두리를 덮음'
SWAMP = '늪 장면에서 메시지 창이 열리는 동안 주문 창 (4,15)-(20,24) 아랫부분이 지워져 보임'
SWAMP_CELLS = tuple(((r, c), 3) for r in (17, 18, 19) for c in (15, 24)) + tuple(((20, c), 3) for c in range(15, 25))
# 1장 세이브 검사(dq4ch1savecheck)와 그 호환 장면(dq4compatscenes save-high)은 같은 세이브 장면을 돈다
SAVES = tuple((f'*/{run}/{name}', SAVE, (((9, 29), 137),)) for run in ('ch1save', 'save-high')
              for name in ('boss', 'hoimin', 'night', 'prologue', 'report'))
SAVES += tuple((f'*/{run}/swamp-hoimin', SWAMP, SWAMP_CELLS) for run in ('ch1save', 'save-high'))
KNOWN = tuple(ww.Known(scene, frozenset({cell}), frames, why) for scene, why, cells in (
    ('*/equip-ch3', EQUIP, (((4, 3), 7), ((4, 29), 7), ((5, 29), 334))),
    ('*/give-full', GIVE, (((17, 17), 12),)),
    ('*/give-shop-ch1', GIVE, tuple(((17, c), 15) for c in range(11, 18))),
    ('*/screens/status-mesence', STATUS1, (((19, 23), 10), ((19, 24), 10))),
) + SAVES for cell, frames in cells)


def check(screen):
    out = []
    for w in screen.rects:
        for r, c, t, h, v in ww.border_cells(w):
            if screen.stroke_ok(r, c, t, h, v) or screen.hidden(w, r, c):
                continue
            # 메시지 넘김 표시 ▼ 는 원래 DQ5 가 메시지 창 아래 변 위에 그린다
            if t == ww.EDGE and v and screen.word(r, c) & 0x3FF == ww.PROMPT:
                continue
            # 다음 쪽 표시 → 는 네네 보기 창이 위 변 둘째 칸에 테두리와 번갈아 깜박인다(dq4-window-text-format 네네 보기 창)
            if t == ww.EDGE and not v and c == w[1] + 1 and screen.word(r, c) & 0xC3FF == NEXT_PAGE:
                continue
            edge = ('위', '아래')[r == w[2]] if r in (w[0], w[2]) else ('왼쪽', '오른쪽')[c == w[3]]
            out.append((r, c, f'창 {w} 의 {edge} 변 칸이 {screen.word(r, c):04X}'))
    return out
