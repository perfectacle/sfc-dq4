"""화면 글자 읽기 상태: 장면마다 winwatch.log 에 글자를 읽은 줄 수를 한 줄 남긴다. 글꼴(DQ4_GALMURI)이 없어 dq4wintext 가
글자를 읽지 못한 장면이면 그렇다고 남긴다. 글자 규칙(잘림·조사·모르는 잉크 등)이 「안 봐서 통과」 로 보이지 않게 하는
표시다. 늘 report(실패로 올리지 않는다). 창이 떴는데 한 줄도 못 읽은 장면은 dq4winrule_wintextzero 가 실패로 건다.
"""
import dq4wintext as wt

NAME = '글자 읽기'
MODE = 'report'
ALLOW = ()


NO_FONT, FAKE_ROM = 'no font', 'fake rom'


def read_lines(run):
    """(창이 뜬 안정 모습 수, 읽은 줄 수). 글꼴이 없으면 NO_FONT, 가짜 롬(단위 시험)이면 FAKE_ROM."""
    try:
        wt.font('galmuri9')
    except SystemExit:
        return NO_FONT
    if not wt.comparable(run.ref.rom):
        return FAKE_ROM
    shots = lines = 0
    for _, screen, _ in wt.steady_screens(run):
        if not screen.rects:
            continue
        got = wt.lines(screen)
        if got is None:
            return NO_FONT
        shots += 1
        lines += sum(len(v) for v in got.values())
    return shots, lines


def check_run(run):
    got = read_lines(run)
    if got == FAKE_ROM:
        return []
    if got == NO_FONT:
        return [(0, 'DQ4_GALMURI 없음, 글자 규칙을 안 봄')]
    return [(0, f'창이 뜬 모습 {got[0]}개에서 {got[1]}줄 읽음')]
