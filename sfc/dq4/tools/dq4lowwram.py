"""낮은 WRAM(7E:0000~1FFF) 가운데 dq4 코드가 자기 몫으로 쓰는 칸의 예약표(정본)와, 그 둘레에서 원래 DQ5 코드가 쓰는 범위.

DQ5 트랙의 실행 실측(dq5-hangul-format 「쓰이지 않은 자리」)으로 고른 빈자리 7E:1A86~·1ABC~·1BBE~·1C33~ 에 여러 모듈이 칸을
나눠 둔다. 그 가운데 7E:1BBE~1BFF 는 DQ5 의 사람 자리 표와 일부 맵 루틴이 쓰는 자리라(DQ5_USES), 거기 놓인 dq4 칸은 맵을
드는 사이에 걸쳐 살아야 하는 값(LIFE 'persistent')이면 안 된다. test_dq4lowwram 이 칸끼리 겹치지 않는지, DQ5 범위와 겹치는
칸이 오래 사는 값이 아닌지, 모듈의 상수가 이 표와 같은지 본다.

실측(dq5wramwatch --range 1BBE-1BFF, 1장 걷기 전체·3장 엔돌 검사 전체):
  - 원래 DQ5 코드의 쓰기는 전원·리셋 때 WRAM 을 지우는 00:864C 와, 1장 필드·ルーラ 장면의 02:87E0~87F2(사람 자리 표
    채우기, 02:87D2 루틴)뿐이었다. 그 표를 읽는 02:871A 고리는 어느 장면에서도 돌지 않았다.
  - 필드 채우기가 있은 장면(field·fly)에서 그 표 자리에 쓴 dq4 칸은 이름 입력의 방향 상태(창마다 새로 정함)뿐이었다.
"""

# 원래 DQ5 코드가 쓰는 범위 [시작, 끝). 주소는 7E 뱅크 낮은 16비트
DQ5_USES = {
    'people': (0x1BC5, 0x1BFD),      # 사람 자리 표 넷 1BC5·1BD3·1BE1·1BEF + 0~13. 02:87D2·93AE·8B1A 가 채우고 02:871A 가 읽음
    'map_routine': (0x1BB5, 0x1BC2),  # DQ5 맵 무리 50·51·53 의 맵별 루틴(02:86C6~8711, 1BB5~1BBE·1BC1 을 씀)
}

# 칸이 사는 동안: 'routine' 루틴 한 번, 'message' 메시지 한 장, 'window' 창이 떠 있는 동안, 'scene' 한 맵 안의 사건,
# 'persistent' 맵을 드는 사이에도 남아야 함
LIVES = ('routine', 'message', 'window', 'scene', 'persistent')

# (시작, 끝, 모듈, 이름, 사는 동안)
CELLS = (
    (0x1A94, 0x1A98, 'dq4soundpatch', 'KEEP_BUSY·KEEP_SONG', 'persistent'),
    (0x1ABC, 0x1ABD, 'dq4bg3slot', 'SHOWN', 'persistent'),
    (0x1ABD, 0x1ABE, 'dq4swampdeath', 'WHO', 'message'),
    (0x1AC0, 0x1BB0, 'dq4menupatch', 'SHARED_WRAM', 'persistent'),
    (0x1BB0, 0x1BB1, 'dq4menupatch', 'MENU_FLAG', 'persistent'),
    (0x1BC0, 0x1BC2, 'dq4josa', 'LAST', 'message'),
    (0x1BC4, 0x1BC5, 'dq4prologue', 'TALKER', 'scene'),
    (0x1BC6, 0x1BD6, 'dq4ch1event', 'SCRATCH', 'routine'),
    (0x1BD6, 0x1BE0, 'dq4neneshop', 'TEMP', 'routine'),
    (0x1BE0, 0x1BE8, 'dq4nameentry', 'in_direction~in_steady', 'window'),
    (0x1BE8, 0x1BFC, 'dq4prologue', 'ROUTE_BUF', 'scene'),
    (0x1C0A, 0x1C0C, 'dq4ch2event', 'STEP_COUNT', 'scene'),
    (0x1C40, 0x1D84, 'dq4windowname', 'wn_keys~wt_stack', 'window'),
)


def overlaps(a, b):
    return a[0] < b[1] and b[0] < a[1]


def problems():
    """[문제 문장]. 칸끼리 겹침, DQ5 범위와 겹치는 오래 사는 칸."""
    out = []
    cells = sorted(CELLS)
    for x, y in zip(cells, cells[1:]):
        if overlaps(x, y):
            out.append(f'{x[2]}.{x[3]} 와 {y[2]}.{y[3]} 가 겹침')
    for c in cells:
        if c[4] not in LIVES:
            out.append(f'{c[2]}.{c[3]}: 모르는 사는 동안 {c[4]}')
        for name, r in DQ5_USES.items():
            if overlaps(c, r) and c[4] == 'persistent':
                out.append(f'{c[2]}.{c[3]}: DQ5 {name}({r[0]:04X}~{r[1] - 1:04X})와 겹치는데 맵을 넘어 살아야 함')
    return out
