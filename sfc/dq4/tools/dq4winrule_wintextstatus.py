"""화면 글자 읽기 상태: 글꼴(DQ4_GALMURI)이 없어 dq4wintext 가 글자를 읽지 못한 장면이면 winwatch.log 에 한 줄 남긴다. 글자
규칙(잘림·조사·모르는 잉크 등)이 「안 봐서 통과」 로 보이지 않게 하는 표시다. 늘 report(실패로 올리지 않는다).
"""
import dq4wintext as wt

NAME = '글자 읽기'
MODE = 'report'
ALLOW = ()


def check_run(run):
    try:
        wt.font('galmuri9')
    except SystemExit:
        return [(0, '글자 읽기: DQ4_GALMURI 없음, 글자 규칙을 안 봄')]
    return []
